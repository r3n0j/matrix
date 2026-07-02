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
import urllib.parse
import urllib.request

MATRIX_DIR = os.path.expanduser("~/.claude/channels/discord/matrix")
CONFIG = os.path.join(MATRIX_DIR, "config.json")
STATE = os.path.join(MATRIX_DIR, "state.json")
LOCK = os.path.join(MATRIX_DIR, "state.lock")

NOBODY = "Nobody"
TTL = 6 * 3600  # s : sans SessionEnd, une session libère son persona après ce délai d'inactivité (anti-crash)
USER_AGENT = "TheMatrix (https://arxcf.com, 1.0)"
CHUNK = 2000
AVATAR_STYLE = "personas"  # style DiceBear ; avatar déterministe par nom d'agent


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
    for uuid in [u for u, e in sessions.items() if not _active(e, now)]:
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
    out = []
    for mtime, path in cands[:scan_max]:
        cwd, ai, is_bg = None, None, False
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
        except OSError:
            continue
        if is_bg:
            continue
        sid = os.path.basename(path)[:-6]
        project = os.path.basename((cwd or "").rstrip("/")) or "?"
        out.append({"sid": sid, "cwd": cwd, "project": project,
                    "agent": (state.get(sid) or {}).get("agent"),
                    "label": ai or project, "mtime": mtime})
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


# ── Envoi webhook ───────────────────────────────────────────────────────────

def avatar_for(agent, config=None):
    """URL d'avatar de l'agent : override explicite (config["avatars"]) sinon DiceBear.

    Pour des visuels sur-mesure : renseigner `avatars` dans config.json
    ({ "Agent Smith": "https://.../smith.jpeg", ... }) — URL publique requise
    (Discord va chercher l'image côté serveur)."""
    if not agent:
        return None
    cfg = config if config is not None else (load_config() or {})
    override = (cfg.get("avatars") or {}).get(agent)
    if override:
        return override
    return "https://api.dicebear.com/9.x/%s/png?seed=%s" % (
        AVATAR_STYLE, urllib.parse.quote(agent))


def post_webhook(url, content, username=None, avatar_url=None):
    """Poste sur un webhook Discord (chunké > 2000). Renvoie True/False (jamais d'exception)."""
    if not url or not content:
        return False
    ok = True
    for i in range(0, len(content), CHUNK):
        body = {"content": content[i:i + CHUNK]}
        if username:
            body["username"] = username
        if avatar_url:
            body["avatar_url"] = avatar_url
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except (urllib.error.URLError, OSError):
            ok = False
    return ok
