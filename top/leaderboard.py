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
import math
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
PRIORITY = {"nifty50": 0, "nse_index": 1, "bse_index": 2, "nse_etf": 3, "bse_etf": 4, "nse": 5, "bse": 6}
UNIVERSE_GROUPS = {
    "all": None,
    "nifty50": ("nifty50",),
    "index": ("nse_index", "bse_index"),
    "etf": ("nse_etf", "bse_etf"),
    "nse": ("nifty50", "nse"),
    "bse": ("bse",),
}
SORTS = {
    "ratio": "ratio DESC NULLS LAST",
    "return_dd": "return_dd DESC NULLS LAST",
    "dsr": "dsr_z DESC NULLS LAST",
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
    if "ids" not in {c[1] for c in con.execute("PRAGMA table_info('leaderboard_done')").fetchall()}:
        # Before per-strategy tracking, a row meant "every strategy at the time was run". Record what was stored.
        con.execute("ALTER TABLE leaderboard_done ADD COLUMN ids VARCHAR")
        con.execute(
            """
            UPDATE leaderboard_done SET catalog_key = ?, ids = COALESCE(
                (SELECT string_agg(strategy, ',' ORDER BY strategy) FROM leaderboard l WHERE l.symbol = leaderboard_done.symbol), '')
            """,
            [catalog_key()],
        )
    con.execute("CREATE TABLE IF NOT EXISTS leaderboard_trials (symbol VARCHAR PRIMARY KEY, trials INTEGER, sr_std DOUBLE, sr_star DOUBLE)")
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
    has_rows = con.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0] > 0
    if has_rows and con.execute("SELECT COUNT(*) FROM leaderboard_liquidity").fetchone()[0] == 0:
        refresh_liquidity(con)
    if has_rows and con.execute("SELECT COUNT(*) FROM leaderboard_trials").fetchone()[0] == 0:
        refresh_trials(con)
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
              -- Only the last ~14 months can hold a symbol's latest 250 bars; reading all history spilled to disk.
              AND ts >= (SELECT MAX(ts) FROM bars) - INTERVAL 420 DAY
        ) WHERE rn <= 250 GROUP BY symbol
        """
    )


# ---------------------------------------------------------------- probabilistic and deflated Sharpe

EULER_GAMMA = 0.5772156649015329


def norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def norm_ppf(p):
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > hi:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def expected_max_sharpe(sr_std, trials):
    """Expected best Sharpe among `trials` unskilled strategies whose Sharpes have spread sr_std (Bailey & López de Prado)."""
    if trials < 2 or not sr_std:
        return 0.0
    return sr_std * ((1 - EULER_GAMMA) * norm_ppf(1 - 1 / trials) + EULER_GAMMA * norm_ppf(1 - 1 / (trials * math.e)))


def refresh_trials(con):
    """Per script: number of strategies tried, spread of their daily Sharpes, and the luck threshold SR*."""
    from top.bhav import _copy_into_temp

    rows = con.execute(
        "SELECT symbol, COUNT(*), stddev_samp(sharpe / sqrt(252)) FROM leaderboard WHERE sharpe IS NOT NULL GROUP BY symbol"
    ).fetchall()
    out = [(symbol, int(n), float(std or 0.0), expected_max_sharpe(float(std or 0.0), int(n))) for symbol, n, std in rows]
    con.execute("DELETE FROM leaderboard_trials")
    if out:
        _copy_into_temp(con, "trials_in", "symbol VARCHAR, trials INTEGER, sr_std DOUBLE, sr_star DOUBLE", out)
        con.execute("INSERT INTO leaderboard_trials SELECT * FROM trials_in")


# z-scores for PSR and DSR, assuming normal daily returns: z = (SR - SR0) * sqrt(n - 1) / sqrt(1 + SR^2 / 2),
# with SR the daily Sharpe and n the tested days. PSR uses SR0 = 0, DSR uses SR0 = SR* for the script.
PSR_Z_SQL = "(l.sharpe / sqrt(252)) * sqrt(greatest(l.years * 252 - 1, 1)) / sqrt(1 + power(l.sharpe / sqrt(252), 2) / 2)"
DSR_Z_SQL = "(l.sharpe / sqrt(252) - COALESCE(t.sr_star, 0)) * sqrt(greatest(l.years * 252 - 1, 1)) / sqrt(1 + power(l.sharpe / sqrt(252), 2) / 2)"


def catalog_ids():
    from top.strategies import catalog

    return sorted(item["id"] for item in catalog())


def catalog_key():
    """Settings that, if changed, invalidate every stored row. New strategies don't: they are added per script."""
    return hashlib.sha1(f"{VERSION}|{CAPITAL}|{COST_BPS}".encode()).hexdigest()[:16]


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

    symbol, ts, o, h, l, c, v, *rest = payload
    only = set(rest[0]) if rest and rest[0] else None
    problem = data_problem(ts, c)
    if problem:
        return symbol, ts[-1], [], 0, problem, rest[0] if rest else None
    frame = Frame(ts, o, h, l, c, v)
    rows, errors = [], 0
    for item in STRATEGIES:
        if only is not None and item["id"] not in only:
            continue
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
    return symbol, ts[-1], rows, errors, None, rest[0] if rest else None


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
    wanted = set(catalog_ids())
    done = {} if force else {s: (d, k, set(filter(None, (i or "").split(","))))
                             for s, d, k, i in con.execute("SELECT symbol, last_day, catalog_key, ids FROM leaderboard_done").fetchall()}
    todo, current = [], 0
    for symbol, universe, _, last, turnover in rows:
        previous = done.get(symbol)
        only = None
        if previous and previous[0] == last and previous[1] == key:
            missing = wanted - previous[2]
            if not missing:
                current += 1
                continue
            only = tuple(sorted(missing))
        todo.append((PRIORITY.get(universe, 9), -(turnover or 0), symbol, only))
    # Partial updates (only newly added strategies) are cheap, so they go first.
    todo.sort(key=lambda x: (x[3] is None, x[0], x[1], x[2]))
    return [(symbol, only) for _, _, symbol, only in todo], current, len(rows)


