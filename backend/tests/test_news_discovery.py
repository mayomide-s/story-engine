from datetime import UTC, datetime

import pytest

from app.schemas.news import NewsDiscoveryRequest, NewsSourceInput
from app.services.news_discovery_service import (
    NewsSourceFetchError,
    _assert_public_host,
    parse_feed_xml,
    rank_news_entries,
)


def test_rss_candidates_are_normalized_deduplicated_and_ranked():
    source_primary = NewsSourceInput(
        name="Primary",
        feed_url="https://example.com/feed.xml",
        source_quality=0.95,
    )
    source_secondary = NewsSourceInput(
        name="Secondary",
        feed_url="https://example.org/feed.xml",
        source_quality=0.70,
    )
    recent_date = "Tue, 18 Aug 2026 10:30:00 GMT"
    stale_date = "Sat, 15 Aug 2026 10:30:00 GMT"

    primary_xml = f"""
    <rss version="2.0">
      <channel>
        <item>
          <title>OpenAI launches a new AI coding product</title>
          <link>https://news.example.com/openai-launch?utm_source=rss</link>
          <description>OpenAI released a new AI tool for developers.</description>
          <pubDate>{recent_date}</pubDate>
        </item>
        <item>
          <title>Old AI story</title>
          <link>https://news.example.com/old-story</link>
          <description>OpenAI old update.</description>
          <pubDate>{stale_date}</pubDate>
        </item>
      </channel>
    </rss>
    """
    secondary_xml = f"""
    <rss version="2.0">
      <channel>
        <item>
          <title>OpenAI launches a new AI coding product</title>
          <link>https://news.example.com/openai-launch</link>
          <description>Duplicate coverage.</description>
          <pubDate>{recent_date}</pubDate>
        </item>
      </channel>
    </rss>
    """

    entries = parse_feed_xml(primary_xml, source_primary)
    entries += parse_feed_xml(secondary_xml, source_secondary)
    request = NewsDiscoveryRequest(
        sources=[source_primary, source_secondary],
        niche_keywords=["openai", "ai", "coding"],
        max_age_hours=36,
        limit=10,
    )
    candidates, deduplicated_count = rank_news_entries(
        entries,
        request,
        now=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )

    assert deduplicated_count == 2
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_name == "Primary"
    assert candidate.url == "https://news.example.com/openai-launch"
    assert set(candidate.matched_keywords) == {
        "openai",
        "ai",
        "coding",
    }
    assert candidate.overall_score > 70


def test_atom_feed_is_supported():
    source = NewsSourceInput(
        name="Atom Source",
        feed_url="https://example.com/atom.xml",
    )
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Nvidia announces new AI chips</title>
        <link href="https://example.com/story?utm_medium=feed" rel="alternate"/>
        <summary>New chips for AI workloads.</summary>
        <updated>2026-08-18T10:00:00Z</updated>
      </entry>
    </feed>
    """

    entries = parse_feed_xml(xml, source)

    assert len(entries) == 1
    assert entries[0]["url"] == "https://example.com/story"
    assert entries[0]["published_at"] == datetime(
        2026,
        8,
        18,
        10,
        0,
        tzinfo=UTC,
    )


def test_private_feed_addresses_are_blocked():
    with pytest.raises(NewsSourceFetchError):
        _assert_public_host("http://127.0.0.1/feed.xml")

    with pytest.raises(NewsSourceFetchError):
        _assert_public_host("http://localhost/feed.xml")


def test_promote_news_candidate_creates_news_image_idea(client):
    payload = {
        "candidate": {
            "candidate_id": "candidate-1",
            "title": "OpenAI launches a new AI coding product",
            "url": "https://news.example.com/openai-launch",
            "source_name": "Primary",
            "published_at": "2026-08-18T10:30:00Z",
            "summary": "OpenAI released a new AI tool for developers.",
            "source_quality": 0.95,
            "matched_keywords": ["openai", "ai", "coding"],
            "freshness_score": 95.0,
            "relevance_score": 88.0,
            "instagram_potential_score": 80.0,
            "source_quality_score": 95.0,
            "overall_score": 90.0,
        }
    }

    response = client.post("/api/news/promote", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["target_platform"] == "instagram"
    assert data["input_config_json"]["content_type"] == "news_image"
    assert (
        data["input_config_json"]["news_source"]["url"]
        == "https://news.example.com/openai-launch"
    )
