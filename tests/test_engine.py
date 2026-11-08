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
        self.assertEqual(sum(1 for s in studies if s["section"] == "Harmonics"), 13)
        self.assertEqual(sum(1 for s in strategies if s["section"] == "Harmonics"), 15)
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

    def test_harmonic_strategies_do_not_look_ahead(self):
        f = self.frame
        n = len(f)
        for sid in ("harm_carney", "harm_abcd", "harm_prz", "harm_prz_bar", "harm_prz_touch"):
            full = signal(sid, f, {}).tolist()
            self.assertTrue(any(v == 1.0 for v in full), sid)
            for k in range(n - 600, n, 23):
                cut = Frame(f.ts[:k], f.o.tolist()[:k], f.h.tolist()[:k], f.l.tolist()[:k], f.c.tolist()[:k], f.v.tolist()[:k])
                part = signal(sid, cut, {}).tolist()
                same = [(a == b) or (a != a and b != b) for a, b in zip(full[:k], part)]
                self.assertTrue(all(same), f"{sid} changed past positions when future bars were added (cut {k})")

    def test_harmonic_entry_waits_for_d_confirmation(self):
        times, opens, highs, lows, closes = _gartley_frame()
        events = [e for e in harmonics.detect(highs, lows, times, 3, 0.05) if "gartley" in e["ids"]]
        self.assertTrue(events)
        self.assertGreater(events[0]["confirmed"], events[0]["index"])

    def test_carney_bat_prz_trade(self):
        path = [(0, 120), (10, 100), (30, 150), (40, 130), (50, 145), (80, 105), (110, 140), (120, 140)]
        closes = []
        for (i0, p0), (i1, p1) in zip(path, path[1:]):
            closes += [p0 + (p1 - p0) * (i - i0) / (i1 - i0) for i in range(i0, i1)]
        opens = [closes[0]] + closes[:-1]
        highs = [max(o, c) * 1.003 for o, c in zip(opens, closes)]
        lows = [min(o, c) * 0.997 for o, c in zip(opens, closes)]
        times = [f"2024-01-{1 + i // 28:02d}-{i % 28:02d}" for i in range(len(closes))]
        frame = Frame(times, opens, highs, lows, closes, [1000.0] * len(closes))
        setups = harmonics.prz_setups(frame.h.tolist(), frame.l.tolist(), 3, 0.05)
        self.assertEqual([s["pattern"] for s in setups], ["bat"])
        bat = setups[0]
        self.assertAlmostEqual(bat["d"], bat["a"] - 0.886 * (bat["a"] - bat["x"]), places=6)
        self.assertAlmostEqual(bat["hop"], bat["a"] - 1.13 * (bat["a"] - bat["x"]), places=6)
        trades = harmonics.prz_trades(frame, {"confirm": 2})
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertLessEqual(frame.l.tolist()[t["touch"]], bat["d"])
        self.assertGreater(t["entry"], t["touch"])  # Carney confirmation comes after the PRZ is reached
        self.assertEqual(t["reason"], "target")
        self.assertGreaterEqual(closes[t["exit"]], t["low"] + 0.618 * (bat["a"] - t["low"]))
        touch = harmonics.prz_trades(frame, {"confirm": 0})[0]
        self.assertEqual(touch["entry"], touch["touch"])
        # Each PRZ strategy runs its own confirmation mode with default settings.
        by_id = {sid: signal(sid, frame, {}).tolist() for sid in ("harm_prz", "harm_prz_touch")}
        self.assertEqual(by_id["harm_prz_touch"].index(1.0), touch["entry"])
        self.assertEqual(by_id["harm_prz"].index(1.0), t["entry"])
        study = compute("carney_prz", frame, {})
        self.assertTrue(any(m["text"].startswith("PRZ Bat") for m in study["markers"]))

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
