"""ServicioCreacion (ronda F7): tras obtener el UPID, un fallo ajeno al desenlace de la tarea es
CONEXION_PERDIDA con upid; ``comprobar_ahora`` sin espera tolerante; ``existe_vm``; ``inv=``."""

import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.modelos.vm import Disco, Firmware
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_api import (
    RUTA_CONFIG,
    RUTA_CREAR,
    RUTA_ESTADO,
    RUTA_LOG,
    UPID,
    Secuencia,
    TransporteFalso,
    crear_sesion,
    dato,
    estado_tarea,
    rutas_creacion,
)

RED_CAIDA = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.1"}, "timeout")
CONFIG = dato("9.2", "qemu_config.json")
EXIT_SIN_ESPACIO = (
    "unable to create VM 100 - lvcreate 'pve/vm-100-disk-0' error:   "
    'Volume group "pve" has insufficient free space (1023 extents): 8192 required.'
)
ESTADO_SIN_ESPACIO = {"status": "stopped", "exitstatus": EXIT_SIN_ESPACIO}

AJENOS = [
    pytest.param(ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401"), id="sesion-expirada"),
    pytest.param(ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"), id="403"),
    pytest.param(ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "500 puntual"), id="500-puntual"),
    pytest.param(RuntimeError("fallo inesperado"), id="excepcion-no-proxlaunch"),
]


def _servicio(transporte, reloj, **opciones):
    return ServicioCreacion(crear_sesion(transporte, reloj=reloj), reloj, **opciones)


# --- Tras el UPID: fallos ajenos al desenlace de la tarea --------------------------------------


@pytest.mark.parametrize("fallo", AJENOS)
def test_en_crear_un_fallo_ajeno_al_sondear_es_conexion_perdida_con_upid(
    inv, hacer_cfg, reloj, fallo
):
    t = rutas_creacion(TransporteFalso(), estado=fallo)
    r = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid == UPID
    assert r.error is not None


@pytest.mark.parametrize("fallo", AJENOS)
def test_en_seguir_un_fallo_ajeno_es_conexion_perdida_con_upid(hacer_cfg, reloj, fallo):
    t = rutas_creacion(TransporteFalso(), estado=fallo)
    r = _servicio(t, reloj).seguir(hacer_cfg(), UPID, threading.Event())
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid == UPID


@pytest.mark.parametrize("fallo", AJENOS)
def test_en_comprobar_ahora_un_fallo_ajeno_es_conexion_perdida_con_upid(hacer_cfg, reloj, fallo):
    t = rutas_creacion(TransporteFalso(), estado=fallo)
    r = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid == UPID


@pytest.mark.parametrize("estado", ["ok", "warnings"])
def test_tarea_ok_o_con_avisos_y_config_falla_con_error_proxlaunch_es_con_avisos(
    inv, hacer_cfg, reloj, estado
):
    sin_permiso = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403 VM.Audit")
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea(estado), config=sin_permiso)
    r = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert r.desenlace == Desenlace.CON_AVISOS
    assert r.upid == UPID
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE


def test_tarea_fallida_y_luego_cae_la_red_al_leer_log_y_config_es_error_traducido(
    inv, hacer_cfg, reloj
):
    t = rutas_creacion(
        TransporteFalso(), estado=ESTADO_SIN_ESPACIO, config=RED_CAIDA, log=RED_CAIDA
    )
    r = _servicio(t, reloj, tolerancia_red_s=5.0).crear(
        hacer_cfg(), inv, lambda e: None, threading.Event()
    )
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.SIN_ESPACIO
    assert r.upid == UPID


def test_tarea_fallida_y_excepcion_inesperada_al_leer_config_sigue_siendo_error(
    inv, hacer_cfg, reloj
):
    t = rutas_creacion(TransporteFalso(), estado=ESTADO_SIN_ESPACIO, config=RuntimeError("x"))
    r = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.SIN_ESPACIO


# --- POST incierto -------------------------------------------------------------------------


def test_post_incierto_es_conexion_perdida_sin_upid_y_no_sondea(inv, hacer_cfg, reloj):
    incierto = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.1", "incierto": "1"}, "ReadTimeout"
    )
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), crear=incierto)
    r = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid is None
    assert r.error.params["incierto"] == "1"
    assert len(t.llamadas_a("POST", RUTA_CREAR)) == 1
    assert t.llamadas_a("GET", RUTA_ESTADO) == []


def test_post_con_excepcion_inesperada_es_conexion_perdida_sin_upid(inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), crear=RuntimeError("x"))
    r = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid is None


# --- comprobar_ahora: una sola ronda sin espera tolerante ------------------------------------


def test_comprobar_ahora_con_red_caida_en_estado_no_espera_ni_reintenta(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=RED_CAIDA)
    r = _servicio(t, reloj, tolerancia_red_s=60.0).comprobar_ahora(hacer_cfg(), UPID)
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert len(t.llamadas) == 1
    assert reloj.ahora() == 0.0


def test_comprobar_ahora_con_red_caida_al_leer_config_no_espera_ni_reintenta(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=RED_CAIDA)
    r = _servicio(t, reloj, tolerancia_red_s=60.0).comprobar_ahora(hacer_cfg(), UPID)
    assert r.desenlace == Desenlace.CONEXION_PERDIDA
    assert r.upid == UPID
    assert len(t.llamadas_a("GET", RUTA_CONFIG)) == 1
    assert reloj.ahora() == 0.0


