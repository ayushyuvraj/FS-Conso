"""Unit and integration tests for Financial Statement Builder, Cell Lineage Tracker, and Agent Tracing."""

import pytest
from fastapi.testclient import TestClient
from fs_conso.web.app import app
from fs_conso.core.aggregator import ConsolidatedTrialBalance, ConsolidatedRow
from fs_conso.core.statement_builder import FinancialStatementBuilder
from fs_conso.core.lineage_tracker import LineageTracker
from fs_conso.agent.state import ConsolidationState, AgentNodeTrace


@pytest.fixture
def sample_conso_tb():
    """Generates a balanced sample Consolidated Trial Balance."""
    return ConsolidatedTrialBalance(
        period="FY2023-24",
        currency="INR",
        entity_codes=["Company_P", "Company_S1", "Company_S2"],
        rows=[
            ConsolidatedRow(
                account_code="1001",
                account_description="Property, plant and equipment",
                entity_balances={"Company_P": 5000000.0, "Company_S1": 2000000.0, "Company_S2": 1000000.0},
                total_entities=8000000.0,
                eliminations=0.0,
                consolidated_total=8000000.0,
                formula="=SUM(C4:E4) - F4"
            ),
            ConsolidatedRow(
                account_code="1205",
                account_description="Cash and cash equivalents",
                entity_balances={"Company_P": 1500000.0, "Company_S1": 500000.0, "Company_S2": 200000.0},
                total_entities=2200000.0,
                eliminations=0.0,
                consolidated_total=2200000.0,
                formula="=SUM(C5:E5) - F5"
            ),
            ConsolidatedRow(
                account_code="3101",
                account_description="Equity share capital",
                entity_balances={"Company_P": 6000000.0, "Company_S1": 1500000.0, "Company_S2": 500000.0},
                total_entities=8000000.0,
                eliminations=0.0,
                consolidated_total=8000000.0,
                formula="=SUM(C6:E6) - F6"
            ),
            ConsolidatedRow(
                account_code="3302",
                account_description="Trade payables",
                entity_balances={"Company_P": 1200000.0, "Company_S1": 800000.0, "Company_S2": 400000.0},
                total_entities=2400000.0,
                eliminations=200000.0,
                consolidated_total=2200000.0,
                formula="=SUM(C7:E7) - F7"
            ),
            ConsolidatedRow(
                account_code="4101",
                account_description="Revenue from operations",
                entity_balances={"Company_P": 9000000.0, "Company_S1": 4000000.0, "Company_S2": 2000000.0},
                total_entities=15000000.0,
                eliminations=500000.0,
                consolidated_total=14500000.0,
                formula="=SUM(C8:E8) - F8"
            ),
            ConsolidatedRow(
                account_code="5101",
                account_description="Cost of materials consumed",
                entity_balances={"Company_P": 4500000.0, "Company_S1": 2000000.0, "Company_S2": 1000000.0},
                total_entities=7500000.0,
                eliminations=500000.0,
                consolidated_total=7000000.0,
                formula="=SUM(C9:E9) - F9"
            ),
        ],
        total_consolidated=0.0
    )


def test_financial_statement_builder_bs(sample_conso_tb):
    """Verifies IND AS Consolidated Balance Sheet generation and balance check."""
    bs = FinancialStatementBuilder.build_balance_sheet(sample_conso_tb)
    assert bs is not None
    assert "rows" in bs
    assert "columns" in bs
    assert "Company_P" in bs["columns"]
    assert "Total Entities" in bs["columns"]
    assert "Consolidated Net" in bs["columns"]

    # Check Total Assets == Total Equity and Liabilities
    total_assets_row = next((r for r in bs["rows"] if r["tag"] == "TOTAL_ASSETS"), None)
    total_eq_liab_row = next((r for r in bs["rows"] if r["tag"] == "TOTAL_EQUITY_LIAB"), None)

    assert total_assets_row is not None
    assert total_eq_liab_row is not None
    # 8,000,000 (PPE) + 2,200,000 (Cash) = 10,200,000
    assert total_assets_row["values"]["consolidated_net"] == 10200000.0
    # 8,000,000 (Equity) + 2,200,000 (Payables) = 10,200,000
    assert total_eq_liab_row["values"]["consolidated_net"] == 10200000.0
    assert bs["is_balanced"] is True


