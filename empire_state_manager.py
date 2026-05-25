import json
import os

class StateManager:
    def __init__(self, filename="strike_history.json"):
        self.filename = filename
        self.history = self.load_state()

    def load_state(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                return json.load(f)
        return []

    def log_strike(self, target_id):
        self.history.append(target_id)
        with open(self.filename, "w") as f:
            json.dump(self.history, f)
