import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
import datetime
import re
import pytz  # per gestire il fuso orario

# Imposta il fuso orario desiderato (es. "Europe/Rome")
timezone = pytz.timezone("Europe/Rome")

# Configurazione della pagina
st.set_page_config(page_title="Filtro Medici - Ricevimento Settimanale", layout="centered")

# ---------- FUNZIONI UTILI ------------------------------------------------------
def parse_interval(cell_value):
    if pd.isna(cell_value):
        return None, None
    s = str(cell_value).strip()
    m = re.match(r'(\d{1,2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}(?::\d{2})?)', s)
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

# ---------- CSS -----------------------------------------------------------------
st.markdown(
    """
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
    """,
    unsafe_allow_html=True,
)

st.title("📋 Filtro Medici - Ricevimento Settimanale")

# ---------- COSTANTI ------------------------------------------------------------
default_spec = ["MMG", "PED"]
spec_extra   = ["ORT", "FIS", "REU", "DOL", "OTO", "DER", "INT", "END", "DIA"]
mesi = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
        "luglio","agosto","settembre","ottobre","novembre","dicembre"]

# ---------- RESET FILTRI ---------------------------------------------------------
def azzera_filtri():
    for k in [
        "filtro_spec","filtro_target","filtro_visto","giorno_scelto","fascia_oraria",
        "provincia_scelta","microarea_scelta","search_query","custom_start","custom_end",
        "ciclo_scelto","filtro_frequenza","filtro_ultima_visita"
    ]:
        st.session_state.pop(k, None)
    st.experimental_rerun()

st.button("🔄 Azzera tutti i filtri", on_click=azzera_filtri)

# ---------- PULSANTI RAPIDI ------------------------------------------------------
if st.button("Specialisti 👨‍⚕️👩‍⚕️"):
    st.session_state["filtro_spec"] = (
        spec_extra if st.session_state.get("filtro_spec", default_spec) == default_spec else default_spec
    )
    st.experimental_rerun()

if st.button("MMG + PED 🩺"):
    st.session_state["filtro_spec"] = ["MMG", "PED"]
    st.experimental_rerun()

# ---------- CARICAMENTO FILE ----------------------------------------------------
file = st.file_uploader("Carica il file Excel", type=["xlsx"])
if not file:
    st.stop()

xls = pd.ExcelFile(file)
df_mmg = pd.read_excel(xls, sheet_name="MMG")
df_mmg.columns = df_mmg.columns.str.lower()
if "provincia" in df_mmg.columns:
    df_mmg["provincia"] = df_mmg["provincia"].astype(str).str.strip()
if "microarea" in df_mmg.columns:
    df_mmg["microarea"] = df_mmg["microarea"].astype(str).str.strip()

# ---------- CALCOLO "ULTIMA VISITA" ---------------------------------------------
def get_ultima_visita(row):
    ultima = ""
    for m in mesi:
        if m in row and str(row[m]).strip().lower() == "x":
            ultima = m.capitalize()
    return ultima
df_mmg["ultima visita"] = df_mmg.apply(get_ultima_visita, axis=1)

# ---------- SELEZIONE CICLO + KPI -----------------------------------------------
ciclo_opts = ["Tutti",
              "Ciclo 1 (Gen-Feb-Mar)",
              "Ciclo 2 (Apr-Mag-Giu)",
              "Ciclo 3 (Lug-Ago-Set)",
              "Ciclo 4 (Ott-Nov-Dic)"]
today = datetime.datetime.now(timezone)
default_cycle_idx = 1 + (today.month-1)//3
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
visto_cols = ( [m for m in mesi if m in df_mmg.columns]
               if ciclo_scelto=="Tutti" else month_cycles[ciclo_scelto] )

