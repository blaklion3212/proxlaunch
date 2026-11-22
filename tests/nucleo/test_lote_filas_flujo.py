"""Flujo completo de un lote por filas: simulación, informe, rollback, reintento y CSV → plan →
ejecución (RF-C08, RF-C09, RF-L21; CA-C08.2, CA-C08.8..C08.10, CA-C09.3, CA-P12.1, INV-L5, INV-M1,
INV-M6; LAB-M3-03 con mocks).

Cuatro MVs de hardware distinto, una con VMID explícito, otra con nodo explícito: el motor, el
rollback, el informe y la simulación son los de M2 sin cambios y siguen garantizando sus
invariantes con filas heterogéneas.
"""

import dataclasses

from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.filas import definicion_para_reintento, definicion_por_filas, sin_filas
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.modelos import EstadoMV, EstadoRollback, MetadatosInforme
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.planificador import Planificador
from proxlaunch.nucleo.lote.rollback import ServicioRollback
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_perfil
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO
from proxlaunch.nucleo.valores_defecto import configuracion_por_defecto

from .apoyo_lote import (
    HOST,
    NORMAL,
    USUARIO,
    ControlAutomatico,
    crear_banco,
    definicion,
    volcar,
)
from .apoyo_mvp3 import DATOS_MVP3, cfg_hw, definicion_filas, fila, perfil_base

METADATOS = MetadatosInforme("perfil", "9.2.1", True, "lab", "2026-05-14T10:00:00")


def _falla_en(error, *vmids):
    """Regla de POST: lanza ``error`` solo para esos VMIDs; el resto sigue la ruta normal."""

    def _regla(llamada):
        if int(llamada.datos["vmid"]) in vmids:
            raise error
        return NORMAL

    return _regla


def _definicion(**kw):
    return definicion_filas(
        [
            fila("pf-01", cores=1, memoria_mib=1024, discos=[Disco("datos", 8)]),
            fila(
                "pf-02",
                vmid=105,
                cores=4,
                memoria_mib=8192,
                discos=[Disco("datos", 64), Disco("datos", 16)],
            ),
            fila("pf-03", nodo="pve2", cores=2, memoria_mib=4096),
            fila("pf-04", cores=8, memoria_mib=16384, discos=[Disco("datos", 128)]),
        ],
        vmid_inicial=100,
        **kw,
    )


def _creado(nodos=("pve1", "pve2")):
    banco = crear_banco(nodos)
    plan = banco.planificar(_definicion())
    assert not plan.bloqueado, plan.problemas
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK] * 4
    return banco, plan, libro


# --- Simulación (CA-C08.9, INV-L5) ----------------------------------------------------------------


def test_la_simulacion_de_un_lote_por_filas_da_la_peticion_exacta_de_cada_fila_y_solo_lee():
    banco = crear_banco(("pve1", "pve2"))
    resultado = simular(banco.sesion, _definicion(), banco.inv, reloj=banco.reloj)
    assert resultado.plan.es_simulacion and not resultado.plan.bloqueado
    assert (
        set(resultado.peticiones)
        == {e.vmid for e in resultado.plan.elementos}
        == {100, 105, 101, 102}
    )
    for e in resultado.plan.elementos:
        assert resultado.peticiones[e.vmid] == construir_parametros(
            e.cfg, banco.inv, resultado.plan.version_validacion
        )
    assert {resultado.peticiones[v]["cores"] for v in resultado.peticiones} == {"1", "4", "2", "8"}
    assert (
        banco.cluster.solo_lecturas and not banco.cluster.posts and banco.cluster.total("POST") == 0
    )


def test_la_simulacion_usa_el_mismo_plan_que_la_creacion_real():
    banco = crear_banco(("pve1", "pve2"))
    simulado = simular(banco.sesion, _definicion(), banco.inv, reloj=banco.reloj).plan
    real = crear_banco(("pve1", "pve2")).planificar(_definicion())
    assert [(e.nombre, e.vmid, e.nodo) for e in simulado.elementos] == [
        (e.nombre, e.vmid, e.nodo) for e in real.elementos
    ]


