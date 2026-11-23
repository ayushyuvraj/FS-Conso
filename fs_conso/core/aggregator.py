"""Consolidated Trial Balance Aggregator."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from fs_conso.core.translator import TranslatedRow, TranslatedTrialBalance
from fs_conso.models.coa import ChartOfAccounts
from fs_conso.models.elimination import EliminationVoucher

class ConsolidatedTBRow(BaseModel):
    account_code: str
    account_description: str
    entity_balances: Dict[str, float] = Field(default_factory=dict)
    total_entities: float = 0.0
    eliminations: float = 0.0
    adjustments: float = 0.0
    consolidated_total: float = 0.0

    def __init__(self, **data):
        if "entity_translated_amounts" in data and "entity_balances" not in data:
            data["entity_balances"] = data["entity_translated_amounts"]
        if "consolidated_net" in data and "consolidated_total" not in data:
            data["consolidated_total"] = data["consolidated_net"]
        if "eliminations_total" in data and "eliminations" not in data:
            data["eliminations"] = data["eliminations_total"]
        super().__init__(**data)

    @property
    def entity_translated_amounts(self) -> Dict[str, float]:
        return self.entity_balances

    @property
    def eliminations_total(self) -> float:
        return self.eliminations

    @property
    def consolidated_net(self) -> float:
        return self.consolidated_total

# Alias for compatibility
ConsolidatedRow = ConsolidatedTBRow

class ConsolidatedTrialBalance(BaseModel):
    period: str
    currency: str = "INR"
    entity_codes: List[str] = Field(default_factory=list)
    rows: List[ConsolidatedTBRow] = Field(default_factory=list)

    @property
    def total_consolidated(self) -> float:
        return round(sum(r.consolidated_total for r in self.rows), 2)

    @property
    def is_tallied(self) -> bool:
        return abs(self.total_consolidated) < 0.01

class TBAggregator:
    """Aggregates translated entity TBs and intercompany eliminations into Consolidated TB."""

    @classmethod
    def aggregate(
        cls,
        coa: ChartOfAccounts,
        translated_tbs: List[TranslatedTrialBalance],
        elimination_vouchers: Optional[List[EliminationVoucher]] = None,
        period: str = "31-Mar-2024",
        currency: str = "INR"
    ) -> ConsolidatedTrialBalance:
        entity_codes = [tb.entity_code for tb in translated_tbs]
        all_accounts: Dict[str, str] = {}

        # Collect all active accounts
        for tb in translated_tbs:
            for r in tb.rows:
                all_accounts[r.account_code] = r.account_description

        # Elimination impacts per account
        elim_map: Dict[str, float] = {}
        if elimination_vouchers:
            for v in elimination_vouchers:
                # Elimination reduces reciprocal balance
                # Debit account gets positive adjustment, Credit gets negative
                elim_map[v.debit_account] = elim_map.get(v.debit_account, 0.0) + v.eliminated_amount
                elim_map[v.credit_account] = elim_map.get(v.credit_account, 0.0) - v.eliminated_amount

        # Build rows in sorted order according to Group COA
        sorted_codes = sorted(all_accounts.keys(), key=lambda c: (coa.get_item(c).fs_statement if coa.get_item(c) else "ZZ", c))
        rows: List[ConsolidatedTBRow] = []

        for code in sorted_codes:
            desc = all_accounts[code]
            ent_bals: Dict[str, float] = {}
            for tb in translated_tbs:
                ent_bals[tb.entity_code] = round(sum(r.translated_amount for r in tb.rows if r.account_code == code), 2)

            tot_ent = round(sum(ent_bals.values()), 2)
            elim = round(elim_map.get(code, 0.0), 2)
            adj = 0.0
            conso_tot = round(tot_ent + elim + adj, 2)

            rows.append(ConsolidatedTBRow(
                account_code=code,
                account_description=desc,
                entity_balances=ent_bals,
                total_entities=tot_ent,
                eliminations=elim,
                adjustments=adj,
                consolidated_total=conso_tot
            ))

        return ConsolidatedTrialBalance(
            period=period,
            currency=currency,
            entity_codes=entity_codes,
            rows=rows
        )
