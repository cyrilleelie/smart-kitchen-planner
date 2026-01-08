import streamlit as st
import requests

st.set_page_config(page_title="Exploration", page_icon="🔥")

API_URL = "http://app:8000"

def main():
    st.title("🔥 Exploration Illimitée")
    st.caption("Découvrez tout le catalogue. L'IA vous propose uniquement ce que vous ne connaissez pas.")

    user_id = st.sidebar.number_input("ID Utilisateur", value=1, step=1)

    # --- GESTION ÉTAT ---
    if 'recipe_stack' not in st.session_state:
        st.session_state['recipe_stack'] = []
    
    if 'current_recipe' not in st.session_state:
        st.session_state['current_recipe'] = None

    # --- NOUVELLE FONCTION LOG ---
    def log_interaction(r_id, action_type):
        """Enregistre l'interaction en tâche de fond (Fire & Forget)"""
        try:
            # On ne bloque pas l'UI si le log échoue
            requests.post(f"{API_URL}/interactions", json={
                "user_id": user_id,
                "recipe_id": r_id,
                "type": action_type # view, rate, skip
            }, timeout=1) 
        except Exception:
            # En prod, on loggerait l'erreur, ici on passe silencieusement
            pass

    # --- FONCTIONS EXISTANTES ---
    def fetch_new_recipes():
        """Récupère un lot de nouvelles recettes fraîches"""
        try:
            resp = requests.get(f"{API_URL}/explore", params={"user_id": user_id, "limit": 5})
            if resp.status_code == 200:
                new_batch = resp.json()
                if new_batch:
                    st.session_state['recipe_stack'].extend(new_batch)
        except Exception as e:
            st.error(f"Erreur connexion : {e}")

    def load_next_from_stack():
        """Prend la prochaine recette de la pile et LOG LA VUE"""
        # Si la pile est vide, on va chercher du stock
        if not st.session_state['recipe_stack']:
            fetch_new_recipes()
        
        # Si après fetch c'est toujours vide, c'est fini
        if st.session_state['recipe_stack']:
            next_recipe = st.session_state['recipe_stack'].pop(0)
            st.session_state['current_recipe'] = next_recipe
            
            # --- LOG AUTO : VUE ---
            # On enregistre que l'utilisateur a vu cette recette
            log_interaction(next_recipe['id'], "view")
            
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
                    # 1. Envoi du feedback (Note explicite)
                    requests.post(f"{API_URL}/feedback", json={
                        "user_id": user_id, 
                        "recipe_id": recipe['id'], 
                        "rating": final_score
                    })
                    
                    # 2. Log de l'interaction (Pour le profilage)
                    log_interaction(recipe['id'], "rate")
                    
                    st.toast(f"Noté {final_score}/5 ⭐")
                except:
                    st.error("Erreur lors de la sauvegarde.")
                
                load_next_from_stack()

    def skip_recipe():
        recipe = st.session_state['current_recipe']
        if recipe and recipe != "DONE":
            # On log le skip, c'est une info précieuse (désintérêt)
            log_interaction(recipe['id'], "skip")
            
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
            
            # Nettoyage affichage tags
            try:
                # Si c'est une string (cas CSV raw), on clean. Si c'est déjà une liste (JSON), on join.
                if isinstance(recipe.get('tags'), str):
                    tags_clean = recipe.get('tags', '').replace('[','').replace(']','').replace("'", "").split(',')
                else:
                    tags_clean = recipe.get('tags', [])
                
                display_tags = tags_clean[:4] if tags_clean else []
                tags_str = ', '.join([str(t).strip() for t in display_tags])
            except:
                tags_str = "Général"

            st.caption(f"🏷️ {tags_str} | 🔥 {int(recipe.get('calories') or 0)} kcal")
            
            st.divider()

            # Ingrédients
            with st.expander("🛒 Voir les ingrédients", expanded=False):
                ing_raw = recipe.get('ingredients', '[]')
                # Gestion robuste str vs list
                if isinstance(ing_raw, str):
                    ing_clean = ing_raw.replace('[','').replace(']','').replace("'", "").split(',')
                elif isinstance(ing_raw, list):
                    ing_clean = ing_raw
                else:
                    ing_clean = []

                for ing in ing_clean: 
                    if str(ing).strip(): st.markdown(f"- {str(ing).strip()}")
            
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
                remaining = len(st.session_state['recipe_stack'])
                st.caption(f"En cache : {remaining} recettes prêtes")

    else:
        st.warning("Chargement...")
        load_next_from_stack()
        st.rerun()

if __name__ == "__main__":
    main()