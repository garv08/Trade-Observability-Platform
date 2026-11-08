"""Scott Carney harmonic ratios on a percent zigzag.

These are research approximations of the published ratio rules, with a tolerance.
They are not the Harmonic Trader product and they do not place orders.

Every signal here is causal. A zigzag pivot is only known once price has moved the
swing % away from it, so pattern strategies act on that confirmation bar, never on D.
The PRZ engine follows Carney's published process: structure (X-A-B-C), ratio (the D
level and the HOP failure level along XA), then a confirmation bar inside the zone.
"""

from __future__ import annotations

from top import arrays as np

PATTERN_SPECS = [
    {"id": "gartley", "name": "Gartley"},
    {"id": "bat", "name": "Bat"},
    {"id": "alt_bat", "name": "Alternate Bat"},
    {"id": "butterfly", "name": "Butterfly"},
    {"id": "crab", "name": "Crab"},
    {"id": "deep_crab", "name": "Deep Crab"},
    {"id": "cypher", "name": "Cypher"},
    {"id": "shark", "name": "Shark"},
    {"id": "five_o", "name": "5-0"},
    {"id": "abcd", "name": "AB=CD"},
    {"id": "three_drives", "name": "Three Drives"},
]


def _near(value, target, tol):
    return value is not None and abs(value - target) <= tol


def _span(value, low, high, tol):
    return value is not None and (low - tol) <= value <= (high + tol)


def zigzag(high, low, pct):
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(high)
    if n < 5:
        return []
    threshold = max(float(pct), 0.5) / 100.0
    pivots = []
    direction = 1
    ext_i = 0
    ext = float(high[0])
    for i in range(1, n):
        hi = float(high[i])
        lo = float(low[i])
        if hi != hi or lo != lo:
            continue
        if direction == 1:
            if hi >= ext:
                ext, ext_i = hi, i
            elif lo <= ext * (1 - threshold) and i != ext_i:
                pivots.append((ext_i, ext, 1))
                direction = -1
                ext, ext_i = lo, i
        elif lo <= ext:
            ext, ext_i = lo, i
        elif hi >= ext * (1 + threshold) and i != ext_i:
            pivots.append((ext_i, ext, -1))
            direction = 1
            ext, ext_i = hi, i
    if not pivots or pivots[-1][0] != ext_i:
        pivots.append((ext_i, ext, direction if direction == 1 else -1))
    return pivots


def _xabcd(points, bullish):
    if bullish:
        signed = points
    else:
        signed = [(i, -px, -kind) for i, px, kind in points]
    (ix, x, kx), (ia, a, ka), (ib, b, kb), (ic, c, kc), (id_, d, kd) = signed
    if [kx, ka, kb, kc, kd] != [-1, 1, -1, 1, -1]:
        return None
    if not (ia > ix and ib > ia and ic > ib and id_ > ic and a > x and b < a and c > b and d < c):
        return None
    xa = a - x
    ab_leg = a - b
    bc_leg = c - b
    if xa <= 0 or ab_leg <= 0 or bc_leg <= 0:
        return None
    return {
        "index": points[-1][0],
        "prz": points[-1][1],
        "ab": ab_leg / xa,
        "bc": bc_leg / ab_leg,
        "cd": (c - d) / bc_leg,
        "ad": (a - d) / xa,
        "xc": (c - x) / xa,
        "xd": (c - d) / (c - x) if c != x else None,
        "ab_len": ab_leg,
        "cd_len": c - d,
    }