df_target = df_mmg[
    (df_mmg["spec"].isin(["MMG","PED"])) &
    (df_mmg["in target"].str.strip().str.lower()=="x")
]
visited = df_target[
    df_target[visto_cols].apply(lambda r: any(str(x).strip().lower() in ["x","v"] for x in r), axis=1)
]
perc = int(len(visited)/len(df_target)*100) if len(df_target) else 0
st.markdown(f"**Medici visti in {ciclo_scelto}: {perc}%**", unsafe_allow_html=True)
st.markdown(
    f"""
    <div style="width:100%;background:#e0e0e0;border-radius:10px;margin:10px 0">
      <div style="width:{perc}%;background:#007bff;height:25px;border-radius:7px;
                  text-align:center;color:#fff;font-weight:bold">{perc}%</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- *** NUOVA POSIZIONE: SELEZIONE MESE *** -----------------------------
lista_mesi_cap = [m.capitalize() for m in mesi]
filtro_ultima = st.selectbox(
    "Seleziona mese ultima visita",
    ["Nessuno"] + lista_mesi_cap,
    index=0,
    key="filtro_ultima_visita",
)

# ---------- FILTRO SPEC / TARGET / VISTO / FREQUENZA ----------------------------
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
    index=["In target","Non in target","Tutti"].index(st.session_state.get("filtro_target","In target")),
    key="filtro_target",
)
filtro_visto = st.selectbox(
    "👀 Filtra per medici 'VISTO'",
    ["Tutti","Visto","Non Visto","Visita VIP"],
    index=["Tutti","Visto","Non Visto","Visita VIP"].index(st.session_state.get("filtro_visto","Non Visto")),
    key="filtro_visto",
)

df_mmg[visto_cols] = df_mmg[visto_cols].fillna("").applymap(
    lambda s: s.lower().strip() if isinstance(s,str) else str(s).strip().lower()
)

df_in_target  = df_mmg[df_mmg["in target"].str.strip().str.lower()=="x"]
df_non_target = df_mmg[~(df_mmg["in target"].str.strip().str.lower()=="x")]
df_filtered_target = (
    df_in_target if filtro_target=="In target" else
    df_non_target if filtro_target=="Non in target" else
    pd.concat([df_in_target, df_non_target])
)

def is_visited(row):
    freq = str(row.get("frequenza","")).strip().lower()
    if freq=="x":
        return sum(1 for c in visto_cols if row[c] in ["x","v"]) >= 2
    return any(row[c] in ["x","v"] for c in visto_cols)

if filtro_visto=="Visto":
    df_mmg = df_filtered_target[df_filtered_target.apply(is_visited, axis=1)]
elif filtro_visto=="Non Visto":
    df_mmg = df_filtered_target[~df_filtered_target.apply(is_visited, axis=1)]
elif filtro_visto=="Visita VIP":
    df_mmg = df_filtered_target[df_filtered_target[visto_cols].eq("v").any(axis=1)]
else:
    df_mmg = df_filtered_target.copy()

if st.checkbox("🔔 FREQUENZA", value=False, key="filtro_frequenza"):
    if "frequenza" in df_mmg.columns:
        df_mmg = df_mmg[df_mmg["frequenza"].str.strip().str.lower()=="x"]

# ---------- FILTRO GIORNO / FASCIA ORARIA ---------------------------------------
oggi = datetime.datetime.now(timezone)
giorni_settimana = ["lunedì","martedì","mercoledì","giovedì","venerdì"]
giorni_opz = ["sempre"] + giorni_settimana
giorno_default = (
    giorni_settimana[oggi.weekday()] if oggi.weekday() < 5 else "sempre"
)
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
    index=fascia_opts.index(st.session_state.get("fascia_oraria","Personalizzato")),
    key="fascia_oraria",
)

if fascia_oraria=="Personalizzato":
    if "custom_start" not in st.session_state or "custom_end" not in st.session_state:
        now = datetime.datetime.now(timezone)
        st.session_state["custom_start"] = now.time()
        st.session_state["custom_end"]   = (now+datetime.timedelta(minutes=15)).time()
    default_min = datetime.datetime.combine(datetime.date.today(), datetime.time(7,0))
    default_max = datetime.datetime.combine(datetime.date.today(), datetime.time(19,0))
    t_start, t_end = st.slider(
        "Seleziona l'intervallo orario",
        min_value=default_min,
        max_value=default_max,
        value=(
            datetime.datetime.combine(datetime.date.today(), st.session_state["custom_start"]),
            datetime.datetime.combine(datetime.date.today(), st.session_state["custom_end"]),
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
    giorni = giorni_settimana if giorno_scelto=="sempre" else [giorno_scelto]
    colonne = []
    for g in giorni:
        if fascia_oraria in ["Mattina","Mattina e Pomeriggio"]:
            colonne.append(f"{g} mattina")
        if fascia_oraria in ["Pomeriggio","Mattina e Pomeriggio"]:
            colonne.append(f"{g} pomeriggio")
        if fascia_oraria=="Personalizzato":
            for suf in ["mattina","pomeriggio"]:
                col=f"{g} {suf}"
                if col in df_base.columns:
                    colonne.append(col)
    colonne=[c.lower() for c in colonne if c.lower() in df_base.columns]
    if not colonne:
        st.error("Le colonne per il filtro giorno/fascia non esistono nel file.")
        st.stop()
    if fascia_oraria=="Personalizzato":
        return df_base[
            df_base[colonne].apply(
                lambda r: any(interval_covers(r[c],custom_start,custom_end) for c in colonne),
                axis=1,
            )
        ], colonne
    return df_base[df_base[colonne].notna().any(axis=1)], colonne

df_filtrato, colonne_da_mostrare = filtra_giorno_fascia(df_mmg)
colonne_da_mostrare = ["nome medico","città"] + colonne_da_mostrare + [
    "indirizzo ambulatorio","microarea","provincia","ultima visita"
]

# ---------- VISITE CICLO & ASTERISCHI ------------------------------------------
def count_visits(row):
    freq=str(row.get("frequenza","")).strip().lower()
    tot=0
    for c in visto_cols:
        v=row[c]
        if freq=="x" and v in ["x","v"]: tot+=1
        if freq!="x" and v=="x":         tot+=1
    return tot
df_filtrato["Visite ciclo"] = df_filtrato[visto_cols].apply(count_visits, axis=1)
colonne_da_mostrare.append("Visite ciclo")

if "frequenza" in df_filtrato.columns:
    df_filtrato["nome medico"] = df_filtrato.apply(
        lambda r: f"{r['nome medico']} * ({r['Visite ciclo']})"
        if str(r.get("frequenza","")).strip().lower()=="x" else r["nome medico"],
        axis=1,
    )

# ---------- MICROAREE (multiselect) --------------------------------------------
microarea_lista = sorted(df_mmg["microarea"].dropna().unique().tolist())
micro_sel = st.multiselect(
    "Seleziona Microaree",
    options=microarea_lista,
    default=st.session_state.get("microarea_scelta", []),
    key="microarea_scelta",
)
if micro_sel:
    df_filtrato = df_filtrato[df_filtrato["microarea"].isin(micro_sel)]

# ---------- APPLICA FILTRO MESE (in base alla selezione fatta sopra) -----------
if filtro_ultima!="Nessuno":
    df_filtrato = df_filtrato[df_filtrato["ultima visita"].str.lower()==filtro_ultima.lower()]

# ---------- FILTRO PROVINCIA ----------------------------------------------------
prov_lista = ["Ovunque"] + sorted(p for p in df_mmg["provincia"].dropna().unique() if p.lower()!="nan")
prov_sel = st.selectbox(
    "📍 Scegli la Provincia",
    prov_lista,
    index=prov_lista.index(st.session_state.get("provincia_scelta","Ovunque")),
    key="provincia_scelta",
)
if prov_sel.lower()!="ovunque":
    df_filtrato = df_filtrato[df_filtrato["provincia"].str.lower()==prov_sel.lower()]

# ---------- RICERCA TESTUALE ----------------------------------------------------
query = st.text_input(
    "🔎 Cerca nei risultati",
    placeholder="Inserisci nome, città, microarea, ecc.",
    key="search_query",
)
if query:
    q=query.lower()
    df_filtrato = df_filtrato[
        df_filtrato.drop(columns=["provincia"], errors="ignore")
        .astype(str)
        .apply(lambda r: q in " ".join(r).lower(), axis=1)
    ]

# ---------- ORDINAMENTO ---------------------------------------------------------
def min_start(row):
    ts=[]
    for c in colonne_da_mostrare:
        if c in ["nome medico","città","indirizzo ambulatorio","microarea","provincia","ultima visita","Visite ciclo"]:
            continue
        stt,_=parse_interval(row.get(c))
        if stt: ts.append(stt)
    return min(ts) if ts else datetime.time(23,59)
df_filtrato["__start"]=df_filtrato.apply(min_start,axis=1)
month_order={m:i+1 for i,m in enumerate(mesi)};month_order[""]=0
df_filtrato["__ult"]=df_filtrato["ultima visita"].str.lower().map(month_order).fillna(0)
df_filtrato=df_filtrato.sort_values(by=["__ult","__start"]);df_filtrato.drop(columns=["__ult","__start"],inplace=True)

# ---------- VISUALIZZAZIONE & CSV ----------------------------------------------
if df_filtrato.empty:
    st.warning("Nessun risultato corrispondente ai filtri selezionati.")
else:
    st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
    st.write("### Medici disponibili")
    gb=GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
    gb.configure_default_column(sortable=True,filter=True,resizable=False,width=100,lockPosition=True)
    gb.configure_column("nome medico",width=150)
    gb.configure_column("città",width=120)
    gb.configure_column("indirizzo ambulatorio",width=200)
    gb.configure_column("microarea",width=120)
    gb.configure_column("provincia",width=120)
    gb.configure_column("ultima visita",width=120)
    gb.configure_column("Visite ciclo",width=120)
    AgGrid(df_filtrato[colonne_da_mostrare],gridOptions=gb.build(),enable_enterprise_modules=False)
    st.download_button(
        "Scarica risultati CSV",
        df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
        "risultati_medici.csv",
        "text/csv",
    )
