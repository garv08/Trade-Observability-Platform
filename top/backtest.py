"""Next-open long/flat backtest with explicit costs."""

from __future__ import annotations

import math

from top import arrays as np


def run(ts, open_, high, low, close, position, capital=1_000_000.0, cost_bps=5.0):
    ts = list(ts)
    open_ = np.asarray(open_, dtype=float)
    close = np.asarray(close, dtype=float)
    position = np.asarray(position, dtype=float)
    n = len(close)
    if n < 3:
        raise ValueError("not enough bars")

    valid = np.where(~np.isnan(position))[0]
    start = int(valid[0]) if len(valid) else 0
    cost = float(cost_bps) / 10_000.0
    capital = float(capital)

    cash = capital
    shares = 0.0
    entry_i = None
    entry_px = None
    entry_cost = 0.0
    trades = []
    equity = np.full(n, np.nan)
    equity[start] = capital

    for i in range(start + 1, n):
        desired = 1 if position[i - 1] == 1 else 0
        px = open_[i]
        if not np.isfinite(px) or px <= 0:
            equity[i] = cash + shares * close[i - 1]
            continue
        current = 1 if shares > 0 else 0
        if current != desired:
            if shares > 0:
                proceeds = shares * px * (1 - cost)
                cash += proceeds
                trades.append(_trade(ts, entry_i, i, entry_px, px, shares, entry_cost, proceeds, False))
                shares = 0.0
                entry_i = None
            if desired == 1 and cash > 0:
                fee = cash * cost
                shares = (cash - fee) / px
                entry_cost = cash
                entry_px = px
                entry_i = i
                cash = 0.0
        mark = close[i] if np.isfinite(close[i]) else px
        equity[i] = cash + shares * mark

    if shares > 0 and entry_i is not None:
        mark = close[-1]
        proceeds = shares * mark
        trades.append(_trade(ts, entry_i, n - 1, entry_px, mark, shares, entry_cost, proceeds, True))

    curve = equity[start:]
    curve = _fill(curve, capital)
    bench = capital * close[start:] / close[start]
    metrics = _metrics(curve, bench, trades, capital)
    return {
        "start": ts[start],
        "end": ts[-1],
        "equity": [{"time": ts[i], "value": round(float(equity[i]), 2)} for i in range(start, n) if np.isfinite(equity[i])],
        "benchmark": [{"time": ts[i], "value": round(float(bench[i - start]), 2)} for i in range(start, n)],
        "trades": trades,
        "metrics": metrics,
        "methodology": "Signal at the close. Fill at the next session open. Long or flat, fully invested. Cost is charged on entry and on a closed exit. Buy-and-hold uses the same start bar and no costs.",
    }


def _trade(ts, entry_i, exit_i, entry_px, exit_px, shares, entry_cost, proceeds, open_trade):
    pnl = proceeds - entry_cost
    ret = (proceeds / entry_cost - 1) * 100 if entry_cost else 0
    return {
        "entry": ts[entry_i],
        "exit": ts[exit_i],
        "entry_px": round(float(entry_px), 2),
        "exit_px": round(float(exit_px), 2),
        "shares": round(float(shares), 4),
        "pnl": round(float(pnl), 2),
        "return_pct": round(float(ret), 2),
        "bars": int(exit_i - entry_i),
        "open": open_trade,
    }


def _fill(curve, capital):
    out = curve.copy()
    if not np.isfinite(out[0]):
        out[0] = capital
    for i in range(1, len(out)):
        if not np.isfinite(out[i]):
            out[i] = out[i - 1]
    return out


def _metrics(equity, benchmark, trades, capital):
    rets = np.diff(equity) / equity[:-1]
    rets = rets[np.isfinite(rets)]
    total = equity[-1] / capital - 1
    years = max(len(equity) / 252, 1 / 252)
    cagr = (equity[-1] / capital) ** (1 / years) - 1 if equity[-1] > 0 else -1
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1
    max_dd = float(dd.min()) if len(dd) else 0
    sharpe = _ratio(rets, downside=False)
    sortino = _ratio(rets, downside=True)
    closed = [t for t in trades if not t["open"]]
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    bh = benchmark[-1] / capital - 1
    exposed = sum(1 for t in trades for _ in range(t["bars"]))
    return {
        "total_return_pct": _pct(total),
        "cagr_pct": _pct(cagr),
        "max_drawdown_pct": _pct(max_dd),
        "sharpe": None if sharpe is None else round(sharpe, 2),
        "sortino": None if sortino is None else round(sortino, 2),
        "win_rate_pct": None if not closed else round(100 * len(wins) / len(closed), 1),
        "profit_factor": None if gross_loss == 0 else round(gross_win / gross_loss, 2),
        "trades": len(trades),
        "closed_trades": len(closed),
        "avg_trade_pct": None if not closed else round(sum(t["return_pct"] for t in closed) / len(closed), 2),
        "exposure_pct": round(100 * min(exposed, len(equity)) / len(equity), 1),
        "buy_hold_pct": _pct(bh),
        "ending_equity": round(float(equity[-1]), 2),
    }


