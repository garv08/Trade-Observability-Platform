"""Plain-language readings of the desk's studies, strategies, and a rule-based swing plan.

Everything here is computed from stored daily bars. It describes conditions and
historical base rates on the same stock. It is research output, not advice and
not a forecast that price will move a certain way.
"""

from __future__ import annotations

import math

from top import harmonics
from top.backtest import run as run_backtest
from top.indicators import (
    atr,
    catalog as indicator_catalog,
    compute as compute_study,
    ema,
    hma,
    ichimoku,
    macd,
    rolling_max,
    rolling_min,
    rsi,
    sma,
)
from top.strategies import catalog as strategy_catalog, signal

HARMONIC_IDS = {"carney"} | {f"harm_{spec['id']}" for spec in harmonics.PATTERN_SPECS}


# ---------------------------------------------------------------- small helpers

def _list(values):
    if values is None:
        return []
    if hasattr(values, "tolist"):
        values = values.tolist()
    out = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float("nan")
        out.append(number)
    return out


def _ok(value):
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def _last(xs, back=0):
    index = len(xs) - 1 - back
    if index < 0:
        return None
    value = xs[index]
    return value if _ok(value) else None


def _change(xs, n=5):
    now, then = _last(xs), _last(xs, n)
    if now is None or then is None:
        return None
    return now - then


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a / b - 1) * 100


def _rank(xs, value, window=252):
    pool = [x for x in xs[-window:] if _ok(x)]
    if value is None or len(pool) < 20:
        return None
    return 100 * sum(1 for x in pool if x <= value) / len(pool)


def _cross(a, b, lookback=5):
    """Most recent sign change of a-b within lookback bars. Returns (direction, bars_ago)."""
    n = min(len(a), len(b))
    for back in range(0, lookback):
        i = n - 1 - back
        if i < 1:
            break
        now = (a[i] - b[i]) if _ok(a[i]) and _ok(b[i]) else None
        prev = (a[i - 1] - b[i - 1]) if _ok(a[i - 1]) and _ok(b[i - 1]) else None
        if now is None or prev is None:
            continue
        if prev <= 0 < now:
            return "up", back
        if prev >= 0 > now:
            return "down", back
    return None, None


def inr(value):
    if not _ok(value):
        return "—"
    negative = value < 0
    value = abs(value)
    whole = int(value)
    frac = f"{value - whole:.2f}"[1:]
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{'-' if negative else ''}₹{digits}{frac}"


def _f(value, places=2):
    return "—" if not _ok(value) else f"{value:,.{places}f}"


def _signed(value, places=1, suffix="%"):
    return "—" if not _ok(value) else f"{value:+.{places}f}{suffix}"


def _ago(bars):
    if bars is None:
        return ""
    return "today" if bars == 0 else ("1 session ago" if bars == 1 else f"{bars} sessions ago")


# ---------------------------------------------------------------- descriptions

FAMILY_WHAT = {
    "ma": "A moving average smooths closing prices so the direction of the trend is easier to see. Price above a rising average is the usual definition of an uptrend; the line often acts as support on pullbacks and as resistance in a downtrend.",
    "band": "An envelope around price. The middle line is the trend, the outer lines mark how far price usually stretches from it. Tags of the outer band show strength or weakness; a narrowing band (squeeze) often comes before a bigger move.",
    "stop": "A trailing stop line. It sits below price in an uptrend and flips above price when the trend turns. Swing traders use it as an exit level rather than an entry signal.",
    "bounded": "A bounded momentum oscillator. High readings mean price closed near the top of its recent range (strong, possibly overbought); low readings mean the opposite. In strong trends it can stay extreme for a long time, so turns back out of the extreme zones matter more than the level itself.",
    "zero": "A momentum oscillator that swings around zero. Above zero means the shorter-term average or momentum is ahead of the longer-term one (bullish pressure); crosses of zero or of its signal line mark shifts in momentum.",
    "vol": "A volatility measure. It says how big the daily swings are, not which way price will go. Low volatility compared with its own history often comes before expansion; high volatility means wider stops and smaller positions.",
    "cum": "A cumulative volume line. What matters is its direction compared with price: rising with price confirms the move, falling while price rises is a warning divergence.",
    "flow": "A money-flow oscillator that weighs volume by where price closed in its range. Positive values suggest accumulation (buying pressure), negative values suggest distribution.",
    "volume": "Traded volume compared with its own average. Breakouts and reversals on above-average volume are more trustworthy than those on thin volume.",
    "stat": "A price statistic. It describes where price sits relative to its own recent history.",
    "trend": "A trend-strength or direction tool. It tells you whether the market is trending and in which direction, which decides whether trend-following or range tactics fit better.",
}

WHAT = {
    "sma": "Simple moving average: the plain average of the last N closes.",
    "ema": "Exponential moving average: an average that weights recent closes more, so it turns faster than an SMA.",
    "hma": "Hull moving average: a fast, low-lag average designed to follow turns quickly.",
    "kama": "Kaufman adaptive average: moves fast when price trends cleanly and flattens when price is choppy.",
    "vwma": "Volume-weighted average: closes on heavy volume count more.",
    "vwap": "Volume-weighted average price over the session window: the average price paid, weighted by volume.",
    "ema_ribbon": "EMA ribbon (default 8, 13, 21, 34, 55; each length is adjustable). When the lines are stacked fast-over-slow and fanning out, the trend is healthy; when they tangle, the trend is pausing.",
    "bbands": "Bollinger Bands: a 20-day average with bands two standard deviations above and below.",
    "keltner": "Keltner Channels: an EMA with bands set by Average True Range.",
    "donchian": "Donchian Channel: the highest high and lowest low of the last N sessions. A close through the upper line is the classic breakout.",
    "envelope": "Moving-average envelope: fixed percentage bands around an average.",
    "atr_bands": "ATR bands: the close plus and minus a multiple of Average True Range.",
    "stddev_channel": "Standard-deviation channel around a regression line.",
    "chandelier_long": "Chandelier exit for longs: highest high minus a multiple of ATR.",
    "chandelier_short": "Chandelier exit for shorts: lowest low plus a multiple of ATR.",
    "psar": "Parabolic SAR: dots that trail price and accelerate as the trend extends.",
    "supertrend": "Supertrend: an ATR-based line that sits below price in an uptrend and above it in a downtrend.",
    "pivots": "Floor-trader pivots from the prior session: a central pivot with support (S1, S2) and resistance (R1, R2) levels.",
    "ichimoku": "Ichimoku cloud: conversion and base lines plus a cloud of two leading spans. Price above the cloud is bullish, below it bearish, inside it undecided.",
    "adx": "ADX with +DI and −DI: ADX measures trend strength regardless of direction; +DI over −DI means buyers are in control.",
    "aroon": "Aroon up/down: how recently the highest high and lowest low occurred within the window.",
    "aroon_osc": "Aroon oscillator: Aroon up minus Aroon down.",
    "vortex": "Vortex indicator: VI+ above VI− signals an uptrend.",
    "chop": "Choppiness Index: above 61.8 means sideways chop, below 38.2 means a directional trend.",
    "mass": "Mass Index: a 'reversal bulge' (above 27 then back under 26.5) warns that the current move may turn.",
    "rsi": "Relative Strength Index (14): momentum on a 0–100 scale. 70+ is overbought, 30− oversold; 40–50 often holds as support in uptrends.",
    "stoch": "Stochastic %K/%D: where the close sits in the recent high-low range, 0–100.",
    "stochrsi": "Stochastic RSI: the stochastic formula applied to RSI. Very fast and noisy.",
    "macd": "MACD (12, 26, 9): the gap between a fast and slow EMA, its signal line, and the histogram between them.",
    "macd_hist": "MACD histogram: MACD minus its signal line. Shrinking bars show momentum fading before a cross.",
    "cci": "Commodity Channel Index: deviation of price from its average. Above +100 is strong, below −100 weak.",
    "willr": "Williams %R: like the stochastic, on a 0 to −100 scale. Above −20 overbought, below −80 oversold.",
    "mfi": "Money Flow Index: a volume-weighted RSI. Above 80 overbought, below 20 oversold.",
    "uo": "Ultimate Oscillator: blends three timeframes of buying pressure. Above 70 strong, below 30 weak.",
    "ao": "Awesome Oscillator: 5- versus 34-period average of the bar midpoints.",
    "obv": "On-balance volume: adds volume on up days and subtracts it on down days.",
    "ad": "Accumulation/distribution line: volume weighted by where price closes in its daily range.",
    "cmf": "Chaikin Money Flow (20): buying versus selling pressure, −1 to +1.",
    "atr": "Average True Range (14): the average daily range in rupees, including gaps.",
    "natr": "Normalized ATR: ATR as a percentage of price.",
    "atrp": "ATR percent: ATR as a percentage of price.",
    "hv": "Historical volatility: annualized standard deviation of daily returns.",
    "zscore": "Z-score: how many standard deviations the close is from its 20-day average.",
    "dist_high": "Distance from the 52-week high, in percent.",
    "dist_low": "Distance from the 52-week low, in percent.",
    "drawdown": "Drawdown from the all-time high in the stored history.",
    "highest": "Highest high of the last N sessions: the nearest overhead breakout level.",
    "lowest": "Lowest low of the last N sessions: the nearest support / swing low.",
    "rolling_sharpe": "Rolling Sharpe ratio: return per unit of volatility over the window.",
}

