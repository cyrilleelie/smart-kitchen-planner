import streamlit as st
import requests
from sqlalchemy.sql.expression import func
import sys
import os

# Fix du Path pour Docker
sys.path.append("/app")

from src.database.connection import get_db
from src.database.models import Recipe, Interaction

st.set_page_config(page_title="Mode Exploration", page_icon="🔥")
API_URL = "http://localhost:8000"

def main():
    st.title("🔥 Mode Exploration")
    st.markdown("Notez des recettes pour affiner votre profil IA !")

    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = 1
    user_id = st.session_state['user_id']
    
    # Connexion BDD
    try:
        db = next(get_db())
    except Exception as e:
        st.error(f"Erreur BDD: {e}")
        return

    # --- 1. CHARGER UNE NOUVELLE RECETTE (Si besoin) ---
    if 'current_recipe' not in st.session_state:
        # On exclut les recettes déjà notées
        rated_subquery = db.query(Interaction.recipe_id).filter(Interaction.user_id == user_id)
        
        # Tirage au sort d'une recette NON notée
        recipe = db.query(Recipe)\
            .filter(Recipe.id.notin_(rated_subquery))\
            .order_by(func.random())\
            .first()
        
        if recipe:
            # On stocke en session
            st.session_state['current_recipe'] = {
                "id": recipe.id,
                "name": recipe.name,
                "description": recipe.description,
                "minutes": recipe.minutes,
                "tags": recipe.tags
            }
        else:
            st.success("🎉 Vous avez fait le tour de toutes les recettes !")
            if st.button("Recommencer à zéro (Reset)"):
                # Optionnel : logique de reset
                pass
            return

    # --- 2. AFFICHAGE DE LA CARTE ---
    rec = st.session_state['current_recipe']
    
    with st.container(border=True):
        st.header(rec['name'].title())
        
        # Tags
        tags = str(rec['tags']).replace('[','').replace(']','').replace("'", "")
        st.caption(f"⏱️ {rec['minutes']} min • 🏷️ {tags[:100]}...")
        
        if rec['description']:
            st.info(rec['description'])
        
        st.divider()
        st.subheader("Votre avis ?")
        
        # --- 3. LOGIQUE AUTOMATIQUE ---
        
        # Cette fonction est appelée AUTOMATIQUEMENT dès qu'on touche aux étoiles
        def submit_rating():
            # On récupère la valeur via la clé dynamique
            widget_key = f"rate_{rec['id']}"
            val = st.session_state.get(widget_key)
            
            if val is not None:
                # 1. Envoi API
                try:
                    score = val + 1 # 0-4 -> 1-5
                    requests.post(f"{API_URL}/feedback", json={
                        "user_id": user_id,
                        "recipe_id": rec['id'],
                        "rating": score
                    })
                    st.toast(f"Avis enregistré ({score}/5) !", icon="✅")
                except Exception as e:
                    st.error(f"Erreur API : {e}")
            
            # 2. NETTOYAGE POUR LE PASSAGE AUTOMATIQUE
            # On supprime la recette courante de la mémoire
            if 'current_recipe' in st.session_state:
                del st.session_state['current_recipe']
            
            # Pas besoin de st.rerun(), le callback on_change le fait implicitement
        
        # --- WIDGET ÉTOILES ---
        # TRUC CLÉ : key=f"rate_{rec['id']}"
        # Comme l'ID change à chaque recette, Streamlit crée un NOUVEAU widget à chaque fois (donc vide)
        st.feedback(
            "stars", 
            key=f"rate_{rec['id']}", 
            on_change=submit_rating
        )
        
        st.markdown("---")
        
        # Bouton pour passer sans noter
        if st.button("Passer cette recette ➡️", use_container_width=True):
            del st.session_state['current_recipe']
            st.rerun()

if __name__ == "__main__":
    main()