def test_financial_statement_builder_pl(sample_conso_tb):
    """Verifies IND AS Consolidated Statement of Profit & Loss calculation."""
    pl = FinancialStatementBuilder.build_profit_and_loss(sample_conso_tb)
    assert pl is not None
    assert len(pl["rows"]) > 0

    rev_row = next((r for r in pl["rows"] if r["tag"] == "REV_OPS"), None)
    exp_row = next((r for r in pl["rows"] if r["tag"] == "OP_EXP"), None)
    pbt_row = next((r for r in pl["rows"] if r["tag"] == "PBT"), None)

    assert rev_row is not None
    assert exp_row is not None
    assert pbt_row is not None
    assert rev_row["values"]["consolidated_net"] == 14500000.0
    assert exp_row["values"]["consolidated_net"] == 7000000.0
    # PBT = Revenue - Expenses = 14,500,000 - 7,000,000 = 7,500,000
    assert pbt_row["values"]["consolidated_net"] == 7500000.0


def test_lineage_tracker_query(sample_conso_tb):
    """Verifies multi-tier lineage resolution for cash and payables."""
    state = ConsolidationState(
        consolidated_tb=sample_conso_tb,
        audit_trail=[
            {"timestamp": "2026-11-24T00:00:00", "stage": "Ingestion", "agent": "ValidatorAgent", "action": "Validated", "status": "PASSED"}
        ]
    )

    # Test exact cash query
    cash_res = LineageTracker.trace_account("Cash and cash equivalents", state)
    assert cash_res["found"] is True
    assert cash_res["target"]["account_code"] == "1205"
    assert len(cash_res["lineage_graph"]) >= 4

    # Check tiers exist
    tiers = [node["tier"] for node in cash_res["lineage_graph"]]
    assert 1 in tiers  # Raw TB
    assert 2 in tiers  # Ind AS 21 FX
    assert 4 in tiers  # Consolidated TB
    assert 5 in tiers  # Statement schedule


def test_api_agent_traces_and_audit_export():
    """Verifies FastAPI endpoints for agent traces, statements, and audit export."""
    client = TestClient(app)

    # Status endpoint includes total_agent_traces
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "total_agent_traces" in status_data

    # Agent traces endpoint
    res_traces = client.get("/api/agent-traces")
    assert res_traces.status_code == 200
    traces_data = res_traces.json()
    assert "traces" in traces_data
    assert "total_nodes_executed" in traces_data

    # Lineage endpoint
    res_lineage = client.get("/api/lineage/Cash")
    assert res_lineage.status_code == 200
    lineage_data = res_lineage.json()
    assert lineage_data["found"] is True

    # Audit export JSON
    res_export_json = client.get("/api/audit-trail/export?format=json")
    assert res_export_json.status_code == 200
    assert "application/json" in res_export_json.headers["content-type"]

    # Audit export CSV
    res_export_csv = client.get("/api/audit-trail/export?format=csv")
    assert res_export_csv.status_code == 200
    assert "text/csv" in res_export_csv.headers["content-type"]


def test_observability_section_and_telemetry():
    """Verifies observability telemetry fields and UI two-section architecture."""
    client = TestClient(app)

    # 1. Telemetry in /api/status
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "token_usage" in status_data
    assert "prompt_tokens" in status_data["token_usage"]
    assert "completion_tokens" in status_data["token_usage"]
    assert "total_tokens" in status_data["token_usage"]
    assert "halted_node" in status_data
    assert "halted_stage" in status_data
    assert "remediation_items" in status_data
    assert isinstance(status_data["remediation_items"], list)

    # 2. Telemetry in /api/pipeline-data
    res_pipe = client.get("/api/pipeline-data")
    assert res_pipe.status_code == 200
    pipe_data = res_pipe.json()
    assert "token_usage" in pipe_data
    assert "halted_node" in pipe_data
    assert "remediation_items" in pipe_data

    # 3. Two-Section Architecture in index.html (6 steps in pipeline, no Step 7 in stepper)
    res_index = client.get("/")
    assert res_index.status_code == 200
    html = res_index.text
    assert 'id="nav-btn-run"' in html
    assert 'id="nav-btn-audit"' in html
    assert 'id="view-pipeline-run"' in html
    assert 'id="view-observability"' in html
    assert 'id="step-btn-6"' in html
    assert 'id="step-btn-7"' not in html

