"""Rol mínimo ProxLaunchCreador y efecto real de quitar cada privilegio (f1 §5).

Para cada variante se crea un usuario ``plcvar@pve`` con un rol que carece de UN
privilegio, y se ejecuta el flujo real (conectar, descubrir, crear, comprobar). Todo se
borra al terminar. El usuario ``plc@pve`` completo lo gestiona la fixture ``plc``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, CredencialToken, MetodoAuth
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, Firmware, InterfazRed
from proxlaunch.nucleo.reloj import RelojReal
from proxlaunch.nucleo.servicios.conexion import (
    CodigoAviso,
    permisos_faltantes,
    permisos_faltantes_detalle,
)
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion
from proxlaunch.nucleo.servicios.descubrimiento import descubrir

from . import apoyo_lab as lab

pytestmark = pytest.mark.integracion

USUARIO_VAR = "plcvar@pve"
ROL_VAR = "PLCVariante"


def _cfg(vmid: int, **kw) -> ConfiguracionVM:
    base = {
        "vmid": vmid,
        "nombre": f"plc-{vmid}",
        "nodo": lab.NODO,
        "discos": [Disco(storage="lab-lvmthin", tamano_gib=1)],
        "redes": [InterfazRed(bridge="vmbr0")],
    }
    base.update(kw)
    return ConfiguracionVM(**base)


def _crear(sesion, cfg, inv):
    return ServicioCreacion(sesion, RelojReal()).crear(cfg, inv, lambda _e: None, threading.Event())


@pytest.fixture
def sesion_sin(entorno) -> Iterator[Callable]:
    """Fábrica de sesiones de un usuario cuyo rol carece de ``quitar`` (token privsep=0)."""
    abiertas = []

    @contextmanager
    def abrir(quitar: str | None):
        privs = tuple(p for p in (*lab.PRIVILEGIOS_ROL, *lab.PRIVILEGIOS_SOBRANTES) if p != quitar)
        lab.borrar_usuario(USUARIO_VAR)
        lab.borrar_rol(ROL_VAR)
        lab.crear_rol(privs, ROL_VAR)
        try:
            lab.crear_usuario(USUARIO_VAR, lab.nuevo_secreto(), ROL_VAR)
            token_id, secreto = lab.crear_token(USUARIO_VAR, "t1").rsplit("=", 1)
            p = lab.perfil(MetodoAuth.TOKEN, token_id)
            lab.confiar_en_laboratorio(entorno, p)
            sesion = entorno.servicio.conectar(p, CredencialToken(token_id, secreto))
            abiertas.append(sesion)
            yield sesion
        finally:
            lab.borrar_usuario(USUARIO_VAR)
            lab.borrar_rol(ROL_VAR)

    yield abrir
    for s in abiertas:
        entorno.servicio.cerrar_sesion(s)


# --- Flujo completo con el rol mínimo ------------------------------------------------


@pytest.mark.parametrize("via", ["token", "contrasena"])
def test_flujo_completo_con_el_rol_minimo(via, entorno, plc, vms):
    if via == "token":
        p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
        cred = CredencialToken(plc.token_id, plc.token_secreto)
    else:
        p = lab.perfil(MetodoAuth.CONTRASENA, "plc")
        cred = CredencialContrasena("plc", "pve", plc.contrasena)
    lab.confiar_en_laboratorio(entorno, p)
    sesion = entorno.servicio.conectar(p, cred)
    try:
        assert permisos_faltantes(sesion) == []
        inv = descubrir(sesion)
        assert sesion.avisos == []
        for vmid, fw, st in (
            (vms(9020 if via == "token" else 9022), Firmware.SEABIOS, "lab-lvmthin"),
            (vms(9021 if via == "token" else 9023), Firmware.OVMF, "local"),
        ):
            cfg = _cfg(vmid, firmware=fw, discos=[Disco(st, 1)])
            etapas: list[Etapa] = []
            r = ServicioCreacion(sesion, RelojReal()).crear(
                cfg, inv, etapas.append, threading.Event()
            )
            assert r.desenlace == Desenlace.OK, r
            assert etapas[-1] == Etapa.LISTO
            assert sesion.cliente.config_vm(lab.NODO, vmid)["name"] == f"plc-{vmid}"
    finally:
        entorno.servicio.cerrar_sesion(sesion)


# --- Privilegios que sobran o faltan --------------------------------------------------


def test_sin_vm_config_disk_no_bloquea_ni_avisa(sesion_sin, vms):
    with sesion_sin("VM.Config.Disk") as s:
        assert permisos_faltantes_detalle(s) == []  # ya no es requerido
        assert s.avisos == []
        inv = descubrir(s)
        for vmid, fw, st in (
            (vms(9030), Firmware.SEABIOS, "lab-lvmthin"),
            (vms(9031), Firmware.OVMF, "local"),
        ):
            r = _crear(s, _cfg(vmid, firmware=fw, discos=[Disco(st, 1)]), inv)
            assert r.desenlace == Desenlace.OK, r  # crear discos nuevos no exige Disk


def test_sin_vm_audit_la_mv_se_crea_pero_no_se_puede_confirmar(sesion_sin, vms):
    with sesion_sin("VM.Audit") as s:
        assert permisos_faltantes_detalle(s) == [("VM.Audit", "/vms")]
        aviso = next(a for a in s.avisos if a.codigo == CodigoAviso.PERMISOS_INCOMPLETOS)
        assert aviso.params["rutas"] == "VM.Audit@/vms"
        vmid = vms(9032)
        inv = descubrir(s)
        r = _crear(s, _cfg(vmid), inv)
        assert r.desenlace == Desenlace.CON_AVISOS, r
        assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
        assert r.error.params == {"privilegio": "VM.Audit", "ruta": f"/vms/{vmid}"}
        assert "TASK OK" in r.log_tarea[-1]
        # La MV existe de verdad (verdad independiente), pero el usuario no puede leerla.
        assert vmid in lab.vmids_de_prueba()
        assert ServicioCreacion(s, RelojReal()).existe_vm(_cfg(vmid)) is None


def test_sin_sys_audit_degrada_topologia_y_oculta_memoria_y_cpu(sesion_sin, vms):
    with sesion_sin("Sys.Audit") as s:
        inv = descubrir(s)
        assert inv.topologia.es_cluster is False
        assert inv.topologia.nodos[0].mem_libre_mib is None
        assert inv.topologia.nodos[0].cpus is None
        codigos = {a.codigo for a in s.avisos}
        assert CodigoAviso.TOPOLOGIA_DEGRADADA in codigos
        assert permisos_faltantes_detalle(s) == [("Sys.Audit", "/")]
        aviso = next(a for a in s.avisos if a.codigo == CodigoAviso.PERMISOS_INCOMPLETOS)
        assert aviso.params["rutas"] == "Sys.Audit@/"
        r = _crear(s, _cfg(vms(9033)), inv)
        assert r.desenlace == Desenlace.OK, r  # el dueño de la tarea la puede seguir


def test_sin_sdn_use_no_aparecen_bridges_y_proxmox_rechaza_la_red(sesion_sin, vms):
    with sesion_sin("SDN.Use") as s:
        inv = descubrir(s)
        assert inv.bridges[lab.NODO] == ()
        assert permisos_faltantes_detalle(s) == [("SDN.Use", "/sdn/zones/localnetwork")]
        aviso = next(a for a in s.avisos if a.codigo == CodigoAviso.PERMISOS_INCOMPLETOS)
        assert aviso.params["rutas"] == "SDN.Use@/sdn/zones/localnetwork"
        # La validación local ya frena (V-16.sinredes): nada llega a Proxmox.
        r = _crear(s, _cfg(vms(9034)), inv)
        assert r.desenlace == Desenlace.ERROR
        assert r.error.codigo == CodigoError.PARAMETRO_INVALIDO
        # Si se saltara la validación, Proxmox lo rechaza con 403 sobre la ruta SDN.
        params = construir_parametros(_cfg(vms(9035)), inv)
        with pytest.raises(ErrorProxLaunch) as e:
            s.cliente.crear_vm(lab.NODO, params)
        assert e.value.codigo == CodigoError.PERMISO_INSUFICIENTE
        assert e.value.params["privilegio"] == "SDN.Use"
        assert e.value.params["ruta"].startswith("/sdn/zones/localnetwork/vmbr0")
        assert 9035 not in lab.vmids_de_prueba()


def test_sin_datastore_audit_no_cambia_nada_ni_avisa(sesion_sin, vms):
    with sesion_sin("Datastore.Audit") as s:
        assert permisos_faltantes_detalle(s) == []  # no es obligatorio (AllocateSpace basta)
        assert s.avisos == []
        inv = descubrir(s)
        assert {st.id for st in inv.storages[lab.NODO]} == {"local", "lab-lvmthin"}
        r = _crear(s, _cfg(vms(9036), firmware=Firmware.OVMF, discos=[Disco("local", 1)]), inv)
        assert r.desenlace == Desenlace.OK, r


# --- Privilegios imprescindibles ------------------------------------------------------

BLOQUEANTES = [
    ("VM.Config.Options", "/vms/"),
    ("VM.Config.HWType", "/vms/"),
    ("VM.Config.CPU", "/vms/"),
    ("VM.Config.Memory", "/vms/"),
    ("VM.Config.Network", "/vms/"),
    ("Datastore.AllocateSpace", "/storage/"),
]


@pytest.mark.parametrize(("privilegio", "prefijo_ruta"), BLOQUEANTES)
def test_sin_el_privilegio_imprescindible_proxmox_rechaza_con_403_y_ruta(
    privilegio, prefijo_ruta, sesion_sin, vms
):
    with sesion_sin(privilegio) as s:
        inv = descubrir(s)
        vmid = vms(9037)
        r = _crear(s, _cfg(vmid), inv)
        assert r.desenlace == Desenlace.ERROR, r
        assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
        assert r.error.params["privilegio"] == privilegio
        assert r.error.params["ruta"].startswith(prefijo_ruta)
        assert permisos_faltantes(s) == [privilegio]
        assert vmid not in lab.vmids_de_prueba()


def test_sin_vm_allocate_proxmox_rechaza_y_el_privilegio_se_infiere(sesion_sin, vms):
    with sesion_sin("VM.Allocate") as s:
        inv = descubrir(s)
        vmid = vms(9038)
        r = _crear(s, _cfg(vmid), inv)
        assert r.desenlace == Desenlace.ERROR, r
        assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
        # El 403 real no trae "(ruta, privilegio)": ProxLaunch infiere VM.Allocate y lo marca.
        assert r.error.params == {
            "privilegio": "VM.Allocate",
            "ruta": f"/vms/{vmid}",
            "inferido": "1",
        }
        assert permisos_faltantes(s) == ["VM.Allocate"]
        assert vmid not in lab.vmids_de_prueba()


# --- Formas de conceder el rol que no sirven ------------------------------------------


def test_acl_sin_propagar_se_detecta_en_las_rutas_hijas(entorno):
    """Rol en ``/`` con propagate=0: solo vale para ``/``; el aviso lo refleja."""
    lab.borrar_usuario(USUARIO_VAR)
    lab.borrar_rol(ROL_VAR)
    lab.crear_rol(lab.PRIVILEGIOS_ROL, ROL_VAR)
    try:
        lab.ssh(f"sudo pveum user add {USUARIO_VAR}")
        lab.ssh(f"sudo pveum acl modify / --users {USUARIO_VAR} --roles {ROL_VAR} --propagate 0")
        token_id, secreto = lab.crear_token(USUARIO_VAR, "t1").rsplit("=", 1)
        p = lab.perfil(MetodoAuth.TOKEN, token_id)
        lab.confiar_en_laboratorio(entorno, p)
        s = entorno.servicio.conectar(p, CredencialToken(token_id, secreto))
        try:
            faltan = permisos_faltantes_detalle(s)
            assert faltan is not None
            nombres = {priv for priv, _ in faltan}
            # Solo Sys.Audit (pedido en `/`, la propia ruta) sigue vigente.
            assert nombres == set(lab.PRIVILEGIOS_ROL) - {"Sys.Audit"}
            assert ("VM.Allocate", "/vms") in faltan
            inv = descubrir(s)
            # Sin SDN.Use heredado Proxmox no lista bridges: no se puede elegir red.
            assert inv.bridges[lab.NODO] == ()
        finally:
            entorno.servicio.cerrar_sesion(s)
    finally:
        lab.borrar_usuario(USUARIO_VAR)
        lab.borrar_rol(ROL_VAR)


def test_token_con_privsep_sin_acl_propia_no_tiene_permisos(entorno):
    """Token privsep=1: sus permisos son la intersección con los del token (sin ACL = nada)."""
    lab.borrar_usuario(USUARIO_VAR)
    lab.borrar_rol(ROL_VAR)
    lab.crear_rol(lab.PRIVILEGIOS_ROL, ROL_VAR)
    try:
        lab.crear_usuario(USUARIO_VAR, lab.nuevo_secreto(), ROL_VAR)
        token_id, secreto = lab.crear_token(USUARIO_VAR, "ps", privsep=1).rsplit("=", 1)
        p = lab.perfil(MetodoAuth.TOKEN, token_id)
        lab.confiar_en_laboratorio(entorno, p)
        s = entorno.servicio.conectar(p, CredencialToken(token_id, secreto))
        try:
            faltan = permisos_faltantes(s)
            assert faltan is not None
            assert set(faltan) == set(lab.PRIVILEGIOS_ROL)
            aviso = next(a for a in s.avisos if a.codigo == CodigoAviso.PERMISOS_INCOMPLETOS)
            assert "VM.Allocate@/vms" in aviso.params["rutas"].split(",")
        finally:
            entorno.servicio.cerrar_sesion(s)
    finally:
        lab.borrar_usuario(USUARIO_VAR)
        lab.borrar_rol(ROL_VAR)
