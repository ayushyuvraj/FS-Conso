# Autonomous Verification & Production Hardening Ledger (EVENTS.md)

This document tracks all autonomous verification runs, edge-case hardening audits, deployment checks, and git checkpoints across the lifecycle of the Enterprise Financial Consolidation Portal.

---

## Event Log

### [2026-11-26 14:50] UX Alignment: Restoration of Institutional Step 1 Look & Feel & Dedicated Perimeter Approval Dialog
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Strict Look & Feel Restoration**:
     - Restored the exact original high-finance institutional design of the Step 1 view (`renderStep1`).
     - Action button quad restored in the top-right header:
       - **Upload Icon Button** (`openBatchUploadModal()`)
       - **Refresh Icon Button** (`refreshCurrentStep()`)
       - **Reset Icon Button** (`triggerResetBaseline()`)
       - **Run Consolidation Primary Button** (`triggerRunPipeline()`)
     - Perimeter readiness strip (green for complete, amber for incomplete) preserved in its sleek, full-width position.
     - Restored the pristine financial table (`fin-table`) with tabular figures (`font-variant-numeric: tabular-nums; font-family: monospace`), sticky headers, zebra striping, and status indicators (`Tallied (0.00)` vs `Pending Upload`), plus Foreign Exchange Rates verification row.
     - Removed all clutter, embedded dropzones, and large cards from the Step 1 canvas.
  2. **Dedicated Perimeter Approval Dialog**:
     - Added `#modal-perimeter-approval` (`max-w-4xl`), which is displayed cleanly *on top of the page* immediately after the user uploads files via `#modal-batch-upload`.
     - In this dialog:
       - Parent Company review card (file, sheet, detected columns, 5-row preview, confidence badge, date mismatch alert).
       - Subsidiary review cards (file, sheet, detected columns, 5-row preview, confidence badge, fallback single upload button).
       - Mandatory FX Rates review card (closing, average, historical, swap rate mappings, currency pairs preview).
       - Collapsible Ignored / Extra Sheets drawer.
       - "Cancel" and "Approve & Confirm Ingestion" buttons.
  3. **Verification**:
     - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
     - Full regression test suite: 76/76 PASSED in 29.04s.
     - Live server: HTTP 200 OK on port 8000.

### [2026-11-26 14:35] Milestone: Step 1 Dual-Engine Ingestion, Multi-Sheet Parsing & Perimeter Approval
- **Branch**: `feature/profile-v2`
- **Core Requirements Implemented**:
  1. **Dual-Engine Toggle & Dynamic Confidence Routing**:
     - Embedded and modal checkboxes: `"Check deterministic"` and `"AI agents"` (both checked by default).
     - Dynamically respects configured confidence threshold percentage from settings (e.g. 85%).
     - Fast deterministic heuristics inspect file names, sheet names, headers, and top 5–10 sample rows; escalates ambiguous or low-confidence layouts to Gemini Agentic Brain; falls back with clear "Human-in-the-Loop review" badge if confidence remains below threshold.
  2. **Multi-Sheet & Dump File Deconstruction**:
     - Decomposes single Excel workbooks containing multiple sheets (`openpyxl`) into discrete classified candidates.
     - Unassigned/extra sheets (e.g. notes, instructions, logs) cleanly routed to a collapsed "Ignored / Extra Sheets" tray.
  3. **Financial Column Variations & Number Cleansing**:
     - Flexible handling of separate Dr/Cr vs single signed Net Amount (`+`, `-`, accounting parentheses `(1,000.00)`, trailing minus `1,000-`, and `CR`/`DR` indicators).
  4. **Period & Multi-Year Schedule Intelligence**:
     - Automatically scans and filters multi-period schedules by active run cutoff date.
     - Detects calendar year discrepancies (e.g., uploaded 2025 data when run date is 2024) and displays amber warning pills.
  5. **Mandatory FX Rates Table Collection**:
     - Dedicated FX Rates verification card requiring standard columns (As of Date, From Currency, To Currency, Closing Rate, Average Rate, and Swap Rate).
  6. **Human Approval View (Perimeter Review)**:
     - Editable perimeter review interface displaying Parent, each Subsidiary, and FX Rates with mapped columns, top-5 rows preview, and inline fallback single-entity upload.
  7. **Strict Pipeline Gating**:
     - Prevents advancement to Step 2 until all perimeter entities and FX rates are verified and confirmed via `"Approve & Confirm Ingestion"`, locking Step 1 with a green checkmark and unlocking Step 2.
