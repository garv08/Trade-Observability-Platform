"""Darvas boxes and a volume-confirmed breakout / trend detector.

Both are causal: every level is known at the close of the bar where it appears.
"""

from __future__ import annotations

import math

from top.arrays import asarray
from top.indicators import atr as _atr

NAN = float("nan")
UP = "#089981"
DOWN = "#f23645"
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


def _marker(time, up, text, shape=None, color=None):
    return {
        "time": time,
        "position": "belowBar" if up else "aboveBar",
        "color": color or (UP if up else DOWN),
        "shape": shape or ("arrowUp" if up else "arrowDown"),
        "text": text,
    }


# ---------------------------------------------------------------- Darvas box

def darvas_boxes(h, l, c, confirm=3):
    """Nicolas Darvas boxes.

    Top: a high that is not exceeded for `confirm` sessions. Bottom: after the top, a low
    that is not undercut for `confirm` sessions. A box is active from the bar its bottom is
    confirmed until a close above the top (breakout) or below the bottom (breakdown).

    Returns (top per bar, bottom per bar, events) where events are (bar, "breakout"|"breakdown", top, bottom).
    """
    n = len(c)
    top_out, bot_out, events = [NAN] * n, [NAN] * n, []
    phase = "top"
    cand_hi, hi_i, hi_count = NAN, -1, 0
    top = NAN
    cand_lo, lo_count = NAN, 0
    box = None
    for i in range(n):
        if not (_ok(h[i]) and _ok(l[i]) and _ok(c[i])):
            continue
        if box is not None:
            b_top, b_bot = box
            top_out[i], bot_out[i] = b_top, b_bot
            if c[i] > b_top:
                events.append((i, "breakout", b_top, b_bot))
            elif c[i] < b_bot:
                events.append((i, "breakdown", b_top, b_bot))
            else:
                continue
            box = None
            phase, cand_hi, hi_i, hi_count = "top", h[i], i, 0
            continue
        if phase == "top":
            if not _ok(cand_hi) or h[i] > cand_hi:
                cand_hi, hi_i, hi_count = h[i], i, 0
            else:
                hi_count += 1
            if hi_count >= confirm:
                top = cand_hi
                window = l[hi_i : i + 1]
                cand_lo = min(window)
                lo_count = (i - hi_i) - max(k for k, v in enumerate(window) if v == cand_lo)
                phase = "bottom"
                if lo_count >= confirm:
                    box = (top, cand_lo)
        elif phase == "bottom":
            if h[i] > top:
                phase, cand_hi, hi_i, hi_count = "top", h[i], i, 0
                continue
            if l[i] < cand_lo:
                cand_lo, lo_count = l[i], 0
            else:
                lo_count += 1
            if lo_count >= confirm:
                box = (top, cand_lo)
        if box is not None:
            top_out[i], bot_out[i] = box
    return top_out, bot_out, events


def darvas_study(f, params):
    ts, h, l, c = list(f.ts), _lst(f.h), _lst(f.l), _lst(f.c)
    top, bot, events = darvas_boxes(h, l, c, _p(params, "confirm", 3))
    markers = [
        _marker(ts[i], kind == "breakout", "Darvas breakout" if kind == "breakout" else "Box broken")
        for i, kind, _, _ in events
    ]
    return {"upper": asarray(top, dtype=float), "lower": asarray(bot, dtype=float)}, markers


