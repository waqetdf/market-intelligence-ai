import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import secrets
from time import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
import httpx
from sqlalchemy import JSON, BigInteger, Column, MetaData, String, Table, create_engine, select
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from backend.market import Asset, INTERVALS, get_candles
from backend.news import commentary, feed_urls, fetch_news, relevant_news
from backend.signals import opportunity, replay
from backend.technical import analyze

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
data = Path(os.getenv("MARKET_DATA_DIR", "data"))
metadata = MetaData()
assets = Table("assets", metadata, Column("symbol", String, primary_key=True), Column("payload", JSON))
alerts = Table("alerts", metadata, Column("key", String, primary_key=True), Column("payload", JSON))
decisions = Table("decisions", metadata,
                  Column("symbol", String, primary_key=True),
                  Column("observed_at", BigInteger, primary_key=True), Column("payload", JSON))
settings = Table("settings", metadata, Column("key", String, primary_key=True), Column("payload", JSON))
engine = create_engine(os.getenv("DATABASE_URL", f"sqlite:///{data / 'market.db'}"))
status = {}
cache = {}
provider_slots = asyncio.Semaphore(3)
started_at = int(time())
monitor_state = {}
news_report = {"items": [], "errors": []}
news_checked = 0


class FeedSelection(BaseModel):
    urls: list[str] = Field(max_length=10)


def enabled_feeds():
    with engine.connect() as connection:
        saved = connection.scalar(select(settings.c.payload).where(settings.c.key == "news"))
    allowed = feed_urls()
    return allowed if saved is None else [url for url in saved if url in allowed]


async def refresh_news():
    global news_report, news_checked
    news_report = await fetch_news(enabled_feeds())
    news_checked = int(time())
basic = HTTPBasic(auto_error=False)


def authorized(credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)]):
    password = os.getenv("MARKET_PASSWORD")
    if not password and os.getenv("MARKET_REQUIRE_AUTH") != "1":
        return
    user = os.getenv("MARKET_USER", "admin")
    if not (password and credentials and secrets.compare_digest(credentials.username.encode(), user.encode())
            and secrets.compare_digest(credentials.password.encode(), password.encode())):
        raise HTTPException(401, "Autenticación requerida", headers={"WWW-Authenticate": 'Basic realm="Market"'})


def stored(table):
    with engine.connect() as connection:
        return list(connection.scalars(select(table.c.payload)).all())


async def candles(asset, interval, limit=300):
    now = int(time())
    key = (asset.symbol, asset.source, asset.ticker, interval, limit)
    cached = cache.get(key)
    if cached and now - cached[0] < 30:
        return cached[1]
    try:
        async with provider_slots:
            result = await get_candles(asset, interval, data / "mt5", now, limit=limit)
    except (httpx.HTTPError, OSError, ValueError, KeyError, IndexError) as exc:
        status[f"{asset.symbol} {interval}"] = {"status": "error", "reason": type(exc).__name__}
        raise HTTPException(502, f"Datos no disponibles para {asset.symbol} {interval}") from exc
    status[f"{asset.symbol} {interval}"] = {"status": "ok" if result else "vacío",
                                            "last_close": result[-1].close_time if result else None}
    cache[key] = (now, result)
    return result


async def notify(payload):
    lines = [f"MARKET INTELLIGENCE · {payload['direction'].upper()}",
             f"{payload['symbol']} · {payload['timeframe']} · {payload['price']}",
             datetime.fromtimestamp(payload["observed_at"], timezone.utc).isoformat(),
             *payload["evidence"],
             f"Invalidación: {payload['invalidation']} · Objetivo: {payload['target']}",
             f"Zona: {payload.get('interest_zone', '—')} · R/B: {payload['reward_risk']}",
             "Calidad: pendiente de calibración",
             *payload["risks"],
             "Aviso informativo. No se ha ejecutado ninguna operación."]
    if payload["chart"]:
        lines.append(payload["chart"])
    if payload["news"]:
        lines += [payload["news"][0]["title"], payload["news"][0]["url"]]
    message = "\n".join(lines)
    messages = []
    if discord := os.getenv("DISCORD_WEBHOOK_URL"):
        messages.append(("discord", discord, {"content": message[:1900], "allowed_mentions": {"parse": []}}))
    if (telegram := os.getenv("TELEGRAM_BOT_TOKEN")) and (chat := os.getenv("TELEGRAM_CHAT_ID")):
        messages.append(("telegram", f"https://api.telegram.org/bot{telegram}/sendMessage",
                         {"chat_id": chat, "text": message[:3900]}))
    async with httpx.AsyncClient(timeout=10) as client:
        for channel, url, body in messages:
            try:
                response = await client.post(url, json=body)
                response.raise_for_status()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("Alert delivery failed for %s (%s)", channel, type(exc).__name__)


