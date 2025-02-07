import streamlit as st
import pandas as pd

# Funzione per caricare il file Excel
@st.cache_data
def load_data(file):
    df = pd.read_excel(file, sheet_name="MMG")
    return df

# Titolo della Web App
st.title("📋 Ricerca Medici - Orari di Ricevimento")

# Caricamento del file Excel
uploaded_file = st.file_uploader("📂 Carica il file Excel con i medici", type=["xlsx"])

if uploaded_file is not None:
    # Carica e pulisci i dati
    df = load_data(uploaded_file)
    df = df.rename(columns=lambda x: x.strip())
    
    # ----- FILTRI -----
    st.header("🔎 Filtri di Ricerca")
    
    # Prima riga di filtri
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        specializzazioni = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
        spec_scelte = st.multiselect("🩺 Specializzazione", specializzazioni, default=["MMG", "PED"])
    with col2:
        stato_scelto = st.selectbox("📌 Stato", ["In Target", "Tutti", "Non In Target"], index=0)
    with col3:
        giorni_settimana = ["Tutti", "LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]
        giorno_scelto = st.selectbox("📅 Giorno della Settimana", giorni_settimana, index=0)
    with col4:
        fascia_oraria = st.selectbox("⏰ Fascia Oraria", ["Mattina", "Pomeriggio"])
    
    # Seconda riga di filtri
    col5, col6, col7 = st.columns(3)
    with col5:
        province = df["PROVINCIA"].dropna().unique().tolist()
        province.insert(0, "Ovunque")
        provincia_scelta = st.selectbox("🏢 Provincia", province)
    with col6:
        microaree = df["Microarea"].dropna().unique().tolist()
        microaree.insert(0, "Ovunque")
        microarea_scelta = st.selectbox("📍 Microarea", microaree)
    with col7:
        escludi_visti = st.checkbox("❌ Escludi medici già visti")
    
    # Terza riga: campo di ricerca testuale
    search_query = st.text_input("🔍 Cerca nei risultati", placeholder="Inserisci parole chiave...")
    
    # ----- APPLICAZIONE DEI FILTRI SUI DATI -----
    
    # Filtro per Specializzazione
    df = df[df["SPEC"].isin(spec_scelte)]
    
    # Filtro per Stato
    if stato_scelto == "In Target":
        df = df[df["In target"].str.upper() == "X"]
    elif stato_scelto == "Non In Target":
        df = df[df["In target"].isna()]
    
    # Filtro per Giorno e Fascia Oraria
    if giorno_scelto == "Tutti":
        giorni = ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]
        orario_cols = [f"{g} mattina" for g in giorni] if fascia_oraria == "Mattina" else [f"{g} pomeriggio" for g in giorni]
        df = df[df[orario_cols].notna().any(axis=1)]
    else:
        colonna_orario = f"{giorno_scelto} mattina" if fascia_oraria == "Mattina" else f"{giorno_scelto} pomeriggio"
        df = df[df[colonna_orario].notna()]
    
    # Filtro per Provincia
    if provincia_scelta != "Ovunque":
        df = df[df["PROVINCIA"] == provincia_scelta]
    
    # Filtro per Microarea
    if microarea_scelta != "Ovunque":
        df = df[df["Microarea"] == microarea_scelta]
    
    # Filtro per medici già visti
    if escludi_visti:
        # Se le prime 3 colonne del DataFrame sono i flag "visto"
        visto_cols = df.columns[:3]
        df = df[~df[visto_cols].fillna("").apply(
            lambda row: any(str(cell).strip().upper() == "X" for cell in row),
            axis=1
        )]
    
    # Filtro di ricerca testuale
    if search_query:
        query = search_query.lower()
        df = df[df.fillna('').astype(str).apply(lambda row: query in " ".join(row).lower(), axis=1)]
    
    # ----- CREAZIONE DEI RISULTATI -----
    if giorno_scelto == "Tutti":
        orario_cols = [f"{g} mattina" for g in ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]] if fascia_oraria == "Mattina" \
                      else [f"{g} pomeriggio" for g in ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]]
        risultati = df[["NOME MEDICO", "Città"] + orario_cols + ["Indirizzo ambulatorio", "Microarea"]]
    else:
        colonna_orario = f"{giorno_scelto} mattina" if fascia_oraria == "Mattina" else f"{giorno_scelto} pomeriggio"
        risultati = df[["NOME MEDICO", "Città", colonna_orario, "Indirizzo ambulatorio", "Microarea"]].rename(
            columns={colonna_orario: "Orario"}
        )
    
    # ----- ORDINAMENTO RISULTATI -----
    st.subheader("Ordinamento dei risultati")
    col_sort, col_order = st.columns(2)
    with col_sort:
        sort_column = st.selectbox("Ordina per colonna", risultati.columns.tolist())
    with col_order:
        sort_order = st.radio("Ordine", ["Ascendente", "Discendente"], horizontal=True)
    
    ascending = True if sort_order == "Ascendente" else False
    risultati = risultati.sort_values(by=sort_column, ascending=ascending)
    
    # ----- VISUALIZZAZIONE DEI RISULTATI -----
    st.subheader("📋 Medici disponibili")
    st.dataframe(risultati)

else:
    st.info("🔹 Carica un file Excel per iniziare la ricerca!")
