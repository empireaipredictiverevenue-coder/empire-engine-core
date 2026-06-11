import os

# Fix SPA
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    spa = f.read()

c = 0
# Fix 1: poolData -> data (poolData is scoped to .then() callback, not render path)
if 'poolData || data' in spa:
    spa = spa.replace('const d0 = poolData || data;', 'const d0 = data;')
    c += 1
    print("SPA: poolData -> data")

# Fix 2: arrow radius 160 -> 148
if 'const cr = 160;' in spa:
    spa = spa.replace('const cr = 160; // slightly inside the orbit ring', 'const cr = 148; // inside orbit ring to avoid card overlap')
    # Also fix the cx/cy that use cr
    spa = spa.replace('const cx = Math.cos(cAngle) * cr;\n                    const cy = Math.sin(cAngle) * cr;\n                    const tx = Math.cos(tAngle) * cr;\n                    const ty = Math.sin(tAngle) * cr;',
                       'const cx = Math.cos(cAngle) * 148;\n                    const cy = Math.sin(cAngle) * 148;\n                    const tx = Math.cos(tAngle) * 148;\n                    const ty = Math.sin(tAngle) * 148;')
    c += 1
    print("SPA: arrow radius 160->148")

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(spa)

# Fix panel_court.py: add agent_critiques to _log_decision
with open('/root/empire-v49/bots/panel_court.py', 'r') as f:
    pc = f.read()

old_log = '"judge_reasoning": result.get("judge_reasoning", "")[:500],'
new_log = '"judge_reasoning": result.get("judge_reasoning", "")[:500],\n                "agent_critiques": json.dumps(result.get("agent_critiques", [])),'
if old_log in pc:
    pc = pc.replace(old_log, new_log)
    c += 1
    print("PanelCourt: agent_critiques persisted to DB")
else:
    print("WARN: Could not find _log_decision line for critique persistence")

with open('/root/empire-v49/bots/panel_court.py', 'w') as f:
    f.write(pc)

print(f"Total fixes: {c}")
