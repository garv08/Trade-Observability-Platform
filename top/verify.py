"""Named checks for the desk. In-process, so the API can run them without calling itself."""

from __future__ import annotations

from top.backtest import run as run_backtest
from top.fundamentals import parse_html
from top.harmonics import detect, zigzag
from top.indicators import Frame, catalog as indicator_catalog
from top.indicators import compute as compute_study
from top.store import coverage, ensure_schema, load_bars, session
from top.strategies import catalog as strategy_catalog
from top.strategies import signal
from top.universe import UNIVERSE


def _gartley_frame():
    # Drop into X, then a bullish Gartley, then a bounce so D is confirmed.
    anchors = [180, 100, 200, 138.2, 176.4, 121.4, 150]
    times, opens, highs, lows, closes = [], [], [], [], []
    cursor = 0
    for price in anchors:
        for _ in range(8):
            cursor += 1
            times.append(f"2020-{(cursor // 28) + 1:02d}-{(cursor % 28) + 1:02d}")
            opens.append(price)
            highs.append(price)
            lows.append(price)
            closes.append(price)
    return times, opens, highs, lows, closes


def run():
    hooks = []

    def check(name, ok, detail=""):
        hooks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    indicators = indicator_catalog()
    strategies = strategy_catalog()
    check("indicator catalog", len(indicators) >= 124, len(indicators))
    check("strategy catalog", len(strategies) >= 55, len(strategies))
    check("harmonic studies", sum(1 for item in indicators if item["section"] == "Harmonics") >= 12, "Carney set")
    check("harmonic strategies", sum(1 for item in strategies if item["section"] == "Harmonics") >= 12, "backtestable")
    check("trend reversal section", any(item["section"] == "Trend reversal" for item in strategies), "present")
    creator_counts = {handle: sum(1 for item in strategies if item.get("creator") == handle) for handle in ("@neurotrader888", "@UnbiasedTradingGoshawk")}
    check("YouTube creator strategies", all(count >= 4 for count in creator_counts.values()), ", ".join(f"{k} {v}" for k, v in creator_counts.items()))
    research = [item for item in strategies if item["section"] == "Quant research"]
    check("X research strategies", len(research) >= 4, f"{len(research)} ({', '.join(item['name'] for item in research)})")

    times, opens, highs, lows, closes = _gartley_frame()
    found = {name for event in detect(highs, lows, times, swing_pct=3, tolerance=0.05) for name in event["ids"]}
    check("synthetic Gartley", "gartley" in found, ",".join(sorted(found)) or "none")
    check("zigzag pivots", len(zigzag(highs, lows, 3)) >= 4, len(zigzag(highs, lows, 3)))

    sample = (
        '<ul id="top-ratios"><li class="flex flex-space-between"><span class="name">Stock P/E</span>'
        '<span class="nowrap value"><span class="number">19.2</span></span></li></ul>'
        '<div class="pros"><ul><li>Cash rich</li></ul></div><div class="cons"><ul><li>Low ROE</li></ul></div>'
    )
    parsed = parse_html("RELIANCE", sample, "https://www.screener.in/company/RELIANCE/consolidated/")
    check("fundamentals parser", parsed["ratios"][0]["label"] == "Stock P/E" and parsed["cons"] == ["Low ROE"], parsed["ratios"][0]["value"])

    with session() as con:
        ensure_schema(con)
        info = coverage(con)
        check("duckdb universe", info["symbols_with_bars"] == len(UNIVERSE), f"{info['symbols_with_bars']}/{len(UNIVERSE)}")
        thin = []
        for row in UNIVERSE:
            count = len(load_bars(con, row["symbol"]))
            if count < 50:
                thin.append(row["symbol"])
        check("every name has bars", not thin, ",".join(thin) or info["bars"])
        extended = {u: v["symbols_with_bars"] for u, v in info.get("universes", {}).items() if u != "nifty50"}
        adjusted = con.execute("SELECT COUNT(*) FROM adjustments").fetchone()[0]
        listed = sum(v.get("listed", 0) for u, v in info.get("universes", {}).items() if u != "nifty50")
        check(
            "BSE stocks and ETFs",
            listed == 0 or sum(extended.values()) > 0,
            ("not synced yet (Sync history or top-sync --bhav)" if listed == 0 else
             f"BSE {extended.get('bse', 0):,} · NSE ETFs {extended.get('nse_etf', 0)} · BSE ETFs {extended.get('bse_etf', 0)} · {adjusted} split/bonus adjustments"),
        )
        check(
            "NSE and BSE indices",
            True,
            (f"NSE {extended.get('nse_index', 0)} · BSE {extended.get('bse_index', 0)}" if extended.get("nse_index") or extended.get("bse_index")
             else "not synced yet (Sync history or top-sync --indices)"),
        )
        from top import delivery as delivery_mod, markets

        delivery_mod.ensure_tables(con)
        deliv = con.execute("SELECT COUNT(DISTINCT symbol), MAX(ts) FROM delivery").fetchone()
        fii = con.execute("SELECT COUNT(DISTINCT day) FROM fii_dii").fetchone()[0]
        check("delivery % and FII/DII", True,
              f"delivery for {deliv[0]:,} names to {deliv[1]} · FII/DII {fii} days" if deliv[0] else "not synced yet (Sync history or top-sync --delivery)")
        breadth_rows = markets.breadth(con)
        regime_now = markets.regime(con)["latest"]
        check("market breadth and regime", True,
              (f"{len(breadth_rows):,} days · {breadth_rows[-1]['pct_above200']}% above 200-day" if breadth_rows else "breadth needs BSE stocks")
              + (f" · Nifty {regime_now['state']}" if regime_now else " · regime needs Nifty 50 index"))
        from top import leaderboard

        board = leaderboard.query(con, min_cagr=None, min_trades=0, limit=1)["computed"]
        check("strategy leaderboard", True,
              f"{board['symbols']:,} scripts · {board['rows']:,} backtests" if board["rows"] else "not computed yet (Leaderboard page → Run backtests)")
        bars = load_bars(con, "RELIANCE")
    frame = Frame(
        [bar["time"] for bar in bars],
        [bar["open"] for bar in bars],
        [bar["high"] for bar in bars],
        [bar["low"] for bar in bars],
        [bar["close"] for bar in bars],
        [bar["volume"] for bar in bars],
    )
    bad_studies = []
    for item in indicators:
        try:
            compute_study(item["id"], frame, {})
        except Exception as exc:  # noqa: BLE001
            bad_studies.append(f"{item['id']}: {exc}")
    check("every indicator on RELIANCE", not bad_studies, "; ".join(bad_studies[:4]) or len(indicators))
    carney = compute_study("carney", frame, {})
    drawn = carney.get("drawings") or []
    from top.explain import explain as explain_selection

    reading = explain_selection(frame, "RELIANCE", [{"id": "rsi", "params": {}}, {"id": "macd", "params": {}}, {"id": "carney", "params": {}}], {"id": "sma_cross", "params": {}})
    blank = [item["title"] for item in reading["items"] if "not ready" in item["now"]]
    check(
        "interpretation and swing plan",
        reading["plan"].get("bias") in ("Bullish", "Bearish", "Neutral") and len(reading["items"]) == 4 and not blank and reading["plan"].get("base"),
        f"{reading['plan'].get('bias')} · {reading['plan'].get('setup')}" + (f" · blank: {', '.join(blank)}" if blank else ""),
    )
    check(
        "Carney patterns drawn on RELIANCE",
        bool(drawn) and all(len(item["legs"]) in (5, 6) for item in drawn),
        f"{len(drawn)} drawn, {len(carney.get('markers') or [])} marked",
    )
    bad_strategies = []
    for item in strategies:
        try:
            position = signal(item["id"], frame, {})
            run_backtest(frame.ts, frame.o, frame.h, frame.l, frame.c, position)
        except Exception as exc:  # noqa: BLE001
            bad_strategies.append(f"{item['id']}: {exc}")
    check("every strategy backtest on RELIANCE", not bad_strategies, "; ".join(bad_strategies[:4]) or len(strategies))
    return {"ok": all(item["ok"] for item in hooks), "hooks": hooks}


if __name__ == "__main__":
    import json
    import sys

    report = run()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
