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
from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.core.lineage_tracker import LineageTracker
from fs_conso.core.loader import ConsoMasterLoader
from fs_conso.core.sample_generator import generate_benchmark_dataset, load_benchmark_raw_tbs
from fs_conso.core.statement_builder import FinancialStatementBuilder
from fs_conso.core.validator import TBValidator

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
    allow_methods=["GET", "POST", "OPTIONS"],
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

# In-memory session manager with clean reset capability
class SessionManager:
    def __init__(self):
        self.state: Optional[ConsolidationState] = None
        self.graph = build_consolidation_graph()
        self.initialize_baseline()

    def initialize_baseline(self):
        sample_dir = config.project_root / "inputs" / "sample_data"
        if not sample_dir.exists() or not (sample_dir / "TB_Company_P.xlsx").exists():
            generate_benchmark_dataset(sample_dir)
        raw_tbs = load_benchmark_raw_tbs(sample_dir)
        self.state = ConsolidationState(
            raw_tbs=raw_tbs,
            current_step=1,
            completed_steps=[],
            is_blocked=False,
            error_message=None
        )

    def reset(self):
        """Completely restores pristine baseline state."""
        self.initialize_baseline()

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
    """Returns portal state, active API key status, and current step without secret leaks."""
    has_key = config.validate_api_key_strict()
    return {
        "has_active_api_key": has_key,
        "masked_api_key": config.get_masked_api_key(),
        "current_period": config.current_period,
        "reporting_currency": config.reporting_currency,
        "ai_confidence_threshold": config.ai_confidence_threshold,
        "ic_absolute_tolerance": config.ic_absolute_tolerance,
        "ic_percent_tolerance": config.ic_percent_tolerance,
        "current_step": session.state.current_step if session.state else 1,
        "completed_steps": session.state.completed_steps if session.state else [],
        "is_blocked": session.state.is_blocked if session.state else False,
        "error_message": sanitize_error_message(session.state.error_message) if session.state and session.state.error_message else None,
        "teacher_score": session.state.teacher_score if session.state else 0.0,
        "total_agent_traces": len(session.state.agent_traces) if session.state else 0,
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
    target_entity = entity_code.strip().upper()
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
    upload_dir = config.project_root / "inputs" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_dest = upload_dir / f"{target_entity}_{safe_name}"
    save_dest.write_bytes(bytes(content))

    # Synchronize into session
    async with pipeline_lock:
        if not session.state:
            session.initialize_baseline()
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
        if not session.state or not session.state.raw_tbs:
            session.initialize_baseline()

        # Clear prior transient block
        session.state.is_blocked = False
        session.state.error_message = None

        try:
            result = session.graph.invoke(session.state)
            session.state = ConsolidationState(**result)
        except Exception as exc:
            err_msg = sanitize_error_message(str(exc))
            session.state.is_blocked = True
            session.state.error_message = f"Agent Execution Error: {err_msg}"
            raise HTTPException(status_code=500, detail=f"Consolidation pipeline failed: {err_msg}")

    return {
        "success": not session.state.is_blocked,
        "current_step": session.state.current_step,
        "completed_steps": session.state.completed_steps,
        "teacher_score": session.state.teacher_score,
        "teacher_evaluation": session.state.teacher_evaluation,
        "error_message": session.state.error_message,
        "audit_trail_count": len(session.state.audit_trail),
        "output_file": session.state.output_excel_path
    }

@app.get("/api/pipeline-data")
async def get_pipeline_data():
    """Returns detailed financial matrices for the active step view with redacted errors."""
    if not session.state:
        session.initialize_baseline()

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
        session.initialize_baseline()
    sanitized_traces = []
    for t in session.state.agent_traces:
        td = t.dict()
        td["input_summary"] = sanitize_error_message(td.get("input_summary", ""))
        td["output_summary"] = sanitize_error_message(td.get("output_summary", ""))
        td["details"] = sanitize_error_message(td.get("details", ""))
        sanitized_traces.append(td)
    return {
        "traces": sanitized_traces,
        "total_nodes_executed": len(sanitized_traces),
        "total_latency_ms": round(sum(t.execution_time_ms for t in session.state.agent_traces), 2)
    }

@app.get("/api/financial-statements")
async def get_financial_statements():
    """Returns structured IND AS Consolidated Balance Sheet & P&L matrices."""
    if not session.state:
        session.initialize_baseline()
    if not session.state.consolidated_tb:
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
        session.initialize_baseline()
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
        session.initialize_baseline()

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