def _load(con, symbol, only=None):
    bars = store.load_bars(con, symbol)
    return (symbol, [b["time"] for b in bars], [b["open"] for b in bars], [b["high"] for b in bars],
            [b["low"] for b in bars], [b["close"] for b in bars], [b["volume"] for b in bars], only)


def save(con, results, key):
    from top.bhav import _copy_into_temp

    stamp = datetime.now().isoformat(timespec="seconds")
    ensure_tables(con)
    every = catalog_ids()
    flat = [(*row, stamp) for _, _, rows, *_ in results for row in rows]
    full = [r for r in results if not (len(r) > 5 and r[5])]
    partial = [r for r in results if len(r) > 5 and r[5]]
    previous = {}
    if partial:
        placeholders = ", ".join("?" for _ in partial)
        previous = dict(con.execute(f"SELECT symbol, ids FROM leaderboard_done WHERE symbol IN ({placeholders})", [r[0] for r in partial]).fetchall())
    done_rows = []
    for symbol, last, rows, *rest in full:
        done_rows.append((symbol, last, key, len(rows), stamp, ",".join(every)))
    for symbol, last, rows, _errors, _problem, only in partial:
        ids = sorted(set(filter(None, (previous.get(symbol) or "").split(","))) | set(only))
        done_rows.append((symbol, last, key, len(rows), stamp, ",".join(ids)))
    _copy_into_temp(con, "lb_done_in", "symbol VARCHAR, last_day DATE, catalog_key VARCHAR, strategies INTEGER, computed_at TIMESTAMP, ids VARCHAR", done_rows)
    if full:
        _copy_into_temp(con, "lb_full_in", "symbol VARCHAR", [(r[0],) for r in full])
        con.execute("DELETE FROM leaderboard WHERE symbol IN (SELECT symbol FROM lb_full_in)")
    if partial:
        _copy_into_temp(con, "lb_part_in", "symbol VARCHAR, strategy VARCHAR", [(r[0], sid) for r in partial for sid in r[5]])
        con.execute("DELETE FROM leaderboard USING lb_part_in p WHERE leaderboard.symbol = p.symbol AND leaderboard.strategy = p.strategy")
    if flat:
        _copy_into_temp(con, "lb_in", COLUMNS, flat)
        con.execute("INSERT INTO leaderboard SELECT * FROM lb_in")
    # Partial rows keep the stored strategy count up to date.
    con.execute("INSERT OR REPLACE INTO leaderboard_done SELECT * FROM lb_done_in")
    if partial:
        con.execute(
            """
            UPDATE leaderboard_done SET strategies = (SELECT COUNT(*) FROM leaderboard l WHERE l.symbol = leaderboard_done.symbol)
            WHERE symbol IN (SELECT symbol FROM lb_part_in)
            """
        )


