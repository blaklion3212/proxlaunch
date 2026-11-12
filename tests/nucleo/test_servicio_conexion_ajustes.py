"""ServicioConexion: permisos detallados y aviso de versión no probada (RF-09, RF-12)."""

import pytest

from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.servicios.conexion import (
    CodigoAviso,
    ServicioConexion,
    permisos_faltantes,
    permisos_faltantes_detalle,
)

from .apoyo_api import (
    HUELLA_A,
    TOKEN_ID,
    TOKEN_SECRETO,
    TransporteFalso,
    crear_sesion,
    dato,
    perfil_basico,
)

A = "10.0.0.1"
TOKEN = CredencialToken(TOKEN_ID, TOKEN_SECRETO)


class LlaveroFalso:
    """Backend de keyring en memoria."""

    def __init__(self):
        self.almacen = {}

    def set_password(self, servicio, clave, valor):
        self.almacen[(servicio, clave)] = valor

    def get_password(self, servicio, clave):
        return self.almacen.get((servicio, clave))

    def delete_password(self, servicio, clave):
        self.almacen.pop((servicio, clave), None)


def _sesion_con_permisos(permisos):
    t = TransporteFalso().en("GET", "/access/permissions", permisos)
    return crear_sesion(t)


def _todos():
    from proxlaunch.nucleo.servicios.conexion import PERMISOS_POR_RUTA

    return {ruta: {p: 1 for p in privs} for ruta, privs in PERMISOS_POR_RUTA.items()}


def _avisos_de_permisos(sesion):
    return [a for a in sesion.avisos if a.codigo == CodigoAviso.PERMISOS_INCOMPLETOS]


# --- permisos_faltantes_detalle ----------------------------------------------------------


def test_permisos_completos_devuelve_lista_vacia_y_no_avisa():
    sesion = _sesion_con_permisos(dato("9.2", "permisos_completos.json"))
    assert permisos_faltantes_detalle(sesion) == []
    assert _avisos_de_permisos(sesion) == []


def test_falta_vm_allocate_se_reporta_con_su_ruta():
    sesion = _sesion_con_permisos(dato("9.2", "permisos_sin_vm_allocate.json"))
    assert permisos_faltantes_detalle(sesion) == [("VM.Allocate", "/vms")]
    (aviso,) = _avisos_de_permisos(sesion)
    assert aviso.params == {"privilegios": "VM.Allocate", "rutas": "VM.Allocate@/vms"}


def test_varios_faltantes_se_listan_en_orden_con_formato_privilegio_arroba_ruta():
    permisos = _todos()
    del permisos["/vms"]["VM.Allocate"]
    del permisos["/storage"]["Datastore.AllocateSpace"]
    sesion = _sesion_con_permisos(permisos)
    assert permisos_faltantes_detalle(sesion) == [
        ("VM.Allocate", "/vms"),
        ("Datastore.AllocateSpace", "/storage"),
    ]
    (aviso,) = _avisos_de_permisos(sesion)
    assert aviso.params["privilegios"] == "VM.Allocate,Datastore.AllocateSpace"
    assert aviso.params["rutas"] == "VM.Allocate@/vms,Datastore.AllocateSpace@/storage"


def test_sin_ningun_permiso_faltan_todos_los_requeridos():
    from proxlaunch.nucleo.servicios.conexion import PRIVILEGIOS_REQUERIDOS

    sesion = _sesion_con_permisos({})
    detalle = permisos_faltantes_detalle(sesion)
    assert [p for p, _ in detalle] == list(PRIVILEGIOS_REQUERIDOS)
    assert len(_avisos_de_permisos(sesion)) == 1


def test_si_la_consulta_falla_devuelve_none_y_no_añade_aviso():
    error = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    sesion = _sesion_con_permisos(error)
    assert permisos_faltantes_detalle(sesion) is None
    assert _avisos_de_permisos(sesion) == []


def test_permisos_faltantes_devuelve_solo_los_nombres_o_none():
    sesion = _sesion_con_permisos(dato("9.2", "permisos_sin_vm_allocate.json"))
    assert permisos_faltantes(sesion) == ["VM.Allocate"]
    fallo = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "x")
    assert permisos_faltantes(_sesion_con_permisos(fallo)) is None


def test_privilegio_heredado_de_la_raiz_con_propagate_cuenta_como_concedido():
    permisos = _todos()
    del permisos["/vms"]["VM.Allocate"]
    permisos["/"]["VM.Allocate"] = 1
    assert permisos_faltantes_detalle(_sesion_con_permisos(permisos)) == []


def test_privilegio_en_la_raiz_sin_propagate_no_cubre_la_subruta():
    permisos = _todos()
    del permisos["/vms"]["VM.Allocate"]
    permisos["/"]["VM.Allocate"] = 0
    assert permisos_faltantes_detalle(_sesion_con_permisos(permisos)) == [("VM.Allocate", "/vms")]


# --- VERSION_NO_PROBADA ------------------------------------------------------------------


@pytest.fixture
def servicio(tmp_path, reloj):
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    huellas.guardar(A, 8006, HUELLA_A)
    return ServicioConexion(
        crear_transporte_http, huellas, AlmacenSecretos(backend=LlaveroFalso()), reloj
    )


def _conectar(servicio, texto):
    t = TransporteFalso().en("GET", "/version", {"version": texto})
    servicio._fabrica = lambda perfil, huellas: t
    return servicio.conectar(perfil_basico(), TOKEN)


@pytest.mark.parametrize("texto", ["9.3", "9.3.1", "10.0", "10.1.2", "11.0"])
def test_version_mayor_que_la_ultima_conocida_añade_el_aviso(servicio, texto):
    sesion = _conectar(servicio, texto)
    avisos = [a for a in sesion.avisos if a.codigo == CodigoAviso.VERSION_NO_PROBADA]
    assert len(avisos) == 1
    assert avisos[0].params["version"] == texto


@pytest.mark.parametrize(
    "texto", ["8.0.4", "8.1", "8.2.4", "8.3.0", "8.4.1", "9.0", "9.1.5", "9.2", "9.2.1"]
)
def test_versiones_8_0_a_9_2_no_llevan_el_aviso(servicio, texto):
    sesion = _conectar(servicio, texto)
    assert all(a.codigo != CodigoAviso.VERSION_NO_PROBADA for a in sesion.avisos)


def test_el_aviso_de_version_no_bloquea_la_conexion(servicio):
    sesion = _conectar(servicio, "10.0")
    assert sesion.capacidades.es_soportada()
