"""Creación por clon con cloud-init (fase B, 0.7.0): orden de escritura, atomicidad por MV y
compatibilidad byte a byte con 0.6.0.

Requisitos: RF-B0.2 (CA-B0.2.1, CA-B0.2.3), RF-B0.7 (CA-B0.7.1, CA-B0.7.2), CA-B1.4.7, RF-B1.6
(CA-B1.6.7, CA-B1.6.8), RF-B1.17 (CA-B1.17.1 a CA-B1.17.7), CA-B3.1.4, CL-B13 y la decisión del
orquestador sobre la contraseña olvidada (PARCIAL + ``CONTRASENA_OLVIDADA``).

Dobles: ``ClusterA`` (con las rutas de la fase B de ``apoyo_lote.Cluster``) y, cuando importa el
cuerpo exacto o la traducción real de un error, el ``TransporteHttp`` real con ``responses``.
Las instantáneas de 0.6.0 son ``tests/datos/fase_b/golden_v060.json``.
"""

from __future__ import annotations

import json
import re

import pytest

from proxlaunch.nucleo.cloudinit.modelos import (
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.ajustes import ajustes_pendientes, reintentar_ajustes
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.modelos.origen import AjustesClon
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.secreto import Secreto

from . import apoyo_golden_fase_b as g
from .apoyo_fase_b_p1 import (
    CENTINELA,
    CLAVE,
    PRIVS_B_8X,
    V_84,
    V_92,
    MundoB,
    ci,
    ci_completa,
    config_plantilla,
    fallar_put,
)
from .apoyo_lote import ControlAutomatico, Http, error_http

CLAVES_CI = frozenset(
    {"ciuser", "sshkeys", "nameserver", "searchdomain", "ciupgrade", "cicustom", "agent", "delete"}
)


def _es_put_ci(datos: dict) -> bool:
    return bool(set(datos) & CLAVES_CI) or any(k.startswith("ipconfig") for k in datos)


# --- RF-B0.2: sin regresiones, instantáneas de 0.6.0 ----------------------------------------------

ESCENARIOS_EJECUCION = [
    "vacio",
    "vacio_encender",
    "iso",
    "importar_con_resize",
    "clon_sin_ajustes",
    "clon_con_ajustes",
    "lote_3_encender",
    "reintento_de_ajustes",
]


def test_las_instantaneas_vienen_de_la_version_0_6_0():
    """Las instantáneas se generaron con el código de la etiqueta v0.6.0 (véase el módulo)."""
    golden = g.golden()
    assert golden["version_codigo"] == "0.6.0"
    assert set(golden["escenarios"]) == set(g.actuales())
    assert all(len(secuencia) >= 2 for secuencia in golden["escenarios"].values())


@pytest.mark.parametrize("nombre", ESCENARIOS_EJECUCION)
def test_ca_b0_2_1_con_las_opciones_b_por_defecto_la_secuencia_es_identica_a_la_de_0_6_0(nombre):
    """CA-B0.2.1: método, ruta, consulta y cuerpo (bytes) de TODAS las peticiones, en orden."""
    esperado = g.golden()["escenarios"][nombre]
    actual = json.loads(json.dumps(g.actuales()[nombre]))
    assert actual == esperado


@pytest.mark.parametrize("nombre", ESCENARIOS_EJECUCION)
def test_ca_b0_2_1_ninguna_peticion_nueva_en_la_creacion_ni_de_lectura(nombre):
    """RF-B0.2: ni escrituras ni lecturas nuevas (agente, cloud-init, snippets, plantilla)."""
    for _metodo, ruta, cuerpo in g.actuales()[nombre]:
        assert "/agent/" not in ruta and "cloudinit" not in ruta and "snippets" not in ruta
        assert "/template" not in ruta
        assert not re.search(
            r"ciuser|sshkeys|ipconfig|cipassword|cicustom|nameserver|agent=", cuerpo
        )


def test_ca_b0_2_1_un_cloudinit_vacio_equivale_a_no_tener_cloudinit():
    """Con la sección vacía (valor por defecto del formulario) no cambia ninguna petición."""
    sin = MundoB()
    sin.crear(sin.cfg(None, ajustes=AjustesClon(cores=4), encender=True))
    vacia = MundoB()
    vacia.crear(vacia.cfg(ConfigCloudInit(), ajustes=AjustesClon(cores=4), encender=True))
    assert [(c.metodo, c.ruta, c.datos) for c in vacia.cl.llamadas] == [
        (c.metodo, c.ruta, c.datos) for c in sin.cl.llamadas
    ]


def test_ca_b3_1_4_sin_esperar_ip_no_hay_ninguna_peticion_de_agente():
    """CA-B3.1.4: con la casilla desmarcada la secuencia es la de 0.6.0 aunque haya cloud-init."""
    m = MundoB()
    m.lote(3, ci_completa(serie=True), encender=True)
    assert m.cl.llamadas_agente == []
    assert not m.cl.llamadas_a("GET", r"/agent/")
    assert not m.cl.llamadas_a("POST", r"/agent/")


# --- RF-B1.17: flujo de escritura -----------------------------------------------------------------


def test_ca_b1_17_1_orden_clone_ajustes_cloudinit_contrasena_resize_start():
    """CA-B1.17.1: clone → (espera de lock) → PUT ajustes → PUT cloud-init → PUT contraseña →
    resize → start."""
    m = MundoB()
    cfg = m.cfg(ci_completa(Secreto(CENTINELA)), ajustes=AjustesClon(cores=4, disco_gib=64),
                encender=True)  # fmt: skip
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    assert m.escrituras(100) == ["clone", "ajustes", "ci", "pw", "resize", "start"]


def test_ca_b1_17_1_sin_ajustes_ni_resize_ni_encendido_solo_clone_cloudinit_y_contrasena():
    m = MundoB()
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), etiquetas=()))
    assert r.desenlace == Desenlace.OK
    assert m.escrituras(100) == ["clone", "ci", "pw"]


