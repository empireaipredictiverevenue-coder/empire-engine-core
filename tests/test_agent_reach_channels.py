"""
EMPIRE V49 . AGENT-REACH CHANNELS UNIT TESTS
==============================================
Unit tests for the 10 new Agent-Reach intelligence channels:
  - hn_search, arxiv_search, wayback_fetch, wikipedia_search
  - cloudscraper_fetch, crawl4ai, apify_scrape
  - google_web_search, claude_analyze, dns_geo_lookup

Also tests SI-genome-driven channel selection (_si_select_channels),
volume multiplier (_si_volume_multiplier), enrich() dispatch with SI
genome, rate limiting, and error handling for all channels.

All tests are pure unit tests - no network, no external services.
"""
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

from products.agent_reach_enrichment import AgentReachEnricher, CHANNELS, TIER_CHANNELS


# - MOCK HELPERS

def _make_mock_db():
    """Return a callable get_db that returns a mock Supabase client."""
    class MT:
        def select(self, *a, **kw): return self
        def eq(self, *a, **kw): return self
        def gte(self, *a, **kw): return self
        def limit(self, *a, **kw): return self
        def execute(self): return type("R", (), {"data": []})()
        def insert(self, *a, **kw): return self
    class M:
        def table(self, n): return MT()
    return MagicMock(return_value=M())


@pytest.fixture
def enricher():
    """Return an AgentReachEnricher with a mock DB."""
    return AgentReachEnricher(get_db=_make_mock_db())


@pytest.fixture
def enterprise_channels():
    """Full channel list for SCRAPER_ENTERPRISE tier."""
    return list(TIER_CHANNELS["SCRAPER_ENTERPRISE"])


# ============================================================
#  Rate Limiting
# ============================================================

class TestRateLimiting:
    """Each channel has a per-minute rate limit defined in CHANNELS."""

    @pytest.mark.parametrize("channel", [
        "hn_search", "arxiv_search", "wayback_fetch", "wikipedia_search",
        "cloudscraper_fetch", "crawl4ai", "apify_scrape",
        "google_web_search", "claude_analyze", "dns_geo_lookup",
    ])
    def test_channel_has_rate_limit_config(self, channel):
        cfg = CHANNELS.get(channel)
        assert cfg is not None, f"{channel} not found in CHANNELS"
        assert "rate_limit" in cfg, f"{channel} missing rate_limit"
        assert "/min" in cfg["rate_limit"], f"{channel} rate_limit format: expected X/min"

    @pytest.mark.parametrize("channel", [
        "hn_search", "arxiv_search", "wayback_fetch", "wikipedia_search",
        "cloudscraper_fetch", "crawl4ai", "apify_scrape",
        "google_web_search", "claude_analyze", "dns_geo_lookup",
    ])
    def test_rate_limit_blocks_after_limit(self, enricher, channel):
        cfg = CHANNELS[channel]
        limit = int(cfg["rate_limit"].split("/")[0])
        for _ in range(limit):
            enricher._record_call(channel)
        assert enricher._check_rate(channel) is False

    def test_different_channels_independent(self, enricher):
        """Rate limits are per-channel, not shared."""
        # Fill hn_search budget
        cfg = CHANNELS["hn_search"]
        limit = int(cfg["rate_limit"].split("/")[0])
        for _ in range(limit):
            enricher._record_call("hn_search")
        # hn_search should be blocked now
        assert enricher._check_rate("hn_search") is False
        # arxiv_search should still be allowed (independent channel)
        assert enricher._check_rate("arxiv_search") is True


# ============================================================
#  hn_search
# ============================================================

