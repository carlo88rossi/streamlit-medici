# ---------- VISUALIZZAZIONE & CSV (AUTO-FIT STABILE PER CLOUD) ------------------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

# Costruisci la griglia
gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])

# ✅ Permette di ridimensionare automaticamente tutte le colonne in base al contenuto
gb.configure_default_column(
    sortable=True,
    filter=True,
    resizable=True,
)

gridOptions = gb.build()
gridOptions["domLayout"] = "autoHeight"

# 👉 Auto-fit dinamico per tutte le colonne (funziona anche su Streamlit Cloud)
gridOptions["onFirstDataRendered"] = {
    "function": """
        setTimeout(() => {
            const allColumnIds = [];
            params.columnApi.getAllColumns().forEach(col => allColumnIds.push(col.colId));
            params.columnApi.autoSizeColumns(allColumnIds, false);
        }, 300);
    """
}

# Visualizza la tabella
AgGrid(
    df_filtrato[colonne_da_mostrare],
    gridOptions=gridOptions,
    enable_enterprise_modules=False,
    allow_unsafe_jscode=True,   # consente l'auto-fit JS
    theme="balham",             # tema chiaro leggibile
)

# Pulsante di download
st.download_button(
    "📥 Scarica risultati CSV",
    df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    file_name="risultati_medici.csv",
    mime="text/csv",
)
