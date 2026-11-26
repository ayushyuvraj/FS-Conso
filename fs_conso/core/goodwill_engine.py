"""Core calculation engine and AI/deterministic matching for Step 5: Goodwill Schedule."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from fs_conso.config import config
from fs_conso.models.goodwill import (
    GoodwillAdjustmentItem,
    GoodwillEntityData,
    GoodwillSchedule,
)

logger = logging.getLogger(__name__)


class GoodwillEngine:
    """Computes Share Capital rollups, dynamic adjustments, investment matching,

    and Goodwill vs Capital Reserve per entity under Ind AS 103 / IFRS 3.
    """

    @classmethod
    def calculate_share_capital_from_l0(
        cls,
        entity_code: str,
        l0_code: str,
        state: Any,
        reporting_currency: str = "INR"
    ) -> Tuple[float, str]:
        """Calculates the sum of all trial balance accounts mapped to the given Level 0 code

        for the specific entity, translated to the reporting currency using Ind AS 21 historical rules.
        Returns: (sum_amount, l0_display_name)
        """
        if not l0_code:
            return 0.0, ""

        norm_ent = (entity_code or "").strip().upper()
        norm_l0 = str(l0_code).strip()
        l0_name = norm_l0

        # 1. Resolve Level 0 Name from mapping decisions or COA if available
        if state and getattr(state, "mapping_decisions", None):
            for d in state.mapping_decisions:
                grp = str(getattr(d, "group_code", "")).strip()
                if grp == norm_l0:
                    l0_name = getattr(d, "level_0_name", None) or getattr(d, "group_description", None) or norm_l0
                    break

        total_amount = 0.0
        found_in_translated = False

        # 2. Check in translated_tbs first (accounts are already standardized to Level 0 and translated to reporting currency)
        if state and getattr(state, "translated_tbs", None):
            for tb in state.translated_tbs:
                if (getattr(tb, "entity_code", "") or "").strip().upper() == norm_ent:
                    for row in getattr(tb, "rows", []):
                        acc = str(getattr(row, "account_code", "")).strip()
                        if acc == norm_l0:
                            # Sum translated amount
                            amt = float(getattr(row, "translated_amount", 0.0) or 0.0)
                            # In financial reporting, equity credit balances might be positive or negative depending on TB convention.
                            # We take the absolute value or normal credit representation for share capital.
                            total_amount += abs(amt)
                            found_in_translated = True

        # 3. Fallback: Sum from mapping_decisions directly
        if not found_in_translated and state and getattr(state, "mapping_decisions", None):
            for d in state.mapping_decisions:
                d_ent = (getattr(d, "entity_code", "") or "").strip().upper()
                grp = str(getattr(d, "group_code", "")).strip()
                if (not d_ent or d_ent == norm_ent) and grp == norm_l0:
                    amt = float(getattr(d, "amount", 0.0) or 0.0)
                    total_amount += abs(amt)

        return round(total_amount, 2), l0_name

    @classmethod
    def search_investment_account(
        cls,
        parent_code: str,
        sub_code: str,
        sub_name: str,
        state: Any,
        reporting_currency: str = "INR"
    ) -> Tuple[Optional[str], Optional[str], float, float, str, bool]:
        """Searches parent entity trial balance for the investment account in the given subsidiary.

        Uses deterministic keyword matching, then Gemini LLM judge, and falls back to HITL.
        Returns: (account_code, account_name, amount, confidence, match_method, needs_hitl)
        """
        norm_parent = (parent_code or "Company_P").strip().upper()
        norm_sub_code = (sub_code or "").strip().lower()
        norm_sub_name = (sub_name or "").strip().lower()

        # Extract parent TB rows
        parent_rows = []
        if state and getattr(state, "translated_tbs", None):
            for tb in state.translated_tbs:
                if (getattr(tb, "entity_code", "") or "").strip().upper() == norm_parent:
                    parent_rows = getattr(tb, "rows", [])
                    break
        elif state and getattr(state, "raw_tbs", None):
            for tb in state.raw_tbs:
                if (getattr(tb, "entity_code", "") or "").strip().upper() == norm_parent:
                    parent_rows = getattr(tb, "rows", [])
                    break

        if not parent_rows:
            return None, None, 0.0, 0.0, "HITL", True

        # 1. Deterministic Search
        # Check for explicit keywords: "investment", "shares in", "inv in" + sub name or code
        candidates = []
        for r in parent_rows:
            code = str(getattr(r, "account_code", "") or getattr(r, "local_account_code", ""))
            desc = str(getattr(r, "account_description", "") or getattr(r, "account_name", "")).strip()
            amt = abs(float(getattr(r, "translated_amount", None) or getattr(r, "source_amount", None) or getattr(r, "amount", 0.0) or 0.0))
            desc_lower = desc.lower()

            is_investment_desc = any(k in desc_lower for k in ["investment", "shares in", "equity in", "subsidiar"])
            code_prefix_match = code.startswith(("A1104", "A1201", "1104", "1201", "INV"))

            sub_code_match = norm_sub_code in desc_lower or norm_sub_code in code.lower()
            sub_name_match = norm_sub_name and any(part in desc_lower for part in norm_sub_name.split() if len(part) > 2)

            score = 0.0
            if (is_investment_desc or code_prefix_match) and (sub_code_match or sub_name_match):
                score = 1.0
            elif is_investment_desc and (sub_code_match or sub_name_match):
                score = 0.95
            elif (sub_code_match or sub_name_match):
                score = 0.75
            elif is_investment_desc:
                score = 0.50

            if score > 0.4:
                candidates.append((code, desc, amt, score))

        # Sort candidates descending by score
        candidates.sort(key=lambda x: x[3], reverse=True)

        if candidates and candidates[0][3] >= 0.85:
            top = candidates[0]
            return top[0], top[1], top[2], top[3], "DETERMINISTIC", False

        # 2. Gemini LLM Matching Fallback
        if config.validate_api_key_strict() and candidates:
            try:
                from google import genai
                client = genai.Client(api_key=config.gemini_api_key)
                cand_json = json.dumps([{"code": c[0], "desc": c[1], "amount": c[2]} for c in candidates[:8]])
                prompt = f"""You are an expert consolidation accountant.