def _ratio(rets, downside):
    if len(rets) < 2:
        return None
    mean = float(np.mean(rets))
    if downside:
        loss = rets[rets < 0]
        if len(loss) == 0:
            return None
        dev = float(np.std(loss, ddof=1))
    else:
        dev = float(np.std(rets, ddof=1))
    if dev == 0 or math.isnan(dev):
        return None
    return mean / dev * math.sqrt(252)


def _pct(value):
    return round(float(value) * 100, 2)


def _finite(value):
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def metrics(open_, close, position, capital=1_000_000.0, cost_bps=5.0):
    """The same rules and metrics as run(), on plain lists, without equity/benchmark/trade output.

    About 10x faster than run(); used by the leaderboard, which needs only the numbers.
    """
    open_ = [float(x) if x is not None else math.nan for x in open_]
    close = [float(x) if x is not None else math.nan for x in close]
    position = [float(x) if x is not None else math.nan for x in position]
    n = len(close)
    if n < 3:
        raise ValueError("not enough bars")
    start = next((i for i, p in enumerate(position) if p == p), 0)
    cost = float(cost_bps) / 10_000.0
    capital = float(capital)
    cash, shares, entry_i, entry_cost = capital, 0.0, None, 0.0
    closed_pnl, closed_ret, bars_held, open_trades = [], [], 0, 0
    equity = [capital]
    for i in range(start + 1, n):
        desired = 1 if position[i - 1] == 1 else 0
        px = open_[i]
        if not math.isfinite(px) or px <= 0:
            equity.append(cash + shares * close[i - 1])
            continue
        if (1 if shares > 0 else 0) != desired:
            if shares > 0:
                proceeds = shares * px * (1 - cost)
                cash += proceeds
                closed_pnl.append(round(proceeds - entry_cost, 2))
                closed_ret.append(round((proceeds / entry_cost - 1) * 100 if entry_cost else 0, 2))
                bars_held += i - entry_i
                shares, entry_i = 0.0, None
            if desired == 1 and cash > 0:
                shares = (cash - cash * cost) / px
                entry_cost, entry_i, cash = cash, i, 0.0
        mark = close[i] if math.isfinite(close[i]) else px
        equity.append(cash + shares * mark)
    if shares > 0 and entry_i is not None:
        open_trades = 1
        bars_held += n - 1 - entry_i
    for i in range(1, len(equity)):
        if not math.isfinite(equity[i]):
            equity[i] = equity[i - 1]
    rets = []
    for a, b in zip(equity, equity[1:]):
        r = (b - a) / a if a else math.nan
        if math.isfinite(r):
            rets.append(r)
    last = equity[-1]
    years = max(len(equity) / 252, 1 / 252)
    cagr = (last / capital) ** (1 / years) - 1 if last > 0 else -1
    peak, max_dd = -math.inf, 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = min(max_dd, value / peak - 1)
    wins = [p for p in closed_pnl if p > 0]
    gross_win, gross_loss = sum(wins), abs(sum(p for p in closed_pnl if p <= 0))
    bh = close[-1] / close[start] - 1
    sharpe = _list_ratio(rets, False)
    sortino = _list_ratio(rets, True)
    trades = len(closed_pnl) + open_trades
    return {
        "total_return_pct": _pct(last / capital - 1),
        "cagr_pct": _pct(cagr),
        "max_drawdown_pct": _pct(max_dd),
        "sharpe": None if sharpe is None else round(sharpe, 2),
        "sortino": None if sortino is None else round(sortino, 2),
        "win_rate_pct": None if not closed_pnl else round(100 * len(wins) / len(closed_pnl), 1),
        "profit_factor": None if gross_loss == 0 else round(gross_win / gross_loss, 2),
        "trades": trades,
        "closed_trades": len(closed_pnl),
        "avg_trade_pct": None if not closed_pnl else round(sum(closed_ret) / len(closed_ret), 2),
        "exposure_pct": round(100 * min(bars_held, len(equity)) / len(equity), 1),
        "buy_hold_pct": _pct(bh),
        "ending_equity": round(float(last), 2),
    }


def _list_ratio(rets, downside):
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    sample = [r for r in rets if r < 0] if downside else rets
    if downside and not sample:
        return None
    if len(sample) < 2:
        return None
    m = sum(sample) / len(sample)
    dev = math.sqrt(sum((r - m) ** 2 for r in sample) / (len(sample) - 1))
    if dev == 0 or math.isnan(dev):
        return None
    return mean / dev * math.sqrt(252)
