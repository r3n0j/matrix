import importlib.machinery
import importlib.util
import json
import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