- **Verification & Hardening**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Dedicated automated suite: `tests/test_step1_dual_engine_ingestion.py` (5/5 PASSED).
  - Full regression test suite: 76/76 PASSED (100% pass rate).
  - Live server check: HTTP 200 OK on port 8000.

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

### [2026-11-25 19:15] Incident Resolution: JavaScript Syntax Fix & Header Element Separation
- **Root Cause Analyzed**:
  - A stray closing brace `}` at line 1378 in `fs_conso/web/static/js/app.js` caused a fatal `SyntaxError: Unexpected token '}'` on script parsing.
  - Because `app.js` failed to parse in the browser, all top-level global handlers (`toggleSidebar`, `switchNavSection`, etc.) were left undefined, freezing sidebar navigation and preventing tab switching between Company Profile, Consolidation, and Audit.
  - The previous header implementation combined the hamburger toggle and KPMG logo into a single morphing element that caused UX confusion and click target ambiguity.
- **Hardening Applied**:
  - Removed stray brace at line 1378; syntax verification via `node -c "fs_conso/web/static/js/app.js"` confirmed clean zero-error parsing.
  - Separated the header into two distinct, clear elements:
    1. Dedicated `<button id="btn-toggle-sidebar" onclick="toggleSidebar()">` with crisp SVG hamburger icon.
    2. Distinct `<div class="flex items-center"><img src="/static/img/kpmg-logo.svg" ... /></div>` KPMG brand logo.
  - Verified full functionality of sidebar toggling (expanded <-> collapsed, `Ctrl+B` shortcut) and section switching (`COMPANIES`, `PIPELINE`, `AUDIT`).
  - Retained strict suppression of company name and period/currency indicators when in the Company Profile view.
  - Fully retained Option A High-Density Ledger with live search, sorting, category filtering, and nested subsidiary trays.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Automated tests: 54/54 PASSED (100% pass rate).
  - Portal server live status: HTTP 200 OK.

### [2026-11-25 19:40] Milestone: Luxury Compact Command Strip, Popover Filters & Whitespace Optimization
- **Requirements Implemented**:
  1. **Clean Borderless Command Strip**:
     - Removed the grey/bordered enclosing card box around the search and filter bar.
     - Modern borderless flex row with minimal search bar on the left and exactly two buttons on the right: `Sort` and `Filter`.
  2. **Dedicated Sort & Filter Popovers (Emil Kowalski Physics & Impeccable Craft)**:
     - Implemented `Sort` popover (`#sort-popover-menu`) with spring easing (`cubic-bezier(0.16, 1, 0.3, 1)` and `scale(0.98)` to `scale(1)`).
     - Implemented `Filter` popover (`#filter-popover-menu`) supporting:
       - **Subsidiary Scope**: `All Profiles`, `With Subsidiaries`, `Standalone (0 Subs)`.
       - **Base Reporting Currency**: dynamically extracted list of all reporting currencies across company profiles.
       - **Live Active Indicators**: badge count on `Filter` button, active checkmarks on selections, and a `Reset` action.
     - Document-level outside-click listener and `Escape` key listeners to dismiss popovers gracefully.
  3. **Company Profile Header & Whitespace Optimization**:
     - Completely removed the redundant `"1 Company"` count pill.
     - Reduced excessive top padding and margins across `<main>` and `#view-companies` (`pt-3 pb-6`, `space-y-3.5`).
     - Removed the obsolete `"Expand All"` button as requested.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Reference data syntax check: `node -c "fs_conso/web/static/js/reference_data.js"`: EXIT 0.
  - Full test suite: 54/54 PASSED.
  - Portal server live status: HTTP 200 OK.

