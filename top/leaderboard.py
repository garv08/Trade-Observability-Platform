"""Leaderboard: every backtest strategy on every stored script and index.

A background job runs all strategies (default parameters, ₹10 lakh, 5 bps per side)
on every symbol with at least `MIN_BARS` daily bars and stores one row per
(symbol, strategy) in DuckDB. Work is spread over worker processes that never open the
database: the parent reads bars and writes results, the workers only compute.

The job is resumable. A symbol is skipped when its stored results were computed on the
same last bar with the same strategy catalogue, so re-running after a daily sync only
recomputes symbols that have new data.

Ranking metric: CAGR / |max drawdown| (both in %), sometimes called the MAR ratio.
"""

from __future__ import annotations

import hashlib
import multiprocessing
import os
import threading
import time
from datetime import datetime

from top import market, store

MIN_BARS = 250
BATCH = 12
VERSION = "2"
CAPITAL = 1_000_000.0
COST_BPS = 5.0
# Index series that are not prices of anything you can hold: excluded from the leaderboard.
EXCLUDE_LIKE = ("%dividend points%", "%vix%")
PRIORITY = {"nifty50": 0, "nse_index": 1, "bse_index": 2, "nse_etf": 3, "bse_etf": 4, "bse": 5}
UNIVERSE_GROUPS = {
    "all": None,
    "nifty50": ("nifty50",),
    "index": ("nse_index", "bse_index"),
    "etf": ("nse_etf", "bse_etf"),
    "bse": ("bse",),
}
SORTS = {
    "ratio": "ratio DESC NULLS LAST",
    "return_dd": "return_dd DESC NULLS LAST",
    "cagr": "cagr_pct DESC NULLS LAST",
    "max_dd": "max_dd_pct DESC NULLS LAST",
    "sharpe": "sharpe DESC NULLS LAST",
    "return": "total_return_pct DESC NULLS LAST",
    "win_rate": "win_rate_pct DESC NULLS LAST",
    "trades": "trades DESC",
}
COLUMNS = (
    "symbol VARCHAR, strategy VARCHAR, cagr_pct DOUBLE, max_dd_pct DOUBLE, ratio DOUBLE, total_return_pct DOUBLE, "
    "buy_hold_pct DOUBLE, trades INTEGER, win_rate_pct DOUBLE, profit_factor DOUBLE, sharpe DOUBLE, exposure_pct DOUBLE, "
    "in_position BOOLEAN, years DOUBLE, first_day DATE, last_day DATE, computed_at TIMESTAMP"
)

_lock = threading.Lock()
_stop = threading.Event()
_thread = None
_runner = None
POOL_START_TIMEOUT = 120
_status = {"running": False, "done": 0, "total": 0, "skipped": 0, "symbol": None, "started": None, "finished": None,
           "eta_seconds": None, "rate_per_min": None, "message": "idle", "errors": 0, "excluded": 0, "workers": 0, "db": None}


def status():
    with _lock:
        if _status["running"] and _runner is not None and not _runner.is_alive():
            # The run thread ended without reporting (for example killed with the process): don't stay "running".
            _status.update(running=False, message="stopped unexpectedly; press Run / resume to continue")
        return dict(_status)


def _ping():
    return os.getpid()


class _Workers:
    """A spawn process pool, or in-process evaluation when worker processes can't start (some Windows setups)."""

    def __init__(self, workers, returns):
        self.pool = None
        self.mode = "in-process"
        if workers > 1:
            try:
                pool = multiprocessing.get_context("spawn").Pool(workers, initializer=_init, initargs=(returns,))
                pool.apply_async(_ping).get(timeout=POOL_START_TIMEOUT)
                self.pool, self.mode = pool, f"{workers} worker processes"
            except Exception:  # noqa: BLE001 - fall back rather than hang or fail
                try:
                    pool.terminate()
                except Exception:  # noqa: BLE001
                    pass

    def map(self, payloads):
        if self.pool is not None:
            return self.pool.map(evaluate, payloads, chunksize=1)
        return [evaluate(payload) for payload in payloads]

    def close(self):
        if self.pool is not None:
            self.pool.terminate()


