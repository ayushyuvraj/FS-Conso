"""Automated test verifying 100% Excel cell formula provenance."""

import pytest
from pathlib import Path
import openpyxl
from fs_conso.config import config

def test_100_percent_formula_integrity():
    excel_path = config.outputs_dir / "Consolidated_Financial_Statements.xlsx"
    assert excel_path.exists(), "Consolidated_Financial_Statements.xlsx must exist before testing."

    wb = openpyxl.load_workbook(excel_path, data_only=False)
    downstream_sheets = ["Translated_TB", "IC_Eliminations", "Consolidated_TB", "Balance_Sheet", "Profit_and_Loss"]

    calc_cols = {
        "Translated_TB": [5, 6, 7],
        "IC_Eliminations": [5, 6, 7],
        "Consolidated_TB": None,
        "Balance_Sheet": None,
        "Profit_and_Loss": None
    }

    total_calc_cells = 0
    formula_cells = 0
    hardcoded_cells = []

    for s_name in downstream_sheets:
        assert s_name in wb.sheetnames, f"Sheet '{s_name}' is missing from workbook."
        ws = wb[s_name]
        cols = calc_cols.get(s_name) or list(range(3, ws.max_column + 1))

        for r in range(4, ws.max_row + 1):
            for c in cols:
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
                    hardcoded_cells.append((s_name, ws.cell(r, c).coordinate, val))

    wb.close()

    assert total_calc_cells > 0, "No calculated cells found to audit."
    assert len(hardcoded_cells) == 0, f"Found hardcoded numbers in downstream sheets: {hardcoded_cells[:5]}"
    assert formula_cells == total_calc_cells, f"Formula integrity violated: {formula_cells}/{total_calc_cells} cells contain formulas."
