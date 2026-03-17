from app.database import SessionLocal
from app.models import Client, Role, User
from app.security import hash_password

ROLES = [
    {"name": "super_admin", "display_name": "Super Admin"},
    {"name": "admin", "display_name": "Admin"},
    {"name": "manager", "display_name": "Manager"},
    {"name": "viewer", "display_name": "Viewer"},
    {"name": "qa", "display_name": "QA"},
    {"name": "agent", "display_name": "Agent"},
]

CLIENTS = [
    {"name": "BankServ Global", "industry": "Finance", "status": "active", "plan": "enterprise"},
]

USERS = [
    {
        "full_name": "Sarah Chen",
        "email": "admin@calltone.ai",
        "password": "Admin123!",
        "role": "super_admin",
        "client_name": None,
    },
    {
        "full_name": "Maya QA",
        "email": "qa@calltone.ai",
        "password": "Qa123456!",
        "role": "qa",
        "client_name": "BankServ Global",
    },
    {
        "full_name": "Agent One",
        "email": "agent1@calltone.ai",
        "password": "Agent123!",
        "role": "agent",
        "client_name": "BankServ Global",
    },
    {
        "full_name": "Agent Two",
        "email": "agent2@calltone.ai",
        "password": "Agent123!",
        "role": "agent",
        "client_name": "BankServ Global",
    },
]


def main():
    db = SessionLocal()

    try:
        for role_data in ROLES:
            if not db.query(Role).filter(Role.name == role_data["name"]).first():
                db.add(Role(**role_data))
        db.commit()

        for client_data in CLIENTS:
            if not db.query(Client).filter(Client.name == client_data["name"]).first():
                db.add(Client(**client_data))
        db.commit()

        for user_data in USERS:
            if db.query(User).filter(User.email == user_data["email"]).first():
                continue

            role = db.query(Role).filter(Role.name == user_data["role"]).first()
            client = None
            if user_data["client_name"]:
                client = db.query(Client).filter(Client.name == user_data["client_name"]).first()

            db.add(
                User(
                    full_name=user_data["full_name"],
                    email=user_data["email"],
                    password_hash=hash_password(user_data["password"]),
                    role_id=role.id,
                    client_id=client.id if client else None,
                    is_active=True,
                )
            )

        db.commit()
        print("Seed completed successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    main()