"""Scott Carney harmonic ratios on a percent zigzag.

These are research approximations of the published ratio rules, with a tolerance.
They are not the Harmonic Trader product and they do not place orders.
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
            events.append(
                {
                    "index": index,
                    "time": ts[index],
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
                events.append(
                    {
                        "index": index,
                        "time": ts[index],
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
        drawings.append(
            {
                "name": ", ".join(event["names"]),
                "side": event["side"],
                "color": "#089981" if bull else "#f23645",
                "time": event["time"],
                "prz": event["prz"],
                "ratios": event["ratios"],
                "legs": pts,
                "guides": guides,
            }
        )
    return {}, markers, drawings


def position(frame, params, only=None):
    swing = float(params.get("swing", DEFAULT_SWING))
    tol = float(params.get("tolerance", DEFAULT_TOLERANCE))
    hold = int(params.get("hold", 10))
    events = detect(frame.h, frame.l, frame.ts, swing, tol, only)
    out = np.full(len(frame), np.nan)
    if len(frame) > 30:
        out[30:] = 0.0
    for event in events:
        if event["side"] != "bull":
            continue
        start = event["index"]
        stop = min(len(frame), start + max(hold, 1))
        out[start:stop] = 1.0
    return out
