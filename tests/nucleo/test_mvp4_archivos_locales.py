"""MVP 4: cuerpo multipart en streaming, archivo local, URLs/checksums y medición de progreso.

Requisitos: RNF-O01 (memoria), RNF-O02 (progreso), RNF-O03 (cancelación), RNF-O05 (URLs y
archivos locales), RF-O09 (CA-O09.1, O09.8), RF-O11 (V-O11, V-O12), RF-O16 (V-O10, CA-O16.1..O16.5),
INV-O5 (solo lectura y fstat), INV-O6 (repr sin URL ni checksum), §11 casos límite 1, 2 y 6.
"""

import hashlib
import io
import os
import random
import stat
import struct
import threading
import tracemalloc

import pytest

from proxlaunch.nucleo.api.multipart import CuerpoMultipart, ParteArchivo, SubidaCancelada
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.origen.constantes import BLOQUE_ENVIO, CHUNK_SUBIDA, MAX_LONG_URL
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.transferencias.archivo_local import (
    AVISO_NO_ISO9660,
    AVISO_RAW_SIN_VERIFICAR,
    DESPLAZAMIENTO_ISO9660,
    MOTIVO_BACKING,
    MOTIVO_CIFRADO,
    MOTIVO_MULTIARCHIVO,
    MOTIVO_OVA,
    MOTIVO_TRUNCADO,
    MOTIVO_VACIO,
    MOTIVO_VERSION,
    TAM_CABECERA,
    TipoArchivoLocal,
    abrir_para_subir,
    calcular_sha256,
    inspeccionar,
    interpretar_cabecera,
)
from proxlaunch.nucleo.transferencias.progreso import MedidorProgreso, progreso_de_log
from proxlaunch.nucleo.transferencias.url import (
    AlgoritmoChecksum,
    host_y_archivo,
    ocultar_url,
    validar_checksum,
    validar_url,
)

# --- Cuerpo multipart (RF-O09, RNF-O01) -----------------------------------------------------------


def _cuerpo(datos: bytes, campos=None, **kw) -> CuerpoMultipart:
    campos = campos or {"content": "iso", "checksum-algorithm": "sha256", "checksum": "ab" * 32}
    return CuerpoMultipart(
        campos, ParteArchivo("alpine.iso", len(datos), io.BytesIO(datos)), frontera="FRONTERA", **kw
    )


def test_ca_o09_1_cuerpo_multipart_exacto_orden_de_partes_y_content_type_de_la_parte():
    crudo = b"".join(_cuerpo(b"HOLA"))
    esperado = (
        b"--FRONTERA\r\n"
        b'Content-Disposition: form-data; name="content"\r\n\r\niso\r\n'
        b"--FRONTERA\r\n"
        b'Content-Disposition: form-data; name="checksum-algorithm"\r\n\r\nsha256\r\n'
        b"--FRONTERA\r\n"
        b'Content-Disposition: form-data; name="checksum"\r\n\r\n' + b"ab" * 32 + b"\r\n"
        b"--FRONTERA\r\n"
        b'Content-Disposition: form-data; name="filename"; filename="alpine.iso"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        b"HOLA\r\n--FRONTERA--\r\n"
    )
    assert crudo == esperado  # el archivo va al final, los campos antes (I4-§B)


@pytest.mark.parametrize(
    "tamano", [0, 1, 1000, BLOQUE_ENVIO, BLOQUE_ENVIO + 1, 3 * CHUNK_SUBIDA + 7]
)
def test_content_length_es_exacto_para_cualquier_tamano(tamano):
    datos = os.urandom(tamano)
    cuerpo = _cuerpo(datos)
    crudo = b"".join(cuerpo)
    assert len(crudo) == len(cuerpo)
    assert datos in crudo


def test_el_tipo_de_contenido_lleva_la_frontera_y_la_frontera_es_aleatoria_por_defecto():
    assert _cuerpo(b"x").tipo_contenido == "multipart/form-data; boundary=FRONTERA"
    a = CuerpoMultipart({}, ParteArchivo("a.iso", 1, io.BytesIO(b"x")))
    b = CuerpoMultipart({}, ParteArchivo("a.iso", 1, io.BytesIO(b"x")))
    assert a.tipo_contenido != b.tipo_contenido


