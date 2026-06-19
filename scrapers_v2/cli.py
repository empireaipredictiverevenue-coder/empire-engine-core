import typer
from typing import Optional
from orchestrator import run_all_sources
import asyncio

app = typer.Typer(help="Elite Scraper v2 - Custom lead & contractor scraping")

@app.command()
def run(vertical: Optional[str] = typer.Option(None, help="Specific vertical to scrape")):
    """Run the scraper (all sources or one vertical)."""
    asyncio.run(run_all_sources())
    typer.echo("Scraping completed.")

@app.command()
def sources():
    """List all configured sources."""
    from sources import SOURCES
    for s in SOURCES:
        typer.echo(f"{s[vertical]} | {s[scraper]} | priority={s.get(priority, 10)}")

if __name__ == "__main__":
    app()
