"""D1.5, D1.11 y D1.12: correspondencias libvirt -> formulario, redes y tipo de SO.

Derivadas de docs/requisitos/fase-d.md: CA-D1.4.1 a CA-D1.4.7 (arquitectura y tipo frente al
nodo), CA-D1.5.1 a CA-D1.5.11, CA-D1.11.1 a CA-D1.11.6 y CA-D1.12.1 a CA-D1.12.5. Se prueba la
interfaz pública (``proponer``, ``FilaVistaPrevia``, ``PropuestaLibvirt``) con XML sintéticos.
"""

from __future__ import annotations

import re

import pytest

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.libvirt.correspondencias import (
    MEMORIA_MAX_MIB,
    TABLA_SO,
    EstadoFila,
    nombre_dns_de,
    proponer,
)
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, RefVolumen, TipoSO
from proxlaunch.nucleo.modelos.vm import Bus, ControladorScsi, Firmware, ModeloRed, OrigenSO
from proxlaunch.nucleo.origen.asistente import TABLA_SO as PERFIL_SO
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_fase_d_libvirt import (
    cfg_formulario,
    codigos,
    disco_xml,
    dominio_desde_texto,
    fila,
    inventario_d,
    proponer_de,
    xml_minimo,
)

X86 = {"pve1": Arquitectura.X86_64, "pve2": Arquitectura.X86_64}
MIXTO = {"pve1": Arquitectura.X86_64, "pve2": Arquitectura.AARCH64}


def _p(xml: str, **kw):
    return proponer_de(dominio_desde_texto(xml), **kw)


def _con_memoria(valor: str, unidad: str | None) -> str:
    atributo = "" if unidad is None else f" unit='{unidad}'"
    return (
        f"<domain type='kvm'><name>m</name><memory{atributo}>{valor}</memory><vcpu>1</vcpu>"
        f"<os><type arch='x86_64'>hvm</type></os><devices>{disco_xml()}</devices></domain>"
    )


# --- CA-D1.5.1 y CA-D1.5.2: memoria ----------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "unidad", "esperada"),
    [
        ("4", "GiB", 4096),
        ("4194305", "KiB", 4097),  # redondeo hacia arriba
        ("4194304", "KiB", 4096),
        ("4194304", None, 4096),  # sin unidad: KiB
        ("16777216", "b", 16),
        ("16777217", "b", 17),
        ("1000", "MB", 954),  # 1 000 000 000 / 2^20 = 953,67 -> 954
        ("1", "TiB", 1024 * 1024),
        ("2", "G", 2048),
        ("512", "M", 512),
        ("3", "TB", 2861023),  # 3e12 / 2^20 = 2861022,9
        ("16384", "k", 16),
        ("2", "T", 2 * 1024 * 1024),
        ("16777", "KB", 16),  # 16 777 000 B = 15,9998 MiB: sube a 16
    ],
)
def test_ca_d1_5_1_la_memoria_se_convierte_a_mib_redondeando_hacia_arriba(valor, unidad, esperada):
    p = _p(_con_memoria(valor, unidad))
    assert p.cfg.memoria_mib == esperada
    assert fila(p, "memoria").estado == EstadoFila.MIGRADO


@pytest.mark.parametrize(
    ("valor", "unidad"),
    [
        ("8", "MiB"),
        ("15", "MiB"),
        ("0", "MiB"),
        ("1024", "KiB"),
        ("5", "TiB"),
        ("x", "MiB"),
        ("4", "ZB"),
    ],
)
def test_ca_d1_5_2_memoria_fuera_de_rango_es_v_d40_y_bloquea(valor, unidad):
    p = _p(_con_memoria(valor, unidad))
    f = fila(p, "memoria")
    assert f.estado == EstadoFila.BLOQUEA
    assert (f.problema.codigo, f.problema.severidad) == ("V-D40", Severidad.ERROR)
    assert p.bloquea()


def test_ca_d1_5_2_los_bordes_16_mib_y_4_tib_se_aceptan():
    assert not _p(_con_memoria("16", "MiB")).bloquea()
    assert not _p(_con_memoria("4", "TiB")).bloquea()
    assert _p(_con_memoria(str(MEMORIA_MAX_MIB + 1), "MiB")).bloquea()


def test_la_memoria_ausente_bloquea_con_v_d40():
    xml = "<domain type='kvm'><name>m</name><os><type arch='x86_64'>hvm</type></os><devices/></domain>"  # noqa: E501
    assert fila(_p(xml), "memoria").problema.codigo == "V-D40"


def test_memoria_actual_menor_va_a_no_se_migra():
    xml = _con_memoria("4", "GiB").replace(
        "<vcpu>", "<currentMemory unit='GiB'>2</currentMemory><vcpu>"
    )
    assert fila(_p(xml), "memoria.actual").estado == EstadoFila.NO_SE_MIGRA


# --- CPU: topología, hilos, límites y tipo (CA-D1.5.3 y CA-D1.5.4) ----------------------------


def _con_cpu(cpu: str, vcpu: str = ">4") -> str:
    return (
        f"<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory>"
        f"<vcpu{vcpu}</vcpu>{cpu}<os><type arch='x86_64'>hvm</type></os>"
        f"<devices>{disco_xml()}</devices></domain>"
    )


def test_ca_d1_5_3_topologia_con_hilos_multiplica_los_nucleos_y_avisa():
    p = _p(_con_cpu("<cpu><topology sockets='2' cores='4' threads='2'/></cpu>", ">16"))
    assert (p.cfg.sockets, p.cfg.cores) == (2, 8)
    h = fila(p, "cpu.hilos")
    assert h is not None and h.estado == EstadoFila.APROXIMADO


