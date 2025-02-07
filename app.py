import streamlit as st
import pandas as pd

# Funzione per caricare il file Excel
@st.cache_data
def load_data(file):
    df = pd.read_excel(file, sheet_name="MMG")
    return df

# Titolo della Web App
st.title("📋 Ricerca Medici - Orari di Ricevimento")

# Caricamento del file
uploaded_file = st.file_uploader("📂 Carica il file Excel con i medici", type=["xlsx"])

if uploaded_file is not None:
    # Caricare i dati
    df = load_data(uploaded_file)

    # Pulizia dati
    df = df.rename(columns=lambda x: x.strip())  # Rimuovere spazi nei nomi colonne

    # **Filtri disponibili**
    st.sidebar.header("🔎 Filtri di Ricerca")

    # **Filtro per Specializzazione (Default: MMG e PED)**
    specializzazioni = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
    spec_scelte = st.sidebar.multiselect("🩺 Specializzazione", specializzazioni, default=["MMG", "PED"])
    df = df[df["SPEC"].isin(spec_scelte)]

    # **Filtro per Stato (Default: In Target)**
    stato_scelto = st.sidebar.selectbox("📌 Stato", ["In Target", "Tutti", "Non In Target"], index=0)
    if stato_scelto == "In Target":
        df = df[df["In target"].str.upper() == "X"]
    elif stato_scelto == "Non In Target":
        df = df[df["In target"].isna()]

    # **Filtro per Giorno della Settimana**
    giorni_settimana = ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]
    giorno_scelto = st.sidebar.selectbox("📅 Giorno della Settimana", giorni_settimana)

    # **Filtro per Fascia Oraria**
    fascia_oraria = st.sidebar.selectbox("⏰ Fascia Oraria", ["Mattina", "Pomeriggio"])
    colonna_orario = f"{giorno_scelto} mattina" if fascia_oraria == "Mattina" else f"{giorno_scelto} pomeriggio"
    df = df[df[colonna_orario].notna()]

    # **Filtro per Provincia**
    province = df["PROVINCIA"].dropna().unique().tolist()
    province.insert(0, "Ovunque")
    provincia_scelta = st.sidebar.selectbox("🏢 Provincia", province)
    if provincia_scelta != "Ovunque":
        df = df[df["PROVINCIA"] == provincia_scelta]

    # **Filtro per Microarea**
    microaree = df["Microarea"].dropna().unique().tolist()
    microaree.insert(0, "Ovunque")
    microarea_scelta = st.sidebar.selectbox("📍 Microarea", microaree)
    if microarea_scelta != "Ovunque":
        df = df[df["Microarea"] == microarea_scelta]

    # **Escludere Medici già Visti**
    escludi_visti = st.sidebar.checkbox("❌ Escludi medici già visti")
    if escludi_visti:
        df = df[df["VISTO"].str.upper() != "X"]

    # **Tabella Risultati**
    st.subheader("📋 Medici disponibili")
    risultati = df[["NOME MEDICO", "Città", colonna_orario, "Indirizzo ambulatorio", "Microarea"]].rename(
        columns={colonna_orario: "Orario"}
    )
    st.dataframe(risultati)

else:
    st.info("🔹 Carica un file Excel per iniziare la ricerca!")
