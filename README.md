# The Matrix — personnification des sessions Claude Code

Chaque session Claude Code devient un **agent** (Agent Smith, Agent Brown…) qui :
- poste ses notifications dans le **salon Discord de son repo**, sous son **identité** (nom + avatar) ;
- porte son nom dans le **titre de la fenêtre kitty** (« Agent X — titre de session ») ;
- est visible et **focusable** depuis le TUI **ccs**.

> **État à ce stade** : entièrement **sortant** (notifications par webhook) + observation/pilotage local (ccs, kitty). Le **Discord bidirectionnel** (piloter les agents *depuis* Discord) n'est **pas encore** implémenté — voir « Prochaine évolution ».

---

## 1. Comment ça marche

### Personnification (le cœur)
- Un **registre** `state.json` associe chaque `session_id` à un **persona** (nom du pool), son salon, sa fenêtre kitty, etc. Muté sous verrou `flock`.
- L'assignation est **paresseuse** : à la 1ʳᵉ notification d'une session, `notify-event.py` lui attribue le **premier persona libre** du pool (ordre fixe). Pool épuisé ou session non encore nommée → **`Nobody`**. Un persona se libère à la vraie fin de session (ou après TTL 6 h).
- Le **lanceur** `matrix`/`redpill` **pré-assigne** le persona et enregistre l'ID de fenêtre kitty (pour le focus).

### Notifications (sortant)
- Hooks `Notification` (attend ton input → « Knock, knock. ») et `Stop` (fin de tour → « The path is clear. »).
- `notify-event.py` route le message vers le **webhook du salon du repo** (`config.json`), sous l'identité de l'agent (username + avatar). Fallback DM si pas de config.
- Fin de session (`SessionEnd`) → `matrix-free.py` poste « <agent> has been unplugged. » (émetteur « The Matrix », avatar Neo) et libère le persona. Ignoré sur `/resume` et `/clear`.

### Titre de fenêtre kitty
- `set-window-title.py` (SessionStart/Stop) pose « **Agent X — <label>** » où `label` = nom `/rename` réel > ai-title > dossier. Il (ré)assigne le persona et **re-lie la fenêtre** à chaque tour (focus fiable après resume).

### ccs (le TUI)
- Colonnes **PROJECT / STATUS / AGENT / HOST / TITLE / … / LAST PROMPT**. STATUS thémé (jacked in / in construct / awaiting / unplugged). HOST = kitty / vscode / bg. TITLE = « /rename · ai-title ».
- **⏎** = focus la fenêtre kitty de l'agent (binding stocké → sinon découverte par titre/cwd → sinon reprise). **o** = détail. **^K** = kill. Thème « The Matrix ».

### kitty
- Fenêtres agent + **fenêtre « The Matrix »** (ccs, thème vert `matrix-window.conf` + fond `matrix-bg.png`). Monitoring k9s (`sessions/*.session`, layout `fat:bias=75`). Actions clic-droit (`kitty.desktop`) : **Red Pill**, **The Matrix**, **Monitoring local/develop/prod**.

---

## 2. Composants

```
scripts/
  matrix_lib.py     cœur : registre+flock, assignation persona (+Nobody/TTL), routage salon,
                    post_webhook, avatar_for, session_label, list_sessions, bind_window
  matrix            lanceur : personnifie une session ; sous-commande `matrix resume <uuid>`
  redpill           menu : reprendre une session récente OU nouvelle (choix repo) = action « Red Pill »
  matrix-setup      crée salons + webhooks Discord (découverte auto des repos), écrit config.json
  claude-sessions   ccs : le TUI (colonnes, focus ⏎, thème Matrix)
hooks/
  notify-event.py   Notification/Stop → notif par salon sous l'identité de l'agent (fallback DM)
  matrix-free.py    SessionEnd → « unplugged » + libère le persona (ignore resume/clear)
  set-window-title.py  SessionStart/Stop → titre fenêtre « Agent X — <label> »
kitty/
  kitty.conf, matrix.conf (thème vert), matrix-window.conf (fenêtre ccs),
  sessions/{local,develop,prod}.session (monitoring k9s), kitty.desktop (actions clic-droit)
install.sh          pose les liens symboliques (repo = source de vérité)
```

---

## 3. Configuration & secrets (jamais committés — cf `.gitignore`)

Sous `~/.claude/channels/discord/` :
- **`.env`** — `DISCORD_BOT_TOKEN=…` (token du bot).
- **`matrix/config.json`** — écrit par `matrix-setup` :
  ```json
  {
    "guild_id": "…",
    "personas": ["Agent Smith", …, "Sati"],
    "default_channel": "the-construct",
    "repoMap": { "<worktree>": "<repo parent>" },
    "avatars": { "Agent Smith": "https://raw.githubusercontent.com/r3n0j/matrix/main/Agent_Smith.jpeg", … },
    "channels": { "<repo>": { "channel_id": "…", "webhook_url": "…" } }
  }
  ```
