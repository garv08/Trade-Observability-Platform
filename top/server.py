"""TOP HTTP server: static web app plus the JSON API for history, studies, backtests, and readings."""

from __future__ import annotations

import argparse
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
from top.store import coverage, ensure_schema, list_symbols, load_bars, needs_sync, session, status, sync_all
from top.strategies import catalog as strategy_catalog
from top.strategies import signal
from top.verify import run as run_verify
from top.universe import UNIVERSE

WEB_ROOT = Path(__file__).resolve().parent / "web"
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
                self._send(200, _start_sync())
            elif parsed.path == "/api/studies":
                self._send(200, _studies(body))
            elif parsed.path == "/api/backtest":
                self._send(200, _backtest(body))
            elif parsed.path == "/api/trend":
                self._send(200, _trend(body))
            elif parsed.path == "/api/scan":
                self._send(200, _scan(body))
            elif parsed.path == "/api/explain":
                self._send(200, _explain(body))
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001 - return the research error to the desk
            self._send(400, {"error": str(exc), "trace": traceback.format_exc(limit=4)})

    def _api_get(self, parsed):
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/health":
                payload = {"ok": True, "universe": len(UNIVERSE)}
            elif parsed.path == "/api/status":
                with session() as con:
                    ensure_schema(con)
                    payload = {"sync": status(), "coverage": coverage(con)}
            elif parsed.path == "/api/symbols":
                with session() as con:
                    ensure_schema(con)
                    payload = {"symbols": list_symbols(con)}
            elif parsed.path == "/api/bars":
                symbol = (query.get("symbol") or [""])[0]
                if symbol not in {row["symbol"] for row in UNIVERSE}:
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
                if symbol not in {row["symbol"] for row in UNIVERSE}:
                    self._send(404, {"error": "unknown symbol"})
                    return
                payload = load_fundamentals(symbol)
            elif parsed.path == "/api/verify":
                payload = run_verify()
            else:
                self._send(404, {"error": "not found"})
                return
            self._send(200, payload)
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB_ROOT / rel).resolve()
        if not target.is_relative_to(WEB_ROOT) or not target.is_file():
            self._send(404, {"error": "missing file"})
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

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


def _frame(symbol):
    with session() as con:
        bars = load_bars(con, symbol)
    if len(bars) < 30:
        raise ValueError(f"{symbol} has no stored history yet")
    return Frame(
        [bar["time"] for bar in bars],
        [bar["open"] for bar in bars],
        [bar["high"] for bar in bars],
        [bar["low"] for bar in bars],
        [bar["close"] for bar in bars],
        [bar["volume"] for bar in bars],
    )


def _studies(body):
    symbol = body.get("symbol")
    if symbol not in {row["symbol"] for row in UNIVERSE}:
        raise ValueError("unknown symbol")
    frame = _frame(symbol)
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
    if symbol not in {row["symbol"] for row in UNIVERSE}:
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
    )
    result["symbol"] = symbol
    result["strategy"] = body.get("strategy")
    return result


TREND_SECTIONS = {"Trend", "Breakout", "Trend reversal"}


def _known(symbol):
    if symbol not in {row["symbol"] for row in UNIVERSE}:
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


def _scan(body):
    strategy_id = body.get("strategy")
    if strategy_id not in {item["id"] for item in strategy_catalog()}:
        raise ValueError("unknown strategy")
    params = body.get("params") or {}
    capital = float(body.get("capital") or 1_000_000)
    cost = float(body.get("cost_bps") if body.get("cost_bps") is not None else 5)
    rows = []
    for item in UNIVERSE:
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
    return {"strategy": strategy_id, "rows": rows}


def _explain(body):
    symbol = body.get("symbol")
    _known(symbol)
    frame = _frame(symbol)
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


def _start_sync():
    global _sync_thread
    current = status()
    if current["syncing"]:
        return current
    _sync_thread = threading.Thread(target=sync_all, daemon=True)
    _sync_thread.start()
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
        _start_sync()
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="top-platform", description="TOP - Trade Observability Platform")
    parser.add_argument("--host", default=HOST, help="bind address (default %(default)s, env TOP_HOST)")
    parser.add_argument("--port", type=int, default=PORT, help="port (default %(default)s, env TOP_PORT)")
    parser.add_argument("--no-sync", action="store_true", help="do not download history on start, even if the store is empty")
    args = parser.parse_args(argv)
    auto_sync = not args.no_sync and os.environ.get("TOP_AUTO_SYNC", "1") != "0"
    server = build_server(args.host, args.port, auto_sync)
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
