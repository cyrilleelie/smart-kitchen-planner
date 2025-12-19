import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Récupération de l'URL depuis l'environnement (défini dans docker-compose)
# Si pas de variable (ex: lancement local hors docker), on fallback sur SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///smartretail.db")

print(f"🔌 Connexion BDD : {DATABASE_URL}")

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # PostgreSQL
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Générateur de session pour FastAPI et scripts"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()