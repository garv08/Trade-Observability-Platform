"""TOP HTTP server: static web app plus the JSON API for history, studies, backtests, and readings."""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from top.backtest import run as run_backtest
from top.explain import explain as explain_selection
from top.fundamentals import load as load_fundamentals
from top.indicators import SECTIONS, Frame, catalog as indicator_catalog
from top.indicators import compute as compute_study
from top.store import coverage, ensure_schema, known_symbols, list_symbols, load_bars, needs_sync, session, status, symbol_info, sync_all
from top.strategies import catalog as strategy_catalog
from top.strategies import signal
from top.verify import run as run_verify
from top import autoupdate, leaderboard, markets, portfolio
from top.robust import monte_carlo, walk_forward
from top.universe import UNIVERSE

WEB_ROOT = Path(__file__).resolve().parent / "web"
# Fixed types: on Windows, mimetypes reads the registry, which often maps .js/.css to text/plain,
# and browsers then refuse the stylesheet (grey, unstyled buttons) or scripts.
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".csv": "text/csv; charset=utf-8",
}
HOST = os.environ.get("TOP_HOST", "127.0.0.1")
PORT = int(os.environ.get("TOP_PORT", "8000"))
_sync_thread = None


def _json_ready(value):
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return round(value, 6)
    return value


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._api_get(parsed)
            return
        self._static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return
        try:
            if parsed.path == "/api/sync":
                self._send(200, _start_sync(body.get("what") or "all"))
            elif parsed.path == "/api/studies":
                self._send(200, _studies(body))
            elif parsed.path == "/api/backtest":
                self._send(200, _backtest(body))
            elif parsed.path == "/api/portfolio":
                self._send(200, _portfolio(body))
            elif parsed.path == "/api/walkforward":
                self._send(200, _walkforward(body))
            elif parsed.path == "/api/trend":
                self._send(200, _trend(body))
            elif parsed.path == "/api/scan":
                self._send(200, _scan(body))
            elif parsed.path == "/api/explain":
                self._send(200, _explain(body))
            elif parsed.path == "/api/leaderboard":
                action = body.get("action") or "start"
                if action == "stop":
                    self._send(200, leaderboard.stop())
                else:
                    self._send(200, leaderboard.start(workers=body.get("workers"), force=bool(body.get("force"))))
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001 - return the research error to the desk
            self._send(400, {"error": str(exc), "trace": traceback.format_exc(limit=4)})

    def _api_get(self, parsed):
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/health":
                payload = {"ok": True, "universe": len(UNIVERSE), "symbols": len(known_symbols())}
            elif parsed.path == "/api/status":
                from top import snapshot

                with session() as con:
                    ensure_schema(con)
                    payload = {"sync": {**status(), "snapshot": snapshot.status(), "auto": autoupdate.status()}, "coverage": coverage(con)}
            elif parsed.path == "/api/symbols":
                with session() as con:
                    ensure_schema(con)
                    payload = {"symbols": list_symbols(con)}
            elif parsed.path == "/api/bars":
                symbol = (query.get("symbol") or [""])[0]
                if symbol not in known_symbols():
                    self._send(404, {"error": "unknown symbol"})
                    return
                with session() as con:
                    payload = {"symbol": symbol, "interval": "1d", "bars": load_bars(con, symbol)}
            elif parsed.path == "/api/indicators":
                payload = {"sections": SECTIONS, "indicators": indicator_catalog(), "count": len(indicator_catalog())}
            elif parsed.path == "/api/strategies":
                items = strategy_catalog()
                payload = {"strategies": items, "count": len(items)}
            elif parsed.path == "/api/fundamentals":
                symbol = (query.get("symbol") or [""])[0]
                if symbol not in known_symbols():
                    self._send(404, {"error": "unknown symbol"})
                    return
                with session() as con:
                    info = symbol_info(con, symbol) or {}
                if info.get("kind") == "etf":
                    raise ValueError("Fundamentals are not available for ETFs. Screener.in covers companies only.")
                if info.get("kind") == "index":
                    raise ValueError("Fundamentals are not available for indices. Screener.in covers companies only.")
                screener_id = info.get("code") if info.get("exchange") == "BSE" or info.get("universe") == "nse" else symbol
                payload = load_fundamentals(symbol, screener_id)
            elif parsed.path == "/api/verify":
                payload = run_verify()
            elif parsed.path == "/api/leaderboard":
                payload = _leaderboard(query)
            elif parsed.path in ("/api/leaderboard/portfolio", "/api/leaderboard/portfolio.csv"):
                out = _strategy_portfolio(query)
                if parsed.path.endswith(".csv"):
                    buffer = io.StringIO()
                    leaderboard.export_portfolio_csv(buffer, out)
                    self._send_text(buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8", f"top{out['n']}-{out['strategy']}.csv")
                    return
                payload = out
            elif parsed.path in ("/api/leaderboard/strategies", "/api/leaderboard/strategies.csv"):
                rows = _strategy_ranking(query)
                if parsed.path.endswith(".csv"):
                    buffer = io.StringIO()
                    leaderboard.export_strategy_csv(buffer, rows)
                    self._send_text(buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8", "top-strategy-ranking.csv")
                    return
                payload = {"strategies": rows, "status": leaderboard.status()}
            elif parsed.path == "/api/leaderboard.csv":
                self._send_csv(query)
                return
            elif parsed.path == "/api/markets/overview":
                payload = _markets_overview(query)
            elif parsed.path == "/api/markets/breadth":
                with session() as con:
                    ensure_schema(con)
                    payload = {"breadth": markets.breadth(con)}
            elif parsed.path == "/api/markets/scan":
                name = (query.get("name") or ["bloodbath"])[0]
                with session() as con:
                    ensure_schema(con)
                    payload = markets.scan(con, name, min_value=float((query.get("min_value") or ["10"])[0] or 0))
            elif parsed.path == "/api/portfolio/strategies":
                payload = {"strategies": portfolio.catalog(), "universes": {k: v[0] for k, v in portfolio.UNIVERSES.items()}, "gates": portfolio.GATES}
            elif parsed.path == "/api/leaderboard/status":
                payload = leaderboard.status()
            else:
                self._send(404, {"error": "not found"})
                return
            self._send(200, payload)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB_ROOT / rel).resolve()
        if not target.is_relative_to(WEB_ROOT) or not target.is_file():
            self._send(404, {"error": "missing file"})
            return
        mime = STATIC_TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, data, mime, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_csv(self, query):
        import tempfile

        filters, _ = _leaderboard_filters(query)
        with tempfile.TemporaryFile("w+b") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            with session() as con:
                ensure_schema(con)
                leaderboard.export_csv(con, text, **filters)
            text.flush()
            size = raw.tell()
            raw.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="top-leaderboard-{filters["universe"]}.csv"')
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    block = raw.read(1 << 16)
                    if not block:
                        break
                    self.wfile.write(block)
            except (BrokenPipeError, ConnectionResetError):
                pass
            text.detach()

    def _send(self, code, payload):
        data = json.dumps(_json_ready(payload)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return


def _frame(symbol, context=()):
    """Bars for one symbol. context may ask for extra per-date data that some studies use: 'delivery', 'regime'."""
    from top.delivery import load_delivery

    extra = {}
    with session() as con:
        bars = load_bars(con, symbol)
        if "delivery" in context:
            extra["delivery"] = load_delivery(con, symbol)
        if "regime" in context:
            extra["regime"] = markets.regime_for(con, [bar["time"] for bar in bars])
    if len(bars) < 30:
        raise ValueError(f"{symbol} has no stored history yet")
    frame = Frame(
        [bar["time"] for bar in bars],
        [bar["open"] for bar in bars],
        [bar["high"] for bar in bars],
        [bar["low"] for bar in bars],
        [bar["close"] for bar in bars],
        [bar["volume"] for bar in bars],
    )
    frame.context = extra
    return frame


def _studies(body):
    symbol = body.get("symbol")
    if symbol not in known_symbols():
        raise ValueError("unknown symbol")
    wanted = {spec.get("id") for spec in body.get("studies") or [] if isinstance(spec, dict)}
    needs = set()
    for item in indicator_catalog():
        if item["id"] in wanted:
            needs.update(item.get("needs") or [])
    frame = _frame(symbol, tuple(needs))
    studies = []
    for spec in body.get("studies") or []:
        result = compute_study(spec["id"], frame, spec.get("params") or {})
        studies.append(
            {
                "id": result["id"],
                "name": result["name"],
                "pane": result["pane"],
                "series": {key: _json_ready(values.tolist()) for key, values in result["series"].items()},
                "markers": result.get("markers") or [],
                "drawings": result.get("drawings") or [],
            }
        )
    return {"symbol": symbol, "time": frame.ts, "studies": studies}


def _backtest(body):
    symbol = body.get("symbol")
    if symbol not in known_symbols():
        raise ValueError("unknown symbol")
    frame = _frame(symbol)
    position = signal(body.get("strategy"), frame, body.get("params") or {})
    result = run_backtest(
        frame.ts,
        frame.o,
        frame.h,
        frame.l,
        frame.c,
        position,
        capital=float(body.get("capital") or 1_000_000),
        cost_bps=float(body.get("cost_bps") if body.get("cost_bps") is not None else 5),
        sizing=body.get("sizing") or "full",
        target_vol=float(body.get("target_vol") or 15),
    )
    result["symbol"] = symbol
    result["strategy"] = body.get("strategy")
    result["monte_carlo"] = monte_carlo(result["trades"])
    return result


def _walkforward(body):
    symbol = body.get("symbol")
    _known(symbol)
    spec = next((item for item in strategy_catalog() if item["id"] == body.get("strategy")), None)
    if spec is None:
        raise ValueError("unknown strategy")
    frame = _frame(symbol)
    out = walk_forward(frame, spec, signal, body.get("params") or {},
                       capital=float(body.get("capital") or 1_000_000),
                       cost_bps=float(body.get("cost_bps") if body.get("cost_bps") is not None else 5))
    out["symbol"], out["strategy"] = symbol, spec["id"]
    return out


TREND_SECTIONS = {"Trend", "Breakout", "Trend reversal"}


def _known(symbol):
    if symbol not in known_symbols():
        raise ValueError("unknown symbol")


def _trend(body):
    symbol = body.get("symbol")
    _known(symbol)
    frame = _frame(symbol)
    capital = float(body.get("capital") or 1_000_000)
    cost = float(body.get("cost_bps") if body.get("cost_bps") is not None else 5)
    rows = []
    for item in strategy_catalog():
        if item["section"] not in TREND_SECTIONS:
            continue
        position = signal(item["id"], frame, {})
        result = run_backtest(frame.ts, frame.o, frame.h, frame.l, frame.c, position, capital=capital, cost_bps=cost)
        last = position[-1]
        rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "section": item["section"],
                "blurb": item["blurb"],
                "in_position": bool(last == 1),
                "return_pct": result["metrics"]["total_return_pct"],
                "max_drawdown_pct": result["metrics"]["max_drawdown_pct"],
                "trades": result["metrics"]["trades"],
                "buy_hold_pct": result["metrics"]["buy_hold_pct"],
            }
        )
    rows.sort(key=lambda row: (row["in_position"], row["return_pct"] or -999), reverse=True)
    return {"symbol": symbol, "rows": rows, "note": "One pass over trend, breakout, and reversal rules. Long or flat, next-open fills."}


