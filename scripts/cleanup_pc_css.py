"""Remove the orphaned old panel court CSS block (now dead after rewrite)."""
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    content = f.read()

# The old block starts with this comment and ends before the next section comment
start_marker = "/* ── PANEL_COURT 5-PANEL CONSENSUS ───────────────────────────────── */"
# Find the next CSS section after it (SI STRATEGY EVOLUTION)
end_marker = "/* ── SI STRATEGY EVOLUTION ────────────────────────────────────── */"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    # Remove everything from start_marker to just before end_marker
    content = content[:start_idx] + content[end_idx:]
    changes = 1
    print("Removed orphaned old panel court CSS block")
else:
    print(f"Markers not found: start={start_idx}, end={end_idx}")
    changes = 0

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"Done: {changes} changes")
