"""Inventario de lotes (fase C, C1): exportación a CSV e IP del agente.

Requisitos: RF-C1.6 (CA-C1.6.1 a CA-C1.6.4), RF-C1.7 (CA-C1.7.1 a CA-C1.7.4). Doble: clúster en
memoria con guion de respuestas del agente; ningún servidor real.
"""

from __future__ import annotations

import csv
import io
import os
import threading
from pathlib import Path

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.inventario.exportacion import (
    COLUMNAS_EXPORTACION,
    COLUMNAS_IP,
    exportar_csv,
)
from proxlaunch.nucleo.inventario.modelos import EstadoIpInventario, IpInventario
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.opciones.disponibilidad_c import disponibilidad_fase_c
from proxlaunch.nucleo.opciones.modelos import OpcionC
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad

from .apoyo_api import TOKEN_SECRETO
from .apoyo_fase_c_inventario import CODIGO, Mundo, etiquetas_lote, nota_origen, permisos
from .apoyo_lote import (
    CENTINELA_CLAVE,
    CENTINELA_TOKEN,
    error_http,
    respuesta_agente,
)

MAC = "AA:BB:CC:DD:EE:01"


def _leer(ruta: Path) -> tuple[list[str], list[list[str]]]:
    texto = ruta.read_bytes().decode("utf-8-sig")
    filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    return filas[0], filas[1:]


def _lote_de_tres(m: Mundo) -> None:
    m.cluster.agregar_mv(101, "web-01")
    m.cluster.agregar_mv(102, "web-02", status="running")
    m.cluster.agregar_mv(103, "web-03", nota=False)


# --- RF-C1.6: exportar CSV ----------------------------------------------------------------------


def test_ca_c1_6_1_un_lote_de_tres_mvs_da_un_encabezado_y_tres_filas_con_las_columnas(tmp_path):
    m = Mundo()
    _lote_de_tres(m)
    ruta = tmp_path / "lote.csv"
    exportar_csv(ruta, [m.detallar()], None)
    encabezado, filas = _leer(ruta)
    assert encabezado == [
        "lote", "fecha", "nombre", "vmid", "nodo", "estado", "bloqueo", "plantilla",
        "protegida", "etiquetas", "nota_origen", "deshacible", "motivo",
    ]  # fmt: skip
    assert tuple(encabezado) == COLUMNAS_EXPORTACION
    assert len(filas) == 3 and all(len(f) == len(encabezado) for f in filas)
    por_vmid = {f[3]: dict(zip(encabezado, f, strict=True)) for f in filas}
    assert por_vmid["101"]["lote"] == CODIGO and por_vmid["101"]["deshacible"] == "sí"
    assert por_vmid["101"]["nota_origen"] == "coincide" and por_vmid["101"]["nodo"] == "pve1"
    assert por_vmid["102"]["estado"] == "running"
    assert por_vmid["103"]["deshacible"] == "no" and por_vmid["103"]["nota_origen"] == "falta"
    assert por_vmid["103"]["motivo"] == "sin_nota"
    assert por_vmid["101"]["fecha"].startswith("2026-11-20T10:00:00")


def test_ca_c1_6_1_el_lector_csv_de_la_app_lo_lee_como_archivo_cualquiera(tmp_path):
    from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv

    m = Mundo()
    _lote_de_tres(m)
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], None)
    tabla = leer_archivo_csv(ruta)
    assert tabla.encabezado == COLUMNAS_EXPORTACION
    assert len(tabla.filas) == 3 and tabla.deteccion.separador == ";"
    assert [f.celdas[3] for f in tabla.filas] == ["101", "102", "103"]


def test_ca_c1_6_1_es_utf8_con_bom_y_se_lee_como_csv_cualquiera(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101, "máquina-ñandú")
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], None)
    crudo = ruta.read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")
    _, filas = _leer(ruta)
    assert filas[0][2] == "máquina-ñandú"


@pytest.mark.skipif(os.name == "nt", reason="permisos POSIX")
def test_ca_c1_6_1_el_archivo_queda_con_permisos_privados(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101)
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], None)
    assert ruta.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "nombre",
    ['=HYPERLINK("http://malo")', "+cmd|' /C calc'!A0", "-2+3", "@SUM(1+1)", "\t=1+1", "=1+1\n=2"],
)
def test_ca_c1_6_2_un_nombre_con_formula_se_escribe_neutralizado(tmp_path, nombre):
    m = Mundo()
    m.cluster.agregar_mv(101, "ok")
    detalle = m.detallar()
    # El nombre viene de la lista del servidor: se pone ahí.
    m.cluster.fila_lista[101] = {"name": nombre}
    detalle = m.detallar()
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [detalle], None)
    _, filas = _leer(ruta)
    celda = filas[0][2]
    assert celda[:1] not in ("=", "+", "-", "@", "\t"), celda
    assert celda.startswith("'") or celda[:1].isalnum()


