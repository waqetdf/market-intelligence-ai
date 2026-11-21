from backend.news import parse_feed


def test_feed_retains_sources_and_drops_unusable_links():
    content = b"""<rss><channel><item><title>Rates</title><link>https://example.org/1</link>
    <pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item>
    <item><title>Bad</title><link>javascript:alert(1)</link></item></channel></rss>"""
    assert parse_feed(content, "example.org") == [{
        "title": "Rates", "url": "https://example.org/1",
        "published": "Sat, 21 Nov 2026 10:00:00 GMT", "source": "example.org",
    }]
