"""Panel d'administration : recherche par mots-clés dans les résumés
(6 mois / 12 mois / tout), gestion des utilisateurs et vue des alertes."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload

from .db import get_db
from .models import User, Alert, Summary, Debate, IGPost, Setting
from .auth import require_admin
from .i18n import LANGS

router = APIRouter()

PERIODS = {"6m": 183, "12m": 366, "all": None}
META_KEYS = ("meta_access_token", "meta_ig_user_id", "meta_fb_page_id")


def _templates():
    from .main import templates, ctx
    return templates, ctx


def search_summaries(db: Session, kw: str, period: str, slang: str, limit=200):
    """Recherche AND sur tous les mots-clés (insensible à la casse) dans
    titre + corps + enjeux + issue des résumés de la période choisie."""
    words = [w.strip() for w in kw.split() if w.strip()]
    if not words:
        return []
    stmt = (select(Summary).join(Debate)
            .options(selectinload(Summary.debate))
            .where(Summary.lang == (slang if slang in LANGS else "fr")))
    days = PERIODS.get(period, 183)
    if days:
        stmt = stmt.where(Debate.day >= date.today() - timedelta(days=days))
    for w in words:
        like = f"%{w}%"
        stmt = stmt.where(or_(Summary.title.ilike(like), Summary.body.ilike(like),
                              Summary.stakes.ilike(like), Summary.outcome.ilike(like)))
    stmt = stmt.order_by(Debate.day.desc()).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/{lang}/admin")
def admin_panel(request: Request, lang: str, kw: str = "", period: str = "6m",
                slang: str = "fr", msg: str = "", admin=Depends(require_admin),
                db: Session = Depends(get_db)):
    templates, ctx = _templates()
    results = search_summaries(db, kw, period, slang) if kw else []
    users = db.query(User).order_by(User.created_at.desc()).all()
    alert_counts = dict(db.execute(
        select(Alert.user_id, func.count()).group_by(Alert.user_id)).all())
    alerts = db.query(Alert).options(selectinload(Alert.user))\
        .order_by(Alert.created_at.desc()).limit(100).all()

    # Publications : derniers posts générés, avec URLs d'aperçu (/media/...)
    posts_raw = db.query(IGPost).order_by(IGPost.day.desc()).limit(14).all()
    posts = []
    for p in posts_raw:
        previews = ["/media/" + fp.split("ig_out/", 1)[-1]
                    for fp in (p.image_paths or "").split("|") if fp][:4]
        posts.append((p, previews))

    meta = {k: (db.get(Setting, k).value if db.get(Setting, k) else "")
            for k in META_KEYS}

    return templates.TemplateResponse("admin.html", ctx(
        request, lang, kw=kw, period=period, slang=slang, results=results,
        users=users, alert_counts=alert_counts, all_alerts=alerts,
        posts=posts, meta=meta, msg=msg))


@router.post("/{lang}/admin/meta")
def save_meta(request: Request, lang: str,
              meta_access_token: str = Form(""), meta_ig_user_id: str = Form(""),
              meta_fb_page_id: str = Form(""), admin=Depends(require_admin),
              db: Session = Depends(get_db)):
    values = {"meta_access_token": meta_access_token,
              "meta_ig_user_id": meta_ig_user_id,
              "meta_fb_page_id": meta_fb_page_id}
    for key, value in values.items():
        row = db.get(Setting, key) or Setting(key=key)
        row.value = value.strip()
        db.merge(row)
    db.commit()
    return RedirectResponse(f"/{lang}/admin?msg=meta_saved", status_code=303)


@router.post("/{lang}/admin/meta/tester")
def test_meta(request: Request, lang: str, admin=Depends(require_admin),
              db: Session = Depends(get_db)):
    from scraper.instagram.publish import get_credentials, check_connection
    try:
        info = check_connection(get_credentials(db))
        parts = [f"{k}: {v}" for k, v in info.items()] or ["aucun compte configuré"]
        msg = "meta_ok::" + " — ".join(parts)
    except Exception as e:  # noqa: BLE001
        msg = "meta_err::" + str(e)[:200]
    return RedirectResponse(f"/{lang}/admin?msg={msg}", status_code=303)


@router.post("/{lang}/admin/posts/{post_id}/caption")
def update_caption(request: Request, lang: str, post_id: int,
                   caption: str = Form(""), admin=Depends(require_admin),
                   db: Session = Depends(get_db)):
    post = db.get(IGPost, post_id)
    if not post:
        raise HTTPException(404)
    post.caption = caption
    db.commit()
    return RedirectResponse(f"/{lang}/admin?msg=caption_saved", status_code=303)


@router.post("/{lang}/admin/posts/{post_id}/publier")
def publish_post(request: Request, lang: str, post_id: int,
                 network_ig: str = Form(""), network_fb: str = Form(""),
                 admin=Depends(require_admin), db: Session = Depends(get_db)):
    post = db.get(IGPost, post_id)
    if not post:
        raise HTTPException(404)
    networks = tuple(n for n, v in (("ig", network_ig), ("fb", network_fb)) if v)
    if not networks:
        return RedirectResponse(f"/{lang}/admin?msg=meta_err::aucun réseau coché",
                                status_code=303)
    from scraper.instagram.publish import publish
    results = publish(post, db, networks)
    errors = [f"{k}: {v}" for k, v in results.items() if v != "ok"]
    msg = ("meta_err::" + " | ".join(errors)[:200]) if errors else "post_published"
    return RedirectResponse(f"/{lang}/admin?msg={msg}", status_code=303)


@router.post("/{lang}/admin/users/{user_id}/role")
def toggle_role(request: Request, lang: str, user_id: int,
                admin=Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    if u.id == admin.id:
        raise HTTPException(400, "Impossible de modifier son propre rôle.")
    u.role = "admin" if u.role != "admin" else "user"
    db.commit()
    return RedirectResponse(f"/{lang}/admin", status_code=303)


@router.post("/{lang}/admin/users/{user_id}/supprimer")
def delete_user(request: Request, lang: str, user_id: int,
                admin=Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    if u.id == admin.id:
        raise HTTPException(400, "Impossible de supprimer son propre compte.")
    db.delete(u)
    db.commit()
    return RedirectResponse(f"/{lang}/admin", status_code=303)
