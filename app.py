import streamlit as st
import pandas as pd

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# 🔄 Pulsante per azzerare i filtri riportandoli ai valori predefiniti
def azzera_filtri():
    st.session_state["filtro_spec"] = ["MMG", "PED"]
    st.session_state["filtro_target"] = "In target"
    st.session_state["filtro_visto"] = "Non Visto"
    st.session_state["giorno_scelto"] = "lunedì"
    st.session_state["fascia_oraria"] = "Mattina e Pomeriggio"
    st.session_state["provincia_scelta"] = "Ovunque"
    st.session_state["microarea_scelta"] = "Ovunque"
    st.rerun()  # 🔄 Ricarica l'app per applicare i valori predefiniti

st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# Caricamento del file Excel
file = st.file_uploader("Carica il file Excel", type=["xlsx"])

if file:
    # Leggiamo il file Excel
    xls = pd.ExcelFile(file)
    df_mmg = pd.read_excel(xls, sheet_name="MMG")

    # Convertiamo i nomi delle colonne in minuscolo per uniformità
    df_mmg.columns = df_mmg.columns.str.lower()

    # Puliamo i dati rimuovendo spazi extra nei nomi delle province e delle microaree
    df_mmg["provincia"] = df_mmg["provincia"].str.strip()
    df_mmg["microarea"] = df_mmg["microarea"].str.strip()

    # Filtri principali con valori predefiniti
    spec_options = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
    filtro_spec = st.multiselect(
        "🩺 Filtra per tipo di specialista (SPEC)",
        spec_options,
        default=st.session_state.get("filtro_spec", ["MMG", "PED"]),
        key="filtro_spec"
    )

    filtro_target = st.selectbox(
        "🎯 Scegli il tipo di medici",
        ["In target", "Non in target", "Tutti"],
        index=["In target", "Non in target", "Tutti"].index(st.session_state.get("filtro_target", "In target")),
        key="filtro_target"
    )

    filtro_visto = st.selectbox(
        "👀 Filtra per medici 'VISTO'",
        ["Tutti", "Visto", "Non Visto"],
        index=["Tutti", "Visto", "Non Visto"].index(st.session_state.get("filtro_visto", "Non Visto")),
        key="filtro_visto"
    )

    giorno_scelto = st.selectbox(
        "📅 Scegli un giorno della settimana",
        ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"],
        index=["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"].index(st.session_state.get("giorno_scelto", "lunedì")),
        key="giorno_scelto"
    )

    fascia_oraria = st.radio(
        "🌞 Scegli la fascia oraria",
        ["Mattina", "Pomeriggio", "Mattina e Pomeriggio"],
        index=["Mattina", "Pomeriggio", "Mattina e Pomeriggio"].index(st.session_state.get("fascia_oraria", "Mattina e Pomeriggio")),
        key="fascia_oraria"
    )

    provincia_scelta = st.selectbox(
        "📍 Scegli la Provincia",
        ["Ovunque"] + sorted(df_mmg["provincia"].dropna().unique().tolist()),
        index=(["Ovunque"] + sorted(df_mmg["provincia"].dropna().unique().tolist())).index(st.session_state.get("provincia_scelta", "Ovunque")),
        key="provincia_scelta"
    )

    microarea_scelta = st.selectbox(
        "📌 Scegli la Microarea",
        ["Ovunque"] + sorted(df_mmg["microarea"].dropna().unique().tolist()),
        index=(["Ovunque"] + sorted(df_mmg["microarea"].dropna().unique().tolist())).index(st.session_state.get("microarea_scelta", "Ovunque")),
        key="microarea_scelta"
    )

    # **Applicazione dei filtri**
    df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]

    if filtro_target == "In target":
        df_mmg = df_mmg[df_mmg["in target"] == "x"]
    elif filtro_target == "Non in target":
        df_mmg = df_mmg[df_mmg["in target"].isna()]

    colonne_visto = df_mmg.columns[:3].tolist()

    def check_visto(row):
        for col in colonne_visto:
            if isinstance(row[col], str) and row[col].lower() == "x":
                return "x"
        return None

    df_mmg["visto_combinato"] = df_mmg.apply(check_visto, axis=1)

    if filtro_visto == "Visto":
        df_mmg = df_mmg[df_mmg["visto_combinato"] == "x"]
    elif filtro_visto == "Non Visto":
        df_mmg = df_mmg[df_mmg["visto_combinato"].isna()]

    colonna_mattina = f"{giorno_scelto} mattina".lower()
    colonna_pomeriggio = f"{giorno_scelto} pomeriggio".lower()

    if fascia_oraria == "Mattina":
        df_filtrato = df_mmg[df_mmg[colonna_mattina].notna()]
    elif fascia_oraria == "Pomeriggio":
        df_filtrato = df_mmg[df_mmg[colonna_pomeriggio].notna()]
    else:
        df_filtrato = df_mmg[df_mmg[colonna_mattina].notna() | df_mmg[colonna_pomeriggio].notna()]

    if provincia_scelta != "Ovunque":
        df_filtrato = df_filtrato[df_filtrato["provincia"] == provincia_scelta]

    if microarea_scelta != "Ovunque":
        df_filtrato = df_filtrato[df_filtrato["microarea"] == microarea_scelta]

    # **Visualizzazione dei risultati con "Microarea" per ultima**
    st.write("### Medici disponibili")

    colonne_da_mostrare = ["nome medico", "città"]
    if fascia_oraria in ["Mattina", "Mattina e Pomeriggio"]:
        colonne_da_mostrare.append(colonna_mattina)
    if fascia_oraria in ["Pomeriggio", "Mattina e Pomeriggio"]:
        colonne_da_mostrare.append(colonna_pomeriggio)

    colonne_da_mostrare.append("microarea")  # Spostiamo "Microarea" per ultima

    # **Assegnazione di larghezze fisse**
    st.dataframe(
        df_filtrato[colonne_da_mostrare].set_index("nome medico"),
        width=1000,  # Imposta una larghezza massima della tabella
        height=500  # Altezza fissa della tabella
    )
