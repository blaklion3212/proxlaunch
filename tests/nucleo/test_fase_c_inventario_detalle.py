"""Inventario de lotes (fase C, C1): detalle de un lote, motivos, clúster y carga.

Requisitos: RF-C1.3 (CA-C1.3.1, CA-C1.3.2, CA-C1.3.4), RF-C1.9 (CA-C1.9.1, CA-C1.9.2),
RF-C1.10 (CA-C1.10.4), RF-C1.11 (CA-C1.11.1 a CA-C1.11.3), RF-C1.12 (CA-C1.12.1, CA-C1.12.3),
RF-C1.13 (CA-C1.13.1) y las validaciones V-C03, V-C04, V-C05 y V-C08. Doble: clúster en memoria.
"""

from __future__ import annotations

import threading

import pytest

from proxlaunch.interfaz.textos_inventario import texto_motivo, texto_motivos_mv
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.inventario.modelos import (
    MAX_LECTURAS_INVENTARIO,
    EstadoNota,
    MotivoNoDeshacible,
)
from proxlaunch.nucleo.inventario.propiedad import evaluar_mv, mv_sin_detalle
from proxlaunch.nucleo.modelos.inventario import RecursoVM

from .apoyo_fase_c_inventario import (
    CODIGO,
    OTRO_CODIGO,
    Mundo,
    etiquetas_lote,
    nota_origen,
    permisos,
)
from .apoyo_lote import NORMAL, error_http, nodo_caido, volcar


def _motivos(m: Mundo, vmid: int, codigo: str = CODIGO):
    detalle = m.detallar(codigo)
    return next(mv for mv in detalle.maquinas if mv.recurso.vmid == vmid)


# --- RF-C1.3: una lectura de config por MV del lote -------------------------------------------


def test_ca_c1_3_1_un_lote_de_tres_mvs_emite_tres_get_config_y_ninguna_de_otro_lote():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    m.cluster.agregar_mv(201, lote=OTRO_CODIGO)
    m.cluster.agregar_mv(202, lote=None, nota=False)
    m.listar()
    m.cluster.llamadas.clear()
    m.cluster.lecturas_config.clear()
    m.servicio.detallar(m.lote(), threading.Event(), None)
    assert sorted(m.cluster.lecturas_config) == [("pve1", 101), ("pve1", 102), ("pve1", 103)]
    assert m.cluster.solo_lecturas


# --- Motivos de «no se puede deshacer desde aquí» (V-C02..V-C05, V-C08) -------------------------


def test_ca_c1_3_2_una_mv_con_lock_backup_no_es_deshacible_y_dice_el_bloqueo():
    m = Mundo()
    m.cluster.agregar_mv(101, lock="backup")
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.BLOQUEADA in mv.motivos and not mv.deshacible
    assert mv.params["bloqueo"] == "backup"
    assert "copia de seguridad" in texto_motivos_mv(mv, CODIGO)


def test_v_c05_un_lock_cualquiera_bloquea_aunque_no_sea_conocido():
    m = Mundo()
    m.cluster.agregar_mv(101, lock="algo-nuevo-de-proxmox")
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.BLOQUEADA in mv.motivos and not mv.deshacible


def test_v_c05_el_bloqueo_de_la_lista_tambien_cuenta_aunque_la_config_no_lo_traiga():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.fila_lista[101] = {"lock": "migrate"}
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.BLOQUEADA in mv.motivos


@pytest.mark.parametrize("valor", [1, "1", True, "true"])
def test_v_c05_una_plantilla_no_es_deshacible(valor):
    m = Mundo()
    m.cluster.agregar_mv(101, template=valor)
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.PLANTILLA in mv.motivos and not mv.deshacible


def test_v_c05_una_plantilla_marcada_solo_en_la_lista_tampoco_es_deshacible():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.fila_lista[101] = {"template": 1}
    assert MotivoNoDeshacible.PLANTILLA in _motivos(m, 101).motivos


