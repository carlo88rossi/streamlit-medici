import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
from streamlit_mic_recorder import mic_recorder

import datetime
import re
import pytz
import io
import json
import urllib.parse
import hashlib
import os
import tempfile

from typing import Optional, Any
from openai import OpenAI

# -------------------- COSTANTI --------------------
timezone = pytz.timezone("Europe/Rome")

DEFAULT_SPEC = ["MMG"]
SPEC_EXTRA = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]

mesi = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"
]
month_order = {m: i + 1 for i, m in enumerate(mesi)}

giorni_settimana = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"]

TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
VOICE_PARSER_MODEL = "gpt-4o-mini"

st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")


# ---------- CACHE COMPAT --------------------------------------------------------
def _cache_data_decorator():
    try:
        return st.cache_data(show_spinner=False)
    except Exception:
        return st.cache(allow_output_mutation=False)


cache_data = _cache_data_decorator()


# ---------- OPENAI --------------------------------------------------------------
def get_openai_client() -> OpenAI:
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Manca OPENAI_API_KEY. Inseriscila in .streamlit/secrets.toml oppure come variabile d'ambiente."
        )
    return OpenAI(api_key=api_key)


def transcribe_voice_command_from_bytes(audio_bytes: bytes, suffix: str = ".webm") -> str:
    client = get_openai_client()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model=TRANSCRIBE_MODEL,
                file=f,
            )
        text = getattr(transcript, "text", None)
        if not text:
            raise ValueError("Trascrizione vuota.")
        return text.strip()
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def _resolve_relative_day(text: str, now: datetime.datetime) -> Optional[str]:
    text = text.lower().strip()

    if "oggi" in text:
        wd = now.weekday()
        if 0 <= wd <= 4:
            return giorni_settimana[wd]
        return "sempre"

    if "domani" in text:
        wd = (now.weekday() + 1) % 7
        if 0 <= wd <= 4:
            return giorni_settimana[wd]
        return None

    if "dopodomani" in text:
        wd = (now.weekday() + 2) % 7
        if 0 <= wd <= 4:
            return giorni_settimana[wd]
        return None

    return None


