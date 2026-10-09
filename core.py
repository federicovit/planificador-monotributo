"""
core.py — Lógica de cálculo para recategorización de Monotributo (ARCA).

Replica la lógica de la hoja 'AFIP' del Excel original:
- Ventana móvil de 12 meses de facturación que cierra el mes anterior a la
  recategorización (Enero: Ene-Dic del año previo | Julio: Jul-Jun).
- Inflación semestral compuesta a partir de la inflación mensual.
- Aumento nominal y variación real (VAN deflactado) vs. el semestre anterior.
- Objetivo de facturación según categoría meta, actual y ajustado por
  inflación estimada del próximo semestre.

Sin dependencias externas (solo stdlib) para poder testear y reutilizar.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
import json
import os

CATEGORIAS = list("ABCDEFGHIJK")


# ---------------------------------------------------------------- utilidades
def mes_key(a: int, m: int) -> str:
    return f"{a}-{m:02d}"


def iter_meses(desde: str, n: int) -> list[str]:
    """n claves 'YYYY-MM' consecutivas empezando en `desde`."""
    a, m = int(desde[:4]), int(desde[5:7])
    out = []
    for _ in range(n):
        out.append(mes_key(a, m))
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return out


def ventana_12m(recat: str) -> list[str]:
    """Meses computados para la recategorización 'YYYY-01' o 'YYYY-07'.

    Enero N  -> Ene(N-1) .. Dic(N-1)
    Julio N  -> Jul(N-1) .. Jun(N)
    """
    a, m = int(recat[:4]), int(recat[5:7])
    if m == 1:
        return iter_meses(mes_key(a - 1, 1), 12)
    return iter_meses(mes_key(a - 1, 7), 12)


def semestre_previo(recat: str) -> list[str]:
    """Los 6 meses inmediatamente anteriores a la recategorización
    (los que definen la inflación del ajuste semestral)."""
    return ventana_12m(recat)[6:]


def recat_anterior(recat: str) -> str:
    a, m = int(recat[:4]), int(recat[5:7])
    return mes_key(a - 1, 7) if m == 1 else mes_key(a, 1)


def recat_siguiente(recat: str) -> str:
    a, m = int(recat[:4]), int(recat[5:7])
    return mes_key(a, 7) if m == 1 else mes_key(a + 1, 1)


def recat_vigente(hoy: date | None = None) -> str:
    """Próxima recategorización a preparar según la fecha actual.

    Se considera 'en preparación' la de Julio si estamos entre Enero y Julio,
    y la de Enero del año siguiente si estamos entre Agosto y Diciembre.
    (La recategorización se tramita del 1 al ~5 de agosto / febrero, sobre
    la ventana que cierra en junio / diciembre respectivamente.)
    """
    hoy = hoy or date.today()
    if hoy.month <= 7:
        return mes_key(hoy.year, 7)
    return mes_key(hoy.year + 1, 1)


def inflacion_compuesta(tasas: list[float]) -> float:
    """(1+i1)(1+i2)...(1+in) - 1  — equivalente a la fórmula anidada del Excel."""
    acc = 1.0
    for t in tasas:
        acc *= 1.0 + t
    return acc - 1.0


def total_mes(facturas: list[float] | None) -> float | None:
    """Suma de las facturas cargadas en el mes, o None si no hay ninguna cargada."""
    if not facturas:
        return None
    return sum(facturas)


def parse_facturas(texto: str) -> list[float]:
    """Convierte 'monto1 + monto2 + ...' en la lista de montos de cada factura.

    Lanza ValueError si alguna parte no es un número.
    """
    partes = [p.strip() for p in texto.split("+")]
    return [float(p) for p in partes if p]


def fmt_facturas(montos: list[float]) -> str:
    """Serializa una lista de montos como 'm1 + m2 + ...' para edición (inversa de parse_facturas)."""
    def _num(v: float) -> str:
        return str(int(v)) if v == int(v) else str(v)
    return " + ".join(_num(v) for v in montos)


# ------------------------------------------------------------------- modelo
@dataclass
class Datos:
    """Contenedor de datos persistidos en JSON."""
    facturacion: dict[str, list[float]] = field(default_factory=dict)  # 'YYYY-MM' -> [monto de cada factura]
    inflacion: dict[str, float] = field(default_factory=dict)     # 'YYYY-MM' -> tasa (0.02 = 2%)
    inflacion_estimada: dict[str, float] = field(default_factory=dict)  # estimaciones propias
    escalas: dict[str, dict[str, float]] = field(default_factory=dict)  # 'YYYY-MM' vigencia -> {cat: tope}
    categoria_meta: str = "G"
    contribuyente: str = ""
    cuit: str = ""

    # ---- persistencia ----
    @classmethod
    def cargar(cls, path: str) -> "Datos":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            facturacion={
                k: ([float(x) for x in v] if isinstance(v, list) else [float(v)])
                for k, v in raw.get("facturacion", {}).items()
            },
            inflacion={k: float(v) for k, v in raw.get("inflacion", {}).items()},
            inflacion_estimada={k: float(v) for k, v in raw.get("inflacion_estimada", {}).items()},
            escalas={k: {c: float(t) for c, t in v.items()} for k, v in raw.get("escalas", {}).items()},
            categoria_meta=raw.get("categoria_meta", "G"),
            contribuyente=raw.get("contribuyente", ""),
            cuit=raw.get("cuit", ""),
        )

    def guardar(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "facturacion": dict(sorted(self.facturacion.items())),
                "inflacion": dict(sorted(self.inflacion.items())),
                "inflacion_estimada": dict(sorted(self.inflacion_estimada.items())),
                "escalas": self.escalas,
                "categoria_meta": self.categoria_meta,
                "contribuyente": self.contribuyente,
                "cuit": self.cuit,
            }, f, indent=2, ensure_ascii=False)

    # ---- helpers ----
    def tasa_mes(self, mes: str) -> float | None:
        """Inflación del mes: primero la real, si no la estimada."""
        if mes in self.inflacion:
            return self.inflacion[mes]
        return self.inflacion_estimada.get(mes)

    def escala_vigente(self, recat: str) -> tuple[str, dict[str, float]] | tuple[None, None]:
        """Escala aplicable a la recategorización `recat` (la de mayor
        vigencia_desde que sea <= recat)."""
        candidatas = [v for v in self.escalas if v <= recat]
        if not candidatas:
            return None, None
        vig = max(candidatas)
        return vig, self.escalas[vig]

    def escala_estimada(self, recat: str) -> tuple[str, dict[str, float], bool] | tuple[None, None, None]:
        """Escala aplicable a `recat`, extrapolando si no hay una cargada.

        - Si hay una escala con vigencia == recat, se devuelve tal cual
          (es_estimada=False).
        - Si `recat` es anterior a la primera vigencia cargada, se deflacta
          esa primera escala semestre a semestre (con la inflación real, o
          la estimada si falta) hasta llegar a `recat`.
        - Si `recat` es posterior a la última vigencia cargada, se actualiza
          esa última escala semestre a semestre (con la inflación proyectada
          de cada tramo futuro) hasta `recat`.

        Devuelve (vigencia_base, escala, es_estimada). (None, None, None) si
        no hay ninguna escala cargada, o si falta algún dato de inflación en
        el camino y no se puede estimar.
        """
        if not self.escalas:
            return None, None, None
        if recat in self.escalas:
            return recat, self.escalas[recat], False

        vigencias = sorted(self.escalas)
        primera, ultima = vigencias[0], vigencias[-1]

        if recat < primera:
            escala = dict(self.escalas[primera])
            paso = primera
            while paso > recat:
                tasas_ok = [t for t in (self.tasa_mes(m) for m in semestre_previo(paso)) if t is not None]
                if not tasas_ok:
                    return None, None, None
                infl = inflacion_compuesta(tasas_ok)
                escala = {cat: v / (1.0 + infl) for cat, v in escala.items()}
                paso = recat_anterior(paso)
            return primera, escala, True

        if recat > ultima:
            escala = dict(self.escalas[ultima])
            paso = ultima
            while paso < recat:
                paso = recat_siguiente(paso)
                tasas_ok = [t for t in (self.tasa_mes(m) for m in semestre_previo(paso)) if t is not None]
                if not tasas_ok:
                    return None, None, None
                infl = inflacion_compuesta(tasas_ok)
                escala = {cat: v * (1.0 + infl) for cat, v in escala.items()}
            return ultima, escala, True

        # 'recat' cae entre dos vigencias conocidas (no debería pasar con
        # recats semestrales estándar); se usa la vigente normal.
        vig, esc = self.escala_vigente(recat)
        return vig, esc, False


# ----------------------------------------------------------------- cálculo
def categoria_para(total_anual: float, escala: dict[str, float]) -> str | None:
    """Menor categoría cuyo tope cubre el total anual. None => excluido."""
    for cat in CATEGORIAS:
        if cat in escala and total_anual <= escala[cat]:
            return cat
    return None


def analizar_recat(datos: Datos, recat: str) -> dict:
    """Análisis completo de una recategorización (réplica del bloque del Excel)."""
    meses = ventana_12m(recat)
    fact = {m: total_mes(datos.facturacion.get(m)) for m in meses}
    total = sum(v for v in fact.values() if v is not None)
    n_cargados = sum(1 for v in fact.values() if v is not None)

    # Inflación semestral compuesta (6 meses previos a la recat)
    sem = semestre_previo(recat)
    tasas = [(m, datos.tasa_mes(m)) for m in sem]
    tasas_ok = [t for _, t in tasas if t is not None]
    infl_6m = inflacion_compuesta(tasas_ok) if tasas_ok else None
    meses_sin_inflacion = [m for m, t in tasas if t is None]

    # Comparación vs recategorización anterior
    prev = recat_anterior(recat)
    meses_prev = ventana_12m(prev)
    total_prev = sum(total_mes(datos.facturacion.get(m)) or 0.0 for m in meses_prev)
    aumento_nominal = (total / total_prev - 1.0) if total_prev else None
    # VAN: total actual deflactado a moneda del semestre anterior (como C20 = C15/(1+C17))
    van = total / (1.0 + infl_6m) if infl_6m is not None else None
    variacion_real = (van / total_prev - 1.0) if (van is not None and total_prev) else None

    # Categoría según escala vigente (o extrapolada si no hay una cargada)
    vig, escala, escala_estimada = datos.escala_estimada(recat)
    cat = categoria_para(total, escala) if escala else None

    return {
        "recat": recat,
        "meses": meses,
        "facturacion": fact,
        "total": total,
        "meses_cargados": n_cargados,
        "promedio_mensual": total / n_cargados if n_cargados else 0.0,
        "inflacion_6m": infl_6m,
        "meses_sin_inflacion": meses_sin_inflacion,
        "total_anterior": total_prev,
        "aumento_nominal": aumento_nominal,
        "van_deflactado": van,
        "variacion_real": variacion_real,
        "escala_vigencia": vig,
        "escala": escala,
        "escala_estimada": escala_estimada,
        "categoria": cat,
    }


def serie_historica(datos: Datos, hasta_recat: str) -> list[dict]:
    """Análisis de cada recategorización con datos, desde la primera disponible
    hasta `hasta_recat` inclusive, para ver cómo varió la facturación.

    Agrega a cada resultado de `analizar_recat`:
    - factor_a_hoy: factor de inflación compuesta para llevar el total de esa
      recategorización a pesos de `hasta_recat` (encadenando la inflación
      semestral de cada recategorización posterior). None si falta algún
      dato de inflación en el camino.
    - total_actualizado: total * factor_a_hoy, comparable entre sí porque
      queda expresado en la misma moneda (la de `hasta_recat`).
    """
    if not datos.facturacion:
        return []
    primero = min(datos.facturacion)
    a0 = int(primero[:4])
    recats = []
    for a in range(a0, int(hasta_recat[:4]) + 1):
        for m in (1, 7):
            r = mes_key(a, m)
            if mes_key(a0, 7) <= r <= hasta_recat:
                recats.append(r)
    resultados = [analizar_recat(datos, r) for r in recats]

    factor = 1.0
    for res in reversed(resultados):
        res["factor_a_hoy"] = factor
        infl = res["inflacion_6m"]
        factor = factor * (1.0 + infl) if (factor is not None and infl is not None) else None

    for res in resultados:
        f = res["factor_a_hoy"]
        res["total_actualizado"] = res["total"] * f if f is not None else None

    return resultados


def objetivo(datos: Datos, recat: str, categoria_meta: str | None = None,
             hoy: date | None = None) -> dict:
    """Objetivo de facturación para la recategorización `recat`.

    Trabaja sobre la ventana de 12 meses que computa para `recat` (la misma
    que analiza `analizar_recat`), no sobre la de la recategorización
    siguiente: lo que interesa es cuánto más se puede facturar sin pasarse
    del tope de la categoría meta en *esta* recategorización.

    - ya_facturado: todo lo que ya va a computar para `recat`. Los meses de
      la ventana ya transcurridos (hasta el mes corriente inclusive) valen lo
      facturado, o $0 si no se cargó nada.
    - meses_restantes: los meses de la ventana que todavía no ocurrieron y no
      tienen facturación cargada. Son los únicos sobre los que se puede
      repartir el margen disponible.
    - tope_actual: tope de la categoría meta con la última escala publicada
      que le sea aplicable.
    - tope_proyectado: el tope que va a regir en `recat`. Si ARCA todavía no
      publicó esa escala, se proyecta la última conocida por la inflación de
      los semestres que faltan (las escalas se actualizan por IPC).
    """
    cat = categoria_meta or datos.categoria_meta
    hoy = hoy or date.today()
    mes_actual = mes_key(hoy.year, hoy.month)

    meses_ventana = ventana_12m(recat)
    facturado = {m: total_mes(datos.facturacion.get(m)) for m in meses_ventana}
    ya_facturado = sum(v for v in facturado.values() if v is not None)
    meses_restantes = [m for m, v in facturado.items() if v is None and m > mes_actual]

    vig, escala = datos.escala_vigente(recat)
    tope_actual = escala.get(cat) if escala else None

    # Tope vigente en `recat`: el oficial si ya se publicó, o el proyectado
    # por inflación desde la última escala conocida.
    _, escala_proy, tope_es_estimado = datos.escala_estimada(recat)
    tope_proyectado = escala_proy.get(cat) if escala_proy else None

    # Inflación del semestre que define la actualización de escala de `recat`
    tasas_ok = [t for t in (datos.tasa_mes(m) for m in semestre_previo(recat)) if t is not None]
    infl_est = inflacion_compuesta(tasas_ok) if tasas_ok else None

    margen_actual = (tope_actual - ya_facturado) if tope_actual is not None else None
    margen_proyectado = (tope_proyectado - ya_facturado) if tope_proyectado is not None else None
    n_rest = len(meses_restantes)

    return {
        "recat": recat,
        "categoria_meta": cat,
        "meses_ventana": meses_ventana,
        "ya_facturado": ya_facturado,
        "meses_restantes": meses_restantes,
        "tope_actual": tope_actual,
        "inflacion_estimada_semestre": infl_est,
        "tope_proyectado": tope_proyectado,
        "tope_es_estimado": tope_es_estimado,
        "margen_actual": margen_actual,
        "margen_proyectado": margen_proyectado,
        "promedio_mensual_actual": margen_actual / n_rest if (margen_actual is not None and n_rest) else None,
        "promedio_mensual_proyectado": margen_proyectado / n_rest if (margen_proyectado is not None and n_rest) else None,
    }


def fmt_ars(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{v:,.0f}".replace(",", ".")
    return f"$ {s}"


def fmt_pct(v: float | None, dec: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{dec}f}%".replace(".", ",")
