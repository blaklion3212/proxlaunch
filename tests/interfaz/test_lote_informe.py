"""Informe del lote en texto plano y su guardado (RF-L19, CA-L19.x, CA-L23.3, RNF-L06)."""

from __future__ import annotations

import dataclasses
import time

import pytest

from proxlaunch.interfaz import informe_lote as il
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    EstadoMV,
    EstadoRollback,
    MotivoNoEnviada,
    Problema,
    ResultadoRollback,
    Severidad,
)
from proxlaunch.nucleo.registro import olvidar_secretos, registrar_secreto

from .apoyo_lote import entrada, entradas_de, informe_de, upid_con_usuario

EM = EstadoMV
IP = "10.0.0.5"
USUARIO = "ana@pve!lab"
SENTINELA = "SENTINELA-9f3c-secreto"


def lineas(texto: str) -> list[str]:
    return texto.splitlines()


@pytest.fixture
def mixto():
    """Un lote de seis máquinas con un resultado de cada tipo."""
    return informe_de(
        (
            entrada(0, EM.OK, upid=upid_con_usuario(101), t_inicio=0.0, t_fin=12.0),
            entrada(
                1, EM.CON_AVISOS, upid=upid_con_usuario(102), avisos=("creada_tras_comprobar",)
            ),
            entrada(
                2, EM.ERROR, error=ErrorProxLaunch(CodigoError.SIN_ESPACIO, {}, "no space left")
            ),
            entrada(3, EM.CONEXION_PERDIDA),
            entrada(4, EM.NO_ENVIADA, motivo_no_enviada=MotivoNoEnviada.CANCELADO),
            entrada(5, EM.OK, upid=upid_con_usuario(106)),
        )
    )


# --- Contenido (CA-L19.1) -----------------------------------------------------------------


def test_ca_l19_1_encabezado_con_fecha_perfil_version_y_topologia(mixto):
    t = il.texto_informe(mixto)
    assert lineas(t)[0] == "ProxLaunch — Informe del lote ab12cd34"
    assert "Fecha: 2026-11-13T10:00:00-05:00" in t
    assert "Perfil: Laboratorio" in t
    assert "Versión de Proxmox: 9.2" in t
    assert "Servidor: clúster «lab»" in t


def test_ca_l19_1_servidor_individual(mixto):
    individual = dataclasses.replace(mixto.metadatos, es_cluster=False, nombre_cluster=None)
    informe = dataclasses.replace(mixto, metadatos=individual)
    assert "Servidor: individual" in il.texto_informe(informe)


def test_ca_l19_1_resumen_con_los_contadores_por_resultado(mixto):
    t = il.texto_informe(mixto)
    for esperado in (
        "Pedidas: 6",
        "Creadas: 2",
        "Creadas con avisos: 1",
        "Con error: 1",
        "Sin confirmar (no sabemos si se crearon): 1",
        "No enviadas: 1",
    ):
        assert esperado in t, esperado


def test_ca_l19_1_tabla_por_maquina_con_nombre_vmid_nodo_resultado_duracion_y_upid(mixto):
    t = il.texto_informe(mixto)
    cab = next(ln for ln in lineas(t) if ln.startswith("N.º"))
    for col in ("Nombre", "VMID", "Nodo", "Resultado", "Duración", "UPID"):
        assert col in cab
    fila = next(ln for ln in lineas(t) if "web-01" in ln and "101" in ln and "pve1" in ln)
    assert "✓ Lista" in fila and "12 s" in fila
    assert "✕ Con error" in t and "? No sabemos si se creó" in t and "– No enviada" in t


def test_ca_l19_2_las_columnas_quedan_alineadas_para_fuente_monoespaciada(mixto):
    t = il.texto_informe(mixto)
    ls = lineas(t)
    i = next(k for k, ln in enumerate(ls) if ln.startswith("N.º"))
    cabecera, filas = ls[i], ls[i + 2 : i + 2 + 6]
    inicio_nombre = cabecera.index("Nombre")
    inicio_vmid = cabecera.index("VMID")
    for f in filas:
        assert f[inicio_nombre : inicio_nombre + 6] == f"web-{int(f.split()[0]):02d}"
        assert f[inicio_vmid : inicio_vmid + 3].strip().isdigit()


