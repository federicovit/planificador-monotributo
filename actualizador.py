"""
actualizador.py — Descarga de datos actualizados desde fuentes públicas.

- Inflación mensual (IPC INDEC) vía API de ArgentinaDatos (gratuita, sin key):
  https://api.argentinadatos.com/v1/finanzas/indices/inflacion
- Escalas de Monotributo: scraping de la página oficial de ARCA
  https://www.afip.gob.ar/monotributo/categorias.asp
  Si el formato de la página cambia y el scraping falla, la app permite
  cargar/editar las escalas a mano.

Requiere: requests (y conexión a internet).
"""
from __future__ import annotations
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (monotributo-app; uso personal)"}
API_INFLACION = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
URL_ESCALAS = "https://www.afip.gob.ar/monotributo/categorias.asp"

CATEGORIAS = list("ABCDEFGHIJK")


def traer_inflacion(timeout: int = 20) -> dict[str, float]:
    """Devuelve {'YYYY-MM': tasa} con la inflación mensual oficial (INDEC).

    La API devuelve [{"fecha": "2025-06-01", "valor": 1.6}, ...] con valor en %.
    """
    r = requests.get(API_INFLACION, headers=UA, timeout=timeout)
    r.raise_for_status()
    out: dict[str, float] = {}
    for item in r.json():
        fecha = str(item.get("fecha", ""))[:7]          # 'YYYY-MM'
        valor = item.get("valor")
        if re.fullmatch(r"\d{4}-\d{2}", fecha) and valor is not None:
            out[fecha] = float(valor) / 100.0
    if not out:
        raise ValueError("La API de inflación no devolvió datos.")
    return out


def _parse_monto(txt: str) -> float:
    """'$ 46.211.109,37' -> 46211109.37"""
    limpio = re.sub(r"[^\d,\.]", "", txt)
    limpio = limpio.replace(".", "").replace(",", ".")
    return float(limpio)


def traer_escalas(timeout: int = 25) -> dict[str, float]:
    """Scrapea los topes de ingresos brutos anuales por categoría desde ARCA.

    Devuelve {'A': tope, ..., 'K': tope}. Lanza excepción si no puede
    identificar las 11 categorías (para que la app avise y ofrezca carga manual).
    """
    r = requests.get(URL_ESCALAS, headers=UA, timeout=timeout, verify=True)
    r.raise_for_status()
    html = r.text

    escala: dict[str, float] = {}
    # Estrategia: por cada categoría, buscar 'Categoría X' (o celda '>X<')
    # y tomar el primer monto grande que aparezca a continuación.
    for cat in CATEGORIAS:
        patrones = [
            rf"Categor[íi]a\s*{cat}\b(.{{0,600}}?)\$\s*([\d\.\,]+)",
            rf">\s*{cat}\s*<(.{{0,600}}?)\$\s*([\d\.\,]+)",
        ]
        for pat in patrones:
            m = re.search(pat, html, flags=re.S | re.I)
            if m:
                try:
                    monto = _parse_monto("$" + m.group(2))
                    if monto > 1_000_000:      # descarta cuotas mensuales
                        escala[cat] = monto
                        break
                except ValueError:
                    continue

    if len(escala) < 11:
        faltan = [c for c in CATEGORIAS if c not in escala]
        raise ValueError(
            f"No pude leer todas las categorías desde ARCA (faltan: {', '.join(faltan)}). "
            "Cargalas manualmente en la pestaña Escalas."
        )
    # Sanidad: deben ser estrictamente crecientes
    topes = [escala[c] for c in CATEGORIAS]
    if any(b <= a for a, b in zip(topes, topes[1:])):
        raise ValueError("Los topes leídos no son crecientes; revisá la página de ARCA.")
    return escala