def test_sin_topologia_es_un_socket_con_todos_los_vcpu():
    p = _p(_con_cpu("", ">6"))
    assert (p.cfg.sockets, p.cfg.cores) == (1, 6)
    assert fila(p, "cpu.hilos") is None


def test_vcpu_current_distinto_se_ignora_con_fila():
    p = _p(_con_cpu("", " current='2'>4"))
    assert p.cfg.cores == 4
    assert fila(p, "cpu.actual").estado == EstadoFila.NO_SE_MIGRA


@pytest.mark.parametrize(
    "topologia",
    ["sockets='5' cores='1'", "sockets='1' cores='129'", "sockets='2' cores='65' threads='2'"],
)
def test_los_limites_de_sockets_y_nucleos_del_formulario_bloquean_con_v_05(topologia):
    p = _p(_con_cpu(f"<cpu><topology {topologia}/></cpu>", ">4"))
    f = fila(p, "cpu.topologia")
    assert f.estado == EstadoFila.BLOQUEA and f.problema.codigo == "V-05"
    assert p.bloquea()


def test_los_limites_exactos_de_sockets_y_nucleos_se_aceptan():
    assert not _p(
        _con_cpu("<cpu><topology sockets='4' cores='32' threads='4'/></cpu>", ">4")
    ).bloquea()


@pytest.mark.parametrize("modo", ["host-passthrough", "maximum"])
def test_ca_d1_5_4_passthrough_y_maximum_son_cpu_host(modo):
    p = _p(_con_cpu(f"<cpu mode='{modo}'/>"))
    assert p.cfg.tipo_cpu == "host"
    assert fila(p, "cpu").estado == EstadoFila.APROXIMADO


def test_ca_d1_5_4_host_model_es_el_defecto_de_la_app_con_v_d37():
    p = _p(_con_cpu("<cpu mode='host-model'/>"))
    assert p.cfg.tipo_cpu == "x86-64-v2-AES"
    assert fila(p, "cpu").problema.codigo == "V-D37"


def test_ca_d1_5_4_custom_con_modelo_conocido_se_conserva_sin_aviso():
    p = _p(_con_cpu("<cpu mode='custom'><model>x86-64-v3</model></cpu>"))
    assert p.cfg.tipo_cpu == "x86-64-v3"
    f = fila(p, "cpu")
    assert f.estado == EstadoFila.MIGRADO and f.problema is None


def test_ca_d1_5_4_custom_con_modelo_desconocido_va_al_defecto_con_v_d37_y_el_nombre_original():
    p = _p(_con_cpu("<cpu mode='custom'><model fallback='allow'>EPYC-Milan</model></cpu>"))
    assert p.cfg.tipo_cpu == "x86-64-v2-AES"
    pr = fila(p, "cpu").problema
    assert pr.codigo == "V-D37" and pr.params["origen"] == "EPYC-Milan"


def test_las_banderas_de_cpu_no_se_migran():
    p = _p(
        _con_cpu(
            "<cpu mode='custom'><model>qemu64</model><feature name='vmx' policy='require'/></cpu>"
        )
    )
    assert fila(p, "cpu.banderas").estado == EstadoFila.NO_SE_MIGRA


# --- CA-D1.5.5: nombre ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Web Server #1 (prod)", "Web-Server-1-prod"),
        ("#$%&()", "migrada"),
        ("", "migrada"),
        ("   ", "migrada"),
        ("ñandú", "and"),
        ("srv.web.01", "srv.web.01"),
        ("-x-", "x"),
        ("a" * 100, "a" * 63),
    ],
)
def test_ca_d1_5_5_limpieza_dns_del_nombre(nombre, esperado):
    assert nombre_dns_de(nombre) == esperado


def test_ca_d1_5_5_el_aviso_solo_si_cambio_el_nombre():
    cambiado = _p(
        xml_minimo(disco_xml()).replace("<name>m</name>", "<name>Web Server #1 (prod)</name>")
    )
    assert cambiado.cfg.nombre == "Web-Server-1-prod"
    assert fila(cambiado, "nombre").estado == EstadoFila.APROXIMADO
    igual = _p(xml_minimo(disco_xml()))
    assert igual.cfg.nombre == "m" and fila(igual, "nombre").estado == EstadoFila.MIGRADO


# --- CA-D1.5.6: modelos de tarjeta ------------------------------------------------------------


def _con_nic(modelo: str, extra: str = "", bridge: str = "vmbr0") -> str:
    return xml_minimo(
        disco_xml()
        + f"<interface type='bridge'><source bridge='{bridge}'/><model type='{modelo}'/>{extra}</interface>"  # noqa: E501
    )


@pytest.mark.parametrize(
    ("modelo", "esperado", "codigo"),
    [
        ("virtio", ModeloRed.VIRTIO, None),
        ("virtio-transitional", ModeloRed.VIRTIO, None),
        ("virtio-non-transitional", ModeloRed.VIRTIO, None),
        ("e1000", ModeloRed.E1000, None),
        ("e1000e", ModeloRed.E1000, "V-D36"),
        ("82540EM", ModeloRed.E1000, "V-D36"),
        ("rtl8139", ModeloRed.VIRTIO, "V-D36"),
        ("vmxnet3", ModeloRed.VIRTIO, "V-D36"),
        ("ne2k_pci", ModeloRed.VIRTIO, "V-D36"),
        ("pcnet", ModeloRed.VIRTIO, "V-D36"),
    ],
)
def test_ca_d1_5_6_modelo_de_tarjeta_en_x86(modelo, esperado, codigo):
    p = _p(_con_nic(modelo), inv=inventario_d(X86))
    assert p.cfg.redes[0].modelo == esperado
    f = fila(p, "red[0].modelo")
    assert (f.problema.codigo if f.problema else None) == codigo


