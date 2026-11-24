"""CA-D11.1, CA-D11.2 y casos límite CL-D de la fase D (0.9.0): ARM, hardware y versión.

Una prueba por V-D (V-D01 a V-D09, V-D50 a V-D64 y V-D70; las V-D20 a V-D41 de libvirt las prueba
``test_fase_d_libvirt_*``): provoca la regla con el código real y comprueba su severidad, los
params (nodo, mapeo, fila, columna) y que ningún valor del servidor llega sin sanear. Después, los
casos límite CL-D1 a CL-D24 que no están ya cubiertos por el resto de archivos de la fase.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from proxlaunch.nucleo.arquitectura.deteccion import forzar
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.arquitectura.validacion import (
    avisos_arquitectura,
    validar_arquitectura,
    validar_mezcla,
)
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.validacion import (
    validar_hardware_local,
    validar_hardware_servidor,
    validar_plantilla_hardware,
)
from proxlaunch.nucleo.lote.modelos import Severidad as SevLote
from proxlaunch.nucleo.modelos.catalogo import DetallePlantilla
from proxlaunch.nucleo.modelos.vm import Bus, Disco, Firmware
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.persistencia.preferencias import RepositorioPreferencias
from proxlaunch.nucleo.servicios.conexion import CodigoAviso
from proxlaunch.nucleo.servicios.descubrimiento import descubrir
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_api import TransporteFalso, crear_sesion, rutas_inventario
from .apoyo_fase_a import cfg_vm, def_lote, plan_de
from .apoyo_fase_d import (
    ARM,
    DESC,
    V_84,
    V_92,
    X86,
    banco_d,
    caps_de,
    cfg_arm,
    con_hardware,
    info_hw,
    inv_arq,
    mapeo,
    pci,
    permisos_mapeo,
    usb,
)
from .apoyo_lote import mapeo_api
from .apoyo_mvp3 import perfil_base, perfiles_fabrica, tabla_csv

HOSTIL = "<img src=x onerror=1>\n\x00\x1b[31m"


def _como_lista(r: Any) -> list[tuple[str, str, dict[str, str]]]:
    """Normaliza problemas de M1 (``codigo``) y del lote (``regla``): ``(código, sev., params)``."""
    salida = []
    for p in r:
        codigo = getattr(p, "codigo", None) or p.regla
        sev = p.severidad.value
        salida.append((codigo, sev, dict(p.params)))
    return salida


def _una(r: Any, codigo: str, severidad: str) -> dict[str, str]:
    hallados = [(c, s, p) for c, s, p in _como_lista(r) if c == codigo]
    assert hallados, (codigo, _como_lista(r))
    assert all(s == severidad for _, s, _ in hallados), hallados
    return hallados[0][2]


def _sin_sucio(params: dict[str, str]) -> None:
    for v in params.values():
        assert not any(c in v for c in "<>\x00\x1b\n"), params


# --- V-D01 a V-D07 --------------------------------------------------------------------------------


class _Llavero:
    def set_password(self, *a: Any) -> None: ...

    def get_password(self, *a: Any) -> None:
        return None

    def delete_password(self, *a: Any) -> None: ...


def _conectar(tmp_path, version: str):
    from proxlaunch.nucleo.api.transporte import crear_transporte_http
    from proxlaunch.nucleo.modelos.conexion import CredencialToken
    from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
    from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
    from proxlaunch.nucleo.reloj import RelojSimulado
    from proxlaunch.nucleo.servicios.conexion import ServicioConexion

    from .apoyo_api import HUELLA_A, TOKEN_ID, TOKEN_SECRETO, perfil_basico

    huellas = RepositorioHuellas(tmp_path / "h.json")
    huellas.guardar("10.0.0.1", 8006, HUELLA_A)
    srv = ServicioConexion(
        crear_transporte_http, huellas, AlmacenSecretos(backend=_Llavero()), RelojSimulado()
    )
    t = TransporteFalso().en("GET", "/version", {"version": version})
    srv._fabrica = lambda perfil, h: t
    return srv.conectar(perfil_basico(), CredencialToken(TOKEN_ID, TOKEN_SECRETO))


def test_v_d01_servidor_8_3_es_error_de_conexion_con_version_y_minima(tmp_path):
    with pytest.raises(ErrorProxLaunch) as e:
        _conectar(tmp_path, "8.3.2")
    assert e.value.codigo == CodigoError.VERSION_NO_SOPORTADA
    assert e.value.params == {"version": "8.3.2", "minima": "8.4"}


def test_v_d02_rama_8_es_aviso_con_la_version_detectada(tmp_path):
    sesion = _conectar(tmp_path, "8.4.1")
    (aviso,) = [a for a in sesion.avisos if a.codigo == CodigoAviso.RAMA_8_SIN_SOPORTE]
    assert aviso.params == {"version": "8.4.1"}


def test_v_d03_version_forzada_anterior_a_8_4_es_aviso_de_preferencias(tmp_path):
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps({"version_esquema": 1, "version_forzada": "8.0"}), encoding="utf-8")
    repo = RepositorioPreferencias(ruta)
    repo.cargar()
    assert repo.version_forzada_descartada == "8.0"


def test_v_d04_arquitectura_no_legible_es_aviso_con_nodo_y_motivo():
    inv = inv_arq({"pve1": DESC}, nodos=("pve1",))
    p = _una(avisos_arquitectura(inv, ["pve1"], caps_de(V_92)), "V-D04", "aviso")
    assert p == {"nodo": "pve1", "motivo": "sin_permiso"}


def test_v_d05_nodo_arm64_es_aviso_una_vez_por_nodo_con_la_variante_de_version():
    inv = inv_arq({"pve1": ARM, "pve2": ARM}, nodos=("pve1", "pve2"))
    r = avisos_arquitectura(inv, ["pve1", "pve2", "pve1"], caps_de(V_84))
    assert [p.params["nodo"] for p in r] == ["pve1", "pve2"]
    assert _una(r, "V-D05", "aviso")["variante"] == "previa"


def test_v_d06_lote_con_arquitecturas_mezcladas_es_error_con_los_nodos_de_cada_tipo():
    inv = inv_arq({"pve1": X86, "pve-arm": ARM}, nodos=("pve1", "pve-arm"))
    r = validar_mezcla({0: "pve1", 1: "pve-arm"}, inv)
    p = _una(r, "V-D06", "error")
    assert p["nodos_x86"] == "pve1" and p["nodos_arm"] == "pve-arm" and p["nodo"] == "pve-arm"


def test_v_d07_plantilla_de_otra_arquitectura_es_error_agrupado_por_plantilla_en_100_filas():
    from proxlaunch.nucleo.lote.modelos import ModoDestino

    from .apoyo_fase_d import MundoD
    from .apoyo_mvp4 import cfg_clon

    m = MundoD(
        nodos=("pve1", "pve-arm"),
        arqs={"pve1": X86, "pve-arm": ARM},
        extra={"scsi0": "nfs1:base-9000-disk-0,size=8G"},
    )
    plan = plan_de(
        m.banco,
        def_lote(
            100, plantilla_vm=cfg_clon("base"), modo=ModoDestino.NODOS_ELEGIDOS, nodos=("pve-arm",)
        ),
    )
    motivos = [p for p in plan.problemas if p.params.get("motivo") == "arquitectura_plantilla"]
    assert len(motivos) == 1  # CA-D11.2: una por plantilla, no una por MV
    assert motivos[0].severidad == SevLote.ERROR and motivos[0].params["plantilla"] == "base"


# --- V-D08 y V-D09 --------------------------------------------------------------------------------


def test_v_d08_valores_x86_adaptados_a_arm_son_aviso_con_la_lista_de_cambios():
    banco = banco_d({"pve1": ARM})
    cfg = cfg_arm(firmware=Firmware.SEABIOS, discos=[Disco("local-lvm", 8, bus=Bus.SATA)])
    plan = plan_de(banco, def_lote(1, plantilla_vm=cfg))
    p = _una(plan.problemas, "V-D08", "aviso")
    assert p["lista"] == "firmware, discos[0].bus, tipo_cpu" and p["nodo"] == "pve1"
    assert "firmware:seabios>ovmf" in p["cambios"]


def test_v_d09_opcion_inexistente_en_arm_es_error_con_opcion_motivo_y_alternativa():
    cfg = cfg_arm(firmware=Firmware.SEABIOS)
    p = _una(validar_arquitectura(cfg, inv_arq({"pve1": ARM}, nodos=("pve1",))), "V-D09", "error")
    assert (p["opcion"], p["motivo"], p["alternativa"]) == ("seabios", "firmware_uefi", "ovmf")


# --- V-D50 a V-D64 --------------------------------------------------------------------------------


def _cfgs(n: int, *disp: Any, nodo: str = "pve1", **kw: Any) -> dict[str, list]:
    return {nodo: [con_hardware(cfg_vm(**kw), *disp) for _ in range(n)]}


def test_v_d50_sin_mapeos_visibles_es_aviso():
    p = _una(validar_hardware_servidor(_cfgs(1, pci("g")), info_hw(), None), "V-D50", "aviso")
    assert p["motivo"] == "sin_mapeos"


def test_v_d51_mapeo_inexistente_es_error_con_el_mapeo():
    r = validar_hardware_servidor(_cfgs(1, pci("g")), info_hw(mapeo("pci", "otro", "pve1")), None)
    assert _una(r, "V-D51", "error")["mapeo"] == "g"


def test_v_d52_mapeo_sin_dispositivo_en_un_nodo_es_error_con_los_nodos():
    info = info_hw(mapeo("pci", "g", "pve1"))
    cfgs = {**_cfgs(1, pci("g")), **_cfgs(1, pci("g"), nodo="pve2")}
    assert _una(validar_hardware_servidor(cfgs, info, None), "V-D52", "error")["nodos"] == "pve2"


def test_v_d53_check_node_con_error_es_error_con_el_mensaje_saneado():
    from proxlaunch.nucleo.hardware_cluster.modelos import ComprobacionNodo

    info = info_hw(
        mapeo("pci", "g", "pve1"), comprobaciones=[ComprobacionNodo("g", "pve1", (HOSTIL,))]
    )
    p = _una(validar_hardware_servidor(_cfgs(1, pci("g")), info, None), "V-D53", "error")
    _sin_sucio(p)


def test_v_d54_pcie_fuerza_q35_es_aviso():
    _una(
        validar_hardware_local(
            con_hardware(cfg_vm(), pci("g", pcie=True)), caps_de(V_92), Arquitectura.X86_64
        ),
        "V-D54",
        "aviso",
    )


def test_v_d55_x_vga_sin_pcie_es_error_y_v_d55b_con_pcie_es_aviso():
    r = validar_hardware_local(
        con_hardware(cfg_vm(), pci("g", x_vga=True)), caps_de(V_92), Arquitectura.X86_64
    )
    _una(r, "V-D55", "error")
    r = validar_hardware_local(
        con_hardware(cfg_vm(), pci("g", pcie=True, x_vga=True)), caps_de(V_92), Arquitectura.X86_64
    )
    _una(r, "V-D55b", "aviso")


def test_v_d56_mas_maquinas_que_dispositivos_es_aviso_con_k_y_n():
    r = validar_hardware_servidor(
        _cfgs(5, pci("g")), info_hw(mapeo("pci", "g", "pve1", por_nodo={"pve1": 2})), None
    )
    p = _una(r, "V-D56", "aviso")
    assert (p["k"], p["n"], p["nodo"]) == ("2", "5", "pve1")


def test_v_d57_sin_migracion_en_vivo_es_aviso():
    r = validar_hardware_local(con_hardware(cfg_vm(), usb("u")), caps_de(V_92), Arquitectura.X86_64)
    assert _una(r, "V-D57", "aviso")["mapeos"] == "u"


def test_v_d58_y_v_d58b_plantilla_con_dispositivos_sin_mapear_o_con_mapeos():
    sin_mapa = detalle_de_config({"hostpci0": "0000:01:00.0"})
    _una(validar_plantilla_hardware(sin_mapa, "base"), "V-D58", "error")
    con_mapa = detalle_de_config({"hostpci0": "mapping=g"})
    _una(validar_plantilla_hardware(con_mapa, "base"), "V-D58b", "aviso")
    assert validar_plantilla_hardware(detalle_de_config({}), "base") == []
    assert isinstance(sin_mapa, DetallePlantilla)


def test_v_d59_demasiados_dispositivos_es_error():
    r = validar_hardware_local(
        con_hardware(cfg_vm(), *[usb(f"u{i}") for i in range(6)]),
        caps_de(V_92),
        Arquitectura.X86_64,
    )
    assert _una(r, "V-D59", "error")["maximo"] == "5"


def test_v_d60_driver_keep_antes_de_9_1_es_error_con_la_version():
    r = validar_hardware_local(
        con_hardware(cfg_vm(), pci("g", driver_keep=True)), caps_de(V_84), Arquitectura.X86_64
    )
    assert _una(r, "V-D60", "error")["version"] == "8.4"


def test_v_d61_y_v_d62_cpu_personalizada_inexistente_o_ilegible():
    info = info_hw(cpus={"pve1": ["kvm64"]})
    r = validar_hardware_servidor(_cfgs(1, tipo_cpu="custom-a"), info, None)
    assert _una(r, "V-D61", "error") == {"cpu": "custom-a", "nodos": "pve1"}
    r = validar_hardware_servidor(_cfgs(1, tipo_cpu="custom-a"), None, None)
    assert _una(r, "V-D62", "aviso")["cpu"] == "custom-a"


def test_v_d63_falta_privilegio_es_error_con_privilegio_y_ruta():
    info = info_hw(mapeo("pci", "g", "pve1"))
    r = validar_hardware_servidor(_cfgs(1, pci("g")), info, permisos_mapeo())
    p = _una(r, "V-D63", "error")
    assert p["privilegio"] == "Mapping.Use" and p["ruta"] == "/mapping/pci/g"


def test_v_d64_el_mismo_mapeo_pci_dos_veces_es_error():
    r = validar_hardware_local(
        con_hardware(cfg_vm(), pci("g"), pci("g")), caps_de(V_92), Arquitectura.X86_64
    )
    assert _una(r, "V-D64", "error")["mapeo"] == "g"


def test_v_d70_valor_invalido_en_una_columna_csv_es_error_con_fila_y_columna():
    r = interpretar(
        tabla_csv(["nombre;mapeo_usb", 'a-01;"con espacio"']),
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    (f,) = r.filas
    p = next(x for x in f.problemas if x.regla == "V-D70")
    assert f.numero == 2 and p.columna == "mapeo_usb" and p.severidad == Severidad.ERROR


# --- Nada sin sanear en ningún problema de la matriz ----------------------------------------------


def test_ca_d11_1_ningun_problema_de_la_matriz_lleva_texto_hostil_ni_secretos():
    sucia = "g" + HOSTIL
    info = info_hw(mapeo("pci", "g", "pve1"))
    cfgs = _cfgs(2, pci(sucia), pci("g"), usb("u" + HOSTIL))
    conjuntos = [
        validar_hardware_servidor(cfgs, info, None),
        validar_hardware_local(
            con_hardware(cfg_vm(), pci(sucia)), caps_de(V_92), Arquitectura.X86_64
        ),
    ]
    for r in conjuntos:
        assert r
        for _, _, params in _como_lista(r):
            _sin_sucio(params)


def test_ca_d11_1_los_problemas_no_contienen_tokens_ni_contrasenas_de_la_sesion():
    banco = banco_d({"pve1": ARM}, nodos=("pve1",))
    plan = plan_de(banco, def_lote(2, plantilla_vm=cfg_arm(firmware=Firmware.SEABIOS)))
    texto = json.dumps([dict(p.params) for p in plan.problemas])
    for secreto in ("PVEAPIToken", "SECRETO", "ticket", "csrf", "passwd"):
        assert secreto.lower() not in texto.lower()


# --- Casos límite pendientes ----------------------------------------------------------------------


def test_cl_d5_una_arquitectura_forzada_incorrecta_avisa_v_d05_y_crea_con_valores_arm():
    """Un x86 marcado como ARM: la MV se crea con el perfil ARM (puede no arrancar; documentado)."""
    banco = banco_d({"pve1": X86}, nodos=("pve1",))
    banco.inv = forzar(banco.inv, "pve1", Arquitectura.AARCH64)
    plan = plan_de(banco, def_lote(1, plantilla_vm=cfg_arm()))
    assert not plan.bloqueado
    aviso = _una([p for p in plan.problemas if p.regla == "V-D05"], "V-D05", "aviso")
    assert aviso["forzada"] == "1"
    from proxlaunch.nucleo.constructor_peticion import construir_parametros

    p = construir_parametros(plan.elementos[0].cfg, banco.inv)
    assert p["bios"] == "ovmf" and p["vga"] == "virtio" and "machine" not in p


def test_cl_d24_otro_servidor_con_otra_arquitectura_no_arrastra_nada_de_la_sesion_anterior():
    """Reconectar vacía arquitectura, mapeos y CPU: viven en el inventario de cada sesión."""
    t_arm = TransporteFalso()
    rutas_inventario(t_arm)
    for n in ("pve1", "pve2", "pve3"):
        t_arm.en("GET", f"/nodes/{n}/status", {"current-kernel": {"machine": "aarch64"}})
    inv_a = descubrir(crear_sesion(t_arm, version=V_84))
    t_x86 = TransporteFalso()
    rutas_inventario(t_x86)
    for n in ("pve1", "pve2", "pve3"):
        t_x86.en("GET", f"/nodes/{n}/status", {"current-kernel": {"machine": "x86_64"}})
    inv_b = descubrir(crear_sesion(t_x86, version=V_84))
    assert {a.arquitectura for a in inv_a.arquitecturas.values()} == {Arquitectura.AARCH64}
    assert {a.arquitectura for a in inv_b.arquitecturas.values()} == {Arquitectura.X86_64}
    assert inv_b.catalogo is not None and inv_b.catalogo.hardware is None


def test_cl_d20_cien_maquinas_con_un_usb_de_un_dispositivo_siguen_siendo_creables():
    banco = banco_d({"pve1": X86}, nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["usb"] = [mapeo_api("u", ("pve1", "/u"))]
    plan = plan_de(
        banco,
        def_lote(100, plantilla_vm=con_hardware(cfg_arm(discos=[Disco("local-lvm", 1)]), usb("u"))),
    )
    (p,) = [x for x in plan.problemas if x.regla == "V-D56"]
    assert (p.params["k"], p.params["n"]) == ("1", "100") and not plan.bloqueado
