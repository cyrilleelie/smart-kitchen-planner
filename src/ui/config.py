import os

# Gestion dynamique de l'URL : 
# - "http://app:8000" si on est dans le réseau Docker
# - "http://localhost:8000" si on lance Streamlit en local
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Catégories de tags partagées entre Profil et Home (si besoin)
TAG_CATEGORIES = {
    "Régime & Santé": ["Végétarien", "Végétalien", "Sans gluten", "Sans lactose", "Faible en calories"],
    "Cuisines du Monde": ["Française", "Italienne", "Asiatique", "Méditerranéenne", "Indienne", "Mexicaine", "Américaine"],
    "Saveurs": ["Épicé", "Sucré-salé", "Frais", "Réconfortant"],
    "Ingrédients": ["Chocolat", "Fromage", "Fruits de mer", "Champignons", "Avocat"]
}