from empire_override import get_manual_override
from empire_si_core import SyntheticIntelligence

class AGIGovernor:
    def __init__(self):
        self.si = SyntheticIntelligence()

    def direct_strategy(self):
        # 1. Check for human intervention
        status = get_manual_override()
        if status.get("mode") == "MANUAL":
            return status.get("strategy", "HOLD")

        # 2. Autonomous AGI Decisioning
        print("[AGI GOVERNOR] Autonomous mode active.")
        return "AGGRESSIVE_STRIKE"

governor = AGIGovernor()
print(f"[AGI] Current Strategy: {governor.direct_strategy()}")

def get_local_brain(task_type):
    """
    Routes tasks to the optimal local model based on intent.
    qwen2.5-coder:14b: Complex Architecture & Code
    llama3.1:latest: Strategic Logic & Negotiation
    llama3.2:3b: High-Speed Outreach & Mining
    """
    if task_type == "code":
        return "qwen2.5-coder:14b"
    elif task_type == "negotiation":
        return "llama3.1:latest"
    else:
        return "llama3.2:3b"

print(f"[GOVERNOR] Brain routing initialized. Ready to execute Strategy Strike.")
