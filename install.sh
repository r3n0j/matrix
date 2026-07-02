#!/usr/bin/env bash
# Déploie The Matrix : liens symboliques depuis CE repo vers ~/.claude, ~/.config/kitty,
# ~/.local/bin et ~/.local/share/applications. Le repo devient la source de vérité :
# éditer un fichier du repo = éditer le fichier live.
#
# Les fichiers existants (non-liens) sont sauvegardés en .bak avant d'être remplacés.
# NON gérés (restent des fichiers live, hors repo) : les secrets
# (~/.claude/channels/discord/.env, .../matrix/config.json, state.json) et l'image
# de fond (~/.config/kitty/matrix-bg.png).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

link() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ]; then
    rm -f "$dst"
  elif [ -e "$dst" ]; then
    mv "$dst" "$dst.bak"
    echo "  sauvegardé : $dst.bak"
  fi
  ln -s "$src" "$dst"
  echo "  lien : ${dst/#$HOME/\~} -> ${src/#$HOME/\~}"
}

echo "Déploiement de The Matrix depuis ${REPO/#$HOME/\~}"
chmod +x "$REPO"/scripts/matrix "$REPO"/scripts/redpill "$REPO"/scripts/matrix-setup \
         "$REPO"/scripts/claude-sessions 2>/dev/null || true

for f in "$REPO"/scripts/*; do link "$f" "$HOME/.claude/scripts/$(basename "$f")"; done
for f in "$REPO"/hooks/*;   do link "$f" "$HOME/.claude/hooks/$(basename "$f")"; done
for f in "$REPO"/kitty/*.conf; do link "$f" "$HOME/.config/kitty/$(basename "$f")"; done
for f in "$REPO"/kitty/sessions/*.session; do link "$f" "$HOME/.config/kitty/sessions/$(basename "$f")"; done
link "$REPO/kitty/kitty.desktop" "$HOME/.local/share/applications/kitty.desktop"
link "$REPO/scripts/matrix"  "$HOME/.local/bin/matrix"
link "$REPO/scripts/redpill" "$HOME/.local/bin/redpill"

echo
echo "Terminé."
echo "Rappels : hooks à câbler dans ~/.claude/settings.json (Notification/Stop/SessionEnd/SessionStart) ;"
echo "         Discord = poser ~/.claude/channels/discord/.env (token) puis lancer scripts/matrix-setup."
