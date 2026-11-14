"""Resumen de una máquina y de un lote con origen del SO (RF-O08, RF-O13, RF-O14, RF-O18,
RF-O20, RF-O29; CA-O08.9, CA-O14.3, CA-O29.3)."""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.resumen_lote import (
    ResumenLote,
    texto_origen_del_plan,
    texto_peticiones,
)
from proxlaunch.nucleo.lote.modelos import (
    AccionPeticion,
    DefinicionLote,
    Destino,
    ElementoPlan,
    ModoDestino,
    MotivoReparto,
    PatronNombres,
    PeticionSimulada,
    Plan,
    ResultadoSimulacion,
)
from proxlaunch.nucleo.modelos.origen import AjustesClon, ModoClon, TipoSO

from .apoyo_mvp4 import (
    ROL_10,
    VOLID_VIRTIO,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    permisos,
)


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


def pintar(resumen, cfg, *, perms=None, cambios=(), avanzado=False, problemas=()):
    resumen.actualizar(
        cfg,
        ["scsi0"],
        list(problemas),
        avanzado=avanzado,
        motivo_nodo="",
        bloqueo=None,
        ocupado=False,
        cambios_asistente=cambios,
        permisos=perms,
    )
    return resumen.texto_html


# --- Línea de origen -----------------------------------------------------------------------------


def test_con_origen_vacia_el_resumen_no_tiene_linea_de_origen(resumen):
    html = pintar(resumen, cfg_base())
    assert "Origen" not in html


def test_ca_o08_9_iso_muestra_el_origen_el_montaje_y_que_la_app_no_enciende_la_maquina(resumen):
    html = pintar(resumen, cfg_iso(), perms=permisos())
    assert "<b>Origen:</b>" in html
    assert "Montará el ISO «alpine.iso» como CD" in html
    assert "no enciende la máquina" in html


def test_ca_o08_3_el_orden_de_arranque_solo_se_muestra_con_vm_config_disk_confirmado(resumen):
    con = pintar(resumen, cfg_iso(), perms=permisos())
    assert "Orden de arranque: disco, CD, red." in con
    sin = pintar(resumen, cfg_iso(), perms=permisos(ROL_10))
    assert "Orden de arranque" not in sin


def test_ca_o08_3_con_permisos_desconocidos_no_se_afirma_un_orden_de_arranque(resumen):
    html = pintar(resumen, cfg_iso(), perms=None)
    assert "Orden de arranque" not in html


def test_ca_o14_1_windows_con_drivers_muestra_el_cd_y_como_cargarlos(resumen):
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_11, drivers=VOLID_VIRTIO)
    html = pintar(resumen, cfg, perms=permisos())
    assert "CD de drivers (virtio-win): virtio-win-0.1.271.iso" in html
    assert "vioscsi" in html and "NetKVM" in html


def test_ca_o14_3_sin_drivers_no_muestra_cd_y_deja_un_aviso_persistente(resumen):
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_11, sin_drivers=True)
    html = pintar(resumen, cfg, perms=permisos())
    assert "CD de drivers" not in html
    assert "Windows no verá el disco VirtIO ni la red" in resumen._avisos.text()
    assert resumen._avisos.isVisible()


def test_linux_no_muestra_aviso_de_drivers(resumen):
    pintar(resumen, cfg_iso(), perms=permisos())
    assert "VirtIO" not in resumen._avisos.text()


def test_ca_o13_el_resumen_lista_lo_que_aplico_el_asistente(resumen):
    from proxlaunch.nucleo.origen.asistente import aplicar_asistente

    res = aplicar_asistente(cfg_base(), TipoSO.WINDOWS_11)
    cfg = cfg_iso(tipo_so=TipoSO.WINDOWS_11)
    html = pintar(resumen, cfg, perms=permisos(), cambios=res.cambios)
    assert "Windows 11 el asistente aplicó" in html
    assert html.count("• ") >= len(res.cambios)


def test_ca_o17_importar_dice_que_el_primer_disco_es_una_copia_de_la_imagen(resumen):
    html = pintar(resumen, cfg_import())
    assert "El primer disco será una copia del disco «cirros.qcow2»" in html


def test_ca_o20_clon_muestra_forma_de_copiar_y_oculta_hardware_propio(resumen):
    html = pintar(resumen, cfg_clon(efectivo=ModoClon.ENLAZADO))
    assert "Forma de copiar" in html
    assert "comparte el disco base con la plantilla" in html
    assert "no borres la plantilla" in html
    assert "los de la plantilla" in html
    assert "Arranque" not in html


def test_ca_o20_clon_completo_no_advierte_dependencia(resumen):
    html = pintar(resumen, cfg_clon(modo=ModoClon.COMPLETO, efectivo=ModoClon.COMPLETO))
    assert "comparte el disco base" not in html


def test_ca_o22_los_ajustes_del_clon_aparecen_en_el_resumen(resumen):
    html = pintar(resumen, cfg_clon(ajustes=AjustesClon(cores=4, memoria_mib=4096)))
    assert "Ajustes:" in html


def test_los_nombres_del_servidor_se_escapan_en_el_resumen(resumen):
    cfg = cfg_iso("local:iso/<b>x</b>.iso")
    html = pintar(resumen, cfg, perms=permisos())
    assert "<b>x</b>.iso" not in html