def test_la_simulacion_de_un_vmid_explicito_ocupado_lo_senala_sin_escribir():
    banco = crear_banco(("pve1", "pve2"))
    banco.cluster.ocupados.add(105)
    resultado = simular(banco.sesion, _definicion(), banco.inv, reloj=banco.reloj)
    assert any(p.regla == "V-03" and p.indice == 1 for p in resultado.plan.problemas)
    assert banco.cluster.solo_lecturas


# --- Informe (CA-C08.8) ---------------------------------------------------------------------------


def test_el_informe_de_un_lote_por_filas_muestra_la_configuracion_de_cada_maquina():
    banco, plan, libro = _creado()
    informe = construir_informe(plan, libro, METADATOS, reloj=banco.reloj, ocultar=(HOST, USUARIO))
    assert informe.por_filas is True and informe.pedidas == 4
    assert [e.elemento.cfg.cores for e in informe.entradas] == [1, 4, 2, 8]
    assert [e.elemento.cfg.memoria_mib for e in informe.entradas] == [1024, 8192, 4096, 16384]
    assert [len(e.elemento.cfg.discos) for e in informe.entradas] == [1, 2, 1, 1]
    assert informe.contadores["ok"] == 4
    assert HOST not in volcar(informe) and USUARIO not in volcar(informe)  # sin host ni usuario


def test_el_informe_de_un_lote_homogeneo_no_es_por_filas():
    banco = crear_banco(("pve1",))
    plan = banco.planificar(definicion(2, vmid_inicial=100))
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert construir_informe(plan, libro, METADATOS, reloj=banco.reloj).por_filas is False


# --- Rollback: solo lo propio, con propiedad demostrada (CA-C08.2) --------------------------------


def _deshacer(banco, libro, etiquetado=True):
    servicio = ServicioRollback(banco.sesion, banco.reloj)
    candidatos = servicio.elegibles(libro, etiquetado=etiquetado)
    eventos = []
    resultados = servicio.deshacer(
        candidatos, eventos.append, ControlLote(), id_lote=libro.id_lote, etiquetado=etiquetado
    )
    return candidatos, resultados


def test_el_rollback_de_un_lote_por_filas_elimina_exactamente_las_maquinas_creadas():
    banco, plan, libro = _creado()
    banco.cluster.agregar_vm(900, "pve1", "ajena")  # una MV que no es del lote
    banco.cluster.agregar_vm(901, "pve2", "ajena-2", tags="proxlaunch;lote-otro99999")
    candidatos, resultados = _deshacer(banco, libro)
    assert all(c.elegible for c in candidatos)
    assert {r.vmid: r.estado for r in resultados} == {
        100: EstadoRollback.ELIMINADA,
        105: EstadoRollback.ELIMINADA,
        101: EstadoRollback.ELIMINADA,
        102: EstadoRollback.ELIMINADA,
    }
    assert dict(banco.cluster.deletes) == {100: 1, 105: 1, 101: 1, 102: 1}
    assert set(banco.cluster.vms) == {900, 901}  # las ajenas siguen ahí (INV-L4)
    por_nodo = {e.vmid: e.nodo for e in plan.elementos}
    assert por_nodo[101] == "pve2"  # la fila con nodo fijo se borró en SU nodo


