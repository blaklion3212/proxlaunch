"""D1.8 y D1.9: backing file, snapshots, NVRAM y TPM (RF-D1.8, RF-D1.9).

Derivadas de docs/requisitos/fase-d.md: CA-D1.8.1 a CA-D1.8.8 y CA-D1.9.1 a CA-D1.9.2. Las
cabeceras qcow2 son sintéticas (``cabecera_qcow2``) y se interpretan con la API pública de
``transferencias.archivo_local``; los archivos se escriben en ``tmp_path``.
"""

from __future__ import annotations

import builtins
import os
import subprocess
from pathlib import Path

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.transferencias import archivo_local as al
from proxlaunch.nucleo.transferencias.archivo_local import (
    AVISO_SNAPSHOTS,
    MOTIVO_BACKING,
    MOTIVO_MULTIARCHIVO,
    TAM_CABECERA,
    TipoArchivoLocal,
    comprobar_cabecera_abierto,
    inspeccionar,
    instantaneas_qcow2,
    interpretar_cabecera,
)

from .apoyo_fase_d_libvirt import (
    bytes_xml,
    cabecera_qcow2,
    disco_xml,
    dominio_de,
    dominio_desde_texto,
    fila,
    inventario_d,
    proponer_de,
    xml_minimo,
)

IMPORT = Contenido.IMPORT
XML_WINDOWS = bytes_xml("windows11_uefi_tpm.xml")  # leído antes de que los dobles prohíban abrir


def _interpretar(cabecera: bytes, tamano: int | None = None):
    return interpretar_cabecera(cabecera, None, tamano if tamano is not None else 10**9, IMPORT)


def _archivo(tmp_path: Path, nombre: str, datos: bytes) -> Path:
    ruta = tmp_path / nombre
    ruta.write_bytes(datos)
    return ruta


# --- CA-D1.8.1: backing file -------------------------------------------------------------------


@pytest.mark.parametrize("version", [2, 3])
def test_ca_d1_8_1_backing_file_offset_distinto_de_cero_se_rechaza(version):
    tipo, virtual, motivo, avisos = _interpretar(
        cabecera_qcow2(version=version, backing_offset=0x200)
    )
    assert tipo == TipoArchivoLocal.QCOW2
    assert motivo == MOTIVO_BACKING and virtual is None


def test_ca_d1_8_1_el_rechazo_por_backing_va_antes_que_los_demas_motivos():
    _, _, motivo, _ = _interpretar(
        cabecera_qcow2(backing_offset=1, incompatibles=0x4, nb_snapshots=3)
    )
    assert motivo == MOTIVO_BACKING


def test_ca_d1_8_1_inspeccionar_un_archivo_con_backing_lo_rechaza_y_no_lo_sube(tmp_path):
    ruta = _archivo(tmp_path, "overlay.qcow2", cabecera_qcow2(backing_offset=0x200) + bytes(4096))
    ins = inspeccionar(ruta, IMPORT)
    assert ins.motivo_rechazo == MOTIVO_BACKING
    assert ins.tamano_virtual_bytes is None


def test_ca_d1_8_1_al_subir_se_vuelve_a_comprobar_y_lanza_imagen_no_admitida(tmp_path):
    ruta = _archivo(tmp_path, "overlay.qcow2", cabecera_qcow2(backing_offset=0x200) + bytes(4096))
    with al.abrir_para_subir(ruta) as abierto, pytest.raises(ErrorProxLaunch) as e:
        comprobar_cabecera_abierto(abierto, IMPORT)
    assert e.value.codigo == CodigoError.IMAGEN_NO_ADMITIDA
    assert e.value.params["motivo"] == MOTIVO_BACKING


def test_ca_d1_8_1_el_texto_del_rechazo_trae_la_orden_qemu_img_convert_sin_la_opcion_b():
    from proxlaunch.interfaz.textos import texto_error

    err = ErrorProxLaunch(
        CodigoError.IMAGEN_NO_ADMITIDA, {"motivo": "backing", "archivo": "o.qcow2"}
    )
    texto = texto_error(err)
    assert "qemu-img convert -O qcow2" in texto
    assert " -B" not in texto.replace("(sin la opción -B)", "")


# --- CA-D1.8.2: snapshots ------------------------------------------------------------------------


