"""ServicioCreacion: cancelación en esperas tolerantes, SIN_ESPACIO con ids de storage,
``seguir``, ``comprobar_ahora`` y ``al_enviar`` (RF-13, RF-19, RF-20, CA-20.x)."""

import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa
from proxlaunch.nucleo.modelos.vm import Disco, Firmware
from proxlaunch.nucleo.servicios.creacion import ServicioCreacion

from .apoyo_api import (
    RUTA_CONFIG,
    RUTA_CREAR,
    RUTA_ESTADO,
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


def _servicio(transporte, reloj, **opciones):
    return ServicioCreacion(crear_sesion(transporte, reloj=reloj), reloj, **opciones)


def _falla_con_espacio():
    estado = {"status": "stopped", "exitstatus": EXIT_SIN_ESPACIO}
    return rutas_creacion(TransporteFalso(), estado=estado)


# --- Cancelación durante la espera tolerante a cortes de red -----------------------------


def test_cancelar_durante_la_espera_de_red_previa_al_envio_da_cancelado_sin_upid(
    inv, hacer_cfg, reloj
):
    cancelado = threading.Event()

    def nextid_cae_y_se_cancela(_llamada):
        cancelado.set()
        raise RED_CAIDA

    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    t.en("GET", "/cluster/nextid", nextid_cae_y_se_cancela)
    resultado = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert resultado.error is None
    assert resultado.upid is None
    assert t.llamadas_a("POST", RUTA_CREAR) == []


def test_cancelar_durante_la_confirmacion_con_red_caida_da_cancelado_con_upid(
    inv, hacer_cfg, reloj
):
    cancelado = threading.Event()

    def config_cae_y_se_cancela(_llamada):
        cancelado.set()
        raise RED_CAIDA

    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    t.en("GET", RUTA_CONFIG, config_cae_y_se_cancela)
    resultado = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert resultado.upid == UPID
    assert resultado.error is None


def test_cancelar_antes_de_empezar_no_envia_nada(inv, hacer_cfg, reloj):
    cancelado = threading.Event()
    cancelado.set()
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    resultado = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert t.llamadas_a("POST", RUTA_CREAR) == []


def test_cancelar_en_seguir_durante_red_caida_da_cancelado_con_upid(hacer_cfg, reloj):
    cancelado = threading.Event()

    def config_cae_y_se_cancela(_llamada):
        cancelado.set()
        raise RED_CAIDA

    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    t.en("GET", RUTA_CONFIG, config_cae_y_se_cancela)
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert resultado.upid == UPID
    assert resultado.error is None


# --- SIN_ESPACIO: ids de storage -----------------------------------------------------------


def test_sin_espacio_lista_los_storages_de_los_discos_sin_duplicados(inv, hacer_cfg, reloj):
    cfg = hacer_cfg(discos=[Disco("local-lvm", 32), Disco("nfs1", 10), Disco("local-lvm", 5)])
    resultado = _servicio(_falla_con_espacio(), reloj).crear(
        cfg, inv, lambda e: None, threading.Event()
    )
    assert resultado.error.codigo == CodigoError.SIN_ESPACIO
    assert resultado.error.params["storage"] == "local-lvm,nfs1"
    assert resultado.error.params["vg"] == "pve"


def test_sin_espacio_con_ovmf_incluye_el_storage_del_efidisk(inv, hacer_cfg, reloj):
    cfg = hacer_cfg(discos=[Disco("local-lvm", 32)], firmware=Firmware.OVMF, storage_efi="zfs1")
    resultado = _servicio(_falla_con_espacio(), reloj).crear(
        cfg, inv, lambda e: None, threading.Event()
    )
    assert resultado.error.params["storage"] == "local-lvm,zfs1"
    assert resultado.error.params["vg"] == "pve"


def test_sin_espacio_con_ovmf_y_efidisk_en_el_mismo_storage_no_duplica(inv, hacer_cfg, reloj):
    cfg = hacer_cfg(
        discos=[Disco("local-lvm", 32)], firmware=Firmware.OVMF, storage_efi="local-lvm"
    )
    resultado = _servicio(_falla_con_espacio(), reloj).crear(
        cfg, inv, lambda e: None, threading.Event()
    )
    assert resultado.error.params["storage"] == "local-lvm"


def test_sin_espacio_con_seabios_ignora_el_storage_efi(inv, hacer_cfg, reloj):
    cfg = hacer_cfg(discos=[Disco("local-lvm", 32)], firmware=Firmware.SEABIOS, storage_efi="zfs1")
    resultado = _servicio(_falla_con_espacio(), reloj).crear(
        cfg, inv, lambda e: None, threading.Event()
    )
    assert resultado.error.params["storage"] == "local-lvm"


def test_sin_espacio_tambien_se_ajusta_en_seguir(hacer_cfg, reloj):
    cfg = hacer_cfg(discos=[Disco("local-lvm", 32), Disco("nfs1", 10)])
    resultado = _servicio(_falla_con_espacio(), reloj).seguir(cfg, UPID, threading.Event())
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.params["storage"] == "local-lvm,nfs1"
    assert resultado.error.params["vg"] == "pve"


# --- seguir ------------------------------------------------------------------------------


def test_seguir_tarea_ok_confirma_y_notifica_etapas(hacer_cfg, reloj):
    t = rutas_creacion(
        TransporteFalso(),
        estado=Secuencia(estado_tarea("running"), estado_tarea("ok")),
        config=CONFIG,
    )
    etapas = []
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, threading.Event(), etapas.append)
    assert resultado.desenlace == Desenlace.OK
    assert resultado.upid == UPID
    assert etapas == [Etapa.CREANDO, Etapa.COMPROBANDO, Etapa.LISTO]
    assert t.llamadas_a("POST", RUTA_CREAR) == []


