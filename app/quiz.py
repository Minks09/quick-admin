"""Quiz « quel·le élu·e vous ressemble ? » — 12 affirmations sur 4 axes
(économie, société, ouverture, écologie), notées de 1 (pas d'accord) à 5
(d'accord). Le résultat rapproche le profil obtenu :
- du parti (et d'un·e élu·e de ce parti dans notre base, à titre d'exemple) ;
- du canton dont les tendances de vote générales s'en rapprochent le plus.

Les profils de partis/cantons ci-dessous sont des estimations indicatives
grossières (tendances générales de vote), pas les réponses réelles des
élu·es ni une étude scientifique — voir le disclaimer affiché sur la page
de résultat.
"""
import random

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Politician

router = APIRouter()

AXES = ["eco", "soc", "ouverture", "ecologie"]

# Chaque question porte sur un axe ; direction=+1 signifie qu'être d'accord
# pousse l'axe vers +1 (marché/conservateur/souveraineté/croissance),
# direction=-1 vers -1 (État/progressiste/ouverture/écologie).
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
    {"id": "q4", "axis": "soc", "direction": -1, "text": {
        "fr": "Le mariage et l'adoption doivent être ouverts à tous les couples, quel que soit leur genre.",
        "de": "Ehe und Adoption sollten für alle Paare offenstehen, unabhängig von ihrem Geschlecht.",
        "it": "Il matrimonio e l'adozione devono essere aperti a tutte le coppie, indipendentemente dal genere."}},
    {"id": "q5", "axis": "soc", "direction": 1, "text": {
        "fr": "Les valeurs et traditions familiales classiques doivent être préservées face aux évolutions de la société.",
        "de": "Klassische Familienwerte und Traditionen sollten trotz gesellschaftlichem Wandel bewahrt werden.",
        "it": "I valori e le tradizioni familiari classiche vanno preservati di fronte ai cambiamenti della società."}},
    {"id": "q6", "axis": "soc", "direction": -1, "text": {
        "fr": "La consommation de cannabis devrait être légalisée pour les adultes.",
        "de": "Der Konsum von Cannabis sollte für Erwachsene legalisiert werden.",
        "it": "Il consumo di cannabis dovrebbe essere legalizzato per gli adulti."}},
    {"id": "q7", "axis": "ouverture", "direction": -1, "text": {
        "fr": "La Suisse devrait se rapprocher davantage de l'Union européenne.",
        "de": "Die Schweiz sollte sich stärker der Europäischen Union annähern.",
        "it": "La Svizzera dovrebbe avvicinarsi maggiormente all'Unione europea."}},
    {"id": "q8", "axis": "ouverture", "direction": 1, "text": {
        "fr": "La Suisse doit limiter l'immigration pour préserver ses ressources et son identité.",
        "de": "Die Schweiz muss die Einwanderung begrenzen, um ihre Ressourcen und Identität zu bewahren.",
        "it": "La Svizzera deve limitare l'immigrazione per preservare le proprie risorse e la propria identità."}},
    {"id": "q9", "axis": "ouverture", "direction": 1, "text": {
        "fr": "La neutralité et l'indépendance de la Suisse doivent primer sur toute intégration internationale.",
        "de": "Neutralität und Unabhängigkeit der Schweiz müssen Vorrang vor jeder internationalen Integration haben.",
        "it": "La neutralità e l'indipendenza della Svizzera devono prevalere su qualsiasi integrazione internazionale."}},
    {"id": "q10", "axis": "ecologie", "direction": -1, "text": {
        "fr": "La lutte contre le changement climatique doit primer, même si cela coûte cher à l'économie.",
        "de": "Der Kampf gegen den Klimawandel muss Vorrang haben, auch wenn es die Wirtschaft viel kostet.",
        "it": "La lotta al cambiamento climatico deve avere la priorità, anche se costa caro all'economia."}},
    {"id": "q11", "axis": "ecologie", "direction": 1, "text": {
        "fr": "Il ne faut pas freiner la croissance économique au nom de l'écologie.",
        "de": "Das Wirtschaftswachstum darf nicht im Namen der Ökologie gebremst werden.",
        "it": "Non bisogna frenare la crescita economica in nome dell'ecologia."}},
    {"id": "q12", "axis": "ecologie", "direction": -1, "text": {
        "fr": "Il faut investir massivement dans les transports publics et les énergies renouvelables, quitte à limiter l'usage de la voiture.",
        "de": "Es braucht massive Investitionen in öffentlichen Verkehr und erneuerbare Energien, auch wenn dies die Autonutzung einschränkt.",
        "it": "Bisogna investire massicciamente nei trasporti pubblici e nelle energie rinnovabili, anche a costo di limitare l'uso dell'auto."}},
]

