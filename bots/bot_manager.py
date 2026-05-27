class BotManager:
    def __init__(self, bot_id):
        self.bot_id = bot_id
        self.safety_limit = 0.95 # Guardrail: Max persuasion threshold

    def validate_action(self, action_plan):
        # GUARDRAILS: Check against safety limits
        if action_plan['persuasion_score'] > self.safety_limit:
            print(f"[MANAGER-{self.bot_id}] ACTION REJECTED: Safety Guardrail Triggered.")
            return False
        return True

    def execute(self, bot_instance, task):
        if self.validate_action(task):
            return bot_instance.run(task)
        return "BLOCKED"