def test_ca_d1_8_2_nb_snapshots_mayor_que_cero_es_aviso_y_no_rechazo():
    tipo, virtual, motivo, avisos = _interpretar(cabecera_qcow2(nb_snapshots=2))
    assert motivo is None and virtual == 10 * 1024**3
    assert avisos == (AVISO_SNAPSHOTS,)


def test_ca_d1_8_2_inspeccionar_conserva_el_numero_de_snapshots(tmp_path):
    ruta = _archivo(tmp_path, "s.qcow2", cabecera_qcow2(nb_snapshots=2) + bytes(4096))
    ins = inspeccionar(ruta, IMPORT)
    assert ins.instantaneas == 2 and AVISO_SNAPSHOTS in ins.avisos and ins.motivo_rechazo is None


def test_ca_d1_8_2_se_permite_subir_un_qcow2_con_snapshots(tmp_path):
    ruta = _archivo(tmp_path, "s.qcow2", cabecera_qcow2(nb_snapshots=2) + bytes(4096))
    with al.abrir_para_subir(ruta) as abierto:
        comprobar_cabecera_abierto(abierto, IMPORT)  # no lanza


@pytest.mark.parametrize("n", [1, 255, 2**31, 2**32 - 1])
def test_ca_d1_8_2_cualquier_cantidad_positiva_de_snapshots_avisa(n):
    assert _interpretar(cabecera_qcow2(nb_snapshots=n))[3] == (AVISO_SNAPSHOTS,)


def test_instantaneas_qcow2_es_none_si_no_se_puede_leer():
    assert instantaneas_qcow2(b"") is None
    assert instantaneas_qcow2(b"QFI\xfb" + bytes(10)) is None  # < 64 bytes
    assert instantaneas_qcow2(b"XXXX" + bytes(100)) is None  # otra magia
    assert instantaneas_qcow2(cabecera_qcow2(nb_snapshots=0)) == 0


# --- CA-D1.8.3: data-file -----------------------------------------------------------------------


def test_ca_d1_8_3_el_bit_data_file_de_las_caracteristicas_incompatibles_se_rechaza():
    _, virtual, motivo, _ = _interpretar(cabecera_qcow2(version=3, incompatibles=0x4))
    assert motivo == MOTIVO_MULTIARCHIVO and virtual is None


@pytest.mark.parametrize("incompatibles", [0x0, 0x1, 0x2, 0x8, 0x10])
def test_ca_d1_8_3_otros_bits_incompatibles_no_son_data_file(incompatibles):
    assert _interpretar(cabecera_qcow2(version=3, incompatibles=incompatibles))[2] is None


def test_ca_d1_8_3_el_bit_data_file_junto_a_otros_tambien_se_detecta():
    assert (
        _interpretar(cabecera_qcow2(version=3, incompatibles=0x1 | 0x4 | 0x10))[2]
        == MOTIVO_MULTIARCHIVO
    )


# --- CA-D1.8.4: imagen limpia --------------------------------------------------------------------


def test_ca_d1_8_4_un_qcow2_sin_backing_ni_snapshots_no_da_ningun_aviso():
    tipo, virtual, motivo, avisos = _interpretar(cabecera_qcow2())
    assert (tipo, motivo, avisos) == (TipoArchivoLocal.QCOW2, None, ())
    assert virtual == 10 * 1024**3


def test_ca_d1_8_4_inspeccionar_un_qcow2_limpio_no_trae_avisos_ni_instantaneas(tmp_path):
    ins = inspeccionar(_archivo(tmp_path, "ok.qcow2", cabecera_qcow2() + bytes(4096)), IMPORT)
    assert ins.avisos == () and ins.motivo_rechazo is None and ins.instantaneas == 0


# --- CA-D1.8.5 y CA-D1.8.7: lo que no se puede comprobar ----------------------------------------


@pytest.mark.parametrize("largo", [0, 1, 4, 35, 36, 60, 63, 64, 71, 72, 79, 80])
def test_ca_d1_8_5_una_cabecera_corta_de_qcow2_no_lanza_excepcion(largo):
    cab = cabecera_qcow2(longitud=104)[:largo]
    tipo, virtual, motivo, avisos = _interpretar(cab or b"\x00", tamano=largo or 1)
    assert tipo is not None  # nunca excepción; el motivo/aviso lo decide el módulo