# Profils de partis (eco, soc, ouverture, ecologie), -1..1. Clé = identifiant
# canonique interne ; "abbrs" liste les valeurs de Politician.party_abbr qui
# s'y rattachent (cf. scraper/party_colors.py pour les mêmes alias).
PARTY_PROFILES = {
    "udc": {"abbrs": ["UDC", "SVP"], "axes": {"eco": 0.5, "soc": 0.9, "ouverture": 1.0, "ecologie": 0.7}},
    "ps": {"abbrs": ["PS", "SP", "PSS"], "axes": {"eco": -0.9, "soc": -0.7, "ouverture": -0.6, "ecologie": -0.7}},
    "plr": {"abbrs": ["PLR", "FDP"], "axes": {"eco": 0.8, "soc": -0.1, "ouverture": -0.4, "ecologie": 0.2}},
    "centre": {"abbrs": ["Centre", "Mitte", "M-E", "PDC", "CVP", "PBD", "BDP"],
               "axes": {"eco": 0.1, "soc": 0.5, "ouverture": 0.1, "ecologie": 0.0}},
    "verts": {"abbrs": ["VERT-E-S", "Vert-e-s", "GRÜNE", "Verts", "GPS"],
              "axes": {"eco": -0.5, "soc": -0.7, "ouverture": -0.5, "ecologie": -1.0}},
    "pvl": {"abbrs": ["PVL", "pvl", "GLP"], "axes": {"eco": 0.3, "soc": -0.4, "ouverture": -0.4, "ecologie": -0.8}},
    "evp": {"abbrs": ["PEV", "EVP"], "axes": {"eco": 0.0, "soc": 0.4, "ouverture": -0.1, "ecologie": -0.3}},
    "edu": {"abbrs": ["EDU", "UDF"], "axes": {"eco": 0.2, "soc": 0.9, "ouverture": 0.8, "ecologie": 0.3}},
    "pdt": {"abbrs": ["PdT", "PST", "POP"], "axes": {"eco": -1.0, "soc": -0.5, "ouverture": -0.6, "ecologie": -0.6}},
    "mcg": {"abbrs": ["MCG"], "axes": {"eco": 0.3, "soc": 0.6, "ouverture": 0.9, "ecologie": 0.3}},
    "lega": {"abbrs": ["Lega"], "axes": {"eco": 0.3, "soc": 0.5, "ouverture": 0.8, "ecologie": 0.2}},
}