def test_el_rollback_no_toca_una_maquina_ajena_con_el_vmid_de_una_fila_que_fallo():
    """INV-L4: la fila 105 no se creó (el VMID lo ocupó otro entre el resumen y el envío)."""
    banco = crear_banco(("pve1", "pve2"))
    plan = banco.planificar(_definicion())
    banco.cluster.agregar_vm(105, "pve1", "ajena-de-otro")
    error = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "105"}, "already exists")
    banco.cluster.regla("POST", r"/qemu$", _falla_en(error, 105))
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert libro.entrada(105).estado == EstadoMV.ERROR
    candidatos, resultados = _deshacer(banco, libro)
    assert {c.entrada.elemento.vmid: c.elegible for c in candidatos} == {
        100: True,
        105: False,
        101: True,
        102: True,
    }
    assert 105 not in banco.cluster.deletes
    assert banco.cluster.vms[105]["config"]["name"] == "ajena-de-otro"
    assert sorted(r.vmid for r in resultados) == [100, 101, 102]


def test_el_rollback_sin_etiquetas_exige_demostrar_la_propiedad_con_el_upid_de_cada_fila():
    banco = crear_banco(("pve1", "pve2"))
    plan = banco.planificar(_definicion(etiquetar=False))
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    assert all(e.cfg.etiquetas == () for e in plan.elementos)
    candidatos, resultados = _deshacer(banco, libro, etiquetado=False)
    assert all(c.elegible for c in candidatos)  # todas con UPID propio
    assert len(resultados) == 4 and not banco.cluster.vms


# --- Reintentar pendientes (CA-C08.10) ------------------------------------------------------------


def test_reintentar_reconstruye_un_lote_por_filas_con_las_filas_no_creadas_y_sus_configuraciones():
    banco = crear_banco(("pve1", "pve2"))
    plan = banco.planificar(_definicion())
    error = ErrorProxLaunch(CodigoError.DESCONOCIDO, {"estado_http": "500"}, "HTTP 500")
    banco.cluster.regla("POST", r"/qemu$", _falla_en(error, 105, 102))
    libro = banco.ejecutar(plan, ControlAutomatico("continuar"))
    estados = {e.elemento.vmid: e.estado for e in libro.instantanea()}
    assert (
        estados[105] == estados[102] == EstadoMV.ERROR
        and estados[100] == estados[101] == EstadoMV.OK
    )
    pendientes = [e.elemento for e in libro.instantanea() if e.estado == EstadoMV.ERROR]
    nueva = definicion_para_reintento(plan.definicion, pendientes)
    assert [(f.nombre, f.vmid, f.cfg.cores) for f in nueva.filas] == [
        ("pf-02", 105, 4),
        ("pf-04", 102, 8),
    ]
    # Se vuelve a planificar con un id de lote nuevo y se ejecuta solo lo pendiente.
    banco.cluster.reglas.clear()
    banco.cluster.reiniciar_llamadas()
    banco.cluster.posts.clear()
    plan2 = Planificador(banco.sesion, banco.reloj, generador_id=lambda: "reint001").planificar(
        nueva, banco.inv
    )
    assert not plan2.bloqueado, plan2.problemas
    assert [(e.nombre, e.vmid, e.nodo) for e in plan2.elementos] == [
        (e.nombre, e.vmid, e.nodo) for e in plan.elementos if e.vmid in {105, 102}
    ]
    libro2 = banco.ejecutar(plan2, ControlAutomatico("continuar"))
    assert [e.estado for e in libro2.instantanea()] == [EstadoMV.OK, EstadoMV.OK]
    assert dict(banco.cluster.posts) == {105: 1, 102: 1}  # lo ya creado no se reenvía
    for e in plan2.elementos:
        assert banco.cluster.cuerpos_post[e.vmid] == construir_parametros(
            e.cfg, banco.inv, plan2.version_validacion
        )
        assert set(banco.cluster.cuerpos_post[e.vmid]["tags"].split(";")) == {
            "proxlaunch",
            "lote-reint001",
        }
    assert (
        banco.cluster.cuerpos_post[105]["cores"] == "4"
        and banco.cluster.cuerpos_post[102]["cores"] == "8"
    )


# --- CSV → plan → ejecución (LAB-M3-03 con mocks; INV-M1, INV-M6) ---------------------------------


