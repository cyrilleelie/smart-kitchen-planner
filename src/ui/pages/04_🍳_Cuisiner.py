import streamlit as st
import requests

# Configuration de la page
st.set_page_config(page_title="Cuisiner", layout="wide")

# URL de l'API (Interne au conteneur Docker)
API_URL = "http://localhost:8000"

st.title("🍳 Le Frigo Magique")
st.markdown("""
**Qu'avez-vous dans votre frigo ?**
Dites-le à l'IA, et elle trouvera les recettes les plus pertinentes.
*L'algorithme ignore automatiquement les quantités et les mots inutiles.*
""")

# --- 1. BARRE DE RECHERCHE ---
col1, col2 = st.columns([3, 1])

with col1:
    # On met une valeur par défaut pour faciliter le test
    user_input = st.text_input(
        "Vos ingrédients (séparés par des virgules)", 
        placeholder="ex: chicken, cream, mushrooms, pasta",
        help="L'anglais fonctionne mieux pour l'instant (ex: tomato, beef, rice)."
    )

with col2:
    # Un peu de CSS pour aligner le bouton verticalement avec le champ texte
    st.write("") 
    st.write("")
    search_btn = st.button("🔍 Trouver une recette", use_container_width=True, type="primary")

# --- 2. LOGIQUE D'APPEL API ---
if search_btn and user_input:
    # Nettoyage basique côté front
    ingredients = [item.strip() for item in user_input.split(",") if item.strip()]
    
    if not ingredients:
        st.warning("Veuillez entrer au moins un ingrédient.")
    else:
        with st.spinner(f"🧠 Analyse de : {', '.join(ingredients)}..."):
            try:
                # Appel à votre API FastAPI
                response = requests.post(
                    f"{API_URL}/recommend",
                    json={"ingredients": ingredients}
                )
                
                if response.status_code == 200:
                    results = response.json()
                    
                    if not results:
                        st.info("🤷‍♂️ Aucune recette trouvée pour ces ingrédients précis.")
                    else:
                        st.success(f"✨ {len(results)} recettes trouvées !")
                        
                        # --- 3. AFFICHAGE DES RÉSULTATS ---
                        for recipe in results:
                            # On utilise un container stylisé pour chaque recette
                            with st.container():
                                st.subheader(f"🍲 {recipe['name'].title()}")
                                
                                # Métriques clés
                                c1, c2, c3 = st.columns([1, 1, 2])
                                c1.caption(f"⏱️ **{recipe['minutes']} min**")
                                c2.caption(f"🆔 **#{recipe['id']}**")
                                
                                # Affichage des tags principaux (nettoyage visuel)
                                raw_tags = recipe['tags'].replace("[", "").replace("]", "").replace("'", "")
                                tag_list = [t.strip() for t in raw_tags.split(",")]
                                c3.caption(f"🏷️ {', '.join(tag_list[:5])}...") # Top 5 tags
                                
                                # Description (si dispo)
                                if recipe.get('description'):
                                    st.write(recipe['description'])
                                
                                # Liste des ingrédients (Expandable pour ne pas polluer l'affichage)
                                with st.expander("Voir les ingrédients nécessaires"):
                                    raw_ings = recipe['ingredients'].replace("[", "").replace("]", "").replace("'", "")
                                    for ing in raw_ings.split(","):
                                        st.markdown(f"- {ing.strip()}")
                                
                                st.divider()

            except requests.exceptions.ConnectionError:
                st.error("🚨 Impossible de contacter l'API. Vérifiez que le backend tourne bien (localhost:8000).")
            except Exception as e:
                st.error(f"Une erreur technique est survenue : {e}")

elif search_btn:
    st.warning("Le frigo est vide ! (Champ vide)")