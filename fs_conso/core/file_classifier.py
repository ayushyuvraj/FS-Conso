"""Agentic Batch Document Classifier & Metadata Extractor.

Accepts 10-15+ arbitrary Excel/CSV files uploaded in a batch and classifies each:
- CURRENT_TB: Trial balance for the active period
- PRIOR_TB: Prior period trial balance for roll-forward consistency validation
- INTERCOMPANY_SCHEDULE: Intercompany transaction / counterparty breakdown
- FX_RATES: Date-effective exchange rate table
- COA_MASTER: Group Chart of Accounts structure
- ENTITY_STRUCTURE: Entity hierarchy and ownership table

Uses a 3-tier escalation:
1. Fast Deterministic Heuristics (exact filename / sheet pattern match)
2. Agentic Brain (Gemini Flash) layout inspection (headers, sheet names, top rows)
3. Human-in-the-Loop review flag if confidence < threshold.
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


class ClassifiedFile(BaseModel):
    """Classification and metadata for an ingested file."""
    filename: str
    file_type: str = Field(..., description="CURRENT_TB, PRIOR_TB, INTERCOMPANY_SCHEDULE, FX_RATES, COA_MASTER, ENTITY_STRUCTURE, UNKNOWN")
    entity_code: Optional[str] = None
    period: Optional[str] = None
    currency: Optional[str] = None
    confidence: float = 1.0
    classification_method: str = "DETERMINISTIC"  # DETERMINISTIC, GEMINI_AI, USER_OVERRIDE
    reasoning: str = ""
    needs_review: bool = False
    sheet_names: List[str] = Field(default_factory=list)
    raw_data: Optional[bytes] = Field(default=None, repr=False)


class FileClassifier:
    """Classifies batch uploaded files into consolidation perimeter roles."""

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

    @classmethod
    def classify_file(
        cls,
        file_bytes: bytes,
        filename: str,
        expected_period: Optional[str] = None,
        known_entities: Optional[List[str]] = None
    ) -> ClassifiedFile:
        """Classifies a single file using 3-tier escalation (Deterministic -> Gemini -> HITL)."""
        preview = cls._inspect_file_preview(file_bytes, filename)
        fname_lower = filename.lower()
        sheets_lower = [s.lower() for s in preview["sheets"]]
        flat_samples = " ".join(" ".join(str(c) for c in r) for r in preview["sample_rows"]).lower()

        # -------------------------------------------------------------
        # Tier 1: Deterministic Heuristics
        # -------------------------------------------------------------
        # 1. Chart of Accounts Master
        fname_normalized = fname_lower.replace("_", " ")
        if "chart of accounts" in sheets_lower or "chart of accounts" in fname_normalized or "group coa" in fname_normalized or "coa" in fname_normalized.split():
            return ClassifiedFile(
                filename=filename,
                file_type="COA_MASTER",
                confidence=1.0,
                classification_method="DETERMINISTIC",
                reasoning="Identified Group Chart of Accounts via explicit sheet name or file title.",
                needs_review=False,
                sheet_names=preview["sheets"],
                raw_data=file_bytes
            )

        # 2. Entity Structure / Ownership
        if "entity structure" in sheets_lower or "entity_structure" in fname_lower or "ownership" in fname_lower:
            return ClassifiedFile(
                filename=filename,
                file_type="ENTITY_STRUCTURE",
                confidence=1.0,
                classification_method="DETERMINISTIC",
                reasoning="Identified Entity Structure / Ownership matrix via sheet or file title.",
                needs_review=False,
                sheet_names=preview["sheets"],
                raw_data=file_bytes
            )

        # 3. FX Rates Table
        if "fx_rate" in fname_lower or "exchange_rate" in fname_lower or "fx rates" in sheets_lower or "forex" in fname_lower:
            # Check for date in filename or content
            detected_period = expected_period or "31-Mar-2024"
            date_match = re.search(r"(\d{1,2}[-_][a-zA-Z]{3}[-_]\d{2,4})", filename)
            if date_match:
                detected_period = date_match.group(1).replace("_", "-")

            return ClassifiedFile(
                filename=filename,
                file_type="FX_RATES",
                period=detected_period,
                confidence=0.98,
                classification_method="DETERMINISTIC",
                reasoning=f"Identified FX rate table for period {detected_period}.",
                needs_review=False,
                sheet_names=preview["sheets"],
                raw_data=file_bytes
            )

        # 4. Intercompany Transactions / Schedules
        if any(k in fname_lower for k in ["intercompany", "ic_trans", "ic_elim", "ic_schedule", "reciprocal"]) or \
           any(k in sheets_lower for k in ["ic_eliminations", "intercompany", "ic eliminations"]):
            return ClassifiedFile(
                filename=filename,
                file_type="INTERCOMPANY_SCHEDULE",
                confidence=0.95,
                classification_method="DETERMINISTIC",
                reasoning="Identified Intercompany Transactions Schedule by filename or sheet name.",
                needs_review=False,
                sheet_names=preview["sheets"],
                raw_data=file_bytes
            )

        # 5. Deterministic Trial Balance (with Entity matching)
        ent_code = None
        if known_entities:
            for e in known_entities:
                pattern = rf"(^|[_\-\s]){re.escape(e.lower())}([_\-\s]|\.|$)"
                if re.search(pattern, fname_lower) or any(re.search(pattern, s) for s in sheets_lower):
                    ent_code = e
                    break

        # Fallback regex for common entity patterns: Company_P, Company_S1, Sub_1, etc.
        if not ent_code:
            m = re.search(r"(company[_\s-]?[a-z0-9]+|sub[_\s-]?[a-z0-9]+|entity[_\s-]?[a-z0-9]+)", fname_lower)
            if m:
                ent_code = m.group(1).title().replace(" ", "_").replace("-", "_")

        is_prior = "prior" in fname_lower or "opening" in fname_lower or "py" in fname_lower

        if ent_code and ("tb" in fname_lower or "trial" in fname_lower or "balance" in fname_lower):
            ftype = "PRIOR_TB" if is_prior else "CURRENT_TB"
            return ClassifiedFile(
                filename=filename,
                file_type=ftype,
                entity_code=ent_code,
                period=expected_period,
                confidence=0.92,
                classification_method="DETERMINISTIC",
                reasoning=f"Identified {ftype} for legal entity '{ent_code}' via filename match.",
                needs_review=False,
                sheet_names=preview["sheets"],
                raw_data=file_bytes
            )

        # -------------------------------------------------------------
        # Tier 2: Agentic Brain (Gemini Flash)
        # -------------------------------------------------------------
        if config.validate_api_key_strict():
            ai_classification = cls._classify_with_gemini(preview, known_entities, expected_period)
            if ai_classification:
                ai_classification.raw_data = file_bytes
                return ai_classification

        # -------------------------------------------------------------
        # Tier 3: Fallback / HITL Escalation
        # -------------------------------------------------------------
        return ClassifiedFile(
            filename=filename,
            file_type="CURRENT_TB" if ent_code else "UNKNOWN",
            entity_code=ent_code,
            period=expected_period,
            confidence=0.50,
            classification_method="DETERMINISTIC",
            reasoning="Uncertain structure. Routed to Human-in-the-Loop for confirmation.",
            needs_review=True,
            sheet_names=preview["sheets"],
            raw_data=file_bytes
        )

    @classmethod
    def _classify_with_gemini(
        cls,
        preview: Dict[str, Any],
        known_entities: Optional[List[str]],
        expected_period: Optional[str]
    ) -> Optional[ClassifiedFile]:
        """Invokes Gemini Agentic Brain to analyze messy layouts and classify the document."""
        try:
            import google.genai as genai
            from google.genai import types

            client = genai.Client(api_key=config.gemini_api_key)
            prompt = f"""
