"""Chart of Accounts (COA) standardization & AI mapping engine.

Features single-shot batched AI inference, complete multi-category COA candidates,
and normalized accounting heuristics for sub-second execution.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
    entity_code: Optional[str] = None
    currency: Optional[str] = None
    amount: Optional[float] = None
    level_0_code: Optional[str] = None
    level_0_name: Optional[str] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    is_ambiguous: bool = False


# Canonical accounting synonym heuristics mapping normalized patterns to Group COA codes (strictly Level 0 leaf accounts)
ACCOUNTING_SYNONYMS = [
    # Equity
    (re.compile(r"equity\s*(share)?\s*capital|common\s*stock|share\s*capital", re.IGNORECASE), "E210101", 0.98, "Matched standard Equity Share Capital line item."),
    (re.compile(r"retained\s*earnings|accumulated\s*profit", re.IGNORECASE), "E210201", 0.98, "Matched standard Opening Retained Earnings line item."),
    # Cash & Bank
    (re.compile(r"cash\s*(and|&)?\s*bank|bank\s*and\s*cash|cash\s*at\s*bank|bank\s*cash|cash\s*and\s*cash\s*equivalents", re.IGNORECASE), "A120402", 0.98, "Matched Bank Balances standard Group COA."),
    (re.compile(r"cash\s*on\s*hand", re.IGNORECASE), "A120401", 0.98, "Matched Cash on Hand standard Group COA."),
    (re.compile(r"fixed\s*deposits?|term\s*deposits?|fd\b", re.IGNORECASE), "A120403", 0.95, "Matched Bank Deposits standard Group COA."),
    # Trade Receivables / Payables
    (re.compile(r"trade\s*receivables|debtors|customer\s*balances", re.IGNORECASE), "A120301", 0.95, "Matched Trade Receivables asset line."),
    (re.compile(r"trade\s*payables|trade\s*creditors|vendor\s*balances", re.IGNORECASE), "L320302", 0.95, "Matched Trade Creditors liability line."),
    # Intercompany Receivables / Payables / Loans
    (re.compile(r"intercompany\s*receivable|ic\s*rec|inter-company\s*receivable", re.IGNORECASE), "A120302", 0.95, "Matched Related Party / Intercompany Trade Receivable."),
    (re.compile(r"intercompany\s*payable|ic\s*pay|inter-company\s*payable", re.IGNORECASE), "L320401", 0.95, "Matched Related Party / Intercompany Trade Payable."),
    (re.compile(r"intercompany\s*loan|ic\s*loan|loan\s*from\s*parent", re.IGNORECASE), "L310104", 0.95, "Matched Intercompany / Related Party Borrowing line."),
    # Revenue lines
    (re.compile(r"patient\s*healthcare\s*revenue|hospital\s*services|healthcare\s*revenue|hospital\s*revenue", re.IGNORECASE), "I410101", 0.95, "Matched Hospital / Healthcare Services operating revenue."),
    (re.compile(r"diagnostic\s*scan\s*revenue|diagnostic\s*revenue|scan\s*revenue", re.IGNORECASE), "I410101", 0.95, "Matched Diagnostic Healthcare Services revenue."),
    (re.compile(r"pharmacy\s*(drug)?\s*sales|drug\s*sales|pharmacy\s*revenue", re.IGNORECASE), "I410102", 0.95, "Matched Pharmacy Sales revenue line."),
    (re.compile(r"revenue\s*from\s*(operating\s*)?management|management\s*fee\s*revenue|revenue\s*from\s*operations", re.IGNORECASE), "I410103", 0.95, "Matched Other Operating Revenue."),
    # Inventories & Purchases
    (re.compile(r"pharmaceutical\s*inventories|drug\s*inventory|inventories|inventory", re.IGNORECASE), "A120101", 0.95, "Matched Inventories - Raw Materials / Traded Goods."),
    (re.compile(r"drug\s*purchases|purchase\s*of\s*stock|purchases", re.IGNORECASE), "X520101", 0.95, "Matched Purchase of Stock-in-Trade expense."),
    (re.compile(r"medical\s*consumables\s*expense|consumables\s*expense", re.IGNORECASE), "X510101", 0.95, "Matched Raw Materials and Consumables Consumed expense."),
    # Fixed Assets & Depreciation
    (re.compile(r"medical\s*equipment|equipment|plant\s*&\s*machinery", re.IGNORECASE), "A110103", 0.95, "Matched Plant & Machinery / Medical Equipment asset."),
    (re.compile(r"equipment\s*depreciation|depreciation\s*on\s*plant|depreciation", re.IGNORECASE), "A110111", 0.95, "Matched Depreciation - Plant & Machinery asset contra."),
    (re.compile(r"\bcwip\b|capital\s*work\s*in\s*progress", re.IGNORECASE), "A110109", 0.95, "Matched Capital Work-in-Progress asset line."),
    # Personnel, Financing & Operating Sundries
    (re.compile(r"employee\s*benefits?|salaries(\s*and\s*wages)?|wages\s*and\s*salaries", re.IGNORECASE), "X540101", 0.95, "Matched Salaries, Wages and Bonus expense line."),
    (re.compile(r"finance\s*costs?|borrowing\s*costs?", re.IGNORECASE), "X560101", 0.95, "Matched Finance Costs / Interest expense line."),
    (re.compile(r"export\s*incentive|duty\s*drawback|freight.*recovery", re.IGNORECASE), "I410103", 0.95, "Matched Other Operating Revenue line item."),
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
        """Categorizes all available leaf Level 0 Chart of Accounts into a structured reference prompt."""
        categories = {
            "ASSET": [],
            "LIABILITY": [],
            "EQUITY": [],
            "INCOME": [],
            "EXPENSE": []
        }
        for item in self.coa.get_level_0_items():
            cat = item.account_type.value.upper()
            if cat in categories:
                l0_desc = item.level_0_account or item.account_name
                categories[cat].append(f"{item.account_code}: {item.account_name} (Level 0: {l0_desc})")

        sections = []
        for cat_name, items in categories.items():
            if items:
                sections.append(f"### {cat_name} LEVEL 0 ACCOUNTS:\n" + "\n".join(items))
        return "\n\n".join(sections)

    def _fallback_semantic_ranking(
        self,
        unmapped_rows: List[Tuple[str, str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """Intelligent semantic candidate ranker: evaluates leaf Level 0 Group COA candidates using accounting terminology & heuristics.
        Returns top 1-3 candidate options with confidence scores and accounting rationales.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for ent, code, desc in unmapped_rows:
            desc_norm = re.sub(r"[^a-zA-Z0-9\s]", " ", desc.lower()).strip()
            desc_tokens = set(desc_norm.split())

            candidates_scored = []
            for item in self.coa.get_level_0_items():
                name_norm = re.sub(r"[^a-zA-Z0-9\s]", " ", item.account_name.lower()).strip()
                name_tokens = set(name_norm.split())
                l0_norm = re.sub(r"[^a-zA-Z0-9\s]", " ", (item.level_0_account or "").lower()).strip()
                l0_tokens = set(l0_norm.split())

                score = 0.0
                shared_name = desc_tokens.intersection(name_tokens)
                shared_l0 = desc_tokens.intersection(l0_tokens)
                if shared_name:
                    score += len(shared_name) * 0.35
                if shared_l0:
                    score += len(shared_l0) * 0.25
                if desc_norm in name_norm or name_norm in desc_norm:
                    score += 0.40

                # Accounting nature keyword reinforcement
                for kw in ["receivable", "payable", "cash", "bank", "deposit", "inventory", "tax", "loan", "borrowing", "revenue", "sales", "expense", "asset", "liability", "equity"]:
                    if kw in desc_norm and (kw in name_norm or kw in l0_norm):
                        score += 0.20

                if score > 0.15:
                    conf = min(0.96, round(0.55 + min(score, 1.0) * 0.40, 2))
                    candidates_scored.append((conf, item))

            candidates_scored.sort(key=lambda x: x[0], reverse=True)
            top_candidates = []
            seen_codes = set()
            for conf, item in candidates_scored:
                if item.account_code not in seen_codes:
                    seen_codes.add(item.account_code)
                    top_candidates.append({
                        "group_account_code": item.account_code,
                        "group_account_name": item.account_name,
                        "level_0_account": item.level_0_account or item.account_name,
                        "confidence": conf,
                        "reasoning": f"Semantic alignment with Level 0 Group COA item '{item.account_name}' ({int(conf*100)}% match)."
                    })
                    if len(top_candidates) >= 3:
                        break

            if top_candidates:
                top = top_candidates[0]
                results[code] = {
                    "group_code": top["group_account_code"],
                    "confidence": top["confidence"],
                    "reasoning": top["reasoning"],
                    "candidates": top_candidates
                }
            else:
                results[code] = {
                    "group_code": "999999",
                    "confidence": 0.0,
                    "reasoning": "No candidate match found; flagged for user resolution.",
                    "candidates": []
                }
        return results

    def _call_gemini_mapping_batch(
        self,
        unmapped_rows: List[Tuple[str, str, str]],  # (entity_code, local_code, local_desc)
        client=None
    ) -> Dict[str, Dict[str, Any]]:
        """Batches unmapped accounts into a Gemini LLM-as-a-Judge prompt returning top 1-3 candidates with confidence scores."""
        results: Dict[str, Dict[str, Any]] = {}
        if not unmapped_rows:
            return results

        if not config.validate_api_key_strict():
            return self._fallback_semantic_ranking(unmapped_rows)

        ai_client = self._get_gemini_client(client)
        if ai_client is None:
            return self._fallback_semantic_ranking(unmapped_rows)

        coa_reference = self._format_complete_coa_candidates()

        accounts_list = "\n".join([
            f"- Entity: {ent} | Local Code: {code} | Local Description: {desc}"
            for ent, code, desc in unmapped_rows
        ])

        prompt = f"""You are an elite Enterprise Financial Accounting Auditor specializing in IND AS 110 / IFRS 10 group consolidation.
Your role is to act as an expert accounting judge to standardize subsidiary and parent trial balance accounts to the Group Chart of Accounts.

=== GROUP CHART OF ACCOUNTS (AVAILABLE TARGETS) ===
{coa_reference}

=== ACCOUNTS TO STANDARDIZE ===
{accounts_list}

=== AUDIT INSTRUCTIONS ===
1. Examine each account's nature (Asset, Liability, Equity, Revenue, Expense) from its local code and description.
2. Select the top matching leaf Level 0 Group Account Code from the Level 0 Group Chart of Accounts above.
3. CRITICAL REQUIREMENT: You MUST map ONLY to the leaf Level 0 accounts listed above. NEVER select higher-level rollups, sub-headers, or summary groups (e.g., do not select parent rollup codes).
4. Identify if there are secondary or tertiary probable Level 0 matches in the Group COA.
5. Assign an exact confidence score (between 0.00 and 1.00) to each candidate option representing the probabilistic fit.
6. Provide a concise accounting justification for each option citing relevant financial statement principles.
7. Return ONLY a valid JSON array of objects matching this exact schema:

[
  {{
    "local_code": "code",
    "top_matches": [
      {{
        "group_account_code": "selected_code",
        "group_account_name": "Account Name",
        "level_0_account": "Level 0 Rollup Name",
        "confidence": 0.94,
        "reasoning": "brief accounting justification"
      }},
      {{
        "group_account_code": "secondary_code",
        "group_account_name": "Secondary Name",
        "level_0_account": "Level 0 Rollup Name",
        "confidence": 0.86,
        "reasoning": "accounting rationale for secondary match"
      }}
    ]
  }}
]
"""
        try:
            response = ai_client.models.generate_content(
                model=config.gemini_model,
                contents=prompt
            )
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
                matches = item.get("top_matches", [])
                if not matches and item.get("group_account_code"):
                    matches = [{
                        "group_account_code": item.get("group_account_code"),
                        "group_account_name": item.get("group_account_name", ""),
                        "level_0_account": item.get("level_0_account", ""),
                        "confidence": float(item.get("confidence", 0.90)),
                        "reasoning": item.get("reasoning", "")
                    }]
                if l_code and matches:
                    valid_l0_matches = []
                    for m in matches:
                        g_code = str(m.get("group_account_code", "")).strip()
                        coa_it = self.coa.get_item(g_code)
                        # STRICT LEVEL 0 CHECK: Only accept matches that are true Level 0 accounts
                        if coa_it and coa_it.is_level_0:
                            m["group_account_code"] = coa_it.account_code
                            m["group_account_name"] = coa_it.account_name
                            m["level_0_account"] = coa_it.level_0_account or coa_it.account_name
                            valid_l0_matches.append(m)

                    if valid_l0_matches:
                        top = valid_l0_matches[0]
                        results[l_code] = {
                            "group_code": top.get("group_account_code"),
                            "confidence": float(top.get("confidence", 0.90)),
                            "reasoning": top.get("reasoning", "Inferred via Gemini LLM judge."),
                            "candidates": valid_l0_matches
                        }
        except Exception as exc:
            logger.warning(f"Gemini LLM mapping batch call failed, using intelligent semantic fallback: {exc}")
            fallback_res = self._fallback_semantic_ranking(unmapped_rows)
            results.update(fallback_res)

        # Fallback fill for any unparsed rows
        missing = [row for row in unmapped_rows if row[1] not in results]
        if missing:
            results.update(self._fallback_semantic_ranking(missing))

        return results

    @classmethod
    def clear_cache(cls) -> None:
        """Clears the global decision cache across all entities."""
        cls._global_decision_cache.clear()

    def add_user_mapping(self, entity_code: str, local_code: str, group_code: str, reasoning: str = "User approved in HITL workbench") -> None:
        """Stores user approved mapping into learning memory cache and historical rules."""
        target_item = self.coa.get_item(group_code)
        if target_item and not target_item.is_level_0:
            raise ValueError(f"Cannot map to '{group_code}' because it is a higher-level rollup header. Universal consolidation requires Level 0 leaf accounts only.")
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

            if row.amount is not None and (row.debit is None or row.credit is None or row.debit == row.credit):
                signed_amount = row.amount
            elif row.debit is not None or row.credit is not None:
                signed_amount = (row.debit or 0.0) - (row.credit or 0.0)
            else:
                signed_amount = row.amount or 0.0

            cache_key = (raw_tb.entity_code, local_code)
            if cache_key in self._global_decision_cache:
                t_code, conf, meth, reas = self._global_decision_cache[cache_key]
                target_item = self.coa.get_item(t_code)
                if target_item and target_item.is_level_0:
                    pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, meth, conf, reas))
                    continue
                else:
                    # Stale or non-Level 0 entry, evict from cache
                    self._global_decision_cache.pop(cache_key, None)

            # 1. Historical mappings (Level 0 only)
            hist_key = (raw_tb.entity_code, local_code)
            if hist_key in self.historical_mappings:
                target_code = self.historical_mappings[hist_key]
                target_item = self.coa.get_item(target_code)
                if target_item and target_item.is_level_0:
                    pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, "HISTORICAL_RULE", 1.0, "Matched via prior approved mapping table."))
                    continue

            # 2. Direct code match in COA (Level 0 only)
            if local_code in self.coa.items:
                target_item = self.coa.get_item(local_code)
                if target_item and target_item.is_level_0:
                    pending_rows.append((idx, local_code, local_desc, signed_amount, target_item, "DIRECT_CODE_MATCH", 1.0, "Local GL code directly matches Group COA code."))
                    continue

            # 3. Exact or fuzzy description match in COA (Level 0 only)
            found = self.coa.find_by_name(local_desc)
            if found and found.is_level_0:
                pending_rows.append((idx, local_code, local_desc, signed_amount, found, "HEURISTIC_EXACT", 0.95, f"Account description matched '{found.account_name}'."))
                continue

            # 4. Standard accounting synonym heuristics (Level 0 only)
            synonym_matched = False
            for pattern, syn_code, syn_conf, syn_reas in ACCOUNTING_SYNONYMS:
                if pattern.search(local_desc) or pattern.search(local_code):
                    target_item = self.coa.get_item(syn_code)
                    if target_item and target_item.is_level_0:
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
            candidates: List[Dict[str, Any]] = []
            is_ambiguous: bool = False

            if target_item is None and method == "PENDING_AI":
                if local_code in ai_results:
                    ai_entry = ai_results[local_code]
                    if isinstance(ai_entry, dict):
                        ai_code = ai_entry.get("group_code")
                        ai_conf = float(ai_entry.get("confidence", 0.0))
                        ai_reas = ai_entry.get("reasoning", "")
                        raw_cands = ai_entry.get("candidates", [])
                    elif isinstance(ai_entry, (tuple, list)):
                        ai_code = ai_entry[0]
                        ai_conf = float(ai_entry[1]) if len(ai_entry) > 1 else 0.0
                        ai_reas = str(ai_entry[2]) if len(ai_entry) > 2 else ""
                        raw_cands = []
                    else:
                        ai_code, ai_conf, ai_reas = None, 0.0, ""

                    # Filter candidates strictly to Level 0 leaf accounts
                    candidates = [
                        c for c in raw_cands
                        if self.coa.get_item(c.get("group_account_code", "")) and self.coa.get_item(c.get("group_account_code", "")).is_level_0
                    ]

                    if ai_code and self.coa.get_item(ai_code) and self.coa.get_item(ai_code).is_level_0:
                        target_item = self.coa.get_item(ai_code)
                        method = "GEMINI_AI"
                        confidence = ai_conf
                        reasoning = ai_reas
                    elif candidates:
                        top_cand = candidates[0]
                        target_item = self.coa.get_item(top_cand["group_account_code"])
                        method = "GEMINI_AI"
                        confidence = float(top_cand.get("confidence", 0.90))
                        reasoning = top_cand.get("reasoning", "Inferred via Gemini LLM judge.")
            elif target_item is not None:
                # Deterministic match: populate a single candidate option
                candidates = [{
                    "group_account_code": target_item.account_code,
                    "group_account_name": target_item.account_name,
                    "level_0_account": target_item.level_0_account or target_item.account_name,
                    "confidence": confidence,
                    "reasoning": reasoning or f"Matched via {method}"
                }]

            if target_item is None:
                target_code = "999999"
                target_desc = f"Unmapped: {local_desc}"
                l0_code = None
                l0_name = None
                method = "UNMAPPED_EXCEPTION"
                confidence = 0.0
                reasoning = reasoning or "No candidate match found; flagged for user resolution."
                needs_rev = True
                is_ambiguous = False
            else:
                target_code = target_item.account_code
                target_desc = target_item.account_name
                l0_code = target_item.account_code
                l0_name = target_item.level_0_account or target_item.account_name

                # Check threshold and ambiguity rules
                threshold = config.ai_confidence_threshold
                if method == "GEMINI_AI" and candidates:
                    # Ambiguity rule: if 2 or 3 candidate options are above or near threshold
                    high_conf_candidates = [c for c in candidates if float(c.get("confidence", 0.0)) >= threshold]
                    if len(high_conf_candidates) >= 2:
                        is_ambiguous = True
                    elif len(candidates) >= 2:
                        c1 = float(candidates[0].get("confidence", 0.0))
                        c2 = float(candidates[1].get("confidence", 0.0))
                        if c1 >= threshold and (c1 - c2) <= 0.08 and c2 >= (threshold - 0.05):
                            is_ambiguous = True

                    if is_ambiguous:
                        needs_rev = True
                        reasoning = f"Ambiguous AI Match: {len(candidates)} probable options near threshold ({int(threshold*100)}%). Auditor review required."
                    elif confidence < threshold:
                        needs_rev = True
                        reasoning = f"AI confidence ({int(confidence*100)}%) is below required threshold ({int(threshold*100)}%)."
                    else:
                        needs_rev = False
                elif method in ("DIRECT_CODE_MATCH", "HISTORICAL_RULE", "USER_APPROVED_RULE"):
                    needs_rev = False
                else:
                    needs_rev = confidence < threshold

                # Cache successful decision (strictly Level 0 leaf accounts)
                if target_item and target_item.is_level_0:
                    self._global_decision_cache[(raw_tb.entity_code, local_code)] = (target_code, confidence, method, reasoning)

            decision = MappingDecision(
                local_code=local_code,
                local_description=local_desc,
                group_code=target_code,
                group_description=target_desc,
                method=method,
                confidence=confidence,
                reasoning=reasoning,
                needs_review=needs_rev,
                entity_code=raw_tb.entity_code,
                currency=raw_tb.currency,
                amount=round(signed_amount, 2),
                level_0_code=l0_code,
                level_0_name=l0_name,
                candidates=candidates,
                is_ambiguous=is_ambiguous
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
