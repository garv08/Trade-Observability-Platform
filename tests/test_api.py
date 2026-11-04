"""Integration checks: start the real HTTP server on a free port and call every route."""

from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from tests.support import use_temp_store
from top.server import build_server


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        cls.server = build_server("127.0.0.1", 0, auto_sync=False)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=60) as response:
                return response.status, response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers.get("Content-Type", "")

    def get_json(self, path):
        status, body, _ = self.get(path)
        return status, json.loads(body)

    def post(self, path, payload):
        request = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_static_files(self):
        for path, kind in (("/", "text/html"), ("/guide.html", "text/html"), ("/app.js", "javascript"), ("/styles.css", "text/css"),
                           ("/leaderboard.html", "text/html"), ("/leaderboard.js", "javascript"),
                           ("/markets.html", "text/html"), ("/markets.js", "javascript"), ("/portfolio.html", "text/html"),
                           ("/portfolio.js", "javascript"), ("/pages.css", "text/css"), ("/vendor/lightweight-charts.standalone.production.js", "javascript")):
            with self.subTest(path=path):
                status, body, ctype = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(kind, ctype)
                self.assertTrue(body)
        status, body, _ = self.get("/")
        self.assertIn(b"Trade Observability Platform", body)

    def test_static_types_ignore_the_os_registry(self):
        import mimetypes

        real = mimetypes.guess_type
        mimetypes.guess_type = lambda *args, **kwargs: ("text/plain", None)
        try:
            for path, kind in (("/styles.css", "text/css"), ("/leaderboard.js", "text/javascript"), ("/app.js", "text/javascript"),
                               ("/leaderboard.html", "text/html")):
                with self.subTest(path=path):
                    status, _, ctype = self.get(path)
                    self.assertEqual(status, 200)
                    self.assertTrue(ctype.startswith(kind), ctype)
        finally:
            mimetypes.guess_type = real

    def test_path_traversal_is_refused(self):
        for path in ("/../pyproject.toml", "/%2e%2e/top/server.py", "/vendor/../../server.py"):
            with self.subTest(path=path):
                status, _, _ = self.get(path)
                self.assertEqual(status, 404)

    def test_health_status_symbols(self):
        status, health = self.get_json("/api/health")
        self.assertEqual((status, health["ok"], health["universe"]), (200, True, 50))
        self.assertGreaterEqual(health["symbols"], 50)
        status, payload = self.get_json("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["coverage"]["symbols_with_bars"], 50)
        status, payload = self.get_json("/api/symbols")
        self.assertEqual(len(payload["symbols"]), 50)

    def test_bars_including_ampersand_symbol(self):
        status, payload = self.get_json("/api/bars?symbol=" + urllib.parse.quote("M&M"))
        self.assertEqual(status, 200)
        self.assertEqual(payload["symbol"], "M&M")
        self.assertGreater(len(payload["bars"]), 500)
        self.assertEqual(self.get_json("/api/bars?symbol=NOPE")[0], 404)

    def test_catalogs(self):
        status, payload = self.get_json("/api/indicators")
        self.assertEqual(payload["sections"][0], "Harmonics")
        self.assertGreaterEqual(payload["count"], 136)
        status, payload = self.get_json("/api/strategies")
        self.assertGreaterEqual(payload["count"], 71)

    def test_studies_with_harmonic_drawings(self):
        status, payload = self.post("/api/studies", {"symbol": "INFY", "studies": [{"id": "carney", "params": {}}, {"id": "macd", "params": {}}]})
        self.assertEqual(status, 200)
        carney, macd = payload["studies"]
        self.assertTrue(carney["drawings"])
        self.assertIsNotNone(macd["series"]["signal"][-1])

    def test_backtest_trend_scan(self):
        status, payload = self.post("/api/backtest", {"symbol": "TCS", "strategy": "sma_cross", "params": {}, "capital": 100000, "cost_bps": 5})
        self.assertEqual(status, 200)
        self.assertIn("total_return_pct", payload["metrics"])
        status, payload = self.post("/api/trend", {"symbol": "TCS"})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["rows"]), 30)
        status, payload = self.post("/api/scan", {"strategy": "harm_carney"})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["rows"]), 50)
        self.assertFalse([row for row in payload["rows"] if row.get("error")])
        self.assertEqual(self.post("/api/scan", {"strategy": "nope"})[0], 400)

    def test_explain(self):
        status, payload = self.post("/api/explain", {"symbol": "M&M", "studies": [{"id": "rsi", "params": {}}], "strategy": {"id": "supertrend", "params": {}}, "focus": "rsi"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["items"][0]["id"], "rsi")
        self.assertIn(payload["plan"]["bias"], ("Bullish", "Bearish", "Neutral"))
        self.assertIn("not investment advice", payload["disclaimer"].lower())

    def test_leaderboard_routes(self):
        status, payload = self.get_json("/api/leaderboard")
        self.assertEqual(status, 200)
        self.assertEqual(payload["rows"], [])
        self.assertIn("running", payload["status"])
        self.assertEqual(set(payload["universes"]), {"all", "nifty50", "index", "etf", "nse", "bse"})
        status, payload = self.get_json("/api/leaderboard?min_cagr=none&universe=bse&sort=cagr&best=1&q=bse")
        self.assertEqual(status, 200)
        status, payload = self.get_json("/api/leaderboard/status")
        self.assertFalse(payload["running"])
        status, payload = self.post("/api/leaderboard", {"action": "stop"})
        self.assertEqual(status, 200)
        status, payload = self.get_json("/api/leaderboard/strategies?min_trades=0&min_years=0&min_value=0&min_scripts=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["strategies"], [])
        status, body, ctype = self.get("/api/leaderboard/strategies.csv")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", ctype)
        self.assertTrue(body.decode().startswith("rank,strategy,"))
        status, body, ctype = self.get("/api/leaderboard.csv?min_cagr=none")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", ctype)
        self.assertTrue(body.decode().startswith("rank,symbol,name,universe"))

    def test_research_routes(self):
        status, payload = self.post("/api/backtest", {"symbol": "TCS", "strategy": "tsmom_12m", "sizing": "vol_target", "target_vol": 10})
        self.assertEqual(status, 200)
        self.assertEqual(payload["sizing"], "vol_target")
        self.assertIn("kelly_pct", payload["metrics"])
        self.assertIn("monte_carlo", payload)
        status, payload = self.post("/api/walkforward", {"symbol": "TCS", "strategy": "sma_cross"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, payload = self.post("/api/studies", {"symbol": "TCS", "studies": [{"id": "delivery_pct", "params": {}}, {"id": "market_regime", "params": {}}]})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["studies"]), 2)
        status, payload = self.get_json("/api/portfolio/strategies")
        self.assertEqual({s["id"] for s in payload["strategies"]}, {"momentum_12_1", "low_vol", "sector_rotation", "etf_momentum"})
        status, payload = self.post("/api/portfolio", {"strategy": "momentum_12_1", "universe": "nifty50", "top_n": 5})
        self.assertEqual(status, 200)
        self.assertEqual(payload["metrics"]["avg_holdings"], 5.0)
        status, payload = self.get_json("/api/markets/overview")
        self.assertEqual(status, 200)
        self.assertEqual(set(payload["counts"]), {s["name"] for s in payload["scans"]})
        status, payload = self.get_json("/api/markets/breadth")
        self.assertEqual(status, 200)
        status, payload = self.get_json("/api/markets/scan?name=bloodbath&min_value=0")
        self.assertEqual(status, 200)
        self.assertEqual(payload["scan"], "bloodbath")

    def test_verify_route(self):
        status, payload = self.get_json("/api/verify")
        self.assertEqual(status, 200)
        failed = [hook["name"] for hook in payload["hooks"] if not hook["ok"]]
        self.assertEqual(failed, [])

    @unittest.skipUnless(os.environ.get("TOP_NETWORK_TESTS") == "1", "set TOP_NETWORK_TESTS=1 to call Screener.in")
    def test_fundamentals_live(self):
        status, payload = self.get_json("/api/fundamentals?symbol=INFY")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ratios"])


if __name__ == "__main__":
    unittest.main()
