"""Compiled LangGraph workflow for Enterprise Financial Consolidation."""

from langgraph.graph import END, START, StateGraph

from fs_conso.agent.auditor_node import auditor_node
from fs_conso.agent.nodes import (
    aggregator_node,
    elimination_node,
    excel_builder_node,
    mapper_node,
    translator_node,
    validator_node,
)
from fs_conso.agent.state import ConsolidationState

def _check_blocked(state: ConsolidationState) -> str:
    if state.is_blocked:
        return "blocked"
    return "continue"

def build_consolidation_graph():
    """Builds and compiles the end-to-end multi-agent LangGraph pipeline."""
    builder = StateGraph(ConsolidationState)

    # 1. Add all agent nodes
    builder.add_node("validator", validator_node)
    builder.add_node("mapper", mapper_node)
    builder.add_node("translator", translator_node)
    builder.add_node("elimination", elimination_node)
    builder.add_node("aggregator", aggregator_node)
    builder.add_node("excel_builder", excel_builder_node)
    builder.add_node("auditor", auditor_node)

    # 2. Add edges with conditional gating
    builder.add_edge(START, "validator")

    builder.add_conditional_edges(
        "validator",
        _check_blocked,
        {"blocked": END, "continue": "mapper"}
    )
    builder.add_conditional_edges(
        "mapper",
        _check_blocked,
        {"blocked": END, "continue": "translator"}
    )
    builder.add_conditional_edges(
        "translator",
        _check_blocked,
        {"blocked": END, "continue": "elimination"}
    )
    builder.add_conditional_edges(
        "elimination",
        _check_blocked,
        {"blocked": END, "continue": "aggregator"}
    )
    builder.add_conditional_edges(
        "aggregator",
        _check_blocked,
        {"blocked": END, "continue": "excel_builder"}
    )
    builder.add_edge("excel_builder", "auditor")
    builder.add_edge("auditor", END)

    return builder.compile()
