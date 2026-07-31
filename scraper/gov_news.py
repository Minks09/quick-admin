"""Communiqués de la Confédération (Conseil fédéral, départements, offices)
via les flux RSS du News Service Bund — publiés toute l'année, 5-8 par jour.

Configuration dans .env :
  GOV_RSS_FEEDS=ABBR|url1,ABBR|url2,...   (ABBR = badge affiché, ex. CF, DFI)

Identifier les org-nr des organisations (Conseil fédéral, départements…) :
  python -m scraper.gov_news discover 1-30 101 201 301 401 1101
→ affiche le nom du canal de chaque flux. Voir .env.example et README §Sources.

Usage :
  python -m scraper.gov_news              # communiqués d'hier
  python -m scraper.gov_news 2026-07-09   # un jour précis
(appelé automatiquement par daily_transcripts)

Chaque communiqué est stocké comme un « débat » avec council_abbr='CF' :
résumés trilingues, alertes e-mail, recherche admin et cartes Instagram
fonctionnent donc sans rien changer.
"""
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, ".")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import Debate, Summary  # noqa: E402
from scraper.daily_transcripts import strip_html, RAW_DIR  # noqa: E402
from scraper.summarizer import summarize_communique  # noqa: E402

load_dotenv()
Base.metadata.create_all(engine)

# Chaque entrée : "URL" ou "ABBR|URL" (ex. "DFI|https://…&org-nr=NNN")
# L'abréviation s'affiche comme badge sur le site ; défaut : CF.
_raw_feeds = [u.strip() for u in os.getenv("GOV_RSS_FEEDS", "").split(",") if u.strip()]
FEEDS: list[tuple[str, str]] = []
for entry in _raw_feeds:
    if "|" in entry.split("://")[0]:  # préfixe ABBR| avant le schéma http
        abbr, url = entry.split("|", 1)
        FEEDS.append((abbr.strip()[:10] or "CF", url.strip()))
    else:
        FEEDS.append(("CF", entry))

# Gabarit pour le mode discover (org-nr inséré à la place de {org})
DISCOVER_BASE = os.getenv(
    "GOV_RSS_BASE",
    "https://www.news.admin.ch/NSBSubscriber/feeds/rss?lang=fr&topic=&kind=M&org-nr={org}")

MIN_TEXT = 200  # en dessous : brève sans substance, on saute


def parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 ou Atom, sans dépendance externe."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    ns_atom = "{http://www.w3.org/2005/Atom}"

    for it in root.iter("item"):  # RSS 2.0
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "description": it.findtext("description") or "",
            "date": _parse_date(it.findtext("pubDate")),
            "sender": (it.findtext("category") or it.findtext("author") or "").strip(),
        })
    for it in root.iter(f"{ns_atom}entry"):  # Atom
        link_el = it.find(f"{ns_atom}link")
        items.append({
            "title": (it.findtext(f"{ns_atom}title") or "").strip(),
            "link": (link_el.get("href", "") if link_el is not None else "").strip(),
            "description": it.findtext(f"{ns_atom}summary")
                           or it.findtext(f"{ns_atom}content") or "",
            "date": _parse_date(it.findtext(f"{ns_atom}updated")
                                or it.findtext(f"{ns_atom}published")),
            "sender": "",
        })
    return items


def _parse_date(value) -> date | None:
    if not value:
        return None
    value = value.strip()
    try:
        return parsedate_to_datetime(value).date()  # format RFC 822 (RSS)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()  # ISO (Atom)
    except ValueError:
        return None


def fetch_full_text(client: httpx.Client, url: str) -> str:
    """Récupère le texte complet du communiqué (la description RSS est tronquée)."""
    try:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        return strip_html(r.text)
    except httpx.HTTPError:
        return ""


