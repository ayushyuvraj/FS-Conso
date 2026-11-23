"""Trial Balance domain models."""

from typing import List, Optional
from pydantic import BaseModel, Field

class RawTBRow(BaseModel):
    """Raw input row from an entity Trial Balance submission."""
    account_code: str
    account_description: str = ""
    debit: Optional[float] = None
    credit: Optional[float] = None
    amount: Optional[float] = None  # Signed amount if single-column format

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

    @property
    def total_debit(self) -> float:
        return sum(r.debit or 0.0 for r in self.rows)

    @property
    def total_credit(self) -> float:
        return sum(r.credit or 0.0 for r in self.rows)

    @property
    def total_signed_amount(self) -> float:
        return sum(r.amount or 0.0 for r in self.rows)

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
