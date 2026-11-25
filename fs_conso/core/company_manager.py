"""Multi-Company workspace and master data persistence manager."""

import json
import re
import shutil
from datetime import date, datetime
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

    @staticmethod
    def slugify_code(code: str) -> str:
        slug = re.sub(r"[^a-z0-9_-]+", "-", str(code).strip().lower()).strip("-_")
        if not slug:
            raise ValueError(f"Invalid company code '{code}': must contain alphanumeric characters.")
        return slug

    def _company_dir(self, company_id: str) -> Path:
        slug = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in str(company_id).lower()).strip("-")
        if not slug:
            raise ValueError(f"Invalid company_id '{company_id}': results in an empty directory slug.")
        target_dir = (self.workspaces_dir / slug).resolve()
        if not target_dir.is_relative_to(self.workspaces_dir.resolve()):
            raise ValueError(f"Directory traversal detected in company_id '{company_id}'.")
        return target_dir

    def _build_company_summary(self, cdir: Path, pdata: Dict[str, Any]) -> Dict[str, Any]:
        """Builds a complete snapshot summary dictionary for UI and API responses."""
        entities_dict: Dict[str, Any] = {}
        if (cdir / "entities.json").exists():
            edata = json.loads((cdir / "entities.json").read_text(encoding="utf-8"))
            entities_dict = edata.get("entities", {}) or {}

        subsidiaries: List[Dict[str, Any]] = []
        for ent_code, ent in entities_dict.items():
            if ent.get("consolidation_method") == "Parent" or ent.get("parent_entity_code") is None:
                continue
            holding = float(ent.get("holding_percentage", 1.0))
            ownership_pct = round(holding * 100.0, 2)
            nci_pct = round(max(0.0, 100.0 - ownership_pct), 2)
            subsidiaries.append({
                "entity_code": ent.get("entity_code", ent_code),
                "entity_name": ent.get("entity_name", ent_code),
                "company_reg_number": ent.get("company_reg_number") or "",
                "country_of_inc": ent.get("country_of_inc") or "",
                "date_of_inc": ent.get("date_of_inc") or "",
                "input_currency": ent.get("input_currency", pdata.get("reporting_currency", "INR")),
                "ownership_pct": ownership_pct,
                "nci_pct": nci_pct,
                "acquisition_date": ent.get("acquisition_date") or "",
                "consolidation_method": ent.get("consolidation_method", "Full Consolidation"),
            })

        coa_count = 0
        if (cdir / "coa.json").exists():
            cdata = json.loads((cdir / "coa.json").read_text(encoding="utf-8"))
            coa_count = len(cdata.get("items", {}))

        comp_id = pdata.get("company_id", cdir.name)
        return {
            "company_id": comp_id,
            "company_code": pdata.get("company_code") or str(comp_id).upper(),
            "company_name": pdata.get("company_name"),
            "reporting_currency": pdata.get("reporting_currency", "INR"),
            "current_period": pdata.get("current_period"),
            "number_of_subsidiaries": pdata.get("number_of_subsidiaries", len(subsidiaries)),
            "entity_count": len(entities_dict) if entities_dict else (1 + len(subsidiaries)),
            "coa_account_count": coa_count,
            "coa_filename": pdata.get("coa_filename"),
            "coa_uploaded_at": pdata.get("coa_uploaded_at"),
            "subsidiaries": subsidiaries,
            "created_at": pdata.get("created_at"),
            "updated_at": pdata.get("updated_at"),
        }

    def list_companies(self) -> List[Dict[str, Any]]:
        """Lists all stored company profiles with high-level summaries and subsidiary snapshots."""
        companies = []
        if not self.workspaces_dir.exists():
            return companies
        for cdir in self.workspaces_dir.iterdir():
            if cdir.is_dir() and (cdir / "profile.json").exists():
                try:
                    pdata = json.loads((cdir / "profile.json").read_text(encoding="utf-8"))
                    companies.append(self._build_company_summary(cdir, pdata))
                except Exception:
                    continue
        return sorted(companies, key=lambda x: (x.get("company_name") or "").lower())

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
        pdata = profile.model_dump(mode="json", exclude={"group_coa", "entity_hierarchy", "fx_tables_by_date"})
        (cdir / "profile.json").write_text(json.dumps(pdata, indent=2), encoding="utf-8")

        # Save COA
        if profile.group_coa:
            (cdir / "coa.json").write_text(
                json.dumps(profile.group_coa.model_dump(mode="json"), indent=2),
                encoding="utf-8"
            )

        # Save Entities
        if profile.entity_hierarchy:
            (cdir / "entities.json").write_text(
                json.dumps(profile.entity_hierarchy.model_dump(mode="json"), indent=2),
                encoding="utf-8"
            )

        # Save FX Tables
        if profile.fx_tables_by_date:
            fx_data = {p: tbl.model_dump(mode="json") for p, tbl in profile.fx_tables_by_date.items()}
            (cdir / "fx_rates.json").write_text(
                json.dumps(fx_data, indent=2),
                encoding="utf-8"
            )

    def create_company(
        self,
        company_id: str,
        company_name: str,
        reporting_currency: str = "INR",
        current_period: Optional[str] = None,
        company_code: Optional[str] = None,
    ) -> CompanyProfile:
        """Creates a fresh, empty company profile."""
        norm_code = (company_code or company_id).strip().upper()
        profile = CompanyProfile(
            company_id=company_id,
            company_code=norm_code,
            company_name=company_name,
            reporting_currency=reporting_currency,
            current_period=current_period,
            group_coa=ChartOfAccounts(),
            entity_hierarchy=EntityHierarchy(parent_code=norm_code, reporting_currency=reporting_currency),
            fx_tables_by_date={},
            historical_mappings=[]
        )
        self.save_company(profile)
        return profile

    @staticmethod
    def _parse_flexible_date(val: Any) -> Optional[date]:
        if val is None:
            return None
        if isinstance(val, date):
            return val
        s = str(val).strip()
        if not s or s.lower() in ("none", "null", "nan", "dd-mm-yyyy", "yyyy-mm-dd", "optional"):
            return None
        # Try ISO format first (YYYY-MM-DD or YYYY/MM/DD)
        s_clean = s[:10].replace("/", "-")
        try:
            return date.fromisoformat(s_clean)
        except Exception:
            pass
        # Try DD-MM-YYYY or DD/MM/YYYY
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except Exception:
                pass
        # Try standard named-month formats
        for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%b/%Y", "%d/%B/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                continue
        raise ValueError(f"Could not parse date '{val}'. Expected format: YYYY-MM-DD or DD-MM-YYYY.")

    @staticmethod
    def _generate_entity_code(entity_name: str, index: int, used_codes: set) -> str:
        base = re.sub(r"[^A-Z0-9]+", "_", entity_name.strip().upper()).strip("_")
        if not base:
            base = f"SUB_{index}"
        base = base[:20].strip("_") or f"SUB_{index}"
        candidate = base
        suffix = 2
        while candidate in used_codes:
            candidate = f"{base[:16]}_{suffix}"
            suffix += 1
        used_codes.add(candidate)
        return candidate

    def create_or_update_profile(
        self,
        company_name: str,
        company_code: str,
        reporting_currency: str,
        subsidiaries: List[Dict[str, Any]],
        coa: Optional[ChartOfAccounts] = None,
        coa_filename: Optional[str] = None,
        existing_company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new CompanyProfile or updates an existing one with parent, N subsidiaries, and Base COA."""
        clean_name = company_name.strip()
        clean_code = company_code.strip().upper()
        clean_curr = reporting_currency.strip().upper()
        if not clean_name:
            raise ValueError("Company name is required.")
        if not clean_code:
            raise ValueError("Company code is required.")
        if not clean_curr:
            raise ValueError("Reporting currency is required.")

        target_id = existing_company_id or self.slugify_code(clean_code)
        existing = self.get_company(target_id)
        if existing_company_id is None and existing is not None:
            raise ValueError(f"A company profile with code '{clean_code}' already exists.")
        if existing_company_id is not None and existing is None:
            raise ValueError(f"Company profile '{existing_company_id}' not found.")

        # Check duplicate company_code against other profiles
        for other in self.list_companies():
            if other["company_id"] != target_id and (other.get("company_code") or "").upper() == clean_code:
                raise ValueError(f"Company code '{clean_code}' is already used by '{other.get('company_name')}'.")

        hierarchy = EntityHierarchy(parent_code=clean_code, reporting_currency=clean_curr)
        used_codes = {clean_code}
        hierarchy.add_entity(
            LegalEntity(
                entity_code=clean_code,
                entity_name=clean_name,
                entity_short_name=clean_code,
                input_currency=clean_curr,
                holding_percentage=1.0,
                consolidation_method="Parent",
            )
        )

        for idx, sub in enumerate(subsidiaries, start=1):
            ent_name = str(sub.get("entity_name") or "").strip()
            ent_curr = str(sub.get("input_currency") or "").strip().upper()
            reg_num = str(sub.get("company_reg_number") or "").strip() or None
            country = str(sub.get("country_of_inc") or "").strip() or None
            inc_date = self._parse_flexible_date(sub.get("date_of_inc"))
            acq_date = self._parse_flexible_date(sub.get("acquisition_date"))
            raw_pct = sub.get("ownership_pct")

            if not ent_name:
                raise ValueError(f"Subsidiary #{idx}: Entity name is mandatory.")
            if not ent_curr:
                raise ValueError(f"Subsidiary #{idx}: Entity currency is mandatory.")
            if raw_pct is None or str(raw_pct).strip() == "":
                raise ValueError(f"Subsidiary #{idx}: Ownership percentage is mandatory.")
            try:
                pct_val = round(float(raw_pct), 2)
            except (TypeError, ValueError):
                raise ValueError(f"Subsidiary #{idx}: Ownership percentage must be a valid number.")
            if pct_val <= 0.0 or pct_val > 100.0:
                raise ValueError(f"Subsidiary #{idx}: Ownership percentage must be between 0.01% and 100.00%.")
            if acq_date is None:
                raise ValueError(f"Subsidiary #{idx}: Acquisition date is mandatory.")

            existing_code = str(sub.get("entity_code") or "").strip().upper()
            if existing_code and existing_code not in used_codes:
                ent_code = existing_code
                used_codes.add(ent_code)
            else:
                ent_code = self._generate_entity_code(ent_name, idx, used_codes)

            holding_ratio = round(pct_val / 100.0, 4)
            hierarchy.add_entity(
                LegalEntity(
                    entity_code=ent_code,
                    entity_name=ent_name,
                    entity_short_name=ent_code,
                    company_reg_number=reg_num,
                    country_of_inc=country,
                    date_of_inc=inc_date,
                    input_currency=ent_curr,
                    parent_entity_code=clean_code,
                    immediate_parent=clean_code,
                    ultimate_parent=clean_code,
                    holding_percentage=holding_ratio,
                    acquisition_date=acq_date,
                    consolidation_method="Full Consolidation" if holding_ratio > 0.5 else "Equity Method",
                )
            )

        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if existing:
            resolved_coa = coa if coa is not None else existing.group_coa
            resolved_coa_fn = coa_filename if coa is not None else existing.coa_filename
            resolved_coa_ts = now_ts if coa is not None else existing.coa_uploaded_at
            profile = CompanyProfile(
                company_id=target_id,
                company_code=clean_code,
                company_name=clean_name,
                reporting_currency=clean_curr,
                current_period=existing.current_period,
                number_of_subsidiaries=len(subsidiaries),
                coa_filename=resolved_coa_fn,
                coa_uploaded_at=resolved_coa_ts,
                group_coa=resolved_coa,
                entity_hierarchy=hierarchy,
                fx_tables_by_date=existing.fx_tables_by_date,
                historical_mappings=existing.historical_mappings,
                period_statuses=existing.period_statuses,
                created_at=existing.created_at,
                updated_at=now_ts,
            )
        else:
            if coa is None:
                raise ValueError("Default Chart of Accounts file is mandatory for creating a profile.")
            profile = CompanyProfile(
                company_id=target_id,
                company_code=clean_code,
                company_name=clean_name,
                reporting_currency=clean_curr,
                current_period=None,
                number_of_subsidiaries=len(subsidiaries),
                coa_filename=coa_filename,
                coa_uploaded_at=now_ts,
                group_coa=coa,
                entity_hierarchy=hierarchy,
                fx_tables_by_date={},
                historical_mappings=[],
                created_at=now_ts,
                updated_at=now_ts,
            )

        self.save_company(profile)
        cdir = self._company_dir(target_id)
        pdata = json.loads((cdir / "profile.json").read_text(encoding="utf-8"))
        return self._build_company_summary(cdir, pdata)

    def delete_company(self, company_id: str) -> bool:
        """Deletes a company workspace directory cleanly."""
        cdir = self._company_dir(company_id)
        if not cdir.exists():
            return False
        shutil.rmtree(cdir)
        return True

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
