"""Crée un compte administrateur (ou promeut un compte existant).

Usage : python -m scripts.create_admin admin@politrace.ch
Le mot de passe est demandé de façon masquée.
"""
import getpass
import sys

sys.path.insert(0, ".")

from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import User  # noqa: E402
from app.auth import hash_password  # noqa: E402

Base.metadata.create_all(engine)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    email = sys.argv[1].strip().lower()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.role = "admin"
        db.commit()
        print(f"✓ {email} promu administrateur.")
    else:
        pw = getpass.getpass("Mot de passe (8 caractères min.) : ")
        if len(pw) < 8:
            print("Mot de passe trop court.")
            sys.exit(1)
        db.add(User(email=email, password_hash=hash_password(pw), role="admin"))
        db.commit()
        print(f"✓ Administrateur {email} créé.")
    db.close()


if __name__ == "__main__":
    main()
