import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re
import pytz  # per gestire il fuso orario

import io
import json
import urllib.parse
from typing import Optional

# Imposta il fuso orario desiderato
timezone = pytz.timezone("Europe/Rome")

# Configurazione della pagina
st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")

# ---------- CACHE COMPAT (streamlit vecchio/nuovo) ------------------------------
def _cache_data_decorator():
    """Usa st.cache_data se disponibile, altrimenti fallback a st.cache."""
    try:
        return st.cache_data(show_spinner=False)
    except Exception:
        return st.cache(allow_output_mutation=False)

cache_data = _cache_data_decorator()

# ---------- PERSISTENZA STATO IN URL (ANTI-RESET MOBILE) ------------------------
def _get_query_param(key: str) -> Optional[str]:
    try:
        v = st.query_params.get(key, None)  # Streamlit recente
        if isinstance(v, list):
            return v[0] if v else None
        return v
    except Exception:
        qp = st.experimental_get_query_params()
        v = qp.get(key, None)
        if isinstance(v, list):
            return v[0] if v else None
        return v

def _set_query_param(key: str, value: Optional[str]) -> None:
    try:
        if value is None:
            if key in st.query_params:
                del st.query_params[key]
        else:
            st.query_params[key] = value
    except Exception:
        qp = st.experimental_get_query_params()
        if value is None:
            qp.pop(key, None)
        else:
            qp[key] = value
        st.experimental_set_query_params(**qp)

def _serialize_value(v):
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v

def _deserialize_time(s: str) -> Optional[datetime.time]:
    if not s:
        return None
    s = str(s).strip()
    try:
        if len(s.split(":")) == 2:
            return datetime.datetime.strptime(s, "%H:%M").time()
        return datetime.datetime.strptime(s, "%H:%M:%S").time()
    except Exception:
        return None

def _encode_state(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    return urllib.parse.quote(raw)

def _decode_state(s: str) -> dict:
    raw = urllib.parse.unquote(s)
    return json.loads(raw)

def clear_state_in_url():
    _set_query_param("state", None)

def load_state_from_url():
    s = _get_query_param("state")
    if not s:
        return
    try:
        payload = _decode_state(s)
        for k, v in payload.items():
            if k not in st.session_state:
                if k in ["custom_start", "custom_end"] and isinstance(v, str):
                    t = _deserialize_time(v)
                    st.session_state[k] = t if t is not None else v
                else:
                    st.session_state[k] = v
    except Exception:
        pass

def save_state_to_url(keys):
    payload = {}
    for k in keys:
        if k in st.session_state:
            payload[k] = _serialize_value(st.session_state[k])

    new_state = _encode_state(payload)
    old_state = _get_query_param("state")
    if new_state != old_state:
        _set_query_param("state", new_state)

# Ripristina PRIMA di creare widget con key (fondamentale)
load_state_from_url()

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

/* --- CHIP MICROAREE: checkbox stile pill --- */
div[data-testid="stCheckbox"] label{
    border:1px solid #ced4da;
    background:#f1f3f5;
    padding:5px 8px;
    border-radius:999px;
    display:flex;
    align-items:center;
    gap:6px;
    margin:2px 0;
    cursor:pointer;
    user-select:none;

    /* compattezza */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    font-size: 0.92rem;
}
div[data-testid="stCheckbox"] input{
    transform: scale(1.05);
}

/* selezionato (Chrome/Safari moderni) */
div[data-testid="stCheckbox"] label:has(input:checked){
    background:#007bff;
    border-color:#007bff;
    color:white;
}

/* --- FORZA LE COLONNE MICROAREE A NON COLLASSARE SU MOBILE --- */
/* Qualsiasi "blocco orizzontale" che contiene checkbox: lascia wrap e colonne strette */
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stCheckbox"]) {
  flex-wrap: wrap !important;
  gap: 0.25rem !important;
}

/* Colonne più strette: così su mobile diventano 2-3 per riga */
div[data-testid="stHorizontalBlock"]:has(div[data-testid="stCheckbox"]) > div[data-testid="column"]{
  min-width: 120px !important;  /* se vuoi ancora più fit: 110 */
  flex: 1 1 120px !important;
}