def _lote_desde_el_csv_de_excel(banco, inv=None):
    datos = (DATOS_MVP3 / "excel-windows1252.csv").read_bytes()
    tabla = leer_tabla(datos)
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=inv or banco.inv,
        nodo_referencia="pve1",
    )
    return tabla, resultado


def test_un_csv_heterogeneo_de_excel_genera_un_plan_con_la_configuracion_de_cada_fila():
    banco = crear_banco(("pve1", "pve2"))
    tabla, resultado = _lote_desde_el_csv_de_excel(banco)
    assert tabla.codificacion.value == "cp1252" and tabla.deteccion.separador == ";"
    assert all(f.estado != EstadoFila.CON_ERROR for f in resultado.filas)
    assert banco.cluster.llamadas == []  # leer e interpretar no tocan el servidor (INV-M1)
    filas = filas_lote(resultado, resultado.numeros_validos)
    d = definicion_por_filas(filas, plantilla_base=cfg_hw())
    plan = banco.planificar(d)
    assert not plan.bloqueado, plan.problemas
    assert [e.nombre for e in plan.elementos] == ["pg-01", "pg-02", "pg-03", "pg-04"]
    assert [e.vmid for e in plan.elementos] == [
        100,
        150,
        101,
        151,
    ]  # 150 y 151 explícitos; el resto, el siguiente libre
    assert plan.elementos[2].nodo == "pve2"  # el nodo explícito de la fila 4 del archivo
    assert [(e.cfg.cores, e.cfg.memoria_mib) for e in plan.elementos] == [
        (1, 1024),
        (4, 8192),
        (2, 4608),
        (8, 16384),
    ]
    assert plan.elementos[1].cfg.redes[0].vlan == 20
    assert [e.cfg.discos[0].tamano_gib for e in plan.elementos] == [8, 64, 32, 128]


def test_con_un_vmid_ocupado_esa_fila_no_genera_post_y_el_resto_se_crea_y_se_deshace_por_completo():
    banco = crear_banco(("pve1", "pve2"))
    banco.cluster.agregar_vm(151, "pve1", "ajena-151")
    _, resultado = _lote_desde_el_csv_de_excel(banco)
    d = definicion_por_filas(
        filas_lote(resultado, resultado.numeros_validos), plantilla_base=cfg_hw()
    )
    plan = banco.planificar(d)
    (v03,) = [p for p in plan.problemas if p.regla == "V-03"]
    assert (v03.indice, v03.params["vmid"]) == (3, "151") and plan.bloqueado
    assert banco.cluster.total("POST") == 0  # INV-M6: bloqueado, nada se envió
    # El usuario excluye esa fila (acción explícita) y se vuelve a planificar.
    plan2 = banco.planificar(sin_filas(d, [3]))
    assert not plan2.bloqueado and [e.nombre for e in plan2.elementos] == [
        "pg-01",
        "pg-02",
        "pg-03",
    ]
    libro = banco.ejecutar(plan2, ControlAutomatico("continuar"))
    assert [e.estado for e in libro.instantanea()] == [EstadoMV.OK] * 3
    assert 151 not in banco.cluster.posts and dict(banco.cluster.posts) == {100: 1, 150: 1, 101: 1}
    for e in plan2.elementos:
        assert banco.cluster.cuerpos_post[e.vmid] == construir_parametros(
            e.cfg, banco.inv, plan2.version_validacion
        )
        assert f"lote-{plan2.id_lote}" in banco.cluster.cuerpos_post[e.vmid]["tags"].split(";")
    _, resultados = _deshacer(banco, libro)
    assert len(resultados) == 3 and all(r.estado == EstadoRollback.ELIMINADA for r in resultados)
    assert (
        set(banco.cluster.vms) == {151} and banco.cluster.vms[151]["config"]["name"] == "ajena-151"
    )


