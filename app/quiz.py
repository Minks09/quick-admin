"""Quiz « quel·le élu·e vous ressemble ? » — 36 affirmations sur 6 axes
inspirés du smartspider de smartvote.ch (l'application d'aide au vote de
référence en Suisse), notées de 1 (pas d'accord) à 5 (d'accord). Le résultat
rapproche le profil obtenu :
- du parti (et d'un·e élu·e de ce parti dans notre base, à titre d'exemple) ;
- du canton dont le vote réel se rapproche le plus.

Sources :
- Profils cantonaux : calculés à partir des résultats OFFICIELS et RÉELS du
  Conseil national 2023 par canton et par parti (force du parti en %),
  données ouvertes de la Confédération (OFS / Chancellerie fédérale,
  élections.admin.ch) — moyenne des positions de partis ci-dessous,
  pondérée par leur score réel dans chaque canton.
  https://opendata.swiss/fr/dataset/eidg-wahlen-2023
  https://www.bfs.admin.ch/bfs/fr/home/statistiques/politique/elections/elections-federales/2023.html
- Positions des partis sur les 6 axes : estimations informées, calibrées sur
  les axes et l'auto-présentation des partis publiés par smartvote.ch
  (méthodologie « smartspider », voir https://www.smartvote.ch/fr/smartspider)
  et sur les classifications idéologiques documentées par Wikipédia
  (« Liste des partis politiques en Suisse ») — ce ne sont PAS les valeurs
  numériques exactes du smartspider officiel (non publiées en libre accès
  sous forme agrégée), d'où le disclaimer affiché sur la page de résultat.
"""
import random

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Politician

router = APIRouter()

AXES = ["eco", "societe", "secu", "migration", "exterieure", "ecologie"]