def interpret_voice_command_to_filters(
    command_text: str,
    province_list: list[str],
    microarea_list: list[str],
) -> dict:
    client = get_openai_client()
    now = datetime.datetime.now(timezone)

    developer_prompt = f"""
Sei un interprete di comandi vocali per un'app Streamlit che filtra medici.

Data e ora Europe/Rome: {now.strftime("%Y-%m-%d %H:%M")}
Giorni supportati dall'app: {giorni_settimana} + "sempre"

Obiettivo:
Trasforma il comando utente in un JSON rigoroso con i filtri da applicare.

Regole:
- Non inventare valori.
- Se l'utente dice "oggi", "domani", "dopodomani", risolvili rispetto alla data corrente.
- L'app supporta solo lunedì-venerdì o "sempre".
- Se l'utente chiede sabato o domenica, imposta action="nessuna_azione" e spiega il motivo.
- Se l'utente dice "domattina", imposta giorno_scelto coerente e fascia_oraria="Mattina".
- Se dice "oggi pomeriggio", imposta il giorno corrente e fascia_oraria="Pomeriggio".
- Se dice "mattina e pomeriggio", usa fascia_oraria="Mattina e Pomeriggio".
- Se dice "MMG" o "medici di base", usa filtro_spec=["MMG"].
- Se dice "specialisti", usa filtro_spec={SPEC_EXTRA}.
- Se dice "ortopedici" usa ["ORT"].
- Se dice "fisiatri" usa ["FIS"].
- Se dice "reumatologi" usa ["REU"].
- Se dice "dolore" o "algologi" usa ["DOL"].
- Se dice "otorini" usa ["OTO"].
- Se dice "dermatologi" usa ["DER"].
- Se dice "internisti" usa ["INT"].
- Se dice "endocrinologi" usa ["END"].
- Se dice "diabetologi" usa ["DIA"].
- Se dice "non visti", usa filtro_visto="Non Visto".
- Se dice "visti", usa filtro_visto="Visto".
- Se dice "vip", usa filtro_visto="Visita VIP".
- Se dice "in target", usa filtro_target="In target".
- Se dice "non in target", usa filtro_target="Non in target".
- Se dice "tutti", usa solo se chiaramente riferito a filtro_target o ciclo.
- Se dice "azzera tutto", "resetta", "reset", usa action="azzera_filtri".
- Se l'utente cita una provincia inesistente, action="nessuna_azione".
- Se cita una microarea inesistente, action="nessuna_azione".
- Se dice un intervallo tipo "dalle 9 alle 10", usa fascia_oraria="Personalizzato", custom_start="09:00", custom_end="10:00".
- Se cita una città o testo libero non mappabile a un filtro strutturato, puoi usare search_query.
- Compila solo i campi rilevanti; gli altri lasciali null.
- Output: SOLO una chiamata funzione.
"""

    tools = [
        {
            "type": "function",
            "function": {
                "name": "set_filters_from_voice",
                "description": "Converte un comando vocale nei filtri dell'app medici.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["apply_filters", "azzera_filtri", "nessuna_azione"],
                        },
                        "message": {"type": ["string", "null"]},
                        "giorno_scelto": {
                            "type": ["string", "null"],
                            "enum": giorni_settimana + ["sempre", None],
                        },
                        "fascia_oraria": {
                            "type": ["string", "null"],
                            "enum": ["Mattina", "Pomeriggio", "Mattina e Pomeriggio", "Personalizzato", None],
                        },
                        "custom_start": {"type": ["string", "null"]},
                        "custom_end": {"type": ["string", "null"]},
                        "provincia_scelta": {
                            "type": ["string", "null"],
                            "enum": province_list + [None],
                        },
                        "microarea_scelta": {
                            "type": ["array", "null"],
                            "items": {"type": "string", "enum": microarea_list},
                        },
                        "filtro_visto": {
                            "type": ["string", "null"],
                            "enum": ["Tutti", "Visto", "Non Visto", "Visita VIP", None],
                        },
                        "filtro_target": {
                            "type": ["string", "null"],
                            "enum": ["In target", "Non in target", "Tutti", None],
                        },
                        "filtro_spec": {
                            "type": ["array", "null"],
                            "items": {"type": "string", "enum": DEFAULT_SPEC + SPEC_EXTRA},
                        },
                        "ciclo_scelto": {
                            "type": ["string", "null"],
                            "enum": [
                                "Tutti",
                                "Ciclo 1 (Gen-Feb-Mar)",
                                "Ciclo 2 (Apr-Mag-Giu)",
                                "Ciclo 3 (Lug-Ago-Set)",
                                "Ciclo 4 (Ott-Nov-Dic)",
                                None,
                            ],
                        },
                        "search_query": {"type": ["string", "null"]},
                    },
                    "required": [
                        "action",
                        "message",
                        "giorno_scelto",
                        "fascia_oraria",
                        "custom_start",
                        "custom_end",
                        "provincia_scelta",
                        "microarea_scelta",
                        "filtro_visto",
                        "filtro_target",
                        "filtro_spec",
                        "ciclo_scelto",
                        "search_query",
                    ],
                },
            },
        }
    ]

    response = client.chat.completions.create(
        model=VOICE_PARSER_MODEL,
        messages=[
            {"role": "system", "content": developer_prompt},
            {"role": "user", "content": command_text},
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "set_filters_from_voice"}},
    )

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise ValueError("Nessun comando strutturato restituito dal modello.")

    args = json.loads(tool_calls[0].function.arguments)

    if not args.get("giorno_scelto"):
        resolved_day = _resolve_relative_day(command_text, now)
        if resolved_day:
            args["giorno_scelto"] = resolved_day

    return args


# ---------- PERSISTENZA STATO IN URL --------------------------------------------
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


# ---------- ORARIO PERSONALIZZATO -----------------------------------------------
def _rounded_now_naive_local(tz):
    dt = datetime.datetime.now(tz).replace(second=0, microsecond=0)
    return dt.replace(tzinfo=None)


def _slider_bounds_for_date(d: datetime.date):
    min_dt = datetime.datetime.combine(d, datetime.time(7, 0))
    max_dt = datetime.datetime.combine(d, datetime.time(19, 0))
    return min_dt, max_dt


def _default_custom_times_rounded(tz):
    now = _rounded_now_naive_local(tz)
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
    now = _rounded_now_naive_local(tz)
    d = now.date()
    min_dt, max_dt = _slider_bounds_for_date(d)
    latest_start = max_dt - datetime.timedelta(minutes=15)

    if not isinstance(custom_start, datetime.time) or not isinstance(custom_end, datetime.time):
        cs, ce = _default_custom_times_rounded(tz)
        custom_start, custom_end = cs, ce

    start_dt = datetime.datetime.combine(d, custom_start).replace(second=0, microsecond=0)
    end_dt = datetime.datetime.combine(d, custom_end).replace(second=0, microsecond=0)

    if end_dt <= start_dt:
        end_dt = start_dt + datetime.timedelta(minutes=15)

    if start_dt < min_dt:
        start_dt = min_dt
    if end_dt > max_dt:
        end_dt = max_dt

    if end_dt <= start_dt:
        start_dt = latest_start
        end_dt = max_dt

    return start_dt, end_dt, min_dt, max_dt


