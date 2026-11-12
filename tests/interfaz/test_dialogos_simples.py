"""Diálogos de huella (TOFU), segundo factor, guía de token y Acerca de (RF-04, RF-05, RF-25)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPlainTextEdit

from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe, leer_licencia
from proxlaunch.interfaz.dialogos.dos_factores import DialogoDosFactores
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.huella import DialogoHuella
from proxlaunch.nucleo.api.autenticacion import DesafioTFA, TipoTFA
from proxlaunch.nucleo.servicios.conexion import EstadoHuella

from .apoyo import HUELLA_A, HUELLA_B, info_huella

# --- Huella: servidor nuevo (CA-05.1 a CA-05.3) -----------------------------------------------


def _cajas(dialogo):
    return [c.toPlainText() for c in dialogo.findChildren(QPlainTextEdit)]


def _boton(dialogo, texto):
    from PySide6.QtWidgets import QPushButton

    return next(b for b in dialogo.findChildren(QPushButton) if b.text() == texto)


def test_huella_nueva_muestra_servidor_puerto_y_huella(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False)
    qtbot.addWidget(d)
    assert _cajas(d) == [HUELLA_A]
    textos = " ".join(lbl.text() for lbl in d.findChildren(QLabel))
    assert "10.0.0.5" in textos and "8006" in textos
    assert "ninguna credencial" in textos


def test_huella_nueva_confiar_acepta(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False)
    qtbot.addWidget(d)
    _boton(d, "Confiar y continuar").click()
    assert d.result() == QDialog.DialogCode.Accepted
    assert d.reemplazar is False


def test_huella_nueva_cancelar_rechaza(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False)
    qtbot.addWidget(d)
    _boton(d, "Cancelar").click()
    assert d.result() == QDialog.DialogCode.Rejected


def test_huella_nueva_es_modal(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False)
    qtbot.addWidget(d)
    assert d.isModal()


def test_huella_cambiada_muestra_ambas_huellas_y_solo_ofrece_cerrar_en_basico(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.CAMBIADA), avanzado=False)
    qtbot.addWidget(d)
    assert _cajas(d) == [HUELLA_A, HUELLA_B]  # guardada, nueva
    with pytest.raises(StopIteration):
        _boton(d, "Reemplazar la huella guardada")
    _boton(d, "Cerrar").click()
    assert d.result() == QDialog.DialogCode.Rejected
    assert d.reemplazar is False


def test_huella_cambiada_no_ofrece_confiar_sin_mas(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.CAMBIADA), avanzado=True)
    qtbot.addWidget(d)
    with pytest.raises(StopIteration):
        _boton(d, "Confiar y continuar")


def test_huella_cambiada_avanzado_reemplazo_pide_confirmacion_y_la_respeta(qtbot, monkeypatch):
    d = DialogoHuella(info_huella(EstadoHuella.CAMBIADA), avanzado=True)
    qtbot.addWidget(d)
    # Responde «No»: no reemplaza ni cierra.
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.No)
    _boton(d, "Reemplazar la huella guardada").click()
    assert d.reemplazar is False and d.result() != QDialog.DialogCode.Accepted


def test_huella_cambiada_avanzado_confirmar_reemplazo(qtbot, monkeypatch):
    d = DialogoHuella(info_huella(EstadoHuella.CAMBIADA), avanzado=True)
    qtbot.addWidget(d)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
    _boton(d, "Reemplazar la huella guardada").click()
    assert d.reemplazar is True
    assert d.result() == QDialog.DialogCode.Accepted


def test_el_aviso_de_reemplazo_nombra_el_servidor(qtbot, monkeypatch):
    visto = {}

    def falso(padre, titulo, texto, *a, **k):
        visto["texto"] = texto
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "warning", falso)
    d = DialogoHuella(info_huella(EstadoHuella.CAMBIADA), avanzado=True)
    qtbot.addWidget(d)
    _boton(d, "Reemplazar la huella guardada").click()
    assert "10.0.0.5:8006" in visto["texto"]


# --- Segundo factor (CA-04.x, V-21) -----------------------------------------------------------


def _desafio(totp=True, recuperacion=True):
    return DesafioTFA("ana@pve", "ticket-parcial", totp, recuperacion)


@pytest.fixture
def dialogo_tfa(qtbot):
    d = DialogoDosFactores(_desafio())
    qtbot.addWidget(d)
    d.show()
    return d


def _enviar(qtbot, d, texto):
    d._campo.setText(texto)
    recibidos = []
    d.enviado.connect(lambda c, t: recibidos.append((c, t)))
    d._boton_ok.click()
    return recibidos


@pytest.mark.parametrize("codigo", ["123456", "000000", "654321"])
def test_totp_valido_emite_codigo_y_tipo(qtbot, dialogo_tfa, codigo):
    recibidos = _enviar(qtbot, dialogo_tfa, codigo)
    assert recibidos == [(codigo.strip(), TipoTFA.TOTP)]
    assert not dialogo_tfa._campo.isEnabled()  # ocupado hasta la respuesta


@pytest.mark.parametrize("codigo", ["", "12345", "abcdef", "12 456"])
def test_totp_invalido_muestra_error_y_no_emite(qtbot, dialogo_tfa, codigo):
    recibidos = _enviar(qtbot, dialogo_tfa, codigo)
    assert recibidos == []
    assert dialogo_tfa._error.isVisible()
    assert dialogo_tfa._campo.isEnabled()


def test_campo_totp_limita_a_seis_caracteres(dialogo_tfa):
    assert dialogo_tfa._campo.maxLength() == 6
    dialogo_tfa._campo.setText("1234567")
    assert dialogo_tfa._campo.text() == "123456"
    assert not dialogo_tfa.uso_recuperacion


def test_alternar_a_recuperacion_cambia_modo_y_limpia(qtbot, dialogo_tfa):
    dialogo_tfa._campo.setText("123")
    dialogo_tfa._alternar.clicked.emit()
    assert dialogo_tfa.uso_recuperacion
    assert dialogo_tfa._campo.text() == ""
    assert dialogo_tfa._campo.maxLength() > 6


def test_clave_de_recuperacion_emite_tipo_recuperacion(qtbot, dialogo_tfa):
    dialogo_tfa._alternar.clicked.emit()
    recibidos = _enviar(qtbot, dialogo_tfa, "abcd-1234-ef56-7890")
    assert recibidos == [("abcd-1234-ef56-7890", TipoTFA.RECUPERACION)]


def test_clave_de_recuperacion_vacia_muestra_error(qtbot, dialogo_tfa):
    dialogo_tfa._alternar.clicked.emit()
    assert _enviar(qtbot, dialogo_tfa, "  ") == []
    assert dialogo_tfa._error.isVisible()


def test_solo_recuperacion_arranca_en_ese_modo_sin_alternar(qtbot):
    d = DialogoDosFactores(_desafio(totp=False, recuperacion=True))
    qtbot.addWidget(d)
    d.show()
    assert d.uso_recuperacion and not d._alternar.isVisible()


def test_solo_totp_no_ofrece_recuperacion(qtbot):
    d = DialogoDosFactores(_desafio(totp=True, recuperacion=False))
    qtbot.addWidget(d)
    d.show()
    assert not d.uso_recuperacion and not d._alternar.isVisible()


def test_mostrar_error_permite_reintentar(qtbot, dialogo_tfa):
    _enviar(qtbot, dialogo_tfa, "123456")
    dialogo_tfa.mostrar_error("código incorrecto")
    assert dialogo_tfa._error.text() == "código incorrecto"
    assert dialogo_tfa._campo.isEnabled() and dialogo_tfa._boton_ok.isEnabled()


def test_enter_en_el_campo_envia(qtbot, dialogo_tfa):
    dialogo_tfa._campo.setText("123456")
    with qtbot.waitSignal(dialogo_tfa.enviado, timeout=500):
        dialogo_tfa._campo.returnPressed.emit()


def test_cancelar_rechaza_el_dialogo(qtbot, dialogo_tfa):
    dialogo_tfa._boton_cancelar.click()
    assert dialogo_tfa.result() == QDialog.DialogCode.Rejected


# --- Guía del token y Acerca de ---------------------------------------------------------------


def test_guia_de_token_lista_pasos_y_privilegios(qtbot):
    d = DialogoGuiaToken()
    qtbot.addWidget(d)
    privilegios = d.findChildren(QPlainTextEdit)[0].toPlainText()
    for p in ("VM.Allocate", "Datastore.AllocateSpace", "SDN.Use", "Sys.Audit"):
        assert p in privilegios
    from PySide6.QtWidgets import QLabel

    pasos = [lbl.text() for lbl in d.findChildren(QLabel) if lbl.text()[:2] == "1."]
    assert pasos


def test_guia_de_token_cerrar_acepta(qtbot):
    from PySide6.QtWidgets import QPushButton

    d = DialogoGuiaToken()
    qtbot.addWidget(d)
    d.findChildren(QPushButton)[0].click()
    assert d.result() == QDialog.DialogCode.Accepted


def test_acerca_de_muestra_version_y_licencias(qtbot):
    from proxlaunch import __version__

    d = DialogoAcercaDe("claro")
    qtbot.addWidget(d)
    from PySide6.QtWidgets import QLabel

    textos = " ".join(lbl.text() for lbl in d.findChildren(QLabel))
    assert __version__ in textos and "Compatible con Proxmox VE" in textos
    assert d._selector.count() == 2
    assert "SIL OPEN FONT LICENSE" in d._licencia.toPlainText().upper()
    d._selector.setCurrentIndex(1)
    assert d._licencia.toPlainText() != ""


def test_licencia_inexistente_devuelve_vacio():
    assert leer_licencia("no-existe.txt") == ""
