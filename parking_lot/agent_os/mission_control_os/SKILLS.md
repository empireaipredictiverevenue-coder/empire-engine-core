# MISSION CONTROL · Skills Registry

## Registered Skills

### 1. `mc.snapshot`
Assemble the full Mission Control snapshot from all subsystems (AGI, SI, brain, revenue, compliance, network, agent OS kernel).
- Input: none
- Output: unified snapshot dict with all subsystems, health color, timestamps

### 2. `mc.health`
Traffic-light health assessment for the entire fleet.
- Input: subsystem (optional filter, e.g. "brain", "agi", "revenue")
- Output: health dict with color (green/amber/red) per subsystem + root cause if red

### 3. `mc.anomaly`
Detect anomalies by correlating metrics across subsystems. Flags funnels blockages, stale agents, revenue drops.
- Input: lookback_minutes (default 60)
- Output: list of anomalies with severity, subsystem, message, and correlated metrics

### 4. `mc.agent-os`
Snapshot of the Agent OS kernel: all registered agents, their status, IPC bus events, capability registry.
- Input: none
- Output: kernel.processes, kernel.ipc, kernel.capabilities snapshot

### 5. `mc.autoresearch`
Status of the recursive self-healing loop — all autoresearch targets and their latest results.
- Input: none (reads scratchpad.md)
- Output: per-target metrics, improvement history, system status table

### 6. `mc.skills`
Snapshot of the ImmutableSkillRegistry — all registered skills across all agent OS instances.
- Input: domain filter (optional)
- Output: skills grouped by domain, active versions, total count

### 7. `mc.system-status`
Aggregate report combining health + anomalies + agent OS + autoresearch + skills.
- Input: none
- Output: comprehensive system status suitable for Telegram digest or dashboard

## Managed Agents
- mc.snapshot — Assembles the unified snapshot every 5s
- mc.health — Traffic-light health assessment
- mc.anomaly — Cross-system anomaly detection
- mc.agent-os — Agent OS kernel monitoring
- mc.autoresearch — Recursive loop status tracking
- mc.skills — Skills registry monitoring
- mc.system-status — Comprehensive system status report
