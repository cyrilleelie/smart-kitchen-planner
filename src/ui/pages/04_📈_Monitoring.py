import streamlit as st
import streamlit.components.v1 as components
import os
import sys
import subprocess

# Configuration de la page
st.set_page_config(page_title="Monitoring Drift", page_icon="📈", layout="wide")

st.title("📈 Pilotage MLOps (Drift & Training)")

# --- CONFIGURATION ---
REPORT_BASE_DIR = "reports"
MONITOR_SCRIPT = "src/mlops/monitor_drift.py"
TRAIN_SCRIPT = "src/mlops/train_model.py"


# --- FONCTIONS ---


def run_analysis_process(model_type):
    """Exécute le script et retourne le résultat brut"""
    cmd = [sys.executable, MONITOR_SCRIPT, "--model", model_type]
    return subprocess.run(cmd, capture_output=True, text=True)


def run_training_process(model_type):
    """Exécute le training et retourne le résultat brut"""
    pipeline_arg = "rf" if model_type == "rf" else "svd"
    cmd = [sys.executable, TRAIN_SCRIPT, "--pipeline", pipeline_arg]
    return subprocess.run(cmd, capture_output=True, text=True)


def get_list_of_reports(model_type):
    target_dir = os.path.join(REPORT_BASE_DIR, model_type)
    if not os.path.exists(target_dir):
        return []
    files = [
        f
        for f in os.listdir(target_dir)
        if f.startswith("drift_report_") and f.endswith(".html")
    ]
    files.sort(reverse=True)
    return files


# --- VARIABLES DE SESSION (Pour garder l'état après le clic) ---
if "last_action_result" not in st.session_state:
    st.session_state["last_action_result"] = None

# --- BARRE LATÉRALE ---
with st.sidebar:
    st.header("🎮 Actions MLOps")

    # SÉLECTEUR DE MODÈLE
    selected_model = st.selectbox(
        "Sélectionner le modèle :",
        ["Random Forest (Content-Based)", "SVD (Collaborative Filtering)"],
    )

    # Map selection to code
    model_code = "rf" if "Random Forest" in selected_model else "svd"
    st.info(f"Modèle actif : **{model_code.upper()}**")

    # Bouton Analyse
    if st.button("🔍 Analyser le Drift", use_container_width=True):
        with st.spinner(f"🕵️‍♂️ Analyse en cours ({model_code})..."):
            res = run_analysis_process(model_code)
            # On stocke le résultat et le type d'action
            st.session_state["last_action_result"] = {"type": "analysis", "data": res}

    # Bouton Entraînement
    if st.button("🏋️‍♂️ Lancer un Entraînement", type="primary", use_container_width=True):
        with st.spinner(f"🏋️‍♂️ Entraînement en cours ({model_code})..."):
            res = run_training_process(model_code)
            st.session_state["last_action_result"] = {"type": "training", "data": res}

    st.divider()

    st.header("📚 Historique")
    report_files = get_list_of_reports(model_code)

    selected_file = None
    if report_files:
        file_options = {
            f: f.replace("drift_report_", "").replace(".html", "").replace("_", " à ")
            for f in report_files
        }
        selected_file = st.selectbox(
            "Choisir un rapport archivé :",
            options=report_files,
            format_func=lambda x: file_options[x],
        )
    else:
        st.info(f"Aucun historique pour {model_code}.")


# --- ZONE D'AFFICHAGE DES MESSAGES (AU CENTRE) ---
# C'est ici que la magie opère : on lit la variable de session pour afficher le message
result_state = st.session_state["last_action_result"]

if result_state:
    res = result_state["data"]
    action_type = result_state["type"]

    st.divider()

    if action_type == "analysis":
        if res.returncode == 0:
            st.success("✅ **Analyse terminée :** Le modèle est stable (Pas de drift).")
        elif res.returncode == 1:
            st.error(
                "⚠️ **ALERTE DRIFT :** La distribution des données a changé significativement."
            )
            with st.expander("Voir les détails techniques"):
                st.code(res.stdout)
        elif res.returncode == 2:
            st.warning(
                "💤 **Analyse ignorée :** Pas assez de nouvelles données ou pas de référence."
            )
            with st.expander("Voir les logs"):
                st.code(res.stdout)
        else:
            st.error("❌ Erreur technique.")
            st.code(res.stderr)

    elif action_type == "training":
        if res.returncode == 0:
            st.success(
                "✅ **Entraînement terminé :** Nouveau modèle sauvegardé dans MLflow !"
            )
            st.balloons()
            with st.expander("Logs d'entraînement"):
                st.code(res.stdout)
        else:
            st.error("❌ Échec de l'entraînement.")
            st.code(res.stderr)

    # Petit bouton pour nettoyer l'affichage
    if st.button("Fermer le message"):
        st.session_state["last_action_result"] = None
        st.rerun()

# --- ZONE D'AFFICHAGE DU RAPPORT ---

if selected_file:
    # Affichage d'un rapport historique
    file_path = os.path.join(REPORT_BASE_DIR, model_code, selected_file)

    st.divider()
    # Safe checks
    if os.path.exists(file_path):
        display_date = (
            selected_file.replace("drift_report_", "")
            .replace(".html", "")
            .replace("_", " à ")
        )
        st.subheader(f"📄 Rapport archivé du {display_date} ({model_code.upper()})")

        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        st.download_button("📥 Télécharger", html_content, selected_file, "text/html")
        components.html(html_content, height=1000, scrolling=True)
    else:
        st.error("Fichier introuvable.")

# Optional: Default to latest if available (and not just ran an action that failed)
elif not result_state and report_files:
    # Show latest by default
    latest_file = report_files[0]
    file_path = os.path.join(REPORT_BASE_DIR, model_code, latest_file)
    if os.path.exists(file_path):
        st.divider()
        st.info(
            f"Visualisation du dernier rapport disponible pour {model_code.upper()}."
        )
        with open(file_path, "r", encoding="utf-8") as f:
            components.html(f.read(), height=1000, scrolling=True)
