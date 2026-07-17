"""matrix_lib — cœur partagé de The Matrix (stdlib only).

Registre des sessions personnifiées : config statique (config.json) + état live
(state.json) muté sous verrou flock. Utilisé par notify-event.py (assignation
paresseuse + routage webhook), le lanceur `matrix` et ccs.
"""
import fcntl
import glob
import json
import os
import time
import urllib.error
import urllib.request

MATRIX_DIR = os.path.expanduser("~/.claude/channels/discord/matrix")
CONFIG = os.path.join(MATRIX_DIR, "config.json")
STATE = os.path.join(MATRIX_DIR, "state.json")
LOCK = os.path.join(MATRIX_DIR, "state.lock")

NOBODY = "Nobody"
TTL = 6 * 3600  # s : sans SessionEnd, une session libère son persona après ce délai d'inactivité (anti-crash)
USER_AGENT = "TheMatrix (https://arxcf.com, 1.0)"
CHUNK = 2000

DISCORD_DIR = os.path.dirname(MATRIX_DIR)  # ~/.claude/channels/discord
BOTS = os.path.join(DISCORD_DIR, "bots.json")
SYSTEM_BOT = "Neo"  # bot système : cycle de vie + repli des sessions sans bot-persona


# ── Config / état ─────────────────────────────────────────────────────────

def load_config():
    try:
        with open(CONFIG) as fh:
            return json.load(fh)
    except (IOError, ValueError):
        return None


class _Lock:
    def __enter__(self):
        os.makedirs(MATRIX_DIR, exist_ok=True)
        self.fh = open(LOCK, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def _load_state():
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except (IOError, ValueError):
        return {"sessions": {}}


def _save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE)


# ── Détection des sessions vivantes (/proc) ─────────────────────────────────

def live_uuids():
    found = set()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                args = [p.decode("utf-8", "replace") for p in fh.read().split(b"\x00") if p]
        except (IOError, OSError):
            continue
        if not any("claude" in a for a in args):
            continue
        for i, arg in enumerate(args):
            for flag in ("--session-id=", "--resume="):
                if arg.startswith(flag):
                    found.add(arg[len(flag):])
            if arg in ("--session-id", "--resume", "-r") and i + 1 < len(args):
                found.add(args[i + 1])
    return found


def _sid_from_args(args):
    """Extrait un session id d'une cmdline claude (--session-id/--resume/-r)."""
    for i, arg in enumerate(args):
        for flag in ("--session-id=", "--resume="):
            if arg.startswith(flag):
                return arg[len(flag):]
        if arg in ("--session-id", "--resume", "-r") and i + 1 < len(args):
            return args[i + 1]
    return None


def _pid_cmdline(pid):
    try:
        with open("/proc/%s/cmdline" % pid, "rb") as fh:
            return [p.decode("utf-8", "replace") for p in fh.read().split(b"\x00") if p]
    except (IOError, OSError):
        return []


def _pid_ppid(pid):
    try:
        with open("/proc/%s/status" % pid) as fh:
            for line in fh:
                if line.startswith("PPid:"):
                    return line.split()[1]
    except (IOError, OSError):
        pass
    return None


def current_session_id():
    """Session id de la session courante : $CLAUDE_SESSION_ID, sinon remontée des
    PID parents jusqu'au process `claude` (cmdline --session-id/--resume)."""
    env = os.environ.get("CLAUDE_SESSION_ID")
    if env:
        return env
    pid = str(os.getppid())
    for _ in range(40):
        if not pid or pid == "0":
            break
        args = _pid_cmdline(pid)
        if any("claude" in a for a in args):
            sid = _sid_from_args(args)
            if sid:
                return sid
        pid = _pid_ppid(pid)
    return None


# ── Assignation / routage ───────────────────────────────────────────────────

def _active(entry, now):
    """Une session « tient » son persona tant qu'elle a été vue il y a moins de TTL."""
    return now - entry.get("seen", entry.get("started", 0)) < TTL


