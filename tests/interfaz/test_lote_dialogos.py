"""Diálogos del lote: confirmación, pausa, deshacer e informe (RF-L14, RF-L18, RF-L19)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from proxlaunch.interfaz.dialogos.confirmar import confirmar
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.dialogos.pausa_lote import AccionPausa, DialogoPausaLote
from proxlaunch.interfaz.informe_lote import texto_informe
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import CandidatoRollback, EstadoMV, MotivoPausa

from .apoyo_lote import entrada, informe_de

EM = EstadoMV


# --- confirmar(): foco inicial en Cancelar (RNF-L04, CA-L10.4) ---------------------------------


class _Cajas:
    """Sustituye ``QMessageBox.exec``: registra el estado de la caja y «pulsa» un botón."""

    def __init__(self):
        self.cajas = []

    def instalar(self, monkeypatch, pulsar: str | None):
        def exec_(caja):
            botones = {b.text(): b for b in caja.buttons()}
            self.cajas.append(
                {
                    "titulo": caja.windowTitle(),
                    "texto": caja.text(),
                    "predeterminado": caja.defaultButton().text() if caja.defaultButton() else None,
                    "escape": caja.escapeButton().text() if caja.escapeButton() else None,
                    "botones": list(botones),
                    "formato": caja.textFormat(),
                }
            )
            if pulsar is not None:
                botones[pulsar].click()
            return 0

        monkeypatch.setattr(QMessageBox, "exec", exec_)


def test_ca_l10_4_confirmar_deja_el_foco_y_la_tecla_intro_en_cancelar(qtbot, monkeypatch):
    cajas = _Cajas()
    cajas.instalar(monkeypatch, pulsar=None)
    assert (
        confirmar(
            None,
            "Confirmar el envío",
            "Se enviarán 11 máquinas a Proxmox. ¿Continuar?",
            "Crear las máquinas",
            "Cancelar",
        )
        is False
    )
    caja = cajas.cajas[0]
    assert caja["predeterminado"] == "Cancelar" and caja["escape"] == "Cancelar"
    assert caja["botones"] == ["Crear las máquinas", "Cancelar"]
    assert caja["formato"] == Qt.TextFormat.PlainText  # el texto puede traer nombres del servidor


def test_confirmar_devuelve_true_solo_si_se_pulsa_aceptar(qtbot, monkeypatch):
    _Cajas().instalar(monkeypatch, pulsar="Sí, crear")
    assert confirmar(None, "t", "x", "Sí, crear", "No") is True


def test_confirmar_cerrar_la_caja_o_pulsar_cancelar_no_confirma(qtbot, monkeypatch):
    _Cajas().instalar(monkeypatch, pulsar="No")
    assert confirmar(None, "t", "x", "Sí, crear", "No") is False


# --- Pausa (RF-L14) -------------------------------------------------------------------------


def dialogo_pausa(qtbot, motivo, error=None, **kw):
    d = DialogoPausaLote(motivo, error, **kw)
    qtbot.addWidget(d)
    return d


def textos_botones(d):
    return {a: b.text() for a, b in d.botones.items()}


def test_ca_l14_2_error_global_de_sesion_ofrece_reconectar_reintentar_y_cancelar(qtbot):
    d = dialogo_pausa(qtbot, MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(CodigoError.SESION_EXPIRADA))
    assert set(d.botones) == {AccionPausa.RECONECTAR, AccionPausa.REINTENTAR, AccionPausa.DETENER}
    assert textos_botones(d)[AccionPausa.RECONECTAR] == "Reconectar…"
    assert textos_botones(d)[AccionPausa.DETENER] == "Cancelar lote"
    assert "No se enviará ninguna máquina más hasta que decidas" in _cuerpo(d)


@pytest.mark.parametrize(
    "codigo",
    [CodigoError.SESION_EXPIRADA, CodigoError.CREDENCIALES_INVALIDAS, CodigoError.HUELLA_CAMBIADA],
)
def test_los_errores_de_sesion_ofrecen_reconectar(qtbot, codigo):
    d = dialogo_pausa(qtbot, MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(codigo))
    assert AccionPausa.RECONECTAR in d.botones


def test_un_error_de_permiso_no_ofrece_reconectar_ni_sin_etiquetas(qtbot):
    err = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.Allocate", "ruta": "/vms/101"}
    )
    d = dialogo_pausa(qtbot, MotivoPausa.ERROR_GLOBAL, err)
    assert set(d.botones) == {AccionPausa.REINTENTAR, AccionPausa.DETENER}
    assert "VM.Allocate" in _cuerpo(d)


def test_ca_l24_4_etiqueta_rechazada_ofrece_seguir_sin_etiquetas_y_lo_explica(qtbot):
    d = dialogo_pausa(
        qtbot, MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA)
    )
    assert AccionPausa.SIN_ETIQUETAS in d.botones
    assert AccionPausa.RECONECTAR not in d.botones
    assert textos_botones(d)[AccionPausa.SIN_ETIQUETAS] == "Seguir sin etiquetas"
    cuerpo = _cuerpo(d)
    assert "no aceptó la etiqueta" in cuerpo
    assert "«Deshacer» solo podrá eliminar las máquinas que ProxLaunch confirme" in cuerpo


def test_ca_l14_3_el_error_repetido_dice_cuantas_fallaron_y_por_que(qtbot):
    err = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm"})
    d = dialogo_pausa(qtbot, MotivoPausa.REPETIDO, err, repetidos=3)
    assert "Fallaron 3 máquinas seguidas por la misma causa:" in _cuerpo(d)
    assert "¿Continuar o detener?" in _cuerpo(d)
    assert set(d.botones) == {AccionPausa.CONTINUAR, AccionPausa.DETENER}
    assert textos_botones(d)[AccionPausa.DETENER] == "Detener el lote"


@pytest.mark.parametrize(
    "n, frase", [(1, "Hay 1 máquina sin confirmar."), (3, "Hay 3 máquinas sin confirmar.")]
)
def test_ca_l17_2_la_pausa_por_conexion_cuenta_las_sin_confirmar_en_plural(qtbot, n, frase):
    d = dialogo_pausa(qtbot, MotivoPausa.CONEXION, None, sin_confirmar=n)
    assert f"Se perdió la conexión. {frase}" in _cuerpo(d)
    assert set(d.botones) == {AccionPausa.COMPROBAR_Y_CONTINUAR, AccionPausa.DETENER}
    assert textos_botones(d)[AccionPausa.COMPROBAR_Y_CONTINUAR] == "Comprobar y continuar"
    assert "Nunca vuelve a enviar una máquina que ya salió" in _cuerpo(d)


@pytest.mark.parametrize("motivo", list(MotivoPausa))
def test_la_opcion_segura_es_la_predeterminada_y_las_demas_no_responden_a_intro(qtbot, motivo):
    err = ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
    d = dialogo_pausa(qtbot, motivo, err, repetidos=3, sin_confirmar=1)
    assert d.botones[AccionPausa.DETENER].isDefault()
    otros = [b for a, b in d.botones.items() if a != AccionPausa.DETENER]
    assert all(not b.isDefault() and not b.autoDefault() for b in otros)


def test_el_dialogo_no_decide_nada_si_se_cierra_sin_elegir(qtbot):
    d = dialogo_pausa(qtbot, MotivoPausa.REPETIDO, None, repetidos=3)
    d.reject()
    assert d.accion is None


_CASOS_PAUSA = [
    (MotivoPausa.ERROR_GLOBAL, CodigoError.SESION_EXPIRADA, AccionPausa.RECONECTAR),
    (MotivoPausa.ERROR_GLOBAL, CodigoError.SESION_EXPIRADA, AccionPausa.REINTENTAR),
    (MotivoPausa.ERROR_GLOBAL, CodigoError.ETIQUETA_RECHAZADA, AccionPausa.SIN_ETIQUETAS),
    (MotivoPausa.ERROR_GLOBAL, CodigoError.ETIQUETA_RECHAZADA, AccionPausa.DETENER),
    (MotivoPausa.REPETIDO, CodigoError.SIN_ESPACIO, AccionPausa.CONTINUAR),
    (MotivoPausa.REPETIDO, CodigoError.SIN_ESPACIO, AccionPausa.DETENER),
    (MotivoPausa.CONEXION, None, AccionPausa.COMPROBAR_Y_CONTINUAR),
    (MotivoPausa.CONEXION, None, AccionPausa.DETENER),
]


@pytest.mark.parametrize("motivo, codigo, accion", _CASOS_PAUSA)
def test_cada_boton_fija_la_accion_y_acepta(qtbot, motivo, codigo, accion):
    error = ErrorProxLaunch(codigo) if codigo else None
    d = dialogo_pausa(qtbot, motivo, error, repetidos=3, sin_confirmar=1)
    d.botones[accion].click()
    assert d.accion == accion and d.result() == d.DialogCode.Accepted


def test_el_cuerpo_de_la_pausa_no_interpreta_html(qtbot):
    err = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "<b>peligro</b>")
    d = dialogo_pausa(qtbot, MotivoPausa.ERROR_GLOBAL, err)
    from PySide6.QtWidgets import QLabel

    cuerpos = [w for w in d.findChildren(QLabel) if w.accessibleName()]
    assert cuerpos and all(w.textFormat() == Qt.TextFormat.PlainText for w in cuerpos)


def _cuerpo(d):
    from PySide6.QtWidgets import QLabel

    return "\n".join(w.text() for w in d.findChildren(QLabel))


# --- Deshacer (RF-L18) ---------------------------------------------------------------------


def candidato(i, estado, *, elegible=None, motivo=None, incompleta=False):
    e = entrada(i, estado)
    elegible = estado in (EM.OK, EM.CON_AVISOS, EM.PARCIAL) if elegible is None else elegible
    return CandidatoRollback(
        e, elegible, None if elegible else (motivo or estado.value), incompleta
    )


def dialogo_deshacer(qtbot, candidatos):
    d = DialogoDeshacer(candidatos)
    qtbot.addWidget(d)
    return d


def items(d):
    return [d.lista.item(i) for i in range(d.lista.count())]


def test_ca_l18_3_las_elegibles_vienen_marcadas_y_el_boton_lleva_el_numero(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK), candidato(1, EM.OK), candidato(2, EM.OK)])
    assert all(i.checkState() == Qt.CheckState.Checked for i in items(d))
    assert d.boton_eliminar.text() == "Eliminar 3 máquinas"
    assert d._advertencia.text() == (
        "Se eliminarán estas 3 máquinas y sus discos de Proxmox. Esta acción no se puede deshacer."
    )
    assert len(d.elegidos()) == 3


def test_ca_l18_3_con_una_sola_maquina_el_texto_va_en_singular(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK)])
    assert d.boton_eliminar.text() == "Eliminar 1 máquina"
    assert "Se eliminará esta máquina y sus discos de Proxmox" in d._advertencia.text()


def test_ca_l18_3_el_foco_inicial_y_la_tecla_intro_son_de_cancelar(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK)])
    assert d.boton_cancelar.isDefault()
    assert not d.boton_eliminar.autoDefault() and not d.boton_eliminar.isDefault()


@pytest.mark.parametrize(
    "estado",
    [
        EM.ERROR,
        EM.NO_ENVIADA,
        EM.NO_CREADA_SEGURA,
        EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
        EM.CONEXION_PERDIDA,
    ],
)
def test_ca_l18_2_las_no_elegibles_salen_deshabilitadas_con_su_motivo(qtbot, estado):
    d = dialogo_deshacer(qtbot, [candidato(0, estado), candidato(1, EM.OK)])
    no_elegible = items(d)[0]
    assert not (no_elegible.flags() & Qt.ItemFlag.ItemIsEnabled)
    assert not (no_elegible.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    assert no_elegible.checkState() == Qt.CheckState.Unchecked
    assert "web-01 (101) — " in no_elegible.text() and len(no_elegible.text()) > 20
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [102]
    assert d.boton_eliminar.text() == "Eliminar 1 máquina"


def test_ca_l15_5_una_existe_sin_confirmar_nunca_queda_en_los_elegidos(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.EXISTE_SIN_CONFIRMAR_PROPIEDAD)])
    items(d)[0].setCheckState(Qt.CheckState.Checked)  # aunque se fuerce desde código
    assert d.elegidos() == []
    assert not d.boton_eliminar.isEnabled()


def test_propiedad_no_demostrada_se_explica_al_usuario(qtbot):
    c = candidato(0, EM.OK, elegible=False, motivo="propiedad_no_demostrada")
    d = dialogo_deshacer(qtbot, [c])
    assert "no podemos asegurar que sea suya" in items(d)[0].text()


def test_sin_ninguna_elegible_el_boton_de_eliminar_esta_deshabilitado(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.ERROR), candidato(1, EM.NO_ENVIADA)])
    assert d.elegidos() == [] and not d.boton_eliminar.isEnabled()
    assert d.boton_eliminar.text() == "Eliminar 0 máquinas"


def test_desmarcar_una_actualiza_el_numero_y_la_advertencia(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK), candidato(1, EM.OK), candidato(2, EM.OK)])
    items(d)[1].setCheckState(Qt.CheckState.Unchecked)
    assert d.boton_eliminar.text() == "Eliminar 2 máquinas"
    assert "estas 2 máquinas" in d._advertencia.text()
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [101, 103]


def test_desmarcar_todas_deshabilita_eliminar(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK), candidato(1, EM.OK)])
    for i in items(d):
        i.setCheckState(Qt.CheckState.Unchecked)
    assert not d.boton_eliminar.isEnabled()


def test_d20_solo_las_incompletas_marca_unicamente_las_incompletas(qtbot):
    d = dialogo_deshacer(
        qtbot,
        [
            candidato(0, EM.OK),
            candidato(1, EM.PARCIAL, incompleta=True),
            candidato(2, EM.CON_AVISOS, incompleta=True),
            candidato(3, EM.ERROR),
        ],
    )
    d.radio_incompletas.setChecked(True)
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [102, 103]
    d.radio_todo.setChecked(True)
    assert [c.entrada.elemento.vmid for c in d.elegidos()] == [101, 102, 103]


def test_eliminar_acepta_y_cancelar_rechaza(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK)])
    d.boton_cancelar.click()
    assert d.result() == d.DialogCode.Rejected
    d2 = dialogo_deshacer(qtbot, [candidato(0, EM.OK)])
    d2.boton_eliminar.click()
    assert d2.result() == d2.DialogCode.Accepted


def test_la_lista_de_deshacer_tiene_nombre_accesible(qtbot):
    d = dialogo_deshacer(qtbot, [candidato(0, EM.OK)])
    assert d.lista.accessibleName()


# --- Informe: copiar = guardar (CA-L19.2, CA-L19.8) ----------------------------------------------


@pytest.fixture
def informe():
    return informe_de(
        (
            entrada(0, EM.OK, upid="UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:101:ana@pve:"),
            entrada(1, EM.ERROR, error=ErrorProxLaunch(CodigoError.SIN_ESPACIO, {}, "no space")),
        ),
        perfil="Laboratorio de Ñandú",
    )


def test_ca_l19_8_copiar_y_guardar_producen_el_mismo_texto(qtbot, informe, tmp_path, monkeypatch):
    d = DialogoInforme(informe, tmp_path)
    qtbot.addWidget(d)
    destino = tmp_path / "carpeta con espacios" / "informe ñ.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), "Texto"))
    d.boton_copiar.click()
    copiado = QApplication.clipboard().text()
    d.boton_guardar.click()
    guardado = destino.read_text(encoding="utf-8")
    assert copiado == guardado == texto_informe(informe) == d.texto
    assert "Laboratorio de Ñandú" in guardado
    assert "Informe copiado." in d._estado.text() or "Guardado en" in d._estado.text()


def test_ca_l19_2_guardar_escribe_utf8_y_sugiere_nombre_con_el_id_del_lote(
    qtbot, informe, tmp_path, monkeypatch
):
    vistos = []

    def guardar(padre, titulo, sugerido, filtro):
        vistos.append(sugerido)
        return str(tmp_path / "x.txt"), filtro

    monkeypatch.setattr(QFileDialog, "getSaveFileName", guardar)
    d = DialogoInforme(informe, tmp_path)
    qtbot.addWidget(d)
    d.boton_guardar.click()
    assert vistos[0] == str(tmp_path / "informe-lote-ab12cd34.txt")
    assert (tmp_path / "x.txt").read_bytes().decode("utf-8") == d.texto


def test_guardar_cancelado_no_escribe_nada(qtbot, informe, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    d = DialogoInforme(informe, tmp_path)
    qtbot.addWidget(d)
    d.boton_guardar.click()
    assert list(tmp_path.iterdir()) == []
    assert d._estado.text() == ""


def test_el_titulo_del_dialogo_distingue_simulacion(qtbot, informe, tmp_path):
    sim = informe_de(informe.entradas, simulacion=True)
    d = DialogoInforme(sim, tmp_path)
    qtbot.addWidget(d)
    assert d.windowTitle() == "Simulación del lote"
    assert DialogoInforme(informe, tmp_path).windowTitle() == "Informe del lote"


def test_ca_l19_2_el_editor_es_monoespaciado_de_solo_lectura_y_con_nombre_accesible(
    qtbot, informe, tmp_path
):
    d = DialogoInforme(informe, tmp_path)
    qtbot.addWidget(d)
    assert d.editor.isReadOnly() and d.editor.property("mono") is True
    assert d.editor.accessibleName()
    assert d.editor.toPlainText() == d.texto
