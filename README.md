# The Matrix — personnification des sessions Claude Code

Chaque session Claude Code devient un **agent** (Agent Smith, Agent Brown…) qui :
- DM ses notifications sous l'**identité de son bot-persona** (nom + avatar du bot) ;
- porte son nom dans le **titre de la fenêtre kitty** (« Agent X — titre de session ») ;
- est visible et **focusable** depuis le TUI **matrix**.

> **Modèle : notifications sortantes en DM.** Chaque session DM son bot-persona, avec un bot système **Neo** pour le cycle de vie et le repli des sessions sans bot dédié.
>
> **Le pilotage *entrant* (répondre/piloter depuis Discord) n'est pas supporté** : il reposerait sur les *channels* de Claude Code (research preview), dont l'injection entrante, le relais de permission et `AskUserQuestion` ne sont pas exploitables en 2.1.201. À rouvrir quand la feature sortira de preview → voir « Évolution possible ».

---

## 1. Comment ça marche

### Personnification (le cœur)
- Un **registre** `state.json` associe chaque `session_id` à un **persona** (nom du pool), sa fenêtre kitty, etc. Muté sous verrou `flock`.
- L'assignation est **paresseuse** : à la 1ʳᵉ notification d'une session, `notify-event.py` lui attribue le **premier persona libre** du pool (ordre fixe). Pool épuisé ou session non encore nommée → **`Nobody`**. Un persona se libère à la vraie fin de session (ou après TTL 6 h).
- Le **lanceur** `construct`/`redpill` **pré-assigne** le persona et enregistre l'ID de fenêtre kitty (pour le focus).

### Notifications (en DM, sous l'identité du persona)
- Hooks `Notification` (attend ton input → « Knock, knock. ») et `Stop` (fin de tour → « The path is clear. »).
- `notify-event.py` envoie le message en **DM via le bot du persona** (`matrix_lib.dm_send`, REST), avec **repli sur le bot Neo** si le persona n'a pas son propre bot.
- Fin de session (`SessionEnd`) → `matrix-free.py` DM « <agent> has been unplugged. » **depuis Neo** et libère le persona. Ignoré sur `/resume` et `/clear`.

### Titre de fenêtre kitty
- `set-window-title.py` (SessionStart/Stop) pose « **Agent X — <label>** » où `label` = nom `/rename` réel > ai-title > dossier. Il (ré)assigne le persona et **re-lie la fenêtre** à chaque tour (focus fiable après resume).

### matrix (le TUI)
- Colonnes **PROJECT / STATUS / AGENT / HOST / TITLE / … / LAST PROMPT**. STATUS thémé (in the matrix / jacked in / knocking / standby / unplugged / paused). HOST = kitty / vscode / bg.
- Hotkeys groupées **Navigation / Session / The Matrix** + **bouton `[⏏ Red Pill]`** (clic → lance `redpill` en nouvelle fenêtre kitty). **⏎** = focus la fenêtre de l'agent. Thème « The Matrix ».

### kitty
- Fenêtres agent + **fenêtre « The Matrix »** (matrix, thème vert `matrix-window.conf` + fond `matrix-bg.png`). Monitoring k9s (`sessions/*.session`). Actions clic-droit (`kitty.desktop`) : **Red Pill**, **The Matrix**, **Monitoring local/develop/prod**.

---

## 2. Composants

```
scripts/
  matrix_lib.py     cœur : registre+flock, assignation persona (+Nobody/TTL),
                    résolution bot par persona (bot_token, repli Neo),
                    API Discord REST (discord_get/post, dm_send), session_label, list_sessions
  construct         lanceur (loading program) : personnifie une session ; sous-commande `construct resume <uuid>`
  redpill           menu : reprendre une session récente OU nouvelle (choix repo) = action « Red Pill »
  matrix-bots       valide les tokens des bots-persona et imprime leurs URLs d'invitation
  claude-sessions   matrix : le TUI (colonnes, focus ⏎, bouton Red Pill, thème Matrix)
hooks/
  notify-event.py   Notification/Stop → DM du bot-persona (repli Neo)
  matrix-free.py    SessionEnd → DM « unplugged » depuis Neo + libère le persona (ignore resume/clear)
  set-window-title.py  SessionStart/Stop → titre fenêtre « Agent X — <label> »
kitty/
  kitty.conf, matrix.conf (thème vert), matrix-window.conf (fenêtre matrix),
  sessions/{local,develop,prod}.session (monitoring k9s), kitty.desktop (actions clic-droit)
install.sh          pose les liens symboliques (repo = source de vérité)
```

