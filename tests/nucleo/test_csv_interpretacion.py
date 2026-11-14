"""Interpretación y validación fila a fila del CSV (RF-C03..C07, RF-C09, RF-C13; CA-C01.4,
CA-C03.6..C03.8, CA-C04.8..C04.9, CA-C05.*, CA-C06.4, CA-C06.10, CA-C07.*, CA-C09.1..C09.4,
CA-C11.5, CA-C11.10, CA-C13.*; V-M06..V-M11; INV-M4; §13 casos 10..13 de los requisitos).

``interpretar`` es una función pura sobre (tabla, perfil base, perfiles, inventario o None). Los
problemas de celda son ``ProblemaCelda`` (nunca excepciones); las columnas de credenciales y las
desconocidas no se leen jamás; los textos de celdas son solo texto (nada se evalúa).
"""

import copy
import random

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo as Aviso
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import FilaLote
from proxlaunch.nucleo.modelos.inventario import Bridge
from proxlaunch.nucleo.modelos.vm import (
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_lote import inventario, nodo, storage, volcar
from .apoyo_mvp3 import (
    CENT_PASSWORD,
    CENT_TOKEN,
    DATOS_MVP3,
    fabrica_por_id,
    importar_csv,
    perfil_base,
    tabla_csv,
)

ENC = "nombre;perfil;cpu;memoria;disco;almacenamiento;red;vlan;nodo;vmid"


def _fila(resultado, numero):
    return next(f for f in resultado.filas if f.numero == numero)


def _problemas(resultado, numero, regla):
    return [p for p in _fila(resultado, numero).problemas if p.regla == regla]


def _inv():
    return inventario(
        (nodo("pve1", 64), nodo("pve2", 32), nodo("pve3", 32, en_linea=False)),
        storages={
            "pve1": (storage("datos", "dir", 500), storage("rapido", "lvmthin", 100)),
            "pve2": (storage("datos", "dir", 400),),
            "pve3": (storage("datos", "dir", 300),),
        },
        bridges={
            "pve1": (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", False)),
            "pve2": (Bridge("vmbr0", "bridge", False),),
            "pve3": (Bridge("vmbr0", "bridge", False),),
        },
    )


def _perfil_usuario(nombre="Mi perfil", **config):
    cfg = ConfigPerfil(discos=(DiscoPerfil(10),), redes=(RedPerfil(),), **config)
    return PerfilMaquina("c" * 32, nombre, "", OrigenPerfil.USUARIO, cfg)


# --- Solo `nombre` (CA-C01.4, CA-C03.6) -----------------------------------------------------------


def test_un_archivo_con_solo_nombre_usa_todo_del_perfil_base_sin_conexion():
    r = importar_csv(["nombre", "web-01", "web-02"])
    assert r.con_inventario is False and r.perfil_base_id == "fabrica.servidor-pequeno"
    for f in r.filas:
        assert f.estado == EstadoFila.CORRECTA and f.cfg is not None
        assert (f.cfg.cores, f.cfg.sockets, f.cfg.memoria_mib) == (2, 1, 2048)
        assert [d.tamano_gib for d in f.cfg.discos] == [32]
        assert (
            f.cfg.discos[0].storage == "" and f.cfg.redes[0].bridge == ""
        )  # sin conexión: sin inventar
    assert [f.numero for f in r.filas] == [2, 3] and [f.nombre for f in r.filas] == [
        "web-01",
        "web-02",
    ]


def test_con_inventario_el_perfil_base_resuelve_storage_y_bridge_en_el_nodo_de_referencia():
    r = importar_csv(["nombre", "web-01"], inv=_inv(), nodo_referencia="pve2")
    assert r.con_inventario is True
    cfg = r.filas[0].cfg
    assert cfg.discos[0].storage == "datos" and cfg.redes[0].bridge == "vmbr0"


def test_otro_perfil_base_cambia_lo_que_el_csv_no_dice():
    base = fabrica_por_id()["fabrica.servidor-grande"]
    f = importar_csv(["nombre", "db-01"], base=base).filas[0]
    assert (f.cfg.cores, f.cfg.memoria_mib, f.cfg.discos[0].tamano_gib) == (8, 16384, 128)


def test_una_celda_vacia_en_una_columna_opcional_usa_el_perfil_y_nombre_vacio_es_v_m07():
    r = importar_csv([ENC, "web-01;;;;;;;;;", ";;4;;;;;;;"])
    assert r.filas[0].estado == EstadoFila.CORRECTA and r.filas[0].cfg.cores == 2
    assert _problemas(r, 3, "V-M07") and _fila(r, 3).estado == EstadoFila.CON_ERROR
    assert _problemas(r, 3, "V-M07")[0].columna == "nombre"


# --- Columnas sobrescriben el perfil (CA-C13.5) ---------------------------------------------------


def test_cada_columna_sobrescribe_lo_suyo():
    r = importar_csv(
        ["nombre;cpu;sockets;memoria;disco;almacenamiento;red;vlan;modelo_red;firmware;tipo_cpu",
         "web-01;4;2;8 GiB;100;rapido;vmbr1;30;e1000;UEFI;host"],
        inv=_inv(), nodo_referencia="pve1",
    )  # fmt: skip
    f = _fila(r, 2)
    assert f.estado in {EstadoFila.CORRECTA, EstadoFila.CON_AVISO}, f.problemas
    c = f.cfg
    assert (c.cores, c.sockets, c.memoria_mib, c.firmware, c.tipo_cpu) == (
        4,
        2,
        8192,
        Firmware.OVMF,
        "host",
    )
    assert c.discos == [Disco("rapido", 100)]
    assert c.redes == [InterfazRed("vmbr1", ModeloRed.E1000, 30)]


def test_el_perfil_de_la_fila_gana_al_perfil_base_y_las_columnas_ganan_al_perfil():
    r = importar_csv(
        [
            "nombre;perfil;cpu",
            "a-01;fabrica.servidor-grande;3",
            "a-02;fabrica.servidor-grande;",
            "a-03;;",
        ]
    )
    a1, a2, a3 = (_fila(r, n).cfg for n in (2, 3, 4))
    assert (a1.cores, a1.memoria_mib) == (
        3,
        16384,
    )  # cpu de la columna, memoria del perfil de la fila
    assert (a2.cores, a2.memoria_mib) == (8, 16384)
    assert (a3.cores, a3.memoria_mib) == (2, 2048)  # perfil base
    assert _fila(r, 2).perfil == "servidor-grande"


def test_propiedad_una_columna_presente_siempre_gana_al_perfil():
    """CA-C13.5: test de propiedad con semilla fija."""
    rng = random.Random(20260514)
    fabrica = list(perfiles_fabrica())
    for _ in range(300):
        perfil_fila = rng.choice([None, *fabrica])
        base = rng.choice(fabrica)
        cpu = rng.choice([None, 1, 2, 6, 16])
        mem = rng.choice([None, "1 GiB", "512 MiB", "3,5", "12"])
        disco = rng.choice([None, 5, 77])
        fw = rng.choice([None, "bios", "uefi"])
        vlan = rng.choice([None, 7, 400])
        lineas = [
            "nombre;perfil;cpu;memoria;disco;firmware;vlan",
            f"m-01;{perfil_fila.id if perfil_fila else ''};{cpu or ''};{mem or ''};{disco or ''};{fw or ''};{vlan or ''}",  # noqa: E501
        ]
        c = _fila(importar_csv(lineas, base=base), 2).cfg
        origen = (perfil_fila or base).config
        assert c.cores == (cpu if cpu else origen.cores)
        esperado_mem = {
            None: origen.memoria_mib,
            "1 GiB": 1024,
            "512 MiB": 512,
            "3,5": 3584,
            "12": 12288,
        }[mem]
        assert c.memoria_mib == esperado_mem
        assert c.discos[0].tamano_gib == (disco if disco else origen.discos[0].tamano_gib)
        assert (
            c.firmware
            == ({None: origen.firmware, "bios": Firmware.SEABIOS, "uefi": Firmware.OVMF}[fw])
        )
        assert c.redes[0].vlan == (vlan if vlan else origen.redes[0].vlan)
        assert (
            c.sockets == origen.sockets and c.tipo_cpu == origen.tipo_cpu
        )  # lo que no dice el CSV


def test_el_hardware_avanzado_del_perfil_se_conserva_si_el_csv_no_lo_toca():
    base = _perfil_usuario(tipo_cpu="host")
    c = _fila(importar_csv(["nombre;cpu", "x-01;3"], base=base, perfiles=[base]), 2).cfg
    assert c.tipo_cpu == "host" and c.cores == 3


# --- Perfil por fila (V-M06, CA-C13.2..C13.4) -----------------------------------------------------


@pytest.mark.parametrize(
    "escrito",
    [
        "servidor-mediano",
        "SERVIDOR-MEDIANO",
        "fabrica.servidor-mediano",
        "FABRICA.Servidor-Mediano",
    ],
)
def test_el_perfil_se_busca_por_nombre_visible_o_id_sin_distinguir_mayusculas(escrito):
    f = _fila(importar_csv(["nombre;perfil", f"x-01;{escrito}"]), 2)
    assert f.estado == EstadoFila.CORRECTA and f.cfg.cores == 4 and f.cfg.memoria_mib == 4096


def test_el_perfil_con_nombre_traducido_con_acentos_se_busca_sin_distinguir_acentos():
    textos = {"servidor-pequeno": ("Servidor pequeño", ""), "minimo": ("Mínimo", "")}
    perfiles = perfiles_fabrica(textos)
    for escrito in ("servidor pequeño", "SERVIDOR PEQUENO", "mínimo", "MINIMO", "Minimo"):
        r = importar_csv(["nombre;perfil", f"x-01;{escrito}"], perfiles=perfiles)
        assert _fila(r, 2).estado == EstadoFila.CORRECTA, escrito
    assert (
        _fila(importar_csv(["nombre;perfil", "x-01;minimo"], perfiles=perfiles), 2).cfg.memoria_mib
        == 512
    )


def test_un_perfil_del_usuario_tambien_se_elige_por_nombre():
    mio = _perfil_usuario("Mi Perfil Ñ")
    perfiles = [*perfiles_fabrica(), mio]
    f = _fila(importar_csv(["nombre;perfil", "x-01;mi perfil n"], perfiles=perfiles), 2)
    assert f.estado == EstadoFila.CORRECTA and f.cfg.discos[0].tamano_gib == 10


def test_un_perfil_inexistente_es_v_m06_con_los_disponibles_y_no_se_usa_otro():
    r = importar_csv(["nombre;perfil", "x-01;no-existe"])
    f = _fila(r, 2)
    (p,) = _problemas(r, 2, "V-M06")
    assert p.severidad == Severidad.ERROR and p.columna == "perfil" and p.valor == "no-existe"
    assert p.params["nombre"] == "no-existe" and p.params["motivo"] == "no_existe"
    assert 1 <= len(p.params["disponibles"].split(", ")) <= 5
    assert f.cfg is None and f.estado == EstadoFila.CON_ERROR


def test_un_perfil_ambiguo_pide_el_nombre_exacto_o_el_id():
    """CA-C13.4."""
    a = _perfil_usuario("Duplicado")
    b = PerfilMaquina(
        "d" * 32,
        "duplicado",
        "",
        OrigenPerfil.USUARIO,
        ConfigPerfil(cores=7, discos=(DiscoPerfil(1),), redes=(RedPerfil(),)),
    )
    perfiles = [*perfiles_fabrica(), a, b]
    r = importar_csv(["nombre;perfil", "x-01;DUPLICADO", f"x-02;{b.id}"], perfiles=perfiles)
    assert _problemas(r, 2, "V-M06")[0].params["motivo"] == "ambiguo" and _fila(r, 2).cfg is None
    assert (
        _fila(r, 3).estado == EstadoFila.CORRECTA and _fila(r, 3).cfg.cores == 7
    )  # el id desambigua


def test_el_texto_de_un_perfil_con_formula_se_muestra_recortado_y_no_se_evalua():
    r = importar_csv(["nombre;perfil", 'x-01;"=HYPERLINK(""http://x"",""y"")"'])
    (p,) = _problemas(r, 2, "V-M06")
    assert p.valor.startswith("=HYPERLINK") and len(p.valor) <= 40


# --- Nombre: V-01, V-M07, V-M10, V-M11 ------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre", ["mi servidor", "-web", "web_01", "a" * 64, "web.", "ñandú", "a b"]
)
def test_nombres_que_no_son_dns_validos_son_v_01(nombre):
    r = importar_csv(["nombre", nombre])
    assert _problemas(r, 2, "V-01") and _fila(r, 2).estado == EstadoFila.CON_ERROR
    assert _problemas(r, 2, "V-01")[0].columna == "nombre"


def test_nombres_duplicados_sin_distinguir_mayusculas_marcan_todas_las_filas_implicadas():
    """CA-C05.3 / V-M10: «Las filas 3 y 9 tienen el mismo nombre»."""
    lineas = ["nombre"] + [
        "web-01" if i == 3 else "WEB-01" if i == 9 else f"otro-{i}" for i in range(2, 12)
    ]
    r = importar_csv(lineas)
    for n in (3, 9):
        (p,) = _problemas(r, n, "V-M10")
        assert (
            p.severidad == Severidad.ERROR and p.params["filas"] == "3, 9" and p.columna == "nombre"
        )
        assert _fila(r, n).estado == EstadoFila.CON_ERROR
    assert all(not _problemas(r, n, "V-M10") for n in range(2, 12) if n not in (3, 9))


def test_tres_filas_con_el_mismo_nombre_se_marcan_las_tres():
    r = importar_csv(["nombre", "a", "A", "a"])
    assert [bool(_problemas(r, n, "V-M10")) for n in (2, 3, 4)] == [True, True, True]


def test_vmid_repetido_marca_todas_las_filas_aunque_los_nombres_sean_distintos():
    """CA-C05.4."""
    r = importar_csv(["nombre;vmid", "a-01;150", "a-02;151", "a-03;150", "a-04;"])
    for n in (2, 4):
        (p,) = _problemas(r, n, "V-M10")
        assert p.columna == "vmid" and p.params["filas"] == "2, 4"
    assert not _problemas(r, 3, "V-M10") and not _problemas(r, 5, "V-M10")


def test_dos_filas_sin_vmid_no_cuentan_como_repetidas():
    assert all(
        not _problemas(importar_csv(["nombre;vmid", "a;", "b;"]), n, "V-M10") for n in (2, 3)
    )


def test_una_fila_ejemplo_lleva_el_aviso_v_m11_y_no_bloquea():
    """CA-C10.3."""
    r = importar_csv(["nombre", "ejemplo-01", "EJEMPLO-02", "real-01"])
    for n in (2, 3):
        (p,) = _problemas(r, n, "V-M11")
        assert p.severidad == Severidad.AVISO
        assert _fila(r, n).estado == EstadoFila.CON_AVISO
    assert not _problemas(r, 4, "V-M11") and r.numeros_validos == (2, 3, 4)


def test_el_nombre_con_caracteres_de_control_se_sanea_en_la_fila_pero_no_se_acepta_como_dns():
    f = _fila(importar_csv(["nombre", "we\x07b‮-01"]), 2)
    assert "\x07" not in f.nombre and "‮" not in f.nombre


# --- vmid / nodo (RF-C09) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vmid", "ok"),
    [
        ("100", True),
        ("250", True),
        ("105.0", True),
        ("999999999", True),
        ("99", False),
        ("0", False),
        ("1000000000", False),
    ],
)
def test_vmid_fuera_de_100_a_999999999_es_v_02(vmid, ok):
    """CA-C09.4."""
    r = importar_csv(["nombre;vmid", f"a-01;{vmid}"])
    assert bool(_problemas(r, 2, "V-02")) is (not ok)
    if ok:
        assert _fila(r, 2).vmid == int(float(vmid))
    else:
        assert _problemas(r, 2, "V-02")[0].columna == "vmid"