def test_ca_d1_5_6_en_un_nodo_aarch64_e1000e_pasa_a_virtio_con_v_d08():
    p = _p(_con_nic("e1000e").replace("x86_64", "aarch64"), inv=inventario_d(MIXTO), nodo="pve2")
    assert p.cfg.redes[0].modelo == ModeloRed.VIRTIO
    assert fila(p, "red[0].modelo").problema.codigo == "V-D08"


def test_ca_d1_5_6_sin_modelo_en_la_tarjeta_es_virtio():
    xml = xml_minimo(disco_xml() + "<interface type='bridge'><source bridge='vmbr0'/></interface>")
    assert _p(xml).cfg.redes[0].modelo == ModeloRed.VIRTIO


# --- CA-D1.5.7: bus de disco ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bus", "esperado"),
    [("virtio", Bus.VIRTIO), ("scsi", Bus.SCSI), ("sata", Bus.SATA), ("ide", Bus.IDE)],
)
def test_ca_d1_5_7_el_bus_se_conserva_en_x86(bus, esperado):
    p = _p(xml_minimo(disco_xml(bus=bus)))
    assert p.cfg.discos[0].bus == esperado
    assert fila(p, "disco[0].bus") is None


@pytest.mark.parametrize("bus", ["sata", "ide"])
def test_ca_d1_5_7_en_aarch64_sata_e_ide_pasan_a_scsi_con_aviso(bus):
    p = _p(xml_minimo(disco_xml(bus=bus), arch="aarch64"), inv=inventario_d(MIXTO), nodo="pve2")
    assert p.cfg.discos[0].bus == Bus.SCSI
    assert fila(p, "disco[0].bus").problema.codigo == "V-D08"


@pytest.mark.parametrize("bus", ["nvme", "usb", "sd", "xen"])
def test_ca_d1_5_7_buses_sin_equivalente_pasan_a_scsi_con_aviso(bus):
    p = _p(xml_minimo(disco_xml(bus=bus)))
    assert p.cfg.discos[0].bus == Bus.SCSI
    f = fila(p, "disco[0].bus")
    assert f.problema.codigo == "V-D36" and f.problema.severidad == Severidad.AVISO


def test_el_bus_ausente_se_deduce_del_nombre_del_dispositivo():
    xml = xml_minimo(disco_xml(dev="sdb", bus=""))
    assert _p(xml).cfg.discos[0].bus == Bus.SCSI


# --- CA-D1.5.8: TPM --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tpm",
    [
        "<tpm model='tpm-crb'><backend type='emulator' version='2.0'/></tpm>",
        "<tpm model='tpm-tis'><backend type='emulator' version='1.2'/></tpm>",
        "<tpm model='tpm-tis'><backend type='passthrough'><device path='/dev/tpm0'/></backend></tpm>",  # noqa: E501
        "<tpm/>",
    ],
)
def test_ca_d1_5_8_cualquier_tpm_activa_el_v2_con_v_d31(tpm):
    p = _p(xml_minimo(disco_xml() + tpm))
    assert p.cfg.tpm is True
    assert fila(p, "tpm").problema.codigo == "V-D31"


def test_ca_d1_5_8_el_motivo_distingue_v12_y_passthrough():
    v12 = _p(xml_minimo(disco_xml() + "<tpm><backend type='emulator' version='1.2'/></tpm>"))
    pas = _p(xml_minimo(disco_xml() + "<tpm><backend type='passthrough'/></tpm>"))
    assert fila(v12, "tpm").problema.params["motivo"] == "v1.2"
    assert fila(pas, "tpm").problema.params["motivo"] == "passthrough"


def test_ca_d1_5_8_sin_tpm_queda_desactivado_y_sin_fila():
    p = _p(xml_minimo(disco_xml()))
    assert p.cfg.tpm is False and fila(p, "tpm") is None


# --- CA-D1.5.9 y CA-D1.5.11: lo que no se migra ----------------------------------------------

_DISPOSITIVOS_SIN_EQUIVALENTE = [
    "<sound model='ich9'/>",
    "<watchdog model='itco' action='reset'/>",
    "<hostdev mode='subsystem' type='pci'><source/></hostdev>",
    "<hostdev mode='subsystem' type='usb'><source/></hostdev>",
    "<graphics type='vnc'/>",
    "<video><model type='cirrus'/></video>",
    "<input type='tablet' bus='usb'/>",
    "<rng model='virtio'/>",
    "<serial type='pty'/>",
    "<console type='pty'/>",
    "<redirdev bus='usb' type='spicevmc'/>",
    "<hub type='usb'/>",
    "<memballoon model='virtio'/>",
]


def test_ca_d1_5_9_ningun_dispositivo_conocido_se_pierde_en_silencio():
    xml = xml_minimo(disco_xml() + "".join(_DISPOSITIVOS_SIN_EQUIVALENTE))
    p = _p(xml)
    f = fila(p, "dispositivos")
    assert f.estado == EstadoFila.NO_SE_MIGRA and f.problema.codigo == "V-D41"
    for etiqueta in ("sound", "watchdog", "hostdev", "graphics", "video", "input", "rng", "serial",
                     "console", "redirdev", "hub", "memballoon"):  # fmt: skip
        assert etiqueta in f.origen, etiqueta


