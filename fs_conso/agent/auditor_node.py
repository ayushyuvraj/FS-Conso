"""Strict Teacher Auditor Agent Node.

Evaluates the consolidation output against institutional criteria (0 to 100 score).
"""

from pathlib import Path
from typing import Dict, Tuple
import openpyxl

from fs_conso.agent.state import ConsolidationState

class StrictTeacherAuditor:
    """Performs rigorous independent verification across 4 quality pillars (25 pts each)."""

    @classmethod
    def audit(cls, state: ConsolidationState) -> Tuple[float, Dict]:
        scores = {
            "formula_integrity": 0.0,
            "financial_correctness": 0.0,
            "validation_and_tolerance": 0.0,
            "provenance_and_flow": 0.0
        }
        feedback = []

        # Pillar 1: Formula Integrity (25 pts)
        if not state.output_excel_path or not Path(state.output_excel_path).exists():
            feedback.append("Failing Pillar 1: Output Excel file was not generated.")
        else:
            wb = openpyxl.load_workbook(state.output_excel_path, data_only=False)
            downstream_sheets = ["Translated_TB", "IC_Eliminations", "Consolidated_TB", "Balance_Sheet", "Profit_and_Loss"]
            total_calc_cells = 0
            formula_cells = 0
            hardcoded_orphans = 0

            calc_col_map = {
                "Translated_TB": [5, 6, 7],
                "IC_Eliminations": [5, 6, 7],
                "Consolidated_TB": None,  # range(3, max_col + 1)
                "Balance_Sheet": None,
                "Profit_and_Loss": None
            }

            for s_name in downstream_sheets:
                if s_name not in wb.sheetnames:
                    continue
                ws = wb[s_name]
                target_cols = calc_col_map.get(s_name)
                cols_to_check = target_cols if target_cols is not None else list(range(3, ws.max_column + 1))

                for r in range(4, ws.max_row + 1):
                    for c in cols_to_check:
                        if c > ws.max_column:
                            continue
                        val = ws.cell(r, c).value
                        if val is None:
                            continue
                        str_val = str(val).strip()
                        total_calc_cells += 1
                        if str_val.startswith("="):
                            formula_cells += 1
                        elif isinstance(val, (int, float)) and val != 0.0:
                            hardcoded_orphans += 1

            wb.close()
            if total_calc_cells > 0:
                formula_pct = formula_cells / total_calc_cells
                scores["formula_integrity"] = round(25.0 * formula_pct, 2)
                if hardcoded_orphans > 0:
                    feedback.append(f"Pillar 1 Warning: Found {hardcoded_orphans} static numbers in downstream sheets.")
            else:
                feedback.append("Failing Pillar 1: No calculated cells found.")

        # Pillar 2: Financial Correctness (25 pts)
        if state.consolidated_tb and abs(state.consolidated_tb.total_consolidated) < 0.05:
            scores["financial_correctness"] = 25.0
        else:
            tot = state.consolidated_tb.total_consolidated if state.consolidated_tb else 999.0
            feedback.append(f"Failing Pillar 2: Consolidated TB does not balance to zero (Net: {tot:.2f}).")
            scores["financial_correctness"] = max(0.0, 25.0 - abs(tot))

        # Pillar 3: Validation and Tolerance (25 pts)
        if all(r.is_valid for r in state.validation_results):
            scores["validation_and_tolerance"] += 15.0
        else:
            feedback.append("Failing Pillar 3: Some entity TBs failed validation.")

        if state.elimination_result:
            scores["validation_and_tolerance"] += 10.0
        else:
            feedback.append("Failing Pillar 3: Intercompany elimination was not evaluated.")

        # Pillar 4: Provenance and Flow (25 pts)
        if state.current_step >= 6 and len(state.audit_trail) >= 5:
            scores["provenance_and_flow"] = 25.0
        else:
            scores["provenance_and_flow"] = round(25.0 * (state.current_step / 6.0), 2)
            feedback.append("Pillar 4: Pipeline did not complete all 6 sequential steps.")

        total_score = round(sum(scores.values()), 1)
        eval_result = {
            "score": total_score,
            "pillar_breakdown": scores,
            "passed": total_score >= 95.0,
            "feedback": feedback
        }
        return total_score, eval_result

def auditor_node(state: ConsolidationState) -> ConsolidationState:
    """Auditor Agent Node: Applies strict teacher grading."""
    score, evaluation = StrictTeacherAuditor.audit(state)
    state.teacher_score = score
    state.teacher_evaluation = evaluation

    status = "PASSED (HONORS)" if score >= 95.0 else "REVISION_REQUIRED"
    details = f"Strict Teacher Score: {score}/100. Breakdown: Formulas={evaluation['pillar_breakdown']['formula_integrity']}/25, Accounting={evaluation['pillar_breakdown']['financial_correctness']}/25, Validation={evaluation['pillar_breakdown']['validation_and_tolerance']}/25, Flow={evaluation['pillar_breakdown']['provenance_and_flow']}/25."

    state.audit_trail.append({
        "timestamp": "2026-11-24 00:00:10",
        "stage": "Quality Gate",
        "agent": "AuditorAgent",
        "action": "Independent verification & strict grading",
        "status": status,
        "details": details
    })

    if not evaluation["passed"]:
        state.is_blocked = True
        state.error_message = f"Strict Teacher Gate: Score {score}/100 below 95.0 threshold. Issues: {'; '.join(evaluation['feedback'])}"

    return state
