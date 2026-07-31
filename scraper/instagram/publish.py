"""Publication sur Instagram et Facebook via l'API Meta Graph.

Identifiants : lus en priorité dans la table `settings` (renseignés depuis le
panel admin), sinon dans .env (IG_ACCESS_TOKEN/META_ACCESS_TOKEN, IG_USER_ID,
FB_PAGE_ID).

Prérequis Meta (voir README §Instagram/Facebook) :
- Page Facebook + compte Instagram PROFESSIONNEL lié à cette Page
- App Meta avec permissions instagram_content_publish, pages_manage_posts,
  pages_read_engagement — token de Page longue durée
- Images accessibles publiquement : PUBLIC_BASE_URL doit servir data/ig_out/
  (le site les expose sous /media/)

Usage CLI :  python -m scraper.instagram.publish 2026-03-04 [--ig] [--fb]
Sans option réseau : publie sur les deux. Sans date : dernier brouillon.
Le panel admin appelle les mêmes fonctions publish_instagram / publish_facebook.
"""
import json
import os
import sys
import time
from datetime import date, datetime

sys.path.insert(0, ".")

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import IGPost, Setting  # noqa: E402

load_dotenv()
GRAPH = "https://graph.facebook.com/v21.0"
BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def get_credentials(db=None) -> dict:
    """settings (admin) > variables d'environnement."""
    creds = {
        "access_token": os.getenv("META_ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN", ""),
        "ig_user_id": os.getenv("IG_USER_ID", ""),
        "fb_page_id": os.getenv("FB_PAGE_ID", ""),
    }
    close = False
    if db is None:
        db, close = SessionLocal(), True
    for key in list(creds):
        row = db.get(Setting, f"meta_{key}")
        if row and (row.value or "").strip():
            creds[key] = row.value.strip()
    if close:
        db.close()
    return creds


def api(method: str, path: str, token: str, **params) -> dict:
    params["access_token"] = token
    r = httpx.request(method, f"{GRAPH}/{path}", params=params, timeout=120)
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data)))
    return data


def public_url(local_path: str) -> str:
    # data/ig_out/2026-03-04/00_cover.png -> https://domaine/media/2026-03-04/00_cover.png
    rel = local_path.split("ig_out/", 1)[-1]
    return f"{BASE_URL}/media/{rel}"


def check_connection(creds: dict) -> dict:
    """Vérifie le token et renvoie les noms des comptes liés (pour le panel admin)."""
    out = {}
    if creds.get("fb_page_id"):
        page = api("GET", creds["fb_page_id"], creds["access_token"], fields="name")
        out["facebook_page"] = page.get("name", "?")
    if creds.get("ig_user_id"):
        ig = api("GET", creds["ig_user_id"], creds["access_token"], fields="username")
        out["instagram"] = "@" + ig.get("username", "?")
    return out


def _require(creds: dict, *keys):
    missing = [k for k in ("access_token", *keys) if not creds.get(k)]
    if missing:
        raise RuntimeError(f"Identifiants Meta manquants : {', '.join(missing)}")
    if not BASE_URL:
        raise RuntimeError("PUBLIC_BASE_URL manquant dans .env (les images doivent "
                           "être accessibles publiquement).")


def publish_instagram(post: IGPost, creds: dict):
    """Publie le carrousel du jour sur Instagram."""
    _require(creds, "ig_user_id")
    token, ig = creds["access_token"], creds["ig_user_id"]
    paths = [p for p in (post.image_paths or "").split("|") if p]
    if not paths:
        raise RuntimeError("Aucune image pour ce post.")

    children = []
    for p in paths:
        c = api("POST", f"{ig}/media", token,
                image_url=public_url(p), is_carousel_item="true")
        children.append(c["id"])
        time.sleep(1)

    carousel = api("POST", f"{ig}/media", token, media_type="CAROUSEL",
                   children=",".join(children), caption=post.caption or "")
    for _ in range(20):
        status = api("GET", carousel["id"], token, fields="status_code")
        if status.get("status_code") == "FINISHED":
            break
        time.sleep(3)
    api("POST", f"{ig}/media_publish", token, creation_id=carousel["id"])


def publish_facebook(post: IGPost, creds: dict):
    """Publie les mêmes visuels + légende sur la Page Facebook."""
    _require(creds, "fb_page_id")
    token, page = creds["access_token"], creds["fb_page_id"]
    paths = [p for p in (post.image_paths or "").split("|") if p]
    if not paths:
        raise RuntimeError("Aucune image pour ce post.")

    media_ids = []
    for p in paths:
        r = api("POST", f"{page}/photos", token,
                url=public_url(p), published="false")
        media_ids.append(r["id"])
        time.sleep(1)

    params = {"message": post.caption or ""}
    for i, mid in enumerate(media_ids):
        params[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    api("POST", f"{page}/feed", token, **params)


def publish(post: IGPost, db, networks=("ig", "fb")) -> dict[str, str]:
    """Publie sur les réseaux demandés ; renvoie {réseau: 'ok' | message d'erreur}."""
    creds = get_credentials(db)
    results = {}
    if "ig" in networks:
        try:
            publish_instagram(post, creds)
            post.ig_published_at = datetime.utcnow()
            results["ig"] = "ok"
        except Exception as e:  # noqa: BLE001
            results["ig"] = str(e)
    if "fb" in networks:
        try:
            publish_facebook(post, creds)
            post.fb_published_at = datetime.utcnow()
            results["fb"] = "ok"
        except Exception as e:  # noqa: BLE001
            results["fb"] = str(e)
    if post.ig_published_at or post.fb_published_at:
        post.status = "published"
    errors = [f"{k}: {v}" for k, v in results.items() if v != "ok"]
    post.last_error = " | ".join(errors) or None
    db.commit()
    return results


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    networks = tuple(n for n in ("ig", "fb") if f"--{n}" in sys.argv) or ("ig", "fb")
    db = SessionLocal()
    if args:
        post = db.query(IGPost).filter_by(day=date.fromisoformat(args[0])).first()
    else:
        post = (db.query(IGPost).filter_by(status="draft")
                .order_by(IGPost.day.desc()).first())
    if not post:
        raise SystemExit("Aucun post à publier.")
    results = publish(post, db, networks)
    for network, res in results.items():
        print(f"{network}: {'✓ publié' if res == 'ok' else '! ' + res}")
    db.close()


if __name__ == "__main__":
    main()
