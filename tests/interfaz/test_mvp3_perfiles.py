"""Perfiles de máquina en la interfaz (MVP 3): selector, aplicar, confirmaciones, guardar,
actualizar, administrar y bloqueo con un lote en ejecución.

Derivadas de docs/requisitos/mvp3.md: RF-P05 (CA-P05.1..8), RF-P02/P11 (selector y textos),
RF-P03/P04 (guardar y administrar) y RF-P06 (pistas). Ningún diálogo modal real: todo pasa por
``Modales`` y nada se escribe fuera de ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoGuardarPerfil
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO, OrigenPerfil
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo import CreacionPorVmid
from .apoyo_mvp3 import (
    Modales,
    conectar3,
    escribir,
    hubo_escritura,
    pulsar_boton,
)
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_ventana_principal import esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

MENSAJE_REEMPLAZO = "Se reemplazarán los ajustes de hardware que cambiaste."
FABRICA_GRANDE = "fabrica.servidor-grande"


# --- Ayudas --------------------------------------------------------------------------------


def elegir_perfil(v, id_perfil: str) -> None:
    """Hace lo que el usuario: abre el combo, elige la opción y se emite ``activated``."""
    combo = v.selector_perfil.combo
    idx = combo.findData(id_perfil)
    assert idx >= 0, f"el selector no ofrece {id_perfil}"
    combo.setCurrentIndex(idx)
    combo.activated.emit(idx)


def editar_nucleos(qtbot, v, valor: str = "6") -> None:
    """Cambio manual de hardware (no es de perfil): los núcleos del formulario."""
    escribir(v.formulario.cores, valor)
    esperar_validacion(qtbot, v)


def crear_perfil_usuario(v, nombre: str = "Mi base", **cambios):
    """Perfil de usuario con el hardware actual del formulario (sin diálogos)."""
    from proxlaunch.nucleo.perfiles_maquina.aplicar import config_desde_configuracion

    config = config_desde_configuracion(v.formulario.configuracion(), con_pistas=True)
    perfil = v._almacen_perfiles.crear(nombre, "", config)
    v._recargar_selector(perfil.id)
    return perfil


@pytest.fixture
def conectado(qtbot, entorno3):
    conectar3(qtbot, entorno3)
    return entorno3.ventana


# --- Selector (RF-P02, RF-P11, CA-P05.4) -------------------------------------------------------


def test_ca_p05_4_el_formulario_recien_abierto_tiene_el_perfil_predeterminado(conectado):
    s = conectado.selector_perfil
    assert s.perfil_actual_id == ID_PREDETERMINADO
    assert not s.modificado
    assert "(modificado)" not in s.texto_combo


def test_ca_p02_1_el_selector_muestra_primero_los_de_fabrica_con_el_texto_de_fabrica(conectado):
    combo = conectado.selector_perfil.combo
    textos = [combo.itemText(i) for i in range(combo.count())]
    assert textos[0] == "Personalizado"
    assert len(textos) > 1
    assert all("De fábrica" in t for t in textos[1:])  # sin usuario aún: solo fábrica


def test_ca_p02_1_los_de_fabrica_van_antes_que_los_del_usuario(conectado):
    crear_perfil_usuario(conectado, "Aaa mío")
    combo = conectado.selector_perfil.combo
    textos = [combo.itemText(i) for i in range(combo.count())]
    assert "De fábrica" in textos[1] and "De fábrica" in textos[-2]
    assert textos[-1] == "Aaa mío"


def test_ca_p11_2_cada_opcion_del_selector_trae_su_resumen_en_lenguaje_llano(conectado):
    combo = conectado.selector_perfil.combo
    for i in range(1, combo.count()):
        ayuda = combo.itemData(i, 3)  # Qt.ItemDataRole.ToolTipRole
        assert ayuda and "GiB" in ayuda, combo.itemText(i)
    assert conectado.selector_perfil._resumen.text() != ""


# --- Aplicar un perfil (CA-P05.1, CA-P05.7) ----------------------------------------------------


def test_ca_p05_1_aplicar_perfil_cambia_el_hardware_pero_no_nombre_vmid_nodo_ni_el_lote(
    qtbot, conectado
):
    v = conectado
    v.formulario.nombre.setText("srv-web-77")
    v.formulario.nombre.textEdited.emit("srv-web-77")
    v.formulario.vmid.setText("4321")
    v.formulario.vmid.textEdited.emit("4321")
    escribir(v.bloque_lote.cantidad, "5")
    escribir(v.bloque_lote.prefijo, "app")
    v.bloque_lote._radio_un_nodo.setChecked(True)
    v.bloque_lote.combo_nodo.setCurrentIndex(v.bloque_lote.combo_nodo.findData("pve3"))
    esperar_validacion(qtbot, v)
    antes = v.formulario.configuracion()
    destino_antes = v.bloque_lote.destino()
    patron_antes = v.bloque_lote.patron()
    assert antes.cores == 2

    elegir_perfil(v, FABRICA_GRANDE)

    despues = v.formulario.configuracion()
    grande = v._almacen_perfiles.obtener(FABRICA_GRANDE).config
    assert despues.cores == grande.cores and despues.memoria_mib == grande.memoria_mib
    assert len(despues.discos) == len(grande.discos) and len(despues.redes) == len(grande.redes)
    assert (despues.vmid, despues.nombre, despues.nodo) == (antes.vmid, antes.nombre, antes.nodo)
    assert v.bloque_lote.cantidad_valor() == 5
    assert v.bloque_lote.patron() == patron_antes
    assert v.bloque_lote.destino() == destino_antes
    assert v.selector_perfil.perfil_actual_id == FABRICA_GRANDE


def test_ca_p05_7_aplicar_un_perfil_no_envia_ninguna_escritura(qtbot, entorno3, modales, archivos):
    cliente = conectar3(qtbot, entorno3)
    antes = len(cliente.llamadas)
    elegir_perfil(entorno3.ventana, FABRICA_GRANDE)
    assert not hubo_escritura(cliente)
    assert len(cliente.llamadas) == antes  # tampoco lecturas: aplicar es local (INV-M1)
    assert modales.vistos == []  # sin cambios manuales no se pregunta (CA-P05.2)


def test_ca_p05_5_aplicar_perfil_invalida_el_resumen_previo_y_revalida(qtbot, conectado):
    v = conectado
    elegir_perfil(v, "fabrica.minimo")
    esperar_validacion(qtbot, v)
    assert v.resumen_lote.plan is None
    assert v.statusBar().currentMessage().startswith("Perfil «")


# --- «(modificado)» y «Personalizado» (CA-P05.8) -------------------------------------------------


def test_ca_p05_8_editar_un_campo_muestra_el_perfil_con_modificado(qtbot, conectado):
    v = conectado
    editar_nucleos(qtbot, v, "6")
    assert v.selector_perfil.modificado
    assert v.selector_perfil.texto_combo.endswith("(modificado)")
    assert v.selector_perfil.texto_combo.startswith("Servidor pequeño")


def test_ca_p05_8_devolver_el_campo_a_su_valor_quita_el_modificado(qtbot, conectado):
    v = conectado
    original = v.formulario.cores.text()
    editar_nucleos(qtbot, v, "6")
    editar_nucleos(qtbot, v, original)
    assert not v.selector_perfil.modificado
    assert "(modificado)" not in v.selector_perfil.texto_combo


def test_ca_p05_8_aplicar_el_perfil_de_nuevo_quita_el_modificado(qtbot, conectado, modales):
    v = conectado
    editar_nucleos(qtbot, v, "6")
    modales.pulsar(QMessageBox, "Reemplazar")
    elegir_perfil(v, ID_PREDETERMINADO)
    assert not v.selector_perfil.modificado


def test_un_lote_cargado_deja_el_selector_en_personalizado(
    qtbot, entorno3, modales, archivos, ruta_lote_homogeneo
):
    cliente = conectar3(qtbot, entorno3)
    v = entorno3.ventana
    archivos.abrir.append(ruta_lote_homogeneo)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: "cargado" in v.statusBar().currentMessage(), timeout=3000)
    assert v.selector_perfil.perfil_actual_id is None
    assert v.selector_perfil.texto_combo == "Personalizado"
    assert not hubo_escritura(cliente)


def test_eliminar_el_perfil_aplicado_pasa_el_selector_a_personalizado(qtbot, conectado):
    v = conectado
    perfil = crear_perfil_usuario(v, "Efímero")
    v.selector_perfil.marcar_aplicado(perfil.id)
    assert v.selector_perfil.perfil_actual_id == perfil.id
    v._almacen_perfiles.eliminar(perfil.id)
    v._al_cambiar_lista_perfiles(frozenset({perfil.id}))
    assert v.selector_perfil.perfil_actual_id is None
    assert v.selector_perfil.texto_combo == "Personalizado"


def test_elegir_personalizado_en_el_combo_no_aplica_nada(qtbot, conectado, modales):
    v = conectado
    antes = v.formulario.configuracion()
    combo = v.selector_perfil.combo
    combo.setCurrentIndex(0)
    combo.activated.emit(0)
    assert v.formulario.configuracion() == antes
    assert v.selector_perfil.perfil_actual_id == ID_PREDETERMINADO
    assert modales.vistos == []


# --- Confirmaciones con foco en «Cancelar» (CA-P05.2) ---------------------------------------------


def test_ca_p05_2_con_cambios_manuales_se_pide_confirmar_con_foco_en_cancelar(
    qtbot, conectado, modales
):
    v = conectado
    editar_nucleos(qtbot, v, "6")
    vistos: dict[str, object] = {}

    def _ver(caja: QMessageBox) -> None:
        vistos["texto"] = caja.text()
        vistos["defecto"] = caja.defaultButton().text()
        vistos["escape"] = caja.escapeButton().text()
        vistos["botones"] = sorted(b.text() for b in caja.buttons())

    modales.responder(QMessageBox, _ver)  # sin pulsar nada: se cierra como «Cancelar»
    elegir_perfil(v, FABRICA_GRANDE)
    assert vistos["texto"] == MENSAJE_REEMPLAZO
    assert vistos["defecto"] == "Cancelar" and vistos["escape"] == "Cancelar"
    assert vistos["botones"] == ["Cancelar", "Reemplazar"]


def test_ca_p05_2_cancelar_conserva_los_cambios_manuales_y_el_perfil_anterior(
    qtbot, conectado, modales
):
    v = conectado
    editar_nucleos(qtbot, v, "6")
    modales.pulsar(QMessageBox, "Cancelar")
    elegir_perfil(v, FABRICA_GRANDE)
    assert v.formulario.cores.text() == "6"
    assert v.selector_perfil.perfil_actual_id == ID_PREDETERMINADO
    assert v.selector_perfil.texto_combo.endswith("(modificado)")
    # El combo vuelve a mostrar el perfil aplicado, no el elegido y cancelado.
    assert v.selector_perfil.combo.currentIndex() == v.selector_perfil.combo.findData(
        ID_PREDETERMINADO
    )


def test_ca_p05_2_reemplazar_aplica_el_perfil_elegido(qtbot, conectado, modales):
    v = conectado
    editar_nucleos(qtbot, v, "6")
    modales.pulsar(QMessageBox, "Reemplazar")
    elegir_perfil(v, FABRICA_GRANDE)
    grande = v._almacen_perfiles.obtener(FABRICA_GRANDE).config
    assert v.formulario.cores.text() == str(grande.cores)
    assert v.selector_perfil.perfil_actual_id == FABRICA_GRANDE
    assert not v.selector_perfil.modificado


def test_ca_p05_2_cerrar_la_confirmacion_con_escape_no_reemplaza(qtbot, conectado, modales):
    v = conectado
    editar_nucleos(qtbot, v, "6")
    modales.responder(QMessageBox, lambda caja: caja.escapeButton().click())
    elegir_perfil(v, FABRICA_GRANDE)
    assert v.formulario.cores.text() == "6"


# --- «Guardar cambios en el perfil «X»» --------------------------------------------------------


def test_el_boton_de_actualizar_no_existe_para_los_perfiles_de_fabrica(qtbot, conectado):
    editar_nucleos(qtbot, conectado, "6")
    assert conectado.selector_perfil.modificado
    assert not conectado.selector_perfil.boton_actualizar.isVisibleTo(conectado)


def test_el_boton_de_actualizar_aparece_solo_con_un_perfil_de_usuario_modificado(qtbot, conectado):
    v = conectado
    perfil = crear_perfil_usuario(v, "Mi base")
    v.selector_perfil.marcar_aplicado(perfil.id)
    assert not v.selector_perfil.boton_actualizar.isVisibleTo(v)
    editar_nucleos(qtbot, v, "7")
    boton = v.selector_perfil.boton_actualizar
    assert boton.isVisibleTo(v)
    assert boton.text() == "Guardar cambios en el perfil «Mi base»"
    assert boton.accessibleName() == boton.text()


def test_actualizar_perfil_pide_confirmar_con_foco_en_cancelar_y_cancelar_no_toca_el_almacen(
    qtbot, conectado, modales
):
    v = conectado
    perfil = crear_perfil_usuario(v, "Mi base")
    v.selector_perfil.marcar_aplicado(perfil.id)
    editar_nucleos(qtbot, v, "7")
    vistos: dict[str, str] = {}

    def _cancelar(caja: QMessageBox) -> None:
        vistos["texto"] = caja.text()
        vistos["defecto"] = caja.defaultButton().text()
        pulsar_boton(caja, "Cancelar")

    modales.responder(QMessageBox, _cancelar)
    v.selector_perfil.boton_actualizar.click()
    assert vistos["defecto"] == "Cancelar"
    assert "«Mi base»" in vistos["texto"]
    assert v._almacen_perfiles.obtener(perfil.id).config.cores == perfil.config.cores
    assert v.selector_perfil.modificado  # sigue habiendo cambios sin guardar en el perfil


def test_actualizar_perfil_confirmado_guarda_el_hardware_en_el_almacen(qtbot, conectado, modales):
    v = conectado
    perfil = crear_perfil_usuario(v, "Mi base")
    v.selector_perfil.marcar_aplicado(perfil.id)
    editar_nucleos(qtbot, v, "7")
    modales.pulsar(QMessageBox, "Guardar cambios")
    v.selector_perfil.boton_actualizar.click()
    assert v._almacen_perfiles.obtener(perfil.id).config.cores == 7
    assert v.statusBar().currentMessage() == "Perfil «Mi base» actualizado"


def test_ca_p05_8_tras_actualizar_el_perfil_el_formulario_ya_no_esta_modificado(
    qtbot, conectado, modales
):
    """El formulario coincide con el perfil recién actualizado: ni «(modificado)» ni el botón."""
    v = conectado
    perfil = crear_perfil_usuario(v, "Mi base")
    v.selector_perfil.marcar_aplicado(perfil.id)
    editar_nucleos(qtbot, v, "7")
    modales.pulsar(QMessageBox, "Guardar cambios")
    v.selector_perfil.boton_actualizar.click()
    assert not v.selector_perfil.modificado
    assert "(modificado)" not in v.selector_perfil.texto_combo
    assert not v.selector_perfil.boton_actualizar.isVisibleTo(v)


# --- Guardar como perfil de máquina (RF-P03) ---------------------------------------------------


def _guardar_perfil_por_menu(qtbot, v, modales: Modales, nombre: str) -> None:
    def _rellenar(d: DialogoGuardarPerfil) -> None:
        d.campo_nombre.setText(nombre)
        pulsar_boton(d, "Guardar perfil")

    modales.responder(DialogoGuardarPerfil, _rellenar)
    v._accion_guardar_perfil.trigger()


def test_guardar_como_perfil_lo_agrega_al_selector_y_no_guarda_datos_de_la_maquina(
    qtbot, entorno3, modales
):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    v.formulario.nombre.setText("srv-secreto-01")
    v.formulario.nombre.textEdited.emit("srv-secreto-01")
    editar_nucleos(qtbot, v, "5")
    _guardar_perfil_por_menu(qtbot, v, modales, "Con cinco núcleos")
    nuevo = [p for p in v._almacen_perfiles.todos() if p.nombre == "Con cinco núcleos"]
    assert len(nuevo) == 1 and nuevo[0].origen == OrigenPerfil.USUARIO
    assert nuevo[0].config.cores == 5
    assert v.selector_perfil.perfil_actual_id == nuevo[0].id
    assert v.statusBar().currentMessage() == "Perfil «Con cinco núcleos» guardado"
    # CA-P01.1: ni nombre, ni VMID, ni nodo de la máquina en el archivo.
    archivo = Path(v._deps.perfiles.ruta).with_name("perfiles_maquina.json")
    contenido = archivo.read_text(encoding="utf-8")
    assert "srv-secreto-01" not in contenido
    claves = set(_claves_recursivas(json.loads(contenido)))
    assert not claves & {"vmid", "nombre_vm", "nodo", "etiquetas"}


def _claves_recursivas(dato):
    if isinstance(dato, dict):
        for k, v in dato.items():
            yield k
            yield from _claves_recursivas(v)
    elif isinstance(dato, list):
        for x in dato:
            yield from _claves_recursivas(x)


def test_ca_p05_8_tras_guardar_como_perfil_el_selector_no_dice_modificado(qtbot, entorno3, modales):
    """El perfil nuevo se creó con el hardware del formulario: son iguales por definición."""
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    editar_nucleos(qtbot, v, "5")
    _guardar_perfil_por_menu(qtbot, v, modales, "Con cinco núcleos")
    assert not v.selector_perfil.modificado
    assert "(modificado)" not in v.selector_perfil.texto_combo
    assert not v.selector_perfil.boton_actualizar.isVisibleTo(v)


def test_guardar_como_perfil_cancelado_no_crea_nada(qtbot, entorno3, modales):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    antes = len(v._almacen_perfiles.todos())
    modales.responder(DialogoGuardarPerfil, lambda d: pulsar_boton(d, "Cancelar"))
    v._accion_guardar_perfil.trigger()
    assert len(v._almacen_perfiles.todos()) == antes


def test_el_dialogo_de_guardar_perfil_rechaza_un_nombre_repetido(qtbot, entorno3, modales):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    crear_perfil_usuario(v, "Repetido")
    vistos: dict[str, object] = {}

    def _ver(d: DialogoGuardarPerfil) -> None:
        d.campo_nombre.setText("repetido")  # sin distinguir mayúsculas
        vistos["aceptar"] = d.boton_aceptar.isEnabled()
        vistos["error"] = d.error_nombre.text()
        pulsar_boton(d, "Cancelar")

    modales.responder(DialogoGuardarPerfil, _ver)
    v._accion_guardar_perfil.trigger()
    assert vistos["aceptar"] is False and vistos["error"]


# --- Pistas (RF-P06) -----------------------------------------------------------------------------


def test_rf_p06_una_pista_de_storage_inexistente_avisa_y_usa_uno_valido(qtbot, conectado, modales):
    from dataclasses import replace

    from proxlaunch.nucleo.perfiles_maquina.aplicar import config_desde_configuracion

    v = conectado
    config = config_desde_configuracion(v.formulario.configuracion(), con_pistas=True)
    config = replace(
        config, discos=tuple(replace(d, storage_preferido="no-existe") for d in config.discos)
    )
    perfil = v._almacen_perfiles.crear("Pista mala", "", config)
    v._recargar_selector(None)
    elegir_perfil(v, perfil.id)
    assert "no-existe" in v.selector_perfil.texto_avisos
    assert v.formulario.configuracion().discos[0].storage != "no-existe"
    assert modales.vistos == []


# --- Administrar perfiles (avanzado) --------------------------------------------------------------


def test_administrar_perfiles_solo_se_ofrece_en_modo_avanzado(qtbot, conectado):
    v = conectado
    assert not v._accion_administrar_perfiles.isVisible()
    assert not v.selector_perfil.boton_administrar.isVisibleTo(v)
    v.establecer_modo(Modo.AVANZADO)
    assert v._accion_administrar_perfiles.isVisible()
    assert v.selector_perfil.boton_administrar.isVisibleTo(v)
    v.establecer_modo(Modo.BASICO)
    assert not v._accion_administrar_perfiles.isVisible()


def test_administrar_perfiles_abre_el_gestor_y_sus_cambios_llegan_al_selector(
    qtbot, conectado, modales
):
    v = conectado
    perfil = crear_perfil_usuario(v, "Para borrar")
    v.selector_perfil.marcar_aplicado(perfil.id)

    def _borrar_y_cerrar(d: DialogoPerfilesMaquina) -> None:
        v._almacen_perfiles.eliminar(perfil.id)
        d.perfiles_cambiados.emit(frozenset({perfil.id}))

    modales.responder(DialogoPerfilesMaquina, _borrar_y_cerrar)
    v._accion_administrar_perfiles.trigger()
    assert modales.de_clase(DialogoPerfilesMaquina)
    assert v.selector_perfil.perfil_actual_id is None
    assert v.selector_perfil.combo.findData(perfil.id) < 0


# --- Lote en ejecución (CA-P05.6) -----------------------------------------------------------------


def test_ca_p05_6_con_un_lote_en_ejecucion_el_selector_y_las_acciones_de_perfil_se_deshabilitan(
    qtbot, entorno3, modales, archivos, limpieza
):
    from .apoyo_ventana_lote import crear_lote, preparar_lote, ver_resumen

    puerta = {101: __import__("threading").Event()}
    preparar_lote(qtbot, entorno3, cantidad=3, creacion=CreacionPorVmid(puertas=puerta))
    v = entorno3.ventana
    ver_resumen(qtbot, v)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: v._lote_en_curso, timeout=4000)
    s = v.selector_perfil
    assert not s.combo.isEnabled()
    assert not s.boton_guardar.isEnabled() and not s.boton_actualizar.isEnabled()
    assert not v._accion_guardar_perfil.isEnabled()
    assert not v._accion_administrar_perfiles.isEnabled()
    # Aunque alguien emita la señal, no se aplica nada.
    antes = v.formulario.configuracion()
    s.perfil_elegido.emit(FABRICA_GRANDE)
    assert v.formulario.configuracion() == antes
    assert modales.vistos == []


# --- Fixtures locales ---------------------------------------------------------------------------


@pytest.fixture
def ruta_lote_homogeneo(tmp_path):
    """Lote guardado válido (3 máquinas «web») escrito con el núcleo."""
    from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote
    from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado

    from .apoyo_lote import definicion

    ruta = tmp_path / "base.proxlaunch-lote.json"
    guardar_lote(ruta, LoteGuardado("base", definicion(3, "web")), app_version="0.1.0")
    return ruta
