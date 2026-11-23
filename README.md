# Enterprise Financial Consolidation Engine (Ind AS 110)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-navy.svg)](https://github.com/langchain-ai/langgraph)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange.svg)](https://ai.google.dev/)
[![Accounting](https://img.shields.io/badge/standards-Ind%20AS%20110%20%7C%2021-emerald.svg)]()
[![Formula Provenance](https://img.shields.io/badge/Excel-100%25%20Formulas-brightgreen.svg)]()

A white-label, multi-entity financial consolidation platform built on **LangGraph** and powered by **Google Gemini**, with an institutional **FastAPI + Modern Tailwind** web portal.

The engine automates the ingestion, validation, standardization, currency translation, intercompany elimination, and aggregation of subsidiary Trial Balances into IND AS-compliant Consolidated Financial Statements (Balance Sheet and Profit & Loss Statement) with **100% cell-level Excel formula traceability**, strict zero-simulation realism, and comprehensive multi-agent auditability.

---

## Key Highlights

1. **100% Cell Formula Traceability Guarantee**:
   - In the generated deliverable (`Consolidated_Financial_Statements.xlsx`), raw numbers exist **only** in the initial entity TB sheets.
   - Every single downstream cell across `Translated_TB`, `IC_Eliminations`, `Consolidated_TB`, `Balance_Sheet`, and `Profit_and_Loss` is an active Excel formula (e.g., `='TB_Company_S2'!E7 * 'FX_Rates'!D4`, `=-SUM(G4:G10)`, `=SUMIFS(...)`).
   - Zero hardcoded numbers in downstream sheets. Press `Ctrl + [` in Excel to trace precedents directly back to source entity TBs.

2. **KPMG-Themed Web Portal with Gated Stepper**:
   - Palette: Deep Navy (`#001D48`), KPMG Royal Blue (`#00338D`), Electric Blue (`#0091DA`), and crisp neutrals (`#F4F5F7`).
   - 6-step gated stepper:
     `1. Ingestion` → `2. Mapping` → `3. Translation` → `4. Eliminations` → `5. Consolidation` → `6. Statements & Audit`
   - Next steps remain strictly locked until prior steps pass validation.
   - PowerPoint Morph-like layout stability: No text drift, no pixel jumping, and standardized element sizes.

3. **LangGraph Multi-Agent Team with Strict Teacher Auditor**:
   - Multi-agent orchestration: `validator` → `mapper` → `translator` → `elimination` → `aggregator` → `excel_builder` → `auditor`.
   - Autonomous **Strict Teacher Auditor Agent** independently scores the consolidation output across 4 pillars (Formula Integrity, Financial Correctness, Validation & Tolerance, Provenance & Flow) with an **Honors Pass threshold of >= 95.0 / 100** (Current benchmark score: **100.0 / 100**).

4. **Configurable Settings Drawer**:
   - Dynamic AI Confidence Threshold Slider (0–100%, editable to any value, default 85%).
   - Intercompany Dual Tolerances (Absolute Amount threshold and Percentage threshold).
   - Mandatory Google Gemini API Key management.

5. **Mandatory Execution Gate**:
   - An active Google Gemini API key is a non-negotiable blocking prerequisite. The engine strictly halts and will not run without an active key.

---

## Project Structure

```
.
├── Conso.xlsx                          # Baseline reference specification
├── rules/                              # Localized Design & Engineering Rulebooks
│   ├── design_system_pro_max.md        # KPMG palette + Anthropic + Impeccable + Malewicz depth
│   ├── emil_kowalski_craft.md          # Micro-interactions, spring physics, morph stability
│   ├── financial_consolidation_rules.md# Ind AS 110/21, FCTR plug, NCI math, 100% formula rules
│   ├── impeccable_and_pro_max.md       # Token scale, WCAG AA contrast, layout discipline
│   ├── strict_teacher_audit_protocol.md# Multi-agent review protocol & strict grading rubric
│   └── unslop_and_taste.md             # Claude frontend design & anti-slop guidelines
├── inputs/                             # Ingestion directory for entity TBs
│   └── sample_data/                    # Benchmark 4-entity conglomerate fixture
├── outputs/                            # Generated Excel deliverables
│   └── Consolidated_Financial_Statements.xlsx # 100% formula-linked Excel deliverable
├── fs_conso/                           # Core Python application package
│   ├── config.py                       # App configuration, tolerance settings, API key gate
│   ├── models/                         # Pydantic schemas (Entity, COA, TB, FX, Elimination)
│   ├── core/                           # Financial computation engines (Validator, Mapper, FX, Elim)
│   ├── excel/                          # 100% Formula-driven Excel generator (openpyxl)
│   ├── agent/                          # LangGraph Multi-Agent Team & Strict Teacher Auditor
│   └── web/                            # FastAPI backend + Tailwind CSS frontend
├── tests/                              # Automated test suite (9 passing tests)
├── run_portal.py                       # One-command web portal runner
└── test_run.py                         # Headless CLI test runner
```

---

## Quick Start

### 1. Requirements & Setup
```powershell
pip install -r requirements.txt
```

### 2. Launch the Web Portal
```powershell
python run_portal.py
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### 3. Run Automated Tests
```powershell
python -m pytest tests/ -v
```

---

## Standards Compliance
- **Ind AS 110**: Consolidated Financial Statements (Parent-Subsidiary control, NCI accounting).
- **Ind AS 21**: The Effects of Changes in Foreign Exchange Rates (Closing, Average, Historical rates, FCTR balancing plug).
- **Ind AS 103**: Business Combinations (Goodwill / Capital Reserve).