def test_ca_d1_5_9_varios_del_mismo_tipo_se_agrupan_con_su_recuento():
    xml = xml_minimo(disco_xml() + "<hostdev/><hostdev/><hostdev/>")
    assert "3×hostdev" in fila(_p(xml), "dispositivos").origen


def test_ca_d1_5_9_el_aviso_de_hostdev_remite_a_hardware_del_cluster():
    from proxlaunch.interfaz.textos import texto_problema

    p = _p(xml_minimo(disco_xml() + "<hostdev/>"))
    assert "Hardware del clúster" in texto_problema(fila(p, "dispositivos").problema)


def test_ca_d1_5_9_cdrom_y_floppy_se_ignoran_con_fila_propia():
    cd = "<disk type='file' device='cdrom'><source file='/x.iso'/><target dev='sda' bus='sata'/></disk>"  # noqa: E501
    fl = "<disk device='floppy'><target dev='fda' bus='fdc'/></disk>"
    p = _p(xml_minimo(disco_xml() + cd + fl))
    assert len(p.cfg.discos) == 1
    assert fila(p, "cdrom[1]").estado == EstadoFila.NO_SE_MIGRA
    assert fila(p, "cdrom[2]").estado == EstadoFila.NO_SE_MIGRA


def test_ca_d1_5_9_elementos_de_dominio_sin_equivalente_van_a_otros():
    extra = (
        "<uuid>x</uuid><title>t</title><description>d</description><clock offset='utc'/><features/>"
    )
    p = _p(xml_minimo(disco_xml(), extra=extra))
    f = fila(p, "otros")
    assert f.estado == EstadoFila.NO_SE_MIGRA
    for e in ("uuid", "title", "description", "clock", "features"):
        assert e in f.origen


def test_ca_d1_5_11_elementos_desconocidos_de_una_version_futura_se_ignoran_con_aviso():
    xml = xml_minimo(disco_xml() + "<holograma foo='1'/><otra-cosa/>", extra="<novedad2030/>")
    p = _p(xml)
    f = fila(p, "desconocidos")
    assert f.estado == EstadoFila.NO_SE_MIGRA
    assert f.problema.codigo == "V-D41.desconocidos" and f.problema.severidad == Severidad.AVISO
    for nombre in ("holograma", "otra-cosa", "novedad2030"):
        assert nombre in f.origen
    assert not p.bloquea()


def test_ca_d1_5_11_atributos_desconocidos_no_provocan_excepcion():
    xml = xml_minimo(disco_xml(extra="<nuevo x='1'/>"), extra="").replace(
        "<vcpu>1</vcpu>", "<vcpu futuro='si' placement='static'>1</vcpu>"
    )
    assert not _p(xml).bloquea()


def test_el_agente_invitado_se_activa_con_el_canal_de_qemu():
    canal = "<channel type='unix'><target type='virtio' name='org.qemu.guest_agent.0'/></channel>"
    assert _p(xml_minimo(disco_xml() + canal)).cfg.agente_qemu is True
    otro = "<channel type='spicevmc'><target type='virtio' name='com.redhat.spice.0'/></channel>"
    p = _p(xml_minimo(disco_xml() + otro))
    assert p.cfg.agente_qemu is False and "channel" in fila(p, "dispositivos").origen


# --- CA-D1.5.10: límite de ancho de banda ------------------------------------------------------


@pytest.mark.parametrize(("kib", "mb"), [(10240, 11), (1, 1), (976, 1), (977, 2), (1000000, 1024)])
def test_ca_d1_5_10_el_limite_de_salida_se_redondea_hacia_arriba_con_aviso(kib, mb):
    extra = f"<bandwidth><outbound average='{kib}'/></bandwidth>"
    p = _p(_con_nic("virtio", extra))
    assert p.cfg.redes[0].limite_mb == float(mb)
    assert fila(p, "red[0].limite").estado == EstadoFila.APROXIMADO


def test_sin_limite_o_con_cero_no_se_propone_limite():
    assert _p(_con_nic("virtio")).cfg.redes[0].limite_mb is None
    p = _p(_con_nic("virtio", "<bandwidth><outbound average='0'/></bandwidth>"))
    assert p.cfg.redes[0].limite_mb is None


def test_mtu_solo_con_virtio_y_dentro_de_rango():
    ok = _p(_con_nic("virtio", "<mtu size='9000'/>"))
    assert ok.cfg.redes[0].mtu == 9000
    e1000 = _p(_con_nic("e1000", "<mtu size='9000'/>"))
    assert (
        e1000.cfg.redes[0].mtu is None
        and fila(e1000, "red[0].mtu").estado == EstadoFila.NO_SE_MIGRA
    )
    fuera = _p(_con_nic("virtio", "<mtu size='100000'/>"))
    assert fuera.cfg.redes[0].mtu is None


def test_enlace_caido_y_filtro_no_se_migran():
    p = _p(_con_nic("virtio", "<link state='down'/><filterref filter='clean-traffic'/>"))
    f = fila(p, "red[0].extra")
    assert (
        f.estado == EstadoFila.NO_SE_MIGRA and "link=down" in f.origen and "filterref" in f.origen
    )


# --- CA-D1.4.x: arquitectura y tipo frente al nodo --------------------------------------------


def test_ca_d1_4_1_kvm_hvm_x86_y_nodo_x86_se_acepta_sin_errores():
    p = _p(xml_minimo(disco_xml()), inv=inventario_d(X86))
    assert not p.bloquea()
    assert fila(p, "tipo_dominio").estado == EstadoFila.MIGRADO
    assert fila(p, "arquitectura").estado == EstadoFila.MIGRADO


