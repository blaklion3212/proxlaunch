"""D2.5 (0.9.0): detección de la arquitectura de cada nodo (RF-D2.5, RNF-D4, CL-D4, CL-D24).

CA-D2.5.1–8. La detección nunca rompe el descubrimiento: un 403, un nodo caído, campos ausentes
o un error inesperado dejan el nodo en ``desconocida`` (V-D04) y se trata como x86_64. Los textos
de los valores no confiables nunca llegan al inventario.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.arquitectura.deteccion import (
    de_estado_nodo,
    de_lista_cpu,
    detectar,
    detectar_nodo,
    forzar,
    normalizar,
)
from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
    arquitectura_de,
    arquitectura_efectiva,
)
from proxlaunch.nucleo.arquitectura.validacion import avisos_arquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import ModeloCpu
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.descubrimiento import MAX_HILOS, descubrir, descubrir_nodo_d

from .apoyo_api import TransporteFalso, crear_sesion, dato, rutas_inventario
from .apoyo_fase_b_p1 import V_84, V_92
from .apoyo_fase_d import caps_de

NODOS = ("pve1", "pve2", "pve3")
RECURSOS_92 = [
    {"node": "pve1", "type": "node", "host-arch": "x86_64"},
    {"node": "pve2", "type": "node", "host-arch": "aarch64"},
    {"node": "pve3", "type": "node", "host-arch": "x86_64"},
]


def _estado(maquina: str | None, **extra: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"uptime": 1}
    if maquina is not None:
        d["current-kernel"] = {"machine": maquina}
    d.update(extra)
    return d


def _transporte(
    *, version=V_92, recursos: Any = None, estados: dict[str, Any] | None = None, nodos="nodes.json"
) -> TransporteFalso:
    t = TransporteFalso()
    rutas_inventario(t, "9.2", nodos)
    if nodos != "nodes.json":
        t.en("GET", "/cluster/status", dato("9.2", "cluster_status_nodo_offline.json"))
    if recursos is not None:
        t.en("GET", "/cluster/resources", recursos)
    for n in NODOS:
        t.en("GET", f"/nodes/{n}/status", (estados or {}).get(n, _estado("x86_64")))
    return t


def _descubrir(t: TransporteFalso, version=V_92):
    return descubrir(crear_sesion(t, version=version))


def _lecturas(t: TransporteFalso, ruta: str) -> int:
    return len(t.llamadas_a("GET", ruta))


def _cliente(t: TransporteFalso) -> ClienteProxmox:
    return ClienteProxmox(
        t, AutenticadorToken(CredencialToken("ana@pve!lab", "s")), RelojSimulado()
    )


# --- Normalización (valores no confiables) --------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("x86_64", Arquitectura.X86_64),
        ("amd64", Arquitectura.X86_64),
        ("X86_64", Arquitectura.X86_64),
        (" amd64 ", Arquitectura.X86_64),
        ("aarch64", Arquitectura.AARCH64),
        ("arm64", Arquitectura.AARCH64),
        ("ARM64", Arquitectura.AARCH64),
        ("riscv64", Arquitectura.DESCONOCIDA),
        ("ppc64le", Arquitectura.DESCONOCIDA),
        ("s390x", Arquitectura.DESCONOCIDA),
        ("i686", Arquitectura.DESCONOCIDA),
        ("", Arquitectura.DESCONOCIDA),
        (None, Arquitectura.DESCONOCIDA),
        (64, Arquitectura.DESCONOCIDA),
        (["x86_64"], Arquitectura.DESCONOCIDA),
        ({"machine": "aarch64"}, Arquitectura.DESCONOCIDA),
    ],
)
def test_normalizacion_solo_acepta_la_lista_conocida(texto, esperado):
    assert normalizar(texto) == esperado


def test_ca_d2_5_5_un_texto_malicioso_o_largo_es_desconocida():
    for malo in ("riscv64", "<script>alert(1)</script>", "x86_64\n; rm -rf /", "a" * 5000):
        assert normalizar(malo) == Arquitectura.DESCONOCIDA
    texto_control = "aarch64\x00\x1b[31m" + "x" * 3000
    assert normalizar(texto_control) == Arquitectura.DESCONOCIDA


# --- CA-D2.5.1: 9.2 con host-arch -----------------------------------------------------------------


def test_ca_d2_5_1_con_9_2_la_arquitectura_sale_de_host_arch_sin_leer_el_estado_de_los_nodos():
    t = _transporte(recursos=RECURSOS_92)
    inv = _descubrir(t)
    assert {n: a.arquitectura for n, a in inv.arquitecturas.items()} == {
        "pve1": Arquitectura.X86_64,
        "pve2": Arquitectura.AARCH64,
        "pve3": Arquitectura.X86_64,
    }
    assert all(a.fuente == FuenteArquitectura.RECURSOS for a in inv.arquitecturas.values())
    assert [_lecturas(t, f"/nodes/{n}/status") for n in NODOS] == [0, 0, 0]
    assert _lecturas(t, "/cluster/resources") == 1


def test_ca_d2_5_8_el_clúster_de_9_2_añade_a_lo_sumo_una_lectura_en_total():
    t = _transporte(recursos=RECURSOS_92)
    _descubrir(t)
    nuevas = _lecturas(t, "/cluster/resources") + sum(
        _lecturas(t, f"/nodes/{n}/status") for n in NODOS
    )
    assert nuevas <= 1


def test_ca_d2_5_1_si_host_arch_falta_en_un_nodo_solo_ese_nodo_lee_su_estado():
    parcial = [RECURSOS_92[0], {"node": "pve2", "type": "node"}, RECURSOS_92[2]]
    t = _transporte(recursos=parcial, estados={"pve2": _estado("aarch64")})
    inv = _descubrir(t)
    assert inv.arquitecturas["pve2"].arquitectura == Arquitectura.AARCH64
    assert inv.arquitecturas["pve2"].fuente == FuenteArquitectura.KERNEL
    assert inv.arquitecturas["pve1"].fuente == FuenteArquitectura.RECURSOS
    assert [_lecturas(t, f"/nodes/{n}/status") for n in NODOS] == [0, 1, 0]


def test_ca_d2_5_5_un_host_arch_invalido_cae_al_estado_del_nodo_con_motivo_si_tampoco_sirve():
    recursos = [{"node": "pve1", "type": "node", "host-arch": "<script>"}, *RECURSOS_92[1:]]
    t = _transporte(recursos=recursos, estados={"pve1": _estado(None)})
    inv = _descubrir(t)
    info = inv.arquitecturas["pve1"]
    assert info.arquitectura == Arquitectura.DESCONOCIDA and info.motivo == "formato"
    assert "script" not in repr(inv.arquitecturas)


@pytest.mark.parametrize(
    "error",
    [
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "caído"),
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"),
        RuntimeError("raro"),
    ],
    ids=["no_responde", "desconocido", "excepcion_inesperada"],
)
def test_la_lectura_de_resources_que_falla_no_rompe_el_descubrimiento(error):
    """``/cluster/resources`` con error: cae a la lectura por nodo (nunca rompe)."""
    t = _transporte(recursos=error, estados={"pve1": _estado("aarch64")})
    inv = _descubrir(t)
    assert inv.arquitecturas["pve1"].arquitectura == Arquitectura.AARCH64
    assert inv.arquitecturas["pve1"].fuente == FuenteArquitectura.KERNEL
    assert len(inv.topologia.nodos) == 3


# --- CA-D2.5.2 y CA-D2.5.3: 8.4 con current-kernel y kversion -------------------------------------


def test_ca_d2_5_2_con_8_4_se_usa_current_kernel_y_no_se_lee_cluster_resources():
    t = _transporte(
        version=V_84,
        estados={"pve1": _estado("x86_64"), "pve2": _estado("aarch64"), "pve3": _estado("x86_64")},
    )
    inv = _descubrir(t, version=V_84)
    assert {n: a.arquitectura.value for n, a in inv.arquitecturas.items()} == {
        "pve1": "x86_64",
        "pve2": "aarch64",
        "pve3": "x86_64",
    }
    assert all(a.fuente == FuenteArquitectura.KERNEL for a in inv.arquitecturas.values())
    assert _lecturas(t, "/cluster/resources") == 0
    assert [_lecturas(t, f"/nodes/{n}/status") for n in NODOS] == [1, 1, 1]  # ≤ 1 por nodo


def test_ca_d2_5_3_sin_current_kernel_se_usa_kversion():
    estados = {"pve1": _estado(None, kversion="Linux 6.17.2-1-pve #1 SMP PREEMPT_DYNAMIC aarch64")}
    t = _transporte(version=V_84, estados=estados)
    inv = _descubrir(t, version=V_84)
    assert inv.arquitecturas["pve1"].arquitectura == Arquitectura.AARCH64
    assert inv.arquitecturas["pve1"].fuente == FuenteArquitectura.KVERSION


def test_ca_d2_5_3_kversion_con_las_dos_arquitecturas_no_se_decide():
    assert de_estado_nodo({"kversion": "Linux x86_64 aarch64"}) == Arquitectura.DESCONOCIDA


@pytest.mark.parametrize(
    ("estado", "esperado"),
    [
        ({"current-kernel": {"machine": "aarch64"}}, Arquitectura.AARCH64),
        (
            {"current-kernel": {"machine": "x86_64"}, "kversion": "Linux aarch64"},
            Arquitectura.X86_64,
        ),
        (
            {"current-kernel": {"machine": "riscv64"}, "kversion": "Linux arm64"},
            Arquitectura.AARCH64,
        ),
        ({"current-kernel": "aarch64"}, Arquitectura.DESCONOCIDA),
        ({"current-kernel": None, "kversion": None}, Arquitectura.DESCONOCIDA),
        ({"current-kernel": {"machine": 64}}, Arquitectura.DESCONOCIDA),
        ({}, Arquitectura.DESCONOCIDA),
    ],
)
def test_de_estado_nodo_con_formatos_variados(estado, esperado):
    assert de_estado_nodo(estado) == esperado


# --- CA-D2.5.4: sin Sys.Audit ---------------------------------------------------------------------


def _403() -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "Sys.Audit"}, "403")


def test_ca_d2_5_4_un_403_en_el_estado_deja_el_nodo_desconocido_con_motivo_sin_permiso():
    t = _transporte(version=V_84, estados={"pve1": _403()})
    inv = _descubrir(t, version=V_84)
    info = inv.arquitecturas["pve1"]
    assert info == ArquitecturaNodo(
        Arquitectura.DESCONOCIDA, FuenteArquitectura.NINGUNA, "sin_permiso"
    )
    assert arquitectura_efectiva(inv, "pve1") == Arquitectura.X86_64  # se trata como x86
    assert inv.arquitecturas["pve2"].arquitectura == Arquitectura.X86_64  # el resto se detecta
    (aviso,) = [a for a in avisos_arquitectura(inv, ["pve1"], caps_de(V_84)) if a.regla == "V-D04"]
    assert aviso.params == {"nodo": "pve1", "motivo": "sin_permiso"}


def test_ca_d2_5_4_la_heuristica_de_la_lista_de_cpu_solo_aplica_si_la_lista_ya_se_leyo():
    """Desviación documentada (arquitectura §0): la heurística nunca provoca un GET propio."""
    arm = [ModeloCpu("cortex-a53", False), ModeloCpu("host", False), ModeloCpu("max", False)]
    x86 = [ModeloCpu("kvm64", False), ModeloCpu("x86-64-v2-AES", False)]
    assert de_lista_cpu(arm) == Arquitectura.AARCH64
    assert de_lista_cpu(x86) == Arquitectura.X86_64
    assert de_lista_cpu([ModeloCpu("neoverse-n1", False)]) == Arquitectura.AARCH64
    assert (
        de_lista_cpu([ModeloCpu("kvm64", False), ModeloCpu("cortex-a53", False)])
        == Arquitectura.X86_64
    )
    assert de_lista_cpu([]) == Arquitectura.DESCONOCIDA
    t = _transporte(version=V_84, estados={"pve1": _403()})
    cliente = crear_sesion(t, version=V_84).cliente
    sin_lista = detectar_nodo(cliente, "pve1")
    assert sin_lista.arquitectura == Arquitectura.DESCONOCIDA
    con_lista = detectar_nodo(cliente, "pve1", modelos_cpu=arm)
    assert con_lista == ArquitecturaNodo(Arquitectura.AARCH64, FuenteArquitectura.LISTA_CPU)
    assert _lecturas(t, "/nodes/pve1/capabilities/qemu/cpu") == 0  # nunca lee la lista él mismo


def test_ca_d2_5_4_si_tampoco_hay_lista_de_cpu_la_arquitectura_es_desconocida():
    t = _transporte(version=V_84, estados={"pve1": _403()})
    cliente = crear_sesion(t, version=V_84).cliente
    r = detectar_nodo(cliente, "pve1", modelos_cpu=[ModeloCpu("host", False)])
    assert r.arquitectura == Arquitectura.DESCONOCIDA and r.motivo == "sin_permiso"


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (_403(), "sin_permiso"),
        (ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"}, "595"), "no_responde"),
        (ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {}, "596"), "no_responde"),
        (ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "?"), "no_responde"),
        (RuntimeError("inesperado"), "no_responde"),
    ],
)
def test_detectar_nodo_nunca_lanza_y_da_el_motivo(error, motivo):
    t = _transporte(version=V_84, estados={"pve1": error})
    r = detectar_nodo(crear_sesion(t, version=V_84).cliente, "pve1")
    assert r == ArquitecturaNodo(Arquitectura.DESCONOCIDA, FuenteArquitectura.NINGUNA, motivo)


@pytest.mark.parametrize("estado", [None, [], "texto", 5, {"current-kernel": {}}])
def test_un_estado_con_forma_inesperada_es_desconocida_con_motivo_formato(estado):
    t = _transporte(version=V_84, estados={"pve1": estado})
    r = detectar_nodo(crear_sesion(t, version=V_84).cliente, "pve1")
    assert r.arquitectura == Arquitectura.DESCONOCIDA and r.motivo == "formato"


# --- CA-D2.5.5: valores hostiles no llegan a ningún sitio -----------------------------------------


def test_ca_d2_5_5_valores_hostiles_en_el_estado_dan_desconocida_y_no_llegan_a_la_interfaz():
    hostil = "<script>alert(1)</script>\x1b[31m" + "A" * 4000
    for estado in (
        _estado("riscv64"),
        _estado(hostil),
        _estado(None, kversion=hostil),
        _estado(None, kversion="Linux " + "A" * 5000),
    ):
        t = _transporte(version=V_84, estados={"pve1": estado})
        inv = _descubrir(t, version=V_84)
        assert inv.arquitecturas["pve1"].arquitectura == Arquitectura.DESCONOCIDA
        texto = repr(inv.arquitecturas) + json.dumps(
            [a.params for a in avisos_arquitectura(inv, ["pve1"], caps_de(V_84))]
        )
        assert "script" not in texto and "\x1b" not in texto and "AAAA" not in texto


def test_ca_d2_5_5_el_cliente_sanea_y_acota_host_arch():
    larga = "aarch64" + "\x00\x1b" * 100 + "z" * 500
    t = TransporteFalso().en(
        "GET",
        "/cluster/resources",
        [
            {"node": "pve1", "host-arch": larga},
            {"node": "pve2", "host-arch": "<b>x86_64</b>"},
            {"node": "pve3"},
            {"host-arch": "aarch64"},
            "basura",
            {"node": "pve4", "host-arch": 12},
        ],
    )
    resultado = _cliente(t).arquitecturas_nodos()
    assert set(resultado) <= {"pve1", "pve2", "pve4"}
    assert all(len(v) <= 32 for v in resultado.values())
    assert all("\x00" not in v and "\x1b" not in v and "<" not in v for v in resultado.values())
    assert normalizar(resultado["pve1"]) == Arquitectura.DESCONOCIDA


@pytest.mark.parametrize("data", [None, {}, "texto", 7])
def test_el_cliente_con_resources_sin_forma_de_lista_devuelve_vacio(data):
    t = TransporteFalso().en("GET", "/cluster/resources", data)
    assert _cliente(t).arquitecturas_nodos() == {}


# --- CA-D2.5.6: nodo fuera de línea ---------------------------------------------------------------


@pytest.mark.parametrize("version", [V_84, V_92], ids=["8.4", "9.2"])
def test_ca_d2_5_6_un_nodo_fuera_de_linea_no_hace_llamadas_y_el_resto_se_detecta(version):
    recursos = (
        [
            {"node": "pve1", "type": "node", "host-arch": "aarch64"},
            {"node": "pve3", "type": "node", "host-arch": "x86_64"},
        ]
        if version == V_92
        else None
    )
    t = _transporte(
        version=version,
        recursos=recursos,
        estados={"pve1": _estado("aarch64"), "pve3": _estado("x86_64")},
        nodos="nodes_nodo_offline.json",
    )
    inv = _descubrir(t, version=version)
    assert _lecturas(t, "/nodes/pve2/status") == 0
    assert _lecturas(t, "/nodes/pve2/capabilities/qemu/cpu") == 0
    info = inv.arquitecturas["pve2"]
    assert info.arquitectura == Arquitectura.DESCONOCIDA and info.motivo == "no_responde"
    assert inv.arquitecturas["pve1"].arquitectura == Arquitectura.AARCH64
    assert inv.arquitecturas["pve3"].arquitectura == Arquitectura.X86_64
    (v_d04,) = [
        a for a in avisos_arquitectura(inv, ["pve2"], caps_de(version)) if a.regla == "V-D04"
    ]
    assert v_d04.params["motivo"] == "no_responde"


def test_un_nodo_que_no_consta_en_el_inventario_cuenta_como_no_responde_y_es_x86():
    t = _transporte(version=V_84)
    inv = _descubrir(t, version=V_84)
    assert arquitectura_de(inv, "inexistente") == Arquitectura.DESCONOCIDA
    assert arquitectura_efectiva(inv, "inexistente") == Arquitectura.X86_64
    (aviso,) = avisos_arquitectura(inv, ["inexistente"], caps_de(V_84))
    assert aviso.regla == "V-D04" and aviso.params["motivo"] == "no_responde"


# --- CA-D2.5.7: arquitectura forzada a mano -------------------------------------------------------


def test_ca_d2_5_7_forzar_manda_sobre_la_detectada_y_marca_la_fuente_manual():
    t = _transporte(version=V_84)
    inv = _descubrir(t, version=V_84)
    forzado = forzar(inv, "pve1", Arquitectura.AARCH64)
    assert arquitectura_efectiva(forzado, "pve1") == Arquitectura.AARCH64
    assert forzado.arquitecturas["pve1"].fuente == FuenteArquitectura.MANUAL
    assert arquitectura_de(inv, "pve1") == Arquitectura.X86_64  # el original no cambia
    (v_d05,) = [
        a for a in avisos_arquitectura(forzado, ["pve1"], caps_de(V_84)) if a.regla == "V-D05"
    ]
    assert v_d05.params["forzada"] == "1"
    assert v_d05.params["variante"] == "previa"


def test_ca_d2_5_7_con_9_2_el_aviso_v_d05_usa_la_variante_9_2():
    inv = _descubrir(_transporte(recursos=RECURSOS_92))
    (aviso,) = avisos_arquitectura(inv, ["pve2"], caps_de(V_92))
    assert aviso.regla == "V-D05" and aviso.params["variante"] == "9_2"
    assert "forzada" not in aviso.params


def test_ca_d2_5_7_volver_a_detectar_quita_solo_la_marca_manual():
    inv = _descubrir(_transporte(version=V_84), version=V_84)
    forzado = forzar(inv, "pve1", Arquitectura.AARCH64)
    assert "pve1" not in forzar(forzado, "pve1", None).arquitecturas
    # Un nodo detectado (no manual) no se borra al pedir «detectar».
    assert forzar(inv, "pve1", None).arquitecturas["pve1"].fuente == FuenteArquitectura.KERNEL
    assert "pve1" not in forzar(forzado, "pve1", Arquitectura.DESCONOCIDA).arquitecturas


def test_cl_d5_forzar_x86_a_mano_sobre_un_nodo_arm_cambia_el_tratamiento():
    inv = _descubrir(_transporte(recursos=RECURSOS_92))
    assert arquitectura_efectiva(inv, "pve2") == Arquitectura.AARCH64
    assert (
        arquitectura_efectiva(forzar(inv, "pve2", Arquitectura.X86_64), "pve2")
        == Arquitectura.X86_64
    )


# --- Función por nodo y concurrencia --------------------------------------------------------------


def test_descubrir_nodo_d_no_lee_el_estado_si_host_arch_ya_trae_el_nodo():
    t = _transporte(recursos=RECURSOS_92)
    sesion = crear_sesion(t)
    *_, arq = descubrir_nodo_d(sesion, "pve2", recursos={"pve2": "aarch64"})
    assert arq is None
    assert _lecturas(t, "/nodes/pve2/status") == 0
    *_, arq = descubrir_nodo_d(sesion, "pve2", recursos={"pve2": "raro"})
    assert arq is not None and arq.arquitectura == Arquitectura.X86_64  # el estado manda (x86)
    assert _lecturas(t, "/nodes/pve2/status") == 1


def test_detectar_pide_el_estado_solo_a_los_nodos_que_recursos_no_cubre():
    t = _transporte(version=V_84, estados={"pve2": _estado("aarch64")})
    sesion = crear_sesion(t, version=V_84)
    res = detectar(sesion, ["pve1", "pve2"], recursos={"pve1": "x86_64"})
    assert res["pve1"].fuente == FuenteArquitectura.RECURSOS
    assert res["pve2"].arquitectura == Arquitectura.AARCH64
    assert _lecturas(t, "/nodes/pve1/status") == 0 and _lecturas(t, "/nodes/pve2/status") == 1


def test_el_descubrimiento_sigue_usando_el_tope_de_hilos_existente():
    assert MAX_HILOS == 8  # la lectura por nodo no añade otra ronda (RNF-D4)
