from bots.bot_manager import BotManager
from bots.bot_brain import BotBrain
from bots.linkedin_sniper import LinkedInSniper

# Initialize the stack
brain = BotBrain()
manager = BotManager("LI-SNIPER-01")
bot = LinkedInSniper("LINKEDIN", ["proxy_pool"])

def execute_outreach(lane_id, strategy, niche):
    # 1. BRAIN: Refine strategy for the specific niche
    refined_plan = brain.generate_strategy(niche, lane_id)
    
    # 2. MANAGER: Verify against guardrails
    if manager.validate_action(refined_plan):
        return bot.run(niche, strategy, refined_plan)
    return "FAILED_SAFETY_CHECK"
