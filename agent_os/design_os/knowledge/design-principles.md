# Design Principles Reference

## Universal Design Principles

### Hierarchy
- Guide the eye from most to least important
- Use size, color, spacing, and position to establish visual weight
- Primary action should be visually dominant; secondary actions should be visually subdued
- Content hierarchy: title → subtitle → body → metadata → action
- 60-30-10 rule: 60% primary content, 30% secondary, 10% accent/highlight

### Balance
- Symmetrical: formal, stable, traditional
- Asymmetrical: dynamic, modern, engaging
- Radial: draws eye to center point (dials, radars, data hubs)
- Balance visual weight — not element count — across the composition
- White space (negative space) is an active design element, not empty waste

### Contrast
- Differentiate elements to create separation and focus
- Minimum 4.5:1 contrast for normal text (WCAG AA), 3:1 for large text
- Use contrast for: call-to-action, errors/alerts, data highlights, navigation state
- Don't rely on color alone for contrast — use size, weight, and shape too

### Repetition
- Reinforce branding by repeating visual elements consistently
- Establish patterns users can learn and predict
- Reuse components rather than designing unique solutions per screen
- Consistent spacing creates rhythm and predictability

### Proximity
- Group related elements together visually
- Elements close together are perceived as related
- Use spacing to create relationships: 8px / 16px / 24px / 32px increments
- Reduce cognitive load by organizing content into logical groups

### Alignment
- Every element should be visually connected to another element
- Grid systems provide the foundation for alignment
- Consistent alignment creates professionalism and readability
- Break alignment deliberately to create emphasis or surprise

## Platform-Specific Design Principles

### Web Design
- Responsive: design for mobile-first, scale up
- Navigation visible and predictable
- Links and buttons clearly distinguishable (underlined links, button shapes)
- Loading states for every async operation
- Scroll behavior should feel natural and performant

### Mobile Design
- Thumb zone: primary interactions within easy thumb reach (bottom third of screen)
- Gesture conventions: swipe, tap, long-press, pinch are recognized patterns
- Native feel: respect platform conventions (iOS vs Android)
- Reduce cognitive load: one primary action per screen
- Touch targets: minimum 44x44pt (48x48 recommended)

### Dashboard Design
- Information density: show data, not chrome
- Progressive disclosure: start with summary, allow drill-down
- Consistent widget layout and sizing
- Real-time data updating without visual disruption
- Print/export consideration for reports

## Design Process

### Double Diamond
1. **Discover** — Research, understand context, gather insights
2. **Define** — Synthesize, frame the problem, set constraints
3. **Develop** — Ideate, prototype, iterate solutions
4. **Deliver** — Refine, finalize, hand off for implementation

### Design Thinking
1. Empathize — Understand users and their needs
2. Define — Articulate the problem
3. Ideate — Generate solutions
4. Prototype — Build representations
5. Test — Validate with users

## Design Tokens Naming Convention

```css
/* Category → Concept → Property → Variant */
/* size.spacing.md */
/* color.background.primary */
/* typography.font-size.heading.lg */
/* shadow.elevation.low */

/* Example system */
--color-brand-primary: #2563EB;
--color-brand-secondary: #7C3AED;
--color-background-base: #FFFFFF;
--color-background-surface: #F8FAFC;
--color-text-primary: #0F172A;
--color-text-secondary: #475569;
--color-border-default: #E2E8F0;
--color-semantic-success: #10B981;
--color-semantic-warning: #F59E0B;
--color-semantic-error: #EF4444;
--size-spacing-xs: 4px;
--size-spacing-sm: 8px;
--size-spacing-md: 16px;
--size-spacing-lg: 24px;
--size-spacing-xl: 32px;
--typography-font-size-body: 16px;
--typography-font-size-h1: 32px;
--typography-font-size-h2: 24px;
--shadow-elevation-low: 0 1px 3px rgba(0,0,0,0.1);
--motion-duration-fast: 150ms;
--motion-duration-normal: 300ms;
```

## Common Design Patterns

### Empty States
- Illustration or icon + message + action CTA
- Never show a blank screen with no guidance
- Examples: no data, no results, first-time user, error state

### Error States
- Inline validation with clear error messages
- Field-level errors: red border + icon + message below field
- Form-level errors: banner at top with summary
- 404 pages: helpful redirect options, not dead ends

### Loading States
- Skeleton screens preferred over spinners for content-heavy areas
- Spinners for actions shorter than ~3 seconds
- Progress bars for operations longer than ~10 seconds
- Optimistic UI for low-risk operations (like, favorite, follow)

### Confirmation Dialogs
- Title + message + confirm/cancel buttons
- Destructive actions: red confirm button, clear warning message
- Don't use confirmation for undoable actions that have clear secondary consequences
