# Color Theory & Systems Reference

## Color Models

### HSL (Hue, Saturation, Lightness)
- **Hue**: position on color wheel (0-360°)
- **Saturation**: intensity of color (0-100%)
- **Lightness**: brightness of color (0-100%, where 50% is pure color)
- Preferred for UI design: intuitive adjustments and accessible color scales

### RGB (Red, Green, Blue)
- Additive color model for screens
- Each channel 0-255
- Common format: hex (#RRGGBB) or rgb(r, g, b)

## Color Wheel Relationships

### Complementary (180° apart)
- Maximum contrast, creates visual tension
- Use: highlights, CTAs, emphasis
- Example: blue (#2563EB) → orange (#EB9425)

### Analogous (30-60° apart)
- Harmonious, creates unified feel
- Use: backgrounds, gradients, brand families
- Example: blue → blue-green → green

### Triadic (120° apart)
- Balanced contrast, vibrant
- Use: multi-brand systems, data visualization
- Example: red → yellow → blue

### Split-Complementary
- Less tension than complementary but still high contrast
- Use: CTAs with sub-actions, data viz

## UI Color Roles

### Primary
- Brand color, used for main actions, key navigation elements
- 1-2 hues maximum
- Application: primary buttons, active states, links, main CTA

### Secondary
- Supporting brand color, used for secondary actions, accents
- Usually a neutral or complementary hue
- Application: secondary buttons, badges, selected states, category labels

### Neutral
- Grays for text, backgrounds, borders, dividers
- Typically 8-10 steps from white to black
- Application: body text, headings, backgrounds, cards, borders

### Semantic
- Communicate meaning at a glance
- **Success** (green): confirmations, completions, positive metrics
- **Warning** (amber/yellow): cautions, near-limits, pending states
- **Error** (red): failures, validation errors, destructive actions
- **Info** (blue): informational messages, system notices
- Rethink: each semantic color needs both foreground and background variants

## Accessibility

### Contrast Ratios
- **WCAG AA** (minimum):
  - Normal text: 4.5:1
  - Large text (≥18px or ≥14px bold): 3:1
  - UI components and graphical objects: 3:1
- **WCAG AAA** (enhanced):
  - Normal text: 7:1
  - Large text: 4.5:1

### Color Blindness Considerations
- ~8% of males and ~0.5% of females have some form of color vision deficiency
- **Deuteranopia** (green-blind): most common, ~6% of males
- **Protanopia** (red-blind): ~2% of males
- **Tritanopia** (blue-blind): rare
- Never rely on color alone to convey information
- Use: icons, text labels, patterns, shapes + color

### Accessible Color Scale Generation
- Keep lightness contrast between adjacent steps
- For text on background: minimum 4.5:1
- Lightness steps of 8-12% between scale levels
- Test with: contrast checkers, color blindness simulators

## Color Scale Generation

### Creating a Scale
1. Choose base hue and lightness (usually L:50%)
2. Generate 10-12 steps from very light to very dark
3. Lighten by: increasing lightness, adding white, reducing saturation
4. Darken by: decreasing lightness, adding black, may increase saturation
5. Test each step for perceptual uniformity

### Recommended Steps
```
50: near-white (backgrounds)
100: subtle background (hover on cards)
200: muted background (disabled states, table stripes)
300: soft border (dividers, disabled borders)
400: muted text (placeholder text, disabled labels)
500: base color (default state)
600: hover state (darken base)
700: active state (pressed/dark)
800: emphasized text (headings with contrast)
900: near-black (primary text)
950: deepest (very dark backgrounds)
```

### Dark Mode Adaptation
- Don't simply invert colors
- Reduce saturation in dark mode (30-50% less saturation)
- Use lighter text on dark backgrounds (90% for primary, 70% for secondary)
- Preserve hue but shift lightness down 40-60%
- Semantic colors: slightly desaturate to avoid eye strain

## Application-Specific Guidelines

### Data Visualization Colors
- Use colorblind-safe palettes (e.g., IBM Carbon, Tableau 10)
- Max 7-8 distinct colors in a single chart
- Avoid: red-green pairs for comparison
- Label data directly instead of relying on legends alone

### Dashboard Color Usage
- Neutrals for data — color for insight
- Green/red for performance metrics (up/down)
- Semantic system for status indicators
- Gradient scales for intensity maps (heat maps, severity)