def _set(**kwargs):
    with _lock:
        _status.update(kwargs)


_tables_ready = {"path": None}


def ensure_tables(con):
    if _tables_ready["path"] == str(store.DB_PATH):
        return
    con.execute(f"CREATE TABLE IF NOT EXISTS leaderboard ({COLUMNS}, PRIMARY KEY (symbol, strategy))")
    con.execute(
        "CREATE TABLE IF NOT EXISTS leaderboard_done (symbol VARCHAR PRIMARY KEY, last_day DATE, catalog_key VARCHAR, strategies INTEGER, computed_at TIMESTAMP)"
    )
    con.execute("CREATE TABLE IF NOT EXISTS leaderboard_liquidity (symbol VARCHAR PRIMARY KEY, median_value_lakh DOUBLE)")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    floor = con.execute("SELECT value FROM meta WHERE key = 'leaderboard_dd_floor'").fetchone()
    if floor is None or floor[0] != str(DD_FLOOR):
        # Rows stored before the drawdown floor existed: recompute the ratio in place.
        con.execute("UPDATE leaderboard SET ratio = round(cagr_pct / greatest(abs(max_dd_pct), ?), 4) WHERE cagr_pct IS NOT NULL AND max_dd_pct IS NOT NULL",
                    [DD_FLOOR])
        con.execute("INSERT INTO meta VALUES ('leaderboard_dd_floor', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", [str(DD_FLOOR)])
    tested = con.execute("SELECT value FROM meta WHERE key = 'leaderboard_years'").fetchone()
    if tested is None:
        # Older rows stored the listing's history; convert to years actually tested (after warm-up),
        # which CAGR and total return imply: (1 + total) = (1 + cagr) ^ years.
        con.execute(
            """
            UPDATE leaderboard SET years = round(ln(1 + total_return_pct / 100) / ln(1 + cagr_pct / 100), 2)
            WHERE cagr_pct IS NOT NULL AND total_return_pct IS NOT NULL AND abs(cagr_pct) >= 0.05
              AND cagr_pct > -100 AND total_return_pct > -100
            """
        )
        con.execute("INSERT INTO meta VALUES ('leaderboard_years', 'tested') ON CONFLICT (key) DO UPDATE SET value = excluded.value")
    if con.execute("SELECT COUNT(*) FROM leaderboard_liquidity").fetchone()[0] == 0 and con.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]:
        refresh_liquidity(con)
    _tables_ready["path"] = str(store.DB_PATH)


def refresh_liquidity(con):
    """Median daily traded value (₹ lakh) over each symbol's last 250 bars."""
    con.execute("DELETE FROM leaderboard_liquidity")
    con.execute(
        """
        INSERT INTO leaderboard_liquidity
        SELECT symbol, median(close * volume) / 1e5 FROM (
            SELECT symbol, close, volume, row_number() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM bars WHERE interval = '1d'
        ) WHERE rn <= 250 GROUP BY symbol
        """
    )


