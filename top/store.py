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
    "bhav": {"syncing": False, "done": 0, "total": 0, "message": "idle", "last_day": None},
}
_symbols_cache: dict = {"key": None, "rows": [], "known": set()}

UNIVERSES = {
    "nifty50": "Nifty 50",
    "nse_etf": "NSE ETFs",
    "bse_etf": "BSE ETFs",
    "bse": "BSE stocks",
    "nse": "NSE stocks",
    "nse_index": "NSE indices",
    "bse_index": "BSE indices",
}


def status() -> dict:
    with _lock:
        out = dict(_status)
        out["bhav"] = dict(_status["bhav"])
        return out


def _set_status(**kwargs) -> None:
    with _lock:
        _status.update(kwargs)


def reset_caches() -> None:
    """Forget everything cached about the store file (after it was replaced by a snapshot)."""
    global _schema_ready
    _schema_ready = False
    with _lock:
        _symbols_cache.update(key=None, rows=[], known=set())


def set_bhav_status(**kwargs) -> None:
    with _lock:
        _status["bhav"].update(kwargs)


def connect() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # DuckDB defaults to 80% of RAM; on small laptops that starves the browser and worker processes.
    limit = os.environ.get("TOP_DB_MEMORY", "768MB")
    return duckdb.connect(str(DB_PATH), config={"memory_limit": limit, "threads": "2"})


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
    for column in ("exchange VARCHAR", "kind VARCHAR", "universe VARCHAR", "code VARCHAR", "isin VARCHAR", "grp VARCHAR"):
        con.execute(f"ALTER TABLE symbols ADD COLUMN IF NOT EXISTS {column}")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS adjustments (
            symbol VARCHAR, ex_date DATE, factor DOUBLE, source VARCHAR, note VARCHAR,
            PRIMARY KEY (symbol, ex_date)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS corporate_actions (
            symbol VARCHAR, isin VARCHAR, ex_date DATE, factor DOUBLE, subject VARCHAR,
            PRIMARY KEY (symbol, ex_date, subject)
        )
        """
    )
    con.execute("CREATE TABLE IF NOT EXISTS bhav_days (exchange VARCHAR, day DATE, rows INTEGER, PRIMARY KEY (exchange, day))")
    con.executemany(
        """
        INSERT INTO symbols (symbol, yahoo, name, sector, weight, rank, exchange, kind, universe, code, isin, grp)
        VALUES (?, ?, ?, ?, ?, ?, 'NSE', 'stock', 'nifty50', ?, NULL, NULL)
        ON CONFLICT (symbol) DO UPDATE SET
            yahoo = excluded.yahoo,
            name = excluded.name,
            sector = excluded.sector,
            weight = excluded.weight,
            rank = excluded.rank,
            exchange = excluded.exchange,
            kind = excluded.kind,
            universe = excluded.universe,
            code = excluded.code
        """,
        [
            (row["symbol"], yahoo_symbol(row["symbol"]), row["name"], row["sector"], row["weight"], i + 1, row["symbol"])
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
    """Store coverage. `symbols_with_bars` and `bars` count the Nifty 50; `universes` covers everything."""
    rows = con.execute(
        """
        SELECT COALESCE(s.universe, 'nifty50'), COUNT(DISTINCT b.symbol), COUNT(*), MIN(b.ts), MAX(b.ts)
        FROM bars b LEFT JOIN symbols s ON s.symbol = b.symbol
        WHERE b.interval = ?
        GROUP BY 1
        """,
        [INTERVAL],
    ).fetchall()
    listed = dict(con.execute("SELECT universe, COUNT(*) FROM symbols GROUP BY universe").fetchall())
    per = {u: {"symbols_with_bars": int(n or 0), "bars": int(b or 0), "first": None if f is None else str(f), "last": None if l is None else str(l)} for u, n, b, f, l in rows}
    for universe in UNIVERSES:
        per.setdefault(universe, {"symbols_with_bars": 0, "bars": 0, "first": None, "last": None})
        per[universe]["listed"] = int(listed.get(universe, 0) or 0)
        per[universe]["label"] = UNIVERSES[universe]
    nifty = per["nifty50"]
    meta = dict(con.execute("SELECT key, value FROM meta WHERE key IN ('last_sync', 'bhav_last_sync')").fetchall())
    return {
        "symbols_with_bars": nifty["symbols_with_bars"],
        "bars": nifty["bars"],
        "first": nifty["first"],
        "last": nifty["last"],
        "last_sync": meta.get("last_sync"),
        "bhav_last_sync": meta.get("bhav_last_sync"),
        "universe": len(UNIVERSE),
        "universes": per,
        "total_symbols_with_bars": sum(v["symbols_with_bars"] for v in per.values()),
        "total_bars": sum(v["bars"] for v in per.values()),
    }


def needs_sync(con: duckdb.DuckDBPyConnection) -> bool:
    info = coverage(con)
    return info["symbols_with_bars"] < len(UNIVERSE) or info["bars"] < 1000


def _store_key(con):
    count, last = con.execute("SELECT COUNT(*), MAX(ts) FROM bars").fetchone()
    symbols = con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    adjustments = con.execute("SELECT COUNT(*) FROM adjustments").fetchone()[0]
    return (str(DB_PATH), int(count or 0), str(last), int(symbols or 0), int(adjustments or 0))


def list_symbols(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Every listed symbol with its last close and day change. Cached until the store changes."""
    key = _store_key(con)
    with _lock:
        if _symbols_cache["key"] == key:
            return _symbols_cache["rows"]
    rows = con.execute(
        """
        WITH recent AS (
            SELECT symbol, ts, close,
                   row_number() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM bars
            WHERE interval = ? AND ts >= (SELECT MAX(ts) FROM bars) - INTERVAL 30 DAY
        )
        SELECT s.symbol, s.name, s.sector, s.weight, s.rank, s.yahoo,
               s.exchange, s.kind, s.universe, s.code, s.grp,
               a.close, b.close, a.ts, adj.factor
        FROM symbols s
        LEFT JOIN recent a ON a.symbol = s.symbol AND a.rn = 1
        LEFT JOIN recent b ON b.symbol = s.symbol AND b.rn = 2
        LEFT JOIN adjustments adj ON adj.symbol = s.symbol AND adj.ex_date = a.ts
        ORDER BY CASE s.universe WHEN 'nifty50' THEN 0 WHEN 'nse_index' THEN 1 WHEN 'bse_index' THEN 2 WHEN 'nse_etf' THEN 3 WHEN 'bse_etf' THEN 4 WHEN 'nse' THEN 5 ELSE 6 END,
                 s.rank NULLS LAST, s.symbol
        """,
        [INTERVAL],
    ).fetchall()
    out = []
    for symbol, name, sector, weight, rank, yahoo, exchange, kind, universe, code, grp, last, prev, ts, factor in rows:
        change = None
        if factor and prev:
            prev = prev / factor
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
                "exchange": exchange or "NSE",
                "kind": kind or "stock",
                "universe": universe or "nifty50",
                "code": code,
                "group": grp,
                "last": last,
                "change_pct": change,
                "as_of": None if ts is None else str(ts),
            }
        )
    with _lock:
        _symbols_cache["key"] = key
        _symbols_cache["rows"] = out
        _symbols_cache["known"] = {row["symbol"] for row in out}
    return out


