import json

class Pipeline:
    def __init__(self):
        self.dashboard_feed = "/root/empire-v49/data/dashboard_feed.json"
        self.command_log = "/root/empire-v49/strike_history.json"

    def broadcast(self, event_data):
        # 1. Update Dashboard (Read-Only Telemetry)
        with open(self.dashboard_feed, 'w') as f:
            json.dump(event_data, f)
        
        # 2. Update Command Deck (Action/Audit Trail)
        with open(self.command_log, 'a') as f:
            f.write(json.dumps(event_data) + "\n")
