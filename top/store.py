"""DuckDB store and Yahoo chart history for the Nifty 50 universe."""

from __future__ import annotations

import csv
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from top.universe import UNIVERSE, yahoo_symbol

# Override with TOP_DB. The default lives next to where the server is started.
DB_PATH = Path(os.environ.get("TOP_DB") or Path.cwd() / "data" / "nse.duckdb")
IST = timezone(timedelta(hours=5, minutes=30))
INTERVAL = "1d"
RANGE = "5y"

_lock = threading.Lock()
_db_lock = threading.Lock()
_schema_ready = False
_status = {
    "syncing": False,
    "done": 0,
    "total": len(UNIVERSE),
    "errors": [],
    "last_sync": None,
    "message": "idle",
}


def status() -> dict:
    with _lock:
        return dict(_status)


def _set_status(**kwargs) -> None:
    with _lock:
        _status.update(kwargs)


def connect() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


@contextmanager
def session():
    """One writer at a time. DuckDB 1.1 does not like overlapping connections here."""
    with _db_lock:
        con = connect()
        try:
            yield con
        finally:
            con.close()


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS symbols (
            symbol VARCHAR PRIMARY KEY,
            yahoo VARCHAR,
            name VARCHAR,
            sector VARCHAR,
            weight DOUBLE,
            rank INTEGER
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bars (
            symbol VARCHAR,
            interval VARCHAR,
            ts DATE,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            PRIMARY KEY (symbol, interval, ts)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key VARCHAR PRIMARY KEY,
            value VARCHAR
        )
        """
    )
    con.executemany(
        """
        INSERT INTO symbols VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol) DO UPDATE SET
            yahoo = excluded.yahoo,
            name = excluded.name,
            sector = excluded.sector,
            weight = excluded.weight,
            rank = excluded.rank
        """,
        [
            (row["symbol"], yahoo_symbol(row["symbol"]), row["name"], row["sector"], row["weight"], i + 1)
            for i, row in enumerate(UNIVERSE)
        ],
    )
    _schema_ready = True


def _to_date(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), IST).date().isoformat()


def fetch_yahoo(symbol: str) -> list[tuple]:
    yahoo = yahoo_symbol(symbol)
    query = urllib.parse.urlencode(
        {"interval": INTERVAL, "range": RANGE, "includeAdjustedClose": "true", "events": "div,splits"}
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo)}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except Exception as exc:  # noqa: BLE001 - retry network failures
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    else:
        raise RuntimeError(f"{symbol}: {last_error}")

    result = (payload.get("chart") or {}).get("result")
    if not result:
        error = (payload.get("chart") or {}).get("error")
        raise RuntimeError(f"{symbol}: {error}")
    block = result[0]
    timestamps = block.get("timestamp") or []
    quote = (block.get("indicators") or {}).get("quote") or [{}]
    quote = quote[0]
    adj_block = ((block.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    rows = []
    seen = set()
    for i, ts in enumerate(timestamps):
        close = _at(quote.get("close"), i)
        if close is None or close <= 0:
            continue
        adj = _at(adj_block, i)
        factor = (adj / close) if adj and adj > 0 else 1.0
        day = _to_date(ts)
        if day in seen:
            rows = [row for row in rows if row[2] != day]
        seen.add(day)
        rows.append(
            (
                symbol,
                INTERVAL,
                day,
                _scale(_at(quote.get("open"), i), close, factor),
                _scale(_at(quote.get("high"), i), close, factor),
                _scale(_at(quote.get("low"), i), close, factor),
                close * factor,
                int(_at(quote.get("volume"), i) or 0),
            )
        )
    if len(rows) < 50:
        raise RuntimeError(f"{symbol}: only {len(rows)} bars")
    return rows


def _at(values, index):
    if not values or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    return float(value)


def _scale(value, close, factor):
    base = close if value is None else value
    return float(base) * factor


def replace_bars(con: duckdb.DuckDBPyConnection, symbol: str, rows: list[tuple]) -> None:
    # Row-by-row inserts are unusable on this CPU. COPY into a temp table, then into bars.
    unique = {}
    for row in rows:
        unique[row[2]] = row
    rows = [unique[day] for day in sorted(unique)]
    con.execute("DELETE FROM bars WHERE symbol = ? AND interval = ?", [symbol, INTERVAL])
    con.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS bars_in (
            symbol VARCHAR, interval VARCHAR, ts DATE,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT
        )
        """
    )
    con.execute("DELETE FROM bars_in")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as handle:
        path = handle.name
        writer = csv.writer(handle)
        writer.writerows(rows)
    try:
        escaped = path.replace("'", "''")
        con.execute(f"COPY bars_in FROM '{escaped}' (HEADER false)")
        con.execute("INSERT INTO bars SELECT * FROM bars_in")
    finally:
        Path(path).unlink(missing_ok=True)


