"""Telegram-channel methods: long base (@wealthcreator7), BAMM and Half Bat (@PhoenixHarmonic)."""

from __future__ import annotations

import unittest
from datetime import date

from tests.support import business_days
from top import channels
from top.explain import Context, read_study
from top.indicators import Frame, compute
from top.strategies import signal


def frame_from_path(path, volume=None, wiggle=0.004):
    """Daily bars following straight lines between (index, price) points."""
    closes = []
    for (i0, p0), (i1, p1) in zip(path, path[1:]):
        closes += [p0 + (p1 - p0) * (i - i0) / (i1 - i0) for i in range(i0, i1)]
    closes.append(path[-1][1])
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) * (1 + wiggle) for o, c in zip(opens, closes)]
    lows = [min(o, c) * (1 - wiggle) for o, c in zip(opens, closes)]
    vols = volume or [1000.0] * len(closes)
    return Frame(business_days(date(2022, 1, 3), len(closes)), opens, highs, lows, closes, vols)


class LongBaseTests(unittest.TestCase):
    def setUp(self):
        # Rise to 110, a year-long base between 95 and 110, a volume breakout at bar 330, a rally, then a slide.
        path = [(0, 80), (40, 110), (80, 95), (160, 108), (220, 96), (329, 108), (330, 112), (430, 170), (560, 120)]
        vols = [1000.0] * 561
        vols[330] = 4000.0
        self.f = frame_from_path(path, vols)

    def test_breakout_day_entry_and_weekly_trail_exit(self):
        trades, bases, _ = channels.long_base_events(self.f, {})
        self.assertEqual([t["entry"] for t in trades], [330])
        self.assertAlmostEqual(trades[0]["top"], max(self.f.h.tolist()[80:330]), places=6)
        self.assertNotEqual(trades[0]["reason"], "open")
        self.assertGreater(trades[0]["exit"], 430)  # held through the rally, out on the slide
        self.assertTrue(trades[0]["reason"].startswith("weekly EMA"))
        pos = signal("wc_long_base", self.f, {}).tolist()
        self.assertEqual(pos[329], 0.0)
        self.assertEqual(pos[330], 1.0)

    def test_needs_volume_and_limits_risk(self):
        flat = frame_from_path([(0, 80), (40, 110), (80, 95), (160, 108), (220, 96), (329, 108), (330, 112), (430, 170), (560, 120)])
        self.assertEqual(channels.long_base_events(flat, {})[0], [])
        self.assertTrue(channels.long_base_events(flat, {"vol_mult": 0})[0])
        self.assertEqual(channels.long_base_events(self.f, {"max_risk": 2.0})[0], [])

    def test_study_and_reading(self):
        study = compute("wc_long_base", self.f, {})
        self.assertEqual(set(study["series"]), {"base_top", "base_floor", "weekly_ema"})
        self.assertTrue(any(m["text"] == "Long base breakout" for m in study["markers"]))
        reading = read_study(Context(self.f), "wc_long_base", {})
        self.assertIn("1 completed trades, 1 up", reading["now"])


class PhoenixTests(unittest.TestCase):
    def test_bamm_enters_above_b_and_exits_at_d(self):
        # X 150 -> A 100 -> B 125 (0.5 of XA) -> C 112 (0.52 of AB) -> rally through B to 148.
        f = frame_from_path([(0, 120), (20, 150), (50, 100), (70, 125), (90, 112), (110, 148), (140, 148)])
        trades = channels.bamm_trades(f, {})
        self.assertEqual(len(trades), 1)
        t = trades[0]
        b = max(f.h.tolist()[60:80])
        self.assertGreater(f.c.tolist()[t["entry"]], b)
        self.assertLessEqual(f.c.tolist()[t["entry"] - 1], b)
        x, a = max(f.h.tolist()[10:30]), min(f.l.tolist()[40:60])
        self.assertAlmostEqual(t["target"], a + 0.886 * (x - a), places=6)
        self.assertAlmostEqual(t["stop"], min(f.l.tolist()[80:100]), places=6)
        self.assertEqual(t["reason"], "target")

    def test_half_bat_buys_the_half_retracement(self):
        # X 100 -> A 150, pullback to 124 (just past 0.5), then a rally back to A.
        f = frame_from_path([(0, 110), (10, 100), (40, 150), (60, 124), (62, 124), (90, 152), (100, 152)])
        setups = [s for s in channels.half_bat_setups(f, {}) if s["state"] == "triggered"]
        self.assertTrue(setups)
        s = setups[0]
        self.assertAlmostEqual(s["zone"], s["a"] - 0.5 * (s["a"] - s["x"]), places=6)
        self.assertLessEqual(f.l.tolist()[s["touch"]], s["zone"])
        self.assertGreater(s["entry"], s["touch"])
        trade = channels.half_bat_trades(f, {})[0]
        self.assertEqual(trade["reason"], "target")

    def test_studies_render(self):
        f = frame_from_path([(0, 120), (20, 150), (50, 100), (70, 125), (90, 112), (110, 148), (140, 148)])
        for sid in ("ph_bamm", "ph_half_bat"):
            out = compute(sid, f, {})
            self.assertEqual(out["series"], {})
            self.assertIsNotNone(read_study(Context(f), sid, {}))


if __name__ == "__main__":
    unittest.main()