def test_ca_b1_17_1_el_clon_espera_a_que_se_suelte_lock_clone_antes_de_escribir():
    """El ``lock: clone`` se consulta (GET) antes del primer PUT; sin lock no hay espera extra."""
    m = MundoB()
    m.crear(m.cfg(ci(), etiquetas=()))
    rutas = [(c.metodo, c.ruta) for c in m.cl.llamadas]
    primero_put = rutas.index(("PUT", "/nodes/pve1/qemu/100/config"))
    assert ("GET", "/nodes/pve1/qemu/100/config") in rutas[:primero_put]


def test_ca_b1_17_2_el_put_de_cloudinit_es_una_sola_llamada_y_no_lleva_cipassword():
    """CA-B1.17.2: todos los parámetros ``ci*`` juntos y la contraseña en su propio PUT."""
    m = MundoB()
    m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), etiquetas=()))
    puts = m.puts_config(100)
    con_ci = [p for p in puts if _es_put_ci(p)]
    assert len(con_ci) == 1
    assert "cipassword" not in con_ci[0]
    assert set(con_ci[0]) >= {"ciuser", "sshkeys", "ipconfig0", "nameserver", "searchdomain",
                              "ciupgrade", "cicustom", "agent"}  # fmt: skip
    con_pw = [p for p in puts if "cipassword" in p]
    assert len(con_pw) == 1 and set(con_pw[0]) == {"cipassword"}
    assert con_pw[0]["cipassword"] == CENTINELA  # el PUT lleva el valor real, no la máscara


def test_ca_b1_17_2_sin_contrasena_no_hay_put_de_contrasena():
    m = MundoB()
    m.crear(m.cfg(ci(), etiquetas=()))
    assert m.escrituras(100) == ["clone", "ci"]


def test_los_parametros_no_fijados_no_se_envian():
    """RF-B1.13: solo viajan las claves que el usuario fijó (usuario y tarjeta 0 DHCP)."""
    m = MundoB()
    m.crear(m.cfg(ConfigCloudInit(usuario="deploy"), etiquetas=()))
    (put,) = m.puts_config(100)
    assert put == {"ciuser": "deploy"}


def test_ca_b1_17_3_nunca_se_escribe_cloudinit_ni_se_lee_cloudinit_dump():
    """CA-B1.17.3: ni ``PUT …/cloudinit`` ni ``GET …/cloudinit/dump`` en ningún caso."""
    m = MundoB()
    m.lote(3, ci_completa(Secreto(CENTINELA), serie=True), encender=True)
    assert all("cloudinit" not in c.ruta for c in m.cl.llamadas)


def test_ca_b1_17_4_con_lock_clone_persistente_no_se_emite_ningun_put():
    """CA-B1.17.4: agotada la espera del ``lock: clone``, no hay PUT de cloud-init ni de nada."""
    m = MundoB()
    m.cl.bloqueo_clon = {100}
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), encender=True))
    assert r.desenlace == Desenlace.TIEMPO_AGOTADO
    assert m.puts_config(100) == []
    assert m.escrituras(100) == ["clone"]  # ni PUT ni resize ni start


# --- CA-B0.2.3: plantilla sin unidad cloud-init ---------------------------------------------------


def _mundo_sin_unidad(**kw):
    return MundoB(plantillas={9000: ("base", config_plantilla(unidad=None))}, **kw)


