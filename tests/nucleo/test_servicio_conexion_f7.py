"""ServicioConexion (ronda F7): avisos recalculados en cada descubrimiento, ``cancelar_tfa`` y
``cerrar_sesion``. Sin red: el transporte es un doble en memoria."""

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket, DesafioTFA, TipoTFA
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, CredencialToken
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.registro import MASCARA, enmascarar
from proxlaunch.nucleo.servicios.conexion import (
    PERMISOS_POR_RUTA,
    CodigoAviso,
    ServicioConexion,
    permisos_faltantes,
)
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from .apoyo_api import (
    TOKEN_ID,
    TOKEN_SECRETO,
    Secuencia,
    TransporteFalso,
    cargar,
    crear_sesion,
    dato,
    perfil_basico,
    rutas_inventario,
)

CONTRASENA = CredencialContrasena("root", "pam", "Contra-Sena-F7-Unica")
TOKEN = CredencialToken(TOKEN_ID, TOKEN_SECRETO)
PERMISO = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "Sys.Audit"})


# --- Avisos recalculados en cada descubrimiento -----------------------------------------------


def _inventario_con(estado_cluster):
    t = TransporteFalso()
    rutas_inventario(t)
    t.en("GET", "/cluster/status", estado_cluster)
    return t


def _avisos(sesion, codigo):
    return [a for a in sesion.avisos if a.codigo == codigo]


def test_el_aviso_de_topologia_degradada_desaparece_si_ya_no_aplica():
    estados = Secuencia(PERMISO, dato("9.2", "cluster_status.json"))
    sesion = crear_sesion(_inventario_con(estados))
    descubrir(sesion)
    assert len(_avisos(sesion, CodigoAviso.TOPOLOGIA_DEGRADADA)) == 1
    descubrir(sesion)
    assert _avisos(sesion, CodigoAviso.TOPOLOGIA_DEGRADADA) == []


def test_el_aviso_de_topologia_no_se_duplica_en_descubrimientos_repetidos():
    sesion = crear_sesion(_inventario_con(PERMISO))
    for _ in range(4):
        descubrir(sesion)
    assert len(_avisos(sesion, CodigoAviso.TOPOLOGIA_DEGRADADA)) == 1


def test_el_aviso_de_topologia_se_recalcula_con_el_numero_de_nodos_actual():
    sesion = crear_sesion(_inventario_con(PERMISO))
    descubrir(sesion)
    (aviso,) = _avisos(sesion, CodigoAviso.TOPOLOGIA_DEGRADADA)
    assert aviso.params == {"nodos": "3"}


def test_el_aviso_de_permisos_se_retira_si_ya_no_faltan():
    completos = {r: {p: 1 for p in ps} for r, ps in PERMISOS_POR_RUTA.items()}
    incompletos = {**completos, "/vms": {}}
    t = TransporteFalso().en("GET", "/access/permissions", Secuencia(incompletos, completos))
    sesion = crear_sesion(t)
    assert permisos_faltantes(sesion) != []
    assert len(_avisos(sesion, CodigoAviso.PERMISOS_INCOMPLETOS)) == 1
    assert permisos_faltantes(sesion) == []
    assert _avisos(sesion, CodigoAviso.PERMISOS_INCOMPLETOS) == []


def test_el_aviso_de_permisos_no_se_duplica_y_se_recalcula():
    completos = {r: {p: 1 for p in ps} for r, ps in PERMISOS_POR_RUTA.items()}
    sin_vms = {**completos, "/vms": {}}
    sin_storage = {**completos, "/storage": {}}
    t = TransporteFalso().en("GET", "/access/permissions", Secuencia(sin_vms, sin_vms, sin_storage))
    sesion = crear_sesion(t)
    for _ in range(3):
        permisos_faltantes(sesion)
    (aviso,) = _avisos(sesion, CodigoAviso.PERMISOS_INCOMPLETOS)
    assert aviso.params["privilegios"] == "Datastore.AllocateSpace"


def test_recalcular_avisos_no_toca_los_otros_avisos():
    from proxlaunch.nucleo.servicios.conexion import Aviso

    sesion = crear_sesion(_inventario_con(PERMISO))
    sesion.avisos.append(Aviso(CodigoAviso.VERSION_NO_PROBADA, {"version": "10.0"}))
    descubrir(sesion)
    descubrir(sesion)
    assert len(_avisos(sesion, CodigoAviso.VERSION_NO_PROBADA)) == 1


# --- cancelar_tfa / cerrar_sesion ---------------------------------------------------------------


