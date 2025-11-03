import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re
import pytz

# Imposta fuso orario
timezone = pytz.timezone("Europe/Rome")
st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")

# CSS responsive
st.markdown("""
<style>
body{background:#f8f9fa;color:#212529;}
[data-testid="stAppViewContainer"]{background:#f8f9fa;}
h1{font-family:'Helvetica Neue',sans-serif;font-size:2.5rem;text-align:center;color:#007bff;margin-bottom:1.5rem;}
div.stButton>button{background:#007bff;color:#fff;border:none;border-radius:4px;padding:0.5rem 1rem;font-size:1rem;}
div.stButton>button:hover{background:#0056b3;}
.ag-root-wrapper{border:1px solid #dee2e6!important;border-radius:4px;overflow-x:auto!important;}
.ag-header-cell-label{font-weight:bold;color:#343a40;}
.ag-row{font-size:0.9rem;}
</style>
""", unsafe_allow_html=True)

st.title("📋 Filtro Medici - Ricevimento Settimanale")

file = st.file_uploader("Carica il file Excel", type=["xlsx"], key="file_uploader")
if not file:
    st.stop()

def azzera_filtri():
    for k in st.session_state.keys():
        if k.startswith("filtro_") or k in ["giorno_scelto", "fascia_oraria", "provincia_scelta", "microarea_scelta", "search_query", "custom_start", "custom_end", "ciclo_scelto"]:
            st.session_state.pop(k, None)
    st.rerun()

def toggle_specialisti():
    st.session_state["filtro_spec"] = (
        ["ORT","FIS","REU","DOL","OTO","DER","INT","END","DIA"]
        if st.session_state.get("filtro_spec", ["MMG","PED"]) == ["MMG","PED"]
        else ["MMG","PED"]
    )
    st.rerun()

def seleziona_mmg_ped():
    st.session_state["filtro_spec"] = ["MMG","PED"]
    st.rerun()

col1, col2, col3 = st.columns([1,1,2])
with col1:
    st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)
with col2:
    st.button("Specialisti 👨‍⚕️👩‍⚕️", on_click=toggle_specialisti)
with col3:
    st.button("MMG + PED 🩺", on_click=seleziona_mmg_ped)

xls = pd.ExcelFile(file)
df = pd.read_excel(xls, sheet_name="MMG")
df.columns = df.columns.str.lower()

mesi = ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"]
month_order = {m: i+1 for i, m in enumerate(mesi)}

for m in mesi:
    if m in df.columns:
        df[m] = df[m].fillna("").astype(str).str.strip().str.lower()

def get_ultima_visita(row):
    ultima = ""
    for m in mesi:
        if row.get(m, "") in ["x", "v"]:
            ultima = m.capitalize()
    return ultima

df["ultima visita"] = df.apply(get_ultima_visita, axis=1)

ciclo_opts = ["Tutti", "Ciclo 1 (Gen-Feb-Mar)", "Ciclo 2 (Apr-Mag-Giu)", "Ciclo 3 (Lug-Ago-Set)", "Ciclo 4 (Ott-Nov-Dic)"]
today = datetime.datetime.now(timezone)
default_cycle_idx = 1 + (today.month - 1) // 3
ciclo_scelto = st.selectbox("💠 Seleziona ciclo", ciclo_opts, index=default_cycle_idx, key="ciclo_scelto")
month_cycles = {
    "Ciclo 1 (Gen-Feb-Mar)": ["gennaio","febbraio","marzo"],
    "Ciclo 2 (Apr-Mag-Giu)": ["aprile","maggio","giugno"],
    "Ciclo 3 (Lug-Ago-Set)": ["luglio","agosto","settembre"],
    "Ciclo 4 (Ott-Nov-Dic)": ["ottobre","novembre","dicembre"],
}
visto_cols = [m for m in mesi if m in df.columns] if ciclo_scelto == "Tutti" else month_cycles[ciclo_scelto]

def count_visits(row):
    return sum(1 for c in visto_cols if row[c] in ["x", "v"])

def annotate_name(row):
    name = row["nome medico"]
    visits = row["Visite ciclo"]
    if any(row[c] == "v" for c in visto_cols):
        name = f"{name} (VIP)"
    return f"{name} ({visits})"

df["Visite ciclo"] = df.apply(count_visits, axis=1)
df["nome medico"] = df.apply(annotate_name, axis=1)

filtro_spec = st.multiselect("🩺 Tipo specialista", ["MMG","PED","ORT","FIS","REU","DOL","OTO","DER","INT","END","DIA"], default=st.session_state.get("filtro_spec", ["MMG","PED"]), key="filtro_spec")
df = df[df["spec"].isin(filtro_spec)]

filtro_ultima = st.selectbox("Ultima visita entro il mese", ["Nessuno"] + [m.capitalize() for m in mesi], index=0, key="filtro_ultima_visita")
if filtro_ultima != "Nessuno":
    sel_num = month_order[filtro_ultima.lower()]
    df = df[df["ultima visita"].str.lower().map(lambda m: month_order.get(m, 0)).le(sel_num)]

prov_sel = st.selectbox("📍 Scegli la Provincia", ["Ovunque"] + sorted(df["provincia"].dropna().unique()), index=0, key="provincia_scelta")
if prov_sel != "Ovunque":
    df = df[df["provincia"] == prov_sel]

query = st.text_input("🔎 Cerca nei risultati", placeholder="Inserisci nome, città, microarea, ecc.", key="search_query")
if query:
    q = query.lower()
    df = df[df.astype(str).apply(lambda r: q in " ".join(r).lower(), axis=1)]

# Ordinamento intelligente
month_order_sort = {m: i+1 for i, m in enumerate(mesi)}
month_order_sort[""] = 0
df["__ult"] = df["ultima visita"].str.lower().map(month_order_sort).fillna(0)
df = df.sort_values(by=["__ult"])
df.drop(columns=["__ult"], inplace=True)

# Visualizzazione finale
st.write(f"**Numero medici:** {df['nome medico'].nunique()} 🧮")
st.write("### Medici disponibili")
colonne_da_mostrare = ["nome medico","città","indirizzo ambulatorio","microarea","provincia","ultima visita","Visite ciclo"]

gb = GridOptionsBuilder.from_dataframe(df[colonne_da_mostrare])
gb.configure_default_column(sortable=True, filter=True, resizable=True, min_width=120, wrapText=True, autoHeight=True)
gb.configure_column("nome medico", width=180)
AgGrid(df[colonne_da_mostrare], gridOptions=gb.build(), fit_columns_on_grid_load=True)

st.download_button(
    "Scarica risultati CSV",
    df[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    "risultati_medici.csv",
    "text/csv",
)
