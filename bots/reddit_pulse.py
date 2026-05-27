from empire_bot_base import EmpireBot

class RedditPulse(EmpireBot):
    def run(self, niche, intensity, instruction):
        print(f"[REDDIT] Mining subreddits for '{niche}' intent...")
        return self.execute(niche, intensity, instruction)