### [2026-11-25 19:55] Milestone: Navigation Persistence, Button Harmony, Icon Actions & Enterprise Date Formatting
- **Core Requirements Implemented**:
  1. **Zero-Reset Navigation Persistence**:
     - Stored `activeNavSection` in `localStorage` (`fs_conso_active_nav_section`).
     - On page refresh, user remains on the active section (Company Profile stays on Company Profile, Consolidation stays on Consolidation) instead of defaulting back to Consolidation.
  2. **Button Styling Unification & Prominence**:
     - Upgraded `+ Create Profile` button to match the primary luxury action button format (`h-9 px-5 rounded-lg bg-gradient-to-r from-kpmg-blue to-kpmg-navy text-white font-semibold text-xs shadow-md btn-tactile`).
  3. **Clean Row Actions (Pencil & Trash Icons)**:
     - Replaced text buttons with two minimal, elegant icon action buttons:
       - Pencil SVG icon button for Edit / Update COA.
       - Trash SVG icon button for Delete Profile.
  4. **Created & Last Updated Columns with Enterprise Date Formatting**:
     - Inserted `Created` column before `Last Updated` in the company perimeter table.
     - Added global enterprise date format preference dropdown in Settings drawer (`#setting-date-format`) with 5 standard options (ISO 8601, UK/Europe/India, US Corporate, International Audit, Google Workspace).
     - Persisted format selection in `localStorage` and dynamically formatted all timestamps via `formatDateTime()`.
  5. **Header & Title Restorations**:
     - Restored the merged KPMG logo / hamburger toggle button with hover morphing state (`group-hover:opacity-100 group-hover:scale-100`).
     - Restored Company Profile title font size to `text-xl font-bold text-kpmg-navy`.
  6. **Codified Immutable Preservation Rule (Rule 7)**:
     - Recorded Rule 7 in `AGENTS.md` and user rule definitions to prevent unauthorized mutations of verified features.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Reference data syntax check: `node -c "fs_conso/web/static/js/reference_data.js"`: EXIT 0.
  - Pytest full suite: 54/54 PASSED.
  - Live server check: HTTP 200 OK.

### [2026-11-25 20:05] Milestone: Standardized Button Sizing, Icon-Only Sort/Filter & Subtle Enterprise Search Bar
- **Requirements Implemented**:
  1. **Standardized Create Button**:
     - Standardized button dimensions to exact `h-7 px-3 rounded` matching the Consolidation page's Batch Upload button.
     - Changed button label from "Create Profile" to simply "Create".
     - Removed redundant double plus icon (kept clean single SVG plus icon).
  2. **Icon-Only Sort and Filter Action Buttons**:
     - Removed text "Sort" and "Filter" labels from the buttons.
     - Replaced with sleek `w-7 h-7` icon-only action buttons matching the Edit and Delete icon buttons.
     - Added clean SVG icons, tooltips ("Sort Profiles", "Filter Profiles"), and dynamic indicator badges.
  3. **Subtle, Realistic Search Bar (Google/Anthropic/Microsoft Standard)**:
     - Standardized shape to `h-7 max-w-sm` seamlessly aligning with adjacent `h-7` buttons.
     - Removed harsh outer boundary (`border border-transparent`) and added soft subtle grey fill (`bg-slate-100/80 hover:bg-slate-100 focus-within:bg-white`).
     - Subtle focus ring and shadow on interaction.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Reference data syntax check: `node -c "fs_conso/web/static/js/reference_data.js"`: EXIT 0.
  - Automated tests: 54/54 PASSED (100% pass rate).
  - Portal server live status: HTTP 200 OK.

