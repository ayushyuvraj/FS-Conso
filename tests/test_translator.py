"""Automated tests for FX Translation & FCTR Balancing (Ind AS 21)."""

import pytest
from pathlib import Path
from fs_conso.config import config
from fs_conso.core.loader import ConsoMasterLoader
from fs_conso.core.translator import FXTranslationEngine
from fs_conso.models.trial_balance import StandardizedRow, StandardizedTrialBalance

def test_fx_translation_and_fctr_plug():
    conso_path = config.project_root / "Conso.xlsx"
    coa = ConsoMasterLoader.load_coa(conso_path)
    fx_table = ConsoMasterLoader.load_default_fx_rates()
    engine = FXTranslationEngine(coa, fx_table)

    # Sub 2 in USD: Assets at Closing (83.5), Expenses at Average (83.0), Equity at Historical (80.0)
    std_rows = [
        StandardizedRow(account_code="A110101", account_description="Land", amount=1000.0, entity_code="Sub_USD", currency="USD"),
        StandardizedRow(account_code="540000", account_description="Employee Exp", amount=500.0, entity_code="Sub_USD", currency="USD"),
        StandardizedRow(account_code="320300", account_description="Trade Payables", amount=-500.0, entity_code="Sub_USD", currency="USD"),
        StandardizedRow(account_code="210100", account_description="Share Capital", amount=-1000.0, entity_code="Sub_USD", currency="USD"),
    ]
    # In USD: 1000 + 500 - 500 - 1000 = 0.00
    std_tb = StandardizedTrialBalance(entity_code="Sub_USD", period="31-Mar-2024", currency="USD", rows=std_rows)
    assert std_tb.is_tallied is True

    trans_tb = engine.translate(std_tb, reporting_currency="INR")
    # Verify exact FCTR plug was created and translated total is strictly 0.00
    assert trans_tb.fctr_row is not None
    assert trans_tb.fctr_row.account_code == "A330000"
    assert trans_tb.is_tallied is True
    assert abs(trans_tb.total_translated) < 0.01
