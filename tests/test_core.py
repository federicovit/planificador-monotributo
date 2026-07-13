"""Tests para la lógica pura de core.py (sin dependencias externas)."""
from datetime import date

import pytest

from core import (
    Datos,
    categoria_para,
    inflacion_compuesta,
    iter_meses,
    mes_key,
    recat_anterior,
    recat_siguiente,
    recat_vigente,
    semestre_previo,
    ventana_12m,
)


def test_mes_key_padea_el_mes():
    assert mes_key(2026, 1) == "2026-01"
    assert mes_key(2026, 12) == "2026-12"


def test_iter_meses_dentro_del_mismo_anio():
    assert iter_meses("2026-01", 3) == ["2026-01", "2026-02", "2026-03"]


def test_iter_meses_cruza_fin_de_anio():
    assert iter_meses("2025-11", 3) == ["2025-11", "2025-12", "2026-01"]


def test_ventana_12m_julio_es_jul_prev_a_jun_actual():
    assert ventana_12m("2026-07") == iter_meses("2025-07", 12)
    assert ventana_12m("2026-07")[0] == "2025-07"
    assert ventana_12m("2026-07")[-1] == "2026-06"


def test_ventana_12m_enero_es_ene_a_dic_del_anio_previo():
    assert ventana_12m("2026-01") == iter_meses("2025-01", 12)
    assert ventana_12m("2026-01")[0] == "2025-01"
    assert ventana_12m("2026-01")[-1] == "2025-12"


def test_semestre_previo_son_los_ultimos_6_meses_de_la_ventana():
    assert semestre_previo("2026-07") == ventana_12m("2026-07")[6:]
    assert semestre_previo("2026-07") == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def test_recat_anterior_y_siguiente_son_inversas():
    assert recat_anterior("2026-07") == "2026-01"
    assert recat_anterior("2026-01") == "2025-07"
    assert recat_siguiente("2026-01") == "2026-07"
    assert recat_siguiente("2026-07") == "2027-01"


@pytest.mark.parametrize(
    "hoy, esperado",
    [
        (date(2026, 1, 15), "2026-07"),
        (date(2026, 7, 31), "2026-07"),
        (date(2026, 8, 1), "2027-01"),
        (date(2026, 12, 31), "2027-01"),
    ],
)
def test_recat_vigente(hoy, esperado):
    assert recat_vigente(hoy) == esperado


def test_inflacion_compuesta_es_producto_no_suma():
    assert inflacion_compuesta([0.1, 0.1]) == pytest.approx(0.21)


def test_inflacion_compuesta_vacia_es_cero():
    assert inflacion_compuesta([]) == 0.0


def test_categoria_para_elige_el_menor_tope_que_cubre_el_total():
    escala = {"A": 100.0, "B": 200.0, "C": 300.0}
    assert categoria_para(50.0, escala) == "A"
    assert categoria_para(100.0, escala) == "A"
    assert categoria_para(150.0, escala) == "B"
    assert categoria_para(300.0, escala) == "C"


def test_categoria_para_excluido_si_supera_el_tope_mas_alto():
    escala = {"A": 100.0, "B": 200.0}
    assert categoria_para(500.0, escala) is None


def test_datos_guardar_y_cargar_roundtrip(tmp_path):
    path = tmp_path / "datos.json"
    original = Datos(
        facturacion={"2026-01": 1000.0},
        inflacion={"2026-01": 0.02},
        inflacion_estimada={"2026-02": 0.015},
        escalas={"2026-01": {"A": 100.0, "B": 200.0}},
        categoria_meta="B",
        contribuyente="Test",
        cuit="20-12345678-9",
    )
    original.guardar(str(path))

    cargado = Datos.cargar(str(path))

    assert cargado.facturacion == original.facturacion
    assert cargado.inflacion == original.inflacion
    assert cargado.inflacion_estimada == original.inflacion_estimada
    assert cargado.escalas == original.escalas
    assert cargado.categoria_meta == original.categoria_meta
    assert cargado.contribuyente == original.contribuyente
    assert cargado.cuit == original.cuit


def test_datos_cargar_sin_archivo_devuelve_valores_por_defecto(tmp_path):
    path = tmp_path / "no_existe.json"
    datos = Datos.cargar(str(path))
    assert datos.facturacion == {}
    assert datos.categoria_meta == "G"
