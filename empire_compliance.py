def is_lead_compliant(lead_data):
    # 1. Did they double opt-in?
    if not lead_data.get("double_opt_in", False):
        return False
    
    # 2. Did they opt-out?
    if lead_data.get("opted_out", False):
        return False
        
    # Add future legal checks here
    return True
