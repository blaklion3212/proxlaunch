"""D1.15: integración con lotes, perfiles, CSV y lotes guardados (RF-D1.15, P-D6; RNF-D2/D3).

Derivadas de docs/requisitos/fase-d.md: CA-D1.15.1 a CA-D1.15.5 y CA-D1.14.1 (``passwd`` en
ningún objeto, archivo ni registro). El recorrido es el real de extremo a extremo del núcleo:
bytes del XML -> ``leer_xml`` -> ``interpretar_dominio`` -> ``proponer`` -> configuración del
formulario -> lote/perfil guardado -> lectura de vuelta.
"""

from __future__ import annotations

import dataclasses
import json
import logging

import pytest

from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO
from proxlaunch.nucleo.constructor_peticion import construir_parametros
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.libvirt.correspondencias import PropuestaLibvirt, proponer
from proxlaunch.nucleo.libvirt.lectura_xml import leer_xml
from proxlaunch.nucleo.libvirt.modelos import interpretar_dominio
from proxlaunch.nucleo.lote.modelos import PatronNombres
from proxlaunch.nucleo.lotes_guardados.formato import (
    leer_lote,
    lote_a_bytes,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_config, config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.formato import config_perfil_a_dict
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil

from .apoyo_fase_d_libvirt import (
    cfg_formulario,
    disco_xml,
    dominio_desde_texto,
    inventario_d,
    proponer_de,
    xml_minimo,
)
from .apoyo_lote import definicion
from .apoyo_mvp3 import importar_csv
from .apoyo_mvp4 import cfg_import, inv_origen

INV = inv_origen()
MAC = "52:54:00:ab:cd:ef"
SECRETO = "secreto-CENTINELA-9876"
RUTA_ORIGEN = "/var/lib/libvirt/images/CENTINELA-disco-origen.qcow2"
RUTA_ORIGEN_2 = "/mnt/privado/CENTINELA-datos.qcow2"
RUTA_NVRAM = "/var/lib/libvirt/qemu/nvram/CENTINELA_VARS.fd"

XML_CON_TODO = f"""<domain type='kvm'>
  <name>maq-centinela</name>
  <uuid>aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee</uuid>
  <description>nota con CENTINELA-descripcion</description>
  <memory unit='GiB'>4</memory>
  <vcpu>2</vcpu>
  <os firmware='efi'>
    <type arch='x86_64' machine='q35'>hvm</type>
    <nvram>{RUTA_NVRAM}</nvram>
  </os>
  <devices>
    <disk type='file' device='disk'><driver name='qemu' type='qcow2'/>
      <source file='{RUTA_ORIGEN}'/><target dev='vda' bus='virtio'/><boot order='1'/></disk>
    <disk type='file' device='disk'><driver name='qemu' type='qcow2'/>
      <source file='{RUTA_ORIGEN_2}'/><target dev='vdb' bus='virtio'/></disk>
    <interface type='bridge'><mac address='{MAC}'/><source bridge='vmbr0'/>
      <model type='virtio'/></interface>
    <graphics type='vnc' port='5900' passwd='{SECRETO}'/>
    <graphics type='spice' passwd='{SECRETO}-2'><listen type='address'/></graphics>
  </devices>
</domain>"""
SENTINELAS = (SECRETO, RUTA_ORIGEN, RUTA_ORIGEN_2, RUTA_NVRAM, "CENTINELA", "aaaaaaaa-bbbb")


def _propuesta(xml: str = XML_CON_TODO, *, conservar_mac: bool = False) -> PropuestaLibvirt:
    dominio = interpretar_dominio(leer_xml(xml.encode()))
    return proponer(dominio, cfg_formulario(), inventario_d(), "pve1", conservar_mac=conservar_mac)


def _cfg_rellenada(*, imagenes: int = 2, conservar_mac: bool = False):
    """El formulario tal como queda tras «Rellenar» y elegir las imágenes (con storage real)."""
    p = _propuesta(conservar_mac=conservar_mac)
    cfg = dataclasses.replace(p.cfg, vmid=100, nodo="pve1")
    for d in cfg.discos:
        d.storage = "local-lvm"
    cfg.redes = [dataclasses.replace(r, bridge="vmbr0") for r in cfg.redes]
    cfg.nombre = "migrada-1"
    otras = tuple(
        ImagenDisco(i, RefVolumen(f"d{i}.qcow2", f"local:import/d{i}.qcow2"))
        for i in range(1, imagenes)
    )
    cfg.detalle_origen = DetalleImportacion(
        imagen=RefVolumen("d0.qcow2", "local:import/d0.qcow2"), otras=otras
    )
    cfg.discos = cfg.discos[: max(imagenes, 1)] if imagenes >= 1 else cfg.discos
    return cfg


def _lote(cfg, cantidad: int = 2) -> LoteGuardado:
    plantilla = dataclasses.replace(cfg, vmid=0, nombre="plantilla", nodo="")
    d = definicion(cantidad, plantilla_vm=plantilla)
    return LoteGuardado("migrado", dataclasses.replace(d, patron=PatronNombres("web", "-", 1, 2)))


def _params(cfg) -> dict[str, str]:
    return construir_parametros(dataclasses.replace(cfg, vmid=100, nombre="x", nodo="pve1"), INV)


def _json(datos: bytes) -> dict:
    return json.loads(datos.decode("utf-8"))


# --- CA-D1.15.2: lote guardado con 2 imágenes ----------------------------------------------------


def test_ca_d1_15_2_un_lote_con_dos_imagenes_se_escribe_como_version_6():
    lote = _lote(_cfg_rellenada(imagenes=2))
    assert version_para(lote) == VERSION_FORMATO == 6
    assert _json(lote_a_bytes(lote, app_version="0.9.0"))["version_formato"] == 6


def test_ca_d1_15_2_ida_y_vuelta_deja_las_mismas_peticiones():
    lote = _lote(_cfg_rellenada(imagenes=2))
    leido = leer_lote(lote_a_bytes(lote, app_version="0.9.0"))
    assert leido.version_original == 6
    antes = _params(lote.definicion.plantilla)
    despues = _params(leido.lote.definicion.plantilla)
    assert antes == despues
    assert "import-from=local:import/d0.qcow2" in despues["virtio0"]
    assert "import-from=local:import/d1.qcow2" in despues["virtio1"]


def test_ca_d1_15_2_las_imagenes_volcadas_no_llevan_el_tamano_virtual_de_la_sesion():
    cfg = _cfg_rellenada(imagenes=2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=cfg.detalle_origen.imagen,
        tamano_virtual_bytes=123456789,
        otras=(dataclasses.replace(cfg.detalle_origen.otras[0], tamano_virtual_bytes=987654321),),
    )
    datos = lote_a_bytes(_lote(cfg), app_version="0.9.0").decode()
    assert "123456789" not in datos and "987654321" not in datos


def test_ca_d1_15_2_crear_vacio_tambien_sube_la_version_y_se_conserva():
    cfg = _cfg_rellenada(imagenes=2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=cfg.detalle_origen.imagen, otras=(ImagenDisco(1, None, crear_vacio=True),)
    )
    lote = _lote(cfg)
    assert version_para(lote) == 6
    leido = leer_lote(lote_a_bytes(lote, app_version="0.9.0")).lote.definicion.plantilla
    assert leido.detalle_origen.otras[0].crear_vacio is True
    assert leido.detalle_origen.otras[0].imagen is None


def test_ca_d1_15_2_una_imagen_adicional_pendiente_sola_tambien_sube_la_version():
    # Revisión F6 (QA-4): la pendiente se escribe para reabrirse como pendiente (V-D27).
    cfg = _cfg_rellenada(imagenes=2)
    cfg.detalle_origen = DetalleImportacion(
        imagen=cfg.detalle_origen.imagen, otras=(ImagenDisco(1),)
    )
    assert version_para(_lote(cfg)) == 6


def test_ca_d1_15_2_la_mac_conservada_va_en_el_lote_v6_y_vuelve_igual():
    cfg = _cfg_rellenada(imagenes=2, conservar_mac=True)
    assert cfg.redes[0].mac_conservada == MAC
    lote = _lote(cfg, cantidad=1)
    assert version_para(lote) == 6
    leido = leer_lote(lote_a_bytes(lote, app_version="0.9.0")).lote.definicion.plantilla
    assert leido.redes[0].mac_conservada == MAC
    assert _params(leido)["net0"] == "virtio=52:54:00:AB:CD:EF,bridge=vmbr0"


def test_la_mac_malformada_en_un_archivo_de_lote_no_se_acepta_al_leer():
    cfg = _cfg_rellenada(imagenes=2, conservar_mac=True)
    datos = _json(lote_a_bytes(_lote(cfg, cantidad=1), app_version="0.9.0"))
    texto = json.dumps(datos).replace(MAC, "zz:11:22:33:44:55")
    assert "zz:11" in texto
    with pytest.raises(ErrorProxLaunch) as e:  # el lector valida la MAC y nombra el campo
        leer_lote(texto.encode())
    assert "mac_conservada" in repr(e.value.params)


# --- CA-D1.15.3: lote con una imagen y MAC nueva ------------------------------------------------


def test_ca_d1_15_3_una_imagen_y_mac_nueva_se_escribe_con_version_menor_que_6():
    cfg = _cfg_rellenada(imagenes=1)
    lote = _lote(cfg)
    assert version_para(lote) <= 5
    datos = lote_a_bytes(lote, app_version="0.9.0")
    assert _json(datos)["version_formato"] <= 5
    assert leer_lote(datos).version_original <= 5


def test_ca_d1_15_3_el_archivo_de_una_imagen_no_trae_claves_de_la_fase_d():
    datos = lote_a_bytes(_lote(_cfg_rellenada(imagenes=1)), app_version="0.9.0").decode()
    for clave in ("imagenes", "mac_conservada", "hardware_cluster"):
        assert clave not in datos


def test_ca_d1_15_3_ida_y_vuelta_de_una_imagen_es_identica():
    lote = _lote(_cfg_rellenada(imagenes=1))
    leido = leer_lote(lote_a_bytes(lote, app_version="0.9.0")).lote.definicion.plantilla
    assert _params(leido) == _params(lote.definicion.plantilla)


# --- CA-D1.15.4 y CA-D1.14.1: privacidad ---------------------------------------------------------


def test_ca_d1_15_4_el_lote_guardado_no_trae_xml_rutas_ni_passwd():
    cfg = _cfg_rellenada(imagenes=2, conservar_mac=False)
    datos = lote_a_bytes(_lote(cfg), app_version="0.9.0").decode("utf-8")
    for s in SENTINELAS:
        assert s not in datos, s
    for fragmento in ("<domain", "<devices", "virsh", "passwd", "libvirt/images", "nvram"):
        assert fragmento not in datos, fragmento


def test_ca_d1_15_4_el_lote_con_mac_conservada_tampoco_trae_nada_del_xml():
    datos = lote_a_bytes(
        _lote(_cfg_rellenada(imagenes=2, conservar_mac=True), 1), app_version="0.9.0"
    )
    for s in SENTINELAS:
        assert s.encode() not in datos, s


def test_ca_d1_14_1_el_passwd_no_aparece_en_ningun_objeto_de_la_cadena():
    dominio = interpretar_dominio(leer_xml(XML_CON_TODO.encode()))
    p = proponer(dominio, cfg_formulario(), inventario_d(), "pve1", conservar_mac=True)
    for objeto in (dominio, p, p.cfg, p.filas, p.cfg.detalle_origen):
        assert SECRETO not in repr(objeto)
        assert SECRETO not in str(objeto)
    assert dominio.con_contrasenas is True


def test_ca_d1_14_1_el_passwd_tampoco_esta_en_los_textos_de_la_vista_previa():
    from proxlaunch.interfaz.textos import texto_problema
    from proxlaunch.interfaz.textos_d import texto_concepto_fila, texto_estado_fila_simbolo

    p = _propuesta()
    for f in p.filas:
        trozos = [f.campo, f.origen, f.destino, texto_concepto_fila(f.campo),
                  texto_estado_fila_simbolo(f.estado)]  # fmt: skip
        if f.problema is not None:
            trozos.append(texto_problema(f.problema))
            trozos.append(repr(f.problema.params))
        assert SECRETO not in " ".join(trozos)


def test_ca_d1_14_1_el_passwd_no_aparece_en_el_registro(caplog):
    with caplog.at_level(logging.DEBUG):
        dominio = interpretar_dominio(leer_xml(XML_CON_TODO.encode()))
        proponer(dominio, cfg_formulario(), inventario_d(), "pve1")
    assert SECRETO not in caplog.text


def test_ca_d1_14_1_un_xml_mal_formado_con_passwd_no_filtra_el_secreto_en_el_error():
    from proxlaunch.nucleo.libvirt.lectura_xml import ErrorXml

    xml = f"<domain><graphics passwd='{SECRETO}'></domain>".encode()
    with pytest.raises(ErrorXml) as e:
        leer_xml(xml)
    assert SECRETO not in repr(e.value) and SECRETO not in str(e.value.params)
    assert SECRETO not in repr(e.value.a_error().params)


def test_ca_d1_14_1_la_peticion_final_no_trae_passwd_ni_rutas_del_xml():
    params = _params(_cfg_rellenada(imagenes=2))
    for valor in params.values():
        for s in SENTINELAS:
            assert s not in valor


def test_ca_d1_14_1_con_passwd_aparece_v_d39_y_el_dominio_lo_marca():
    p = _propuesta()
    assert any(f.problema and f.problema.codigo == "V-D39" for f in p.filas)
    assert not p.bloquea()


def test_el_passwd_en_una_etiqueta_de_otro_tipo_no_se_confunde():
    xml = xml_minimo(disco_xml() + "<graphics type='vnc'/>")
    assert dominio_desde_texto(xml).con_contrasenas is False


# --- CA-D1.15.1: perfiles -------------------------------------------------------------------------


def test_ca_d1_15_1_el_perfil_de_un_formulario_rellenado_no_trae_imagenes_rutas_ni_mac():
    cfg = _cfg_rellenada(imagenes=2, conservar_mac=True)
    cp = config_desde_configuracion(cfg, con_pistas=False)
    volcado = json.dumps(config_perfil_a_dict(cp, con_pistas=False))
    for s in (*SENTINELAS, MAC, "d0.qcow2", "d1.qcow2", "import-from", "imagen", "mac"):
        assert s not in volcado, s


def test_ca_d1_15_1_incluso_con_pistas_no_se_guardan_las_imagenes_adicionales_ni_la_mac():
    cfg = _cfg_rellenada(imagenes=2, conservar_mac=True)
    cp = config_desde_configuracion(cfg, con_pistas=True)
    volcado = json.dumps(config_perfil_a_dict(cp, con_pistas=True))
    assert MAC not in volcado and "d1.qcow2" not in volcado
    assert "mac_conservada" not in volcado


def test_ca_d1_15_1_el_hardware_si_se_guarda_y_vuelve_a_aplicarse_sin_d1():
    cfg = _cfg_rellenada(imagenes=2, conservar_mac=True)
    cp = config_desde_configuracion(cfg, con_pistas=False)
    assert isinstance(cp, ConfigPerfil)
    assert (cp.memoria_mib, cp.cores, cp.tipo_cpu) == (cfg.memoria_mib, cfg.cores, cfg.tipo_cpu)
    actual = cfg_import()
    r = aplicar_config(cp, actual, INV)
    nueva = r.cfg if hasattr(r, "cfg") else r
    assert nueva.memoria_mib == cfg.memoria_mib and nueva.cores == cfg.cores
    assert all(red.mac_conservada is None for red in nueva.redes)
    det = nueva.detalle_origen
    assert not isinstance(det, DetalleImportacion) or det.otras == ()


# --- CA-D1.15.5: CSV de 0.8.0 -------------------------------------------------------------------


def test_ca_d1_15_5_una_fila_importar_conserva_una_sola_imagen_como_en_0_8_0():
    r = importar_csv(["nombre;origen;fuente;cpu;memoria", "a;importar;cirros.qcow2;2;4"])
    cfg = r.filas[0].cfg
    assert r.filas[0].problemas == ()
    assert isinstance(cfg.detalle_origen, DetalleImportacion)
    assert cfg.detalle_origen.imagen.nombre == "cirros.qcow2"
    assert cfg.detalle_origen.otras == ()
    assert all(red.mac_conservada is None for red in cfg.redes)


def test_ca_d1_15_5_el_csv_no_tiene_columnas_nuevas_de_d1():
    from proxlaunch.nucleo.csv_importacion import columnas

    texto = " ".join(map(str, vars(columnas).values())).lower()
    for palabra in ("libvirt", "xml", "mac_conservada", "imagenes"):
        assert palabra not in texto


def test_ca_d1_15_5_una_columna_de_mac_en_el_csv_no_se_acepta_como_conservada():
    r = importar_csv(["nombre;origen;fuente;mac", "a;importar;cirros.qcow2;52:54:00:ab:cd:ef"])
    cfg = r.filas[0].cfg
    assert all(red.mac_conservada is None for red in cfg.redes)


# --- Lotes: cantidad -----------------------------------------------------------------------------


def test_ca_d1_15_x_un_lote_de_varias_copias_con_mac_nueva_es_valido_y_con_mac_conservada_no():
    from proxlaunch.nucleo.libvirt.validacion import validar_importacion_d

    cfg = _cfg_rellenada(imagenes=2, conservar_mac=True)
    assert [p.codigo for p in validar_importacion_d(cfg, 5)].count("V-D33") == 1
    cfg2 = _cfg_rellenada(imagenes=2, conservar_mac=False)
    assert validar_importacion_d(cfg2, 5) == []


def test_ca_d1_15_x_el_xml_siempre_describe_una_maquina_y_la_propuesta_no_trae_reparto():
    p = proponer_de("linux_bios.xml", inv=inventario_d())
    assert p.cfg.nodo == "pve1" or p.cfg.nodo == ""
    assert not hasattr(p, "cantidad")