def test_ca_l19_4_un_error_sale_en_lenguaje_llano_y_con_su_texto_original(mixto):
    t = il.texto_informe(mixto)
    seccion = t[t.index("Detalle de las máquinas con problemas") :]
    assert "• web-03 (103):" in seccion
    assert "Código: sin_espacio" in seccion
    assert "Detalles técnicos: no space left" in seccion
    assert "• web-02 (102): Se creó aunque Proxmox tardó en responder." in seccion
    assert "• web-05 (105): «web-05» no se envió (cancelaste el lote)." in seccion


def test_ca_l19_1_parametros_de_la_plantilla_en_resumen(mixto):
    t = il.texto_informe(mixto)
    assert "Configuración de las máquinas" in t
    assert "Procesadores: 2 (1 × 2)" in t and "Memoria: 2 GiB" in t
    assert "Discos: 10 GiB en local-lvm" in t and "Redes: vmbr0" in t


def test_ca_l19_1_avisos_del_plan_se_listan(mixto):
    informe = informe_de(
        mixto.entradas,
        problemas=[
            Problema("V-L06", Severidad.AVISO, "nombre", {"nombre": "web-01", "vmid": "105"})
        ],
    )
    t = il.texto_informe(informe)
    assert "Avisos del plan" in t
    assert "⚠ Ya existe una máquina llamada «web-01» (número 105)." in t


def test_ca_l19_1_la_seccion_deshacer_aparece_solo_si_hubo(mixto):
    assert "Deshacer" not in il.texto_informe(mixto)
    rb = [
        ResultadoRollback(101, "pve1", "web-01", EstadoRollback.ELIMINADA),
        ResultadoRollback(
            102,
            "pve1",
            "web-02",
            EstadoRollback.OMITIDA,
            error=ErrorProxLaunch(CodigoError.ROLLBACK_ENCENDIDA, {"nombre": "web-02"}),
        ),
    ]
    t = il.texto_informe(informe_de(mixto.entradas, rollback=rb))
    sec = t[t.index("\nDeshacer\n") :]
    assert "web-01" in sec and "Eliminada" in sec
    assert "web-02" in sec and "está encendida" in sec


def test_ca_l11_8_una_simulacion_se_titula_simulacion_y_no_dice_como_buscar_maquinas(mixto):
    t = il.texto_informe(informe_de(mixto.entradas, simulacion=True))
    assert lineas(t)[0] == "ProxLaunch — Simulación del lote ab12cd34"
    assert "SIMULACIÓN — no se creó nada." in t
    assert "Cómo encontrar estas máquinas" not in t


def test_ca_l18_14_el_informe_explica_como_encontrar_las_maquinas_con_etiqueta_y_rango(mixto):
    t = il.texto_informe(mixto)
    assert "«proxlaunch»" in t and "«lote-ab12cd34»" in t
    assert "sus números son 101–106" in t


def test_ca_l19_5_el_informe_parcial_tambien_explica_como_ver_que_se_creo():
    parcial = informe_de(entradas_de([EM.OK, EM.CREANDO, EM.PENDIENTE]))
    assert "Cómo encontrar estas máquinas en Proxmox" in il.texto_informe(parcial)


def test_el_informe_es_determinista_para_el_mismo_libro(mixto):
    assert il.texto_informe(mixto) == il.texto_informe(mixto)


def test_el_informe_termina_en_salto_de_linea(mixto):
    assert il.texto_informe(mixto).endswith("\n")


def test_ca_l19_7_un_informe_de_cien_maquinas_se_genera_en_menos_de_un_segundo():
    informe = informe_de(entradas_de([EM.OK] * 90 + [EM.ERROR] * 10, upid="x"))
    inicio = time.perf_counter()
    texto = il.texto_informe(informe)
    assert time.perf_counter() - inicio < 1.0
    assert texto.count("web-") >= 100


# --- Privacidad (CA-L19.3, RNF-L06) ------------------------------------------------------------


def test_ca_l19_3_el_upid_se_muestra_sin_el_usuario(mixto):
    t = il.texto_informe(mixto)
    assert "ana@pve" not in t and "root@pam" not in t
    assert "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:101:…:" in t


@pytest.mark.parametrize(
    "upid, esperado",
    [
        (None, "—"),
        ("", "—"),
        (
            "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:root@pam:",
            "UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:…:",
        ),
        ("texto-raro", "texto-raro"),
        ("UPID:corto:1:2", "UPID:corto:1:2"),
    ],
)
def test_upid_sin_usuario(upid, esperado):
    assert il.upid_sin_usuario(upid) == esperado


