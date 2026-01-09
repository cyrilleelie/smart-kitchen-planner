import streamlit as st
import streamlit.components.v1 as components
import os
import sys
import subprocess
from datetime import datetime

# Configuration de la page
st.set_page_config(
    page_title="Monitoring Drift",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Pilotage MLOps (Drift & Training)")

# --- CONFIGURATION ---
REPORT_DIR = "reports"
MONITOR_SCRIPT = "src/mlops/monitor_drift.py"
TRAIN_SCRIPT = "src/mlops/train_model.py"

if not os.path.exists(REPORT_DIR):
    os.makedirs(REPORT_DIR)

# --- FONCTIONS ---

def run_analysis_process():
    """Exécute le script et retourne le résultat brut"""
    return subprocess.run(
        [sys.executable, MONITOR_SCRIPT],
        capture_output=True,
        text=True
    )

def run_training_process():
    """Exécute le training et retourne le résultat brut"""
    return subprocess.run(
        [sys.executable, TRAIN_SCRIPT],
        capture_output=True,
        text=True
    )

def get_list_of_reports():
    if not os.path.exists(REPORT_DIR):
        return []
    files = [f for f in os.listdir(REPORT_DIR) if f.startswith("drift_report_20") and f.endswith(".html")]
    files.sort(reverse=True)
    return files

# --- VARIABLES DE SESSION (Pour garder l'état après le clic) ---
if 'last_action_result' not in st.session_state:
    st.session_state['last_action_result'] = None

# --- BARRE LATÉRALE ---
with st.sidebar:
    st.header("🎮 Actions MLOps")
    
    # Bouton Analyse
    if st.button("🔍 Analyser le Drift", use_container_width=True):
        with st.spinner("🕵️‍♂️ Analyse en cours..."):
            res = run_analysis_process()
            # On stocke le résultat et le type d'action
            st.session_state['last_action_result'] = {"type": "analysis", "data": res}
            
    # Bouton Entraînement    
    if st.button("🏋️‍♂️ Lancer un Entraînement", type="primary", use_container_width=True):
        with st.spinner("🏋️‍♂️ Entraînement en cours..."):
            res = run_training_process()
            st.session_state['last_action_result'] = {"type": "training", "data": res}

    st.divider()
    
    st.header("📚 Historique")
    report_files = get_list_of_reports()
    
    selected_file = None
    if report_files:
        file_options = {
            f: f.replace("drift_report_", "").replace(".html", "").replace("_", " à ").replace("-", "/") 
            for f in report_files
        }
        selected_file = st.selectbox(
            "Choisir un rapport archivé :",
            options=report_files,
            format_func=lambda x: file_options[x]
        )
    else:
        st.info("Aucun historique disponible.")


# --- ZONE D'AFFICHAGE DES MESSAGES (AU CENTRE) ---
# C'est ici que la magie opère : on lit la variable de session pour afficher le message
result_state = st.session_state['last_action_result']

if result_state:
    res = result_state["data"]
    action_type = result_state["type"]
    
    st.divider()
    
    if action_type == "analysis":
        if res.returncode == 0:
            st.success("✅ **Analyse terminée :** Le modèle est stable (Pas de drift).")
        elif res.returncode == 1:
            st.error("⚠️ **ALERTE DRIFT :** La distribution des données a changé significativement.")
            with st.expander("Voir les détails techniques"):
                st.code(res.stdout)
        elif res.returncode == 2:
            st.warning("💤 **Analyse ignorée :** Pas assez de nouvelles données.")
            st.info("Il faut plus de 50 nouvelles interactions depuis le dernier entraînement pour lancer une analyse fiable.")
        else:
            st.error("❌ Erreur technique.")
            st.code(res.stderr)
            
    elif action_type == "training":
        if res.returncode == 0:
            st.success("✅ **Entraînement terminé :** Nouveau modèle sauvegardé dans MLflow !")
            st.balloons()
            with st.expander("Logs d'entraînement"):
                st.code(res.stdout)
        else:
            st.error("❌ Échec de l'entraînement.")
            st.code(res.stderr)
            
    # Petit bouton pour nettoyer l'affichage
    if st.button("Fermer le message"):
        st.session_state['last_action_result'] = None
        st.rerun()

# --- ZONE D'AFFICHAGE DU RAPPORT ---

if selected_file:
    # Affichage d'un rapport historique
    file_path = os.path.join(REPORT_DIR, selected_file)
    display_date = selected_file.replace("drift_report_", "").replace(".html", "").replace("_", " à ")
    
    st.divider()
    st.subheader(f"📄 Rapport archivé du {display_date}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    st.download_button("📥 Télécharger", html_content, selected_file, "text/html")
    components.html(html_content, height=1000, scrolling=True)

elif os.path.exists(os.path.join(REPORT_DIR, "drift_report_latest.html")):
    # Affichage du dernier rapport par défaut
    if not result_state: # On évite de surcharger si on vient d'afficher un message
        st.divider()
        st.info("Visualisation du dernier rapport disponible (Latest).")
        with open(os.path.join(REPORT_DIR, "drift_report_latest.html"), 'r', encoding='utf-8') as f:
            components.html(f.read(), height=1000, scrolling=True)