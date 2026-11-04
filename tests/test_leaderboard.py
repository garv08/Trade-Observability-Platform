"""Offline checks for NSE/BSE indices and the all-strategy leaderboard."""

from __future__ import annotations

import unittest
from datetime import date

from tests.support import temp_dir, use_temp_store
from top import indices, leaderboard, market, store

NSE_INDEX = (
    "Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,"
    "Turnover (Rs. Cr.),P/E,P/B,Div Yield\n"
    "Nifty 50,30-10-2026,22964.5,23118.1,22905.1,23053.1,116.35,.51,328562872,29216.03,19.3,2.83,1.42\n"
    "Nifty Bank,30-10-2026,50000,50500,49800,50250,250,.5,-,-,15,2.5,1\n"
    "India VIX,30-10-2026,-,-,-,14.2,0.1,.7,-,-,-,-,-\n"
)
BSE_INDEX = (
    "IndexCode,IndexID,IndexName,PreviousClose,OpenPrice,HighPrice,LowPrice,ClosePrice,52weeksHigh,52weeksLow,Filler1,Filler2,Filler3,Filler4\n"
    "1,SENSEX,BSE SENSEX,74151.04,74199.69,74742.59,74082.03,74459.53,86159.02,71292.88,,,,\n"
    "2,BSE100,BSE 100,24443.83,24455.51,24574.90,24369.64,24479.83,27621.72,23200,,,,\n"
)


class IndexParserTests(unittest.TestCase):
    def test_nse(self):
        rows = {r["symbol"]: r for r in indices.parse_nse_index(NSE_INDEX)}
        self.assertEqual(set(rows), {"IDX:NIFTY50", "IDX:NIFTYBANK", "IDX:INDIAVIX"})
        self.assertEqual(rows["IDX:NIFTY50"]["close"], 23053.1)
        self.assertEqual(rows["IDX:NIFTY50"]["volume"], 328562872)
        vix = rows["IDX:INDIAVIX"]
        self.assertEqual((vix["open"], vix["high"], vix["low"]), (14.2, 14.2, 14.2))

    def test_bse(self):
        rows = indices.parse_bse_index(BSE_INDEX)
        self.assertEqual([r["symbol"] for r in rows], ["IDX:BSE:SENSEX", "IDX:BSE:BSE100"])
        self.assertEqual(rows[0]["name"], "BSE SENSEX")

    def test_rejects_holiday_pages(self):
        with self.assertRaises(indices.Missing):
            indices.parse_nse_index("<html>holiday</html>")
        with self.assertRaises(indices.Missing):
            indices.parse_bse_index("<html>not found</html>")


class IndexSyncTests(unittest.TestCase):
    def setUp(self):
        use_temp_store()
        self.saved = (indices.fetch_nse_index, indices.fetch_bse_index, indices.PAUSE)
        indices.PAUSE = 0

        def nse(day):
            if day.weekday() == 0:
                raise indices.Missing("holiday")
            return indices.parse_nse_index(NSE_INDEX)

        def bse(day):
            if day < date(2026, 10, 20):
                raise indices.Missing("too old")
            return indices.parse_bse_index(BSE_INDEX)

        indices.fetch_nse_index, indices.fetch_bse_index = nse, bse

    def tearDown(self):
        indices.fetch_nse_index, indices.fetch_bse_index, indices.PAUSE = self.saved

    def test_sync_and_resume(self):
        out = indices.sync_indices(years=0, today=date(2026, 10, 30))
        self.assertGreater(out["nse_bars"], 0)
        self.assertGreater(out["bse_bars"], 0)
        with store.session() as con:
            kinds = dict(con.execute("SELECT universe, COUNT(*) FROM symbols WHERE kind = 'index' GROUP BY 1").fetchall())
            self.assertEqual(kinds, {"nse_index": 3, "bse_index": 2})
            self.assertEqual(con.execute("SELECT COUNT(*) FROM adjustments").fetchone()[0], 0)
        again = indices.sync_indices(years=0, today=date(2026, 10, 30))
        self.assertEqual(again["nse_bars"] + again["bse_bars"], 0)


