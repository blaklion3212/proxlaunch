"""Ventana principal con las opciones de la fase A: disponibilidad al conectar, cambio de servidor,
versión forzada, Resumen y lecturas en trabajadores.

Derivadas de docs/requisitos/fase-a.md: RF-A0.1, RF-A0.3, RF-A0.4 (CA-A0.4.2), CA-A1.1.4,
CA-A4.2.1-5, CL-A15, RNF-A3.
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

import pytest

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoolsServidor
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .apoyo_fase_a import inventario_con, permisos_fase_a, textos_de
from .test_ventana_principal import conectar, esperar_validacion

entorno = _base.entorno


def conectar_con(qtbot, entorno, permisos, pools=None, **sesion_kw):
    """Conecta la ventana a un servidor cuyo catálogo trae esos permisos y pools."""
    entorno.inv = inventario_con(entorno.inv, permisos, pools)
    s = conectar(qtbot, entorno, sesion_falsa(**sesion_kw))
    esperar_validacion(qtbot, entorno.ventana)
    return s


# --- RF-A0.3: privilegio ausente en la ventana ---


def test_ca_a1_1_4_al_conectar_sin_vm_powermgmt_la_casilla_de_encender_queda_deshabilitada(
    qtbot, entorno
):
    conectar_con(qtbot, entorno, permisos_fase_a(anadir=()))
    f = entorno.ventana.formulario
    assert f.chk_encender.isVisible() and not f.chk_encender.isEnabled()
    assert "VM.PowerMgmt" in f.chk_encender.accessibleDescription()
    assert "VM.PowerMgmt" in textos_de(f.fila_encender)


def test_ca_a8_1_2_con_el_rol_mas_los_dos_opcionales_todas_las_opciones_estan_habilitadas(
    qtbot, entorno
):
    conectar_con(
        qtbot,
        entorno,
        permisos_fase_a(anadir=("VM.PowerMgmt", "Pool.Audit")),
        PoolsServidor(EstadoPools.OK, ("produccion",)),
    )
    f = entorno.ventana.formulario
    entorno.ventana.establecer_modo(Modo.AVANZADO)
    for nombre in (
        "chk_encender",
        "chk_arranque_auto",
        "chk_notas_origen",
        "txt_notas",
        "txt_etiquetas",
        "combo_pool",
        "txt_orden",
        "txt_espera",
        "chk_proteger",
    ):
        assert getattr(f, nombre).isEnabled(), nombre
    assert not f.tabla_redes._filas[0].mtu.accessibleDescription()


def test_ca_a8_1_1_con_el_rol_de_0_5_1_no_aparece_ningun_aviso_nuevo_de_privilegios(qtbot, entorno):
    conectar_con(qtbot, entorno, permisos_fase_a(anadir=()))
    v = entorno.ventana
    from .apoyo_mvp3 import textos_de_avisos

    todo = textos_de_avisos(v)
    assert "faltan" not in todo.lower() or "VM.PowerMgmt" not in todo
    assert "VM.PowerMgmt" not in v.statusBar().currentMessage()


@pytest.mark.parametrize(
    ("estado", "esperado", "habilitada"),
    [
        (PoolsServidor(EstadoPools.SIN_PERMISO), "Pool.Audit", False),
        (PoolsServidor(EstadoPools.OK, ()), "No hay pools", True),
        (PoolsServidor(EstadoPools.DESCONOCIDO), "No sabemos si puedes ver", True),
        (PoolsServidor(EstadoPools.ERROR), "No se pudo leer la lista de pools", False),
    ],
)
def test_ca_a4_2_x_la_ventana_pinta_cada_estado_de_pools(
    qtbot, entorno, estado, esperado, habilitada
):
    conectar_con(qtbot, entorno, permisos_fase_a(), estado)
    f = entorno.ventana.formulario
    assert f.combo_pool.isEnabled() is habilitada
    assert esperado in textos_de(f.fila_pool)
    assert f.nombre.isEnabled()  # CA-A4.2.5: el resto del formulario sigue usable


def test_ca_a4_2_3_la_ventana_ofrece_solo_los_pools_que_devuelve_la_api(qtbot, entorno):
    conectar_con(qtbot, entorno, permisos_fase_a(), PoolsServidor(EstadoPools.OK, ("a",)))
    combo = entorno.ventana.formulario.combo_pool
    assert [combo.itemText(i) for i in range(combo.count())] == ["Ninguno", "a"]


# --- RF-A0.4: versión forzada ---


def test_ca_a0_4_2_con_la_version_forzada_menor_que_la_minima_las_etiquetas_se_deshabilitan(
    qtbot, entorno
):
    conectar_con(qtbot, entorno, permisos_fase_a(), version=(7, 0), forzada=True)
    f = entorno.ventana.formulario
    assert f.txt_etiquetas.isVisible() and not f.txt_etiquetas.isEnabled()
    assert "7.3" in f.txt_etiquetas.accessibleDescription()


def test_ca_a0_4_2_con_una_version_real_soportada_las_etiquetas_estan_habilitadas(qtbot, entorno):
    conectar_con(qtbot, entorno, permisos_fase_a(), version=(9, 2))
    assert entorno.ventana.formulario.txt_etiquetas.isEnabled()


# --- CL-A15: cambio de servidor ---


def releer_servidor(qtbot, entorno, inv) -> None:
    """El servidor responde distinto (otros permisos o pools) y la ventana vuelve a descubrir."""
    v = entorno.ventana
    entorno.inv = inv
    v._descubrir()
    qtbot.waitUntil(lambda: v._formulario_listo and not v._descubriendo, timeout=4000)
    esperar_validacion(qtbot, v)


def test_cl_a15_al_cambiar_los_permisos_del_servidor_el_valor_se_restablece_con_aviso(
    qtbot, entorno
):
    v = entorno.ventana
    conectar_con(qtbot, entorno, permisos_fase_a())
    v.formulario.chk_encender.setChecked(True)
    assert v.formulario.configuracion().encender
    releer_servidor(qtbot, entorno, inventario_con(entorno.inv, permisos_fase_a(anadir=())))
    f = v.formulario
    assert not f.chk_encender.isEnabled()
    assert not f.configuracion().encender
    assert "Se restableció" in textos_de(f.fila_encender)
    assert "VM.PowerMgmt" in textos_de(f.fila_encender)


def test_cl_a15_un_pool_elegido_que_el_servidor_ya_no_tiene_se_restablece_con_aviso(qtbot, entorno):
    v = entorno.ventana
    conectar_con(qtbot, entorno, permisos_fase_a(), PoolsServidor(EstadoPools.OK, ("produccion",)))
    combo = v.formulario.combo_pool
    combo.setCurrentIndex(combo.findData("produccion"))
    assert v.formulario.configuracion().pool == "produccion"
    releer_servidor(
        qtbot,
        entorno,
        inventario_con(entorno.inv, permisos_fase_a(), PoolsServidor(EstadoPools.OK, ("otro",))),
    )
    assert v.formulario.configuracion().pool is None
    assert "Se restableció" in textos_de(v.formulario.fila_pool)


def test_cl_a15_al_conectar_a_otro_servidor_el_formulario_arranca_limpio_con_su_disponibilidad(
    qtbot, entorno
):
    v = entorno.ventana
    conectar_con(qtbot, entorno, permisos_fase_a())
    v.formulario.chk_encender.setChecked(True)
    entorno.inv = inventario_con(entorno.inv, permisos_fase_a(anadir=()))
    conectar(qtbot, entorno, sesion_falsa(perfil_=perfil("p2", "Otro", hosts=("10.0.0.9",))))
    esperar_validacion(qtbot, v)
    f = v.formulario
    assert not f.configuracion().encender
    assert not f.chk_encender.isEnabled()
    assert "VM.PowerMgmt" in textos_de(f.fila_encender)


# --- RF-A0.1: el Resumen de la ventana ---


def test_ca_a0_1_1_marcar_una_opcion_en_el_formulario_la_agrega_al_resumen(qtbot, entorno):
    v = entorno.ventana
    conectar_con(qtbot, entorno, permisos_fase_a(), PoolsServidor(EstadoPools.OK, ("produccion",)))
    assert "Encender al terminar" not in v.resumen.texto_html
    v.formulario.chk_encender.setChecked(True)
    v.formulario.combo_pool.setCurrentIndex(v.formulario.combo_pool.findData("produccion"))
    esperar_validacion(qtbot, v)
    assert "Encender al terminar:</b> sí" in v.resumen.texto_html
    assert "Pool:</b> produccion" in v.resumen.texto_html


def test_ca_a0_1_3_el_resumen_inicial_solo_agrega_notas_de_origen(qtbot, entorno):
    v = entorno.ventana
    conectar_con(qtbot, entorno, permisos_fase_a())
    html = v.resumen.texto_html
    assert "Notas de origen:</b> sí" in html
    for ausente in ("Encender", "Arrancar con el servidor", "Pool", "Proteger", "MTU"):
        assert ausente not in html, ausente


# --- RNF-A3: lecturas en trabajadores ---


def test_rnf_a3_el_descubrimiento_que_lee_pools_y_politica_corre_fuera_del_hilo_de_la_interfaz(
    qtbot, entorno, monkeypatch
):
    hilos: list[int] = []
    original = vp.descubrir_y_comprobar_permisos

    def espia(sesion):
        hilos.append(threading.get_ident())
        return original(sesion)

    monkeypatch.setattr(vp, "descubrir_y_comprobar_permisos", espia)
    conectar_con(qtbot, entorno, permisos_fase_a())
    assert hilos, "la conexión debe descubrir el inventario"
    assert threading.get_ident() not in hilos


RAIZ = Path(__file__).resolve().parents[2] / "src" / "proxlaunch" / "interfaz"
LECTURAS_DEL_SERVIDOR = {
    "pools",
    "opciones_cluster",
    "leer_pools",
    "leer_politica_etiquetas",
    "detalle_plantilla",
    "config_vm",
    "estado_actual_vm",
}


def llamadas_directas(ruta: Path) -> list[str]:
    """Llamadas a lecturas del servidor hechas directamente en el código de la interfaz."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    malas: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nombre in LECTURAS_DEL_SERVIDOR:
                malas.append(f"{ruta.name}:{nodo.lineno} {nombre}")
    return malas


def test_rnf_a3_ninguna_vista_ni_dialogo_lee_pools_ni_politica_ni_descripciones_directamente():
    malas: list[str] = []
    for ruta in sorted(RAIZ.rglob("*.py")):
        if ruta.name == "trabajadores.py":
            continue  # es el único sitio que habla con el servidor, siempre fuera del hilo gráfico
        malas += llamadas_directas(ruta)
    assert malas == []


def test_rnf_a3_las_lecturas_del_catalogo_con_opciones_se_encargan_a_un_trabajador():
    fuente = (RAIZ / "trabajadores.py").read_text(encoding="utf-8")
    assert "def leer_catalogo_para" in fuente and "opciones=True" in fuente
    assert "def leer_detalle_plantilla" in fuente
    assert "def inspeccionar_lotes" in fuente
