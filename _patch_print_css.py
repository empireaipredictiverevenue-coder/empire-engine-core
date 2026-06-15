"""Add print-friendly CSS for Revenue/Pulse dashboard tabs to the existing @media print block."""

with open('empire_command_spa.py', 'rb') as f:
    data = f.read()

# Find the end of the existing @media print block
# The block ends with a closing } after the print-date rule
marker = b'.cpl-header .print-date{display:block!important;font-family:monospace!important;\nfont-size:7px!important;color:#999!important;margin-top:2px!important}\n}'

if marker not in data:
    print("[FAIL] Could not find end of @media print block")
    exit(1)

# The new print styles for Pulse and Revenue tabs
new_styles = b"""
/* -- PULSE DASHBOARD PRINT STYLES --------------------------------- */
.pulse-grid{display:grid!important;grid-template-columns:repeat(4,1fr)!important;gap:8px!important;margin-bottom:12px!important}
.stat-card{background:#f8f8f8!important;border:1px solid #ccc!important;padding:10px 12px!important;page-break-inside:avoid!important}
.stat-label{font-size:8px!important;color:#666!important;letter-spacing:0.12em!important}
.stat-value{font-size:22px!important;color:#000!important}
.stat-value.teal{color:#008080!important}
.stat-value.cyan{color:#0088aa!important}
.stat-value.dim{color:#888!important}
.stat-meta{color:#666!important;font-size:8px!important}
.pulse-tabs{display:none!important}
.pulse-tab{display:none!important}
.section-sub{font-size:8px!important;color:#666!important}

/* -- REVENUE DASHBOARD PRINT STYLES ------------------------------- */
.pipeline-breakdown{background:#fff!important;border:1px solid #ccc!important;padding:12px!important;margin-bottom:12px!important;page-break-inside:avoid!important}
.pipeline-h{border-bottom:1px solid #ddd!important;margin-bottom:10px!important}
.pipeline-title{font-size:12px!important;color:#000!important}
.pipeline-total{color:#008080!important;font-size:10px!important}
.pipeline-grid{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))!important;gap:8px!important}
.rv-bar-row{display:grid!important;grid-template-columns:100px 1fr 60px 40px!important;gap:8px!important;padding:5px 0!important;border-bottom:1px solid #eee!important;font-size:9px!important}
.rv-bar-lane{color:#000!important;font-weight:600!important;font-size:9px!important}
.rv-bar-niche{color:#666!important;font-size:7px!important}
.rv-bar-track{height:8px!important;background:#eee!important;border-radius:3px!important}
.rv-bar-fill{background:#008080!important;border-radius:3px!important;min-width:2px!important}
.rv-bar-val{color:#008080!important;font-size:10px!important}
.rv-bar-meta{color:#888!important;font-size:7px!important}
.rv-accuracy-panel{background:#fff!important;border:1px solid #ccc!important;padding:12px!important;margin-top:12px!important;page-break-inside:avoid!important}
.rv-accuracy-head{border-bottom:1px solid #ddd!important;margin-bottom:12px!important;padding-bottom:8px!important}
.rv-accuracy-title{font-size:12px!important;color:#000!important}
.rv-accuracy-summary{font-size:9px!important;color:#666!important}
.rv-accuracy-chart{display:block!important;max-height:none!important}
.rv-acc-row{display:grid!important;grid-template-columns:50px 1fr 44px!important;gap:8px!important;padding:4px 0!important;border-bottom:1px solid #eee!important}
.rv-acc-date{color:#666!important;font-size:8px!important}
.rv-acc-bar-wrap{height:12px!important;background:#eee!important;border-radius:2px!important}
.rv-acc-bar.forecast{background:#0088aa!important;opacity:0.7!important}
.rv-acc-bar.actual{background:#008080!important;opacity:0.9!important}
.rv-acc-bar-label{font-size:7px!important;color:#fff!important}
.rv-acc-pct{font-size:10px!important;color:#000!important}
.rv-accuracy-legend{display:flex!important;gap:14px!important;margin-top:8px!important;padding-top:8px!important;border-top:1px solid #eee!important;font-size:8px!important}
.rv-acc-legend-swatch{width:8px!important;height:8px!important}
/* -- Hide non-essential elements ---------------------------------- */
.pulse-tabs + .pulse-tabs,
.topbar-actions,.rv-alerts,.rv-niche-card,.rv-narrative-panel,
.rv-accuracy-actions,.rv-export-btn,.rv-usdc-panel,
.section-h .topbar-actions{display:none!important}
"""

# Insert before the closing } of the @media print block
# The marker ends with '}\n}' — we replace the last '}' with new_styles + '}'
old_end = b'}\n}'
new_end = b'}' + new_styles + b'}'

# Apply after the marker
insert_pos = data.find(marker) + len(marker)
# The marker ends with '}\n}' — the last } is the closing brace of @media print
# We want to insert BEFORE that closing brace
# So we replace the final '}' with newstyles + '}'
final_brace_pos = data.rfind(b'}', insert_pos - 2, insert_pos + 2)
# Actually the marker ends with '}\n}' so we want to replace the last '}'
pass

# Simpler approach: find the exact position and do a direct replacement
idx = data.find(marker)
if idx >= 0:
    # Find the closing } after the marker
    # The marker ends with '}\n}' so the last char of the marker IS the closing brace
    end_of_print_block = idx + len(marker)  # this points past the closing }
    # Insert new styles right before the closing }
    # The marker's last char is '}'. We want to keep that '}' but add styles before it.
    # Actually the marker is: ...margin-top:2px!important}\n}
    # The last '}' closes @media print. We want before that.
    # Let's find the second-to-last }
    second_to_last_brace = data.rfind(b'}', idx, idx + len(marker) - 1)
    if second_to_last_brace >= 0:
        before_close = data[:second_to_last_brace]
        after_close = data[second_to_last_brace:]
        new_data = before_close + new_styles + after_close
        with open('empire_command_spa.py', 'wb') as f:
            f.write(new_data)
        print(f"[OK] Inserted {len(new_styles)} bytes of print styles before closing brace")
    else:
        print("[FAIL] Could not locate second-to-last brace")
else:
    print("[FAIL] Could not find end of @media print block")
