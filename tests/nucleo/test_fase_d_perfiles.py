"""D6.2, D3.7 (perfiles), D2.10.5 y D2.11.4 (0.9.0): perfiles de máquina y la fase D.

CA-D6.2.1–2 (núcleo), CA-D3.7.1, CA-D2.10.5, CA-D2.11.4, CL-D6. Un perfil guarda hardware
independiente del servidor: la CPU (incluida ``custom-x``) sí; los mapeos PCI/USB, las imágenes y
la MAC **no** (RF-D6.2). No hay cambio de versión del formato de perfil.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.arquitectura.perfil import adaptar_a_arquitectura
from proxlaunch.nucleo.modelos.vm import Bus, Disco, Firmware, InterfazRed, ModeloRed
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_config, config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.formato import (
    leer_archivo_perfiles,
    leer_perfiles,
    perfiles_a_bytes,
    version_para,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import OrigenPerfil, PerfilMaquina
from proxlaunch.nucleo.perfiles_maquina.validacion import validar_config_perfil
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_d import cfg_arm, hw, inv_arq, pci, usb

DATOS = Path(__file__).resolve().parent.parent / "datos"
MAC = "52:54:00:ab:cd:ef"


def _perfil(config) -> PerfilMaquina:
    return PerfilMaquina("a" * 32, "Mi perfil", "", OrigenPerfil.USUARIO, config)


def _bytes(cfg, **kw: Any) -> bytes:
    p = _perfil(config_desde_configuracion(cfg, con_pistas=False))
    return perfiles_a_bytes([p], con_pistas=False, app_version="0.9.0")


def _con_d(**cambios: Any):
    """Un formulario con todo lo de D rellenado (mapeos, MAC, imagen adicional)."""
    from proxlaunch.nucleo.modelos.origen import ImagenDisco, RefVolumen

    from .apoyo_fase_d import VOLID_IMAGEN_2
    from .apoyo_mvp4 import cfg_import

    cfg = cfg_import(cfg={"discos": [Disco("local-lvm", 32), Disco("local-lvm", 8)]})
    det = dataclasses.replace(
        cfg.detalle_origen, otras=(ImagenDisco(1, RefVolumen("debian.qcow2", VOLID_IMAGEN_2)),)
    )
    return dataclasses.replace(
        cfg,
        detalle_origen=det,
        redes=[InterfazRed("vmbr0", mac_conservada=MAC)],
        hardware_cluster=hw(pci("gpu-a2", pcie=True, x_vga=True), usb("llave-hasp", usb3=True)),
        **cambios,
    )


def _sin_d(cfg):
    return dataclasses.replace(
        cfg,
        hardware_cluster=None,
        redes=[dataclasses.replace(r, mac_conservada=None) for r in cfg.redes],
        detalle_origen=dataclasses.replace(cfg.detalle_origen, otras=()),
    )


# --- CA-D6.2.1 y CA-D3.7.1 ------------------------------------------------------------------------


def test_ca_d6_2_1_el_perfil_de_un_formulario_con_todo_de_d_es_el_mismo_que_sin_d():
    con = _con_d()
    assert config_desde_configuracion(con, con_pistas=False) == config_desde_configuracion(
        _sin_d(con), con_pistas=False
    )
    assert config_desde_configuracion(con, con_pistas=True) == config_desde_configuracion(
        _sin_d(con), con_pistas=True
    )


def test_ca_d6_2_1_el_archivo_de_perfiles_es_identico_al_de_0_8_0_con_el_mismo_hardware():
    con = _con_d()
    assert _bytes(con) == _bytes(_sin_d(con))


def test_ca_d6_2_1_no_hay_cambio_de_version_del_formato_de_perfil():
    p = _perfil(config_desde_configuracion(_con_d(), con_pistas=False))
    assert version_para([p]) <= 3
    assert json.loads(_bytes(_con_d()))["version_formato"] <= 3


def test_ca_d3_7_1_un_perfil_con_cpu_custom_y_dos_mapeos_guarda_la_cpu_y_ningun_mapeo():
    cfg = _con_d(tipo_cpu="custom-x")
    crudo = _bytes(cfg).decode()
    assert '"tipo_cpu": "custom-x"' in crudo or '"tipo_cpu":"custom-x"' in crudo
    for prohibido in ("gpu-a2", "llave-hasp", "mapeo", "hostpci", "usb3", "mac_conservada", MAC,
                      "imagenes", "debian.qcow2", "hardware_cluster"):  # fmt: skip
        assert prohibido not in crudo, prohibido
    assert leer_perfiles(_bytes(cfg)).validos[0].config.tipo_cpu == "custom-x"


def test_ca_d3_7_1_un_perfil_con_cpu_custom_de_64_caracteres_de_nombre_cabe():
    nombre = "custom-" + "a" * 64
    archivo = leer_perfiles(_bytes(cfg_arm(tipo_cpu=nombre)))
    assert archivo.validos and not archivo.invalidos
    assert archivo.validos[0].config.tipo_cpu == nombre


def test_ca_d3_7_1_un_nombre_de_cpu_con_aspecto_de_inyeccion_hace_invalido_el_perfil():
    crudo = json.loads(_bytes(cfg_arm()))
    crudo["perfiles"][0]["config"]["tipo_cpu"] = "custom-x;y=z"
    archivo = leer_perfiles(json.dumps(crudo).encode())
    assert not archivo.validos and archivo.invalidos


def test_ca_d6_2_un_perfil_con_claves_de_d_las_ignora_con_aviso_y_no_las_aplica():
    crudo = json.loads(_bytes(cfg_arm()))
    crudo["perfiles"][0]["config"]["hardware_cluster"] = {"pci": [{"mapeo": "gpu-a2"}]}
    crudo["perfiles"][0]["config"]["redes"][0]["mac_conservada"] = MAC
    archivo = leer_perfiles(json.dumps(crudo).encode())
    assert len(archivo.validos) == 1
    assert any(a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS for a in archivo.avisos)
    assert "gpu-a2" not in repr(archivo.validos[0].config) and MAC not in repr(archivo.validos[0])


# --- CA-D6.2.2 (núcleo): aplicar un perfil --------------------------------------------------------


def test_ca_d6_2_2_aplicar_un_perfil_no_inventa_campos_de_d_ni_toca_los_de_la_cpu_del_perfil():
    cfg = cfg_arm(tipo_cpu="custom-x", firmware=Firmware.OVMF)
    config = config_desde_configuracion(cfg, con_pistas=False)
    inv = inv_arq({}, nodos=("pve1",))
    r = aplicar_config(config, cfg_arm(), inv)
    assert r.cfg.tipo_cpu == "custom-x"
    assert r.cfg.hardware_cluster is None and all(x.mac_conservada is None for x in r.cfg.redes)


def test_ca_d6_2_2_un_perfil_de_0_8_0_con_cpu_x86_se_aplica_igual_en_un_servidor_x86():
    cfg = cfg_arm(tipo_cpu="x86-64-v2-AES")
    r = aplicar_config(config_desde_configuracion(cfg, con_pistas=False), cfg_arm(), None)
    assert r.cfg.tipo_cpu == "x86-64-v2-AES" and r.avisos == ()


# --- CA-D2.10.5: el perfil guardado del formulario adaptado ---------------------------------------


def test_ca_d2_10_5_el_perfil_guardado_desde_el_formulario_adaptado_lleva_los_valores_adaptados():
    x86 = cfg_arm(
        firmware=Firmware.SEABIOS, tipo_cpu="x86-64-v3",
        discos=[Disco("local-lvm", 32, bus=Bus.SATA)],
        redes=[InterfazRed("vmbr0", modelo=ModeloRed.E1000)],
    )  # fmt: skip
    adaptada, cambios = adaptar_a_arquitectura(x86, Arquitectura.AARCH64)
    assert {c.campo for c in cambios} == {
        "firmware",
        "tipo_cpu",
        "discos[0].bus",
        "redes[0].modelo",
    }
    config = config_desde_configuracion(adaptada, con_pistas=False)
    assert config.firmware == Firmware.OVMF and config.tipo_cpu == "host"
    assert config.discos[0].bus == Bus.SCSI and config.redes[0].modelo == ModeloRed.VIRTIO
    # El perfil guardado ya no tiene valores x86: no vuelve a necesitar adaptación en ARM.
    _, de_nuevo = adaptar_a_arquitectura(
        aplicar_config(config, cfg_arm(), None).cfg, Arquitectura.AARCH64
    )
    assert de_nuevo == ()


def test_ca_d2_10_5_el_perfil_adaptado_se_puede_reabrir_en_x86_sin_error():
    adaptada, _ = adaptar_a_arquitectura(
        cfg_arm(firmware=Firmware.SEABIOS, tipo_cpu="x86-64-v2-AES"), Arquitectura.AARCH64
    )
    config = config_desde_configuracion(adaptada, con_pistas=False)
    errores = [p for p in validar_config_perfil(config) if p.severidad == Severidad.ERROR]
    assert errores == []  # SCSI, UEFI y ``host`` son válidos en x86
    archivo = leer_perfiles(
        perfiles_a_bytes([_perfil(config)], con_pistas=False, app_version="0.9.0")
    )
    assert archivo.validos and not archivo.invalidos
    cfg = aplicar_config(config, cfg_arm(), inv_arq({}, nodos=("pve1",))).cfg
    assert cfg.tipo_cpu == "host" and cfg.firmware == Firmware.OVMF


def test_ca_d2_10_1_un_perfil_x86_aplicado_a_un_nodo_arm_se_adapta_en_memoria():
    """El perfil no cambia: lo que se adapta es la configuración resultante (en memoria)."""
    config = config_desde_configuracion(
        cfg_arm(firmware=Firmware.SEABIOS, discos=[Disco("local-lvm", 32, bus=Bus.SATA)]),
        con_pistas=False,
    )
    antes = repr(config)
    cfg = aplicar_config(config, cfg_arm(), inv_arq({}, nodos=("pve1",))).cfg
    adaptada, cambios = adaptar_a_arquitectura(cfg, Arquitectura.AARCH64)
    assert [c.campo for c in cambios] == ["firmware", "discos[0].bus", "tipo_cpu"]
    assert adaptada.discos[0].bus == Bus.SCSI and repr(config) == antes


# --- CA-D2.11.4: perfiles de 0.8.0 ----------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre", ["fase_a_p2/perfiles-051-v1.json", "fase_a_p2/perfiles-051-v2.json"]
)
def test_ca_d2_11_4_los_perfiles_de_0_5_1_con_x86_64_v2_aes_se_leen_y_se_escriben_igual(nombre):
    ruta = DATOS / nombre
    original = json.loads(ruta.read_text(encoding="utf-8"))
    archivo = leer_archivo_perfiles(ruta)
    assert not archivo.invalidos
    assert all(p.config.tipo_cpu == "x86-64-v2-AES" for p in archivo.validos)
    perfiles = [
        PerfilMaquina("a" * 32, p.nombre, p.descripcion, OrigenPerfil.USUARIO, p.config)
        for p in archivo.validos
    ]
    regrabado = json.loads(
        perfiles_a_bytes(perfiles, con_pistas=True, app_version=original["app_version"])
    )
    assert regrabado["perfiles"] == original["perfiles"]


def test_los_perfiles_de_fabrica_siguen_con_la_cpu_x86_por_defecto():
    from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica

    perfiles = perfiles_fabrica()
    assert perfiles and all(p.config.tipo_cpu in ("x86-64-v2-AES", "host") for p in perfiles)
