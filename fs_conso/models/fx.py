"""Foreign currency translation models."""

from typing import Dict, Optional, Tuple
from pydantic import BaseModel, Field

class FXRateEntry(BaseModel):
    """Exchange rate triple for a specific currency pair & period."""
    from_currency: str
    to_currency: str = "INR"
    as_on_date: str
    closing_rate: float = Field(..., gt=0.0, description="Used for Balance Sheet Assets & Liabilities")
    average_rate: float = Field(..., gt=0.0, description="Used for Profit & Loss Income & Expenses")
    historical_rate: float = Field(..., gt=0.0, description="Used for Equity & Share Capital")

class FXRateTable(BaseModel):
    """Lookup table for exchange rates."""
    rates: Dict[Tuple[str, str], FXRateEntry] = Field(default_factory=dict)

    def add_rate(self, entry: FXRateEntry) -> None:
        self.rates[(entry.from_currency.upper(), entry.to_currency.upper())] = entry

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
        return self.rates.get((from_curr.upper(), to_curr.upper()))
