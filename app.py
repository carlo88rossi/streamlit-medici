# ---------- VISUALIZZAZIONE & CSV (VERSIONE AUTO-FIT COLONNE COMPLETA) ----------
st.write(f"**Numero medici:** {df_filtrato['nome medico'].str.lower().nunique()} 🧮")
st.write("### Medici disponibili")

# Costruzione dinamica griglia
gb = GridOptionsBuilder.from_dataframe(df_filtrato[colonne_da_mostrare])
gb.configure_default_column(
    sortable=True,
    filter=True,
    resizable=True,
)

# Imposta l’altezza automatica della griglia
gridOptions = gb.build()
gridOptions["domLayout"] = "autoHeight"

# 👉 Forza l’adattamento automatico di TUTTE le colonne al contenuto
# tramite evento onFirstDataRendered
gridOptions["onFirstDataRendered"] = {
    "function": """
        setTimeout(() => {
            const allColumnIds = [];
            params.columnApi.getAllColumns().forEach(col => allColumnIds.push(col.colId));
            params.columnApi.autoSizeColumns(allColumnIds, false);
        }, 100);
    """
}

# Visualizza la tabella adattiva
AgGrid(
    df_filtrato[colonne_da_mostrare],
    gridOptions=gridOptions,
    enable_enterprise_modules=False,
    allow_unsafe_jscode=True,  # serve per eseguire lo script JS sopra
    theme="balham",
)

# ---------- DOWNLOAD CSV --------------------------------------------------------
st.download_button(
    "📥 Scarica risultati CSV",
    data=df_filtrato[colonne_da_mostrare].to_csv(index=False).encode("utf-8"),
    file_name="risultati_medici.csv",
    mime="text/csv",
)
