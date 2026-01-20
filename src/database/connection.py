import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Récupération de l'URL depuis l'environnement (défini dans docker-compose)
# Si pas de variable (ex: lancement local hors docker), on fallback sur SQLite
# Fallback sur PostgreSQL localhost (port mapped 5433) si pas de variable
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://user:password@localhost:5433/smartretail"
)

print(f"🔌 Connexion BDD : {DATABASE_URL}")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Générateur de session pour FastAPI et scripts"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
