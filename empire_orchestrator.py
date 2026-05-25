from empire_sniper_satellite import SniperSatellite
from empire_cinematic_engine import launch_3d_render
from empire_state_manager import StateManager

class EmpireOrchestrator:
    def __init__(self):
        self.scout = SniperSatellite()
        self.state = StateManager()

    def run_production_cycle(self, lat, lon, storm):
        intel = self.scout.scan_and_identify(lat, lon, storm)
        if intel.get("status") == "STRIKE":
            target_id = intel['details']['warehouse_name']
            if target_id not in self.state.history:
                launch_3d_render(intel['details'])
                self.state.log_strike(target_id)
            else:
                print(f"SKIP: Already processed {target_id}")

if __name__ == "__main__":
    orchestrator = EmpireOrchestrator()
    orchestrator.run_production_cycle(32.7767, -96.7970, "Tornado-Viper")
