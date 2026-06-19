import logging
import os

def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler("/app/logs/customer.log"),
            logging.StreamHandler()
        ]
    )