def run_all(workers=None, force=False, limit=None, progress=None):
    """Compute the leaderboard. Blocking; use start() for the background version."""
    global _runner
    workers = max(1, int(workers or os.environ.get("TOP_WORKERS") or min(2, os.cpu_count() or 1)))
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
                refresh_trials(con)  # a run interrupted before its last step leaves these stale
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
                        payloads = [_load(con, symbol, only) for symbol, only in batch]
                    results = pool.map(payloads)
                    with store.session() as con:
                        save(con, results, key)
                    done += len(batch)
                    errors += sum(r[3] for r in results)
                    excluded += sum(1 for r in results if len(r) > 4 and r[4])
                    elapsed = time.time() - began
                    rate = done / elapsed if elapsed else 0
                    _set(done=done, errors=errors, excluded=excluded, symbol=batch[-1][0], rate_per_min=round(rate * 60, 1),
                         eta_seconds=int((total - done) / rate) if rate else None,
                         message=f"{done:,} of {total:,} symbols")
                    if progress:
                        progress(done, total, batch[-1][0])
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
            refresh_trials(con)
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
              min_value=None, min_dsr=None):
    """SQL for the filtered leaderboard: (base query, args, order, filters without universe, their args)."""
    where = ["l.trades >= ?", "l.years >= ?", "l.ratio IS NOT NULL"]
    args = [int(min_trades), float(min_years)]
    if min_cagr is not None:
        where.append("l.cagr_pct > ?")
        args.append(float(min_cagr))
    if strategy:
        where.append("l.strategy = ?")
        args.append(strategy)
    if min_dsr:
        where.append(f"{DSR_Z_SQL} >= ?")
        args.append(norm_ppf(min(max(float(min_dsr), 0.1), 99.9) / 100))
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
               {PSR_Z_SQL} AS psr_z, {DSR_Z_SQL} AS dsr_z,
               s.name, COALESCE(s.universe, 'nifty50') AS universe, s.exchange, q.median_value_lakh
        FROM leaderboard l JOIN symbols s ON s.symbol = l.symbol LEFT JOIN leaderboard_liquidity q ON q.symbol = l.symbol
             LEFT JOIN leaderboard_trials t ON t.symbol = l.symbol
        WHERE {' AND '.join(where)}
    """
    if best:
        # Each script's best row follows the chosen sort (CAGR ÷ DD by default).
        base += f" QUALIFY row_number() OVER (PARTITION BY l.symbol ORDER BY {order}, l.strategy) = 1"
    return base, args, order, chip_where, chip_args


CSV_COLUMNS = ("symbol", "name", "universe", "exchange", "median_value_lakh", "strategy", "strategy_name", "section", "ratio", "return_dd", "psr_pct", "dsr_pct", "cagr_pct", "max_dd_pct",
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
            row = _probabilities(dict(zip(cols, raw)))
            meta = names.get(row["strategy"], {})
            row["strategy_name"] = meta.get("name", row["strategy"])
            row["section"] = meta.get("section", "")
            rank += 1
            writer.writerow((rank, *("" if row.get(c) is None else row.get(c) for c in CSV_COLUMNS)))
    return rank


def _probabilities(row):
    for key in ("psr", "dsr"):
        z = row.pop(f"{key}_z", None)
        row[f"{key}_pct"] = None if z is None else round(100 * norm_cdf(z), 1)
    return row


def query(con, min_cagr=15.0, universe="all", strategy=None, min_trades=1, min_years=0.0, search="",
          best=False, sort="ratio", limit=100, offset=0, min_value=None, min_dsr=None):
    """Ranked rows plus totals. Filters apply before ranking; best=True keeps each symbol's top row."""
    ensure_tables(con)
    base, args, order, chip_where, chip_args = _filtered(min_cagr, universe, strategy, min_trades, min_years, search, best, sort, min_value, min_dsr)
    total = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT symbol) FROM ({base})", args).fetchone()
    cursor = con.execute(f"SELECT * FROM ({base}) ORDER BY {order}, symbol, strategy LIMIT ? OFFSET ?", [*args, int(limit), int(offset)])
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r)) for r in cursor.fetchall()]
    for row in rows:
        _probabilities(row)
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
             LEFT JOIN leaderboard_trials t ON t.symbol = l.symbol
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
    "pct_dsr95": "pct_dsr95 DESC NULLS LAST",
    "scripts": "scripts DESC",
}
STRATEGY_COLUMNS = ("rank", "strategy", "strategy_name", "section", "creator", "scripts", "median_return_dd", "mean_return_dd",
                    "p25_return_dd", "p75_return_dd", "median_return_pct", "median_max_dd_pct", "median_cagr_pct", "median_cagr_dd",
                    "pct_profitable", "pct_beat_hold", "median_trades", "median_years", "pct_dsr95", "best_symbol", "best_return_dd")


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
               100.0 * avg(CASE WHEN dsr_z >= 1.6448536 THEN 1 ELSE 0 END) AS pct_dsr95,
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