# Chaque question porte sur un axe ; direction=+1 signifie qu'être d'accord
# pousse l'axe vers +1 (marché/conservateur/sécuritaire/migration restrictive/
# souverainiste/priorité à la croissance), direction=-1 vers -1 (état/
# progressiste/libertés civiles/migration ouverte/ouverture internationale/
# priorité à l'écologie).
QUESTIONS = [
    {"id": "q1", "axis": "eco", "direction": -1, "text": {
        "fr": "L'État devrait redistribuer davantage les richesses, quitte à augmenter les impôts des hauts revenus.",
        "de": "Der Staat sollte den Wohlstand stärker umverteilen, auch wenn dafür die Steuern für hohe Einkommen steigen.",
        "it": "Lo Stato dovrebbe ridistribuire maggiormente la ricchezza, anche a costo di aumentare le imposte sui redditi alti."}},
    {"id": "q2", "axis": "eco", "direction": 1, "text": {
        "fr": "Les entreprises doivent pouvoir agir avec le moins de régulation possible de l'État.",
        "de": "Unternehmen sollten mit möglichst wenig staatlicher Regulierung handeln können.",
        "it": "Le imprese devono poter operare con il minor numero possibile di regolamentazioni statali."}},
    {"id": "q3", "axis": "eco", "direction": -1, "text": {
        "fr": "Les services publics (santé, transports, énergie) devraient rester majoritairement en mains publiques.",
        "de": "Öffentliche Dienstleistungen (Gesundheit, Verkehr, Energie) sollten mehrheitlich in öffentlicher Hand bleiben.",
        "it": "I servizi pubblici (sanità, trasporti, energia) dovrebbero restare prevalentemente in mano pubblica."}},
    {"id": "q4", "axis": "eco", "direction": 1, "text": {
        "fr": "Les impôts devraient être abaissés, même si cela réduit les prestations de l'État.",
        "de": "Die Steuern sollten gesenkt werden, auch wenn dies die staatlichen Leistungen verringert.",
        "it": "Le imposte dovrebbero essere ridotte, anche se ciò riduce le prestazioni statali."}},
    {"id": "q5", "axis": "eco", "direction": -1, "text": {
        "fr": "L'assurance-maladie de base devrait être financée par une caisse publique unique plutôt que par des caisses privées en concurrence.",
        "de": "Die Grundversicherung sollte über eine öffentliche Einheitskasse statt über konkurrierende private Krankenkassen finanziert werden.",
        "it": "L'assicurazione malattia di base dovrebbe essere finanziata da una cassa pubblica unica invece che da casse private in concorrenza."}},
    {"id": "q6", "axis": "eco", "direction": 1, "text": {
        "fr": "L'âge de la retraite devrait pouvoir être relevé pour garantir le financement de l'AVS.",
        "de": "Das Rentenalter sollte angehoben werden können, um die Finanzierung der AHV zu sichern.",
        "it": "L'età di pensionamento dovrebbe poter essere innalzata per garantire il finanziamento dell'AVS."}},

    {"id": "q7", "axis": "societe", "direction": -1, "text": {
        "fr": "Le mariage et l'adoption doivent être ouverts à tous les couples, quel que soit leur genre.",
        "de": "Ehe und Adoption sollten für alle Paare offenstehen, unabhängig von ihrem Geschlecht.",
        "it": "Il matrimonio e l'adozione devono essere aperti a tutte le coppie, indipendentemente dal genere."}},
    {"id": "q8", "axis": "societe", "direction": 1, "text": {
        "fr": "Les valeurs et traditions familiales classiques doivent être préservées face aux évolutions de la société.",
        "de": "Klassische Familienwerte und Traditionen sollten trotz gesellschaftlichem Wandel bewahrt werden.",
        "it": "I valori e le tradizioni familiari classiche vanno preservati di fronte ai cambiamenti della società."}},
    {"id": "q9", "axis": "societe", "direction": -1, "text": {
        "fr": "La consommation de cannabis devrait être légalisée pour les adultes.",
        "de": "Der Konsum von Cannabis sollte für Erwachsene legalisiert werden.",
        "it": "Il consumo di cannabis dovrebbe essere legalizzato per gli adulti."}},
    {"id": "q10", "axis": "societe", "direction": 1, "text": {
        "fr": "L'école devrait davantage transmettre les valeurs et repères traditionnels.",
        "de": "Die Schule sollte traditionelle Werte und Orientierung stärker vermitteln.",
        "it": "La scuola dovrebbe trasmettere maggiormente i valori e i punti di riferimento tradizionali."}},
    {"id": "q11", "axis": "societe", "direction": -1, "text": {
        "fr": "Le droit à l'avortement doit rester pleinement garanti, sans restriction supplémentaire.",
        "de": "Das Recht auf Abtreibung muss uneingeschränkt gewährleistet bleiben, ohne weitere Einschränkungen.",
        "it": "Il diritto all'aborto deve restare pienamente garantito, senza ulteriori restrizioni."}},
    {"id": "q12", "axis": "societe", "direction": 1, "text": {
        "fr": "La religion et les traditions religieuses doivent garder une place importante dans la vie publique.",
        "de": "Religion und religiöse Traditionen sollten im öffentlichen Leben einen wichtigen Platz behalten.",
        "it": "La religione e le tradizioni religiose devono mantenere un posto importante nella vita pubblica."}},

    {"id": "q13", "axis": "secu", "direction": 1, "text": {
        "fr": "La police devrait disposer de plus de moyens et de compétences pour assurer la sécurité publique.",
        "de": "Die Polizei sollte mehr Mittel und Befugnisse erhalten, um die öffentliche Sicherheit zu gewährleisten.",
        "it": "La polizia dovrebbe disporre di più mezzi e competenze per garantire la sicurezza pubblica."}},
    {"id": "q14", "axis": "secu", "direction": -1, "text": {
        "fr": "La surveillance électronique des citoyens (caméras, données) doit rester strictement limitée, même au prix d'une sécurité un peu moindre.",
        "de": "Die elektronische Überwachung der Bürger (Kameras, Daten) muss strikt begrenzt bleiben, auch auf Kosten etwas geringerer Sicherheit.",
        "it": "La sorveglianza elettronica dei cittadini (telecamere, dati) deve restare rigorosamente limitata, anche a costo di una sicurezza leggermente inferiore."}},
    {"id": "q15", "axis": "secu", "direction": 1, "text": {
        "fr": "Les peines pour les délits graves devraient être plus sévères.",
        "de": "Die Strafen für schwere Delikte sollten härter ausfallen.",
        "it": "Le pene per i reati gravi dovrebbero essere più severe."}},
    {"id": "q16", "axis": "secu", "direction": -1, "text": {
        "fr": "La réinsertion doit primer sur la punition dans la politique pénale.",
        "de": "Die Wiedereingliederung sollte in der Strafpolitik Vorrang vor der Bestrafung haben.",
        "it": "Il reinserimento deve avere la priorità sulla punizione nella politica penale."}},
    {"id": "q17", "axis": "secu", "direction": 1, "text": {
        "fr": "L'armée suisse doit rester forte et le service militaire obligatoire maintenu.",
        "de": "Die Schweizer Armee muss stark bleiben und die Wehrpflicht beibehalten werden.",
        "it": "L'esercito svizzero deve restare forte e il servizio militare obbligatorio mantenuto."}},
    {"id": "q18", "axis": "secu", "direction": -1, "text": {
        "fr": "Les libertés individuelles doivent primer sur les mesures de contrôle, même en cas de crise (sanitaire, sécuritaire).",
        "de": "Individuelle Freiheiten müssen Vorrang vor Kontrollmassnahmen haben, auch in Krisenzeiten (Gesundheit, Sicherheit).",
        "it": "Le libertà individuali devono avere la priorità sulle misure di controllo, anche in tempo di crisi (sanitaria, sicuritaria)."}},

    {"id": "q19", "axis": "migration", "direction": 1, "text": {
        "fr": "La Suisse doit limiter l'immigration pour préserver ses ressources et son identité.",
        "de": "Die Schweiz muss die Einwanderung begrenzen, um ihre Ressourcen und Identität zu bewahren.",
        "it": "La Svizzera deve limitare l'immigrazione per preservare le proprie risorse e la propria identità."}},
    {"id": "q20", "axis": "migration", "direction": -1, "text": {
        "fr": "Les personnes sans papiers vivant et travaillant en Suisse depuis longtemps devraient pouvoir régulariser leur situation.",
        "de": "Personen ohne Papiere, die seit langem in der Schweiz leben und arbeiten, sollten ihren Status regularisieren können.",
        "it": "Le persone senza documenti che vivono e lavorano in Svizzera da lungo tempo dovrebbero poter regolarizzare la propria situazione."}},
    {"id": "q21", "axis": "migration", "direction": 1, "text": {
        "fr": "Les critères pour obtenir la nationalité suisse devraient être plus stricts.",
        "de": "Die Kriterien für den Erwerb des Schweizer Bürgerrechts sollten strenger werden.",
        "it": "I criteri per ottenere la cittadinanza svizzera dovrebbero essere più severi."}},
    {"id": "q22", "axis": "migration", "direction": -1, "text": {
        "fr": "L'accès à l'asile doit rester un droit garanti pour toute personne persécutée, sans le durcir davantage.",
        "de": "Der Zugang zum Asylverfahren muss für alle Verfolgten ein garantiertes Recht bleiben, ohne weitere Verschärfung.",
        "it": "L'accesso all'asilo deve restare un diritto garantito per ogni persona perseguitata, senza ulteriori inasprimenti."}},
    {"id": "q23", "axis": "migration", "direction": 1, "text": {
        "fr": "Les étrangers ayant commis un crime grave doivent systématiquement être expulsés, même s'ils vivent en Suisse depuis l'enfance.",
        "de": "Ausländische Personen, die ein schweres Verbrechen begangen haben, müssen systematisch ausgewiesen werden, auch wenn sie seit ihrer Kindheit in der Schweiz leben.",
        "it": "Gli stranieri che hanno commesso un reato grave devono essere sistematicamente espulsi, anche se vivono in Svizzera fin dall'infanzia."}},
    {"id": "q24", "axis": "migration", "direction": -1, "text": {
        "fr": "La main-d'œuvre étrangère est nécessaire et bénéfique à l'économie suisse.",
        "de": "Ausländische Arbeitskräfte sind für die Schweizer Wirtschaft notwendig und von Vorteil.",
        "it": "La manodopera straniera è necessaria e vantaggiosa per l'economia svizzera."}},

    {"id": "q25", "axis": "exterieure", "direction": -1, "text": {
        "fr": "La Suisse devrait se rapprocher davantage de l'Union européenne.",
        "de": "Die Schweiz sollte sich stärker der Europäischen Union annähern.",
        "it": "La Svizzera dovrebbe avvicinarsi maggiormente all'Unione europea."}},
    {"id": "q26", "axis": "exterieure", "direction": 1, "text": {
        "fr": "La neutralité et l'indépendance de la Suisse doivent primer sur toute intégration internationale.",
        "de": "Neutralität und Unabhängigkeit der Schweiz müssen Vorrang vor jeder internationalen Integration haben.",
        "it": "La neutralità e l'indipendenza della Svizzera devono prevalere su qualsiasi integrazione internazionale."}},
    {"id": "q27", "axis": "exterieure", "direction": -1, "text": {
        "fr": "La Suisse devrait participer davantage aux sanctions internationales et à la diplomatie multilatérale.",
        "de": "Die Schweiz sollte sich stärker an internationalen Sanktionen und der multilateralen Diplomatie beteiligen.",
        "it": "La Svizzera dovrebbe partecipare maggiormente alle sanzioni internazionali e alla diplomazia multilaterale."}},
    {"id": "q28", "axis": "exterieure", "direction": 1, "text": {
        "fr": "Les accords internationaux ne doivent jamais l'emporter sur le droit suisse et la volonté populaire.",
        "de": "Internationale Abkommen dürfen niemals über dem Schweizer Recht und dem Volkswillen stehen.",
        "it": "Gli accordi internazionali non devono mai prevalere sul diritto svizzero e sulla volontà popolare."}},
    {"id": "q29", "axis": "exterieure", "direction": -1, "text": {
        "fr": "La Suisse devrait faciliter les échanges commerciaux et la libre circulation avec ses voisins européens.",
        "de": "Die Schweiz sollte den Handel und die Freizügigkeit mit ihren europäischen Nachbarn erleichtern.",
        "it": "La Svizzera dovrebbe facilitare gli scambi commerciali e la libera circolazione con i suoi vicini europei."}},
    {"id": "q30", "axis": "exterieure", "direction": 1, "text": {
        "fr": "La Suisse doit d'abord défendre ses propres intérêts avant de s'engager dans des causes internationales.",
        "de": "Die Schweiz muss zuerst ihre eigenen Interessen verteidigen, bevor sie sich international engagiert.",
        "it": "La Svizzera deve prima difendere i propri interessi prima di impegnarsi in cause internazionali."}},

    {"id": "q31", "axis": "ecologie", "direction": -1, "text": {
        "fr": "La lutte contre le changement climatique doit primer, même si cela coûte cher à l'économie.",
        "de": "Der Kampf gegen den Klimawandel muss Vorrang haben, auch wenn es die Wirtschaft viel kostet.",
        "it": "La lotta al cambiamento climatico deve avere la priorità, anche se costa caro all'economia."}},
    {"id": "q32", "axis": "ecologie", "direction": 1, "text": {
        "fr": "Il ne faut pas freiner la croissance économique au nom de l'écologie.",
        "de": "Das Wirtschaftswachstum darf nicht im Namen der Ökologie gebremst werden.",
        "it": "Non bisogna frenare la crescita economica in nome dell'ecologia."}},
    {"id": "q33", "axis": "ecologie", "direction": -1, "text": {
        "fr": "Il faut investir massivement dans les transports publics et les énergies renouvelables, quitte à limiter l'usage de la voiture.",
        "de": "Es braucht massive Investitionen in öffentlichen Verkehr und erneuerbare Energien, auch wenn dies die Autonutzung einschränkt.",
        "it": "Bisogna investire massicciamente nei trasporti pubblici e nelle energie rinnovabili, anche a costo di limitare l'uso dell'auto."}},
    {"id": "q34", "axis": "ecologie", "direction": 1, "text": {
        "fr": "Le nucléaire doit rester une option pour garantir l'approvisionnement énergétique de la Suisse.",
        "de": "Die Kernenergie muss eine Option bleiben, um die Energieversorgung der Schweiz zu sichern.",
        "it": "Il nucleare deve restare un'opzione per garantire l'approvvigionamento energetico della Svizzera."}},
    {"id": "q35", "axis": "ecologie", "direction": -1, "text": {
        "fr": "Les taxes incitatives (carburants, énergie) sont un outil efficace et légitime pour réduire l'impact environnemental.",
        "de": "Lenkungsabgaben (auf Treibstoffe, Energie) sind ein wirksames und legitimes Mittel, um die Umweltbelastung zu senken.",
        "it": "Le tasse incentivanti (carburanti, energia) sono uno strumento efficace e legittimo per ridurre l'impatto ambientale."}},
    {"id": "q36", "axis": "ecologie", "direction": 1, "text": {
        "fr": "L'agriculture et l'industrie suisses ne doivent pas être pénalisées par des normes environnementales trop strictes.",
        "de": "Die Schweizer Landwirtschaft und Industrie dürfen nicht durch zu strenge Umweltauflagen benachteiligt werden.",
        "it": "L'agricoltura e l'industria svizzere non devono essere penalizzate da norme ambientali troppo severe."}},
]

