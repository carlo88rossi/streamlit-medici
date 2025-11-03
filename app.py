import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re
import pytz  # per gestire il fuso orario

# Imposta il fuso orario desiderato
timezone = pytz.timezone("Europe/Rome")

# Configurazione della pagina
st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")

# ---------- CSS -----------------------------------------------------------------
st.markdown("""
<style>
body{background:#f8f9fa;color:#212529;}
[data-testid="stAppViewContainer"]{background:#f8f9fa;}
h1{font-family:'Helvetica Neue',sans-serif;font-size:2.5rem;text-align:center;
   color:#007bff;margin-bottom:1.5rem;}
div.stButton>button{background:#007bff;color:#fff;border:none;border-radius:4px;
   padding:0.5rem 1rem;font-size:1rem;}
div.stButton>button:hover{background:#0056b3;}
.ag-root-wrapper{border:1px solid #dee2e6!important;border-radius:4px;overflow:hidden;}
.ag-header-cell-label{font-weight:bold;color:#343a40;}
.ag-row{font-size:0.9rem;}
</style>
""", unsafe_allow_html=True)

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# ---------- CARICAMENTO FILE ----------------------------------------------------
file = st.file_uploader("Carica il file Excel", type=["xlsx"], key="file_uploader")
if not file:
    st.stop()

# ---------- RESET FILTRI & PULSANTI RAPIDI --------------------------------------
def azzera_filtri():
    for k in [
        "filtro_spec","filtro_target","filtro_visto","giorno_scelto","fascia_oraria",
        "provincia_scelta","microarea_scelta","search_query","custom_start","custom_end",
        "ciclo_scelto","filtro_frequenza","filtro_ultima_visita"
    ]:
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

# ---------- LETTURA E PREPARAZIONE DATAFRAME ------------------------------------
xls = pd.ExcelFile(file)
df_mmg = pd.read_excel(xls, sheet_name="MMG")
df_mmg.columns = df_mmg.columns.str.lower()

if "provincia" in df_mmg.columns:
    df_mmg["provincia"] = df_mmg["provincia"].astype(str).str.strip()
if "microarea" in df_mmg.columns:
    df_mmg["microarea"] = df_mmg["microarea"].astype(str).str.strip()

# ---------- FUNZIONI UTILI ------------------------------------------------------
def parse_interval(cell_value):
    if pd.isna(cell_value):
        return None, None
    s = str(cell_value).strip()
    m = re.match(r"(\d{1,2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}(?::\d{2})?)", s)
    if not m:
        return None, None
    start_str, end_str = m.groups()
    fmt = "%H:%M" if ":" in start_str else "%H"
    try:
        return (
            datetime.datetime.strptime(start_str, fmt).time(),
            datetime.datetime.strptime(end_str, fmt).time(),
        )
    except ValueError:
        return None, None

def interval_covers(cell_value, custom_start, custom_end):
    start_t, end_t = parse_interval(cell_value)
    if start_t is None or end_t is None:
        return False
    return start_t <= custom_start and end_t >= custom_end

# ---------- CALCOLO "ULTIMA VISITA" ---------------------------------------------
mesi = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
        "luglio","agosto","settembre","ottobre","novembre","dicembre"]
month_order = {m: i+1 for i, m in enumerate(mesi)}

def get_ultima_visita(row):
    ultima = ""
    for m in mesi:
        val = str(row.get(m, "")).strip().lower()
        if val in ["x", "v"]:
            ultima = m.capitalize()
    return ultima

for m in mesi:
    if m in df_mmg.columns:
        df_mmg[m] = df_mmg[m].fillna("").astype(str).str.strip().str.lower()

df_mmg["ultima visita"] = df_mmg.apply(get_ultima_visita, axis=1)

# ---------- SELEZIONE CICLO + KPI -----------------------------------------------
ciclo_opts = [
    "Tutti",
    "Ciclo 1 (Gen-Feb-Mar)",
    "Ciclo 2 (Apr-Mag-Giu)",
    "Ciclo 3 (Lug-Ago-Set)",
    "Ciclo 4 (Ott-Nov-Dic)",
]
today = datetime.datetime.now(timezone)
default_cycle_idx = 1 + (today.month - 1) // 3
ciclo_scelto = st.selectbox(
    f"💠 SELEZIONA CICLO ({today.strftime('%B').capitalize()} {today.year})",
    ciclo_opts,
    index=default_cycle_idx,
    key="ciclo_scelto",
)

