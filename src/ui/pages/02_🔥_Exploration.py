import streamlit as st
import requests
from src.ui.config import API_URL

st.set_page_config(page_title="Exploration", page_icon="🔥")

def main():
    st.title("🔥 Exploration Illimitée")
    st.caption("Notez des recettes pour affiner votre profil.")

    user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)

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