@pytest.mark.parametrize("tipo", ["xen", "lxc", "vmware", "hvf", "vbox", ""])
def test_ca_d1_4_2_dominios_no_kvm_son_v_d23_y_bloquean(tipo):
    p = _p(xml_minimo(disco_xml(), tipo=tipo))
    f = fila(p, "tipo_dominio")
    assert f.estado == EstadoFila.BLOQUEA and f.problema.codigo == "V-D23"
    assert p.bloquea()


def test_ca_d1_4_2_os_type_exe_de_contenedor_es_v_d23():
    xml = xml_minimo(disco_xml()).replace(">hvm<", ">exe<")
    p = _p(xml)
    assert fila(p, "tipo_os").problema.codigo == "V-D23" and p.bloquea()


def test_ca_d1_4_3_qemu_se_acepta_con_v_d23b():
    p = _p(xml_minimo(disco_xml(), tipo="qemu"))
    assert fila(p, "tipo_dominio").problema.codigo == "V-D23b"
    assert fila(p, "tipo_dominio").problema.severidad == Severidad.AVISO
    assert not p.bloquea()


def test_ca_d1_4_4_aarch64_en_nodos_x86_es_v_d24_con_las_dos_arquitecturas():
    p = _p(xml_minimo(disco_xml(), arch="aarch64"), inv=inventario_d(X86))
    f = fila(p, "arquitectura")
    assert f.estado == EstadoFila.BLOQUEA and f.problema.codigo == "V-D24"
    assert f.problema.params["arq_xml"] == "aarch64" and f.problema.params["arq_nodo"] == "x86_64"
    assert p.bloquea()


def test_ca_d1_4_4_con_un_nodo_aarch64_ese_nodo_se_acepta():
    inv = inventario_d(MIXTO)
    xml = xml_minimo(disco_xml(), arch="aarch64")
    assert not _p(xml, inv=inv, nodo="pve2").bloquea()
    assert _p(xml, inv=inv, nodo="pve1").bloquea()


def test_ca_d1_4_4_x86_en_un_nodo_aarch64_tambien_bloquea():
    p = _p(xml_minimo(disco_xml()), inv=inventario_d(MIXTO), nodo="pve2")
    assert fila(p, "arquitectura").problema.codigo == "V-D24" and p.bloquea()


def test_ca_d1_4_5_arch_ausente_asume_la_del_nodo_con_aviso():
    xml = (
        "<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory><os><type>hvm</type></os><devices>"  # noqa: E501
        + disco_xml()
        + "</devices></domain>"
    )
    p = _p(xml, inv=inventario_d(MIXTO), nodo="pve2")
    f = fila(p, "arquitectura")
    assert f.problema.codigo == "V-D24.supuesta" and f.problema.severidad == Severidad.AVISO
    assert f.destino == "aarch64" and not p.bloquea()


@pytest.mark.parametrize("arch", ["ppc64le", "ppc64", "s390x", "riscv64", "armv7l", "mips"])
def test_ca_d1_4_6_otras_arquitecturas_siempre_v_d24(arch):
    for nodo, inv in (("pve1", inventario_d(X86)), ("pve2", inventario_d(MIXTO))):
        p = _p(xml_minimo(disco_xml(), arch=arch), inv=inv, nodo=nodo)
        assert fila(p, "arquitectura").problema.codigo == "V-D24" and p.bloquea()


def test_ca_d1_4_6_otras_arquitecturas_bloquean_incluso_sin_nodo():
    assert _p(xml_minimo(disco_xml(), arch="ppc64le"), nodo=None).bloquea()


def test_ca_d1_4_7_nodo_de_arquitectura_desconocida_acepta_x86_con_v_d04():
    p = _p(xml_minimo(disco_xml()), inv=inventario_d({"pve1": Arquitectura.DESCONOCIDA}))
    f = fila(p, "arquitectura")
    assert f.problema.codigo == "V-D04" and f.estado == EstadoFila.APROXIMADO
    assert not p.bloquea()


def test_i686_se_acepta_en_x86_con_aviso():
    p = _p(xml_minimo(disco_xml(), arch="i686"), inv=inventario_d(X86))
    assert fila(p, "arquitectura.i686").problema.codigo == "V-D24.i686"
    assert not p.bloquea()


# --- CA-D1.11.x: redes ----------------------------------------------------------------------


def _con_red(tipo: str, fuente: str, extra: str = "") -> str:
    return xml_minimo(
        disco_xml() + f"<interface type='{tipo}'>{fuente}<model type='virtio'/>{extra}</interface>"
    )


def test_ca_d1_11_1_el_bridge_del_xml_que_existe_en_el_nodo_se_propone():
    inv = inventario_d(X86, bridges=("br0", "vmbr0"))
    p = _p(_con_red("bridge", "<source bridge='br0'/>"), inv=inv)
    assert p.cfg.redes[0].bridge == "br0"
    assert fila(p, "red[0]").problema is None


def test_ca_d1_11_1_si_el_bridge_no_existe_la_tarjeta_queda_sin_red_con_v_d35():
    p = _p(_con_red("bridge", "<source bridge='br0'/>"), inv=inventario_d(X86))
    assert p.cfg.redes[0].bridge == ""
    f = fila(p, "red[0]")
    assert f.problema.codigo == "V-D35" and f.problema.severidad == Severidad.ERROR
    assert f.problema.params["motivo"] == "bridge_inexistente"


