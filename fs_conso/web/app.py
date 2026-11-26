"""Production-Hardened FastAPI backend server for the Consolidation Portal.

Connects the web frontend directly to the LangGraph consolidation agent.
Zero simulations: all operations execute real accounting and agent workflows.
"""

import asyncio
import csv
from datetime import datetime
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
from fs_conso.agent.state import ConsolidationState, AgentNodeTrace
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
        self.pending_approval_state: Optional[Dict[str, Any]] = None
        self.cached_file_bytes: Dict[str, bytes] = {}
        companies = company_manager.list_companies()
        if companies:
            self.initialize_company(companies[0]["company_id"], load_samples=False)
            self.is_launcher_active = True

    def initialize_company(self, company_id: Optional[str], load_samples: bool = False):
        self.pending_approval_state = None
        self.cached_file_bytes = {}
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
            "perimeter_entities": [],
            "missing_entities": [],
            "is_perimeter_complete": True,
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

    perimeter_entities = []
    if hierarchy and hierarchy.entities:
        for ent in hierarchy.entities.values():
            perimeter_entities.append({
                "entity_code": ent.entity_code,
                "entity_name": ent.entity_name,
                "input_currency": ent.input_currency,
                "holding_percentage": ent.holding_percentage,
                "is_parent": ent.is_parent
            })
    else:
        perimeter_entities.append({
            "entity_code": prof.company_code or "P",
            "entity_name": prof.company_name or "Parent Company",
            "input_currency": prof.reporting_currency or "INR",
            "holding_percentage": 1.0,
            "is_parent": True
        })

    if session.state:
        session.state.missing_prerequisites = missing_prereqs
        # Strict generic gating: if any mapping decision needs review, step 2 and subsequent steps cannot be completed
        if session.state.mapping_decisions and any(getattr(d, "needs_review", False) for d in session.state.mapping_decisions):
            if any(s >= 2 for s in session.state.completed_steps) or session.state.current_step > 2:
                session.state.completed_steps = [s for s in session.state.completed_steps if s < 2]
                session.state.current_step = min(session.state.current_step, 2)
                session.state.is_blocked = True
                session.state.halted_node = "mapper"
                session.state.halted_stage = "Chart of Accounts Standardization"

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
        "perimeter_entities": perimeter_entities,
        "all_entities": all_entity_codes,
        "uploaded_entities": uploaded_entity_codes,
        "missing_entities": missing_tbs,
        "is_perimeter_complete": len(missing_tbs) == 0,
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

