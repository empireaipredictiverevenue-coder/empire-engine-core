import asyncio
import sys
from public_adjuster_async import PublicAdjusterAsyncScraper

async def main():
    urls = sys.argv[1:] if len(sys.argv) > 1 else [
        "https://www.bbb.org/search?term=public+adjuster&location=Texas"
    ]
    scraper = PublicAdjusterAsyncScraper()
    results = await scraper.run(urls)
    print(f"Found {len(results)} leads")
    for r in results[:5]:
        print(r.model_dump())

if __name__ == "__main__":
    asyncio.run(main())
