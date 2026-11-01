"""BSE equities and NSE / BSE ETFs from the exchanges' daily bhavcopy files.

One file per trading day lists every traded security, so five years of history for
~5,000 BSE stocks and ~400 ETFs needs ~1,250 downloads per exchange instead of
thousands of per-symbol requests.

Prices in bhavcopies are not adjusted for splits or bonus issues. Adjustments are
stored separately (table `adjustments`) and applied when bars are read:

- NSE corporate actions ("Face Value Split", "Bonus a:b", consolidations), matched to
  BSE stocks by the ISIN issuer code (first 7 characters) and to ETFs by symbol.
- For BSE-only names, an overnight gap of at least 40% that matches a standard split or
  bonus ratio. Most BSE-only stocks have 2–20% price bands, so such gaps are almost
  always corporate actions. These are labelled source='gap'.
"""

from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from top import store

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
BSE_NEW = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV"
BSE_OLD = "https://www.bseindia.com/download/BhavCopy/Equity/EQ{dmy}_CSV.ZIP"
NSE_NEW = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
NSE_OLD = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{yyyy}/{mon}/cm{dd}{mon}{yyyy}bhav.csv.zip"
NSE_ETF_LIST = "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv"
NSE_CA = "https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date={start}&to_date={end}"
NEW_FORMAT_FROM = date(2024, 7, 8)
PAUSE = 0.25

SPLIT_RATIOS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 20.0, 25.0, 50.0, 100.0]


# ---------------------------------------------------------------- download helpers

class Missing(Exception):
    """No file for this day (holiday, weekend, or not published yet)."""


def _get(url, referer=None, timeout=40, tries=3):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise Missing(url) from exc
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _zip_text(blob):
    if blob[:2] != b"PK":
        raise Missing("not a zip (holiday page)")
    archive = zipfile.ZipFile(io.BytesIO(blob))
    return archive.read(archive.namelist()[0]).decode("utf-8", "replace")


# ---------------------------------------------------------------- parsers

def parse_bse_new(text):
    if not text.startswith("TradDt"):
        raise Missing("not a BSE bhavcopy")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        close = _num(r.get("ClsPric"))
        if not close or close <= 0:
            continue
        out.append({
            "code": (r.get("FinInstrmId") or "").strip(), "ticker": (r.get("TckrSymb") or "").strip().upper(),
            "isin": (r.get("ISIN") or "").strip(), "name": (r.get("FinInstrmNm") or "").strip(), "group": (r.get("SctySrs") or "").strip(),
            "open": _num(r.get("OpnPric")) or close, "high": _num(r.get("HghPric")) or close, "low": _num(r.get("LwPric")) or close,
            "close": close, "prev_close": _num(r.get("PrvsClsgPric")), "volume": int(_num(r.get("TtlTradgVol")) or 0),
        })
    return out


def parse_bse_old(text):
    if not text.startswith("SC_CODE"):
        raise Missing("not a BSE bhavcopy")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        close = _num(r.get("CLOSE"))
        if not close or close <= 0:
            continue
        out.append({
            "code": (r.get("SC_CODE") or "").strip(), "ticker": None, "isin": None, "name": (r.get("SC_NAME") or "").strip(),
            "group": (r.get("SC_GROUP") or "").strip(), "open": _num(r.get("OPEN")) or close, "high": _num(r.get("HIGH")) or close,
            "low": _num(r.get("LOW")) or close, "close": close, "prev_close": _num(r.get("PREVCLOSE")), "volume": int(_num(r.get("NO_OF_SHRS")) or 0),
        })
    return out


def parse_nse_new(text):
    if not text.startswith("TradDt"):
        raise Missing("not an NSE bhavcopy")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        close = _num(r.get("ClsPric"))
        if not close or close <= 0:
            continue
        out.append({
            "ticker": (r.get("TckrSymb") or "").strip().upper(), "series": (r.get("SctySrs") or "").strip(), "isin": (r.get("ISIN") or "").strip(),
            "name": (r.get("FinInstrmNm") or "").strip(), "open": _num(r.get("OpnPric")) or close, "high": _num(r.get("HghPric")) or close,
            "low": _num(r.get("LwPric")) or close, "close": close, "prev_close": _num(r.get("PrvsClsgPric")), "volume": int(_num(r.get("TtlTradgVol")) or 0),
        })
    return out


