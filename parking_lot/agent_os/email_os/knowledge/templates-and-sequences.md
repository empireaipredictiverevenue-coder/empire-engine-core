# Email Template & Sequence Reference

## Email Shell Structure

### Empire Email HTML Shell (CAN-SPAM compliant)
```
┌──────────────────────────────────────────┐
│  BRAND BAR                               │
│  Empire AI · Predictive Revenue          │
│  Paid commercial notice · Sender Name    │
├──────────────────────────────────────────┤
│                                          │
│  ┌────────────────────────────────────┐  │
│  │        BODY CONTENT                │  │
│  │  (subject, value props, CTA)       │  │
│  └────────────────────────────────────┘  │
│                                          │
├──────────────────────────────────────────┤
│  DISCLOSURE + CAN-SPAM FOOTER            │
│  Why you received this                   │
│  Physical postal address                 │
│  [Unsubscribe] · One click               │
└──────────────────────────────────────────┘
```

### Required Elements (per CAN-SPAM)
1. **Brand Bar** — Sender identity, commercial disclosure
2. **Body** — Value proposition, content, CTA
3. **Disclosure** — Why recipient received this
4. **Physical Address** — Current street address or PO Box
5. **Unsubscribe Link** — One-click, works immediately
6. **Tracking Pixel** — Invisible 1x1 GIF for open detection (optional)

## Sequence Design Patterns

### 4-Touch Storm Strike Sequence (default)
| Step | Timing | Subject Pattern | Goal |
|---|---|---|---|
| 0 | T+0 | Storm activity detected at {target} | Immediate awareness + assessment CTA |
| 1 | T+24h | Following up · {target} storm assessment | Urgency: 72-hour insurance window |
| 2 | T+72h | {target} · what we'd find | Education: assessment process |
| 3 | T+7d | Last note from us · {target} | Final touch + graceful exit |

### 4-Touch B2B Outreach Sequence
| Step | Timing | Subject Pattern | Goal |
|---|---|---|---|
| 0 | T+0 | Qualified {niche} leads for {company} | Value proposition + success fee model |
| 1 | T+24h | Following up · {company} lead generation | Process detail + credibility |
| 2 | T+72h | {company} · what providers are saying | Social proof + results |
| 3 | T+7d | Last note from us · {company} | Final touch + graceful exit |

### Lead Nurture Sequence
| Step | Timing | Subject Pattern | Goal |
|---|---|---|---|
| 0 | T+0 | Qualified leads for {facility} | B2B partnership value prop |
| 1 | T+24h | Following up · {facility} lead generation | Process + verification detail |
| 2 | T+72h | {facility} · what operators are saying | Social proof + results |
| 3 | T+7d | Last note from us · {facility} | Final touch + graceful exit |

### Product Email Sequences
| Sequence | Steps | Timing | Goal |
|---|---|---|---|
| Onboarding | 5 (welcome → setup → first value → best practices → request feedback) | Days 0, 1, 3, 7, 14 | Activation |
| Trial Conversion | 4 (day 5 → 8 → 11 → 14) | Trial progression | Conversion to paid |
| Upsell | 3 (value expansion → feature reveal → limited offer) | Post-purchase or pre-renewal | Revenue expansion |
| Renewal | 3 (reminder 7d → 3d → expired) | Before expiry | Retention |
| Reactivation | 3 (day 1 → 7 → 30 post-expiry) | After expiry | Win-back |

## Send Time Optimization

### Best Send Times by Industry (Recipient Local Time)
| Industry | Best Day | Best Time |
|---|---|---|
| B2B Services | Tuesday-Thursday | 8-11 AM |
| Construction | Tuesday, Thursday | 6-8 AM |
| Home Services | Wednesday, Friday | 8-10 AM |
| Finance | Tuesday, Thursday | 7-9 AM |
| Healthcare | Monday, Wednesday | 9-11 AM |
| Retail | Wednesday, Saturday | 10 AM - 1 PM |

### Empire Quiet Hours
- No emails between 10 PM - 7 AM recipient's local time zone
- Detect via recipient timezone in profile, or use US time zones as default
- Override available for transactional/automated messages

## Templating Best Practices

### HTML Email Design
- **Use tables for layout**: email clients strip modern CSS
- **Inline CSS**: no `<style>` blocks in body (Gmail strips them)
- **Max width**: 600px for desktop, fluid for mobile
- **Font stack**: `-apple-system, system-ui, 'Helvetica Neue', sans-serif`
- **Fallback colors**: backgrounds in `<td>` not CSS
- **Dark mode**: add `[data-ogsc]` and `[data-ogsb]` attribute selectors for Outlook
- **Accessibility**: semantic `<table>` structure, alt text on all images, readable contrast

### Responsive Email
```css
@media screen and (max-width: 600px) {
  .email-table { width: 100% !important; }
  .email-padding { padding: 16px !important; }
  .email-button { width: 100% !important; display: block !important; }
  .email-hide-mobile { display: none !important; }
}
```

### Tracking Integration
- Open tracking: 1×1 transparent GIF loaded via query string
- Click tracking: Signed redirect URL wrapping target links
- UTM parameters: utm_source=email&utm_medium=email&utm_campaign={campaign}
- Events logged to email_tracking table (open, click, bounce, unsubscribe)

## Personalization Fields

### Available Merge Tags
```
{{first_name}}        — Recipient first name
{{company}}           — Company/organization name
{{target_location}}   — City, State or property address
{{sequence_step}}     — Current sequence step number
{{unsubscribe_url}}   — Signed one-click unsubscribe link
{{tracking_pixel}}    — Invisible 1x1 tracking GIF
{{sender_name}}       — Human sender display name
{{niche}}             — Industry/vertical
{{storm_event}}       — Severe weather event name
{{severity}}          — Damage severity level
```

### Personalization Rules
- Always check field exists before using (fallback to generic)
- Keep personalization natural — don't force fields that don't fit
- Never use personalization in subject line if data quality is low
- Test personalization rendering across email clients
