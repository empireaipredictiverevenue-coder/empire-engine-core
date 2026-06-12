"""
EMPIRE V49 · STANDARD AGENT LOGGING
====================================
Single helper for any agent that wants to log to its own per-agent
log file under /root/empire-v49/logs/. Standardizes the format
(timestamp + level + message) and the file naming (agent_<name>.log
or, for backward compat, the existing legacy file name).

Usage:
    from bots.agent_logging import get_logger
    log = get_logger("my_agent")
    log.info("started")
    log.warning("rate-limited, sleeping 5s")

    # The log file is /root/empire-v49/logs/agent_my_agent.log by
    # default. Pass log_file="custom_name.log" to override.

    # The logger also writes to stdout (so existing tail -f behavior
    # in cron / launchd / pm2 keeps working). Use the env var
    # AGENT_LOG_STDOUT=0 to silence stdout if needed.
"""

import logging
import os
import sys
from pathlib import Path


LOG_DIR = Path("/root/empire-v49/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Map legacy log file names so we don't break existing tailers.
LEGACY_NAMES = {
    "bridge":      "bridge.log",           # legacy: bots/mass_tort_bridge.py
    "storm":       "storm_scraper.log",    # legacy: scripts/storm_scraper.py
    "agents":      "agents.log",           # legacy: automate_empire.sh
    "synthetic_brain": "synthetic_brain.log",  # legacy: synthetic_brain.py
}


def get_logger(agent_name: str, *, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    Return a logger that writes to /root/empire-v49/logs/<log_file>
    and stdout. Idempotent: calling get_logger("foo") twice returns
    the same logger (no duplicate handlers).
    """
    logger = logging.getLogger(f"empire.{agent_name}")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fname = log_file or LEGACY_NAMES.get(agent_name) or f"agent_{agent_name}.log"
    fpath = LOG_DIR / fname
    fh = logging.FileHandler(fpath)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Stdout handler (off when AGENT_LOG_STDOUT=0)
    if os.environ.get("AGENT_LOG_STDOUT", "1") != "0":
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    logger.propagate = False  # don't double-log via root
    return logger
