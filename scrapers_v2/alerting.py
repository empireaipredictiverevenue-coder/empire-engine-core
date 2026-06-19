from logging_config import get_logger
import os
import requests

logger = get_logger("scraper.alerting")

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")

def send_slack_alert(message: str):
    if not SLACK_WEBHOOK:
        logger.warning("No Slack webhook configured")
        return
    try:
        requests.post(SLACK_WEBHOOK, json={"text": message})
        logger.info("Slack alert sent")
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")

def alert_source_paused(source: str):
    send_slack_alert(f"🚨 Elite Scraper: Source *{source}* has been auto-paused due to repeated failures.")

def alert_circuit_breaker_open():
    send_slack_alert("🚨 Elite Scraper: Circuit breaker is OPEN. Scraping paused.")