WHAT.update({
    "nt_zigzag": "Directional-change zigzag (@neurotrader888): a swing is confirmed only after price reverses by Sigma %, so the last leg updates as price moves.",
    "nt_trendlines": "Auto trendlines (@neurotrader888): support and resistance lines fitted to the last Lookback closes so that they touch price without crossing it, projected to today.",
    "nt_hawkes": "Hawkes volatility (@neurotrader888): each day's range divided by ATR, fed through a self-exciting decay filter. Its 5th and 95th percentiles mark quiet and explosive regimes.",
    "nt_vsa": "Volume spread analysis (@neurotrader888): how much wider or narrower today's range is than the volume would predict. Large positive values mean effort with a big result; negative values mean heavy volume that did not move price.",
    "nt_cmma": "CMMA difference (@neurotrader888): this stock's close-minus-average, scaled by volatility, minus the same for an equal-weight Nifty 50 proxy. Positive means stronger than the market.",
    "nt_perm_entropy": "Permutation entropy (@neurotrader888): how random the order of recent closes is, from 0 (perfectly ordered trend) to 1 (pure noise).",
    "ut_ewmac": "EWMAC trend forecast (@UnbiasedTradingGoshawk's AHL video): four volatility-scaled EMA crossovers averaged, from −20 (strong downtrend) to +20 (strong uptrend).",
    "ut_rel_return": "Daily return minus the equal-weight Nifty 50 proxy return, in percent (@UnbiasedTradingGoshawk's MIT contrarian video).",
})

FAMILY = {}
for _id in ("sma ema wma dema tema hma kama zlema alma vwma rma mcginley t3 vidya lsma tsf supersmoother frama vwap typical median wclose ha_close").split():
    FAMILY[_id] = "ma"
for _id in ("bbands keltner donchian envelope stddev_channel atr_bands").split():
    FAMILY[_id] = "band"
for _id in ("chandelier_long chandelier_short psar supertrend").split():
    FAMILY[_id] = "stop"
for _id in ("rsi rsi_signal rmi connors stochrsi stoch willr mfi uo bb_percent percent_rank smi cci cmo cmo_smooth psych ifisher").split():
    FAMILY[_id] = "bounded"
for _id in ("macd macd_hist ppo apo ao ao_signal tsi kst trix roc roc_smooth mom coppock fisher rvi dpo linreg_slope derivative elder_ray bop qstick trend_intensity").split():
    FAMILY[_id] = "zero"
for _id in ("atr natr tr hv stddev ulcer chaikin_vol atrp range_ma hv_close bb_width keltner_width").split():
    FAMILY[_id] = "vol"
for _id in ("obv ad nvi pvi vpt williams_ad klinger").split():
    FAMILY[_id] = "cum"
for _id in ("cmf twiggs intraday_intensity force emv emv_signal vol_osc chaikin_osc").split():
    FAMILY[_id] = "flow"
for _id in ("vol_sma vol_ema up_down").split():
    FAMILY[_id] = "volume"
for _id in ("adx aroon aroon_osc vortex chop mass ichimoku ema_ribbon pivots").split():
    FAMILY[_id] = "trend"
WHAT.update({
    "darvas": "Darvas box (Nicolas Darvas): the box top is a high not exceeded for 3 sessions, the bottom a low not undercut for 3 sessions after it. A close above the top is a breakout; a close below the bottom breaks the box.",
    "breakout_trend": "Breakout and trend detector: flags closes through the prior 20-session high or low on at least 1.5× average volume, marks breakouts that fail within 3 sessions, and follows each breakout with an ATR trailing stop to show whether the trend is still alive.",
})
WHAT.update({
    "key_levels": "Key levels plan (method inspired by @TradZoo's daily chart posts): two inner levels just around the close, a long trigger above and a short trigger below, plus outer resistance and support from recent swings. Each side gets three stepped targets for the next session.",
    "pattern_breakout": "Pattern breakout projector (method inspired by @TradZoo's chart posts): fits support and resistance lines over recent bars, names the pattern (wedge, triangle, channel, range), and on a close through resistance gives a buying zone, a stop under support, target 1 at the prior swing high, and target 2 at the pattern height projected from the breakout.",
})
FAMILY.update({"darvas": "pattern", "breakout_trend": "pattern", "key_levels": "pattern", "pattern_breakout": "pattern"})
FAMILY.update({"nt_zigzag": "trend", "nt_trendlines": "band", "nt_hawkes": "vol", "nt_vsa": "zero", "nt_cmma": "zero",
               "nt_perm_entropy": "stat", "ut_ewmac": "zero", "ut_rel_return": "zero"})

# (low, high) zones for bounded oscillators; key picks the main output.
ZONES = {
    "rsi": (30, 70), "rsi_signal": (30, 70), "rmi": (30, 70), "connors": (10, 90), "stochrsi": (20, 80),
    "stoch": (20, 80), "willr": (-80, -20), "mfi": (20, 80), "uo": (30, 70), "bb_percent": (0, 1),
    "percent_rank": (10, 90), "smi": (-40, 40), "cci": (-100, 100), "cmo": (-50, 50), "cmo_smooth": (-50, 50),
    "psych": (25, 75), "ifisher": (-0.5, 0.5),
}


# ---------------------------------------------------------------- context

class Context:
    def __init__(self, frame):
        self.frame = frame
        self.o = _list(frame.o)
        self.h = _list(frame.h)
        self.l = _list(frame.l)
        self.c = _list(frame.c)
        self.v = _list(frame.v)
        self.ts = list(frame.ts)
        self.close = _last(self.c)
        self.prev = _last(self.c, 1)
        self.atr = _list(atr(frame.h, frame.l, frame.c, 14))
        self.atr_now = _last(self.atr)
        self.sma20 = _list(sma(frame.c, 20))
        self.sma50 = _list(sma(frame.c, 50))
        self.sma200 = _list(sma(frame.c, 200))
        self.ema20 = _list(ema(frame.c, 20))
        self.ema50 = _list(ema(frame.c, 50))
        self.rsi = _list(rsi(frame.c, 14))
        line, sig, hist = macd(frame.c, 12, 26, 9)
        self.macd, self.macd_sig, self.macd_hist = _list(line), _list(sig), _list(hist)
        self.hi20 = _list(rolling_max(frame.h, 20))
        self.lo20 = _list(rolling_min(frame.l, 20))
        self.lo10 = _list(rolling_min(frame.l, 10))
        self.hi252 = _list(rolling_max(frame.h, 252))
        self.lo252 = _list(rolling_min(frame.l, 252))
        vol20 = _list(sma(frame.v, 20))
        self.vol_ratio = (self.v[-1] / vol20[-1]) if vol20 and _ok(vol20[-1]) and vol20[-1] else None

    def atr_units(self, distance):
        if distance is None or not self.atr_now:
            return None
        return distance / self.atr_now


# ---------------------------------------------------------------- study readings

def _tone_of(value, low, high):
    if value is None:
        return "neutral"
    if value >= high:
        return "bull-hot"
    if value <= low:
        return "bear-cold"
    return "neutral"