def _match_xabcd(geo, tol):
    found = []
    ab, bc, cd, ad = geo["ab"], geo["bc"], geo["cd"], geo["ad"]
    if _near(ab, 0.618, tol) and _span(bc, 0.382, 0.886, tol) and _span(cd, 1.272, 1.618, tol) and _near(ad, 0.786, tol):
        found.append("gartley")
    if _span(ab, 0.382, 0.50, tol) and _span(bc, 0.382, 0.886, tol) and _span(cd, 1.618, 2.618, tol) and _near(ad, 0.886, tol):
        found.append("bat")
    if _near(ab, 0.382, tol) and _span(bc, 0.382, 0.886, tol) and _span(cd, 2.0, 3.618, tol) and _near(ad, 1.13, tol):
        found.append("alt_bat")
    if _near(ab, 0.786, tol) and _span(bc, 0.382, 0.886, tol) and _span(cd, 1.618, 2.618, tol) and _near(ad, 1.272, tol):
        found.append("butterfly")
    if _span(ab, 0.382, 0.618, tol) and _span(bc, 0.382, 0.886, tol) and _span(cd, 2.24, 3.618, tol) and _near(ad, 1.618, tol):
        found.append("crab")
    if _near(ab, 0.886, tol) and _span(bc, 0.382, 0.886, tol) and _span(cd, 2.0, 3.618, tol) and _near(ad, 1.618, tol):
        found.append("deep_crab")
    if _span(ab, 0.382, 0.618, tol) and _span(geo["xc"], 1.272, 1.414, tol) and _near(geo["xd"], 0.786, tol):
        found.append("cypher")
    if _span(ab, 1.13, 1.618, tol) and _span(bc, 1.618, 2.24, tol) and _near(cd, 0.50, tol):
        found.append("five_o")
    if geo["ab_len"] and _near(geo["cd_len"] / geo["ab_len"], 1.0, tol) and _span(bc, 0.382, 0.886, tol):
        found.append("abcd")
    return found


def _shark(points, bullish, tol):
    geo = _xabcd(points, bullish)
    if not geo:
        return False
    # Completion at the last pivot. AB extends XA, BC extends AB, and C sits in the 0.886-1.13 zone of XA.
    return _span(geo["ab"], 1.13, 1.618, tol) and _span(geo["bc"], 1.618, 2.24, tol) and _span(geo["ad"], 0.886, 1.13, tol)


def _three_drives(points, bullish, tol):
    if bullish:
        signed = points
    else:
        signed = [(i, -px, -kind) for i, px, kind in points]
    if [kind for _, _, kind in signed] != [1, -1, 1, -1, 1, -1]:
        return False
    _, h0, _ = signed[0]
    _, l1, _ = signed[1]
    _, h1, _ = signed[2]
    _, l2, _ = signed[3]
    _, h2, _ = signed[4]
    _, l3, _ = signed[5]
    if not (l2 < l1 and l3 < l2 and h0 > l1 and h1 > l2 and h2 > l3):
        return False
    r1 = (h1 - l1) / (h0 - l1) if h0 != l1 else None
    r2 = (h2 - l2) / (h1 - l2) if h1 != l2 else None
    e2 = (l1 - l2) / (h0 - l1) if h0 != l1 else None
    e3 = (l2 - l3) / (h1 - l2) if h1 != l2 else None
    return _span(r1, 0.618, 0.786, tol) and _span(r2, 0.618, 0.786, tol) and _span(e2, 1.272, 1.618, tol) and _span(e3, 1.272, 1.618, tol)


def _confirm_index(high, low, index, price, bottom, swing_pct):
    """First bar after a pivot where the zigzag could know it: price moved swing % away."""
    threshold = max(float(swing_pct), 0.5) / 100.0
    for j in range(index + 1, len(high)):
        if bottom and float(high[j]) >= price * (1 + threshold):
            return j
        if not bottom and float(low[j]) <= price * (1 - threshold):
            return j
    return None