def test_comprobar_ahora_con_tarea_fallida_y_red_caida_al_leer_es_error_sin_esperar(
    hacer_cfg, reloj
):
    t = rutas_creacion(
        TransporteFalso(), estado=ESTADO_SIN_ESPACIO, config=RED_CAIDA, log=RED_CAIDA
    )
    r = _servicio(t, reloj, tolerancia_red_s=60.0).comprobar_ahora(hacer_cfg(), UPID)
    assert r.desenlace == Desenlace.ERROR
    assert r.error.codigo == CodigoError.SIN_ESPACIO
    assert reloj.ahora() == 0.0


# --- existe_vm ----------------------------------------------------------------------------


def test_existe_vm_true_si_la_config_existe(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    assert _servicio(t, reloj).existe_vm(hacer_cfg()) is True


def test_existe_vm_false_si_la_config_no_existe(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"))  # config inexistente
    assert _servicio(t, reloj).existe_vm(hacer_cfg()) is False


@pytest.mark.parametrize(
    "fallo",
    [
        RED_CAIDA,
        ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403"),
        ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401"),
        RuntimeError("x"),
    ],
    ids=["red", "403", "sesion", "excepcion"],
)
def test_existe_vm_none_si_no_se_pudo_saber(hacer_cfg, reloj, fallo):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=fallo)
    assert _servicio(t, reloj).existe_vm(hacer_cfg()) is None
    assert len(t.llamadas_a("GET", RUTA_CONFIG)) == 1  # una sola consulta
    assert reloj.ahora() == 0.0


def test_existe_vm_nunca_envia_post(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    _servicio(t, reloj).existe_vm(hacer_cfg())
    assert t.metodos == ["GET"]


# --- inv= con OVMF -------------------------------------------------------------------------


def _cfg_ovmf(hacer_cfg):
    # Sin storage_efi explícito: el efidisk va al del primer disco (CA-14.2).
    return hacer_cfg(discos=[Disco("zfs1", 32)], firmware=Firmware.OVMF, storage_efi=None)


def test_seguir_con_inv_y_ovmf_incluye_el_storage_efi_efectivo(inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=ESTADO_SIN_ESPACIO)
    cfg = hacer_cfg(discos=[Disco("nfs1", 32)], firmware=Firmware.OVMF, storage_efi="zfs1")
    r = _servicio(t, reloj).seguir(cfg, UPID, threading.Event(), inv=inv)
    assert r.error.params["storage"] == "nfs1,zfs1"


def test_comprobar_ahora_con_inv_y_ovmf_incluye_el_storage_efi_efectivo(inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=ESTADO_SIN_ESPACIO)
    cfg = hacer_cfg(discos=[Disco("nfs1", 32)], firmware=Firmware.OVMF, storage_efi="zfs1")
    r = _servicio(t, reloj).comprobar_ahora(cfg, UPID, inv=inv)
    assert r.error.codigo == CodigoError.SIN_ESPACIO
    assert r.error.params["storage"] == "nfs1,zfs1"


def test_comprobar_ahora_con_ovmf_sin_disco_usa_el_primer_storage_con_images_del_inventario(
    inv, hacer_cfg, reloj
):
    t = rutas_creacion(TransporteFalso(), estado=ESTADO_SIN_ESPACIO)
    cfg = hacer_cfg(con_disco=False, discos=[], firmware=Firmware.OVMF, storage_efi=None)
    r = _servicio(t, reloj).comprobar_ahora(cfg, UPID, inv=inv)
    # Primer storage activo con «images» de pve1 en el inventario de pruebas.
    assert r.error.params["storage"] == "local-lvm"


# --- Sin estado compartido entre llamadas ----------------------------------------------------


def test_una_llamada_no_tolerante_no_afecta_a_la_siguiente_tolerante(inv, hacer_cfg, reloj):
    estados = Secuencia(RED_CAIDA, estado_tarea("ok"))
    t = rutas_creacion(TransporteFalso(), estado=estados, config=CONFIG)
    servicio = _servicio(t, reloj, tolerancia_red_s=30.0)
    primera = servicio.comprobar_ahora(hacer_cfg(), UPID)
    assert primera.desenlace == Desenlace.CONEXION_PERDIDA
    # Segunda llamada en la misma instancia: sondeo normal, sin heredar nada de la primera.
    t.en("GET", RUTA_ESTADO, Secuencia(RED_CAIDA, estado_tarea("ok")))
    segunda = servicio.seguir(hacer_cfg(), UPID, threading.Event())
    assert segunda.desenlace == Desenlace.OK


def test_una_cancelacion_previa_no_cancela_la_llamada_siguiente(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    servicio = _servicio(t, reloj)
    cancelado = threading.Event()
    cancelado.set()
    assert servicio.seguir(hacer_cfg(), UPID, cancelado).desenlace == Desenlace.CANCELADO
    assert servicio.seguir(hacer_cfg(), UPID, threading.Event()).desenlace == Desenlace.OK


def test_el_log_no_se_pide_si_la_tarea_ok_confirma_sin_avisos(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert t.llamadas_a("GET", RUTA_LOG) == []