# ---------- CSS -----------------------------------------------------------------
st.markdown("""
<style>
body {background:#f8f9fa;color:#212529;}
[data-testid="stAppViewContainer"] {background:#f8f9fa;}
h1 {
    font-family:'Helvetica Neue',sans-serif;
    font-size:2.3rem;
    text-align:center;
    color:#007bff;
    margin-bottom:1.2rem;
}
div.stButton > button {
    background:#007bff;
    color:#fff;
    border:none;
    border-radius:10px;
    padding:0.55rem 1rem;
    font-size:1rem;
}
div.stButton > button:hover {background:#0056b3;}
.ag-root-wrapper {
    border:1px solid #dee2e6 !important;
    border-radius:10px;
    overflow:hidden;
}
.ag-header-cell-label {font-weight:bold;color:#343a40;}
.ag-row {font-size:0.9rem;}

#microarea-box div[data-testid="stCheckbox"] { margin:0 !important; padding:0 !important; }
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

.voice-wrap {
    margin: 8px 0 18px 0;
    padding: 16px 18px;
    border-radius: 18px;
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.06);
    box-shadow: 0 8px 24px rgba(23,35,59,0.08);
}
.voice-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1f2937;
    margin-bottom: 6px;
}
.voice-sub {
    font-size: 0.92rem;
    color: #6b7280;
    margin-bottom: 10px;
}
.voice-result {
    margin-top: 12px;
    padding: 12px 14px;
    border-radius: 12px;
    background: #f8fafc;
    border: 1px solid rgba(0,0,0,0.05);
}
.voice-label {
    font-weight: 700;
    color: #374151;
}
</style>
""", unsafe_allow_html=True)

st.title("📋 Filtro Medici - Ricevimento Settimanale")


# ---------- CARICAMENTO FILE ----------------------------------------------------
file = st.file_uploader("Carica il file Excel", type=["xlsx"], key="file_uploader")

if file is not None:
    try:
        st.session_state["uploaded_file_bytes"] = file.getvalue()
    except Exception:
        pass

file_bytes = st.session_state.get("uploaded_file_bytes", None)

if file_bytes is None:
    st.stop()


# ---------- RESET FILTRI & PULSANTI RAPIDI --------------------------------------
def azzera_filtri():
    try:
        clear_all_query_params()
    except Exception:
        pass

    preserved_file = st.session_state.get("uploaded_file_bytes", None)

    today = datetime.datetime.now(timezone)
    default_cycle_idx = 1 + (today.month - 1) // 3
    ciclo_opts = [
        "Tutti",
        "Ciclo 1 (Gen-Feb-Mar)",
        "Ciclo 2 (Apr-Mag-Giu)",
        "Ciclo 3 (Lug-Ago-Set)",
        "Ciclo 4 (Ott-Nov-Dic)",
    ]
    ciclo_default = ciclo_opts[default_cycle_idx]

    giorno_default = giorni_settimana[today.weekday()] if today.weekday() < 5 else "sempre"

    defaults = {
        "ciclo_scelto": ciclo_default,
        "filtro_ultima_visita": "Nessuno",
        "mese_limite_visita": "Nessuno",
        "filtro_spec": DEFAULT_SPEC.copy(),
        "filtro_target": "In target",
        "filtro_visto": "Non Visto",
        "giorno_scelto": giorno_default,
        "fascia_oraria": "Personalizzato",
        "custom_start": None,
        "custom_end": None,
        "provincia_scelta": "Ovunque",
        "microarea_scelta": [],
        "search_query": "",
        "prov_escludi": [],
    }

    for k in list(st.session_state.keys()):
        try:
            del st.session_state[k]
        except Exception:
            pass

    if preserved_file is not None:
        st.session_state["uploaded_file_bytes"] = preserved_file

    for k, v in defaults.items():
        st.session_state[k] = v

    try:
        for sk in list(st.session_state.keys()):
            if sk.startswith("micro_chk_"):
                st.session_state[sk] = False
    except Exception:
        pass

    st.session_state["_skip_url_save_once"] = True


