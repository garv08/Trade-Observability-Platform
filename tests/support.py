"""Offline fixtures: a temporary DuckDB filled with synthetic daily bars for all 50 names."""

from __future__ import annotations

import math
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path

import top.store as store
from top.universe import UNIVERSE


def business_days(start: date, count: int) -> list[str]:
    days, current = [], start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def synthetic_rows(symbol: str, count: int = 800) -> list[tuple]:
    """A random walk with slow waves, so trends, ranges, and swing patterns all occur."""
    rng = random.Random(symbol)
    price = 100 + rng.random() * 900
    drift = rng.uniform(-0.0002, 0.0006)
    period = rng.uniform(40, 90)
    rows = []
    for i, day in enumerate(business_days(date(2022, 1, 3), count)):
        wave = 0.012 * math.sin(2 * math.pi * i / period)
        change = drift + wave * 0.35 + rng.gauss(0, 0.013)
        open_ = price * (1 + rng.gauss(0, 0.003))
        close = max(1.0, price * (1 + change))
        high = max(open_, close) * (1 + abs(rng.gauss(0, 0.006)))
        low = min(open_, close) * (1 - abs(rng.gauss(0, 0.006)))
        rows.append((symbol, store.INTERVAL, day, open_, high, low, close, int(rng.uniform(5e5, 5e6))))
        price = close
    return rows


def use_temp_store() -> Path:
    """Point the store at a fresh file in a temp folder and seed every symbol."""
    folder = Path(tempfile.mkdtemp(prefix="top-test-"))
    store.DB_PATH = folder / "test.duckdb"
    store._schema_ready = False
    with store.session() as con:
        store.ensure_schema(con)
        for row in UNIVERSE:
            store.replace_bars(con, row["symbol"], synthetic_rows(row["symbol"]))
    return store.DB_PATH
