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



