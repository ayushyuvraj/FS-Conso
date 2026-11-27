# Autonomous Verification & Production Hardening Ledger (EVENTS.md)

This document tracks all autonomous verification runs, edge-case hardening audits, deployment checks, and git checkpoints across the lifecycle of the Enterprise Financial Consolidation Portal.

---

## Event Log

### [2026-11-27 13:20] Milestone: Step 5 Goodwill - Floppy Disk Icon Save Button & FX Transition Header Indicators
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Floppy Disk Save Button Parity**:
     - Replaced text "Save" and previous icon with a dedicated floppy disk SVG icon (`w-4 h-4`, `M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z`).
     - Aligned button footprint to match Ingestion toolbar ghost icon buttons (`w-8 h-8 rounded text-slate-500 hover:text-kpmg-blue hover:bg-slate-100 transition flex items-center justify-center cursor-pointer btn-tactile relative select-none`, `title="Save Changes"`).
     - Removed all inner text labels across idle and saving states (spinner appears in-place within the button).
  2. **Multi-Currency FX Transition Header Indicators**:
     - In the table header for every subsidiary whose currency differs from the base reporting currency (e.g. `B` in `USD` and `C` in `EUR` with `INR` base), rendered the conversion path indicator (`USD &rarr; INR`, `EUR &rarr; INR`).
     - Retained standard single currency badge for entities matching base reporting currency (`INR`).
  3. **Verification & Hardening**:
     - JavaScript syntax validated (`node -c fs_conso/web/static/js/app.js`: 0 errors).
     - Unit test suite (`tests/test_goodwill_engine.py`): 6/6 passed (100%).

### [2026-11-27 13:10] Milestone: Step 5 Goodwill Matrix - N-Column Sticky Scrolling, Center Headers, Manual Save Action & Ingestion Button Parity
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **N-Column Horizontal Scrolling & Fixed Particulars Column**:
     - Upgraded the Goodwill table to support any scale of subsidiaries ($N = 1$ to $30+$ subsidiaries).
     - Applied smooth horizontal overflow (`overflow-x-auto min-h-[460px] max-h-[calc(100vh-270px)] border border-kpmg-border rounded-lg bg-white shadow-2xs`).
     - Permanently pinned the first column (**Particulars**) across the table header and all 7 data rows (`w-[220px] min-w-[220px] max-w-[220px] sticky left-0 z-10/z-30 bg-white/bg-slate-100 shadow-[inset_-1px_0_0_var(--kpmg-border)] border-r border-slate-100`).
  2. **Center-Aligned Entity & Remarks Headers**:
     - Center-aligned headers for the Parent Company, all Subsidiaries, and the Remarks column (`text-center px-3 py-2.5 min-w-[160px]/min-w-[180px]`).
     - Kept the Particulars header left-aligned for clear tabular hierarchy.
  3. **Removed Top Badge Boxes**:
     - Stripped out the `Total Goodwill` (green badge) and `Total Reserves` (yellow badge) summary cards from the top card, maintaining a clean executive layout.
  4. **Primary Consolidate Button Parity**:
     - Aligned the primary action button on Step 5 Goodwill to match Step 1 Ingestion: exact position, dimensions (`h-7 px-3 rounded`), styling (`bg-kpmg-blue hover:bg-kpmg-navy text-white text-[11px] font-semibold`), tactile spring animation (`btn-tactile`), play-circle icon with `#ACEAFF`, and identical text (`Consolidate`).
  5. **Borderless Ghost Save Button**:
     - Introduced `#btn-goodwill-save` directly to the left of the Consolidate button matching Ingestion ghost action styling (`h-7 px-2.5 rounded text-slate-600 hover:text-kpmg-blue hover:bg-slate-100 transition flex items-center space-x-1 text-[11px] font-semibold cursor-pointer btn-tactile select-none`).
     - Replaced keystroke auto-syncing with manual Save execution (`saveGoodwillScheduleManual`), persisting values to `/api/pipeline/goodwill/update` with loading state and confirmation toast.
     - Hardened dynamic row operations (`addGoodwillAdjustmentRow`, `deleteGoodwillAdjustmentRow`) and `confirmGoodwillSchedule` to automatically persist pending in-memory edits before execution.
  6. **Verification & Hardening**:
     - JavaScript syntax check: `node -c fs_conso/web/static/js/app.js` passed (0 errors).
     - Goodwill unit tests: `tests/test_goodwill_engine.py` 6/6 passed (100%).
     - Full suite verification: 106 passed.

### [2026-11-27 12:45] Milestone: Step 5 Goodwill Matrix Polish - Fixed Column Layout, Zero Horizontal Scroll & Compact Code-Only Dropdowns
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Clean Particulars & Header Styling**:
     - Stripped out all redundant descriptive subtitles across all 7 row types:
       - Row 1: `Share capital` (clean bold text; removed "From Group COA Level 0 (Translated)").
       - Row 2: `Adjustments` (removed separate subheader banner row spanning all columns; default 1 row with small tactile `+` button in Particulars cell to append dynamic adjustment rows).
       - Row 3: `Retained earnings and addition` (clean bold text; removed "At Acquisition Date").
       - Row 4: `Net asset acquisition` (clean bold text; removed "Sum of rows 1 + 2 + 3").
       - Row 5: `Investment by company` (clean bold text; removed "Purchase Consideration (Deterministic / LLM / HITL)").
       - Row 6: `Goodwill` (clean bold text; removed subtitle).
       - Row 7: `Reserves` (clean bold text; removed subtitle).
  2. **Table Grid & Fixed Column Widths (Zero Horizontal Scroll)**:
     - Configured `<table class="fin-table w-full" style="table-layout: fixed; width: 100%;">` with explicit `<colgroup>` (Particulars: 220px, Entities: evenly distributed `width: auto`, Remarks: 180px).
     - Applied `overflow-hidden` on table container and cells, eliminating unwanted horizontal scrollbars.
  3. **Space-Saving Compact Code-Only Dropdowns**:
     - Configured closed dropdown triggers for Share Capital Level 0 and Parent Investment Accounts to display **ONLY the account code** (e.g. `E210101`, `A120101`), capped at `max-w-[130px]`.
     - Created interactive floating popovers (`openGoodwillInvestDropdown`, `renderGoodwillInvestPopoverContent`, `selectGoodwillInvestAccount`) matching the Level 0 popover with real-time search, account descriptions, and balances.
  4. **Targeted Remarks Column**:
     - Input field active strictly on dynamic Adjustments rows for recordkeeping.
     - Centered `—` rendered across all other rows.
  5. **Verification & Hardening**:
     - Syntax verification: `node -c fs_conso/web/static/js/app.js` passed with zero errors.
     - Goodwill engine & API tests: `tests/test_goodwill_engine.py` 6/6 passed (100%).
     - Full test suite: 106 passed, 1 skipped, 0 failed in 30.90s.


