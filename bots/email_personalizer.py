from local_brain import LocalBrain

def personalize_email(lead_name, niche):
    brain = LocalBrain(model="llama3.1:latest")
    prompt = f"Write a professional, high-intent outreach email for {lead_name} in {niche}. Keep it under 100 words and focus on value."
    return brain.think(prompt)
