# Marketing Skill Routing Reference

## Channel → Skill Mapping
| Channel | Primary Skill | Fallback Skills | SLA | Priority |
|---|---|---|---|---|
| Email Campaign | marketing.emails | marketing.copywriting, marketing.offers | 24h | Medium |
| Cold Outreach | marketing.cold-email | marketing.prospecting, marketing.copywriting | 4h | High |
| SMS Blast | marketing.sms | marketing.offers, marketing.marketing-psychology | 2h | Critical |
| SEO Content | marketing.content-strategy | marketing.programmatic-seo, marketing.ai-seo | 7d | Low |
| Schema Markup | marketing.schema | marketing.seo-audit | 48h | Medium |
| Paid Ads | marketing.ads | marketing.ad-creative, marketing.copywriting | 12h | High |
| Landing Page | marketing.copywriting | marketing.cro, marketing.signup | 24h | High |
| Referral Program | marketing.referrals | marketing.offers, marketing.community | 7d | Low |
| Onboarding Flow | marketing.onboarding | marketing.emails, marketing.signup | 48h | Medium |
| Social Content | marketing.social | marketing.content-strategy, marketing.image | 24h | Medium |
| Video Campaign | marketing.video | marketing.content-strategy, marketing.copywriting | 7d | Low |
| Product Launch | marketing.launch | marketing.product, marketing.marketing-plan | 14d | Critical |

## Skill Dependencies
- marketing.emails → marketing.copywriting (needs copy)
- marketing.ads → marketing.ad-creative (needs creative) + marketing.copywriting (needs copy)
- marketing.launch → marketing.product (needs positioning) + marketing.marketing-plan (needs plan)
- marketing.sms → marketing.offers (needs offer) + marketing.copywriting (needs copy)
- marketing.seo-audit → marketing.site-architecture (needs architecture audit) + marketing.schema (needs schema audit)

## Compliance Gates
| Channel | TCPA | CAN-SPAM | Hours |
|---|---|---|---|
| Email | N/A | Unsubscribe link required | Anytime |
| SMS | Consent + opt-out required | N/A | 8am-9pm local |
| Cold Call | DNC scrub + consent | N/A | 8am-9pm local |
| Social | N/A | N/A | Anytime |
| Ads | N/A | N/A | Anytime |

## Escalation Path
1. Marketing skill fails → retry with backoff (30s, 2min, 5min) up to 3x
2. All retries exhausted → escalate to Hermes Controller with failure context
3. Compliance block → escalate immediately with rule violation detail
4. Budget overrun → escalate to operator with spending summary
