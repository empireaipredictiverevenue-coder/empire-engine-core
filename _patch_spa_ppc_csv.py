"""Patch empire_command_spa.py to add 'PPC Ready' column to CSV export."""

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# 1. Headers: add 'PPC Ready' after 'CPL Available'
old_headers = "['Lane','Niche','Sub-Niche','CPL Low','CPL High','Model','Sell Price Low','Sell Price High','Margin %','Annual Revenue','ROI %','Mo. Rev','Acq Cost','BE Vol','Health','CPL Available']];"
new_headers = "['Lane','Niche','Sub-Niche','CPL Low','CPL High','Model','Sell Price Low','Sell Price High','Margin %','Annual Revenue','ROI %','Mo. Rev','Acq Cost','BE Vol','Health','CPL Available','PPC Ready']];"
if old_headers in content:
    content = content.replace(old_headers, new_headers)
    changes += 1
    print(f"[1/3] Headers updated")
else:
    print(f"[1/3] WARN: headers not found! Trying broader match...")
    # The file might have slightly different formatting
    import re
    # Find the headers line containing 'CPL Available'
    match = re.search(r"\[\s*'Lane'.*'CPL Available'\s*\]\];", content)
    if match:
        old = match.group(0)
        new = old.replace("'CPL Available']];", "'CPL Available','PPC Ready']];")
        content = content.replace(old, new)
        changes += 1
        print(f"[1/3] Headers updated (regex match)")
    else:
        print(f"[1/3] FAILED: could not find headers")

# 2. Row data: add ppc_ready after CPL Available
old_row = "        l.cpl_available ? 'Yes' : 'No'\n      ]);"
new_row = "        l.cpl_available ? 'Yes' : 'No',\n        l.ppc_ready ? 'Yes' : 'No'\n      ]);"
if old_row in content:
    content = content.replace(old_row, new_row)
    changes += 1
    print(f"[2/3] Row data updated")
else:
    print(f"[2/3] WARN: row data not found! Trying regex...")
    match = re.search(r"        l\.cpl_available \? 'Yes' : 'No'\n      \]\);", content)
    if match:
        old = match.group(0)
        new = "        l.cpl_available ? 'Yes' : 'No',\n        l.ppc_ready ? 'Yes' : 'No'\n      ]);"
        content = content.replace(old, new)
        changes += 1
        print(f"[2/3] Row data updated (regex match)")
    else:
        print(f"[2/3] FAILED: could not find row data")

# 3. Spacer and totals rows (add one more empty field each)
old_spacer = "rows.push(['','','','','','','','','','','','','','','','']);"
new_spacer = "rows.push(['','','','','','','','','','','','','','','','','']);"
if old_spacer in content:
    content = content.replace(old_spacer, new_spacer)
    changes += 1
    print(f"[3a/3] Spacer row updated")
else:
    print(f"[3a/3] WARN: spacer row not found! Trying regex...")
    match = re.search(r"rows\.push\(\[('',){15}\]\);", content)
    if match:
        old = match.group(0)
        new = "rows.push(['','','','','','','','','','','','','','','','','']);"
        content = content.replace(old, new)
        changes += 1
        print(f"[3a/3] Spacer row updated (regex match)")
    else:
        print(f"[3a/3] FAILED: could not find spacer row")

old_totals = "rows.push(['TOTALS','','','','','','','','','','','$'+totalMRR,'$'+avgAcq,'','G:'+g+' A:'+a+' R:'+r,'']);"
new_totals = "rows.push(['TOTALS','','','','','','','','','','','$'+totalMRR,'$'+avgAcq,'','G:'+g+' A:'+a+' R:'+r,'','']);"
if old_totals in content:
    content = content.replace(old_totals, new_totals)
    changes += 1
    print(f"[3b/3] Totals row updated")
else:
    print(f"[3b/3] WARN: totals row not found! Trying regex...")
    match = re.search(r"rows\.push\(\[('TOTALS',)('',){10}('\$'\+totalMRR,)'\$'\+avgAcq,'','G:\+g\+\+ ' A:\+a\+\+ ' R:\+r,''\])\);", content)
    if not match:
        # Try broader search
        for line in content.split('\n'):
            if 'TOTALS' in line and "totalMRR" in line and "avgAcq" in line:
                print(f"[3b/3] Found totals line: {line.strip()}")
                break
    print(f"[3b/3] FAILED: could not update totals row — manual fix needed")

print(f"\nTotal changes: {changes}")
if changes == 4:
    with open('empire_command_spa.py', 'w') as f:
        f.write(content)
    print("File saved successfully!")
else:
    print("Some changes failed — NOT saving file.")
