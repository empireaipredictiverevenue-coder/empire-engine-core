import sys
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    content = f.read()

# Fix: Dynamic Y-axis ticks from data range
old_ticks = "const yTicks = [0.05, 0.08, 0.11, 0.14];"
new_ticks = "const tickCount = 4;\n        const yTicks = Array.from({length: tickCount}, (_, i) => Math.round((tempMin + (tempSpan * i / (tickCount - 1))) * 100) / 100);"

if old_ticks in content:
    content = content.replace(old_ticks, new_ticks)
    print("OK: dynamic ticks")
else:
    print("NOT FOUND: yTicks")

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(content)
