import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re

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

# Definizione delle specializzazioni di default ed extra
default_spec = ["MMG", "PED"]
spec_extra = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

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
        "custom_range"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    try:
        st.experimental_rerun()
    except AttributeError:
        st.warning("Ricarica manualmente la pagina (aggiorna Streamlit per usare experimental_rerun).")

st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# --- PULSANTE SPECIALISTI 👨‍⚕️👩‍⚕️ ---
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
        st.warning("Ricarica manualmente la pagina (aggiorna Streamlit per usare experimental_rerun).")

# Caricamento del file Excel
file = st.file_uploader("Carica il file Excel", type=["xlsx"])
if file:
    # Legge il file Excel e seleziona il foglio "MMG"
    xls = pd.ExcelFile(file)
    df_mmg = pd.read_excel(xls, sheet_name="MMG")
    
    # Uniforma i nomi delle colonne in minuscolo e rimuove spazi extra
    df_mmg.columns = df_mmg.columns.str.lower()
    if "provincia" in df_mmg.columns:
        df_mmg["provincia"] = df_mmg["provincia"].str.strip()
    if "microarea" in df_mmg.columns:
        df_mmg["microarea"] = df_mmg["microarea"].str.strip()
    
    # ---------------------------
    # PRIMO FILTRO: CICLO DEI MESI
    # ---------------------------
    ciclo_options = [
        "Tutti",
        "Ciclo 1 (Gen-Feb-Mar)",
        "Ciclo 2 (Apr-Mag-Giu)",
        "Ciclo 3 (Lug-Ago-Set)",
        "Ciclo 4 (Ott-Nov-Dic)"
    ]
    current_date = datetime.datetime.now()
    month_names = {1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
                   7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"}
    current_month_name = month_names[current_date.month]
    if current_date.month in [1, 2, 3]:
        default_cycle_index = 1
    elif current_date.month in [4, 5, 6]:
        default_cycle_index = 2
    elif current_date.month in [7, 8, 9]:
        default_cycle_index = 3
    else:
        default_cycle_index = 4

    label_ciclo = f"💠 SELEZIONA CICLO ({current_month_name} {current_date.year})"
    ciclo_scelto = st.selectbox(label_ciclo, ciclo_options, index=default_cycle_index, key="ciclo_scelto")
    
    # ---------------------------
    # 1. Filtro per specialista (spec)
    # ---------------------------
    spec_options = default_spec + spec_extra
    filtro_spec = st.multiselect(
        "🩺 Filtra per tipo di specialista (spec)",
        spec_options,
        default=st.session_state.get("filtro_spec", default_spec),
        key="filtro_spec"
    )
    df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]
    
    # ---------------------------
    # 2. Filtro per target (In target / Non in target / Tutti)
    # ---------------------------
    filtro_target = st.selectbox(
        "🎯 Scegli il tipo di medici",
        ["In target", "Non in target", "Tutti"],
        index=["In target", "Non in target", "Tutti"].index(st.session_state.get("filtro_target", "In target")),
        key="filtro_target"
    )
    if filtro_target == "In target":
        df_mmg = df_mmg[df_mmg["in target"] == "x"]
    elif filtro_target == "Non in target":
        df_mmg = df_mmg[df_mmg["in target"].isna()]
    
    # ---------------------------
    # 3. Filtro per "visto" (Tutti / Visto / Non Visto / Visita VIP)
    # ---------------------------
    filtro_visto = st.selectbox(
        "👀 Filtra per medici 'VISTO'",
        ["Tutti", "Visto", "Non Visto", "Visita VIP"],
        index=["Tutti", "Visto", "Non Visto", "Visita VIP"].index(st.session_state.get("filtro_visto", "Non Visto")),
        key="filtro_visto"
    )
    
    if ciclo_scelto == "Tutti":
        all_months = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                      "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
        visto_cols = [col for col in all_months if col in df_mmg.columns]
        if not visto_cols:
            visto_cols = df_mmg.columns[:3]
    else:
        month_cycles = {
            "Ciclo 1 (Gen-Feb-Mar)": ["gennaio", "febbraio", "marzo"],
            "Ciclo 2 (Apr-Mag-Giu)": ["aprile", "maggio", "giugno"],
            "Ciclo 3 (Lug-Ago-Set)": ["luglio", "agosto", "settembre"],
            "Ciclo 4 (Ott-Nov-Dic)": ["ottobre", "novembre", "dicembre"]
        }
        ciclo_cols = month_cycles.get(ciclo_scelto, [])
        visto_cols = [col for col in ciclo_cols if col in df_mmg.columns]
        if not visto_cols:
            st.warning(f"Non sono state trovate colonne per {ciclo_scelto}.")
            visto_cols = df_mmg.columns[:3]
    
    df_mmg[visto_cols] = df_mmg[visto_cols].fillna("").applymap(lambda s: s.lower() if isinstance(s, str) else s)
    if filtro_visto == "Visto":
        df_mmg = df_mmg[df_mmg[visto_cols].eq("x").any(axis=1)]
    elif filtro_visto == "Non Visto":
        df_mmg = df_mmg[~df_mmg[visto_cols].eq("x").any(axis=1)]
    elif filtro_visto == "Visita VIP":
        df_mmg = df_mmg[df_mmg[visto_cols].eq("v").any(axis=1)]
    
    # ---------------------------
    # Nuovo filtro: FREQUENZA (dopo "VISTO")
    # ---------------------------
    filtro_frequenza = st.checkbox("🔔 FREQUENZA", value=False, key="filtro_frequenza")
    if filtro_frequenza:
        if "frequenza" in df_mmg.columns:
            df_mmg = df_mmg[df_mmg["frequenza"].str.strip().str.lower() == "x"]
        else:
            st.warning("La colonna 'frequenza' non è presente nel file Excel.")
    
    # ---------------------------
    # 4. Filtro per giorno della settimana
    # ---------------------------
    # Calcola il default dinamico per il giorno della settimana in base alla data corrente
    oggi = datetime.datetime.now()
    weekday = oggi.weekday()  # 0: lunedì, 1: martedì, ..., 6: domenica
    giorni_settimana = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]
    if weekday < 5:
        default_giorno = giorni_settimana[weekday]
    else:
        default_giorno = "sempre"  # Se siamo nel weekend

    giorni_opzioni = ["sempre", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]
    # Se "giorno_scelto" non è presente, verrà usato il default dinamico
    giorno_scelto = st.selectbox(
        "📅 Scegli un giorno della settimana",
        giorni_opzioni,
        index=giorni_opzioni.index(st.session_state.get("giorno_scelto", default_giorno)),
        key="giorno_scelto"
    )
    
    # ---------------------------
    # 5. Filtro per fascia oraria (con opzione "Personalizzato")
    # ---------------------------
    default_fascia = "Personalizzato"
    fascia_options = ["Mattina", "Pomeriggio", "Mattina e Pomeriggio", "Personalizzato"]
    fascia_value = st.session_state.get("fascia_oraria")
    if fascia_value is None or fascia_value not in fascia_options:
        fascia_value = default_fascia

    fascia_oraria = st.radio(
        "🌞 Scegli la fascia oraria",
        fascia_options,
        index=fascia_options.index(fascia_value),
        key="fascia_oraria"
    )
    if fascia_oraria == "Personalizzato":
        # Se non esiste già il range salvato in session_state, lo impostiamo in base all'orario corrente +1 ora
        if "custom_range" not in st.session_state:
            ora_corrente_dt = datetime.datetime.now()
            custom_start_default = ora_corrente_dt.time()
            custom_end_dt = ora_corrente_dt + datetime.timedelta(hours=1)  # +1 ora anziché +2 ore
            custom_end_default = custom_end_dt.time() if custom_end_dt.time() <= datetime.time(23, 59) else datetime.time(23, 59)
            st.session_state["custom_range"] = (custom_start_default, custom_end_default)
            
        custom_range = st.slider(
            "Seleziona l'intervallo orario",
            min_value=datetime.time(0, 0),
            max_value=datetime.time(23, 59),
            value=st.session_state["custom_range"],
            step=datetime.timedelta(minutes=15),
            format="HH:mm",
            key="custom_range"
        )
        custom_start, custom_end = custom_range
        if custom_end <= custom_start:
            st.error("L'orario di fine deve essere successivo all'orario di inizio.")
            st.stop()
    
    # ---------------------------
    # 6. Filtro per Provincia e Microarea
    # ---------------------------
    provincia_lista = ["Ovunque"] + (sorted(df_mmg["provincia"].dropna().unique().tolist()) if "provincia" in df_mmg.columns else [])
    provincia_scelta = st.selectbox(
        "📍 Scegli la Provincia",
        provincia_lista,
        index=provincia_lista.index(st.session_state.get("provincia_scelta", "Ovunque")),
        key="provincia_scelta"
    )
    microarea_lista = ["Ovunque"] + (sorted(df_mmg["microarea"].dropna().unique().tolist()) if "microarea" in df_mmg.columns else [])
    microarea_scelta = st.selectbox(
        "📌 Scegli la Microarea",
        microarea_lista,
        index=microarea_lista.index(st.session_state.get("microarea_scelta", "Ovunque")),
        key="microarea_scelta"
    )
    
    # ---------------------------
    # FUNZIONI PER IL PARSING DEGLI ORARI
    # ---------------------------
    def parse_interval(cell_value):
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
        start_time, end_time = parse_interval(cell_value)
        if start_time is None or end_time is None:
            return False
        return (start_time <= custom_start) and (end_time >= custom_end)
    
    def interval_overlaps(cell_value, custom_start, custom_end):
        start_time, end_time = parse_interval(cell_value)
        if start_time is None or end_time is None:
            return False
        return (start_time < custom_end) and (custom_start < end_time)
    
    # ---------------------------
    # FILTRI PER GIORNO E FASCIA ORARIA
    # ---------------------------
    if giorno_scelto == "sempre":
        giorni_settimana = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]
        colonne_giorni = []
        for g in giorni_settimana:
            if fascia_oraria == "Mattina":
                colonne_giorni.append(f"{g} mattina".lower())
            elif fascia_oraria == "Pomeriggio":
                colonne_giorni.append(f"{g} pomeriggio".lower())
            elif fascia_oraria == "Mattina e Pomeriggio":
                colonne_giorni.append(f"{g} mattina".lower())
                colonne_giorni.append(f"{g} pomeriggio".lower())
            elif fascia_oraria == "Personalizzato":
                col_mattina = f"{g} mattina".lower()
                col_pomeriggio = f"{g} pomeriggio".lower()
                if col_mattina in df_mmg.columns:
                    colonne_giorni.append(col_mattina)
                if col_pomeriggio in df_mmg.columns:
                    colonne_giorni.append(col_pomeriggio)
        if fascia_oraria != "Personalizzato":
            for col in colonne_giorni:
                if col not in df_mmg.columns:
                    st.error(f"La colonna '{col}' non esiste nel file Excel.")
                    st.stop()
        if fascia_oraria == "Personalizzato":
            df_filtrato = df_mmg[
                df_mmg[colonne_giorni].apply(lambda row: any(interval_covers(row[col], custom_start, custom_end) for col in colonne_giorni), axis=1)
            ]
            colonne_da_mostrare = ["nome medico", "città"] + colonne_giorni + ["indirizzo ambulatorio", "microarea"]
        else:
            df_filtrato = df_mmg[df_mmg[colonne_giorni].notna().any(axis=1)]
            colonne_da_mostrare = ["nome medico", "città"] + colonne_giorni + ["indirizzo ambulatorio", "microarea"]
    else:
        colonna_mattina = f"{giorno_scelto} mattina".lower()
        colonna_pomeriggio = f"{giorno_scelto} pomeriggio".lower()
        if fascia_oraria == "Personalizzato":
            col_list = []
            if colonna_mattina in df_mmg.columns:
                col_list.append(colonna_mattina)
            if colonna_pomeriggio in df_mmg.columns:
                col_list.append(colonna_pomeriggio)
            if not col_list:
                st.error(f"Le colonne per il giorno {giorno_scelto} non esistono nel file Excel.")
                st.stop()
            df_filtrato = df_mmg[
                df_mmg[col_list].apply(lambda row: any(interval_covers(row[col], custom_start, custom_end) for col in col_list), axis=1)
            ]
            colonne_da_mostrare = ["nome medico", "città"] + col_list + ["indirizzo ambulatorio", "microarea"]
        else:
            if fascia_oraria in ["Mattina", "Mattina e Pomeriggio"]:
                if colonna_mattina not in df_mmg.columns:
                    st.error(f"La colonna '{colonna_mattina}' non esiste nel file Excel.")
                    st.stop()
            if fascia_oraria in ["Pomeriggio", "Mattina e Pomeriggio"]:
                if colonna_pomeriggio not in df_mmg.columns:
                    st.error(f"La colonna '{colonna_pomeriggio}' non esiste nel file Excel.")
                    st.stop()
            if fascia_oraria == "Mattina":
                df_filtrato = df_mmg[df_mmg[colonna_mattina].notna()]
                colonne_da_mostrare = ["nome medico", "città", colonna_mattina, "indirizzo ambulatorio", "microarea"]
            elif fascia_oraria == "Pomeriggio":
                df_filtrato = df_mmg[df_mmg[colonna_pomeriggio].notna()]
                colonne_da_mostrare = ["nome medico", "città", colonna_pomeriggio, "indirizzo ambulatorio", "microarea"]
            else:
                df_filtrato = df_mmg[df_mmg[colonna_mattina].notna() | df_mmg[colonna_pomeriggio].notna()]
                colonne_da_mostrare = ["nome medico", "città", colonna_mattina, colonna_pomeriggio, "indirizzo ambulatorio", "microarea"]
    
    # ---------------------------
    # FILTRO PER PROVINCIA E MICROAREA
    # ---------------------------
    if provincia_scelta != "Ovunque" and "provincia" in df_filtrato.columns:
        df_filtrato = df_filtrato[
            df_filtrato["provincia"].str.strip().str.lower() == provincia_scelta.strip().lower()
        ]
    if microarea_scelta != "Ovunque" and "microarea" in df_filtrato.columns:
        df_filtrato = df_filtrato[
            df_filtrato["microarea"].str.strip().str.lower() == microarea_scelta.strip().lower()
        ]
    
    # ---------------------------
    # BARRA DI RICERCA
    # ---------------------------
    search_query = st.text_input("🔎 Cerca nei risultati", placeholder="Inserisci nome, città, microarea, ecc.", key="search_query")
    if search_query:
        query = search_query.lower()
        df_filtrato = df_filtrato[
            df_filtrato.drop(columns=["provincia"], errors="ignore")
                      .astype(str)
                      .apply(lambda row: query in " ".join(row).lower(), axis=1)
        ]
    
    # ---------------------------
    # CONTEGGIO MEDICI
    # ---------------------------
    num_unique_medici = df_filtrato["nome medico"].str.lower().nunique()
    st.write(f"**Numero medici:** {num_unique_medici} 🧮")
    
    st.write("### Medici disponibili")
    
    # ---------------------------
    # VISUALIZZAZIONE CON AgGrid
    # ---------------------------
    gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
    gb.configure_default_column(sortable=True, filter=True, resizable=False, width=100, lockPosition=True)
    gb.configure_column("nome medico", width=150, resizable=False, lockPosition=True)
    gb.configure_column("città", width=120, resizable=False, lockPosition=True)
    for col in colonne_da_mostrare:
        if col not in ["nome medico", "città", "indirizzo ambulatorio", "microarea"]:
            gb.configure_column(col, width=100, resizable=False, lockPosition=True)
    gb.configure_column("indirizzo ambulatorio", width=150, resizable=False, lockPosition=True)
    gb.configure_column("microarea", width=100, resizable=False, lockPosition=True)
    
    grid_options = gb.build()
    grid_options["suppressMovableColumns"] = True
    
    AgGrid(df_filtrato[colonne_da_mostrare],
           gridOptions=grid_options,
           height=500,
           fit_columns_on_grid_load=False)
    
    # ---------------------------
    # Possibilità di scaricare il risultato della tabella in CSV
    # ---------------------------
    csv = df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Scarica tabella (CSV)",
        data=csv,
        file_name="medici_filtrati.csv",
        mime="text/csv"
    )
