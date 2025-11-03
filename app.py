# ---------- VISUALIZZAZIONE & CSV ----------------------------------------------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

# CSS per rendere la tabella scrollabile orizzontalmente su mobile
st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] > div {
    overflow-x: auto !important;
}
.ag-theme-streamlit-light {
    min-width: 700px;  /* mantiene larghezza leggibile */
}
</style>
""", unsafe_allow_html=True)

# Griglia con larghezza automatica vera
gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
gb.configure_default_column(
    sortable=True,
    filter=True,
    resizable=True,
    wrapText=False,        # non va a capo
    autoHeight=False       # righe compatte
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

# Contenitore scrollabile orizzontale
with st.container():
    st.markdown('<div style="overflow-x:auto;">', unsafe_allow_html=True)
    AgGrid(
        df_filtrato[colonne_da_mostrare],
        gridOptions=gridOptions,
        enable_enterprise_modules=False,
        fit_columns_on_grid_load=False,
        height=600,
    )
    st.markdown('</div>', unsafe_allow_html=True)

# ---------- DOWNLOAD CSV --------------------------------------------------------
st.download_button(
    "📥 Scarica risultati CSV",
    df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    "risultati_medici.csv",
    "text/csv",
)
