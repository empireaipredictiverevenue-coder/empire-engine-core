import json

class BotManager:
    def __init__(self, agent_id=None):
        self.agent_id = agent_id
        self.safety_limit = 85
        print(f"[BOT MANAGER] Online for agent footprint: {self.agent_id}")

    def validate_action(self, action_plan):
        print(f"[BOT MANAGER] Validating action plan type: {type(action_plan)}")
        
        # If the plan arrived as raw text string, safely parse it
        if isinstance(action_plan, str):
            try:
                action_plan = json.loads(action_plan)
            except Exception:
                print("[BOT MANAGER] Fallback: Found raw string, converting to clean dict")
                action_plan = {"persuasion_score": 50, "text": action_plan}
        
        # Safely extract the score using .get() to prevent crashes
        if isinstance(action_plan, dict):
            score = action_plan.get('persuasion_score', 50)
            return score <= self.safety_limit
            
        return True