month_cycles = {
    "Ciclo 1 (Gen-Feb-Mar)": ["gennaio","febbraio","marzo"],
    "Ciclo 2 (Apr-Mag-Giu)": ["aprile","maggio","giugno"],
    "Ciclo 3 (Lug-Ago-Set)": ["luglio","agosto","settembre"],
    "Ciclo 4 (Ott-Nov-Dic)": ["ottobre","novembre","dicembre"],
}
visto_cols = (
    [m for m in mesi if m in df_mmg.columns]
    if ciclo_scelto == "Tutti"
    else month_cycles[ciclo_scelto]
)

# ---------- FILTRO MESE ULTIMA VISITA -------------------------------------------
lista_mesi_cap = [m.capitalize() for m in mesi]
filtro_ultima = st.selectbox(
    "Seleziona mese ultima visita",
    ["Nessuno"] + lista_mesi_cap,
    index=0,
    key="filtro_ultima_visita",
)

if filtro_ultima != "Nessuno":
    sel_num = month_order[filtro_ultima.lower()]
    df_mmg = df_mmg[
        df_mmg["ultima visita"]
            .str.lower()
            .map(lambda m: month_order.get(m, 0))
            .le(sel_num)
    ]

# ---------- FUNZIONI VISITA ----------------------------------------------------
def is_visited(row):
    freq = str(row.get("frequenza","")).strip().lower()
    count = sum(1 for c in visto_cols if row[c] in ["x","v"])
    return count >= 2 if freq == "x" else count >= 1

def is_vip(row):
    return any(row[c] == "v" for c in visto_cols)

def count_visits(row):
    return sum(1 for c in visto_cols if row[c] in ["x","v"])

def annotate_name(row):
    name = row["nome medico"]
    freq = str(row.get("frequenza","")).strip().lower()
    visits = row["Visite ciclo"]
    if freq == "x":
        name = f"{name} * ({visits})"
    if any(row[c] == "v" for c in visto_cols):
        name = f"{name} (VIP)"
    return name

# ---------- FILTRI --------------------------------------------------------------
default_spec = ["MMG", "PED"]
spec_extra = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

filtro_spec = st.multiselect(
    "🩺 Filtra per tipo di specialista (spec)",
    default_spec + spec_extra,
    default=st.session_state.get("filtro_spec", default_spec),
    key="filtro_spec",
)
df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]

# ---------- VISUALIZZAZIONE & CSV ----------------------------------------------
st.write(f"**Numero medici:** {df_mmg['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

# CSS: scroll orizzontale su mobile
st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] > div { overflow-x: auto !important; }
.ag-theme-streamlit-light { min-width: 700px; }
.ag-header-cell-label { font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Griglia responsive
gb = GridOptionsBuilder.from_dataframe(df_mmg)
gb.configure_default_column(
    sortable=True,
    filter=True,
    resizable=True,
    wrapText=False,
    autoHeight=False
)
gridOptions = gb.build()
gridOptions["domLayout"] = "normal"
gridOptions["onFirstDataRendered"] = {
    "function": """
        function(params) {
            let allColumnIds = [];
            params.columnApi.getAllColumns().forEach(function(column) {
                allColumnIds.push(column.colId);
            });
            params.columnApi.autoSizeColumns(allColumnIds, false);
        }
    """
}

# Mostra griglia scrollabile
with st.container():
    st.markdown('<div style="overflow-x:auto;">', unsafe_allow_html=True)
    AgGrid(
        df_mmg,
        gridOptions=gridOptions,
        enable_enterprise_modules=False,
        fit_columns_on_grid_load=False,
        height=600,
    )
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- DOWNLOAD CSV --------------------------------------------------------
st.download_button(
    "📥 Scarica risultati CSV",
    df_mmg.to_csv(index=False).encode("utf-8"),
    "risultati_medici.csv",
    "text/csv",
)
