"""Consolidation Run persistence and lifecycle manager."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from fs_conso.agent.state import ConsolidationState
from fs_conso.config import config
from fs_conso.core.company_manager import CompanyManager, company_manager as default_company_manager


class RunSummary(BaseModel):
    """Lightweight metadata summary of a consolidation run for table listings."""
    run_id: str
    run_name: str
    company_id: str
    company_name: str
    company_code: str
    run_date: str
    reporting_currency: str
    current_step: int = 1
    completed_steps: List[int] = Field(default_factory=list)
    status: str = "IN_PROGRESS"  # "IN_PROGRESS", "HALTED", "COMPLETED"
    is_completed: bool = False
    entity_count: int = 0
    created_at: str
    updated_at: str


class RunManager:
    """Manages creation, execution logging, persistence, and resumption of multi-company consolidation runs."""

    def __init__(self, company_mgr: Optional[CompanyManager] = None):
        self.company_manager = company_mgr or default_company_manager
        self.workspaces_dir = self.company_manager.workspaces_dir

    def _runs_dir(self, company_id: str) -> Path:
        cdir = self.company_manager._company_dir(company_id)
        runs_dir = cdir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        return runs_dir

    def _get_next_run_number(self, company_id: str) -> int:
        runs_dir = self._runs_dir(company_id)
        max_num = 0
        for f in runs_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("run_name", "")
                match = re.search(r"-\s*Run\s+(\d+)\s*-", name, re.IGNORECASE)
                if match:
                    max_num = max(max_num, int(match.group(1)))
            except Exception:
                continue
        return max_num + 1

    def create_run(self, company_id: str, run_date: str) -> Dict[str, Any]:
        """Creates a fresh consolidation run record with sequential naming and initialized state."""
        prof = self.company_manager.get_company(company_id)
        if not prof:
            raise ValueError(f"Company profile '{company_id}' not found.")

        clean_date = str(run_date).strip()
        if not clean_date:
            clean_date = datetime.now().strftime("%Y-%m-%d")

        run_num = self._get_next_run_number(prof.company_id)
        run_name = f"{prof.company_name} - Run {run_num} - {clean_date}"
        
        # Clean slug for filename
        date_slug = re.sub(r"[^0-9a-zA-Z]+", "", clean_date)
        run_id = f"{prof.company_id}_run_{run_num}_{date_slug}"

        hierarchy = prof.entity_hierarchy
        entity_count = len(hierarchy.entities) if (hierarchy and hierarchy.entities) else 1

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial_state = ConsolidationState(
            company_id=prof.company_id,
            period=clean_date,
            raw_tbs=[],
            current_step=1,
            completed_steps=[],
            is_blocked=False,
            error_message=None
        )

        record = {
            "run_id": run_id,
            "run_name": run_name,
            "company_id": prof.company_id,
            "company_name": prof.company_name,
            "company_code": prof.company_code,
            "run_date": clean_date,
            "reporting_currency": prof.reporting_currency,
            "current_step": 1,
            "completed_steps": [],
            "status": "IN_PROGRESS",
            "is_completed": False,
            "entity_count": entity_count,
            "created_at": now_str,
            "updated_at": now_str,
            "state": initial_state.model_dump(),
        }

        runs_dir = self._runs_dir(prof.company_id)
        run_file = runs_dir / f"{run_id}.json"
        run_file.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return record

    def save_run_state(self, company_id: str, run_id: str, state: ConsolidationState) -> None:
        """Saves current state and updates execution status for a run."""
        runs_dir = self._runs_dir(company_id)
        run_file = runs_dir / f"{run_id}.json"
        if not run_file.exists():
            # If not found directly, attempt search across workspaces
            found = False
            for cdir in self.workspaces_dir.iterdir():
                if cdir.is_dir() and (cdir / "runs" / f"{run_id}.json").exists():
                    run_file = cdir / "runs" / f"{run_id}.json"
                    found = True
                    break
            if not found:
                return

        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
            data["current_step"] = state.current_step
            data["completed_steps"] = state.completed_steps
            is_done = 6 in state.completed_steps
            data["is_completed"] = is_done
            if is_done:
                data["status"] = "COMPLETED"
            elif state.is_blocked:
                data["status"] = "HALTED"
            else:
                data["status"] = "IN_PROGRESS"
            data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data["state"] = state.model_dump()
            run_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def get_run(self, run_id: str, company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a full run record by run_id."""
        if company_id:
            runs_dir = self._runs_dir(company_id)
            run_file = runs_dir / f"{run_id}.json"
            if run_file.exists():
                try:
                    return json.loads(run_file.read_text(encoding="utf-8"))
                except Exception:
                    return None

        # Search all workspaces if company_id is omitted or not found
        if self.workspaces_dir.exists():
            for cdir in self.workspaces_dir.iterdir():
                if cdir.is_dir():
                    candidate = cdir / "runs" / f"{run_id}.json"
                    if candidate.exists():
                        try:
                            return json.loads(candidate.read_text(encoding="utf-8"))
                        except Exception:
                            return None
        return None

    def list_runs(self, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all consolidation runs sorted chronologically (newest first)."""
        runs: List[Dict[str, Any]] = []

        dirs_to_scan = []
        if company_id:
            try:
                dirs_to_scan.append(self._runs_dir(company_id))
            except Exception:
                pass
        elif self.workspaces_dir.exists():
            for cdir in self.workspaces_dir.iterdir():
                if cdir.is_dir() and (cdir / "runs").is_dir():
                    dirs_to_scan.append(cdir / "runs")

        for rdir in dirs_to_scan:
            for f in rdir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    runs.append({
                        "run_id": data.get("run_id", f.stem),
                        "run_name": data.get("run_name", f.stem),
                        "company_id": data.get("company_id", ""),
                        "company_name": data.get("company_name", ""),
                        "company_code": data.get("company_code", ""),
                        "run_date": data.get("run_date", ""),
                        "reporting_currency": data.get("reporting_currency", "INR"),
                        "current_step": data.get("current_step", 1),
                        "completed_steps": data.get("completed_steps", []),
                        "status": data.get("status", "IN_PROGRESS"),
                        "is_completed": data.get("is_completed", False),
                        "entity_count": data.get("entity_count", 0),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    })
                except Exception:
                    continue

        return sorted(runs, key=lambda x: (x.get("created_at") or "", x.get("run_name") or ""), reverse=True)


run_manager = RunManager()
