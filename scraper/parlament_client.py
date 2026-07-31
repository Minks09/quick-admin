"""Client pour l'API open data du Parlement suisse (ws.parlament.ch, OData v3).

Documentation : https://ws.parlament.ch/odata.svc/$metadata
Entités utilisées : MemberCouncil, MemberCouncilHistory, Transcript, Session.

L'API renvoie du JSON avec $format=json. Pagination via odata.nextLink / __next.
Les dates arrivent au format /Date(1699999999000)/ → converties en date Python.
"""
import os
import re
import time
from datetime import date, datetime

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = os.getenv("PARLAMENT_ODATA", "https://ws.parlament.ch/odata.svc").rstrip("/")

_DATE_RE = re.compile(r"/Date\((-?\d+)")


def parse_odata_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, str):
        m = _DATE_RE.search(value)
        if m:
            return datetime.utcfromtimestamp(int(m.group(1)) / 1000).date()
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


class ParlamentClient:
    def __init__(self, timeout=60):
        self.http = httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json",
                     "User-Agent": "Politrace/1.0 (projet transparence; contact: admin@politrace.ch)"},
        )

    def _get(self, url: str, params: dict | None = None) -> dict:
        for attempt in range(4):
            try:
                r = self.http.get(url, params=params)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return {}

    def query(self, entity: str, filter_: str | None = None, select: str | None = None,
              orderby: str | None = None, top: int | None = None):
        """Itère sur toutes les pages d'une entité OData."""
        params = {"$format": "json"}
        if filter_:
            params["$filter"] = filter_
        if select:
            params["$select"] = select
        if orderby:
            params["$orderby"] = orderby
        if top:
            params["$top"] = str(top)

        url = f"{BASE}/{entity}"
        while url:
            data = self._get(url, params)
            payload = data.get("d", data)
            results = payload.get("results", payload) if isinstance(payload, dict) else payload
            if isinstance(results, dict):
                results = [results]
            yield from results
            # pagination (OData v3 : d.__next ; v4 : @odata.nextLink)
            next_url = None
            if isinstance(payload, dict):
                next_url = payload.get("__next")
            if not next_url and isinstance(data, dict):
                next_url = data.get("@odata.nextLink") or data.get("odata.nextLink")
            url, params = (next_url, None) if next_url else (None, None)

    # ---- requêtes métier ----

    def active_members(self, lang="FR"):
        """Membres actifs des deux conseils, dans la langue demandée."""
        return self.query(
            "MemberCouncil",
            filter_=f"Language eq '{lang}' and Active eq true",
        )

    def member_history(self, person_number: int, lang="FR"):
        return self.query(
            "MemberCouncilHistory",
            filter_=f"Language eq '{lang}' and PersonNumber eq {person_number}",
        )

    def transcripts_for_day(self, day: date):
        """Toutes les retranscriptions (Bulletin officiel) d'un jour donné.

        Le champ Transcript.MeetingDate correspond au jour de séance.
        Chaque locuteur parle dans sa langue : le texte est donc multilingue.
        """
        start = f"datetime'{day.isoformat()}T00:00:00'"
        end = f"datetime'{day.isoformat()}T23:59:59'"
        return self.query(
            "Transcript",
            filter_=f"MeetingDate ge {start} and MeetingDate le {end}",
            orderby="IdSubject,SortOrder",
        )
