"""Strategies and studies from the November 2026 X research digest (docs/research/x-digest.md).

Each rule is a published idea re-implemented by TOP in plain Python, long/flat, signal at
the close. Sources are listed per rule.
"""

from __future__ import annotations

import math

from top import arrays as np

NAN = float("nan")
SECTION = "Quant research"


def _ok(x):
    return x is not None and x == x and not math.isinf(x)


def _list(a):
    return [float(x) for x in (a.tolist() if hasattr(a, "tolist") else a)]


# ---------------------------------------------------------------- building blocks

def kalman_level(close, ratio=0.01):
    """Local-level Kalman filter on log price. ratio = process / measurement noise (smaller = smoother).

    Returns the filtered level (in price units). Causal: each value uses data up to that bar.
    """
    c = _list(close)
    out = [NAN] * len(c)
    level, var = None, 1.0
    q, r = float(ratio), 1.0
    # Measurement noise scaled to the series' typical daily log change, so `ratio` means the same on every stock.
    diffs = [math.log(b / a) for a, b in zip(c, c[1:]) if _ok(a) and _ok(b) and a > 0 and b > 0]
    scale = (sum(d * d for d in diffs) / len(diffs)) if diffs else 1e-4
    q, r = q * scale, scale
    for i, price in enumerate(c):
        if not _ok(price) or price <= 0:
            out[i] = math.exp(level) if level is not None else NAN
            continue
        y = math.log(price)
        if level is None:
            level, var = y, r
        else:
            var += q
            gain = var / (var + r)
            level += gain * (y - level)
            var *= 1 - gain
        out[i] = math.exp(level)
    return out


def hurst_vr(close, window=120, lag=5):
    """Rolling Hurst exponent from the variance ratio of lag-day vs 1-day log returns.

    Var(r_lag) ∝ lag^(2H), so H = ln(Var_lag / Var_1) / (2 ln lag). H ≈ 0.5 random walk,
    above 0.55 trending, below 0.45 mean-reverting. Overlapping lag sums; causal.
    """
    c = _list(close)
    n = len(c)
    logs = [math.log(x) if _ok(x) and x > 0 else NAN for x in c]
    out = [NAN] * n
    for i in range(window + lag, n):
        r1, rq = [], []
        for j in range(i - window + 1, i + 1):
            a, b = logs[j - 1], logs[j]
            if _ok(a) and _ok(b):
                r1.append(b - a)
            a, b = logs[j - lag], logs[j]
            if _ok(a) and _ok(b):
                rq.append(b - a)
        if len(r1) < window // 2 or len(rq) < window // 2:
            continue
        m1, mq = sum(r1) / len(r1), sum(rq) / len(rq)
        v1 = sum((x - m1) ** 2 for x in r1) / (len(r1) - 1)
        vq = sum((x - mq) ** 2 for x in rq) / (len(rq) - 1)
        if v1 > 0 and vq > 0:
            out[i] = math.log(vq / v1) / (2 * math.log(lag))
    return out


def _rsi(close, length=14):
    c = _list(close)
    out = [NAN] * len(c)
    gain = loss = 0.0
    for i in range(1, len(c)):
        change = c[i] - c[i - 1] if _ok(c[i]) and _ok(c[i - 1]) else 0.0
        up, down = max(change, 0.0), max(-change, 0.0)
        if i <= length:
            gain += up / length
            loss += down / length
            if i == length:
                out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
        else:
            gain = (gain * (length - 1) + up) / length
            loss = (loss * (length - 1) + down) / length
            out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def _ema(values, length):
    out, k, level = [NAN] * len(values), 2 / (length + 1), None
    for i, x in enumerate(values):
        if not _ok(x):
            out[i] = level if level is not None else NAN
            continue
        level = x if level is None else level + k * (x - level)
        out[i] = level if i >= length - 1 else NAN
    return out


# ---------------------------------------------------------------- strategies

def tsmom_position(f, p):
    """Time-series momentum: long while the Lookback-day return is positive."""
    lookback = int(p.get("lookback", 252))
    c = _list(f.c)
    out = [NAN] * len(c)
    for i in range(lookback, len(c)):
        a, b = c[i - lookback], c[i]
        out[i] = 1.0 if _ok(a) and _ok(b) and a > 0 and b / a - 1 > 0 else 0.0
    return np.asarray(out, dtype=float)


