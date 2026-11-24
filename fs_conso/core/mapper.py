"""Chart of Accounts (COA) standardization & AI mapping engine.

Features single-shot batched AI inference, complete multi-category COA candidates,
and normalized accounting heuristics for sub-second execution.
"""

import json
import re
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
    method: str  # "HISTORICAL_RULE", "DIRECT_CODE_MATCH", "HEURISTIC_EXACT", "ACCOUNTING_SYNONYM", "GEMINI_AI", "MANUAL", "UNMAPPED_EXCEPTION"
    confidence: float = 1.0
    reasoning: Optional[str] = None
    needs_review: bool = False


# Canonical accounting synonym heuristics mapping normalized patterns to Group COA codes
ACCOUNTING_SYNONYMS = [
    # Equity
    (re.compile(r"equity\s*(share)?\s*capital|common\s*stock|share\s*capital", re.IGNORECASE), "E210101", 0.98, "Matched standard Equity Share Capital line item."),
    (re.compile(r"retained\s*earnings|accumulated\s*profit", re.IGNORECASE), "210200", 0.98, "Matched standard Retained Earnings line item."),
    # Cash & Bank
    (re.compile(r"cash\s*at\s*bank|bank\s*cash|cash\s*and\s*cash\s*equivalents|cash\s*on\s*hand", re.IGNORECASE), "120400", 0.98, "Matched Cash & Cash Equivalents standard Group COA."),
    # Trade Receivables / Payables
    (re.compile(r"trade\s*receivables|debtors|customer\s*balances", re.IGNORECASE), "A120301", 0.95, "Matched Trade Receivables asset line."),
    (re.compile(r"trade\s*payables|trade\s*creditors|vendor\s*balances", re.IGNORECASE), "320300", 0.95, "Matched Trade Payables liability line."),
    # Intercompany Receivables / Payables / Loans
    (re.compile(r"intercompany\s*receivable|ic\s*rec|inter-company\s*receivable", re.IGNORECASE), "A120302", 0.95, "Matched Related Party / Intercompany Trade Receivable."),
    (re.compile(r"intercompany\s*payable|ic\s*pay|inter-company\s*payable", re.IGNORECASE), "L320401", 0.95, "Matched Related Party / Intercompany Trade Payable."),
    (re.compile(r"intercompany\s*loan|ic\s*loan|loan\s*from\s*parent", re.IGNORECASE), "L310104", 0.95, "Matched Intercompany / Related Party Borrowing line."),
    # Revenue lines
    (re.compile(r"patient\s*healthcare\s*revenue|hospital\s*services|healthcare\s*revenue|hospital\s*revenue", re.IGNORECASE), "I410101", 0.95, "Matched Hospital / Healthcare Services operating revenue."),
    (re.compile(r"diagnostic\s*scan\s*revenue|diagnostic\s*revenue|scan\s*revenue", re.IGNORECASE), "I410101", 0.95, "Matched Diagnostic Healthcare Services revenue."),
    (re.compile(r"pharmacy\s*(drug)?\s*sales|drug\s*sales|pharmacy\s*revenue", re.IGNORECASE), "I410102", 0.95, "Matched Pharmacy Sales revenue line."),
    (re.compile(r"revenue\s*from\s*(operating\s*)?management|management\s*fee\s*revenue", re.IGNORECASE), "410100", 0.95, "Matched Revenue from Operations."),
    # Inventories & Purchases
    (re.compile(r"pharmaceutical\s*inventories|drug\s*inventory|inventories|inventory", re.IGNORECASE), "A120101", 0.95, "Matched Inventories - Raw Materials / Traded Goods."),
    (re.compile(r"drug\s*purchases|purchase\s*of\s*stock|purchases", re.IGNORECASE), "X520101", 0.95, "Matched Purchase of Stock-in-Trade expense."),
    (re.compile(r"medical\s*consumables\s*expense|consumables\s*expense", re.IGNORECASE), "X510101", 0.95, "Matched Raw Materials and Consumables Consumed expense."),
    # Fixed Assets & Depreciation
    (re.compile(r"medical\s*equipment|equipment|plant\s*&\s*machinery", re.IGNORECASE), "A110103", 0.95, "Matched Plant & Machinery / Medical Equipment asset."),
    (re.compile(r"equipment\s*depreciation|depreciation\s*on\s*plant|depreciation", re.IGNORECASE), "A110111", 0.95, "Matched Depreciation - Plant & Machinery asset contra."),
]