def test_vmid_que_no_es_un_numero_o_ambiguo():
    r = importar_csv(["nombre;vmid", "a-01;abc", "a-02;1.000", "a-03;12,5", "a-04;-5"])
    assert _problemas(r, 2, "E-M11.no_numero") and _problemas(r, 3, "V-M08")
    assert _problemas(r, 4, "E-M11.no_entero") and _problemas(r, 5, "E-M11.no_numero")
    assert all(_fila(r, n).estado == EstadoFila.CON_ERROR for n in (2, 3, 4, 5))


def test_sin_inventario_el_nodo_no_se_valida_hasta_el_plan():
    f = _fila(importar_csv(["nombre;nodo", "a-01;lo-que-sea"]), 2)
    assert f.estado == EstadoFila.CORRECTA and f.nodo == "lo-que-sea"


def test_nodo_en_linea_es_correcto_inexistente_o_sin_conexion_es_v_04():
    """CA-C09.2."""
    r = importar_csv(
        ["nombre;nodo", "a-01;pve2", "a-02;pve3", "a-03;fantasma", "a-04;"],
        inv=_inv(),
        nodo_referencia="pve1",
    )
    assert _fila(r, 2).estado == EstadoFila.CORRECTA
    (sin,) = _problemas(r, 3, "V-04")
    assert sin.params["motivo"] == "sin_conexion" and sin.columna == "nodo"
    (no_existe,) = _problemas(r, 4, "V-04")
    assert no_existe.params["motivo"] == "no_existe"
    assert _fila(r, 5).estado == EstadoFila.CORRECTA


