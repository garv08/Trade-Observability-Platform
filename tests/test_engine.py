"""Engine checks: indicators, strategies, backtests, harmonics, fundamentals parsing, and readings."""

from __future__ import annotations

import math
import unittest

from tests.support import use_temp_store
from top import harmonics
from top.backtest import run as run_backtest
from top.explain import explain, technical_rating, Context
from top.fundamentals import parse_html
from top.indicators import Frame, catalog as indicator_catalog, compute, ema
from top.store import load_bars, session
from top.strategies import catalog as strategy_catalog, signal
from top.verify import _gartley_frame


def frame_for(symbol: str) -> Frame:
    with session() as con:
        bars = load_bars(con, symbol)
    return Frame(
        [b["time"] for b in bars], [b["open"] for b in bars], [b["high"] for b in bars],
        [b["low"] for b in bars], [b["close"] for b in bars], [b["volume"] for b in bars],
    )


def finite(value) -> bool:
    return isinstance(value, float) and math.isfinite(value)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        cls.frame = frame_for("RELIANCE")
        # Context some studies read (delivery %, market regime); synthetic but realistic.
        cls.frame.context = {
            "delivery": {t: 30 + (i % 40) for i, t in enumerate(cls.frame.ts)},
            "regime": [{"vol_pct": float(i % 100)} for i in range(len(cls.frame.ts))],
        }

    def test_catalog_sizes(self):
        studies = indicator_catalog()
        strategies = strategy_catalog()
        self.assertGreaterEqual(len(studies), 136)
        self.assertGreaterEqual(len(strategies), 71)
        self.assertEqual(sum(1 for s in studies if s["section"] == "Harmonics"), 12)
        self.assertEqual(sum(1 for s in strategies if s["section"] == "Harmonics"), 12)
        self.assertTrue(any(s["section"] == "Trend reversal" for s in strategies))

    def test_every_study_has_a_latest_value(self):
        blank = []
        for item in indicator_catalog():
            result = compute(item["id"], self.frame, {})
            for key, values in result["series"].items():
                if (item["id"], key) in {("ichimoku", "chikou"), ("darvas", "upper"), ("darvas", "lower"), ("breakout_trend", "trail"),
                                           ("pattern_breakout", "upper"), ("pattern_breakout", "lower")}:
                    continue  # blank by design: lagging span; no active Darvas box; no active breakout trend
                if not finite(values.tolist()[-1]):
                    blank.append(f"{item['id']}.{key}")
        self.assertEqual(blank, [])

    def test_ema_seeds_after_leading_blanks(self):
        values = [float("nan")] * 5 + [float(i) for i in range(1, 30)]
        out = ema(values, 9).tolist()
        self.assertTrue(finite(out[-1]))
        self.assertTrue(math.isnan(out[5 + 7]))
        self.assertTrue(finite(out[5 + 8]))

    def test_every_strategy_backtests(self):
        f = self.frame
        for item in strategy_catalog():
            with self.subTest(strategy=item["id"]):
                position = signal(item["id"], f, {})
                self.assertEqual(len(position), len(f))
                result = run_backtest(f.ts, f.o, f.h, f.l, f.c, position)
                metrics = result["metrics"]
                self.assertIn("total_return_pct", metrics)
                self.assertGreater(metrics["ending_equity"], 0)

    def test_backtest_fills_next_open(self):
        f = self.frame
        position = [float("nan")] * 30 + [0.0] * 10 + [1.0] * 20 + [0.0] * (len(f) - 60)
        result = run_backtest(f.ts, f.o, f.h, f.l, f.c, position, cost_bps=0)
        trade = result["trades"][0]
        self.assertEqual(trade["entry"], f.ts[41])
        self.assertAlmostEqual(trade["entry_px"], round(f.o.tolist()[41], 2), places=2)

    def test_synthetic_gartley_is_found(self):
        times, opens, highs, lows, closes = _gartley_frame()
        found = {i for event in harmonics.detect(highs, lows, times, 3, 0.05) for i in event["ids"]}
        self.assertIn("gartley", found)

    def test_harmonic_study_draws_patterns(self):
        result = compute("carney", self.frame, {})
        self.assertTrue(result["drawings"])
        for drawing in result["drawings"]:
            self.assertIn(len(drawing["legs"]), (5, 6))
            times = [p["time"] for p in drawing["legs"]]
            self.assertEqual(times, sorted(times))

    def test_darvas_box_and_breakout(self):
        from top.patterns import darvas_boxes

        # rise to 110, hold below it for 3 days, set a 100 low held for 3 days, then break out
        highs = [100, 105, 110, 108, 107, 106, 104, 103, 104, 105, 106, 115]
        lows = [95, 100, 105, 102, 100, 101, 102, 101, 102, 103, 104, 110]
        closes = [98, 104, 109, 103, 101, 104, 103, 102, 103, 104, 105, 114]
        top, bot, events = darvas_boxes(highs, lows, closes, 3)
        self.assertEqual(events[-1][1], "breakout")
        self.assertEqual(events[-1][2], 110)
        self.assertEqual(events[-1][3], 100)
        self.assertTrue(all(t != t for t in top[:7]), "box must not exist before its bottom is confirmed")

    def test_breakout_detector_marks_volume_breakouts(self):
        from top.patterns import breakout_trend

        out = breakout_trend(self.frame, {})
        kinds = {kind for _, kind, _ in out["events"]}
        self.assertIn("breakout", kinds)
        for i, kind, level in out["events"]:
            if kind == "breakout":
                self.assertGreater(self.frame.c.tolist()[i], level)

    def test_fundamentals_parser(self):
        html = (
            '<ul id="top-ratios"><li class="flex flex-space-between"><span class="name">Stock P/E</span>'
            '<span class="nowrap value"><span class="number">19.2</span></span></li></ul>'
            '<div class="pros"><ul><li>Cash rich</li></ul></div><div class="cons"><ul><li>Low ROE</li></ul></div>'
        )
        parsed = parse_html("RELIANCE", html, "https://www.screener.in/company/RELIANCE/consolidated/")
        self.assertEqual(parsed["ratios"][0]["label"], "Stock P/E")
        self.assertEqual(parsed["pros"], ["Cash rich"])
        self.assertEqual(parsed["cons"], ["Low ROE"])

    def test_technical_rating_labels(self):
        rating = technical_rating(Context(self.frame))
        labels = {"Strong buy", "Buy", "Neutral", "Sell", "Strong sell"}
        for part in ("ma", "osc", "overall"):
            self.assertIn(rating[part]["label"], labels)

    def test_explain_reads_every_family(self):
        ids = ["sma", "bbands", "supertrend", "rsi", "macd", "atr", "obv", "cmf", "vol_sma", "adx", "ichimoku", "ema_ribbon", "pivots", "zscore", "carney"]
        out = explain(self.frame, "RELIANCE", [{"id": i, "params": {}} for i in ids], {"id": "sma_cross", "params": {}}, focus="rsi")
        self.assertEqual(out["items"][0]["id"], "rsi")
        self.assertEqual(len(out["items"]), len(ids) + 1)
        for item in out["items"]:
            self.assertNotIn("not ready", item["now"], item["id"])
            self.assertNotIn("Could not read", item["now"], item["id"])
        plan = out["plan"]
        self.assertIn(plan["bias"], ("Bullish", "Bearish", "Neutral"))
        if plan.get("entry") is not None:
            self.assertGreater(plan["entry"], plan["stop"])
            self.assertGreater(plan["t2"], plan["t1"])
            self.assertGreater(plan["t1"], plan["entry"])

    def test_swing_plan_on_every_symbol(self):
        from top.universe import UNIVERSE

        for row in UNIVERSE:
            with self.subTest(symbol=row["symbol"]):
                plan = explain(frame_for(row["symbol"]), row["symbol"], [], None)["plan"]
                self.assertIn(plan["bias"], ("Bullish", "Bearish", "Neutral"))
                self.assertTrue(plan["steps"])


if __name__ == "__main__":
    unittest.main()
