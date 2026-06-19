#!/usr/bin/env node
/**
 * screenshot_self_awareness.js — v2
 *
 * Connects to existing headless Chrome (port 9222), sets auth token,
 * navigates to #/self-awareness via hash change (no page reload), waits
 * for React rendering, takes a screenshot.
 *
 * Usage: node scripts/screenshot_self_awareness.js
 */

const puppeteer = require('puppeteer-core');
const CDP_WS_URL = 'http://127.0.0.1:9222/json/version';
const HUB_TOKEN = process.env.HUB_TOKEN || require('fs').readFileSync('/root/.env','utf8')
  .split('\n').find(l=>l.startsWith('HUB_TOKEN=')).split('=').slice(1).join('=').replace(/"/g,'').trim();
const OUTPUT = '/root/empire-v49/screenshots/self_awareness.png';

(async () => {
  // 1. Get WebSocket debugger URL from Chrome
  const http = require('http');
  const wsUrl = await new Promise((resolve, reject) => {
    http.get(CDP_WS_URL, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => { try { resolve(JSON.parse(data).webSocketDebuggerUrl); } catch(e) { reject(e); } });
    }).on('error', reject);
  });

  console.log('Connecting to Chrome...');
  const browser = await puppeteer.connect({
    browserWSEndpoint: wsUrl,
    defaultViewport: { width: 1440, height: 900 },
  });

  const page = await browser.newPage();
  const logs = [];

  page.on('console', msg => logs.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => logs.push(`[PAGE_ERROR] ${err.message}`));
  page.on('response', r => {
    if (r.status() >= 400) logs.push(`[HTTP ${r.status()}] ${r.url().slice(0,120)}`);
  });

  // 2. Navigate to base page first (establishes session, loads SPA shell)
  console.log('Loading SPA shell...');
  await page.goto('http://localhost:8001/command', {
    waitUntil: 'networkidle0',
    timeout: 20000,
  });

  // 3. Set auth token BEFORE navigating to the hash route so apiFetch works
  await page.evaluate((token) => {
    localStorage.setItem('hub_token', token);
  }, HUB_TOKEN);
  console.log('Auth token set in localStorage.');

  // 4. Navigate via hash change — does NOT reload the page, preserves localStorage
  console.log('Navigating to #/self-awareness...');
  await page.evaluate(() => { window.location.hash = '#/self-awareness'; });

  // 5. Wait for React to render the self-awareness dashboard
  //    Look for a specific element that only appears after the SPA renders
  //    the SelfAwarenessDashboard: sa-graph-wrap, sa-status, or the Claude OS title
  try {
    await page.waitForSelector('.sa-graph-wrap, .sa-status, .section-title em', {
      timeout: 15000,
    });
    console.log('Self-awareness dashboard rendered.');
  } catch {
    console.log('Dashboard selector not found — checking page content anyway.');
  }

  // 6. Give a brief extra moment for WebSocket connection + initial narrative
  await new Promise(r => setTimeout(r, 2000));

  // 7. Screenshot
  const fs = require('fs');
  const path = require('path');
  const dir = path.dirname(OUTPUT);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: OUTPUT, fullPage: true });
  console.log(`Screenshot saved to ${OUTPUT}`);

  // 8. Report page content
  const visible = await page.evaluate(() => {
    const el = document.querySelector('.body, #root');
    return el ? el.innerText.slice(0, 2000) : '(no .body or #root found)';
  });
  console.log('\n--- Visible page text ---\n' + visible);

  // 9. Report apiFetch result from the SPA
  const apiResult = await page.evaluate(async () => {
    try {
      const r = await fetch('/api/self-awareness/snapshot', {
        headers: { Authorization: 'Bearer ' + (localStorage.getItem('hub_token') || '') }
      });
      const data = await r.json();
      const agents = (data.system_model?.agents || []).map(a => ({
        name: a.name, status: a.status, capabilities: a.capabilities
      }));
      return { status: r.status, agentCount: agents.length, agents,
        anomalyCount: data.anomaly_count, narrativeHealth: data.narrative?.health };
    } catch(e) {
      return { error: e.message };
    }
  });
  console.log('\n--- API snapshot ---\n' + JSON.stringify(apiResult, null, 2));

  // 10. Console log summary
  console.log('\n--- Console & network logs ---');
  for (const l of logs) console.log(l);

  await page.close();
  await browser.disconnect();
  console.log('\nDone.');
})().catch(err => {
  console.error('Script failed:', err);
  process.exit(1);
});
