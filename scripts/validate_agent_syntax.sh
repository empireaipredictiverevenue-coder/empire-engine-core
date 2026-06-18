#!/bin/bash
# Validate syntax for all modified cron agent files
set -e
cd /root/empire-v49

files=(
  agents/event_emitter.py
  agents/lead_scanner/scanner.py
  agents/lead_enricher/enricher.py
  agents/lead_converter/converter.py
  agents/dispatch/dispatcher.py
  agents/prospector/prospector.py
  agents/prospector_bridge/prospector_bridge.py
  agents/contractor_outreach/outreach.py
  agents/retarget/retarget.py
  agents/warp_scout/warp_scout.py
)

all_ok=true
for f in "${files[@]}"; do
  if python3 -c "import ast; ast.parse(open('$f').read())" 2>&1; then
    echo "OK: $f"
  else
    echo "FAIL: $f"
    all_ok=false
  fi
done

if $all_ok; then
  echo "=== ALL FILES OK ==="
else
  echo "=== SOME FILES FAILED ==="
  exit 1
fi