class TransporteCerrable(TransporteFalso):
    """Doble que además registra el cierre y los autenticadores asignados."""

    def __init__(self):
        super().__init__()
        self.cerrado = 0
        self.autenticadores = []

    def usar_autenticador(self, auth):
        super().usar_autenticador(auth)
        self.autenticadores.append(auth)

    def cerrar(self):
        self.cerrado += 1


@pytest.fixture
def entorno(tmp_path, reloj):
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    transportes: list[TransporteCerrable] = []
    respuesta_login = {"valor": cargar("9.2", "ticket_completo.json")["data"]}

    def fabrica(perfil, _huellas):
        t = TransporteCerrable()
        t.en("POST", "/access/ticket", lambda _l: respuesta_login["valor"])
        t.en("GET", "/version", dato("9.2", "version.json"))
        transportes.append(t)
        return t

    class _Llavero:
        def set_password(self, *a): ...
        def get_password(self, *a):
            return None

        def delete_password(self, *a): ...

    servicio = ServicioConexion(
        fabrica, huellas, AlmacenSecretos(backend=_Llavero()), reloj, obtener_huella_fn=None
    )

    class E:
        pass

    e = E()
    e.servicio, e.transportes, e.login = servicio, transportes, respuesta_login
    e.perfil = perfil_basico(ignorar_ssl=True)
    return e


def _con_2fa(entorno):
    entorno.login["valor"] = cargar("9.2", "ticket_tfa_totp_recovery.json")["data"]


def test_cerrar_sesion_cierra_el_transporte_y_olvida_el_ticket(entorno):
    sesion = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    transporte = entorno.transportes[-1]
    auth = transporte.autenticadores[-1]
    assert isinstance(auth, AutenticadorTicket) and auth.ticket.ticket != ""
    entorno.servicio.cerrar_sesion(sesion)
    assert transporte.cerrado == 1
    assert auth.ticket.ticket == "" and auth.ticket.csrf == ""
    assert transporte.autenticadores[-1] is None


def test_cerrar_sesion_olvida_el_secreto_del_token(entorno):
    sesion = entorno.servicio.conectar(entorno.perfil, TOKEN)
    transporte = entorno.transportes[-1]
    auth = transporte.autenticadores[0]
    entorno.servicio.cerrar_sesion(sesion)
    assert transporte.cerrado == 1
    cab = {}
    auth.aplicar("GET", cab, {})
    assert TOKEN_SECRETO not in str(cab)


def test_cerrar_la_ultima_sesion_olvida_los_secretos_del_registro(entorno):
    sesion = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    assert enmascarar(CONTRASENA.contrasena) == MASCARA
    entorno.servicio.cerrar_sesion(sesion)
    assert enmascarar(CONTRASENA.contrasena) == CONTRASENA.contrasena


def test_con_otra_sesion_abierta_no_se_olvidan_los_secretos(entorno):
    una = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    otra = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    entorno.servicio.cerrar_sesion(una)
    assert enmascarar(CONTRASENA.contrasena) == MASCARA
    entorno.servicio.cerrar_sesion(otra)
    assert enmascarar(CONTRASENA.contrasena) == CONTRASENA.contrasena


def test_con_2fa_pendiente_no_se_olvidan_los_secretos(entorno):
    sesion = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    _con_2fa(entorno)
    desafio = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    assert isinstance(desafio, DesafioTFA)
    entorno.servicio.cerrar_sesion(sesion)
    assert enmascarar(CONTRASENA.contrasena) == MASCARA


def test_cancelar_tfa_descarta_lo_pendiente_y_cierra_su_transporte(entorno):
    _con_2fa(entorno)
    desafio = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    transporte = entorno.transportes[-1]
    entorno.servicio.cancelar_tfa(desafio)
    assert transporte.cerrado == 1
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(desafio, "123456", TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.SESION_EXPIRADA


def test_cancelar_tfa_dos_veces_o_de_un_desafio_desconocido_no_falla(entorno):
    _con_2fa(entorno)
    desafio = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    entorno.servicio.cancelar_tfa(desafio)
    entorno.servicio.cancelar_tfa(desafio)


def test_tras_cancelar_el_2fa_cerrar_la_ultima_sesion_si_olvida_los_secretos(entorno):
    sesion = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    _con_2fa(entorno)
    desafio = entorno.servicio.conectar(entorno.perfil, CONTRASENA)
    entorno.servicio.cancelar_tfa(desafio)
    entorno.servicio.cerrar_sesion(sesion)
    assert enmascarar(CONTRASENA.contrasena) == CONTRASENA.contrasena
