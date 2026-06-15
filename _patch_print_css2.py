"""
Fix: Reclaim sidebar space in print and remove dead CSS classes.
"""
import sys

with open('empire_command_spa.py', 'rb') as f:
    data = bytearray(f.read())

# 1. Reclaim sidebar space: add .app{grid-template-columns:1fr!important}
# after the body style line
old_body = b'body{background:#fff!important;color:#111!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif!important}'
new_body = b'body{background:#fff!important;color:#111!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif!important}' \
           b'\n.app{grid-template-columns:1fr!important}' \
           b'\n.nav,.nav *{display:none!important}'

idx = data.find(old_body)
if idx >= 0:
    end = idx + len(old_body)
    data[idx:end] = new_body
    print("[OK] Fixed: .app grid-columns and .nav hidden in print")
else:
    print("[FAIL] Could not find body style in print CSS")

# 2. Remove dead CSS classes .cpl-health-dot, .print-only, .print-date
# Remove the cpl-health-dot block
old_dots = b'\n.cpl-health-dot{display:inline-block!important;width:8px!important;height:8px!important;border-radius:50%!important;margin-right:2px!important}\n.cpl-health-dot.green{background:#4CAF50!important}\n.cpl-health-dot.amber{background:#FFC107!important}\n.cpl-health-dot.red{background:#F44336!important}\n'
idx2 = data.find(old_dots)
if idx2 >= 0:
    end2 = idx2 + len(old_dots)
    data[idx2:end2] = b'\n'
    print("[OK] Removed dead .cpl-health-dot CSS")
else:
    print("[FAIL] Could not find .cpl-health-dot CSS")

# Remove the print-only and print-date block
old_utils = b'\n.no-print,.cpl-skeleton{display:none!important}\n.print-only{display:block!important}\n'
idx3 = data.find(old_utils)
if idx3 >= 0:
    end3 = idx3 + len(old_utils)
    data[idx3:end3] = b'\n.no-print,.cpl-skeleton{display:none!important}\n'
    print("[OK] Removed dead .print-only CSS")
else:
    print("[FAIL] Could not find .print-only CSS")

# Remove the print-date block
old_date = b"\n.cpl-header .print-date{display:block!important;font-family:monospace!important;font-size:7px!important;color:#999!important;margin-top:2px!important}"
idx4 = data.find(old_date)
if idx4 >= 0:
    end4 = idx4 + len(old_date)
    data[idx4:end4] = b''
    print("[OK] Removed dead .print-date CSS")
else:
    print("[FAIL] Could not find .print-date CSS")

with open('empire_command_spa.py', 'wb') as f:
    f.write(data)

print("\nAll fixes applied!")
