"""LangGraph state schema for consolidation pipeline with deep agent tracing."""

from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fs_conso.core.aggregator import ConsolidatedTrialBalance
from fs_conso.core.elimination_engine import EliminationResult
from fs_conso.core.mapper import MappingDecision
from fs_conso.core.translator import TranslatedTrialBalance
from fs_conso.core.validator import ValidationResult
from fs_conso.models.goodwill import GoodwillSchedule
from fs_conso.models.trial_balance import RawTrialBalance, StandardizedTrialBalance


class AgentNodeTrace(BaseModel):
    """Deep execution telemetry captured for a LangGraph agent node run."""
    node_id: str
    agent_role: str
    status: str = "SUCCESS"  # "SUCCESS", "BLOCKED", "FAILED", "WARNING"
    start_time: str
    end_time: str
    execution_time_ms: float
    input_summary: Dict[str, Any] = Field(default_factory=dict)
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    decisions_count: int = 0
    token_usage: Dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    ai_calls: List[Dict[str, Any]] = Field(default_factory=list)
    state_mutations: List[str] = Field(default_factory=list)
    details: Optional[str] = None


class ConsolidationState(BaseModel):
    """Execution state passed through the LangGraph consolidation graph."""
    # Active workspace context
    company_id: str = "company-p"
    period: str = "31-Mar-2024"
    uploaded_ic_pairs: List[Any] = Field(default_factory=list)
    hitl_pending_reviews: List[Dict[str, Any]] = Field(default_factory=list)
    missing_prerequisites: List[str] = Field(default_factory=list)

    # Pipeline data
    raw_tbs: List[RawTrialBalance] = Field(default_factory=list)
    validation_results: List[ValidationResult] = Field(default_factory=list)
    standardized_tbs: List[StandardizedTrialBalance] = Field(default_factory=list)
    mapping_decisions: List[MappingDecision] = Field(default_factory=list)
    translated_tbs: List[TranslatedTrialBalance] = Field(default_factory=list)
    elimination_result: Optional[EliminationResult] = None
    goodwill_schedule: Optional[GoodwillSchedule] = None
    consolidated_tb: Optional[ConsolidatedTrialBalance] = None
    financial_statements: Dict[str, Any] = Field(default_factory=dict)
    output_excel_path: Optional[str] = None

    # Stepper and gating state
    current_step: int = 1  # 1: Ingestion, 2: Mapping, 3: Translation, 4: Eliminations, 5: Goodwill, 6: Consolidation, 7: Statements
    completed_steps: List[int] = Field(default_factory=list)
    is_blocked: bool = False
    error_message: Optional[str] = None
    current_stage: Optional[str] = None
    current_node: Optional[str] = None
    halted_node: Optional[str] = None
    halted_stage: Optional[str] = None
    remediation_items: List[str] = Field(default_factory=list)
    token_usage: Dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    # Teacher self-evaluation & audit telemetry
    teacher_score: float = 0.0
    teacher_evaluation: Dict[str, Any] = Field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    agent_traces: List[AgentNodeTrace] = Field(default_factory=list)