def catalog_key():
    from top.strategies import catalog

    ids = ",".join(sorted(item["id"] for item in catalog()))
    return hashlib.sha1(f"{VERSION}|{CAPITAL}|{COST_BPS}|{ids}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------- worker side

def _init(returns):
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    market.pin(returns)


def _num(value):
    if value is None:
        return None
    value = float(value)
    return value if value == value and value not in (float("inf"), float("-inf")) else None


DD_FLOOR = 5.0
MIN_VALUE_LAKH = 10.0


def ratio_of(cagr, dd):
    """CAGR / |max drawdown|, with the drawdown floored at DD_FLOOR % so near-zero drawdowns don't explode."""
    if cagr is None or dd is None:
        return None
    return cagr / max(abs(dd), DD_FLOOR)


MIN_DENSITY = 0.5
MAX_UP, MAX_DOWN = 2.0, 0.5


def data_problem(ts, close):
    """Why a (split-adjusted) series is unfit for ranking, or None.

    Thinly traded BSE listings and left-over unadjusted corporate actions produce
    impossible returns; they are skipped rather than ranked.
    """
    from datetime import date

    first, last = date.fromisoformat(str(ts[0])[:10]), date.fromisoformat(str(ts[-1])[:10])
    weekdays = max(1, (last - first).days * 5 / 7)
    if len(ts) / weekdays < MIN_DENSITY:
        return f"thin trading: {len(ts)} bars over {weekdays:.0f} weekdays"
    for prev, cur in zip(close, close[1:]):
        if prev and cur and prev > 0 and cur > 0 and not (MAX_DOWN <= cur / prev <= MAX_UP):
            return f"price jump {cur / prev:.2f}x in one day"
    return None


def evaluate(payload):
    """Run every strategy on one symbol. payload = (symbol, ts, o, h, l, c, v). Never touches the store."""
    from top.backtest import metrics
    from top.indicators import Frame
    from top.strategies import STRATEGIES, signal

    symbol, ts, o, h, l, c, v = payload
    problem = data_problem(ts, c)
    if problem:
        return symbol, ts[-1], [], 0, problem
    frame = Frame(ts, o, h, l, c, v)
    rows, errors = [], 0
    for item in STRATEGIES:
        try:
            position = signal(item["id"], frame, {})
            m = metrics(frame.o, frame.c, position, capital=CAPITAL, cost_bps=COST_BPS)
        except Exception:  # noqa: BLE001 - one failing rule must not stop the rest
            errors += 1
            continue
        cagr, dd = _num(m.get("cagr_pct")), _num(m.get("max_drawdown_pct"))
        ratio = ratio_of(cagr, dd)
        start = next((i for i, x in enumerate(position) if x == x), 0)
        tested = (len(ts) - start) / 252
        in_position = bool(position[-1] == 1) if len(position) else False
        rows.append((symbol, item["id"], cagr, dd, None if ratio is None else round(ratio, 4), _num(m.get("total_return_pct")),
                     _num(m.get("buy_hold_pct")), int(m.get("trades") or 0), _num(m.get("win_rate_pct")),
                     _num(m.get("profit_factor")), _num(m.get("sharpe")), _num(m.get("exposure_pct")),
                     in_position, round(tested, 2), ts[start] if start < len(ts) else ts[0], ts[-1]))
    return symbol, ts[-1], rows, errors, None


# ---------------------------------------------------------------- parent side

def members(con, force=False):
    """Symbols to (re)compute, highest priority first, and how many are already current."""
    ensure_tables(con)
    rows = con.execute(
        f"""
        WITH recent AS (SELECT MAX(ts) - INTERVAL 45 DAY AS since FROM bars)
        SELECT s.symbol, COALESCE(s.universe, 'nifty50'), COUNT(*), MAX(b.ts),
               AVG(CASE WHEN b.ts >= (SELECT since FROM recent) THEN b.close * b.volume END)
        FROM symbols s JOIN bars b ON b.symbol = s.symbol AND b.interval = '1d'
        WHERE NOT (COALESCE(s.kind, '') = 'index' AND ({' OR '.join('lower(s.name) LIKE ?' for _ in EXCLUDE_LIKE)}))
        GROUP BY 1, 2 HAVING COUNT(*) >= ? AND MIN(b.close) > 0
        """,
        [*EXCLUDE_LIKE, MIN_BARS],
    ).fetchall()
    key = catalog_key()
    done = {} if force else {s: (d, k) for s, d, k in con.execute("SELECT symbol, last_day, catalog_key FROM leaderboard_done").fetchall()}
    todo, current = [], 0
    for symbol, universe, _, last, turnover in rows:
        if done.get(symbol) == (last, key):
            current += 1
            continue
        todo.append((PRIORITY.get(universe, 9), -(turnover or 0), symbol))
    todo.sort()
    return [symbol for _, _, symbol in todo], current, len(rows)


def _load(con, symbol):
    bars = store.load_bars(con, symbol)
    return (symbol, [b["time"] for b in bars], [b["open"] for b in bars], [b["high"] for b in bars],
            [b["low"] for b in bars], [b["close"] for b in bars], [b["volume"] for b in bars])


def save(con, results, key):
    from top.bhav import _copy_into_temp

    stamp = datetime.now().isoformat(timespec="seconds")
    flat = [(*row, stamp) for _, _, rows, *_ in results for row in rows]
    symbols = [(symbol, last, key, len(rows), stamp) for symbol, last, rows, *_ in results]
    ensure_tables(con)
    _copy_into_temp(con, "lb_done_in", "symbol VARCHAR, last_day DATE, catalog_key VARCHAR, strategies INTEGER, computed_at TIMESTAMP", symbols)
    con.execute("DELETE FROM leaderboard WHERE symbol IN (SELECT symbol FROM lb_done_in)")
    if flat:
        _copy_into_temp(con, "lb_in", COLUMNS, flat)
        con.execute("INSERT INTO leaderboard SELECT * FROM lb_in")
    con.execute("INSERT OR REPLACE INTO leaderboard_done SELECT * FROM lb_done_in")


def run_all(workers=None, force=False, limit=None, progress=None):
    """Compute the leaderboard. Blocking; use start() for the background version."""
    global _runner
    workers = max(1, workers or min(2, os.cpu_count() or 1))
    _runner = threading.current_thread()
    _stop.clear()
    _set(running=True, done=0, total=0, skipped=0, errors=0, excluded=0, symbol=None, started=datetime.now().isoformat(timespec="seconds"),
         finished=None, eta_seconds=None, rate_per_min=None, workers=workers, message="listing symbols")
    try:
        with store.session() as con:
            store.ensure_schema(con)
            ensure_tables(con)
            not_prices = f"SELECT symbol FROM symbols WHERE kind = 'index' AND ({' OR '.join('lower(name) LIKE ?' for _ in EXCLUDE_LIKE)})"
            con.execute(f"DELETE FROM leaderboard WHERE symbol IN ({not_prices})", list(EXCLUDE_LIKE))
            con.execute(f"DELETE FROM leaderboard_done WHERE symbol IN ({not_prices})", list(EXCLUDE_LIKE))
            todo, current, eligible = members(con, force=force)
        if limit:
            todo = todo[: int(limit)]
        returns = market.daily_returns()
        key = catalog_key()
        _set(total=len(todo), skipped=current, message=f"{len(todo)} to compute, {current} already current of {eligible}")
        if not todo:
            message = ("nothing to compute: no script has 250+ daily bars yet. Open the charting desk and click Sync history first"
                       if eligible == 0 else f"complete: all {current:,} scripts are already current")
            with store.session() as con:
                refresh_liquidity(con)
            _set(running=False, finished=datetime.now().isoformat(timespec="seconds"), message=message, db=str(store.DB_PATH))
            return status()
        began, done, errors, excluded, total = time.time(), 0, 0, 0, len(todo)
        _set(message="starting worker processes")
        pool = _Workers(workers, returns)
        _set(workers=workers if pool.pool is not None else 1, message=f"{len(todo):,} to compute with {pool.mode}")
        try:
            # Later passes pick up scripts whose bars changed while this run was going (a sync finishing meanwhile).
            for attempt in range(3):
                for start in range(0, len(todo), BATCH):
                    if _stop.is_set():
                        break
                    batch = todo[start:start + BATCH]
                    with store.session() as con:
                        payloads = [_load(con, symbol) for symbol in batch]
                    results = pool.map(payloads)
                    with store.session() as con:
                        save(con, results, key)
                    done += len(batch)
                    errors += sum(r[3] for r in results)
                    excluded += sum(1 for r in results if len(r) > 4 and r[4])
                    elapsed = time.time() - began
                    rate = done / elapsed if elapsed else 0
                    _set(done=done, errors=errors, excluded=excluded, symbol=batch[-1], rate_per_min=round(rate * 60, 1),
                         eta_seconds=int((total - done) / rate) if rate else None,
                         message=f"{done:,} of {total:,} symbols")
                    if progress:
                        progress(done, total, batch[-1])
                if _stop.is_set() or limit or attempt == 2:
                    break
                with store.session() as con:
                    todo, _, _ = members(con)
                if not todo:
                    break
                total += len(todo)
                _set(total=total, message=f"{len(todo)} scripts changed during the run; recomputing")
        finally:
            pool.close()
        with store.session() as con:
            refresh_liquidity(con)
        stopped = _stop.is_set()
        _set(running=False, finished=datetime.now().isoformat(timespec="seconds"), eta_seconds=None,
             message=("stopped" if stopped else "complete") + f": {done:,} symbols computed")
        return status()
    except Exception as exc:  # noqa: BLE001
        _set(running=False, message=f"failed: {exc}")
        raise


def start(workers=None, force=False):
    global _thread
    if status()["running"]:
        return status()

    def target():
        try:
            run_all(workers=workers, force=force)
        except Exception:  # noqa: BLE001 - status carries the message
            pass

    _thread = threading.Thread(target=target, daemon=True)
    _thread.start()
    time.sleep(0.2)
    return status()


def stop():
    _stop.set()
    return status()


# ---------------------------------------------------------------- reading

def _filtered(min_cagr=15.0, universe="all", strategy=None, min_trades=1, min_years=0.0, search="", best=False, sort="ratio",
              min_value=None):
    """SQL for the filtered leaderboard: (base query, args, order, filters without universe, their args)."""
    where = ["l.trades >= ?", "l.years >= ?", "l.ratio IS NOT NULL"]
    args = [int(min_trades), float(min_years)]
    if min_cagr is not None:
        where.append("l.cagr_pct > ?")
        args.append(float(min_cagr))
    if strategy:
        where.append("l.strategy = ?")
        args.append(strategy)
    if min_value:
        # Indices are not traded themselves, so the liquidity floor applies to stocks and ETFs only.
        where.append("(s.kind = 'index' OR COALESCE(q.median_value_lakh, 0) >= ?)")
        args.append(float(min_value))
    for term in (search or "").lower().split():
        where.append("(lower(l.symbol) LIKE ? OR lower(s.name) LIKE ? OR s.code = ?)")
        args.extend([f"%{term}%", f"%{term}%", term])
    chip_where, chip_args = list(where), list(args)
    groups = UNIVERSE_GROUPS.get(universe or "all")
    if groups:
        where.append(f"COALESCE(s.universe, 'nifty50') IN ({', '.join('?' for _ in groups)})")
        args.extend(groups)
    order = SORTS.get(sort, SORTS["ratio"])
    base = f"""
        SELECT l.*, round(l.total_return_pct / greatest(abs(l.max_dd_pct), {DD_FLOOR}), 4) AS return_dd,
               s.name, COALESCE(s.universe, 'nifty50') AS universe, s.exchange, q.median_value_lakh
        FROM leaderboard l JOIN symbols s ON s.symbol = l.symbol LEFT JOIN leaderboard_liquidity q ON q.symbol = l.symbol
        WHERE {' AND '.join(where)}
    """
    if best:
        # Each script's best row follows the chosen sort (CAGR ÷ DD by default).
        base += f" QUALIFY row_number() OVER (PARTITION BY l.symbol ORDER BY {order}, l.strategy) = 1"
    return base, args, order, chip_where, chip_args


CSV_COLUMNS = ("symbol", "name", "universe", "exchange", "median_value_lakh", "strategy", "strategy_name", "section", "ratio", "return_dd", "cagr_pct", "max_dd_pct",
               "total_return_pct", "buy_hold_pct", "trades", "win_rate_pct", "profit_factor", "sharpe", "exposure_pct",
               "in_position", "years", "first_day", "last_day", "computed_at")


def export_csv(con, handle, **filters):
    """Write every filtered row, ranked, as CSV to a text handle. Returns the row count."""
    import csv

    from top.strategies import catalog

    ensure_tables(con)
    names = {item["id"]: item for item in catalog()}
    base, args, order, _, _ = _filtered(**filters)
    cursor = con.execute(f"SELECT * FROM ({base}) ORDER BY {order}, symbol, strategy", args)
    cols = [d[0] for d in cursor.description]
    writer = csv.writer(handle)
    writer.writerow(("rank", *CSV_COLUMNS))
    rank = 0
    while True:
        chunk = cursor.fetchmany(5000)
        if not chunk:
            break
        for raw in chunk:
            row = dict(zip(cols, raw))
            meta = names.get(row["strategy"], {})
            row["strategy_name"] = meta.get("name", row["strategy"])
            row["section"] = meta.get("section", "")
            rank += 1
            writer.writerow((rank, *("" if row.get(c) is None else row.get(c) for c in CSV_COLUMNS)))
    return rank


def query(con, min_cagr=15.0, universe="all", strategy=None, min_trades=1, min_years=0.0, search="",
          best=False, sort="ratio", limit=100, offset=0, min_value=None):
    """Ranked rows plus totals. Filters apply before ranking; best=True keeps each symbol's top row."""
    ensure_tables(con)
    base, args, order, chip_where, chip_args = _filtered(min_cagr, universe, strategy, min_trades, min_years, search, best, sort, min_value)
    total = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT symbol) FROM ({base})", args).fetchone()
    cursor = con.execute(f"SELECT * FROM ({base}) ORDER BY {order}, symbol, strategy LIMIT ? OFFSET ?", [*args, int(limit), int(offset)])
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r)) for r in cursor.fetchall()]
    for row in rows:
        for k in ("first_day", "last_day", "computed_at"):
            if row.get(k) is not None:
                row[k] = str(row[k])
    by_strategy = con.execute(
        f"""
        SELECT strategy, COUNT(*) AS scripts, median(ratio) AS median_ratio, median(cagr_pct) AS median_cagr,
               median(max_dd_pct) AS median_dd
        FROM ({base}) GROUP BY strategy ORDER BY scripts DESC, median_ratio DESC LIMIT 100
        """,
        args,
    ).fetchall()
    per_universe = dict(con.execute(
        f"""
        SELECT COALESCE(s.universe, 'nifty50'), COUNT(DISTINCT l.symbol)
        FROM leaderboard l JOIN symbols s ON s.symbol = l.symbol LEFT JOIN leaderboard_liquidity q ON q.symbol = l.symbol
        WHERE {' AND '.join(chip_where)} GROUP BY 1
        """,
        chip_args,
    ).fetchall())
    universes = {key: sum(per_universe.get(u, 0) for u in (members_ or per_universe)) for key, members_ in UNIVERSE_GROUPS.items()}
    computed = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT symbol), MAX(computed_at), MAX(last_day) FROM leaderboard"
    ).fetchone()
    return {
        "rows": rows,
        "total": int(total[0] or 0),
        "symbols": int(total[1] or 0),
        "universes": universes,
        "by_strategy": [{"strategy": s, "scripts": n, "median_ratio": r, "median_cagr": c, "median_dd": d} for s, n, r, c, d in by_strategy],
        "computed": {"rows": int(computed[0] or 0), "symbols": int(computed[1] or 0),
                     "at": None if computed[2] is None else str(computed[2]), "data_to": None if computed[3] is None else str(computed[3])},
    }


