"""Staging-only: create/refresh manager, viewer (tenant TEST) + owner (platform)
test users so every role can be browser-verified. Idempotent.

Run with the staging venv on the VPS:
  /opt/calltone-backend-staging/venv/bin/python scripts/staging_seed_roles.py
"""
import sys, uuid
sys.path.insert(0, "/opt/calltone-backend-staging")

from app.database import SessionLocal  # noqa: E402
from app.models import User, Role, Client  # noqa: E402
from app.security import hash_password  # noqa: E402

CLIENT_ID = 1  # TEST tenant

# (email, password, role_name, client_id)  client_id=None => platform scope
TARGETS = [
    ("staging_calltone_manager@spamok.com", "Manager#Staging2026", "manager", CLIENT_ID),
    ("staging_calltone_viewer@spamok.com",  "Viewer#Staging2026",  "viewer",  CLIENT_ID),
    ("staging_calltone_owner@spamok.com",   "Owner#Staging2026",   "owner",   None),
]


def main() -> None:
    db = SessionLocal()
    try:
        for email, pw, role_name, client_id in TARGETS:
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                print(f"[ERROR] role {role_name!r} not found in DB; skipping {email}")
                continue
            u = db.query(User).filter(User.email == email).first()
            created = False
            if not u:
                u = User(email=email)  # integer PK autoincrements
                db.add(u)
                created = True
            u.password_hash = hash_password(pw)
            u.role_id = role.id
            u.client_id = client_id
            if hasattr(u, "is_active"):
                u.is_active = True
            if hasattr(u, "status"):
                u.status = "active"
            if hasattr(u, "name") and not getattr(u, "name", None):
                u.name = f"staging {role_name}"
            if hasattr(u, "full_name") and not getattr(u, "full_name", None):
                u.full_name = f"staging {role_name}"
            db.flush()
            client = db.query(Client).filter(Client.id == u.client_id).first() if u.client_id else None
            print(f"[{'NEW' if created else 'UPD'}] {email} pw={pw} role={role_name} "
                  f"client={client.name if client else '(platform)'}")
        db.commit()
        print("COMMIT OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
