module.exports = {
  apps: [{
    name: "empire-hub",
    script: "/usr/bin/python3",
    args: "-m uvicorn hub:app --host 0.0.0.0 --port 8000 --log-level info",
    cwd: "/root/empire-v49",
    interpreter: "none",
    env: {
      PYTHONPATH: "/root/empire-v49",
      PUBLIC_BASE_URL: "https://empire-ai.co.uk",
      EMPIRE_PUBLIC_BASE_URL: "https://empire-ai.co.uk",
      HUB_URL: "http://127.0.0.1:8000",
      SECRET_KEY: "empire-rotate-this-to-a-long-random-string"
    },
    out_file: "/root/.pm2/logs/empire-hub-out.log",
    error_file: "/root/.pm2/logs/empire-hub-error.log",
    max_memory_restart: "3G",
    autorestart: true,
    restart_delay: 5000
  }]
};