def test_ca_d1_11_1_sin_nodo_elegido_no_se_propone_ningun_bridge():
    p = _p(_con_red("bridge", "<source bridge='vmbr0'/>"), nodo=None)
    assert p.cfg.redes[0].bridge == ""


def test_ca_d1_11_2_red_default_de_libvirt_es_nat_y_no_bloquea_rellenar():
    p = _p(_con_red("network", "<source network='default'/>"), inv=inventario_d(X86))
    f = fila(p, "red[0]")
    assert f.problema.codigo == "V-D35" and f.problema.params["motivo"] == "nat"
    assert f.estado != EstadoFila.BLOQUEA and not p.bloquea()
    assert p.cfg.redes[0].bridge == ""


def test_ca_d1_11_2_el_texto_de_nat_lo_explica():
    from proxlaunch.interfaz.textos import texto_problema

    p = _p(_con_red("network", "<source network='default'/>"), inv=inventario_d(X86))
    assert "NAT" in texto_problema(fila(p, "red[0]").problema)


def test_ca_d1_11_2_el_texto_de_v_d35_nombra_la_tarjeta_sin_marcadores_sin_resolver():
    from proxlaunch.interfaz.textos import texto_problema

    p = _p(_con_red("network", "<source network='default'/>"), inv=inventario_d(X86))
    assert "un dato" not in texto_problema(fila(p, "red[0]").problema)


def test_ca_d1_11_3_direct_es_v_d35():
    p = _p(_con_red("direct", "<source dev='eth0' mode='bridge'/>"), inv=inventario_d(X86))
    f = fila(p, "red[0]")
    assert f.problema.codigo == "V-D35" and f.problema.params["motivo"] == "direct"


def test_ca_d1_11_3_el_texto_de_direct_explica_macvtap():
    from proxlaunch.interfaz.textos import texto_problema

    p = _p(_con_red("direct", "<source dev='eth0' mode='bridge'/>"), inv=inventario_d(X86))
    assert "macvtap" in texto_problema(fila(p, "red[0]").problema).lower()


@pytest.mark.parametrize("tipo", ["user", "ethernet", "vhostuser", "hostdev", "vdpa", "udp"])
def test_ca_d1_11_x_los_tipos_sin_equivalente_son_v_d35_y_sin_bridge(tipo):
    p = _p(_con_red(tipo, "<source dev='x'/>"), inv=inventario_d(X86))
    assert fila(p, "red[0]").problema.codigo == "V-D35"
    assert p.cfg.redes[0].bridge == "" and not p.bloquea()


def test_ca_d1_11_x_openvswitch_avisa_de_elegir_un_bridge_ovs():
    p = _p(_con_red("bridge", "<source bridge='vmbr0'/>", "<virtualport type='openvswitch'/>"),
           inv=inventario_d(X86))  # fmt: skip
    f = fila(p, "red[0].virtualport")
    assert f.problema.codigo == "V-D35" and f.problema.params["motivo"] == "openvswitch"


def test_ca_d1_11_4_la_vlan_del_xml_se_propone():
    p = _p(_con_red("bridge", "<source bridge='vmbr0'/>", "<vlan><tag id='20'/></vlan>"),
           inv=inventario_d(X86))  # fmt: skip
    assert p.cfg.redes[0].vlan == 20


@pytest.mark.parametrize("tag", ["0", "4095", "99999", "x", ""])
def test_ca_d1_11_4_una_vlan_fuera_de_rango_no_se_propone(tag):
    p = _p(_con_red("bridge", "<source bridge='vmbr0'/>", f"<vlan><tag id='{tag}'/></vlan>"),
           inv=inventario_d(X86))  # fmt: skip
    assert p.cfg.redes[0].vlan is None


def test_ca_d1_11_5_tres_interfaces_son_tres_tarjetas_en_el_mismo_orden():
    nics = "".join(
        f"<interface type='bridge'><source bridge='{b}'/><model type='virtio'/></interface>"
        for b in ("vmbr1", "vmbr0", "vmbr1")
    )
    p = _p(xml_minimo(disco_xml() + nics), inv=inventario_d(X86))
    assert [r.bridge for r in p.cfg.redes] == ["vmbr1", "vmbr0", "vmbr1"]
    assert [f.campo for f in p.filas if re.fullmatch(r"red\[\d\]", f.campo)] == [
        "red[0]",
        "red[1]",
        "red[2]",
    ]


@pytest.mark.parametrize(
    "nombre",
    [
        "vmbr0;rm -rf /",
        "../../etc",
        "vmbr0‮",
        "<b>vmbr0</b>",
        "vmbr0\n",
        "a" * 400,
        "VMBR0",
        "vmbr0 ",
    ],
)
def test_ca_d1_11_6_un_nombre_de_bridge_raro_nunca_se_propone(nombre):
    from xml.sax.saxutils import quoteattr

    xml = xml_minimo(
        disco_xml()
        + f"<interface type='bridge'><source bridge={quoteattr(nombre)}/><model type='virtio'/></interface>"  # noqa: E501
    )
    p = _p(xml, inv=inventario_d(X86, bridges=("vmbr0",)))
    assert p.cfg.redes[0].bridge == ""


def test_ca_d1_11_6_aunque_el_nodo_tenga_un_bridge_con_nombre_raro_no_se_toma_del_xml():
    nombre = "vmbr0‮"  # saneado = «vmbr0», que SÍ existe: el texto original no es limpio
    from xml.sax.saxutils import quoteattr

    xml = xml_minimo(
        disco_xml()
        + f"<interface type='bridge'><source bridge={quoteattr(nombre)}/><model type='virtio'/></interface>"  # noqa: E501
    )
    p = _p(xml, inv=inventario_d(X86, bridges=("vmbr0",)))
    assert p.cfg.redes[0].bridge == ""


