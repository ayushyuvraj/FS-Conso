"""Agentic Batch Document Classifier & Metadata Extractor.

Accepts 10-15+ arbitrary Excel/CSV files or single multi-sheet workbooks in a batch and classifies each:
- CURRENT_TB: Trial balance for the active period
- PRIOR_TB: Prior period trial balance for roll-forward consistency validation
- INTERCOMPANY_SCHEDULE: Intercompany transaction / counterparty breakdown
- FX_RATES: Date-effective exchange rate table
- COA_MASTER: Group Chart of Accounts structure
- ENTITY_STRUCTURE: Entity hierarchy and ownership table

Uses configurable dual-engine execution:
1. Deterministic Heuristics (pattern matching against sheet names, file names, headers, top sample rows)
2. Agentic Brain (Gemini Flash) layout inspection (headers, sheet names, top sample rows)
3. Configurable flags: use_deterministic, use_ai, and dynamic confidence_threshold.
"""

import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import openpyxl
import pandas as pd
from pydantic import BaseModel, Field

from fs_conso.config import config
from fs_conso.core.file_parser import FlexibleTBParser


class ClassifiedFile(BaseModel):
    """Classification and metadata for an ingested file or workbook sheet."""
    filename: str
    sheet_name: Optional[str] = None
    file_type: str = Field(..., description="CURRENT_TB, PRIOR_TB, INTERCOMPANY_SCHEDULE, FX_RATES, COA_MASTER, ENTITY_STRUCTURE, UNKNOWN")
    entity_code: Optional[str] = None
    entity_name: Optional[str] = None
    period: Optional[str] = None
    currency: Optional[str] = None
    confidence: float = 1.0
    classification_method: str = "DETERMINISTIC"  # DETERMINISTIC, GEMINI_AI, USER_OVERRIDE, FALLBACK
    reasoning: str = ""
    needs_review: bool = False
    sheet_names: List[str] = Field(default_factory=list)
    detected_columns: Dict[str, str] = Field(default_factory=dict)
    sample_rows: List[List[str]] = Field(default_factory=list)
    date_status: str = "MATCH"  # MATCH, MISMATCH, MULTI_PERIOD
    detected_period: Optional[str] = None
    is_extra_unassigned: bool = False
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    denomination: str = "UNITS"  # UNITS, LAKHS, CRORES, MILLIONS, THOUSANDS, HUNDREDS
    scale_multiplier: float = 1.0
    scale_instruction: str = "Reported in exact absolute currency (multiplier 1.0)"
    raw_data: Optional[bytes] = Field(default=None, repr=False)


