"""
app.py — Monotributo FV: planificador de recategorización (Streamlit).

Ejecutar:
    streamlit run app.py

Pestañas:
- Dashboard: análisis de la recategorización seleccionada (réplica del Excel).
- Facturación: carga/edición mensual.
- Datos y escalas: inflación real/estimada y escalas de topes, con botones
  de actualización online (API ArgentinaDatos + página de ARCA).
- Reporte: genera y descarga el PDF de resumen.
"""
from __future__ import annotations
from datetime import date

import pandas as pd
import streamlit as st

import core
from core import Datos, fmt_ars, fmt_pct, CATEGORIAS

ARCHIVO_DATOS = "datos.json"

st.set_page_config(page_title="Monotributo FV", page_icon="🧾", layout="wide")


@st.cache_resource
def _estado():
    return {"datos": Datos.cargar(ARCHIVO_DATOS)}


estado = _estado()
datos: Datos = estado["datos"]


def guardar():
    datos.guardar(ARCHIVO_DATOS)


# ------------------------------------------------------------------ sidebar
st.sidebar.title("🧾 Monotributo FV")
recats_posibles = []
if datos.facturacion:
    primero = min(datos.facturacion)
    a0 = int(primero[:4])
    hoy = date.today()
    for a in range(a0, hoy.year + 2):
        for m in (1, 7):
            r = core.mes_key(a, m)
            if r >= core.mes_key(a0, 7):
                recats_posibles.append(r)
recat_default = core.recat_vigente()
if recat_default not in recats_posibles:
    recats_posibles.append(recat_default)
recats_posibles.sort()

def _label(r):
    return ("Julio " if r.endswith("07") else "Enero ") + r[:4]

recat = st.sidebar.selectbox(
    "Recategorización a analizar", recats_posibles,
    index=recats_posibles.index(recat_default), format_func=_label)

meta = st.sidebar.selectbox(
    "Categoría meta", CATEGORIAS, index=CATEGORIAS.index(datos.categoria_meta))
if meta != datos.categoria_meta:
    datos.categoria_meta = meta
    guardar()

datos.contribuyente = st.sidebar.text_input("Contribuyente", datos.contribuyente)
datos.cuit = st.sidebar.text_input("CUIT", datos.cuit)

tab_dash, tab_fact, tab_datos, tab_rep = st.tabs(
    ["📊 Dashboard", "🧮 Facturación", "🔄 Datos y escalas", "📄 Reporte PDF"])

# ---------------------------------------------------------------- dashboard
with tab_dash:
    an = core.analizar_recat(datos, recat)
    ob = core.objetivo(datos, recat)

    st.subheader(f"Recategorización {_label(recat)}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Facturación 12 meses", fmt_ars(an["total"]))
    c2.metric("Categoría resultante", an["categoria"] or "EXCLUIDO")
    c3.metric("Aumento nominal", fmt_pct(an["aumento_nominal"]),
              help="vs. total de la recategorización anterior")
    c4.metric("Variación real", fmt_pct(an["variacion_real"]),
              delta=fmt_pct(an["variacion_real"]),
              help=f"Deflactado por inflación del semestre: {fmt_pct(an['inflacion_6m'])}")

    if an["meses_sin_inflacion"]:
        st.warning("Faltan tasas de inflación (real o estimada) para: "
                   + ", ".join(an["meses_sin_inflacion"])
                   + ". Cargalas en la pestaña «Datos y escalas».")

    col_izq, col_der = st.columns([3, 2])
    with col_izq:
        st.markdown("**Ventana de 12 meses computada**")
        df = pd.DataFrame({
            "Mes": an["meses"],
            "Facturado": [an["facturacion"][m] for m in an["meses"]],
        })
        st.bar_chart(df.set_index("Mes"), height=260)
        st.dataframe(
            df.assign(Facturado=df["Facturado"].map(lambda v: fmt_ars(v) if pd.notna(v) else "sin datos")),
            hide_index=True, use_container_width=True)

    with col_der:
        st.markdown(f"**Objetivo — Categoría {ob['categoria_meta']}** "
                    f"(próxima recat.: {_label(ob['recat_proxima'])})")
        st.metric("Tope actual", fmt_ars(ob["tope_actual"]))
        st.metric("Tope proyectado por inflación", fmt_ars(ob["tope_proyectado"]),
                  help=f"Inflación estimada del semestre: {fmt_pct(ob['inflacion_estimada_semestre'])}")
        st.metric("Ya facturado en la nueva ventana", fmt_ars(ob["ya_facturado"]))
        st.metric("Margen disponible (proyectado)", fmt_ars(ob["margen_proyectado"]))
        if ob["meses_restantes"]:
            st.metric(f"Promedio mensual disponible ({len(ob['meses_restantes'])} meses)",
                      fmt_ars(ob["promedio_mensual_proyectado"]))
        if an["escala"]:
            st.caption(f"Escala vigente desde {an['escala_vigencia']}")

