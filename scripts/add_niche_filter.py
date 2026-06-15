"""
Add niche filter to the Compare Modes tab in empire_command_spa.py.
1. Add cmpNicheFilter state
2. Add filter buttons between intro and summary
3. Wire filter into the compare table
"""
SPA = "/root/empire-v49/empire_command_spa.py"

with open(SPA, "r") as f:
    src = f.read()

changes = 0

# --- 1. ADD CMP NICHE FILTER STATE ---
old_state = 'const [autoRefresh, setAutoRefresh] = React.useState(false);\n  const [cmpNicheFilter, setCmpNicheFilter] = React.useState'
new_state = 'const [autoRefresh, setAutoRefresh] = React.useState(false);\n  const [cmpNicheFilter, setCmpNicheFilter] = React.useState(null);\n  const [cmpNicheFilter, setCmpNicheFilter] = React.useState'

# Actually, simpler approach: add the state after autoRefresh
old_state = 'const [autoRefresh, setAutoRefresh] = React.useState(false);'
new_state = 'const [autoRefresh, setAutoRefresh] = React.useState(false);\n  const [cmpNicheFilter, setCmpNicheFilter] = React.useState(null);'

if old_state in src:
    src = src.replace(old_state, new_state, 1)
    changes += 1
    print("[OK] Added cmpNicheFilter state")
else:
    print("[WARN] Could not find autoRefresh state")

# --- 2. ADD NICHE FILTER BUTTONS BETWEEN INTRO AND SUMMARY ---
# The gap currently has: </div>\n\n        <div class="cmp-summary">
# We need to insert the filter bar there.
# Let me find the exact location
idx = src.find('cmp-intro')
if idx > 0:
    # Find the closing </div> of the intro
    end_div = src.find('</div>', idx)
    if end_div > 0:
        # Find the next <div after it (the cmp-summary)
        next_div = src.find('<div', end_div)
        if next_div > 0:
            # Insert the filter bar between them
            filter_bar = '''</div>

        <div class="cmp-niche-filter">
          <button class="cmp-niche-btn''' + " ${cmpNicheFilter === null ? 'active' : ''}" + '''" onClick=${() => setCmpNicheFilter(null)}>All</button>
          ${[...new Set(lanes.filter(l => l.cpl_available).map(l => l.niche))].sort().map(n => html`
            <button class="cmp-niche-btn''' + " ${cmpNicheFilter === n ? 'active' : ''}" + '''" onClick=${() => setCmpNicheFilter(n)}>${n}</button>
          `)}
        </div>

        <div class="cmp-summary">'''
            src = src[:end_div] + filter_bar + src[next_div:]
            changes += 1
            print("[OK] Added niche filter buttons")
        else:
            print("[WARN] Could not find next div after intro")
    else:
        print("[WARN] Could not find closing div of intro")
else:
    print("[WARN] Could not find cmp-intro")

# --- 3. FILTER LANES IN THE COMPARE TABLE ---
# The compare tab uses lanes.map() - we need to filter it when cmpNicheFilter is set
# Find the lanes.map inside the compare tab
idx_compare = src.find("tab === 'compare'")
if idx_compare > 0:
    compare_end = src.find("` : ''}", idx_compare)
    compare_section = src[idx_compare:compare_end]
    
    # Find the ${lanes.map(l => { pattern
    old_map = '${lanes.map(l => {'
    new_map = '${(cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes).map(l => {'
    
    if old_map in compare_section:
        # Only replace the one in the compare tab
        src_inner = src[idx_compare:idx_compare + len(compare_section)]
        src_inner = src_inner.replace(old_map, new_map, 1)
        src = src[:idx_compare] + src_inner + src[idx_compare + len(compare_section):]
        changes += 1
        print("[OK] Wired niche filter into compare table")
    else:
        print("[WARN] Could not find lanes.map in compare section")
    
    # Also update the summary card for total lanes to use filtered count
    old_total = '${lanes.length}'
    # We need to only change the one in the compare tab's summary
    # Find it within the compare section
    if '<div class="cmp-card"><div class="cmp-card-label">Total Lanes</div><div class="cmp-card-value">${lanes.length}</div></div>' in compare_section:
        old_total_card = '<div class="cmp-card"><div class="cmp-card-label">Total Lanes</div><div class="cmp-card-value">${lanes.length}</div></div>'
        new_total_card = '<div class="cmp-card"><div class="cmp-card-label">Total Lanes</div><div class="cmp-card-value">${cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter).length : lanes.length}</div></div>'
        
        src_inner = src[idx_compare:idx_compare + len(compare_section)]
        src_inner = src_inner.replace(old_total_card, new_total_card, 1)
        src = src[:idx_compare] + src_inner + src[idx_compare + len(compare_section):]
        changes += 1
        print("[OK] Updated total lanes summary to use filtered count")
    else:
        print("[WARN] Could not find total lanes card in compare tab")