# ---------------------------------------------------------------- strategy ranking

STRATEGY_SORTS = {
    "median_return_dd": "median_return_dd DESC NULLS LAST",
    "mean_return_dd": "mean_return_dd DESC NULLS LAST",
    "median_cagr_dd": "median_cagr_dd DESC NULLS LAST",
    "pct_profitable": "pct_profitable DESC NULLS LAST",
    "pct_beat_hold": "pct_beat_hold DESC NULLS LAST",
    "scripts": "scripts DESC",
}
STRATEGY_COLUMNS = ("rank", "strategy", "strategy_name", "section", "creator", "scripts", "median_return_dd", "mean_return_dd",
                    "p25_return_dd", "p75_return_dd", "median_return_pct", "median_max_dd_pct", "median_cagr_pct", "median_cagr_dd",
                    "pct_profitable", "pct_beat_hold", "median_trades", "median_years", "best_symbol", "best_return_dd")


def strategy_ranking(con, universe="all", min_trades=3, min_years=2.0, min_value=10.0, min_scripts=50, sort="median_return_dd"):
    """Rank strategies by total return / |max drawdown| across scripts.

    Per (script, strategy): return_dd = total_return_pct / max(|max_dd_pct|, DD_FLOOR). Per strategy: the median
    across every qualifying script (robust to a few multibaggers), plus mean, quartiles, hit rates, and the best script.
    No CAGR cut: losing scripts count, so a strategy has to work broadly to rank high.
    """
    from top.strategies import catalog

    ensure_tables(con)
    base, args, _, _, _ = _filtered(min_cagr=None, universe=universe, min_trades=min_trades, min_years=min_years, min_value=min_value)
    order = STRATEGY_SORTS.get(sort, STRATEGY_SORTS["median_return_dd"])
    rows = con.execute(
        f"""
        WITH r AS (
            SELECT * EXCLUDE (return_dd), total_return_pct / greatest(abs(max_dd_pct), {DD_FLOOR}) AS return_dd FROM ({base})
            WHERE total_return_pct IS NOT NULL AND max_dd_pct IS NOT NULL
        )
        SELECT strategy, COUNT(*) AS scripts,
               median(return_dd) AS median_return_dd, avg(return_dd) AS mean_return_dd,
               quantile_cont(return_dd, 0.25) AS p25_return_dd, quantile_cont(return_dd, 0.75) AS p75_return_dd,
               median(total_return_pct) AS median_return_pct, median(max_dd_pct) AS median_max_dd_pct,
               median(cagr_pct) AS median_cagr_pct, median(ratio) AS median_cagr_dd,
               100.0 * avg(CASE WHEN total_return_pct > 0 THEN 1 ELSE 0 END) AS pct_profitable,
               100.0 * avg(CASE WHEN total_return_pct > buy_hold_pct THEN 1 ELSE 0 END) AS pct_beat_hold,
               median(trades) AS median_trades, median(years) AS median_years,
               first(symbol ORDER BY return_dd DESC, symbol) AS best_symbol, max(return_dd) AS best_return_dd
        FROM r GROUP BY strategy HAVING COUNT(*) >= ?
        ORDER BY {order}, strategy
        """,
        [*args, int(min_scripts)],
    ).fetchall()
    meta = {item["id"]: item for item in catalog()}
    out = []
    for rank, row in enumerate(rows, start=1):
        strategy = row[0]
        item = meta.get(strategy, {})
        values = dict(zip(STRATEGY_COLUMNS[5:], row[1:]))
        for key, value in values.items():
            if isinstance(value, float):
                values[key] = round(value, 4 if key.endswith("_dd") else 2)
        out.append({"rank": rank, "strategy": strategy, "strategy_name": item.get("name", strategy), "section": item.get("section", ""),
                    "creator": item.get("creator") or "", **values})
    return out


