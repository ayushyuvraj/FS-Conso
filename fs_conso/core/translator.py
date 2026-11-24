"""Foreign currency translation engine (Ind AS 21).

Applies Closing, Average, and Historical rates and generates exact FCTR plug.
Supports multi-period date-effective rate tables and missing FX detection.
"""

from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from fs_conso.models.coa import AccountClassification, ChartOfAccounts
from fs_conso.models.entity import LegalEntity
from fs_conso.models.fx import FXRateEntry, FXRateTable
from fs_conso.models.trial_balance import StandardizedRow, StandardizedTrialBalance


class TranslatedRow(BaseModel):
    """An individual line item translated into the parent reporting currency (e.g. INR)."""
    account_code: str
    account_description: str
    source_currency: str
    source_amount: float
    rate_applied: float
    rate_type: str  # "Closing", "Average", "Historical", "Identity", "FCTR_Plug"
    translated_amount: float
    is_fctr_plug: bool = False
    formula: Optional[str] = None


class TranslatedTrialBalance(BaseModel):
    """Translated Trial Balance in reporting currency (Sum == 0.00)."""
    entity_code: str
    period: str
    reporting_currency: str = "INR"
    rows: List[TranslatedRow] = Field(default_factory=list)
    fctr_row: Optional[TranslatedRow] = None

    @property
    def total_translated(self) -> float:
        return round(sum(r.translated_amount for r in self.rows), 2)

    @property
    def is_tallied(self) -> bool:
        return abs(self.total_translated) < 0.01


class FXTranslationEngine:
    """Performs Ind AS 21 currency translation with exact FCTR balancing."""

    def __init__(self, coa: ChartOfAccounts, fx_table: Optional[FXRateTable] = None):
        self.coa = coa
        self.fx_table = fx_table or FXRateTable()

    @classmethod
    def check_missing_rates(
        cls,
        entities: List[LegalEntity],
        fx_table: Optional[FXRateTable],
        reporting_currency: str = "INR",
        presentation_currency: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """Identifies foreign currencies in scope that lack exchange rates to the reporting currency."""
        missing = []
        rep = (presentation_currency or reporting_currency).upper()
        tbl = fx_table or FXRateTable()
        for ent in entities:
            curr = ent.input_currency.upper()
            if curr != rep:
                rate = tbl.get_rate(curr, rep)
                if not rate:
                    pair = (curr, rep)
                    if pair not in missing:
                        missing.append(pair)
        return missing

    def translate(
        self,
        std_tb: StandardizedTrialBalance,
        reporting_currency: str = "INR"
    ) -> TranslatedTrialBalance:
        translated_rows: List[TranslatedRow] = []

        # If already in reporting currency, identity translation
        is_identity = (std_tb.currency.upper() == reporting_currency.upper())
        fx_entry: Optional[FXRateEntry] = self.fx_table.get_rate(std_tb.currency, reporting_currency)

        if not is_identity and fx_entry is None:
            raise ValueError(
                f"MISSING FX RATE: No exchange rate found for currency pair '{std_tb.currency}' -> '{reporting_currency}' "
                f"for period '{std_tb.period}'. Please upload or configure exchange rates for this date."
            )

        for idx, row in enumerate(std_tb.rows, start=1):
            coa_item = self.coa.get_item(row.account_code)
            acc_type = coa_item.account_type if coa_item else AccountClassification.ASSET

            if is_identity or fx_entry is None:
                rate = 1.0
                rate_type = "Identity"
            else:
                # Ind AS 21 Translation Rules:
                # Balance Sheet Assets & Liabilities: Closing Rate
                # Profit & Loss (Income & Expenses): Average Rate
                # Equity & Share Capital: Historical Rate
                if acc_type in (AccountClassification.ASSET, AccountClassification.LIABILITY):
                    rate = fx_entry.closing_rate
                    rate_type = "Closing"
                elif acc_type in (AccountClassification.INCOME, AccountClassification.EXPENSE):
                    rate = fx_entry.average_rate
                    rate_type = "Average"
                elif acc_type == AccountClassification.EQUITY:
                    rate = fx_entry.historical_rate
                    rate_type = "Historical"
                else:
                    rate = fx_entry.closing_rate
                    rate_type = "Closing"

            trans_amt = round(row.amount * rate, 2)
            translated_rows.append(TranslatedRow(
                account_code=row.account_code,
                account_description=row.account_description,
                source_currency=std_tb.currency,
                source_amount=row.amount,
                rate_applied=rate,
                rate_type=rate_type,
                translated_amount=trans_amt,
                is_fctr_plug=False
            ))

        # Check translation balance
        subtotal = round(sum(r.translated_amount for r in translated_rows), 2)
        fctr_row = None

        # If difference exists and foreign currency was translated, plug FCTR
        if not is_identity and abs(subtotal) > 0.001:
            fctr_plug = -subtotal
            fctr_row = TranslatedRow(
                account_code="O620102",  # Group COA: Foreign Currency Translation Differences
                account_description="Foreign Currency Translation Reserve (FCTR Plug)",
                source_currency=std_tb.currency,
                source_amount=0.0,
                rate_applied=1.0,
                rate_type="FCTR_Plug",
                translated_amount=round(fctr_plug, 2),
                is_fctr_plug=True
            )
            translated_rows.append(fctr_row)

        return TranslatedTrialBalance(
            entity_code=std_tb.entity_code,
            period=std_tb.period,
            reporting_currency=reporting_currency,
            rows=translated_rows,
            fctr_row=fctr_row
        )
