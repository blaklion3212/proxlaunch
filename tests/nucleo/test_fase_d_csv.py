"""D6.3, D0.5 y D2.7.3 (0.9.0): las dos columnas nuevas del CSV (``mapeo_pci``, ``mapeo_usb``).

CA-D6.3.1–9, CA-D0.5.1–2, CA-D2.7.3, CA-D3.7.3–4, CA-D0.3.3, CL-D17. Una celda con ids (separados
por «;») manda sobre el formulario; vacía, la fila hereda los mapeos del formulario (cada id con las
opciones del formulario). Lo explícito que no existe en ARM64 es un error de la fila y la columna
(V-D09); lo heredado se adapta (V-D08).
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
from collections.abc import Sequence

import pytest

from proxlaunch.nucleo.archivos.constantes import MAX_COLUMNAS_CSV
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.csv_importacion.columnas import COLUMNAS, resolver_columnas
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, ResultadoImportacion
from proxlaunch.nucleo.csv_importacion.plantilla import ENCABEZADO_PLANTILLA, escribir_plantilla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, PatronNombres
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.modelos.vm import Disco
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_a import plan_de
from .apoyo_fase_d import ARM, X86, banco_d, hw, info_hw, inv_arq, mapeo, pci, permisos_mapeo, usb
from .apoyo_lote import mapeo_api
from .apoyo_mvp3 import csv_bytes, definicion_filas, perfil_base, perfiles_fabrica, tabla_csv


def importar(lineas: Sequence[str], *, inv=None, hardware_base=None) -> ResultadoImportacion:
    return interpretar(
        tabla_csv(lineas),
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=inv,
        nodo_referencia="pve1",
        hardware_base=hardware_base,
    )


def fila(r: ResultadoImportacion, n: int):
    return next(f for f in r.filas if f.numero == n)


def reglas(f) -> list[tuple[str | None, str]]:
    return [(p.columna, p.regla) for p in f.problemas]


# --- CA-D6.3.5 y CA-D6.3.3: las columnas ----------------------------------------------------------


def test_ca_d6_3_5_las_columnas_canonicas_son_61_y_el_maximo_sigue_en_70():
    assert len(COLUMNAS) == 61 and MAX_COLUMNAS_CSV == 70
    por_nombre = {c.canonica: c for c in COLUMNAS}
    assert por_nombre["mapeo_pci"].alias == ("pci_mapping",) and por_nombre["mapeo_pci"].avanzada
    assert por_nombre["mapeo_usb"].alias == ("usb_mapping",) and por_nombre["mapeo_usb"].avanzada


def test_ca_d6_3_5_un_csv_con_las_61_columnas_canonicas_se_acepta():
    encabezado = [c.canonica for c in COLUMNAS]
    mapa, _ = resolver_columnas(encabezado)
    assert len(mapa.posiciones) == 61
    leer_tabla(csv_bytes([";".join(encabezado), ";".join(["x"] * 61)]))  # y se lee la tabla


def test_ca_d6_3_5_un_csv_con_71_columnas_se_rechaza_por_exceso_y_con_70_se_lee():
    """El código real del exceso de columnas es E-M06 (``tipo=columnas``), como en 0.8.0."""
    encabezado = ["nombre", *[f"extra{i}" for i in range(70)]]
    leer_tabla(csv_bytes([";".join(encabezado[:70]), ";".join(["x"] * 70)]))
    with pytest.raises(ErrorProxLaunch) as e:
        leer_tabla(csv_bytes([";".join(encabezado), ";".join(["x"] * 71)]))
    assert e.value.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert e.value.params["tipo"] == "columnas" and e.value.params["max"] == "70"


@pytest.mark.parametrize(("a", "b"), [("mapeo_pci", "pci_mapping"), ("mapeo_usb", "usb_mapping")])
def test_ca_d6_3_3_dos_columnas_alias_de_la_misma_son_csv_columnas_duplicada(a, b):
    with pytest.raises(ErrorProxLaunch) as e:
        importar([f"nombre;{a};{b}", "a-01;g;h"])
    assert e.value.codigo == CodigoError.CSV_COLUMNAS and e.value.params["motivo"] == "duplicada"


@pytest.mark.parametrize("alias", ["pci_mapping", "PCI Mapping", "Mapeo PCI", "mapeo-pci"])
def test_los_alias_y_variantes_de_mayusculas_y_guiones_se_reconocen(alias):
    r = importar([f"nombre;{alias}", "a-01;gpu-a2"])
    assert fila(r, 2).cfg.hardware_cluster == hw(pci("gpu-a2"))


# --- CA-D3.7.3 y CA-D6.3.1/2: valores y herencia --------------------------------------------------


def test_ca_d3_7_3_un_csv_con_dos_pci_y_un_usb_genera_hostpci0_hostpci1_y_usb0():
    # Los ids van separados por «;»: se entrecomillan para no confundirlos con el separador.
    r = importar(["nombre;mapeo_pci;mapeo_usb", 'a-01;"gpu-a2;gpu-b1";llave-hasp'])
    f = fila(r, 2)
    assert f.estado != EstadoFila.CON_ERROR, f.problemas
    assert f.cfg.hardware_cluster == hw(pci("gpu-a2"), pci("gpu-b1"), usb("llave-hasp"))


def test_ca_d3_7_3_cada_id_toma_las_opciones_por_defecto_del_formulario():
    base = hw(pci("gpu-a2", pcie=True, x_vga=True, rombar=False), usb("llave-hasp", usb3=True))
    r = importar(
        ["nombre;mapeo_pci;mapeo_usb", 'a-01;"gpu-a2;nueva";llave-hasp'], hardware_base=base
    )
    f = fila(r, 2).cfg.hardware_cluster
    assert f.pci[0] == pci("gpu-a2", pcie=True, x_vga=True, rombar=False)  # opciones del formulario
    assert f.pci[1] == pci("nueva")  # un id nuevo: opciones por defecto
    assert f.usb[0] == usb("llave-hasp", usb3=True)


def test_ca_d6_3_1_un_csv_de_0_8_0_sin_las_columnas_nuevas_usa_los_valores_del_formulario():
    r = importar(["nombre;cpu", "a-01;2", "a-02;4"])
    assert all(f.cfg.hardware_cluster is None for f in r.filas)
    r2 = importar(["nombre;cpu", "a-01;2"], hardware_base=hw(pci("gpu-a2")))
    assert fila(r2, 2).cfg.hardware_cluster == hw(pci("gpu-a2"))  # el formulario se hereda


def test_ca_d6_3_2_cada_celda_vacia_hereda_el_valor_del_formulario_por_separado():
    base = hw(pci("del-formulario"), usb("usb-formulario"))
    r = importar(["nombre;mapeo_pci;mapeo_usb", "a-01;;", "a-02;propio;", "a-03;;usb-propio"],
                 hardware_base=base)  # fmt: skip
    assert fila(r, 2).cfg.hardware_cluster == base
    assert fila(r, 3).cfg.hardware_cluster == hw(pci("propio"), usb("usb-formulario"))
    assert fila(r, 4).cfg.hardware_cluster == hw(pci("del-formulario"), usb("usb-propio"))


def test_ca_d0_5_2_un_csv_con_mapeo_usb_distinto_por_fila_y_celdas_vacias_en_otras():
    base = hw(usb("formulario"))
    r = importar(["nombre;mapeo_usb", "a-01;llave-1", "a-02;", "a-03;llave-3"], hardware_base=base)
    usos = [fila(r, n).cfg.hardware_cluster.usb[0].mapeo for n in (2, 3, 4)]
    assert usos == ["llave-1", "formulario", "llave-3"]


def test_ca_d0_5_1_un_lote_homogeneo_lleva_el_mismo_hardware_en_todas_las_filas_sin_celdas():
    base = hw(pci("g"), usb("u"))
    r = importar(["nombre", "a-01", "a-02", "a-03"], hardware_base=base)
    assert {fila(r, n).cfg.hardware_cluster for n in (2, 3, 4)} == {base}


def test_la_celda_con_espacios_y_ids_repetidos_se_normaliza_sin_inventar_nada():
    r = importar(["nombre;mapeo_pci", 'a-01;" gpu-a2 ; otra "'])
    assert fila(r, 2).cfg.hardware_cluster == hw(pci("gpu-a2"), pci("otra"))
    r = importar(["nombre;mapeo_pci", "a-01; ;"])  # solo separadores: vacío
    assert fila(r, 2).cfg.hardware_cluster is None


# --- CA-D6.3.4, CA-D6.3.6, CA-D6.3.8: errores por fila y columna ----------------------------------


@pytest.mark.parametrize(
    "malo", ["con espacio", "a=b", "a,b", "x" * 65, "<b>", "a/b", "ñandú", "$(rm)", "a\\b"]
)
def test_ca_d6_3_4_un_id_invalido_marca_la_fila_y_la_columna_con_v_d70_sin_bloquear_las_demas(malo):
    r = importar(["nombre;mapeo_pci", f'a-01;"{malo}"', "a-02;gpu-a2", "a-03;"])
    assert ("mapeo_pci", "V-D70") in reglas(fila(r, 2))
    assert fila(r, 2).estado == EstadoFila.CON_ERROR
    p = next(p for p in fila(r, 2).problemas if p.regla == "V-D70")
    assert p.severidad == Severidad.ERROR and p.params["motivo"] == "id_invalido"
    assert fila(r, 3).estado != EstadoFila.CON_ERROR and fila(r, 4).estado != EstadoFila.CON_ERROR
    assert set(r.numeros_validos) == {3, 4}


def test_ca_d6_3_4_un_id_invalido_en_la_columna_usb_se_asocia_a_esa_columna():
    r = importar(["nombre;mapeo_pci;mapeo_usb", "a-01;ok;con espacio"])
    assert ("mapeo_usb", "V-D70") in reglas(fila(r, 2)) and ("mapeo_pci", "V-D70") not in reglas(
        fila(r, 2)
    )


def test_ca_d6_3_6_las_celdas_que_empiezan_por_formula_son_texto_y_no_se_ejecutan():
    for celda in ("=1+1", "+cmd", "-2+3", "@SUMA(A1)"):
        r = importar(["nombre;mapeo_pci", f'a-01;"{celda}"'])
        assert ("mapeo_pci", "V-D70") in reglas(fila(r, 2)), celda  # un id no puede ser una fórmula
        assert fila(r, 2).cfg is None or fila(r, 2).cfg.hardware_cluster is None


@pytest.mark.parametrize(
    ("columna", "cantidad", "maximo", "tipo"),
    [("mapeo_pci", 17, 16, "pci"), ("mapeo_usb", 6, 5, "usb")],
)
def test_ca_d6_3_8_mas_de_16_pci_o_mas_de_5_usb_dan_v_d59_en_esa_fila(
    columna, cantidad, maximo, tipo
):
    ids = ";".join(f"m{i}" for i in range(cantidad))
    r = importar([f"nombre;{columna}", f'a-01;"{ids}"', "a-02;m1"])
    p = next(p for p in fila(r, 2).problemas if p.regla == "V-D59")
    assert p.columna == columna and p.severidad == Severidad.ERROR
    assert p.params == {"tipo": tipo, "maximo": str(maximo), "cantidad": str(cantidad)}
    assert fila(r, 3).estado != EstadoFila.CON_ERROR


def test_ca_d6_3_8_el_limite_exacto_de_16_pci_y_5_usb_se_acepta():
    pci_ids = ";".join(f"g{i}" for i in range(16))
    usb_ids = ";".join(f"u{i}" for i in range(5))
    r = importar(["nombre;mapeo_pci;mapeo_usb", f'a-01;"{pci_ids}";"{usb_ids}"'])
    assert fila(r, 2).estado != EstadoFila.CON_ERROR
    assert (
        len(fila(r, 2).cfg.hardware_cluster.pci) == 16
        and len(fila(r, 2).cfg.hardware_cluster.usb) == 5
    )


def test_ca_d6_3_4_el_error_no_filtra_el_texto_hostil_a_los_params():
    r = importar(["nombre;mapeo_pci", 'a-01;"<script>alert(1)</script>"'])
    p = next(p for p in fila(r, 2).problemas if p.regla == "V-D70")
    assert "script" not in json.dumps(p.params)


# --- CA-D2.7.3, CA-D6.3.9, CL-D17: filas ARM ------------------------------------------------------


def _inv_mixto():
    return inv_arq({"pve1": X86, "pve2": X86, "pve-arm": ARM}, nodos=("pve1", "pve2", "pve-arm"))


def test_ca_d2_7_3_firmware_seabios_en_una_fila_de_un_nodo_arm_da_v_d09_en_su_fila_y_columna():
    lineas = [
        "nombre;nodo;firmware",
        "a-01;pve1;seabios",
        "a-02;pve-arm;seabios",
        "a-03;pve-arm;ovmf",
    ]
    r = importar(lineas, inv=_inv_mixto())
    assert fila(r, 2).estado != EstadoFila.CON_ERROR
    assert ("firmware", "V-D09") in reglas(fila(r, 3)) and fila(r, 3).estado == EstadoFila.CON_ERROR
    assert fila(r, 4).estado != EstadoFila.CON_ERROR
    p = next(p for p in fila(r, 3).problemas if p.regla == "V-D09")
    assert p.params["motivo"] == "firmware" and p.params["alternativa"] == "ovmf"


@pytest.mark.parametrize(
    ("columna", "valor", "motivo"),
    [
        ("modelo_red", "e1000", "red"),
        ("tipo_cpu", "x86-64-v3", "cpu"),
        ("tipo_cpu", "kvm64", "cpu"),
    ],
)
def test_ca_d6_3_9_una_fila_arm_con_valores_x86_da_v_d09_en_fila_y_columna(columna, valor, motivo):
    r = importar([f"nombre;nodo;{columna}", f"a-01;pve-arm;{valor}"], inv=_inv_mixto())
    p = next(p for p in fila(r, 2).problemas if p.regla == "V-D09")
    assert p.columna == columna and p.params["motivo"] == motivo


@pytest.mark.parametrize("valor", ["host", "max", "custom-gamer"])
def test_las_cpu_validas_en_arm_en_la_celda_no_dan_error(valor):
    r = importar(["nombre;nodo;tipo_cpu", f"a-01;pve-arm;{valor}"], inv=_inv_mixto())
    assert "V-D09" not in [x for _, x in reglas(fila(r, 2))]


def test_ca_d6_3_9_lo_heredado_del_perfil_en_un_nodo_arm_no_es_error_se_adapta_despues():
    r = importar(["nombre;nodo", "a-01;pve-arm"], inv=_inv_mixto())
    assert fila(r, 2).estado != EstadoFila.CON_ERROR and "V-D09" not in [
        x for _, x in reglas(fila(r, 2))
    ]


def test_cl_d17_pci_con_pcie_heredado_del_formulario_en_una_fila_arm_es_v_d09_en_mapeo_pci():
    base = hw(pci("gpu-a2", pcie=True))
    r = importar(["nombre;nodo;mapeo_pci", "a-01;pve-arm;gpu-a2", "a-02;pve1;gpu-a2"],
                 inv=_inv_mixto(), hardware_base=base)  # fmt: skip
    p = next(p for p in fila(r, 2).problemas if p.regla == "V-D09")
    assert p.columna == "mapeo_pci" and p.params["motivo"] == "pcie"
    assert fila(r, 3).estado != EstadoFila.CON_ERROR


def test_en_x86_o_sin_inventario_los_mismos_valores_no_dan_v_d09():
    for inv in (None, inv_arq({"pve1": X86}, nodos=("pve1",))):
        r = importar(["nombre;nodo;firmware;modelo_red", "a-01;pve1;seabios;e1000"], inv=inv)
        assert "V-D09" not in [x for _, x in reglas(fila(r, 2))]


# --- CA-D2.8.3 y CA-D0.3.3: de CSV a plan ---------------------------------------------------------


def _plan(r: ResultadoImportacion, inv, hw_=None):
    filas = filas_lote(r, r.numeros_validos)
    d = DefinicionLote(filas[0].cfg, len(filas), PatronNombres(""), Destino(), filas=filas)
    return construir_plan(
        d, inv, list(range(100, 100 + len(filas))), [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip


def test_ca_d2_8_3_un_csv_con_la_fila_4_en_un_nodo_arm_asocia_v_d06_a_la_fila_4():
    inv = _inv_mixto()
    r = importar(["nombre;nodo", "a-01;pve1", "a-02;pve1", "a-03;pve2", "a-04;pve-arm"], inv=inv)
    plan = _plan(r, inv)
    v_d06 = [p for p in plan.problemas if p.regla == "V-D06"]
    assert [p.indice for p in v_d06] == [3]  # la 4.ª fila del archivo (índice 3 del plan)
    assert plan.elementos[3].nombre == "a-04" and plan.bloqueado


def test_ca_d0_3_3_un_csv_con_un_mapeo_sin_mapping_use_no_deja_crear_con_el():
    inv = inv_arq({"pve1": X86}, nodos=("pve1",))  # el rol de 14 no trae Mapping.Use
    inv.catalogo = dataclasses.replace(
        inv.catalogo, hardware=info_hw(mapeo("pci", "gpu-a2", "pve1"))
    )
    r = importar(["nombre;nodo;mapeo_pci", "a-01;pve1;gpu-a2"], inv=inv)
    plan = _plan(r, inv)
    assert plan.bloqueado
    (p,) = [x for x in plan.problemas if x.regla == "V-D63"]
    assert p.params["ruta"] == "/mapping/pci/gpu-a2" and p.params["privilegio"] == "Mapping.Use"


def test_ca_d3_7_3_el_csv_con_permiso_genera_hostpci_y_usb_en_la_peticion():
    banco = banco_d({"pve1": X86}, nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [
        mapeo_api("gpu-a2", ("pve1", "/x")),
        mapeo_api("gpu-b1", ("pve1", "/y")),
    ]
    banco.cluster.mapeos_api["usb"] = [mapeo_api("llave-hasp", ("pve1", "/u"))]
    lineas = ["nombre;nodo;mapeo_pci;mapeo_usb", 'a-01;pve1;"gpu-a2;gpu-b1";llave-hasp']
    r = importar(lineas, inv=banco.inv)
    filas = tuple(
        dataclasses.replace(f, cfg=dataclasses.replace(f.cfg, discos=[Disco("local-lvm", 8)]))
        for f in filas_lote(r, r.numeros_validos)
    )
    plan = plan_de(banco, definicion_filas(list(filas)))
    assert not plan.bloqueado, [(p.regla, p.params) for p in plan.problemas]
    p = construir_parametros(plan.elementos[0].cfg, banco.inv)
    assert p["hostpci0"] == "mapping=gpu-a2" and p["hostpci1"] == "mapping=gpu-b1"
    assert p["usb0"] == "mapping=llave-hasp"


# --- CA-D6.3.7: la plantilla descargable ----------------------------------------------------------


def test_ca_d6_3_7_la_plantilla_incluye_las_columnas_nuevas_con_ejemplos_que_no_rompen_la_lectura(
    tmp_path,
):
    assert "mapeo_pci" in ENCABEZADO_PLANTILLA and "mapeo_usb" in ENCABEZADO_PLANTILLA
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    texto = ruta.read_text(encoding="utf-8-sig")
    filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert len(filas[0]) == len(ENCABEZADO_PLANTILLA)
    r = interpretar(
        leer_tabla(ruta.read_bytes()),
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    assert r.filas and all(f.estado != EstadoFila.CON_ERROR for f in r.filas), [
        (f.numero, reglas(f)) for f in r.filas
    ]


def test_ca_d6_3_7_la_plantilla_no_incluye_columnas_para_mac_imagenes_ni_xml():
    for prohibida in (
        "mac",
        "imagen_disco",
        "imagenes",
        "xml",
        "libvirt",
        "passwd",
        "mac_conservada",
    ):
        assert prohibida not in ENCABEZADO_PLANTILLA


def test_las_columnas_nuevas_no_cambian_el_orden_de_las_anteriores():
    nombres = [c.canonica for c in COLUMNAS]
    assert nombres.index("nombre") == 0 and nombres.index("mapeo_pci") > nombres.index("tipo_cpu")
