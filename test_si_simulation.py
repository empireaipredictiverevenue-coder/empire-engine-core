from empire_si_core import SyntheticIntelligence

# 1. Initialize the Synthetic Intelligence Core
si_engine = SyntheticIntelligence()

# 2. Simulate a high-intent lead in a storm zone (2 wins, 1 loss for demo data)
lead_data = {"id": "test-lead-001", "intent_score": 9, "city": "Dallas"}
print(f"[TEST] Simulating dispatch for: {lead_data['id']}...")

# 3. SI Core: Pre-flight Prediction using Bayesian beta-binomial model
prediction = si_engine.simulate_strategy(
    strategy_name="AGGRESSIVE_STRIKE",
    wins=2,
    losses=1,
    revenue=1500.0,
    n_opportunities=10,
)
print(f"[SI RESULT] win_rate={prediction['win_rate']['mean']:.1%} "
      f"EV=${prediction['expected_revenue']['expected']:.0f} "
      f"recommendation={prediction['recommendation']}")

# 4. Feedback Test: Calibrate using prediction-outcome pairs
feedback = si_engine.evolve_logic({
    "predictions": [0.7, 0.3, 0.85, 0.4, 0.6],
    "outcomes": [1, 0, 1, 1, 0],
    "revenues": [9000, 0, 12000, 5000, 0],
    "niche": "Roofing Restoration",
})
print(f"[SI EVOLUTION] calibration_a={feedback['calibration']['a']:.3f} "
      f"optimization_weight={feedback['optimization_weight']}")
