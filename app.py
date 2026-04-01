import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime, re, pytz, io, json, urllib.parse, hashlib, os, unicodedata
from difflib import get_close_matches
from typing import Optional, Any
from openai import OpenAI

timezone = pytz.timezone('Europe/Rome')
DEFAULT_SPEC = ['MMG']
SPEC_EXTRA = ['ORT','FIS','REU','DOL','OTO','DER','INT','END','DIA']
mesi = ['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre']
month_order = {m:i+1 for i,m in enumerate(mesi)}
giorni_settimana = ['lunedì','martedì','mercoledì','giovedì','venerdì']
giorni_ascii = ['lunedi','martedi','mercoledi','giovedi','venerdi']
TRANSCRIBE_MODEL = 'gpt-4o-mini-transcribe'
st.set_page_config(page_title='Filtro Medici - Ricevimento Settimanale', layout='centered')

def _cache_data_decorator():
    try:
        return st.cache_data(show_spinner=False)
    except Exception:
        return st.cache(allow_output_mutation=False)
cache_data = _cache_data_decorator()

def get_openai_client() -> OpenAI:
    api_key = (st.secrets.get('OPENAI_API_KEY') if hasattr(st, 'secrets') else None) or os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError('Manca OPENAI_API_KEY.')
    return OpenAI(api_key=api_key)

def transcribe_streamlit_audio(uploaded_audio) -> str:
    client = get_openai_client()
    audio_file = io.BytesIO(uploaded_audio.getvalue())
    audio_file.name = getattr(uploaded_audio, 'name', 'audio.wav')
    transcript = client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=audio_file)
    text = getattr(transcript, 'text', None)
    if not text:
        raise ValueError('Trascrizione vuota.')
    return text.strip()

def strip_accents(s:str)->str:
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))