class FastMetricsTests(unittest.TestCase):
    def test_metrics_match_full_backtest_for_every_strategy(self):
        from tests.support import synthetic_rows
        from top.backtest import metrics, run
        from top.indicators import Frame
        from top.strategies import STRATEGIES, signal

        market.pin({})
        try:
            for symbol in ("INFY", "TCS"):
                rows = synthetic_rows(symbol)
                frame = Frame([r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows], [r[5] for r in rows], [r[6] for r in rows], [r[7] for r in rows])
                for item in STRATEGIES:
                    position = signal(item["id"], frame, {})
                    slow = run(frame.ts, frame.o, frame.h, frame.l, frame.c, position)["metrics"]
                    fast = metrics(frame.o, frame.c, position)
                    with self.subTest(symbol=symbol, strategy=item["id"]):
                        self.assertEqual(set(fast), set(slow))
                        for key, value in slow.items():
                            if value is None:
                                self.assertIsNone(fast[key], key)
                            else:
                                self.assertAlmostEqual(fast[key], value, delta=0.011, msg=key)
        finally:
            market.pin(None)


class SharpeStatsTests(unittest.TestCase):
    def test_normal_functions(self):
        for p, z in ((0.5, 0.0), (0.975, 1.959964), (0.05, -1.644854), (0.001, -3.090232)):
            self.assertAlmostEqual(leaderboard.norm_ppf(p), z, places=5)
            self.assertAlmostEqual(leaderboard.norm_cdf(z), p, places=5)

    def test_expected_max_sharpe_grows_with_trials(self):
        few, many = leaderboard.expected_max_sharpe(0.02, 10), leaderboard.expected_max_sharpe(0.02, 88)
        self.assertGreater(many, few)
        self.assertGreater(few, 0)
        self.assertEqual(leaderboard.expected_max_sharpe(0.02, 1), 0.0)


class RatioTests(unittest.TestCase):
    def test_drawdown_floor(self):
        self.assertAlmostEqual(leaderboard.ratio_of(30.0, -15.0), 2.0)
        self.assertAlmostEqual(leaderboard.ratio_of(40.0, -0.1), 8.0)
        self.assertIsNone(leaderboard.ratio_of(None, -10.0))


class DataQualityTests(unittest.TestCase):
    def test_gate(self):
        from tests.support import business_days

        days = business_days(date(2022, 1, 3), 300)
        self.assertIsNone(leaderboard.data_problem(days, [100 + i * 0.1 for i in range(300)]))
        jump = [100.0] * 150 + [260.0] * 150
        self.assertIn("jump", leaderboard.data_problem(days, jump))
        crash = [100.0] * 150 + [40.0] * 150
        self.assertIn("jump", leaderboard.data_problem(days, crash))
        sparse = days[::3]
        self.assertIn("thin", leaderboard.data_problem(sparse, [100.0] * len(sparse)))


class RunRobustnessTests(unittest.TestCase):
    def test_falls_back_to_in_process_when_workers_cannot_start(self):
        use_temp_store()
        real = leaderboard.multiprocessing.get_context

        def broken(_method):
            raise OSError("spawn is not available here")

        leaderboard.multiprocessing.get_context = broken
        try:
            out = leaderboard.run_all(workers=2, limit=1)
        finally:
            leaderboard.multiprocessing.get_context = real
        self.assertFalse(out["running"])
        self.assertEqual(out["done"], 1)
        self.assertEqual(out["workers"], 1)

    def test_empty_store_explains_itself(self):

        store.DB_PATH = temp_dir("top-empty-") / "empty.duckdb"
        store._schema_ready = False
        out = leaderboard.run_all(workers=1)
        self.assertFalse(out["running"])
        self.assertIn("Sync history", out["message"])

    def test_dead_run_thread_does_not_stay_running(self):
        import threading

        thread = threading.Thread(target=lambda: None)
        thread.start()
        thread.join()
        leaderboard._runner = thread
        leaderboard._set(running=True)
        try:
            self.assertFalse(leaderboard.status()["running"])
        finally:
            leaderboard._runner = None
            leaderboard._set(running=False)


class LeaderboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        cls.result = leaderboard.run_all(workers=1, limit=2)

    def test_non_price_indices_are_excluded(self):
        from tests.support import synthetic_rows

        with store.session() as con:
            for symbol, name in (("IDX:NIFTY50DIVIDENDPOINTS", "Nifty50 Dividend Points"), ("IDX:INDIAVIX", "India VIX"), ("IDX:NIFTYBANK", "Nifty Bank")):
                con.execute("INSERT OR REPLACE INTO symbols (symbol, name, kind, universe, exchange) VALUES (?, ?, 'index', 'nse_index', 'NSE')", [symbol, name])
                store.replace_bars(con, symbol, [(symbol, *row[1:]) for row in synthetic_rows("INFY")])
            todo, _, _ = leaderboard.members(con, force=True)
        todo = [symbol for symbol, _ in todo]
        self.assertIn("IDX:NIFTYBANK", todo)
        self.assertNotIn("IDX:NIFTY50DIVIDENDPOINTS", todo)
        self.assertNotIn("IDX:INDIAVIX", todo)

    def test_computed_and_resumable(self):
        self.assertEqual(self.result["done"], 2)
        with store.session() as con:
            todo, current, eligible = leaderboard.members(con)
            self.assertEqual(current, 2)
            self.assertEqual(len(todo), eligible - 2)
            n = con.execute("SELECT COUNT(DISTINCT strategy) FROM leaderboard").fetchone()[0]
        self.assertGreater(n, 60)

    def test_new_strategies_are_added_without_recomputing(self):
        with store.session() as con:
            symbol = con.execute("SELECT MIN(symbol) FROM leaderboard_done WHERE strategies > 0").fetchone()[0]
            before = dict(con.execute("SELECT strategy, computed_at FROM leaderboard WHERE symbol = ?", [symbol]).fetchall())
            # Pretend two strategies were added to the catalogue after this script was computed.
            gone = sorted(before)[:2]
            ids = ",".join(sorted(set(before) - set(gone)))
            con.execute("DELETE FROM leaderboard WHERE symbol = ? AND strategy IN (?, ?)", [symbol, *gone])
            con.execute("UPDATE leaderboard_done SET ids = ? WHERE symbol = ?", [ids, symbol])
            todo, _, _ = leaderboard.members(con)
        self.assertIn((symbol, tuple(gone)), todo)
        leaderboard.run_all(workers=1, limit=1)
        with store.session() as con:
            after = dict(con.execute("SELECT strategy, computed_at FROM leaderboard WHERE symbol = ?", [symbol]).fetchall())
            stored = con.execute("SELECT ids, strategies FROM leaderboard_done WHERE symbol = ?", [symbol]).fetchone()
            todo, _, _ = leaderboard.members(con)
        self.assertEqual(set(after), set(before))
        untouched = [s for s in before if s not in gone]
        self.assertTrue(all(after[s] == before[s] for s in untouched))
        self.assertEqual(stored[1], len(after))
        self.assertTrue(set(gone) <= set(stored[0].split(",")))
        self.assertNotIn(symbol, [s for s, _ in todo])

    def test_years_are_tested_years(self):
        with store.session() as con:
            bars = con.execute("SELECT COUNT(*) FROM bars WHERE symbol = (SELECT MIN(symbol) FROM leaderboard)").fetchone()[0]
            years = dict(con.execute("SELECT strategy, years FROM leaderboard WHERE symbol = (SELECT MIN(symbol) FROM leaderboard)").fetchall())
        self.assertLessEqual(years["above_sma200"], round((bars - 199) / 252, 2))
        self.assertGreater(max(years.values()), years["above_sma200"])

    def test_strategy_ranking_and_results(self):

        with store.session() as con:
            leaderboard.refresh_liquidity(con)
            ranked = leaderboard.strategy_ranking(con, min_trades=0, min_years=0, min_value=0, min_scripts=1)
            self.assertGreater(len(ranked), 60)
            values = [r["median_return_dd"] for r in ranked]
            self.assertEqual(values, sorted(values, reverse=True))
            self.assertEqual([r["rank"] for r in ranked], list(range(1, len(ranked) + 1)))
            top = ranked[0]
            per_script = [ret / max(abs(dd), leaderboard.DD_FLOOR) for ret, dd in con.execute(
                "SELECT total_return_pct, max_dd_pct FROM leaderboard WHERE strategy = ?", [top["strategy"]]).fetchall()]
            per_script.sort()
            mid = len(per_script) // 2
            median = per_script[mid] if len(per_script) % 2 else (per_script[mid - 1] + per_script[mid]) / 2
            self.assertAlmostEqual(top["median_return_dd"], median, places=3)
            self.assertEqual(top["scripts"], len(per_script))
            self.assertEqual(leaderboard.strategy_ranking(con, min_scripts=10_000), [])
            folder = temp_dir("top-results-")
            written = leaderboard.write_results(con, folder)
        self.assertEqual(set(written), {"leaderboard-cagr15.csv", "leaderboard-best-per-script.csv", "strategy-ranking-return-dd.csv"})
        header = (folder / "strategy-ranking-return-dd.csv").read_text().splitlines()[0]
        self.assertTrue(header.startswith("rank,strategy,strategy_name,section,creator,scripts,median_return_dd"))

    def test_ranking_and_filters(self):
        with store.session() as con:
            out = leaderboard.query(con, min_cagr=None, min_trades=0, limit=1000)
            rows = out["rows"]
            self.assertTrue(rows)
            ratios = [r["ratio"] for r in rows]
            self.assertEqual(ratios, sorted(ratios, reverse=True))
            for r in rows[:20]:
                self.assertAlmostEqual(r["ratio"], r["cagr_pct"] / max(abs(r["max_dd_pct"]), leaderboard.DD_FLOOR), places=3)
            above = leaderboard.query(con, min_cagr=15, min_trades=0, limit=1000)
            self.assertTrue(all(r["cagr_pct"] > 15 for r in above["rows"]))
            by_return = leaderboard.query(con, min_cagr=None, min_trades=0, sort="return_dd", limit=1000)["rows"]
            values = [r["return_dd"] for r in by_return]
            self.assertEqual(values, sorted(values, reverse=True))
            for r in by_return[:20]:
                self.assertAlmostEqual(r["return_dd"], r["total_return_pct"] / max(abs(r["max_dd_pct"]), leaderboard.DD_FLOOR), places=3)
            best_return = leaderboard.query(con, min_cagr=None, min_trades=0, sort="return_dd", best=True, limit=1000)["rows"]
            for r in best_return:
                mine = [x["return_dd"] for x in by_return if x["symbol"] == r["symbol"]]
                self.assertEqual(r["return_dd"], max(mine))
            best = leaderboard.query(con, min_cagr=None, min_trades=0, best=True, limit=1000)
            self.assertEqual(len({r["symbol"] for r in best["rows"]}), len(best["rows"]))
            self.assertLessEqual(len(best["rows"]), 2)
            import io

            buffer = io.StringIO()
            n = leaderboard.export_csv(con, buffer, min_cagr=None, min_trades=0)
            lines = buffer.getvalue().splitlines()
            self.assertEqual(n, out["total"])
            self.assertEqual(len(lines), n + 1)
            self.assertTrue(lines[1].startswith(f"1,{rows[0]['symbol']},"))
            leaderboard.refresh_liquidity(con)
            leaderboard.refresh_trials(con)
            with_p = leaderboard.query(con, min_cagr=None, min_trades=0, limit=1000)["rows"]
            for r in with_p:
                if r["sharpe"] is not None:
                    self.assertTrue(0 <= r["psr_pct"] <= 100 and 0 <= r["dsr_pct"] <= 100)
                    self.assertLessEqual(r["dsr_pct"], r["psr_pct"] + 1e-9)
            strict = leaderboard.query(con, min_cagr=None, min_trades=0, min_dsr=95, limit=1000)
            self.assertTrue(all(r["dsr_pct"] >= 95 - 0.05 for r in strict["rows"]))
            self.assertLessEqual(strict["total"], len(with_p))
            liquid = leaderboard.query(con, min_cagr=None, min_trades=0, min_value=1, limit=1000)
            self.assertEqual(liquid["total"], out["total"])
            self.assertTrue(all(r["median_value_lakh"] > 1 for r in liquid["rows"]))
            none = leaderboard.query(con, min_cagr=None, min_trades=0, min_value=1e9, limit=1000)
            self.assertEqual(none["total"], 0)
            one = leaderboard.query(con, min_cagr=None, min_trades=0, strategy=rows[0]["strategy"], limit=1000)
            self.assertTrue(all(r["strategy"] == rows[0]["strategy"] for r in one["rows"]))


if __name__ == "__main__":
    unittest.main()
