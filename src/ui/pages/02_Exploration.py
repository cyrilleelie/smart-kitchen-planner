import streamlit as st
import requests

st.set_page_config(page_title="Exploration", page_icon="🔥")

API_URL = "http://app:8000"

def main():
    st.title("🔥 Exploration Illimitée")
    st.caption("Découvrez tout le catalogue. L'IA vous propose uniquement ce que vous ne connaissez pas.")

    user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)

    # --- GESTION ÉTAT ---
    # On stocke une pile (stack) de recettes pour éviter d'appeler l'API à chaque clic
    if 'recipe_stack' not in st.session_state:
        st.session_state['recipe_stack'] = []
    
    if 'current_recipe' not in st.session_state:
        st.session_state['current_recipe'] = None

    # --- FONCTIONS ---
    def fetch_new_recipes():
        """Récupère un lot de nouvelles recettes fraîches"""
        try:
            # On en demande 5 d'un coup pour fluidifier l'expérience
            resp = requests.get(f"{API_URL}/explore", params={"user_id": user_id, "limit": 5})
            if resp.status_code == 200:
                new_batch = resp.json()
                if new_batch:
                    # On ajoute le batch à notre pile locale
                    st.session_state['recipe_stack'].extend(new_batch)
        except Exception as e:
            st.error(f"Erreur connexion : {e}")

    def load_next_from_stack():
        """Prend la prochaine recette de la pile"""
        # Si la pile est vide, on va chercher du stock
        if not st.session_state['recipe_stack']:
            fetch_new_recipes()
        
        # Si après fetch c'est toujours vide, c'est qu'on a TOUT noté !
        if st.session_state['recipe_stack']:
            st.session_state['current_recipe'] = st.session_state['recipe_stack'].pop(0)
        else:
            st.session_state['current_recipe'] = "DONE"

    # --- CALLBACKS ---
    def submit_rating():
        recipe = st.session_state['current_recipe']
        if recipe and recipe != "DONE":
            # Récupération note
            widget_key = f"rating_{recipe['id']}"
            val = st.session_state.get(widget_key)
            
            if val is not None:
                final_score = val + 1
                
                # Envoi asynchrone (on n'attend pas la réponse pour changer l'UI)
                try:
                    requests.post(f"{API_URL}/feedback", json={
                        "user_id": user_id, 
                        "recipe_id": recipe['id'], 
                        "rating": final_score
                    })
                    st.toast(f"Noté {final_score}/5 ⭐")
                except:
                    pass
                
                # Suivant !
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
        st.success("🏆 INCROYABLE ! Vous avez noté l'intégralité de la base de données !")
        st.info("Revenez quand nous aurons ajouté de nouvelles recettes.")
        if st.button("Recommencer (Reset Stack)"):
            st.session_state['recipe_stack'] = []
            st.session_state['current_recipe'] = None
            st.rerun()

    elif recipe:
        with st.container(border=True):
            # Header
            st.header(recipe['name'])
            tags_clean = recipe.get('tags', '').replace('[','').replace(']','').replace("'", "").split(',')
            st.caption(f"🏷️ {', '.join(tags_clean[:4])} | 🔥 {int(recipe.get('calories', 0))} kcal")
            
            st.divider()

            # Ingrédients
            with st.expander("🛒 Voir les ingrédients", expanded=False):
                ing_raw = recipe.get('ingredients', '[]')
                if isinstance(ing_raw, str):
                    ing_clean = ing_raw.replace('[','').replace(']','').replace("'", "").split(',')
                    for ing in ing_clean: 
                        if ing.strip(): st.markdown(f"- {ing.strip()}")
            
            st.markdown("#### Notez ce plat :")
            
            # Notation avec Auto-Switch
            st.feedback(
                "stars", 
                key=f"rating_{recipe['id']}", 
                on_change=submit_rating
            )
            
            st.markdown("---")
            
            # Bouton Passer
            c1, c2 = st.columns([1, 4])
            with c1:
                st.button("Passer ⏭️", on_click=skip_recipe, use_container_width=True)
            with c2:
                # Debug info (optionnel, pour voir le stock)
                remaining = len(st.session_state['recipe_stack'])
                st.caption(f"En cache : {remaining} recettes prêtes")

    else:
        st.warning("Chargement...")
        load_next_from_stack()
        st.rerun()

if __name__ == "__main__":
    main()