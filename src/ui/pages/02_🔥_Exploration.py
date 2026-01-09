import streamlit as st
import requests
from src.ui.config import API_URL
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import User

st.set_page_config(page_title="Exploration", page_icon="🔥")

def main():
    st.title("🔥 Exploration Illimitée")
    st.caption("Notez des recettes pour affiner votre profil.")

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

    # --- GESTION ÉTAT ---
    if 'recipe_stack' not in st.session_state:
        st.session_state['recipe_stack'] = []
    
    if 'current_recipe' not in st.session_state:
        st.session_state['current_recipe'] = None

    # --- FONCTIONS ---
    def fetch_new_recipes():
        """Récupère un lot de nouvelles recettes fraîches"""
        try:
            resp = requests.get(f"{API_URL}/explore", params={"user_id": user_id, "limit": 5})
            if resp.status_code == 200:
                new_batch = resp.json()
                if new_batch:
                    st.session_state['recipe_stack'].extend(new_batch)
        except Exception:
            st.error("Impossible de joindre l'API.")

    def load_next_from_stack():
        """Prend la prochaine recette de la pile"""
        if not st.session_state['recipe_stack']:
            fetch_new_recipes()
        
        if st.session_state['recipe_stack']:
            st.session_state['current_recipe'] = st.session_state['recipe_stack'].pop(0)
        else:
            st.session_state['current_recipe'] = "DONE"

    # --- CALLBACKS ---
    def submit_rating():
        recipe = st.session_state['current_recipe']
        if recipe and recipe != "DONE":
            widget_key = f"rating_{recipe['id']}"
            val = st.session_state.get(widget_key)
            
            if val is not None:
                final_score = val + 1
                try:
                    requests.post(f"{API_URL}/feedback", json={
                        "user_id": user_id, 
                        "recipe_id": recipe['id'], 
                        "rating": final_score
                    })
                    st.toast(f"Noté {final_score}/5 ⭐")
                except:
                    st.error("Erreur sauvegarde.")
                
                load_next_from_stack()

    def skip_recipe():
        st.toast("Passé ⏭️")
        load_next_from_stack()

    # --- INITIALISATION ---
    if st.session_state['current_recipe'] is None:
        load_next_from_stack()

    # --- AFFICHAGE ---
    recipe = st.session_state['current_recipe']

    if recipe == "DONE":
        st.balloons()
        st.success("Bravo ! Vous avez fait le tour des suggestions du moment.")
        if st.button("Recharger"):
            st.session_state['recipe_stack'] = []
            st.session_state['current_recipe'] = None
            st.rerun()

    elif recipe:
        with st.container(border=True):
            st.header(recipe['name'])
            st.caption(f"⏱️ {recipe.get('minutes')} min | 🔥 {int(recipe.get('calories') or 0)} kcal")
            st.divider()

            # Ingrédients avec nettoyage simple
            with st.expander("🛒 Voir les ingrédients"):
                ing_raw = recipe.get('ingredients', '[]')
                # Nettoyage visuel rapide
                clean_ing = str(ing_raw).replace("[", "").replace("]", "").replace("'", "")
                for ing in clean_ing.split(","):
                    if ing.strip(): st.markdown(f"- {ing.strip()}")

            st.markdown("#### Votre avis ?")
            st.feedback("stars", key=f"rating_{recipe['id']}", on_change=submit_rating)
            
            st.markdown("---")
            st.button("Passer ⏭️", on_click=skip_recipe, use_container_width=True)

    else:
        st.info("Chargement des recettes...")
        load_next_from_stack()
        st.rerun()

if __name__ == "__main__":
    main()