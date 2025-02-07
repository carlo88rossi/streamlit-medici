import streamlit as st
import pandas as pd
import requests
from io import BytesIO

# URL corretto per il download diretto da Dropbox
file_url = "https://www.dropbox.com/scl/fi/xjajne2rivvfrl27ac32t/NUOVO-FOGLIO-MEDICI.xlsx?rlkey=ryndkj5izepxgfmagmeu4ph3m&st=c6x9kqxz&dl=1"

# Funzione per caricare il file Excel
@st.cache_data
def load_data(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            file = BytesIO(response.content)  # Converti in file-like object
            df = pd.read_excel(file, sheet_name="Foglio1")  # Carica il foglio "Foglio1"
            df = df.rename(columns=lambda x: x.strip())  # Rimuovi spazi nei nomi delle colonne
            return df
        else:
            st.error(f"❌ Errore nel download del file. Codice: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"❌ Errore nel caricamento del file: {e}")
        return None

# Titolo della Web App
st.title("📋 Ricerca Medici - Orari di Ricevimento")

# Caricare i dati
df = load_data(file_url)

if df is not None:
    # Sidebar per i filtri
    st.sidebar.header("🔎 Filtri di Ricerca")

    # Filtro per Specializzazione
    specializzazioni = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
    spec_scelte = st.sidebar.multiselect("🩺 Specializzazione", specializzazioni, default=["MMG", "PED"])
    df = df[df["SPEC"].isin(spec_scelte)]

    # Filtro per Stato (Default: In Target)
    stato_scelto = st.sidebar.selectbox("📌 Stato", ["In Target", "Tutti", "Non In Target"], index=0)
    df["In target"] = df["In target"].fillna('').astype(str).str.upper()
    if stato_scelto == "In Target":
        df = df[df["In target"] == "X"]
    elif stato_scelto == "Non In Target":
        df = df[df["In target"] != "X"]

    # Filtro per Giorno della Settimana
    giorni_settimana = ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]
    giorno_scelto = st.sidebar.selectbox("📅 Giorno della Settimana", giorni_settimana)

    # Filtro per Fascia Oraria
    fascia_oraria = st.sidebar.selectbox("⏰ Fascia Oraria", ["Mattina", "Pomeriggio"])
    colonna_orario = f"{giorno_scelto} mattina" if fascia_oraria == "Mattina" else f"{giorno_scelto} pomeriggio"

    # Verifica che la colonna esista
    if colonna_orario in df.columns:
        df = df[df[colonna_orario].notna()]
    else:
        st.warning(f"La colonna '{colonna_orario}' non esiste nel file!")

    # Filtro per Provincia
    if "PROVINCIA" in df.columns:
        province = df["PROVINCIA"].dropna().unique().tolist()
        province.insert(0, "Ovunque")
        provincia_scelta = st.sidebar.selectbox("🏢 Provincia", province)
        if provincia_scelta != "Ovunque":
            df = df[df["PROVINCIA"] == provincia_scelta]

    # Filtro per Microarea
    if "Microarea" in df.columns:
        microaree = df["Microarea"].dropna().unique().tolist()
        microaree.insert(0, "Ovunque")
        microarea_scelta = st.sidebar.selectbox("📍 Microarea", microaree)
        if microarea_scelta != "Ovunque":
            df = df[df["Microarea"] == microarea_scelta]

    # Escludere Medici già Visti
    if "VISTO" in df.columns:
        df["VISTO"] = df["VISTO"].fillna('').astype(str).str.upper()
        escludi_visti = st.sidebar.checkbox("❌ Escludi medici già visti")
        if escludi_visti:
            df = df[df["VISTO"] != "X"]

    # Tabella Risultati
    st.subheader("📋 Medici disponibili")

    colonne_da_mostrare = ["NOME MEDICO", "Città", "Indirizzo ambulatorio", "Microarea"]
    if colonna_orario in df.columns:
        colonne_da_mostrare.insert(2, colonna_orario)  # Inserisce orario nella posizione giusta
        risultati = df[colonne_da_mostrare].rename(columns={colonna_orario: "Orario"})
    else:
        risultati = df[colonne_da_mostrare]

    st.dataframe(risultati)

else:
    st.error("❌ Impossibile caricare il file Excel.")
