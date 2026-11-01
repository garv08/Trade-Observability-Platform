"""Checks for the creator strategies (@neurotrader888, @UnbiasedTradingGoshawk)."""

from __future__ import annotations

import math
import unittest

from tests.support import use_temp_store
from tests.test_engine import frame_for
from top import creators, market
from top.indicators import catalog as indicator_catalog, compute
from top.strategies import catalog as strategy_catalog, signal


class CreatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        cls.frame = frame_for("INFY")

    def test_sections_and_provenance(self):
        strategies = strategy_catalog()
        for handle in (creators.NT, creators.UT):
            items = [s for s in strategies if s["section"] == handle]
            self.assertGreaterEqual(len(items), 4, handle)
            for item in items:
                self.assertEqual(item["creator"], handle)
                self.assertTrue(item["sources"], item["id"])
                self.assertIn(item["confidence"], ("HIGH", "MEDIUM"))
        studies = [s for s in indicator_catalog() if s["section"] in (creators.NT, creators.UT)]
        self.assertGreaterEqual(len(studies), 8)

    def test_fit_line_never_crosses(self):
        ys = [10, 12, 11, 15, 13, 14, 18, 16, 17, 20]
        for upper in (True, False):
            slope, base = creators.fit_line(ys, upper)
            for x, y in enumerate(ys):
                line = base + slope * x
                if upper:
                    self.assertGreaterEqual(line + 1e-9, y)
                else:
                    self.assertLessEqual(line - 1e-9, y)

    def test_directional_change_confirms_swings(self):
        c = [100, 104, 108, 112, 106, 101, 96, 99, 103, 108, 113]
        state, pivots = creators.directional_change(c, c, c, 0.05)
        kinds = [p[3] for p in pivots]
        self.assertEqual(kinds, [1, -1])
        self.assertEqual(pivots[0][1], 3)  # top at 112
        self.assertEqual(pivots[1][1], 6)  # bottom at 96
        self.assertEqual(state[-1], 1)

    def test_inverse_head_and_shoulders_is_found(self):
        anchors = [100, 90, 96, 80, 96, 90, 100, 104]
        prices = []
        for a, b in zip(anchors, anchors[1:]):
            prices += [a + (b - a) * k / 6 for k in range(6)]
        prices.append(anchors[-1])
        found = creators._inverse_head_shoulders(prices, prices, prices, 2)
        self.assertTrue(found)
        self.assertAlmostEqual(found[0]["head"], 80)

    def test_jacobi_eigen(self):
        values, vecs = creators._jacobi_eigen([[2.0, 1.0], [1.0, 2.0]])
        self.assertEqual(sorted(round(v, 6) for v in values), [1.0, 3.0])
        for j in range(2):
            norm = math.sqrt(sum(vecs[i][j] ** 2 for i in range(2)))
            self.assertAlmostEqual(norm, 1.0, places=6)

    def test_market_proxy_aligns(self):
        rets = market.aligned_returns(list(self.frame.ts))
        self.assertEqual(len(rets), len(self.frame))
        self.assertGreater(sum(1 for r in rets if r == r), len(rets) * 0.9)
        level = market.aligned_close(list(self.frame.ts))
        self.assertEqual(len(level), len(self.frame))

    def test_every_creator_strategy_trades_only_long_or_flat(self):
        for item in [s for s in strategy_catalog() if s.get("creator")]:
            with self.subTest(strategy=item["id"]):
                pos = signal(item["id"], self.frame, {}).tolist()
                values = {x for x in pos if x == x}
                self.assertTrue(values <= {0.0, 1.0}, values)
                self.assertIn(0.0, values)

    def test_creator_studies_have_latest_values(self):
        for item in [s for s in indicator_catalog() if s["section"] in (creators.NT, creators.UT)]:
            with self.subTest(study=item["id"]):
                out = compute(item["id"], self.frame, {})
                for key, values in out["series"].items():
                    last = values.tolist()[-1]
                    self.assertTrue(isinstance(last, float) and math.isfinite(last), f"{item['id']}.{key}")


if __name__ == "__main__":
    unittest.main()