def _read_ma(ctx, name, line):
    level = _last(line)
    if level is None:
        return f"{name} has no value yet for this window.", "neutral"
    gap = _pct(ctx.close, level)
    slope = _pct(level, _last(line, 5))
    rising = slope is not None and slope > 0
    above = ctx.close >= level
    direction = "rising" if rising else "falling"
    atr_gap = ctx.atr_units(abs(ctx.close - level))
    text = (f"Close {inr(ctx.close)} is {abs(gap):.1f}% {'above' if above else 'below'} the {name} at {inr(level)}, "
            f"and the line is {direction} ({_signed(slope)} over 5 sessions). ")
    if above and rising:
        text += ("That is an uptrend reading. The line is the first support area on a pullback")
        text += (f"; price is {atr_gap:.1f} ATR away" if atr_gap is not None else "")
        text += (". More than about 2 ATR above means stretched; buying near the line is usually better value than chasing." if atr_gap and atr_gap > 2 else ". It is close enough that a pullback entry is near.")
        tone = "bull"
    elif above and not rising:
        text += "Price is above a flat or falling line: an early recovery that still needs the line to turn up to confirm."
        tone = "neutral"
    elif not above and not rising:
        text += "That is a downtrend reading. Rallies into the line are where sellers tend to appear; long swing trades usually wait for a close back above it."
        tone = "bear"
    else:
        text += "Price slipped below a still-rising line: a pullback inside an uptrend. A quick reclaim keeps the trend intact; several closes below it weaken it."
        tone = "neutral"
    return text, tone


def _read_band(ctx, name, series):
    up, lo = _last(series.get("upper", [])), _last(series.get("lower", []))
    mid = _last(series.get("mid", [])) if "mid" in series else None
    if up is None or lo is None or up == lo:
        return f"{name} is not ready for this window.", "neutral"
    pos = (ctx.close - lo) / (up - lo) * 100
    width = [(_u - _l) for _u, _l in zip(series["upper"], series["lower"]) if _ok(_u) and _ok(_l)]
    width_rank = _rank(width, width[-1]) if width else None
    text = f"Close sits at {pos:.0f}% of the band (lower {inr(lo)}, upper {inr(up)}{', middle ' + inr(mid) if mid else ''}). "
    if pos >= 100:
        text += "Price closed above the upper band: strong momentum. In trends this often continues; for a new swing entry it is a stretched spot."
        tone = "bull-hot"
    elif pos >= 80:
        text += "Price is riding the upper half, which happens in healthy uptrends."
        tone = "bull"
    elif pos <= 0:
        text += "Price closed below the lower band: heavy selling. Mean-reversion traders watch for a close back inside as a bounce trigger."
        tone = "bear-cold"
    elif pos <= 20:
        text += "Price is pressing the lower band, a weak reading unless it turns back up."
        tone = "bear"
    else:
        text += "Price is in the middle of the band, no stretch either way."
        tone = "neutral"
    if width_rank is not None:
        if width_rank <= 15:
            text += f" The band is narrower than {100 - width_rank:.0f}% of the past year: a squeeze. Squeezes often end in a sharp move; the direction of the break out of the band is the signal."
        elif width_rank >= 85:
            text += " Bands are very wide: volatility is high, so stops need room."
    return text, tone


def _read_stop(ctx, name, line, study_id):
    level = _last(line)
    if level is None:
        return f"{name} is not ready.", "neutral"
    above = ctx.close > level
    units = ctx.atr_units(abs(ctx.close - level))
    dist = f"{inr(abs(ctx.close - level))} ({units:.1f} ATR)" if units is not None else inr(abs(ctx.close - level))
    if study_id == "chandelier_short":
        if above:
            return f"Close is above the short-side chandelier at {inr(level)}: a short trade would already be stopped out, which says sellers have lost control.", "bull"
        return f"Close is {dist} below the short-side chandelier at {inr(level)}: the downtrend trail is intact.", "bear"
    if above:
        return (f"Price is above the {name} at {inr(level)}, {dist} below the close. The line says 'uptrend'. "
                f"For a swing long this is a natural trailing stop: exit on a daily close below {inr(level)}."), "bull"
    return (f"Price is below the {name} at {inr(level)}, {dist} above the close. The line says 'downtrend'. "
            f"A long swing setup would usually wait for a close back above {inr(level)}."), "bear"


def _read_bounded(ctx, study_id, name, series):
    keys = list(series)
    key = keys[0]
    values = series[key]
    now, prev = _last(values), _last(values, 1)
    low, high = ZONES.get(study_id, (20, 80))
    if now is None:
        return f"{name} is not ready.", "neutral"
    turning = None if prev is None else ("rising" if now > prev else "falling")
    text = f"{name} reads {_f(now, 2 if abs(now) < 5 else 1)} ({turning or 'flat'}); the usual zones are {low} and {high}. "
    if now >= high:
        text += ("That is overbought: buyers have pushed price to the top of its range. In an uptrend this is strength, not an automatic sell; "
                 "the warning comes when it falls back below " + str(high) + ".")
        tone = "bull-hot"
    elif now <= low:
        text += ("That is oversold: sellers are stretched. In an uptrend this is often a pullback buying zone; the trigger is a turn back above "
                 + str(low) + ".")
        tone = "bear-cold"
    else:
        mid = (low + high) / 2
        if now > mid:
            text += "It is in the upper half, which leans bullish."
            tone = "bull"
        else:
            text += "It is in the lower half, which leans bearish."
            tone = "bear"
    if len(keys) > 1:
        direction, ago = _cross(values, series[keys[1]], 5)
        if direction:
            text += f" It crossed {'above' if direction == 'up' else 'below'} its signal line {_ago(ago)}."
    rank = _rank(values, now)
    if rank is not None:
        text += f" The reading is higher than {rank:.0f}% of the past year."
    return text, tone


def _read_zero(ctx, study_id, name, series):
    keys = list(series)
    main = series["hist"] if study_id == "macd" else series[keys[0]]
    now = _last(main)
    if now is None:
        return f"{name} is not ready.", "neutral"
    change = _change(main, 3)
    text = f"{name} is {_f(now, 2)} and {'rising' if (change or 0) > 0 else 'falling'} over 3 sessions. "
    if study_id == "macd":
        m, s = _last(series["macd"]), _last(series["signal"])
        direction, ago = _cross(series["macd"], series["signal"], 10)
        text = (f"MACD {_f(m)} vs signal {_f(s)}; histogram {_f(now)} and {'growing' if (change or 0) > 0 else 'shrinking'}. "
                f"MACD is {'above' if (m or 0) > 0 else 'below'} zero, so the 12-day EMA is {'above' if (m or 0) > 0 else 'below'} the 26-day EMA. ")
        if direction:
            text += f"It crossed {'above' if direction == 'up' else 'below'} the signal {_ago(ago)}, a {'bullish' if direction == 'up' else 'bearish'} momentum shift. "
        tone = "bull" if now > 0 else "bear"
        if now > 0 and (change or 0) < 0:
            text += "MACD is above its signal line, but the gap is narrowing: upward momentum is fading, a common sign of a pause or pullback."
            tone = "neutral"
        elif now > 0:
            text += "MACD is above its signal line and the gap is widening: upward momentum is building."
        elif now < 0 and (change or 0) > 0:
            text += "MACD is below its signal line, but the gap is closing: downward momentum is easing and sellers are losing steam."
            tone = "neutral"
        else:
            text += "MACD is below its signal line and the gap is widening: downward momentum is building."
        return text, tone
    if len(keys) > 1 and study_id != "elder_ray":
        direction, ago = _cross(series[keys[0]], series[keys[1]], 10)
        if direction:
            text += f"It crossed {'above' if direction == 'up' else 'below'} its signal {_ago(ago)}. "
    if study_id == "elder_ray":
        bull, bear = _last(series["bull"]), _last(series["bear"])
        text = f"Bull power {_f(bull)}, bear power {_f(bear)}. "
        if (bull or 0) > 0 and (bear or 0) < 0:
            text += "Highs are above the EMA and lows below it: balanced. "
        elif (bear or 0) > 0:
            text += "Even the lows are above the EMA: strong buying. "
        elif (bull or 0) < 0:
            text += "Even the highs are below the EMA: strong selling. "
        return text, "bull" if (bear or -1) > 0 or ((bull or 0) > abs(bear or 0)) else "bear"
    direction, ago = _cross(main, [0.0] * len(main), 10)
    if direction:
        text += f"It crossed {'above' if direction == 'up' else 'below'} zero {_ago(ago)}. "
    if now > 0:
        text += "Above zero means upward momentum." + (" It is fading, so watch for a pause." if (change or 0) < 0 else " It is building.")
        tone = "bull" if (change or 0) >= 0 else "neutral"
    else:
        text += "Below zero means downward momentum." + (" It is improving." if (change or 0) > 0 else " It is still deteriorating.")
        tone = "bear" if (change or 0) <= 0 else "neutral"
    return text, tone


