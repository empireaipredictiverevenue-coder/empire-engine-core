#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# EMPIRE PORT HEALTH CHECKER
# ══════════════════════════════════════════════════════════════════════
# Diagnoses port conflicts, finds orphaned process holders,
# and cleans up stale ports so services can start cleanly.
#
# Usage:
#   ./check_ports.sh                 # check all empire ports
#   ./check_ports.sh --clean         # kill orphaned processes
#   ./check_ports.sh --port 8000     # check a specific port
#   ./check_ports.sh --json          # machine-readable output
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

CLEAN=false
JSON=false
TARGET_PORT=""

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=true ;;
    --json) JSON=true ;;
    --port=*) TARGET_PORT="${arg#*=}" ;;
    --port) echo "Use --port=8000"; exit 1 ;;
    --help)
      echo "Empire Port Health Checker"
      echo "  ./check_ports.sh              — check all empire ports"
      echo "  ./check_ports.sh --clean       — kill orphaned processes"
      echo "  ./check_ports.sh --port=8000   — check one port"
      echo "  ./check_ports.sh --json        — machine-readable output"
      exit 0 ;;
  esac
done

# ── Known empire services ──────────────────────────────────────────
declare -A SERVICE_PORTS
SERVICE_PORTS[8000]="empire-hub (FastAPI)"
SERVICE_PORTS[8005]="synthetic_brain (Ollama LLM)"
SERVICE_PORTS[8010]="matrix-sovereign-agi"
SERVICE_PORTS[8020]="matrix-strategy-roi"
SERVICE_PORTS[8030]="matrix-landing"
SERVICE_PORTS[8040]="matrix-universal"
SERVICE_PORTS[8045]="matrix-ppc-inbound"
SERVICE_PORTS[8042]="agent-orchestrator"
SERVICE_PORTS[8046]="hook-analytics"
SERVICE_PORTS[9222]="chrome-headless"
SERVICE_PORTS[11434]="ollama"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

TOTAL_PORTS=0
OK_PORTS=0
WARN_PORTS=0
ERROR_PORTS=0
ORPHANS=()

check_port() {
  local port="$1"
  local service="${SERVICE_PORTS[$port]:-unknown}"
  TOTAL_PORTS=$((TOTAL_PORTS + 1))

  # Check if anything is listening on this port
  local listener
  listener=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -v "State" | head -1)

  if [ -z "$listener" ]; then
    # Port is free
    if [ "$JSON" = true ]; then
      echo "{\"port\":$port,\"service\":\"$service\",\"status\":\"free\",\"pid\":null,\"process\":null}"
    else
      echo -e "  ${GREEN}✓${NC}  Port $port  ${CYAN}$service${NC}  — free"
    fi
    OK_PORTS=$((OK_PORTS + 1))
    return 0
  fi

  # Parse the listener to get PID and process name
  local pid_process
  pid_process=$(echo "$listener" | awk '{for(i=1;i<=NF;i++) if($i ~ /pid=/) print $i}' | sed 's/.*pid=\([0-9]*\).*/\1/' | sed 's/,/ /')
  local pid="${pid_process%% *}"
  local proc_name=""
  
  if [ -n "$pid" ] && [ "$pid" != "-" ]; then
    proc_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
    # Check if it's a PM2-managed process (look up by port, not PID)
    local pm2_name=""
    case "$port" in
      8000) pm2_name="empire-hub" ;;
      8005) pm2_name="synthetic_brain" ;;
      8042) pm2_name="agent-orchestrator" ;;
      8046) pm2_name="hook-analytics" ;;
    esac
    if [ -n "$pm2_name" ]; then
      local pm2_status
      pm2_status=$(pm2 show "$pm2_name" 2>/dev/null | grep "status" | awk '{print $NF}' || echo "unknown")
      if [ -n "$pm2_status" ] && [ "$pm2_status" != "unknown" ]; then
        proc_name="$proc_name (PM2: $pm2_name, status: $pm2_status)"
      fi
    fi
  fi

  # Determine if this port is correctly occupied
  local expected_pm2=""
  case "$port" in
    8000) expected_pm2="empire-hub" ;;
    8005) expected_pm2="synthetic_brain" ;;
    *) expected_pm2="" ;;
  esac

  local status="ok"
  local status_msg="occupied by $proc_name (pid $pid)"
  
  if [ -n "$expected_pm2" ]; then
    # Check if PM2 says this process should be running
    local pm2_status
    pm2_status=$(pm2 show "$expected_pm2" 2>/dev/null | grep "status" | awk '{print $NF}' || echo "unknown")
    if [ "$pm2_status" = "online" ]; then
      status="ok"
    elif [ "$pm2_status" = "errored" ] || [ "$pm2_status" = "stopped" ]; then
      status="orphan"
      ORPHANS+=("$port:$pid:$expected_pm2")
      status_msg="ORPHAN — $expected_pm2 is $pm2_status but port $port is held by pid $pid"
    fi
  fi

  if [ "$status" = "orphan" ]; then
    if [ "$JSON" = true ]; then
      echo "{\"port\":$port,\"service\":\"$service\",\"status\":\"orphan\",\"pid\":$pid,\"process\":\"$proc_name\",\"pm2_name\":\"$expected_pm2\"}"
    else
      echo -e "  ${YELLOW}⚠${NC}  Port $port  ${CYAN}$service${NC}  — $status_msg"
    fi
    WARN_PORTS=$((WARN_PORTS + 1))
  else
    if [ "$JSON" = true ]; then
      echo "{\"port\":$port,\"service\":\"$service\",\"status\":\"occupied\",\"pid\":$pid,\"process\":\"$proc_name\"}"
    else
      echo -e "  ${GREEN}✓${NC}  Port $port  ${CYAN}$service${NC}  — $status_msg"
    fi
    OK_PORTS=$((OK_PORTS + 1))
  fi
}

# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

echo ""
if [ "$JSON" = false ]; then
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     EMPIRE PORT HEALTH CHECKER                          ║"
  echo "║     Detects conflicts and orphaned port holders        ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
fi

if [ -n "$TARGET_PORT" ]; then
  # Single port mode
  check_port "$TARGET_PORT"
else
  # Check all known ports in sorted order
  for port in $(echo "${!SERVICE_PORTS[@]}" | tr ' ' '\n' | sort -n); do
    check_port "$port"
  done
fi

# ── Clean up orphans if --clean flag is set ────────────────────────
if [ "$CLEAN" = true ] && [ ${#ORPHANS[@]} -gt 0 ]; then
  if [ "$JSON" = false ]; then
    echo ""
    echo "─── Cleaning orphaned processes ───"
  fi
  for orphan in "${ORPHANS[@]}"; do
    local port="${orphan%%:*}"
    local rest="${orphan#*:}"
    local pid="${rest%%:*}"
    local pm2_name="${rest#*:}"
    if [ -n "$pid" ] && [ "$pid" != "-" ]; then
      if [ "$JSON" = true ]; then
        echo "{\"action\":\"killed\",\"port\":$port,\"pid\":$pid}"
      else
        echo -e "  ${YELLOW}✗${NC}  Killing pid $pid (was holding port $port for $pm2_name)"
      fi
      kill "$pid" 2>/dev/null || true
      sleep 0.5
      # Verify it's gone
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        if [ "$JSON" = false ]; then
          echo -e "  ${RED}✗${NC}  Had to force-kill pid $pid (SIGKILL)"
        fi
      fi
    fi
  done
elif [ "$CLEAN" = true ] && [ ${#ORPHANS[@]} -eq 0 ]; then
  if [ "$JSON" = false ]; then
    echo ""
    echo "  No orphaned processes to clean."
  fi
fi

# ── Summary ────────────────────────────────────────────────────────
if [ "$JSON" = false ]; then
  echo ""
  echo "─── Summary ───"
  echo -e "  ${GREEN}${OK_PORTS}${NC} ports OK  ·  ${YELLOW}${WARN_PORTS}${NC} warnings  ·  ${RED}${ERROR_PORTS}${NC} errors"
  if [ ${#ORPHANS[@]} -gt 0 ]; then
    echo ""
    echo -e "  ${YELLOW}⚠  ${#ORPHANS[@]} orphaned process(es) detected${NC}"
    echo "  Run: ./check_ports.sh --clean"
  fi
  echo ""
fi

exit $ERROR_PORTS
