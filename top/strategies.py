"""Fifty long/flat research strategies. Signals are known at the close."""

from __future__ import annotations

from top import arrays as np

from top.indicators import (
    adx_pack,
    aroon,
    atr,
    awesome,
    bbands,
    cmf,
    cmo,
    donchian,
    ema,
    hma,
    ichimoku,
    macd,
    mfi,
    obv,
    psar,
    roc,
    rsi,
    rolling_max,
    rolling_mean,
    rolling_min,
    sma,
    stoch,
    supertrend,
    tsi,
    vortex,
    zscore,
)

STRATEGIES = []


def _num(key, label, default, min_, max_, step=1):
    return {"key": key, "label": label, "type": "number", "default": default, "min": min_, "max": max_, "step": step}


def _p(params, key, default):
    value = params.get(key, default)
    return int(value) if isinstance(default, int) else float(value)


def _nan_prefix(mask, warmup):
    out = np.where(mask, 1.0, 0.0).astype(float)
    out[: int(warmup)] = np.nan
    return out


def _hold(entry, exit_, warmup):
    out = np.full(len(entry), np.nan)
    holding = False
    for i in range(int(warmup), len(entry)):
        if holding and exit_[i]:
            holding = False
        elif (not holding) and entry[i]:
            holding = True
        out[i] = 1.0 if holding else 0.0
    return out


def _cross_up(a, b):
    prev_a = np.roll(a, 1)
    prev_b = np.roll(b, 1)
    prev_a[0] = np.nan
    prev_b[0] = np.nan
    return (a > b) & (prev_a <= prev_b)


def _cross_down(a, b):
    prev_a = np.roll(a, 1)
    prev_b = np.roll(b, 1)
    prev_a[0] = np.nan
    prev_b[0] = np.nan
    return (a < b) & (prev_a >= prev_b)


def _add(strategy_id, name, section, blurb, params, fn, **meta):
    """Register a strategy. Optional meta: creator (YouTube handle), sources (URLs), confidence, license."""
    STRATEGIES.append(
        {
            "id": strategy_id,
            "name": name,
            "section": section,
            "blurb": blurb,
            "params": params,
            "fn": fn,
            "meta": meta,
        }
    )