def test_ca_b0_2_3_clon_sin_unidad_no_emite_ningun_put_con_claves_de_cloudinit():
    """CA-B0.2.3: ni ``ci*``/``ipconfigN``/``cicustom``/``agent`` ni la contraseña."""
    m = _mundo_sin_unidad()
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), encender=True))
    assert not any(_es_put_ci(p) or "cipassword" in p for p in m.puts_config(100))
    assert r.desenlace == Desenlace.PARCIAL
    assert "ajuste_pendiente:cloudinit" in r.avisos
    assert r.error is not None and r.error.codigo == CodigoError.CLOUDINIT_SIN_UNIDAD
    assert "start" not in m.escrituras(100)  # no se enciende (RF-B0.7)


def test_ca_b0_2_3_la_contrasena_queda_pendiente_sin_enviarse_si_no_hay_unidad():
    m = _mundo_sin_unidad()
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA))))
    assert "ajuste_pendiente:contrasena" in r.avisos
    assert not any("cipassword" in p for p in m.puts_config(100))


def test_ca_b0_2_3_los_ajustes_de_0_6_0_se_aplican_aunque_falte_la_unidad():
    """El PUT de ajustes (etiquetas) sigue su camino: solo cloud-init queda pendiente."""
    m = _mundo_sin_unidad()
    m.crear(m.cfg(ci(), ajustes=AjustesClon(cores=4)))
    puts = m.puts_config(100)
    assert len(puts) == 1 and "cores" in puts[0] and "tags" in puts[0]


def test_ca_b0_2_3_una_unidad_en_otro_bus_tambien_se_detecta():
    """R-B7: la unidad puede estar en cualquier bus (aquí ``scsi5``): se envía como siempre."""
    m = MundoB(plantillas={9000: ("base", config_plantilla(unidad="scsi5"))})
    r = m.crear(m.cfg(ci(), etiquetas=()))
    assert r.desenlace == Desenlace.OK
    assert m.escrituras(100) == ["clone", "ci"]


# --- RF-B0.7: atomicidad por MV -------------------------------------------------------------------


def test_ca_b0_7_1_un_403_en_el_put_de_cloudinit_deja_parcial_sin_encender(rsps):
    """CA-B0.7.1 (una MV): PARCIAL, sin ``status/start``, el error nombra privilegio y ruta."""
    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "ciuser", Http(403, "Permission check failed (/vms/100, VM.Config.Cloudinit)"))
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert "start" not in m.escrituras(100)
    assert r.error is not None and r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "VM.Config.Cloudinit"
    assert r.error.params["ruta"] == "/vms/100"
    assert r.error.params["ajuste"] == "cloudinit"
    assert "ajuste_pendiente:cloudinit" in r.avisos
    assert "encendido_omitido" in r.avisos


def test_ca_b0_7_1_tras_fallar_cloudinit_la_contrasena_y_el_resize_no_se_intentan(rsps):
    """RF-B0.7 / DT-B7: el fallo de un paso deja ese y los siguientes como pendientes."""
    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "ciuser", Http(403, "Permission check failed (/vms/100, VM.Config.Cloudinit)"))
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), ajustes=AjustesClon(disco_gib=64)))
    assert m.escrituras(100) == ["clone", "ajustes", "ci"]
    assert set(r.avisos) >= {"ajuste_pendiente:cloudinit", "ajuste_pendiente:contrasena",
                             "ajuste_pendiente:disco"}  # fmt: skip


def test_ca_b0_7_1_las_demas_mvs_siguen_y_el_lote_no_se_pausa_por_un_403_de_cloudinit(rsps):
    """CA-B0.7.1 (lote) y §0: un 403 de cloud-init en 8.x nombra ``VM.Config.Network``, un
    privilegio de escritura; aun así NO pausa el lote: la MV queda PARCIAL y las demás siguen."""
    m = MundoB(version=V_84, privilegios=PRIVS_B_8X, rsps=rsps)
    fallar_put(
        m.cl,
        "ciuser",
        Http(403, "Permission check failed (/vms/100, VM.Config.Network)"),
        vmid=100,
    )
    plan = m.planificar(m.definicion(3, ci(), encender=True))
    assert not plan.bloqueado, plan.problemas
    control = ControlAutomatico("suspender")
    libro = m.ejecutar(plan, control)
    estados = m.estados(libro)
    assert estados == {100: EstadoMV.PARCIAL, 101: EstadoMV.OK, 102: EstadoMV.OK}
    assert control.pausas == []
    assert "start" not in m.escrituras(100)
    assert m.escrituras(101)[-1] == "start" and m.escrituras(102)[-1] == "start"
    assert libro.entrada(100).error.params["privilegio"] == "VM.Config.Network"


