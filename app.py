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
    st.session_state["filtro_spec"] = ["MMG"]
    st.rerun()

col1, col2, col3 = st.columns([1,1,2])
with col1:
    st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)
with col2:
    st.button("Specialisti 👨‍⚕️👩‍⚕️", on_click=toggle_specialisti)
with col3:
    st.button("MMG 🩺", on_click=seleziona_mmg_ped)

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
# Mappatura mesi -> numero per filtrare precedenti
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

# Applica filtro: include mese selezionato e tutti i precedenti
if filtro_ultima != "Nessuno":
    sel_num = month_order[filtro_ultima.lower()]
    df_mmg = df_mmg[
        df_mmg["ultima visita"]
            .str.lower()
            .map(lambda m: month_order.get(m, 0))
            .le(sel_num)
    ]

# ---------- FILTRI PRINCIPALI --------------------------------------------------
default_spec = ["MMG"]
spec_extra = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

filtro_spec = st.multiselect(
    "🩺 Filtra per tipo di specialista (spec)",
    default_spec + spec_extra,
    default=st.session_state.get("filtro_spec", default_spec),
    key="filtro_spec",
)
df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]

filtro_target = st.selectbox(
    "🎯 Scegli il tipo di medici",
    ["In target","Non in target","Tutti"],
    index=["In target","Non in target","Tutti"].index(
        st.session_state.get("filtro_target","In target")
    ),
    key="filtro_target",
)
filtro_visto = st.selectbox(
    "👀 Filtra per medici 'VISTO'",
    ["Tutti","Visto","Non Visto","Visita VIP"],
    index=["Tutti","Visto","Non Visto","Visita VIP"].index(
        st.session_state.get("filtro_visto","Non Visto")
    ),
    key="filtro_visto",
)

is_in = df_mmg["in target"].astype(str).str.strip().str.lower() == "x"
df_in_target  = df_mmg[is_in]
df_non_target = df_mmg[~is_in]
df_filtered_target = {
    "In target": df_in_target,
    "Non in target": df_non_target,
    "Tutti": pd.concat([df_in_target, df_non_target])
}[filtro_target]

if filtro_visto == "Visto":
    df_mmg = df_filtered_target[df_filtered_target.apply(is_visited, axis=1)]
elif filtro_visto == "Non Visto":
    df_mmg = df_filtered_target[~df_filtered_target.apply(is_visited, axis=1)]
elif filtro_visto == "Visita VIP":
    df_mmg = df_filtered_target[df_filtered_target.apply(is_vip, axis=1)]
else:
    df_mmg = df_filtered_target.copy()

if st.checkbox("🔔 FREQUENZA", value=False, key="filtro_frequenza"):
    if "frequenza" in df_mmg.columns:
        df_mmg = df_mmg[
            df_mmg["frequenza"].astype(str).str.strip().str.lower() == "x"
        ]

# ---------- FILTRO GIORNO / FASCIA ORARIA --------------------------------------
oggi = datetime.datetime.now(timezone)
giorni_settimana = ["lunedì","martedì","mercoledì","giovedì","venerdì"]
giorni_opz = ["sempre"] + giorni_settimana
giorno_default = giorni_settimana[oggi.weekday()] if oggi.weekday()<5 else "sempre"
giorno_scelto = st.selectbox(
    "📅 Scegli un giorno della settimana",
    giorni_opz,
    index=giorni_opz.index(st.session_state.get("giorno_scelto",giorno_default)),
    key="giorno_scelto",
)

fascia_opts = ["Mattina","Pomeriggio","Mattina e Pomeriggio","Personalizzato"]
fascia_oraria = st.radio(
    "🌞 Scegli la fascia oraria",
    fascia_opts,
    index=fascia_opts.index(st.session_state.get("fascia_oraria","Personalizzato")),
    key="fascia_oraria",
)

