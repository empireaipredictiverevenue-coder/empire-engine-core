"""Empire AI Customer Container Entrypoint"""
import os
import importlib
import threading
from dotenv import load_dotenv
from reporting_agent import ReportingAgent
from logging_config import setup_logging

load_dotenv()
setup_logging()

SUPPORTED_PRODUCTS = [
    "predictive_backlink_agent",
    "storm_pipeline_system",
    "command_centre_system",
    "media_engine_system",
    "fee_system_system",
    "contractor_portal_system",
    "leadscore_system",
    "strike_system",
    "hexstrike_system",
    # Add more as they are created
]

def start_health_server():
    import health

def main():
    product = os.getenv("EMPIRE_PRODUCT", "predictive_backlink_agent")
    
    if product not in SUPPORTED_PRODUCTS:
        print(f"WARNING: {product} not in supported list. Attempting to load anyway.")
    
    print(f"Empire AI Customer Container starting: {product}")
    
    agent = ReportingAgent()
    agent.report_metric("container_started", 1.0)
    
    threading.Thread(target=start_health_server, daemon=True).start()
    
    try:
        module = importlib.import_module(f"bots.{product}")
        if hasattr(module, "run_continuously"):
            import asyncio
            asyncio.run(module.run_continuously())
        elif hasattr(module, "run_genome_cycle"):
            import asyncio
            asyncio.run(module.run_genome_cycle())
        else:
            print(f"No run method found in {product}")
    except Exception as e:
        print(f"Error loading product {product}: {e}")

if __name__ == "__main__":
    main()
