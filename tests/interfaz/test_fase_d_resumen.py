"""Resumen de una máquina y del lote con las opciones de la fase D (0.9.0).

Derivadas de docs/requisitos/fase-d.md: RF-D0.1 (CA-D0.1.1, CA-D0.1.2), RF-D2.12 (CA-D2.12.1,
CA-D2.12.2: la marca «experimental»), RF-D1.10 (la MAC conservada se ve) y RF-D1.7 (las imágenes
por disco se ven). Solo aparece lo que difiere del valor por defecto. Las líneas del lote vienen de
un plan real sobre un cliente falso, sin red.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.resumen_lote import texto_opciones_del_plan
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.arquitectura.perfil import CambioArquitectura
from proxlaunch.nucleo.hardware_cluster.modelos import (
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
)
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, InterfazRed, OrigenSO

from .apoyo import inventario_cluster
from .apoyo_lote import cfg_simple, definicion, planificar
from .apoyo_mvp4 import cfg_base

MAC = "52:54:00:ab:cd:ef"


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


def pintar(resumen: ResumenVM, cfg: ConfiguracionVM, *, arq=None, cambios=(), avanzado=True) -> str:
    resumen.actualizar(
        cfg,
        ["scsi0", "scsi1", "scsi2"][: len(cfg.discos)] or ["scsi0"],
        [],
        avanzado=avanzado,
        motivo_nodo="",
        bloqueo=None,
        ocupado=False,
        arquitectura=arq,
        cambios_arquitectura=cambios,
    )
    return resumen.texto_html


def con_hardware(**cambios) -> ConfiguracionVM:
    hw = HardwareCluster(
        pci=(AsignacionPCI("gpu-a2", pcie=True, x_vga=True),), usb=(AsignacionUSB("llave-hasp"),)
    )
    return cfg_base(hardware_cluster=hw, tipo_cpu="custom-x", **cambios)


# --- CA-D0.1.1: mapeos y CPU personalizada --------------------------------------------------------


def test_ca_d0_1_1_el_resumen_muestra_el_hardware_del_cluster_y_la_cpu_personalizada(resumen):
    html = pintar(resumen, con_hardware())
    assert (
        "Hardware del clúster:</b> tarjeta PCI «gpu-a2» (pcie, pantalla principal), USB «llave-hasp»"  # noqa: E501
        in html
    )
    assert "CPU:</b> personalizada «custom-x»" in html


def test_ca_d0_1_1_las_opciones_de_cada_dispositivo_salen_en_su_linea(resumen):
    hw = HardwareCluster(
        pci=(AsignacionPCI("a", rombar=False), AsignacionPCI("b", driver_keep=True)),
        usb=(AsignacionUSB("k", usb3=True),),
    )
    html = pintar(resumen, cfg_base(hardware_cluster=hw))
    assert "tarjeta PCI «a» (sin ROM)" in html
    assert "tarjeta PCI «b» (conserva el controlador)" in html
    assert "USB «k» (USB 3)" in html


def test_ca_d0_1_1_con_pcie_el_resumen_dice_que_la_maquina_sera_q35(resumen):
    assert "Tipo de máquina:</b> q35" in pintar(resumen, con_hardware())


def test_ca_d0_1_1_sin_pcie_no_dice_q35(resumen):
    hw = HardwareCluster(usb=(AsignacionUSB("k"),))
    assert "q35" not in pintar(resumen, cfg_base(hardware_cluster=hw))


def test_ca_d0_1_1_el_resumen_escapa_el_marcado_de_lo_que_viene_del_formulario(resumen):
    cfg = cfg_base(
        detalle_origen=DetalleImportacion(
            imagen=RefVolumen("x.qcow2", "local:import/x.qcow2"),
            otras=(ImagenDisco(1, RefVolumen("<b>malo</b>&.qcow2", "local:import/m.qcow2")),),
        ),
        origen=OrigenSO.IMPORTAR_DISCO,
    )
    html = pintar(resumen, cfg)
    assert "<b>malo</b>" not in html and "&lt;b&gt;malo&lt;/b&gt;" in html


# --- CA-D0.1.2: sin opciones de D no hay líneas nuevas --------------------------------------------


def test_ca_d0_1_2_sin_opciones_de_la_fase_d_en_x86_el_resumen_no_gana_ninguna_linea(resumen):
    base = pintar(resumen, cfg_base())
    con_x86 = pintar(resumen, cfg_base(), arq=Arquitectura.X86_64)
    sin_dato = pintar(resumen, cfg_base(), arq=None)
    assert base == con_x86 == sin_dato
    for palabra in ("Hardware del clúster", "MAC conservada", "Discos importados", "experimental",
                    "Valores adaptados", "CPU:", "Servidor:"):  # fmt: skip
        assert palabra not in base, palabra


def test_ca_d0_1_2_una_arquitectura_desconocida_tampoco_añade_nada(resumen):
    assert pintar(resumen, cfg_base(), arq=Arquitectura.DESCONOCIDA) == pintar(resumen, cfg_base())


def test_ca_d0_1_2_un_tipo_de_cpu_normal_no_sale_como_personalizada(resumen):
    for tipo in ("host", "x86-64-v3", "kvm64"):
        assert "personalizada" not in pintar(resumen, cfg_base(tipo_cpu=tipo))


def test_ca_d0_1_2_un_hardware_vacio_no_sale(resumen):
    assert "Hardware del clúster" not in pintar(
        resumen, cfg_base(hardware_cluster=HardwareCluster())
    )


# --- MAC conservada e imágenes por disco ----------------------------------------------------------


def test_ca_d1_10_la_mac_conservada_sale_por_tarjeta_y_la_nueva_no_sale(resumen):
    cfg = cfg_base(redes=[InterfazRed("vmbr0", mac_conservada=MAC), InterfazRed("vmbr0")])
    html = pintar(resumen, cfg)
    assert f"MAC conservada:</b> net0 ({MAC})" in html
    assert "net1 (" not in html.split("MAC conservada")[1].split("<br>")[0]


def test_ca_d1_10_sin_mac_conservada_no_hay_linea(resumen):
    assert "MAC conservada" not in pintar(resumen, cfg_base())


def test_ca_d1_7_las_imagenes_por_disco_salen_con_su_estado(resumen):
    cfg = cfg_base(
        origen=OrigenSO.IMPORTAR_DISCO,
        discos=cfg_simple(gib=8).discos * 3,
        detalle_origen=DetalleImportacion(
            imagen=RefVolumen("a.qcow2", "local:import/a.qcow2"),
            otras=(
                ImagenDisco(1, RefVolumen("b.qcow2", "local:import/b.qcow2")),
                ImagenDisco(2, None, crear_vacio=True),
            ),
        ),
    )
    html = pintar(resumen, cfg)
    assert "Discos importados:</b> disco 2: copia de «b.qcow2»; disco 3: vacío" in html


def test_ca_d1_7_un_disco_pendiente_se_dice_sin_imagen_elegida(resumen):
    cfg = cfg_base(
        origen=OrigenSO.IMPORTAR_DISCO,
        discos=cfg_simple(gib=8).discos * 2,
        detalle_origen=DetalleImportacion(
            imagen=RefVolumen("a.qcow2", "local:import/a.qcow2"), otras=(ImagenDisco(1),)
        ),
    )
    assert "disco 2: sin imagen elegida" in pintar(resumen, cfg)


def test_ca_d1_7_con_una_sola_imagen_como_en_0_8_0_no_hay_linea_de_discos_importados(resumen):
    cfg = cfg_base(
        origen=OrigenSO.IMPORTAR_DISCO,
        detalle_origen=DetalleImportacion(imagen=RefVolumen("a.qcow2", "local:import/a.qcow2")),
    )
    assert "Discos importados" not in pintar(resumen, cfg)


# --- ARM64 (RF-D2.12) -----------------------------------------------------------------------------


def test_ca_d2_12_1_en_un_nodo_arm_el_nodo_y_una_linea_llevan_la_marca(resumen):
    html = pintar(resumen, cfg_base(nodo="pve-arm"), arq=Arquitectura.AARCH64)
    assert "pve-arm (ARM64, experimental)" in html
    assert "ARM64: experimental, sin probar en un servidor arm64" in html


def test_ca_d2_12_1_los_valores_adaptados_se_listan_con_antes_y_despues(resumen):
    cambios = (
        CambioArquitectura("firmware", "seabios", "ovmf"),
        CambioArquitectura("discos[0].bus", "sata", "scsi"),
        CambioArquitectura("tipo_cpu", "x86-64-v3", "host"),
    )
    html = pintar(resumen, cfg_base(), arq=Arquitectura.AARCH64, cambios=cambios)
    linea = next(x for x in html.split("<br>") if "Valores adaptados" in x)
    for esperado in ("seabios", "ovmf", "sata", "scsi", "x86-64-v3", "host"):
        assert esperado in linea
    assert "{" not in linea and "un dato" not in linea


def test_ca_d2_12_2_los_cambios_de_arquitectura_sin_nodo_arm_no_se_muestran(resumen):
    cambios = (CambioArquitectura("firmware", "seabios", "ovmf"),)
    html = pintar(resumen, cfg_base(), arq=Arquitectura.X86_64, cambios=cambios)
    assert "Valores adaptados" not in html and "experimental" not in html


def test_ca_d2_12_2_un_nodo_x86_no_lleva_la_marca_experimental(resumen):
    assert "experimental" not in pintar(resumen, cfg_base(nodo="pve1"), arq=Arquitectura.X86_64)


def test_el_resumen_en_arm_no_pierde_las_demas_lineas(resumen):
    html = pintar(resumen, cfg_base(), arq=Arquitectura.AARCH64)
    for et in ("Nombre", "Procesadores", "Memoria", "Discos", "Redes"):
        assert f"<b>{et}:</b>" in html


def test_el_modo_basico_no_esconde_la_marca_de_arm(resumen):
    assert "experimental" in pintar(resumen, cfg_base(), arq=Arquitectura.AARCH64, avanzado=False)


def test_la_llamada_antigua_sin_los_parametros_de_arquitectura_sigue_valiendo(resumen):
    resumen.actualizar(
        cfg_base(), ["scsi0"], [], avanzado=True, motivo_nodo="", bloqueo=None, ocupado=False
    )
    assert "Nombre" in resumen.texto_html


def test_los_textos_de_los_widgets_no_traen_marcadores_sin_resolver(resumen):
    pintar(resumen, con_hardware(), arq=Arquitectura.AARCH64,
           cambios=(CambioArquitectura("firmware", "seabios", "ovmf"),))  # fmt: skip
    for lbl in resumen.findChildren(QLabel):
        assert "{" not in lbl.text() and "un dato" not in lbl.text()


# --- Resumen del lote (RF-D0.1) -------------------------------------------------------------------


def _plan(plantilla: ConfiguracionVM, cantidad: int = 3):
    return planificar(inventario_cluster(), definicion(cantidad, plantilla=plantilla))


def test_ca_d0_1_2_un_lote_sin_la_fase_d_no_gana_lineas():
    texto = texto_opciones_del_plan(_plan(cfg_simple()))
    for palabra in ("Hardware del clúster", "MAC conservada", "Discos importados", "experimental"):
        assert palabra not in texto
    assert "CPU:" not in texto


def test_ca_d0_1_1_un_lote_con_mapeos_y_cpu_personalizada_los_muestra():
    hw = HardwareCluster(
        pci=(AsignacionPCI("gpu-a2", pcie=True),), usb=(AsignacionUSB("llave-hasp"),)
    )
    texto = texto_opciones_del_plan(_plan(cfg_simple(hardware_cluster=hw, tipo_cpu="custom-x")))
    assert "Hardware del clúster: tarjeta PCI «gpu-a2» (pcie), USB «llave-hasp»" in texto
    assert "CPU: personalizada «custom-x»" in texto


def test_ca_d1_10_un_lote_con_mac_conservada_dice_en_cuantas_maquinas():
    cfg = cfg_simple(redes=[InterfazRed("vmbr0", mac_conservada=MAC)])
    texto = texto_opciones_del_plan(_plan(cfg, cantidad=1))
    assert any(x.startswith("MAC conservada") and "sí" in x for x in texto.splitlines())


def _plan_falso(cfgs: list[ConfiguracionVM], problemas=()):
    """Un plan mínimo (elementos y problemas) para probar solo el texto del Resumen del lote."""
    from types import SimpleNamespace

    from proxlaunch.nucleo.lote.modelos import ElementoPlan

    elementos = [ElementoPlan(i, f"web-{i}", 100 + i, "pve1", c) for i, c in enumerate(cfgs)]
    return SimpleNamespace(elementos=tuple(elementos), problemas=tuple(problemas))


def test_ca_d1_7_el_lote_resume_las_imagenes_de_los_discos_adicionales():
    cfg = cfg_simple(
        origen=OrigenSO.IMPORTAR_DISCO,
        discos=cfg_simple(gib=5).discos * 2,
        detalle_origen=DetalleImportacion(
            imagen=RefVolumen("a.qcow2", "local:import/a.qcow2"),
            otras=(ImagenDisco(1, RefVolumen("b.qcow2", "local:import/b.qcow2")),),
        ),
    )
    texto = texto_opciones_del_plan(_plan_falso([cfg, cfg]))
    assert "disco 2: copia de «b.qcow2»" in texto


def test_ca_d2_12_1_el_lote_con_v_d05_lleva_la_linea_experimental_y_sin_el_no():
    from proxlaunch.nucleo.lote.modelos import Problema, Severidad

    p = Problema("V-D05", Severidad.AVISO, "nodo", {"nodo": "pve-arm"})
    assert "ARM64: experimental" in texto_opciones_del_plan(_plan_falso([cfg_simple()], [p]))
    assert "experimental" not in texto_opciones_del_plan(_plan_falso([cfg_simple()]))


def test_ca_d0_1_1_un_lote_donde_solo_algunas_maquinas_usan_la_mac_lo_dice_con_recuento():
    con = cfg_simple(redes=[InterfazRed("vmbr0", mac_conservada=MAC)])
    sin = cfg_simple()
    texto = texto_opciones_del_plan(_plan_falso([con, sin, sin]))
    linea = next(x for x in texto.splitlines() if x.startswith("MAC conservada"))
    assert "1 de 3" in linea
