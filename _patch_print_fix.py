"""Fix missing CSS classes (rv-bar-label, rv-acc-bars, section-title) 
and clean up redundant selectors in the @media print block."""

with open('empire_command_spa.py', 'rb') as f:
    data = f.read()

# Find the "Hide non-essential elements" section
old_block = b'/* -- Hide non-essential elements ---------------------------------- */\n.pulse-tabs + .pulse-tabs,\n.topbar-actions,.rv-alerts,.rv-niche-card,.rv-narrative-panel,\n.rv-accuracy-actions,.rv-export-btn,.rv-usdc-panel,\n.section-h .topbar-actions{display:none!important}\n}\n}'

new_block = b'/* -- Section title / container support ------------------------------ */\n.section-title{font-size:20px!important;color:#000!important}\n.section-title em{color:#008080!important}\n.rv-bar-label{display:flex!important;flex-direction:column!important;gap:2px!important}\n.rv-acc-bars{display:flex!important;flex-direction:column!important;gap:4px!important}\n\n/* -- Hide non-essential elements ---------------------------------- */\n.topbar-actions,.rv-alerts,.rv-niche-card,.rv-narrative-panel,\n.rv-accuracy-actions,.rv-export-btn,.rv-usdc-panel{display:none!important}\n}'

if old_block in data:
    data = data.replace(old_block, new_block)
    with open('empire_command_spa.py', 'wb') as f:
        f.write(data)
    print("[OK] Replaced with fixed CSS including rv-bar-label, rv-acc-bars, section-title styles")
else:
    print("[FAIL] Could not find the exact block to replace")
    # Show what's actually there
    idx = data.find(b'Hide non-essential')
    if idx >= 0:
        print(f"Found at offset {idx}, showing 300 bytes:")
        print(data[idx:idx+300].decode('utf-8', errors='replace'))
