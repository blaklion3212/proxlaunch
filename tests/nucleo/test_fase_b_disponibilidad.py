"""Disponibilidad por versión y privilegios de las opciones de la fase B (0.7.0).

Requisitos: RF-B0.3 (CA-B0.3.1 a CA-B0.3.3), RF-B0.4 (CA-B0.4.1 a CA-B0.4.3), CA-B1.2.1 a
CA-B1.2.3, CA-B1.6.5, CA-B3.1.1, CA-B3.1.2, CA-B4.1.4, RF-B5.1 (CA-B5.1.1 a CA-B5.1.4), RF-B5.3
(CA-B5.3.1 a CA-B5.3.4) y CL-B23. La versión se compara solo en ``capacidades.TABLA`` y la
disponibilidad es pura: la interfaz solo la pinta (aquí se comprueba además el texto de motivo).
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.textos import texto_error, texto_estado_opcion
from proxlaunch.nucleo.capacidades import (
    Funcion,
    asistente_plantilla_disponible,
    capacidades_para,
)
from proxlaunch.nucleo.cloudinit.deteccion import info_cloudinit
from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB, disponibilidad_fase_b
from proxlaunch.nucleo.cloudinit.modelos import INFO_DESCONOCIDA, ConfigCloudInit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.origen.permisos import (
    PRIVILEGIOS_OPCIONALES,
    ROL_PROXLAUNCH,
    RUTA_STORAGE_SNIPPETS_DESCONOCIDO,
    estado_privilegio,
    privilegios_agente,
    privilegios_cloudinit,
    privilegios_opcionales,
    privilegios_snippets_8x,
    ruta_almacen_snippets,
)
from proxlaunch.nucleo.plantilla_imagen.disponibilidad import (
    ControlB2,
    disponibilidad_plantilla_imagen,
)
from proxlaunch.nucleo.servicios.conexion import PERMISOS_POR_RUTA

from .apoyo_fase_b_p1 import (
    PRIVS_B_8X,
    PRIVS_B_92,
    MundoB,
    ci,
    config_plantilla,
    permisos_en,
)
from .apoyo_lote import error_http
from .apoyo_mvp4 import inv_origen

SI, NO, AVISO = Disponibilidad.SI, Disponibilidad.NO, Disponibilidad.CON_AVISO


def caps(mayor: int, menor: int, forzada: tuple[int, int] | None = None):
    return capacidades_para(Version(f"{mayor}.{menor}.0", mayor, menor, 0), forzada)


def disp(privilegios, version=(9, 2), info=None, snippets=True, *, ruta_storage=True):
    """``disponibilidad_fase_b`` con los privilegios dados (``None`` = permisos desconocidos).

    Los de ``/storage`` (``Datastore.*``) se conceden en esa ruta; el resto, en ``/``.
    """
    if privilegios is None:
        permisos = None
    else:
        rutas: dict[str, dict[str, int]] = {"/": {}, "/storage": {}}
        for p in privilegios:
            rutas["/storage" if ruta_storage and p.startswith("Datastore.") else "/"][p] = 1
        permisos = PermisosEfectivos(rutas=rutas)
    return disponibilidad_fase_b(permisos, caps(*version), info, snippets)


CON_UNIDAD = info_cloudinit(config_plantilla())
SIN_UNIDAD = info_cloudinit(config_plantilla(unidad=None))
WINDOWS = info_cloudinit(config_plantilla(ostype="win10"))

# privilegios sin ninguno de los de la fase B
BASE = tuple(ROL_PROXLAUNCH)


# --- RF-B0.3 / CA-B0.3.1: sin el privilegio, la opción se deshabilita y se explica ----------------


@pytest.mark.parametrize(
    ("opcion", "version", "concedidos", "falta", "ruta"),
    [
        (OpcionB.CLOUDINIT, (9, 2), (*BASE,), "VM.Config.Cloudinit", "/vms"),
        (OpcionB.CONTRASENA, (9, 2), (*BASE,), "VM.Config.Cloudinit", "/vms"),
        (
            OpcionB.CLOUDINIT,
            (8, 4),
            tuple(p for p in BASE if p != "VM.Config.Network"),
            "VM.Config.Cloudinit",
            "/vms",
        ),  # fmt: skip
        (
            OpcionB.DNS_DOMINIO,
            (9, 2),
            tuple(p for p in BASE if p != "VM.Config.Network"),
            "VM.Config.Cloudinit",
            "/vms",
        ),  # fmt: skip
        (OpcionB.ESPERAR_IP, (8, 4), (*BASE,), "VM.Monitor", "/vms"),
        (OpcionB.ESPERAR_IP, (9, 2), (*BASE,), "VM.GuestAgent.Audit", "/vms"),
        (OpcionB.SNIPPETS, (9, 2), ("VM.Config.Cloudinit",), "Datastore.Audit", "/storage"),
        (
            OpcionB.ACTIVAR_AGENTE,
            (9, 2),
            ("VM.Config.Cloudinit", "VM.Config.Network"),
            "VM.Config.Options",
            "/vms",
        ),  # fmt: skip
    ],
)
def test_ca_b0_3_1_sin_el_privilegio_la_opcion_se_deshabilita_y_la_ayuda_nombra_privilegio_y_ruta(
    opcion, version, concedidos, falta, ruta
):
    est = disp(concedidos, version, CON_UNIDAD)[opcion]
    assert est.disponibilidad == NO, (opcion, est)
    assert est.params["privilegio"] == falta and est.params["ruta"] == ruta
    texto = texto_estado_opcion(est)
    assert falta in texto and ruta in texto


def test_ca_b0_3_1_el_motivo_menciona_el_privilegio_alternativo_cuando_la_version_lo_admite():
    """En 8.x vale ``VM.Config.Network`` en lugar de ``VM.Config.Cloudinit``: la ayuda lo dice."""
    est = disp(tuple(p for p in BASE if p != "VM.Config.Network"), (8, 4), CON_UNIDAD)[
        OpcionB.CLOUDINIT
    ]
    assert est.params["alternativo"] == "VM.Config.Network"
    assert "VM.Config.Network" in texto_estado_opcion(est)


def test_ca_b0_3_1_los_estados_no_ocultan_el_control_siempre_hay_un_estado_por_opcion():
    est = disp(BASE, (9, 2), CON_UNIDAD)
    assert set(est) == set(OpcionB)  # se deshabilita (no se oculta) y se explica


# --- CA-B0.3.2: permisos desconocidos -------------------------------------------------------------


@pytest.mark.parametrize("version", [(8, 0), (8, 4), (9, 0), (9, 2)])
def test_ca_b0_3_2_con_permisos_desconocidos_todo_queda_habilitado(version):
    est = disp(None, version, CON_UNIDAD)
    assert {o: e.disponibilidad for o, e in est.items()} == dict.fromkeys(OpcionB, SI)


def test_ca_b0_3_2_un_403_se_traduce_a_un_mensaje_que_nombra_el_privilegio():
    e = error_http(403, "Permission check failed (/vms/100, VM.Config.Cloudinit)")
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.params["privilegio"] == "VM.Config.Cloudinit" and e.params["ruta"] == "/vms/100"
    assert "VM.Config.Cloudinit" in texto_error(e)


# --- CA-B0.3.3: opción fijada desde un perfil, lote guardado o CSV sin permiso --------------------


def _reglas(plan):
    return {p.regla: p for p in plan.problemas}


def test_ca_b0_3_3_cloudinit_fijado_sin_privilegio_bloquea_la_comprobacion_y_no_se_crea_nada():
    """V-B37: «Comprobar» (planificar) bloquea y la creación directa se rechaza sin escribir."""
    m = MundoB(privilegios=BASE)
    plan = m.planificar(m.definicion(2, ci()))
    assert plan.bloqueado and "V-B37" in _reglas(plan)
    r = m.crear(m.cfg(ci()))
    assert r.desenlace.value == "error"
    assert m.cl.rutas_de_escritura() == []


def test_ca_b0_3_3_esperar_ip_sin_privilegio_del_agente_bloquea_con_v_b63():
    m = MundoB(privilegios=BASE)
    plan = m.planificar(m.definicion(2, None, encender=True, esperar_ip=True))
    assert plan.bloqueado and "V-B63" in _reglas(plan)


def test_ca_b0_3_3_snippets_sin_privilegio_de_almacenamiento_bloquean_con_v_b55():
    from proxlaunch.nucleo.cloudinit.modelos import SnippetsCloudInit

    m = MundoB(privilegios=("VM.Config.Cloudinit", *BASE))
    permisos_sin_storage = tuple(p for p in BASE if p != "Datastore.AllocateSpace")
    m = MundoB(privilegios=("VM.Config.Cloudinit", *permisos_sin_storage))
    plan = m.planificar(
        m.definicion(
            2, ConfigCloudInit(snippets=SnippetsCloudInit(vendor="snip:snippets/agente.yaml"))
        )
    )
    assert plan.bloqueado and "V-B55" in _reglas(plan)


def test_ca_b0_3_3_con_todos_los_privilegios_el_mismo_lote_no_se_bloquea():
    m = MundoB()
    assert not m.planificar(m.definicion(2, ci(), encender=True, esperar_ip=True)).bloqueado


# --- RF-B0.4: versión -----------------------------------------------------------------------------


def test_ca_b0_4_1_el_asistente_de_plantilla_esta_disponible_con_la_minima_8_4():
    """Con la mínima 8.4 (DT-D3) el asistente solo depende de que haya sesión y un import."""
    assert asistente_plantilla_disponible(caps(8, 4))
    assert asistente_plantilla_disponible(caps(9, 2))
    assert not asistente_plantilla_disponible(None)
    inv = inv_origen(version=Version("8.4.0", 8, 4, 0), nodos=("pve1",))
    est = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(8, 4), inv, "pve1")
    assert est[ControlB2.ASISTENTE].disponibilidad == SI


def test_ca_b0_4_2_la_version_forzada_manda_sobre_la_detectada():
    """Servidor real 9.2 con la versión forzada 8.4: el mismo resultado que en un 8.4."""
    forzada = capacidades_para(Version("9.2.1", 9, 2, 1), (8, 4))
    assert forzada.forzada and forzada.version == (8, 4)
    assert asistente_plantilla_disponible(forzada)
    inv = inv_origen(version=Version("9.2.1", 9, 2, 1), nodos=("pve1",))
    est = disponibilidad_plantilla_imagen(inv.catalogo.permisos, forzada, inv, "pve1")
    assert est[ControlB2.ASISTENTE].disponibilidad == SI


def test_ca_b0_4_3_con_8_0_estan_disponibles_cloudinit_agente_y_snippets_con_sus_privilegios():
    est = disp(PRIVS_B_8X, (8, 0), CON_UNIDAD)
    for opcion in (OpcionB.CLOUDINIT, OpcionB.CONTRASENA, OpcionB.ESPERAR_IP, OpcionB.SNIPPETS):
        assert est[opcion].disponibilidad == SI, opcion


@pytest.mark.parametrize(
    ("funcion", "minima"),
    [
        (Funcion.CLOUDINIT, (8, 0)),
        (Funcion.SNIPPETS_CICUSTOM, (8, 0)),
        (Funcion.AGENTE_IP, (8, 0)),
        (Funcion.PRIVILEGIOS_GUEST_AGENT, (9, 0)),
        (Funcion.CLOUDINIT_PRIVILEGIO_INCIERTO, (9, 0)),
        (Funcion.CLOUDINIT_PRIVILEGIO_PROPIO, (9, 2)),
        (Funcion.CICUSTOM_CON_ALLOCATESPACE, (9, 0)),
    ],
)
def test_la_tabla_de_capacidades_registra_cada_funcion_nueva_con_su_version_minima(funcion, minima):
    assert caps(*minima).requisito(funcion) == minima
    assert caps(*minima).tiene(funcion)
    anterior = (minima[0], minima[1] - 1) if minima[1] else (minima[0] - 1, 9)
    assert not caps(*anterior).tiene(funcion)


# --- RF-B1.2: unidad cloud-init en la plantilla ---------------------------------------------------


def test_ca_b1_2_1_con_unidad_la_seccion_esta_habilitada():
    est = disp(PRIVS_B_92, (9, 2), CON_UNIDAD)
    assert est[OpcionB.CLOUDINIT].disponibilidad == SI
    assert (
        est[OpcionB.CONTRASENA].disponibilidad == SI
        and est[OpcionB.DNS_DOMINIO].disponibilidad == SI
    )


def test_ca_b1_2_2_sin_unidad_se_deshabilita_todo_cloudinit_con_el_motivo_de_la_ayuda():
    est = disp(PRIVS_B_92, (9, 2), SIN_UNIDAD)
    for opcion in (OpcionB.CLOUDINIT, OpcionB.CONTRASENA, OpcionB.DNS_DOMINIO, OpcionB.SNIPPETS):
        assert est[opcion].disponibilidad == NO, opcion
    assert est[OpcionB.CLOUDINIT].codigo == CodigoError.CLOUDINIT_SIN_UNIDAD
    assert est[OpcionB.CLOUDINIT].params["motivo"] == "sin_unidad"
    assert "CloudInit Drive" in texto_error(ErrorProxLaunch(CodigoError.CLOUDINIT_SIN_UNIDAD))
    # esperar la IP no depende de cloud-init
    assert est[OpcionB.ESPERAR_IP].disponibilidad == SI


def test_ca_b1_2_2_sin_unidad_la_planificacion_bloquea_con_v_b20_y_no_emite_ningun_put():
    m = MundoB(plantillas={9000: ("base", config_plantilla(unidad=None))})
    plan = m.planificar(m.definicion(3, ci()))
    assert plan.bloqueado
    v20 = [p for p in plan.problemas if p.regla == "V-B20"]
    assert len(v20) == 1 and v20[0].params["plantilla"] == "base"
    assert m.cl.solo_lecturas  # planificar solo lee


def test_ca_b1_2_2_estado_desconocido_se_habilita_con_aviso_v_b20():
    est = disp(PRIVS_B_92, (9, 2), INFO_DESCONOCIDA)
    assert est[OpcionB.CLOUDINIT].disponibilidad == AVISO
    assert est[OpcionB.CLOUDINIT].params["motivo"] == "unidad_desconocida"
    assert disp(PRIVS_B_92, (9, 2), None)[OpcionB.CLOUDINIT].disponibilidad == AVISO


def test_ca_b1_2_3_un_origen_distinto_de_clonar_no_admite_cloudinit_v_b39():
    """La sección solo existe al clonar: con otro origen, tener cloud-init es el error V-B39."""
    from proxlaunch.nucleo.capacidades import Capacidades
    from proxlaunch.nucleo.validacion import validar_vm

    from .apoyo_fase_a import catalogo as cat
    from .apoyo_fase_a import cfg_vm, inv_con

    cfg = cfg_vm(cloudinit=ci())
    problemas = validar_vm(cfg, inv_con(cat()), Capacidades((9, 2), False))
    assert [p.codigo for p in problemas if p.codigo == "V-B39"] == ["V-B39"]


# --- CA-B1.6.5: Windows ---------------------------------------------------------------------------


def test_ca_b1_6_5_con_windows_la_contrasena_se_deshabilita_y_lo_demas_sigue():
    est = disp(PRIVS_B_92, (9, 2), WINDOWS)
    assert est[OpcionB.CONTRASENA].disponibilidad == NO
    assert est[OpcionB.CONTRASENA].params["motivo"] == "windows"
    assert "Con Windows, Proxmox guardaría la contraseña sin cifrar; no se permite" in (
        texto_estado_opcion(est[OpcionB.CONTRASENA])
    )
    assert est[OpcionB.CLOUDINIT].disponibilidad == SI
    assert est[OpcionB.DNS_DOMINIO].disponibilidad == SI


def test_ca_b1_6_5_con_windows_la_planificacion_avisa_y_con_contrasena_bloquea():
    from proxlaunch.nucleo.secreto import Secreto

    m = MundoB(plantillas={9000: ("base", config_plantilla(ostype="win10"))})
    con_aviso = m.planificar(m.definicion(1, ci()))
    assert not con_aviso.bloqueado and "V-B35" in _reglas(con_aviso)
    con_pw = m.planificar(m.definicion(1, ci(contrasena=Secreto("S3cr3t-Prueba!"))))
    assert con_pw.bloqueado and "V-B25" in _reglas(con_pw)


# --- B3: casilla «Esperar la IP» ------------------------------------------------------------------


def test_ca_b3_1_1_esperar_la_ip_sin_encender_es_un_error_de_validacion_v_b60():
    from proxlaunch.nucleo.agente.validacion import validar_espera_ip

    from .apoyo_fase_a import cfg_vm

    assert [p.codigo for p in validar_espera_ip(cfg_vm(esperar_ip=True, encender=False), caps(9, 2))
            if p.codigo == "V-B60"] == ["V-B60"]  # fmt: skip
    assert not [p for p in validar_espera_ip(cfg_vm(esperar_ip=True, encender=True), caps(9, 2))
                if p.codigo == "V-B60"]  # fmt: skip
    assert validar_espera_ip(cfg_vm(esperar_ip=False, encender=False), caps(9, 2)) == []


def test_ca_b3_1_2_habilitada_en_8_4_con_monitor_y_en_9_2_con_guestagent_audit():
    assert disp(PRIVS_B_8X, (8, 4), CON_UNIDAD)[OpcionB.ESPERAR_IP].disponibilidad == SI
    assert disp(PRIVS_B_92, (9, 2), CON_UNIDAD)[OpcionB.ESPERAR_IP].disponibilidad == SI


def test_ca_b3_1_2_en_9_2_con_solo_monitor_se_deshabilita_y_nombra_guestagent_audit():
    est = disp((*BASE, "VM.Monitor"), (9, 2), CON_UNIDAD)[OpcionB.ESPERAR_IP]
    assert est.disponibilidad == NO and est.params["privilegio"] == "VM.GuestAgent.Audit"
    assert "VM.GuestAgent.Audit" in texto_estado_opcion(est)


def test_ca_b3_1_2_en_8_4_con_solo_guestagent_se_deshabilita_y_nombra_monitor():
    est = disp((*BASE, "VM.GuestAgent.Audit"), (8, 4), CON_UNIDAD)[OpcionB.ESPERAR_IP]
    assert est.disponibilidad == NO and est.params["privilegio"] == "VM.Monitor"


def test_ca_b3_1_2_en_9_x_basta_guestagent_unrestricted():
    est = disp((*BASE, "VM.GuestAgent.Unrestricted"), (9, 2), CON_UNIDAD)[OpcionB.ESPERAR_IP]
    assert est.disponibilidad == SI


# --- B4: almacenamiento con contenido «snippets» --------------------------------------------------


def test_ca_b4_1_4_sin_almacenamiento_con_snippets_la_seccion_se_deshabilita():
    est = disp(PRIVS_B_92, (9, 2), CON_UNIDAD, snippets=False)[OpcionB.SNIPPETS]
    assert est.disponibilidad == NO and est.params["motivo"] == "sin_storage_snippets"
    assert "Fragmentos" in texto_estado_opcion(est)
    assert (
        disp(PRIVS_B_92, (9, 2), CON_UNIDAD, snippets=True)[OpcionB.SNIPPETS].disponibilidad == SI
    )


def test_ca_b4_1_4_sin_snippets_el_resto_de_cloudinit_sigue_habilitado():
    est = disp(PRIVS_B_92, (9, 2), CON_UNIDAD, snippets=False)
    assert est[OpcionB.CLOUDINIT].disponibilidad == SI


def test_ca_b4_1_4_el_inventario_planificado_sin_storage_snippets_da_v_b50():
    from proxlaunch.nucleo.cloudinit.modelos import SnippetsCloudInit

    m = MundoB()
    m.inv.storages_todos = {n: tuple(s for s in ss if "snippets" not in s.contenido)
                            for n, ss in m.inv.storages_todos.items()}  # fmt: skip
    plan = m.planificar(
        m.definicion(1, ConfigCloudInit(snippets=SnippetsCloudInit(vendor="snip:snippets/a.yaml")))
    )
    assert plan.bloqueado and "V-B50" in _reglas(plan)


# --- RF-B5.1: privilegios opcionales --------------------------------------------------------------


def test_ca_b5_1_1_el_rol_sigue_con_14_y_ningun_privilegio_nuevo_esta_en_el_el():
    assert len(ROL_PROXLAUNCH) == 14
    nuevos = {"VM.Config.Cloudinit", "VM.Monitor", "VM.GuestAgent.Audit",
              "VM.GuestAgent.Unrestricted", "Datastore.Allocate", "Datastore.Audit"}  # fmt: skip
    assert not nuevos & set(ROL_PROXLAUNCH)
    assert dict(PRIVILEGIOS_OPCIONALES) == {"VM.PowerMgmt": "/vms", "Pool.Audit": "/pool"}


@pytest.mark.parametrize(("version", "con", "sin"), [
    ((8, 0), "VM.Monitor", "VM.GuestAgent.Audit"),
    ((8, 4), "VM.Monitor", "VM.GuestAgent.Audit"),
    ((9, 0), "VM.GuestAgent.Audit", "VM.Monitor"),
    ((9, 2), "VM.GuestAgent.Audit", "VM.Monitor"),
])  # fmt: skip
def test_ca_b5_1_2_los_opcionales_efectivos_dependen_de_la_version(version, con, sin):
    nombres = {o.privilegio for o in privilegios_opcionales(caps(*version))}
    assert con in nombres and sin not in nombres
    assert "VM.Config.Cloudinit" in nombres
    assert {"VM.PowerMgmt", "Pool.Audit"} <= nombres  # los de la fase A se conservan


def test_ca_b5_1_2_datastore_allocate_solo_antes_de_9_0_y_no_verificado():
    antes = {o.privilegio: o for o in privilegios_opcionales(caps(8, 4))}
    despues = {o.privilegio: o for o in privilegios_opcionales(caps(9, 2))}
    assert antes["Datastore.Allocate"].no_verificado
    assert antes["Datastore.Allocate"].ruta == RUTA_STORAGE_SNIPPETS_DESCONOCIDO  # B3: no /storage
    assert "Datastore.Allocate" not in despues and "Datastore.AllocateSpace" not in despues


def test_b3_en_8x_los_privilegios_de_snippets_van_sobre_el_almacen_de_snippets():
    """B3: ``AllocateSpace`` primero y ``Allocate`` como alternativa no verificada, ambos sobre
    ``/storage/<almacén>`` (nunca sobre todo ``/storage``)."""
    lista = privilegios_opcionales(caps(8, 4), "snips")
    snippets = [o for o in lista if o.privilegio.startswith("Datastore.")]
    assert [(o.privilegio, o.ruta, o.no_verificado) for o in snippets] == [
        ("Datastore.AllocateSpace", "/storage/snips", False),
        ("Datastore.Allocate", "/storage/snips", True),
    ]
    assert ruta_almacen_snippets("snips") == "/storage/snips"
    assert privilegios_snippets_8x("snips") == tuple(snippets)
    assert not [
        o for o in privilegios_opcionales(caps(9, 2), "snips") if o.ruta == "/storage/snips"
    ]


def test_ca_b5_1_2_sin_capacidades_solo_estan_los_de_la_fase_a():
    assert [(o.privilegio, o.ruta) for o in privilegios_opcionales(None)] == list(
        PRIVILEGIOS_OPCIONALES
    )


def test_ca_b5_1_2_la_version_forzada_decide_los_privilegios_que_se_presentan():
    """CL-B23: 8.4 forzada sobre un 9.2: se presentan los de 8.x."""
    forzada = capacidades_para(Version("9.2.1", 9, 2, 1), (8, 4))
    nombres = {o.privilegio for o in privilegios_opcionales(forzada)}
    assert "VM.Monitor" in nombres and "VM.GuestAgent.Audit" not in nombres
    assert privilegios_agente(forzada) == ("VM.Monitor",)
    assert privilegios_cloudinit(forzada) == ("VM.Config.Cloudinit", "VM.Config.Network")


def test_ca_b5_1_3_con_el_rol_de_0_6_0_no_hay_avisos_nuevos_y_se_crea_como_antes():
    """CA-B5.1.3: los privilegios nuevos no están entre los mínimos que avisa la conexión."""
    todos = {p for privs in PERMISOS_POR_RUTA.values() for p in privs}
    assert not {"VM.Config.Cloudinit", "VM.Monitor", "VM.GuestAgent.Audit"} & todos
    m = MundoB(privilegios=BASE)
    plan = m.planificar(m.definicion(3, None))
    assert not plan.bloqueado and not [p for p in plan.problemas if p.regla.startswith("V-B")]
    libro = m.ejecutar(plan)
    assert {e.estado.value for e in libro.instantanea()} == {"ok"}


def test_ca_b5_1_3_con_el_rol_de_0_6_0_en_8_x_cloudinit_ya_funciona_por_network():
    est = disp(BASE, (8, 4), CON_UNIDAD)
    assert est[OpcionB.CLOUDINIT].disponibilidad == SI  # VM.Config.Network está en el rol


def test_ca_b5_1_4_un_privilegio_con_propagate_cero_en_vms_no_se_concede_a_vms_id():
    sin = PermisosEfectivos(rutas={"/vms": {"VM.GuestAgent.Audit": 0}})
    con = PermisosEfectivos(rutas={"/vms": {"VM.GuestAgent.Audit": 1}})
    assert estado_privilegio(sin, "VM.GuestAgent.Audit", "/vms/100") is False
    assert estado_privilegio(con, "VM.GuestAgent.Audit", "/vms/100") is True
    assert estado_privilegio(None, "VM.GuestAgent.Audit", "/vms/100") is None


def test_ca_b5_1_4_un_privilegio_solo_en_una_mv_no_habilita_la_opcion_de_todo_el_lote():
    solo_una = permisos_en(("VM.GuestAgent.Audit",), "/vms/105")
    est = disponibilidad_fase_b(solo_una, caps(9, 2), CON_UNIDAD, True)
    assert est[OpcionB.ESPERAR_IP].disponibilidad == NO


# --- RF-B5.3: zona de incertidumbre y permisos en 8.x ---------------------------------------------


NETWORK_SOLO = (*BASE,)  # el rol de 14 trae VM.Config.Network pero no VM.Config.Cloudinit


@pytest.mark.parametrize("version", [(9, 0), (9, 1)])
def test_ca_b5_3_1_en_9_0_y_9_1_con_solo_network_se_habilita_con_aviso(version):
    est = disp(NETWORK_SOLO, version, CON_UNIDAD)[OpcionB.CLOUDINIT]
    assert est.disponibilidad == AVISO
    assert (
        est.params["motivo"] == "version_incierta"
        and est.params["privilegio"] == "VM.Config.Cloudinit"
    )
    assert "VM.Config.Network" in texto_estado_opcion(est)


def test_ca_b5_3_1_en_9_2_con_solo_network_se_deshabilita_con_el_motivo():
    est = disp(NETWORK_SOLO, (9, 2), CON_UNIDAD)[OpcionB.CLOUDINIT]
    assert est.disponibilidad == NO and est.codigo == CodigoError.OPCION_SIN_PRIVILEGIO
    assert est.params["privilegio"] == "VM.Config.Cloudinit" and "alternativo" not in est.params


def test_ca_b5_3_1_sin_network_ni_cloudinit_se_deshabilita_tambien_en_la_zona_incierta():
    sin_red = tuple(p for p in BASE if p != "VM.Config.Network")
    assert disp(sin_red, (9, 1), CON_UNIDAD)[OpcionB.CLOUDINIT].disponibilidad == NO


def test_ca_b5_3_1_el_aviso_de_la_zona_incierta_se_propaga_a_contrasena_y_snippets():
    est = disp((*NETWORK_SOLO, "Datastore.Audit", "Datastore.AllocateSpace"), (9, 1), CON_UNIDAD)
    assert est[OpcionB.CONTRASENA].disponibilidad == AVISO
    assert est[OpcionB.SNIPPETS].disponibilidad == AVISO


@pytest.mark.parametrize("version", [(8, 0), (8, 4)])
def test_ca_b5_3_2_en_8_x_network_basta_sin_aviso_de_privilegio(version):
    est = disp(NETWORK_SOLO, version, CON_UNIDAD)[OpcionB.CLOUDINIT]
    assert est.disponibilidad == SI and "motivo" not in est.params


def test_ca_b5_3_3_cicustom_en_8_4_con_solo_allocatespace_se_habilita_con_aviso_no_verificado():
    est = disp(("VM.Config.Cloudinit", "Datastore.AllocateSpace"), (8, 4), CON_UNIDAD)[
        OpcionB.SNIPPETS
    ]
    assert est.disponibilidad == AVISO and est.params["motivo"] == "no_verificado"
    assert est.params["privilegio"] == "Datastore.Allocate"
    assert "no está verificado" in texto_estado_opcion(est)


def test_ca_b5_3_3_en_9_2_con_solo_allocatespace_se_habilita_sin_aviso():
    est = disp(("VM.Config.Cloudinit", "Datastore.AllocateSpace"), (9, 2), CON_UNIDAD)[
        OpcionB.SNIPPETS
    ]
    assert est.disponibilidad == SI


def test_ca_b5_3_3_en_8_4_con_datastore_allocate_se_habilita_sin_aviso():
    est = disp(("VM.Config.Cloudinit", "Datastore.Allocate", "Datastore.Audit"), (8, 4), CON_UNIDAD)
    assert est[OpcionB.SNIPPETS].disponibilidad == SI


@pytest.mark.parametrize("version", [(8, 4), (9, 2)])
def test_ca_b5_3_3_sin_audit_ni_allocatespace_se_deshabilita(version):
    est = disp(("VM.Config.Cloudinit",), version, CON_UNIDAD)[OpcionB.SNIPPETS]
    assert est.disponibilidad == NO


def test_ca_b5_3_4_el_403_de_storage_se_traduce_nombrando_privilegio_y_almacenamiento():
    e = error_http(403, "Permission check failed (/storage/snip, Datastore.Allocate)")
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert e.params["privilegio"] == "Datastore.Allocate" and e.params["ruta"] == "/storage/snip"
    texto = texto_error(e)
    assert "Datastore.Allocate" in texto and "snip" in texto


# --- CL-B23: versión forzada ----------------------------------------------------------------------


def test_cl_b23_con_8_4_forzada_sobre_9_2_se_aplican_los_privilegios_de_8_x_en_la_presentacion():
    """Solo ``VM.Config.Network``: en 8.x basta (habilitada sin aviso); en 9.2 real, no."""
    forzada = capacidades_para(Version("9.2.1", 9, 2, 1), (8, 4))
    permisos = permisos_en(NETWORK_SOLO)
    est = disponibilidad_fase_b(permisos, forzada, CON_UNIDAD, True)
    assert est[OpcionB.CLOUDINIT].disponibilidad == SI
    real = disponibilidad_fase_b(permisos, caps(9, 2), CON_UNIDAD, True)
    assert real[OpcionB.CLOUDINIT].disponibilidad == NO


def test_cl_b23_un_403_real_se_traduce_y_nombra_el_privilegio_de_la_version_real():
    """Con 8.4 forzada la app dejó pasar la opción; el 403 real de un 9.2 se traduce igual."""
    e = error_http(403, "Permission check failed (/vms/100, VM.Config.Cloudinit)")
    assert "VM.Config.Cloudinit" in texto_error(e)
