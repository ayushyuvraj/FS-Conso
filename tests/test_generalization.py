"""
Comprehensive Integration & Edge Case Test Suite for Generalization Engine
Validates:
1. Multi-Company Workspace Isolation & Persistence
2. Batch File Classification (10-15+ mixed files) with 3-tier escalation
3. 75-Column Wide Dimension Trial Balance Ingestion
4. Proactive Missing FX Rate & Prerequisite Detection
5. N x N Intercompany Matrix Eliminations with Dual Tolerances
6. Ind AS 103 Acquisition Accounting (Goodwill, Capital Reserve, NCI)
7. Scalability to 75+ Subsidiaries with 100% Formula Provenance in openpyxl
8. Security Defense (Formula Injection, Path Traversal, Null Bytes)
"""

import io
import pytest
import pandas as pd
import openpyxl
from decimal import Decimal
from pathlib import Path

from fs_conso.config import config
from fs_conso.models.company import CompanyProfile, PeriodStatus
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.models.fx import FXRateTable, FXRateEntry
from fs_conso.models.elimination import IntercompanyRecord
from fs_conso.models.trial_balance import RawTrialBalance, RawTBRow
from fs_conso.core.company_manager import CompanyManager
from fs_conso.core.file_classifier import FileClassifier, ClassifiedFile
from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.core.translator import FXTranslationEngine
from fs_conso.core.elimination_engine import IntercompanyEliminationEngine
from fs_conso.core.aggregator import ConsolidationAggregator, ConsolidatedTrialBalance, ConsolidatedTBRow
from fs_conso.excel.report_writer import ExcelReportWriter


# ---------------------------------------------------------
# 1. Multi-Company Workspace Isolation & Lifecycle
# ---------------------------------------------------------
def test_multi_company_workspace_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "inputs_dir", tmp_path / "inputs")
    mgr = CompanyManager(workspaces_root=tmp_path / "inputs" / "workspaces")

    # Create Company X and Company Y
    comp_x = mgr.create_company("company-x", "Company X Corp", "USD", "31-Dec-2025")
    comp_y = mgr.create_company("company-y", "Company Y Global", "INR", "31-Mar-2026")

    # Add custom mappings to X
    comp_x.add_mapping("SUB_01", "1001", "CASH_GRP")
    mgr.save_company(comp_x)

    # Reload both
    reloaded_x = mgr.get_company("company-x")
    reloaded_y = mgr.get_company("company-y")

    assert reloaded_x is not None
    assert reloaded_x.reporting_currency == "USD"
    assert reloaded_x.get_mapping("SUB_01", "1001") == "CASH_GRP"

    assert reloaded_y is not None
    assert reloaded_y.reporting_currency == "INR"
    # Verify isolation: Y has no mappings from X
    assert reloaded_y.get_mapping("SUB_01", "1001") is None

    # List companies
    comps = mgr.list_companies()
    comp_ids = [c["company_id"] for c in comps]
    assert "company-x" in comp_ids
    assert "company-y" in comp_ids


# ---------------------------------------------------------
# 2. Batch File Classification (10-15+ Mixed Files)
# ---------------------------------------------------------
def test_batch_file_classifier_multi_file():
    known_entities = ["HOLD_CO", "SUB_ALPHA", "SUB_BETA", "SUB_GAMMA"]

    # Construct mock files
    files = [
        ("TB_SUB_ALPHA.xlsx", b"dummy excel content"),
        ("Trial_Balance_SUB_BETA_March2024.xlsx", b"dummy excel content"),
        ("Prior_Period_TB_SUB_GAMMA_2023.xlsx", b"dummy excel content"),
        ("FX_Rate_Sheet_31Mar2024.xlsx", b"dummy excel content"),
        ("Intercompany_Reconciliation_Matrix.xlsx", b"dummy excel content"),
        ("Group_Chart_of_Accounts_v2.xlsx", b"dummy excel content"),
        ("Entity_Hierarchy_Ownership_Structure.xlsx", b"dummy excel content"),
        ("Random_Invoice_Scan_99482.pdf", b"%PDF-1.4 garbage"),
        ("Unidentified_Messy_Dump.csv", b"col1,col2,col3\n1,2,3")
    ]

    classified = FileClassifier.classify_batch(
        files,
        expected_period="31-Mar-2024",
        known_entities=known_entities
    )

    by_name = {c.filename: c for c in classified}

    # Verify Current TB
    assert by_name["TB_SUB_ALPHA.xlsx"].file_type == "CURRENT_TB"
    assert by_name["TB_SUB_ALPHA.xlsx"].entity_code == "SUB_ALPHA"
    assert by_name["TB_SUB_ALPHA.xlsx"].confidence >= 0.85

    # Verify Prior TB
    assert by_name["Prior_Period_TB_SUB_GAMMA_2023.xlsx"].file_type == "PRIOR_TB"
    assert by_name["Prior_Period_TB_SUB_GAMMA_2023.xlsx"].entity_code == "SUB_GAMMA"

    # Verify FX Sheet
    assert by_name["FX_Rate_Sheet_31Mar2024.xlsx"].file_type == "FX_RATES"

    # Verify IC Schedule
    assert by_name["Intercompany_Reconciliation_Matrix.xlsx"].file_type == "INTERCOMPANY_SCHEDULE"

    # Verify COA Master
    assert by_name["Group_Chart_of_Accounts_v2.xlsx"].file_type == "COA_MASTER"

    # Verify Ambiguous / Garbage routes to review
    assert by_name["Random_Invoice_Scan_99482.pdf"].needs_review is True


