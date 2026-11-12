"""Descubrimiento: los errores de sesión no se disfrazan de «nodo caído» (CA-03.3, CA-11.8)."""

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.transporte import TransporteHttp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from .apoyo_api import (
    HUELLA_A,
    TransporteFalso,
    agregar_error,
    crear_sesion,
    dato,
    rutas_inventario,
    url,
)


def _transporte(**fallos):
    t = TransporteFalso()
    rutas_inventario(t)
    for nodo, valor in fallos.items():
        t.en("GET", f"/nodes/{nodo}/storage", valor)
    return t


@pytest.mark.parametrize(
    "codigo", [CodigoError.SESION_EXPIRADA, CodigoError.CREDENCIALES_INVALIDAS]
)
def test_sesion_expirada_en_un_solo_nodo_se_propaga_y_no_lo_marca_caido(codigo):
    t = _transporte(pve3=ErrorProxLaunch(codigo, {}, "401"))
    with pytest.raises(ErrorProxLaunch) as e:
        descubrir(crear_sesion(t))
    assert e.value.codigo == codigo


def test_401_real_en_un_nodo_se_propaga_como_error_de_sesion(rsps):
    host = "10.0.0.1"
    rsps.get(url(host, "/cluster/status"), json={"data": dato("9.2", "cluster_status.json")})
    rsps.get(url(host, "/nodes"), json={"data": dato("9.2", "nodes.json")})
    rsps.get(url(host, "/cluster/nextid"), json={"data": "101"})
    for n in ("pve1", "pve2", "pve3"):
        rsps.get(url(host, f"/nodes/{n}/network"), json={"data": dato("9.2", "network.json")})
        if n == "pve2":
            agregar_error(rsps, "GET", url(host, f"/nodes/{n}/storage"), 401, "No ticket")
        else:
            rsps.get(url(host, f"/nodes/{n}/storage"), json={"data": dato("9.2", "storage.json")})
    transporte = TransporteHttp([host], 8006, huellas={host: HUELLA_A})
    cliente = ClienteProxmox(
        transporte, AutenticadorToken(CredencialToken("ana@pve!lab", "s")), RelojSimulado()
    )
    sesion = crear_sesion(TransporteFalso())
    sesion.cliente = cliente
    with pytest.raises(ErrorProxLaunch) as e:
        descubrir(sesion)
    assert e.value.codigo not in (
        CodigoError.NODO_NO_DISPONIBLE,
        CodigoError.SERVIDOR_NO_RESPONDE,
    )


def test_403_en_todos_los_nodos_se_propaga_como_permiso_insuficiente():
    error = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "Datastore"}, "403")
    t = _transporte(pve1=error, pve2=error, pve3=error)
    with pytest.raises(ErrorProxLaunch) as e:
        descubrir(crear_sesion(t))
    assert e.value.codigo == CodigoError.PERMISO_INSUFICIENTE


def test_un_nodo_con_nodo_no_disponible_si_queda_registrado_y_fuera_de_linea():
    t = _transporte(pve3=ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve3"}, "595"))
    inv = descubrir(crear_sesion(t))
    assert inv.errores_por_nodo["pve3"].codigo == CodigoError.NODO_NO_DISPONIBLE
    estado = {n.nombre: n.en_linea for n in inv.topologia.nodos}
    assert estado["pve3"] is False
    assert estado["pve1"] is True
