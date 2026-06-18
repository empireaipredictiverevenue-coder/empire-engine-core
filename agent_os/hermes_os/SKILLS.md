# HERMES MESH · Skills Registry

## Registered Skills

### 1. `mesh.task.create`
Create a new task ticket in the agent_task_queue.
- Input: task_type, payload, assigned_agent (optional), priority
- Output: ticket_id

### 2. `mesh.task.claim`
Atomically claim the next available task for an agent.
- Input: agent_name, task_types (optional filter)
- Output: task dict or null

### 3. `mesh.task.update`
Update a task's status (Done, Failed, Blocked, etc.).
- Input: ticket_id, status, result (optional), error (optional)
- Output: ok

### 4. `mesh.agent.heartbeat`
Register/ping an agent in the registry.
- Input: agent_name, status
- Output: ok

### 5. `mesh.status.report`
Full mesh snapshot — agents, queue stats, recent tasks.
- Input: none
- Output: structured mesh status

## Mesh Agents Managed
- mesh.scout — Finds targets in storm zones
- mesh.outreach — Sends messages
- mesh.dispatcher — Dispatches contractors
- mesh.studio_copy — Writes copy
- mesh.studio_render — Renders videos
- mesh.quality — Scores calls
