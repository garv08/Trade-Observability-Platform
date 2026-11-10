"""Daily automatic data update, driven by the system clock.

NSE and BSE publish the day's bhavcopies in the evening, so after a weekday's close plus a
margin (default 19:00 India time) every script's OHLC data is refreshed once. The clock is
converted to IST explicitly, so the machine's own time zone does not matter. A missed slot
(PC off, server stopped) is caught up at the next start. Exchange holidays simply find no
new file.

Two ways to run it, because DuckDB lets only one process open the store:
- inside top-platform: a background thread (on by default; TOP_AUTO_UPDATE=0 or
  --no-auto-update turns it off);
- from cron: `top-sync --auto` asks a running top-platform to sync through its API, or
  syncs directly when the server is not running. `top-sync --install-cron` adds the line.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_AT = "19:00"
CHECK_SECONDS = 300
FULL_STORE = 1000  # scripts; below this the store is a fresh install and only the Nifty 50 is refreshed

_lock = threading.Lock()
_state = {"enabled": False, "at": DEFAULT_AT, "running_slot": None, "message": "off"}


def update_time(text=None):
    text = (text or os.environ.get("TOP_AUTO_UPDATE_AT") or DEFAULT_AT).strip()
    try:
        hour, minute = (int(part) for part in text.split(":", 1))
        return time(hour, minute)
    except (ValueError, TypeError):
        raise ValueError(f"TOP_AUTO_UPDATE_AT must look like 19:00, not {text!r}") from None


def now_ist(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.astimezone()  # naive = the system's local time
    return now.astimezone(IST)


def latest_slot(now=None, at=None):
    """The most recent weekday update time (IST) at or before now."""
    now = now_ist(now)
    at = at or update_time()
    day = now.date()
    for _ in range(8):
        slot = datetime.combine(day, at, IST)
        if day.weekday() < 5 and slot <= now:
            return slot
        day -= timedelta(days=1)
    return None


def next_slot(now=None, at=None):
    now = now_ist(now)
    at = at or update_time()
    day = now.date()
    for _ in range(8):
        slot = datetime.combine(day, at, IST)
        if day.weekday() < 5 and slot > now:
            return slot
        day += timedelta(days=1)
    return None


def state_path(db_path=None):
    from top import store

    return Path(db_path or store.DB_PATH).with_name("auto-update.json")


def load_state(db_path=None):
    try:
        return json.loads(state_path(db_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(data, db_path=None):
    path = state_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def due(now=None, at=None, db_path=None):
    """The slot to run now, or None if the latest slot was already done."""
    slot = latest_slot(now, at)
    if slot is None:
        return None
    done = load_state(db_path).get("last_slot")
    return None if done and done >= slot.isoformat() else slot


def scope(con):
    """'all' for a filled store; 'nifty' on a fresh install (the full backfill takes hours; the snapshot is faster)."""
    from top.store import coverage

    return "all" if (coverage(con).get("total_symbols_with_bars") or 0) >= FULL_STORE else "nifty"


RETRY_MINUTES = 30
GIVE_UP = time(23, 30)  # no exchange files by then means a holiday


def exchange_day(con):
    """The newest day with exchange-file (NSE/BSE) bars in the store, or None."""
    row = con.execute("SELECT MAX(ts) FROM bars WHERE interval = '1d' AND (symbol LIKE 'NSE:%' OR symbol LIKE 'BSE:%')").fetchone()
    return row[0] if row and row[0] else None


def files_missing(con, slot, what, now=None):
    """True while the slot's exchange files are not in the store yet and it is still worth retrying.

    NSE and BSE publish at different times in the evening, so an update can run before they are out.
    After GIVE_UP on the same day it is treated as an exchange holiday."""
    if what != "all":
        return False
    day = exchange_day(con)
    if day is not None and str(day)[:10] >= slot.date().isoformat():
        return False
    return now_ist(now) < datetime.combine(slot.date(), GIVE_UP, IST)


def mark_done(slot, what, errors=None, db_path=None):
    data = load_state(db_path)
    data.update(last_slot=slot.isoformat(), what=what, finished=now_ist().isoformat(timespec="seconds"), errors=errors or [])
    save_state(data, db_path)


def status():
    with _lock:
        out = {k: v for k, v in _state.items() if k != "scope"}
    data = load_state()
    out["last_slot"] = data.get("last_slot")
    out["last_finished"] = data.get("finished")
    out["last_scope"] = data.get("what")
    nxt = next_slot(at=update_time(out["at"])) if out["enabled"] else None
    out["next"] = nxt.isoformat() if nxt else None
    return out


def _set(**kwargs):
    with _lock:
        _state.update(kwargs)


def _busy():
    # A long leaderboard run does not hold up the data; it catches up with the new bars afterwards.
    from top import snapshot
    from top.store import status as sync_status

    st = sync_status()
    return st["syncing"] or st["bhav"]["syncing"] or snapshot.status()["running"]


def tick(start_sync, now=None):
    """One scheduler step inside the server. start_sync(what) starts the background syncs."""
    from top.store import session, status as sync_status

    running = _state.get("running_slot")
    if running:
        st = sync_status()
        if st["syncing"] or st["bhav"]["syncing"]:
            return "running"
        errors = [e.get("symbol", "") + ": " + e.get("error", "") for e in st.get("errors") or []][:20]
        slot = datetime.fromisoformat(running)
        with session() as con:
            waiting = files_missing(con, slot, _state.get("scope", "all"), now)
        if waiting:
            retry = now_ist(now) + timedelta(minutes=RETRY_MINUTES)
            _set(running_slot=None, retry_after=retry.isoformat(),
                 message=f"exchange files for {slot.date()} are not out yet; retrying at {retry:%H:%M} IST")
            return "waiting"
        mark_done(slot, _state.get("scope", "all"), errors)
        _set(running_slot=None, retry_after=None, message=f"updated for {running[:10]}" + (f" ({len(errors)} errors)" if errors else ""))
        return "finished"
    slot = due(now, update_time(_state["at"]))
    if slot is None:
        return "idle"
    retry_after = _state.get("retry_after")
    if retry_after and now_ist(now) < datetime.fromisoformat(retry_after):
        return "idle"
    if _busy():
        _set(message="waiting for the running sync or leaderboard run")
        return "busy"
    with session() as con:
        what = scope(con)
    start_sync(what)
    _set(running_slot=slot.isoformat(), scope=what,
         message=f"updating for {slot.date()} ({'all scripts' if what == 'all' else 'Nifty 50'})")
    return "started"


def start(start_sync, at=None):
    """Run the scheduler in a daemon thread for the life of the server."""
    _set(enabled=True, at=(at or update_time()).strftime("%H:%M"), message="waiting for the next update time")
    stop = threading.Event()

    def loop():
        while True:
            try:
                tick(start_sync)
            except Exception as exc:  # noqa: BLE001 - the scheduler must keep running
                _set(message=f"auto update error: {exc}")
            if stop.wait(CHECK_SECONDS):
                return

    threading.Thread(target=loop, name="top-auto-update", daemon=True).start()
    return stop


# ---------------------------------------------------------------- cron side

def ask_server(what="all", host=None, port=None, timeout=10):
    """Ask a running top-platform to sync. Returns True if a server answered."""
    import urllib.error
    import urllib.request

    host = host or os.environ.get("TOP_HOST", "127.0.0.1")
    port = port or int(os.environ.get("TOP_PORT", "8000"))
    request = urllib.request.Request(f"http://{host}:{port}/api/sync", data=json.dumps({"what": what}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def server_schedules(host=None, port=None, timeout=10):
    """True if a running top-platform has its own scheduler on; cron then leaves the update to it."""
    import urllib.error
    import urllib.request

    host = host or os.environ.get("TOP_HOST", "127.0.0.1")
    port = port or int(os.environ.get("TOP_PORT", "8000"))
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=timeout) as response:
            return bool(json.loads(response.read().decode("utf-8")).get("sync", {}).get("auto", {}).get("enabled"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def cron_line(python=None, workdir=None, at=None):
    """A crontab line that runs `top-sync --auto` every 30 minutes; --auto itself decides whether an update is due."""
    import shlex
    import sys

    python = python or sys.executable
    workdir = Path(workdir or Path.cwd()).resolve()
    log = workdir / "data" / "auto-update.log"
    env = f"TOP_AUTO_UPDATE_AT={at} " if at else ""
    return (f"*/30 * * * * cd {shlex.quote(str(workdir))} && {env}{shlex.quote(python)} -m top.store --auto "
            f">> {shlex.quote(str(log))} 2>&1  # TOP auto update")


def install_cron(line):
    """Add or replace the TOP line in the user's crontab. Returns the new crontab text."""
    import subprocess

    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = [row for row in (current.stdout if current.returncode == 0 else "").splitlines() if "# TOP auto update" not in row]
    lines.append(line)
    text = "\n".join(lines) + "\n"
    subprocess.run(["crontab", "-"], input=text, text=True, check=True)
    return text