def test_ca_c1_6_2_las_etiquetas_y_el_motivo_tambien_se_neutralizan(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101, etiquetas="=cmd;proxlaunch;lote-" + CODIGO, nota=False)
    m.cluster.fila_lista[101] = {"tags": "=cmd;proxlaunch;lote-" + CODIGO}
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], None)
    _, filas = _leer(ruta)
    assert not filas[0][9].startswith("=")


def test_ca_c1_6_2_las_celdas_de_texto_externo_se_acotan_en_longitud(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101)
    m.cluster.fila_lista[101] = {"name": "N" * 5000, "tags": etiquetas_lote() + ";" + "t" * 5000}
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], None)
    _, filas = _leer(ruta)
    assert all(len(c) <= 260 for c in filas[0])


def test_ca_c1_6_3_el_csv_no_contiene_tokens_contrasenas_ni_la_nota_completa(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(
        101,
        nota=nota_origen(
            CODIGO, extra=f"NOTA-LIBRE-PRIVADA password={CENTINELA_CLAVE} token={CENTINELA_TOKEN}"
        ),
        cipassword="**********",
        sshkeys="ssh-ed25519%20AAAA",
    )
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], None)
    texto = ruta.read_bytes().decode("utf-8-sig")
    for prohibido in (
        "NOTA-LIBRE-PRIVADA", CENTINELA_CLAVE, CENTINELA_TOKEN, TOKEN_SECRETO,
        "Creada con ProxLaunch", "cipassword", "sshkeys", "ssh-ed25519",
    ):  # fmt: skip
        assert prohibido not in texto, prohibido
    assert "coincide" in texto  # de la nota solo se conserva el estado


def test_ca_c1_6_3_con_ip_el_csv_tampoco_trae_otros_datos_de_la_config(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101, status="running", agent=1, net0=f"virtio={MAC},bridge=vmbr0")
    detalle = m.detallar()
    ips = {101: IpInventario(EstadoIpInventario.OK, "10.0.0.5")}
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [detalle], ips)
    texto = ruta.read_bytes().decode("utf-8-sig")
    assert MAC not in texto and "vmbr0" not in texto


def test_ca_c1_6_4_exportar_no_emite_escrituras_en_el_servidor_y_solo_escribe_el_archivo(tmp_path):
    from proxlaunch.interfaz.trabajadores import exportar_inventario_csv

    m = Mundo()
    _lote_de_tres(m)
    ruta = tmp_path / "x.csv"
    assert not ruta.exists()
    resultado = exportar_inventario_csv(
        m.sesion, m.reloj, ruta, [], [m.lote()], {}, False, None,
        al_cambiar_etapa=lambda _e: None, al_enviar=lambda _t: None, cancelado=threading.Event(),
    )  # fmt: skip
    assert resultado[0] == ruta and ruta.exists()
    assert m.cluster.solo_lecturas and m.cluster.escrituras == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.csv"]  # sin temporales ni extras


def test_ca_c1_6_4_si_se_cancela_antes_de_escribir_no_se_crea_el_archivo(tmp_path):
    from proxlaunch.interfaz.trabajadores import exportar_inventario_csv

    m = Mundo()
    _lote_de_tres(m)
    cancelado = threading.Event()
    cancelado.set()
    ruta = tmp_path / "x.csv"
    resultado = exportar_inventario_csv(
        m.sesion, m.reloj, ruta, [], [m.lote()], {}, False, None,
        al_cambiar_etapa=lambda _e: None, al_enviar=lambda _t: None, cancelado=cancelado,
    )  # fmt: skip
    assert resultado[0] is None and not ruta.exists()


