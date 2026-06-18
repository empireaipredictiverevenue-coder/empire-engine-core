/**
 * PREDICITIVE TRADING BOT — PM2 Ecosystem Config
 * ===============================================
 * Two services:
 *   trading-bot      — Full stack (FastAPI on :8050 + stop loss monitor)
 *   trading-stoploss — Stop loss-only (monitor, no API)
 *
 * Apply:
 *   pm2 start ecosystem.config.js
 *
 * Hot-reload individual processes:
 *   pm2 restart trading-bot
 *   pm2 restart trading-stoploss
 *
 * Remove:
 *   pm2 delete trading-bot trading-stoploss
 */

const SHARED = {
  cwd: '/root/empire-v49/the-predicitive-trading-bot',
  interpreter: 'python3',
  exec_mode: 'fork',
  instances: 1,
  env: {
    PYTHONUNBUFFERED: '1',
  },
  kill_timeout: 10000,
  max_restarts: 10,
  min_uptime: 10000,
  restart_delay: 3000,
  merge_logs: true,
  log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
};

module.exports = {
  apps: [
    // ── Trading Bot (API :8050 + stop loss monitor) ──────────────────
    {
      ...SHARED,
      name: 'trading-bot',
      script: 'trading_bot.py',
      // Full stack by default (no flags = API + monitor).
      // Use --stoploss-only or --api-only for single-mode.
      args: '',
      listen_timeout: 30000,
      max_memory_restart: '400M',
      env: {
        ...SHARED.env,
        STOPLOSS_INTERVAL_SEC: '15',
      },
      error_file: '/root/.pm2/logs/trading-bot-error.log',
      out_file: '/root/.pm2/logs/trading-bot-out.log',
      pid_file: '/root/.pm2/pids/trading-bot.pid',
    },

    // ── Stop Loss Monitor (no API) ───────────────────────────────────
    {
      ...SHARED,
      name: 'trading-stoploss',
      script: 'stoploss_bot.py',
      args: '--loop',
      listen_timeout: 15000,
      max_memory_restart: '200M',
      env: {
        ...SHARED.env,
        STOPLOSS_INTERVAL_SEC: '15',
        STOPLOSS_SOLANA_TIMEOUT: '30',
      },
      error_file: '/root/.pm2/logs/trading-stoploss-error.log',
      out_file: '/root/.pm2/logs/trading-stoploss-out.log',
      pid_file: '/root/.pm2/pids/trading-stoploss.pid',
    },
  ],
};