class TestHnSearch:
    """hn_search - Hacker News via Algolia API."""

    def test_success(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {
                    "ok": True,
                    "data": {
                        "hits": [
                            {"title": "Roofing in 2024", "url": "https://news.ycombinator.com/item?id=1", "points": 42, "author": "user1"},
                            {"title": "HVAC startups", "url": "https://news.ycombinator.com/item?id=2", "points": 15, "author": "user2"},
                        ]
                    },
                    "channel": "hn_search",
                    "format": "json",
                }
                result = await enricher.hn_search("roofing contractors", max_results=2)
                assert result["ok"] is True
                assert len(result["data"]["hits"]) == 2
                assert result["data"]["hits"][0]["title"] == "Roofing in 2024"
                assert result["channel"] == "hn_search"
        asyncio.run(run())

    def test_rate_limited(self, enricher):
        async def run():
            cfg = CHANNELS["hn_search"]
            limit = int(cfg["rate_limit"].split("/")[0])
            for _ in range(limit):
                enricher._record_call("hn_search")
            result = await enricher.hn_search("test", max_results=1)
            assert result["ok"] is False
            assert "rate limited" in result["error"]
        asyncio.run(run())

    def test_channel_config(self):
        cfg = CHANNELS.get("hn_search")
        assert cfg is not None
        assert "Hacker News" in cfg["description"]
        assert cfg["cost"] == "free"
        assert cfg["installed"] is True


# ============================================================
#  arxiv_search
# ============================================================

class TestArxivSearch:
    """arxiv_search - Academic papers via arXiv API."""

    def test_success_parses_atom_xml(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                atom_xml = '''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Machine Learning for Roofing</title>
    <summary>We apply ML to roofing contractor selection.</summary>
    <link href="http://arxiv.org/abs/1234.5678v1" rel="alternate"/>
    <author><name>John Doe</name></author>
  </entry>
  <entry>
    <title>Solar Panel Optimization</title>
    <summary>A study of solar panel placement.</summary>
    <link href="http://arxiv.org/abs/2345.6789" rel="alternate"/>
    <author><name>Jane Smith</name></author>
    <author><name>Bob Wilson</name></author>
  </entry>
</feed>'''
                mock_run.return_value = {
                    "ok": True,
                    "data": {"text": atom_xml},
                    "channel": "arxiv_search",
                    "format": "text",
                }
                result = await enricher.arxiv_search("machine learning roofing", max_results=2)
                assert result["ok"] is True
                assert result["format"] == "json"
                papers = result["data"]["papers"]
                assert len(papers) == 2
                assert papers[0]["title"] == "Machine Learning for Roofing"
                assert papers[0]["url"] == "http://arxiv.org/abs/1234.5678v1"
                assert papers[0]["authors"] == ["John Doe"]
                assert papers[1]["authors"] == ["Jane Smith", "Bob Wilson"]
                assert len(papers[0]["summary"]) > 0
        asyncio.run(run())

    def test_channel_config(self):
        cfg = CHANNELS.get("arxiv_search")
        assert cfg is not None
        assert "arXiv" in cfg["description"]
        assert cfg["cost"] == "free"


# ============================================================
#  wayback_fetch
# ============================================================

class TestWaybackFetch:
    """wayback_fetch - Wayback Machine CDX API."""

    def test_success_parses_cdx_json(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                cdx_data = [
                    ["timestamp", "original", "statuscode"],
                    ["20240101120000", "https://example.com/roofing", "200"],
                    ["20230101120000", "https://example.com/hvac", "301"],
                ]
                mock_run.return_value = {
                    "ok": True,
                    "data": cdx_data,
                    "channel": "wayback_fetch",
                    "format": "json",
                }
                result = await enricher.wayback_fetch("https://example.com", max_results=2)
                assert result["ok"] is True
                snapshots = result["data"]["snapshots"]
                assert len(snapshots) == 2
                assert snapshots[0]["timestamp"] == "20240101120000"
                assert snapshots[0]["original_url"] == "https://example.com/roofing"
                assert snapshots[0]["status_code"] == "200"
                assert "web.archive.org" in snapshots[0]["wayback_url"]
                assert snapshots[1]["status_code"] == "301"
        asyncio.run(run())


# ============================================================
#  wikipedia_search
# ============================================================

class TestWikipediaSearch:
    """wikipedia_search - Wikipedia API search + summary."""

    def test_success_two_step_search(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.side_effect = [
                    {
                        "ok": True,
                        "data": {
                            "query": {
                                "search": [
                                    {"pageid": 12345, "title": "Roofing"},
                                    {"pageid": 67890, "title": "Roofing contractor"},
                                ]
                            }
                        },
                        "channel": "wikipedia_search",
                        "format": "json",
                    },
                    {
                        "ok": True,
                        "data": {
                            "query": {
                                "pages": {
                                    "12345": {
                                        "title": "Roofing",
                                        "extract": "Roofing is the process of installing a roof.",
                                    },
                                    "67890": {
                                        "title": "Roofing contractor",
                                        "extract": "A roofing contractor installs and repairs roofs.",
                                    },
                                }
                            }
                        },
                        "channel": "wikipedia_search",
                        "format": "json",
                    },
                ]
                result = await enricher.wikipedia_search("roofing", max_results=2)
                assert result["ok"] is True
                articles = result["data"]["articles"]
                assert len(articles) == 2
                assert articles[0]["title"] == "Roofing"
                assert "installing a roof" in articles[0]["summary"]
                assert "wikipedia.org" in articles[0]["url"]
                assert articles[1]["title"] == "Roofing contractor"
                assert mock_run.call_count == 2
        asyncio.run(run())

    def test_no_search_results(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {
                    "ok": True,
                    "data": {"query": {"search": []}},
                    "channel": "wikipedia_search",
                    "format": "json",
                }
                result = await enricher.wikipedia_search("xyznonexistent", max_results=2)
                assert result["ok"] is True
                assert result.get("data", {}).get("query", {}).get("search", []) == []
        asyncio.run(run())


# ============================================================
#  cloudscraper_fetch
# ============================================================

class TestCloudscraperFetch:
    """cloudscraper_fetch - Cloudflare-bypass HTTP fetch."""

    def test_success(self, enricher):
        async def run():
            with patch("cloudscraper.create_scraper") as mock_create:
                mock_scraper = MagicMock()
                mock_create.return_value = mock_scraper
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.text = "<html><body>Page content here</body></html>"
                mock_scraper.get.return_value = mock_response

                result = await enricher.cloudscraper_fetch("https://example.com")
                assert result["ok"] is True
                assert "Page content" in result["data"]["text"]
                assert result["data"]["status_code"] == 200
                assert result["data"]["url"] == "https://example.com"
        asyncio.run(run())

    def test_non_200_status(self, enricher):
        async def run():
            with patch("cloudscraper.create_scraper") as mock_create:
                mock_scraper = MagicMock()
                mock_create.return_value = mock_scraper
                mock_response = MagicMock()
                mock_response.status_code = 403
                mock_scraper.get.return_value = mock_response

                result = await enricher.cloudscraper_fetch("https://blocked.example.com")
                assert result["ok"] is False
                assert "403" in result["error"]
        asyncio.run(run())

    def test_import_error(self, enricher):
        async def run():
            import builtins
            original_import = builtins.__import__
            def mock_import(name, *args, **kw):
                if name == "cloudscraper":
                    raise ImportError("No module named 'cloudscraper'")
                return original_import(name, *args, **kw)
            with patch("builtins.__import__", side_effect=mock_import):
                result = await enricher.cloudscraper_fetch("https://example.com")
                assert result["ok"] is False
                assert "not installed" in result["error"]
        asyncio.run(run())


# ============================================================
#  crawl4ai
# ============================================================

class TestCrawl4AI:
    """crawl4ai - Deep web crawling via Crawl4AI library."""

    def test_success(self, enricher):
        async def run():
            with (
                patch("crawl4ai.AsyncWebCrawler") as mock_crawler_cls,
                patch("crawl4ai.async_configs.CrawlerRunConfig"),
            ):
                mock_instance = AsyncMock()
                mock_crawler_cls.return_value.__aenter__.return_value = mock_instance

                mock_result = MagicMock()
                mock_result.success = True
                mock_result.markdown = "# Page Title\n\nContent here."
                mock_result.html = "<html><body>Content</body></html>"
                mock_result.metadata = {"title": "Test Page"}
                mock_result.links = {
                    "internal": ["/about", "/contact"],
                    "external": ["https://other.com"],
                }
                mock_result.error_message = None
                mock_instance.arun.return_value = mock_result

                result = await enricher.crawl4ai("https://example.com", max_results=10)
                assert result["ok"] is True
                assert "Page Title" in result["data"]["content"]
                assert result["data"]["title"] == "Test Page"
                assert len(result["data"]["links"]) == 3
                assert result["channel"] == "crawl4ai"
        asyncio.run(run())

    def test_crawl_failure(self, enricher):
        async def run():
            with (
                patch("crawl4ai.AsyncWebCrawler") as mock_crawler_cls,
                patch("crawl4ai.async_configs.CrawlerRunConfig"),
            ):
                mock_instance = AsyncMock()
                mock_crawler_cls.return_value.__aenter__.return_value = mock_instance

                mock_result = MagicMock()
                mock_result.success = False
                mock_result.error_message = "Connection timeout"
                mock_instance.arun.return_value = mock_result

                result = await enricher.crawl4ai("https://timeout.example.com")
                assert result["ok"] is False
                assert "timeout" in result["error"].lower()
        asyncio.run(run())

    def test_channel_config(self):
        cfg = CHANNELS.get("crawl4ai")
        assert cfg is not None
        assert "Crawl4AI" in cfg["description"]
        assert "headless browser" in cfg["auth_note"].lower()


# ============================================================
#  apify_scrape
# ============================================================

class TestApifyScrape:
    """apify_scrape - Apify platform scraping."""

    def test_success_with_query(self, enricher):
        async def run():
            with patch.dict(os.environ, {"APIFY_TOKEN": "test-token-123"}), \
                 patch("apify_client.ApifyClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client

                mock_actor = MagicMock()
                mock_client.actor.return_value = mock_actor
                mock_actor.call.return_value = {"defaultDatasetId": "ds-123"}

                mock_dataset = MagicMock()
                mock_client.dataset.return_value = mock_dataset
                mock_items = MagicMock()
                mock_items.items = [
                    {"title": "Roofing Co", "url": "https://example.com/roofing"},
                    {"title": "HVAC Inc", "url": "https://example.com/hvac"},
                ]
                mock_dataset.list_items.return_value = mock_items

                result = await enricher.apify_scrape("roofing contractors", max_results=2)
                assert result["ok"] is True
                assert len(result["data"]["items"]) == 2
                assert result["data"]["items"][0]["title"] == "Roofing Co"
                assert mock_client.actor.call_args[0][0] == "apify/google-search-results-scraper"
        asyncio.run(run())

    def test_success_with_url(self, enricher):
        async def run():
            with patch.dict(os.environ, {"APIFY_TOKEN": "test-token-123"}), \
                 patch("apify_client.ApifyClient") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client

                mock_actor = MagicMock()
                mock_client.actor.return_value = mock_actor
                mock_actor.call.return_value = {"defaultDatasetId": "ds-456"}

                mock_dataset = MagicMock()
                mock_client.dataset.return_value = mock_dataset
                mock_items = MagicMock()
                mock_items.items = [{"url": "https://example.com", "title": "Example"}]
                mock_dataset.list_items.return_value = mock_items

                result = await enricher.apify_scrape("https://example.com", max_results=1)
                assert result["ok"] is True
                assert mock_client.actor.call_args[0][0] == "apify/web-scraper"
        asyncio.run(run())

    def test_no_api_token(self, enricher):
        async def run():
            with patch.dict(os.environ, {}, clear=True):
                result = await enricher.apify_scrape("test", max_results=1)
                assert result["ok"] is False
                assert "APIFY_TOKEN" in result["error"]
        asyncio.run(run())


# ============================================================
#  google_web_search
# ============================================================

class TestGoogleWebSearch:
    """google_web_search - Google Programmable Search."""

    def test_success(self, enricher):
        async def run():
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key", "GOOGLE_CSE_ID": "test-cse"}), \
                 patch("googleapiclient.discovery.build") as mock_build:
                mock_service = MagicMock()
                mock_build.return_value = mock_service

                mock_cse = MagicMock()
                mock_service.cse.return_value = mock_cse
                mock_list = MagicMock()
                mock_cse.list.return_value = mock_list
                mock_list.execute.return_value = {
                    "items": [
                        {"title": "Roofing Contractors", "link": "https://example.com/roofing", "snippet": "Best roofing in Texas"},
                        {"title": "HVAC Services", "link": "https://example.com/hvac", "snippet": "AC repair"},
                    ],
                    "searchInformation": {"totalResults": "2"},
                }

                result = await enricher.google_web_search("roofing contractors Texas", max_results=2)
                assert result["ok"] is True
                assert len(result["data"]["results"]) == 2
                assert result["data"]["results"][0]["title"] == "Roofing Contractors"
                assert result["data"]["results"][0]["url"] == "https://example.com/roofing"
                assert result["data"]["total_estimated"] == "2"
                mock_cse.list.assert_called_once_with(q="roofing contractors Texas", cx="test-cse", num=2)
        asyncio.run(run())

    def test_no_api_key(self, enricher):
        async def run():
            with patch.dict(os.environ, {}, clear=True):
                result = await enricher.google_web_search("test", max_results=1)
                assert result["ok"] is False
                assert "GOOGLE_API_KEY" in result["error"]
        asyncio.run(run())

    def test_no_cse_id(self, enricher):
        async def run():
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=True):
                result = await enricher.google_web_search("test", max_results=1)
                assert result["ok"] is False
                assert "GOOGLE_CSE_ID" in result["error"]
        asyncio.run(run())


# ============================================================
#  claude_analyze
# ============================================================

class TestClaudeAnalyze:
    """claude_analyze - AI analysis via Anthropic Claude."""

    def test_success(self, enricher):
        async def run():
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test123"}), \
                 patch("anthropic.AsyncAnthropic") as mock_anthropic_cls:
                mock_anthropic = AsyncMock()
                mock_anthropic_cls.return_value = mock_anthropic

                mock_msg = MagicMock()
                mock_msg.content = [MagicMock(text="This is an analysis of the roofing industry.")]
                mock_msg.model = "claude-sonnet-4-20250514"
                mock_msg.usage = MagicMock(input_tokens=50, output_tokens=100)
                mock_anthropic.messages.create.return_value = mock_msg

                result = await enricher.claude_analyze("Analyze roofing industry trends")
                assert result["ok"] is True
                assert "analysis of the roofing industry" in result["data"]["analysis"]
                assert result["data"]["model"] == "claude-sonnet-4-20250514"
                assert result["data"]["usage"]["input_tokens"] == 50
                assert result["channel"] == "claude_analyze"
        asyncio.run(run())

    def test_no_api_key(self, enricher):
        async def run():
            with patch.dict(os.environ, {}, clear=True):
                result = await enricher.claude_analyze("test prompt")
                assert result["ok"] is False
                assert "ANTHROPIC_API_KEY" in result["error"]
        asyncio.run(run())

    def test_truncates_long_prompts(self, enricher):
        async def run():
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test123"}), \
                 patch("anthropic.AsyncAnthropic") as mock_anthropic_cls:
                mock_anthropic = AsyncMock()
                mock_anthropic_cls.return_value = mock_anthropic

                mock_msg = MagicMock()
                mock_msg.content = [MagicMock(text="Analysis result")]
                mock_msg.model = "claude-sonnet-4-20250514"
                mock_anthropic.messages.create.return_value = mock_msg

                long_prompt = "x" * 50000
                result = await enricher.claude_analyze(long_prompt)
                assert result["ok"] is True
                call_kwargs = mock_anthropic.messages.create.call_args[1]
                sent_content = call_kwargs["messages"][0]["content"]
                assert len(sent_content) <= 25000
        asyncio.run(run())


# ============================================================
#  dns_geo_lookup
# ============================================================

class TestDnsGeoLookup:
    """dns_geo_lookup - DNS resolution + IP geolocation."""

    def test_success(self, enricher):
        async def run():
            with (
                patch("dns.resolver.resolve") as mock_resolve,
                patch("geopy.geocoders.Nominatim") as mock_geo,
            ):
                def resolve_side_effect(domain, qtype):
                    result = MagicMock()
                    if qtype == "A":
                        a_rec = MagicMock()
                        a_rec.__str__.return_value = "93.184.216.34"
                        result.__iter__.return_value = iter([a_rec])
                    elif qtype == "AAAA":
                        result.__iter__.return_value = iter([])
                    elif qtype == "NS":
                        ns_rec = MagicMock()
                        ns_rec.__str__.return_value = "ns1.example.com."
                        result.__iter__.return_value = iter([ns_rec])
                    elif qtype == "MX":
                        mx_rec = MagicMock()
                        mx_rec.preference = 10
                        mx_exchange = MagicMock()
                        mx_exchange.__str__.return_value = "mail.example.com."
                        mx_rec.exchange = mx_exchange
                        result.__iter__.return_value = iter([mx_rec])
                    elif qtype == "TXT":
                        txt_rec = MagicMock()
                        txt_rec.strings = [b"v=spf1 include:_spf.example.com ~all"]
                        result.__iter__.return_value = iter([txt_rec])
                        # Slicing support: Answer objects support [:5]
                        result.__getitem__.return_value = [txt_rec]
                    else:
                        result.__iter__.return_value = iter([])
                    return result
                mock_resolve.side_effect = resolve_side_effect

                mock_geolocator = MagicMock()
                mock_geo.return_value = mock_geolocator
                mock_location = MagicMock()
                mock_location.address = "Boston, MA, US"
                mock_location.latitude = 42.36
                mock_location.longitude = -71.06
                mock_geolocator.geocode.return_value = mock_location

                result = await enricher.dns_geo_lookup("example.com", max_results=5)
                assert result["ok"] is True
                dns = result["data"]["dns"]
                assert len(dns["a"]) == 1
                assert dns["a"][0] == "93.184.216.34"
                assert len(dns["aaaa"]) == 0
                assert len(dns["ns"]) == 1
                assert "ns1.example.com" in dns["ns"][0]
                assert len(dns["mx"]) == 1
                assert dns["mx"][0]["priority"] == 10
                assert "mail.example.com" in dns["mx"][0]["server"]
                assert len(dns["txt"]) == 1
                assert "v=spf1" in dns["txt"][0]

                geo = result["data"]["geo"]
                assert geo["ip"] == "93.184.216.34"
                assert geo["address"] == "Boston, MA, US"
                assert geo["latitude"] == 42.36
        asyncio.run(run())


# ============================================================
#  SI Genome -> Channel Selection
# ============================================================

class TestSIGenomeChannelSelection:
    """_si_select_channels maps genome traits to channel selections."""

    @pytest.fixture
    def enterprise_tier(self):
        return list(TIER_CHANNELS["SCRAPER_ENTERPRISE"])

    def test_fallback_empty_genome(self, enterprise_tier):
        channels = AgentReachEnricher._si_select_channels({}, enterprise_tier)
        assert len(channels) == len(enterprise_tier)
        assert set(channels) == set(enterprise_tier)

    def test_fallback_empty_genome_empty_tier(self):
        channels = AgentReachEnricher._si_select_channels({}, [])
        assert channels == ["jina_read"]

    def test_fallback_none_genome(self, enterprise_tier):
        channels = AgentReachEnricher._si_select_channels(None, enterprise_tier)
        assert len(channels) == len(enterprise_tier)

    def test_aggressive_strike_wide_net(self, enterprise_tier):
        genome = {"aggressiveness": 0.9, "risk_tolerance": 0.7, "outreach_intensity": 0.9, "price_premium": 0.8, "narrow_focus": 0.3}
        channels = AgentReachEnricher._si_select_channels(genome, enterprise_tier)
        assert len(channels) > len(enterprise_tier) * 0.7
        assert "jina_read" in channels
        assert "semantic_search" in channels
        assert "rss_fetch" in channels
        assert "crawl4ai" in channels
        assert "google_web_search" in channels
        assert "claude_analyze" in channels

    def test_recall_sniper_narrow_focus(self, enterprise_tier):
        genome = {"aggressiveness": 0.7, "risk_tolerance": 0.5, "outreach_intensity": 0.8, "price_premium": 0.5, "narrow_focus": 0.8}
        channels = AgentReachEnricher._si_select_channels(genome, enterprise_tier)
        assert "semantic_search" in channels
        assert "google_web_search" in channels
        assert "dns_geo_lookup" in channels
        assert "twitter_search" in channels
        assert "reddit_search" in channels

    def test_ugly_banner_conservative(self, enterprise_tier):
        genome = {"aggressiveness": 0.4, "risk_tolerance": 0.3, "outreach_intensity": 0.6, "price_premium": 0.2, "narrow_focus": 0.5}
        channels = AgentReachEnricher._si_select_channels(genome, enterprise_tier)
        assert "cloudscraper_fetch" not in channels
        assert "apify_scrape" not in channels
        assert "crawl4ai" not in channels
        assert "google_web_search" not in channels
        assert "claude_analyze" not in channels
        assert "jina_read" in channels
        assert "semantic_search" in channels

    def test_standard_balanced(self, enterprise_tier):
        genome = {"aggressiveness": 0.5, "risk_tolerance": 0.5, "outreach_intensity": 0.5, "price_premium": 0.5, "narrow_focus": 0.5}
        channels = AgentReachEnricher._si_select_channels(genome, enterprise_tier)
        assert "jina_read" in channels
        assert "semantic_search" in channels
        assert "rss_fetch" in channels
        assert "youtube_transcript" in channels
        assert "google_web_search" in channels
        assert "claude_analyze" in channels
        assert "cloudscraper_fetch" not in channels

    def test_low_price_premium_blocks_paid(self, enterprise_tier):
        genome = {"aggressiveness": 0.7, "risk_tolerance": 0.5, "outreach_intensity": 0.5, "price_premium": 0.3, "narrow_focus": 0.5}
        channels = AgentReachEnricher._si_select_channels(genome, enterprise_tier)
        assert "google_web_search" not in channels
        assert "claude_analyze" not in channels

    def test_high_risk_tolerance_adds_experimental(self, enterprise_tier):
        genome = {"aggressiveness": 0.4, "risk_tolerance": 0.8, "outreach_intensity": 0.5, "price_premium": 0.5, "narrow_focus": 0.5}
        channels = AgentReachEnricher._si_select_channels(genome, enterprise_tier)
        assert "cloudscraper_fetch" in channels

    def test_pro_tier_constrains_selection(self):
        pro_channels = list(TIER_CHANNELS["SCRAPER_PRO"])
        genome = {"aggressiveness": 0.9, "risk_tolerance": 0.7, "outreach_intensity": 0.9, "price_premium": 0.8, "narrow_focus": 0.3}
        channels = AgentReachEnricher._si_select_channels(genome, pro_channels)
        for ch in channels:
            assert ch in pro_channels, f"{ch} not in SCRAPER_PRO"
        assert "crawl4ai" not in channels
        assert "cloudscraper_fetch" not in channels
        assert "google_web_search" not in channels

    def test_starter_tier_only_jina(self):
        starter_channels = list(TIER_CHANNELS["SCRAPER_STARTER"])
        genome = {"aggressiveness": 0.9, "narrow_focus": 0.3}
        channels = AgentReachEnricher._si_select_channels(genome, starter_channels)
        assert channels == starter_channels  # starter only has jina_read


# ============================================================
#  SI Volume Multiplier
# ============================================================

class TestSIVolumeMultiplier:
    """_si_volume_multiplier maps outreach_intensity to a volume scalar."""

    def test_empty_genome_returns_1x(self):
        assert AgentReachEnricher._si_volume_multiplier({}) == 1.0

    def test_none_genome_returns_1x(self):
        assert AgentReachEnricher._si_volume_multiplier(None) == 1.0

    def test_low_outreach_minimum(self):
        m = AgentReachEnricher._si_volume_multiplier({"outreach_intensity": 0.0})
        assert m == pytest.approx(0.3, abs=0.01)

    def test_baseline_outreach(self):
        m = AgentReachEnricher._si_volume_multiplier({"outreach_intensity": 0.5})
        assert m == pytest.approx(1.15, abs=0.01)

    def test_max_outreach(self):
        m = AgentReachEnricher._si_volume_multiplier({"outreach_intensity": 1.0})
        assert m == pytest.approx(2.0, abs=0.01)

    def test_mid_outreach(self):
        m = AgentReachEnricher._si_volume_multiplier({"outreach_intensity": 0.3})
        assert m == pytest.approx(0.3 + 1.7 * 0.3, abs=0.01)


# ============================================================
#  enrich() dispatch with SI genome
# ============================================================

class TestEnrichDispatchWithGenome:
    """enrich() method with SI genome parameter."""

    # ── Archetype genomes for reuse ──
    _AGGRESSIVE = {"aggressiveness": 0.9, "narrow_focus": 0.3, "risk_tolerance": 0.7, "price_premium": 0.8, "outreach_intensity": 0.9}
    _RECALL =     {"aggressiveness": 0.7, "narrow_focus": 0.8, "risk_tolerance": 0.5, "price_premium": 0.5, "outreach_intensity": 0.8}
    _UGLY =       {"aggressiveness": 0.4, "narrow_focus": 0.5, "risk_tolerance": 0.3, "price_premium": 0.2, "outreach_intensity": 0.6}
    _FINANCIAL =  {"aggressiveness": 0.8, "narrow_focus": 0.4, "risk_tolerance": 0.6, "price_premium": 0.7, "outreach_intensity": 0.7}
    _STANDARD =   {"aggressiveness": 0.5, "narrow_focus": 0.5, "risk_tolerance": 0.5, "price_premium": 0.5, "outreach_intensity": 0.5}

    def test_genome_selects_fewer_channels(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "semantic_search", "format": "text"}
                genome = {"aggressiveness": 0.2, "narrow_focus": 0.9}
                all_channels = list(TIER_CHANNELS["SCRAPER_PRO"])
                result = await enricher.enrich(
                    query="test query",
                    channels=all_channels,
                    max_results=10,
                    save_to_db=False,
                    genome=genome,
                )
                assert result["ok"] is True
                used = result["channels_used"]
                assert len(used) < len(all_channels), f"Expected {len(used)} < {len(all_channels)}"
                assert "semantic_search" in used
        asyncio.run(run())

    def test_genome_scales_max_results(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                genome = {"outreach_intensity": 1.0}
                result = await enricher.enrich(
                    query="test",
                    channels=["hn_search"],
                    max_results=10,
                    save_to_db=False,
                    genome=genome,
                )
                assert result["ok"] is True
                expected_max = max(5, int(10 * 2.0))
                assert expected_max == 20
        asyncio.run(run())

    def test_genome_none_falls_back_to_all_channels(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                pro_subset = ["hn_search", "wikipedia_search"]
                result = await enricher.enrich(
                    query="test",
                    channels=pro_subset,
                    max_results=5,
                    save_to_db=False,
                    genome=None,
                )
                assert result["ok"] is True
                used = result["channels_used"]
                assert set(used) == set(pro_subset)
        asyncio.run(run())

    def test_genome_empty_dict_uses_all(self, enricher):
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                pro_subset = ["hn_search", "wikipedia_search", "semantic_search"]
                result = await enricher.enrich(
                    query="test",
                    channels=pro_subset,
                    max_results=10,
                    save_to_db=False,
                    genome={},
                )
                assert result["ok"] is True
                used = result["channels_used"]
                assert set(used) == set(pro_subset)
        asyncio.run(run())

    # ── Skipped channels bug fix test ──
    def test_genome_skipped_channels_present_in_results(self, enricher):
        """URL-dependent channels selected by the genome are present in results
        even when skipped in pre-flight (non-URL query).

        Regression test for bug fix: the second `results = dict(cache_hit or {})`
        assignment was overwriting skipped channel entries set during pre-flight.
        See test_enrich_skipped_results_bug.py for the reproduction.
        """
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "semantic_search", "format": "text"}
                all_channels = list(TIER_CHANNELS["SCRAPER_ENTERPRISE"])
                # Use STANDARD genome + non-URL query
                # STANDARD (a=0.5,n=0.5) selects: jina_read, semantic_search, rss_fetch,
                # hn_search, wayback_fetch, github_search, youtube_transcript,
                # reddit_search, twitter_search, google_web_search, claude_analyze
                # URL-dependent among those: jina_read, rss_fetch, wayback_fetch
                result = await enricher.enrich(
                    query="roofing contractor Dallas",
                    channels=all_channels,
                    max_results=5,
                    save_to_db=False,
                    genome=self._STANDARD,
                )
                assert result["ok"] is True
                results_dict = result.get("results", {})
                # STANDARD selects jina_read, rss_fetch, wayback_fetch — all URL-dependent
                for ch in ["jina_read", "rss_fetch", "wayback_fetch"]:
                    assert ch in results_dict, f"{ch} missing from results (skipped channel bug)"
                    assert results_dict[ch].get("skipped") is True, f"{ch} should be marked as skipped"
                # crawl4ai is NOT selected by STANDARD genome (a=0.5 < 0.7, r=0.5 < 0.6)
                # cloudscraper_fetch is NOT selected (r=0.5 < 0.6)
                # Non-URL-dependent channels should be present with ok=True
                assert "semantic_search" in results_dict
                assert results_dict["semantic_search"].get("ok") is True
        asyncio.run(run())

    def test_genome_skipped_channels_present_with_partial_cache(self, enricher):
        """Skipped channels preserved even when there's a partial cache hit.

        The bug double-assignment was especially harmful with partial cache:
        cache results for some channels + skipped results for others,
        then the second assignment wiped the skipped ones.
        """
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                # Mock _check_cache to simulate partial cache hit
                cached = {"semantic_search": {"ok": True, "data": {"text": "cached"}}}
                orig = enricher._check_cache
                enricher._check_cache = lambda q, ch: cached
                try:
                    result = await enricher.enrich(
                        query="roofing contractor Dallas",
                        channels=["semantic_search", "jina_read", "github_search", "hn_search"],
                        max_results=5,
                        save_to_db=True,
                        genome=self._STANDARD,
                    )
                finally:
                    enricher._check_cache = orig
                assert result["ok"] is True
                r = result.get("results", {})
                assert "semantic_search" in r  # from cache
                assert "jina_read" in r and r["jina_read"].get("skipped") is True  # skipped, not wiped
                assert "github_search" in r  # live
                assert "hn_search" in r  # live
        asyncio.run(run())

    # ── Tier constraint tests ──
    def test_genome_starter_tier_only_jina_read(self, enricher):
        """SCRAPER_STARTER tier with any genome returns only jina_read."""
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "jina_read", "format": "text"}
                for name, genome in [("AGGRESSIVE", self._AGGRESSIVE), ("STANDARD", self._STANDARD), ("None", None)]:
                    result = await enricher.enrich(
                        query="https://example.com",
                        channels=None,
                        max_results=5,
                        tier="SCRAPER_STARTER",
                        save_to_db=False,
                        genome=genome,
                    )
                    assert result["ok"] is True, f"{name}: enrich failed"
                    used = result["channels_used"]
                    assert used == ["jina_read"], f"{name}: expected [jina_read], got {used}"
        asyncio.run(run())

    def test_genome_pro_tier_blocks_enterprise_channels(self, enricher):
        """Pro tier with aggressive genome blocks Enterprise-only channels."""
        async def run():
            pro_channels = set(TIER_CHANNELS["SCRAPER_PRO"])
            enterprise_only = [c for c in TIER_CHANNELS["SCRAPER_ENTERPRISE"] if c not in pro_channels]
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "semantic_search", "format": "text"}
                result = await enricher.enrich(
                    query="roofing contractor Texas",
                    channels=list(TIER_CHANNELS["SCRAPER_ENTERPRISE"]),  # request all 19
                    max_results=10,
                    tier="SCRAPER_PRO",
                    save_to_db=False,
                    genome=self._AGGRESSIVE,
                )
                assert result["ok"] is True
                used = set(result["channels_used"])
                # No Enterprise-only channels should leak through
                leaked = used & set(enterprise_only)
                assert len(leaked) == 0, f"Pro tier leaked Enterprise channels: {leaked}"
                # All channels must be within Pro tier
                assert used.issubset(pro_channels), f"Channels outside Pro tier: {used - pro_channels}"
        asyncio.run(run())

    # ── Full archetype dispatch tests ──
    def test_genome_aggressive_strike_max_coverage(self, enricher):
        """AGGRESSIVE_STRIKE genome selects the most channels."""
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "semantic_search", "format": "text"}
                all_channels = list(TIER_CHANNELS["SCRAPER_PRO"])
                result = await enricher.enrich(
                    query="test contractor Texas",
                    channels=all_channels,
                    max_results=10,
                    tier="SCRAPER_PRO",
                    save_to_db=False,
                    genome=self._AGGRESSIVE,
                )
                assert result["ok"] is True
                used = result["channels_used"]
                # AGGRESSIVE_STRIKE should select most Pro channels (wide-net + high aggression)
                assert len(used) >= 8, f"Expected >=8 channels, got {len(used)}: {used}"
                assert "semantic_search" in used
                assert "jina_read" in used
                assert "rss_fetch" in used
        asyncio.run(run())

    def test_genome_recall_sniper_ultra_targeted(self, enricher):
        """RECALL_SNIPER genome uses precision/focused channels."""
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                all_channels = list(TIER_CHANNELS["SCRAPER_PRO"])
                result = await enricher.enrich(
                    query="test",
                    channels=all_channels,
                    max_results=10,
                    tier="SCRAPER_PRO",
                    save_to_db=False,
                    genome=self._RECALL,
                )
                assert result["ok"] is True
                used = result["channels_used"]
                # RECALL_SNIPER has n=0.8 (ultra-targeted), fewer discovery channels
                # Pro tier has no paid/experimental, so this is a focused subset
                assert "semantic_search" in used
                assert len(used) >= 5, f"Expected >=5 channels, got {len(used)}: {used}"
        asyncio.run(run())

    def test_genome_ugly_banner_conservative(self, enricher):
        """UGLY_BANNER genome excludes paid/experimental channels."""
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                all_channels = list(TIER_CHANNELS["SCRAPER_ENTERPRISE"])
                result = await enricher.enrich(
                    query="test",
                    channels=all_channels,
                    max_results=10,
                    tier="SCRAPER_ENTERPRISE",
                    save_to_db=False,
                    genome=self._UGLY,
                )
                assert result["ok"] is True
                used = result["channels_used"]
                # UGLY_BANNER: no paid, no experimental, no crawl4ai
                assert "google_web_search" not in used
                assert "claude_analyze" not in used
                assert "cloudscraper_fetch" not in used
                assert "crawl4ai" not in used
                assert "jina_read" in used
                assert "semantic_search" in used
        asyncio.run(run())

    def test_genome_volume_scaling_through_enrich(self, enricher):
        """enrich() with genome scales max_results by outreach_intensity."""
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                test_cases = [
                    (self._AGGRESSIVE, 1.83),  # oi=0.9 → 1.83x
                    (self._RECALL, 1.66),       # oi=0.8 → 1.66x
                    (self._UGLY, 1.32),         # oi=0.6 → 1.32x
                    (self._STANDARD, 1.15),     # oi=0.5 → 1.15x
                ]
                for genome, expected_vol in test_cases:
                    result = await enricher.enrich(
                        query="test",
                        channels=["hn_search"],
                        max_results=5,
                        tier="SCRAPER_PRO",
                        save_to_db=False,
                        genome=genome,
                    )
                    assert result["ok"] is True
                    vol = AgentReachEnricher._si_volume_multiplier(genome)
                    assert vol == pytest.approx(expected_vol, abs=0.02), f"Expected vol {expected_vol}, got {vol}"
        asyncio.run(run())

    def test_genome_custom_genome_via_enrich(self, enricher):
        """A completely custom genome (not one of the 5 archetypes) works through enrich()."""
        async def run():
            with patch.object(enricher, "_run_cmd") as mock_run:
                mock_run.return_value = {"ok": True, "data": {"text": "result"}, "channel": "hn_search", "format": "text"}
                custom = {"aggressiveness": 0.6, "narrow_focus": 0.1, "risk_tolerance": 0.9, "price_premium": 1.0, "outreach_intensity": 0.4}
                all_channels = list(TIER_CHANNELS["SCRAPER_ENTERPRISE"])
                result = await enricher.enrich(
                    query="test",
                    channels=all_channels,
                    max_results=10,
                    tier="SCRAPER_ENTERPRISE",
                    save_to_db=False,
                    genome=custom,
                )
                assert result["ok"] is True
                used = result["channels_used"]
                # n=0.1 → wide net (RSS, HN, Wikipedia, arXiv, V2EX, Bilibili)
                # a=0.6 → just above medium threshold, adds social
                # r=0.9 → high risk tolerance: experimental channels
                # p=1.0 → max price_premium: all paid channels
                assert "hn_search" in used
                assert "cloudscraper_fetch" in used or "crawl4ai" in used or "apify_scrape" in used
                assert len(used) > 10, f"Expected many channels, got {len(used)}"
        asyncio.run(run())


# ============================================================
#  Channel Tier Config
# ============================================================

class TestChannelTierAccess:
    """Each channel is available in the correct tiers."""

    @pytest.mark.parametrize("channel", [
        "hn_search", "arxiv_search", "wayback_fetch", "wikipedia_search",
    ])
    def test_free_channels_in_pro_and_enterprise(self, channel):
        assert channel in TIER_CHANNELS["SCRAPER_PRO"], f"{channel} should be in SCRAPER_PRO"
        assert channel in TIER_CHANNELS["SCRAPER_ENTERPRISE"], f"{channel} should be in SCRAPER_ENTERPRISE"
        assert channel not in TIER_CHANNELS["SCRAPER_STARTER"], f"{channel} should NOT be in SCRAPER_STARTER"

    @pytest.mark.parametrize("channel", [
        "cloudscraper_fetch", "crawl4ai", "apify_scrape",
        "google_web_search", "claude_analyze", "dns_geo_lookup",
    ])
    def test_paid_niche_channels_only_in_enterprise(self, channel):
        assert channel not in TIER_CHANNELS["SCRAPER_STARTER"], f"{channel} should NOT be in SCRAPER_STARTER"
        assert channel not in TIER_CHANNELS["SCRAPER_PRO"], f"{channel} should NOT be in SCRAPER_PRO"
        assert channel in TIER_CHANNELS["SCRAPER_ENTERPRISE"], f"{channel} should be in SCRAPER_ENTERPRISE"


# ============================================================
#  Channel Config Completeness
# ============================================================

class TestChannelConfig:
    """All 10 new channels have complete config entries."""

    @pytest.mark.parametrize("channel", [
        "hn_search", "arxiv_search", "wayback_fetch", "wikipedia_search",
        "cloudscraper_fetch", "crawl4ai", "apify_scrape",
        "google_web_search", "claude_analyze", "dns_geo_lookup",
    ])
    def test_channel_has_required_config_fields(self, channel):
        cfg = CHANNELS.get(channel)
        assert cfg is not None, f"{channel} not in CHANNELS"
        assert "description" in cfg and cfg["description"], f"{channel} missing description"
        assert "cost" in cfg and cfg["cost"], f"{channel} missing cost"
        assert "rate_limit" in cfg and cfg["rate_limit"], f"{channel} missing rate_limit"
        assert "installed" in cfg and cfg["installed"] is True, f"{channel} not marked as installed"

    def test_total_channels_count(self):
        assert len(CHANNELS) == 19, f"Expected 19 channels, got {len(CHANNELS)}"

    def test_all_new_channels_in_enterprise(self):
        new_channels = [
            "hn_search", "arxiv_search", "wayback_fetch", "wikipedia_search",
            "cloudscraper_fetch", "crawl4ai", "apify_scrape",
            "google_web_search", "claude_analyze", "dns_geo_lookup",
        ]
        enterprise = set(TIER_CHANNELS["SCRAPER_ENTERPRISE"])
        for ch in new_channels:
            assert ch in enterprise, f"{ch} not in SCRAPER_ENTERPRISE"
