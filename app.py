import streamlit as st
import pandas as pd

st.title("📋 Filtro Medici - Dati sempre aggiornati")
st.write("I dati vengono caricati automaticamente da Google Sheets.")

# 📍 Link CSV del Google Sheets (già aggiornato con il tuo!)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1VVvp7NyGwN-tf7XhzkscamyAAJhNTC27k5CnZQyBg_g/export?format=csv"

# Funzione per caricare i dati dal Google Sheet
@st.cache_data
def load_data():
    return pd.read_csv(SHEET_URL)

# Carichiamo i dati
df_mmg = load_data()

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

# **NUOVA SEZIONE: Gestione delle colonne "Visto"**
colonne_visto = df_mmg.columns[:3].tolist()

def check_visto(row):
    for col in colonne_visto:
        val = row[col]
        if isinstance(val, str) and val.lower() == "x":
            return "x"
    return None

df_mmg["visto_combinato"] = df_mmg.apply(check_visto, axis=1)

# **Filtri per Target e Visto**
filtro_target = st.selectbox(
    "🎯 Scegli il tipo di medici da visualizzare (Target)",
    ["In target", "Non in target", "Tutti"],
    index=0,
    key="filtro_target"
)

filtro_visto = st.selectbox(
    "👀 Filtra per medici 'VISTO'",
    ["Tutti", "Visto", "Non Visto"],
    index=2,
    key="filtro_visto"
)

# Applichiamo i filtri
if filtro_visto == "Visto":
    df_mmg = df_mmg[df_mmg["visto_combinato"] == "x"]
elif filtro_visto == "Non Visto":
    df_mmg = df_mmg[df_mmg["visto_combinato"].isna()]

if filtro_target == "In target":
    df_mmg = df_mmg[df_mmg["in target"] == "x"]
elif filtro_target == "Non in target":
    df_mmg = df_mmg[df_mmg["in target"].isna()]

# **Selezione del giorno della settimana**
giorno_scelto = st.selectbox("📅 Scegli un giorno della settimana", ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"], key="giorno_scelto")

# **Scelta tra Mattina, Pomeriggio e Sempre**
fascia_oraria = st.radio("🌞 Scegli la fascia oraria", ["Mattina", "Pomeriggio", "Sempre"], key="fascia_oraria")

# **Filtriamo per Provincia**
province_disponibili = ["Ovunque"] + sorted(df_mmg["provincia"].dropna().unique().tolist())
provincia_scelta = st.selectbox("📍 Scegli la Provincia", province_disponibili, key="provincia_scelta")

# **Filtriamo per Microarea**
microaree_disponibili = ["Ovunque"] + sorted(df_mmg["microarea"].dropna().unique().tolist())
microarea_scelta = st.selectbox("📌 Scegli la Microarea", microaree_disponibili, key="microarea_scelta")

# **Colonne per Mattina e Pomeriggio**
colonna_mattina = f"{giorno_scelto} mattina".lower()
colonna_pomeriggio = f"{giorno_scelto} pomeriggio".lower()

# **Filtriamo il dataframe in base alla fascia oraria scelta**
if fascia_oraria == "Mattina":
    df_filtrato = df_mmg[df_mmg[colonna_mattina].notna()]
elif fascia_oraria == "Pomeriggio":
    df_filtrato = df_mmg[df_mmg[colonna_pomeriggio].notna()]
else:  # fascia_oraria == "Sempre"
    df_filtrato = df_mmg[df_mmg[colonna_mattina].notna() | df_mmg[colonna_pomeriggio].notna()]

# **Applichiamo i filtri su Provincia e Microarea**
if provincia_scelta != "Ovunque":
    df_filtrato = df_filtrato[df_filtrato["provincia"] == provincia_scelta]

if microarea_scelta != "Ovunque":
    df_filtrato = df_filtrato[df_filtrato["microarea"] == microarea_scelta]

# **Mostriamo la tabella risultante**
st.write("### Medici disponibili")
colonne_da_mostrare = ["nome medico", "città", "microarea"]
if fascia_oraria in ["Mattina", "Sempre"]:
    colonne_da_mostrare.append(colonna_mattina)
if fascia_oraria in ["Pomeriggio", "Sempre"]:
    colonne_da_mostrare.append(colonna_pomeriggio)

st.dataframe(df_filtrato[colonne_da_mostrare])