def test_asignar_automaticamente_una_fila_con_vmid_ocupado_la_hace_planificable():
    from proxlaunch.nucleo.lote.filas import reemplazar_fila

    banco = crear_banco(("pve1", "pve2"))
    banco.cluster.agregar_vm(151, "pve1", "ajena-151")
    _, resultado = _lote_desde_el_csv_de_excel(banco)
    d = definicion_por_filas(
        filas_lote(resultado, resultado.numeros_validos), plantilla_base=cfg_hw()
    )
    d2 = reemplazar_fila(d, 3, dataclasses.replace(d.filas[3], vmid=None))
    plan = banco.planificar(d2)
    assert not plan.bloqueado and plan.elementos[3].vmid not in {151, 150}


def test_importar_un_csv_y_planificarlo_solo_hace_lecturas_hasta_confirmar():
    """INV-M1 / INV-M6: ``Planificador`` solo hace GET; el motor solo se lanza con un plan recién generado."""  # noqa: E501
    banco = crear_banco(("pve1", "pve2"))
    _, resultado = _lote_desde_el_csv_de_excel(banco)
    d = definicion_por_filas(
        filas_lote(resultado, resultado.numeros_validos), plantilla_base=cfg_hw()
    )
    banco.planificar(d)
    simular(banco.sesion, d, banco.inv, reloj=banco.reloj)
    assert banco.cluster.solo_lecturas and not banco.cluster.posts


# --- CA-P12.1: el perfil predeterminado da el POST de M2 ------------------------------------------


def test_el_perfil_predeterminado_produce_el_mismo_post_que_la_configuracion_por_defecto_de_m1():
    por_defecto = configuracion_por_defecto(0, "plantilla", "", "datos", "vmbr0")
    banco_a = crear_banco(("pve1",))
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    del_perfil = aplicar_perfil(
        perfil,
        # Fase A: un perfil no toca las notas; el formulario parte con «notas de origen» marcada.
        ConfiguracionVM(
            vmid=0, nombre="plantilla", nodo="pve1", notas_origen=por_defecto.notas_origen
        ),
        banco_a.inv,
    ).cfg
    cuerpos = []
    for banco, plantilla in ((banco_a, del_perfil), (crear_banco(("pve1",)), por_defecto)):
        plan = banco.planificar(
            definicion(
                2,
                prefijo="web",
                vmid_inicial=100,
                plantilla_vm=dataclasses.replace(plantilla, nodo=""),
            )
        )
        banco.ejecutar(plan, ControlAutomatico("continuar"))
        cuerpos.append(dict(banco.cluster.cuerpos_post))
    assert cuerpos[0] == cuerpos[1] and set(cuerpos[0]) == {100, 101}


def test_una_fila_con_el_hardware_del_perfil_predeterminado_da_el_mismo_post_que_un_lote_homogeneo():  # noqa: E501
    """El lote por filas con filas iguales es el caso particular del homogéneo (CA-C08.12)."""
    banco_h = crear_banco(("pve1",))
    homogeneo = banco_h.planificar(
        definicion(3, prefijo="web", separador="-", inicio=1, relleno=2, vmid_inicial=100)
    )
    banco_h.ejecutar(homogeneo, ControlAutomatico("continuar"))
    base = homogeneo.definicion.plantilla
    banco_f = crear_banco(("pve1",))
    filas = [
        dataclasses.replace(
            fila(f"web-0{i}"), cfg=dataclasses.replace(base, nombre="", vmid=0, nodo="")
        )
        for i in (1, 2, 3)
    ]
    por_filas = banco_f.planificar(definicion_filas(filas, vmid_inicial=100))
    banco_f.ejecutar(por_filas, ControlAutomatico("continuar"))
    assert dict(banco_f.cluster.cuerpos_post) == dict(banco_h.cluster.cuerpos_post)
    assert [(e.nombre, e.vmid, e.nodo) for e in por_filas.elementos] == [
        (e.nombre, e.vmid, e.nodo) for e in homogeneo.elementos
    ]
    assert por_filas.reparto == homogeneo.reparto and por_filas.uso == homogeneo.uso
