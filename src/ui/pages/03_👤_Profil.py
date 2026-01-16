import streamlit as st
import requests
from src.ui.config import API_URL, TAG_CATEGORIES
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import User

st.set_page_config(page_title="Mon Profil", page_icon="👤", layout="wide")


def save_preferences(user_id, tags):
    try:
        resp = requests.put(f"{API_URL}/user/{user_id}/preferences", json=tags)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    st.title("👤 Profil du Chef")

    with st.sidebar:
        st.header("Paramètres")

        # 1. On récupère tous les utilisateurs en base
        with Session(engine) as session:
            users = session.query(User).order_by(User.username).all()
            # On crée un dictionnaire : { "NomUtilisateur": ID }
            user_map = {u.username: u.id for u in users}

        # 2. Si la base est vide, on gère l'erreur
        if not user_map:
            st.error("Aucun utilisateur trouvé en base.")
            st.stop()

        # 3. La liste déroulante affiche les CLES (les noms)
        # On utilise st.session_state pour mémoriser le choix quand on change de page
        if "selected_username" not in st.session_state:
            # Par défaut, on prend le dernier utilisé ou le premier de la liste
            st.session_state["selected_username"] = list(user_map.keys())[0]

        # On s'assure que la valeur en session existe toujours dans la base (cas de suppression)
        if st.session_state["selected_username"] not in user_map:
            st.session_state["selected_username"] = list(user_map.keys())[0]

        selected_name = st.selectbox(
            "Sélectionner un utilisateur :",
            options=list(user_map.keys()),
            index=list(user_map.keys()).index(st.session_state["selected_username"]),
            key="user_selector",  # La clé met à jour automatiquement la session state
        )

        # 4. On récupère l'ID correspondant au nom choisi
        user_id = user_map[selected_name]

        # Mise à jour manuelle de la variable de session (double sécurité)
        st.session_state["selected_username"] = selected_name

        st.success(f"Connecté : **{selected_name}** (ID: {user_id})")

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
