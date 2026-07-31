"""Importe d'autres personnalités publiques (juges fédéraux, conseillers
fédéraux, élus cantonaux…) depuis un CSV.

Usage : python -m scraper.import_people data/csv/juges_federaux.csv

Colonnes attendues (en-tête obligatoire, colonnes optionnelles laissables vides) :
  nom,prenom,fonction,institution,niveau,parti,canton,canton_abbr,annee_naissance,depuis

- fonction : parliament | federal_council | federal_judge | cantonal_exec | cantonal_parl
- niveau   : federal | cantonal
- depuis   : AAAA ou AAAA-MM-JJ (début de la fonction, crée une étape de parcours)

Exemple de ligne (juge fédérale) :
  Meyer,Anne,federal_judge,Tribunal fédéral,federal,PS,,,1968,2015

Sources pour remplir ces CSV :
- Juges fédéraux : liste publique sur bger.ch (avec parti d'élection) — les
  juges sont élus par l'Assemblée fédérale, leur affiliation partisane est
  publique et pertinente.
- Conseil fédéral : admin.ch.
- Cantons : sites officiels ou portails open data (ZH, GE, BE, VD…).

Les liens d'intérêts de ces personnes s'importent ensuite avec le même
sync_interests (rapprochement par nom/prénom).
Idempotent : la clé est (source='csv', source_id=fonction:nom:prenom).
"""
import csv
import sys
from datetime import date

sys.path.insert(0, ".")

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import Politician, Mandate  # noqa: E402

Base.metadata.create_all(engine)

VALID_ROLES = {"parliament", "federal_council", "federal_judge",
               "cantonal_exec", "cantonal_parl"}


def parse_since(v) -> date | None:
    v = str(v or "").strip()
    if not v:
        return None
    try:
        return date(int(v), 1, 1) if len(v) == 4 else date.fromisoformat(v[:10])
    except ValueError:
        return None


def main(path: str):
    db = SessionLocal()
    added = updated = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nom = (row.get("nom") or "").strip()
            prenom = (row.get("prenom") or "").strip()
            role = (row.get("fonction") or "").strip()
            if not nom or role not in VALID_ROLES:
                print(f"  ! ligne ignorée (nom/fonction invalide) : {row}")
                continue
            sid = f"{role}:{nom}:{prenom}".lower()
            p = db.query(Politician).filter_by(source="csv", source_id=sid).first()
            if p:
                updated += 1
            else:
                p = Politician(source="csv", source_id=sid)
                db.add(p)
                added += 1
            p.first_name, p.last_name = prenom, nom
            p.role_type = role
            p.level = (row.get("niveau") or "").strip() or \
                ("cantonal" if role.startswith("cantonal") else "federal")
            p.institution = (row.get("institution") or "").strip() or None
            p.party_abbr = (row.get("parti") or "").strip() or None
            p.canton = (row.get("canton") or "").strip() or None
            p.canton_abbr = (row.get("canton_abbr") or "").strip() or None
            year = (row.get("annee_naissance") or "").strip()
            p.birth_year = int(year) if year.isdigit() else None
            p.active = True
            db.flush()

            since = parse_since(row.get("depuis"))
            label = p.institution or role
            if not db.query(Mandate).filter_by(politician_id=p.id, kind="role",
                                               label=label, start=since).first():
                db.add(Mandate(politician_id=p.id, kind="role", label=label,
                               organization=p.party_abbr, start=since, source="csv"))
    db.commit()
    db.close()
    print(f"✓ Import : {added} personnes ajoutées, {updated} mises à jour.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
