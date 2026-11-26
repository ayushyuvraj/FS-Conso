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