def test_en_un_servidor_individual_la_columna_nodo_es_opcional():
    """CA-C09.1: vacía = el único nodo; el correcto = ok; otro = V-04."""
    solo = inventario((nodo("pve1"),), es_cluster=False)
    r = importar_csv(
        ["nombre;nodo", "a-01;", "a-02;pve1", "a-03;pve9"], inv=solo, nodo_referencia="pve1"
    )
    assert _fila(r, 2).estado == EstadoFila.CORRECTA and _fila(r, 3).estado == EstadoFila.CORRECTA
    assert _problemas(r, 4, "V-04")


def test_vmid_y_nodo_se_aceptan_igual_con_cualquier_modo():
    """CA-C09.6: lo que se importa no depende del modo básico/avanzado (la función no lo recibe)."""
    f = _fila(importar_csv(["nombre;vmid;nodo", "a-01;300;pve2"], inv=_inv()), 2)
    assert (f.vmid, f.nodo) == (300, "pve2") and f.cfg.vmid == 300 and f.cfg.nodo == "pve2"


# --- Rangos de las reglas de M1 (CA-C04.8) --------------------------------------------------------


@pytest.mark.parametrize(
    ("columna", "valor", "regla"),
    [
        ("cpu", "0", "V-05"), ("cpu", "129", "V-05"), ("cpu", "500", "V-05"), ("sockets", "0", "V-05"), ("sockets", "5", "V-05"),  # noqa: E501
        ("memoria", "4 MiB", "V-06"), ("memoria", "0", "V-06"), ("memoria", "15 MiB", "V-06"),
        ("disco", "65537", "V-08"), ("vlan", "0", "V-15"), ("vlan", "4095", "V-15"), ("vlan", "5000", "V-15"),  # noqa: E501
        ("tipo_cpu", "x86 64", "V-22"), ("tipo_cpu", "a,b", "V-22"),
    ],
)  # fmt: skip
def test_valores_fuera_de_rango_dan_el_error_de_la_regla_en_esa_fila_y_columna(
    columna, valor, regla
):
    r = importar_csv([f"nombre;{columna}", f"a-01;{valor}"])
    problemas = _problemas(r, 2, regla)
    assert problemas, _fila(r, 2).problemas
    assert problemas[0].columna == columna and problemas[0].severidad == Severidad.ERROR
    assert _fila(r, 2).estado == EstadoFila.CON_ERROR


