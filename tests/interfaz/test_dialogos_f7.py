"""Diálogos y vistas (ronda F7): huella, 2FA, «Recordar credenciales», «Ignorar SSL» con
contraseña, barra superior en texto plano y textos de las reglas nuevas."""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.dialogos.huella import DialogoHuella
from proxlaunch.interfaz.vistas.barra_superior import BarraSuperior
from proxlaunch.nucleo.modelos.conexion import MetodoAuth
from proxlaunch.nucleo.modelos.inventario import Nodo, Topologia
from proxlaunch.nucleo.servicios.conexion import EstadoHuella
from proxlaunch.nucleo.validacion import Problema, Severidad

from . import test_dialogo_conexion as _base
from .apoyo import info_huella, perfil, sesion_falsa
from .test_dialogo_conexion import TOKEN, _llegar_a_tfa, _llenar_token

# Fixtures del diálogo de conexión (con sus dobles) reutilizados sin copiarlos.
crear = _base.crear
lanzador = _base.lanzador


def _textos(dialogo):
    return " ".join(lbl.text() for lbl in dialogo.findChildren(QLabel))


def _por_defecto(dialogo):
    return [b.text() for b in dialogo.findChildren(QPushButton) if b.isDefault()]


# --- 13. Diálogo de huella ---------------------------------------------------------------------


def test_huella_nueva_tiene_cancelar_como_boton_por_defecto(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False)
    qtbot.addWidget(d)
    assert _por_defecto(d) == ["Cancelar"]


@pytest.mark.parametrize("avanzado", [False, True])
def test_huella_cambiada_tiene_cerrar_como_boton_por_defecto(qtbot, avanzado):
    d = DialogoHuella(info_huella(EstadoHuella.CAMBIADA), avanzado=avanzado)
    qtbot.addWidget(d)
    assert _por_defecto(d) == ["Cerrar"]


def test_huella_nueva_con_archivo_danado_no_dice_primera_vez(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False, archivo_danado=True)
    qtbot.addWidget(d)
    texto = _textos(d)
    assert "archivo de huellas se dañó" in texto
    assert "primera vez" not in texto
    assert _por_defecto(d) == ["Cancelar"]


def test_huella_nueva_sin_dano_dice_primera_vez(qtbot):
    d = DialogoHuella(info_huella(EstadoHuella.NUEVA), avanzado=False, archivo_danado=False)
    qtbot.addWidget(d)
    assert "primera vez" in _textos(d)


def test_el_dialogo_de_conexion_avisa_del_archivo_danado_al_pedir_la_huella(
    qtbot, crear, deps, servicio_falso, monkeypatch
):
    vistos = []

    def exec_(self):
        vistos.append(_textos(self))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(DialogoHuella, "exec", exec_)
    deps.huellas.hubo_corrupcion = True
    servicio_falso.infos = [info_huella(EstadoHuella.NUEVA)]
    d = crear()
    _llenar_token(d)
    d.btn_conectar.click()
    qtbot.waitUntil(lambda: bool(vistos), timeout=4000)
    assert "archivo de huellas se dañó" in vistos[0]


# --- 14. Cancelar el segundo factor ------------------------------------------------------------


def test_cancelar_el_2fa_llama_a_cancelar_tfa_con_el_desafio(
    qtbot, crear, servicio_falso, lanzador
):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    desafio = d._desafio_tfa
    tfa.reject()
    assert ("cancelar_tfa", desafio) in servicio_falso.llamadas
    assert d.btn_conectar.isEnabled()
    assert d._dialogo_tfa is None


def test_cerrar_el_dialogo_de_conexion_con_2fa_pendiente_cancela_el_tfa(
    qtbot, crear, servicio_falso, lanzador
):
    d = crear()
    _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    desafio = d._desafio_tfa
    d.reject()
    assert [ll for ll in servicio_falso.llamadas if ll[0] == "cancelar_tfa"] == [
        ("cancelar_tfa", desafio)
    ]


def test_completar_el_2fa_no_llama_a_cancelar_tfa(qtbot, crear, servicio_falso, lanzador):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    servicio_falso.resultado_tfa = sesion_falsa()
    tfa._campo.setText("123456")
    with qtbot.waitSignal(d.accepted, timeout=4000):
        tfa._boton_ok.click()
    assert not any(ll[0] == "cancelar_tfa" for ll in servicio_falso.llamadas)


