import streamlit as st
import requests
import pandas as pd
import altair as alt
import json

st.set_page_config(page_title="Mon Profil", page_icon="👤", layout="wide")

API_URL = "http://app:8000"

# --- CONFIGURATION DES TAGS ---
TAG_CATEGORIES = {
    "Régime & Santé": ["Végétarien", "Végétalien", "Sans gluten", "Sans lactose", "Faible en calories"],
    "Cuisines du Monde": ["Française", "Italienne", "Asiatique", "Méditerranéenne", "Indienne", "Mexicaine", "Américaine"],
    "Saveurs": ["Épicé", "Sucré-salé", "Frais", "Réconfortant"],
    "Ingrédients": ["Chocolat", "Fromage", "Fruits de mer", "Champignons", "Avocat"],
    "Moment": ["Petit-déjeuner", "Déjeuner", "Dîner", "Apéro", "Snack"]
}

def save_preferences(user_id, tags):
    """Envoie les tags au backend"""
    try:
        # On suppose un endpoint PUT /user/{id} ou PUT /user/{id}/preferences
        resp = requests.put(f"{API_URL}/user/{user_id}/preferences", json=tags)
        if resp.status_code == 200:
            st.success("✅ Préférences enregistrées !")
            return True
        else:
            st.error(f"Erreur sauvegarde : {resp.status_code}")
    except Exception as e:
        st.error(f"Erreur technique : {e}")
    return False

def main():
    st.title("👤 Profil du Chef")
    
    user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)
    
    # Récupération des données
    try:
        response = requests.get(f"{API_URL}/user/{user_id}/profile")
        if response.status_code == 200:
            user_data = response.json()
        else:
            st.warning("Profil introuvable (API non connectée ?). Mode démo activé.")
            user_data = {"total_likes": 0, "favorite_tags": [], "preferences": []}
    except:
        user_data = {"total_likes": 0, "favorite_tags": [], "preferences": []}

    # --- PARTIE 1 : VISUALISATION (Ton code existant) ---
    st.header("Analyse de l'historique")
    
    c1, c2 = st.columns(2)
    c1.metric("Interactions Totales", user_data.get("total_likes", 0))
    flavors = user_data.get("favorite_tags", [])
    c2.metric("Goûts identifiés (Auto)", len(flavors))
    
    if flavors:
        st.caption("Basé sur vos likes passés")
        df = pd.DataFrame(flavors)
        df = df.rename(columns={"tag": "Saveur", "count": "Intérêt"})
        chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('Intérêt', title='Score'),
            y=alt.Y('Saveur', sort='-x'), 
            color=alt.value("#4CAF50"),
            tooltip=['Saveur', 'Intérêt']
        ).properties(height=max(300, len(df) * 25))
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Pas assez de données d'interaction pour générer le graphique.")

    st.divider()

    # --- PARTIE 2 : SAISIE MANUELLE (Nouveau code) ---
    st.header("Mes Préférences Explicites")
    st.caption("Aidez l'algorithme en précisant ce que vous aimez.")

    # Récupérer les prefs existantes (si JSON en base, sinon liste vide)
    current_prefs = user_data.get("preferences", [])
    # Sécurité si jamais c'est null
    if current_prefs is None: current_prefs = []

    with st.form("prefs_form"):
        selected_tags = []
        
        # Affichage en grille
        for category, tags in TAG_CATEGORIES.items():
            st.subheader(f"🏷️ {category}")
            cols = st.columns(3)
            for i, tag in enumerate(tags):
                # Case cochée si le tag est déjà dans le profil
                checked = tag in current_prefs
                if cols[i % 3].checkbox(tag, value=checked, key=f"check_{user_id}_{tag}"):
                    selected_tags.append(tag)
            st.write("") # Espace
        
        submit = st.form_submit_button("Enregistrer mes choix")
        
        if submit:
            if save_preferences(user_id, selected_tags):
                # Petit délai pour laisser le toast s'afficher avant refresh
                import time
                time.sleep(1)
                st.rerun()

if __name__ == "__main__":
    main()