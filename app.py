import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re
import pytz
import io
import json
import urllib.parse
import hashlib
from typing import Optional

# -------------------- COSTANTI --------------------
timezone = pytz.timezone("Europe/Rome")

DEFAULT_SPEC = ["MMG"]
SPEC_EXTRA = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

mesi = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
        "luglio","agosto","settembre","ottobre","novembre","dicembre"]
month_order = {m: i+1 for i, m in enumerate(mesi)}

# Configurazione pagina
st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")

# ---------- CACHE COMPAT (streamlit vecchio/nuovo) ------------------------------
def _cache_data_decorator():
    try:
        return st.cache_data(show_spinner=False)
    except Exception:
        return st.cache(allow_output_mutation=False)

cache_data = _cache_data_decorator()

# ---------- PERSISTENZA STATO IN URL (ANTI-RESET MOBILE) ------------------------
# NOTE: SOLO st.query_params (no experimental), per evitare crash Streamlit moderni.

def _get_query_param(key: str) -> Optional[str]:
    v = st.query_params.get(key, None)
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v

def _set_query_param(key: str, value: Optional[str]) -> None:
    if value is None:
        if key in st.query_params:
            del st.query_params[key]
    else:
        st.query_params[key] = value

def clear_all_query_params():
    # rimuove QUALSIASI parametro in URL (state incluso)
    for k in list(st.query_params.keys()):
        del st.query_params[k]

def clear_state_in_url():
    _set_query_param("state", None)

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

load_state_from_url()

# ---------- ORARIO PERSONALIZZATO (NAIVE per slider Streamlit) -------------------
def _rounded_now_naive_local(tz):
    # prendo "now" nel fuso Roma, poi tolgo tzinfo => naive coerente con slider/combine
    dt = datetime.datetime.now(tz).replace(second=0, microsecond=0)
    return dt.replace(tzinfo=None)

def _slider_bounds_for_date(d: datetime.date):
    min_dt = datetime.datetime.combine(d, datetime.time(7, 0))   # naive
    max_dt = datetime.datetime.combine(d, datetime.time(19, 0))  # naive
    return min_dt, max_dt

def _default_custom_times_rounded(tz):
    now = _rounded_now_naive_local(tz)  # naive
    d = now.date()
    min_dt, max_dt = _slider_bounds_for_date(d)
    latest_start = max_dt - datetime.timedelta(minutes=15)

    if now < min_dt:
        start_dt = min_dt
    elif now > latest_start:
        start_dt = latest_start
    else:
        start_dt = now

    end_dt = start_dt + datetime.timedelta(minutes=15)
    return start_dt.time(), end_dt.time()

def _normalize_custom_times_for_slider(tz, custom_start, custom_end):
    now = _rounded_now_naive_local(tz)  # naive
    d = now.date()
    min_dt, max_dt = _slider_bounds_for_date(d)
    latest_start = max_dt - datetime.timedelta(minutes=15)

    if not isinstance(custom_start, datetime.time) or not isinstance(custom_end, datetime.time):
        cs, ce = _default_custom_times_rounded(tz)
        custom_start, custom_end = cs, ce

    start_dt = datetime.datetime.combine(d, custom_start).replace(second=0, microsecond=0)
    end_dt   = datetime.datetime.combine(d, custom_end).replace(second=0, microsecond=0)

    if end_dt <= start_dt:
        end_dt = start_dt + datetime.timedelta(minutes=15)

    # clamp dentro 07:00–19:00
    if start_dt < min_dt:
        start_dt = min_dt
    if end_dt > max_dt:
        end_dt = max_dt

    # se per via del clamp end <= start, forza 18:45–19:00
    if end_dt <= start_dt:
        start_dt = latest_start
        end_dt = max_dt

    return start_dt, end_dt, min_dt, max_dt

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

