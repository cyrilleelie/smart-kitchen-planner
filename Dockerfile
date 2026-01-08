# Image de base légère
FROM python:3.12-slim

# Dossier de travail
WORKDIR /app

# Installation des outils système
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copie des fichiers Poetry
COPY pyproject.toml ./

# Installation de Poetry
RUN pip install poetry
RUN poetry config virtualenvs.create false

# --- CORRECTION DU PROBLÈME DE TÉLÉCHARGEMENT ---
# 1. Augmenter le temps d'attente avant de déclarer une erreur (300 secondes = 5 min)
ENV POETRY_HTTP_TIMEOUT=300
# 2. Forcer le téléchargement UN PAR UN pour ne pas saturer la connexion
RUN poetry config installer.max-workers 1

# Installation des dépendances (maintenant plus stable)
# On ajoute --no-root pour ignorer l'absence du README et du code source
RUN poetry install --no-interaction --no-ansi --no-root

# On télécharge le modèle spaCy pendant la construction de l'image
RUN poetry run python -m spacy download en_core_web_sm

# Copie du code source
COPY . .

# Ports
EXPOSE 8000
EXPOSE 8501

# Commande par défaut
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]