"""Unit tests for FlexibleTBParser, Security Gates, and Production Hardening."""

import io
import math
import pytest
import pandas as pd
from pydantic import ValidationError

from fs_conso.config import config, AppConfig
from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.core.validator import TBValidator
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance
from fs_conso.web.app import SettingsUpdate, sanitize_error_message


def test_flexible_tb_parser_number_cleaning():
    """Verifies that clean_number correctly parses messy currency strings and nil symbols."""
    # Nil balances in accounting represent 0.00
    assert FlexibleTBParser.clean_number("-") == 0.0
    assert FlexibleTBParser.clean_number("—") == 0.0
    assert FlexibleTBParser.clean_number("--") == 0.0
    assert FlexibleTBParser.clean_number("nil") == 0.0
    assert FlexibleTBParser.clean_number("NIL") == 0.0
    assert FlexibleTBParser.clean_number("0") == 0.0
    assert FlexibleTBParser.clean_number("0.00") == 0.0

    # True blanks represent missing data
    assert FlexibleTBParser.clean_number(None) is None
    assert FlexibleTBParser.clean_number("") is None
    assert FlexibleTBParser.clean_number("   ") is None
    assert FlexibleTBParser.clean_number("nan") is None

    # Dirty numbers with currencies, spaces, commas
    assert FlexibleTBParser.clean_number("₹ 1,23,456.78") == 123456.78
    assert FlexibleTBParser.clean_number("$ 5,000,000.00") == 5000000.00
    assert FlexibleTBParser.clean_number("€ 42.50") == 42.50
    assert FlexibleTBParser.clean_number("£ 10.00") == 10.00

    # Negative formats: parentheses and trailing minus
    assert FlexibleTBParser.clean_number("(50,000.00)") == -50000.00
    assert FlexibleTBParser.clean_number("1,200.50-") == -1200.50
    assert FlexibleTBParser.clean_number("2,500.00 CR") == -2500.00
    assert FlexibleTBParser.clean_number("2,500.00 DR") == 2500.00


def test_flexible_tb_parser_header_detection_and_summary_skip():
    """Verifies parser finds headers offset by blank/title rows and skips summary rows."""
    data = [
        ["Sample Conglomerate Entity", "", ""],
        ["Trial Balance as of 31-Mar-2024", "", ""],
        ["GL Account", "Description", "Closing Balance"],  # Actual header at row 2
        ["1001", "Cash at Bank", "50,000.00"],
        ["2001", "Trade Payables", "-50,000.00"],
        ["Total", "Grand Total", "0.00"]  # Summary row to be ignored
    ]
    df = pd.DataFrame(data)

    parsed = FlexibleTBParser.parse_dataframe(df, entity_code="TEST_CO")
    assert len(parsed.rows) == 2
    assert parsed.rows[0].account_code == "1001"
    assert parsed.rows[0].amount == 50000.00
    assert parsed.rows[1].account_code == "2001"
    assert parsed.rows[1].amount == -50000.00
    assert parsed.total_signed_amount == 0.0


def test_validator_empty_tb_and_numeric_safety():
    """Verifies TBValidator rejects empty submissions, negative debits, and non-finite values."""
    # 1. Empty TB
    empty_tb = RawTrialBalance(entity_code="EMPTY_CO", period="31-Mar-2024", currency="INR", rows=[])
    val_empty = TBValidator.validate(empty_tb)
    assert not val_empty.is_valid
    assert any(e.error_code == "EMPTY_TRIAL_BALANCE" for e in val_empty.errors)

    # 2. Negative Debit in double-entry column
    neg_tb = RawTrialBalance(
        entity_code="TEST_CO",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            RawTBRow(account_code="101", debit=-500.0, credit=0.0),
            RawTBRow(account_code="102", debit=500.0, credit=0.0),
        ]
    )
    val_neg = TBValidator.validate(neg_tb)
    assert not val_neg.is_valid
    assert any(e.error_code == "NEGATIVE_DEBIT" for e in val_neg.errors)

    # 3. Non-finite (NaN)
    nan_tb = RawTrialBalance(
        entity_code="TEST_CO",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            RawTBRow(account_code="101", debit=float("nan"), credit=0.0),
        ]
    )
    val_nan = TBValidator.validate(nan_tb)
    assert not val_nan.is_valid
    assert any(e.error_code == "INVALID_NUMERIC_DEBIT" for e in val_nan.errors)


def test_settings_validation_nan_and_bounds():
    """Verifies SettingsUpdate rejects NaN, Inf, and out-of-range values."""
    with pytest.raises(ValidationError):
        SettingsUpdate(ai_confidence_threshold=float("nan"))

    with pytest.raises(ValidationError):
        SettingsUpdate(ai_confidence_threshold=1.5)  # Must be <= 1.0

    with pytest.raises(ValidationError):
        SettingsUpdate(ic_absolute_tolerance=-10.0)  # Must be >= 0.0

    with pytest.raises(ValidationError):
        SettingsUpdate(gemini_api_key="AIzaSy\nInjected")  # Control characters rejected


def test_config_api_key_masking_and_repr():
    """Verifies that API keys are masked and never printed in repr."""
    cfg = AppConfig(gemini_api_key="AIzaSy1234567890abcdefghijklmnopqrstuvwxyz")
    assert cfg.get_masked_api_key() == "AIzaSy...wxyz"
    assert "AIzaSy1234567890abcdefghijklmnopqrstuvwxyz" not in repr(cfg)


def test_config_api_key_env_persistence(tmp_path, monkeypatch):
    """Verifies that set_api_key_secure safely writes to .env and unsets when cleared."""
    import dotenv
    test_env = tmp_path / ".env"
    monkeypatch.setattr("fs_conso.config.ENV_PATH", test_env)

    cfg = AppConfig(gemini_api_key="")
    test_key = "AIzaSy" + "K" * 30
    cfg.set_api_key_secure(test_key, persist_to_env=True)

    assert test_env.exists()
    content = test_env.read_text(encoding="utf-8")
    assert test_key in content
    assert dotenv.get_key(str(test_env), "GEMINI_API_KEY") == test_key

    # Clearing the key should unset it
    cfg.set_api_key_secure("", persist_to_env=True)
    cleared_content = test_env.read_text(encoding="utf-8")
    assert test_key not in cleared_content
    assert dotenv.get_key(str(test_env), "GEMINI_API_KEY") is None


def test_sanitize_error_message():
    """Verifies that error messages redact any embedded API keys."""
    raw_error = "Failed to connect to https://generativelanguage.googleapis.com?key=AIzaSySecretTestKey123456789"
    sanitized = sanitize_error_message(raw_error)
    assert "AIzaSySecretTestKey123456789" not in sanitized
    assert "[REDACTED]" in sanitized