def export_strategy_csv(handle, rows):
    import csv

    writer = csv.writer(handle)
    writer.writerow(STRATEGY_COLUMNS)
    for row in rows:
        writer.writerow(["" if row.get(c) is None else row.get(c) for c in STRATEGY_COLUMNS])
    return len(rows)


# Committed snapshot files and the exact settings that produce them (`top-leaderboard --results results/`).
RESULT_FILTERS = {"min_cagr": 15.0, "min_trades": 3, "min_years": 2.0, "min_value": 10.0}
STRATEGY_FILTERS = {"min_trades": 3, "min_years": 2.0, "min_value": 10.0, "min_scripts": 50}


def write_results(con, folder):
    """Write every committed results file into folder. Returns {file name: rows}."""
    from pathlib import Path

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = {}
    with open(folder / "leaderboard-cagr15.csv", "w", newline="", encoding="utf-8") as handle:
        written["leaderboard-cagr15.csv"] = export_csv(con, handle, **RESULT_FILTERS)
    with open(folder / "leaderboard-best-per-script.csv", "w", newline="", encoding="utf-8") as handle:
        written["leaderboard-best-per-script.csv"] = export_csv(con, handle, best=True, **RESULT_FILTERS)
    with open(folder / "strategy-ranking-return-dd.csv", "w", newline="", encoding="utf-8") as handle:
        written["strategy-ranking-return-dd.csv"] = export_strategy_csv(handle, strategy_ranking(con, **STRATEGY_FILTERS))
    return written


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="top-leaderboard", description="Backtest every strategy on every stored script and index.")
    parser.add_argument("--db", help="DuckDB file (default: TOP_DB or ./data/nse.duckdb)")
    parser.add_argument("--workers", type=int, default=None, help="worker processes (default: up to 2)")
    parser.add_argument("--force", action="store_true", help="recompute symbols that are already current")
    parser.add_argument("--limit", type=int, default=None, help="only this many symbols (testing)")
    parser.add_argument("--export", metavar="CSV", help="write the stored leaderboard to this CSV instead of computing")
    parser.add_argument("--min-cagr", type=float, default=None, help="with --export: keep rows with CAGR above this %%")
    parser.add_argument("--min-trades", type=int, default=0, help="with --export: minimum trades")
    parser.add_argument("--best", action="store_true", help="with --export: only each script's best strategy")
    parser.add_argument("--min-years", type=float, default=0.0, help="with --export: minimum years tested")
    parser.add_argument("--min-value", type=float, default=None, help="with --export: minimum median daily traded value in ₹ lakh (indices exempt)")
    parser.add_argument("--strategies", metavar="CSV", help="write the strategy ranking (median total return / max DD across scripts) to this CSV")
    parser.add_argument("--results", metavar="DIR", help="compute (resuming), then write every committed results file into DIR")
    args = parser.parse_args(argv)
    if args.db:
        from pathlib import Path

        store.DB_PATH = Path(args.db)
        store._schema_ready = False
    if args.export:
        with store.session() as con, open(args.export, "w", newline="", encoding="utf-8") as handle:
            n = export_csv(con, handle, min_cagr=args.min_cagr, min_trades=args.min_trades, best=args.best, min_value=args.min_value, min_years=args.min_years)
        print(f"wrote {n:,} rows to {args.export}", flush=True)
        return 0
    if args.strategies:
        with store.session() as con, open(args.strategies, "w", newline="", encoding="utf-8") as handle:
            n = export_strategy_csv(handle, strategy_ranking(con, min_trades=args.min_trades or 3, min_years=args.min_years or 2.0,
                                                             min_value=10.0 if args.min_value is None else args.min_value))
        print(f"wrote {n} strategies to {args.strategies}", flush=True)
        return 0
    out = run_all(workers=args.workers, force=args.force, limit=args.limit,
                  progress=lambda done, total, symbol: print(f"  {done:>5}/{total} {symbol}", flush=True))
    print(out["message"], flush=True)
    if args.results:
        with store.session() as con:
            for name, rows in write_results(con, args.results).items():
                print(f"wrote {rows:,} rows to {args.results}/{name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
