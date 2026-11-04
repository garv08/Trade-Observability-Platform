"""Robustness checks for a single-stock backtest: Monte Carlo trade shuffling and walk-forward.

Both answer "how much of this result is luck or tuning?" — ideas the X research digest
(docs/research/x-digest.md) found repeated across the quant accounts.
"""

from __future__ import annotations

import math
import random

from top.backtest import run


def _pct(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def monte_carlo(trades, runs=1000, seed=7):
    """Reshuffle the order of closed-trade returns and compound them.

    Same trades, different order: the spread of max drawdown shows how much of the
    backtest's drawdown was the luck of the sequence. Drawdown here is measured trade to
    trade (between trades), so it understates drawdowns inside a trade.
    """
    returns = [t["return_pct"] / 100 for t in trades if not t.get("open")]
    if len(returns) < 5:
        return {"runs": 0, "trades": len(returns), "note": "At least 5 closed trades are needed."}
    rng = random.Random(seed)
    dds, finals = [], []
    for _ in range(int(runs)):
        order = returns[:]
        rng.shuffle(order)
        equity, peak, worst = 1.0, 1.0, 0.0
        for r in order:
            equity *= 1 + r
            peak = max(peak, equity)
            worst = min(worst, equity / peak - 1)
        dds.append(worst * 100)
        finals.append((equity - 1) * 100)
    actual_equity, peak, actual_dd = 1.0, 1.0, 0.0
    for r in returns:
        actual_equity *= 1 + r
        peak = max(peak, actual_equity)
        actual_dd = min(actual_dd, actual_equity / peak - 1)
    return {
        "runs": int(runs),
        "trades": len(returns),
        "max_dd_pct": {"p5": round(_pct(dds, 0.05), 2), "p50": round(_pct(dds, 0.5), 2), "p95": round(_pct(dds, 0.95), 2)},
        "actual_trade_dd_pct": round(actual_dd * 100, 2),
        "total_return_pct": round((actual_equity - 1) * 100, 2),
        "worse_dd_share_pct": round(100 * sum(1 for d in dds if d < actual_dd * 100) / len(dds), 1),
        "note": "Shuffling only reorders trades, so the total return is the same in every run; the drawdown range shows sequence risk. p5 is the bad case.",
    }


def primary_param(spec):
    """The strategy's first numeric setting, or None."""
    for param in spec.get("params") or []:
        if param.get("type", "number") == "number":
            return param
    return None


def grid(param, current):
    """Five values around the current setting: ×0.5, ×0.75, ×1, ×1.25, ×1.5, clipped and de-duplicated."""
    lo, hi = param.get("min"), param.get("max")
    step = param.get("step") or 1
    integer = float(step).is_integer() and float(current).is_integer()
    values = []
    for k in (0.5, 0.75, 1.0, 1.25, 1.5):
        v = float(current) * k
        if lo is not None:
            v = max(float(lo), v)
        if hi is not None:
            v = min(float(hi), v)
        v = int(round(v)) if integer else round(v, 6)
        if v not in values:
            values.append(v)
    return values


def _score(points, capital):
    """CAGR ÷ |max DD| (5% floor) over a list of (time, value) points."""
    if len(points) < 20:
        return None
    first, last = points[0][1], points[-1][1]
    if first <= 0 or last <= 0:
        return None
    years = len(points) / 252
    cagr = (last / first) ** (1 / years) - 1
    peak, dd = -math.inf, 0.0
    for _, v in points:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    return cagr * 100 / max(abs(dd) * 100, 5.0)


def _stats(values):
    if len(values) < 2:
        return {"cagr_pct": None, "max_dd_pct": None, "total_return_pct": None}
    years = len(values) / 252
    total = values[-1] / values[0] - 1
    cagr = (values[-1] / values[0]) ** (1 / years) - 1 if values[-1] > 0 else -1
    peak, dd = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    return {"cagr_pct": round(cagr * 100, 2), "max_dd_pct": round(dd * 100, 2), "total_return_pct": round(total * 100, 2)}


def walk_forward(frame, spec, signal_fn, params, capital=1_000_000.0, cost_bps=5.0, train_years=2):
    """Re-pick the strategy's main setting each calendar year from earlier data only.

    For every value in a five-point grid around the current setting, the strategy is run once
    over the whole history (signals are causal, so this is safe). For each test year after the
    first `train_years`, the value with the best CAGR ÷ |max DD| on all data before that year is
    chosen, and that value's daily returns during the test year are stitched together.
    Switching costs between values are ignored. Result: out-of-sample (OOS) equity vs the fixed
    current setting over the same test years.
    """
    param = primary_param(spec)
    if param is None:
        return {"ok": False, "note": "This strategy has no numeric setting to tune, so walk-forward does not apply."}
    key = param["key"]
    current = params.get(key, param.get("default"))
    values = grid(param, current)
    curves = {}
    for value in values:
        position = signal_fn(spec["id"], frame, {**params, key: value})
        result = run(frame.ts, frame.o, frame.h, frame.l, frame.c, position, capital=capital, cost_bps=cost_bps)
        curves[value] = {p["time"]: p["value"] for p in result["equity"]}
    times = [t for t in frame.ts if all(t in c for c in curves.values())]
    years = sorted({t[:4] for t in times})
    tests = years[train_years:]
    # The last year is often partial; keep it if it has a quarter of a year of bars.
    tests = [y for y in tests if sum(1 for t in times if t.startswith(y)) >= 60]
    if not tests:
        return {"ok": False, "note": f"Walk-forward needs more than {train_years} years of history."}
    oos, fixed, picks = [1.0], [1.0], []
    oos_dates = []
    for year in tests:
        train_points = {v: [(t, curves[v][t]) for t in times if t < year] for v in values}
        scores = {v: _score(pts, capital) for v, pts in train_points.items()}
        ranked = sorted((s, v) for v, s in scores.items() if s is not None)
        chosen = ranked[-1][1] if ranked else current
        year_times = [t for t in times if t.startswith(year)]
        prev_time = max((t for t in times if t < year), default=None)
        seq = ([prev_time] if prev_time else []) + year_times
        year_oos = _stats([curves[chosen][t] for t in seq])
        year_fixed = _stats([curves[current][t] for t in seq] if current in curves else [])
        picks.append({"year": year, "value": chosen, "train_score": None if not ranked else round(ranked[-1][0], 3),
                      "oos_return_pct": year_oos["total_return_pct"], "fixed_return_pct": year_fixed["total_return_pct"]})
        for a, b in zip(seq, seq[1:]):
            oos.append(oos[-1] * curves[chosen][b] / curves[chosen][a])
            if current in curves:
                fixed.append(fixed[-1] * curves[current][b] / curves[current][a])
            oos_dates.append(b)
    changes = sum(1 for a, b in zip(picks, picks[1:]) if a["value"] != b["value"])
    stable = changes <= max(1, len(picks) // 3)
    return {
        "ok": True,
        "param": {"key": key, "label": param.get("label", key), "current": current, "grid": values},
        "years": picks,
        "oos": _stats(oos),
        "fixed": _stats(fixed),
        "changes": changes,
        "verdict": "stable" if stable else "unstable",
        "equity": [{"time": t, "value": round(v * capital, 2)} for t, v in zip(oos_dates, oos[1:])],
        "note": ("The best setting barely changed from year to year, which suggests the rule is not over-tuned."
                 if stable else "The best setting changed often between years: results depend on tuning, so treat the full-period backtest with caution."),
        "test_from": tests[0],
    }