- **`matrix/state.json`** — état live : `{ "sessions": { "<uuid>": {agent, channel, webhook_url, repo, cwd, started, seen, kitty_window_id, kitty_listen_on} } }`.

Avatars des personas : hébergés dans **ce repo** (public), référencés par URL `raw`. Style généré par défaut = DiceBear si un persona n'a pas d'entrée `avatars`.

---

## 4. Installation (de zéro)

**Prérequis** : `kitty` (≥ 0.47, userland), `python3`, `jq`, `curl` ; un **bot Discord** + un **serveur** « The Matrix ».

1. **Cloner** ce repo dans `~/matrix`.
2. **Déployer les liens** : `./install.sh` (crée les symlinks ; sauvegarde tout fichier existant en `.bak`).
3. **PATH** : s'assurer que `~/.local/bin` est dans le PATH (pour `matrix` / `redpill`).
4. **Discord** :
   - Poser le token : `~/.claude/channels/discord/.env` → `DISCORD_BOT_TOKEN=…` (chmod 600).
   - Créer le serveur « The Matrix », inviter le bot (permissions *Manage Channels* + *Manage Webhooks*).
   - Générer salons + webhooks : `python3 ~/matrix/scripts/matrix-setup` → écrit `config.json`.
   - Avatars : déposer les portraits dans ce repo (public) ; renseigner la map `avatars` de `config.json` (ou laisser DiceBear).
5. **Hooks** — dans `~/.claude/settings.json` (`hooks`) :
   ```json
   "Notification": [{ "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/notify-event.py question" }] }],
   "Stop":         [{ "hooks": [
       { "type": "command", "command": "python3 ~/.claude/hooks/notify-event.py done" },
       { "type": "command", "command": "python3 ~/.claude/hooks/set-window-title.py" } ] }],
   "SessionStart": [{ "matcher": "startup|resume|clear", "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/set-window-title.py" }] }],
   "SessionEnd":   [{ "hooks": [{ "type": "command", "command": "python3 ~/.claude/hooks/matrix-free.py" }] }]
   ```
   (Chemins réels absolus. `hot.md` sur SessionStart est un hook perso séparé, hors Matrix.)
6. **kitty** : `update-desktop-database ~/.local/share/applications/` pour les actions clic-droit ; recharger la config (`Ctrl+Shift+F5`).

---

## 5. Utilisation

- **Lancer un agent** : clic-droit kitty → **Red Pill** (menu : reprendre une session récente **ou** nouvelle → choix du repo), ou `redpill` / `matrix` dans un terminal.
- **Voir les agents** : **The Matrix** (ccs). ⏎ = sauter sur la fenêtre de l'agent.
- **Monitoring k9s** : clic-droit → Monitoring local/develop/prod.
- Les notifs arrivent dans **#<repo>** sous l'identité de l'agent ; « unplugged » à la fermeture.

---

## 6. Prochaine évolution (non implémentée)

**Discord bidirectionnel — DM only + bots-persona** (design dans le vault) :
- Un **bot par persona** (nom + avatar = le persona) → identité parfaite, résout le conflit « 1 token = 1 Gateway » (un persona = une session à la fois).
- **DM only** : chaque bot-persona DM ses notifs + reçoit tes réponses/approbations de permission (mode natif du plugin Discord officiel).
- **Bot « The Matrix » (Neo)** dédié : DM les événements **système / cycle de vie** (unplugged, `Nobody`, pool saturé) — le fil « système » (équivalent DM de #the-construct).
- Remplace probablement les webhooks + salons (à trancher : garder les salons pour la lecture groupée par repo ?).

---

## 7. Rollback / désinstallation

- **Revenir en arrière (fichiers)** : `install.sh` a sauvegardé chaque original en `<fichier>.bak`. Pour restaurer un fichier : supprimer le lien puis remettre le `.bak`, p.ex.
  ```bash
  rm ~/.claude/scripts/matrix && mv ~/.claude/scripts/matrix.bak ~/.claude/scripts/matrix
  ```
  (idem pour les autres liens listés par `install.sh`).
- **Désactiver les notifications / le titrage** : retirer les blocs correspondants de `~/.claude/settings.json` (`Notification`, `Stop`, `SessionEnd`, et `set-window-title.py` sous `SessionStart`).
- **Discord** : les webhooks/salons restent tant qu'on ne les supprime pas côté Discord ; `config.json`/`state.json`/`.env` sont locaux (jamais dans le repo).
- **Neutraliser rapidement** : vider `config.json` (ou le supprimer) → `notify-event.py` retombe sur le **fallback DM** ; supprimer `state.json` → repart d'un registre vide.