def _held_personas(sessions, now):
    return {e["agent"] for e in sessions.values()
            if e.get("agent") and e["agent"] != NOBODY and _active(e, now)}


def _assign_persona(sessions, config, now):
    held = _held_personas(sessions, now)
    for persona in config.get("personas", []):
        if persona not in held:
            return persona
    return NOBODY


def resolve_channel(cwd, config):
    """basename(cwd) -> repoMap -> salon connu, sinon salon système. Renvoie (nom, webhook_url)."""
    repo = os.path.basename(cwd.rstrip("/")) if cwd else ""
    name = config.get("repoMap", {}).get(repo, repo)
    channels = config.get("channels", {})
    if name not in channels:
        name = config.get("default_channel", "the-construct")
    return name, channels.get(name, {}).get("webhook_url")


def _prune(sessions, now):
    for uuid in [u for u, e in sessions.items()
                 if not _active(e, now) and not e.get("paused") and not e.get("waiting")]:
        del sessions[uuid]


def _new_entry(agent, cwd, config, now, extra=None):
    channel, webhook = resolve_channel(cwd, config)
    entry = {"agent": agent, "channel": channel, "webhook_url": webhook,
             "repo": os.path.basename(cwd.rstrip("/")) if cwd else "",
             "cwd": cwd, "started": now, "seen": now}
    if extra:
        entry.update(extra)
    return entry


def get_or_assign(session_id, cwd):
    """Assignation paresseuse : renvoie l'entrée du session_id, en la créant au besoin.

    Rafraîchit `seen` à chaque appel (la session est active puisqu'elle notifie).
    Renvoie None si aucune config Matrix (fallback appelant). Sous verrou.
    """
    config = load_config()
    if not config:
        return None
    now = time.time()
    with _Lock():
        state = _load_state()
        sessions = state["sessions"]
        _prune(sessions, now)
        entry = sessions.get(session_id)
        if entry is None:
            entry = _new_entry(_assign_persona(sessions, config, now), cwd, config, now)
            sessions[session_id] = entry
        else:
            entry["seen"] = now
        _save_state(state)
        return entry


def register(session_id, cwd, agent=None, **extra):
    """Pré-assignation par le lanceur (persona + salon + infos fenêtre). Renvoie l'entrée.

    Si `agent` est fourni (reprise d'une session), il est conservé ; sinon on
    assigne le premier persona libre."""
    config = load_config()
    if not config:
        return None
    now = time.time()
    with _Lock():
        state = _load_state()
        sessions = state["sessions"]
        _prune(sessions, now)
        if agent is None:
            agent = _assign_persona(sessions, config, now)
        entry = _new_entry(agent, cwd, config, now, extra)
        sessions[session_id] = entry
        _save_state(state)
        return entry


def free(session_id):
    """Retire une session du registre (SessionEnd). Renvoie l'entrée retirée ou None."""
    with _Lock():
        state = _load_state()
        entry = state["sessions"].pop(session_id, None)
        if entry is not None:
            _save_state(state)
        return entry


def _ensure_entry(sessions, sid, cwd, now):
    """Renvoie l'entrée de `sid`, en créant une entrée minimale si absente."""
    entry = sessions.get(sid)
    if entry is None:
        entry = {"cwd": cwd, "started": now, "seen": now}
        sessions[sid] = entry
    return entry


def set_paused(sid, note=None, cwd=None):
    """Marque une session en pause (manuel, durable). Crée l'entrée au besoin."""
    now = time.time()
    with _Lock():
        state = _load_state()
        entry = _ensure_entry(state["sessions"], sid, cwd, now)
        entry["paused"] = {"note": note or "", "since": now}
        _save_state(state)
        return entry


def clear_paused(sid):
    """Lève le flag pause (idempotent)."""
    with _Lock():
        state = _load_state()
        entry = state["sessions"].get(sid)
        if entry and "paused" in entry:
            del entry["paused"]
            _save_state(state)