def _read_vol(ctx, study_id, name, series):
    values = series[list(series)[0]]
    now = _last(values)
    rank = _rank(values, now)
    if now is None:
        return f"{name} is not ready.", "neutral"
    text = f"{name} is {_f(now)}"
    if rank is not None:
        text += f", higher than {rank:.0f}% of the past year. "
        if rank <= 20:
            text += "Volatility is compressed. Quiet periods tend to be followed by bigger moves, so this favours breakout setups with tight stops."
        elif rank >= 80:
            text += "Volatility is elevated. Expect wide swings: use wider stops and smaller size, and avoid chasing."
        else:
            text += "Volatility is normal for this stock."
    else:
        text += "."
    if ctx.atr_now:
        text += f" For reference, ATR(14) is {inr(ctx.atr_now)} ({ctx.atr_now / ctx.close * 100:.1f}% of price), a typical one-day move."
    return text, "neutral"


def _read_cum(ctx, name, series):
    values = series[list(series)[0]]
    flow = _change(values, 20)
    price = _pct(ctx.close, _last(ctx.c, 20))
    if flow is None or price is None:
        return f"{name} is not ready.", "neutral"
    up = flow > 0
    text = f"Over 20 sessions {name} is {'rising' if up else 'falling'} while price moved {_signed(price)}. "
    if up and price > 0:
        return text + "Volume confirms the rise: buyers are behind the move.", "bull"
    if not up and price < 0:
        return text + "Volume confirms the fall: selling is real.", "bear"
    if up and price <= 0:
        return text + "Positive divergence: volume is accumulating while price is flat or down. That often comes before a bounce.", "bull"
    return text + "Negative divergence: price is up but volume flow is leaving. Rallies like this are less reliable.", "bear"


def _read_flow(ctx, name, series):
    values = series[list(series)[0]]
    now = _last(values)
    if now is None:
        return f"{name} is not ready.", "neutral"
    change = _change(values, 5)
    text = f"{name} is {_f(now, 3 if abs(now) < 1 else 1)}, {'improving' if (change or 0) > 0 else 'weakening'} over 5 sessions. "
    if now > 0:
        return text + "Positive flow means closes are landing in the upper part of the daily range on volume: accumulation.", "bull"
    return text + "Negative flow means closes are landing low in the range on volume: distribution.", "bear"


def _read_volume(ctx, name, series):
    if ctx.vol_ratio is None:
        return f"{name} is not ready.", "neutral"
    text = f"Today's volume is {ctx.vol_ratio:.1f}× its 20-day average. "
    day = _pct(ctx.close, ctx.prev)
    if ctx.vol_ratio >= 1.5:
        text += f"That is heavy participation on a {_signed(day)} day, so today's move carries weight."
        return text, "bull" if (day or 0) > 0 else "bear"
    if ctx.vol_ratio <= 0.7:
        return text + "Volume is light: today's move has little conviction behind it.", "neutral"
    return text + "Volume is ordinary.", "neutral"


def _read_trend(ctx, study_id, name, series):
    if study_id == "adx":
        adx, plus, minus = _last(series["adx"]), _last(series["plus_di"]), _last(series["minus_di"])
        if adx is None:
            return "ADX is not ready.", "neutral"
        strength = "no real trend (range)" if adx < 20 else "a developing trend" if adx < 25 else "a strong trend" if adx < 40 else "a very strong, possibly late trend"
        rising = (_change(series["adx"], 5) or 0) > 0
        side = "buyers (+DI above −DI)" if (plus or 0) > (minus or 0) else "sellers (−DI above +DI)"
        text = (f"ADX {adx:.1f} ({'rising' if rising else 'falling'}) means {strength}. +DI {_f(plus, 1)}, −DI {_f(minus, 1)}: {side} have the upper hand. ")
        text += "Trend-following swing entries (pullbacks, breakouts) work best when ADX is above 20 and rising." if adx >= 20 else "With ADX under 20, range tactics (buy support, sell resistance) usually fit better than breakouts."
        return text, ("bull" if (plus or 0) > (minus or 0) else "bear") if adx >= 20 else "neutral"
    if study_id in ("aroon", "vortex"):
        a, b = series[list(series)[0]], series[list(series)[1]]
        up, down = _last(a), _last(b)
        label = ("Aroon up", "Aroon down") if study_id == "aroon" else ("VI+", "VI−")
        text = f"{label[0]} {_f(up, 1)} vs {label[1]} {_f(down, 1)}. "
        direction, ago = _cross(a, b, 10)
        if direction:
            text += f"They crossed {_ago(ago)} in favour of the {'up' if direction == 'up' else 'down'} side. "
        return text + ("The up side leads: new highs are more recent than new lows." if (up or 0) > (down or 0) else "The down side leads."), "bull" if (up or 0) > (down or 0) else "bear"
    if study_id == "aroon_osc":
        now = _last(series["osc"])
        return f"Aroon oscillator {_f(now, 0)} (−100 to +100). {'Positive: uptrend bias.' if (now or 0) > 0 else 'Negative: downtrend bias.'}", "bull" if (now or 0) > 0 else "bear"
    if study_id == "chop":
        now = _last(series["chop"])
        if now is None:
            return "Choppiness is not ready.", "neutral"
        if now > 61.8:
            return f"Choppiness {now:.1f}: sideways and noisy. Breakout and trend entries fail more often here; fade the edges of the range instead.", "neutral"
        if now < 38.2:
            return f"Choppiness {now:.1f}: price is moving in a clean direction. Trend-following entries fit.", "neutral"
        return f"Choppiness {now:.1f}: between trending and choppy.", "neutral"
    if study_id == "mass":
        values = series["mass"]
        now = _last(values)
        bulge = any((x or 0) > 27 for x in values[-25:] if _ok(x))
        text = f"Mass Index {_f(now, 1)}. "
        text += "A reversal bulge (above 27) appeared in the last 25 sessions: the current swing may be ending." if bulge else "No reversal bulge recently."
        return text, "neutral"
    if study_id == "ichimoku":
        span_a, span_b = _last(series["span_a"]), _last(series["span_b"])
        tenkan, kijun = _last(series["tenkan"]), _last(series["kijun"])
        if span_a is None or span_b is None:
            return "Ichimoku cloud is not ready.", "neutral"
        top, bottom = max(span_a, span_b), min(span_a, span_b)
        where = "above the cloud (bullish)" if ctx.close > top else "below the cloud (bearish)" if ctx.close < bottom else "inside the cloud (undecided)"
        text = f"Price is {where}; cloud spans {inr(bottom)}–{inr(top)}. Conversion line {inr(tenkan)} is {'above' if (tenkan or 0) > (kijun or 0) else 'below'} the base line {inr(kijun)}. "
        text += f"The cloud top at {inr(top)} is support on pullbacks." if ctx.close > top else f"The cloud bottom at {inr(bottom)} is resistance on rallies." if ctx.close < bottom else "Wait for a close outside the cloud for a direction."
        return text, "bull" if ctx.close > top else "bear" if ctx.close < bottom else "neutral"
    if study_id == "ema_ribbon":
        last = [_last(values) for values in series.values()]
        if any(x is None for x in last):
            return "EMA ribbon is not ready.", "neutral"
        if all(a > b for a, b in zip(last, last[1:])):
            return f"All five EMAs are stacked fast-over-slow and price is {'above' if ctx.close > last[0] else 'below'} the fastest: a clean uptrend structure. The middle EMAs ({inr(last[2])}/{inr(last[3])}) are the usual pullback zone.", "bull"
        if all(a < b for a, b in zip(last, last[1:])):
            return "All five EMAs are stacked slow-over-fast: a clean downtrend structure. Long swings usually wait until the ribbon untangles and flips.", "bear"
        return "The EMAs are tangled: the trend is pausing or turning. Wait for them to fan out again.", "neutral"
    if study_id == "nt_zigzag":
        values = series["zigzag"]
        now, before = _last(values), _last(values, 3)
        if now is None or before is None:
            return "No confirmed swing yet at this Sigma %.", "neutral"
        up = now >= before
        return (f"The zigzag's current leg is {'rising' if up else 'falling'}. In the directional-change view the trend is {'up' if up else 'down'} "
                f"until price reverses by Sigma % from the leg's extreme; the long rule holds only during up-legs."), "bull" if up else "bear"
    if study_id == "pivots":
        levels = {k.upper(): _last(series[k]) for k in ("s2", "s1", "pp", "r1", "r2")}
        below = [(k, v) for k, v in levels.items() if v is not None and v <= ctx.close]
        above = [(k, v) for k, v in levels.items() if v is not None and v > ctx.close]
        sup = max(below, key=lambda kv: kv[1]) if below else None
        res = min(above, key=lambda kv: kv[1]) if above else None
        text = "Floor pivots from the last session: " + ", ".join(f"{k} {inr(v)}" for k, v in levels.items() if v is not None) + ". "
        if sup:
            text += f"Nearest support is {sup[0]} at {inr(sup[1])}. "
        if res:
            text += f"Nearest resistance is {res[0]} at {inr(res[1])}."
        return text, "neutral"
    return f"{name} is on the chart.", "neutral"


