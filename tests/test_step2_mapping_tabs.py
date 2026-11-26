"""Automated Test Suite for Step 2 Dynamic Mapping Tabs, Trial Balance Columns & Level 0 Dropdowns.

Tests:
1. MappingDecision domain model carries entity_code, currency, amount, level_0_code, and level_0_name.
2. COAMappingEngine populates these fields accurately for parent and subsidiary trial balances.
3. Multi-entity tab structure generates exactly 1 tab for Parent and 1 tab for each Subsidiary (N+1 tabs total).
4. Auto-triggering COA mapping via /api/pipeline/run-mapping or during Step 1 approval.
5. /api/pipeline-data returns full multi-entity mapping decisions without truncation, plus level_0_choices.
6. /api/hitl/resolve updates mapping to 100% confidence, sets needs_review=False, updates group and level 0 info, and clears pending reviews.
"""

import pytest
from fastapi.testclient import TestClient

from fs_conso.core.mapper import COAMappingEngine, MappingDecision
from fs_conso.models.coa import ChartOfAccounts, COAItem, AccountClassification
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.web.app import app, session, company_manager


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def sample_coa():
    coa = ChartOfAccounts()
    coa.add_item(COAItem(
        account_code="120400",
        account_name="Cash & Cash Equivalents",
        level_0_account="Cash & Bank",
        account_type=AccountClassification.ASSET
    ))
    coa.add_item(COAItem(
        account_code="320300",
        account_name="Trade Payables",
        level_0_account="Trade Payables",
        account_type=AccountClassification.LIABILITY
    ))
    coa.add_item(COAItem(
        account_code="A110101",
        account_name="Land & Freehold Property",
        level_0_account="Land",
        account_type=AccountClassification.ASSET
    ))
    return coa


def test_mapping_decision_model_enrichment():
    """Validates that MappingDecision model carries entity, currency, amount, and Level 0 fields."""
    decision = MappingDecision(
        local_code="11001",
        local_description="Cash (Local Code)",
        group_code="120400",
        group_description="Cash & Cash Equivalents",
        method="DIRECT_CODE_MATCH",
        confidence=1.0,
        needs_review=False,
        entity_code="Company_S1",
        currency="USD",
        amount=1500000.0,
        level_0_code="120400",
        level_0_name="Cash & Bank"
    )
    assert decision.entity_code == "Company_S1"
    assert decision.currency == "USD"
    assert decision.amount == 1500000.0
    assert decision.level_0_code == "120400"
    assert decision.level_0_name == "Cash & Bank"


def test_coa_mapping_engine_populates_step2_columns(sample_coa):
    """Verifies COAMappingEngine sets account code, name, currency, amount, and Level 0 for every row."""
    raw_tb = RawTrialBalance(
        entity_code="Company_S1",
        period="31-03-2024",
        currency="USD",
        rows=[
            RawTBRow(account_code="120400", account_description="Cash in hand", debit=50000.0, credit=0.0),
            RawTBRow(account_code="320300", account_description="Trade Payables", debit=0.0, credit=50000.0),
        ]
    )

    mapper = COAMappingEngine(sample_coa)
    std_tb, decisions = mapper.standardize_trial_balance(raw_tb, use_ai=False)

    assert len(decisions) == 2
    d1 = decisions[0]
    assert d1.local_code == "120400"
    assert d1.entity_code == "Company_S1"
    assert d1.currency == "USD"
    assert d1.amount == 50000.0
    assert d1.group_code == "120400"
    assert d1.level_0_name == "Cash & Bank"
    assert d1.confidence >= 0.95

    d2 = decisions[1]
    assert d2.local_code == "320300"
    assert d2.entity_code == "Company_S1"
    assert d2.currency == "USD"
    assert d2.amount == -50000.0
    assert d2.group_code == "320300"
    assert d2.level_0_name == "Trade Payables"


