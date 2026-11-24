"""Regresión de los hallazgos corregidos de la revisión F6 de la fase D (0.9.0), parte de la
interfaz: QA-2 (quitar un disco con varias imágenes), QA-8 (resultados tardíos de una sesión
anterior), QA-10 (comprobaciones del clúster fusionadas), Seg-B1 (tooltips con marcado) y el
texto de V-D33b (Seg-B6). Sin red ni modales reales; el resto está en
``tests/nucleo/test_fase_d_regresion_f6.py``.
"""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument

from nucleo.apoyo_fase_d_libvirt import (
    disco_xml,
    dominio_desde_texto,
    inventario_d,
    proponer_de,
    xml_minimo,
)
from proxlaunch.interfaz.controlador_origen import _fusionar_hardware
from proxlaunch.interfaz.dialogos.importar_libvirt import DialogoImportarLibvirt
from proxlaunch.interfaz.textos_d import texto_problema_d
from proxlaunch.interfaz.vistas.seccion_hardware_cluster import SeccionHardwareCluster
from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen
from proxlaunch.nucleo.arquitectura.modelos import (
    Arquitectura,
    ArquitecturaNodo,
    FuenteArquitectura,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    ComprobacionNodo,
    EntradaMapeo,
    InfoHardwareCluster,
    Mapeo,
    TipoMapeo,
)
from proxlaunch.nucleo.hardware_cluster.validacion import validar_hardware_servidor
from proxlaunch.nucleo.libvirt.validacion import validar_importacion_d
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen
from proxlaunch.nucleo.modelos.vm import Disco
from proxlaunch.nucleo.validacion import Problema, Severidad

from . import test_ventana_principal as _base
from .apoyo import sesion_falsa
from .apoyo_mvp4 import cfg_import
from .test_ventana_principal import conectar

entorno = _base.entorno  # fixture base de la ventana


# --- QA-2: quitar un disco cuando cada disco lleva su imagen -----------------------------------


def _ref(nombre: str) -> RefVolumen:
    return RefVolumen(nombre, f"local:import/{nombre}")


A, B, C = _ref("a.qcow2"), _ref("b.qcow2"), _ref("c.qcow2")


def _selector(qtbot, *, otra1: ImagenDisco, otra2: ImagenDisco | None = None):
    """Selector cargado con tres discos: A (sistema) y las imágenes de los discos 1 y 2."""
    sel = SelectorOrigen()
    qtbot.addWidget(sel)
    otras = (otra1, otra2 if otra2 is not None else ImagenDisco(2, C))
    cfg = dataclasses.replace(
        cfg_import(),
        discos=[Disco("local-lvm", 8), Disco("local-lvm", 16), Disco("local-lvm", 32)],
        detalle_origen=DetalleImportacion(imagen=A, otras=otras),
    )
    sel.aplicar(cfg)
    sel.establecer_discos(["scsi0", "scsi1", "scsi2"])
    return sel, cfg


def _tras_quitar(sel: SelectorOrigen, cfg, posicion: int):
    """Quita el disco ``posicion`` (también del formulario) y devuelve el detalle resultante."""
    sel.al_quitar_disco(posicion)
    discos = [d for i, d in enumerate(cfg.discos) if i != posicion]
    sel.establecer_discos([f"scsi{i}" for i in range(len(discos))])
    nueva = sel.completar(dataclasses.replace(cfg, discos=discos))
    return nueva, nueva.detalle_origen


def _volids(det: DetalleImportacion) -> list[str | None]:
    return [det.imagen.volid, *(o.imagen.volid if o.imagen else None for o in det.otras)]


def test_qa2_quitar_el_disco_0_cada_restante_conserva_su_imagen(qtbot):
    sel, cfg = _selector(qtbot, otra1=ImagenDisco(1, B))
    _, det = _tras_quitar(sel, cfg, 0)
    assert _volids(det) == [B.volid, C.volid]
    assert [o.indice for o in det.otras] == [1]


def test_qa2_quitar_el_disco_1_cada_restante_conserva_su_imagen(qtbot):
    sel, cfg = _selector(qtbot, otra1=ImagenDisco(1, B))
    _, det = _tras_quitar(sel, cfg, 1)
    assert _volids(det) == [A.volid, C.volid]
    assert [o.indice for o in det.otras] == [1]


def test_qa2_quitar_el_disco_2_cada_restante_conserva_su_imagen(qtbot):
    sel, cfg = _selector(qtbot, otra1=ImagenDisco(1, B))
    _, det = _tras_quitar(sel, cfg, 2)
    assert _volids(det) == [A.volid, B.volid]
    assert [o.indice for o in det.otras] == [1]


