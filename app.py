import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode  # Per eseguire codice JavaScript personalizzato

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
    
    st.header("🔎 Filtri di Ricerca")
    
    # ---- PRIMA RIGA DI FILTRI ----
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        specializzazioni = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
        spec_scelte = st.multiselect("🩺 Specializzazione", specializzazioni,
                                      default=["MMG", "PED"],
                                      key="specializzazione")
    with col2:
        stato_scelto = st.selectbox("📌 Stato", ["In Target", "Tutti", "Non In Target"],
                                    index=0, key="stato")
    with col3:
        giorni_settimana = ["Tutti", "LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]
        giorno_scelto = st.selectbox("📅 Giorno della Settimana", giorni_settimana,
                                     index=0, key="giorno")
    with col4:
        # Aggiunta l'opzione "Mattina e Pomeriggio"
        fascia_oraria = st.selectbox("⏰ Fascia Oraria", ["Mattina", "Pomeriggio", "Mattina e Pomeriggio"],
                                     key="fascia")
    
    # ---- SECONDA RIGA DI FILTRI ----
    col5, col6, col7 = st.columns(3)
    with col5:
        province = df["PROVINCIA"].dropna().unique().tolist()
        province.insert(0, "Ovunque")
        provincia_scelta = st.selectbox("🏢 Provincia", province, key="provincia")
    with col6:
        microaree = df["Microarea"].dropna().unique().tolist()
        microaree.insert(0, "Ovunque")
        microarea_scelta = st.selectbox("📍 Microarea", microaree, key="microarea")
    with col7:
        escludi_visti = st.checkbox("❌ Escludi medici già visti", key="visti")
    
    # ---- CAMPO DI RICERCA ----
    search_query = st.text_input("🔍 Cerca nei risultati",
                                 placeholder="Inserisci parole chiave...",
                                 key="search_query")
    
    # ---- BOTTONCINO PER AZZERARE I FILTRI ----
    if st.button("🔄 Azzerare tutti i filtri"):
        keys_to_reset = ["specializzazione", "stato", "giorno", "fascia",
                         "provincia", "microarea", "visti", "search_query"]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        st.experimental_rerun()
    
    # ---- APPLICAZIONE DEI FILTRI SUI DATI ----
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
        if fascia_oraria == "Mattina":
            orario_cols = [f"{g} mattina" for g in giorni]
        elif fascia_oraria == "Pomeriggio":
            orario_cols = [f"{g} pomeriggio" for g in giorni]
        elif fascia_oraria == "Mattina e Pomeriggio":
            # Per ogni giorno includiamo entrambe le colonne, se presenti
            orario_cols = []
            for g in giorni:
                if f"{g} mattina" in df.columns:
                    orario_cols.append(f"{g} mattina")
                if f"{g} pomeriggio" in df.columns:
                    orario_cols.append(f"{g} pomeriggio")
        # Filtra le righe in cui almeno una delle colonne di orario è non nulla (se esistono)
        orario_cols_present = [col for col in orario_cols if col in df.columns]
        if len(orario_cols_present) > 0:
            df = df[df[orario_cols_present].notna().any(axis=1)]
        else:
            st.warning("Nessuna colonna di orario trovata per i giorni selezionati.")
    else:
        # Giorno specifico
        if fascia_oraria == "Mattina":
            colonna_orario = f"{giorno_scelto} mattina"
            if colonna_orario in df.columns:
                df = df[df[colonna_orario].notna()]
            else:
                st.warning(f"La colonna '{colonna_orario}' non è presente nel file Excel.")
        elif fascia_oraria == "Pomeriggio":
            colonna_orario = f"{giorno_scelto} pomeriggio"
            if colonna_orario in df.columns:
                df = df[df[colonna_orario].notna()]
            else:
                st.warning(f"La colonna '{colonna_orario}' non è presente nel file Excel.")
        elif fascia_oraria == "Mattina e Pomeriggio":
            col_mattina = f"{giorno_scelto} mattina"
            col_pomeriggio = f"{giorno_scelto} pomeriggio"
            cols_exist = [col for col in [col_mattina, col_pomeriggio] if col in df.columns]
            if len(cols_exist) > 0:
                # Filtra le righe in cui almeno una delle due colonne non è nulla
                df = df[df[cols_exist].notna().any(axis=1)]
            else:
                st.warning("Nessuna colonna trovata per il giorno selezionato.")
    
    # Filtro per Provincia
    if provincia_scelta != "Ovunque":
        df = df[df["PROVINCIA"] == provincia_scelta]
    
    # Filtro per Microarea
    if microarea_scelta != "Ovunque":
        df = df[df["Microarea"] == microarea_scelta]
    
    # Filtro per Medici già Visti
    if escludi_visti:
        visto_cols = df.columns[:3]
        df = df[~df[visto_cols].fillna("").apply(
            lambda row: any(str(cell).strip().upper() == "X" for cell in row),
            axis=1
        )]
    
    # Filtro di ricerca testuale
    if search_query:
        query = search_query.lower()
        df = df[df.fillna('').astype(str).apply(
            lambda row: query in " ".join(row).lower(), axis=1)]
    
    # ---- CREAZIONE DEI RISULTATI ----
    if giorno_scelto == "Tutti":
        if fascia_oraria in ["Mattina", "Pomeriggio"]:
            # Mostra per ogni giorno la fascia scelta
            if fascia_oraria == "Mattina":
                orario_cols = [f"{g} mattina" for g in ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]]
            else:
                orario_cols = [f"{g} pomeriggio" for g in ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]]
        elif fascia_oraria == "Mattina e Pomeriggio":
            # Per ogni giorno includi entrambe le colonne, se presenti
            orario_cols = []
            for g in ["LUNEDì", "MARTEDì", "MERCOLEDì", "GIOVEDì", "VENERDì"]:
                if f"{g} mattina" in df.columns:
                    orario_cols.append(f"{g} mattina")
                if f"{g} pomeriggio" in df.columns:
                    orario_cols.append(f"{g} pomeriggio")
        # Usa solo le colonne di orario effettivamente presenti
        orario_cols_present = [col for col in orario_cols if col in df.columns]
        risultati = df[["NOME MEDICO", "Città"] + orario_cols_present + ["Indirizzo ambulatorio", "Microarea"]]
    else:
        # Giorno specifico
        if fascia_oraria in ["Mattina", "Pomeriggio"]:
            colonna_orario = f"{giorno_scelto} {fascia_oraria.lower()}"
            if colonna_orario in df.columns:
                risultati = df[["NOME MEDICO", "Città", colonna_orario, "Indirizzo ambulatorio", "Microarea"]].rename(
                    columns={colonna_orario: "Orario"}
                )
            else:
                risultati = df[["NOME MEDICO", "Città", "Indirizzo ambulatorio", "Microarea"]]
        elif fascia_oraria == "Mattina e Pomeriggio":
            col_mattina = f"{giorno_scelto} mattina"
            col_pomeriggio = f"{giorno_scelto} pomeriggio"
            cols_exist = [col for col in [col_mattina, col_pomeriggio] if col in df.columns]
            if len(cols_exist) > 0:
                risultati = df[["NOME MEDICO", "Città"] + cols_exist + ["Indirizzo ambulatorio", "Microarea"]]
                # Rinomina le colonne per chiarezza
                rename_map = {}
                if col_mattina in cols_exist:
                    rename_map[col_mattina] = "Orario Mattina"
                if col_pomeriggio in cols_exist:
                    rename_map[col_pomeriggio] = "Orario Pomeriggio"
                risultati = risultati.rename(columns=rename_map)
            else:
                risultati = df[["NOME MEDICO", "Città", "Indirizzo ambulatorio", "Microarea"]]
    
    unique_medici = risultati["NOME MEDICO"].nunique()
    st.markdown(f"**Numero di medici trovati: {unique_medici}**")
    
    # ---- CONFIGURAZIONE DI AGGRID ----
    gb = GridOptionsBuilder.from_dataframe(risultati)
    gb.configure_default_column(sortable=True, filter=True, suppressMenu=True, suppressMovable=True)
    
    # Callback JS: tutte le colonne tranne "Città" vengono auto-dimensionate normalmente.
    # Per "Città" viene calcolata la larghezza ideale e poi impostata fissa a metà.
    auto_size_js = JsCode("""
    function(params) {
        setTimeout(function(){
            var allCols = params.columnApi.getAllColumns();
            var colsToAutoSize = [];
            allCols.forEach(function(col) {
                if (col.colDef.field !== "Città") {
                    colsToAutoSize.push(col.colDef.field);
                }
            });
            if (colsToAutoSize.length > 0) {
                params.columnApi.autoSizeColumns(colsToAutoSize, false);
            }
            // Auto-dimensiona "Città" per calcolarne la larghezza ideale
            params.columnApi.autoSizeColumns(["Città"], false);
            var cityColumn = params.columnApi.getColumn("Città");
            if (cityColumn) {
                var autoWidth = cityColumn.getActualWidth();
                params.columnApi.setColumnWidth(cityColumn, Math.floor(autoWidth / 2));
            }
        }, 300);
    }
    """)
    
    gb.configure_grid_options(onGridReady=auto_size_js)
    grid_options = gb.build()
    
    # Visualizzazione dei risultati con AgGrid (allow_unsafe_jscode=True per il JS personalizzato)
    AgGrid(risultati, gridOptions=grid_options, height=400, allow_unsafe_jscode=True)
    
else:
    st.info("🔹 Carica un file Excel per iniziare la ricerca!")