def detect(high, low, ts, swing_pct=3.0, tolerance=0.05, only=None):
    pivots = zigzag(high, low, swing_pct)
    names = {row["id"]: row["name"] for row in PATTERN_SPECS}
    events = []
    for end in range(4, len(pivots)):
        window = pivots[end - 4 : end + 1]
        for bullish, side in ((True, "bull"), (False, "bear")):
            geo = _xabcd(window, bullish)
            found = _match_xabcd(geo, tolerance) if geo else []
            if _shark(window, bullish, tolerance):
                found.append("shark")
            if only:
                found = [item for item in found if item == only]
            if not found or geo is None:
                continue
            index = window[-1][0]
            confirmed = _confirm_index(high, low, index, float(window[-1][1]), bullish, swing_pct)
            events.append(
                {
                    "index": index,
                    "time": ts[index],
                    "confirmed": confirmed,
                    "confirmed_time": ts[confirmed] if confirmed is not None else None,
                    "side": side,
                    "names": [names[item] for item in found],
                    "ids": found,
                    "prz": round(float(window[-1][1]), 2),
                    "points": [(i, float(px)) for i, px, _ in window],
                    "labels": ["X", "A", "B", "C", "D"],
                    "ratios": {key: round(geo[key], 3) for key in ("ab", "bc", "cd", "ad") if geo.get(key) is not None},
                }
            )
    if only in (None, "three_drives"):
        for end in range(5, len(pivots)):
            window = pivots[end - 5 : end + 1]
            for bullish, side in ((True, "bull"), (False, "bear")):
                if not _three_drives(window, bullish, tolerance):
                    continue
                index = window[-1][0]
                confirmed = _confirm_index(high, low, index, float(window[-1][1]), bullish, swing_pct)
                events.append(
                    {
                        "index": index,
                        "time": ts[index],
                        "confirmed": confirmed,
                        "confirmed_time": ts[confirmed] if confirmed is not None else None,
                        "side": side,
                        "names": ["Three Drives"],
                        "ids": ["three_drives"],
                        "prz": round(float(window[-1][1]), 2),
                        "points": [(i, float(px)) for i, px, _ in window],
                        "labels": ["0", "1", "A", "2", "B", "3"],
                        "ratios": {},
                    }
                )
    return events


DEFAULT_SWING = 3.0
DEFAULT_TOLERANCE = 0.05
MAX_DRAWN = 12


def study(frame, params, only=None):
    swing = float(params.get("swing", DEFAULT_SWING))
    tol = float(params.get("tolerance", DEFAULT_TOLERANCE))
    events = detect(frame.h, frame.l, frame.ts, swing, tol, only)
    events.sort(key=lambda event: event["index"])
    markers = []
    drawings = []
    for event in events:
        bull = event["side"] == "bull"
        text = ", ".join(event["names"])
        markers.append(
            {
                "time": event["time"],
                "position": "belowBar" if bull else "aboveBar",
                "color": "#089981" if bull else "#f23645",
                "shape": "arrowUp" if bull else "arrowDown",
                "text": f"{'Bull' if bull else 'Bear'} {text}",
            }
        )
    for event in events[-MAX_DRAWN:]:
        bull = event["side"] == "bull"
        pts = [{"time": frame.ts[i], "value": round(px, 2), "label": label} for (i, px), label in zip(event["points"], event["labels"])]
        if len(pts) == 5:
            guides = [[pts[0], pts[2], pts[4]], [pts[1], pts[3]]]
        else:
            guides = [[pts[1], pts[3], pts[5]]]
        hop = None
        spec = next((PRZ_SPECS[i] for i in event["ids"] if i in PRZ_SPECS), None)
        if spec and len(event["points"]) == 5:
            x, a = event["points"][0][1], event["points"][1][1]
            hop = round(a - spec["hop"] * (a - x), 2)
        d_px = event["prz"]
        a_px = target_anchor(event)
        drawings.append(
            {
                "name": ", ".join(event["names"]),
                "side": event["side"],
                "color": "#089981" if bull else "#f23645",
                "time": event["time"],
                "confirmed": event["confirmed_time"],
                "prz": event["prz"],
                "hop": hop,
                "t1": round(d_px + 0.382 * (a_px - d_px), 2),
                "t2": round(d_px + 0.618 * (a_px - d_px), 2),
                "ratios": event["ratios"],
                "legs": pts,
                "guides": guides,
            }
        )
    return {}, markers, drawings