def parse_nse_old(text):
    if not text.startswith("SYMBOL"):
        raise Missing("not an NSE bhavcopy")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        close = _num(r.get("CLOSE"))
        if not close or close <= 0:
            continue
        out.append({
            "ticker": (r.get("SYMBOL") or "").strip().upper(), "series": (r.get("SERIES") or "").strip(), "isin": (r.get("ISIN") or "").strip(),
            "name": None, "open": _num(r.get("OPEN")) or close, "high": _num(r.get("HIGH")) or close, "low": _num(r.get("LOW")) or close,
            "close": close, "prev_close": _num(r.get("PREVCLOSE")), "volume": int(_num(r.get("TOTTRDQTY")) or 0),
        })
    return out


def fetch_bse(day):
    ymd, dmy = day.strftime("%Y%m%d"), day.strftime("%d%m%y")
    tries = [("new", BSE_NEW.format(ymd=ymd)), ("old", BSE_OLD.format(dmy=dmy))]
    if day < NEW_FORMAT_FROM:
        tries.reverse()
    for kind, url in tries:
        try:
            blob = _get(url, referer="https://www.bseindia.com/")
            return parse_bse_new(blob.decode("utf-8", "replace")) if kind == "new" else parse_bse_old(_zip_text(blob))
        except Missing:
            time.sleep(PAUSE)
    raise Missing(f"BSE {day}")


def fetch_nse(day):
    ymd = day.strftime("%Y%m%d")
    mon = day.strftime("%b").upper()
    tries = [("new", NSE_NEW.format(ymd=ymd)), ("old", NSE_OLD.format(yyyy=day.year, mon=mon, dd=day.strftime("%d")))]
    if day < NEW_FORMAT_FROM:
        tries.reverse()
    for kind, url in tries:
        try:
            text = _zip_text(_get(url))
            return parse_nse_new(text) if kind == "new" else parse_nse_old(text)
        except Missing:
            time.sleep(PAUSE)
    raise Missing(f"NSE {day}")


def fetch_nse_etf_list():
    text = _get(NSE_ETF_LIST).decode("utf-8", "replace")
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        symbol = (r.get("Symbol") or "").strip().upper()
        if symbol:
            out[symbol] = {"name": (r.get("Underlying Asset") or r.get("SecurityName") or symbol).strip(), "isin": (r.get("ISINNumber") or "").strip(),
                           "underlying": (r.get("ETF Underlying") or "").strip()}
    return out


# ---------------------------------------------------------------- listings

def _clean_ticker(text):
    return re.sub(r"[^A-Z0-9&\-_.]", "", text.upper())


def classify_bse(row):
    """'stock' for equity shares (ISIN INE…01…), 'etf' for fund units (INF…), else None."""
    isin = row.get("isin") or ""
    if isin.startswith("INF"):
        return "etf"
    if isin.startswith("INE") and isin[7:9] == "01":
        return "stock"
    return None


def build_listings(bse_rows, nse_rows, nse_etfs):
    """Symbols for the extended universe from the latest day's files."""
    listings = []
    nse_etf_isins = set()
    for row in nse_rows:
        if row["ticker"] in nse_etfs and row.get("series") == "EQ":
            info = nse_etfs[row["ticker"]]
            nse_etf_isins.add(row["isin"])
            listings.append({"symbol": f"NSE:{row['ticker']}", "name": row.get("name") or info["name"], "sector": info.get("underlying") or "ETF",
                             "exchange": "NSE", "kind": "etf", "universe": "nse_etf", "code": row["ticker"], "isin": row["isin"], "grp": "ETF"})
    seen = set()
    for row in bse_rows:
        kind = classify_bse(row)
        if kind is None or not row.get("ticker"):
            continue
        if kind == "etf" and row["isin"] in nse_etf_isins:
            continue  # the NSE line is usually more liquid
        symbol = f"BSE:{_clean_ticker(row['ticker'])}"
        if symbol in seen:
            symbol = f"BSE:{row['code']}"
        seen.add(symbol)
        listings.append({"symbol": symbol, "name": row["name"].title() if row["name"].isupper() else row["name"],
                         "sector": f"BSE group {row['group']}" if kind == "stock" else "ETF", "exchange": "BSE", "kind": kind,
                         "universe": "bse" if kind == "stock" else "bse_etf", "code": row["code"], "isin": row["isin"], "grp": row["group"]})
    return listings