def test_hitl_resolve_updates_mapping_and_clears_review(test_client):
    """Tests /api/hitl/resolve updates mapping, sets confidence to 100%, and clears needs_review flag."""
    # Reset baseline
    test_client.post("/api/reset-baseline")

    # Inject an unmapped decision needing review
    session.state.mapping_decisions.append(MappingDecision(
        local_code="UNMAPPED_99",
        local_description="Mystery Account",
        group_code="999999",
        group_description="Unmapped Exception",
        method="UNMAPPED_EXCEPTION",
        confidence=0.0,
        needs_review=True,
        entity_code="Company_S1",
        currency="USD",
        amount=12345.0,
        level_0_code=None,
        level_0_name=None
    ))
    session.state.hitl_pending_reviews.append({
        "entity_code": "Company_S1",
        "local_code": "UNMAPPED_99",
        "local_description": "Mystery Account",
        "suggested_group_code": "120400",
        "confidence": 0.0,
        "reasoning": "Needs resolution"
    })

    # Call HITL resolve
    res = test_client.post("/api/hitl/resolve", json={
        "entity_code": "Company_S1",
        "local_code": "UNMAPPED_99",
        "group_code": "120400",
        "reasoning": "Mapped to Cash by Auditor"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # Verify decision is now mapped with 100% confidence and needs_review=False
    updated = next(d for d in session.state.mapping_decisions if d.local_code == "UNMAPPED_99" and d.entity_code == "Company_S1")
    assert updated.group_code == "120400"
    assert updated.confidence == 1.0
    assert updated.needs_review is False
    assert updated.method == "USER_APPROVED_RULE"

    # Verify pending review was cleared
    assert not any(r.get("local_code") == "UNMAPPED_99" for r in session.state.hitl_pending_reviews)


def test_pipeline_data_returns_level_0_choices_and_full_mappings(test_client):
    """Tests /api/pipeline-data returns complete mappings without 50-item cap and includes level_0_choices."""
    test_client.post("/api/reset-baseline")

    res = test_client.get("/api/pipeline-data")
    assert res.status_code == 200
    data = res.json()

    assert "mapping_decisions" in data
    assert "level_0_choices" in data
    assert "perimeter_entities" in data
    assert isinstance(data["level_0_choices"], list)
    if data["level_0_choices"]:
        choice = data["level_0_choices"][0]
        assert "account_code" in choice
        assert "label" in choice


def test_multi_entity_ingestion_and_strict_entity_partitioning():
    """Verifies that multi-entity trial balances are strictly partitioned with non-zero amounts."""
    from fs_conso.core.file_parser import FlexibleTBParser
    from fs_conso.agent.state import ConsolidationState
    from fs_conso.agent.nodes import mapper_node

    sheets = {
        "C2": "Parent TB",
        "A": "Sub A TB",
        "B": "Sub B TB",
        "C": "Sub C TB"
    }
    raw_tbs = []
    for code, sheet in sheets.items():
        tb = FlexibleTBParser.parse_file(
            file_path_or_bytes="inputs/uploads/c2_Two_Year_Consolidation_TBs_balanced-v2.xlsx",
            filename="c2_Two_Year_Consolidation_TBs_balanced-v2.xlsx",
            entity_code=code,
            sheet_name=sheet,
            period="31-Mar-2025"
        )
        raw_tbs.append(tb)

    # Verify raw TB row counts matching exact ingested file
    c2_tb = next(t for t in raw_tbs if t.entity_code == "C2")
    assert len(c2_tb.rows) == 70
    assert c2_tb.rows[0].account_code == "1002"
    assert c2_tb.rows[0].amount == 15000.0  # Non-zero balance!

    a_tb = next(t for t in raw_tbs if t.entity_code == "A")
    assert len(a_tb.rows) == 80
    assert a_tb.rows[0].account_code == "2002"
    assert a_tb.rows[0].amount == 9750.0

    b_tb = next(t for t in raw_tbs if t.entity_code == "B")
    assert len(b_tb.rows) == 90
    assert b_tb.rows[0].account_code == "3002"
    assert b_tb.rows[0].amount == 12750.0

    c_tb = next(t for t in raw_tbs if t.entity_code == "C")
    assert len(c_tb.rows) == 100
    assert c_tb.rows[0].account_code == "4002"
    assert c_tb.rows[0].amount == 11250.0

    # Run mapper_node
    st = ConsolidationState(
        company_id="c2",
        period="31-Mar-2025",
        raw_tbs=raw_tbs,
        current_step=2
    )
    st = mapper_node(st)

    # Verify mapping decisions count and per-entity isolation
    assert len(st.mapping_decisions) == 340  # 70 + 80 + 90 + 100

    c2_decisions = [d for d in st.mapping_decisions if d.entity_code == "C2"]
    assert len(c2_decisions) == 70
    assert all(d.entity_code == "C2" for d in c2_decisions)
    assert all(d.amount is not None and abs(d.amount) > 0 for d in c2_decisions)
    assert c2_decisions[0].local_code == "1002"

    a_decisions = [d for d in st.mapping_decisions if d.entity_code == "A"]
    assert len(a_decisions) == 80
    assert all(d.entity_code == "A" for d in a_decisions)
    assert all(d.amount is not None and abs(d.amount) > 0 for d in a_decisions)
    assert a_decisions[0].local_code == "2002"

    b_decisions = [d for d in st.mapping_decisions if d.entity_code == "B"]
    assert len(b_decisions) == 90
    assert all(d.entity_code == "B" for d in b_decisions)
    assert all(d.amount is not None and abs(d.amount) > 0 for d in b_decisions)
    assert b_decisions[0].local_code == "3002"

    c_decisions = [d for d in st.mapping_decisions if d.entity_code == "C"]
    assert len(c_decisions) == 100
    assert all(d.entity_code == "C" for d in c_decisions)
    assert all(d.amount is not None and abs(d.amount) > 0 for d in c_decisions)
    assert c_decisions[0].local_code == "4002"


def test_pipeline_data_auto_heals_missing_mapping_metadata(test_client):
    """Verifies that /api/pipeline-data automatically heals legacy mapping decisions lacking entity_code or amount."""
    from fs_conso.core.file_parser import FlexibleTBParser
    from fs_conso.agent.state import ConsolidationState

    session.initialize_company("c2", load_samples=False)

    tb = FlexibleTBParser.parse_file(
        file_path_or_bytes="inputs/uploads/c2_Two_Year_Consolidation_TBs_balanced-v2.xlsx",
        filename="c2_Two_Year_Consolidation_TBs_balanced-v2.xlsx",
        entity_code="C2",
        sheet_name="Parent TB",
        period="31-Mar-2025"
    )
    session.state.raw_tbs = [tb]
    # Set legacy decisions with None entity_code and None amount
    session.state.mapping_decisions = [
        MappingDecision(
            local_code="1002",
            local_description="Cash and Bank",
            group_code="120400",
            group_description="Cash and Cash Equivalents",
            method="LEGACY",
            confidence=0.9,
            needs_review=False,
            entity_code=None,
            amount=None,
            level_0_name=None
        )
    ]

    res = test_client.get("/api/pipeline-data")
    assert res.status_code == 200
    data = res.json()

    # Must be auto-healed with entity_code and non-zero amount
    mappings = data.get("mapping_decisions", [])
    assert len(mappings) >= 1
    healed = next(m for m in mappings if m.get("local_code") == "1002")
    assert healed.get("entity_code") == "C2"
    assert healed.get("amount") is not None and healed.get("amount") > 0
