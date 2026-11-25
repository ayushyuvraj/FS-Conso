"""Multi-Company workspace and profile domain models."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from fs_conso.models.coa import ChartOfAccounts
from fs_conso.models.entity import EntityHierarchy
from fs_conso.models.fx import FXRateTable


class PeriodStatus(str, Enum):
    OPEN = "OPEN"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    LOCKED = "LOCKED"


class CompanyProfile(BaseModel):
    """Encapsulates a client company/group workspace (e.g. Company P, Company X, Company Y).

    Maintains isolated master data:
    - Group Chart of Accounts (COA)
    - Entity Hierarchy & Ownership tree (1 to 1,000 entities)
    - Date-effective FX rate tables (keyed by period/date, e.g. "31-Mar-2024", "31-May-2026")
    - Approved historical account mappings memory (learning cache)
    - Active period configurations
    """
    company_id: str = Field(..., description="Unique slug/ID for workspace (e.g., 'acme-corp')")
    company_code: str = Field("", description="Normalized company code (e.g., 'ACME')")
    company_name: str = Field(..., description="Display name of enterprise/group")
    reporting_currency: str = Field("INR", description="Group reporting currency")
    current_period: Optional[str] = Field(None, description="Optional active reporting period")
    number_of_subsidiaries: int = Field(0, ge=0, description="Declared count of subsidiaries")
    coa_filename: Optional[str] = Field(None, description="Uploaded base Chart of Accounts filename")
    coa_uploaded_at: Optional[str] = Field(None, description="Timestamp when base COA was uploaded")
    
    # Master data structures
    group_coa: Optional[ChartOfAccounts] = None
    entity_hierarchy: Optional[EntityHierarchy] = None
    
    # Date-effective FX rates: { "31-Mar-2024": FXRateTable, "31-May-2026": FXRateTable }
    fx_tables_by_date: Dict[str, FXRateTable] = Field(default_factory=dict)
    
    # Learning Memory: (entity_code, local_code) -> group_code
    # Serialized as list of dicts for clean JSON persistence
    historical_mappings: List[Dict[str, str]] = Field(default_factory=list)
    
    # Period states: { "31-Mar-2024": "LOCKED", "31-May-2026": "OPEN" }
    period_statuses: Dict[str, PeriodStatus] = Field(default_factory=dict)
    
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def get_fx_table_for_period(self, period: Optional[str] = None) -> Optional[FXRateTable]:
        """Resolves the FXRateTable for the given period or active current period."""
        p = period or self.current_period
        if not p:
            return None
        return self.fx_tables_by_date.get(p)

    def set_fx_table_for_period(self, period: str, table: FXRateTable) -> None:
        self.fx_tables_by_date[period] = table
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_mappings_dict(self) -> Dict[Tuple[str, str], str]:
        """Returns in-memory dictionary lookup for mapper engine: (entity, local_code) -> group_code."""
        result: Dict[Tuple[str, str], str] = {}
        for m in self.historical_mappings:
            ent = m.get("entity", "").strip()
            loc = m.get("local_code", "").strip()
            grp = m.get("group_code", "").strip()
            if ent and loc and grp:
                result[(ent, loc)] = grp
        return result

    def add_mapping(self, entity_code: str, local_code: str, group_code: str) -> None:
        """Adds or updates a mapping in the learning memory store."""
        ent = entity_code.strip()
        loc = local_code.strip()
        grp = group_code.strip()
        
        # Remove existing if present
        self.historical_mappings = [
            m for m in self.historical_mappings
            if not (m.get("entity") == ent and m.get("local_code") == loc)
        ]
        self.historical_mappings.append({
            "entity": ent,
            "local_code": loc,
            "group_code": grp,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_mapping(self, entity_code: str, local_code: str) -> Optional[str]:
        """Looks up a specific approved mapping for an entity code and local GL code."""
        ent = entity_code.strip()
        loc = local_code.strip()
        for m in self.historical_mappings:
            if m.get("entity") == ent and m.get("local_code") == loc:
                return m.get("group_code")
        return None