def _copy_into_temp(con, name, columns, rows):
    """Bulk-load rows into a fresh temp table via CSV + COPY (row inserts are very slow on old CPUs)."""
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(f"CREATE TEMP TABLE {name} ({columns})")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as handle:
        path = handle.name
        csv.writer(handle).writerows(rows)
    try:
        escaped = path.replace("'", "''")
        con.execute(f"COPY {name} FROM '{escaped}' (HEADER false)")
    finally:
        Path(path).unlink(missing_ok=True)


def save_listings(con, listings):
    _copy_into_temp(
        con, "listing_in",
        "symbol VARCHAR, name VARCHAR, sector VARCHAR, exchange VARCHAR, kind VARCHAR, universe VARCHAR, code VARCHAR, isin VARCHAR, grp VARCHAR",
        [(x["symbol"], x["name"], x["sector"], x["exchange"], x["kind"], x["universe"], x["code"], x["isin"], x["grp"]) for x in listings],
    )
    con.execute(
        """
        INSERT INTO symbols (symbol, yahoo, name, sector, weight, rank, exchange, kind, universe, code, isin, grp)
        SELECT symbol, NULL, name, sector, NULL, NULL, exchange, kind, universe, code, isin, grp FROM listing_in
        ON CONFLICT (symbol) DO UPDATE SET name = excluded.name, sector = excluded.sector, exchange = excluded.exchange,
            kind = excluded.kind, universe = excluded.universe, code = excluded.code, isin = excluded.isin, grp = excluded.grp
        """
    )


# ---------------------------------------------------------------- ingestion

