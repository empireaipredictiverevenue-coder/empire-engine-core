#!/bin/bash
set -e
cd /root/empire-v49

echo "[DEPLOY] Pulling latest code..."
git pull origin master 2>/dev/null || echo "[DEPLOY] No git remote / already current"

echo "[DEPLOY] Installing dependencies..."
pip install -r requirements.txt --break-system-packages 2>/dev/null || pip install praw beautifulsoup4 requests supabase python-dotenv httpx --break-system-packages

echo "[DEPLOY] Restarting services..."
pm2 restart empire-hub empire-agents

echo "[DEPLOY] Saving PM2 state..."
pm2 save

echo "[DEPLOY] Done. Status:"
pm2 list