# Profils cantonaux, mêmes 4 axes. Estimations grossières issues des grandes
# tendances de vote (résultats électoraux fédéraux par canton) — indicatif.
CANTONS = {
    "ZH": {"fr": "Zurich", "de": "Zürich", "it": "Zurigo", "axes": {"eco": 0.1, "soc": -0.1, "ouverture": -0.2, "ecologie": -0.1}},
    "BE": {"fr": "Berne", "de": "Bern", "it": "Berna", "axes": {"eco": 0.0, "soc": 0.0, "ouverture": 0.1, "ecologie": 0.0}},
    "LU": {"fr": "Lucerne", "de": "Luzern", "it": "Lucerna", "axes": {"eco": 0.3, "soc": 0.3, "ouverture": 0.3, "ecologie": 0.2}},
    "UR": {"fr": "Uri", "de": "Uri", "it": "Uri", "axes": {"eco": 0.4, "soc": 0.6, "ouverture": 0.6, "ecologie": 0.4}},
    "SZ": {"fr": "Schwytz", "de": "Schwyz", "it": "Svitto", "axes": {"eco": 0.6, "soc": 0.6, "ouverture": 0.7, "ecologie": 0.5}},
    "OW": {"fr": "Obwald", "de": "Obwalden", "it": "Obvaldo", "axes": {"eco": 0.6, "soc": 0.6, "ouverture": 0.6, "ecologie": 0.4}},
    "NW": {"fr": "Nidwald", "de": "Nidwalden", "it": "Nidvaldo", "axes": {"eco": 0.6, "soc": 0.5, "ouverture": 0.5, "ecologie": 0.4}},
    "GL": {"fr": "Glaris", "de": "Glarus", "it": "Glarona", "axes": {"eco": 0.1, "soc": 0.1, "ouverture": 0.1, "ecologie": 0.0}},
    "ZG": {"fr": "Zoug", "de": "Zug", "it": "Zugo", "axes": {"eco": 0.7, "soc": 0.3, "ouverture": 0.2, "ecologie": 0.3}},
    "FR": {"fr": "Fribourg", "de": "Freiburg", "it": "Friburgo", "axes": {"eco": 0.0, "soc": 0.3, "ouverture": 0.0, "ecologie": 0.0}},
    "SO": {"fr": "Soleure", "de": "Solothurn", "it": "Soletta", "axes": {"eco": 0.0, "soc": 0.0, "ouverture": 0.0, "ecologie": -0.1}},
    "BS": {"fr": "Bâle-Ville", "de": "Basel-Stadt", "it": "Basilea Città", "axes": {"eco": -0.6, "soc": -0.6, "ouverture": -0.6, "ecologie": -0.7}},
    "BL": {"fr": "Bâle-Campagne", "de": "Basel-Landschaft", "it": "Basilea Campagna", "axes": {"eco": 0.0, "soc": -0.1, "ouverture": -0.1, "ecologie": -0.1}},
    "SH": {"fr": "Schaffhouse", "de": "Schaffhausen", "it": "Sciaffusa", "axes": {"eco": 0.2, "soc": 0.2, "ouverture": 0.3, "ecologie": 0.1}},
    "AR": {"fr": "Appenzell Rhodes-Extérieures", "de": "Appenzell Ausserrhoden", "it": "Appenzello Esterno", "axes": {"eco": 0.4, "soc": 0.5, "ouverture": 0.5, "ecologie": 0.2}},
    "AI": {"fr": "Appenzell Rhodes-Intérieures", "de": "Appenzell Innerrhoden", "it": "Appenzello Interno", "axes": {"eco": 0.4, "soc": 0.8, "ouverture": 0.7, "ecologie": 0.3}},
    "SG": {"fr": "Saint-Gall", "de": "St. Gallen", "it": "San Gallo", "axes": {"eco": 0.3, "soc": 0.4, "ouverture": 0.4, "ecologie": 0.2}},
    "GR": {"fr": "Grisons", "de": "Graubünden", "it": "Grigioni", "axes": {"eco": 0.2, "soc": 0.2, "ouverture": 0.1, "ecologie": -0.1}},
    "AG": {"fr": "Argovie", "de": "Aargau", "it": "Argovia", "axes": {"eco": 0.3, "soc": 0.3, "ouverture": 0.4, "ecologie": 0.2}},
    "TG": {"fr": "Thurgovie", "de": "Thurgau", "it": "Turgovia", "axes": {"eco": 0.4, "soc": 0.4, "ouverture": 0.5, "ecologie": 0.3}},
    "TI": {"fr": "Tessin", "de": "Tessin", "it": "Ticino", "axes": {"eco": 0.2, "soc": 0.2, "ouverture": 0.4, "ecologie": 0.1}},
    "VD": {"fr": "Vaud", "de": "Waadt", "it": "Vaud", "axes": {"eco": -0.4, "soc": -0.4, "ouverture": -0.5, "ecologie": -0.5}},
    "VS": {"fr": "Valais", "de": "Wallis", "it": "Vallese", "axes": {"eco": 0.3, "soc": 0.5, "ouverture": 0.2, "ecologie": 0.1}},
    "NE": {"fr": "Neuchâtel", "de": "Neuenburg", "it": "Neuchâtel", "axes": {"eco": -0.5, "soc": -0.3, "ouverture": -0.4, "ecologie": -0.3}},
    "GE": {"fr": "Genève", "de": "Genf", "it": "Ginevra", "axes": {"eco": -0.5, "soc": -0.5, "ouverture": -0.7, "ecologie": -0.5}},
    "JU": {"fr": "Jura", "de": "Jura", "it": "Giura", "axes": {"eco": -0.3, "soc": -0.2, "ouverture": -0.3, "ecologie": -0.2}},
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
def quiz_submit(
    request: Request, lang: str,
    q1: int = Form(...), q2: int = Form(...), q3: int = Form(...), q4: int = Form(...),
    q5: int = Form(...), q6: int = Form(...), q7: int = Form(...), q8: int = Form(...),
    q9: int = Form(...), q10: int = Form(...), q11: int = Form(...), q12: int = Form(...),
    db: Session = Depends(get_db),
):
    templates, ctx = _templates()
    answers = {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5, "q6": q6,
               "q7": q7, "q8": q8, "q9": q9, "q10": q10, "q11": q11, "q12": q12}
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
