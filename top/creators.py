"""Strategies and studies adapted from two YouTube trading channels.

Each entry is registered under a section named after the creator's handle and
carries its sources and a confidence label:

- HIGH: rules taken from the creator's own published code.
- MEDIUM: rules from the original public source the creator tested (book or paper),
  where the exact variant used in the video is not public.

All rules are re-implemented here from the published algorithms, adapted to daily
NSE bars and long/flat positions (no shorting), with defaults re-scaled from the
creators' hourly crypto settings. They are research adaptations, not the creators'
own results. See docs/creators.md.
"""

from __future__ import annotations

import math

from top import market
from top.arrays import asarray as _arr
from top.indicators import atr as _atr_arr, ema as _ema_arr, rsi as _rsi_arr, sma as _sma_arr

NAN = float("nan")

NT = "@neurotrader888"
UT = "@UnbiasedTradingGoshawk"
NT_URL = "https://www.youtube.com/@neurotrader888"
UT_URL = "https://www.youtube.com/@UnbiasedTradingGoshawk"
NT_GH = "https://github.com/neurotrader888"


# ---------------------------------------------------------------- helpers

def _lst(values):
    return values.tolist() if hasattr(values, "tolist") else list(values)


def _ok(x):
    return x is not None and x == x and not math.isinf(x)


def _p(params, key, default):
    value = params.get(key, default)
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def _ohlcv(f):
    return _lst(f.o), _lst(f.h), _lst(f.l), _lst(f.c), _lst(f.v)


def _logs(xs):
    return [math.log(x) if _ok(x) and x > 0 else NAN for x in xs]


def _rolling_mean(xs, n):
    out, acc, count = [NAN] * len(xs), 0.0, 0
    window = []
    for i, x in enumerate(xs):
        window.append(x)
        if _ok(x):
            acc += x
            count += 1
        if len(window) > n:
            old = window.pop(0)
            if _ok(old):
                acc -= old
                count -= 1
        if len(window) == n and count == n:
            out[i] = acc / n
    return out


def _rolling_quantile(xs, n, q):
    out = [NAN] * len(xs)
    for i in range(n - 1, len(xs)):
        window = sorted(x for x in xs[i - n + 1 : i + 1] if _ok(x))
        if len(window) < n // 2:
            continue
        pos = q * (len(window) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(window) - 1)
        out[i] = window[lo] + (window[hi] - window[lo]) * (pos - lo)
    return out


def _cc_atr(log_close, n):
    """Close-to-close 'ATR' on log prices: rolling mean of |Δ log close|."""
    moves = [NAN] + [abs(b - a) if _ok(a) and _ok(b) else NAN for a, b in zip(log_close, log_close[1:])]
    return _rolling_mean(moves, n)


def _hold_positions(n, warmup, trades):
    """trades: list of (entry_bar, exit_bar) where the position is 1 from entry_bar to exit_bar - 1."""
    out = [NAN] * n
    for i in range(min(warmup, n), n):
        out[i] = 0.0
    for start, stop in trades:
        for i in range(max(start, 0), min(stop, n)):
            out[i] = 1.0
    return out


# ---------------------------------------------------------------- neurotrader888 building blocks

def directional_change(h, l, c, threshold, atr_values=None):
    """Directional-change zigzag (TechnicalAnalysisAutomation/directional_change.py).

    A top is confirmed when the close falls `threshold` (fraction) below the running high,
    or `threshold` ATRs below it when atr_values is given. Bottoms are symmetric.
    Returns (state per bar: 1 up-leg / -1 down-leg / 0 unknown, pivots as (confirm_i, extreme_i, price, kind)).
    """
    n = len(c)
    state, pivots = [0] * n, []
    if n == 0:
        return state, pivots
    up = True
    hi_v, hi_i, lo_v, lo_i = h[0], 0, l[0], 0
    for i in range(n):
        if not (_ok(h[i]) and _ok(l[i]) and _ok(c[i])):
            state[i] = state[i - 1] if i else 0
            continue
        band_hi = hi_v * threshold if atr_values is None else (atr_values[i] * threshold if _ok(atr_values[i]) else None)
        band_lo = lo_v * threshold if atr_values is None else band_hi
        if up:
            if h[i] > hi_v:
                hi_v, hi_i = h[i], i
            elif band_hi is not None and c[i] < hi_v - band_hi:
                pivots.append((i, hi_i, hi_v, 1))
                up = False
                lo_v, lo_i = l[i], i
        else:
            if l[i] < lo_v:
                lo_v, lo_i = l[i], i
            elif band_lo is not None and c[i] > lo_v + band_lo:
                pivots.append((i, lo_i, lo_v, -1))
                up = True
                hi_v, hi_i = h[i], i
        state[i] = (1 if up else -1) if pivots else 0
    return state, pivots


