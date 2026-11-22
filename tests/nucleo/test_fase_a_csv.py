"""Fase A (0.6.0): columnas nuevas del CSV (interpretación fila a fila).

Cubre CA-A1.4.2 a A1.4.4, CA-A2.6.2, CA-A3.6.1 a A3.6.3, CA-A4.6.1/A4.6.2, CA-A5.2.4,
CA-A5.3.1/A5.3.2, CA-A6.2.1/A6.2.2, RF-A7.3 (CA-A7.3.1 a A7.3.5, A7.3.8, A7.3.9), RNF-A2, RNF-A4
y CL-A1. Los límites de lectura y la plantilla están en ``test_fase_a_csv_lectura.py``.
"""

import dataclasses

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo as Aviso
from proxlaunch.nucleo.csv_importacion.columnas import COLUMNAS, resolver_columnas
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, PatronNombres
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor
from proxlaunch.nucleo.modelos.vm import ModeloRed
from proxlaunch.nucleo.opciones.modelos import OpcionesParciales
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)

from .apoyo_fase_a_p2 import permisos
from .apoyo_lote import crear_banco, plantilla, volcar
from .apoyo_mvp3 import importar_csv

TOKEN = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"


def _fila(r, n):
    return next(f for f in r.filas if f.numero == n)


def _problemas(f):
    return [(p.columna, p.regla) for p in f.problemas]


# --- RF-A1.4 y RF-A6.2: columnas booleanas ----------------------------------------------------


def test_ca_a1_4_2_encender_si_y_arranque_auto_no_se_reflejan_en_la_fila():
    r = importar_csv(["nombre;encender;arranque_auto", "a;sí;no"])
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CORRECTA
    assert f.opciones.encender is True
    assert f.opciones.arranque_auto is False
    assert (f.cfg.encender, f.cfg.arranque_auto) == (True, False)


@pytest.mark.parametrize(
    ("celda", "esperado"),
    [("si", True), ("SÍ", True), ("yes", True), ("true", True), ("1", True),
     ("no", False), ("No", False), ("false", False), ("0", False)],
)  # fmt: skip
def test_ca_a1_4_2_los_valores_booleanos_aceptados(celda, esperado):
    f = _fila(importar_csv(["nombre;encender", f"a;{celda}"]), 2)
    assert f.opciones.encender is esperado


@pytest.mark.parametrize("columna", ["encender", "arranque_auto", "proteger"])
def test_ca_a1_4_3_a6_2_2_un_valor_no_booleano_da_error_con_columna_y_valor_y_no_se_crea(columna):
    r = importar_csv([f"nombre;{columna}", "a;quizá", "b;si"])
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    (p,) = f.problemas
    assert p.columna == columna  # el encabezado tal como está en el archivo
    assert p.valor == "quizá"
    assert p.severidad.value == "error"
    assert f.cfg is None
    assert 2 not in r.numeros_validos
    with pytest.raises(ValueError):
        filas_lote(r, [2])
    assert _fila(r, 3).estado == EstadoFila.CORRECTA  # las demás filas no se bloquean


def test_ca_a1_4_3_el_error_nombra_la_columna_tal_como_viene_en_el_archivo():
    r = importar_csv(["nombre;Encender", "a;quizá"])
    assert _fila(r, 2).problemas[0].columna == "Encender"


def test_ca_a1_4_4_sin_las_columnas_se_usan_los_valores_del_formulario():
    r = importar_csv(["nombre;cpu", "a;2", "b;4"])
    for f in r.filas:
        assert f.opciones is None  # None = hereda todo del formulario (RF-A0.7)


def test_ca_a6_2_1_proteger_si_protege_no_y_vacio_no():
    r = importar_csv(["nombre;proteger", "a;sí", "b;no", "c;"])
    assert _fila(r, 2).opciones.proteger is True
    assert _fila(r, 2).cfg.proteger is True
    assert _fila(r, 3).opciones.proteger is False
    assert _fila(r, 4).opciones is None  # vacío = hereda (no «falso»; CA-A7.3.2)


