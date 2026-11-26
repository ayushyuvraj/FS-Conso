"""Foreign currency translation models with date-effective support."""

from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field


class FXRateEntry(BaseModel):
    """Exchange rate triple for a specific currency pair & period."""
    from_currency: str
    to_currency: str = "INR"
    as_on_date: str = "31-Mar-2024"
    closing_rate: float = Field(..., gt=0.0, description="Used for Balance Sheet Assets & Liabilities")
    average_rate: float = Field(..., gt=0.0, description="Used for Profit & Loss Income & Expenses")
    historical_rate: float = Field(..., gt=0.0, description="Used for Equity & Share Capital")
    swap_rate: Optional[float] = Field(default=None, description="Used for Forward & Currency Swap adjustments")


class FXRateTable(BaseModel):
    """Lookup table for exchange rates supporting date-effective lookup."""
    # List of entries for clean JSON serialization
    entries: List[FXRateEntry] = Field(default_factory=list)

    def add_rate(self, entry: FXRateEntry) -> None:
        # Replace if existing from/to exists
        self.entries = [
            e for e in self.entries
            if not (e.from_currency.upper() == entry.from_currency.upper() and e.to_currency.upper() == entry.to_currency.upper())
        ]
        self.entries.append(entry)

    def get_rate(self, from_curr: str, to_curr: str = "INR") -> Optional[FXRateEntry]:
        if from_curr.upper() == to_curr.upper():
            return FXRateEntry(
                from_currency=from_curr,
                to_currency=to_curr,
                as_on_date="identity",
                closing_rate=1.0,
                average_rate=1.0,
                historical_rate=1.0
            )
        for e in self.entries:
            if e.from_currency.upper() == from_curr.upper() and e.to_currency.upper() == to_curr.upper():
                return e
        return None

    @property
    def rates(self) -> Dict[Tuple[str, str], FXRateEntry]:
        """Backwards compatibility for legacy tuple lookup."""
        return {(e.from_currency.upper(), e.to_currency.upper()): e for e in self.entries}
