import re
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# Fix 1: Add chartDrawn useRef after highlighted useState
old1 = "const [highlighted, setHighlighted] = useState(null);"
new1 = "const [highlighted, setHighlighted] = useState(null);\n  const chartDrawn = useRef(false);"
if old1 in content:
    content = content.replace(old1, new1)
    changes += 1
    print("✓ Added chartDrawn useRef")
else:
    print("NOT FOUND: highlighted useState")

# Fix 2: Add useEffect to mark chart drawn, before agent sort
old2 = "const agents = (pool && pool.agents ? [...pool.agents] : []).sort((a, b) => (a.id || 0) - (b.id || 0));"
new2 = "useEffect(() => { if (pool && pool.temperature_history && pool.temperature_history.length >= 2) { chartDrawn.current = true; } }, [pool]);\n\n  const agents = (pool && pool.agents ? [...pool.agents] : []).sort((a, b) => (a.id || 0) - (b.id || 0));"
if old2 in content:
    content = content.replace(old2, new2)
    changes += 1
    print("✓ Added chartDrawn useEffect")
else:
    print("NOT FOUND: agents sort")

# Fix 3: Conditional animation on path elements
old3 = """return html`<path key=${'line'+a.id} d="${d}" class="pc-converge-line" stroke="${color}" opacity="${lineOpacity}" style=${{strokeDasharray:'1000',strokeDashoffset:'1000',animation:'pc-chart-draw 1.2s var(--ease-out-empire) '+(ai * 0.08)+'s forwards'}}/>`;"""
new3 = """const drawStyle = !chartDrawn.current ? {strokeDasharray:'1000',strokeDashoffset:'1000',animation:'pc-chart-draw 1.2s var(--ease-out-empire) '+(ai * 0.08)+'s forwards'} : {};
          return html`<path key=${'line'+a.id} d="${d}" class="pc-converge-line" stroke="${color}" opacity="${lineOpacity}" style=${drawStyle}/>`;"""
if old3 in content:
    content = content.replace(old3, new3)
    changes += 1
    print("✓ Conditional animation on first render only")
else:
    print("NOT FOUND: path style animation")

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"Total: {changes}")