/* Riduce margini interni */
div[data-testid="stCheckbox"]{
  margin: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# ---------- CARICAMENTO FILE ----------------------------------------------------
file = st.file_uploader("Carica il file Excel", type=["xlsx"], key="file_uploader")
if not file:
    st.stop()

# ---------- RESET FILTRI & PULSANTI RAPIDI --------------------------------------
def azzera_filtri():
    # rimuovi checkbox dinamici microaree
    for k in list(st.session_state.keys()):
        if str(k).startswith("micro_chk_"):
            st.session_state.pop(k, None)

    for k in [
        "filtro_spec","filtro_target","filtro_visto","giorno_scelto","fascia_oraria",
        "provincia_scelta","microarea_scelta","search_query","custom_start","custom_end",
        "ciclo_scelto","filtro_ultima_visita","mese_limite_visita"
    ]:
        st.session_state.pop(k, None)

    clear_state_in_url()
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
@cache_data
def load_excel(file_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    df = pd.read_excel(xls, sheet_name="MMG")
    return df

df_mmg = load_excel(file.getvalue())
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

# ---------- FUNZIONI VISITA ----------------------------------------------------
def is_visited(row):
    count = sum(1 for c in visto_cols if row[c] in ["x","v"])
    return count >= 1

def is_vip(row):
    return any(row[c] == "v" for c in visto_cols)

def count_visits(row):
    return sum(1 for c in visto_cols if row[c] in ["x","v"])

def annotate_name(row):
    name = row["nome medico"]
    _ = row.get("Visite ciclo", None)
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

if "ciclo_scelto" in st.session_state and st.session_state["ciclo_scelto"] not in ciclo_opts:
    st.session_state.pop("ciclo_scelto", None)

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
valid_filtro_ult = ["Nessuno"] + lista_mesi_cap

if "filtro_ultima_visita" in st.session_state and st.session_state["filtro_ultima_visita"] not in valid_filtro_ult:
    st.session_state.pop("filtro_ultima_visita", None)

filtro_ultima = st.selectbox(
    "Seleziona mese ultima visita",
    valid_filtro_ult,
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

# ---------- FILTRI PRINCIPALI --------------------------------------------------
default_spec = ["MMG"]
spec_extra = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
spec_options = default_spec + spec_extra

if "filtro_spec" in st.session_state:
    if not isinstance(st.session_state["filtro_spec"], list):
        st.session_state["filtro_spec"] = [st.session_state["filtro_spec"]]
    st.session_state["filtro_spec"] = [x for x in st.session_state["filtro_spec"] if x in spec_options]
    if not st.session_state["filtro_spec"]:
        st.session_state["filtro_spec"] = default_spec

filtro_spec = st.multiselect(
    "🩺 Filtra per tipo di specialista (spec)",
    spec_options,
    default=st.session_state.get("filtro_spec", default_spec),
    key="filtro_spec",
)
df_mmg = df_mmg[df_mmg["spec"].isin(filtro_spec)]

target_opts = ["In target","Non in target","Tutti"]
if "filtro_target" in st.session_state and st.session_state["filtro_target"] not in target_opts:
    st.session_state.pop("filtro_target", None)

filtro_target = st.selectbox(
    "🎯 Scegli il tipo di medici",
    target_opts,
    index=target_opts.index(st.session_state.get("filtro_target","In target")),
    key="filtro_target",
)

visto_opts = ["Tutti","Visto","Non Visto","Visita VIP"]
if "filtro_visto" in st.session_state and st.session_state["filtro_visto"] not in visto_opts:
    st.session_state.pop("filtro_visto", None)

filtro_visto = st.selectbox(
    "👀 Filtra per medici 'VISTO'",
    visto_opts,
    index=visto_opts.index(st.session_state.get("filtro_visto","Non Visto")),
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

# ---------- FILTRO GIORNO / FASCIA ORARIA --------------------------------------
oggi = datetime.datetime.now(timezone)
giorni_settimana = ["lunedì","martedì","mercoledì","giovedì","venerdì"]
giorni_opz = ["sempre"] + giorni_settimana
giorno_default = giorni_settimana[oggi.weekday()] if oggi.weekday()<5 else "sempre"

if "giorno_scelto" in st.session_state and st.session_state["giorno_scelto"] not in giorni_opz:
    st.session_state.pop("giorno_scelto", None)

giorno_scelto = st.selectbox(
    "📅 Scegli un giorno della settimana",
    giorni_opz,
    index=giorni_opz.index(st.session_state.get("giorno_scelto",giorno_default)),
    key="giorno_scelto",
)

fascia_opts = ["Mattina","Pomeriggio","Mattina e Pomeriggio","Personalizzato"]

if "fascia_oraria" in st.session_state and st.session_state["fascia_oraria"] not in fascia_opts:
    st.session_state.pop("fascia_oraria", None)

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
    ora_rif = custom_start.hour
    if ora_rif < 13:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if "mattina" in c.lower()]
    else:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if "pomeriggio" in c.lower()]

if not colonne_da_mostrare:
    colonne_da_mostrare = [c for c in df_mmg.columns if any(x in c for x in ["mattina","pomeriggio"])]

colonne_da_mostrare = ["nome medico","città"] + colonne_da_mostrare + [
    "indirizzo ambulatorio","microarea","provincia","ultima visita"
]

# ---------- MICROAREE: CHIP COMPATTI AFFIANCATI (NO MENU A TENDINA) -------------
microarea_lista = sorted(df_mmg["microarea"].dropna().unique().tolist())

st.write("### Microaree")

b1, b2, b3 = st.columns([1, 1, 2])
with b1:
    if st.button("✅ Tutte", key="micro_all"):
        st.session_state["microarea_scelta"] = microarea_lista.copy()
        for i, _m in enumerate(microarea_lista):
            st.session_state[f"micro_chk_{i}"] = True
        st.rerun()

with b2:
    if st.button("🚫 Nessuna", key="micro_none"):
        st.session_state["microarea_scelta"] = []
        for i, _m in enumerate(microarea_lista):
            st.session_state[f"micro_chk_{i}"] = False
        st.rerun()

with b3:
    st.caption(f"Selezionate: {len(st.session_state.get('microarea_scelta', []))}")

# IMPORTANTISSIMO: mettiamo MOLTE colonne + CSS le rende strette e wrap su mobile
N_COLS_MICRO = 6  # <-- così su mobile diventano 2-3 per riga (non 1)
cols_micro = st.columns(N_COLS_MICRO)

selected_set = set(st.session_state.get("microarea_scelta", []))

for i, m in enumerate(microarea_lista):
    key = f"micro_chk_{i}"
    if key not in st.session_state:
        st.session_state[key] = (m in selected_set)

    with cols_micro[i % N_COLS_MICRO]:
        st.checkbox(m, key=key)

micro_sel = [microarea_lista[i] for i in range(len(microarea_lista)) if st.session_state.get(f"micro_chk_{i}", False)]
st.session_state["microarea_scelta"] = micro_sel

if micro_sel:
    df_filtrato = df_filtrato[df_filtrato["microarea"].isin(micro_sel)]

# ---------- PROVINCIA -----------------------------------------------------------
prov_lista = ["Ovunque"] + sorted(p for p in df_mmg["provincia"].dropna().unique() if p.lower() != "nan")

prov_default = st.session_state.get("provincia_scelta","Ovunque")
if prov_default not in prov_lista:
    prov_default = "Ovunque"

prov_sel = st.selectbox(
    "📍 Scegli la Provincia",
    prov_lista,
    index=prov_lista.index(prov_default),
    key="provincia_scelta",
)

if prov_sel.lower() != "ovunque":
    df_filtrato = df_filtrato[df_filtrato["provincia"].str.lower() == prov_sel.lower()]

# ---------- FILTRO "MOSTRA SOLO MEDICI VISTI PRIMA DI (INCLUSO)" ---------------
mesi_cap = [m.capitalize() for m in mesi]
valid_mese_limite = ["Nessuno"] + mesi_cap

if "mese_limite_visita" in st.session_state and st.session_state["mese_limite_visita"] not in valid_mese_limite:
    st.session_state.pop("mese_limite_visita", None)

mese_limite = st.selectbox(
    "🕰️ Mostra solo medici visti prima di (incluso)",
    valid_mese_limite,
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

# ---------- PERSISTI STATO (SUBITO) ---------------------------------------------
PERSIST_KEYS = [
    "filtro_spec",
    "filtro_target",
    "filtro_visto",
    "giorno_scelto",
    "fascia_oraria",
    "provincia_scelta",
    "microarea_scelta",
    "search_query",
    "custom_start",
    "custom_end",
    "ciclo_scelto",
    "filtro_ultima_visita",
    "mese_limite_visita",
]
save_state_to_url(PERSIST_KEYS)

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

# ---------- VISITE CICLO & VIP --------------------------------------------------
df_filtrato["Visite ciclo"] = df_filtrato.apply(count_visits, axis=1)
df_filtrato["nome medico"]  = df_filtrato.apply(annotate_name, axis=1)

# ---------- VISUALIZZAZIONE & CSV ----------------------------------------------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

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

for c in colonne_da_mostrare:
    gb.configure_column(c, minWidth=120, autoHeaderHeight=True)

grid_options = gb.build()
grid_options["onFirstDataRendered"] = """
function(event) {
    event.api.sizeColumnsToFit();
}
"""

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

AgGrid(
    df_filtrato[colonne_da_mostrare],
    gridOptions=grid_options,
    enable_enterprise_modules=False,
    fit_columns_on_grid_load=True,
    allow_unsafe_jscode=True,
    height=500,
    theme="streamlit",
)

st.download_button(
    "📥 Scarica risultati CSV",
    df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    "risultati_medici.csv",
    "text/csv",
)