### [2026-11-27 02:05] Milestone: Universal Level 0 Leaf Account Mapping, Rollup Header Exclusion, Ind AS 21 Entity Tabs & Bottom-Right Toast Removal
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Universal Level 0 Account Rule (Zero Rollup Headers)**:
     - Enforced universal requirement across all entities: the system and LLM MUST ALWAYS select from leaf Level 0 accounts only, never higher-level rollup headers (e.g. `100000 Assets`, `110000 Non-Current Assets`, `110300 Other Intangible Assets`, `500000 Expenses`).
     - Enhanced domain models (`fs_conso/models/coa.py`):
       - Added `@property is_level_0` on `COAItem` dynamically detecting whether an account is a true leaf account vs a rollup header.
       - Added `get_level_0_items()` and `get_level_0_codes()` on `ChartOfAccounts` returning strictly leaf accounts (174 leaf accounts in `Conso.xlsx` vs 65 rollup headers).
     - Enhanced parser hygiene (`fs_conso/core/coa_parser.py`):
       - Prevented higher-level rollup rows from falling back to `level_0_account = name`.
  2. **LLM Judge & Semantic Ranker Candidate Scoping (`fs_conso/core/mapper.py`)**:
     - `_format_complete_coa_candidates`: Populated reference prompt exclusively from `self.coa.get_level_0_items()`. The Gemini LLM prompt never receives rollup headers like `100000` or `500000`.
     - `_fallback_semantic_ranking`: Evaluates candidate options and confidence scores exclusively over `self.coa.get_level_0_items()`.
     - Filtered AI responses in `_call_gemini_mapping_batch` to strictly discard non-Level 0 items and fall back to top valid Level 0 candidates.
     - Updated `ACCOUNTING_SYNONYMS` targets to strictly Level 0 accounts (`E210201`, `A120402`, `A120401`, `A120403`, `A120301`, `L320302`, `A110109`, `X540101`, `X560101`, `I410103`).
  3. **Mapping Cache & Historical Profile Hygiene**:
     - Added `COAMappingEngine.clear_cache()` and active cache sanitization in `mapper_node` (`fs_conso/agent/nodes.py`) evicting any stale non-Level 0 entries.
     - Enhanced `CompanyProfile.get_mappings_dict()` and `CompanyProfile.add_mapping()` in `fs_conso/models/company.py` to enforce Level 0 validation and reject rollup headers.
     - Protected `/api/hitl/resolve`: Returns HTTP 400 Bad Request with explicit audit explanation if a user or script attempts to map to a higher-level rollup header.
  4. **Fresh Re-run Across Client_2 Perimeter (340 Accounts)**:
     - Executed a clean, fresh re-run of `mapper_node` across all 4 perimeter entities (`Client_2`, `A`, `B`, `C`).
     - Verified `2025 - Intangible Assets` in entity `A`:
       - Automatically mapped to Level 0 account `A110303 - Intangible Assets under Development` (95% confidence).
       - Ranked candidates list contains strictly Level 0 options: `A110303 (Intangible Assets under Development)`, `A110304 (Accumulated Amortisation - Intangible Assets)`, and `X570102 (Amortisation of Intangible Assets)`.
       - Rollup headers `100000` and `110300` are 100% excluded.
     - Verified all 340 accounts across all entities strictly map to Level 0 accounts (or `999999` unmapped exception).
  5. **Removal of Bottom-Right Toast Notifications**:
     - Removed `#toast-container` element from `fs_conso/web/templates/index.html`.
     - Added CSS `#toast-container { display: none !important; }` in `style.css`.
     - Transformed `showToast()` in `fs_conso/web/static/js/app.js` into a silent no-op.
  6. **Step 3 Ind AS 21 FX Translation Engine & Entity Tabs**:
     - Cleaned translation title to "Foreign Currency Translation".
     - Implemented dynamic entity tabs ($N$ tabs: 1 Parent + 1 for each Subsidiary).
     - Applied Closing (Assets/Liabilities), Average (P&L), and Historical (Equity) rates, balancing net translated balance strictly to `0.00` via automated FCTR plug (`O620102`).
  7. **Automated Verification & Hardening**:
     - Added targeted unit and regression tests in `tests/test_step2_llm_mapping.py` (`test_hitl_resolve_rejects_non_level_0_rollup_header`, `test_level_0_filtering_excludes_all_rollups_across_master_coa`, `test_2025_intangible_assets_candidates_are_strictly_level_0`).
     - Full Regression Suite: **100/100 PASSED (100%)** in 28.53s (`python -m pytest tests/`).
     - Live server: Verified operational on port 8000.
     - Git: Staged, committed, and pushed cleanly to remote branch `feature/profile-v2`.

