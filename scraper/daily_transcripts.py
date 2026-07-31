"""Pipeline quotidien : récupère les retranscriptions de la veille, les regroupe
par débat (IdSubject), résume via Claude en FR/DE/IT, stocke tout, puis génère
les visuels + légende Instagram.

Usage :
  python -m scraper.daily_transcripts              # la veille
  python -m scraper.daily_transcripts 2026-03-04   # un jour précis

Hors session parlementaire : aucune retranscription → le script se termine
proprement. À planifier chaque matin (systemd timer / cron, voir deploy/).
"""
import html
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, ".")

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import Debate, Summary  # noqa: E402
from scraper.parlament_client import ParlamentClient  # noqa: E402
from scraper.summarizer import summarize_debate  # noqa: E402

Base.metadata.create_all(engine)
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return html.unescape(TAG_RE.sub(" ", text or "")).replace("\xa0", " ").strip()


def group_by_debate(transcripts):
    """Regroupe les retranscriptions par (IdSubject, conseil)."""
    groups: dict[tuple, dict] = {}
    for t in transcripts:
        subject = str(t.get("IdSubject") or t.get("IdSession") or "0")
        council = (t.get("CouncilAbbreviation")
                   or t.get("MeetingCouncilAbbreviation") or "?")
        key = (subject, council)
        g = groups.setdefault(key, {
            "subject_id": subject, "council": council,
            "title": None, "business": None, "parts": [],
        })
        g["title"] = g["title"] or t.get("VoteBusinessTitle") or t.get("SubjectTitle") \
            or t.get("BusinessTitle") or t.get("Title")
        g["business"] = g["business"] or t.get("BusinessNumber") or t.get("BusinessShortNumber")
        speaker = t.get("SpeakerFullName") or ""
        func = t.get("SpeakerFunction") or t.get("Function") or ""
        text = strip_html(t.get("Text") or "")
        if text:
            head = f"[{speaker}{' — ' + func if func else ''}]" if speaker else ""
            g["parts"].append(f"{head}\n{text}")
    return groups


def run(day: date, summarize: bool = True):
    client = ParlamentClient()
    db = SessionLocal()

    print(f"→ Retranscriptions du {day.isoformat()}…")
    transcripts = list(client.transcripts_for_day(day))
    if not transcripts:
        print("  Aucune retranscription (pas de session ce jour). Fin.")
        return 0

    groups = group_by_debate(transcripts)
    print(f"  {len(transcripts)} interventions → {len(groups)} débats.")

    n_summarized = 0
    for (subject, council), g in groups.items():
        full_text = "\n\n".join(g["parts"])
        if len(full_text) < 400:   # points d'ordre, annonces : on saute
            continue

        deb = db.query(Debate).filter_by(
            day=day, council_abbr=council, subject_id=subject).first()
        if deb and deb.summaries:
            continue  # déjà traité (relance idempotente)
        if not deb:
            raw_path = RAW_DIR / f"{day.isoformat()}_{council}_{subject}.txt"
            raw_path.write_text(full_text, encoding="utf-8")
            deb = Debate(day=day, council_abbr=council, subject_id=subject,
                         business_number=str(g["business"] or "") or None,
                         raw_title=(g["title"] or "")[:500] or None,
                         transcript_count=len(g["parts"]),
                         raw_text_path=str(raw_path))
            db.add(deb)
            db.flush()

        if not summarize:
            db.commit()
            continue

        print(f"  → Résumé : {g['title'] or subject} ({council})…")
        try:
            result = summarize_debate(g["title"] or "", council, day.isoformat(), full_text)
        except Exception as e:  # noqa: BLE001
            print(f"    ! API Claude : {e}")
            db.commit()
            continue
        if not result:
            print("    ! JSON invalide, débat sauté (relancez le script plus tard).")
            db.commit()
            continue

        groups = result.get("groups") or []
        if isinstance(groups, list):
            deb.groups = "|".join(str(g)[:20] for g in groups[:10]) or None

        for lang in ("fr", "de", "it"):
            s = result.get(lang) or {}
            if not s.get("title"):
                continue
            db.add(Summary(debate_id=deb.id, lang=lang,
                           title=s["title"][:300],
                           body=s.get("body", ""),
                           stakes=s.get("stakes") or None,
                           outcome=s.get("outcome") or None))
        db.commit()
        n_summarized += 1

    db.close()
    print(f"✓ {n_summarized} débats résumés.")
    return n_summarized


if __name__ == "__main__":
    target = (date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1
              else date.today() - timedelta(days=1))
    n = run(target)

    # Communiqués du Conseil fédéral et de l'administration (toute l'année)
    from scraper.gov_news import run as run_gov
    n += run_gov(target)

    if n:
        # Génère les visuels Instagram du jour traité
        from scraper.instagram.make_cards import make_for_day
        make_for_day(target)
        # Envoie les alertes e-mail par mots-clés
        from scraper.alerts import notify_for_day
        notify_for_day(target)
