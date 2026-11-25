# Autonomous Verification & Production Hardening Ledger (EVENTS.md)

This document tracks all autonomous verification runs, edge-case hardening audits, deployment checks, and git checkpoints across the lifecycle of the Enterprise Financial Consolidation Portal.

---

## Event Log

### [2026-11-25 18:35] Milestone: Dynamic Profile Creation & Base COA Architecture (Phase 1)
- **Branch**: `feature/profile-v2`
- **Core Changes**:
  - Replaced legacy stub workspaces with dynamic multi-entity profile creation (`fs_conso/core/company_manager.py`).
  - Added Base Chart of Accounts parser (`fs_conso/core/coa_parser.py`) supporting `.xlsx`, `.xls`, `.csv` with flexible column auto-detection (Account Code, Description, Account Type, Financial Statement, Rollup Group).
  - Implemented Emil Kowalski tactile shake validation (`@keyframes field-shake`, `.shake-error`, `.input-invalid`) with zero console errors.
  - Added reference databases for 195 sovereign countries and 20 top global currencies (`fs_conso/web/static/js/reference_data.js`).
  - Implemented clean 0-company baseline on startup with full multi-subsidiary snapshot table.
- **Verification**:
  - Automated tests: 51/51 PASSED.
  - End-to-end HTTP creation test: 200 OK with parent and 3 subsidiaries.

### [2026-11-25 18:40] Production Hardening: Resilient Profile Lookup, Case-Insensitive Renaming & Master Data Retention
- **Root Cause Analyzed**:
  - `get_company()` relied solely on directory slug match without fallback to `company_code` or case-insensitive matching across workspace directories.
  - Duplicate code check checked `other["company_id"] != target_id` without lowercase normalization, triggering false code collision when updating profiles with uppercase codes.
  - In-place renaming (changing casing of company name or code) failed if the identifier casing diverged.
- **Hardening Applied**:
  - Multi-tier case-insensitive resolver in `get_company()` (slug, id, code, directory name, company name).
  - Normalized target ID and duplicate code checking using `lower()`.
  - In-place renaming preservation: retains existing Base COA, entity hierarchy, FX tables, and timestamps during name/casing updates.
  - Zero-exception fallback: if an existing profile is edited without a new COA file, its existing Base COA is strictly preserved.
- **Verification**:
  - Added `tests/test_robust_company_updates.py`.
  - Full suite: 54/54 PASSED.

### [2026-11-25 18:52] UX Refinement: Context-Aware Header & Clean Profile Workspace State
- **Problem**:
  - When viewing the Company Profile page or when no active profile was selected, the header top-right displayed awkward dashes (`— • —`) intended for pipeline execution time and currency.
  - The center title displayed `"No Active Profile"` even on the dedicated company management screen.
- **Resolution**:
  - Updated `index.html` to remove the default `md:flex` display on `#header-period-curr-wrap`, preventing unstyled flash of dashes.
  - Contextual visibility in `renderHeaderStatus()` and `switchNavSection()`: dynamically suppresses the period & currency widget whenever the user is in the `COMPANIES` view or whenever no active profile exists.
  - Suppressed the `"No Active Profile"` banner from the top-center on the Company Profile management screen.
  - Added automatic default redirection to the Company Profile workspace on initial launch when 0 companies exist.
- **Verification**:
  - Automated tests: 54/54 PASSED.
  - Live server check: HTTP 200 OK.

### [2026-11-25 19:08] Milestone: Option A High-Density Institutional Ledger & Header Clean-up
- **Requirements Implemented**:
  1. Complete suppression of client names (such as `Client_1`) in the top navigation header while viewing the Company Profile page.
  2. Option A High-Density Institutional Ledger Architecture:
     - Replaced bulky ~450px card layout with sleek single-row (~42px) table layout.
     - Live multi-attribute search filtering by Company Name, Company Code, Subsidiary Name, Country of Incorporation, and Currency.
     - Multi-attribute sorting: Name (A-Z, Z-A), Code, Subsidiary Count (high/low), COA Account Count, Recently Updated.
     - Category filter chips: `All (N)`, `With Subs (N)`, `Standalone (N)`.
     - 1-Click Expand / Collapse: interactive chevron and row click smoothly expands an inline tray showing the complete subsidiary table and COA/perimeter metadata.
     - Global "Expand All" / "Collapse All" toggle button.
     - Removed obsolete "Set Active" / "Active Profile" buttons; row actions strictly limited to `Edit / Update COA` and `Delete`.
- **Verification**:
  - Pytest full suite: 54/54 PASSED.
  - Zero syntax or JavaScript console errors.


