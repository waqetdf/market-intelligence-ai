import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
import re
from pathlib import Path
from ipaddress import ip_address
import secrets
from time import time
from uuid import uuid4
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
import httpx
from sqlalchemy import JSON, BigInteger, Column, MetaData, String, Table, cast, create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from backend.alerts import notify
from backend.calendar import fetch_schedule, nearby_releases
from backend.forward import evaluate_alert
from backend.local_integrations import INTEGRATION_KEYS, save_local_integrations
from backend.market import Asset, INTERVALS, get_candles
from backend.news import commentary, feed_urls, fetch_news, relevant_news
from backend.signals import CONTEXT_FRAMES, Strategy, assess_quality, default_strategy, opportunity, replay, strategy_signature
from backend.technical import analyze

logging.basicConfig(level=logging.INFO)
# Outbound request URLs may carry webhook or bot credentials.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)
data = Path(os.getenv("MARKET_DATA_DIR", "data"))
metadata = MetaData()
assets = Table("assets", metadata, Column("symbol", String, primary_key=True), Column("payload", JSON))
alerts = Table("alerts", metadata, Column("key", String, primary_key=True), Column("payload", JSON))
decisions = Table("decisions", metadata,
                  Column("symbol", String, primary_key=True),
                  Column("observed_at", BigInteger, primary_key=True), Column("payload", JSON))
settings = Table("settings", metadata, Column("key", String, primary_key=True), Column("payload", JSON))
simulations = Table("simulations", metadata, Column("id", String, primary_key=True),
                    Column("symbol", String, index=True), Column("timeframe", String),
                    Column("created_at", BigInteger), Column("payload", JSON))
forward_results = Table("forward_results", metadata, Column("key", String, primary_key=True),
                        Column("symbol", String, index=True), Column("resolved_at", BigInteger),
                        Column("payload", JSON))
database_url = os.getenv("DATABASE_URL") or URL.create("sqlite", database=str(data / "market.db"))
engine = create_engine(database_url, pool_pre_ping=True)
status = {}
cache = {}
provider_slots = asyncio.Semaphore(3)
started_at = int(time())
monitor_state = {}
news_report = {"items": [], "errors": []}
news_checked = 0
calendar_state = {}


class IntegrationSelection(BaseModel):
    ai: bool
    discord: bool
    telegram: bool