def test_rnf_o01_lee_en_bloques_acotados_y_entrega_trozos_de_tam_envio():
    class Espia(io.BytesIO):
        lecturas: list[int] = []

        def read(self, n=-1):
            Espia.lecturas.append(n)
            return super().read(n)

    Espia.lecturas = []
    datos = os.urandom(3 * CHUNK_SUBIDA + 5)
    cuerpo = CuerpoMultipart(
        {},
        ParteArchivo("a.iso", len(datos), Espia(datos)),
        tam_lectura=CHUNK_SUBIDA,
        tam_envio=BLOQUE_ENVIO,
    )
    trozos = list(cuerpo)
    assert all(n > 0 and n <= CHUNK_SUBIDA for n in Espia.lecturas)  # nunca read() sin tope
    assert max(len(t) for t in trozos) <= max(BLOQUE_ENVIO, len(trozos[0]), len(trozos[-1]))
    cuerpo_del_archivo = [t for t in trozos[1:-1]]
    assert all(len(t) <= BLOQUE_ENVIO for t in cuerpo_del_archivo)


def test_cabecera_y_cierre_se_entregan_aparte_para_que_el_archivo_no_se_copie_entero():
    trozos = list(_cuerpo(b"A" * 10, tam_envio=4))
    assert trozos[0].startswith(b"--FRONTERA") and trozos[-1].endswith(b"--FRONTERA--\r\n")
    assert [len(t) for t in trozos[1:-1]] == [4, 4, 2]


def test_rnf_o01_ocho_gib_ficticios_no_aumentan_la_memoria_mas_de_64_mib():
    """El flujo es ficticio (ceros generados al vuelo); ni el cuerpo ni la prueba guardan nada."""
    total = 8 * 1024**3

    class Ceros:
        def __init__(self):
            self.restante = total
            self.bloque = bytes(CHUNK_SUBIDA)

        def read(self, n=-1):
            n = min(n, self.restante)
            self.restante -= n
            return self.bloque[:n] if n <= len(self.bloque) else bytes(n)

    try:
        import resource

        rss_antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:  # Windows: solo tracemalloc
        resource = None
    vistos = 0
    tracemalloc.start()
    try:
        cuerpo = CuerpoMultipart({}, ParteArchivo("a.iso", total, Ceros()), tam_envio=CHUNK_SUBIDA)
        for trozo in cuerpo:
            vistos += len(trozo)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert vistos == len(cuerpo)
    assert pico <= 64 * 1024**2, f"pico de {pico / 1024**2:.1f} MiB"
    if resource is not None:
        aumento_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_antes
        assert aumento_kib <= 64 * 1024  # RSS (KiB en Linux)


def test_rnf_o02_el_progreso_entrega_bytes_del_archivo_y_total_sin_contar_cabeceras():
    eventos: list[tuple[int, int]] = []
    datos = os.urandom(10_000)
    list(_cuerpo(datos, tam_envio=4096, al_progresar=lambda h, t: eventos.append((h, t))))
    assert eventos == [(4096, 10_000), (8192, 10_000), (10_000, 10_000)]


def test_al_leer_recibe_todos_los_bytes_del_archivo_para_recalcular_el_hash_al_vuelo():
    datos = os.urandom(300_000)
    visto = hashlib.sha256()
    list(_cuerpo(datos, al_leer=visto.update))
    assert visto.hexdigest() == hashlib.sha256(datos).hexdigest()


def test_rnf_o03_cancelar_interrumpe_entre_trozos_con_subida_cancelada():
    cancelado = threading.Event()
    cuerpo = _cuerpo(os.urandom(100_000), tam_envio=1000, cancelado=cancelado,
                     al_progresar=lambda h, t: cancelado.set() if h >= 3000 else None)  # fmt: skip
    entregados = 0
    with pytest.raises(SubidaCancelada):
        for t in cuerpo:
            entregados += len(t)
    assert cuerpo.enviados <= 3000 + 1000 and entregados < 100_000


def test_cancelar_antes_de_empezar_no_entrega_ni_la_cabecera():
    ev = threading.Event()
    ev.set()
    assert list(_enganchar(_cuerpo(b"x", cancelado=ev))) == ["cancelado"]


def _enganchar(it):
    try:
        yield from it
    except SubidaCancelada:
        yield "cancelado"


