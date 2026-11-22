"""B3: informe y exportación «nombre → IP» (RF-B3.6) y salidas sin cloud-init (CA-B7.2.5).

Requisitos: CA-B3.6.1, CA-B3.6.2, CA-B3.6.3, CA-B3.6.5 (la parte del núcleo: escritura atómica) y
el resumen «n con IP / m sin IP / k no aplicable». CA-B3.6.4 (el botón «Exportar IPs…» no se muestra
sin B3) es de la interfaz y la cubren las pruebas de ``tests/interfaz``.

Las entradas salen de un lote real (motor + ``EsperaIp`` + ``enlazar_espera`` sobre un doble del
servidor); los datos sensibles son centinelas únicos que no pueden aparecer en ninguna salida.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import os
from pathlib import Path

import pytest

from proxlaunch.nucleo.agente.exportacion import (
    COLUMNAS_IPS,
    filas_ips,
    guardar_ips_csv,
    lista_ips_texto,
)
from proxlaunch.nucleo.agente.modelos import EstadoIp, ResultadoIp
from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import construir_informe, resumen_ips
from proxlaunch.nucleo.lote.libro import Libro
from proxlaunch.nucleo.lote.modelos import EntradaLibro, MetadatosInforme
from proxlaunch.nucleo.secreto import Secreto

from .apoyo_fase_b_agente import (
    MAC_OTRA,
    correr,
    ejecutar_espera,
    interfaz,
    lote,
    mac_de,
    respuesta,
    respuesta_con_ip,
    vmids,
)
from .apoyo_lote import volcar

CENTINELA_CONTRASENA = "S3cr3t-Prueba!"
CENTINELA_USUARIO = "usuario-ci-P3-7f3a"
CENTINELA_CLAVE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5CENTINELAP3clave ana@pc"
METADATOS = MetadatosInforme("perfil", "9.2.1", True, "lab", "2026-11-22T10:00:00")


def lote_de_tres() -> tuple[list[EntradaLibro], list[int]]:
    """Tres MVs encendidas: la 1.ª con IP, la 2.ª con IP y otra interfaz, la 3.ª sin IP."""
    b, plan = lote(3, plazo=30)
    a, c, d = vmids(plan)
    b.cluster.guion[a] = [respuesta_con_ip("192.168.1.50", mac_de(a))]
    b.cluster.guion[c] = [
        respuesta(
            interfaz("ens18", mac_de(c), "192.168.1.51", "2001:db8::51"),
            interfaz("ens19", MAC_OTRA, "10.20.30.40"),
        )
    ]
    b.cluster.guion[d] = [respuesta(interfaz("ens18", mac_de(d)))]  # responde, pero sin IP
    libro, espera, _ = correr(b, plan)
    ejecutar_espera(b, espera)
    return libro.instantanea(), [a, c, d]


def leer_csv(ruta: Path) -> list[list[str]]:
    texto = ruta.read_bytes().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto, newline=""), delimiter=","))


def con_nombre(entrada: EntradaLibro, nombre: str) -> EntradaLibro:
    return dataclasses.replace(
        entrada, elemento=dataclasses.replace(entrada.elemento, nombre=nombre)
    )


# --- CA-B3.6.1: CSV de tres MVs ------------------------------------------------------------------


def test_ca_b3_6_1_el_csv_tiene_una_fila_por_mv_y_la_sin_ip_va_con_ip_vacia(tmp_path):
    entradas, (a, c, d) = lote_de_tres()
    ruta = guardar_ips_csv(tmp_path / "ips.csv", entradas)
    filas = leer_csv(ruta)
    assert filas[0] == ["nombre", "vmid", "nodo", "ip", "otras_ips", "estado"]
    assert len(filas) == 1 + 3
    por_vmid = {int(f[1]): f for f in filas[1:]}
    assert por_vmid[a][3] == "192.168.1.50" and por_vmid[a][5] == "obtenida"
    assert por_vmid[c][3] == "192.168.1.51" and por_vmid[c][5] == "obtenida"
    assert por_vmid[d][3] == "" and por_vmid[d][4] == "" and por_vmid[d][5] == "sin_ip"
    assert [f[2] for f in filas[1:]] == ["pve1"] * 3  # nodo de cada MV


def test_las_otras_ips_van_en_su_columna_separadas_por_espacio_y_sin_la_principal(tmp_path):
    entradas, (_, c, _) = lote_de_tres()
    fila = next(
        f for f in leer_csv(guardar_ips_csv(tmp_path / "ips.csv", entradas))[1:] if int(f[1]) == c
    )
    assert set(fila[4].split(" ")) == {"2001:db8::51", "10.20.30.40"}
    assert "192.168.1.51" not in fila[4].split(" ")


def test_las_columnas_y_el_orden_de_las_filas_son_los_del_plan():
    entradas, vmids_plan = lote_de_tres()
    assert COLUMNAS_IPS == ("nombre", "vmid", "nodo", "ip", "otras_ips", "estado")
    assert [f[1] for f in filas_ips(entradas)] == vmids_plan
    assert all(len(f) == len(COLUMNAS_IPS) for f in filas_ips(entradas))


def test_el_formato_es_utf8_con_bom_separador_coma(tmp_path):
    entradas, _ = lote_de_tres()
    bruto = guardar_ips_csv(tmp_path / "ips.csv", entradas).read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")
    primera = bruto.decode("utf-8-sig").split("\r\n", 1)[0]
    assert primera == '"nombre","vmid","nodo","ip","otras_ips","estado"'
    assert ";" not in primera


def test_solo_se_listan_las_mvs_que_pidieron_esperar_la_ip(tmp_path):
    b, plan = lote(2, esperar_ip=False)
    libro, _, _ = correr(b, plan)
    assert filas_ips(libro.instantanea()) == []
    assert lista_ips_texto(libro.instantanea()) == ""
    assert leer_csv(guardar_ips_csv(tmp_path / "vacio.csv", libro.instantanea())) == [
        list(COLUMNAS_IPS)
    ]


def test_una_mv_con_espera_pedida_y_sin_resultado_aun_figura_como_pendiente():
    b, plan = lote(2)
    libro, _, _ = correr(b, plan)  # la espera no se ha ejecutado
    assert [f[5] for f in filas_ips(libro.instantanea())] == ["pendiente", "pendiente"]


def test_los_estados_de_ip_se_exportan_con_su_nombre_estable():
    entradas, _ = lote_de_tres()
    base = entradas[2]
    for estado in EstadoIp:
        entrada = dataclasses.replace(base, ip=ResultadoIp(estado))
        assert filas_ips([entrada])[0][5] == estado.value


def test_una_mv_omitida_porque_no_se_encendio_se_exporta_como_omitida():
    b, plan = lote(2, encender=False)
    libro, espera, _ = correr(b, plan)
    ejecutar_espera(b, espera)
    assert [f[5] for f in filas_ips(libro.instantanea())] == ["omitida", "omitida"]


# --- «Copiar lista» ------------------------------------------------------------------------------


def test_la_lista_para_copiar_es_nombre_tab_ip_solo_de_las_que_tienen_ip():
    entradas, (a, c, d) = lote_de_tres()
    texto = lista_ips_texto(entradas)
    lineas = texto.split("\n")
    nombre = {e.elemento.vmid: e.elemento.nombre for e in entradas}
    assert lineas == [f"{nombre[a]}\t192.168.1.50", f"{nombre[c]}\t192.168.1.51"]
    assert nombre[d] not in texto


# --- CA-B3.6.2: fórmulas en hojas de cálculo -----------------------------------------------------


@pytest.mark.parametrize(
    "nombre",
    ['=HYPERLINK("http://x","y")', "+cmd|' /C calc'!A0", "-2+3", "@SUM(1+1)", "  =1+1", "\t=1+1"],
)
def test_ca_b3_6_2_un_nombre_que_empieza_como_formula_se_neutraliza(tmp_path, nombre):
    entradas, _ = lote_de_tres()
    peligrosa = con_nombre(entradas[0], nombre)
    fila = leer_csv(guardar_ips_csv(tmp_path / "ips.csv", [peligrosa]))[1]
    celda = fila[0]
    assert celda.startswith("'")  # el apóstrofe impide que la hoja la evalúe
    assert nombre.strip() in celda  # el contenido original se conserva, solo se prefija
    assert not celda.lstrip().startswith(("=", "+", "-", "@"))


def test_ca_b3_6_2_una_ip_o_texto_raro_en_cualquier_celda_tambien_se_neutraliza(tmp_path):
    entradas, _ = lote_de_tres()
    raro = dataclasses.replace(
        entradas[0], ip=ResultadoIp(EstadoIp.OBTENIDA, principal="=1+1", otras=("@x", "-y"))
    )
    fila = leer_csv(guardar_ips_csv(tmp_path / "ips.csv", [raro]))[1]
    assert fila[3] == "'=1+1"
    assert fila[4].startswith(
        "'@x"
    )  # solo importa el inicio de la celda; el resto va tras un espacio


def test_ca_b3_6_2_el_nombre_normal_no_se_altera(tmp_path):
    entradas, _ = lote_de_tres()
    fila = leer_csv(guardar_ips_csv(tmp_path / "ips.csv", entradas))[1]
    assert fila[0] == entradas[0].elemento.nombre


# --- CA-B3.6.3: ningún dato de cloud-init (ni la contraseña centinela) ---------------------------


def entradas_con_cloudinit() -> list[EntradaLibro]:
    """Entradas cuyo ``cfg`` lleva usuario, clave y contraseña de cloud-init (solo en memoria)."""
    entradas, _ = lote_de_tres()
    ci = ConfigCloudInit(
        usuario=CENTINELA_USUARIO,
        claves=(CENTINELA_CLAVE,),
        contrasena=Secreto(CENTINELA_CONTRASENA),
        dns=("10.0.0.2",),
        dominio="interno.centinela.example",
    )
    resultado = []
    for e in entradas:
        cfg = dataclasses.replace(e.elemento.cfg, cloudinit=ci)
        resultado.append(dataclasses.replace(e, elemento=dataclasses.replace(e.elemento, cfg=cfg)))
    return resultado


def test_ca_b3_6_3_el_csv_y_la_lista_no_contienen_ningun_valor_de_cloudinit(tmp_path):
    entradas = entradas_con_cloudinit()
    bruto = guardar_ips_csv(tmp_path / "ips.csv", entradas).read_bytes().decode("utf-8-sig")
    texto = lista_ips_texto(entradas)
    for salida in (bruto, texto, repr(filas_ips(entradas))):
        for centinela in (
            CENTINELA_CONTRASENA,
            CENTINELA_USUARIO,
            "CENTINELAP3clave",
            "interno.centinela",
        ):
            assert centinela not in salida


def test_ca_b3_7_2_5_el_informe_quita_el_cloudinit_de_todas_las_configuraciones():
    """CA-B7.2.5: el libro conserva el cloud-init en memoria; lo que SALE de él, no."""
    b, plan = lote(3, plazo=30)
    libro, espera, _ = correr(b, plan)
    ejecutar_espera(b, espera)
    ci = ConfigCloudInit(usuario=CENTINELA_USUARIO, contrasena=Secreto(CENTINELA_CONTRASENA))
    entradas = [
        dataclasses.replace(
            e,
            elemento=dataclasses.replace(
                e.elemento, cfg=dataclasses.replace(e.elemento.cfg, cloudinit=ci)
            ),
        )
        for e in libro.instantanea()
    ]
    plan_ci = dataclasses.replace(
        plan,
        elementos=tuple(e.elemento for e in entradas),
        definicion=dataclasses.replace(
            plan.definicion,
            plantilla=dataclasses.replace(plan.definicion.plantilla, cloudinit=ci),
        ),
    )
    libro_ci = Libro(plan_ci)
    for e in entradas:
        libro_ci.registrar_ip(e.elemento.vmid, e.ip or ResultadoIp(EstadoIp.OMITIDA))
    informe = construir_informe(plan_ci, libro_ci, METADATOS, reloj=b.reloj)
    assert all(e.elemento.cfg.cloudinit is None for e in informe.entradas)
    assert informe.plantilla.cloudinit is None
    volcado = volcar(informe)
    assert CENTINELA_CONTRASENA not in volcado and CENTINELA_USUARIO not in volcado
    assert CENTINELA_CONTRASENA not in repr(informe)
    # El libro (memoria) sigue pudiendo reintentar los ajustes.
    assert libro_ci.instantanea()[0].elemento.cfg.cloudinit is ci


# --- Informe: IP por máquina y resumen -----------------------------------------------------------


def test_el_informe_lleva_por_mv_el_estado_de_ip_la_principal_y_las_otras():
    entradas, (a, c, d) = lote_de_tres()
    b, plan = lote(3, plazo=30)
    libro = Libro(plan)
    for e, v in zip(entradas, vmids(plan), strict=True):
        libro.registrar_ip(v, e.ip)  # type: ignore[arg-type]
    informe = construir_informe(plan, libro, METADATOS, reloj=b.reloj)
    por = {e.elemento.indice: e.ip for e in informe.entradas}
    assert por[0].estado == EstadoIp.OBTENIDA and por[0].principal == "192.168.1.50"
    assert por[1].principal == "192.168.1.51" and set(por[1].otras) == {
        "2001:db8::51",
        "10.20.30.40",
    }
    assert por[2].estado == EstadoIp.SIN_IP and por[2].principal is None


def test_el_resumen_cuenta_con_ip_sin_ip_y_no_aplicable():
    entradas, _ = lote_de_tres()  # 2 con IP, 1 sin IP
    r = resumen_ips(entradas)
    assert (r.con_ip, r.sin_ip, r.no_aplicable) == (2, 1, 0)
    assert r.hay_espera
    b, plan = lote(2, esperar_ip=False)
    libro, _, _ = correr(b, plan)
    sin_b3 = resumen_ips(libro.instantanea())
    assert (sin_b3.con_ip, sin_b3.sin_ip, sin_b3.no_aplicable) == (0, 0, 2)
    assert not sin_b3.hay_espera  # sin B3 el informe no muestra la sección


def test_el_resumen_trata_omitida_como_no_aplicable_y_cancelada_como_sin_ip():
    entradas, _ = lote_de_tres()
    base = entradas[2]
    omitida = dataclasses.replace(base, ip=ResultadoIp(EstadoIp.OMITIDA))
    cancelada = dataclasses.replace(base, ip=ResultadoIp(EstadoIp.CANCELADA))
    pendiente = dataclasses.replace(base, ip=None)
    r = resumen_ips([omitida, cancelada, pendiente])
    assert (r.con_ip, r.sin_ip, r.no_aplicable) == (0, 2, 1)


def test_una_ip_obtenida_parcial_cuenta_como_con_ip():
    entradas, _ = lote_de_tres()
    parcial = dataclasses.replace(
        entradas[2], ip=ResultadoIp(EstadoIp.OBTENIDA_PARCIAL, principal="10.20.30.40")
    )
    assert resumen_ips([parcial]).con_ip == 1


# --- CA-B3.6.5 (núcleo): escritura atómica y errores de guardado ---------------------------------


def test_ca_b3_6_5_guardar_en_una_carpeta_inexistente_da_archivo_no_guardable(tmp_path):
    entradas, _ = lote_de_tres()
    with pytest.raises(ErrorProxLaunch) as e:
        guardar_ips_csv(tmp_path / "no-existe" / "ips.csv", entradas)
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_b3_6_5_si_falla_el_reemplazo_el_archivo_anterior_queda_intacto_y_sin_temporales(
    tmp_path, monkeypatch
):
    entradas, _ = lote_de_tres()
    destino = tmp_path / "ips.csv"
    destino.write_bytes(b"CONTENIDO ANTERIOR")

    def falla(*_a, **_k):
        raise PermissionError(13, "denegado")

    monkeypatch.setattr(os, "replace", falla)
    with pytest.raises(ErrorProxLaunch) as e:
        guardar_ips_csv(destino, entradas)
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert destino.read_bytes() == b"CONTENIDO ANTERIOR"
    assert [p.name for p in tmp_path.iterdir()] == ["ips.csv"]  # ningún temporal olvidado


@pytest.mark.skipif(os.name == "nt", reason="los permisos POSIX no aplican en Windows")
def test_ca_b3_6_5_el_archivo_nace_privado_porque_usa_la_escritura_segura(tmp_path):
    entradas, _ = lote_de_tres()
    ruta = guardar_ips_csv(tmp_path / "ips.csv", entradas)
    assert (ruta.stat().st_mode & 0o777) == 0o600


def test_ca_b3_6_5_el_nucleo_no_pide_confirmacion_pero_tampoco_deja_basura(tmp_path):
    """La confirmación de reemplazo es del diálogo de guardado; el núcleo reemplaza entero."""
    entradas, _ = lote_de_tres()
    destino = tmp_path / "ips.csv"
    guardar_ips_csv(destino, entradas)
    primero = destino.read_bytes()
    guardar_ips_csv(destino, entradas[:1])
    assert destino.read_bytes() != primero and len(leer_csv(destino)) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["ips.csv"]
