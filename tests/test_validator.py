"""Automated tests for Trial Balance Validation Engine."""

import pytest
from fs_conso.core.validator import TBValidator
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance

def test_balanced_two_column_tb():
    rows = [
        RawTBRow(account_code="1000", account_description="Cash", debit=1000.0, credit=0.0),
        RawTBRow(account_code="2000", account_description="Payable", debit=0.0, credit=1000.0),
    ]
    tb = RawTrialBalance(entity_code="E1", period="31-Mar-2024", currency="INR", rows=rows)
    res = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="E1")
    assert res.is_valid is True
    assert len(res.errors) == 0

def test_unbalanced_two_column_tb():
    rows = [
        RawTBRow(account_code="1000", account_description="Cash", debit=1000.0, credit=0.0),
        RawTBRow(account_code="2000", account_description="Payable", debit=0.0, credit=800.0),
    ]
    tb = RawTrialBalance(entity_code="E1", period="31-Mar-2024", currency="INR", rows=rows)
    res = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="E1")
    assert res.is_valid is False
    assert any(e.error_code == "UNBALANCED_TB_TWO_COL" for e in res.errors)

def test_blank_vs_zero_distinction():
    rows = [
        RawTBRow(account_code="1000", account_description="Cash", debit=None, credit=None, amount=None), # Blank
        RawTBRow(account_code="2000", account_description="Payable", debit=0.0, credit=0.0), # Zero (valid nil)
    ]
    tb = RawTrialBalance(entity_code="E1", period="31-Mar-2024", currency="INR", rows=rows)
    res = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="E1")
    assert res.is_valid is False
    assert any(e.error_code == "MISSING_DATA_BLANK" for e in res.errors)

def test_period_and_entity_mismatch():
    rows = [RawTBRow(account_code="1000", account_description="Cash", debit=500.0, credit=500.0)]
    tb = RawTrialBalance(entity_code="E1", period="30-Apr-2024", currency="INR", rows=rows)
    res = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="E2")
    assert res.is_valid is False
    assert any(e.error_code == "PERIOD_MISMATCH" for e in res.errors)
    assert any(e.error_code == "ENTITY_MISMATCH" for e in res.errors)
