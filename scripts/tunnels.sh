#!/usr/bin/env bash
# tunnels.sh — open SSH tunnels from your laptop to the Hetzner box.
# Run this in a terminal on YOUR LAPTOP (not on the box).
# Requires: ssh key at ~/.ssh/hermes_to_server, ssh access as root@5.78.148.141.

set -e
HOST="root@5.78.148.141"
KEY="${HOME}/.ssh/hermes_to_server"
HUB_PORT=18000
HERMES_PORT=19119
BRAIN_PORT=18005
ORCH_PORT=18042

echo "Opening 4 tunnels to $HOST. Leave this terminal open."
echo "  Hub (Empire-AI command SPA):  http://localhost:$HUB_PORT"
echo "  Hermes dashboard:             http://localhost:$HERMES_PORT"
echo "  Synthetic brain (debug):      http://localhost:$BRAIN_PORT"
echo "  Agent orchestrator (debug):   http://localhost:$ORCH_PORT"
echo ""
echo "Open those URLs in your browser. Ctrl-C in THIS terminal to close."
echo ""

# -N: no remote command, -L: local port forward, -g: allow remote hosts (skip; localhost only)
ssh -N \
  -i "$KEY" \
  -L "$HUB_PORT:127.0.0.1:8001" \
  -L "$HERMES_PORT:127.0.0.1:9119" \
  -L "$BRAIN_PORT:127.0.0.1:8005" \
  -L "$ORCH_PORT:127.0.0.1:8042" \
  "$HOST"
