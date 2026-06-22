# Accessibility Reference

## WCAG 2.1 Overview

### Four Principles (POUR)
1. **Perceivable** — Users must be able to perceive the content (not invisible to all senses)
2. **Operable** — Users must be able to operate the interface (not require interaction they can't perform)
3. **Understandable** — Users must be able to understand the content and operation
4. **Robust** — Content must be interpretable by assistive technologies

### Conformance Levels
- **Level A** (minimum): essential accessibility features
- **Level AA** (standard): removes major barriers — target for most products
- **Level AAA** (enhanced): highest level — not required for all content

## Key WCAG Success Criteria

### Perceivable

#### 1.1.1 Non-text Content (A)
- All non-text content must have text alternative
- Images: alt text, aria-label, or role="presentation" for decorative
- Icons: aria-label or hidden text
- Charts: data table or summary

#### 1.4.1 Use of Color (A)
- Color is NOT the only way to convey information
- Error states: icon + text + color (not just red)
- Links: underline + color (not just color)

#### 1.4.3 Contrast (AA) — Minimum
- Text: 4.5:1 for normal text, 3:1 for large text (≥18px or ≥14px bold)
- UI components: 3:1 for visual state boundaries

#### 1.4.11 Non-text Contrast (AA)
- UI components and graphical objects: 3:1 minimum contrast ratio
- Includes: form field borders, focus indicators, icons, chart colors

#### 1.4.12 Text Spacing (AA)
- No loss of content when user overrides:
  - Line height: 1.5× font size
  - Paragraph spacing: 2× font size
  - Letter spacing: 0.12× font size
  - Word spacing: 0.16× font size

### Operable

#### 2.1.1 Keyboard (A)
- All functionality operable through keyboard interface
- No keyboard traps (can navigate in and out of all components)
- Tab order follows visual order

#### 2.4.3 Focus Order (A)
- Focusable components receive focus in meaningful sequence
- Logical reading order = logical focus order

#### 2.4.7 Focus Visible (AA)
- Keyboard focus indicator must be visible
- Minimum: 2px outline with 3:1 contrast against adjacent colors
- Never: outline: none without providing visible focus style

#### 2.5.5 Target Size (AAA)
- Touch targets: minimum 44×44 CSS pixels
- Exceptions: inline links, browser default controls

### Understandable

#### 3.2.1 On Focus (A)
- Changing focus does not initiate context change
- No automatic page refresh, navigation, or submission on focus

#### 3.3.1 Error Identification (A)
- Automatically detect input errors and describe to user
- Clear error message: what went wrong and how to fix it

#### 3.3.2 Labels or Instructions (A)
- Labels or instructions provided when user input required
- Placeholder text is NOT a substitute for labels

#### 3.3.3 Error Suggestion (AA)
- Suggestions provided for correcting input errors

## ARIA Landmarks

### Landmark Roles
```html
<header role="banner">      <!-- Site-level header -->
<nav role="navigation">      <!-- Navigation blocks -->
<main role="main">           <!-- Primary content -->
<aside role="complementary"> <!-- Supporting content -->
<footer role="contentinfo">  <!-- Site-level footer -->
<form role="search">         <!-- Search form -->
<section>                    <!-- Thematic grouping -->
```

### ARIA Best Practices
- Use native HTML semantics first, add ARIA only when semantics insufficient
- Don't override native semantics (e.g., don't add role="button" to a <button>)
- Use aria-live="polite" for dynamic content updates
- Use aria-atomic="true" for self-contained announcements
- Use aria-describedby for additional descriptions

## Focus Management

### Focus Indicators
- Default browser outline is insufficient — provide custom focus styles
- Focus ring: 2-3px solid outline with 2-4px offset
- High contrast: ensure focus ring visible on all backgrounds
- Never: remove focus outlines without providing accessible alternative

### Focus Order Patterns
- Modals: trap focus within modal, restore to trigger on close
- Flyout menus: focus first item on open, return to trigger on close
- Tab panels: focus the tab, not the panel content initially
- Dynamic content: move focus to new content or provide announcement

## Screen Reader Considerations

### Headings
- Use hierarchical heading structure (h1 → h2 → h3 — never skip levels)
- One h1 per page describing the page purpose
- Headings should be descriptive, not generic ("Pricing" not "Section 1")

### Images
- Informative: describe the message in alt text
- Decorative: alt="" (empty) or role="presentation"
- Complex (charts/diagrams): alt text summary + nearby data table
- Functional (linked image): describe the link destination, not the image

### Forms
- Every input must have an associated label
- Required fields: aria-required="true" or visual indicator + screen reader text
- Error messages: aria-describedby linking to error text
- Autocomplete attributes for common fields (name, email, address)

## Testing Checklist

### Automated Testing
- [ ] Color contrast ratios meet WCAG AA
- [ ] All images have alt text
- [ ] ARIA attributes are valid
- [ ] Heading structure is hierarchical
- [ ] Form inputs have associated labels
- [ ] No empty links or buttons

### Manual Testing
- [ ] Full keyboard navigation works
- [ ] Focus order follows visual order
- [ ] Focus indicator visible on all interactive elements
- [ ] Screen reader announces all content correctly
- [ ] Tab through all interactive elements
- [ ] Test with zoom (200%) — no content loss
- [ ] Test with forced colors mode (Windows High Contrast)

### Assistive Technology Testing
- [ ] VoiceOver (macOS/iOS)
- [ ] NVDA (Windows)
- [ ] TalkBack (Android)
- [ ] Switch control / voice control