def build_perimeter_approval_state(
    classified_files: List[ClassifiedFile],
    files_map: Dict[str, List[str]],
    prof: Any,
    target_period: str
) -> Dict[str, Any]:
    """Constructs a unified, editable Perimeter Ingestion Approval payload."""
    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    parent_code = hierarchy.parent_code or (prof.company_code or prof.company_id)
    parent_ent = hierarchy.get_entity(parent_code)
    parent_name = parent_ent.entity_name if parent_ent else (prof.company_name or parent_code)
    parent_curr = parent_ent.input_currency if parent_ent else prof.reporting_currency

    subsidiary_entities = [e for e in hierarchy.entities.values() if e.entity_code != parent_code]

    tb_map: Dict[str, ClassifiedFile] = {}
    fx_item: Optional[ClassifiedFile] = None
    unassigned_items: List[Dict[str, Any]] = []

    for cf in classified_files:
        if cf.file_type in ("CURRENT_TB", "PRIOR_TB") and cf.entity_code:
            code_upper = cf.entity_code.upper()
            if code_upper not in tb_map or cf.confidence > tb_map[code_upper].confidence:
                tb_map[code_upper] = cf
        elif cf.file_type == "FX_RATES":
            if not fx_item or cf.confidence > fx_item.confidence:
                fx_item = cf
        else:
            unassigned_items.append({
                "filename": cf.filename,
                "sheet_name": cf.sheet_name or "",
                "reasoning": cf.reasoning or "Unassigned extra sheet / document",
                "sample_rows": cf.sample_rows[:5]
            })

    # 1. Parent card
    parent_cf = tb_map.get(parent_code.upper())
    parent_matched = parent_cf is not None
    parent_obj = {
        "entity_code": parent_code,
        "entity_name": parent_name,
        "is_parent": True,
        "currency": parent_curr,
        "holding_pct": 100.0,
        "matched": parent_matched,
        "filename": parent_cf.filename if parent_cf else "",
        "sheet_name": parent_cf.sheet_name if parent_cf else (files_map.get(parent_cf.filename, ["Sheet1"])[0] if parent_cf and files_map.get(parent_cf.filename) else ""),
        "detected_columns": parent_cf.detected_columns if parent_cf else {
            "account_code": "Account Code", "account_description": "Description", "debit": "Debit", "credit": "Credit"
        },
        "sample_rows": parent_cf.sample_rows if parent_cf else [],
        "confidence": parent_cf.confidence if parent_cf else 0.0,
        "classification_method": parent_cf.classification_method if parent_cf else "NONE",
        "date_status": parent_cf.date_status if parent_cf else "MATCH",
        "detected_period": parent_cf.detected_period if parent_cf else target_period,
        "needs_review": parent_cf.needs_review if parent_cf else True,
        "reasoning": parent_cf.reasoning if parent_cf else "Trial balance not yet uploaded.",
        "denomination": parent_cf.denomination if parent_cf else "UNITS",
        "scale_multiplier": parent_cf.scale_multiplier if parent_cf else 1.0,
        "scale_instruction": parent_cf.scale_instruction if parent_cf else "Reported in exact absolute currency (multiplier 1.0)"
    }

    # 2. Subsidiaries cards
    subs_list = []
    for sub in subsidiary_entities:
        sub_cf = tb_map.get(sub.entity_code.upper())
        sub_matched = sub_cf is not None
        holding_pct = round(float(sub.holding_percentage or 1.0) * 100, 2)
        subs_list.append({
            "entity_code": sub.entity_code,
            "entity_name": sub.entity_name or sub.entity_code,
            "is_parent": False,
            "currency": sub.input_currency or prof.reporting_currency,
            "holding_pct": holding_pct,
            "matched": sub_matched,
            "filename": sub_cf.filename if sub_cf else "",
            "sheet_name": sub_cf.sheet_name if sub_cf else (files_map.get(sub_cf.filename, ["Sheet1"])[0] if sub_cf and files_map.get(sub_cf.filename) else ""),
            "detected_columns": sub_cf.detected_columns if sub_cf else {
                "account_code": "Account Code", "account_description": "Description", "debit": "Debit", "credit": "Credit"
            },
            "sample_rows": sub_cf.sample_rows if sub_cf else [],
            "confidence": sub_cf.confidence if sub_cf else 0.0,
            "classification_method": sub_cf.classification_method if sub_cf else "NONE",
            "date_status": sub_cf.date_status if sub_cf else "MATCH",
            "detected_period": sub_cf.detected_period if sub_cf else target_period,
            "needs_review": sub_cf.needs_review if sub_cf else True,
            "reasoning": sub_cf.reasoning if sub_cf else f"Trial balance for '{sub.entity_name}' not yet uploaded.",
            "denomination": sub_cf.denomination if sub_cf else "UNITS",
            "scale_multiplier": sub_cf.scale_multiplier if sub_cf else 1.0,
            "scale_instruction": sub_cf.scale_instruction if sub_cf else "Reported in exact absolute currency (multiplier 1.0)"
        })

    # 3. FX Rates card
    existing_fx = prof.get_fx_table_for_period(target_period)
    fx_matched = fx_item is not None or (existing_fx is not None and len(existing_fx.entries) > 0)
    fx_rates_preview = []
    if existing_fx:
        fx_rates_preview = [
            {"from_currency": e.from_currency, "to_currency": e.to_currency, "closing_rate": e.closing_rate, "average_rate": e.average_rate, "historical_rate": e.historical_rate, "swap_rate": e.swap_rate}
            for e in existing_fx.entries
        ]
    fx_obj = {
        "matched": fx_matched,
        "is_existing": existing_fx is not None and fx_item is None,
        "filename": fx_item.filename if fx_item else "",
        "sheet_name": fx_item.sheet_name if fx_item else "",
        "detected_columns": fx_item.detected_columns if fx_item else {
            "date": "as_on_date", "from_currency": "from_currency", "to_currency": "to_currency", "closing_rate": "closing_rate", "average_rate": "average_rate", "historical_rate": "historical_rate", "swap_rate": "swap_rate"
        },
        "sample_rows": fx_item.sample_rows if fx_item else [],
        "rates_preview": fx_rates_preview,
        "confidence": fx_item.confidence if fx_item else (1.0 if existing_fx else 0.0),
        "classification_method": fx_item.classification_method if fx_item else ("EXISTING" if existing_fx else "NONE"),
        "date_status": fx_item.date_status if fx_item else "MATCH",
        "detected_period": fx_item.detected_period if fx_item else target_period,
        "needs_review": fx_item.needs_review if fx_item else not fx_matched,
        "reasoning": fx_item.reasoning if fx_item else ("Active FX table loaded from profile." if existing_fx else "Exchange rates required for target period.")
    }

    all_matched = parent_matched and all(s["matched"] for s in subs_list) and fx_matched
    missing_entities = []
    if not parent_matched:
        missing_entities.append({"entity_code": parent_code, "entity_name": parent_name, "is_parent": True})
    for s in subs_list:
        if not s["matched"]:
            missing_entities.append({"entity_code": s["entity_code"], "entity_name": s["entity_name"], "is_parent": False})

    return {
        "target_period": target_period,
        "reporting_currency": prof.reporting_currency,
        "parent": parent_obj,
        "subsidiaries": subs_list,
        "fx_rates": fx_obj,
        "unassigned_items": unassigned_items,
        "missing_entities": missing_entities,
        "files_map": files_map,
        "available_files_and_sheets": files_map,
        "is_ready_to_confirm": all_matched
    }

