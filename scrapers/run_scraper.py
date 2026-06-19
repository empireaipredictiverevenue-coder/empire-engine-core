import sys
from public_adjuster_scraper import PublicAdjusterScraper
from restoration_scraper import RestorationScraper

if __name__ == "__main__":
    vertical = sys.argv[1] if len(sys.argv) > 1 else "public_adjuster"
    urls = sys.argv[2:] if len(sys.argv) > 2 else []

    if vertical == "public_adjuster":
        scraper = PublicAdjusterScraper()
    elif vertical == "restoration":
        scraper = RestorationScraper()
    else:
        print("Unknown vertical")
        sys.exit(1)

    results = scraper.run(urls)
    print(f"Found {len(results)} results")
    for r in results[:5]:
        print(r)
