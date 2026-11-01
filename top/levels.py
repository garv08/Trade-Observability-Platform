"""Next-session key levels and chart-pattern breakouts.

The method follows how the X account @TradZoo publishes its daily analysis (studied
from its public posts; no content is copied):

1. Key levels. Four horizontal levels around the last close: an inner resistance
   (long trigger) and inner support (short trigger) just around price, and outer
   resistance / support from recent swings. Each side gets three stepped targets
   towards the outer level, written like "Long above 24550-24600, targets 24700
   24750 24800+".
2. Pattern breakouts. Support and resistance trendlines over a recent window,
   classified as wedge / triangle / channel / range / broadening. A close above
   resistance is a breakout with a buying zone, a stop under support, target 1 at
   the prior swing high and target 2 at the pattern height projected from the
   breakout ("Pattern height = projected target").

Both are causal: every level is computed from bars up to and including the bar
it is shown on, and applies to the next session.
"""

from __future__ import annotations

import math

from top.arrays import asarray
from top.creators import fit_line, rolling_extremes
from top.indicators import atr as _atr

NAN = float("nan")
GREEN = "#089981"
RED = "#f23645"
AMBER = "#f2a900"


def _lst(values):
    return values.tolist() if hasattr(values, "tolist") else list(values)


def _ok(x):
    return x is not None and x == x and not math.isinf(x)


def _p(params, key, default):
    try:
        return type(default)(params.get(key, default))
    except (TypeError, ValueError):
        return default


def nice_step(price):
    """A round price step of about 0.2% (₹50 on 24,500; ₹1 on 500; ₹0.05 on 25)."""
    if not _ok(price) or price <= 0:
        return 1.0
    raw = price * 0.002
    base = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= base * mult:
            return base * mult
    return base * 10


def snap(value, step):
    return round(value / step) * step if _ok(value) else value


# ---------------------------------------------------------------- key levels

def _cluster(prices, tol):
    """Merge swing prices closer than tol; returns (level, touches) sorted by level."""
    levels = []
    for price in sorted(prices):
        # Compare with the cluster's first price, so clusters cannot chain into wide bands.
        if levels and price - levels[-1][2] <= tol:
            group = levels[-1]
            group[0] += price
            group[1] += 1
        else:
            levels.append([price, 1, price])
    return [(total / count, count) for total, count, _ in levels]


def key_levels(f, params):
    """Per-bar R2 > R1 > close > S1 > S2 and the latest plan."""
    h, l, c = _lst(f.h), _lst(f.l), _lst(f.c)
    n = len(c)
    order = _p(params, "order", 5)
    lookback = _p(params, "lookback", 120)
    a = _lst(_atr(f.h, f.l, f.c, 14))
    pivots = rolling_extremes(h, l, order)
    out = {k: [NAN] * n for k in ("r2", "r1", "s1", "s2")}
    k = 0
    known = []
    for i in range(n):
        while k < len(pivots) and pivots[k][0] <= i:
            known.append(pivots[k])
            k += 1
        if i < max(order * 2, 20) or not _ok(a[i]) or a[i] <= 0:
            continue
        recent = [p for p in known if p[1] >= i - lookback]
        prices = [p[2] for p in recent]
        lo_win, hi_win = min(l[max(0, i - lookback) : i + 1]), max(h[max(0, i - lookback) : i + 1])
        # The latest swings are not confirmed yet; recent session extremes keep the inner levels close to price.
        prices += [lo_win, hi_win, h[i], l[i], max(h[max(0, i - 4) : i + 1]), min(l[max(0, i - 4) : i + 1])]
        gap = 0.15 * a[i]
        prices = [x for x in prices if abs(x - c[i]) > gap]
        levels = [lvl for lvl, _ in _cluster(prices, 0.6 * a[i])]
        above = [x for x in levels if x > c[i] + gap]
        below = [x for x in levels if x < c[i] - gap]
        r1 = above[0] if above else c[i] + a[i]
        s1 = below[-1] if below else c[i] - a[i]
        far_above = [x for x in above if x >= r1 + 0.75 * a[i]]
        far_below = [x for x in below if x <= s1 - 0.75 * a[i]]
        r2 = far_above[0] if far_above else r1 + 2 * a[i]
        s2 = far_below[-1] if far_below else s1 - 2 * a[i]
        out["r2"][i], out["r1"][i], out["s1"][i], out["s2"][i] = r2, r1, s1, s2
    return out


def level_plan(levels, close, i=-1):
    """TradZoo-style plan from the levels on bar i (for the next session)."""
    r2, r1, s1, s2 = (levels[k][i] for k in ("r2", "r1", "s1", "s2"))
    if not all(_ok(x) for x in (r2, r1, s1, s2)):
        return None
    step = nice_step(close)
    r1s, s1s = snap(r1, step), snap(s1, step)
    up = [snap(r1 + (r2 - r1) * f, step) for f in (1 / 3, 2 / 3, 1.0)]
    down = [snap(s1 - (s1 - s2) * f, step) for f in (1 / 3, 2 / 3, 1.0)]
    return {
        "step": step,
        "long_zone": (r1s, r1s + step),
        "long_targets": up,
        "short_below": s1s,
        "short_targets": down,
        "r1": r1, "r2": r2, "s1": s1, "s2": s2,
    }


