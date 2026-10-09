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
import os
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import core
from core import Datos, fmt_ars, fmt_pct, fmt_facturas, parse_facturas, CATEGORIAS

ARCHIVO_DATOS = "datos.json"
ARCHIVO_EJEMPLO = "datos.ejemplo.json"

st.set_page_config(page_title="Monotributo FV", page_icon="🧾", layout="wide")


@st.cache_resource
def _estado():
    # `datos.json` no se versiona: cada instalación tiene el suyo. En una
    # instalación nueva todavía no existe, así que se arranca desde el ejemplo
    # (escalas de ARCA e inflación del INDEC, sin facturación) y el primer
    # guardado crea el datos.json propio.
    origen = ARCHIVO_DATOS if os.path.exists(ARCHIVO_DATOS) else ARCHIVO_EJEMPLO
    return {"datos": Datos.cargar(origen)}


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

    if an["escala_estimada"]:
        st.caption(f"⚠ No hay escala oficial cargada para {_label(recat)}: la categoría se estimó "
                   f"a partir de la escala vigente desde {an['escala_vigencia']}, actualizada por inflación.")

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
        st.markdown(f"**Objetivo — Categoría meta {ob['categoria_meta']}** "
                    f"(recat. {_label(ob['recat'])})")
        st.metric("Tope actual", fmt_ars(ob["tope_actual"]))
        st.metric("Tope proyectado por inflación", fmt_ars(ob["tope_proyectado"]),
                  help=("Escala estimada: la última publicada, actualizada por la inflación "
                        f"del semestre ({fmt_pct(ob['inflacion_estimada_semestre'])})."
                        if ob["tope_es_estimado"] else
                        "Escala oficial ya publicada por ARCA para esta recategorización."))
        st.metric("Ya facturado en esta ventana", fmt_ars(ob["ya_facturado"]),
                  help=f"Ventana {ob['meses_ventana'][0]} a {ob['meses_ventana'][-1]}: "
                       "suma de los meses ya transcurridos (los que no tienen facturación "
                       "cargada computan $0).")
        st.metric("Margen disponible (proyectado)", fmt_ars(ob["margen_proyectado"]))
        if ob["meses_restantes"]:
            st.metric(f"Promedio mensual disponible ({len(ob['meses_restantes'])} meses)",
                      fmt_ars(ob["promedio_mensual_proyectado"]),
                      help="Meses de la ventana que todavía no ocurrieron: "
                           + ", ".join(ob["meses_restantes"]))
        else:
            st.caption("La ventana de esta recategorización ya está cerrada: "
                       "no quedan meses por facturar.")
        if ob["margen_proyectado"] is not None and ob["margen_proyectado"] < 0:
            st.warning(f"Ya superaste el tope proyectado de la categoría "
                       f"{ob['categoria_meta']} por {fmt_ars(-ob['margen_proyectado'])}.")
        if an["escala"]:
            st.caption(f"Escala vigente desde {an['escala_vigencia']}")

    st.markdown("---")
    st.markdown("**Evolución de la facturación entre recategorizaciones**")
    st.caption("Facturación real de cada recategorización vs. esa misma facturación "
               f"actualizada por inflación a pesos de {_label(recat)}, para comparar entre sí.")
    hist = core.serie_historica(datos, recat)
    if len(hist) < 2:
        st.caption("Necesitás al menos dos recategorizaciones con datos para ver la evolución.")
    else:
        col_actualizada = f"Actualizada a pesos de {_label(recat)}"
        df_hist = pd.DataFrame({
            "recat": [r["recat"] for r in hist],
            "Recategorización": [_label(r["recat"]) for r in hist],
            "Categoría": [
                (r["categoria"] or "EXCLUIDO") + (" (est.)" if r["escala_estimada"] else "")
                for r in hist
            ],
            "Facturación real": [r["total"] for r in hist],
            col_actualizada: [r["total_actualizado"] for r in hist],
        })
        # Barras superpuestas (no apiladas): la ancha/clara es la actualizada
        # por inflación y la angosta/oscura, la real, para poder comparar
        # ambas sin que el alto visual sea la suma de las dos.
        orden = df_hist["recat"].tolist()
        escala_color = alt.Scale(domain=["Facturación real", col_actualizada],
                                  range=["#1a73e8", "#a8c7fa"])
        df_actualizada = df_hist[["recat", col_actualizada]].rename(columns={col_actualizada: "valor"})
        df_actualizada["Serie"] = col_actualizada
        df_real = df_hist[["recat", "Facturación real"]].rename(columns={"Facturación real": "valor"})
        df_real["Serie"] = "Facturación real"

        capa_actualizada = alt.Chart(df_actualizada).mark_bar(opacity=0.6).encode(
            x=alt.X("recat:N", sort=orden, title=None),
            y=alt.Y("valor:Q", title="Facturación ($)"),
            color=alt.Color("Serie:N", scale=escala_color, legend=alt.Legend(title=None)),
            tooltip=["recat", "Serie", "valor"])
        capa_real = alt.Chart(df_real).mark_bar().encode(
            x=alt.X("recat:N", sort=orden),
            y=alt.Y("valor:Q"),
            color=alt.Color("Serie:N", scale=escala_color),
            tooltip=["recat", "Serie", "valor"])
        st.altair_chart((capa_actualizada + capa_real).properties(height=300), use_container_width=True)
        st.dataframe(
            df_hist.drop(columns="recat").assign(**{
                "Facturación real": df_hist["Facturación real"].map(fmt_ars),
                col_actualizada: df_hist[col_actualizada].map(
                    lambda v: fmt_ars(v) if pd.notna(v) else "—"),
            }),
            hide_index=True, use_container_width=True)
        if any(r["total_actualizado"] is None for r in hist):
            st.caption("⚠ Alguna recategorización no se pudo actualizar por inflación "
                       "por faltar una tasa mensual en el camino hasta la seleccionada.")

