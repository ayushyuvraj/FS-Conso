"""Comprehensive unit tests for Edge Case Ingestion & Validation Engine.

Tests all 5 critical edge cases:
1. Unexpected column headers (GL_Code, Acc_No, Dr, Cr, Balance, Debit Balance).
2. Number formatting: commas, Indian lakhs (12,34,567.89), currencies (₹, $, SGD),
   parentheses negatives '(1,200.00)', trailing minus '500-', European decimals.
3. Empty rows, top comments/preambles, bottom 'Grand Total' summary rows.
4. Duplicate accounts and blank cells vs zero values ('-' converted to 0.0, blanks preserved as None).
5. Large numbers and exact Decimal precision.
"""

import io
from pathlib import Path
import pandas as pd
import pytest

from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.core.loader import TrialBalanceLoader, load_trial_balance
from fs_conso.core.validator import TBValidator
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance


# =========================================================================
# Category 1: Column Header Variations & Dialect Resolution
# =========================================================================

def test_gl_code_acc_no_header_variations():
    """Tests diverse column naming conventions across ERP dialects."""
    # Format with GL_Code, Particulars, Dr, Cr
    csv_data = """GL_Code,Particulars,Dr,Cr
A1101,Cash & Bank,1500000.00,0.00
A2101,Trade Payables,0.00,1500000.00
"""
    tb = FlexibleTBParser.parse_file(csv_data.encode("utf-8"), "test.csv", "Company_X", "31-Mar-2024", "INR")
    assert len(tb.rows) == 2
    assert tb.rows[0].account_code == "A1101"
    assert tb.rows[0].account_description == "Cash & Bank"
    assert tb.rows[0].debit == 1500000.0
    assert tb.rows[1].credit == 1500000.0

    val = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="Company_X")
    assert val.is_valid is True
    assert val.total_debit == 1500000.0
    assert val.total_credit == 1500000.0


def test_single_column_signed_balance_headers():
    """Tests single column signed balance headers like Acc_No, Account Name, Net Balance."""
    csv_data = """Acc_No,Account Name,Net Balance
1001,Equipment,50000.00
2001,Bank Loan,-50000.00
"""
    tb = FlexibleTBParser.parse_file(csv_data.encode("utf-8"), "test.csv", "Company_X", "31-Mar-2024", "USD")
    assert len(tb.rows) == 2
    assert tb.rows[0].account_code == "1001"
    assert tb.rows[0].amount == 50000.0
    assert tb.rows[1].amount == -50000.0

    val = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="Company_X")
    assert val.is_valid is True
    assert val.net_difference == 0.0


def test_dr_cr_indicator_column():
    """Tests TB with Amount column and separate Dr/Cr indicator column."""
    csv_data = """GL Account,Description,Amount,Dr/Cr
100100,Cash In Hand,25000.00,Dr
200100,Accounts Payable,25000.00,Cr
"""
    tb = FlexibleTBParser.parse_file(csv_data.encode("utf-8"), "test.csv", "Company_X", "31-Mar-2024", "INR")
    assert len(tb.rows) == 2
    assert tb.rows[0].amount == 25000.0
    assert tb.rows[1].amount == -25000.0

    val = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="Company_X")
    assert val.is_valid is True


# =========================================================================
# Category 2: Whitespace, Currencies, Parentheses, Number Formats
# =========================================================================

def test_clean_number_currencies_and_parentheses():
    """Tests dirty string representations of numbers."""
    parser = FlexibleTBParser

    # Standard currency and commas
    assert parser.clean_number("₹ 1,200,000.50") == 1200000.50
    assert parser.clean_number("$ 50,000.00") == 50000.00
    assert parser.clean_number("SGD 10,000.25") == 10000.25

    # Parentheses with currency inside/outside
    assert parser.clean_number("(100.00)") == -100.00
    assert parser.clean_number("( 1,200.50 )") == -1200.50
    assert parser.clean_number("(₹ 50,000.00)") == -50000.00
    assert parser.clean_number("$ (1,200.50)") == -1200.50
    assert parser.clean_number("($1,200.50)") == -1200.50

    # Indian numbering format (lakhs & crores)
    assert parser.clean_number("12,34,567.89") == 1234567.89
    assert parser.clean_number("₹ 1,00,00,000.00") == 10000000.00

    # European decimal comma
    assert parser.clean_number("1.200.000,50") == 1200000.50

    # Trailing minus and CR notation
    assert parser.clean_number("1,500.00-") == -1500.00
    assert parser.clean_number("2,500.00 CR") == -2500.00
    assert parser.clean_number("2,500.00 DR") == 2500.00

    # Explicit nil/dash representations -> 0.0
    assert parser.clean_number("-") == 0.0
    assert parser.clean_number("--") == 0.0
    assert parser.clean_number("—") == 0.0
    assert parser.clean_number("nil") == 0.0
    assert parser.clean_number("0.00") == 0.0

    # True blanks -> None
    assert parser.clean_number(None) is None
    assert parser.clean_number("") is None
    assert parser.clean_number("   ") is None
    assert parser.clean_number("NaN") is None