def _fmt(x, step):
    places = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    return f"{x:,.{places}f}"


def describe_plan(plan, close):
    s = plan["step"]
    lz, lt, sb, st = plan["long_zone"], plan["long_targets"], plan["short_below"], plan["short_targets"]
    where = "between the two triggers" if plan["s1"] <= close <= plan["r1"] else ("above the long trigger" if close > plan["r1"] else "below the short trigger")
    return (
        f"Long above {_fmt(lz[0], s)}–{_fmt(lz[1], s)}, targets {_fmt(lt[0], s)} {_fmt(lt[1], s)} {_fmt(lt[2], s)}+. "
        f"Below {_fmt(sb, s)} the bias turns weak, downside {_fmt(st[0], s)} {_fmt(st[1], s)} {_fmt(st[2], s)}−. "
        f"Outer resistance {_fmt(plan['r2'], s)}, outer support {_fmt(plan['s2'], s)}. The close ({_fmt(close, s)}) sits {where}."
    )


def levels_study(f, params):
    """Today's four levels drawn flat across the last Span sessions, like a daily levels chart."""
    levels = key_levels(f, params)
    ts, c = list(f.ts), _lst(f.c)
    n = len(c)
    span = max(5, _p(params, "span", 30))
    lines = {k: [NAN] * n for k in levels}
    for k, values in levels.items():
        latest = values[-1] if values else NAN
        if _ok(latest):
            for i in range(max(0, n - span), n):
                lines[k][i] = latest
    markers = []
    for i in range(max(1, n - 10), n):
        r1, s1 = levels["r1"][i - 1], levels["s1"][i - 1]
        if _ok(r1) and c[i] > r1 >= c[i - 1]:
            markers.append({"time": ts[i], "position": "belowBar", "color": GREEN, "shape": "arrowUp", "text": "Long trigger"})
        elif _ok(s1) and c[i] < s1 <= c[i - 1]:
            markers.append({"time": ts[i], "position": "aboveBar", "color": RED, "shape": "arrowDown", "text": "Below support"})
    return {k: asarray(v, dtype=float) for k, v in lines.items()}, markers


def levels_position(f, params):
    """Long on a close above yesterday's long trigger; exit at the outer resistance or below yesterday's support."""
    levels = key_levels(f, params)
    c = _lst(f.c)
    out, pos, target = [NAN] * len(c), 0.0, NAN
    for i in range(1, len(c)):
        r1, r2, s1 = levels["r1"][i - 1], levels["r2"][i - 1], levels["s1"][i - 1]
        if not all(_ok(x) for x in (r1, r2, s1)):
            continue
        if pos == 0.0 and c[i] > r1 >= c[i - 1]:
            pos, target = 1.0, r2
        elif pos == 1.0 and (c[i] >= target or c[i] < s1):
            pos = 0.0
        out[i] = pos
    return out


# ---------------------------------------------------------------- pattern breakouts

def classify(res_slope, sup_slope, width_start, width_end, atr_now):
    flat = 0.02 * atr_now
    up_r, dn_r = res_slope > flat, res_slope < -flat
    up_s, dn_s = sup_slope > flat, sup_slope < -flat
    converging = width_end < 0.75 * width_start
    diverging = width_end > 1.3 * width_start
    if diverging:
        return "Broadening wedge"
    if converging:
        if dn_r and dn_s:
            return "Falling wedge"
        if up_r and up_s:
            return "Rising wedge"
        if dn_r and not (up_s or dn_s):
            return "Descending triangle"
        if up_s and not (up_r or dn_r):
            return "Ascending triangle"
        if dn_r and up_s:
            return "Symmetrical triangle"
    if dn_r and dn_s:
        return "Descending channel"
    if up_r and up_s:
        return "Rising channel"
    if not (up_r or dn_r or up_s or dn_s):
        return "Range"
    return "Consolidation"


