"""NSE and BSE indices from the exchanges' daily index files.

- NSE publishes `ind_close_all_DDMMYYYY.csv` every trading day: open, high, low, close
  and volume for every NSE index (Nifty 50, Bank Nifty, sectoral, thematic, strategy,
  India VIX, bond indices). The archive goes back well beyond five years.
- BSE publishes `INDEXSummary_DDMMYYYY.csv` (Sensex, BSE 100, 500, sectoral ...). Its
  archive only reaches back to roughly April 2025; the older-history API is blocked for
  scripts, so BSE indices have a shorter history.

Indices are stored as ordinary bars with symbols `IDX:<NAME>` (NSE) and
`IDX:BSE:<ID>` (BSE), universes `nse_index` and `bse_index`, kind `index`. They
are never split-adjusted.
"""

from __future__ import annotations

import csv
import io
import re
import time
from datetime import date, datetime

from top import store
from top.bhav import PAUSE, Missing, _copy_into_temp, _get, _num, _weekdays, insert_rows

NSE_INDEX = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{dmy}.csv"
BSE_INDEX = "https://www.bseindia.com/bsedata/Index_Bhavcopy/INDEXSummary_{dmy}.csv"
NSE_SOURCE, BSE_SOURCE = "NSE-IDX", "BSE-IDX"
# BSE keeps about 18 months of index files; stop walking back after this many missing weekdays.
BSE_MISS_LIMIT = 15


def slug(text):
    return re.sub(r"[^A-Z0-9&]+", "", (text or "").upper())


def nse_symbol(name):
    return f"IDX:{slug(name)}"


def bse_symbol(index_id):
    return f"IDX:BSE:{slug(index_id)}"


def parse_nse_index(text):
    if not text.lstrip("\ufeff").startswith("Index Name"):
        raise Missing("not an NSE index file")
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        name = (r.get("Index Name") or "").strip()
        close = _num(r.get("Closing Index Value"))
        if not name or not close or close <= 0:
            continue
        o, h, l = (_num(r.get(k)) for k in ("Open Index Value", "High Index Value", "Low Index Value"))
        o = o if o and o > 0 else close
        h = max(h if h and h > 0 else close, o, close)
        l = min(l if l and l > 0 else close, o, close)
        volume = _num(r.get("Volume"))
        out.append({"symbol": nse_symbol(name), "name": name, "open": o, "high": h, "low": l, "close": close,
                    "volume": int(volume) if volume and volume > 0 else 0})
    return out


def parse_bse_index(text):
    if not text.lstrip("\ufeff").startswith("IndexCode"):
        raise Missing("not a BSE index file")
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        index_id = (r.get("IndexID") or "").strip()
        close = _num(r.get("ClosePrice"))
        if not index_id or not close or close <= 0:
            continue
        o, h, l = (_num(r.get(k)) for k in ("OpenPrice", "HighPrice", "LowPrice"))
        o = o if o and o > 0 else close
        h = max(h if h and h > 0 else close, o, close)
        l = min(l if l and l > 0 else close, o, close)
        name = (r.get("IndexName") or index_id).strip()
        out.append({"symbol": bse_symbol(index_id), "name": name, "open": o, "high": h, "low": l, "close": close, "volume": 0})
    return out


def fetch_nse_index(day):
    blob = _get(NSE_INDEX.format(dmy=day.strftime("%d%m%Y")), referer="https://www.nseindia.com/")
    return parse_nse_index(blob.decode("utf-8", "replace"))


def fetch_bse_index(day):
    blob = _get(BSE_INDEX.format(dmy=day.strftime("%d%m%Y")), referer="https://www.bseindia.com/")
    return parse_bse_index(blob.decode("utf-8", "replace"))


