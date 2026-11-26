"""Domain models for Step 5: Goodwill & Acquisition Accounting Schedule."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GoodwillAdjustmentItem(BaseModel):
    """Dynamic adjustment line item (e.g. Fair value adjustment, PPA, deferred tax)."""
    id: str = Field(..., description="Unique client-side ID for the adjustment row")
    name: str = Field("Fair Value Adjustment", description="Display name / particulars for this adjustment")
    amounts_by_entity: Dict[str, float] = Field(default_factory=dict, description="Amount keyed by entity_code")
    remarks: str = Field("", description="Recordkeeping remarks for this adjustment row")


class GoodwillEntityData(BaseModel):
    """Goodwill calculation data and accounting inputs for a single entity (parent or subsidiary)."""
    entity_code: str = Field(..., description="Entity code (e.g., Company_P, Sub_1)")
    entity_name: str = Field("", description="Entity display name")
    is_parent: bool = Field(False, description="Whether this entity is the parent company")
    currency: str = Field("INR", description="Functional currency")

    # Row 1: Share Capital
    share_capital_l0_code: Optional[str] = Field(None, description="Selected Level 0 account code")
    share_capital_l0_name: Optional[str] = Field(None, description="Selected Level 0 account name")
    share_capital_amount: float = Field(0.0, description="Sum of mapped TB balances in reporting currency")

    # Row 3: Retained earnings and addition
    retained_earnings_amount: float = Field(0.0, description="Manual retained earnings at acquisition input")
    retained_earnings_remarks: str = Field("", description="Remarks for retained earnings")

    # Row 4: Net asset acquisition (Row 1 + sum(Row 2 adjustments) + Row 3)
    net_assets_at_acquisition: float = Field(0.0, description="Calculated net assets at acquisition")

    # Row 5: Investment by company
    investment_account_code: Optional[str] = Field(None, description="Account code representing investment in this entity")
    investment_account_name: Optional[str] = Field(None, description="Description of investment account")
    investment_amount: float = Field(0.0, description="Investment amount in reporting currency")
    investment_match_method: str = Field("MANUAL", description="'DETERMINISTIC', 'AI_INFERRED', 'HITL', 'MANUAL'")
    investment_confidence: float = Field(1.0, description="Matching confidence score (0.0 to 1.0)")
    investment_remarks: str = Field("", description="Remarks for investment line")
    needs_hitl: bool = Field(False, description="Flagged for user review when auto-matching confidence is low")

    # Row 6: Goodwill (positive difference)
    goodwill_amount: float = Field(0.0, description="Goodwill amount (Investment - Net Assets > 0)")

    # Row 7: Reserves (Capital Reserve / negative difference)
    capital_reserve_amount: float = Field(0.0, description="Capital Reserve amount (Net Assets - Investment > 0)")


class GoodwillSchedule(BaseModel):
    """Complete multi-entity Goodwill calculation matrix for Step 5."""
    company_id: str
    period: str
    reporting_currency: str = "INR"
    parent_entity_code: str = "Company_P"
    entities: List[str] = Field(default_factory=list, description="Ordered list of entity codes: [Parent, Sub1, Sub2, ...]")
    adjustments: List[GoodwillAdjustmentItem] = Field(default_factory=list, description="Dynamic adjustment rows (up to 100)")
    data_by_entity: Dict[str, GoodwillEntityData] = Field(default_factory=dict, description="Entity data keyed by entity_code")
    is_completed: bool = Field(False, description="Whether Step 5 has been confirmed and verified")
    total_goodwill: float = Field(0.0, description="Group aggregate Goodwill")
    total_capital_reserve: float = Field(0.0, description="Group aggregate Capital Reserve")