def integration_availability():
    return {
        "ai": os.getenv("MARKET_AI_PROVIDER") in ("ollama", "openai-compatible") and bool(os.getenv("MARKET_AI_MODEL")),
        "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    }


def enabled_integrations():
    configured = integration_availability()
    with engine.connect() as connection:
        saved = connection.scalar(select(settings.c.payload).where(settings.c.key == "integrations")) or {}
    return {key: available and saved.get(key, True) for key, available in configured.items()}


def store_setting(key, payload):
    statement = settings.update().where(settings.c.key == key).values(payload=payload)
    with engine.begin() as connection:
        if connection.execute(statement).rowcount == 0:
            try:
                with connection.begin_nested():
                    connection.execute(settings.insert().values(key=key, payload=payload))
            except IntegrityError:
                connection.execute(statement)


def active_strategy():
    with engine.connect() as connection:
        payload = connection.scalar(select(settings.c.payload).where(settings.c.key == "strategy"))
    return Strategy.model_validate(payload) if payload is not None else default_strategy()


def simulation_history(symbol=None, timeframe=None, limit=30):
    query = select(simulations.c.payload).order_by(simulations.c.created_at.desc()).limit(limit)
    if symbol:
        query = query.where(simulations.c.symbol == symbol)
    if timeframe:
        query = query.where(simulations.c.timeframe == timeframe)
    with engine.connect() as connection:
        return list(connection.scalars(query))


class FeedSelection(BaseModel):
    urls: list[str] = Field(max_length=10)


def configured_feeds():
    initial = feed_urls()
    if os.getenv("MARKET_DESKTOP") != "1":
        return initial
    with engine.connect() as connection:
        saved = connection.scalar(select(settings.c.payload).where(settings.c.key == "feed_catalog"))
    return initial if saved is None else saved


def enabled_feeds():
    with engine.connect() as connection:
        saved = connection.scalar(select(settings.c.payload).where(settings.c.key == "news"))
    allowed = configured_feeds()
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


def chart_link(asset):
    if asset.source == "binance":
        return f"https://www.binance.com/en/trade/{asset.ticker}"
    base = os.getenv("MARKET_DASHBOARD_URL", "").rstrip("/")
    if base and urlsplit(base).scheme in ("https", "http"):
        return base + "/?" + urlencode({"symbol": asset.symbol, "interval": "15m"})
    return None


async def annotate_alert(payload, current):
    data = {"symbol": payload["symbol"], "source": payload["source"],
            "price": payload["price"], "observed_at": payload["observed_at"],
            "trend": current["trend"], "events": payload["patterns"], "news": payload["news"]}
    try:
        return await asyncio.wait_for(commentary(data), timeout=8)
    except TimeoutError:
        return {"text": None}


async def refresh_calendar():
    calendar_state["checked_at"] = int(time())
    try:
        calendar_state.update(items=await fetch_schedule(), error=None)
    except (httpx.HTTPError, ValueError, LookupError) as exc:
        calendar_state.update(error=type(exc).__name__)


def evaluate_pending(symbol, bars):
    if not bars:
        return
    opens = {bar.time: bar for bar in bars}
    timestamp = cast(alerts.c.payload["observed_at"].as_string(), BigInteger)
    query = (select(alerts.c.key, alerts.c.payload)
             .where(alerts.c.payload["symbol"].as_string() == symbol,
                    timestamp >= bars[0].time, timestamp <= bars[-1].time,
                    ~select(forward_results.c.key).where(forward_results.c.key == alerts.c.key).exists()))
    with engine.begin() as connection:
        for key, payload in connection.execute(query).all():
            next_bar = opens.get(payload["observed_at"])
            result = evaluate_alert(payload, next_bar) if next_bar else None
            if result is None:
                continue
            try:
                with connection.begin_nested():
                    connection.execute(forward_results.insert().values(
                        key=key, symbol=symbol, resolved_at=result["resolved_at"], payload=result))
            except IntegrityError:
                pass


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
    if low:
        evaluate_pending(asset.symbol, low)
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
            snapshots[interval] = analyze(closed[-150:])
    current = snapshots["15m"]
    rules = active_strategy()
    outcome = opportunity(low, snapshots.get("4h"), current, snapshots, rules)
    items = relevant_news(news_report["items"], asset, low, observed)
    if any(item["volatility_watch"] for item in items):
        outcome["risks"].append("Titular reciente asociado a posible volatilidad")
    events = nearby_releases(calendar_state.get("items", []), observed, rules.macro_pause_minutes or 30)
    if events:
        outcome["risks"].append("Publicación macroeconómica BLS cercana")
    macro_block = rules.macro_pause_minutes and (events or not calendar_state.get("items") or calendar_state.get("error"))
    if macro_block and outcome["direction"] != "sin señal":
        outcome["risks"].append("Pausa macroeconómica activada o calendario indisponible")
        outcome.update(direction="sin señal", invalidation=None, target=None, reward_risk=None)
    if outcome["direction"] != "sin señal":
        previous = simulation_history(asset.symbol, "15m", limit=1)
        outcome["quality"] = assess_quality(previous[0] if previous else None, observed, strategy_signature(rules))
    payload = dict(outcome, news=items, calendar=events, symbol=asset.symbol, timeframe="15m", price=low[-1].close,
                   observed_at=observed, source=asset.source,
                   trends={interval: report["trend"] for interval, report in snapshots.items()},
                   mode="observación en tiempo real",
                   chart=chart_link(asset))
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
        if callback := getattr(app.state, "desktop_alert", None):
            callback(payload)
        enabled = enabled_integrations()
        if enabled["ai"] and items:
            assessment = await annotate_alert(payload, current)
            if assessment.get("text"):
                payload["assessment"] = assessment
                with engine.begin() as connection:
                    connection.execute(alerts.update().where(alerts.c.key == key).values(payload=payload))
                    connection.execute(decisions.update().where(decisions.c.symbol == asset.symbol,
                                       decisions.c.observed_at == observed).values(payload=payload))
        await notify(payload, enabled)


async def monitor():
    delay = max(60, int(os.getenv("MARKET_POLL_SECONDS", "60")))
    while True:
        try:
            if int(time()) - news_checked >= 300:
                await refresh_news()
            if os.getenv("MARKET_CALENDAR_ENABLED", "1") == "1" and int(time()) - calendar_state.get("checked_at", 0) >= 3600:
                await refresh_calendar()
            for item in stored(assets):
                try:
                    asset = Asset.model_validate(item)
                    if asset.enabled:
                        await scan_asset(asset)
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
    calendar_state.clear()
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
    return [Asset.model_validate(item) for item in stored(assets)]


@api.post("/assets", status_code=201)
def add_asset(asset: Asset):
    try:
        with engine.begin() as connection:
            connection.execute(assets.insert().values(symbol=asset.symbol, payload=asset.model_dump()))
    except IntegrityError as exc:
        raise HTTPException(409, "El símbolo ya existe") from exc
    return asset


class AssetMonitor(BaseModel):
    symbol: str = Field(max_length=24)
    enabled: bool


@api.put("/assets/monitor")
def set_asset_monitor(request: AssetMonitor):
    asset = lookup(request.symbol).model_copy(update={"enabled": request.enabled})
    with engine.begin() as connection:
        connection.execute(assets.update().where(assets.c.symbol == request.symbol)
                           .values(payload=asset.model_dump()))
    return asset


@api.get("/overview")
def overview():
    latest = (select(decisions.c.payload, func.row_number()
                     .over(partition_by=decisions.c.symbol, order_by=decisions.c.observed_at.desc())
                     .label("sequence")).subquery())
    with engine.connect() as connection:
        observations = {item["symbol"]: item for item in connection.scalars(
            select(latest.c.payload).where(latest.c.sequence == 1))}
    return [{"asset": asset, "latest": observations.get(asset.symbol)} for asset in list_assets()]


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
    timestamp = cast(alerts.c.payload["observed_at"].as_string(), BigInteger)
    query = select(alerts.c.payload).order_by(timestamp.desc()).limit(100)
    with engine.connect() as connection:
        return list(connection.scalars(query))


@api.get("/history")
def history(symbol: str | None = None):
    query = select(decisions.c.payload).order_by(decisions.c.observed_at.desc()).limit(100)
    if symbol:
        query = query.where(decisions.c.symbol == symbol)
    with engine.connect() as connection:
        return list(connection.scalars(query))


@api.get("/forward")
def forward(symbol: str):
    lookup(symbol)
    with engine.connect() as connection:
        results = list(connection.scalars(select(forward_results.c.payload)
                       .where(forward_results.c.symbol == symbol)
                       .order_by(forward_results.c.resolved_at.desc()).limit(100)))
    returns = [item["net_return"] for item in results]
    return {"items": results, "count": len(returns),
            "expectancy": sum(returns) / len(returns) if returns else None,
            "positive": sum(value > 0 for value in returns), "mode": "simulación de alertas en vivo"}


@api.get("/server")
def server():
    return {"started_at": started_at, "monitor": monitor_state}


@api.get("/status")
def source_status():
    return status


@api.get("/backtest")
@api.post("/backtest")
async def backtest(
    request: Request, symbol: str, interval: str = "15m", count: Annotated[int, Query(ge=300, le=5000)] = 3000,
    fee_bps: Annotated[float, Query(ge=0, le=500)] = 10,
    slippage_bps: Annotated[float, Query(ge=0, le=500)] = 5,
):
    asset = lookup(symbol)
    context_interval = CONTEXT_FRAMES.get(interval)
    if context_interval is None:
        raise HTTPException(422, "La simulación requiere una temporalidad superior disponible")
    rules = active_strategy()
    if rules.require_fvg and INTERVALS[interval] > 1800:
        raise HTTPException(422, "Con FVG obligatorio, simula entre 1m y 30m")
    context_count = max(300, count * INTERVALS[interval] // INTERVALS[context_interval] + 150)
    requests = [candles(asset, interval, count), candles(asset, context_interval, context_count)]
    if rules.require_fvg:
        requests.append(candles(asset, "5m", count * INTERVALS[interval] // 300 + 150))
    low, high, *lower = await asyncio.gather(*requests)
    report = await asyncio.to_thread(replay, low, high, fee_bps, slippage_bps, interval, rules,
                                     lower[0] if lower else None)
    report.update(id=uuid4().hex, symbol=symbol, timeframe=interval, context_timeframe=context_interval,
                  candle_count=len(low), fee_bps=fee_bps, slippage_bps=slippage_bps,
                  strategy=strategy_signature(rules), created_at=int(time()),
                  bar_end=low[-1].close_time if low else None,
                  exclusions=["noticias", "modelos IA", "eventos macroeconómicos", "operaciones reales"])
    if request.method == "POST":
        with engine.begin() as connection:
            connection.execute(simulations.insert().values(id=report["id"], symbol=symbol, timeframe=interval,
                                                           created_at=report["created_at"], payload=report))
    return report


@api.get("/simulations")
def list_simulations(symbol: str | None = None, interval: str | None = None):
    return simulation_history(symbol, interval)


@api.get("/calendar")
def calendar():
    now = int(time())
    return {"items": [item for item in calendar_state.get("items", []) if item["starts_at"] >= now][:30],
            "checked_at": calendar_state.get("checked_at"), "error": calendar_state.get("error")}


@api.get("/news")
async def news():
    return {**news_report, "checked_at": news_checked or None}


@api.get("/settings")
def read_settings():
    return {"strategy": active_strategy(), "feeds": {"allowed": configured_feeds(), "enabled": enabled_feeds(),
                                                     "editable": os.getenv("MARKET_DESKTOP") == "1"},
            "local_configuration": os.getenv("MARKET_DESKTOP") == "1",
            "ai": {"provider": os.getenv("MARKET_AI_PROVIDER") or "off",
                   "model": os.getenv("MARKET_AI_MODEL")},
            "configured": integration_availability(),
            "integrations": enabled_integrations()}


@api.put("/settings/strategy")
def set_strategy(selection: Strategy):
    store_setting("strategy", selection.model_dump())
    return read_settings()


class LocalIntegration(BaseModel):
    integration: Literal["ai", "discord", "telegram"]
    values: list[str] = Field(max_length=4)
    clear: bool = False


def valid_service_url(url, *, local=False):
    try:
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port == 0:
            return False
        if parsed.scheme == "https":
            return bool(parsed.hostname)
        return local and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        return False


@api.put("/settings/local-integration")
def configure_local_integration(request: LocalIntegration):
    if os.getenv("MARKET_DESKTOP") != "1":
        raise HTTPException(403, "La configuración de credenciales se realiza en el equipo local")
    keys = INTEGRATION_KEYS[request.integration]
    values = [value.strip() for value in request.values]
    if len(values) != len(keys) or any(len(value) > 1024 or "\x00" in value for value in values):
        raise HTTPException(422, "Configuración de integración inválida")
    if not request.clear:
        if request.integration == "ai":
            provider, endpoint, model, _ = values
            if provider not in ("off", "ollama", "openai-compatible"):
                raise HTTPException(422, "Selecciona un proveedor de IA válido")
            if provider != "off" and (not model or not valid_service_url(endpoint, local=provider == "ollama")):
                raise HTTPException(422, "Introduce el modelo y su URL HTTPS o una URL local para Ollama")
        elif request.integration == "discord":
            url, = values
            if not (valid_service_url(url) and urlsplit(url).hostname == "discord.com"
                    and urlsplit(url).port in (None, 443)
                    and re.fullmatch(r"/api/webhooks/[0-9]+/[A-Za-z0-9_-]+", urlsplit(url).path)):
                raise HTTPException(422, "Introduce un webhook oficial de Discord")
        elif not (re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", values[0])
                  and re.fullmatch(r"-?[0-9]+|@[A-Za-z0-9_]+", values[1])):
            raise HTTPException(422, "Introduce el token y el identificador del chat de Telegram")
    try:
        save_local_integrations(data, request.integration, values, request.clear)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, "No se pudo guardar la configuración local") from exc
    return read_settings()


@api.put("/settings/integrations")
def set_integrations(selection: IntegrationSelection):
    configured = integration_availability()
    requested = selection.model_dump()
    if any(active and not configured[key] for key, active in requested.items()):
        raise HTTPException(422, "Configura la integración en el servidor")
    store_setting("integrations", {key: active for key, active in requested.items() if configured[key]})
    return read_settings()


def valid_feed_url(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".")
        if (parsed.scheme != "https" or not host or "." not in host
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.port not in (None, 443) or not re.fullmatch(r"[a-z0-9.-]+", host) or host.endswith((".localhost", ".local", ".internal"))):
            return False
        try:
            ip_address(host)
        except ValueError:
            return True
        return False
    except ValueError:
        return False


@api.put("/settings/feed-catalog")
async def set_feed_catalog(selection: FeedSelection):
    if os.getenv("MARKET_DESKTOP") != "1":
        raise HTTPException(403, "El catálogo se administra con la configuración del despliegue")
    urls = list(dict.fromkeys(selection.urls))
    if any(len(url) > 1024 or not valid_feed_url(url) for url in urls):
        raise HTTPException(422, "Usa URLs HTTPS públicas sin parámetros ni credenciales")
    store_setting("feed_catalog", urls)
    await refresh_news()
    return read_settings()


@api.put("/settings/feeds")
async def set_feeds(selection: FeedSelection):
    allowed = configured_feeds()
    if len(set(selection.urls)) != len(selection.urls) or any(url not in allowed for url in selection.urls):
        raise HTTPException(422, "Selecciona fuentes autorizadas en el servidor")
    store_setting("news", selection.urls)
    await refresh_news()
    return read_settings()


@api.get("/context")
async def context(symbol: str):
    asset = lookup(symbol)
    if not enabled_integrations()["ai"]:
        return {"provider": "off", "text": None}
    bars = await candles(asset, "15m")
    technical = analyze(bars)
    data = {"symbol": symbol, "source": asset.source, "last_close": bars[-1].model_dump() if bars else None,
            "trend": technical["trend"], "events": technical["events"][-8:], "news": relevant_news(news_report["items"], asset, bars, int(time()))}
    return await commentary(data)


distribution = Path(os.getenv("MARKET_FRONTEND_DIR", "frontend/dist"))
if distribution.is_dir():
    @app.get("/", dependencies=[Depends(authorized)])
    def dashboard():
        return FileResponse(distribution / "index.html")

    app.mount("/", StaticFiles(directory=distribution, html=True))
