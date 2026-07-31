"""Résumé d'un débat parlementaire via l'API Claude, en FR/DE/IT d'un seul appel.

Sortie JSON strict :
{ "fr": {"title","body","stakes","outcome"}, "de": {...}, "it": {...} }
"""
import json
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
BACKEND = os.getenv("SUMMARIZER_BACKEND", "api")  # api | claude_cli
MAX_INPUT_CHARS = 60_000  # ~15k tokens de retranscription max par débat

SYSTEM = """Tu es un journaliste parlementaire suisse rigoureux et neutre.
On te donne la retranscription officielle (Bulletin officiel) d'un débat au
Parlement fédéral suisse. Les interventions peuvent être en français, allemand
ou italien.

Produis un résumé factuel et accessible au grand public, dans les TROIS langues
(fr, de, it), avec pour chaque langue :
- "title" : titre court et informatif (max 90 caractères)
- "body" : de quoi il s'agit et ce qui a été débattu, avec les principales
  positions des groupes/orateurs (4-7 phrases)
- "stakes" : les tenants et aboutissants — pourquoi c'est important, qui est
  concerné, quelles conséquences concrètes (2-4 phrases)
- "outcome" : l'issue de la discussion si elle ressort du texte (vote, renvoi
  en commission, prochaine étape) ; sinon "" (1-2 phrases)

Ajoute aussi, au niveau racine du JSON (hors langues), une clé "groups" :
la liste des abréviations des partis/groupes qui se sont exprimés ou dont la
position ressort du texte (ex. ["UDC","PS","PLR","Centre","VERT-E-S","PVL"]).
Uniquement ceux réellement présents dans la retranscription.

Règles strictes :
- Uniquement des faits présents dans la retranscription. N'invente rien.
- Ton neutre, aucun jugement de valeur, pas d'adjectifs militants.
- Attribue les positions aux groupes ou orateurs nommés dans le texte.
- Réponds UNIQUEMENT avec un objet JSON valide, sans balises Markdown,
  sans texte avant ou après."""

_client = None


def _call_api(system: str, prompt: str) -> str:
    """Backend API (clé ANTHROPIC_API_KEY, facturation à l'usage)."""
    global _client
    if _client is None:
        import anthropic  # import paresseux : inutile en mode claude_cli
        _client = anthropic.Anthropic()
    resp = _client.messages.create(
        model=MODEL, max_tokens=3000, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def _call_claude_cli(system: str, prompt: str) -> str:
    """Backend Claude Code (`claude -p`, quota de l'abonnement Pro/Max).

    Prérequis sur la machine : Claude Code installé et connecté au compte
    abonné (`claude login`), SANS variable ANTHROPIC_API_KEY dans
    l'environnement (sinon Claude Code basculerait sur la facturation API).
    Attention aux limites de l'abonnement (fenêtres de 5 h + plafond
    hebdomadaire) : un jour de session = 20-40 appels volumineux.
    """
    result = subprocess.run(
        ["claude", "-p", f"{system}\n\n{prompt}", "--output-format", "text"],
        capture_output=True, text=True, timeout=600,
        env={k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI: {result.stderr.strip()[:300]}")
    return result.stdout

SYSTEM_COMMUNIQUE = """Tu es un journaliste politique suisse rigoureux et neutre.
On te donne un communiqué officiel de la Confédération (Conseil fédéral,
département ou office fédéral).

Produis un résumé factuel et accessible au grand public, dans les TROIS langues
(fr, de, it), avec pour chaque langue :
- "title" : titre court et informatif (max 90 caractères)
- "body" : de quoi il s'agit — la décision ou l'annonce, son contexte (3-5 phrases)
- "stakes" : les tenants et aboutissants — pourquoi c'est important, qui est
  concerné, quelles conséquences concrètes (2-4 phrases)
- "outcome" : la suite concrète si elle est mentionnée (entrée en vigueur,
  consultation, délais, prochaine étape) ; sinon "" (1-2 phrases)

Ajoute aussi, au niveau racine du JSON, "groups" : [] (liste vide, sauf si des
partis politiques sont explicitement cités dans le communiqué).

Règles strictes :
- Uniquement des faits présents dans le communiqué. N'invente rien.
- Ton neutre, aucun jugement de valeur.
- Réponds UNIQUEMENT avec un objet JSON valide, sans balises Markdown,
  sans texte avant ou après."""


def _call_and_parse(system: str, prompt: str) -> dict | None:
    if BACKEND == "claude_cli":
        raw = _call_claude_cli(system, prompt).strip()
    else:
        raw = _call_api(system, prompt).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not all(k in data for k in ("fr", "de", "it")):
        return None
    return data


def summarize_communique(title: str, sender: str, day: str, text: str) -> dict | None:
    prompt = (f"Titre : {title or 'Sans titre'}\n"
              f"Expéditeur : {sender or 'Confédération'}\nDate : {day}\n\n"
              f"Communiqué :\n{text[:MAX_INPUT_CHARS]}")
    return _call_and_parse(SYSTEM_COMMUNIQUE, prompt)


def summarize_debate(title: str, council: str, day: str, transcript_text: str) -> dict | None:
    text = transcript_text[:MAX_INPUT_CHARS]
    prompt = (f"Objet : {title or 'Sans titre'}\n"
              f"Conseil : {council}\nDate : {day}\n\n"
              f"Retranscription :\n{text}")
    return _call_and_parse(SYSTEM, prompt)
