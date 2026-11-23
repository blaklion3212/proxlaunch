"""Correcciones de la fase C tras la revisión F5 (0.8.0): pruebas de regresión del núcleo.

Derivadas de docs/investigacion/fase-c-errores-f5.md y docs/requisitos/fase-c.md:
BUG-C-P3-1 (``cortafuegos=no`` en una fila apaga el firewall de esa fila sin heredar grupo ni
políticas del formulario; V-C52 solo si la propia fila fija grupo o políticas, CA-C6.3.9),
BUG-C-P3-2 (solo cuentan las reglas de grupo ACTIVAS de la plantilla; P-C8, CA-C3.6.2) y
BUG-C-P4-1 (el CSV del inventario se rechaza con ``motivo="inventario"``, CA-C6.4.2).
Solo se simula la red; todo lo demás es código real.
"""

from __future__ import annotations

import dataclasses

import pytest

from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.lectura import leer_info_firewall
from proxlaunch.nucleo.firewall.modelos import FirewallMV, FirewallParcial, Politica, ReglaFirewall
from proxlaunch.nucleo.firewall.reglas import regla_ya_existe
from proxlaunch.nucleo.inventario.exportacion import COLUMNAS_EXPORTACION, COLUMNAS_IP
from proxlaunch.nucleo.lote.filas import definicion_por_filas
from proxlaunch.nucleo.lote.modelos import EstadoMV, FilaLote
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.opciones.modelos import OpcionesLote, OpcionesParciales
from proxlaunch.nucleo.opciones.preparacion import combinar_firewall
from proxlaunch.nucleo.servicios.creacion import AVISO_FIREWALL_GRUPO_YA_ESTABA

from .apoyo_fase_a import cfg_vm
from .apoyo_fase_c_firewall import GRUPO, MundoC, fw, secuencia
from .apoyo_mvp3 import perfil_base, perfiles_fabrica
from .apoyo_mvp4 import cfg_clon

FORMULARIO = FirewallMV(
    activo=True, grupo=GRUPO, politica_entrada=Politica.PERMITIR, politica_salida=Politica.BLOQUEAR
)


# --- BUG-C-P3-1: «cortafuegos=no» no hereda grupo ni políticas del formulario ------------------


def test_bug_c_p3_1_cortafuegos_no_apaga_y_no_hereda_grupo_ni_politicas_del_formulario():
    r = combinar_firewall(FORMULARIO, FirewallParcial(activo=False))
    assert r == FirewallMV()  # apagado, sin grupo y con las políticas por defecto
    assert r.activo is False and r.grupo is None


def test_bug_c_p3_1_cortafuegos_no_sin_formulario_da_el_firewall_apagado_por_defecto():
    assert combinar_firewall(None, FirewallParcial(activo=False)) == FirewallMV()


def test_bug_c_p3_1_cortafuegos_no_con_grupo_propio_conserva_el_grupo_para_que_salga_v_c52():
    r = combinar_firewall(FORMULARIO, FirewallParcial(activo=False, grupo="db-01"))
    assert r.activo is False and r.grupo == "db-01"


def test_bug_c_p3_1_cortafuegos_no_con_politica_propia_la_conserva_y_no_hereda_la_otra():
    r = combinar_firewall(
        FORMULARIO, FirewallParcial(activo=False, politica_entrada=Politica.PERMITIR)
    )
    defecto = FirewallMV()
    assert r.politica_entrada == Politica.PERMITIR
    assert r.politica_salida == defecto.politica_salida  # no la del formulario (BLOQUEAR)


def test_bug_c_p3_1_una_celda_vacia_o_cortafuegos_si_siguen_heredando_el_formulario():
    assert combinar_firewall(FORMULARIO, None) == FORMULARIO
    assert combinar_firewall(FORMULARIO, FirewallParcial()) == FORMULARIO
    r = combinar_firewall(
        FORMULARIO, FirewallParcial(activo=True, politica_salida=Politica.PERMITIR)
    )
    assert r.grupo == GRUPO and r.politica_entrada == Politica.PERMITIR
    assert r.politica_salida == Politica.PERMITIR