def test_v_c03_falta_la_etiqueta_proxlaunch_y_se_nombra():
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas=f"lote-{CODIGO}")
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.FALTA_ETIQUETA in mv.motivos and not mv.deshacible
    assert mv.params["falta"] == "proxlaunch"
    assert "proxlaunch" in texto_motivos_mv(mv, CODIGO)


def test_v_c03_falta_la_etiqueta_del_lote_en_la_config_aunque_la_lista_la_traiga():
    """La lista puede ir desfasada: manda la config releída (RNF-C6.1)."""
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas="proxlaunch")
    m.cluster.fila_lista[101] = {"tags": etiquetas_lote()}
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.FALTA_ETIQUETA in mv.motivos
    assert mv.params["falta"] == f"lote-{CODIGO}"


def test_v_c03_faltan_las_dos_etiquetas_y_se_nombran_ambas():
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas="otra")
    m.cluster.fila_lista[101] = {"tags": etiquetas_lote()}
    mv = _motivos(m, 101)
    assert mv.params["falta"] == f"proxlaunch, lote-{CODIGO}"


def test_v_c04_sin_nota_de_origen_no_es_deshacible():
    m = Mundo()
    m.cluster.agregar_mv(101, nota=False)
    mv = _motivos(m, 101)
    assert mv.motivos == (MotivoNoDeshacible.SIN_NOTA,)
    assert mv.nota is not None and mv.nota.estado == EstadoNota.FALTA


def test_v_c04_la_nota_de_otro_lote_no_es_deshacible_y_dice_cual():
    m = Mundo()
    m.cluster.agregar_mv(101, nota=nota_origen(OTRO_CODIGO))
    mv = _motivos(m, 101)
    assert mv.motivos == (MotivoNoDeshacible.NOTA_OTRO_LOTE,)
    assert OTRO_CODIGO in texto_motivos_mv(mv, CODIGO)


def test_v_c04_una_nota_editada_a_mano_sin_las_lineas_estrictas_no_vale():
    m = Mundo()
    m.cluster.agregar_mv(101, nota=f"Creada con ProxLaunch\n\nesto es del lote {CODIGO}")
    assert MotivoNoDeshacible.SIN_NOTA in _motivos(m, 101).motivos


@pytest.mark.parametrize("estado", ["unknown", "paused", "", None])
def test_ca_c1_4_1_un_estado_distinto_de_running_o_stopped_no_es_deshacible(estado):
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.fila_lista[101] = {"status": estado}
    mv = _motivos(m, 101)
    assert MotivoNoDeshacible.ESTADO_DESCONOCIDO in mv.motivos and not mv.deshacible


@pytest.mark.parametrize("estado", ["running", "stopped", "Running"])
def test_v_c05_running_y_stopped_si_cuentan_como_estado_conocido(estado):
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.fila_lista[101] = {"status": estado}
    assert _motivos(m, 101).deshacible


def test_ca_c1_3_4_un_get_config_que_falla_deja_esa_fila_ilegible_y_el_resto_sigue():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    m.cluster.regla("GET", r"/qemu/102/config$", error_http(500, "boom interno"))
    detalle = m.detallar()
    por_vmid = {mv.recurso.vmid: mv for mv in detalle.maquinas}
    assert por_vmid[102].motivos == (MotivoNoDeshacible.CONFIG_ILEGIBLE,)
    assert not por_vmid[102].deshacible
    assert por_vmid[101].deshacible and por_vmid[103].deshacible
    assert detalle.completo is True
    assert "No se pudo leer" in texto_motivos_mv(por_vmid[102], CODIGO)


def test_ca_c1_3_4_una_excepcion_inesperada_en_una_lectura_tampoco_rompe_el_detalle():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    m.cluster.regla("GET", r"/qemu/101/config$", RuntimeError("fallo raro"))
    por_vmid = {mv.recurso.vmid: mv for mv in m.detallar().maquinas}
    assert por_vmid[101].motivos == (MotivoNoDeshacible.CONFIG_ILEGIBLE,)
    assert por_vmid[102].deshacible


