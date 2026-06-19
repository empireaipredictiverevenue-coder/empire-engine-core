from prometheus_client import Counter, Gauge, start_http_server

leads_scraped = Counter("leads_scraped_total", "Total leads scraped", ["vertical", "source"])
scrape_duration = Gauge("scrape_duration_seconds", "Time spent scraping", ["vertical"])
active_sources = Gauge("active_sources", "Number of active scraping sources")

def start_metrics_server(port=8002):
    start_http_server(port)
    print(f"Metrics server started on :{port}")

def record_lead(vertical, source):
    leads_scraped.labels(vertical=vertical, source=source).inc()