def test_ca_b0_7_1_con_el_privilegio_propio_de_cloudinit_el_lote_tampoco_se_pausa(rsps):
    """Misma situación nombrando ``VM.Config.Cloudinit`` (9.x): las demás MVs siguen."""
    m = MundoB(rsps=rsps)
    fallar_put(
        m.cl,
        "ciuser",
        Http(403, "Permission check failed (/vms/100, VM.Config.Cloudinit)"),
        vmid=100,
    )
    plan = m.planificar(m.definicion(3, ci(), encender=True))
    control = ControlAutomatico("suspender")
    libro = m.ejecutar(plan, control)
    assert m.estados(libro) == {100: EstadoMV.PARCIAL, 101: EstadoMV.OK, 102: EstadoMV.OK}
    assert control.pausas == []
    assert "start" not in m.escrituras(100)
    assert libro.entrada(100).error.params["privilegio"] == "VM.Config.Cloudinit"


def test_ca_b0_7_1_el_403_de_otro_privilegio_del_lote_si_sigue_pausando():
    """La excepción es solo para los pasos B: un 403 de ``VM.Clone`` pausa como en 0.6.0."""
    m = MundoB()
    m.cl.regla("POST", r"/clone$", error_http(403, "Permission check failed (/vms/9000, VM.Clone)"))
    control = ControlAutomatico("suspender")
    m.ejecutar(m.planificar(m.definicion(3, ci())), control)
    assert len(control.pausas) == 1


def test_ca_b0_7_2_si_falla_la_contrasena_y_cloudinit_fue_bien_el_informe_las_distingue():
    """CA-B0.7.2: ``cloudinit`` aplicado y solo ``contrasena`` pendiente; no se enciende."""
    m = MundoB()
    fallar_put(m.cl, "cipassword", error_http(500, "no se pudo guardar"))
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    avisos_ajuste = [a for a in r.avisos if a.startswith("ajuste_pendiente")]
    assert avisos_ajuste == ["ajuste_pendiente:contrasena"]
    assert "ci" in m.escrituras(100) and "start" not in m.escrituras(100)
    assert r.error is not None and r.error.params["ajuste"] == "contrasena"
    assert m.cl.vms[100]["config"]["ciuser"] == "deploy"  # lo de cloud-init quedó aplicado


# --- CA-B1.4.7, CA-B1.17.5, CA-B1.17.7: traducción de errores del servidor ------------------------


def test_ca_b1_4_7_un_500_de_clave_ssh_deja_la_mv_parcial_y_conserva_la_causa(rsps):
    """CA-B1.4.7: la MV queda PARCIAL; el error conserva que la causa son las claves SSH."""
    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "sshkeys", Http(500, "SSH public key validation error"))
    r = m.crear(m.cfg(ci(), encender=True))
    assert r.desenlace == Desenlace.PARCIAL
    assert "ajuste_pendiente:cloudinit" in r.avisos and "start" not in m.escrituras(100)
    assert r.error is not None
    causa = r.error.params.get("causa", "")
    assert (
        causa == CodigoError.CLAVE_SSH_RECHAZADA
        or r.error.codigo == CodigoError.CLAVE_SSH_RECHAZADA
    )


def test_ca_b1_4_7_el_mensaje_que_ve_el_usuario_es_el_de_las_claves_ssh(rsps):
    from proxlaunch.interfaz.textos import texto_error

    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "sshkeys", Http(500, "SSH public key validation error"))
    r = m.crear(m.cfg(ci()))
    assert "Proxmox rechazó una de las claves SSH" in texto_error(r.error)


def test_ca_b1_4_7_el_traductor_da_el_codigo_y_el_texto_de_las_claves_ssh():
    from proxlaunch.interfaz.textos import texto_error

    e = error_http(500, "SSH public key validation error")
    assert e.codigo == CodigoError.CLAVE_SSH_RECHAZADA
    assert texto_error(e) == (
        "Proxmox rechazó una de las claves SSH. Revisa que sean claves públicas completas."
    )


