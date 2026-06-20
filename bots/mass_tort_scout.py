import urllib.request
import json

def fetch_latest_recall():
    url = "https://api.fda.gov/device/enforcement.json?limit=1"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            results = data.get('results', [])
            if results:
                recall = results[0]
                description = recall.get('product_description', 'Unknown Device')
                reason = recall.get('reason_for_recall', 'No reason listed')
                return {"device": description[:100], "reason": reason[:100]}
    except Exception as e:
        return {"error": str(e)}
    return None

def run_once():
    """Single cycle for agent_runner loop mode."""
    result = fetch_latest_recall()
    print(f"[MASS TORT SCOUT] Result: {result}")
    return {"status": "ok", "result": result}


if __name__ == "__main__":
    live_lead = fetch_latest_recall()
    print(f"[MASS TORT SCOUT] Live Target Found: {live_lead}")
