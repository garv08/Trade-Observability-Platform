"""Offline checks for data snapshots: make, install from a file, safety checks."""

from __future__ import annotations

import gzip
import json
import unittest

from tests.support import temp_dir, use_temp_store
from top import snapshot, store


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.source_db = use_temp_store()
        self.folder = temp_dir("top-snap-")

    def test_make_and_install_round_trip(self):
        manifest = snapshot.make(self.folder, self.source_db)
        asset = self.folder / snapshot.ASSET
        self.assertTrue(asset.exists())
        saved = json.loads((self.folder / snapshot.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(saved["sha256"], manifest["sha256"])
        self.assertEqual(saved["symbols_with_bars"], 50)
        self.assertGreater(saved["bars"], 1000)

        target_dir = temp_dir("top-snap-target-")
        target = target_dir / "nse.duckdb"
        target.write_bytes(b"old store")
        (target_dir / "nse.duckdb.wal").write_bytes(b"old wal")
        info = snapshot.install(str(asset), target)
        self.assertEqual(info["symbols_with_bars"], 50)
        self.assertEqual(info["bars"], manifest["bars"])
        self.assertEqual((target_dir / "nse.duckdb.bak").read_bytes(), b"old store")
        self.assertFalse((target_dir / "nse.duckdb.wal").exists(), "an old WAL must never be replayed onto the snapshot")
        self.assertFalse((target_dir / "snapshot.download").exists())
        self.assertFalse(snapshot.store_in_use(target))
        self.assertEqual(snapshot.coverage_of(target)["bars"], manifest["bars"])

    def test_install_rejects_empty_or_broken_files(self):
        empty_dir = temp_dir("top-snap-empty-")
        broken = empty_dir / "broken.duckdb.gz"
        with gzip.open(broken, "wb") as handle:
            handle.write(b"not a database")
        target = temp_dir("top-snap-target-") / "nse.duckdb"
        target.write_bytes(b"keep me")
        with self.assertRaises(Exception):
            snapshot.install(str(broken), target)
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertFalse(snapshot.status()["running"])
        self.assertIn("failed", snapshot.status()["message"])

    def test_store_in_use(self):
        import subprocess
        import sys

        self.assertFalse(snapshot.store_in_use(self.source_db))
        # Another process (like a running top-platform) holding the store open must be detected.
        holder = subprocess.Popen(
            [sys.executable, "-c", "import duckdb, sys, time; c = duckdb.connect(sys.argv[1]); print('open', flush=True); time.sleep(60)",
             str(self.source_db)],
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "open")
            self.assertTrue(snapshot.store_in_use(self.source_db))
        finally:
            holder.kill()
            holder.wait()
        self.assertFalse(snapshot.store_in_use(self.source_db))

    def test_reset_caches(self):
        with store.session() as con:
            self.assertTrue(store.list_symbols(con))
        store.reset_caches()
        self.assertFalse(store._schema_ready)
        self.assertIsNone(store._symbols_cache["key"])


if __name__ == "__main__":
    unittest.main()
