# ---------- % MMG VISTI (CICLO) - CARD MINIMAL ---------------------------------
try:
    ciclo_cols = [c for c in visto_cols if c in df_mmg.columns]
    if ciclo_cols and "nome medico" in df_mmg.columns:
        # calcoli: dedup per nome medico, conta x/v nel ciclo selezionato
        df_mmg["_nome_norm"] = df_mmg["nome medico"].astype(str).str.strip().str.lower()

        is_mmg = df_mmg.get("spec", pd.Series("", index=df_mmg.index)).astype(str).str.strip().str.upper() == "MMG"
        is_in_target = df_mmg.get("in target", pd.Series("", index=df_mmg.index)).astype(str).str.strip().str.lower() == "x"
        base_mask = is_mmg & is_in_target

        total_mmg_target = int(df_mmg[base_mask]["_nome_norm"].nunique())

        def _row_has_visit_vals(vals):
            for v in vals:
                if str(v).strip().lower() in ["x", "v"]:
                    return True
            return False

        seen_rows = df_mmg[ciclo_cols].apply(lambda r: _row_has_visit_vals(r.values), axis=1)
        seen_count = int(df_mmg[base_mask & seen_rows]["_nome_norm"].nunique())

        pct = int(round((seen_count / total_mmg_target) * 100)) if total_mmg_target > 0 else 0

        # UI minimal
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

        # pulizia colonna temporanea
        df_mmg.drop(columns=["_nome_norm"], inplace=True, errors="ignore")
    else:
        # niente crash, solo silenzioso
        pass

except Exception:
    import traceback
    traceback.print_exc()
