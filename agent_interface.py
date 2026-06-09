import sys
sys.path.append('/root/empire-v49/bots')
from bot_manager import BotManager
from mass_tort_scout import fetch_latest_recall

def execute_outreach(lane_id, strategy, niche_name):
    # Initialize the bot manager with the sniper footprint
    manager = BotManager("LI-SNIPER-01")
    
    # Intercept lanes 16-20 or any lane tagged Mass Tort
    if "Mass Tort" in str(niche_name) or lane_id in [16, 17, 18, 19, 20]:
        live_recall = fetch_latest_recall()
        device = live_recall.get('device', 'Recalled Medical Device')
        reason = live_recall.get('reason', 'Product Defect')
        
        print(f"[LANE {lane_id}] MASS TORT SNIPER LAUNCHED | Strategy: {strategy}")
        print(f"[TARGET DEVICE] {device}")
        print(f"[TRIGGER REASON] {reason}")
        return f"Mass Tort Campaign live for {device}."
        
    print(f"[LANE {lane_id}] Running standard campaign for: {niche_name} | Strategy: {strategy}")
    return "Standard campaign active."

if __name__ == "__main__":
    # Quick internal sanity check
    execute_outreach(16, "AGGRESSIVE_STRIKE", "Mass Tort")
