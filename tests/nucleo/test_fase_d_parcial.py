"""D0.7 y D3.8 (0.9.0): fallo a mitad del hardware del clúster, reintento y errores explicados.

CA-D0.7.1–2, CA-D3.8.1–5, CA-D3.5.4, CA-D0.3.2. Un fallo posterior a la creación o al clonado (el
``PUT`` de hardware con un 403) deja la MV creada, ``PARCIAL``, sin encender, y el resto del lote
sigue. «Reintentar ajustes» repite solo lo pendiente y es idempotente. Los textos de arranque
fallido se traducen sobre el texto saneado del servidor; nunca aparece un secreto.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.errores import traducir_error_hardware
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.servicios.creacion import AJUSTE_HARDWARE, hardware_de_clon

from .apoyo_fase_b_p1 import PRIVS_B_92, fallar_put
from .apoyo_fase_d import MundoD, cfg_arm, hw, pci, usb
from .apoyo_lote import error_http, mapeo_api
from .apoyo_mvp4 import cfg_clon

CENTINELA = "PVEAPIToken=ana@pve!lab=SECRETO-DE-PRUEBA-123"
RUTA = "/mapping/pci/gpu-a2"


def _403(ruta: str = RUTA, priv: str = "Mapping.Use") -> ErrorProxLaunch:
    return error_http(403, f"Permission check failed ({ruta}, {priv})")


def _mundo(n_dispositivos: int = 4, **kw: Any) -> MundoD:
    m = MundoD(privilegios=(*PRIVS_B_92, "Mapping.Use", "Mapping.Audit"), **kw)
    m.cl.mapeos_api["pci"] = [
        mapeo_api("gpu-a2", *[("pve1", f"/dev/{i}") for i in range(n_dispositivos)], migrable=True)
    ]
    return m


def _lote(m: MundoD, n: int = 3, **kw: Any):
    kw.setdefault("hardware_cluster", hw(pci("gpu-a2")))
    kw.setdefault("encender", True)
    plan, libro = m.lote(n, **kw)
    return plan, libro


# --- CA-D0.7.1: un 403 en el PUT de hardware ------------------------------------------------------


def test_ca_d0_7_1_un_403_en_el_put_de_hardware_deja_la_mv_parcial_sin_encender_y_el_lote_sigue():
    m = _mundo()
    fallar_put(m.cl, "hostpci0", _403(), vmid=100)
    plan, libro = _lote(m)
    estados = m.estados(libro)
    assert estados[100] == EstadoMV.PARCIAL
    assert estados[101] in (EstadoMV.OK, EstadoMV.CON_AVISOS)
    assert estados[102] in (EstadoMV.OK, EstadoMV.CON_AVISOS)
    assert m.cl.inicios.get(100, 0) == 0  # no se emite status/start para la MV parcial
    assert m.cl.inicios.get(101, 0) == 1 and m.cl.inicios.get(102, 0) == 1
    assert 100 in m.cl.vms and m.cl.deletes[100] == 0  # nunca se borra sola


def test_ca_d0_7_1_el_error_de_la_mv_parcial_nombra_el_privilegio_la_ruta_y_el_paso():
    m = _mundo()
    fallar_put(m.cl, "hostpci0", _403(), vmid=100)
    _, libro = _lote(m, 2)
    (entrada,) = [e for e in libro.instantanea() if e.elemento.vmid == 100]
    err = entrada.error
    assert err.codigo == CodigoError.PERMISO_INSUFICIENTE  # un 403 conserva su código (E-O20)
    assert err.params["ajuste"] == "hardware"
    assert err.params["privilegio"] == "Mapping.Use" and err.params["ruta"] == RUTA
    assert "ajuste_pendiente:hardware" in entrada.avisos


def test_ca_d0_7_1_el_403_de_mapeo_no_pausa_el_lote_porque_el_ajuste_hardware_es_sin_pausa():
    from proxlaunch.nucleo.lote.politica_pausa import AJUSTES_SIN_PAUSA

    assert "hardware" in AJUSTES_SIN_PAUSA
    m = _mundo()
    fallar_put(m.cl, "hostpci0", _403())  # falla en todas las MVs
    _, libro = _lote(m, 3)
    assert set(m.estados(libro).values()) == {EstadoMV.PARCIAL}
    assert m.cl.inicios == {}


def test_ca_d0_7_1_un_error_500_del_put_de_hardware_tambien_es_parcial_con_el_paso_y_el_texto():
    m = _mundo()
    fallar_put(m.cl, "hostpci0", error_http(500, "texto de Proxmox"), vmid=100)
    _, libro = _lote(m, 2)
    (e,) = [x for x in libro.instantanea() if x.elemento.vmid == 100]
    assert e.estado == EstadoMV.PARCIAL and e.error.params["ajuste"] == "hardware"
    assert e.error.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO
    assert "texto de Proxmox" in (e.error.detalle_tecnico or "")


# --- CA-D0.7.2: reintentar ------------------------------------------------------------------------


def test_ca_d0_7_2_reintentar_ajustes_repite_solo_el_put_de_hardware_pendiente():
    m = _mundo()
    regla = fallar_put(m.cl, "hostpci0", _403(), veces=1)
    cfg, _ = _resolver(m)
    r1 = m.crear(cfg)
    assert r1.desenlace == Desenlace.PARCIAL and "ajuste_pendiente:hardware" in r1.avisos
    antes = len(m.cl.llamadas)
    r2 = m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    nuevas = m.cl.llamadas[antes:]
    escrituras = [(c.metodo, c.ruta) for c in nuevas if c.metodo != "GET"]
    assert escrituras == [("PUT", "/nodes/pve1/qemu/100/config")]  # un único PUT: el pendiente
    assert any(k.startswith("hostpci") for c in nuevas for k in (c.datos or {}))
    assert r2.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS), r2.error
    assert m.cl.vms[100]["config"]["hostpci0"] == "mapping=gpu-a2"
    assert regla.disparos >= 1 and m.cl.clones == {100: 1}  # no se vuelve a clonar


def _resolver(m: MundoD, dispositivo: str = "gpu-a2", **kw: Any):
    from proxlaunch.nucleo.origen.resolucion import resolver_origen

    kw.setdefault("etiquetas", ("proxlaunch", "lote-ab12cd34"))
    base = dataclasses.replace(cfg_clon("base", **kw), hardware_cluster=hw(pci(dispositivo)))
    return resolver_origen(base, m.inv, "pve1")


def test_ca_d0_7_2_si_el_put_llego_pero_la_respuesta_se_perdio_no_se_asigna_dos_veces():
    """Idempotencia: el ``mapping=<id>`` ya asignado en la config se reconoce y se omite."""
    m = _mundo()
    cfg, _ = _resolver(m)
    from .apoyo_lote import NORMAL

    def aplica_y_pierde(ll: Any) -> Any:
        if not any(k.startswith("hostpci") for k in (ll.datos or {})):
            return NORMAL
        m.cl.vms[100]["config"].update(ll.datos)  # el servidor SÍ lo aplicó…
        raise ErrorProxLaunch(
            CodigoError.SERVIDOR_NO_RESPONDE, {}, "respuesta perdida"
        )  # …no llegó

    m.cl.regla("PUT", r"/qemu/100/config$", aplica_y_pierde, veces=1)
    m.crear(cfg)
    config = m.cl.vms[100]["config"]
    assert [k for k in config if k.startswith("hostpci")] == ["hostpci0"]  # una sola asignación
    antes = len(m.cl.llamadas)
    m.reintentar(cfg, pendientes=frozenset({AJUSTE_HARDWARE}))
    puts = [c for c in m.cl.llamadas[antes:] if c.metodo == "PUT"]
    assert not any(k.startswith("hostpci") for c in puts for k in (c.datos or {}))
    assert [k for k in config if k.startswith("hostpci")] == ["hostpci0"]


def test_ca_d0_7_2_reintentar_con_otra_lista_de_pendientes_no_toca_el_hardware():
    m = _mundo()
    cfg, _ = _resolver(m)
    m.crear(cfg)
    antes = len(m.cl.llamadas)
    m.reintentar(cfg, pendientes=frozenset({"etiquetas"}))
    nuevos = [c for c in m.cl.llamadas[antes:] if c.metodo == "PUT"]
    assert not any(k.startswith("hostpci") for c in nuevos for k in (c.datos or {}))


# --- Sin índices libres ---------------------------------------------------------------------------


def _plantilla_llena() -> dict[str, str]:
    return {f"hostpci{i}": f"mapping=ocupado{i}" for i in range(16)}


def test_el_paso_hardware_sin_indices_libres_en_la_plantilla_deja_la_mv_parcial_sin_encender():
    m = _mundo(extra=_plantilla_llena())
    cfg, _ = _resolver(m, encender=True)
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO
    assert (
        r.error.params["ajuste"] == "hardware" and r.error.params["causa"] == "sin_indices_libres"
    )
    assert "ajuste_pendiente:hardware" in r.avisos and "encendido_omitido" in r.avisos
    assert m.cl.inicios == {}
    assert not [c for c in m.cl.llamadas if c.metodo == "PUT" and "hostpci16" in (c.datos or {})]


def test_hardware_de_clon_con_id_o_indices_invalidos_lanza_el_error_de_ajuste():
    from proxlaunch.nucleo.origen.clon import detalle_de_config

    det = detalle_de_config(_plantilla_llena())
    cfg = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(pci("g")))
    with pytest.raises(ErrorProxLaunch) as e:
        hardware_de_clon(cfg, det)
    assert e.value.codigo == CodigoError.AJUSTE_POST_CLON_FALLIDO
    assert (
        e.value.params["ajuste"] == "hardware" and e.value.params["causa"] == "sin_indices_libres"
    )
    malo = dataclasses.replace(cfg_clon("base"), hardware_cluster=hw(pci("a;b")))
    with pytest.raises(ErrorProxLaunch) as e2:
        hardware_de_clon(malo, detalle_de_config({}))
    assert e2.value.params["causa"] == "mapeo_invalido"
    assert hardware_de_clon(cfg_clon("base"), det) == {}


# --- CA-D3.8: errores del servidor explicados -----------------------------------------------------


def test_ca_d3_8_1_un_403_con_la_ruta_del_mapeo_nombra_mapping_use_la_ruta_y_el_mapeo():
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("gpu-a2")))
    e = traducir_error_hardware(_403(), cfg)
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.params["privilegio"] == "Mapping.Use" and e.params["ruta"] == RUTA
    assert e.params["mapeo"] == "gpu-a2" and e.params["tipo"] == "pci"
    assert CENTINELA not in str(e.params) + (e.detalle_tecnico or "")


def test_ca_d3_8_1_tambien_para_un_mapeo_usb():
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(usb("llave-hasp")))
    e = traducir_error_hardware(_403("/mapping/usb/llave-hasp"), cfg)
    assert e.params["mapeo"] == "llave-hasp" and e.params["tipo"] == "usb"
    assert e.params["ruta"] == "/mapping/usb/llave-hasp"


@pytest.mark.parametrize(
    ("ruta", "priv", "version"),
    [("/nodes", "Sys.Audit", "8.4"), ("/mapping/cpu/gamer", "Mapping.Use", "9.2")],
)
def test_ca_d3_8_2_el_403_de_cpu_personalizada_nombra_el_privilegio_y_la_ruta_de_cada_version(
    ruta, priv, version
):
    cfg = dataclasses.replace(cfg_arm(), tipo_cpu="custom-gamer")
    e = traducir_error_hardware(_403(ruta, priv), cfg)
    assert e.codigo == CodigoError.CPU_PERSONALIZADA_RECHAZADA, version
    assert e.params["privilegio"] == priv and e.params["ruta"] == ruta
    assert e.params["cpu"] == "custom-gamer"


def test_ca_d3_8_2_un_403_de_nodes_sin_cpu_personalizada_no_se_reinterpreta():
    original = _403("/nodes", "Sys.Audit")
    cfg = dataclasses.replace(cfg_arm(), tipo_cpu="host")
    assert traducir_error_hardware(original, cfg) is original


MENSAJES = [
    ("PCI device mapping not found for 'gpu-a2'", "sin_dispositivo", "gpu-a2"),
    ("PCI device mapping invalid (hardware probably changed)", "hardware_cambiado", "gpu-a2"),
    ("USB Mapping invalid (hardware probably changed)", "hardware_cambiado", "gpu-a2"),
    ("q35 machine model is not enabled", "necesita_q35", "gpu-a2"),
    ("More than one USB mapping per host not supported", "usb_en_uso", "gpu-a2"),
]


@pytest.mark.parametrize(("mensaje", "motivo", "mapeo"), MENSAJES)
def test_ca_d3_8_3_cada_mensaje_de_arranque_reconocido_da_su_motivo_y_conserva_el_original(
    mensaje, motivo, mapeo
):
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("gpu-a2")))
    origen = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, mensaje)
    e = traducir_error_hardware(origen, cfg)
    assert e.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert e.params["motivo"] == motivo and e.params["mapeo"] == mapeo
    assert e.detalle_tecnico == mensaje  # el texto original va saneado junto a la explicación


def test_ca_d3_8_3_un_mensaje_desconocido_no_se_traduce():
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("gpu-a2")))
    origen = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "algo que no conocemos")
    assert traducir_error_hardware(origen, cfg) is origen


def test_ca_d3_8_3_con_varios_mapeos_no_se_adivina_cual_es_y_el_nombre_queda_vacio():
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("a"), usb("b")))
    e = traducir_error_hardware(
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "q35 machine model is not enabled"), cfg
    )
    assert e.params["mapeo"] == "" and e.params["motivo"] == "necesita_q35"


def test_ca_d3_8_3_un_id_hostil_en_el_mensaje_no_pasa_como_nombre_de_mapeo():
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("gpu-a2")))
    mal = ErrorProxLaunch(
        CodigoError.DESCONOCIDO, {}, "PCI device mapping not found for '<b>x</b>;y'"
    )
    e = traducir_error_hardware(mal, cfg)
    assert e.params["mapeo"] == "gpu-a2"  # el id del texto no es válido: se usa el único de la MV
    assert "<" not in e.params["mapeo"]


@pytest.mark.parametrize(("mensaje", "motivo", "_m"), MENSAJES)
def test_ca_d3_8_3_el_arranque_fallido_en_el_servicio_deja_con_avisos_y_no_es_un_error_del_lote(
    mensaje, motivo, _m
):
    m2 = _mundo()
    cfg2, _ = _resolver(m2, encender=True)
    m2.cl.exitstatus_inicio[100] = mensaje
    r = m2.crear(cfg2)
    assert r.desenlace == Desenlace.CON_AVISOS and "encendido_fallido" in r.avisos
    assert r.error is not None and r.error.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert r.error.params["motivo"] == motivo
    assert m2.cl.vms[100]["status"] != "running"


def test_ca_d3_8_4_un_500_de_5000_caracteres_o_con_html_se_acota_y_se_sanea_en_el_error():
    m = _mundo()
    sucio = "<script>alert(1)</script>\n" + "x" * 5000
    fallar_put(m.cl, "hostpci0", error_http(500, sucio), vmid=100)
    _, libro = _lote(m, 1, encender=False)
    (e,) = libro.instantanea()
    assert e.estado == EstadoMV.PARCIAL
    for texto in (str(e.error.params), *e.log_tarea):
        assert "<script>" not in texto and len(texto) < 4000
    assert len(e.error.detalle_tecnico or "") < 6000  # acotado por el traductor, no ilimitado


def test_ca_d3_8_5_un_mensaje_de_proxmox_con_el_token_no_llega_al_informe_ni_a_los_params():
    from proxlaunch.nucleo.lote.informe import MetadatosInforme, construir_informe

    m = _mundo()
    secreto = "ana@pve!lab=SECRETO-DE-PRUEBA-123"
    fallar_put(
        m.cl, "hostpci0", error_http(500, f"fallo; Authorization: PVEAPIToken={secreto}"), vmid=100
    )
    plan, libro = _lote(m, 1, encender=False)
    meta = MetadatosInforme("lab", "9.2.1", False, None, "2026-11-23T10:00:00+00:00")
    informe = construir_informe(plan, libro, meta, reloj=m.reloj, ocultar=("ana@pve!lab",))
    volcado = repr(libro.instantanea()) + repr(informe)
    assert "SECRETO-DE-PRUEBA-123" not in volcado


def test_ca_d3_5_4_el_403_al_clonar_con_la_ruta_del_mapeo_nombra_mapping_use():
    """Un mapeo nuevo sin ``Mapping.Use`` en una plantilla con otro mapeo: el PUT falla."""
    m = _mundo(extra={"hostpci0": "mapping=gpu-a2"})
    fallar_put(m.cl, "hostpci1", _403("/mapping/pci/gpu-b1"), veces=1)
    cfg, _ = _resolver(m, "gpu-b1")
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert r.error.params["privilegio"] == "Mapping.Use"
    assert (
        r.error.params["ruta"] == "/mapping/pci/gpu-b1" and r.error.params["ajuste"] == "hardware"
    )