def test_ca_c1_3_4_una_config_que_no_es_un_diccionario_es_ilegible():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.regla("GET", r"/qemu/101/config$", lambda _ll: ["no", "es", "dict"])
    assert _motivos(m, 101).motivos == (MotivoNoDeshacible.CONFIG_ILEGIBLE,)


def test_ca_c1_10_4_una_mv_ya_borrada_por_otro_medio_se_marca_ya_no_existe_sin_error():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.agregar_mv(102)
    m.cluster.lista_cruda = [
        {"vmid": v, "node": "pve1", "type": "qemu", "status": "stopped", "tags": etiquetas_lote()}
        for v in (101, 102)
    ]
    del m.cluster.vms[102]
    por_vmid = {mv.recurso.vmid: mv for mv in m.detallar().maquinas}
    assert por_vmid[102].motivos == (MotivoNoDeshacible.YA_NO_EXISTE,)
    assert texto_motivos_mv(por_vmid[102], CODIGO).endswith("Ya no existe.")
    assert por_vmid[101].deshacible


def test_ca_c1_9_1_ningun_motivo_queda_con_texto_vacio_y_ninguno_deja_marcadores_sin_rellenar():
    recurso = RecursoVM(101, "web", "pve1", "qemu", "stopped", None, None, ())
    for motivo in MotivoNoDeshacible:
        mv = mv_sin_detalle(recurso)
        mv = type(mv)(mv.recurso, None, None, (motivo,), {})
        texto = texto_motivos_mv(mv, CODIGO)
        assert texto.strip() and "{" not in texto and "}" not in texto, motivo
        assert texto.startswith("No se puede deshacer desde aquí:"), motivo


def test_ca_c1_9_1_cada_motivo_tiene_un_texto_distinto():
    textos = {m: texto_motivo(m, {"falta": "x", "otro": "y", "bloqueo": "z", "nodo": "n",
                                  "vmid": "1"}, CODIGO) for m in MotivoNoDeshacible}  # fmt: skip
    assert len(set(textos.values())) == len(textos)


def test_ca_c1_9_1_los_valores_del_servidor_se_ponen_como_texto_plano_y_acotados():
    m = Mundo()
    m.cluster.agregar_mv(101, lock="<b>x</b>‮\n" + "A" * 500)
    mv = _motivos(m, 101)
    assert len(mv.params["bloqueo"]) <= 64
    assert "\n" not in mv.params["bloqueo"] and "‮" not in mv.params["bloqueo"]


def test_ca_c1_9_2_un_lote_sin_ninguna_deshacible_lo_sabe_el_detalle():
    m = Mundo()
    m.cluster.agregar_mv(101, nota=False)
    m.cluster.agregar_mv(102, lock="backup")
    detalle = m.detallar()
    assert not any(mv.deshacible for mv in detalle.maquinas)
    assert all(mv.motivos for mv in detalle.maquinas)


def test_v_c08_sin_vm_allocate_no_es_deshacible_y_el_texto_nombra_privilegio_y_ruta():
    m = Mundo()
    m.cluster.agregar_mv(101)
    sin = permisos({"/": {"VM.Audit": 1}})
    mv = m.detallar(permisos=sin).maquinas[0]
    assert MotivoNoDeshacible.SIN_PERMISO_BORRAR in mv.motivos and not mv.deshacible
    texto = texto_motivos_mv(mv, CODIGO)
    assert "VM.Allocate" in texto and "/vms/101" in texto


def test_v_c08_con_vm_allocate_o_permisos_desconocidos_no_se_bloquea_por_permiso():
    m = Mundo()
    m.cluster.agregar_mv(101)
    con = permisos({"/vms": {"VM.Allocate": 1}})
    assert m.detallar(permisos=con).maquinas[0].deshacible
    assert m.detallar(permisos=None).maquinas[0].deshacible  # desconocido: se intenta


