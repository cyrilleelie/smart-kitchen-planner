# 🥗 SmartRetail RecSys (Dockerized)

> **Projet d'Ingénierie IA de bout en bout :** Recommandation culinaire, Architecture Micro-services et Déploiement Docker.

**SmartRetail RecSys** est un moteur intelligent de génération de menus. Contrairement aux systèmes classiques qui suggèrent des plats isolés, ce système construit des **plannings hebdomadaires cohérents** (Midi & Soir) qui respectent vos contraintes nutritionnelles (Calories) et logistiques (Temps de préparation).

Le projet met l'accent sur une architecture **Clean Code**, conteneurisée avec **Docker**, et une séparation stricte entre le Data Engineering, le Backend (FastAPI) et le Frontend (Streamlit).

---

## 🏗️ Architecture

Le système suit une architecture micro-services orchestrée par Docker Compose.

```mermaid
graph TD
    User((Utilisateur)) -->|Interface Web| UI[Streamlit Frontend]
    UI -->|JSON HTTP| API[FastAPI Backend]
    
    subgraph "Container: App"
        API -->|CRUD & Auth| DB_Conn[SQLAlchemy]
        API -->|Recommandation| Engine[Content Engine (TF-IDF/Tags)]
        API -->|Planification| Solver[Greedy Solver]
    end
    
    subgraph "Container: DB"
        DB_Conn --> DB[(PostgreSQL)]
    end
```

## ✨ Fonctionnalités Clés

### 1. 🧠 Moteur de Recommandation (Content-Based)
Analyse les tags et ingrédients des recettes pour trouver ce qui correspond au profil de l'utilisateur.
* **Technique :** Matching de tags pondéré (Bonus/Malus) et Nettoyage NLP (Stop-words removal) pour la recherche par ingrédients.
* **Profilage :** Construction dynamique des préférences (Tags aimés/détestés) basée sur l'historique des notes.

### 2. 📅 Générateur de Planning (Le Solveur)
Transformer une liste de recettes aimées en un planning valide est un problème d'optimisation.
* **Algorithme :** Approche Greedy (Gloutonne) avec contraintes souples.
* **Contraintes gérées :**
    * Cible calorique (ex: 600 kcal +/- 20% par repas).
    * Diversité (pas deux fois la même recette).
    * Temps de préparation maximum.

### 3. 🛠️ Infrastructure & Data Engineering
* **Parsing Robuste :** Extraction des données nutritionnelles via Regex/AST pour gérer les formats CSV hétérogènes.
* **Docker :** Environnement reproductible avec `docker-compose`.
* **Base de données :** PostgreSQL pour la persistance des utilisateurs, recettes et interactions.

---

## 🛠️ Stack Technique

* **Langage :** Python 3.12
* **Infrastructure :** Docker, Docker Compose
* **Backend :** FastAPI, Pydantic, SQLAlchemy
* **Frontend :** Streamlit
* **Database :** PostgreSQL
* **Data Science :** Pandas, Scikit-learn (TF-IDF), Numpy
* **Gestionnaire de paquets :** Poetry

---

## 🚀 Installation & Démarrage

### 1. Pré-requis
* Docker & Docker Compose installés.
* Le fichier de données `RAW_recipes.csv` (à placer dans `data/raw/`).
  * [Lien Kaggle vers le dataset Food.com](https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions)

### 2. Démarrage Rapide
Tout le projet se lance en une seule commande :

```bash
docker-compose up --build
```

Cela va :
1. Lancer le conteneur Base de données (PostgreSQL).
2. Construire et lancer le conteneur Application (API + Frontend).
3. Exposer les services.

### 3. Initialisation des Données (Premier lancement)
Une fois les conteneurs actifs, chargez les données dans PostgreSQL :

```bash
# Dans un nouveau terminal
docker exec smartretail-recsys-app-1 poetry run python -m src.scripts.load_data
```
*Note : Ce script nettoie la donnée brute, parse les infos nutritionnelles et peuple la BDD.*

### 4. Accès

* **Frontend (Streamlit) :** [http://localhost:8501](http://localhost:8501)
* **API Docs (Swagger UI) :** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📂 Structure du Projet

```text
smartretail-recsys/
├── data/raw/            # Placez RAW_recipes.csv ici
├── src/
│   ├── api/             # FastAPI (Routes & Schemas)
│   ├── database/        # Modèles SQLAlchemy & Connexion
│   ├── recommender/     # Logique métier (ContentEngine, Solver, Profiler)
│   ├── scripts/         # Scripts ETL (load_data, pipeline)
│   ├── ui/              # Interface Streamlit (Pages & Components)
│   └── utils/           # Constantes & Helpers NLP
├── docker-compose.yml   # Orchestration
├── Dockerfile           # Image Python
└── pyproject.toml       # Dépendances Poetry
```

## 👤 Auteur

**Cyrille ELIE** - Projet Portfolio Ingénieur IA.