@app.post("/api/upload-batch")
async def upload_batch(
    files: List[UploadFile] = File(...),
    period: Optional[str] = Form(None),
    use_deterministic: bool = Form(True),
    use_ai: bool = Form(True)
):
    """Accepts a batch of arbitrary Excel/CSV files and classifies them for perimeter approval."""
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    if prof is None:
        raise HTTPException(status_code=400, detail="No active Company Profile found. Please create or select a Company Profile first.")
    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    target_period = period or (session.state.period if session.state and session.state.period else None) or prof.current_period or config.current_period

    upload_dir = (config.project_root / "inputs" / "uploads").resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    files_data = []
    files_map: Dict[str, List[str]] = {}

    for f in files:
        b = await f.read()
        if len(b) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File '{f.filename}' exceeds maximum {MAX_FILE_SIZE // (1024*1024)}MB limit.")
        safe_n = re.sub(r"[^a-zA-Z0-9_.-]", "_", f.filename.split("/")[-1].split("\\")[-1])
        files_data.append((safe_n, b))
        session.cached_file_bytes[safe_n] = b

        # Persist to upload_dir
        disk_path = upload_dir / f"{session.active_company_id}_{safe_n}"
        disk_path.write_bytes(b)

        # Detect sheets
        if safe_n.lower().endswith((".xlsx", ".xls")):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
                files_map[safe_n] = list(wb.sheetnames)
                wb.close()
            except Exception:
                files_map[safe_n] = ["Sheet1"]
        else:
            files_map[safe_n] = ["Sheet1"]

    classified_files = FileClassifier.classify_batch(
        files=files_data,
        expected_period=target_period,
        known_entities=hierarchy,
        use_deterministic=use_deterministic,
        use_ai=use_ai,
        confidence_threshold=config.ai_confidence_threshold
    )

    approval_state = build_perimeter_approval_state(classified_files, files_map, prof, target_period)
    session.pending_approval_state = approval_state

    return {
        "success": True,
        "total_files": len(files),
        "approval_state": approval_state,
        "use_deterministic": use_deterministic,
        "use_ai": use_ai
    }

@app.get("/api/pipeline/ingestion-approval-state")
async def get_ingestion_approval_state():
    """Retrieves current Step 1 perimeter approval state."""
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    if prof is None:
        raise HTTPException(status_code=400, detail="No active Company Profile found.")
    target_period = (session.state.period if session.state and session.state.period else None) or prof.current_period or config.current_period

    if session.pending_approval_state:
        return {"success": True, "approval_state": session.pending_approval_state}

    # Generate baseline state from already ingested raw_tbs or profile
    files_map = {}
    for fn in session.cached_file_bytes:
        files_map[fn] = ["Sheet1"]

    synthetic_classified: List[ClassifiedFile] = []
    if session.state and session.state.raw_tbs:
        for tb in session.state.raw_tbs:
            synthetic_classified.append(ClassifiedFile(
                filename=tb.source_filename or f"{tb.entity_code}.xlsx",
                sheet_name="Sheet1",
                file_type="CURRENT_TB",
                entity_code=tb.entity_code,
                entity_name=tb.entity_name,
                period=tb.period,
                currency=tb.currency,
                confidence=1.0,
                classification_method="DETERMINISTIC",
                reasoning="Ingested trial balance loaded from active session.",
                detected_columns=tb.detected_columns or {},
                sample_rows=[[r.account_code, r.account_description, str(r.debit or ''), str(r.credit or ''), str(r.amount or '')] for r in tb.rows[:5]]
            ))

    state = build_perimeter_approval_state(synthetic_classified, files_map, prof, target_period)
    return {"success": True, "approval_state": state}

@app.post("/api/pipeline/single-entity-upload")
async def single_entity_upload(
    file: UploadFile = File(...),
    entity_code: str = Form(...),
    period: Optional[str] = Form(None),
    use_deterministic: bool = Form(True),
    use_ai: bool = Form(True)
):
    """Uploads and classifies a specific file designated for an individual entity or FX rates."""
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    if prof is None:
        raise HTTPException(status_code=400, detail="No active Company Profile found.")
    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    target_period = period or (session.state.period if session.state and session.state.period else None) or prof.current_period or config.current_period

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum {MAX_FILE_SIZE // (1024*1024)}MB limit.")

    safe_n = re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename.split("/")[-1].split("\\")[-1])
    session.cached_file_bytes[safe_n] = content

    upload_dir = (config.project_root / "inputs" / "uploads").resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    disk_path = upload_dir / f"{session.active_company_id}_{safe_n}"
    disk_path.write_bytes(content)

    sheet_names = ["Sheet1"]
    if safe_n.lower().endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet_names = list(wb.sheetnames)
            wb.close()
        except Exception:
            pass

    # Classify file
    classified_items = FileClassifier.classify_batch(
        files=[(safe_n, content)],
        expected_period=target_period,
        known_entities=hierarchy,
        use_deterministic=use_deterministic,
        use_ai=use_ai,
        confidence_threshold=config.ai_confidence_threshold
    )

    # If entity_code is specified, ensure match
    if entity_code.upper() != "FX_RATES":
        for cf in classified_items:
            cf.entity_code = entity_code
            cf.file_type = "CURRENT_TB"
            cf.needs_review = False
            cf.confidence = max(cf.confidence, 0.95)
    else:
        for cf in classified_items:
            cf.file_type = "FX_RATES"
            cf.needs_review = False
            cf.confidence = max(cf.confidence, 0.95)

    files_map = (session.pending_approval_state.get("files_map", {}) if session.pending_approval_state else {})
    files_map[safe_n] = sheet_names

    existing_cf = []
    # Retain other classified items if present in pending approval state
    approval_state = build_perimeter_approval_state(classified_items, files_map, prof, target_period)
    session.pending_approval_state = approval_state

    return {"success": True, "approval_state": approval_state}

class EntityConfirmationItem(BaseModel):
    entity_code: str
    filename: str
    sheet_name: Optional[str] = None
    columns: Dict[str, str] = Field(default_factory=dict)
    scale_multiplier: float = 1.0
    denomination: Optional[str] = "UNITS"

class FXConfirmationItem(BaseModel):
    filename: Optional[str] = None
    sheet_name: Optional[str] = None
    columns: Dict[str, str] = Field(default_factory=dict)

class ConfirmIngestionPayload(BaseModel):
    entities: List[EntityConfirmationItem]
    fx_rates: Optional[FXConfirmationItem] = None

@app.post("/api/pipeline/confirm-ingestion")
async def confirm_ingestion(payload: ConfirmIngestionPayload):
    """Final human approval of Step 1 Ingestion: parses and commits TBs & FX rates, locks Step 1."""
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    if prof is None:
        raise HTTPException(status_code=400, detail="No active Company Profile found.")
    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    target_period = (session.state.period if session.state and session.state.period else None) or prof.current_period or config.current_period
    upload_dir = (config.project_root / "inputs" / "uploads").resolve()

    def get_file_bytes(fname: str) -> Optional[bytes]:
        if fname in session.cached_file_bytes:
            return session.cached_file_bytes[fname]
        direct_path = upload_dir / f"{session.active_company_id}_{fname}"
        if direct_path.exists():
            return direct_path.read_bytes()
        wildcard_matches = list(upload_dir.glob(f"*{fname}"))
        if wildcard_matches and wildcard_matches[0].exists():
            return wildcard_matches[0].read_bytes()
        return None

    ingested_tbs = []
    async with pipeline_lock:
        for ent_item in payload.entities:
            file_bytes = get_file_bytes(ent_item.filename)
            if not file_bytes:
                raise HTTPException(status_code=400, detail=f"Source file '{ent_item.filename}' for entity '{ent_item.entity_code}' not found.")

            # Strict Period Validation: verify that mapped columns do not cover a different financial year
            if target_period:
                exp_yr_m = re.search(r"20\d{2}", target_period)
                if exp_yr_m:
                    exp_yr = int(exp_yr_m.group(0))
                    mapped_cols_str = " ".join(ent_item.columns.values())
                    fy_matches = re.findall(r"(?:fy|fiscal|financial\s*year)?\s*(20\d{2})[-/](\d{2,4})", mapped_cols_str, re.IGNORECASE)
                    for s_yr, e_yr in fy_matches:
                        c_closing_yr = int(s_yr[:2] + e_yr) if len(e_yr) == 2 else int(e_yr)
                        if c_closing_yr != exp_yr:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Cannot ingest entity '{ent_item.entity_code}': The mapped column '{mapped_cols_str}' covers FY {s_yr}-{e_yr} (ending 31-Mar-{c_closing_yr}), but the active consolidation run cutoff is {target_period}. Data belongs to a different reporting period."
                            )

            legal_ent = hierarchy.get_entity(ent_item.entity_code)
            ent_name = legal_ent.entity_name if legal_ent else ent_item.entity_code
            ent_curr = legal_ent.input_currency if legal_ent else prof.reporting_currency

            raw_tb = FlexibleTBParser.parse_file(
                file_path_or_bytes=file_bytes,
                filename=ent_item.filename,
                entity_code=ent_item.entity_code,
                period=target_period,
                currency=ent_curr,
                entity_name=ent_name,
                column_overrides=ent_item.columns,
                sheet_name=ent_item.sheet_name,
                scale_multiplier=ent_item.scale_multiplier
            )

            # Insert or replace in session state
            replaced = False
            for idx, existing in enumerate(session.state.raw_tbs):
                if existing.entity_code.upper() == raw_tb.entity_code.upper():
                    session.state.raw_tbs[idx] = raw_tb
                    replaced = True
                    break
            if not replaced:
                session.state.raw_tbs.append(raw_tb)
            ingested_tbs.append(ent_item.entity_code)

        # Parse FX Rates if provided
        if payload.fx_rates and payload.fx_rates.filename:
            fx_bytes = get_file_bytes(payload.fx_rates.filename)
            if fx_bytes:
                fx_table = FlexibleTBParser.parse_fx_rates(
                    file_path_or_bytes=fx_bytes,
                    filename=payload.fx_rates.filename,
                    sheet_name=payload.fx_rates.sheet_name,
                    reporting_currency=prof.reporting_currency,
                    as_on_date=target_period,
                    column_overrides=payload.fx_rates.columns
                )
                prof.set_fx_table_for_period(target_period, fx_table)
                company_manager.save_company(prof)

        # Verification: Check that all perimeter entities have ingested TBs
        all_perimeter_codes = set(hierarchy.entities.keys()) if hierarchy.entities else {prof.company_code or prof.company_id}
        ingested_codes = {tb.entity_code.upper() for tb in session.state.raw_tbs}
        missing_codes = [c for c in all_perimeter_codes if c.upper() not in ingested_codes]

        if missing_codes:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot close Step 1: Missing trial balances for perimeter entities: {', '.join(missing_codes)}."
            )

        # Verify FX table exists
        current_fx = prof.get_fx_table_for_period(target_period)
        missing_fx = FXTranslationEngine.check_missing_rates(list(hierarchy.entities.values()), current_fx, prof.reporting_currency)
        if missing_fx:
            pairs_str = ", ".join(f"{f}->{t}" for f, t in missing_fx)
            raise HTTPException(
                status_code=400,
                detail=f"Cannot close Step 1: Missing exchange rates for pairs: {pairs_str}."
            )

        # Mark Step 1 completed and advance to Step 2
        if 1 not in session.state.completed_steps:
            session.state.completed_steps.append(1)
        session.state.current_step = 2
        session.state.is_blocked = False

        # Auto-compute COA Mappings for Step 2 so tabs are pre-populated
        try:
            from fs_conso.agent.nodes import mapper_node
            session.state = mapper_node(session.state)
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Auto COA mapping error during ingestion confirmation: {exc}")

        session.state.audit_trail.append({
            "node_id": "Ingestion",
            "event": "STEP_1_CONFIRMED",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "details": f"User confirmed Step 1 Ingestion for all {len(session.state.raw_tbs)} entities. Step 1 locked, Step 2 unlocked."
        })

        if session.active_company_id and session.active_run_id and session.state:
            run_manager.save_run_state(session.active_company_id, session.active_run_id, session.state)

    return {
        "success": True,
        "message": "Step 1 Ingestion successfully confirmed and locked. Step 2 unlocked.",
        "completed_steps": session.state.completed_steps,
        "current_step": session.state.current_step
    }