/* MICROAREE: compatte (una sotto l'altra) */
#microarea-box div[data-testid="stCheckbox"]{ margin:0 !important; padding:0 !important; }
#microarea-box div[data-testid="stCheckbox"] label{
  margin:0 !important;
  padding:2px 0 !important;
  line-height:1.1 !important;
  font-size:0.95rem !important;
  white-space: normal !important;
}
#microarea-box div[data-testid="stCheckbox"] input{
  transform: scale(0.95);
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
    """
    RESET = boot pulito mantenendo il file caricato:
    - cancella TUTTI i filtri, micro checkbox, orari custom, ricerca, selezioni
    - cancella TUTTI i query params in URL (state incluso)
    - NON imposta nulla a mano: i default vengono ricalcolati come al boot
    - IMPORTANT: niente st.rerun() qui (Streamlit fa rerun dopo il click)
    """
    whitelist = {"file_uploader", "_skip_url_save_once"}

    # cancella tutto lo session_state tranne whitelist
    for k in list(st.session_state.keys()):
        if k not in whitelist:
            st.session_state.pop(k, None)

    # flag: in questo rerun non riscrivere lo state in URL (così rimane pulito)
    st.session_state["_skip_url_save_once"] = True

    # pulisci completamente l'URL
    clear_all_query_params()

def toggle_specialisti():
    current = st.session_state.get("filtro_spec", DEFAULT_SPEC)
    if current == DEFAULT_SPEC:
        st.session_state["filtro_spec"] = SPEC_EXTRA
    else:
        st.session_state["filtro_spec"] = DEFAULT_SPEC
    # niente rerun: dopo click Streamlit rilancia già lo script

def seleziona_mmg():
    st.session_state["filtro_spec"] = DEFAULT_SPEC
    # niente rerun: dopo click Streamlit rilancia già lo script

col1, col2, col3 = st.columns([1,1,2])
with col1:
    st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)
with col2:
    st.button("Specialisti 👨‍⚕️👩‍⚕️", on_click=toggle_specialisti)
with col3:
    st.button("MMG 🩺", on_click=seleziona_mmg)

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
def _parse_time_flexible(s: str) -> Optional[datetime.time]:
    s = str(s).strip()
    try:
        if ":" in s:
            return datetime.datetime.strptime(s, "%H:%M").time()
        return datetime.datetime.strptime(s, "%H").time()
    except Exception:
        return None

def parse_interval(cell_value):
    if pd.isna(cell_value):
        return None, None
    s = str(cell_value).strip()
    m = re.match(r"(\d{1,2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}(?::\d{2})?)", s)
    if not m:
        return None, None
    start_str, end_str = m.groups()

    start_t = _parse_time_flexible(start_str)
    end_t   = _parse_time_flexible(end_str)
    if start_t is None or end_t is None:
        return None, None
    return start_t, end_t

def interval_covers(cell_value, custom_start, custom_end):
    start_t, end_t = parse_interval(cell_value)
    if start_t is None or end_t is None:
        return False
    return start_t <= custom_start and end_t >= custom_end

# ---------- CALCOLO "ULTIMA VISITA" ---------------------------------------------
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

# ---------- CICLO ---------------------------------------------------------------
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

# ---------- FUNZIONI VISITA ----------------------------------------------------
def is_visited(row):
    return sum(1 for c in visto_cols if row.get(c, "") in ["x","v"]) >= 1

def is_vip(row):
    return any(row.get(c, "") == "v" for c in visto_cols)

def count_visits(row):
    return sum(1 for c in visto_cols if row.get(c, "") in ["x","v"])

def annotate_name(row):
    name = row["nome medico"]
    if any(row.get(c, "") == "v" for c in visto_cols):
        name = f"{name} (VIP)"
    return name

# ---------- FILTRO MESE ULTIMA VISITA -------------------------------------------
lista_mesi_cap = [m.capitalize() for m in mesi]
filtro_ultima = st.selectbox(
    "Seleziona mese ultima visita",
    ["Nessuno"] + lista_mesi_cap,
    index=0,
    key="filtro_ultima_visita",
)

df_work = df_mmg.copy()

if filtro_ultima != "Nessuno":
    sel_num = month_order[filtro_ultima.lower()]
    df_work = df_work[
        df_work["ultima visita"]
            .str.lower()
            .map(lambda m: month_order.get(m, 0))
            .le(sel_num)
    ].copy()

# ---------- FILTRI PRINCIPALI --------------------------------------------------
filtro_spec = st.multiselect(
    "🩺 Filtra per tipo di specialista (spec)",
    DEFAULT_SPEC + SPEC_EXTRA,
    default=st.session_state.get("filtro_spec", DEFAULT_SPEC),
    key="filtro_spec",
)
df_work = df_work[df_work["spec"].isin(filtro_spec)].copy()

