"""Validation engine for Trial Balance ingestion with strict accounting & safety bounds.

Codifies validation checks from Conso.xlsx ('2_TB_Upload' and 'Steps') and strict accounting principles.
"""

import math
import re
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
    def _normalize_period(cls, p_str: Optional[str]) -> str:
        """Normalizes dates like '31-Mar-2024', '2024-03-31', '31/03/2024' to '2024-03-31'."""
        if not p_str:
            return ""
        s = p_str.strip().lower()
        # Check ISO format YYYY-MM-DD
        m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
        if m_iso:
            y, m, d = m_iso.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"

        # Check DD-MMM-YYYY (e.g. 31-mar-2024)
        months = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
            "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
        }
        m_eng = re.match(r"^(\d{1,2})[-/ ]([a-z]{3})[-/ ](\d{4})$", s)
        if m_eng:
            d, m_name, y = m_eng.groups()
            m_num = months.get(m_name, "00")
            return f"{y}-{m_num}-{int(d):02d}"

        # Check DD-MM-YYYY or DD/MM/YYYY
        m_num_date = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
        if m_num_date:
            d, m, y = m_num_date.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"

        return s

    @classmethod
    def validate(
        cls,
        raw_tb: RawTrialBalance,
        expected_period: Optional[str] = None,
        expected_entity: Optional[str] = None,
        duplicate_policy: str = "error"
    ) -> ValidationResult:
        errors: List[ValidationError] = []
        checked_rows = len(raw_tb.rows)

        # 0. Empty submission check
        if checked_rows == 0:
            errors.append(ValidationError(
                error_code="EMPTY_TRIAL_BALANCE",
                message="Trial balance submission contains zero rows. Ingestion rejected."
            ))
            return ValidationResult(
                is_valid=False,
                entity_code=raw_tb.entity_code,
                period=raw_tb.period,
                errors=errors,
                checked_rows=0
            )

        # 1. Entity alignment check
        if expected_entity and raw_tb.entity_code.strip().lower() != expected_entity.strip().lower():
            errors.append(ValidationError(
                error_code="ENTITY_MISMATCH",
                message=f"Entity in file '{raw_tb.entity_code}' does not match expected entity '{expected_entity}'."
            ))

        # 2. Period validation check with date normalization
        if expected_period:
            p_file = cls._normalize_period(raw_tb.period)
            p_exp = cls._normalize_period(expected_period)
            if p_file != p_exp:
                errors.append(ValidationError(
                    error_code="PERIOD_MISMATCH",
                    message=f"Period in file '{raw_tb.period}' does not match reporting period '{expected_period}'."
                ))

        # 3. Currency validity
        if not raw_tb.currency or not raw_tb.currency.strip() or len(raw_tb.currency.strip()) > 5:
            errors.append(ValidationError(
                error_code="MISSING_CURRENCY",
                message="Trial balance submission is missing a valid functional currency (e.g. INR, USD)."
            ))

        # 4. Row-level checks
        seen_accounts = set()
        tot_debit = 0.0
        tot_credit = 0.0
        tot_signed = 0.0
        is_two_col = False

        dup_severity = "WARNING" if duplicate_policy.lower() == "warn" else "BLOCKING"

        for idx, row in enumerate(raw_tb.rows, start=1):
            if not row.account_code or not row.account_code.strip():
                errors.append(ValidationError(
                    error_code="BLANK_ACCOUNT_CODE",
                    message=f"Row {idx} contains an empty account code.",
                    row_index=idx
                ))
                continue

            acc_code = row.account_code.strip()

            if len(acc_code) > 100:
                errors.append(ValidationError(
                    error_code="ACCOUNT_CODE_TOO_LONG",
                    message=f"Row {idx} account code exceeds maximum allowable length of 100 characters.",
                    row_index=idx,
                    account_code=acc_code[:20] + "..."
                ))
            if any(ord(c) < 32 for c in acc_code):
                errors.append(ValidationError(
                    error_code="ILLEGAL_ACCOUNT_CODE_CHARS",
                    message=f"Row {idx} account code contains illegal control characters.",
                    row_index=idx,
                    account_code=acc_code
                ))

            # Duplicate account check
            if acc_code in seen_accounts:
                errors.append(ValidationError(
                    error_code="DUPLICATE_ACCOUNT",
                    message=f"Duplicate account code '{acc_code}' found at row {idx}.",
                    severity=dup_severity,
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

            # Numeric validation & non-negativity check
            if row.debit is not None or row.credit is not None:
                is_two_col = True
                d_val = row.debit or 0.0
                c_val = row.credit or 0.0

                if math.isnan(d_val) or math.isinf(d_val):
                    errors.append(ValidationError(
                        error_code="INVALID_NUMERIC_DEBIT",
                        message=f"Row {idx} (Account {acc_code}) contains non-finite debit value (NaN/Inf).",
                        row_index=idx,
                        account_code=acc_code
                    ))
                elif d_val < 0:
                    errors.append(ValidationError(
                        error_code="NEGATIVE_DEBIT",
                        message=f"Row {idx} (Account {acc_code}) contains negative debit amount ({d_val}). Double-entry debit columns must be positive.",
                        row_index=idx,
                        account_code=acc_code
                    ))
                else:
                    tot_debit += d_val

                if math.isnan(c_val) or math.isinf(c_val):
                    errors.append(ValidationError(
                        error_code="INVALID_NUMERIC_CREDIT",
                        message=f"Row {idx} (Account {acc_code}) contains non-finite credit value (NaN/Inf).",
                        row_index=idx,
                        account_code=acc_code
                    ))
                elif c_val < 0:
                    errors.append(ValidationError(
                        error_code="NEGATIVE_CREDIT",
                        message=f"Row {idx} (Account {acc_code}) contains negative credit amount ({c_val}). Double-entry credit columns must be positive.",
                        row_index=idx,
                        account_code=acc_code
                    ))
                else:
                    tot_credit += c_val

            if row.amount is not None:
                a_val = row.amount
                if math.isnan(a_val) or math.isinf(a_val):
                    errors.append(ValidationError(
                        error_code="INVALID_NUMERIC_AMOUNT",
                        message=f"Row {idx} (Account {acc_code}) contains non-finite signed amount (NaN/Inf).",
                        row_index=idx,
                        account_code=acc_code
                    ))
                else:
                    tot_signed += a_val

        # 5. Balance integrity check with strict decimal precision rounding
        tot_debit = round(tot_debit, 2)
        tot_credit = round(tot_credit, 2)
        tot_signed = round(tot_signed, 2)

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