def toggle_specialisti():
    current = st.session_state.get("filtro_spec", DEFAULT_SPEC)
    if current == DEFAULT_SPEC:
        st.session_state["filtro_spec"] = SPEC_EXTRA
    else:
        st.session_state["filtro_spec"] = DEFAULT_SPEC


def seleziona_mmg():
    st.session_state["filtro_spec"] = DEFAULT_SPEC


col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)
with col2:
    st.button("Specialisti 👨‍⚕️👩‍⚕️", on_click=toggle_specialisti)
with col3:
    st.button("MMG 🩺", on_click=seleziona_mmg)


# ---------- LETTURA EXCEL -------------------------------------------------------
def _normalize_columns(cols) -> list[str]:
    return [str(c).strip().lower() for c in cols]


def _is_compatible_mmg_sheet(df: pd.DataFrame) -> bool:
    cols = _normalize_columns(df.columns)

    if "nome medico" not in cols:
        return False

    months_present = sum(1 for m in mesi if m in cols)
    if months_present >= 6:
        return True

    return False


@cache_data
def load_excel(file_bytes: bytes):
    bio = io.BytesIO(file_bytes)

    try:
        xls = pd.ExcelFile(bio)
    except Exception as e:
        raise ValueError(f"Impossibile aprire il file Excel: {e}")

    preferred_sheets = ["MMG", "MMG_Tabella 1"]

    for sheet_name in preferred_sheets:
        if sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                if _is_compatible_mmg_sheet(df):
                    return df
            except Exception:
                pass

    compatible_candidates = []

    for sheet_name in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            if _is_compatible_mmg_sheet(df):
                compatible_candidates.append((sheet_name, df))
        except Exception:
            continue

    if len(compatible_candidates) == 1:
        return compatible_candidates[0][1]

    if len(compatible_candidates) > 1:
        candidate_names = [name for name, _ in compatible_candidates]
        raise ValueError(
            "Trovati più fogli compatibili con la struttura MMG. "
            f"Fogli compatibili: {candidate_names}. "
            "Rendi univoco il nome del foglio oppure limita il file a un solo foglio MMG."
        )

    raise ValueError(
        "Foglio MMG non trovato. "
        f"Fogli disponibili: {xls.sheet_names}. "
        "Atteso un foglio chiamato 'MMG' oppure un foglio con colonne compatibili "
        "(es. 'nome medico' e mesi da gennaio a dicembre)."
    )


try:
    df_mmg = load_excel(file_bytes)
except Exception as e:
    st.error(f"Errore nel caricamento del file Excel: {e}")
    st.stop()

df_mmg.columns = df_mmg.columns.str.lower()

if "provincia" in df_mmg.columns:
    df_mmg["provincia"] = df_mmg["provincia"].astype(str).str.strip()
if "microarea" in df_mmg.columns:
    df_mmg["microarea"] = df_mmg["microarea"].astype(str).str.strip()


def build_all_province(df: pd.DataFrame) -> list[str]:
    vals = (
        df.get("provincia", pd.Series([], dtype=str))
        .dropna()
        .astype(str)
        .str.strip()
    )
    return ["Ovunque"] + sorted([x for x in vals.unique().tolist() if x and x.lower() != "nan"])


def build_all_microaree(df: pd.DataFrame) -> list[str]:
    vals = (
        df.get("microarea", pd.Series([], dtype=str))
        .dropna()
        .astype(str)
        .str.strip()
    )
    raw_list = [x for x in vals.unique().tolist() if x and x.lower() != "nan"]

    parent_codes_with_variant = set()
    for x in raw_list:
        up = x.strip().upper()
        m = re.match(r"^([A-Z]{2}\d{2})\s*\(", up)
        if m:
            parent_codes_with_variant.add(m.group(1))

    filtered = []
    for x in raw_list:
        up = x.strip().upper()
        if up in parent_codes_with_variant:
            continue
        filtered.append(x)

    priority = {"FM": 0, "MC": 1, "SBT": 2, "AP": 3, "MTPR": 4, "TER": 5}

    def micro_sort_key(s: str):
        up = s.strip().upper()
        code = re.split(r"[^A-Z]", up)[0]
        grp = priority.get(code, 999)
        return (grp, up.casefold())

    return sorted(filtered, key=micro_sort_key)


all_province = build_all_province(df_mmg)
all_microaree = build_all_microaree(df_mmg)


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
    end_t = _parse_time_flexible(end_str)
    if start_t is None or end_t is None:
        return None, None
    return start_t, end_t


