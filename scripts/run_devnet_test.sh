#!/usr/bin/env bash
# run_devnet_test.sh — sourced wrapper for the Solana devnet test.
# Reads SOLANA_RPC_URL from /root/.env and forwards it to the test.
set -a
. /root/.env
set +a
export EMPIRE_SOLANA_NETWORK=devnet
exec /root/sniper_env/bin/python3 /root/empire-v49/scripts/test_solana_payout.py
