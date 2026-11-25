"""Test suite for Ingestion Page 'Run Consolidation' gate check and dynamic read-only period display."""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from fs_conso.web.app import app, session
from fs_conso.core.company_manager import company_manager


@pytest.fixture
def test_client():
    return TestClient(app)


def test_template_batch_upload_modal_structure():
    """Verify that the batch upload modal in index.html has read-only period display and hidden input."""
    tpl_path = Path("fs_conso/web/templates/index.html")
    assert tpl_path.exists(), "index.html must exist"
    html_content = tpl_path.read_text(encoding="utf-8")

    # 1. Old editable input must NOT be present
    assert '<input id="batch-upload-period" type="text"' not in html_content, (
        "Editable text input for batch-upload-period must be removed"
    )

    # 2. Informational read-only display element must be present
    assert 'id="batch-upload-period-disp"' in html_content, (
        "Dynamic read-only span #batch-upload-period-disp must be present"
    )

    # 3. Format badge element must be present
    assert 'id="batch-upload-format-badge"' in html_content, (
        "Format badge #batch-upload-format-badge must be present"
    )

    # 4. Hidden input preserving form submission must be present
    assert '<input id="batch-upload-period" type="hidden"' in html_content, (
        "Hidden input #batch-upload-period must be present for form submission"
    )

    # 5. Lock indicator text must be present
    assert "Locked for active run" in html_content, (
        "'Locked for active run' label must be displayed"
    )


def test_javascript_gate_check_and_date_formatting():
    """Verify that app.js implements the gate check and multi-format date functions."""
    js_path = Path("fs_conso/web/static/js/app.js")
    assert js_path.exists(), "app.js must exist"
    js_content = js_path.read_text(encoding="utf-8")

    # 1. Gate check in triggerRunPipeline
    assert "openBatchUploadModal();" in js_content, "triggerRunPipeline must call openBatchUploadModal on empty files"
    assert "pipelineData.raw_tbs" in js_content, "Gate check must verify pipelineData.raw_tbs"

    # 2. Dynamic display function
    assert "function updateBatchUploadPeriodDisplay()" in js_content, (
        "updateBatchUploadPeriodDisplay function must be defined"
    )

    # 3. Date formatting helper
    assert "function formatDateOnly(dateVal)" in js_content, (
        "formatDateOnly helper must be defined"
    )
    assert "function parseLocalDate(dateVal)" in js_content, (
        "parseLocalDate helper must be defined"
    )


def test_api_active_run_period_propagation(test_client):
    """Verify that creating a run sets the active period and propagates to /api/status."""
    companies = company_manager.list_companies()
    if not companies:
        company_manager.create_company("test_c1", "Test Company", "TC", "INR")
        comp_id = "test_c1"
    else:
        comp_id = companies[0]["company_id"]

    # Create run with specific cutoff date
    create_res = test_client.post("/api/runs/create", json={
        "company_id": comp_id,
        "run_date": "2024-03-31"
    })
    assert create_res.status_code == 200
    create_data = create_res.json()
    assert create_data["success"] is True
    assert create_data["run"]["run_date"] == "2024-03-31"

    # Status check should return current_period as "2024-03-31"
    st_res = test_client.get("/api/status")
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert st_data["is_launcher_active"] is False
    assert st_data["current_period"] == "2024-03-31"


def test_live_web_portal_root_endpoint():
    """Verify live web portal serves index.html with the new modal elements."""
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "batch-upload-period-disp" in res.text
    assert "Locked for active run" in res.text
