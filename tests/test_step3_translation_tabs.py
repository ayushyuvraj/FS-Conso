import pytest
from fastapi.testclient import TestClient
from fs_conso.web.app import app
from fs_conso.models.coa import ChartOfAccounts, COAItem, AccountClassification
from fs_conso.models.fx import FXRateEntry, FXRateTable
from fs_conso.models.trial_balance import StandardizedRow, StandardizedTrialBalance
from fs_conso.core.translator import FXTranslationEngine, TranslatedTrialBalance, TranslatedRow


def test_fx_engine_5_category_rates_and_fctr():
    # 1. Create a COA with all 5 types
    coa = ChartOfAccounts(items={
        "A100": COAItem(account_code="A100", account_name="Cash & Bank", level_0_account="Cash", account_type=AccountClassification.ASSET),
        "L200": COAItem(account_code="L200", account_name="Trade Payables", level_0_account="Payables", account_type=AccountClassification.LIABILITY),
        "E300": COAItem(account_code="E300", account_name="Share Capital", level_0_account="Capital", account_type=AccountClassification.EQUITY),
        "R400": COAItem(account_code="R400", account_name="Revenue", level_0_account="Revenue", account_type=AccountClassification.INCOME),
        "X500": COAItem(account_code="X500", account_name="Salaries", level_0_account="Salaries", account_type=AccountClassification.EXPENSE),
    })

    # 2. FX Rate Table: USD -> INR (Closing: 95.0, Average: 98.0, Historical: 90.0)
    fx_table = FXRateTable()
    fx_table.add_rate(FXRateEntry(from_currency="USD", to_currency="INR", closing_rate=95.0, average_rate=98.0, historical_rate=90.0))

    engine = FXTranslationEngine(coa, fx_table)

    # 3. Standardized TB in USD
    std_tb = StandardizedTrialBalance(
        entity_code="SUB_B",
        period="2025-03-31",
        currency="USD",
        rows=[
            StandardizedRow(account_code="A100", account_description="Cash & Bank", amount=100.0, entity_code="SUB_B", currency="USD"),
            StandardizedRow(account_code="L200", account_description="Trade Payables", amount=-40.0, entity_code="SUB_B", currency="USD"),
            StandardizedRow(account_code="E300", account_description="Share Capital", amount=-30.0, entity_code="SUB_B", currency="USD"),
            StandardizedRow(account_code="R400", account_description="Revenue", amount=-50.0, entity_code="SUB_B", currency="USD"),
            StandardizedRow(account_code="X500", account_description="Salaries", amount=20.0, entity_code="SUB_B", currency="USD"),
        ]
    )

    # 4. Translate
    trans_tb = engine.translate(std_tb, reporting_currency="INR")
    assert trans_tb.entity_code == "SUB_B"
    assert trans_tb.source_currency == "USD"
    assert trans_tb.reporting_currency == "INR"

    # Check categories & applied rates
    row_map = {r.account_code: r for r in trans_tb.rows}
    assert row_map["A100"].category == "Asset"
    assert row_map["A100"].rate_applied == 95.0
    assert row_map["A100"].rate_type == "Closing"
    assert row_map["A100"].translated_amount == 9500.0

    assert row_map["L200"].category == "Liability"
    assert row_map["L200"].rate_applied == 95.0
    assert row_map["L200"].rate_type == "Closing"
    assert row_map["L200"].translated_amount == -3800.0

    assert row_map["E300"].category == "Equity"
    assert row_map["E300"].rate_applied == 90.0
    assert row_map["E300"].rate_type == "Historical"
    assert row_map["E300"].translated_amount == -2700.0

    assert row_map["R400"].category == "Income"
    assert row_map["R400"].rate_applied == 98.0
    assert row_map["R400"].rate_type == "Average"
    assert row_map["R400"].translated_amount == -4900.0

    assert row_map["X500"].category == "Expense"
    assert row_map["X500"].rate_applied == 98.0
    assert row_map["X500"].rate_type == "Average"
    assert row_map["X500"].translated_amount == 1960.0

    # Subtotal before FCTR: 9500 - 3800 - 2700 - 4900 + 1960 = 60.0
    # Expected FCTR plug: -60.0
    assert trans_tb.fctr_row is not None
    assert trans_tb.fctr_row.is_fctr_plug is True
    assert trans_tb.fctr_row.category == "Equity"
    assert trans_tb.fctr_row.rate_type == "FCTR_Plug"
    assert trans_tb.fctr_row.translated_amount == -60.0
    assert trans_tb.is_tallied is True
    assert trans_tb.total_translated == 0.00


def test_fx_identity_translation():
    coa = ChartOfAccounts(items={
        "A100": COAItem(account_code="A100", account_name="Cash", level_0_account="Cash", account_type=AccountClassification.ASSET),
    })
    engine = FXTranslationEngine(coa)
    std_tb = StandardizedTrialBalance(
        entity_code="PARENT",
        period="2025-03-31",
        currency="INR",
        rows=[StandardizedRow(account_code="A100", account_description="Cash", amount=1000.0, entity_code="PARENT", currency="INR")]
    )
    trans = engine.translate(std_tb, reporting_currency="INR")
    assert trans.source_currency == "INR"
    assert trans.rows[0].rate_applied == 1.0
    assert trans.rows[0].rate_type == "Identity"
    assert trans.fctr_row is None


def test_pipeline_data_returns_full_translated_rows():
    client = TestClient(app)
    res = client.get("/api/pipeline-data")
    assert res.status_code == 200
    data = res.json()
    trans_tbs = data.get("translated_tbs", [])
    if trans_tbs:
        for tb in trans_tbs:
            assert "source_currency" in tb
            assert "currency" in tb
            assert "total_translated" in tb
            assert "has_fctr" in tb
            assert isinstance(tb["rows"], list)
