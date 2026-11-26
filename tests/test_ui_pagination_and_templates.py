"""Tests for Template DOM integrity (ghost loader elimination) and Pagination logic/endpoints."""

import os
import re
import pytest
from fastapi.testclient import TestClient

from fs_conso.web import app as web_app


def test_index_template_ghost_loader_eliminated():
    """Verify that 'Loading company profiles...' occurs exactly once in index.html,

    confirming the orphan duplicate placeholder bug is permanently resolved.
    """
    template_path = os.path.join("fs_conso", "web", "templates", "index.html")
    assert os.path.exists(template_path), f"Template not found at {template_path}"

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Search for occurrences of 'Loading company profiles...'
    matches = re.findall(r"Loading company profiles\.\.\.", content)
    assert len(matches) == 1, (
        f"Expected exactly 1 occurrence of 'Loading company profiles...', found {len(matches)}. "
        "Orphan placeholder must not be present outside #company-perimeter-content."
    )

    # Ensure it is located inside company-perimeter-content
    perimeter_match = re.search(
        r'<div id="company-perimeter-content"[^>]*>[\s\S]*?Loading company profiles\.\.\.[\s\S]*?</div>',
        content,
    )
    assert perimeter_match is not None, "'Loading company profiles...' must be inside #company-perimeter-content"

    # Verify audit loader text is also singular
    audit_matches = re.findall(r"Loading consolidation audit runs\.\.\.", content)
    assert len(audit_matches) == 1, "Expected exactly 1 occurrence of 'Loading consolidation audit runs...'"


def test_app_js_pagination_architecture():
    """Verify that app.js contains pagination functions, handlers, and page size options."""
    js_path = os.path.join("fs_conso", "web", "static", "js", "app.js")
    assert os.path.exists(js_path), f"app.js not found at {js_path}"

    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Assert pagination function definition
    assert "function renderPaginationControls(" in content
    assert "function goToCompanyPage(" in content
    assert "function changeCompanyPageSize(" in content
    assert "function goToAuditPage(" in content
    assert "function changeAuditPageSize(" in content

    # Assert state variables
    assert "let companyCurrentPage = 1;" in content
    assert "let companyPageSize = 10;" in content
    assert "let auditCurrentPage = 1;" in content
    assert "let auditPageSize = 10;" in content

    # Assert page size options 10, 25, 50, 100
    assert "10, 25, 50, 100" in content


def test_pagination_math_edge_cases():
    """Validates boundary calculations for pagination:

    - 0 items
    - 2 items (user's current scenario)
    - 50 and 100 items per page
    - Out-of-bounds page clamping
    """
    def paginate(total_items: int, current_page: int, page_size: int):
        if total_items <= 0:
            return {"total_pages": 1, "current_page": 1, "start_item": 0, "end_item": 0, "slice_len": 0}
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        valid_page = max(1, min(current_page, total_pages))
        start_item = (valid_page - 1) * page_size + 1
        end_item = min(valid_page * page_size, total_items)
        slice_len = max(0, end_item - start_item + 1)
        return {
            "total_pages": total_pages,
            "current_page": valid_page,
            "start_item": start_item,
            "end_item": end_item,
            "slice_len": slice_len,
        }

    # Case 1: User's exact scenario (2 companies, page size 10)
    res = paginate(total_items=2, current_page=1, page_size=10)
    assert res["total_pages"] == 1
    assert res["start_item"] == 1
    assert res["end_item"] == 2
    assert res["slice_len"] == 2

    # Case 2: 75 items with page size 25
    p1 = paginate(75, 1, 25)
    assert p1["total_pages"] == 3
    assert p1["start_item"] == 1
    assert p1["end_item"] == 25

    p3 = paginate(75, 3, 25)
    assert p3["total_pages"] == 3
    assert p3["start_item"] == 51
    assert p3["end_item"] == 75

    # Case 3: Page size up to 50 or 100
    p50 = paginate(120, 2, 50)
    assert p50["total_pages"] == 3
    assert p50["start_item"] == 51
    assert p50["end_item"] == 100

    p100 = paginate(120, 2, 100)
    assert p100["total_pages"] == 2
    assert p100["start_item"] == 101
    assert p100["end_item"] == 120

    # Case 4: Clamping out-of-bounds page requests
    p_clamp_high = paginate(10, 999, 10)
    assert p_clamp_high["current_page"] == 1

    p_clamp_low = paginate(10, -5, 10)
    assert p_clamp_low["current_page"] == 1

    # Case 5: Zero items
    p_zero = paginate(0, 1, 10)
    assert p_zero["total_pages"] == 1
    assert p_zero["slice_len"] == 0


def test_api_companies_and_runs_endpoints():
    """Verify FastAPI endpoints /api/companies and /api/runs return valid 200 OK structures."""
    client = TestClient(web_app.app)

    comp_res = client.get("/api/companies")
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert "companies" in comp_data
    assert isinstance(comp_data["companies"], list)
    assert "active_company_id" in comp_data

    runs_res = client.get("/api/runs")
    assert runs_res.status_code == 200
    runs_data = runs_res.json()
    assert "runs" in runs_data
    assert isinstance(runs_data["runs"], list)
    assert "active_run_id" in runs_data
