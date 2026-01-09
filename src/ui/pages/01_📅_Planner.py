import streamlit as st
import requests
from src.ui.config import API_URL
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import User

st.set_page_config(page_title="Planner Contextuel", page_icon="📅", layout="wide")

# Mappings pour l'interface
MEAL_TYPES = {
    "🥐 Petit-déjeuner": 0,
    "🥗 Déjeuner": 1,
    "🍲 Dîner": 2,
    "🍪 Snack": 3
}

SEASONS = {
    "❄️ Hiver": 0,
    "🌸 Printemps": 1,
    "☀️ Été": 2,
    "🍂 Automne": 3
}

def main():
    st.title("📅 Générateur de Menu Intelligent")
    st.caption("Un planning adapté à vos goûts, à la saison et au moment de la journée.")

    # --- BARRE LATÉRALE ---
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
            key="user_selector" # La clé met à jour automatiquement la session state
        )

        # 4. On récupère l'ID correspondant au nom choisi
        user_id = user_map[selected_name]
        
        # Mise à jour manuelle de la variable de session (double sécurité)
        st.session_state["selected_username"] = selected_name
        
        st.success(f"Connecté : **{selected_name}** (ID: {user_id})")
        st.divider()
        
        days = st.slider("Durée (Jours)", 2, 7, 7)
        
        # Sélection des repas (Multiselect)
        selected_meal_labels = st.multiselect(
            "Quels repas planifier ?",
            options=list(MEAL_TYPES.keys()),
            default=["🥗 Déjeuner", "🍲 Dîner"]
        )
        
        # Sélection de la saison
        season_label = st.selectbox("Saison actuelle", list(SEASONS.keys()), index=0)
        
        st.divider()
        
        generate_btn = st.button("✨ Générer le planning", type="primary")

    # --- LOGIQUE ---
    if generate_btn:
        if not selected_meal_labels:
            st.error("Veuillez sélectionner au moins un type de repas.")
            return

        # Conversion des choix en codes (0, 1, 2, 3)
        selected_meal_codes = [MEAL_TYPES[label] for label in selected_meal_labels]
        # On trie pour que l'affichage soit logique (Matin avant Soir)
        selected_meal_codes.sort()
        
        season_code = SEASONS[season_label]

        with st.spinner("🤖 L'IA compose votre semaine sur mesure..."):
            try:
                # Construction du payload conforme au nouveau MenuRequest
                payload = {
                    "user_id": user_id,
                    "days": days,
                    "selected_meals": selected_meal_codes,
                    "season": season_code,
                    "target_calories": 600 # Valeur indicative
                }
                
                response = requests.post(f"{API_URL}/generate-planning", json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    plan = data.get("plan", [])
                    stats = data.get("stats", {})
                    
                    if not plan:
                        st.warning("⚠️ L'IA n'a pas trouvé de recettes correspondantes.")
                    else:
                        st.success("✅ Menu prêt !")
                        
                        # KPIs
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Moyenne Kcal/Repas", f"{int(stats.get('average_calories', 0))}")
                        k2.metric("Score Match IA", f"{float(stats.get('average_match_score', 0)):.2f}/5")
                        k3.metric("Recettes prévues", len(plan))
                        
                        st.divider()
                        
                        # --- AFFICHAGE DU PLANNING ---
                        # Organisation des données par Jour
                        schedule = {}
                        for item in plan:
                            schedule.setdefault(item['day'], []).append(item)

                        # Affichage en colonnes
                        cols = st.columns(len(schedule))
                        
                        # Mapping inverse pour l'affichage (0 -> Petit-déj)
                        CODE_TO_LABEL = {v: k.split(" ")[1] for k, v in MEAL_TYPES.items()}

                        for idx, day in enumerate(sorted(schedule.keys())):
                            with cols[idx]:
                                st.markdown(f"<div style='text-align:center; background:#e0e7ff; padding:8px; border-radius:8px; margin-bottom:10px;'><b>J{day}</b></div>", unsafe_allow_html=True)
                                
                                items_of_day = schedule[day]
                                # Il faut mapper les items aux bons repas. 
                                # L'API renvoie les items dans l'ordre de la boucle des repas.
                                
                                for i, meal in enumerate(items_of_day):
                                    # On essaie de deviner le label du repas via l'index
                                    # Si on a demandé [Midi, Soir], le 1er est Midi, le 2eme est Soir
                                    current_meal_code = selected_meal_codes[i % len(selected_meal_codes)]
                                    meal_name = CODE_TO_LABEL[current_meal_code]
                                    
                                    with st.container(border=True):
                                        st.caption(f"{meal_name}")
                                        st.markdown(f"**{meal['recipe_name']}**")
                                        st.markdown(f"⏱️ {meal['time']} min | 🔥 {int(meal['calories'])}")
                                        
                                        # Score & Algo Tag
                                        if "Découverte" in meal.get("tags", []):
                                            st.markdown("🎲 <span style='color:#6f42c1'><b>Découverte</b></span>", unsafe_allow_html=True)
                                        else:
                                            st.markdown(f"⭐ **{meal['match_score']:.2f}** / 5")
                                        
                                        st.divider()
                                        
                                        # --- AJOUT DES LISTES DÉPLIANTES ---
                                        
                                        # 1. Tags (Utile pour comprendre le contexte "winter", "breakfast"...)
                                        with st.expander("🏷️ Tags"):
                                            # On affiche les tags sous forme de petites puces ou texte brut
                                            st.markdown(", ".join([f"`{t}`" for t in meal.get('recipe_tags', [])]))
                                            
                                        # 2. Ingrédients
                                        with st.expander("🛒 Ingrédients"):
                                            for ing in meal.get('ingredients', []):
                                                st.markdown(f"- {ing}")

                else:
                    st.error(f"Erreur API: {response.status_code}")
                    st.json(response.json())
            
            except Exception as e:
                st.error(f"Erreur technique: {e}")

if __name__ == "__main__":
    main()