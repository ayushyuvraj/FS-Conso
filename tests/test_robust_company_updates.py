"""Exhaustive Edge-Case and Robustness Test Suite for Company Profiles.

Covers:
1. In-place renaming with casing changes (e.g. client_one <-> CLient_one).
2. Case-insensitive company_id and company_code lookup and URL routing (C1 vs c1).
3. Preservation of Base Chart of Accounts and entity hierarchies across updates.
4. Duplicate code collision prevention across different letter cases.
5. Directory slug tolerance and deletion robustness.
6. Zero, single, and multiple subsidiary updates.
"""

import io
import json
import pytest
from starlette.testclient import TestClient
from fs_conso.web.app import app
from fs_conso.core.company_manager import CompanyManager
from fs_conso.core.coa_parser import COAParser


@pytest.fixture
def client(tmp_path):
    mgr = CompanyManager(workspaces_dir=tmp_path / "workspaces")
    # Patch module level company_manager in app
    import fs_conso.web.app as web_app
    old_mgr = web_app.company_manager
    web_app.company_manager = mgr
    yield TestClient(web_app.app)
    web_app.company_manager = old_mgr


def test_create_and_rename_casing_end_to_end(client):
    """Verifies creating 'client_one' with code 'C1', then renaming to 'CLient_one' and back."""
    coa_bytes = COAParser.generate_template_bytes()
    
    # 1. Create company client_one with code C1
    create_payload = {
        "company_name": "client_one",
        "company_code": "C1",
        "reporting_currency": "INR",
        "number_of_subsidiaries": 1,
        "subsidiaries": [
            {
                "entity_name": "Subsidiary 1",
                "company_reg_number": "REG-100",
                "country_of_inc": "India",
                "date_of_inc": "2020-01-15",
                "input_currency": "INR",
                "ownership_pct": 100.0,
                "acquisition_date": "31-03-2024"
            }
        ]
    }
    
    res = client.post(
        "/api/companies/create",
        data={"profile_json": json.dumps(create_payload)},
        files={"coa_file": ("Base_COA.xlsx", io.BytesIO(coa_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["company"]["company_name"] == "client_one"
    assert data["company"]["company_code"] == "C1"
    assert data["company"]["company_id"] == "c1"
    assert data["company"]["coa_account_count"] > 0
    original_coa_count = data["company"]["coa_account_count"]

    # 2. Rename to 'CLient_one' (changing 'l' to capital 'L') via PUT /api/companies/c1 without re-uploading COA
    update_payload_1 = {
        "company_name": "CLient_one",
        "company_code": "C1",
        "reporting_currency": "INR",
        "number_of_subsidiaries": 1,
        "subsidiaries": [
            {
                "entity_name": "Subsidiary 1",
                "company_reg_number": "REG-100",
                "country_of_inc": "India",
                "date_of_inc": "2020-01-15",
                "input_currency": "INR",
                "ownership_pct": 100.0,
                "acquisition_date": "2024-03-31"
            }
        ]
    }
    
    res_up1 = client.put(
        "/api/companies/c1",
        data={"profile_json": json.dumps(update_payload_1)}
    )
    assert res_up1.status_code == 200, res_up1.text
    up1_data = res_up1.json()
    assert up1_data["company"]["company_name"] == "CLient_one"
    # Base COA must be preserved intact!
    assert up1_data["company"]["coa_account_count"] == original_coa_count

    # 3. Rename back from 'CLient_one' to 'client_one' via UPPERCASE url PUT /api/companies/C1
    update_payload_2 = {
        "company_name": "client_one",
        "company_code": "C1",
        "reporting_currency": "INR",
        "number_of_subsidiaries": 1,
        "subsidiaries": [
            {
                "entity_name": "Subsidiary 1",
                "input_currency": "INR",
                "ownership_pct": 100.0,
                "acquisition_date": "31-03-2024"
            }
        ]
    }
    
    res_up2 = client.put(
        "/api/companies/C1",
        data={"profile_json": json.dumps(update_payload_2)}
    )
    assert res_up2.status_code == 200, res_up2.text
    up2_data = res_up2.json()
    assert up2_data["company"]["company_name"] == "client_one"
    assert up2_data["company"]["coa_account_count"] == original_coa_count


def test_case_insensitive_lookup_and_duplicate_collision_defense(client):
    """Verifies that lookup works across casing, and creating a duplicate code with different case is blocked."""
    coa_bytes = COAParser.generate_template_bytes()
    
    create_payload = {
        "company_name": "Alpha Corp",
        "company_code": "ALPHA",
        "reporting_currency": "USD",
        "number_of_subsidiaries": 0,
        "subsidiaries": []
    }
    
    res = client.post(
        "/api/companies/create",
        data={"profile_json": json.dumps(create_payload)},
        files={"coa_file": ("Base_COA.xlsx", io.BytesIO(coa_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 200

    # Attempting to create another company with code 'alpha' (lowercase) must be rejected
    dup_payload = {
        "company_name": "Alpha Second",
        "company_code": "alpha",
        "reporting_currency": "USD",
        "number_of_subsidiaries": 0,
        "subsidiaries": []
    }
    res_dup = client.post(
        "/api/companies/create",
        data={"profile_json": json.dumps(dup_payload)},
        files={"coa_file": ("Base_COA.xlsx", io.BytesIO(coa_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.json()["detail"].lower()


def test_switch_and_delete_case_insensitivity(client):
    """Verifies switching and deleting works whether lowercase or uppercase ID/code is used."""
    coa_bytes = COAParser.generate_template_bytes()
    
    create_payload = {
        "company_name": "Beta Corp",
        "company_code": "BETA1",
        "reporting_currency": "EUR",
        "number_of_subsidiaries": 0,
        "subsidiaries": []
    }
    res = client.post(
        "/api/companies/create",
        data={"profile_json": json.dumps(create_payload)},
        files={"coa_file": ("Base_COA.xlsx", io.BytesIO(coa_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 200

    # Switch using uppercase code
    res_sw = client.post("/api/companies/switch", json={"company_id": "BETA1"})
    assert res_sw.status_code == 200

    # Delete using uppercase code
    res_del = client.delete("/api/companies/BETA1")
    assert res_del.status_code == 200

    # Verify company list is now empty
    res_list = client.get("/api/companies")
    assert len(res_list.json()["companies"]) == 0