# =========================================================================
# Category 3: Preamble, Comments, Empty Rows, and Grand Total Footers
# =========================================================================

def test_preamble_and_summary_row_stripping():
    """Tests file with 4 preamble lines and a 'Grand Total' summary row at the bottom."""
    csv_data = """Healthcare Conglomerate Holdings Ltd
Trial Balance as at 31-Mar-2024
Report Generated by Financial Controller
[Blank row]
GL_Code,Account_Name,Debit_Balance,Credit_Balance
1001,Inventories,"₹ 50,000.00",-
1002,Receivables,"₹ 25,000.00",-
2001,Share Capital,-,"₹ 75,000.00"
Grand Total,Total debits and credits,"₹ 75,000.00","₹ 75,000.00"
*** END OF REPORT ***
"""
    tb = FlexibleTBParser.parse_file(csv_data.encode("utf-8"), "report.csv", "Company_P", "31-Mar-2024", "INR")

    # Should only contain the 3 genuine accounts, skipping preamble, Grand Total, and footer
    assert len(tb.rows) == 3
    assert [r.account_code for r in tb.rows] == ["1001", "1002", "2001"]

    # Dash '-' was correctly converted to 0.0, not None
    assert tb.rows[0].credit == 0.0
    assert tb.rows[2].debit == 0.0

    val = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="Company_P")
    assert val.is_valid is True
    assert val.total_debit == 75000.0
    assert val.total_credit == 75000.0
    assert val.net_difference == 0.0


# =========================================================================
# Category 4: Duplicate Accounts & Blank Cells vs Zero Values
# =========================================================================

def test_blank_cells_vs_dash_zeroes():
    """Verifies that explicit '-' is treated as 0.0, but a completely blank row triggers MISSING_DATA_BLANK."""
    rows = [
        RawTBRow(account_code="1001", account_description="Active Nil Account", debit=0.0, credit=0.0),
        RawTBRow(account_code="1002", account_description="Missing Balance Account", debit=None, credit=None, amount=None)
    ]
    tb = RawTrialBalance(entity_code="E1", period="31-Mar-2024", currency="INR", rows=rows)
    val = TBValidator.validate(tb)

    assert val.is_valid is False
    assert any(e.error_code == "MISSING_DATA_BLANK" and e.account_code == "1002" for e in val.errors)
    assert not any(e.account_code == "1001" for e in val.errors)


def test_duplicate_accounts_aggregation():
    """Tests aggregating subledger duplicate lines for the same GL code."""
    csv_data = """Account Code,Description,Debit,Credit
1001,Cash Branch North,10000.00,0.00
1001,Cash Branch South,15000.00,0.00
2001,Accounts Payable,0.00,25000.00
"""
    # Policy = "aggregate"
    tb_agg = FlexibleTBParser.parse_file(
        csv_data.encode("utf-8"),
        "subledger.csv",
        "Company_S1",
        "31-Mar-2024",
        "INR",
        duplicate_policy="aggregate"
    )

    assert len(tb_agg.rows) == 2
    cash_row = [r for r in tb_agg.rows if r.account_code == "1001"][0]
    assert cash_row.debit == 25000.00

    val = TBValidator.validate(tb_agg, duplicate_policy="warn")
    assert val.is_valid is True
    assert val.total_debit == 25000.0
    assert val.total_credit == 25000.0


# =========================================================================
# Category 5: Floating-Point Precision & Date Normalization
# =========================================================================

def test_large_numbers_and_decimal_precision():
    """Tests exact Decimal balance check without IEEE 754 float drift."""
    rows = [
        RawTBRow(account_code="1001", account_description="Major Asset", debit=1000000000.10, credit=0.0),
        RawTBRow(account_code="1002", account_description="Minor Asset", debit=0.20, credit=0.0),
        RawTBRow(account_code="2001", account_description="Total Liability", debit=0.0, credit=1000000000.30),
    ]
    tb = RawTrialBalance(entity_code="E1", period="31-Mar-2024", currency="INR", rows=rows)
    val = TBValidator.validate(tb)

    assert val.is_valid is True
    assert val.net_difference == 0.0
    assert val.total_debit == 1000000000.30
    assert val.total_credit == 1000000000.30


def test_flexible_period_normalization():
    """Tests that ISO format '2024-03-31' matches reporting period '31-Mar-2024' without error."""
    rows = [
        RawTBRow(account_code="1001", account_description="Asset", debit=500.0, credit=0.0),
        RawTBRow(account_code="2001", account_description="Liability", debit=0.0, credit=500.0)
    ]
    tb = RawTrialBalance(entity_code="E1", period="2024-03-31", currency="INR", rows=rows)
    val = TBValidator.validate(tb, expected_period="31-Mar-2024", expected_entity="E1")

    assert val.is_valid is True
    assert not any(e.error_code == "PERIOD_MISMATCH" for e in val.errors)