def norm_text(s:Any)->str:
    s = strip_accents(str(s)).lower().strip().replace('’', "'")
    s = re.sub(r"[^\w\s()/\-']", ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def norm_geo_key(s:Any)->str:
    s = norm_text(s)
    repl = {
        'civitanova marche':'civitanova', 'porto recanati':'portorecanati',
        'monte san giusto':'montesangiusto', 'potenza picena':'potenzapicena',
        'montecosaro scalo':'montecosaroscalo'
    }
    for a,b in repl.items(): s = s.replace(a,b)
    return s

def canon_code(s:Any)->str:
    return re.sub(r'\s+','',strip_accents(str(s)).upper())

def find_col(df:pd.DataFrame, candidates:list[str])->Optional[str]:
    cols_norm = {norm_text(c):c for c in df.columns}
    for c in candidates:
        if norm_text(c) in cols_norm:
            return cols_norm[norm_text(c)]
    return None

def resolve_columns(df:pd.DataFrame)->dict:
    return {
        'nome_medico': find_col(df,['nome medico','medico','nome']),
        'citta': find_col(df,['città','citta','comune']),
        'microarea': find_col(df,['microarea']),
        'provincia': find_col(df,['provincia']),
        'spec': find_col(df,['spec','specialita','specialità']),
        'in_target': find_col(df,['in target','target']),
        'indirizzo': find_col(df,['indirizzo ambulatorio','indirizzo','ambulatorio']),
    }

def build_all_province(df, col):
    if not col: return ['Ovunque']
    vals = df.get(col, pd.Series([], dtype=str)).dropna().astype(str).str.strip()
    cleaned = [x for x in vals.unique().tolist() if x and x.lower() != 'nan']
    return ['Ovunque'] + sorted(cleaned, key=lambda s: s.casefold())

def build_all_citta(df, col):
    if not col: return []
    vals = df.get(col, pd.Series([], dtype=str)).dropna().astype(str).str.strip()
    cleaned = [x for x in vals.unique().tolist() if x and x.lower() != 'nan']
    return sorted(cleaned, key=lambda s: s.casefold())

def build_all_microaree(df, col):
    if not col: return []
    vals = df.get(col, pd.Series([], dtype=str)).dropna().astype(str).str.strip()
    raw = [x for x in vals.unique().tolist() if x and x.lower() != 'nan']
    parent = set()
    for x in raw:
        m = re.match(r'^([A-Z]{2}\d{2})\s*\(', x.strip().upper())
        if m: parent.add(m.group(1))
    filtered = [x for x in raw if x.strip().upper() not in parent]
    priority = {'FM':0,'MC':1,'SBT':2,'AP':3,'MTPR':4,'TER':5,'GRTM':6}
    def keyf(s):
        up = s.strip().upper(); code = re.split(r'[^A-Z]', up)[0]
        return (priority.get(code,999), up.casefold())
    return sorted(filtered, key=keyf)

def build_lookup_maps(all_citta, all_province, all_microaree, df, cols):
    city_map = {norm_geo_key(c):c for c in all_citta}
    prov_map = {norm_geo_key(p):p for p in all_province if p!='Ovunque'}
    micro_exact, micro_code_map = {}, {}
    for m in all_microaree:
        micro_exact[norm_geo_key(m)] = m
        mm = re.match(r'^([A-Z]{2}\d{2})', canon_code(m))
        code = mm.group(1) if mm else canon_code(m)
        micro_code_map.setdefault(code, []).append(m)
    doctor_records = []
    if cols['nome_medico']:
        for _, row in df.iterrows():
            name = str(row.get(cols['nome_medico'], '')).strip()
            if not name: continue
            doctor_records.append({
                'name': name,
                'name_norm': norm_text(name),
                'microarea': str(row.get(cols['microarea'], '')).strip() if cols['microarea'] else '',
                'citta': str(row.get(cols['citta'], '')).strip() if cols['citta'] else '',
                'provincia': str(row.get(cols['provincia'], '')).strip() if cols['provincia'] else '',
            })
    return dict(city_map=city_map, prov_map=prov_map, micro_exact=micro_exact, micro_code_map=micro_code_map, doctor_records=doctor_records)

def resolve_microareas_from_phrase(text, all_microaree, maps):
    found, text_up = [], canon_code(text)
    for label_norm, label in maps['micro_exact'].items():
        if label_norm in norm_geo_key(text): found.append(label)
    for code in re.findall(r'\b[A-Z]{2}\d{2}\b', text_up):
        found.extend(maps['micro_code_map'].get(code, []))
    for code, variants in maps['micro_code_map'].items():
        if len(code)>=2 and re.search(rf'\b{re.escape(code)}\b', text_up): found.extend(variants)
    out=[]; seen=set()
    for x in found:
        if x not in seen: seen.add(x); out.append(x)
    return out

def resolve_city_from_phrase(text, maps):
    t = norm_geo_key(text); hits=[]
    for key, value in maps['city_map'].items():
        if re.search(rf'\b{re.escape(key)}\b', t): hits.append(value)
    return hits[0] if len(hits)==1 else None

def resolve_province_from_phrase(text, maps):
    t = norm_geo_key(text); hits=[]
    for key, value in maps['prov_map'].items():
        if re.search(rf'\b{re.escape(key)}\b', t): hits.append(value)
    return hits[0] if len(hits)==1 else None

def resolve_doctor_reference(text, maps):
    t = norm_text(text); cand=[]
    for rec in maps['doctor_records']:
        dn = rec['name_norm']; toks = dn.split(); surname = toks[-1] if toks else dn
        score=0
        if dn in t: score=max(score,100)
        if surname and re.search(rf'\b{re.escape(surname)}\b', t): score=max(score,80)
        if len(toks)>=2 and re.search(rf'\b{re.escape(toks[0])}\b', t) and re.search(rf'\b{re.escape(surname)}\b', t): score=max(score,95)
        if score>0: cand.append((score, rec))
    if not cand:
        close = get_close_matches(t, [r['name_norm'] for r in maps['doctor_records']], n=3, cutoff=0.82)
        for c in close:
            rec = next((r for r in maps['doctor_records'] if r['name_norm']==c), None)
            if rec: cand.append((60,rec))
    cand.sort(key=lambda x:(-x[0], x[1]['name']))
    recs = [r for _,r in cand]
    if len(recs)==1: return recs[0], recs
    if len(recs)>1:
        for r in recs:
            sur = r['name_norm'].split()[-1]
            if re.search(rf'\b{re.escape(sur)}\b', t) and sum(1 for x in recs if x['name_norm'].split()[-1]==sur)==1:
                return r, recs
    return None, recs

def _resolve_relative_day(text, now):
    t = norm_text(text)
    if 'oggi' in t:
        wd = now.weekday(); return giorni_settimana[wd] if 0<=wd<=4 else 'sempre'
    if 'dopodomani' in t:
        wd=(now.weekday()+2)%7; return giorni_settimana[wd] if 0<=wd<=4 else None
    if 'domani' in t:
        wd=(now.weekday()+1)%7; return giorni_settimana[wd] if 0<=wd<=4 else None
    return None

def parse_day_from_text(text, now):
    rel = _resolve_relative_day(text, now)
    if rel: return rel
    t = norm_text(text)
    for i, d in enumerate(giorni_settimana):
        if d in t or giorni_ascii[i] in t: return d
    return None

def parse_time_range(text):
    t = norm_text(text)
    m = re.search(r'\bdalle\s+(\d{1,2})(?::(\d{2}))?\s+(?:alle|a)\s+(\d{1,2})(?::(\d{2}))?\b', t)
    if m:
        h1,m1,h2,m2 = m.groups(); return 'Personalizzato', f'{int(h1):02d}:{int(m1 or 0):02d}', f'{int(h2):02d}:{int(m2 or 0):02d}'
    if re.search(r'\bmattina e pomeriggio\b|\btutto il giorno\b', t): return 'Mattina e Pomeriggio', None, None
    if re.search(r'\bdomattina\b|\boggi mattina\b|\bmattina\b', t): return 'Mattina', None, None
    if re.search(r'\bdomani pomeriggio\b|\boggi pomeriggio\b|\bpomeriggio\b', t): return 'Pomeriggio', None, None
    return None,None,None

def parse_spec(text):
    t = norm_text(text)
    if re.search(r'\b(mmg|medici di base|medico di base)\b', t): return ['MMG']
    if 'specialisti' in t: return SPEC_EXTRA.copy()
    mapping = {'ORT':['ortopedic','ortoped'],'FIS':['fisiatr'],'REU':['reumatolog','reumat'],'DOL':['algolog','dolore'],'OTO':['otorin'],'DER':['dermatolog','dermato'],'INT':['internist','medicina interna'],'END':['endocrinolog','endo'],'DIA':['diabetolog','diabeto']}
    found=[]
    for code, pats in mapping.items():
        if any(p in t for p in pats): found.append(code)
    return found or None

def parse_visto_target(text):
    t = norm_text(text); fv=None; ft=None
    if 'visita vip' in t or re.search(r'\bvip\b', t): fv='Visita VIP'
    elif re.search(r'\bnon visti\b|\bnon visto\b', t): fv='Non Visto'
    elif re.search(r'\bvisti\b|\bvisto\b', t): fv='Visto'
    if 'non in target' in t: ft='Non in target'
    elif 'in target' in t: ft='In target'
    elif re.search(r'\btutti\b', t): ft='Tutti'
    return fv, ft

def parse_cycle(text):
    t = norm_text(text)
    for n, label in [('1','Ciclo 1 (Gen-Feb-Mar)'),('2','Ciclo 2 (Apr-Mag-Giu)'),('3','Ciclo 3 (Lug-Ago-Set)'),('4','Ciclo 4 (Ott-Nov-Dic)')]:
        if f'ciclo {n}' in t: return label
    return None

def parse_ultima_visita(text):
    t = norm_text(text)
    if not re.search(r'\b(ultima visita|visti prima di|fino a)\b', t): return None
    for m in mesi:
        if m in t: return m.capitalize()
    return None

def parse_search_query(text):
    m = re.search(r'\bcerca\s+(.+)$', norm_text(text))
    return m.group(1).strip() if m else None

def should_reset(text):
    t = norm_text(text)
    return any(x in t for x in ['azzera tutto','resetta','reset','azzera filtri'])

def infer_mode(text):
    t = norm_text(text)
    return 'merge' if any(m in t for m in ['aggiungi','escludi','togli','rimuovi','senza','tranne','anche','oltre']) else 'replace'

def extract_excluded_provinces(text, maps):
    t = norm_geo_key(text)
    if not re.search(r'\b(escludi|senza|tranne)\b', t): return []
    found=[]
    for key, value in maps['prov_map'].items():
        if re.search(rf'\b{re.escape(key)}\b', t): found.append(value)
    return list(dict.fromkeys(found))

def detect_geo_scope(text):
    t = norm_text(text)
    if re.search(r'\b(microarea|micro area)\b', t): return 'microarea'
    if re.search(r'\bprovincia\b', t): return 'provincia'
    if re.search(r'\b(citta|comune)\b', t): return 'citta'
    return None

def interpret_voice_command_to_filters_local(command_text, all_province, all_microaree, maps):
    now = datetime.datetime.now(timezone); text = command_text.strip(); text_n = norm_text(text)
    payload = {'action':'apply_filters','message':None,'mode':infer_mode(text),'giorno_scelto':None,'fascia_oraria':None,'custom_start':None,'custom_end':None,'provincia_scelta':None,'microarea_scelta':None,'filtro_visto':None,'filtro_target':None,'filtro_spec':None,'ciclo_scelto':None,'mese_limite_visita':None,'search_query':None,'prov_escludi':[],'voice_geo_scope':None,'voice_geo_value':None,'voice_geo_values':[],'reference_doctor':None}
    if should_reset(text):
        payload['action']='azzera_filtri'; payload['message']='Filtri azzerati.'; return payload
    payload['giorno_scelto'] = parse_day_from_text(text, now)
    payload['fascia_oraria'], payload['custom_start'], payload['custom_end'] = parse_time_range(text)
    payload['filtro_spec'] = parse_spec(text)
    payload['filtro_visto'], payload['filtro_target'] = parse_visto_target(text)
    payload['ciclo_scelto'] = parse_cycle(text)
    payload['mese_limite_visita'] = parse_ultima_visita(text)
    payload['search_query'] = parse_search_query(text)
    payload['prov_escludi'] = extract_excluded_provinces(text, maps)
    scope = detect_geo_scope(text); payload['voice_geo_scope'] = scope
    if scope == 'microarea':
        micros = resolve_microareas_from_phrase(text, all_microaree, maps)
        if not micros: return {'action':'nessuna_azione','message':'Microarea non riconosciuta.'}
        payload['microarea_scelta'] = micros; payload['voice_geo_values']=micros; payload['voice_geo_value']=micros[0]
    elif scope == 'provincia':
        prov = resolve_province_from_phrase(text, maps)
        if not prov: return {'action':'nessuna_azione','message':'Provincia non riconosciuta.'}
        payload['provincia_scelta']=prov; payload['voice_geo_value']=prov
    elif scope == 'citta':
        city = resolve_city_from_phrase(text, maps)
        if not city: return {'action':'nessuna_azione','message':'Città non riconosciuta.'}
        payload['voice_geo_value']=city
    if payload['voice_geo_scope'] is None:
        micros = resolve_microareas_from_phrase(text, all_microaree, maps)
        if micros:
            payload['voice_geo_scope']='microarea'; payload['microarea_scelta']=micros; payload['voice_geo_values']=micros; payload['voice_geo_value']=micros[0]
        else:
            city = resolve_city_from_phrase(text, maps)
            if city:
                payload['voice_geo_scope']='citta'; payload['voice_geo_value']=city
            else:
                prov = resolve_province_from_phrase(text, maps)
                if prov:
                    payload['voice_geo_scope']='provincia'; payload['provincia_scelta']=prov; payload['voice_geo_value']=prov
    doctor_ref, doctor_candidates = resolve_doctor_reference(text, maps)
    same_zone = re.search(r'\b(stessa zona|stesso posto|stessa microarea|dove riceve|zona di|vicino a)\b', text_n)
    if doctor_ref and (same_zone or 'con la dottoressa' in text_n or 'con il dottore' in text_n or 'della dottoressa' in text_n or 'del dottore' in text_n):
        payload['reference_doctor'] = doctor_ref['name']
        if doctor_ref.get('microarea'):
            payload['voice_geo_scope']='microarea'; payload['microarea_scelta']=[doctor_ref['microarea']]; payload['voice_geo_values']=[doctor_ref['microarea']]; payload['voice_geo_value']=doctor_ref['microarea']
        elif doctor_ref.get('citta'):
            payload['voice_geo_scope']='citta'; payload['voice_geo_value']=doctor_ref['citta']
        elif doctor_ref.get('provincia'):
            payload['voice_geo_scope']='provincia'; payload['provincia_scelta']=doctor_ref['provincia']; payload['voice_geo_value']=doctor_ref['provincia']
    elif same_zone and not doctor_ref and len(doctor_candidates)>1:
        names = ', '.join(d['name'] for d in doctor_candidates[:3])
        return {'action':'nessuna_azione','message':f'Riferimento medico ambiguo: {names}.'}
    if payload.get('voice_geo_scope') == 'citta':
        payload['provincia_scelta'] = None; payload['microarea_scelta'] = None
    elif payload.get('voice_geo_scope') == 'microarea':
        payload['provincia_scelta'] = None
    fb=[]
    if payload.get('filtro_spec'): fb.append('/'.join(payload['filtro_spec']))
    if payload.get('giorno_scelto'): fb.append(payload['giorno_scelto'])
    if payload.get('fascia_oraria'):
        fb.append(f"{payload['custom_start']}-{payload['custom_end']}" if payload['fascia_oraria']=='Personalizzato' and payload.get('custom_start') and payload.get('custom_end') else payload['fascia_oraria'])
    if payload.get('voice_geo_scope')=='citta' and payload.get('voice_geo_value'): fb.append(f"città={payload['voice_geo_value']}")
    if payload.get('voice_geo_scope')=='microarea' and payload.get('voice_geo_values'): fb.append(f"microarea={', '.join(payload['voice_geo_values'])}")
    if payload.get('voice_geo_scope')=='provincia' and payload.get('voice_geo_value'): fb.append(f"provincia={payload['voice_geo_value']}")
    if payload.get('prov_escludi'): fb.append(f"escludi={', '.join(payload['prov_escludi'])}")
    if payload.get('reference_doctor'): fb.append(f"rif={payload['reference_doctor']}")
    payload['message'] = 'Applicato: ' + ', '.join(fb) if fb else 'Filtri aggiornati da comando vocale.'
    return payload

def _get_query_param(key):
    v = st.query_params.get(key, None)
    if isinstance(v, (list, tuple)): return v[0] if v else None
    return v

def _set_query_param(key, value):
    if value is None:
        if key in st.query_params: del st.query_params[key]
    else:
        st.query_params[key] = value

def clear_all_query_params():
    for k in list(st.query_params.keys()): del st.query_params[k]

def _serialize_value(v):
    if isinstance(v, datetime.time): return v.strftime('%H:%M:%S')
    if isinstance(v, (datetime.datetime, datetime.date)): return v.isoformat()
    return v

def _deserialize_time(s):
    if not s: return None
    s = str(s).strip()
    try:
        return datetime.datetime.strptime(s, '%H:%M' if len(s.split(':'))==2 else '%H:%M:%S').time()
    except Exception:
        return None

def _encode_state(payload): return urllib.parse.quote(json.dumps(payload, ensure_ascii=False))
def _decode_state(s): return json.loads(urllib.parse.unquote(s))

def load_state_from_url():
    s = _get_query_param('state')
    if not s: return
    try:
        payload = _decode_state(s)
        for k, v in payload.items():
            if k not in st.session_state:
                st.session_state[k] = _deserialize_time(v) if k in ['custom_start','custom_end'] and isinstance(v, str) else v
    except Exception:
        pass

def save_state_to_url(keys):
    payload = {k:_serialize_value(st.session_state[k]) for k in keys if k in st.session_state}
    new_state = _encode_state(payload); old_state = _get_query_param('state')
    if new_state != old_state: _set_query_param('state', new_state)

load_state_from_url()

def _rounded_now_naive_local(tz):
    dt = datetime.datetime.now(tz).replace(second=0, microsecond=0)
    return dt.replace(tzinfo=None)

def _slider_bounds_for_date(d):
    return datetime.datetime.combine(d, datetime.time(7,0)), datetime.datetime.combine(d, datetime.time(19,0))

def _default_custom_times_rounded(tz):
    now = _rounded_now_naive_local(tz); d = now.date(); min_dt, max_dt = _slider_bounds_for_date(d); latest_start = max_dt - datetime.timedelta(minutes=15)
    start_dt = min_dt if now < min_dt else latest_start if now > latest_start else now
    return start_dt.time(), (start_dt + datetime.timedelta(minutes=15)).time()

def _normalize_custom_times_for_slider(tz, custom_start, custom_end):
    now = _rounded_now_naive_local(tz); d = now.date(); min_dt, max_dt = _slider_bounds_for_date(d); latest_start = max_dt - datetime.timedelta(minutes=15)
    if not isinstance(custom_start, datetime.time) or not isinstance(custom_end, datetime.time): custom_start, custom_end = _default_custom_times_rounded(tz)
    start_dt = datetime.datetime.combine(d, custom_start).replace(second=0, microsecond=0); end_dt = datetime.datetime.combine(d, custom_end).replace(second=0, microsecond=0)
    if end_dt <= start_dt: end_dt = start_dt + datetime.timedelta(minutes=15)
    if start_dt < min_dt: start_dt = min_dt
    if end_dt > max_dt: end_dt = max_dt
    if end_dt <= start_dt: start_dt, end_dt = latest_start, max_dt
    return start_dt, end_dt, min_dt, max_dt

st.markdown("""
<style>
body {background:#f8f9fa;color:#212529;} [data-testid="stAppViewContainer"] {background:#f8f9fa;}
h1 {font-family:'Helvetica Neue',sans-serif;font-size:2.3rem;text-align:center;color:#007bff;margin-bottom:1.2rem;}
div.stButton > button {background:#007bff;color:#fff;border:none;border-radius:10px;padding:0.55rem 1rem;font-size:1rem;}
div.stButton > button:hover {background:#0056b3;} .ag-root-wrapper {border:1px solid #dee2e6 !important;border-radius:10px;overflow:hidden;}
.ag-header-cell-label {font-weight:bold;color:#343a40;} .ag-row {font-size:0.9rem;}
#microarea-box div[data-testid="stCheckbox"] { margin:0 !important; padding:0 !important; }
#microarea-box div[data-testid="stCheckbox"] label{ margin:0 !important; padding:2px 0 !important; line-height:1.1 !important; font-size:0.95rem !important; white-space: normal !important;}
#microarea-box div[data-testid="stCheckbox"] input{ transform: scale(0.95);} .voice-wrap {margin:8px 0 18px 0;padding:16px 18px;border-radius:18px;background:#fff;border:1px solid rgba(0,0,0,0.06);box-shadow:0 8px 24px rgba(23,35,59,0.08);} .voice-title {font-size:1.05rem;font-weight:700;color:#1f2937;margin-bottom:6px;} .voice-sub {font-size:0.92rem;color:#6b7280;margin-bottom:10px;} .voice-result {margin-top:12px;padding:12px 14px;border-radius:12px;background:#f8fafc;border:1px solid rgba(0,0,0,0.05);} .voice-label {font-weight:700;color:#374151;}
</style>
""", unsafe_allow_html=True)
st.title('📋 Filtro Medici - Ricevimento Settimanale')
file = st.file_uploader('Carica il file Excel', type=['xlsx'], key='file_uploader')
if file is not None:
    try: st.session_state['uploaded_file_bytes'] = file.getvalue()
    except Exception: pass
file_bytes = st.session_state.get('uploaded_file_bytes')
if file_bytes is None: st.stop()
@cache_data
def load_excel(file_bytes:bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes)); return pd.read_excel(xls, sheet_name='MMG')
df_mmg = load_excel(file_bytes); cols = resolve_columns(df_mmg)
all_province = build_all_province(df_mmg, cols['provincia']); all_microaree = build_all_microaree(df_mmg, cols['microarea']); all_citta = build_all_citta(df_mmg, cols['citta']); maps = build_lookup_maps(all_citta, all_province, all_microaree, df_mmg, cols)