def pattern_scan(f, params):
    """Breakouts of fitted support/resistance patterns. Returns events and the latest pattern."""
    h, l, c = _lst(f.h), _lst(f.l), _lst(f.c)
    n = len(c)
    window = _p(params, "window", 60)
    a = _lst(_atr(f.h, f.l, f.c, 14))
    events, latest = [], None
    last_break = -10**9
    for i in range(window + 1, n):
        if not _ok(a[i]) or a[i] <= 0:
            continue
        hs, ls = h[i - window : i], l[i - window : i]
        rs, rb = fit_line(hs, upper=True)
        ss, sb = fit_line(ls, upper=False)
        width_start = rb - sb
        width_end = (rb + rs * (window - 1)) - (sb + ss * (window - 1))
        if width_start <= 0 or width_end <= 0:
            continue
        res_now, sup_now = rb + rs * window, sb + ss * window
        touches_r = sum(1 for x, v in enumerate(hs) if (rb + rs * x) - v <= 0.3 * a[i])
        touches_s = sum(1 for x, v in enumerate(ls) if v - (sb + ss * x) <= 0.3 * a[i])
        name = classify(rs, ss, width_start, width_end, a[i])
        pattern = {"i": i, "name": name, "start": i - window, "res": (rb, rs), "sup": (sb, ss), "res_now": res_now, "sup_now": sup_now,
                   "height": max(width_start, width_end), "touches": (touches_r, touches_s)}
        valid = touches_r >= 2 and touches_s >= 2 and pattern["height"] >= 2 * a[i]
        if valid:
            latest = pattern
        prev_res = rb + rs * (window - 1)
        if valid and c[i] > res_now and c[i - 1] <= prev_res and i - last_break > window // 3:
            level = res_now
            height = pattern["height"]
            t2 = level + height
            swing_high = max(hs)
            t1 = swing_high if level < swing_high < t2 else level + height / 2
            stop = max(min(l[i - 5 : i + 1]), sup_now) if sup_now < c[i] else min(l[i - 5 : i + 1])
            events.append({**pattern, "level": level, "t1": t1, "t2": t2, "stop": stop, "zone": (level, level + 0.5 * a[i]), "close": c[i]})
            last_break = i
    return {"events": events, "latest": latest}


def pattern_study(f, params):
    out = pattern_scan(f, params)
    ts, n = list(f.ts), len(f.ts)
    upper, lower = [NAN] * n, [NAN] * n
    shown = out["events"][-1] if out["events"] else out["latest"]
    if shown:
        (rb, rs), (sb, ss) = shown["res"], shown["sup"]
        end = min(n - 1, shown["i"] + (10 if shown in out["events"] else 0))
        for x in range(shown["start"], end + 1):
            upper[x] = rb + rs * (x - shown["start"])
            lower[x] = sb + ss * (x - shown["start"])
    markers = [{"time": ts[e["i"]], "position": "belowBar", "color": GREEN, "shape": "arrowUp",
                "text": f"{e['name']} breakout → {e['t2']:.0f}"} for e in out["events"]]
    return {"upper": asarray(upper, dtype=float), "lower": asarray(lower, dtype=float)}, markers


def pattern_position(f, params):
    """Long on a pattern breakout; exit at target 2, a close below the stop, or after Hold bars."""
    out = pattern_scan(f, params)
    c = _lst(f.c)
    hold = _p(params, "hold", 40)
    window = _p(params, "window", 60)
    by_bar = {e["i"]: e for e in out["events"]}
    pos = [NAN] * len(c)
    state, trade, since = 0.0, None, 0
    for i in range(len(c)):
        if i <= window:
            continue
        if state == 1.0:
            since += 1
            if c[i] >= trade["t2"] or c[i] < trade["stop"] or since >= hold:
                state, trade = 0.0, None
        if state == 0.0 and i in by_bar:
            state, trade, since = 1.0, by_bar[i], 0
        pos[i] = state
    return pos


def describe_pattern(f, params):
    out = pattern_scan(f, params)
    c, ts = _lst(f.c), list(f.ts)
    n = len(c)
    step = nice_step(c[-1])
    if out["events"] and n - 1 - out["events"][-1]["i"] <= 20:
        e = out["events"][-1]
        ago = n - 1 - e["i"]
        status = "target 2 reached" if max(c[e["i"]:]) >= e["t2"] else ("stopped out" if min(c[e["i"]:]) < e["stop"] else "in play")
        text = (f"{e['name']} breakout on {ts[e['i']]} ({ago} sessions ago) above {_fmt(e['level'], step)}. "
                f"Buying zone {_fmt(e['zone'][0], step)}–{_fmt(e['zone'][1], step)}, stop below {_fmt(e['stop'], step)}, "
                f"target 1 {_fmt(e['t1'], step)}, target 2 {_fmt(e['t2'], step)} (pattern height {_fmt(e['height'], step)} projected from the breakout). Status: {status}.")
        tone = "bull" if status == "in play" else ("bull-hot" if status.startswith("target") else "bear")
    elif out["latest"] and n - 1 - out["latest"]["i"] <= 5:
        p = out["latest"]
        text = (f"Forming: {p['name'].lower()} over the last {p['i'] - p['start']} sessions, resistance near {_fmt(p['res_now'], step)} and support near {_fmt(p['sup_now'], step)}. "
                f"A daily close above {_fmt(p['res_now'], step)} would be the breakout, with a projected target of {_fmt(p['res_now'] + p['height'], step)}; a close below {_fmt(p['sup_now'], step)} breaks the pattern.")
        tone = "neutral"
    else:
        text = "No clean wedge, triangle, or channel with at least two touches on each side right now."
        tone = "neutral"
    done = [e for e in out["events"] if e["i"] + 40 < n]
    if len(done) >= 3:
        hits = sum(1 for e in done if max(c[e["i"] + 1 : e["i"] + 41]) >= e["t2"])
        text += f" On this stock {len(done)} past breakouts reached target 2 within 40 sessions {100 * hits / len(done):.0f}% of the time."
    return text, tone
