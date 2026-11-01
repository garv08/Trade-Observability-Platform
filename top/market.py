"""Equal-weight Nifty 50 proxy built from the stored Nifty 50 bars.

Used by strategies that compare one stock with "the market". There is no index
feed in the store, so the proxy is the equal-weight average daily close-to-close
return of every stored name, compounded from 100. Days with fewer than ten names
reporting are skipped.
"""

from __future__ import annotations

import threading

from top import store

_lock = threading.Lock()
_cache: dict = {"key": None, "returns": {}}


def _key():
    with store.session() as con:
        count, last = con.execute("SELECT count(*), max(ts) FROM bars WHERE interval = '1d'").fetchone()
    return (str(store.DB_PATH), int(count or 0), str(last))


def daily_returns() -> dict[str, float]:
    """Equal-weight mean close-to-close return per date, keyed by ISO date."""
    key = _key()
    with _lock:
        if _cache["key"] == key:
            return _cache["returns"]
    with store.session() as con:
        rows = con.execute(
            """
            SELECT b.symbol, b.ts, b.close FROM bars b JOIN symbols s ON s.symbol = b.symbol
            WHERE b.interval = '1d' AND s.universe = 'nifty50' ORDER BY b.symbol, b.ts
            """
        ).fetchall()
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    prev_symbol, prev_close = None, None
    for symbol, ts, close in rows:
        day = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        if symbol == prev_symbol and prev_close and close:
            ret = close / prev_close - 1
            sums[day] = sums.get(day, 0.0) + ret
            counts[day] = counts.get(day, 0) + 1
        prev_symbol, prev_close = symbol, close
    returns = {day: sums[day] / counts[day] for day in sums if counts[day] >= 10}
    with _lock:
        _cache["key"] = key
        _cache["returns"] = returns
    return returns


def aligned_returns(ts: list[str]) -> list[float]:
    """Market return for each date in ts (NaN where unknown)."""
    returns = daily_returns()
    return [returns.get(day, float("nan")) for day in ts]


def aligned_close(ts: list[str]) -> list[float]:
    """Market proxy level for each date in ts, compounded from 100 at the first date."""
    level, out = 100.0, []
    for ret in aligned_returns(ts):
        if ret == ret:
            level *= 1 + ret
        out.append(level)
    return out
