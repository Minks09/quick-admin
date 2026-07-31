# Politrace

Site de transparence politique suisse : parcours des élu·es fédéraux, liens
d'intérêts derrière chaque politicien·ne, et résumé quotidien automatique
(FR/DE/IT) des débats parlementaires — avec génération de carrousels Instagram.

## Architecture

```
[ws.parlament.ch OData]        [Lobbywatch / CSV]
   élus + parcours +              liens d'intérêts
   retranscriptions (BO)               |
        |                              |
        v                              v
  scraper/ (Python) ----> SQLite/Postgres <---- app/ (FastAPI, site FR/DE/IT)
        |
        +--> API Claude : résumés (tenants, aboutissants, issue) x 3 langues
        +--> Pillow : carrousel Instagram 1080x1350 + légende
        +--> (optionnel) API Meta Graph : publication auto
```

- **Pipeline quotidien** (`scraper/daily_transcripts.py`, timer systemd 06:30) :
  deux sources → (a) retranscriptions parlementaires de la veille (en session
  uniquement, ~60 jours/an) et (b) communiqués de la Confédération via les
  flux RSS du News Service Bund (Conseil fédéral, départements — toute
  l'année, 5-8/jour). Chaque élément est résumé par Claude en FR/DE/IT
  (sujet, enjeux, issue), publié sur le site (étiquette « Conseil fédéral /
  administration » pour les communiqués), inclus dans les alertes e-mail et
  les cartes Instagram. Pour activer les communiqués : renseignez
  `GOV_RSS_FEEDS` dans `.env` avec les flux choisis sur la page « Flux RSS »
  des communiqués d'admin.ch ou sur https://www.abo.news.admin.ch/ (au
  minimum le flux du Conseil fédéral).
- **Sync hebdo des élus** (`scraper/sync_members.py`, lundi 05:00).
- **Intérêts** (`scraper/sync_interests.py`) : API Lobbywatch ou import CSV.

## Sources — À VÉRIFIER AVANT PRODUCTION

Ce code a été écrit sans accès réseau : les endpoints sont corrects sur le
principe mais **doivent être validés** :

1. **Parlement** : `https://ws.parlament.ch/odata.svc/$metadata` — vérifiez que
   les entités `MemberCouncil`, `MemberCouncilHistory`, `Transcript` et leurs
   champs (`PersonNumber`, `MeetingDate`, `IdSubject`, `Text`,
   `SpeakerFullName`, `CouncilAbbreviation`…) correspondent à ceux utilisés
   dans `scraper/parlament_client.py` et `scraper/daily_transcripts.py`.
   Test rapide :
   ```bash
   curl "https://ws.parlament.ch/odata.svc/MemberCouncil?\$filter=Language%20eq%20'FR'%20and%20Active%20eq%20true&\$top=2&\$format=json"
   ```
   Ajustez les noms de champs si besoin (ils sont regroupés en tête de chaque
   fichier). L'API est publique et gratuite ; gardez un rythme raisonnable.

2. **Lobbywatch** (VÉRIFIÉ) : interface REST officielle « dataIF »
   (spécification OpenAPI 3.0) sur `cms.lobbywatch.ch` — format
   `…/de/data/interface/v1/json/table/<table>/flat/list`. Consultez la page
   « Datenexport » de lobbywatch.ch pour la spec exacte, puis adaptez
   `LW_FIELD_MAP` dans `scraper/sync_interests.py` au schéma des champs.
   Alternative robuste : les exports hebdomadaires (mis à jour le lundi matin)
   en CSV (séparateur TABULATION), JSON, JSONL ou SQL — téléchargeables et
   importables. Plus de 48 000 liens d'intérêts vérifiés depuis 2014.
   Licence : données libres et gratuites avec règles d'usage (mémento sur leur
   site, attribution obligatoire) — à lire impérativement avant toute
   utilisation commerciale des données Lobbywatch ; les alertes B2B de
   Politrace reposent sur les résumés parlementaires (source officielle), pas
   sur les données Lobbywatch, ce qui sépare proprement les deux régimes.

