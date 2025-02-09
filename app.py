import streamlit as st
import pandas as pd

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# Pulsante per azzerare i filtri
def azzera_filtri():
    for key in st.session_state.keys():
        del st.session_state[key]

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

    # Filtri principali
    spec_options = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
    filtro_spec = st.multiselect(
        "🩺 Filtra per tipo di specialista (SPEC)",
        spec_options,
        default=["MMG", "PED"]  # MMG e PED selezionati di default
    )

    filtro_target = st.selectbox("🎯 Scegli il tipo di medici", ["In target", "Non in target", "Tutti"], index=0)

    filtro_visto = st.selectbox("👀 Filtra per medici 'VISTO'", ["Tutti", "Visto", "Non Visto"], index=2)

    giorno_scelto = st.selectbox("📅 Scegli un giorno della settimana", ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"])

    fascia_oraria = st.radio("🌞 Scegli la fascia oraria", ["Mattina", "Pomeriggio", "Mattina e Pomeriggio"], index=2)

    provincia_scelta = st.selectbox("📍 Scegli la Provincia", ["Ovunque"] + sorted(df_mmg["provincia"].dropna().unique().tolist()))

    microarea_scelta = st.selectbox("📌 Scegli la Microarea", ["Ovunque"] + sorted(df_mmg["microarea"].dropna().unique().tolist()))

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