def test_qa2_quitar_el_disco_0_con_el_1_en_crear_vacio_deja_el_0_pendiente_v_d27(qtbot):
    sel, cfg = _selector(qtbot, otra1=ImagenDisco(1, None, crear_vacio=True))
    nueva, det = _tras_quitar(sel, cfg, 0)
    assert not det.imagen.nombre and not det.imagen.volid  # el disco 0 queda sin imagen
    assert [(o.indice, o.imagen.volid) for o in det.otras] == [(1, C.volid)]
    v27 = [p for p in validar_importacion_d(nueva) if p.codigo == "V-D27"]
    assert [(p.campo, p.params["disco"]) for p in v27] == [("detalle_origen.imagen", "0")]


def test_qa2_quitar_el_disco_1_en_crear_vacio_no_arrastra_su_marca_al_siguiente(qtbot):
    sel, cfg = _selector(qtbot, otra1=ImagenDisco(1, None, crear_vacio=True))
    _, det = _tras_quitar(sel, cfg, 1)
    assert det.imagen.volid == A.volid
    assert [(o.indice, o.imagen.volid, o.crear_vacio) for o in det.otras] == [(1, C.volid, False)]


def test_qa2_quitar_un_disco_de_un_selector_sin_varias_imagenes_no_toca_la_imagen_unica(qtbot):
    sel = SelectorOrigen()
    qtbot.addWidget(sel)
    cfg = dataclasses.replace(
        cfg_import(), discos=[Disco("local-lvm", 8)], detalle_origen=DetalleImportacion(imagen=A)
    )
    sel.aplicar(cfg)
    sel.al_quitar_disco(0)
    assert sel.completar(cfg).detalle_origen.imagen == A


# --- QA-8: resultados tardíos de una sesión anterior --------------------------------------------


def _arq(nodo_arch: Arquitectura) -> ArquitecturaNodo:
    return ArquitecturaNodo(nodo_arch, FuenteArquitectura.KERNEL)


def test_qa8_el_resultado_tardio_de_recargar_un_nodo_de_otra_sesion_se_descarta(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    conectar(qtbot, entorno, sesion_falsa())
    inv = v._inv
    llamadas: list[tuple] = []
    monkeypatch.setattr(v.formulario, "actualizar_recursos_nodo", lambda *a: llamadas.append(a))
    antes = (dict(inv.arquitecturas), dict(inv.storages_todos))
    vieja = sesion_falsa()  # una sesión anterior (otra conexión) cuyo trabajo termina tarde
    v._tras_recargar_nodo(vieja, ("pve1", [], [], ["intruso"], None, _arq(Arquitectura.AARCH64)))
    assert llamadas == []
    assert (dict(inv.arquitecturas), dict(inv.storages_todos)) == antes


def test_qa8_el_resultado_de_recargar_un_nodo_de_la_sesion_actual_si_se_aplica(
    qtbot, entorno, monkeypatch
):
    v = entorno.ventana
    conectar(qtbot, entorno, sesion_falsa())
    llamadas: list[tuple] = []
    monkeypatch.setattr(v.formulario, "actualizar_recursos_nodo", lambda *a: llamadas.append(a))
    v._tras_recargar_nodo(v._sesion, ("pve1", [], [], [], None, _arq(Arquitectura.AARCH64)))
    assert len(llamadas) == 1
    assert v._inv.arquitecturas["pve1"].arquitectura == Arquitectura.AARCH64


def test_qa8_el_resultado_tardio_de_un_reintento_de_nodos_de_otra_sesion_se_descarta(
    qtbot, entorno
):
    v = entorno.ventana
    conectar(qtbot, entorno, sesion_falsa())
    inv = v._inv
    inv.errores_por_nodo["pve2"] = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    antes = (dict(inv.storages), dict(inv.errores_por_nodo), dict(inv.arquitecturas))
    v._tras_reintento(sesion_falsa(), ({"pve2": ((), (), ())}, {}))
    assert (dict(inv.storages), dict(inv.errores_por_nodo), dict(inv.arquitecturas)) == antes
    assert "pve2" in inv.errores_por_nodo  # sigue marcado como fallido


def test_qa8_el_resultado_de_un_reintento_de_la_sesion_actual_recupera_el_nodo(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno, sesion_falsa())
    inv = v._inv
    inv.errores_por_nodo["pve2"] = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    v._tras_reintento(v._sesion, ({"pve2": ((), (), ())}, {}))
    assert "pve2" not in inv.errores_por_nodo


# --- QA-10 y QA-6 (parte de interfaz): fusión de las lecturas de hardware -----------------------


def _comp(tipo: TipoMapeo, *errores: str) -> ComprobacionNodo:
    return ComprobacionNodo("g", "pve1", errores, tipo)


def test_qa10_un_par_que_fallo_y_luego_se_comprobo_bien_no_queda_como_fallido():
    previo = InfoHardwareCluster(errores_comprobacion=(("pci", "g", "pve1"),))
    nuevo = InfoHardwareCluster(comprobaciones=(_comp(TipoMapeo.PCI),))
    fusion = _fusionar_hardware(previo, nuevo)
    assert fusion.errores_comprobacion == ()
    assert [(c.tipo, c.mapeo, c.nodo) for c in fusion.comprobaciones] == [
        (TipoMapeo.PCI, "g", "pve1")
    ]


def test_qa10_sin_v_d53_sin_comprobar_tras_fusionar_un_fallo_y_su_exito_posterior():
    from nucleo.apoyo_fase_d import cfg_arm, hw, pci

    previo = InfoHardwareCluster(
        mapeos=(Mapeo(TipoMapeo.PCI, "g", "", (EntradaMapeo("pve1"),)),),
        errores_comprobacion=(("pci", "g", "pve1"),),
    )
    nuevo = InfoHardwareCluster(comprobaciones=(_comp(TipoMapeo.PCI),))
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("g")))
    sin_fusion = validar_hardware_servidor({"pve1": [cfg]}, previo, None)
    assert any(p.codigo == "V-D53.sin_comprobar" for p in sin_fusion)  # el aviso existía
    r = validar_hardware_servidor({"pve1": [cfg]}, _fusionar_hardware(previo, nuevo), None)
    assert not any(p.codigo.startswith("V-D53") for p in r)