@app.post("/api/pipeline/run-mapping")
async def run_coa_mapping():
    """Runs the COA mapping engine on all ingested trial balances."""
    async with pipeline_lock:
        if not session.state or not session.state.raw_tbs:
            raise HTTPException(status_code=400, detail="No ingested trial balances available to map.")
        from fs_conso.agent.nodes import mapper_node
        session.state = mapper_node(session.state)
        if session.active_company_id and session.active_run_id and session.state:
            run_manager.save_run_state(session.active_company_id, session.active_run_id, session.state)
    return {
        "success": True,
        "total_mapped": len(session.state.mapping_decisions),
        "pending_reviews": len(session.state.hitl_pending_reviews)
    }

# --- Human-in-the-Loop Mapping Confirmation Endpoint ---

class IngestionMappingOverride(BaseModel):
    filename: str
    entity_code: str
    account_code: Optional[str] = None
    account_description: Optional[str] = None
    debit: Optional[str] = None
    credit: Optional[str] = None
    amount: Optional[str] = None

class ConfirmMappingsPayload(BaseModel):
    overrides: List[IngestionMappingOverride]

@app.post("/api/confirm-ingestion-mappings")
async def confirm_ingestion_mappings(payload: ConfirmMappingsPayload):
    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    if prof is None:
        raise HTTPException(status_code=400, detail="No active Company Profile found.")
    hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
    target_period = (session.state.period if session.state and session.state.period else None) or prof.current_period or config.current_period

    upload_dir = (config.project_root / "inputs" / "uploads").resolve()
    re_ingested = []

    async with pipeline_lock:
        for ov in payload.overrides:
            legal_ent = hierarchy.get_entity(ov.entity_code) if ov.entity_code else None
            ent_name = legal_ent.entity_name if legal_ent else ov.entity_code
            ent_curr = legal_ent.input_currency if legal_ent else prof.reporting_currency

            matching_files = list(upload_dir.glob(f"*{ov.filename}"))
            file_bytes = None
            if matching_files and matching_files[0].exists():
                file_bytes = matching_files[0].read_bytes()

            col_overrides = {
                "account_code": ov.account_code,
                "account_description": ov.account_description,
                "debit": ov.debit,
                "credit": ov.credit,
                "amount": ov.amount,
            }
            col_overrides = {k: v for k, v in col_overrides.items() if v}

            if file_bytes:
                raw_tb = FlexibleTBParser.parse_file(
                    file_path_or_bytes=file_bytes,
                    filename=ov.filename,
                    entity_code=ov.entity_code,
                    period=target_period,
                    currency=ent_curr,
                    entity_name=ent_name,
                    column_overrides=col_overrides
                )
                replaced = False
                for i, existing in enumerate(session.state.raw_tbs):
                    if existing.entity_code == raw_tb.entity_code:
                        session.state.raw_tbs[i] = raw_tb
                        replaced = True
                        break
                if not replaced:
                    session.state.raw_tbs.append(raw_tb)
                re_ingested.append(ov.entity_code)

        if session.active_company_id and session.active_run_id and session.state:
            run_manager.save_run_state(session.active_company_id, session.active_run_id, session.state)

    return {"success": True, "re_ingested": re_ingested}

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

    # Also update in-memory mapping engine cache
    from fs_conso.core.mapper import COAMappingEngine
    COAMappingEngine._global_decision_cache[(req.entity_code, req.local_code)] = (
        req.group_code, 1.0, "USER_APPROVED_RULE", req.reasoning
    )

    resolved_item = prof.group_coa.get_item(req.group_code) if (prof and prof.group_coa) else None

    async with pipeline_lock:
        if session.state:
            for d in session.state.mapping_decisions:
                # Match entity_code (case-insensitive) and local_code
                ent_match = not req.entity_code or not d.entity_code or (d.entity_code.upper() == req.entity_code.upper())
                if ent_match and d.local_code == req.local_code:
                    d.group_code = req.group_code
                    if resolved_item:
                        d.group_description = resolved_item.account_name
                        d.level_0_code = resolved_item.account_code
                        d.level_0_name = resolved_item.level_0_account or resolved_item.account_name
                    d.method = "USER_APPROVED_RULE"
                    d.confidence = 1.0
                    d.needs_review = False
                    d.is_ambiguous = False
                    d.reasoning = req.reasoning

            # Also synchronize standardized_tbs if already created
            if session.state.standardized_tbs:
                for std_tb in session.state.standardized_tbs:
                    if not req.entity_code or std_tb.entity_code.upper() == req.entity_code.upper():
                        for row in std_tb.rows:
                            if row.local_account_code == req.local_code:
                                row.account_code = req.group_code
                                if resolved_item:
                                    row.account_description = resolved_item.account_name

            session.state.hitl_pending_reviews = [
                r for r in session.state.hitl_pending_reviews
                if not ((not req.entity_code or r.get("entity_code") == req.entity_code) and r.get("local_code") == req.local_code)
            ]
            if not session.state.hitl_pending_reviews and not any(d.needs_review for d in session.state.mapping_decisions):
                session.state.halted_node = None
                session.state.is_blocked = False
                session.state.error_message = None
                session.state.remediation_items = []
                if 2 not in session.state.completed_steps:
                    session.state.completed_steps.append(2)
                session.state.current_step = max(session.state.current_step, 3)

            if session.active_company_id and session.active_run_id and session.state:
                run_manager.save_run_state(session.active_company_id, session.active_run_id, session.state)

    return {
        "success": True,
        "message": f"Mapping for '{req.local_code}' saved to learning memory.",
        "resolved_code": req.group_code,
        "resolved_name": resolved_item.account_name if resolved_item else req.group_code,
        "level_0_name": (resolved_item.level_0_account or resolved_item.account_name) if resolved_item else req.group_code
    }

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
        if session.active_company_id and session.active_run_id and session.state:
            run_manager.save_run_state(session.active_company_id, session.active_run_id, session.state)
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

        # Perimeter Completeness Gate: Validate that trial balances exist for all perimeter entities
        hierarchy = prof.entity_hierarchy or EntityHierarchy(parent_code=prof.company_code or prof.company_id)
        if hierarchy and hierarchy.entities:
            uploaded_codes = {tb.entity_code.strip().upper() for tb in session.state.raw_tbs}
            missing_entities = [
                f"{ent.entity_name} ({ent.entity_code})"
                for ent in hierarchy.entities.values()
                if ent.entity_code.strip().upper() not in uploaded_codes
            ]
            if missing_entities:
                raise HTTPException(
                    status_code=400,
                    detail=f"Perimeter Incomplete: Missing trial balance submissions for {len(missing_entities)} entity/entities: {', '.join(missing_entities)}. Please upload all perimeter trial balances before running consolidation."
                )

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
            if session.state.is_blocked:
                session.current_stage = f"Halted at {session.state.halted_node or 'Gate'}: {session.state.error_message or 'Action required.'}"
                session.current_node = session.state.halted_node
            else:
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

    prof = company_manager.get_company(session.active_company_id) if session.active_company_id else None
    hierarchy = prof.entity_hierarchy if prof else None
    st = session.state

    level_0_choices = []
    if prof and prof.group_coa and prof.group_coa.items:
        for it in sorted(prof.group_coa.items.values(), key=lambda x: str(x.account_code)):
            l0_name = it.level_0_account or it.account_name
            level_0_choices.append({
                "account_code": it.account_code,
                "account_name": it.account_name,
                "level_0_account": l0_name,
                "label": f"{it.account_code} - {l0_name}"
            })

    perimeter_entities = []
    if hierarchy and hierarchy.entities:
        for ent in hierarchy.entities.values():
            perimeter_entities.append({
                "entity_code": ent.entity_code,
                "entity_name": ent.entity_name,
                "input_currency": ent.input_currency,
                "holding_percentage": ent.holding_percentage,
                "is_parent": ent.is_parent
            })
    elif prof:
        perimeter_entities.append({
            "entity_code": prof.company_code or "P",
            "entity_name": prof.company_name or "Parent Company",
            "input_currency": prof.reporting_currency or "INR",
            "holding_percentage": 1.0,
            "is_parent": True
        })

    # Auto-heal legacy or missing mapping decisions so entity_code and amounts are strictly populated
    if st.raw_tbs:
        needs_heal = False
        if not st.mapping_decisions:
            needs_heal = True
        elif any(getattr(d, "entity_code", None) is None or getattr(d, "amount", None) is None for d in st.mapping_decisions):
            needs_heal = True
        if needs_heal:
            try:
                from fs_conso.agent.nodes import mapper_node
                st = mapper_node(st)
                session.state = st
                if session.active_company_id and session.active_run_id:
                    run_manager.save_run_state(session.active_company_id, session.active_run_id, st)
            except Exception as exc:
                logging.getLogger(__name__).warning(f"Auto-heal mapping decisions failed: {exc}")

    # Strict generic gating: if any mapping decision needs review, step 2 and subsequent steps cannot be completed
    if st.mapping_decisions and any(getattr(d, "needs_review", False) for d in st.mapping_decisions):
        if any(s >= 2 for s in st.completed_steps) or st.current_step > 2 or not st.is_blocked:
            st.completed_steps = [s for s in st.completed_steps if s < 2]
            st.current_step = min(st.current_step, 2)
            st.is_blocked = True
            st.halted_node = "mapper"
            st.halted_stage = "Chart of Accounts Standardization"
            session.state = st
            if session.active_company_id and session.active_run_id:
                run_manager.save_run_state(session.active_company_id, session.active_run_id, st)

    safe_mapping_decisions = []
    for d in st.mapping_decisions:
        d_dict = d.model_dump() if hasattr(d, "model_dump") else d.dict()
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
        "perimeter_entities": perimeter_entities,
        "level_0_choices": level_0_choices,
        "raw_tbs": [
            {
                "entity_code": tb.entity_code,
                "entity_name": getattr(tb, "entity_name", None) or (hierarchy.get_entity(tb.entity_code).entity_name if 'hierarchy' in locals() and hierarchy and hierarchy.get_entity(tb.entity_code) else tb.entity_code),
                "period": tb.period,
                "currency": tb.currency,
                "row_count": len(tb.rows),
                "total_debit": tb.total_debit,
                "total_credit": tb.total_credit,
                "signed_sum": tb.total_signed_amount or round(tb.total_debit - tb.total_credit, 2),
                "is_tallied": abs(tb.total_signed_amount or (tb.total_debit - tb.total_credit)) < 0.01,
                "detected_columns": getattr(tb, "detected_columns", {}),
                "detection_trace": getattr(tb, "detection_trace", ""),
                "rows": [r.dict() for r in tb.rows]
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