def test_subida_cancelada_no_es_un_oserror_para_que_urllib3_no_la_envuelva():
    assert not issubclass(SubidaCancelada, OSError)


def test_ca_o09_8_el_archivo_que_se_acorta_aborta_con_archivo_cambio_en_vez_de_colgar():
    cuerpo = CuerpoMultipart({}, ParteArchivo("a.iso", 1000, io.BytesIO(b"x" * 400)))
    with pytest.raises(ErrorProxLaunch) as e:
        list(cuerpo)
    assert e.value.codigo == CodigoError.ARCHIVO_CAMBIO


@pytest.mark.parametrize("nombre", ['a".iso', "a\r\nX-Inyectada: 1.iso", "a\n.iso", "a\x00.iso"])
def test_inyeccion_de_cabeceras_por_el_nombre_de_archivo_se_rechaza(nombre):
    with pytest.raises(ValueError):
        CuerpoMultipart({}, ParteArchivo(nombre, 1, io.BytesIO(b"x")))


def test_inyeccion_por_campos_o_tipo_se_rechaza():
    p = ParteArchivo("a.iso", 1, io.BytesIO(b"x"))
    for campos in ({'con"tent': "iso"}, {"content": "iso\r\nX: 1"}, {"a\nb": "x"}):
        with pytest.raises(ValueError):
            CuerpoMultipart(campos, p)
    with pytest.raises(ValueError):
        CuerpoMultipart({}, ParteArchivo("a.iso", 1, io.BytesIO(b"x"), tipo="x\r\ny"))
    with pytest.raises(ValueError):
        CuerpoMultipart({}, ParteArchivo("a.iso", -1, io.BytesIO(b"")))
    with pytest.raises(ValueError):
        CuerpoMultipart({}, p, tam_lectura=0)


# --- Archivo local: cabeceras (V-O10, CA-O16.1..O16.5) --------------------------------------------


def _qcow2(version=3, virtual=2 * 1024**3, backing=0, crypt=0, largo=104) -> bytes:
    h = bytearray(largo)
    h[0:4] = b"QFI\xfb"
    struct.pack_into(">I", h, 4, version)
    struct.pack_into(">Q", h, 8, backing)
    struct.pack_into(">Q", h, 24, virtual)
    struct.pack_into(">I", h, 32, crypt)
    return bytes(h)


def _vmdk(sectores=4_194_304) -> bytes:
    h = bytearray(512)
    h[0:4] = b"KDMV"
    struct.pack_into("<Q", h, 12, sectores)
    return bytes(h)


def _tipo(cab, contenido=Contenido.IMPORT, tamano=10**6, firma=None):
    return interpretar_cabecera(cab, firma, tamano, contenido)


@pytest.mark.parametrize("version", [2, 3])
def test_ca_o16_1_qcow2_v2_y_v3_se_aceptan_y_se_lee_el_tamano_virtual(version):
    tipo, virtual, motivo, avisos = _tipo(_qcow2(version=version))
    assert (tipo, virtual, motivo, avisos) == (TipoArchivoLocal.QCOW2, 2 * 1024**3, None, ())


@pytest.mark.parametrize(
    ("cab", "motivo"),
    [
        (_qcow2(version=1), MOTIVO_VERSION),
        (_qcow2(version=4), MOTIVO_VERSION),
        (_qcow2(backing=512), MOTIVO_BACKING),  # CA-O16.2
        (_qcow2(crypt=1), MOTIVO_CIFRADO),
        (_qcow2()[:20], MOTIVO_TRUNCADO),  # §11.2: truncado en 20 bytes
        (_qcow2(virtual=0), MOTIVO_TRUNCADO),
    ],
)
def test_ca_o16_2_qcow2_con_dependencias_cifrado_o_truncado_se_rechaza_antes_de_subir(cab, motivo):
    tipo, virtual, rechazo, _ = _tipo(cab)
    assert tipo == TipoArchivoLocal.QCOW2 and virtual is None and rechazo == motivo


def test_qcow2_con_archivo_de_datos_externo_se_rechaza():
    cab = bytearray(_qcow2(version=3, largo=104))
    struct.pack_into(">Q", cab, 72, 0x4)  # incompatible_features: external data file
    assert _tipo(bytes(cab))[2] == MOTIVO_MULTIARCHIVO