else:
    print("[WARN] Could not find compare tab section")

# --- 4. UPDATE THE OTHER SUMMARY CARDS (Best PPL, Best PPC) TO USE FILTERED DATA ---
idx_compare = src.find("tab === 'compare'")
if idx_compare > 0:
    compare_end = src.find("` : ''}", idx_compare)
    compare_section = src[idx_compare:compare_end]
    
    # Best PPL: use filtered lanes
    old_best_ppl = 'const pplLowest = lanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppl.low != null).map(l => l.cpl.ppl.low); return pplLowest.length ? \'$\' + Math.min(...pplLowest) : \'-\''
    new_best_ppl = 'const pplLanes = cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes; const pplLowest = pplLanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppl.low != null).map(l => l.cpl.ppl.low); return pplLowest.length ? \'$\' + Math.min(...pplLowest) : \'-\''
    
    if old_best_ppl in compare_section:
        src_inner = src[idx_compare:idx_compare + len(compare_section)]
        src_inner = src_inner.replace(old_best_ppl, new_best_ppl, 1)
        src = src[:idx_compare] + src_inner + src[idx_compare + len(compare_section):]
        changes += 1
        print("[OK] Updated Best PPL summary to use filtered lanes")
    else:
        print("[WARN] Could not find Best PPL summary")
    
    # Best PPC: use filtered lanes
    old_best_ppc = 'const ppcLowest = lanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppc && l.cpl.ppc.low != null).map(l => l.cpl.ppc.low); return ppcLowest.length ? \'$\' + Math.min(...ppcLowest) : \'-\''
    new_best_ppc = 'const ppcLanes = cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes; const ppcLowest = ppcLanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppc && l.cpl.ppc.low != null).map(l => l.cpl.ppc.low); return ppcLowest.length ? \'$\' + Math.min(...ppcLowest) : \'-\''
    
    if old_best_ppc in src:
        # Only replace in compare tab
        src_inner = src[idx_compare:idx_compare + len(compare_section)]
        src_inner = src_inner.replace(old_best_ppc, new_best_ppc, 1)
        src = src[:idx_compare] + src_inner + src[idx_compare + len(compare_section):]
        changes += 1
        print("[OK] Updated Best PPC summary to use filtered lanes")
    else:
        print("[WARN] Could not find Best PPC summary")
    
    # Lanes with both: use filtered lanes
    old_both = 'lanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppc).length'
    new_both = '(cmpNicheFilter ? lanes.filter(l => l.niche === cmpNicheFilter) : lanes).filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppc).length'
    
    if old_both in compare_section:
        src_inner = src[idx_compare:idx_compare + len(compare_section)]
        src_inner = src_inner.replace(old_both, new_both, 1)
        src = src[:idx_compare] + src_inner + src[idx_compare + len(compare_section):]
        changes += 1
        print("[OK] Updated Both models summary to use filtered lanes")
    else:
        print("[WARN] Could not find Both models summary")

# --- WRITE ---
with open(SPA, "w") as f:
    f.write(src)

print(f"\nDone -- {changes} changes applied")