def kalman_position(f, p):
    """Long while close is above the Kalman level and the level is higher than Slope bars ago."""
    ratio = float(p.get("ratio", 0.01))
    slope = int(p.get("slope", 5))
    c = _list(f.c)
    level = kalman_level(c, ratio)
    warm = max(50, slope + 1)
    out = [NAN] * len(c)
    for i in range(warm, len(c)):
        out[i] = 1.0 if _ok(c[i]) and _ok(level[i]) and _ok(level[i - slope]) and c[i] > level[i] and level[i] > level[i - slope] else 0.0
    return np.asarray(out, dtype=float)


def month_windows(ts, before=5, after=3):
    """1 for bars whose NEXT session falls in the turn-of-month window, else 0.

    The window is the last `before` sessions of a month plus the first `after` sessions of
    the next. Exchange holiday calendars are published in advance, so knowing which session
    ends a month is not look-ahead. The final, unfinished month in the data has no month-end yet.
    """
    months = [str(t)[:7] for t in ts]
    n = len(months)
    in_window = [False] * n
    start = 0
    while start < n:
        end = start
        while end + 1 < n and months[end + 1] == months[start]:
            end += 1
        complete = end + 1 < n
        for k in range(start, end + 1):
            if k - start < after and start > 0:
                in_window[k] = True
            if complete and end - k < before:
                in_window[k] = True
        start = end + 1
    # Signal at the close of bar i is filled at the next open, so mark bar i when bar i+1 is in the window.
    return [1.0 if i + 1 < n and in_window[i + 1] else 0.0 for i in range(n)]


def turn_of_month_position(f, p):
    out = month_windows(f.ts, int(p.get("before", 5)), int(p.get("after", 3)))
    for i in range(min(25, len(out))):
        out[i] = NAN
    return np.asarray(out, dtype=float)


def hurst_route_position(f, p):
    """Trend rule when Hurst says the stock trends, RSI reversion when it mean-reverts, else flat.

    Trend (H > High): long while close > EMA 50 and EMA 20 > EMA 50.
    Reversion (H < Low): enter when RSI 14 < 35, exit when RSI 14 > 55.
    In between (or when the regime flips), positions from the active rule are closed.
    """
    window, high, low = int(p.get("window", 120)), float(p.get("high", 0.55)), float(p.get("low", 0.45))
    c = _list(f.c)
    h = hurst_vr(c, window)
    e20, e50, r = _ema(c, 20), _ema(c, 50), _rsi(c, 14)
    out = [NAN] * len(c)
    holding_rev = False
    for i in range(window + 6, len(c)):
        hi = h[i]
        if not _ok(hi):
            out[i] = 0.0
            holding_rev = False
            continue
        if hi > high:
            holding_rev = False
            out[i] = 1.0 if _ok(e20[i]) and _ok(e50[i]) and c[i] > e50[i] and e20[i] > e50[i] else 0.0
        elif hi < low:
            if holding_rev and _ok(r[i]) and r[i] > 55:
                holding_rev = False
            elif not holding_rev and _ok(r[i]) and r[i] < 35:
                holding_rev = True
            out[i] = 1.0 if holding_rev else 0.0
        else:
            holding_rev = False
            out[i] = 0.0
    return np.asarray(out, dtype=float)


def _num(key, label, default, min_, max_, step=1):
    return {"key": key, "label": label, "type": "number", "default": default, "min": min_, "max": max_, "step": step}


DIGEST = "docs/research/x-digest.md"