class FileClassifier:
    """Classifies batch uploaded files and multi-sheet workbooks into consolidation perimeter roles."""

    @staticmethod
    def _inspect_file_preview(file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extracts sheet names, header candidates, and sample rows from an Excel or CSV file."""
        preview: Dict[str, Any] = {
            "filename": filename,
            "sheets": [],
            "sample_rows": []
        }
        fname_lower = filename.lower()
        if fname_lower.endswith(".csv"):
            preview["sheets"] = ["Sheet1"]
            try:
                content = file_bytes.decode("utf-8", errors="replace")
                lines = [line.strip() for line in content.splitlines() if line.strip()][:10]
                preview["sample_rows"] = [line.split(",")[:10] for line in lines]
            except Exception:
                pass
            return preview

        # Excel
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            preview["sheets"] = list(wb.sheetnames)
            first_sheet = wb.active or wb[wb.sheetnames[0]]
            rows = []
            for r in first_sheet.iter_rows(values_only=True):
                if any(c is not None for c in r):
                    clean_row = [str(c).strip() if c is not None else "" for c in r][:15]
                    rows.append(clean_row)
                    if len(rows) >= 10:
                        break
            preview["sample_rows"] = rows
            wb.close()
        except Exception:
            pass

        return preview

    @staticmethod
    def _inspect_sheet_preview(wb: openpyxl.Workbook, sheet_name: str) -> List[List[str]]:
        """Extracts sample rows from a specific sheet in an open workbook."""
        rows = []
        try:
            ws = wb[sheet_name]
            for r in ws.iter_rows(values_only=True):
                if any(c is not None for c in r):
                    clean_row = [str(c).strip() if c is not None else "" for c in r][:15]
                    rows.append(clean_row)
                    if len(rows) >= 10:
                        break
        except Exception:
            pass
        return rows

    @classmethod
    def _detect_columns_from_sample(cls, sample_rows: List[List[str]], is_fx: bool = False) -> Dict[str, str]:
        """Detects column mappings from top sample rows using FlexibleTBParser aliases."""
        if not sample_rows:
            return {}

        best_mapping: Dict[str, str] = {}
        max_scan = min(5, len(sample_rows))

        for r_idx in range(max_scan):
            row_vals = [c.strip() for c in sample_rows[r_idx] if c and c.strip()]
            if not row_vals:
                continue

            if is_fx:
                mapping = {}
                f_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_FROM_CURRENCY_ALIASES)
                t_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_TO_CURRENCY_ALIASES)
                c_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_CLOSING_RATE_ALIASES)
                a_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_AVERAGE_RATE_ALIASES)
                h_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_HISTORICAL_RATE_ALIASES)
                s_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_SWAP_RATE_ALIASES)
                d_c = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.FX_AS_ON_DATE_ALIASES)
                if f_c: mapping["from_currency"] = f_c
                if t_c: mapping["to_currency"] = t_c
                if c_c: mapping["closing_rate"] = c_c
                if a_c: mapping["average_rate"] = a_c
                if h_c: mapping["historical_rate"] = h_c
                if s_c: mapping["swap_rate"] = s_c
                if d_c: mapping["date"] = d_c
                if len(mapping) >= 2:
                    return mapping
            else:
                mapping = {}
                code_col = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.ACCOUNT_CODE_ALIASES)
                desc_col = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.DESCRIPTION_ALIASES)
                debit_col = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.DEBIT_ALIASES, exclude_indicators=True)
                credit_col = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.CREDIT_ALIASES, exclude_indicators=True)
                amount_col = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.AMOUNT_ALIASES)
                ind_col = FlexibleTBParser._find_column(row_vals, FlexibleTBParser.DR_CR_INDICATOR_ALIASES)

                if code_col: mapping["account_code"] = code_col
                if desc_col: mapping["account_description"] = desc_col
                if debit_col: mapping["debit"] = debit_col
                if credit_col: mapping["credit"] = credit_col
                if amount_col: mapping["amount"] = amount_col
                if ind_col: mapping["indicator"] = ind_col

                if code_col and (debit_col or credit_col or amount_col or desc_col):
                    return mapping
                if len(mapping) > len(best_mapping):
                    best_mapping = mapping

        return best_mapping

    @classmethod
    def _evaluate_date_discrepancy(
        cls,
        text_corpus: str,
        expected_period: Optional[str]
    ) -> Tuple[str, Optional[str]]:
        """Evaluates whether detected dates match the expected run date or indicate discrepancy / multi-period."""
        if not expected_period:
            return "MATCH", None

        p_norm = re.sub(r"[^a-z0-9]", "", expected_period.lower())
        exp_year = re.search(r"20\d{2}", expected_period)
        exp_year_str = exp_year.group(0) if exp_year else ""

        # Find years in corpus (handle underscores, hyphens, and whitespace)
        years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", text_corpus))
        dates = re.findall(r"(\d{1,2}[-_/][a-zA-Z]{3,}[-_/]\d{2,4})", text_corpus)

        if len(years) > 1:
            return "MULTI_PERIOD", expected_period

        if years:
            found_year = next(iter(years))
            if exp_year_str and found_year != exp_year_str:
                detected_date = dates[0] if dates else found_year
                return "MISMATCH", detected_date

        return "MATCH", expected_period

    @classmethod
    def _detect_denomination(
        cls,
        sample_rows: Optional[List[List[str]]] = None,
        sheet_name: Optional[str] = None,
        filename: Optional[str] = None
    ) -> Tuple[str, float, str]:
        """Detects whether financial amounts are reported in Lakhs, Crores, Millions, Thousands, Hundreds, or Units."""
        text_corpus = f"{filename or ''} {sheet_name or ''} "
        if sample_rows:
            for r in sample_rows[:10]:
                text_corpus += " ".join(str(c) for c in r if c) + " "

        norm = text_corpus.lower()

        # 1. Crores (10^7 = 10,000,000)
        if re.search(r"\b(?:in\s+)?(?:rs\.?|inr|₹)?\s*(?:cr(?:ore)?s?)\b|\b(?:in\s+crores?)\b|\bcrores?\b", norm):
            return "CRORES", 10000000.0, "Reported in ₹ Crores — multiplied by 10,000,000 to normalize to absolute currency"

        # 2. Lakhs (10^5 = 100,000)
        if re.search(r"\b(?:in\s+)?(?:rs\.?|inr|₹)?\s*(?:lakh?s?|lacs?)\b|\b(?:in\s+lakh?s?)\b|\blakh?s?\b|\blacs?\b", norm):
            return "LAKHS", 100000.0, "Reported in ₹ Lakhs — multiplied by 100,000 to normalize to absolute currency"

        # 3. Millions (10^6 = 1,000,000)
        if re.search(r"\b(?:in\s+)?(?:usd|\$|eur|€|inr|₹)?\s*(?:millions?|mn)\b|\b(?:in\s+millions?)\b|\bmillions?\b", norm):
            return "MILLIONS", 1000000.0, "Reported in Millions — multiplied by 1,000,000 to normalize to absolute currency"

        # 4. Thousands (10^3 = 1,000)
        if re.search(r"\b(?:in\s+)?(?:usd|\$|eur|€|inr|₹)?\s*(?:thousands?|'000|000s?)\b|\b(?:in\s+'000)\b|\bthousands?\b", norm):
            return "THOUSANDS", 1000.0, "Reported in Thousands — multiplied by 1,000 to normalize to absolute currency"

        # 5. Hundreds (10^2 = 100)
        if re.search(r"\b(?:in\s+)?(?:hundreds?|'00)\b|\bhundreds?\b", norm):
            return "HUNDREDS", 100.0, "Reported in Hundreds — multiplied by 100 to normalize to absolute currency"

        # Default: Units / Absolute (1.0)
        return "UNITS", 1.0, "Reported in exact absolute currency (multiplier 1.0)"

    @classmethod
    def _extract_roster(cls, target_entities: Any) -> List[Dict[str, Any]]:
        """Normalizes entities from EntityHierarchy, dicts, or lists into a roster."""
        roster: List[Dict[str, Any]] = []
        if not target_entities:
            return roster

        if hasattr(target_entities, "entities"):  # EntityHierarchy
            for ent in target_entities.entities.values():
                roster.append({
                    "code": getattr(ent, "entity_code", ""),
                    "name": getattr(ent, "entity_name", ""),
                    "currency": getattr(ent, "input_currency", "INR"),
                    "holding": getattr(ent, "holding_percentage", 1.0)
                })
        elif isinstance(target_entities, list):
            for item in target_entities:
                if isinstance(item, dict):
                    roster.append({
                        "code": item.get("entity_code") or item.get("code", ""),
                        "name": item.get("entity_name") or item.get("name", ""),
                        "currency": item.get("input_currency") or item.get("currency", "INR"),
                        "holding": item.get("holding_percentage", 1.0)
                    })
                elif hasattr(item, "entity_code"):
                    roster.append({
                        "code": getattr(item, "entity_code", ""),
                        "name": getattr(item, "entity_name", ""),
                        "currency": getattr(item, "input_currency", "INR"),
                        "holding": getattr(item, "holding_percentage", 1.0)
                    })
                elif isinstance(item, str):
                    roster.append({
                        "code": item,
                        "name": item,
                        "currency": "INR",
                        "holding": 1.0
                    })
        return roster

    @classmethod
    def classify_sheet_or_file(
        cls,
        file_bytes: bytes,
        filename: str,
        sheet_name: Optional[str] = None,
        sample_rows: Optional[List[List[str]]] = None,
        all_sheet_names: Optional[List[str]] = None,
        expected_period: Optional[str] = None,
        target_entities: Optional[Any] = None,
        use_deterministic: bool = True,
        use_ai: bool = True,
        confidence_threshold: Optional[float] = None
    ) -> ClassifiedFile:
        """Classifies a specific sheet or standalone file using dual-engine escalation."""
        threshold = confidence_threshold if confidence_threshold is not None else config.ai_confidence_threshold
        roster = cls._extract_roster(target_entities)

        fname_lower = filename.lower()
        sname_lower = (sheet_name or "").lower()
        sheets_list = all_sheet_names or ([sheet_name] if sheet_name else ["Sheet1"])
        rows = sample_rows or []

        flat_text = f"{fname_lower} {sname_lower} " + " ".join(" ".join(str(c) for c in r) for r in rows).lower()
        date_status, detected_date = cls._evaluate_date_discrepancy(flat_text, expected_period)
        det_denom, det_multiplier, det_instruction = cls._detect_denomination(rows, sheet_name, filename)

        # -------------------------------------------------------------
        # Tier 1: Deterministic Heuristics (if enabled)
        # -------------------------------------------------------------
        if use_deterministic:
            sname_norm = sname_lower.replace("_", " ")
            fname_norm = fname_lower.replace("_", " ")

            # 1. Chart of Accounts Master
            if any(k in sname_lower or k in sname_norm for k in ["chart of accounts", "chart_of_accounts", "account_master"]) or \
               "coa" in sname_norm.split() or \
               any(k in fname_lower or k in fname_norm for k in ["chart of accounts", "chart_of_accounts", "account_master", "group coa"]) or \
               "coa" in fname_norm.split():
                return ClassifiedFile(
                    filename=filename,
                    sheet_name=sheet_name,
                    file_type="COA_MASTER",
                    confidence=1.0,
                    classification_method="DETERMINISTIC",
                    reasoning="Identified Group Chart of Accounts via explicit sheet or file title.",
                    needs_review=False,
                    sheet_names=sheets_list,
                    sample_rows=rows[:5],
                    raw_data=file_bytes
                )

            # 2. Entity Structure / Ownership
            if any(k in sname_lower or k in sname_norm for k in ["entity structure", "entity_structure", "ownership", "ownership_structure", "hierarchy"]) or \
               any(k in fname_lower or k in fname_norm for k in ["entity structure", "entity_structure", "ownership", "ownership_structure", "hierarchy"]):
                return ClassifiedFile(
                    filename=filename,
                    sheet_name=sheet_name,
                    file_type="ENTITY_STRUCTURE",
                    confidence=1.0,
                    classification_method="DETERMINISTIC",
                    reasoning="Identified Entity Structure / Ownership matrix.",
                    needs_review=False,
                    sheet_names=sheets_list,
                    sample_rows=rows[:5],
                    raw_data=file_bytes
                )

            # 3. FX Rates Table
            is_fx_sheet = (
                any(k in sname_lower or k in sname_norm for k in ["fx_rate", "fx rate", "fxrates", "exchange rate", "exchange_rate", "forex"]) or
                any(k in fname_lower or k in fname_norm for k in ["fx_rate", "fx rate", "fxrates", "exchange rate", "exchange_rate", "forex"]) or
                "fx" in sname_norm.split()
            )
            if is_fx_sheet:
                det_cols = cls._detect_columns_from_sample(rows, is_fx=True)
                reason = f"Identified FX rate table for period {expected_period or '31-Mar-2024'}."
                needs_rev = False
                if date_status == "MISMATCH":
                    needs_rev = True
                    reason += f" [Period Mismatch: Found {detected_date} vs Run Date {expected_period}]"

                return ClassifiedFile(
                    filename=filename,
                    sheet_name=sheet_name,
                    file_type="FX_RATES",
                    period=expected_period,
                    confidence=0.98,
                    classification_method="DETERMINISTIC",
                    reasoning=reason,
                    needs_review=needs_rev,
                    sheet_names=sheets_list,
                    detected_columns=det_cols,
                    sample_rows=rows[:5],
                    date_status=date_status,
                    detected_period=detected_date,
                    raw_data=file_bytes
                )

            # 4. Intercompany Transactions / Schedules
            if any(k in fname_lower for k in ["intercompany", "ic_trans", "ic_elim", "ic_schedule", "reciprocal"]) or \
               any(k in sname_lower for k in ["ic_eliminations", "intercompany", "ic eliminations"]):
                return ClassifiedFile(
                    filename=filename,
                    sheet_name=sheet_name,
                    file_type="INTERCOMPANY_SCHEDULE",
                    confidence=0.95,
                    classification_method="DETERMINISTIC",
                    reasoning="Identified Intercompany Transactions Schedule.",
                    needs_review=False,
                    sheet_names=sheets_list,
                    sample_rows=rows[:5],
                    raw_data=file_bytes
                )

            # 5. Deterministic Trial Balance (with Entity matching)
            matched_ent = None
            matched_conf = 0.0

            # Pass 1: Exact entity code match with word boundary
            for ent in roster:
                code = ent["code"].lower().strip()
                if not code:
                    continue
                code_pattern = rf"(^|[_\-\s\(\)\.\[\]]){re.escape(code)}([_\-\s\(\)\.\[\]]|\.|$)"
                if re.search(code_pattern, sname_lower) or re.search(code_pattern, fname_lower):
                    matched_ent = ent
                    matched_conf = 0.96
                    break

            # Pass 2: Common parent / sub abbreviations (Parent or Sub 1, Sub 2, S1, S2)
            if not matched_ent:
                m_sub = re.search(r"(?:subsidiary|sub|s)[_\s-]?(\d+)", sname_lower) or re.search(r"(?:subsidiary|sub|s)[_\s-]?(\d+)", fname_lower)
                if m_sub:
                    sub_num = m_sub.group(1)
                    for ent in roster:
                        ent_c = ent["code"].lower()
                        if ent_c.endswith(sub_num) or f"s{sub_num}" in ent_c or f"sub{sub_num}" in ent_c or sub_num in ent["name"].lower():
                            matched_ent = ent
                            matched_conf = 0.94
                            break

                if not matched_ent:
                    for ent in roster:
                        if ent.get("holding", 1.0) == 1.0 and ("parent" in sname_lower or "parent" in fname_lower or "_p_" in fname_lower or fname_lower.endswith("_p")):
                            matched_ent = ent
                            matched_conf = 0.92
                            break

            # Pass 3: Exact or distinctive slug entity name match
            GENERIC_TOKENS = {"subsidiary", "sub", "company", "corp", "corporation", "inc", "ltd", "limited", "pvt", "private", "llc", "group"}
            if not matched_ent:
                for ent in roster:
                    name_clean = re.sub(r"[^a-z0-9]", "", ent["name"].lower())
                    sname_clean = re.sub(r"[^a-z0-9]", "", sname_lower)
                    fname_clean = re.sub(r"[^a-z0-9]", "", fname_lower)
                    if len(name_clean) >= 3 and (name_clean in sname_clean or name_clean in fname_clean):
                        matched_ent = ent
                        matched_conf = 0.93
                        break
                    distinct_tokens = [t for t in re.split(r"[_\-\s]+", ent["name"].lower()) if len(t) > 2 and t not in GENERIC_TOKENS]
                    if distinct_tokens and (all(t in sname_lower for t in distinct_tokens) or all(t in fname_lower for t in distinct_tokens)):
                        matched_ent = ent
                        matched_conf = 0.90
                        break

            is_prior = "prior" in sname_lower or "prior" in fname_lower or "opening" in sname_lower or "py" in fname_lower
            ftype = "PRIOR_TB" if is_prior else "CURRENT_TB"

            if matched_ent and matched_conf >= threshold:
                det_cols = cls._detect_columns_from_sample(rows, is_fx=False)
                reason = f"Deterministically matched legal entity '{matched_ent['name']}' ({matched_ent['code']})."
                needs_rev = False
                if date_status == "MISMATCH":
                    needs_rev = True
                    reason += f" [Period Mismatch: Found {detected_date} vs Run Date {expected_period}]"

                return ClassifiedFile(
                    filename=filename,
                    sheet_name=sheet_name,
                    file_type=ftype,
                    entity_code=matched_ent["code"],
                    entity_name=matched_ent["name"],
                    period=expected_period,
                    currency=matched_ent["currency"],
                    confidence=matched_conf,
                    classification_method="DETERMINISTIC",
                    reasoning=reason,
                    needs_review=needs_rev,
                    sheet_names=sheets_list,
                    detected_columns=det_cols,
                    sample_rows=rows[:5],
                    date_status=date_status,
                    detected_period=detected_date,
                    candidates=roster,
                    denomination=det_denom,
                    scale_multiplier=det_multiplier,
                    scale_instruction=det_instruction,
                    raw_data=file_bytes
                )

        # -------------------------------------------------------------
        # Tier 2: Agentic Brain (Gemini Flash) - if AI enabled
        # -------------------------------------------------------------
        if use_ai and config.validate_api_key_strict():
            ai_cf = cls._classify_with_gemini(
                preview={
                    "filename": filename,
                    "sheet_name": sheet_name,
                    "sheets": sheets_list,
                    "sample_rows": rows[:6]
                },
                roster=roster,
                expected_period=expected_period,
                threshold=threshold
            )
            if ai_cf:
                ai_cf.raw_data = file_bytes
                ai_cf.candidates = roster
                ai_cf.sample_rows = rows[:5]
                ai_cf.date_status = date_status
                ai_cf.detected_period = detected_date
                if not ai_cf.detected_columns:
                    ai_cf.detected_columns = cls._detect_columns_from_sample(rows, is_fx=(ai_cf.file_type == "FX_RATES"))
                if date_status == "MISMATCH":
                    ai_cf.needs_review = True
                    ai_cf.reasoning += f" [Period Mismatch: Found {detected_date} vs Run Date {expected_period}]"
                return ai_cf

        # -------------------------------------------------------------
        # Tier 3: Human-in-the-Loop Fallback
        # -------------------------------------------------------------
        best_code = matched_ent["code"] if (use_deterministic and 'matched_ent' in locals() and matched_ent) else None
        best_name = matched_ent["name"] if (use_deterministic and 'matched_ent' in locals() and matched_ent) else None
        best_curr = matched_ent["currency"] if (use_deterministic and 'matched_ent' in locals() and matched_ent) else "INR"
        best_conf = matched_conf if (use_deterministic and 'matched_conf' in locals() and matched_conf) else 0.50

        # Check if sheet is unassigned extra
        is_extra = best_code is None and not any(k in sname_lower for k in ["fx", "rate", "currency", "tb", "ledger", "trial", "balance", "gl"])
        det_cols = cls._detect_columns_from_sample(rows, is_fx=False)

        reasoning_msg = f"Confidence ({best_conf:.2f}) below threshold ({threshold:.2f}). Routed to Human-in-the-Loop review."
        if not use_ai and use_deterministic:
            reasoning_msg = f"Deterministic confidence ({best_conf:.2f}) below threshold ({threshold:.2f}) with 0 AI tokens spent. Routed to Human-in-the-Loop."
        elif not use_deterministic and not use_ai:
            reasoning_msg = "Both Deterministic and AI classification bypassed. Manual review required."

        return ClassifiedFile(
            filename=filename,
            sheet_name=sheet_name,
            file_type="CURRENT_TB" if best_code else "UNKNOWN",
            entity_code=best_code,
            entity_name=best_name,
            period=expected_period,
            currency=best_curr,
            confidence=best_conf,
            classification_method="DETERMINISTIC" if best_code else "FALLBACK",
            reasoning=reasoning_msg,
            needs_review=True,
            sheet_names=sheets_list,
            detected_columns=det_cols,
            sample_rows=rows[:5],
            date_status=date_status,
            detected_period=detected_date,
            is_extra_unassigned=is_extra,
            candidates=roster,
            denomination=det_denom,
            scale_multiplier=det_multiplier,
            scale_instruction=det_instruction,
            raw_data=file_bytes
        )

    @classmethod
    def _classify_with_gemini(
        cls,
        preview: Dict[str, Any],
        roster: Optional[List[Dict[str, Any]]],
        expected_period: Optional[str],
        threshold: float = 0.85
    ) -> Optional[ClassifiedFile]:
        """Invokes Gemini Agentic Brain to analyze messy layouts and classify the document or sheet."""
        try:
            import google.genai as genai
            from google.genai import types

            client = genai.Client(api_key=config.gemini_api_key)
            prompt = f"""
You are an expert financial consolidation and ERP ingestion agent.
Analyze the following document preview and determine what kind of accounting data it contains, which legal entity it belongs to, and what reporting period it covers.

File Name: {preview['filename']}
Sheet Name: {preview.get('sheet_name', 'Default')}
All Sheets in File: {preview.get('sheets', [])}
Top Sample Rows (JSON):
{json.dumps(preview['sample_rows'][:6])}

Known In-Scope Entities in Conglomerate Perimeter:
{json.dumps(roster or [{'code': 'P', 'name': 'Parent Company', 'currency': 'INR'}], indent=2)}
Expected Reporting Period: {expected_period or '31-Mar-2024'}

Classify into exactly ONE of the following file_types:
- CURRENT_TB: Trial Balance for current consolidation period
- PRIOR_TB: Prior period trial balance / opening balance file
- INTERCOMPANY_SCHEDULE: Intercompany transactions, receivables/payables between subsidiaries
- FX_RATES: Currency exchange rates table (as on date, from currency, to currency, closing, average, historical, swap)
- COA_MASTER: Group Chart of Accounts hierarchy
- ENTITY_STRUCTURE: Entity ownership hierarchy
- UNKNOWN: Extra or unrelated sheet (notes, blank, summary)

Respond STRICTLY in JSON format matching this schema:
{{
  "file_type": "CURRENT_TB",
  "entity_code": "code of one of the in-scope entities or null if FX_RATES/UNKNOWN",
  "period": "31-Mar-2024",
  "currency": "INR",
  "confidence": 0.95,
  "denomination": "LAKHS | CRORES | MILLIONS | THOUSANDS | HUNDREDS | UNITS",
  "scale_multiplier": 100000.0,
  "scale_instruction": "Explanation of financial scale detected",
  "reasoning": "Reasoning based on file headers, currency columns, scale, and entity profile."
}}
"""
            response = client.models.generate_content(
                model=config.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )

            text = response.text.strip()
            data = json.loads(text)
            conf = float(data.get("confidence", 0.85))

            ent_code = data.get("entity_code")
            matched_ent = next((e for e in (roster or []) if e.get("code") == ent_code or e.get("name") == ent_code), None)
            ent_name = matched_ent["name"] if matched_ent else None
            ent_curr = matched_ent["currency"] if matched_ent else data.get("currency")
            if matched_ent:
                ent_code = matched_ent["code"]

            ftype = data.get("file_type", "CURRENT_TB")
            is_extra = ftype == "UNKNOWN"

            # Denomination detection with fallback
            det_denom, det_mult, det_inst = cls._detect_denomination(
                preview.get("sample_rows"),
                preview.get("sheet_name"),
                preview["filename"]
            )
            final_denom = data.get("denomination") or det_denom
            try:
                final_mult = float(data.get("scale_multiplier") or det_mult)
            except (ValueError, TypeError):
                final_mult = det_mult
            final_inst = data.get("scale_instruction") or det_inst

            return ClassifiedFile(
                filename=preview["filename"],
                sheet_name=preview.get("sheet_name"),
                file_type=ftype,
                entity_code=ent_code,
                entity_name=ent_name,
                period=data.get("period") or expected_period,
                currency=ent_curr,
                confidence=conf,
                classification_method="GEMINI_AI",
                reasoning=data.get("reasoning", "Classified via Gemini Agentic Brain layout inspection."),
                needs_review=(conf < threshold or (ent_code is None and ftype == "CURRENT_TB")),
                sheet_names=preview.get("sheets", []),
                is_extra_unassigned=is_extra,
                candidates=roster or [],
                denomination=final_denom,
                scale_multiplier=final_mult,
                scale_instruction=final_inst
            )
        except Exception:
            return None

    @classmethod
    def classify_file(
        cls,
        file_bytes: bytes,
        filename: str,
        expected_period: Optional[str] = None,
        known_entities: Optional[Any] = None,
        entity_hierarchy: Optional[Any] = None,
        use_deterministic: bool = True,
        use_ai: bool = True,
        confidence_threshold: Optional[float] = None
    ) -> ClassifiedFile:
        """Classifies a single file for backwards compatibility."""
        target_entities = known_entities if known_entities is not None else entity_hierarchy
        preview = cls._inspect_file_preview(file_bytes or b"", filename)
        first_sheet = preview["sheets"][0] if preview["sheets"] else None
        return cls.classify_sheet_or_file(
            file_bytes=file_bytes,
            filename=filename,
            sheet_name=first_sheet,
            sample_rows=preview["sample_rows"],
            all_sheet_names=preview["sheets"],
            expected_period=expected_period,
            target_entities=target_entities,
            use_deterministic=use_deterministic,
            use_ai=use_ai,
            confidence_threshold=confidence_threshold
        )

    @classmethod
    def classify_batch(
        cls,
        files: List[Tuple[str, bytes]],
        expected_period: Optional[str] = None,
        known_entities: Optional[Any] = None,
        entity_hierarchy: Optional[Any] = None,
        use_deterministic: bool = True,
        use_ai: bool = True,
        confidence_threshold: Optional[float] = None
    ) -> List[ClassifiedFile]:
        """Classifies a batch of uploaded files, inspecting each sheet of multi-sheet workbooks."""
        target_entities = known_entities if known_entities is not None else entity_hierarchy
        results: List[ClassifiedFile] = []

        for filename, file_bytes in files:
            fname_lower = filename.lower()
            if fname_lower.endswith((".xlsx", ".xls")):
                try:
                    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
                    sheet_names = list(wb.sheetnames)

                    # If multiple sheets exist, classify each sheet individually!
                    if len(sheet_names) > 1:
                        for s_name in sheet_names:
                            s_rows = cls._inspect_sheet_preview(wb, s_name)
                            cf = cls.classify_sheet_or_file(
                                file_bytes=file_bytes,
                                filename=filename,
                                sheet_name=s_name,
                                sample_rows=s_rows,
                                all_sheet_names=sheet_names,
                                expected_period=expected_period,
                                target_entities=target_entities,
                                use_deterministic=use_deterministic,
                                use_ai=use_ai,
                                confidence_threshold=confidence_threshold
                            )
                            results.append(cf)
                    else:
                        # Single sheet workbook
                        s_name = sheet_names[0] if sheet_names else "Sheet1"
                        s_rows = cls._inspect_sheet_preview(wb, s_name)
                        cf = cls.classify_sheet_or_file(
                            file_bytes=file_bytes,
                            filename=filename,
                            sheet_name=s_name,
                            sample_rows=s_rows,
                            all_sheet_names=sheet_names,
                            expected_period=expected_period,
                            target_entities=target_entities,
                            use_deterministic=use_deterministic,
                            use_ai=use_ai,
                            confidence_threshold=confidence_threshold
                        )
                        results.append(cf)
                    wb.close()
                except Exception:
                    # Fallback single file classification
                    cf = cls.classify_file(
                        file_bytes=file_bytes,
                        filename=filename,
                        expected_period=expected_period,
                        known_entities=target_entities,
                        use_deterministic=use_deterministic,
                        use_ai=use_ai,
                        confidence_threshold=confidence_threshold
                    )
                    results.append(cf)
            else:
                # CSV or text file
                cf = cls.classify_file(
                    file_bytes=file_bytes,
                    filename=filename,
                    expected_period=expected_period,
                    known_entities=target_entities,
                    use_deterministic=use_deterministic,
                    use_ai=use_ai,
                    confidence_threshold=confidence_threshold
                )
                results.append(cf)

        return results
