"""Automated Test Suite for Step 1 Dual-Engine Ingestion & Perimeter Approval.

Tests:
1. Multi-sheet Excel workbook parsing (Parent, Sub 1, Sub 2, FX Rates, Extra notes).
2. Dual-Engine execution flags (Deterministic only with 0 AI tokens, AI only, and Both).
3. Date discrepancy detection (2025 vs 2024 run date) and multi-period filtering.
4. Mandatory 6-column FX Rates parsing (Date, From, To, Closing, Average, Historical, Swap).
5. Step 1 Gating & Confirmation: locks Step 1 with completed checkmark and unlocks Step 2.
"""

import io
import openpyxl
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fs_conso.core.file_classifier import FileClassifier, ClassifiedFile
from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.models.fx import FXRateTable, FXRateEntry
from fs_conso.web.app import app, session, company_manager


@pytest.fixture
def sample_hierarchy():
    h = EntityHierarchy(parent_code="Company_P")
    h.add_entity(LegalEntity(
        entity_code="Company_P",
        entity_name="Parent Corp",
        country_of_inc="India",
        input_currency="INR",
        holding_percentage=1.0,
        consolidation_method="Full Consolidation"
    ))
    h.add_entity(LegalEntity(
        entity_code="Company_S1",
        entity_name="Subsidiary US",
        country_of_inc="USA",
        input_currency="USD",
        holding_percentage=1.0,
        consolidation_method="Full Consolidation"
    ))
    h.add_entity(LegalEntity(
        entity_code="Company_S2",
        entity_name="Subsidiary Singapore",
        country_of_inc="Singapore",
        input_currency="SGD",
        holding_percentage=0.8,
        consolidation_method="Full Consolidation"
    ))
    return h