def test_evaluar_mv_acumula_todos_los_motivos_a_la_vez():
    recurso = RecursoVM(101, None, "pve1", "qemu", "unknown", "backup", True, ())
    lote = type("L", (), {"codigo": "prueba", "valido": False})()
    mv = evaluar_mv(
        recurso,
        lote,
        {"tags": "otra", "template": 1, "lock": "backup"},
        None,
        None,  # type: ignore[arg-type]
    )
    esperados = {
        MotivoNoDeshacible.CODIGO_INVALIDO,
        MotivoNoDeshacible.FALTA_ETIQUETA,
        MotivoNoDeshacible.SIN_NOTA,
        MotivoNoDeshacible.PLANTILLA,
        MotivoNoDeshacible.BLOQUEADA,
        MotivoNoDeshacible.ESTADO_DESCONOCIDO,
    }
    assert esperados <= set(mv.motivos)


# --- Detalle sin datos del servidor en el resultado (CA-C1.3.5, RNF-C6.5) -----------------------


def test_ca_c1_3_5_el_detalle_no_guarda_la_nota_completa_ni_el_token():
    m = Mundo()
    m.cluster.agregar_mv(
        101, nota=nota_origen(CODIGO, extra="SECRETO-DE-LA-NOTA contraseña: hunter2")
    )
    detalle = m.detallar()
    volcado = volcar(detalle)
    assert "SECRETO-DE-LA-NOTA" not in volcado and "hunter2" not in volcado
    assert "Creada con ProxLaunch" not in volcado
    from .apoyo_api import TOKEN_SECRETO

    assert TOKEN_SECRETO not in volcado


# --- RF-C1.11: clúster y nodo suelto ------------------------------------------------------------


def test_ca_c1_11_1_cada_lectura_va_al_nodo_de_su_entrada():
    m = Mundo(("pve1", "pve2", "pve3"))
    reparto = {101: "pve1", 102: "pve2", 103: "pve3", 104: "pve2", 105: "pve1"}
    for vmid, nodo in reparto.items():
        m.cluster.agregar_mv(vmid, nodo=nodo)
    detalle = m.detallar()
    assert all(mv.deshacible for mv in detalle.maquinas)  # una lectura al nodo equivocado fallaría
    assert sorted(m.cluster.lecturas_config) == sorted((n, v) for v, n in reparto.items())
    assert {mv.recurso.vmid: mv.recurso.nodo for mv in detalle.maquinas} == reparto


def test_ca_c1_11_2_un_nodo_suelto_funciona_igual_con_un_unico_nodo():
    m = Mundo(("pve1",))
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    lista = m.listar()
    assert [x.codigo for x in lista.lotes] == [CODIGO]
    assert all(mv.deshacible for mv in m.detallar().maquinas)


@pytest.mark.parametrize("estado", [595, 596, 597])
def test_ca_c1_11_3_un_nodo_que_no_responde_marca_solo_sus_mvs(estado):
    m = Mundo(("pve1", "pve2"))
    m.cluster.agregar_mv(101, nodo="pve1")
    m.cluster.agregar_mv(102, nodo="pve2")
    m.cluster.agregar_mv(103, nodo="pve2")
    m.cluster.agregar_mv(104, nodo="pve1")
    m.cluster.regla("GET", r"/nodes/pve2/qemu/\d+/config$", nodo_caido("pve2", estado))
    detalle = m.detallar()
    por_vmid = {mv.recurso.vmid: mv for mv in detalle.maquinas}
    for vmid in (102, 103):
        assert por_vmid[vmid].motivos == (MotivoNoDeshacible.NODO_SIN_RESPUESTA,)
        assert por_vmid[vmid].params["nodo"] == "pve2"
        assert "pve2" in texto_motivos_mv(por_vmid[vmid], CODIGO)
    assert por_vmid[101].deshacible and por_vmid[104].deshacible