def test_qcow2_con_tamano_virtual_enorme_no_falla():
    assert _tipo(_qcow2(virtual=2**62))[1] == 2**62


def test_ca_o16_4_vmdk_monolitico_lee_la_capacidad_en_sectores_de_512():
    assert _tipo(_vmdk(4_194_304)) == (TipoArchivoLocal.VMDK, 4_194_304 * 512, None, ())
    assert _tipo(_vmdk(0))[2] == MOTIVO_TRUNCADO
    assert _tipo(b"KDMV")[2] == MOTIVO_TRUNCADO


def test_ca_o16_2_vmdk_de_descriptor_de_texto_es_multiarchivo():
    cab = b"# Disk DescriptorFile\nversion=1\nCID=fffffffe\n"
    assert _tipo(cab)[:3] == (TipoArchivoLocal.VMDK, None, MOTIVO_MULTIARCHIVO)


def test_ca_o16_3_un_tar_ova_se_rechaza():
    cab = bytearray(512)
    cab[257:262] = b"ustar"
    assert _tipo(bytes(cab))[:3] == (TipoArchivoLocal.OVA, None, MOTIVO_OVA)


def test_ca_o16_1_ca_o16_5_raw_cualquier_contenido_con_aviso_y_tamano_virtual_el_del_archivo():
    tipo, virtual, motivo, avisos = _tipo(os.urandom(512), tamano=1024**2)
    assert (tipo, virtual, motivo, avisos) == (
        TipoArchivoLocal.RAW, 1024**2, None, (AVISO_RAW_SIN_VERIFICAR,),
    )  # fmt: skip
    assert _tipo(b"", tamano=0)[2] == MOTIVO_VACIO


def test_v_o10_iso_acepta_cualquier_contenido_y_avisa_si_no_hay_firma_iso9660():
    assert _tipo(b"lo que sea", Contenido.ISO, 100, b"CD001")[:3] == (
        TipoArchivoLocal.ISO,
        None,
        None,
    )
    tipo, _, rechazo, avisos = _tipo(b"x", Contenido.ISO, 100, b"zzzzz")
    assert (
        tipo == TipoArchivoLocal.DESCONOCIDO and rechazo is None and avisos == (AVISO_NO_ISO9660,)
    )
    assert _tipo(b"x", Contenido.ISO, 100, None)[3] == (AVISO_NO_ISO9660,)
    assert _tipo(_qcow2(), Contenido.ISO, 100, None)[2] is None  # un qcow2 como ISO: solo aviso


def test_rnf_o05_fuzz_de_10000_cabeceras_mutadas_sin_excepcion_no_controlada():
    rng = random.Random(20260514)
    bases = [_qcow2(2), _qcow2(3), _vmdk(), b"# Disk DescriptorFile\n" + bytes(40), bytes(300), b""]
    for _ in range(10_000):
        cab = bytearray(rng.choice(bases))
        for _ in range(rng.randint(0, 6)):
            if cab and rng.random() < 0.8:
                cab[rng.randrange(len(cab))] = rng.randrange(256)
            else:
                cab += bytes(rng.randrange(256) for _ in range(rng.randint(0, 40)))
        if rng.random() < 0.3:
            del cab[rng.randint(0, len(cab)) :]
        cab = bytes(cab)[: rng.choice([TAM_CABECERA, TAM_CABECERA + 500, 64])]
        contenido = rng.choice([Contenido.ISO, Contenido.IMPORT])
        firma = rng.choice([None, b"CD001", b"12345"])
        tipo, virtual, motivo, avisos = interpretar_cabecera(
            cab, firma, rng.choice([0, 1, 10**9]), contenido
        )
        assert isinstance(tipo, TipoArchivoLocal)
        assert virtual is None or (isinstance(virtual, int) and virtual >= 0)
        assert (motivo is None) or isinstance(motivo, str)
        assert isinstance(avisos, tuple)


def test_la_cabecera_leida_se_recorta_a_1_kib():
    cab = _qcow2() + b"\x00" * 5000
    assert interpretar_cabecera(cab, None, 10**6, Contenido.IMPORT)[0] == TipoArchivoLocal.QCOW2
    assert TAM_CABECERA == 1024 and DESPLAZAMIENTO_ISO9660 == 0x8001


# --- Archivo local: E/S (INV-O5, §11.1) -----------------------------------------------------------


