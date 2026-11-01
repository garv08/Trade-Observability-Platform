"""Key levels plan and pattern breakout projector (method inspired by @TradZoo)."""

from __future__ import annotations

import math
import unittest

from tests.support import use_temp_store
from tests.test_engine import frame_for
from top import levels
from top.indicators import Frame, catalog as indicator_catalog
from top.strategies import catalog as strategy_catalog, signal


def _frame(closes, spread=0.004):
    ts = [f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(closes))]
    highs = [c * (1 + spread) for c in closes]
    lows = [c * (1 - spread) for c in closes]
    return Frame(ts, closes, highs, lows, closes, [1000] * len(closes))


class LevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        cls.frame = frame_for("TCS")

    def test_nice_step_and_snap(self):
        self.assertEqual(levels.nice_step(24500), 50)
        self.assertEqual(levels.nice_step(700), 2)
        self.assertEqual(levels.nice_step(25), 0.05)
        self.assertEqual(levels.snap(24563, 50), 24550)

    def test_clusters_do_not_chain(self):
        merged = levels._cluster([100, 101, 102, 103, 104, 105], tol=2.0)
        self.assertEqual(len(merged), 2)

    def test_levels_bracket_the_close(self):
        out = levels.key_levels(self.frame, {})
        c = self.frame.c.tolist()
        checked = 0
        for i in range(60, len(c)):
            r2, r1, s1, s2 = (out[k][i] for k in ("r2", "r1", "s1", "s2"))
            if r2 == r2:
                self.assertTrue(r2 > r1 > c[i] > s1 > s2, (i, r2, r1, c[i], s1, s2))
                checked += 1
        self.assertGreater(checked, 500)

    def test_plan_text(self):
        out = levels.key_levels(self.frame, {})
        close = self.frame.c.tolist()[-1]
        plan = levels.level_plan(out, close)
        self.assertLess(plan["long_targets"][0], plan["long_targets"][2])
        self.assertGreater(plan["short_targets"][0], plan["short_targets"][2])
        text = levels.describe_plan(plan, close)
        self.assertIn("Long above", text)
        self.assertIn("targets", text)
        self.assertIn("Below", text)

    def test_levels_are_causal(self):
        full = levels.key_levels(self.frame, {})
        f = self.frame
        cut = 400
        part = Frame(f.ts[:cut], f.o.tolist()[:cut], f.h.tolist()[:cut], f.l.tolist()[:cut], f.c.tolist()[:cut], f.v.tolist()[:cut])
        short = levels.key_levels(part, {})
        for key in ("r2", "r1", "s1", "s2"):
            self.assertAlmostEqual(full[key][cut - 1], short[key][cut - 1], places=6)

    def test_classify(self):
        self.assertEqual(levels.classify(-1.0, -0.5, 30, 10, 5), "Falling wedge")
        self.assertEqual(levels.classify(0.0, 0.5, 30, 10, 5), "Ascending triangle")
        self.assertEqual(levels.classify(-0.5, 0.0, 30, 10, 5), "Descending triangle")
        self.assertEqual(levels.classify(-0.5, 0.5, 30, 10, 5), "Symmetrical triangle")
        self.assertEqual(levels.classify(0.0, 0.0, 30, 29, 5), "Range")
        self.assertEqual(levels.classify(0.0, 0.0, 10, 30, 5), "Broadening wedge")

    def test_falling_wedge_breakout_projects_height(self):
        # 40 flat bars, then a 60-bar falling wedge (lower highs, slower lower lows), then a breakout.
        closes = [100.0] * 40
        for x in range(60):
            top = 100 - 0.30 * x
            bottom = 86 - 0.12 * x
            closes.append(top if x % 10 < 5 else bottom)
        closes += [92, 95, 97]
        f = _frame(closes, spread=0.001)
        out = levels.pattern_scan(f, {"window": 60})
        self.assertTrue(out["events"], "breakout expected")
        e = out["events"][-1]
        self.assertGreater(e["t2"], e["level"])
        self.assertAlmostEqual(e["t2"] - e["level"], e["height"], places=6)
        self.assertLess(e["stop"], e["level"])

    def test_registered(self):
        studies = {s["id"]: s for s in indicator_catalog()}
        self.assertEqual(studies["key_levels"]["section"], "Trend")
        self.assertTrue(studies["key_levels"]["step"])
        self.assertIn("TradZoo", studies["key_levels"]["credit"])
        strategies = {s["id"]: s for s in strategy_catalog()}
        for sid in ("key_level_breakout", "pattern_breakout"):
            self.assertEqual(strategies[sid]["section"], "Breakout")
            pos = signal(sid, self.frame, {}).tolist()
            self.assertTrue({x for x in pos if x == x} <= {0.0, 1.0})


if __name__ == "__main__":
    unittest.main()
