import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import matrix_lib  # noqa: E402


class StateTestBase(unittest.TestCase):
    """Redirige state.json/lock vers un dossier temporaire par test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (matrix_lib.MATRIX_DIR, matrix_lib.STATE, matrix_lib.LOCK)
        matrix_lib.MATRIX_DIR = self.tmp
        matrix_lib.STATE = os.path.join(self.tmp, "state.json")
        matrix_lib.LOCK = os.path.join(self.tmp, "state.lock")

    def tearDown(self):
        matrix_lib.MATRIX_DIR, matrix_lib.STATE, matrix_lib.LOCK = self._orig

    def write_state(self, sessions):
        matrix_lib._save_state({"sessions": sessions})


class PausedPrimitivesTest(StateTestBase):
    def test_set_paused_creates_entry_when_absent(self):
        matrix_lib.set_paused("s1", note="attend !61", cwd="/home/u/repo")
        e = matrix_lib.get("s1")
        self.assertEqual(e["paused"]["note"], "attend !61")
        self.assertIn("since", e["paused"])
        self.assertEqual(e["cwd"], "/home/u/repo")

    def test_clear_paused_is_idempotent(self):
        matrix_lib.set_paused("s1")
        matrix_lib.clear_paused("s1")
        matrix_lib.clear_paused("s1")  # no-op
        self.assertNotIn("paused", matrix_lib.get("s1") or {})

    def test_paused_sessions_sorted_recent_first(self):
        matrix_lib.set_paused("old")
        time.sleep(0.01)
        matrix_lib.set_paused("new")
        sids = [s["sid"] for s in matrix_lib.paused_sessions()]
        self.assertEqual(sids[0], "new")

    def test_prune_keeps_paused_entry_past_ttl(self):
        old = time.time() - matrix_lib.TTL - 10
        self.write_state({"s1": {"agent": "Neo", "seen": old, "paused": {"since": old}}})
        state = matrix_lib._load_state()
        matrix_lib._prune(state["sessions"], time.time())
        self.assertIn("s1", state["sessions"])

    def test_prune_drops_stale_entry_without_flags(self):
        old = time.time() - matrix_lib.TTL - 10
        self.write_state({"s1": {"agent": "Neo", "seen": old}})
        state = matrix_lib._load_state()
        matrix_lib._prune(state["sessions"], time.time())
        self.assertNotIn("s1", state["sessions"])


if __name__ == "__main__":
    unittest.main()
