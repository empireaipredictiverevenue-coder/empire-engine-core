"""
EMPIRE V49 - SYNTHETIC BRAIN ORCHESTRATOR WRAPPER
=================================================
Launches the FastAPI synthetic_brain server in-process from the orchestrator
(main.py) so it doesn't need to be started separately with
`uvicorn synthetic_brain:app`.

Lives at bots/synthetic_brain.py so main.py's existing orchestrator pattern
`importlib.import_module("bots.{name}").run()` finds it without any
special-casing in the AGENTS list.

Exposes a `run()` function (same shape as the other bot modules) that:
  1. Validates required env vars (fail-closed: refuses to start without
     SYNTHETIC_BRAIN_API_KEY — we never want to run unauthenticated TTS)
  2. Configures logging to /var/log/empire/synthetic_brain.out.log
  3. Runs uvicorn.Server with synthetic_brain.app in a blocking loop
  4. Installs SIGTERM/SIGINT handlers that flip server.should_exit = True
     for graceful shutdown — gracefully no-ops if called from a non-main
     thread (main.py launches agents in daemon threads)

For PRODUCTION (Hetzner) deploys, prefer deploy/hetzner/start_synthetic_brain.sh
+ the PM2 ecosystem config — those run uvicorn as a real process so it
can be supervised, memory-capped, and log-rotated independently of the
orchestrator.
"""
import os
import sys
import signal
import logging
from pathlib import Path

import uvicorn

# Make project root importable so `import synthetic_brain` works.
# This wrapper lives in bots/ — we add the parent dir of the project root
# (i.e. the project root itself) so the bare `synthetic_brain` module
# (which is the FastAPI app, at the project root) is discoverable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Defaults overridable via env. Production should set:
#   SYNTHETIC_BRAIN_HOST=127.0.0.1  (loopback; Caddy/Nginx fronts it)
#   SYNTHETIC_BRAIN_PORT=8005
HOST = os.environ.get("SYNTHETIC_BRAIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("SYNTHETIC_BRAIN_PORT", "8005"))
# NOTE: when run via uvicorn.Server in-process (this script), only 1 worker
# is possible — the multi-worker pool is a CLI-only feature. For multi-worker
# production, use deploy/hetzner/start_synthetic_brain.sh which exec's
# `uvicorn ... --workers N` and lets uvicorn fork. The single-worker mode
# here is fine for local dev + the in-memory InMemoryStreamRegistry.
# For multi-worker streaming, set REDIS_URL=redis://... and the registry
# auto-switches to RedisStreamRegistry (which shares state across workers).
LOG_LEVEL = os.environ.get("SYNTHETIC_BRAIN_LOG_LEVEL", "info")
WS_MAX_SIZE = int(os.environ.get("SYNTHETIC_BRAIN_WS_MAX_SIZE", str(20 * 1024 * 1024)))

# Import the FastAPI app (side effect: defines the routes + Kokoro singleton)
import synthetic_brain  # noqa: E402


def _validate_env() -> None:
    """Fail-closed: refuse to start if required env vars are missing.

    SYNTHETIC_BRAIN_API_KEY is mandatory — without it, every endpoint is
    unauthenticated. EMPIRE_PUBLIC_BASE_URL is optional (only Vonage cares;
    local dev doesn't need it). OLLAMA_MODEL has a sane default in
    synthetic_brain.py.
    """
    if not os.environ.get("SYNTHETIC_BRAIN_API_KEY"):
        raise RuntimeError(
            "SYNTHETIC_BRAIN_API_KEY env var is not set — refusing to start "
            "an unauthenticated TTS server. Set it in /root/.env or your "
            "process manager before starting the orchestrator."
        )


def _configure_logging() -> None:
    """Route logs to /var/log/empire/synthetic_brain.out.log + stdout.

    Falls back to stdout-only if /var/log/empire isn't writable (e.g. when
    running as a non-root user in a CI test environment).
    """
    handlers: list = [logging.StreamHandler(sys.stdout)]
    try:
        log_dir = Path("/var/log/empire")
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.insert(0, logging.FileHandler(log_dir / "synthetic_brain.out.log"))
    except PermissionError:
        pass
    logging.basicConfig(
        level=LOG_LEVEL.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,  # override any logger config synthetic_brain.py might set at import
    )


def _install_signal_handlers(server: uvicorn.Server, log: logging.Logger) -> None:
    """Install SIGTERM/SIGINT -> server.should_exit handlers.

    Gracefully no-ops if called from a non-main thread (signal.signal()
    raises ValueError there). This happens when main.py launches the
    orchestrator's agents in daemon threads — those threads are killed
    by the daemon when the orchestrator process exits, so explicit
    signal handling isn't needed. The handlers are still useful for
    standalone use (`python3 -m bots.synthetic_brain`) and for the
    Hetzner wrapper script (which runs as a real process).
    """
    def _handle_signal(signum, _frame):
        log.info(
            f"[synthetic_brain] signal {signum} received, "
            f"shutting down gracefully (port {PORT})"
        )
        server.should_exit = True

    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except ValueError:
        log.debug(
            "[synthetic_brain] signal handlers not installed "
            "(non-main thread; daemon-thread kill will handle shutdown)"
        )


def run() -> None:
    """Entry point called by main.py via importlib + mod.run().

    Blocks until server.should_exit is set (either by signal handlers
    or by external code flipping the flag). When launched from main.py's
    daemon-thread pattern, shutdown happens implicitly when the
    orchestrator process exits (daemon threads are killed).
    """
    _validate_env()
    _configure_logging()
    log = logging.getLogger("synthetic_brain.orchestrator")

    config = uvicorn.Config(
        app=synthetic_brain.app,
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL,
        log_config=None,  # we configured our own above
        # Production parity with the Hetzner deploy flags
        proxy_headers=True,
        ws_max_size=WS_MAX_SIZE,
    )
    server = uvicorn.Server(config)
    _install_signal_handlers(server, log)

    log.info(
        f"[synthetic_brain] starting on {HOST}:{PORT} "
        f"(ws_max_size={WS_MAX_SIZE // (1024*1024)}MB, log_level={LOG_LEVEL})"
    )
    # server.run() blocks until server.should_exit is set
    server.run()
    log.info(f"[synthetic_brain] shut down (port {PORT} released)")


if __name__ == "__main__":
    # Standalone use: `python3 -m bots.synthetic_brain`
    # (mostly for debugging — production uses the Hetzner wrapper script)
    run()