@pytest.mark.parametrize(
    ("columna", "valor"),
    [
        ("cpu", "1"),
        ("cpu", "128"),
        ("sockets", "4"),
        ("memoria", "16 MiB"),
        ("disco", "1"),
        ("vlan", "1"),
        ("vlan", "4094"),
        ("tipo_cpu", "host"),
    ],
)
def test_los_valores_en_el_limite_son_validos(columna, valor):
    assert (
        _fila(importar_csv([f"nombre;{columna}", f"a-01;{valor}"]), 2).estado
        != EstadoFila.CON_ERROR
    )


def test_vlan_0_y_4095_de_la_tabla_de_casos_limite():
    """§13.11."""
    r = importar_csv(["nombre;vlan", "a-01;0", "a-02;4095", "a-03;4094"])
    assert [_fila(r, n).estado for n in (2, 3, 4)] == [
        EstadoFila.CON_ERROR,
        EstadoFila.CON_ERROR,
        EstadoFila.CORRECTA,
    ]


def test_valores_de_la_tabla_de_unidades_a_traves_de_la_interpretacion():
    """§13.11: memoria y disco en su contexto completo."""
    caso = {
        "4": 4096, "4 GiB": 4096, "4G": 4096, "4096 MiB": 4096, "1,5": 1536,
    }  # fmt: skip
    for i, (texto, mib) in enumerate(caso.items()):
        r = importar_csv(["nombre;memoria", f'm-{i:02d};"{texto}"'])
        assert _fila(r, 2).cfg.memoria_mib == mib, texto
    r = importar_csv(
        [
            "nombre;memoria",
            'a-01;"0,3"',
            'a-02;"1.000"',
            'a-03;"1.024,5"',
            "a-04;abc",
            "a-05;-1",
            "a-06;1e3",
        ]
    )
    assert (
        _problemas(r, 2, "E-M11.mib_no_entero")
        and _problemas(r, 3, "V-M08")
        and _problemas(r, 4, "V-M08")
    )
    assert (
        _problemas(r, 5, "E-M11.no_numero")
        and _problemas(r, 6, "E-M11.no_numero")
        and _problemas(r, 7, "E-M11.no_numero")
    )
    assert all(
        _fila(r, n).cfg is None for n in range(2, 8)
    )  # un error de valor impide construir la configuración


def test_cpu_2_0_vale_y_2_5_no():
    r = importar_csv(["nombre;cpu", "a-01;2.0", "a-02;2.5", "a-03;0", "a-04;129"])
    assert _fila(r, 2).cfg.cores == 2
    assert (
        _problemas(r, 3, "E-M11.no_entero")
        and _problemas(r, 4, "V-05")
        and _problemas(r, 5, "V-05")
    )


# --- V-M09: memoria desmesurada (CA-C04.9) --------------------------------------------------------


def test_memoria_4096_sin_unidad_es_4096_gib_y_avisa_de_la_confusion_mib_gib():
    r = importar_csv(["nombre;memoria", "a-01;4096", "a-02;1024", "a-03;1025", "a-04;4096 MiB"])
    (p,) = _problemas(r, 2, "V-M09")
    assert p.severidad == Severidad.AVISO and p.params["gib"] == "4096" and p.columna == "memoria"
    assert _fila(r, 2).estado == EstadoFila.CON_AVISO and _fila(r, 2).cfg.memoria_mib == 4096 * 1024
    assert not _problemas(r, 3, "V-M09")  # justo 1024 GiB no avisa
    assert _problemas(r, 4, "V-M09")
    assert not _problemas(r, 5, "V-M09")


def test_con_inventario_tambien_avisa_si_supera_al_mayor_nodo_conocido():
    r = importar_csv(
        ["nombre;memoria", "a-01;100", "a-02;64", "a-03;32"], inv=_inv(), nodo_referencia="pve1"
    )
    (p,) = _problemas(r, 2, "V-M09")  # pve1 tiene 64 GiB: 100 GiB no cabe en ningún nodo
    assert p.params["maximo_nodo_mib"] == str(64 * 1024)
    assert not _problemas(r, 3, "V-M09") and not _problemas(r, 4, "V-M09")


def test_una_fila_con_aviso_v_m09_se_puede_importar():
    r = importar_csv(["nombre;memoria", "a-01;4096"])
    assert r.numeros_validos == (2,) and len(filas_lote(r, [2])) == 1


# --- Avisos de unidad: una vez por columna y archivo (D-T9, CA-C05.6) -----------------------------