# ---------------------------------------------------------------- top-N portfolio of one strategy

PORTFOLIO_STOCKS = ("nifty50", "nse", "bse")


def _curve_stats(values, days):
    """Total return, CAGR, max drawdown and CAGR ÷ |max DD| (5% floor) for a daily value series."""
    if len(values) < 2 or values[0] <= 0:
        return {}
    years = max(days / 365.25, 1 / 365.25)
    total = values[-1] / values[0] - 1
    cagr = (values[-1] / values[0]) ** (1 / years) - 1 if values[-1] > 0 else -1.0
    peak, dd = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    return {"start_value": round(values[0], 2), "final_value": round(values[-1], 2), "total_return_pct": round(total * 100, 2),
            "cagr_pct": round(cagr * 100, 2), "max_dd_pct": round(dd * 100, 2), "years": round(years, 2),
            "cagr_dd": round(cagr * 100 / max(abs(dd) * 100, DD_FLOOR), 3)}


def strategy_portfolio(con, strategy=None, n=20, per_stock=100_000.0, cost_bps=COST_BPS, sort="ratio",
                       min_trades=3, min_years=2.0, min_value=10.0):
    """Put `per_stock` into each of the top `n` stocks for one strategy and add up the money over time.

    strategy: a strategy id, or None for the #1 strategy of the By strategy ranking.
    The stocks are that strategy's best leaderboard rows (stocks only, by `sort`, default CAGR ÷ |max DD|),
    with the usual filters and one row per company (a company listed on NSE and BSE counts once).
    Each stock runs the strategy on its own ₹per_stock (signal at the close, fill at the next open, costs);
    money is never moved between stocks. Before a stock's test starts its money waits in cash.
    Because the stocks are chosen with hindsight from the same period, this is an in-sample best case.
    """
    from top.backtest import run
    from top.indicators import Frame
    from top.strategies import catalog, signal

    ensure_tables(con)
    names = {item["id"]: item for item in catalog()}
    if not strategy:
        ranking = strategy_ranking(con, **STRATEGY_FILTERS)
        if not ranking:
            # Small stores (or strict filters): rank on whatever has been computed.
            ranking = strategy_ranking(con, min_trades=0, min_years=0, min_value=0, min_scripts=1)
        if not ranking:
            raise ValueError("The leaderboard has no results yet. Run backtests first.")
        strategy = ranking[0]["strategy"]
    if strategy not in names:
        raise ValueError("unknown strategy")
    base, args, order, _, _ = _filtered(min_cagr=None, strategy=strategy, min_trades=min_trades, min_years=min_years,
                                        min_value=min_value, sort=sort)
    groups = ", ".join("?" for _ in PORTFOLIO_STOCKS)
    rows = con.execute(
        f"""
        SELECT r.symbol, r.name, r.universe, r.cagr_pct, r.max_dd_pct, r.ratio, r.total_return_pct,
               COALESCE(s.isin, b.isin) AS isin
        FROM ({base}) r JOIN symbols s ON s.symbol = r.symbol
        LEFT JOIN symbols b ON b.symbol = 'BSE:' || r.symbol AND r.universe = 'nifty50'
        WHERE r.universe IN ({groups})
        ORDER BY {order}, r.symbol
        """,
        [*args, *PORTFOLIO_STOCKS],
    ).fetchall()
    picked, companies = [], set()
    for symbol, name, universe, cagr, dd, ratio, total, isin in rows:
        company = (isin or "")[:7] or symbol
        if company in companies:
            continue
        companies.add(company)
        picked.append({"symbol": symbol, "name": name, "universe": universe, "leaderboard_cagr_pct": cagr,
                       "leaderboard_max_dd_pct": dd, "leaderboard_ratio": ratio})
        if len(picked) >= int(n):
            break
    if not picked:
        raise ValueError("No stocks pass the filters for this strategy.")
    curves = []
    for item in picked:
        bars = store.load_bars(con, item["symbol"])
        frame = Frame([b["time"] for b in bars], [b["open"] for b in bars], [b["high"] for b in bars],
                      [b["low"] for b in bars], [b["close"] for b in bars], [b["volume"] for b in bars])
        result = run(frame.ts, frame.o, frame.h, frame.l, frame.c, signal(strategy, frame, {}), capital=per_stock, cost_bps=cost_bps)
        curve = {p["time"]: p["value"] for p in result["equity"]}
        curves.append(curve)
        m = result["metrics"]
        item.update(final_value=round(result["equity"][-1]["value"], 2), start=result["start"], trades=m["trades"],
                    total_return_pct=m["total_return_pct"])
    dates = sorted(set().union(*curves))
    last = [None] * len(curves)
    equity = []
    for day in dates:
        total = 0.0
        for k, curve in enumerate(curves):
            if day in curve:
                last[k] = curve[day]
            total += per_stock if last[k] is None else last[k]
        equity.append({"time": day, "value": round(total, 2)})
    from datetime import date as _date

    span = (_date.fromisoformat(dates[-1]) - _date.fromisoformat(dates[0])).days
    stats = _curve_stats([p["value"] for p in equity], span)
    nifty = dict((str(t), c) for t, c in con.execute(
        "SELECT ts, close FROM bars WHERE symbol = 'IDX:NIFTY50' AND interval = '1d' AND ts >= CAST(? AS DATE) ORDER BY ts", [dates[0]]).fetchall())
    bench, first, level = [], None, None
    for day in dates:
        level = nifty.get(day, level)
        if level is not None:
            first = first or level
            bench.append({"time": day, "value": round(per_stock * len(picked) * level / first, 2)})
    bench_stats = _curve_stats([p["value"] for p in bench], span) if bench else {}
    peak, underwater = -math.inf, []
    for p in equity:
        peak = max(peak, p["value"])
        underwater.append({"time": p["time"], "value": round(100 * (p["value"] / peak - 1), 2)})
    picked.sort(key=lambda x: -x["final_value"])
    return {
        "strategy": strategy, "strategy_name": names[strategy]["name"], "n": len(picked), "per_stock": per_stock,
        "invested": per_stock * len(picked), "sort": sort, "metrics": stats, "benchmark": bench_stats,
        "stocks": picked, "equity": equity, "benchmark_equity": bench, "underwater": underwater,
        "start": dates[0], "end": dates[-1],
        "note": ("Stocks were chosen using their results over this same period, so this is an in-sample best case: "
                 "a real investor could not have known them in advance."),
    }


