"""Synchronise les élus fédéraux (Conseil national + Conseil des États) et leur parcours.

Usage : python -m scraper.sync_members
À lancer 1×/semaine (les compositions changent rarement hors élections).
"""
import sys
from datetime import date

sys.path.insert(0, ".")

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import Politician, Mandate  # noqa: E402
from scraper.parlament_client import ParlamentClient, parse_odata_date  # noqa: E402

Base.metadata.create_all(engine)


def upsert_member(db, m: dict):
    pid = m.get("PersonNumber")
    if not pid:
        return None
    p = db.query(Politician).filter_by(source="parlament", source_id=str(pid)).first()
    if not p:
        p = Politician(source="parlament", source_id=str(pid))
        db.add(p)
    p.role_type = "parliament"
    p.level = "federal"
    p.institution = m.get("CouncilName")
    p.first_name = m.get("FirstName", "") or ""
    p.last_name = m.get("LastName", "") or ""
    p.party_abbr = m.get("PartyAbbreviation")
    p.party_name = m.get("PartyName")
    p.canton = m.get("CantonName")
    p.canton_abbr = m.get("CantonAbbreviation")
    p.council = m.get("CouncilName")
    p.gender = (m.get("GenderAsString") or "")[:1] or None
    birth = parse_odata_date(m.get("DateOfBirth"))
    p.birth_year = birth.year if birth else None
    p.date_joining = parse_odata_date(m.get("DateJoining"))
    p.active = bool(m.get("Active", True))
    db.flush()
    return p.id


def upsert_history(db, pid: int, h: dict):
    label = h.get("CouncilName") or "Mandat"
    start = parse_odata_date(h.get("DateJoining"))
    exists = db.query(Mandate).filter_by(
        politician_id=pid, kind="council", label=label, start=start).first()
    if exists:
        exists.end = parse_odata_date(h.get("DateLeaving"))
        return
    db.add(Mandate(
        politician_id=pid, kind="council", label=label,
        organization=h.get("ParlGroupName") or h.get("PartyName"),
        start=start, end=parse_odata_date(h.get("DateLeaving")),
        source="parlament.ch",
    ))


def main():
    client = ParlamentClient()
    db = SessionLocal()
    seen: dict[int, int] = {}  # id interne -> PersonNumber

    print("→ Téléchargement des membres actifs…")
    for m in client.active_members(lang="FR"):
        internal_id = upsert_member(db, m)
        if internal_id:
            seen[internal_id] = m["PersonNumber"]
    db.commit()
    print(f"  {len(seen)} élu·es synchronisés.")

    print("→ Parcours (historique des mandats)…")
    for i, (internal_id, person_number) in enumerate(sorted(seen.items()), 1):
        try:
            for h in client.member_history(person_number, lang="FR"):
                upsert_history(db, internal_id, h)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            print(f"  ! historique {person_number}: {e}")
        if i % 25 == 0:
            print(f"  {i}/{len(seen)}")

    # désactiver les parlementaires qui ne sont plus dans la liste
    # (uniquement source=parlament : ne touche pas aux juges, cantonaux, etc.)
    db.query(Politician).filter(
        Politician.source == "parlament",
        ~Politician.id.in_(seen.keys()),
    ).update({"active": False}, synchronize_session=False)
    db.commit()
    db.close()
    print("✓ Terminé.")


if __name__ == "__main__":
    main()
