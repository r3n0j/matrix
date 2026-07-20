#!/usr/bin/env python3
"""Hook Claude Code : titre de la fenêtre kitty.

Appelé sur SessionStart et Stop. Session personnifiée (The Matrix) →
« <Agent> — <libellé> » ; sinon « Claude — <libellé> ». Le libellé (nom /rename
réel > ai-title > dossier) vient de `matrix_lib.session_label`. Assigne/retrouve
le persona et re-lie la fenêtre kitty courante (pour le focus depuis matrix).

Silencieux et non bloquant. Ne fait rien hors d'une fenêtre kitty (pas de
KITTY_WINDOW_ID) — donc pas d'effet sur les sessions d'agents / headless.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "scripts"))

PREFIX = "Claude — "


def read_stdin_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def set_kitty_title(title):
    subprocess.run(["kitty", "@", "set-window-title", title],
                   timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def matrix_agent(payload):
    """Persona de la session : l'assigne au besoin et (re)lie la fenêtre kitty courante
    (utile après un resume dans une nouvelle fenêtre). None si indisponible/Nobody."""
    try:
        import matrix_lib
        sid = payload.get("session_id")
        if not sid:
            return None
        cwd = payload.get("cwd") or os.getcwd()
        entry = matrix_lib.get_or_assign(sid, cwd)
        matrix_lib.bind_window(sid, os.environ.get("KITTY_WINDOW_ID"),
                               os.environ.get("KITTY_LISTEN_ON"))
        agent = (entry or {}).get("agent")
        if agent and agent != matrix_lib.NOBODY:
            return agent
    except Exception:
        pass
    return None


def label(payload):
    cwd = payload.get("cwd") or os.getcwd()
    try:
        import matrix_lib
        return matrix_lib.session_label(payload.get("session_id"), cwd)
    except Exception:
        return os.path.basename(cwd.rstrip("/")) or cwd


def main():
    if not os.environ.get("KITTY_WINDOW_ID"):
        return
    payload = read_stdin_payload()
    agent = matrix_agent(payload)
    body = label(payload)
    title = ("%s — %s" % (agent, body)) if agent else (PREFIX + body)
    try:
        set_kitty_title(title)
    except Exception:
        pass


if __name__ == "__main__":
    main()