def test_ca_l19_3_el_nombre_del_perfil_es_lo_unico_que_identifica_al_servidor(mixto):
    t = il.texto_informe(mixto)
    assert IP not in t and USUARIO not in t and "10.0." not in t


def test_rnf_l06_centinela_registrado_como_secreto_no_aparece_en_el_informe():
    registrar_secreto(SENTINELA)
    try:
        err = ErrorProxLaunch(
            CodigoError.DESCONOCIDO, {}, f"PVEAPIToken=ana@pve!lab={SENTINELA} rechazado"
        )
        informe = informe_de((entrada(0, EM.ERROR, error=err),))
        t = il.texto_informe(informe)
        assert SENTINELA not in t
        assert "***" in t
    finally:
        olvidar_secretos()


def test_rnf_l06_el_informe_no_contiene_cabeceras_ni_marcas_de_credenciales(mixto):
    t = il.texto_informe(mixto).lower()
    for prohibido in (
        "authorization",
        "csrfpreventiontoken",
        "pveauthcookie",
        "password",
        "ticket",
    ):
        assert prohibido not in t


# --- Utilidades de formato -----------------------------------------------------------------


@pytest.mark.parametrize(
    "segundos, esperado",
    [
        (None, "—"),
        (0, "0 s"),
        (0.4, "0 s"),
        (12, "12 s"),
        (59.4, "59 s"),
        (65, "1 min 5 s"),
        (3600, "60 min 0 s"),
    ],
)
def test_texto_duracion(segundos, esperado):
    assert il.texto_duracion(segundos) == esperado


def test_texto_rangos_acepta_cualquier_iterable_y_ordena():
    assert il.texto_rangos(iter([5, 3, 4, 9])) == "3–5, 9"


def test_nombre_sugerido_distingue_simulacion_y_lleva_el_id(mixto):
    assert il.nombre_archivo_sugerido(mixto) == "informe-lote-ab12cd34.txt"
    assert il.nombre_archivo_sugerido(informe_de(mixto.entradas, simulacion=True)) == (
        "simulacion-ab12cd34.txt"
    )


# --- Guardado (CA-L19.2, RF-L23) -----------------------------------------------------------------


def test_escribir_informe_crea_la_carpeta_y_escribe_utf8(tmp_path):
    ruta = tmp_path / "con espacios" / "ñandú" / "informe.txt"
    il.escribir_informe(ruta, "Máquina «ñ» ✓\n")
    assert ruta.read_bytes() == "Máquina «ñ» ✓\n".encode()


def test_ca_l23_3_el_informe_parcial_se_guarda_y_deja_un_aviso_de_un_solo_uso(tmp_path, mixto):
    ruta = il.guardar_informe_parcial(mixto, tmp_path)
    assert ruta == tmp_path / "parcial-ab12cd34.txt"
    assert ruta.read_text(encoding="utf-8") == il.texto_informe(mixto)
    assert il.tomar_aviso_informe_parcial(tmp_path) == ruta
    assert il.tomar_aviso_informe_parcial(tmp_path) is None  # solo se avisa una vez


def test_no_hay_aviso_si_nunca_se_guardo_un_informe_parcial(tmp_path):
    assert il.tomar_aviso_informe_parcial(tmp_path) is None
    assert il.tomar_aviso_informe_parcial(tmp_path / "no-existe") is None


def test_el_aviso_se_descarta_si_el_informe_ya_no_existe(tmp_path, mixto):
    ruta = il.guardar_informe_parcial(mixto, tmp_path)
    ruta.unlink()
    assert il.tomar_aviso_informe_parcial(tmp_path) is None


def test_guardar_el_informe_parcial_nunca_lanza_aunque_no_se_pueda_escribir(tmp_path, mixto):
    bloqueo = tmp_path / "es-un-archivo"
    bloqueo.write_text("x", encoding="utf-8")
    assert il.guardar_informe_parcial(mixto, bloqueo) is None


def test_el_informe_parcial_de_un_segundo_lote_reemplaza_el_aviso_del_primero(tmp_path, mixto):
    il.guardar_informe_parcial(mixto, tmp_path)
    otro = informe_de(mixto.entradas, id_lote="ffffeeee")
    ruta = il.guardar_informe_parcial(otro, tmp_path)
    assert il.tomar_aviso_informe_parcial(tmp_path) == ruta