def _por_filas(m: MundoC, *parciales: FirewallParcial | None, formulario=FORMULARIO):
    """Plan de un lote por filas (``a-01``, ``a-02``…) sobre la plantilla ``base``; la fila
    ``i`` lleva ``parciales[i]``; el formulario aporta ``formulario`` a todas."""
    base = dataclasses.replace(cfg_clon("base"), discos=cfg_vm().discos, redes=cfg_vm().redes)
    filas = [
        FilaLote(
            f"a-{i:02d}",
            base,
            opciones=None if p is None else OpcionesParciales(firewall=p),
        )
        for i, p in enumerate(parciales, 1)
    ]
    definicion = dataclasses.replace(
        definicion_por_filas(filas, plantilla_base=base),
        opciones=OpcionesLote(firewall=formulario),
    )
    return m.planificar(definicion)


def _reglas_vc(plan, regla: str) -> list:
    return [p for p in plan.problemas if p.regla == regla]


def test_bug_c_p3_1_fila_con_cortafuegos_no_no_da_v_c52_aunque_el_formulario_tenga_grupo():
    m = MundoC()
    m.leer_firewall()
    plan = _por_filas(m, FirewallParcial(activo=False))
    assert _reglas_vc(plan, "V-C52") == []
    assert not plan.bloqueado, plan.problemas


def test_bug_c_p3_1_fila_con_cortafuegos_no_y_grupo_propio_si_da_v_c52():
    m = MundoC()
    m.leer_firewall()
    plan = _por_filas(m, FirewallParcial(activo=False, grupo=GRUPO))
    assert _reglas_vc(plan, "V-C52")
    assert plan.bloqueado


def test_bug_c_p3_1_la_mv_con_cortafuegos_no_no_recibe_ninguna_peticion_de_firewall():
    """La fila 1 apaga el firewall; la 2 hereda el del formulario (control: sí lo aplica)."""
    m = MundoC()
    m.leer_firewall()
    plan = _por_filas(m, FirewallParcial(activo=False), None)
    assert not plan.bloqueado, plan.problemas
    m.cl.llamadas.clear()
    libro = m.ejecutar(plan)
    apagada, heredera = 100, 101  # los VMID siguientes libres, en el orden de las filas
    assert libro.entrada(apagada).estado != EstadoMV.PARCIAL
    seq = secuencia(m.cl, apagada)
    assert "fw_opciones" not in seq and "fw_regla" not in seq
    assert not [
        c for c in m.cl.llamadas if f"/qemu/{apagada}/firewall/" in c.ruta and c.metodo != "GET"
    ]
    assert not m.cl.fw_reglas.get(apagada)
    assert not m.cl.fw_opciones.get(apagada, {}).get("enable")
    # Control: la otra fila sí aplica el firewall del formulario.
    seq2 = secuencia(m.cl, heredera)
    assert "fw_opciones" in seq2 and "fw_regla" in seq2
    assert [r["action"] for r in m.cl.fw_reglas[heredera]] == [GRUPO]


# --- BUG-C-P3-2: solo cuentan las reglas de grupo activas de la plantilla -----------------------


def test_bug_c_p3_2_regla_ya_existe_ignora_la_regla_de_grupo_deshabilitada():
    inactiva = ReglaFirewall("group", GRUPO, activa=False)
    assert regla_ya_existe([inactiva], GRUPO) is False
    assert regla_ya_existe([ReglaFirewall("group", GRUPO, activa=True)], GRUPO) is True
    assert regla_ya_existe([inactiva, ReglaFirewall("group", GRUPO, activa=True)], GRUPO) is True


def test_bug_c_p3_2_regla_ya_existe_distingue_grupo_y_tipo():
    assert regla_ya_existe([ReglaFirewall("group", "db", activa=True)], GRUPO) is False
    assert regla_ya_existe([ReglaFirewall("in", GRUPO, activa=True)], GRUPO) is False
    assert regla_ya_existe([], GRUPO) is False


