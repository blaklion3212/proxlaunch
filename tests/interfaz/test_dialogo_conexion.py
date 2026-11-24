"""DialogoConexion: perfiles, credenciales, huella, 2FA y errores (RF-01 a RF-08, RF-26)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from proxlaunch.interfaz.dialogos import conexion as modulo
from proxlaunch.interfaz.dialogos.conexion import DialogoConexion
from proxlaunch.interfaz.dialogos.huella import DialogoHuella
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.api.autenticacion import DesafioTFA, TipoTFA
from proxlaunch.nucleo.capacidades import VERSIONES_CONOCIDAS
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, CredencialToken, MetodoAuth
from proxlaunch.nucleo.servicios.conexion import (
    Aviso,
    CodigoAviso,
    EstadoHuella,
)

from .apoyo import HUELLA_A, HUELLA_B, info_huella, perfil, sesion_falsa

TOKEN = "ana@pve!lab=11111111-2222-3333-4444-555555555555"


@pytest.fixture
def lanzador(qtbot):
    lz = Lanzador()
    yield lz
    lz.esperar(2000)


@pytest.fixture
def crear(qtbot, deps, lanzador):
    """Fábrica del diálogo; usa servicios falsos y repositorios en ``tmp_path``."""

    def _crear(avanzado=False, **kw):
        d = DialogoConexion(
            deps.servicio_conexion,
            deps.perfiles,
            deps.huellas,
            deps.secretos,
            lanzador,
            avanzado=avanzado,
            **kw,
        )
        qtbot.addWidget(d)
        d.show()
        return d

    return _crear


def _esperar(qtbot, lanzador):
    qtbot.waitUntil(lambda: not lanzador.hay_activos, timeout=4000)


def _llenar_token(d, hosts="10.0.0.5", token=TOKEN, nombre="Lab"):
    d.nombre.setText(nombre)
    d.hosts.setPlainText(hosts)
    d.token.setText(token)


def _aceptar_huella(monkeypatch, reemplazar=False):
    def exec_(self):
        self.reemplazar = reemplazar
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DialogoHuella, "exec", exec_)


def _rechazar_huella(monkeypatch):
    monkeypatch.setattr(DialogoHuella, "exec", lambda self: QDialog.DialogCode.Rejected)


# --- Estado inicial ---------------------------------------------------------------------------


def test_casilla_recordar_credenciales_desmarcada_por_defecto(crear):
    d = crear()
    assert d.chk_recordar.isChecked() is False  # CA-08.1


def test_perfil_nuevo_por_defecto(crear):
    d = crear()
    assert d.combo_perfiles.count() == 1
    assert d.puerto.text() == "8006"
    assert d.radio_token.isChecked()
    assert d.fila_token.isVisible() and not d.fila_usuario.isVisible()
    assert not d.btn_duplicar.isEnabled() and not d.btn_eliminar.isEnabled()


def test_modo_basico_oculta_ssl_y_version_forzada(crear):
    """CA-06.1, CA-24.2, CA-26.3."""
    d = crear(avanzado=False)
    assert not d.fila_version.isVisible() and not d._contenedor_ssl.isVisible()


def test_modo_avanzado_muestra_ssl_y_version_forzada(crear):
    """CA-26.1."""
    d = crear(avanzado=True)
    assert d.fila_version.isVisible() and d._contenedor_ssl.isVisible()


def test_selector_de_version_se_puebla_desde_versiones_conocidas(crear):
    """CA-26.1."""
    d = crear(avanzado=True)
    datos = [d.combo_version.itemData(i) for i in range(d.combo_version.count())]
    assert datos == [None, *VERSIONES_CONOCIDAS]
    assert d.combo_version.itemText(0) == "Detectada"
    assert d.combo_version.itemText(d.combo_version.count() - 1) == "9.2"
    assert d.combo_version.currentData() is None


def _version_nueva(mayor, menor):
    """Tupla recién creada, como la que entrega ``RepositorioPreferencias.cargar``."""
    return (int(str(mayor)), int(str(menor)))


def test_version_forzada_previa_queda_seleccionada(crear):
    d = crear(avanzado=True, version_forzada=_version_nueva(8, 4))
    assert d.combo_version.currentData() == (8, 4)


def test_version_forzada_previa_se_conserva_al_conectar(qtbot, crear, servicio_falso):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa(version=(8, 4), forzada=True)
    d = crear(avanzado=True, version_forzada=_version_nueva(8, 4))
    _llenar_token(d)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert servicio_falso.llamadas[-1][3] == (8, 4)


def test_motivo_se_muestra_como_aviso(crear):
    d = crear(motivo="Tu sesión expiró")
    assert d._motivo.isVisible() and d._motivo.text() == "Tu sesión expiró"


def test_cambiar_a_usuario_y_contrasena_alterna_campos(crear):
    d = crear()
    d.radio_clave.setChecked(True)
    assert d.fila_usuario.isVisible() and d.fila_contrasena.isVisible() and d.fila_realm.isVisible()
    assert not d.fila_token.isVisible()
    assert d.token.echoMode() == d.token.EchoMode.Password
    assert d.contrasena.echoMode() == d.contrasena.EchoMode.Password


# --- Validación (V-18, V-19) ------------------------------------------------------------------


@pytest.mark.parametrize("token", ["", "abc", "ana@pve!lab", "ana!lab=x", "ana@pve!la b=x"])
def test_token_invalido_muestra_error_y_no_lanza_nada(qtbot, crear, servicio_falso, token):
    d = crear()
    _llenar_token(d, token=token)
    d.btn_conectar.click()
    assert d.fila_token.hay_error
    assert servicio_falso.llamadas == []


@pytest.mark.parametrize("host", ["", "no es host", "999.1.1.1", "-malo-"])
def test_host_invalido_muestra_error(crear, servicio_falso, host):
    d = crear()
    _llenar_token(d, hosts=host)
    d.btn_conectar.click()
    assert d.fila_hosts.hay_error
    assert servicio_falso.llamadas == []


@pytest.mark.parametrize("puerto", ["0", "70000", "abc"])
def test_puerto_invalido_muestra_error(crear, servicio_falso, puerto):
    d = crear()
    _llenar_token(d)
    d.puerto.setText(puerto)
    d.btn_conectar.click()
    assert d.fila_puerto.hay_error
    assert servicio_falso.llamadas == []


def test_host_con_esquema_y_puerto_se_normaliza(
    qtbot, crear, servicio_falso, lanzador, monkeypatch
):
    d = crear()
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA, host="10.0.0.5", puerto=9000)]
    servicio_falso.resultado_conectar = sesion_falsa(perfil(hosts=("10.0.0.5",), puerto=9000))
    _llenar_token(d, hosts="https://10.0.0.5:9000/")
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    enviado = servicio_falso.llamadas[0][1]
    assert enviado.hosts == ["10.0.0.5"] and enviado.puerto == 9000


def test_contrasena_vacia_con_metodo_clave_muestra_error(crear, servicio_falso):
    d = crear()
    d.hosts.setPlainText("10.0.0.5")
    d.radio_clave.setChecked(True)
    d.usuario.setText("ana")
    d.btn_conectar.click()
    assert d.fila_contrasena.hay_error
    assert servicio_falso.llamadas == []


def test_usuario_vacio_con_metodo_clave_muestra_error(crear):
    d = crear()
    d.hosts.setPlainText("10.0.0.5")
    d.radio_clave.setChecked(True)
    d.contrasena.setText("x")
    d.btn_conectar.click()
    assert d.fila_usuario.hay_error


def test_aviso_no_bloqueante_si_se_usa_root_pam(crear):
    """CA-25.4."""
    d = crear()
    d.token.setText("root@pam!lab=abc")
    assert d._aviso_root.isVisible()
    d.token.setText("ana@pve!lab=abc")
    assert not d._aviso_root.isVisible()
    d.radio_clave.setChecked(True)
    d.usuario.setText("root")
    d.realm.setCurrentText("pam")
    assert d._aviso_root.isVisible()


# --- Perfiles ---------------------------------------------------------------------------------


def test_guardar_perfil_lo_persiste_sin_secretos(crear, deps, llavero):
    d = crear()
    _llenar_token(d)
    d.btn_guardar.click()
    guardados = deps.perfiles.listar()
    assert len(guardados) == 1
    p = guardados[0]
    assert (p.nombre, p.hosts, p.puerto, p.metodo) == ("Lab", ["10.0.0.5"], 8006, MetodoAuth.TOKEN)
    assert p.recordar_credenciales is False
    assert llavero.datos == {}  # el token no se guarda sin casilla
    assert TOKEN.split("=")[1] not in (deps.perfiles._almacen.ruta.read_text(encoding="utf-8"))
    assert d.combo_perfiles.count() == 2
    assert d.btn_duplicar.isEnabled() and d.btn_eliminar.isEnabled()


def test_guardar_sin_nombre_usa_el_primer_host(crear, deps):
    d = crear()
    _llenar_token(d, nombre="")
    d.btn_guardar.click()
    assert deps.perfiles.listar()[0].nombre == "10.0.0.5"


def test_guardar_con_datos_invalidos_no_guarda(crear, deps):
    d = crear()
    _llenar_token(d, token="mal")
    d.btn_guardar.click()
    assert deps.perfiles.listar() == []


def test_al_abrir_se_carga_el_primer_perfil_guardado(crear, deps):
    deps.perfiles.guardar(perfil("a", "Alfa", ("10.0.0.1",), puerto=8007))
    deps.perfiles.guardar(perfil("b", "Beta", ("10.0.0.2",)))
    d = crear()
    assert d.nombre.text() == "Alfa" and d.puerto.text() == "8007"
    assert d.hosts.toPlainText() == "10.0.0.1"


def test_abrir_con_perfil_id_selecciona_ese_perfil(crear, deps):
    deps.perfiles.guardar(perfil("a", "Alfa"))
    deps.perfiles.guardar(perfil("b", "Beta", ("10.0.0.2",)))
    d = crear(perfil_id="b")
    assert d.nombre.text() == "Beta"


def test_elegir_perfil_nuevo_vacia_el_formulario(crear, deps):
    deps.perfiles.guardar(perfil("a", "Alfa"))
    d = crear()
    d.combo_perfiles.setCurrentIndex(0)
    assert d.nombre.text() == "" and d.hosts.toPlainText() == ""
    assert not d.chk_recordar.isChecked()


def test_perfil_con_contrasena_carga_usuario_y_metodo(crear, deps):
    deps.perfiles.guardar(
        perfil("a", "Clave", metodo=MetodoAuth.CONTRASENA, usuario="ana", realm="pve")
    )
    d = crear()
    assert d.radio_clave.isChecked() and d.usuario.text() == "ana"
    assert d.realm.currentText() == "pve"


def test_duplicar_crea_copia_con_otro_id_sin_secretos(crear, deps, llavero):
    deps.perfiles.guardar(perfil("a", "Alfa", recordar_credenciales=True))
    llavero.set_password("ProxLaunch", "perfil:a", "secreto")
    d = crear()
    d.btn_duplicar.click()
    perfiles = deps.perfiles.listar()
    assert len(perfiles) == 2
    copia = next(p for p in perfiles if p.id != "a")
    assert "Alfa" in copia.nombre
    assert ("ProxLaunch", f"perfil:{copia.id}") not in llavero.datos
    assert d.nombre.text() == copia.nombre  # queda seleccionada


def test_eliminar_pide_confirmacion_y_respeta_no(crear, deps):
    deps.perfiles.guardar(perfil("a", "Alfa"))
    d = crear()
    d.btn_eliminar.click()  # el conftest responde «No»
    assert len(deps.perfiles.listar()) == 1


def test_eliminar_confirmado_borra_perfil_secreto_y_huellas_huerfanas(
    crear, deps, llavero, monkeypatch
):
    deps.perfiles.guardar(perfil("a", "Alfa", ("10.0.0.1",), recordar_credenciales=True))
    deps.huellas.guardar("10.0.0.1", 8006, HUELLA_A)
    llavero.set_password("ProxLaunch", "perfil:a", "secreto")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    d = crear()
    d.btn_eliminar.click()
    assert deps.perfiles.listar() == []
    assert llavero.datos == {}  # CA-07.7
    assert deps.huellas.obtener("10.0.0.1", 8006) is None
    assert d.combo_perfiles.count() == 1


def test_nombre_repetido_avisa_sin_bloquear(crear, deps):
    deps.perfiles.guardar(perfil("a", "Alfa"))
    d = crear()
    d.combo_perfiles.setCurrentIndex(0)
    d.nombre.setText("Alfa")
    assert not d.fila_nombre._aviso_extra.isHidden()
    d.nombre.setText("Otro")
    assert d.fila_nombre._aviso_extra.isHidden()


def test_desmarcar_recordar_y_guardar_borra_el_secreto(crear, deps, llavero):
    # CA-08.6
    deps.perfiles.guardar(perfil("a", "Alfa", recordar_credenciales=True))
    llavero.set_password("ProxLaunch", "perfil:a", TOKEN)
    d = crear()
    assert d.token.placeholderText() == "(guardado en el llavero)"
    d.chk_recordar.setChecked(False)
    d.btn_guardar.click()
    assert llavero.datos == {}
    assert deps.perfiles.obtener("a").recordar_credenciales is False
    assert d.token.placeholderText() != "(guardado en el llavero)"


def test_perfil_recordado_usa_el_secreto_del_llavero_sin_reescribirlo(
    qtbot, crear, deps, llavero, servicio_falso, lanzador, monkeypatch
):
    deps.perfiles.guardar(perfil("a", "Alfa", recordar_credenciales=True))
    llavero.set_password("ProxLaunch", "perfil:a", TOKEN)
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear()
    assert d.token.text() == ""  # nunca se vuelve a mostrar
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    llamada = next(ll for ll in servicio_falso.llamadas if ll[0] == "conectar")
    assert llamada[2] == CredencialToken("ana@pve!lab", "11111111-2222-3333-4444-555555555555")


def test_llavero_roto_al_cargar_no_impide_abrir(crear, deps, llavero):
    class Roto:
        def get_password(self, *a):
            raise RuntimeError("sin llavero")

    deps.secretos._backend = Roto()
    deps.perfiles.guardar(perfil("a", "Alfa", recordar_credenciales=True))
    d = crear()
    assert d.nombre.text() == "Alfa"
    assert d.token.placeholderText() != "(guardado en el llavero)"


# --- Flujo de conexión ------------------------------------------------------------------------


def test_conexion_con_huella_ya_confirmada_conecta_y_acepta(
    qtbot, crear, deps, servicio_falso, lanzador
):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear()
    _llenar_token(d)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert d.sesion is not None and d.perfil_conectado is not None
    assert [ll[0] for ll in servicio_falso.llamadas] == ["consultar_huellas", "conectar"]
    assert len(deps.perfiles.listar()) == 1  # se guarda al conectar
    assert d.token.text() == "" and d.contrasena.text() == ""  # se limpian los secretos


def test_no_se_envian_credenciales_antes_de_resolver_la_huella(
    qtbot, crear, servicio_falso, lanzador, monkeypatch
):
    # RNF-07: huella nueva y el usuario cancela -> conectar no se llama nunca.
    servicio_falso.infos = [info_huella(EstadoHuella.NUEVA)]
    _rechazar_huella(monkeypatch)
    d = crear()
    _llenar_token(d)
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    assert [ll[0] for ll in servicio_falso.llamadas] == ["consultar_huellas"]
    assert d.btn_conectar.isEnabled()
    assert d.sesion is None


def test_huella_nueva_aceptada_se_confia_y_luego_se_conecta(
    qtbot, crear, servicio_falso, lanzador, monkeypatch
):
    servicio_falso.infos = [info_huella(EstadoHuella.NUEVA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    _aceptar_huella(monkeypatch)
    d = crear()
    _llenar_token(d)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert [ll[0] for ll in servicio_falso.llamadas] == ["consultar_huellas", "confiar", "conectar"]
    assert servicio_falso.llamadas[1][2] == HUELLA_A


def test_huella_cambiada_rechazada_bloquea_con_mensaje_y_no_guarda(
    qtbot, crear, servicio_falso, lanzador, monkeypatch
):
    servicio_falso.infos = [info_huella(EstadoHuella.CAMBIADA)]
    _rechazar_huella(monkeypatch)
    d = crear()
    _llenar_token(d)
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    assert "certificado del servidor cambió" in d._estado.text()
    assert [ll[0] for ll in servicio_falso.llamadas] == ["consultar_huellas"]  # CA-05.4


def test_huella_cambiada_con_reemplazo_usa_reemplazar_huella(
    qtbot, crear, servicio_falso, lanzador, monkeypatch
):
    servicio_falso.infos = [info_huella(EstadoHuella.CAMBIADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    _aceptar_huella(monkeypatch, reemplazar=True)
    d = crear(avanzado=True)
    _llenar_token(d)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    ops = [ll[0] for ll in servicio_falso.llamadas]
    assert ops == ["consultar_huellas", "reemplazar", "conectar"]
    assert servicio_falso.llamadas[1][2] == HUELLA_B


def test_ignorar_ssl_en_avanzado_no_pide_huella(qtbot, crear, servicio_falso, monkeypatch):
    servicio_falso.infos = [info_huella(EstadoHuella.IGNORADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    monkeypatch.setattr(
        DialogoHuella, "exec", lambda self: pytest.fail("no debe pedir huella con IGNORADA")
    )
    d = crear(avanzado=True)
    _llenar_token(d)
    d.chk_ignorar.setChecked(True)
    assert d._info.isVisible()
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert d.perfil_conectado.ignorar_ssl is True
    assert servicio_falso.llamadas[0][1].ignorar_ssl is True


def test_ignorar_ssl_guardado_no_se_aplica_en_modo_basico(qtbot, crear, deps, servicio_falso):
    # CA-06.3: fuera del modo avanzado se verifica siempre por huella.
    """CA-06.1."""
    deps.perfiles.guardar(perfil("a", "Alfa", ignorar_ssl=True))
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear(avanzado=False)
    d.token.setText(TOKEN)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert servicio_falso.llamadas[0][1].ignorar_ssl is False


def test_version_forzada_elegida_se_pasa_al_servicio(qtbot, crear, servicio_falso):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa(version=(9, 0), forzada=True)
    d = crear(avanzado=True)
    _llenar_token(d)
    d.combo_version.setCurrentIndex(
        next(i for i in range(d.combo_version.count()) if d.combo_version.itemData(i) == (9, 0))
    )
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert servicio_falso.llamadas[-1][3] == (9, 0)
    assert d.version_forzada == (9, 0)


def test_en_modo_basico_no_se_fuerza_version(qtbot, crear, servicio_falso):
    """CA-26.3."""
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear(avanzado=False, version_forzada=(9, 0))
    _llenar_token(d)
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert servicio_falso.llamadas[-1][3] is None


def test_varios_hosts_con_una_huella_nueva_y_otra_cambiada_piden_ambas(
    qtbot, crear, servicio_falso, monkeypatch
):
    servicio_falso.infos = [
        info_huella(EstadoHuella.NUEVA, host="10.0.0.5"),
        info_huella(EstadoHuella.CAMBIADA, host="10.0.0.6"),
        info_huella(EstadoHuella.CONFIRMADA, host="10.0.0.7"),
    ]
    servicio_falso.resultado_conectar = sesion_falsa()
    vistos = []

    def exec_(self):
        vistos.append(self.info.host)
        self.reemplazar = False
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DialogoHuella, "exec", exec_)
    d = crear()
    _llenar_token(d, hosts="10.0.0.5\n10.0.0.6\n10.0.0.7")
    with qtbot.waitSignal(d.accepted, timeout=4000):
        d.btn_conectar.click()
    assert vistos == ["10.0.0.5", "10.0.0.6"]


def test_el_boton_se_bloquea_mientras_se_conecta_y_no_lanza_dos_intentos(
    qtbot, crear, servicio_falso, lanzador
):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = ErrorProxLaunch(CodigoError.CREDENCIALES_INVALIDAS)
    d = crear()
    _llenar_token(d)
    d.btn_conectar.click()
    assert not d.btn_conectar.isEnabled()
    d._conectar()  # un segundo intento directo se ignora
    _esperar(qtbot, lanzador)
    assert [ll[0] for ll in servicio_falso.llamadas].count("consultar_huellas") == 1


# --- Errores (sección 7) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "fragmento"),
    [
        (ErrorProxLaunch(CodigoError.CREDENCIALES_INVALIDAS), "credenciales no son válidas"),
        (
            ErrorProxLaunch(CodigoError.VERSION_NO_SOPORTADA, {"minima": "8.0", "version": "7.4"}),
            "8.0",
        ),
        (ErrorProxLaunch(CodigoError.TFA_NO_SOPORTADO), "segundo factor"),
        (ErrorProxLaunch(CodigoError.HUELLA_NO_CONFIADA, {"host": "10.0.0.5"}), "10.0.0.5"),
    ],
)
def test_errores_de_conexion_se_muestran_en_espanol_y_se_puede_reintentar(
    qtbot, crear, servicio_falso, lanzador, error, fragmento
):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = error
    d = crear()
    _llenar_token(d)
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    assert fragmento in d._estado.text()
    assert d.btn_conectar.isEnabled()
    assert d.sesion is None


def test_credenciales_invalidas_con_contrasena_la_borra_del_campo(
    qtbot, crear, servicio_falso, lanzador
):
    # CA-02.2
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = ErrorProxLaunch(CodigoError.CREDENCIALES_INVALIDAS)
    d = crear()
    d.hosts.setPlainText("10.0.0.5")
    d.radio_clave.setChecked(True)
    d.usuario.setText("ana")
    d.contrasena.setText("mala")
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    assert d.contrasena.text() == ""
    assert d.usuario.text() == "ana"


def test_servidor_no_responde_muestra_destino_con_puerto(qtbot, crear, servicio_falso, lanzador):
    servicio_falso.infos = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.5", "hosts": "10.0.0.5", "motivos": ""}
    )
    d = crear()
    _llenar_token(d)
    d.puerto.setText("8007")
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    assert "10.0.0.5:8007" in d._estado.text()


def test_servidor_no_responde_con_varias_ips_da_el_motivo_de_cada_una(
    qtbot, crear, servicio_falso, lanzador
):
    servicio_falso.infos = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE,
        {"host": "a", "hosts": "10.0.0.5,10.0.0.6", "motivos": "10.0.0.5=timeout;10.0.0.6=refused"},
    )
    d = crear()
    _llenar_token(d, hosts="10.0.0.5\n10.0.0.6")
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    texto = d._estado.text()
    assert "10.0.0.5" in texto and "10.0.0.6" in texto


def test_cargar_otro_perfil_limpia_el_error(qtbot, crear, deps, servicio_falso, lanzador):
    deps.perfiles.guardar(perfil("a", "Alfa"))
    servicio_falso.infos = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    d = crear()
    d.token.setText(TOKEN)
    d.btn_conectar.click()
    _esperar(qtbot, lanzador)
    assert d._estado.isVisible()
    d.combo_perfiles.setCurrentIndex(0)
    assert not d._estado.isVisible()


# --- Segundo factor ---------------------------------------------------------------------------


def _desafio(totp=True, recuperacion=True):
    return DesafioTFA("ana@pve", "ticket", totp, recuperacion)


def _llegar_a_tfa(qtbot, d, servicio_falso, lanzador):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = _desafio()
    _llenar_token(d)
    d.btn_conectar.click()
    qtbot.waitUntil(lambda: d._dialogo_tfa is not None, timeout=4000)
    return d._dialogo_tfa


def test_conectar_con_desafio_abre_el_dialogo_de_dos_factores(
    qtbot, crear, servicio_falso, lanzador
):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    assert tfa.isVisible()
    assert not d.btn_conectar.isEnabled()
    assert "segundo factor" in d._info.text()


def test_totp_correcto_completa_la_conexion(qtbot, crear, servicio_falso, lanzador):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    servicio_falso.resultado_tfa = sesion_falsa()
    tfa._campo.setText("123456")
    with qtbot.waitSignal(d.accepted, timeout=4000):
        tfa._boton_ok.click()
    assert ("tfa", "123456", TipoTFA.TOTP) in servicio_falso.llamadas
    assert d.sesion is not None
    assert d.uso_clave_recuperacion is False
    assert d._dialogo_tfa is None


def test_clave_de_recuperacion_marca_su_uso(qtbot, crear, servicio_falso, lanzador):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    servicio_falso.resultado_tfa = sesion_falsa()
    tfa._alternar.clicked.emit()
    tfa._campo.setText("abcd-1234-ef56-7890")
    with qtbot.waitSignal(d.accepted, timeout=4000):
        tfa._boton_ok.click()
    assert d.uso_clave_recuperacion is True


def test_codigo_incorrecto_deja_reintentar_sin_reescribir_credenciales(
    qtbot, crear, servicio_falso, lanzador
):
    # CA-04.3
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    servicio_falso.resultado_tfa = [
        ErrorProxLaunch(CodigoError.TFA_CODIGO_INCORRECTO),
        sesion_falsa(),
    ]
    tfa._campo.setText("000000")
    tfa._boton_ok.click()
    qtbot.waitUntil(lambda: tfa._error.isVisible(), timeout=4000)
    assert "no es correcto" in tfa._error.text()
    assert d._dialogo_tfa is tfa and tfa._campo.isEnabled()
    tfa._campo.setText("123456")
    with qtbot.waitSignal(d.accepted, timeout=4000):
        tfa._boton_ok.click()


def test_otro_error_en_el_segundo_factor_cierra_el_dialogo_y_lo_muestra(
    qtbot, crear, servicio_falso, lanzador
):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    servicio_falso.resultado_tfa = ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
    tfa._campo.setText("123456")
    tfa._boton_ok.click()
    qtbot.waitUntil(lambda: d._dialogo_tfa is None, timeout=4000)
    assert "sesión expiró" in d._estado.text()
    assert d.btn_conectar.isEnabled()


def test_cancelar_el_segundo_factor_libera_el_dialogo_de_conexion(
    qtbot, crear, servicio_falso, lanzador
):
    d = crear()
    tfa = _llegar_a_tfa(qtbot, d, servicio_falso, lanzador)
    tfa._boton_cancelar.click()
    assert d._dialogo_tfa is None
    assert d.btn_conectar.isEnabled()
    assert d.sesion is None


def test_cancelar_el_dialogo_descarta_resultados_tardios(qtbot, crear, servicio_falso, lanzador):
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    d = crear()
    _llenar_token(d)
    d.btn_conectar.click()
    d.reject()  # el usuario cierra antes de que llegue la respuesta
    _esperar(qtbot, lanzador)
    assert d.sesion is None


# --- Avisos de la sesión ----------------------------------------------------------------------


def test_textos_de_avisos_antes_y_despues_de_conectar(qtbot, crear, servicio_falso):
    d = crear()
    assert d.textos_avisos() == []
    d.sesion = sesion_falsa(avisos=[Aviso(CodigoAviso.LLAVERO_NO_DISPONIBLE)])
    assert "llavero" in d.textos_avisos()[0]
    assert DialogoConexion.hay_aviso_llavero(d.sesion)
    assert not DialogoConexion.hay_aviso_llavero(sesion_falsa())


def test_el_modulo_expone_las_constantes_de_valores_por_defecto():
    assert modulo.PUERTO == 8006 and modulo.REALM == "pam"
    assert isinstance(CredencialContrasena("a", "pam", "x"), CredencialContrasena)


def test_enlace_de_la_guia_del_token_abre_el_dialogo(crear, monkeypatch):
    """CA-25.3: la pantalla de conexión trae «¿Cómo creo un API Token?» y abre la guía."""
    from proxlaunch.interfaz.dialogos import conexion as modulo

    abiertos = []
    monkeypatch.setattr(modulo.DialogoGuiaToken, "exec", lambda self: abiertos.append(self))
    d = crear(avanzado=False)
    assert d.enlace_guia.text() == "¿Cómo creo un API Token?"
    d.enlace_guia.clicked.emit()
    assert len(abiertos) == 1
