"""Offline checks for the X research digest features: strategies, sizing, robustness, markets, portfolio, delivery."""

from __future__ import annotations

import math
import unittest
from datetime import date

from tests.support import business_days, synthetic_rows, use_temp_store
from top import delivery, markets, portfolio, research, store
from top.backtest import kelly_fraction, run
from top.indicators import Frame
from top.robust import grid, monte_carlo, walk_forward
from top.strategies import catalog, signal

DAYS = 800


def _frame(symbol="INFY", count=DAYS):
    rows = synthetic_rows(symbol, count)
    return Frame([r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows], [r[5] for r in rows], [r[6] for r in rows], [r[7] for r in rows])


def seed_market():
    """Add BSE group A/B stocks (one with a 2:1 split), Nifty 50 and two sector indices, and delivery rows."""
    with store.session() as con:
        for k in range(12):
            symbol = f"BSE:S{k:02d}"
            con.execute(
                "INSERT INTO symbols (symbol, name, sector, exchange, kind, universe, code, isin, grp) VALUES (?, ?, 'BSE group A', 'BSE', 'stock', 'bse', ?, ?, ?)",
                [symbol, f"Stock {k}", f"5000{k:02d}", f"INE{k:03d}A01011", "A" if k < 8 else "B"],
            )
            rows = [(symbol, *row[1:]) for row in synthetic_rows(f"stock{k}", DAYS)]
            if k == 0:
                # Unadjusted 2:1 split half-way: raw prices halve from the ex-date.
                ex = rows[DAYS // 2][2]
                rows = [r if r[2] < ex else (r[0], r[1], r[2], r[3] / 2, r[4] / 2, r[5] / 2, r[6] / 2, r[7] * 2) for r in rows]
                con.execute("INSERT INTO adjustments VALUES (?, ?, 2.0, 'nse_ca', 'split 2:1')", [symbol, ex])
            store.replace_bars(con, symbol, rows)
        for symbol, name in (("IDX:NIFTY50", "Nifty 50"), ("IDX:NIFTYIT", "Nifty IT"), ("IDX:NIFTYBANK", "Nifty Bank")):
            con.execute("INSERT INTO symbols (symbol, name, sector, exchange, kind, universe) VALUES (?, ?, 'NSE index', 'NSE', 'index', 'nse_index')", [symbol, name])
            store.replace_bars(con, symbol, [(symbol, *row[1:]) for row in synthetic_rows(name, DAYS)])
        delivery.ensure_tables(con)
        days = [r[2] for r in synthetic_rows("x", DAYS)]
        con.executemany("INSERT INTO delivery VALUES ('BSE:S01', ?, 1000, ?, ?)", [(d, 300 + i % 50, 30.0 + i % 5) for i, d in enumerate(days)])
        # A delivery surge on the last day, together with a volume spike.
        con.execute("UPDATE delivery SET pct = 90 WHERE symbol = 'BSE:S01' AND ts = ?", [days[-1]])
        con.execute("UPDATE bars SET volume = volume * 10 WHERE symbol = 'BSE:S01' AND ts = ?", [days[-1]])


class ResearchStrategyTests(unittest.TestCase):
    def test_new_strategies_registered_with_sources(self):
        ids = {item["id"]: item for item in catalog()}
        for sid in ("tsmom_12m", "kalman_trend", "turn_of_month", "hurst_route"):
            self.assertIn(sid, ids)
            self.assertTrue(ids[sid].get("sources"))

    def test_signals_are_causal(self):
        """Changing future prices must not change past positions."""
        frame = _frame()
        cut = 600
        for sid in ("tsmom_12m", "kalman_trend", "hurst_route"):
            full = signal(sid, frame, {}).tolist()
            changed = _frame()
            for i in range(cut + 1, len(changed)):
                changed.c[i] = changed.c[i] * 1.5
                changed.o[i] = changed.o[i] * 1.5
            again = signal(sid, changed, {}).tolist()
            same = [a == b or (a != a and b != b) for a, b in zip(full[:cut + 1], again[:cut + 1])]
            self.assertTrue(all(same), sid)

    def test_turn_of_month_window(self):
        ts = business_days(date(2024, 1, 1), 70)
        marks = research.month_windows(ts, before=3, after=2)
        # The signal on bar i means "be long at bar i + 1's open", so check the bars it puts us in.
        held = {ts[i + 1] for i in range(len(ts) - 1) if marks[i] == 1.0}
        self.assertIn("2024-01-31", held)
        self.assertIn("2024-02-01", held)
        self.assertIn("2024-02-02", held)
        self.assertNotIn("2024-02-05", held)
        self.assertNotIn("2024-01-15", held)

    def test_hurst_and_kalman(self):
        trend = [100 * math.exp(0.002 * i) for i in range(400)]
        level = research.kalman_level(trend)
        self.assertLess(abs(level[-1] / trend[-1] - 1), 0.05)
        h = research.hurst_vr(_frame().c, 120)
        finite = [x for x in h if x == x]
        self.assertTrue(finite and all(0 < x < 1.2 for x in finite))


class SizingTests(unittest.TestCase):
    def test_kelly_fraction(self):
        self.assertAlmostEqual(kelly_fraction([10, 10, -5, 10]), 0.75 - 0.25 / 2, places=6)
        self.assertIsNone(kelly_fraction([1, 2, 3]))

    def test_sizing_modes(self):
        frame = _frame()
        position = signal("sma_cross", frame, {})
        full = run(frame.ts, frame.o, frame.h, frame.l, frame.c, position)
        vol = run(frame.ts, frame.o, frame.h, frame.l, frame.c, position, sizing="vol_target", target_vol=5)
        kelly = run(frame.ts, frame.o, frame.h, frame.l, frame.c, position, sizing="half_kelly")
        self.assertEqual(full["metrics"]["avg_position_pct"], 100.0)
        self.assertLess(vol["metrics"]["avg_position_pct"], 100.0)
        self.assertLessEqual(kelly["metrics"]["avg_position_pct"], 50.0)
        self.assertEqual(len(full["trades"]), len(vol["trades"]))
        # Smaller positions mean smaller drawdowns on the same signals.
        self.assertGreaterEqual(vol["metrics"]["max_drawdown_pct"], full["metrics"]["max_drawdown_pct"])
        self.assertIn("volatility", vol["methodology"])


class RobustnessTests(unittest.TestCase):
    def test_monte_carlo(self):
        trades = [{"return_pct": r, "open": False} for r in (5, -3, 8, -6, 2, -1, 4, -7, 6, 1)]
        out = monte_carlo(trades, runs=500)
        self.assertEqual(out["trades"], 10)
        dd = out["max_dd_pct"]
        self.assertLessEqual(dd["p5"], dd["p50"])
        self.assertLessEqual(dd["p50"], dd["p95"])
        self.assertEqual(monte_carlo(trades[:3])["runs"], 0)

    def test_walk_forward(self):
        frame = _frame(count=900)
        spec = next(s for s in catalog() if s["id"] == "sma_cross")
        out = walk_forward(frame, spec, signal, {})
        self.assertTrue(out["ok"])
        self.assertEqual(out["param"]["key"], "fast")
        self.assertTrue(out["years"])
        self.assertIn(out["verdict"], ("stable", "unstable"))
        self.assertTrue(all(y["value"] in out["param"]["grid"] for y in out["years"]))
        no_params = next(s for s in catalog() if not s["params"])
        self.assertFalse(walk_forward(frame, no_params, signal, {})["ok"])

    def test_grid_respects_bounds(self):
        self.assertEqual(grid({"min": 5, "max": 30, "step": 1}, 20), [10, 15, 20, 25, 30])
        self.assertEqual(grid({"min": 18, "max": 22, "step": 1}, 20), [18, 20, 22])


class MarketsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        seed_market()

    def test_adjusted_sql_matches_load_bars(self):
        with store.session() as con:
            ref = {b["time"]: b["close"] for b in store.load_bars(con, "BSE:S00")}
            got = con.execute(f"SELECT ts, close FROM ({markets.adjusted_sql('s.symbol = ' + chr(39) + 'BSE:S00' + chr(39))})").fetchall()
        self.assertEqual(len(got), len(ref))
        self.assertLess(max(abs(c / ref[str(t)] - 1) for t, c in got), 1e-12)

    def test_breadth(self):
        with store.session() as con:
            rows = markets.breadth(con)
        self.assertEqual(len(rows), DAYS)
        last = rows[-1]
        self.assertEqual(last["stocks"], 12)
        self.assertTrue(0 <= last["pct_above200"] <= 100)
        self.assertEqual(last["advances"] + last["declines"] <= 12, True)
        # The 2:1 split must not show up as a crash: no day has all 12 names at a new low because of it.
        self.assertTrue(all(r["new_lows"] < 12 for r in rows))

    def test_regime_and_sectors(self):
        with store.session() as con:
            reg = markets.regime(con)
            sectors = markets.sector_rotation(con)
        self.assertIn(reg["latest"]["state"], ("calm", "normal", "stressed"))
        states = {r["state"] for r in reg["series"] if r["state"]}
        self.assertTrue(states <= {"calm", "normal", "stressed"} and len(states) >= 2)
        self.assertEqual({s["symbol"] for s in sectors}, {"IDX:NIFTYIT", "IDX:NIFTYBANK"})
        self.assertTrue(all(s.get("quadrant") in ("Leading", "Weakening", "Improving", "Lagging") for s in sectors))

    def test_scans(self):
        with store.session() as con:
            counts = markets.scan_counts(con, min_value=0)
            surge = markets.scan(con, "delivery_surge", min_value=0)
            for name in markets.SCANS:
                out = markets.scan(con, name, min_value=0)
                self.assertEqual(out["count"], counts[name], name)
        self.assertEqual([r["symbol"] for r in surge["rows"]], ["BSE:S01"])
        with self.assertRaises(ValueError):
            with store.session() as con:
                markets.scan(con, "nope")


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        seed_market()

    def test_month_ends(self):
        dates = business_days(date(2024, 1, 1), 70)
        ends = [dates[i] for i in portfolio.month_ends(dates)]
        self.assertEqual(ends, ["2024-01-31", "2024-02-29", "2024-03-29"])  # April is unfinished, so excluded

    def test_momentum_nifty50(self):
        with store.session() as con:
            out = portfolio.run(con, "momentum_12_1", universe="nifty50", top_n=5, sweep=True)
        m = out["metrics"]
        self.assertEqual(out["members"], 50)
        self.assertGreater(m["rebalances"], 10)
        self.assertEqual(m["avg_holdings"], 5.0)
        self.assertEqual(len(out["holdings"]), 5)
        self.assertTrue(out["benchmark"])
        self.assertLessEqual(max(p["value"] for p in out["underwater"]), 0)
        self.assertEqual(out["sweep"][0]["top_n"], 1)
        # Trades happen at the open after the ranking close.
        for r in out["rebalances"]:
            self.assertGreater(r["traded"], r["decided"])
            self.assertGreaterEqual(r["cash_pct"], 0)

    def test_no_lookahead(self):
        """Holdings chosen at a month-end must not change if later prices change."""
        with store.session() as con:
            panel = portfolio.load_panel(con, "nifty50")
        first = portfolio.simulate(panel, "momentum_12_1", top_n=5)
        cut = portfolio.month_ends(panel["dates"])[-3]
        changed = {**panel, "close": {s: a[:] for s, a in panel["close"].items()}, "open": {s: a[:] for s, a in panel["open"].items()}}
        for s in panel["symbols"]:
            for i in range(cut + 1, len(panel["dates"])):
                changed["close"][s][i] = changed["close"][s][i] * (3 if s < "M" else 0.3)
                changed["open"][s][i] = changed["open"][s][i] * (3 if s < "M" else 0.3)
        second = portfolio.simulate(changed, "momentum_12_1", top_n=5)
        decided = panel["dates"][cut]
        a = [r["holdings"] for r in first["rebalances"] if r["decided"] <= decided]
        b = [r["holdings"] for r in second["rebalances"] if r["decided"] <= decided]
        self.assertEqual(a, b)

    def test_other_strategies(self):
        with store.session() as con:
            low = portfolio.run(con, "low_vol", universe="bse_a", top_n=3, min_value_lakh=0)
            sectors = portfolio.run(con, "sector_rotation", top_n=1)
            etf = portfolio.run(con, "momentum_12_1", universe="bse_a", top_n=3, gate="market", min_value_lakh=0)
        self.assertEqual(low["members"], 8)
        self.assertEqual(sectors["members"], 2)
        self.assertTrue(all(len(r["holdings"]) <= 1 for r in sectors["rebalances"]))
        self.assertTrue(any(len(r["holdings"]) == 0 for r in etf["rebalances"]) or etf["metrics"]["rebalances"] > 0)
        with self.assertRaises(ValueError):
            with store.session() as con:
                portfolio.run(con, "etf_momentum")  # no ETFs in the test store


class DeliveryTests(unittest.TestCase):
    TEXT = (
        "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
        "20MICRONS, EQ, 30-Oct-2026, 168.09, 166.51, 166.79, 159.00, 161.57, 161.48, 161.92, 132501, 214.54, 3365, 60324, 45.53\n"
        "SOMEBOND, N1, 30-Oct-2026, 100, 100, 100, 100, 100, 100, 100, 10, 1, 1, 10, 100\n"
        "NIFTYBEES, EQ, 30-Oct-2026, 262, 262, 263, 261, 262, 262.89, 262, 100000, 262, 500, 40000, 40.00\n"
    )

    def test_parse(self):
        rows = delivery.parse_delivery(self.TEXT)
        self.assertEqual(rows, [("20MICRONS", 132501, 60324, 45.53), ("NIFTYBEES", 100000, 40000, 40.0)])
        with self.assertRaises(delivery.Missing):
            delivery.parse_delivery("<html>")

    def test_fii_dii(self):
        rows = delivery.parse_fii_dii([
            {"buyValue": "14988.48", "category": "DII", "date": "02-Nov-2026", "netValue": "-392.2", "sellValue": "15380.68"},
            {"buyValue": "16499.46", "category": "FII/FPI", "date": "02-Nov-2026", "netValue": "3114.68", "sellValue": "13384.78"},
            {"category": "junk", "date": "bad"},
        ])
        self.assertEqual(rows, [("2026-11-02", "DII", 14988.48, 15380.68, -392.2), ("2026-11-02", "FII", 16499.46, 13384.78, 3114.68)])

    def test_ticker_map(self):
        use_temp_store()
        with store.session() as con:
            store.ensure_schema(con)
            con.execute("INSERT INTO symbols (symbol, name, kind, universe, code, isin, exchange) VALUES ('BSE:ABC', 'Abc', 'stock', 'bse', '500001', 'INE001A01011', 'BSE')")
            con.execute("INSERT INTO symbols (symbol, name, kind, universe, code, exchange) VALUES ('NSE:NIFTYBEES', 'Bees', 'etf', 'nse_etf', 'NIFTYBEES', 'NSE')")
            con.execute("INSERT INTO symbols (symbol, name, kind, universe, code, isin, exchange) VALUES ('NSE:ABC', 'Abc', 'stock', 'nse', 'ABC', 'INE001A01011', 'NSE')")
            mapping = delivery.ticker_map(con, [{"ticker": "ABC", "isin": "INE001A01011", "series": "EQ"},
                                                {"ticker": "ZZZ", "isin": "INE999Z01011", "series": "EQ"}])
        self.assertEqual(sorted(mapping["ABC"]), ["BSE:ABC", "NSE:ABC"])
        self.assertEqual(mapping["NIFTYBEES"], ["NSE:NIFTYBEES"])
        self.assertEqual(mapping["INFY"], ["INFY"])
        self.assertNotIn("ZZZ", mapping)


if __name__ == "__main__":
    unittest.main()