def set_waiting(sid, message=None, cwd=None):
    """Marque une session en attente d'une réponse utilisateur (auto, transitoire)."""
    now = time.time()
    with _Lock():
        state = _load_state()
        entry = _ensure_entry(state["sessions"], sid, cwd, now)
        entry["waiting"] = {"message": message or "", "since": now}
        _save_state(state)
        return entry


def clear_waiting(sid):
    """Lève le flag d'attente (idempotent)."""
    with _Lock():
        state = _load_state()
        entry = state["sessions"].get(sid)
        if entry and "waiting" in entry:
            del entry["waiting"]
            _save_state(state)


def set_busy(sid, cwd=None):
    """Marque une session « au travail » : le tour est en cours (posé sur
    UserPromptSubmit, levé sur Stop). Rafraîchit `seen` pour que la session
    active ne soit pas purgée. Signal fiable, indépendant du mtime du transcript."""
    now = time.time()
    with _Lock():
        state = _load_state()
        entry = _ensure_entry(state["sessions"], sid, cwd, now)
        entry["busy"] = {"since": now}
        entry["seen"] = now
        _save_state(state)
        return entry


def clear_busy(sid):
    """Lève le flag « au travail » (idempotent ; posé sur Stop)."""
    with _Lock():
        state = _load_state()
        entry = state["sessions"].get(sid)
        if entry and "busy" in entry:
            del entry["busy"]
            _save_state(state)


def paused_sessions():
    """Sessions en pause, plus récentes d'abord, jointes au transcript pour label/cwd."""
    state = _load_state()
    out = []
    for sid, e in state["sessions"].items():
        p = e.get("paused")
        if not p:
            continue
        cwd = e.get("cwd") or ""
        out.append({
            "sid": sid,
            "cwd": cwd,
            "project": os.path.basename(cwd.rstrip("/")) if cwd else "?",
            "agent": e.get("agent"),
            "label": session_label(sid, cwd),
            "note": p.get("note", ""),
            "since": p.get("since", 0),
        })
    out.sort(key=lambda s: s["since"], reverse=True)
    return out


def bind_window(session_id, window_id=None, listen_on=None):
    """Met à jour la fenêtre kitty liée à la session (focus ccs), après un resume p.ex."""
    if not (window_id or listen_on):
        return
    with _Lock():
        state = _load_state()
        entry = state["sessions"].get(session_id)
        if not entry:
            return
        if window_id:
            entry["kitty_window_id"] = window_id
        if listen_on:
            entry["kitty_listen_on"] = listen_on
        _save_state(state)


def get(session_id):
    return _load_state()["sessions"].get(session_id)


def all_sessions():
    return _load_state()["sessions"]


# ── Libellé de session (pour le titre de fenêtre) ───────────────────────────

def find_transcript(session_id):
    """Chemin du transcript .jsonl d'une session (glob sur les projets), ou None."""
    if not session_id:
        return None
    hits = glob.glob(os.path.expanduser("~/.claude/projects/*/%s.jsonl" % session_id))
    return hits[0] if hits else None


def _last_meta(path, mtype, field):
    """Dernière valeur `field` des lignes `type==mtype` du transcript."""
    if not path or not os.path.exists(path):
        return None
    val = None
    try:
        with open(path) as fh:
            for line in fh:
                if ('"%s"' % mtype) not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") == mtype and obj.get(field):
                    val = obj[field]
    except Exception:
        pass
    return val


