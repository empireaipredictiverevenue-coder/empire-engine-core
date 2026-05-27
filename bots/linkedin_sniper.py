from empire_bot_base import EmpireBot

class LinkedInSniper(EmpireBot):
    def run(self, niche, intensity, instruction):
        print(f"[LINKEDIN] Searching for {niche} decision makers...")
        return self.execute(niche, intensity, instruction)