def target_anchor(event):
    """Reaction targets are measured from D toward A (Carney); when A is not on the reward side (5-0, Shark), from C."""
    points = event["points"]
    d_px = event["prz"]
    a_px = points[1][1] if len(points) == 5 else points[-2][1]
    bull = event["side"] == "bull"
    if (bull and a_px <= d_px) or (not bull and a_px >= d_px):
        a_px = points[-2][1]
    return a_px


PRZ_NAMES = {"bat": "Bat", "deep_crab": "Deep Crab", "crab": "Crab", "gartley": "Gartley", "butterfly": "Butterfly", "alt_bat": "Alternate Bat"}


def prz_study(frame, params):
    """Past PRZ trades as markers, and live bullish setups drawn as X-A-B-C with their D and HOP levels."""
    markers, drawings = [], []
    for trade in prz_trades(frame, params):
        name = PRZ_NAMES[trade["pattern"]]
        markers.append({"time": frame.ts[trade["entry"]], "position": "belowBar", "color": "#089981", "shape": "arrowUp", "text": f"PRZ {name}"})
        if trade["reason"] != "open":
            markers.append({"time": frame.ts[trade["exit"]], "position": "aboveBar", "color": "#787b86", "shape": "circle",
                            "text": {"target": "target", "hop": "HOP stop", "time": "time stop"}[trade["reason"]]})
    last = len(frame) - 1
    for row in prz_watch(frame, params)[-4:]:
        legs = [{"time": frame.ts[i], "value": round(px, 2), "label": label} for (i, px), label in zip(row["points"], "XABC")]
        start = frame.ts[row["points"][0][0]]
        end = frame.ts[last]
        drawings.append(
            {
                "name": f"{PRZ_NAMES[row['pattern']]} PRZ ({row['state']})",
                "side": "bull",
                "color": "#2962ff",
                "time": start,
                "confirmed": None,
                "prz": round(row["d"], 2),
                "hop": round(row["hop"], 2),
                "t1": None,
                "t2": None,
                "ratios": {"ab": round((row["a"] - row["b"]) / (row["a"] - row["x"]), 3), "bc": round((row["c"] - row["b"]) / (row["a"] - row["b"]), 3)},
                "legs": legs,
                "guides": [[{"time": start, "value": round(row["d"], 2), "label": "D"}, {"time": end, "value": round(row["d"], 2), "label": "D"}],
                           [{"time": start, "value": round(row["hop"], 2), "label": "HOP"}, {"time": end, "value": round(row["hop"], 2), "label": "HOP"}]],
            }
        )
    markers.sort(key=lambda m: m["time"])
    return {}, markers, drawings


def _cached(frame, key, build):
    """Per-frame memo, so the 12 pattern strategies share one zigzag and match pass."""
    cache = frame.__dict__.setdefault("_harmonic_cache", {})
    if key not in cache:
        cache[key] = build()
    return cache[key]


def position(frame, params, only=None):
    """Long for `hold` bars from the bar that confirms a bullish D pivot (no look-ahead)."""
    swing = float(params.get("swing", DEFAULT_SWING))
    tol = float(params.get("tolerance", DEFAULT_TOLERANCE))
    hold = int(params.get("hold", 10))
    every = _cached(frame, ("detect", swing, tol), lambda: detect(frame.h, frame.l, frame.ts, swing, tol))
    events = [event for event in every if only is None or only in event["ids"]]
    out = np.full(len(frame), np.nan)
    if len(frame) > 30:
        out[30:] = 0.0
    for event in events:
        if event["side"] != "bull" or event["confirmed"] is None:
            continue
        start = event["confirmed"]
        stop = min(len(frame), start + max(hold, 1))
        for i in range(start, stop):
            out[i] = 1.0
    return out


# ---------------------------------------------------------------- Carney PRZ engine

