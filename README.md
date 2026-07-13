# Monotributo FV — Planificador de recategorización

Aplicación Streamlit que automatiza el proceso de tu Excel `AFIP-Para_Claude.xlsx`
(hoja **AFIP**): ventanas móviles de 12 meses por recategorización semestral,
ajuste por inflación compuesta, comparación nominal/real contra el semestre
anterior, objetivo de facturación por categoría meta, actualización online de
datos y reporte PDF.

## Instalación y uso

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre en el navegador (por defecto http://localhost:8501).

## Estructura

| Archivo | Función |
|---|---|
| `app.py` | Interfaz Streamlit (4 pestañas) |
| `core.py` | Lógica de cálculo pura (sin dependencias, testeable) |
| `actualizador.py` | Descarga de inflación (API ArgentinaDatos) y escalas (scraping ARCA) |
| `reporte.py` | Generación del PDF con reportlab |
| `datos.json` | Base de datos local (facturación, inflación, escalas, configuración) |
| `migrar_excel.py` | Script que generó el seed inicial desde tu Excel |

## Lógica de cálculo (equivalencia con el Excel)

- **Ventana computada**: 12 meses que cierran el mes anterior a la
  recategorización. Julio N → Jul(N-1)–Jun(N); Enero N → Ene(N-1)–Dic(N-1).
- **Inflación semestral** (`C17`, `I17`, `O17`…): producto compuesto
  `(1+i₁)(1+i₂)···(1+i₆) − 1` de los 6 meses previos a la recategorización.
  Tu fórmula anidada del Excel es algebraicamente equivalente.
- **Aumento nominal** (`C16`…): total anual / total del semestre anterior − 1.
- **VAN deflactado** (`C20`…): total / (1 + inflación semestral), y
  **variación real** (`C21`…) comparándolo con el total anterior.
- **Objetivo** (`E15`/`E20`…): tope de la categoría meta con la escala vigente,
  y tope proyectado multiplicado por la inflación estimada del semestre en
  curso (las escalas de ARCA se actualizan por IPC). El margen disponible
  descuenta lo ya facturado en la nueva ventana y lo reparte entre los meses
  restantes.

Para cada mes la app usa la **inflación real** si está cargada; si no, cae en
la **estimada** (editable en la pestaña «Datos y escalas»).

## Actualización online

- **Inflación**: botón «Traer inflación real» → API pública de ArgentinaDatos
  (`https://api.argentinadatos.com/v1/finanzas/indices/inflacion`), datos IPC
  INDEC mensuales, sin API key. Pisa/agrega los meses en `inflacion` (real).
- **Escalas**: botón «Traer escalas desde ARCA» → scrapea
  `https://www.afip.gob.ar/monotributo/categorias.asp` y guarda la escala con
  vigencia del semestre actual. Si ARCA cambia el formato de la página el
  scraping puede fallar: la app avisa y podés cargar los 11 topes a mano en la
  misma pestaña (o crear una nueva vigencia copiando la anterior y editándola).

Las escalas se guardan **por vigencia** (`2026-01`, `2026-07`, …), y cada
recategorización usa la escala de mayor vigencia que le sea anterior o igual,
así el histórico no se recalcula con topes nuevos.

## Datos precargados

- Facturación mensual Ene 2023 → Jul 2026, migrada de tu Excel (el total
  Jul 25–Jun 26 da $52.788.000, igual que tu celda I15).
- Inflación real hasta Jun 2025 e inflación estimada Jul 2025 → Dic 2026
  (los valores que tenías en las columnas G/M; Jul–Dic 2026 quedó al 2,0 %
  mensual como estimación editable — tu Excel tenía ese bloque vacío).
- Escala vigente desde Enero 2026 (ARCA): A $10.277.988 … G $46.211.109 …
  K $108.357.084.

⚠️ **Dato relevante**: con la escala de Enero 2026, tu facturación
Jul 25–Jun 26 ($52,79 M) supera el tope G ($46,21 M) y cae en **categoría H**.
La actualización de Julio 2026 (~+14,3 % estimado) llevaría el tope G a
~$52,8 M, es decir que quedás justo en el límite. Apenas ARCA publique la
escala oficial, usá el botón de actualización (o cargala a mano con vigencia
`2026-07`) antes de confirmar la recategorización, que inicia el 15/07/2026.

## Reporte PDF

Pestaña «Reporte PDF» → genera un A4 con: resumen (total, categoría, aumento
nominal, inflación, variación real), detalle mensual de la ventana, escala
aplicada con la categoría resaltada, y objetivo hacia la próxima
recategorización. Descarga directa desde el navegador.

## Notas

- `datos.json` es la única fuente de datos: hacé backup de ese archivo.
- Documento de planificación interna; verificar siempre los valores oficiales
  en el Portal Monotributo antes de confirmar el trámite.
