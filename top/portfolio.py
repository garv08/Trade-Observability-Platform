"""Portfolio backtests: rank a universe each month and hold the top N.

TOP's other backtests trade one stock at a time. These rules come from the X research digest
(docs/research/x-digest.md): cross-sectional momentum, low volatility, sector rotation and
ETF momentum with a trend filter.

Mechanics (long only, no leverage):
- Rank at the close of the last trading day of each month, using only data up to that close.
- Trade at the next session's open: sell names that dropped out, rebalance the rest to equal
  weight, buy new names. Costs are charged on every rupee traded.
- Positions are marked at each close. A name with no bar on a day keeps its last close.
- Survivorship: the universe is today's listing, so delisted stocks are missing. This flatters
  results, especially for small caps; the page says so.
"""

from __future__ import annotations

import math
import threading
from array import array

from top import store

UNIVERSES = {
    "nifty50": ("Nifty 50 stocks", "s.universe = 'nifty50'"),
    "bse_a": ("BSE group A stocks", "s.universe = 'bse' AND s.kind = 'stock' AND s.grp = 'A'"),
    "sectors": ("NSE sector indices", None),
    "etf": ("NSE ETFs", "s.universe = 'nse_etf'"),
}

STRATEGIES = [
    {"id": "momentum_12_1", "name": "Momentum 12-1, top N", "universe": "bse_a", "top_n": 20,
     "blurb": "Each month, rank by the return from 12 months ago to 1 month ago (skipping the latest month) and hold the top N equally weighted.",
     "sources": ["https://x.com/quantscience_/status/2003872379815010544", "https://x.com/quantscience_/status/2012932087402176607"],
     "creator": "@quantscience_"},
    {"id": "low_vol", "name": "Low volatility, top N", "universe": "bse_a", "top_n": 20,
     "blurb": "Each month, hold the N names with the lowest volatility of daily returns over the past year, equally weighted.",
     "sources": ["https://x.com/quantscience_/status/2098079855266992349"], "creator": "@quantscience_"},
    {"id": "sector_rotation", "name": "Sector rotation", "universe": "sectors", "top_n": 3,
     "blurb": "Each month, hold the N NSE sector indices with the best 6-month return (as a proxy for sector ETFs or funds).",
     "sources": ["https://x.com/quantscience_/status/2098079864712532268"], "creator": "@quantscience_"},
    {"id": "etf_momentum", "name": "ETF momentum with trend filter", "universe": "etf", "top_n": 3,
     "blurb": "Each month, rank liquid NSE ETFs by 12-month return and hold the top N, but only those above their 10-month (210-day) average; the rest stays in cash.",
     "sources": ["https://x.com/quantscience_/status/2098079844533698638"], "creator": "@quantscience_"},
]
GATES = {
    "none": "No filter",
    "positive": "Only names with a positive score (absolute momentum)",
    "market": "Hold cash while Nifty 50 is below its 200-day average",
}

NAN = float("nan")
_cache_lock = threading.Lock()
_panel_cache = {"key": None, "panel": None}


def catalog():
    return [{**item, "universe_label": UNIVERSES[item["universe"]][0]} for item in STRATEGIES]


def _spec(strategy_id):
    for item in STRATEGIES:
        if item["id"] == strategy_id:
            return item
    raise ValueError("unknown portfolio strategy")


# ---------------------------------------------------------------- data