def test_ca_a7_3_2_celda_vacia_en_una_fila_hereda_el_valor_del_formulario_no_falso():
    r = importar_csv(["nombre;encender;pool;etiquetas;notas", "a;si;p1;web;hola", "b;;;;"])
    assert _fila(r, 2).opciones == OpcionesParciales(
        encender=True, notas="hola", etiquetas_usuario=("web",), pool="p1"
    )
    assert _fila(r, 3).opciones is None


def test_ca_a1_4_x_el_perfil_de_la_columna_perfil_con_arranque_lo_fija_en_la_fila():
    perfil = PerfilMaquina(
        "d" * 32, "Con arranque", "", OrigenPerfil.USUARIO,
        ConfigPerfil(discos=(DiscoPerfil(10),), redes=(RedPerfil(),), arranque_auto=True),
    )  # fmt: skip
    r = importar_csv(["nombre;perfil", "a;Con arranque", "b;"], perfiles=[perfil])
    assert _fila(r, 2).opciones.arranque_auto is True
    assert _fila(r, 3).opciones is None


# --- RF-A3.6 etiquetas ------------------------------------------------------------------------


def test_ca_a3_6_1_etiquetas_web_prod_se_reparten_y_las_fijas_las_pone_el_planificador():
    r = importar_csv(["nombre;etiquetas", 'a;"web,prod"'])
    f = _fila(r, 2)
    assert f.opciones.etiquetas_usuario == ("web", "prod")
    assert f.cfg.etiquetas == ()  # ni las fijas ni las de usuario van en ``etiquetas``
    (fl,) = filas_lote(r, [2])
    assert fl.cfg.etiquetas == ()
    assert fl.opciones.etiquetas_usuario == ("web", "prod")


@pytest.mark.parametrize("celda", ['"web,prod"', '"web, prod"', '"web;prod"', '"web ; prod"'])
def test_ca_a3_6_1_separadores_coma_y_punto_y_coma_con_espacios(celda):
    f = _fila(importar_csv(["nombre;etiquetas", f"a;{celda}"]), 2)
    assert f.opciones.etiquetas_usuario == ("web", "prod")


def test_ca_a3_6_1_duplicadas_y_vacias_se_normalizan():
    r = importar_csv(["nombre;etiquetas", 'a;"web,,web, prod ,"'])
    assert _fila(r, 2).opciones.etiquetas_usuario == ("web", "prod")


def test_ca_a3_6_2_una_etiqueta_invalida_nombra_la_etiqueta_y_la_columna_sin_bloquear_las_demas():
    r = importar_csv(["nombre;etiquetas", "a;mala etiqueta!", "b;web"])
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    p = next(p for p in f.problemas if p.regla == "V-A02")
    assert p.columna == "etiquetas"
    assert p.params["etiqueta"] == "mala etiqueta!"
    assert _fila(r, 3).estado == EstadoFila.CORRECTA
    assert r.numeros_validos == (3,)


def test_ca_a3_6_2_una_etiqueta_demasiado_larga_es_error_de_esa_celda():
    r = importar_csv(["nombre;etiquetas", f"a;{'a' * 129}"])
    assert ("etiquetas", "V-A02") in _problemas(_fila(r, 2))


def test_ca_a3_6_3_sin_la_columna_se_usan_las_del_formulario():
    f = _fila(importar_csv(["nombre", "a"]), 2)
    assert f.opciones is None


# --- RF-A4.6 pool -----------------------------------------------------------------------------


def test_ca_a4_6_1_cada_fila_lleva_su_pool():
    r = importar_csv(["nombre;pool", "a;produccion", "b;lab", "c;produccion"])
    assert [_fila(r, n).opciones.pool for n in (2, 3, 4)] == ["produccion", "lab", "produccion"]
    assert [_fila(r, n).cfg.pool for n in (2, 3, 4)] == ["produccion", "lab", "produccion"]


