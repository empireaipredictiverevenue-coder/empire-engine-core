class LocalBrain:
    def __init__(self, model="qwen2.5-coder:14b"):
        self.model = model

    def think(self, prompt):
        # In production, this calls your Ollama/local model
        # Returning a formatted string to simulate the AI response
        return f"[THINKING with {self.model}] Strategy: Focus on ROI. Hook: Stop bleeding cash on bad leads. Leverage: Our 32-lane mesh fills your calendar."
