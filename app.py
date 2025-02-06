import streamlit as st
import pandas as pd

st.title("📋 Filtro Medici - Ricevimento Settimanale")
st.write("Carica il file Excel per filtrare i medici disponibili.")

# Funzione per azzerare i filtri
def azzera_filtri():
    for key in st.session_state.keys():
        del st.session_state[key]

# Pulsante per azzerare i filtri
st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# Caricamento del file Excel
file = st.file_uploader("Carica il file Excel", type=["xlsx"])

if file:
    # Leggiamo il file Excel
    xls = pd.ExcelFile(file)
    df_mmg = pd.read_excel(xls, sheet_name="MMG")

    # Convertiamo tutti i nomi delle colonne in minuscolo per evitare problemi di maiuscole/minuscole
    df_mmg.columns = df_mmg.columns.str.lower()

    # Puliamo i dati rimuovendo spazi extra nei nomi delle province e delle microaree
    df_mmg["provincia"] = df_mmg["provincia"].str.strip()
    df_mmg["microarea"] = df_mmg["microarea"].str.strip()

    # **NUOVA SEZIONE: Filtro per la colonna SPEC**
    if 'filtro_spec' not in st.session_state:
        st.session_state['filtro_spec'] = ["MMG"]  # MMG selezionato di default
    
    spec_options = ["MMG", "PED", "ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
    filtro_spec = st.multiselect(
        "🩺 Filtra per tipo di specialista (SPEC)",
        spec_options,
        default=["MMG"],
        key="filtro_spec"
    )

    # Applica il filtro SPEC
    df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]
    # **FINE NUOVA SEZIONE**

    # **NUOVA SEZIONE: Gestione delle colonne "Visto"**
    # Identifica le prime tre colonne (assumendo che siano le colonne "visto")
    colonne_visto = df_mmg.columns[:3].tolist()

    # Crea una colonna "visto_combinato" che è "x" se ALMENO una delle colonne "visto" contiene "x"
    def check_visto(row):
        for col in colonne_visto:
            val = row[col]
            if isinstance(val, str) and val.lower() == "x":
                return "x"
        return None

    df_mmg["visto_combinato"] = df_mmg.apply(check_visto, axis=1)
    # **FINE NUOVA SEZIONE**

    # Menu a tendina per scegliere quali medici vedere (In Target)
    if 'filtro_target' not in st.session_state:
        st.session_state['filtro_target'] = "In target"  # Valore predefinito impostato su "In target"
    filtro_target = st.selectbox(
        "🎯 Scegli il tipo di medici da visualizzare (Target)",
        ["In target", "Non in target", "Tutti"],
        index=0, #indice per selezionare "In target" di default
        key="filtro_target"  # Usiamo una key per lo st.session_state
    )

    # Menu a tendina per filtrare medici "VISTO"
    if 'filtro_visto' not in st.session_state:
        st.session_state['filtro_visto'] = "Non Visto"  # Valore predefinito
    filtro_visto = st.selectbox(
        "👀 Filtra per medici 'VISTO'",
        ["Tutti", "Visto", "Non Visto"],
        index=2, #indice per selezionare "Non Visto" di default
        key="filtro_visto"  # Usiamo una key per lo st.session_state
    )

    # Applicare il filtro "VISTO" (ora usa la colonna "visto_combinato")
    if filtro_visto == "Visto":
        df_mmg = df_mmg[df_mmg["visto_combinato"] == "x"]
    elif filtro_visto == "Non Visto":
        df_mmg = df_mmg[df_mmg["visto_combinato"].isna()]
    elif filtro_visto == "Tutti":
        pass #non applicare nessun filtro

    # Applicare il filtro scelto (Target)
    if filtro_target == "In target":
        df_mmg = df_mmg[df_mmg["in target"] == "x"]
    elif filtro_target == "Non in target":
        df_mmg = df_mmg[df_mmg["in target"].isna()]
    elif filtro_target == "Tutti":
        pass #non applicare nessun filtro

    # Lista dei giorni disponibili (convertiti in minuscolo)
    if 'giorno_scelto' not in st.session_state:
        st.session_state['giorno_scelto'] = "lunedì"  # Valore predefinito
    giorno_scelto = st.selectbox("📅 Scegli un giorno della settimana", ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"], key="giorno_scelto")

    # Scelta tra Mattina, Pomeriggio e "Sempre"
    if 'fascia_oraria' not in st.session_state:
        st.session_state['fascia_oraria'] = "Sempre"  # Valore predefinito
    fascia_oraria = st.radio("🌞 Scegli la fascia oraria", ["Mattina", "Pomeriggio", "Sempre"], key="fascia_oraria")

    # Filtriamo per Provincia (aggiungendo "Ovunque")
    province_disponibili = ["Ovunque"] + sorted(df_mmg["provincia"].dropna().unique().tolist())
    if 'provincia_scelta' not in st.session_state:
        st.session_state['provincia_scelta'] = "Ovunque"  # Valore predefinito
    provincia_scelta = st.selectbox("📍 Scegli la Provincia", province_disponibili, key="provincia_scelta")

    # Filtriamo per Microarea (aggiungendo "Ovunque")
    microaree_disponibili = ["Ovunque"] + sorted(df_mmg["microarea"].dropna().unique().tolist())
    if 'microarea_scelta' not in st.session_state:
        st.session_state['microarea_scelta'] = "Ovunque"  # Valore predefinito
    microarea_scelta = st.selectbox("📌 Scegli la Microarea", microaree_disponibili, key="microarea_scelta")

    # Creiamo il nome della colonna in minuscolo
    colonna_mattina = f"{giorno_scelto} mattina".lower()
    colonna_pomeriggio = f"{giorno_scelto} pomeriggio".lower()

    # Filtriamo il dataframe in base alla selezione di mattina/pomeriggio/sempre
    if fascia_oraria == "Mattina":
        df_filtrato = df_mmg[df_mmg[colonna_mattina].notna()]
    elif fascia_oraria == "Pomeriggio":
        df_filtrato = df_mmg[df_mmg[colonna_pomeriggio].notna()]
    else:  # fascia_oraria == "Sempre"
        df_filtrato = df_mmg[df_mmg[colonna_mattina].notna() | df_mmg[colonna_pomeriggio].notna()]

    # Applichiamo il filtro sulla provincia se non è "Ovunque"
    if provincia_scelta != "Ovunque":
        df_filtrato = df_filtrato[df_filtrato["provincia"] == provincia_scelta]

    # Applichiamo il filtro sulla microarea se non è "Ovunque"
    if microarea_scelta != "Ovunque":
        df_filtrato = df_filtrato[df_filtrato["microarea"] == microarea_scelta]

    # Mostriamo la tabella risultante
    st.write("### Medici disponibili")
    colonne_da_mostrare = ["nome medico", "città", "microarea"]
    if fascia_oraria in ["Mattina", "Sempre"]:
        colonne_da_mostrare.append(colonna_mattina)
    if fascia_oraria in ["Pomeriggio", "Sempre"]:
        colonne_da_mostrare.append(colonna_pomeriggio)

    st.dataframe(df_filtrato[colonne_da_mostrare])