### [2026-11-27 00:20] Milestone: Step 2 Interactive Column Sorting, Scroll Position Retention, Dynamic HITL Counter, Status Tick Iconography & LLM Provenance Popovers
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Column Sorting Across All Headers (Requirement 1)**:
     - Implemented dynamic, bidirectional sorting on all 7 financial ledger columns in Step 2: `Account Code`, `Account Name`, `Currency`, `Amount`, `Level 0 Mapping`, `Confidence`, and `Status`.
     - Sorting by `Status`: Clicking the header in ascending mode groups all accounts requiring auditor attention (`Review Required`) at the top of the table, allowing auditors to focus on actionable exceptions in one consolidated view. Secondary tie-breaking preserves numeric account code order.
     - Interactive headers feature visual indicators (`▲`, `▼`, and subtle `▲▼` inactive indicators) styled in KPMG Royal Blue and slate.
  2. **Scroll Position Retention on "Accept" & L0 Selection (Requirement 2)**:
     - Eliminated entire-table re-rendering on single-account approvals.
     - Implemented in-place DOM row updating via unified `approveMappingItem()` helper: targets the specific table row (`tr[data-entity][data-code]`), removes the amber highlight, updates the Level 0 button text, sets Confidence to 100%, and transforms the Status cell into a clean green checkmark tick.
     - Retains the exact scroll position in `#step2-table-container` (`scrollTop` untouched). Auditors can continuously scroll downward and click "Accept" without jumping to the top of the table.
  3. **LLM Routing Transparency & Scoping in (i) Popover (Requirement 3)**:
     - Addressed user feedback regarding transparency of LLM vs deterministic matching.
     - Enhanced `openCandidatePopover`:
       - `GEMINI_AI`: Displays purple badge `[ Gemini LLM Judge ]`, notes that the account had no exact deterministic rule match and was routed to the Gemini AI Agentic Brain, and displays ranked candidate options with confidence percentages and reasoning.
       - Deterministic matches (`DIRECT_CODE_MATCH`, `HEURISTIC_EXACT`, `ACCOUNTING_SYNONYM`, `HISTORICAL_RULE` / `USER_APPROVED_RULE`): Displays emerald/blue/indigo badges, clearly explains the matching rule, and explicitly notes: *"Confidence: XX% (Deterministic). Not routed to LLM."*
       - Transparently reveals that deterministic accounts are not sent to the LLM.
  4. **Dynamic HITL Counter Decrement (Requirement 4)**:
     - Implemented `refreshHITLCounters()` helper:
       - Recalculates total pending reviews across all entity tabs whenever an approval occurs.
       - Decrements the top header badge (`#badge-hitl-count`) live from 46 down to 45, 44... 1, and hides the badge completely once all items are approved.
       - Dynamically updates individual entity tab dots (`#step2-tab-dot-${entityCode}`), transitioning pulsing amber dots to solid emerald when all items in a tab are approved.
       - Automatically unlocks the primary action button (`#btn-consolidate-step2`) once all accounts across all entities are approved.
  5. **Status Column Iconography (Requirement 5)**:
     - Replaced the green text badge `"Mapped"` with a clean green checkmark circle icon (`bg-emerald-100 text-emerald-600 border border-emerald-200`) with checkmark SVG.
     - For items requiring review: Displays alert triangle icon + `"Review Required"` badge and tactile green `"Accept"` button.
     - Approving an item immediately transforms the cell in-place into the green checkmark icon.
  6. **Automated Verification & Hardening**:
     - Added new tests in `tests/test_step2_mapping_tabs.py` (`test_deterministic_vs_llm_provenance_tagging`, `test_hitl_resolve_decrements_to_zero_and_unblocks`).
     - JavaScript syntax verification: `node -c fs_conso/web/static/js/app.js` (0 errors).
     - Full Regression Suite: **95/95 PASSED (100%)** in 27.82s (`python -m pytest tests/`).
     - Verified live server responds with HTTP 200 OK on port 8000.
     - Atomic Git commit and push to remote branch `feature/profile-v2`.

### [2026-11-26 23:50] Milestone: Stepper Header Border Unification & Generic Step Completion Gating Enforcement
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Stepper Header Border & Visual Unification (Issue 1)**:
     - Fixed missing border around Step 2 and any inactive/locked steps in the top stepper navigation bar.
     - Added base persistent border and container styling (`border: 1px solid #E2E8F0; border-radius: 6px; background-color: #FFFFFF; color: #475569`) to `.step-tab`.
     - Added distinct `.step-tab.review-needed` amber pill styling (`border: 1px solid #FCD34D; background-color: #FFFBEB; color: #92400E; .step-num background-color: #F59E0B; color: #FFFFFF`) when Step 2 has pending human reviews.
     - Updated `.step-tab.completed` (`border: 1px solid #CBD5E1; background-color: #F1F5F9; color: #0F172A`) and `.step-tab.locked` (`border: 1px solid #E2E8F0; background-color: #F8FAFC`).
     - Every step in the header now possesses an intentional, crisp, and uniform pill border across all states (active, completed, review-needed, unlocked, locked).
  2. **Generic Step Completion Gating Rule (Issue 2)**:
     - Enforced mandatory rule: *If anything in any given step is not complete, the system CANNOT proceed to the next step.*
     - **LangGraph Node Halting**:
       - `mapper_node`: If any accounts require review (`needs_review=True` or `is_ambiguous=True`), sets `state.is_blocked = True`, `state.current_step = 2`, and strips all subsequent steps from `state.completed_steps` (`[s for s in state.completed_steps if s < 2]`). Conditional edge routes to `END`, preventing premature execution of translator, eliminations, aggregator, or excel builder.
       - `translator_node`, `elimination_node`, `aggregator_node`, `excel_builder_node`: Each node now explicitly checks that its prerequisite step is in `completed_steps` and halts with `state.is_blocked = True` if any prerequisite is incomplete.
     - **Backend State Healing & Gating**:
       - In `/api/pipeline-data` and `/api/status`, automatically cleanses corrupted or stale `completed_steps` if mapping decisions have pending reviews, resetting `current_step = 2` and `completed_steps = [1]`.
       - `/api/hitl/resolve`: Only adds `2` to `completed_steps` and advances to Step 3 when all pending reviews across all entity tabs are 0.
       - `/api/run-pipeline`: Returns `success: False` with `current_step: 2` and `halted_node: "mapper"` when mapping requires human review, preventing client-side advancement.
     - **Frontend Step Navigation (`switchStep`)**:
       - Strictly blocks navigation to Step $K$ if any prior step $< K$ is incomplete:
         - Target $\ge 2$: Step 1 must have uploaded, validated, and tallied trial balances with complete perimeter.
         - Target $\ge 3$: Step 2 must have 0 pending reviews across all entity tabs.
         - Target $\ge 4$: Step 3 FX translation must be complete.
         - Target $\ge 5$: Step 4 eliminations must be complete.
         - Target $\ge 6$: Step 5 consolidation aggregation must be complete.
       - Intercepts invalid clicks, displays warning toast explaining the incomplete prerequisite, and redirects user to the earliest incomplete step.
     - **Pipeline Trigger (`triggerRunPipeline`)**:
       - When mapping reviews are required, halts and immediately lands the user on Step 2 (`switchStep(2)`), preventing any jump to Step 6.
  3. **Verification & Hardening**:
     - Added new automated suite: `tests/test_step_progression_gating.py` (4/4 PASSED).
     - Full Regression Suite: **93/93 PASSED (100%)** in 24.77s (`python -m pytest tests/`).
     - JavaScript Syntax Check: `node -c fs_conso/web/static/js/app.js` (0 errors).
     - Live Server: HTTP 200 OK verified on `http://localhost:8000/api/status`.
     - Git: Staged, committed, and pushed cleanly to remote branch `feature/profile-v2`.

