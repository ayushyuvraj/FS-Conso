# Emil Kowalski UI Craft & Micro-Interaction Directives

Inspired by Emil Kowalski's principles of interface craftsmanship, animation physics, and interaction delight.

## 1. Morph-Like Layout Stability
- **No Text Drift**:
  - When switching between tabs, steps, or views, stationary elements (navigation headers, step indicators, search bars, primary buttons) must NOT jump by even 1 pixel.
  - Standardized widths and heights for containers (`h-10`, `h-12`, fixed button dimensions).
- **No Coordinate Jumping**:
  - Use stable layout containers (`grid` or CSS layout geometry) rather than variable flex calculations that reflow abruptly.
  - Loading states and populated states share identical dimensions so the UI transitions smoothly without content popping.

## 2. Micro-Interactions & Spring Physics
- **Spring Curves over Linear Easing**:
  - Transitions use natural physics: `cubic-bezier(0.16, 1, 0.3, 1)` or spring stiffness/damping.
  - No sluggish linear animations.
- **Tactile Feedback on Interaction**:
  - Buttons depress slightly on `:active` (`transform: scale(0.98)` or `translate-y-[1px]`).
  - Hover states provide instant, subtle brightness/contrast feedback (`bg-opacity-90` or `border-blue-400`).
- **Focus Rings**:
  - High-contrast, clean 2px focus ring with 2px offset (`ring-2 ring-blue-600 ring-offset-2`).

## 3. Delight in Functionality
- **Data States**:
  - Clean visual indicators when a cell recalculates or updates.
  - Status badges with subtle dot indicators (Green pulse for balanced TB, Amber for within-tolerance variance, Red for out-of-tolerance exception).
- **Tooltips & Formula Previews**:
  - Hovering over any calculated figure reveals an elegant floating pill showing its exact formula lineage without cluttering the screen.