def list_sessions(limit=15, since_days=3, scan_max=40):
    """Sessions Claude récentes (hors sessions de fond), triées par activité.

    Renvoie une liste de dicts {sid, cwd, project, agent, label, mtime}. Lit au plus
    `scan_max` transcripts (les plus récents) pour rester rapide au lancement."""
    cutoff = time.time() - since_days * 86400
    cands = []
    for path in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime >= cutoff:
            cands.append((mtime, path))
    cands.sort(reverse=True)
    state = all_sessions()
    personas = (load_config() or {}).get("personas") or []
    out = []
    for mtime, path in cands[:scan_max]:
        cwd, ai, rename, is_bg = None, None, None, False
        try:
            with open(path) as fh:
                for line in fh:
                    if '"agent-setting"' in line or '"entrypoint":"sdk-cli"' in line.replace(" ", ""):
                        is_bg = True
                        break
                    if cwd is None and '"cwd"' in line:
                        try:
                            cwd = json.loads(line).get("cwd")
                        except Exception:
                            pass
                    if '"ai-title"' in line:
                        try:
                            val = json.loads(line).get("aiTitle")
                            if val:
                                ai = val
                        except Exception:
                            pass
                    if '"agent-name"' in line:
                        try:
                            val = json.loads(line).get("agentName")
                            if val:
                                rename = val
                        except Exception:
                            pass
        except OSError:
            continue
        if is_bg:
            continue
        sid = os.path.basename(path)[:-6]
        project = os.path.basename((cwd or "").rstrip("/")) or "?"
        label = rename if (rename and rename not in personas) else (ai or project)
        out.append({"sid": sid, "cwd": cwd, "project": project,
                    "agent": (state.get(sid) or {}).get("agent"),
                    "paused": (state.get(sid) or {}).get("paused"),
                    "waiting": (state.get(sid) or {}).get("waiting"),
                    "label": label, "mtime": mtime})
        if len(out) >= limit:
            break
    return out


def session_label(session_id, cwd, config=None):
    """Libellé descriptif d'une session : nom /rename réel > ai-title > nom du dossier.

    Le /rename (transcript `agent-name`/`agentName`) n'est retenu que s'il n'est
    PAS un nom du pool (sinon c'est le --name du lanceur, pas un vrai rename)."""
    cfg = config if config is not None else (load_config() or {})
    personas = cfg.get("personas") or []
    path = find_transcript(session_id)
    rename = _last_meta(path, "agent-name", "agentName")
    if rename and rename not in personas:
        return rename
    ai_title = _last_meta(path, "ai-title", "aiTitle")
    return ai_title or (os.path.basename(cwd.rstrip("/")) if cwd else "")


# ── Bots-persona (Full DM-only) ─────────────────────────────────────────────

def load_bots():
    """Charge bots.json ({user_id, bots:{<persona>:{token,...}}}) ou None."""
    try:
        with open(BOTS) as fh:
            return json.load(fh)
    except (IOError, ValueError):
        return None


def bots_user_id(bots=None):
    data = bots if bots is not None else load_bots()
    return (data or {}).get("user_id")


def bot_token(persona, bots=None):
    """Token du bot d'un persona ; repli sur le bot système Neo ; None sinon."""
    data = bots if bots is not None else load_bots()
    if not data:
        return None
    entries = data.get("bots", {})
    ent = entries.get(persona) or entries.get(SYSTEM_BOT)
    return (ent or {}).get("token")


# ── API Discord (bot, REST) ──────────────────────────────────────────────────

DISCORD_API = "https://discord.com/api/v10"


def _discord_req(token, path, body=None, method="GET"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        DISCORD_API + path, data=data, method=method,
        headers={"Authorization": "Bot " + token,
                 "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def discord_get(token, path):
    return _discord_req(token, path, method="GET")


def discord_post(token, path, body):
    return _discord_req(token, path, body=body, method="POST")


def dm_send(token, user_id, content):
    """Envoie un DM à l'utilisateur via le bot (REST). Chunké > 2000.

    Ouvre (ou retrouve) le canal DM puis poste. Jamais d'exception ;
    renvoie True si tout est parti, False sinon."""
    if not token or not user_id or not content:
        return False
    try:
        channel_id = discord_post(token, "/users/@me/channels",
                                  {"recipient_id": user_id}).get("id")
    except (urllib.error.URLError, OSError, ValueError):
        return False
    if not channel_id:
        return False
    ok = True
    for i in range(0, len(content), CHUNK):
        try:
            discord_post(token, "/channels/%s/messages" % channel_id,
                         {"content": content[i:i + CHUNK]})
        except (urllib.error.URLError, OSError, ValueError):
            ok = False
    return ok