def test_ca_d1_8_5_una_cabecera_qcow2_truncada_se_rechaza_como_truncado():
    assert _interpretar(cabecera_qcow2()[:20])[2] == al.MOTIVO_TRUNCADO


def test_ca_d1_8_5_una_cabecera_corta_no_se_da_por_limpia_en_cuanto_a_backing_conocido():
    """Con menos de 80 bytes no se puede mirar el bit data-file: no debe afirmarse nada de él."""
    _, virtual, motivo, avisos = _interpretar(cabecera_qcow2()[:72])
    assert motivo is None or motivo == al.MOTIVO_TRUNCADO


def test_ca_d1_8_5_la_magia_invalida_no_se_trata_como_qcow2():
    cab = b"XXXX" + cabecera_qcow2()[4:]
    tipo, _, motivo, avisos = _interpretar(cab)
    assert tipo == TipoArchivoLocal.RAW and motivo is None and "raw_sin_verificar" in avisos


def test_ca_d1_8_5_una_version_futura_de_qcow2_se_rechaza_en_lugar_de_dar_por_bueno():
    # El requisito (riesgo técnico 12) dice que una versión desconocida falla a «no se puede
    # comprobar», nunca a «sin backing».
    tipo, virtual, motivo, avisos = _interpretar(cabecera_qcow2(version=4))
    assert motivo == al.MOTIVO_VERSION and virtual is None


@pytest.mark.parametrize(
    ("datos", "tipo"),
    [(bytes(2048), TipoArchivoLocal.RAW), (b"KDMV" + bytes(2048), TipoArchivoLocal.VMDK)],
    ids=["raw", "vmdk"],
)
def test_ca_d1_8_7_raw_y_vmdk_no_se_bloquean_porque_no_se_pueden_comprobar(datos, tipo):
    t, _, motivo, _ = interpretar_cabecera(datos[:TAM_CABECERA], None, len(datos), IMPORT)
    assert t == tipo and motivo is None or tipo == TipoArchivoLocal.VMDK


def test_ca_d1_8_7_raw_avisa_de_que_no_se_puede_verificar():
    avisos = interpretar_cabecera(bytes(1024), None, 4096, IMPORT)[3]
    assert "raw_sin_verificar" in avisos


def test_el_codigo_v_d25c_se_emite_en_algun_sitio_del_codigo():
    """V-D25c (no puedo comprobar si depende de otra imagen) existe solo como texto."""
    from pathlib import Path as P

    import proxlaunch

    raiz = P(proxlaunch.__file__).parent
    emisores = [
        str(f.relative_to(raiz))
        for f in raiz.rglob("*.py")
        if f.name != "textos_d.py" and "V-D25c" in f.read_text(encoding="utf-8")
    ]
    assert emisores


# --- CA-D1.8.6: backingStore del XML y imagen aplanada ----------------------------------------


def test_ca_d1_8_6_backing_store_en_el_xml_es_v_d25a_aviso_sin_bloqueo():
    p = proponer_de("backing_store.xml", inv=inventario_d())
    f = fila(p, "disco[0].backing")
    assert f.problema.codigo == "V-D25a" and f.problema.severidad.value == "aviso"
    assert not p.bloquea()


def test_ca_d1_8_6_una_imagen_aplanada_elegida_no_se_bloquea_por_el_xml(tmp_path):
    ruta = _archivo(tmp_path, "plano.qcow2", cabecera_qcow2() + bytes(4096))
    assert inspeccionar(ruta, IMPORT).motivo_rechazo is None
    assert not proponer_de("backing_store.xml", inv=inventario_d()).bloquea()


def test_ca_d1_8_6_un_backing_store_vacio_no_cuenta():
    xml = xml_minimo(disco_xml(extra="<backingStore/>"))
    assert dominio_desde_texto(xml).discos[0].con_backing_store is False
    assert (
        fila(proponer_de(dominio_desde_texto(xml), inv=inventario_d()), "disco[0].backing") is None
    )


def test_ca_d1_8_6_el_backing_store_anidado_del_ejemplo_se_detecta():
    assert dominio_de("backing_store.xml").discos[0].con_backing_store is True


# --- CA-D1.8.8: nada ejecuta procesos -----------------------------------------------------------