@pytest.mark.parametrize("celda", ["ninguno", "Ninguna", "sin pool", "none"])
def test_ca_a4_6_2_ninguno_equivale_a_sin_pool_aunque_el_formulario_lo_fije(celda):
    f = _fila(importar_csv(["nombre;pool", f"a;{celda}"]), 2)
    assert f.opciones.pool == ""  # anula el del formulario (planificador)
    assert f.cfg.pool is None


def test_ca_a4_6_2_vacio_hereda_el_del_formulario():
    f = _fila(importar_csv(["nombre;pool;cpu", "a;;2"]), 2)
    assert f.opciones is None
    assert f.cfg.pool is None


# --- RF-A5.3 mtu y limite_red -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("celda", "esperado"),
    [("igual", 1), ("1", 1), ("Igual", 1), ("1500", 1500), ("9000", 9000), ("576", 576),
     ("65520", 65520), ("heredar", None)],
)  # fmt: skip
def test_ca_a5_3_2_vocabulario_del_mtu(celda, esperado):
    f = _fila(importar_csv(["nombre;mtu", f"a;{celda}"]), 2)
    assert f.estado == EstadoFila.CORRECTA
    assert f.cfg.redes[0].mtu == esperado


def test_ca_a5_3_2_mtu_vacio_es_heredar_y_no_pisa_el_del_perfil_base():
    base = PerfilMaquina(
        "e" * 32, "MTU alto", "", OrigenPerfil.USUARIO,
        ConfigPerfil(discos=(DiscoPerfil(10),), redes=(RedPerfil(mtu=9000, limite_mb=50.0),)),
    )  # fmt: skip
    r = importar_csv(["nombre;mtu", "a;", "b;heredar", "c;1500"], base=base)
    assert _fila(r, 2).cfg.redes[0].mtu == 9000  # celda vacía: lo del perfil
    assert _fila(r, 3).cfg.redes[0].mtu is None  # heredar explícito
    assert _fila(r, 4).cfg.redes[0].mtu == 1500
    assert all(_fila(r, n).cfg.redes[0].limite_mb == 50.0 for n in (2, 3, 4))


@pytest.mark.parametrize(("celda", "esperado"), [("50", 50.0), ("12,5", 12.5), ("0.5", 0.5)])
def test_ca_a5_3_limite_red_en_mb_con_decimales(celda, esperado):
    f = _fila(importar_csv(["nombre;limite_red", f'a;"{celda}"']), 2)
    assert f.estado == EstadoFila.CORRECTA
    assert f.cfg.redes[0].limite_mb == esperado


def test_ca_a5_3_las_columnas_se_aplican_a_la_tarjeta_1():
    f = _fila(importar_csv(["nombre;mtu;limite_red", "a;9000;50"]), 2)
    assert (f.cfg.redes[0].mtu, f.cfg.redes[0].limite_mb) == (9000, 50.0)
    assert len(f.cfg.redes) == 1


def test_ca_a5_3_1_mtu_y_limite_red_son_columnas_avanzadas_como_sockets():
    por_nombre = {c.canonica: c for c in COLUMNAS}
    assert por_nombre["mtu"].avanzada and por_nombre["limite_red"].avanzada
    assert por_nombre["sockets"].avanzada  # la referencia del requisito
    for estandar in ("encender", "arranque_auto", "notas", "etiquetas", "pool", "proteger"):
        assert not por_nombre[estandar].avanzada


def test_ca_a5_2_4_mtu_con_modelo_no_virtio_error_de_fila_en_la_columna_mtu():
    r = importar_csv(["nombre;mtu;modelo_red", "a;9000;e1000", "b;9000;virtio"])
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    p = next(p for p in f.problemas if p.regla == "V-A05")
    assert p.columna == "mtu"
    assert p.params["modelo"] == "e1000"
    assert _fila(r, 3).estado == EstadoFila.CORRECTA


def test_ca_a5_2_3_limite_si_se_admite_con_modelo_no_virtio():
    f = _fila(importar_csv(["nombre;limite_red;modelo_red", "a;50;e1000"]), 2)
    assert f.estado == EstadoFila.CORRECTA
    assert f.cfg.redes[0].modelo == ModeloRed.E1000


# --- RF-A7.3 columnas y errores ---------------------------------------------------------------

