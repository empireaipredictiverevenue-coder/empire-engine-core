import sys

with open('empire_command_spa.py', 'rb') as f:
    data = bytearray(f.read())

# Find the forEach closing and CSV generation start
old = b'});\n    const csv = rows.map'
idx = data.find(old)
if idx < 0:
    print("[FAIL] Could not find forEach close + csv gen pattern")
    sys.exit(1)

# Build the insertion JS
# We need to insert AFTER the forEach close (the closing }); )
# Find the exact end of }); 
insert_point = idx + len(b'});')

# The summary computation JS as bytes
summary_js = b'\n    // Aggregate summary row\n    const pricedLanes = lanes.filter(l => l.cpl_available);\n    const n = pricedLanes.length;\n    const totalMRR = pricedLanes.reduce(function(s, l) { return s + (l.monthly_revenue || 0); }, 0);\n    const avgAcq = n > 0 ? Math.round(pricedLanes.reduce(function(s, l) { return s + (l.monthly_acq_cost || 0); }, 0) / n) : 0;\n    var g = 0, a = 0, r = 0;\n    pricedLanes.forEach(function(l) {\n      if (l.roi_pct == null) return;\n      if (l.roi_pct > 0 && l.margin_pct > 50 && l.breakeven <= 200) g++;\n      else if (l.roi_pct > 0) a++;\n      else r++;\n    });\n    rows.push([\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\']);\n    rows.push([\'TOTALS\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'\',\'$\'+totalMRR,\'$\'+avgAcq,\'\',\'G:\'+g+\' A:\'+a+\' R:\'+r,\'\']);\n'

data[insert_point:insert_point] = summary_js

with open('empire_command_spa.py', 'wb') as f:
    f.write(data)

print(f"[OK] Inserted {len(summary_js)} bytes of summary row JS after forEach close")