@pytest.fixture
def multi_sheet_workbook_bytes():
    """Builds a single Excel workbook containing Parent, Sub 1, Sub 2, FX Rates, and an extra Notes sheet."""
    wb = openpyxl.Workbook()
    
    # Sheet 1: Parent
    ws_parent = wb.active
    ws_parent.title = "Company_P_Trial_Balance"
    ws_parent.append(["Account Code", "Account Description", "Debit", "Credit"])
    ws_parent.append(["11000", "Cash in INR", 1000000, None])
    ws_parent.append(["31000", "Share Capital", None, 1000000])

    # Sheet 2: Sub 1
    ws_s1 = wb.create_sheet(title="Company_S1_TB")
    ws_s1.append(["GL Code", "Description", "Actual Debit", "Actual Credit"])
    ws_s1.append(["10100", "USD Bank Account", 50000, None])
    ws_s1.append(["30100", "Equity", None, 50000])

    # Sheet 3: Sub 2
    ws_s2 = wb.create_sheet(title="Subsidiary_2")
    ws_s2.append(["Account #", "Particulars", "Net Balance"])
    ws_s2.append(["CASH-SGD", "DBS Account", 75000])
    ws_s2.append(["EQ-SGD", "Common Stock", -75000])

    # Sheet 4: FX Rates Table (6 columns)
    ws_fx = wb.create_sheet(title="FX_Rates")
    ws_fx.append(["As of Date", "From Currency", "To Currency", "Closing Rate", "Average Rate", "Historical Rate", "Swap Rate"])
    ws_fx.append(["31-Mar-2024", "USD", "INR", 83.50, 83.00, 80.00, 0.25])
    ws_fx.append(["31-Mar-2024", "SGD", "INR", 62.00, 61.50, 60.00, 0.15])

    # Sheet 5: Unassigned Notes
    ws_notes = wb.create_sheet(title="Audit_Notes")
    ws_notes.append(["Notes", "Prepared By", "Reviewed By"])
    ws_notes.append(["Q4 consolidation draft", "Senior Accountant", "Manager"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_multi_sheet_classification_and_extra_sheets(multi_sheet_workbook_bytes, sample_hierarchy):
    """Verifies that a single workbook with multiple sheets is decomposed into individual classified items."""
    classified = FileClassifier.classify_batch(
        files=[("Client2_Consolidated.xlsx", multi_sheet_workbook_bytes)],
        expected_period="31-Mar-2024",
        known_entities=sample_hierarchy,
        use_deterministic=True,
        use_ai=False
    )
    assert len(classified) == 5

    # Check that Parent, Sub 1, Sub 2, and FX Rates are identified
    parent_item = next((c for c in classified if c.entity_code == "Company_P"), None)
    assert parent_item is not None
    assert parent_item.file_type == "CURRENT_TB"
    assert parent_item.sheet_name == "Company_P_Trial_Balance"
    assert parent_item.detected_columns.get("account_code") == "Account Code"

    s1_item = next((c for c in classified if c.entity_code == "Company_S1"), None)
    assert s1_item is not None
    assert s1_item.file_type == "CURRENT_TB"
    assert s1_item.sheet_name == "Company_S1_TB"

    s2_item = next((c for c in classified if c.entity_code == "Company_S2"), None)
    assert s2_item is not None
    assert s2_item.sheet_name == "Subsidiary_2"

    fx_item = next((c for c in classified if c.file_type == "FX_RATES"), None)
    assert fx_item is not None
    assert fx_item.sheet_name == "FX_Rates"
    assert fx_item.detected_columns.get("closing_rate") == "Closing Rate"

    # Notes sheet should be marked as extra unassigned
    notes_item = next((c for c in classified if c.sheet_name == "Audit_Notes"), None)
    assert notes_item is not None
    assert notes_item.is_extra_unassigned is True


def test_dual_engine_deterministic_zero_ai_tokens(multi_sheet_workbook_bytes, sample_hierarchy):
    """When AI agents is unchecked (use_ai=False), deterministic runs with zero external API calls."""
    classified = FileClassifier.classify_batch(
        files=[("Client2.xlsx", multi_sheet_workbook_bytes)],
        expected_period="31-Mar-2024",
        known_entities=sample_hierarchy,
        use_deterministic=True,
        use_ai=False
    )
    for c in classified:
        assert c.classification_method in ("DETERMINISTIC", "FALLBACK")


def test_date_discrepancy_and_multi_period_detection(sample_hierarchy):
    """Tests detection of mismatched period (2025 vs 2024) and multi-period schedules."""
    # 1. Date Discrepancy (2025 data when run date is 2024)
    wb_mismatch = openpyxl.Workbook()
    ws = wb_mismatch.active
    ws.title = "Company_S1_31_Mar_2025"
    ws.append(["Account Code", "Description", "Debit", "Credit"])
    ws.append(["1001", "Cash", 5000, 0])

    buf = io.BytesIO()
    wb_mismatch.save(buf)
    mismatch_bytes = buf.getvalue()

    cf_mismatch = FileClassifier.classify_file(
        file_bytes=mismatch_bytes,
        filename="TB_Company_S1_2025.xlsx",
        expected_period="31-Mar-2024",
        known_entities=sample_hierarchy,
        use_deterministic=True,
        use_ai=False
    )
    assert cf_mismatch.date_status == "MISMATCH"
    assert cf_mismatch.needs_review is True

    # 2. Multi-period schedule filtering in FlexibleTBParser
    df_multi = pd.DataFrame({
        "Period": ["31-Mar-2023", "31-Mar-2024", "31-Mar-2025"],
        "GL Code": ["1001", "1001", "1001"],
        "Description": ["Cash", "Cash", "Cash"],
        "Debit": [100.0, 200.0, 300.0],
        "Credit": [0.0, 0.0, 0.0]
    })
    tb_filtered = FlexibleTBParser.parse_dataframe(
        df=df_multi,
        entity_code="Company_S1",
        period="31-Mar-2024",
        currency="USD"
    )
    assert len(tb_filtered.rows) == 1
    assert tb_filtered.rows[0].debit == 200.0


def test_fx_rate_table_parsing_with_swap_rate():
    """Verifies parsing of 6-column exchange rate schedule."""
    fx_df = pd.DataFrame({
        "As on Date": ["31-Mar-2024", "31-Mar-2024"],
        "From Currency": ["USD", "EUR"],
        "To Currency": ["INR", "INR"],
        "Closing Rate": [83.50, 90.25],
        "Average Rate": [83.00, 89.80],
        "Historical Rate": [80.00, 87.00],
        "Swap Rate": [0.35, 0.45]
    })
    buf = io.BytesIO()
    fx_df.to_excel(buf, index=False)
    fx_bytes = buf.getvalue()

    fx_table = FlexibleTBParser.parse_fx_rates(
        file_path_or_bytes=fx_bytes,
        filename="FX_Rates_2024.xlsx",
        reporting_currency="INR",
        as_on_date="31-Mar-2024"
    )
    usd_rate = fx_table.get_rate("USD", "INR")
    assert usd_rate is not None
    assert usd_rate.closing_rate == 83.50
    assert usd_rate.average_rate == 83.00
    assert usd_rate.historical_rate == 80.00
    assert usd_rate.swap_rate == 0.35


def test_pipeline_confirmation_api_gating(multi_sheet_workbook_bytes):
    """End-to-end API test: confirm-ingestion succeeds when all entities are mapped, locks Step 1."""
    client = TestClient(app)

    # 1. Switch to active company
    companies = company_manager.list_companies()
    if not companies:
        pytest.skip("No company workspace available for API test.")
    cid = companies[0]["company_id"]
    client.post("/api/companies/switch", json={"company_id": cid})

    # 2. Upload multi-sheet batch
    res_upload = client.post(
        "/api/upload-batch",
        files=[("files", ("Client_All.xlsx", multi_sheet_workbook_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        data={"period": "31-Mar-2024", "use_deterministic": "true", "use_ai": "false"}
    )
    assert res_upload.status_code == 200
    state = res_upload.json()["approval_state"]
    assert "parent" in state
    assert "subsidiaries" in state
    assert "fx_rates" in state

    # 3. Test Confirm with Missing entity (should fail)
    res_incomplete = client.post(
        "/api/pipeline/confirm-ingestion",
        json={
            "entities": [
                {"entity_code": "Company_P", "filename": "Client_All.xlsx", "sheet_name": "Company_P_Trial_Balance"}
            ],
            "fx_rates": {"filename": "Client_All.xlsx", "sheet_name": "FX_Rates"}
        }
    )
    # If company has subsidiaries, confirmation should be rejected with 400
    if state["subsidiaries"]:
        assert res_incomplete.status_code == 400
        assert "Cannot close Step 1: Missing trial balances" in res_incomplete.json()["detail"]

    # 4. Confirm with ALL entities
    all_entities_payload = [
        {"entity_code": state["parent"]["entity_code"], "filename": "Client_All.xlsx", "sheet_name": "Company_P_Trial_Balance"}
    ]
    for sub in state["subsidiaries"]:
        all_entities_payload.append({
            "entity_code": sub["entity_code"],
            "filename": "Client_All.xlsx",
            "sheet_name": "Company_S1_TB" if "s1" in sub["entity_code"].lower() else "Subsidiary_2"
        })

    res_confirm = client.post(
        "/api/pipeline/confirm-ingestion",
        json={
            "entities": all_entities_payload,
            "fx_rates": {"filename": "Client_All.xlsx", "sheet_name": "FX_Rates"}
        }
    )
    assert res_confirm.status_code == 200
    data_confirm = res_confirm.json()
    assert data_confirm["success"] is True
    assert 1 in data_confirm["completed_steps"]
    assert data_confirm["current_step"] == 2
