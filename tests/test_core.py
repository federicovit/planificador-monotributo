"""Tests para la lógica pura de core.py (sin dependencias externas)."""
from datetime import date

import pytest

from core import (
    Datos,
    categoria_para,
    fmt_facturas,
    inflacion_compuesta,
    iter_meses,
    mes_key,
    objetivo,
    parse_facturas,
    recat_anterior,
    recat_siguiente,
    recat_vigente,
    semestre_previo,
    serie_historica,
    total_mes,
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


def test_total_mes_suma_las_facturas_del_mes():
    assert total_mes([500000.0, 12000000.0, 850000.0]) == pytest.approx(13350000.0)


def test_total_mes_sin_facturas_es_none():
    assert total_mes([]) is None
    assert total_mes(None) is None


def test_parse_facturas_separa_por_mas_y_descarta_partes_vacias():
    assert parse_facturas("500000 + 12000000 + 850000") == [500000.0, 12000000.0, 850000.0]
    assert parse_facturas(" 100 + ") == [100.0]
    assert parse_facturas("") == []


def test_parse_facturas_valor_invalido_lanza_value_error():
    with pytest.raises(ValueError):
        parse_facturas("500000 + abc")


def test_fmt_facturas_es_inversa_de_parse_facturas():
    montos = [500000.0, 12000000.5, 850000.0]
    assert parse_facturas(fmt_facturas(montos)) == montos


def test_serie_historica_actualiza_totales_a_pesos_de_la_ultima_recat():
    facturacion = {mes: [100.0] for mes in iter_meses("2024-07", 18)}  # 2024-07..2025-12
    inflacion = {mes_key(2025, m): 0.01 for m in range(7, 13)}  # 2025-07..2025-12
    datos = Datos(facturacion=facturacion, inflacion=inflacion)

    hist = serie_historica(datos, "2026-01")

    assert [r["recat"] for r in hist] == ["2024-07", "2025-01", "2025-07", "2026-01"]

    ultimo = hist[-1]
    assert ultimo["total"] == pytest.approx(1200.0)
    assert ultimo["factor_a_hoy"] == pytest.approx(1.0)
    assert ultimo["total_actualizado"] == pytest.approx(1200.0)

    anterior = hist[-2]
    assert anterior["recat"] == "2025-07"
    assert anterior["total"] == pytest.approx(1200.0)
    factor_esperado = 1.0 + inflacion_compuesta([0.01] * 6)
    assert anterior["factor_a_hoy"] == pytest.approx(factor_esperado)
    assert anterior["total_actualizado"] == pytest.approx(1200.0 * factor_esperado)


def test_serie_historica_sin_facturacion_es_vacia():
    assert serie_historica(Datos(), "2026-01") == []


def _datos_objetivo():
    """Ene..Jul 2026 facturados a $1000; la ventana de la recat de Ene 2027 es Ene-Dic 2026."""
    return Datos(
        facturacion={mes_key(2026, m): [1000.0] for m in range(1, 8)},
        escalas={"2026-01": {"G": 100000.0}},
        categoria_meta="G",
    )


def test_objetivo_usa_la_ventana_de_la_recat_analizada_no_la_siguiente():
    ob = objetivo(_datos_objetivo(), "2027-01", hoy=date(2026, 9, 1))

    assert ob["recat"] == "2027-01"
    assert ob["meses_ventana"] == iter_meses("2026-01", 12)


def test_objetivo_no_cuenta_como_disponibles_los_meses_ya_transcurridos():
    # Agosto y septiembre 2026 ya pasaron sin facturación cargada: computan $0
    # para la recategorización, pero no son meses sobre los que todavía se pueda facturar.
    ob = objetivo(_datos_objetivo(), "2027-01", hoy=date(2026, 9, 1))

    assert ob["ya_facturado"] == pytest.approx(7000.0)
    assert ob["meses_restantes"] == ["2026-10", "2026-11", "2026-12"]


def test_objetivo_reparte_el_margen_solo_entre_los_meses_abiertos():
    ob = objetivo(_datos_objetivo(), "2027-01", hoy=date(2026, 9, 1))

    assert ob["margen_actual"] == pytest.approx(93000.0)
    assert ob["promedio_mensual_actual"] == pytest.approx(93000.0 / 3)


def test_objetivo_excluye_el_mes_corriente_de_los_meses_restantes():
    ob = objetivo(_datos_objetivo(), "2027-01", hoy=date(2026, 10, 15))

    assert ob["meses_restantes"] == ["2026-11", "2026-12"]


def test_objetivo_de_una_ventana_ya_cerrada_no_tiene_meses_restantes():
    ob = objetivo(_datos_objetivo(), "2026-07", hoy=date(2026, 9, 1))

    assert ob["meses_ventana"] == iter_meses("2025-07", 12)
    assert ob["meses_restantes"] == []
    assert ob["promedio_mensual_actual"] is None


def test_objetivo_de_una_ventana_futura_tiene_los_12_meses_abiertos():
    ob = objetivo(_datos_objetivo(), "2028-01", hoy=date(2026, 9, 1))

    assert ob["meses_ventana"] == iter_meses("2027-01", 12)
    assert ob["ya_facturado"] == pytest.approx(0.0)
    assert len(ob["meses_restantes"]) == 12


def test_objetivo_usa_el_tope_oficial_si_la_escala_de_la_recat_ya_se_publico():
    datos = _datos_objetivo()
    datos.escalas["2027-01"] = {"G": 150000.0}

    ob = objetivo(datos, "2027-01", hoy=date(2026, 9, 1))

    assert ob["tope_es_estimado"] is False
    assert ob["tope_proyectado"] == pytest.approx(150000.0)


def test_objetivo_proyecta_el_tope_si_la_escala_de_la_recat_no_se_publico():
    datos = _datos_objetivo()
    # La única escala es la de 2026-01, así que hay que encadenar dos semestres
    # para llegar a 2027-01: Ene-Jun 2026 y Jul-Dic 2026.
    datos.inflacion_estimada = {mes_key(2026, m): 0.05 for m in range(1, 13)}

    ob = objetivo(datos, "2027-01", hoy=date(2026, 9, 1))

    infl = inflacion_compuesta([0.05] * 6)
    assert ob["tope_es_estimado"] is True
    assert ob["inflacion_estimada_semestre"] == pytest.approx(infl)
    assert ob["tope_proyectado"] == pytest.approx(100000.0 * (1.0 + infl) ** 2)


def test_escala_estimada_devuelve_la_exacta_si_esta_cargada():
    datos = Datos(escalas={"2026-01": {"A": 100.0}})
    assert datos.escala_estimada("2026-01") == ("2026-01", {"A": 100.0}, False)


def test_escala_estimada_deflacta_hacia_atras_con_inflacion_real():
    datos = Datos(
        escalas={"2026-01": {"A": 100.0}},
        inflacion={mes_key(2025, m): 0.10 for m in range(7, 13)},  # 2025-07..2025-12
    )
    vig, escala, estimada = datos.escala_estimada("2025-07")
    infl_esperada = inflacion_compuesta([0.10] * 6)
    assert vig == "2026-01"
    assert estimada is True
    assert escala["A"] == pytest.approx(100.0 / (1.0 + infl_esperada))


def test_escala_estimada_actualiza_hacia_adelante_con_inflacion_proyectada():
    datos = Datos(
        escalas={"2026-01": {"A": 100.0}},
        inflacion_estimada={mes_key(2026, m): 0.05 for m in range(1, 7)},  # 2026-01..2026-06
    )
    vig, escala, estimada = datos.escala_estimada("2026-07")
    infl_esperada = inflacion_compuesta([0.05] * 6)
    assert vig == "2026-01"
    assert estimada is True
    assert escala["A"] == pytest.approx(100.0 * (1.0 + infl_esperada))


def test_escala_estimada_sin_inflacion_disponible_no_puede_estimar():
    datos = Datos(escalas={"2026-01": {"A": 100.0}})
    assert datos.escala_estimada("2025-07") == (None, None, None)


def test_escala_estimada_sin_escalas_cargadas():
    assert Datos().escala_estimada("2026-01") == (None, None, None)


def test_datos_cargar_migra_formato_antiguo_de_un_solo_monto_por_mes(tmp_path):
    path = tmp_path / "datos.json"
    path.write_text('{"facturacion": {"2026-01": 1000.0}}', encoding="utf-8")

    datos = Datos.cargar(str(path))

    assert datos.facturacion == {"2026-01": [1000.0]}


def test_datos_guardar_y_cargar_roundtrip(tmp_path):
    path = tmp_path / "datos.json"
    original = Datos(
        facturacion={"2026-01": [500.0, 12000.0, 850.0]},
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
