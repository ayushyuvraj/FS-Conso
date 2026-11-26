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

from fs_conso.config import config
from fs_conso.models.fx import FXRateEntry, FXRateTable
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

    FX_AS_ON_DATE_ALIASES = [
        "as on date", "as_on_date", "as of date", "as_of_date", "date", "period", "effective date", "effective_date"
    ]
    FX_FROM_CURRENCY_ALIASES = [
        "from currency", "from_currency", "from", "from_curr", "source currency", "source_currency", "currency", "curr"
    ]
    FX_TO_CURRENCY_ALIASES = [
        "to currency", "to_currency", "to", "to_curr", "target currency", "target_currency", "reporting currency", "base currency"
    ]
    FX_CLOSING_RATE_ALIASES = [
        "closing", "closing rate", "closing_rate", "spot", "spot rate", "spot_rate", "bs rate", "ending rate"
    ]
    FX_AVERAGE_RATE_ALIASES = [
        "average", "average rate", "average_rate", "avg", "avg rate", "avg_rate", "pl rate", "p&l rate"
    ]
    FX_HISTORICAL_RATE_ALIASES = [
        "historical", "historical rate", "historical_rate", "hist", "hist rate", "equity rate"
    ]
    FX_SWAP_RATE_ALIASES = [
        "swap", "swap rate", "swap_rate", "swap rates", "forward", "forward rate", "forward_rate"
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
    def _find_currency_specific_column(
        cls,
        columns: List[str],
        aliases: List[str],
        target_currency: Optional[str] = None,
        exclude_indicators: bool = False
    ) -> Optional[str]:
        """Finds column matching alias and specifically tailored to target functional currency."""
        if not target_currency:
            return cls._find_column(columns, aliases, exclude_indicators=exclude_indicators)

        curr_clean = str(target_currency).strip().lower()
        curr_tokens = [curr_clean]
        if curr_clean == "inr":
            curr_tokens.extend(["rs", "rs.", "₹", "rupees", "rupee"])
        elif curr_clean == "usd":
            curr_tokens.extend(["$", "us$", "dollar", "dollars"])
        elif curr_clean == "eur":
            curr_tokens.extend(["€", "euro", "euros"])
        elif curr_clean == "gbp":
            curr_tokens.extend(["£", "pound", "pounds"])
        elif curr_clean == "sgd":
            curr_tokens.extend(["s$", "sgd$"])
        elif curr_clean == "aed":
            curr_tokens.extend(["dhs", "dirham", "dirhams"])

        col_lower = {str(c).strip().lower(): c for c in columns}

        # 1. Exact alias AND target currency token match
        for alias in aliases:
            for token in curr_tokens:
                for c_str, original in col_lower.items():
                    if exclude_indicators and cls._is_indicator_column(original):
                        continue
                    if alias in c_str and (token in c_str or re.search(rf"\b{re.escape(token)}\b", c_str)):
                        return original

        # 2. Look for column matching alias that does NOT contain other competing currencies
        all_competing = {"inr", "usd", "eur", "gbp", "sgd", "aed", "cad", "aud", "jpy", "cny", "$", "₹", "€", "£"} - set(curr_tokens)
        candidate = cls._find_column(columns, aliases, exclude_indicators=exclude_indicators)
        if candidate:
            cand_lower = str(candidate).lower()
            if not any(re.search(rf"\b{re.escape(comp)}\b", cand_lower) or comp in cand_lower for comp in all_competing):
                return candidate

        return candidate

    @classmethod
    def _is_summary_row(cls, code: str, desc: str) -> bool:
        code_clean = str(code).lower().strip()
        if code_clean in ("check", "chk", "diff", "difference", "total", "tally"):
            return True
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
    def _parse_complex_layout_with_gemini(
        cls,
        df: pd.DataFrame,
        entity_code: Optional[str] = None,
        entity_name: Optional[str] = None,
        entity_currency: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Uses Gemini Agentic Brain to analyze messy layouts, multi-tables, or ambiguous headers."""
        if not config.validate_api_key_strict():
            return None
        try:
            import json
            import google.genai as genai
            from google.genai import types

            client = genai.Client(api_key=config.gemini_api_key)
            preview_rows = df.head(8).fillna("").to_dict(orient="records")
            columns = [str(c) for c in df.columns]

            target_ctx = f"Entity: {entity_code or ''} ({entity_name or ''}), Functional Currency: {entity_currency or 'INR'}"
            prompt = f"""
You are an expert financial system parser analyzing a complex accounting trial balance sheet.
Target Company: {target_ctx}
Identify the functional role of the columns in this dataset.
Important: If there are multiple currency columns (e.g., amount_INR, amount_USD), select the columns that correspond to the entity's functional currency ({entity_currency or 'INR'}).

Columns ({len(columns)}): {columns[:40]}
Sample Rows:
{json.dumps(preview_rows[:5], default=str)}

Return a JSON object identifying which column name corresponds to:
- "code_col": column holding the GL account code or account number
- "desc_col": column holding the account description or name (optional)
- "debit_col": column holding debit amounts (optional)
- "credit_col": column holding credit amounts (optional)
- "amount_col": column holding signed or net amounts (optional)
- "dr_cr_col": column indicating DR or CR (optional)
- "reasoning": brief explanation of column choices

Schema:
{{
  "code_col": "string",
  "desc_col": "string or null",
  "debit_col": "string or null",
  "credit_col": "string or null",
  "amount_col": "string or null",
  "dr_cr_col": "string or null",
  "reasoning": "string"
}}
"""
            res = client.models.generate_content(
                model=config.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json")
            )
            return json.loads(res.text.strip())
        except Exception:
            return None

    @classmethod
    def _unpivot_wide_matrix(
        cls,
        df: pd.DataFrame,
        code_col: str,
        desc_col: Optional[str],
        numeric_cols: List[str],
        entity_code: str,
        period: str,
        currency: str,
        duplicate_policy: str,
        scale_multiplier: float = 1.0
    ) -> RawTrialBalance:
        """Unpivots a wide dimensional matrix (e.g., 75 department/dimension columns) into normalized rows."""
        rows: List[RawTBRow] = []
        for _, r in df.iterrows():
            c_raw = r[code_col]
            if pd.isna(c_raw) or not str(c_raw).strip():
                continue
            code = str(c_raw).strip()
            desc = str(r[desc_col]).strip() if desc_col and pd.notna(r[desc_col]) else code
            if cls._is_summary_row(code, desc):
                continue

            for dim_col in numeric_cols:
                val = cls.clean_number(r[dim_col])
                if val is not None and abs(val) > 0.0001:
                    if scale_multiplier != 1.0 and scale_multiplier > 0:
                        val = round(val * float(scale_multiplier), 2)
                    rows.append(RawTBRow(
                        account_code=code,
                        account_description=desc,
                        amount=val,
                        dimensions={"dimension": str(dim_col).strip()}
                    ))

        # If duplicate policy is aggregate, sum up by account code
        if duplicate_policy == "aggregate" and rows:
            agg_map: Dict[str, RawTBRow] = {}
            for row in rows:
                if row.account_code not in agg_map:
                    agg_map[row.account_code] = row.model_copy()
                else:
                    curr = agg_map[row.account_code]
                    curr.amount = round((curr.amount or 0.0) + (row.amount or 0.0), 2)
            rows = list(agg_map.values())

        return RawTrialBalance(
            entity_code=entity_code,
            period=period,
            currency=currency,
            rows=rows
        )

    @classmethod
    def parse_dataframe(
        cls,
        df: pd.DataFrame,
        entity_code: str,
        period: str = "31-Mar-2024",
        currency: str = "INR",
        duplicate_policy: str = "keep",
        entity_name: Optional[str] = None,
        column_overrides: Optional[Dict[str, str]] = None,
        scale_multiplier: float = 1.0
    ) -> RawTrialBalance:
        df = df.dropna(how="all").copy()
        if df.empty:
            return RawTrialBalance(entity_code=entity_code, entity_name=entity_name, period=period, currency=currency, rows=[])

        cols = [str(c).strip() for c in df.columns]

        # Multi-period date filtering
        date_candidates = ["date", "period", "as_on_date", "as_of_date", "reporting_period", "year", "fiscal_year"]
        date_col = cls._find_column(cols, date_candidates)
        if date_col and period:
            valid_dates = df[date_col].dropna().astype(str).str.strip()
            unique_dates = valid_dates.unique()
            if len(unique_dates) > 1:
                p_norm = re.sub(r"[^a-z0-9]", "", period.lower())
                mask = valid_dates.apply(lambda d: p_norm in re.sub(r"[^a-z0-9]", "", str(d).lower()) or re.sub(r"[^a-z0-9]", "", str(d).lower()) in p_norm)
                if mask.any():
                    df = df[mask].copy()

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
            # Stage 2: Agentic Brain layout inspection fallback
            ai_layout = cls._parse_complex_layout_with_gemini(
                df,
                entity_code=entity_code,
                entity_name=entity_name,
                entity_currency=currency
            )
            if ai_layout and ai_layout.get("code_col"):
                code_col = ai_layout.get("code_col")
                desc_col = ai_layout.get("desc_col")
                debit_col = ai_layout.get("debit_col")
                credit_col = ai_layout.get("credit_col")
                amount_col = ai_layout.get("amount_col")
                dr_cr_col = ai_layout.get("dr_cr_col")
            else:
                # Deterministic fallback: pick first non-empty column as code
                code_col = cols[0] if cols else None
                if not code_col:
                    raise ValueError(
                        f"Could not identify an 'Account Code' column. Columns inspected: {', '.join([str(c) for c in cols[:8]])}."
                    )

        desc_col = desc_col if 'desc_col' in locals() and desc_col else cls._find_column(cols, cls.DESCRIPTION_ALIASES)
        debit_col = debit_col if 'debit_col' in locals() and debit_col else cls._find_currency_specific_column(cols, cls.DEBIT_ALIASES, target_currency=currency, exclude_indicators=True)
        credit_col = credit_col if 'credit_col' in locals() and credit_col else cls._find_currency_specific_column(cols, cls.CREDIT_ALIASES, target_currency=currency, exclude_indicators=True)
        amount_col = amount_col if 'amount_col' in locals() and amount_col else cls._find_currency_specific_column(cols, cls.AMOUNT_ALIASES, target_currency=currency)
        dr_cr_col = dr_cr_col if 'dr_cr_col' in locals() and dr_cr_col else cls._find_column(cols, cls.DR_CR_INDICATOR_ALIASES)

        # Smart period / annual column detection if neither debit nor credit nor amount was found
        if not (debit_col and credit_col) and not amount_col:
            candidates = [c for c in cols if c not in (code_col, desc_col, dr_cr_col) and c.lower() not in ("currency", "curr")]
            exp_year_m = re.search(r"20\d{2}", period) if period else None
            exp_year = int(exp_year_m.group(0)) if exp_year_m else None
            best_cand = None
            best_score = -1
            for c in candidates:
                score = 0
                c_lower = c.lower()
                # Check fiscal year pattern e.g. FY 2024-25 (closing year is 2025)
                fy_m = re.search(r"(?:fy|fiscal|financial\s*year)?\s*(20\d{2})[-/](\d{2,4})", c_lower)
                if fy_m:
                    s_yr, e_yr = fy_m.groups()
                    c_closing_yr = int(s_yr[:2] + e_yr) if len(e_yr) == 2 else int(e_yr)
                    if exp_year and c_closing_yr == exp_year:
                        score += 40
                    else:
                        score -= 30  # Penalize columns belonging to different fiscal years
                elif exp_year and (str(exp_year) in c_lower or str(exp_year)[2:] in c_lower):
                    score += 20
                elif re.search(r"(?:fy|fiscal|yr|year|cy|py)?\s*(?:20\d\d|\d\d)", c_lower):
                    score += 5
                if any(w in c_lower for w in ["lakh", "crore", "million", "thousand", "bal", "amt", "amount"]):
                    score += 5
                # Check numeric presence
                if pd.to_numeric(df[c].dropna().astype(str).str.replace(r"[,()₹$€£\s]", "", regex=True), errors="coerce").notna().any():
                    score += 10
                if score > best_score:
                    best_score = score
                    best_cand = c
            if best_cand and best_score >= 10:
                amount_col = best_cand

        # Apply manual column overrides if provided
        if column_overrides:
            if column_overrides.get("account_code") or column_overrides.get("code_col"):
                code_col = column_overrides.get("account_code") or column_overrides.get("code_col")
            if column_overrides.get("account_description") or column_overrides.get("desc_col"):
                desc_col = column_overrides.get("account_description") or column_overrides.get("desc_col")
            if column_overrides.get("debit") or column_overrides.get("debit_col"):
                debit_col = column_overrides.get("debit") or column_overrides.get("debit_col")
            if column_overrides.get("credit") or column_overrides.get("credit_col"):
                credit_col = column_overrides.get("credit") or column_overrides.get("credit_col")
            if column_overrides.get("amount") or column_overrides.get("amount_col") or column_overrides.get("net_amount"):
                amount_col = column_overrides.get("amount") or column_overrides.get("amount_col") or column_overrides.get("net_amount")

            # If debit column is provided without credit (or debit == credit), it's a signed net amount column
            if debit_col and (not credit_col or debit_col == credit_col):
                amount_col = debit_col
                debit_col = None
                credit_col = None
            elif credit_col and not debit_col:
                amount_col = credit_col
                credit_col = None

        # General guard: If debit == credit (single net balance column passed as both), convert to amount_col
        if debit_col and credit_col and str(debit_col).strip().lower() == str(credit_col).strip().lower():
            amount_col = debit_col
            debit_col = None
            credit_col = None

        # Check for wide dimensional layout (e.g. 75 cost center/subsidiary columns)
        numeric_cols = [c for c in cols if c not in (code_col, desc_col, dr_cr_col)]
        is_wide_matrix = len(numeric_cols) > 5 and not (debit_col and credit_col)

        if is_wide_matrix:
            return cls._unpivot_wide_matrix(df, code_col, desc_col, numeric_cols, entity_code, period, currency, duplicate_policy, scale_multiplier=scale_multiplier)

        rows: List[RawTBRow] = []

        for _, row_data in df.iterrows():
            code_raw = row_data[code_col]
            if pd.isna(code_raw) or not str(code_raw).strip():
                continue
            code = str(code_raw).strip()

            desc = str(row_data[desc_col]).strip() if desc_col and pd.notna(row_data[desc_col]) else code

            if cls._is_summary_row(code, desc):
                continue

            if amount_col:
                # Single signed column: positive -> debit, negative -> credit
                amount_val = cls.clean_number(row_data[amount_col])
                if dr_cr_col and amount_val is not None:
                    indicator = str(row_data[dr_cr_col]).strip().lower()
                    if indicator in ("cr", "credit", "c", "-"):
                        amount_val = -abs(amount_val)
                    elif indicator in ("dr", "debit", "d", "+"):
                        amount_val = abs(amount_val)

                if scale_multiplier != 1.0 and scale_multiplier > 0 and amount_val is not None:
                    amount_val = round(amount_val * float(scale_multiplier), 2)

                if amount_val is not None:
                    d_val = amount_val if amount_val >= 0 else 0.0
                    c_val = abs(amount_val) if amount_val < 0 else 0.0
                    rows.append(RawTBRow(
                        account_code=code,
                        account_description=desc,
                        debit=d_val,
                        credit=c_val,
                        amount=amount_val
                    ))
                else:
                    rows.append(RawTBRow(
                        account_code=code,
                        account_description=desc,
                        debit=0.0,
                        credit=0.0,
                        amount=0.0
                    ))
            else:
                # Two-column TB
                debit_val = cls.clean_number(row_data[debit_col]) if debit_col else 0.0
                credit_val = cls.clean_number(row_data[credit_col]) if credit_col else 0.0
                if scale_multiplier != 1.0 and scale_multiplier > 0:
                    if debit_val is not None:
                        debit_val = round(debit_val * float(scale_multiplier), 2)
                    if credit_val is not None:
                        credit_val = round(credit_val * float(scale_multiplier), 2)
                amt_val = round((debit_val or 0.0) - (credit_val or 0.0), 2)
                rows.append(RawTBRow(
                    account_code=code,
                    account_description=desc,
                    debit=debit_val or 0.0,
                    credit=credit_val or 0.0,
                    amount=amt_val
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

        detected = {}
        if code_col: detected["account_code"] = code_col
        if desc_col: detected["account_description"] = desc_col
        if debit_col: detected["debit"] = debit_col
        if credit_col: detected["credit"] = credit_col
        if amount_col: detected["amount"] = amount_col

        return RawTrialBalance(
            entity_code=entity_code,
            entity_name=entity_name,
            period=period,
            currency=currency,
            rows=rows,
            detected_columns=detected,
            detection_trace=f"Mapped columns for {entity_name or entity_code} ({currency}): Code={code_col}, Desc={desc_col}, Debit={debit_col}, Credit={credit_col}, Amount={amount_col}"
        )

    @classmethod
    def parse_file(
        cls,
        file_path_or_bytes: Union[Path, str, bytes],
        filename: str,
        entity_code: str,
        period: str = "31-Mar-2024",
        currency: str = "INR",
        duplicate_policy: str = "keep",
        entity_name: Optional[str] = None,
        column_overrides: Optional[Dict[str, str]] = None,
        sheet_name: Optional[str] = None,
        scale_multiplier: float = 1.0
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
            read_kwargs = {}
            if sheet_name:
                read_kwargs["sheet_name"] = sheet_name
            if isinstance(file_path_or_bytes, bytes):
                df = pd.read_excel(io.BytesIO(file_path_or_bytes), **read_kwargs)
            else:
                df = pd.read_excel(file_path_or_bytes, **read_kwargs)
        else:
            raise ValueError(f"Unsupported file format '{filename}'. Please upload .xlsx, .xls, or .csv.")

        res = cls.parse_dataframe(
            df,
            entity_code,
            period,
            currency,
            duplicate_policy=duplicate_policy,
            entity_name=entity_name,
            column_overrides=column_overrides,
            scale_multiplier=scale_multiplier
        )
        res.source_filename = filename
        return res

    @classmethod
    def parse_fx_rates(
        cls,
        file_path_or_bytes: Union[Path, str, bytes],
        filename: str,
        sheet_name: Optional[str] = None,
        reporting_currency: str = "INR",
        as_on_date: str = "31-Mar-2024",
        column_overrides: Optional[Dict[str, str]] = None
    ) -> FXRateTable:
        """Parses an Excel or CSV file into an FXRateTable with support for 5-6 standardized columns."""
        fn_lower = filename.lower()
        if fn_lower.endswith(".csv"):
            if isinstance(file_path_or_bytes, bytes):
                df = pd.read_csv(io.BytesIO(file_path_or_bytes))
            else:
                df = pd.read_csv(file_path_or_bytes)
        elif fn_lower.endswith((".xlsx", ".xls")):
            read_kwargs = {}
            if sheet_name:
                read_kwargs["sheet_name"] = sheet_name
            if isinstance(file_path_or_bytes, bytes):
                df = pd.read_excel(io.BytesIO(file_path_or_bytes), **read_kwargs)
            else:
                df = pd.read_excel(file_path_or_bytes, **read_kwargs)
        else:
            raise ValueError(f"Unsupported FX file format '{filename}'.")

        df = df.dropna(how="all").copy()
        if df.empty:
            return FXRateTable()

        cols = [str(c).strip() for c in df.columns]

        # Preamble detection if header is not on row 0
        from_col = cls._find_column(cols, cls.FX_FROM_CURRENCY_ALIASES)
        closing_col = cls._find_column(cols, cls.FX_CLOSING_RATE_ALIASES)

        if not (from_col and closing_col):
            for r_idx in range(min(15, len(df))):
                row_vals = [str(x).strip() for x in df.iloc[r_idx].values if pd.notna(x)]
                f_c = cls._find_column(row_vals, cls.FX_FROM_CURRENCY_ALIASES)
                c_c = cls._find_column(row_vals, cls.FX_CLOSING_RATE_ALIASES)
                if f_c and c_c:
                    df.columns = [str(x).strip() for x in df.iloc[r_idx].values]
                    df = df.iloc[r_idx + 1:].copy()
                    cols = [str(c).strip() for c in df.columns]
                    break

        date_col = cls._find_column(cols, cls.FX_AS_ON_DATE_ALIASES)
        from_col = cls._find_column(cols, cls.FX_FROM_CURRENCY_ALIASES)
        to_col = cls._find_column(cols, cls.FX_TO_CURRENCY_ALIASES)
        closing_col = cls._find_column(cols, cls.FX_CLOSING_RATE_ALIASES)
        avg_col = cls._find_column(cols, cls.FX_AVERAGE_RATE_ALIASES)
        hist_col = cls._find_column(cols, cls.FX_HISTORICAL_RATE_ALIASES)
        swap_col = cls._find_column(cols, cls.FX_SWAP_RATE_ALIASES)

        # Overrides if provided
        if column_overrides:
            if column_overrides.get("date"): date_col = column_overrides["date"]
            if column_overrides.get("from_currency"): from_col = column_overrides["from_currency"]
            if column_overrides.get("to_currency"): to_col = column_overrides["to_currency"]
            if column_overrides.get("closing_rate"): closing_col = column_overrides["closing_rate"]
            if column_overrides.get("average_rate"): avg_col = column_overrides["average_rate"]
            if column_overrides.get("historical_rate"): hist_col = column_overrides["historical_rate"]
            if column_overrides.get("swap_rate"): swap_col = column_overrides["swap_rate"]

        fx_table = FXRateTable()
        for _, row_data in df.iterrows():
            from_val = str(row_data[from_col]).strip().upper() if from_col and pd.notna(row_data[from_col]) else ""
            if not from_val or from_val in ("FROM", "SOURCE", "TOTAL", "CURRENCY"):
                continue

            to_val = str(row_data[to_col]).strip().upper() if to_col and pd.notna(row_data[to_col]) else reporting_currency.upper()
            row_date = str(row_data[date_col]).strip() if date_col and pd.notna(row_data[date_col]) else as_on_date

            closing_val = cls.clean_number(row_data[closing_col]) if closing_col and pd.notna(row_data[closing_col]) else 1.0
            avg_val = cls.clean_number(row_data[avg_col]) if avg_col and pd.notna(row_data[avg_col]) else (closing_val or 1.0)
            hist_val = cls.clean_number(row_data[hist_col]) if hist_col and pd.notna(row_data[hist_col]) else (closing_val or 1.0)
            swap_val = cls.clean_number(row_data[swap_col]) if swap_col and pd.notna(row_data[swap_col]) else None

            if from_val and closing_val is not None:
                fx_table.add_rate(FXRateEntry(
                    from_currency=from_val,
                    to_currency=to_val,
                    as_on_date=row_date,
                    closing_rate=float(closing_val),
                    average_rate=float(avg_val or closing_val),
                    historical_rate=float(hist_val or closing_val),
                    swap_rate=float(swap_val) if swap_val is not None else None
                ))

        return fx_table