def test_los_avisos_de_unidad_y_decimal_salen_una_vez_por_columna_y_no_por_fila():
    lineas = (
        ["nombre;memoria;disco"]
        + [f"m-{i:02d};{4 + i};{20 + i}" for i in range(20)]
        + ['x-1;"1,5";"40,0"', "x-2;4 GB;10 GB"]
    )
    r = importar_csv(lineas)
    por_codigo: dict = {}
    for a in r.avisos:
        por_codigo.setdefault(a.codigo, []).append(a.params["columna"])
    assert por_codigo[Aviso.GIB_ASUMIDO] == ["memoria", "disco"]
    assert por_codigo[Aviso.DECIMAL_COMA] == ["memoria", "disco"]
    assert por_codigo[Aviso.GB_COMO_GIB] == ["memoria", "disco"]
    assert all(not _fila(r, n).problemas for n in range(2, 22))  # nada por fila


def test_con_unidad_explicita_no_hay_aviso_de_gib_asumido():
    r = importar_csv(["nombre;memoria;disco", "a-01;4 GiB;20 GiB"])
    assert r.avisos == ()


def test_un_alias_con_unidad_en_el_encabezado_fija_la_unidad_y_no_avisa():
    """Decisión fijada: ``memoria_mib`` fija la unidad."""
    r = importar_csv(["nombre;memoria_mib", "a-01;4096", "a-02;512"])
    assert [_fila(r, n).cfg.memoria_mib for n in (2, 3)] == [4096, 512]
    assert not [a for a in r.avisos if a.codigo == Aviso.GIB_ASUMIDO]
    r2 = importar_csv(["nombre;memoria_gib", "a-01;4"])
    assert _fila(r2, 2).cfg.memoria_mib == 4096 and not [
        a for a in r2.avisos if a.codigo == Aviso.GIB_ASUMIDO
    ]


def test_avisos_de_columnas_no_usadas_y_credenciales_en_el_resultado():
    r = importar_csv(["nombre;xyz;token;cpu", "a-01;v;SECRETO;3"])
    codigos = [a.codigo for a in r.avisos]
    assert (
        codigos.count(Aviso.COLUMNA_NO_USADA) == 1 and codigos.count(Aviso.CREDENCIAL_IGNORADA) == 1
    )


# --- Credenciales y desconocidas: nunca se leen (CA-C03.3, CA-X04.2) ------------------------------


def test_las_celdas_de_credenciales_y_de_columnas_desconocidas_nunca_aparecen_en_el_resultado():
    lineas = [
        "nombre;token;Password;comentario;cpu",
        f"a-01;{CENT_TOKEN};{CENT_PASSWORD};VALOR-PRIVADO-XYZ;3",
    ]
    r = importar_csv(lineas)
    texto = volcar(r)
    assert (
        CENT_TOKEN not in texto and CENT_PASSWORD not in texto and "VALOR-PRIVADO-XYZ" not in texto
    )
    assert _fila(r, 2).cfg.cores == 3 and "token" not in _fila(r, 2).originales


def test_una_celda_de_credencial_con_formato_invalido_no_produce_error_de_fila():
    r = importar_csv(["nombre;cpu;ticket", "a-01;2;=CMD()+@@"])
    assert _fila(r, 2).estado == EstadoFila.CORRECTA


# --- Disparadores y texto no confiable (CA-C11.5, CA-C11.10, INV-M4, §13.13) ----------------------


def test_las_celdas_con_formulas_se_tratan_como_texto_y_nunca_se_evaluan():
    tabla = tabla_csv(((DATOS_MVP3 / "formulas.csv").read_text("utf-8-sig")).splitlines())
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    f2, f3, f4, f5 = r.filas
    assert _problemas(r, f2.numero, "V-01")  # nombre `=HYPERLINK(...)` no es un nombre DNS
    assert (
        f2.nombre.startswith("=HYPERLINK") and f2.cfg is not None
    )  # el texto se conserva tal cual
    assert _problemas(r, f3.numero, "V-M06") and f3.cfg is None  # perfil `=cmd|...`
    assert f4.estado == EstadoFila.CORRECTA  # columna desconocida con `-1`: ni se mira
    assert _problemas(r, f5.numero, "V-01")
    assert len([a for a in r.avisos if a.codigo == Aviso.COLUMNA_NO_USADA]) == 1


@pytest.mark.parametrize(
    "valor",
    [
        '=HYPERLINK("http://x","y")',
        "@SUM(1)",
        "+1",
        "-1",
        "\t=1",
        " =1",
        "=1+1",
        "+cmd|' /C calc'!A0",
    ],
)
def test_nombre_perfil_y_columnas_con_disparadores_no_rompen_ni_se_ejecutan(valor):
    celda = '"' + valor.replace('"', '""') + '"'
    r = importar_csv(
        [
            "nombre;perfil;cpu;memoria;disco;almacenamiento;red;nodo;columna_rara",
            f"{celda};{celda};{celda};{celda};{celda};{celda};{celda};{celda};{celda}",
        ]
    )
    f = _fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR and f.problemas
    assert all(
        len(p.valor) <= 40 and "\t" not in p.valor and "\n" not in p.valor for p in f.problemas
    )


def test_la_apostrofe_inicial_de_una_exportacion_anterior_se_quita_una_sola_vez():
    """CA-C11.5."""
    r = importar_csv(["nombre;cpu", "'=mi-nombre;'+2", "''=otra;3", "'normal;2"])
    assert _fila(r, 2).nombre == "=mi-nombre"
    assert _problemas(r, 2, "E-M11.no_numero")  # `'+2` pierde la apóstrofe y `+2` no es un número
    assert _fila(r, 3).nombre == "''=otra"  # no hay disparador tras la 1.ª apóstrofe: tal cual
    assert _fila(r, 4).nombre == "'normal"  # sin disparador detrás: el texto queda tal cual
    assert _problemas(r, 4, "V-01")  # y suele fallar V-01 con un mensaje claro