---

## 3. Configuration & secrets (jamais committés — cf `.gitignore`)

Sous `~/.claude/channels/discord/` :
- **`bots.json`** — tokens des bots-persona + Neo (secret, édité à la main) :
  ```json
  {
    "user_id": "<ton user id Discord — cible des DM>",
    "bots": {
      "Neo":         { "token": "…" },
      "Agent Smith": { "token": "…" },
      "Agent Brown": { "token": "…" }
    }
  }
  ```
- **`matrix/config.json`** — **pool de personas** (`personas`), `guild_id`, `repoMap`. Maintenu à la main ; la liste `personas` doit couvrir les personas de `bots.json`.
- **`matrix/state.json`** — état live : `{ "sessions": { "<uuid>": {agent, repo, cwd, started, seen, kitty_window_id, kitty_listen_on, …} } }`.

Un persona DM sous son propre bot s'il figure dans `bots.json` ; sinon ses notifs partent via **Neo** (repli).

---

## 4. Installation (de zéro)

**Prérequis** : `kitty` (≥ 0.47, userland), `python3` ; un **serveur Discord** « The Matrix » et **une app-bot par persona** (+ Neo).

1. **Cloner** ce repo dans `~/matrix`.
2. **Déployer les liens** : `./install.sh` (crée les symlinks ; sauvegarde tout fichier existant en `.bak`).
3. **PATH** : s'assurer que `~/.local/bin` est dans le PATH (pour `matrix` / `redpill`).
4. **Discord (bots-persona)** — pour **chaque** persona (+ **Neo**) dans le Developer Portal :
   - **New Application** (nom = le persona) ; onglet **General** → App Icon = le portrait du persona ; **Bot** → **Reset Token** (à copier).
   - Onglet **Installation** → **Install Link = None** (bot privé : on l'invite via l'URL OAuth2 de `matrix-bots`).
   - Poser `~/.claude/channels/discord/bots.json` (chmod 600) avec `user_id` + les tokens (cf §3).
   - `python3 ~/matrix/scripts/matrix-bots` → valide les tokens et imprime une **URL d'invitation** par bot. Ouvrir chaque URL pour **inviter le bot** sur le serveur (indispensable : un bot ne peut DM que s'il partage un serveur avec toi).
   - Renseigner le pool `personas` de `config.json` (aligné sur `bots.json`).
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

- **Lancer un agent** : clic-droit kitty → **Red Pill** (menu : reprendre une session récente **ou** nouvelle → choix du repo), ou `redpill` / `construct` dans un terminal, ou le **bouton `[⏏ Red Pill]`** dans matrix.
- **Voir les agents** : **The Matrix** (matrix). ⏎ = sauter sur la fenêtre de l'agent.
- Les notifs arrivent en **DM** sous l'identité de l'agent (repli Neo) ; « unplugged » (Neo) à la fermeture.

---

## 6. Évolution possible (non supportée aujourd'hui)

**Pilotage entrant depuis Discord** (répondre, approuver les permissions, `AskUserQuestion`) : reposerait sur les *channels* de Claude Code. En 2.1.201 (research preview) : l'injection entrante des canaux chargés en dev ne parvient pas à la session, le relais de permission est bridé, et `AskUserQuestion` n'est pas relayable (pas de hook/callback). À réévaluer quand les *channels* sortiront de preview (le socle bots-persona + `dm_send` est déjà en place pour ça).

---

## 7. Rollback / désinstallation

- **Revenir en arrière (fichiers)** : `install.sh` a sauvegardé chaque original en `<fichier>.bak`. Pour restaurer : supprimer le lien puis remettre le `.bak`, p.ex.
  ```bash
  rm ~/.claude/scripts/matrix && mv ~/.claude/scripts/matrix.bak ~/.claude/scripts/matrix
  ```
- **Désactiver les notifications / le titrage** : retirer les blocs correspondants de `~/.claude/settings.json` (`Notification`, `Stop`, `SessionEnd`, et `set-window-title.py` sous `SessionStart`).
- **Neutraliser rapidement** : supprimer `bots.json` → plus aucun DM (les hooks retombent en no-op silencieux) ; supprimer `state.json` → repart d'un registre vide.