ALIAS = {
    "encender": "start",
    "arranque_auto": "onboot",
    "notas": "notes",
    "etiquetas": "tags",
    "pool": "pool",
    "proteger": "protection",
    "mtu": "mtu",
    "limite_red": "rate",
}


@pytest.mark.parametrize(("canonica", "alias"), ALIAS.items())
def test_cl_a_p22_los_alias_en_ingles_se_resuelven_a_la_columna_canonica(canonica, alias):
    mapa, avisos = resolver_columnas(["nombre", alias])
    assert mapa.posiciones[canonica] == 1
    assert avisos == ()


@pytest.mark.parametrize("canonica", ALIAS)
def test_ca_a7_3_columna_canonica_con_mayusculas_y_espacios(canonica):
    mapa, _ = resolver_columnas(["Nombre", canonica.upper().replace("_", " ")])
    assert canonica in mapa.posiciones


def test_ca_a7_3_1_un_csv_de_051_se_lee_igual_y_las_filas_toman_los_del_formulario():
    lineas = [
        "nombre;perfil;cpu;memoria;disco;almacenamiento;red;vlan;nodo;vmid",
        "web-01;fabrica.servidor-mediano;2;4 GiB;40 GiB;;vmbr0;20;;150",
        "web-02;;4;8 GiB;80 GiB;;vmbr0;;;",
    ]
    r = importar_csv(lineas)
    assert [f.estado for f in r.filas] == [EstadoFila.CORRECTA, EstadoFila.CORRECTA]
    assert r.avisos == ()
    a, b = r.filas
    assert (a.cfg.cores, a.cfg.memoria_mib, a.vmid, a.cfg.redes[0].vlan) == (2, 4096, 150, 20)
    assert (b.cfg.cores, b.cfg.memoria_mib) == (4, 8192)
    for f in r.filas:
        assert f.opciones is None
        assert f.cfg.redes[0].mtu is None and f.cfg.redes[0].limite_mb is None
        assert not (f.cfg.encender or f.cfg.proteger or f.cfg.notas or f.cfg.pool)
        assert f.cfg.etiquetas_usuario == ()


def test_rnf_a4_los_csv_de_tests_datos_mvp3_se_siguen_leyendo_igual():
    from .apoyo_mvp3 import DATOS_MVP3

    texto = (DATOS_MVP3 / "excel-windows1252.csv").read_bytes().decode("cp1252")
    r = importar_csv(texto.splitlines())
    assert [f.estado for f in r.filas] == [EstadoFila.CORRECTA] * 4
    assert all(f.opciones is None for f in r.filas)
    assert [f.cfg.cores for f in r.filas] == [1, 4, 2, 8]


@pytest.mark.parametrize(
    "encabezado",
    ["nombre;pool;pool", "nombre;notas;notes", "nombre;encender;start", "nombre;mtu;mtu",
     "nombre;limite_red;rate", "nombre;proteger;protection", "nombre;etiquetas;tags"],
)  # fmt: skip
def test_ca_a7_3_3_columna_nueva_duplicada_o_con_dos_alias_es_error_csv_columnas(encabezado):
    with pytest.raises(ErrorProxLaunch) as exc:
        importar_csv([encabezado, "a;x;y"])
    assert exc.value.codigo == CodigoError.CSV_COLUMNAS
    assert exc.value.params["motivo"] == "duplicada"


def test_ca_a7_3_4_columna_de_nombre_parecido_no_definido_es_aviso_no_error():
    r = importar_csv(["nombre;etiqueta", "a;web"])
    assert [a.codigo for a in r.avisos] == [Aviso.COLUMNA_NO_USADA]
    assert r.avisos[0].params["columna"] == "etiqueta"
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CORRECTA and f.opciones is None  # no se lee


