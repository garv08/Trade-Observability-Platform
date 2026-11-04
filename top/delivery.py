"""Delivery % from NSE's daily security-wise file, plus a daily FII/DII cash snapshot.

`sec_bhavdata_full_DDMMYYYY.csv` lists, for every NSE security, traded quantity and the
quantity marked for delivery. Delivery % is a ratio, so splits don't affect it. NSE tickers
map to TOP symbols as follows:

- Nifty 50: the symbol is the NSE ticker.
- NSE ETFs and NSE stocks: the `code` is the NSE ticker.
- BSE stocks: matched by ISIN through the latest NSE bhavcopy (ticker -> ISIN), so a
  company listed on both exchanges gets the same NSE delivery % on both symbols. Stocks
  listed only on BSE have no NSE delivery data.

NSE's FII/DII endpoint returns only the latest day, so the history in `fii_dii` builds up
from the day TOP first runs it.
"""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import date, datetime

from top import store
from top.bhav import PAUSE, Missing, _copy_into_temp, _get, _num, _weekdays, fetch_nse

DELIVERY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{dmy}.csv"
FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
# Bumped when the ticker map gains symbols, so every day is read once more (inserts are idempotent).
SOURCE = "NSE-DELIV2"


def ensure_tables(con):
    con.execute("CREATE TABLE IF NOT EXISTS delivery (symbol VARCHAR, ts DATE, traded BIGINT, delivered BIGINT, pct DOUBLE, PRIMARY KEY (symbol, ts))")
    con.execute(
        "CREATE TABLE IF NOT EXISTS fii_dii (day DATE, category VARCHAR, buy DOUBLE, sell DOUBLE, net DOUBLE, PRIMARY KEY (day, category))"
    )


def parse_delivery(text):
    """Rows (ticker, traded qty, delivered qty, delivery %) for EQ/BE series."""
    text = text.lstrip("\ufeff")
    if not text.startswith("SYMBOL"):
        raise Missing("not a security-wise delivery file")
    out = []
    reader = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(reader)]
    index = {name: i for i, name in enumerate(header)}
    for row in reader:
        if len(row) < len(header):
            continue
        series = row[index["SERIES"]].strip()
        if series not in ("EQ", "BE", "BZ"):
            continue
        pct = _num(row[index["DELIV_PER"]])
        traded = _num(row[index["TTL_TRD_QNTY"]])
        delivered = _num(row[index["DELIV_QTY"]])
        if pct is None or traded is None or delivered is None:
            continue
        out.append((row[index["SYMBOL"]].strip().upper(), int(traded), int(delivered), float(pct)))
    return out


def fetch_delivery(day):
    blob = _get(DELIVERY_URL.format(dmy=day.strftime("%d%m%Y")), referer="https://www.nseindia.com/")
    return parse_delivery(blob.decode("utf-8", "replace"))


def ticker_map(con, nse_rows):
    """NSE ticker -> list of TOP symbols, from the store's listings and an NSE bhavcopy (ticker, ISIN)."""
    rows = con.execute("SELECT symbol, universe, code, isin FROM symbols").fetchall()
    out = {}
    by_isin, by_issuer = {}, {}
    for symbol, universe, code, isin in rows:
        universe = universe or "nifty50"
        if universe == "nifty50":
            out.setdefault(symbol, []).append(symbol)
        elif universe in ("nse_etf", "nse") and code:
            out.setdefault(code, []).append(symbol)
        elif universe == "bse" and isin:
            by_isin[isin] = symbol
            by_issuer.setdefault(isin[:7], []).append(symbol)
    for r in nse_rows or []:
        ticker, isin = r.get("ticker"), r.get("isin") or ""
        if not ticker or r.get("series") not in ("EQ", "BE", "BZ"):
            continue
        symbol = by_isin.get(isin)
        if symbol is None and isin.startswith("INE") and len(by_issuer.get(isin[:7], [])) == 1:
            symbol = by_issuer[isin[:7]][0]
        if symbol and symbol not in out.get(ticker, []):
            out.setdefault(ticker, []).append(symbol)
    return out


def _latest_nse(today):
    day = today
    for _ in range(10):
        if day.weekday() < 5:
            try:
                return fetch_nse(day)
            except Missing:
                pass
        day = date.fromordinal(day.toordinal() - 1)
    raise RuntimeError("no recent NSE bhavcopy for the ticker map")