def test_ca_d1_11_6_lo_que_llega_a_la_peticion_solo_es_un_bridge_del_nodo():
    inv = inventario_d(X86, bridges=("vmbr0",))
    p = _p(_con_red("bridge", "<source bridge='vmbr0'/>"), inv=inv)
    assert {r.bridge for r in p.cfg.redes} <= {"", "vmbr0"}


# --- CA-D1.12.x: tipo de SO -----------------------------------------------------------------


def _con_pista(pista: str | None, extra: str = "") -> str:
    meta = (
        ""
        if pista is None
        else "<metadata><libosinfo:libosinfo xmlns:libosinfo='http://libosinfo.org/xmlns/libvirt/domain/1.0'>"
        f"<libosinfo:os id='{pista}'/></libosinfo:libosinfo></metadata>"
    )
    return xml_minimo(disco_xml(), extra=meta + extra)


@pytest.mark.parametrize(
    ("pista", "ostype"),
    [
        ("http://microsoft.com/win/11", "win11"),
        ("http://ubuntu.com/ubuntu/24.04", "l26"),
        ("http://debian.org/debian/13", "l26"),
        ("http://microsoft.com/win/2k22", "win11"),
        ("http://microsoft.com/win/2k25", "win11"),
        ("http://microsoft.com/win/10", "win10"),
        ("http://microsoft.com/win/2k16", "win10"),
        ("http://microsoft.com/win/2k19", "win10"),
        ("http://fedoraproject.org/fedora/40", "l26"),
        ("http://redhat.com/rhel/9.4", "l26"),
        ("http://archlinux.org/archlinux/rolling", "l26"),
    ],
)
def test_ca_d1_12_1_tipo_de_so_por_libosinfo(pista, ostype):
    p = _p(_con_pista(pista))
    assert PERFIL_SO[p.cfg.tipo_so].ostype == ostype
    f = fila(p, "tipo_so")
    assert f.estado == EstadoFila.MIGRADO and f.problema is None


@pytest.mark.parametrize(
    "pista",
    ["http://microsoft.com/win/7", "http://microsoft.com/win/xp", "http://microsoft.com/win/2k8r2",
     "http://microsoft.com/win/8.1", "http://microsoft.com/win/vista"],
)  # fmt: skip
def test_ca_d1_12_2_windows_antiguo_es_other_con_v_d38(pista):
    p = _p(_con_pista(pista))
    assert p.cfg.tipo_so == TipoSO.OTRO
    f = fila(p, "tipo_so")
    assert f.problema.codigo == "V-D38" and f.problema.params["motivo"] == "windows_antiguo"
    assert f.estado == EstadoFila.APROXIMADO


@pytest.mark.parametrize(
    "pista", ["http://oracle.com/solaris/11", "http://openindiana.org/openindiana/2023"]
)
def test_solaris_y_openindiana_son_other_aproximado(pista):
    p = _p(_con_pista(pista))
    assert p.cfg.tipo_so == TipoSO.OTRO and fila(p, "tipo_so").problema.codigo == "V-D38"


def test_ca_d1_12_3_sin_metadatos_y_con_hyperv_es_windows_10_con_v_d38():
    p = _p(xml_minimo(disco_xml(), extra="<features><hyperv mode='custom'/></features>"))
    assert p.cfg.tipo_so == TipoSO.WINDOWS_10
    f = fila(p, "tipo_so")
    assert f.problema.codigo == "V-D38" and f.problema.params["motivo"] == "hyperv"
    assert f.estado == EstadoFila.APROXIMADO


def test_ca_d1_12_3_sin_metadatos_ni_hyperv_es_other_con_v_d38():
    p = _p(_con_pista(None))
    assert p.cfg.tipo_so == TipoSO.OTRO and fila(p, "tipo_so").problema.codigo == "V-D38"


@pytest.mark.parametrize(
    "pista",
    ["", "no-es-una-url", "http://microsoft.com/win/", "http://microsoft.com/win/1", "http://microsoft.com/win/110",
     "x" * 5000, "http://ubuntu.com/ubuntuXX/1", "javascript:alert(1)", "‮http://microsoft.com/win/11"],
)  # fmt: skip
def test_ca_d1_12_4_un_id_inesperado_o_largo_es_other_sin_excepcion(pista):
    p = _p(_con_pista(pista))
    assert p.cfg.tipo_so == TipoSO.OTRO or p.cfg.tipo_so == TipoSO.WINDOWS_11
    # El id solo sale saneado y acotado.
    assert len(fila(p, "tipo_so").origen) <= 256
    assert not set("<>&") & set(fila(p, "tipo_so").origen)


def test_ca_d1_12_4_la_comparacion_es_por_segmentos_no_por_prefijo_de_texto():
    # «win/110» no es «win/11»; «ubuntuXX» no es «ubuntu».
    assert _p(_con_pista("http://microsoft.com/win/110")).cfg.tipo_so == TipoSO.OTRO
    assert _p(_con_pista("http://ubuntu.com/ubuntuXX/1")).cfg.tipo_so == TipoSO.OTRO


def test_ca_d1_12_x_la_tabla_cubre_los_prefijos_del_requisito():
    for prefijo in ("microsoft.com/win/11", "microsoft.com/win/10", "microsoft.com/win/2k22"):
        assert prefijo in TABLA_SO


