"""Market-wide views: breadth, volatility regime, sector rotation, and stock scans.

Ideas from the X research digest (docs/research/x-digest.md), computed from TOP's own
daily bars. Prices are split/bonus adjusted in SQL with the `adjustments` table, the same
factors `store.load_bars` applies, so 52-week highs and lows aren't distorted by splits.
"""

from __future__ import annotations

import math

from top import store

# Breadth counts BSE group A and B companies: regularly traded names, excluding the thin T/X/Z groups.
BREADTH_GROUPS = ("A", "B")
NIFTY = "IDX:NIFTY50"
SECTOR_INDICES = (
    "NIFTYAUTO", "NIFTYBANK", "NIFTYPRIVATEBANK", "NIFTYPSUBANK", "NIFTYFINANCIALSERVICES", "NIFTYNBFC", "NIFTYINSURANCE",
    "NIFTYCAPITALMARKETS", "NIFTYIT", "NIFTYINDIADIGITAL", "NIFTYPHARMA", "NIFTYHEALTHCAREINDEX", "NIFTYHOSPITALS",
    "NIFTYFMCG", "NIFTYINDIACONSUMPTION", "NIFTYCONSUMERDURABLES", "NIFTYRETAIL", "NIFTYMETAL", "NIFTYCOMMODITIES",
    "NIFTYCHEMICALS", "NIFTYCEMENT", "NIFTYENERGY", "NIFTYOIL&GAS", "NIFTYPOWER", "NIFTYREALTY", "NIFTYHOUSING",
    "NIFTYINFRASTRUCTURE", "NIFTYCAPITALGOODS", "NIFTYINDIAMANUFACTURING", "NIFTYINDIADEFENCE", "NIFTYINDIARAILWAYSPSU",
    "NIFTYCPSE", "NIFTYPSE", "NIFTYMNC", "NIFTYMEDIA", "NIFTYTELECOMMUNICATIONS", "NIFTYTRANSPORTATION&LOGISTICS",
    "NIFTYEV&NEWAGEAUTOMOTIVE", "NIFTYINDIATOURISM", "NIFTYRURAL",
)


def adjusted_sql(where="TRUE", since=None):
    """SQL for split/bonus-adjusted daily bars (symbol, ts, open, high, low, close, volume, value) matching `where` on symbols s."""
    since_clause = f"AND b.ts >= DATE '{since}'" if since else ""
    # Each adjustment row covers bars from the previous ex-date up to (not including) its own ex-date,
    # with the product of its factor and every later one. Bars after the last ex-date get 1.
    return f"""
        WITH r AS (
            SELECT symbol,
                   COALESCE(lag(ex_date) OVER (PARTITION BY symbol ORDER BY ex_date), DATE '1900-01-01') AS lo,
                   ex_date AS hi,
                   exp(sum(ln(factor)) OVER (PARTITION BY symbol ORDER BY ex_date DESC
                                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)) AS f
            FROM adjustments WHERE factor > 0
        )
        SELECT b.symbol, b.ts,
               b.open / COALESCE(r.f, 1) AS open, b.high / COALESCE(r.f, 1) AS high, b.low / COALESCE(r.f, 1) AS low,
               b.close / COALESCE(r.f, 1) AS close, b.volume * COALESCE(r.f, 1) AS volume, b.close * b.volume AS value
        FROM bars b
        JOIN symbols s ON s.symbol = b.symbol
        LEFT JOIN r ON r.symbol = b.symbol AND b.ts >= r.lo AND b.ts < r.hi
        WHERE b.interval = '1d' AND ({where}) {since_clause}
    """


