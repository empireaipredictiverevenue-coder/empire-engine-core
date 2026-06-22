# Interaction Patterns Reference

## Navigation Patterns

### Top Navigation (Header)
- Brand/logo on left, navigation items center or right
- Active page highlighted
- Responsive: collapse to hamburger menu on mobile
- Max 5-7 top-level navigation items
- Dropdown for nested pages (hover on desktop, tap on mobile)

### Sidebar Navigation
- Persistent navigation for complex applications
- Collapsible for space efficiency
- Icons + labels for scannability
- Section headers to group navigation items
- Nested items via expand/collapse accordion

### Tab Navigation
- For switching between related content views
- Active tab visually distinguished (underline, fill, or color)
- Content changes without page navigation
- Max 5-7 tabs before using overflow dropdown

### Breadcrumbs
- Secondary navigation showing current location
- Format: Home > Section > Subsection > Current Page
- Last item is current page (not linked)
- Truncate middle items on small screens with "…"

## Data Display Patterns

### Tables
- Sortable columns with sort direction indicator
- Row hover for legibility
- Selectable rows with checkbox or click
- Pagination or virtual scrolling for large datasets
- Responsive: horizontal scroll or card view on mobile
- Column resize and reorder for complex tables

### Lists
- Icon/avatar + title + description + metadata + action
- Sorting and filtering controls
- Pull-to-refresh on mobile
- Infinite scroll or pagination
- Empty state for zero results

### Data Cards
- Visual summary of a data entity
- Consistent sizing within a grid
- Hover state for interactivity cue
- Progressive disclosure: summary on card, detail on click

### Charts & Graphs
- Appropriate chart type: bar (comparison), line (trend), pie (composition), scatter (correlation)
- Direct labeling preferred over legends
- Interactive: hover for detail, click for drill-down
- Time series: zoom and pan for date ranges
- Colorblind-safe color palette

## Input Patterns

### Forms
- Single column for most forms (faster completion)
- Labels above inputs (best readability)
- Inline validation on blur (not on every keystroke)
- Submit button aligned left or full width
- Never disable submit button without explanation
- Show password toggle for password fields

### Search
- Search bar with magnifying glass icon
- Live results as user types (debounced, 300ms delay)
- Recent searches below input on focus
- Faceted search with filters for complex datasets
- Clear button within search field
- Voice search option for mobile

### Date Pickers
- Month/year navigation with arrow buttons
- Today highlighted
- Range selection: start and end date highlight
- Min/max date constraints
- Keyboard: Tab between month/day/year fields

### File Upload
- Drag and drop zone with click alternative
- File type and size limits shown
- Upload progress indicator
- Success/error state per file
- Preview for images
- Remove file option

## Feedback Patterns

### Toast Notifications
- Temporary, auto-dismiss (3-5 seconds)
- Types: success (green), error (red), warning (amber), info (blue)
- Position: top-right on desktop, top on mobile
- Stack: multiple toasts stacked vertically
- Dismiss button for persistent notifications

### Inline Validation
- Real-time validation on field blur
- Error below field in red with icon
- Success: green checkmark or subtle confirmation
- Character count for text fields with limits

### Modals & Dialogs
- Blocking action required (confirmation, form completion)
- Escape key to close
- Click outside to close (for informational dialogs only)
- Focus trap within modal
- Title + content + actions (primary/secondary buttons)
- Prevent background scroll when open

### Empty States
- Illustration or icon related to the context
- Friendly message explaining what should be here
- Clear call-to-action for next step
- Never show blank content area

## Motion & Animation

### Purpose of Motion
- **Functional** — communicate state changes, transitions, feedback
- **Spatial** — show relationships between elements and screens
- **Attention** — guide focus to important changes
- **Expressive** — reinforce brand personality

### Duration Guidelines
- Micro-interactions (button press, toggle): 100-200ms
- Element transitions (modal open, panel slide): 200-300ms
- Screen transitions (page change): 300-500ms
- Loading animations: continuous until complete
- Reduce motion: respect prefers-reduced-motion media query

### Easing Functions
- Ease-out (deceleration): elements entering screen — feels natural
- Ease-in (acceleration): elements leaving screen
- Ease-in-out: elements moving between positions
- Spring: playful, elastic feel — use for emphasis
- Linear: progress bars, loading indicators only

### Common Easing Values
```css
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);
--ease-in: cubic-bezier(0.4, 0, 1, 1);
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
```

### Gesture & Mobile Motion
- Swipe to dismiss: follow finger position, snap to open/closed
- Pull to refresh: resistance with spring release
- Long press: haptic feedback + contextual action
- Pinch to zoom: scale content smoothly

## Responsive & Adaptive

### Breakpoint Reference
```css
/* Mobile-first breakpoints */
sm:  640px   /* Large phones */
md:  768px   /* Tablets */
lg:  1024px  /* Small desktops / landscape tablets */
xl:  1280px  /* Standard desktops */
2xl: 1536px  /* Large desktops */
```

### Mobile Adaptations
- Single column layouts
- Bottom navigation bar (thumb zone)
- Full-width inputs and buttons
- Reduced data density (show less, load more)
- Touch-friendly targets (min 44×44px)
- Progressive enhancement instead of graceful degradation

### Content Priority
- Critical content first (above the fold on mobile)
- Progressive disclosure for secondary content
- Collapse: accordions, tabs, "show more" toggles
- Table → Card list on small screens
- Multi-column → Single column on small screens
