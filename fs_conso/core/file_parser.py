"""Flexible Trial Balance File Parser.

Handles real-world messy client Excel and CSV files:
- Fuzzy column header resolution across ERP dialects (GL Code, Acc No, Dr, Cr, Description, Net Balance, Dr/Cr Type).
- Strict word-boundary matching (prevents false matches like 'gl' in 'conglomerate' or 'dr' in 'dr/cr').
- Multi-concept header detection (scans top 25 rows for true column headers).
- Distinguishes true blank (missing data = None) from accounting nil balance ('-', 'nil', '0' = 0.00).
- Robust number parsing: handles Indian/Western comma groupings, European decimals (1.200.000,50),
  currency codes/symbols (₹, $, €, £, SGD, USD, INR), parentheses '(1,000.00)', '$ (1,000.00)',
  trailing minus '1,000-', and CR/DR notation.
- Strips whitespace and skips summary/total rows (Grand Total, Total, Subtotal, End of report).
- Configurable duplicate handling: 'keep' or 'aggregate'.
"""

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import openpyxl
import pandas as pd

from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance


class FlexibleTBParser:
    """Parses Excel or CSV files into RawTrialBalance with enterprise fault-tolerance."""

    # Fuzzy column aliases across enterprise ERP dialects (SAP, Oracle, Tally, NetSuite, QuickBooks)
    ACCOUNT_CODE_ALIASES = [
        "account code", "account_code", "accountcode", "account", "gl code", "gl_code",
        "glcode", "gl", "acc code", "acc_code", "code", "acc_no", "acc no", "account_no",
        "account no", "account no.", "account number", "gl account", "gl number",
        "nominal code", "ledger code", "account #", "acct #", "acct no", "acct code",
        "account id", "gl acct", "nominal a/c", "general ledger code"
    ]
    DESCRIPTION_ALIASES = [
        "account description", "account_description", "accountdescription",
        "description", "gl description", "gl_description", "desc", "account name",
        "account_name", "accountname", "name", "particulars", "line item", "ledger name",
        "title", "account title", "details", "line description", "account details"
    ]
    DEBIT_ALIASES = [
        "debit", "debits", "dr", "dr amount", "debit amount", "debit balance", "dr.",
        "actual debit", "debit (inr)", "debit ($)", "closing dr", "opening dr",
        "debit lc", "amount dr", "dr_amt", "debit total", "debit amt", "debit_balance"
    ]
    CREDIT_ALIASES = [
        "credit", "credits", "cr", "cr amount", "credit amount", "credit balance", "cr.",
        "actual credit", "credit (inr)", "credit ($)", "closing cr", "opening cr",
        "credit lc", "amount cr", "cr_amt", "credit total", "credit amt", "credit_balance"
    ]
    AMOUNT_ALIASES = [
        "amount", "signed amount", "balance", "net balance", "net amount", "closing balance",
        "net", "closing", "amount in inr", "total amount", "bal", "amt", "ending balance",
        "ytd balance", "closing bal", "net bal", "current balance"
    ]
    DR_CR_INDICATOR_ALIASES = [
        "dr/cr", "d/c", "dr / cr", "d / c", "indicator", "type", "dc", "dr_cr",
        "sign", "balance type", "debit/credit"
    ]

    SUMMARY_ROW_KEYWORDS = [
        "total", "grand total", "total debit", "total credit", "subtotal", "sub-total",
        "balance check", "difference", "net total", "end of report", "tally total", "report total"
    ]

    NIL_BALANCE_INDICATORS = {
        "-", "—", "–", "--", "( - )", "(-)", "nil", "null (nil)", "zero", "0", "0.0", "0.00", "0.000"
    }

    CURRENCY_TOKENS = {
        "₹", "$", "€", "£", "¥", "sgd", "usd", "inr", "eur", "gbp", "rs", "rs."
    }

    @classmethod
    def clean_number(cls, val: Any) -> Optional[float]:
        """Cleans dirty financial numbers across global formats.

        - Preserves None for blank cells (distinguishing missing data from zero).
        - Converts dashes ('-', '--', '—') and explicit zero text ('nil', '0.00') to 0.0.
        - Handles currency symbols (₹, $, €, £, ¥, SGD, INR, USD, EUR, GBP, Rs, Rs.).
        - Handles accounting parentheses: '(1,200.50)' or '$ (1,200.50)' -> -1200.50.
        - Handles trailing minus / CR indicators: '1,200.00-' or '1,200.00 CR' -> -1200.00.
        - Handles Indian numbering (12,34,567.89) and European decimal commas (1.200,50).
        """
        if val is None or pd.isna(val):
            return None
        if isinstance(val, (int, float)):
            return float(val)

        # Replace non-breaking and Unicode whitespace
        s = str(val).replace("\u00a0", " ").strip()
        if not s or s.lower() in ("nan", "none", "null", "n/a", "na", "#n/a", "#value!", "#ref!"):
            return None

        # Accounting nil / zero check
        if s in cls.NIL_BALANCE_INDICATORS or s.lower() in cls.NIL_BALANCE_INDICATORS:
            return 0.0

        # Strip outer currency symbols and words before negative check
        # This handles '$ (1,200.50)' by stripping '$' first -> '(1,200.50)'
        for token in cls.CURRENCY_TOKENS:
            pattern = re.compile(rf"\b{re.escape(token)}\b|[₹$€£¥]", re.IGNORECASE)
            s = pattern.sub("", s).strip()

        is_negative = False
        s_lower = s.lower()

        # Check for negative notations
        if s.startswith("(") and s.endswith(")"):
            is_negative = True
            s = s[1:-1].strip()
        elif s.endswith("-"):
            is_negative = True
            s = s[:-1].strip()
        elif s.startswith("-"):
            is_negative = True
            s = s[1:].strip()
        elif s_lower.endswith("cr") or s_lower.endswith("cr."):
            is_negative = True
            s = s[: -2 if s_lower.endswith("cr") else -3].strip()
        elif s_lower.endswith("dr") or s_lower.endswith("dr."):
            is_negative = False
            s = s[: -2 if s_lower.endswith("dr") else -3].strip()

        # In case currency was inside parentheses: '($1,200.50)'
        for token in cls.CURRENCY_TOKENS:
            pattern = re.compile(rf"\b{re.escape(token)}\b|[₹$€£¥]", re.IGNORECASE)
            s = pattern.sub("", s).strip()

        if not s:
            return 0.0 if is_negative else None

        # European decimal notation (1.200.000,50) vs Standard (1,200,000.50 or Indian 12,34,567.89)
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # European: 1.200.000,50 -> 1200000.50
                s = s.replace(".", "").replace(",", ".")
            else:
                # Standard / Indian: 1,200,000.50 or 12,34,567.89
                s = s.replace(",", "")
        elif "," in s and "." not in s:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) in (1, 2):
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")

        # Strip remaining internal whitespace, quotes
        s = re.sub(r"[\",\s]", "", s)

        try:
            num = float(s)
            return -abs(num) if is_negative else num
        except ValueError:
            return None

    @classmethod
    def _is_indicator_column(cls, col_name: str) -> bool:
        col_clean = re.sub(r"[\s_\.\-#/]+", "", str(col_name).strip().lower())
        for ind_alias in cls.DR_CR_INDICATOR_ALIASES:
            ind_clean = re.sub(r"[\s_\.\-#/]+", "", ind_alias.lower())
            if col_clean == ind_clean:
                return True
        return False

    @classmethod
    def _find_column(cls, columns: List[str], aliases: List[str], exclude_indicators: bool = False) -> Optional[str]:
        col_lower = {str(c).strip().lower(): c for c in columns}

        # 1. Exact match
        for alias in aliases:
            if alias in col_lower:
                matched_col = col_lower[alias]
                if exclude_indicators and cls._is_indicator_column(matched_col):
                    continue
                return matched_col

        # 2. Normalized punctuation match (gl_code -> gl code)
        norm_map = {re.sub(r"[\s_\.\-#]+", " ", str(c).strip().lower()): c for c in columns}
        for alias in aliases:
            alias_norm = re.sub(r"[\s_\.\-#]+", " ", alias.lower())
            if alias_norm in norm_map:
                matched_col = norm_map[alias_norm]
                if exclude_indicators and cls._is_indicator_column(matched_col):
                    continue
                return matched_col

        # 3. Word-boundary regex match (strictly prevents 'gl' matching 'conglomerate' or 'dr' matching 'dr/cr')
        for alias in aliases:
            pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
            for c_str, original in col_lower.items():
                if exclude_indicators and cls._is_indicator_column(original):
                    continue
                if pattern.search(c_str):
                    return original

        return None

    @classmethod
    def _is_summary_row(cls, code: str, desc: str) -> bool:
        combined = f"{code} {desc}".lower().strip()
        if any(kw in combined for kw in cls.SUMMARY_ROW_KEYWORDS):
            return True
        if code.startswith("***") or code.startswith("[") or "end of report" in combined:
            return True
        return False

    @classmethod
    def detect_header_row_from_lines(cls, lines: List[str], delimiter: str = ",") -> Tuple[int, Dict[str, str]]:
        """Scans CSV lines using csv.reader to detect true column header row without parser errors."""
        best_row_idx = 0
        best_score = -1
        best_mapping: Dict[str, str] = {}

        max_scan = min(25, len(lines))
        for r_idx in range(max_scan):
            line = lines[r_idx].strip()
            if not line:
                continue
            try:
                row_vals = [val.strip() for val in next(csv.reader([line], delimiter=delimiter)) if val.strip()]
            except Exception:
                row_vals = [v.strip() for v in line.split(delimiter) if v.strip()]

            if not row_vals:
                continue

            score = 0
            mapping: Dict[str, str] = {}

            code_col = cls._find_column(row_vals, cls.ACCOUNT_CODE_ALIASES)
            if code_col:
                score += 10
                mapping["account_code"] = code_col

            desc_col = cls._find_column(row_vals, cls.DESCRIPTION_ALIASES)
            if desc_col:
                score += 3
                mapping["account_description"] = desc_col

            debit_col = cls._find_column(row_vals, cls.DEBIT_ALIASES, exclude_indicators=True)
            if debit_col:
                score += 5
                mapping["debit"] = debit_col

            credit_col = cls._find_column(row_vals, cls.CREDIT_ALIASES, exclude_indicators=True)
            if credit_col:
                score += 5
                mapping["credit"] = credit_col

            amount_col = cls._find_column(row_vals, cls.AMOUNT_ALIASES)
            if amount_col:
                score += 4
                mapping["amount"] = amount_col

            ind_col = cls._find_column(row_vals, cls.DR_CR_INDICATOR_ALIASES)
            if ind_col:
                score += 2
                mapping["indicator"] = ind_col

            # Require code_col AND at least one monetary column or description
            if code_col and (debit_col or credit_col or amount_col or desc_col):
                score += 10

            if score > best_score:
                best_score = score
                best_row_idx = r_idx
                best_mapping = mapping

        if best_score >= 15:
            return best_row_idx, best_mapping
        return 0, {}

    @classmethod
    def detect_header_row_df(cls, df: pd.DataFrame) -> Tuple[int, Dict[str, str]]:
        """Scans DataFrame rows to detect genuine header row."""
        best_row_idx = 0
        best_score = -1
        best_mapping: Dict[str, str] = {}

        max_scan = min(25, len(df))
        for r_idx in range(max_scan):
            row_vals = [str(x).strip() for x in df.iloc[r_idx].values if pd.notna(x) and str(x).strip()]
            if not row_vals:
                continue

            score = 0
            mapping: Dict[str, str] = {}

            code_col = cls._find_column(row_vals, cls.ACCOUNT_CODE_ALIASES)
            if code_col:
                score += 10
                mapping["account_code"] = code_col

            desc_col = cls._find_column(row_vals, cls.DESCRIPTION_ALIASES)
            if desc_col:
                score += 3
                mapping["account_description"] = desc_col

            debit_col = cls._find_column(row_vals, cls.DEBIT_ALIASES, exclude_indicators=True)
            if debit_col:
                score += 5
                mapping["debit"] = debit_col

            credit_col = cls._find_column(row_vals, cls.CREDIT_ALIASES, exclude_indicators=True)
            if credit_col:
                score += 5
                mapping["credit"] = credit_col

            amount_col = cls._find_column(row_vals, cls.AMOUNT_ALIASES)
            if amount_col:
                score += 4
                mapping["amount"] = amount_col

            ind_col = cls._find_column(row_vals, cls.DR_CR_INDICATOR_ALIASES)
            if ind_col:
                score += 2
                mapping["indicator"] = ind_col

            if code_col and (debit_col or credit_col or amount_col or desc_col):
                score += 10

            if score > best_score:
                best_score = score
                best_row_idx = r_idx
                best_mapping = mapping

        if best_score >= 15:
            return best_row_idx, best_mapping
        return 0, {}

    @classmethod
    def parse_dataframe(
        cls,
        df: pd.DataFrame,
        entity_code: str,
        period: str = "31-Mar-2024",
        currency: str = "INR",
        duplicate_policy: str = "keep"
    ) -> RawTrialBalance:
        df = df.dropna(how="all").copy()
        if df.empty:
            return RawTrialBalance(entity_code=entity_code, period=period, currency=currency, rows=[])

        cols = [str(c).strip() for c in df.columns]
        code_col = cls._find_column(cols, cls.ACCOUNT_CODE_ALIASES)

        # Check if header is offset in the data rows (preamble detection)
        if not code_col or not any(cls._find_column(cols, a) for a in (cls.DEBIT_ALIASES, cls.AMOUNT_ALIASES, cls.DESCRIPTION_ALIASES)):
            header_idx, _ = cls.detect_header_row_df(df)
            if header_idx is not None and header_idx < len(df):
                new_cols = [str(x).strip() for x in df.iloc[header_idx].values]
                df = df.iloc[header_idx + 1:].copy()
                df.columns = new_cols
                cols = [str(c).strip() for c in df.columns]
                code_col = cls._find_column(cols, cls.ACCOUNT_CODE_ALIASES)

        if not code_col:
            raise ValueError(
                f"Could not identify an 'Account Code' column. Columns inspected: {', '.join([str(c) for c in cols[:8]])}."
            )

        desc_col = cls._find_column(cols, cls.DESCRIPTION_ALIASES)
        debit_col = cls._find_column(cols, cls.DEBIT_ALIASES, exclude_indicators=True)
        credit_col = cls._find_column(cols, cls.CREDIT_ALIASES, exclude_indicators=True)
        amount_col = cls._find_column(cols, cls.AMOUNT_ALIASES)
        dr_cr_col = cls._find_column(cols, cls.DR_CR_INDICATOR_ALIASES)

        rows: List[RawTBRow] = []

        for _, row_data in df.iterrows():
            code_raw = row_data[code_col]
            if pd.isna(code_raw) or not str(code_raw).strip():
                continue
            code = str(code_raw).strip()

            desc = str(row_data[desc_col]).strip() if desc_col and pd.notna(row_data[desc_col]) else code

            if cls._is_summary_row(code, desc):
                continue

            debit_val = cls.clean_number(row_data[debit_col]) if debit_col else None
            credit_val = cls.clean_number(row_data[credit_col]) if credit_col else None
            amount_val = cls.clean_number(row_data[amount_col]) if amount_col else None

            # Handle Dr/Cr indicator column if present
            if dr_cr_col and amount_val is not None:
                indicator = str(row_data[dr_cr_col]).strip().lower()
                if indicator in ("cr", "credit", "c", "-"):
                    amount_val = -abs(amount_val)
                elif indicator in ("dr", "debit", "d", "+"):
                    amount_val = abs(amount_val)

            # Check if this is a two-column or single-column TB
            if debit_col or credit_col:
                rows.append(RawTBRow(
                    account_code=code,
                    account_description=desc,
                    debit=debit_val,
                    credit=credit_val
                ))
            else:
                rows.append(RawTBRow(
                    account_code=code,
                    account_description=desc,
                    amount=amount_val
                ))

        # Handle duplicate policy: "aggregate"
        if duplicate_policy == "aggregate" and rows:
            agg_map: Dict[str, RawTBRow] = {}
            for r in rows:
                c = r.account_code
                if c not in agg_map:
                    agg_map[c] = r.model_copy()
                else:
                    curr = agg_map[c]
                    if r.debit is not None or curr.debit is not None:
                        curr.debit = round((curr.debit or 0.0) + (r.debit or 0.0), 2)
                    if r.credit is not None or curr.credit is not None:
                        curr.credit = round((curr.credit or 0.0) + (r.credit or 0.0), 2)
                    if r.amount is not None or curr.amount is not None:
                        curr.amount = round((curr.amount or 0.0) + (r.amount or 0.0), 2)
            rows = list(agg_map.values())

        return RawTrialBalance(
            entity_code=entity_code,
            period=period,
            currency=currency,
            rows=rows
        )

    @classmethod
    def parse_file(
        cls,
        file_path_or_bytes: Union[Path, str, bytes],
        filename: str,
        entity_code: str,
        period: str = "31-Mar-2024",
        currency: str = "INR",
        duplicate_policy: str = "keep"
    ) -> RawTrialBalance:
        fn_lower = filename.lower()
        if fn_lower.endswith(".csv"):
            raw_text = ""
            if isinstance(file_path_or_bytes, bytes):
                try:
                    raw_text = file_path_or_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    try:
                        raw_text = file_path_or_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        raw_text = file_path_or_bytes.decode("latin1", errors="replace")
            elif isinstance(file_path_or_bytes, Path):
                raw_text = file_path_or_bytes.read_text(encoding="utf-8-sig", errors="replace")
            else:
                raw_text = str(file_path_or_bytes)

            raw_lines = [line for line in raw_text.splitlines() if line.strip()]

            # Sniff delimiter
            sample = "\n".join(raw_lines[:15])
            delimiter = ","
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample, delimiters=[",", ";", "\t", "|"])
                delimiter = dialect.delimiter
            except Exception:
                counts = {",": sample.count(","), ";": sample.count(";"), "\t": sample.count("\t"), "|": sample.count("|")}
                delimiter = max(counts, key=counts.get) if max(counts.values()) > 0 else ","

            # Detect true header line in lines 0 to 25
            header_line_idx, _ = cls.detect_header_row_from_lines(raw_lines, delimiter=delimiter)

            cleaned_csv = "\n".join(raw_lines[header_line_idx:])
            df = pd.read_csv(io.StringIO(cleaned_csv), sep=delimiter, skipinitialspace=True, on_bad_lines="skip")
        elif fn_lower.endswith((".xlsx", ".xls")):
            if isinstance(file_path_or_bytes, bytes):
                df = pd.read_excel(io.BytesIO(file_path_or_bytes))
            else:
                df = pd.read_excel(file_path_or_bytes)
        else:
            raise ValueError(f"Unsupported file format '{filename}'. Please upload .xlsx, .xls, or .csv.")

        return cls.parse_dataframe(df, entity_code, period, currency, duplicate_policy=duplicate_policy)