def azzera_filtri():
    try: clear_all_query_params()
    except Exception: pass
    preserved_file = st.session_state.get('uploaded_file_bytes')
    today = datetime.datetime.now(timezone); default_cycle_idx = 1 + (today.month - 1)//3
    ciclo_opts = ['Tutti','Ciclo 1 (Gen-Feb-Mar)','Ciclo 2 (Apr-Mag-Giu)','Ciclo 3 (Lug-Ago-Set)','Ciclo 4 (Ott-Nov-Dic)']
    giorno_default = giorni_settimana[today.weekday()] if today.weekday() < 5 else 'sempre'
    defaults = {'ciclo_scelto':ciclo_opts[default_cycle_idx],'filtro_ultima_visita':'Nessuno','mese_limite_visita':'Nessuno','filtro_spec':DEFAULT_SPEC.copy(),'filtro_target':'In target','filtro_visto':'Non Visto','giorno_scelto':giorno_default,'fascia_oraria':'Personalizzato','custom_start':None,'custom_end':None,'provincia_scelta':'Ovunque','microarea_scelta':[],'search_query':'','prov_escludi':[],'voice_geo_scope':None,'voice_geo_value':None,'voice_geo_values':[],'reference_doctor':None}
    for k in list(st.session_state.keys()):
        try: del st.session_state[k]
        except Exception: pass
    if preserved_file is not None: st.session_state['uploaded_file_bytes'] = preserved_file
    for k,v in defaults.items(): st.session_state[k] = v
    for m in all_microaree:
        st.session_state['micro_chk_' + hashlib.md5(m.encode('utf-8')).hexdigest()[:10]] = False
    st.session_state['_skip_url_save_once'] = True