def export_portfolio_csv(handle, out):
    import csv

    writer = csv.writer(handle)
    m, b = out["metrics"], out["benchmark"]
    writer.writerow(["strategy", out["strategy"], out["strategy_name"]])
    writer.writerow(["stocks", out["n"], "per stock", out["per_stock"], "invested", out["invested"]])
    writer.writerow(["period", out["start"], out["end"], "years", m.get("years")])
    writer.writerow(["final value", m.get("final_value"), "total return %", m.get("total_return_pct")])
    writer.writerow(["CAGR %", m.get("cagr_pct"), "max drawdown %", m.get("max_dd_pct"), "CAGR / |max DD|", m.get("cagr_dd")])
    writer.writerow(["Nifty 50, same money", b.get("final_value"), "CAGR %", b.get("cagr_pct"), "max drawdown %", b.get("max_dd_pct"),
                     "CAGR / |max DD|", b.get("cagr_dd")])
    writer.writerow([])
    writer.writerow(["symbol", "name", "start", "trades", "final_value", "total_return_pct", "leaderboard_cagr_pct", "leaderboard_max_dd_pct", "leaderboard_ratio"])
    for s in out["stocks"]:
        writer.writerow([s["symbol"], s["name"], s["start"], s["trades"], s["final_value"], s["total_return_pct"],
                         s["leaderboard_cagr_pct"], s["leaderboard_max_dd_pct"], s["leaderboard_ratio"]])
    writer.writerow([])
    writer.writerow(["date", "portfolio_value", "nifty50_value"])
    bench = {p["time"]: p["value"] for p in out["benchmark_equity"]}
    for p in out["equity"]:
        writer.writerow([p["time"], p["value"], bench.get(p["time"], "")])
    return out["n"]


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
    with open(folder / "top20-portfolio.csv", "w", newline="", encoding="utf-8") as handle:
        written["top20-portfolio.csv"] = export_portfolio_csv(handle, strategy_portfolio(con))
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
    parser.add_argument("--min-dsr", type=float, default=None, help="with --export: minimum deflated Sharpe probability in %%")
    parser.add_argument("--min-value", type=float, default=None, help="with --export: minimum median daily traded value in ₹ lakh (indices exempt)")
    parser.add_argument("--strategies", metavar="CSV", help="write the strategy ranking (median total return / max DD across scripts) to this CSV")
    parser.add_argument("--portfolio", metavar="CSV", help="write the top-N portfolio of one strategy (default: the #1 strategy, top 20, ₹1 lakh each)")
    parser.add_argument("--strategy", default=None, help="with --portfolio: strategy id (default: #1 of the strategy ranking)")
    parser.add_argument("--top", type=int, default=20, help="with --portfolio: number of stocks")
    parser.add_argument("--per-stock", type=float, default=100_000.0, help="with --portfolio: rupees per stock")
    parser.add_argument("--results", metavar="DIR", help="compute (resuming), then write every committed results file into DIR")
    args = parser.parse_args(argv)
    if args.db:
        from pathlib import Path

        store.DB_PATH = Path(args.db)
        store._schema_ready = False
    if args.export:
        with store.session() as con, open(args.export, "w", newline="", encoding="utf-8") as handle:
            n = export_csv(con, handle, min_cagr=args.min_cagr, min_trades=args.min_trades, best=args.best, min_value=args.min_value, min_years=args.min_years, min_dsr=args.min_dsr)
        print(f"wrote {n:,} rows to {args.export}", flush=True)
        return 0
    if args.portfolio:
        with store.session() as con, open(args.portfolio, "w", newline="", encoding="utf-8") as handle:
            out = strategy_portfolio(con, strategy=args.strategy, n=args.top, per_stock=args.per_stock)
            export_portfolio_csv(handle, out)
        m = out["metrics"]
        print(f"{out['strategy_name']}: ₹{out['invested']:,.0f} in {out['n']} stocks → ₹{m['final_value']:,.0f} "
              f"({out['start']} to {out['end']}); CAGR {m['cagr_pct']}%, max DD {m['max_dd_pct']}%, CAGR ÷ |DD| {m['cagr_dd']}", flush=True)
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
