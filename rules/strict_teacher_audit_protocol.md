# Strict Teacher Multi-Agent Audit Protocol

Guidelines for the autonomous multi-agent verification team and strict self-grading evaluation.

## 1. Multi-Agent Team Structure
1. **Validator Agent**:
   - Audits raw TBs: debit/credit equality, blank vs zero distinction, period/entity alignment.
2. **COA Mapping Agent**:
   - Matches local GLs against Group COA using exact historical rules and Google Gemini semantic inference.
   - Enforces user-configured confidence threshold.
3. **FX Translation Agent**:
   - Applies Closing/Average/Historical rates and computes exact mathematical FCTR plug.
4. **Elimination Arbiter Agent**:
   - Matches reciprocal transactions, checks tolerances, generates zero-balanced elimination journals.
5. **Formula Builder Agent**:
   - Writes openpyxl dynamic coordinate formulas for 100% of calculated cells across all sheets.
6. **Strict Teacher / Auditor Agent**:
   - Independently reviews the entire output before presentation to the user.

## 2. Strict Teacher Evaluation Rubric (0 to 100)
The Auditor Agent evaluates the consolidated workbook and application state across 4 pillars (25 points each):

| Pillar | Strict Criteria | Max Points |
|---|---|---|
| **1. Formula Integrity** | 100% of calculated cells start with `'='`. Zero orphan static constants in downstream sheets. Precedents resolve cleanly. | 25 |
| **2. Financial Correctness** | Balance Sheet equation holds: `Total Assets == Total Liabilities + Equity`. Translated TB sums to 0.00 with FCTR. Eliminations balance to 0. | 25 |
| **3. Tolerance & Validation** | Out-of-tolerance items are properly flagged red; within-tolerance variances are recorded; no unmapped accounts. | 25 |
| **4. UI/UX & Interaction** | Zero text drift, morph-like layout stability, responsive stepper gating, clean KPMG visual language, no broken controls. | 25 |

## 3. Strict Gate Policy
- **Passing Threshold**: Score >= **95 / 100**.
- If the score is `< 95`, the Auditor Agent halts the presentation, identifies the exact failing criteria, and triggers a feedback loop back to the relevant agent node to fix and re-verify until perfection is achieved.
