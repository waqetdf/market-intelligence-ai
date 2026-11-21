from backend.news import parse_feed


def test_feed_retains_sources_and_drops_unusable_links():
    content = b"""<rss><channel><item><title>Rates</title><link>https://example.org/1</link>
    <pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item>
    <item><title>Bad</title><link>javascript:alert(1)</link></item></channel></rss>"""
    assert parse_feed(content, "example.org") == [{
        "title": "Rates", "url": "https://example.org/1",
        "published": "Sat, 21 Nov 2026 10:00:00 GMT", "source": "example.org",
    }]


def test_news_comparison_excludes_unclosed_reaction_and_future_items():
    from backend.market import Asset, Candle
    from backend.news import relevant_news

    def candle(start, close):
        return Candle(time=start, close_time=start + 60, open=close, high=close,
                      low=close, close=close, volume=10)

    asset = Asset(symbol="BTC/USDT", source="binance", ticker="BTCUSDT")
    item = {"title": "Bitcoin rises", "published": "1970-01-01T00:01:00Z",
            "url": "https://example.org/btc", "source": "example.org"}
    bars = [candle(0, 100), candle(60, 110)]
    assert relevant_news([item], asset, bars, 59) == []
    assert relevant_news([item], asset, bars, 119)[0]["price_comparison"] is None
    article, = relevant_news([item], asset, bars, 120)
    assert article["price_comparison"]["to"] == 120
    assert article["sentiment"] == "positivo"


def test_model_can_only_render_classifications_and_known_references():
    import pytest

    from backend.news import render_assessment

    evidence = {"news": [{"title": "Published headline"}], "trend": "lateral"}
    result = render_assessment('{"sentiment":"mixed","context":"mixed","references":[0]}', evidence)
    assert result["references"] == evidence["news"]
    with pytest.raises(ValueError):
        render_assessment('{"sentiment":"positive","context":"consistent","references":[4]}', evidence)
    with pytest.raises(ValueError):
        render_assessment('{"sentiment":"positive","context":"consistent","references":[0],"price":1}', evidence)
