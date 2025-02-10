import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# 🔄 Funzione per azzerare i filtri riportandoli ai valori predefiniti
def azzera_filtri():
    st.session_state["filtro_spec"] = ["MMG", "PED"]
    st.session_state["filtro_target"] = "In target"
    st.session_state["filtro_visto"] = "Non Visto"
    st.session_state["giorno_scelto"] = "sempre"   # Impostato di default su "sempre"
    st.session_state["fascia_oraria"] = "Mattina e Pomeriggio"
    st.session_state["provincia_scelta"] = "Ovunque"
    st.session_state["microarea_scelta"] = "Ovunque"
    st.session_state["search_query"] = ""  # Resetta anche la barra di ricerca
    st.experimental_rerun()

st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# Caricamento del file Excel
file = st.file_uploader("Carica il file Excel", type=["xlsx"])

if file:
    # Legge il file Excel e seleziona il foglio "MMG"
    xls = pd.ExcelFile(file)
    df_mmg = pd.read_excel(xls, sheet_name="MMG")
    
    # Uniforma i nomi delle colonne in minuscolo
    df_mmg.columns = df_mmg.columns.str.lower()
    
    # Rimuove eventuali spazi extra nelle colonne "provincia" e "microarea" (se presenti)
    if "provincia" in df_mmg.columns:
        df_mmg["provincia"] = df_mmg["provincia"].str.strip()
    if "microarea" in df_mmg.columns:
        df_mmg["microarea"] = df_mmg["microarea"].str.strip()
    
    # --- FILTRI ---
    # 1. Filtro per tipo di specialista (spec)
    spec_options = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
    filtro_spec = st.multiselect(
        "🩺 Filtra per tipo di specialista (spec)",
        spec_options,
        default=st.session_state.get("filtro_spec", ["MMG", "PED"]),
        key="filtro_spec"
    )
    
    # 2. Filtro per target (In target / Non in target / Tutti)
    filtro_target = st.selectbox(
        "🎯 Scegli il tipo di medici",
        ["In target", "Non in target", "Tutti"],
        index=["In target", "Non in target", "Tutti"].index(st.session_state.get("filtro_target", "In target")),
        key="filtro_target"
    )
    
    # 3. Filtro per "visto" (Tutti / Visto / Non Visto)
    filtro_visto = st.selectbox(
        "👀 Filtra per medici 'VISTO'",
        ["Tutti", "Visto", "Non Visto"],
        index=["Tutti", "Visto", "Non Visto"].index(st.session_state.get("filtro_visto", "Non Visto")),
        key="filtro_visto"
    )
    
    # 4. Selezione del giorno della settimana (opzione "sempre" impostata di default)
    giorni_opzioni = ["sempre", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]
    giorno_scelto = st.selectbox(
        "📅 Scegli un giorno della settimana",
        giorni_opzioni,
        index=giorni_opzioni.index(st.session_state.get("giorno_scelto", "sempre")),
        key="giorno_scelto"
    )
    
    # 5. Selezione della fascia oraria
    fascia_oraria = st.radio(
        "🌞 Scegli la fascia oraria",
        ["Mattina", "Pomeriggio", "Mattina e Pomeriggio"],
        index=["Mattina", "Pomeriggio", "Mattina e Pomeriggio"].index(st.session_state.get("fascia_oraria", "Mattina e Pomeriggio")),
        key="fascia_oraria"
    )
    
    # 6. Filtro per Provincia e Microarea (se presenti)
    provincia_scelta = st.selectbox(
        "📍 Scegli la Provincia",
        ["Ovunque"] + (sorted(df_mmg["provincia"].dropna().unique().tolist()) if "provincia" in df_mmg.columns else []),
        index=(["Ovunque"] + (sorted(df_mmg["provincia"].dropna().unique().tolist()) if "provincia" in df_mmg.columns else [])).index(st.session_state.get("provincia_scelta", "Ovunque")),
        key="provincia_scelta"
    )
    
    microarea_scelta = st.selectbox(
        "📌 Scegli la Microarea",
        ["Ovunque"] + (sorted(df_mmg["microarea"].dropna().unique().tolist()) if "microarea" in df_mmg.columns else []),
        index=(["Ovunque"] + (sorted(df_mmg["microarea"].dropna().unique().tolist()) if "microarea" in df_mmg.columns else [])).index(st.session_state.get("microarea_scelta", "Ovunque")),
        key="microarea_scelta"
    )
    
    # Applica il filtro per il tipo di specialista
    df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]
    
    # Applica il filtro per il target
    if filtro_target == "In target":
        df_mmg = df_mmg[df_mmg["in target"] == "x"]
    elif filtro_target == "Non in target":
        df_mmg = df_mmg[df_mmg["in target"].isna()]
    
    # --- FILTRO "VISTO" ---
    # Utilizza SEMPRE le prime tre colonne per verificare la presenza della "x" (case-insensitive)
    visto_cols = df_mmg.columns[:3]
    df_mmg[visto_cols] = df_mmg[visto_cols].fillna("").applymap(lambda s: s.lower() if isinstance(s, str) else s)
    if filtro_visto == "Visto":
        # Mostra solo i medici per cui almeno una delle prime tre colonne contiene "x"
        df_mmg = df_mmg[df_mmg[visto_cols].eq("x").any(axis=1)]
    elif filtro_visto == "Non Visto":
        # Esclude i medici per cui almeno una delle prime tre colonne contiene "x"
        df_mmg = df_mmg[~df_mmg[visto_cols].eq("x").any(axis=1)]
    
    # --- FILTRI PER GIORNO E FASCIA ORARIA ---
    if giorno_scelto == "sempre":
        giorni_settimana = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]
        colonne_giorni = []
        for g in giorni_settimana:
            if fascia_oraria == "Mattina":
                colonne_giorni.append(f"{g} mattina".lower())
            elif fascia_oraria == "Pomeriggio":
                colonne_giorni.append(f"{g} pomeriggio".lower())
            else:  # "Mattina e Pomeriggio"
                colonne_giorni.append(f"{g} mattina".lower())
                colonne_giorni.append(f"{g} pomeriggio".lower())
        for col in colonne_giorni:
            if col not in df_mmg.columns:
                st.error(f"La colonna '{col}' non esiste nel file Excel.")
                st.stop()
        df_filtrato = df_mmg[df_mmg[colonne_giorni].notna().any(axis=1)]
        # Le colonne da mostrare includono "indirizzo ambulatorio" PRIMA di "microarea"
        colonne_da_mostrare = ["nome medico", "città"] + colonne_giorni + ["indirizzo ambulatorio", "microarea"]
    else:
        colonna_mattina = f"{giorno_scelto} mattina".lower()
        colonna_pomeriggio = f"{giorno_scelto} pomeriggio".lower()
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
    
    if provincia_scelta != "Ovunque" and "provincia" in df_mmg.columns:
        df_filtrato = df_filtrato[df_filtrato["provincia"] == provincia_scelta]
    if microarea_scelta != "Ovunque" and "microarea" in df_mmg.columns:
        df_filtrato = df_filtrato[df_filtrato["microarea"] == microarea_scelta]
    
    # --- BARRA DI RICERCA ---
    search_query = st.text_input("🔎 Cerca nei risultati", placeholder="Inserisci nome, città, microarea, ecc.", key="search_query")
    if search_query:
        query = search_query.lower()
        df_filtrato = df_filtrato[
            df_filtrato.drop(columns=["provincia"], errors="ignore")
                      .astype(str)
                      .apply(lambda row: query in " ".join(row).lower(), axis=1)
        ]
    
    # Contatore medici unici (basato sul campo "nome medico", ignorando maiuscole/minuscole)
    num_unique_medici = df_filtrato["nome medico"].str.lower().nunique()
    st.write(f"**Numero medici:** {num_unique_medici} 🧮")
    
    st.write("### Medici disponibili")
    
    # --- CONFIGURAZIONE E VISUALIZZAZIONE CON AgGrid ---
    # Imposta anche la proprietà per non permettere lo spostamento delle colonne
    gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
    gb.configure_default_column(sortable=True, filter=True, resizable=False, width=100, lockPosition=True)
    gb.configure_column("nome medico", width=150, resizable=False, lockPosition=True)
    gb.configure_column("città", width=120, resizable=False, lockPosition=True)
    # Configura le colonne relative al ricevimento
    for col in colonne_da_mostrare:
        if col not in ["nome medico", "città", "indirizzo ambulatorio", "microarea"]:
            gb.configure_column(col, width=100, resizable=False, lockPosition=True)
    gb.configure_column("indirizzo ambulatorio", width=150, resizable=False, lockPosition=True)
    gb.configure_column("microarea", width=100, resizable=False, lockPosition=True)
    
    grid_options = gb.build()
    # Inoltre, impediamo lo spostamento delle colonne a livello di grid
    grid_options["suppressMovableColumns"] = True
    
    AgGrid(df_filtrato[colonne_da_mostrare],
           gridOptions=grid_options,
           height=500,
           fit_columns_on_grid_load=False)
