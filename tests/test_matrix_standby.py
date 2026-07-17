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


class WaitingPrimitivesTest(StateTestBase):
    def test_set_waiting_stores_message(self):
        matrix_lib.set_waiting("s1", message="Puis-je merger ?", cwd="/x")
        self.assertEqual(matrix_lib.get("s1")["waiting"]["message"], "Puis-je merger ?")

    def test_clear_waiting_idempotent(self):
        matrix_lib.set_waiting("s1")
        matrix_lib.clear_waiting("s1")
        matrix_lib.clear_waiting("s1")
        self.assertNotIn("waiting", matrix_lib.get("s1") or {})

    def test_waiting_and_paused_coexist(self):
        matrix_lib.set_paused("s1", note="n")
        matrix_lib.set_waiting("s1", message="m")
        e = matrix_lib.get("s1")
        self.assertIn("paused", e)
        self.assertIn("waiting", e)


class BusyPrimitivesTest(StateTestBase):
    def test_set_busy_marks_and_refreshes_seen(self):
        matrix_lib.set_busy("s1", cwd="/x")
        e = matrix_lib.get("s1")
        self.assertIn("since", e["busy"])
        self.assertAlmostEqual(e["seen"], e["busy"]["since"], delta=1)

    def test_clear_busy_idempotent(self):
        matrix_lib.set_busy("s1")
        matrix_lib.clear_busy("s1")
        matrix_lib.clear_busy("s1")
        self.assertNotIn("busy", matrix_lib.get("s1") or {})


class SidResolutionTest(unittest.TestCase):
    def test_sid_from_equals_form(self):
        self.assertEqual(matrix_lib._sid_from_args(["claude", "--session-id=abc"]), "abc")

    def test_sid_from_spaced_resume(self):
        self.assertEqual(matrix_lib._sid_from_args(["claude", "--resume", "def"]), "def")

    def test_sid_from_short_r(self):
        self.assertEqual(matrix_lib._sid_from_args(["claude", "-r", "ghi"]), "ghi")

    def test_sid_none_when_absent(self):
        self.assertIsNone(matrix_lib._sid_from_args(["claude", "--foo"]))

    def test_current_session_id_uses_env(self):
        os.environ["CLAUDE_SESSION_ID"] = "env-sid"
        try:
            self.assertEqual(matrix_lib.current_session_id(), "env-sid")
        finally:
            del os.environ["CLAUDE_SESSION_ID"]


if __name__ == "__main__":
    unittest.main()
