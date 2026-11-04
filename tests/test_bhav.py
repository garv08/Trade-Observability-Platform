"""Offline checks for BSE stocks and ETFs from exchange bhavcopies."""

from __future__ import annotations

import io
import json
import unittest
import urllib.parse
import zipfile
from datetime import date, timedelta

from tests.support import business_days, use_temp_store
from top import bhav, store

BSE_NEW = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,"
    "OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,"
    "TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2026-10-30,2026-10-30,CM,BSE,STK,500002,INE117A01022,ABB,A,,,,,ABB INDIA LIMITED,6486.80,6486.80,6386.00,6403.00,6403.00,6530.00,,6412.94,,,9368,60218127.00,2047,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,BSE,STK,532985,INF174KA1JD7,SENSEX1,B,,,,,KOTAK MAHINDRA MUTUAL FUND,81.00,82.10,80.90,82.00,82.00,81.24,,82.00,,,500,41000.00,10,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,BSE,STK,975001,INE001X07011,ABCNCD,F,,,,,ABC NCD,1000,1000,1000,1000,1000,1000,,1000,,,5,5000.00,1,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,BSE,STK,800001,IN0020230011,GSEC,G,,,,,GOVT SEC,100,100,100,100,100,100,,100,,,5,500.00,1,F1,1,,,,,\n"
)
BSE_OLD = (
    "SC_CODE,SC_NAME,SC_GROUP,SC_TYPE,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,NO_TRADES,NO_OF_SHRS,NET_TURNOV,TDCLOINDI\n"
    "500002,ABB LTD.    ,A ,Q,2125.00,2167.55,2030.00,2081.55,2081.55,2109.70,3062,27205,56941246.00,\n"
)
NSE_NEW = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,"
    "OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,"
    "TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2026-10-30,2026-10-30,CM,NSE,STK,1,INF204KB14I2,NIFTYBEES,EQ,,,,,NIP IND ETF NIFTY BEES,262,263,261,262.89,262.9,261.88,,262.89,,,100000,26289000,500,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,NSE,STK,2,INE002A01018,RELIANCE,EQ,,,,,RELIANCE INDUSTRIES,1150,1170,1145,1164.9,1165,1167.4,,1164.9,,,1,1,1,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,NSE,STK,3,INE736A01011,CDSL,EQ,,,,,CENTRAL DEPO SER (I) LTD,1500,1520,1490,1510,1510,1500,,1510,,,900,1359000,90,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,NSE,STK,4,INE111A01011,TFTSTOCK,BE,,,,,TRADE FOR TRADE LTD,50,51,49,50.5,50.5,50,,50.5,,,100,5050,9,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,NSE,STK,5,INE222A01011,SMEONE,SM,,,,,SME ONE LIMITED,80,82,79,81,81,80,,81,,,4000,324000,4,F1,1,,,,,\n"
    "2026-10-30,2026-10-30,CM,NSE,STK,6,INE333A08011,SOMENCD,N1,,,,,SOME NCD,1000,1000,1000,1000,1000,1000,,1000,,,5,5000,1,F1,1,,,,,\n"
)
NSE_OLD = (
    "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
    "NIFTYBEES,EQ,190,191,189,190.5,190.5,189.8,50000,9525000,01-NOV-2021,300,INF204KB14I2,\n"
)


def _zip(text):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("file.csv", text)
    return buffer.getvalue()