def ensure_tables(con):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS market_breadth (
            ts DATE PRIMARY KEY, stocks INTEGER, advances INTEGER, declines INTEGER,
            above50 INTEGER, base50 INTEGER, above200 INTEGER, base200 INTEGER, new_highs INTEGER, new_lows INTEGER, base252 INTEGER
        )
        """
    )


def refresh_breadth(con):
    """Recompute daily breadth over BSE group A/B stocks. Returns days stored."""
    ensure_tables(con)
    groups = ", ".join(f"'{g}'" for g in BREADTH_GROUPS)
    con.execute("DELETE FROM market_breadth")
    con.execute(
        f"""
        INSERT INTO market_breadth
        WITH base AS ({adjusted_sql(f"s.universe = 'bse' AND s.grp IN ({groups})")}),
        w AS (
            SELECT ts, close, high, low,
                   lag(close) OVER s AS prev,
                   avg(close) OVER (s ROWS 49 PRECEDING) AS a50, count(*) OVER (s ROWS 49 PRECEDING) AS n50,
                   avg(close) OVER (s ROWS 199 PRECEDING) AS a200, count(*) OVER (s ROWS 199 PRECEDING) AS n200,
                   max(high) OVER (s ROWS BETWEEN 251 PRECEDING AND 1 PRECEDING) AS hi,
                   min(low) OVER (s ROWS BETWEEN 251 PRECEDING AND 1 PRECEDING) AS lo,
                   count(*) OVER (s ROWS BETWEEN 251 PRECEDING AND 1 PRECEDING) AS n252
            FROM base WINDOW s AS (PARTITION BY symbol ORDER BY ts)
        )
        SELECT ts, COUNT(*),
               SUM(CASE WHEN close > prev THEN 1 ELSE 0 END), SUM(CASE WHEN close < prev THEN 1 ELSE 0 END),
               SUM(CASE WHEN n50 = 50 AND close > a50 THEN 1 ELSE 0 END), SUM(CASE WHEN n50 = 50 THEN 1 ELSE 0 END),
               SUM(CASE WHEN n200 = 200 AND close > a200 THEN 1 ELSE 0 END), SUM(CASE WHEN n200 = 200 THEN 1 ELSE 0 END),
               SUM(CASE WHEN n252 >= 240 AND high > hi THEN 1 ELSE 0 END), SUM(CASE WHEN n252 >= 240 AND low < lo THEN 1 ELSE 0 END),
               SUM(CASE WHEN n252 >= 240 THEN 1 ELSE 0 END)
        FROM w GROUP BY ts
        """
    )
    return con.execute("SELECT COUNT(*) FROM market_breadth").fetchone()[0]


def breadth(con):
    """Daily breadth series, oldest first. Recomputed if the stored series is behind the bars."""
    ensure_tables(con)
    latest_bar = con.execute(
        "SELECT MAX(b.ts) FROM bars b JOIN symbols s ON s.symbol = b.symbol WHERE s.universe = 'bse' AND b.interval = '1d'"
    ).fetchone()[0]
    latest = con.execute("SELECT MAX(ts) FROM market_breadth").fetchone()[0]
    if latest_bar is not None and latest != latest_bar:
        refresh_breadth(con)
    rows = con.execute("SELECT * FROM market_breadth ORDER BY ts").fetchall()
    out = []
    for ts, stocks, adv, dec, a50, b50, a200, b200, nh, nl, b252 in rows:
        out.append({
            "time": str(ts), "stocks": stocks, "advances": adv, "declines": dec,
            "pct_above50": round(100 * a50 / b50, 2) if b50 else None,
            "pct_above200": round(100 * a200 / b200, 2) if b200 else None,
            "new_highs": nh, "new_lows": nl, "nh_nl": (nh or 0) - (nl or 0), "base252": b252,
        })
    # Advance/decline line: cumulative advances minus declines.
    level = 0
    for row in out:
        level += (row["advances"] or 0) - (row["declines"] or 0)
        row["ad_line"] = level
    return out


def _closes(con, symbol):
    return [(b["time"], b["close"]) for b in store.load_bars(con, symbol)]


def realised_vol(closes, length=20):
    """Annualised rolling volatility (%) of daily log returns; None until `length` returns exist."""
    out = [None] * len(closes)
    rets = [None] + [math.log(b / a) if a and b and a > 0 and b > 0 else None for a, b in zip(closes, closes[1:])]
    for i in range(length, len(closes)):
        window = [r for r in rets[i - length + 1:i + 1] if r is not None]
        if len(window) >= length // 2:
            m = sum(window) / len(window)
            var = sum((r - m) ** 2 for r in window) / (len(window) - 1)
            out[i] = math.sqrt(var * 252) * 100
    return out


def regime(con, symbol=NIFTY, length=20, lookback=252):
    """Volatility regime of an index: 20-day realised volatility ranked against its own past year.

    State per day: calm (below the 33rd percentile), stressed (above the 67th), else normal.
    Also reports trend (close above its 200-day average) and drawdown from the 252-day high.
    Causal: each day uses only data up to that day.
    """
    series = _closes(con, symbol)
    if len(series) < length + 30:
        return {"symbol": symbol, "series": [], "latest": None}
    closes = [c for _, c in series]
    vols = realised_vol(closes, length)
    out = []
    for i, (t, c) in enumerate(series):
        v = vols[i]
        past = [x for x in vols[max(0, i - lookback + 1):i + 1] if x is not None]
        pct = None if v is None or len(past) < 60 else round(100 * sum(1 for x in past if x <= v) / len(past), 1)
        state = None if pct is None else "calm" if pct < 33.3 else "stressed" if pct > 66.7 else "normal"
        window = closes[max(0, i - 199):i + 1]
        sma200 = sum(window) / len(window) if len(window) == 200 else None
        high = max(closes[max(0, i - 251):i + 1])
        out.append({"time": t, "close": c, "vol": None if v is None else round(v, 2), "vol_pct": pct, "state": state,
                    "above200": None if sma200 is None else c > sma200, "dd_pct": round(100 * (c / high - 1), 2)})
    return {"symbol": symbol, "series": out, "latest": out[-1]}


def regime_for(con, ts, symbol=NIFTY):
    """{date: regime row} for aligning the market regime to another chart's dates."""
    rows = {r["time"]: r for r in regime(con, symbol)["series"]}
    out, last = [], None
    for t in ts:
        last = rows.get(t, last)
        out.append(last)
    return out