def rolling_extremes(h, l, order):
    """Swing highs/lows that are the extreme of `order` bars on each side (rolling_window.py).

    Returns a list of (confirm_i, extreme_i, price, kind) with kind 1 = high, -1 = low.
    Confirmation lags the extreme by `order` bars, so no look-ahead.
    """
    out = []
    for i in range(2 * order, len(h)):
        j = i - order
        window_h = h[j - order : i + 1]
        window_l = l[j - order : i + 1]
        if _ok(h[j]) and all(_ok(x) and x <= h[j] for x in window_h):
            out.append((i, j, h[j], 1))
        if _ok(l[j]) and all(_ok(x) and x >= l[j] for x in window_l):
            out.append((i, j, l[j], -1))
    return out


def fit_line(y, upper):
    """Support (upper=False) or resistance (upper=True) line over y (trendline_automation.py).

    Finds the pivot with the largest residual from the least-squares line, then the slope
    through that pivot that minimises squared distance to all points while never crossing
    any point. The creator solves this by coordinate descent; with one free slope the
    constrained optimum has a closed form, used here. Returns (slope, intercept at x=0).
    """
    n = len(y)
    xm = (n - 1) / 2
    ym = sum(y) / n
    sxx = sum((x - xm) ** 2 for x in range(n))
    slope = sum((x - xm) * (v - ym) for x, v in enumerate(y)) / sxx if sxx else 0.0
    base = ym - slope * xm
    resid = [v - (slope * x + base) for x, v in enumerate(y)]
    p = max(range(n), key=resid.__getitem__) if upper else min(range(n), key=resid.__getitem__)
    lo, hi = -math.inf, math.inf
    num = den = 0.0
    for j, v in enumerate(y):
        d = j - p
        if d == 0:
            continue
        r = (v - y[p]) / d
        if upper:
            if d > 0:
                lo = max(lo, r)
            else:
                hi = min(hi, r)
        else:
            if d > 0:
                hi = min(hi, r)
            else:
                lo = max(lo, r)
        num += d * (v - y[p])
        den += d * d
    best = num / den if den else slope
    best = min(max(best, lo), hi) if lo <= hi else slope
    return best, y[p] - best * p


def trendline_projection(series, lookback, upper):
    """Value at bar i of the line fitted over series[i-lookback:i], projected one bar ahead."""
    out = [NAN] * len(series)
    for i in range(lookback, len(series)):
        window = series[i - lookback : i]
        if not all(_ok(x) for x in window):
            continue
        slope, base = fit_line(window, upper)
        out[i] = base + slope * lookback
    return out


def hawkes_volatility(h, l, c, norm_lookback, kappa):
    """Hawkes-filtered normalised range (VolatilityHawkes/hawkes.py)."""
    lh, ll, lc = _logs(h), _logs(l), _logs(c)
    ranges = [hi - lo if _ok(hi) and _ok(lo) else NAN for hi, lo in zip(lh, ll)]
    log_atr = _lst(_atr_arr(_arr(lh, dtype=float), _arr(ll, dtype=float), _arr(lc, dtype=float), norm_lookback))
    norm = [r / a if _ok(r) and _ok(a) and a > 0 else NAN for r, a in zip(ranges, log_atr)]
    decay = math.exp(-kappa)
    out, prev = [NAN] * len(norm), 0.0
    started = False
    for i, x in enumerate(norm):
        if not _ok(x):
            continue
        prev = prev * decay + x
        started = True
        out[i] = prev * kappa if started else NAN
    return out


def cmma(log_close, lookback, atr_lookback):
    """Close minus moving average, scaled by ATR × sqrt(lookback) (IntramarketDifference)."""
    ma = _rolling_mean(log_close, lookback)
    vol = _cc_atr(log_close, atr_lookback)
    root = math.sqrt(lookback)
    return [(x - m) / (a * root) if _ok(x) and _ok(m) and _ok(a) and a > 0 else NAN for x, m, a in zip(log_close, ma, vol)]


def cmma_difference(f, lookback, atr_lookback):
    own = cmma(_logs(_lst(f.c)), lookback, atr_lookback)
    ref = cmma(_logs(market.aligned_close(list(f.ts))), lookback, atr_lookback)
    return [a - b if _ok(a) and _ok(b) else NAN for a, b in zip(own, ref)]


