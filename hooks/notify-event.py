#!/usr/bin/env python3
"""Hook de notification Claude Code : desktop (notify-send) + DM Discord.

Usage : appelé par les hooks Notification et Stop.
  notify-event.py question   -> Claude attend une réponse (question / permission)
  notify-event.py done       -> Claude a fini son traitement

Le payload JSON du hook est lu sur stdin ; on en extrait `cwd` (pour le nom
du projet) et, pour Notification, le champ `message`.
Aucune erreur ne doit faire planter le hook : tout est encapsulé.
"""
import json
import os
import sys
import subprocess
import urllib.request

HOME = os.path.expanduser("~")
DISCORD_DIR = os.path.join(HOME, ".claude", "channels", "discord")
ENV_FILE = os.path.join(DISCORD_DIR, ".env")
ACCESS_FILE = os.path.join(DISCORD_DIR, "access.json")
SCRIPTS_DIR = os.path.join(HOME, ".claude", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)  # pour importer matrix_lib


def read_stdin_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def project_name(payload):
    cwd = payload.get("cwd") or os.getcwd()
    return os.path.basename(cwd.rstrip("/")) or cwd


def is_background_session(payload):
    """Vrai si la session ne doit pas déclencher de notif, c'est-à-dire :
    - session d'agent (agenda, mail, obs-*…) → ligne `agent-setting`, ou
    - session non interactive (cron, /morning, /evening, headless) → les lignes
      assistant/user portent "entrypoint":"sdk-cli" (vs "cli" en interactif)."""
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            for line in f:
                if '"agent-setting"' in line:
                    return True
                if '"entrypoint"' in line:
                    if '"entrypoint":"sdk-cli"' in line.replace(" ", ""):
                        return True
    except Exception:
        pass
    return False


def has_active_background_tasks(payload):
    """Vrai s'il reste au moins une tâche lancée en arrière-plan encore active
    (Agent/Bash `run_in_background`). Le payload des hooks Stop/SubagentStop
    expose `background_tasks` : liste d'objets {id, status, description}.
    `status` vaut `running` quand la tâche tourne encore, `completed`/`killed`
    une fois terminée. On considère « actif » tout statut non terminal connu,
    pour ne pas notifier tant que Claude attend ces réponses — la notif finale
    se déclenchera quand toutes les tâches seront dans un état terminal."""
    terminal = {"completed", "killed", "failed", "error", "cancelled", "done"}
    tasks = payload.get("background_tasks")
    if not isinstance(tasks, list):
        return False
    for task in tasks:
        if not isinstance(task, dict):
            # Forme inattendue : par prudence, on considère qu'il reste du travail.
            return True
        status = (task.get("status") or "").lower()
        if status not in terminal:
            return True
    return False


def session_title(payload):
    """Nom lisible de la session via matrix_lib.session_label (nom /rename explicite >
    ai-title > dossier). Repli sur `session <id>` s'il n'y a ni nom ni titre — le dossier
    serait redondant avec le repo affiché en ligne 1."""
    sid = payload.get("session_id") or ""
    cwd = payload.get("cwd") or ""
    try:
        import matrix_lib
        name = matrix_lib.session_label(sid, cwd)
        folder = os.path.basename(cwd.rstrip("/")) if cwd else ""
        if name and name != folder:      # un vrai nom (--name / ai-title), pas le dossier
            return name
    except Exception:
        pass
    return ("session " + sid[:8]) if sid else "session"


def discord_token():
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith("DISCORD_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def discord_user_id():
    try:
        with open(ACCESS_FILE) as f:
            data = json.load(f)
        allow = data.get("allowFrom") or []
        return allow[0] if allow else None
    except Exception:
        return None


def discord_api(path, token, body):
    req = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": "Bot " + token,
            "Content-Type": "application/json",
            "User-Agent": "ClaudeCodeHook (local, 1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        return json.loads(resp.read().decode())


def send_discord(content):
    token = discord_token()
    user_id = discord_user_id()
    if not token or not user_id:
        return
    try:
        dm = discord_api("/users/@me/channels", token, {"recipient_id": user_id})
        channel_id = dm.get("id")
        if channel_id:
            discord_api("/channels/%s/messages" % channel_id, token, {"content": content})
    except Exception:
        pass


def send_desktop(title, message, urgent=False):
    try:
        cmd = ["notify-send"]
        if urgent:
            cmd += ["-u", "critical"]
        cmd += [title, message]
        subprocess.run(cmd, timeout=5)
    except Exception:
        pass


def matrix_entry(payload):
    """Assignation paresseuse Matrix (persona + salon). None si pas de config Matrix."""
    try:
        import matrix_lib
        sid = payload.get("session_id")
        if not sid:
            return None
        cwd = payload.get("cwd") or os.getcwd()
        return matrix_lib.get_or_assign(sid, cwd)
    except Exception:
        return None


def deliver(entry, content, dm_content):
    """Full DM-only : DM via le bot du persona (repli Neo). `dm_content` = ultime repli legacy."""
    try:
        import matrix_lib
        agent = (entry or {}).get("agent")
        token = matrix_lib.bot_token(agent)        # token du persona, sinon Neo
        user_id = matrix_lib.bots_user_id()
        if token and user_id and matrix_lib.dm_send(token, user_id, content):
            return
    except Exception:
        pass
    send_discord(dm_content)  # repli : ancien mécanisme .env si encore présent (sinon no-op)


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "done"
    payload = read_stdin_payload()

    # On ne notifie pas pour les sessions de fond (agents, cron, /morning…).
    if is_background_session(payload):
        return

    proj = project_name(payload)
    title = session_title(payload)

    if kind == "question":
        detail = payload.get("message") or ""
        # Notification d'inactivité (prompt vide), pas une vraie question/permission : on ignore.
        if "waiting for your input" in detail.lower():
            return
        content = "%s · %s\n❓ Knock, knock. 🐇" % (title, proj)
    else:
        # Claude n'a pas vraiment fini : il attend des tâches lancées en arrière-plan.
        if has_active_background_tasks(payload):
            return
        content = "%s · %s\n✅ The path is clear. 🕶️" % (title, proj)

    # Route vers le bot du persona ; fallback DM legacy.
    deliver(matrix_entry(payload), content, content)


if __name__ == "__main__":
    main()
