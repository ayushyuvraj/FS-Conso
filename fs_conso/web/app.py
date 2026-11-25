"""Production-Hardened FastAPI backend server for the Consolidation Portal.

Connects the web frontend directly to the LangGraph consolidation agent.
Zero simulations: all operations execute real accounting and agent workflows.
"""

import asyncio
import csv
import io
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from fs_conso.agent.graph import build_consolidation_graph
from fs_conso.agent.state import ConsolidationState
from fs_conso.config import config
from fs_conso.core.coa_parser import COAParser
from fs_conso.core.company_manager import company_manager
import pandas as pd
from fs_conso.core.file_classifier import FileClassifier, ClassifiedFile
from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.core.elimination_engine import IntercompanyEliminationEngine
from fs_conso.models.entity import EntityHierarchy
from fs_conso.core.lineage_tracker import LineageTracker
from fs_conso.core.loader import ConsoMasterLoader, get_active_profile, load_coa_for_company, load_entity_hierarchy_for_company, load_fx_rates_for_company, load_mappings_for_company
from fs_conso.core.sample_generator import generate_benchmark_dataset, load_benchmark_raw_tbs
from fs_conso.core.statement_builder import FinancialStatementBuilder
from fs_conso.core.translator import FXTranslationEngine
from fs_conso.core.validator import TBValidator
from fs_conso.models.fx import FXRateEntry, FXRateTable
from fs_conso.core.run_manager import run_manager

app = FastAPI(
    title="Enterprise Financial Consolidation Portal",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)

