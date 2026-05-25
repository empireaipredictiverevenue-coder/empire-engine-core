class StormTracker:
    def __init__(self):
        self.active_storms = ["Tornado-Viper", "Storm-Front-Omega"]

    def check_storm_path(self, storm_name):
        if storm_name in self.active_storms:
            return f"TRACKING: {storm_name}"
        return "CLEAR"
