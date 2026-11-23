# Financial Consolidation & Strict Provenance Rules

Domain rules codified directly from `Conso.xlsx` (Sheets: 'Project scope', 'Phase 1', 'Steps', 'Overview', 'Balance Sheet', 'Profit & Loss Statement').

## 1. Mandatory Google Gemini API Key Gate
- **Strict Execution Prerequisite**:
  - The consolidation engine will **refuse to execute** if an active Google Gemini API key is not present and verified.
  - Startup checks `GEMINI_API_KEY`. If missing, the app locks down and directs the user to supply the key.

## 2. Strict 100% Excel Formula Provenance
- In the final consolidated output workbook (`Consolidated_Financial_Statements.xlsx`):
  - **Zero hardcoded numbers in downstream sheets**:
    - `Translated_TB`: Every cell must be a formula (e.g. `='TB_Sub1'!C10 * 'FX_Rates'!C5`).
    - `FCTR`: Must be calculated via dynamic formula: `=-SUM(E5:E45)`.
    - `IC_Eliminations`: Elimination entries reference the matched entity TB cells.
    - `Consolidated_TB`: Total column must be `=SUM(C10:G10) + H10` (Entities + Eliminations).
    - `Balance_Sheet`: Every line item references the Consolidated TB or rollup sums.
    - `Profit_and_Loss`: Every revenue/expense item references the Consolidated TB.
  - The client must never encounter a number whose origin is untraceable.

## 3. Core Financial Accounting Rules (Ind AS 110 / 21)
- **Validation Engine**:
  - Two-column TBs: `Total Debits == Total Credits`.
  - One-column TBs: `Sum of all amounts == 0.00`.
  - Assets & Expenses: Positive (+).
  - Liabilities, Income & Equity: Negative (-).
  - **Blank != Zero**: A blank cell is missing data (triggers error); zero is a valid nil value.
- **FX Translation & FCTR (Ind AS 21)**:
  - Balance Sheet (Assets & Liabilities): **Closing FX Rate**.
  - Profit & Loss (Income & Expenses): **Average FX Rate**.
  - Equity & Capital: **Historical FX Rate**.
  - Net mathematical translation difference plugs into **FCTR (Foreign Currency Translation Reserve)**.
- **Ownership & Non-Controlling Interest (NCI)**:
  - `NCI % = 1.0 - Holding %`.
  - Consolidation adjusts for NCI in Equity.
- **Intercompany Matching & Dual Tolerances**:
  - Match on `(Entity, Counterparty, Account, Amount)`.
  - `|Variance| <= Absolute Tolerance OR Variance % <= Percent Tolerance`: Auto-clears to IC Variance (Amber).
  - `|Variance| > Tolerance`: Tagged as Red Exception for review, but does not block pipeline completion.