def toggle_specialisti(): st.session_state['filtro_spec'] = SPEC_EXTRA if st.session_state.get('filtro_spec', DEFAULT_SPEC) == DEFAULT_SPEC else DEFAULT_SPEC
def seleziona_mmg(): st.session_state['filtro_spec'] = DEFAULT_SPEC
col1,col2,col3 = st.columns([1,1,2])
with col1: st.button('🔄 Azzera tutti i filtri', on_click=azzera_filtri)
with col2: st.button('Specialisti 👨‍⚕️👩‍⚕️', on_click=toggle_specialisti)
with col3: st.button('MMG 🩺', on_click=seleziona_mmg)

def get_ultima_visita(row):
    ultima=''
    for m in mesi:
        col_m = find_col(df_mmg, [m])
        if col_m and str(row.get(col_m,'')).strip().lower() in ['x','v']: ultima = m.capitalize()
    return ultima
for m in mesi:
    col_m = find_col(df_mmg,[m])
    if col_m: df_mmg[col_m] = df_mmg[col_m].fillna('').astype(str).str.strip().str.lower()
df_mmg['ultima visita'] = df_mmg.apply(get_ultima_visita, axis=1)
ciclo_opts = ['Tutti','Ciclo 1 (Gen-Feb-Mar)','Ciclo 2 (Apr-Mag-Giu)','Ciclo 3 (Lug-Ago-Set)','Ciclo 4 (Ott-Nov-Dic)']
today = datetime.datetime.now(timezone); default_cycle_idx = 1 + (today.month - 1)//3
if st.session_state.get('ciclo_scelto') not in [None,*ciclo_opts]: st.session_state.pop('ciclo_scelto', None)