def sector_rotation(con, periods=(21, 63, 126)):
    """Sector indices ranked by 3-month return relative to Nifty, with 1/3/6-month absolute and relative returns."""
    nifty = dict(_closes(con, NIFTY))
    rows = []
    names = dict(con.execute("SELECT symbol, name FROM symbols WHERE universe = 'nse_index'").fetchall())
    for slug in SECTOR_INDICES:
        symbol = f"IDX:{slug}"
        if symbol not in names:
            continue
        series = _closes(con, symbol)
        if len(series) < max(periods) + 1:
            continue
        last_t, last_c = series[-1]
        item = {"symbol": symbol, "name": names[symbol], "close": last_c, "as_of": last_t}
        for n in periods:
            t0, c0 = series[-1 - n]
            ret = (last_c / c0 - 1) * 100 if c0 else None
            n0, n1 = nifty.get(t0), nifty.get(last_t)
            bench = (n1 / n0 - 1) * 100 if n0 and n1 else None
            item[f"ret_{n}"] = None if ret is None else round(ret, 2)
            item[f"rel_{n}"] = None if ret is None or bench is None else round(ret - bench, 2)
        # RRG-style quadrant from 3-month relative strength and its change over the last month.
        rel_now, rel_month_ago = item.get(f"rel_{periods[1]}"), None
        if len(series) > periods[1] + periods[0]:
            t1, c1 = series[-1 - periods[0]]
            t2, c2 = series[-1 - periods[0] - periods[1]]
            n1, n2 = nifty.get(t1), nifty.get(t2)
            if c2 and n1 and n2:
                rel_month_ago = (c1 / c2 - 1) * 100 - (n1 / n2 - 1) * 100
        if rel_now is not None and rel_month_ago is not None:
            rising = rel_now > rel_month_ago
            item["quadrant"] = ("Leading" if rising else "Weakening") if rel_now > 0 else ("Improving" if rising else "Lagging")
        rows.append(item)
    rows.sort(key=lambda r: r.get(f"rel_{periods[1]}") if r.get(f"rel_{periods[1]}") is not None else -999, reverse=True)
    return rows


# ---------------------------------------------------------------- scans

SCANS = {
    "bloodbath": ("Bloodbath: 30–60% below 52-week high",
                  "Liquid stocks 30–60% below their 52-week high and still at least 10% above their 52-week low. Inspired by @stockmarket8058's most-liked series; add your own quality check."),
    "multi_year_breakout": ("Multi-year breakout",
                            "Close above the highest high of the previous 2 years (excluding the last week), with 20-day volume at least 1.5× its 1-year average. Inspired by @stockmarket8058."),
    "weekly_breakout": ("52-week breakout on volume",
                        "Close above the prior 52-week high (excluding the last week) with 5-day volume at least 1.5× its 100-day average."),
    "breakout_soon": ("Breakout soon",
                      "Close within 5% below the prior 52-week high, not yet above it."),
    "leaders": ("Leaders while Nifty falls",
                "Stocks within 3% of their 52-week high. Most telling when Nifty itself is 5% or more below its high (shown above the table). Inspired by @stockmarket8058."),
    "multibagger": ("1-year multibaggers near highs",
                    "1-year return of at least 100% and close within 10% of the 52-week high."),
    "near_low": ("Near 52-week low after a big fall",
                 "Close within 5% of the 52-week low and at least 30% below the 52-week high. Momentum research says these lag on average; use it as a watchlist, not a buy list."),
    "delivery_surge": ("Delivery surge",
                       "Latest delivery % at least 1.5× its 20-day average and at least 50%, on volume at least 2× its 20-day average (NSE-traded stocks)."),
}


