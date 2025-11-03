# ---------- VISUALIZZAZIONE & CSV (AUTO-FIT MIGLIORATO) -------------------------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

# Costruisci le opzioni della griglia
gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
gb.configure_default_column(sortable=True, filter=True, resizable=True)

# Imposta comportamento: adatta automaticamente tutte le colonne al contenuto
gridOptions = gb.build()
gridOptions["domLayout"] = "autoHeight"
gridOptions["onFirstDataRendered"] = {
    "function": """
        setTimeout(() => {
            const allColumnIds = [];
            params.columnApi.getAllColumns().forEach(col => allColumnIds.push(col.colId));
            params.columnApi.autoSizeColumns(allColumnIds, false);
        }, 150);
    """
}

AgGrid(
    df_filtrato[colonne_da_mostrare],
    gridOptions=gridOptions,
    enable_enterprise_modules=False,
    allow_unsafe_jscode=True,   # consente di eseguire lo script JS sopra
    theme="balham",             # tema chiaro gradevole
)

# ---------- DOWNLOAD CSV --------------------------------------------------------
st.download_button(
    "📥 Scarica risultati CSV",
    df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    file_name="risultati_medici.csv",
    mime="text/csv",
)