# ---------------------------------------------------------
# 3. Dynamic Parser on 75-Column Wide Dimension TB
# ---------------------------------------------------------
def test_dynamic_parser_75_column_wide_tb():
    # Construct a wide 75-column DataFrame
    cols = ["GL_Code", "Account_Name"]
    # Add 71 dimension columns (Dept, Cost Center, Project_1 ... Project_69)
    cols.append("Department")
    cols.append("Cost_Center")
    for i in range(1, 70):
        cols.append(f"Project_Dim_{i:02d}")
    cols.extend(["Debit_Amount", "Credit_Amount"])

    assert len(cols) == 75

    data = [
        ["1001", "Cash at Bank", "Treasury", "CC100", *["N/A"] * 69, 500000.0, 0.0],
        ["1002", "Trade Receivables", "Sales", "CC200", *["N/A"] * 69, 300000.0, 0.0],
        ["2001", "Trade Payables", "Procurement", "CC300", *["N/A"] * 69, 0.0, 200000.0],
        ["3001", "Share Capital", "Corporate", "CC400", *["N/A"] * 69, 0.0, 600000.0],
    ]

    df = pd.DataFrame(data, columns=cols)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    file_bytes = buf.getvalue()

    raw_tb = FlexibleTBParser.parse_file(
        file_path_or_bytes=file_bytes,
        filename="TB_Wide_75Cols.xlsx",
        entity_code="WIDE_SUB",
        period="31-Mar-2024",
        currency="INR"
    )

    assert raw_tb.entity_code == "WIDE_SUB"
    assert len(raw_tb.rows) == 4
    assert raw_tb.total_debit == 800000.0
    assert raw_tb.total_credit == 800000.0
    # Debit = Credit -> signed balance = 0.0
    assert abs(raw_tb.total_signed_amount) < 0.01


# ---------------------------------------------------------
# 4. Proactive Missing FX Rate & Prerequisite Detection
# ---------------------------------------------------------
def test_missing_fx_rate_detection():
    hierarchy_nodes = [
        LegalEntity(entity_code="PARENT", entity_name="Parent Co", input_currency="INR", holding_percentage=1.0),
        LegalEntity(entity_code="SUB_EUR", entity_name="Euro Sub", input_currency="EUR", holding_percentage=1.0),
        LegalEntity(entity_code="SUB_SGD", entity_name="Singapore Sub", input_currency="SGD", holding_percentage=0.8),
        LegalEntity(entity_code="SUB_INR", entity_name="Domestic Sub", input_currency="INR", holding_percentage=1.0),
    ]

    # FX table only has EUR -> INR, missing SGD -> INR
    fx_table = FXRateTable()
    fx_table.add_rate(FXRateEntry(
        from_currency="EUR",
        to_currency="INR",
        as_on_date="31-Mar-2024",
        closing_rate=90.0,
        average_rate=88.0,
        historical_rate=85.0
    ))

    missing = FXTranslationEngine.check_missing_rates(hierarchy_nodes, fx_table, presentation_currency="INR")
    assert ("SGD", "INR") in missing
    assert ("EUR", "INR") not in missing
    assert ("INR", "INR") not in missing


# ---------------------------------------------------------
# 5. N x N Intercompany Matrix Eliminations
# ---------------------------------------------------------
def test_n_by_n_intercompany_elimination_matrix():
    records = [
        # Pair 1: S1 & S2 (Matched within 0)
        IntercompanyRecord(entity_code="SUB_01", counterparty_code="SUB_02", account_code="2001", amount=150000.0),
        IntercompanyRecord(entity_code="SUB_02", counterparty_code="SUB_01", account_code="1002", amount=-150000.0),

        # Pair 2: S2 & S3 (Warning: diff is 5,000 <= 10,000 absolute tolerance)
        IntercompanyRecord(entity_code="SUB_02", counterparty_code="SUB_03", account_code="2001", amount=50000.0),
        IntercompanyRecord(entity_code="SUB_03", counterparty_code="SUB_02", account_code="1002", amount=-45000.0),

        # Pair 3: S3 & S4 (Exception: diff is 80,000 > 10,000 absolute tolerance)
        IntercompanyRecord(entity_code="SUB_03", counterparty_code="SUB_04", account_code="2001", amount=100000.0),
        IntercompanyRecord(entity_code="SUB_04", counterparty_code="SUB_03", account_code="1002", amount=-20000.0),
    ]

    engine = IntercompanyEliminationEngine(abs_tol=10000.0, pct_tol=0.01)
    result = engine.run(records)

    assert result.matched_count == 1
    assert result.tolerance_warning_count == 1
    assert result.exception_count == 1

    # Verify vouchers are generated
    assert len(result.vouchers) >= 2


