"""
reporte.py — Reporte PDF de recategorización (A4) con reportlab.

Genera un resumen imprimible: datos del contribuyente, ventana de 12 meses,
total anual, categoría resultante, comparación nominal/real vs. semestre
anterior y objetivo de facturación hacia la próxima recategorización.
"""
from __future__ import annotations
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

from core import Datos, analizar_recat, objetivo, fmt_ars, fmt_pct, CATEGORIAS

AZUL = colors.HexColor("#1a3a5c")
GRIS = colors.HexColor("#5a6570")
CLARO = colors.HexColor("#eef2f6")

ST_TITULO = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, textColor=AZUL, spaceAfter=2)
ST_SUB = ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=GRIS, spaceAfter=8)
ST_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, textColor=AZUL,
                       spaceBefore=10, spaceAfter=4)
ST_TXT = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13)
ST_NOTA = ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8, textColor=GRIS, leading=11)

MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _mes_lindo(key: str) -> str:
    a, m = int(key[:4]), int(key[5:7])
    return f"{MESES_ES[m]} {a}"


def _tabla(data, col_widths, header=True, align_right_from=1):
    t = Table(data, colWidths=col_widths)
    estilo = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#d6dde4")),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
    ]
    if header:
        estilo += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), CLARO),
            ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
        ]
    t.setStyle(TableStyle(estilo))
    return t


def generar_pdf(datos: Datos, recat: str, categoria_meta: str | None = None) -> bytes:
    an = analizar_recat(datos, recat)
    ob = objetivo(datos, recat, categoria_meta)
    a, m = int(recat[:4]), int(recat[5:7])

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=14 * mm,
        title=f"Recategorización Monotributo {MESES_ES[m]} {a}",
    )
    el = []

    # Encabezado
    el.append(Paragraph(f"Recategorización Monotributo — {MESES_ES[m]} {a}", ST_TITULO))
    quien = " · ".join(x for x in [datos.contribuyente, f"CUIT {datos.cuit}" if datos.cuit else ""] if x)
    fecha = date.today().strftime("%d/%m/%Y")
    el.append(Paragraph(f"{quien + ' · ' if quien else ''}Generado el {fecha}", ST_SUB))
    el.append(HRFlowable(width="100%", thickness=1, color=AZUL))

    # Resumen ejecutivo
    el.append(Paragraph("Resumen", ST_H2))
    resumen = [
        ["Facturación 12 meses", fmt_ars(an["total"])],
        ["Categoría resultante", an["categoria"] or "EXCLUIDO (supera tope K)"],
        ["Promedio mensual", fmt_ars(an["promedio_mensual"])],
        ["Aumento nominal vs. recat. anterior", fmt_pct(an["aumento_nominal"])],
        ["Inflación del semestre (compuesta)", fmt_pct(an["inflacion_6m"])],
        ["Variación real (deflactada)", fmt_pct(an["variacion_real"])],
    ]
    if an["escala_vigencia"]:
        resumen.append(["Escala aplicada (vigencia)", an["escala_vigencia"]])
    el.append(_tabla([["Concepto", "Valor"]] + resumen, [95 * mm, 79 * mm]))

    # Detalle mensual
    el.append(Paragraph("Facturación de la ventana computada (12 meses)", ST_H2))
    filas = [["Mes", "Facturado"]]
    for mes in an["meses"]:
        v = an["facturacion"][mes]
        filas.append([_mes_lindo(mes), fmt_ars(v) if v is not None else "sin datos"])
    filas.append(["TOTAL", fmt_ars(an["total"])])
    t = _tabla(filas, [95 * mm, 79 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), CLARO),
    ]))
    el.append(t)

    # Escala vigente
    if an["escala"]:
        el.append(Paragraph("Escala de topes anuales aplicada", ST_H2))
        filas = [["Cat."] + CATEGORIAS,
                 ["Tope"] + [fmt_ars(an["escala"].get(c)).replace("$ ", "") for c in CATEGORIAS]]
        t = Table(filas, colWidths=[12 * mm] + [14.7 * mm] * 11)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.4),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 0), (-1, 0), CLARO),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c6cfd8")),
        ]))
        # Resaltar categoría resultante y meta
        if an["categoria"] in CATEGORIAS:
            i = 1 + CATEGORIAS.index(an["categoria"])
            t.setStyle(TableStyle([("BACKGROUND", (i, 0), (i, 1), colors.HexColor("#d9e8d4"))]))
        el.append(t)
        el.append(Paragraph("Verde: categoría resultante según facturación de la ventana.", ST_NOTA))

    # Objetivo
    el.append(Paragraph(
        f"Objetivo para la recategorización ({_mes_lindo(ob['recat'])}) "
        f"— Categoría meta: {ob['categoria_meta']}", ST_H2))
    filas = [
        ["Ya facturado en esta ventana", fmt_ars(ob["ya_facturado"])],
        ["Tope actual de la categoría meta", fmt_ars(ob["tope_actual"])],
        ["Inflación estimada del semestre", fmt_pct(ob["inflacion_estimada_semestre"])],
        ["Tope proyectado (ajustado por inflación)", fmt_ars(ob["tope_proyectado"])],
        ["Margen disponible (tope actual)", fmt_ars(ob["margen_actual"])],
        ["Margen disponible (tope proyectado)", fmt_ars(ob["margen_proyectado"])],
        [f"Promedio mensual disponible ({len(ob['meses_restantes'])} meses restantes)",
         fmt_ars(ob["promedio_mensual_proyectado"])],
    ]
    el.append(_tabla([["Concepto", "Valor"]] + filas, [95 * mm, 79 * mm]))

    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Documento de uso interno para planificación. Los topes proyectados son estimaciones "
        "(las escalas oficiales las publica ARCA con la actualización semestral por IPC). "
        "Verificar los valores definitivos en el Portal Monotributo antes de confirmar la recategorización.",
        ST_NOTA))

    doc.build(el)
    return buf.getvalue()
