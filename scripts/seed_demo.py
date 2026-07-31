"""Injecte des données FICTIVES pour voir le site fonctionner avant le premier
vrai scraping. À NE PAS lancer en production.

Usage : python -m scripts.seed_demo
Nettoyage : supprimez le fichier de base de données et relancez les syncs.
"""
import sys
from datetime import date

sys.path.insert(0, ".")

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import Politician, Mandate, Interest, Debate, Summary  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()

p = Politician(id=999901, source="demo", source_id="1",
               role_type="parliament", level="federal",
               first_name="Exemple", last_name="Démo",
               party_abbr="XYZ", party_name="Parti fictif", canton="Vaud",
               canton_abbr="VD", council="Conseil national",
               birth_year=1975, active=True)
db.merge(p)
db.merge(Mandate(id=1, politician_id=999901, kind="council",
                 label="Conseil national", organization="Groupe fictif",
                 start=date(2019, 12, 2), source="demo"))
db.merge(Interest(id=1, politician_id=999901, organization="Association Alpha",
                  function="Membre du comité", sector="Santé", paid="yes",
                  since=date(2021, 1, 1), source="demo"))
db.merge(Interest(id=2, politician_id=999901, organization="Fondation Bêta",
                  function="Présidente", sector="Énergie", paid="no", source="demo"))

deb = Debate(id=1, day=date(2026, 3, 4), council_abbr="N", subject_id="demo-1",
             business_number="24.999", raw_title="Objet de démonstration",
             transcript_count=12)
db.merge(deb)
texts = {
    "fr": ("Loi fictive sur la démonstration : le Conseil national entre en matière",
           "Ceci est un résumé de démonstration. Le Conseil national a débattu d'un objet fictif pour illustrer le rendu du site. Les groupes ont exposé des positions contrastées.",
           "Cet exemple montre où apparaissent les tenants et aboutissants du débat.",
           "Entrée en matière acceptée ; l'objet passe au vote sur l'ensemble (fictif)."),
    "de": ("Fiktives Demonstrationsgesetz: Nationalrat tritt ein",
           "Dies ist eine Demo-Zusammenfassung zur Illustration der Website.",
           "Hier stünde, worum es geht.", "Eintreten beschlossen (fiktiv)."),
    "it": ("Legge fittizia di dimostrazione: il Nazionale entra in materia",
           "Questo è un riassunto dimostrativo per illustrare il sito.",
           "Qui apparirebbe la posta in gioco.", "Entrata in materia accettata (fittizio)."),
}
for i, (lang, (t, b, s, o)) in enumerate(texts.items(), start=1):
    db.merge(Summary(id=i, debate_id=1, lang=lang, title=t, body=b,
                     stakes=s, outcome=o))
db.commit()
db.close()
print("✓ Données de démo injectées. Lancez le site : uvicorn app.main:app --reload")