### [2026-11-26 20:05] Milestone: Step 2 LLM-as-a-Judge Dynamic Mapping, Multi-Candidate Scoring, Hoverable Info Popover & 1-Click Accept
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **LLM as Judge Routing for Unmatched Accounts**:
     - Upgraded `COAMappingEngine` to evaluate every account deterministically first (historical rules, exact code match, exact name match, standard synonym heuristics).
     - Any accounts remaining unmapped are automatically routed to Gemini LLM-as-a-Judge in batched prompts containing the complete Group Chart of Accounts categorized by nature (Asset, Liability, Equity, Income, Expense) with Level 0 rollup groupings.
  2. **Multi-Candidate Probabilities & Ambiguity Flagging**:
     - The LLM evaluates and returns up to 3 candidate options in descending order of confidence percentage with explicit accounting justifications.
     - **Default Top Selection**: The option with the highest percentage is automatically assigned by default in the Level 0 mapping column (`group_code`, `level_0_name`).
     - **Ambiguity Rule**: If 2 or 3 candidate options are above or near the confidence threshold (or top confidence < threshold), `is_ambiguous = True` and `needs_review = True`, highlighting the row in yellow for required auditor oversight.
  3. **Institutional UI: Confidence Hover Popover `(i)` & 1-Click Accept**:
     - Added an informative `(i)` button in the Confidence column. Hovering or clicking opens `#step2-candidate-popover` displaying all top 3 candidate options with confidence % (Option 1, Option 2, Option 3) and accounting rationales, with 1-click option switching.
     - Added an inline 1-click **`Accept`** checkmark button in the Status column next to `Review Required`. Clicking it immediately approves the default top match, calls `/api/hitl/resolve`, turns the row green, and clears the review requirement.
     - The Level 0 dropdown button remains available for every row to search and select any account from the Group COA.
  4. **Strict Gating**:
     - The top-right **"Consolidate"** button and Step 3 remain locked until all pending reviews across all entity tabs are resolved.
  5. **Verification & Hardening**:
     - New Automated Suite: `tests/test_step2_llm_mapping.py` (3/3 PASSED).
     - Full Test Suite: **89/89 PASSED (100%)** in 35.14s.
     - JavaScript Syntax: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Live server: Verified operational on port 8000.
     - Git: Staged and pushed to remote branch `feature/profile-v2`.

### [2026-11-26 19:40] Milestone: Step 2 Entity Tab Isolation, Non-Zero Amount Preservation & UI Clutter Cleanup
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Strict Entity Tab Partitioning (Zero Cross-Entity Queue Mixing)**:
     - Fixed root cause where legacy or missing `entity_code` in mapping decisions triggered `!m.entity_code` fallback, causing all 340 accounts from all entities to be lumped into every tab.
     - Implemented `getMappingsForEntity(entityCode)` with strict case-insensitive entity code matching.
     - For Parent `Client 2` (`C2`), only its exact 70 accounts (`1002` to `10071`) from the ingested file's `Parent TB` sheet appear.
     - For `Sub A` (`A`), only its exact 80 accounts (`2002`+) from `Sub A TB` appear.
     - For `Sub B` (`B`), only its exact 90 accounts (`3002`+) from `Sub B TB` appear.
     - For `Sub C` (`C`), only its exact 100 accounts (`4002`+) from `Sub C TB` appear.
  2. **Non-Zero Ingested Amount Preservation**:
     - Fixed root cause where single signed amount columns (e.g. `FY 2024-25 (Lakhs)`) produced `0.00` because `row.debit == row.credit` zeroed out the calculated signed amount.
     - Hardened `FlexibleTBParser.parse_dataframe` and `COAMappingEngine.standardize_trial_balance` to prioritize `row.amount` whenever debit and credit match or when single amount column is ingested.
     - In `fs_conso/web/app.py`, included `"rows": [r.dict() for r in tb.rows]` inside each item in `raw_tbs` returned by `/api/pipeline-data`.
     - In `app.js`, cross-referenced `pipelineData.raw_tbs` rows to guarantee that amounts and currencies from the primary trial balance are never displayed as 0.00 if the raw TB contains non-zero balances.
  3. **Auto-Healing of Legacy Run States**:
     - Added auto-healing in `/api/pipeline-data` and `/api/status`: if an active run's mapping decisions lack `entity_code` or `amount`, the backend auto-invokes `mapper_node` to enrich all decisions and persists the healed state via `run_manager.save_run_state`.
     - Updated `MappingDecision` model fields (`entity_code`, `currency`, `amount`) to `Optional` with default `None` to prevent Pydantic deserialization crashes on legacy run records.
  4. **Elimination of Secondary Gray Strip Clutter**:
     - Removed the redundant secondary gray banner strip (`<!-- 3. Concerned Entity Header Banner -->`) below the tabs that cluttered the UI.
     - The active tab in the dynamic tabs bar is prominently highlighted in KPMG Blue (`bg-kpmg-blue text-white shadow-xs ring-2 ring-kpmg-blue/20`) with entity name, role (`Parent` / `Subsidiary`), currency, and review status indicator, maximizing vertical screen real estate for the financial ledger table.
  5. **Verification & Hardening**:
     - Automated Test Suite: **86/86 PASSED (100%)** in 27.09s (including `test_multi_entity_ingestion_and_strict_entity_partitioning` and `test_pipeline_data_auto_heals_missing_mapping_metadata`).
     - JavaScript syntax check: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Live server: Verified running and responding with HTTP 200 on port 8000.
     - Git: Staged and pushed to remote branch `feature/profile-v2`.