def load_panel(con, universe):
    """Aligned daily opens/closes/traded value for every member of a universe (split adjusted).

    Returns {"dates": [...], "symbols": [...], "names": {...}, "open": {sym: [..]}, "close": {...}, "value": {...}}
    with None where a symbol has no bar. Cached until the store changes.
    """
    from top.markets import SECTOR_INDICES, adjusted_sql

    if universe not in UNIVERSES:
        raise ValueError("unknown universe")
    count, last = con.execute("SELECT COUNT(*), MAX(ts) FROM bars").fetchone()
    adjustments = con.execute("SELECT COUNT(*) FROM adjustments").fetchone()[0]
    key = (str(store.DB_PATH), universe, int(count or 0), str(last), int(adjustments or 0))
    with _cache_lock:
        if _panel_cache["key"] == key:
            return _panel_cache["panel"]
    where = UNIVERSES[universe][1]
    if universe == "sectors":
        where = "s.symbol IN (" + ", ".join("'IDX:" + slug.replace("'", "''") + "'" for slug in SECTOR_INDICES) + ")"
    with _cache_lock:
        _panel_cache.update(key=None, panel=None)  # free the previous panel before loading a new one
    names = dict(con.execute(f"SELECT s.symbol, s.name FROM symbols s WHERE {where}").fetchall())
    nifty = [str(t) for (t,) in con.execute(
        "SELECT ts FROM bars WHERE symbol = 'IDX:NIFTY50' AND interval = '1d' ORDER BY ts").fetchall()]
    dates = nifty or [str(t) for (t,) in con.execute(f"SELECT DISTINCT ts FROM ({adjusted_sql(where)}) ORDER BY ts").fetchall()]
    index = {d: i for i, d in enumerate(dates)}
    panel = {"dates": dates, "symbols": [], "names": names, "open": {}, "close": {}, "value": {}}
    blank = array("d", [NAN]) * len(dates)
    cursor = con.execute(f"SELECT symbol, ts, open, close, value FROM ({adjusted_sql(where)}) ORDER BY symbol, ts")
    while True:
        chunk = cursor.fetchmany(20000)
        if not chunk:
            break
        for symbol, ts, o, c, v in chunk:
            i = index.get(str(ts))
            if i is None:
                continue
            if symbol not in panel["close"]:
                panel["symbols"].append(symbol)
                panel["open"][symbol] = array("d", blank)
                panel["close"][symbol] = array("d", blank)
                panel["value"][symbol] = array("d", blank)
            panel["open"][symbol][i] = NAN if o is None else o
            panel["close"][symbol][i] = NAN if c is None else c
            panel["value"][symbol][i] = NAN if v is None else v
    with _cache_lock:
        _panel_cache.update(key=key, panel=panel)
    return panel


def load_benchmark(con, dates):
    rows = dict((str(t), c) for t, c in con.execute(
        "SELECT ts, close FROM bars WHERE symbol = 'IDX:NIFTY50' AND interval = '1d' ORDER BY ts").fetchall())
    if not rows:
        return None
    out, last = [], None
    for d in dates:
        last = rows.get(d, last)
        out.append(last)
    return out


# ---------------------------------------------------------------- scoring

def _ok(x):
    return x is not None and x == x


def _px(series, i):
    """The value at i, or None if missing."""
    x = series[i]
    return x if x == x else None


def _at(series, i):
    """Last known value at or before index i, looking back at most 5 bars."""
    for k in range(i, max(-1, i - 6), -1):
        if series[k] == series[k]:
            return series[k]
    return None


def _ret(series, i, back, skip=0):
    a, b = _at(series, i - back), _at(series, i - skip)
    if a and b and a > 0:
        return b / a - 1
    return None


def _vol(series, i, length=252):
    rets = []
    for k in range(i - length + 1, i + 1):
        a, b = series[k - 1], series[k]
        if a == a and b == b and a > 0 and b > 0:
            rets.append(math.log(b / a))
    if len(rets) < length * 0.8:
        return None
    m = sum(rets) / len(rets)
    return math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1) * 252)


def _sma(series, i, length):
    window = [x for x in series[i - length + 1:i + 1] if x == x]
    return sum(window) / len(window) if len(window) >= length * 0.8 else None