def test_ca_b1_17_5_un_400_de_ipconfig_nombra_el_parametro_y_la_tarjeta(rsps):
    """CA-B1.17.5: el error del servidor por ``ipconfig0`` identifica el parámetro (y con él
    la tarjeta 0); la MV queda PARCIAL con el paso cloud-init pendiente."""
    m = MundoB(rsps=rsps)
    cuerpo = {
        "data": None,
        "message": "Parameter verification failed.",
        "errors": {"ipconfig0": "invalid format - format error"},
    }
    fallar_put(m.cl, "ipconfig0", Http(400, cuerpo=cuerpo))
    cfg = m.cfg(ci(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.50/24"),)))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL and "ajuste_pendiente:cloudinit" in r.avisos
    assert r.error is not None
    assert r.error.params.get("campo") == "ipconfig0"
    assert r.error.params["ajuste"] == "cloudinit"


def test_ca_b1_17_7_el_403_de_9_x_nombra_el_privilegio_y_la_ruta_de_la_mv(rsps):
    """CA-B1.17.7: sin ``VM.Config.Cloudinit`` en 9.x el mensaje nombra privilegio y /vms/<vmid>."""
    from proxlaunch.interfaz.textos import texto_error

    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "ciuser", Http(403, "Permission check failed (/vms/100, VM.Config.Cloudinit)"))
    r = m.crear(m.cfg(ci()))
    texto = texto_error(r.error)
    assert "VM.Config.Cloudinit" in texto and "/vms/100" in texto


def test_ca_b1_17_7_un_403_sin_privilegio_en_el_texto_infiere_el_de_la_version(rsps):
    """Un 403 sin nombre se completa con el privilegio propio y la ruta de la MV."""
    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "ciuser", Http(403, "Forbidden"))
    r = m.crear(m.cfg(ci()))
    assert r.error.params["privilegio"] == "VM.Config.Cloudinit"
    assert r.error.params["ruta"] == "/vms/100" and r.error.params.get("inferido") == "1"


def test_cl_b13_un_snippet_que_desaparece_deja_la_mv_parcial_sin_encender(rsps):
    """CL-B13: el PUT falla (500 «is not in the snippets directory»): PARCIAL, sin start."""
    m = MundoB(rsps=rsps)
    volid = "snip:snippets/a.yaml"
    fallar_put(m.cl, "cicustom", Http(500, f"volume '{volid}' is not in the snippets directory"))
    cfg = m.cfg(ConfigCloudInit(snippets=SnippetsCloudInit(vendor=volid)), encender=True)
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert "start" not in m.escrituras(100)
    assert r.error is not None and r.error.params.get("ajuste") == "cloudinit"
    assert r.error.params.get("causa") == CodigoError.SNIPPET_NO_ENCONTRADO
    assert r.error.params.get("snippet") == volid


# --- RF-B1.6: contraseña --------------------------------------------------------------------------


def test_ca_b1_6_7_cada_mv_recibe_su_propio_put_y_el_fallo_de_una_no_afecta_a_las_demas(rsps):
    """CA-B1.6.7: un PUT de contraseña por MV (no se agrupan); la 101 falla y las demás siguen."""
    m = MundoB(rsps=rsps)
    fallar_put(m.cl, "cipassword", Http(500, "fallo de prueba"), vmid=101)
    plan, libro = m.lote(3, ci(contrasena=Secreto(CENTINELA)), encender=True)
    assert m.estados(libro) == {100: EstadoMV.OK, 101: EstadoMV.PARCIAL, 102: EstadoMV.OK}
    por_mv = {v: [b for vv, b in m.cl.puts_crudos if vv == v] for v in (100, 101, 102)}
    for v, cuerpos in por_mv.items():
        con_pw = [b for b in cuerpos if b.startswith(b"cipassword=")]
        assert len(con_pw) == 1, (v, cuerpos)  # exactamente uno por MV
        assert b"&" not in con_pw[0]  # solo ese parámetro
    assert "start" in m.escrituras(100) and "start" in m.escrituras(102)
    assert "start" not in m.escrituras(101)


def test_ca_b1_6_8_el_servidor_devuelve_la_contrasena_enmascarada_y_la_app_no_la_usa():
    """CA-B1.6.8: el ``GET config`` posterior la lee como ``**********``; la app nunca la usa:
    reintentar sin lista de pendientes no la reenvía ni cambia nada."""
    m = MundoB()
    cfg = m.cfg(ci(contrasena=Secreto(CENTINELA)))
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.OK
    assert m.cl.vms[100]["config"]["cipassword"] == "**********"
    antes = len(m.cl.llamadas_a("PUT"))
    r2 = m.reintentar(cfg, None)
    assert len(m.cl.llamadas_a("PUT")) == antes  # nada que reenviar
    assert r2.desenlace == Desenlace.OK
    assert CENTINELA not in repr(r2) and "**********" not in repr(r2)


# --- Contraseña olvidada (decisión del orquestador) -----------------------------------------------


def test_qa_m5_contrasena_olvidada_antes_de_crear_es_error_de_validacion_sin_escribir_nada():
    """Un ``Secreto`` olvidado antes de crear no se lanza (V-B40): la validación del plan da
    error y no se envía nada al servidor; antes quedaba PARCIAL con la contraseña sin escribir."""
    m = MundoB()
    secreto = Secreto(CENTINELA)
    cfg = m.cfg(ci(contrasena=secreto), encender=True)
    secreto.olvidar()
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.ERROR
    assert r.error is not None and r.error.codigo == CodigoError.PARAMETRO_INVALIDO
    assert r.error.params.get("regla") == "V-B40"
    assert m.escrituras(100) == []


