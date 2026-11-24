"""D1.1, D1.6 y D1.14: asistente «Rellenar desde un XML de libvirt» (RF-D1.1, RF-D1.6, RF-D1.14).

Derivadas de docs/requisitos/fase-d.md: CA-D1.1.1 a CA-D1.1.3, CA-D1.2.5/6 (parte de interfaz),
CA-D1.6.1 a CA-D1.6.6, CA-D1.10.3/6 (casilla de la MAC), CA-D1.13.4, CA-D1.14.1/2 y RNF-D6 (la
lectura del XML no ocurre en el hilo de la interfaz). Dos niveles: el diálogo aislado con un
arnés que hace de ventana (lee y propone con el núcleo real) y la ventana principal con el
servidor y el lanzador de trabajos de las pruebas existentes. Sin red ni modales reales.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, Qt, QThread
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton

from nucleo.apoyo_fase_d_libvirt import (
    bytes_xml,
    cfg_formulario,
    disco_xml,
    inventario_d,
    xml_minimo,
)
from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.catalogo import FuenteCatalogo
from proxlaunch.interfaz.dialogos.importar_libvirt import DialogoImportarLibvirt
from proxlaunch.interfaz.textos_d import texto_comandos_obtener_xml
from proxlaunch.interfaz.trabajadores import leer_xml_libvirt
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.libvirt.correspondencias import proponer
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import DetalleImportacion
from proxlaunch.nucleo.modelos.vm import OrigenSO

from . import test_ventana_principal as _base
from .apoyo import sesion_falsa
from .apoyo_mvp4 import caps_origen, cfg_import, volumen
from .test_ventana_principal import conectar, esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

MIXTO = {"pve1": Arquitectura.X86_64, "pve2": Arquitectura.AARCH64}
SECRETO = "secreto-SUPER-9876"


# --- Arnés del diálogo aislado ---------------------------------------------------------------


class Arnes:
    """Hace de ventana: lee con el trabajador real y calcula la propuesta con el núcleo real."""

    def __init__(self, dialogo: DialogoImportarLibvirt, inv, base=None):
        self.dialogo = dialogo
        self.inv = inv
        self.base = base if base is not None else cfg_formulario()
        self.rutas: list[Path] = []
        self.pedidos: list[tuple[bool, str]] = []
        dialogo.pide_lectura.connect(self.rutas.append)
        dialogo.pide_propuesta.connect(self._proponer)

    def _proponer(self, dominio, conservar_mac, nodo):
        self.pedidos.append((conservar_mac, nodo))
        self.dialogo.establecer_propuesta(
            proponer(dominio, self.base, self.inv, nodo or None, conservar_mac=conservar_mac)
        )

    def abrir(self, ruta: Path):
        """El usuario elige ``ruta``: se lee (como el trabajador) y se entrega el resultado."""
        self.dialogo.leer(ruta)
        try:
            dominio, error = leer_xml_libvirt(ruta), None
        except ErrorProxLaunch as e:
            dominio, error = None, e
        self.dialogo.establecer_resultado(dominio, error)


def _archivo(tmp_path, nombre: str, datos: bytes | None = None) -> Path:
    ruta = tmp_path / nombre
    ruta.write_bytes(datos if datos is not None else bytes_xml(nombre))
    return ruta


def _dialogo(qtbot, *, inv=None, nodos=("pve1", "pve2"), nodo="pve1", cantidad=1, modificado=False):
    inv = inv if inv is not None else inventario_d(MIXTO)
    d = DialogoImportarLibvirt(
        None, inv=inv, nodos=nodos, nodo=nodo, cantidad=cantidad, formulario_modificado=modificado
    )
    qtbot.addWidget(d)
    d.show()
    return d, Arnes(d, inv)


def _celdas(d: DialogoImportarLibvirt) -> list[list[str]]:
    m = d.modelo
    return [[m.item(f, c).text() for c in range(m.columnCount())] for f in range(m.rowCount())]


def _todo_el_texto(d: DialogoImportarLibvirt) -> str:
    tabla = " ".join(" ".join(fila) for fila in _celdas(d))
    etiquetas = (
        d.error_lectura,
        d.motivos_bloqueo,
        d.aviso_mac,
        d.estado_lectura,
        d.etiqueta_archivo,
    )
    partes = [tabla, d.detalle.toPlainText(), d.texto_ayuda_xml.toPlainText()]
    partes.extend(e.text() for e in etiquetas)
    return "\n".join(partes)


# --- CA-D1.6.1: vista previa con una fila por concepto y el estado en texto ----------------------


def test_ca_d1_6_1_un_xml_valido_muestra_una_fila_por_concepto_con_el_estado_en_palabras(
    qtbot, tmp_path
):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    assert d.propuesta is not None
    filas = _celdas(d)
    assert len(filas) == len(d.propuesta.filas) > 8
    conceptos = {f[0] for f in filas}
    assert {"Nombre", "Memoria", "Sockets y núcleos", "Tipo de CPU", "Disco 1"} <= conceptos
    palabras = {"Migrado", "Aproximado", "No se migra", "Bloquea"}
    for fila in filas:
        assert any(p in fila[3] for p in palabras), fila
    assert [d.modelo.horizontalHeaderItem(i).text() for i in range(4)] == [
        "Concepto", "En libvirt", "En Proxmox", "Estado"
    ]  # fmt: skip


def test_ca_d1_6_1_cada_estado_lleva_un_simbolo_ademas_del_color(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "windows11_uefi_tpm.xml"))
    simbolos = {"✔": "Migrado", "⚠": "Aproximado", "–": "No se migra", "✖": "Bloquea"}
    for fila in _celdas(d):
        simbolo = fila[3].split(" ")[0]
        assert simbolo in simbolos and simbolos[simbolo] in fila[3]


def test_ca_d1_6_1_las_celdas_vacias_se_muestran_con_raya_y_no_son_editables(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "windows11_uefi_tpm.xml"))
    assert any(f[2] == "—" for f in _celdas(d))
    for r in range(d.modelo.rowCount()):
        assert all(not d.modelo.item(r, c).isEditable() for c in range(4))


def test_ca_d1_6_1_los_avisos_se_explican_en_el_detalle(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "windows11_uefi_tpm.xml"))
    detalle = d.detalle.toPlainText()
    assert "BitLocker" in detalle and "NVRAM" in detalle and "NAT" in detalle


def test_ca_d1_6_1_antes_de_elegir_archivo_no_hay_vista_previa_ni_rellenar(qtbot):
    d, _ = _dialogo(qtbot)
    assert d.modelo.rowCount() == 0 and d.propuesta is None
    assert not d.boton_rellenar.isEnabled()
    assert "Todavía no elegiste" in d.etiqueta_archivo.text()


# --- CA-D1.6.2: bloqueos --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("archivo", "motivo"),
    [("xen.xml", "KVM"), ("sin_discos.xml", "disco")],
)
def test_ca_d1_6_2_una_fila_bloquea_deshabilita_rellenar_y_el_motivo_esta_a_la_vista(
    qtbot, tmp_path, archivo, motivo
):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, archivo))
    assert any("Bloquea" in f[3] for f in _celdas(d))
    assert not d.boton_rellenar.isEnabled()
    assert not d.motivos_bloqueo.isHidden()  # visible sin pasar el ratón
    assert motivo in d.motivos_bloqueo.text()
    assert "no está disponible" in d.motivos_bloqueo.text()


def test_ca_d1_6_2_pulsar_rellenar_deshabilitado_no_acepta(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "xen.xml"))
    qtbot.mouseClick(d.boton_rellenar, Qt.MouseButton.LeftButton)
    d._rellenar()  # aunque algo lo llame directamente
    assert d.propuesta_aceptada is None and d.isVisible()


def test_ca_d1_11_2_la_red_sin_equivalente_no_bloquea_rellenar(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "windows11_uefi_tpm.xml"))  # red «default» de libvirt (NAT)
    assert any("NAT" in f for f in d.detalle.toPlainText().splitlines())
    assert d.boton_rellenar.isEnabled()
    assert d.motivos_bloqueo.isHidden()


def test_ca_d1_6_2_los_motivos_de_varios_bloqueos_aparecen_todos(qtbot, tmp_path):
    xml = xml_minimo("", tipo="xen", arch="ppc64le").encode()  # tipo, arquitectura y sin discos
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "malo.xml", xml))
    texto = d.motivos_bloqueo.text()
    assert "KVM" in texto and "ppc64le" in texto


def test_ca_d1_6_2_el_bloqueo_de_arquitectura_nombra_las_dos_arquitecturas(qtbot, tmp_path):
    d, a = _dialogo(qtbot, nodos=("pve1",), inv=inventario_d({"pve1": Arquitectura.X86_64}))
    a.abrir(_archivo(tmp_path, "aarch64.xml"))
    assert "aarch64" in d.motivos_bloqueo.text() and "x86_64" in d.motivos_bloqueo.text()
    assert not d.boton_rellenar.isEnabled()


# --- CA-D1.6.3 y CA-D1.6.4: cancelar y reemplazar -------------------------------------------------


def test_ca_d1_6_3_cancelar_no_deja_nada_que_aplicar(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    d.boton_cancelar.click()
    assert d.propuesta_aceptada is None and not d.isVisible()
    assert d.result() == d.DialogCode.Rejected


def test_ca_d1_6_3_cerrar_el_dialogo_con_escape_tampoco_deja_nada(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    d.reject()
    assert d.propuesta_aceptada is None


def test_rellenar_deja_la_propuesta_para_quien_abrio_el_dialogo(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    d.boton_rellenar.click()
    assert d.propuesta_aceptada is d.propuesta and d.result() == d.DialogCode.Accepted


def test_ca_d1_6_4_con_el_formulario_modificado_rellenar_pide_confirmar_el_reemplazo(
    qtbot, tmp_path
):
    d, a = _dialogo(qtbot, modificado=True)
    preguntas: list[int] = []
    d.confirmar_reemplazo = lambda: preguntas.append(1) or False
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    d.boton_rellenar.click()
    assert preguntas == [1]
    assert d.propuesta_aceptada is None and d.isVisible()  # rechazado: nada cambia


def test_ca_d1_6_4_si_se_confirma_el_reemplazo_se_acepta(qtbot, tmp_path):
    d, a = _dialogo(qtbot, modificado=True)
    d.confirmar_reemplazo = lambda: True
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    d.boton_rellenar.click()
    assert d.propuesta_aceptada is not None


def test_ca_d1_6_4_con_el_formulario_intacto_no_se_pregunta_nada(qtbot, tmp_path):
    d, a = _dialogo(qtbot, modificado=False)
    d.confirmar_reemplazo = lambda: pytest.fail("no debía preguntar")
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    d.boton_rellenar.click()
    assert d.propuesta_aceptada is not None


# --- CA-D1.6.6: recalcular al cambiar servidor o MAC ----------------------------------------------


def test_ca_d1_6_6_cambiar_el_servidor_de_destino_recalcula_las_filas_de_arquitectura(
    qtbot, tmp_path
):
    d, a = _dialogo(qtbot, nodo="pve1")  # pve1 = x86, pve2 = aarch64
    a.abrir(_archivo(tmp_path, "aarch64.xml"))
    assert a.pedidos[-1][1] == "pve1" and not d.boton_rellenar.isEnabled()
    d.combo_nodo.setCurrentIndex(d.combo_nodo.findData("pve2"))
    assert a.pedidos[-1][1] == "pve2" and d.boton_rellenar.isEnabled()
    assert d.motivos_bloqueo.isHidden()
    d.combo_nodo.setCurrentIndex(d.combo_nodo.findData("pve1"))
    assert not d.boton_rellenar.isEnabled()


def test_ca_d1_6_6_cambiar_de_servidor_recalcula_las_redes_del_bridge(qtbot, tmp_path):
    inv = inventario_d(MIXTO)
    inv.bridges = {"pve1": inv.bridges["pve1"][:1], "pve2": inv.bridges["pve2"]}  # pve1 sin vmbr1
    xml = xml_minimo(
        disco_xml() + "<interface type='bridge'><source bridge='vmbr1'/></interface>"
    ).encode()
    d, a = _dialogo(qtbot, inv=inv)
    a.abrir(_archivo(tmp_path, "red.xml", xml))
    assert a.pedidos[-1][1] == "pve1" and d.propuesta.cfg.redes[0].bridge == ""
    d.combo_nodo.setCurrentIndex(d.combo_nodo.findData("pve2"))
    assert d.propuesta.cfg.redes[0].bridge == "vmbr1"


def test_ca_d1_6_6_el_bus_en_arm_se_recalcula_al_cambiar_de_servidor(qtbot, tmp_path):
    xml = xml_minimo(disco_xml(bus="sata", dev="sda"), arch="aarch64").encode()
    d, a = _dialogo(qtbot, nodo="pve2")
    a.abrir(_archivo(tmp_path, "arm.xml", xml))
    assert any("conexión" in f[0] for f in _celdas(d))  # V-D08: SATA pasó a SCSI


def test_ca_d1_6_6_el_combo_nombra_la_arquitectura_de_cada_servidor(qtbot):
    d, _ = _dialogo(qtbot)
    textos = [d.combo_nodo.itemText(i) for i in range(d.combo_nodo.count())]
    assert "pve1" in textos  # x86: sin marca
    assert any("pve2" in t and "ARM64" in t and "experimental" in t for t in textos)


def test_el_servidor_inicial_es_el_del_formulario_o_el_primero(qtbot):
    d, _ = _dialogo(qtbot, nodo="pve2")
    assert d.nodo_elegido == "pve2"
    d2, _ = _dialogo(qtbot, nodo="no-existe")
    assert d2.nodo_elegido == "pve1"


def test_sin_servidores_el_combo_no_se_muestra_y_no_hay_destino(qtbot):
    d, _ = _dialogo(qtbot, nodos=(), nodo=None)
    assert d.combo_nodo.isHidden() and d.nodo_elegido == ""


# --- MAC en el diálogo (CA-D1.10.2, 10.3) ---------------------------------------------------------


def test_la_casilla_de_la_mac_empieza_desmarcada(qtbot):
    d, _ = _dialogo(qtbot)
    assert not d.casilla_mac.isChecked() and d.casilla_mac.isEnabled() and not d.conservar_mac


def test_ca_d1_10_2_marcar_la_casilla_pide_la_propuesta_con_mac_y_muestra_v_d32(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    assert a.pedidos[-1][0] is False
    assert all(r.mac_conservada is None for r in d.propuesta.cfg.redes)
    d.casilla_mac.setChecked(True)
    assert a.pedidos[-1][0] is True
    assert d.propuesta.cfg.redes[0].mac_conservada == "52:54:00:ab:cd:ef"
    assert "Apaga la máquina original" in d.aviso_mac.text() and not d.aviso_mac.isHidden()
    d.casilla_mac.setChecked(False)
    assert d.propuesta.cfg.redes[0].mac_conservada is None and d.aviso_mac.isHidden()


@pytest.mark.parametrize("cantidad", [2, 5])
def test_ca_d1_10_3_con_varias_copias_la_casilla_esta_deshabilitada_y_dice_por_que(
    qtbot, tmp_path, cantidad
):
    d, a = _dialogo(qtbot, cantidad=cantidad)
    assert not d.casilla_mac.isEnabled()
    assert str(cantidad) in d.aviso_mac.text() and "copias" in d.aviso_mac.text()
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    assert a.pedidos[-1][0] is False and not d.conservar_mac


def test_con_una_sola_copia_no_hay_aviso_de_copias(qtbot):
    d, _ = _dialogo(qtbot, cantidad=1)
    assert d.aviso_mac.isHidden()


# --- Errores de lectura (V-D20..V-D23) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("archivo", "texto"),
    [
        ("doctype.xml", "DOCTYPE"),
        ("billion_laughs.xml", "DOCTYPE"),
        ("entidad_externa.xml", "ENTITY"),
        ("mal_formado.xml", "mal formado"),
        ("utf16_sin_bom.xml", "codificación"),
        ("latin1.xml", "codificación"),
    ],
)
def test_los_xml_malos_muestran_el_error_sin_vista_previa(qtbot, tmp_path, archivo, texto):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, archivo))
    assert d.propuesta is None and d.modelo.rowCount() == 0
    assert not d.boton_rellenar.isEnabled()
    assert not d.error_lectura.isHidden() and texto in d.error_lectura.text()
    assert d.boton_elegir.isEnabled()  # puede elegir otro


def test_ca_d1_2_1_un_xml_de_mas_de_4_mib_dice_que_es_demasiado_grande(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "grande.xml", b"<domain>" + b" " * (4 * 1024 * 1024 + 1)))
    assert "demasiado grande" in d.error_lectura.text() and "4 MiB" in d.error_lectura.text()


def test_un_archivo_que_no_existe_muestra_un_error_y_no_lanza(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(tmp_path / "no-existe.xml")
    assert not d.error_lectura.isHidden() and d.propuesta is None


def test_el_error_de_un_archivo_se_borra_al_elegir_otro_valido(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "doctype.xml"))
    assert not d.error_lectura.isHidden()
    a.abrir(_archivo(tmp_path, "linux_bios.xml"))
    assert d.error_lectura.isHidden() and d.boton_rellenar.isEnabled()


def test_mientras_se_lee_no_se_puede_rellenar_ni_elegir_otro(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    d.leer(_archivo(tmp_path, "linux_bios.xml"))  # sin entregar el resultado: «leyendo»
    assert "Leyendo" in d.estado_lectura.text()
    assert not d.boton_elegir.isEnabled() and not d.boton_rellenar.isEnabled()
    assert d.propuesta is None


def test_la_lectura_pide_solo_la_ruta_elegida_y_el_dialogo_no_la_conserva_como_texto_largo(
    qtbot, tmp_path
):
    d, a = _dialogo(qtbot)
    ruta = _archivo(tmp_path, "linux_bios.xml")
    d.leer(ruta)
    assert a.rutas == [ruta]
    assert d.etiqueta_archivo.text() == "linux_bios.xml"  # solo el nombre, no la carpeta


# --- CA-D1.14.1: la contraseña no aparece en ningún texto -----------------------------------------


def test_ca_d1_14_1_el_passwd_no_aparece_en_la_vista_previa_y_si_el_aviso_v_d39(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "con_passwd.xml"))
    assert SECRETO not in _todo_el_texto(d)
    assert "otro-secreto" not in _todo_el_texto(d)
    assert "contraseñas" in d.detalle.toPlainText() and d.boton_rellenar.isEnabled()
    assert any(f[0] == "Contraseñas" for f in _celdas(d))


def test_ca_d1_14_1_tampoco_en_tooltips_ni_nombres_accesibles(qtbot, tmp_path):
    d, a = _dialogo(qtbot)
    a.abrir(_archivo(tmp_path, "con_passwd.xml"))
    textos = [d.modelo.item(r, c).toolTip() for r in range(d.modelo.rowCount()) for c in range(4)]
    textos += [
        w.toolTip() + w.accessibleName() + w.accessibleDescription()
        for w in d.findChildren(QPushButton)
    ]
    assert SECRETO not in " ".join(textos)


# --- CA-D1.14.2 y CA-D1.13.4: las cuatro órdenes --------------------------------------------------


def test_ca_d1_14_2_las_cuatro_ordenes_estan_en_la_ayuda_con_su_explicacion(qtbot):
    d, _ = _dialogo(qtbot)
    texto = d.texto_ayuda_xml.toPlainText()
    for orden in (
        "virsh dumpxml --inactive nombre-de-la-maquina > maquina.xml",
        "virsh domblklist nombre-de-la-maquina",
        "qemu-img info --backing-chain disco.qcow2",
        "qemu-img convert -O qcow2 entrada.qcow2 salida.qcow2",
    ):
        assert orden in texto
        resto = texto.split(orden, 1)[1].lstrip("\n ")
        assert resto and not resto.startswith(("virsh", "qemu-img"))  # le sigue su explicación


def test_ca_d1_14_2_la_orden_de_dumpxml_no_pide_security_info():
    texto = texto_comandos_obtener_xml()[0][0]
    assert "--security-info" not in texto and "--inactive" in texto


def test_ca_d1_14_2_el_enlace_como_obtener_el_xml_muestra_y_oculta_las_ordenes(qtbot):
    d, _ = _dialogo(qtbot)
    assert d.texto_ayuda_xml.isHidden()
    d.boton_como_obtener.click()
    assert not d.texto_ayuda_xml.isHidden()
    d.boton_como_obtener.click()
    assert d.texto_ayuda_xml.isHidden()


def test_ca_d1_13_4_las_ordenes_son_texto_seleccionable_y_de_solo_lectura(qtbot):
    d, _ = _dialogo(qtbot)
    d.boton_como_obtener.click()
    assert d.texto_ayuda_xml.isReadOnly()
    d.texto_ayuda_xml.selectAll()
    d.texto_ayuda_xml.copy()
    assert "virsh dumpxml" in QCoreApplication.instance().clipboard().text()


def test_ca_d1_13_4_hay_un_boton_copiar_para_las_ordenes(qtbot):
    d, _ = _dialogo(qtbot)
    assert any("Copiar" in b.text() for b in d.findChildren(QPushButton))


def test_ca_d1_13_4_el_dialogo_no_ejecuta_nada_al_copiar_ni_al_mostrar_las_ordenes(
    qtbot, monkeypatch
):
    import subprocess

    def prohibido(*a, **k):
        raise AssertionError("no debe ejecutarse nada")

    monkeypatch.setattr(subprocess, "run", prohibido)
    monkeypatch.setattr(subprocess, "Popen", prohibido)
    d, _ = _dialogo(qtbot)
    d.boton_como_obtener.click()
    d.texto_ayuda_xml.selectAll()
    d.texto_ayuda_xml.copy()


# --- CA-D1.1.1 y CA-D1.1.2: el botón en el selector de origen -------------------------------------


def test_ca_d1_1_1_y_1_2_el_boton_solo_aparece_en_importar_disco_y_se_habilita_con_conexion(qtbot):
    from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen

    s = SelectorOrigen()
    qtbot.addWidget(s)
    s.show()
    assert not s.boton_libvirt.isEnabled() and not s.boton_libvirt.isVisible()  # sin conexión
    assert "Conéctate" in s.motivos[OrigenSO.IMPORTAR_DISCO].text()  # el motivo se ve
    s.establecer_capacidades(caps_origen())
    visibles = {}
    for origen in (
        OrigenSO.DISCO_VACIO,
        OrigenSO.ISO,
        OrigenSO.IMPORTAR_DISCO,
        OrigenSO.CLONAR_PLANTILLA,
    ):
        s.opciones[origen].setChecked(True)
        visibles[origen] = s.boton_libvirt.isVisible()
    assert visibles == {
        OrigenSO.DISCO_VACIO: False,
        OrigenSO.ISO: False,
        OrigenSO.IMPORTAR_DISCO: True,
        OrigenSO.CLONAR_PLANTILLA: False,
    }
    assert s.boton_libvirt.isEnabled()


def test_ca_d1_1_1_el_texto_del_boton_es_el_del_requisito(qtbot):
    from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen

    s = SelectorOrigen()
    qtbot.addWidget(s)
    assert s.boton_libvirt.text() == "Rellenar desde un XML de libvirt…"


def test_ca_d1_1_1_pulsar_el_boton_emite_la_peticion_de_abrir_el_asistente(qtbot):
    from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen

    s = SelectorOrigen()
    qtbot.addWidget(s)
    s.show()
    s.establecer_capacidades(caps_origen())
    s.opciones[OrigenSO.IMPORTAR_DISCO].setChecked(True)
    with qtbot.waitSignal(s.pedir_libvirt, timeout=500):
        s.boton_libvirt.click()


# --- La ventana principal -------------------------------------------------------------------------


def _ventana_conectada(qtbot, entorno, inv=None):
    entorno.inv = inv if inv is not None else entorno.inv
    conectar(qtbot, entorno, sesion_falsa())
    esperar_validacion(qtbot, entorno.ventana)
    return entorno.ventana


def _abrir(v):
    v._abrir_importar_libvirt()
    assert v._dialogo_libvirt is not None
    return v._dialogo_libvirt


def _esperar_propuesta(qtbot, dialogo):
    qtbot.waitUntil(
        lambda: dialogo.propuesta is not None or not dialogo.error_lectura.isHidden(), timeout=4000
    )


def test_ca_d1_1_1_la_accion_de_archivo_se_habilita_al_conectar(qtbot, entorno):
    v = entorno.ventana
    assert not v._accion_importar_libvirt.isEnabled()
    assert "Conéctate" in v._accion_importar_libvirt.statusTip()
    _ventana_conectada(qtbot, entorno)
    assert v._accion_importar_libvirt.isEnabled()
    assert v._accion_importar_libvirt.statusTip() == ""


def test_ca_d1_1_3_abrir_el_asistente_no_hace_ninguna_peticion_al_servidor(qtbot, entorno):
    v = _ventana_conectada(qtbot, entorno)
    antes = list(entorno.llamadas)
    d = _abrir(v)
    qtbot.wait(50)
    assert entorno.llamadas == antes  # nada: ni lecturas ni escrituras
    assert (
        d.isVisible() and v._sesion.cliente.__class__ is object
    )  # un cliente que explota si se usa


def test_ca_d1_6_pasa_al_dialogo_los_servidores_en_linea_y_el_del_formulario(qtbot, entorno):
    v = _ventana_conectada(qtbot, entorno)
    d = _abrir(v)
    nodos = [d.combo_nodo.itemData(i) for i in range(d.combo_nodo.count())]
    assert nodos == ["pve1", "pve3"]  # pve2 está caído
    assert d.nodo_elegido == v.formulario.nodo_efectivo()


def test_solo_se_abre_un_asistente_a_la_vez(qtbot, entorno):
    v = _ventana_conectada(qtbot, entorno)
    d = _abrir(v)
    v._abrir_importar_libvirt()
    assert v._dialogo_libvirt is d
    assert not v._accion_importar_libvirt.isEnabled()


def test_rnf_d6_la_lectura_del_xml_no_ocurre_en_el_hilo_de_la_interfaz(
    qtbot, entorno, monkeypatch, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    hilos: list[object] = []

    def lectura(ruta):
        hilos.append(QThread.currentThread())
        hilos.append(threading.current_thread())
        return leer_xml_libvirt(ruta)

    monkeypatch.setattr(vp, "leer_xml_libvirt", lectura)
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "linux_bios.xml"))
    _esperar_propuesta(qtbot, d)
    assert hilos, "el trabajador debió ejecutarse"
    assert hilos[0] is not QCoreApplication.instance().thread()
    assert hilos[1] is not threading.main_thread()
    assert d.propuesta is not None and d.boton_rellenar.isEnabled()


def test_ca_d1_2_6_cerrar_el_dialogo_durante_la_lectura_la_cancela_sin_error(
    qtbot, entorno, monkeypatch, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    liberar, empezo = threading.Event(), threading.Event()

    def lenta(ruta):
        empezo.set()
        liberar.wait(5)
        return leer_xml_libvirt(ruta)

    monkeypatch.setattr(vp, "leer_xml_libvirt", lenta)
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "linux_bios.xml"))
    qtbot.waitUntil(empezo.is_set, timeout=2000)
    d.reject()  # el usuario cierra mientras se lee
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    liberar.set()
    qtbot.waitUntil(lambda: not v._lanzador.hay_activos, timeout=4000)
    qtbot.wait(30)
    assert v._dialogo_libvirt is None and v._accion_importar_libvirt.isEnabled()


def test_un_resultado_tardio_de_una_lectura_abandonada_se_descarta(
    qtbot, entorno, monkeypatch, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    d = _abrir(v)
    gen = v._gen_libvirt
    d.reject()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    v._libvirt_leido(d, gen, None, None)  # no debe fallar aunque el diálogo ya no exista


def test_ca_d1_6_5_rellenar_aplica_la_propuesta_una_sola_vez_y_el_formulario_sigue_editable(
    qtbot, entorno, monkeypatch, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    veces: list[int] = []
    original = v.formulario.aplicar_propuesta_libvirt
    monkeypatch.setattr(
        v.formulario,
        "aplicar_propuesta_libvirt",
        lambda p, *a: (veces.append(1), original(p, *a))[1],
    )
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "linux_bios.xml"))
    _esperar_propuesta(qtbot, d)
    d.boton_rellenar.click()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    esperar_validacion(qtbot, v)
    assert veces == [1]
    cfg = v.formulario.configuracion()
    assert (
        cfg.nombre == "srv-linux"
        and cfg.memoria_mib == 4096
        and cfg.origen == OrigenSO.IMPORTAR_DISCO
    )
    assert isinstance(cfg.detalle_origen, DetalleImportacion)
    assert v.formulario.nombre.isEnabled() and v.formulario.nombre.isReadOnly() is False
    v.formulario.nombre.setText("otro-nombre")
    assert v.formulario.configuracion().nombre == "otro-nombre"


def test_ca_d1_6_3_cancelar_deja_el_formulario_exactamente_igual(qtbot, entorno, tmp_path):
    v = _ventana_conectada(qtbot, entorno)
    antes = v.formulario.configuracion()
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "windows11_uefi_tpm.xml"))
    _esperar_propuesta(qtbot, d)
    d.boton_cancelar.click()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    assert v.formulario.configuracion() == antes


def test_ca_d1_6_4_un_formulario_modificado_hace_que_el_dialogo_pida_confirmacion(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    v.formulario.nombre.setText("mi-maquina")
    assert v._formulario_modificado() is True
    d = _abrir(v)
    preguntas: list[int] = []
    d.confirmar_reemplazo = lambda: preguntas.append(1) or False
    d.leer(_archivo(tmp_path, "linux_bios.xml"))
    _esperar_propuesta(qtbot, d)
    d.boton_rellenar.click()
    assert preguntas == [1] and v.formulario.configuracion().nombre == "mi-maquina"
    assert v._dialogo_libvirt is d  # sigue abierto: el usuario no confirmó


def test_el_formulario_sin_tocar_no_cuenta_como_modificado(qtbot, entorno):
    v = _ventana_conectada(qtbot, entorno)
    assert v._formulario_modificado() is False


def test_ca_d1_14_1_el_passwd_no_llega_al_formulario_ni_a_la_barra_de_estado(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "con_passwd.xml"))
    _esperar_propuesta(qtbot, d)
    d.boton_rellenar.click()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    esperar_validacion(qtbot, v)
    assert SECRETO not in repr(v.formulario.configuracion())
    assert SECRETO not in v.statusBar().currentMessage()
    from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit

    for w in v.findChildren(QLabel):
        assert SECRETO not in w.text()
    for w in v.findChildren(QLineEdit):
        assert SECRETO not in w.text()
    for w in v.findChildren(QPlainTextEdit):
        assert SECRETO not in w.toPlainText()


def test_cerrar_la_sesion_cierra_el_asistente(qtbot, entorno):
    v = _ventana_conectada(qtbot, entorno)
    _abrir(v)
    v._cerrar_dialogo_libvirt()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)


def test_la_ventana_calcula_la_propuesta_con_el_formulario_y_el_inventario_reales(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "linux_bios.xml"))
    _esperar_propuesta(qtbot, d)
    assert d.propuesta.cfg.redes[0].bridge == "vmbr0"  # existe en pve1 del inventario de pruebas
    assert d.propuesta.cfg.nodo == v.formulario.configuracion().nodo


# --- Imágenes por disco tras «Rellenar» (RF-D1.7, CA-D1.7.2/3, CA-D1.15) ---------------------------  # noqa: E501


def _rellenar_con(qtbot, v, tmp_path, nombre="varios_discos_nic.xml"):
    d = _abrir(v)
    d.leer(_archivo(tmp_path, nombre))
    _esperar_propuesta(qtbot, d)
    d.boton_rellenar.click()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    esperar_validacion(qtbot, v)
    return v.formulario.selector_origen


def _botones(selector, texto: str):
    return [b for b in selector.panel_otras.findChildren(QPushButton) if b.text() == texto]


def _casillas_vacio(selector):
    return [c for c in selector.panel_otras.findChildren(QCheckBox) if c.text() == "Crear vacío"]


def _elegir_imagen(qtbot, selector, boton, nombre: str) -> None:
    boton.click()  # abre el catálogo para ese disco
    selector.establecer_seleccion(
        FuenteCatalogo.IMAGEN, volumen(f"local:import/{nombre}", Contenido.IMPORT)
    )
    if selector.dialogo_catalogo is not None:
        selector.dialogo_catalogo.reject()


def test_ca_d1_7_tras_rellenar_cada_disco_adicional_tiene_su_fila_de_imagen(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    sel = _rellenar_con(qtbot, v, tmp_path)
    assert sel.varias_imagenes and sel.origen == OrigenSO.IMPORTAR_DISCO
    assert not sel.panel_otras.isHidden()
    assert len(_botones(sel, "Elegir imagen…")) == 2 and len(_casillas_vacio(sel)) == 2
    otras = v.formulario.configuracion().detalle_origen.otras
    assert [(o.indice, o.imagen, o.crear_vacio) for o in otras] == [
        (1, None, False),
        (2, None, False),
    ]


def test_ca_d1_7_2_un_disco_sin_imagen_ni_crear_vacio_impide_crear_con_v_d27(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    _rellenar_con(qtbot, v, tmp_path)
    v.formulario.nombre.setText("migrada")
    esperar_validacion(qtbot, v)
    assert not v.resumen.boton_crear.isEnabled()
    assert "Elige la imagen del disco" in v.resumen._pendientes.text()


def test_ca_d1_7_cada_eleccion_de_imagen_o_crear_vacio_queda_en_la_configuracion(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    sel = _rellenar_con(qtbot, v, tmp_path)
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[0], "datos.qcow2")
    _casillas_vacio(sel)[1].setChecked(True)
    otras = v.formulario.configuracion().detalle_origen.otras
    assert otras[0].imagen.volid == "local:import/datos.qcow2" and not otras[0].crear_vacio
    assert otras[1].imagen is None and otras[1].crear_vacio is True
    assert "datos.qcow2" in "".join(w.text() for w in sel.panel_otras.findChildren(QLabel))


def test_ca_d1_7_crear_vacio_y_una_imagen_se_excluyen_la_ultima_eleccion_manda(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    sel = _rellenar_con(qtbot, v, tmp_path)
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[0], "datos.qcow2")
    _casillas_vacio(sel)[0].setChecked(True)
    o = v.formulario.configuracion().detalle_origen.otras[0]
    assert o.imagen is None and o.crear_vacio
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[0], "otra.qcow2")
    o = v.formulario.configuracion().detalle_origen.otras[0]
    assert o.imagen is not None and o.imagen.nombre == "otra.qcow2" and not o.crear_vacio


def test_ca_d1_7_las_imagenes_elegidas_se_conservan_al_seguir_editando_el_formulario(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    sel = _rellenar_con(qtbot, v, tmp_path)
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[0], "datos.qcow2")
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[1], "extra.img")
    antes = v.formulario.configuracion().detalle_origen.otras
    v.formulario.nombre.setText("otro-nombre")
    v.formulario.memoria.setText("3072")
    v.formulario.memoria.textEdited.emit("3072")
    esperar_validacion(qtbot, v)
    despues = v.formulario.configuracion().detalle_origen.otras
    assert despues == antes
    assert [o.imagen.nombre for o in despues] == ["datos.qcow2", "extra.img"]


def test_ca_d1_7_sin_libvirt_un_disco_mas_sigue_siendo_vacio_como_en_0_8_0(qtbot, entorno):
    v = _ventana_conectada(qtbot, entorno)
    v.formulario.selector_origen.aplicar(cfg_import())  # sin señales: no abre preguntas
    v.formulario.tabla_discos.agregar_disco()
    esperar_validacion(qtbot, v)
    sel = v.formulario.selector_origen
    assert not sel.varias_imagenes and sel.panel_otras.isHidden()
    assert v.formulario.configuracion().detalle_origen.otras == ()


def test_ca_d1_7_aplicar_otro_xml_empieza_de_cero_con_las_imagenes_del_nuevo(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    sel = _rellenar_con(qtbot, v, tmp_path)
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[0], "datos.qcow2")
    xml = xml_minimo(disco_xml(dev="vda") + disco_xml(dev="vdb", archivo="/i/otro.qcow2")).encode()
    d = _abrir(v)
    d.confirmar_reemplazo = lambda: True
    d.leer(_archivo(tmp_path, "dos_discos.xml", xml))
    _esperar_propuesta(qtbot, d)
    d.boton_rellenar.click()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    esperar_validacion(qtbot, v)
    otras = v.formulario.configuracion().detalle_origen.otras
    assert [(o.indice, o.imagen, o.crear_vacio) for o in otras] == [(1, None, False)]


def test_ca_d1_7_al_quitar_un_disco_intermedio_cada_imagen_sigue_con_su_disco(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    sel = _rellenar_con(qtbot, v, tmp_path)
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[0], "datos.qcow2")  # disco 2
    _elegir_imagen(qtbot, sel, _botones(sel, "Elegir imagen…")[1], "extra.img")  # disco 3
    v.formulario.tabla_discos._filas[1].quitar.click()  # se quita el disco 2
    esperar_validacion(qtbot, v)
    otras = v.formulario.configuracion().detalle_origen.otras
    assert [o.imagen.nombre for o in otras if o.imagen] == ["extra.img"]


# --- MAC por tarjeta en la tabla de redes (RF-D1.10, CA-D1.10.1/5/6/7) ------------------------

DOS_TARJETAS = xml_minimo(
    disco_xml()
    + "<interface type='bridge'><mac address='52:54:00:00:00:01'/><source bridge='vmbr0'/></interface>"  # noqa: E501
    + "<interface type='bridge'><mac address='52:54:00:00:00:02'/><source bridge='vmbr0'/></interface>"  # noqa: E501
    + "<interface type='bridge'><source bridge='vmbr0'/></interface>"
).encode()  # fmt: skip


def _rellenar_con_mac(qtbot, v, tmp_path, xml: bytes, *, conservar: bool):
    d = _abrir(v)
    d.leer(_archivo(tmp_path, "tarjetas.xml", xml))
    _esperar_propuesta(qtbot, d)
    d.casilla_mac.setChecked(conservar)
    d.boton_rellenar.click()
    qtbot.waitUntil(lambda: v._dialogo_libvirt is None, timeout=2000)
    esperar_validacion(qtbot, v)
    return v.formulario.tabla_redes


def test_ca_d1_10_1_por_defecto_ninguna_tarjeta_conserva_la_mac_pero_hay_casillas_desmarcadas(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    tabla = _rellenar_con_mac(qtbot, v, tmp_path, DOS_TARJETAS, conservar=False)
    assert len(tabla._filas) == 3
    # Las tarjetas con <mac> ofrecen su casilla (desmarcada); la que no la trae, no.
    assert [not f.chk_mac.isHidden() for f in tabla._filas] == [True, True, False]
    assert not any(f.chk_mac.isChecked() for f in tabla._filas)
    assert all(r.mac_conservada is None for r in v.formulario.configuracion().redes)
    tabla._filas[1].chk_mac.setChecked(True)  # se puede marcar después, tarjeta a tarjeta
    macs = [r.mac_conservada for r in v.formulario.configuracion().redes]
    assert macs == [None, "52:54:00:00:00:02", None]


def test_ca_d1_10_2_al_conservar_cada_tarjeta_con_mac_muestra_su_casilla_marcada(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    tabla = _rellenar_con_mac(qtbot, v, tmp_path, DOS_TARJETAS, conservar=True)
    visibles = [not f.chk_mac.isHidden() for f in tabla._filas]
    assert visibles == [True, True, False]  # la tarjeta sin <mac> no tiene casilla (CA-D1.10.6)
    assert all(f.chk_mac.isChecked() for f in tabla._filas[:2])
    assert "52:54:00:00:00:01" in tabla._filas[0].chk_mac.text()
    macs = [r.mac_conservada for r in v.formulario.configuracion().redes]
    assert macs == ["52:54:00:00:00:01", "52:54:00:00:00:02", None]


def test_ca_d1_10_5_desmarcar_una_tarjeta_deja_la_mac_solo_en_la_otra(qtbot, entorno, tmp_path):
    v = _ventana_conectada(qtbot, entorno)
    tabla = _rellenar_con_mac(qtbot, v, tmp_path, DOS_TARJETAS, conservar=True)
    tabla._filas[0].chk_mac.setChecked(False)
    macs = [r.mac_conservada for r in v.formulario.configuracion().redes]
    assert macs == [None, "52:54:00:00:00:02", None]
    tabla._filas[0].chk_mac.setChecked(True)  # se puede volver a marcar
    assert v.formulario.configuracion().redes[0].mac_conservada == "52:54:00:00:00:01"


def test_ca_d1_10_6_un_xml_sin_mac_no_ofrece_ninguna_casilla_aunque_se_pida_conservar(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    xml = xml_minimo(disco_xml() + "<interface type='bridge'><source bridge='vmbr0'/></interface>")
    tabla = _rellenar_con_mac(qtbot, v, tmp_path, xml.encode(), conservar=True)
    assert all(f.chk_mac.isHidden() for f in tabla._filas)
    assert all(r.mac_conservada is None for r in v.formulario.configuracion().redes)


def test_ca_d1_10_2_la_mac_conservada_aparece_en_el_resumen_y_avisa_de_apagar_la_original(
    qtbot, entorno, tmp_path
):
    v = _ventana_conectada(qtbot, entorno)
    _rellenar_con_mac(qtbot, v, tmp_path, DOS_TARJETAS, conservar=True)
    assert "MAC conservada" in v.resumen.texto_html and "52:54:00:00:00:01" in v.resumen.texto_html
    assert "Apaga la máquina original" in v.resumen._avisos.text()


def test_ca_d1_10_3_la_ventana_pasa_la_cantidad_del_lote_y_con_varias_copias_no_se_puede_conservar(
    qtbot, entorno
):
    v = _ventana_conectada(qtbot, entorno)
    v.bloque_lote.establecer_cantidad(3)
    assert v.bloque_lote.cantidad_valor() == 3
    d = _abrir(v)
    assert not d.casilla_mac.isEnabled() and "3" in d.aviso_mac.text()
    assert not d.conservar_mac