def test_el_valor_mostrado_se_recorta_a_40_y_no_lleva_control_ni_direccion_de_texto():
    """CA-C05.1."""
    largo = "x" * 120
    r = importar_csv(["nombre;cpu", f'a-01;"{largo}"', 'a-02;"a\x07b‮c"'])
    (p,) = [p for p in _fila(r, 2).problemas if p.regla == "E-M11.no_numero"]
    assert len(p.valor) <= 40
    (q,) = [p for p in _fila(r, 3).problemas if p.regla == "E-M11.no_numero"]
    assert q.valor == "abc"


# --- Mensajes: fila, columna, orden y límite (CA-C05.1, CA-C05.7) ---------------------------------


def test_cada_problema_lleva_fila_de_excel_columna_del_encabezado_original_y_valor():
    r = importar_csv(
        ["Nombre;Núcleos;Memoria (GiB)", "web-01;2;abc"], alias_extra={"memoria (gib)": "memoria"}
    )
    (p,) = [p for p in _fila(r, 2).problemas if p.severidad == Severidad.ERROR]
    assert (p.fila, p.columna, p.regla, p.valor) == (2, "Memoria (GiB)", "E-M11.no_numero", "abc")
    assert "ejemplo" in p.params


def test_los_problemas_se_ordenan_por_posicion_de_columna_y_se_limitan_a_cinco_sin_ocultar_errores():  # noqa: E501
    """CA-C05.7: hasta 5 por fila y luego «y N más»."""
    lineas = [
        "nombre;tipo_cpu;firmware;cpu;memoria;disco;vlan;modelo_red;sockets",
        "mal nombre;x y;linux;0;abc;abc;0;rtl;9",
    ]
    r = importar_csv(lineas)
    f = _fila(r, 2)
    assert len(f.problemas) == 5 and f.problemas_omitidos >= 2
    posiciones = [
        [
            "nombre",
            "tipo_cpu",
            "firmware",
            "cpu",
            "memoria",
            "disco",
            "vlan",
            "modelo_red",
            "sockets",
        ].index(p.columna)
        for p in f.problemas
        if p.columna
    ]
    assert posiciones == sorted(posiciones)
    assert all(
        p.severidad == Severidad.ERROR for p in f.problemas
    )  # los errores no se ocultan tras avisos
    assert f.estado == EstadoFila.CON_ERROR


def test_un_aviso_no_desplaza_a_un_error_cuando_hay_mas_de_cinco_problemas():
    lineas = ["nombre;cpu;sockets;memoria;disco;vlan", "ejemplo-x;0;9;4096;abc;0"]
    f = _fila(importar_csv(lineas), 2)
    # 4 errores (cpu, sockets, disco, vlan) + 2 avisos (V-M11, V-M09): salen los 4 errores y 1 aviso.  # noqa: E501
    assert len(f.problemas) == 5 and f.problemas_omitidos == 1
    assert sum(p.severidad == Severidad.ERROR for p in f.problemas) == 4
    assert f.estado == EstadoFila.CON_ERROR


def test_un_csv_de_100_filas_todas_con_error_se_interpreta_completo():
    """CA-C05.10."""
    r = importar_csv(["nombre;cpu"] + [f"mal nombre {i};0" for i in range(100)])
    assert len(r.filas) == 100 and all(f.estado == EstadoFila.CON_ERROR for f in r.filas)
    assert r.numeros_validos == () and all(1 <= len(f.problemas) <= 5 for f in r.filas)


def test_los_originales_conservan_el_texto_de_la_celda_para_el_detalle():
    """CA-C06.4: «Valor del archivo: «4096»»."""
    f = _fila(importar_csv(["nombre;memoria;cpu", "a-01;  4096 ;"]), 2)
    assert f.originales == {"nombre": "a-01", "memoria": "4096"}
    assert f.cfg.memoria_mib == 4096 * 1024


def test_estado_de_fila():
    r = importar_csv(["nombre;memoria", "ok-01;2", "ejemplo-01;2", "mal nombre;2"])
    assert [_fila(r, n).estado for n in (2, 3, 4)] == [
        EstadoFila.CORRECTA,
        EstadoFila.CON_AVISO,
        EstadoFila.CON_ERROR,
    ]
    assert r.numeros_validos == (2, 3)


# --- Discos y redes (CA-C03.7, CA-C03.8) ----------------------------------------------------------


def _sin_disco_ni_red() -> PerfilMaquina:
    return PerfilMaquina(
        "e" * 32,
        "Vacío",
        "",
        OrigenPerfil.USUARIO,
        ConfigPerfil(con_disco=False, discos=(), redes=()),
    )


def test_disco_0_o_ninguno_crea_la_fila_sin_disco():
    r = importar_csv(["nombre;disco", "a-01;0", "a-02;ninguno", "a-03;Sin disco"])
    for n in (2, 3, 4):
        c = _fila(r, n).cfg
        assert c.con_disco is False and c.discos == [] and _fila(r, n).estado == EstadoFila.CORRECTA


def test_disco_en_un_perfil_sin_disco_crea_uno_con_los_valores_por_defecto():
    base = _sin_disco_ni_red()
    r = importar_csv(["nombre;disco;almacenamiento", "a-01;50;rapido"], base=base, perfiles=[base])
    c = _fila(r, 2).cfg
    assert c.con_disco and c.discos == [
        Disco("rapido", 50, Bus.SCSI, discard=True, ssd=True, iothread=True)
    ]


def test_disco_adicional_hereda_el_storage_del_primero_y_se_puede_dar_otro():
    r = importar_csv(
        ["nombre;disco;almacenamiento;disco2;disco3;almacenamiento3", "a-01;10;rapido;20;30;datos"]
    )
    c = _fila(r, 2).cfg
    assert [(d.storage, d.tamano_gib) for d in c.discos] == [
        ("rapido", 10),
        ("rapido", 20),
        ("datos", 30),
    ]


def test_hasta_8_discos():
    cab = "nombre;disco;" + ";".join(f"disco{n}" for n in range(2, 9))
    r = importar_csv([cab, "a-01;" + ";".join(str(n) for n in range(1, 9))])
    assert [d.tamano_gib for d in _fila(r, 2).cfg.discos] == list(range(1, 9))


def test_un_disco_adicional_en_cero_no_existe():
    r = importar_csv(["nombre;disco;disco2", "a-01;10;0"])
    assert [d.tamano_gib for d in _fila(r, 2).cfg.discos] == [10]


