"""
Scrapy items for B2B lead enrichment from BBB, Yelp, Google Business.
"""
import scrapy


class B2BBusinessItem(scrapy.Item):
    """Enriched business data from directory scraping."""
    # ── Identity (for matching back to b2b_leads) ──
    b2b_lead_id = scrapy.Field()       # UUID of the b2b_leads row
    company_name = scrapy.Field()      # As found on the directory
    search_phone = scrapy.Field()      # Phone used for search/lookup
    search_website = scrapy.Field()    # Website used for lookup

    # ── Source metadata ──
    source = scrapy.Field()            # "bbb", "yelp", "google_business"
    profile_url = scrapy.Field()       # URL of the business profile page

    # ── Enrichment data ──
    rating = scrapy.Field()            # Numeric rating (e.g. 4.5)
    review_count = scrapy.Field()      # Number of reviews
    categories = scrapy.Field()        # List of category strings
    accreditation = scrapy.Field()     # BBB: "A+" etc, Yelp: None
    price_level = scrapy.Field()       # "$" to "$$$$"
    hours = scrapy.Field()             # Business hours text
    phone_on_profile = scrapy.Field()  # Phone as listed on profile
    address_on_profile = scrapy.Field()# Address as listed on profile
    website_on_profile = scrapy.Field()# Website as listed on profile
    claimed = scrapy.Field()           # Whether business claimed the profile
    photos_count = scrapy.Field()      # Number of photos

    # ── Match confidence ──
    match_confidence = scrapy.Field()  # "high", "medium", "low"
    match_reason = scrapy.Field()      # Why we think this is a match

    # ── Raw ──
    scraped_at = scrapy.Field()        # ISO timestamp
    raw_html_snippet = scrapy.Field()  # Truncated raw HTML for debugging