def test_inspeccionar_un_qcow2_real_propone_la_extension_del_contenido(tmp_path):
    f = tmp_path / "disco.img"  # §11.1: un .img que en realidad es qcow2
    f.write_bytes(_qcow2() + bytes(1000))
    r = inspeccionar(f, Contenido.IMPORT)
    assert r.tipo == TipoArchivoLocal.QCOW2 and r.extension_propuesta == ".qcow2"  # DT-O12
    assert r.tamano_virtual_bytes == 2 * 1024**3 and r.motivo_rechazo is None
    assert r.nombre_local == "disco.img" and r.tamano_bytes == f.stat().st_size


def test_inspeccionar_iso_con_firma_en_0x8001(tmp_path):
    f = tmp_path / "sistema.iso"
    datos = bytearray(40_000)
    datos[DESPLAZAMIENTO_ISO9660 : DESPLAZAMIENTO_ISO9660 + 5] = b"CD001"
    f.write_bytes(bytes(datos))
    r = inspeccionar(f, Contenido.ISO)
    assert r.tipo == TipoArchivoLocal.ISO and r.avisos == () and r.extension_propuesta == ".iso"


def test_inspeccionar_iso_pequeno_o_sin_firma_avisa_pero_no_rechaza(tmp_path):
    f = tmp_path / "x.img"
    f.write_bytes(b"hola")
    r = inspeccionar(f, Contenido.ISO)
    assert r.motivo_rechazo is None and r.avisos == (AVISO_NO_ISO9660,)
    assert r.extension_propuesta == ".img"  # un .img es válido como ISO
    g = tmp_path / "otro.bin"
    g.write_bytes(b"hola")
    assert inspeccionar(g, Contenido.ISO).extension_propuesta == ".iso"


def test_inspeccionar_archivo_de_0_bytes_y_ova(tmp_path):
    vacio = tmp_path / "v.iso"
    vacio.write_bytes(b"")
    assert inspeccionar(vacio, Contenido.ISO).motivo_rechazo == MOTIVO_VACIO
    ova = tmp_path / "appliance.ova"
    ova.write_bytes(b"x" * 100)
    assert inspeccionar(ova, Contenido.IMPORT).motivo_rechazo == MOTIVO_OVA
    ovf = tmp_path / "appliance.ovf"
    ovf.write_bytes(b"<xml/>")
    assert inspeccionar(ovf, Contenido.IMPORT).motivo_rechazo == MOTIVO_OVA


def test_abrir_para_subir_archivo_de_1_byte_si_y_de_0_bytes_no(tmp_path):
    uno = tmp_path / "uno.iso"
    uno.write_bytes(b"x")
    with abrir_para_subir(uno) as a:
        assert a.huella.tamano == 1 and a.flujo.read() == b"x"
    cero = tmp_path / "cero.iso"
    cero.write_bytes(b"")
    with pytest.raises(ErrorProxLaunch) as e:
        abrir_para_subir(cero)
    assert (
        e.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO and e.value.params["motivo"] == "vacio"
    )


def test_rnf_o05_directorio_tuberia_y_dispositivo_no_son_archivos_regulares(tmp_path):
    with pytest.raises(ErrorProxLaunch) as e:
        abrir_para_subir(tmp_path)
    assert e.value.codigo in (CodigoError.ARCHIVO_NO_PERMITIDO, CodigoError.ARCHIVO_NO_ACCESIBLE)
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "tuberia"
        os.mkfifo(fifo)
        with pytest.raises(ErrorProxLaunch) as e:  # no se queda esperando a un escritor
            abrir_para_subir(fifo)
        assert e.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
        assert e.value.params["motivo"] == "no_regular"
    if os.path.exists("/dev/zero"):
        with pytest.raises(ErrorProxLaunch) as e:
            abrir_para_subir(type(tmp_path)("/dev/zero"))
        assert e.value.params["motivo"] == "no_regular"


def test_enlace_roto_y_archivo_inexistente_dan_no_accesible_sin_la_ruta_completa(tmp_path):
    roto = tmp_path / "enlace"
    os.symlink(tmp_path / "no_existe.iso", roto)
    for ruta in (roto, tmp_path / "nada.iso"):
        with pytest.raises(ErrorProxLaunch) as e:
            abrir_para_subir(ruta)
        assert (
            e.value.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
            and e.value.params["motivo"] == "no_existe"
        )
        assert str(tmp_path) not in repr(e.value.params) + e.value.detalle_tecnico  # INV-O6