filtro_target = st.selectbox(
    "🎯 Scegli il tipo di medici",
    ["In target","Non in target","Tutti"],
    index=["In target","Non in target","Tutti"].index(st.session_state.get("filtro_target","In target")),
    key="filtro_target",
)
filtro_visto = st.selectbox(
    "👀 Filtra per medici 'VISTO'",
    ["Tutti","Visto","Non Visto","Visita VIP"],
    index=["Tutti","Visto","Non Visto","Visita VIP"].index(st.session_state.get("filtro_visto","Non Visto")),
    key="filtro_visto",
)

is_in = df_work["in target"].astype(str).str.strip().str.lower() == "x"
df_in_target  = df_work[is_in].copy()
df_non_target = df_work[~is_in].copy()
df_filtered_target = {
    "In target": df_in_target,
    "Non in target": df_non_target,
    "Tutti": pd.concat([df_in_target, df_non_target], ignore_index=True)
}[filtro_target]

if filtro_visto == "Visto":
    df_work = df_filtered_target[df_filtered_target.apply(is_visited, axis=1)].copy()
elif filtro_visto == "Non Visto":
    df_work = df_filtered_target[~df_filtered_target.apply(is_visited, axis=1)].copy()
elif filtro_visto == "Visita VIP":
    df_work = df_filtered_target[df_filtered_target.apply(is_vip, axis=1)].copy()
else:
    df_work = df_filtered_target.copy()

# ---------- FILTRO GIORNO / FASCIA ORARIA --------------------------------------
oggi = datetime.datetime.now(timezone)
giorni_settimana = ["lunedì","martedì","mercoledì","giovedì","venerdì"]
giorni_opz = ["sempre"] + giorni_settimana
giorno_default = giorni_settimana[oggi.weekday()] if oggi.weekday() < 5 else "sempre"

giorno_scelto = st.selectbox(
    "📅 Scegli un giorno della settimana",
    giorni_opz,
    index=giorni_opz.index(st.session_state.get("giorno_scelto", giorno_default)),
    key="giorno_scelto",
)

fascia_opts = ["Mattina","Pomeriggio","Mattina e Pomeriggio","Personalizzato"]
fascia_oraria = st.radio(
    "🌞 Scegli la fascia oraria",
    fascia_opts,
    index=fascia_opts.index(st.session_state.get("fascia_oraria", "Personalizzato")),
    key="fascia_oraria",
)

if fascia_oraria == "Personalizzato":
    start_dt, end_dt, default_min, default_max = _normalize_custom_times_for_slider(
        timezone,
        st.session_state.get("custom_start"),
        st.session_state.get("custom_end"),
    )
    st.session_state["custom_start"] = start_dt.time()
    st.session_state["custom_end"]   = end_dt.time()

    t_start, t_end = st.slider(
        "Seleziona l'intervallo orario",
        min_value=default_min,
        max_value=default_max,
        value=(start_dt, end_dt),
        format="HH:mm",
    )
    custom_start, custom_end = t_start.time(), t_end.time()
    st.session_state["custom_start"] = custom_start
    st.session_state["custom_end"]   = custom_end

    if custom_end <= custom_start:
        st.error("L'orario di fine deve essere successivo all'orario di inizio.")
        st.stop()
else:
    custom_start = custom_end = None
    st.session_state.pop("custom_start", None)
    st.session_state.pop("custom_end", None)

def filtra_giorno_fascia(df_base: pd.DataFrame):
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
            lambda r: any(interval_covers(r.get(c), custom_start, custom_end) for c in cols),
            axis=1
        )].copy()
        return df_f, cols

    df_f = df_base[df_base[cols].notna().any(axis=1)].copy()
    return df_f, cols

df_filtrato, colonne_da_mostrare = filtra_giorno_fascia(df_work)

if fascia_oraria == "Personalizzato":
    ora_rif = custom_start.hour
    if ora_rif < 13:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if "mattina" in c.lower()]
    else:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if "pomeriggio" in c.lower()]

if not colonne_da_mostrare:
    colonne_da_mostrare = [c for c in df_work.columns if any(x in c for x in ["mattina","pomeriggio"])]

colonne_da_mostrare = ["nome medico","città"] + colonne_da_mostrare + [
    "indirizzo ambulatorio","microarea","provincia","ultima visita"
]

# ---------- MICROAREE (verticali, compatte, ordine richiesto) -------------------
st.write("### Microaree")

