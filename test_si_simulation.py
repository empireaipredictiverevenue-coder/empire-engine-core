from empire_si_core import SyntheticIntelligence

# 1. Initialize the Synthetic Intelligence Core
si_engine = SyntheticIntelligence()

# 2. Simulate a high-intent lead in a storm zone
lead_data = {"id": "test-lead-001", "intent_score": 9, "city": "Dallas"}
print(f"[TEST] Simulating dispatch for: {lead_data['id']}...")

# 3. SI Core: Pre-flight Prediction
prediction = si_engine.simulate_strategy(lead_data)
print(f"[SI RESULT] {prediction}")

# 4. Feedback Test: Simulate a successful outcome to trigger learning
feedback = si_engine.evolve_logic("Outcome: SUCCESS | Revenue: $500")
print(f"[SI EVOLUTION] {feedback}")