# Profils de partis (eco, societe, secu, migration, exterieure, ecologie), -1..1.
# Clé = identifiant canonique interne ; "abbrs" liste les valeurs de
# Politician.party_abbr qui s'y rattachent (cf. scraper/party_colors.py).
# Voir le disclaimer en tête de fichier sur la source de ces positions.
PARTY_PROFILES = {
    "udc": {"abbrs": ["UDC", "SVP"],
            "axes": {"eco": 0.5, "societe": 0.8, "secu": 0.8, "migration": 1.0, "exterieure": 1.0, "ecologie": 0.7}},
    "ps": {"abbrs": ["PS", "SP", "PSS"],
           "axes": {"eco": -0.9, "societe": -0.7, "secu": -0.6, "migration": -0.7, "exterieure": -0.6, "ecologie": -0.7}},
    "plr": {"abbrs": ["PLR", "FDP"],
            "axes": {"eco": 0.9, "societe": -0.1, "secu": 0.3, "migration": 0.2, "exterieure": -0.3, "ecologie": 0.2}},
    "centre": {"abbrs": ["Centre", "Mitte", "M-E", "PDC", "CVP", "PBD", "BDP"],
               "axes": {"eco": 0.1, "societe": 0.5, "secu": 0.3, "migration": 0.2, "exterieure": 0.1, "ecologie": 0.0}},
    "verts": {"abbrs": ["VERT-E-S", "Vert-e-s", "GRÜNE", "Verts", "GPS"],
              "axes": {"eco": -0.5, "societe": -0.7, "secu": -0.7, "migration": -0.7, "exterieure": -0.5, "ecologie": -1.0}},
    "pvl": {"abbrs": ["PVL", "pvl", "GLP"],
            "axes": {"eco": 0.3, "societe": -0.4, "secu": -0.2, "migration": -0.3, "exterieure": -0.4, "ecologie": -0.8}},
    "evp": {"abbrs": ["PEV", "EVP"],
            "axes": {"eco": 0.0, "societe": 0.4, "secu": 0.2, "migration": 0.1, "exterieure": -0.1, "ecologie": -0.3}},
    "edu": {"abbrs": ["EDU", "UDF"],
            "axes": {"eco": 0.2, "societe": 0.9, "secu": 0.7, "migration": 0.8, "exterieure": 0.8, "ecologie": 0.3}},
    "pdt": {"abbrs": ["PdT", "PST", "POP"],
            "axes": {"eco": -1.0, "societe": -0.6, "secu": -0.8, "migration": -0.8, "exterieure": -0.6, "ecologie": -0.6}},
    "mcg": {"abbrs": ["MCG"],
            "axes": {"eco": 0.3, "societe": 0.6, "secu": 0.7, "migration": 0.9, "exterieure": 0.9, "ecologie": 0.3}},
    "lega": {"abbrs": ["Lega"],
             "axes": {"eco": 0.3, "societe": 0.5, "secu": 0.6, "migration": 0.8, "exterieure": 0.8, "ecologie": 0.2}},
}