def interval_covers(cell_value, custom_start, custom_end):
    start_t, end_t = parse_interval(cell_value)
    if start_t is None or end_t is None:
        return False
    return start_t <= custom_start and end_t >= custom_end


# ---------- CALCOLO ULTIMA VISITA ----------------------------------------------
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


# ---------- APPLY VOICE FILTERS -------------------------------------------------
def _parse_hhmm_or_none(value):
    if value is None:
        return None
    try:
        return datetime.datetime.strptime(str(value), "%H:%M").time()
    except Exception:
        return None


def apply_voice_filters(payload: dict):
    action = payload.get("action")

    if action == "azzera_filtri":
        azzera_filtri()
        return "Filtri azzerati."

    if action == "nessuna_azione":
        return payload.get("message") or "Comando non applicato."

    if action != "apply_filters":
        return "Nessuna modifica applicata."

    today = datetime.datetime.now(timezone)
    default_cycle_idx = 1 + (today.month - 1) // 3
    ciclo_opts_local = [
        "Tutti",
        "Ciclo 1 (Gen-Feb-Mar)",
        "Ciclo 2 (Apr-Mag-Giu)",
        "Ciclo 3 (Lug-Ago-Set)",
        "Ciclo 4 (Ott-Nov-Dic)",
    ]
    ciclo_default = ciclo_opts_local[default_cycle_idx]
    giorno_default = giorni_settimana[today.weekday()] if today.weekday() < 5 else "sempre"

    st.session_state["ciclo_scelto"] = ciclo_default
    st.session_state["filtro_ultima_visita"] = "Nessuno"
    st.session_state["mese_limite_visita"] = "Nessuno"
    st.session_state["filtro_spec"] = DEFAULT_SPEC.copy()
    st.session_state["filtro_target"] = "In target"
    st.session_state["filtro_visto"] = "Non Visto"
    st.session_state["giorno_scelto"] = giorno_default
    st.session_state["fascia_oraria"] = "Personalizzato"
    st.session_state["custom_start"] = None
    st.session_state["custom_end"] = None
    st.session_state["provincia_scelta"] = "Ovunque"
    st.session_state["microarea_scelta"] = []
    st.session_state["search_query"] = ""
    st.session_state["prov_escludi"] = []

    for m in all_microaree:
        mk = "micro_chk_" + hashlib.md5(m.encode("utf-8")).hexdigest()[:10]
        st.session_state[mk] = False

    scalar_keys = [
        "giorno_scelto",
        "provincia_scelta",
        "filtro_visto",
        "filtro_target",
        "ciclo_scelto",
        "search_query",
    ]

    for key in scalar_keys:
        value = payload.get(key)
        if value is not None:
            st.session_state[key] = value

    filtro_spec = payload.get("filtro_spec")
    if isinstance(filtro_spec, list) and filtro_spec:
        valid_specs = [x for x in filtro_spec if x in (DEFAULT_SPEC + SPEC_EXTRA)]
        if valid_specs:
            st.session_state["filtro_spec"] = valid_specs

    micro_sel = payload.get("microarea_scelta")
    if isinstance(micro_sel, list):
        st.session_state["microarea_scelta"] = micro_sel
        for m in all_microaree:
            mk = "micro_chk_" + hashlib.md5(m.encode("utf-8")).hexdigest()[:10]
            st.session_state[mk] = m in micro_sel

    fascia = payload.get("fascia_oraria")
    if fascia is not None:
        st.session_state["fascia_oraria"] = fascia

    if fascia == "Personalizzato":
        t1 = _parse_hhmm_or_none(payload.get("custom_start"))
        t2 = _parse_hhmm_or_none(payload.get("custom_end"))
        if t1 and t2 and t2 > t1:
            st.session_state["custom_start"] = t1
            st.session_state["custom_end"] = t2
        else:
            st.session_state["custom_start"] = None
            st.session_state["custom_end"] = None

    return payload.get("message") or "Filtri aggiornati da comando vocale."


# ---------- COMANDO VOCALE AI ---------------------------------------------------
st.markdown("""
<div class="voice-wrap">
  <div class="voice-title">🎙️ Comando vocale AI</div>
  <div class="voice-sub">
    Premi il pulsante, parla, poi ripremilo per fermare.<br>
    Appena fermi la registrazione, il comando parte da solo.
  </div>
</div>
""", unsafe_allow_html=True)