_scan_cache = {"key": None, "rows": None, "latest": None}
# BSE stocks, plus NSE stocks with no BSE listing, so a company listed on both appears once.
SCAN_UNIVERSE = ("(s.universe = 'bse' AND s.kind = 'stock') OR (s.universe = 'nse' AND s.isin IS NOT NULL AND NOT EXISTS "
                 "(SELECT 1 FROM symbols x WHERE x.universe = 'bse' AND substr(x.isin, 1, 7) = substr(s.isin, 1, 7)))")


def _scan_key(con):
    from top.delivery import ensure_tables as ensure_delivery

    ensure_delivery(con)
    bars = con.execute("SELECT COUNT(*), MAX(ts) FROM bars").fetchone()
    deliv = con.execute("SELECT COUNT(*), MAX(ts) FROM delivery").fetchone()
    adj = con.execute("SELECT COUNT(*) FROM adjustments").fetchone()[0]
    return (str(store.DB_PATH), *map(str, bars), *map(str, deliv), adj)


def scan_frame(con):
    """Per-stock figures at each BSE stock's latest bar, shared by every scan. Cached until the store changes."""
    key = _scan_key(con)
    if _scan_cache["key"] == key:
        return _scan_cache["rows"], _scan_cache["latest"]
    since = con.execute("SELECT MAX(ts) - INTERVAL 800 DAY FROM bars").fetchone()[0]
    latest = con.execute("SELECT MAX(ts) FROM bars b JOIN symbols s ON s.symbol = b.symbol WHERE s.universe = 'bse'").fetchone()[0]
    sql = f"""
        WITH f AS ({adjusted_sql(SCAN_UNIVERSE, since=since)}),
        w AS (
            SELECT f.symbol, f.ts, f.close, f.high, f.low, f.volume, f.value,
                   row_number() OVER (PARTITION BY f.symbol ORDER BY f.ts DESC) AS rn,
                   lag(f.close) OVER s AS prev,
                   max(f.high) OVER (s ROWS 251 PRECEDING) AS hi252,
                   min(f.low) OVER (s ROWS 251 PRECEDING) AS lo252,
                   max(f.high) OVER (s ROWS BETWEEN 251 PRECEDING AND 5 PRECEDING) AS prior_hi252,
                   max(f.high) OVER (s ROWS BETWEEN 503 PRECEDING AND 5 PRECEDING) AS prior_hi504,
                   count(*) OVER (s ROWS BETWEEN 503 PRECEDING AND 5 PRECEDING) AS n504,
                   lag(f.close, 251) OVER s AS close_252ago,
                   avg(f.volume) OVER (s ROWS 4 PRECEDING) AS v5,
                   avg(f.volume) OVER (s ROWS 19 PRECEDING) AS v20,
                   avg(f.volume) OVER (s ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS v20_prior,
                   avg(f.volume) OVER (s ROWS 99 PRECEDING) AS v100,
                   avg(f.volume) OVER (s ROWS 251 PRECEDING) AS v252,
                   median(f.value) OVER (s ROWS 19 PRECEDING) AS value20,
                   count(*) OVER (s ROWS 251 PRECEDING) AS n252,
                   d.pct AS dpct,
                   avg(d.pct) OVER (s ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS dpct20
            FROM f LEFT JOIN delivery d ON d.symbol = f.symbol AND d.ts = f.ts
            WINDOW s AS (PARTITION BY f.symbol ORDER BY f.ts)
        )
        SELECT w.*, s.name, s.grp FROM w JOIN symbols s ON s.symbol = w.symbol
        WHERE w.rn = 1 AND w.ts >= DATE '{latest}' - INTERVAL 10 DAY AND w.n252 >= 200
    """
    cursor = con.execute(sql)
    cols = [d[0] for d in cursor.description]
    rows = [dict(zip(cols, raw)) for raw in cursor.fetchall()]
    _scan_cache.update(key=key, rows=rows, latest=latest)
    return rows, latest