async def scan_asset(asset):
    frames = await asyncio.gather(*(candles(asset, interval) for interval in INTERVALS),
                                  return_exceptions=True)
    available = {}
    for interval, frame in zip(INTERVALS, frames):
        if isinstance(frame, HTTPException):
            continue
        if isinstance(frame, BaseException):
            raise frame
        available[interval] = frame
    low = available.get("15m")
    if not low or time() - low[-1].close_time > 1800:
        return
    observed = low[-1].close_time
    with engine.connect() as connection:
        exists = connection.scalar(select(decisions.c.observed_at).where(
            decisions.c.symbol == asset.symbol, decisions.c.observed_at == observed))
    if exists is not None:
        return
    snapshots = {}
    for interval, bars in available.items():
        closed = [bar for bar in bars if bar.close_time <= observed]
        if closed and observed - closed[-1].close_time < INTERVALS[interval] * 2:
            snapshots[interval] = analyze(closed)
    current = snapshots["15m"]
    outcome = opportunity(low, snapshots.get("4h"), current, snapshots)
    items = relevant_news(news_report["items"], asset, low, observed)
    if any(item["volatility_watch"] for item in items):
        outcome["risks"].append("Titular reciente asociado a posible volatilidad")
    payload = dict(outcome, news=items, symbol=asset.symbol, timeframe="15m", price=low[-1].close,
                   observed_at=observed, source=asset.source,
                   trends={interval: report["trend"] for interval, report in snapshots.items()},
                   mode="observación en tiempo real",
                   chart=f"https://www.binance.com/en/trade/{asset.ticker}" if asset.source == "binance" else None)
    deliver = False
    try:
        with engine.begin() as connection:
            connection.execute(decisions.insert().values(symbol=asset.symbol,
                                                         observed_at=observed, payload=payload))
            if outcome["direction"] != "sin señal":
                key = f"{asset.symbol}:{outcome['trigger_time']}:{outcome['direction']}"
                try:
                    with connection.begin_nested():
                        connection.execute(alerts.insert().values(key=key, payload=payload))
                    deliver = True
                except IntegrityError:
                    pass
    except IntegrityError:
        return
    if deliver:
        await notify(payload)


async def monitor():
    delay = max(60, int(os.getenv("MARKET_POLL_SECONDS", "60")))
    while True:
        try:
            if int(time()) - news_checked >= 300:
                await refresh_news()
            for item in stored(assets):
                try:
                    await scan_asset(Asset.model_validate(item))
                except Exception:
                    log.exception("Asset scan failed")
            monitor_state.update(last_cycle=int(time()), error=None)
        except Exception as exc:
            monitor_state.update(error=type(exc).__name__)
            log.exception("Monitoring cycle failed")
        await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(_app):
    if os.getenv("MARKET_REQUIRE_AUTH") == "1" and not os.getenv("MARKET_PASSWORD"):
        raise RuntimeError("MARKET_PASSWORD is required")
    global provider_slots, news_checked, news_report
    news_checked = 0
    news_report = {"items": [], "errors": []}
    provider_slots = asyncio.Semaphore(3)
    cache.clear()
    status.clear()
    monitor_state.clear()
    data.mkdir(parents=True, exist_ok=True)
    metadata.create_all(engine)
    task = asyncio.create_task(monitor())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