def _parse_hhmm_or_none(value):
    if value is None: return None
    try: return datetime.datetime.strptime(str(value), '%H:%M').time()
    except Exception: return None

def apply_voice_filters(payload):
    action = payload.get('action')
    if action == 'azzera_filtri': azzera_filtri(); return 'Filtri azzerati.'
    if action == 'nessuna_azione': return payload.get('message') or 'Comando non applicato.'
    if action != 'apply_filters': return 'Nessuna modifica applicata.'
    if payload.get('mode','replace') == 'replace': azzera_filtri()
    for key in ['giorno_scelto','provincia_scelta','filtro_visto','filtro_target','ciclo_scelto','search_query','voice_geo_scope','voice_geo_value','reference_doctor']:
        if payload.get(key) is not None: st.session_state[key] = payload[key]
    st.session_state['voice_geo_values'] = payload.get('voice_geo_values') or []
    if isinstance(payload.get('filtro_spec'), list) and payload['filtro_spec']:
        valid = [x for x in payload['filtro_spec'] if x in (DEFAULT_SPEC + SPEC_EXTRA)]
        if valid: st.session_state['filtro_spec'] = valid
    if isinstance(payload.get('microarea_scelta'), list):
        st.session_state['microarea_scelta'] = payload['microarea_scelta']
        for m in all_microaree:
            st.session_state['micro_chk_' + hashlib.md5(m.encode('utf-8')).hexdigest()[:10]] = m in payload['microarea_scelta']
    if isinstance(payload.get('prov_escludi'), list):
        cur = set(st.session_state.get('prov_escludi', [])) if payload.get('mode') == 'merge' else set()
        cur.update(payload['prov_escludi']); st.session_state['prov_escludi'] = sorted(cur)
    if payload.get('fascia_oraria') is not None: st.session_state['fascia_oraria'] = payload['fascia_oraria']
    if payload.get('fascia_oraria') == 'Personalizzato':
        t1,t2 = _parse_hhmm_or_none(payload.get('custom_start')), _parse_hhmm_or_none(payload.get('custom_end'))
        st.session_state['custom_start'] = t1 if t1 and t2 and t2 > t1 else None
        st.session_state['custom_end'] = t2 if t1 and t2 and t2 > t1 else None
    if payload.get('mese_limite_visita'): st.session_state['mese_limite_visita'] = payload['mese_limite_visita']
    if payload.get('voice_geo_scope') == 'citta': st.session_state['provincia_scelta'] = 'Ovunque'
    return payload.get('message') or 'Filtri aggiornati da comando vocale.'

st.markdown("""<div class='voice-wrap'><div class='voice-title'>🎙️ Comando vocale AI</div><div class='voice-sub'>Premi il pulsante, parla, poi ferma la registrazione.<br>Appena finisce, il comando parte da solo.</div></div>""", unsafe_allow_html=True)
audio = st.audio_input('🎙️ Avvia comando vocale', sample_rate=16000, key='voice_audio_input')
if 'last_processed_audio_hash' not in st.session_state: st.session_state['last_processed_audio_hash'] = None
if audio is not None:
    audio_bytes = audio.getvalue(); audio_hash = hashlib.md5(audio_bytes).hexdigest()
    if audio_hash != st.session_state['last_processed_audio_hash']:
        try:
            with st.spinner('Trascrivo e applico i filtri...'):
                transcript = transcribe_streamlit_audio(audio)
                payload = interpret_voice_command_to_filters_local(transcript, all_province, all_microaree, maps)
                msg = apply_voice_filters(payload)
                st.session_state['last_voice_transcript'] = transcript; st.session_state['last_voice_payload'] = payload; st.session_state['voice_feedback'] = msg; st.session_state['last_processed_audio_hash'] = audio_hash
            st.rerun()
        except Exception as e:
            st.session_state['voice_feedback'] = f'Errore comando vocale: {e}'; st.session_state['last_processed_audio_hash'] = audio_hash
