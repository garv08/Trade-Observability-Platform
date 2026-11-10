"""Automatic daily update: slot maths in IST, catch-up, the server scheduler step, and the cron side."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest import mock

from top import autoupdate

IST = autoupdate.IST
AT = time(19, 0)


def ist(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


class SlotTests(unittest.TestCase):
    # 2026-11-09 is a Monday.
    def test_after_the_time_on_a_weekday(self):
        self.assertEqual(autoupdate.latest_slot(ist(2026, 11, 10, 19, 5), AT), ist(2026, 11, 10, 19))

    def test_before_the_time_uses_the_previous_weekday(self):
        self.assertEqual(autoupdate.latest_slot(ist(2026, 11, 10, 10), AT), ist(2026, 11, 9, 19))

    def test_monday_morning_and_weekend_use_friday(self):
        for now in (ist(2026, 11, 9, 9), ist(2026, 11, 8, 23), ist(2026, 11, 7, 12)):
            self.assertEqual(autoupdate.latest_slot(now, AT), ist(2026, 11, 6, 19), now)

    def test_next_slot_skips_the_weekend(self):
        self.assertEqual(autoupdate.next_slot(ist(2026, 11, 6, 20), AT), ist(2026, 11, 9, 19))
        self.assertEqual(autoupdate.next_slot(ist(2026, 11, 10, 18), AT), ist(2026, 11, 10, 19))

    def test_system_time_zone_does_not_matter(self):
        # 13:35 UTC is 19:05 IST; the same instant in New York time gives the same slot.
        utc = datetime(2026, 11, 10, 13, 35, tzinfo=timezone.utc)
        new_york = utc.astimezone(timezone(timedelta(hours=-5)))
        self.assertEqual(autoupdate.latest_slot(utc, AT), ist(2026, 11, 10, 19))
        self.assertEqual(autoupdate.latest_slot(new_york, AT), ist(2026, 11, 10, 19))

    def test_update_time_parsing(self):
        self.assertEqual(autoupdate.update_time("18:30"), time(18, 30))
        with self.assertRaises(ValueError):
            autoupdate.update_time("evening")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = Path(self.dir.name) / "nse.duckdb"

    def tearDown(self):
        self.dir.cleanup()

    def test_due_until_marked_done_and_catches_up_missed_days(self):
        now = ist(2026, 11, 10, 20)
        self.assertEqual(autoupdate.due(now, AT, self.db), ist(2026, 11, 10, 19))  # never run
        autoupdate.mark_done(ist(2026, 11, 10, 19), "all", db_path=self.db)
        self.assertIsNone(autoupdate.due(now, AT, self.db))
        self.assertIsNone(autoupdate.due(ist(2026, 11, 11, 18), AT, self.db))
        # PC off for two days: the next start catches up with one update.
        self.assertEqual(autoupdate.due(ist(2026, 11, 13, 9), AT, self.db), ist(2026, 11, 12, 19))

    def test_scheduler_step_starts_once_and_records_the_finish(self):
        started = []
        sync = {"syncing": False, "bhav": {"syncing": False}, "errors": []}
        autoupdate._set(at="19:00", running_slot=None, retry_after=None)
        with mock.patch("top.store.DB_PATH", self.db), \
                mock.patch("top.store.status", side_effect=lambda: sync), \
                mock.patch("top.store.session"), \
                mock.patch.object(autoupdate, "files_missing", return_value=False), \
                mock.patch.object(autoupdate, "scope", return_value="all"), \
                mock.patch.object(autoupdate, "_busy", return_value=False):
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 1)), "started")
            self.assertEqual(started, ["all"])
            sync["bhav"]["syncing"] = True
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 6)), "running")
            sync["bhav"]["syncing"] = False
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 11)), "finished")
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 16)), "idle")
            self.assertEqual(started, ["all"])
            self.assertEqual(autoupdate.load_state(self.db)["last_slot"], ist(2026, 11, 10, 19).isoformat())
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 11, 19, 1)), "started")
        autoupdate._set(running_slot=None, retry_after=None)

    def test_scheduler_retries_until_the_exchange_files_are_out(self):
        started = []
        sync = {"syncing": False, "bhav": {"syncing": False}, "errors": []}
        missing = [True]
        autoupdate._set(at="19:00", running_slot=None, retry_after=None)
        with mock.patch("top.store.DB_PATH", self.db), \
                mock.patch("top.store.status", side_effect=lambda: sync), \
                mock.patch("top.store.session"), \
                mock.patch.object(autoupdate, "files_missing", side_effect=lambda *a, **k: missing[0]), \
                mock.patch.object(autoupdate, "scope", return_value="all"), \
                mock.patch.object(autoupdate, "_busy", return_value=False):
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 1)), "started")
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 6)), "waiting")
            self.assertNotIn("last_slot", autoupdate.load_state(self.db))
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 20)), "idle")  # before the retry time
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 40)), "started")
            missing[0] = False
            self.assertEqual(autoupdate.tick(started.append, ist(2026, 11, 10, 19, 45)), "finished")
        self.assertEqual(started, ["all", "all"])
        autoupdate._set(running_slot=None, retry_after=None)

    def test_files_missing_until_the_day_arrives_or_next_morning(self):
        import duckdb

        con = duckdb.connect()
        con.execute("CREATE TABLE bars (symbol VARCHAR, interval VARCHAR, ts DATE)")
        con.execute("INSERT INTO bars VALUES ('RELIANCE', '1d', '2026-11-10'), ('NSE:IRFC', '1d', '2026-11-09')")
        slot = ist(2026, 11, 10, 19)
        self.assertTrue(autoupdate.files_missing(con, slot, "all", ist(2026, 11, 10, 19, 30)))
        self.assertFalse(autoupdate.files_missing(con, slot, "nifty", ist(2026, 11, 10, 19, 30)))
        self.assertTrue(autoupdate.files_missing(con, slot, "all", ist(2026, 11, 10, 23, 0)))
        self.assertFalse(autoupdate.files_missing(con, slot, "all", ist(2026, 11, 10, 23, 30)))  # holiday: give up
        con.execute("INSERT INTO bars VALUES ('BSE:500325', '1d', '2026-11-10')")
        self.assertFalse(autoupdate.files_missing(con, slot, "all", ist(2026, 11, 10, 19, 30)))

    def test_cli_auto_leaves_it_to_a_server_with_its_own_scheduler(self):
        from top import store

        with mock.patch.object(store, "DB_PATH", self.db), mock.patch.object(store, "_schema_ready", store._schema_ready), \
                mock.patch.object(autoupdate, "server_schedules", return_value=True), \
                mock.patch.object(autoupdate, "ask_server") as ask, mock.patch("builtins.print"):
            self.assertEqual(store.main(["--db", str(self.db), "--auto"]), 0)
        ask.assert_not_called()
        self.assertNotIn("last_slot", autoupdate.load_state(self.db))  # the server's scheduler records it

    def test_cron_line_runs_auto_from_the_project(self):
        line = autoupdate.cron_line(python="/opt/venv/bin/python", workdir=self.dir.name, at="18:30")
        self.assertTrue(line.startswith("*/30 * * * * cd "))
        self.assertIn("TOP_AUTO_UPDATE_AT=18:30 /opt/venv/bin/python -m top.store --auto", line)
        self.assertTrue(line.endswith("# TOP auto update"))

    def test_cli_auto_does_nothing_when_up_to_date(self):
        from top import store

        slot = autoupdate.latest_slot()
        autoupdate.mark_done(slot, "all", db_path=self.db)
        with mock.patch.object(store, "DB_PATH", self.db), mock.patch.object(store, "_schema_ready", store._schema_ready), \
                mock.patch.object(autoupdate, "ask_server") as ask, mock.patch("builtins.print"):
            self.assertEqual(store.main(["--db", str(self.db), "--auto"]), 0)
        ask.assert_not_called()

    def test_cli_auto_hands_over_to_a_running_server(self):
        from top import store

        with mock.patch.object(store, "DB_PATH", self.db), mock.patch.object(store, "_schema_ready", store._schema_ready), \
                mock.patch.object(autoupdate, "server_schedules", return_value=False), \
                mock.patch.object(autoupdate, "ask_server", return_value=True) as ask, mock.patch("builtins.print"):
            self.assertEqual(store.main(["--db", str(self.db), "--auto"]), 0)
        ask.assert_called_once_with("all")
        self.assertEqual(autoupdate.load_state(self.db)["last_slot"], autoupdate.latest_slot().isoformat())


if __name__ == "__main__":
    unittest.main()