### [2026-11-25 20:15] Milestone: Ghost Icon Buttons, Uniform Quiet Typography & Standardized Input Sizing
- **Requirements Implemented**:
  1. **Ghost Icon Buttons (No Outer Box/Border)**:
     - Converted `Edit`, `Delete`, `Sort`, and `Filter` buttons to true ghost icon buttons without permanent borders or box backgrounds.
     - Backgrounds and hover states (`hover:bg-slate-100`, `hover:bg-rose-50`) appear exclusively on hover.
  2. **Uniform Quiet Data Cells (No Colored Boxes, Pills, or Bolding)**:
     - Code cell: rendered as quiet mono text (`font-mono text-xs text-slate-700`) without blue pill background or bolding.
     - Company Name cell: rendered as quiet plain text (`text-xs text-slate-700`) without bolding.
     - Currency cell: rendered as quiet mono text (`font-mono text-xs text-slate-700`) without blue border or pill background.
     - Base Chart of Accounts cell: rendered as quiet mono text (`font-mono text-xs text-slate-700`, e.g. `239 GL Accounts`) without green status dot or green text coloring.
  3. **Subsidiaries & Subsidiary Currencies Columns**:
     - Subsidiaries column: displays solely the integer count (e.g. `2`, `3`, `0`), completely removing the word "subs" and bracketed notes like `(2 wholly owned)`.
     - Renamed column header from `Perimeter FX` to `Subsidiary Currencies`.
     - Subsidiary Currencies column: displays clean comma-separated list of subsidiary input currencies (or `—` when 0 subsidiaries exist).
  4. **Standardized Input Box Sizing (Google Gemini API Key Benchmark)**:
     - Standardized the Settings drawer's `Display Date & Time Format` select to `w-full h-9 px-3 rounded border border-kpmg-border font-mono text-xs text-kpmg-text bg-white focus:ring-2 focus:ring-kpmg-electric focus:outline-none`, matching the Google Gemini API key box.
     - Standardized the tolerance number inputs to `h-9 px-3 rounded border border-kpmg-border`.
     - Standardized Search Bar height to `h-9` with subtle borderless background matching corporate design guidelines.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Automated tests: 54/54 PASSED in 31.40s (100% pass rate).
  - Portal server live status: HTTP 200 OK (`active_company_id: c1`, `is_ready: True`).
  - Git checkpoint and remote push: tagged `checkpoint-profile-v2-ghost-buttons-and-plain-cells`.

### [2026-11-25 20:30] Milestone: Consolidation Toolbar Action Alignment (Ghost Upload/Reset & Run Consolidation)
- **Requirements Implemented**:
  1. **Ghost Icon Buttons for Upload and Reset**:
     - Converted `Batch Upload` and `Reset Workspace` buttons to clean borderless ghost icon buttons matching Edit/Delete and Sort/Filter.
     - Upload button: `w-8 h-8 rounded text-slate-500 hover:text-kpmg-blue hover:bg-slate-100 transition flex items-center justify-center cursor-pointer btn-tactile` with cloud upload icon.
     - Reset button: `w-8 h-8 rounded text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition flex items-center justify-center cursor-pointer btn-tactile` with refresh icon and rose hover glow.
  2. **Suppression of Counter Badge**:
     - Completely removed the redundant `${tbs.length} Ingested` counter badge.
  3. **Relocated 'Run Consolidation' Button**:
     - Removed the oversized `Run Consolidation` button from the top sticky stepper navigation bar.
     - Brought it down into the workspace toolbar on the far right where "0 ingested" previously stood.
     - Standardized button dimensions and typography to the established `h-7 px-3 rounded bg-kpmg-blue` corporate standard.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Full automated pytest suite: 54/54 PASSED in 22.47s (100% pass rate).
  - Portal server live status: HTTP 200 OK (`active_company_id: c1`, `is_ready: True`).
  - Git checkpoint and remote push: tagged `checkpoint-consolidation-toolbar-ghost-actions`.