def test_archivo_sin_permiso_de_lectura(tmp_path):
    f = tmp_path / "privado.iso"
    f.write_bytes(b"x")
    f.chmod(0)
    try:
        if os.access(f, os.R_OK):
            pytest.skip("se ejecuta como superusuario")
        with pytest.raises(ErrorProxLaunch) as e:
            abrir_para_subir(f)
        assert e.value.params["motivo"] == "sin_permiso"
    finally:
        f.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_un_enlace_simbolico_a_un_archivo_regular_se_abre_el_destino_con_fstat(tmp_path):
    real = tmp_path / "real.iso"
    real.write_bytes(b"datos")
    enlace = tmp_path / "enlace.iso"
    os.symlink(real, enlace)
    with abrir_para_subir(enlace) as a:
        assert a.flujo.read() == b"datos"


def test_el_archivo_se_abre_solo_para_lectura(tmp_path):
    f = tmp_path / "ro.iso"
    f.write_bytes(b"datos")
    with abrir_para_subir(f) as a, pytest.raises((io.UnsupportedOperation, OSError)):
        a.flujo.write(b"x")
    assert f.read_bytes() == b"datos"


def test_sigue_igual_detecta_cambio_de_tamano_y_de_fecha(tmp_path):
    f = tmp_path / "a.iso"
    f.write_bytes(b"x" * 100)
    with abrir_para_subir(f) as a:
        assert a.sigue_igual()
        with open(f, "ab") as g:
            g.write(b"y")
        assert not a.sigue_igual()
    g = tmp_path / "b.iso"
    g.write_bytes(b"x" * 100)
    with abrir_para_subir(g) as a:
        estado = g.stat()
        os.utime(g, ns=(estado.st_atime_ns, estado.st_mtime_ns + 10**9))
        assert not a.sigue_igual()
    assert not a.sigue_igual()  # cerrado


def test_calcular_sha256_coincide_con_hashlib_reporta_progreso_y_deja_el_flujo_en_cero(tmp_path):
    f = tmp_path / "g.iso"
    datos = os.urandom(3 * CHUNK_SUBIDA + 123)
    f.write_bytes(datos)
    vistos: list[tuple[int, int]] = []
    with abrir_para_subir(f) as a:
        h = calcular_sha256(a, al_progresar=lambda x, t: vistos.append((x, t)))
        assert a.flujo.tell() == 0
    assert h == hashlib.sha256(datos).hexdigest()
    assert vistos[-1] == (len(datos), len(datos)) and len(vistos) == 4  # por bloques de 1 MiB


def test_calcular_sha256_con_bloque_pequeno_y_en_archivo_de_1_byte(tmp_path):
    f = tmp_path / "u.iso"
    f.write_bytes(b"z")
    with abrir_para_subir(f) as a:
        assert calcular_sha256(a, tam_bloque=1) == hashlib.sha256(b"z").hexdigest()


def test_ca_o12_3_cancelar_durante_la_huella_detiene_la_lectura(tmp_path):
    f = tmp_path / "grande.iso"
    f.write_bytes(os.urandom(5 * CHUNK_SUBIDA))
    ev = threading.Event()
    hechos: list[int] = []

    def al_progresar(h, t):
        hechos.append(h)
        ev.set()

    with abrir_para_subir(f) as a, pytest.raises(ErrorProxLaunch) as e:
        calcular_sha256(a, al_progresar=al_progresar, cancelado=ev)
    assert e.value.codigo == CodigoError.TRANSFERENCIA_CANCELADA
    assert hechos == [CHUNK_SUBIDA]  # un bloque y se detiene


def test_calcular_sha256_si_el_archivo_se_acorta_da_archivo_cambio(tmp_path):
    f = tmp_path / "c.iso"
    f.write_bytes(os.urandom(3 * CHUNK_SUBIDA))
    with abrir_para_subir(f) as a:
        os.truncate(f, 10)
        with pytest.raises(ErrorProxLaunch) as e:
            calcular_sha256(a)
    assert e.value.codigo == CodigoError.ARCHIVO_CAMBIO


