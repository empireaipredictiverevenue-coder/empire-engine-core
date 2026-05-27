def calculate_lead_score(lead_data):
    # High-value filter: Prioritize Debt Relief + High Net Worth Zip Codes
    base_score = 100
    if lead_data.get('intent_score', 0) > 8:
        base_score += 500
    return base_score