def test_bug_c_p3_2_la_lectura_de_la_plantilla_no_cuenta_el_grupo_de_una_regla_deshabilitada():
    m = MundoC()
    m.cl.fw_reglas[9000] = [
        {"type": "group", "action": GRUPO, "enable": 0},
        {"type": "group", "action": "db", "enable": 1},
    ]
    m.cl.grupos["db"] = []
    cat = m.inv.catalogo
    info = leer_info_firewall(m.sesion.cliente, cat.permisos, (GRUPO,), list(cat.plantillas or ()))
    p = info.plantillas[9000]
    assert p.legible and p.con_reglas is True
    assert p.grupos == frozenset({"db"})


def test_bug_c_p3_2_regla_de_grupo_deshabilitada_en_la_plantilla_se_anade_una_activa_sin_aviso():
    m = MundoC()
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 0}]
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert "fw_regla" in secuencia(m.cl)
    assert f"{AVISO_FIREWALL_GRUPO_YA_ESTABA}:{GRUPO}" not in r.avisos
    reglas = m.cl.fw_reglas[100]
    assert [(x["type"], x["action"], int(x["enable"])) for x in reglas] == [
        ("group", GRUPO, 0),
        ("group", GRUPO, 1),
    ]


def test_bug_c_p3_2_regla_de_grupo_activa_en_la_plantilla_no_se_duplica_y_avisa():
    m = MundoC()
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 1}]
    m.leer_firewall()
    r = m.crear(m.cfg(None, firewall=fw()))
    assert "fw_regla" not in secuencia(m.cl)
    assert len(m.cl.fw_reglas[100]) == 1
    assert f"{AVISO_FIREWALL_GRUPO_YA_ESTABA}:{GRUPO}" in r.avisos
    assert r.desenlace == Desenlace.CON_AVISOS


def test_bug_c_p3_2_sin_leer_la_plantilla_la_comprobacion_del_clon_tambien_ignora_la_inactiva():
    """DT-C10: ``GET …/rules`` del clon antes del ``POST``; la inactiva no impide la regla."""
    m = MundoC()
    m.cl.fw_reglas[9000] = [{"type": "group", "action": GRUPO, "enable": 0}]
    r = m.crear(m.cfg(None, firewall=fw()))  # sin ``leer_firewall``: plantilla sin leer
    assert "fw_leer_reglas" in secuencia(m.cl)
    assert "fw_regla" in secuencia(m.cl)
    assert [int(x["enable"]) for x in m.cl.fw_reglas[100]] == [0, 1]
    assert r.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS)


# --- BUG-C-P4-1: el CSV del inventario se rechaza con el motivo «inventario» ---------------------


def test_bug_c_p4_1_el_csv_exportado_por_el_inventario_da_csv_columnas_con_motivo_inventario(
    tmp_path,
):
    cab = [*COLUMNAS_EXPORTACION, *COLUMNAS_IP]
    fila_mv = [
        "ab12cd34", "2026-11-20T10:00:00", "web-01", "101", "pve1", "stopped", "", "no", "no",
        "proxlaunch;lote-ab12cd34", "coincide", "sí", "", "10.0.0.5", "ok",
    ]  # fmt: skip
    ruta = tmp_path / "inventario.csv"
    escribir_csv(ruta, cab, [fila_mv])
    tabla = leer_archivo_csv(ruta)
    with pytest.raises(ErrorProxLaunch) as e:
        interpretar(
            tabla, perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()), inv=None,
            nodo_referencia="pve1",
        )  # fmt: skip
    assert e.value.codigo == CodigoError.CSV_COLUMNAS
    assert e.value.params["motivo"] == "inventario"


def test_bug_c_p4_1_un_csv_de_importacion_normal_no_se_confunde_con_el_del_inventario(tmp_path):
    ruta = tmp_path / "ok.csv"
    escribir_csv(ruta, ["nombre", "origen", "fuente"], [["a", "clonar", "base"]])
    r = interpretar(
        leer_archivo_csv(ruta), perfil_base=perfil_base(), perfiles=tuple(perfiles_fabrica()),
        inv=None, nodo_referencia="pve1",
    )  # fmt: skip
    assert r.filas
