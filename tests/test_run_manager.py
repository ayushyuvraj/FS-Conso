"""Exhaustive tests for RunManager, Consolidation Run Lifecycle, and Resumption Hub."""

import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from fs_conso.agent.state import ConsolidationState
from fs_conso.core.company_manager import CompanyManager
from fs_conso.core.run_manager import RunManager
from fs_conso.models.company import CompanyProfile
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.web.app import app, session


@pytest.fixture
def temp_workspace():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_fs_conso_runs_"))
    try:
        cm = CompanyManager(workspaces_dir=tmp_dir)
        # Create a test company profile
        cm.create_company(
            company_id="acme",
            company_name="Acme Holdings",
            company_code="ACM",
            reporting_currency="USD",
            current_period="2024-03-31"
        )
        rm = RunManager(company_mgr=cm)
        yield cm, rm, tmp_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sequential_run_naming(temp_workspace):
    cm, rm, tmp_dir = temp_workspace

    # First run
    r1 = rm.create_run("acme", "2024-03-31")
    assert r1["run_name"] == "Acme Holdings - Run 1 - 2024-03-31"
    assert r1["current_step"] == 1
    assert r1["status"] == "IN_PROGRESS"
    assert r1["is_completed"] is False
    assert r1["entity_count"] == 1

    # Second run
    r2 = rm.create_run("acme", "2024-03-31")
    assert r2["run_name"] == "Acme Holdings - Run 2 - 2024-03-31"

    # Third run with different date
    r3 = rm.create_run("acme", "2024-06-30")
    assert r3["run_name"] == "Acme Holdings - Run 3 - 2024-06-30"

    runs = rm.list_runs("acme")
    assert len(runs) == 3
    # Check descending order by created_at
    assert runs[0]["run_id"] == r3["run_id"]


def test_run_state_save_and_recovery(temp_workspace):
    cm, rm, tmp_dir = temp_workspace
    r1 = rm.create_run("acme", "2024-03-31")
    run_id = r1["run_id"]

    # Simulate advancing the run to step 3 (Translation)
    state = ConsolidationState(
        company_id="acme",
        period="2024-03-31",
        current_step=3,
        completed_steps=[1, 2],
        is_blocked=False
    )
    rm.save_run_state("acme", run_id, state)

    saved = rm.get_run(run_id, "acme")
    assert saved is not None
    assert saved["current_step"] == 3
    assert saved["completed_steps"] == [1, 2]
    assert saved["status"] == "IN_PROGRESS"
    assert saved["is_completed"] is False

    # Simulate completing the run at step 6
    state.current_step = 6
    state.completed_steps = [1, 2, 3, 4, 5, 6]
    rm.save_run_state("acme", run_id, state)

    completed = rm.get_run(run_id, "acme")
    assert completed["status"] == "COMPLETED"
    assert completed["is_completed"] is True


def test_api_status_launcher_mode():
    client = TestClient(app)

    # 1. Put into launcher mode
    res = client.post("/api/runs/launcher-mode")
    assert res.status_code == 200
    assert res.json()["is_launcher_active"] is True

    # 2. Status in launcher mode must return blank/None for company and period
    status_res = client.get("/api/status")
    assert status_res.status_code == 200
    sdata = status_res.json()
    assert sdata["is_launcher_active"] is True
    assert sdata["active_company_id"] is None
    assert sdata["active_company_name"] is None
    assert sdata["current_period"] is None
    assert sdata["reporting_currency"] is None


def test_api_run_create_and_resume():
    client = TestClient(app)

    # Make sure we have a company in the real workspace
    comps = client.get("/api/companies").json().get("companies", [])
    if not comps:
        # Create a test company
        client.post("/api/companies/create", data={
            "profile_json": '{"company_name":"TestCorp","company_code":"TC","reporting_currency":"USD","number_of_subsidiaries":0,"subsidiaries":[]}'
        })
        comps = client.get("/api/companies").json().get("companies", [])

    target_comp = comps[0]
    target_id = target_comp["company_id"]

    # 1. Create a fresh run
    create_res = client.post("/api/runs/create", json={
        "company_id": target_id,
        "run_date": "2024-03-31"
    })
    assert create_res.status_code == 200
    cdata = create_res.json()
    assert cdata["success"] is True
    run_rec = cdata["run"]
    assert "Run" in run_rec["run_name"]
    run_id = run_rec["run_id"]

    # 2. Check status is now active with this run
    status_res = client.get("/api/status")
    sdata = status_res.json()
    assert sdata["is_launcher_active"] is False
    assert sdata["active_company_id"] == target_id
    assert sdata["active_run_id"] == run_id

    # 3. List runs
    list_res = client.get("/api/runs")
    assert list_res.status_code == 200
    runs = list_res.json().get("runs", [])
    assert any(r["run_id"] == run_id for r in runs)

    # 4. Put into launcher mode (simulating user clicking Consolidation nav item)
    client.post("/api/runs/launcher-mode")
    assert client.get("/api/status").json()["is_launcher_active"] is True

    # 5. Resume the run
    resume_res = client.post("/api/runs/resume", json={"run_id": run_id})
    assert resume_res.status_code == 200
    rdata = resume_res.json()
    assert rdata["success"] is True
    assert rdata["run_id"] == run_id
    assert rdata["current_step"] == 1

    # Status must now reflect the resumed run
    status_after_resume = client.get("/api/status").json()
    assert status_after_resume["is_launcher_active"] is False
    assert status_after_resume["active_run_id"] == run_id
