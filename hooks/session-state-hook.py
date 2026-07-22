#!/usr/bin/env python3
"""Hook d'état de session (découplé de la notification).

Usage (payload JSON du hook sur stdin) :
  session-state-hook.py set    -> Notification              : Claude attend une réponse — permission
                                                              (waiting ; ignore la notif d'inactivité)
  session-state-hook.py ask    -> PreToolUse/AskUserQuestion : Claude pose une question (waiting)
  session-state-hook.py unask  -> PostToolUse/AskUserQuestion: réponse reçue (clear waiting)
  session-state-hook.py busy   -> UserPromptSubmit           : le tour démarre (busy ; clear waiting/done)
  session-state-hook.py clear  -> Stop                       : tour terminé (clear busy/waiting ; set done)

N'envoie AUCUNE notification (c'est le rôle de notify-event.py). Ne lève jamais.
"""
import json
import os
import sys

SCRIPTS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)  # pour importer matrix_lib


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
        if action == "set":          # Notification : permission demandée
            message = payload.get("message") or ""
            if "waiting for your input" in message.lower():
                return               # notif d'inactivité, pas une vraie attente
            matrix_lib.set_waiting(sid, message=message, cwd=payload.get("cwd"))
        elif action == "ask":        # PreToolUse/AskUserQuestion : question posée
            matrix_lib.set_waiting(sid, message=payload.get("message"),
                                   cwd=payload.get("cwd"))
        elif action == "unask":      # PostToolUse/AskUserQuestion : réponse reçue
            matrix_lib.clear_waiting(sid)
        elif action == "busy":       # UserPromptSubmit : le tour démarre
            matrix_lib.set_busy(sid, cwd=payload.get("cwd"))
            matrix_lib.clear_waiting(sid)
            matrix_lib.clear_done(sid)
            matrix_lib.clear_paused(sid)  # activité réelle → sortie de veille (resume)
            matrix_lib.clear_asking_dismissed(sid)  # nouveau tour → masque périmé
        elif action == "clear":      # Stop : tour terminé
            matrix_lib.clear_busy(sid)
            matrix_lib.clear_waiting(sid)
            matrix_lib.set_done(sid, cwd=payload.get("cwd"))
    except Exception:
        pass


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "clear"
    handle(action, read_payload())


if __name__ == "__main__":
    main()
