"""Data loader and benchmark fixture builder.

Extracts real master data from Conso.xlsx and constructs the 4-entity conglomerate fixture.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import openpyxl
import pandas as pd

from fs_conso.core.file_parser import FlexibleTBParser
from fs_conso.models.coa import AccountClassification, ChartOfAccounts, COAItem, RollUpOperator
from fs_conso.models.entity import EntityHierarchy, LegalEntity
from fs_conso.models.fx import FXRateEntry, FXRateTable
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance

# Expose TrialBalanceLoader for multi-format file ingestion
TrialBalanceLoader = FlexibleTBParser


def load_trial_balance(
    file_path_or_bytes: Union[Path, str, bytes],
    entity_code: str,
    period: str = "31-Mar-2024",
    currency: str = "INR",
    filename: Optional[str] = None,
    sheet_name: Optional[str] = None,
    duplicate_policy: str = "keep"
) -> RawTrialBalance:
    """Loads and parses raw trial balance from any Excel or CSV file."""
    fname = filename or (str(file_path_or_bytes) if isinstance(file_path_or_bytes, (str, Path)) else "upload.xlsx")
    return FlexibleTBParser.parse_file(
        file_path_or_bytes=file_path_or_bytes,
        filename=fname,
        entity_code=entity_code,
        period=period,
        currency=currency,
        sheet_name=sheet_name,
        duplicate_policy=duplicate_policy
    )


class ConsoMasterLoader:
    """Extracts master data from the reference Conso.xlsx file."""

    @staticmethod
    def load_coa(conso_path: Path) -> ChartOfAccounts:
        wb = openpyxl.load_workbook(conso_path, data_only=True)
        ws = wb["Chart of Accounts"]
        coa = ChartOfAccounts()

        for r in range(2, ws.max_row + 1):
            code_val = ws.cell(r, 1).value
            if code_val is None:
                continue
            code = str(code_val).strip()
            level_3 = ws.cell(r, 2).value
            level_2 = ws.cell(r, 3).value
            level_1 = ws.cell(r, 4).value
            level_0 = ws.cell(r, 5).value
            acc_type_val = ws.cell(r, 6).value or "Asset"
            rollup_val = ws.cell(r, 7).value

            # Determine name
            name = level_0 or level_1 or level_2 or level_3 or code
            
            # Map type
            type_str = str(acc_type_val).strip().capitalize()
            if "Asset" in type_str:
                acc_type = AccountClassification.ASSET
            elif "Liab" in type_str:
                acc_type = AccountClassification.LIABILITY
            elif "Equity" in type_str:
                acc_type = AccountClassification.EQUITY
            elif "Inc" in type_str or "Rev" in type_str:
                acc_type = AccountClassification.INCOME
            elif "Exp" in type_str:
                acc_type = AccountClassification.EXPENSE
            else:
                acc_type = AccountClassification.ASSET

            rollup_op = RollUpOperator.SUBTRACTION if rollup_val and "Sub" in str(rollup_val) else RollUpOperator.ADDITION
            statement = "PL" if acc_type in (AccountClassification.INCOME, AccountClassification.EXPENSE) else "BS"

            coa.add_item(COAItem(
                account_code=code,
                account_name=str(name).strip(),
                level_3=str(level_3).strip() if level_3 else None,
                level_2=str(level_2).strip() if level_2 else None,
                level_1=str(level_1).strip() if level_1 else None,
                level_0_account=str(level_0).strip() if level_0 else None,
                account_type=acc_type,
                rollup_operator=rollup_op,
                fs_statement=statement
            ))
        wb.close()
        return coa

    @staticmethod
    def load_entity_hierarchy(conso_path: Path) -> EntityHierarchy:
        wb = openpyxl.load_workbook(conso_path, data_only=True)
        ws = wb["Entity Structure"]
        hierarchy = EntityHierarchy(parent_code="Company_P", reporting_currency="INR")

        # Parent Company P
        hierarchy.add_entity(LegalEntity(
            entity_code="Company_P",
            entity_name="Parent Holding Healthcare Corp",
            entity_short_name="Parent",
            input_currency="INR",
            holding_percentage=1.0,
            consolidation_method="Parent"
        ))

        # Subsidiaries
        # Row 5: Company S1, 100%
        # Row 6: Company S2, 90%
        # Row 7: Company S3, 80%
        subs = [
            ("Company_S1", "Operating Services Sub 1", "INR", 1.0),
            ("Company_S2", "Diagnostic Equipment Sub 2", "USD", 0.9),
            ("Company_S3", "Specialty Pharmacy Sub 3", "SGD", 0.8),
        ]
        for code, name, curr, pct in subs:
            hierarchy.add_entity(LegalEntity(
                entity_code=code,
                entity_name=name,
                input_currency=curr,
                parent_entity_code="Company_P",
                immediate_parent="Company_P",
                ultimate_parent="Company_P",
                holding_percentage=pct,
                consolidation_method="Full Consolidation"
            ))
        wb.close()
        return hierarchy

    @staticmethod
    def load_historical_mappings(conso_path: Path) -> Dict[Tuple[str, str], str]:
        """Loads known mapping table from 1_COA_Mapping: (entity, local_acc) -> group_acc."""
        wb = openpyxl.load_workbook(conso_path, data_only=True)
        ws = wb["1_COA_Mapping"]
        mappings: Dict[Tuple[str, str], str] = {}

        # Rows 24 to 27 has examples:
        # Entity | Local account | Local description | Group account | FS line
        for r in range(25, ws.max_row + 1):
            ent = ws.cell(r, 1).value
            loc = ws.cell(r, 2).value
            grp = ws.cell(r, 4).value
            if ent and loc and grp:
                mappings[(str(ent).strip(), str(loc).strip())] = str(grp).strip()
        
        # Hardcode baseline known rules from Steps sheet
        # Sub 1: 11001 -> 120400 (Cash), 21001 -> 320300 (Payables)
        # Sub 2: CASH01 -> 120400, PAY01 -> 320300
        mappings[("Company_S1", "11001")] = "120400"
        mappings[("Company_S1", "21001")] = "320300"
        mappings[("Company_S2", "CASH01")] = "120400"
        mappings[("Company_S2", "PAY01")] = "320300"
        
        wb.close()
        return mappings

    @staticmethod
    def load_default_fx_rates() -> FXRateTable:
        """Returns standard FX rate table based on Conso.xlsx Steps sheet."""
        table = FXRateTable()
        # USD -> INR: Closing = 83.5, Average = 83.0, Historical = 80.0
        table.add_rate(FXRateEntry(
            from_currency="USD",
            to_currency="INR",
            as_on_date="31-Mar-2024",
            closing_rate=83.50,
            average_rate=83.00,
            historical_rate=80.00
        ))
        # SGD -> INR: Closing = 62.0, Average = 61.5, Historical = 60.0
        table.add_rate(FXRateEntry(
            from_currency="SGD",
            to_currency="INR",
            as_on_date="31-Mar-2024",
            closing_rate=62.00,
            average_rate=61.50,
            historical_rate=60.00
        ))
        return table
