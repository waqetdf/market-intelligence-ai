"""Normalized closed candles and read-only market data adapters."""

import asyncio
import csv
from datetime import datetime
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Annotated

import httpx
from pydantic import BaseModel, Field, model_validator

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
             "4h": 14400, "1d": 86400, "1w": 604800}
MT5_INTERVALS = dict(zip(INTERVALS, ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1")))


# Shared pacing includes historical pagination and on-demand chart requests.
next_market_request = 0.0


async def wait_for_market_slot():
    global next_market_request
    now = monotonic()
    slot = max(now, next_market_request)
    next_market_request = slot + 0.2
    if slot > now:
        await asyncio.sleep(slot - now)


class Candle(BaseModel):
    time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @model_validator(mode="after")
    def validate_prices(self):
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(map(isfinite, values)):
            raise ValueError("Non-finite OHLCV")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Inconsistent OHLC")
        if self.volume < 0 or self.close_time <= self.time:
            raise ValueError("Invalid volume or timestamp")
        return self


class Asset(BaseModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9._/-]{0,23}$")]
    source: Annotated[str, Field(pattern=r"^(binance|mt5-csv)$")]
    ticker: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")]


def closed_candles(rows: list[Candle], now: int, limit: int) -> list[Candle]:
    seen = {}
    for candle in rows:
        if candle.close_time > now:
            continue
        if candle.time in seen and seen[candle.time] != candle:
            raise ValueError("Conflicting candles at the same timestamp")
        seen[candle.time] = candle
    return sorted(seen.values(), key=lambda candle: candle.time)[-limit:]


async def get_candles(asset: Asset, interval: str, directory: Path, now: int, limit: int = 300):
    if asset.source == "mt5-csv":
        return await asyncio.to_thread(read_mt5_csv, directory, asset.ticker, interval, now, limit)
    rows = []
    end = now * 1000
    remaining = limit + 1
    async with httpx.AsyncClient(timeout=10) as client:
        while remaining > 0:
            size = min(1000, remaining)
            await wait_for_market_slot()
            response = await client.get(
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": asset.ticker, "interval": interval, "limit": size, "endTime": end},
            )
            response.raise_for_status()
            page = response.json()
            if not page:
                break
            rows.extend(Candle(time=row[0] // 1000, close_time=(row[6] + 1) // 1000,
                               open=row[1], high=row[2], low=row[3], close=row[4], volume=row[5])
                        for row in page)
            if len(page) < size:
                break
            remaining -= len(page)
            end = page[0][0] - 1
    return closed_candles(rows, now, limit)


def read_mt5_csv(directory: Path, ticker: str, interval: str, now: int, limit: int):
    name = f"{ticker}_{MT5_INTERVALS[interval]}.csv"
    path = directory / name
    if not path.is_file():
        snapshots = sorted(directory.glob(f"scan_*_UTC/{name}"), reverse=True)
        if snapshots:
            path = snapshots[0]
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            stamp = datetime.fromisoformat(row["time_utc"])
            if stamp.utcoffset() is None:
                raise ValueError("MT5 timestamps must include a timezone")
            start = int(stamp.timestamp())
            rows.append(Candle(time=start, close_time=start + INTERVALS[interval],
                               open=row["open"], high=row["high"], low=row["low"],
                               close=row["close"], volume=row["tick_volume"]))
    return closed_candles(rows, now, limit)