def test_qa_m5_con_solo_la_contrasena_olvidada_tampoco_se_lanza():
    """Mismo caso cuando la contraseña es lo único que pedía cloud-init."""
    m = MundoB()
    secreto = Secreto(CENTINELA)
    cfg = m.cfg(ConfigCloudInit(contrasena=secreto))
    secreto.olvidar()
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.ERROR
    assert r.error is not None and r.error.params.get("regla") == "V-B40"
    assert m.escrituras(100) == []


def test_el_secreto_del_cuerpo_de_un_error_del_servidor_sale_enmascarado(rsps):
    """CA-B0.8.1 (parte de creación): el eco del cuerpo en el error no filtra la contraseña."""
    m = MundoB(rsps=rsps)
    m.cl.eco_put = {"cipassword"}
    r = m.crear(m.cfg(ci(contrasena=Secreto(CENTINELA))))
    assert r.desenlace == Desenlace.PARCIAL and r.error is not None
    assert CENTINELA not in r.error.detalle_tecnico
    assert "cipassword" in r.error.detalle_tecnico  # el eco llegó, pero enmascarado


# --- CA-B1.17.6: Reintentar ajustes ---------------------------------------------------------------


def test_ca_b1_17_6_el_reintento_repite_solo_los_put_que_faltaban():
    """Falla la contraseña tras aplicar cloud-init: el reintento solo reenvía la contraseña."""
    m = MundoB()
    cfg = m.cfg(ci(contrasena=Secreto(CENTINELA)), etiquetas=())
    regla = fallar_put(m.cl, "cipassword", error_http(500, "fallo de prueba"), veces=1)
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL and m.escrituras(100) == ["clone", "ci", "pw"]
    m.cl.reglas.remove(regla)
    r2 = m.reintentar(cfg, frozenset({"contrasena"}))
    assert r2.desenlace == Desenlace.OK, (r2.desenlace, r2.error)
    assert m.escrituras(100) == ["clone", "ci", "pw", "pw"]  # ni cloud-init ni nada más
    assert m.puts_config(100)[-1] == {"cipassword": CENTINELA}


def test_ca_b1_17_6_si_falto_cloudinit_el_reintento_envia_cloudinit_y_luego_la_contrasena():
    m = MundoB()
    cfg = m.cfg(ci(contrasena=Secreto(CENTINELA)), etiquetas=())
    regla = fallar_put(m.cl, "ciuser", error_http(500, "fallo de prueba"), veces=1)
    r = m.crear(cfg)
    assert set(r.avisos) == {"ajuste_pendiente:cloudinit", "ajuste_pendiente:contrasena"}
    m.cl.reglas.remove(regla)
    r2 = m.reintentar(cfg, frozenset({"cloudinit", "contrasena"}))
    assert r2.desenlace == Desenlace.OK
    assert m.escrituras(100) == ["clone", "ci", "ci", "pw"]


def test_ca_b1_17_6_con_la_contrasena_olvidada_pide_volver_a_escribirla():
    """Si el ``Secreto`` ya no está en memoria no se reenvía: CONTRASENA_OLVIDADA."""
    m = MundoB()
    secreto = Secreto(CENTINELA)
    cfg = m.cfg(ci(contrasena=secreto), etiquetas=())
    regla = fallar_put(m.cl, "cipassword", error_http(500, "fallo de prueba"), veces=1)
    m.crear(cfg)
    m.cl.reglas.remove(regla)
    secreto.olvidar()
    r2 = m.reintentar(cfg, frozenset({"contrasena"}))
    assert r2.desenlace == Desenlace.PARCIAL
    assert "ajuste_pendiente:contrasena" in r2.avisos
    assert r2.error is not None and r2.error.codigo == CodigoError.CONTRASENA_OLVIDADA
    assert m.escrituras(100) == ["clone", "ci", "pw"]  # no se envió nada más


def test_ca_b1_17_6_el_reintento_nunca_envia_un_post_de_creacion():
    m = MundoB()
    cfg = m.cfg(ci(), etiquetas=())
    m.crear(cfg)
    clones = m.cl.clones[100]
    m.reintentar(cfg, frozenset({"cloudinit"}))
    assert m.cl.clones[100] == clones == 1


