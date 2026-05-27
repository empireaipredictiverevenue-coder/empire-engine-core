def render_radar(coords, status, confidence):
    lat, lon = coords
    if status == 'STRIKE':
        print(f"[GREEN DOT] PRECISION LOCK: LAT {lat}, LON {lon} | Confidence: {confidence:.2f}")
    else:
        print(f"[CYAN DOT] Scanning... Sector {lat}, {lon}")