def sync_delivery(years=5, today=None, progress=None):
    """Fill or refresh delivery data. Resumable: finished days are recorded in bhav_days."""
    today = today or date.today()
    start = date(today.year - years, today.month, min(today.day, 28))
    store.set_bhav_status(syncing=True, done=0, total=0, message="delivery: building the NSE ticker map")
    try:
        mapping_rows = _latest_nse(today)
        with store.session() as con:
            store.ensure_schema(con)
            ensure_tables(con)
            mapping = ticker_map(con, mapping_rows)
            done = {d for (d,) in con.execute("SELECT day FROM bhav_days WHERE exchange = ?", [SOURCE]).fetchall()}
        pending = [d for d in _weekdays(start, today) if d not in done]
        store.set_bhav_status(total=len(pending), message=f"delivery: {len(pending)} day files, {len(mapping):,} mapped tickers")
        stored = 0
        for n, day in enumerate(pending, start=1):
            try:
                rows = fetch_delivery(day)
            except Missing:
                if (today - day).days > 4:
                    with store.session() as con:
                        con.execute("INSERT OR IGNORE INTO bhav_days VALUES (?, ?, 0)", [SOURCE, day.isoformat()])
                continue
            except RuntimeError as exc:
                store.set_bhav_status(message=f"delivery {day}: {exc}")
                continue
            finally:
                time.sleep(PAUSE)
            out = [(symbol, day.isoformat(), traded, delivered, pct)
                   for t, traded, delivered, pct in rows for symbol in mapping.get(t, ())]
            with store.session() as con:
                if out:
                    _copy_into_temp(con, "deliv_in", "symbol VARCHAR, ts DATE, traded BIGINT, delivered BIGINT, pct DOUBLE", out)
                    con.execute("INSERT OR IGNORE INTO delivery SELECT * FROM deliv_in")
                con.execute("INSERT OR IGNORE INTO bhav_days VALUES (?, ?, ?)", [SOURCE, day.isoformat(), len(out)])
            stored += len(out)
            store.set_bhav_status(done=n, last_day=day.isoformat(), message=f"delivery {day}: {len(out):,} symbols")
            if progress:
                progress(day, n, len(pending), len(out))
        snapshot_fii_dii()
        store.set_bhav_status(syncing=False, message=f"delivery ready: {stored:,} new rows")
        return {"rows": stored, "days": len(pending), "mapped": len(mapping)}
    except Exception as exc:  # noqa: BLE001
        store.set_bhav_status(syncing=False, message=f"delivery failed: {exc}")
        raise


def parse_fii_dii(payload):
    out = []
    for item in payload if isinstance(payload, list) else []:
        try:
            day = datetime.strptime(item.get("date", ""), "%d-%b-%Y").date()
        except ValueError:
            continue
        category = "FII" if "FII" in (item.get("category") or "").upper() else "DII" if "DII" in (item.get("category") or "").upper() else None
        if category is None:
            continue
        out.append((day.isoformat(), category, _num(item.get("buyValue")), _num(item.get("sellValue")), _num(item.get("netValue"))))
    return out


def snapshot_fii_dii():
    """Store today's provisional FII/DII cash numbers (₹ crore). Best effort; returns rows stored."""
    try:
        rows = parse_fii_dii(json.loads(_get(FII_DII_URL, referer="https://www.nseindia.com/reports/fii-dii").decode("utf-8", "replace")))
    except Exception:  # noqa: BLE001 - the endpoint is flaky and optional
        return 0
    if not rows:
        return 0
    with store.session() as con:
        ensure_tables(con)
        con.executemany("INSERT OR REPLACE INTO fii_dii VALUES (?, ?, ?, ?, ?)", rows)
    return len(rows)


def load_delivery(con, symbol):
    """{iso date: delivery %} for one symbol."""
    ensure_tables(con)
    return {str(ts): pct for ts, pct in con.execute("SELECT ts, pct FROM delivery WHERE symbol = ? ORDER BY ts", [symbol]).fetchall()}


def load_fii_dii(con, limit=250):
    ensure_tables(con)
    rows = con.execute("SELECT day, category, buy, sell, net FROM fii_dii ORDER BY day DESC, category LIMIT ?", [int(limit)]).fetchall()
    return [{"day": str(d), "category": c, "buy": b, "sell": s, "net": n} for d, c, b, s, n in rows]