def test_qa10_un_fallo_que_sigue_sin_resolverse_se_conserva():
    previo = InfoHardwareCluster(errores_comprobacion=(("pci", "g", "pve1"),))
    nuevo = InfoHardwareCluster(errores_comprobacion=(("usb", "g", "pve1"),))
    fusion = _fusionar_hardware(previo, nuevo)
    assert set(fusion.errores_comprobacion) == {("pci", "g", "pve1"), ("usb", "g", "pve1")}


def test_qa10_un_exito_en_usb_no_borra_el_fallo_pci_del_mismo_id_y_nodo():
    previo = InfoHardwareCluster(errores_comprobacion=(("pci", "g", "pve1"),))
    nuevo = InfoHardwareCluster(comprobaciones=(_comp(TipoMapeo.USB),))
    assert _fusionar_hardware(previo, nuevo).errores_comprobacion == (("pci", "g", "pve1"),)


def test_qa6_la_fusion_conserva_las_comprobaciones_pci_y_usb_del_mismo_id_y_nodo():
    previo = InfoHardwareCluster(comprobaciones=(_comp(TipoMapeo.PCI, "falla el PCI"),))
    nuevo = InfoHardwareCluster(comprobaciones=(_comp(TipoMapeo.USB),))
    fusion = _fusionar_hardware(previo, nuevo)
    assert {(c.tipo, c.errores) for c in fusion.comprobaciones} == {
        (TipoMapeo.PCI, ("falla el PCI",)),
        (TipoMapeo.USB, ()),
    }


# --- Seg-B1: marcado en los tooltips -------------------------------------------------------------

HTML = "<b>x</b>"


def _renderiza_en_negrita(tooltip: str) -> bool:
    """¿Qt dibujaría algún fragmento del tooltip en negrita? (lo que haría un ``<b>`` activo)."""
    doc = QTextDocument()
    doc.setHtml(tooltip)
    return "font-weight:700" in doc.toHtml() or "font-weight:bold" in doc.toHtml()


