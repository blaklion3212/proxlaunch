"""Resumen de una máquina, resumen del lote y simulación con las opciones de la fase A (RF-A0.1).

Derivadas de docs/requisitos/fase-a.md: CA-A0.1.1, CA-A0.1.2, CA-A0.1.3 y, de RF-A0.4/A5.2.2, la
nota de que un MTU con tarjeta no VirtIO se ignora.
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.resumen_lote import (
    ResumenLote,
    texto_opciones_del_plan,
    texto_peticiones,
)
from proxlaunch.nucleo.lote.modelos import AccionPeticion
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed, ModeloRed
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo import ClienteLoteFalso, sesion_falsa
from .apoyo_lote import cfg_simple, definicion, planificar
from .apoyo_mvp4 import cfg_base

OPCIONES = {
    "encender": True,
    "arranque_auto": True,
    "arranque_orden": 2,
    "arranque_espera": 30,
    "notas_origen": True,
    "notas_usuario": True,
    "notas": "Servidor de pruebas del equipo",
    "etiquetas_usuario": ("web", "produccion"),
    "pool": "produccion",
    "proteger": True,
}


def cfg_completa(**cambios) -> ConfiguracionVM:
    redes = [InterfazRed("vmbr0", ModeloRed.VIRTIO, None, mtu=1500, limite_mb=100.0)]
    base = {**OPCIONES, "redes": redes}
    base.update(cambios)
    return cfg_base(**base)


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


def pintar(resumen: ResumenVM, cfg: ConfiguracionVM, *, avanzado: bool = True) -> str:
    resumen.actualizar(
        cfg,
        ["scsi0"],
        [],
        avanzado=avanzado,
        motivo_nodo="",
        bloqueo=None,
        ocupado=False,
    )
    return resumen.texto_html


# --- CA-A0.1.1: cada opción aparece con su valor legible ---


def test_ca_a0_1_1_el_resumen_muestra_cada_opcion_nueva_con_su_valor(resumen):
    html = pintar(resumen, cfg_completa())
    for esperado in (
        "Encender al terminar:</b> sí",
        "Arrancar con el servidor:</b> sí",
        "Pool:</b> produccion",
        "Etiquetas:</b> web, produccion",
        "Orden de arranque:</b> 2",
        "Espera de arranque:</b> 30 s",
        "Proteger contra borrado:</b> sí",
        "Notas:</b> Servidor de pruebas del equipo",
        "Notas de origen:</b> sí, con tu usuario",
        "MTU 1500",
        "límite 100 MB/s",
    ):
        assert esperado in html, esperado


def test_ca_a0_1_1_mtu_igual_al_bridge_y_limite_decimal_se_leen_en_claro(resumen):
    cfg = cfg_completa(redes=[InterfazRed("vmbr0", mtu=1, limite_mb=12.5)])
    html = pintar(resumen, cfg)
    assert "MTU Igual al bridge" in html
    assert "límite 12.5 MB/s" in html


def test_ca_a0_1_1_en_modo_basico_las_opciones_avanzadas_salen_como_ocultas_que_se_aplicaran(
    resumen,
):
    html = pintar(resumen, cfg_completa(), avanzado=False)
    assert "Opciones avanzadas que se aplicarán" in html
    for esperado in ("Orden de arranque: 2", "Proteger contra borrado: sí", "MTU 1500"):
        assert esperado in html, esperado
    # Las básicas siguen saliendo en el cuerpo del resumen.
    assert "Encender al terminar:</b> sí" in html


def test_ca_a0_1_1_el_resumen_no_inventa_lineas_con_tarjeta_no_virtio_y_avisa_que_se_ignora(
    resumen,
):
    cfg = cfg_completa(redes=[InterfazRed("vmbr0", ModeloRed.E1000, mtu=1500)])
    html = pintar(resumen, cfg)
    assert "se ignora" in html  # CA-A5.2.2: el Resumen indica que el MTU no se aplica


def test_ca_a0_1_1_el_texto_de_las_notas_se_escapa_en_el_resumen(resumen):
    html = pintar(resumen, cfg_completa(notas="<b>negrita</b> & más"))
    assert "<b>negrita</b>" not in html
    assert "&lt;b&gt;negrita" in html


# --- CA-A0.1.3: por defecto solo «Notas de origen» ---


def test_ca_a0_1_3_con_los_valores_por_defecto_solo_sale_notas_de_origen(resumen):
    html = pintar(resumen, cfg_base(notas_origen=True))
    assert "Notas de origen:</b> sí" in html
    for ausente in (
        "Encender",
        "Arrancar con el servidor",
        "Pool",
        "Etiquetas",
        "Orden de arranque",
        "Espera de arranque",
        "Proteger",
        "MTU",
        "límite",
        "Opciones avanzadas",
        "Notas:</b>",
    ):
        assert ausente not in html, ausente


def test_ca_a0_1_3_con_notas_de_origen_desmarcada_el_resumen_lo_dice_y_nada_mas(resumen):
    html = pintar(resumen, cfg_base(notas_origen=False))
    assert "Notas de origen:</b> no" in html
    assert "Encender" not in html and "Pool" not in html


def test_ca_a0_1_3_en_modo_basico_tampoco_aparece_el_bloque_de_avanzadas_por_defecto(resumen):
    html = pintar(resumen, cfg_base(notas_origen=True), avanzado=False)
    assert "Opciones avanzadas que se aplicarán" not in html


# --- Resumen del lote ---


def plan_con(inv, **opciones):
    cfg = cfg_simple(**opciones)
    return planificar(inv, definicion(3, plantilla=cfg))


def test_ca_a0_1_1_el_resumen_del_lote_lista_las_opciones_nuevas(inv_cluster):
    plan = plan_con(inv_cluster, **OPCIONES)
    texto = texto_opciones_del_plan(plan)
    for esperado in (
        "Notas de origen: sí, con tu usuario",
        "Encender al terminar: sí",
        "Arrancar con el servidor: sí",
        "Etiquetas: web, produccion",
        "Pool: produccion",
        "Orden de arranque: 2",
        "Espera de arranque: 30 s",
        "Proteger contra borrado: sí",
    ):
        assert esperado in texto, esperado


def test_ca_a0_1_3_el_resumen_del_lote_con_valores_por_defecto_solo_dice_notas_de_origen(
    inv_cluster,
):
    plan = plan_con(inv_cluster, notas_origen=True)
    assert texto_opciones_del_plan(plan) == "Notas de origen: sí"


def test_ca_a0_1_3_notas_de_origen_desmarcada_en_el_lote_se_indica(inv_cluster):
    plan = plan_con(inv_cluster, notas_origen=False)
    assert texto_opciones_del_plan(plan) == "Notas de origen: no"


def test_ca_a0_7_2_el_resumen_del_lote_dice_varia_si_las_filas_difieren(inv_cluster):
    # Lote por filas con valores distintos por fila (CA-A0.7.2): el resumen no oculta la diferencia.
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.lote.modelos import FilaLote

    filas = []
    for i, pool in enumerate(("produccion", "pruebas", None)):
        cfg = cfg_simple(pool=pool, encender=i == 0)
        cfg.discos = [Disco("local-lvm", 10)]
        filas.append(FilaLote(f"web-{i + 1:02d}", cfg, None, "pve1", None))
    plan = planificar(inv_cluster, definicion_por_filas(filas, plantilla_base=cfg_simple()))
    texto = texto_opciones_del_plan(plan)
    assert "Encender al terminar: sí en 1 de 3" in texto
    assert "Pool: varía según la fila" in texto


def test_ca_a0_1_1_la_pantalla_del_lote_muestra_las_opciones_en_su_resumen(qtbot, inv_cluster):
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    r.mostrar_plan(plan_con(inv_cluster, **OPCIONES))
    textos = "\n".join(lbl.text() for lbl in r.findChildren(type(r._titulo)) if lbl.isVisibleTo(r))
    assert "Encender al terminar" in textos
    assert "Pool" in textos


# --- CA-A0.1.2: simulación ---


def simulacion_con(inv, **opciones):
    cfg = cfg_simple(**opciones)
    cfg.redes = [InterfazRed("vmbr0", ModeloRed.VIRTIO, None, mtu=1500, limite_mb=100.0)]
    cliente = ClienteLoteFalso()
    sesion = sesion_falsa(cliente=cliente)
    res = simular(sesion, definicion(2, plantilla=cfg), inv, reloj=RelojSimulado())
    return res, cliente


def test_ca_a0_1_2_la_simulacion_incluye_los_parametros_de_las_opciones_nuevas(inv_cluster):
    res, _ = simulacion_con(inv_cluster, **OPCIONES)
    texto = texto_peticiones(res)
    for esperado in (
        "tags =",
        "pool = produccion",
        "description =",
        "protection = 1",
        "onboot = 1",
        "startup = order=2,up=30",
        "mtu=1500",
        "rate=100",
    ):
        assert esperado in texto, esperado


def test_ca_a0_1_2_la_simulacion_enciende_al_final_de_cada_maquina(inv_cluster):
    res, _ = simulacion_con(inv_cluster, **OPCIONES)
    assert res.peticiones_detalle, "la simulación debe traer las peticiones de cada MV"
    for detalle in res.peticiones_detalle.values():
        acciones = [p.accion for p in detalle]
        assert acciones[-1] == AccionPeticion.ENCENDER
        assert acciones.count(AccionPeticion.ENCENDER) == 1
        assert acciones[0] == AccionPeticion.CREAR


def test_ca_a0_1_2_la_simulacion_no_escribe_nada_en_el_servidor(inv_cluster):
    _, cliente = simulacion_con(inv_cluster, **OPCIONES)
    assert cliente.creados == [] and cliente.eliminados == []
    assert not [ll for ll in cliente.llamadas if ll[0] in ("crear_vm", "eliminar_vm")]


def test_ca_a0_1_2_sin_encender_la_simulacion_no_lista_el_encendido(inv_cluster):
    res, _ = simulacion_con(inv_cluster, **{**OPCIONES, "encender": False})
    for detalle in res.peticiones_detalle.values():
        assert AccionPeticion.ENCENDER not in [p.accion for p in detalle]


def test_ca_a0_1_3_con_valores_por_defecto_la_simulacion_no_lleva_parametros_nuevos(inv_cluster):
    cliente = ClienteLoteFalso()
    cfg = cfg_simple(notas_origen=False)
    res = simular(
        sesion_falsa(cliente=cliente),
        definicion(1, plantilla=cfg),
        inv_cluster,
        reloj=RelojSimulado(),
    )
    texto = texto_peticiones(res)
    for ausente in ("pool =", "description =", "protection", "onboot", "startup", "mtu=", "rate="):
        assert ausente not in texto, ausente
