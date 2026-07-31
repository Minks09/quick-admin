"""Génère un carrousel Instagram (1080×1350) à partir des résumés d'un jour :
1 carte de couverture + 1 carte par débat (max 9, limite carrousel = 10),
plus une légende prête à publier. Sortie : data/ig_out/AAAA-MM-JJ/

Usage : python -m scraper.instagram.make_cards 2026-03-04
(appelé automatiquement en fin de daily_transcripts)
"""
import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Debate, Summary, IGPost  # noqa: E402
from scraper.party_colors import party_color, hex_to_rgb  # noqa: E402

W, H = 1080, 1350
PAPER = (238, 240, 237)
INK = (18, 21, 25)
RED = (218, 41, 28)
STEEL = (90, 102, 114)
OUT = Path("data/ig_out")

MONTHS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


def font(size: int, bold=False):
    """Polices : dépose Archivo-Bold.ttf / Archivo-Regular.ttf dans ce dossier
    pour un rendu conforme au site ; sinon repli sur DejaVu (préinstallée)."""
    here = Path(__file__).parent
    custom = here / ("Archivo-Bold.ttf" if bold else "Archivo-Regular.ttf")
    if custom.exists():
        return ImageFont.truetype(str(custom), size)
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for base in ("/usr/share/fonts/truetype/dejavu/", ""):
        try:
            return ImageFont.truetype(base + name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fmt_date(day: date) -> str:
    return f"{day.day} {MONTHS_FR[day.month]} {day.year}"


def draw_frame(d: ImageDraw.ImageDraw, page: int, total: int, day: date | None = None):
    d.rectangle([0, 0, W, 14], fill=INK)                      # barre haute
    d.rectangle([60, H - 90, 60 + 26, H - 64], fill=RED)      # carré signature
    d.text((100, H - 92), "politrace.ch", font=font(30, True), fill=INK)
    if day:
        d.text((W / 2, H - 92), fmt_date(day).upper(), font=font(28), fill=STEEL, anchor="ma")
    d.text((W - 60, H - 92), f"{page}/{total}", font=font(30), fill=STEEL, anchor="ra")


def wrap(d, text, f, max_width):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if d.textlength(trial, font=f) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def cover_card(day: date, n_debates: int, total: int) -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    draw_frame(d, 1, total, day)
    d.text((60, 90), "SESSION EN BREF", font=font(40, True), fill=RED)
    date_str = f"{day.day} {MONTHS_FR[day.month]}\n{day.year}"
    d.multiline_text((60, 200), date_str, font=font(150, True), fill=INK, spacing=12)
    d.text((60, 640), f"{n_debates} sujets résumés", font=font(52, True), fill=INK)
    sub = ("L'essentiel de la politique fédérale d'hier,\n"
           "résumé simplement : le sujet, les enjeux, l'issue.")
    d.multiline_text((60, 730), sub, font=font(38), fill=STEEL, spacing=14)
    d.rectangle([60, 900, 380, 906], fill=INK)
    return img


def groups_row(d: ImageDraw.ImageDraw, y: int, groups: list[str]) -> int:
    """Dessine les groupes impliqués avec leur code couleur ; renvoie le y suivant."""
    x = 60
    f = font(28, True)
    for g in groups[:7]:
        color = hex_to_rgb(party_color(g))
        w_txt = d.textlength(g, font=f)
        d.rectangle([x, y, x + 22, y + 22], fill=color)
        d.text((x + 32, y - 4), g, font=f, fill=INK)
        x += 32 + w_txt + 28
        if x > W - 160:
            break
    return y + 54


def debate_card(page: int, total: int, council: str, title: str,
                stakes: str, outcome: str, groups: list[str] | None = None,
                day: date | None = None) -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    draw_frame(d, page, total, day)
    council_lbl = {"N": "CONSEIL NATIONAL", "S": "CONSEIL DES ÉTATS",
                   "CF": "CONSEIL FÉDÉRAL"}.get(council, council)
    d.text((60, 80), council_lbl, font=font(30, True), fill=STEEL)
    if day:
        d.text((W - 60, 80), fmt_date(day).upper(), font=font(30, True), fill=STEEL, anchor="ra")

    y = 140
    for line in wrap(d, title, font(58, True), W - 120)[:4]:
        d.text((60, y), line, font=font(58, True), fill=INK)
        y += 72

    if groups:
        y += 16
        y = groups_row(d, y, groups)

    y += 30
    d.text((60, y), "ENJEUX", font=font(28, True), fill=RED)
    y += 46
    for line in wrap(d, textwrap.shorten(stakes or "", 420, placeholder="…"),
                     font(38), W - 120)[:7]:
        d.text((60, y), line, font=font(38), fill=INK)
        y += 52

    if outcome:
        y += 24
        d.text((60, y), "ISSUE", font=font(28, True), fill=RED)
        y += 46
        for line in wrap(d, textwrap.shorten(outcome, 220, placeholder="…"),
                         font(38), W - 120)[:4]:
            d.text((60, y), line, font=font(38), fill=INK)
            y += 52
    return img


def make_for_day(day: date) -> list[str]:
    db = SessionLocal()
    rows = db.execute(
        select(Debate, Summary).join(Summary)
        .where(Debate.day == day, Summary.lang == "fr")
        .order_by(Debate.council_abbr, Debate.id)
    ).all()
    if not rows:
        print("Aucun résumé pour ce jour — pas de visuels générés.")
        return []

    rows = rows[:9]
    total = len(rows) + 1
    out_dir = OUT / day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    p = out_dir / "00_cover.png"
    cover_card(day, len(rows), total).save(p)
    paths.append(str(p))
    for i, (deb, s) in enumerate(rows, start=2):
        p = out_dir / f"{i - 1:02d}_{deb.council_abbr}.png"
        debate_card(i, total, deb.council_abbr or "?", s.title,
                    s.stakes or s.body, s.outcome or "",
                    groups=(deb.groups or "").split("|") if deb.groups else None,
                    day=day).save(p)
        paths.append(str(p))

    caption = build_caption(day, rows)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")

    post = db.query(IGPost).filter_by(day=day).first() or IGPost(day=day)
    post.caption = caption
    post.image_paths = "|".join(paths)
    db.merge(post)
    db.commit()
    db.close()
    print(f"✓ {len(paths)} cartes générées dans {out_dir}/ (+ caption.txt)")
    return paths


def build_caption(day: date, rows) -> str:
    lines = [f"📌 {day.day} {MONTHS_FR[day.month]} {day.year} — la politique fédérale en bref.\n"]
    for deb, s in rows:
        c = {"N": "CN", "S": "CE", "CF": "CF"}.get(deb.council_abbr, "")
        lines.append(f"▪️ [{c}] {s.title}")
    lines.append("\nRésumés complets en FR/DE/IT sur politrace.ch (lien en bio).")
    lines.append("Résumés générés par IA à partir du Bulletin officiel — le texte officiel fait foi.")
    lines.append("\n#Suisse #Politique #Parlement #ConseilNational #ConseilDesEtats #Transparence #Schweiz #Politik #Svizzera")
    return "\n".join(lines)


if __name__ == "__main__":
    make_for_day(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1
                 else date.today())
