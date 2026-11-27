"""Strategies and studies adapted from two Indian Telegram channels.

- @wealthcreator7 (Wealthcreator): "long base" breakouts held on the weekly 40 EMA, and
  21 EMA pullbacks in stacked uptrends. Rules are stated in the channel's case-study posts.
- @PhoenixHarmonicOfficial (Phoenix Harmonic): BAMM (Bat Action Magnetic Move) and the
  channel's own "Half Bat". BAMM rules are stated in posts; Half Bat ratios are read off
  its charts, so they are an inference.

Only the methods are used; no post text or chart is copied. Everything is long/flat and
causal: a position at bar i uses data up to bar i, and the backtest fills at the next open.
See docs/creators.md.
"""

from __future__ import annotations

import math
from datetime import date

from top import harmonics

NAN = float("nan")
WC = "@wealthcreator7"
PH = "@PhoenixHarmonic"
WC_URL = "https://t.me/wealthcreator7"
PH_URL = "https://t.me/PhoenixHarmonicOfficial"


def _num(key, label, default, min_, max_, step=1):
    return {"key": key, "label": label, "type": "number", "default": default, "min": min_, "max": max_, "step": step}


def _lst(values):
    return values.tolist() if hasattr(values, "tolist") else list(values)


def _p(params, key, default):
    try:
        return type(default)(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _ema(values, n):
    out, k, e = [], 2 / (n + 1), None
    for v in values:
        e = v if e is None else e + k * (v - e)
        out.append(e)
    return out


def _flat(n, warm):
    return [NAN] * min(warm, n) + [0.0] * max(n - warm, 0)


def _as_array(xs):
    from top.arrays import asarray

    return asarray(xs, dtype=float)


# ---------------------------------------------------------------- Wealthcreator: long base

def weekly_ema(ts, c, length):
    """Per daily bar: the weekly EMA of closes as if the week ended at this bar (completed weeks plus this close),
    and whether the bar ends its week (a Friday, or the last bar before the next week starts is unknown yet)."""
    weeks = [date.fromisoformat(str(t)[:10]).isocalendar()[:2] for t in ts]
    friday = [date.fromisoformat(str(t)[:10]).weekday() == 4 for t in ts]
    out, k, value, done = [], 2 / (length + 1), None, 0
    for i in range(len(c)):
        if i > 0 and weeks[i] != weeks[i - 1]:
            value = c[i - 1] if value is None else value + k * (c[i - 1] - value)
            done += 1
        out.append(None if value is None or done < length // 2 else value + k * (c[i] - value))
    return out, friday


def long_base_events(f, params):
    """Long-base breakouts and their exits.

    A base is the prior `base` bars: price stayed under its high for at least half of them and never fell
    more than 50% below it. A close above the base high on volume >= vol_mult x the 50-day average, with the
    stop (lower of today's and yesterday's low) within max_risk %, enters. Exit on a close below the stop, or a
    Friday close below the weekly EMA(trail)."""
    base = max(_p(params, "base", 250), 60)
    max_risk = _p(params, "max_risk", 8.0)
    vol_mult = _p(params, "vol_mult", 1.5)
    trail = max(_p(params, "trail", 40), 5)
    capped = base // 2
    _, h, l, c, v = (_lst(x) for x in (f.o, f.h, f.l, f.c, f.v))
    n = len(c)
    wema, friday = weekly_ema(f.ts, c, trail)
    vavg, acc = [None] * n, 0.0
    for i in range(n):
        acc += v[i]
        if i >= 50:
            acc -= v[i - 50]
            vavg[i] = acc / 50
    trades, holding = [], None
    bases = [None] * n
    for i in range(base + 1, n):
        lo = i - base
        window = h[lo:i]
        top = max(window)
        top_at = lo + window.index(top)
        floor = min(l[lo:i])
        valid = i - top_at >= capped and floor >= 0.5 * top
        if valid:
            bases[i] = (top, floor)
        if holding is None:
            if not (valid and c[i] > top):
                continue
            if vol_mult > 0 and (vavg[i] is None or v[i] < vol_mult * vavg[i]):
                continue
            stop = min(l[i], l[i - 1])
            if (c[i] - stop) / c[i] * 100 > max_risk:
                continue
            holding = {"entry": i, "stop": stop, "top": top, "floor": floor, "base_start": lo}
        elif c[i] < holding["stop"] or (friday[i] and wema[i] is not None and c[i] < wema[i]):
            holding.update(exit=i, reason="stop" if c[i] < holding["stop"] else f"weekly EMA {trail}")
            trades.append(holding)
            holding = None
    if holding is not None:
        holding.update(exit=n, reason="open")
        trades.append(holding)
    return trades, bases, wema


def long_base_position(f, params):
    n = len(f)
    pos = _flat(n, max(_p(params, "base", 250), 60) + 1)
    for t in long_base_events(f, params)[0]:
        for j in range(t["entry"], t["exit"]):
            pos[j] = 1.0
    return pos


def long_base_study(f, params):
    trades, bases, wema = long_base_events(f, params)
    top = [b[0] if b else NAN for b in bases]
    floor = [b[1] if b else NAN for b in bases]
    markers = []
    for t in trades:
        markers.append({"time": f.ts[t["entry"]], "position": "belowBar", "color": "#089981", "shape": "arrowUp", "text": "Long base breakout"})
        if t["reason"] != "open":
            markers.append({"time": f.ts[t["exit"]], "position": "aboveBar", "color": "#787b86", "shape": "circle", "text": f"exit ({t['reason']})"})
    return {"base_top": _as_array(top), "base_floor": _as_array(floor), "weekly_ema": _as_array([NAN if x is None else x for x in wema])}, markers


def describe_long_base(f, params):
    trades, bases, wema = long_base_events(f, params)
    c = _lst(f.c)
    base = max(_p(params, "base", 250), 60)
    parts, tone = [], "neutral"
    if trades and trades[-1]["reason"] == "open":
        t = trades[-1]
        parts.append(f"In a long-base trade since {f.ts[t['entry']]} (broke out of a {base}-session base at {t['top']:,.2f}); "
                     f"it is held until a Friday close below the weekly EMA {_p(params, 'trail', 40)} ({wema[-1]:,.2f} now) or below the stop {t['stop']:,.2f}.")
        tone = "bull"
    elif bases[-1]:
        top, floor = bases[-1]
        gap = (top / c[-1] - 1) * 100
        parts.append(f"A {base}-session base is in place: resistance {top:,.2f}, floor {floor:,.2f}. "
                     f"Close is {gap:.1f}% below the breakout level; Wealthcreator buys only the breakout day, on good volume, with the stop within 8%.")
        tone = "bull" if gap < 3 else "neutral"
    else:
        parts.append(f"No long base right now: price set a new {base}-session high recently or fell more than half from it.")
    done = [t for t in trades if t["reason"] != "open"]
    if done:
        rets = [(c[t["exit"]] / c[t["entry"]] - 1) * 100 for t in done]
        parts.append(f"On this stock the rule made {len(done)} completed trades, {sum(r > 0 for r in rets)} up, average {sum(rets) / len(rets):+.1f}% close to close.")
    return " ".join(parts), tone


# ---------------------------------------------------------------- Wealthcreator: 21 EMA pullback

def ema21_position(f, params):
    c, l = _lst(f.c), _lst(f.l)
    exit_len = max(_p(params, "exit_ema", 50), 5)
    e21, e50, e200, ex = _ema(c, 21), _ema(c, 50), _ema(c, 200), _ema(c, exit_len)
    n = len(c)
    pos, holding = _flat(n, 200), False
    for i in range(200, n):
        if not holding:
            holding = e21[i] > e50[i] > e200[i] and l[i] <= e21[i] * 1.005 and c[i] > e21[i]
        elif c[i] < ex[i]:
            holding = False
        pos[i] = 1.0 if holding else 0.0
    return pos


# ---------------------------------------------------------------- Phoenix Harmonic: BAMM and Half Bat

def _pivots(h, l, swing):
    out = []
    for idx, px, kind in harmonics.zigzag(h, l, swing):
        known = harmonics._confirm_index(h, l, idx, px, kind == -1, swing)
        if known is not None:
            out.append((idx, px, kind, known))
    return out


def _take(trades, c, max_hold, n):
    """Run candidate trades in entry order, one at a time; exit on target, stop, or time."""
    taken, busy = [], -1
    for t in sorted(trades, key=lambda row: row["entry"]):
        if t["entry"] <= busy:
            continue
        end = min(n, t["entry"] + max_hold)
        exit_, reason = end, "time" if end < n else "open"
        for j in range(t["entry"] + 1, end):
            if c[j] >= t["target"]:
                exit_, reason = j, "target"
                break
            if c[j] < t["stop"]:
                exit_, reason = j, "stop"
                break
        taken.append(dict(t, exit=exit_, reason=reason))
        busy = exit_
    return taken


BAMM_WAIT = 60


def bamm_setups(f, params):
    """Bullish BAMM: X high, A low, B high retracing 0.382-0.618 of XA, then a pullback C holding 0.382-0.886 of AB.
    A close above B is the trigger; D (A + 0.886 XA) is the target and a close below C the stop."""
    swing = _p(params, "swing", 5.0)
    h, l, c = _lst(f.h), _lst(f.l), _lst(f.c)
    n = len(c)
    out = []
    piv = _pivots(h, l, swing)
    for k in range(2, len(piv)):
        (ix, x, kx, _), (ia, a, ka, _), (ib, b, kb, known) = piv[k - 2 : k + 1]
        if (kx, ka, kb) != (1, -1, 1) or x <= a or not (0.382 <= (b - a) / (x - a) <= 0.618):
            continue
        cl, ci, state, entry = b, ib, "waiting", None
        for i in range(known, min(n, known + BAMM_WAIT)):
            if l[i] < cl:
                cl, ci = l[i], i
            if cl < a:
                state = "failed"
                break
            if c[i] > b:
                state = "triggered" if 0.382 <= (b - cl) / (b - a) <= 0.886 else "no C"
                entry = i if state == "triggered" else None
                break
        else:
            if known + BAMM_WAIT <= n:
                state = "expired"
        out.append({"points": [(ix, x), (ia, a), (ib, b), (ci, cl)], "x": x, "a": a, "b": b, "c": cl, "known": known,
                    "state": state, "entry": entry, "stop": cl, "target": a + 0.886 * (x - a)})
    return out


def bamm_trades(f, params):
    c = _lst(f.c)
    cands = [s for s in bamm_setups(f, params) if s["state"] == "triggered"]
    return _take(cands, c, max(_p(params, "max_hold", 60), 1), len(c))


def half_bat_setups(f, params):
    """Bullish Half Bat: after an X low -> A high leg of at least min_leg %, price pulls back to 0.5 of XA before
    making a new high. A close above the prior bar's high (within 20 bars of the touch) enters; the stop is a
    close below 0.886 of XA (where Phoenix says the Half Bat turns into a full Bat), the target is A."""
    swing = _p(params, "swing", 5.0)
    min_leg = _p(params, "min_leg", 10.0)
    o, h, l, c = (_lst(x) for x in (f.o, f.h, f.l, f.c))
    n = len(c)
    out = []
    piv = _pivots(h, l, swing)
    for k in range(1, len(piv)):
        (ix, x, kx, _), (ia, a, ka, known) = piv[k - 1 : k + 1]
        if (kx, ka) != (-1, 1) or (a - x) / x * 100 < min_leg:
            continue
        zone, stop = a - 0.5 * (a - x), a - 0.886 * (a - x)
        touch, state, entry = None, "waiting", None
        for i in range(known, min(n, known + 60)):
            if h[i] > a:
                state = "new high"
                break
            if l[i] <= zone:
                touch, state = i, "in zone"
                break
        else:
            if known + 60 <= n:
                state = "expired"
        if touch is not None:
            for j in range(touch + 1, min(n, touch + 20)):
                if c[j] < stop:
                    state = "failed"
                    break
                if c[j] > h[j - 1]:
                    entry, state = j, "triggered"
                    break
            else:
                if touch + 20 <= n:
                    state = "expired"
        out.append({"points": [(ix, x), (ia, a)], "x": x, "a": a, "zone": zone, "stop": stop, "target": a,
                    "known": known, "touch": touch, "state": state, "entry": entry})
    return out


def half_bat_trades(f, params):
    c = _lst(f.c)
    cands = [s for s in half_bat_setups(f, params) if s["state"] == "triggered"]
    return _take(cands, c, max(_p(params, "max_hold", 60), 1), len(c))


def _position(trades, n):
    pos = _flat(n, 30)
    for t in trades:
        for j in range(t["entry"], t["exit"]):
            pos[j] = 1.0
    return pos


def bamm_position(f, params):
    return _position(bamm_trades(f, params), len(f))


def half_bat_position(f, params):
    return _position(half_bat_trades(f, params), len(f))


def _line(ts, start, end, value, label):
    return [{"time": ts[start], "value": round(value, 2), "label": label}, {"time": ts[end], "value": round(value, 2), "label": label}]


def _trade_markers(f, trades, label):
    markers = []
    for t in trades:
        markers.append({"time": f.ts[t["entry"]], "position": "belowBar", "color": "#089981", "shape": "arrowUp", "text": label})
        if t["reason"] != "open":
            markers.append({"time": f.ts[t["exit"]], "position": "aboveBar", "color": "#787b86", "shape": "circle", "text": t["reason"]})
    return markers


def bamm_study(f, params):
    trades = bamm_trades(f, params)
    last = len(f) - 1
    drawings = []
    for s in [s for s in bamm_setups(f, params) if s["state"] == "waiting"][-3:]:
        legs = [{"time": f.ts[i], "value": round(px, 2), "label": lab} for (i, px), lab in zip(s["points"], "XABC")]
        start = s["points"][2][0]
        drawings.append({
            "name": "BAMM (waiting for a close above B)", "side": "bull", "color": "#ff9800", "time": f.ts[start],
            "confirmed": None, "prz": round(s["target"], 2), "hop": None, "t1": None, "t2": None,
            "ratios": {"b": round((s["b"] - s["a"]) / (s["x"] - s["a"]), 3)},
            "legs": legs,
            "guides": [_line(f.ts, start, last, s["b"], "B trigger"), _line(f.ts, start, last, s["target"], "D target"),
                       _line(f.ts, start, last, s["c"], "C stop")],
        })
    return {}, sorted(_trade_markers(f, trades, "BAMM"), key=lambda m: m["time"]), drawings


def half_bat_study(f, params):
    trades = half_bat_trades(f, params)
    last = len(f) - 1
    drawings = []
    for s in [s for s in half_bat_setups(f, params) if s["state"] in ("waiting", "in zone")][-3:]:
        start = s["points"][0][0]
        drawings.append({
            "name": f"Half Bat ({s['state']})", "side": "bull", "color": "#9c27b0", "time": f.ts[start],
            "confirmed": None, "prz": round(s["zone"], 2), "hop": round(s["stop"], 2), "t1": None, "t2": round(s["target"], 2),
            "ratios": {},
            "legs": [{"time": f.ts[i], "value": round(px, 2), "label": lab} for (i, px), lab in zip(s["points"], "XA")],
            "guides": [_line(f.ts, s["points"][1][0], last, s["zone"], "0.5 zone"), _line(f.ts, s["points"][1][0], last, s["stop"], "0.886 stop")],
        })
    return {}, sorted(_trade_markers(f, trades, "Half Bat"), key=lambda m: m["time"]), drawings


def _record(c, trades):
    done = [t for t in trades if t["reason"] != "open"]
    if not done:
        return ""
    rets = [(c[t["exit"]] / c[t["entry"]] - 1) * 100 for t in done]
    return f" On this stock the rule made {len(done)} completed trades, {sum(r > 0 for r in rets)} up, average {sum(rets) / len(rets):+.1f}% close to close."


def describe_bamm(f, params):
    c = _lst(f.c)
    trades = bamm_trades(f, params)
    live = [s for s in bamm_setups(f, params) if s["state"] == "waiting"]
    if trades and trades[-1]["reason"] == "open":
        t = trades[-1]
        text, tone = (f"BAMM trade open since {f.ts[t['entry']]}: target D {t['target']:,.2f}, stop on a close below C {t['stop']:,.2f}.", "bull")
    elif live:
        s = live[-1]
        text, tone = (f"Live BAMM setup: a close above B {s['b']:,.2f} triggers it, with D {s['target']:,.2f} as the magnetic target and C {s['c']:,.2f} as support.", "neutral")
    else:
        text, tone = "No bullish BAMM setup is live.", "neutral"
    return text + _record(c, trades), tone


def describe_half_bat(f, params):
    c = _lst(f.c)
    trades = half_bat_trades(f, params)
    live = [s for s in half_bat_setups(f, params) if s["state"] in ("waiting", "in zone")]
    if trades and trades[-1]["reason"] == "open":
        t = trades[-1]
        text, tone = (f"Half Bat trade open since {f.ts[t['entry']]}: target A {t['target']:,.2f}, stop on a close below {t['stop']:,.2f}.", "bull")
    elif live:
        s = live[-1]
        where = "price is in the zone; wait for a close above the prior day's high" if s["state"] == "in zone" else "waiting for price to reach it"
        text, tone = (f"Half Bat zone at {s['zone']:,.2f} (0.5 of the {s['x']:,.2f} to {s['a']:,.2f} rally), stop {s['stop']:,.2f}: {where}.",
                      "bull" if s["state"] == "in zone" else "neutral")
    else:
        text, tone = "No bullish Half Bat zone is live.", "neutral"
    return text + _record(c, trades), tone


READERS = {"wc_long_base": describe_long_base, "ph_bamm": describe_bamm, "ph_half_bat": describe_half_bat}

WHAT = {
    "wc_long_base": "Long base (method from the Wealthcreator Telegram channel): a stock that has stayed under its high for a long time "
                    "(default 250 sessions, about a year) without falling more than half. A close above that high on volume at least 1.5x "
                    "the 50-day average, with the stop under the breakout or previous day's low within 8%, is the entry; the trade is held "
                    "until a Friday close below the weekly 40 EMA. Shaded lines are the base's top and floor; the third line is the weekly EMA.",
    "ph_bamm": "BAMM, Bat Action Magnetic Move (method from the Phoenix Harmonic Telegram channel): after a fall X to A, a bounce to B "
               "retracing 0.382-0.618 of XA and a pullback C, a close above B is pulled toward D at 0.886 of XA. C is support; a close below it ends the trade.",
    "ph_half_bat": "Half Bat (the Phoenix Harmonic channel's own pattern; ratios read off its charts): after a rally X to A of at least 10%, "
                   "the pullback to 0.5 of XA is a reversal zone. A close above the prior day's high enters; the target is A and a close below 0.886 of XA, "
                   "where it would turn into a full Bat, is the stop.",
}


# ---------------------------------------------------------------- registration

def register_strategies(add):
    wc = {"creator": WC, "channel": WC_URL, "sources": [WC_URL]}
    ph = {"creator": PH, "channel": PH_URL, "sources": [PH_URL]}
    add("wc_long_base", "Long base breakout", WC,
        "Buy the breakout day of a long base (price under its high for at least half of Base bars, never more than 50% below it) on volume ≥ Volume × the 50-day average, "
        "only if the stop (lower of today's and yesterday's low) is within Max risk %. Hold until a Friday close below the weekly EMA (Trail weeks) or a close below the stop.",
        [_num("base", "Base bars", 250, 120, 750, 10), _num("max_risk", "Max risk %", 8.0, 2.0, 20.0, 0.5),
         _num("vol_mult", "Volume ×", 1.5, 0.0, 5.0, 0.1), _num("trail", "Trail weeks", 40, 10, 60)],
        long_base_position, confidence="HIGH",
        notes="Entry, risk and weekly 40 EMA trail are as stated in the channel's case studies; the base test (half the window under the high, at most 50% deep) is TOP's. "
              "Partial exits after big moves are not modelled.", **wc)
    add("wc_ema21_pullback", "21 EMA pullback (stacked EMAs)", WC,
        "With EMA 21 > 50 > 200, buy a session that dips to EMA 21 and closes above it; exit on a close below the Exit EMA.",
        [_num("exit_ema", "Exit EMA", 50, 10, 100)], ema21_position, confidence="HIGH",
        notes="The post exits below EMA 21 and trails to EMA 50 after a break; on NSE data the EMA 50 exit tested better, so it is the default.", **wc)
    add("ph_bamm", "BAMM (close above B → D)", PH,
        "Bullish Bat Action Magnetic Move: X high, A low, B high retracing 0.382-0.618 of XA, C low holding 0.382-0.886 of AB. "
        "A close above B enters; exit at a close at D (0.886 of XA), a close below C, or after Max bars.",
        [_num("swing", "Swing %", 5.0, 2.0, 15.0, 0.5), _num("max_hold", "Max bars", 60, 10, 200)], bamm_position, confidence="MEDIUM",
        notes="Trigger, target and support are as stated in the channel's posts; the B and C ratio ranges are standard Bat ratios.", **ph)
    add("ph_half_bat", "Half Bat reversal", PH,
        "After a rally of at least Min leg %, buy the first close above the prior day's high once price has pulled back to 0.5 of the rally. "
        "Target the rally high; stop on a close below 0.886 of the rally; exit after Max bars.",
        [_num("swing", "Swing %", 5.0, 2.0, 15.0, 0.5), _num("min_leg", "Min leg %", 10.0, 3.0, 50.0, 1.0), _num("max_hold", "Max bars", 60, 10, 200)],
        half_bat_position, confidence="LOW",
        notes="Phoenix does not publish the Half Bat ratios; the 0.5 zone, 0.886 stop and target at A are read off its charts.", **ph)


def register_studies(add, price):
    wc = {"credit": "Method from the Wealthcreator Telegram channel (@wealthcreator7)", "sources": [WC_URL]}
    ph = {"credit": "Method from the Phoenix Harmonic Telegram channel (@PhoenixHarmonicOfficial)", "sources": [PH_URL]}
    add("wc_long_base", "Long base + weekly 40 EMA", WC, price,
        [_num("base", "Base bars", 250, 120, 750, 10), _num("max_risk", "Max risk %", 8.0, 2.0, 20.0, 0.5),
         _num("vol_mult", "Volume ×", 1.5, 0.0, 5.0, 0.1), _num("trail", "Trail weeks", 40, 10, 60)],
        ["base_top", "base_floor", "weekly_ema"], long_base_study,
        colors={"base_top": "#f23645", "base_floor": "#089981", "weekly_ema": "#2962ff"}, step=True, **wc)
    add("ph_bamm", "BAMM (Bat Action Magnetic Move)", PH, price,
        [_num("swing", "Swing %", 5.0, 2.0, 15.0, 0.5), _num("max_hold", "Max bars", 60, 10, 200)], ["pattern"], bamm_study, **ph)
    add("ph_half_bat", "Half Bat zone", PH, price,
        [_num("swing", "Swing %", 5.0, 2.0, 15.0, 0.5), _num("min_leg", "Min leg %", 10.0, 3.0, 50.0, 1.0), _num("max_hold", "Max bars", 60, 10, 200)],
        ["pattern"], half_bat_study, **ph)
