import streamlit as st
import pandas as pd
from collections import Counter
from sqlalchemy.orm import Session
from src.database.connection import engine
from src.database.models import Recipe
from src.data_engineering.processor import DataPipeline

# Configuration de la page
st.set_page_config(page_title="Data Inspector", layout="wide")

st.title("🕵️ Data Engineering Inspector")
st.markdown("Utilisez cet outil pour auditer la qualité des données et identifier les mots 'polluants'.")

# --- 1. BARRE LATÉRALE (CONTROLS) ---
with st.sidebar:
    st.header("Paramètres d'Audit")
    
    # A. Contrôle du volume de données chargées
    db_limit = st.number_input(
        "Volume total à analyser (Lignes BDD)", 
        min_value=100, 
        max_value=5000, 
        value=500, 
        step=100,
        help="Augmenter ce nombre améliore la précision statistique mais ralentit le chargement."
    )
    
    # B. Contrôle de l'affichage
    display_limit = st.slider(
        "Lignes affichées dans le tableau comparatif", 
        min_value=10, 
        max_value=100, 
        value=50
    )

# --- 2. CHARGEMENT DES DONNÉES ---
@st.cache_data
def load_data(limit):
    """Charge les données brutes depuis la base SQL."""
    with Session(engine) as db:
        recipes = db.query(Recipe).limit(limit).all()
        data = [{
            'id': r.id, 
            'name': r.name,
            'raw_tags': r.tags, 
            'raw_ingredients': r.ingredients
        } for r in recipes]
    return pd.DataFrame(data)

df = load_data(db_limit)

# --- 3. PRÉPARATION DES DONNÉES ---
if not df.empty:
    df['combined_raw'] = df['raw_tags'].fillna('') + " " + df['raw_ingredients'].fillna('')
else:
    st.error("Aucune donnée trouvée. Avez-vous lancé le script d'initialisation ?")
    st.stop()

# --- 4. INSTANTIATION DU PIPELINE ---
with Session(engine) as db:
    pipeline = DataPipeline(db)

# --- 5. INTERFACE D'ANALYSE ---
col1, col2 = st.columns([1, 1])

# COLONNE GAUCHE : Visualisation unitaire
with col1:
    st.subheader("1. Comparaison Avant / Après")
    st.caption(f"Affichage des {display_limit} premières recettes")
    
    sample_df = df.head(display_limit).copy()
    sample_df['cleaned_output'] = sample_df['combined_raw'].apply(pipeline._clean_text)
    
    st.dataframe(
        sample_df[['name', 'combined_raw', 'cleaned_output']],
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Recette", width="small"),
            "combined_raw": st.column_config.TextColumn("Brut", width="small"),
            "cleaned_output": st.column_config.TextColumn("Nettoyé", width="medium"),
        }
    )

# COLONNE DROITE : Statistiques globales (MODIFIÉE)
with col2:
    st.subheader(f"2. Dictionnaire de Fréquence")
    st.caption(f"Comptage sur {len(df)} recettes. Cliquez sur la colonne 'Fréquence' pour trier.")
    
    with st.spinner("Analyse du corpus complet en cours..."):
        # Nettoyage de tout le corpus
        all_text = " ".join(df['combined_raw'].apply(pipeline._clean_text))
        words = all_text.split()
        word_counts = Counter(words)
        
    # Création d'un DataFrame complet avec TOUS les mots
    freq_df = pd.DataFrame.from_dict(word_counts, orient='index', columns=['Fréquence'])
    freq_df.index.name = 'Mot'
    freq_df = freq_df.reset_index()
    
    # Tri par défaut
    freq_df = freq_df.sort_values(by='Fréquence', ascending=False)
    
    # Affichage du tableau interactif complet
    st.dataframe(
        freq_df, 
        use_container_width=True,
        height=600, # Hauteur fixe pour scroller dedans
        hide_index=True
    )
    
    # Bouton d'export CSV (Outil de Data Scientist)
    csv = freq_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Télécharger la liste complète (CSV)",
        data=csv,
        file_name='corpus_frequency.csv',
        mime='text/csv',
    )

# --- 6. ZONE DE TEST ---
st.divider()
st.subheader("🛠 Zone de Test Unitaire")
test_input = st.text_input("Test manuel :", "1 cup of fresh tomatoes, diced and 2 oz of cheese")
if test_input:
    st.code(pipeline._clean_text(test_input))