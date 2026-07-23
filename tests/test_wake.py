import importlib.machinery
import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)

import matrix_lib  # noqa: E402

# `claude-sessions` n'a pas d'extension .py : loader explicite.
_loader = importlib.machinery.SourceFileLoader(
    "claude_sessions", os.path.join(SCRIPTS, "claude-sessions"))
cs = importlib.util.module_from_spec(importlib.util.spec_from_loader("claude_sessions", _loader))
_loader.exec_module(cs)


class PausedSessionsBindingTest(unittest.TestCase):
    """Régression wake up neo : paused_sessions() doit exposer le binding kitty
    (kitty_window_id/kitty_listen_on) pour que le réveil focus la fenêtre par id
    plutôt que de retomber sur un matching cwd/titre fragile."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self._orig = (matrix_lib.MATRIX_DIR, matrix_lib.STATE, matrix_lib.LOCK)
        matrix_lib.MATRIX_DIR = self.tmp
        matrix_lib.STATE = os.path.join(self.tmp, "state.json")
        matrix_lib.LOCK = os.path.join(self.tmp, "state.lock")

    def tearDown(self):
        matrix_lib.MATRIX_DIR, matrix_lib.STATE, matrix_lib.LOCK = self._orig

    def test_paused_sessions_exposes_kitty_binding(self):
        matrix_lib._save_state({"sessions": {"s1": {
            "cwd": "/home/u/repo", "kitty_window_id": "7",
            "kitty_listen_on": "unix:/tmp/kitty-1",
            "paused": {"since": 1}}}})
        p = matrix_lib.paused_sessions()[0]
        self.assertEqual(p["kitty_window_id"], "7")
        self.assertEqual(p["kitty_listen_on"], "unix:/tmp/kitty-1")


class FocusCriteriaTest(unittest.TestCase):
    """Le matching de fenêtre ne doit jamais s'appuyer sur cwd==HOME : trop
    générique, il focusserait une fenêtre au repos quelconque dans le home
    (dont le TUI matrix lui-même), effaçant le flag paused sans vraie reprise."""

    def test_excludes_home_cwd(self):
        crit = cs._focus_criteria("Agent Brown", cs.HOME)
        self.assertNotIn("cwd:%s" % cs.HOME, crit)
        self.assertIn("title:Agent Brown", crit)

    def test_keeps_specific_cwd(self):
        crit = cs._focus_criteria("Neo", "/home/u/repo")
        self.assertIn("cwd:/home/u/repo", crit)
        self.assertIn("title:Neo", crit)

    def test_no_agent_yields_only_cwd(self):
        self.assertEqual(cs._focus_criteria(None, "/home/u/repo"), ["cwd:/home/u/repo"])

    def test_home_and_no_agent_yields_nothing(self):
        self.assertEqual(cs._focus_criteria(None, cs.HOME), [])


if __name__ == "__main__":
    unittest.main()
