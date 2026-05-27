def audit_performance(dispatch_data):
    # If CPA > 60% of Revenue, flag for termination
    if dispatch_data['cpa'] > (dispatch_data['revenue'] * 0.6):
        print("[AUDITOR] WASTE DETECTED: Killing dispatch in zone: " + dispatch_data['zone'])
        return "TERMINATE"
    return "CONTINUE"
