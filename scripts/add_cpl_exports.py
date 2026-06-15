"""
Add CSV/PDF export buttons to the CplPricing component in empire_command_spa.py.
Uses pure client-side JS for CSV and window.print() for PDF — zero dependencies.
"""
SPA = "/root/empire-v49/empire_command_spa.py"

with open(SPA, "r") as f:
    src = f.read()

changes = 0

# --- 1. ADD EXPORT CSS & PRINT STYLES ------------------------------------
# Insert before the closing """ of _SPA_CSS
old_css_marker = "/* -- ROI CALCULATOR ---------------------------------------------- */"
new_css = """
/* -- EXPORT BUTTONS --------------------------------------------- */
.cpl-export-bar{display:flex;gap:6px;align-items:center}
.cpl-export-btn{padding:6px 14px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap);display:flex;align-items:center;gap:5px}
.cpl-export-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal);background:var(--signal-teal-soft)}
.cpl-export-btn svg{width:14px;height:14px;opacity:0.7}
.cpl-export-btn:hover svg{opacity:1}
/* -- PRINT STYLES ------------------------------------------------- */
@media print{@page{size:landscape;margin:12mm}body{background:#fff!important;color:#000!important}.cpl-header{margin-bottom:10px!important}.cpl-header h2{font-size:14px!important;color:#000!important}.cpl-tabs,.cpl-nav,.cpl-pagination,.cpl-export-bar,.sidebar,.nav-panel,.section-h>div:not(.section-h){display:none!important}.cpl-table{width:100%!important;border-collapse:collapse!important;font-size:9px!important}.cpl-table th{background:#f0f0f0!important;color:#333!important;padding:4px 6px!important;border:1px solid #ccc!important;text-transform:uppercase!important}.cpl-table td{padding:3px 6px!important;border:1px solid #ddd!important;color:#333!important}.cpl-table tr.seo-row td{opacity:0.4!important}.cpl-badge{border:1px solid #999!important;padding:1px 4px!important;font-size:8px!important;border-radius:2px!important}.cpl-badge.ppl{border-color:#00c8c8!important;color:#009999!important}.cpl-badge.ppc{border-color:#ffb700!important;color:#cc9200!important}.cpl-badge.service{border-color:#8264ff!important;color:#6a4fcc!important}.cpl-margin-bar{border:1px solid #999!important;height:4px!important}.cpl-card{background:#f8f8f8!important;border:1px solid #ddd!important;padding:6px 10px!important}.cpl-card-value{font-size:14px!important;color:#000!important}.cpl-card-label{color:#666!important}.cpl-summary{margin-bottom:10px!important;gap:8px!important}.cpl-loading,.cpl-error{display:none!important}}
"""

if old_css_marker in src:
    idx = src.find(old_css_marker)
    # Insert the new CSS before the ROI CALCULATOR comment
    src = src[:idx] + new_css + src[idx:]
    changes += 1
    print("[OK] Added export CSS and print styles")
else:
    print("[WARN] Could not find CSS marker")

# --- 2. ADD CSV EXPORT FUNCTION INSIDE CplPricing COMPONENT --------------
# Add after the roiClass function definition
old_roi_class = "  const roiClass = (v) => v > 0 ? 'profit' : v < 0 ? 'loss' : 'neutral';"
new_export_fns = """  const roiClass = (v) => v > 0 ? 'profit' : v < 0 ? 'loss' : 'neutral';

  // -- CSV export ---------------------------------------------------------
  const exportCSV = () => {
    const rows = [['Lane','Niche','Sub-Niche','CPL Low','CPL High','Model','Sell Price Low','Sell Price High','Margin %','Annual Revenue','CPL Available']];
    lanes.forEach(l => {
      rows.push([
        'L'+String(l.lane_id).padStart(2,'0'),
        l.niche,
        l.sub_niche,
        l.cpl_available ? String(l.cpl_low) : 'N/A',
        l.cpl_available ? String(l.cpl_high) : 'N/A',
        l.best_model || 'n/a',
        l.cpl_available ? String(l.sell_price_low) : 'N/A',
        l.cpl_available ? String(l.sell_price_high) : 'N/A',
        l.cpl_available ? String(l.margin_pct) : 'N/A',
        l.cpl_available ? String(l.annual_revenue || 0) : 'N/A',
        l.cpl_available ? 'Yes' : 'No'
      ]);
    });
    const csv = rows.map(r => r.map(c => '"' + String(c).replace(/"/g,'""') + '"').join(',')).join('\\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'empire_cpl_pricing.csv';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  // -- PDF / Print --------------------------------------------------------
  const exportPDF = () => { window.print(); };"""

if old_roi_class in src:
    src = src.replace(old_roi_class, new_export_fns)
    changes += 1
    print("[OK] Added CSV/PDF export functions")
else:
    print("[WARN] Could not find roiClass function")

# --- 3. ADD EXPORT BUTTONS IN HEADER ------------------------------------
# Replace the header div with export buttons
old_header = """        <div class="cpl-header">
        <h2 style="margin:0;font-size:16px;font-weight:600">CPL Pricing</h2>
        <div class="cpl-tabs">"""
new_header = """        <div class="cpl-header">
        <h2 style="margin:0;font-size:16px;font-weight:600">CPL Pricing</h2>
        <div class="cpl-export-bar">
          <button class="cpl-export-btn" onClick=${exportCSV} title="Download CSV">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            CSV
          </button>
          <button class="cpl-export-btn" onClick=${exportPDF} title="Print / Save as PDF">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            PDF
          </button>
        </div>
        <div class="cpl-tabs">"""

if old_header in src:
    src = src.replace(old_header, new_header)
    changes += 1
    print("[OK] Added export buttons in header")
else:
    print("[WARN] Could not find header div")

# --- WRITE -----------------------------------------------------------------
with open(SPA, "w") as f:
    f.write(src)

print(f"\nDone -- {changes} changes applied")
