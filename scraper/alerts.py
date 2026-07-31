"""Alertes par mots-clés : après le pipeline quotidien, notifie par e-mail les
utilisateurs dont les mots-clés apparaissent dans les résumés du jour.

Usage manuel : python -m scraper.alerts 2026-03-04
(appelé automatiquement en fin de daily_transcripts)

Configuration SMTP dans .env : SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
SMTP_FROM. Sans configuration SMTP, les alertes sont listées en console
(mode dry-run) — pratique pour tester.
"""
import os
import smtplib
import sys
from datetime import date, datetime
from email.message import EmailMessage

sys.path.insert(0, ".")

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Alert, Debate, Summary  # noqa: E402

load_dotenv()
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "alertes@politrace.ch")
BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://politrace.ch").rstrip("/")

SUBJECT = {"fr": "Politrace — alerte mots-clés",
           "de": "Politrace — Stichwort-Alarm",
           "it": "Politrace — allerta parole chiave"}


def summaries_for_day(db, day: date):
    return db.execute(
        select(Summary).join(Debate).where(Debate.day == day)
        .options(selectinload(Summary.debate))
    ).scalars().all()


def matches(alert: Alert, s: Summary) -> list[str]:
    if s.lang != alert.lang:
        return []
    haystack = " ".join(filter(None, [s.title, s.body, s.stakes, s.outcome])).lower()
    return [k for k in (k.strip() for k in alert.keywords.split(","))
            if k and k.lower() in haystack]


def send_email(to: str, subject: str, body: str):
    if not SMTP_HOST:
        print(f"  [dry-run] → {to}\n  {subject}\n{body}\n{'-' * 40}")
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)


def notify_for_day(day: date) -> int:
    db = SessionLocal()
    summaries = summaries_for_day(db, day)
    if not summaries:
        db.close()
        return 0

    alerts = db.execute(
        select(Alert).where(Alert.active == True)  # noqa: E712
        .options(selectinload(Alert.user))
    ).scalars().all()

    sent = 0
    for alert in alerts:
        hits = []
        for s in summaries:
            found = matches(alert, s)
            if found:
                hits.append((s, found))
        if not hits:
            continue

        lines = [f"Résumés du {day.isoformat()} correspondant à vos mots-clés "
                 f"({alert.keywords}) :", ""]
        for s, found in hits:
            lines.append(f"• {s.title}")
            lines.append(f"  Mots-clés trouvés : {', '.join(found)}")
            lines.append(f"  {BASE_URL}/{alert.lang}/sessions/{day.isoformat()}")
            lines.append("")
        lines.append("— Politrace. Gérez vos alertes : "
                      f"{BASE_URL}/{alert.lang}/alertes")
        try:
            send_email(alert.user.email, SUBJECT.get(alert.lang, SUBJECT["fr"]),
                       "\n".join(lines))
            alert.last_match_at = datetime.utcnow()
            sent += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ! e-mail vers {alert.user.email} : {e}")
    db.commit()
    db.close()
    print(f"✓ Alertes : {sent} e-mail(s) envoyé(s).")
    return sent


if __name__ == "__main__":
    target = (date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today())
    notify_for_day(target)