### [2026-11-25 21:30] Milestone: Preliminary Consolidation Run Launcher & Audit Run Ledger Resumption Hub
- **Requirements Implemented**:
  1. **Preliminary Consolidation Run Launcher Screen**:
     - Dedicated `#view-conso-launcher` card presented whenever the user navigates to *Consolidation*.
     - Header top bar displays blank values for Client Name (`""`), Date (`""`), and Currency (`""`) while on the preliminary launcher.
     - Dropdown populated dynamically from all client company profiles created in Company Profile (`#launcher-company-select`).
     - Calendar date picker for selecting the consolidation cutoff date (`#launcher-run-date`).
     - Real-time company master data snapshot card showing parent code, reporting currency, subsidiary count, and Base COA status upon selection.
     - Primary button `Start Consolidation Run` enables only after both company and run date are selected.
     - On launch, generates a sequentially named run (`<Client Name> - Run <N> - <Date>`), initializes `ConsolidationState`, populates top bar indicators, and routes into Step 1 (Ingestion).
  2. **Audit Section Redesign (Consolidation Run Ledger)**:
     - Replaced legacy telemetry/observability graphs with an institutional, high-density Consolidation Run Ledger table styled identically to the Company Profile table.
     - Displays Run Name/Code, Client Company, Cutoff Date, Scope (entity count), Step Status, and Created Timestamp.
     - Filterable by Client Company, Status (`All`, `In Progress`, `Completed`), and full-text search.
  3. **Run Resumption and Viewing Hub**:
     - In-progress runs (`current_step < 6` or incomplete): interactive **Resume** button restores full run state, unlocks prior completed steps, updates top bar indicators, and drops the user directly onto the exact step where work was left off.
     - Completed runs (`is_completed == True`): **View** button loads financial statements in view-only mode at Step 6.
     - Added a clean `New Run` button on the consolidation stepper bar to return to the launcher at any time.
  4. **Persistence & Lifecycle Backend**:
     - Added `fs_conso/core/run_manager.py` managing isolated per-company run persistence under `inputs/workspaces/{company_id}/runs/{run_id}.json`.
     - Added FastAPI routes: `GET /api/runs`, `POST /api/runs/create`, `POST /api/runs/resume`, `POST /api/runs/launcher-mode`.
     - Automatic run state synchronization on pipeline execution and file uploads.
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Automated tests: `tests/test_run_manager.py`: 4/4 PASSED in 5.42s.
  - Regression suite: 12/12 PASSED in 6.15s (100% pass rate).
  - Portal server live status: HTTP 200 OK.

### [2026-11-25 22:00] Milestone: Minimalist Institutional Consolidation Launcher Card & Client Name Fix
- **Requirements Implemented**:
  1. **Purged All Tutorial / Lecture Clutter**:
     - Completely removed the "Fresh consolidation run" badge, "Scope & Cutoff", long descriptive paragraphs, and bottom audit explanatory text.
  2. **Fixed Client Company Name in Dropdown**:
     - Replaced incorrect variable reference with `availableCompanies` populated from `/api/companies`.
     - Automatically calls `populateLauncherCompanies()` whenever company profiles are fetched.
     - Dropdown now immediately displays the exact saved client name (e.g. `Client_1`).
  3. **High-Taste Institutional Card Redesign**:
     - Compact, elegant card (`max-w-xl mx-auto py-12`).
     - Clean side-by-side grid for `Client Company` and `Cutoff Date`.
     - Quiet live perimeter pill showing currency, subsidiary count, and GL account readiness when a client is selected.
     - Action button `Start Consolidation` with Emil Kowalski active press physics (`active:scale-[0.98]`).
- **Verification**:
  - Node.js syntax check: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Live server verification: HTTP 200 OK, dropdown accurately populated with `Client_1`.
  - Automated tests: 4/4 PASSED in 4.43s.
  - Git checkpoint and remote push: commit `d7bf649`.