SCAN_LIMIT = 200
UNIVERSE_GROUPS = {
    "nifty50": ("nifty50",),
    "index": ("nse_index", "bse_index"),
    "etf": ("nse_etf", "bse_etf"),
    "nse": ("nifty50", "nse"),
    "bse": ("bse",),
    "all": ("nifty50", "nse_index", "bse_index", "nse_etf", "bse_etf", "nse", "bse"),
}


def _scan_members(universe, limit):
    """Symbols to scan: the whole Nifty 50, or the most traded names of a larger universe."""
    groups = UNIVERSE_GROUPS.get(universe or "nifty50", ("nifty50",))
    with session() as con:
        rows = list_symbols(con)
        if groups == ("nifty50",):
            return [r for r in rows if r["universe"] == "nifty50"], False
        placeholders = ", ".join("?" for _ in groups)
        liquid = con.execute(
            f"""
            SELECT b.symbol, AVG(b.close * b.volume) AS turnover
            FROM bars b JOIN symbols s ON s.symbol = b.symbol
            WHERE b.interval = '1d' AND s.universe IN ({placeholders}) AND b.ts >= (SELECT MAX(ts) FROM bars) - INTERVAL 45 DAY
            GROUP BY b.symbol ORDER BY turnover DESC LIMIT ?
            """,
            [*groups, int(limit)],
        ).fetchall()
    by_symbol = {r["symbol"]: r for r in rows}
    total = sum(1 for r in rows if r["universe"] in groups and r["last"] is not None)
    members = [by_symbol[symbol] for symbol, _ in liquid if symbol in by_symbol]
    return members, total > len(members)