def known_symbols(con=None) -> set:
    """Symbols the store knows about (Nifty 50 plus any BSE / ETF listings)."""
    if con is not None:
        list_symbols(con)
    else:
        with session() as c:
            ensure_schema(c)
            list_symbols(c)
    with _lock:
        return set(_symbols_cache["known"]) | {row["symbol"] for row in UNIVERSE}


def symbol_info(con: duckdb.DuckDBPyConnection, symbol: str) -> dict | None:
    for row in list_symbols(con):
        if row["symbol"] == symbol:
            return row
    return None


def load_bars(con: duckdb.DuckDBPyConnection, symbol: str) -> list[dict]:
    """Daily bars, back-adjusted for any recorded splits and bonus issues."""
    rows = con.execute(
        """
        SELECT ts, open, high, low, close, volume
        FROM bars
        WHERE symbol = ? AND interval = ?
        ORDER BY ts
        """,
        [symbol, INTERVAL],
    ).fetchall()
    factors = con.execute("SELECT ex_date, factor FROM adjustments WHERE symbol = ? AND factor > 0 ORDER BY ex_date", [symbol]).fetchall()
    out = []
    # Walk backwards so the cumulative factor covers every action after each bar.
    cumulative, k = 1.0, len(factors) - 1
    for ts, open_, high, low, close, volume in reversed(rows):
        while k >= 0 and factors[k][0] > ts:
            cumulative *= factors[k][1]
            k -= 1
        out.append(
            {
                "time": str(ts),
                "open": open_ / cumulative,
                "high": high / cumulative,
                "low": low / cumulative,
                "close": close / cumulative,
                "volume": int((volume or 0) * cumulative),
            }
        )
    out.reverse()
    return out