def register_strategies(add):
    add("tsmom_12m", "TSMOM 12-month", SECTION,
        "Time-series momentum (Moskowitz, Ooi & Pedersen, 2012): long while the Lookback-day return is positive, flat otherwise.",
        [_num("lookback", "Lookback", 252, 20, 500)], tsmom_position,
        creator="@quantscience_", channel="https://x.com/quantscience_", confidence="HIGH",
        sources=["https://x.com/quantscience_/status/1994755555613696413", "https://x.com/sopersone/status/2075693614588657846"],
        notes="Classic published rule; the account posts the 12-month version and a short 20-day variant.")
    add("kalman_trend", "Kalman trend", SECTION,
        "Long while close is above a local-level Kalman filter of price and the filtered level is rising over Slope bars. Ratio sets smoothness (smaller = smoother).",
        [_num("ratio", "Noise ratio", 0.01, 0.0005, 0.2, 0.0005), _num("slope", "Slope bars", 5, 1, 30)], kalman_position,
        creator="@RuOnChain1", channel="https://x.com/RuOnChain1", confidence="MEDIUM",
        sources=["https://x.com/RuOnChain1/status/2069779422367146180"],
        notes="TOP's own long/flat version of the Kalman-trend idea; parameters are TOP's defaults.")
    add("turn_of_month", "Turn of the month", SECTION,
        "Calendar flow trade: long over the last Before sessions of each month and the first After sessions of the next.",
        [_num("before", "Before month-end", 5, 1, 10), _num("after", "After month start", 3, 0, 10)], turn_of_month_position,
        creator="@quantscience_", channel="https://x.com/quantscience_", confidence="MEDIUM",
        sources=["https://x.com/quantscience_/status/1995175057639805124"],
        notes="The account's version trades US bonds (long before month-end, short after); TOP keeps a long-only window spanning the turn.")
    add("hurst_route", "Hurst regime router", SECTION,
        "Measures the rolling Hurst exponent (variance ratio). Above High: trend rule (close > EMA 50 and EMA 20 > EMA 50). Below Low: RSI reversion (buy < 35, sell > 55). In between: flat.",
        [_num("window", "Window", 120, 60, 250), _num("high", "Trend above", 0.55, 0.5, 0.7, 0.01), _num("low", "Revert below", 0.45, 0.3, 0.5, 0.01)],
        hurst_route_position,
        creator="@RuOnChain1", channel="https://x.com/RuOnChain1", confidence="MEDIUM",
        sources=["https://x.com/RuOnChain1/status/2081397093919236257"],
        notes="Routing thresholds 0.45 / 0.55 follow the post; the trend and reversion legs are TOP's existing rules.")


def _context_series(f, name, pick):
    data = getattr(f, "context", {}) or {}
    rows = data.get(name)
    if rows is None:
        return [NAN] * len(f)
    if isinstance(rows, dict):
        return [rows.get(t, NAN) if rows.get(t) is not None else NAN for t in f.ts]
    return [NAN if r is None or pick(r) is None else pick(r) for r in rows]


def delivery_study(f, p):
    """NSE delivery % per day and its Length-day average. Blank for names without NSE delivery data."""
    length = int(p.get("length", 20))
    pct = _context_series(f, "delivery", lambda r: r)
    avg = [NAN] * len(pct)
    window = []
    for i, x in enumerate(pct):
        window.append(x)
        if len(window) > length:
            window.pop(0)
        vals = [v for v in window if _ok(v)]
        if len(vals) >= length // 2:
            avg[i] = sum(vals) / len(vals)
    return {"delivery": np.asarray(pct, dtype=float), "average": np.asarray(avg, dtype=float)}


def regime_study(f, p):
    """Nifty 50's 20-day volatility percentile over its past year, aligned to this chart's dates."""
    pct = _context_series(f, "regime", lambda r: r.get("vol_pct"))
    return {"vol_pct": np.asarray(pct, dtype=float), "stressed": np.full(len(f), 66.7), "calm": np.full(len(f), 33.3)}


def register_studies(add, price_pane, oscillator_pane):
    credit = {"credit": f"From the X research digest ({DIGEST})"}
    add("kalman_level", "Kalman level", "Moving averages", price_pane,
        [_num("ratio", "Noise ratio", 0.01, 0.0005, 0.2, 0.0005)], ["level"],
        lambda f, p: {"level": np.asarray(kalman_level(f.c, float(p.get("ratio", 0.01))), dtype=float)},
        colors={"level": "#f2a900"}, sources=["https://x.com/RuOnChain1/status/2069779422367146180"], **credit)
    add("hurst", "Hurst exponent", "Price statistics", oscillator_pane,
        [_num("window", "Window", 120, 60, 250)], ["hurst", "trend", "revert"],
        lambda f, p: {"hurst": np.asarray(hurst_vr(f.c, int(p.get("window", 120))), dtype=float),
                      "trend": np.full(len(f), 0.55), "revert": np.full(len(f), 0.45)},
        sources=["https://x.com/RuOnChain1/status/2081397093919236257"], **credit)
    add("delivery_pct", "Delivery %", "Volume", oscillator_pane,
        [_num("length", "Average", 20, 5, 60)], ["delivery", "average"], delivery_study,
        needs=["delivery"], colors={"delivery": "#2962ff", "average": "#f2a900"},
        credit="NSE security-wise delivery data (NSE-traded stocks only)")
    add("market_regime", "Market volatility regime (Nifty)", "Volatility", oscillator_pane,
        [], ["vol_pct", "stressed", "calm"], regime_study,
        needs=["regime"], colors={"vol_pct": "#f2a900", "stressed": "#f23645", "calm": "#089981"},
        sources=["https://x.com/quantscience_/status/2111068435023085672"], **credit)