class COAMappingEngine:
    """Standardizes local entity accounts to Group COA import format with batched AI inference."""
    _global_decision_cache: Dict[Tuple[str, str], Tuple[str, float, str, str]] = {}

    def __init__(self, coa: ChartOfAccounts, historical_mappings: Optional[Dict[Tuple[str, str], str]] = None):
        self.coa = coa
        self.historical_mappings = historical_mappings or {}
        self._gemini_client = None
        self.last_token_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _get_gemini_client(self, client=None):
        if client is not None:
            return client
        if self._gemini_client is not None:
            return self._gemini_client
        try:
            from google import genai
            self._gemini_client = genai.Client(api_key=config.gemini_api_key)
            return self._gemini_client
        except Exception:
            return None

    def _format_complete_coa_candidates(self) -> str:
        """Categorizes all available Chart of Accounts into a structured reference prompt."""
        categories = {
            "ASSET": [],
            "LIABILITY": [],
            "EQUITY": [],
            "INCOME": [],
            "EXPENSE": []
        }
        for item in self.coa.items.values():
            cat = item.account_type.value.upper()
            if cat in categories:
                categories[cat].append(f"{item.account_code}: {item.account_name}")

        sections = []
        for cat_name, items in categories.items():
            if items:
                sections.append(f"### {cat_name} ACCOUNTS:\n" + "\n".join(items))
        return "\n\n".join(sections)

    def _call_gemini_mapping_batch(
        self,
        unmapped_rows: List[Tuple[str, str, str]],  # (entity_code, local_code, local_desc)
        client=None
    ) -> Dict[str, Tuple[Optional[str], float, str]]:
        """Batches multiple unmapped accounts into a single Gemini prompt returning all mappings at once."""
        results: Dict[str, Tuple[Optional[str], float, str]] = {}
        if not unmapped_rows:
            return results

        if not config.validate_api_key_strict():
            return {code: (None, 0.0, "API key missing or invalid") for _, code, _ in unmapped_rows}

        ai_client = self._get_gemini_client(client)
        if ai_client is None:
            return {code: (None, 0.0, "Gemini client initialization failed") for _, code, _ in unmapped_rows}

        coa_reference = self._format_complete_coa_candidates()
        
        accounts_list = "\n".join([
            f"- ID: {idx+1} | Entity: {ent} | Local Code: {code} | Local Description: {desc}"
            for idx, (ent, code, desc) in enumerate(unmapped_rows)
        ])

        prompt = f"""You are an elite Enterprise Financial Accounting Auditor specializing in IND AS 110 consolidation.
Standardize and map the following subsidiary accounts to the best matching Group Chart of Accounts code.

SUBSIDIARY ACCOUNTS TO MAP:
{accounts_list}

GROUP CHART OF ACCOUNTS:
{coa_reference}

INSTRUCTIONS:
1. Examine the account nature (Asset, Liability, Equity, Income, or Expense) from the local description.
2. Select the most accurate leaf or header Group Account Code from the Group Chart of Accounts provided above.
3. Return ONLY a valid JSON array of objects matching this exact schema:
[
  {{
    "local_code": "code",
    "group_account_code": "selected_code",
    "confidence": 0.95,
    "reasoning": "brief accounting justification"
  }}
]
"""
        try:
            response = ai_client.models.generate_content(
                model=config.gemini_model,
                contents=prompt
            )
            # Capture token usage from Gemini metadata
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                p_tok = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                c_tok = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                t_tok = getattr(response.usage_metadata, "total_token_count", 0) or (p_tok + c_tok)
                self.last_token_usage["prompt_tokens"] += p_tok
                self.last_token_usage["completion_tokens"] += c_tok
                self.last_token_usage["total_tokens"] += t_tok

            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:].strip()
            items = json.loads(text)
            for item in items:
                l_code = str(item.get("local_code", "")).strip()
                g_code = str(item.get("group_account_code", "")).strip()
                conf = float(item.get("confidence", 0.90))
                reason = str(item.get("reasoning", "Inferred via batched Gemini AI semantic model."))
                if l_code:
                    results[l_code] = (g_code, conf, reason)
        except Exception as exc:
            err_msg = re.sub(r"AIza[0-9A-Za-z_-]{15,}", "AIzaSy[REDACTED]", str(exc))
            for _, code, _ in unmapped_rows:
                if code not in results:
                    results[code] = (None, 0.0, f"Gemini batch error: {err_msg}")

        return results

    def add_user_mapping(self, entity_code: str, local_code: str, group_code: str, reasoning: str = "User approved in HITL workbench") -> None:
        """Stores user approved mapping into learning memory cache and historical rules."""
        self.historical_mappings[(entity_code, local_code)] = group_code
        self._global_decision_cache[(entity_code, local_code)] = (group_code, 1.0, "USER_APPROVED_RULE", reasoning)

    def standardize_trial_balance(
        self,
        raw_tb: RawTrialBalance,
        use_ai: bool = True,
        gemini_client=None
    ) -> Tuple[StandardizedTrialBalance, List[MappingDecision]]:
        """Converts raw entity TB into standard import format:
        - Account GL Code, GL Description, Signed Amount (Debits +, Credits -).
        - Sum = 0.00.
        Uses cached rules, exact match, synonym heuristics, and batched AI inference.
        """
        standardized_rows: List[StandardizedRow] = []
        decisions: List[MappingDecision] = []

        # Step 1: Pre-classify all rows using fast local heuristics, cache, and rules
        pending_rows = []
        unmapped_for_ai = []

        for idx, row in enumerate(raw_tb.rows, start=1):
            local_code = row.account_code.strip()
            local_desc = row.account_description.strip()

            if row.debit is not None or row.credit is not None:
                signed_amount = (row.debit or 0.0) - (row.credit or 0.0)
            else:
                signed_amount = row.amount or 0.0

            cache_key = (raw_tb.entity_code, local_code)
            if cache_key in self._global_decision_cache:
                t_code, conf, meth, reas = self._global_decision_cache[cache_key]
                target_item = self.coa.get_item(t_code)
                pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, meth, conf, reas))
                continue

            # 1. Historical mappings
            hist_key = (raw_tb.entity_code, local_code)
            if hist_key in self.historical_mappings:
                target_code = self.historical_mappings[hist_key]
                target_item = self.coa.get_item(target_code)
                pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, "HISTORICAL_RULE", 1.0, "Matched via prior approved mapping table."))
                continue

            # 2. Direct code match in COA
            if local_code in self.coa.items:
                target_item = self.coa.get_item(local_code)
                pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, "DIRECT_CODE_MATCH", 1.0, "Local GL code directly matches Group COA code."))
                continue

            # 3. Exact or fuzzy description match in COA
            found = self.coa.find_by_name(local_desc)
            if found:
                pending_rows.append((idx, local_code, local_desc, signed_amount, found, "HEURISTIC_EXACT", 0.95, f"Account description matched '{found.account_name}'."))
                continue

            # 4. Standard accounting synonym heuristics
            synonym_matched = False
            for pattern, syn_code, syn_conf, syn_reas in ACCOUNTING_SYNONYMS:
                if pattern.search(local_desc) or pattern.search(local_code):
                    target_item = self.coa.get_item(syn_code)
                    if target_item:
                        pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, "ACCOUNTING_SYNONYM", syn_conf, syn_reas))
                        synonym_matched = True
                        break
            if synonym_matched:
                continue

            # 5. Row needs AI inference
            pending_rows.append((idx, local_code, local_desc, signed_amount, None, "PENDING_AI", 0.0, None))
            unmapped_for_ai.append((raw_tb.entity_code, local_code, local_desc))

        # Step 2: Batch process any unmapped rows via Gemini AI in a single call
        ai_results = {}
        if unmapped_for_ai and use_ai:
            ai_results = self._call_gemini_mapping_batch(unmapped_for_ai, client=gemini_client)

        # Step 3: Finalize all decisions and standardized rows
        for item in pending_rows:
            idx, local_code, local_desc, signed_amount, target_item, method, confidence, reasoning = item

            if target_item is None and method == "PENDING_AI":
                if local_code in ai_results:
                    ai_code, ai_conf, ai_reas = ai_results[local_code]
                    if ai_code and self.coa.get_item(ai_code):
                        target_item = self.coa.get_item(ai_code)
                        method = "GEMINI_AI"
                        confidence = ai_conf
                        reasoning = ai_reas

            if target_item is None:
                target_code = "999999"
                target_desc = f"Unmapped: {local_desc}"
                method = "UNMAPPED_EXCEPTION"
                confidence = 0.0
                reasoning = reasoning or "No candidate match found; flagged for user resolution."
                needs_rev = True
            else:
                target_code = target_item.account_code
                target_desc = target_item.account_name
                needs_rev = confidence < config.ai_confidence_threshold
                # Cache successful decision
                self._global_decision_cache[(raw_tb.entity_code, local_code)] = (target_code, confidence, method, reasoning)

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