# --- 15. Desmarcar «Recordar credenciales» -----------------------------------------------------


def _con_secreto_guardado(deps, llavero, metodo_clave=False):
    extra = {}
    if metodo_clave:
        extra = {"metodo": MetodoAuth.CONTRASENA, "usuario": "ana", "realm": "pve"}
    deps.perfiles.guardar(perfil("a", "Alfa", recordar_credenciales=True, **extra))
    llavero.set_password("ProxLaunch", "perfil:a", "secreto-guardado")


def test_desmarcar_recordar_con_secreto_guardado_muestra_nota_no_modal(
    crear, deps, llavero, monkeypatch
):
    for nombre in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, nombre, lambda *a, **k: pytest.fail("no debe ser modal"))
    _con_secreto_guardado(deps, llavero)
    d = crear()
    assert d._nota_recordar.isHidden()
    d.chk_recordar.setChecked(False)
    assert not d._nota_recordar.isHidden()
    assert "se borrarán del llavero" in d._nota_recordar.text()
    assert d.token.placeholderText() != "(guardado en el llavero)"
    assert llavero.datos  # todavía no se borra: será al guardar o conectar


def test_desmarcar_recordar_deja_de_usar_el_secreto_guardado(
    qtbot, crear, deps, llavero, servicio_falso
):
    _con_secreto_guardado(deps, llavero, metodo_clave=True)
    d = crear()
    d.chk_recordar.setChecked(False)
    d.btn_conectar.click()
    # Sin contraseña escrita y sin secreto en uso: pide la contraseña y no llega a conectar.
    assert "Escribe tu contraseña" in d.fila_contrasena._error.text()
    assert not any(ll[0] in ("consultar_huellas", "conectar") for ll in servicio_falso.llamadas)


def test_desmarcar_recordar_y_conectar_borra_el_secreto_del_llavero(
    qtbot, crear, deps, llavero, servicio_falso
):
    _con_secreto_guardado(deps, llavero)
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear()
    d.chk_recordar.setChecked(False)
    d.token.setText(TOKEN)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert llavero.datos == {}
    assert deps.perfiles.obtener("a").recordar_credenciales is False


def test_desmarcar_recordar_y_guardar_borra_el_secreto_y_quita_el_marcador(crear, deps, llavero):
    _con_secreto_guardado(deps, llavero)
    d = crear()
    d.chk_recordar.setChecked(False)
    d.btn_guardar.click()
    assert llavero.datos == {}


def test_volver_a_marcar_recordar_quita_la_nota(crear, deps, llavero):
    _con_secreto_guardado(deps, llavero)
    d = crear()
    d.chk_recordar.setChecked(False)
    d.chk_recordar.setChecked(True)
    assert d._nota_recordar.isHidden()


def test_desmarcar_recordar_sin_secreto_guardado_no_muestra_nota(crear, deps):
    deps.perfiles.guardar(perfil("a", "Alfa", recordar_credenciales=True))  # llavero vacío
    d = crear()
    d.chk_recordar.setChecked(False)
    assert d._nota_recordar.isHidden()


def test_cambiar_de_perfil_limpia_la_nota_de_recordar(crear, deps, llavero):
    _con_secreto_guardado(deps, llavero)
    deps.perfiles.guardar(perfil("b", "Beta"))
    d = crear(perfil_id="a")
    d.chk_recordar.setChecked(False)
    d.combo_perfiles.setCurrentIndex(d.combo_perfiles.findData("b"))
    assert d._nota_recordar.isHidden()


# --- 16. «Ignorar SSL» con contraseña -----------------------------------------------------------


def _preparar_ignorar_con_contrasena(d):
    d.nombre.setText("Lab")
    d.hosts.setPlainText("10.0.0.5")
    d.radio_clave.setChecked(True)
    d.usuario.setText("ana")
    d.contrasena.setText("clave-secreta")
    d.chk_ignorar.setChecked(True)


