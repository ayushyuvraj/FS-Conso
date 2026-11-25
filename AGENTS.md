# Enterprise Frontend Design & Engineering Rules

This repository incorporates five core design and interaction skills installed in `.agent/skills/` (and `.agents/skills/`). All frontend, UI/UX, styling, and animation development must strictly adhere to their principles:

## 1. Emil Kowalski (`.agent/skills/emil-kowalski/SKILL.md`)
- **Animation Physics**: Use natural spring physics and custom easings (`cubic-bezier(0.16, 1, 0.3, 1)` or Apple-tier fluid spring curves). Never use generic `ease` or linear timers for interactive surfaces.
- **Micro-Interactions**: Active click scaling (`scale(0.97)` / `scale(0.98)`), tactile spring responses on buttons and toggles.
- **Frequency Rule**: Never animate frequent keyboard actions (e.g., `Ctrl+B`, command palette). Animate state changes, toasts, modals, and spatial transitions with clear directional intent.

## 2. Impeccable (`.agent/skills/impeccable/SKILL.md`)
- **Visual Hierarchy & Craft**: Out-of-distribution design craft. No cookie-cutter templates or timid designs.
- **Luxury Color Harmony**:
  - Primary Corporate: KPMG Royal Navy (`#001D48`), KPMG Blue (`#00338D`), KPMG Electric (`#0091DA`).
  - High-Finance Accents: Neo Kinpaku Gold (`#D4AF37`, `rgba(212, 175, 55, 0.2)`), Verdigris Patina (`#0D9488`).
  - Dark Surfaces: Obsidian Lacquer (`#0B0F17`, `#05070B`, `#111827`).
- **Surface Elevation**: Frosted glassmorphism (`backdrop-filter: blur(8px)`), subtle translucent white borders (`rgba(255, 255, 255, 0.1)`), and layered elevation shadows.

## 3. Taste (`.agent/skills/taste/SKILL.md`)
- **Anti-Slop Discipline**: Never generate generic AI tropes (purple gradients, generic centered hero cards, uniform rounded boxes, unstyled Inter text).
- **Typography & Restraint**: Strict editorial restraint, intentional font pairings, high contrast ratios, and deliberate breathing room.
- **Design Read**: Always assess the context (institutional high-finance consolidation portal for audit and executive finance leaders) before selecting component styles.

## 4. UI/UX Pro Max (`.agent/skills/ui-ux-pro-max/SKILL.md`)
- **Financial Data Density**: High-information density with tabular figures (`font-variant-numeric: tabular-nums; font-family: 'JetBrains Mono', monospace`).
- **Complex Financial Tables**: Sticky headers (`position: sticky; top: 0`), high-legibility zebra stripes, clear alignment (text left, numbers right, codes centered).
- **Accessible & Responsive**: WCAG AA color contrast (4.5:1 minimum), clear focus states, keyboard shortcuts, and responsive collapsed states.

## 5. Frontend Design by Anthropic (`.agent/skills/frontend-design/SKILL.md`)
- **Subject-Matter Grounding**: Interface design tailored specifically to multi-entity consolidation accounting, legal perimeter governance, and multi-agent observability.
- **Design Token Discipline**: Centralized CSS variables in `style.css` rather than scattered arbitrary inline styles.
- **Resilient Component Architecture**: Clear state management, robust DOM handling, zero console errors, and graceful degradations.

---

## 6. Autonomous Verification, Production Hardening & Git Checkpoint Rule (MANDATORY)

In every implementation task, the agent MUST autonomously execute exhaustive end-to-end verifications before completing the turn:
1. **Security**: Validate against formula injection (`=`, `@`, `+`, `-`), path traversal (`..`), XSS (`escapeHtml`), and sensitive credential/API key leakage.
2. **Robustness & Defensiveness**:
   - Case-insensitive lookups and slug tolerance for all identifiers, codes, and company names.
   - Comprehensive error handling: never return raw 500s or unhandled exceptions to the user.
   - Resilient date and number parsing supporting international formats, blank placeholders, and regional variations.
3. **Exhaustive Edge Cases**:
   - Zero, single, and high-volume subsidiaries (0, 1, 3, 50+ entities).
   - In-place renaming, casing alterations (e.g. `CLient_one` vs `client_one`), and code updates.
   - Preserving master structures (Base COA, FX tables, entity hierarchies) across partial edits.
4. **Deployment & Runtime Hardening**:
   - Detect and prevent stale server processes or locked ports (8000).
   - Ensure server auto-reloading (`reload=True` with WatchFiles) is active and running cleanly.
   - Verify all static assets and JavaScript functions parse and execute without console errors.
5. **Continuous Verification Ledger (`EVENTS.md`)**:
   - Record all production audits, edge case verifications, and architectural changes in `EVENTS.md`.
6. **Git Checkpoint & Push**:
   - Create clean, atomic commits for every milestone.
   - Push verified changes directly to the remote repository (`git push origin <branch>`).

---

## 7. Immutable Preservation Rule (MANDATORY)

Once a UX interaction, styling choice, button layout, or component behavior is established and verified, the agent MUST NEVER touch, rewrite, alter, or remove it in subsequent tasks unless the user explicitly requests that specific change.
1. **Zero Unsolicited Mutations**: Only change what is strictly required to fulfill the user's immediate request. Working, existing code and UI patterns are frozen.
2. **Design Continuity & Unification**: Always match established button sizes, typography scales, paddings, and interaction physics (e.g., standard action buttons, morphing brand toggles, navigation persistence).
3. **Strict Scope Discipline**: Never make unauthorized aesthetic or functional assumptions. If in doubt, ask before modifying working features.