3. **Autres personnalités publiques** : le modèle couvre désormais toute
   fonction (`role_type` : parlementaire fédéral, conseiller fédéral, juge
   fédéral, exécutif/parlement cantonal). Import par CSV :
   ```bash
   venv/bin/python -m scraper.import_people data/csv/exemple_juges_federaux.csv
   ```
   Sources : bger.ch pour les juges fédéraux (élus par l'Assemblée fédérale,
   affiliation partisane publique — voir en-tête de `scraper/import_people.py`
   pour le format), admin.ch pour le Conseil fédéral, sites cantonaux pour le
   reste. Leurs liens d'intérêts s'importent avec le même `sync_interests`
   (rapprochement par nom). Le site propose un filtre par fonction.

4. **Cantons (plus tard)** : il n'existe pas d'API unifiée ; chaque canton a
   son propre système. Le modèle de données est prêt (ajoutez un champ
   un adaptateur par canton dans
   `scraper/`). Commencez par les cantons dotés d'open data (ZH, GE, BE).

## Installation sur VPS (Ubuntu/Debian)

```bash
# 1. Utilisateur + code
sudo useradd -r -m -d /opt/politrace politrace
sudo -u politrace -i
cd /opt/politrace
# copiez le contenu du projet ici (git clone ou scp)

# 2. Environnement Python
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env   # clé Anthropic, domaine, etc.
mkdir -p data/raw data/ig_out data/csv

# 3. Premier remplissage
venv/bin/python -m scraper.sync_members            # ~250 élus + parcours
venv/bin/python -m scraper.sync_interests data/csv/interets.csv   # ou API
venv/bin/python -m scraper.daily_transcripts 2026-03-04   # un jour de session passé, pour tester
venv/bin/python -m scripts.create_admin vous@domaine.ch    # compte administrateur

# (ou, pour voir le site tout de suite sans scraper :)
venv/bin/python -m scripts.seed_demo

# 4. Test local
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# → http://IP-DU-VPS:8000/fr/

# 5. Services systemd (en root)
exit
sudo cp /opt/politrace/deploy/politrace*.service /opt/politrace/deploy/politrace*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now politrace.service politrace-daily.timer politrace-members.timer

# 6. HTTPS avec Caddy
sudo apt install caddy
sudo cp /opt/politrace/deploy/Caddyfile /etc/caddy/Caddyfile   # éditez le domaine
sudo systemctl reload caddy
```

Journal du pipeline : `journalctl -u politrace-daily.service -f`.

## Installation avec Docker

Un conteneur par tâche : `caddy` (HTTPS/reverse proxy), `web` (app FastAPI),
`scheduler` (pipeline quotidien + sync hebdo, remplace les timers systemd) et
`db` (Postgres).

```bash
cp .env.example .env && nano .env   # clé Anthropic, POSTGRES_PASSWORD, DOMAIN...

docker compose up -d --build
# → http://localhost/fr/ (ou https://$DOMAIN/fr/ si DOMAIN est un vrai domaine)

# Premier remplissage / administration (dans le conteneur web)
docker compose exec web python -m scraper.sync_members
docker compose exec web python -m scripts.create_admin vous@domaine.ch
docker compose exec web python -m scripts.seed_demo   # ou : données de démo

docker compose logs -f scheduler   # suivre le pipeline quotidien/hebdo
```

Les données persistantes (Postgres, transcriptions brutes, visuels Instagram,
certificats Caddy) vivent dans des volumes Docker nommés (`db_data`,
`app_data`, `caddy_data`, `caddy_config`) et survivent aux `docker compose
down` (sans `-v`).

## Coût des résumés (API Claude)

Un jour de session ≈ 20–40 débats. Avec `claude-sonnet-4-6` et ~15k tokens
d'entrée par débat, comptez grossièrement quelques francs par jour de session,
soit un budget modeste à l'année (≈ 60 jours de session). Le champ
`MAX_INPUT_CHARS` dans `summarizer.py` plafonne le coût. Vérifiez les tarifs
actuels sur https://docs.claude.com.