def test_seguir_sin_callback_de_etapas_funciona(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, threading.Event())
    assert resultado.desenlace == Desenlace.OK


def test_seguir_tarea_con_avisos(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("warnings"), config=CONFIG)
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, threading.Event())
    assert resultado.desenlace == Desenlace.CON_AVISOS


def test_seguir_tarea_fallida_es_error(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("error_generico"))
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, threading.Event())
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error is not None


def test_seguir_tarea_que_nunca_termina_agota_el_tiempo(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("running"), config=CONFIG)
    resultado = _servicio(t, reloj, max_espera_s=30.0).seguir(hacer_cfg(), UPID, threading.Event())
    assert resultado.desenlace == Desenlace.TIEMPO_AGOTADO
    assert resultado.error.codigo == CodigoError.TAREA_TIEMPO_AGOTADO
    assert resultado.upid == UPID
    assert reloj.ahora() >= 30.0


def test_seguir_con_red_caida_mas_de_la_tolerancia_es_conexion_perdida(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=RED_CAIDA)
    resultado = _servicio(t, reloj, tolerancia_red_s=10.0).seguir(
        hacer_cfg(), UPID, threading.Event()
    )
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert resultado.upid == UPID
    assert resultado.error.codigo == CodigoError.SERVIDOR_NO_RESPONDE


def test_seguir_cancelado_desde_el_inicio(hacer_cfg, reloj):
    cancelado = threading.Event()
    cancelado.set()
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("running"), config=CONFIG)
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, cancelado)
    assert resultado.desenlace == Desenlace.CANCELADO
    assert resultado.upid == UPID
    assert resultado.error is None


