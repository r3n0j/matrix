#!/usr/bin/env python3
"""Hook d'état de session (découplé de la notification).

Usage (payload JSON du hook sur stdin) :
  session-state-hook.py set    -> Notification : Claude attend une réponse
  session-state-hook.py clear  -> Stop / UserPromptSubmit : plus en attente

N'envoie AUCUNE notification (c'est le rôle de notify-event.py). Ne lève jamais.
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def is_background(payload):
    """Session de fond (agent, cron, SDK) : ne pas suivre l'état d'attente."""
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            for line in f:
                if '"agent-setting"' in line:
                    return True
                if '"entrypoint"' in line and '"entrypoint":"sdk-cli"' in line.replace(" ", ""):
                    return True
    except Exception:
        pass
    return False


def handle(action, payload):
    try:
        sid = payload.get("session_id")
        if not sid or is_background(payload):
            return
        import matrix_lib
        if action == "set":
            matrix_lib.set_waiting(sid, message=payload.get("message"),
                                   cwd=payload.get("cwd"))
        elif action == "clear":
            matrix_lib.clear_waiting(sid)
    except Exception:
        pass


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "clear"
    handle(action, read_payload())


if __name__ == "__main__":
    main()
