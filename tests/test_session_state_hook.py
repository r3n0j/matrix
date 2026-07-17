import os
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import matrix_lib  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location(
    "session_state_hook", os.path.join(SCRIPTS, "session-state-hook.py"))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class StateHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (matrix_lib.MATRIX_DIR, matrix_lib.STATE, matrix_lib.LOCK)
        matrix_lib.MATRIX_DIR = self.tmp
        matrix_lib.STATE = os.path.join(self.tmp, "state.json")
        matrix_lib.LOCK = os.path.join(self.tmp, "state.lock")

    def tearDown(self):
        matrix_lib.MATRIX_DIR, matrix_lib.STATE, matrix_lib.LOCK = self._orig

    def test_set_posts_waiting(self):
        hook.handle("set", {"session_id": "s1", "cwd": "/x", "message": "q ?"})
        self.assertEqual(matrix_lib.get("s1")["waiting"]["message"], "q ?")

    def test_clear_removes_waiting(self):
        matrix_lib.set_waiting("s1", message="q")
        hook.handle("clear", {"session_id": "s1"})
        self.assertNotIn("waiting", matrix_lib.get("s1") or {})

    def test_background_session_ignored(self):
        with mock.patch.object(hook, "is_background", return_value=True):
            hook.handle("set", {"session_id": "bg"})
        self.assertIsNone(matrix_lib.get("bg"))

    def test_no_session_id_is_noop(self):
        hook.handle("set", {})  # ne lève pas
