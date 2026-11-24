"""Catálogo de textos de la fase D (0.9.0): cada regla V-D tiene su mensaje en español llano, sin
códigos crudos ni marcadores sin sustituir, y todo está en el catálogo traducible.

Derivadas de docs/requisitos/fase-d.md: CA-D7.1.1 y CA-D7.1.3 (existen los textos de cada V-D y
concepto, con parámetros nombrados), CA-D11.1 (cada V-D con su mensaje, sin secretos ni valores
del XML sin sanear), CA-D1.3.4 (V-D22 con la línea), CA-D1.9.2 (V-D31), CA-D1.11.3 (V-D35) y
RNF-D7 (todo texto nuevo en el catálogo). Los parámetros de cada caso son los que el núcleo
emite de verdad (se comprueba con el recorrido ``proponer`` y con los emisores de las demás
reglas); un texto cuyo marcador no coincide con el parámetro sale con un texto neutro («un dato»),
que estas pruebas tratan como marcador sin resolver.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

import proxlaunch
from nucleo.apoyo_fase_d_libvirt import (
    disco_xml,
    dominio_desde_texto,
    inventario_d,
    proponer_de,
    xml_minimo,
)
from proxlaunch.interfaz import textos_d
from proxlaunch.interfaz.ayuda import CAMPOS_AYUDA_FASE_D, ayuda
from proxlaunch.interfaz.textos import texto_error, texto_problema
from proxlaunch.interfaz.textos_d import (
    texto_comandos_obtener_xml,
    texto_concepto_fila,
    texto_error_d,
    texto_estado_fila,
    texto_estado_fila_simbolo,
    texto_problema_d,
)
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.libvirt.correspondencias import EstadoFila
from proxlaunch.nucleo.validacion import Problema, Severidad

RAIZ = Path(proxlaunch.__file__).parent
CATALOGO = RAIZ / "recursos" / "traducciones" / "proxlaunch_es.ts"
# Textos neutros que usa ``_Seguro`` cuando falta un dato: si salen, el marcador no coincide.
NEUTROS = ("un dato", "ese servidor", "ese elemento")
E, A = Severidad.ERROR, Severidad.AVISO


def sin_marcadores(texto: str | None, codigo: str = "") -> None:
    assert texto, codigo
    assert "{" not in texto and "}" not in texto, (codigo, texto)
    for neutro in NEUTROS:
        assert neutro not in texto, (codigo, texto)
    assert re.search(r"\bV-D\d\d", texto) is None, (codigo, texto)  # sin códigos crudos


# Un caso por regla V-D con los parámetros que el núcleo emite (ver validacion.py de cada módulo).
CASOS_V_D: list[tuple[str, dict[str, str], Severidad]] = [
    ("V-D01", {"version": "8.2.4", "minima": "8.4"}, E),
    ("V-D02", {"version": "8.4.1"}, A),
    ("V-D03", {"version": "8.2"}, A),
    ("V-D04", {"nodo": "pve1", "motivo": "sin_permiso"}, A),
    ("V-D05", {"nodo": "pve-arm", "variante": "9_2"}, A),
    ("V-D05", {"nodo": "pve-arm", "variante": "previa", "forzada": "1"}, A),
    ("V-D06", {"nodos_x86": "pve1", "nodos_arm": "pve-arm", "nodo": "pve1"}, E),
    ("V-D08", {"nodo": "pve-arm", "lista": "firmware, tipo_cpu",
               "cambios": "firmware:seabios>ovmf;tipo_cpu:x86-64-v3>host"}, A),
    ("V-D09", {"opcion": "e1000", "motivo": "red", "alternativa": "virtio"}, E),
    ("V-D20", {"motivo": "tamano", "tamano": "5000000"}, E),
    ("V-D23", {"tipo": "xen"}, E),
    ("V-D23b", {}, A),
    ("V-D24", {"arq_xml": "aarch64", "nodo": "pve1", "arq_nodo": "x86_64"}, E),
    ("V-D24.supuesta", {"nodo": "pve1", "arq_nodo": "x86_64"}, A),
    ("V-D24.i686", {"arq_xml": "i686", "nodo": "pve1"}, A),
    ("V-D25", {"disco": "vda"}, E),
    ("V-D25a", {"disco": "vda"}, A),
    ("V-D25c", {"archivo": "disco.raw"}, A),
    ("V-D26", {"archivo": "disco.qcow2", "n": "2"}, A),
    ("V-D27", {"disco": "2"}, E),
    ("V-D27", {"disco": "0", "sistema": "si"}, E),
    ("V-D27", {"disco": "0", "motivo": "sin_discos"}, E),
    ("V-D27b", {"necesario": "410 GiB", "libre": "300 GiB", "storage": "local-lvm"}, E),
    ("V-D29", {"disco": "vdb", "tipo": "network", "sistema": "no"}, A),
    ("V-D29", {"disco": "vda", "tipo": "network", "sistema": "si"}, E),
    ("V-D30", {}, A),
    ("V-D31", {"motivo": "nuevo", "windows": "si"}, A),
    ("V-D31", {"motivo": "v1.2", "windows": "no"}, A),
    ("V-D31", {"motivo": "passthrough", "windows": "no"}, A),
    ("V-D32", {"tarjeta": "0"}, A),
    ("V-D33", {"n": "3"}, E),
    ("V-D34", {"tarjeta": "0", "mac": "01:00:5e:00:00:01"}, E),
    ("V-D36", {"modelo": "rtl8139", "nuevo": "virtio"}, A),
    ("V-D37", {"origen": "EPYC-Milan", "cpu": "x86-64-v2-AES"}, A),
    ("V-D38", {"pista": "http://microsoft.com/win/7", "motivo": "windows_antiguo"}, A),
    ("V-D39", {}, A),
    ("V-D41", {"lista": "2×hostdev, sound"}, A),
    ("V-D41.desconocidos", {"lista": "holograma"}, A),
    ("V-D50", {"motivo": "sin_mapeos"}, A),
    ("V-D50", {"motivo": "no_leido", "tipo": "pci", "error": "permiso_insuficiente"}, A),
    ("V-D51", {"mapeo": "gpu-a2", "tipo": "pci"}, E),
    ("V-D51", {"mapeo": "mal id", "motivo": "formato", "tipo": "pci"}, E),
    ("V-D52", {"mapeo": "gpu-a2", "tipo": "pci", "nodos": "pve2, pve3"}, E),
    ("V-D53", {"mapeo": "gpu-a2", "nodo": "pve1", "mensaje": "Invalid configuration"}, E),
    ("V-D54", {"maquina": "q35"}, A),
    ("V-D55", {"mapeo": "gpu-a2"}, E),
    ("V-D55b", {"vga": "none"}, A),
    ("V-D56", {"mapeo": "gpu-a2", "nodo": "pve1", "k": "2", "n": "5"}, A),
    ("V-D57", {"mapeos": "gpu-a2, llave-hasp"}, A),
    ("V-D58", {"plantilla": "base"}, E),
    ("V-D58b", {"plantilla": "base", "lista": "gpu-a2"}, A),
    ("V-D59", {"tipo": "pci", "maximo": "16", "cantidad": "17"}, E),
    ("V-D59", {"tipo": "usb", "maximo": "5", "cantidad": "6"}, E),
    ("V-D60", {"version": "9.0", "mapeo": "gpu-a2"}, E),
    ("V-D61", {"cpu": "custom-a", "nodos": "pve2"}, E),
    ("V-D62", {"cpu": "custom-a", "nodos": "pve2"}, A),
    ("V-D63", {"privilegio": "Mapping.Use", "ruta": "/mapping/pci/gpu-a2", "mapeo": "gpu-a2", "tipo": "pci"}, E),  # noqa: E501
    ("V-D64", {"mapeo": "gpu-a2"}, E),
]  # fmt: skip


def _id(caso) -> str:
    return caso[0] + ("" if not caso[1].get("motivo") else f"-{caso[1]['motivo']}")


# --- CA-D7.1.1 y CA-D11.1: un mensaje para cada regla V-D -----------------------------------------


@pytest.mark.parametrize(
    "caso", CASOS_V_D, ids=[f"{i:02d}-{_id(c)}" for i, c in enumerate(CASOS_V_D)]
)
def test_ca_d11_1_cada_regla_v_d_tiene_su_mensaje_sin_marcadores_ni_codigos_crudos(caso):
    codigo, params, sev = caso
    p = Problema("campo", codigo, sev, params)
    texto = texto_problema(p)
    sin_marcadores(texto, codigo)
    assert texto == texto_problema_d(p)  # un único camino de textos para la fase D


def test_ca_d7_1_1_todas_las_reglas_v_d_del_requisito_estan_en_los_casos():
    esperadas = {
        "V-D01", "V-D02", "V-D03", "V-D04", "V-D05", "V-D06", "V-D07", "V-D08", "V-D09", "V-D20",
        "V-D21", "V-D22", "V-D23", "V-D23b", "V-D24", "V-D25", "V-D25a", "V-D25c", "V-D26",
        "V-D27", "V-D27b", "V-D28", "V-D29", "V-D30", "V-D31", "V-D32", "V-D33", "V-D34", "V-D35",
        "V-D36", "V-D37", "V-D38", "V-D39", "V-D40", "V-D41", "V-D50", "V-D51", "V-D52", "V-D53",
        "V-D54", "V-D55", "V-D55b", "V-D56", "V-D57", "V-D58", "V-D58b", "V-D59", "V-D60", "V-D61",
        "V-D62", "V-D63", "V-D64", "V-D70",
    }  # fmt: skip
    cubiertas = {c.split(".")[0] for c, _, _ in CASOS_V_D}
    # V-D07, V-D21, V-D22, V-D28, V-D35, V-D40 y V-D70 se prueban aparte (flujo, error o celda).
    assert esperadas - cubiertas == {"V-D07", "V-D21", "V-D22", "V-D28", "V-D35", "V-D40", "V-D70"}


def test_un_codigo_que_no_es_de_la_fase_d_no_lo_toma_texto_problema_d():
    assert texto_problema_d(Problema("c", "V-C10", E, {})) is None
    assert texto_problema_d(Problema("c", "V-01", E, {})) is None


# --- Las reglas que el núcleo emite desde la vista previa de libvirt (flujo real) -----------------


def _problemas_reales(xml: str, *, arch: str = "x86_64", nodo: str = "pve1", arqs=None):
    inv = inventario_d(arqs or {"pve1": Arquitectura.X86_64, "pve2": Arquitectura.X86_64})
    p = proponer_de(dominio_desde_texto(xml), inv=inv, nodo=nodo)
    return [f.problema for f in p.filas if f.problema is not None]


def _xml_con(devices: str = "", **kw) -> str:
    return xml_minimo(devices, **kw)


ESCENARIOS_REALES = {
    "linux": lambda: _problemas_reales(_xml_con(disco_xml() + "<hostdev/><sound/>")),
    "red-nat": lambda: _problemas_reales(
        _xml_con(disco_xml() + "<interface type='network'><source network='default'/></interface>")
    ),
    "red-direct": lambda: _problemas_reales(
        _xml_con(disco_xml() + "<interface type='direct'><source dev='eth0'/></interface>")
    ),
    "red-bridge-inexistente": lambda: _problemas_reales(
        _xml_con(disco_xml() + "<interface type='bridge'><source bridge='nada'/></interface>")
    ),
    "red-ovs": lambda: _problemas_reales(
        _xml_con(
            disco_xml() + "<interface type='bridge'><source bridge='vmbr0'/>"
            "<virtualport type='openvswitch'/><model type='rtl8139'/></interface>"
        )
    ),
    "tpm-uefi": lambda: _problemas_reales(
        _xml_con(disco_xml() + "<tpm><backend type='emulator' version='2.0'/></tpm>").replace(
            "<os>", "<os firmware='efi'>"
        )
    ),
    "xen": lambda: _problemas_reales(_xml_con(disco_xml(), tipo="xen")),
    "qemu": lambda: _problemas_reales(_xml_con(disco_xml(), tipo="qemu")),
    "ppc": lambda: _problemas_reales(_xml_con(disco_xml(), arch="ppc64le")),
    "sin-discos": lambda: _problemas_reales(_xml_con("")),
    "disco-red": lambda: _problemas_reales(
        _xml_con(
            "<disk type='network' device='disk'><source protocol='rbd' name='a/b'/>"
            "<target dev='vda' bus='virtio'/></disk>"
        )
    ),
    "cpu-custom": lambda: _problemas_reales(
        _xml_con(disco_xml(), extra="<cpu mode='custom'><model>EPYC</model></cpu>")
    ),
    "hyperv": lambda: _problemas_reales(
        _xml_con(disco_xml(), extra="<features><hyperv/></features>")
    ),
    "backing": lambda: _problemas_reales(
        _xml_con(disco_xml(extra="<backingStore><source file='/a'/></backingStore>"))
    ),
    "passwd": lambda: _problemas_reales(
        _xml_con(disco_xml() + "<graphics type='vnc' passwd='x'/>")
    ),
    "desconocido": lambda: _problemas_reales(_xml_con(disco_xml() + "<holograma/>")),
    "arm-sata": lambda: _problemas_reales(
        _xml_con(
            disco_xml(bus="sata")
            + "<interface type='bridge'><source bridge='vmbr0'/><model type='e1000'/></interface>",
            arch="aarch64",
        ),
        nodo="pve2",
        arqs={"pve1": Arquitectura.X86_64, "pve2": Arquitectura.AARCH64},
    ),
    "arch-aarch64-en-x86": lambda: _problemas_reales(_xml_con(disco_xml(), arch="aarch64")),
    "i686": lambda: _problemas_reales(_xml_con(disco_xml(), arch="i686")),
    "arch-ausente": lambda: _problemas_reales(
        "<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory><os><type>hvm</type></os>"
        f"<devices>{disco_xml()}</devices></domain>"
    ),
}


@pytest.mark.parametrize("escenario", sorted(ESCENARIOS_REALES))
def test_ca_d11_1_los_textos_de_lo_que_emite_proponer_no_tienen_marcadores_sin_resolver(escenario):
    problemas = ESCENARIOS_REALES[escenario]()
    assert problemas, escenario
    for p in problemas:
        sin_marcadores(texto_problema(p), p.codigo)


def test_los_escenarios_reales_cubren_las_reglas_de_la_vista_previa():
    vistos = {p.codigo for fabrica in ESCENARIOS_REALES.values() for p in fabrica()}
    assert {"V-D23", "V-D23b", "V-D24", "V-D24.supuesta", "V-D24.i686", "V-D25a", "V-D27", "V-D29",
            "V-D30", "V-D31", "V-D35", "V-D36", "V-D37", "V-D38", "V-D39", "V-D41",
            "V-D41.desconocidos", "V-D08"} <= vistos  # fmt: skip


@pytest.mark.parametrize(
    "escenario", ["red-nat", "red-direct", "red-bridge-inexistente", "red-ovs"]
)
def test_v_d35_nombra_la_tarjeta(escenario):
    for p in ESCENARIOS_REALES[escenario]():
        if p.codigo == "V-D35":
            sin_marcadores(texto_problema(p), "V-D35")


def test_v_d28_dice_cuantos_discos_admite_el_bus():
    xml = _xml_con("".join(disco_xml(dev=f"vd{i}", bus="virtio") for i in range(17)))
    p = next(p for p in _problemas_reales(xml) if p.codigo == "V-D28")
    sin_marcadores(texto_problema(p), "V-D28")
    assert "16" in texto_problema(p)


def test_v_d40_dice_el_maximo_de_memoria():
    xml = _xml_con(disco_xml()).replace("unit='MiB'>1024", "unit='MiB'>8")
    p = next(p for p in _problemas_reales(xml) if p.codigo == "V-D40")
    sin_marcadores(texto_problema(p), "V-D40")


def test_v_d07_la_plantilla_de_otra_arquitectura_se_explica_con_ambas_arquitecturas():
    from proxlaunch.interfaz.textos import texto_problema_lote
    from proxlaunch.nucleo.lote.modelos import Problema as ProblemaLote
    from proxlaunch.nucleo.lote.modelos import Severidad as SeveridadLote

    p = ProblemaLote(
        "V-L11",
        SeveridadLote.ERROR,
        "destino",
        {"nodo": "pve-arm", "motivo": "arquitectura_plantilla", "plantilla": "base",
         "arq_origen": "x86_64", "arq_destino": "aarch64"},
    )  # fmt: skip
    texto = texto_problema_lote(p)
    assert "base" in texto and "x86" in texto and "ARM64" in texto


def test_v_d09_por_pcie_en_arm_no_deja_un_marcador_sin_resolver():
    params = {"opcion": "pcie", "motivo": "pcie", "arquitectura": "aarch64", "mapeo": "gpu-a2",
              "alternativa": "sin_pcie"}  # fmt: skip
    p = Problema("hardware_cluster.pci[0].pcie", "V-D09", E, params)
    texto = texto_problema(p)
    sin_marcadores(texto, "V-D09")
    assert "sin_pcie" not in texto


def test_v_d53_sin_comprobar_dice_que_no_se_pudo_comprobar_y_no_que_el_mapeo_es_invalido():
    p = Problema("hardware_cluster", "V-D53.sin_comprobar", A, {"mapeo": "gpu-a2", "nodo": "pve1"})
    texto = texto_problema(p)
    sin_marcadores(texto, "V-D53.sin_comprobar")
    assert "no es válido" not in texto


@pytest.mark.parametrize(
    "motivo", ["id_invalido", "demasiados_pci", "demasiados_usb", "repetido", "pcie_en_arm", "otro"]
)
def test_v_d70_la_linea_del_csv_nombra_fila_y_columna_sin_marcadores(motivo):
    from proxlaunch.interfaz.textos import texto_linea_problema
    from proxlaunch.nucleo.csv_importacion.modelos import ProblemaCelda

    texto = texto_linea_problema(ProblemaCelda(7, "mapeo_pci", "V-D70", E, {"motivo": motivo}))
    sin_marcadores(texto, "V-D70")
    assert "Fila 7" in texto and "mapeo_pci" in texto


# --- Detalles de contenido de textos concretos ----------------------------------------------------


def _t(codigo: str, **params: str) -> str:
    return texto_problema(Problema("c", codigo, E, params))


def test_ca_d1_9_2_v_d31_dice_que_bitlocker_y_las_claves_se_pierden():
    assert "BitLocker" in _t("V-D31", motivo="nuevo", windows="si")


def test_ca_d1_9_1_v_d30_trae_el_procedimiento_del_menu_uefi():
    t = _t("V-D30")
    assert "NVRAM" in t and "Esc" in t and "shimx64.efi" in t


def test_ca_d1_14_1_v_d39_dice_que_no_se_leyeron_las_contrasenas_y_que_se_cambien():
    t = _t("V-D39")
    assert "contraseñas" in t and "No las he leído" in t and "cámbialas" in t


def test_ca_d1_5_9_v_d41_remite_a_hardware_del_cluster():
    assert "Hardware del clúster" in _t("V-D41", lista="hostdev")


def test_ca_d1_8_1_v_d25_trae_la_orden_de_aplanar_sin_la_opcion_b_y_sin_ejecutarla():
    t = _t("V-D25", disco="vda")
    assert "qemu-img convert -O qcow2" in t and "sin la opción -B" in t


def test_ca_d1_8_4_v_d25c_dice_que_no_se_pudo_comprobar_y_como_aplanar():
    t = _t("V-D25c", archivo="d.raw")
    assert "d.raw" in t and "qemu-img convert" in t


def test_ca_d1_8_2_v_d26_nombra_el_archivo_y_cuantas_fotos():
    t = _t("V-D26", archivo="d.qcow2", n="2")
    assert "d.qcow2" in t and "2" in t and "snapshots" in t


def test_ca_d1_7_4_v_d27b_nombra_los_tamanos_y_el_storage():
    t = _t("V-D27b", necesario="410 GiB", libre="300 GiB", storage="local-lvm")
    assert "410 GiB" in t and "300 GiB" in t and "local-lvm" in t


def test_ca_d1_4_4_v_d24_nombra_las_dos_arquitecturas_y_el_servidor():
    t = _t("V-D24", arq_xml="aarch64", nodo="pve1", arq_nodo="x86_64")
    assert "aarch64" in t and "x86_64" in t and "pve1" in t


def test_ca_d1_10_3_v_d33_dice_cuantas_copias():
    assert "5" in _t("V-D33", n="5") and "copias" in _t("V-D33", n="5")


def test_ca_d1_10_4_v_d34_explica_el_formato_y_el_bit_de_grupo():
    t = _t("V-D34", tarjeta="0", mac="01:00:5e:00:00:01")
    assert "01:00:5e:00:00:01" in t and "52:54:00:ab:cd:ef" in t and "par" in t


def test_los_valores_de_los_parametros_no_se_interpretan_como_formato():
    """Un nombre con llaves o «%s» viene de un archivo: se muestra tal cual, sin romper el texto."""
    t = _t("V-D29", disco="{0}%s{x}", tipo="{red}", sistema="no")
    assert "«{0}%s{x}»" in t  # el valor se ve literal, sin interpretarse como formato


@pytest.mark.parametrize("codigo", sorted({c.split(".")[0] for c, _, _ in CASOS_V_D}))
def test_un_parametro_con_marcado_no_hace_fallar_el_texto_de_ninguna_regla(codigo):
    """Los textos son planos: lo que viene del XML o del servidor nunca los rompe."""
    params = {
        k: "<b>x</b>"
        for k in ("disco", "archivo", "nodo", "mapeo", "plantilla", "cpu", "origen", "modelo")
    }
    texto = texto_problema(Problema("c", codigo, E, params)) or ""
    assert isinstance(texto, str)  # nunca lanza con valores raros


# --- CA-D1.3.4 y V-D20 a V-D23: errores de lectura del XML ----------------------------------------


@pytest.mark.parametrize(
    ("motivo", "extra", "fragmento"),
    [
        ("tamano", {"tamano": "5000000"}, "demasiado grande"),
        ("doctype", {}, "DOCTYPE"),
        ("formato", {}, "mal formado"),
        ("codificacion", {}, "codificación"),
        ("limites", {}, "anidado"),
        ("no_dominio", {}, "descripción de una máquina"),
        ("no_kvm", {"tipo": "xen"}, "KVM"),
        ("desconocido", {}, "no es válido"),
    ],
)
def test_ca_d1_2_los_errores_del_xml_se_explican_sin_marcadores(motivo, extra, fragmento):
    err = ErrorProxLaunch(CodigoError.XML_NO_VALIDO, {"motivo": motivo, **extra})
    texto = texto_error(err)
    sin_marcadores(texto, motivo)
    assert fragmento in texto
    assert texto == texto_error_d(err)


def test_ca_d1_2_1_v_d20_dice_el_limite_de_4_mib():
    err = ErrorProxLaunch(CodigoError.XML_NO_VALIDO, {"motivo": "tamano", "tamano": "5000000"})
    assert "4 MiB" in texto_error(err)


def test_ca_d1_3_4_v_d22_mal_formado_dice_la_linea_si_se_conoce():
    err = ErrorProxLaunch(CodigoError.XML_NO_VALIDO, {"motivo": "formato", "linea": "17"})
    assert "17" in texto_error(err)


def test_otros_errores_de_la_fase_d_no_los_toma_texto_error_d():
    assert texto_error_d(ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {})) is None


# --- Estados, conceptos y órdenes de la vista previa ----------------------------------------------


def test_ca_d1_6_1_los_cuatro_estados_en_palabras_y_con_simbolo():
    esperado = {
        EstadoFila.MIGRADO: ("Migrado", "✔"),
        EstadoFila.APROXIMADO: ("Aproximado", "⚠"),
        EstadoFila.NO_SE_MIGRA: ("No se migra", "–"),
        EstadoFila.BLOQUEA: ("Bloquea", "✖"),
    }
    for estado, (palabra, simbolo) in esperado.items():
        assert texto_estado_fila(estado) == palabra
        assert texto_estado_fila_simbolo(estado) == f"{simbolo} {palabra}"


def test_ca_d1_6_1_cada_clave_de_fila_tiene_un_concepto_en_llano():
    claves = [
        "nombre", "tipo_dominio", "tipo_os", "arquitectura", "arquitectura.i686", "memoria",
        "memoria.actual", "cpu", "cpu.topologia", "cpu.hilos", "cpu.actual", "cpu.banderas",
        "tipo_so", "firmware", "firmware.claves", "nvram", "tpm", "agente", "controlador",
        "dispositivos", "pantalla", "otros", "desconocidos", "contrasenas", "disco[0]",
        "disco[1].bus", "disco[2].backing", "disco[0].opciones", "disco_origen[3]", "cdrom[1]",
        "discos.virtio", "red[0]", "red[1].modelo", "red[0].vlan", "red[0].mtu", "red[0].limite",
        "red[0].mac", "red[0].virtualport", "red[0].extra",
    ]  # fmt: skip
    for clave in claves:
        t = texto_concepto_fila(clave)
        assert t and t != clave, clave
        sin_marcadores(t, clave)


def test_una_clave_de_fila_desconocida_se_muestra_tal_cual_sin_romper():
    assert texto_concepto_fila("algo.nuevo") == "algo.nuevo"
    assert texto_concepto_fila("") == ""


def test_ca_d1_14_2_las_cuatro_ordenes_con_su_explicacion_en_llano():
    ordenes = texto_comandos_obtener_xml()
    assert [o for o, _ in ordenes] == [
        "virsh dumpxml --inactive nombre-de-la-maquina > maquina.xml",
        "virsh domblklist nombre-de-la-maquina",
        "qemu-img info --backing-chain disco.qcow2",
        "qemu-img convert -O qcow2 entrada.qcow2 salida.qcow2",
    ]
    for _, porque in ordenes:
        assert len(porque) > 25
        sin_marcadores(porque)
    assert "--security-info" in ordenes[0][1]  # lo advierte como lo que NO se debe usar
    assert "--security-info" not in ordenes[0][0]


# --- Glosario y catálogo --------------------------------------------------------------------------


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_FASE_D)
def test_ca_d7_1_1_cada_ayuda_de_la_fase_d_existe_y_es_llana(clave):
    texto = ayuda(clave)
    assert texto and len(texto) > 40
    sin_marcadores(texto, clave)


def test_ca_d7_1_1_el_glosario_de_d_tiene_los_conceptos_del_requisito():
    requeridos = {
        "libvirt_xml", "backing_file", "nvram", "tpm", "mac_origen", "mapeo",
        "cpu_personalizada", "migracion_en_vivo", "pcie", "gpu_principal", "usb3",
    }  # fmt: skip
    assert requeridos <= set(CAMPOS_AYUDA_FASE_D)


def test_ca_d7_1_2_la_ayuda_de_libvirt_trae_un_ejemplo_concreto():
    t = ayuda("libvirt_xml")
    assert "maquina.xml" in t and "virsh dumpxml" in t and "--security-info" not in t


def test_ca_d7_1_2_cada_ayuda_de_hardware_lleva_su_ejemplo_o_su_motivo():
    assert "gpu-a2" in ayuda("mapeo")
    assert "custom-gamer" in ayuda("cpu_personalizada")
    assert "q35" in ayuda("pcie")
    assert "Proxmox 9.1" in ayuda("driver_keep")
    assert "BitLocker" in ayuda("tpm")


def _llamadas_translate(ruta: Path) -> list[tuple[str, ast.Call]]:
    """``(contexto, llamada)`` de cada ``translate``/``tr`` con literal de texto del módulo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    salida: list[tuple[str, ast.Call]] = []

    def visita(nodo: ast.AST, clase: str) -> None:
        for h in ast.iter_child_nodes(nodo):
            actual = h.name if isinstance(h, ast.ClassDef) else clase
            if isinstance(h, ast.Call):
                f = h.func
                if isinstance(f, ast.Attribute) and f.attr == "translate" and len(h.args) >= 2:
                    ctx = h.args[0]
                    if isinstance(ctx, ast.Constant):
                        salida.append((str(ctx.value), h))
                elif isinstance(f, ast.Attribute) and f.attr == "tr" and h.args and clase:
                    salida.append((clase, h))
            visita(h, actual)

    visita(arbol, "")
    return salida


