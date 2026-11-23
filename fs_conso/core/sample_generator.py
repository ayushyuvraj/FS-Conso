"""Generates real benchmark conglomerate data files in inputs/sample_data/."""

from pathlib import Path
import openpyxl
import pandas as pd

from fs_conso.config import config
from fs_conso.core.loader import ConsoMasterLoader
from fs_conso.models.trial_balance import RawTBRow, RawTrialBalance

def generate_benchmark_dataset(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    conso_path = config.project_root / "Conso.xlsx"
    coa = ConsoMasterLoader.load_coa(conso_path)

    # 1. Company P (INR) - 2-column format (Debit/Credit)
    rows_p = [
        RawTBRow(account_code="A110101", account_description="Land", debit=5000000.0, credit=0.0),
        RawTBRow(account_code="A110102", account_description="Buildings", debit=12000000.0, credit=0.0),
        RawTBRow(account_code="120400", account_description="Cash & Cash Equivalents", debit=3000000.0, credit=0.0),
        RawTBRow(account_code="TRD_REC", account_description="Trade Receivables", debit=4500000.0, credit=0.0),
        RawTBRow(account_code="IC_REC_S3", account_description="Intercompany Receivable from Sub 3", debit=50000.0, credit=0.0),
        RawTBRow(account_code="A210101", account_description="Equity Share Capital", debit=0.0, credit=15000000.0),
        RawTBRow(account_code="A220101", account_description="Retained Earnings", debit=0.0, credit=4550000.0),
        RawTBRow(account_code="320300", account_description="Trade Payables", debit=0.0, credit=3000000.0),
        RawTBRow(account_code="REV_OPS", account_description="Revenue from Hospital Management", debit=0.0, credit=8000000.0),
        RawTBRow(account_code="EXP_EMP", account_description="Employee Benefits Expense", debit=6000000.0, credit=0.0),
    ]
    df_p = pd.DataFrame([
        {"Account Code": r.account_code, "Account Description": r.account_description, "Debit": r.debit, "Credit": r.credit}
        for r in rows_p
    ])
    df_p.to_excel(target_dir / "TB_Company_P.xlsx", index=False)

    # 2. Company S1 (INR) - Hospital Operations (100% Owned)
    rows_s1 = [
        RawTBRow(account_code="A110103", account_description="Plant & Machinery", debit=8000000.0, credit=0.0),
        RawTBRow(account_code="11001", account_description="Cash (Local Code)", debit=1500000.0, credit=0.0),
        RawTBRow(account_code="IC_REC_S2", account_description="Intercompany Receivable from Sub 2", debit=100000.0, credit=0.0),
        RawTBRow(account_code="A210101", account_description="Equity Share Capital", debit=0.0, credit=5000000.0),
        RawTBRow(account_code="21001", account_description="Trade Payables (Local Code)", debit=0.0, credit=2600000.0),
        RawTBRow(account_code="REV_OPS", account_description="Patient Healthcare Revenue", debit=0.0, credit=10000000.0),
        RawTBRow(account_code="EXP_MED", account_description="Medical Consumables Expense", debit=8000000.0, credit=0.0),
    ]
    df_s1 = pd.DataFrame([
        {"Account Code": r.account_code, "Account Description": r.account_description, "Debit": r.debit, "Credit": r.credit}
        for r in rows_s1
    ])
    df_s1.to_excel(target_dir / "TB_Company_S1.xlsx", index=False)

    # 3. Company S2 (USD) - Diagnostic Equipment Sub (90% Owned)
    # 1-column signed format
    rows_s2 = [
        RawTBRow(account_code="A110103", account_description="Medical Equipment - MRI & CT", amount=120000.0),
        RawTBRow(account_code="CASH01", account_description="Cash at Bank", amount=30000.0),
        RawTBRow(account_code="A210101", account_description="Common Stock / Equity", amount=-80000.0),
        RawTBRow(account_code="PAY01", account_description="Trade Payables", amount=-40000.0),
        RawTBRow(account_code="IC_PAY_S1", account_description="Intercompany Payable to Sub 1", amount=-1197.6), # ~$1,197.6 @ 83.5 = ~-100,000 INR
        RawTBRow(account_code="REV_DIAG", account_description="Diagnostic Scan Revenue", amount=-70000.0),
        RawTBRow(account_code="EXP_DEP", account_description="Equipment Depreciation", amount=41197.6),
    ]
    df_s2 = pd.DataFrame([
        {"Account Code": r.account_code, "Account Description": r.account_description, "Amount": r.amount}
        for r in rows_s2
    ])
    df_s2.to_excel(target_dir / "TB_Company_S2.xlsx", index=False)

    # 4. Company S3 (SGD) - Specialty Pharmacy Sub (80% Owned)
    rows_s3 = [
        RawTBRow(account_code="INV_MED", account_description="Pharmaceutical Inventories", debit=60000.0, credit=0.0),
        RawTBRow(account_code="CASH01", account_description="Bank Cash", debit=25000.0, credit=0.0),
        RawTBRow(account_code="A210101", account_description="Share Capital", debit=0.0, credit=50000.0),
        RawTBRow(account_code="IC_PAY_P", account_description="Intercompany Loan from Parent", debit=0.0, credit=806.45), # ~806.45 SGD @ 62 = ~-50,000 INR
        RawTBRow(account_code="REV_PHARM", account_description="Pharmacy Drug Sales", debit=0.0, credit=90000.0),
        RawTBRow(account_code="EXP_PURCH", account_description="Drug Purchases", debit=55806.45, credit=0.0),
    ]
    df_s3 = pd.DataFrame([
        {"Account Code": r.account_code, "Account Description": r.account_description, "Debit": r.debit, "Credit": r.credit}
        for r in rows_s3
    ])
    df_s3.to_excel(target_dir / "TB_Company_S3.xlsx", index=False)

def load_benchmark_raw_tbs(sample_dir: Path) -> list:
    """Loads the 4 entity benchmark TBs."""
    tbs = []
    # Company P
    df_p = pd.read_excel(sample_dir / "TB_Company_P.xlsx")
    rows_p = [
        RawTBRow(
            account_code=str(row["Account Code"]),
            account_description=str(row["Account Description"]),
            debit=float(row["Debit"]) if pd.notna(row["Debit"]) else 0.0,
            credit=float(row["Credit"]) if pd.notna(row["Credit"]) else 0.0
        )
        for _, row in df_p.iterrows()
    ]
    tbs.append(RawTrialBalance(entity_code="Company_P", period=config.current_period, currency="INR", rows=rows_p))

    # Company S1
    df_s1 = pd.read_excel(sample_dir / "TB_Company_S1.xlsx")
    rows_s1 = [
        RawTBRow(
            account_code=str(row["Account Code"]),
            account_description=str(row["Account Description"]),
            debit=float(row["Debit"]) if pd.notna(row["Debit"]) else 0.0,
            credit=float(row["Credit"]) if pd.notna(row["Credit"]) else 0.0
        )
        for _, row in df_s1.iterrows()
    ]
    tbs.append(RawTrialBalance(entity_code="Company_S1", period=config.current_period, currency="INR", rows=rows_s1))

    # Company S2
    df_s2 = pd.read_excel(sample_dir / "TB_Company_S2.xlsx")
    rows_s2 = [
        RawTBRow(
            account_code=str(row["Account Code"]),
            account_description=str(row["Account Description"]),
            amount=float(row["Amount"])
        )
        for _, row in df_s2.iterrows()
    ]
    tbs.append(RawTrialBalance(entity_code="Company_S2", period=config.current_period, currency="USD", rows=rows_s2))

    # Company S3
    df_s3 = pd.read_excel(sample_dir / "TB_Company_S3.xlsx")
    rows_s3 = [
        RawTBRow(
            account_code=str(row["Account Code"]),
            account_description=str(row["Account Description"]),
            debit=float(row["Debit"]) if pd.notna(row["Debit"]) else 0.0,
            credit=float(row["Credit"]) if pd.notna(row["Credit"]) else 0.0
        )
        for _, row in df_s3.iterrows()
    ]
    tbs.append(RawTrialBalance(entity_code="Company_S3", period=config.current_period, currency="SGD", rows=rows_s3))

    return tbs
