"""Flexible Chart of Accounts (COA) file parser and template generator."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
import pandas as pd

from fs_conso.models.coa import (
    AccountClassification,
    ChartOfAccounts,
    COAItem,
    RollUpOperator,
)


_HEADER_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "account_code": (
        "account code",
        "account_code",
        "gl code",
        "gl_code",
        "gl account",
        "account no",
        "account number",
        "account #",
        "code",
        "gl",
    ),
    "account_name": (
        "account name",
        "account_name",
        "account description",
        "gl description",
        "description",
        "particulars",
        "name",
        "title",
        "level 0",
        "level_0",
        "level_0_account",
    ),
    "account_type": (
        "account type",
        "account_type",
        "classification",
        "category",
        "nature",
        "class",
        "type",
    ),
    "fs_statement": (
        "fs statement",
        "fs_statement",
        "statement",
        "report",
        "fs",
    ),
    "level_3": ("level 3", "level_3", "l3", "statement group", "major group"),
    "level_2": ("level 2", "level_2", "l2", "sub group", "subgroup"),
    "level_1": ("level 1", "level_1", "l1", "fs line", "line item"),
    "level_0_account": ("level 0", "level_0", "level_0_account", "l0"),
    "rollup_operator": ("rollup operator", "rollup_operator", "rollup", "operator", "sign"),
}


def _norm_header(val: object) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val).replace("_", " ").strip().lower())


def _match_header_field(header_text: str) -> Optional[str]:
    norm = _norm_header(header_text)
    if not norm:
        return None
    for field, aliases in _HEADER_SYNONYMS.items():
        if norm in aliases:
            return field
    for field, aliases in _HEADER_SYNONYMS.items():
        if any(alias in norm for alias in aliases if len(alias) > 3):
            return field
    return None


def _parse_account_type(raw_val: Optional[str], fallback_text: str = "") -> AccountClassification:
    combined = f"{raw_val or ''} {fallback_text}".strip().lower()
    if any(k in combined for k in ("asset", "receivable", "cash", "bank", "inventory", "ppe", "goodwill")):
        return AccountClassification.ASSET
    if any(k in combined for k in ("liab", "payable", "debt", "borrowing", "provision")):
        return AccountClassification.LIABILITY
    if any(k in combined for k in ("equity", "capital", "reserve", "retained", "nci")):
        return AccountClassification.EQUITY
    if any(k in combined for k in ("inc", "rev", "sales", "turnover", "gain")):
        return AccountClassification.INCOME
    if any(k in combined for k in ("exp", "cost", "cogs", "depreciation", "amort", "tax", "salary", "rent")):
        return AccountClassification.EXPENSE
    return AccountClassification.ASSET


def _parse_rollup(raw_val: Optional[str]) -> RollUpOperator:
    if raw_val and any(k in str(raw_val).strip().lower() for k in ("sub", "minus", "deduct", "-")):
        return RollUpOperator.SUBTRACTION
    return RollUpOperator.ADDITION


class COAParser:
    """Parses uploaded Excel/CSV files into a validated ChartOfAccounts model."""

    @staticmethod
    def parse_file(file_bytes: bytes, filename: str) -> ChartOfAccounts:
        """Parses .xlsx, .xls, or .csv COA bytes into a ChartOfAccounts."""
        if not file_bytes:
            raise ValueError("Uploaded Chart of Accounts file is empty.")

        ext = Path(filename).suffix.lower()
        if ext not in {".xlsx", ".xls", ".csv"}:
            raise ValueError(f"Unsupported COA file format '{ext}'. Please upload .xlsx, .xls, or .csv.")

        rows: List[List[object]] = []
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=object)
            rows = df.where(pd.notnull(df), None).values.tolist()
        elif ext == ".xls":
            xl = pd.ExcelFile(io.BytesIO(file_bytes))
            sheet = next((s for s in xl.sheet_names if any(k in s.lower() for k in ("chart", "coa"))), xl.sheet_names[0])
            df = xl.parse(sheet_name=sheet, header=None, dtype=object)
            rows = df.where(pd.notnull(df), None).values.tolist()
        else:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            try:
                sheet_name = next(
                    (s for s in wb.sheetnames if any(k in s.lower() for k in ("chart", "coa"))),
                    wb.sheetnames[0],
                )
                ws = wb[sheet_name]
                rows = [list(r) for r in ws.iter_rows(values_only=True)]
            finally:
                wb.close()

        if not rows:
            raise ValueError("Uploaded Chart of Accounts sheet contains no rows.")

        # Detect header row within first 15 rows
        header_idx: Optional[int] = None
        col_map: Dict[str, int] = {}
        best_score = 0

        for idx, row in enumerate(rows[:15]):
            candidate: Dict[str, int] = {}
            for col_i, cell in enumerate(row):
                field = _match_header_field(cell)
                if field and field not in candidate:
                    candidate[field] = col_i
            score = len(candidate)
            if "account_code" in candidate and ("account_name" in candidate or "level_0_account" in candidate):
                score += 5
            if score > best_score and len(candidate) >= 2:
                best_score = score
                header_idx = idx
                col_map = candidate

        # Positional fallback for standard 7-column Conso COA format or 2-column Code/Name
        start_row = 0
        if header_idx is not None:
            start_row = header_idx + 1
        else:
            first_non_empty = next((i for i, r in enumerate(rows) if any(c is not None and str(c).strip() for c in r)), 0)
            sample = rows[first_non_empty] if rows else []
            if len(sample) >= 6:
                col_map = {
                    "account_code": 0,
                    "level_3": 1,
                    "level_2": 2,
                    "level_1": 3,
                    "level_0_account": 4,
                    "account_type": 5,
                    "rollup_operator": 6,
                }
            elif len(sample) >= 2:
                col_map = {"account_code": 0, "account_name": 1}
                if len(sample) >= 3:
                    col_map["account_type"] = 2
            start_row = first_non_empty

        if "account_code" not in col_map:
            raise ValueError(
                "Could not identify an 'Account Code' (or 'GL Code') column in the uploaded Chart of Accounts."
            )

        coa = ChartOfAccounts()
        for row in rows[start_row:]:
            def _get(field: str) -> Optional[str]:
                ci = col_map.get(field)
                if ci is None or ci >= len(row):
                    return None
                val = row[ci]
                if val is None:
                    return None
                s = str(val).strip()
                return s if s and s.lower() != "nan" else None

            code = _get("account_code")
            if not code:
                continue
            # Clean float-like integer codes read from Excel (e.g. "1001.0" -> "1001")
            if re.fullmatch(r"\d+\.0", code):
                code = code[:-2]

            l3 = _get("level_3")
            l2 = _get("level_2")
            l1 = _get("level_1")
            l0 = _get("level_0_account")
            name = _get("account_name") or l0 or l1 or l2 or l3 or code

            raw_type = _get("account_type")
            acc_type = _parse_account_type(raw_type, fallback_text=" ".join(p for p in (l3, l2, l1, name) if p))
            rollup = _parse_rollup(_get("rollup_operator"))

            raw_stmt = (_get("fs_statement") or "").upper()
            if raw_stmt in ("BS", "BALANCE SHEET"):
                stmt = "BS"
            elif raw_stmt in ("PL", "P&L", "PROFIT AND LOSS", "INCOME STATEMENT"):
                stmt = "PL"
            else:
                stmt = "PL" if acc_type in (AccountClassification.INCOME, AccountClassification.EXPENSE) else "BS"

            coa.add_item(
                COAItem(
                    account_code=code,
                    account_name=name,
                    level_3=l3,
                    level_2=l2,
                    level_1=l1,
                    level_0_account=l0 or name,
                    account_type=acc_type,
                    rollup_operator=rollup,
                    fs_statement=stmt,
                )
            )

        if not coa.items:
            raise ValueError("No valid GL accounts found in the uploaded Chart of Accounts file.")

        return coa

    @staticmethod
    def generate_template_bytes() -> bytes:
        """Generates a clean, formatted Excel template for uploading a company's Base Chart of Accounts."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Chart of Accounts"

        headers = [
            "Account Code",
            "Account Name",
            "Account Type",
            "FS Statement",
            "Level 3",
            "Level 2",
            "Level 1",
            "Rollup Operator",
        ]
        ws.append(headers)

        header_fill = PatternFill(start_color="00338D", end_color="00338D", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left", vertical="center")

        sample_rows = [
            ["A110101", "Land & Buildings", "Asset", "BS", "Assets", "Non-Current Assets", "Property, Plant & Equipment", "Addition"],
            ["A120301", "Trade Receivables", "Asset", "BS", "Assets", "Current Assets", "Trade Receivables", "Addition"],
            ["A120401", "Cash and Cash Equivalents", "Asset", "BS", "Assets", "Current Assets", "Cash and Bank Balances", "Addition"],
            ["L320301", "Trade Payables", "Liability", "BS", "Liabilities", "Current Liabilities", "Trade Payables", "Addition"],
            ["E210101", "Equity Share Capital", "Equity", "BS", "Equity", "Shareholders' Equity", "Share Capital", "Addition"],
            ["I410101", "Revenue from Operations", "Income", "PL", "Income", "Operating Revenue", "Revenue from Operations", "Addition"],
            ["X510101", "Operating Expenses", "Expense", "PL", "Expenses", "Operating Expenses", "Cost of Services", "Addition"],
        ]
        for row_data in sample_rows:
            ws.append(row_data)

        col_widths = [16, 30, 14, 14, 16, 24, 28, 16]
        for idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width

        buf = io.BytesIO()
        wb.save(buf)
        wb.close()
        return buf.getvalue()