def test_ca_c1_11_3_el_servidor_que_no_responde_se_distingue_de_una_config_ilegible():
    m = Mundo(("pve1", "pve2"))
    m.cluster.agregar_mv(101, nodo="pve2")
    m.cluster.regla(
        "GET",
        r"/qemu/101/config$",
        ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.1"}, "HTTP 596"),
    )
    assert _motivos(m, 101).motivos == (MotivoNoDeshacible.NODO_SIN_RESPUESTA,)


# --- RF-C1.12: carga sobre el servidor ----------------------------------------------------------


def test_ca_c1_12_1_un_lote_de_100_mvs_nunca_pasa_de_4_lecturas_simultaneas():
    m = Mundo()
    for vmid in range(1000, 1100):
        m.cluster.agregar_mv(vmid)
    m.cluster.medir = True
    detalle = m.detallar()
    assert len(detalle.maquinas) == 100 and len(m.cluster.lecturas_config) == 100
    assert 1 < m.cluster.max_lecturas_config <= MAX_LECTURAS_INVENTARIO == 4
    assert len({v for _, v in m.cluster.lecturas_config}) == 100  # una lectura por MV, no más


def test_ca_c1_12_1_el_medidor_detectaria_mas_de_4_si_el_servicio_lo_permitiera():
    """Control del propio doble: con un límite mayor el medidor ve más de 4 a la vez."""
    from proxlaunch.nucleo.inventario.servicio import ServicioInventario

    m = Mundo()
    for vmid in range(1000, 1040):
        m.cluster.agregar_mv(vmid)
    m.cluster.medir = True
    servicio = ServicioInventario(m.sesion, m.reloj, max_lecturas=8)
    servicio.detallar(m.lote(), threading.Event(), None)
    assert m.cluster.max_lecturas_config > 4


def test_ca_c1_12_3_cancelar_antes_de_empezar_no_lee_nada_y_deja_el_detalle_incompleto():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    lote = m.lote()
    cancelado = threading.Event()
    cancelado.set()
    detalle = m.servicio.detallar(lote, cancelado, None)
    assert m.cluster.lecturas_config == []
    assert detalle.completo is False
    assert all(mv.motivos == (MotivoNoDeshacible.SIN_DETALLE,) for mv in detalle.maquinas)
    assert not any(mv.deshacible for mv in detalle.maquinas)


def test_ca_c1_12_3_cancelar_durante_la_lectura_deja_sin_leer_las_pendientes():
    m = Mundo()
    for vmid in range(1000, 1060):
        m.cluster.agregar_mv(vmid)
    lote = m.lote()
    cancelado = threading.Event()

    def cancelar_al_primero(_ll):
        cancelado.set()
        return NORMAL

    m.cluster.regla("GET", r"/qemu/\d+/config$", cancelar_al_primero, veces=1)
    detalle = m.servicio.detallar(lote, cancelado, None)
    assert len(m.cluster.lecturas_config) < 60
    assert detalle.completo is False
    assert any(MotivoNoDeshacible.SIN_DETALLE in mv.motivos for mv in detalle.maquinas)


# --- RF-C1.13: solo lectura ---------------------------------------------------------------------


def test_ca_c1_13_1_un_recorrido_sin_borrar_solo_emite_get():
    m = Mundo(("pve1", "pve2"))
    m.cluster.agregar_mv(101, nodo="pve1", status="running", agent=1)
    m.cluster.agregar_mv(102, nodo="pve2", protection=1)
    m.cluster.agregar_mv(103, nodo="pve2", nota=False)
    m.cluster.guion_agente(101, {"result": []})
    lista = m.listar()
    detalle = m.servicio.detallar(lista.lotes[0], threading.Event(), None)
    m.servicio.inspeccionar(detalle, {101, 102}, None)
    m.servicio.obtener_ips(detalle, [101, 102, 103], threading.Event(), None)
    m.listar()  # «Comprobar»
    m.servicio.detallar(lista.lotes[0], threading.Event(), None)
    assert set(m.cluster.metodos) == {"GET"}
    assert m.cluster.escrituras == []
