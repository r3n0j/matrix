# The Matrix — personnification des sessions Claude Code

Outillage perso : chaque session Claude Code devient un « agent » (Agent Smith, Agent
Brown, …) qui poste ses notifications dans le **bon salon Discord** sous son identité,
porte son nom dans le **titre de fenêtre kitty**, et est visible/pilotable depuis **ccs**.

## Contenu

### `scripts/`
- **`matrix_lib.py`** — cœur : registre (`state.json`) sous `flock`, assignation de persona
  (+ `Nobody`, TTL 6 h), routage salon, `post_webhook`, `avatar_for`, `list_sessions`,
  `session_label`, `bind_window`.
- **`matrix`** — lanceur : personnifie une session (persona + titre fenêtre + stockage
  `KITTY_WINDOW_ID`/`KITTY_LISTEN_ON`) ; sous-commande `matrix resume <uuid>`.
- **`redpill`** — menu : **reprendre** une session récente **ou** **nouvelle** session
  (choix du repo). = action clic-droit kitty « Red Pill ».
- **`matrix-setup`** — crée les salons + webhooks Discord (découverte auto des repos sous
  `~/Arx/repositories`), écrit `config.json`.
- **`claude-sessions`** (ccs) — TUI : colonnes AGENT / HOST / TITLE, focus fenêtre sur ⏎
  (`kitty @ focus-window`), thème « The Matrix ».

### `hooks/`
- **`notify-event.py`** — Notification/Stop : assignation **paresseuse** + notif par salon
  sous l'identité de l'agent (fallback DM).
- **`matrix-free.py`** — SessionEnd : « <agent> has been unplugged. » + libère le persona ;
  ignore les bascules (`reason` = `resume`/`clear`).
- **`set-window-title.py`** — SessionStart/Stop : titre fenêtre « Agent X — <label> »
  (matrix-aware ; label = `/rename` réel > ai-title > dossier).

### `kitty/`
- `kitty.conf`, `matrix.conf` (thème vert), `matrix-window.conf` (fenêtre ccs),
  `sessions/*.session` (monitoring k9s local/develop/prod), `kitty.desktop` (actions clic-droit).

## Déploiement
`./install.sh` pose des **liens symboliques** depuis ce repo vers les emplacements ci-dessous
(le **repo = source de vérité** : éditer un fichier du repo = éditer le live ; les fichiers
existants sont sauvegardés en `.bak`).
- `scripts/*` → `~/.claude/scripts/` (+ liens `~/.local/bin/matrix`, `~/.local/bin/redpill`)
- `hooks/*` → `~/.claude/hooks/` (câblés dans `~/.claude/settings.json` : Notification, Stop,
  SessionEnd, SessionStart)
- `kitty/*` → `~/.config/kitty/` ; `kitty.desktop` → `~/.local/share/applications/`

## Secrets — jamais committés (cf `.gitignore`)
- `~/.claude/channels/discord/.env` — token du bot Discord.
- `~/.claude/channels/discord/matrix/config.json` — URLs de webhooks + guild id.
- `~/.claude/channels/discord/matrix/state.json` — état live des sessions.

## Conception (vault Obsidian, `B. Areas/Claude Code/`)
- Plan « The Matrix » · note « Migration Tilix → Kitty » · « Discord bidirectionnel (design) ».