def vsa_deviation(h, l, v, n):
    """Range versus volume regression residual (VSAIndicator/vsa.py)."""
    c_like = [(a + b) / 2 if _ok(a) and _ok(b) else NAN for a, b in zip(h, l)]
    rng = [a - b if _ok(a) and _ok(b) else NAN for a, b in zip(h, l)]
    atr_v = _lst(_atr_arr(_arr(h, dtype=float), _arr(l, dtype=float), _arr(c_like, dtype=float), n))
    norm_r = [r / a if _ok(r) and _ok(a) and a > 0 else NAN for r, a in zip(rng, atr_v)]
    norm_v = [NAN] * len(v)
    for i in range(n - 1, len(v)):
        window = sorted(x for x in v[i - n + 1 : i + 1] if _ok(x))
        med = window[len(window) // 2] if window else 0
        norm_v[i] = v[i] / med if med else NAN
    out = [NAN] * len(v)
    for i in range(2 * n, len(v)):
        xs = norm_v[i - n + 1 : i + 1]
        ys = norm_r[i - n + 1 : i + 1]
        pairs = [(x, y) for x, y in zip(xs, ys) if _ok(x) and _ok(y)]
        if len(pairs) < n // 2:
            continue
        mx = sum(p[0] for p in pairs) / len(pairs)
        my = sum(p[1] for p in pairs) / len(pairs)
        sxx = sum((p[0] - mx) ** 2 for p in pairs)
        syy = sum((p[1] - my) ** 2 for p in pairs)
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
        if sxx == 0 or syy == 0:
            out[i] = 0.0
            continue
        slope = sxy / sxx
        r = sxy / math.sqrt(sxx * syy)
        if slope <= 0 or r < 0.2 or not (_ok(norm_v[i]) and _ok(norm_r[i])):
            out[i] = 0.0
            continue
        predicted = my + slope * (norm_v[i] - mx)
        out[i] = norm_r[i] - predicted
    return out


def permutation_entropy(c, lookback, d=3):
    """Normalised Bandt-Pompe permutation entropy of closes (PermutationEntropy/perm_entropy.py)."""
    patterns = [NAN] * len(c)
    for i in range(d - 1, len(c)):
        window = c[i - d + 1 : i + 1]
        if all(_ok(x) for x in window):
            patterns[i] = tuple(sorted(range(d), key=lambda k: (window[k], k)))
    out = [NAN] * len(c)
    norm = math.log(math.factorial(d))
    for i in range(lookback + d - 2, len(c)):
        counts = {}
        total = 0
        for pat in patterns[i - lookback + 1 : i + 1]:
            if pat == pat and isinstance(pat, tuple):
                counts[pat] = counts.get(pat, 0) + 1
                total += 1
        if total:
            out[i] = -sum((k / total) * math.log(k / total) for k in counts.values()) / norm
    return out


def _jacobi_eigen(a, sweeps=30):
    """Eigenvalues and eigenvectors (columns) of a small symmetric matrix."""
    n = len(a)
    a = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < 1e-18:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-14:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1 if theta >= 0 else -1) / (abs(theta) + math.sqrt(theta * theta + 1))
                cos = 1 / math.sqrt(t * t + 1)
                sin = t * cos
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = cos * akp - sin * akq
                    a[k][q] = sin * akp + cos * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = cos * apk - sin * aqk
                    a[q][k] = sin * apk + cos * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = cos * vkp - sin * vkq
                    v[k][q] = sin * vkp + cos * vkq
    values = [a[i][i] for i in range(n)]
    return values, v


