/**
 * EMPIRE AI V49 — PM2 Ecosystem Config
 * ======================================
 * Manages all PM2-managed services with proper restart limits,
 * graceful shutdown timeouts, and memory limits to prevent
 * crash loops and port conflicts.
 *
 * Apply changes:
 *   pm2 delete ecosystem.config.js   # remove old instance
 *   pm2 start ecosystem.config.js     # start with new config
 *
 * Or hot-reload individual processes:
 *   pm2 restart empire-hub
 *   pm2 restart empire-mesh
 */

module.exports = {
  apps: [
    // ── Empire Hub (FastAPI, port 8000) ──────────────────────────
    {
      name: 'empire-hub',
      script: '/root/empire-v49/hub.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: {
        PYTHONUNBUFFERED: '1',
      },

      // ── Port conflict prevention ──────────────────────────────
      // Time (ms) to wait for the app to start listening.
      // If it doesn't bind within this window, PM2 marks it failed.
      listen_timeout: 30000,

      // ── Graceful shutdown ─────────────────────────────────────
      // After SIGTERM, wait this long before SIGKILL. The hub needs
      // time to close DB connections, finish in-flight requests, etc.
      kill_timeout: 10000,

      // ── Crash-loop prevention ─────────────────────────────────
      // Max consecutive restarts within min_uptime window.
      // After this, PM2 stops trying (status: errored).
      max_restarts: 10,

      // Min uptime (ms) for a restart to count as "successful."
      // If the process crashes faster than this, it's counted toward
      // max_restarts exponentially (PM2's backoff).
      min_uptime: 20000,

      // Delay (ms) between restart attempts (after min_uptime check).
      restart_delay: 2000,

      // Auto-restart if memory exceeds this limit.
      max_memory_restart: '600M',

      // ── Logging ───────────────────────────────────────────────
      error_file: '/root/.pm2/logs/empire-hub-error.log',
      out_file: '/root/.pm2/logs/empire-hub-out.log',
      pid_file: '/root/.pm2/pids/empire-hub.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Empire Mesh (background orchestrator) ───────────────────
    {
      name: 'empire-mesh',
      script: '/root/empire-v49/main.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: {
        PYTHONUNBUFFERED: '1',
      },
      listen_timeout: 15000,
      kill_timeout: 8000,
      max_restarts: 5,
      min_uptime: 10000,
      restart_delay: 3000,
      max_memory_restart: '400M',
      error_file: '/root/.pm2/logs/empire-mesh-error.log',
      out_file: '/root/.pm2/logs/empire-mesh-out.log',
      pid_file: '/root/.pm2/pids/empire-mesh.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
    // ── Hermes Dashboard (port 9119) ───────────────────────────
    {
      name: 'hermes-dashboard',
      script: '/usr/local/bin/hermes',
      args: 'dashboard --port 9119',
      cwd: '/root/.hermes',
      exec_mode: 'fork',
      instances: 1,
      env: {
        HERMES_HOME: '/root/.hermes',
      },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 10,
      min_uptime: 10000,
      restart_delay: 3000,
      max_memory_restart: '500M',
      error_file: '/root/.pm2/logs/hermes-dashboard-error.log',
      out_file: '/root/.pm2/logs/hermes-dashboard-out.log',
      pid_file: '/root/.pm2/pids/hermes-dashboard.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Synthetic Brain (LLM, port 8005) via uvicorn ────────────────
    {
      name: 'synthetic-brain',
      script: '/usr/local/bin/uvicorn',
      args: 'synthetic_brain:app --host 0.0.0.0 --port 8005',
      cwd: '/root/empire-v49',
      exec_mode: 'fork',
      instances: 1,
      env: { PYTHONUNBUFFERED: '1' },
      listen_timeout: 20000,
      kill_timeout: 15000,
      max_restarts: 5,
      min_uptime: 15000,
      restart_delay: 5000,
      max_memory_restart: '2G',
      error_file: '/root/.pm2/logs/synthetic-brain-error.log',
      out_file: '/root/.pm2/logs/synthetic-brain-out.log',
      pid_file: '/root/.pm2/pids/synthetic-brain.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Agent Orchestrator (port 8042) via uvicorn ─────────────────────
    {
      name: 'agent-orchestrator',
      script: '/usr/local/bin/uvicorn',
      args: 'agent_orchestrator:app --host 0.0.0.0 --port 8042',
      cwd: '/root/empire-v49',
      exec_mode: 'fork',
      instances: 1,
      env: { PYTHONUNBUFFERED: '1' },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 10,
      min_uptime: 10000,
      restart_delay: 3000,
      max_memory_restart: '500M',
      error_file: '/root/.pm2/logs/agent-orchestrator-error.log',
      out_file: '/root/.pm2/logs/agent-orchestrator-out.log',
      pid_file: '/root/.pm2/pids/agent-orchestrator.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Hook Analytics (port 8046) ─────────────────────────────────────
    {
      name: 'hook-analytics',
      script: '/root/empire-v49/hook_analytics.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: { PYTHONUNBUFFERED: '1' },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 10,
      min_uptime: 10000,
      restart_delay: 3000,
      max_memory_restart: '300M',
      error_file: '/root/.pm2/logs/hook-analytics-error.log',
      out_file: '/root/.pm2/logs/hook-analytics-out.log',
      pid_file: '/root/.pm2/pids/hook-analytics.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Error Watcher (agent error monitoring → watcher_findings table) ──
    {
      name: 'error-watcher',
      script: '/root/empire-v49/bots/error_watcher.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      args: '--interval 300',
      exec_mode: 'fork',
      instances: 1,
      env: { PYTHONUNBUFFERED: '1' },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 10,
      min_uptime: 10000,
      restart_delay: 5000,
      max_memory_restart: '300M',
      error_file: '/root/.pm2/logs/error-watcher-error.log',
      out_file: '/root/.pm2/logs/error-watcher-out.log',
      pid_file: '/root/.pm2/pids/error-watcher.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Space Reasoner (deep reasoning: Gemini → Claude → Ollama) ──────
    {
      name: 'space-reasoner',
      script: '/root/empire-v49/bots/space_reasoner.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: { PYTHONUNBUFFERED: '1' },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 5,
      min_uptime: 10000,
      restart_delay: 5000,
      max_memory_restart: '500M',
      error_file: '/root/.pm2/logs/space-reasoner-error.log',
      out_file: '/root/.pm2/logs/space-reasoner-out.log',
      pid_file: '/root/.pm2/pids/space-reasoner.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Autonomous Supervisor (loop agent + PM2 health) ────────────────
    {
      name: 'autonomous-supervisor',
      script: '/root/empire-v49/empire_autonomous_supervisor.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: { PYTHONUNBUFFERED: '1' },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 10,
      min_uptime: 10000,
      restart_delay: 5000,
      max_memory_restart: '200M',
      error_file: '/root/.pm2/logs/autonomous-supervisor-error.log',
      out_file: '/root/.pm2/logs/autonomous-supervisor-out.log',
      pid_file: '/root/.pm2/pids/autonomous-supervisor.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Affiliate Recruiter (auto-recruit + nurture affiliates) ────────
    {
      name: 'affiliate-recruiter',
      script: '/root/empire-v49/bots/affiliate_recruiter.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: {
        PYTHONUNBUFFERED: '1',
        AFFILIATE_RECRUITER_INTERVAL: '60',
      },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 5,
      min_uptime: 10000,
      restart_delay: 5000,
      max_memory_restart: '300M',
      error_file: '/root/.pm2/logs/affiliate-recruiter-error.log',
      out_file: '/root/.pm2/logs/affiliate-recruiter-out.log',
      pid_file: '/root/.pm2/pids/affiliate-recruiter.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── SEO Agent (AI-powered SEO optimization loop) ───────────────────
    {
      name: 'seo-agent',
      script: '/root/empire-v49/bots/seo_agent.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      args: '--loop',
      exec_mode: 'fork',
      instances: 1,
      env: {
        PYTHONUNBUFFERED: '1',
        SEO_INTERVAL_HOURS: '6',
      },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 5,
      min_uptime: 10000,
      restart_delay: 5000,
      max_memory_restart: '500M',
      error_file: '/root/.pm2/logs/seo-agent-error.log',
      out_file: '/root/.pm2/logs/seo-agent-out.log',
      pid_file: '/root/.pm2/pids/seo-agent.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ── Traffic Specialist (cross-channel traffic orchestration) ────────
    {
      name: 'traffic-specialist',
      script: '/root/empire-v49/bots/traffic_specialist.py',
      cwd: '/root/empire-v49',
      interpreter: 'python3',
      exec_mode: 'fork',
      instances: 1,
      env: {
        PYTHONUNBUFFERED: '1',
        TRAFFIC_SPECIALIST_INTERVAL: '30',
      },
      listen_timeout: 15000,
      kill_timeout: 10000,
      max_restarts: 5,
      min_uptime: 10000,
      restart_delay: 5000,
      max_memory_restart: '300M',
      error_file: '/root/.pm2/logs/traffic-specialist-error.log',
      out_file: '/root/.pm2/logs/traffic-specialist-out.log',
      pid_file: '/root/.pm2/pids/traffic-specialist.pid',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

  ],
};