def darvas_position(f, params):
    """Long on a close above a Darvas box top (optionally only near the 52-week high).

    The stop is the bottom of the box that was broken; it ratchets up to the bottom of
    each new box that forms while long. Exit on a close below the stop.
    """
    h, l, c = _lst(f.h), _lst(f.l), _lst(f.c)
    near = _p(params, "near_high", 10.0)
    top, bot, events = darvas_boxes(h, l, c, _p(params, "confirm", 3))
    by_bar = {i: (kind, t, b) for i, kind, t, b in events}
    out = [NAN] * len(c)
    pos, stop = 0.0, NAN
    for i in range(len(c)):
        hi252 = max(h[max(0, i - 251) : i + 1])
        if i >= 20:
            out[i] = 0.0
        if pos == 1.0:
            if _ok(bot[i]) and bot[i] > stop:
                stop = bot[i]
            if c[i] < stop:
                pos = 0.0
        event = by_bar.get(i)
        if pos == 0.0 and event and event[0] == "breakout":
            if near <= 0 or c[i] >= hi252 * (1 - near / 100):
                pos, stop = 1.0, event[2]
        if i >= 20:
            out[i] = pos
    return out


# ---------------------------------------------------------------- breakout and trend detector

def breakout_trend(f, params):
    """Volume-confirmed breakouts of the prior N-session range and the trend that follows.

    - Breakout: close above the prior N-session high on volume ≥ vol_mult × 20-day average.
    - Breakdown: close below the prior N-session low on the same volume test.
    - Failed breakout: within 3 sessions of a breakout, a close back below the breakout level.
    - Trend: after a breakout, up-trend while the close stays above a trailing stop
      (highest close since the breakout minus atr_mult × ATR 14).
    """
    ts, h, l, c, v = list(f.ts), _lst(f.h), _lst(f.l), _lst(f.c), _lst(f.v)
    n = _p(params, "length", 20)
    vol_mult = _p(params, "vol_mult", 1.5)
    atr_mult = _p(params, "atr_mult", 3.0)
    a = _lst(_atr(f.h, f.l, f.c, 14))
    size = len(c)
    upper, lower, trail = [NAN] * size, [NAN] * size, [NAN] * size
    state = [0] * size
    events = []
    in_trend, level, best, since = False, NAN, NAN, -1
    for i in range(max(n, 20), size):
        hi = max(h[i - n : i])
        lo = min(l[i - n : i])
        upper[i], lower[i] = hi, lo
        avg_vol = sum(v[i - 20 : i]) / 20
        heavy = avg_vol > 0 and v[i] >= vol_mult * avg_vol
        if in_trend:
            best = max(best, c[i])
            stop = best - atr_mult * a[i] if _ok(a[i]) else NAN
            if i - since <= 3 and c[i] < level:
                events.append((i, "failed", level))
                in_trend = False
            elif _ok(stop) and c[i] < stop:
                events.append((i, "trend_end", stop))
                in_trend = False
            else:
                trail[i] = stop
                state[i] = 1
                continue
        if c[i] > hi and heavy:
            events.append((i, "breakout", hi))
            in_trend, level, best, since = True, hi, c[i], i
            trail[i] = c[i] - atr_mult * a[i] if _ok(a[i]) else NAN
            state[i] = 1
        elif c[i] < lo and heavy:
            events.append((i, "breakdown", lo))
            state[i] = -1
    return {"upper": upper, "lower": lower, "trail": trail, "state": state, "events": events, "ts": ts}


def breakout_study(f, params):
    out = breakout_trend(f, params)
    ts = out["ts"]
    labels = {
        "breakout": (True, "Breakout", "arrowUp", UP),
        "breakdown": (False, "Breakdown", "arrowDown", DOWN),
        "failed": (False, "Failed breakout", "circle", AMBER),
        "trend_end": (False, "Trend ended", "square", AMBER),
    }
    markers = [_marker(ts[i], labels[k][0], labels[k][1], labels[k][2], labels[k][3]) for i, k, _ in out["events"]]
    return {
        "upper": asarray(out["upper"], dtype=float),
        "lower": asarray(out["lower"], dtype=float),
        "trail": asarray(out["trail"], dtype=float),
    }, markers


def breakout_position(f, params):
    out = breakout_trend(f, params)
    warm = max(_p(params, "length", 20), 20)
    return [NAN if i < warm else (1.0 if s == 1 else 0.0) for i, s in enumerate(out["state"])]
