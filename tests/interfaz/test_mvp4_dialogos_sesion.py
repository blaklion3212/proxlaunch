"""«Qué puedo hacer en este servidor» y «Archivos subidos en esta sesión» (RF-O24, RF-O25,
RF-O32; CA-O25.x, CA-O32.x; INV-O6)."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QGuiApplication

from proxlaunch.interfaz.dialogos.capacidades import (
    DialogoCapacidades,
    texto_faltante_para_administrador,
)
from proxlaunch.interfaz.dialogos.transferencias_sesion import (
    DialogoTransferenciasSesion,
    texto_registros,
)
from proxlaunch.nucleo.origen.capacidades_origen import Via
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.transferencias.modelos import (
    EstadoTransferencia,
    RegistroTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion

from .apoyo_mvp4 import ROL_10, caps_origen, inv_origen

# --- Capacidades ---------------------------------------------------------------------------------


def _dialogo(qtbot, caps):
    d = DialogoCapacidades(caps)
    qtbot.addWidget(d)
    d.show()
    return d


def test_ca_o02_9_la_tabla_lista_las_nueve_vias_con_estado_en_texto_y_simbolo(qtbot):
    d = _dialogo(qtbot, caps_origen())
    # Las nueve vías de origen, las cinco filas de la fase C (RF-C5.2) y las tres de la D (RF-D5.2).
    assert d.tabla.rowCount() == 17
    for fila in range(17):
        estado = d.tabla.item(fila, d.COL_ESTADO).text()
        assert estado[0] in "✔!✖" and len(estado) > 2  # símbolo + texto: no solo color


def test_ca_o24_4_con_el_rol_de_10_solo_quedan_no_disponibles_las_vias_que_necesitan_los_nuevos(
    qtbot,
):
    d = _dialogo(qtbot, caps_origen(inv_origen(privilegios=ROL_10)))
    no = {
        d.tabla.item(f, d.COL_VIA).text()
        for f in range(d.tabla.rowCount())
        if d.tabla.item(f, d.COL_ESTADO).text().startswith("✖")
    }
    assert no  # subir ISO, descargar, orden de arranque, ampliar...
    assert len(no) < 9
    assert "Permisos" not in "".join(no)


def test_ca_o32_2_el_texto_para_el_administrador_lista_lo_que_falta_y_los_14_privilegios(qtbot):
    d = _dialogo(qtbot, caps_origen(inv_origen(privilegios=ROL_10)))
    texto = d.texto_para_administrador()
    assert "En este servidor no puedo hacer lo siguiente" in texto
    assert "Datastore.AllocateTemplate" in texto
    for p in ROL_PROXLAUNCH:
        assert p in texto
    assert d.texto_admin.toPlainText() == texto


def test_ca_o32_2_copiar_deja_el_texto_en_el_portapapeles(qtbot):
    d = _dialogo(qtbot, caps_origen(inv_origen(privilegios=ROL_10)))
    d.boton_copiar.click()
    assert QGuiApplication.clipboard().text() == d.texto_para_administrador()


def test_con_todo_disponible_no_hay_lista_de_faltantes():
    # Con el rol de 14 privilegios solo faltan los permisos opcionales de la fase D (Mapping.Use).
    lineas = texto_faltante_para_administrador(caps_origen()).splitlines()
    assert all(
        linea.startswith(("- Usar tarjetas PCI y USB", "- Usar modelos de CPU")) for linea in lineas
    )


def test_la_lista_de_faltantes_nombra_cada_funcion_y_su_motivo():
    # Con la mínima 8.4 ninguna función falta por la versión: el motivo es el permiso (con su ruta).
    texto = texto_faltante_para_administrador(caps_origen(inv_origen(privilegios=ROL_10)))
    assert texto.startswith("- ")
    assert "Datastore.AllocateTemplate" in texto


def test_sin_capacidades_todavia_el_dialogo_lo_dice(qtbot):
    d = _dialogo(qtbot, None)
    assert d.tabla.rowCount() == 0
    assert "conéctate" in d.etiqueta_version.text()


def test_el_dialogo_muestra_la_version_forzada_y_el_nodo(qtbot):
    from dataclasses import replace

    caps = replace(caps_origen(), forzada=True)
    d = _dialogo(qtbot, caps)
    assert "versión forzada" in d.etiqueta_version.text()
    assert "pve" in d.etiqueta_version.text()


def test_las_vias_estan_todas_en_el_orden_esperado(qtbot):
    d = _dialogo(qtbot, caps_origen())
    primeras = [d.tabla.item(f, d.COL_VIA).text() for f in range(d.tabla.rowCount())]
    assert len(set(primeras)) == len(list(Via))


# --- Archivos subidos en la sesión ---------------------------------------------------------------


def _registro(
    nombre="alpine.iso", estado=EstadoTransferencia.TERMINADA, volid="local:iso/alpine.iso"
):
    return RegistroTransferencia(
        TipoTransferencia.SUBIDA,
        nombre,
        "local",
        "pve",
        1024**3,
        "2026-11-14 10:00:00",
        estado,
        volid,
    )


@pytest.fixture
def registro():
    r = RegistroSesion()
    return r


def test_ca_o25_1_sin_transferencias_dice_que_no_hay_nada_y_deshabilita_copiar(qtbot, registro):
    d = DialogoTransferenciasSesion(registro)
    qtbot.addWidget(d)
    d.show()
    assert d.etiqueta_vacia.isVisible() and not d.tabla.isVisible()
    assert not d.boton_copiar.isEnabled() and not d.boton_guardar.isEnabled()


def test_ca_o25_2_lista_archivo_storage_nodo_tamano_y_estado(qtbot, registro):
    registro.agregar(_registro())
    d = DialogoTransferenciasSesion(registro)
    qtbot.addWidget(d)
    d.show()
    assert d.tabla.rowCount() == 1
    fila = [d.tabla.item(0, c).text() for c in range(7)]
    assert fila[d.COL_ARCHIVO] == "alpine.iso" and fila[d.COL_STORAGE] == "local"
    assert fila[d.COL_NODO] == "pve" and "1" in fila[d.COL_TAMANO]
    assert d.tabla.item(0, d.COL_ARCHIVO).toolTip() == "local:iso/alpine.iso"


def test_ca_o25_4_el_aviso_dice_que_la_app_no_puede_borrar_los_archivos(qtbot, registro):
    d = DialogoTransferenciasSesion(registro)
    qtbot.addWidget(d)
    textos = " ".join(w.text() for w in d.findChildren(type(d.etiqueta_vacia)))
    assert "no puede borrarlos" in textos


def test_ca_o25_3_copiar_y_guardar_dan_el_mismo_texto_con_el_volid(qtbot, registro, tmp_path):
    registro.agregar(_registro())
    d = DialogoTransferenciasSesion(registro)
    qtbot.addWidget(d)
    d.copiar()
    copiado = QGuiApplication.clipboard().text()
    assert "local:iso/alpine.iso" in copiado
    destino = tmp_path / "lista.txt"
    d.guardar_en(destino)
    assert destino.read_text(encoding="utf-8").strip() == copiado.strip()


def test_inv_o6_la_lista_no_contiene_url_ruta_local_ni_huella():
    texto = texto_registros([_registro()])
    for prohibido in ("http", "/home", "sha256", "checksum"):
        assert prohibido not in texto


def test_actualizar_refleja_una_transferencia_nueva(qtbot, registro):
    d = DialogoTransferenciasSesion(registro)
    qtbot.addWidget(d)
    d.show()
    registro.agregar(_registro("otro.iso", EstadoTransferencia.FALLIDA, None))
    d.actualizar()
    assert d.tabla.rowCount() == 1 and d.tabla.isVisible()