def _liquid(panel, symbol, i, min_value_lakh):
    if not min_value_lakh:
        return True
    values = sorted(v for v in panel["value"][symbol][max(0, i - 62):i + 1] if v == v)
    return bool(values) and values[len(values) // 2] / 1e5 >= min_value_lakh


def score(strategy_id, panel, symbol, i):
    """The ranking score at index i (higher is better), or None if the name is not eligible."""
    close = panel["close"][symbol]
    if i < 252 or close[i] != close[i]:
        return None
    present = sum(1 for x in close[i - 251:i + 1] if x == x)
    if present < 200:
        return None
    if strategy_id == "momentum_12_1":
        return _ret(close, i, 252, 21)
    if strategy_id == "low_vol":
        vol = _vol(close, i)
        return None if vol is None else -vol
    if strategy_id == "sector_rotation":
        return _ret(close, i, 126)
    if strategy_id == "etf_momentum":
        sma = _sma(close, i, 210)
        r = _ret(close, i, 252)
        return r if sma and r is not None and close[i] > sma else None
    raise ValueError("unknown portfolio strategy")


def month_ends(dates):
    """Indices of the last trading day of each month (the final, unfinished month excluded)."""
    return [i for i in range(len(dates) - 1) if dates[i][:7] != dates[i + 1][:7]]


# ---------------------------------------------------------------- simulation

def simulate(panel, strategy_id, top_n=20, cost_bps=5.0, capital=1_000_000.0, min_value_lakh=0.0, gate="none", benchmark=None):
    dates = panel["dates"]
    n_days = len(dates)
    rebalance = set(i for i in month_ends(dates) if i >= 252)
    cost = float(cost_bps) / 10_000
    cash, shares = float(capital), {}
    last_close = {}
    equity = [None] * n_days
    log, turnover = [], []
    pending = None  # target list decided at the previous close, traded at this open
    started = None
    top_n = max(1, int(top_n))
    for i in range(n_days):
        if pending is not None:
            targets, decided = pending
            pending = None
            opens = {s: _px(panel["open"][s], i) or _px(panel["close"][s], i) for s in set(shares) | set(targets)}
            # Value the book at this open (fall back to the last close for names that didn't trade).
            value_now = cash + sum(q * (opens.get(s) or last_close.get(s, 0.0)) for s, q in shares.items())
            weight = 1.0 / top_n
            traded = 0.0
            new_shares = {}
            # Sell everything that is not a target, at the open if it traded, else at its last close.
            for s, q in shares.items():
                if s not in targets:
                    px = opens.get(s) or last_close.get(s)
                    proceeds = q * px
                    cash += proceeds * (1 - cost)
                    traded += proceeds
            for s in targets:
                px = opens.get(s)
                if not px:
                    continue
                # Leave room for the cost so the book never borrows.
                want = value_now * weight / (1 + cost) / px
                have = shares.get(s, 0.0)
                delta = want - have
                cash -= delta * px
                cash -= abs(delta) * px * cost
                traded += abs(delta) * px
                new_shares[s] = want
            # Names held but not tradeable today stay as they were.
            for s, q in shares.items():
                if s in targets and s not in new_shares:
                    new_shares[s] = q
            shares = new_shares
            turnover.append(traded / value_now if value_now > 0 else 0.0)
            log.append({"decided": dates[decided], "traded": dates[i], "holdings": sorted(shares),
                        "cash_pct": round(100 * cash / value_now, 1) if value_now > 0 else None})
            if started is None:
                started = i
        for s in list(shares):
            c = panel["close"][s][i]
            if c == c:
                last_close[s] = c
        if started is not None or pending is not None:
            equity[i] = cash + sum(q * last_close.get(s, 0.0) for s, q in shares.items())
        if i in rebalance:
            gated_out = False
            if gate == "market" and benchmark is not None:
                b = [x for x in benchmark[max(0, i - 199):i + 1] if x is not None]
                gated_out = len(b) >= 160 and benchmark[i] is not None and benchmark[i] < sum(b) / len(b)
            ranked = []
            if not gated_out:
                for s in panel["symbols"]:
                    if not _liquid(panel, s, i, min_value_lakh):
                        continue
                    sc = score(strategy_id, panel, s, i)
                    if sc is None or (gate == "positive" and sc <= 0):
                        continue
                    ranked.append((sc, s))
            ranked.sort(key=lambda x: (-x[0], x[1]))
            pending = ([s for _, s in ranked[:top_n]], i)
            if started is None:
                equity[i] = float(capital)
                started = i
    return _report(panel, equity, log, turnover, capital, benchmark, started)


def _stats(values, capital):
    if len(values) < 2 or values[0] <= 0:
        return {}
    years = (len(values) - 1) / 252
    total = values[-1] / values[0] - 1
    cagr = (values[-1] / values[0]) ** (1 / years) - 1 if years > 0 and values[-1] > 0 else None
    peak, dd = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    rets = [b / a - 1 for a, b in zip(values, values[1:]) if a > 0]
    mean = sum(rets) / len(rets) if rets else 0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    sharpe = mean / sd * math.sqrt(252) if sd > 0 else None
    out = {
        "total_return_pct": round(total * 100, 2),
        "cagr_pct": None if cagr is None else round(cagr * 100, 2),
        "max_drawdown_pct": round(dd * 100, 2),
        "sharpe": None if sharpe is None else round(sharpe, 2),
        "years": round(years, 2),
        "ending_equity": round(values[-1] / values[0] * capital, 2),
    }
    if cagr is not None:
        out["cagr_dd"] = round(cagr * 100 / max(abs(dd) * 100, 5.0), 3)
        out["return_dd"] = round(total * 100 / max(abs(dd) * 100, 5.0), 3)
    return out


def _report(panel, equity, log, turnover, capital, benchmark, started):
    dates = panel["dates"]
    points = [(dates[i], v) for i, v in enumerate(equity) if v is not None]
    values = [v for _, v in points]
    metrics = _stats(values, capital)
    metrics["rebalances"] = len(log)
    metrics["avg_turnover_pct"] = round(100 * sum(turnover) / len(turnover), 1) if turnover else None
    metrics["avg_holdings"] = round(sum(len(x["holdings"]) for x in log) / len(log), 1) if log else None
    bench_points = []
    if benchmark is not None and points:
        first = next((benchmark[i] for i, v in enumerate(equity) if v is not None and benchmark[i]), None)
        if first:
            bench_points = [{"time": dates[i], "value": round(capital * benchmark[i] / first, 2)}
                            for i, v in enumerate(equity) if v is not None and benchmark[i]]
            metrics["benchmark"] = _stats([p["value"] for p in bench_points], capital)
    peak, underwater = -math.inf, []
    for t, v in points:
        peak = max(peak, v)
        underwater.append({"time": t, "value": round(100 * (v / peak - 1), 2)})
    holdings = []
    if log:
        last = log[-1]
        i = len(dates) - 1
        since = dates.index(last["traded"]) if last["traded"] in dates else None
        for s in last["holdings"]:
            series = panel["close"][s]
            now = _at(series, i)
            then = _px(panel["open"][s], since) if since is not None else None
            holdings.append({"symbol": s, "name": panel["names"].get(s, s), "close": now,
                             "ret_since_pct": round(100 * (now / then - 1), 2) if now and then else None})
    return {
        "equity": [{"time": t, "value": round(v, 2)} for t, v in points],
        "benchmark": bench_points,
        "underwater": underwater,
        "metrics": metrics,
        "rebalances": log[-24:],
        "holdings": holdings,
        "start": points[0][0] if points else None,
        "end": points[-1][0] if points else None,
    }


def run(con, strategy_id, universe=None, top_n=None, cost_bps=5.0, capital=1_000_000.0, min_value_lakh=None, gate="none", sweep=False):
    spec = _spec(strategy_id)
    universe = universe or spec["universe"]
    top_n = int(top_n or spec["top_n"])
    if min_value_lakh is None:
        min_value_lakh = 0.0 if universe in ("sectors", "nifty50") else 10.0
    gate = gate if gate in GATES else "none"
    panel = load_panel(con, universe)
    if not panel["symbols"]:
        raise ValueError(f"No bars stored for {UNIVERSES[universe][0]} yet. Run Sync history first.")
    benchmark = load_benchmark(con, panel["dates"])
    result = simulate(panel, strategy_id, top_n, cost_bps, capital, min_value_lakh, gate, benchmark)
    result.update({
        "strategy": strategy_id, "name": spec["name"], "universe": universe, "universe_label": UNIVERSES[universe][0],
        "members": len(panel["symbols"]), "top_n": top_n, "gate": gate, "min_value_lakh": min_value_lakh, "cost_bps": cost_bps,
        "methodology": ("Rank at each month-end close using only data to that close; trade at the next open to equal weights; "
                        f"{cost_bps:g} bps cost on every rupee traded; long only, no leverage. The universe is today's listing, "
                        "so delisted names are missing (survivorship bias flatters results)."),
    })
    if sweep:
        sizes = [n for n in (1, 3, 5, 10, 20, 30, 50) if n <= max(1, len(panel["symbols"]) // 2)]
        rows = []
        for n in sizes:
            m = simulate(panel, strategy_id, n, cost_bps, capital, min_value_lakh, gate, benchmark)["metrics"]
            rows.append({"top_n": n, **{k: m.get(k) for k in ("cagr_pct", "max_drawdown_pct", "sharpe", "cagr_dd", "return_dd", "total_return_pct", "avg_turnover_pct")}})
        result["sweep"] = rows
    return result