class ParserTests(unittest.TestCase):
    def test_bse_new_and_classification(self):
        rows = bhav.parse_bse_new(BSE_NEW)
        self.assertEqual(len(rows), 4)
        kinds = {r["ticker"]: bhav.classify_bse(r) for r in rows}
        self.assertEqual(kinds, {"ABB": "stock", "SENSEX1": "etf", "ABCNCD": None, "GSEC": None})
        self.assertEqual(rows[0]["code"], "500002")
        self.assertEqual(rows[0]["volume"], 9368)

    def test_bse_old_zip(self):
        rows = bhav.parse_bse_old(bhav._zip_text(_zip(BSE_OLD)))
        self.assertEqual(rows[0]["code"], "500002")
        self.assertEqual(rows[0]["group"], "A")
        self.assertAlmostEqual(rows[0]["close"], 2081.55)

    def test_nse_formats(self):
        new = bhav.parse_nse_new(bhav._zip_text(_zip(NSE_NEW)))
        old = bhav.parse_nse_old(bhav._zip_text(_zip(NSE_OLD)))
        self.assertEqual(new[0]["ticker"], "NIFTYBEES")
        self.assertEqual(old[0]["ticker"], "NIFTYBEES")
        self.assertEqual(old[0]["volume"], 50000)

    def test_holiday_pages_are_missing(self):
        with self.assertRaises(bhav.Missing):
            bhav.parse_bse_new("<!DOCTYPE html><html>")
        with self.assertRaises(bhav.Missing):
            bhav._zip_text(b"<!DOCTYPE html>")

    def test_listings(self):
        etfs = {"NIFTYBEES": {"name": "Nifty 50", "isin": "INF204KB14I2", "underlying": "EQUITY"}}
        listings = bhav.build_listings(bhav.parse_bse_new(BSE_NEW), bhav.parse_nse_new(bhav._zip_text(_zip(NSE_NEW))), etfs,
                                       skip_nse={"RELIANCE"})
        by_symbol = {x["symbol"]: x for x in listings}
        # Main-board NSE stocks (EQ/BE) are listed; SME (SM), debt, ETFs-as-stocks and the Nifty 50 ticker are not.
        self.assertEqual(set(by_symbol), {"BSE:ABB", "BSE:SENSEX1", "NSE:NIFTYBEES", "NSE:CDSL", "NSE:TFTSTOCK"})
        self.assertEqual(by_symbol["NSE:CDSL"]["universe"], "nse")
        self.assertEqual(by_symbol["NSE:CDSL"]["code"], "CDSL")
        self.assertEqual(by_symbol["NSE:CDSL"]["name"], "Central Depo Ser (I) Ltd")
        self.assertEqual(by_symbol["NSE:TFTSTOCK"]["grp"], "BE")
        self.assertEqual(by_symbol["BSE:ABB"]["universe"], "bse")
        self.assertEqual(by_symbol["BSE:SENSEX1"]["universe"], "bse_etf")
        self.assertEqual(by_symbol["NSE:NIFTYBEES"]["universe"], "nse_etf")

    def test_corporate_action_factors(self):
        cases = {
            "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share": 5.0,
            "Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share": 2.0,
            "Bonus 4:1": 5.0,
            "Bonus 1:2": 1.5,
            "Consolidation Of Shares From Re 1/- To Rs 10/-": 0.1,
            "Dividend - Rs 5 Per Share": None,
        }
        for subject, expected in cases.items():
            with self.subTest(subject=subject):
                got = bhav.action_factor(subject)
                self.assertEqual(got if expected is None else round(got, 6), expected)

    def test_gap_rule(self):
        self.assertEqual(bhav.gap_factor(1000, 505, 498), 2.0)
        self.assertEqual(bhav.gap_factor(9334.15, 954.5, 937.75), 10.0)
        self.assertAlmostEqual(bhav.gap_factor(10, 98, 101), 0.1)
        self.assertIsNone(bhav.gap_factor(1000, 900, 880))
        self.assertIsNone(bhav.gap_factor(1000, 520, 760))  # opened low but recovered: not a clean split