# 1. CORS Hardening
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# 2. Defense-in-Depth Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Credential Redaction Helper
def sanitize_error_message(msg: str) -> str:
    """Prevents API key reflection in exception logs, client responses, and audit trails."""
    if not msg:
        return ""
    sanitized = re.sub(r"AIza[0-9A-Za-z_-]{15,}", "AIzaSy[REDACTED_API_KEY]", str(msg))
    sanitized = re.sub(r"(key|api_key|token)=([^&\s]+)", r"\1=[REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"(x-goog-api-key:\s*)([^\s]+)", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized

# Global execution lock to prevent session race conditions
pipeline_lock = asyncio.Lock()

# In-memory session manager with clean multi-company reset capability
class SessionManager:
    def __init__(self):
        self.active_company_id: Optional[str] = None
        self.active_run_id: Optional[str] = None
        self.active_run_name: Optional[str] = None
        self.is_launcher_active: bool = True
        self.state: Optional[ConsolidationState] = None
        self.graph = build_consolidation_graph()
        self.is_running: bool = False
        self.current_stage: Optional[str] = None
        self.current_node: Optional[str] = None
        companies = company_manager.list_companies()
        if companies:
            self.initialize_company(companies[0]["company_id"], load_samples=False)
            self.is_launcher_active = True

    def initialize_company(self, company_id: Optional[str], load_samples: bool = False):
        if not company_id:
            self.active_company_id = None
            self.active_run_id = None
            self.active_run_name = None
            self.state = None
            self.is_running = False
            self.current_stage = None
            self.current_node = None
            return

        prof = company_manager.get_company(company_id)
        if not prof:
            companies = company_manager.list_companies()
            if not companies:
                self.active_company_id = None
                self.active_run_id = None
                self.active_run_name = None
                self.state = None
                self.is_running = False
                self.current_stage = None
                self.current_node = None
                return
            prof = company_manager.get_company(companies[0]["company_id"])

        self.active_company_id = prof.company_id
        self.state = ConsolidationState(
            company_id=self.active_company_id,
            period=prof.current_period or "",
            raw_tbs=[],
            current_step=1,
            completed_steps=[],
            is_blocked=False,
            error_message=None
        )
        self.is_running = False
        self.current_stage = None
        self.current_node = None

    def initialize_baseline(self):
        self.initialize_company(self.active_company_id, load_samples=False)

    def reset(self):
        """Completely restores pristine baseline state for active company."""
        self.initialize_company(self.active_company_id, load_samples=False)

session = SessionManager()

# Mount static files and templates
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = Path(__file__).parent / "templates" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return index_file.read_text(encoding="utf-8")

@app.get("/api/status")
async def get_status():
    """Returns portal state, active company info, API key status, and current step without secret leaks."""
    has_key = config.validate_api_key_strict()
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None

    if session.is_launcher_active or prof is None:
        return {
            "has_active_api_key": has_key,
            "masked_api_key": config.get_masked_api_key(),
            "active_company_id": None,
            "active_company_code": None,
            "active_company_name": None,
            "active_run_id": None,
            "active_run_name": None,
            "is_launcher_active": True,
            "current_period": None,
            "reporting_currency": None,
            "ai_confidence_threshold": config.ai_confidence_threshold,
            "ic_absolute_tolerance": config.ic_absolute_tolerance,
            "ic_percent_tolerance": config.ic_percent_tolerance,
            "all_entities": [],
            "uploaded_entities": [],
            "missing_prerequisites": [],
            "hitl_pending_reviews": [],
            "current_step": 1,
            "completed_steps": [],
            "is_blocked": False,
            "error_message": None,
            "teacher_score": 0.0,
            "total_agent_traces": 0,
            "is_running": False,
            "current_stage": None,
            "current_node": None,
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "halted_node": None,
            "halted_stage": None,
            "remediation_items": [],
        }

    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    all_entity_codes = list(hierarchy.entities.keys()) if hierarchy.entities else []
    uploaded_entity_codes = [tb.entity_code for tb in session.state.raw_tbs] if session.state else []

    # Check for missing prerequisites
    missing_prereqs = []
    missing_tbs = [e for e in all_entity_codes if e not in uploaded_entity_codes]
    if missing_tbs:
        missing_prereqs.append(f"Missing Trial Balance for {len(missing_tbs)} active entities: {', '.join(missing_tbs[:3])}{'...' if len(missing_tbs)>3 else ''}")

    active_period = (session.state.period if session.state and session.state.period else prof.current_period) or None
    fx_table = prof.get_fx_table_for_period(active_period) if active_period else None
    missing_fx = FXTranslationEngine.check_missing_rates(list(hierarchy.entities.values()), fx_table, prof.reporting_currency)
    if missing_fx:
        missing_prereqs.append(f"Missing FX Rates{f' for {active_period}' if active_period else ''} ({', '.join(f'{f}->{t}' for f,t in missing_fx)})")

    if session.state:
        session.state.missing_prerequisites = missing_prereqs

    return {
        "has_active_api_key": has_key,
        "masked_api_key": config.get_masked_api_key(),
        "active_company_id": session.active_company_id,
        "active_company_code": prof.company_code or prof.company_id.upper(),
        "active_company_name": prof.company_name,
        "active_run_id": session.active_run_id,
        "active_run_name": session.active_run_name,
        "is_launcher_active": False,
        "current_period": active_period,
        "reporting_currency": prof.reporting_currency,
        "ai_confidence_threshold": config.ai_confidence_threshold,
        "ic_absolute_tolerance": config.ic_absolute_tolerance,
        "ic_percent_tolerance": config.ic_percent_tolerance,
        "all_entities": all_entity_codes,
        "uploaded_entities": uploaded_entity_codes,
        "missing_prerequisites": missing_prereqs,
        "hitl_pending_reviews": session.state.hitl_pending_reviews if session.state else [],
        "current_step": session.state.current_step if session.state else 1,
        "completed_steps": session.state.completed_steps if session.state else [],
        "is_blocked": session.state.is_blocked if session.state else False,
        "error_message": sanitize_error_message(session.state.error_message) if session.state and session.state.error_message else None,
        "teacher_score": session.state.teacher_score if session.state else 0.0,
        "total_agent_traces": len(session.state.agent_traces) if session.state else 0,
        "is_running": session.is_running,
        "current_stage": session.current_stage or (session.state.current_stage if session.state else None),
        "current_node": session.current_node or (session.state.current_node if session.state else None),
        "token_usage": session.state.token_usage if session.state else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "halted_node": session.state.halted_node if session.state else None,
        "halted_stage": session.state.halted_stage if session.state else None,
        "remediation_items": session.state.remediation_items if session.state else [],
    }

# 3. Input Validation Models with Strict Finite / Non-NaN Bounds
class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    ai_confidence_threshold: Optional[float] = None
    ic_absolute_tolerance: Optional[float] = None
    ic_percent_tolerance: Optional[float] = None

    @field_validator("ai_confidence_threshold")
    @classmethod
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if math.isnan(v) or math.isinf(v):
            raise ValueError("AI confidence threshold must be a finite number.")
        if not (0.0 <= v <= 1.0):
            raise ValueError("AI confidence threshold must be strictly between 0.0 and 1.0 (0% to 100%).")
        return round(v, 4)

    @field_validator("ic_absolute_tolerance")
    @classmethod
    def validate_abs_tolerance(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Intercompany absolute tolerance must be a finite number.")
        if v < 0.0:
            raise ValueError("Intercompany absolute tolerance cannot be negative.")
        if v > 100_000_000.0:
            raise ValueError("Intercompany absolute tolerance cannot exceed ₹100,000,000 / $100M cap.")
        return round(v, 2)

    @field_validator("ic_percent_tolerance")
    @classmethod
    def validate_pct_tolerance(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Intercompany percent tolerance must be a finite number.")
        if not (0.0 <= v <= 1.0):
            raise ValueError("Intercompany percent tolerance must be strictly between 0.0 and 1.0 (0% to 100%).")
        return round(v, 4)

    @field_validator("gemini_api_key")
    @classmethod
    def validate_api_key_str(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = v.strip()
        if not cleaned:
            return None
        if any(c in cleaned for c in ["\r", "\n", "\0", "\t"]):
            raise ValueError("API Key contains invalid control characters.")
        return cleaned

@app.post("/api/settings")
async def update_settings(update: SettingsUpdate):
    if update.gemini_api_key is not None:
        try:
            config.set_api_key_secure(update.gemini_api_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if update.ai_confidence_threshold is not None:
        config.ai_confidence_threshold = update.ai_confidence_threshold
    if update.ic_absolute_tolerance is not None:
        config.ic_absolute_tolerance = update.ic_absolute_tolerance
    if update.ic_percent_tolerance is not None:
        config.ic_percent_tolerance = update.ic_percent_tolerance

    return {
        "success": True,
        "has_active_api_key": config.validate_api_key_strict(),
        "masked_api_key": config.get_masked_api_key(),
        "ai_confidence_threshold": config.ai_confidence_threshold,
        "ic_absolute_tolerance": config.ic_absolute_tolerance,
        "ic_percent_tolerance": config.ic_percent_tolerance
    }

# 4. Safe State Recovery Endpoints
@app.post("/api/reset")
async def reset_portal_state():
    """Allows users to recover from corrupted states, unhandled exceptions, or bad uploads."""
    async with pipeline_lock:
        session.reset()
    return {"success": True, "message": "Portal state has been reset to clean baseline."}

@app.post("/api/reset-baseline")
async def reset_baseline():
    """Resets session state to the benchmark multi-entity model."""
    async with pipeline_lock:
        session.initialize_baseline()
    return {
        "success": True,
        "message": "Reset to benchmark multi-entity conglomerate fixture.",
        "entity_count": len(session.state.raw_tbs),
        "entities": [tb.entity_code for tb in session.state.raw_tbs]
    }

# --- Multi-Company Profile Endpoints ---

class SubsidiaryPayload(BaseModel):
    entity_code: Optional[str] = None
    entity_name: str
    company_reg_number: Optional[str] = None
    country_of_inc: Optional[str] = None
    date_of_inc: Optional[str] = None
    input_currency: str
    ownership_pct: float
    acquisition_date: str

    @field_validator("entity_name")
    @classmethod
    def validate_entity_name(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Entity name is mandatory.")
        return cleaned

    @field_validator("input_currency")
    @classmethod
    def validate_entity_currency(cls, v: str) -> str:
        cleaned = (v or "").strip().upper()
        if not cleaned:
            raise ValueError("Entity currency is mandatory.")
        return cleaned

    @field_validator("ownership_pct")
    @classmethod
    def validate_ownership_pct(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Ownership percentage must be a finite number.")
        if v <= 0.0 or v > 100.0:
            raise ValueError("Ownership percentage must be between 0.01% and 100.00%.")
        if abs(round(v, 2) - v) > 1e-6:
            raise ValueError("Ownership percentage supports up to 2 decimal places.")
        return round(v, 2)

    @field_validator("acquisition_date")
    @classmethod
    def validate_acquisition_date(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Acquisition date is mandatory.")
        return cleaned

class CompanyProfilePayload(BaseModel):
    company_name: str
    company_code: str
    reporting_currency: str
    number_of_subsidiaries: int = Field(0, ge=0, le=100)
    subsidiaries: List[SubsidiaryPayload] = Field(default_factory=list)

class CompanySwitchRequest(BaseModel):
    company_id: str

class CreateRunRequest(BaseModel):
    company_id: str
    run_date: str

class ResumeRunRequest(BaseModel):
    run_id: str
    company_id: Optional[str] = None

@app.get("/api/companies")
async def list_companies():
    """Lists all available client company profiles."""
    companies = company_manager.list_companies()
    return {"companies": companies, "active_company_id": session.active_company_id}

@app.get("/api/companies/coa-template")
async def download_coa_template():
    """Downloads a clean Excel template for a company's Base Chart of Accounts."""
    content = COAParser.generate_template_bytes()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="Base_Chart_of_Accounts_Template.xlsx"',
            "Cache-Control": "no-cache",
        },
    )

@app.post("/api/companies/switch")
async def switch_company(req: CompanySwitchRequest):
    """Switches active company workspace."""
    prof = company_manager.get_company(req.company_id)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Company profile '{req.company_id}' not found.")
    async with pipeline_lock:
        session.initialize_company(prof.company_id, load_samples=False)
    return {"success": True, "active_company_id": session.active_company_id}

@app.get("/api/runs")
async def list_consolidation_runs(company_id: Optional[str] = None):
    """Lists consolidation runs across companies or for a specific company."""
    runs = run_manager.list_runs(company_id)
    return {"runs": runs, "active_run_id": session.active_run_id}

@app.post("/api/runs/create")
async def create_new_run(req: CreateRunRequest):
    """Creates a fresh consolidation run record with sequential naming and initialized state."""
    prof = company_manager.get_company(req.company_id)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Company profile '{req.company_id}' not found.")
    async with pipeline_lock:
        rec = run_manager.create_run(prof.company_id, req.run_date)
        session.active_company_id = prof.company_id
        session.active_run_id = rec["run_id"]
        session.active_run_name = rec["run_name"]
        session.is_launcher_active = False
        session.initialize_company(prof.company_id, load_samples=False)
        session.state.period = req.run_date
        run_manager.save_run_state(prof.company_id, rec["run_id"], session.state)
    return {"success": True, "run": rec}

@app.post("/api/runs/resume")
async def resume_consolidation_run(req: ResumeRunRequest):
    """Resumes an existing consolidation run and restores full execution state."""
    rec = run_manager.get_run(req.run_id, req.company_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Run '{req.run_id}' not found.")
    async with pipeline_lock:
        company_id = rec["company_id"]
        prof = company_manager.get_company(company_id)
        if not prof:
            raise HTTPException(status_code=404, detail=f"Company profile '{company_id}' not found.")
        session.active_company_id = prof.company_id
        session.active_run_id = rec["run_id"]
        session.active_run_name = rec["run_name"]
        session.is_launcher_active = False
        
        state_dict = rec.get("state")
        if state_dict:
            try:
                session.state = ConsolidationState(**state_dict)
            except Exception:
                session.initialize_company(prof.company_id, load_samples=False)
                session.state.period = rec.get("run_date", "")
                session.state.current_step = rec.get("current_step", 1)
                session.state.completed_steps = rec.get("completed_steps", [])
        else:
            session.initialize_company(prof.company_id, load_samples=False)
            session.state.period = rec.get("run_date", "")
            session.state.current_step = rec.get("current_step", 1)
            session.state.completed_steps = rec.get("completed_steps", [])

        target_step = session.state.current_step or 1
        return {
            "success": True,
            "run_id": session.active_run_id,
            "run_name": session.active_run_name,
            "company_id": session.active_company_id,
            "company_name": prof.company_name,
            "run_date": rec.get("run_date", ""),
            "reporting_currency": prof.reporting_currency,
            "current_step": target_step,
            "completed_steps": session.state.completed_steps,
            "is_completed": rec.get("is_completed", False),
        }

@app.post("/api/runs/launcher-mode")
async def enter_launcher_mode():
    """Puts session in fresh run launcher mode with cleared top bar."""
    session.is_launcher_active = True
    session.active_run_id = None
    session.active_run_name = None
    return {"success": True, "is_launcher_active": True}

def _read_and_parse_coa_upload(file_bytes: bytes, raw_filename: str):
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded Chart of Accounts file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"COA file exceeds maximum {MAX_FILE_SIZE // (1024*1024)}MB limit.")
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", (raw_filename or "coa.xlsx").replace("\\", "/").split("/")[-1])
    try:
        coa = COAParser.parse_file(file_bytes, safe_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse Chart of Accounts: {sanitize_error_message(str(exc))}")
    return coa, safe_name

@app.post("/api/companies/create")
async def create_company(
    profile_json: str = Form(...),
    coa_file: UploadFile = File(...),
):
    """Creates a new company profile with parent metadata, N subsidiaries, and mandatory Base COA."""
    try:
        payload = CompanyProfilePayload(**json.loads(profile_json))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid profile payload: {sanitize_error_message(str(exc))}")

    if len(payload.subsidiaries) != payload.number_of_subsidiaries:
        raise HTTPException(
            status_code=400,
            detail=f"Expected {payload.number_of_subsidiaries} subsidiary record(s), received {len(payload.subsidiaries)}."
        )

    coa_bytes = await coa_file.read()
    coa, safe_coa_name = _read_and_parse_coa_upload(coa_bytes, coa_file.filename or "coa.xlsx")

    try:
        summary = company_manager.create_or_update_profile(
            company_name=payload.company_name,
            company_code=payload.company_code,
            reporting_currency=payload.reporting_currency,
            subsidiaries=[s.model_dump() for s in payload.subsidiaries],
            coa=coa,
            coa_filename=safe_coa_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    async with pipeline_lock:
        session.initialize_company(summary["company_id"], load_samples=False)
    return {"success": True, "company": summary}

@app.put("/api/companies/{company_id}")
async def update_company(
    company_id: str,
    profile_json: str = Form(...),
    coa_file: Optional[UploadFile] = File(None),
):
    """Updates an existing company profile, subsidiaries, and optionally replaces its Base COA."""
    try:
        payload = CompanyProfilePayload(**json.loads(profile_json))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid profile payload: {sanitize_error_message(str(exc))}")

    if len(payload.subsidiaries) != payload.number_of_subsidiaries:
        raise HTTPException(
            status_code=400,
            detail=f"Expected {payload.number_of_subsidiaries} subsidiary record(s), received {len(payload.subsidiaries)}."
        )

    coa = None
    safe_coa_name = None
    if coa_file is not None and coa_file.filename:
        coa_bytes = await coa_file.read()
        if len(coa_bytes) > 0:
            coa, safe_coa_name = _read_and_parse_coa_upload(coa_bytes, coa_file.filename)

    try:
        summary = company_manager.create_or_update_profile(
            company_name=payload.company_name,
            company_code=payload.company_code,
            reporting_currency=payload.reporting_currency,
            subsidiaries=[s.model_dump() for s in payload.subsidiaries],
            coa=coa,
            coa_filename=safe_coa_name,
            existing_company_id=company_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if session.active_company_id and session.active_company_id.lower() in (company_id.lower(), summary["company_id"].lower()):
        async with pipeline_lock:
            session.initialize_company(summary["company_id"], load_samples=False)
    return {"success": True, "company": summary}

@app.delete("/api/companies/{company_id}")
async def delete_company(company_id: str):
    """Deletes a company profile workspace."""
    deleted = company_manager.delete_company(company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Company profile '{company_id}' not found.")

    async with pipeline_lock:
        if session.active_company_id and session.active_company_id.lower() == company_id.lower():
            remaining = company_manager.list_companies()
            next_id = remaining[0]["company_id"] if remaining else None
            session.initialize_company(next_id, load_samples=False)
    return {"success": True, "active_company_id": session.active_company_id}

@app.post("/api/companies/import-master")
async def import_master_workbook(
    file: UploadFile = File(...),
    company_id: str = Form(...),
    company_name: str = Form(...)
):
    """Imports master setup from a multi-tab Excel file (like Conso.xlsx)."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum size limit of {MAX_FILE_SIZE // (1024*1024)}MB.")

    safe_fn = re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename.split("/")[-1].split("\\")[-1])
    upload_dir = (config.inputs_dir / "uploads").resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f"master_{safe_fn}"
    if not temp_path.resolve().is_relative_to(upload_dir):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    temp_path.write_bytes(content)

    prof = company_manager.import_master_workbook(
        conso_path=temp_path,
        company_id=company_id,
        company_name=company_name
    )
    async with pipeline_lock:
        session.initialize_company(prof.company_id, load_samples=False)
    return {"success": True, "company_id": prof.company_id, "entities_count": len(prof.entity_hierarchy.entities) if prof.entity_hierarchy else 0}

# --- Batch Upload & Agentic Ingestion ---

@app.post("/api/upload-batch")
async def upload_batch(
    files: List[UploadFile] = File(...),
    period: Optional[str] = Form(None)
):
    """Accepts a batch of 10-15+ files and autonomously classifies & ingests each."""
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    if prof is None:
        raise HTTPException(status_code=400, detail="No active Company Profile found. Please create a Company Profile first.")
    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    known_ents = list(hierarchy.entities.keys()) if hierarchy.entities else []
    target_period = period or prof.current_period or config.current_period

    files_data = []
    for f in files:
        b = await f.read()
        if len(b) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File '{f.filename}' exceeds maximum {MAX_FILE_SIZE // (1024*1024)}MB limit.")
        safe_n = re.sub(r"[^a-zA-Z0-9_.-]", "_", f.filename.split("/")[-1].split("\\")[-1])
        files_data.append((safe_n, b))

    classified_files = FileClassifier.classify_batch(files_data, expected_period=target_period, known_entities=known_ents)
    
    ingested_tbs = []
    ingested_fx = 0
    ingested_ic = 0
    pending_reviews = []

    async with pipeline_lock:
        for cf, (_, file_bytes) in zip(classified_files, files_data):
            if cf.file_type in ("CURRENT_TB", "PRIOR_TB") and cf.entity_code:
                try:
                    raw_tb = FlexibleTBParser.parse_file(
                        file_path_or_bytes=file_bytes,
                        filename=cf.filename,
                        entity_code=cf.entity_code,
                        period=cf.period or target_period,
                        currency=cf.currency or "INR"
                    )
                    raw_tb.is_prior_period = (cf.file_type == "PRIOR_TB")
                    
                    replaced = False
                    for i, existing in enumerate(session.state.raw_tbs):
                        if existing.entity_code == raw_tb.entity_code and existing.is_prior_period == raw_tb.is_prior_period:
                            session.state.raw_tbs[i] = raw_tb
                            replaced = True
                            break
                    if not replaced:
                        session.state.raw_tbs.append(raw_tb)
                    ingested_tbs.append(cf.entity_code)
                except Exception as e:
                    cf.needs_review = True
                    cf.reasoning += f" (Ingestion error: {str(e)})"

            elif cf.file_type == "FX_RATES":
                try:
                    df = pd.read_excel(io.BytesIO(file_bytes))
                    fx_table = FXRateTable()
                    for _, r in df.iterrows():
                        from_c = str(r.get("From Currency", r.get("from_currency", ""))).strip().upper()
                        to_c = str(r.get("To Currency", r.get("to_currency", prof.reporting_currency))).strip().upper()
                        cr = float(r.get("Closing", r.get("closing_rate", 1.0)))
                        ar = float(r.get("Average", r.get("average_rate", 1.0)))
                        hr = float(r.get("Historical", r.get("historical_rate", 1.0)))
                        if from_c:
                            fx_table.add_rate(FXRateEntry(
                                from_currency=from_c,
                                to_currency=to_c,
                                as_on_date=target_period,
                                closing_rate=cr,
                                average_rate=ar,
                                historical_rate=hr
                            ))
                    prof.set_fx_table_for_period(target_period, fx_table)
                    company_manager.save_company(prof)
                    ingested_fx += 1
                except Exception:
                    pass

            elif cf.file_type == "INTERCOMPANY_SCHEDULE":
                try:
                    pairs = IntercompanyEliminationEngine.parse_uploaded_ic_file(file_bytes, cf.filename)
                    session.state.uploaded_ic_pairs.extend(pairs)
                    ingested_ic += len(pairs)
                except Exception:
                    pass

            if cf.needs_review:
                pending_reviews.append({
                    "filename": cf.filename,
                    "detected_type": cf.file_type,
                    "entity_code": cf.entity_code,
                    "confidence": cf.confidence,
                    "reasoning": cf.reasoning
                })

        session.state.current_step = 1
        session.state.completed_steps = []

    return {
        "success": True,
        "total_files": len(files),
        "ingested_tbs": ingested_tbs,
        "ingested_fx": ingested_fx,
        "ingested_ic_pairs": ingested_ic,
        "pending_reviews": pending_reviews,
        "classified_summary": [
            {
                "filename": cf.filename,
                "file_type": cf.file_type,
                "entity_code": cf.entity_code,
                "confidence": cf.confidence,
                "needs_review": cf.needs_review,
                "reasoning": cf.reasoning
            }
            for cf in classified_files
        ]
    }

# --- Human-in-the-Loop (HITL) Workbench Endpoints ---

class HITLResolveRequest(BaseModel):
    entity_code: str
    local_code: str
    group_code: str
    reasoning: Optional[str] = "User approved in HITL workbench"

@app.get("/api/hitl/pending")
async def get_hitl_pending():
    """Returns items needing Human-in-the-Loop review & learning memory suggestions."""
    reviews = session.state.hitl_pending_reviews if session.state else []
    return {"pending_reviews": reviews, "threshold": config.ai_confidence_threshold}

@app.post("/api/hitl/resolve")
async def resolve_hitl_item(req: HITLResolveRequest):
    """Applies human review decision and commits it into Learning Memory."""
    prof = company_manager.get_company(session.active_company_id)
    if prof:
        prof.add_mapping(req.entity_code, req.local_code, req.group_code)
        company_manager.save_company(prof)

    async with pipeline_lock:
        if session.state:
            for d in session.state.mapping_decisions:
                if d.local_code == req.local_code:
                    d.group_code = req.group_code
                    d.method = "USER_APPROVED_RULE"
                    d.confidence = 1.0
                    d.needs_review = False
                    d.reasoning = req.reasoning
            session.state.hitl_pending_reviews = [
                r for r in session.state.hitl_pending_reviews
                if r.get("local_code") != req.local_code
            ]
            if not session.state.hitl_pending_reviews:
                session.state.halted_node = None
                session.state.remediation_items = []

    return {"success": True, "message": f"Mapping for '{req.local_code}' saved to learning memory."}

# 5. Production-Hardened File Upload Endpoint
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB cap
CHUNK_SIZE = 1024 * 1024          # 1 MB chunk buffer
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
RESERVED_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
    "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3"
}

@app.post("/api/upload-tb")
async def upload_trial_balance(
    file: UploadFile = File(...),
    entity_code: str = Form(...),
    period: Optional[str] = Form(None),
    currency: Optional[str] = Form("INR")
):
    """Secure file upload with path traversal defense, magic byte checks, and stream size capping."""
    raw_filename = file.filename or "unknown.xlsx"

    # A. Path Traversal & Sanitization
    if ".." in raw_filename or "/" in raw_filename or "\\" in raw_filename or "\x00" in raw_filename:
        raise HTTPException(status_code=400, detail="Invalid filename: Directory traversal characters detected.")

    safe_name = raw_filename.replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", safe_name)
    ext = Path(safe_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Only .xlsx, .xls, and .csv are allowed."
        )

    stem = Path(safe_name).stem.upper()
    if stem in RESERVED_DEVICE_NAMES:
        safe_name = f"upload_{safe_name}"

    # B. Streaming Chunk Inspection (Max 25MB)
    total_bytes = 0
    content = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size cap of {MAX_FILE_SIZE / (1024 * 1024):.0f}MB."
            )
        content.extend(chunk)

    if total_bytes == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    # C. File Content-Type & Magic Byte Signature Verification
    if ext == ".xlsx":
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(status_code=400, detail="File signature mismatch: Not a valid .xlsx spreadsheet.")
    elif ext == ".xls":
        if not content.startswith(b"\xD0\xCF\x11\xE0"):
            raise HTTPException(status_code=400, detail="File signature mismatch: Not a valid legacy .xls workbook.")
    elif ext == ".csv":
        if content.startswith(b"MZ") or content.startswith(b"\x7fELF"):
            raise HTTPException(status_code=400, detail="Security violation: Executable payload detected.")
        if b"\x00" in content[:4096]:
            raise HTTPException(status_code=400, detail="Invalid CSV format: Binary null bytes detected.")

    # D. Ingestion & Accounting Validation
    target_period = (period or config.current_period).strip()
    target_entity = re.sub(r"[^a-zA-Z0-9_-]", "", entity_code.strip().upper())
    if not target_entity:
        raise HTTPException(status_code=400, detail="Invalid entity code provided.")
    target_currency = (currency or config.reporting_currency).strip().upper()

    try:
        raw_tb = FlexibleTBParser.parse_file(
            file_path_or_bytes=bytes(content),
            filename=safe_name,
            entity_code=target_entity,
            period=target_period,
            currency=target_currency
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse trial balance: {sanitize_error_message(str(exc))}")

    # Validate parsed trial balance
    val_res = TBValidator.validate(raw_tb, expected_period=target_period, expected_entity=target_entity)

    # Save copy to inputs/uploads
    upload_dir = (config.project_root / "inputs" / "uploads").resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_dest = upload_dir / f"{target_entity}_{safe_name}"
    if not save_dest.resolve().is_relative_to(upload_dir):
        raise HTTPException(status_code=400, detail="Invalid destination path.")
    save_dest.write_bytes(bytes(content))

    # Synchronize into session
    async with pipeline_lock:
        if not session.state:
            if not session.active_company_id:
                raise HTTPException(status_code=400, detail="No active Company Profile found. Please create a Company Profile first.")
            session.initialize_company(session.active_company_id, load_samples=False)
        replaced = False
        for i, existing in enumerate(session.state.raw_tbs):
            if existing.entity_code.strip().upper() == target_entity:
                session.state.raw_tbs[i] = raw_tb
                replaced = True
                break
        if not replaced:
            session.state.raw_tbs.append(raw_tb)

        session.state.current_step = 1
        session.state.completed_steps = []
        session.state.is_blocked = False
        session.state.error_message = None

    return {
        "success": True,
        "message": f"Successfully ingested {len(raw_tb.rows)} rows for '{target_entity}'.",
        "entity_code": target_entity,
        "row_count": len(raw_tb.rows),
        "total_debit": raw_tb.total_debit,
        "total_credit": raw_tb.total_credit,
        "is_tallied": abs(raw_tb.total_signed_amount or (raw_tb.total_debit - raw_tb.total_credit)) < 0.01,
        "validation_result": val_res.dict(),
        "total_entities": len(session.state.raw_tbs)
    }

# 6. Fault-Tolerant Pipeline Invocation
@app.post("/api/run-pipeline")
async def run_pipeline():
    """Executes the full multi-agent LangGraph consolidation pipeline with fault recovery."""
    if not config.validate_api_key_strict():
        raise HTTPException(
            status_code=403,
            detail="MANDATORY GATE ERROR: Active Google Gemini API Key required to run the consolidation engine. Click Settings (top right) to configure."
        )

    async with pipeline_lock:
        if not session.active_company_id:
            raise HTTPException(status_code=400, detail="No active Company Profile found. Please create a Company Profile first.")
        if not session.state:
            session.initialize_company(session.active_company_id, load_samples=False)

        session.state.company_id = session.active_company_id
        prof = company_manager.get_company(session.active_company_id)
        if prof and not session.state.period:
            session.state.period = prof.current_period or config.current_period

        # Clear prior transient block and flag active run
        session.state.is_blocked = False
        session.state.error_message = None
        session.is_running = True
        session.current_stage = "Initiating multi-agent consolidation..."
        session.current_node = "validator"

        try:
            # Execute synchronous LangGraph engine in worker threadpool to keep event loop responsive
            result = await asyncio.to_thread(session.graph.invoke, session.state)
            session.state = ConsolidationState(**result)
            session.current_stage = "Consolidation complete."
            session.current_node = None
        except Exception as exc:
            err_msg = sanitize_error_message(str(exc))
            session.state.is_blocked = True
            session.state.error_message = f"Agent Execution Error: {err_msg}"
            session.state.halted_node = session.current_node or "pipeline"
            session.state.halted_stage = session.current_stage or "Execution Failure"
            session.state.remediation_items = [
                f"Execution failed at {session.state.halted_node}: {err_msg}",
                "Check that GEMINI_API_KEY is configured with valid quota.",
                "Verify trial balance input sheets are clean and balanced.",
                "Click 'Reset to Baseline' to restore standard multi-entity benchmark."
            ]
            session.current_stage = f"Execution failed: {err_msg}"
            session.current_node = None
            raise HTTPException(status_code=500, detail=f"Consolidation pipeline failed: {err_msg}")
        finally:
            if session.active_company_id and session.active_run_id and session.state:
                run_manager.save_run_state(session.active_company_id, session.active_run_id, session.state)
            session.is_running = False

    return {
        "success": not session.state.is_blocked,
        "current_step": session.state.current_step,
        "completed_steps": session.state.completed_steps,
        "teacher_score": session.state.teacher_score,
        "teacher_evaluation": session.state.teacher_evaluation,
        "error_message": session.state.error_message,
        "token_usage": session.state.token_usage,
        "halted_node": session.state.halted_node,
        "halted_stage": session.state.halted_stage,
        "remediation_items": session.state.remediation_items,
        "audit_trail_count": len(session.state.audit_trail),
        "output_file": session.state.output_excel_path
    }

@app.get("/api/pipeline-data")
async def get_pipeline_data():
    """Returns detailed financial matrices for the active step view with redacted errors."""
    if not session.state:
        return {
            "current_step": 1,
            "completed_steps": [],
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "halted_node": None,
            "halted_stage": None,
            "remediation_items": [],
            "raw_tbs": [],
            "validation_results": [],
            "mapping_decisions": [],
            "translated_tbs": [],
            "eliminations": None,
            "consolidated_tb": None,
            "audit_trail": [],
            "teacher_evaluation": {},
            "agent_traces": [],
        }

    st = session.state
    safe_mapping_decisions = []
    for d in st.mapping_decisions[:50]:
        d_dict = d.dict()
        if d_dict.get("reasoning"):
            d_dict["reasoning"] = sanitize_error_message(d_dict["reasoning"])
        safe_mapping_decisions.append(d_dict)

    return {
        "current_step": st.current_step,
        "completed_steps": st.completed_steps,
        "token_usage": st.token_usage,
        "halted_node": st.halted_node,
        "halted_stage": st.halted_stage,
        "remediation_items": st.remediation_items,
        "raw_tbs": [
            {
                "entity_code": tb.entity_code,
                "period": tb.period,
                "currency": tb.currency,
                "row_count": len(tb.rows),
                "total_debit": tb.total_debit,
                "total_credit": tb.total_credit,
                "signed_sum": tb.total_signed_amount or round(tb.total_debit - tb.total_credit, 2),
                "is_tallied": abs(tb.total_signed_amount or (tb.total_debit - tb.total_credit)) < 0.01
            }
            for tb in st.raw_tbs
        ],
        "validation_results": [r.dict() for r in st.validation_results],
        "mapping_decisions": safe_mapping_decisions,
        "translated_tbs": [
            {
                "entity_code": tb.entity_code,
                "currency": tb.reporting_currency,
                "total_translated": tb.total_translated,
                "has_fctr": tb.fctr_row is not None,
                "fctr_amount": tb.fctr_row.translated_amount if tb.fctr_row else 0.0,
                "rows": [r.dict() for r in tb.rows[:15]]
            }
            for tb in st.translated_tbs
        ],
        "eliminations": st.elimination_result.dict() if st.elimination_result else None,
        "consolidated_tb": {
            "period": st.consolidated_tb.period,
            "currency": st.consolidated_tb.currency,
            "entity_codes": st.consolidated_tb.entity_codes,
            "total_consolidated": st.consolidated_tb.total_consolidated,
            "rows": [r.dict() for r in st.consolidated_tb.rows]
        } if st.consolidated_tb else None,
        "audit_trail": [
            {**ev, "details": sanitize_error_message(ev.get("details", ""))}
            for ev in st.audit_trail
        ],
        "teacher_evaluation": st.teacher_evaluation,
        "agent_traces": [t.dict() for t in st.agent_traces]
    }

@app.get("/api/agent-traces")
async def get_agent_traces():
    """Returns real LangGraph runtime execution traces with node latencies and sanitized state deltas."""
    if not session.state:
        return {"traces": [], "total_nodes_executed": 0, "total_latency_ms": 0.0}
    sanitized_traces = []
    for t in session.state.agent_traces:
        td = t.dict()
        td["input_summary"] = sanitize_error_message(td.get("input_summary", ""))
        td["output_summary"] = sanitize_error_message(td.get("output_summary", ""))
        td["details"] = sanitize_error_message(td.get("details", ""))
        td["token_usage"] = t.token_usage
        sanitized_traces.append(td)
    return {
        "traces": sanitized_traces,
        "total_nodes_executed": len(sanitized_traces),
        "total_latency_ms": round(sum(t.execution_time_ms for t in session.state.agent_traces), 2)
    }

@app.get("/api/financial-statements")
async def get_financial_statements():
    """Returns structured IND AS Consolidated Balance Sheet & P&L matrices."""
    if not session.state or not session.state.consolidated_tb:
        return {
            "success": False,
            "message": "Consolidation not executed yet. Run consolidation pipeline to generate statements.",
            "balance_sheet": None,
            "profit_and_loss": None
        }

    bs = FinancialStatementBuilder.build_balance_sheet(session.state.consolidated_tb)
    pl = FinancialStatementBuilder.build_profit_and_loss(session.state.consolidated_tb)
    return {
        "success": True,
        "period": session.state.consolidated_tb.period,
        "currency": session.state.consolidated_tb.currency,
        "balance_sheet": bs,
        "profit_and_loss": pl
    }

@app.get("/api/lineage")
async def get_cell_lineage_empty():
    """Handles lineage requests with empty query gracefully."""
    return {
        "success": False,
        "found": False,
        "query": "",
        "message": "Query parameter required to trace lineage. Example: /api/lineage/Cash"
    }

@app.get("/api/lineage/{query:path}")
async def get_cell_lineage(query: str):
    """Traces cell formula lineage backward from Statement line to Raw Client TB."""
    if not session.state:
        return {"success": False, "found": False, "query": query, "message": "No active consolidation run."}
    return LineageTracker.trace_account(query, session.state)

def sanitize_csv_cell(val: Any) -> str:
    """Neutralizes formula injection characters (=, +, -, @, |, %, \\t, \\r) including leading whitespace."""
    if val is None:
        return ""
    s = str(val)
    s_clean = s.lstrip()
    if s_clean and s_clean[0] in ("=", "+", "-", "@", "|", "%", "\t", "\r"):
        return f"'{s}"
    return s

@app.get("/api/audit-trail/export")
async def export_audit_trail(format: str = "json"):
    """Exports full audit trail and agent traces as downloadable JSON or CSV with formula defense."""
    if not session.state:
        raise HTTPException(status_code=400, detail="No consolidation run data available to export.")

    audit_data = [
        {**ev, "details": sanitize_error_message(ev.get("details", ""))}
        for ev in session.state.audit_trail
    ]

    sanitized_traces = []
    for t in session.state.agent_traces:
        td = t.dict()
        td["input_summary"] = sanitize_error_message(td.get("input_summary", ""))
        td["output_summary"] = sanitize_error_message(td.get("output_summary", ""))
        td["details"] = sanitize_error_message(td.get("details", ""))
        td["token_usage"] = t.token_usage
        sanitized_traces.append(td)

    if format.lower() == "csv":
        import codecs
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["timestamp", "stage", "agent", "action", "status", "details"])
        writer.writeheader()
        for row in audit_data:
            writer.writerow({
                "timestamp": sanitize_csv_cell(row.get("timestamp", "")),
                "stage": sanitize_csv_cell(row.get("stage", "")),
                "agent": sanitize_csv_cell(row.get("agent", "")),
                "action": sanitize_csv_cell(row.get("action", "")),
                "status": sanitize_csv_cell(row.get("status", "")),
                "details": sanitize_csv_cell(row.get("details", ""))
            })
        csv_bytes = codecs.BOM_UTF8 + output.getvalue().encode("utf-8")
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="Consolidation_Audit_Trail.csv"',
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    else:
        json_str = json.dumps({
            "period": config.current_period,
            "reporting_currency": config.reporting_currency,
            "teacher_score": session.state.teacher_score,
            "teacher_evaluation": session.state.teacher_evaluation,
            "audit_trail": audit_data,
            "agent_traces": sanitized_traces
        }, indent=2)
        return Response(
            content=json_str.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="Consolidation_Audit_Trail.json"',
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )

@app.get("/api/export-excel")
async def export_excel():
    """Downloads the generated 100% formula-linked Excel deliverable with strict path containment."""
    excel_path = (config.outputs_dir / "Consolidated_Financial_Statements.xlsx").resolve()

    if not excel_path.is_relative_to(config.outputs_dir.resolve()):
        raise HTTPException(status_code=403, detail="Access denied: Path traversal attempt detected.")

    if not excel_path.exists():
        if config.validate_api_key_strict():
            async with pipeline_lock:
                result = session.graph.invoke(session.state)
                session.state = ConsolidationState(**result)
        else:
            raise HTTPException(status_code=400, detail="Excel report not generated yet. Configure API key and run pipeline.")

    return FileResponse(
        path=str(excel_path),
        filename="Consolidated_Financial_Statements.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
