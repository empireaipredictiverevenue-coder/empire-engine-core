# TRAFFIC DIRECTOR · Skills Registry

## Registered Skills

### 1. `traffic.allocate_budget`
Distribute budget across channels based on performance data and strategic priorities.
- Input: total_budget, channel_performance (optional)
- Output: channel budget allocations

### 2. `traffic.channel.report`
Generate a per-channel performance report.
- Input: days (default 7), channels (optional, all if omitted)
- Output: structured report with spend, leads, CPL, reply rate per channel

### 3. `traffic.optimize_channel_mix`
Analyze channel performance and suggest optimal budget reallocation.
- Input: channel_data, constraints
- Output: suggested new allocation with projected impact

### 4. `traffic.strategy.review`
Review current traffic strategy against goals and market conditions.
- Input: none
- Output: strategy assessment with recommendations

## Specialized Sub-Agents
- ppc_specialist — Pay-per-call + search ads
- seo_specialist — Organic content, backlinks
- native_ads_specialist — Ad network campaigns
- email_sms_specialist — Outreach sequences
- social_specialist — Social ads + community
- affiliate_specialist — Recruit + manage partners
