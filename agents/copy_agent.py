import json
from local_brain import LocalBrain

class CopyAgent:
    def __init__(self):
        self.brain = LocalBrain(model="qwen2.5-coder:14b")

    def get_past_wins(self):
        # Pulls high-converting patterns from your strike history
        try:
            with open('/root/empire-v49/strike_history.json', 'r') as f:
                return f.read()[:500] # Feed top recent insights
        except:
            return "No previous data."

    def polish(self, draft):
        context = self.get_past_wins()
        system_prompt = f"""
        You are the Chief Copy Officer for Empire AI.
        Learn from these past successes: {context}
        Style: Punchy, motivational, Grade 5-7.
        Constraint: Always Value-Friction-Leverage-Proof-CTA.
        """
        return self.brain.think(f"{system_prompt}\nTarget: {draft}")

    def log_result(self, campaign_id, success):
        # Automatically updates the AI's "memory" after a strike
        with open('/root/empire-v49/strike_history.json', 'a') as f:
            f.write(json.dumps({"id": campaign_id, "win": success}) + "\n")
