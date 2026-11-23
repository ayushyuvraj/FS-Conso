"""Cell-Level Mathematical Formula Lineage & Provenance Tracker.

Traces any number on the Financial Statements backward to Group COA,
Consolidated TB, Intercompany Eliminations, FX Translations, and Raw Ingested TB coordinates.
"""

from typing import Any, Dict, List, Optional
from fs_conso.agent.state import ConsolidationState


class LineageTracker:
    """Provides end-to-end mathematical lineage from Statement Line down to Raw Client TB Cell."""

    @classmethod
    def trace_account(
        cls,
        account_code_or_query: str,
        state: ConsolidationState
    ) -> Dict[str, Any]:
        """Traces the backward lineage of an account across all consolidation stages."""
        raw_query = (account_code_or_query or "").strip()
        if not raw_query:
            return {
                "success": False,
                "found": False,
                "query": "",
                "message": "Search query cannot be empty."
            }

        query = raw_query.lower()

        # 1. Locate matching row in Consolidated TB
        matched_conso_row = None
        if state.consolidated_tb and state.consolidated_tb.rows:
            for r in state.consolidated_tb.rows:
                code = (r.account_code or "").strip().lower()
                desc = (r.account_description or "").strip().lower()
                if query == code or query in code or query in desc:
                    matched_conso_row = r
                    break

        # 2. If not found in Consolidated TB, search in Raw TBs
        if not matched_conso_row and state.raw_tbs:
            for raw_tb in state.raw_tbs:
                for idx, r in enumerate(raw_tb.rows, start=4):
                    code = (r.account_code or "").strip().lower()
                    desc = (r.account_description or "").strip().lower()
                    if query == code or query in code or query in desc:
                        target_code = r.account_code
                        target_desc = r.account_description or raw_query
                        tot = r.amount if r.amount is not None else round((r.debit or 0.0) - (r.credit or 0.0), 2)
                        
                        raw_stage = {
                            "stage_name": "Raw Ingested Trial Balances",
                            "sources": [{
                                "entity_code": raw_tb.entity_code,
                                "sheet_name": f"TB_{raw_tb.entity_code}",
                                "cell_coordinate": f"C{idx}",
                                "local_account_code": r.account_code,
                                "local_description": r.account_description,
                                "debit": r.debit,
                                "credit": r.credit,
                                "signed_amount": tot,
                                "provenance_type": "Direct Client Ingested Coordinate"
                            }]
                        }
                        lineage_graph = [
                            {
                                "tier": 1,
                                "stage": "Raw Client TB",
                                "source": f"TB_{raw_tb.entity_code}!C{idx}",
                                "description": f"Direct TB coordinate for {raw_tb.entity_code} ({r.account_code})",
                                "formula": "Client Ingested Value",
                                "amount": tot,
                                "status": "INGESTED"
                            },
                            {
                                "tier": 2,
                                "stage": "Ind AS 21 FX",
                                "source": "FX_Rates",
                                "description": "Functional currency translation pending consolidation execution",
                                "formula": "=Source * FX_Rate",
                                "amount": tot,
                                "status": "PENDING_RUN"
                            },
                            {
                                "tier": 3,
                                "stage": "IC Eliminations",
                                "source": "IC_Eliminations",
                                "description": "Intercompany elimination checks",
                                "formula": "Net 0.00 Adjustment",
                                "amount": 0.0,
                                "status": "PENDING_RUN"
                            },
                            {
                                "tier": 4,
                                "stage": "Consolidated TB",
                                "source": "Consolidated_TB",
                                "description": "Multi-entity summation",
                                "formula": "=SUM(Entities)",
                                "amount": tot,
                                "status": "PENDING_RUN"
                            },
                            {
                                "tier": 5,
                                "stage": "Financial Statements",
                                "source": "Balance_Sheet / Profit_and_Loss",
                                "description": f"IND AS presentation under {target_desc}",
                                "formula": f'=SUMIFS(Consolidated_TB!$H:$H, Consolidated_TB!$A:$A, "{target_code}")',
                                "amount": tot,
                                "status": "PENDING_RUN"
                            }
                        ]
                        return {
                            "success": True,
                            "found": True,
                            "query": raw_query,
                            "target": {
                                "account_code": target_code,
                                "account_description": target_desc,
                                "consolidated_net": tot
                            },
                            "target_account": {
                                "code": target_code,
                                "description": target_desc
                            },
                            "lineage_graph": lineage_graph,
                            "lineage_path": [raw_stage]
                        }

        # If still not found, return found=False with zero false positives
        if not matched_conso_row:
            return {
                "success": True,
                "found": False,
                "query": raw_query,
                "message": f"No account found matching '{raw_query}' in Consolidated TB or source Trial Balances."
            }

        target_code = matched_conso_row.account_code
        target_desc = matched_conso_row.account_description
        row_idx = getattr(matched_conso_row, "source_row_index", 14) or 14

        # 3. Consolidated TB Stage
        ent_count = len(state.consolidated_tb.entity_codes) if state.consolidated_tb else 4
        last_ent_col = chr(ord('C') + max(0, ent_count - 1))
        elim_col = chr(ord(last_ent_col) + 1)
        conso_formula = f'=SUM(C{row_idx}:{last_ent_col}{row_idx}) + {elim_col}{row_idx}'

        conso_stage = {
            "stage_name": "Consolidated Trial Balance",
            "sheet_name": "Consolidated_TB",
            "account_code": target_code,
            "account_description": target_desc,
            "total_entities_amount": matched_conso_row.total_entities,
            "eliminations_amount": matched_conso_row.eliminations_total,
            "consolidated_net_amount": matched_conso_row.consolidated_net,
            "excel_formula": conso_formula,
            "formula_rule": "Sum of entity translated balances plus net intercompany elimination adjustments."
        }

        # 4. Eliminations Stage
        elim_stage = {
            "stage_name": "Intercompany Eliminations",
            "sheet_name": "IC_Eliminations",
            "vouchers_affecting": [],
            "total_adjustment": matched_conso_row.eliminations_total,
            "excel_formula": f'=SUMIFS(IC_Eliminations!$E:$E, IC_Eliminations!$C:$C, "{target_code}") - SUMIFS(IC_Eliminations!$F:$F, IC_Eliminations!$C:$C, "{target_code}")'
        }

        if state.elimination_result and state.elimination_result.vouchers:
            for v in state.elimination_result.vouchers:
                is_debit = (v.debit_account.strip() == target_code)
                is_credit = (v.credit_account.strip() == target_code)
                if is_debit or is_credit:
                    elim_stage["vouchers_affecting"].append({
                        "voucher_id": v.voucher_id,
                        "entity_code": v.entity_code,
                        "counterparty_code": v.counterparty_code,
                        "debit": v.eliminated_amount if is_debit else 0.0,
                        "credit": v.eliminated_amount if is_credit else 0.0,
                        "net_impact": v.eliminated_amount if is_debit else -v.eliminated_amount,
                        "description": f"Intercompany elimination between {v.entity_code} and {v.counterparty_code}",
                        "status": v.status.value if hasattr(v.status, "value") else str(v.status)
                    })

        # 5. FX Translations Stage
        trans_stage = {
            "stage_name": "Foreign Currency Translation (Ind AS 21)",
            "sheet_name": "Translated_TB",
            "entities": []
        }

        for tb in state.translated_tbs:
            for r in tb.rows:
                if r.account_code.strip() == target_code:
                    row_num = getattr(r, "source_row_index", 7) or 7
                    trans_stage["entities"].append({
                        "entity_code": tb.entity_code,
                        "local_currency": getattr(r, "source_currency", getattr(r, "currency", "INR")),
                        "local_amount": getattr(r, "source_amount", getattr(r, "local_amount", 0.0)),
                        "rate_applied": getattr(r, "rate_applied", 1.0),
                        "rate_type": getattr(r.rate_type, "value", str(r.rate_type)) if hasattr(r, "rate_type") else "Closing",
                        "translated_inr": getattr(r, "translated_amount", 0.0),
                        "excel_formula": f"='TB_{tb.entity_code}'!E{row_num} * 'FX_Rates'!D4"
                    })

        # 6. Raw Source Ingested TB Stage
        raw_stage = {
            "stage_name": "Raw Ingested Trial Balances",
            "sources": []
        }

        for raw_tb in state.raw_tbs:
            for idx, r in enumerate(raw_tb.rows, start=4):
                mapped_match = False
                for dec in state.mapping_decisions:
                    if dec.local_code == r.account_code and dec.group_code == target_code:
                        mapped_match = True
                        break

                if r.account_code == target_code or mapped_match:
                    raw_stage["sources"].append({
                        "entity_code": raw_tb.entity_code,
                        "sheet_name": f"TB_{raw_tb.entity_code}",
                        "cell_coordinate": f"C{idx}",
                        "local_account_code": r.account_code,
                        "local_description": r.account_description,
                        "debit": r.debit,
                        "credit": r.credit,
                        "signed_amount": r.amount if r.amount is not None else round((r.debit or 0.0) - (r.credit or 0.0), 2),
                        "provenance_type": "Direct Client Ingested Coordinate"
                    })

        # Build 5-tier lineage graph
        lineage_graph = []

        # Tier 1
        raw_sources = raw_stage.get("sources", [])
        if raw_sources:
            for s in raw_sources[:3]:
                lineage_graph.append({
                    "tier": 1,
                    "stage": "Raw Client TB",
                    "source": f"{s['sheet_name']}!{s['cell_coordinate']}",
                    "description": f"Direct TB coordinate for {s['entity_code']} ({s['local_account_code']})",
                    "formula": "Client Ingested Value",
                    "amount": s.get("signed_amount", 0.0),
                    "status": "INGESTED"
                })
        else:
            lineage_graph.append({
                "tier": 1,
                "stage": "Raw Client TB",
                "source": "Consolidated Ledger Precedents",
                "description": f"Source ledger balances for {target_desc}",
                "formula": "Client Ingested Value",
                "amount": matched_conso_row.total_entities,
                "status": "INGESTED"
            })

        # Tier 2
        lineage_graph.append({
            "tier": 2,
            "stage": "Ind AS 21 FX",
            "source": "FX_Rates & Translated_TB",
            "description": "Functional to presentation currency conversion (closing/average rate)",
            "formula": "=Source_Amount * FX_Rate",
            "amount": matched_conso_row.total_entities,
            "status": "TRANSLATED"
        })

        # Tier 3
        vouchers = elim_stage.get("vouchers_affecting", [])
        if vouchers:
            v_desc = ", ".join(v["voucher_id"] for v in vouchers)
            lineage_graph.append({
                "tier": 3,
                "stage": "IC Eliminations",
                "source": f"IC_Eliminations ({v_desc})",
                "description": f"Elimination adjustment of ₹ {matched_conso_row.eliminations_total}",
                "formula": elim_stage["excel_formula"],
                "amount": matched_conso_row.eliminations_total,
                "status": "ELIMINATED"
            })
        else:
            lineage_graph.append({
                "tier": 3,
                "stage": "IC Eliminations",
                "source": "IC_Eliminations",
                "description": "No intercompany variances detected (Zero reciprocal balance)",
                "formula": "Net 0.00 Adjustment",
                "amount": 0.0,
                "status": "BALANCED"
            })

        # Tier 4
        lineage_graph.append({
            "tier": 4,
            "stage": "Consolidated TB",
            "source": "Consolidated_TB",
            "description": f"Net consolidated balance for code {target_code}",
            "formula": conso_stage["excel_formula"],
            "amount": matched_conso_row.consolidated_net,
            "status": "FORMULA_LINKED"
        })

        # Tier 5
        lineage_graph.append({
            "tier": 5,
            "stage": "Financial Statements",
            "source": "Balance_Sheet / Profit_and_Loss",
            "description": f"IND AS presentation under {target_desc}",
            "formula": f'=SUMIFS(Consolidated_TB!$H:$H, Consolidated_TB!$A:$A, "{target_code}")',
            "amount": matched_conso_row.consolidated_net,
            "status": "PUBLISHED"
        })

        return {
            "success": True,
            "found": True,
            "query": raw_query,
            "target": {
                "account_code": target_code,
                "account_description": target_desc,
                "consolidated_net": matched_conso_row.consolidated_net
            },
            "target_account": {
                "code": target_code,
                "description": target_desc
            },
            "lineage_graph": lineage_graph,
            "lineage_path": [
                raw_stage,
                trans_stage,
                elim_stage,
                conso_stage
            ]
        }
