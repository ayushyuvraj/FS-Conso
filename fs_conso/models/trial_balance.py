"""Trial Balance domain models supporting flexible layouts and dimensions."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RawTBRow(BaseModel):
    """Raw input row from an entity Trial Balance submission."""
    account_code: str
    account_description: str = ""
    debit: Optional[float] = None
    credit: Optional[float] = None
    amount: Optional[float] = None  # Signed amount if single-column format
    dimensions: Dict[str, Any] = Field(default_factory=dict)  # e.g., Counterparty, Cost Center, Dept
    row_number: Optional[int] = None

    @property
    def is_blank(self) -> bool:
        """Determines if the amount fields are completely missing (blank)."""
        return self.debit is None and self.credit is None and self.amount is None


class RawTrialBalance(BaseModel):
    """Container for an ingested entity Trial Balance before standardization."""
    entity_code: str
    period: str
    currency: str
    rows: List[RawTBRow] = Field(default_factory=list)
    version: int = 1
    is_active: bool = True
    is_prior_period: bool = False
    source_filename: Optional[str] = None
    source_sheet: Optional[str] = None
    entity_name: Optional[str] = None
    detected_columns: Dict[str, str] = Field(default_factory=dict)
    detection_trace: Optional[str] = None

    @property
    def total_debit(self) -> float:
        return sum(
            r.debit if r.debit is not None else (r.amount if (r.amount is not None and r.amount > 0) else 0.0)
            for r in self.rows
        )

    @property
    def total_credit(self) -> float:
        return sum(
            r.credit if r.credit is not None else (abs(r.amount) if (r.amount is not None and r.amount < 0) else 0.0)
            for r in self.rows
        )

    @property
    def total_signed_amount(self) -> float:
        return sum(
            r.amount if r.amount is not None else ((r.debit or 0.0) - (r.credit or 0.0))
            for r in self.rows
        )

    @property
    def is_tallied(self) -> bool:
        return abs(self.total_signed_amount) < 0.01 or abs(self.total_debit - self.total_credit) < 0.01


class StandardizedRow(BaseModel):
    """A row converted to the Standard Import Format:

    - Account GL Code
    - GL Description
    - Signed Amount: Assets/Expenses are positive (+), Liabilities/Income/Equity are negative (-)
    - Source coordinate / provenance reference
    """
    account_code: str = Field(..., description="Group Standard COA Code")
    account_description: str = Field(..., description="Group Standard Description")
    amount: float = Field(..., description="Signed balance (Debits +, Credits -)")
    local_account_code: Optional[str] = None
    local_description: Optional[str] = None
    entity_code: str
    currency: str
    source_row_index: Optional[int] = None
    dimensions: Dict[str, Any] = Field(default_factory=dict)


class StandardizedTrialBalance(BaseModel):
    """Entity Trial Balance aligned to the Group Import Format."""
    entity_code: str
    period: str
    currency: str
    rows: List[StandardizedRow] = Field(default_factory=list)

    @property
    def sum_amount(self) -> float:
        """Under the standard import format, sum must equal 0.00."""
        return round(sum(r.amount for r in self.rows), 2)

    @property
    def is_tallied(self) -> bool:
        return abs(self.sum_amount) < 0.01
