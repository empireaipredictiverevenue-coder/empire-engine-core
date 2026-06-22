---
type: skill
name: social.scraper
version: 1.0.0
description: Social media scraper — extract content, trends, mentions, hashtags, and audience insights across major platforms
tags:
  - domain:social
  - mode:llm
  - pipeline:scraping
timeout_seconds: 60.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - content.seo
  - marketing.publishing
---

# social.scraper

Social media scraper — extract, analyze, and report on content, trends, competitor activity, mentions, hashtags, and audience engagement across Instagram, TikTok, LinkedIn, Twitter/X, YouTube, and Facebook.

## Overview

Scrape and analyze social media content for competitive intelligence, trend detection, content inspiration, audience insights, and brand monitoring. Covers post extraction, profile analysis, hashtag research, comment/engagement scraping, video metadata collection, and cross-platform trend correlation.

Designed for social media managers, content strategists, and growth teams who need structured data from social platforms to inform content strategy, measure share of voice, and identify growth opportunities.

## Capabilities

- **Platform-specific scraping** — extract posts, reels, videos, stories, and carousels from Instagram, TikTok, LinkedIn, Twitter/X, YouTube, and Facebook
- **Profile analysis** — follower counts, engagement rates, posting frequency, content mix (photo vs video vs carousel), top-performing content, growth trajectory
- **Hashtag & keyword research** — trending hashtags per platform, hashtag volume and engagement correlation, keyword mentions across posts, community overlap analysis
- **Competitor monitoring** — competitor profiles and their content strategy, posting cadence, engagement benchmarks, ad creative and sponsored content detection, audience overlap
- **Comment & engagement scraping** — top comments, sentiment analysis, reply patterns, question detection, spam vs real engagement filtering, comment-to-post ratio
- **Trend detection** — viral content patterns, emerging topics per platform, audio/music trends (TikTok/Reels), challenge detection, format trends (carousel vs short-form vs long-form)
- **Video & reel metadata** — view counts, like/comment/share ratios, video duration patterns, caption analysis, music/audio usage, thumbnail analysis, posting time optimization
- **Influencer identification** — accounts with high engagement-to-follower ratios, niche authority scores, brand affinity, audience demographics, collaboration history
- **Brand mention monitoring** — organic brand mentions, sentiment over time, share of voice vs competitors, crisis detection, UGC (user-generated content) identification
- **Audience intelligence** — demographic breakdowns per platform, peak activity times, content format preferences, cross-platform audience overlap, follower growth velocity
- **Export & reporting** — structured JSON output per scraper run, CSV export for analysis, change detection (new vs removed content), scheduled recurring scrape support

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `social.scraper` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("social.scraper", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | Scraping goal (e.g. "monitor competitor activity on Instagram", "find trending hashtags for storm restoration on TikTok", "extract LinkedIn thought leaders in contracting") |
| platforms | list | — | Platforms to scrape: `instagram`, `tiktok`, `linkedin`, `twitter`, `youtube`, `facebook`. Default: all available |
| scrape_type | string | — | What to scrape: `profile`, `hashtag`, `trending`, `competitor`, `mentions`, `comments`, `video_metadata`. Default: `trending` |
| targets | list | — | Specific targets: profile URLs, hashtags (with or without #), keywords, competitor account names |
| lookback_days | integer | — | How far back to scrape: `1`, `7`, `30`, `90`. Default: `7` |
| max_results | integer | — | Maximum posts/profiles to scrape per platform. Default: `50` |
| include_comments | boolean | — | Whether to also scrape comments on extracted posts. Default: `false` |
| include_engagement_metrics | boolean | — | Whether to extract likes, shares, saves, replies. Default: `true` |
| sentiment_analysis | boolean | — | Run sentiment analysis on scraped content and comments. Default: `false` |
| cross_platform | boolean | — | Cross-reference findings across platforms for trend correlation. Default: `false` |
| export_format | string | — | Output format: `json`, `csv`, `both`. Default: `json` |

## Output

A structured scraped data report with:

```json
{
  "scrape_report": {
    "goal": "...",
    "run_timestamp": "2026-06-21T12:00:00Z",
    "platforms_scraped": ["instagram", "tiktok", "linkedin"],
    "total_items": 150,
    "lookback_days": 7
  },
  "by_platform": {
    "instagram": {
      "total_posts": 50,
      "total_profiles": 5,
      "posts": [
        {
          "id": "...",
          "url": "https://instagram.com/p/...",
          "type": "reel|carousel|image|story",
          "caption": "...",
          "hashtags": ["#storm", "#roofing"],
          "posted_at": "2026-06-20T14:30:00Z",
          "profile": "@username",
          "follower_count": 15000,
          "metrics": {
            "likes": 1240,
            "comments": 38,
            "saves": 210,
            "shares": 45,
            "engagement_rate": 8.2
          },
          "media": {
            "type": "video",
            "duration_sec": 45,
            "url": "...",
            "thumbnail_url": "..."
          },
          "top_comments": [
            {"user": "@user1", "text": "...", "likes": 24, "sentiment": "positive"}
          ]
        }
      ],
      "trending_hashtags": [
        {"hashtag": "#stormdamage", "post_count": 12400, "avg_engagement": 6.5},
        {"hashtag": "#roofrepair", "post_count": 8900, "avg_engagement": 4.2}
      ],
      "top_profiles": [
        {"username": "@competitor1", "followers": 45000, "posts_7d": 12, "avg_engagement": 5.1}
      ]
    },
    "tiktok": {
      "total_videos": 50,
      "videos": [
        {
          "id": "...",
          "url": "https://tiktok.com/@user/video/...",
          "caption": "...",
          "hashtags": ["#roofing", "#hail"],
          "sound": {"title": "Original Sound", "artist": "@creator"},
          "posted_at": "2026-06-19T18:00:00Z",
          "metrics": {
            "views": 45000,
            "likes": 8900,
            "comments": 320,
            "shares": 1500,
            "avg_watch_time_pct": 72
          }
        }
      ],
      "trending_sounds": [
        {"title": "Storm Season Anthem", "usage_count": 25000, "avg_views": 35000}
      ]
    },
    "linkedin": {
      "total_posts": 30,
      "total_profiles": 10,
      "posts": [
        {
          "id": "...",
          "url": "https://linkedin.com/posts/...",
          "author": {"name": "John Doe", "headline": "CEO at RoofCo", "connections": 5000},
          "text": "...",
          "posted_at": "2026-06-18T09:00:00Z",
          "metrics": {
            "reactions": 450,
            "comments": 28,
            "reposts": 12
          }
        }
      ]
    },
    "twitter": {
      "total_tweets": 30,
      "tweets": [
        {
          "id": "...",
          "url": "https://twitter.com/user/status/...",
          "author": {"handle": "@username", "followers": 12000},
          "text": "...",
          "posted_at": "2026-06-20T08:00:00Z",
          "metrics": {"likes": 340, "retweets": 85, "replies": 12, "quotes": 5}
        }
      ],
      "trending_topics": [
        {"topic": "Storm Season 2026", "tweet_volume": 125000}
      ]
    }
  },
  "cross_platform_insights": {
    "top_trends": [
      {"trend": "Hail damage claims", "platforms": ["instagram", "tiktok", "twitter"], "total_mentions": 15000, "growth_7d": "+45%"}
    ],
    "share_of_voice": {
      "brand_mentions": {"empire_ai": 120, "competitor_a": 85, "competitor_b": 64},
      "positive_sentiment_pct": 72,
      "neutral_sentiment_pct": 22,
      "negative_sentiment_pct": 6
    },
    "recommended_actions": [
      "Post TikTok video on 'How to spot hail damage' — trending +45% this week",
      "Engage with Instagram posts tagging #stormdamage with contractor lead magnet offer",
      "Monitor LinkedIn competitor @roofco's new video series strategy"
    ]
  }
}
```

## Example

```python
# Execute the skill
result = registry.execute("social.scraper", {
    "params": {
        "goal": "Monitor competitor activity and trending content in storm restoration niche",
        "platforms": ["instagram", "tiktok", "linkedin"],
        "scrape_type": "competitor",
        "targets": ["#stormdamage", "#roofrepair", "@competitor_roofco", "@restoration_inc"],
        "lookback_days": 7,
        "max_results": 25,
        "include_comments": true,
        "sentiment_analysis": true,
        "cross_platform": true
    },
    "context": {"source": "mission-control"}
})
print(result)
```