audio = mic_recorder(
    start_prompt="🎙️ Avvia comando vocale",
    stop_prompt="⏹️ Ferma e invia",
    just_once=True,
    format="webm",
    key="voice_recorder_v2",
)


def _get_audio_id(audio_dict: Any):
    if not isinstance(audio_dict, dict):
        return None
    return audio_dict.get("id")


audio_id = _get_audio_id(audio)

if "last_processed_audio_id" not in st.session_state:
    st.session_state["last_processed_audio_id"] = None

if audio and audio_id and audio_id != st.session_state["last_processed_audio_id"]:
    try:
        with st.spinner("Trascrivo e applico i filtri..."):
            transcript = transcribe_voice_command_from_bytes(
                audio_bytes=audio["bytes"],
                suffix=".webm",
            )

            payload = interpret_voice_command_to_filters(
                command_text=transcript,
                province_list=all_province,
                microarea_list=all_microaree,
            )

            msg = apply_voice_filters(payload)

            st.session_state["last_voice_transcript"] = transcript
            st.session_state["last_voice_payload"] = payload
            st.session_state["voice_feedback"] = msg
            st.session_state["last_processed_audio_id"] = audio_id

        st.rerun()

    except Exception as e:
        st.session_state["voice_feedback"] = f"Errore comando vocale: {e}"
        st.session_state["last_processed_audio_id"] = audio_id

