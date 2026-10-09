# Monotributo — Planificador de recategorización

Aplicación Streamlit para planificar las recategorizaciones semestrales del
Monotributo (ARCA, Argentina): ventanas móviles de 12 meses, ajuste por
inflación compuesta, comparación nominal/real contra el semestre anterior,
objetivo de facturación por categoría meta, actualización online de datos y
reporte PDF.

Corre **local, en tu máquina**. Tus datos nunca salen de tu computadora: se
guardan en un `datos.json` propio que no forma parte del repositorio.

## Instalación

Necesitás Python 3.10 o superior.

```bash
git clone https://github.com/federicovit/monotributo.git
cd monotributo
pip install -r requirements.txt
```

## Uso

```bash
streamlit run app.py
```

Se abre en el navegador (por defecto http://localhost:8501). En Windows también
podés hacer doble clic en `iniciar_app.bat`.

La primera vez la app arranca desde `datos.ejemplo.json` (escalas de ARCA e
inflación del INDEC, **sin facturación**). Cuando cargás tus datos y apretás
«Guardar», se crea tu propio `datos.json`, que queda fuera de git.

## Pestañas

- **Dashboard** — análisis de la recategorización seleccionada: total de la
  ventana de 12 meses, categoría resultante, aumento nominal, variación real,
  objetivo hacia la categoría meta y evolución histórica entre
  recategorizaciones (facturación real vs. actualizada por inflación).
- **Facturación** — carga mensual. Podés escribir el monto de cada factura
  separado por `+` (ej.: `500000 + 12000000 + 850000`) y la app te muestra la
  cantidad de facturas y el total de cada mes, para saber si ya cargaste todas.
- **Datos y escalas** — inflación real/estimada y escalas de topes por
  vigencia, con botones de actualización online.
- **Reporte PDF** — resumen imprimible A4 para descargar.

## Estructura

| Archivo | Función |
|---|---|
| `app.py` | Interfaz Streamlit (4 pestañas) |
| `core.py` | Lógica de cálculo pura (solo stdlib, testeable) |
| `actualizador.py` | Descarga de inflación (API ArgentinaDatos) y escalas (scraping ARCA) |
| `reporte.py` | Generación del PDF con reportlab |
| `datos.ejemplo.json` | Datos públicos de arranque (escalas e inflación) |
| `datos.json` | **Tus** datos. Se crea solo y no se versiona |
| `migrar_excel.py` | Script opcional para migrar facturación desde un Excel |
| `tests/test_core.py` | Tests de la lógica de cálculo |

## Lógica de cálculo

- **Ventana computada**: 12 meses que cierran el mes anterior a la
  recategorización. Julio N → Jul(N-1)–Jun(N); Enero N → Ene(N-1)–Dic(N-1).
- **Inflación semestral**: producto compuesto `(1+i₁)(1+i₂)···(1+i₆) − 1` de
  los 6 meses previos a la recategorización.
- **Aumento nominal**: total anual / total del semestre anterior − 1.
- **VAN deflactado**: total / (1 + inflación semestral), y **variación real**
  comparándolo con el total anterior.
- **Evolución histórica**: cada recategorización pasada se expresa también en
  pesos de la recategorización analizada, encadenando la inflación semestral
  de los períodos intermedios, para comparar crecimiento real contra nominal.
- **Objetivo**: trabaja sobre la ventana de la recategorización analizada.
  Suma lo que ya computa (los meses transcurridos, contando $0 los que no
  tienen facturación cargada) y reparte el margen hasta el tope de la
  categoría meta entre los meses de la ventana que todavía no ocurrieron.

Para cada mes la app usa la **inflación real** si está cargada; si no, cae en
la **estimada** (editable en la pestaña «Datos y escalas»).

## Escalas de categorías

Se guardan **por vigencia** (`2025-07`, `2026-01`, …) y cada recategorización
usa la escala que le corresponde. Las escalas de ARCA cambian el mes en que se
tramita la recategorización (agosto y febrero), no en enero/julio.

Si para una recategorización no hay escala cargada, la app la **estima**: hacia
atrás deflactando la escala conocida más antigua con la inflación real, y hacia
adelante actualizando la última conocida con la inflación proyectada (es lo que
pasa con la recategorización en curso hasta que ARCA publica los topes nuevos).
Las categorías estimadas aparecen marcadas como `(est.)`.

## Actualización online

- **Inflación**: botón «Traer inflación real» → API pública de ArgentinaDatos
  (`https://api.argentinadatos.com/v1/finanzas/indices/inflacion`), datos IPC
  INDEC mensuales, sin API key. Trae la serie histórica completa; si no la
  querés entera, borrá los meses viejos en la misma pestaña.
- **Escalas**: botón «Traer escalas desde ARCA» → scrapea
  `https://www.afip.gob.ar/monotributo/categorias.asp` y guarda la escala con
  vigencia del semestre actual. Ojo: trae lo que ARCA muestre **hoy**, así que
  si todavía no publicaron la escala nueva vas a guardar un duplicado de la
  anterior. Si el scraping falla, podés cargar los 11 topes a mano o crear una
  vigencia nueva copiando la anterior.

## Tests

```bash
pip install pytest
python -m pytest
```

## Notas

- `datos.json` es la única fuente de datos: hacé backup de ese archivo.
- La app está pensada para **un usuario por instalación**. No la publiques en
  un servidor compartido tal cual: el estado es global al proceso, así que
  todos los visitantes compartirían los mismos datos.
- Es una herramienta de planificación: verificá siempre los valores oficiales
  en el Portal Monotributo antes de confirmar el trámite.