if st.session_state.get('last_voice_transcript') or st.session_state.get('voice_feedback'):
    st.markdown('<div class="voice-result">', unsafe_allow_html=True)
    if st.session_state.get('last_voice_transcript'): st.markdown(f"<div><span class='voice-label'>Hai detto:</span> {st.session_state['last_voice_transcript']}</div>", unsafe_allow_html=True)
    if st.session_state.get('voice_feedback'): st.markdown(f"<div style='margin-top:6px;'><span class='voice-label'>Esito:</span> {st.session_state['voice_feedback']}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
st.caption('Esempi: “chi riceve domattina in microarea FM01 più FM02” · “chi riceve nella città di Macerata” · “chi posso vedere nella stessa zona di Biagiola”')

ciclo_scelto = st.selectbox(f"💠 SELEZIONA CICLO ({today.strftime('%B').capitalize()} {today.year})", ciclo_opts, index=default_cycle_idx, key='ciclo_scelto')
month_cycles = {'Ciclo 1 (Gen-Feb-Mar)':['gennaio','febbraio','marzo'],'Ciclo 2 (Apr-Mag-Giu)':['aprile','maggio','giugno'],'Ciclo 3 (Lug-Ago-Set)':['luglio','agosto','settembre'],'Ciclo 4 (Ott-Nov-Dic)':['ottobre','novembre','dicembre']}
visto_cols = [find_col(df_mmg, [m]) for m in (mesi if ciclo_scelto=='Tutti' else month_cycles[ciclo_scelto])]; visto_cols = [c for c in visto_cols if c]
try:
    if visto_cols and cols['nome_medico']:
        df_tmp = df_mmg.copy(); df_tmp['_nome_norm'] = df_tmp[cols['nome_medico']].astype(str).str.strip().str.lower(); is_mmg = df_tmp.get(cols['spec'], pd.Series('', index=df_tmp.index)).astype(str).str.strip().str.upper() == 'MMG' if cols['spec'] else True; is_in_target = df_tmp.get(cols['in_target'], pd.Series('', index=df_tmp.index)).astype(str).str.strip().str.lower() == 'x' if cols['in_target'] else True; base_mask = is_mmg & is_in_target; total_mmg_target = int(df_tmp[base_mask]['_nome_norm'].nunique())
        seen_rows = df_tmp[visto_cols].apply(lambda r: any(str(v).strip().lower() in ['x','v'] for v in r.values), axis=1); seen_count = int(df_tmp[base_mask & seen_rows]['_nome_norm'].nunique()); pct = int(round((seen_count / total_mmg_target) * 100)) if total_mmg_target > 0 else 0
        st.markdown(f"""<style>.mmg-mini-card {{padding:12px 14px;border-radius:12px;box-shadow:0 6px 18px rgba(23,35,59,0.08);background:#fff;border:1px solid rgba(0,0,0,0.04);margin:6px 0 14px 0;}} .mmg-mini-top {{display:flex;justify-content:space-between;align-items:baseline;gap:10px;}} .mmg-mini-title {{font-size:0.95rem;font-weight:700;color:#495057;margin:0;}} .mmg-mini-pct {{font-size:1.6rem;font-weight:800;color:#0d6efd;margin:0;line-height:1;}} .mmg-mini-bar-outer {{height:14px;background:#e9ecef;border-radius:999px;overflow:hidden;margin-top:10px;}} .mmg-mini-bar-inner {{height:100%;width:{pct}%;background:linear-gradient(90deg,#198754,#0d6efd);border-radius:999px;transition:width 500ms ease;}} .mmg-mini-sub {{margin-top:6px;font-size:0.85rem;color:#6c757d;}}</style><div class='mmg-mini-card'><div class='mmg-mini-top'><div class='mmg-mini-title'>% MMG visti (ciclo)</div><div class='mmg-mini-pct'>{pct}%</div></div><div class='mmg-mini-bar-outer'><div class='mmg-mini-bar-inner'></div></div><div class='mmg-mini-sub'>{seen_count} / {total_mmg_target}</div></div>""", unsafe_allow_html=True)
except Exception: pass

def is_visited(row): return sum(1 for c in visto_cols if str(row.get(c,'')).strip().lower() in ['x','v']) >= 1
def is_vip(row): return any(str(row.get(c,'')).strip().lower()=='v' for c in visto_cols)
def count_visits(row): return sum(1 for c in visto_cols if str(row.get(c,'')).strip().lower() in ['x','v'])
def annotate_name(row):
    name = row[cols['nome_medico']]
    return f"{name} (VIP)" if any(str(row.get(c,'')).strip().lower()=='v' for c in visto_cols) else name
lista_mesi_cap = [m.capitalize() for m in mesi]
filtro_ultima = st.selectbox('Seleziona mese ultima visita', ['Nessuno'] + lista_mesi_cap, index=0, key='filtro_ultima_visita')
df_work = df_mmg.copy()
if filtro_ultima != 'Nessuno':
    sel_num = month_order[filtro_ultima.lower()]
    df_work = df_work[df_work['ultima visita'].str.lower().map(lambda m: month_order.get(m,0)).le(sel_num)].copy()
if cols['spec']:
    filtro_spec = st.multiselect('🩺 Filtra per tipo di specialista (spec)', DEFAULT_SPEC + SPEC_EXTRA, default=st.session_state.get('filtro_spec', DEFAULT_SPEC), key='filtro_spec')
    df_work = df_work[df_work[cols['spec']].isin(filtro_spec)].copy()
else:
    filtro_spec = DEFAULT_SPEC
filtro_target = st.selectbox('🎯 Scegli il tipo di medici', ['In target','Non in target','Tutti'], index=['In target','Non in target','Tutti'].index(st.session_state.get('filtro_target','In target')), key='filtro_target')
filtro_visto = st.selectbox("👀 Filtra per medici 'VISTO'", ['Tutti','Visto','Non Visto','Visita VIP'], index=['Tutti','Visto','Non Visto','Visita VIP'].index(st.session_state.get('filtro_visto','Non Visto')), key='filtro_visto')
is_in = df_work[cols['in_target']].astype(str).str.strip().str.lower() == 'x' if cols['in_target'] else pd.Series(True, index=df_work.index)
df_in_target = df_work[is_in].copy(); df_non_target = df_work[~is_in].copy(); df_filtered_target = {'In target':df_in_target,'Non in target':df_non_target,'Tutti':pd.concat([df_in_target, df_non_target], ignore_index=True)}[filtro_target]
if filtro_visto == 'Visto': df_work = df_filtered_target[df_filtered_target.apply(is_visited, axis=1)].copy()
elif filtro_visto == 'Non Visto': df_work = df_filtered_target[~df_filtered_target.apply(is_visited, axis=1)].copy()
elif filtro_visto == 'Visita VIP': df_work = df_filtered_target[df_filtered_target.apply(is_vip, axis=1)].copy()
else: df_work = df_filtered_target.copy()
oggi = datetime.datetime.now(timezone); giorni_opz = ['sempre'] + giorni_settimana; giorno_default = giorni_settimana[oggi.weekday()] if oggi.weekday() < 5 else 'sempre'
giorno_scelto = st.selectbox('📅 Scegli un giorno della settimana', giorni_opz, index=giorni_opz.index(st.session_state.get('giorno_scelto', giorno_default)), key='giorno_scelto')
fascia_opts = ['Mattina','Pomeriggio','Mattina e Pomeriggio','Personalizzato']
fascia_oraria = st.radio('🌞 Scegli la fascia oraria', fascia_opts, index=fascia_opts.index(st.session_state.get('fascia_oraria','Personalizzato')), key='fascia_oraria')
if fascia_oraria == 'Personalizzato':
    start_dt, end_dt, default_min, default_max = _normalize_custom_times_for_slider(timezone, st.session_state.get('custom_start'), st.session_state.get('custom_end')); st.session_state['custom_start']=start_dt.time(); st.session_state['custom_end']=end_dt.time(); t_start, t_end = st.slider('Seleziona l\'intervallo orario', min_value=default_min, max_value=default_max, value=(start_dt, end_dt), format='HH:mm'); custom_start, custom_end = t_start.time(), t_end.time(); st.session_state['custom_start']=custom_start; st.session_state['custom_end']=custom_end
    if custom_end <= custom_start: st.error('L\'orario di fine deve essere successivo all\'orario di inizio.'); st.stop()
else:
    custom_start = custom_end = None; st.session_state.pop('custom_start', None); st.session_state.pop('custom_end', None)

def _parse_time_flexible(s):
    s = str(s).strip()
    try: return datetime.datetime.strptime(s, '%H:%M' if ':' in s else '%H').time()
    except Exception: return None

def parse_interval(cell_value):
    if pd.isna(cell_value): return None, None
    s = str(cell_value).strip(); m = re.match(r'(\d{1,2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}(?::\d{2})?)', s)
    if not m: return None, None
    start_t, end_t = _parse_time_flexible(m.group(1)), _parse_time_flexible(m.group(2))
    return (start_t, end_t) if start_t and end_t else (None, None)

def interval_covers(cell_value, custom_start, custom_end):
    start_t, end_t = parse_interval(cell_value); return bool(start_t and end_t and start_t <= custom_start and end_t >= custom_end)

def filtra_giorno_fascia(df_base):
    giorni = giorni_settimana if giorno_scelto == 'sempre' else [giorno_scelto]; cols_g=[]
    for g in giorni:
        if fascia_oraria in ['Mattina','Mattina e Pomeriggio']: cols_g.append(find_col(df_base, [f'{g} mattina']))
        if fascia_oraria in ['Pomeriggio','Mattina e Pomeriggio']: cols_g.append(find_col(df_base, [f'{g} pomeriggio']))
        if fascia_oraria == 'Personalizzato':
            for suf in ['mattina','pomeriggio']:
                cols_g.append(find_col(df_base, [f'{g} {suf}']))
    cols_g = [c for c in cols_g if c]
    if not cols_g: st.error('Le colonne per il filtro giorno/fascia non esistono nel file.'); st.stop()
    if fascia_oraria == 'Personalizzato':
        return df_base[df_base[cols_g].apply(lambda r: any(interval_covers(r.get(c), custom_start, custom_end) for c in cols_g), axis=1)].copy(), cols_g
    return df_base[df_base[cols_g].notna().any(axis=1)].copy(), cols_g

df_filtrato, colonne_da_mostrare = filtra_giorno_fascia(df_work)
if fascia_oraria == 'Personalizzato':
    ora_rif = custom_start.hour
    if ora_rif < 13:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if 'mattina' in norm_text(c)]
    else:
        colonne_da_mostrare = [c for c in colonne_da_mostrare if 'pomeriggio' in norm_text(c)]