def _register():
    if STRATEGIES:
        return
    T = "Trend"
    R = "Mean reversion"
    B = "Breakout"
    O = "Oscillator"
    V = "Volume"
    P = "Price action"

    _add("sma_cross", "SMA cross", T, "Long when the fast SMA is above the slow SMA.", [_num("fast", "Fast", 20, 2, 100), _num("slow", "Slow", 50, 5, 250)], lambda f, p: _nan_prefix(sma(f.c, _p(p, "fast", 20)) > sma(f.c, _p(p, "slow", 50)), _p(p, "slow", 50)))
    _add("golden_cross", "Golden cross 50/200", T, "Long when SMA 50 is above SMA 200.", [], lambda f, p: _nan_prefix(sma(f.c, 50) > sma(f.c, 200), 200))
    _add("ema_cross", "EMA 9/21", T, "Long when EMA 9 is above EMA 21.", [], lambda f, p: _nan_prefix(ema(f.c, 9) > ema(f.c, 21), 21))
    _add("ema_12_26", "EMA 12/26", T, "Long when EMA 12 is above EMA 26.", [], lambda f, p: _nan_prefix(ema(f.c, 12) > ema(f.c, 26), 26))
    _add("triple_ema", "Triple EMA alignment", T, "Long only when EMA 8, 21, and 55 are stacked.", [], lambda f, p: _nan_prefix((ema(f.c, 8) > ema(f.c, 21)) & (ema(f.c, 21) > ema(f.c, 55)), 55))
    _add("hull_trend", "Hull trend", T, "Long when close is above the Hull moving average.", [_num("length", "Length", 20, 4, 120)], lambda f, p: _nan_prefix(f.c > hma(f.c, _p(p, "length", 20)), _p(p, "length", 20)))
    _add("above_sma200", "Above SMA 200", T, "Long while price holds above the 200-day average.", [], lambda f, p: _nan_prefix(f.c > sma(f.c, 200), 200))
    _add("above_ema50", "Above EMA 50", T, "Long while price holds above the 50-day EMA.", [], lambda f, p: _nan_prefix(f.c > ema(f.c, 50), 50))
    _add("dual_momentum", "Dual momentum", T, "Long when price is above SMA 200 and 6-month ROC is positive.", [], lambda f, p: _nan_prefix((f.c > sma(f.c, 200)) & (roc(f.c, 126) > 0), 200))
    _add("ema_ribbon", "EMA ribbon expansion", T, "Long when the short ribbon is above the long ribbon.", [], lambda f, p: _nan_prefix((ema(f.c, 8) > ema(f.c, 21)) & (ema(f.c, 21) > ema(f.c, 55)) & ((ema(f.c, 8) - ema(f.c, 55)) > (ema(f.c, 21) - ema(f.c, 55)) * 0.15), 55))

    def _rsi_rev(f, p):
        length, buy, sell = _p(p, "length", 14), _p(p, "buy", 30), _p(p, "sell", 55)
        value = rsi(f.c, length)
        return _hold(value < buy, value > sell, length)

    _add("rsi_reversion", "RSI reversion", R, "Buy an RSI washout and exit when RSI recovers.", [_num("length", "Length", 14, 2, 30), _num("buy", "Buy below", 30, 5, 45), _num("sell", "Exit above", 55, 40, 80)], _rsi_rev)

    def _rsi_pull(f, p):
        value = rsi(f.c, 14)
        trend = f.c > sma(f.c, 200)
        return _hold(trend & (value < _p(p, "buy", 40)), value > _p(p, "sell", 60), 200)

    _add("rsi_pullback", "RSI pullback in uptrend", R, "Buy RSI dips only while price is above SMA 200.", [_num("buy", "Buy below", 40, 20, 50), _num("sell", "Exit above", 60, 50, 80)], _rsi_pull)
    _add("rsi_trend", "RSI trend", O, "Long when RSI holds above 55, flat below 45.", [], lambda f, p: _hold(rsi(f.c, 14) > 55, rsi(f.c, 14) < 45, 14))

    def _stoch_rev(f, p):
        k, d = stoch(f.h, f.l, f.c, 14, 3)
        return _hold((k < 20) & _cross_up(k, d), k > 80, 20)

    _add("stoch_reversion", "Stochastic reversal", R, "Buy a %K/%D cross from oversold and exit overbought.", [], _stoch_rev)
    _add("stoch_trend", "Stochastic trend", O, "Long when smoothed %K is above %D and above 50.", [], lambda f, p: _nan_prefix((stoch(f.h, f.l, f.c, 14, 3)[0] > stoch(f.h, f.l, f.c, 14, 3)[1]) & (stoch(f.h, f.l, f.c, 14, 3)[0] > 50), 20))

    def _srsi(f, p):
        value = rsi(f.c, 14)
        k, d = stoch(value, value, value, 14, 3)
        return _hold(_cross_up(k, d) & (k < 30), _cross_down(k, d) & (k > 70), 30)

    _add("stochrsi", "Stochastic RSI cross", O, "Trade StochRSI crosses from the extremes.", [], _srsi)
    _add("macd_cross", "MACD cross", O, "Long when the MACD line is above its signal.", [], lambda f, p: _nan_prefix(macd(f.c, 12, 26, 9)[0] > macd(f.c, 12, 26, 9)[1], 35))
    _add("macd_hist", "MACD histogram flip", O, "Long when the histogram turns positive.", [], lambda f, p: _nan_prefix(macd(f.c, 12, 26, 9)[2] > 0, 35))
    _add("macd_zero", "MACD zero line", O, "Long when MACD itself is above zero.", [], lambda f, p: _nan_prefix(macd(f.c, 12, 26, 9)[0] > 0, 35))

    def _bb_rev(f, p):
        upper, mid, lower = bbands(f.c, 20, 2)
        return _hold(f.c < lower, f.c > mid, 20)

    def _bb_break(f, p):
        upper, mid, lower = bbands(f.c, 20, 2)
        return _hold(f.c > upper, f.c < mid, 20)

    _add("bb_reversion", "Bollinger reversion", R, "Buy a close below the lower band and exit at the midline.", [], _bb_rev)
    _add("bb_breakout", "Bollinger breakout", B, "Buy a close above the upper band and exit at the midline.", [], _bb_break)

    def _squeeze(f, p):
        upper, mid, lower = bbands(f.c, 20, 2)
        width = (upper - lower) / np.where(mid == 0, np.nan, mid)
        quiet = width < rolling_mean(width, 120)
        return _hold(quiet & (f.c > upper), f.c < mid, 120)

    _add("bb_squeeze", "Bollinger squeeze break", B, "Buy an upper-band break after bandwidth has been compressed.", [], _squeeze)

    def _keltner(f, p):
        mid = ema(f.c, 20)
        band = atr(f.h, f.l, f.c, 20) * 2
        return _hold(f.c > mid + band, f.c < mid, 20)

    _add("keltner_break", "Keltner breakout", B, "Buy a close above the upper Keltner channel.", [], _keltner)
    _add("donchian_20", "Donchian 20 break", B, "Long after a 20-day high until a 10-day low.", [], lambda f, p: _hold(f.c >= rolling_max(f.h, 20), f.c <= rolling_min(f.l, 10), 20))
    _add("donchian_55", "Donchian 55 break", B, "Turtle-style 55-day high entry and 20-day low exit.", [], lambda f, p: _hold(f.c >= rolling_max(f.h, 55), f.c <= rolling_min(f.l, 20), 55))
    _add("turtle_20", "Turtle 20/10", B, "20-day breakout entry, 10-day breakdown exit.", [], lambda f, p: _hold(f.c > rolling_max(np.roll(f.h, 1), 20), f.c < rolling_min(np.roll(f.l, 1), 10), 21))
    _add("supertrend", "Supertrend flip", T, "Long when Supertrend is below price.", [_num("length", "ATR", 10, 2, 30), _num("mult", "Mult", 3, 1, 6)], lambda f, p: _nan_prefix(supertrend(f.h, f.l, f.c, _p(p, "length", 10), _p(p, "mult", 3))[1] > 0, _p(p, "length", 10)))
    _add("psar", "Parabolic SAR", T, "Long when SAR is below the close.", [], lambda f, p: _nan_prefix(psar(f.h, f.l) < f.c, 5))

    def _adx(f, p):
        adx_, plus, minus = adx_pack(f.h, f.l, f.c, 14)
        return _nan_prefix((plus > minus) & (adx_ > _p(p, "floor", 20)), 28)

    _add("adx_di", "ADX trend filter", T, "Long when +DI leads -DI and ADX is above the floor.", [_num("floor", "ADX floor", 20, 10, 40)], _adx)
    _add("aroon", "Aroon cross", T, "Long when Aroon Up is above Aroon Down.", [], lambda f, p: _nan_prefix(aroon(f.h, f.l, 25)[0] > aroon(f.h, f.l, 25)[1], 25))
    _add("vortex", "Vortex cross", T, "Long when VI+ is above VI-.", [], lambda f, p: _nan_prefix(vortex(f.h, f.l, f.c, 14)[0] > vortex(f.h, f.l, f.c, 14)[1], 14))
    _add("cci_zero", "CCI zero cross", O, "Long when CCI is above zero.", [], lambda f, p: _nan_prefix(((f.c - sma(f.c, 20)) / np.where(rolling_mean(np.abs(f.c - sma(f.c, 20)), 20) == 0, np.nan, rolling_mean(np.abs(f.c - sma(f.c, 20)), 20))) > 0, 20))

    def _cci_rev(f, p):
        tp = (f.h + f.l + f.c) / 3
        mean = sma(tp, 20)
        dev = rolling_mean(np.abs(tp - mean), 20)
        value = (tp - mean) / np.where(0.015 * dev == 0, np.nan, 0.015 * dev)
        return _hold(value < -100, value > 0, 20)

    _add("cci_reversion", "CCI extreme reversal", R, "Buy CCI below -100 and exit when it returns through zero.", [], _cci_rev)
    _add("willr", "Williams %R reversal", R, "Buy %R below -80 and exit above -50.", [], lambda f, p: _hold((-100 * (rolling_max(f.h, 14) - f.c) / np.where((rolling_max(f.h, 14) - rolling_min(f.l, 14)) == 0, np.nan, rolling_max(f.h, 14) - rolling_min(f.l, 14))) < -80, (-100 * (rolling_max(f.h, 14) - f.c) / np.where((rolling_max(f.h, 14) - rolling_min(f.l, 14)) == 0, np.nan, rolling_max(f.h, 14) - rolling_min(f.l, 14))) > -50, 14))
    _add("roc_mom", "ROC momentum", O, "Long when 20-day rate of change is positive.", [], lambda f, p: _nan_prefix(roc(f.c, 20) > 0, 20))
    _add("tsi_cross", "TSI cross", O, "Long when TSI is above its signal EMA.", [], lambda f, p: _nan_prefix(tsi(f.c, 25, 13) > ema(tsi(f.c, 25, 13), 9), 40))
    _add("ao_cross", "Awesome oscillator", O, "Long when the awesome oscillator is above zero.", [], lambda f, p: _nan_prefix(awesome(f.h, f.l) > 0, 34))
    _add("obv_trend", "OBV trend", V, "Long when on-balance volume is above its 20-day average.", [], lambda f, p: _nan_prefix(obv(f.c, f.v) > sma(obv(f.c, f.v), 20), 20))
    _add("mfi_reversion", "MFI reversal", R, "Buy money-flow index below 20 and exit above 55.", [], lambda f, p: _hold(mfi(f.h, f.l, f.c, f.v, 14) < 20, mfi(f.h, f.l, f.c, f.v, 14) > 55, 14))
    _add("cmf_trend", "Chaikin money flow", V, "Long when 20-day CMF is positive.", [], lambda f, p: _nan_prefix(cmf(f.h, f.l, f.c, f.v, 20) > 0, 20))

    def _ichi(f, p):
        tenkan, kijun, span_a, span_b, _chikou = ichimoku(f.h, f.l, f.c)
        cloud_top = np.maximum(span_a, span_b)
        return _nan_prefix((f.c > cloud_top) & (tenkan > kijun), 52)

    _add("ichimoku", "Ichimoku break", T, "Long above the cloud when Tenkan leads Kijun.", [], _ichi)
    _add("pivot_break", "Pivot R1 break", B, "Long when the close clears yesterday's R1.", [], lambda f, p: _nan_prefix(f.c > (2 * ((np.roll(f.h, 1) + np.roll(f.l, 1) + np.roll(f.c, 1)) / 3) - np.roll(f.l, 1)), 2))
    _add("week52", "52-week high", B, "Long on a 252-day closing high until a 20% giveback.", [], lambda f, p: _hold(f.c >= rolling_max(np.roll(f.c, 1), 252), f.c < rolling_max(f.c, 252) * 0.8, 252))
    _add("volume_break", "Volume breakout", B, "Long when price breaks a 20-day high on 1.5x average volume.", [], lambda f, p: _hold((f.c > rolling_max(np.roll(f.h, 1), 20)) & (f.v > 1.5 * sma(f.v, 20)), f.c < sma(f.c, 20), 21))

    def _nr7(f, p):
        span = f.h - f.l
        narrow = span <= rolling_min(span, 7)
        return _hold(narrow & (f.c > np.roll(f.h, 1)), f.c < np.roll(f.l, 1), 8)

    _add("nr7", "NR7 breakout", P, "Buy the break of a 7-day narrow-range bar.", [], _nr7)

    def _inside(f, p):
        inside = (f.h < np.roll(f.h, 1)) & (f.l > np.roll(f.l, 1))
        return _hold(np.roll(inside, 1) & (f.c > np.roll(f.h, 1)), f.c < sma(f.c, 10), 12)

    _add("inside_bar", "Inside-bar break", P, "Buy a close through the prior inside bar's high.", [], _inside)
    _add("gap_up", "Gap continuation", P, "Long after an opening gap up that holds the open.", [], lambda f, p: _hold((f.o > np.roll(f.c, 1) * 1.005) & (f.c > f.o), f.c < ema(f.c, 10), 10))
    _add("gap_fade", "Gap-down fade", R, "Buy a 1% gap down and exit after a 5-day bounce or a new low.", [], lambda f, p: _hold(f.o < np.roll(f.c, 1) * 0.99, (f.c > np.roll(f.c, 5)) | (f.c < f.l), 6))
    _add("three_up", "Three rising closes", P, "Long after three higher closes, exit under EMA 10.", [], lambda f, p: _hold((f.c > np.roll(f.c, 1)) & (np.roll(f.c, 1) > np.roll(f.c, 2)) & (np.roll(f.c, 2) > np.roll(f.c, 3)), f.c < ema(f.c, 10), 10))
    _add("zscore", "Z-score reversion", R, "Buy a 20-day z-score below -2 and exit at the mean.", [], lambda f, p: _hold(zscore(f.c, 20) < -2, zscore(f.c, 20) > 0, 20))
    _add("pullback_ema", "Pullback to EMA 20", T, "In an uptrend, buy a tag of EMA 20 that closes back above it.", [], lambda f, p: _hold((f.c > sma(f.c, 50)) & (f.l <= ema(f.c, 20)) & (f.c > ema(f.c, 20)), f.c < ema(f.c, 20), 50))
    _add("cmo_trend", "CMO trend", O, "Long when Chande momentum is positive.", [], lambda f, p: _nan_prefix(cmo(f.c, 14) > 0, 14))
    _add("donchian_mid", "Donchian midline", T, "Long when close is above the 20-day Donchian midline.", [], lambda f, p: _nan_prefix(f.c > donchian(f.h, f.l, 20)[1], 20))
    _add("higher_high", "Higher-high break", P, "Long when today's high clears the prior 10-day high.", [], lambda f, p: _hold(f.h > rolling_max(np.roll(f.h, 1), 10), f.c < rolling_min(f.l, 5), 11))
    _add("atr_trail", "ATR trail", T, "Enter above EMA 20 and trail 3 ATR below the close.", [], lambda f, p: _hold(f.c > ema(f.c, 20) + atr(f.h, f.l, f.c, 14), f.c < rolling_max(f.c, 20) - 3 * atr(f.h, f.l, f.c, 14), 20))

    X = "Trend reversal"
    _add("ema50_reclaim", "EMA 50 reclaim", X, "Buy a close back above EMA 50 after at least five closes below it.", [], lambda f, p: _hold((f.c > ema(f.c, 50)) & (np.roll(f.c, 1) < np.roll(ema(f.c, 50), 1)) & (np.roll(f.c, 5) < np.roll(ema(f.c, 50), 5)), f.c < ema(f.c, 50), 55))
    _add("breakdown_reclaim", "Breakdown reclaim", X, "Buy a close back inside the range after a pierce of the 20-day low.", [], lambda f, p: _hold((f.l < rolling_min(np.roll(f.l, 1), 20)) & (f.c > rolling_min(np.roll(f.l, 1), 20)), f.c < rolling_min(f.l, 10), 21))
    _add("swing_reversal", "Swing-low reversal", X, "Buy a close through the prior 10-day high within three sessions of a 20-day low.", [], lambda f, p: _hold((f.l <= rolling_min(f.l, 20)) & (f.c > rolling_max(np.roll(f.h, 1), 10)), f.c < ema(f.c, 10), 21))
    _add("macd_reversal", "MACD reversal", X, "Buy a MACD cross up while price is still below SMA 50, and exit above it.", [], lambda f, p: _hold(_cross_up(macd(f.c, 12, 26, 9)[0], macd(f.c, 12, 26, 9)[1]) & (f.c < sma(f.c, 50)), f.c > sma(f.c, 50), 35))

    from top.harmonics import PATTERN_SPECS, position as harmonic_position

    harm_params = [_num("swing", "Swing %", 3, 1, 20, 0.5), _num("tolerance", "Tolerance", 0.05, 0.01, 0.12, 0.01), _num("hold", "Hold bars", 10, 1, 40)]
    for spec in PATTERN_SPECS:
        pattern_id = spec["id"]
        _add(
            f"harm_{pattern_id}",
            f"{spec['name']} long",
            "Harmonics",
            "Bullish Scott Carney completion. Long for the hold window. Research ratios, not a certified signal.",
            harm_params,
            lambda f, p, pattern_id=pattern_id: harmonic_position(f, p, pattern_id),
        )
    _add(
        "harm_carney",
        "Any Carney bullish",
        "Harmonics",
        "Long after any bullish Carney pattern in this set completes.",
        harm_params,
        lambda f, p: harmonic_position(f, p, None),
    )

    from top.patterns import breakout_position, darvas_position

    _add("darvas_breakout", "Darvas box breakout", B,
         "Nicolas Darvas: buy a close above a confirmed box top near the 52-week high; stop at the box bottom, raised to each new box's bottom.",
         [_num("confirm", "Confirm days", 3, 2, 10), _num("near_high", "Within % of 52w high", 10.0, 0.0, 50.0, 1.0)], darvas_position)
    _add("breakout_trend_vol", "Volume breakout trend", B,
         "Buy a close above the prior Range high on volume ≥ Volume × average; ride it with a trailing stop of Trail ATR below the best close; exit early if the breakout fails within 3 sessions.",
         [_num("length", "Range", 20, 5, 120), _num("vol_mult", "Volume ×", 1.5, 1.0, 5.0, 0.1), _num("atr_mult", "Trail ATR", 3.0, 1.0, 8.0, 0.5)], breakout_position)

    from top.creators import register_strategies

    register_strategies(_add)


_register()


def catalog():
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "section": item["section"],
            "blurb": item["blurb"],
            "params": item["params"],
            **item.get("meta", {}),
        }
        for item in STRATEGIES
    ]


def signal(strategy_id: str, frame, params: dict | None = None) -> np.ndarray:
    params = params or {}
    for item in STRATEGIES:
        if item["id"] == strategy_id:
            position = np.asarray(item["fn"](frame, params), dtype=float)
            if len(position) != len(frame):
                raise RuntimeError(f"{strategy_id} returned {len(position)} bars, expected {len(frame)}")
            return position
    raise KeyError(strategy_id)