def test_v_o26_y_v_o27_bloquean_el_boton_crear(resumen):
    from proxlaunch.nucleo.validacion import Problema, Severidad

    for codigo in ("V-O26", "V-O27"):
        pintar(
            resumen,
            cfg_iso(),
            perms=permisos(),
            problemas=[Problema("origen", codigo, Severidad.ERROR, {"storage": "x"})],
        )
        assert not resumen.boton_crear.isEnabled()
        assert resumen.texto_pendientes


def test_un_campo_sin_mapear_no_muestra_el_identificador_crudo_en_pendientes(resumen):
    from proxlaunch.nucleo.validacion import Problema, Severidad

    pintar(
        resumen,
        cfg_iso(),
        perms=permisos(),
        problemas=[Problema("campo_inexistente_x", "V-O05", Severidad.ERROR, {})],
    )
    assert "campo_inexistente_x" not in resumen.texto_pendientes


# --- Lote de clones: peticiones simuladas (RF-O29, CA-O29.3) -


def _plan_de(cfg, n=2) -> Plan:
    defn = DefinicionLote(
        plantilla=cfg,
        cantidad=n,
        patron=PatronNombres(prefijo="web"),
        destino=Destino(ModoDestino.UN_NODO, ("pve",)),
        vmid_inicial=200,
    )
    elementos = tuple(ElementoPlan(i, f"web-{i + 1:02d}", 200 + i, "pve", cfg) for i in range(n))
    return Plan(
        id_lote="abcd1234",
        definicion=defn,
        elementos=elementos,
        vmids_saltados=(),
        reparto={"pve": (n, MotivoReparto.ELEGIDO_POR_USUARIO.value)},
        uso={},
        problemas=(),
        capacidad_maxima=None,
        generado_en=0.0,
        version_validacion=(9, 2),
    )


def _sim_clon(n=2) -> ResultadoSimulacion:
    cfg = cfg_clon(efectivo=ModoClon.ENLAZADO, ajustes=AjustesClon(cores=4, disco_gib=40))
    plan = _plan_de(cfg, n)
    detalle = {
        e.vmid: (
            PeticionSimulada(
                AccionPeticion.CLONAR, "pve", {"newid": str(e.vmid), "name": e.nombre}
            ),
            PeticionSimulada(AccionPeticion.CONFIGURAR, "pve", {"cores": "4"}),
            PeticionSimulada(AccionPeticion.AMPLIAR, "pve", {"disk": "scsi0", "size": "40G"}),
        )
        for e in plan.elementos
    }
    return ResultadoSimulacion(
        plan=plan,
        peticiones={v: dict(p[0].parametros) for v, p in detalle.items()},
        version_detectada=(9, 2),
        version_forzada=None,
        peticiones_detalle=detalle,
    )


def test_ca_o29_3_la_simulacion_de_un_clon_muestra_clone_config_y_resize_en_orden():
    texto = texto_peticiones(_sim_clon(1))
    lineas = [ln for ln in texto.splitlines() if ln.startswith(("POST", "PUT"))]
    assert lineas == [
        "POST /nodes/pve/qemu/9000/clone",
        "PUT /nodes/pve/qemu/200/config",
        "PUT /nodes/pve/qemu/200/resize",
    ]
    assert "newid = 200" in texto and "size = 40G" in texto


def test_ca_o29_3_cada_maquina_del_lote_tiene_su_bloque_de_peticiones():
    texto = texto_peticiones(_sim_clon(3))
    assert texto.count("/clone") == 3 and texto.count("/resize") == 3
    assert "# web-01 (VMID 200)" in texto and "# web-03 (VMID 202)" in texto


def test_ca_o29_3_una_simulacion_sin_origen_sigue_mostrando_un_solo_post():
    plan = _plan_de(cfg_base(), 1)
    sim = ResultadoSimulacion(
        plan=plan, peticiones={200: {"vmid": "200"}}, version_detectada=(9, 2), version_forzada=None
    )
    texto = texto_peticiones(sim)
    assert "POST /nodes/pve/qemu\n" in texto + "\n" and "clone" not in texto


def test_la_simulacion_no_contiene_secretos_ni_cabeceras():
    texto = texto_peticiones(_sim_clon(1))
    for prohibido in ("Authorization", "PVEAPIToken", "CSRFPreventionToken", "ticket"):
        assert prohibido not in texto


def test_ca_o29_el_resumen_del_lote_dice_de_que_plantilla_y_como_se_copia():
    texto = texto_origen_del_plan(_plan_de(cfg_clon(efectivo=ModoClon.ENLAZADO), 3))
    assert "Origen:" in texto
    assert "comparten el disco base con la plantilla" in texto


def test_ca_o29_un_lote_de_discos_vacios_no_agrega_texto_de_origen():
    assert texto_origen_del_plan(_plan_de(cfg_base(), 3)) == ""


def test_ca_o29_el_lote_de_isos_dice_el_iso(qtbot):
    texto = texto_origen_del_plan(_plan_de(cfg_iso(), 2))
    assert "alpine.iso" in texto


def test_el_panel_de_resumen_del_lote_muestra_el_origen_y_las_peticiones(qtbot):
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    sim = _sim_clon(2)
    r.mostrar_plan(sim.plan, simulacion=sim)
    assert r.plan is sim.plan
    assert r._origen.isVisible() and "Origen" in r._origen.text()
    texto = r.detalles_peticiones.texto
    assert texto.count("/clone") == 2 and "/config" in texto and "/resize" in texto
    assert "SIMULACIÓN" in r._simulacion_etiqueta.text()