microarea_raw = df_work.get("microarea", pd.Series([], dtype=str)).dropna().astype(str).str.strip().tolist()
microarea_lista = list({m for m in microarea_raw if m and m.lower() != "nan"})

priority = {"FM": 0, "MC": 1, "SBT": 2, "AP": 3, "MTPR": 4, "TER": 5}

def micro_sort_key(s: str):
    up = s.strip().upper()
    code = re.split(r"[^A-Z]", up)[0]
    grp = priority.get(code, 999)
    return (grp, up.casefold())

microarea_lista = sorted(microarea_lista, key=micro_sort_key)

b1, b2, b3 = st.columns([1, 1, 2])
with b1:
    if st.button("✅ Tutte", key="micro_all"):
        st.session_state["microarea_scelta"] = microarea_lista.copy()
        for m in microarea_lista:
            mk = "micro_chk_" + hashlib.md5(m.encode("utf-8")).hexdigest()[:10]
            st.session_state[mk] = True
        st.rerun()

with b2:
    if st.button("🚫 Nessuna", key="micro_none"):
        st.session_state["microarea_scelta"] = []
        for m in microarea_lista:
            mk = "micro_chk_" + hashlib.md5(m.encode("utf-8")).hexdigest()[:10]
            st.session_state[mk] = False
        st.rerun()

with b3:
    st.caption(f"Selezionate: {len(st.session_state.get('microarea_scelta', []))}")

st.markdown('<div id="microarea-box">', unsafe_allow_html=True)

selected_set = set(st.session_state.get("microarea_scelta", []))
micro_sel = []

for m in microarea_lista:
    mk = "micro_chk_" + hashlib.md5(m.encode("utf-8")).hexdigest()[:10]
    if mk not in st.session_state:
        st.session_state[mk] = (m in selected_set)

    if st.checkbox(m, key=mk):
        micro_sel.append(m)

st.markdown('</div>', unsafe_allow_html=True)

st.session_state["microarea_scelta"] = micro_sel
if micro_sel and "microarea" in df_filtrato.columns:
    df_filtrato = df_filtrato[df_filtrato["microarea"].isin(micro_sel)].copy()

# ---------- PROVINCIA -----------------------------------------------------------
prov_raw = df_work.get("provincia", pd.Series([], dtype=str)).dropna().unique().tolist()
prov_lista = ["Ovunque"] + sorted([p for p in prov_raw if str(p).lower() != "nan"])

prov_sel = st.selectbox(
    "📍 Scegli la Provincia",
    prov_lista,
    index=prov_lista.index(st.session_state.get("provincia_scelta","Ovunque")) if st.session_state.get("provincia_scelta","Ovunque") in prov_lista else 0,
    key="provincia_scelta",
)

if prov_sel.lower() != "ovunque" and "provincia" in df_filtrato.columns:
    df_filtrato = df_filtrato[df_filtrato["provincia"].str.lower() == prov_sel.lower()].copy()

# ---------- FILTRO "MOSTRA SOLO MEDICI VISTI PRIMA DI (INCLUSO)" ----------------
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
    ].copy()

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
    ].copy()

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

# Se arrivi da RESET: non riscrivere lo state in URL (e lascialo pulito).
if st.session_state.pop("_skip_url_save_once", False):
    clear_all_query_params()
else:
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

df_filtrato = df_filtrato.copy()
df_filtrato["__start"] = df_filtrato.apply(min_start, axis=1)

month_order_sort = {m: i+1 for i, m in enumerate(mesi)}
month_order_sort[""] = 0
df_filtrato["__ult"] = df_filtrato["ultima visita"].str.lower().map(month_order_sort).fillna(0)

df_filtrato = df_filtrato.sort_values(by=["__ult","__start"]).copy()
df_filtrato.drop(columns=["__ult","__start"], inplace=True, errors="ignore")

# ---------- GESTIONE DATAFRAME VUOTO --------------------------------------------
if df_filtrato.empty:
    st.warning("Nessun risultato corrispondente ai filtri selezionati.")
    st.stop()

# ---------- VISITE CICLO & VIP --------------------------------------------------
df_filtrato["Visite ciclo"] = df_filtrato.apply(count_visits, axis=1)
df_filtrato["nome medico"]  = df_filtrato.apply(annotate_name, axis=1)

# ---------- VISUALIZZAZIONE & CSV ----------------------------------------------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].astype(str).str.lower().nunique()} 🧮")
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