if st.session_state.get("last_voice_transcript") or st.session_state.get("voice_feedback"):
    st.markdown('<div class="voice-result">', unsafe_allow_html=True)

    if st.session_state.get("last_voice_transcript"):
        st.markdown(
            f"<div><span class='voice-label'>Hai detto:</span> "
            f"{st.session_state['last_voice_transcript']}</div>",
            unsafe_allow_html=True,
        )

    if st.session_state.get("voice_feedback"):
        st.markdown(
            f"<div style='margin-top:6px;'><span class='voice-label'>Esito:</span> "
            f"{st.session_state['voice_feedback']}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

st.caption("Esempi: “chi riceve domattina in microarea FM” · “solo MMG oggi pomeriggio” · “azzera tutto”")


# ---------- WIDGET FILTRI -------------------------------------------------------
ciclo_scelto = st.selectbox(
    f"💠 SELEZIONA CICLO ({today.strftime('%B').capitalize()} {today.year})",
    ciclo_opts,
    index=default_cycle_idx,
    key="ciclo_scelto",
)

month_cycles = {
    "Ciclo 1 (Gen-Feb-Mar)": ["gennaio", "febbraio", "marzo"],
    "Ciclo 2 (Apr-Mag-Giu)": ["aprile", "maggio", "giugno"],
    "Ciclo 3 (Lug-Ago-Set)": ["luglio", "agosto", "settembre"],
    "Ciclo 4 (Ott-Nov-Dic)": ["ottobre", "novembre", "dicembre"],
}
visto_cols = (
    [m for m in mesi if m in df_mmg.columns]
    if ciclo_scelto == "Tutti"
    else month_cycles[ciclo_scelto]
)


# ---------- % MMG VISTI ---------------------------------------------------------
try:
    ciclo_cols = [c for c in visto_cols if c in df_mmg.columns]
    if ciclo_cols and "nome medico" in df_mmg.columns:
        df_tmp = df_mmg.copy()
        df_tmp["_nome_norm"] = df_tmp["nome medico"].astype(str).str.strip().str.lower()

        is_mmg = df_tmp.get("spec", pd.Series("", index=df_tmp.index)).astype(str).str.strip().str.upper() == "MMG"
        is_in_target = df_tmp.get("in target", pd.Series("", index=df_tmp.index)).astype(str).str.strip().str.lower() == "x"
        base_mask = is_mmg & is_in_target

        total_mmg_target = int(df_tmp[base_mask]["_nome_norm"].nunique())

        def _row_has_visit_vals(vals):
            for v in vals:
                if str(v).strip().lower() in ["x", "v"]:
                    return True
            return False

        seen_rows = df_tmp[ciclo_cols].apply(lambda r: _row_has_visit_vals(r.values), axis=1)
        seen_count = int(df_tmp[base_mask & seen_rows]["_nome_norm"].nunique())

        pct = int(round((seen_count / total_mmg_target) * 100)) if total_mmg_target > 0 else 0

        st.markdown(f"""
        <style>
        .mmg-mini-card {{
            padding: 12px 14px;
            border-radius: 12px;
            box-shadow: 0 6px 18px rgba(23,35,59,0.08);
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.04);
            margin: 6px 0 14px 0;
        }}
        .mmg-mini-top {{
            display:flex;
            justify-content:space-between;
            align-items:baseline;
            gap:10px;
        }}
        .mmg-mini-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #495057;
            margin: 0;
        }}
        .mmg-mini-pct {{
            font-size: 1.6rem;
            font-weight: 800;
            color: #0d6efd;
            margin: 0;
            line-height: 1;
        }}
        .mmg-mini-bar-outer {{
            height: 14px;
            background: #e9ecef;
            border-radius: 999px;
            overflow: hidden;
            margin-top: 10px;
        }}
        .mmg-mini-bar-inner {{
            height: 100%;
            width: {pct}%;
            background: linear-gradient(90deg, #198754, #0d6efd);
            border-radius: 999px;
            transition: width 500ms ease;
        }}
        .mmg-mini-sub {{
            margin-top: 6px;
            font-size: 0.85rem;
            color: #6c757d;
        }}
        </style>

        <div class="mmg-mini-card">
          <div class="mmg-mini-top">
            <div class="mmg-mini-title">% MMG visti (ciclo)</div>
            <div class="mmg-mini-pct">{pct}%</div>
          </div>
          <div class="mmg-mini-bar-outer" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">
            <div class="mmg-mini-bar-inner"></div>
          </div>
          <div class="mmg-mini-sub">{seen_count} / {total_mmg_target}</div>
        </div>
        """, unsafe_allow_html=True)

except Exception:
    pass


# ---------- FUNZIONI VISITA ----------------------------------------------------
def is_visited(row):
    return sum(1 for c in visto_cols if row.get(c, "") in ["x", "v"]) >= 1


def is_vip(row):
    return any(row.get(c, "") == "v" for c in visto_cols)


def count_visits(row):
    return sum(1 for c in visto_cols if row.get(c, "") in ["x", "v"])


def annotate_name(row):
    name = row["nome medico"]
    if any(row.get(c, "") == "v" for c in visto_cols):
        name = f"{name} (VIP)"
    return name


# ---------- FILTRO MESE ULTIMA VISITA ------------------------------------------
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


# ---------- FILTRI PRINCIPALI ---------------------------------------------------
filtro_spec = st.multiselect(
    "🩺 Filtra per tipo di specialista (spec)",
    DEFAULT_SPEC + SPEC_EXTRA,
    default=st.session_state.get("filtro_spec", DEFAULT_SPEC),
    key="filtro_spec",
)
df_work = df_work[df_work["spec"].isin(filtro_spec)].copy()

filtro_target = st.selectbox(
    "🎯 Scegli il tipo di medici",
    ["In target", "Non in target", "Tutti"],
    index=["In target", "Non in target", "Tutti"].index(st.session_state.get("filtro_target", "In target")),
    key="filtro_target",
)
filtro_visto = st.selectbox(
    "👀 Filtra per medici 'VISTO'",
    ["Tutti", "Visto", "Non Visto", "Visita VIP"],
    index=["Tutti", "Visto", "Non Visto", "Visita VIP"].index(st.session_state.get("filtro_visto", "Non Visto")),
    key="filtro_visto",
)

is_in = df_work["in target"].astype(str).str.strip().str.lower() == "x"
df_in_target = df_work[is_in].copy()
df_non_target = df_work[~is_in].copy()
df_filtered_target = {
    "In target": df_in_target,
    "Non in target": df_non_target,
    "Tutti": pd.concat([df_in_target, df_non_target], ignore_index=True),
}[filtro_target]

if filtro_visto == "Visto":
    df_work = df_filtered_target[df_filtered_target.apply(is_visited, axis=1)].copy()
elif filtro_visto == "Non Visto":
    df_work = df_filtered_target[~df_filtered_target.apply(is_visited, axis=1)].copy()
elif filtro_visto == "Visita VIP":
    df_work = df_filtered_target[df_filtered_target.apply(is_vip, axis=1)].copy()
else:
    df_work = df_filtered_target.copy()


# ---------- FILTRO GIORNO / FASCIA ----------------------------------------------
oggi = datetime.datetime.now(timezone)
giorni_opz = ["sempre"] + giorni_settimana
giorno_default = giorni_settimana[oggi.weekday()] if oggi.weekday() < 5 else "sempre"

giorno_scelto = st.selectbox(
    "📅 Scegli un giorno della settimana",
    giorni_opz,
    index=giorni_opz.index(st.session_state.get("giorno_scelto", giorno_default)),
    key="giorno_scelto",
)

fascia_opts = ["Mattina", "Pomeriggio", "Mattina e Pomeriggio", "Personalizzato"]
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
    st.session_state["custom_end"] = end_dt.time()

    t_start, t_end = st.slider(
        "Seleziona l'intervallo orario",
        min_value=default_min,
        max_value=default_max,
        value=(start_dt, end_dt),
        format="HH:mm",
    )
    custom_start, custom_end = t_start.time(), t_end.time()
    st.session_state["custom_start"] = custom_start
    st.session_state["custom_end"] = custom_end

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
        if fascia_oraria in ["Mattina", "Mattina e Pomeriggio"]:
            cols.append(f"{g} mattina")
        if fascia_oraria in ["Pomeriggio", "Mattina e Pomeriggio"]:
            cols.append(f"{g} pomeriggio")
        if fascia_oraria == "Personalizzato":
            for suf in ["mattina", "pomeriggio"]:
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
    colonne_da_mostrare = [c for c in df_work.columns if any(x in c for x in ["mattina", "pomeriggio"])]

colonne_da_mostrare = ["nome medico", "città"] + colonne_da_mostrare + [
    "indirizzo ambulatorio", "microarea", "provincia", "ultima visita"
]


# ---------- MICROAREE -----------------------------------------------------------
st.write("### Microaree")

microarea_lista = all_microaree.copy()

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
    index=prov_lista.index(st.session_state.get("provincia_scelta", "Ovunque")) if st.session_state.get("provincia_scelta", "Ovunque") in prov_lista else 0,
    key="provincia_scelta",
)