if fascia_oraria == "Personalizzato":
    if "custom_start" not in st.session_state or "custom_end" not in st.session_state:
        now = datetime.datetime.now(timezone)
        st.session_state["custom_start"] = now.time()
        st.session_state["custom_end"]   = (now + datetime.timedelta(minutes=15)).time()
    default_min = datetime.datetime.combine(datetime.date.today(), datetime.time(7,0))
    default_max = datetime.datetime.combine(datetime.date.today(), datetime.time(19,0))
    t_start, t_end = st.slider(
        "Seleziona l'intervallo orario",
        min_value=default_min,
        max_value=default_max,
        value=(
            datetime.datetime.combine(datetime.date.today(), st.session_state["custom_start"]),
            datetime.datetime.combine(datetime.date.today(), st.session_state["custom_end"])
        ),
        format="HH:mm",
    )
    custom_start, custom_end = t_start.time(), t_end.time()
    if custom_end <= custom_start:
        st.error("L'orario di fine deve essere successivo all'orario di inizio.")
        st.stop()
else:
    custom_start = custom_end = None

def filtra_giorno_fascia(df_base):
    giorni = giorni_settimana if giorno_scelto == "sempre" else [giorno_scelto]
    cols = []
    for g in giorni:
        if fascia_oraria in ["Mattina","Mattina e Pomeriggio"]:
            cols.append(f"{g} mattina")
        if fascia_oraria in ["Pomeriggio","Mattina e Pomeriggio"]:
            cols.append(f"{g} pomeriggio")
        if fascia_oraria == "Personalizzato":
            for suf in ["mattina","pomeriggio"]:
                col = f"{g} {suf}"
                if col in df_base.columns:
                    cols.append(col)
    cols = [c.lower() for c in cols if c.lower() in df_base.columns]
    if not cols:
        st.error("Le colonne per il filtro giorno/fascia non esistono nel file.")
        st.stop()
    if fascia_oraria == "Personalizzato":
        df_f = df_base[df_base[cols].apply(
            lambda r: any(interval_covers(r[c], custom_start, custom_end) for c in cols),
            axis=1
        )]
        return df_f, cols
    return df_base[df_base[cols].notna().any(axis=1)], cols

df_filtrato, colonne_da_mostrare = filtra_giorno_fascia(df_mmg)

# ---- MOSTRA SOLO COLONNE PERTINENTI ALLA FASCIA ORARIA ATTUALE ----
if fascia_oraria == "Personalizzato":
    # Determina se siamo in mattina o pomeriggio in base all'orario scelto
    ora_rif = custom_start.hour
    if ora_rif < 13:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if "mattina" in c.lower()]
    else:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if "pomeriggio" in c.lower()]

# Se per qualche motivo non resta nessuna colonna (caso limite), mostra comunque tutte
if not colonne_da_mostrare:
    colonne_da_mostrare = [c for c in df_mmg.columns if any(x in c for x in ["mattina","pomeriggio"])]

# Aggiungi sempre colonne fisse per leggibilità
colonne_da_mostrare = ["nome medico","città"] + colonne_da_mostrare + [
    "indirizzo ambulatorio","microarea","provincia","ultima visita"
]


# ---------- FILTRO MICROAREA & PROVINCIA ---------------------------------------
microarea_lista = sorted(df_mmg["microarea"].dropna().unique().tolist())
micro_sel = st.multiselect(
    "Seleziona Microaree",
    options=microarea_lista,
    default=st.session_state.get("microarea_scelta", []),
    key="microarea_scelta",
)
if micro_sel:
    df_filtrato = df_filtrato[df_filtrato["microarea"].isin(micro_sel)]

prov_lista = ["Ovunque"] + sorted(p for p in df_mmg["provincia"].dropna().unique() if p.lower() != "nan")
prov_sel = st.selectbox(
    "📍 Scegli la Provincia",
    prov_lista,
    index=prov_lista.index(st.session_state.get("provincia_scelta","Ovunque")),
    key="provincia_scelta",
)
if prov_sel.lower() != "ovunque":
    df_filtrato = df_filtrato[df_filtrato["provincia"].str.lower() == prov_sel.lower()]


