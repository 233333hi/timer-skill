#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Portable tests for scripts/clock.py.

Every test runs the real CLI as a subprocess in an isolated state directory, so
tests never touch the user's timers and never depend on the machine's clock
other than through the deadlines they build themselves.
"""

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

CLOCK = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "clock.py"


def run(args, state_dir, session="test-session", timeout=60):
    env = dict(os.environ)
    env["DSH_TIMER_STATE"] = str(state_dir)
    env["CLAUDE_CODE_SESSION_ID"] = session
    return subprocess.run(
        [sys.executable, "-I", str(CLOCK)] + list(args),
        capture_output=True, env=env, timeout=timeout,
        # clock.py always writes UTF-8; decoding with the locale codec breaks on
        # non-UTF-8 consoles (e.g. cp1252 on the Windows CI runner).
        encoding="utf-8",
    )


def run_json(args, state_dir, session="test-session"):
    proc = run(list(args) + ["--json"], state_dir, session)
    if proc.returncode != 0:
        raise AssertionError("clock.py failed: %s\n%s" % (proc.returncode, proc.stderr or proc.stdout))
    return json.loads(proc.stdout)


class TimerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self._tmp.name) / "state"

    def tearDown(self):
        self._tmp.cleanup()

    def test_duration_then_satisfied(self):
        info = run_json(["set", "1s"], self.state)
        self.assertFalse(info["satisfied"])
        self.assertEqual(info["kind"], "duration")
        # seconds are truncated, so allow the sub-second loss
        self.assertTrue(0 <= info["remaining_seconds"] + info["elapsed_seconds"] <= 2)

        time.sleep(1.2)
        now = run_json(["now"], self.state)
        self.assertTrue(now["timer"]["satisfied"])
        self.assertLessEqual(now["timer"]["remaining_seconds"], 0)

    def test_compound_duration(self):
        info = run_json(["set", "1h30m"], self.state)
        total = info["remaining_seconds"] + info["elapsed_seconds"]
        self.assertAlmostEqual(total, 5400, delta=2)

    def test_deadline_is_in_the_future(self):
        info = run_json(["set", "until 00:00"], self.state)
        self.assertEqual(info["kind"], "deadline")
        self.assertGreater(info["remaining_seconds"], 0)   # rolls to the next day

    def test_tomorrow_deadline_adds_a_day(self):
        info = run_json(["set", "until 18:00 tomorrow"], self.state)
        now = datetime.datetime.fromisoformat(info["start"])
        target = datetime.datetime.fromisoformat(info["target"])
        self.assertEqual(target.date(), now.date() + datetime.timedelta(days=1))
        self.assertEqual((target.hour, target.minute), (18, 0))

    def test_rejects_ambiguous_and_invalid_specs(self):
        for spec in ("2h until 18:00", "99:99", "abc", "0m"):
            proc = run(["set", spec], self.state)
            self.assertEqual(proc.returncode, 2, "accepted invalid spec %r" % spec)
            self.assertIn("error", json.loads(proc.stdout))

    def test_roll_note_only_when_the_system_rolls(self):
        auto = run(["set", "until 00:00"], self.state)
        self.assertIn("已顺延", auto.stdout)

        explicit = run(["set", "until 09:00 +1d"], self.state)
        self.assertNotIn("已顺延", explicit.stdout, "explicit +1d is not an auto-roll")

    def test_out_of_range_values_fail_cleanly(self):
        # datetime only spans up to year 9999; absurd durations must not traceback
        for spec in ("999999999d", "999999999999h", "until 18:00 +999999999d"):
            proc = run(["set", spec, "--json"], self.state)
            self.assertEqual(proc.returncode, 2, "accepted out-of-range spec %r" % spec)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("error", json.loads(proc.stdout))

    def test_off_clears_only_the_named_timer(self):
        run_json(["set", "10m", "--name", "a"], self.state)
        run_json(["set", "20m", "--name", "b"], self.state)
        cleared = run_json(["set", "off", "--name", "a"], self.state)
        self.assertTrue(cleared["cleared"])

        still = run_json(["now", "--name", "b"], self.state)
        self.assertEqual(still["timer"]["spec"], "20m")
        gone = run_json(["now", "--name", "a"], self.state)
        self.assertNotIn("timer", gone)

        again = run_json(["set", "off", "--name", "a"], self.state)
        self.assertFalse(again["cleared"])

    def test_sessions_are_isolated(self):
        run_json(["set", "10m"], self.state, session="session-a")
        other = run_json(["now"], self.state, session="session-b")
        self.assertNotIn("timer", other)
        mine = run_json(["now"], self.state, session="session-a")
        self.assertEqual(mine["timer"]["spec"], "10m")

    def test_corrupt_state_reads_as_no_timer(self):
        run_json(["set", "10m"], self.state)
        for path in self.state.glob("*.json"):
            path.write_text("{not json", encoding="utf-8")
        now = run_json(["now"], self.state)
        self.assertNotIn("timer", now)

    def test_legacy_naive_state_still_reports(self):
        # Timers written by older versions stored naive timestamps; they must not
        # crash the aware-vs-naive subtraction, and must be read as local time.
        self.state.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now()
        legacy = {
            "name": "default", "spec": "1h", "kind": "duration",
            "start": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "target": (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            "session": "test-session",
        }
        (self.state / "test-session__default.json").write_text(
            json.dumps(legacy), encoding="utf-8")

        now_info = run_json(["now"], self.state)
        self.assertIn("timer", now_info)
        self.assertFalse(now_info["timer"]["satisfied"])
        start = datetime.datetime.fromisoformat(now_info["timer"]["start"])
        self.assertIsNotNone(start.tzinfo, "legacy start was not localised")
        self.assertGreater(now_info["timer"]["remaining_seconds"], 3000)

    def test_json_report_shape(self):
        run_json(["set", "5m"], self.state)
        now = run_json(["now"], self.state)
        for key in ("now", "date", "time", "weekday", "utc_offset", "session", "state_dir"):
            self.assertIn(key, now)
        for key in ("spec", "kind", "start", "target", "elapsed", "remaining", "satisfied"):
            self.assertIn(key, now["timer"])

    def test_state_lives_outside_the_skill_directory(self):
        run_json(["set", "5m"], self.state)
        skill_root = CLOCK.parents[1]
        self.assertFalse((skill_root / "state").exists())
        self.assertTrue(list(self.state.glob("*.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