### [2026-11-25 22:30] Milestone: Ingestion File Gate & Dynamic Read-Only Reporting Period Display
- **Requirements Implemented**:
  1. **Ingestion Run Consolidation Gate Check**:
     - In `triggerRunPipeline()`, added an automated verification check for uploaded trial balance files (`pipelineData.raw_tbs` and `appStatus.uploaded_entities`).
     - If no files have been uploaded when clicking "Run Consolidation" (either from the Step 1 toolbar or the sidebar action button), the portal immediately triggers a friendly notification toast ("Upload Required") and opens the "Batch Document Dispatcher" modal (`#modal-batch-upload`).
  2. **Dynamic Read-Only Target Reporting Period in Batch Upload Modal**:
     - Replaced the editable `<input id="batch-upload-period" type="text" ...>` with an informational, non-editable luxury display element (`#batch-upload-period-disp`).
     - Added an informational lock badge ("Locked for active run") preventing unauthorized alteration of the active run's cutoff period.
     - Preserved existing batch file ingestion API contracts using a hidden input (`<input id="batch-upload-period" type="hidden">`) that automatically carries the active run period.
  3. **Universal Date Format Synchronization**:
     - Implemented `parseLocalDate(dateVal)` and `formatDateOnly(dateVal)` in `app.js` supporting all 5 global date preference formats configured via the Settings drawer:
       - ISO 8601 (`YYYY-MM-DD`)
       - UK / Europe / India (`DD-MM-YYYY`)
       - US Corporate (`MM/DD/YYYY`)
       - International Audit (`DD MMM YYYY`)
       - Americas Compact (`MMM DD, YYYY`)
     - Integrated `updateBatchUploadPeriodDisplay()` so the modal period and the top header period update immediately in real time whenever the user switches the date format in Settings.
- **Verification**:
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Test Suite: 8/8 PASSED in `tests/test_ingestion_gate.py` and `tests/test_run_manager.py`.
  - Live server verification: Uvicorn serving on `http://127.0.0.1:8000` with HTTP 200 OK.

### [2026-11-25 23:20] Milestone: Agentic Ingestion Pipeline, Dynamic Currency Parsing & Perimeter Gating
- **Requirements Implemented**:
  1. **Perimeter Completeness Gating**:
     - Evaluated active Company Profile entity hierarchy (`P`, `S1`, `S2`) against uploaded trial balances in `ConsolidationState`.
     - Blocked `/api/run-pipeline` with a structured 400 error identifying missing perimeter entities when incomplete.
     - Enforced frontend pre-flight verification in `triggerRunPipeline()`, displaying an explanatory warning toast and opening `#modal-batch-upload`.
  2. **Hybrid Entity Identification & Escalation**:
     - Multi-pass deterministic matcher in `FileClassifier` matching entity codes, full legal names, and slug permutations against the active entity roster.
     - Escalation to Gemini Agentic Brain when confidence is below `ai_confidence_threshold` (0.85).
     - Flagging for Human-in-the-Loop (`needs_review`) when ambiguity remains.
  3. **Dynamic Currency-Aware Column Parsing**:
     - Implemented `_find_currency_specific_column` in `FlexibleTBParser` resolving currency-specific column headers (e.g., `Amount_INR` vs `Amount_USD`) tailored to each entity's functional currency.
     - Tolerates arbitrary column ordering (GL Code in Col A or Col H) and extra columns.
     - Supports both 2-column (`Debit`/`Credit`) and single signed-column (`Amount`) accounting formats.
  4. **Step 1 Unified Perimeter Table & Two-Line Entity Cell**:
     - Renders every perimeter entity in Step 1 table: uploaded rows display GL accounts, debits, credits, and `Tallied (0.00)`; missing entities show quiet `Pending Upload` badges.
     - Two-line entity cell design: primary bold legal entity name on top, entity code pill and ownership percentage below, with functional currency badge.
     - Live **Perimeter Readiness Strip** summarizing total vs ingested entities.
  5. **Post-Upload Mapping Review Modal (HITL)**:
     - Added `#modal-hitl-mapping` dialog and `/api/confirm-ingestion-mappings` endpoint for user review and 1-click confirmation of ambiguous files.
  6. **Agent Observability & Traces**:
     - Persists classification decisions, column mappings, and extraction lineage to `session.state.agent_traces` and `session.state.audit_trail`.
