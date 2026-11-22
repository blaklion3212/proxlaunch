"""A2: notas automáticas (bloque, usuario, clon, codificación y límites).

Requisitos: RF-A2.1..A2.5 con las desviaciones de la §17 (P-10, P-11, P-12) y de la §0 de la
arquitectura (aviso desde 7500, error por encima de 8192; ``%XX`` solo con versión < 8.3).
También CL-A7, CL-A8 y los errores del traductor CA-A2.5.6, CA-A4.4.2 y CA-A3.4.12.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from proxlaunch.nucleo.api.traductor_errores import traducir_exitstatus, traducir_http
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.origen import ModoClon
from proxlaunch.nucleo.opciones.notas import (
    AVISO_DESCRIPCION,
    LEIDA_NO,
    LIMITE_DESCRIPCION,
    bloque_automatico,
    componer_descripcion,
    escapar_markdown,
    limpiar_texto_libre,
    neutralizar_porcentajes,
    usuario_para_notas,
)
from proxlaunch.nucleo.opciones.preparacion import preparar_elemento
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_fase_a import catalogo, cfg_vm, ctx_notas, inv_con
from .apoyo_mvp4 import cfg_clon, detalle_plantilla

CAPS = capacidades_para(Version("9.2.1", 9, 2, 1), None)
V92 = (9, 2)


def _desc(**cambios):
    """Descripción final de una MV (no clon) con el contexto fijo."""
    cfg = cfg_vm(**cambios)
    return componer_descripcion(cfg, ctx_notas(), None, V92)


# --- RF-A2.1: casilla y campo libre ---------------------------------------------------------------


def test_ca_a2_1_1_formulario_por_defecto_solo_bloque_automatico():
    """CA-A2.1.1: casilla marcada y «Notas» vacío -> ``description`` es el bloque y nada más."""
    d = _desc(notas_origen=True)
    assert d == bloque_automatico(ctx_notas())
    assert d.startswith("Creada con ProxLaunch 0.6.0")


def test_ca_a2_1_2_casilla_desmarcada_y_notas_vacio_no_envia_description():
    assert _desc(notas_origen=False) is None
    assert _desc(notas_origen=False, notas="") is None


@pytest.mark.parametrize("notas", ["   ", "\n\n", " \t \n"])
def test_a2_1_notas_solo_en_blanco_cuentan_como_vacias(notas):
    """Texto libre solo con espacios o saltos: no hay nada que enviar (Proxmox los perdería)."""
    assert _desc(notas_origen=False, notas=notas) is None


def test_ca_a2_1_3_casilla_desmarcada_y_texto_solo_texto_libre():
    assert _desc(notas_origen=False, notas="Servidor de **pruebas**") == "Servidor de **pruebas**"


def test_ca_a2_1_4_bloque_linea_en_blanco_texto_libre_sin_escapar():
    """CA-A2.1.4: bloque + línea en blanco + texto tal cual (sin escapar)."""
    d = _desc(notas_origen=True, notas="# Título *libre* <b>x</b>")
    assert d == bloque_automatico(ctx_notas()) + "\n\n# Título *libre* <b>x</b>"


# --- RF-A2.2: contenido del bloque ---------------------------------------------------------------


def test_ca_a2_2_1_el_bloque_lleva_version_fecha_lote_y_perfil_pero_no_usuario():
    """CA-A2.2.1 / CA-A2.2.5: versión, fecha ISO 8601 inyectada, lote y perfil; sin usuario."""
    b = bloque_automatico(ctx_notas(id_lote="ab12cd34", perfil="Servidor pequeño"))
    assert "ProxLaunch 0.6.0" in b
    assert "2026-11-21T10:30:15+00:00" in b
    assert "ab12cd34" in b and "Servidor pequeño" in b
    assert "Usuario" not in b and "@" not in b


def test_ca_a2_2_2_sin_perfil_la_linea_se_omite_sin_valor_vacio():
    b = bloque_automatico(ctx_notas(perfil=None))
    assert "Perfil" not in b and "None" not in b and ": \n" not in b
    assert not any(linea.rstrip().endswith(":") for linea in b.splitlines())


def test_ca_a2_2_3_mv_individual_omite_la_linea_del_lote():
    b = bloque_automatico(ctx_notas(id_lote=None))
    assert "Lote" not in b and "None" not in b


@pytest.mark.parametrize("caracter", list("#*_[]()<>`|~\\"))
def test_ca_a2_2_4_los_signos_markdown_se_escapan_en_el_bloque(caracter):
    """CA-A2.2.4: perfil y lote con signos Markdown salen escapados con ``\\``."""
    nombre = f"a{caracter}b"
    b = bloque_automatico(ctx_notas(perfil=nombre, id_lote=nombre))
    assert f"a\\{caracter}b" in b


def test_ca_a2_2_4_saltos_de_linea_y_esquemas_javascript_no_se_interpretan():
    """CA-A2.2.4: un nombre con saltos de línea no inyecta líneas ni listas; ``javascript:`` se
    neutraliza.
    """
    nombre = "perfil\n- Usuario: admin@pam\n[x](javascript:alert(1))"
    b = bloque_automatico(ctx_notas(perfil=nombre))
    lineas = b.splitlines()
    assert sum(1 for linea in lineas if linea.startswith("- Perfil:")) == 1
    assert not any(linea.startswith("- Usuario:") for linea in lineas)  # sin inyección de líneas
    assert "javascript:" not in b.replace("javascript\\:", "")
    assert "[" not in b.replace("\\[", "") and "](" not in b.replace("\\]\\(", "")


def test_a2_2_4_escapar_markdown_quita_controles_y_conserva_texto_legible():
    assert escapar_markdown("Servidor año ñ") == "Servidor año ñ"
    assert escapar_markdown("a\x00b\x07c") == "abc"
    assert "\n" not in escapar_markdown("a\r\nb\nc\rd")


def test_ca_a2_2_5_la_fecha_es_iso_8601_con_zona_y_viene_del_reloj_inyectado():
    otra = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-5)))
    b = bloque_automatico(ctx_notas(fecha=otra))
    assert "2030-01-02T03:04:05-05:00" in b
    # Mismo contexto -> mismo bloque (determinista).
    assert bloque_automatico(ctx_notas()) == bloque_automatico(ctx_notas())


# --- RF-A2.3: usuario creador ---------------------------------------------------------------------


def test_ca_a2_3_1_con_la_casilla_el_bloque_lleva_usuario_realm_sin_token():
    """CA-A2.3.1: ``usuario@realm`` y nunca el nombre del token ni su secreto."""
    usuario = usuario_para_notas("ana@pve!lab")
    assert usuario == "ana@pve"
    b = bloque_automatico(ctx_notas(usuario=usuario))
    assert "- Usuario: ana@pve" in b.replace("\\", "")
    assert "lab" not in b and "!" not in b


def test_ca_a2_3_2_sin_la_casilla_el_bloque_no_lleva_datos_del_usuario():
    assert "Usuario" not in bloque_automatico(ctx_notas(usuario=None))


def test_ca_a2_3_5_el_usuario_con_markdown_se_escapa():
    b = bloque_automatico(ctx_notas(usuario="a_b*c@pve"))
    assert "a\\_b\\*c@pve" in b


def test_a2_3_usuario_para_notas_con_secreto_pegado_corta_en_el_signo_de_admiracion():
    """El nombre completo del token (``user@realm!token``) nunca llega al bloque."""
    assert usuario_para_notas("root@pam!t1") == "root@pam"
    assert usuario_para_notas("root@pam") == "root@pam"
    assert usuario_para_notas("  ana@pve!x=11111111-2222  ") == "ana@pve"


# --- RF-A2.4: clon --------------------------------------------------------------------------------


def _clon(**cambios):
    return cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, **cambios)


def test_ca_a2_4_1_clon_plantilla_linea_en_blanco_bloque():
    """CA-A2.4.1: descripción de la plantilla + línea en blanco + bloque."""
    cfg = _clon(notas_origen=True)
    d = componer_descripcion(cfg, ctx_notas(), "Plantilla Ubuntu", V92)
    assert d == "Plantilla Ubuntu\n\n" + bloque_automatico(ctx_notas())


@pytest.mark.parametrize("previa", [None, "", "   \n"])
def test_ca_a2_4_2_plantilla_sin_descripcion_no_hay_linea_en_blanco_inicial(previa):
    cfg = _clon(notas_origen=True)
    d = componer_descripcion(cfg, ctx_notas(), previa, V92)
    assert d == bloque_automatico(ctx_notas())
    assert not d.startswith("\n")


def test_a2_4_clon_con_texto_libre_y_bloque_las_tres_partes_en_orden():
    cfg = _clon(notas_origen=True, notas="mi texto")
    d = componer_descripcion(cfg, ctx_notas(), "previa", V92)
    assert d == f"previa\n\n{bloque_automatico(ctx_notas())}\n\nmi texto"


def test_ca_a2_4_3_plantilla_ilegible_no_envia_description():
    """CA-A2.4.3 / P-10: sin poder leer la plantilla no se pisan sus notas."""
    cfg = _clon(notas_origen=True, notas="algo")
    assert componer_descripcion(cfg, ctx_notas(), LEIDA_NO, V92) is None


def test_ca_a2_4_3_preparar_elemento_clon_sin_detalle_o_con_descripcion_ilegible():
    cfg = _clon(notas_origen=True)
    assert preparar_elemento(cfg, ctx_notas(), None, V92).descripcion is None
    ilegible = dataclasses.replace(detalle_plantilla(), descripcion_legible=False)
    assert preparar_elemento(cfg, ctx_notas(), ilegible, V92).descripcion is None


def test_ca_a2_4_4_se_usa_la_ultima_descripcion_leida():
    """CA-A2.4.4: dos cálculos con distinta descripción de plantilla usan cada vez la última."""
    cfg = _clon(notas_origen=True)
    d1 = dataclasses.replace(detalle_plantilla(), descripcion="vieja")
    d2 = dataclasses.replace(detalle_plantilla(), descripcion="nueva")
    assert str(preparar_elemento(cfg, ctx_notas(), d1, V92).descripcion).startswith("vieja\n\n")
    assert str(preparar_elemento(cfg, ctx_notas(), d2, V92).descripcion).startswith("nueva\n\n")


def test_ca_a2_4_5_clon_sin_notas_no_envia_description():
    """CA-A2.4.5: el clon con la casilla desmarcada y «Notas» vacío deja que Proxmox copie la de la
    plantilla.
    """
    cfg = _clon(notas_origen=False)
    det = dataclasses.replace(detalle_plantilla(), descripcion="de la plantilla")
    assert preparar_elemento(cfg, ctx_notas(), det, V92).descripcion is None


def test_ca_a2_4_la_descripcion_de_la_plantilla_se_normaliza_igual_que_el_resto():
    """\\r\\n de la plantilla -> \\n; espacios finales recortados antes de la línea en blanco."""
    cfg = _clon(notas_origen=True)
    d = componer_descripcion(cfg, ctx_notas(), "a\r\nb  \r\n\r\n", V92)
    assert d is not None and d.startswith("a\nb\n\nCreada con")
    assert "\r" not in d


# --- RF-A2.5: codificación ------------------------------------------------------------------------


@pytest.mark.parametrize("texto", ["a\r\nb", "a\rb", "a\nb", "a\r\n\r\nb\rc"])
def test_ca_a2_5_1_solo_se_envia_lf(texto):
    """CA-A2.5.1: nunca ``\\r``."""
    d = _desc(notas=texto)
    assert d is not None and "\r" not in d


def test_ca_a2_5_1_crlf_equivale_a_lf():
    assert _desc(notas="a\r\nb\r\nc") == _desc(notas="a\nb\nc") == "a\nb\nc"


def test_a2_5_1_normalizar_saltos_no_es_un_cambio_que_merezca_aviso():
    """P-12: ``\\r\\n`` se normaliza sin aviso; solo los caracteres de control avisan (V-A14)."""
    assert limpiar_texto_libre("a\r\nb") == ("a\nb", False)
    assert limpiar_texto_libre("a\x07b") == ("ab", True)


@pytest.mark.parametrize("version", [None, (7, 4), (8, 0), (8, 2)])
def test_ca_a2_5_2_porcentaje_xx_se_neutraliza_antes_de_8_3(version):
    """CA-A2.5.2: ``%41`` literal no llega intacto en ≤ 8.2 (ni con versión desconocida)."""
    d = componer_descripcion(cfg_vm(notas="100%41 y %ZZ"), ctx_notas(), None, version)
    assert d is not None
    assert "%41" not in d
    assert "%ZZ" in d  # solo los hexadecimales de dos dígitos se tocan
    assert d.replace("​", "") == "100%41 y %ZZ"  # nada se pierde: solo se inserta U+200B


@pytest.mark.parametrize("version", [(8, 3), (8, 4), (9, 0), (9, 2)])
def test_ca_a2_5_2_a_partir_de_8_3_no_se_toca(version):
    assert neutralizar_porcentajes("100%41", version) == "100%41"


def test_a2_5_2_porcentaje_de_una_sola_cifra_o_final_de_texto_no_se_toca():
    assert neutralizar_porcentajes("100% y %4 y %", (8, 0)) == "100% y %4 y %"


@pytest.mark.parametrize("fin", ["", "   ", "\n\n", " \t\n "])
def test_ca_a2_5_8_no_se_prometen_los_espacios_finales(fin):
    """CA-A2.5.8: el texto final se envía sin espacios ni líneas en blanco al final."""
    assert _desc(notas="hola" + fin) == "hola"


def test_ca_a2_5_7_control_eliminados_con_aviso_v_a14():
    """CA-A2.5.7 / P-12: se quitan los caracteres de control (salvo \\n y \\t) y se avisa."""
    d = _desc(notas="a\x00b\x1bc\td\ne\x7f")
    assert d == "abc\td\ne"
    inv = inv_con(catalogo())
    problemas = validar_vm(cfg_vm(notas="a\x00b"), inv, CAPS)
    avisos = [p for p in problemas if p.codigo == "V-A14"]
    assert len(avisos) == 1 and avisos[0].severidad == Severidad.AVISO
    assert not [p for p in validar_vm(cfg_vm(notas="a\tb\nc"), inv, CAPS) if p.codigo == "V-A14"]


def test_a2_5_5_el_conteo_es_en_caracteres_no_en_bytes():
    """CA-A2.5.5: 7000 ñ (14000 bytes) caben bajo el límite de 8192 caracteres."""
    texto = "ñ" * 7000
    d = _desc(notas=texto)
    assert len(d) == 7000
    assert not [
        p for p in validar_vm(cfg_vm(notas=texto), inv_con(catalogo()), CAPS) if p.codigo == "V-A07"
    ]


# --- Límites de longitud (CA-A2.5.3, CL-A7, CL-A8, P-11) ------------------------------------------


def _problemas_de_notas(notas, inv=None, **cfg):
    inv = inv or inv_con(catalogo())
    return {
        p.codigo: p
        for p in validar_vm(cfg_vm(notas=notas, **cfg), inv, CAPS)
        if p.codigo in ("V-A07", "V-A08")
    }


@pytest.mark.parametrize(
    ("total", "aviso", "error"),
    [
        (1, False, False),
        (AVISO_DESCRIPCION - 1, False, False),  # 7499: acepta sin aviso
        (AVISO_DESCRIPCION, True, False),  # 7500: aviso (desviación §0)
        (AVISO_DESCRIPCION + 1, True, False),  # 7501: aviso, ya no bloquea (P-11)
        (LIMITE_DESCRIPCION, True, False),  # 8192: se acepta
        (LIMITE_DESCRIPCION + 1, False, True),  # 8193: error
        (20000, False, True),
    ],
)
def test_ca_a2_5_3_y_cl_a7_umbrales_de_longitud(total, aviso, error):
    """CA-A2.5.3 / CL-A7 / P-11: aviso desde 7500, bloqueo solo por encima de 8192."""
    p = _problemas_de_notas("x" * total)
    assert ("V-A08" in p) is aviso
    assert ("V-A07" in p) is error
    if aviso:
        assert p["V-A08"].severidad == Severidad.AVISO
        assert p["V-A08"].params == {"total": str(total), "limite": str(LIMITE_DESCRIPCION)}
    if error:
        e = p["V-A07"]
        assert e.severidad == Severidad.ERROR and e.campo == "notas"
        assert e.params == {
            "total": str(total),
            "limite": str(LIMITE_DESCRIPCION),
            "sobran": str(total - LIMITE_DESCRIPCION),
        }


def test_ca_a2_5_3_un_texto_de_8192_se_envia_completo_y_el_de_8193_lo_bloquea_el_servicio():
    """CA-A2.5.3: «nunca se envía» una descripción > 8192: ``validar_vm`` da ERROR y el servicio no
    hace POST.
    """
    assert len(_desc(notas="y" * 8192)) == 8192
    assert any(
        p.codigo == "V-A07" and p.severidad == Severidad.ERROR
        for p in validar_vm(cfg_vm(notas="y" * 8193), inv_con(catalogo()), CAPS)
    )


def test_ca_a2_5_3_el_total_incluye_el_bloque_automatico():
    """El total medido es el de la descripción final (bloque + libre), no solo el texto libre."""
    bloque = len(bloque_automatico(ctx_notas()))
    libre = LIMITE_DESCRIPCION - bloque - 2  # + separador "\n\n"
    p = _problemas_de_notas("z" * libre, notas_origen=True, descripcion=None)
    assert "V-A07" not in p
    p = _problemas_de_notas("z" * (libre + 40), notas_origen=True)
    assert "V-A07" in p


def test_ca_a2_5_3_con_la_descripcion_ya_calculada_se_mide_esa():
    """V-A07/V-A08 miden ``cfg.descripcion`` cuando ``preparar_elemento`` ya la calculó."""
    cfg = preparar_elemento(cfg_vm(notas_origen=True, notas="k" * 8200), ctx_notas(), None, V92)
    codigos = [p.codigo for p in validar_vm(cfg, inv_con(catalogo()), CAPS)]
    assert "V-A07" in codigos


def test_ca_a2_5_4_y_cl_a8_el_total_de_un_clon_incluye_la_descripcion_de_la_plantilla():
    """CA-A2.5.4 / CL-A8: plantilla casi al límite + bloque + texto corto > 8192 bloquea."""
    from proxlaunch.nucleo.modelos.catalogo import Plantilla

    previa = "p" * 8150
    det = dataclasses.replace(detalle_plantilla(), descripcion=previa)
    cat = catalogo(plantillas=(Plantilla(9000, "base", "pve1", None, None, det),))
    cfg = _clon(notas_origen=True, notas="corto")
    p = _problemas_de_notas("corto", inv_con(cat), notas_origen=True)  # no clon: referencia
    assert "V-A07" not in p
    problemas = validar_vm(cfg_vm_clon(cfg), inv_con(cat), CAPS)
    assert any(x.codigo == "V-A07" and x.severidad == Severidad.ERROR for x in problemas)


def cfg_vm_clon(cfg):
    """Un clon sobre ``inventario()``: mismo nodo y nombre de la plantilla en el catálogo."""
    return dataclasses.replace(cfg, nodo="pve1", vmid=100, nombre="srv-web-01")


def test_cl_a8_sin_la_plantilla_en_catalogo_no_se_estima_la_descripcion_previa():
    """Si el catálogo no conoce la plantilla, el clon se valida solo con lo propio."""
    cfg = _clon(notas_origen=True, notas="corto")
    problemas = validar_vm(cfg_vm_clon(cfg), inv_con(catalogo()), CAPS)
    assert not [p for p in problemas if p.codigo == "V-A07"]


# --- Traductor de errores (CA-A2.5.6, CA-A4.4.2, CA-A3.4.12) --------------------------------------


def test_ca_a2_5_6_400_de_8192_caracteres_se_traduce_a_descripcion_larga():
    """CA-A2.5.6: 400 «value may only be 8192 characters long» -> DESCRIPCION_LARGA (campo
    ``description``, el que la interfaz muestra como «Notas»)."""
    cuerpo = '{"errors":{"description":"value may only be 8192 characters long"},"data":null}'
    e = traducir_http(400, "Parameter verification failed.", cuerpo)
    assert e.codigo == CodigoError.DESCRIPCION_LARGA
    assert e.params.get("campo") == "description"


def test_ca_a2_5_6_otro_400_no_se_confunde_con_descripcion_larga():
    cuerpo = '{"errors":{"cores":"value must be >= 1"},"data":null}'
    e = traducir_http(400, "Parameter verification failed.", cuerpo)
    assert e.codigo == CodigoError.PARAMETRO_INVALIDO


def test_ca_a4_4_2_403_pool_inexistente_no_es_un_permiso_generico():
    """CA-A4.4.2: 403 «pool 'X' does not exist» -> POOL_INEXISTENTE con el pool nombrado."""
    e = traducir_http(403, "pool 'prod' does not exist", '{"data":null}')
    assert e.codigo == CodigoError.POOL_INEXISTENTE
    assert e.params["pool"] == "prod"


def test_ca_a4_4_2_un_403_de_permiso_normal_sigue_siendo_permiso_insuficiente():
    e = traducir_http(403, "Permission check failed (/vms/100, VM.Allocate)", '{"data":null}')
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE


def test_ca_a3_4_12_fallo_en_la_tarea_por_politica_de_etiquetas_se_traduce():
    """CA-A3.4.12: «Sys.Modify for modifying tag 'x'» en el resultado de la tarea ->
    ETIQUETA_RECHAZADA.
    """
    e = traducir_exitstatus("Permission check failed (/, Sys.Modify for modifying tag 'prod')")
    assert e.codigo == CodigoError.ETIQUETA_RECHAZADA
    assert e.params.get("tag") == "prod"


def test_ca_a3_4_12_el_403_directo_por_etiqueta_tambien_se_traduce():
    e = traducir_http(403, "Sys.Modify for modifying tag 'web'", '{"data":null}')
    assert e.codigo == CodigoError.ETIQUETA_RECHAZADA and e.params.get("tag") == "web"


def test_cl_a8_clon_sin_catalogo_no_estima_la_descripcion_de_la_plantilla():
    """Sin catálogo (inventario sin leer) el clon se valida solo con lo propio."""
    cfg = cfg_vm_clon(_clon(notas_origen=True, notas="corto"))
    assert not [p for p in validar_vm(cfg, inv_con(None), CAPS) if p.codigo.startswith("V-A0")]


def test_ca_a3_4_12_una_etiqueta_hash_en_el_resultado_de_la_tarea_no_se_nombra():
    """Proxmox a veces escribe ``HASH(0x…)`` en lugar del nombre: no se muestra como etiqueta."""
    e = traducir_exitstatus("Sys.Modify for modifying tag 'HASH(0x55d0)'")
    assert e.codigo == CodigoError.ETIQUETA_RECHAZADA and "tag" not in e.params