def _solve(m, b):
    """Gaussian elimination for a small dense system; None if singular."""
    n = len(b)
    aug = [row[:] + [b[i]] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            return None
        aug[col], aug[piv] = aug[piv], aug[col]
        for r in range(n):
            if r != col:
                factor = aug[r][col] / aug[col][col]
                for k in range(col, n + 1):
                    aug[r][k] -= factor * aug[col][k]
    return [aug[i][n] / aug[i][i] for i in range(n)]


def rsi_pca_prediction(c, periods, components, horizon, train, refit):
    """Walk-forward RSI-PCA forecast of the next `horizon`-bar log return (RSI-PCA repo).

    The creator fits in-sample; here the model is refit every `refit` bars using only
    the previous `train` bars whose forward return is already known.
    Returns (prediction per bar, long threshold per bar).
    """
    n = len(c)
    rsis = [_lst(_rsi_arr(c, p)) for p in periods]
    rows = [[r[i] for r in rsis] for i in range(n)]
    logc = _logs(c)
    target = [logc[i + horizon] - logc[i] if i + horizon < n and _ok(logc[i]) and _ok(logc[i + horizon]) else NAN for i in range(n)]
    pred, thresh = [NAN] * n, [NAN] * n
    model = None
    for t in range(n):
        if t >= train + horizon and (model is None or (t - train) % refit == 0):
            idx = [s for s in range(t - train - horizon, t - horizon) if all(_ok(x) for x in rows[s]) and _ok(target[s])]
            if len(idx) >= max(60, train // 3):
                k = len(periods)
                mean = [sum(rows[s][j] for s in idx) / len(idx) for j in range(k)]
                cov = [[0.0] * k for _ in range(k)]
                for s in idx:
                    dev = [rows[s][j] - mean[j] for j in range(k)]
                    for a in range(k):
                        da = dev[a]
                        row = cov[a]
                        for b in range(a, k):
                            row[b] += da * dev[b]
                for a in range(k):
                    for b in range(a, k):
                        cov[a][b] /= len(idx) - 1
                        cov[b][a] = cov[a][b]
                values, vecs = _jacobi_eigen(cov)
                order = sorted(range(k), key=lambda j: values[j], reverse=True)[:components]

                def project(row, mean=mean, vecs=vecs, order=order):
                    dev = [row[j] - mean[j] for j in range(len(row))]
                    return [sum(dev[j] * vecs[j][o] for j in range(len(dev))) for o in order]

                feats = [[1.0] + project(rows[s]) for s in idx]
                ys = [target[s] for s in idx]
                m = len(feats[0])
                xtx = [[sum(f[a] * f[b] for f in feats) for b in range(m)] for a in range(m)]
                xty = [sum(f[a] * y for f, y in zip(feats, ys)) for a in range(m)]
                beta = _solve(xtx, xty)
                if beta:
                    fitted = sorted(sum(b * x for b, x in zip(beta, f)) for f in feats)
                    model = (beta, project, fitted)
        if model and all(_ok(x) for x in rows[t]):
            beta, project, fitted = model
            pred[t] = sum(b * x for b, x in zip(beta, [1.0] + project(rows[t])))
            thresh[t] = fitted
    return pred, thresh


def _quantile_sorted(values, q):
    if not values:
        return NAN
    pos = q * (len(values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


# ---------------------------------------------------------------- neurotrader888 strategies

def s_directional_change(f, p):
    o, h, l, c, v = _ohlcv(f)
    state, pivots = directional_change(h, l, c, _p(p, "sigma", 5.0) / 100)
    first = pivots[0][0] if pivots else len(c)
    return [NAN if i < first else (1.0 if state[i] == 1 else 0.0) for i in range(len(c))]


def s_atr_directional_change(f, p):
    o, h, l, c, v = _ohlcv(f)
    atr_v = _lst(_atr_arr(f.h, f.l, f.c, _p(p, "atr", 14)))
    state, pivots = directional_change(h, l, c, _p(p, "mult", 2.0), atr_v)
    first = pivots[0][0] if pivots else len(c)
    return [NAN if i < first else (1.0 if state[i] == 1 else 0.0) for i in range(len(c))]


def s_trendline_breakout(f, p):
    lookback = _p(p, "lookback", 30)
    logc = _logs(_lst(f.c))
    res = trendline_projection(logc, lookback, upper=True)
    sup = trendline_projection(logc, lookback, upper=False)
    out, pos = [NAN] * len(logc), 0.0
    for i in range(len(logc)):
        if not (_ok(res[i]) and _ok(sup[i])):
            continue
        if logc[i] > res[i]:
            pos = 1.0
        elif logc[i] < sup[i]:
            pos = 0.0
        out[i] = pos
    return out


def _inverse_head_shoulders(h, l, c, order):
    """Confirmed inverse head-and-shoulders patterns, as dicts (head_shoulders.py, mirrored)."""
    ext = sorted(rolling_extremes(h, l, order), key=lambda e: (e[1], e[3]))
    seq = []
    for confirm, idx, price, kind in ext:
        if seq and seq[-1][3] == kind:
            last = seq[-1]
            better = price < last[2] if kind == -1 else price > last[2]
            if better:
                seq[-1] = (confirm, idx, price, kind)
            continue
        seq.append((confirm, idx, price, kind))
    found = []
    for k in range(4, len(seq)):
        ls, la, hd, ra, rs = seq[k - 4 : k + 1]
        if [e[3] for e in (ls, la, hd, ra, rs)] != [-1, 1, -1, 1, -1]:
            continue
        if not (hd[2] < ls[2] and hd[2] < rs[2]):
            continue
        r_mid = 0.5 * (rs[2] + ra[2])
        l_mid = 0.5 * (ls[2] + la[2])
        if ls[2] > r_mid or rs[2] > l_mid:
            continue
        l_to_h, r_to_h = hd[1] - ls[1], rs[1] - hd[1]
        if l_to_h <= 0 or r_to_h <= 0 or r_to_h > 2.5 * l_to_h or l_to_h > 2.5 * r_to_h:
            continue
        slope = (ra[2] - la[2]) / (ra[1] - la[1]) if ra[1] != la[1] else 0.0
        found.append({"ready": max(rs[0], ra[0]), "head": hd[2], "rs_low": rs[2], "la": la, "slope": slope,
                      "width": max(ra[1] - la[1], 5), "span": rs[1] - ls[1]})
    return found


def s_inverse_head_shoulders(f, p):
    o, h, l, c, v = _ohlcv(f)
    order = _p(p, "order", 6)
    trades = []
    busy_until = -1
    for pat in _inverse_head_shoulders(h, l, c, order):
        start = pat["ready"]
        for i in range(start, min(len(c), start + pat["span"] + 1)):
            if c[i] < pat["head"]:
                break
            neck = pat["la"][2] + pat["slope"] * (i - pat["la"][1])
            if c[i] > neck:
                if i <= busy_until:
                    break
                stop_at = min(len(c), i + pat["width"])
                for j in range(i + 1, stop_at):
                    if c[j] < pat["rs_low"]:
                        stop_at = j
                        break
                trades.append((i, stop_at))
                busy_until = stop_at
                break
    return _hold_positions(len(c), 2 * order, trades)


def s_bull_flag(f, p):
    o, h, l, c, v = _ohlcv(f)
    order = _p(p, "order", 6)
    min_pole_atr = _p(p, "pole_atr", 3.0)
    atr_v = _lst(_atr_arr(f.h, f.l, f.c, 14))
    lows = [e for e in rolling_extremes(h, l, order) if e[3] == -1]
    trades, li, base, busy_until = [], 0, None, -1
    for i in range(len(c)):
        while li < len(lows) and lows[li][0] <= i:
            base = lows[li]
            li += 1
        if base is None or i <= busy_until or not _ok(atr_v[i]):
            continue
        b = base[1]
        if i - b < 7:
            continue
        t = max(range(b, i), key=lambda k: h[k])
        pole_w, flag_n = t - b, i - t
        if pole_w < 3 or flag_n < 3 or flag_n > 0.5 * pole_w:
            continue
        pole_h = h[t] - l[b]
        if pole_h < min_pole_atr * atr_v[i]:
            continue
        flag_low = min(l[t:i])
        if h[t] - flag_low > 0.5 * pole_h:
            continue
        slope, base_y = fit_line(h[t:i], upper=True)
        if c[i] > base_y + slope * flag_n:
            stop_at = min(len(c), i + pole_w)
            for j in range(i + 1, stop_at):
                if c[j] < flag_low:
                    stop_at = j
                    break
            trades.append((i, stop_at))
            busy_until = stop_at
            base = None
    return _hold_positions(len(c), 2 * order, trades)


def s_hawkes(f, p):
    o, h, l, c, v = _ohlcv(f)
    vol = hawkes_volatility(h, l, c, _p(p, "norm", 20), _p(p, "kappa", 0.1))
    lookback = _p(p, "lookback", 60)
    q05 = _rolling_quantile(vol, lookback, 0.05)
    q95 = _rolling_quantile(vol, lookback, 0.95)
    out, pos, last_below = [NAN] * len(c), 0.0, -1
    for i in range(1, len(c)):
        if not (_ok(vol[i]) and _ok(q05[i]) and _ok(q95[i])):
            continue
        if vol[i] < q05[i]:
            last_below = i
            pos = 0.0
        if _ok(vol[i - 1]) and _ok(q95[i - 1]) and vol[i] > q95[i] and vol[i - 1] <= q95[i - 1] and last_below > 0:
            pos = 1.0 if c[i] > c[last_below] else 0.0
        out[i] = pos
    return out


def s_cmma_index(f, p):
    diff = cmma_difference(f, _p(p, "lookback", 20), _p(p, "atr", 60))
    thr = _p(p, "threshold", 0.25)
    out, pos = [NAN] * len(diff), 0.0
    for i in range(1, len(diff)):
        if not (_ok(diff[i]) and _ok(diff[i - 1])):
            continue
        if pos == 0.0 and diff[i] > thr and diff[i - 1] <= thr:
            pos = 1.0
        elif pos == 1.0 and diff[i] < 0:
            pos = 0.0
        out[i] = pos
    return out


def s_donchian_runs(f, p):
    o, h, l, c, v = _ohlcv(f)
    n = _p(p, "lookback", 20)
    mode = _p(p, "mode", 1)
    out = [NAN] * len(c)
    in_base, taken, entry_px, last_ret = False, False, None, None
    for i in range(n, len(c)):
        upper = max(h[i - n : i])
        lower = min(l[i - n : i])
        if not in_base and c[i] > upper:
            in_base, entry_px = True, c[i]
            taken = mode == 0 or last_ret is None or (mode == 1 and last_ret <= 0) or (mode == 2 and last_ret > 0)
        elif in_base and c[i] < lower:
            in_base = False
            last_ret = c[i] / entry_px - 1
            taken = False
        out[i] = 1.0 if (in_base and taken) else 0.0
    return out


def s_rsi_pca(f, p):
    c = _lst(f.c)
    pred, fitted = rsi_pca_prediction(c, list(range(2, 25, 2)), _p(p, "components", 3), _p(p, "horizon", 6), _p(p, "train", 500), _p(p, "refit", 63))
    q = _p(p, "pct", 90) / 100
    out = [NAN] * len(c)
    for i, (y, fit) in enumerate(zip(pred, fitted)):
        if _ok(y) and isinstance(fit, list):
            out[i] = 1.0 if y > _quantile_sorted(fit, q) else 0.0
    return out


# ---------------------------------------------------------------- Unbiased Trading strategies

def s_connors_rsi2(f, p):
    c = _lst(f.c)
    r2 = _lst(_rsi_arr(f.c, 2))
    s200 = _lst(_sma_arr(f.c, _p(p, "trend", 200)))
    s5 = _lst(_sma_arr(f.c, _p(p, "exit", 5)))
    entry = _p(p, "rsi", 10.0)
    out, pos = [NAN] * len(c), 0.0
    for i in range(len(c)):
        if not (_ok(r2[i]) and _ok(s200[i]) and _ok(s5[i])):
            continue
        if pos == 0.0 and c[i] > s200[i] and r2[i] < entry:
            pos = 1.0
        elif pos == 1.0 and c[i] > s5[i]:
            pos = 0.0
        out[i] = pos
    return out


def s_double_seven(f, p):
    c = _lst(f.c)
    n = _p(p, "days", 7)
    s200 = _lst(_sma_arr(f.c, 200))
    out, pos = [NAN] * len(c), 0.0
    for i in range(n, len(c)):
        if not _ok(s200[i]):
            continue
        window = c[i - n + 1 : i + 1]
        if pos == 0.0 and c[i] > s200[i] and c[i] <= min(window):
            pos = 1.0
        elif pos == 1.0 and c[i] >= max(window):
            pos = 0.0
        out[i] = pos
    return out


def ewmac_forecast(c, speeds=((8, 32), (16, 64), (32, 128), (64, 256)), vol_n=25):
    """Average of volatility-scaled EMA crossovers, clipped to ±20 (trend-following signal)."""
    rets = [NAN] + [b - a if _ok(a) and _ok(b) else NAN for a, b in zip(c, c[1:])]
    sq = [r * r if _ok(r) else NAN for r in rets]
    var = _rolling_mean(sq, vol_n)
    vol = [math.sqrt(x) if _ok(x) else NAN for x in var]
    total = [0.0] * len(c)
    count = [0] * len(c)
    for fast, slow in speeds:
        ef, es = _lst(_ema_arr(c, fast)), _lst(_ema_arr(c, slow))
        for i in range(len(c)):
            if _ok(ef[i]) and _ok(es[i]) and _ok(vol[i]) and vol[i] > 0:
                total[i] += max(-20.0, min(20.0, (ef[i] - es[i]) / vol[i]))
                count[i] += 1
    return [total[i] / count[i] if count[i] == len(speeds) else NAN for i in range(len(c))]


def s_ahl_trend(f, p):
    fc = ewmac_forecast(_lst(f.c))
    thr = _p(p, "threshold", 0.0)
    return [NAN if not _ok(x) else (1.0 if x > thr else 0.0) for x in fc]


def relative_return(f):
    c = _lst(f.c)
    mkt = market.aligned_returns(list(f.ts))
    out = [NAN] * len(c)
    for i in range(1, len(c)):
        if _ok(c[i]) and _ok(c[i - 1]) and c[i - 1] and _ok(mkt[i]):
            out[i] = (c[i] / c[i - 1] - 1 - mkt[i]) * 100
    return out


def s_lo_contrarian(f, p):
    rel = relative_return(f)
    thr = -abs(_p(p, "threshold", 2.0))
    hold = max(1, _p(p, "hold", 1))
    out, until = [NAN] * len(rel), -1
    for i in range(len(rel)):
        if not _ok(rel[i]):
            continue
        if rel[i] < thr:
            until = i + hold - 1
        out[i] = 1.0 if i <= until else 0.0
    return out


# ---------------------------------------------------------------- registration

def _num(key, label, default, min_, max_, step=1):
    return {"key": key, "label": label, "type": "number", "default": default, "min": min_, "max": max_, "step": step}


def register_strategies(add):
    common = {"creator": NT, "channel": NT_URL, "license": "MIT (creator's code); re-implemented"}
    add("nt_dc_trend", "Directional-change trend", NT,
        "Ride the up-leg of a directional-change zigzag: long once price rises Sigma % off the last low, flat once it falls Sigma % from the high.",
        [_num("sigma", "Sigma %", 5.0, 1.0, 20.0, 0.5)], s_directional_change,
        sources=[f"{NT_GH}/TechnicalAnalysisAutomation/blob/main/directional_change.py"], confidence="HIGH", **common)
    add("nt_atr_dc_trend", "ATR directional-change trend", NT,
        "Same zigzag, but a swing is confirmed by a reversal of Mult × ATR instead of a fixed percent.",
        [_num("atr", "ATR", 14, 5, 60), _num("mult", "Mult", 2.0, 0.5, 6.0, 0.25)], s_atr_directional_change,
        sources=[f"{NT_GH}/market-structure/blob/main/atr_directional_change.py"], confidence="HIGH", **common)
    add("nt_trendline_breakout", "Trendline breakout", NT,
        "Fit support and resistance lines to the last Lookback closes (lines never cross price). Long on a close above projected resistance, flat on a close below projected support.",
        [_num("lookback", "Lookback", 30, 10, 120)], s_trendline_breakout,
        sources=[f"{NT_GH}/TrendLineAutomation", f"{NT_GH}/TrendlineBreakoutMetaLabel", "https://www.youtube.com/watch?v=jCBnbQ1PUkE"],
        confidence="HIGH", notes="The video's random-forest meta-label filter is not included.", **common)
    add("nt_inverse_hs", "Inverse head and shoulders", NT,
        "Five alternating swing points with a lower head, balanced shoulders, and symmetric timing. Long on a close through the neckline; exit after the head width or on a close below the right shoulder.",
        [_num("order", "Swing order", 6, 2, 20)], s_inverse_head_shoulders,
        sources=[f"{NT_GH}/TechnicalAnalysisAutomation/blob/main/head_shoulders.py"], confidence="HIGH", **common)
    add("nt_bull_flag", "Bull flag / pennant breakout", NT,
        "A pole of at least Pole ATR × ATR from a swing low, then a flag no wider than half the pole and no deeper than half its height. Long on a close above the flag's resistance line; exit after the pole width or below the flag low.",
        [_num("order", "Swing order", 6, 2, 20), _num("pole_atr", "Pole ATR", 3.0, 1.0, 10.0, 0.5)], s_bull_flag,
        sources=[f"{NT_GH}/TechnicalAnalysisAutomation/blob/main/flags_pennants.py"], confidence="HIGH", **common)
    add("nt_hawkes_vol", "Hawkes volatility breakout", NT,
        "Hawkes-filtered range. When volatility jumps above its 95th percentile after a quiet spell below the 5th, go long if price rose during the quiet spell; flat when volatility goes quiet again.",
        [_num("norm", "ATR length", 20, 5, 100), _num("kappa", "Kappa", 0.1, 0.01, 1.0, 0.01), _num("lookback", "Quantile window", 60, 20, 250)], s_hawkes,
        sources=[f"{NT_GH}/VolatilityHawkes", "https://www.youtube.com/watch?v=wdsiZBIhAFw"], confidence="HIGH", **common)
    add("nt_cmma_index", "Intramarket CMMA vs Nifty proxy", NT,
        "Each stock's close-minus-average (ATR scaled) minus the same for an equal-weight Nifty 50 proxy. Long when the gap crosses above Threshold, flat when it falls below zero.",
        [_num("lookback", "Lookback", 20, 5, 100), _num("atr", "ATR length", 60, 10, 250), _num("threshold", "Threshold", 0.25, 0.05, 1.0, 0.05)], s_cmma_index,
        sources=[f"{NT_GH}/IntramarketDifference"], confidence="HIGH", creator=NT, channel=NT_URL,
        license="Creator's repo has no license; only the published idea is used, re-implemented from scratch",
        notes="The creator compared ETH with BTC; here each stock is compared with an equal-weight Nifty 50 proxy built from the stored bars.")
    add("nt_donchian_runs", "Donchian breakout + last-trade filter", NT,
        "20-day Donchian breakout (long above the prior high, flat below the prior low). Mode 1 takes a breakout only if the previous breakout trade lost, mode 2 only if it won, mode 0 takes all.",
        [_num("lookback", "Lookback", 20, 5, 120), _num("mode", "Mode 0/1/2", 1, 0, 2)], s_donchian_runs,
        sources=[f"{NT_GH}/TradeDependenceRunsTest"], confidence="HIGH", **common)
    add("nt_rsi_pca", "RSI-PCA forecast", NT,
        "RSI at 12 lengths compressed with PCA, regressed on the next 6-day return. Refit walk-forward every 63 days on the prior 500; long when the forecast is in the top (100 − Pct)% of its training forecasts.",
        [_num("components", "Components", 3, 1, 6), _num("pct", "Pct", 90, 50, 99), _num("train", "Train bars", 500, 200, 900, 50), _num("refit", "Refit every", 63, 21, 252, 21), _num("horizon", "Horizon", 6, 1, 20)], s_rsi_pca,
        sources=[f"{NT_GH}/RSI-PCA", "https://www.youtube.com/watch?v=mdncZ034Q7k"], confidence="HIGH",
        notes="The creator fitted in-sample on RSI 2–24; this version is walk-forward on even lengths 2–24 to avoid look-ahead.", **common)

    ucommon = {"creator": UT, "channel": UT_URL}
    add("ut_connors_rsi2", "Connors RSI(2) pullback", UT,
        "Larry Connors' published rule: above the 200-day SMA, buy when RSI(2) < 10; sell on a close above the 5-day SMA.",
        [_num("rsi", "RSI(2) below", 10.0, 1.0, 30.0, 1.0), _num("trend", "Trend SMA", 200, 50, 250), _num("exit", "Exit SMA", 5, 2, 20)], s_connors_rsi2,
        sources=["https://www.youtube.com/watch?v=4TTb0f9fk1U"], confidence="MEDIUM",
        notes="The video tests a Connors strategy; the exact variant is not public, so this uses Connors' published RSI(2) rules.", **ucommon)
    add("ut_double_seven", "Connors Double 7s", UT,
        "Connors' Double 7s: above the 200-day SMA, buy at a 7-day closing low; sell at a 7-day closing high.",
        [_num("days", "Days", 7, 3, 20)], s_double_seven,
        sources=["https://www.youtube.com/watch?v=4TTb0f9fk1U"], confidence="MEDIUM",
        notes="A second published Connors system, included because the video's variant is not public.", **ucommon)
    add("ut_ahl_trend", "AHL-style trend following (EWMAC)", UT,
        "Average of four volatility-scaled EMA crossovers (8/32, 16/64, 32/128, 64/256). Long when the combined forecast is above Threshold.",
        [_num("threshold", "Threshold", 0.0, -5.0, 10.0, 0.5)], s_ahl_trend,
        sources=["https://www.youtube.com/watch?v=54PMBYXA3e0", "https://www.youtube.com/watch?v=MHCRqXL_mkA"], confidence="MEDIUM",
        notes="The videos reproduce a Man AHL trend signal without public parameters; this is the standard multi-speed EWMAC trend signal.", **ucommon)
    add("ut_lo_contrarian", "Lo–Khandani contrarian", UT,
        "From the MIT paper the video tests: buy stocks that lagged the market. Long for Hold days after the stock's daily return trails the equal-weight Nifty proxy by more than Threshold %.",
        [_num("threshold", "Threshold %", 2.0, 0.5, 10.0, 0.5), _num("hold", "Hold days", 1, 1, 10)], s_lo_contrarian,
        sources=["https://www.youtube.com/watch?v=elPKLu9cj_I", "https://web.mit.edu/Alo/www/Papers/august07.pdf"], confidence="MEDIUM",
        notes="The paper's portfolio is long-short across all stocks with close-to-close returns; this is a long-only, single-stock version filled at the next open.", **ucommon)


def _zigzag_line(h, l, c, sigma):
    state, pivots = directional_change(h, l, c, sigma)
    points = sorted({(p[1], p[2]) for p in pivots})
    if points and points[-1][0] < len(c) - 1 and _ok(c[-1]):
        points.append((len(c) - 1, c[-1]))
    out = [NAN] * len(c)
    for (i0, y0), (i1, y1) in zip(points, points[1:]):
        for i in range(i0, i1 + 1):
            out[i] = y0 + (y1 - y0) * (i - i0) / (i1 - i0) if i1 != i0 else y0
    return out


def register_studies(add, price, osc):
    from top.arrays import asarray

    def arr(xs):
        return asarray(xs, dtype=float)

    add("nt_zigzag", "Directional-change zigzag", NT, price, [_num("sigma", "Sigma %", 5.0, 1.0, 20.0, 0.5)], ["zigzag"],
        lambda f, p: {"zigzag": arr(_zigzag_line(_lst(f.h), _lst(f.l), _lst(f.c), _p(p, "sigma", 5.0) / 100))})
    add("nt_trendlines", "Auto trendlines", NT, price, [_num("lookback", "Lookback", 30, 10, 120)], ["upper", "lower"],
        lambda f, p: {
            "upper": arr([math.exp(x) if _ok(x) else NAN for x in trendline_projection(_logs(_lst(f.c)), _p(p, "lookback", 30), True)]),
            "lower": arr([math.exp(x) if _ok(x) else NAN for x in trendline_projection(_logs(_lst(f.c)), _p(p, "lookback", 30), False)]),
        })

    def hawkes_study(f, p):
        vol = hawkes_volatility(_lst(f.h), _lst(f.l), _lst(f.c), _p(p, "norm", 20), _p(p, "kappa", 0.1))
        n = _p(p, "lookback", 60)
        return {"hawkes": arr(vol), "q05": arr(_rolling_quantile(vol, n, 0.05)), "q95": arr(_rolling_quantile(vol, n, 0.95))}

    add("nt_hawkes", "Hawkes volatility", NT, osc,
        [_num("norm", "ATR length", 20, 5, 100), _num("kappa", "Kappa", 0.1, 0.01, 1.0, 0.01), _num("lookback", "Quantile window", 60, 20, 250)],
        ["hawkes", "q05", "q95"], hawkes_study)
    add("nt_vsa", "VSA range-vs-volume", NT, osc, [_num("length", "Length", 60, 20, 250)], ["vsa"],
        lambda f, p: {"vsa": arr(vsa_deviation(_lst(f.h), _lst(f.l), _lst(f.v), _p(p, "length", 60)))})
    add("nt_cmma", "CMMA vs Nifty proxy", NT, osc, [_num("lookback", "Lookback", 20, 5, 100), _num("atr", "ATR length", 60, 10, 250)], ["diff"],
        lambda f, p: {"diff": arr(cmma_difference(f, _p(p, "lookback", 20), _p(p, "atr", 60)))})
    add("nt_perm_entropy", "Permutation entropy", NT, osc, [_num("length", "Length", 30, 10, 250)], ["entropy"],
        lambda f, p: {"entropy": arr(permutation_entropy(_lst(f.c), _p(p, "length", 30)))})
    add("ut_ewmac", "EWMAC trend forecast", UT, osc, [], ["forecast"], lambda f, p: {"forecast": arr(ewmac_forecast(_lst(f.c)))})
    add("ut_rel_return", "Return vs Nifty proxy", UT, osc, [], ["rel"], lambda f, p: {"rel": arr(relative_return(f))})
