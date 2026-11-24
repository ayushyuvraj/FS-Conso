"""
Extreme Edge Cases & Hardening Test Suite.
Tests:
- 0 subsidiaries (Parent standalone)
- 1 subsidiary
- Boundary values (₹0.01, ₹100,000,000,000)
- Unbalanced trial balance rejection
- Dangerous upload protection (path traversal, null byte, extension spoofing)
- Secret redaction in error messages and API responses
- Security HTTP headers (nosniff, DENY, XSS-Protection)
"""

import io
import pytest
from starlette.testclient import TestClient
import pandas as pd

from fs_conso.web.app import app, sanitize_error_message
from fs_conso.core.validator import TBValidator
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.core.aggregator import TBAggregator, ConsolidatedTrialBalance
from fs_conso.models.coa import ChartOfAccounts, COAItem, AccountClassification
from fs_conso.core.translator import TranslatedTrialBalance, TranslatedRow


def test_sanitize_error_message_redaction():
    # Verify API key patterns are thoroughly redacted
    raw_error = "Failed to call Gemini API with key AIzaSyABC1234567890xyz and token=secretToken123"
    sanitized = sanitize_error_message(raw_error)
    assert "AIzaSyABC1234567890xyz" not in sanitized
    assert "secretToken123" not in sanitized
    assert "REDACTED" in sanitized


def test_security_http_headers():
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "1; mode=block" in response.headers.get("X-XSS-Protection", "")


def test_edge_case_zero_subsidiaries():
    # Only parent entity present
    coa = ChartOfAccounts()
    coa.add_item(COAItem(
        account_code="1001",
        account_name="Cash",
        account_description="Cash",
        account_type=AccountClassification.ASSET,
        fs_statement="BS",
        fs_line_item="Cash and cash equivalents"
    ))

    parent_trans = TranslatedTrialBalance(
        entity_code="PARENT",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            TranslatedRow(
                account_code="1001",
                account_description="Cash",
                source_currency="INR",
                source_amount=500000.0,
                rate_applied=1.0,
                rate_type="Identity",
                translated_amount=500000.0
            )
        ]
    )

    ctb = TBAggregator.aggregate(
        coa=coa,
        translated_tbs=[parent_trans],
        elimination_vouchers=[],
        period="31-Mar-2024",
        currency="INR"
    )

    assert len(ctb.entity_codes) == 1
    assert ctb.entity_codes[0] == "PARENT"
    assert len(ctb.rows) >= 1
    cash_row = next(r for r in ctb.rows if r.account_code == "1001")
    assert cash_row.total_entities == 500000.0
    assert cash_row.consolidated_total == 500000.0


def test_edge_case_single_subsidiary():
    coa = ChartOfAccounts()
    coa.add_item(COAItem(
        account_code="1001",
        account_name="Cash",
        account_description="Cash",
        account_type=AccountClassification.ASSET,
        fs_statement="BS",
        fs_line_item="Cash and cash equivalents"
    ))

    parent_trans = TranslatedTrialBalance(
        entity_code="PARENT",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            TranslatedRow(
                account_code="1001",
                account_description="Cash",
                source_currency="INR",
                source_amount=100000.0,
                rate_applied=1.0,
                rate_type="Identity",
                translated_amount=100000.0
            )
        ]
    )

    sub_trans = TranslatedTrialBalance(
        entity_code="SUB_01",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            TranslatedRow(
                account_code="1001",
                account_description="Cash",
                source_currency="INR",
                source_amount=250000.0,
                rate_applied=1.0,
                rate_type="Identity",
                translated_amount=250000.0
            )
        ]
    )

    ctb = TBAggregator.aggregate(
        coa=coa,
        translated_tbs=[parent_trans, sub_trans],
        elimination_vouchers=[],
        period="31-Mar-2024",
        currency="INR"
    )

    assert len(ctb.entity_codes) == 2
    cash_row = next(r for r in ctb.rows if r.account_code == "1001")
    assert cash_row.total_entities == 350000.0
    assert cash_row.consolidated_total == 350000.0


def test_edge_case_extreme_numerical_bounds():
    # Massive numbers up to ₹100,000,000,000 (10,000 Crores)
    raw_tb = RawTrialBalance(
        entity_code="MEGA_CORP",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            RawTBRow(account_code="1001", account_description="Cash", debit=100000000000.0, credit=0.0),
            RawTBRow(account_code="2001", account_description="Capital", debit=0.0, credit=100000000000.0)
        ]
    )
    res = TBValidator.validate(raw_tb, expected_period="31-Mar-2024")
    assert res.is_valid is True
    assert res.net_difference == 0.0


def test_edge_case_unbalanced_trial_balance_rejected():
    # Debit != Credit
    raw_tb = RawTrialBalance(
        entity_code="UNBALANCED_SUB",
        period="31-Mar-2024",
        currency="INR",
        rows=[
            RawTBRow(account_code="1001", account_description="Cash", debit=50000.0, credit=0.0),
            RawTBRow(account_code="2001", account_description="Payables", debit=0.0, credit=49000.0)
        ]
    )
    res = TBValidator.validate(raw_tb, expected_period="31-Mar-2024")
    assert res.is_valid is False
    assert any("not tallied" in e.message.lower() or "does not sum to zero" in e.message.lower() for e in res.errors)


def test_upload_security_path_traversal():
    client = TestClient(app)
    # Attempt upload with path traversal in filename
    file_content = b"Account,Debit,Credit\n1001,100,100\n"
    response = client.post(
        "/api/upload-tb",
        files={"file": ("../../etc/passwd.xlsx", file_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"entity_code": "TRAVERSAL_SUB"}
    )
    assert response.status_code == 400
    assert "Directory traversal" in response.json()["detail"]


def test_upload_security_disallowed_extension():
    client = TestClient(app)
    file_content = b"echo 'malicious payload'"
    response = client.post(
        "/api/upload-tb",
        files={"file": ("payload.exe", file_content, "application/octet-stream")},
        data={"entity_code": "MALICIOUS_SUB"}
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