def test_ca_c1_6_4_una_ruta_no_escribible_da_un_error_controlado(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101)
    with pytest.raises(ErrorProxLaunch) as e:
        exportar_csv(tmp_path / "no-existe" / "x.csv", [m.detallar()], None)
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_c1_6_exportar_todos_los_lotes_une_las_filas_de_cada_lote(tmp_path):
    m = Mundo()
    m.cluster.agregar_mv(101, lote="aaaaaaaa")
    m.cluster.agregar_mv(102, lote="bbbbbbbb")
    m.cluster.agregar_mv(103, lote="bbbbbbbb")
    detalles = [m.detallar("aaaaaaaa"), m.detallar("bbbbbbbb")]
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, detalles, None)
    _, filas = _leer(ruta)
    assert [(f[0], f[3]) for f in filas] == [
        ("aaaaaaaa", "101"),
        ("bbbbbbbb", "102"),
        ("bbbbbbbb", "103"),
    ]


def test_ca_c1_6_el_csv_de_un_lote_vacio_solo_lleva_el_encabezado(tmp_path):
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [], None)
    encabezado, filas = _leer(ruta)
    assert tuple(encabezado) == COLUMNAS_EXPORTACION and filas == []


def test_ca_c1_6_con_ip_las_columnas_nuevas_van_al_final_y_las_mvs_sin_dato_quedan_vacias(tmp_path):
    m = Mundo()
    _lote_de_tres(m)
    ips = {101: IpInventario(EstadoIpInventario.OK, "10.0.0.5"),
           102: IpInventario(EstadoIpInventario.APAGADA)}  # fmt: skip
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [m.detallar()], ips)
    encabezado, filas = _leer(ruta)
    assert tuple(encabezado) == COLUMNAS_EXPORTACION + COLUMNAS_IP
    por_vmid = {f[3]: f[-2:] for f in filas}
    assert por_vmid == {"101": ["10.0.0.5", "ok"], "102": ["", "apagada"], "103": ["", ""]}


# --- RF-C1.7: IP del agente ---------------------------------------------------------------------


def _mundo_ip() -> Mundo:
    m = Mundo()
    m.cluster.agregar_mv(101, "enc", status="running", agent=1, net0=f"virtio={MAC},bridge=vmbr0")
    m.cluster.agregar_mv(102, "apagada", status="stopped", agent=1)
    m.cluster.agregar_mv(103, "sin-agente", status="running", net0=f"virtio={MAC},bridge=vmbr0")
    m.cluster.agregar_mv(104, "agente-cero", status="running", agent=0)
    return m


def test_ca_c1_7_1_una_mv_encendida_con_agente_da_la_ip_con_los_filtros_de_la_fase_b():
    m = _mundo_ip()
    m.cluster.guion_agente(
        101,
        respuesta_agente(
            ("lo", "00:00:00:00:00:00", ("127.0.0.1",)),
            ("docker0", "02:42:00:00:00:01", ("172.17.0.1",)),
            ("eth0", MAC, ("fe80::1", "10.0.0.5")),
        ),
    )
    ips = m.servicio.obtener_ips(m.detallar(), [101], threading.Event(), None)
    assert ips[101] == IpInventario(EstadoIpInventario.OK, "10.0.0.5")


def test_ca_c1_7_1_si_el_agente_solo_tiene_direcciones_descartables_no_hay_ip():
    m = _mundo_ip()
    m.cluster.guion_agente(101, respuesta_agente(("lo", None, ("127.0.0.1",))))
    ips = m.servicio.obtener_ips(m.detallar(), [101], threading.Event(), None)
    assert ips[101].estado == EstadoIpInventario.SIN_IP and ips[101].ip is None


def test_ca_c1_7_2_apagada_o_sin_agente_deja_ip_vacia_sin_preguntar_al_agente():
    m = _mundo_ip()
    ips = m.servicio.obtener_ips(m.detallar(), [102, 103, 104], threading.Event(), None)
    assert ips[102] == IpInventario(EstadoIpInventario.APAGADA)
    assert ips[103] == IpInventario(EstadoIpInventario.SIN_AGENTE)
    assert ips[104] == IpInventario(EstadoIpInventario.SIN_AGENTE)
    assert m.cluster.llamadas_agente == []  # ni una sola petición al agente


def test_ca_c1_7_2_el_csv_lleva_apagada_y_sin_agente_en_ip_estado(tmp_path):
    m = _mundo_ip()
    detalle = m.detallar()
    ips = m.servicio.obtener_ips(detalle, [102, 103], threading.Event(), None)
    ruta = tmp_path / "x.csv"
    exportar_csv(ruta, [detalle], ips)
    encabezado, filas = _leer(ruta)
    por_vmid = {f[3]: (f[-2], f[-1]) for f in filas}
    assert por_vmid["102"] == ("", "apagada") and por_vmid["103"] == ("", "sin_agente")