if prov_sel.lower() != "ovunque" and "provincia" in df_filtrato.columns:
    df_filtrato = df_filtrato[df_filtrato["provincia"].str.lower() == prov_sel.lower()].copy()


# ---------- ESCLUDI PROVINCE ----------------------------------------------------
prov_excl_raw = df_work.get("provincia", pd.Series([], dtype=str)).dropna().unique().tolist()
prov_excl_opts = sorted([str(p).strip() for p in prov_excl_raw if str(p).strip() and str(p).lower() != "nan"])

prov_escludi = st.multiselect(
    "🚫 Escludi province",
    prov_excl_opts,
    default=st.session_state.get("prov_escludi", []),
    key="prov_escludi",
)

if prov_escludi and "provincia" in df_filtrato.columns:
    excl_set = {str(p).strip().lower() for p in prov_escludi}
    df_filtrato = df_filtrato[~df_filtrato["provincia"].astype(str).str.strip().str.lower().isin(excl_set)].copy()


# ---------- MESE LIMITE ---------------------------------------------------------
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


# ---------- RICERCA -------------------------------------------------------------
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


# ---------- PERSISTI STATO ------------------------------------------------------
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
    "prov_escludi",
]

if st.session_state.pop("_skip_url_save_once", False):
    clear_all_query_params()
else:
    save_state_to_url(PERSIST_KEYS)


# ---------- ORDINAMENTO ---------------------------------------------------------
def min_start(row):
    ts = []
    for c in colonne_da_mostrare:
        if c in ["nome medico", "città", "indirizzo ambulatorio", "microarea", "provincia", "ultima visita", "Visite ciclo"]:
            continue
        stt, _ = parse_interval(row.get(c))
        if stt:
            ts.append(stt)
    return min(ts) if ts else datetime.time(23, 59)


df_filtrato = df_filtrato.copy()
df_filtrato["__start"] = df_filtrato.apply(min_start, axis=1)

month_order_sort = {m: i + 1 for i, m in enumerate(mesi)}
month_order_sort[""] = 0
df_filtrato["__ult"] = df_filtrato["ultima visita"].str.lower().map(month_order_sort).fillna(0)

df_filtrato = df_filtrato.sort_values(by=["__ult", "__start"]).copy()
df_filtrato.drop(columns=["__ult", "__start"], inplace=True, errors="ignore")


# ---------- EMPTY ----------------------------------------------------------------
if df_filtrato.empty:
    st.warning("Nessun risultato corrispondente ai filtri selezionati.")
    st.stop()


# ---------- VISITE CICLO --------------------------------------------------------
df_filtrato["Visite ciclo"] = df_filtrato.apply(count_visits, axis=1)
df_filtrato["nome medico"] = df_filtrato.apply(annotate_name, axis=1)


# ---------- VISUALIZZAZIONE -----------------------------------------------------
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
