"""Planificación y simulación de lotes con las opciones de la fase B (0.7.0).

Requisitos: CA-B0.1.2, RF-B0.5 (CA-B0.5.1, CA-B0.5.2), CA-B0.2.1 (simulación), CA-B1.11.1,
CA-B1.11.2, CA-B1.12.1, CA-B1.16.1, CA-B1.16.2, RF-B4.2 (CA-B4.2.1 a CA-B4.2.5), RF-B4.4
(CA-B4.4.1 a CA-B4.4.3), CA-B14.2, CL-B1, CL-B14 y RNF-B5 (una consulta por almacenamiento).
La planificación lee con el clúster simulado (solo GET); la simulación no escribe nada.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from proxlaunch.nucleo.cloudinit.deteccion import info_cloudinit
from proxlaunch.nucleo.cloudinit.modelos import (
    CloudInitParcial,
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.filas import definicion_por_filas
from proxlaunch.nucleo.lote.modelos import (
    AccionPeticion,
    Algoritmo,
    EstadoMV,
    FilaLote,
    ModoDestino,
    Severidad,
)
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.secreto import MASCARA, Secreto

from . import apoyo_golden_fase_b as g
from .apoyo_fase_b_p1 import (
    CENTINELA,
    CLAVE,
    CLAVE_2,
    MundoB,
    ci,
    ci_completa,
    config_plantilla,
)
from .apoyo_lote import definicion, error_http
from .apoyo_mvp4 import cfg_clon

MIB = 1024 * 1024
A = AccionPeticion


def _problemas(plan, regla):
    return [p for p in plan.problemas if p.regla == regla]


def _ci_put(m, vmid):
    """El ``PUT`` de cloud-init de una MV (el único con ``ciuser``/``ipconfig0``/… del lote)."""
    (put,) = [
        p for p in m.puts_config(vmid) if {"ciuser", "ipconfig0", "nameserver", "sshkeys"} & set(p)
    ]
    return put


def _def(n, cloudinit, *, nodos=(), clon=None, **kw):
    """Lote homogéneo de clones de «base» repartido por turnos entre ``nodos``."""
    base = dataclasses.replace(cfg_clon("base", **(clon or {})), cloudinit=cloudinit, **kw)
    modo = (
        ModoDestino.NODOS_ELEGIDOS
        if len(nodos) > 1
        else ModoDestino.UN_NODO
        if nodos
        else ModoDestino.AUTOMATICO
    )
    return definicion(
        n, plantilla_vm=base, modo=modo, nodos=tuple(nodos), algoritmo=Algoritmo.POR_TURNOS
    )


def _mundo_3_nodos(**kw):
    """3 nodos, plantilla en almacenamiento compartido (clonable en cualquiera) y un almacenamiento
    ``snip`` con contenido snippets en cada nodo."""
    kw.setdefault("nodos", ("pve1", "pve2", "pve3"))
    kw.setdefault(
        "plantillas",
        {9000: ("base", config_plantilla(scsi0="nfs1:base-9000-disk-0,size=8G"))},
    )
    return MundoB(**kw)


def _filas(m, *specs):
    """Filas de clones: cada spec es ``(nombre, plantilla, opciones | None, nodo | None)``."""
    return tuple(
        FilaLote(nombre, cfg_clon(plantilla), None, nodo, None, opciones)
        for nombre, plantilla, opciones, nodo in specs
    )


def _def_filas(filas, opciones=None):
    d = definicion_por_filas(filas, plantilla_base=cfg_clon("base"))
    return dataclasses.replace(d, opciones=opciones)


# --- CA-B0.2.1: la simulación sin opciones de la fase B es idéntica a la de 0.6.0 ----------------


@pytest.mark.parametrize("nombre", ["simulacion_lote_vacio", "simulacion_lote_clon"])
def test_ca_b0_2_1_la_simulacion_por_defecto_es_identica_a_la_de_0_6_0(nombre):
    esperado = g.golden()["escenarios"][nombre]
    assert json.loads(json.dumps(g.actuales()[nombre])) == esperado


@pytest.mark.parametrize("nombre", ["simulacion_lote_vacio", "simulacion_lote_clon"])
def test_ca_b0_2_1_la_simulacion_por_defecto_no_lleva_acciones_ni_claves_de_la_fase_b(nombre):
    _, detalle = g.actuales()[nombre]
    for peticiones in detalle.values():
        assert not {p[0] for p in peticiones} & {"cloudinit", "contrasena", "sondear_ip"}
        assert not [k for p in peticiones for k in p[2] if k.startswith(("ci", "ipconfig"))]


# --- CA-B0.1.2 / CA-B1.12.1: la simulación --------------------------------------------------------


def _simular(m, definicion_, **kw):
    return simular(m.sesion, definicion_, m.inv, reloj=m.reloj, **kw)


def test_ca_b0_1_2_la_simulacion_lista_los_pasos_nuevos_en_el_orden_del_flujo():
    """CLONAR, CONFIGURAR, CLOUDINIT, CONTRASENA, AMPLIAR, ENCENDER y SONDEAR_IP por MV; sin
    ninguna llamada de escritura real."""
    m = MundoB()
    d = _def(
        2, ci_completa(Secreto(CENTINELA), serie=True), encender=True, esperar_ip=True,
        clon={"ajustes": AjustesClon(disco_gib=64)},
    )  # fmt: skip
    res = _simular(m, d)
    assert not res.plan.bloqueado, res.plan.problemas
    assert m.cl.solo_lecturas
    for peticiones in res.peticiones_detalle.values():
        assert [p.accion for p in peticiones] == [
            A.CLONAR, A.CONFIGURAR, A.CLOUDINIT, A.CONTRASENA, A.AMPLIAR, A.ENCENDER, A.SONDEAR_IP
        ]  # fmt: skip
        by = {p.accion: p for p in peticiones}
        assert by[A.CONTRASENA].parametros == {"cipassword": MASCARA}
        assert by[A.SONDEAR_IP].parametros == {"plazo_s": "120"}


def test_ca_b0_1_2_sin_contrasena_no_hay_paso_de_contrasena_y_sin_esperar_ip_no_hay_sondeo():
    m = MundoB()
    res = _simular(m, _def(1, ci(), encender=True))
    (acciones,) = [[p.accion for p in ps] for ps in res.peticiones_detalle.values()]
    assert A.CLOUDINIT in acciones and A.CONTRASENA not in acciones and A.SONDEAR_IP not in acciones
    assert acciones[-1] == A.ENCENDER


def test_ca_b0_1_2_sin_encender_no_hay_sondeo_aunque_se_pida_esperar_la_ip():
    """El sondeo va tras ``encender``; sin él la validación V-B60 bloquea el plan."""
    m = MundoB()
    res = _simular(m, _def(1, ci(), esperar_ip=True))
    assert res.plan.bloqueado and _problemas(res.plan, "V-B60")
    assert all(A.SONDEAR_IP not in [p.accion for p in ps] for ps in res.peticiones_detalle.values())


def test_la_simulacion_omite_el_paso_de_contrasena_si_el_secreto_ya_se_olvido():
    m = MundoB()
    secreto = Secreto(CENTINELA)
    d = _def(1, ci(contrasena=secreto))
    secreto.olvidar()
    res = _simular(m, d)
    (acciones,) = [[p.accion for p in ps] for ps in res.peticiones_detalle.values()]
    assert A.CONTRASENA not in acciones


def test_ca_b1_12_1_la_simulacion_muestra_el_valor_final_de_cada_parametro_por_mv():
    """IP en serie ya calculada, DNS y el NÚMERO de claves (nunca su cuerpo)."""
    m = MundoB()
    res = _simular(m, _def(3, ci_completa(serie=True)))
    assert not res.plan.bloqueado, res.plan.problemas
    for i, peticiones in enumerate(res.peticiones_detalle.values()):
        (cloud,) = [p for p in peticiones if p.accion == A.CLOUDINIT]
        assert cloud.parametros["ipconfig0"] == f"ip=10.0.0.{50 + i}/24,gw=10.0.0.1"
        assert cloud.parametros["nameserver"] == "1.1.1.1 9.9.9.9"
        assert cloud.parametros["sshkeys"] == "[2]"
        texto = json.dumps(cloud.parametros)
        assert CLAVE.split()[1] not in texto and CLAVE_2.split()[1] not in texto


def test_la_simulacion_es_la_misma_que_se_envia_de_verdad():
    """CA-B0.1.2 / CA-L11: los valores simulados de cloud-init son los del ``PUT`` real."""
    m = MundoB()
    d = _def(3, ci_completa(serie=True), encender=True)
    res = _simular(m, d)
    plan = m.planificar(d)
    libro = m.ejecutar(plan)
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.OK}
    for vmid, peticiones in res.peticiones_detalle.items():
        (cloud,) = [p for p in peticiones if p.accion == A.CLOUDINIT]
        real = _ci_put(m, vmid)
        assert list(real) == list(cloud.parametros)  # mismas claves y mismo orden
        assert {k: v for k, v in real.items() if k != "sshkeys"} == {
            k: v for k, v in cloud.parametros.items() if k != "sshkeys"
        }
        acciones_reales = [e for e in m.escrituras(vmid)]
        esperado = {A.CLONAR: "clone", A.CONFIGURAR: "ajustes", A.CLOUDINIT: "ci",
                    A.ENCENDER: "start"}  # fmt: skip
        assert acciones_reales == [esperado[p.accion] for p in peticiones]


# --- RF-B0.5: un mismo valor para todo el lote y valores por fila ---------------------------------


def test_ca_b0_5_1_las_n_peticiones_llevan_los_mismos_valores_salvo_la_ip_en_serie():
    m = MundoB()
    plan, _ = m.lote(4, ci_completa(serie=True))
    puts = [_ci_put(m, e.vmid) for e in plan.elementos]
    sin_ip = [{k: v for k, v in p.items() if k != "ipconfig0"} for p in puts]
    assert all(p == sin_ip[0] for p in sin_ip)
    assert [p["ipconfig0"] for p in puts] == [
        f"ip=10.0.0.{50 + i}/24,gw=10.0.0.1" for i in range(4)
    ]


def test_ca_b0_5_1_la_ip_en_serie_se_expande_al_planificar_y_ya_no_es_serie():
    """DT-B3: el ``cfg`` de cada elemento es el que se envía (simulación y creación coinciden)."""
    m = MundoB()
    plan = m.planificar(_def(3, ci_completa(serie=True)))
    ips = [e.cfg.cloudinit.tarjeta(0) for e in plan.elementos]
    assert [t.ip for t in ips] == ["10.0.0.50/24", "10.0.0.51/24", "10.0.0.52/24"]
    assert not any(t.serie for t in ips)


def test_ca_b0_5_1_un_lote_con_ip_fija_sin_serie_y_mas_de_una_mv_bloquea_v_b38():
    m = MundoB()
    plan = m.planificar(_def(3, ci_completa(serie=False)))
    assert plan.bloqueado and _problemas(plan, "V-B38")


def _fila_ip(nombre, ip):
    parcial = CloudInitParcial(tarjeta0=TarjetaCloudInit(0, ModoTarjeta.FIJA, ip))
    return FilaLote(
        nombre, cfg_clon("base"), None, None, None, OpcionesParciales(cloudinit=parcial)
    )


def test_ca_b0_5_1_dos_mvs_con_la_misma_ip_entre_otras_distintas_bloquean_v_b31():
    m = MundoB()
    plan = m.planificar(_def_filas((_fila_ip("a-01", "10.0.0.9/24"),
                                    _fila_ip("a-02", "10.0.0.9/24"),
                                    _fila_ip("a-03", "10.0.0.10/24"))))  # fmt: skip
    assert plan.bloqueado and _problemas(plan, "V-B31")


def test_ca_b0_5_1_todas_las_filas_con_la_misma_ip_fija_dan_v_b38_y_no_v_b31():
    m = MundoB()
    plan = m.planificar(
        _def_filas((_fila_ip("a-01", "10.0.0.9/24"), _fila_ip("a-02", "10.0.0.9/24")))
    )
    assert plan.bloqueado and _problemas(plan, "V-B38") and not _problemas(plan, "V-B31")


def test_ca_b0_5_1_ips_distintas_por_fila_no_bloquean():
    m = MundoB()
    plan = m.planificar(
        _def_filas((_fila_ip("a-01", "10.0.0.9/24"), _fila_ip("a-02", "10.0.0.10/24")))
    )
    assert not plan.bloqueado, plan.problemas


def test_ca_b0_5_2_cada_peticion_lleva_el_valor_de_su_fila_o_el_del_formulario():
    """Celda no vacía = la de la fila; celda vacía = hereda del formulario (RF-B0.5, CA-B6.3.2)."""
    m = MundoB()
    formulario = OpcionesLote(
        cloudinit=ConfigCloudInit(usuario="base", dominio="lab.local", dns=("9.9.9.9",),
                                  claves=(CLAVE,)),
        encender=False,
    )  # fmt: skip
    filas = _filas(
        m,
        ("a-01", "base", OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana")), None),
        ("a-02", "base", None, None),
        ("a-03", "base", OpcionesParciales(cloudinit=CloudInitParcial(dns=("8.8.8.8",),
            tarjeta0=TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.7/24", False, "10.0.0.1"))),
         None),
    )  # fmt: skip
    plan = m.planificar(_def_filas(filas, formulario))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.OK}
    p1, p2, p3 = (_ci_put(m, e.vmid) for e in plan.elementos)
    assert (p1["ciuser"], p1["nameserver"], p1["searchdomain"]) == ("ana", "9.9.9.9", "lab.local")
    assert (p2["ciuser"], p2["nameserver"], p2["searchdomain"]) == ("base", "9.9.9.9", "lab.local")
    assert (p3["ciuser"], p3["nameserver"], p3["searchdomain"]) == ("base", "8.8.8.8", "lab.local")
    assert p3["ipconfig0"] == "ip=10.0.0.7/24,gw=10.0.0.1"
    assert "ipconfig0" not in p1 and "ipconfig0" not in p2
    assert all("sshkeys" in p for p in (p1, p2, p3))  # las claves del formulario llegan a todas


def test_ca_b0_5_2_una_fila_con_la_contrasena_propia_solo_la_envia_a_esa_mv():
    m = MundoB()
    filas = _filas(
        m,
        ("a-01", "base", OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana")), None),
        ("a-02", "base", OpcionesParciales(cloudinit=CloudInitParcial(
            usuario="eva", contrasena=Secreto(CENTINELA))), None),
    )  # fmt: skip
    plan = m.planificar(_def_filas(filas, OpcionesLote()))
    libro = m.ejecutar(plan)
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.OK}
    vmids = [e.vmid for e in plan.elementos]
    assert m.escrituras(vmids[0]).count("pw") == 0
    assert m.escrituras(vmids[1]).count("pw") == 1


# --- CA-B1.11: lotes por filas con plantillas distintas -------------------------------------------


def _mundo_dos_plantillas():
    return MundoB(
        plantillas={
            9000: ("base", config_plantilla()),
            9001: ("sinu", config_plantilla(unidad=None)),
        }
    )


def test_ca_b1_11_1_solo_las_filas_de_la_plantilla_sin_unidad_son_invalidas_y_la_nombran():
    m = _mundo_dos_plantillas()
    con = OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana"))
    filas = _filas(
        m, ("a-01", "base", con, None), ("a-02", "base", con, None),
        ("b-01", "sinu", con, None), ("b-02", "sinu", con, None),
    )  # fmt: skip
    plan = m.planificar(_def_filas(filas))
    assert plan.bloqueado
    v20 = _problemas(plan, "V-B20")
    assert v20 and all(p.params["plantilla"] == "sinu" for p in v20)
    assert all(p.severidad == Severidad.ERROR for p in v20)
    assert v20[0].indice == 2  # la primera fila de la plantilla sin unidad
    assert m.cl.solo_lecturas  # ninguna escritura hasta resolverlo


def test_ca_b1_11_1_quitar_las_filas_invalidas_deja_el_lote_creable():
    m = _mundo_dos_plantillas()
    con = OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana"))
    plan = m.planificar(
        _def_filas(_filas(m, ("a-01", "base", con, None), ("a-02", "base", con, None)))
    )
    assert not plan.bloqueado, plan.problemas


def test_ca_b1_11_2_una_fila_sin_cloudinit_no_emite_put_de_cloudinit():
    m = _mundo_dos_plantillas()
    con = OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana"))
    filas = _filas(m, ("a-01", "base", con, None), ("a-02", "base", None, None),
                   ("a-03", "base", con, None))  # fmt: skip
    plan = m.planificar(_def_filas(filas, OpcionesLote()))
    assert not plan.bloqueado, plan.problemas
    libro = m.ejecutar(plan)
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.OK}
    vmids = [e.vmid for e in plan.elementos]
    assert [m.escrituras(v).count("ci") for v in vmids] == [1, 0, 1]


def test_cl_b1_lote_mixto_solo_se_marcan_las_filas_invalidas_y_no_se_escribe_nada():
    """CL-B1: unas filas con cloud-init y otras sin, con plantillas distintas."""
    m = _mundo_dos_plantillas()
    con = OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana"))
    filas = _filas(m, ("a-01", "base", con, None), ("a-02", "base", None, None),
                   ("b-01", "sinu", None, None), ("b-02", "sinu", con, None))  # fmt: skip
    plan = m.planificar(_def_filas(filas, OpcionesLote()))
    v20 = _problemas(plan, "V-B20")
    assert [p.indice for p in v20] == [3]  # solo la fila de «sinu» que pide cloud-init
    assert plan.bloqueado and m.cl.solo_lecturas


# --- CA-B1.16: «Comprobar» bloquea en errores y no en avisos --------------------------------------


@pytest.mark.parametrize(
    ("cloudinit", "regla"),
    [
        (ConfigCloudInit(usuario="con espacio"), "V-B21"),
        (ConfigCloudInit(claves=("esto no es una clave",)), "V-B22"),
        (ConfigCloudInit(claves=("-----BEGIN OPENSSH PRIVATE KEY-----",)), "V-B23"),
        (
            ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "999.1.1.1/24"),)),
            "V-B26",
        ),
        (ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.50"),)), "V-B26"),
        (ConfigCloudInit(tarjetas=(TarjetaCloudInit(5, ModoTarjeta.DHCP),)), "V-B34"),
        (ConfigCloudInit(dns=("no-es-ip",)), "V-B32"),
        (ConfigCloudInit(dominio="dominio con espacios"), "V-B33"),
        (ConfigCloudInit(snippets=SnippetsCloudInit(user="local:iso/a.iso")), "V-B54"),
    ],
)
def test_ca_b1_16_1_un_error_de_b1_bloquea_el_plan_y_la_creacion_se_rechaza_sin_escribir(
    cloudinit, regla
):
    m = MundoB()
    plan = m.planificar(_def(1, cloudinit))
    errores = [p for p in _problemas(plan, regla) if p.severidad == Severidad.ERROR]
    assert plan.bloqueado and errores, (regla, plan.problemas)
    # El servicio recibe la configuración ya preparada por el plan (con lo que dice la plantilla).
    cfg = dataclasses.replace(m.cfg(cloudinit), info_cloudinit=info_cloudinit(config_plantilla()))
    r = m.crear(cfg)
    assert r.desenlace.value == "error"
    assert m.cl.rutas_de_escritura() == []  # ni POST ni PUT


def test_ca_b1_16_1_los_params_de_los_errores_no_llevan_valores_secretos_ni_la_clave():
    m = MundoB()
    secreto = Secreto(CENTINELA)
    plan = m.planificar(
        _def(
            1,
            ConfigCloudInit(
                usuario="con espacio", claves=("ssh-rsa !!!!", CLAVE), contrasena=secreto
            ),
        )
    )
    texto = json.dumps([dataclasses.asdict(p) for p in plan.problemas], default=str)
    assert CENTINELA not in texto and CLAVE.split()[1] not in texto and "!!!!" not in texto


def test_ca_b1_16_2_solo_avisos_permite_crear_y_el_aviso_queda_en_el_plan():
    m = MundoB()
    cloudinit = ci(usuario="Deploy", dns=("1.1.1.1", "8.8.8.8", "9.9.9.9", "4.4.4.4"))
    plan = m.planificar(_def(2, cloudinit))
    assert not plan.bloqueado
    avisos = [p for p in plan.problemas if p.regla in ("V-B21", "V-B32")]
    assert {p.regla for p in avisos} == {"V-B21", "V-B32"}
    assert all(p.severidad == Severidad.AVISO for p in avisos)
    libro = m.ejecutar(plan)
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.OK}


def test_una_contrasena_corta_es_solo_un_aviso():
    m = MundoB()
    plan = m.planificar(_def(1, ci(contrasena=Secreto("corta"))))
    assert not plan.bloqueado


# --- CA-B14.2: agrupar el error de plantilla ------------------------------------------------------


def test_ca_b14_2_cien_filas_con_el_mismo_error_de_plantilla_se_agrupan_en_un_problema():
    m = _mundo_dos_plantillas()
    con = OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana"))
    filas = tuple(
        FilaLote(
            f"b-{i:03d}",
            cfg_clon(
                "sinu",
            ),
            None,
            None,
            None,
            con,
        )
        for i in range(100)
    )
    plan = m.planificar(_def_filas(filas))
    v20 = _problemas(plan, "V-B20")
    assert len(v20) == 1
    assert v20[0].params["plantilla"] == "sinu" and v20[0].params["elementos"] == "100"


def test_ca_b14_2_en_un_lote_homogeneo_el_error_tambien_sale_una_sola_vez():
    m = MundoB(plantillas={9000: ("base", config_plantilla(unidad=None))})
    plan = m.planificar(_def(20, ci()))
    v20 = _problemas(plan, "V-B20")
    assert len(v20) == 1 and v20[0].params["elementos"] == "20"


def test_ca_b14_2_dos_plantillas_distintas_dan_un_problema_por_plantilla():
    m = MundoB(
        plantillas={
            9000: ("sin1", config_plantilla(unidad=None)),
            9001: ("sin2", config_plantilla(unidad=None)),
        }
    )
    con = OpcionesParciales(cloudinit=CloudInitParcial(usuario="ana"))
    filas = _filas(m, *[(f"x-{i}", "sin1" if i % 2 else "sin2", con, None) for i in range(6)])
    plan = m.planificar(_def_filas(filas))
    v20 = _problemas(plan, "V-B20")
    assert sorted(p.params["plantilla"] for p in v20) == ["sin1", "sin2"]
    assert all(p.params["elementos"] == "3" for p in v20)


# --- RF-B4.2: snippets por nodo destino -----------------------------------------------------------


VENDOR = SnippetsCloudInit(vendor="snip:snippets/agente.yaml")


def _ci_snip(**kw):
    return ConfigCloudInit(snippets=VENDOR, **kw)


def test_ca_b4_2_1_un_snippet_ausente_en_un_nodo_bloquea_nombrando_ese_nodo():
    """6 MVs en 3 nodos con un almacenamiento no compartido; el snippet solo está en 2 nodos."""
    m = _mundo_3_nodos(snippets={("pve1", "snip"): [("snip:snippets/agente.yaml", 100)],
                                 ("pve2", "snip"): [("snip:snippets/agente.yaml", 100)],
                                 ("pve3", "snip"): []})  # fmt: skip
    plan = m.planificar(_def(6, _ci_snip(), nodos=("pve1", "pve2", "pve3")))
    v51 = _problemas(plan, "V-B51")
    assert plan.bloqueado and v51
    assert {p.params["nodo"] for p in v51} == {"pve3"}
    assert all(p.severidad == Severidad.ERROR for p in v51)
    assert {plan.elementos[p.indice].nodo for p in v51} == {"pve3"}


def test_ca_b4_2_1_con_el_snippet_en_los_tres_nodos_no_hay_problema():
    m = _mundo_3_nodos()
    m.cl.snippets = {(n, "snip"): [("snip:snippets/agente.yaml", 100)] for n in m.nodos}
    plan = m.planificar(_def(6, _ci_snip(), nodos=("pve1", "pve2", "pve3")))
    assert not plan.bloqueado, plan.problemas
    assert sorted(m.cl.listados_snippets) == [("pve1", "snip"), ("pve2", "snip"), ("pve3", "snip")]


def test_ca_b4_2_2_un_almacenamiento_compartido_se_consulta_una_sola_vez():
    m = _mundo_3_nodos(snip_compartido=True)
    plan = m.planificar(_def(6, _ci_snip(), nodos=("pve1", "pve2", "pve3")))
    assert not plan.bloqueado, plan.problemas
    assert len(m.cl.listados_snippets) == 1


def test_ca_b4_2_3_con_un_unico_nodo_de_destino_solo_se_consulta_ese_nodo():
    m = _mundo_3_nodos()
    m.cl.snippets = {("pve2", "snip"): [("snip:snippets/agente.yaml", 100)]}
    plan = m.planificar(_def(3, _ci_snip(), nodos=("pve2",)))
    assert not plan.bloqueado, plan.problemas
    assert m.cl.listados_snippets == [("pve2", "snip")]


def test_ca_b4_2_4_al_cambiar_el_nodo_destino_se_revalida_contra_ese_nodo():
    m = _mundo_3_nodos()
    m.cl.snippets = {("pve1", "snip"): [("snip:snippets/agente.yaml", 100)]}
    en_pve1 = m.planificar(_def(2, _ci_snip(), nodos=("pve1",)))
    en_pve3 = m.planificar(_def(2, _ci_snip(), nodos=("pve3",)))
    assert not en_pve1.bloqueado
    assert en_pve3.bloqueado and {p.params["nodo"] for p in _problemas(en_pve3, "V-B51")} == {
        "pve3"
    }


def test_ca_b4_2_4_por_filas_cada_mv_se_valida_contra_su_nodo():
    m = _mundo_3_nodos()
    m.cl.snippets = {("pve1", "snip"): [("snip:snippets/agente.yaml", 100)],
                     ("pve2", "snip"): []}  # fmt: skip
    con = OpcionesParciales(cloudinit=CloudInitParcial(snippets=VENDOR))
    filas = _filas(m, ("a-01", "base", con, "pve1"), ("a-02", "base", con, "pve2"))
    plan = m.planificar(_def_filas(filas))
    v51 = _problemas(plan, "V-B51")
    assert [(p.indice, p.params["nodo"]) for p in v51] == [(1, "pve2")]


def test_ca_b4_2_5_un_fallo_del_listado_no_bloquea_el_formulario():
    """403 o error del servidor al listar: no se juzga el snippet (entrada manual con aviso)."""
    for error in (error_http(403, "Permission check failed (/storage/snip, Datastore.Audit)"),
                  error_http(500, "fallo de prueba")):  # fmt: skip
        m = _mundo_3_nodos()
        m.cl.regla("GET", r"/storage/snip/content$", error)
        plan = m.planificar(_def(3, _ci_snip(), nodos=("pve1",)))
        assert not plan.bloqueado, plan.problemas
        assert not _problemas(plan, "V-B51")
        listado = plan.catalogo.snippets_en("pve1", "snip")
        assert listado is not None and listado.error is not None


def test_ca_b4_2_5_el_403_del_listado_se_anota_como_catalogo_sin_permiso():
    m = _mundo_3_nodos()
    m.cl.regla(
        "GET",
        r"/storage/snip/content$",
        error_http(403, "Permission check failed (/storage/snip, Datastore.Audit)"),
    )
    plan = m.planificar(_def(3, _ci_snip(), nodos=("pve1",)))
    assert (
        plan.catalogo.snippets_en("pve1", "snip").error.codigo == CodigoError.CATALOGO_SIN_PERMISO
    )


def test_cl_b14_storage_compartido_pero_nodo_sin_acceso_bloquea_nombrando_el_nodo():
    m = _mundo_3_nodos(snip_compartido=True)
    m.inv.storages_todos = {
        n: tuple(s for s in ss if not (n == "pve3" and s.id == "snip"))
        for n, ss in m.inv.storages_todos.items()
    }
    plan = m.planificar(_def(6, _ci_snip(), nodos=("pve1", "pve2", "pve3")))
    # Con el almacenamiento compartido pero invisible para pve3 el plan lo bloquea nombrando el nodo
    # con V-B50 (el nodo no tiene ningún almacenamiento con snippets); CL-B14 prevé V-B51.
    bloqueos = _problemas(plan, "V-B50") + _problemas(plan, "V-B51")
    assert plan.bloqueado and {p.params["nodo"] for p in bloqueos} == {"pve3"}
    assert all(p.severidad == Severidad.ERROR for p in bloqueos)


def test_rnf_b5_sin_snippets_elegidos_no_se_lista_ningun_almacenamiento_de_snippets():
    m = _mundo_3_nodos()
    m.planificar(_def(3, ci()))
    assert m.cl.listados_snippets == []


def test_rnf_b5_el_planificar_no_consulta_dos_veces_el_mismo_almacenamiento_por_nodo():
    m = _mundo_3_nodos()
    m.planificar(_def(9, _ci_snip(), nodos=("pve1", "pve2", "pve3")))
    assert len(m.cl.listados_snippets) == len(set(m.cl.listados_snippets)) == 3


# --- RF-B4.4: tamaño y combinación ----------------------------------------------------------------


def _snips(**tamanos):
    return {("pve1", "snip"): [(f"snip:snippets/{n}.yaml", t) for n, t in tamanos.items()]}


def _ci_con(**tipos):
    return ConfigCloudInit(
        snippets=SnippetsCloudInit(**{t: f"snip:snippets/{n}.yaml" for t, n in tipos.items()})
    )


def test_ca_b4_4_1_un_snippet_de_2_mib_es_un_error_de_tamano_individual():
    m = MundoB(snippets=_snips(grande=2 * MIB))
    plan = m.planificar(_def(1, _ci_con(vendor="grande")))
    v52 = _problemas(plan, "V-B52")
    assert plan.bloqueado and [p.params["motivo"] for p in v52] == ["individual"]


def test_ca_b4_4_1_tres_snippets_de_1_mib_exactos_suman_3_mib_y_se_aceptan():
    m = MundoB(snippets=_snips(a=MIB, b=MIB, c=MIB))
    plan = m.planificar(_def(1, _ci_con(user="a", vendor="b", network="c")))
    assert not _problemas(plan, "V-B52") and not plan.bloqueado


def test_ca_b4_4_1_tres_snippets_de_1_2_mib_fallan_por_tamano_individual_cada_uno():
    m = MundoB(snippets=_snips(a=int(1.2 * MIB), b=int(1.2 * MIB), c=int(1.2 * MIB)))
    plan = m.planificar(_def(1, _ci_con(user="a", vendor="b", network="c")))
    v52 = _problemas(plan, "V-B52")
    individuales = [p for p in v52 if p.params["motivo"] == "individual"]
    assert plan.bloqueado and len(individuales) == 3  # además la suma (3,6 MiB) supera los 3 MiB


def test_ca_b4_4_1_cuatro_snippets_de_1_mib_superan_la_suma_de_3_mib():
    m = MundoB(snippets=_snips(a=MIB, b=MIB, c=MIB, d=MIB))
    plan = m.planificar(_def(1, _ci_con(user="a", vendor="b", network="c", meta="d")))
    v52 = _problemas(plan, "V-B52")
    assert plan.bloqueado and [p.params["motivo"] for p in v52] == ["suma"]


def test_ca_b4_4_1_un_snippet_de_exactamente_1_mib_se_acepta_y_uno_de_1_mib_mas_1_byte_no():
    ok = MundoB(snippets=_snips(a=MIB))
    assert not _problemas(ok.planificar(_def(1, _ci_con(vendor="a"))), "V-B52")
    mal = MundoB(snippets=_snips(a=MIB + 1))
    assert _problemas(mal.planificar(_def(1, _ci_con(vendor="a"))), "V-B52")


def test_ca_b4_4_2_elegir_user_con_usuario_o_claves_de_b1_es_un_aviso_no_un_error():
    m = MundoB(snippets=_snips(u=100))
    plan = m.planificar(
        _def(1, dataclasses.replace(_ci_con(user="u"), usuario="deploy", claves=(CLAVE,)))
    )
    v53 = _problemas(plan, "V-B53")
    assert [p.severidad for p in v53] == [Severidad.AVISO] and not plan.bloqueado


def test_ca_b4_4_2_tambien_avisa_si_solo_hay_contrasena():
    m = MundoB(snippets=_snips(u=100))
    plan = m.planificar(
        _def(1, dataclasses.replace(_ci_con(user="u"), contrasena=Secreto(CENTINELA)))
    )
    assert _problemas(plan, "V-B53") and not plan.bloqueado


def test_ca_b4_4_3_elegir_vendor_con_claves_de_b1_no_avisa_de_reemplazo():
    m = MundoB(snippets=_snips(v=100))
    plan = m.planificar(_def(1, dataclasses.replace(_ci_con(vendor="v"), claves=(CLAVE,))))
    assert not _problemas(plan, "V-B53") and not plan.bloqueado


def test_ca_b4_4_user_sin_nada_de_b1_tampoco_avisa():
    m = MundoB(snippets=_snips(u=100))
    plan = m.planificar(_def(1, _ci_con(user="u")))
    assert not _problemas(plan, "V-B53")


# --- La planificación no escribe nada -------------------------------------------------------------


def test_planificar_y_simular_con_la_fase_b_solo_leen():
    m = MundoB()
    d = _def(3, ci_completa(Secreto(CENTINELA), serie=True), encender=True, esperar_ip=True)
    m.planificar(d)
    _simular(m, d)
    assert m.cl.solo_lecturas
    assert m.cl.llamadas_agente == [] and not m.cl.llamadas_a("PUT")