def _read_stat(ctx, study_id, name, series):
    values = series[list(series)[0]]
    now = _last(values)
    if study_id in ("highest", "lowest"):
        gap = _pct(ctx.close, now)
        if study_id == "highest":
            return (f"The 20-session high is {inr(now)}, {abs(gap or 0):.1f}% above the close. A daily close above it would be a fresh breakout; until then it is overhead resistance.", "neutral")
        return (f"The 20-session low is {inr(now)}, {abs(gap or 0):.1f}% below the close. It is the nearest swing-low support and a logical stop area for a long.", "neutral")
    if study_id == "dist_high":
        return f"Price is {_f(now, 1)}% from its 52-week high. {'Within 5% of the high: leaders often break out from here.' if (now or -99) > -5 else 'Well off the high: there is overhead supply from earlier buyers.'}", "bull" if (now or -99) > -5 else "neutral"
    if study_id == "dist_low":
        return f"Price is {_f(now, 1)}% above its 52-week low.", "neutral"
    if study_id == "zscore":
        tone = "bull-hot" if (now or 0) > 2 else "bear-cold" if (now or 0) < -2 else "neutral"
        return f"Z-score {_f(now)}: the close is {abs(now or 0):.1f} standard deviations {'above' if (now or 0) > 0 else 'below'} its 20-day average. Beyond ±2 is statistically stretched and tends to revert.", tone
    if study_id == "drawdown":
        return f"Price is {_f(now, 1)}% below its highest close in the stored history.", "neutral"
    if study_id == "rolling_sharpe":
        return f"Rolling Sharpe {_f(now)}. Above 1 means the recent trend has been strong relative to its noise; below 0 means the recent period lost money.", "bull" if (now or 0) > 1 else "bear" if (now or 0) < 0 else "neutral"
    if now is None:
        return f"{name} is not ready.", "neutral"
    rank = _rank(values, now)
    text = f"{name} is {_f(now)}"
    if rank is not None:
        text += f", higher than {rank:.0f}% of the past year."
    return text, "neutral"


def _read_pattern(ctx, study_id, params):
    from top.patterns import breakout_trend, darvas_boxes

    if study_id == "key_levels":
        from top.levels import describe_plan, key_levels, level_plan

        plan = level_plan(key_levels(ctx.frame, params), ctx.close)
        if not plan:
            return "Not enough history for key levels yet.", "neutral"
        nxt = "the next session"
        text = f"Plan for {nxt} (from the {ctx.ts[-1]} close): " + describe_plan(plan, ctx.close)
        room_up = (plan["r1"] / ctx.close - 1) * 100
        room_dn = (1 - plan["s1"] / ctx.close) * 100
        text += f" The long trigger is {room_up:.1f}% above the close and the short trigger {room_dn:.1f}% below."
        tone = "bull" if ctx.close > plan["r1"] else "bear" if ctx.close < plan["s1"] else "neutral"
        return text, tone
    if study_id == "pattern_breakout":
        from top.levels import describe_pattern

        return describe_pattern(ctx.frame, params)

    if study_id == "darvas":
        top, bot, events = darvas_boxes(ctx.h, ctx.l, ctx.c, int(params.get("confirm", 3)))
        t, b = _last(top), _last(bot)
        last = events[-1] if events else None
        text = ""
        if t is not None and b is not None:
            pos = (ctx.close - b) / (t - b) * 100 if t > b else 50
            text += (f"An active Darvas box runs from {inr(b)} to {inr(t)}; the close sits at {pos:.0f}% of it. "
                     f"A close above {inr(t)} is the Darvas buy signal; a close below {inr(b)} breaks the box. ")
            tone = "bull" if pos > 70 else "neutral"
        else:
            text += "No box is active right now: price is still setting a new top or bottom, or has just left a box. "
            tone = "neutral"
        if last:
            i, kind, bt, bb = last
            text += f"The last event was a {'breakout above ' + inr(bt) if kind == 'breakout' else 'break below ' + inr(bb)} on {ctx.ts[i]} ({_ago(len(ctx.c) - 1 - i)}). "
            if t is None and kind == "breakout":
                tone = "bull"
            elif t is None:
                tone = "bear"
        breakouts = [e for e in events if e[1] == "breakout"]
        if breakouts:
            wins = sum(1 for i, *_ in breakouts if i + 10 < len(ctx.c) and ctx.c[i + 10] > ctx.c[i])
            done = sum(1 for i, *_ in breakouts if i + 10 < len(ctx.c))
            if done >= 3:
                text += f"On this stock {done} past Darvas breakouts were higher 10 sessions later {100 * wins / done:.0f}% of the time."
        return text, tone
    out = breakout_trend(ctx.frame, params)
    hi, lo, trail = _last(out["upper"]), _last(out["lower"]), _last(out["trail"])
    events = out["events"]
    names = {"breakout": "volume breakout above", "breakdown": "volume breakdown below", "failed": "failed breakout back under", "trend_end": "trend exit at the trailing stop"}
    text = ""
    if out["state"][-1] == 1 and trail is not None:
        start = max(i for i, k, _ in events if k == "breakout")
        gain = _pct(ctx.close, ctx.c[start])
        text += (f"In a breakout uptrend since {ctx.ts[start]} ({_ago(len(ctx.c) - 1 - start)}), {_signed(gain)} since the breakout. "
                 f"The trailing stop is {inr(trail)}; the trend is considered over on a close below it. ")
        tone = "bull"
    else:
        width = (hi - lo) if hi is not None and lo is not None else None
        pos = (ctx.close - lo) / width * 100 if width else None
        text += (f"No active breakout trend. The prior 20-session range is {inr(lo)}–{inr(hi)}"
                 + (f" and the close sits at {pos:.0f}% of it" if pos is not None else "") + ". "
                 f"A close above {inr(hi)} on heavy volume would trigger a breakout; below {inr(lo)}, a breakdown. ")
        tone = "neutral"
    if events:
        i, kind, level = events[-1]
        text += f"Last signal: {names[kind]} {inr(level)} on {ctx.ts[i]} ({_ago(len(ctx.c) - 1 - i)}). "
        if kind == "breakdown" and out["state"][-1] != 1:
            tone = "bear"
    ups = [i for i, k, _ in events if k == "breakout"]
    fails = sum(1 for _, k, _ in events if k == "failed")
    if len(ups) >= 3:
        text += f"On this stock {len(ups)} volume breakouts were detected, {fails} failed within 3 sessions."
    return text, tone


def read_study(ctx, study_id, params):
    spec = next((item for item in indicator_catalog() if item["id"] == study_id), None)
    if spec is None:
        return None
    name = spec["name"]
    if study_id in HARMONIC_IDS:
        return read_harmonic(ctx, study_id, params, name)
    result = compute_study(study_id, ctx.frame, params or {})
    series = {key: _list(values) for key, values in result["series"].items()}
    family = FAMILY.get(study_id, "stat")
    if family == "ma":
        text, tone = _read_ma(ctx, name, series[list(series)[0]])
    elif family == "band":
        text, tone = _read_band(ctx, name, series)
    elif family == "stop":
        text, tone = _read_stop(ctx, name, series[list(series)[0]], study_id)
    elif family == "bounded":
        text, tone = _read_bounded(ctx, study_id, name, series)
    elif family == "zero":
        text, tone = _read_zero(ctx, study_id, name, series)
    elif family == "vol":
        text, tone = _read_vol(ctx, study_id, name, series)
    elif family == "cum":
        text, tone = _read_cum(ctx, name, series)
    elif family == "flow":
        text, tone = _read_flow(ctx, name, series)
    elif family == "volume":
        text, tone = _read_volume(ctx, name, series)
    elif family == "trend":
        text, tone = _read_trend(ctx, study_id, name, series)
    elif family == "pattern":
        text, tone = _read_pattern(ctx, study_id, params or {})
    else:
        text, tone = _read_stat(ctx, study_id, name, series)
    if "length" in (params or {}) and FAMILY.get(study_id) in ("ma", "band", "bounded", "vol"):
        name = f"{name} {params['length']}"
    return {
        "kind": "study",
        "id": study_id,
        "title": name,
        "section": spec["section"],
        "what": WHAT.get(study_id, FAMILY_WHAT.get(family, FAMILY_WHAT["stat"])),
        "now": text,
        "tone": tone,
    }