def test_seguir_ok_pero_vm_inexistente_es_error(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"))  # config inexistente
    resultado = _servicio(t, reloj).seguir(hacer_cfg(), UPID, threading.Event())
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.RECURSO_INEXISTENTE


# --- comprobar_ahora ---------------------------------------------------------------------


def test_comprobar_ahora_con_tarea_en_curso_hace_una_sola_consulta(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("running"), config=CONFIG)
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.TIEMPO_AGOTADO
    assert resultado.error.codigo == CodigoError.TAREA_TIEMPO_AGOTADO
    assert resultado.upid == UPID
    assert len(t.llamadas) == 1
    assert reloj.ahora() == 0.0  # sin esperas


def test_comprobar_ahora_con_fallo_de_red_es_conexion_perdida(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=RED_CAIDA)
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert resultado.upid == UPID
    assert len(t.llamadas_a("GET", RUTA_ESTADO)) == 1


def test_comprobar_ahora_con_tarea_ok_confirma_la_configuracion(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.OK
    assert len(t.llamadas_a("GET", RUTA_CONFIG)) == 1


def test_comprobar_ahora_con_tarea_ok_y_vm_inexistente_es_error(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"))
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.RECURSO_INEXISTENTE


def test_comprobar_ahora_con_avisos(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("warnings"), config=CONFIG)
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.CON_AVISOS


def test_comprobar_ahora_con_tarea_fallida_es_error(hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("error_generico"))
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.ERROR


def test_comprobar_ahora_con_error_que_no_es_de_red_es_error(hacer_cfg, reloj):
    prohibido = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    t = rutas_creacion(TransporteFalso(), estado=prohibido)
    resultado = _servicio(t, reloj).comprobar_ahora(hacer_cfg(), UPID)
    assert resultado.desenlace == Desenlace.ERROR
    assert resultado.error.codigo == CodigoError.PERMISO_INSUFICIENTE


# --- al_enviar ---------------------------------------------------------------------------


def test_al_enviar_se_llama_una_vez_con_el_upid_tras_el_post_y_antes_del_sondeo(
    inv, hacer_cfg, reloj
):
    t = rutas_creacion(
        TransporteFalso(),
        estado=Secuencia(estado_tarea("running"), estado_tarea("running"), estado_tarea("ok")),
        config=CONFIG,
    )
    recibidos = []

    def al_enviar(upid):
        # En este punto aún no hubo ninguna consulta de estado.
        recibidos.append(
            (upid, len(t.llamadas_a("GET", RUTA_ESTADO)), len(t.llamadas_a("POST", RUTA_CREAR)))
        )

    resultado = _servicio(t, reloj).crear(
        hacer_cfg(), inv, lambda e: None, threading.Event(), al_enviar=al_enviar
    )
    assert resultado.desenlace == Desenlace.OK
    assert recibidos == [(UPID, 0, 1)]


def test_al_enviar_no_se_llama_si_el_post_falla(inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG, crear=RED_CAIDA)
    llamadas = []
    resultado = _servicio(t, reloj).crear(
        hacer_cfg(), inv, lambda e: None, threading.Event(), al_enviar=llamadas.append
    )
    assert resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert llamadas == []


def test_al_enviar_no_se_llama_si_la_validacion_falla(inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    llamadas = []
    resultado = _servicio(t, reloj).crear(
        hacer_cfg(nombre=""), inv, lambda e: None, threading.Event(), al_enviar=llamadas.append
    )
    assert resultado.desenlace == Desenlace.ERROR
    assert llamadas == []


def test_crear_sin_al_enviar_sigue_funcionando(inv, hacer_cfg, reloj):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    resultado = _servicio(t, reloj).crear(hacer_cfg(), inv, lambda e: None, threading.Event())
    assert resultado.desenlace == Desenlace.OK


@pytest.mark.parametrize("etapa", [Etapa.CREANDO])
def test_al_enviar_ocurre_antes_de_la_etapa_creando(inv, hacer_cfg, reloj, etapa):
    t = rutas_creacion(TransporteFalso(), estado=estado_tarea("ok"), config=CONFIG)
    orden = []
    _servicio(t, reloj).crear(
        hacer_cfg(),
        inv,
        lambda e: orden.append(("etapa", e)),
        threading.Event(),
        al_enviar=lambda upid: orden.append(("enviado", upid)),
    )
    assert orden.index(("enviado", UPID)) < orden.index(("etapa", etapa))
