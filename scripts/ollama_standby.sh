#!/bin/bash
# Ollama standby helper.
#   bash scripts/ollama_standby.sh on     - enable + start (the brain comes back)
#   bash scripts/ollama_standby.sh off    - stop + disable (saves 2 CPU + 9.6GB RAM)
#   bash scripts/ollama_standby.sh status  - show whether it's running
#
# Use ON when you actually need predictive_revenue / matrix services.
# Use OFF when you don't - the hub only does a health check on ollama,
# and the niche pages / map / pulse / multi-touch cadence / storm webhook
# all work without it.
set -e
case "${1:-status}" in
  on)
    sudo systemctl enable --now ollama
    echo "ollama starting..."
    for i in 1 2 3 4 5 6 7 8 9 10; do
      curl -s -f -m 2 http://localhost:11434/api/tags >/dev/null 2>&1 && { echo "ready"; exit 0; }
      sleep 1
    done
    echo "ollama didn't come up in 10s. check: journalctl -u ollama -n 30"
    exit 1
    ;;
  off)
    sudo systemctl disable --now ollama 2>/dev/null || true
    pkill -9 -f llama-server 2>/dev/null || true
    echo "ollama stopped. 2 CPU + 9.6GB RAM freed."
    echo "bring it back: bash scripts/ollama_standby.sh on"
    ;;
  status)
    if pgrep -f "ollama serve" >/dev/null 2>&1; then
      echo "ollama: RUNNING"
      pgrep -af llama-server | head -5
      echo "models:"
      curl -s -m 2 http://localhost:11434/api/tags 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); [print('  '+m['name']) for m in d.get('models',[])]" 2>/dev/null
    else
      echo "ollama: STOPPED (standby)"
      echo "  bring it back: bash scripts/ollama_standby.sh on"
    fi
    ;;
  *)
    echo "usage: $0 {on|off|status}"
    exit 1
    ;;
esac