"""Validation engine for Trial Balance ingestion.

Codifies validation checks from Conso.xlsx ('2_TB_Upload' and 'Steps').
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance

class ValidationError(BaseModel):
    error_code: str
    message: str
    severity: str = "BLOCKING"  # "BLOCKING" or "WARNING"
    row_index: Optional[int] = None
    account_code: Optional[str] = None

class ValidationResult(BaseModel):
    is_valid: bool
    entity_code: str
    period: str
    errors: List[ValidationError] = Field(default_factory=list)
    total_debit: float = 0.0
    total_credit: float = 0.0
    net_difference: float = 0.0
    checked_rows: int = 0

class TBValidator:
    """Performs strict accounting validation on ingested Trial Balances."""

    @classmethod
    def validate(
        cls,
        raw_tb: RawTrialBalance,
        expected_period: Optional[str] = None,
        expected_entity: Optional[str] = None
    ) -> ValidationResult:
        errors: List[ValidationError] = []
        checked_rows = len(raw_tb.rows)

        # 1. Entity alignment check
        if expected_entity and raw_tb.entity_code.strip().lower() != expected_entity.strip().lower():
            errors.append(ValidationError(
                error_code="ENTITY_MISMATCH",
                message=f"Entity in file '{raw_tb.entity_code}' does not match expected entity '{expected_entity}'."
            ))

        # 2. Period validation check
        if expected_period and raw_tb.period.strip().lower() != expected_period.strip().lower():
            errors.append(ValidationError(
                error_code="PERIOD_MISMATCH",
                message=f"Period in file '{raw_tb.period}' does not match reporting period '{expected_period}'."
            ))

        # 3. Currency validity
        if not raw_tb.currency or not raw_tb.currency.strip():
            errors.append(ValidationError(
                error_code="MISSING_CURRENCY",
                message="Trial balance submission is missing a valid functional currency."
            ))

        # 4. Row-level checks: Blanks vs Zeroes, Missing Account Codes, Duplicates
        seen_accounts = set()
        tot_debit = 0.0
        tot_credit = 0.0
        tot_signed = 0.0
        is_two_col = False

        for idx, row in enumerate(raw_tb.rows, start=1):
            # No blank account codes
            if not row.account_code or not row.account_code.strip():
                errors.append(ValidationError(
                    error_code="BLANK_ACCOUNT_CODE",
                    message=f"Row {idx} contains an empty account code.",
                    row_index=idx
                ))
                continue

            acc_code = row.account_code.strip()
            # Duplicate account check
            if acc_code in seen_accounts:
                errors.append(ValidationError(
                    error_code="DUPLICATE_ACCOUNT",
                    message=f"Duplicate account code '{acc_code}' found at row {idx}.",
                    row_index=idx,
                    account_code=acc_code
                ))
            seen_accounts.add(acc_code)

            # Blank vs Zero distinction
            if row.is_blank:
                errors.append(ValidationError(
                    error_code="MISSING_DATA_BLANK",
                    message=f"Row {idx} (Account {acc_code}) is completely blank. Blanks indicate missing data and are not automatically converted to zeroes.",
                    row_index=idx,
                    account_code=acc_code
                ))
                continue

            # Accumulate totals
            if row.debit is not None or row.credit is not None:
                is_two_col = True
                tot_debit += (row.debit or 0.0)
                tot_credit += (row.credit or 0.0)
            if row.amount is not None:
                tot_signed += row.amount

        # 5. Balance integrity check
        net_diff = 0.0
        if is_two_col:
            net_diff = round(tot_debit - tot_credit, 2)
            if abs(net_diff) >= 0.01:
                errors.append(ValidationError(
                    error_code="UNBALANCED_TB_TWO_COL",
                    message=f"Trial balance is not tallied: Total Debits ({tot_debit:,.2f}) != Total Credits ({tot_credit:,.2f}). Difference: {net_diff:,.2f}."
                ))
        else:
            net_diff = round(tot_signed, 2)
            if abs(net_diff) >= 0.01:
                errors.append(ValidationError(
                    error_code="UNBALANCED_TB_ONE_COL",
                    message=f"Signed Trial balance does not sum to zero: Sum is {tot_signed:,.2f} (expected 0.00)."
                ))

        blocking_errors = [e for e in errors if e.severity == "BLOCKING"]
        return ValidationResult(
            is_valid=len(blocking_errors) == 0,
            entity_code=raw_tb.entity_code,
            period=raw_tb.period,
            errors=errors,
            total_debit=tot_debit,
            total_credit=tot_credit,
            net_difference=net_diff,
            checked_rows=checked_rows
        )