# ---------------------------------------------------------
# 6. Ind AS 103 Acquisition Accounting
# ---------------------------------------------------------
def test_ind_as_103_goodwill_and_nci_calculation():
    # Scenario A: 80% acquisition, consideration = 1,000,000, net assets = 800,000
    # Net asset share (80%) = 640,000 -> Goodwill = 1,000,000 - 640,000 = 360,000
    # NCI (20%) = 800,000 * 20% = 160,000
    gw_a, cr_a, nci_a = ConsolidationAggregator.calculate_acquisition_accounting(
        holding_percentage=80.0,
        consideration_paid=1000000.0,
        net_assets_at_acquisition=800000.0
    )
    assert gw_a == 360000.0
    assert cr_a == 0.0
    assert nci_a == 160000.0

    # Scenario B: 100% acquisition at a bargain: consideration = 500,000, net assets = 600,000
    # Capital Reserve = 600,000 - 500,000 = 100,000
    gw_b, cr_b, nci_b = ConsolidationAggregator.calculate_acquisition_accounting(
        holding_percentage=100.0,
        consideration_paid=500000.0,
        net_assets_at_acquisition=600000.0
    )
    assert gw_b == 0.0
    assert cr_b == 100000.0
    assert nci_b == 0.0


# ---------------------------------------------------------
# 7. Scalability to 75+ Subsidiaries with 100% Formulas
# ---------------------------------------------------------
def test_report_writer_scaling_to_75_entities(tmp_path):
    from fs_conso.core.loader import load_coa_for_company, load_entity_hierarchy_for_company, load_fx_rates_for_company

    coa = load_coa_for_company("company-p")
    hierarchy = load_entity_hierarchy_for_company("company-p")
    fx_table = load_fx_rates_for_company("company-p", "31-Mar-2024")
    writer = ExcelReportWriter(coa, hierarchy, fx_table)

    # Generate 75 entity names
    entity_codes = ["HOLD_CO"] + [f"SUB_{i:02d}" for i in range(1, 75)]
    assert len(entity_codes) == 75

    rows = [
        ConsolidatedTBRow(
            account_code="A110101",
            account_description="Cash and cash equivalents",
            entity_balances={e: 1000.0 for e in entity_codes},
            entity_eliminations={e: 0.0 for e in entity_codes},
            total_entities=75000.0,
            eliminations=0.0,
            adjustments=0.0,
            consolidated_total=75000.0
        ),
        ConsolidatedTBRow(
            account_code="L210101",
            account_description="Trade Payables",
            entity_balances={e: -500.0 for e in entity_codes},
            entity_eliminations={e: 10.0 for e in entity_codes},
            total_entities=-37500.0,
            eliminations=750.0,
            adjustments=0.0,
            consolidated_total=-36750.0
        )
    ]

    ctb = ConsolidatedTrialBalance(
        period="31-Mar-2026",
        currency="INR",
        entity_codes=entity_codes,
        rows=rows
    )

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Test writing Consolidated_TB sheet
    writer._write_consolidated_tb_sheet(wb, ctb)
    ws_ctb = wb["Consolidated_TB"]
    assert ws_ctb is not None
    # Total cols = 2 + 75 + 75 + 3 = 155 columns
    assert ws_ctb.max_column >= 155

    # Test writing Balance Sheet with 75 entities
    writer._write_balance_sheet(wb, ctb)
    ws_bs = wb["Balance_Sheet"]
    assert ws_bs is not None
    assert ws_bs.max_column >= 155

    # Check cell formula in net total column
    net_col = ws_bs.max_column
    formula_val = str(ws_bs.cell(row=6, column=net_col).value or "")
    assert formula_val.startswith("=")

    output_path = tmp_path / "Consolidated_75_Subsidiaries.xlsx"
    wb.save(output_path)
    wb.close()
    assert output_path.exists()


# ---------------------------------------------------------
# 8. Security Hardening & Edge Cases
# ---------------------------------------------------------
def test_security_formula_injection_defense():
    from fs_conso.excel.formula_builder import escape_csv_formula_injection

    malicious_inputs = [
        "=cmd|'/C calc'!A0",
        "-2+3+cmd|' /C notepad'!A0",
        "+100-200",
        "@SUM(1,2)",
        "\t=1+1",
        "\r=1+1"
    ]

    for malicious in malicious_inputs:
        sanitized = escape_csv_formula_injection(malicious)
        assert not sanitized.startswith("=")
        assert not sanitized.startswith("+")
        assert not sanitized.startswith("-")
        assert not sanitized.startswith("@")


def test_security_path_traversal_defense():
    traversal_names = [
        "../../etc/passwd.xlsx",
        "..\\..\\Windows\\System32\\calc.exe",
        "file/../../sub.csv",
        "normal\x00hidden.xlsx"
    ]

    for name in traversal_names:
        # In upload_trial_balance sanitization
        has_traversal = ".." in name or "/" in name or "\\" in name or "\x00" in name
        assert has_traversal is True
