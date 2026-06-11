// Empire AI — production PM2 config for Hetzner
// Usage:
//     cd /root/empire-v49
//     pm2 start deploy/hetzner/ecosystem.config.js
//     pm2 save
//     pm2 startup   # follow the printed command for boot persistence
//
// Environment is loaded from /root/.env (loaded by uvicorn's start_synthetic_brain.sh
// wrapper script) and from inline env blocks below.

module.exports = {
  apps: [
    {
      name: 'synthetic_brain',
      // uvicorn is installed via pip; the wrapper script sets the env first
      // so SYNTHETIC_BRAIN_API_KEY + OLLAMA_MODEL are present.
      script: 'deploy/hetzner/start_synthetic_brain.sh',
      // Restart on crash + cap memory so a runaway model load doesn't OOM
      autorestart: true,
      max_memory_restart: '2G',
      // uvicorn logs go here; PM2 rotates them
      out_file: '/var/log/empire/synthetic_brain.out.log',
      error_file: '/var/log/empire/synthetic_brain.err.log',
      time: true,
    },
    {
      name: 'voice_streaming_agent',
      script: 'deploy/hetzner/start_voice_streaming_agent.sh',
      autorestart: true,
      max_memory_restart: '1G',
      out_file: '/var/log/empire/voice_streaming_agent.out.log',
      error_file: '/var/log/empire/voice_streaming_agent.err.log',
      time: true,
    },
  ],
};
