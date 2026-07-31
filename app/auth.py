"""Authentification : mots de passe PBKDF2 (stdlib), sessions par cookie signé.

SECRET_KEY doit être défini dans .env en production (générer avec :
  python -c "import secrets; print(secrets.token_hex(32))" )
"""
import hashlib
import os
import secrets

from dotenv import load_dotenv
from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # clé éphémère : les sessions sautent à chaque redémarrage → définir SECRET_KEY !
    SECRET_KEY = secrets.token_hex(32)
    print("⚠️  SECRET_KEY absent de .env — clé éphémère générée (sessions non persistantes).")

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="politrace-session")
SESSION_COOKIE = "pt_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 jours


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240_000)
    return secrets.compare_digest(dk.hex(), expected)


def make_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None


def current_user(request: Request):
    """L'utilisateur connecté (posé par le middleware), ou None."""
    return getattr(request.state, "user", None)


def require_user(request: Request):
    user = current_user(request)
    if not user:
        lang = request.path_params.get("lang", "fr")
        raise HTTPException(status_code=303,
                            headers={"Location": f"/{lang}/connexion"})
    return user


def require_admin(request: Request):
    user = require_user(request)
    if user.role != "admin":
        raise HTTPException(status_code=403)
    return user