def _scan(body):
    strategy_id = body.get("strategy")
    if strategy_id not in {item["id"] for item in strategy_catalog()}:
        raise ValueError("unknown strategy")
    params = body.get("params") or {}
    capital = float(body.get("capital") or 1_000_000)
    cost = float(body.get("cost_bps") if body.get("cost_bps") is not None else 5)
    universe = body.get("universe") or "nifty50"
    limit = max(1, min(int(body.get("limit") or SCAN_LIMIT), 1000))
    members, capped = _scan_members(universe, limit)
    rows = []
    for item in members:
        symbol = item["symbol"]
        try:
            frame = _frame(symbol)
            position = signal(strategy_id, frame, params)
            result = run_backtest(frame.ts, frame.o, frame.h, frame.l, frame.c, position, capital=capital, cost_bps=cost)
            metrics = result["metrics"]
            rows.append(
                {
                    "symbol": symbol,
                    "name": item["name"],
                    "in_position": bool(position[-1] == 1),
                    "return_pct": metrics["total_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "trades": metrics["trades"],
                    "buy_hold_pct": metrics["buy_hold_pct"],
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep the rest of the universe
            rows.append({"symbol": symbol, "name": item["name"], "error": str(exc)})
    rows.sort(key=lambda row: row.get("return_pct") if row.get("return_pct") is not None else -999, reverse=True)
    note = f"Top {len(members)} by recent traded value." if capped else ""
    return {"strategy": strategy_id, "universe": universe, "rows": rows, "note": note}


def _leaderboard_filters(query):
    def one(name, default=None):
        values = query.get(name)
        return values[0] if values and values[0] != "" else default

    min_cagr = one("min_cagr", "15")
    return {
        "min_cagr": None if min_cagr in ("none", "off") else float(min_cagr),
        "universe": one("universe", "all"),
        "strategy": one("strategy"),
        "min_trades": int(one("min_trades", "1")),
        "min_years": float(one("min_years", "0")),
        "search": one("q", ""),
        "best": one("best", "0") in ("1", "true", "yes"),
        "sort": one("sort", "ratio"),
        "min_value": float(one("min_value", "0")),
        "min_dsr": float(one("min_dsr", "0")) or None,
    }, one


def _markets_overview(query):
    from top.delivery import load_fii_dii

    min_value = float((query.get("min_value") or ["10"])[0] or 0)
    with session() as con:
        ensure_schema(con)
        reg = markets.regime(con)
        return {
            "regime": {"latest": reg["latest"], "series": reg["series"][-504:]},
            "sectors": markets.sector_rotation(con),
            "scans": [{"name": key, "title": title, "rule": rule} for key, (title, rule) in markets.SCANS.items()],
            "counts": markets.scan_counts(con, min_value),
            "fii_dii": load_fii_dii(con, 60),
        }


def _portfolio(body):
    with session() as con:
        ensure_schema(con)
        return portfolio.run(
            con,
            body.get("strategy") or "momentum_12_1",
            universe=body.get("universe") or None,
            top_n=body.get("top_n") or None,
            cost_bps=float(body.get("cost_bps") if body.get("cost_bps") is not None else 5),
            capital=float(body.get("capital") or 1_000_000),
            min_value_lakh=None if body.get("min_value") in (None, "") else float(body.get("min_value")),
            gate=body.get("gate") or "none",
            sweep=bool(body.get("sweep")),
        )


def _strategy_portfolio(query):
    def one(name, default=None):
        values = query.get(name)
        return values[0] if values and values[0] != "" else default

    with session() as con:
        ensure_schema(con)
        return leaderboard.strategy_portfolio(
            con,
            strategy=one("strategy"),
            n=max(1, min(int(one("n", "20")), 100)),
            per_stock=float(one("per_stock", "100000")),
            sort=one("sort", "ratio"),
            min_trades=int(one("min_trades", "3")),
            min_years=float(one("min_years", "2")),
            min_value=float(one("min_value", "10")),
        )


def _strategy_ranking(query):
    filters, one = _leaderboard_filters(query)
    with session() as con:
        ensure_schema(con)
        return leaderboard.strategy_ranking(
            con,
            universe=filters["universe"],
            min_trades=int(one("min_trades", "3")),
            min_years=float(one("min_years", "2")),
            min_value=float(one("min_value", "10")),
            min_scripts=int(one("min_scripts", "50")),
            sort=one("sort", "median_return_dd"),
        )


def _leaderboard(query):
    filters, one = _leaderboard_filters(query)
    with session() as con:
        ensure_schema(con)
        out = leaderboard.query(
            con,
            **filters,
            limit=max(1, min(int(one("limit", "100")), 1000)),
            offset=max(0, int(one("offset", "0"))),
        )
    out["status"] = leaderboard.status()
    return out


def _explain(body):
    symbol = body.get("symbol")
    _known(symbol)
    wanted = {spec.get("id") for spec in body.get("studies") or [] if isinstance(spec, dict)}
    needs = {n for item in indicator_catalog() if item["id"] in wanted for n in (item.get("needs") or [])}
    frame = _frame(symbol, tuple(needs))
    strategy = body.get("strategy") or None
    if strategy and strategy.get("id") not in {item["id"] for item in strategy_catalog()}:
        strategy = None
    studies = [spec for spec in (body.get("studies") or []) if isinstance(spec, dict) and spec.get("id")]
    return explain_selection(
        frame,
        symbol,
        studies[:20],
        strategy,
        capital=float(body.get("capital") or 1_000_000),
        cost_bps=float(body.get("cost_bps") if body.get("cost_bps") is not None else 5),
        focus=body.get("focus"),
    )


_bhav_thread = None


def _run_bhav(what="bhav"):
    from top.bhav import sync_bhav
    from top.indices import sync_indices

    from top.delivery import sync_delivery

    if what in ("bhav", "all"):
        try:
            sync_bhav()
        except Exception:  # noqa: BLE001 - status already carries the message
            pass
    if what in ("bhav", "all", "indices"):
        try:
            sync_indices()
        except Exception:  # noqa: BLE001
            pass
    if what in ("bhav", "all", "delivery"):
        try:
            sync_delivery()
        except Exception:  # noqa: BLE001
            pass
    _refresh_leaderboard()


def _refresh_leaderboard():
    """After new bars arrive, recompute leaderboard rows for changed scripts (only if a leaderboard exists)."""
    try:
        with session() as con:
            leaderboard.ensure_tables(con)
            has_rows = con.execute("SELECT COUNT(*) FROM leaderboard_done").fetchone()[0] > 0
        if has_rows and not leaderboard.status()["running"]:
            leaderboard.start()
    except Exception:  # noqa: BLE001 - best effort
        pass


def _run_snapshot():
    from top import snapshot

    try:
        snapshot.install(lock=store_db_lock())
    except Exception:  # noqa: BLE001 - status carries the message
        pass


def store_db_lock():
    from top import store

    return store._db_lock


def _start_sync(what="all"):
    """Start background syncs: 'nifty' (Yahoo, adjusted), 'bhav' (BSE stocks + ETFs + indices), 'indices', or 'all'."""
    global _sync_thread, _bhav_thread
    current = status()
    if what == "snapshot":
        from top import snapshot

        if current["syncing"] or current["bhav"]["syncing"] or leaderboard.status()["running"] or snapshot.status()["running"]:
            raise ValueError("Wait for the running sync or leaderboard run to finish (or stop it) before installing the snapshot.")
        threading.Thread(target=_run_snapshot, daemon=True).start()
        return status()
    if what in ("nifty", "all") and not current["syncing"]:
        _sync_thread = threading.Thread(target=sync_all, daemon=True)
        _sync_thread.start()
    if what in ("bhav", "indices", "delivery", "all") and not current["bhav"]["syncing"]:
        _bhav_thread = threading.Thread(target=_run_bhav, args=(what,), daemon=True)
        _bhav_thread.start()
    return status()


class _IPv6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def _also_listen_on_ipv6_loopback(port):
    """Browsers may resolve localhost to ::1 first; answer there too. Best effort."""
    try:
        server = _IPv6Server(("::1", port), Handler)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def build_server(host=HOST, port=PORT, auto_sync=True):
    with session() as con:
        ensure_schema(con)
        stale = needs_sync(con)
    if stale and auto_sync:
        # First start: the Nifty 50 only (1–2 minutes). Everything else is a choice on the desk:
        # the ready-made data snapshot (minutes) or Sync history (hours).
        _start_sync("nifty")
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="top-platform", description="TOP - Trade Observability Platform")
    parser.add_argument("--host", default=HOST, help="bind address (default %(default)s, env TOP_HOST)")
    parser.add_argument("--port", type=int, default=PORT, help="port (default %(default)s, env TOP_PORT)")
    parser.add_argument("--no-sync", action="store_true", help="do not download history on start, even if the store is empty")
    parser.add_argument("--no-auto-update", action="store_true",
                        help="do not update every script's data automatically after each weekday's close (env TOP_AUTO_UPDATE=0)")
    parser.add_argument("--update-at", help="daily update time in IST, HH:MM (default 19:00, env TOP_AUTO_UPDATE_AT)")
    args = parser.parse_args(argv)
    auto_sync = not args.no_sync and os.environ.get("TOP_AUTO_SYNC", "1") != "0"
    server = build_server(args.host, args.port, auto_sync)
    if not args.no_auto_update and os.environ.get("TOP_AUTO_UPDATE", "1") != "0":
        at = autoupdate.update_time(args.update_at)
        autoupdate.start(_start_sync, at)
        print(f"Automatic data update: every weekday after {at:%H:%M} IST (missed days are caught up on start).", flush=True)
    port = server.server_address[1]
    extra = _also_listen_on_ipv6_loopback(port) if args.host in ("127.0.0.1", "localhost") else None
    print(f"TOP - Trade Observability Platform at http://{args.host}:{port}" + (f" (also http://localhost:{port})" if extra else ""), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