def _matches(name, r):
    """(keep, score) for one stock under one scan."""
    close, hi, lo = r["close"], r["hi252"], r["lo252"]
    dd = (1 - close / hi) * 100
    from_low = (close / lo - 1) * 100
    ret252 = (close / r["close_252ago"] - 1) * 100 if r["close_252ago"] else None
    if name == "bloodbath":
        return 30 <= dd <= 60 and close >= 1.1 * lo, dd
    if name == "multi_year_breakout":
        keep = bool(r["n504"] and r["n504"] >= 400 and r["prior_hi504"] and close > r["prior_hi504"] and r["v252"] and r["v20"] >= 1.5 * r["v252"])
        return keep, (r["v20"] / r["v252"]) if keep else 0
    if name == "weekly_breakout":
        keep = bool(r["prior_hi252"] and close > r["prior_hi252"] and r["v100"] and r["v5"] >= 1.5 * r["v100"])
        return keep, (r["v5"] / r["v100"]) if keep else 0
    if name == "breakout_soon":
        level = r["prior_hi252"]
        keep = bool(level and 0.95 * level <= close <= level)
        return keep, (-(level - close) / level) if keep else 0
    if name == "leaders":
        return dd <= 3, -dd
    if name == "multibagger":
        return ret252 is not None and ret252 >= 100 and dd <= 10, ret252 or 0
    if name == "near_low":
        return from_low <= 5 and dd >= 30, -from_low
    if name == "delivery_surge":
        keep = bool(r["dpct"] is not None and r["dpct20"] and r["dpct"] >= 50 and r["dpct"] >= 1.5 * r["dpct20"]
                    and r["v20_prior"] and r["volume"] >= 2 * r["v20_prior"])
        return keep, (r["dpct"] / r["dpct20"]) if keep else 0
    raise ValueError("unknown scan")


def scan(con, name, min_value=10.0, limit=200):
    """Run one named scan on every stock (BSE, plus NSE-only names) at its latest bar. Returns rows plus context."""
    if name not in SCANS:
        raise ValueError("unknown scan")
    frame, latest = scan_frame(con)
    rows = []
    for r in frame:
        if not r["close"] or not r["hi252"] or not r["lo252"]:
            continue
        if (r["value20"] or 0) / 1e5 < float(min_value or 0):
            continue
        keep, score = _matches(name, r)
        if not keep:
            continue
        close = r["close"]
        ret252 = (close / r["close_252ago"] - 1) * 100 if r["close_252ago"] else None
        rows.append({
            "symbol": r["symbol"], "name": r["name"], "group": r["grp"], "as_of": str(r["ts"]), "close": round(close, 2),
            "change_pct": round((close / r["prev"] - 1) * 100, 2) if r["prev"] else None,
            "from_high_pct": round(-(1 - close / r["hi252"]) * 100, 2), "from_low_pct": round((close / r["lo252"] - 1) * 100, 2),
            "ret_252_pct": None if ret252 is None else round(ret252, 2),
            "vol_ratio": round(r["v20"] / r["v252"], 2) if r["v252"] else None,
            "value_lakh": round(r["value20"] / 1e5, 1) if r["value20"] else None,
            "delivery_pct": None if r["dpct"] is None else round(r["dpct"], 1),
            "score": score,
        })
    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    for x in rows:
        x.pop("score", None)
    context = {}
    if name == "leaders":
        nifty = regime(con)["latest"]
        context["nifty_dd_pct"] = None if nifty is None else nifty["dd_pct"]
    if name == "delivery_surge":
        from top.delivery import ensure_tables as ensure_delivery

        ensure_delivery(con)
        context["delivery_to"] = str(con.execute("SELECT MAX(ts) FROM delivery").fetchone()[0])
    title, rule = SCANS[name]
    return {"scan": name, "title": title, "rule": rule, "count": len(rows), "rows": rows[:int(limit)], "as_of": str(latest), "context": context,
            "min_value": min_value}


def scan_counts(con, min_value=10.0):
    """How many stocks each scan finds right now."""
    frame, _ = scan_frame(con)
    out = {}
    for name in SCANS:
        n = 0
        for r in frame:
            if r["close"] and r["hi252"] and r["lo252"] and (r["value20"] or 0) / 1e5 >= float(min_value or 0) and _matches(name, r)[0]:
                n += 1
        out[name] = n
    return out
