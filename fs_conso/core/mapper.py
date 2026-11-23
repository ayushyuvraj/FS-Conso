"""Chart of Accounts (COA) standardization & AI mapping engine."""

import json
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from fs_conso.config import config
from fs_conso.models.coa import AccountClassification, ChartOfAccounts, COAItem
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance, StandardizedRow, StandardizedTrialBalance

class MappingDecision(BaseModel):
    local_code: str
    local_description: str
    group_code: str
    group_description: str
    method: str  # "HISTORICAL_RULE", "HEURISTIC_EXACT", "GEMINI_AI", "MANUAL"
    confidence: float = 1.0
    reasoning: Optional[str] = None
    needs_review: bool = False

class COAMappingEngine:
    """Standardizes local entity accounts to Group COA import format."""

    def __init__(self, coa: ChartOfAccounts, historical_mappings: Optional[Dict[Tuple[str, str], str]] = None):
        self.coa = coa
        self.historical_mappings = historical_mappings or {}

    def _call_gemini_mapping(
        self,
        local_code: str,
        local_desc: str,
        entity_code: str,
        client=None
    ) -> Tuple[Optional[str], float, str]:
        """Calls Google Gemini using the google.genai SDK to semantically infer Group COA mapping."""
        # Check active API key gate
        if not config.validate_api_key_strict():
            config.require_active_api_key()

        if client is None:
            try:
                from google import genai
                client = genai.Client(api_key=config.gemini_api_key)
            except Exception as e:
                return None, 0.0, f"Gemini client initialization failed: {e}"

        candidates = [
            f"{item.account_code}: {item.account_name} ({item.account_type.value})"
            for item in list(self.coa.items.values())[:60]
        ]
        candidates_str = "\n".join(candidates)

        prompt = f"""You are an elite Enterprise Financial Accounting Auditor.
Map this subsidiary GL account to the best matching Group Chart of Accounts code.

Subsidiary Account:
- Entity: {entity_code}
- Local GL Code: {local_code}
- Local Description: {local_desc}

Candidate Group COA:
{candidates_str}

Return ONLY valid JSON matching this schema:
{{
  "group_account_code": "code",
  "confidence": 0.95,
  "reasoning": "one concise sentence explaining the match"
}}
"""
        try:
            response = client.models.generate_content(
                model=config.gemini_model,
                contents=prompt
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:].strip()
            data = json.loads(text)
            return data.get("group_account_code"), float(data.get("confidence", 0.0)), data.get("reasoning", "")
        except Exception as e:
            return None, 0.0, f"Gemini error: {e}"

    def standardize_trial_balance(
        self,
        raw_tb: RawTrialBalance,
        use_ai: bool = True,
        gemini_client=None
    ) -> Tuple[StandardizedTrialBalance, List[MappingDecision]]:
        """Converts raw entity TB into standard import format:

        - Account GL Code, GL Description, Signed Amount (Debits +, Credits -).
        - Sum = 0.00.
        """
        standardized_rows: List[StandardizedRow] = []
        decisions: List[MappingDecision] = []

        for idx, row in enumerate(raw_tb.rows, start=1):
            local_code = row.account_code.strip()
            local_desc = row.account_description.strip()
            
            # Determine signed local amount:
            # If 2 columns (debit/credit): Debits are +, Credits are -
            if row.debit is not None or row.credit is not None:
                signed_amount = (row.debit or 0.0) - (row.credit or 0.0)
            else:
                # 1 column format: assumes debit +, credit -
                signed_amount = row.amount or 0.0

            # 1. Check historical mapping
            hist_key = (raw_tb.entity_code, local_code)
            target_item: Optional[COAItem] = None
            method = "HISTORICAL_RULE"
            confidence = 1.0
            reasoning = "Matched via prior approved mapping table."

            if hist_key in self.historical_mappings:
                target_code = self.historical_mappings[hist_key]
                target_item = self.coa.get_item(target_code)
            elif local_code in self.coa.items:
                target_item = self.coa.get_item(local_code)
                method = "DIRECT_CODE_MATCH"
                reasoning = "Local GL code directly matches Group COA code."
            else:
                # 2. Check exact/fuzzy description match
                found = self.coa.find_by_name(local_desc)
                if found:
                    target_item = found
                    method = "HEURISTIC_EXACT"
                    confidence = 0.95
                    reasoning = f"Account description matched '{target_item.account_name}'."
                elif use_ai:
                    # 3. Call Gemini
                    ai_code, ai_conf, ai_reason = self._call_gemini_mapping(
                        local_code, local_desc, raw_tb.entity_code, gemini_client
                    )
                    if ai_code and self.coa.get_item(ai_code):
                        target_item = self.coa.get_item(ai_code)
                        method = "GEMINI_AI"
                        confidence = ai_conf
                        reasoning = ai_reason

            if target_item is None:
                # Fallback to general suspense/unmapped
                target_code = "999999"
                target_desc = f"Unmapped: {local_desc}"
                method = "UNMAPPED_EXCEPTION"
                confidence = 0.0
                reasoning = "No candidate match found; flagged for user resolution."
                needs_rev = True
            else:
                target_code = target_item.account_code
                target_desc = target_item.account_name
                needs_rev = confidence < config.ai_confidence_threshold

            decision = MappingDecision(
                local_code=local_code,
                local_description=local_desc,
                group_code=target_code,
                group_description=target_desc,
                method=method,
                confidence=confidence,
                reasoning=reasoning,
                needs_review=needs_rev
            )
            decisions.append(decision)

            standardized_rows.append(StandardizedRow(
                account_code=target_code,
                account_description=target_desc,
                amount=round(signed_amount, 2),
                local_account_code=local_code,
                local_description=local_desc,
                entity_code=raw_tb.entity_code,
                currency=raw_tb.currency,
                source_row_index=idx
            ))

        std_tb = StandardizedTrialBalance(
            entity_code=raw_tb.entity_code,
            period=raw_tb.period,
            currency=raw_tb.currency,
            rows=standardized_rows
        )
        return std_tb, decisions