# Per pattern, in multiples of XA unless named: B retracement range, D level, HOP (harmonic
# optimal price, the failure level), BC projection range to D, and an optional CD/AB range.
PRZ_SPECS = {
    "bat": {"b": (0.382, 0.55), "d": 0.886, "hop": 1.13, "bc_proj": (1.618, 3.618)},
    "deep_crab": {"b": (0.886, 0.886), "d": 1.618, "hop": 2.0, "bc_proj": (2.0, 3.618)},
    "crab": {"b": (0.382, 0.618), "d": 1.618, "hop": 2.0, "bc_proj": (2.24, 3.618)},
    "gartley": {"b": (0.618, 0.618), "d": 0.786, "hop": 1.0, "bc_proj": (1.13, 1.618), "abcd": (1.0, 1.27)},
    "butterfly": {"b": (0.786, 0.786), "d": 1.272, "hop": 1.414, "bc_proj": (1.618, 2.618)},
    "alt_bat": {"b": (0.30, 0.382), "d": 1.13, "hop": 1.272, "bc_proj": (2.0, 3.618)},
}
PRZ_ORDER = ["bat", "deep_crab", "crab", "gartley", "butterfly", "alt_bat"]  # Carney's stated preference
PRZ_C = (0.382, 0.886)
PRZ_WAIT = 60
PRZ_WINDOW = 30


def _rsi(close, length=14):
    out = [None] * len(close)
    gain = loss = 0.0
    for i in range(1, len(close)):
        change = close[i] - close[i - 1]
        up, down = max(change, 0.0), max(-change, 0.0)
        if i <= length:
            gain += up / length
            loss += down / length
            if i < length:
                continue
        else:
            gain = (gain * (length - 1) + up) / length
            loss = (loss * (length - 1) + down) / length
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def prz_setups(high, low, swing_pct=3.0, tolerance=0.05, only=None):
    """Bullish X-A-B-C structures whose C is confirmed, with the PRZ (D to HOP) they project.

    `known` is the bar where C is confirmed, the first bar the setup could be traded from."""
    pivots = zigzag(high, low, swing_pct)
    found = []
    for k in range(3, len(pivots)):
        (ix, x, kx), (ia, a, ka), (ib, b, kb), (ic, c, kc) = pivots[k - 3 : k + 1]
        if [kx, ka, kb, kc] != [-1, 1, -1, 1]:
            continue
        xa, ab, bc = a - x, a - b, c - b
        if xa <= 0 or ab <= 0 or bc <= 0 or not _span(bc / ab, PRZ_C[0], PRZ_C[1], tolerance):
            continue
        known = _confirm_index(high, low, ic, c, False, swing_pct)
        if known is None:
            continue
        for pattern in PRZ_ORDER:
            if only and pattern != only:
                continue
            spec = PRZ_SPECS[pattern]
            if not _span(ab / xa, spec["b"][0], spec["b"][1], tolerance):
                continue
            d = a - spec["d"] * xa
            if d <= 0 or not _span((c - d) / bc, spec["bc_proj"][0], spec["bc_proj"][1], tolerance):
                continue
            if "abcd" in spec and not _span((c - d) / ab, spec["abcd"][0], spec["abcd"][1], tolerance):
                continue
            found.append({"pattern": pattern, "known": known, "points": [(ix, x), (ia, a), (ib, b), (ic, c)],
                          "x": x, "a": a, "b": b, "c": c, "d": d, "hop": max(a - spec["hop"] * xa, 0.0)})
            break
    return found


def _confirmed_bar(o, h, c, j, d, mode):
    if mode <= 0:
        return True
    if mode == 1:
        return c[j] > o[j] and c[j] > d
    three = j >= 3 and c[j] > max(h[j - 3 : j])
    two = j >= 1 and c[j] > o[j] and c[j - 1] > o[j - 1] and c[j] > c[j - 1]
    return three or two


