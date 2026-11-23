"""FastAPI backend server for the Consolidation Portal.

Connects the web frontend directly to the LangGraph consolidation agent.
Zero simulations: all operations execute real accounting and agent workflows.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fs_conso.agent.graph import build_consolidation_graph
from fs_conso.agent.state import ConsolidationState
from fs_conso.config import config
from fs_conso.core.loader import ConsoMasterLoader
from fs_conso.core.sample_generator import generate_benchmark_dataset, load_benchmark_raw_tbs

app = FastAPI(title="Enterprise Financial Consolidation Portal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session state
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
            completed_steps=[]
        )

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
    """Returns portal state, active API key status, and current step."""
    has_key = config.validate_api_key_strict()
    return {
        "has_active_api_key": has_key,
        "current_period": config.current_period,
        "reporting_currency": config.reporting_currency,
        "ai_confidence_threshold": config.ai_confidence_threshold,
        "ic_absolute_tolerance": config.ic_absolute_tolerance,
        "ic_percent_tolerance": config.ic_percent_tolerance,
        "current_step": session.state.current_step if session.state else 1,
        "completed_steps": session.state.completed_steps if session.state else [],
        "is_blocked": session.state.is_blocked if session.state else False,
        "error_message": session.state.error_message if session.state else None,
        "teacher_score": session.state.teacher_score if session.state else 0.0,
    }

class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    ai_confidence_threshold: Optional[float] = None
    ic_absolute_tolerance: Optional[float] = None
    ic_percent_tolerance: Optional[float] = None

@app.post("/api/settings")
async def update_settings(update: SettingsUpdate):
    if update.gemini_api_key is not None:
        config.gemini_api_key = update.gemini_api_key.strip()
    if update.ai_confidence_threshold is not None:
        config.ai_confidence_threshold = max(0.0, min(1.0, update.ai_confidence_threshold))
    if update.ic_absolute_tolerance is not None:
        config.ic_absolute_tolerance = max(0.0, update.ic_absolute_tolerance)
    if update.ic_percent_tolerance is not None:
        config.ic_percent_tolerance = max(0.0, update.ic_percent_tolerance)

    return {
        "success": True,
        "has_active_api_key": config.validate_api_key_strict(),
        "ai_confidence_threshold": config.ai_confidence_threshold,
        "ic_absolute_tolerance": config.ic_absolute_tolerance,
        "ic_percent_tolerance": config.ic_percent_tolerance
    }

@app.post("/api/run-pipeline")
async def run_pipeline():
    """Executes the full multi-agent LangGraph consolidation pipeline."""
    # Strict API Key requirement gate
    if not config.validate_api_key_strict():
        raise HTTPException(
            status_code=403,
            detail="MANDATORY GATE ERROR: Active Google Gemini API Key required to run the consolidation engine."
        )

    # Re-initialize state with raw TBs if not present
    if not session.state or not session.state.raw_tbs:
        session.initialize_baseline()

    # Invoke compiled LangGraph agent
    result = session.graph.invoke(session.state)
    session.state = ConsolidationState(**result)

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
    """Returns detailed financial matrices for the active step view."""
    if not session.state:
        session.initialize_baseline()

    st = session.state
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
        "mapping_decisions": [d.dict() for d in st.mapping_decisions[:50]],
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
        "audit_trail": st.audit_trail,
        "teacher_evaluation": st.teacher_evaluation
    }

@app.get("/api/export-excel")
async def export_excel():
    """Downloads the generated 100% formula-linked Excel deliverable."""
    excel_path = config.outputs_dir / "Consolidated_Financial_Statements.xlsx"
    if not excel_path.exists():
        # Run pipeline if not already generated
        if config.validate_api_key_strict():
            result = session.graph.invoke(session.state)
            session.state = ConsolidationState(**result)
        else:
            raise HTTPException(status_code=400, detail="Excel report not generated yet. Configure API key and run pipeline.")

    return FileResponse(
        path=str(excel_path),
        filename="Consolidated_Financial_Statements.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