class NseStockTests(unittest.TestCase):
    def setUp(self):
        use_temp_store()
        self.saved = (bhav.fetch_nse, bhav.PAUSE)
        bhav.PAUSE = 0

    def tearDown(self):
        bhav.fetch_nse, bhav.PAUSE = self.saved

    def test_backfill_maps_by_ticker_then_isin(self):
        days = [date.fromisoformat(d) for d in business_days(date(2025, 3, 3), 10)]
        rename_day = days[5]

        def fake(day):
            if day == days[2]:
                raise bhav.Missing("holiday")
            # NEWNAME was called OLDNAME before rename_day; same ISIN.
            ticker = "NEWNAME" if day >= rename_day else "OLDNAME"
            return [
                {"ticker": ticker, "series": "EQ", "isin": "INE555A01011", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
                {"ticker": "SMEONE", "series": "SM", "isin": "INE222A01011", "open": 5, "high": 5, "low": 5, "close": 5, "volume": 1},
            ]

        bhav.fetch_nse = fake
        with store.session() as con:
            bhav.save_listings(con, [{"symbol": "NSE:NEWNAME", "name": "New Name Ltd", "sector": "NSE series EQ", "exchange": "NSE", "kind": "stock",
                                      "universe": "nse", "code": "NEWNAME", "isin": "INE555A01011", "grp": "EQ"}])
            maps = bhav._maps(con)
        stored = bhav.backfill_nse_stocks(days[0], days[-1], maps, today=date(2025, 6, 1))
        self.assertEqual(stored, 9)
        with store.session() as con:
            bars = store.load_bars(con, "NSE:NEWNAME")
            recorded = con.execute("SELECT COUNT(*) FROM bhav_days WHERE exchange = ?", [bhav.NSE_EQ_SOURCE]).fetchone()[0]
        self.assertEqual(len(bars), 9)  # history before the rename is kept through the ISIN
        self.assertEqual(recorded, 10)  # the holiday is recorded too, so it is not retried
        self.assertEqual(bhav.backfill_nse_stocks(days[0], days[-1], maps, today=date(2025, 6, 1)), 0)


class AdjustedStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_temp_store()
        days = [date.fromisoformat(d) for d in business_days(date(2025, 1, 1), 60)]
        cls.split_day = days[30]
        with store.session() as con:
            bhav.save_listings(con, [
                {"symbol": "BSE:TESTSPLIT", "name": "Test Split Ltd", "sector": "BSE group B", "exchange": "BSE", "kind": "stock", "universe": "bse", "code": "999001", "isin": "INE999Z01011", "grp": "B"},
                {"symbol": "BSE:TESTCA", "name": "Test Bonus Ltd", "sector": "BSE group A", "exchange": "BSE", "kind": "stock", "universe": "bse", "code": "999002", "isin": "INE998Z01012", "grp": "A"},
                {"symbol": "NSE:TESTETF", "name": "Test ETF", "sector": "EQUITY", "exchange": "NSE", "kind": "etf", "universe": "nse_etf", "code": "TESTETF", "isin": "INF999Z01019", "grp": "ETF"},
            ])
            for i, day in enumerate(days):
                after = day >= cls.split_day
                a = 500.0 + i if not after else (500.0 + i) / 5   # 5:1 split, found by the gap rule
                b = 800.0 + i if not after else (800.0 + i) / 2   # bonus 1:1, given by a corporate action
                bhav.insert_rows(con, day, [
                    ("BSE:TESTSPLIT", a, a * 1.01, a * 0.99, a, 1000 if not after else 5000),
                    ("BSE:TESTCA", b, b * 1.01, b * 0.99, b, 2000),
                    ("NSE:TESTETF", 100.0 + i * 0.1, 101.0, 99.0, 100.0 + i * 0.1, 300),
                ])
            bhav.save_corporate_actions(con, [{"symbol": "TESTCA", "isin": "INE998Z01020", "ex_date": cls.split_day, "factor": 2.0, "subject": "Bonus 1:1"}])
            cls.made = bhav.rebuild_adjustments(con)
            cls.adjustments = con.execute("SELECT symbol, ex_date, factor, source FROM adjustments ORDER BY symbol").fetchall()

    def test_adjustments_found(self):
        found = {(s, src): f for s, ex, f, src in self.adjustments}
        self.assertAlmostEqual(found[("BSE:TESTSPLIT", "gap")], 5.0)
        self.assertAlmostEqual(found[("BSE:TESTCA", "nse_ca")], 2.0)
        self.assertFalse(any(s == "BSE:TESTCA" and src == "gap" for s, _, _, src in self.adjustments), "gap rule must not double-count a known action")
        self.assertFalse(any(s == "NSE:TESTETF" for s, *_ in self.adjustments))

    def test_bars_are_back_adjusted(self):
        with store.session() as con:
            bars = store.load_bars(con, "BSE:TESTSPLIT")
        closes = [b["close"] for b in bars]
        jumps = [abs(b / a - 1) for a, b in zip(closes, closes[1:])]
        self.assertLess(max(jumps), 0.05, "no split gap left after adjustment")
        self.assertAlmostEqual(closes[-1], (500.0 + 59) / 5)
        self.assertEqual(bars[0]["volume"], 5000)  # 1000 shares × 5

    def test_list_symbols_and_coverage(self):
        with store.session() as con:
            rows = {r["symbol"]: r for r in store.list_symbols(con)}
            cov = store.coverage(con)
        self.assertEqual(rows["NSE:TESTETF"]["kind"], "etf")
        self.assertEqual(rows["BSE:TESTSPLIT"]["universe"], "bse")
        self.assertEqual(cov["symbols_with_bars"], 50)
        self.assertEqual(cov["universes"]["bse"]["symbols_with_bars"], 2)
        self.assertIn("BSE:TESTSPLIT", store.known_symbols())

    def test_api_serves_bse_and_scans_universes(self):
        import threading
        import urllib.request

        from top.server import build_server

        server = build_server("127.0.0.1", 0, auto_sync=False)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(base + "/api/bars?symbol=" + urllib.parse.quote("BSE:TESTSPLIT"), timeout=60) as response:
                payload = json.loads(response.read())
            self.assertEqual(len(payload["bars"]), 60)
            request = urllib.request.Request(base + "/api/scan", data=json.dumps({"strategy": "sma_cross", "universe": "bse"}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                scan = json.loads(response.read())
            self.assertEqual({r["symbol"] for r in scan["rows"]}, {"BSE:TESTSPLIT", "BSE:TESTCA"})
            request = urllib.request.Request(base + "/api/scan", data=json.dumps({"strategy": "sma_cross", "universe": "etf"}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                self.assertEqual([r["symbol"] for r in json.loads(response.read())["rows"]], ["NSE:TESTETF"])
            try:
                urllib.request.urlopen(base + "/api/fundamentals?symbol=" + urllib.parse.quote("NSE:TESTETF"), timeout=30)
                self.fail("ETF fundamentals should be refused")
            except urllib.error.HTTPError as error:
                self.assertIn("ETF", json.loads(error.read())["error"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
