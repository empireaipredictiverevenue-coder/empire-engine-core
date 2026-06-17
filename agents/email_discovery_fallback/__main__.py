import sys, argparse
sys.path.insert(0, "/root/empire-v49")
from agents.email_discovery_fallback.email_discovery import run
p = argparse.ArgumentParser()
p.add_argument("--max-per-run", type=int, default=500)
args = p.parse_args()
result = run(max_per_run=args.max_per_run)
print(f"FINAL: {result}")