def test_ca_d1_12_5_el_tipo_propuesto_es_editable_y_la_regla_de_claves_usa_el_final():
    """El tipo del formulario manda sobre lo propuesto: ``proponer`` no fija claves por SO."""
    p = _p(_con_pista("http://microsoft.com/win/11"))
    assert p.cfg.tipo_so == TipoSO.WINDOWS_11
    p.cfg.tipo_so = TipoSO.LINUX  # el usuario lo cambia
    from proxlaunch.nucleo.constructor_peticion import construir_parametros

    p.cfg.firmware = Firmware.OVMF
    p.cfg.nodo = "pve1"
    p.cfg.detalle_origen = DetalleImportacion(imagen=RefVolumen("x.qcow2", "local:import/x.qcow2"))
    params = construir_parametros(p.cfg, inventario_d(X86))
    assert "pre-enrolled-keys=0" in params["efidisk0"]  # Linux: sin claves precargadas


def test_secure_boot_inscrito_en_un_so_no_windows_avisa_con_fila():
    xml = xml_minimo(disco_xml()).replace("<os>", "<os firmware='efi'>")
    xml = xml.replace("<devices>", "<devices>", 1).replace(
        "</os>",
        "<loader secure='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.secboot.fd</loader></os>",
    )
    p = _p(xml)
    assert fila(p, "firmware.claves") is not None


# --- Forma general de la propuesta ----------------------------------------------------------


def test_la_propuesta_rellena_origen_importar_disco_y_controlador_virtio_single():
    p = _p(xml_minimo(disco_xml()))
    assert p.cfg.origen == OrigenSO.IMPORTAR_DISCO
    assert p.cfg.controlador_scsi == ControladorScsi.VIRTIO_SINGLE
    assert isinstance(p.cfg.detalle_origen, DetalleImportacion)


def test_proponer_no_modifica_la_configuracion_base():
    base = cfg_formulario(nombre="mio", memoria_mib=777)
    antes = repr(base)
    dominio = dominio_desde_texto(xml_minimo(disco_xml()))
    proponer(dominio, base, inventario_d(X86), "pve1")
    assert repr(base) == antes


def test_proponer_conserva_lo_que_libvirt_no_trae_del_formulario_base():
    base = cfg_formulario(nombre="mio", vmid=321, etiquetas=("prod",))
    p = proponer(dominio_desde_texto(xml_minimo(disco_xml())), base, inventario_d(X86), "pve1")
    assert p.cfg.vmid == 321 and "prod" in p.cfg.etiquetas


def test_las_claves_de_fila_son_las_documentadas():
    patron = re.compile(
        r"nombre|tipo_dominio|tipo_os|arquitectura(\.i686)?|memoria(\.actual)?|"
        r"cpu(\.(topologia|hilos|actual|banderas))?|tipo_so|firmware(\.claves)?|nvram|tpm|agente|"
        r"disco\[\d+\](\.(bus|backing|opciones))?|disco_origen\[\d+\]|cdrom\[\d+\]|"
        r"discos\.\w+|controlador|red\[\d+\](\.(modelo|vlan|mtu|limite|mac|virtualport|extra))?|"
        r"dispositivos|pantalla|otros|desconocidos|contrasenas"
    )
    for nombre in ("linux_bios.xml", "windows11_uefi_tpm.xml", "varios_discos_nic.xml",
                   "backing_store.xml", "con_passwd.xml", "sin_discos.xml"):  # fmt: skip
        for f in proponer_de(nombre, inv=inventario_d(X86)).filas:
            assert patron.fullmatch(f.campo), (nombre, f.campo)


def test_cada_fila_con_problema_trae_un_estado_y_codigo_v_d_conocido():
    for nombre in (
        "linux_bios.xml",
        "windows11_uefi_tpm.xml",
        "varios_discos_nic.xml",
        "backing_store.xml",
    ):
        for f in proponer_de(nombre, inv=inventario_d(X86)).filas:
            assert isinstance(f.estado, EstadoFila)
            if f.problema is not None:
                assert f.problema.codigo.startswith(("V-D", "V-0"))
                assert all(isinstance(v, str) for v in f.problema.params.values())


def test_los_params_de_las_filas_estan_saneados():
    nombre = "x<b>&y"  # el XML ya sanea al leer; aquí se fuerza un valor sin sanear
    import dataclasses

    from proxlaunch.nucleo.libvirt.modelos import DominioLibvirt  # noqa: F401

    d = dominio_desde_texto(xml_minimo(disco_xml(), tipo="xen"))
    d = dataclasses.replace(d, tipo_dominio=nombre)
    p = proponer(d, cfg_formulario(), inventario_d(X86), "pve1")
    assert not set("<>&") & set(fila(p, "tipo_dominio").problema.params["tipo"])


def test_las_cpus_de_nodos_con_modelos_personalizados_se_reconocen_por_nodo():
    import dataclasses

    from proxlaunch.nucleo.hardware_cluster.modelos import InfoHardwareCluster, ModeloCpu

    inv = inventario_d(X86)
    hw = InfoHardwareCluster(cpus={"pve1": (ModeloCpu("custom-mio", True),)})
    inv.catalogo = dataclasses.replace(inv.catalogo, hardware=hw)
    xml = _con_cpu("<cpu mode='custom'><model>custom-mio</model></cpu>")
    p = _p(xml, inv=inv)
    assert p.cfg.tipo_cpu == "custom-mio" and fila(p, "cpu").problema is None


def test_codigos_de_un_dumpxml_completo_son_los_esperados():
    c = codigos(proponer_de("windows11_uefi_tpm.xml", inv=inventario_d(X86)))
    assert {"V-D30", "V-D31", "V-D35", "V-D36", "V-D41"} <= c