def test_ca_b1_17_6_reintentar_ajustes_de_un_lote_repite_solo_lo_pendiente_de_esa_mv(rsps):
    """Nivel lote (``lote.ajustes``): la MV 101 quedó PARCIAL por la contraseña; se reintenta
    solo ella y solo su contraseña."""
    m = MundoB(rsps=rsps)
    regla = fallar_put(m.cl, "cipassword", Http(500, "fallo de prueba"), vmid=101, veces=1)
    plan = m.planificar(m.definicion(3, ci(contrasena=Secreto(CENTINELA))))
    libro = m.ejecutar(plan)
    assert m.estados(libro)[101] == EstadoMV.PARCIAL
    assert ajustes_pendientes(libro.entrada(101)) == frozenset({"contrasena"})
    m.cl.reglas.remove(regla)
    antes = len(m.cl.puts_crudos)
    reintentar_ajustes(libro, [101], m.sesion, m.reloj, m.inv, m.banco.observador, ControlLote())
    nuevos = m.cl.puts_crudos[antes:]
    assert [v for v, _ in nuevos] == [101]
    assert nuevos[0][1].startswith(b"cipassword=")
    assert m.estados(libro)[101] == EstadoMV.OK


def test_ca_b1_17_6_reintentar_ajustes_de_un_lote_con_la_contrasena_olvidada_sigue_parcial(rsps):
    m = MundoB(rsps=rsps)
    secreto = Secreto(CENTINELA)
    regla = fallar_put(m.cl, "cipassword", Http(500, "fallo de prueba"), vmid=101, veces=1)
    plan = m.planificar(m.definicion(3, ci(contrasena=secreto)))
    libro = m.ejecutar(plan)
    m.cl.reglas.remove(regla)
    secreto.olvidar()
    antes = len(m.cl.puts_crudos)
    reintentar_ajustes(libro, [101], m.sesion, m.reloj, m.inv, m.banco.observador, ControlLote())
    assert len(m.cl.puts_crudos) == antes  # no se envió nada: no hay qué enviar
    entrada = libro.entrada(101)
    assert entrada.estado == EstadoMV.PARCIAL
    assert entrada.error is not None and entrada.error.codigo == CodigoError.CONTRASENA_OLVIDADA


def test_ca_b1_17_6_un_lote_con_cloudinit_en_todas_las_mvs_las_deja_ok_y_aplicadas():
    """Camino feliz de lote: cada MV recibe clone, ajustes (etiqueta del lote), cloud-init,
    contraseña y start."""
    m = MundoB()
    plan, libro = m.lote(3, ci_completa(Secreto(CENTINELA), serie=True), encender=True)
    assert set(m.estados(libro).values()) == {EstadoMV.OK}
    for v in (100, 101, 102):
        assert m.escrituras(v) == ["clone", "ajustes", "ci", "pw", "start"]


def test_clave_publica_de_ejemplo_va_codificada_una_sola_vez_en_el_cuerpo(rsps):
    """DT-B4/R-B1: el cuerpo en bruto lleva ``sshkeys`` con UN nivel de codificación del valor
    (el del formulario) sobre el ya codificado por la app; decodificado una vez es ``quote``."""
    from urllib.parse import parse_qs, quote

    m = MundoB(rsps=rsps)
    m.crear(m.cfg(ConfigCloudInit(claves=(CLAVE,)), etiquetas=()))
    (cuerpo,) = [b for v, b in m.cl.puts_crudos if v == 100]
    valor = parse_qs(cuerpo.decode())["sshkeys"][0]
    assert valor == quote(CLAVE, safe="")
    assert "%2520" in cuerpo.decode()  # el espacio de la clave: %20 codificado otra vez = %2520


@pytest.mark.parametrize("version", [V_84, V_92])
def test_el_flujo_completo_es_el_mismo_en_8_x_y_9_x(version):
    m = MundoB(version=version, privilegios=PRIVS_B_8X if version == V_84 else None)
    r = m.crear(m.cfg(ci_completa(Secreto(CENTINELA)), etiquetas=()))
    assert r.desenlace == Desenlace.OK
    assert m.escrituras(100) == ["clone", "ci", "pw"]


# --- Contrato de los dobles de la fase B (``apoyo_lote.Cluster``) --------------------------


def test_doble_agente_responde_el_guion_por_vmid_y_repite_la_ultima_respuesta():
    from proxlaunch.nucleo.agente.clasificacion import Clase, clasificar_error
    from proxlaunch.nucleo.errores import ErrorProxLaunch

    from .apoyo_lote import respuesta_agente

    m = MundoB()
    m.cl.agregar_vm(100, "pve1", "x")
    ok = respuesta_agente(("eth0", "AA:BB:CC:DD:EE:FF", ("10.0.0.5",)))
    m.cl.guion_agente(100, error_http(500, "QEMU guest agent is not running"), ok)
    cliente = m.sesion.cliente
    with pytest.raises(ErrorProxLaunch) as info:
        cliente.interfaces_agente("pve1", 100)
    assert info.value.codigo == CodigoError.AGENTE_NO_RESPONDE
    assert clasificar_error(info.value) == Clase.TODAVIA_NO
    assert cliente.interfaces_agente("pve1", 100) == ok
    assert cliente.interfaces_agente("pve1", 100) == ok  # la última se repite
    assert m.cl.sondeos_agente[100] == 3 and m.cl.llamadas_agente == [("GET", 100)] * 3


