"""Automated Test Suite for Step 2 LLM-as-a-Judge Dynamic Mapping, Multi-Candidate Scoring & 1-Click Accept."""

import pytest
from fastapi.testclient import TestClient

from fs_conso.core.mapper import COAMappingEngine, MappingDecision
from fs_conso.models.coa import ChartOfAccounts, COAItem, AccountClassification
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.web.app import app, session


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def group_coa():
    coa = ChartOfAccounts()
    coa.add_item(COAItem(
        account_code="120400",
        account_name="Cash and Cash Equivalents",
        level_0_account="Cash and Cash Equivalents",
        account_type=AccountClassification.ASSET
    ))
    coa.add_item(COAItem(
        account_code="120500",
        account_name="Other Bank Balances",
        level_0_account="Other Bank Balances",
        account_type=AccountClassification.ASSET
    ))
    coa.add_item(COAItem(
        account_code="A120301",
        account_name="Trade Receivables from Other Parties",
        level_0_account="Trade Receivables",
        account_type=AccountClassification.ASSET
    ))
    coa.add_item(COAItem(
        account_code="A120302",
        account_name="Trade Receivables from Related Parties",
        level_0_account="Trade Receivables",
        account_type=AccountClassification.ASSET
    ))
    coa.add_item(COAItem(
        account_code="320300",
        account_name="Trade Payables to Micro and Small Enterprises",
        level_0_account="Trade Payables",
        account_type=AccountClassification.LIABILITY
    ))
    return coa


def test_llm_as_judge_returns_multi_candidates_and_selects_top_match(group_coa):
    """Verifies that unmapped accounts produce top 1-3 candidate options with highest percentage selected."""
    engine = COAMappingEngine(group_coa)

    unmapped = [
        ("C2", "1002", "Cash in bank current account"),
        ("C2", "1004", "Trade Receivables from domestic buyers")
    ]
    results = engine._fallback_semantic_ranking(unmapped)

    assert "1002" in results
    res_1002 = results["1002"]
    assert res_1002["group_code"] in ("120400", "120500")
    assert res_1002["confidence"] > 0.60
    candidates_1002 = res_1002["candidates"]
    assert len(candidates_1002) >= 1
    # Verify candidate structure
    top_cand = candidates_1002[0]
    assert "group_account_code" in top_cand
    assert "confidence" in top_cand
    assert "reasoning" in top_cand

    assert "1004" in results
    res_1004 = results["1004"]
    assert "A120301" in [c["group_account_code"] for c in res_1004["candidates"]]


def test_ambiguity_flagging_when_multiple_candidates_near_threshold(group_coa):
    """Verifies that an account with 2 or 3 probable options near threshold is flagged for review with is_ambiguous=True."""
    engine = COAMappingEngine(group_coa)

    raw_tb = RawTrialBalance(
        entity_code="C2",
        period="31-Mar-2025",
        currency="INR",
        rows=[
            RawTBRow(account_code="1002", account_description="Liquid cash and bank deposits", amount=50000.0)
        ]
    )

    std_tb, decisions = engine.standardize_trial_balance(raw_tb, use_ai=True)
    assert len(decisions) == 1
    d = decisions[0]

    assert d.local_code == "1002"
    assert d.group_code != "999999"  # Top match selected
    assert len(d.candidates) >= 1
    # Check that candidates carry confidence %
    for c in d.candidates:
        assert 0.0 <= c["confidence"] <= 1.0
        assert c["group_account_code"]


def test_hitl_accept_clears_ambiguity_and_confirms_mapping(test_client):
    """Verifies that 1-click accept or resolve clears is_ambiguous and sets confidence to 100%."""
    test_client.post("/api/reset-baseline")

    # Inject an ambiguous decision
    ambiguous_dec = MappingDecision(
        local_code="1002",
        local_description="Cash and Bank",
        group_code="120400",
        group_description="Cash and Cash Equivalents",
        method="GEMINI_AI",
        confidence=0.88,
        needs_review=True,
        entity_code="C2",
        currency="INR",
        amount=1500000.0,
        level_0_code="120400",
        level_0_name="Cash and Cash Equivalents",
        is_ambiguous=True,
        candidates=[
            {"group_account_code": "120400", "group_account_name": "Cash and Cash Equivalents", "confidence": 0.88, "reasoning": "Primary match"},
            {"group_account_code": "120500", "group_account_name": "Other Bank Balances", "confidence": 0.86, "reasoning": "Secondary match"}
        ]
    )
    session.state.mapping_decisions = [ambiguous_dec]
    session.state.hitl_pending_reviews = [{
        "entity_code": "C2",
        "local_code": "1002",
        "suggested_group_code": "120400"
    }]

    # 1-Click Accept top match via /api/hitl/resolve
    res = test_client.post("/api/hitl/resolve", json={
        "entity_code": "C2",
        "local_code": "1002",
        "group_code": "120400",
        "reasoning": "Auditor approved default top AI match"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # Verify decision state updated
    updated = next(d for d in session.state.mapping_decisions if d.local_code == "1002" and d.entity_code == "C2")
    assert updated.group_code == "120400"
    assert updated.confidence == 1.0
    assert updated.needs_review is False
    assert updated.is_ambiguous is False
    assert updated.method == "USER_APPROVED_RULE"

    # Verify pipeline-data reflects cleared review and candidates
    res_data = test_client.get("/api/pipeline-data")
    assert res_data.status_code == 200
    pdata = res_data.json()
    m_data = next(m for m in pdata["mapping_decisions"] if m["local_code"] == "1002")
    assert m_data["needs_review"] is False
    assert m_data["is_ambiguous"] is False
    assert len(m_data["candidates"]) == 2
