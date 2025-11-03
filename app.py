# ---------- VISUALIZZAZIONE & CSV RESPONSIVE (TABELLARE + CARD MOBILE) ----------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")

# Rileva automaticamente se l'utente è su mobile (larghezza schermo ridotta)
is_mobile = st.session_state.get("is_mobile", False)
if not is_mobile:
    # Prova a dedurre da user agent se disponibile
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
        window.parent.postMessage({isMobile: isMobile}, "*");
        </script>
        """,
        height=0,
    )
    # Flag temporaneo
    st.session_state["is_mobile"] = False

# Se Streamlit non riesce a leggere l'user agent, offri opzione manuale
if st.toggle("📱 Modalità Mobile (schede verticali)", value=False):
    st.session_state["is_mobile"] = True

# ---------- VISTA MOBILE (schede verticali) ----------
if st.session_state.get("is_mobile"):
    st.write("### 👇 Medici disponibili (vista mobile)")

    for _, r in df_filtrato.iterrows():
        st.markdown(f"""
        <div style="background:#ffffff;border:1px solid #dee2e6;border-radius:10px;
                    padding:12px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <b style="font-size:1.1rem;color:#007bff;">{r['nome medico']}</b><br>
            <small><b>Città:</b> {r['città']}</small><br>
            <small><b>Indirizzo:</b> {r['indirizzo ambulatorio']}</small><br>
            <small><b>Microarea:</b> {r['microarea']}</small><br>
            <small><b>Provincia:</b> {r['provincia']}</small><br>
            <small><b>Ultima visita:</b> {r['ultima visita']}</small>
        </div>
        """, unsafe_allow_html=True)

else:
    # ---------- VISTA DESKTOP / TABLET (AgGrid classica) ----------
    st.write("### Medici disponibili")

    from st_aggrid import AgGrid, GridOptionsBuilder

    gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gridOptions = gb.build()
    gridOptions["domLayout"] = "autoHeight"
    gridOptions["onFirstDataRendered"] = {
        "function": """
            setTimeout(() => {
                const allColumnIds = [];
                params.columnApi.getAllColumns().forEach(col => allColumnIds.push(col.colId));
                params.columnApi.autoSizeColumns(allColumnIds, false);
            }, 200);
        """
    }

    AgGrid(
        df_filtrato[colonne_da_mostrare],
        gridOptions=gridOptions,
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True,
        theme="balham",
    )

# ---------- DOWNLOAD CSV --------------------------------------------------------
st.download_button(
    "📥 Scarica risultati CSV",
    data=df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    file_name="risultati_medici.csv",
    mime="text/csv",
)