def test_doble_agente_sin_guion_dice_que_el_agente_no_corre_y_atiende_get_y_post():
    from proxlaunch.nucleo.errores import ErrorProxLaunch

    m = MundoB()
    for metodo in ("GET", "POST"):
        with pytest.raises(ErrorProxLaunch) as info:
            m.cl.atender(metodo, "/nodes/pve1/qemu/7/agent/network-get-interfaces")
        assert info.value.codigo == CodigoError.AGENTE_NO_RESPONDE
    assert m.cl.llamadas_agente == [("GET", 7), ("POST", 7)]


def test_doble_post_template_convierte_la_mv_y_su_tarea_termina_bien():
    m = MundoB()
    m.crear(m.cfg(None))
    upid = m.sesion.cliente.convertir_en_plantilla("pve1", 100)
    assert upid is not None and ":qmtemplate:100:" in upid
    assert m.cl.conversiones[100] == 1 and m.cl.vms[100]["config"]["template"] == 1
    assert m.sesion.cliente.estado_tarea("pve1", upid).exitstatus == "OK"


def test_doble_snippets_lista_por_nodo_y_almacenamiento_con_tamano_y_cuenta_las_consultas():
    m = MundoB(snippets={("pve1", "snip"): [("snip:snippets/a.yaml", 123)]})
    (sn,) = m.sesion.cliente.contenido_snippets("pve1", "snip")
    assert (sn.volid, sn.nombre, sn.tamano, sn.admitido) == (
        "snip:snippets/a.yaml",
        "a.yaml",
        123,
        True,
    )
    assert m.sesion.cliente.contenido_snippets("pve2", "snip") == []
    assert m.cl.listados_snippets == [("pve1", "snip"), ("pve2", "snip")]


def test_doble_put_config_guarda_el_cuerpo_en_bruto_y_el_modo_eco_lo_repite_en_el_error(rsps):
    m = MundoB(rsps=rsps)
    m.cl.agregar_vm(100, "pve1", "x")
    cliente = m.sesion.cliente
    cliente.configurar_vm("pve1", 100, {"ciuser": "ana lopez", "nameserver": "1.1.1.1 9.9.9.9"})
    assert m.cl.puts_crudos == [(100, b"ciuser=ana+lopez&nameserver=1.1.1.1+9.9.9.9")]
    m.cl.eco_put = {"ciuser"}
    with pytest.raises(Exception) as info:
        cliente.configurar_vm("pve1", 100, {"ciuser": "pepe"})
    assert "ciuser=pepe" in info.value.detalle_tecnico  # el eco llegó
    cliente.configurar_vm("pve1", 100, {"nameserver": "8.8.8.8"})  # sin esa clave no hay eco
    assert len(m.cl.puts_crudos) == 3


# --- DT-B7: qué pasa cuando falla cada paso ---------------------------------------------


def test_dt_b7_si_falla_el_put_de_ajustes_cloudinit_y_contrasena_quedan_pendientes():
    """§11: el resize se sigue intentando como en 0.6.0; cloud-init y contraseña, no."""
    m = MundoB()
    fallar_put(m.cl, "tags", error_http(500, "fallo de prueba"))
    cfg = m.cfg(ci_completa(Secreto(CENTINELA)), ajustes=AjustesClon(disco_gib=64), encender=True)
    r = m.crear(cfg)
    assert r.desenlace == Desenlace.PARCIAL
    assert m.escrituras(100) == ["clone", "ajustes", "resize"]
    assert {"ajuste_pendiente:etiquetas", "ajuste_pendiente:cloudinit",
            "ajuste_pendiente:contrasena"} <= set(r.avisos)  # fmt: skip
    assert "ajuste_pendiente:disco" not in r.avisos and "start" not in m.escrituras(100)


def test_qa_m2_los_fallos_repetidos_de_cloudinit_no_pausan_el_lote():
    """QA-M2: los errores de los pasos B (``params["ajuste"]``) tampoco cuentan para la racha
    «repetido»: las MVs quedan PARCIAL y el lote sigue sin pausar."""
    m = MundoB()
    fallar_put(m.cl, "ciuser", error_http(500, "fallo de prueba"))
    control = ControlAutomatico("suspender")
    libro = m.ejecutar(m.planificar(m.definicion(8, ci())), control)
    assert control.pausas == []
    assert set(m.estados(libro).values()) == {EstadoMV.PARCIAL}
