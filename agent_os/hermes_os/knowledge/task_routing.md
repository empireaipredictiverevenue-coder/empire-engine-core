# Task Routing Reference

## Task Type → Agent Mapping
| Task Type | Assigned Agent | SLA | Priority |
|---|---|---|---|
| scout.find_roofs | mesh.scout | 30 min | High |
| outreach.draft_email | mesh.outreach | 5 min | Critical |
| studio.write_script | mesh.studio_copy | 60 min | Medium |
| studio.render_reel | mesh.studio_render | 10 min | High |
| revenue.connect_buyer | mesh.dispatcher | 5 min | Critical |
| revenue.score_call | mesh.quality | 15 min | Medium |
| swarm.fire | mesh.swarm_worker | 5 min | High |
| swarm.strike_video | mesh.swarm_worker | 10 min | Medium |

## Retry Policy
- Failed tasks: retry up to 3 times with exponential backoff (30s, 2min, 5min)
- Blocked tasks: notify operator via IPC event every 30 min
- Stale In-Progress: reassign after 2× SLA timeout

## Agent Health Rules
- Expected heartbeat: every 30s (configurable)
- Missed 3 heartbeats → mark as STALE → try restart
- Missed 6 heartbeats → mark as ERROR → alert operator
- Auto-recover: restart ERROR agents every 5 min (max 5 attempts)
