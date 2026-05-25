from empire_owner_lookup import get_property_details
from empire_weather_scout import StormTracker

class SniperSatellite:
    def scan_and_identify(self, lat, lon, storm_name):
        tracker = StormTracker()
        if tracker.check_storm_path(storm_name) == "CLEAR":
            return {"status": "NO_STORM_RISK"}
        
        details = get_property_details(lat, lon)
        return {"status": "STRIKE", "details": details, "storm": storm_name}