def test_ca_c1_7_el_agente_que_no_responde_se_dice_sin_romper_el_resto():
    m = _mundo_ip()
    m.cluster.agente_guion[101] = [error_http(500, "QEMU guest agent is not running")]
    ips = m.servicio.obtener_ips(m.detallar(), [101, 102], threading.Event(), None)
    assert ips[101].estado in (EstadoIpInventario.SIN_AGENTE, EstadoIpInventario.SIN_RESPUESTA)
    assert ips[102].estado == EstadoIpInventario.APAGADA


def test_ca_c1_7_con_el_privilegio_del_agente_negado_no_se_pregunta_al_agente():
    m = _mundo_ip()
    sin = permisos({"/": {"VM.Audit": 1}})
    ips = m.servicio.obtener_ips(m.detallar(), [101], threading.Event(), sin)
    assert ips[101].estado == EstadoIpInventario.SIN_PERMISO
    assert m.cluster.llamadas_agente == []


def test_ca_c1_7_4_la_sonda_nunca_pasa_de_4_simultaneas_y_cada_mv_recibe_una_sola():
    m = Mundo()
    for vmid in range(1000, 1040):
        m.cluster.agregar_mv(vmid, status="running", agent=1, net0=f"virtio={MAC},bridge=vmbr0")
    activas = 0
    maximo = 0
    cerrojo = threading.Lock()
    juntas = threading.Event()

    def sonda(_ll):
        nonlocal activas, maximo
        with cerrojo:
            activas += 1
            maximo = max(maximo, activas)
            if activas >= 5:
                juntas.set()
        try:
            juntas.wait(0.01)
            return respuesta_agente(("eth0", MAC, ("10.0.0.5",)))
        finally:
            with cerrojo:
                activas -= 1

    for vmid in range(1000, 1040):
        m.cluster.guion_agente(vmid, sonda)
    detalle = m.detallar()
    ips = m.servicio.obtener_ips(detalle, [mv.recurso.vmid for mv in detalle.maquinas],
                                 threading.Event(), None)  # fmt: skip
    assert len(ips) == 40 and all(i.estado == EstadoIpInventario.OK for i in ips.values())
    assert 1 < maximo <= 4
    assert set(m.cluster.sondeos_agente.values()) == {1}


def test_ca_c1_7_4_cancelar_la_sonda_deja_sin_resultado_a_las_no_procesadas():
    m = _mundo_ip()
    cancelado = threading.Event()
    cancelado.set()
    assert m.servicio.obtener_ips(m.detallar(), [101, 102], cancelado, None) == {}
    assert m.cluster.llamadas_agente == []


@pytest.mark.parametrize(
    ("version", "privilegio"),
    [((8, 4), "VM.Monitor"), ((9, 2), "VM.GuestAgent.Audit")],
)
def test_ca_c1_7_3_sin_el_privilegio_del_agente_de_la_version_la_casilla_se_deshabilita(
    version, privilegio
):
    caps = capacidades_para(Version(f"{version[0]}.{version[1]}", *version, 0), None)
    sin = permisos({"/": {"VM.Audit": 1, "VM.Allocate": 1}})
    estado = disponibilidad_fase_c(sin, caps)[OpcionC.IP_INVENTARIO]
    assert estado.disponibilidad == Disponibilidad.NO
    assert estado.params["privilegio"] == privilegio


@pytest.mark.parametrize(
    ("version", "privilegio"),
    [((8, 4), "VM.Monitor"), ((9, 2), "VM.GuestAgent.Audit")],
)
def test_ca_c1_7_3_con_el_privilegio_correcto_la_ip_esta_disponible(version, privilegio):
    caps = capacidades_para(Version(f"{version[0]}.{version[1]}", *version, 0), None)
    con = permisos({"/": {privilegio: 1}})
    assert disponibilidad_fase_c(con, caps)[OpcionC.IP_INVENTARIO].disponibilidad == (
        Disponibilidad.SI
    )


def test_ca_c1_7_3_con_permisos_desconocidos_no_se_bloquea():
    caps = capacidades_para(Version("9.2", 9, 2, 0), None)
    estado = disponibilidad_fase_c(None, caps)[OpcionC.IP_INVENTARIO]
    assert estado.disponibilidad != Disponibilidad.NO