### [2026-11-26 19:05] Milestone: Step 2 Dynamic Entity Mapping Tabs, Required Columns, Level 0 Searchable Dropdowns & HITL Review Gating
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Dynamic Multi-Entity Tabs (Parent + N Subsidiaries)**:
     - Replaced the single flat table in Step 2 with dynamic entity tabs: exactly 1 tab for the Parent company + 1 tab for each Subsidiary (e.g. 4 tabs for Parent + 3 subs, 8 tabs for Parent + 7 subs).
     - Clicking an entity tab smoothly transitions the view, displaying the concerned entity's header banner on top (Entity Name, Entity Code, Input Currency, Total Line Items, and Pending Review Count).
  2. **Standardized High-Density Financial Ledger Grid**:
     - Strict 7-column layout:
       `Account Code` | `Account Name` | `Currency` | `Amount` | `Level 0 Mapping` | `Confidence` | `Status`
     - Populated directly from the respective entity's primary trial balance and standardized Group Chart of Accounts.
  3. **Searchable Level 0 Dropdowns with Real-Time Filtering**:
     - Every row in the table provides an interactive Level 0 dropdown button displaying `Code - L0 Account Name`.
     - Clicking opens a viewport-anchored floating popover with instant real-time search filtering across code and description.
     - Selecting an option immediately invokes `/api/hitl/resolve`, commits the mapping to Learning Memory, updates confidence to 100%, turns the row from yellow to green, updates the pending review counter, and evaluates Step 3 gating.
  4. **Strict Human-in-the-Loop Yellow Highlight & Gating**:
     - Any account requiring review (confidence below threshold or unmapped) is highlighted in yellow (`bg-amber-50/80 border-amber-200 text-amber-950`).
     - The top-right toolbar action button is renamed to **"Consolidate"** across all 6 steps in the exact same position, shape, and size.
     - In Step 2, the **"Consolidate"** button and Step 3 in the stepper navigation bar remain locked/disabled until all reviews across all tabs are closed.
     - As soon as 0 reviews remain, the button enables and clicking it cleanly advances to Step 3 and runs the consolidation pipeline.
  5. **Auto-Triggering Mapping on Ingestion Approval**:
     - Extended `/api/pipeline/confirm-ingestion` to auto-trigger the COA mapping engine upon Step 1 confirmation, ensuring Step 2 tabs are immediately pre-populated upon navigation.
     - Added `/api/pipeline/run-mapping` endpoint for on-demand mapping execution.
     - Removed the 50-item truncation cap in `/api/pipeline-data` and returned complete multi-entity mapping decisions along with `level_0_choices`.
  6. **Verification & Hardening**:
     - Test Suite: **84/84 PASSED (100%)** in 23.38s across all unit and API test suites.
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Git: Staged and pushed to remote branch `feature/profile-v2`.

### [2026-11-26 18:20] Milestone: Action Button Streamlining & Global Header Cleanup
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Removed Global `+ New Run` from Stepper Header**:
     - Removed the redundant `+ New Run` button in `fs_conso/web/templates/index.html` adjacent to Step 6 Statements that was persistently visible on every consolidation step.
  2. **Streamlined Ingestion Action Toolbar**:
     - Removed obsolete `Refresh` button.
     - Transformed `Review Mappings` from a bulky button to the exact same ghost icon button style as Upload and Delete (`w-8 h-8 rounded text-slate-500 hover:text-kpmg-blue hover:bg-slate-100`).
     - Standardized toolbar sequence strictly as:
       `[Upload (Ghost)]` → `[Review Mappings (Ghost)]` → `[Reset/Delete (Ghost)]` → `[Run Consolidation (Primary)]`.
  3. **Verification & Hardening**:
     - Test Suite: **80/80 PASSED (100%)** in 19.11s.
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Git: Staged and pushed to remote branch `feature/profile-v2`.



### [2026-11-26 18:05] Milestone: Ingestion Review V3 (3-View Architecture, Adaptive 50-Row Sampling & Viewport-Anchored Tooltips)
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **3-View Segmented Architecture**:
     - Completely replaced the cluttered mixed-table and top strip layout with a 3-tab segmented architecture in `#modal-perimeter-approval`:
       • **🏢 Perimeter Entities View**: Dedicated high-density table for Parent and Subsidiaries with ~36px row height and tabular numeric formatting.
       • **💱 Foreign Exchange View**: Dedicated FX rates table with closing, average, and swap rate mappings.
       • **📄 Ignored Extra Sheets View**: Full-width dedicated table displaying all non-perimeter sheets with their exclusion context.
     - Smooth Emil Kowalski tab transition physics with real-time status counters on each tab pill.
  2. **Viewport-Anchored Tooltip Geometry**:
     - Solved the CSS containing-block transform bug by anchoring `#approval-floating-tooltip` directly to `document.body` instead of inside `.modal-dialog-card`.
     - Computed dynamic viewport coordinates (`rect.right + 10`, `rect.top - 8`) with bottom-screen boundary flipping, ensuring diagnostic cards appear right adjacent to the hovered status icon without clipping or drift.
  3. **Standardized Rightmost Action Column Sequence**:
     - Moved inline upload icon away from `Assigned File` to the far right.
     - Enforced strict sequence: `[Confidence %]` → `[View (👁)]` → `[Upload (Ghost)]`.
  4. **Column Terminology & Dual-Column Auto-Fill**:
     - Renamed table headers to clean standard **`Debit`** and **`Credit`**.
     - In `file_classifier.py` and `app.js`, single-column net amount sheets automatically populate both `debit` and `credit` columns with the detected amount column.
     - If either remains unselected, both are highlighted with red outlines.
  5. **Authentic KPMG Brand Button & Tactile Field Shake**:
     - Restored solid KPMG Royal Blue (`#00338D` / `bg-kpmg-blue hover:bg-kpmg-navy text-white`) for the `Approve & Confirm Ingestion` button without washed-out `opacity-60`.
     - Clicking with unfilled required fields fires a tactile CSS shake animation on all red unfilled cells and shows an informative toast alert without freezing or disabling the button.
  6. **Adaptive Sampling Privilege (50-Row Ceiling)**:
     - Expanded `_inspect_sheet_preview` and `_detect_columns_from_sample` in `file_classifier.py` to scan up to 20 rows for deep header detection with a user-authorized upper limit of 50 rows for ambiguous/complex sheets.
  7. **Verification & Hardening**:
     - Test Suite: **80/80 PASSED (100%)** in 19.59s.
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Git: Staged and pushed to remote branch `feature/profile-v2`.



