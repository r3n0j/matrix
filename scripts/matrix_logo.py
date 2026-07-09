"""matrix_logo — bannière visuelle partagée (logo figlet MATRIX + pluie de code katakana).

La pluie est un instantané généré une fois par process (fixe pendant toute la vie du
programme, régénérée à chaque lancement). Utilisé par le lanceur `matrix` (intro) et
par `redpill` (en-tête), pour un logo strictement identique entre les deux.
"""
import random
import re

GREEN, BRIGHT, DIM, RESET = "\033[32m", "\033[92m", "\033[2m", "\033[0m"
WHITE, DARK = "\033[97m", "\033[2;32m"

FIGLET = [
    " __  __   _ _____ ___ _____  __",
    "|  \\/  | /_\\_   _| _ \\_ _\\ \\/ /",
    "| |\\/| |/ _ \\| | |   /| | >  <",
]
LOGO_W = max(len(line) for line in FIGLET)
RAIN_ROWS = 5
BANNER_ROWS = len(FIGLET) + RAIN_ROWS  # hauteur du bloc bannière
KATA = "ｦｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def vis(s):
    """Largeur visible (glyphes demi-largeur uniquement -> len après strip ANSI)."""
    return len(ANSI_RE.sub("", s))


def _rain_color(dist):
    """Contraste tête→traîne : blanc vif, vert vif, vert, vert sombre."""
    return (WHITE, BRIGHT, GREEN, GREEN, DARK)[min(dist, 4)]


def _gen_rain():
    """Instantané de pluie : colonnes de hauteurs inégales, tête vive."""
    grid = [[None] * LOGO_W for _ in range(RAIN_ROWS)]
    for c in range(LOGO_W):
        if random.random() < 0.4:  # colonnes vides -> bords irréguliers
            continue
        head = random.randint(0, RAIN_ROWS - 1)
        length = random.randint(1, RAIN_ROWS)
        for k in range(length):
            r = head - k  # la traîne remonte depuis la tête
            if 0 <= r < RAIN_ROWS:
                grid[r][c] = (random.choice(KATA), _rain_color(k))
    return grid


_RAIN = _gen_rain()


def banner_rows():
    """Lignes du bloc bannière (logo + pluie), chacune cadrée à LOGO_W colonnes visibles."""
    rows = ["%s%s%s" % (BRIGHT, line.ljust(LOGO_W), RESET) for line in FIGLET]
    for r in range(RAIN_ROWS):
        cells = []
        for c in range(LOGO_W):
            cell = _RAIN[r][c]
            cells.append(" " if cell is None else "%s%s%s" % (cell[1], cell[0], RESET))
        rows.append("".join(cells))
    return rows


def overlay_right(left, width, banner=None):
    """Compose `left` (lignes de texte) avec le bloc bannière calé sur le bord droit `width`.

    Renvoie une liste de lignes (hauteur = max des deux blocs). La bannière est masquée
    si le terminal est trop étroit pour la loger sans chevaucher le texte."""
    banner = banner_rows() if banner is None else banner
    n = max(len(left), len(banner))
    left = list(left) + [""] * (n - len(left))
    banner = list(banner) + [""] * (n - len(banner))
    max_left = max((vis(x) for x in left), default=0)
    fits = width >= max_left + LOGO_W + 2
    out = []
    for lft, rgt in zip(left, banner):
        if fits and vis(rgt):
            out.append(lft + " " * (width - vis(lft) - vis(rgt)) + rgt)
        else:
            out.append(lft)
    return out