# ---------- FILTRO "MOSTRA SOLO MEDICI VISTI PRIMA DI (INCLUSO)" ---------------
mesi_cap = [m.capitalize() for m in mesi]
mese_limite = st.selectbox(
    "🕰️ Mostra solo medici visti prima di (incluso)",
    ["Nessuno"] + mesi_cap,
    index=0,
    key="mese_limite_visita",
)

if mese_limite != "Nessuno":
    sel_num_limite = month_order[mese_limite.lower()]
    df_filtrato = df_filtrato[
        df_filtrato["ultima visita"]
            .str.lower()
            .map(lambda m: month_order.get(m, 0))
            .le(sel_num_limite)
    ]


# ---------- RICERCA TESTUALE ----------------------------------------------------
query = st.text_input(
    "🔎 Cerca nei risultati",
    placeholder="Inserisci nome, città, microarea, ecc.",
    key="search_query",
)
if query:
    q = query.lower()
    df_filtrato = df_filtrato[
        df_filtrato.drop(columns=["provincia"], errors="ignore")
                  .astype(str)
                  .apply(lambda r: q in " ".join(r).lower(), axis=1)
    ]

# ---------- ORDINAMENTO ---------------------------------------------------------
def min_start(row):
    ts = []
    for c in colonne_da_mostrare:
        if c in ["nome medico","città","indirizzo ambulatorio","microarea","provincia","ultima visita","Visite ciclo"]:
            continue
        stt, _ = parse_interval(row.get(c))
        if stt:
            ts.append(stt)
    return min(ts) if ts else datetime.time(23,59)

df_filtrato["__start"] = df_filtrato.apply(min_start, axis=1)
month_order_sort = {m: i+1 for i, m in enumerate(mesi)}
month_order_sort[""] = 0
df_filtrato["__ult"] = df_filtrato["ultima visita"].str.lower().map(month_order_sort).fillna(0)
df_filtrato = df_filtrato.sort_values(by=["__ult","__start"])
df_filtrato.drop(columns=["__ult","__start"], inplace=True)

# ---------- GESTIONE DATAFRAME VUOTO --------------------------------------------
if df_filtrato.empty:
    st.warning("Nessun risultato corrispondente ai filtri selezionati.")
    st.stop()

# ---------- VISITE CICLO & ASTERISCHI & VIP ------------------------------------
df_filtrato["Visite ciclo"] = df_filtrato.apply(count_visits, axis=1)
df_filtrato["nome medico"]  = df_filtrato.apply(annotate_name, axis=1)

# ---------- VISUALIZZAZIONE & CSV ----------------------------------------------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

# Costruzione opzioni griglia dinamica
gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
gb.configure_default_column(
    sortable=True,
    filter=True,
    resizable=True,
    wrapText=True,
    autoHeight=True,
)
gb.configure_grid_options(domLayout='autoHeight')
gb.configure_grid_options(suppressSizeToFit=False)

# Colonne con larghezza minima, ma auto adattabili
for c in colonne_da_mostrare:
    gb.configure_column(c, minWidth=120, autoHeaderHeight=True)

grid_options = gb.build()
grid_options["onFirstDataRendered"] = """
function(event) {
    event.api.sizeColumnsToFit();
}
"""

# CSS per forzare la griglia full-width su mobile
st.markdown("""
<style>
.ag-theme-streamlit-light, .ag-theme-streamlit-dark {
    width: 100% !important;
    min-width: 100% !important;
    overflow-x: auto;
}
.ag-header-cell-label {
    white-space: normal !important;
    text-overflow: clip !important;
    overflow: visible !important;
}
.ag-cell {
    white-space: normal !important;
    text-overflow: clip !important;
    overflow: visible !important;
}
</style>
""", unsafe_allow_html=True)

# Visualizzazione griglia
AgGrid(
    df_filtrato[colonne_da_mostrare],
    gridOptions=grid_options,
    enable_enterprise_modules=False,
    fit_columns_on_grid_load=True,
    allow_unsafe_jscode=True,
    height=500,
    theme="streamlit",
)

# Pulsante download
st.download_button(
    "📥 Scarica risultati CSV",
    df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    "risultati_medici.csv",
    "text/csv",
)