# --------------------------------------------------------------- facturación
with tab_fact:
    st.subheader("Facturación mensual")
    st.caption(
        "Para cada mes, escribí el monto de cada factura separado por «+» "
        "(ej.: 500000 + 12000000 + 850000), igual que en el Excel. "
        "La cantidad y el total se calculan solos, para saber si ya cargaste todas. "
        "Dejá vacío un mes futuro para que no compute."
    )
    serie = dict(sorted(datos.facturacion.items()))
    # dtype explícito: con la facturación vacía pandas infiere columnas float
    # y el editor falla al configurarlas como texto.
    df = pd.DataFrame({
        "Mes": pd.Series(list(serie), dtype="object"),
        "Facturas": pd.Series([fmt_facturas(montos) for montos in serie.values()],
                              dtype="object"),
    })
    editado = st.data_editor(
        df, hide_index=True, num_rows="dynamic", use_container_width=True,
        key="editor_fact",
        column_config={
            "Mes": st.column_config.TextColumn("Mes (YYYY-MM)"),
            "Facturas": st.column_config.TextColumn(
                "Facturas (separadas por +)", width="large"),
        },
    )

    filas_resumen = []
    filas_invalidas = []
    for _, fila in editado.iterrows():
        mes = str(fila["Mes"]).strip()[:7]
        texto = str(fila["Facturas"]).strip() if not pd.isna(fila["Facturas"]) else ""
        if not mes:
            continue
        try:
            montos = parse_facturas(texto)
        except ValueError:
            filas_invalidas.append(mes)
            continue
        filas_resumen.append({
            "Mes": mes,
            "Cantidad de facturas": len(montos),
            "Total": fmt_ars(sum(montos)) if montos else "sin datos",
        })

    if filas_resumen:
        st.dataframe(pd.DataFrame(filas_resumen), hide_index=True, use_container_width=True)
    if filas_invalidas:
        st.error("Hay montos que no se pudieron interpretar como número (revisá que estén "
                 "separados por «+») en: " + ", ".join(filas_invalidas))

    if st.button("💾 Guardar cambios", type="primary", disabled=bool(filas_invalidas)):
        nueva = {}
        for _, fila in editado.iterrows():
            mes = str(fila["Mes"]).strip()[:7]
            texto = str(fila["Facturas"]).strip() if not pd.isna(fila["Facturas"]) else ""
            if len(mes) != 7:
                continue
            montos = parse_facturas(texto)
            if montos:
                nueva[mes] = montos
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
