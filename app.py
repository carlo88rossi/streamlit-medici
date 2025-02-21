import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re
import pytz
import math
import streamlit.components.v1 as components

# Imposta il fuso orario desiderato (es. "Europe/Rome")
timezone = pytz.timezone("Europe/Rome")

# Configurazione della pagina
st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")

# CSS personalizzato: design pulito e leggibile
st.markdown(
    """
    <style>
    /* Sfondo e colori base */
    body {
        background-color: #f8f9fa;
        color: #212529;
    }
    [data-testid="stAppViewContainer"] {
        background-color: #f8f9fa;
    }
    /* Titolo */
    h1 {
        font-family: 'Helvetica Neue', sans-serif;
        font-size: 2.5rem;
        text-align: center;
        color: #007bff;
        margin-bottom: 1.5rem;
    }
    /* Pulsanti */
    div.stButton > button {
        background-color: #007bff;
        color: #ffffff;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1rem;
        font-size: 1rem;
        transition: background-color 0.3s ease;
    }
    div.stButton > button:hover {
        background-color: #0056b3;
    }
    /* File uploader */
    .stFileUploader {
        background-color: #ffffff;
        border: 1px solid #ced4da;
        border-radius: 4px;
        padding: 0.75rem;
    }
    /* Widget di input e selezione */
    .css-1d391kg, .stSelectbox, .stTextInput input {
        font-size: 1rem;
        padding: 0.5rem;
    }
    /* Regole per dispositivi mobili */
    @media only screen and (max-width: 600px) {
        h1 {
            font-size: 2rem;
        }
        div.stButton > button {
            width: 100% !important;
            margin-bottom: 0.5rem;
        }
    }
    /* Personalizzazione AgGrid */
    .ag-root-wrapper {
        border: 1px solid #dee2e6 !important;
        border-radius: 4px;
        overflow: hidden;
    }
    .ag-header-cell-label {
        font-weight: bold;
        color: #343a40;
    }
    .ag-row {
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True
)

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# --- SEZIONE: Geolocalizzazione (visualizzazione solo) ---
st.markdown("### Geolocalizzazione")
geolocalizzazione_html = """
<div id="geolocation">
  <p>Attendi il recupero della posizione...</p>
</div>
<script>
if ("geolocation" in navigator) {
  navigator.geolocation.getCurrentPosition(
    function(position) {
      document.getElementById("geolocation").innerHTML = 
        "<p><strong>Latitudine:</strong> " + position.coords.latitude + "</p>" +
        "<p><strong>Longitudine:</strong> " + position.coords.longitude + "</p>";
    },
    function(error) {
      document.getElementById("geolocation").innerHTML = "<p>Impossibile ottenere la posizione: " + error.message + "</p>";
    }
  );
} else {
  document.getElementById("geolocation").innerHTML = "<p>Geolocalizzazione non supportata dal browser.</p>";
}
</script>
"""
components.html(geolocalizzazione_html, height=150)

# Definizione delle specializzazioni di default ed extra
default_spec = ["MMG", "PED"]
spec_extra = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

# --- DEFINIZIONE FUNZIONI UTILI (Parsing orari e distanza) ---
def parse_interval(cell_value):
    """Parsa un valore tipo '08:00-12:00' e restituisce (start_time, end_time) come oggetti time."""
    if pd.isna(cell_value):
        return None, None
    cell_value = str(cell_value).strip()
    m = re.match(r'(\d{1,2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}(?::\d{2})?)', cell_value)
    if not m:
        return None, None
    start_str, end_str = m.groups()
    fmt = "%H:%M" if ":" in start_str else "%H"
    try:
        start_time = datetime.datetime.strptime(start_str, fmt).time()
        end_time = datetime.datetime.strptime(end_str, fmt).time()
        return start_time, end_time
    except:
        return None, None

def interval_covers(cell_value, custom_start, custom_end):
    """Controlla se l'intervallo orario in cell_value copre completamente [custom_start, custom_end]."""
    start_time, end_time = parse_interval(cell_value)
    if start_time is None or end_time is None:
        return False
    return (start_time <= custom_start) and (end_time >= custom_end)

def haversine(lat1, lon1, lat2, lon2):
    """Calcola la distanza in km tra due punti definiti da latitudine e longitudine usando la formula di Haversine."""
    r = 6371.0  # raggio medio della Terra in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return r * c

# Funzione per azzerare i filtri: rimuoviamo le chiavi dal session_state
def azzera_filtri():
    keys_to_clear = [
        "filtro_spec",
        "filtro_target",
        "filtro_visto",
        "giorno_scelto",
        "fascia_oraria",
        "provincia_scelta",
        "microarea_scelta",
        "search_query",
        "custom_start",
        "custom_end",
        "ciclo_scelto",
        "filtro_frequenza"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    try:
        st.experimental_rerun()
    except AttributeError:
        st.warning("Ricarica manualmente la pagina.")

st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# --- PULSANTI PER SPECIALISTI ---
if st.button("Specialisti 👨‍⚕️👩‍⚕️"):
    current_selection = st.session_state.get("filtro_spec", default_spec)
    if current_selection == default_spec:
        new_selection = spec_extra
    else:
        new_selection = default_spec
    st.session_state["filtro_spec"] = new_selection
    try:
        st.experimental_rerun()
    except AttributeError:
        st.warning("Ricarica manualmente la pagina.")

if st.button("MMG + PED 🩺"):
    st.session_state["filtro_spec"] = ["MMG", "PED"]
    try:
        st.experimental_rerun()
    except AttributeError:
        st.warning("Ricarica manualmente la pagina.")

# Caricamento del file Excel
file = st.file_uploader("Carica il file Excel", type=["xlsx"])
if file:
    # Legge il file Excel e seleziona il foglio "MMG"
    xls = pd.ExcelFile(file)
    df_mmg = pd.read_excel(xls, sheet_name="MMG")
    
    # Uniforma i nomi delle colonne in minuscolo e rimuove spazi extra
    df_mmg.columns = df_mmg.columns.str.lower()
    if "provincia" in df_mmg.columns:
        df_mmg["provincia"] = df_mmg["provincia"].astype(str).str.strip()
    if "microarea" in df_mmg.columns:
        df_mmg["microarea"] = df_mmg["microarea"].astype(str).str.strip()
    
    # --- NUOVA SEZIONE: FILTRO PER DISTANZA ---
    # Se le colonne latitudine e longitudine sono presenti, permette di filtrare per raggio
    if "latitudine" in df_mmg.columns and "longitudine" in df_mmg.columns:
        st.markdown("### Filtro per Distanza")
        st.info("Inserisci le tue coordinate e seleziona il raggio (in km)")
        user_lat = st.number_input("La tua latitudine", value=0.0, format="%.6f")
        user_lon = st.number_input("La tua longitudine", value=0.0, format="%.6f")
        radius = st.slider("Raggio (km)", min_value=1, max_value=100, value=10)
        # Calcola la distanza per ogni medico e crea la nuova colonna "distanza_km"
        df_mmg["distanza_km"] = df_mmg.apply(
            lambda row: haversine(user_lat, user_lon, float(row["latitudine"]), float(row["longitudine"])),
            axis=1
        )
        st.write(f"Medici con distanza ≤ {radius} km: {df_mmg[df_mmg['distanza_km'] <= radius].shape[0]}")
        # Filtra i dati in base al raggio selezionato
        df_mmg = df_mmg[df_mmg["distanza_km"] <= radius]
    
    # ---------------------------
    # CALCOLO DEL CAMPO "ULTIMA VISITA"
    # ---------------------------
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", 
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    def get_ultima_visita(row):
        ultima = ""
        for m in mesi:
            if m in row and str(row[m]).strip().lower() == "x":
                ultima = m.capitalize()
        return ultima
    df_mmg["ultima visita"] = df_mmg.apply(get_ultima_visita, axis=1)
    
    # Il resto del codice (selezione ciclo, filtri, ordinamenti, visualizzazione AgGrid, etc.) rimane invariato...
    # [Qui segue il resto del tuo codice, con i filtri esistenti come nel tuo script originale]
    
    # (Il codice per la gestione dei cicli, filtri per specializzazione, target, fascia oraria, ecc.)
    # ...
