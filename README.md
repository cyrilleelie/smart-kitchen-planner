# 🥗 Smart Kitchen Planner

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)
[![MLflow](https://img.shields.io/badge/MLflow-2.12-red.svg)](https://mlflow.org/)
[![Tests](https://img.shields.io/badge/Tests-32%20passed-success.svg)]()

**Smart Kitchen Planner** est un assistant culinaire intelligent qui génère des plannings de repas hebdomadaires ultra-personnalisés en combinant **Machine Learning** et **optimisation algorithmique**.

---

## ✨ Fonctionnalités Clés

| Fonctionnalité | Description |
|----------------|-------------|
| 🧠 **Recommandation Hybride** | **Collaborative (SVD)** pour la personnalisation & **Content-Based (Random Forest)** pour le contexte (temps/saison) |
| 🔄 **Stratégie 80/20** | Mix équilibré entre recettes performantes (80%) et découvertes (20%) pour éviter la routine |
| 🔍 **Recherche Sémantique** | Embeddings Sentence-BERT (384 dimensions) pour comprendre le sens des recettes |
| ⚖️ **Contraintes Nutritionnelles** | Respect des cibles caloriques et du temps de préparation |
| 📊 **MLOps Intégré** | Tracking des expériences avec MLflow (Random Forest & SVD), détection du drift avec Evidently |
| 🛡️ **Sécurité API** | Rate Limiting (slowapi), CORS configuré, paramètres externalisés |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Streamlit  │───▶│   FastAPI   │◀──▶│ PostgreSQL  │         │
│  │   (8501)    │    │   (8000)    │    │   (5433)    │         │
│  └─────────────┘    └──────┬──────┘    └─────────────┘         │
│                            │                                    │
│                     ┌──────▼──────┐                            │
│                     │   MLflow    │                            │
│                     │   (5000)    │                            │
│                     └─────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### Services

| Service | Port | Technologie | Rôle |
|---------|------|-------------|------|
| `db` | 5433 | PostgreSQL 15 + PGVector | Stockage des recettes, utilisateurs, embeddings |
| `app` | 8000, 8501 | FastAPI + Streamlit | API REST + Interface utilisateur |
| `mlflow` | 5000 | MLflow | Tracking des expériences ML |

---

## ⚙️ Configuration

### Variables d'Environnement

1. Copier le fichier template :
   ```bash
   cp .env.example .env
   ```

2. Configurer les valeurs :
   ```env
   # Database
   POSTGRES_USER=user
   POSTGRES_PASSWORD=your_secure_password
   POSTGRES_DB=smartretail
   
   # API Security
   ALLOWED_ORIGINS=http://localhost:8501
   ```

> ⚠️ **IMPORTANT** : Ne jamais commiter le fichier `.env` (déjà dans `.gitignore`)

---

## � Installation

### Prérequis
- Docker & Docker Compose
- Git

### Démarrage Rapide

```bash
# 1. Cloner le projet
git clone https://github.com/cyrilleelie/smartretail-recsys
cd smartretail-recsys

# 2. Configurer l'environnement
cp .env.example .env

# 3. Lancer la stack
docker-compose up --build -d

# 4. Vérifier les services
docker-compose ps
```

### Initialisation des Données

#### Step 1 : Base de données & Recettes
```bash
# Créer les tables, charger les recettes et générer les embeddings
docker-compose exec app python src/scripts/init_db.py

# (Optionnel) Charger des recettes supplémentaires
# Arguments : --count <nombre_de_recettes>
docker-compose exec app python src/scripts/load_recipes.py --count 1000
```

#### Step 2 : Utilisateurs & Personas
```bash
# Initialiser TOUS les utilisateurs définis dans data/personas/
# Cela crée les comptes et génère un historique initial d'interactions
docker-compose exec app python src/scripts/init_personas.py

# (Manuel) Charger un persona spécifique
# Arguments : <nom_persona> (fichier sans extension dans data/personas/)
docker-compose exec app python src/scripts/inject_persona.py captain_nemo

# (Manuel) Ajouter des interactions supplémentaires
# Arguments : <nom_persona> <nombre_interactions>
docker-compose exec app python src/scripts/add_interactions.py captain_nemo 50

# (Manuel) Supprimer un utilisateur et tout son historique (interactions & logs)
# Arguments : <username>
docker-compose exec app python src/scripts/delete_user.py captain_nemo
```

#### Step 3 : Simulation & Monitoring
```bash

# Simuler une activité historique (Logs + Interactions) pour tester le monitoring
# Scanne data/personas/ pour trouver les utilisateurs correspondants
# Arguments : --start YYYY-MM-DD --end YYYY-MM-DD --interactions <N> --simulations <M>
docker-compose exec app python src/scripts/simulate_activity.py --start 2026-01-01 --end 2026-01-31 --interactions 5 --simulations 10

```

### Accès aux Interfaces

| Interface | URL |
|-----------|-----|
| 🖥️ Frontend Streamlit | http://localhost:8501 |
| 📚 API Documentation | http://localhost:8000/docs |
| 📊 MLflow Dashboard | http://localhost:5000 |

---

## 📡 API Endpoints

| Méthode | Endpoint | Description | Rate Limit |
|---------|----------|-------------|------------|
| `POST` | `/recommend` | Recommandations contextuelles (Content-Based ou Collaborative) | 30/min |
| `POST` | `/generate-planning` | Planning complet (jours, repas, calories, stratégie) | 10/min |
| `PUT` | `/user/{id}/preferences` | Met à jour les préférences | 50/min |
| `POST` | `/feedback` | Enregistre une note utilisateur | - |
| `GET` | `/explore` | Découvrir de nouvelles recettes | - |

---

## 🧪 Tests

```bash
# Exécuter les tests avec couverture
docker-compose exec app pytest tests/ -v --cov=src

# Ou localement avec le venv
.venv/Scripts/python.exe -m pytest tests/ -v --cov=src
```

**Couverture actuelle :** ~85% (32 tests)

---

## 📂 Structure du Projet

```
├── src/
│   ├── api/                 # API FastAPI
│   │   ├── app.py           # Routes et endpoints
│   │   └── schemas.py       # Modèles Pydantic
│   ├── database/            # Couche de persistance
│   │   ├── models.py        # Modèles SQLAlchemy
│   │   └── connection.py    # Gestion des sessions
│   ├── recommender/         # Moteur de recommandation
│   │   ├── inference_service.py  # Inférence ML (MLflow)
│   │   ├── solver.py        # Algorithme de planification
│   │   ├── profile_builder.py    # Construction profil utilisateur
│   │   └── vectorizer.py    # Génération embeddings
│   ├── mlops/               # Outils MLOps
│   │   ├── train_model.py   # Entraînement du modèle
│   │   └── monitor_drift.py # Détection du drift (Evidently)
│   ├── ui/                  # Frontend Streamlit
│   └── utils/               # Utilitaires (logging, traductions)
├── tests/                   # Tests unitaires
├── docker-compose.yml       # Orchestration des services
├── Dockerfile               # Image Python
└── pyproject.toml           # Dépendances Poetry
```

---

## �️ Commandes Utiles

```bash
# Logs en temps réel
docker-compose logs -f app

# Redémarrer un service
docker-compose restart app

# Arrêter la stack
docker-compose down

# Entraîner le modèle ML (Random Forest par défaut)
# Arguments : --pipeline <rf|svd>
docker-compose exec app python src/mlops/train_model.py --pipeline rf

# Entraîner le modèle de Collaborative Filtering (SVD)
# Arguments : --pipeline <rf|svd>
docker-compose exec app python src/mlops/train_model.py --pipeline svd

# Voir la section MLOps pour le Monitoring et l'Orchestration
```

---

## 🔐 Sécurité

- ✅ **Secrets externalisés** : Pas de credentials dans le code
- ✅ **Rate Limiting** : Protection contre les abus (slowapi)
- ✅ **CORS configuré** : Origines autorisées contrôlées
- ✅ **Logging structuré** : Traçabilité des erreurs

---

## 📈 MLOps

Le projet intègre un pipeline MLOps complet :

1. **Entraînement Multi-Modèle** :
    - **Random Forest (rf)** : Apprentissage contextuel (Heure, Saison, Profil) sur vecteurs sémantiques.
    - **SVD (svd)** : Filtrage collaboratif pur (Matrix Factorization) pour la personnalisation.
2. **Tracking** : Paramètres, métriques (RMSE, MAE) et artefacts dans MLflow.
3. **Inférence** : Sélection dynamique de la stratégie (Content-Based vs Collaborative).
4. **Monitoring** : Détection du drift avec Evidently.
    - **Random Forest (rf)** : Tests KS (Embeddings) et Chi-Square (Categorical).
    - **SVD (collaborative)** : Test Wasserstein sur les distributions de scores et ratings.
    - **Rapports** : Générés dans `reports/rf/` et `reports/svd/`.

### Automation & Monitoring

**1. Monitoring (Détection de drift)**

```bash
# Random Forest
# Arguments : --model <rf|svd>
docker-compose exec app python src/mlops/monitor_drift.py --model rf

# SVD
# Arguments : --model <rf|svd>
docker-compose exec app python src/mlops/monitor_drift.py --model svd
```

**2. Orchestrateur (Monitoring + Réentraînement auto)**
L'orchestrateur lance le monitoring et déclenche un réentraînement si un drift est détecté.

```bash
# Pipeline Random Forest
# Arguments : --model <rf|svd>
docker-compose exec app python src/mlops/orchestrator.py --model rf

# Pipeline SVD
# Arguments : --model <rf|svd>
docker-compose exec app python src/mlops/orchestrator.py --model svd
```

### Simulation de Drift (Tests)

Le projet inclut un script dédié pour simuler du drift et tester le pipeline de monitoring.

#### Processus de test complet

```bash
# Étape 1 : Réinitialiser la base avec des recettes
docker-compose exec app python -m src.scripts.init_db

# Étape 2 : Créer les utilisateurs (personas)
docker-compose exec app python -m src.scripts.init_personas

# Étape 3 : Simuler une période de RÉFÉRENCE (comportement normal)
# Génère des interactions et logs sur la période J-14 à J-7
docker-compose exec app python -m src.scripts.simulate_activity \
    --start 2026-01-14 --end 2026-01-20 \
    --interactions 10 --simulations 20

# Étape 4 : Simuler une période avec DRIFT (comportement anormal)
# Utilise le script simulate_drift.py avec un type de drift
docker-compose exec app python -m src.scripts.simulate_drift \
    --start 2026-01-21 --end 2026-01-28 \
    --simulations 20 --drift-type invert

# Étape 5 : Exécuter le monitoring (doit détecter le drift)
# Pour Random Forest
docker-compose exec app python -m src.mlops.monitor_drift --model rf
# Pour SVD
docker-compose exec app python -m src.mlops.monitor_drift --model svd

# Étape 6 : Tester l'orchestrateur (monitoring + réentraînement auto si drift)
# Pour Random Forest
docker-compose exec app python -m src.mlops.orchestrator --model rf
# Pour SVD
docker-compose exec app python -m src.mlops.orchestrator --model svd
```

#### Types de drift disponibles

| Type | Description | Effet sur les données |
|------|-------------|----------------------|
| `invert` | Inverse les scores | 5→1, 1→5 |
| `fixed_context` | Force un contexte fixe | meal_type=0, season=0 |
| `offset` | Ajoute un biais aux scores | +1.5 sur tous les scores |
| `random` | Scores complètement aléatoires | Ignore les profils persona |

#### Stratégie de détection par modèle

Le monitoring utilise une **sliding window** comparant deux périodes :
- **Référence** : `[J-14, J-7]` — Données de la semaine précédente
- **Courant** : `[J-7, J-0]` — Données des 7 derniers jours

**Random Forest (RF)** — Approche cosine similarity :
| Feature | Type | Test statistique |
|---------|------|-----------------|
| `cosine_similarity` | Numérique | Wasserstein |
| `prediction` | Numérique | Wasserstein |
| `meal_type` | Catégoriel | Chi² |
| `season` | Catégoriel | Chi² |

**SVD (Collaborative Filtering)** :
| Feature | Type | Test statistique |
|---------|------|-----------------|
| `rating` | Numérique | Wasserstein |
| `prediction` | Numérique | Wasserstein |

**Seuils de protection** :
- Minimum 100 échantillons dans la période courante
- Ratio volume courant/référence ≥ 10%

---

## 🤝 Contribution

1. Créer une branche : `git checkout -b feature/ma-feature`
2. Commiter : `git commit -m "✨ feat: Ma nouvelle feature"`
3. Pousser : `git push origin feature/ma-feature`
4. Ouvrir une Pull Request

---

## 📄 Licence

MIT License - Voir [LICENSE](LICENSE) pour plus de détails.