if not colonne_da_mostrare: colonne_da_mostrare = [c for c in df_work.columns if any(x in norm_text(c) for x in ['mattina','pomeriggio'])]
display_cols=[]
for key in ['nome_medico','citta']:
    if cols[key]: display_cols.append(cols[key])
display_cols += colonne_da_mostrare
for key in ['indirizzo','microarea','provincia']:
    if cols[key]: display_cols.append(cols[key])
display_cols += ['ultima visita']; colonne_da_mostrare = list(dict.fromkeys([c for c in display_cols if c in df_filtrato.columns or c == 'ultima visita']))
st.write('### Microaree')
microarea_lista = all_microaree.copy(); b1,b2,b3 = st.columns([1,1,2])
with b1:
    if st.button('✅ Tutte', key='micro_all'):
        st.session_state['microarea_scelta'] = microarea_lista.copy()
        for m in microarea_lista: st.session_state['micro_chk_' + hashlib.md5(m.encode('utf-8')).hexdigest()[:10]] = True
        st.rerun()
with b2:
    if st.button('🚫 Nessuna', key='micro_none'):
        st.session_state['microarea_scelta'] = []
        for m in microarea_lista: st.session_state['micro_chk_' + hashlib.md5(m.encode('utf-8')).hexdigest()[:10]] = False
        st.rerun()
with b3: st.caption(f"Selezionate: {len(st.session_state.get('microarea_scelta', []))}")
st.markdown('<div id="microarea-box">', unsafe_allow_html=True)
selected_set = set(st.session_state.get('microarea_scelta', [])); micro_sel=[]
for m in microarea_lista:
    mk = 'micro_chk_' + hashlib.md5(m.encode('utf-8')).hexdigest()[:10]
    if mk not in st.session_state: st.session_state[mk] = (m in selected_set)
    if st.checkbox(m, key=mk): micro_sel.append(m)
st.markdown('</div>', unsafe_allow_html=True)
st.session_state['microarea_scelta'] = micro_sel
if micro_sel and cols['microarea'] and cols['microarea'] in df_filtrato.columns: df_filtrato = df_filtrato[df_filtrato[cols['microarea']].isin(micro_sel)].copy()
prov_sel = st.selectbox('📍 Scegli la Provincia', all_province, index=all_province.index(st.session_state.get('provincia_scelta','Ovunque')) if st.session_state.get('provincia_scelta','Ovunque') in all_province else 0, key='provincia_scelta')
if prov_sel.lower() != 'ovunque' and cols['provincia'] and cols['provincia'] in df_filtrato.columns: df_filtrato = df_filtrato[df_filtrato[cols['provincia']].astype(str).str.strip().str.lower() == prov_sel.lower()].copy()
prov_escludi = st.multiselect('🚫 Escludi province', [p for p in all_province if p!='Ovunque'], default=st.session_state.get('prov_escludi', []), key='prov_escludi')
if prov_escludi and cols['provincia'] and cols['provincia'] in df_filtrato.columns:
    excl_set = {str(p).strip().lower() for p in prov_escludi}; df_filtrato = df_filtrato[~df_filtrato[cols['provincia']].astype(str).str.strip().str.lower().isin(excl_set)].copy()
