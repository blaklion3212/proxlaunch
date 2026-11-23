"""Inventario de lotes (fase C, C1): lista, agrupación, nota de origen y tolerancia a datos
incompletos.

Requisitos: RF-C1.2 (CA-C1.2.1 a CA-C1.2.6), RF-C1.3 (CA-C1.3.3, CA-C1.3.5), RF-C1.4
(CA-C1.4.1 a CA-C1.4.3), RF-C1.5 (CA-C1.5.2, CA-C1.5.3), V-C01, V-C02 y los casos límite CL-C1,
CL-C3 y CL-C5. Todo contra un clúster simulado en memoria: ningún servidor real.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from proxlaunch.nucleo.inventario.agrupacion import agrupar_lotes, filtrar_lotes
from proxlaunch.nucleo.inventario.modelos import RE_CODIGO_LOTE, EstadoNota, MotivoNoDeshacible
from proxlaunch.nucleo.inventario.nota import leer_nota_origen
from proxlaunch.nucleo.modelos.inventario import RecursoVM

from .apoyo_fase_c_inventario import (
    CODIGO,
    FECHA_BASE,
    OTRO_CODIGO,
    Mundo,
    etiquetas_lote,
    nota_origen,
)


def _recurso(vmid=101, nombre="web-01", tipo="qemu", etiquetas=(), nodo="pve1", estado="stopped"):
    return RecursoVM(vmid, nombre, nodo, tipo, estado, None, None, tuple(etiquetas))


# --- RF-C1.2: agrupación -------------------------------------------------------------------


def test_ca_c1_2_1_cinco_mvs_dan_un_grupo_de_cuatro_y_la_sin_etiquetas_no_aparece():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    m.cluster.agregar_mv(104, etiquetas=f"lote-{CODIGO}")  # sin la etiqueta «proxlaunch»
    m.cluster.agregar_mv(105, lote=None, nota=False)  # sin etiquetas
    lista = m.listar()
    assert [x.codigo for x in lista.lotes] == [CODIGO]
    assert [r.vmid for r in lista.lotes[0].recursos] == [101, 102, 103, 104]
    assert lista.lotes[0].de_proxlaunch is True and lista.lotes[0].valido is True
    assert lista.total_visibles == 5  # la 105 se ve, pero no es de ningún lote


def test_ca_c1_2_2_las_mayusculas_se_agrupan_igual_y_el_codigo_sale_en_minusculas():
    lista = agrupar_lotes(
        [
            _recurso(101, etiquetas=("proxlaunch", f"lote-{CODIGO}")),
            _recurso(102, etiquetas=("Proxlaunch", f"LOTE-{CODIGO.upper()}")),
        ]
    )
    assert [x.codigo for x in lista.lotes] == [CODIGO]
    assert len(lista.lotes[0].recursos) == 2 and lista.lotes[0].de_proxlaunch


def test_ca_c1_2_2_el_cliente_normaliza_las_etiquetas_de_la_lista_del_servidor():
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas=f"Proxlaunch;LOTE-{CODIGO.upper()}")
    lote = m.listar().lotes[0]
    assert lote.codigo == CODIGO and lote.valido and lote.de_proxlaunch


def test_ca_c1_2_3_los_contenedores_lxc_con_la_etiqueta_del_lote_no_se_listan():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.visibles_extra.append(
        {"vmid": 200, "type": "lxc", "node": "pve1", "tags": etiquetas_lote(), "status": "running"}
    )
    lista = m.listar()
    assert [r.vmid for r in lista.lotes[0].recursos] == [101]
    assert lista.total_visibles == 1


def test_ca_c1_2_3_un_servidor_solo_con_lxc_etiquetados_no_crea_lotes():
    lista = agrupar_lotes([_recurso(200, tipo="lxc", etiquetas=("proxlaunch", f"lote-{CODIGO}"))])
    assert lista.lotes == () and lista.total_visibles == 0


def test_ca_c1_2_4_un_codigo_que_no_son_8_hex_aparece_como_no_valido_y_no_es_deshacible():
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas="proxlaunch;lote-prueba", nota=nota_origen("prueba"))
    lote = m.listar().lotes[0]
    assert lote.codigo == "prueba" and lote.valido is False
    detalle = m.detallar("prueba")
    assert MotivoNoDeshacible.CODIGO_INVALIDO in detalle.maquinas[0].motivos
    assert not detalle.maquinas[0].deshacible


@pytest.mark.parametrize(
    "codigo", ["", "ab12cd3", "ab12cd345", "AB12CD34", "ab12cd3g", "ab12-d34", " ab12cd34"]
)
def test_ca_c1_2_4_solo_ocho_hexadecimales_en_minusculas_son_un_codigo_de_proxlaunch(codigo):
    assert RE_CODIGO_LOTE.match(codigo) is None


def test_ca_c1_2_4_un_codigo_con_salto_de_linea_final_no_es_de_proxlaunch():
    lista = agrupar_lotes([_recurso(101, etiquetas=("proxlaunch", f"lote-{CODIGO}\n"))])
    assert lista.lotes[0].valido is False


def test_ca_c1_2_4_un_lote_sin_la_etiqueta_proxlaunch_se_marca_como_no_de_proxlaunch():
    lista = agrupar_lotes([_recurso(101, etiquetas=(f"lote-{CODIGO}",))])
    assert lista.lotes[0].de_proxlaunch is False


def test_ca_c1_2_5_la_lectura_inicial_es_una_sola_peticion_y_ninguna_config():
    m = Mundo()
    for vmid in range(101, 111):
        m.cluster.agregar_mv(vmid)
    m.listar()
    assert m.cluster.rutas("GET") == ["/cluster/resources"]
    assert m.cluster.lecturas_config == []
    assert m.cluster.escrituras == []


def test_ca_c1_2_6_la_busqueda_filtra_por_nombre_de_maquina_y_por_codigo():
    lista = agrupar_lotes(
        [
            _recurso(101, "web-01", etiquetas=("proxlaunch", "lote-aaaaaaaa")),
            _recurso(102, "db-01", etiquetas=("proxlaunch", "lote-bbbbbbbb")),
            _recurso(103, "WEB-02", etiquetas=("proxlaunch", "lote-cccccccc")),
        ]
    )
    assert [x.codigo for x in filtrar_lotes(lista.lotes, "web")] == ["aaaaaaaa", "cccccccc"]
    assert [x.codigo for x in filtrar_lotes(lista.lotes, "bbbb")] == ["bbbbbbbb"]
    assert [x.codigo for x in filtrar_lotes(lista.lotes, "  ")] == [
        "aaaaaaaa",
        "bbbbbbbb",
        "cccccccc",
    ]
    assert filtrar_lotes(lista.lotes, "no-existe") == ()


def test_ca_c1_2_6_la_busqueda_tolera_maquinas_sin_nombre():
    lista = agrupar_lotes([_recurso(101, None, etiquetas=("proxlaunch", f"lote-{CODIGO}"))])
    assert filtrar_lotes(lista.lotes, "web") == ()


def test_ca_c1_2_los_lotes_salen_ordenados_por_codigo_y_las_maquinas_por_vmid():
    lista = agrupar_lotes(
        [
            _recurso(105, etiquetas=("lote-bbbbbbbb",)),
            _recurso(103, etiquetas=("lote-bbbbbbbb",)),
            _recurso(104, etiquetas=("lote-aaaaaaaa",)),
        ]
    )
    assert [x.codigo for x in lista.lotes] == ["aaaaaaaa", "bbbbbbbb"]
    assert [r.vmid for r in lista.lotes[1].recursos] == [103, 105]


def test_cl_c1_dos_lotes_con_una_etiqueta_copiada_se_agrupan_por_codigo_y_la_nota_decide():
    """Una MV con la etiqueta de otro lote copiada a mano se agrupa, pero su nota no coincide."""
    m = Mundo()
    m.cluster.agregar_mv(101, lote=CODIGO)
    m.cluster.agregar_mv(102, etiquetas=etiquetas_lote(CODIGO), nota=nota_origen(OTRO_CODIGO))
    m.cluster.agregar_mv(103, lote=OTRO_CODIGO)
    lista = m.listar()
    assert [x.codigo for x in lista.lotes] == [CODIGO, OTRO_CODIGO]
    detalle = m.detallar(CODIGO)
    por_vmid = {mv.recurso.vmid: mv for mv in detalle.maquinas}
    assert por_vmid[101].deshacible
    assert MotivoNoDeshacible.NOTA_OTRO_LOTE in por_vmid[102].motivos
    assert por_vmid[102].params["otro"] == OTRO_CODIGO


def test_cl_c3_un_lote_de_150_maquinas_se_lista_entero():
    m = Mundo()
    for vmid in range(1000, 1150):
        m.cluster.agregar_mv(vmid)
    assert len(m.listar().lotes[0].recursos) == 150
    assert m.cluster.lecturas_config == []


# --- V-C01: nada visible ---------------------------------------------------------------------


def test_v_c01_sin_ninguna_maquina_visible_la_lista_viene_vacia_con_total_cero():
    m = Mundo()
    lista = m.listar()
    assert lista.lotes == () and lista.total_visibles == 0


def test_v_c01_con_maquinas_sin_etiqueta_de_lote_hay_total_pero_ningun_lote():
    m = Mundo()
    m.cluster.agregar_mv(101, lote=None, nota=False)
    lista = m.listar()
    assert lista.lotes == () and lista.total_visibles == 1


# --- RF-C1.4: tolerancia a datos incompletos ----------------------------------------------------


def test_ca_c1_4_1_status_unknown_y_sin_nombre_se_lista_sin_error_y_no_es_deshacible():
    m = Mundo()
    m.cluster.lista_cruda = [
        {"vmid": 101, "node": "pve1", "type": "qemu", "status": "unknown", "tags": etiquetas_lote()}
    ]
    m.cluster.agregar_mv(101)  # la config sí existe y es de ProxLaunch
    detalle = m.detallar()
    mv = detalle.maquinas[0]
    assert mv.recurso.nombre is None and mv.recurso.estado == "unknown"
    assert MotivoNoDeshacible.ESTADO_DESCONOCIDO in mv.motivos
    assert not mv.deshacible


def test_ca_c1_4_1_un_estado_ausente_tampoco_es_deshacible():
    m = Mundo()
    m.cluster.lista_cruda = [
        {"vmid": 101, "node": "pve1", "type": "qemu", "tags": etiquetas_lote()}
    ]
    m.cluster.agregar_mv(101)
    mv = m.detallar().maquinas[0]
    assert MotivoNoDeshacible.ESTADO_DESCONOCIDO in mv.motivos and not mv.deshacible


def test_cl_c5_mv_recien_creada_se_lista_y_pasa_a_deshacible_al_informar_proxmox():
    """CA-C1.4.3: tras «Comprobar» con el estado ya conocido, la MV pasa a deshacible."""
    m = Mundo()
    m.cluster.agregar_mv(101, status="unknown")
    m.cluster.fila_lista[101] = {"status": "unknown"}
    antes = m.detallar().maquinas[0]
    assert not antes.deshacible
    m.cluster.vms[101]["status"] = "stopped"
    m.cluster.fila_lista.clear()
    despues = m.detallar().maquinas[0]  # equivale a pulsar «Comprobar»
    assert despues.deshacible and despues.motivos == ()


def test_ca_c1_4_2_entradas_malformadas_se_ignoran_o_quedan_sin_leer_sin_excepcion():
    m = Mundo()
    m.cluster.lista_cruda = [
        {"node": "pve1", "type": "qemu", "tags": etiquetas_lote()},  # sin vmid
        {"vmid": "no-es-numero", "node": "pve1", "type": "qemu", "tags": etiquetas_lote()},
        {"vmid": 102, "node": "pve1", "type": "qemu", "tags": 12345},  # tags numérico
        {"vmid": 103, "type": "qemu", "tags": etiquetas_lote(), "status": "stopped"},  # sin node
        {"vmid": 104, "node": ["pve1"], "type": "qemu", "tags": [etiquetas_lote()]},
        "una cadena",
        None,
        {"vmid": 105, "node": "pve1", "type": "qemu", "tags": etiquetas_lote(), "name": 7},
    ]
    lista = m.listar()
    codigos = [x.codigo for x in lista.lotes]
    assert codigos == [CODIGO]
    vmids = [r.vmid for r in lista.lotes[0].recursos]
    assert 103 in vmids and 105 in vmids and 102 not in vmids and 104 not in vmids
    m.cluster.agregar_mv(105)
    detalle = m.detallar()
    sin_nodo = next(mv for mv in detalle.maquinas if mv.recurso.vmid == 103)
    assert MotivoNoDeshacible.CONFIG_ILEGIBLE in sin_nodo.motivos and not sin_nodo.deshacible
    assert m.cluster.lecturas_config == [("pve1", 105)]  # no se lee la config de una MV sin nodo


def test_ca_c1_4_2_una_respuesta_que_no_es_lista_no_rompe_la_lectura():
    m = Mundo()
    m.cluster.regla("GET", r"^/cluster/resources$", lambda _ll: {"data": "raro"})
    assert m.listar().lotes == ()


# --- RF-C1.3: nota de origen -----------------------------------------------------------------


def test_ca_c1_3_5_solo_se_extraen_las_lineas_lote_y_fecha_de_la_nota():
    nota = leer_nota_origen(nota_origen(CODIGO), CODIGO)
    assert nota.estado == EstadoNota.COINCIDE and nota.lote == CODIGO
    assert nota.fecha == datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    assert not hasattr(nota, "texto") and not hasattr(nota, "descripcion")


@pytest.mark.parametrize(
    "descripcion",
    [
        None,
        42,
        ["Creada con ProxLaunch 0.8.0"],
        "",
        "Notas libres del usuario",
        f"- Lote: {CODIGO}",  # sin la cabecera «Creada con ProxLaunch»
        f"Creada con ProxLaunch 0.8.0\n\n- Fecha: {FECHA_BASE}",  # sin línea de lote
        "Creada con ProxLaunch 0.8.0\n\n- Lote: AB12CD34",  # mayúsculas: no es un código válido
        "Creada con ProxLaunch 0.8.0\n\n- Lote:  ab12cd34",  # espacio de más
        "Creada con ProxLaunch 0.8.0\n\n- Lote: ab12cd34 y más texto",
        "Creada con ProxLaunch 0.8.0\n\n- Lote: ab12cd3",
        "Creada con ProxLaunch 0.8.0\n\n  - Lote: ab12cd34",  # sangrada
        "Creada con ProxLaunch 0.8.0\n\nTexto libre\n- Lote: ab12cd34",  # tras texto libre
        "creada con proxlaunch 0.8.0\n\n- Lote: ab12cd34",  # cabecera en minúsculas
    ],
)
def test_ca_c1_3_5_una_nota_que_no_cumple_la_forma_estricta_es_falta(descripcion):
    assert leer_nota_origen(descripcion, CODIGO).estado == EstadoNota.FALTA


def test_ca_c1_3_5_el_texto_libre_tras_el_bloque_no_se_interpreta():
    descripcion = nota_origen(
        CODIGO, extra=f"- Lote: {OTRO_CODIGO}\n<b>negrita</b> [x](http://e.x)"
    )
    nota = leer_nota_origen(descripcion, CODIGO)
    assert nota.estado == EstadoNota.COINCIDE and nota.lote == CODIGO


def test_ca_c1_3_5_prevalece_el_ultimo_bloque_de_la_nota():
    descripcion = nota_origen(OTRO_CODIGO) + "\n\n" + nota_origen(CODIGO)
    assert leer_nota_origen(descripcion, CODIGO).estado == EstadoNota.COINCIDE
    assert leer_nota_origen(descripcion, OTRO_CODIGO).estado == EstadoNota.OTRO_LOTE


def test_ca_c1_3_5_los_saltos_de_linea_de_windows_se_entienden():
    descripcion = nota_origen(CODIGO).replace("\n", "\r\n")
    assert leer_nota_origen(descripcion, CODIGO).estado == EstadoNota.COINCIDE


def test_ca_c1_3_5_una_nota_enorme_no_se_examina_mas_alla_del_limite_ni_falla():
    relleno = "x" * 40000
    descripcion = relleno + "\n" + nota_origen(CODIGO)
    # La cabecera queda fuera de los primeros 16 KiB: no se examina.
    assert leer_nota_origen(descripcion, CODIGO).estado == EstadoNota.FALTA
    assert leer_nota_origen(nota_origen(CODIGO) + "\n" + relleno, CODIGO).estado == (
        EstadoNota.COINCIDE
    )


def test_ca_c1_3_5_una_fecha_ilegible_deja_la_fecha_en_desconocida():
    nota = leer_nota_origen(nota_origen(CODIGO, fecha="ayer por la tarde"), CODIGO)
    assert nota.estado == EstadoNota.COINCIDE and nota.fecha is None


def test_ca_c1_3_5_una_fecha_sin_zona_se_interpreta_como_hora_local():
    nota = leer_nota_origen(nota_origen(CODIGO, fecha="2026-11-20T10:00:00"), CODIGO)
    assert nota.fecha is not None and nota.fecha.tzinfo is not None


def test_ca_c1_3_3_la_fecha_del_lote_es_la_mas_antigua_de_las_notas_validas():
    m = Mundo()
    m.cluster.agregar_mv(101, nota=nota_origen(CODIGO, "2026-11-20T10:00:00+00:00"))
    m.cluster.agregar_mv(102, nota=nota_origen(CODIGO, "2026-11-18T09:30:00+00:00"))
    m.cluster.agregar_mv(103, nota=nota_origen(CODIGO, "2026-11-21T08:00:00+00:00"))
    # Una nota de otro lote con una fecha aún más antigua no cuenta.
    m.cluster.agregar_mv(
        104,
        etiquetas=etiquetas_lote(CODIGO),
        nota=nota_origen(OTRO_CODIGO, "2020-01-01T00:00:00+00:00"),
    )
    assert m.detallar().fecha == datetime(2026, 11, 18, 9, 30, tzinfo=UTC)


def test_ca_c1_3_3_sin_notas_validas_la_fecha_es_desconocida():
    m = Mundo()
    m.cluster.agregar_mv(101, nota=False)
    assert m.detallar().fecha is None


# --- RF-C1.5: Comprobar (releer) ----------------------------------------------------------------


def test_ca_c1_5_2_comprobar_no_emite_ninguna_escritura():
    m = Mundo()
    for vmid in (101, 102):
        m.cluster.agregar_mv(vmid)
    m.listar()
    m.detallar()
    m.listar()
    m.detallar()  # segunda lectura = «Comprobar»
    assert m.cluster.solo_lecturas and m.cluster.escrituras == []


def test_ca_c1_5_3_las_mvs_nuevas_con_la_misma_etiqueta_aparecen_al_releer():
    """El núcleo las devuelve; la interfaz las deja desmarcadas (prueba de interfaz)."""
    m = Mundo()
    m.cluster.agregar_mv(101)
    assert [r.vmid for r in m.listar().lotes[0].recursos] == [101]
    m.cluster.agregar_mv(102)
    detalle = m.detallar()
    assert [mv.recurso.vmid for mv in detalle.maquinas] == [101, 102]


def test_ca_c1_5_1_una_mv_que_desaparece_no_bloquea_al_resto_del_lote():
    m = Mundo()
    for vmid in (101, 102, 103):
        m.cluster.agregar_mv(vmid)
    lote = m.lote()
    del m.cluster.vms[102]  # desaparece entre la lista y el detalle
    detalle = m.servicio.detallar(lote, threading.Event(), None)
    por_vmid = {mv.recurso.vmid: mv for mv in detalle.maquinas}
    assert MotivoNoDeshacible.YA_NO_EXISTE in por_vmid[102].motivos
    assert por_vmid[101].deshacible and por_vmid[103].deshacible
    assert detalle.completo is True


# --- RNF-C6.2: el texto del servidor no es confiable --------------------------------------------


def _hay_control_o_bidi(texto: str) -> bool:
    return any(not c.isprintable() or c in "‪‫‬‭‮⁦⁧⁨⁩"
               for c in texto)  # fmt: skip


def test_rnf_c6_2_el_nombre_de_la_mv_llega_sin_controles_ni_marcas_bidireccionales():
    m = Mundo()
    m.cluster.agregar_mv(101, "web‮10-bak\x07\nsegunda-linea")
    recurso = m.listar().lotes[0].recursos[0]
    assert recurso.nombre is not None and not _hay_control_o_bidi(recurso.nombre)


def test_rnf_c6_2_el_nombre_de_la_mv_se_acota_en_longitud():
    m = Mundo()
    m.cluster.agregar_mv(101, "N" * 5000)
    recurso = m.listar().lotes[0].recursos[0]
    assert recurso.nombre is not None and len(recurso.nombre) <= 256


def test_rnf_c6_2_las_etiquetas_llegan_sin_controles_ni_marcas_bidireccionales():
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.fila_lista[101] = {"tags": f"proxlaunch;lote-{CODIGO};‮evil\x07"}
    recurso = m.listar().lotes[0].recursos[0]
    assert not any(_hay_control_o_bidi(e) for e in recurso.etiquetas)


def test_rnf_c6_2_el_detalle_sanea_el_bloqueo_y_el_nodo_que_pone_en_los_parametros():
    m = Mundo()
    m.cluster.agregar_mv(101, lock="a\x07b‮c" + "Z" * 300)
    mv = m.detallar().maquinas[0]
    assert not _hay_control_o_bidi(mv.params["bloqueo"]) and len(mv.params["bloqueo"]) <= 64


def test_cl_una_mv_con_dos_etiquetas_de_lote_solo_es_deshacible_en_el_de_su_nota():
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas=f"proxlaunch;lote-{CODIGO};lote-{OTRO_CODIGO}")
    lista = m.listar()
    assert [x.codigo for x in lista.lotes] == [CODIGO, OTRO_CODIGO]
    assert m.detallar(CODIGO).maquinas[0].deshacible
    otro = m.detallar(OTRO_CODIGO).maquinas[0]
    assert not otro.deshacible and MotivoNoDeshacible.NOTA_OTRO_LOTE in otro.motivos