# Profils cantonaux (mêmes 6 axes) — moyenne des profils de partis ci-dessus,
# pondérée par la force RÉELLE de chaque parti au Conseil national 2023 dans
# le canton (données officielles OFS/Chancellerie fédérale, cf. en-tête).
CANTONS = {
    "ZH": {"fr": "Zurich", "de": "Zürich", "it": "Zurigo",
           "axes": {"eco": 0.056, "societe": 0.003, "secu": 0.076, "migration": 0.075, "exterieure": 0.027, "ecologie": -0.141}},
    "BE": {"fr": "Berne", "de": "Bern", "it": "Berna",
           "axes": {"eco": 0.03, "societe": 0.073, "secu": 0.113, "migration": 0.128, "exterieure": 0.105, "ecologie": -0.11}},
    "LU": {"fr": "Lucerne", "de": "Luzern", "it": "Lucerna",
           "axes": {"eco": 0.155, "societe": 0.157, "secu": 0.189, "migration": 0.177, "exterieure": 0.092, "ecologie": -0.019}},
    "UR": {"fr": "Uri", "de": "Uri", "it": "Uri",
           "axes": {"eco": 0.245, "societe": 0.609, "secu": 0.481, "migration": 0.489, "exterieure": 0.426, "ecologie": 0.253}},
    "SZ": {"fr": "Schwytz", "de": "Schwyz", "it": "Svitto",
           "axes": {"eco": 0.3, "societe": 0.274, "secu": 0.341, "migration": 0.362, "exterieure": 0.248, "ecologie": 0.175}},
    "OW": {"fr": "Obwald", "de": "Obwalden", "it": "Obvaldo",
           "axes": {"eco": 0.691, "societe": 0.371, "secu": 0.562, "migration": 0.619, "exterieure": 0.38, "ecologie": 0.462}},
    "NW": {"fr": "Nidwald", "de": "Nidwalden", "it": "Nidvaldo",
           "axes": {"eco": 0.378, "societe": 0.531, "secu": 0.499, "migration": 0.519, "exterieure": 0.4, "ecologie": 0.309}},
    "GL": {"fr": "Glaris", "de": "Glarus", "it": "Glarona",
           "axes": {"eco": 0.035, "societe": 0.343, "secu": 0.302, "migration": 0.334, "exterieure": 0.326, "ecologie": 0.138}},
    "ZG": {"fr": "Zoug", "de": "Zug", "it": "Zugo",
           "axes": {"eco": 0.191, "societe": 0.188, "secu": 0.207, "migration": 0.219, "exterieure": 0.157, "ecologie": -0.013}},
    "FR": {"fr": "Fribourg", "de": "Freiburg", "it": "Friburgo",
           "axes": {"eco": 0.039, "societe": 0.066, "secu": 0.105, "migration": 0.099, "exterieure": 0.05, "ecologie": -0.086}},
    "SO": {"fr": "Soleure", "de": "Solothurn", "it": "Soletta",
           "axes": {"eco": 0.137, "societe": 0.1, "secu": 0.162, "migration": 0.159, "exterieure": 0.079, "ecologie": -0.031}},
    "BS": {"fr": "Bâle-Ville", "de": "Basel-Stadt", "it": "Basilea Città",
           "axes": {"eco": -0.238, "societe": -0.27, "secu": -0.2, "migration": -0.232, "exterieure": -0.219, "ecologie": -0.417}},
    "BL": {"fr": "Bâle-Campagne", "de": "Basel-Landschaft", "it": "Basilea Campagna",
           "axes": {"eco": 0.033, "societe": 0.014, "secu": 0.084, "migration": 0.083, "exterieure": 0.033, "ecologie": -0.106}},
    "SH": {"fr": "Schaffhouse", "de": "Schaffhausen", "it": "Sciaffusa",
           "axes": {"eco": 0.063, "societe": 0.089, "secu": 0.167, "migration": 0.197, "exterieure": 0.157, "ecologie": 0.002}},
    "AR": {"fr": "Appenzell Rhodes-Extérieures", "de": "Appenzell Ausserrhoden", "it": "Appenzello Esterno",
           "axes": {"eco": 0.58, "societe": 0.428, "secu": 0.54, "migration": 0.584, "exterieure": 0.388, "ecologie": 0.408}},
    "AI": {"fr": "Appenzell Rhodes-Intérieures", "de": "Appenzell Innerrhoden", "it": "Appenzello Interno",
           "axes": {"eco": 0.111, "societe": 0.508, "secu": 0.314, "migration": 0.222, "exterieure": 0.125, "ecologie": 0.019}},
    "SG": {"fr": "Saint-Gall", "de": "St. Gallen", "it": "San Gallo",
           "axes": {"eco": 0.188, "societe": 0.203, "secu": 0.244, "migration": 0.261, "exterieure": 0.19, "ecologie": 0.048}},
    "GR": {"fr": "Grisons", "de": "Graubünden", "it": "Grigioni",
           "axes": {"eco": 0.136, "societe": 0.18, "secu": 0.213, "migration": 0.212, "exterieure": 0.14, "ecologie": 0.015}},
    "AG": {"fr": "Argovie", "de": "Aargau", "it": "Argovia",
           "axes": {"eco": 0.154, "societe": 0.159, "secu": 0.213, "migration": 0.232, "exterieure": 0.168, "ecologie": 0.013}},
    "TG": {"fr": "Thurgovie", "de": "Thurgau", "it": "Turgovia",
           "axes": {"eco": 0.21, "societe": 0.273, "secu": 0.3, "migration": 0.339, "exterieure": 0.284, "ecologie": 0.097}},
    "TI": {"fr": "Tessin", "de": "Tessin", "it": "Ticino",
           "axes": {"eco": 0.188, "societe": 0.108, "secu": 0.195, "migration": 0.2, "exterieure": 0.095, "ecologie": -0.017}},
    "VD": {"fr": "Vaud", "de": "Waadt", "it": "Vaud",
           "axes": {"eco": -0.013, "societe": -0.169, "secu": -0.058, "migration": -0.08, "exterieure": -0.145, "ecologie": -0.224}},
    "VS": {"fr": "Valais", "de": "Wallis", "it": "Vallese",
           "axes": {"eco": 0.118, "societe": 0.187, "secu": 0.191, "migration": 0.174, "exterieure": 0.096, "ecologie": -0.004}},
    "NE": {"fr": "Neuchâtel", "de": "Neuenburg", "it": "Neuchâtel",
           "axes": {"eco": -0.102, "societe": -0.23, "secu": -0.142, "migration": -0.16, "exterieure": -0.198, "ecologie": -0.285}},
    "GE": {"fr": "Genève", "de": "Genf", "it": "Ginevra",
           "axes": {"eco": 0.016, "societe": -0.059, "secu": 0.031, "migration": 0.037, "exterieure": -0.005, "ecologie": -0.187}},
    "JU": {"fr": "Jura", "de": "Jura", "it": "Giura",
           "axes": {"eco": -0.117, "societe": -0.015, "secu": -0.0, "migration": -0.031, "exterieure": -0.053, "ecologie": -0.192}},
}