# --------------------------------------------------------------- facturación
with tab_fact:
    st.subheader("Facturación mensual")
    st.caption("Editá los montos y presioná «Guardar cambios». "
               "Dejá vacío un mes futuro para que no compute.")
    if datos.facturacion:
        todos = core.iter_meses(min(datos.facturacion), 0) or []
    serie = dict(sorted(datos.facturacion.items()))
    df = pd.DataFrame({"Mes": list(serie), "Monto": list(serie.values())})
    editado = st.data_editor(df, hide_index=True, num_rows="dynamic",
                             use_container_width=True, key="editor_fact")
    if st.button("💾 Guardar cambios", type="primary"):
        nueva = {}
        for _, fila in editado.iterrows():
            mes = str(fila["Mes"]).strip()[:7]
            if len(mes) == 7 and fila["Monto"] is not None and not pd.isna(fila["Monto"]):
                nueva[mes] = float(fila["Monto"])
        datos.facturacion = nueva
        guardar()
        st.success("Facturación guardada.")
        st.rerun()

# ------------------------------------------------------------ datos/escalas
with tab_datos:
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Inflación mensual")
        if st.button("🔄 Traer inflación real (INDEC vía ArgentinaDatos)"):
            try:
                import actualizador
                nueva = actualizador.traer_inflacion()
                datos.inflacion.update(nueva)
                guardar()
                st.success(f"Inflación actualizada: {len(nueva)} meses "
                           f"(último: {max(nueva)}, {fmt_pct(nueva[max(nueva)])}).")
            except Exception as e:
                st.error(f"No se pudo actualizar: {e}")

        st.markdown("**Real (INDEC)** — editable")
        df_i = pd.DataFrame({"Mes": list(datos.inflacion),
                             "Tasa %": [v * 100 for v in datos.inflacion.values()]})
        df_i = df_i.sort_values("Mes", ascending=False)
        ed_i = st.data_editor(df_i, hide_index=True, num_rows="dynamic",
                              use_container_width=True, key="ed_inf", height=250)

        st.markdown("**Estimada** (para meses sin dato oficial / proyección)")
        df_e = pd.DataFrame({"Mes": list(datos.inflacion_estimada),
                             "Tasa %": [v * 100 for v in datos.inflacion_estimada.values()]})
        ed_e = st.data_editor(df_e, hide_index=True, num_rows="dynamic",
                              use_container_width=True, key="ed_est", height=200)

        if st.button("💾 Guardar inflación"):
            datos.inflacion = {str(r["Mes"])[:7]: float(r["Tasa %"]) / 100
                               for _, r in ed_i.iterrows() if not pd.isna(r["Tasa %"])}
            datos.inflacion_estimada = {str(r["Mes"])[:7]: float(r["Tasa %"]) / 100
                                        for _, r in ed_e.iterrows() if not pd.isna(r["Tasa %"])}
            guardar()
            st.success("Inflación guardada.")

    with col_b:
        st.subheader("Escalas de Monotributo (topes anuales)")
        if st.button("🔄 Traer escalas vigentes desde ARCA"):
            try:
                import actualizador
                escala = actualizador.traer_escalas()
                hoy = date.today()
                vigencia = core.mes_key(hoy.year, 7 if hoy.month >= 7 else 1)
                datos.escalas[vigencia] = escala
                guardar()
                st.success(f"Escala cargada con vigencia {vigencia}. "
                           f"Tope K: {fmt_ars(escala['K'])}.")
            except Exception as e:
                st.error(f"No se pudo leer la página de ARCA: {e}")

        vigencias = sorted(datos.escalas, reverse=True)
        if vigencias:
            vig_sel = st.selectbox("Vigencia", vigencias)
            esc = datos.escalas[vig_sel]
            df_s = pd.DataFrame({"Categoría": CATEGORIAS,
                                 "Tope anual": [esc.get(c) for c in CATEGORIAS]})
            ed_s = st.data_editor(df_s, hide_index=True, use_container_width=True, key="ed_esc")
            c_g, c_n = st.columns(2)
            if c_g.button("💾 Guardar escala"):
                datos.escalas[vig_sel] = {str(r["Categoría"]): float(r["Tope anual"])
                                          for _, r in ed_s.iterrows() if not pd.isna(r["Tope anual"])}
                guardar()
                st.success("Escala guardada.")
        nueva_vig = st.text_input("Agregar nueva vigencia (YYYY-MM, ej. 2026-07)")
        if st.button("➕ Crear vigencia") and len(nueva_vig) == 7:
            base = datos.escalas.get(max(datos.escalas), {}) if datos.escalas else {}
            datos.escalas[nueva_vig] = dict(base)
            guardar()
            st.rerun()

# -------------------------------------------------------------------- PDF
with tab_rep:
    st.subheader("Reporte PDF de recategorización")
    st.caption("Resumen imprimible con la ventana de 12 meses, categoría, "
               "comparación real/nominal y objetivo hacia la próxima recategorización.")
    if st.button("📄 Generar reporte", type="primary"):
        import reporte
        pdf = reporte.generar_pdf(datos, recat)
        nombre = f"recategorizacion_{recat.replace('-', '_')}.pdf"
        st.download_button("⬇️ Descargar PDF", data=pdf, file_name=nombre,
                           mime="application/pdf")
        st.success("Reporte generado.")