def discover(org_numbers: list[str]):
    """Identifie à quelle organisation correspond chaque org-nr : interroge le
    flux et affiche le titre du canal + le dernier communiqué.

    Usage : python -m scraper.gov_news discover 1 2 3 101 201 301 401 1101
            python -m scraper.gov_news discover 1-30   (plage)
    """
    nrs: list[str] = []
    for token in org_numbers:
        if "-" in token and token.replace("-", "").isdigit():
            a, b = token.split("-", 1)
            nrs.extend(str(i) for i in range(int(a), int(b) + 1))
        else:
            nrs.append(token)

    client = httpx.Client(timeout=30, follow_redirects=True, headers={
        "User-Agent": "Politrace/1.0 (projet transparence)"})
    for nr in nrs:
        url = DISCOVER_BASE.format(org=nr)
        try:
            r = client.get(url)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            channel = root.findtext("channel/title") or \
                root.findtext("{http://www.w3.org/2005/Atom}title") or "?"
            first = root.findtext("channel/item/title") or ""
            print(f"org-nr={nr:>5} → {channel.strip()[:70]}"
                  f"{' | dernier : ' + first.strip()[:60] if first else ''}")
        except (httpx.HTTPError, ET.ParseError) as e:
            print(f"org-nr={nr:>5} → erreur ({type(e).__name__})")


def run(day: date) -> int:
    if not FEEDS:
        print("GOV_RSS_FEEDS non défini — communiqués fédéraux ignorés (voir README).")
        return 0

    client = httpx.Client(timeout=60, headers={
        "User-Agent": "Politrace/1.0 (projet transparence)"})
    db = SessionLocal()

    print(f"→ Communiqués fédéraux du {day.isoformat()}…")
    seen_links: set[str] = set()
    n_summarized = 0

    for abbr, feed_url in FEEDS:
        try:
            r = client.get(feed_url, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as e:
            print(f"  ! flux {feed_url} : {e}")
            continue
        for item in parse_feed(r.text):
            if item["date"] != day or not item["link"] or item["link"] in seen_links:
                continue
            seen_links.add(item["link"])

            subject_id = "nsb-" + hashlib.sha1(item["link"].encode()).hexdigest()[:16]
            deb = db.query(Debate).filter_by(
                day=day, council_abbr=abbr, subject_id=subject_id).first()
            if deb and deb.summaries:
                continue  # déjà traité

            text = fetch_full_text(client, item["link"]) or strip_html(item["description"])
            if len(text) < MIN_TEXT:
                continue

            if not deb:
                raw_path = RAW_DIR / f"{day.isoformat()}_{abbr}_{subject_id}.txt"
                raw_path.write_text(f"{item['link']}\n\n{text}", encoding="utf-8")
                deb = Debate(day=day, council_abbr=abbr, subject_id=subject_id,
                             raw_title=item["title"][:500] or None,
                             transcript_count=1, raw_text_path=str(raw_path))
                db.add(deb)
                db.flush()

            print(f"  → Résumé : {item['title'][:70]}…")
            try:
                result = summarize_communique(item["title"], item["sender"],
                                              day.isoformat(), text)
            except Exception as e:  # noqa: BLE001
                print(f"    ! API Claude : {e}")
                db.commit()
                continue
            if not result:
                print("    ! JSON invalide, communiqué sauté.")
                db.commit()
                continue

            groups = result.get("groups") or []
            if isinstance(groups, list) and groups:
                deb.groups = "|".join(str(g)[:20] for g in groups[:10])

            for lang in ("fr", "de", "it"):
                s = result.get(lang) or {}
                if not s.get("title"):
                    continue
                db.add(Summary(debate_id=deb.id, lang=lang,
                               title=s["title"][:300], body=s.get("body", ""),
                               stakes=s.get("stakes") or None,
                               outcome=s.get("outcome") or None))
            db.commit()
            n_summarized += 1

    db.close()
    print(f"✓ {n_summarized} communiqués résumés.")
    return n_summarized


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "discover":
        discover(sys.argv[2:] or ["1-10"])
    else:
        target = (date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1
                  else date.today() - timedelta(days=1))
        run(target)
