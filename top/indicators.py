"""Chart studies. Each catalog entry is a named indicator with a section and pane."""

from __future__ import annotations

from collections import deque

from top import arrays as np

SECTIONS = [
    "Harmonics",
    "@neurotrader888",
    "@UnbiasedTradingGoshawk",
    "Moving averages",
    "Bands and channels",
    "Trend",
    "Momentum",
    "Volatility",
    "Volume",
    "Price statistics",
]


class Frame:
    def __init__(self, ts, open_, high, low, close, volume):
        self.ts = list(ts)
        self.o = np.asarray(open_, dtype=float)
        self.h = np.asarray(high, dtype=float)
        self.l = np.asarray(low, dtype=float)
        self.c = np.asarray(close, dtype=float)
        self.v = np.asarray(volume, dtype=float)

    def __len__(self):
        return len(self.c)


def _nan(n):
    return np.full(n, np.nan)


def shift(x, n=1):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    if n == 0:
        return x.copy()
    if n > 0 and n < len(x):
        out[n:] = x[:-n]
    elif n < 0 and -n < len(x):
        out[:n] = x[-n:]
    return out


def rolling_sum(x, n):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    n = int(n)
    if n <= 0 or len(x) < n:
        return out
    clean = np.nan_to_num(x, nan=0.0)
    csum = np.cumsum(clean)
    out[n - 1] = csum[n - 1]
    if n < len(x):
        out[n:] = csum[n:] - csum[:-n]
    return out


def rolling_mean(x, n):
    total = rolling_sum(x, n)
    valid = ~np.isnan(total)
    total[valid] = total[valid] / int(n)
    return total


def rolling_std(x, n):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    n = int(n)
    if n < 2 or len(x) < n:
        return out
    for i in range(n - 1, len(x)):
        window = x[i - n + 1 : i + 1]
        if np.isnan(window).any():
            continue
        out[i] = float(np.std(window, ddof=0))
    return out


def _rolling_extreme(x, n, pick):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    n = int(n)
    if n <= 0:
        return out
    dq = deque()
    for i, value in enumerate(x):
        while dq and dq[0] <= i - n:
            dq.popleft()
        while dq and pick(x[dq[-1]], value):
            dq.pop()
        dq.append(i)
        if i >= n - 1 and not np.isnan(x[dq[0]]):
            out[i] = x[dq[0]]
    return out


def rolling_max(x, n):
    return _rolling_extreme(x, n, lambda old, new: old <= new)


def rolling_min(x, n):
    return _rolling_extreme(x, n, lambda old, new: old >= new)


def _first_window(x, n):
    """Index where the first run of values with any finite number starts, if n values remain."""
    for i in range(len(x)):
        if not np.isnan(x[i]):
            return i if len(x) - i >= n else None
    return None


def ema(x, n):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    n = int(n)
    if n <= 0 or len(x) < n:
        return out
    alpha = 2 / (n + 1)
    start = _first_window(x, n)
    if start is None:
        return out
    prev = float(np.nanmean(x[start : start + n]))
    out[start + n - 1] = prev
    for i in range(start + n, len(x)):
        value = x[i]
        if np.isnan(value) or np.isnan(prev):
            continue
        prev = alpha * value + (1 - alpha) * prev
        out[i] = prev
    return out


def rma(x, n):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    n = int(n)
    if n <= 0 or len(x) < n:
        return out
    start = _first_window(x, n)
    if start is None:
        return out
    prev = float(np.nanmean(x[start : start + n]))
    out[start + n - 1] = prev
    alpha = 1 / n
    for i in range(start + n, len(x)):
        if np.isnan(x[i]):
            continue
        prev = prev + alpha * (x[i] - prev)
        out[i] = prev
    return out


def wma(x, n):
    x = np.asarray(x, dtype=float)
    out = _nan(len(x))
    n = int(n)
    if n <= 0 or len(x) < n:
        return out
    weights = np.arange(1, n + 1, dtype=float)
    denom = weights.sum()
    for i in range(n - 1, len(x)):
        window = x[i - n + 1 : i + 1]
        if np.isnan(window).any():
            continue
        out[i] = float(np.dot(window, weights) / denom)
    return out


def sma(x, n):
    return rolling_mean(x, n)


def dema(x, n):
    first = ema(x, n)
    return 2 * first - ema(first, n)


def tema(x, n):
    first = ema(x, n)
    second = ema(first, n)
    third = ema(second, n)
    return 3 * first - 3 * second + third


def hma(x, n):
    n = max(int(n), 2)
    half = max(int(n / 2), 1)
    root = max(int(np.sqrt(n)), 1)
    raw = 2 * wma(x, half) - wma(x, n)
    return wma(raw, root)


def rma_from(x, n):
    return rma(np.nan_to_num(x, nan=0.0), n)


def true_range(h, l, c):
    prev = shift(c)
    ranges = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    ranges[0] = h[0] - l[0]
    return ranges


def atr(h, l, c, n):
    return rma(true_range(h, l, c), n)


def rsi(c, n):
    delta = np.diff(c, prepend=c[0])
    delta[0] = 0
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = rma(gain, n)
    avg_loss = rma(loss, n)
    rs = avg_gain / np.where(avg_loss == 0, np.nan, avg_loss)
    out = 100 - (100 / (1 + rs))
    out[: int(n)] = np.nan
    return out


def stdev(x, n):
    return rolling_std(x, n)


def typical(h, l, c):
    return (h + l + c) / 3


def median_price(h, l):
    return (h + l) / 2


def weighted_close(h, l, c):
    return (h + l + 2 * c) / 4


def roc(c, n):
    prev = shift(c, n)
    return (c / prev - 1) * 100


def mom(c, n):
    return c - shift(c, n)