def test_storage_sin_tamano_para_un_disco_que_no_existe_es_error():
    r = importar_csv(["nombre;almacenamiento2", "a-01;datos"])
    assert _fila(r, 2).estado == EstadoFila.CON_ERROR and _fila(r, 2).cfg is None


def test_sin_disco_principal_no_puede_haber_otros_discos_ni_storage():
    r = importar_csv(["nombre;disco;almacenamiento;disco2", "a-01;0;datos;10"])
    assert _fila(r, 2).estado == EstadoFila.CON_ERROR


def test_red_y_vlan_crean_la_red_si_el_perfil_no_tiene():
    base = _sin_disco_ni_red()
    r = importar_csv(["nombre;red;vlan", "a-01;vmbr1;20"], base=base, perfiles=[base])
    assert _fila(r, 2).cfg.redes == [InterfazRed("vmbr1", ModeloRed.VIRTIO, 20)]


def test_modelo_de_red_y_firmware_invalidos_dan_el_error_con_los_valores_validos():
    r = importar_csv(["nombre;modelo_red;firmware", "a-01;rtl;legacy"])
    problemas = {p.columna: p for p in _fila(r, 2).problemas}
    assert (
        problemas["modelo_red"].regla == "E-M11.valor_no_admitido"
        and "virtio" in problemas["modelo_red"].params["validos"]
    )
    assert (
        problemas["firmware"].regla == "E-M11.valor_no_admitido"
        and "ovmf" in problemas["firmware"].params["validos"]
    )


# --- Capa 2 de la vista previa (CA-C06.10, CA-C07.6) ----------------------------------------------


def test_sin_inventario_solo_hay_capa_1_aunque_el_storage_no_exista():
    r = importar_csv(["nombre;almacenamiento;red", "a-01;no-existe;vmbr99"])
    assert r.con_inventario is False and _fila(r, 2).estado == EstadoFila.CORRECTA


def test_con_nodo_fijo_storage_y_bridge_se_validan_en_ese_nodo():
    r = importar_csv(
        [
            "nombre;nodo;almacenamiento;red",
            "a-01;pve1;rapido;vmbr1",
            "a-02;pve2;rapido;vmbr1",
            "a-03;pve2;datos;vmbr0",
        ],
        inv=_inv(),
    )
    assert _fila(r, 2).estado == EstadoFila.CORRECTA
    f3 = _fila(r, 3)
    assert {p.regla for p in f3.problemas} >= {"V-17", "V-16"}
    assert {p.columna for p in f3.problemas if p.regla in {"V-17", "V-16"}} == {
        "almacenamiento",
        "red",
    }
    assert _fila(r, 4).estado == EstadoFila.CORRECTA


def test_sin_nodo_la_fila_debe_caber_en_algun_nodo_elegible():
    """Automático: ``nodos_elegibles`` vacío → error de fila con los motivos (V-L11)."""
    r = importar_csv(
        ["nombre;almacenamiento", "a-01;rapido", "a-02;no-existe-en-ningun-nodo"],
        inv=_inv(),
        nodo_referencia="pve1",
    )
    assert _fila(r, 2).estado == EstadoFila.CORRECTA  # «rapido» existe en pve1
    (p,) = _problemas(r, 3, "V-L11")
    assert (
        p.severidad == Severidad.ERROR
        and p.columna is None
        and "no-existe" not in p.params.get("n", "")
    )
    assert p.params["motivos"]


def test_el_nombre_que_ya_existe_en_el_servidor_se_deja_para_el_plan():
    """V-L06 necesita GET: no es de la vista previa."""
    r = importar_csv(["nombre", "ya-existe"], inv=_inv(), nodo_referencia="pve1")
    assert _fila(r, 2).estado == EstadoFila.CORRECTA


def test_pista_de_storage_que_no_existe_en_el_nodo_es_un_aviso_una_vez_por_fila():
    """CA-C13.6."""
    base = PerfilMaquina(
        "f" * 32,
        "Con pista",
        "",
        OrigenPerfil.USUARIO,
        ConfigPerfil(
            discos=(
                DiscoPerfil(10, storage_preferido="ssd-fantasma"),
                DiscoPerfil(5, storage_preferido="ssd-fantasma"),
            ),
            redes=(RedPerfil(bridge_preferido="br-fantasma"),),
        ),
    )
    r = importar_csv(
        ["nombre", "a-01"], inv=_inv(), nodo_referencia="pve1", base=base, perfiles=[base]
    )
    pistas = [p for p in _fila(r, 2).problemas if p.regla.startswith("pista.")]
    assert sorted(p.regla for p in pistas) == ["pista.bridge", "pista.storage"]
    assert all(p.severidad == Severidad.AVISO for p in pistas)
    assert _fila(r, 2).estado == EstadoFila.CON_AVISO
    assert _fila(r, 2).cfg.discos[0].storage == "datos"  # se usó el storage por defecto, con aviso


def test_si_el_csv_trae_la_columna_la_pista_del_perfil_no_da_aviso():
    base = PerfilMaquina(
        "f" * 32,
        "Con pista",
        "",
        OrigenPerfil.USUARIO,
        ConfigPerfil(
            discos=(DiscoPerfil(10, storage_preferido="ssd-fantasma"),),
            redes=(RedPerfil(bridge_preferido="br-fantasma"),),
        ),
    )
    r = importar_csv(
        ["nombre;almacenamiento;red", "a-01;rapido;vmbr1"],
        inv=_inv(),
        nodo_referencia="pve1",
        base=base,
        perfiles=[base],
    )
    assert not [p for p in _fila(r, 2).problemas if p.regla.startswith("pista.")]


def test_sin_inventario_la_pista_queda_como_valor_sin_aviso():
    base = PerfilMaquina(
        "f" * 32,
        "Con pista",
        "",
        OrigenPerfil.USUARIO,
        ConfigPerfil(
            discos=(DiscoPerfil(10, storage_preferido="mi-storage"),),
            redes=(RedPerfil(bridge_preferido="mi-bridge"),),
        ),
    )
    f = _fila(importar_csv(["nombre", "a-01"], base=base, perfiles=[base]), 2)
    assert (
        f.cfg.discos[0].storage == "mi-storage"
        and f.cfg.redes[0].bridge == "mi-bridge"
        and not f.problemas
    )