### [2026-11-26 17:20] Milestone: Red Cell Highlighting, Shake Animation, Inline Row Upload & Overflow-Proof Tooltips
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Red Cell Highlighting & Dynamic Shake Validation**:
     - Added dynamic validation for required mapping dropdowns (`Assigned File`, `Worksheet`, `Account Code Col`, `Debit / Net Col`, and FX closing/average rates).
     - Any unfilled required select is immediately highlighted with a vivid red outline (`border-rose-600 ring-2 ring-rose-200 bg-rose-50/20 text-rose-800`).
     - As the user selects or maps a valid value, the red outline disappears instantaneously.
     - If the user attempts to confirm with unfilled required fields, a tactile shake animation (`animate-field-shake`) shakes the unfilled dropdowns, disables confirmation, and alerts the user.
  2. **Row-Level Re-Upload Action with Single-File Enforcement**:
     - Provided a clean ghost upload icon (without borders or background) beside each entity's `Assigned File` dropdown.
     - Enforces exactly 1 file selection, uploads via `/api/pipeline/single-entity-upload`, re-evaluates deterministic/AI classification, automatically updates sheet and column mappings in place, and preserves the open review modal.
     - Any still-missing columns remain clearly highlighted in red.
  3. **Overflow-Proof Floating Tooltips**:
     - Eliminated table overflow clipping by migrating tooltips from relative children inside scrollable table cells to a global fixed floating popper (`#approval-floating-tooltip`).
     - Calculates viewport bounds (`getBoundingClientRect()`) to dynamically prevent off-screen or cropped text. All period alerts, mapped sheets, columns, and scales are 100% visible and crystal-clear.
  4. **Tactile Status Icon Micro-Animation**:
     - Added smooth Emil Kowalski spring micro-interaction on hover over status ticks and crosses (`transform: scale(1.25) rotate(6deg); box-shadow: 0 4px 12px rgba(0,0,0,0.15)`).
  5. **Top KPI Strip Relocation for Ignored Sheets**:
     - Replaced the bulky bottom drawer with an `Ignored Extra Sheets (n)` action button inside the top KPI strip, expanding a neat top banner tray when clicked.
  6. **Verification & Hardening**:
     - Test Suite: **80/80 PASSED (100%)** in 8.48s.
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Git: Committed and pushed to `feature/profile-v2`.


### [2026-11-26 17:00] Milestone: High-Density Financial Ledger Grid for Ingestion Review Modal (Option 1)
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Option 1 Implementation (High-Density Financial Ledger Grid)**:
     - Replaced the tall, vertically stacked perimeter approval cards in `#modal-perimeter-approval` with an institutional, high-density financial table (~36px row height) matching the Company Profile and Audit Runs tables.
     - Scales smoothly from small groups to 100+ subsidiary perimeters without endless vertical scrolling.
     - Sticky header with 9 structured columns: `Status`, `Entity & Role`, `Assigned File`, `Worksheet`, `Account Code Col`, `Debit / Net Col`, `Credit Col`, `Scale / Denom`, and `View`.
  2. **Minimal Surface Clutter with Rich Diagnostic Hover Tooltips**:
     - Surface displays crisp status icons (Green ✓ for Ready, Red ✕ for Date Mismatch or Missing File, Amber ⚠️ for Review Mapping).
     - Hovering on any status indicator activates a KPMG Obsidian-lacquer (`#0B0F17`) floating card with structured diagnostic bullets:
       • Period alignment / discrepancy details (`File has FY 2024-25 vs Cutoff 31-03-2024`).
       • File & worksheet assignments.
       • Scale normalization multiplier.
       • Column mappings (Code, Debit, Credit).
       • Engine confidence score and classification method.
  3. **Real-Time KPI Strip, Filter Tabs & Fast Search**:
     - Summary bar displays live perimeter counts: `4/4 Entities Mapped`, `1 Flagged`, and `FX Ready/Missing`.
     - Instant filter tabs: `All`, `Flagged`, and `Ready`.
     - Instant search box filtering entities by name or code without resetting dropdown states or selections.
  4. **Preserved Micro-Drawer Preview & FX Table Row**:
     - Preserved collapsible preview drawer rows (toggled via eye icon `👁`) showing raw extracted 5 sample rows and scale multipliers.
     - Dedicated Foreign Exchange Rates row with purple/indigo styling and explicit closing, average, and swap rate dropdowns (`col-fx-closing`, `col-fx-average`, `col-fx-swap`).
     - Preserved ignored/extra sheets tray at the bottom for unassigned sheets (e.g. `Acquisition`).
     - Preserved all critical DOM IDs required by `confirmPerimeterApprovalModal`.
  5. **Verification & Hardening**:
     - Test Suite: **80/80 PASSED (100%)** in 9.14s.
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited 0.
     - CSS: Added `.dense-fin-table` rules with tabular numeric figures and proper vertical alignment.
     - Modal container expanded to `max-w-6xl` for seamless horizontal spacing.


### [2026-11-26 16:20] Milestone: Strict Fiscal Year Date Discrepancy Gate, Multi-Sheet Precedence & Review Mappings Action
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Fiscal Year Date Discrepancy Gate**:
     - Upgraded `_evaluate_date_discrepancy` with accounting financial year logic: `FY 2024-25` corresponds to period ending 31-Mar-2025; `FY 2025-26` to 31-Mar-2026; `FY 2023-24` to 31-Mar-2024.
     - When consolidation run cutoff date is `31-03-2024` and the uploaded file only contains data for 2025 / 2026, the engine flags a strict **`date_status = "MISMATCH"`**, reduces confidence to 0.40, and sets `needs_review = True`.
     - In `confirm_ingestion` (`app.py`), added backend validation rejecting column overrides covering an incompatible fiscal year with HTTP 400.
     - In `confirmPerimeterApprovalModal` (`app.js`), blocked confirmation when date mismatches exist, displaying an error toast and card alert banner.
  2. **Multi-Sheet Entity Matching Precedence**:
     - Prioritized sheet-level matching (`sname_lower`) over filename matching (`fname_lower`) in multi-sheet workbooks.
     - Automatically routes `Parent TB` $\rightarrow$ `C2`, `Sub A TB` $\rightarrow$ `A`, `Sub B TB` $\rightarrow$ `B`, `Sub C TB` $\rightarrow$ `C`, `Exchange Rate` $\rightarrow$ `FX_RATES`, and `Acquisition` $\rightarrow$ `UNKNOWN` (unassigned extra).
  3. **Dedicated "Review Mappings" Action Button**:
     - Added a tactile **"Review Mappings"** button in the Step 1 top action toolbar.
     - Allows users to re-open the Ingestion Review / Perimeter Mappings dialog at any time to inspect sheet assignments, sample rows, detected columns, and scale multipliers.
  4. **Verification & Hardening**:
     - Test Suite: **80/80 PASSED (100%)** (including new `test_client2_date_mismatch_and_entity_mapping`).
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited 0.
     - Live server operational on port 8000.

