# Facebook Messenger + Chatwoot Setup Guide

This guide walks through the complete setup of Facebook Messenger integration
with your self-hosted Chatwoot instance for the Empire AI Facebook page.

---

## Step 1: Create a Facebook App

1. Go to **[developers.facebook.com](https://developers.facebook.com/)**
2. Click **My Apps** → **Create App**
3. Select **"Business"** as the app type
4. App name: **`Empire AI Messenger`**
5. Contact email: your email
6. Click **Create App**

### After creation:

1. In the app dashboard, go to **Settings** → **Basic**
2. Note down:
   - **App ID** (looks like: `1234567890123456`)
   - **App Secret** (click **Show**)

---

## Step 2: Add Messenger Product

1. In left sidebar, scroll to **Products** section
2. Find **Messenger** and click **Set Up**
3. This adds Messenger settings to your app

---

## Step 3: Generate Page Access Token

1. In Messenger settings, find **Access Tokens** section
2. Click **"Add or Remove Pages"**
3. A Facebook Login dialog appears — grant access to your **Empire AI Facebook Page**
4. Back in the Access Tokens section, click **"Generate Token"** next to your page
5. **Copy the token immediately** — it looks like:
   `EAAx...long-string...ZD`
6. Store it safely — you'll need it for Step 7

---

## Step 4: Configure Webhook in Facebook App

1. In Messenger settings, find the **Webhooks** section
2. Click **"Add Callback URL"**
3. Enter:
   - **Callback URL:** `https://chat.empire-ai.co.uk/bot`
   - **Verify Token:** Use the same `FB_VERIFY_TOKEN` you set in `.env.chatwoot`
4. Click **"Verify and Save"**
5. After verification, under **"Webhook Subscriptions"** → **Page** section:
   - Click **"Manage Subscription"**
   - Subscribe to these fields:
     - `messages` — required
     - `messaging_postbacks` — required
     - `message_deliveries`
     - `message_reads`
     - `message_echoes`
   - Click **Save**

---

## Step 5: Deploy Chatwoot with Facebook Credentials

Edit `deploy/chatwoot/.env` with your Facebook App credentials:

```bash
cd deploy/chatwoot
cp .env.chatwoot .env
nano .env
```

Set these values:
```
FB_APP_ID=your-app-id-from-step-1
FB_APP_SECRET=your-app-secret-from-step-1
FB_VERIFY_TOKEN=a-random-string-you-create-this
```

Then deploy:
```bash
docker compose up -d
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose restart rails
```

---

## Step 6: Connect Facebook Page in Chatwoot

1. Open **http://localhost:8093** (or your Chatwoot URL)
2. Create your admin account
3. Go to **Settings** → **Inboxes** → **Add Inbox**
4. Select **"Messenger"** (Facebook Messenger)
5. Click **"Login with Facebook"**
6. Authorize your Facebook Page
7. Chatwoot will create the Facebook Messenger channel
8. Note the **inbox ID** (numeric, from the URL when viewing the inbox)

---

## Step 7: Create Chatwoot API Access Token

1. In Chatwoot, go to **Settings** → **Profile** → **Access Tokens**
2. Click **"Generate Token"**
3. Name it: **`Empire Facebook Bot`**
4. Copy the token

---

## Step 8: Configure Empire AI Environment

Now set the Chatwoot credentials in Empire AI's environment so our
Facebook bot can communicate with Chatwoot:

```bash
cat >> /root/.env << 'EOF'

# Chatwoot
CHATWOOT_ENABLED=true
CHATWOOT_URL=http://localhost:8093
CHATWOOT_ACCESS_TOKEN=your-chatwoot-api-token-from-step-7
CHATWOOT_ACCOUNT_ID=1
CHATWOOT_API_ACCESS_TOKEN=your-chatwoot-api-token-from-step-7
EOF
```

Then restart the hub:
```bash
pm2 restart empire-hub
```

---

## Step 9: Configure Chatwoot Webhook to Empire AI Bot

1. In Chatwoot, go to **Settings** → **Webhooks**
2. Click **"Add Webhook"**
3. URL: **`https://empire-ai.co.uk/webhook/facebook-bot`**
4. Subscribe to: **`message_created`**
5. Click **"Save"**

Now when someone messages the Empire AI Facebook page:
1. Facebook → Chatwoot (via Facebook Messenger API)
2. Chatwoot → `/webhook/facebook-bot` (webhook event)
3. Empire Facebook Bot processes the message
4. Reply sent back through Chatwoot API → Facebook Messenger

---

## Step 10: Verify the Setup

Send a test message to your Facebook Page and check:

1. The message appears in Chatwoot inbox
2. The bot replies within a few seconds
3. Check logs:
   ```bash
   pm2 logs empire-hub --lines 50 | grep -i facebook
   ```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Invalid App ID" | FB_APP_ID wrong | Check in Facebook Developers → Settings → Basic |
| Webhook verification fails | FB_VERIFY_TOKEN mismatch | Must be identical in .env and Facebook Webhook config |
| Messages not arriving | Webhook URL wrong | Chatwoot webhook must be `https://chat.empire-ai.co.uk/bot` |
| Bot not replying | CHATWOOT_ENABLED not set | `export CHATWOOT_ENABLED=true` in /root/.env |
| "403 Forbidden" | Page Access Token expired | Regenerate in Facebook Developer → Messenger settings |
| Chatwoot not starting | Port conflict | Port 8093 might be in use — check `ss -tlnp \| grep 8093` |

---

## Nginx Subdomain (Optional)

To expose Chatwoot via `chat.empire-ai.co.uk`:

1. Add to the nginx config:
```nginx
server {
    listen 80;
    server_name chat.empire-ai.co.uk;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name chat.empire-ai.co.uk;

    ssl_certificate /etc/letsencrypt/live/empire-ai.co.uk/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/empire-ai.co.uk/privkey.pem;

    underscores_in_headers on;

    location / {
        proxy_pass http://127.0.0.1:8093;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

2. Expand the SSL cert:
```bash
certbot --expand -d empire-ai.co.uk -d www.empire-ai.co.uk -d chat.empire-ai.co.uk
```

3. Activate the config:
```bash
ln -sf /root/empire-v49/deploy/nginx-empire-chatwoot.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```