def _capturar_advertencia(monkeypatch, respuestas):
    llamadas = []

    def advertencia(padre, titulo, texto, botones=None, por_defecto=None):
        llamadas.append(por_defecto)
        return respuestas.pop(0)

    monkeypatch.setattr(QMessageBox, "warning", advertencia)
    return llamadas


def test_ignorar_ssl_con_contrasena_pide_confirmacion_con_no_por_defecto(
    qtbot, crear, servicio_falso, monkeypatch
):
    llamadas = _capturar_advertencia(monkeypatch, [QMessageBox.StandardButton.No])
    d = crear(avanzado=True)
    _preparar_ignorar_con_contrasena(d)
    d.btn_conectar.click()
    assert llamadas == [QMessageBox.StandardButton.No]
    assert servicio_falso.llamadas == []  # No conecta ni consulta nada
    assert d.btn_conectar.isEnabled()


def test_ignorar_ssl_con_contrasena_conecta_si_se_confirma_y_vuelve_a_preguntar_cada_vez(
    qtbot, crear, servicio_falso, monkeypatch
):
    llamadas = _capturar_advertencia(
        monkeypatch, [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes]
    )
    servicio_falso.infos = [info_huella(EstadoHuella.IGNORADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    for _ in range(2):  # dos diálogos distintos = dos conexiones: se pregunta en cada una
        d = crear(avanzado=True)
        _preparar_ignorar_con_contrasena(d)
        with qtbot.waitSignal(d.accepted, timeout=4000):
            d.btn_conectar.click()
    assert len(llamadas) == 2
    assert [ll[0] for ll in servicio_falso.llamadas].count("conectar") == 2


def test_ignorar_ssl_con_token_no_pide_confirmacion(qtbot, crear, servicio_falso, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("no debe preguntar"))
    servicio_falso.infos = [info_huella(EstadoHuella.IGNORADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear(avanzado=True)
    _llenar_token(d)
    d.chk_ignorar.setChecked(True)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()


def test_contrasena_sin_ignorar_ssl_no_pide_confirmacion(qtbot, crear, servicio_falso, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("no debe preguntar"))
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear(avanzado=True)
    _preparar_ignorar_con_contrasena(d)
    d.chk_ignorar.setChecked(False)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()


# --- 17. Barra superior en texto plano ---------------------------------------------------------


def test_las_etiquetas_con_datos_del_servidor_de_la_barra_son_texto_plano(qtbot):
    b = BarraSuperior()
    qtbot.addWidget(b)
    for etiqueta in (b._perfil, b._version, b._topologia, b._ssl):
        assert etiqueta.textFormat() == Qt.TextFormat.PlainText


def test_la_barra_no_interpreta_html_de_los_nombres(qtbot):
    b = BarraSuperior()
    qtbot.addWidget(b)
    b.establecer_conexion("<b>lab</b>", "9.2", False, False, "<i>ana</i>")
    b.establecer_topologia(
        Topologia(True, "<u>c</u>", (Nodo("pve1", True, 1, 1),)),
        degradada=False,
    )
    assert b._perfil.text() == "<b>lab</b> · <i>ana</i>"
    assert "<u>c</u>" in b.texto_topologia
    assert b._perfil.textFormat() == Qt.TextFormat.PlainText


# --- 18. Textos de las reglas nuevas ------------------------------------------------------------

MARCADOR = re.compile(r"\{[a-z_]+\}")


@pytest.mark.parametrize("codigo", ["V-22", "V-23", "V-07.sindisco", "V-16.sinredes"])
def test_textos_de_las_reglas_nuevas_no_estan_vacios_ni_tienen_marcadores(codigo):
    texto = textos.texto_problema(Problema("campo", codigo, Severidad.ERROR, {}))
    assert texto.strip()
    assert not MARCADOR.search(texto)
    assert "{" not in texto


def test_los_textos_de_v22_v23_y_sindisco_son_distintos_entre_si():
    t = {
        c: textos.texto_problema(Problema("c", c, Severidad.ERROR, {}))
        for c in ("V-22", "V-23", "V-07.sindisco")
    }
    assert len(set(t.values())) == 3


def test_el_texto_de_v23_menciona_el_maximo():
    texto = textos.texto_problema(Problema("redes", "V-23", Severidad.ERROR, {"maximo": "32"}))
    assert "32" in texto