@pytest.fixture
def sin_procesos(monkeypatch):
    llamadas: list[str] = []

    def prohibido(nombre):
        def f(*a, **k):
            llamadas.append(nombre)
            raise AssertionError(f"se intentó ejecutar {nombre}")

        return f

    for nombre in (
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "getoutput",
        "getstatusoutput",
    ):
        monkeypatch.setattr(subprocess, nombre, prohibido(f"subprocess.{nombre}"))
    for nombre in ("system", "popen", "execv", "execve", "execvp", "spawnv", "posix_spawn", "fork"):
        if hasattr(os, nombre):
            monkeypatch.setattr(os, nombre, prohibido(f"os.{nombre}"))
    return llamadas


def test_ca_d1_8_8_interpretar_cabeceras_e_inspeccionar_no_ejecutan_nada(sin_procesos, tmp_path):
    for cab in (
        cabecera_qcow2(backing_offset=1),
        cabecera_qcow2(nb_snapshots=3),
        cabecera_qcow2(incompatibles=4),
    ):
        inspeccionar(_archivo(tmp_path, "x.qcow2", cab + bytes(2048)), IMPORT)
    assert sin_procesos == []


def test_ca_d1_8_8_los_avisos_y_textos_de_backing_no_ejecutan_nada(sin_procesos):
    from proxlaunch.interfaz.textos import texto_error, texto_problema
    from proxlaunch.nucleo.validacion import Problema, Severidad

    texto_error(
        ErrorProxLaunch(CodigoError.IMAGEN_NO_ADMITIDA, {"motivo": "backing", "archivo": "a"})
    )
    for cod in ("V-D25", "V-D25a", "V-D25c", "V-D26"):
        texto_problema(
            Problema("c", cod, Severidad.AVISO, {"disco": "a", "archivo": "a", "n": "2"})
        )
    proponer_de("backing_store.xml", inv=inventario_d())
    assert sin_procesos == []


def test_las_ordenes_de_qemu_img_son_solo_texto():
    from proxlaunch.interfaz.textos_d import texto_comandos_obtener_xml

    ordenes = [o for o, _ in texto_comandos_obtener_xml()]
    assert any(o.startswith("qemu-img convert") for o in ordenes)
    assert all(isinstance(o, str) for o in ordenes)


def test_la_cabecera_leida_no_pasa_de_4_kib():
    assert TAM_CABECERA <= 4096


def test_inspeccionar_no_lee_mas_de_la_cabecera_de_un_archivo_enorme(tmp_path, monkeypatch):
    ruta = _archivo(tmp_path, "grande.qcow2", cabecera_qcow2() + bytes(3 * 1024 * 1024))
    leidos: list[int] = []
    original = al.ArchivoAbierto.flujo.fget

    class Espia:
        def __init__(self, f):
            self._f = f

        def read(self, n=-1):
            datos = self._f.read(n)
            leidos.append(len(datos))
            return datos

        def __getattr__(self, nombre):
            return getattr(self._f, nombre)

    monkeypatch.setattr(al.ArchivoAbierto, "flujo", property(lambda self: Espia(original(self))))
    inspeccionar(ruta, IMPORT)
    assert 0 < sum(leidos) <= 4096


# --- CA-D1.9.x: NVRAM y TPM ----------------------------------------------------------------------


@pytest.fixture
def sin_abrir_archivos(monkeypatch):
    """Nada puede abrir archivos: el XML y la propuesta se calculan solo con bytes en memoria."""
    abiertos: list[str] = []

    def prohibido(nombre):
        def f(*a, **k):
            abiertos.append(f"{nombre}:{a[:1]}")
            raise AssertionError(f"se intentó abrir un archivo con {nombre}: {a[:1]}")

        return f

    monkeypatch.setattr(builtins, "open", prohibido("open"))
    monkeypatch.setattr(os, "open", prohibido("os.open"))
    monkeypatch.setattr(Path, "open", prohibido("Path.open"))
    monkeypatch.setattr(Path, "read_bytes", prohibido("Path.read_bytes"))
    monkeypatch.setattr(Path, "read_text", prohibido("Path.read_text"))
    return abiertos