### [2026-11-26 15:50] UI Polish & Population: Row-Level Status Ticks, Banner Elimination & Debit/Credit Parsing
- **Branch**: `feature/profile-v2`
- **Resolution Applied**:
  1. **Elimination of Readiness Banner**:
     - Removed the full-width `"Perimeter Ingestion Complete: All 4 legal entities have valid ingested trial balances..."` banner from the Step 1 view for visual cleanliness and institutional aesthetics.
  2. **Row-Level Status Indicator Ticks with Diagnostic Hover**:
     - Added status indicator circles positioned to the left of the entity name and code:
       - **Green Tick (`✓`)**: Displays when trial balance is uploaded, non-empty, and balanced. Tooltip details total accounts, debits, and credits.
       - **Red Cross (`✕`)**: Displays when there are issues or doubts (missing TB, zero accounts, unparsed amounts, or debit/credit imbalance). Hovering shows bulleted diagnostics (`• Missing Trial Balance`, `• Amounts unpopulated`, `• Unbalanced Trial Balance: Debits != Credits`).
     - Added matching green/red indicator for Foreign Exchange Rates row.
  3. **Debit & Credit Balances Dynamic Population**:
     - Resolved root cause where annual/period columns (e.g. `FY 2024-25 (Lakhs)`) in single signed amount sheets resulted in `0.00` debits and credits.
     - Enhanced `FileClassifier` to score and detect period amount columns matching the active run date or sample numbers.
     - Enhanced `FlexibleTBParser` to split signed single amount columns into debits (positive values) and credits (negative values as positive), normalized to absolute currency using the scale multiplier.
  4. **Verification & Hardening**:
     - Test Suite: 79/79 PASSED (including new test `test_annual_column_detection_and_debit_credit_population`).
     - JavaScript syntax: `node -c "fs_conso/web/static/js/app.js"` exited with 0 errors.
     - Live server: Verified operational on port 8000.

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

### [2026-11-27] - Milestone: Remove Bottom-Right Pop-up Notifications
- **UI & UX Refinement**:
  - Removed bottom-right toast pop-up container (`#toast-container`) from `index.html`.
  - Added `#toast-container { display: none !important; }` in `style.css`.
  - Disabled `showToast()` in `app.js` into a clean no-op so no pop-up notifications appear in the bottom right, while allowing callers to execute harmlessly without errors.
- **Verification & Testing**:
  - Full test suite: **98/98 tests PASSED** in 20.17s.
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.

### [2026-11-27] - Milestone: Step 3 Dynamic Entity Tabs, 5-Category Ind AS 21 FX Translation Engine & Stepper Polish
- **Architectural & UI Enhancements**:
  - **Stepper Visual Washout Restoration**:
    - Fixed CSS specificity bug in `style.css` where `.step-tab:hover:not(.locked)` overrode `.step-tab.active`, eliminating white-on-white text washout.
    - Enforced unbreakable KPMG Royal Blue (`#00338D`) with bold white text on active steps, clear green checkmarks on completed steps, and crisp dark typography on inactive steps.
  - **HITL Review Counter Synchronization**:
    - Unified single source of truth between backend `state.hitl_pending_reviews` (including `entity_code`) and frontend `pipelineData.mapping_decisions`.
    - Counter accurately reflects total pending reviews across all perimeter entities, decrements strictly by 1 upon each individual approval ($N \to N-1 \dots \to 0$), and disappears cleanly at 0.
    - Synchronized per-entity tab dots (`step2-tab-dot-${entity_code}`) with exact per-entity counts.
  - **Step 3 Title & Dynamic Entity Tabs**:
    - Cleaned Step 3 heading from "Foreign Currency Translation (Ind AS 21)" to "Foreign Currency Translation".
    - Restructured Step 3 using Dynamic Entity Tabs ($N$ tabs: 1 Parent + 1 for each Subsidiary), eliminating vertical stacking and scaling seamlessly to 100+ entities.
  - **5-Category FX Translation Engine & Rate Application**:
    - In `FXTranslationEngine`, categorized all Level 0 items into the 5 core accounting categories: `Asset`, `Liability`, `Equity`, `Income`, `Expense`.
    - Applied exact Ind AS 21 translation rules from ingested Step 1 rates:
      - `Asset` & `Liability` &rarr; Closing Rate (`CLOSING`)
      - `Income` & `Expense` &rarr; Average Rate (`AVERAGE`)
      - `Equity` &rarr; Historical Rate (`HISTORICAL`)
      - Functional currency == Reporting currency &rarr; `1.0000 (Identity)`
    - Dynamically resolved true functional currency per entity (`USD`, `EUR`, `INR`) rather than hardcoding INR.
  - **FCTR Reserve Balancing Plug & Full Row Display**:
    - Calculated exact FCTR balancing plug row (`O620102`) bringing net translated balance strictly to `0.00`.
    - Prominently styled FCTR plug row in amber frosted glass with gold accent badge.
    - Removed 15-row truncation in `/api/pipeline-data`; returns all rows with full search filter capability.
- **Verification & Testing**:
  - Added `tests/test_step3_translation_tabs.py`: verifies 5-category classification, Closing/Average/Historical rate routing, FCTR plug math, and API serialization.
  - Full test suite: **98/98 tests PASSED** in 26.36s (100% pass rate).
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.

