"""Comptes utilisateurs : inscription, connexion, déconnexion, mes alertes."""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, Alert
from .auth import (hash_password, verify_password, make_session_token,
                   require_user, SESSION_COOKIE, SESSION_MAX_AGE)
from .i18n import LANGS

router = APIRouter()


def _templates():
    from .main import templates, ctx
    return templates, ctx


@router.get("/{lang}/connexion")
def login_page(request: Request, lang: str):
    templates, ctx = _templates()
    return templates.TemplateResponse("login.html", ctx(request, lang, error=None))


@router.post("/{lang}/connexion")
def login(request: Request, lang: str, email: str = Form(...),
          password: str = Form(...), db: Session = Depends(get_db)):
    templates, ctx = _templates()
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html", ctx(request, lang, error="login_error"), status_code=401)
    resp = RedirectResponse(f"/{lang}/alertes", status_code=303)
    resp.set_cookie(SESSION_COOKIE, make_session_token(user.id),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@router.get("/{lang}/inscription")
def register_page(request: Request, lang: str):
    templates, ctx = _templates()
    return templates.TemplateResponse("register.html", ctx(request, lang, error=None))


@router.post("/{lang}/inscription")
def register(request: Request, lang: str, email: str = Form(...),
             name: str = Form(""), password: str = Form(...),
             db: Session = Depends(get_db)):
    templates, ctx = _templates()
    email = email.strip().lower()
    if "@" not in email or len(password) < 8:
        return templates.TemplateResponse(
            "register.html", ctx(request, lang, error="register_invalid"), status_code=400)
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "register.html", ctx(request, lang, error="email_taken"), status_code=400)
    user = User(email=email, name=name.strip()[:100] or None,
                password_hash=hash_password(password))
    db.add(user)
    db.commit()
    resp = RedirectResponse(f"/{lang}/alertes", status_code=303)
    resp.set_cookie(SESSION_COOKIE, make_session_token(user.id),
                    max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@router.get("/deconnexion")
def logout():
    resp = RedirectResponse("/fr/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---- Mes alertes ----

@router.get("/{lang}/alertes")
def my_alerts(request: Request, lang: str, user=Depends(require_user),
              db: Session = Depends(get_db)):
    templates, ctx = _templates()
    alerts = db.query(Alert).filter(Alert.user_id == user.id)\
        .order_by(Alert.created_at.desc()).all()
    return templates.TemplateResponse("alerts.html", ctx(request, lang, alerts=alerts))


@router.post("/{lang}/alertes/ajouter")
def add_alert(request: Request, lang: str, keywords: str = Form(...),
              alert_lang: str = Form("fr"), user=Depends(require_user),
              db: Session = Depends(get_db)):
    kw = ",".join(k.strip() for k in keywords.split(",") if k.strip())[:300]
    if kw and alert_lang in LANGS:
        db.add(Alert(user_id=user.id, keywords=kw, lang=alert_lang))
        db.commit()
    return RedirectResponse(f"/{lang}/alertes", status_code=303)


@router.post("/{lang}/alertes/{alert_id}/supprimer")
def delete_alert(request: Request, lang: str, alert_id: int,
                 user=Depends(require_user), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return RedirectResponse(f"/{lang}/alertes", status_code=303)


@router.post("/{lang}/alertes/{alert_id}/basculer")
def toggle_alert(request: Request, lang: str, alert_id: int,
                 user=Depends(require_user), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    a.active = not a.active
    db.commit()
    return RedirectResponse(f"/{lang}/alertes", status_code=303)
