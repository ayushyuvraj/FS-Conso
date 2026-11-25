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