# --- URL y checksum (V-O11, V-O12, INV-O6) --------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "permitir_http", "motivo"),
    [
        ("https://dl.example.org/iso/alpine.iso", False, None),
        ("HTTPS://DL.EXAMPLE.ORG/a.iso", False, None),
        ("http://dl.example.org/a.iso", True, None),
        ("http://dl.example.org/a.iso", False, "solo_https"),
        ("file:///etc/passwd", True, "esquema"),
        ("ftp://dl.example.org/a.iso", True, "esquema"),
        ("javascript:alert(1)", True, "esquema"),
        ("https://usuario:clave@dl.example.org/a.iso", False, "credenciales"),
        ("https://usuario@dl.example.org/a.iso", False, "credenciales"),
        ("https://dl.example.org/con espacio.iso", False, "caracteres"),
        ("https://dl.example.org/a.iso\n", False, None),  # el recorte quita el salto final
        ("https://dl.example.org/a\n.iso", False, "caracteres"),
        ("https://dl.example.org/a\t.iso", False, "caracteres"),
        ("https://dl.example.org/a\x00.iso", False, "caracteres"),
        ("https://dl.example.org/ñ.iso", False, "caracteres"),
        ("https://bücher.example/a.iso", False, "caracteres"),  # IDN: se pide punycode
        ("https://xn--bcher-kva.example/a.iso", False, None),
        ("https://dl.example.org:99999/a.iso", False, "puerto"),
        ("https:///a.iso", False, "sin_host"),
        ("https://", False, "sin_host"),
        ("", False, "vacia"),
        ("   ", False, "vacia"),
        ("https://10.0.0.5/a.iso", False, None),  # IP interna: la resuelve y limita el servidor
        ("https://dl.example.org/a.iso?token=secreto", False, None),
    ],
)
def test_v_o11_url(url, permitir_http, motivo):
    resultado, rechazo = validar_url(url, permitir_http=permitir_http)
    assert rechazo == motivo
    assert (resultado is None) == (motivo is not None)


def test_v_o11_longitud_maxima_de_2048():
    base = "https://h.example/"
    ok = base + "a" * (MAX_LONG_URL - len(base))
    assert validar_url(ok, permitir_http=False)[1] is None
    assert validar_url(ok + "a", permitir_http=False)[1] == "larga"  # 2049


def test_v_o11_extrae_host_y_archivo_y_el_repr_no_filtra_la_url():
    url, _ = validar_url(
        "https://dl.example.org:8443/dir/alpine%20x.iso?token=SECRETO", permitir_http=False
    )
    assert (url.host, url.archivo, url.es_http) == ("dl.example.org", "alpine x.iso", False)
    assert host_y_archivo(url) == ("dl.example.org", "alpine x.iso")
    assert "SECRETO" not in repr(url) and "token" not in repr(url) and "SECRETO" not in str(url)
    assert repr(url) == "UrlDescarga(dl.example.org/alpine x.iso)"
    http, _ = validar_url("http://h.example/a.iso", permitir_http=True)
    assert http.es_http is True


def test_ocultar_url_la_quita_en_todas_sus_formas():
    from urllib.parse import quote, quote_plus

    url, _ = validar_url("https://dl.example.org/dir/a.iso?token=SECRETO&x=1", permitir_http=False)
    for forma in (
        url.texto,
        quote(url.texto, safe=""),
        quote_plus(url.texto),
        url.texto.split("://", 1)[1],
        url.texto[: len(url.texto) // 2] + "...",
    ):
        limpio = ocultar_url(f"fallo al pedir {forma} (timeout)", url)
        assert "SECRETO" not in limpio and "token=" not in limpio, forma
    assert "dl.example.org/a.iso" in ocultar_url(f"get {url.texto}", url)
    assert ocultar_url("sin url", url) == "sin url"


@pytest.mark.parametrize(
    ("texto", "algoritmo"),
    [
        ("a" * 32, AlgoritmoChecksum.MD5),
        ("a" * 40, AlgoritmoChecksum.SHA1),
        ("a" * 56, AlgoritmoChecksum.SHA224),
        ("a" * 64, AlgoritmoChecksum.SHA256),
        ("A" * 96, AlgoritmoChecksum.SHA384),
        ("0123456789abcdef" * 8, AlgoritmoChecksum.SHA512),
    ],
)
def test_v_o12_el_algoritmo_se_deduce_de_la_longitud(texto, algoritmo):
    cs, motivo = validar_checksum(texto)
    assert motivo is None and cs.algoritmo == algoritmo and cs.valor == texto.lower()


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("a" * 63, "formato"),  # §11.6
        ("a" * 65, "formato"),
        ("g" * 64, "formato"),
        ("a" * 31 + " ", None),  # el recorte de espacios exteriores deja 31 → formato
        ("aa aa" + "a" * 59, "formato"),
        ("", "vacio"),
        ("   ", "vacio"),
        (None, "vacio"),
    ],
)
def test_v_o12_checksums_invalidos(texto, motivo):
    cs, rechazo = validar_checksum(texto)
    if motivo is None:
        assert rechazo == "formato" and cs is None
    else:
        assert rechazo == motivo and cs is None