def _catalogo() -> dict[str, set[str]]:
    por_contexto: dict[str, set[str]] = {}
    for c in ET.fromstring(CATALOGO.read_text(encoding="utf-8")).findall("context"):
        por_contexto[c.findtext("name") or ""] = {
            m.findtext("source") or "" for m in c.findall("message")
        }
    return por_contexto


MODULOS_D = (
    "interfaz/textos_d.py",
    "interfaz/vistas/seccion_hardware_cluster.py",
    "interfaz/dialogos/importar_libvirt.py",
)


@pytest.mark.parametrize("modulo", MODULOS_D)
def test_rnf_d7_los_textos_nuevos_son_literales_y_estan_en_el_catalogo(modulo):
    catalogo = _catalogo()
    faltan: list[str] = []
    for ctx, llamada in _llamadas_translate(RAIZ / modulo):
        fuente = llamada.args[1] if llamada.func.attr == "translate" else llamada.args[0]
        assert isinstance(fuente, ast.Constant) and isinstance(fuente.value, str), (
            f"{modulo}:{llamada.lineno}: el texto debe ser un literal (sin +, f-string ni variable)"
        )
        if fuente.value not in catalogo.get(ctx, set()):
            faltan.append(f"{ctx}: {fuente.value[:50]}")
    assert faltan == [], faltan[:3]


def test_rnf_d7_no_se_usan_alias_de_traduccion_que_lupdate_no_detecte():
    patron = re.compile(r"\b(_tr|tr_)\s*\(")
    for modulo in MODULOS_D:
        assert not patron.search((RAIZ / modulo).read_text(encoding="utf-8")), modulo


def test_rnf_d7_sin_traductor_los_textos_salen_en_el_idioma_de_origen():
    assert QCoreApplication.translate("TextosD", "Migrado") == "Migrado"
    assert texto_estado_fila(EstadoFila.MIGRADO) == "Migrado"


def test_el_modulo_de_textos_de_d_no_importa_qt_widgets():
    codigo = (RAIZ / "interfaz" / "textos_d.py").read_text(encoding="utf-8")
    assert "QtWidgets" not in codigo and "QtGui" not in codigo
    assert textos_d.__doc__
