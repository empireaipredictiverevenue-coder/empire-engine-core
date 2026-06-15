import sys

with open('empire_command_spa.py', 'rb') as f:
    data = bytearray(f.read())

# ── EDIT 1: Add prevHealthRef state ──
old = b'const [pulseBreakdown, setPulseBreakdown] = useState(null);'
new = b'const [pulseBreakdown, setPulseBreakdown] = useState(null);\n  const prevHealthRef = useRef(null);'
idx = data.find(old)
if idx >= 0:
    end = idx + len(old)
    data[end:end] = b'\n  const prevHealthRef = useRef(null);'
    print("[OK] Edit 1: Added prevHealthRef")
else:
    print("[FAIL] Edit 1")

# ── EDIT 2: Add delta computation after g/a/r line ──
# Find: const g = ... a = ... r = ...;
old2 = b'const g = h.green || 0, a = h.amber || 0, r = h.red || 0;\n                const t = g+a+r;'
# Find at JS template section (after byte 160000)
idx2 = data.find(old2, 160000)
if idx2 < 0:
    idx2 = data.find(old2)
    
if idx2 >= 0:
    # Find the end of 'const t = g+a+r;'
    end2 = idx2 + len(old2)
    
    # Insert delta logic before 'if (t > 0)' 
    delta_logic = b'\n                var deltaStr = \'\';\n                const prev = prevHealthRef.current;\n                if (prev && t > 0) {\n                  const dg = g - prev.green, da = a - prev.amber, dr = r - prev.red;\n                  if (dg || da || dr) deltaStr = (dg>0?"+":"") + dg + "g " + (da>0?"+":"") + da + "a " + (dr>0?"+":"") + dr + "r";\n                }\n                if (t > 0) prevHealthRef.current = {green: g, amber: a, red: r};\n'
    data[end2:end2] = delta_logic
    print("[OK] Edit 2: Added delta computation")
else:
    print("[FAIL] Edit 2: g/a/r line not found")
    # Debug
    test = data.find(b'const g = h.green', 160000)
    print(f"  g/a/r search result: {test}")

# ── EDIT 3: Update lanes span to include delta ──
old3 = b'<span>${t} lanes</span>'
idx3 = data.find(old3, 170000)  # Find in JS section
if idx3 < 0:
    idx3 = data.find(old3)

if idx3 >= 0:
    end3 = idx3 + len(old3)
    new3 = b'<span>${deltaStr?html`<span style="color:var(--empire-mist);margin-right:8px">${deltaStr}</span>`:\'\'}${t} lanes</span>'
    data[idx3:end3] = new3
    print("[OK] Edit 3: Updated lanes span with delta")
else:
    print("[FAIL] Edit 3: lanes span not found")

with open('empire_command_spa.py', 'wb') as f:
    f.write(data)

print("\nAll edits applied!")
