# CONTRACTOR SNIPER · Skills Registry

## Registered Skills

### 1. `contractor.scout`
Find new roofing contractors in a metro area via Google Places / web search.
- Input: metro, limit (default 20)
- Output: list of potential contractors with name, phone, website, rating

### 2. `contractor.enroll`
Enroll a found contractor into the dispatch network.
- Input: name, phone, email, metro, specialties
- Output: contractor_id

### 3. `contractor.winback`
Send win-back sequence to dormant contractors.
- Input: days_dormant (default 30), limit (default 10)
- Output: count of messages sent

### 4. `contractor.status.report`
Current contractor network status — active, dormant, new, lost.
- Input: metro (optional)
- Output: structured report with counts and trends

### 5. `contractor.heartbeat.check`
Verify contractor responsiveness — ping a sample and measure response rate.
- Input: sample_size (default 10)
- Output: response rate, avg response time