## Comptes, panel admin et alertes par mots-clés

- **Comptes** : inscription libre sur `/fr/inscription` (sessions par cookie
  signé, mots de passe PBKDF2). Définissez `SECRET_KEY` dans `.env` (sinon les
  sessions sautent à chaque redémarrage).
- **Admin** : créez le premier admin avec
  `python -m scripts.create_admin vous@domaine.ch`. Le panel `/fr/admin`
  offre : recherche par mots-clés dans les résumés (6 derniers mois,
  12 derniers mois, ou toute la base — recherche AND, insensible à la casse,
  sur titre/corps/enjeux/issue), gestion des utilisateurs
  (promouvoir/rétrograder/supprimer) et vue de toutes les alertes.
- **Alertes** : chaque utilisateur définit ses mots-clés (séparés par des
  virgules) et une langue sur `/fr/alertes`. En fin de pipeline quotidien,
  un e-mail est envoyé pour chaque alerte dont un mot-clé apparaît dans un
  résumé du jour. Configurez `SMTP_*` dans `.env` ; sans SMTP, les alertes
  s'affichent en console (dry-run) — pratique pour tester. C'est la brique
  de base de l'offre de veille B2B : il suffit d'y ajouter la facturation.

5. **Communiqués fédéraux (News Service Bund)** : flux RSS officiels sur
   `https://www.news.admin.ch/NSBSubscriber/feeds/rss?lang=fr&topic=&kind=M&org-nr=NNN`
   (variante constatée fonctionnelle : `d-nsbc-p.admin.ch`, même chemin).
   La correspondance org-nr → organisation n'étant pas documentée, identifiez
   vos numéros avec `python -m scraper.gov_news discover 1-30 101 201 301 401 1101`
   (affiche le nom de chaque canal), puis remplissez `GOV_RSS_FEEDS` dans
   `.env` au format `ABBR|url` (le badge ABBR s'affiche sur le site).
   Organisations recommandées — priorité 1 : Conseil fédéral, Chancellerie,
   DFAE, DFI, DFJP, DDPS, DFF, DEFR, DETEC ; priorité 2 (alertes B2B
   sectorielles) : OFSP, SECO, OFEV, OFEN, AFC. Les communiqués paraissent
   toute l'année et alimentent le site, les alertes et Instagram entre les
   sessions parlementaires. Les communiqués des commissions parlementaires
   passent par parlament.ch (extension future).

## Backend des résumés : API ou abonnement Pro/Max

Deux options via `SUMMARIZER_BACKEND` dans `.env` :

- **`api`** (défaut, recommandé) : SDK Anthropic + `ANTHROPIC_API_KEY`,
  facturation à l'usage. Fiable, sans limite de fenêtre, adapté à un service
  automatisé. Pour réduire les coûts ~4x, passez `CLAUDE_MODEL=claude-haiku-4-5`.
- **`claude_cli`** : utilise Claude Code (`claude -p`) connecté à votre
  abonnement Pro/Max (`claude login`, sans ANTHROPIC_API_KEY dans
  l'environnement — le script la filtre par sécurité). Le quota consommé est
  celui de l'abonnement. Limites à connaître : fenêtres de 5 h + plafond
  hebdomadaire partagés avec votre usage personnel de Claude ; un jour de
  session = 20-40 appels volumineux qui peuvent épuiser une fenêtre, et le
  cron peut tomber sur une limite atteinte. L'abonnement est pensé pour un
  usage personnel/interactif : pour un service en production destiné à des
  tiers (alertes B2B payantes), utilisez l'API. Un abonnement ne donne PAS
  de crédits API — ce mode passe par l'outil Claude Code, pas par l'API.

## Instagram et Facebook

À chaque jour avec du contenu, le pipeline dépose dans `data/ig_out/AAAA-MM-JJ/`
un carrousel (couverture + 1 carte/sujet, max 10) et `caption.txt`, et crée un
brouillon dans la section **Publications** du panel admin.

**Workflow de validation (recommandé)** : le panel admin (`/fr/admin`) affiche
chaque brouillon avec aperçu des cartes, légende éditable, statut par réseau
(IG ✓ / FB ✓) et cases à cocher — un clic sur « Publier maintenant » envoie le
carrousel sur Instagram et/ou la Page Facebook. Les erreurs de l'API Meta
s'affichent directement sous le post.

**Connexion des comptes** : section « Connexion Instagram / Facebook » du
panel admin. Il faut : une Page Facebook, un compte Instagram professionnel
lié à cette Page, une app Meta (developers.facebook.com) avec les permissions
`instagram_content_publish`, `pages_manage_posts` et `pages_read_engagement`,
puis un **token de Page longue durée**. Renseignez le token, l'IG User ID et
le Page ID dans le panel (prioritaires sur `.env` : `META_ACCESS_TOKEN`,
`IG_USER_ID`, `FB_PAGE_ID`), et validez avec « Tester la connexion » qui
affiche les noms des comptes liés. ⚠️ Le token donne le contrôle de vos pages :
il est stocké dans la base — protégez le VPS et la base en conséquence.

Les images doivent être accessibles publiquement (l'API Meta les télécharge) :
le site les sert déjà sous `/media/…`, `PUBLIC_BASE_URL` doit être défini.

**CLI équivalente** : `python -m scraper.instagram.publish [AAAA-MM-JJ] [--ig] [--fb]`
(sans option : les deux réseaux ; sans date : dernier brouillon).
- Polices : déposez `Archivo-Regular.ttf` et `Archivo-Bold.ttf` (Google Fonts)
  dans `scraper/instagram/` pour des cartes assorties au site.
- **Code couleur des partis** : chaque groupe a une couleur fixe
  (`scraper/party_colors.py`), affichée sur le site (pastilles) et sur les
  cartes IG. Le résumeur identifie les groupes qui se sont exprimés dans
  chaque débat ; ils apparaissent sous le titre de la carte. Mettez le mapping
  à jour si le paysage politique change.

## Points juridiques et éditoriaux (important)

- **Données publiques** : registre des intérêts et Bulletin officiel sont
  publics ; Lobbywatch est sous licence ouverte avec attribution. Citez vos
  sources (déjà fait en pied de page et sur les fiches).
- **Exactitude** : les fiches concernent des personnes réelles. Prévoyez une
  page contact pour les demandes de rectification, et datez vos données
  (`updated_at` existe déjà).
- **Résumés IA** : le disclaimer « le Bulletin officiel fait foi » est affiché
  sous chaque résumé et dans la légende IG. Relisez les premiers résumés avant
  de publier automatiquement — le prompt impose la neutralité et l'attribution
  des positions, mais un contrôle humain initial est indispensable.
- **Neutralité** : présenter les liens d'intérêts factuellement (la loi oblige
  à les déclarer, ce n'est pas une accusation) protège le projet juridiquement
  et renforce sa crédibilité.

## Structure du projet

```
app/            site FastAPI (main.py, models.py, i18n, templates/, static/)
scraper/        parlament_client.py, sync_members.py, sync_interests.py,
                daily_transcripts.py, summarizer.py, instagram/
deploy/         unités systemd + timers + Caddyfile (VPS sans Docker)
deploy/docker/  Caddyfile pour le conteneur `caddy` (Docker)
scripts/        seed_demo.py, create_admin.py, scheduler.py (timers en boucle Python)
data/           base SQLite (hors Docker), textes bruts archivés, sorties Instagram, CSV
Dockerfile, docker-compose.yml   image app (web + scheduler), Postgres, Caddy
```

## Feuille de route suggérée

1. Valider les endpoints (§Sources), lancer les syncs, tester sur un jour de
   session passé.
2. Mettre en ligne, relire manuellement les premiers résumés.
3. Brancher Lobbywatch (API ou CSV) et enrichir les fiches.
4. Activer la publication Instagram automatique.
5. Étendre aux cantons (un adaptateur par canton, en commençant par l'open data).
```
