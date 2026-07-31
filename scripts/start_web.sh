#!/bin/sh
# Entrypoint du conteneur web : synchronise les élus (données réelles, API
# publique du Parlement, pas de clé requise) puis démarre le serveur.
# $PORT est fourni par les plateformes type Render ; 8000 par défaut ailleurs.
set -e

echo "[start] synchronisation des élus (parlament.ch)..."
python -m scraper.sync_members || echo "[start] échec de la synchronisation, on démarre quand même"

echo "[start] lancement du serveur web..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
