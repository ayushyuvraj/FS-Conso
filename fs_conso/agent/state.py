"""LangGraph state schema for consolidation pipeline."""

from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fs_conso.core.aggregator import ConsolidatedTrialBalance
from fs_conso.core.elimination_engine import EliminationResult
from fs_conso.core.mapper import MappingDecision
from fs_conso.core.translator import TranslatedTrialBalance
from fs_conso.core.validator import ValidationResult
from fs_conso.models.trial_balance import RawTrialBalance, StandardizedTrialBalance

class ConsolidationState(BaseModel):
    """Execution state passed through the LangGraph consolidation graph."""
    # Pipeline data
    raw_tbs: List[RawTrialBalance] = Field(default_factory=list)
    validation_results: List[ValidationResult] = Field(default_factory=list)
    standardized_tbs: List[StandardizedTrialBalance] = Field(default_factory=list)
    mapping_decisions: List[MappingDecision] = Field(default_factory=list)
    translated_tbs: List[TranslatedTrialBalance] = Field(default_factory=list)
    elimination_result: Optional[EliminationResult] = None
    consolidated_tb: Optional[ConsolidatedTrialBalance] = None
    output_excel_path: Optional[str] = None

    # Stepper and gating state
    current_step: int = 1  # 1: Ingestion, 2: Mapping, 3: Translation, 4: Eliminations, 5: Consolidation, 6: Statements & Audit
    completed_steps: List[int] = Field(default_factory=list)
    is_blocked: bool = False
    error_message: Optional[str] = None

    # Teacher self-evaluation & audit
    teacher_score: float = 0.0
    teacher_evaluation: Dict[str, Any] = Field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