def insert_rows(con, day, rows):
    """rows: (symbol, open, high, low, close, volume). Existing bars are kept."""
    if not rows:
        return 0
    con.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS bhav_in (
            symbol VARCHAR, interval VARCHAR, ts DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT
        )
        """
    )
    con.execute("DELETE FROM bhav_in")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as handle:
        path = handle.name
        writer = csv.writer(handle)
        iso = day.isoformat()
        for symbol, o, h, l, c, v in rows:
            writer.writerow((symbol, store.INTERVAL, iso, o, h, l, c, v))
    try:
        escaped = path.replace("'", "''")
        con.execute(f"COPY bhav_in FROM '{escaped}' (HEADER false)")
        con.execute("INSERT OR IGNORE INTO bars SELECT * FROM bhav_in")
    finally:
        Path(path).unlink(missing_ok=True)
    return len(rows)


def ingest_day(con, day, bse_rows, nse_rows, maps):
    bse_by_code, nse_by_ticker = maps
    out = []
    for r in bse_rows or []:
        symbol = bse_by_code.get(r["code"])
        if symbol:
            out.append((symbol, r["open"], r["high"], r["low"], r["close"], r["volume"]))
    for r in nse_rows or []:
        symbol = nse_by_ticker.get(r["ticker"])
        if symbol and r.get("series") == "EQ":
            out.append((symbol, r["open"], r["high"], r["low"], r["close"], r["volume"]))
    return insert_rows(con, day, out)


def _maps(con):
    rows = con.execute("SELECT symbol, universe, code FROM symbols WHERE universe IN ('bse', 'bse_etf', 'nse_etf')").fetchall()
    bse = {code: symbol for symbol, universe, code in rows if universe in ("bse", "bse_etf") and code}
    nse = {code: symbol for symbol, universe, code in rows if universe == "nse_etf" and code}
    return bse, nse


def _weekdays(start, end):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


# ---------------------------------------------------------------- corporate actions and adjustments

_SPLIT = re.compile(r"(?:split|sub-division|consolidation)[^|]*?from\s+(?:rs|re)\.?\s*([\d.]+)[^|]*?to\s+(?:rs|re)\.?\s*([\d.]+)", re.I)
_BONUS = re.compile(r"bonus\s+(\d+)\s*:\s*(\d+)", re.I)


def action_factor(subject):
    """Price factor for a corporate-action subject, or None. Prices before the ex-date are divided by it."""
    text = subject or ""
    m = _SPLIT.search(text)
    if m:
        old, new = float(m.group(1)), float(m.group(2))
        if old > 0 and new > 0 and old != new:
            return old / new
    m = _BONUS.search(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > 0 and b > 0:
            return (a + b) / b
    return None


def fetch_corporate_actions(start, end):
    """NSE corporate actions with a price factor, between two dates, in monthly windows."""
    out = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        nxt = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        stop = min(nxt - timedelta(days=1), end)
        url = NSE_CA.format(start=cursor.strftime("%d-%m-%Y"), end=stop.strftime("%d-%m-%Y"))
        try:
            data = json.loads(_get(url, referer="https://www.nseindia.com/companies-listing/corporate-filings-actions").decode("utf-8", "replace"))
        except (Missing, RuntimeError, ValueError, urllib.error.HTTPError):
            data = []
        for item in data if isinstance(data, list) else []:
            factor = action_factor(item.get("subject"))
            if not factor:
                continue
            try:
                ex = datetime.strptime(item.get("exDate", ""), "%d-%b-%Y").date()
            except ValueError:
                continue
            out.append({"symbol": (item.get("symbol") or "").upper(), "isin": item.get("isin") or "", "ex_date": ex, "factor": factor,
                        "subject": (item.get("subject") or "")[:200]})
        cursor = nxt
        time.sleep(PAUSE)
    return out


def save_corporate_actions(con, actions):
    if not actions:
        return
    _copy_into_temp(con, "ca_in", "symbol VARCHAR, isin VARCHAR, ex_date DATE, factor DOUBLE, subject VARCHAR",
                    [(a["symbol"], a["isin"], a["ex_date"].isoformat(), a["factor"], a["subject"]) for a in actions])
    con.execute("INSERT OR IGNORE INTO corporate_actions SELECT * FROM ca_in")


def gap_factor(prev_close, open_, close):
    """A standard split/bonus ratio if both the open and the close gapped by it, else None."""
    if not (prev_close and open_ and close) or prev_close <= 0 or open_ <= 0 or close <= 0:
        return None
    r_open, r_close = prev_close / open_, prev_close / close
    for k in SPLIT_RATIOS:
        for target in (k, 1 / k):
            if abs(r_open / target - 1) <= 0.12 and abs(r_close / target - 1) <= 0.15 and (target >= 1.4 or target <= 1 / 1.4):
                return target
    return None


def rebuild_adjustments(con):
    """Recreate the adjustments table from corporate actions plus the gap rule."""
    con.execute("DELETE FROM adjustments")
    symbols = con.execute("SELECT symbol, universe, code, isin FROM symbols WHERE universe IN ('bse', 'bse_etf', 'nse_etf')").fetchall()
    by_issuer, by_code = {}, {}
    for symbol, universe, code, isin in symbols:
        if universe == "bse" and isin and isin.startswith("INE"):
            by_issuer.setdefault(isin[:7], []).append(symbol)
        if universe == "nse_etf" and code:
            by_code[code] = symbol
    combined = {}
    for ca_symbol, isin, ex_date, factor, subject in con.execute("SELECT symbol, isin, ex_date, factor, subject FROM corporate_actions").fetchall():
        targets = list(by_issuer.get((isin or "")[:7], [])) if (isin or "").startswith("INE") else []
        if ca_symbol in by_code:
            targets.append(by_code[ca_symbol])
        for symbol in targets:
            key = (symbol, ex_date)
            f, notes = combined.get(key, (1.0, []))
            combined[key] = (f * factor, notes + [subject])
    covered = {}
    for (symbol, ex_date), (factor, notes) in combined.items():
        covered.setdefault(symbol, []).append(ex_date)
    rows = [(symbol, ex.isoformat(), factor, "nse_ca", "; ".join(notes)[:300]) for (symbol, ex), (factor, notes) in combined.items()]
    gaps = con.execute(
        """
        SELECT symbol, ts, prev_close, open, close FROM (
            SELECT b.symbol, b.ts, b.open, b.close, lag(b.close) OVER (PARTITION BY b.symbol ORDER BY b.ts) AS prev_close
            FROM bars b JOIN symbols s ON s.symbol = b.symbol
            WHERE b.interval = ? AND s.universe IN ('bse', 'bse_etf', 'nse_etf')
        )
        WHERE prev_close IS NOT NULL AND open > 0 AND (prev_close / open >= 1.35 OR prev_close / open <= 0.74)
        """,
        [store.INTERVAL],
    ).fetchall()
    for symbol, ts, prev_close, open_, close in gaps:
        if any(abs((ts - ex).days) <= 5 for ex in covered.get(symbol, [])):
            continue
        factor = gap_factor(prev_close, open_, close)
        if factor:
            rows.append((symbol, ts.isoformat(), factor, "gap", f"overnight gap {prev_close:.2f} -> {open_:.2f}"))
    if rows:
        _copy_into_temp(con, "adj_in", "symbol VARCHAR, ex_date DATE, factor DOUBLE, source VARCHAR, note VARCHAR", rows)
        con.execute("INSERT OR IGNORE INTO adjustments SELECT * FROM adj_in")
    return len(rows)


# ---------------------------------------------------------------- sync

def _latest_files(today):
    """The most recent day with both a BSE and an NSE file (looks back up to 10 days)."""
    day = today
    for _ in range(10):
        if day.weekday() < 5:
            try:
                bse = fetch_bse(day)
                nse = fetch_nse(day)
                return day, bse, nse
            except Missing:
                pass
        day -= timedelta(days=1)
    raise RuntimeError("no recent bhavcopy found")


def sync_bhav(years=5, today=None, progress=None):
    """Fill or refresh BSE stocks and ETFs. Safe to re-run; finished days are skipped."""
    today = today or date.today()
    store.set_bhav_status(syncing=True, done=0, total=0, message="finding the latest bhavcopy")
    try:
        latest_day, bse_rows, nse_rows = _latest_files(today)
        etfs = fetch_nse_etf_list()
        # Union of the last five trading days, so thinly traded names that skipped a day are kept.
        listing_rows = list(bse_rows)
        codes = {r["code"] for r in listing_rows}
        day, extra = latest_day, 0
        while extra < 4:
            day -= timedelta(days=1)
            if day.weekday() >= 5 or (latest_day - day).days > 14:
                if (latest_day - day).days > 14:
                    break
                continue
            try:
                for r in fetch_bse(day):
                    if r["code"] not in codes and r.get("ticker"):
                        listing_rows.append(r)
                        codes.add(r["code"])
                extra += 1
            except Missing:
                pass
            time.sleep(PAUSE)
        listings = build_listings(listing_rows, nse_rows, etfs)
        with store.session() as con:
            store.ensure_schema(con)
            save_listings(con, listings)
            maps = _maps(con)
            done_days = {d for (d,) in con.execute("SELECT DISTINCT day FROM bhav_days").fetchall()}
            first_bar = con.execute("SELECT MIN(day) FROM bhav_days WHERE rows > 0").fetchone()[0]
        start = date(today.year - years, today.month, min(today.day, 28))
        pending = [d for d in _weekdays(start, latest_day) if d not in done_days]
        store.set_bhav_status(total=len(pending), message=f"{len(listings)} listings; {len(pending)} days to fetch")
        new_rows = 0
        for n, day in enumerate(pending, start=1):
            if day == latest_day:
                b_rows, n_rows = bse_rows, nse_rows
            else:
                b_rows = n_rows = None
                try:
                    b_rows = fetch_bse(day)
                except Missing:
                    pass
                except RuntimeError as exc:
                    store.set_bhav_status(message=f"{day}: {exc}")
                    continue
                try:
                    n_rows = fetch_nse(day)
                except Missing:
                    pass
                except RuntimeError as exc:
                    store.set_bhav_status(message=f"{day}: {exc}")
                    continue
            with store.session() as con:
                count = ingest_day(con, day, b_rows, n_rows, maps) if (b_rows or n_rows) else 0
                con.execute("INSERT OR IGNORE INTO bhav_days VALUES ('BSE+NSE', ?, ?)", [day.isoformat(), count])
            new_rows += count
            store.set_bhav_status(done=n, last_day=day.isoformat(), message=f"{day}: {count} bars")
            if progress:
                progress(day, n, len(pending), count)
            time.sleep(PAUSE)
        store.set_bhav_status(message="corporate actions")
        ca_start = start if first_bar is None else latest_day - timedelta(days=120)
        actions = fetch_corporate_actions(ca_start, latest_day + timedelta(days=7))
        with store.session() as con:
            save_corporate_actions(con, actions)
            adjustments = rebuild_adjustments(con)
            stamp = datetime.now(store.IST).isoformat(timespec="seconds")
            con.execute("INSERT INTO meta VALUES ('bhav_last_sync', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", [stamp])
        store.set_bhav_status(syncing=False, message=f"ready: {len(listings)} listings, {new_rows} new bars, {adjustments} adjustments")
        return {"listings": len(listings), "days": len(pending), "bars": new_rows, "adjustments": adjustments, "latest": latest_day.isoformat()}
    except Exception as exc:  # noqa: BLE001 - report and stop
        store.set_bhav_status(syncing=False, message=f"failed: {exc}")
        raise
