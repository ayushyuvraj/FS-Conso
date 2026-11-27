"""Tests for Consolidated Trial Balance Matrix Level 0 accounts and multi-column eliminations."""

import pytest
from fs_conso.core.loader import load_coa_for_company
from fs_conso.models.coa import ChartOfAccounts, COAItem, AccountClassification
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.models.fx import FXRateTable
from fs_conso.models.elimination import EliminationVoucher, EliminationStatus
from fs_conso.core.translator import TranslatedRow, TranslatedTrialBalance
from fs_conso.core.aggregator import TBAggregator, ConsolidatedTrialBalance
from fs_conso.excel.report_writer import ExcelReportWriter


def test_conso_matrix_populates_all_level_0_accounts():
    """Verify that all Level 0 items in Group COA appear in the Consolidated TB rows."""
    coa = load_coa_for_company("company-p")
    l0_items = coa.get_level_0_items()
    assert len(l0_items) > 100, f"Expected 100+ L0 items, got {len(l0_items)}"

    tb1 = TranslatedTrialBalance(
        entity_code="Company_P",
        period="31-Mar-2024",
        source_currency="INR",
        reporting_currency="INR",
        rows=[
            TranslatedRow(
                local_code="1001",
                local_description="Cash in Hand",
                account_code="A120401",
                account_description="Cash on Hand",
                source_currency="INR",
                source_amount=50000.0,
                translated_amount=50000.0,
                rate_applied=1.0,
                rate_type="Closing"
            ),
            TranslatedRow(
                local_code="2001",
                local_description="Equity Capital",
                account_code="E210101",
                account_description="Equity Share Capital",
                source_currency="INR",
                source_amount=-50000.0,
                translated_amount=-50000.0,
                rate_applied=1.0,
                rate_type="Historical"
            )
        ]
    )

    conso_tb = TBAggregator.aggregate(
        coa=coa,
        translated_tbs=[tb1],
        period="31-Mar-2024",
        currency="INR"
    )

    conso_codes = {r.account_code for r in conso_tb.rows}
    # Verify every Level 0 item from COA is in conso_tb rows
    for item in l0_items:
        assert item.account_code in conso_codes, f"L0 account {item.account_code} missing from Consolidated TB rows"

    # Verify active row has populated amount
    cash_row = next(r for r in conso_tb.rows if r.account_code == "A120401")
    assert cash_row.entity_balances["Company_P"] == 50000.0
    assert cash_row.total_entities == 50000.0

    # Verify inactive row has 0.00
    land_row = next(r for r in conso_tb.rows if r.account_code == "A110101")
    assert land_row.entity_balances.get("Company_P", 0.0) == 0.0
    assert land_row.total_entities == 0.0

    # Net total remains strictly 0.00
    assert abs(conso_tb.total_consolidated) < 0.01
    assert conso_tb.is_tallied is True