def test_ca_a7_3_5_valores_erroneos_se_asocian_a_fila_y_columna_sin_bloquear_las_validas():
    lineas = [
        "nombre;encender;etiquetas;mtu;limite_red;proteger",
        "a;quizá;;;;",  # booleano inválido
        "b;;mala etiqueta!;;;",  # etiquetas inválidas
        "c;;;100;;",  # MTU fuera de rango
        "d;;;;-5;",  # rate negativo
        "e;;;;0;",  # rate cero
        "f;;;70000;;",  # MTU por encima
        "g;si;web;1500;50;si",  # válida
    ]
    r = importar_csv(lineas)
    esperado = {
        2: ("encender", "E-M11.valor_no_admitido"),
        3: ("etiquetas", "V-A02"),
        4: ("mtu", "V-A04"),
        5: ("limite_red", "E-M11.no_numero"),
        6: ("limite_red", "V-A06"),
        7: ("mtu", "V-A04"),
    }
    for n, par in esperado.items():
        f = _fila(r, n)
        assert f.estado == EstadoFila.CON_ERROR, n
        assert par in _problemas(f), (n, _problemas(f))
    assert _fila(r, 8).estado == EstadoFila.CORRECTA
    assert r.numeros_validos == (8,)


@pytest.mark.parametrize("celda", ["1,5", "1500,5", "abc", "9000 MB"])
def test_ca_a7_3_5_mtu_no_entero_o_no_numerico_es_error_de_la_celda(celda):
    f = _fila(importar_csv(["nombre;mtu", f'a;"{celda}"']), 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert all(p.columna == "mtu" for p in f.problemas)


def test_ca_a7_3_5_pool_con_solo_espacios_cuenta_como_celda_vacia():
    f = _fila(importar_csv(["nombre;pool", "a;   "]), 2)
    assert f.estado == EstadoFila.CORRECTA and f.opciones is None


def test_ca_a7_3_5_varios_errores_en_una_fila_se_listan_hasta_el_tope_de_problemas():
    r = importar_csv(["nombre;encender;arranque_auto;proteger;mtu;limite_red", "a;x;x;x;x;x"])
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert {p.columna for p in f.problemas} >= {"encender", "arranque_auto", "proteger"}
    assert len(f.problemas) + f.problemas_omitidos == 5


# --- Notas ------------------------------------------------------------------------------------


def test_ca_a2_6_2_notas_con_saltos_de_linea_entre_comillas_se_conservan_como_lf():
    r = importar_csv(["nombre;notas", 'a;"línea 1\r\nlínea 2\nlínea 3"'])
    assert _fila(r, 2).opciones.notas == "línea 1\nlínea 2\nlínea 3"


def test_ca_a2_6_2_notas_conserva_tabuladores_y_acentos():
    r = importar_csv(["nombre;notas", 'a;"col1\tcol2 ñandú"'])
    assert _fila(r, 2).opciones.notas == "col1\tcol2 ñandú"


def test_ca_a2_5_7_notas_con_caracteres_de_control_se_limpian_con_aviso():
    r = importar_csv(["nombre;notas", "a;hola\x07mundo"])
    f = _fila(r, 2)
    assert f.opciones.notas == "holamundo"
    assert ("notas", "V-A14") in _problemas(f)
    assert f.estado == EstadoFila.CON_AVISO


def test_ca_a2_6_1_notas_de_300_caracteres_se_aceptan():
    r = importar_csv(["nombre;notas", f"a;{'n' * 300}"])
    assert len(_fila(r, 2).opciones.notas) == 300


def test_ca_a7_3_8_notas_con_disparador_de_formula_se_trata_como_texto():
    r = importar_csv(["nombre;notas", "a;=cmd|' /C calc'!A0", "b;@SUM(1)"])
    assert _fila(r, 2).opciones.notas == "=cmd|' /C calc'!A0"
    assert _fila(r, 3).opciones.notas == "@SUM(1)"
    assert all(f.estado == EstadoFila.CORRECTA for f in r.filas)


def test_ca_a7_3_8_al_escribir_un_csv_las_notas_con_disparador_no_generan_formula(tmp_path):
    from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv

    ruta = tmp_path / "salida.csv"
    escribir_csv(ruta, ["nombre", "notas"], [["a", "=cmd|' /C calc'!A0"], ["b", "+1"]])
    for linea in ruta.read_text("utf-8-sig").splitlines()[1:]:
        celda = linea.split(";", 1)[1]
        assert celda.startswith("'") or celda.startswith("\"'")


# --- RNF-A2: credenciales ---------------------------------------------------------------------


def test_rnf_a2_notas_con_token_es_error_de_fila_sin_nombrar_el_secreto_en_los_parametros():
    r = importar_csv(["nombre;notas", f"a;{TOKEN}"])
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert f.cfg is None
    assert f.problemas[0].columna == "notas"
    assert f.problemas[0].params == {"motivo": "token"}


def test_rnf_a2_notas_con_token_no_se_conserva_en_el_resultado_de_la_importacion():
    """El resultado alimenta el diálogo («Valor del archivo: …») y puede acabar en registros."""
    r = importar_csv(["nombre;notas", f"a;{TOKEN}"])
    assert "0a1b2c3d" not in volcar(r)


# --- CA-A7.3.9 / CL-A1: Comprobar valida por fila ---------------------------------------------


def _plan_de_filas(banco, r, numeros, privilegios):
    filas = filas_lote(r, numeros)
    d = DefinicionLote(plantilla(), len(filas), PatronNombres(""), Destino(), filas=filas)
    inv = dataclasses.replace(
        banco.inv, catalogo=CatalogoServidor(permisos=permisos(*privilegios, ruta="/"))
    )
    return Planificador(banco.sesion, banco.reloj, generador_id=lambda: "abcd1234").planificar(
        d, inv
    )


BASICOS = ["VM.Allocate", "VM.Audit", "VM.Config.Options", "VM.Config.Network",
           "Datastore.AllocateSpace", "SDN.Use"]  # fmt: skip


def test_ca_a7_3_9_encender_si_sin_powermgmt_bloquea_solo_esa_fila_con_el_privilegio_que_falta():
    banco = crear_banco()
    r = importar_csv(
        ["nombre;encender", "a;si", "b;no", "c;"], inv=banco.inv, nodo_referencia="pve1"
    )
    plan = _plan_de_filas(banco, r, [2, 3, 4], BASICOS)
    v_a12 = [p for p in plan.problemas if p.regla == "V-A12"]
    assert [p.indice for p in v_a12] == [0]
    assert v_a12[0].params["privilegio"] == "VM.PowerMgmt"
    assert v_a12[0].severidad.value == "error"


def test_ca_a7_3_9_con_powermgmt_no_hay_bloqueo():
    banco = crear_banco()
    r = importar_csv(["nombre;encender", "a;si"], inv=banco.inv, nodo_referencia="pve1")
    plan = _plan_de_filas(banco, r, [2], [*BASICOS, "VM.PowerMgmt"])
    assert not [p for p in plan.problemas if p.regla == "V-A12"]


def test_cl_a1_lote_mixto_cada_fila_se_valida_por_separado():
    banco = crear_banco()
    r = importar_csv(
        ["nombre;encender;proteger;pool", "a;si;;", "b;;si;", "c;;;ninguno", "d;;;"],
        inv=banco.inv,
        nodo_referencia="pve1",
    )
    plan = _plan_de_filas(banco, r, [2, 3, 4, 5], [*BASICOS])
    por_fila = {p.indice for p in plan.problemas if p.regla == "V-A12"}
    assert por_fila == {0}  # solo la que enciende sin VM.PowerMgmt; proteger sí tiene Options


def test_cl_a1_fila_con_proteger_sin_config_options_bloquea_solo_esa_fila():
    banco = crear_banco()
    r = importar_csv(
        ["nombre;proteger", "a;;", "b;si", "c;no"], inv=banco.inv, nodo_referencia="pve1"
    )
    sin_options = [p for p in BASICOS if p != "VM.Config.Options"]
    plan = _plan_de_filas(banco, r, [2, 3, 4], [*sin_options, "VM.PowerMgmt"])
    v_a12 = [p for p in plan.problemas if p.regla == "V-A12"]
    assert [p.indice for p in v_a12] == [1]
    assert v_a12[0].params["privilegio"] == "VM.Config.Options"
