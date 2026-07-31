"""Rattrapage historique : remplit la base avec les débats des sessions passées.

Usage :
  python -m scraper.backfill 2025-09-01 2026-07-01              # débats + textes bruts, SANS résumés (gratuit)
  python -m scraper.backfill 2025-09-01 2026-07-01 --summarize  # avec résumés Claude (coûte des crédits API !)

Fonctionnement :
- Parcourt chaque jour de la période et interroge l'API du Parlement.
- Les jours sans session ne renvoient rien → passés en une requête légère.
- Idempotent : relançable sans doublons (les débats déjà résumés sont sautés).
- Sans --summarize, les textes bruts sont archivés dans data/raw/ ; vous pouvez
  résumer plus tard, jour par jour :
      python -m scraper.daily_transcripts 2026-03-04

⚠️ Coût : ~60 jours de session/an × 20-40 débats/jour. Résumer une année
complète représente un vrai budget API — commencez sans --summarize, puis
résumez sélectivement les jours qui vous intéressent.
"""
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, ".")

from scraper.daily_transcripts import run  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    summarize = "--summarize" in sys.argv
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    start, end = date.fromisoformat(args[0]), date.fromisoformat(args[1])

    day = start
    total_days = 0
    while day <= end:
        if day.weekday() < 5:  # le Parlement ne siège pas le week-end
            try:
                n = run(day, summarize=summarize)
                if n or True:
                    total_days += 1
            except Exception as e:  # noqa: BLE001
                print(f"! {day}: {e} — nouvel essai dans 30 s")
                time.sleep(30)
                continue
            time.sleep(1)  # rester courtois avec l'API
        day += timedelta(days=1)
    print(f"✓ Rattrapage terminé ({total_days} jours parcourus).")


if __name__ == "__main__":
    main()