- **Architectural & UI Enhancements**:
  - **Modal Polish & Anti-Clutter**:
    - Renamed modal header from "Review Ingestion & Perimeter Mappings" to "Review Ingestion Mappings".
    - Removed extraneous "Dual-Engine Classification" badge and top parameter alignment blue banner.
    - Simplified card header: removed "Deterministic" / "AI Agent" boxes; replaced with tactile eye preview button (`👁`) and clean percentage text (e.g. `92%`, `96%`).
    - FX Rates Table card: removed "Identified" badge; unified with eye preview button and percentage text.
  - **Comprehensive Dropdown Prefilling**:
    - `Assigned File`: prefilled with detected workbook/file.
    - `Worksheet`: prefilled with detected worksheet name.
    - `Account Code Col`: prefilled with detected account code column name.
    - `Debit Col` & `Credit Col`: split into separate prefilled dropdowns.
    - `FX Rates Table`: prefilled with closing rate, average rate, and swap rate columns.
    - Resilient sample scanning across rows 0-5 to identify true header rows even with preamble banners.
  - **Denomination & Currency Scale Normalization (Lakhs, Crores, Millions, Thousands)**:
    - Added `_detect_denomination()` in `FileClassifier`: detects scale from preambles, titles, and headers (Lakhs $\times 10^5$, Crores $\times 10^7$, Millions $\times 10^6$, Thousands $\times 10^3$, Hundreds $\times 10^2$, Units $\times 1$).
    - Added scale selector (`Units`, `₹ Lakhs`, `₹ Crores`, `Millions`, `Thousands`, `Hundreds`) and dynamic instruction banner (`💡 Scale Normalization: Reported in ₹ Lakhs — multiplying by 100,000 to normalize to absolute currency`) on each entity card.
    - Updated `FlexibleTBParser` (`parse_dataframe`, `parse_file`, `_unpivot_wide_matrix`): automatically scales all debit, credit, and balance amounts by `scale_multiplier` so that all stored and displayed numbers are in absolute currency.
- **Verification & Testing**:
  - `tests/test_step1_dual_engine_ingestion.py`: Added `test_denomination_detection_and_scale_multiplication` and `test_perimeter_approval_state_prefill_and_scale`. All 7/7 tests PASSED.
  - Full project test suite: 78/78 tests PASSED (100% pass rate).
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Live API verification on `http://127.0.0.1:8000/api/status`: HTTP 200 OK.

---

### [2026-11-27] Step 5: Goodwill on Consolidation (Ind AS 103 / IFRS 3) Implementation

- **Architectural & Stepper Progression**:
  - Introduced dedicated **Step 5: Goodwill** between Step 4 (Eliminations) and Step 6 (Consolidation), expanding primary pipeline stepper to 7 distinct steps:
    - Step 1: Ingestion
    - Step 2: Mapping
    - Step 3: Translation
    - Step 4: Eliminations
    - Step 5: **Goodwill** (NEW)
    - Step 6: Consolidation (previously Step 5)
    - Step 7: Financial Statements (previously Step 6)
  - Updated `switchStep` gating in `app.js` to enforce prerequisites across all 7 steps.

- **Goodwill Calculation Engine & Models**:
  - `fs_conso/models/goodwill.py`: Created `GoodwillSchedule`, `GoodwillEntityData`, `GoodwillAdjustmentItem`.
  - `fs_conso/core/goodwill_engine.py`:
    - `calculate_share_capital_from_l0`: Sums mapped trial balance line items for any selected Level 0 code for that entity, translated to reporting currency using Ind AS 21 historical rules.
    - `search_investment_account`: Deterministic keyword search + Gemini LLM fallback + interactive HITL routing.
    - `recalculate_schedule`: Real-time reactive calculation:
      - $\text{Net Assets} = \text{Share Capital} + \sum\text{Adjustments} + \text{Retained Earnings}$
      - $\text{Diff} = \text{Investment} - \text{Net Assets}$
      - $\text{Goodwill} = \max(0, \text{Diff})$
      - $\text{Capital Reserve} = \max(0, -\text{Diff})$
    - Applied identical formula across Parent and all subsidiary columns.

- **Backend API Endpoints (`fs_conso/web/app.py`)**:
  - `GET /api/pipeline/goodwill`: Returns schedule, entity data, parent TB investment candidates, and Level 0 options.
  - `POST /api/pipeline/goodwill/update`: Updates selected Level 0 codes, manual adjustments, retained earnings, investments, and remarks.
  - `POST /api/pipeline/goodwill/add-adjustment`: Adds dynamic adjustment rows (capped at 100 rows).
  - `POST /api/pipeline/goodwill/delete-adjustment`: Removes dynamic adjustment rows.
  - `POST /api/pipeline/goodwill/confirm`: Confirms Step 5, triggers Consolidated TB aggregation with Goodwill/Reserves integrated, and advances to Step 6.

- **Consolidated Trial Balance Integration (`fs_conso/core/aggregator.py`)**:
  - Posts aggregate Goodwill to Asset `A110301` ("Goodwill on Consolidation").
  - Posts aggregate Capital Reserve to Equity `E210103` ("Capital Reserve on Consolidation").
  - Records entity acquisition accounting details in `AcquisitionAccountingResult`.

- **Frontend Luxury Matrix UI (`fs_conso/web/static/js/app.js` & `index.html`)**:
  - Header: `Particulars` | `[Parent Company]` | `[Sub 1]` | `[Sub 2]` ... | `Remarks`.
  - Floating Level 0 popover with instant search to select Share Capital mapping.
  - Tactile `+` button to add up to 100 dynamic adjustment rows with delete buttons and remarks.
  - Retained earnings input per entity with remarks writing capability.
  - Investment by company with auto-matched accounts, inline dropdown selector, and editable amount input.
  - Monospace tabular figures with instant client-side calculation and formula tooltips.
  - Responsive KPI badges for Total Goodwill and Total Capital Reserve.

- **Verification & Testing**:
  - `tests/test_goodwill_engine.py`: 6/6 tests PASSED (Share Capital from L0, positive Goodwill, bargain purchase Capital Reserve, deterministic investment matching, Consolidated TB posting, API lifecycle).
  - Full project test suite: 106 passed, 1 skipped, 0 failed (100% pass rate).
  - Node.js syntax audit: `node -c "fs_conso/web/static/js/app.js"`: EXIT 0.
  - Live server verification on `http://127.0.0.1:8000`: HTTP 200 OK.