def _templates():
    from .main import templates, ctx
    return templates, ctx


def _distance(a: dict, b: dict) -> float:
    return sum((a[axis] - b[axis]) ** 2 for axis in AXES) ** 0.5


def score_answers(answers: dict) -> dict:
    """answers: {question_id: 1..5} -> {axis: -1..1}."""
    totals = {axis: 0.0 for axis in AXES}
    counts = {axis: 0 for axis in AXES}
    for q in QUESTIONS:
        value = answers.get(q["id"])
        if value is None:
            continue
        centered = value - 3  # -2..2
        totals[q["axis"]] += q["direction"] * centered
        counts[q["axis"]] += 1
    return {axis: (totals[axis] / (counts[axis] * 2)) if counts[axis] else 0.0 for axis in AXES}


def closest_party(user_axes: dict) -> tuple[str, dict]:
    key = min(PARTY_PROFILES, key=lambda k: _distance(user_axes, PARTY_PROFILES[k]["axes"]))
    return key, PARTY_PROFILES[key]


def ranked_cantons(user_axes: dict) -> list[dict]:
    ranked = sorted(CANTONS.items(), key=lambda kv: _distance(user_axes, kv[1]["axes"]))
    return [{"abbr": abbr, **info} for abbr, info in ranked]


@router.get("/{lang}/quiz")
def quiz_page(request: Request, lang: str):
    templates, ctx = _templates()
    return templates.TemplateResponse("quiz.html", ctx(request, lang, questions=QUESTIONS))


@router.post("/{lang}/quiz")
async def quiz_submit(request: Request, lang: str, db: Session = Depends(get_db)):
    templates, ctx = _templates()
    form = await request.form()
    answers = {}
    for q in QUESTIONS:
        raw = form.get(q["id"])
        try:
            answers[q["id"]] = int(raw)
        except (TypeError, ValueError):
            continue
    user_axes = score_answers(answers)

    party_key, party = closest_party(user_axes)
    cantons = ranked_cantons(user_axes)
    top_canton = cantons[0]

    matches = db.execute(
        select(Politician)
        .where(Politician.active == True, Politician.party_abbr.in_(party["abbrs"]))
    ).scalars().all()
    example = None
    if matches:
        in_top_canton = [p for p in matches if p.canton_abbr == top_canton["abbr"]]
        example = random.choice(in_top_canton or matches)

    return templates.TemplateResponse("quiz_result.html", ctx(
        request, lang,
        user_axes=user_axes, party_key=party_key, party=party, example=example,
        top_canton=top_canton, other_cantons=cantons[1:3],
    ))
