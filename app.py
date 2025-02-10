import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# Definizione delle specializzazioni di default ed extra
default_spec = ["MMG", "PED"]
spec_extra = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

# 🔄 Funzione per azzerare i filtri riportandoli ai valori predefiniti
def azzera_filtri():
    st.session_state["filtro_spec"] = default_spec
    st.session_state["filtro_target"] = "In target"
    st.session_state["filtro_visto"] = "Non Visto"
    st.session_state["giorno_scelto"] = "sempre"   # Impostato di default su "sempre"
    st.session_state["fascia_oraria"] = "Mattina e Pomeriggio"
    st.session_state["provincia_scelta"] = "Ovunque"
    st.session_state["microarea_scelta"] = "Ovunque"
    st.session_state["search_query"] = ""  # Resetta anche la barra di ricerca
    try:
        st.experimental_rerun()
    except AttributeError:
        st.warning("Ricarica manualmente la pagina (aggiorna Streamlit per usare experimental_rerun).")

st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# --- PULSANTE SPECIALISTI 👨‍⚕️👩‍⚕️ ---
if st.button("Specialisti 👨‍⚕️👩‍⚕️"):
    current_selection = st.session_state.get("filtro_spec", default_spec)
    # Se la selezione corrente è quella di default (solo MMG e PED), allora impostiamo la selezione a quella degli specialisti extra;
    # altrimenti, ripristiniamo la selezione di default.
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
    
    # Uniforma i nomi delle colonne in minuscolo e rimuove eventuali spazi extra per "provincia" e "microarea"
    df_mmg.columns = df_mmg.columns.str.lower()
    if "provincia" in df_mmg.columns:
        df_mmg["provincia"] = df_mmg["provincia"].str.strip()
    if "microarea" in df_mmg.columns:
        df_mmg["microarea"] = df_mmg["microarea"].str.strip()
    
    # ---------------------------
    # PRIMO FILTRO: CICLO DEI MESI
    # ---------------------------
    # Questo filtro determina su quali colonne (relative ai mesi) applicare il filtro "visto"
    ciclo_options = [
        "Tutti",
        "Ciclo 1 (Gen-Feb-Mar)",
        "Ciclo 2 (Apr-Mag-Giu)",
        "Ciclo 3 (Lug-Ago-Set)",
        "Ciclo 4 (Ott-Nov-Dic)"
    ]
    # Utilizziamo un menu a tendina con il label "💠 SELEZIONA CICLO"
    ciclo_scelto = st.selectbox("💠 SELEZIONA CICLO", ciclo_options, key="ciclo_scelto")
    
    # ---------------------------
    # 1. Filtro per tipo di specialista (spec)
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
    # 3. Filtro per "visto" (Tutti / Visto / Non Visto)
    # ---------------------------
    filtro_visto = st.selectbox(
        "👀 Filtra per medici 'VISTO'",
        ["Tutti", "Visto", "Non Visto"],
        index=["Tutti", "Visto", "Non Visto"].index(st.session_state.get("filtro_visto", "Non Visto")),
        key="filtro_visto"
    )
    
    # Determiniamo le colonne da utilizzare per il filtro "visto" in base al ciclo scelto
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
    
    # Applica il lowercase e gestisce eventuali NaN nelle colonne del filtro "visto"
    df_mmg[visto_cols] = df_mmg[visto_cols].fillna("").applymap(lambda s: s.lower() if isinstance(s, str) else s)
    if filtro_visto == "Visto":
        df_mmg = df_mmg[df_mmg[visto_cols].eq("x").any(axis=1)]
    elif filtro_visto == "Non Visto":
        df_mmg = df_mmg[~df_mmg[visto_cols].eq("x").any(axis=1)]
    
    # ---------------------------
    # 4. Filtro per giorno della settimana
    # ---------------------------
    giorni_opzioni = ["sempre", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]
    giorno_scelto = st.selectbox(
        "📅 Scegli un giorno della settimana",
        giorni_opzioni,
        index=giorni_opzioni.index(st.session_state.get("giorno_scelto", "sempre")),
        key="giorno_scelto"
    )
    
    # ---------------------------
    # 5. Filtro per fascia oraria (con opzione "Personalizzato")
    # ---------------------------
    fascia_options = ["Mattina", "Pomeriggio", "Mattina e Pomeriggio", "Personalizzato"]
    fascia_oraria = st.radio(
        "🌞 Scegli la fascia oraria",
        fascia_options,
        index=fascia_options.index(st.session_state.get("fascia_oraria", "Mattina e Pomeriggio")),
        key="fascia_oraria"
    )
    if fascia_oraria == "Personalizzato":
        custom_range = st.slider(
            "Seleziona l'intervallo orario",
            min_value=datetime.time(0, 0),
            max_value=datetime.time(23, 59),
            value=(datetime.time(10, 0), datetime.time(12, 0)),
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
                df_mmg[colonne_giorni].apply(lambda row: any(interval_overlaps(row[col], custom_start, custom_end) for col in colonne_giorni), axis=1)
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
                df_mmg[col_list].apply(lambda row: any(interval_overlaps(row[col], custom_start, custom_end) for col in col_list), axis=1)
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
