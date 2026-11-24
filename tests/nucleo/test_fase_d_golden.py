"""RF-D0.2: con las opciones de D por defecto y un nodo x86_64 la petición es la de 0.8.0.

Las instantáneas (``tests/datos/fase_d/golden_v080.json``) se generaron con el código de la
etiqueta ``v0.8.0`` (véase ``apoyo_golden_fase_d``) sobre un doble 8.4 y otro 9.2: disco vacío,
ISO (con y sin TPM/OVMF), importar un disco (con y sin ampliar), importar con el disco 2 sin
imagen, clonar (con y sin ajustes, cloud-init, red del clon y firewall), el asistente de imagen
cloud, lotes, reintento, Deshacer, simulación y los lotes guardados de 0.5.1 a 0.8.0. Aquí se
repiten con 0.9.0 y se comparan las ESCRITURAS byte a byte (método, ruta, consulta y cuerpo).
CA-D0.2.1 a CA-D0.2.4, CA-D2.4.3, CA-D2.6.6, CA-D6.1.2, CA-D0.4.1 (lo que no cambia).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from proxlaunch.nucleo import constructor_peticion, valores_defecto
from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
)
from proxlaunch.nucleo.modelos.cpu import TIPO_CPU_X86_DEFECTO

from . import apoyo_golden_fase_d as g
from .apoyo_fase_a import catalogo, cfg_vm, def_lote, inv_con, plan_de
from .apoyo_fase_d import ARM, cfg_arm, inv_arq
from .apoyo_lote import Cluster, crear_banco

GOLDEN = g.golden()
VERSIONES = sorted(GOLDEN["versiones"])
NOMBRES = sorted(GOLDEN["versiones"]["8.4"])

X86_KERNEL = ArquitecturaNodo(Arquitectura.X86_64, FuenteArquitectura.KERNEL)
X86_RECURSOS = ArquitecturaNodo(Arquitectura.X86_64, FuenteArquitectura.RECURSOS)
ILEGIBLE = ArquitecturaNodo(Arquitectura.DESCONOCIDA, FuenteArquitectura.NINGUNA, "sin_permiso")


def _fijar(arq: ArquitecturaNodo):
    def gancho(inv: Any) -> None:
        inv.arquitecturas = {n.nombre: arq for n in inv.topologia.nodos}

    return gancho


@pytest.fixture
def con_arquitectura(monkeypatch: pytest.MonkeyPatch):
    """Ejecuta los escenarios con el gancho que fija la arquitectura de todos los nodos."""

    def _poner(arq: ArquitecturaNodo | None) -> None:
        monkeypatch.setattr(g, "GANCHO_INVENTARIO", None if arq is None else _fijar(arq))

    return _poner


def _igual(actual: Any, esperado: Any) -> bool:
    # json.loads conserva el orden de inserción: se compara también el orden de las claves.
    texto = json.dumps(json.loads(json.dumps(actual)), sort_keys=False)
    return texto == json.dumps(esperado, sort_keys=False)


# --- Las instantáneas -----------------------------------------------------------------------------


def test_las_instantaneas_vienen_de_la_version_0_8_0_y_cubren_8_4_y_9_2():
    assert GOLDEN["version_codigo"] == "0.8.0"
    assert VERSIONES == ["8.4", "9.2"]
    assert set(GOLDEN["versiones"]["8.4"]) == set(GOLDEN["versiones"]["9.2"])
    assert len(NOMBRES) >= 24
    for requerido in (
        "vacio",
        "iso",
        "iso_windows_tpm_ovmf",
        "importar_con_resize",
        "importar_sin_resize",
        "importar_dos_discos_sin_imagen",
        "clon_sin_ajustes",
        "clon_con_ajustes",
        "clon_cloudinit",
        "clon_red_del_clon",
        "clon_firewall",
        "asistente_imagen_cloud",
        "lote_3_encender",
        "reintento_de_ajustes",
        "deshacer_2",
        "simulacion_lote_vacio",
        "simulacion_lote_clon",
    ):
        assert requerido in NOMBRES


def test_las_escrituras_de_0_8_0_son_las_mismas_en_8_4_y_en_9_2():
    """Premisa del golden: en 0.8.0 la versión no cambia las escrituras (9.2 = 8.4)."""
    assert GOLDEN["versiones"]["8.4"] == GOLDEN["versiones"]["9.2"]


@pytest.mark.parametrize("nombre", NOMBRES)
@pytest.mark.parametrize("version", VERSIONES)
def test_ca_d0_2_1_las_escrituras_son_identicas_byte_a_byte_a_las_de_0_8_0(version, nombre):
    """CA-D0.2.1 y CA-D2.4.3: sin arquitectura detectada (inventario como el de 0.8.0)."""
    assert _igual(g.actuales(version)[nombre], GOLDEN["versiones"][version][nombre])


@pytest.mark.parametrize("version", VERSIONES)
@pytest.mark.parametrize("arq", [X86_KERNEL, X86_RECURSOS], ids=["kernel", "host-arch"])
def test_ca_d0_2_1_con_el_nodo_x86_64_detectado_las_escrituras_son_las_de_0_8_0(
    con_arquitectura, version, arq
):
    con_arquitectura(arq)
    actual = g.escenarios(version)
    for nombre in NOMBRES:
        assert _igual(actual[nombre], GOLDEN["versiones"][version][nombre]), nombre


@pytest.mark.parametrize("version", VERSIONES)
def test_ca_d0_2_2_con_la_arquitectura_no_legible_las_escrituras_son_las_de_0_8_0(
    con_arquitectura, version
):
    """CA-D0.2.2: nodo ``desconocida`` (sin ``Sys.Audit``) se trata como x86_64."""
    con_arquitectura(ILEGIBLE)
    actual = g.escenarios(version)
    for nombre in NOMBRES:
        assert _igual(actual[nombre], GOLDEN["versiones"][version][nombre]), nombre


def test_ca_d0_2_2_solo_se_anade_el_aviso_v_d04_al_plan_con_arquitectura_no_legible():
    """CA-D0.2.2: frente a un nodo x86_64 conocido, el plan solo gana V-D04 (aviso)."""

    def plan(arq: ArquitecturaNodo) -> Any:
        banco = crear_banco(("pve1",), cluster=Cluster(("pve1",)))
        banco.inv = inv_con(catalogo())
        banco.inv.arquitecturas = {"pve1": arq}
        return plan_de(banco, def_lote(3, plantilla_vm=cfg_vm(encender=True)))

    x86, ilegible = plan(X86_KERNEL), plan(ILEGIBLE)
    reglas = lambda p: sorted(q.regla for q in p.problemas)  # noqa: E731
    assert reglas(ilegible) == sorted([*reglas(x86), "V-D04"])
    (aviso,) = [q for q in ilegible.problemas if q.regla == "V-D04"]
    assert aviso.severidad.value == "aviso" and aviso.params["nodo"] == "pve1"
    assert not ilegible.bloqueado
    assert [e.cfg for e in ilegible.elementos] == [e.cfg for e in x86.elementos]


# --- CA-D0.2.4: importar con un disco y con discos 2+ sin imagen ----------------------------------


@pytest.mark.parametrize("version", VERSIONES)
def test_ca_d0_2_4_importar_un_disco_y_dos_discos_sin_imagen_como_en_0_8_0(version):
    actual = g.actuales(version)
    uno = actual["importar_sin_resize"][0][2]
    dos = actual["importar_dos_discos_sin_imagen"][0][2]
    assert uno.count("import-from") == 1
    # El disco 2 se crea vacío (sin ``import-from``) como en 0.8.0.
    assert dos.count("import-from") == 1 and "scsi1=local-lvm%3A16" in dos
    assert _igual(dos, GOLDEN["versiones"][version]["importar_dos_discos_sin_imagen"][0][2])


# --- Espía y valor por defecto (arquitectura §7.2) ------------------------------------------------


@pytest.mark.parametrize("arq", [None, X86_KERNEL, ILEGIBLE], ids=["sin_dato", "x86", "ilegible"])
def test_ca_d2_6_6_un_nodo_x86_o_ilegible_no_entra_en_el_perfil_aarch64(
    monkeypatch, arq, con_arquitectura
):
    """CA-D2.6.6: ``construir_parametros`` con nodo x86 no toca la rama ARM (espía)."""
    llamadas: list[str] = []
    original = constructor_peticion._parametros_aarch64

    def espia(*a: Any, **kw: Any) -> Any:
        llamadas.append("arm")
        return original(*a, **kw)

    monkeypatch.setattr(constructor_peticion, "_parametros_aarch64", espia)
    if arq is not None:
        con_arquitectura(arq)
    g.escenarios("9.2")
    assert llamadas == []


def test_ca_d2_6_6_el_espia_si_detecta_la_rama_arm_con_un_nodo_aarch64(
    monkeypatch, con_arquitectura
):
    """Control del espía: con un nodo ARM64 la rama se usa (el espía funciona)."""
    llamadas: list[str] = []
    original = constructor_peticion._parametros_aarch64

    def espia(*a: Any, **kw: Any) -> Any:
        llamadas.append("arm")
        return original(*a, **kw)

    monkeypatch.setattr(constructor_peticion, "_parametros_aarch64", espia)
    con_arquitectura(ArquitecturaNodo(Arquitectura.AARCH64, FuenteArquitectura.KERNEL))
    constructor_peticion.construir_parametros(cfg_arm(), inv_arq({"pve1": ARM}))
    assert llamadas == ["arm"]


def test_el_tipo_de_cpu_por_defecto_sigue_siendo_el_de_0_8_0():
    """CA-D2.11.2/4: el alias conserva el valor (golden intacto)."""
    assert valores_defecto.TIPO_CPU == "x86-64-v2-AES" == TIPO_CPU_X86_DEFECTO


# --- CA-D6.1.2: lotes guardados de 0.5.1 a 0.8.0 ---------------------------------------------


def _guardados() -> Iterator[str]:
    return (n for n in NOMBRES if n.startswith("simulacion_guardado_"))


def test_ca_d6_1_2_hay_lotes_guardados_de_los_formatos_1_a_4_en_el_golden():
    assert len(list(_guardados())) == len(g.LOTES_GUARDADOS) >= 8


def test_el_gancho_de_arquitectura_es_efectivo_con_un_nodo_aarch64(con_arquitectura):
    """Control del golden: con ARM64 las escrituras SÍ cambian (el gancho llega al inventario).

    ``crear`` directo no adapta la configuración (lo hace el planificador): V-D09 bloquea el
    SeaBIOS x86 antes de escribir nada, de modo que la secuencia deja de ser la de 0.8.0.
    """
    con_arquitectura(ARM)
    iso = g.escenarios("9.2")["iso"]
    assert not _igual(iso, GOLDEN["versiones"]["9.2"]["iso"])
