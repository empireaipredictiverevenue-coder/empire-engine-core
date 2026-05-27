import requests
import time
import os

# CONFIG: Targeted Zones (Dallas/Fort Worth & New Orleans)
TARGET_ZONES = ["TXC113", "LAC071"] # Dallas County & Orleans Parish

def check_weather():
    print("📡 SENTRY: Scanning the skies over the Empire...")
    url = "https://api.weather.gov/alerts/active"
    try:
        response = requests.get(url, headers={"User-Agent": "EmpireAI-Sovereign-Lab"})
        alerts = response.json().get('features', [])
        
        for alert in alerts:
            props = alert.get('properties', {})
            event = props.get('event', '').upper()
            zone = props.get('geocode', {}).get('UGC', [])
            
            # TRIGGER: If Hail or Flood is detected in our zones
            if any(z in zone for z in TARGET_ZONES):
                if "HAIL" in event or "THUNDERSTORM" in event or "FLOOD" in event:
                    print(f"🔥 ALERT DETECTED: {event} in {zone}")
                    return True, event
                    
    except Exception as e:
        print(f"❌ SENTRY ERROR: {e}")
    return False, None

if __name__ == "__main__":
    while True:
        hit, event_type = check_weather()
        if hit:
            print(f"🚀 TRIGGERING THE SWARM: {event_type}")
            # 1. RUN THE SATELLITE SCOUT
            os.system("/root/sniper_env/bin/python3 /root/empire-app/satellite_scout.py")
            # 2. RUN THE SMS SNIPER
            os.system("/root/sniper_env/bin/python3 /root/empire-app/sms_blast.py")
            
            print("💤 SWARM DEPLOYED. Cooling down for 1 hour...")
            time.sleep(3600) # Don't spam the same storm
        else:
            print("☁️ SKY IS CLEAR. Waiting 15 minutes...")
            time.sleep(900)