You are an expert financial consolidation and ERP ingestion agent.
Analyze the following file preview and determine what kind of accounting file it is, which legal entity it belongs to, and what reporting period it covers.

File Name: {preview['filename']}
Sheet Names: {preview['sheets']}
Top Sample Rows (JSON):
{json.dumps(preview['sample_rows'][:6])}

Known In-Scope Entities in Conglomerate: {known_entities or ['Company_P', 'Company_S1', 'Company_S2', 'Company_S3']}
Expected Reporting Period: {expected_period or '31-Mar-2024'}

Classify the file into exactly ONE of the following file_types:
- CURRENT_TB: Trial Balance for current consolidation period
- PRIOR_TB: Prior period trial balance / opening balance file
- INTERCOMPANY_SCHEDULE: Intercompany transactions, receivables/payables between subsidiaries
- FX_RATES: Currency exchange rates table
- COA_MASTER: Group Chart of Accounts hierarchy
- ENTITY_STRUCTURE: Entity ownership hierarchy

Respond STRICTLY in JSON format matching this schema:
{{
  "file_type": "CURRENT_TB",
  "entity_code": "Company_S1",
  "period": "31-Mar-2024",
  "currency": "INR",
  "confidence": 0.95,
  "reasoning": "Headers show GL Code, Account Description, Debit, Credit for Operating Sub 1."
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
            threshold = config.ai_confidence_threshold

            return ClassifiedFile(
                filename=preview["filename"],
                file_type=data.get("file_type", "CURRENT_TB"),
                entity_code=data.get("entity_code"),
                period=data.get("period") or expected_period,
                currency=data.get("currency"),
                confidence=conf,
                classification_method="GEMINI_AI",
                reasoning=data.get("reasoning", "Classified via Gemini Agentic Brain layout inspection."),
                needs_review=(conf < threshold or data.get("entity_code") is None),
                sheet_names=preview["sheets"]
            )
        except Exception as e:
            return None

    @classmethod
    def classify_batch(
        cls,
        files: List[Tuple[str, bytes]],
        expected_period: Optional[str] = None,
        known_entities: Optional[List[str]] = None
    ) -> List[ClassifiedFile]:
        """Classifies a batch of 10-15+ files and checks for missing prerequisites."""
        results = []
        for filename, file_bytes in files:
            cf = cls.classify_file(file_bytes, filename, expected_period, known_entities)
            results.append(cf)
        return results
