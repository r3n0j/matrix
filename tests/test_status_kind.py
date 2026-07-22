import importlib.machinery
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)

# `claude-sessions` n'a pas d'extension .py : loader explicite.
_loader = importlib.machinery.SourceFileLoader(
    "claude_sessions", os.path.join(SCRIPTS, "claude-sessions"))
cs = importlib.util.module_from_spec(importlib.util.spec_from_loader("claude_sessions", _loader))
_loader.exec_module(cs)


class LooksLikeQuestionTest(unittest.TestCase):
    def test_ends_with_question_mark(self):
        self.assertTrue(cs._looks_like_question("Je propose deux options. Laquelle ?"))

    def test_bold_markdown_question(self):
        self.assertTrue(cs._looks_like_question("**Dois-je continuer ?**"))

    def test_statement_is_not_question(self):
        self.assertFalse(cs._looks_like_question("C'est fait, tout passe au vert."))

    def test_rhetorical_midtext_not_flagged(self):
        self.assertFalse(cs._looks_like_question("Pourquoi ? Parce que X. J'ai corrigé."))

    def test_cue_without_mark(self):
        self.assertTrue(cs._looks_like_question("Dis-moi si tu veux que je poursuive"))

    def test_empty(self):
        self.assertFalse(cs._looks_like_question(""))


def _line(**kw):
    return json.dumps(kw)


def _asst(text):
    return _line(type="assistant", message={"content": [{"type": "text", "text": text}]})


class ScanAsksTest(unittest.TestCase):
    def test_asks_true_when_last_assistant_is_question(self):
        self.assertTrue(cs._scan_reversed([_asst("Voici le plan. On y va ?")], False)["asks"])

    def test_asks_false_when_last_assistant_is_statement(self):
        self.assertFalse(cs._scan_reversed([_asst("Terminé, tout est vert.")], False)["asks"])

    def test_asks_false_when_last_message_is_user(self):
        lines = [_asst("On y va ?"),
                 _line(type="user", message={"content": [{"type": "text", "text": "oui"}]})]
        self.assertFalse(cs._scan_reversed(lines, False)["asks"])

    def test_asks_false_when_last_assistant_runs_tool(self):
        line = _line(type="assistant", message={"content": [
            {"type": "text", "text": "Je vérifie ?"},
            {"type": "tool_use", "name": "Bash"}]})
        r = cs._scan_reversed([line], False)
        self.assertTrue(r["working"])
        self.assertFalse(r["asks"])


class StatusKindTest(unittest.TestCase):
    def _sess(self, **kw):
        base = {"mtime": 1000.0, "last_msg_type": "assistant"}
        base.update(kw)
        return base

    def test_maybe_asking_when_done_live_and_asks(self):
        s = self._sess(done={"since": 1}, live=True, asks=True)
        self.assertEqual(cs.status_kind(s, 1000.0)[0], "maybe_asking")

    def test_standby_when_done_live_without_asks(self):
        s = self._sess(done={"since": 1}, live=True, asks=False)
        self.assertEqual(cs.status_kind(s, 1000.0)[0], "standby")

    def test_knocking_wins_over_maybe_asking(self):
        s = self._sess(waiting={"since": 1}, done={"since": 1}, live=True, asks=True)
        self.assertEqual(cs.status_kind(s, 1000.0)[0], "knocking")

    def test_running_tool_wins_over_maybe_asking(self):
        s = self._sess(working=True, done={"since": 1}, live=True, asks=True)
        self.assertEqual(cs.status_kind(s, 1000.0)[0], "active")

    def test_maybe_asking_registered_in_status_meta(self):
        self.assertIn("maybe_asking", cs.STATUS_META)

    def test_maybe_asking_registered_in_status_rank(self):
        self.assertIn("maybe_asking", cs._STATUS_RANK)

    def test_dismissed_asking_falls_back_to_standby(self):
        s = self._sess(done={"since": 1}, live=True, asks=True,
                       asking_dismissed={"since": 2})
        self.assertEqual(cs.status_kind(s, 1000.0)[0], "standby")


class KittyTargetsTest(unittest.TestCase):
    def test_binding_comes_first(self):
        s = {"mx_socket": "unix:/tmp/kitty-1", "mx_window": "42",
             "agent": "Neo", "cwd": "/x"}
        self.assertEqual(cs._kitty_targets(s)[0], ("unix:/tmp/kitty-1", "id:42"))

    def test_no_binding_yields_no_id_match(self):
        s = {"agent": "Neo", "cwd": "/x"}  # pas de binding
        self.assertTrue(all(not m.startswith("id:") for _sock, m in cs._kitty_targets(s)))


class CleanExitTest(unittest.TestCase):
    def test_sends_exit_then_closes_window(self):
        calls = []

        def fake_run(sock, args):
            calls.append(list(args))
            return args[0] == "send-text"

        with mock.patch.object(cs, "_kitty_targets",
                               return_value=[("unix:/tmp/kitty-1", "id:42")]), \
             mock.patch.object(cs, "_kitty_run", side_effect=fake_run), \
             mock.patch.object(cs.time, "sleep", lambda *_a: None):
            kind, _info = cs.clean_exit({"sid": "s1"})
        self.assertEqual(kind, "ok")
        self.assertEqual(calls[0][0], "send-text")
        self.assertIn("/exit\r", calls[0])
        self.assertEqual(calls[1][0], "close-window")

    def test_no_window_reachable(self):
        with mock.patch.object(cs, "_kitty_targets", return_value=[]), \
             mock.patch.object(cs.time, "sleep", lambda *_a: None):
            self.assertEqual(cs.clean_exit({"sid": "s1"})[0], "nowin")


if __name__ == "__main__":
    unittest.main()