api = FastAPI(dependencies=[Depends(authorized)], docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", api)


@app.get("/health")
def health():
    return {"status": "ok"}


@api.get("/assets")
def list_assets():
    return stored(assets)


@api.post("/assets", status_code=201)
def add_asset(asset: Asset):
    try:
        with engine.begin() as connection:
            connection.execute(assets.insert().values(symbol=asset.symbol, payload=asset.model_dump()))
    except IntegrityError as exc:
        raise HTTPException(409, "El símbolo ya existe") from exc
    return asset


def lookup(symbol):
    with engine.connect() as connection:
        item = connection.scalar(select(assets.c.payload).where(assets.c.symbol == symbol))
    if item is None:
        raise HTTPException(404, "Activo sin configurar")
    return Asset.model_validate(item)


@api.get("/candles")
async def chart(symbol: str, interval: str = "15m"):
    if interval not in INTERVALS:
        raise HTTPException(422, "Temporalidad no admitida")
    asset = lookup(symbol)
    bars = await candles(asset, interval)
    return {"bars": bars, "technical": analyze(bars), "source": asset.source}


@api.get("/alerts")
def list_alerts():
    return sorted(stored(alerts), key=lambda alert: alert["observed_at"], reverse=True)[:100]


@api.get("/history")
def history(symbol: str | None = None):
    query = select(decisions.c.payload).order_by(decisions.c.observed_at.desc()).limit(100)
    if symbol:
        query = query.where(decisions.c.symbol == symbol)
    with engine.connect() as connection:
        return list(connection.scalars(query))


@api.get("/server")
def server():
    return {"started_at": started_at, "monitor": monitor_state}


@api.get("/status")
def source_status():
    return status


@api.get("/backtest")
async def backtest(
    symbol: str, count: Annotated[int, Query(ge=300, le=5000)] = 3000,
    fee_bps: Annotated[float, Query(ge=0, le=500)] = 10,
    slippage_bps: Annotated[float, Query(ge=0, le=500)] = 5,
):
    asset = lookup(symbol)
    low, high = await asyncio.gather(candles(asset, "15m", count),
                                     candles(asset, "4h", max(300, count // 16 + 150)))
    report = await asyncio.to_thread(replay, low, high, fee_bps, slippage_bps)
    return dict(report, symbol=symbol, timeframe="15m", candle_count=len(low),
                fee_bps=fee_bps, slippage_bps=slippage_bps)


@api.get("/news")
async def news():
    return {**news_report, "checked_at": news_checked or None}


@api.get("/settings")
def read_settings():
    return {"feeds": {"allowed": feed_urls(), "enabled": enabled_feeds()},
            "ai": {"provider": os.getenv("MARKET_AI_PROVIDER", "off"),
                   "model": os.getenv("MARKET_AI_MODEL")},
            "notifications": {"discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
                              "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))}}


@api.put("/settings/feeds")
async def set_feeds(selection: FeedSelection):
    allowed = feed_urls()
    if len(set(selection.urls)) != len(selection.urls) or any(url not in allowed for url in selection.urls):
        raise HTTPException(422, "Selecciona fuentes autorizadas en el servidor")
    statement = settings.update().where(settings.c.key == "news").values(payload=selection.urls)
    with engine.begin() as connection:
        if connection.execute(statement).rowcount == 0:
            try:
                with connection.begin_nested():
                    connection.execute(settings.insert().values(key="news", payload=selection.urls))
            except IntegrityError:
                connection.execute(statement)
    await refresh_news()
    return read_settings()


@api.get("/context")
async def context(symbol: str):
    asset = lookup(symbol)
    bars = await candles(asset, "15m")
    technical = analyze(bars)
    data = {"symbol": symbol, "source": asset.source, "last_close": bars[-1].model_dump() if bars else None,
            "trend": technical["trend"], "events": technical["events"][-8:], "news": relevant_news(news_report["items"], asset, bars, int(time()))}
    return await commentary(data)


distribution = Path("frontend/dist")
if distribution.is_dir():
    @app.get("/", dependencies=[Depends(authorized)])
    def dashboard():
        return FileResponse(distribution / "index.html")

    app.mount("/", StaticFiles(directory=distribution, html=True))