def test_conso_matrix_multi_column_eliminations_client_2():
    """Verify 5 elimination columns for Client 2: 1 parent + 3 subsidiaries + 1 total elimination."""
    # Entities: Parent C2, Subsidiaries A, B, C
    hierarchy = EntityHierarchy(parent_code="C2")
    hierarchy.add_entity(LegalEntity(entity_code="C2", entity_name="Client 2 Parent", is_parent=True))
    hierarchy.add_entity(LegalEntity(entity_code="A", entity_name="Sub A", parent_code="C2", is_parent=False))
    hierarchy.add_entity(LegalEntity(entity_code="B", entity_name="Sub B", parent_code="C2", is_parent=False))
    hierarchy.add_entity(LegalEntity(entity_code="C", entity_name="Sub C", parent_code="C2", is_parent=False))

    coa = ChartOfAccounts()
    coa.add_item(COAItem(account_code="A120302", account_name="Intercompany Receivables", level_0_account="Intercompany Receivables", is_level_0=True))
    coa.add_item(COAItem(account_code="L320401", account_name="Intercompany Payables", level_0_account="Intercompany Payables", is_level_0=True))
    coa.add_item(COAItem(account_code="A120401", account_name="Cash", level_0_account="Cash", is_level_0=True))

    tb_c2 = TranslatedTrialBalance(
        entity_code="C2",
        period="31-Mar-2024",
        source_currency="INR",
        reporting_currency="INR",
        rows=[
            TranslatedRow(local_code="101", local_description="IC Rec A", account_code="A120302", account_description="Intercompany Receivables", source_currency="INR", source_amount=100000.0, translated_amount=100000.0, rate_applied=1.0, rate_type="Closing"),
            TranslatedRow(local_code="102", local_description="Cash", account_code="A120401", account_description="Cash", source_currency="INR", source_amount=-100000.0, translated_amount=-100000.0, rate_applied=1.0, rate_type="Closing")
        ]
    )
    tb_a = TranslatedTrialBalance(
        entity_code="A",
        period="31-Mar-2024",
        source_currency="INR",
        reporting_currency="INR",
        rows=[
            TranslatedRow(local_code="201", local_description="IC Pay C2", account_code="L320401", account_description="Intercompany Payables", source_currency="INR", source_amount=-100000.0, translated_amount=-100000.0, rate_applied=1.0, rate_type="Closing"),
            TranslatedRow(local_code="202", local_description="Cash", account_code="A120401", account_description="Cash", source_currency="INR", source_amount=100000.0, translated_amount=100000.0, rate_applied=1.0, rate_type="Closing")
        ]
    )
    tb_b = TranslatedTrialBalance(entity_code="B", period="31-Mar-2024", source_currency="USD", reporting_currency="INR", rows=[])
    tb_c = TranslatedTrialBalance(entity_code="C", period="31-Mar-2024", source_currency="EUR", reporting_currency="INR", rows=[])

    # Intercompany elimination voucher between C2 and A
    vouchers = [
        EliminationVoucher(
            voucher_id="ELIM_001",
            entity_code="C2",
            counterparty_code="A",
            debit_account="L320401",
            credit_account="A120302",
            eliminated_amount=100000.0,
            status=EliminationStatus.MATCHED,
            entity_allocations={"C2": -100000.0, "A": 100000.0}
        )
    ]

    conso_tb = TBAggregator.aggregate(
        coa=coa,
        translated_tbs=[tb_c2, tb_a, tb_b, tb_c],
        elimination_vouchers=vouchers,
        entity_hierarchy=hierarchy,
        period="31-Mar-2024"
    )

    assert conso_tb.parent_entity_code == "C2"
    assert set(conso_tb.subsidiary_codes) == {"A", "B", "C"}

    # Find the IC Receivable row
    rec_row = next(r for r in conso_tb.rows if r.account_code == "A120302")
    assert rec_row.entity_balances["C2"] == 100000.0
    assert rec_row.total_entities == 100000.0
    # Individual entity elimination allocations
    assert rec_row.entity_eliminations["C2"] == -100000.0
    assert rec_row.entity_eliminations["A"] == 0.0
    assert rec_row.entity_eliminations["B"] == 0.0
    assert rec_row.entity_eliminations["C"] == 0.0
    # Total elimination equals sum of all entity elimination columns
    assert rec_row.eliminations == -100000.0
    assert rec_row.consolidated_total == 0.0

    # Find the IC Payable row
    pay_row = next(r for r in conso_tb.rows if r.account_code == "L320401")
    assert pay_row.entity_balances["A"] == -100000.0
    assert pay_row.total_entities == -100000.0
    assert pay_row.entity_eliminations["C2"] == 0.0
    assert pay_row.entity_eliminations["A"] == 100000.0
    assert pay_row.entity_eliminations["B"] == 0.0
    assert pay_row.entity_eliminations["C"] == 0.0
    assert pay_row.eliminations == 100000.0
    assert pay_row.consolidated_total == 0.0

    # Verify Excel column layout resolution: 1 parent + 3 subsidiaries in elimination display
    writer = ExcelReportWriter(coa=coa, hierarchy=hierarchy, fx_table=FXRateTable())
    entity_disp, elim_disp = writer._resolve_column_layout(conso_tb)
    # Total elim columns = len(elim_disp) + 1 (Elim Total) = 4 + 1 = 5
    assert len(elim_disp) == 4
    assert "C2" in elim_disp
    assert set(elim_disp) == {"C2", "A", "B", "C"}
    # Total elimination columns = 1 parent + 3 subsidiaries + 1 total = 5
    total_elim_cols = len(elim_disp) + 1
    assert total_elim_cols == 5


def test_conso_matrix_multi_column_eliminations_seven_subsidiaries():
    """Verify 9 elimination columns for 7 subsidiaries + 1 parent company."""
    parent = "Parent_Corp"
    subs = [f"Sub_{i}" for i in range(1, 8)]

    hierarchy = EntityHierarchy(parent_code=parent)
    hierarchy.add_entity(LegalEntity(entity_code=parent, entity_name="Parent Corp", is_parent=True))
    for s in subs:
        hierarchy.add_entity(LegalEntity(entity_code=s, entity_name=s, parent_code=parent, is_parent=False))

    coa = ChartOfAccounts()
    coa.add_item(COAItem(account_code="A120302", account_name="IC Rec", level_0_account="IC Rec", is_level_0=True))

    entities = [parent] + subs
    tbs = [TranslatedTrialBalance(entity_code=e, period="31-Mar-2024", source_currency="INR", reporting_currency="INR", rows=[]) for e in entities]

    conso_tb = TBAggregator.aggregate(
        coa=coa,
        translated_tbs=tbs,
        entity_hierarchy=hierarchy,
        period="31-Mar-2024"
    )

    writer = ExcelReportWriter(coa=coa, hierarchy=hierarchy, fx_table=FXRateTable())
    entity_disp, elim_disp = writer._resolve_column_layout(conso_tb)
    # Total elim columns = 8 entities (1 parent + 7 subs) + 1 (Elim Total) = 9
    assert len(elim_disp) == 8
    total_elim_cols = len(elim_disp) + 1
    assert total_elim_cols == 9
