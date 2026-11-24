"""Intercompany elimination models supporting N x N scaling."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class EliminationStatus(str, Enum):
    MATCHED = "MATCHED"                    # Net difference == 0.00
    TOLERANCE_WARNING = "TOLERANCE_WARNING"  # |diff| <= tolerance (Amber)
    EXCEPTION = "EXCEPTION"                  # |diff| > tolerance (Red)


class IntercompanyRecord(BaseModel):
    """Raw intercompany transaction record from TB dimensions or uploaded IC schedule."""
    entity_code: str
    counterparty_code: str
    account_code: str
    account_description: str = ""
    amount: float
    currency: str = "INR"
    reference_doc: Optional[str] = None
    transaction_date: Optional[str] = None


class EliminationPair(BaseModel):
    """A reciprocal relationship between two entities for a given transaction."""
    entity_code: str
    counterparty_code: str
    account_code: str
    account_description: str
    entity_amount: float
    counterparty_amount: float
    currency: str = "INR"
    
    @property
    def net_variance(self) -> float:
        """Net difference between the reciprocal balances."""
        return round(self.entity_amount + self.counterparty_amount, 2)

    @property
    def variance_percentage(self) -> float:
        base = max(abs(self.entity_amount), abs(self.counterparty_amount))
        if base == 0.0:
            return 0.0
        return round(abs(self.net_variance) / base, 4)

    def evaluate_status(self, abs_tolerance: float, pct_tolerance: float) -> EliminationStatus:
        if abs(self.net_variance) < 0.01:
            return EliminationStatus.MATCHED
        if abs(self.net_variance) <= abs_tolerance or self.variance_percentage <= pct_tolerance:
            return EliminationStatus.TOLERANCE_WARNING
        return EliminationStatus.EXCEPTION


class EliminationVoucher(BaseModel):
    """An elimination journal entry that adjusts consolidated figures.

    Contains individual entity allocations so that separate elimination columns
    (e.g., Company P1 Elim, Company P2 Elim) can be generated in financial statements.
    """
    voucher_id: str
    entity_code: str
    counterparty_code: str
    debit_account: str
    credit_account: str
    eliminated_amount: float
    variance_amount: float = 0.0
    status: EliminationStatus = EliminationStatus.MATCHED
    source_cells: List[str] = Field(default_factory=list)
    # Entity-specific elimination allocations: { "Company_S1": -100000.0, "Company_S2": 100000.0 }
    entity_allocations: Dict[str, float] = Field(default_factory=dict)


class IntercompanyEliminationResult(BaseModel):
    """Aggregated results of the intercompany elimination engine."""
    pairs: List[EliminationPair] = Field(default_factory=list)
    vouchers: List[EliminationVoucher] = Field(default_factory=list)
    matched_count: int = 0
    tolerance_warning_count: int = 0
    exception_count: int = 0
    total_eliminated: float = 0.0
    total_uneliminated_variance: float = 0.0
    # N x N matrix data: matrix[entity_code][counterparty_code] = net_amount
    matrix: Dict[str, Dict[str, float]] = Field(default_factory=dict)