voice_geo_scope, voice_geo_value, voice_geo_values = st.session_state.get('voice_geo_scope'), st.session_state.get('voice_geo_value'), st.session_state.get('voice_geo_values', [])
if voice_geo_scope == 'citta' and voice_geo_value and cols['citta'] and cols['citta'] in df_filtrato.columns:
    df_filtrato = df_filtrato[df_filtrato[cols['citta']].astype(str).str.strip().str.lower() == str(voice_geo_value).strip().lower()].copy()
elif voice_geo_scope == 'microarea' and cols['microarea'] and cols['microarea'] in df_filtrato.columns:
    vals = voice_geo_values if voice_geo_values else ([voice_geo_value] if voice_geo_value else []); vals_norm = {str(x).strip().lower() for x in vals}
    if vals_norm: df_filtrato = df_filtrato[df_filtrato[cols['microarea']].astype(str).str.strip().str.lower().isin(vals_norm)].copy()
elif voice_geo_scope == 'provincia' and voice_geo_value and cols['provincia'] and cols['provincia'] in df_filtrato.columns:
    df_filtrato = df_filtrato[df_filtrato[cols['provincia']].astype(str).str.strip().str.lower() == str(voice_geo_value).strip().lower()].copy()
mese_limite = st.selectbox('🕰️ Mostra solo medici visti prima di (incluso)', ['Nessuno'] + [m.capitalize() for m in mesi], index=0, key='mese_limite_visita')
if mese_limite != 'Nessuno':
    sel_num_limite = month_order[mese_limite.lower()]; df_filtrato = df_filtrato[df_filtrato['ultima visita'].str.lower().map(lambda m: month_order.get(m, 0)).le(sel_num_limite)].copy()
query = st.text_input('🔎 Cerca nei risultati', placeholder='Inserisci nome, città, microarea, ecc.', key='search_query')
if query: df_filtrato = df_filtrato[df_filtrato.astype(str).apply(lambda r: query.lower() in ' '.join(r).lower(), axis=1)].copy()
PERSIST_KEYS = ['filtro_spec','filtro_target','filtro_visto','giorno_scelto','fascia_oraria','provincia_scelta','microarea_scelta','search_query','custom_start','custom_end','ciclo_scelto','filtro_ultima_visita','mese_limite_visita','prov_escludi','voice_geo_scope','voice_geo_value','voice_geo_values','reference_doctor']
if st.session_state.pop('_skip_url_save_once', False): clear_all_query_params()
else: save_state_to_url(PERSIST_KEYS)

def min_start(row):
    ts=[]
    for c in colonne_da_mostrare:
        if c == 'ultima visita': continue
        stt,_ = parse_interval(row.get(c))
        if stt: ts.append(stt)
    return min(ts) if ts else datetime.time(23,59)
df_filtrato = df_filtrato.copy(); df_filtrato['__start'] = df_filtrato.apply(min_start, axis=1); month_order_sort = {m:i+1 for i,m in enumerate(mesi)}; month_order_sort[''] = 0; df_filtrato['__ult'] = df_filtrato['ultima visita'].str.lower().map(month_order_sort).fillna(0)
if st.session_state.get('reference_doctor'):
    ref = next((r for r in maps['doctor_records'] if r['name'] == st.session_state['reference_doctor']), None)
    df_filtrato['__rank_ref'] = (df_filtrato[cols['microarea']].astype(str).str.strip() != ref['microarea']).astype(int) if ref and cols['microarea'] and cols['microarea'] in df_filtrato.columns else 0
else: df_filtrato['__rank_ref'] = 0
df_filtrato = df_filtrato.sort_values(by=['__rank_ref','__ult','__start']).copy(); df_filtrato.drop(columns=['__ult','__start','__rank_ref'], inplace=True, errors='ignore')
if df_filtrato.empty: st.warning('Nessun risultato corrispondente ai filtri selezionati.'); st.stop()
df_filtrato['Visite ciclo'] = df_filtrato.apply(count_visits, axis=1)
if cols['nome_medico']: df_filtrato[cols['nome_medico']] = df_filtrato.apply(annotate_name, axis=1)
if 'Visite ciclo' not in colonne_da_mostrare: colonne_da_mostrare = [c for c in colonne_da_mostrare if c != 'Visite ciclo'] + ['Visite ciclo']
doctor_display_col = cols['nome_medico'] or colonne_da_mostrare[0]
st.write(f"**Numero medici:** {df_filtrato[doctor_display_col].astype(str).str.lower().nunique()} 🧮"); st.write('### Medici disponibili')
gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare]); gb.configure_default_column(sortable=True, filter=True, resizable=True, wrapText=True, autoHeight=True); gb.configure_grid_options(domLayout='autoHeight'); gb.configure_grid_options(suppressSizeToFit=False)
for c in colonne_da_mostrare: gb.configure_column(c, minWidth=120, autoHeaderHeight=True)
grid_options = gb.build(); grid_options['onFirstDataRendered'] = """function(event) { event.api.sizeColumnsToFit(); }"""
st.markdown("""<style>.ag-theme-streamlit-light, .ag-theme-streamlit-dark {width: 100% !important; min-width: 100% !important; overflow-x: auto;} .ag-header-cell-label {white-space: normal !important; text-overflow: clip !important; overflow: visible !important;} .ag-cell {white-space: normal !important; text-overflow: clip !important; overflow: visible !important;}</style>""", unsafe_allow_html=True)
AgGrid(df_filtrato[colonne_da_mostrare], gridOptions=grid_options, enable_enterprise_modules=False, fit_columns_on_grid_load=True, allow_unsafe_jscode=True, height=500, theme='streamlit')
st.download_button('📥 Scarica risultati CSV', df_filtrato[colonne_da_mostrare].to_csv(index=False).encode('utf-8'), 'risultati_medici.csv', 'text/csv')
