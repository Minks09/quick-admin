"""Code couleur des partis/groupes fédéraux suisses (couleurs conventionnelles).

Utilisé sur le site (pastilles) et sur les cartes Instagram pour identifier
les groupes d'un coup d'œil. Facile à mettre à jour si le paysage change.
"""

PARTY_COLORS: dict[str, str] = {
    # Abréviations FR/DE courantes → hex
    "UDC": "#00823D", "SVP": "#00823D",
    "PS": "#E4002B", "SP": "#E4002B", "PSS": "#E4002B",
    "PLR": "#0E52A0", "FDP": "#0E52A0",
    "Centre": "#F39200", "Mitte": "#F39200", "M-E": "#F39200",
    "VERT-E-S": "#84B414", "Vert-e-s": "#84B414", "GRÜNE": "#84B414",
    "Verts": "#84B414", "GPS": "#84B414",
    "PVL": "#0BA1A8", "pvl": "#0BA1A8", "GLP": "#0BA1A8",
    "PEV": "#FFD500", "EVP": "#FFD500",
    "MCG": "#FFDD00",
    "Lega": "#1C39BB",
    "EDU": "#8B6F4E", "UDF": "#8B6F4E",
    "PdT": "#B71C1C", "PST": "#B71C1C", "POP": "#B71C1C",
}
DEFAULT_COLOR = "#5A6672"  # gris acier pour indépendants / inconnus


def party_color(abbr: str | None) -> str:
    if not abbr:
        return DEFAULT_COLOR
    return PARTY_COLORS.get(abbr.strip(), DEFAULT_COLOR)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore
