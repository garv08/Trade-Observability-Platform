"""Ready-made data snapshots: the whole DuckDB store, compressed, as a GitHub release asset.

The store (`data/nse.duckdb`) is generated data and far larger than git allows (100 MB per
file), so it is not in the repository. Instead `top-sync --make-snapshot` writes
`top-data.duckdb.gz` plus a `.json` manifest (size, SHA-256, coverage), which are attached to
a GitHub release. On another machine, after `git pull`:

    top-sync --snapshot            # newest snapshot from the repository's releases
    top-sync --snapshot FILE|URL   # a copy you made yourself

The download is checked against its SHA-256 and opened before it replaces the store; the old
store is kept as `nse.duckdb.bak`. Afterwards Sync history only fetches the days since the
snapshot was made.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path

import duckdb

from top import store

REPO = os.environ.get("TOP_SNAPSHOT_REPO", "garv08/Trade-Observability-Platform")
ASSET = "top-data.duckdb.gz"
MANIFEST = "top-data.json"
CHUNK = 1 << 20
_status = {"running": False, "message": "idle", "done_mb": 0.0, "total_mb": None}


def status():
    return dict(_status)


def _set(**kwargs):
    _status.update(kwargs)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def coverage_of(path):
    """Counts from a store file (opened read-only), for the manifest and the safety check."""
    con = duckdb.connect(str(path), read_only=True, config={"memory_limit": "256MB", "threads": "1"})
    try:
        bars, last = con.execute("SELECT COUNT(*), MAX(ts) FROM bars").fetchone()
        symbols = con.execute("SELECT COUNT(DISTINCT symbol) FROM bars").fetchone()[0]
        tables = {name for (name,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        board = con.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0] if "leaderboard" in tables else 0
        return {"bars": int(bars or 0), "symbols_with_bars": int(symbols or 0), "data_to": None if last is None else str(last),
                "leaderboard_rows": int(board or 0)}
    finally:
        con.close()


def make(out_dir, db_path=None):
    """Checkpoint the store and write ASSET + MANIFEST into out_dir. The server must be stopped."""
    db_path = Path(db_path or store.DB_PATH)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), config={"memory_limit": "256MB", "threads": "1"})
    try:
        con.execute("CHECKPOINT")
    finally:
        con.close()
    info = coverage_of(db_path)
    target = out_dir / ASSET
    with open(db_path, "rb") as src, gzip.open(target, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, CHUNK)
    from top import __version__

    manifest = {"asset": ASSET, "bytes": target.stat().st_size, "sha256": _sha256(target), "db_bytes": db_path.stat().st_size,
                "made": datetime.now(store.IST).isoformat(timespec="seconds"), "top_version": __version__,
                "duckdb": duckdb.__version__, **info}
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _get(url, accept="application/octet-stream"):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "top-platform", "Accept": accept}), timeout=60)


def latest_release():
    """(asset URL, manifest dict or None, release tag) of the newest release that has a data snapshot."""
    with _get(f"https://api.github.com/repos/{REPO}/releases?per_page=30", "application/vnd.github+json") as response:
        releases = json.loads(response.read().decode("utf-8"))
    for release in releases:
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        if ASSET in assets:
            manifest = None
            if MANIFEST in assets:
                try:
                    with _get(assets[MANIFEST]) as response:
                        manifest = json.loads(response.read().decode("utf-8"))
                except Exception:  # noqa: BLE001 - the checksum is optional
                    manifest = None
            return assets[ASSET], manifest, release.get("tag_name")
    raise RuntimeError(f"No release of {REPO} has a data snapshot ({ASSET}) yet.")


def _fetch(source, target):
    """Copy a URL or local file to target, reporting progress."""
    if os.path.exists(source):
        total = os.path.getsize(source)
        _set(total_mb=round(total / 1e6, 1))
        with open(source, "rb") as src, open(target, "wb") as dst:
            done = 0
            for block in iter(lambda: src.read(CHUNK), b""):
                dst.write(block)
                done += len(block)
                _set(done_mb=round(done / 1e6, 1), message=f"copying {done / 1e6:,.0f} of {total / 1e6:,.0f} MB")
        return
    with _get(source) as response, open(target, "wb") as dst:
        total = int(response.headers.get("Content-Length") or 0) or None
        _set(total_mb=None if total is None else round(total / 1e6, 1))
        done = 0
        for block in iter(lambda: response.read(CHUNK), b""):
            dst.write(block)
            done += len(block)
            of = f" of {total / 1e6:,.0f}" if total else ""
            _set(done_mb=round(done / 1e6, 1), message=f"downloading {done / 1e6:,.0f}{of} MB")


def install(source=None, db_path=None, lock=None):
    """Download (or copy) a snapshot and replace the store with it. Returns the new coverage.

    source: None for the newest release asset, else a URL or a local `.duckdb.gz` / `.duckdb` file.
    lock: held while the store file is swapped (the server passes its database lock).
    """
    db_path = Path(db_path or store.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    work = db_path.parent / "snapshot.download"
    unpacked = db_path.parent / "snapshot.duckdb"
    _set(running=True, message="finding the snapshot", done_mb=0.0, total_mb=None)
    try:
        manifest, tag = None, None
        if source is None:
            source, manifest, tag = latest_release()
        _fetch(str(source), work)
        if manifest and manifest.get("sha256"):
            _set(message="checking the download")
            if _sha256(work) != manifest["sha256"]:
                raise RuntimeError("The download is damaged (SHA-256 mismatch). Please try again.")
        _set(message="unpacking")
        with open(work, "rb") as probe:
            gzipped = probe.read(2) == b"\x1f\x8b"
        if gzipped:
            with gzip.open(work, "rb") as src, open(unpacked, "wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            work.unlink()
        else:
            os.replace(work, unpacked)
        info = coverage_of(unpacked)
        if info["bars"] == 0:
            raise RuntimeError("The snapshot has no bars; the current store was left untouched.")
        _set(message="replacing the store")

        def swap():
            backup = db_path.with_name(db_path.name + ".bak")
            if db_path.exists():
                os.replace(db_path, backup)
            # A write-ahead log belongs to the old file; replaying it onto the snapshot would corrupt it.
            wal = db_path.with_name(db_path.name + ".wal")
            if wal.exists():
                os.replace(wal, backup.with_name(backup.name + ".wal"))
            os.replace(unpacked, db_path)

        if lock is not None:
            with lock:
                swap()
        else:
            swap()
        store.reset_caches()
        from top import leaderboard, markets

        leaderboard._tables_ready["path"] = None
        markets._scan_cache.update(key=None, rows=None, latest=None)
        where = f" from release {tag}" if tag else ""
        _set(running=False, message=f"snapshot installed{where}: {info['symbols_with_bars']:,} scripts, data to {info['data_to']}")
        return {**info, "release": tag}
    except Exception as exc:  # noqa: BLE001
        _set(running=False, message=f"snapshot failed: {exc}")
        for leftover in (work, unpacked):
            try:
                leftover.unlink()
            except FileNotFoundError:
                pass
        raise


def store_in_use(db_path=None):
    """True if another process (usually top-platform) holds the store open."""
    db_path = Path(db_path or store.DB_PATH)
    if not db_path.exists():
        return False
    try:
        duckdb.connect(str(db_path), config={"memory_limit": "64MB", "threads": "1"}).close()
        return False
    except (duckdb.IOException, duckdb.ConnectionException):
        return True
