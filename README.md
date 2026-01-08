# 🥗 Smart Kitchen Planner (Smart Retail 2.0)

**Smart Kitchen Planner** est un assistant culinaire intelligent nouvelle génération. Il génère des plannings de repas hebdomadaires ultra-personnalisés en respectant à la fois vos goûts (appris par IA) et vos contraintes nutritionnelles (gérées par algorithme).

Le projet a été entièrement refondu pour adopter une **architecture micro-services conteneurisée**, garantissant robustesse, scalabilité et facilité de déploiement via Docker.

---

## 🏗️ Architecture Technique Détaillée

### 1. Le Moteur de Recommandation Hybride
La force du Smart Kitchen Planner réside dans son moteur "Bicéphale" qui combine le meilleur de l'IA et de la Recherche Opérationnelle :

* **A. Le Cerveau Sémantique (Vector Search)**
    * **Technologie :** [Sentence-Transformers](https://www.sbert.net/) (modèle `all-MiniLM-L6-v2`) + [PGVector](https://github.com/pgvector/pgvector).
    * **Fonctionnement :** Contrairement à une recherche par mots-clés classique (TF-IDF), chaque recette est convertie en un vecteur mathématique dense (embedding) de 384 dimensions. Cela permet de capturer le **sens** et le **contexte** (ex: comprendre que "Tacos" est proche de "Fajitas" même s'ils ne partagent pas les mêmes mots).
    * **Stockage :** Les vecteurs sont stockés directement dans PostgreSQL grâce à l'extension `vector`, permettant des recherches de similarité cosinus ultra-rapides.

* **B. Le Solver Algorithmique (Contraintes)**
    * **Technologie :** Algorithme heuristique custom (Python pur).
    * **Fonctionnement :** Une fois les recettes "pertinentes" identifiées par l'IA, le Solver entre en jeu pour assembler le puzzle. Il applique des contraintes strictes :
        * **Cible Calorique :** Respect d'une fourchette (ex: 500-700 kcal/repas).
        * **Temps de Préparation :** Filtrage dynamique selon le temps disponible.
        * **Diversité :** Mécanisme de pénalité pour éviter de proposer deux fois le même plat ou le même type de cuisine le même jour.

### 2. Infrastructure Micro-services (Docker)
L'application est découpée en 3 conteneurs isolés communiquant via un réseau Docker interne :

1.  **`db` (Database Layer)**
    * Image : `postgres:15`
    * Extensions : `pgvector` activé au démarrage.
    * Rôle : Stockage persistant des utilisateurs, interactions, recettes et leurs embeddings.
2.  **`app` (Backend Layer)**
    * Image : Python 3.12 (Slim)
    * Framework : **FastAPI**.
    * Rôle : Expose une API RESTful. C'est le seul composant qui communique avec la BDD et qui charge les modèles d'IA lourds en mémoire.
3.  **`ui` (Frontend Layer)**
    * Image : Python 3.12 (Slim)
    * Framework : **Streamlit**.
    * Rôle : Interface utilisateur. Elle ne possède aucune logique métier propre et se contente d'interroger l'API via HTTP.

---

## 🖥️ L'Application Streamlit (Frontend)

L'interface utilisateur a été repensée pour être modulaire et intuitive. Elle se divise en 4 espaces distincts :

* **🏠 Dashboard (Home) :** Le tableau de bord principal. Il affiche l'état de santé du système (connexion API), les statistiques globales de l'utilisateur (nombre de recettes notées) et sert de hub de navigation.
* **📅 Planner (Le Générateur) :** Le cœur fonctionnel. Vous définissez vos critères (nombre de jours, calories cibles, temps max en cuisine) et lancez la génération. Le résultat affiche un planning détaillé jour par jour avec des indicateurs de compatibilité (Score Match) et des badges "Découverte".
* **🔥 Exploration :** Un mode "Tinder for Food". L'IA vous propose des recettes que vous ne connaissez pas encore. Vous pouvez les noter ou les passer. Chaque interaction affine votre profil vectoriel en temps réel.
* **👤 Profil :** Le centre de contrôle de vos données. C'est ici que vous définissez vos contraintes explicites ("Végétarien", "Sans Gluten", "Épicé"...) qui agiront comme des filtres durs sur les recommandations.

---

## 📂 Structure du Projet ("Clean Architecture")

```text
.
├── src/
│   ├── api/             # API REST (FastAPI)
│   │   ├── app.py       # Point d'entrée et routes
│   │   └── schemas.py   # Modèles de données Pydantic
│   ├── database/        # Couche de Persistance
│   │   ├── models.py    # Tables SQLAlchemy (User, Recipe, Interaction)
│   │   └── connection.py # Gestion de la session DB
│   ├── recommender/     # Moteur IA
│   │   ├── vectorizer.py # Génération des embeddings (Sentence-BERT)
│   │   ├── solver.py     # Algorithme de construction de menu
│   │   └── profile_builder.py # Création du vecteur utilisateur
│   ├── scripts/         # Outils d'Administration (CLI)
│   │   ├── init_db.py           # Reset total de la base
│   │   ├── load_data.py         # Ajout incrémental
│   │   ├── generate_embeddings.py # Calcul des vecteurs manquants
│   │   └── seed_interactions.py   # Génération de fausses données
│   ├── ui/              # Frontend Streamlit
│   │   ├── Home.py      # Page d'accueil
│   │   ├── config.py    # Configuration centralisée (URL API)
│   │   └── pages/       # Sous-pages (Planner, Exploration, Profil)
│   └── utils/           # Utilitaires transverses (Traductions)
├── data/                # Dossier monté pour les CSV bruts
├── docker-compose.yml   # Orchestration des services
└── Dockerfile           # Définition de l'image Python unique
```

---

## 🚀 Installation et Démarrage

Tout le projet est piloté par Docker Compose. Aucune installation locale de Python ou PostgreSQL n'est requise.

### 1. Démarrage de la Stack
```bash
# Clonez le projet
git clone https://github.com/cyrilleelie/smartretail-recsys
cd smartretail-recsys

# Construisez et lancez les conteneurs (mode détaché)
docker-compose up --build -d

# Vérifiez que tout tourne (3 services doivent être "Up")
docker-compose ps
```

Accès aux interfaces :
* **Frontend :** [http://localhost:8501](http://localhost:8501)
* **API Docs :** [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Initialisation des Données (Obligatoire au premier lancement)
Les scripts d'administration doivent être exécutés **à l'intérieur** du conteneur `app` pour accéder à la base de données.

**Étape A : Charger les données brutes (CSV vers PostgreSQL)**
```bash
docker-compose exec app python src/scripts/init_db.py
```

**Étape B : Calculer les Embeddings (Vectorisation IA)**
*Attention : Cette étape peut prendre quelques minutes selon la puissance de votre CPU.*
```bash
docker-compose exec app python src/scripts/generate_embeddings.py
```

**Étape C : (Optionnel) Créer un historique factice**
Pour tester l'application avec un utilisateur ayant déjà des préférences.
```bash
docker-compose exec app python src/scripts/seed_interactions.py
```

---

## 🛠️ Commandes Utiles

* **Voir les logs du Backend (API) :**
    ```bash
    docker-compose logs -f app
    ```
* **Voir les logs du Frontend :**
    ```bash
    docker-compose logs -f ui
    ```
* **Arrêter la stack :**
    ```bash
    docker-compose down
    ```
