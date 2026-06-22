# Email Deliverability Reference

## Email Authentication

### SPF (Sender Policy Framework)
- TXT record listing authorized sending servers
- Format: `v=spf1 include:spf.resend.com ~all`
- Soft fail (`~all`): allows testing without breaking delivery
- Hard fail (`-all`): strict, reject unauthorized senders
- Max 10 DNS lookups per SPF record (Azure/external services count)
- Tools: MXToolbox SPF lookup, Resend domain setup wizard

### DKIM (DomainKeys Identified Mail)
- Cryptographic signature on every email
- Resend auto-configures DKIM for verified domains
- 2048-bit key recommended (vs 1024-bit)
- Rotate keys annually
- Monitor: `dig TXT resend._domainkey.yourdomain.com`

### DMARC (Domain-based Message Authentication, Reporting & Conformance)
- Policy: `none` → `quarantine` → `reject` (gradual rollout)
- Format: `v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com`
- Aggregate reports (rua): daily XML from receivers
- Forensic reports (ruf): individual failure details
- pct=100 (apply to all mail) after validation phase
- Monitor: dmarcian, Postmark DMARC, MXToolbox

### BIMI (Brand Indicators for Message Identification)
- Display brand logo in supporting email clients (Apple Mail, Gmail)
- Requires DMARC `p=quarantine` or `p=reject`
- SVG logo hosted at public URL
- Verified Mark Certificate (VMC) for checkmark in Gmail

## Sender Reputation

### Key Factors
- **Bounce rate**: < 2% (hard bounces), < 5% (soft bounces)
- **Spam complaint rate**: < 0.1% (Resend threshold)
- **Unknown user rate**: < 5%
- **List engagement**: open rate, click rate, reply rate
- **Volume consistency**: avoid sudden spikes or drops

### Repairing Reputation
1. Stop sending to unengaged segments (90+ days no open)
2. Remove all hard bounces immediately
3. Implement double opt-in for new subscribers
4. Reduce sending volume by 50% for 2 weeks
5. Send only to most engaged 25%
6. Monitor blocklists (Spamhaus, Barracuda, SURBL)

## Blocklists
- **Spamhaus ZEN**: most widely used, triggered by spam traps + high complaint rates
- **Barracuda**: triggered by spam reports + poor reputation
- **SURBL**: triggered by embedded URLs in spammy emails
- **URIBL**: triggered by known spam domains in email body
- **Invaluement**: triggered by spam traps and list buying
- **Check**: MXToolbox blacklist check, Resend deliverability dashboard

## Sending Best Practices

### Volume Management
- Increase volume gradually (10-15% per week)
- Warm new domains/IPs for 4-8 weeks
- Maintain consistent sending cadence (daily > bursts)
- Segment engagement tiers: high (weekly), medium (bi-weekly), low (monthly)

### Content Considerations
- Plain text > HTML for first-contact cold emails (> 70% plain text)
- Text-to-image ratio: minimum 60:40 (more text)
- Avoid: excessive links, one-image emails, spam trigger words
- Link to authenticated domains only
- Include physical mailing address in every email (CAN-SPAM)
- One-click unsubscribe in every email

### Sending Infrastructure
- Rate limit: respect provider limits (Resend: 5 req/s)
- Queue throttling: spread sends evenly across sending window
- Dedicated IP vs shared IP: dedicated for > 100K/month
- Sending window: business hours in recipient timezone (8 AM - 6 PM local)

## Email Metrics & Benchmarks

### Industry Benchmarks (B2B)
| Metric | B2B Cold | B2B Lifecycle |
|---|---|---|
| Open Rate | 20-35% | 35-50% |
| Click Rate | 2-6% | 4-12% |
| Reply Rate | 3-8% | 1-3% |
| Bounce Rate | 2-5% | 1-2% |
| Unsubscribe Rate | 0.3-0.8% | 0.1-0.3% |
| Complaint Rate | < 0.1% | < 0.05% |

### Metrics to Track
- **Inbox placement rate**: % that reaches inbox (not spam)
- **List churn rate**: % lost per month (unsubscribes + bounces + spam complaints)
- **Revenue per email**: total attributed revenue ÷ emails sent
- **Campaign ROI**: (revenue - cost) ÷ cost
- **Click-to-open rate (CTOR)**: clicks ÷ opens (measures content quality)
- **List engagement score**: weighted activity per subscriber

## List Acquisition

### Permitted Sources
- **Opt-in via website**: double opt-in preferred
- **Lead magnets**: content download, webinar registration
- **Event signups**: conference, workshop, demo request
- **B2B outreach**: business email address, relevant offer, CAN-SPAM compliant
- **Referral programs**: forwarded by existing subscriber

### Prohibited Sources
- Purchased or rented lists (guaranteed deliverability problems)
- Scraped email addresses (non-compliant, high bounce rates)
- Co-registration with unclear consent
- Automatically generated emails (local-part@domain.com patterns)