def macd(c, fast, slow, signal):
    line = ema(c, fast) - ema(c, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bbands(c, n, k):
    mid = sma(c, n)
    dev = stdev(c, n)
    return mid + k * dev, mid, mid - k * dev


def donchian(h, l, n):
    upper = rolling_max(h, n)
    lower = rolling_min(l, n)
    return upper, (upper + lower) / 2, lower


def stoch(h, l, c, n, smooth):
    lowest = rolling_min(l, n)
    highest = rolling_max(h, n)
    span = highest - lowest
    raw = 100 * (c - lowest) / np.where(span == 0, np.nan, span)
    k = sma(raw, smooth)
    d = sma(k, smooth)
    return k, d


def psar(h, l, step=0.02, maximum=0.2):
    n = len(h)
    out = _nan(n)
    if n < 2:
        return out
    bull = True
    af = step
    ep = h[0]
    out[0] = l[0]
    for i in range(1, n):
        prev = out[i - 1]
        value = prev + af * (ep - prev)
        if bull:
            value = min(value, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < value:
                bull = False
                value = ep
                ep = l[i]
                af = step
            elif h[i] > ep:
                ep = h[i]
                af = min(af + step, maximum)
        else:
            value = max(value, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > value:
                bull = True
                value = ep
                ep = h[i]
                af = step
            elif l[i] < ep:
                ep = l[i]
                af = min(af + step, maximum)
        out[i] = value
    return out


def supertrend(h, l, c, n, mult):
    basis = atr(h, l, c, n)
    hl2 = (h + l) / 2
    upper_basic = hl2 + mult * basis
    lower_basic = hl2 - mult * basis
    upper = upper_basic.copy()
    lower = lower_basic.copy()
    trend = np.ones(len(c))
    line = _nan(len(c))
    for i in range(1, len(c)):
        if np.isnan(upper_basic[i]) or np.isnan(lower_basic[i]):
            continue
        if np.isnan(upper[i - 1]) or np.isnan(lower[i - 1]):
            upper[i] = upper_basic[i]
            lower[i] = lower_basic[i]
            trend[i] = trend[i - 1]
            line[i] = lower[i] if trend[i] == 1 else upper[i]
            continue
        upper[i] = upper_basic[i] if (upper_basic[i] < upper[i - 1] or c[i - 1] > upper[i - 1]) else upper[i - 1]
        lower[i] = lower_basic[i] if (lower_basic[i] > lower[i - 1] or c[i - 1] < lower[i - 1]) else lower[i - 1]
        if c[i] > upper[i - 1]:
            trend[i] = 1
        elif c[i] < lower[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
        line[i] = lower[i] if trend[i] == 1 else upper[i]
    line[: int(n)] = np.nan
    return line, trend


def adx_pack(h, l, c, n):
    up = h - shift(h)
    down = shift(l) - l
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm[0] = 0
    minus_dm[0] = 0
    atr_ = atr(h, l, c, n)
    plus_di = 100 * rma(plus_dm, n) / np.where(atr_ == 0, np.nan, atr_)
    minus_di = 100 * rma(minus_dm, n) / np.where(atr_ == 0, np.nan, atr_)
    denom = plus_di + minus_di
    dx = 100 * np.abs(plus_di - minus_di) / np.where(denom == 0, np.nan, denom)
    adx_ = rma(np.nan_to_num(dx, nan=0.0), n)
    adx_[: n * 2] = np.nan
    return adx_, plus_di, minus_di


def obv(c, v):
    direction = np.sign(c - shift(c))
    direction[0] = 0
    return np.cumsum(np.nan_to_num(direction, nan=0.0) * v)


def vwap(h, l, c, v):
    tp = typical(h, l, c)
    cumulative_v = np.cumsum(v)
    cumulative_tp = np.cumsum(tp * v)
    return cumulative_tp / np.where(cumulative_v == 0, np.nan, cumulative_v)


def kama(c, n=10, fast=2, slow=30):
    out = _nan(len(c))
    n = int(n)
    if len(c) <= n:
        return out
    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    change = np.abs(c - shift(c, n))
    volatility = rolling_sum(np.abs(c - shift(c)), n)
    er = change / np.where(volatility == 0, np.nan, volatility)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    out[n] = c[n]
    prev = c[n]
    for i in range(n + 1, len(c)):
        if np.isnan(sc[i]):
            continue
        prev = prev + sc[i] * (c[i] - prev)
        out[i] = prev
    return out


def zlema(c, n):
    lag = max(int((n - 1) / 2), 0)
    return ema(c + (c - shift(c, lag)), n)


def alma(c, n=20, offset=0.85, sigma=6):
    out = _nan(len(c))
    n = int(n)
    if len(c) < n:
        return out
    m = offset * (n - 1)
    s = n / sigma
    weights = np.exp(-((np.arange(n) - m) ** 2) / (2 * s * s))
    weights /= weights.sum()
    for i in range(n - 1, len(c)):
        window = c[i - n + 1 : i + 1]
        if np.isnan(window).any():
            continue
        out[i] = float(np.dot(window, weights))
    return out


def mcginley(c, n):
    out = _nan(len(c))
    n = int(n)
    if len(c) < n:
        return out
    prev = float(np.mean(c[:n]))
    out[n - 1] = prev
    for i in range(n, len(c)):
        if prev == 0:
            break
        prev = prev + (c[i] - prev) / (n * ((c[i] / prev) ** 4))
        out[i] = prev
    return out


def t3(c, n, vfactor=0.7):
    e1 = ema(c, n)
    e2 = ema(e1, n)
    e3 = ema(e2, n)
    e4 = ema(e3, n)
    e5 = ema(e4, n)
    e6 = ema(e5, n)
    vf = vfactor
    c1 = -(vf ** 3)
    c2 = 3 * vf ** 2 + 3 * vf ** 3
    c3 = -6 * vf ** 2 - 3 * vf - 3 * vf ** 3
    c4 = 1 + 3 * vf + vf ** 3 + 3 * vf ** 2
    return c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3


def vidya(c, n, smooth=9):
    changes = c - shift(c)
    up = rolling_sum(np.maximum(changes, 0), smooth)
    down = rolling_sum(np.maximum(-changes, 0), smooth)
    cmo = (up - down) / np.where((up + down) == 0, np.nan, up + down)
    alpha = 2 / (n + 1)
    out = _nan(len(c))
    start = max(n, smooth)
    if len(c) <= start:
        return out
    prev = c[start]
    out[start] = prev
    for i in range(start + 1, len(c)):
        if np.isnan(cmo[i]):
            continue
        k = alpha * abs(cmo[i])
        prev = prev + k * (c[i] - prev)
        out[i] = prev
    return out


def linreg(c, n):
    out = _nan(len(c))
    slope = _nan(len(c))
    n = int(n)
    if len(c) < n:
        return out, slope
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    var = np.sum((x - x_mean) ** 2)
    for i in range(n - 1, len(c)):
        y = c[i - n + 1 : i + 1]
        if np.isnan(y).any():
            continue
        beta = np.sum((x - x_mean) * (y - y.mean())) / var
        intercept = y.mean() - beta * x_mean
        slope[i] = beta
        out[i] = intercept + beta * (n - 1)
    return out, slope


def tsf(c, n):
    value, slope = linreg(c, n)
    return value + slope


def supersmoother(c, n):
    # Ehlers 2-pole super smoother. Period n.
    out = _nan(len(c))
    n = max(int(n), 1)
    if len(c) < 3:
        return out
    a1 = np.exp(-np.sqrt(2) * np.pi / n)
    b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / n)
    c2 = b1
    c3 = -(a1 ** 2)
    c1 = 1 - c2 - c3
    out[0] = c[0]
    out[1] = c[1]
    for i in range(2, len(c)):
        out[i] = c1 * (c[i] + c[i - 1]) / 2 + c2 * out[i - 1] + c3 * out[i - 2]
    out[: n] = np.nan
    return out


def frama(c, n=16):
    out = _nan(len(c))
    n = max(int(n), 4)
    if n % 2:
        n += 1
    half = n // 2
    if len(c) <= n:
        return out
    prev = c[n]
    out[n] = prev
    for i in range(n, len(c)):
        w = c[i - n + 1 : i + 1]
        n1 = (np.max(w[:half]) - np.min(w[:half])) / half
        n2 = (np.max(w[half:]) - np.min(w[half:])) / half
        n3 = (np.max(w) - np.min(w)) / n
        if n1 > 0 and n2 > 0 and n3 > 0:
            dim = (np.log(n1 + n2) - np.log(n3)) / np.log(2)
        else:
            dim = 1
        alpha = np.exp(-4.6 * (dim - 1))
        alpha = min(max(alpha, 0.01), 1)
        prev = alpha * c[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def ichimoku(h, l, c, tenkan_n=9, kijun_n=26, span_b_n=52):
    tenkan = (rolling_max(h, tenkan_n) + rolling_min(l, tenkan_n)) / 2
    kijun = (rolling_max(h, kijun_n) + rolling_min(l, kijun_n)) / 2
    span_a = shift((tenkan + kijun) / 2, kijun_n)
    span_b = shift((rolling_max(h, span_b_n) + rolling_min(l, span_b_n)) / 2, kijun_n)
    chikou = shift(c, -kijun_n)
    return tenkan, kijun, span_a, span_b, chikou


def fisher(h, l, n):
    mid = (h + l) / 2
    low = rolling_min(l, n)
    high = rolling_max(h, n)
    span = high - low
    raw = 2 * ((mid - low) / np.where(span == 0, np.nan, span) - 0.5)
    raw = np.clip(np.nan_to_num(raw, nan=0.0), -0.999, 0.999)
    value = _nan(len(h))
    prev = 0.0
    prev_f = 0.0
    for i in range(len(h)):
        prev = 0.33 * raw[i] + 0.67 * prev
        prev = min(max(prev, -0.999), 0.999)
        fish = 0.5 * np.log((1 + prev) / (1 - prev)) + 0.5 * prev_f
        value[i] = fish
        prev_f = fish
    value[: int(n)] = np.nan
    return value, shift(value)


def tsi(c, long, short):
    delta = c - shift(c)
    delta[0] = 0
    abs_delta = np.abs(delta)
    num = ema(ema(delta, long), short)
    den = ema(ema(abs_delta, long), short)
    return 100 * num / np.where(den == 0, np.nan, den)


def ultimate(h, l, c, s=7, m=14, l_=28):
    prev = shift(c)
    bp = c - np.minimum(l, prev)
    tr = np.maximum(h, prev) - np.minimum(l, prev)
    def avg(n):
        return rolling_sum(bp, n) / np.where(rolling_sum(tr, n) == 0, np.nan, rolling_sum(tr, n))
    return 100 * (4 * avg(s) + 2 * avg(m) + avg(l_)) / 7


def awesome(h, l):
    mid = (h + l) / 2
    return sma(mid, 5) - sma(mid, 34)


def cmo(c, n):
    delta = c - shift(c)
    up = rolling_sum(np.maximum(delta, 0), n)
    down = rolling_sum(np.maximum(-delta, 0), n)
    return 100 * (up - down) / np.where((up + down) == 0, np.nan, up + down)


def kst(c):
    r1 = sma(roc(c, 10), 10)
    r2 = sma(roc(c, 15), 10)
    r3 = sma(roc(c, 20), 10)
    r4 = sma(roc(c, 30), 15)
    line = r1 + 2 * r2 + 3 * r3 + 4 * r4
    return line, sma(line, 9)


def smi(h, l, c, n=13, smooth=25, signal=2):
    hh = rolling_max(h, n)
    ll = rolling_min(l, n)
    diff = c - (hh + ll) / 2
    span = hh - ll
    smi_ = 100 * ema(ema(diff, smooth), smooth) / np.where(ema(ema(span, smooth), smooth) == 0, np.nan, ema(ema(span, smooth), smooth) / 2)
    # The /2 on the range is the usual Stochastic Momentum Index form.
    return smi_, ema(smi_, signal)


def connors_rsi(c, rsi_n=3, streak_n=2, rank_n=100):
    base = rsi(c, rsi_n)
    delta = np.sign(c - shift(c))
    delta[0] = 0
    streak = np.zeros(len(c))
    for i in range(1, len(c)):
        if delta[i] == 0:
            streak[i] = 0
        elif delta[i] == delta[i - 1]:
            streak[i] = streak[i - 1] + delta[i]
        else:
            streak[i] = delta[i]
    streak_rsi = rsi(streak, streak_n)
    rank = _nan(len(c))
    changes = roc(c, 1)
    for i in range(rank_n, len(c)):
        window = changes[i - rank_n + 1 : i + 1]
        rank[i] = np.mean(window <= changes[i]) * 100
    return (base + streak_rsi + rank) / 3


def rvi(o, h, l, c, n=10):
    num = rolling_sum(c - o, n)  # simplified relative vigor
    den = rolling_sum(h - l, n)
    line = num / np.where(den == 0, np.nan, den)
    signal = (line + 2 * shift(line) + 2 * shift(line, 2) + shift(line, 3)) / 6
    return line, signal


def aroon(h, l, n):
    up = _nan(len(h))
    down = _nan(len(h))
    n = int(n)
    for i in range(n, len(h)):
        hw = h[i - n : i + 1]
        lw = l[i - n : i + 1]
        up[i] = 100 * (n - (n - np.argmax(hw))) / n
        down[i] = 100 * (n - (n - np.argmin(lw))) / n
    return up, down


def vortex(h, l, c, n):
    prev_l = shift(l)
    prev_h = shift(h)
    tr = true_range(h, l, c)
    vmp = np.abs(h - prev_l)
    vmm = np.abs(l - prev_h)
    return rolling_sum(vmp, n) / rolling_sum(tr, n), rolling_sum(vmm, n) / rolling_sum(tr, n)


def mass_index(h, l, n=25):
    span = h - l
    ema1 = ema(span, 9)
    ema2 = ema(ema1, 9)
    ratio = ema1 / np.where(ema2 == 0, np.nan, ema2)
    return rolling_sum(ratio, n)


def choppiness(h, l, c, n):
    tr_sum = rolling_sum(true_range(h, l, c), n)
    span = rolling_max(h, n) - rolling_min(l, n)
    return 100 * np.log10(tr_sum / np.where(span == 0, np.nan, span)) / np.log10(n)


def ulcer(c, n):
    out = _nan(len(c))
    peak = rolling_max(c, n)
    dd = 100 * (c - peak) / np.where(peak == 0, np.nan, peak)
    for i in range(n - 1, len(c)):
        window = dd[i - n + 1 : i + 1]
        out[i] = np.sqrt(np.mean(window ** 2))
    return out


def mfi(h, l, c, v, n):
    tp = typical(h, l, c)
    flow = tp * v
    direction = tp - shift(tp)
    pos = rolling_sum(np.where(direction > 0, flow, 0), n)
    neg = rolling_sum(np.where(direction < 0, flow, 0), n)
    ratio = pos / np.where(neg == 0, np.nan, neg)
    return 100 - 100 / (1 + ratio)


def cmf(h, l, c, v, n):
    span = h - l
    clv = ((c - l) - (h - c)) / np.where(span == 0, np.nan, span)
    return rolling_sum(clv * v, n) / np.where(rolling_sum(v, n) == 0, np.nan, rolling_sum(v, n))


def force(c, v, n):
    return ema((c - shift(c)) * v, n)


def emv(h, l, v, n):
    mid = (h + l) / 2
    prev = shift(mid)
    span = h - l
    box = (v / 1e8) / np.where(span == 0, np.nan, span)
    raw = (mid - prev) / np.where(box == 0, np.nan, box)
    return sma(raw, n)


def ad_line(h, l, c, v):
    span = h - l
    clv = ((c - l) - (h - c)) / np.where(span == 0, np.nan, span)
    return np.cumsum(np.nan_to_num(clv, nan=0.0) * v)


def nvi_pvi(c, v):
    nvi = np.ones(len(c)) * 1000
    pvi = np.ones(len(c)) * 1000
    for i in range(1, len(c)):
        change = 0 if c[i - 1] == 0 else (c[i] - c[i - 1]) / c[i - 1]
        if v[i] < v[i - 1]:
            nvi[i] = nvi[i - 1] * (1 + change)
            pvi[i] = pvi[i - 1]
        elif v[i] > v[i - 1]:
            pvi[i] = pvi[i - 1] * (1 + change)
            nvi[i] = nvi[i - 1]
        else:
            nvi[i] = nvi[i - 1]
            pvi[i] = pvi[i - 1]
    return nvi, pvi


def klinger(h, l, c, v):
    dm = h + l + c
    trend = np.sign(dm - shift(dm))
    trend[0] = 1
    daily_range = h - l
    cm = np.zeros(len(c))
    for i in range(1, len(c)):
        if trend[i] == trend[i - 1]:
            cm[i] = cm[i - 1] + daily_range[i]
        else:
            cm[i] = daily_range[i] + daily_range[i - 1]
    vf = v * np.abs(2 * daily_range / np.where(cm == 0, np.nan, cm) - 1) * trend * 100
    line = ema(np.nan_to_num(vf, nan=0.0), 34) - ema(np.nan_to_num(vf, nan=0.0), 55)
    return line, ema(line, 13)


def williams_ad(h, l, c):
    out = np.zeros(len(c))
    prev = c[0]
    for i in range(1, len(c)):
        if c[i] > prev:
            out[i] = out[i - 1] + (c[i] - min(l[i], prev))
        elif c[i] < prev:
            out[i] = out[i - 1] + (c[i] - max(h[i], prev))
        else:
            out[i] = out[i - 1]
        prev = c[i]
    return out


def percent_rank(x, n):
    out = _nan(len(x))
    n = int(n)
    for i in range(n - 1, len(x)):
        window = x[i - n + 1 : i + 1]
        out[i] = float(np.mean(window <= x[i]) * 100)
    return out


def zscore(x, n):
    mean = sma(x, n)
    dev = stdev(x, n)
    return (x - mean) / np.where(dev == 0, np.nan, dev)


def drawdown(c):
    peak = np.maximum.accumulate(c)
    return (c / np.where(peak == 0, np.nan, peak) - 1) * 100


def rolling_sharpe(c, n):
    ret = c / shift(c) - 1
    mean = rolling_mean(ret, n)
    dev = rolling_std(ret, n)
    return mean / np.where(dev == 0, np.nan, dev) * np.sqrt(252)


def _param(params, key, default):
    value = params.get(key, default)
    if isinstance(default, int):
        return int(value)
    return float(value)


def _num(key, label, default, min_, max_, step=1):
    return {"key": key, "label": label, "type": "number", "default": default, "min": min_, "max": max_, "step": step}


STUDIES = []


def _add(study_id, name, section, pane, params, outputs, fn):
    STUDIES.append(
        {
            "id": study_id,
            "name": name,
            "section": section,
            "pane": pane,
            "params": params,
            "outputs": outputs,
            "fn": fn,
        }
    )


def _build():
    if STUDIES:
        return
    P = "price"
    O = "osc"
    MA = "Moving averages"
    B = "Bands and channels"
    T = "Trend"
    M = "Momentum"
    V = "Volatility"
    VO = "Volume"
    S = "Price statistics"

    _add("sma", "SMA", MA, P, [_num("length", "Length", 20, 2, 400)], ["sma"], lambda f, p: {"sma": sma(f.c, _param(p, "length", 20))})
    _add("ema", "EMA", MA, P, [_num("length", "Length", 20, 2, 400)], ["ema"], lambda f, p: {"ema": ema(f.c, _param(p, "length", 20))})
    _add("wma", "WMA", MA, P, [_num("length", "Length", 20, 2, 400)], ["wma"], lambda f, p: {"wma": wma(f.c, _param(p, "length", 20))})
    _add("dema", "DEMA", MA, P, [_num("length", "Length", 20, 2, 250)], ["dema"], lambda f, p: {"dema": dema(f.c, _param(p, "length", 20))})
    _add("tema", "TEMA", MA, P, [_num("length", "Length", 20, 2, 200)], ["tema"], lambda f, p: {"tema": tema(f.c, _param(p, "length", 20))})
    _add("hma", "Hull MA", MA, P, [_num("length", "Length", 20, 2, 250)], ["hma"], lambda f, p: {"hma": hma(f.c, _param(p, "length", 20))})
    _add("kama", "KAMA", MA, P, [_num("length", "ER length", 10, 2, 100)], ["kama"], lambda f, p: {"kama": kama(f.c, _param(p, "length", 10))})
    _add("zlema", "Zero-lag EMA", MA, P, [_num("length", "Length", 20, 2, 250)], ["zlema"], lambda f, p: {"zlema": zlema(f.c, _param(p, "length", 20))})
    _add("alma", "ALMA", MA, P, [_num("length", "Length", 20, 2, 250)], ["alma"], lambda f, p: {"alma": alma(f.c, _param(p, "length", 20))})
    _add("vwma", "VWMA", MA, P, [_num("length", "Length", 20, 2, 250)], ["vwma"], lambda f, p: {"vwma": rolling_sum(f.c * f.v, _param(p, "length", 20)) / np.where(rolling_sum(f.v, _param(p, "length", 20)) == 0, np.nan, rolling_sum(f.v, _param(p, "length", 20)))})
    _add("rma", "Wilder RMA", MA, P, [_num("length", "Length", 14, 2, 250)], ["rma"], lambda f, p: {"rma": rma(f.c, _param(p, "length", 14))})
    _add("mcginley", "McGinley Dynamic", MA, P, [_num("length", "Length", 14, 2, 200)], ["mcginley"], lambda f, p: {"mcginley": mcginley(f.c, _param(p, "length", 14))})
    _add("t3", "Tillson T3", MA, P, [_num("length", "Length", 8, 2, 100)], ["t3"], lambda f, p: {"t3": t3(f.c, _param(p, "length", 8))})
    _add("vidya", "VIDYA", MA, P, [_num("length", "Length", 14, 2, 200)], ["vidya"], lambda f, p: {"vidya": vidya(f.c, _param(p, "length", 14))})
    _add("lsma", "Least-squares MA", MA, P, [_num("length", "Length", 25, 5, 250)], ["lsma"], lambda f, p: {"lsma": linreg(f.c, _param(p, "length", 25))[0]})
    _add("tsf", "Time-series forecast", MA, P, [_num("length", "Length", 25, 5, 250)], ["tsf"], lambda f, p: {"tsf": tsf(f.c, _param(p, "length", 25))})
    _add("supersmoother", "Ehlers Super Smoother", MA, P, [_num("length", "Period", 10, 2, 100)], ["ss"], lambda f, p: {"ss": supersmoother(f.c, _param(p, "length", 10))})
    _add("frama", "FRAMA", MA, P, [_num("length", "Length", 16, 4, 80)], ["frama"], lambda f, p: {"frama": frama(f.c, _param(p, "length", 16))})
    ribbon = [(f"r{k}", f"EMA {k}", d) for k, d in enumerate((8, 13, 21, 34, 55), start=1)]
    _add("ema_ribbon", "EMA ribbon", MA, P, [_num(key, label, d, 2, 400) for key, label, d in ribbon], [key for key, _, _ in ribbon],
         lambda f, p: {key: ema(f.c, _param(p, key, d)) for key, _, d in ribbon})

    def _bb(f, p):
        n, k = _param(p, "length", 20), _param(p, "mult", 2)
        upper, mid, lower = bbands(f.c, n, k)
        return {"upper": upper, "mid": mid, "lower": lower}

    _add("bbands", "Bollinger Bands", B, P, [_num("length", "Length", 20, 5, 200), _num("mult", "Stdev", 2, 0.5, 4, 0.1)], ["upper", "mid", "lower"], _bb)
    _add("bb_percent", "Bollinger %B", B, O, [_num("length", "Length", 20, 5, 200), _num("mult", "Stdev", 2, 0.5, 4, 0.1)], ["percent_b"], lambda f, p: {"percent_b": (lambda u, m, l: (f.c - l) / np.where((u - l) == 0, np.nan, u - l))(*bbands(f.c, _param(p, "length", 20), _param(p, "mult", 2)))})
    _add("bb_width", "Bollinger bandwidth", B, O, [_num("length", "Length", 20, 5, 200)], ["width"], lambda f, p: {"width": (lambda u, m, l: (u - l) / np.where(m == 0, np.nan, m))(*bbands(f.c, _param(p, "length", 20), 2))})

    def _kc(f, p):
        n, mult = _param(p, "length", 20), _param(p, "mult", 2)
        mid = ema(f.c, n)
        band = atr(f.h, f.l, f.c, n) * mult
        return {"upper": mid + band, "mid": mid, "lower": mid - band}

    _add("keltner", "Keltner Channels", B, P, [_num("length", "Length", 20, 5, 200), _num("mult", "ATR mult", 2, 0.5, 5, 0.1)], ["upper", "mid", "lower"], _kc)
    _add("keltner_width", "Keltner width", B, O, [_num("length", "Length", 20, 5, 200)], ["width"], lambda f, p: {"width": (2 * atr(f.h, f.l, f.c, _param(p, "length", 20))) / np.where(ema(f.c, _param(p, "length", 20)) == 0, np.nan, ema(f.c, _param(p, "length", 20)))})

    def _don(f, p):
        upper, mid, lower = donchian(f.h, f.l, _param(p, "length", 20))
        return {"upper": upper, "mid": mid, "lower": lower}

    _add("donchian", "Donchian Channel", B, P, [_num("length", "Length", 20, 5, 250)], ["upper", "mid", "lower"], _don)
    _add("envelope", "Moving-average envelope", B, P, [_num("length", "Length", 20, 2, 250), _num("pct", "Percent", 2.5, 0.2, 15, 0.1)], ["upper", "mid", "lower"], lambda f, p: {"upper": sma(f.c, _param(p, "length", 20)) * (1 + _param(p, "pct", 2.5) / 100), "mid": sma(f.c, _param(p, "length", 20)), "lower": sma(f.c, _param(p, "length", 20)) * (1 - _param(p, "pct", 2.5) / 100)})
    _add("atr_bands", "ATR bands", B, P, [_num("length", "ATR", 14, 2, 100), _num("mult", "Mult", 2, 0.5, 6, 0.1)], ["upper", "lower"], lambda f, p: {"upper": f.c + _param(p, "mult", 2) * atr(f.h, f.l, f.c, _param(p, "length", 14)), "lower": f.c - _param(p, "mult", 2) * atr(f.h, f.l, f.c, _param(p, "length", 14))})
    _add("chandelier_long", "Chandelier long stop", B, P, [_num("length", "Length", 22, 5, 100), _num("mult", "ATR", 3, 0.5, 6, 0.1)], ["stop"], lambda f, p: {"stop": rolling_max(f.h, _param(p, "length", 22)) - _param(p, "mult", 3) * atr(f.h, f.l, f.c, _param(p, "length", 22))})
    _add("chandelier_short", "Chandelier short stop", B, P, [_num("length", "Length", 22, 5, 100), _num("mult", "ATR", 3, 0.5, 6, 0.1)], ["stop"], lambda f, p: {"stop": rolling_min(f.l, _param(p, "length", 22)) + _param(p, "mult", 3) * atr(f.h, f.l, f.c, _param(p, "length", 22))})

    def _pivots(f, p):
        prev_h, prev_l, prev_c = shift(f.h), shift(f.l), shift(f.c)
        pivot = (prev_h + prev_l + prev_c) / 3
        return {"pp": pivot, "r1": 2 * pivot - prev_l, "s1": 2 * pivot - prev_h, "r2": pivot + (prev_h - prev_l), "s2": pivot - (prev_h - prev_l)}

    _add("pivots", "Floor pivots", B, P, [], ["pp", "r1", "s1", "r2", "s2"], _pivots)
    _add("stddev_channel", "StdDev channel", B, P, [_num("length", "Length", 20, 5, 200)], ["upper", "mid", "lower"], lambda f, p: {"upper": sma(f.c, _param(p, "length", 20)) + stdev(f.c, _param(p, "length", 20)), "mid": sma(f.c, _param(p, "length", 20)), "lower": sma(f.c, _param(p, "length", 20)) - stdev(f.c, _param(p, "length", 20))})

    _add("psar", "Parabolic SAR", T, P, [_num("step", "Step", 0.02, 0.01, 0.1, 0.01), _num("max", "Max", 0.2, 0.05, 0.5, 0.01)], ["sar"], lambda f, p: {"sar": psar(f.h, f.l, _param(p, "step", 0.02), _param(p, "max", 0.2))})
    _add("supertrend", "Supertrend", T, P, [_num("length", "ATR", 10, 2, 50), _num("mult", "Mult", 3, 0.5, 6, 0.1)], ["supertrend"], lambda f, p: {"supertrend": supertrend(f.h, f.l, f.c, _param(p, "length", 10), _param(p, "mult", 3))[0]})

    def _ichi(f, p):
        tenkan, kijun, span_a, span_b, chikou = ichimoku(f.h, f.l, f.c)
        return {"tenkan": tenkan, "kijun": kijun, "span_a": span_a, "span_b": span_b, "chikou": chikou}

    _add("ichimoku", "Ichimoku cloud", T, P, [], ["tenkan", "kijun", "span_a", "span_b", "chikou"], _ichi)
    _add("adx", "ADX / DMI", T, O, [_num("length", "Length", 14, 2, 50)], ["adx", "plus_di", "minus_di"], lambda f, p: dict(zip(["adx", "plus_di", "minus_di"], adx_pack(f.h, f.l, f.c, _param(p, "length", 14)))))
    _add("aroon", "Aroon", T, O, [_num("length", "Length", 25, 5, 100)], ["up", "down"], lambda f, p: dict(zip(["up", "down"], aroon(f.h, f.l, _param(p, "length", 25)))))
    _add("aroon_osc", "Aroon oscillator", T, O, [_num("length", "Length", 25, 5, 100)], ["osc"], lambda f, p: {"osc": (lambda u, d: u - d)(*aroon(f.h, f.l, _param(p, "length", 25)))})
    _add("vortex", "Vortex", T, O, [_num("length", "Length", 14, 2, 50)], ["vi_plus", "vi_minus"], lambda f, p: dict(zip(["vi_plus", "vi_minus"], vortex(f.h, f.l, f.c, _param(p, "length", 14)))))
    _add("linreg_slope", "Linear-regression slope", T, O, [_num("length", "Length", 20, 5, 200)], ["slope"], lambda f, p: {"slope": linreg(f.c, _param(p, "length", 20))[1]})
    _add("dpo", "Detrended price oscillator", T, O, [_num("length", "Length", 20, 5, 100)], ["dpo"], lambda f, p: {"dpo": shift(f.c, int(_param(p, "length", 20) / 2) + 1) - sma(f.c, _param(p, "length", 20))})
    _add("trix", "TRIX", T, O, [_num("length", "Length", 15, 3, 50)], ["trix"], lambda f, p: {"trix": roc(ema(ema(ema(f.c, _param(p, "length", 15)), _param(p, "length", 15)), _param(p, "length", 15)), 1)})
    _add("mass", "Mass Index", T, O, [_num("length", "Sum", 25, 5, 50)], ["mass"], lambda f, p: {"mass": mass_index(f.h, f.l, _param(p, "length", 25))})
    _add("chop", "Choppiness Index", T, O, [_num("length", "Length", 14, 5, 50)], ["chop"], lambda f, p: {"chop": choppiness(f.h, f.l, f.c, _param(p, "length", 14))})
    _add("qstick", "Qstick", T, O, [_num("length", "Length", 14, 2, 50)], ["qstick"], lambda f, p: {"qstick": sma(f.c - f.o, _param(p, "length", 14))})
    _add("elder_ray", "Elder Ray", T, O, [_num("length", "EMA", 13, 2, 50)], ["bull", "bear"], lambda f, p: {"bull": f.h - ema(f.c, _param(p, "length", 13)), "bear": f.l - ema(f.c, _param(p, "length", 13))})
    _add("coppock", "Coppock curve", T, O, [], ["coppock"], lambda f, p: {"coppock": wma(roc(f.c, 14) + roc(f.c, 11), 10)})
    _add("trend_intensity", "Trend intensity", T, O, [_num("length", "Length", 20, 5, 100)], ["tii"], lambda f, p: {"tii": 100 * rolling_sum((f.c > sma(f.c, _param(p, "length", 20))).astype(float), _param(p, "length", 20)) / _param(p, "length", 20)})

    _add("rsi", "RSI", M, O, [_num("length", "Length", 14, 2, 50)], ["rsi"], lambda f, p: {"rsi": rsi(f.c, _param(p, "length", 14))})
    _add("stoch", "Stochastic", M, O, [_num("length", "Length", 14, 2, 50), _num("smooth", "Smooth", 3, 1, 10)], ["k", "d"], lambda f, p: dict(zip(["k", "d"], stoch(f.h, f.l, f.c, _param(p, "length", 14), _param(p, "smooth", 3)))))
    _add("stochrsi", "Stochastic RSI", M, O, [_num("length", "Length", 14, 2, 50)], ["k", "d"], lambda f, p: dict(zip(["k", "d"], stoch(rsi(f.c, _param(p, "length", 14)), rsi(f.c, _param(p, "length", 14)), rsi(f.c, _param(p, "length", 14)), _param(p, "length", 14), 3))))
    _add("macd", "MACD", M, O, [_num("fast", "Fast", 12, 2, 50), _num("slow", "Slow", 26, 5, 100), _num("signal", "Signal", 9, 2, 30)], ["macd", "signal", "hist"], lambda f, p: dict(zip(["macd", "signal", "hist"], macd(f.c, _param(p, "fast", 12), _param(p, "slow", 26), _param(p, "signal", 9)))))
    _add("ppo", "Percentage price oscillator", M, O, [_num("fast", "Fast", 12, 2, 50), _num("slow", "Slow", 26, 5, 100)], ["ppo"], lambda f, p: {"ppo": 100 * (ema(f.c, _param(p, "fast", 12)) - ema(f.c, _param(p, "slow", 26))) / np.where(ema(f.c, _param(p, "slow", 26)) == 0, np.nan, ema(f.c, _param(p, "slow", 26)))})
    _add("apo", "Absolute price oscillator", M, O, [_num("fast", "Fast", 12, 2, 50), _num("slow", "Slow", 26, 5, 100)], ["apo"], lambda f, p: {"apo": ema(f.c, _param(p, "fast", 12)) - ema(f.c, _param(p, "slow", 26))})
    _add("cci", "CCI", M, O, [_num("length", "Length", 20, 2, 100)], ["cci"], lambda f, p: {"cci": (lambda tp, n: (tp - sma(tp, n)) / np.where(0.015 * sma(np.abs(tp - sma(tp, n)), n) == 0, np.nan, 0.015 * sma(np.abs(tp - sma(tp, n)), n)))(typical(f.h, f.l, f.c), _param(p, "length", 20))})
    _add("willr", "Williams %R", M, O, [_num("length", "Length", 14, 2, 50)], ["willr"], lambda f, p: {"willr": -100 * (rolling_max(f.h, _param(p, "length", 14)) - f.c) / np.where((rolling_max(f.h, _param(p, "length", 14)) - rolling_min(f.l, _param(p, "length", 14))) == 0, np.nan, rolling_max(f.h, _param(p, "length", 14)) - rolling_min(f.l, _param(p, "length", 14)))})
    _add("roc", "Rate of change", M, O, [_num("length", "Length", 12, 1, 250)], ["roc"], lambda f, p: {"roc": roc(f.c, _param(p, "length", 12))})
    _add("mom", "Momentum", M, O, [_num("length", "Length", 10, 1, 250)], ["mom"], lambda f, p: {"mom": mom(f.c, _param(p, "length", 10))})
    _add("tsi", "True strength index", M, O, [_num("long", "Long", 25, 5, 80), _num("short", "Short", 13, 2, 40)], ["tsi"], lambda f, p: {"tsi": tsi(f.c, _param(p, "long", 25), _param(p, "short", 13))})
    _add("uo", "Ultimate oscillator", M, O, [], ["uo"], lambda f, p: {"uo": ultimate(f.h, f.l, f.c)})
    _add("ao", "Awesome oscillator", M, O, [], ["ao"], lambda f, p: {"ao": awesome(f.h, f.l)})
    _add("cmo", "Chande momentum", M, O, [_num("length", "Length", 14, 2, 50)], ["cmo"], lambda f, p: {"cmo": cmo(f.c, _param(p, "length", 14))})
    _add("fisher", "Fisher transform", M, O, [_num("length", "Length", 10, 2, 50)], ["fisher", "trigger"], lambda f, p: dict(zip(["fisher", "trigger"], fisher(f.h, f.l, _param(p, "length", 10)))))
    _add("ifisher", "Inverse Fisher RSI", M, O, [_num("length", "RSI", 5, 2, 30)], ["ifisher"], lambda f, p: {"ifisher": (lambda value: (np.exp(2 * value) - 1) / (np.exp(2 * value) + 1))(0.1 * (rsi(f.c, _param(p, "length", 5)) - 50))})
    _add("kst", "Know Sure Thing", M, O, [], ["kst", "signal"], lambda f, p: dict(zip(["kst", "signal"], kst(f.c))))
    _add("bop", "Balance of power", M, O, [_num("length", "Smooth", 14, 1, 50)], ["bop"], lambda f, p: {"bop": sma((f.c - f.o) / np.where((f.h - f.l) == 0, np.nan, f.h - f.l), _param(p, "length", 14))})
    _add("smi", "Stochastic momentum index", M, O, [_num("length", "Length", 13, 2, 50)], ["smi", "signal"], lambda f, p: dict(zip(["smi", "signal"], smi(f.h, f.l, f.c, _param(p, "length", 13)))))
    _add("connors", "Connors RSI", M, O, [], ["crsi"], lambda f, p: {"crsi": connors_rsi(f.c)})
    _add("rvi", "Relative vigor index", M, O, [_num("length", "Length", 10, 2, 40)], ["rvi", "signal"], lambda f, p: dict(zip(["rvi", "signal"], rvi(f.o, f.h, f.l, f.c, _param(p, "length", 10)))))
    _add("psych", "Psychological line", M, O, [_num("length", "Length", 12, 2, 50)], ["psych"], lambda f, p: {"psych": 100 * rolling_sum((f.c > shift(f.c)).astype(float), _param(p, "length", 12)) / _param(p, "length", 12)})
    _add("rmi", "Relative momentum index", M, O, [_num("length", "RSI", 14, 2, 40), _num("momentum", "Momentum", 5, 1, 20)], ["rmi"], lambda f, p: {"rmi": rsi(np.cumsum(np.nan_to_num(mom(f.c, _param(p, "momentum", 5)), nan=0.0)), _param(p, "length", 14))})
    _add("derivative", "Derivative oscillator", M, O, [_num("length", "RSI", 14, 2, 40)], ["deriv"], lambda f, p: {"deriv": rsi(f.c, _param(p, "length", 14)) - sma(rsi(f.c, _param(p, "length", 14)), 9)})
    _add("cmo_smooth", "Smoothed CMO", M, O, [_num("length", "Length", 14, 2, 40)], ["cmo"], lambda f, p: {"cmo": ema(cmo(f.c, _param(p, "length", 14)), 5)})
    _add("rsi_signal", "RSI with signal", M, O, [_num("length", "Length", 14, 2, 40), _num("signal", "Signal", 9, 2, 30)], ["rsi", "signal"], lambda f, p: {"rsi": rsi(f.c, _param(p, "length", 14)), "signal": sma(rsi(f.c, _param(p, "length", 14)), _param(p, "signal", 9))})
    _add("ao_signal", "Awesome oscillator signal", M, O, [], ["ao", "signal"], lambda f, p: {"ao": awesome(f.h, f.l), "signal": sma(awesome(f.h, f.l), 5)})
    _add("macd_hist", "MACD histogram", M, O, [], ["hist"], lambda f, p: {"hist": macd(f.c, 12, 26, 9)[2]})
    _add("roc_smooth", "Smoothed ROC", M, O, [_num("length", "Length", 12, 1, 100)], ["roc"], lambda f, p: {"roc": sma(roc(f.c, _param(p, "length", 12)), 5)})

    _add("atr", "Average true range", V, O, [_num("length", "Length", 14, 2, 50)], ["atr"], lambda f, p: {"atr": atr(f.h, f.l, f.c, _param(p, "length", 14))})
    _add("natr", "Normalized ATR", V, O, [_num("length", "Length", 14, 2, 50)], ["natr"], lambda f, p: {"natr": 100 * atr(f.h, f.l, f.c, _param(p, "length", 14)) / np.where(f.c == 0, np.nan, f.c)})
    _add("tr", "True range", V, O, [], ["tr"], lambda f, p: {"tr": true_range(f.h, f.l, f.c)})
    _add("hv", "Historical volatility", V, O, [_num("length", "Length", 20, 5, 120)], ["hv"], lambda f, p: {"hv": rolling_std(np.log(f.c / np.where(shift(f.c) == 0, np.nan, shift(f.c))), _param(p, "length", 20)) * np.sqrt(252) * 100})
    _add("stddev", "Standard deviation", V, O, [_num("length", "Length", 20, 2, 120)], ["stddev"], lambda f, p: {"stddev": stdev(f.c, _param(p, "length", 20))})
    _add("ulcer", "Ulcer Index", V, O, [_num("length", "Length", 14, 5, 100)], ["ulcer"], lambda f, p: {"ulcer": ulcer(f.c, _param(p, "length", 14))})
    _add("chaikin_vol", "Chaikin volatility", V, O, [_num("length", "EMA", 10, 2, 40)], ["cv"], lambda f, p: {"cv": roc(ema(f.h - f.l, _param(p, "length", 10)), 10)})
    _add("atrp", "ATR percent", V, O, [_num("length", "Length", 14, 2, 50)], ["atrp"], lambda f, p: {"atrp": 100 * atr(f.h, f.l, f.c, _param(p, "length", 14)) / np.where(sma(f.c, _param(p, "length", 14)) == 0, np.nan, sma(f.c, _param(p, "length", 14)))})
    _add("range_ma", "Average range", V, O, [_num("length", "Length", 14, 2, 50)], ["range"], lambda f, p: {"range": sma(f.h - f.l, _param(p, "length", 14))})
    _add("hv_close", "Close-to-close vol", V, O, [_num("length", "Length", 30, 5, 120)], ["hv"], lambda f, p: {"hv": rolling_std(f.c / shift(f.c) - 1, _param(p, "length", 30)) * np.sqrt(252) * 100})

    _add("obv", "On-balance volume", VO, O, [], ["obv"], lambda f, p: {"obv": obv(f.c, f.v)})
    _add("ad", "Accumulation/distribution", VO, O, [], ["ad"], lambda f, p: {"ad": ad_line(f.h, f.l, f.c, f.v)})
    _add("cmf", "Chaikin money flow", VO, O, [_num("length", "Length", 20, 2, 50)], ["cmf"], lambda f, p: {"cmf": cmf(f.h, f.l, f.c, f.v, _param(p, "length", 20))})
    _add("mfi", "Money flow index", VO, O, [_num("length", "Length", 14, 2, 50)], ["mfi"], lambda f, p: {"mfi": mfi(f.h, f.l, f.c, f.v, _param(p, "length", 14))})
    _add("force", "Force index", VO, O, [_num("length", "EMA", 13, 1, 40)], ["force"], lambda f, p: {"force": force(f.c, f.v, _param(p, "length", 13))})
    _add("emv", "Ease of movement", VO, O, [_num("length", "Length", 14, 1, 40)], ["emv"], lambda f, p: {"emv": emv(f.h, f.l, f.v, _param(p, "length", 14))})
    _add("vol_sma", "Volume SMA", VO, O, [_num("length", "Length", 20, 2, 100)], ["volume"], lambda f, p: {"volume": sma(f.v, _param(p, "length", 20))})
    _add("vol_ema", "Volume EMA", VO, O, [_num("length", "Length", 20, 2, 100)], ["volume"], lambda f, p: {"volume": ema(f.v, _param(p, "length", 20))})
    _add("nvi", "Negative volume index", VO, O, [], ["nvi"], lambda f, p: {"nvi": nvi_pvi(f.c, f.v)[0]})
    _add("pvi", "Positive volume index", VO, O, [], ["pvi"], lambda f, p: {"pvi": nvi_pvi(f.c, f.v)[1]})
    _add("vol_osc", "Volume oscillator", VO, O, [_num("fast", "Fast", 5, 2, 30), _num("slow", "Slow", 20, 5, 80)], ["osc"], lambda f, p: {"osc": 100 * (sma(f.v, _param(p, "fast", 5)) - sma(f.v, _param(p, "slow", 20))) / np.where(sma(f.v, _param(p, "slow", 20)) == 0, np.nan, sma(f.v, _param(p, "slow", 20)))})
    _add("chaikin_osc", "Chaikin oscillator", VO, O, [], ["osc"], lambda f, p: {"osc": ema(ad_line(f.h, f.l, f.c, f.v), 3) - ema(ad_line(f.h, f.l, f.c, f.v), 10)})
    _add("vwap", "Session VWAP", VO, P, [], ["vwap"], lambda f, p: {"vwap": vwap(f.h, f.l, f.c, f.v)})
    _add("vwap_dev", "VWAP deviation", VO, O, [], ["dev"], lambda f, p: {"dev": 100 * (f.c / np.where(vwap(f.h, f.l, f.c, f.v) == 0, np.nan, vwap(f.h, f.l, f.c, f.v)) - 1)})
    _add("vpt", "Volume price trend", VO, O, [], ["vpt"], lambda f, p: {"vpt": np.cumsum(np.nan_to_num(f.v * (f.c / np.where(shift(f.c) == 0, np.nan, shift(f.c)) - 1), nan=0.0))})
    _add("twiggs", "Twiggs money flow", VO, O, [_num("length", "Length", 21, 5, 60)], ["tmf"], lambda f, p: {"tmf": (lambda adv, length: rolling_sum(adv, length) / np.where(rolling_sum(true_range(f.h, f.l, f.c), length) == 0, np.nan, rolling_sum(true_range(f.h, f.l, f.c), length)))(np.where(f.c >= shift(f.c), f.c - np.minimum(f.l, shift(f.c)), f.c - np.maximum(f.h, shift(f.c))), _param(p, "length", 21))})
    _add("klinger", "Klinger oscillator", VO, O, [], ["kvo", "signal"], lambda f, p: dict(zip(["kvo", "signal"], klinger(f.h, f.l, f.c, f.v))))
    _add("williams_ad", "Williams accumulation", VO, O, [], ["wad"], lambda f, p: {"wad": williams_ad(f.h, f.l, f.c)})
    _add("intraday_intensity", "Intraday intensity", VO, O, [_num("length", "Length", 21, 2, 60)], ["ii"], lambda f, p: {"ii": sma(((2 * f.c - f.h - f.l) / np.where((f.h - f.l) == 0, np.nan, f.h - f.l)) * f.v, _param(p, "length", 21))})
    _add("emv_signal", "Ease of movement signal", VO, O, [_num("length", "Length", 14, 2, 40)], ["emv", "signal"], lambda f, p: {"emv": emv(f.h, f.l, f.v, _param(p, "length", 14)), "signal": sma(emv(f.h, f.l, f.v, _param(p, "length", 14)), 9)})

    _add("typical", "Typical price", S, P, [], ["typical"], lambda f, p: {"typical": typical(f.h, f.l, f.c)})
    _add("median", "Median price", S, P, [], ["median"], lambda f, p: {"median": median_price(f.h, f.l)})
    _add("wclose", "Weighted close", S, P, [], ["wclose"], lambda f, p: {"wclose": weighted_close(f.h, f.l, f.c)})
    _add("zscore", "Z-score", S, O, [_num("length", "Length", 20, 5, 120)], ["z"], lambda f, p: {"z": zscore(f.c, _param(p, "length", 20))})
    _add("percent_rank", "Percent rank", S, O, [_num("length", "Length", 100, 10, 250)], ["rank"], lambda f, p: {"rank": percent_rank(f.c, _param(p, "length", 100))})
    _add("highest", "Highest high", S, P, [_num("length", "Length", 20, 2, 252)], ["high"], lambda f, p: {"high": rolling_max(f.h, _param(p, "length", 20))})
    _add("lowest", "Lowest low", S, P, [_num("length", "Length", 20, 2, 252)], ["low"], lambda f, p: {"low": rolling_min(f.l, _param(p, "length", 20))})
    _add("drawdown", "Drawdown from peak", S, O, [], ["dd"], lambda f, p: {"dd": drawdown(f.c)})
    _add("gap", "Gap percent", S, O, [], ["gap"], lambda f, p: {"gap": 100 * (f.o / np.where(shift(f.c) == 0, np.nan, shift(f.c)) - 1)})
    _add("clv", "Close location value", S, O, [], ["clv"], lambda f, p: {"clv": ((f.c - f.l) - (f.h - f.c)) / np.where((f.h - f.l) == 0, np.nan, f.h - f.l)})
    _add("range_pct", "Range percent", S, O, [], ["range"], lambda f, p: {"range": 100 * (f.h - f.l) / np.where(f.c == 0, np.nan, f.c)})
    _add("dist_high", "Distance from high", S, O, [_num("length", "Length", 252, 20, 252)], ["dist"], lambda f, p: {"dist": 100 * (f.c / np.where(rolling_max(f.h, _param(p, "length", 252)) == 0, np.nan, rolling_max(f.h, _param(p, "length", 252))) - 1)})
    _add("dist_low", "Distance from low", S, O, [_num("length", "Length", 252, 20, 252)], ["dist"], lambda f, p: {"dist": 100 * (f.c / np.where(rolling_min(f.l, _param(p, "length", 252)) == 0, np.nan, rolling_min(f.l, _param(p, "length", 252))) - 1)})
    _add("ha_close", "Heikin-Ashi close", S, P, [], ["ha"], lambda f, p: {"ha": (f.o + f.h + f.l + f.c) / 4})
    _add("rolling_sharpe", "Rolling Sharpe", S, O, [_num("length", "Length", 63, 10, 252)], ["sharpe"], lambda f, p: {"sharpe": rolling_sharpe(f.c, _param(p, "length", 63))})
    _add("body_pct", "Candle body percent", S, O, [], ["body"], lambda f, p: {"body": 100 * (f.c - f.o) / np.where(f.o == 0, np.nan, f.o)})
    _add("log_return", "Log return", S, O, [], ["log"], lambda f, p: {"log": np.log(f.c / np.where(shift(f.c) == 0, np.nan, shift(f.c)))})
    _add("up_down", "Up/down volume ratio", VO, O, [_num("length", "Length", 20, 2, 60)], ["ratio"], lambda f, p: {"ratio": rolling_sum(np.where(f.c >= shift(f.c), f.v, 0), _param(p, "length", 20)) / np.where(rolling_sum(np.where(f.c < shift(f.c), f.v, 0), _param(p, "length", 20)) == 0, np.nan, rolling_sum(np.where(f.c < shift(f.c), f.v, 0), _param(p, "length", 20)))})

    from top.harmonics import PATTERN_SPECS, study as harmonic_study

    harm_params = [_num("swing", "Swing %", 3, 1, 20, 0.5), _num("tolerance", "Tolerance", 0.05, 0.01, 0.12, 0.01)]
    for spec in PATTERN_SPECS:
        pattern_id = spec["id"]
        _add(
            f"harm_{pattern_id}",
            spec["name"],
            "Harmonics",
            P,
            harm_params,
            ["pattern"],
            lambda f, p, pattern_id=pattern_id: harmonic_study(f, p, pattern_id),
        )
    _add("carney", "Carney all harmonics", "Harmonics", P, harm_params, ["pattern"], lambda f, p: harmonic_study(f, p, None))

    from top.patterns import breakout_study, darvas_study

    _add("darvas", "Darvas box", B, P, [_num("confirm", "Confirm days", 3, 2, 10)], ["upper", "lower"], darvas_study)
    _add("breakout_trend", "Breakout & trend detector", T, P,
         [_num("length", "Range", 20, 5, 120), _num("vol_mult", "Volume ×", 1.5, 1.0, 5.0, 0.1), _num("atr_mult", "Trail ATR", 3.0, 1.0, 8.0, 0.5)],
         ["upper", "lower", "trail"], breakout_study)

    from top.creators import register_studies

    register_studies(_add, P, O)


_build()


def catalog():
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "section": item["section"],
            "pane": item["pane"],
            "params": item["params"],
            "outputs": item["outputs"],
        }
        for item in STUDIES
    ]


def compute(study_id: str, frame: Frame, params: dict | None = None) -> dict:
    params = params or {}
    for item in STUDIES:
        if item["id"] == study_id:
            values = item["fn"](frame, params)
            markers, drawings = [], []
            if isinstance(values, tuple):
                values, markers, *rest = values
                drawings = rest[0] if rest else []
            return {"id": item["id"], "name": item["name"], "pane": item["pane"], "series": values, "markers": markers, "drawings": drawings}
    raise KeyError(study_id)
