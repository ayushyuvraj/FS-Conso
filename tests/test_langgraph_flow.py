"""Automated tests for LangGraph multi-agent orchestration & strict teacher gate."""

import pytest
from pathlib import Path
from fs_conso.agent.graph import build_consolidation_graph
from fs_conso.agent.state import ConsolidationState
from fs_conso.config import config
from fs_conso.core.sample_generator import load_benchmark_raw_tbs

def test_api_key_blocking_gate():
    config.gemini_api_key = ""
    app = build_consolidation_graph()
    state = ConsolidationState(raw_tbs=[])
    res = app.invoke(state)
    assert res["is_blocked"] is True
    assert "MANDATORY GATE ERROR" in res["error_message"]

def test_end_to_end_langgraph_with_strict_teacher_honors():
    config.gemini_api_key = "AIzaSyActiveTestKeyForAuditing"
    sample_dir = config.project_root / "inputs" / "sample_data"
    tbs = load_benchmark_raw_tbs(sample_dir)

    app = build_consolidation_graph()
    state = ConsolidationState(raw_tbs=tbs)
    res = app.invoke(state)

    assert res["is_blocked"] is False
    assert res["current_step"] == 6
    assert res["teacher_score"] >= 95.0, f"Teacher score {res['teacher_score']} was below honors threshold (95.0)"
    assert res["teacher_evaluation"]["passed"] is True
