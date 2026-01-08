import streamlit as st
import requests
from src.ui.config import API_URL, TAG_CATEGORIES

st.set_page_config(page_title="Mon Profil", page_icon="👤", layout="wide")

def save_preferences(user_id, tags):
    try:
        resp = requests.put(f"{API_URL}/user/{user_id}/preferences", json=tags)
        return resp.status_code == 200
    except:
        return False

def main():
    st.title("👤 Profil du Chef")
    
    # L'ID Utilisateur est le maître du contexte ici
    user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)
    
    user_prefs = []
    total_likes = 0
    
    try:
        # Récupération fraîche des données à chaque changement d'ID
        resp_prof = requests.get(f"{API_URL}/user/{user_id}/profile")
        if resp_prof.status_code == 200:
            user_prefs = resp_prof.json().get("preferences", [])
            
        resp_inter = requests.get(f"{API_URL}/user/{user_id}/interactions")
        if resp_inter.status_code == 200:
            total_likes = len(resp_inter.json())
            
    except Exception as e:
        st.error(f"Erreur API : {e}")

    # Stats
    st.header("Mes Stats")
    c1, c2 = st.columns(2)
    c1.metric("Recettes notées", total_likes)
    c2.metric("Tags favoris", len(user_prefs))
    st.divider()

    # Formulaire
    st.header("Mes Préférences Alimentaires")
    st.caption(f"Configuration pour l'utilisateur #{user_id}")

    with st.form("prefs_form"):
        selected_tags = []
        
        for category, tags in TAG_CATEGORIES.items():
            st.subheader(f"🏷️ {category}")
            cols = st.columns(3)
            for i, tag in enumerate(tags):
                checked = tag in user_prefs
                
                # --- CORRECTIF CRUCIAL ICI ---
                # On intègre user_id dans la key pour forcer le reset des cases
                # quand on change d'utilisateur
                widget_key = f"{user_id}_{category}_{tag}"
                
                if cols[i % 3].checkbox(tag, value=checked, key=widget_key):
                    selected_tags.append(tag)
            st.write("")
        
        if st.form_submit_button("Enregistrer mes choix", type="primary"):
            if save_preferences(user_id, selected_tags):
                st.success("✅ Préférences sauvegardées !")
                import time
                time.sleep(1)
                st.rerun()
            else:
                st.error("Erreur sauvegarde.")

if __name__ == "__main__":
    main()