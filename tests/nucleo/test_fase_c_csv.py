"""Fase C (0.8.0): las cinco columnas nuevas del CSV de importación (RF-C6.3, RF-C6.4, RF-C0.5).

Cubre CA-C6.3.1 a CA-C6.3.11, CA-C6.4.2, CA-C0.5.2, P-C4 (tope de 70 columnas) y P-C7
(``reescribir_red=sí`` explícito). ``p4_csv-070.csv`` y su ``.esperado.json`` los produjo el código
de 0.7.0 (``tests/datos/fase_c/p4_generar_datos.py``): 0.8.0 debe dar las mismas filas.

Las reglas que miran el servidor (V-C10, V-C30, V-C52 con el firewall del formulario) se evalúan
en el plan con las filas que salen de ``filas_lote``: ahí es donde «Comprobar» las nombra.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import MAX_COLUMNAS_CSV
from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.archivos.esquema_opciones import opciones_parciales_a_dict
from proxlaunch.nucleo.csv_importacion.columnas import COLUMNAS, resolver_columnas
from proxlaunch.nucleo.csv_importacion.errores_csv import escribir_filas_con_error
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv, leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, ResultadoImportacion
from proxlaunch.nucleo.csv_importacion.plantilla import ENCABEZADO_PLANTILLA, escribir_plantilla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    FirewallMV,
    FirewallParcial,
    GrupoSeguridad,
    InfoFirewall,
    Politica,
)
from proxlaunch.nucleo.inventario.exportacion import COLUMNAS_EXPORTACION, COLUMNAS_IP
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, PatronNombres
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.modelos.inventario import RedVirtual
from proxlaunch.nucleo.red.modelos import AccionTarjeta, CampoRed, ModoRedClon, RedClon
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_mvp3 import csv_bytes, perfil_base, perfiles_fabrica, tabla_csv
from .apoyo_mvp4 import inv_origen, plantilla_pve

DATOS_C = Path(__file__).resolve().parent.parent / "datos" / "fase_c"
COLUMNAS_C = (
    "reescribir_red",
    "cortafuegos",
    "grupo_seguridad",
    "politica_entrada",
    "politica_salida",
)
CLON = "origen;fuente"


def importar(lineas: Sequence[str], *, inv=None) -> ResultadoImportacion:
    return interpretar(
        tabla_csv(lineas),
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=inv,
        nodo_referencia="pve1",
    )


def fila(r: ResultadoImportacion, n: int):
    return next(f for f in r.filas if f.numero == n)


def reglas(f) -> list[tuple[str | None, str]]:
    return [(p.columna, p.regla) for p in f.problemas]


def clonando(cabecera: str, *filas: str) -> list[str]:
    """CSV cuyas filas clonan la plantilla ``base``."""
    return [
        f"nombre;{CLON};{cabecera}",
        *(f"{f.split(';', 1)[0]};clonar;base;{f.split(';', 1)[1]}" for f in filas),
    ]


def inventario_c(*, grupos=("web-01", "db-01"), vnets: dict | None = None):
    inv = inv_origen(plantillas=(plantilla_pve(9000, "base", "pve1"),))
    inv.catalogo = dataclasses.replace(
        inv.catalogo,
        firewall=InfoFirewall(
            grupos=tuple(GrupoSeguridad(g) for g in grupos),
            general_activo=True,
            entrada_por_grupo=dict.fromkeys(grupos, True),
        ),
    )
    if vnets:
        inv = dataclasses.replace(inv, redes_sdn=vnets)
    return inv


def plan_de(r: ResultadoImportacion, inv, formulario: dict | None = None):
    """Plan con las filas del CSV sobre un «formulario» (campos de ``ConfiguracionVM``)."""
    filas = filas_lote(r, r.numeros_validos)
    cambios = formulario or {}
    filas = tuple(dataclasses.replace(f, cfg=dataclasses.replace(f.cfg, **cambios)) for f in filas)
    d = DefinicionLote(filas[0].cfg, len(filas), PatronNombres(""), Destino(), filas=filas)
    return construir_plan(
        d, inv, list(range(100, 100 + len(filas))), [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip


def reglas_plan(plan, prefijo="V-C"):
    return [(p.regla, p.severidad) for p in plan.problemas if p.regla.startswith(prefijo)]


# --- RF-C6.3: las 5 columnas, sus alias y su posición ---


def test_rf_c6_3_las_cinco_columnas_canonicas_existen_y_el_total_es_59():
    canonicas = [c.canonica for c in COLUMNAS]
    assert set(COLUMNAS_C) <= set(canonicas)
    assert len(canonicas) == 59 and len(set(canonicas)) == 59


def test_rf_c6_3_las_marcadas_avanzadas_son_las_de_la_tabla():
    avanzadas = {c.canonica for c in COLUMNAS if c.avanzada and c.canonica in COLUMNAS_C}
    assert avanzadas == {"reescribir_red", "politica_entrada", "politica_salida"}


@pytest.mark.parametrize(
    ("alias", "canonica"),
    [
        ("rewrite_net", "reescribir_red"),
        ("red_clon", "reescribir_red"),
        ("Reescribir Red", "reescribir_red"),
        ("firewall", "cortafuegos"),
        ("CORTAFUEGOS", "cortafuegos"),
        ("security_group", "grupo_seguridad"),
        ("firewall_group", "grupo_seguridad"),
        ("Grupo-Seguridad", "grupo_seguridad"),
        ("grupo-seguridad", "grupo_seguridad"),
        ("policy_in", "politica_entrada"),
        ("Política entrada", "politica_entrada"),
        ("policy_out", "politica_salida"),
        ("politica_salida", "politica_salida"),
    ],
)
def test_rf_c6_3_los_alias_de_la_tabla_se_resuelven_a_su_columna_canonica(alias, canonica):
    mapa, avisos = resolver_columnas(["nombre", alias])
    assert mapa.posiciones == {"nombre": 0, canonica: 1}
    assert avisos == ()


@pytest.mark.parametrize(
    ("cabecera", "canonica"),
    [
        (["nombre", "cortafuegos", "firewall"], "cortafuegos"),
        (["nombre", "grupo_seguridad", "security_group"], "grupo_seguridad"),
        (["nombre", "grupo_seguridad", "firewall_group"], "grupo_seguridad"),
        (["nombre", "security_group", "firewall_group"], "grupo_seguridad"),
        (["nombre", "reescribir_red", "rewrite_net"], "reescribir_red"),
        (["nombre", "rewrite_net", "red_clon"], "reescribir_red"),
        (["nombre", "politica_entrada", "policy_in"], "politica_entrada"),
        (["nombre", "politica_salida", "policy_out"], "politica_salida"),
    ],
    ids=lambda c: "+".join(c[1:]) if isinstance(c, list) else None,
)
def test_ca_c6_3_3_dos_alias_de_la_misma_columna_dan_csv_columnas_duplicada(cabecera, canonica):
    with pytest.raises(ErrorProxLaunch) as exc:
        resolver_columnas(cabecera)
    assert exc.value.codigo == CodigoError.CSV_COLUMNAS
    assert exc.value.params["motivo"] == "duplicada"
    assert exc.value.params["columna"] == canonica


def test_ca_c6_3_3_el_error_de_duplicada_aparece_tambien_al_interpretar_el_csv():
    with pytest.raises(ErrorProxLaunch) as exc:
        importar(["nombre;cortafuegos;firewall", "a;si;no"])
    assert exc.value.codigo == CodigoError.CSV_COLUMNAS


def test_la_columna_red_clon_es_alias_de_reescribir_red_no_de_la_red_de_la_tarjeta():
    """``red`` (la tarjeta) y ``red_clon`` (alias de ``reescribir_red``) no se confunden."""
    mapa, _ = resolver_columnas(["nombre", "red", "red_clon"])
    assert set(mapa.posiciones) == {"nombre", "red", "reescribir_red"}


# --- CA-C6.3.1, CA-C6.3.11: un CSV de 0.7.0 da las mismas filas ---


def _proyeccion(r: ResultadoImportacion) -> list[dict]:
    return [
        {
            "numero": f.numero,
            "nombre": f.nombre,
            "estado": str(f.estado),
            "cfg": None if f.cfg is None else f.cfg.a_dict(),
            "opciones": None if f.opciones is None else opciones_parciales_a_dict(f.opciones),
            "problemas": [[p.columna, p.regla, str(p.severidad)] for p in f.problemas],
        }
        for f in r.filas
    ]


def test_ca_c6_3_1_un_csv_de_070_produce_las_mismas_filas_que_producia_070():
    datos = (DATOS_C / "p4_csv-070.csv").read_bytes()
    r = interpretar(
        leer_tabla(datos),
        perfil_base=perfil_base(),
        perfiles=tuple(perfiles_fabrica()),
        inv=None,
        nodo_referencia="pve1",
    )
    esperado = json.loads((DATOS_C / "p4_csv-070.esperado.json").read_text())
    assert json.loads(json.dumps(_proyeccion(r), sort_keys=True)) == esperado


def test_ca_c6_3_1_un_csv_sin_columnas_nuevas_no_fija_nada_de_la_fase_c():
    r = importar(["nombre;cpu;memoria;encender", "a;2;4 GiB;si", "b;4;8 GiB;"])
    for f in r.filas:
        assert f.estado == EstadoFila.CORRECTA
        assert f.cfg.firewall is None and f.cfg.red_clon is None
        assert f.opciones is None or (f.opciones.firewall is None and f.opciones.red_clon is None)
    assert r.avisos == ()


def test_ca_c6_3_11_red_y_vlan_en_filas_de_clon_no_reescriben_la_tarjeta_sin_reescribir_red():
    r = importar(clonando("red;vlan;modelo_red;mtu;limite_red", "a;vmbr1;30;e1000;1500;50"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CORRECTA
    assert f.opciones is None or f.opciones.red_clon is None
    assert f.cfg.red_clon is None


# --- CA-C6.3.2: celda vacía hereda ---


def test_ca_c6_3_2_una_celda_nueva_vacia_hereda_el_formulario_no_es_falso():
    r = importar(
        clonando(
            "reescribir_red;cortafuegos;grupo_seguridad;politica_entrada;politica_salida",
            "a;;;;;",
            "b;no;si;web-01;permitir;bloquear",
        )
    )
    assert fila(r, 2).opciones is None  # todo vacío = hereda todo (ni «falso» ni «no»)
    assert fila(r, 2).estado == EstadoFila.CORRECTA
    assert fila(r, 3).opciones.firewall == FirewallParcial(
        True, "web-01", Politica.PERMITIR, Politica.BLOQUEAR
    )
    assert fila(r, 3).opciones.red_clon == RedClon()  # «no» explícito = como la plantilla


@pytest.mark.parametrize(
    ("columna", "celda", "esperado"),
    [
        ("cortafuegos", "si", FirewallParcial(activo=True)),
        ("cortafuegos", "no", FirewallParcial(activo=False)),
        ("cortafuegos", "SÍ", FirewallParcial(activo=True)),
        ("cortafuegos", "yes", FirewallParcial(activo=True)),
        ("cortafuegos", "false", FirewallParcial(activo=False)),
        ("grupo_seguridad", "web-01", FirewallParcial(grupo="web-01")),
        ("politica_entrada", "bloquear", FirewallParcial(politica_entrada=Politica.BLOQUEAR)),
        ("politica_entrada", "DROP", FirewallParcial(politica_entrada=Politica.BLOQUEAR)),
        ("politica_entrada", "Permitir", FirewallParcial(politica_entrada=Politica.PERMITIR)),
        ("politica_entrada", "accept", FirewallParcial(politica_entrada=Politica.PERMITIR)),
        ("politica_salida", "drop", FirewallParcial(politica_salida=Politica.BLOQUEAR)),
        ("politica_salida", "ACCEPT", FirewallParcial(politica_salida=Politica.PERMITIR)),
    ],
)
def test_rf_c6_3_cada_celda_del_firewall_se_interpreta_y_solo_fija_la_suya(
    columna, celda, esperado
):
    r = importar(clonando(columna, f"a;{celda}"))
    assert fila(r, 2).opciones.firewall == esperado


# --- CA-C6.3.4: celdas inválidas, fila y columna, sin bloquear las otras filas ---


def test_ca_c6_3_4_una_celda_invalida_se_asocia_a_su_fila_y_columna_y_no_bloquea_las_demas():
    r = importar(
        clonando(
            "cortafuegos;grupo_seguridad;politica_entrada;politica_salida;reescribir_red",
            "a;quizas;;;;",
            "b;;1mal;;;",
            "c;;;rechazar;;",
            "d;;;;cerrar;",
            "e;;;;;tal vez",
            "f;si;web-01;permitir;permitir;si",
        )
    )
    for n, columna, regla in [
        (2, "cortafuegos", "E-M11.valor_no_admitido"),
        (3, "grupo_seguridad", "V-C31"),
        (4, "politica_entrada", "V-C39"),
        (5, "politica_salida", "V-C39"),
        (6, "reescribir_red", "E-M11.valor_no_admitido"),
    ]:
        f = fila(r, n)
        assert f.estado == EstadoFila.CON_ERROR, n
        assert reglas(f) == [(columna, regla)], n
        assert all(p.fila == n for p in f.problemas)
    assert fila(r, 7).estado == EstadoFila.CORRECTA
    assert r.numeros_validos == frozenset({7}) or set(r.numeros_validos) == {7}


def test_ca_c6_3_4_el_error_de_celda_usa_el_encabezado_tal_como_esta_en_el_archivo():
    r = importar(clonando("Grupo-Seguridad", "a;1mal"))
    assert fila(r, 2).problemas[0].columna == "Grupo-Seguridad"


def test_ca_c6_3_4_el_valor_del_error_va_acotado_y_sin_control():
    r = importar(clonando("politica_entrada", "a;" + "x" * 200))
    (p,) = fila(r, 2).problemas
    assert p.regla == "V-C39" and len(p.valor) <= 40


def test_ca_c6_3_4_un_grupo_que_no_existe_se_marca_en_comprobar_con_su_nombre():
    inv = inventario_c(grupos=("web-01",))
    r = importar(clonando("cortafuegos;grupo_seguridad", "a;si;web-01", "b;si;fantasma"), inv=inv)
    plan = plan_de(r, inv)
    errores = [p for p in plan.problemas if p.regla == "V-C30"]
    assert len(errores) == 1 and errores[0].severidad == Severidad.ERROR
    assert errores[0].params["grupo"] == "fantasma"
    assert plan.bloqueado


# --- CA-C6.3.5 y P-C4: el tope de columnas ---


def test_ca_c6_3_5_p_c4_un_csv_con_las_59_columnas_canonicas_se_acepta():
    cabecera = [c.canonica for c in COLUMNAS]
    datos = csv_bytes(
        [";".join(cabecera), ";".join("a" if c == "nombre" else "" for c in cabecera)]
    )
    tabla = leer_tabla(datos)
    assert len(tabla.encabezado) == 59
    r = interpretar(
        tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
        nodo_referencia=None,
    )  # fmt: skip
    assert fila(r, 2).estado == EstadoFila.CORRECTA


def test_p_c4_el_tope_es_70_se_acepta_con_70_columnas_y_se_rechaza_con_71():
    assert MAX_COLUMNAS_CSV == 70
    justo = ["nombre", *(f"extra{i}" for i in range(69))]
    assert (
        len(leer_tabla(csv_bytes([";".join(justo), ";".join("a" for _ in justo)])).encabezado) == 70
    )
    de_mas = [*justo, "una_mas"]
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_tabla(csv_bytes([";".join(de_mas), ";".join("a" for _ in de_mas)]))
    assert exc.value.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert exc.value.params["columnas"] == "71"


# --- CA-C6.3.6: fórmulas ---


@pytest.mark.parametrize("disparador", ["=", "+", "-", "@"])
@pytest.mark.parametrize("columna", ["grupo_seguridad", "cortafuegos", "politica_entrada"])
def test_ca_c6_3_6_una_celda_que_empieza_por_un_disparador_es_texto_nunca_una_formula(
    disparador, columna
):
    r = importar(clonando(columna, f"a;{disparador}HYPERLINK(1)"))
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR  # texto inválido para ese campo, nada se evalúa
    assert [c for c, _ in reglas(f)] == [columna]
    assert f.cfg is None or f.cfg.firewall is None


def test_ca_c6_3_6_el_csv_de_errores_neutraliza_las_celdas_de_la_fase_c_con_formula(tmp_path):
    tabla = tabla_csv(clonando("grupo_seguridad;politica_entrada", "a;=CMD()|' /c;@calc"))
    r = interpretar(
        tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
        nodo_referencia=None,
    )  # fmt: skip
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, r, lambda p: p.regla)
    texto = ruta.read_bytes().decode("utf-8-sig")
    celdas = next(csv.reader(io.StringIO(texto.split("\r\n", 1)[1]), delimiter=";"))
    assert "'@calc" in celdas
    assert not any(c.startswith(("=", "@", "+", "-")) for c in celdas)


# --- CA-C6.3.7: plantilla descargable ---


def test_ca_c6_3_7_la_plantilla_incluye_las_cinco_columnas_nuevas():
    assert all(c in ENCABEZADO_PLANTILLA for c in COLUMNAS_C)
    assert len(ENCABEZADO_PLANTILLA) == 40
    assert len(ENCABEZADO_PLANTILLA) <= MAX_COLUMNAS_CSV


@pytest.mark.parametrize("separador", [";", ","])
def test_ca_c6_3_7_la_plantilla_escrita_se_lee_sin_errores_con_las_columnas_nuevas(
    tmp_path, separador
):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta, separador=separador)
    tabla = leer_archivo_csv(ruta)
    assert all(c in tabla.encabezado for c in COLUMNAS_C)
    r = interpretar(
        tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
        nodo_referencia=None,
    )  # fmt: skip
    assert [f.nombre for f in r.filas if f.estado == EstadoFila.CON_ERROR] == []
    # (los avisos de GiB asumido de otras columnas no son de la fase C)
    assert not [a for a in r.avisos if a.params.get("columna") in COLUMNAS_C]


def test_ca_c6_3_7_los_ejemplos_de_la_fase_c_de_la_plantilla_son_los_documentados(tmp_path):
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    tabla = leer_archivo_csv(ruta)
    pos = {c: tabla.encabezado.index(c) for c in COLUMNAS_C}
    # grupo_seguridad queda vacío: el grupo depende del servidor (no se inventa uno).

    def celda(f, columna):
        return f.celdas[pos[columna]] if pos[columna] < len(f.celdas) else ""

    assert all(celda(f, "grupo_seguridad") == "" for f in tabla.filas)
    con_fw = [f for f in tabla.filas if celda(f, "cortafuegos") != ""]
    assert con_fw  # al menos un ejemplo de firewall
    r = interpretar(
        tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
        nodo_referencia=None,
    )  # fmt: skip
    assert not [f for f in r.filas if f.cfg is None]
    assert not any(c.startswith(("=", "+", "-", "@")) for f in tabla.filas for c in f.celdas if c)


# --- CA-C6.3.8 y P-C7: reescribir_red ---


@pytest.mark.parametrize("origen", ["vacio", "iso", "importar"])
def test_ca_c6_3_8_reescribir_red_si_con_origen_distinto_de_clonar_es_v_c51(origen):
    r = importar(["nombre;origen;fuente;reescribir_red", f"a;{origen};x;si"])
    f = fila(r, 2)
    assert f.estado == EstadoFila.CON_ERROR
    assert ("reescribir_red", "V-C51") in reglas(f)
    assert next(p for p in f.problemas if p.regla == "V-C51").severidad == Severidad.ERROR


def test_ca_c6_3_8_reescribir_red_no_o_vacio_con_origen_que_no_clona_no_es_error():
    r = importar(["nombre;origen;fuente;reescribir_red", "a;vacio;;no", "b;vacio;;"])
    assert fila(r, 2).estado == EstadoFila.CORRECTA
    assert fila(r, 3).estado == EstadoFila.CORRECTA
    assert "V-C51" not in {p.regla for f in r.filas for p in f.problemas}


def test_ca_c6_3_8_sin_columna_origen_la_fila_no_clona_y_reescribir_red_si_es_v_c51():
    r = importar(["nombre;reescribir_red", "a;si"])
    assert ("reescribir_red", "V-C51") in reglas(fila(r, 2))


def test_p_c7_reescribir_red_si_en_un_clon_aplica_las_columnas_de_red_a_net0_del_clon():
    r = importar(
        clonando("reescribir_red;red;vlan;modelo_red;mtu;limite_red", "a;si;prod;20;e1000;1500;50")
    )
    f = fila(r, 2)
    assert f.estado == EstadoFila.CORRECTA
    red = f.opciones.red_clon
    assert red.modo == ModoRedClon.PERSONALIZAR and len(red.tarjetas) == 1
    t = red.tarjetas[0]
    assert (t.indice, t.accion) == (0, AccionTarjeta.CAMBIAR)
    assert (t.bridge, t.modelo, t.vlan, t.mtu, t.limite_mb) == ("prod", "e1000", 20, 1500, 50.0)
    assert t.fijados == frozenset(CampoRed)
    assert t.mac_nueva is False  # la MAC se conserva


def test_p_c7_solo_se_fijan_las_columnas_con_valor_y_las_demas_se_conservan():
    r = importar(clonando("reescribir_red;red;vlan", "a;si;prod;", "b;si;;30"))
    ta, tb = (fila(r, n).opciones.red_clon.tarjetas[0] for n in (2, 3))
    assert ta.fijados == frozenset({CampoRed.BRIDGE}) and ta.bridge == "prod"
    assert tb.fijados == frozenset({CampoRed.VLAN}) and tb.vlan == 30


def test_p_c7_reescribir_red_no_fija_como_la_plantilla_aunque_haya_columnas_de_red():
    r = importar(clonando("reescribir_red;red;vlan", "a;no;prod;20"))
    red = fila(r, 2).opciones.red_clon
    assert red == RedClon() and not red.tarjetas


def test_p_c7_sin_reescribir_red_las_columnas_de_red_no_tocan_net0_del_clon():
    sin = importar(clonando("red;vlan", "a;prod;20"))
    con_no = importar(clonando("reescribir_red;red;vlan", "a;no;prod;20"))
    assert fila(sin, 2).cfg.redes == fila(con_no, 2).cfg.redes
    assert fila(sin, 2).opciones is None or fila(sin, 2).opciones.red_clon is None


def test_p_c7_la_vlan_fuera_de_rango_con_reescribir_red_la_rechaza_comprobar_con_v_c15():
    inv = inventario_c()
    r = importar(clonando("reescribir_red;vlan", "a;si;5000"), inv=inv)
    plan = plan_de(r, inv)
    assert ("V-C15", Severidad.ERROR) in reglas_plan(plan)
    assert plan.bloqueado


# --- CA-C6.3.9: grupo o políticas sin firewall activo ---


def test_ca_c6_3_9_grupo_con_cortafuegos_vacio_y_formulario_apagado_es_v_c52_no_se_ignora():
    inv = inventario_c()
    r = importar(clonando("grupo_seguridad", "a;web-01"), inv=inv)
    plan = plan_de(r, inv)
    assert ("V-C52", Severidad.ERROR) in reglas_plan(plan)
    assert plan.bloqueado


def test_ca_c6_3_9_politica_con_cortafuegos_vacio_y_formulario_apagado_tambien_es_v_c52():
    inv = inventario_c()
    r = importar(clonando("politica_entrada", "a;permitir"), inv=inv)
    assert ("V-C52", Severidad.ERROR) in reglas_plan(plan_de(r, inv))


def test_ca_c6_3_9_con_cortafuegos_si_en_la_fila_el_grupo_es_valido():
    inv = inventario_c()
    r = importar(clonando("cortafuegos;grupo_seguridad", "a;si;web-01"), inv=inv)
    assert "V-C52" not in {c for c, _ in reglas_plan(plan_de(r, inv))}


def test_ca_c6_3_9_con_el_formulario_activo_la_fila_hereda_el_firewall_y_no_hay_v_c52():
    inv = inventario_c()
    r = importar(clonando("grupo_seguridad", "a;db-01"), inv=inv)
    plan = plan_de(r, inv, {"firewall": FirewallMV(activo=True, grupo="web-01")})
    assert "V-C52" not in {c for c, _ in reglas_plan(plan)}
    assert plan.elementos[0].cfg.firewall == FirewallMV(activo=True, grupo="db-01")


# --- CA-C0.5.2: valor de la fila o, si está vacía, el del formulario ---


def test_ca_c0_5_2_cada_peticion_lleva_el_valor_de_su_fila_o_el_del_formulario():
    inv = inventario_c()
    r = importar(
        clonando(
            "cortafuegos;grupo_seguridad;politica_entrada",
            "a;si;db-01;permitir",
            "b;;;",
            "d;;;permitir",
        ),
        inv=inv,
    )
    formulario = FirewallMV(activo=True, grupo="web-01")
    plan = plan_de(r, inv, {"firewall": formulario})
    a, b, d = (e.cfg.firewall for e in plan.elementos)
    assert a == FirewallMV(activo=True, grupo="db-01", politica_entrada=Politica.PERMITIR)
    assert b == formulario
    assert d == FirewallMV(activo=True, grupo="web-01", politica_entrada=Politica.PERMITIR)
    assert not [p for p in plan.problemas if p.severidad == Severidad.ERROR]


def test_ca_c0_5_2_una_fila_puede_apagar_el_firewall_del_formulario_sin_grupo_heredado():
    inv = inventario_c()
    r = importar(clonando("cortafuegos", "a;no"), inv=inv)
    plan = plan_de(r, inv, {"firewall": FirewallMV(activo=True)})
    assert plan.elementos[0].cfg.firewall.activo is False
    assert "V-C52" not in {c for c, _ in reglas_plan(plan)}


def test_ca_c0_5_2_el_formulario_sin_firewall_y_filas_vacias_no_ponen_firewall():
    inv = inventario_c()
    r = importar(clonando("cortafuegos", "a;", "b;"), inv=inv)
    plan = plan_de(r, inv)
    assert all(e.cfg.firewall is None for e in plan.elementos)
    assert reglas_plan(plan) == []


# --- CA-C6.3.10: VNet y VLAN ---


def _vnets(vlan_aware: bool) -> dict:
    return {n: (RedVirtual("prod", None, vlan_aware, True),) for n in ("pve1", "pve2")}


def test_ca_c6_3_10_una_vlan_sobre_una_vnet_no_vlanaware_en_un_clon_es_v_c10():
    inv = inventario_c(vnets=_vnets(False))
    r = importar(clonando("reescribir_red;red;vlan", "a;si;prod;20"), inv=inv)
    errores = [p for p in plan_de(r, inv).problemas if p.regla == "V-C10"]
    assert errores and errores[0].severidad == Severidad.ERROR
    assert errores[0].params["vnet"] == "prod"


def test_ca_c6_3_10_con_una_vnet_vlanaware_la_vlan_del_clon_es_valida():
    inv = inventario_c(vnets=_vnets(True))
    r = importar(clonando("reescribir_red;red;vlan", "a;si;prod;20"), inv=inv)
    plan = plan_de(r, inv)
    assert "V-C10" not in {c for c, _ in reglas_plan(plan)}
    assert not plan.bloqueado


def test_ca_c6_3_10_una_fila_que_no_clona_con_red_vnet_vlanaware_no_queda_sin_nodo_elegible():
    inv = inventario_c(vnets=_vnets(True))
    r = importar(["nombre;origen;red;vlan", "a;vacio;prod;20"], inv=inv)
    assert fila(r, 2).estado != EstadoFila.CON_ERROR
    plan = plan_de(r, inv)
    assert [
        p
        for p in plan.problemas
        if p.regla in ("V-L11", "E-L01") and p.severidad == Severidad.ERROR
    ] == []


def test_ca_c6_3_10_una_fila_que_no_clona_con_vlan_sobre_vnet_no_vlanaware_da_v_c10():
    inv = inventario_c(vnets=_vnets(False))
    r = importar(["nombre;origen;red;vlan", "a;vacio;prod;20"], inv=inv)
    assert fila(r, 2).estado != EstadoFila.CON_ERROR
    assert "V-C10" in [p.regla for p in plan_de(r, inv).problemas]


# --- CA-C6.4.2: el CSV exportado por el inventario no se importa como creación ---


def _csv_de_exportacion(tmp_path: Path) -> Path:
    cab = [*COLUMNAS_EXPORTACION, *COLUMNAS_IP]
    fila_mv = [
        "ab12cd34", "2026-11-20T10:00:00", "web-01", "101", "pve1", "stopped", "", "no", "no",
        "proxlaunch;lote-ab12cd34", "coincide", "sí", "", "10.0.0.5", "ok",
    ]  # fmt: skip
    ruta = tmp_path / "inventario.csv"
    escribir_csv(ruta, cab, [fila_mv])
    return ruta


def test_ca_c6_4_2_el_csv_del_inventario_se_lee_sin_escribir_nada_ni_romper(tmp_path):
    ruta = _csv_de_exportacion(tmp_path)
    antes = ruta.read_bytes()
    tabla = leer_archivo_csv(ruta)
    assert tabla.encabezado[: len(COLUMNAS_EXPORTACION)] == COLUMNAS_EXPORTACION
    assert ruta.read_bytes() == antes


def test_ca_c6_4_2_el_csv_del_inventario_se_rechaza_con_un_motivo_propio(tmp_path):
    tabla = leer_archivo_csv(_csv_de_exportacion(tmp_path))
    with pytest.raises(ErrorProxLaunch) as e:
        interpretar(
            tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
            nodo_referencia="pve1",
        )  # fmt: skip
    assert e.value.codigo == CodigoError.CSV_COLUMNAS
    assert e.value.params["motivo"] == "inventario"


def test_ca_c6_4_2_el_csv_del_inventario_no_produce_filas_de_creacion(tmp_path):
    tabla = leer_archivo_csv(_csv_de_exportacion(tmp_path))
    try:
        r = interpretar(
            tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
            nodo_referencia="pve1",
        )  # fmt: skip
    except ErrorProxLaunch as e:
        assert e.codigo == CodigoError.CSV_COLUMNAS  # rechazado: correcto
        return
    assert [f for f in r.filas if f.cfg is not None and f.estado != EstadoFila.CON_ERROR] == []
