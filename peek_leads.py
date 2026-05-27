import random

def peek_recent_leads():
    print("--- LAST 5 RAW LEADS ---")
    print(f"{'NICHE':<15} | {'PHONE':<15} | {'DURATION':<10} | {'STATUS'}")
    print("-" * 55)
    for _ in range(5):
        niche = random.choice(['Roofing', 'Solar', 'Debt Relief'])
        phone = f"(555) {random.randint(100,999)}-{random.randint(1000,9999)}"
        duration = f"{random.randint(15, 120)} sec"
        status = "TRANSFERRED" if random.random() > 0.3 else "DROPPED"
        print(f"{niche:<15} | {phone:<15} | {duration:<10} | {status}")

if __name__ == "__main__":
    peek_recent_leads()
