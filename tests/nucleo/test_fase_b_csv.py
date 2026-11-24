"""Fase B (0.7.0): columnas de cloud-init y de espera de IP en el CSV (RF-B6.3, RF-B6.5, RF-B4.6).

Cubre CA-B6.3.1 a CA-B6.3.11, CA-B6.5.1 a CA-B6.5.6, CA-B4.6.1, CA-B4.6.2, CA-B1.5.3, CL-B25
(parte del núcleo) y las decisiones de la arquitectura §0 y §12: celda vacía hereda, ``heredar`` =
sin configurar, alias genéricos ``ip``/``dns``/``gateway``/``gw``/``upgrade`` retirados (siguen
como ``COLUMNA_NO_USADA``), ``ci_contrasena`` enmascarada, nunca persistida y fuera de la plantilla
descargable, aviso ``CSV_CON_CONTRASENAS`` y ``CONTRASENA_NO_GUARDADA`` al reabrir un lote guardado.

Las reglas que miran la plantilla o el servidor (V-B20, V-B25 con Windows, V-B37) se evalúan en el
plan, con las filas que salen de ``filas_lote``: ahí es donde «Comprobar» las nombra por fila.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import (
    MAX_COLUMNAS_CSV,
    MAX_LONG_CELDA,
    MAX_LONG_CLAVES,
)
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo as Aviso
from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    CloudInitParcial,
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
    combinar,
)
from proxlaunch.nucleo.csv_importacion.columnas import (
    COLUMNA_CONTRASENA,
    COLUMNAS,
    resolver_columnas,
)
from proxlaunch.nucleo.csv_importacion.errores_csv import (
    escribir_filas_con_error,
    filas_con_error,
)
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv, leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, ResultadoImportacion
from proxlaunch.nucleo.csv_importacion.plantilla import (
    ENCABEZADO_PLANTILLA,
    escribir_plantilla,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, PatronNombres
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.lotes_guardados.formato import leer_lote, lote_a_bytes
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.opciones.modelos import OpcionesLote
from proxlaunch.nucleo.secreto import MASCARA, Secreto
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_mvp3 import csv_bytes, perfil_base, perfiles_fabrica, tabla_csv
from .apoyo_mvp4 import ROL_MVP4, detalle_plantilla, inv_origen, plantilla_pve

CENTINELA = "S3cr3t-Prueba!"
CUERPO_PRIVADO = "CuerpoPrivado-ZZZ-9f8e7d"
CLAVE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA= ana@pc"
CLAVE_2 = "ssh-rsa AAAAB3NzaC1yc2EAAAAAAAAAAA== bea@pc"
PRIVADA = (
    f"-----BEGIN OPENSSH PRIVATE KEY-----\n{CUERPO_PRIVADO}\n-----END OPENSSH PRIVATE KEY-----"
)
COLUMNAS_B = (
    "ci_usuario",
    "ci_claves",
    "ci_contrasena",
    "ci_ip",
    "ci_puerta",
    "ci_dns",
    "ci_dominio",
    "ci_actualizar",
    "ci_snippet_usuario",
    "ci_snippet_vendor",
    "ci_snippet_red",
    "ci_snippet_meta",
    "esperar_ip",
)
CLON = "origen;fuente"  # filas que clonan la plantilla «base»: ``clonar;base``


def importar(
    lineas: Sequence[str],
    *,
    inv=None,
    encender_base: bool | None = None,
    alias_extra: dict[str, str] | None = None,
) -> ResultadoImportacion:
    return interpretar(
        tabla_csv(lineas),
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=inv,
        nodo_referencia="pve1",
        alias_extra=alias_extra,
        encender_base=encender_base,
    )


def fila(r: ResultadoImportacion, n: int):
    return next(f for f in r.filas if f.numero == n)


def reglas(f) -> list[tuple[str | None, str]]:
    return [(p.columna, p.regla) for p in f.problemas]


def clonando(cabecera: str, *filas: str) -> list[str]:
    """CSV cuyas filas clonan la plantilla ``base`` (cloud-init solo existe al clonar, V-B39)."""
    return [
        f"nombre;{CLON};{cabecera}",
        *(f"{f.split(';', 1)[0]};clonar;base;{f.split(';', 1)[1]}" for f in filas),
    ]


def inventario_con(*plantillas, privilegios=ROL_MVP4):
    return inv_origen(plantillas=tuple(plantillas), privilegios=privilegios)


def plan_de(r: ResultadoImportacion, inv):
    filas = filas_lote(r, r.numeros_validos)
    d = DefinicionLote(filas[0].cfg, len(filas), PatronNombres(""), Destino(), filas=filas)
    return construir_plan(
        d, inv, list(range(100, 100 + len(filas))), [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip


def plantilla_con(vmid: int, nombre: str, info: InfoCloudInitPlantilla):
    return plantilla_pve(
        vmid, nombre, "pve1", dataclasses.replace(detalle_plantilla(), cloudinit=info)
    )


# --- RF-B6.3: las 13 columnas, sus alias y su posición -------------------------------------------


def test_rf_b6_3_las_trece_columnas_canonicas_existen_y_son_59_en_total():
    # Fase C (RF-C6.3): 5 columnas nuevas (54 → 59); fase D (RF-D6.3): 2 más (59 → 61).
    canonicas = [c.canonica for c in COLUMNAS]
    assert set(COLUMNAS_B) <= set(canonicas)
    assert len(canonicas) == 61 and len(set(canonicas)) == 61


def test_rf_b6_3_las_marcadas_avanzadas_son_las_de_la_tabla():
    avanzadas = {c.canonica for c in COLUMNAS if c.avanzada and c.canonica in COLUMNAS_B}
    assert avanzadas == {
        "ci_dns",
        "ci_dominio",
        "ci_actualizar",
        "ci_snippet_usuario",
        "ci_snippet_vendor",
        "ci_snippet_red",
        "ci_snippet_meta",
    }


@pytest.mark.parametrize(
    ("alias", "canonica"),
    [
        ("ciuser", "ci_usuario"),
        ("ci_user", "ci_usuario"),
        ("sshkeys", "ci_claves"),
        ("ssh_keys", "ci_claves"),
        ("claves_ssh", "ci_claves"),
        ("cipassword", "ci_contrasena"),
        ("ci_password", "ci_contrasena"),
        ("CI PASSWORD", "ci_contrasena"),
        ("ipconfig0", "ci_ip"),
        ("puerta_enlace", "ci_puerta"),
        ("nameserver", "ci_dns"),
        ("searchdomain", "ci_dominio"),
        ("dominio_busqueda", "ci_dominio"),
        ("ciupgrade", "ci_actualizar"),
        ("cicustom_user", "ci_snippet_usuario"),
        ("snippet_user", "ci_snippet_usuario"),
        ("cicustom_vendor", "ci_snippet_vendor"),
        ("snippet_vendor", "ci_snippet_vendor"),
        ("cicustom_network", "ci_snippet_red"),
        ("snippet_network", "ci_snippet_red"),
        ("cicustom_meta", "ci_snippet_meta"),
        ("snippet_meta", "ci_snippet_meta"),
        ("wait_ip", "esperar_ip"),
        ("wait_for_ip", "esperar_ip"),
        ("Esperar IP", "esperar_ip"),
    ],
)
def test_rf_b6_3_los_alias_de_la_tabla_se_resuelven_a_su_columna_canonica(alias, canonica):
    mapa, avisos = resolver_columnas(["nombre", alias])
    assert mapa.posiciones == {"nombre": 0, canonica: 1}
    assert avisos == ()


@pytest.mark.parametrize("alias", ["ip", "dns", "gateway", "gw", "upgrade"])
def test_s12_los_alias_genericos_retirados_siguen_como_columna_no_usada(alias):
    mapa, avisos = resolver_columnas(["nombre", alias])
    assert mapa.posiciones == {"nombre": 0}
    assert [(a.codigo, a.params) for a in avisos] == [(Aviso.COLUMNA_NO_USADA, {"columna": alias})]


@pytest.mark.parametrize("alias", ["ip", "dns", "gateway", "gw", "upgrade"])
def test_s12_un_csv_de_060_con_esas_columnas_se_lee_igual_que_sin_ellas(alias):
    """Compatibilidad: ``ip`` o ``gw`` en un CSV de 0.6.0 no pueden cambiar el resultado."""
    con = importar(["nombre;cpu;" + alias, "a;2;10.0.0.5/24", "b;4;dhcp"])
    sin = importar(["nombre;cpu", "a;2", "b;4"])
    assert [(f.estado, f.opciones, f.problemas) for f in con.filas] == [
        (f.estado, f.opciones, f.problemas) for f in sin.filas
    ]
    assert all(f.opciones is None for f in con.filas)
    assert any(a.codigo == Aviso.COLUMNA_NO_USADA for a in con.avisos)


def test_ca_b6_3_3_dos_alias_de_la_misma_columna_dan_csv_columnas_duplicada():
    for cabecera in (
        ["nombre", "ci_usuario", "ciuser"],
        ["nombre", "ci_claves", "sshkeys"],
        ["nombre", "esperar_ip", "wait_ip"],
        ["nombre", "ci_ip", "ipconfig0"],
    ):
        with pytest.raises(ErrorProxLaunch) as exc:
            resolver_columnas(cabecera)
        assert exc.value.codigo == CodigoError.CSV_COLUMNAS
        assert exc.value.params["motivo"] == "duplicada"
        assert exc.value.params["columna"] == cabecera[1]


def test_ca_b6_3_3_la_contrasena_y_su_alias_tambien_son_duplicada():
    with pytest.raises(ErrorProxLaunch) as exc:
        resolver_columnas(["nombre", "ci_contrasena", "cipassword"])
    assert exc.value.params["motivo"] == "duplicada"


# --- CA-B6.3.1 / CA-B6.3.2: sin columnas nuevas y celdas vacías ----------------------------------


def test_ca_b6_3_1_un_csv_de_060_sin_columnas_nuevas_se_lee_igual():
    r = importar(["nombre;cpu;memoria;encender;notas", "a;2;4 GiB;sí;hola", "b;4;8 GiB;;"])
    for f in r.filas:
        assert f.estado == EstadoFila.CORRECTA
        assert f.opciones is None or (
            f.opciones.cloudinit is None and f.opciones.esperar_ip is None
        )
        assert f.cfg.cloudinit is None and f.cfg.esperar_ip is False
    assert fila(r, 2).opciones.encender is True and fila(r, 2).opciones.notas == "hola"
    assert r.avisos == ()


def test_ca_b6_3_2_una_celda_nueva_vacia_hereda_el_formulario_no_es_falso():
    r = importar(
        clonando("ci_usuario;esperar_ip;ci_actualizar;ci_dns", "a;deploy;sí;no;1.1.1.1", "b;;;;")
    )
    assert fila(r, 2).opciones.cloudinit.usuario == "deploy"
    assert (
        fila(r, 2).opciones.esperar_ip is True and fila(r, 2).opciones.cloudinit.actualizar is False
    )
    assert fila(r, 3).opciones is None  # todo vacío = hereda todo
    assert fila(r, 3).estado == EstadoFila.CORRECTA


def test_ca_b6_3_2_la_fila_que_fija_una_celda_conserva_las_demas_sin_fijar_como_none():
    r = importar(clonando("ci_usuario;ci_dns;ci_dominio", "a;deploy;;"))
    p = fila(r, 2).opciones.cloudinit
    assert p == CloudInitParcial(usuario="deploy")
    assert (p.claves, p.tarjeta0, p.dns, p.dominio, p.actualizar, p.snippets) == (None,) * 6


def test_ca_b6_3_2_filas_lote_combina_las_celdas_con_el_formulario_la_celda_gana_la_vacia_hereda():
    base = ConfigCloudInit(
        usuario="formulario",
        dominio="base.local",
        tarjetas=(TarjetaCloudInit(0, ModoTarjeta.DHCP),),
        actualizar=True,
    )
    r = importar(clonando("ci_usuario;ci_dominio", "a;fila-a;", "b;;"))
    pa, pb = (fila(r, n).opciones.cloudinit if fila(r, n).opciones else None for n in (2, 3))
    final_a = combinar(base, pa)
    assert (final_a.usuario, final_a.dominio, final_a.actualizar) == ("fila-a", "base.local", True)
    assert combinar(base, pb) is base  # la fila vacía no cambia nada


def test_rf_b6_3_ci_ip_heredar_es_sin_configurar_explicito_y_vacio_hereda_del_formulario():
    base = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.DHCP),))
    r = importar(clonando("ci_ip", "a;heredar", "b;"))
    explicita = fila(r, 2).opciones.cloudinit
    assert explicita.tarjeta0 == TarjetaCloudInit(0, ModoTarjeta.SIN_CONFIGURAR)
    assert combinar(base, explicita).tarjetas[0].modo == ModoTarjeta.SIN_CONFIGURAR  # anula
    assert fila(r, 3).opciones is None  # vacío = hereda DHCP del formulario


@pytest.mark.parametrize("celda", ["heredar", "Heredar", "HEREDAR"])
def test_rf_b6_3_heredar_no_distingue_mayusculas(celda):
    r = importar(clonando("ci_ip", f"a;{celda}"))
    assert fila(r, 2).opciones.cloudinit.tarjeta0.modo == ModoTarjeta.SIN_CONFIGURAR


# --- Interpretación de cada celda ----------------------------------------------------------------


def test_rf_b6_3_ci_ip_dhcp_ip_fija_y_puerta_forman_la_tarjeta_1():
    r = importar(clonando("ci_ip;ci_puerta", "a;dhcp;", "b;10.0.0.5/24;10.0.0.1"))
    assert fila(r, 2).opciones.cloudinit.tarjeta0 == TarjetaCloudInit(0, ModoTarjeta.DHCP)
    assert fila(r, 3).opciones.cloudinit.tarjeta0 == TarjetaCloudInit(
        0, ModoTarjeta.FIJA, "10.0.0.5/24", False, "10.0.0.1"
    )
    assert fila(r, 3).estado == EstadoFila.CORRECTA


def test_rf_b6_3_las_filas_de_csv_nunca_traen_serie_la_serie_es_del_formulario():
    r = importar(clonando("ci_ip", "a;10.0.0.5/24"))
    assert fila(r, 2).opciones.cloudinit.tarjeta0.serie is False


def test_rf_b6_3_ci_dns_admite_espacio_coma_y_punto_y_coma_en_celda_entrecomillada():
    r = importar(
        clonando("ci_dns", 'a;"8.8.8.8 1.1.1.1"', 'b;"8.8.8.8, 1.1.1.1"', 'c;"8.8.8.8;1.1.1.1"')
    )
    for n in (2, 3, 4):
        assert fila(r, n).opciones.cloudinit.dns == ("8.8.8.8", "1.1.1.1")
        assert fila(r, n).estado == EstadoFila.CORRECTA


def test_ca_b1_8_4_un_dns_invalido_en_una_fila_es_v_b32_en_su_columna_y_no_bloquea_las_demas():
    r = importar(clonando("ci_dns", "a;8.8.8", "b;1.1.1.1"))
    assert reglas(fila(r, 2)) == [("ci_dns", "V-B32")]
    assert fila(r, 2).estado == EstadoFila.CON_ERROR and fila(r, 3).estado == EstadoFila.CORRECTA


def test_rf_b6_3_ci_actualizar_si_no_y_vacio():
    r = importar(clonando("ci_actualizar", "a;sí", "b;no", "c;"))
    assert fila(r, 2).opciones.cloudinit.actualizar is True
    assert fila(r, 3).opciones.cloudinit.actualizar is False
    assert fila(r, 4).opciones is None


def test_rf_b6_3_esperar_ip_si_no_y_vacio_con_encendido_efectivo():
    r = importar(clonando("esperar_ip;encender", "a;sí;sí", "b;no;sí", "c;;sí"))
    assert fila(r, 2).opciones.esperar_ip is True
    assert fila(r, 3).opciones.esperar_ip is False
    assert fila(r, 4).opciones.esperar_ip is None and fila(r, 4).opciones.encender is True


def test_ca_b6_3_4_un_booleano_erroneo_se_asocia_a_su_fila_y_columna_sin_bloquear_las_demas():
    r = importar(clonando("ci_actualizar;esperar_ip", "a;quizá;", "b;sí;"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    (p,) = [p for p in f.problemas if p.columna == "ci_actualizar"]
    assert p.valor == "quizá" and p.severidad == Severidad.ERROR
    assert fila(r, 3).estado == EstadoFila.CORRECTA


# --- CA-B6.3.4: celdas inválidas -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("cabecera", "celdas", "columna", "regla"),
    [
        ("ci_ip", "10.0.0.5", "ci_ip", "V-B26"),
        ("ci_ip", "10.0.0.5/7", "ci_ip", "V-B26"),
        ("ci_ip", "010.0.0.5/24", "ci_ip", "V-B26"),
        ("ci_ip", "10.0.0.0/24", "ci_ip", "V-B27"),
        ("ci_ip;ci_puerta", "dhcp;10.0.0.1", "ci_puerta", "V-B29"),
        ("ci_ip;ci_puerta", "10.0.0.5/24;10.0.1.1", "ci_puerta", "V-B28"),
        ("ci_ip;ci_puerta", "10.0.0.5/24;10.0.0.5", "ci_puerta", "V-B28"),
        ("ci_puerta", "10.0.0.1", "ci_puerta", "V-B29"),  # puerta sin ip (CA-B1.8.3)
        ("ci_dominio", "_a..b", "ci_dominio", "V-B33"),
        ("ci_usuario", "mal usuario", "ci_usuario", "V-B21"),
        ("ci_snippet_vendor", "local:iso/a.iso", "ci_snippet_vendor", "V-B54"),
        ("ci_snippet_usuario", "snippets/a.yaml", "ci_snippet_usuario", "V-B54"),
        ("ci_snippet_red", "local:snippets/../x", "ci_snippet_red", "V-B54"),
        ("ci_snippet_meta", "local:snippets/a,b", "ci_snippet_meta", "V-B54"),
    ],
)
def test_ca_b6_3_4_una_celda_invalida_da_error_con_fila_columna_y_regla(
    cabecera, celdas, columna, regla
):
    r = importar(clonando(cabecera, f"a;{celdas}", "b;"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert (columna, regla) in reglas(f)
    assert all(p.fila == 2 for p in f.problemas)
    assert fila(r, 3).estado == EstadoFila.CORRECTA  # no bloquea las filas válidas
    assert 3 in r.numeros_validos and 2 not in r.numeros_validos


def test_ca_b6_3_4_el_error_nombra_la_columna_tal_como_viene_en_el_archivo():
    r = importar(clonando("CI_IP", "a;10.0.0.5"))
    assert fila(r, 2).problemas[0].columna == "CI_IP"


def test_ca_b6_3_4_una_fila_invalida_no_se_puede_pasar_a_filas_lote():
    r = importar(clonando("ci_ip", "a;10.0.0.5"))
    with pytest.raises(ValueError):
        filas_lote(r, [2])


def test_ca_b6_3_4_varios_errores_de_cloudinit_en_la_misma_fila_se_acumulan_en_orden_de_columna():
    r = importar(clonando("ci_usuario;ci_ip;ci_dominio", "a;mal usuario;10.0.0.5;_a..b"))
    assert reglas(fila(r, 2)) == [
        ("ci_usuario", "V-B21"),
        ("ci_ip", "V-B26"),
        ("ci_dominio", "V-B33"),
    ]


# --- V-B39: cloud-init solo al clonar ------------------------------------------------------------


def test_v_b39_una_fila_que_no_clona_con_celdas_de_cloudinit_es_invalida():
    r = importar(["nombre;ci_usuario", "a;deploy"])  # origen del perfil base: disco vacío
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert [(p.regla, p.severidad) for p in f.problemas if p.regla == "V-B39"] == [
        ("V-B39", Severidad.ERROR)
    ]


def test_v_b39_una_fila_que_no_clona_y_sin_celdas_de_cloudinit_no_tiene_problema():
    r = importar(["nombre;ci_usuario", "a;"])
    assert fila(r, 2).estado == EstadoFila.CORRECTA


# --- CA-B6.3.5 / CA-B6.3.6: columnas y límites ---------------------------------------------------


def test_ca_b6_3_5_un_csv_con_todas_las_columnas_canonicas_se_acepta():
    assert MAX_COLUMNAS_CSV == 70
    cabecera = [c.canonica for c in COLUMNAS]
    datos = csv_bytes(
        [";".join(cabecera), ";".join("a" if c == "nombre" else "" for c in cabecera)]
    )
    tabla = leer_tabla(datos)
    assert len(tabla.encabezado) == 61
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    assert fila(r, 2).estado == EstadoFila.CORRECTA


def test_ca_b6_3_5_mas_de_70_columnas_se_rechazan_con_el_valor_real():
    cabecera = ["nombre", *(f"extra{i}" for i in range(70))]
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(csv_bytes([";".join(cabecera), ";".join("a" for _ in cabecera)]))
    assert exc.value.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert exc.value.params["tipo"] == "columnas" and exc.value.params["columnas"] == "71"


def _clave_de(n: int) -> str:
    base = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA="
    return f"{base} " + "x" * (n - len(base) - 1)


def test_ca_b6_3_6_la_celda_ci_claves_admite_hasta_8192_caracteres():
    assert MAX_LONG_CLAVES == 8192
    celda = _clave_de(8192)
    assert len(celda) == 8192
    r = importar(clonando("ci_claves", f"a;{celda}"))
    assert fila(r, 2).estado == EstadoFila.CORRECTA
    assert fila(r, 2).opciones.cloudinit.claves == (celda,)


def test_ca_b6_3_6_ci_claves_con_20_claves_de_unos_400_caracteres_cabe():
    claves = [CLAVE.replace("ana@pc", "c" * 360 + str(i)) for i in range(20)]
    celda = ";".join(claves)
    assert 7000 < len(celda) <= 8192
    r = importar(clonando("ci_claves", f'a;"{celda}"'))
    assert fila(r, 2).estado == EstadoFila.CORRECTA
    assert len(fila(r, 2).opciones.cloudinit.claves) == 20


def test_ca_b6_3_6_ci_claves_de_8193_caracteres_se_rechaza_con_el_valor_real():
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(csv_bytes(["nombre;ci_claves", f"a;{_clave_de(8193)}"]))
    assert exc.value.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert exc.value.params["tipo"] == "celda" and exc.value.params["celda"] == "8193"
    assert exc.value.params["max"] == "8192"


def test_ca_b6_3_6_el_limite_de_ci_claves_tambien_vale_con_su_alias_y_con_alias_traducidos():
    datos = csv_bytes(["nombre;sshkeys", f"a;{_clave_de(8192)}"])
    assert leer_tabla(datos)
    traducido = csv_bytes(["nombre;claves publicas", f"a;{_clave_de(8192)}"])
    assert leer_tabla(traducido, alias_extra={"claves publicas": "ci_claves"})


@pytest.mark.parametrize(
    "columna", ["ci_usuario", "ci_dominio", "ci_dns", "ci_ip", "ci_snippet_vendor"]
)
def test_ca_b6_3_6_las_demas_columnas_conservan_el_limite_de_256(columna):
    assert MAX_LONG_CELDA == 256
    assert leer_tabla(csv_bytes([f"nombre;{columna}", f"a;{'x' * 256}"]))
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(csv_bytes([f"nombre;{columna}", f"a;{'x' * 257}"]))
    assert exc.value.params["tipo"] == "celda" and exc.value.params["max"] == "256"


def test_ca_b6_3_6_el_limite_de_ci_claves_no_se_extiende_a_la_contrasena():
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(csv_bytes(["nombre;ci_contrasena", f"a;{'x' * 257}"]))
    assert exc.value.params["tipo"] == "celda"
    assert "x" * 20 not in str(exc.value.params)


# --- RF-B1.4 / CA-B1.5.3: claves en la celda -----------------------------------------------------


def test_rf_b1_4_ci_claves_separa_por_punto_y_coma_o_por_salto_de_linea_y_quita_duplicadas():
    r = importar(
        clonando("ci_claves", f'a;"{CLAVE};{CLAVE_2};{CLAVE}"', f'b;"{CLAVE}\r\n{CLAVE_2}"')
    )
    for n in (2, 3):
        assert fila(r, n).opciones.cloudinit.claves == (CLAVE, CLAVE_2)
        assert fila(r, n).estado == EstadoFila.CORRECTA


def test_rf_b1_4_una_celda_de_solo_comentarios_o_vacia_equivale_a_celda_vacia():
    r = importar(clonando("ci_claves", 'a;"# nada"', "b;"))
    assert fila(r, 2).opciones is None and fila(r, 3).opciones is None


@pytest.mark.parametrize(
    ("celda", "regla", "linea"),
    [
        (f'"{CLAVE};ssh-rsa"', "V-B22", "2"),
        (f'"{CLAVE};hola"', "V-B22", "2"),
        (f'"command=""x"" {CLAVE}"', "V-B22", "1"),
    ],
)
def test_ca_b6_3_4_una_clave_mal_formada_es_v_b22_con_su_linea_y_sin_eco(celda, regla, linea):
    r = importar(clonando("ci_claves", f"a;{celda}"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    (p,) = [p for p in f.problemas if p.regla == regla]
    assert p.columna == "ci_claves" and p.params["linea"] == linea
    assert p.valor == ""  # nunca se conserva el contenido de la celda
    assert "hola" not in repr(f.problemas)


def test_ca_b1_5_3_una_clave_privada_en_la_celda_es_v_b23_y_la_celda_no_se_muestra():
    celda = PRIVADA.replace("\n", "\r\n")
    r = importar(clonando("ci_claves", f'a;"{celda}"', f"b;{CLAVE}"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    (p,) = [p for p in f.problemas if p.regla == "V-B23"]
    assert (p.columna, p.valor) == ("ci_claves", "")
    assert CUERPO_PRIVADO not in repr(r)  # ni problemas, ni originales, ni nada
    assert "ci_claves" not in f.originales
    assert fila(r, 3).estado == EstadoFila.CORRECTA


def test_ca_b1_5_3_la_clave_privada_mezclada_con_publicas_rechaza_toda_la_celda():
    r = importar(clonando("ci_claves", f'a;"{CLAVE}\r\n{PRIVADA}"'.replace("\n", "\r\n")))
    f = fila(r, 2)
    assert [p.regla for p in f.problemas if p.regla.startswith("V-B2")] == ["V-B23"]
    assert f.opciones is None or f.opciones.cloudinit is None or f.opciones.cloudinit.claves is None


def test_ca_b1_5_3_mas_de_20_claves_en_la_celda_es_v_b24():
    celda = ";".join(CLAVE.replace("ana@pc", f"c{i}") for i in range(21))
    r = importar(clonando("ci_claves", f'a;"{celda}"'))
    (p,) = [p for p in fila(r, 2).problemas if p.regla == "V-B24"]
    assert p.params["motivo"] == "demasiadas"


# --- RF-B4.6 / CA-B4.6.1 / CA-B4.6.2: snippets ---------------------------------------------------


def test_ca_b4_6_1_un_snippet_en_la_columna_vendor_se_aplica_solo_a_esa_fila():
    r = importar(clonando("ci_snippet_vendor", "a;local:snippets/v.yaml", "b;"))
    assert fila(r, 2).opciones.cloudinit.snippets == SnippetsCloudInit(
        vendor="local:snippets/v.yaml"
    )
    assert fila(r, 2).estado == EstadoFila.CORRECTA
    assert fila(r, 3).opciones is None


def test_ca_b4_6_2_ninguno_equivale_a_ninguno_y_el_resto_de_tipos_quedan_como_la_plantilla():
    r = importar(clonando("ci_snippet_usuario;ci_snippet_meta", "a;NINGUNO;local:snippets/m.yaml"))
    assert fila(r, 2).opciones.cloudinit.snippets == SnippetsCloudInit(
        user=NINGUNO, meta="local:snippets/m.yaml"
    )


def test_ca_b4_6_1_los_cuatro_tipos_van_a_su_columna():
    cab = "ci_snippet_usuario;ci_snippet_vendor;ci_snippet_red;ci_snippet_meta"
    celdas = ";".join(f"local:snippets/{t}.yaml" for t in "uvnm")
    r = importar(clonando(cab, f"a;{celdas}"))
    s = fila(r, 2).opciones.cloudinit.snippets
    assert (s.user, s.vendor, s.network, s.meta) == tuple(
        f"local:snippets/{t}.yaml" for t in "uvnm"
    )


# --- CA-B6.3.7: fórmulas -------------------------------------------------------------------------


@pytest.mark.parametrize("disparador", ["=", "+", "-", "@"])
def test_ca_b6_3_7_una_celda_que_empieza_por_un_disparador_es_texto_nunca_una_formula(disparador):
    celda = f"{disparador}HYPERLINK(1)"
    r = importar(clonando("ci_dominio", f"a;{celda}"))
    f = fila(r, 2)
    assert f.opciones.cloudinit.dominio == celda  # se conserva literal
    assert any(p.regla == "V-B33" for p in f.problemas)  # y se valida como cualquier texto


def test_ca_b6_3_7_el_csv_de_errores_neutraliza_las_celdas_con_formula(tmp_path):
    tabla = tabla_csv(clonando("ci_dominio;ci_usuario", "a;=HYPERLINK(1);@calc"))
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, r, lambda p: p.regla)
    texto = ruta.read_bytes().decode("utf-8-sig")
    celdas = next(csv.reader(io.StringIO(texto.split("\r\n", 1)[1]), delimiter=";"))
    assert "'=HYPERLINK(1)" in celdas and "'@calc" in celdas
    assert not any(c.startswith(("=", "@", "+", "-")) for c in celdas)


# --- CA-B6.3.8: plantilla descargable ------------------------------------------------------------


def test_ca_b6_3_8_la_plantilla_incluye_las_columnas_nuevas_salvo_la_contrasena():
    nuevas = [c for c in COLUMNAS_B if c != "ci_contrasena"]
    assert all(c in ENCABEZADO_PLANTILLA for c in nuevas)
    assert COLUMNA_CONTRASENA not in ENCABEZADO_PLANTILLA
    assert "cipassword" not in ENCABEZADO_PLANTILLA and "ci_password" not in ENCABEZADO_PLANTILLA
    assert len(ENCABEZADO_PLANTILLA) == 42  # fase D: 2 columnas más


@pytest.mark.parametrize("separador", [";", ","])
def test_ca_b6_3_8_la_plantilla_escrita_se_lee_sin_errores_y_sin_contrasena(tmp_path, separador):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta, separador=separador)
    texto = ruta.read_text(encoding="utf-8-sig")
    assert "contrasena" not in texto.lower() and "password" not in texto.lower()
    tabla = leer_archivo_csv(ruta)
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    assert [f.estado for f in r.filas if f.estado == EstadoFila.CON_ERROR] == []
    assert not [
        a for a in r.avisos if a.codigo in (Aviso.CSV_CON_CONTRASENAS, Aviso.CREDENCIAL_IGNORADA)
    ]


def test_ca_b6_3_8_la_fila_de_ejemplo_que_clona_lleva_un_ejemplo_de_cloudinit_valido(tmp_path):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    tabla = leer_archivo_csv(ruta)
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    con_ci = [f for f in r.filas if f.opciones and f.opciones.cloudinit]
    assert len(con_ci) == 1 and con_ci[0].nombre == "ejemplo-05"
    assert con_ci[0].opciones.cloudinit.tarjeta0.modo == ModoTarjeta.DHCP
    assert con_ci[0].opciones.cloudinit.usuario == "ubuntu"


# --- CA-B6.3.9: esperar_ip sin encender ----------------------------------------------------------


def test_ca_b6_3_9_esperar_ip_sin_encender_en_la_fila_es_v_b60_si_el_formulario_no_enciende():
    r = importar(clonando("esperar_ip", "a;sí"), encender_base=False)
    assert reglas(fila(r, 2)) == [("esperar_ip", "V-B60")]
    assert fila(r, 2).estado == EstadoFila.CON_ERROR


def test_ca_b6_3_9_con_encender_en_la_fila_o_en_el_formulario_no_hay_problema():
    en_fila = importar(clonando("esperar_ip;encender", "a;sí;sí"), encender_base=False)
    assert fila(en_fila, 2).estado == EstadoFila.CORRECTA
    en_formulario = importar(clonando("esperar_ip", "a;sí"), encender_base=True)
    assert fila(en_formulario, 2).estado == EstadoFila.CORRECTA


def test_ca_b6_3_9_la_columna_encender_de_la_fila_manda_sobre_el_formulario():
    r = importar(clonando("esperar_ip;encender", "a;sí;no", "b;sí;"), encender_base=True)
    assert reglas(fila(r, 2)) == [
        ("esperar_ip", "V-B60")
    ]  # la fila apaga lo que el formulario enciende
    assert fila(r, 3).estado == EstadoFila.CORRECTA


def test_ca_b6_3_9_si_no_se_conoce_el_encendido_del_formulario_la_regla_la_evalua_el_plan():
    r = importar(clonando("esperar_ip", "a;sí"))  # encender_base=None
    assert fila(r, 2).estado == EstadoFila.CORRECTA
    inv = inventario_con(plantilla_pve(9000, "base", "pve1"))
    filas = filas_lote(r, [2])
    assert filas[0].opciones.esperar_ip is True
    plan = plan_de(r, inv)  # el formulario (cfg de la fila) no enciende: V-B60 del plan
    assert [p.regla for p in plan.problemas if p.regla == "V-B60"] == ["V-B60"]
    assert [p.indice for p in plan.problemas if p.regla == "V-B60"] == [0]


def test_ca_b6_3_9_esperar_ip_no_en_la_fila_no_da_v_b60_aunque_no_se_encienda():
    r = importar(clonando("esperar_ip", "a;no", "b;"), encender_base=False)
    assert all(fila(r, n).estado == EstadoFila.CORRECTA for n in (2, 3))


# --- CA-B6.3.10 / CA-B6.3.11 / CA-B6.5.6: lo que miran el plan y el servidor ---------------------


def test_ca_b6_3_10_dhcp_en_una_fila_de_plantilla_sin_unidad_es_v_b20_y_solo_de_esa_fila():
    sin = plantilla_con(9000, "sin", InfoCloudInitPlantilla(unidad=False, tarjetas=(0,)))
    con = plantilla_con(9001, "con", InfoCloudInitPlantilla(unidad=True, tarjetas=(0,)))
    inv = inventario_con(sin, con, privilegios=(*ROL_MVP4, "VM.Config.Cloudinit"))
    lineas = [
        "nombre;origen;fuente;ci_ip",
        "a;clonar;sin;dhcp",
        "b;clonar;con;dhcp",
        "c;clonar;sin;",
    ]
    plan = plan_de(importar(lineas, inv=inv), inv)
    v_b20 = [p for p in plan.problemas if p.regla == "V-B20"]
    assert [(p.severidad, p.indice, p.params["plantilla"]) for p in v_b20] == [
        (Severidad.ERROR, 0, "sin")
    ]


def test_ca_b6_3_11_sin_el_privilegio_de_cloudinit_el_plan_bloquea_las_filas_y_lo_nombra():
    info = InfoCloudInitPlantilla(unidad=True, tarjetas=(0,))
    sin_priv = inventario_con(plantilla_con(9000, "base", info))  # ROL_MVP4 no trae Cloudinit
    lineas = clonando("ci_claves;ci_usuario", f"a;{CLAVE};", "b;;deploy", "c;;")
    r = importar(lineas, inv=sin_priv)
    plan = plan_de(r, sin_priv)
    bloqueadas = [p for p in plan.problemas if p.regla == "V-B37"]
    assert [(p.severidad, p.indice) for p in bloqueadas] == [
        (Severidad.ERROR, 0),
        (Severidad.ERROR, 1),
    ]
    assert all(p.params["privilegio"] == "VM.Config.Cloudinit" for p in bloqueadas)
    con_priv = inventario_con(
        plantilla_con(9000, "base", info), privilegios=(*ROL_MVP4, "VM.Config.Cloudinit")
    )
    assert not [p for p in plan_de(r, con_priv).problemas if p.regla == "V-B37"]


def test_ca_b6_5_6_una_contrasena_para_una_plantilla_windows_es_error_de_la_fila_v_b25():
    win = plantilla_con(
        9002,
        "win",
        InfoCloudInitPlantilla(unidad=True, tarjetas=(0,), ostype="win10", es_windows=True),
    )
    lin = plantilla_con(
        9003, "lin", InfoCloudInitPlantilla(unidad=True, tarjetas=(0,), ostype="l26")
    )
    inv = inventario_con(win, lin, privilegios=(*ROL_MVP4, "VM.Config.Cloudinit"))
    lineas = [
        "nombre;origen;fuente;ci_contrasena",
        f"a;clonar;win;{CENTINELA}",
        f"b;clonar;lin;{CENTINELA}",
    ]
    plan = plan_de(importar(lineas, inv=inv), inv)
    v_b25 = [p for p in plan.problemas if p.regla == "V-B25"]
    assert [(p.severidad, p.indice, p.params["motivo"]) for p in v_b25] == [
        (Severidad.ERROR, 0, "windows")
    ]
    assert CENTINELA not in repr(plan.problemas)


# --- RF-B6.5 / CA-B6.5.1 / CA-B6.5.2: reconocimiento de la columna secreta -----------------------


@pytest.mark.parametrize(
    "encabezado", ["ci_contrasena", "cipassword", "ci_password", "CI_Contrasena"]
)
def test_ca_b6_5_1_la_columna_de_contrasena_se_reconoce_y_no_da_credencial_ignorada(encabezado):
    mapa, avisos = resolver_columnas(["nombre", encabezado])
    assert mapa.posiciones == {"nombre": 0, "ci_contrasena": 1}
    assert mapa.credenciales == ()
    assert avisos == ()


@pytest.mark.parametrize(
    "encabezado",
    ["password", "token", "ci_secreto", "contrasena", "contraseña", "secret", "ci_token"],
)
def test_ca_b6_5_2_cualquier_otra_columna_con_aspecto_de_credencial_sigue_descartandose(encabezado):
    mapa, avisos = resolver_columnas(["nombre", encabezado])
    assert mapa.posiciones == {"nombre": 0}
    assert mapa.credenciales == (1,)
    assert [(a.codigo, a.params) for a in avisos] == [(Aviso.CREDENCIAL_IGNORADA, {"n": "1"})]


def test_ca_b6_5_2_junto_a_la_columna_secreta_las_demas_credenciales_se_siguen_descartando():
    r = importar(
        clonando("ci_contrasena;password;token", f"a;{CENTINELA};otro-secreto-1;otro-secreto-2")
    )
    assert [(a.codigo, a.params) for a in r.avisos if a.codigo == Aviso.CREDENCIAL_IGNORADA] == [
        (Aviso.CREDENCIAL_IGNORADA, {"n": "2"})
    ]
    assert fila(r, 2).opciones.cloudinit.contrasena.revelar() == CENTINELA
    assert "otro-secreto" not in repr(r) and "otro-secreto" not in repr(fila(r, 2).opciones)


def test_ca_b6_5_2_los_alias_traducidos_nunca_se_aplican_a_la_columna_secreta():
    extra = {
        "usuario cloud-init": "ci_usuario",
        "contraseña": "ci_contrasena",
        "clave": "ci_contrasena",
    }
    r = importar(
        clonando("usuario cloud-init;contraseña", "a;deploy;" + CENTINELA), alias_extra=extra
    )
    assert fila(r, 2).opciones.cloudinit.usuario == "deploy"  # el alias normal sí funciona
    assert fila(r, 2).opciones.cloudinit.contrasena is None  # el de la contraseña, no
    assert any(a.codigo == Aviso.CREDENCIAL_IGNORADA for a in r.avisos)
    assert CENTINELA not in repr(r)


# --- CA-B6.5.3: el centinela no aparece en ninguna parte -----------------------------------------


def _csv_con_errores_y_contrasena() -> list[str]:
    return clonando(
        "ci_contrasena;ci_ip;ci_usuario;ci_dns;cpu",
        f"a;{CENTINELA};10.0.0.5;mal usuario;8.8.8;nada",
        f"b;{CENTINELA};dhcp;ok;1.1.1.1;2",
    )


def test_ca_b6_5_3_la_contrasena_no_sale_en_la_vista_previa_ni_en_los_problemas_ni_en_originales():
    r = importar(_csv_con_errores_y_contrasena())
    assert CENTINELA not in repr(r)
    for f in r.filas:
        assert CENTINELA not in repr(f.problemas) and CENTINELA not in repr(f.originales)
        assert CENTINELA not in repr(f)
        for p in f.problemas:
            assert CENTINELA not in p.valor and CENTINELA not in repr(p.params)
    assert fila(r, 2).originales.get("ci_contrasena") == MASCARA  # «definida», nunca el texto
    assert all(
        p.valor == MASCARA for f in r.filas for p in f.problemas if p.columna == "ci_contrasena"
    )


def test_ca_b6_5_3_la_contrasena_no_sale_en_el_log(caplog):
    caplog.set_level(logging.DEBUG)
    r = importar(_csv_con_errores_y_contrasena())
    filas_lote(r, r.numeros_validos)
    assert CENTINELA not in caplog.text
    assert CENTINELA not in "".join(str(rec.args) + rec.getMessage() for rec in caplog.records)


def test_ca_b6_5_3_la_fila_correcta_lleva_un_secreto_cuyo_repr_es_la_mascara():
    r = importar(_csv_con_errores_y_contrasena())
    (fl,) = filas_lote(r, r.numeros_validos)
    secreto = fl.opciones.cloudinit.contrasena
    assert isinstance(secreto, Secreto) and secreto.revelar() == CENTINELA
    assert (
        CENTINELA not in repr(fl)
        and CENTINELA not in repr(fl.opciones)
        and CENTINELA not in str(secreto)
    )


def test_ca_b6_5_3_el_csv_de_filas_con_error_no_contiene_la_contrasena(tmp_path):
    tabla = tabla_csv(_csv_con_errores_y_contrasena())
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, r, lambda p: f"{p.columna}: {p.regla}")
    assert CENTINELA.encode() not in ruta.read_bytes()
    encabezado, filas = filas_con_error(tabla, r, lambda p: p.regla)
    assert CENTINELA not in repr(filas) and "ci_contrasena" not in encabezado


def test_ca_b6_5_3_el_csv_de_filas_con_error_conserva_el_resto_de_columnas(tmp_path):
    """Lo que SÍ debe seguir saliendo: las demás columnas de la fila con error (reimportable)."""
    tabla = tabla_csv(_csv_con_errores_y_contrasena())
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    encabezado, filas = filas_con_error(tabla, r, lambda p: p.regla)
    assert {"nombre", "ci_ip", "ci_usuario", "ci_dns"} <= set(encabezado)
    assert len(filas) == 1 and filas[0][encabezado.index("nombre")] == "a"


def test_ca_b6_5_3_los_errores_de_lectura_de_la_celda_secreta_no_repiten_su_valor():
    largo = "x" + CENTINELA * 40
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(csv_bytes(["nombre;ci_contrasena", f"a;{largo}"]))
    assert CENTINELA not in repr(exc.value.params) and CENTINELA not in str(exc.value)


# --- CA-B6.5.5: formato de la contraseña ---------------------------------------------------------


def test_ca_b6_5_5_una_contrasena_con_salto_de_linea_es_error_de_fila_v_b25_sin_eco():
    r = importar(clonando("ci_contrasena", f'a;"{CENTINELA}\r\ntrozo-2"', "b;12345678-ok"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    (p,) = [p for p in f.problemas if p.regla == "V-B25" and p.severidad == Severidad.ERROR]
    assert (p.columna, p.params["motivo"], p.valor) == ("ci_contrasena", "control", MASCARA)
    assert CENTINELA not in repr(r) and "trozo-2" not in repr(r)
    assert fila(r, 3).estado == EstadoFila.CORRECTA


def test_ca_b6_5_5_una_contrasena_de_mas_de_128_caracteres_es_error_y_de_128_vale():
    r = importar(clonando("ci_contrasena", f"a;{'x' * 129}", f"b;{'y' * 128}"))
    (p,) = [p for p in fila(r, 2).problemas if p.severidad == Severidad.ERROR]
    assert (p.regla, p.params["motivo"], p.valor) == ("V-B25", "larga", MASCARA)
    assert fila(r, 3).estado == EstadoFila.CORRECTA
    assert "x" * 30 not in repr(r) and "y" * 30 not in repr(r)


def test_b1_menos_de_8_caracteres_es_error_y_la_fila_no_es_valida():
    r = importar(clonando("ci_contrasena", "a;abc"))
    f = fila(r, 2)
    assert [(p.regla, p.severidad) for p in f.problemas] == [("V-B25", Severidad.ERROR)]
    assert f.estado == EstadoFila.CON_ERROR and 2 not in r.numeros_validos


def test_ca_b6_5_5_una_contrasena_invalida_no_llega_a_la_configuracion_de_la_fila():
    r = importar(clonando("ci_contrasena", f"a;{'x' * 129}"))
    assert fila(r, 2).cfg is None  # la fila con error no se puede importar
    assert (
        fila(r, 2).opciones is None
        or fila(r, 2).opciones.cloudinit is None
        or (fila(r, 2).opciones.cloudinit.contrasena is None)
    )


@pytest.mark.parametrize(
    "contrasena", ["  con espacios  ", "ñandú-🙂-12345", "a%b&c+d=e-123", "tab\tdentro1"]
)
def test_cl_b9_cl_b10_la_contrasena_se_conserva_tal_cual_sin_recortar_ni_decodificar(contrasena):
    r = importar(clonando("ci_contrasena", f'a;"{contrasena}"'))
    f = fila(r, 2)
    if "\t" in contrasena:
        assert f.estado == EstadoFila.CON_ERROR  # control: no se admite
        return
    assert f.opciones.cloudinit.contrasena.revelar() == contrasena


# --- CSV_CON_CONTRASENAS -------------------------------------------------------------------------


def test_rf_b6_5_con_contrasenas_en_el_csv_se_avisa_una_sola_vez_sin_valores():
    r = importar(clonando("ci_contrasena", f"a;{CENTINELA}", f"b;{CENTINELA}", "c;"))
    avisos = [a for a in r.avisos if a.codigo == Aviso.CSV_CON_CONTRASENAS]
    assert len(avisos) == 1 and avisos[0].params == {}


def test_rf_b6_5_sin_contrasenas_no_hay_aviso_aunque_exista_la_columna_vacia():
    r = importar(clonando("ci_contrasena", "a;", "b;"))
    assert [a for a in r.avisos if a.codigo == Aviso.CSV_CON_CONTRASENAS] == []


def test_rf_b6_5_sin_la_columna_no_hay_aviso():
    r = importar(clonando("ci_usuario", "a;deploy"))
    assert r.avisos == ()


# --- CA-B6.5.4: guardar el lote no guarda la contraseña ------------------------------------------


def _lote_desde_csv(lineas: Sequence[str]) -> LoteGuardado:
    r = importar(lineas)
    filas = filas_lote(r, r.numeros_validos)
    d = DefinicionLote(filas[0].cfg, len(filas), PatronNombres(""), Destino(), filas=filas)
    return LoteGuardado("Desde CSV", d)


def test_ca_b6_5_4_el_lote_guardado_desde_un_csv_con_contrasena_no_la_contiene_y_avisa_al_reabrir():
    lote = _lote_desde_csv(
        clonando("ci_contrasena;ci_usuario", f"a;{CENTINELA};deploy", "b;;deploy")
    )
    datos = lote_a_bytes(lote, app_version="0.7.0")
    assert CENTINELA.encode() not in datos
    texto = datos.decode()
    assert "contrasena" not in texto and "password" not in texto.lower()
    archivo = leer_lote(datos)
    assert Aviso.CONTRASENA_NO_GUARDADA in {a.codigo for a in archivo.avisos}
    for f in archivo.lote.definicion.filas:
        assert f.opciones.cloudinit.contrasena is None
    assert [f.opciones.cloudinit.usuario for f in archivo.lote.definicion.filas] == ["deploy"] * 2


def test_ca_b6_5_4_un_csv_sin_contrasenas_no_deja_el_indicador_ni_el_aviso():
    lote = _lote_desde_csv(clonando("ci_usuario", "a;deploy"))
    datos = lote_a_bytes(lote, app_version="0.7.0")
    assert b"con_acceso_local" not in datos
    assert Aviso.CONTRASENA_NO_GUARDADA not in {a.codigo for a in leer_lote(datos).avisos}


# --- CL-B25 (parte del núcleo) -------------------------------------------------------------------


def test_cl_b25_cada_importacion_crea_sus_propios_secretos_y_no_toca_un_lote_ya_abierto():
    abierto = _lote_desde_csv(clonando("ci_usuario", "a;deploy"))
    antes = lote_a_bytes(abierto, app_version="0.7.0")
    r1 = importar(clonando("ci_contrasena", f"a;{CENTINELA}"))
    r2 = importar(clonando("ci_contrasena", f"a;{CENTINELA}"))
    s1, s2 = (fila(r, 2).opciones.cloudinit.contrasena for r in (r1, r2))
    assert s1 is not s2 and s1.revelar() == s2.revelar() == CENTINELA
    s1.olvidar()
    assert s1.revelar() == "" and s2.revelar() == CENTINELA  # olvidar uno no afecta al otro
    assert lote_a_bytes(abierto, app_version="0.7.0") == antes
    assert abierto.definicion.filas[0].opciones.cloudinit.contrasena is None


# --- Archivo CSV desde disco (E/S) ---------------------------------------------------------------


def test_ca_b6_5_3_leer_un_csv_con_contrasena_desde_disco_no_la_deja_en_el_resultado(
    tmp_path: Path,
):
    ruta = tmp_path / "lote.csv"
    ruta.write_bytes(csv_bytes(clonando("ci_contrasena;ci_ip", f"a;{CENTINELA};malo")))
    tabla = leer_archivo_csv(ruta)
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia=None,
    )
    assert CENTINELA not in repr(r)
    assert ruta.read_bytes().count(CENTINELA.encode()) == 1  # el archivo del usuario no se toca


# --- CA-B6.3.2 de extremo a extremo: las celdas de la fila frente al formulario ------------------


def test_ca_b6_3_2_el_plan_combina_cada_fila_con_el_formulario_celda_gana_vacia_hereda():
    info = InfoCloudInitPlantilla(unidad=True, tarjetas=(0,))
    privilegios = (*ROL_MVP4, "VM.Config.Cloudinit", "VM.PowerMgmt", "VM.GuestAgent.Audit")
    inv = inventario_con(plantilla_con(9000, "base", info), privilegios=privilegios)
    lineas = clonando(
        "ci_usuario;ci_dominio;esperar_ip", "a;fila-a;;no", "b;;;", "c;;otro.local;sí"
    )
    r = importar(lineas, inv=inv)
    base = ConfigCloudInit(
        usuario="formulario",
        dominio="base.local",
        tarjetas=(TarjetaCloudInit(0, ModoTarjeta.DHCP),),
        actualizar=True,
    )
    filas = tuple(
        dataclasses.replace(
            f,
            cfg=dataclasses.replace(
                f.cfg, cloudinit=base, esperar_ip=True, plazo_ip_s=90, encender=True
            ),
        )
        for f in filas_lote(r, r.numeros_validos)
    )
    plantilla_form = filas[0].cfg
    d = DefinicionLote(
        plantilla_form,
        len(filas),
        PatronNombres(""),
        Destino(),
        filas=filas,
        opciones=OpcionesLote.desde_config(plantilla_form),
    )
    plan = construir_plan(
        d, inv, [100, 101, 102], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    assert not [p for p in plan.problemas if p.severidad == Severidad.ERROR]
    a, b, c = (e.cfg for e in plan.elementos)
    assert (a.cloudinit.usuario, a.cloudinit.dominio, a.esperar_ip) == (
        "fila-a",
        "base.local",
        False,
    )
    assert (b.cloudinit.usuario, b.cloudinit.dominio, b.esperar_ip) == (
        "formulario",
        "base.local",
        True,
    )
    assert (c.cloudinit.usuario, c.cloudinit.dominio, c.esperar_ip) == (
        "formulario",
        "otro.local",
        True,
    )
    assert all(x.cloudinit.tarjetas == base.tarjetas and x.cloudinit.actualizar for x in (a, b, c))
    assert all(x.plazo_ip_s == 90 for x in (a, b, c))  # el plazo es el del formulario


# --- Más casos de celda --------------------------------------------------------------------------


@pytest.mark.parametrize("celda", ["dhcp", "DHCP", " dhcp ", "Dhcp"])
def test_rf_b6_3_ci_ip_dhcp_no_distingue_mayusculas_ni_espacios(celda):
    r = importar(clonando("ci_ip", f"a;{celda}"))
    assert fila(r, 2).opciones.cloudinit.tarjeta0.modo == ModoTarjeta.DHCP
    assert fila(r, 2).estado == EstadoFila.CORRECTA


def test_ca_b1_8_1_mas_de_tres_dns_en_la_celda_es_solo_aviso_v_b32():
    r = importar(clonando("ci_dns", 'a;"1.1.1.1 8.8.8.8 9.9.9.9 8.8.4.4"'))
    f = fila(r, 2)
    assert [(p.regla, p.severidad) for p in f.problemas] == [("V-B32", Severidad.AVISO)]
    assert f.estado == EstadoFila.CON_AVISO and 2 in r.numeros_validos


@pytest.mark.parametrize("columna", ["ci_usuario", "ci_dominio"])
def test_rnf_b6_6_un_token_en_un_texto_libre_de_cloudinit_invalida_la_fila_sin_eco(columna):
    token = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"
    r = importar(clonando(columna, f"a;{token}", "b;"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert token not in repr(r) and token not in repr(f.originales)
    assert fila(r, 3).estado == EstadoFila.CORRECTA


@pytest.mark.parametrize(
    "columna",
    [
        "ci_snippet_usuario",
        "ci_snippet_vendor",
        "ci_snippet_red",
        "ci_snippet_meta",
        "ci_dns",
        "ci_ip",
    ],
)
def test_obs_p2_a_un_token_en_snippets_dns_o_ip_no_se_conserva_en_ninguna_salida(columna, tmp_path):
    """OBS-P2-a: igual que ``ci_usuario``, el token no queda en ``originales``, ``valor`` ni en
    el CSV de filas con error."""
    token = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"
    tabla = tabla_csv(clonando(columna, f"a;{token}", "b;"))
    r = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia="pve1",
    )
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert token not in repr(r) and token not in repr(f.originales)
    assert all(token not in p.valor for p in f.problemas)
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, r, lambda p: p.regla)
    assert token.encode() not in ruta.read_bytes()


def test_rf_b6_3_una_fila_que_no_clona_pero_trae_esperar_ip_no_da_v_b39_solo_cloudinit_lo_da():
    r = importar(["nombre;esperar_ip;encender", "a;sí;sí"])
    assert [p.regla for p in fila(r, 1 + 1).problemas if p.regla == "V-B39"] == []