# ---------------------------------------------------------------- harmonics

def _harmonic_events(ctx, params, only):
    swing = float((params or {}).get("swing", harmonics.DEFAULT_SWING))
    tol = float((params or {}).get("tolerance", harmonics.DEFAULT_TOLERANCE))
    events = harmonics.detect(ctx.frame.h, ctx.frame.l, ctx.frame.ts, swing, tol, only)
    events.sort(key=lambda event: event["index"])
    return events, swing, tol


def _harmonic_history(ctx, events, side, horizon=10):
    wins, rets = 0, []
    for event in events:
        if event["side"] != side:
            continue
        i = event["index"]
        if i + horizon >= len(ctx.c) or not _ok(ctx.c[i]):
            continue
        ret = (ctx.c[i + horizon] / ctx.c[i] - 1) * 100
        if side == "bear":
            ret = -ret
        rets.append(ret)
        wins += ret > 0
    if not rets:
        return None
    rets.sort()
    return {"n": len(rets), "hit": 100 * wins / len(rets), "median": rets[len(rets) // 2]}


def read_harmonic(ctx, study_id, params, name):
    only = None if study_id == "carney" else study_id.replace("harm_", "")
    events, swing, tol = _harmonic_events(ctx, params, only)
    what = ("Scott Carney harmonic patterns: five swing points X-A-B-C-D whose legs match Fibonacci ratios. D is the potential reversal zone (PRZ). "
            "A bullish pattern completes at a low and expects a bounce; a bearish one completes at a high and expects a drop. "
            f"Detection uses a {swing:g}% zigzag and ±{tol:g} ratio tolerance.")
    if not events:
        return {"kind": "harmonic", "id": study_id, "title": name, "section": "Harmonics", "what": what,
                "now": "No completed pattern at these settings. Lower Swing % to see smaller patterns or raise Tolerance for looser ratio matches.", "tone": "neutral"}
    last = events[-1]
    i = last["index"]
    bars = len(ctx.c) - 1 - i
    bull = last["side"] == "bull"
    pts = last["points"]
    d_px = last["prz"]
    c_px = pts[-2][1]
    move = _pct(ctx.close, d_px)
    t1 = d_px + 0.382 * (c_px - d_px)
    t2 = d_px + 0.618 * (c_px - d_px)
    stop = d_px - ctx.atr_now if bull else d_px + ctx.atr_now
    text = (f"Latest: {'bullish' if bull else 'bearish'} {', '.join(last['names'])} completed at D = {inr(d_px)} on {last['time']} ({_ago(bars)}). ")
    ratios = last.get("ratios") or {}
    if ratios:
        text += "Measured ratios: " + ", ".join(f"{k.upper()} {v}" for k, v in ratios.items()) + ". "
    hit_stop = (ctx.close < stop) if bull else (ctx.close > stop)
    hit_t1 = (ctx.close >= t1) if bull else (ctx.close <= t1)
    hit_t2 = (ctx.close >= t2) if bull else (ctx.close <= t2)
    if hit_stop:
        status = "failed: price has moved more than 1 ATR beyond D, so the reversal did not hold."
        tone = "bear" if bull else "bull"
    elif hit_t2:
        status = "played out: price has already reached the 0.618 CD retracement target."
        tone = "bull" if bull else "bear"
    elif hit_t1:
        status = "working: price reached the first target (0.382 of CD). Carney-style management moves the stop to break-even here."
        tone = "bull" if bull else "bear"
    elif bars <= 10:
        status = "fresh and still in play."
        tone = "bull" if bull else "bear"
    else:
        status = "stale: it is old and has not reached its targets."
        tone = "neutral"
    text += (f"Close is {_signed(move)} from D. Status: {status} "
             f"Reaction targets are 0.382 and 0.618 of the CD leg: {inr(t1)} and {inr(t2)}. "
             f"A common invalidation is 1 ATR beyond D: {inr(stop)}. ")
    history = _harmonic_history(ctx, events, last["side"])
    if history and history["n"] >= 3:
        text += (f"On this stock, {history['n']} past {'bullish' if bull else 'bearish'} completions at these settings moved in the expected direction over the next 10 sessions "
                 f"{history['hit']:.0f}% of the time (median {_signed(history['median'])}).")
    bulls = sum(1 for e in events if e["side"] == "bull")
    text += f" In total {len(events)} patterns were found in the stored history ({bulls} bullish, {len(events) - bulls} bearish)."
    return {"kind": "harmonic", "id": study_id, "title": name, "section": "Harmonics", "what": what, "now": text, "tone": tone,
            "pattern": {"side": last["side"], "d": d_px, "t1": round(t1, 2), "t2": round(t2, 2), "stop": round(stop, 2), "bars": bars, "fresh": bars <= 10 and not hit_stop and not hit_t2}}


# ---------------------------------------------------------------- strategy

def read_strategy(ctx, strategy_id, params, capital, cost_bps):
    spec = next((item for item in strategy_catalog() if item["id"] == strategy_id), None)
    if spec is None:
        return None
    position = _list(signal(strategy_id, ctx.frame, params or {}))
    now = _last(position)
    change = None
    for back in range(1, len(position)):
        a, b = position[-back], position[-back - 1]
        if _ok(a) and _ok(b) and a != b:
            change = back - 1
            break
    result = run_backtest(ctx.frame.ts, ctx.frame.o, ctx.frame.h, ctx.frame.l, ctx.frame.c, signal(strategy_id, ctx.frame, params or {}), capital=capital, cost_bps=cost_bps)
    m = result["metrics"]
    long_now = now == 1
    text = f"Today the rule is {'LONG' if long_now else 'FLAT'}"
    if change is not None:
        text += f"; it switched {'in' if long_now else 'out'} {_ago(change)} ({ctx.ts[len(ctx.ts) - 1 - change]})."
    else:
        text += "."
    text += (f" Over the stored history it made {_signed(m['total_return_pct'])} vs buy-and-hold {_signed(m['buy_hold_pct'])}, with {m['trades']} trades, "
             f"win rate {('—' if m['win_rate_pct'] is None else str(m['win_rate_pct']) + '%')} and max drawdown {_signed(m['max_drawdown_pct'])}. ")
    if not m["trades"]:
        text = (f"Today the rule is FLAT. It has not triggered on this stock in the stored history at these settings, so there is nothing to judge yet. "
                "Loosen its settings, or use Backtest 50 to find stocks where it does fire.")
    elif m["total_return_pct"] is not None and m["buy_hold_pct"] is not None:
        if m["total_return_pct"] > m["buy_hold_pct"]:
            text += "It beat simply holding the stock here, which is uncommon and worth a closer look."
        else:
            text += "It lagged simply holding the stock; on this name the rule is better used as a filter or exit than as the whole plan."
    if spec.get("creator"):
        text += f" Adapted from {spec['creator']} (confidence {spec.get('confidence', '—')})."
        if spec.get("notes"):
            text += " " + spec["notes"]
    return {"kind": "strategy", "id": strategy_id, "title": spec["name"], "section": spec["section"], "what": spec["blurb"],
            "now": text, "tone": "bull" if long_now else "neutral"}


# ---------------------------------------------------------------- technical rating

def technical_rating(ctx):
    """Vote count in the style of TradingView's public technical-ratings method (MAs + oscillators)."""
    f = ctx.frame
    ma_votes = []
    for n in (10, 20, 30, 50, 100, 200):
        for fn in (sma, ema):
            level = _last(_list(fn(f.c, n)))
            if level is not None:
                ma_votes.append(1 if ctx.close > level else -1)
    kijun = _last(_list(ichimoku(f.h, f.l, f.c)[1]))
    if kijun is not None:
        ma_votes.append(1 if ctx.close > kijun else -1)
    h9 = _last(_list(hma(f.c, 9)))
    if h9 is not None:
        ma_votes.append(1 if ctx.close > h9 else -1)

    osc = []

    def series(study_id, key=None, params=None):
        out = compute_study(study_id, f, params or {})["series"]
        return _list(out[key or list(out)[0]])

    r = ctx.rsi
    if _last(r) is not None and _last(r, 1) is not None:
        osc.append(1 if _last(r) < 30 and _last(r) > _last(r, 1) else -1 if _last(r) > 70 and _last(r) < _last(r, 1) else 0)
    k, d = series("stoch", "k"), series("stoch", "d")
    if _last(k) is not None and _last(d) is not None:
        osc.append(1 if _last(k) < 20 and _last(k) > _last(d) else -1 if _last(k) > 80 and _last(k) < _last(d) else 0)
    cci = series("cci")
    if _last(cci) is not None and _last(cci, 1) is not None:
        osc.append(1 if _last(cci) < -100 and _last(cci) > _last(cci, 1) else -1 if _last(cci) > 100 and _last(cci) < _last(cci, 1) else 0)
    adx_s, plus, minus = series("adx", "adx"), series("adx", "plus_di"), series("adx", "minus_di")
    if _last(adx_s) is not None and _last(adx_s, 1) is not None:
        rising = _last(adx_s) > _last(adx_s, 1)
        if _last(adx_s) > 20 and rising:
            osc.append(1 if _last(plus) > _last(minus) else -1)
        else:
            osc.append(0)
    ao = series("ao")
    if _last(ao) is not None and _last(ao, 1) is not None:
        osc.append(1 if _last(ao) > 0 and _last(ao) > _last(ao, 1) else -1 if _last(ao) < 0 and _last(ao) < _last(ao, 1) else 0)
    mom = series("mom")
    if _last(mom) is not None and _last(mom, 1) is not None:
        osc.append(1 if _last(mom) > _last(mom, 1) else -1)
    if _last(ctx.macd) is not None and _last(ctx.macd_sig) is not None:
        osc.append(1 if _last(ctx.macd) > _last(ctx.macd_sig) else -1)
    wr = series("willr")
    if _last(wr) is not None and _last(wr, 1) is not None:
        osc.append(1 if _last(wr) < -80 and _last(wr) > _last(wr, 1) else -1 if _last(wr) > -20 and _last(wr) < _last(wr, 1) else 0)
    uo = series("uo")
    if _last(uo) is not None:
        osc.append(1 if _last(uo) > 70 else -1 if _last(uo) < 30 else 0)

    def label(score):
        if score is None:
            return "Neutral"
        if score > 0.5:
            return "Strong buy"
        if score > 0.1:
            return "Buy"
        if score < -0.5:
            return "Strong sell"
        if score < -0.1:
            return "Sell"
        return "Neutral"

    ma_score = sum(ma_votes) / len(ma_votes) if ma_votes else None
    osc_score = sum(osc) / len(osc) if osc else None
    parts = [s for s in (ma_score, osc_score) if s is not None]
    overall = sum(parts) / len(parts) if parts else None
    return {
        "ma": {"score": ma_score, "label": label(ma_score), "buy": ma_votes.count(1), "sell": ma_votes.count(-1), "neutral": 0},
        "osc": {"score": osc_score, "label": label(osc_score), "buy": osc.count(1), "sell": osc.count(-1), "neutral": osc.count(0)},
        "overall": {"score": overall, "label": label(overall)},
    }


# ---------------------------------------------------------------- swing plan

def _state_at(ctx, i):
    c, s50, s200, r = ctx.c[i], ctx.sma50[i], ctx.sma200[i], ctx.rsi[i]
    if not all(_ok(x) for x in (c, s50, s200, r)):
        return None
    return (c > s50, s50 > s200, r)


def _odds(ctx, stop_atr, target_r, setup_filter, match_rsi=True, horizon=15):
    """Replay the same plan on this stock's own history.

    For every past bar where the same condition held: enter at that close, stop
    stop_atr ATRs below, target target_r times the risk above. A bar that touches
    both counts as a loss. Bars still open after `horizon` sessions are closed at
    the close.
    """
    now_state = _state_at(ctx, len(ctx.c) - 1)
    if now_state is None:
        return None
    outcomes = []
    last_used = -99
    for i in range(210, len(ctx.c) - 2):
        if i - last_used < 5:
            continue
        state = _state_at(ctx, i)
        if state is None or state[0] != now_state[0] or state[1] != now_state[1]:
            continue
        if match_rsi and abs(state[2] - now_state[2]) > 8:
            continue
        if not setup_filter(i):
            continue
        a = ctx.atr[i]
        if not _ok(a) or a <= 0:
            continue
        entry = ctx.c[i]
        stop = entry - stop_atr * a
        target = entry + target_r * stop_atr * a
        result = None
        for j in range(i + 1, min(i + 1 + horizon, len(ctx.c))):
            if ctx.l[j] <= stop:
                result = -1.0
                break
            if ctx.h[j] >= target:
                result = target_r
                break
        if result is None:
            end = min(i + horizon, len(ctx.c) - 1)
            if end <= i:
                continue
            result = (ctx.c[end] - entry) / (stop_atr * a)
        outcomes.append(result)
        last_used = i
    if len(outcomes) < 8:
        return {"n": len(outcomes)}
    wins = sum(1 for x in outcomes if x > 0)
    return {"n": len(outcomes), "win": 100 * wins / len(outcomes), "expectancy": sum(outcomes) / len(outcomes)}


def _base_rate(ctx, horizon=10):
    """Forward returns after past sessions in the same trend state and a similar RSI."""
    now_state = _state_at(ctx, len(ctx.c) - 1)
    if now_state is None:
        return None
    rets = []
    for i in range(200, len(ctx.c) - horizon):
        state = _state_at(ctx, i)
        if state is None or state[:2] != now_state[:2] or abs(state[2] - now_state[2]) > 5:
            continue
        rets.append((ctx.c[i + horizon] / ctx.c[i] - 1) * 100)
    if len(rets) < 15:
        return {"n": len(rets), "horizon": horizon}
    rets.sort()
    q = lambda f: rets[min(len(rets) - 1, int(f * len(rets)))]
    return {"n": len(rets), "horizon": horizon, "up": 100 * sum(1 for r in rets if r > 0) / len(rets),
            "median": q(0.5), "p25": q(0.25), "p75": q(0.75)}


def swing_plan(ctx, rating, harmonic, capital, risk_pct=1.0):
    close, a = ctx.close, ctx.atr_now
    s50, s200, e20 = _last(ctx.sma50), _last(ctx.sma200), _last(ctx.ema20)
    r = _last(ctx.rsi)
    hist, hist_prev = _last(ctx.macd_hist), _last(ctx.macd_hist, 1)
    hi20_prev, lo10 = _last(ctx.hi20, 1), _last(ctx.lo10)
    if None in (close, a, s50, e20, r):
        return {"bias": "Neutral", "headline": "Not enough history for a swing read.", "steps": [], "levels": []}

    score = 0
    reasons = []
    if close > s50:
        score += 1; reasons.append("close is above the 50-day average")
    else:
        score -= 1; reasons.append("close is below the 50-day average")
    if s200 is not None:
        if s50 > s200:
            score += 1; reasons.append("the 50-day is above the 200-day (long-term uptrend)")
        else:
            score -= 1; reasons.append("the 50-day is below the 200-day (long-term downtrend)")
    if r >= 55:
        score += 1; reasons.append(f"RSI {r:.0f} shows positive momentum")
    elif r <= 45:
        score -= 1; reasons.append(f"RSI {r:.0f} shows weak momentum")
    if hist is not None and hist_prev is not None:
        if hist > 0 and hist >= hist_prev:
            score += 1; reasons.append("MACD histogram is positive and growing")
        elif hist < 0 and hist <= hist_prev:
            score -= 1; reasons.append("MACD histogram is negative and falling")
    tr = rating["overall"]["score"]
    if tr is not None:
        score += 1 if tr > 0.1 else -1 if tr < -0.1 else 0
    if harmonic and harmonic.get("fresh"):
        score += 1 if harmonic["side"] == "bull" else -1
        reasons.append(f"a fresh {'bullish' if harmonic['side'] == 'bull' else 'bearish'} harmonic completed {harmonic['bars']} sessions ago")

    bias = "Bullish" if score >= 2 else "Bearish" if score <= -2 else "Neutral"
    stretch = (close - e20) / a
    near_high = hi20_prev is not None and close >= hi20_prev - 0.5 * a

    steps, levels = [], []
    filter_fn = lambda i: True
    match_rsi = True
    if harmonic and harmonic.get("fresh") and harmonic["side"] == "bull" and bias != "Bearish":
        setup = "Harmonic reversal long"
        entry = max(close, ctx.h[-1])
        stop = harmonic["stop"]
        trigger = f"a daily close above {inr(ctx.h[-1])} (today's high) to confirm the bounce from D = {inr(harmonic['d'])}"
        t1, t2 = harmonic["t1"], harmonic["t2"]
        filter_fn = lambda i: True
    elif bias == "Bullish" and stretch > 2.0:
        setup = "Uptrend, but extended — wait"
        entry = e20 + 0.25 * a
        stop = min(lo10 or entry - 1.5 * a, entry - 1.0 * a)
        trigger = f"a pullback toward the 20-day EMA around {inr(e20)}, then a close back above the prior day's high. Price is {stretch:.1f} ATR above the EMA, so buying here has poor risk/reward"
        t1, t2 = None, None
        filter_fn = lambda i: _ok(ctx.ema20[i]) and _ok(ctx.atr[i]) and abs(ctx.c[i] - ctx.ema20[i]) / ctx.atr[i] <= 0.5
        match_rsi = False
    elif bias == "Bullish" and near_high:
        setup = "Breakout long"
        entry = (hi20_prev or close) + 0.1 * a
        stop = entry - 1.5 * a
        trigger = f"a daily close above the 20-session high of {inr(hi20_prev)}, ideally on volume above its 20-day average"
        t1, t2 = None, None
        filter_fn = lambda i: _ok(ctx.hi20[i - 1]) and _ok(ctx.atr[i]) and ctx.c[i] >= ctx.hi20[i - 1] - 0.5 * ctx.atr[i]
    elif bias == "Bullish":
        setup = "Pullback long in an uptrend"
        entry = max(close, ctx.h[-1]) + 0.05 * a
        swing_low = lo10 if lo10 is not None else close - 1.5 * a
        stop = min(swing_low - 0.2 * a, entry - 1.0 * a)
        trigger = f"a daily close above today's high of {inr(ctx.h[-1])}, showing buyers stepping back in near the 20-day EMA ({inr(e20)})"
        t1, t2 = None, None
        filter_fn = lambda i: _ok(ctx.ema20[i]) and _ok(ctx.atr[i]) and abs(ctx.c[i] - ctx.ema20[i]) / ctx.atr[i] <= 2.0
    elif bias == "Bearish":
        setup = "No long setup — downtrend"
        entry, stop, t1, t2 = None, None, None, None
        flip = _last(ctx.ema50)
        trigger = (f"stand aside. A long swing needs the trend to repair first: a close back above the 50-day EMA ({inr(flip)}) with RSI back over 50. "
                   "NSE cash-market shorts must be squared off the same day, so a bearish swing is expressed with F&O or simply by staying out")
        filter_fn = lambda i: True
    else:
        setup = "Range — buy support, sell resistance"
        lo20, hi20 = _last(ctx.lo20), _last(ctx.hi20)
        entry = (lo20 or close) + 0.3 * a
        stop = (lo20 or close) - 0.7 * a
        trigger = f"price near the bottom of the 20-session range ({inr(lo20)}) with RSI turning up from below 40; the top of the range ({inr(hi20)}) is the exit"
        t1, t2 = hi20, None
        filter_fn = lambda i: _ok(ctx.lo20[i]) and _ok(ctx.atr[i]) and ctx.c[i] <= ctx.lo20[i] + 1.0 * ctx.atr[i]
        match_rsi = False

    plan = {"bias": bias, "score": score, "setup": setup, "reasons": reasons, "trigger": trigger}
    if entry is not None and stop is not None and entry > stop:
        risk = entry - stop
        if t1 is None:
            t1 = entry + 1.5 * risk
        if t2 is None or t2 <= t1:
            t2 = max(entry + 3.0 * risk, t1 + risk)
        hi52 = _last(ctx.hi252)
        shares = int((capital * risk_pct / 100) // risk) if risk > 0 else 0
        shares = min(shares, int(capital // entry)) if entry else shares
        stop_atr = risk / a
        odds = _odds(ctx, stop_atr, (t1 - entry) / risk, filter_fn, match_rsi)
        plan.update({
            "entry": round(entry, 2), "stop": round(stop, 2), "t1": round(t1, 2), "t2": round(t2, 2),
            "risk": round(risk, 2), "risk_pct": round(risk / entry * 100, 2), "r1": round((t1 - entry) / risk, 2), "r2": round((t2 - entry) / risk, 2),
            "shares": shares, "exposure": round(shares * entry, 2), "capital_risk": round(shares * risk, 2), "odds": odds,
            "resistance": round(hi52, 2) if hi52 and hi52 > entry and hi52 < t2 else None,
        })
        steps = [
            f"Wait for {trigger}.",
            f"Entry around {inr(entry)}. Initial stop {inr(stop)} — {inr(risk)} or {risk / entry * 100:.1f}% below entry ({stop_atr:.1f} ATR).",
            f"Target 1 {inr(t1)} ({plan['r1']:.1f}R): book part of the position and move the stop to entry. Target 2 {inr(t2)} ({plan['r2']:.1f}R): trail the rest under the 20-day EMA or Supertrend.",
            f"Size: risking {risk_pct:g}% of {inr(capital)} = {inr(capital * risk_pct / 100)} → about {shares:,} shares ({inr(shares * entry)} exposure).",
            "Time stop: if neither target nor stop is hit within 10–15 sessions, exit; swing trades that do not move tend to fail.",
        ]
        if plan["resistance"]:
            steps.append(f"The 52-week high at {inr(plan['resistance'])} sits between entry and target 2; expect selling there.")
    else:
        steps = [trigger[0].upper() + trigger[1:] + "."]
    plan["steps"] = steps
    plan["base"] = _base_rate(ctx)
    return plan


# ---------------------------------------------------------------- entry point

def explain(frame, symbol, studies, strategy, capital=1_000_000, cost_bps=5.0, focus=None):
    ctx = Context(frame)
    rating = technical_rating(ctx)
    items = []
    harmonic_item = None
    for spec in studies or []:
        try:
            item = read_study(ctx, spec.get("id"), spec.get("params") or {})
        except Exception as exc:  # noqa: BLE001 - one bad study should not blank the pane
            item = {"kind": "study", "id": spec.get("id"), "title": spec.get("id"), "section": "", "what": "", "now": f"Could not read this study: {exc}", "tone": "neutral"}
        if item:
            items.append(item)
            if item["kind"] == "harmonic" and (harmonic_item is None or item["id"] == "carney"):
                harmonic_item = item
    if harmonic_item is None:
        background = read_harmonic(ctx, "carney", {}, "Carney all harmonics")
    else:
        background = harmonic_item
    if strategy and strategy.get("id"):
        try:
            item = read_strategy(ctx, strategy["id"], strategy.get("params") or {}, capital, cost_bps)
            if item:
                items.append(item)
        except Exception as exc:  # noqa: BLE001
            items.append({"kind": "strategy", "id": strategy["id"], "title": strategy["id"], "section": "", "what": "", "now": f"Could not read this strategy: {exc}", "tone": "neutral"})
    if focus:
        items.sort(key=lambda item: 0 if item["id"] == focus else 1)

    plan = swing_plan(ctx, rating, background.get("pattern"), capital)
    day = _pct(ctx.close, ctx.prev)
    trend_word = {"Bullish": "an uptrend", "Bearish": "a downtrend", "Neutral": "a sideways range"}[plan["bias"]]
    headline = (f"{symbol} closed at {inr(ctx.close)} ({_signed(day)}) on {ctx.ts[-1]}. Overall it looks like {trend_word}: "
                + "; ".join(plan.get("reasons", [])[:4]) + ".")
    snapshot = {
        "close": ctx.close, "day_pct": day, "date": ctx.ts[-1], "atr": ctx.atr_now,
        "atr_pct": (ctx.atr_now / ctx.close * 100) if ctx.atr_now else None,
        "rsi": _last(ctx.rsi), "sma50": _last(ctx.sma50), "sma200": _last(ctx.sma200), "ema20": _last(ctx.ema20),
        "hi52": _last(ctx.hi252), "lo52": _last(ctx.lo252), "vol_ratio": ctx.vol_ratio,
    }
    return {
        "symbol": symbol,
        "headline": headline,
        "snapshot": snapshot,
        "rating": rating,
        "plan": plan,
        "harmonic": background,
        "items": items,
        "disclaimer": "Rule-based reading of delayed daily data. The odds are what the same rules did on this stock's own past, not a forecast. Not investment advice.",
    }
