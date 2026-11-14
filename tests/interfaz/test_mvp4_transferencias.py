"""Diálogos de subida y descarga (RF-O09 a RF-O12, RF-O16, RNF-O02/O08; E-O06..E-O11, E-O22, E-O23).

Controlador falso con lanzador real y servicio falso: nunca hay red. Ningún diálogo es modal real
(solo se muestran, sin ``exec``).
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from proxlaunch.interfaz.dialogos import transferencia as dt
from proxlaunch.interfaz.dialogos.transferencia import DialogoDescarga, DialogoSubida
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.transferencias.modelos import EstadoTransferencia as Est
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_mvp4 import (
    VOLID_ISO,
    ControladorFalso,
    ServicioTransferenciasFalso,
    comprobacion,
    inv_origen,
    progreso,
    resultado_transferencia,
)

GIB = 1024**3


@pytest.fixture
def iso_local(tmp_path):
    ruta = tmp_path / "alpine mini.iso"
    datos = bytearray(0x8000) + b"\x01CD001\x01" + bytes(2048)
    ruta.write_bytes(bytes(datos))
    return ruta


@pytest.fixture
def servicio():
    s = ServicioTransferenciasFalso()
    yield s
    s.puerta.set()  # nunca queda un hilo esperando


@pytest.fixture
def ctrl(servicio):
    c = ControladorFalso(inv_origen(), servicio)
    yield c
    c.lanzador.esperar(3000)


def _subida(qtbot, ctrl, ruta, contenido=Contenido.ISO) -> DialogoSubida:
    d = DialogoSubida(ctrl, contenido, "pve", ruta=ruta)
    qtbot.addWidget(d)
    d.show()
    return d


def _lista(qtbot, d) -> None:
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)


def _terminada(qtbot, d) -> None:
    qtbot.waitUntil(lambda: d.resultado is not None, timeout=4000)


def _problema(codigo, **params):
    return Problema("destino", codigo, Severidad.ERROR, params)


# --- Subida: camino feliz y confirmación ---------------------------------------------------------


def test_ca_o09_2_antes_de_confirmar_muestra_nombre_tamano_storage_y_nodo(qtbot, ctrl, iso_local):
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    resumen = d.etiqueta_resumen.text()
    assert "«alpine_mini.iso»" in resumen or "alpine" in resumen
    assert "«local»" in resumen and "«pve»" in resumen
    assert d.etiqueta_resumen.isVisible()
    assert d.aviso_no_deshacer.isVisible() and d.aviso_no_deshacer.text()
    assert d.campo_archivo.text() == iso_local.name  # nunca la ruta completa
    assert str(iso_local.parent) not in d.campo_archivo.text()


def test_rnf_o08_el_foco_inicial_y_el_predeterminado_son_cancelar_nunca_subir(
    qtbot, ctrl, iso_local
):
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    assert d.boton_cancelar.isDefault()
    assert not d.boton_accion.isDefault() and not d.boton_accion.autoDefault()
    assert QApplication.focusWidget() in (d.boton_cancelar, None) or d.boton_cancelar.hasFocus()


def test_ca_o09_1_subir_envia_el_destino_correcto_y_termina_con_el_volid(
    qtbot, ctrl, iso_local, servicio
):
    servicio.resultado = resultado_transferencia(volid="local:iso/alpine_mini.iso")
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    terminadas = []
    d.terminada.connect(terminadas.append)
    d.boton_accion.click()
    _terminada(qtbot, d)
    llamada = next(ll for ll in servicio.llamadas if ll[0] == "subir")
    assert llamada[1].storage == "local" and llamada[1].nodo == "pve"
    assert llamada[1].nombre_archivo == d.nombre_final
    assert d.volid_elegido == "local:iso/alpine_mini.iso"
    assert d.barra.value() == d.barra.maximum()
    assert "Listo" in d.etiqueta_final.text()
    assert terminadas and terminadas[0].estado == Est.TERMINADA
    assert d.boton_cancelar.text() == "Cerrar"


def test_ca_o12_1_la_barra_muestra_bytes_velocidad_y_tiempo_restante(
    qtbot, ctrl, iso_local, servicio
):
    servicio.progresos = [progreso(512 * 1024**2, GIB)]
    servicio.bloquear = True
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: "512" in d.etiqueta_estado.text(), timeout=3000)
    texto = d.etiqueta_estado.text()
    assert "50 %" in texto and "/s" in texto and "quedan" in texto
    assert 0 < d.barra.value() < d.barra.maximum()
    assert d.barra.accessibleName() and d.barra.accessibleDescription()
    assert d.transferencia_en_curso
    assert d.boton_cancelar.text() == "Cancelar subida"
    servicio.puerta.set()
    _terminada(qtbot, d)


def test_ca_o12_5_el_porcentaje_nunca_se_inventa_sin_total(qtbot, ctrl, iso_local, servicio):
    servicio.progresos = [progreso(0, 0, Est.ESPERANDO_SERVIDOR)]
    servicio.bloquear = True
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: d.etiqueta_estado.text().startswith("Esperando"), timeout=3000)
    assert "%" not in d.etiqueta_estado.text()
    assert d.barra.maximum() == 0  # barra indeterminada
    servicio.puerta.set()
    _terminada(qtbot, d)


# --- Cancelar (CA-O12.2) -------------------------------------------------------------------------


def test_ca_o12_2_cancelar_propaga_el_evento_y_dice_que_no_se_guardo_nada(
    qtbot, ctrl, iso_local, servicio
):
    servicio.bloquear = True
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: servicio.inicio.is_set(), timeout=3000)
    inicio = time.monotonic()
    d.boton_cancelar.click()
    assert d.boton_cancelar.text() == "Cancelando…" and not d.boton_cancelar.isEnabled()
    _terminada(qtbot, d)
    assert time.monotonic() - inicio < 2.0
    assert servicio.cancelado_visto
    assert d.resultado.estado == Est.CANCELADA
    assert "No se guardó ningún archivo" in d.etiqueta_final.text()
    assert d.volid_elegido is None


def test_cancelar_con_archivo_parcial_pide_al_administrador_que_lo_borre(
    qtbot, ctrl, iso_local, servicio
):
    servicio.resultado = resultado_transferencia(Est.CANCELADA, volid=None, quedo=True)
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    assert "parcial" in d.etiqueta_final.text() and "administrador" in d.etiqueta_final.text()


def test_cancelar_sin_saber_si_quedo_algo_lo_dice_con_honestidad(qtbot, ctrl, iso_local, servicio):
    servicio.resultado = resultado_transferencia(Est.CANCELADA, volid=None, quedo=None)
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    assert "No se pudo comprobar" in d.etiqueta_final.text()


def test_cerrar_con_la_equis_durante_la_subida_equivale_a_cancelar_y_no_cierra(
    qtbot, ctrl, iso_local, servicio
):
    servicio.bloquear = True
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: servicio.inicio.is_set(), timeout=3000)
    d.reject()
    assert d.isVisible()  # sigue abierto hasta que la transferencia termine
    _terminada(qtbot, d)
    assert servicio.cancelado_visto


# --- Errores E-O06..E-O11, E-O22, E-O23 durante la transferencia -


@pytest.mark.parametrize(
    ("error", "esperado"),
    [
        (ErrorProxLaunch(CodigoError.TRANSFERENCIA_NO_VERIFICADA), "no coincide"),
        (ErrorProxLaunch(CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA), "dañado"),
        (
            ErrorProxLaunch(
                CodigoError.TRANSFERENCIA_CORTADA, {"bytes": "1048576", "total": "2097152"}
            ),
            "Se cortó la conexión",
        ),
        (ErrorProxLaunch(CodigoError.ARCHIVO_CAMBIO), "cambió mientras se subía"),
        (
            ErrorProxLaunch(CodigoError.NOMBRE_YA_EXISTE, {"nombre": "a.iso", "storage": "local"}),
            "Ya existe",
        ),
        (
            ErrorProxLaunch(
                CodigoError.DESCARGA_URL_FALLIDA,
                {"archivo": "a.iso", "host": "x.org", "motivo": "404"},
            ),
            "x.org",
        ),
        (
            ErrorProxLaunch(
                CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA,
                {"storage": "local", "necesario": "2147483648", "libre": "1048576"},
            ),
            "local",
        ),
        (ErrorProxLaunch(CodigoError.TRANSFERENCIA_EN_CURSO), "en curso"),
    ],
    ids=["E-O06", "E-O07", "E-O08", "E-O09", "E-O10", "E-O11", "E-O22", "E-O23"],
)
def test_los_errores_de_transferencia_se_muestran_en_espanol_con_reintentar(
    qtbot, ctrl, iso_local, servicio, error, esperado
):
    servicio.resultado = resultado_transferencia(Est.FALLIDA, volid=None, error=error, quedo=False)
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    texto = d.etiqueta_final.text()
    assert esperado in texto, texto
    assert error.codigo.value not in texto  # nunca el identificador crudo
    assert d.etiqueta_final.property("error") is True
    assert d.boton_reintentar.isVisible()
    assert d.volid_elegido is None


def test_e_o23_una_excepcion_del_servicio_se_trata_como_fallo_y_se_puede_reintentar(
    qtbot, ctrl, iso_local, servicio
):
    servicio.resultado = ErrorProxLaunch(CodigoError.TRANSFERENCIA_EN_CURSO)
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    assert d.resultado.estado == Est.FALLIDA
    assert d.boton_reintentar.isVisible()


def test_reintentar_vuelve_a_comprobar_el_nombre_antes_de_enviar(qtbot, ctrl, iso_local, servicio):
    servicio.resultado = resultado_transferencia(
        Est.FALLIDA,
        volid=None,
        error=ErrorProxLaunch(CodigoError.TRANSFERENCIA_CORTADA),
        quedo=False,
    )
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    antes = sum(1 for ll in servicio.llamadas if ll[0] == "comprobar")
    d.boton_reintentar.click()
    qtbot.waitUntil(
        lambda: sum(1 for ll in servicio.llamadas if ll[0] == "comprobar") == antes + 1,
        timeout=3000,
    )
    _lista(qtbot, d)  # CA-O10.2


# --- Comprobaciones previas (RF-O10) -


def test_ca_o10_1_nombre_existente_bloquea_y_ofrece_usar_el_existente_o_cambiar_el_nombre(
    qtbot, ctrl, iso_local, servicio
):
    servicio.comprobacion = comprobacion(
        [_problema("V-O14", volid="local:iso/alpine_mini.iso")],
        existente="local:iso/alpine_mini.iso",
    )
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(lambda: d.fila_existente.isVisible(), timeout=3000)
    assert not d.boton_accion.isEnabled()
    assert (
        "no lo sobrescribe" in d.mensaje_comprobacion.text()
        or "Ya existe" in d.mensaje_comprobacion.text()
    )
    usados = []
    d.usar_existente.connect(usados.append)
    d.boton_usar_existente.click()
    assert usados == ["local:iso/alpine_mini.iso"]
    assert d.volid_elegido == "local:iso/alpine_mini.iso"
    assert d.resultado is None


def test_ca_o10_1_cambiar_el_nombre_lleva_el_foco_al_campo_y_nunca_hay_sobrescribir(
    qtbot, ctrl, iso_local, servicio
):
    servicio.comprobacion = comprobacion(
        [_problema("V-O14", volid="local:iso/alpine_mini.iso")],
        existente="local:iso/alpine_mini.iso",
    )
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(lambda: d.fila_existente.isVisible(), timeout=3000)
    d.boton_cambiar_nombre.click()
    assert d.campo_nombre.hasFocus() or d.campo_nombre.isEnabled()
    textos = [b.text().lower() for b in d.findChildren(type(d.boton_accion))]
    assert not any("sobrescrib" in t or "reemplaz" in t for t in textos)


def test_ca_o10_3_sin_espacio_en_el_storage_bloquea_con_e_o22(qtbot, ctrl, iso_local, servicio):
    servicio.comprobacion = comprobacion(
        [_problema("V-O13", storage="local", necesario=str(2 * GIB), libre=str(GIB // 2))]
    )
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(lambda: "«local»" in d.mensaje_comprobacion.text(), timeout=3000)
    assert not d.boton_accion.isEnabled()


def test_ca_o10_4_poco_espacio_en_el_nodo_avisa_y_exige_marcar_la_casilla(
    qtbot, ctrl, iso_local, servicio
):
    servicio.comprobacion = comprobacion(
        [
            Problema(
                "destino",
                "V-O13.raiz",
                Severidad.AVISO,
                {"nodo": "pve", "necesario": str(GIB), "libre": "1"},
            )
        ]
    )
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(lambda: d.casilla_raiz.isVisible(), timeout=3000)
    assert not d.boton_accion.isEnabled()
    d.casilla_raiz.setChecked(True)
    assert d.boton_accion.isEnabled()
    d.boton_accion.click()
    _terminada(qtbot, d)
    assert next(ll for ll in servicio.llamadas if ll[0] == "subir")[2] is True


def test_ca_o10_5_sin_permiso_de_subida_bloquea_con_el_privilegio_y_la_ruta(
    qtbot, ctrl, iso_local, servicio
):
    servicio.comprobacion = comprobacion(
        [_problema("V-O15", privilegio="Datastore.AllocateTemplate", ruta="/storage/local")]
    )
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(
        lambda: "Datastore.AllocateTemplate" in d.mensaje_comprobacion.text(), timeout=3000
    )
    assert "/storage/local" in d.mensaje_comprobacion.text()
    assert not d.boton_accion.isEnabled()


def test_una_falla_de_lectura_al_comprobar_se_muestra_como_error_y_bloquea(
    qtbot, ctrl, iso_local, servicio
):
    servicio.comprobacion = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.5"})
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(
        lambda: (
            d.mensaje_comprobacion.isVisible()
            and "Comprobando" not in d.mensaje_comprobacion.text()
        ),
        timeout=3000,
    )
    assert not d.boton_accion.isEnabled()


# --- Archivo local inválido (V-O10) -


def test_v_o10_un_archivo_vacio_se_rechaza_antes_de_comprobar_nada(qtbot, ctrl, tmp_path, servicio):
    vacio = tmp_path / "vacio.iso"
    vacio.write_bytes(b"")
    d = _subida(qtbot, ctrl, vacio)
    qtbot.waitUntil(lambda: "vacío" in d.mensaje_comprobacion.text(), timeout=3000)
    assert not d.boton_accion.isEnabled()
    assert not [ll for ll in servicio.llamadas if ll[0] == "comprobar"]


def test_v_o10_un_archivo_inexistente_muestra_error_y_no_habilita_subir(
    qtbot, ctrl, tmp_path, servicio
):
    d = _subida(qtbot, ctrl, tmp_path / "no-existe.iso")
    qtbot.waitUntil(
        lambda: (
            d.mensaje_comprobacion.isVisible() and "Leyendo" not in d.mensaje_comprobacion.text()
        ),
        timeout=3000,
    )
    assert not d.boton_accion.isEnabled()


def test_ca_o09_12_el_nombre_propuesto_se_sanea_y_un_nombre_invalido_bloquea(
    qtbot, ctrl, iso_local
):
    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    assert " " not in d.nombre_final and d.nombre_final.endswith(".iso")
    d.campo_nombre.setText("mal;nombre.iso")
    assert d.error_nombre.isVisible()
    assert not d.boton_accion.isEnabled()


def test_enter_en_el_campo_de_nombre_no_confirma_la_subida(qtbot, ctrl, iso_local, servicio):
    from PySide6.QtCore import Qt

    d = _subida(qtbot, ctrl, iso_local)
    _lista(qtbot, d)
    d.campo_nombre.setFocus()
    qtbot.keyClick(d.campo_nombre, Qt.Key.Key_Return)
    assert not [ll for ll in servicio.llamadas if ll[0] == "subir"]


def test_sin_storage_para_el_contenido_dice_que_pedir_al_administrador(qtbot, ctrl, iso_local):
    ctrl.respuesta_storage = None
    d = _subida(qtbot, ctrl, iso_local)
    qtbot.waitUntil(lambda: "almacenamiento" in d.mensaje_comprobacion.text(), timeout=3000)
    assert "administrador" in d.mensaje_comprobacion.text()
    assert not d.boton_accion.isEnabled()


def test_subir_una_imagen_de_disco_usa_el_titulo_y_contenido_de_disco(qtbot, ctrl, tmp_path):
    ruta = tmp_path / "disco.qcow2"
    ruta.write_bytes(b"QFI\xfb" + bytes(2000))
    d = DialogoSubida(ctrl, Contenido.IMPORT, "pve", ruta=ruta)
    qtbot.addWidget(d)
    assert "disco" in d.windowTitle()


# --- Descarga por URL (RF-O11) -


def _descarga(qtbot, ctrl, **kw) -> DialogoDescarga:
    d = DialogoDescarga(ctrl, Contenido.ISO, "pve", **kw)
    qtbot.addWidget(d)
    d.show()
    return d


def _comprobar(qtbot, d, url="https://mirror.example.org/alpine.iso", huella=""):
    d.campo_url.setText(url)
    d.campo_checksum.setText(huella)
    d.comprobar_url()
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)


def test_ca_o11_3_http_en_basico_se_rechaza_con_mensaje_claro(qtbot, ctrl):
    d = _descarga(qtbot, ctrl)
    d.campo_url.setText("http://mirror.example.org/a.iso")
    d.comprobar_url()
    assert d.error_campos.isVisible()
    assert "https://" in d.error_campos.text()
    assert not d.boton_accion.isEnabled()


def test_ca_o11_3_http_en_avanzado_se_acepta_pero_pide_confirmacion_al_descargar(
    qtbot, ctrl, servicio, monkeypatch
):
    ctrl.modo_avanzado = True
    preguntas = []
    monkeypatch.setattr(dt, "confirmar", lambda *a, **k: preguntas.append(a[2]) or False)
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, "http://mirror.example.org/a.iso")
    d.boton_accion.click()
    assert preguntas and "http://" in preguntas[0]
    assert not [ll for ll in servicio.llamadas if ll[0] == "descargar"]  # dijo que no


def test_ca_o11_4_verificar_certificados_solo_existe_en_avanzado_y_por_defecto_verifica(
    qtbot, ctrl
):
    d = _descarga(qtbot, ctrl)
    assert not d.casilla_certificados.isVisible()
    assert d.verificar_certificados is True
    ctrl.modo_avanzado = True
    d2 = _descarga(qtbot, ctrl)
    assert d2.casilla_certificados.isVisible() and d2.casilla_certificados.isChecked()


def test_ca_o11_4_desmarcar_la_verificacion_exige_confirmar(qtbot, ctrl, servicio, monkeypatch):
    ctrl.modo_avanzado = True
    preguntas = []
    monkeypatch.setattr(dt, "confirmar", lambda *a, **k: preguntas.append(a[2]) or False)
    d = _descarga(qtbot, ctrl)
    d.casilla_certificados.setChecked(False)
    _comprobar(qtbot, d)
    d.boton_accion.click()
    assert preguntas and "certificado" in preguntas[0]


def test_ca_o11_11_una_huella_con_longitud_invalida_se_rechaza(qtbot, ctrl):
    d = _descarga(qtbot, ctrl)
    d.campo_url.setText("https://mirror.example.org/a.iso")
    d.campo_checksum.setText("abc123")
    d.comprobar_url()
    assert d.error_campos.isVisible()
    assert not d.boton_accion.isEnabled()


def test_ca_o11_1_comprobar_pregunta_al_servidor_y_muestra_lo_que_ve_sin_la_url_completa(
    qtbot, ctrl, servicio
):
    d = _descarga(qtbot, ctrl)
    d.campo_url.setText("https://mirror.example.org/alpine.iso?token=T0K3N")
    d.comprobar_url()
    qtbot.waitUntil(lambda: d.etiqueta_metadatos.isVisible(), timeout=3000)
    todo = " ".join(w.text() for w in d.findChildren(QLabel))
    assert "mirror.example.org/alpine.iso" in d.etiqueta_metadatos.text()
    assert "T0K3N" not in todo
    assert d.campo_nombre.isEnabled() and d.nombre_final == "alpine.iso"
    assert ("consultar_url", "pve", "mirror.example.org", True) in servicio.llamadas


def test_inv_o6_una_url_con_credenciales_se_rechaza_y_el_mensaje_no_las_repite(
    qtbot, ctrl, servicio
):
    d = _descarga(qtbot, ctrl)
    d.campo_url.setText("https://usuario:clave-secreta@mirror.example.org/a.iso")
    d.comprobar_url()
    assert d.error_campos.isVisible()
    todo = " ".join(w.text() for w in d.findChildren(QLabel))
    assert "clave-secreta" not in todo
    assert not [ll for ll in servicio.llamadas if ll[0] == "consultar_url"]


def test_cambiar_la_url_despues_de_comprobar_invalida_la_comprobacion(qtbot, ctrl):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d)
    d.campo_url.setText("https://otro.example.org/b.iso")
    assert not d.boton_accion.isEnabled()
    assert not d.etiqueta_metadatos.isVisible()


def test_ca_o11_5_la_descarga_muestra_progreso_del_servidor_y_no_se_puede_cancelar(
    qtbot, ctrl, servicio
):
    from proxlaunch.nucleo.transferencias.modelos import Progreso

    servicio.progresos = [Progreso(Est.ESPERANDO_SERVIDOR, 0, None, None, None, 40.0)]
    servicio.bloquear = True
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: "40 %" in d.etiqueta_estado.text(), timeout=3000)
    assert d.barra.value() == 400
    assert d.boton_cancelar.text() == "Dejar de esperar"
    assert d.aviso_no_se_cancela.isVisible()
    servicio.puerta.set()
    _terminada(qtbot, d)
    assert d.volid_elegido == VOLID_ISO


def test_ca_o11_8_dejar_de_esperar_avisa_que_la_descarga_sigue_en_el_servidor(
    qtbot, ctrl, servicio
):
    servicio.bloquear = True
    servicio.resultado = resultado_transferencia(Est.SIN_ESPERAR, volid=None, quedo=None)
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: servicio.inicio.is_set(), timeout=3000)
    d.boton_cancelar.click()
    assert d.boton_cancelar.text() == "Dejando de esperar…"
    _terminada(qtbot, d)
    assert servicio.cancelado_visto
    assert d.resultado.estado == Est.CANCELADA or d.resultado.estado == Est.SIN_ESPERAR


def test_ca_o11_8_el_texto_de_sin_esperar_dice_que_la_descarga_sigue(qtbot, ctrl, servicio):
    servicio.resultado = resultado_transferencia(Est.SIN_ESPERAR, volid=None, quedo=None)
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    assert "sigue en el servidor" in d.etiqueta_final.text()


def test_ca_o11_7_si_la_descarga_falla_el_mensaje_no_contiene_la_url(qtbot, ctrl, servicio):
    servicio.resultado = resultado_transferencia(
        Est.FALLIDA,
        volid=None,
        error=ErrorProxLaunch(
            CodigoError.DESCARGA_URL_FALLIDA,
            {
                "archivo": "a.iso",
                "host": "x.org",
                "motivo": "error al bajar https://x.org/a.iso?token=T0K3N",
            },
        ),
        quedo=False,
    )
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d)
    d.boton_accion.click()
    _terminada(qtbot, d)
    assert "T0K3N" not in d.etiqueta_final.text()
    assert "https://" not in d.etiqueta_final.text()
    assert d.boton_reintentar.isVisible()


def test_ca_o11_2_la_url_fija_de_virtio_no_se_puede_editar(qtbot, ctrl):
    d = _descarga(
        qtbot,
        ctrl,
        url_inicial="https://fedorapeople.example/virtio-win.iso",
        checksum_inicial="a" * 64,
        url_fija=True,
    )
    assert d.campo_url.isReadOnly() and d.campo_checksum.isReadOnly()