def test_v_o12_espacios_exteriores_se_recortan_y_las_mayusculas_se_normalizan():
    cs, rechazo = validar_checksum("  " + "AB" * 32 + "\n")
    assert rechazo is None and cs.valor == "ab" * 32 and cs.algoritmo == AlgoritmoChecksum.SHA256


def test_inv_o6_el_repr_del_checksum_no_muestra_el_valor():
    cs, _ = validar_checksum("ab" * 32)
    assert "ab" * 8 not in repr(cs) and repr(cs) == "ChecksumTransferencia(sha256)"


# --- Medición de progreso (RNF-O02) ---------------------------------------------------------------


def test_medidor_calcula_velocidad_y_tiempo_restante_con_media_movil():
    reloj = RelojSimulado()
    m = MedidorProgreso(reloj, ventana_s=5.0)
    assert m.registrar(0, 1000) == (None, None)  # sin intervalo no hay velocidad
    reloj.avanzar(1.0)
    v, restante = m.registrar(100, 1000)
    assert v == pytest.approx(100.0) and restante == pytest.approx(9.0)
    reloj.avanzar(1.0)
    v, restante = m.registrar(300, 1000)
    assert v == pytest.approx(150.0) and restante == pytest.approx(700 / 150)


def test_medidor_olvida_lo_anterior_a_la_ventana():
    reloj = RelojSimulado()
    m = MedidorProgreso(reloj, ventana_s=2.0)
    m.registrar(0, None)
    reloj.avanzar(10.0)
    m.registrar(10_000, None)  # rápido al principio
    reloj.avanzar(1.0)
    m.registrar(10_100, None)
    reloj.avanzar(1.0)
    v, restante = m.registrar(10_200, None)
    assert v == pytest.approx(100.0) and restante is None  # total desconocido


def test_medidor_sin_avance_o_retroceso_no_da_velocidad():
    reloj = RelojSimulado()
    m = MedidorProgreso(reloj)
    m.registrar(500, 1000)
    reloj.avanzar(1.0)
    assert m.registrar(500, 1000) == (None, None)
    reloj.avanzar(1.0)
    assert m.registrar(100, 1000) == (None, None)


def test_rnf_o02_debe_emitir_como_mucho_diez_veces_por_segundo():
    reloj = RelojSimulado()
    m = MedidorProgreso(reloj)
    emisiones = 0
    for _ in range(1000):  # 1000 notificaciones en 1 s simulado
        emisiones += m.debe_emitir()
        reloj.avanzar(0.001)
    assert 9 <= emisiones <= 11
    assert m.debe_emitir() in (True, False)


def test_progreso_de_log_es_tolerante_y_extrae_porcentaje_y_total():
    lineas = [
        "starting download of 'https://h/x.iso'",
        "Length: 1073741824 (1.0G) [application/x-iso9660-image]",
        "  10M .......... .......... 25% 12.3M 1s",
        "  50M .......... .......... 50% 12.3M 1s",
    ]
    hechos, total, pct = progreso_de_log(lineas)
    assert (total, pct) == (1073741824, 50.0) and hechos == 50 * 1024**2
    assert progreso_de_log([]) == (None, None, None)
    assert progreso_de_log(["basura", "100% 200% -5%", "\x00\x01"])[2] in (None, 100.0)
    h, t, p = progreso_de_log(["Length: 1000", "30 %"])
    assert (h, t, p) == (300, 1000, 30.0)
    assert progreso_de_log(["Length: 10", "99%"])[0] <= 10  # nunca más que el total
