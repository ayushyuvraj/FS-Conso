"""Entity structure & ownership domain models."""

from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class LegalEntity(BaseModel):
    """Represents a legal entity within the enterprise consolidation perimeter."""
    entity_code: str = Field(..., description="Unique entity identifier (e.g., Company_P, Sub_1)")
    entity_name: str = Field(..., description="Full legal name of the entity")
    entity_short_name: Optional[str] = None
    company_reg_number: Optional[str] = None
    country_of_inc: str = "India"
    date_of_inc: Optional[date] = None
    input_currency: str = Field("INR", description="Functional/Local currency of this entity")
    parent_entity_code: Optional[str] = Field(None, description="Direct parent entity code")
    immediate_parent: Optional[str] = None
    ultimate_parent: Optional[str] = None
    holding_percentage: float = Field(1.0, ge=0.0, le=1.0, description="Parent ownership share (0.0 to 1.0)")
    acquisition_date: Optional[date] = None
    consolidation_method: str = "Full Consolidation"  # Full, Equity Method, Proportional

    @property
    def nci_percentage(self) -> float:
        """Calculates Non-Controlling Interest (NCI) % automatically:

        NCI % = 1.0 - Holding %
        """
        return round(max(0.0, 1.0 - self.holding_percentage), 4)

    @property
    def is_parent(self) -> bool:
        return self.parent_entity_code is None or self.holding_percentage == 1.0 and not self.immediate_parent

class EntityHierarchy(BaseModel):
    """Complete entity tree for a consolidation run."""
    entities: Dict[str, LegalEntity] = Field(default_factory=dict)
    parent_code: str = "Company_P"
    reporting_currency: str = "INR"

    def add_entity(self, entity: LegalEntity) -> None:
        self.entities[entity.entity_code] = entity

    def get_entity(self, code: str) -> Optional[LegalEntity]:
        return self.entities.get(code)

    def get_children(self, parent_code: str) -> List[LegalEntity]:
        return [e for e in self.entities.values() if e.parent_entity_code == parent_code]
