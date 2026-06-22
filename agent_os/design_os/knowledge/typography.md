# Typography Systems Reference

## Type Classification

### Serif
- Classic, authoritative, readable for long-form text
- Use: body text in print, editorial content, formal brands
- Examples: Georgia, Merriweather, Playfair Display

### Sans-Serif
- Modern, clean, highly readable on screens
- Use: UI text, headings, digital-first brands
- Examples: Inter, Roboto, Open Sans, SF Pro

### Monospace
- Technical, precise, equal-width characters
- Use: code, data, tables, system output
- Examples: JetBrains Mono, Fira Code, Source Code Pro

### Display
- Decorative, expressive, unique personality
- Use: headlines, logos, limited contexts
- Caution: low readability at small sizes

## Type Scale

### Modular Scale
- Base size: 16px (1rem) is standard for body text
- Ratio options: 1.125 (major second), 1.25 (major third), 1.333 (perfect fourth)
- Recommended UI scale with 1.25 ratio:
  ```
  text-xs:   12px  (0.75rem)
  text-sm:   14px  (0.875rem)
  text-base: 16px  (1rem)
  text-lg:   20px  (1.25rem)
  text-xl:   24px  (1.5rem)
  text-2xl:  28px  (1.75rem)
  text-3xl:  36px  (2.25rem)
  text-4xl:  44px  (2.75rem)
  text-5xl:  56px  (3.5rem)
  text-6xl:  64px  (4rem)
  ```

### Line Height (Leading)
- Body text: 1.5-1.7 (relaxed for readability)
- Headings: 1.1-1.3 (tight for visual grouping)
- UI labels: 1.0 (match height to text)
- Multi-column: increase line height with column count

### Line Length (Measure)
- Optimal: 45-75 characters per line
- Minimum: 30 characters
- Maximum: 80 characters (web), 70 characters (mobile)
- Solution: max-width container (typically 600-700px for body text)

## Hierarchy

### Establishing Visual Hierarchy
1. Scale: larger = more important
2. Weight: bolder = more important (400 regular, 500 medium, 600 semibold, 700 bold)
3. Color: higher contrast = more important
4. Spacing: more space around = more important
5. Case: uppercase = emphasis (use sparingly)

### UI Typography Hierarchy
```css
/* Screen Title */
font-size: 24px; font-weight: 600; line-height: 1.3;

/* Section Heading */
font-size: 18px; font-weight: 600; line-height: 1.4;

/* Card Title */
font-size: 16px; font-weight: 600; line-height: 1.4;

/* Body Text */
font-size: 14px; font-weight: 400; line-height: 1.5;

/* Caption / Metadata */
font-size: 12px; font-weight: 400; line-height: 1.4; color: var(--color-text-secondary);

/* Label */
font-size: 13px; font-weight: 500; line-height: 1.0;

/* Data / Monospace */
font-size: 14px; font-weight: 400; font-family: monospace;
```

## Readability Guidelines

### Font Selection for UI
- Prefer system fonts for performance (Inter, SF Pro, system-ui)
- Max 2 typefaces per interface (one heading, one body — or same for both)
- Ensure font supports: Latin Extended, Cyrillic, locale-specific characters
- Variable fonts preferred over static — fewer HTTP requests, more flexibility

### Text Readability
- Minimum 16px for body text on web
- Minimum 14px for secondary/caption text
- Avoid: all-caps for long passages, low contrast text, justified alignment
- Use: sentence case for UI labels, title case for headings

## Responsive Typography

### Fluid Type Scaling
```css
/* Fluid type using clamp() */
--font-size-heading: clamp(1.5rem, 1rem + 2vw, 2.5rem);
--font-size-body: clamp(0.875rem, 0.75rem + 0.5vw, 1rem);
```

### Breakpoint Adjustments
- Mobile: smaller scale, tighter line height, shorter line length
- Tablet: medium scale, standard line height
- Desktop: full scale, wider line length (max-width container)
- Large desktop: maximum scale, maintained line length with centering

## Accessibility

### Typography Accessibility
- Minimum 16px body text (some browsers zoom to 16px minimum)
- Minimum touch target for clickable text: 44x44px
- Avoid: justified text (causes uneven word spacing), italics for long passages
- Letter spacing: 0.02em minimum for all-caps text
- Word spacing: normal or wider for readability

### Dyslexia-Friendly Typography
- Sans-serif fonts preferred
- Adequate letter spacing (0.05em minimum)
- Avoid italics for emphasis (use bold instead)
- Left-aligned text (not centered or justified)
- Short line length (50-60 characters)
