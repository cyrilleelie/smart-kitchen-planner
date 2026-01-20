import streamlit as st
import requests
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import User

# Configuration de la page
st.set_page_config(page_title="Context Recommender", page_icon="🍽️", layout="wide")

API_URL = "http://localhost:8000/recommend"

st.title("🍽️ Recommandation Contextuelle")
st.markdown(
    """
Cette interface interroge l'API intelligente. Le modèle ne se base pas seulement sur les goûts de l'utilisateur, 
mais adapte ses suggestions en fonction du **Moment de la journée** et de la **Saison**.
"""
)

# --- COLONNE DE GAUCHE : CONTRÔLES ---
with st.sidebar:
    st.header("👤 Profil & Contexte")

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

    st.divider()

    # 2. Sélection Moment (Mapping vers 0, 1, 2, 3)
    meal_options = {
        "Matin (Petit-déj)": 0,
        "Midi (Déjeuner)": 1,
        "Soir (Dîner)": 2,
        "Snack / Goûter": 3,
    }
    selected_meal_label = st.radio(
        "🕒 Moment du repas", list(meal_options.keys()), index=1
    )
    meal_code = meal_options[selected_meal_label]

    st.divider()

    # 3. Sélection Saison (Mapping vers 0, 1, 2, 3)
    season_options = {"❄️ Hiver": 0, "🌸 Printemps": 1, "☀️ Été": 2, "🍂 Automne": 3}
    selected_season_label = st.selectbox(
        "📅 Saison", list(season_options.keys()), index=0
    )
    season_code = season_options[selected_season_label]

    st.divider()

    # Bouton d'action
    launch_btn = st.button("✨ Générer les suggestions", type="primary")

# --- CORPS PRINCIPAL : RÉSULTATS ---

if launch_btn:
    # Préparation de la requête
    payload = {"user_id": user_id, "meal_type": meal_code, "season": season_code}

    try:
        with st.spinner("🧠 Interrogation du modèle IA..."):
            response = requests.post(API_URL, json=payload)

        if response.status_code == 200:
            recommendations = response.json()

            if not recommendations:
                st.warning("Aucune recommandation trouvée (ou modèle non chargé).")
            else:
                st.success(
                    f"Top 5 Recettes pour **{selected_meal_label}** en **{selected_season_label}**"
                )

                # Affichage sous forme de cartes
                cols = st.columns(len(recommendations))

                for idx, rec in enumerate(recommendations):
                    with cols[idx]:
                        # Score visuel (étoiles ou barre)
                        score_val = rec["score"]
                        normalized_score = min(
                            1.0, max(0.0, (score_val - 1) / 4)
                        )  # Normalisation 1-5 vers 0-1

                        st.metric(label=f"Rank #{idx+1}", value=f"{score_val}/5")
                        st.progress(normalized_score)

                        st.subheader(rec["name"])
                        st.caption(
                            f"⏱️ {rec['minutes']} min | 🔥 {rec.get('calories', '?')} kcal"
                        )

                        # Petit badge pour expliquer pourquoi (Fake explanation pour l'UI)
                        if meal_code == 3:
                            st.info("Snack time! 🍪")
                        elif season_code == 0 and "soup" in rec["name"].lower():
                            st.info("Winter Warmer ❄️")
                        elif score_val >= 4.5:
                            st.success("Super Match! ⭐")

        else:
            st.error(f"Erreur API : {response.status_code}")
            st.code(response.text)

    except Exception as e:
        st.error(f"Impossible de contacter l'API : {e}")

else:
    # État initial (Message d'accueil)
    st.info(
        "👈 Configurez le contexte dans la barre latérale et cliquez sur 'Générer'."
    )