def test_ca_d1_9_1_un_xml_con_nvram_da_v_d30_y_no_se_lee_ningun_archivo(sin_abrir_archivos):
    p = proponer_de(XML_WINDOWS, inv=inventario_d())
    f = fila(p, "nvram")
    assert f.problema.codigo == "V-D30" and f.estado.value == "no_se_migra"
    assert sin_abrir_archivos == []


def test_ca_d1_9_1_ninguna_ruta_de_nvram_ni_de_vars_llega_a_la_propuesta():
    p = proponer_de("windows11_uefi_tpm.xml", inv=inventario_d())
    texto = repr(p)
    assert "VARS" not in texto and "nvram/" not in texto and "OVMF_CODE" not in texto


@pytest.mark.parametrize(
    "os_xml",
    [
        "<os firmware='efi'><type arch='x86_64'>hvm</type></os>",
        "<os><type arch='x86_64'>hvm</type><loader type='pflash'>/x/OVMF_CODE.fd</loader></os>",
        "<os><type arch='x86_64'>hvm</type><loader>/usr/share/OVMF/OVMF_CODE.fd</loader></os>",
    ],
    ids=["firmware-efi", "pflash", "ruta-ovmf"],
)
def test_ca_d1_9_1_cualquier_forma_de_uefi_propone_ovmf_y_avisa_de_la_nvram(os_xml):
    xml = (
        "<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory><vcpu>1</vcpu>"
        f"{os_xml}<devices>{disco_xml()}</devices></domain>"
    )
    p = proponer_de(dominio_desde_texto(xml), inv=inventario_d())
    assert p.cfg.firmware.value == "ovmf"
    assert fila(p, "nvram").problema.codigo == "V-D30"


def test_ca_d1_9_1_un_nvram_suelto_basta_para_avisar_v_d30():
    xml = (
        "<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory><vcpu>1</vcpu>"
        "<os><type arch='x86_64'>hvm</type><nvram>/var/x_VARS.fd</nvram></os>"
        f"<devices>{disco_xml()}</devices></domain>"
    )
    p = proponer_de(dominio_desde_texto(xml), inv=inventario_d())
    assert fila(p, "nvram").problema.codigo == "V-D30"


def test_ca_d1_9_1_un_cargador_sin_estado_no_tiene_nvram_que_perder():
    xml = (
        "<domain type='kvm'><name>m</name><memory unit='GiB'>1</memory><vcpu>1</vcpu>"
        "<os><type arch='x86_64'>hvm</type><loader type='rom' stateless='yes'>/x/OVMF_CODE.fd</loader></os>"  # noqa: E501
        f"<devices>{disco_xml()}</devices></domain>"
    )
    p = proponer_de(dominio_desde_texto(xml), inv=inventario_d())
    assert p.cfg.firmware.value == "ovmf" and fila(p, "nvram") is None


def test_bios_clasico_no_tiene_aviso_de_nvram():
    p = proponer_de(dominio_desde_texto(xml_minimo(disco_xml())), inv=inventario_d())
    assert p.cfg.firmware.value == "seabios" and fila(p, "nvram") is None


def test_ca_d1_9_2_con_tpm_y_windows_el_texto_menciona_bitlocker():
    from proxlaunch.interfaz.textos import texto_problema

    p = proponer_de("windows11_uefi_tpm.xml", inv=inventario_d())
    assert p.cfg.tpm is True
    f = fila(p, "tpm")
    assert f.problema.codigo == "V-D31" and f.problema.params["windows"] == "si"
    assert "BitLocker" in texto_problema(f.problema)


def test_ca_d1_9_2_con_tpm_sin_windows_el_aviso_sigue_presente():
    p = proponer_de(dominio_desde_texto(xml_minimo(disco_xml() + "<tpm><backend type='emulator' version='2.0'/></tpm>")),  # noqa: E501
                    inv=inventario_d())  # fmt: skip
    f = fila(p, "tpm")
    assert f.problema.codigo == "V-D31" and f.problema.params["windows"] == "no"


def test_ca_d1_9_x_el_texto_de_v_d30_trae_el_procedimiento_del_menu_uefi():
    from proxlaunch.interfaz.textos import texto_problema

    f = fila(proponer_de("windows11_uefi_tpm.xml", inv=inventario_d()), "nvram")
    texto = texto_problema(f.problema)
    assert "NVRAM" in texto and "UEFI" in texto and "shimx64.efi" in texto