# --- Encabezado y estructura ----------------------------------------------------------------------


def test_sin_columna_nombre_es_e_m10_y_no_se_importa_nada():
    with pytest.raises(ErrorProxLaunch) as exc:
        importar_csv(["cpu;memoria", "2;4"])
    assert (
        exc.value.codigo == CodigoError.CSV_COLUMNAS
        and exc.value.params["motivo"] == "falta_nombre"
    )


def test_datos_en_una_columna_sin_encabezado_es_e_m10_vacia():
    """CA-C03.4."""
    with pytest.raises(ErrorProxLaunch) as exc:
        importar_csv(["nombre;cpu", "a-01;2;extra-sin-encabezado"])
    assert exc.value.params["motivo"] == "vacia" and exc.value.params["posiciones"] == "3"


def test_alias_del_idioma_activo_via_alias_extra():
    r = importar_csv(["nombre;nucleos_es", "a-01;3"], alias_extra={"nucleos_es": "cpu"})
    assert _fila(r, 2).cfg.cores == 3


def test_los_alias_en_ingles_funcionan():
    r = importar_csv(["name;cores;ram;node", "a-01;3;8;pve1"])
    f = _fila(r, 2)
    assert (f.cfg.cores, f.cfg.memoria_mib, f.nodo) == (3, 8192, "pve1")


def test_la_numeracion_de_filas_es_la_de_excel_con_lineas_en_blanco():
    r = importar_csv(["nombre", "a-01", "", "a-02"])
    assert [f.numero for f in r.filas] == [2, 4]


# --- Pureza y determinismo (CA-C05.8, RNF-M07) ----------------------------------------------------


def test_mismo_archivo_y_entorno_mismos_resultados_y_mensajes():
    lineas = [
        ENC,
        "ejemplo-01;;0;4096;abc;;;;;",
        "web-01;servidor-mediano;;8;100;datos;vmbr0;;pve1;150",
        "web-01;;2;;;;;;;",
    ]
    inv = _inv()
    assert importar_csv(lineas, inv=inv, nodo_referencia="pve1") == importar_csv(
        lineas, inv=inv, nodo_referencia="pve1"
    )


def test_interpretar_no_modifica_los_perfiles_ni_el_inventario():
    perfiles = tuple(perfiles_fabrica())
    inv = _inv()
    copia_inv = copy.deepcopy(inv)
    importar_csv(
        ["nombre;cpu;memoria;disco", "a-01;4;8;100", "a-02;1;1;5"],
        inv=inv,
        nodo_referencia="pve1",
        perfiles=perfiles,
    )
    assert tuple(perfiles_fabrica()) == perfiles and inv == copia_inv


def test_no_hay_red_ni_estado_oculto_entre_llamadas():
    """Dos importaciones seguidas no comparten estado (avisos de unidad por archivo)."""
    a = importar_csv(["nombre;memoria", "a-01;4"])
    b = importar_csv(["nombre;memoria", "a-01;4 GiB"])
    assert a.avisos and not b.avisos


# --- filas_lote -----------------------------------------------------------------------------------


def test_filas_lote_convierte_las_filas_elegidas_en_filalote_en_orden_de_archivo():
    r = importar_csv(
        ["nombre;cpu;vmid;nodo", "a-01;1;150;pve2", "a-02;2;;", "a-03;3;;pve1"],
        inv=_inv(),
        nodo_referencia="pve1",
    )
    filas = filas_lote(r, [4, 2])  # el orden pedido no importa: manda el del archivo
    assert [f.nombre for f in filas] == ["a-01", "a-03"]
    assert all(isinstance(f, FilaLote) for f in filas)
    a01 = filas[0]
    assert (a01.vmid, a01.nodo, a01.origen, a01.cfg.cores) == (150, "pve2", 2, 1)
    assert (a01.cfg.nombre, a01.cfg.vmid, a01.cfg.nodo, a01.cfg.etiquetas) == (
        "a-01",
        150,
        "pve2",
        (),
    )
    a03 = filas[1]
    assert (a03.vmid, a03.nodo, a03.origen) == (None, "pve1", 4)


def test_filas_lote_entrega_copias_independientes_de_la_interpretacion():
    r = importar_csv(["nombre", "a-01"])
    (f,) = filas_lote(r, [2])
    f.cfg.cores = 99
    f.cfg.discos[0].tamano_gib = 99
    assert _fila(r, 2).cfg.cores == 2 and _fila(r, 2).cfg.discos[0].tamano_gib == 32
    (g,) = filas_lote(r, [2])
    assert g.cfg.cores == 2


def test_filas_lote_rechaza_filas_con_error_o_inexistentes():
    r = importar_csv(["nombre;cpu", "ok-01;2", "mal nombre;2", "ok-03;0"])
    with pytest.raises(ValueError):
        filas_lote(r, [2, 3])
    with pytest.raises(ValueError):
        filas_lote(r, [2, 4])
    with pytest.raises(ValueError):
        filas_lote(r, [99])
    with pytest.raises(ValueError):
        filas_lote(r, [1])  # el encabezado no es una fila de datos


def test_filas_lote_con_conjunto_vacio_devuelve_vacio():
    assert filas_lote(importar_csv(["nombre", "a-01"]), []) == ()


def test_numeros_validos_son_las_filas_importables():
    r = importar_csv(["nombre;cpu", "ok-01;2", "mal nombre;2", "ejemplo-03;1"])
    assert r.numeros_validos == (2, 4)
    assert len(filas_lote(r, r.numeros_validos)) == 2


def test_una_fila_con_aviso_de_perfil_ausente_no_construye_configuracion():
    """Una fila cuyo ``cfg`` es None nunca llega al lote (aunque otros problemas fueran avisos)."""
    r = importar_csv(["nombre;perfil", "a-01;no-existe"])
    assert _fila(r, 2).cfg is None and r.numeros_validos == ()
    assert isinstance(_fila(r, 2).cfg, ConfiguracionVM) is False