- **Verification**:
  - New test suite: `tests/test_agentic_ingestion.py` (5/5 PASSED).
  - Full regression test suite: 13/13 PASSED across all suites.
  - End-to-end multi-entity ingestion verified with multi-currency files.
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Live portal HTTP 200 OK on `http://127.0.0.1:8000`.

### [2026-11-26 13:15] Milestone: Ghost Loader Elimination & Enterprise High-Density Pagination
- **Branch**: `feature/profile-v2`
- **Root Cause & Resolution for Ghost Loader**:
  - Investigated issue where "Loading company profiles..." remained visible beneath the company table despite profiles being fully loaded.
  - Root cause: An accidental duplicate `<div class="flex items-center justify-center h-48 text-kpmg-muted text-xs">Loading company profiles...</div>` was positioned outside `#company-perimeter-content` in `fs_conso/web/templates/index.html` (lines 574–576).
  - Fix: Removed the orphan duplicate block; verified exactly 1 dynamic loading placeholder exists inside `#company-perimeter-content`, which is cleanly replaced upon data fetch.
- **Enterprise High-Density Pagination Architecture**:
  - Implemented centralized, zero-latency client-side pagination in `fs_conso/web/static/js/app.js`:
    - `renderPaginationControls()`: Generates responsive pagination footer with summary counter ("Showing X–Y of Z items"), rows-per-page selector, and tactile navigation buttons.
    - Page size options: **10, 25, 50, and 100** rows per page (defaulting to 10 for clean density).
    - Smart page windowing: Renders direct page numbers with ellipsis windowing (e.g. `1 2 3 ... 10`) for clean horizontal footprint.
    - Full synchronization: Resetting page to 1 automatically when typing in search bars or switching category/currency/company/status filters.
    - Resilient page-size switching: Re-indexes `currentPage` so top visible records stay in view.
  - **Company Profile View**:
    - Integrated with `renderCompanyTableBody()`: slices `filtered` company profiles and docks pagination bar at table card bottom.
    - Preserves inline expandable subsidiary trays (`toggleCompanyExpansion`) and COA metadata across page switches.
  - **Consolidation Audit Ledger View**:
    - Integrated with `renderAuditRunsTable()`: slices `filtered` consolidation runs and docks pagination bar at table card bottom.
    - Retains horizontal table scrollability on smaller screens while keeping pagination bar docked 100% width.
  - **Styling & Interaction Physics**:
    - Styled with `.fin-pagination-bar` using `--kpmg-border`, `#F8FAFC`, and tabular figures (`font-variant-numeric: tabular-nums`).
    - Emil Kowalski spring micro-interactions: `.btn-tactile` with `active: scale(0.97)` and `cubic-bezier(0.16, 1, 0.3, 1)`.
- **Verification**:
  - Created automated test suite `tests/test_ui_pagination_and_templates.py`:
    - `test_index_template_ghost_loader_eliminated`: PASSED.
    - `test_app_js_pagination_architecture`: PASSED.
    - `test_pagination_math_edge_cases`: PASSED (0, 2, 75, 120 items, clamping, boundaries).
    - `test_api_companies_and_runs_endpoints`: PASSED (HTTP 200 OK).
  - Full regression test suite: 71/71 PASSED (100% pass rate).
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Live server verification on `http://127.0.0.1:8000`: HTTP 200 OK for `/api/companies` and `/api/runs`.






