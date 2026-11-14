"""«Administrar perfiles de máquina» (avanzado): eliminar con foco en «Cancelar», perfiles de
fábrica no modificables, duplicar, renombrar, exportar sin pistas por defecto e importar con
conflictos (RF-P02, RF-P04, RF-P08, RF-P09, RF-P10; CA-P02.2, CA-P04.4, CA-P08.2, CA-P09.x).

El diálogo se usa directamente con un almacén en ``tmp_path``; los diálogos anidados y de archivo
pasan por los registros de ``apoyo_mvp3`` (ninguno modal real).
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoNombrePerfil
from proxlaunch.interfaz.dialogos.importar_perfiles import DialogoImportarPerfiles
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina, _DialogoExportar
from proxlaunch.interfaz.textos import textos_perfiles_fabrica
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import exportar_perfiles
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    RedPerfil,
)

from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .apoyo_mvp3 import pulsar_boton


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenPerfilesMaquina(
        tmp_path / "perfiles_maquina.json",
        fabrica=perfiles_fabrica(textos_perfiles_fabrica()),
        app_version="0.1.0",
    )
    a.cargar()
    return a


def config_propia(cores: int = 3, storage: str | None = "mi-storage") -> ConfigPerfil:
    return ConfigPerfil(
        cores=cores,
        discos=(DiscoPerfil(30, storage_preferido=storage),),
        redes=(RedPerfil(bridge_preferido="mi-bridge"),),
    )


@pytest.fixture
def gestor(qtbot, almacen, modales, archivos):
    d = DialogoPerfilesMaquina(almacen, Lanzador(), app_version="0.1.0")
    qtbot.addWidget(d)
    d.show()
    return d


# --- Fábrica no se modifica (CA-P02.2) ---------------------------------------------------------


def test_ca_p02_2_un_perfil_de_fabrica_no_se_puede_renombrar_ni_eliminar_y_dice_por_que(gestor):
    gestor.tabla.selectRow(0)
    assert gestor.seleccionados()[0].origen == OrigenPerfil.FABRICA
    assert not gestor.boton_renombrar.isEnabled() and not gestor.boton_eliminar.isEnabled()
    assert gestor.boton_duplicar.isEnabled() and gestor.boton_usar.isEnabled()
    assert gestor.nota_fabrica.isVisibleTo(gestor)
    assert "Duplícalo" in gestor.nota_fabrica.text()


def test_la_lista_dice_de_fabrica_o_propio_con_texto_y_no_solo_color(gestor, almacen):
    almacen.crear("Mío", "", config_propia())
    gestor.recargar()
    m = gestor.modelo
    tipos = [m.data(m.index(r, 1)) for r in range(m.rowCount())]
    assert tipos[0] == "De fábrica" and tipos[-1] == "Propio"
    assert tipos.index("Propio") > max(i for i, t in enumerate(tipos) if t == "De fábrica")


# --- Duplicar y renombrar ----------------------------------------------------------------------


def test_duplicar_un_perfil_de_fabrica_crea_uno_propio_editable(gestor, almacen, modales):
    gestor.seleccionar("fabrica.minimo")
    cambios: list[object] = []
    gestor.perfiles_cambiados.connect(cambios.append)

    def _nombre(d: DialogoNombrePerfil) -> None:
        d.campo_nombre.setText("Mínimo mejorado")
        d.boton_aceptar.click()

    modales.responder(DialogoNombrePerfil, _nombre)
    gestor.boton_duplicar.click()
    copia = almacen.buscar_por_nombre("Mínimo mejorado")
    assert len(copia) == 1 and copia[0].origen == OrigenPerfil.USUARIO
    assert "Mínimo mejorado" in gestor.estado.text()
    assert cambios == [frozenset()]  # solo se añadió: el selector no pasa a «Personalizado»


def test_renombrar_no_cambia_el_hardware_y_avisa_al_selector(gestor, almacen, modales):
    perfil = almacen.crear("Viejo", "", config_propia(cores=5))
    gestor.recargar(perfil.id)
    cambios: list[object] = []
    gestor.perfiles_cambiados.connect(cambios.append)

    def _nombre(d: DialogoNombrePerfil) -> None:
        d.campo_nombre.setText("Nuevo")
        d.boton_aceptar.click()

    modales.responder(DialogoNombrePerfil, _nombre)
    gestor.boton_renombrar.click()
    renombrado = almacen.obtener(perfil.id)
    assert renombrado.nombre == "Nuevo" and renombrado.config.cores == 5
    assert cambios == [frozenset({perfil.id})]


def test_duplicar_con_nombre_repetido_deja_el_boton_aceptar_deshabilitado(gestor, almacen, modales):
    almacen.crear("Repetido", "", config_propia())
    gestor.recargar()
    gestor.seleccionar("fabrica.minimo")
    vistos: dict[str, object] = {}

    def _nombre(d: DialogoNombrePerfil) -> None:
        d.campo_nombre.setText("repetido")  # sin distinguir mayúsculas
        vistos["aceptar"] = d.boton_aceptar.isEnabled()
        vistos["error"] = d.error_nombre.text()
        d.reject()

    modales.responder(DialogoNombrePerfil, _nombre)
    gestor.boton_duplicar.click()
    assert vistos["aceptar"] is False and vistos["error"]


# --- Eliminar con foco en «Cancelar» (CA-P04.4) --------------------------------------------------


def test_ca_p04_4_eliminar_confirma_con_el_nombre_y_foco_en_cancelar(gestor, almacen, modales):
    perfil = almacen.crear("Para borrar", "", config_propia())
    gestor.recargar(perfil.id)
    visto: dict[str, str] = {}

    def _caja(caja: QMessageBox) -> None:
        visto["texto"] = caja.text()
        visto["defecto"] = caja.defaultButton().text()
        visto["escape"] = caja.escapeButton().text()
        pulsar_boton(caja, "Cancelar")

    modales.responder(QMessageBox, _caja)
    gestor.boton_eliminar.click()
    assert "«Para borrar»" in visto["texto"]
    assert visto["defecto"] == "Cancelar" and visto["escape"] == "Cancelar"
    assert almacen.obtener(perfil.id).nombre == "Para borrar"  # Cancelar no borra


def test_ca_p04_5_eliminar_confirmado_borra_y_avisa_al_selector(gestor, almacen, modales):
    perfil = almacen.crear("Para borrar", "", config_propia())
    gestor.recargar(perfil.id)
    cambios: list[object] = []
    gestor.perfiles_cambiados.connect(cambios.append)
    modales.pulsar(QMessageBox, "Eliminar")
    gestor.boton_eliminar.click()
    assert almacen.buscar_por_nombre("Para borrar") == []
    assert cambios == [frozenset({perfil.id})]
    assert gestor.estado.text() == "Se eliminó «Para borrar»."


# --- Exportar e importar (RF-P08, RF-P09) ------------------------------------------------------


def test_ca_p08_2_exportar_deja_desmarcada_la_casilla_de_pistas_y_no_lleva_credenciales(
    qtbot, gestor, almacen, modales, archivos, tmp_path
):
    perfil = almacen.crear("Con pistas", "", config_propia())
    gestor.recargar(perfil.id)
    destino = tmp_path / "salida.proxlaunch-perfiles.json"
    archivos.guardar.append(destino)
    vistos: dict[str, object] = {}

    def _exportar(d: _DialogoExportar) -> None:
        vistos["pistas"] = d.casilla_pistas.isChecked()
        d.boton_exportar.click()

    modales.responder(_DialogoExportar, _exportar)
    gestor.boton_exportar.click()
    qtbot.waitUntil(destino.exists, timeout=3000)
    qtbot.waitUntil(lambda: "exportó" in gestor.estado.text(), timeout=3000)
    contenido = destino.read_text(encoding="utf-8")
    assert vistos["pistas"] is False
    assert "mi-storage" not in contenido and "mi-bridge" not in contenido
    assert json.loads(contenido)["formato"] == "proxlaunch.perfiles"
    assert gestor.estado.text() == "Se exportó 1 perfil."


def test_ca_p08_2_exportar_con_pistas_las_incluye(
    qtbot, gestor, almacen, modales, archivos, tmp_path
):
    perfil = almacen.crear("Con pistas", "", config_propia())
    gestor.recargar(perfil.id)
    destino = tmp_path / "salida.proxlaunch-perfiles.json"
    archivos.guardar.append(destino)
    modales.responder(
        _DialogoExportar, lambda d: (d.casilla_pistas.setChecked(True), d.boton_exportar.click())
    )
    gestor.boton_exportar.click()
    qtbot.waitUntil(destino.exists, timeout=3000)
    qtbot.waitUntil(lambda: "exportó" in gestor.estado.text(), timeout=3000)
    assert "mi-storage" in destino.read_text(encoding="utf-8")


def test_exportar_con_la_ruta_cancelada_no_escribe(
    qtbot, gestor, almacen, modales, archivos, tmp_path
):
    gestor.seleccionar("fabrica.minimo")
    archivos.guardar.append(None)
    modales.responder(_DialogoExportar, lambda d: d.boton_exportar.click())
    gestor.boton_exportar.click()
    qtbot.wait(50)
    assert list(tmp_path.glob("*.json")) == [tmp_path / "perfiles_maquina.json"] or not list(
        tmp_path.glob("*.proxlaunch-perfiles.json")
    )


def test_el_boton_importar_pide_el_archivo_al_usuario_y_lo_lee(
    qtbot, gestor, almacen, archivos, tmp_path
):
    """El botón «Importar…» debe abrir el selector de archivos de perfiles y leer lo elegido.

    ``clicked`` emite ``checked`` (``False``); la señal no debe confundirse con una ruta.
    """
    from .apoyo_mvp3 import definicion_homogenea, escribir_lote_guardado

    ruta = escribir_lote_guardado(tmp_path / "l.proxlaunch-lote.json", definicion_homogenea())
    archivos.abrir.append(ruta)
    gestor.boton_importar.click()
    assert len(archivos.pedidos_abrir) == 1  # se pidió el archivo con el selector del sistema
    qtbot.waitUntil(lambda: bool(gestor.error.text()), timeout=3000)
    assert "Parece un archivo de lote" in gestor.error.text()  # y se leyó la ruta elegida


def test_importar_un_archivo_ajeno_dice_que_parece_un_lote_y_no_cambia_nada(
    qtbot, gestor, almacen, archivos, tmp_path
):
    from .apoyo_mvp3 import definicion_homogenea, escribir_lote_guardado

    lote = escribir_lote_guardado(tmp_path / "l.proxlaunch-lote.json", definicion_homogenea())
    antes = len(almacen.todos())
    archivos.abrir.append(lote)
    gestor.importar()
    qtbot.waitUntil(lambda: "Parece un archivo de lote" in gestor.error.text(), timeout=3000)
    assert len(almacen.todos()) == antes


def test_ca_p09_importar_con_un_nombre_repetido_ofrece_conservar_ambos_reemplazar_u_omitir(
    qtbot, gestor, almacen, modales, archivos, tmp_path
):
    existente = almacen.crear("Servidor web", "", config_propia(cores=2))
    otro = almacen.crear("Servidor web (otro)", "", config_propia(cores=7))
    # Archivo con un perfil que se llama como el existente.
    archivo = tmp_path / "in.proxlaunch-perfiles.json"
    from dataclasses import replace

    exportar_perfiles(
        archivo, [replace(otro, nombre="Servidor web")], con_pistas=False, app_version="0.1.0"
    )
    archivos.abrir.append(archivo)
    vistos: dict[str, object] = {}

    def _revisar(d: DialogoImportarPerfiles) -> None:
        d.tabla.selectRow(0)
        vistos["radios"] = [d.radio_ambos.text(), d.radio_reemplazar.text(), d.radio_omitir.text()]
        vistos["conflicto"] = d.grupo_conflicto.isVisibleTo(d)
        d.radio_reemplazar.click()
        pulsar_boton(d, d.boton_importar.text())

    def _confirmar_reemplazo(caja: QMessageBox) -> None:
        vistos["defecto"] = caja.defaultButton().text()
        pulsar_boton(caja, "Cancelar")

    modales.responder(DialogoImportarPerfiles, _revisar)
    modales.responder(QMessageBox, _confirmar_reemplazo)
    gestor.importar()
    qtbot.waitUntil(lambda: "defecto" in vistos, timeout=4000)
    assert vistos["conflicto"] is True
    assert vistos["defecto"] == "Cancelar"  # reemplazar pide confirmación con foco en «Cancelar»
    assert len(vistos["radios"]) == 3
    assert almacen.obtener(existente.id).config.cores == 2  # no se reemplazó