def main(argv=None) -> int:
    """Download or refresh daily history for all 50 names without starting the server."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="top-sync",
        description="Fill or refresh the TOP DuckDB store: the Nifty 50 from Yahoo (adjusted), and NSE/BSE stocks, ETFs, indices and delivery % from exchange files. "
                    "On a new machine, --snapshot installs a ready-made copy of the whole store in minutes.",
    )
    parser.add_argument("--db", help="DuckDB file (default: TOP_DB or ./data/nse.duckdb)")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--nifty", action="store_true", help="only the Nifty 50 (Yahoo)")
    which.add_argument("--bhav", action="store_true", help="only BSE stocks, ETFs and indices (exchange files)")
    which.add_argument("--indices", action="store_true", help="only NSE and BSE indices")
    which.add_argument("--delivery", action="store_true", help="only NSE delivery %% and the FII/DII snapshot")
    which.add_argument("--snapshot", nargs="?", const="latest", metavar="FILE_OR_URL",
                       help="install a ready-made store: the newest one from the GitHub releases, or a file/URL you give (stop top-platform first)")
    which.add_argument("--make-snapshot", metavar="DIR", help="write top-data.duckdb.gz and top-data.json into DIR for a release (stop top-platform first)")
    parser.add_argument("--years", type=int, default=5, help="history for BSE stocks and ETFs (default 5)")
    args = parser.parse_args(argv)
    global DB_PATH, _schema_ready
    if args.db:
        DB_PATH = Path(args.db)
        _schema_ready = False
    if args.snapshot or args.make_snapshot:
        from top import snapshot

        if snapshot.store_in_use(DB_PATH):
            print(f"{DB_PATH} is open in another program (usually top-platform). Stop it, or use the desk's "
                  "'Download ready-made data' button instead.", flush=True)
            return 1
        if args.make_snapshot:
            manifest = snapshot.make(args.make_snapshot, DB_PATH)
            print(f"wrote {manifest['asset']} ({manifest['bytes'] / 1e6:,.0f} MB) for {manifest['symbols_with_bars']:,} scripts, "
                  f"data to {manifest['data_to']}, into {args.make_snapshot}", flush=True)
            return 0
        last = [-1]

        def show():
            st = snapshot.status()
            if int(st["done_mb"]) // 25 != last[0] or not st["running"]:
                last[0] = int(st["done_mb"]) // 25
                print(f"  {st['message']}", flush=True)

        import threading

        stop = threading.Event()

        def ticker():
            while not stop.wait(2):
                show()

        threading.Thread(target=ticker, daemon=True).start()
        try:
            info = snapshot.install(None if args.snapshot == "latest" else args.snapshot, DB_PATH)
        except Exception as exc:  # noqa: BLE001
            stop.set()
            print(f"Snapshot failed: {exc}", flush=True)
            return 1
        stop.set()
        print(f"Installed: {info['symbols_with_bars']:,} scripts, {info['bars']:,} bars, data to {info['data_to']}, "
              f"{info['leaderboard_rows']:,} leaderboard rows. The old store is kept as {DB_PATH.name}.bak. "
              "Run top-sync (or Sync history) to add the days since then.", flush=True)
        return 0
    failed = False
    if not (args.bhav or args.indices or args.delivery):
        print(f"Syncing the Nifty 50 from Yahoo into {DB_PATH}", flush=True)
        result = sync_all(lambda symbol, done, errors: print(f"  {done:>2}/{len(UNIVERSE)} {symbol}", flush=True))
        for error in result["errors"]:
            print(f"  failed: {error['symbol']}: {error['error']}", flush=True)
        failed = bool(result["errors"])
        with session() as con:
            info = coverage(con)
        print(f"Nifty 50: {info['symbols_with_bars']}/{len(UNIVERSE)} names, {info['bars']} bars.", flush=True)
    if not (args.nifty or args.indices or args.delivery):
        from top.bhav import sync_bhav

        print(f"Syncing BSE stocks and ETFs ({args.years} years of bhavcopies) into {DB_PATH}", flush=True)
        try:
            out = sync_bhav(years=args.years, progress=lambda day, n, total, count: print(f"  {n:>4}/{total} {day} {count} bars", flush=True))
            print(f"BSE/ETFs: {out['listings']} listings, {out['bars']} new bars, {out['adjustments']} split/bonus adjustments, latest {out['latest']}.", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"BSE/ETF sync failed: {exc}", flush=True)
            failed = True
    if not (args.nifty or args.delivery):
        from top.indices import sync_indices

        print(f"Syncing NSE and BSE indices into {DB_PATH}", flush=True)
        try:
            out = sync_indices(years=args.years, progress=lambda exchange, day, n, total: print(f"  {n:>4}/{total} {exchange} {day}", flush=True))
            print(f"Indices: {out['nse_bars']} NSE and {out['bse_bars']} BSE new bars.", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Index sync failed: {exc}", flush=True)
            failed = True
    if not (args.nifty or args.indices):
        from top.delivery import sync_delivery

        print(f"Syncing NSE delivery % into {DB_PATH}", flush=True)
        try:
            out = sync_delivery(years=args.years, progress=lambda day, n, total, count: print(f"  {n:>4}/{total} {day} {count} names", flush=True))
            print(f"Delivery: {out['rows']:,} new rows for {out['mapped']:,} mapped NSE tickers.", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Delivery sync failed: {exc}", flush=True)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
