"""Test suite for strict generic step progression gating rules.

Generic Rule: If anything in any given step is not complete, the system CANNOT
proceed to the next step under any circumstances.
"""

import pytest
from pathlib import Path
from fs_conso.agent.state import ConsolidationState, MappingDecision
from fs_conso.agent.nodes import (
    validator_node,
    mapper_node,
    translator_node,
    elimination_node,
    aggregator_node,
    excel_builder_node,
)
from fs_conso.agent.graph import build_consolidation_graph
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.web.app import app, session
from httpx import AsyncClient, ASGITransport


def test_mapper_halts_pipeline_when_reviews_pending():
    """Verify that when any account in Step 2 needs review, the pipeline blocks at Step 2."""
    raw_tb = RawTrialBalance(
        entity_code="TEST_PARENT",
        entity_name="Test Parent Co",
        period="31-Mar-2025",
        currency="INR",
        rows=[
            RawTBRow(line_number=1, account_code="1001", account_description="Unmapped Rare Item", amount=500000.0)
        ]
    )

    state = ConsolidationState(
        company_id="TEST_CO",
        period="31-Mar-2025",
        raw_tbs=[raw_tb],
        current_step=1,
        completed_steps=[1]
    )

    # Execute mapper node
    res = mapper_node(state)

    # Must be blocked at Step 2
    assert res.is_blocked is True
    assert res.current_step == 2
    assert res.halted_node == "mapper"
    assert 2 not in res.completed_steps
    assert 3 not in res.completed_steps
    assert 6 not in res.completed_steps
    assert res.completed_steps == [1]
    assert len(res.hitl_pending_reviews) > 0


def test_translator_blocks_if_step2_not_complete():
    """Verify that translator_node refuses execution if Step 2 is incomplete."""
    raw_tb = RawTrialBalance(
        entity_code="TEST_SUB",
        entity_name="Test Sub",
        period="31-Mar-2025",
        currency="USD",
        rows=[
            RawTBRow(line_number=1, account_code="2001", account_description="Pending Review GL", amount=100.0)
        ]
    )

    # State with incomplete mapping
    state = ConsolidationState(
        company_id="TEST_CO",
        period="31-Mar-2025",
        raw_tbs=[raw_tb],
        mapping_decisions=[
            MappingDecision(
                local_code="2001",
                local_description="Pending Review GL",
                group_code="A120101",
                group_description="Inventories",
                confidence=0.72,
                method="GEMINI_AI",
                needs_review=True,
                entity_code="TEST_SUB"
            )
        ],
        current_step=2,
        completed_steps=[1]
    )

    # Attempt to invoke translator directly
    res = translator_node(state)

    assert res.is_blocked is True
    assert res.current_step == 2
    assert 3 not in res.completed_steps


def test_langgraph_halts_at_mapper_when_unmapped():
    """Verify that the compiled LangGraph workflow halts after mapper when items need review."""
    graph = build_consolidation_graph()

    raw_tb = RawTrialBalance(
        entity_code="TEST_SUB",
        entity_name="Test Sub",
        period="31-Mar-2025",
        currency="INR",
        rows=[
            RawTBRow(line_number=1, account_code="3001", account_description="Unmapped Ambiguous GL", amount=100.0, debit=100.0),
            RawTBRow(line_number=2, account_code="3002", account_description="Cash and Cash Equivalents", amount=-100.0, credit=100.0)
        ]
    )

    state = ConsolidationState(
        company_id="generic_test",
        period="31-Mar-2025",
        raw_tbs=[raw_tb],
        current_step=1,
        completed_steps=[]
    )

    result_dict = graph.invoke(state)
    final_state = ConsolidationState(**result_dict)

    # Should have executed validator (passed) and mapper (halted), but NOT translator or downstream
    assert final_state.is_blocked is True
    assert final_state.halted_node == "mapper"
    assert final_state.current_step == 2
    assert 1 in final_state.completed_steps
    assert 2 not in final_state.completed_steps
    assert 6 not in final_state.completed_steps
    assert final_state.consolidated_tb is None
    assert final_state.output_excel_path is None


@pytest.mark.asyncio
async def test_api_cleanses_stale_completed_steps():
    """Verify /api/pipeline-data automatically cleanses completed_steps if mapping reviews exist."""
    session.initialize_company("c2", load_samples=False)

    # Corrupt state with stale downstream completed steps
    session.state.completed_steps = [1, 3, 4, 5, 6]
    session.state.current_step = 6
    session.state.mapping_decisions = [
        MappingDecision(
            local_code="1008",
            local_description="Ambiguous Account",
            group_code="A111001",
            group_description="Capital Advances",
            confidence=0.78,
            method="GEMINI_AI",
            needs_review=True,
            entity_code="C2"
        )
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/pipeline-data")
        assert res.status_code == 200
        data = res.json()

        # Must have cleansed completed_steps to remove 2, 3, 4, 5, 6
        assert 2 not in data["completed_steps"]
        assert 3 not in data["completed_steps"]
        assert 6 not in data["completed_steps"]
        assert data["current_step"] <= 2