def test_seg_b1_un_texto_del_xml_con_marcado_no_se_interpreta_en_los_tooltips_del_dialogo(qtbot):
    # El nombre del dispositivo de un disco (atributo del XML) llega al texto de V-D29.
    xml = xml_minimo(
        disco_xml()
        + "<disk type='dir' device='disk'><source dir='/srv/x'/>"
        + "<target dev='&lt;b&gt;x&lt;/b&gt;' bus='virtio'/></disk>"
    )
    inv = inventario_d({"pve1": Arquitectura.X86_64})
    d = DialogoImportarLibvirt(
        None, inv=inv, nodos=("pve1",), nodo="pve1", cantidad=1, formulario_modificado=False
    )
    qtbot.addWidget(d)
    d.show()
    d.establecer_propuesta(proponer_de(dominio_desde_texto(xml), inv=inv))
    tooltips = [d.modelo.item(r, c).toolTip() for r in range(d.modelo.rowCount()) for c in range(4)]
    con_problema = [t for t in tooltips if t]
    assert con_problema, "la fila del disco no migrable debe llevar tooltip"
    for t in con_problema:
        assert "<b>" not in t and "</b>" not in t, t
        assert not _renderiza_en_negrita(t), t


def test_seg_b1_un_id_de_mapeo_con_marcado_se_muestra_escapado_en_el_tooltip_de_la_seccion(qtbot):
    sucio = Mapeo(TipoMapeo.PCI, HTML, "", (EntradaMapeo("pve1"),))
    permisos = PermisosEfectivos(rutas={"/": {"VM.Audit": 1}})  # sin Mapping.Use: deshabilitado
    s = SeccionHardwareCluster()
    qtbot.addWidget(s)
    s.show()
    s.chk_activar.setChecked(True)
    s.establecer_info(InfoHardwareCluster(mapeos=(sucio,)), permisos)
    combo = s._filas[0].combo
    indice = combo.findData(HTML)
    assert indice > 0
    tip = combo.itemData(indice, Qt.ItemDataRole.ToolTipRole)
    assert tip and "<b>" not in tip and not _renderiza_en_negrita(tip)
    assert "&lt;b&gt;x&lt;/b&gt;" in tip  # el texto sigue ahí, pero como texto
    assert HTML in combo.itemText(indice)  # el combo no interpreta HTML: se ve literal


def test_seg_b1_aunque_un_parametro_llegue_con_marcado_el_tooltip_del_dialogo_lo_escapa(qtbot):
    """Defensa en profundidad: si el saneado del XML fallara, el tooltip no interpretaría HTML."""
    inv = inventario_d({"pve1": Arquitectura.X86_64})
    xml = xml_minimo(
        disco_xml() + "<disk type='dir' device='disk'><source dir='/s'/>"
        "<target dev='vdb' bus='virtio'/></disk>"
    )
    propuesta = proponer_de(dominio_desde_texto(xml), inv=inv)
    filas = tuple(
        dataclasses.replace(
            f, problema=dataclasses.replace(f.problema, params={**f.problema.params, "disco": HTML})
        )
        if f.problema is not None and f.problema.codigo == "V-D29"
        else f
        for f in propuesta.filas
    )
    d = DialogoImportarLibvirt(
        None, inv=inv, nodos=("pve1",), nodo="pve1", cantidad=1, formulario_modificado=False
    )
    qtbot.addWidget(d)
    d.show()
    d.establecer_propuesta(dataclasses.replace(propuesta, filas=filas))
    tips = [d.modelo.item(r, c).toolTip() for r in range(d.modelo.rowCount()) for c in range(4)]
    con_disco = [t for t in tips if "&lt;b&gt;x&lt;/b&gt;" in t]
    assert con_disco, tips
    for t in tips:
        assert "<b>" not in t and not _renderiza_en_negrita(t), t


# --- Seg-B6: texto del aviso V-D33b -------------------------------------------------------------


def test_seg_b6_el_texto_de_v_d33b_dice_la_mac_y_la_maquina_sin_marcadores():
    p = Problema(
        "redes[0].mac_conservada", "V-D33b", Severidad.AVISO,
        {"mac": "aa:bb:cc:dd:ee:ff", "vmid": "9000"},
    )  # fmt: skip
    texto = texto_problema_d(p)
    assert texto and "aa:bb:cc:dd:ee:ff" in texto and "9000" in texto
    assert "{" not in texto and "}" not in texto
    for neutro in ("un dato", "ese servidor", "ese elemento"):
        assert neutro not in texto
    assert "V-D33b" not in texto  # sin código crudo


def test_seg_b6_el_texto_de_v_d33b_sale_del_catalogo_de_textos_d_y_no_del_generico():
    from proxlaunch.interfaz.textos import texto_problema

    p = Problema("c", "V-D33b", Severidad.AVISO, {"mac": "aa:bb:cc:dd:ee:ff", "vmid": "7"})
    assert texto_problema(p) == texto_problema_d(p) and "7" in texto_problema(p)
