#!/usr/bin/env python3
"""Hook SessionEnd de The Matrix : libère le persona et annonce l'« unplug ».

Lit le payload JSON du hook sur stdin (session_id), retire la session du
registre Matrix et poste « <agent> has been unplugged. » dans son salon.
Tout est encapsulé : aucune erreur ne doit faire échouer le hook.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "scripts"))


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    session_id = payload.get("session_id")
    if not session_id:
        return
    # /resume, /clear… ne sont pas de vraies fermetures (bascule/reset de conversation) :
    # on ne libère pas le persona et on n'annonce pas d'« unplug ».
    if payload.get("reason") in ("resume", "clear", "bypass_permissions_disabled"):
        return
    try:
        import matrix_lib
        entry = matrix_lib.free(session_id)
        agent = (entry or {}).get("agent")
        token = matrix_lib.bot_token(matrix_lib.SYSTEM_BOT)  # Neo
        user_id = matrix_lib.bots_user_id()
        if token and user_id and agent and agent != matrix_lib.NOBODY:
            repo = (entry or {}).get("repo") or "?"
            matrix_lib.dm_send(token, user_id, "%s · %s\n☎️ Unplugged." % (agent, repo))
    except Exception:
        pass


if __name__ == "__main__":
    main()
