"""Importe les liens d'intérêts des élus.

Deux modes :
1. API Lobbywatch (si LOBBYWATCH_API est défini dans .env)
   Lobbywatch.ch documente une interface de données sur son site
   (« Daten/Schnittstelle »). L'URL et le schéma exacts doivent être
   VÉRIFIÉS avant mise en production — voir README §Sources.
   Le code ci-dessous s'adapte via LW_FIELD_MAP.

2. Import CSV (recommandé pour démarrer) :
   python -m scraper.sync_interests data/csv/interets.csv
   Colonnes attendues (en-tête obligatoire) :
   nom,prenom,organisation,fonction,secteur,remunere,depuis
   `remunere` : oui|non|inconnu — `depuis` : AAAA ou AAAA-MM-JJ (optionnel)

Le rapprochement se fait par (nom, prénom) normalisés.
"""
import csv
import os
import sys
import unicodedata
from datetime import date

sys.path.insert(0, ".")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import Politician, Interest  # noqa: E402

load_dotenv()
Base.metadata.create_all(engine)

LOBBYWATCH_API = os.getenv("LOBBYWATCH_API", "").strip()

# Adapter ces clés au schéma réel de l'API Lobbywatch après vérification.
LW_FIELD_MAP = {
    "last_name": "nachname",
    "first_name": "vorname",
    "organization": "organisation_name",
    "function": "art",
    "sector": "branche",
    "paid": "verguetung",
    "since": "von",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().strip()


def build_index(db) -> dict[tuple[str, str], int]:
    return {(norm(p.last_name), norm(p.first_name)): p.id
            for p in db.query(Politician).all()}


def parse_since(v) -> date | None:
    v = str(v or "").strip()
    if not v:
        return None
    try:
        if len(v) == 4:
            return date(int(v), 1, 1)
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def upsert(db, pid: int, org: str, fn: str | None, sector: str | None,
           paid: str | None, since: date | None, source: str):
    org = (org or "").strip()[:300]
    if not org:
        return False
    fn = (fn or "").strip()[:200] or None
    row = db.query(Interest).filter_by(
        politician_id=pid, organization=org, function=fn).first()
    if row:
        row.sector, row.paid, row.since = sector, paid, since or row.since
        return False
    db.add(Interest(politician_id=pid, organization=org, function=fn,
                    sector=(sector or "").strip()[:120] or None,
                    paid=paid, since=since, source=source))
    return True


def normalize_paid(v) -> str:
    v = norm(str(v or ""))
    if v in ("oui", "ja", "si", "yes", "bezahlt", "1", "true"):
        return "yes"
    if v in ("non", "nein", "no", "unbezahlt", "0", "false"):
        return "no"
    return "unknown"


def import_csv(path: str):
    db = SessionLocal()
    index = build_index(db)
    added = missed = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (norm(row.get("nom", "")), norm(row.get("prenom", "")))
            pid = index.get(key)
            if not pid:
                missed += 1
                continue
            if upsert(db, pid, row.get("organisation", ""), row.get("fonction"),
                      row.get("secteur"), normalize_paid(row.get("remunere")),
                      parse_since(row.get("depuis")), source="csv"):
                added += 1
    db.commit()
    db.close()
    print(f"✓ CSV importé : {added} liens ajoutés, {missed} lignes sans correspondance.")


def import_api():
    if not LOBBYWATCH_API:
        print("LOBBYWATCH_API non défini dans .env — utilisez l'import CSV :")
        print("  python -m scraper.sync_interests data/csv/interets.csv")
        sys.exit(1)
    db = SessionLocal()
    index = build_index(db)
    r = httpx.get(LOBBYWATCH_API, timeout=120,
                  headers={"User-Agent": "Politrace/1.0"})
    r.raise_for_status()
    data = r.json()
    rows = data.get("data", data) if isinstance(data, dict) else data
    fm = LW_FIELD_MAP
    added = missed = 0
    for row in rows:
        key = (norm(str(row.get(fm["last_name"], ""))),
               norm(str(row.get(fm["first_name"], ""))))
        pid = index.get(key)
        if not pid:
            missed += 1
            continue
        if upsert(db, pid, str(row.get(fm["organization"], "")),
                  str(row.get(fm["function"], "") or "") or None,
                  str(row.get(fm["sector"], "") or "") or None,
                  normalize_paid(row.get(fm["paid"])),
                  parse_since(row.get(fm["since"])), source="lobbywatch"):
            added += 1
    db.commit()
    db.close()
    print(f"✓ API importée : {added} liens ajoutés, {missed} lignes sans correspondance.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        import_csv(sys.argv[1])
    else:
        import_api()