def prz_trades(frame, params, only=None):
    """Causal Carney PRZ trades: touch D before C is exceeded, confirm inside the zone, exit at target/HOP/time."""
    swing = float(params.get("swing", DEFAULT_SWING))
    tol = float(params.get("tolerance", DEFAULT_TOLERANCE))
    mode = int(params.get("confirm", 2))
    target = float(params.get("target", 0.618))
    max_hold = max(int(params.get("max_hold", PRZ_WINDOW)), 1)
    use_rsi = bool(int(params.get("rsi", 0)))
    o = [float(v) for v in frame.o]
    h = [float(v) for v in frame.h]
    l = [float(v) for v in frame.l]
    c = [float(v) for v in frame.c]
    n = len(c)
    rsi = _rsi(c) if use_rsi else None
    candidates = []
    for setup in prz_setups(h, l, swing, tol, only):
        a, top, d, hop = setup["a"], setup["c"], setup["d"], setup["hop"]
        touch = None
        for i in range(setup["known"], min(n, setup["known"] + PRZ_WAIT)):
            if h[i] > top:
                break
            if l[i] <= d:
                touch = i
                break
        if touch is None:
            continue
        low, entry = l[touch], None
        for j in range(touch, min(n, touch + PRZ_WINDOW)):
            low = min(low, l[j])
            if c[j] < hop:
                break
            ok = _confirmed_bar(o, h, c, j, d, mode)
            if ok and use_rsi:
                seen = [v for v in rsi[touch : j + 1] if v is not None]
                ok = bool(seen) and min(seen) < 35 and j >= 1 and rsi[j] is not None and rsi[j - 1] is not None and rsi[j] > rsi[j - 1]
            if ok:
                entry = j
                break
        if entry is None:
            continue
        goal = low + target * (a - low)
        exit_ = entry + max_hold
        reason = "time"
        if exit_ >= n:
            exit_, reason = n, "open"  # still held at the last bar
        for j in range(entry + 1, min(n, entry + max_hold + 1)):
            if c[j] >= goal:
                exit_, reason = j, "target"
                break
            if c[j] < hop:
                exit_, reason = j, "hop"
                break
        candidates.append(dict(setup, touch=touch, entry=entry, exit=exit_, reason=reason, low=low,
                               t1=low + 0.382 * (a - low), t2=low + 0.618 * (a - low)))
    # Take trades in the order they would have been entered, one at a time, so a later setup never blocks an earlier one.
    trades, busy = [], -1
    for trade in sorted(candidates, key=lambda row: (row["entry"], row["known"])):
        if trade["touch"] <= busy:
            continue
        trades.append(trade)
        busy = trade["exit"]
    return trades


def prz_position(frame, params, only=None):
    out = np.full(len(frame), np.nan)
    if len(frame) > 30:
        out[30:] = 0.0
    for trade in prz_trades(frame, params, only):
        for i in range(trade["entry"], trade["exit"]):
            out[i] = 1.0
    return out


def prz_watch(frame, params, only=None):
    """Bullish setups whose PRZ is still ahead or being tested at the last bar."""
    swing = float(params.get("swing", DEFAULT_SWING))
    tol = float(params.get("tolerance", DEFAULT_TOLERANCE))
    h = [float(v) for v in frame.h]
    l = [float(v) for v in frame.l]
    c = [float(v) for v in frame.c]
    n = len(c)
    live = []
    for setup in prz_setups(h, l, swing, tol, only):
        state, touch = "waiting", None
        for i in range(setup["known"], n):
            if touch is None and i - setup["known"] >= PRZ_WAIT:
                state = "expired"
                break
            if touch is None and h[i] > setup["c"]:
                state = "cancelled"
                break
            if touch is None and l[i] <= setup["d"]:
                touch, state = i, "in zone"
            if touch is not None and c[i] < setup["hop"]:
                state = "failed"
                break
            if touch is not None and i - touch >= PRZ_WINDOW:
                state = "expired"
                break
        if state in ("waiting", "in zone"):
            live.append(dict(setup, state=state, touch=touch))
    return live
