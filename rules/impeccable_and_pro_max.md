# Impeccable & UI/UX Pro Max Design System Tokens

Guidelines combining Paul Bakaus's Impeccable design patterns and UI/UX Pro Max tokens.

## 1. Token Scale & Theme Hierarchy
- **Primary Corporate Palette (KPMG Institutional)**:
  - `brand-navy`: `#001D48` (Primary dark background, navigation, high emphasis)
  - `brand-kpmg-blue`: `#00338D` (Signature brand accent, active state, primary buttons)
  - `brand-electric`: `#0091DA` (Secondary accent, highlighted active steps, focus borders)
  - `neutral-bg`: `#F4F5F7` (Clean financial workspace canvas)
  - `neutral-surface`: `#FFFFFF` (Data tables, cards, dialogs)
  - `neutral-border`: `#E2E8F0` (Crisp separation, 1px borders)
  - `neutral-text-main`: `#0F172A` (Headings, primary figures)
  - `neutral-text-muted`: `#64748B` (Secondary descriptions, column labels)
  - `status-success`: `#10B981` (Balanced TB, reconciled entries)
  - `status-warning`: `#F59E0B` (Within-tolerance IC variances)
  - `status-error`: `#EF4444` (Unbalanced TB, blocking errors)

## 2. Accessibility & Contrast Verification
- All text meets **WCAG AA** standards:
  - Main text contrast ratio >= `7:1`.
  - Muted labels contrast ratio >= `4.5:1`.
  - Large display metrics >= `3:1`.
- Buttons always maintain clear contrast against background (never white text on light gray or transparent buttons without borders).

## 3. UI/UX Pro Max Layout Rules
- **Predictable Natural Flow**:
  - The interface follows a left-to-right, top-to-bottom progression:
    1. Header Bar: Brand mark, current consolidation period, mandatory API Key indicator, Settings Drawer trigger.
    2. Primary Stepper: 6 sequential steps, locked ahead of current progress.
    3. Contextual Sub-bar: Displays micro-actions specific to the active step.
    4. Active Workspace: Dense, high-legibility financial table or reconciliation matrix.
    5. Bottom Action Bar: Contextual primary action ("Validate & Advance", "Recalculate", "Export").
- **No Empty State Dead Ends**:
  - Every empty state clearly states what data is required and provides an immediate one-click action to load baseline data or upload a file.
