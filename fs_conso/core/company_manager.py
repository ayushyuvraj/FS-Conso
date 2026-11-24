"""Multi-Company workspace and master data persistence manager."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import openpyxl

from fs_conso.config import config
from fs_conso.models.coa import AccountClassification, ChartOfAccounts, COAItem, RollUpOperator
from fs_conso.models.company import CompanyProfile, PeriodStatus
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.models.fx import FXRateEntry, FXRateTable


class CompanyManager:
    """Manages isolated multi-company workspaces and master data persistence."""

    def __init__(self, workspaces_dir: Optional[Path] = None, workspaces_root: Optional[Path] = None):
        self.workspaces_dir = workspaces_dir or workspaces_root or (config.project_root / "inputs" / "workspaces")
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    def _company_dir(self, company_id: str) -> Path:
        slug = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in str(company_id).lower()).strip("-")
        if not slug:
            raise ValueError(f"Invalid company_id '{company_id}': results in an empty directory slug.")
        target_dir = (self.workspaces_dir / slug).resolve()
        if not target_dir.is_relative_to(self.workspaces_dir.resolve()):
            raise ValueError(f"Directory traversal detected in company_id '{company_id}'.")
        return target_dir

    def list_companies(self) -> List[Dict[str, Any]]:
        """Lists all stored company profiles with high-level summaries."""
        companies = []
        for cdir in self.workspaces_dir.iterdir():
            if cdir.is_dir() and (cdir / "profile.json").exists():
                try:
                    pdata = json.loads((cdir / "profile.json").read_text(encoding="utf-8"))
                    entity_count = 0
                    if (cdir / "entities.json").exists():
                        edata = json.loads((cdir / "entities.json").read_text(encoding="utf-8"))
                        entity_count = len(edata.get("entities", {}))
                    coa_count = 0
                    if (cdir / "coa.json").exists():
                        cdata = json.loads((cdir / "coa.json").read_text(encoding="utf-8"))
                        coa_count = len(cdata.get("items", {}))

                    companies.append({
                        "company_id": pdata.get("company_id"),
                        "company_name": pdata.get("company_name"),
                        "reporting_currency": pdata.get("reporting_currency", "INR"),
                        "current_period": pdata.get("current_period", "31-Mar-2024"),
                        "entity_count": entity_count,
                        "coa_account_count": coa_count,
                        "updated_at": pdata.get("updated_at")
                    })
                except Exception:
                    continue
        return sorted(companies, key=lambda x: x.get("company_name", ""))

    def get_company(self, company_id: str) -> Optional[CompanyProfile]:
        """Loads complete CompanyProfile from its isolated workspace directory."""
        cdir = self._company_dir(company_id)
        pfile = cdir / "profile.json"
        if not pfile.exists():
            return None

        pdata = json.loads(pfile.read_text(encoding="utf-8"))
        profile = CompanyProfile(**pdata)

        # Load Group COA
        coa_file = cdir / "coa.json"
        if coa_file.exists():
            try:
                coa_data = json.loads(coa_file.read_text(encoding="utf-8"))
                profile.group_coa = ChartOfAccounts(**coa_data)
            except Exception:
                pass

        # Load Entity Hierarchy
        ent_file = cdir / "entities.json"
        if ent_file.exists():
            try:
                ent_data = json.loads(ent_file.read_text(encoding="utf-8"))
                profile.entity_hierarchy = EntityHierarchy(**ent_data)
            except Exception:
                pass

        # Load FX Tables
        fx_file = cdir / "fx_rates.json"
        if fx_file.exists():
            try:
                fx_data = json.loads(fx_file.read_text(encoding="utf-8"))
                profile.fx_tables_by_date = {
                    period: FXRateTable(**tbl) for period, tbl in fx_data.items()
                }
            except Exception:
                pass

        return profile

    def save_company(self, profile: CompanyProfile) -> None:
        """Saves company profile and master data structures."""
        cdir = self._company_dir(profile.company_id)
        cdir.mkdir(parents=True, exist_ok=True)

        # Save main profile
        pdata = profile.model_dump(exclude={"group_coa", "entity_hierarchy", "fx_tables_by_date"})
        (cdir / "profile.json").write_text(json.dumps(pdata, indent=2), encoding="utf-8")

        # Save COA
        if profile.group_coa:
            (cdir / "coa.json").write_text(
                json.dumps(profile.group_coa.model_dump(), indent=2),
                encoding="utf-8"
            )

        # Save Entities
        if profile.entity_hierarchy:
            (cdir / "entities.json").write_text(
                json.dumps(profile.entity_hierarchy.model_dump(), indent=2),
                encoding="utf-8"
            )

        # Save FX Tables
        if profile.fx_tables_by_date:
            fx_data = {p: tbl.model_dump() for p, tbl in profile.fx_tables_by_date.items()}
            (cdir / "fx_rates.json").write_text(
                json.dumps(fx_data, indent=2),
                encoding="utf-8"
            )

    def create_company(
        self,
        company_id: str,
        company_name: str,
        reporting_currency: str = "INR",
        current_period: str = "31-Mar-2024"
    ) -> CompanyProfile:
        """Creates a fresh, empty company profile."""
        profile = CompanyProfile(
            company_id=company_id,
            company_name=company_name,
            reporting_currency=reporting_currency,
            current_period=current_period,
            group_coa=ChartOfAccounts(),
            entity_hierarchy=EntityHierarchy(parent_code=company_id, reporting_currency=reporting_currency),
            fx_tables_by_date={},
            historical_mappings=[]
        )
        self.save_company(profile)
        return profile

    def import_master_workbook(
        self,
        conso_path: Path,
        company_id: str,
        company_name: str,
        reporting_currency: str = "INR",
        current_period: str = "31-Mar-2024"
    ) -> CompanyProfile:
        """Ingests master setup from an Excel file (like Conso.xlsx) to create a populated profile."""
        wb = openpyxl.load_workbook(conso_path, data_only=True)
        
        # 1. Parse Group COA
        coa = ChartOfAccounts()
        if "Chart of Accounts" in wb.sheetnames:
            ws = wb["Chart of Accounts"]
            for r in range(2, ws.max_row + 1):
                code_val = ws.cell(r, 1).value
                if code_val is None:
                    continue
                code = str(code_val).strip()
                l3 = ws.cell(r, 2).value
                l2 = ws.cell(r, 3).value
                l1 = ws.cell(r, 4).value
                l0 = ws.cell(r, 5).value
                acc_type_val = ws.cell(r, 6).value or "Asset"
                rollup_val = ws.cell(r, 7).value
                name = l0 or l1 or l2 or l3 or code

                t_str = str(acc_type_val).strip().capitalize()
                if "Asset" in t_str:
                    acc_type = AccountClassification.ASSET
                elif "Liab" in t_str:
                    acc_type = AccountClassification.LIABILITY
                elif "Equity" in t_str:
                    acc_type = AccountClassification.EQUITY
                elif "Inc" in t_str or "Rev" in t_str:
                    acc_type = AccountClassification.INCOME
                elif "Exp" in t_str:
                    acc_type = AccountClassification.EXPENSE
                else:
                    acc_type = AccountClassification.ASSET

                rollup = RollUpOperator.SUBTRACTION if rollup_val and "Sub" in str(rollup_val) else RollUpOperator.ADDITION
                stmt = "PL" if acc_type in (AccountClassification.INCOME, AccountClassification.EXPENSE) else "BS"

                coa.add_item(COAItem(
                    account_code=code,
                    account_name=str(name).strip(),
                    level_3=str(l3).strip() if l3 else None,
                    level_2=str(l2).strip() if l2 else None,
                    level_1=str(l1).strip() if l1 else None,
                    level_0_account=str(l0).strip() if l0 else None,
                    account_type=acc_type,
                    rollup_operator=rollup,
                    fs_statement=stmt
                ))

        # 2. Parse Entity Hierarchy
        hierarchy = EntityHierarchy(parent_code="Company_P", reporting_currency=reporting_currency)
        if "Entity Structure" in wb.sheetnames:
            ws = wb["Entity Structure"]
            # Look for Parent in row 4/5
            hierarchy.add_entity(LegalEntity(
                entity_code="Company_P",
                entity_name=f"{company_name} (Parent)",
                entity_short_name="Parent",
                input_currency=reporting_currency,
                holding_percentage=1.0,
                consolidation_method="Parent"
            ))
            # Dynamic subsidiaries scanning
            for r in range(5, ws.max_row + 1):
                col2 = ws.cell(r, 2).value
                col3 = ws.cell(r, 3).value
                if col2:
                    sub_code = str(col2).strip()
                    pct = 1.0
                    if col3 is not None:
                        try:
                            pct = float(col3)
                        except Exception:
                            pct = 1.0
                    curr = "USD" if "S2" in sub_code else ("SGD" if "S3" in sub_code else reporting_currency)
                    hierarchy.add_entity(LegalEntity(
                        entity_code=sub_code,
                        entity_name=f"{sub_code} Operating Subsidiary",
                        entity_short_name=sub_code,
                        input_currency=curr,
                        parent_entity_code="Company_P",
                        immediate_parent="Company_P",
                        ultimate_parent="Company_P",
                        holding_percentage=pct,
                        consolidation_method="Full Consolidation"
                    ))

        # 3. Parse FX Rates
        fx_table = FXRateTable()
        fx_table.add_rate(FXRateEntry(
            from_currency="USD",
            to_currency=reporting_currency,
            as_on_date=current_period,
            closing_rate=83.50,
            average_rate=83.00,
            historical_rate=80.00
        ))
        fx_table.add_rate(FXRateEntry(
            from_currency="SGD",
            to_currency=reporting_currency,
            as_on_date=current_period,
            closing_rate=62.00,
            average_rate=61.50,
            historical_rate=60.00
        ))

        # 4. Parse Historical Mappings
        hist_mappings: List[Dict[str, str]] = []
        if "1_COA_Mapping" in wb.sheetnames:
            ws = wb["1_COA_Mapping"]
            for r in range(25, ws.max_row + 1):
                ent = ws.cell(r, 1).value
                loc = ws.cell(r, 2).value
                grp = ws.cell(r, 4).value
                if ent and loc and grp:
                    hist_mappings.append({
                        "entity": str(ent).strip(),
                        "local_code": str(loc).strip(),
                        "group_code": str(grp).strip()
                    })

        # Baseline known rules
        baseline_rules = [
            ("Company_S1", "11001", "120400"),
            ("Company_S1", "21001", "320300"),
            ("Company_S2", "CASH01", "120400"),
            ("Company_S2", "PAY01", "320300"),
            ("Company_S3", "CASH01", "120400"),
        ]
        for ent, loc, grp in baseline_rules:
            if not any(m["entity"] == ent and m["local_code"] == loc for m in hist_mappings):
                hist_mappings.append({"entity": ent, "local_code": loc, "group_code": grp})

        wb.close()

        profile = CompanyProfile(
            company_id=company_id,
            company_name=company_name,
            reporting_currency=reporting_currency,
            current_period=current_period,
            group_coa=coa,
            entity_hierarchy=hierarchy,
            fx_tables_by_date={current_period: fx_table},
            historical_mappings=hist_mappings
        )
        self.save_company(profile)
        return profile

    def ensure_default_demo_company(self) -> CompanyProfile:
        """Initializes or returns the standard 'Company P Healthcare' demo benchmark profile."""
        existing = self.get_company("company-p")
        if existing:
            return existing

        conso_path = config.project_root / "Conso.xlsx"
        if conso_path.exists():
            return self.import_master_workbook(
                conso_path=conso_path,
                company_id="company-p",
                company_name="Company P Healthcare Corp",
                reporting_currency="INR",
                current_period="31-Mar-2024"
            )

        return self.create_company("company-p", "Company P Healthcare Corp")


# Global company manager singleton
company_manager = CompanyManager()