def sync_all(progress=None) -> dict:
    _set_status(syncing=True, done=0, total=len(UNIVERSE), errors=[], message="syncing Yahoo daily history")
    errors = []
    done = 0
    with session() as con:
        ensure_schema(con)
    for row in UNIVERSE:
        symbol = row["symbol"]
        try:
            bars = fetch_yahoo(symbol)
            with session() as con:
                replace_bars(con, symbol, bars)
        except Exception as exc:  # noqa: BLE001 - keep the rest of the universe
            errors.append({"symbol": symbol, "error": str(exc)})
        done += 1
        _set_status(done=done, errors=list(errors), message=f"{done}/{len(UNIVERSE)} {symbol}")
        if progress:
            progress(symbol, done, errors)
        time.sleep(0.15)
    stamp = datetime.now(IST).isoformat(timespec="seconds")
    with session() as con:
        con.execute(
            "INSERT INTO meta VALUES ('last_sync', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [stamp],
        )
    _set_status(syncing=False, last_sync=stamp, errors=errors, message="ready" if not errors else "ready with gaps")
    return status()


def coverage(con: duckdb.DuckDBPyConnection) -> dict:
    row = con.execute(
        """
        SELECT COUNT(DISTINCT symbol), COUNT(*), MIN(ts), MAX(ts)
        FROM bars WHERE interval = ?
        """,
        [INTERVAL],
    ).fetchone()
    meta = con.execute("SELECT value FROM meta WHERE key = 'last_sync'").fetchone()
    return {
        "symbols_with_bars": int(row[0] or 0),
        "bars": int(row[1] or 0),
        "first": None if row[2] is None else str(row[2]),
        "last": None if row[3] is None else str(row[3]),
        "last_sync": None if meta is None else meta[0],
        "universe": len(UNIVERSE),
    }


def needs_sync(con: duckdb.DuckDBPyConnection) -> bool:
    info = coverage(con)
    return info["symbols_with_bars"] < len(UNIVERSE) or info["bars"] < 1000


def list_symbols(con: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = con.execute(
        """
        WITH ranked AS (
            SELECT symbol, ts, close,
                   row_number() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM bars
            WHERE interval = ?
        )
        SELECT s.symbol, s.name, s.sector, s.weight, s.rank, s.yahoo,
               a.close, b.close, a.ts
        FROM symbols s
        LEFT JOIN ranked a ON a.symbol = s.symbol AND a.rn = 1
        LEFT JOIN ranked b ON b.symbol = s.symbol AND b.rn = 2
        ORDER BY s.rank
        """,
        [INTERVAL],
    ).fetchall()
    out = []
    for symbol, name, sector, weight, rank, yahoo, last, prev, ts in rows:
        change = None
        if last is not None and prev not in (None, 0):
            change = (last / prev - 1) * 100
        out.append(
            {
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "weight": weight,
                "rank": rank,
                "yahoo": yahoo,
                "last": last,
                "change_pct": change,
                "as_of": None if ts is None else str(ts),
            }
        )
    return out


def load_bars(con: duckdb.DuckDBPyConnection, symbol: str) -> list[dict]:
    rows = con.execute(
        """
        SELECT ts, open, high, low, close, volume
        FROM bars
        WHERE symbol = ? AND interval = ?
        ORDER BY ts
        """,
        [symbol, INTERVAL],
    ).fetchall()
    return [
        {
            "time": str(ts),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": int(volume or 0),
        }
        for ts, open_, high, low, close, volume in rows
    ]


def main(argv=None) -> int:
    """Download or refresh daily history for all 50 names without starting the server."""
    import argparse

    parser = argparse.ArgumentParser(prog="top-sync", description="Fill or refresh the TOP DuckDB store from Yahoo daily history.")
    parser.add_argument("--db", help="DuckDB file (default: TOP_DB or ./data/nse.duckdb)")
    args = parser.parse_args(argv)
    global DB_PATH, _schema_ready
    if args.db:
        DB_PATH = Path(args.db)
        _schema_ready = False
    print(f"Syncing {len(UNIVERSE)} names into {DB_PATH}", flush=True)
    result = sync_all(lambda symbol, done, errors: print(f"  {done:>2}/{len(UNIVERSE)} {symbol}", flush=True))
    for error in result["errors"]:
        print(f"  failed: {error['symbol']}: {error['error']}", flush=True)
    with session() as con:
        info = coverage(con)
    print(f"Done: {info['symbols_with_bars']}/{len(UNIVERSE)} names, {info['bars']} bars.", flush=True)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