Target subsidiary: {sub_name} (Code: {sub_code}).
Parent company candidate investment accounts:
{cand_json}

Identify the exact parent company account representing the investment/shares in this subsidiary.
Return JSON:
{{"code": "...", "desc": "...", "confidence": 0.0 to 1.0, "reasoning": "..."}}
"""
                resp = client.models.generate_content(
                    model=config.gemini_model,
                    contents=prompt
                )
                text = resp.text or ""
                # Parse JSON
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    p_code = parsed.get("code")
                    conf = float(parsed.get("confidence", 0.0))
                    matched_cand = next((c for c in candidates if c[0] == p_code), None)
                    if matched_cand and conf >= config.ai_confidence_threshold:
                        return matched_cand[0], matched_cand[1], matched_cand[2], conf, "AI_INFERRED", False
            except Exception as exc:
                logger.warning(f"LLM investment matching failed: {exc}")

        # 3. Route to HITL
        best_cand = candidates[0] if candidates else (None, None, 0.0, 0.0)
        return best_cand[0], best_cand[1], best_cand[2], best_cand[3] if candidates else 0.0, "HITL", True

    @classmethod
    def recalculate_schedule(cls, schedule: GoodwillSchedule) -> GoodwillSchedule:
        """Computes Net Asset at acquisition, Goodwill, and Capital Reserve for each entity."""
        total_goodwill = 0.0
        total_capital_reserve = 0.0

        for ent_code in schedule.entities:
            data = schedule.data_by_entity.get(ent_code)
            if not data:
                continue

            # Calculate sum of all dynamic adjustments for this entity
            adj_sum = sum(
                float(adj.amounts_by_entity.get(ent_code, 0.0) or 0.0)
                for adj in schedule.adjustments
            )

            # Net Assets at Acquisition = Share Capital + Adjustments + Retained Earnings
            net_assets = round(
                data.share_capital_amount + adj_sum + data.retained_earnings_amount,
                2
            )
            data.net_assets_at_acquisition = net_assets

            # Diff = Investment by company - Net Assets at acquisition
            diff = round(data.investment_amount - net_assets, 2)

            if diff > 0.001:
                data.goodwill_amount = diff
                data.capital_reserve_amount = 0.0
            elif diff < -0.001:
                data.goodwill_amount = 0.0
                data.capital_reserve_amount = abs(diff)
            else:
                data.goodwill_amount = 0.0
                data.capital_reserve_amount = 0.0

            total_goodwill += data.goodwill_amount
            total_capital_reserve += data.capital_reserve_amount

        schedule.total_goodwill = round(total_goodwill, 2)
        schedule.total_capital_reserve = round(total_capital_reserve, 2)
        return schedule

    @classmethod
    def initialize_schedule(
        cls,
        company_id: str,
        period: str,
        state: Any,
        company_profile: Any = None
    ) -> GoodwillSchedule:
        """Creates or rehydrates a GoodwillSchedule from company profile and active state."""
        rep_curr = "INR"
        if company_profile and getattr(company_profile, "reporting_currency", None):
            rep_curr = company_profile.reporting_currency
        elif state and getattr(state, "reporting_currency", None):
            rep_curr = state.reporting_currency

        # Determine entities: Parent first, then Subsidiaries
        hierarchy = getattr(company_profile, "entity_hierarchy", None) if company_profile else None
        parent_code = "Company_P"
        entities_list: List[str] = []
        entity_info_map: Dict[str, Dict[str, Any]] = {}

        if hierarchy and getattr(hierarchy, "entities", None):
            parent_code = hierarchy.parent_code or "Company_P"
            # Put parent first
            p_ent = hierarchy.get_entity(parent_code)
            if p_ent:
                entities_list.append(parent_code)
                entity_info_map[parent_code] = {
                    "name": p_ent.entity_name,
                    "is_parent": True,
                    "currency": p_ent.input_currency or rep_curr
                }

            # Put subsidiaries next
            for e_code, ent in hierarchy.entities.items():
                if e_code != parent_code:
                    entities_list.append(e_code)
                    entity_info_map[e_code] = {
                        "name": ent.entity_name,
                        "is_parent": False,
                        "currency": ent.input_currency or rep_curr
                    }
        elif state and getattr(state, "raw_tbs", None):
            # Fallback from raw TBs
            for tb in state.raw_tbs:
                code = tb.entity_code
                if code not in entities_list:
                    entities_list.append(code)
                    entity_info_map[code] = {
                        "name": getattr(tb, "entity_name", code) or code,
                        "is_parent": (code == entities_list[0]),
                        "currency": tb.currency or rep_curr
                    }

        if not entities_list:
            entities_list = ["Company_P", "Sub_1", "Sub_2"]
            entity_info_map = {
                "Company_P": {"name": "Company P (Parent)", "is_parent": True, "currency": rep_curr},
                "Sub_1": {"name": "Subsidiary 1", "is_parent": False, "currency": "USD"},
                "Sub_2": {"name": "Subsidiary 2", "is_parent": False, "currency": "EUR"},
            }

        # Create schedule
        sched = GoodwillSchedule(
            company_id=company_id,
            period=period or "31-Mar-2024",
            reporting_currency=rep_curr,
            parent_entity_code=parent_code,
            entities=entities_list,
            adjustments=[
                GoodwillAdjustmentItem(
                    id="adj-1",
                    name="Fair Value & PPA Adjustments",
                    amounts_by_entity={e: 0.0 for e in entities_list},
                    remarks="Fair value uplift on acquisition"
                )
            ],
            data_by_entity={}
        )

        for ent_code in entities_list:
            info = entity_info_map.get(ent_code, {})
            ent_data = GoodwillEntityData(
                entity_code=ent_code,
                entity_name=info.get("name", ent_code),
                is_parent=info.get("is_parent", False),
                currency=info.get("currency", rep_curr),
                share_capital_amount=0.0,
                retained_earnings_amount=0.0,
                net_assets_at_acquisition=0.0,
                investment_amount=0.0
            )

            # Auto-detect default Share Capital Level 0 account if available in mapped TBs
            if state and getattr(state, "mapping_decisions", None):
                for d in state.mapping_decisions:
                    d_ent = (getattr(d, "entity_code", "") or "").strip().upper()
                    grp_desc = str(getattr(d, "group_description", "") or "").lower()
                    lvl_name = str(getattr(d, "level_0_name", "") or "").lower()
                    if (not d_ent or d_ent == ent_code.upper()) and any(k in grp_desc or k in lvl_name for k in ["share capital", "equity capital", "common stock"]):
                        ent_data.share_capital_l0_code = getattr(d, "group_code", None)
                        ent_data.share_capital_l0_name = getattr(d, "level_0_name", None) or getattr(d, "group_description", None)
                        amt, _ = cls.calculate_share_capital_from_l0(ent_code, ent_data.share_capital_l0_code, state, rep_curr)
                        ent_data.share_capital_amount = amt
                        break

            # Search investment for subsidiaries
            if not ent_data.is_parent:
                inv_code, inv_name, inv_amt, conf, method, hitl = cls.search_investment_account(
                    parent_code=parent_code,
                    sub_code=ent_code,
                    sub_name=ent_data.entity_name,
                    state=state,
                    reporting_currency=rep_curr
                )
                ent_data.investment_account_code = inv_code
                ent_data.investment_account_name = inv_name
                ent_data.investment_amount = inv_amt
                ent_data.investment_confidence = conf
                ent_data.investment_match_method = method
                ent_data.needs_hitl = hitl

            sched.data_by_entity[ent_code] = ent_data

        # Recalculate Net Assets, Goodwill, and Reserves
        return cls.recalculate_schedule(sched)
