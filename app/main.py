"""Politrace — site web (FastAPI + Jinja2), routes préfixées par langue /fr /de /it."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session, selectinload

from .db import get_db, engine, Base, SessionLocal
from . import models
from .i18n import LANGS, DEFAULT, make_t
from .auth import SESSION_COOKIE, read_session_token
from scraper.party_colors import party_color

load_dotenv()
Base.metadata.create_all(engine)

app = FastAPI(title="Politrace")


@app.middleware("http")
async def attach_user(request: Request, call_next):
    """Pose request.state.user à partir du cookie de session signé."""
    request.state.user = None
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        uid = read_session_token(token)
        if uid:
            db = SessionLocal()
            try:
                request.state.user = db.get(models.User, uid)
            finally:
                db.close()
    return await call_next(request)
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/media", StaticFiles(directory=Path("data/ig_out"), check_dir=False), name="media")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

SITE_NAME = os.getenv("SITE_NAME", "Politrace")


def ctx(request: Request, lang: str, **kw):
    if lang not in LANGS:
        raise HTTPException(404)
    return {"request": request, "lang": lang, "langs": LANGS, "t": make_t(lang),
            "site_name": SITE_NAME, "pcolor": party_color,
            "user": getattr(request.state, "user", None), **kw}


from .accounts import router as accounts_router  # noqa: E402
from .admin import router as admin_router  # noqa: E402
app.include_router(accounts_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return RedirectResponse(f"/{DEFAULT}/")


@app.get("/{lang}/")
def home(request: Request, lang: str, db: Session = Depends(get_db)):
    latest = db.execute(
        select(models.Summary)
        .join(models.Debate)
        .where(models.Summary.lang == lang)
        .order_by(models.Debate.day.desc(), models.Summary.id.desc())
        .limit(8)
        .options(selectinload(models.Summary.debate))
    ).scalars().all()
    stats = {
        "members": db.scalar(select(func.count()).select_from(models.Politician)
                             .where(models.Politician.active == True)) or 0,
        "interests": db.scalar(select(func.count()).select_from(models.Interest)) or 0,
        "debates": db.scalar(select(func.count()).select_from(models.Debate)) or 0,
    }
    return templates.TemplateResponse("index.html",
                                      ctx(request, lang, latest=latest, stats=stats))


@app.get("/{lang}/politiciens")
def politicians(request: Request, lang: str, q: str = "", party: str = "",
                canton: str = "", council: str = "", role: str = "",
                db: Session = Depends(get_db)):
    stmt = select(models.Politician).where(models.Politician.active == True)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(models.Politician.first_name.ilike(like),
                              models.Politician.last_name.ilike(like),
                              models.Politician.party_abbr.ilike(like),
                              models.Politician.canton.ilike(like),
                              models.Politician.institution.ilike(like)))
    if party:
        stmt = stmt.where(models.Politician.party_abbr == party)
    if canton:
        stmt = stmt.where(models.Politician.canton_abbr == canton)
    if council:
        stmt = stmt.where(models.Politician.council == council)
    if role:
        stmt = stmt.where(models.Politician.role_type == role)
    people = db.execute(stmt.order_by(models.Politician.last_name)).scalars().all()

    roles = [r[0] for r in db.execute(
        select(models.Politician.role_type).where(models.Politician.active == True)
        .distinct().order_by(models.Politician.role_type)) if r[0]]

    parties = [r[0] for r in db.execute(
        select(models.Politician.party_abbr).where(models.Politician.active == True)
        .distinct().order_by(models.Politician.party_abbr)) if r[0]]
    cantons = [r[0] for r in db.execute(
        select(models.Politician.canton_abbr).where(models.Politician.active == True)
        .distinct().order_by(models.Politician.canton_abbr)) if r[0]]

    # nb de liens d'intérêts par personne (pour l'affichage en liste)
    counts = dict(db.execute(
        select(models.Interest.politician_id, func.count())
        .group_by(models.Interest.politician_id)).all())

    return templates.TemplateResponse("politicians.html",
        ctx(request, lang, people=people, parties=parties, cantons=cantons,
            counts=counts, roles=roles, q=q, f_party=party, f_canton=canton,
            f_council=council, f_role=role))


@app.get("/{lang}/politiciens/{pid}")
def politician_detail(request: Request, lang: str, pid: int,
                      db: Session = Depends(get_db)):
    person = db.get(models.Politician, pid,
                    options=[selectinload(models.Politician.mandates),
                             selectinload(models.Politician.interests)])
    if not person:
        raise HTTPException(404)
    mandates = sorted(person.mandates,
                      key=lambda m: (m.start or date(1900, 1, 1)), reverse=True)
    # regrouper les intérêts par secteur
    by_sector: dict[str, list] = {}
    for i in sorted(person.interests, key=lambda i: (i.sector or "~", i.organization)):
        by_sector.setdefault(i.sector or "—", []).append(i)
    return templates.TemplateResponse("politician_detail.html",
        ctx(request, lang, p=person, mandates=mandates, by_sector=by_sector))


@app.get("/{lang}/sessions")
def sessions(request: Request, lang: str, db: Session = Depends(get_db)):
    days = db.execute(
        select(models.Debate.day, func.count(models.Debate.id))
        .group_by(models.Debate.day).order_by(models.Debate.day.desc()).limit(60)
    ).all()
    return templates.TemplateResponse("sessions.html", ctx(request, lang, days=days))


@app.get("/{lang}/sessions/{day}")
def session_day(request: Request, lang: str, day: str, db: Session = Depends(get_db)):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(404)
    debates = db.execute(
        select(models.Debate).where(models.Debate.day == d)
        .order_by(models.Debate.council_abbr, models.Debate.id)
        .options(selectinload(models.Debate.summaries))
    ).scalars().all()
    items = []
    for deb in debates:
        s = next((s for s in deb.summaries if s.lang == lang), None) or \
            next((s for s in deb.summaries if s.lang == DEFAULT), None)
        if s:
            items.append((deb, s))
    return templates.TemplateResponse("session_day.html",
                                      ctx(request, lang, day=d, items=items))


@app.get("/{lang}/a-propos")
def about(request: Request, lang: str):
    return templates.TemplateResponse("about.html", ctx(request, lang))


@app.get("/health")
def health():
    return {"ok": True}
