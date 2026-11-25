"""Tests for Company Profile v2 CRUD, COA parsing, subsidiary validation, and clean zero-default state."""

import io
import json
import openpyxl
import pytest
from fastapi.testclient import TestClient

from fs_conso.core.coa_parser import COAParser
from fs_conso.core.company_manager import CompanyManager
from fs_conso.models.coa import AccountClassification
from fs_conso.web import app as web_app


def _make_sample_coa_xlsx() -> bytes:
    return COAParser.generate_template_bytes()


def _make_sample_coa_csv() -> bytes:
    return (
        "GL Code,Description,Classification,Statement\n"
        "1001,Cash at Bank,Asset,BS\n"
        "2001,Trade Payables,Liability,BS\n"
        "3001,Share Capital,Equity,BS\n"
        "4001,Service Revenue,Income,PL\n"
        "5001,Staff Cost,Expense,PL\n"
    ).encode("utf-8")


def test_coa_parser_xlsx_and_csv():
    xlsx_coa = COAParser.parse_file(_make_sample_coa_xlsx(), "template.xlsx")
    assert len(xlsx_coa.items) == 7
    assert xlsx_coa.get_item("A110101").account_type == AccountClassification.ASSET
    assert xlsx_coa.get_item("I410101").fs_statement == "PL"

    csv_coa = COAParser.parse_file(_make_sample_coa_csv(), "custom_coa.csv")
    assert len(csv_coa.items) == 5
    assert csv_coa.get_item("1001").account_name == "Cash at Bank"
    assert csv_coa.get_item("2001").account_type == AccountClassification.LIABILITY
    assert csv_coa.get_item("5001").fs_statement == "PL"


def test_coa_parser_rejects_empty_or_invalid():
    with pytest.raises(ValueError):
        COAParser.parse_file(b"", "empty.xlsx")
    with pytest.raises(ValueError):
        COAParser.parse_file(b"foo,bar\n1,2\n", "bad.txt")


def test_company_manager_profile_crud_with_subsidiaries(tmp_path):
    mgr = CompanyManager(workspaces_root=tmp_path / "workspaces")
    assert mgr.list_companies() == []

    coa = COAParser.parse_file(_make_sample_coa_csv(), "base_coa.csv")
    summary = mgr.create_or_update_profile(
        company_name="Acme Global Holdings",
        company_code="ACME",
        reporting_currency="USD",
        subsidiaries=[
            {
                "entity_name": "Acme India Pvt Ltd",
                "company_reg_number": "U72900KA2021PTC",
                "country_of_inc": "India",
                "date_of_inc": "2021-04-15",
                "input_currency": "INR",
                "ownership_pct": 75.25,
                "acquisition_date": "2022-01-10",
            },
            {
                "entity_name": "Acme Singapore Pte Ltd",
                "company_reg_number": "",
                "country_of_inc": "",
                "date_of_inc": "",
                "input_currency": "SGD",
                "ownership_pct": 100.0,
                "acquisition_date": "2023-06-01",
            },
        ],
        coa=coa,
        coa_filename="base_coa.csv",
    )

    assert summary["company_id"] == "acme"
    assert summary["company_code"] == "ACME"
    assert summary["reporting_currency"] == "USD"
    assert summary["number_of_subsidiaries"] == 2
    assert summary["coa_account_count"] == 5
    assert summary["coa_filename"] == "base_coa.csv"

    subs = summary["subsidiaries"]
    assert len(subs) == 2
    assert subs[0]["ownership_pct"] == 75.25
    assert subs[0]["nci_pct"] == 24.75
    assert subs[0]["country_of_inc"] == "India"
    assert subs[1]["country_of_inc"] == ""
    assert subs[1]["date_of_inc"] == ""

    # Duplicate company code rejected on create
    with pytest.raises(ValueError, match="already exists"):
        mgr.create_or_update_profile(
            company_name="Acme Duplicate",
            company_code="ACME",
            reporting_currency="EUR",
            subsidiaries=[],
            coa=coa,
            coa_filename="base_coa.csv",
        )

    # Update profile and replace COA dynamically
    new_coa = COAParser.parse_file(_make_sample_coa_xlsx(), "updated_coa_2027.xlsx")
    updated = mgr.create_or_update_profile(
        company_name="Acme Global Holdings Ltd",
        company_code="ACME",
        reporting_currency="EUR",
        subsidiaries=subs[:1],
        coa=new_coa,
        coa_filename="updated_coa_2027.xlsx",
        existing_company_id="acme",
    )
    assert updated["reporting_currency"] == "EUR"
    assert updated["number_of_subsidiaries"] == 1
    assert updated["coa_account_count"] == 7
    assert updated["coa_filename"] == "updated_coa_2027.xlsx"

    assert mgr.delete_company("acme") is True
    assert mgr.list_companies() == []


def test_fastapi_company_profile_endpoints_zero_default(tmp_path, monkeypatch):
    isolated_mgr = CompanyManager(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(web_app, "company_manager", isolated_mgr)
    web_app.session.initialize_company(None)

    client = TestClient(web_app.app)

    # 1. Clean startup with 0 companies (no auto-seeded company-p)
    res_list = client.get("/api/companies")
    assert res_list.status_code == 200
    assert res_list.json() == {"companies": [], "active_company_id": None}

    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    assert res_status.json()["active_company_id"] is None
    assert res_status.json()["all_entities"] == []

    # 2. Download COA template
    res_tpl = client.get("/api/companies/coa-template")
    assert res_tpl.status_code == 200
    assert res_tpl.content.startswith(b"PK\x03\x04")

    # 3. Create profile via multipart/form-data
    payload = {
        "company_name": "Beacon Manufacturing Corp",
        "company_code": "BEACON",
        "reporting_currency": "INR",
        "number_of_subsidiaries": 1,
        "subsidiaries": [
            {
                "entity_name": "Beacon Europe GmbH",
                "company_reg_number": "HRB 99102",
                "country_of_inc": "Germany",
                "date_of_inc": "2019-03-10",
                "input_currency": "EUR",
                "ownership_pct": 85.75,
                "acquisition_date": "2024-01-01",
            }
        ],
    }
    res_create = client.post(
        "/api/companies/create",
        data={"profile_json": json.dumps(payload)},
        files={"coa_file": ("beacon_coa.csv", _make_sample_coa_csv(), "text/csv")},
    )
    assert res_create.status_code == 200
    created = res_create.json()["company"]
    assert created["company_code"] == "BEACON"
    assert created["coa_account_count"] == 5
    assert created["subsidiaries"][0]["ownership_pct"] == 85.75

    # 4. Edit profile without replacing COA
    payload["company_name"] = "Beacon Manufacturing Group"
    res_edit = client.put(
        "/api/companies/beacon",
        data={"profile_json": json.dumps(payload)},
    )
    assert res_edit.status_code == 200
    assert res_edit.json()["company"]["company_name"] == "Beacon Manufacturing Group"
    assert res_edit.json()["company"]["coa_account_count"] == 5

    # 5. Delete profile returns to clean empty state
    res_del = client.delete("/api/companies/beacon")
    assert res_del.status_code == 200
    assert res_del.json()["active_company_id"] is None
    assert client.get("/api/companies").json()["companies"] == []
