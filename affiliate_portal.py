from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/portal/affiliate/<affiliate_id>/performance', methods=['GET'])
def get_performance(affiliate_id):
    # Retrieve performance from the central dashboard events
    stats = {
        "affiliate_id": affiliate_id,
        "active_lanes": 32,
        "total_conversions": 1250,
        "revenue_share_usdc": 45000.50
    }
    return jsonify(stats)

# This portal is the "Hook" for external partners to grow your revenue
