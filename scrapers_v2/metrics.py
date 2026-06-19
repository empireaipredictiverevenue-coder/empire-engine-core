from prometheus_client import Counter, Gauge, start_http_server
import time

leads_scraped = Counter(leads_scraped_total, Total leads scraped, [vertical, source])
scrape_duration = Gauge(scrape_duration_seconds, Time spent scraping, [vertical])
active_sources = Gauge(active_sources, Number of active scraping sources)

def start_metrics_server(port: int = 8002):
    start_http_server(port)
    print(f"Metrics server started on :{port}")

def record_lead(vertical: str, source: str):
    leads_scraped.labels(vertical=vertical, source=source).inc()

def record_duration(vertical: str, duration: float):
    scrape_duration.labels(vertical=vertical).set(duration)