def save_index_listings(con, rows, exchange):
    universe = "nse_index" if exchange == "NSE" else "bse_index"
    seen, listings = set(), []
    for r in rows:
        if r["symbol"] in seen:
            continue
        seen.add(r["symbol"])
        listings.append((r["symbol"], r["name"], f"{exchange} index", exchange, "index", universe, r["symbol"].split(":")[-1], "", ""))
    if not listings:
        return 0
    _copy_into_temp(con, "index_in",
                    "symbol VARCHAR, name VARCHAR, sector VARCHAR, exchange VARCHAR, kind VARCHAR, universe VARCHAR, code VARCHAR, isin VARCHAR, grp VARCHAR",
                    listings)
    con.execute(
        """
        INSERT INTO symbols (symbol, yahoo, name, sector, weight, rank, exchange, kind, universe, code, isin, grp)
        SELECT symbol, NULL, name, sector, NULL, NULL, exchange, kind, universe, code, NULL, NULL FROM index_in
        ON CONFLICT (symbol) DO UPDATE SET name = excluded.name, sector = excluded.sector, exchange = excluded.exchange,
            kind = excluded.kind, universe = excluded.universe, code = excluded.code
        """
    )
    return len(listings)


def _ingest(con, day, rows, exchange, source):
    save_index_listings(con, rows, exchange)
    count = insert_rows(con, day, [(r["symbol"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows])
    con.execute("INSERT OR IGNORE INTO bhav_days VALUES (?, ?, ?)", [source, day.isoformat(), count])
    return count


def _record_missing(con, day, source, today):
    # Recent days may simply not be published yet; only settle days older than a few days.
    if (today - day).days > 4:
        con.execute("INSERT OR IGNORE INTO bhav_days VALUES (?, ?, 0)", [source, day.isoformat()])


def sync_indices(years=5, today=None, progress=None):
    """Fill or refresh NSE and BSE indices. Safe to re-run; finished days are skipped."""
    today = today or date.today()
    start = date(today.year - years, today.month, min(today.day, 28))
    with store.session() as con:
        store.ensure_schema(con)
        done = {(src, d) for src, d in con.execute(
            "SELECT exchange, day FROM bhav_days WHERE exchange IN (?, ?)", [NSE_SOURCE, BSE_SOURCE]).fetchall()}
    days = list(_weekdays(start, today))
    nse_pending = [d for d in days if (NSE_SOURCE, d) not in done]
    bse_pending = sorted((d for d in days if (BSE_SOURCE, d) not in done), reverse=True)
    total = len(nse_pending) + len(bse_pending)
    store.set_bhav_status(syncing=True, done=0, total=total, message=f"indices: {total} day files to check")
    n, bars = 0, {"NSE": 0, "BSE": 0}
    try:
        for day in nse_pending:
            n += 1
            try:
                rows = fetch_nse_index(day)
            except Missing:
                with store.session() as con:
                    _record_missing(con, day, NSE_SOURCE, today)
                continue
            except RuntimeError as exc:
                store.set_bhav_status(message=f"NSE indices {day}: {exc}")
                continue
            finally:
                time.sleep(PAUSE)
            with store.session() as con:
                bars["NSE"] += _ingest(con, day, rows, "NSE", NSE_SOURCE)
            store.set_bhav_status(done=n, last_day=day.isoformat(), message=f"NSE indices {day}: {len(rows)}")
            if progress:
                progress("NSE", day, n, total)
        misses = 0
        for day in bse_pending:
            n += 1
            try:
                rows = fetch_bse_index(day)
                misses = 0
            except Missing:
                misses += 1
                with store.session() as con:
                    _record_missing(con, day, BSE_SOURCE, today)
                if misses >= BSE_MISS_LIMIT:
                    with store.session() as con:
                        for older in bse_pending:
                            if older < day:
                                _record_missing(con, older, BSE_SOURCE, today)
                    break
                continue
            except RuntimeError as exc:
                store.set_bhav_status(message=f"BSE indices {day}: {exc}")
                continue
            finally:
                time.sleep(PAUSE)
            with store.session() as con:
                bars["BSE"] += _ingest(con, day, rows, "BSE", BSE_SOURCE)
            store.set_bhav_status(done=n, last_day=day.isoformat(), message=f"BSE indices {day}: {len(rows)}")
            if progress:
                progress("BSE", day, n, total)
        with store.session() as con:
            stamp = datetime.now(store.IST).isoformat(timespec="seconds")
            con.execute("INSERT INTO meta VALUES ('index_last_sync', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", [stamp])
        store.set_bhav_status(syncing=False, message=f"indices ready: {bars['NSE']} NSE and {bars['BSE']} BSE new bars")
        return {"nse_bars": bars["NSE"], "bse_bars": bars["BSE"], "days": total}
    except Exception as exc:  # noqa: BLE001
        store.set_bhav_status(syncing=False, message=f"indices failed: {exc}")
        raise

