"""D1.2 a D1.4: lectura segura del XML de libvirt (RF-D1.2, RF-D1.3, RF-D1.4; RNF-D2).

Derivadas de docs/requisitos/fase-d.md: CA-D1.2.1 a CA-D1.2.4, CA-D1.3.1 a CA-D1.3.7 y
CA-D1.4.1 a CA-D1.4.7 (la parte de interpretación del dominio). Los archivos viven en
``tests/datos/fase_d/libvirt``; los grandes se generan aquí. El fuzz usa semilla fija y bytes
arbitrarios: la salida es siempre un árbol o un ``ErrorXml``, nunca otra excepción.
"""

from __future__ import annotations

import logging
import pyexpat
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.libvirt import lectura_xml
from proxlaunch.nucleo.libvirt.correspondencias import nombre_dns_de
from proxlaunch.nucleo.libvirt.lectura_xml import (
    MAX_BYTES_XML,
    MAX_ELEMENTOS,
    MAX_PROFUNDIDAD,
    ErrorXml,
    leer_archivo,
    leer_xml,
)
from proxlaunch.nucleo.libvirt.modelos import interpretar_dominio, texto_saneado

from .apoyo_fase_d_libvirt import (
    bytes_xml,
    dominio_de,
    dominio_desde_texto,
    xml_minimo,
)

DOMINIO_OK = xml_minimo().encode()


def _motivo(datos: bytes) -> str:
    with pytest.raises(ErrorXml) as e:
        leer_xml(datos)
    return e.value.motivo


def _anidado(niveles: int) -> bytes:
    """``<domain>`` con ``niveles`` niveles en total (la raíz cuenta como el primero)."""
    return ("<domain>" + "<a>" * (niveles - 1) + "</a>" * (niveles - 1) + "</domain>").encode()


def _con_elementos(total: int) -> bytes:
    """``<domain>`` con exactamente ``total`` elementos (la raíz incluida)."""
    return ("<domain>" + "<a/>" * (total - 1) + "</domain>").encode()


# --- CA-D1.2.1: tamaño ---------------------------------------------------------------------


def test_ca_d1_2_1_un_byte_por_encima_de_4_mib_es_tamano():
    datos = DOMINIO_OK + b" " * (MAX_BYTES_XML + 1 - len(DOMINIO_OK))
    assert len(datos) == MAX_BYTES_XML + 1
    with pytest.raises(ErrorXml) as e:
        leer_xml(datos)
    assert e.value.motivo == "tamano"
    assert e.value.a_error().codigo == CodigoError.XML_NO_VALIDO
    assert e.value.a_error().params["motivo"] == "tamano"


def test_ca_d1_2_1_exactamente_4_mib_se_acepta():
    datos = DOMINIO_OK + b" " * (MAX_BYTES_XML - len(DOMINIO_OK))
    assert len(datos) == MAX_BYTES_XML
    assert leer_xml(datos).tag == "domain"


def test_ca_d1_2_1_el_tamano_no_se_interpreta_aunque_sea_un_dominio_valido():
    # Si se interpretara, el análisis tardaría; basta con que el motivo sea «tamano» y no «formato».
    assert _motivo(b"<domain>" + b"x" * (MAX_BYTES_XML + 1)) == "tamano"


def test_ca_d1_2_1_leer_archivo_no_lee_mas_de_el_limite_mas_un_byte(tmp_path):
    ruta = tmp_path / "enorme.xml"
    ruta.write_bytes(b"<" + b"a" * (MAX_BYTES_XML * 2))
    leidos = leer_archivo(ruta)
    assert len(leidos) == MAX_BYTES_XML + 1
    assert _motivo(leidos) == "tamano"


def test_leer_archivo_rechaza_lo_que_no_es_un_archivo_regular(tmp_path):
    with pytest.raises(ErrorProxLaunch) as e:
        leer_archivo(tmp_path)  # un directorio
    assert e.value.codigo in (CodigoError.ARCHIVO_NO_PERMITIDO, CodigoError.ARCHIVO_NO_ACCESIBLE)
    with pytest.raises(ErrorProxLaunch) as e2:
        leer_archivo(tmp_path / "no-existe.xml")
    assert e2.value.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE


def test_leer_archivo_lee_los_bytes_de_un_xml_real(tmp_path):
    ruta = tmp_path / "m.xml"
    ruta.write_bytes(bytes_xml("linux_bios.xml"))
    assert leer_archivo(ruta) == bytes_xml("linux_bios.xml")


# --- CA-D1.2.2: vacío, un byte, binario ----------------------------------------------------


@pytest.mark.parametrize(
    "datos",
    [
        b"",
        b"<",
        b"x",
        b"\x00",
        b"\xff",
        bytes(range(256)),
        b"\x89PNG\r\n\x1a\n" + bytes(64),
        b"\n\n",
    ],
    ids=["vacio", "menor", "texto", "nul", "ff", "binario256", "png", "blancos"],
)
def test_ca_d1_2_2_vacio_un_byte_o_binario_es_error_xml_sin_excepcion(datos):
    with pytest.raises(ErrorXml) as e:
        leer_xml(datos)
    assert e.value.motivo in ("formato", "codificacion")


# --- CA-D1.2.3: límites ----------------------------------------------------------------------


def test_ca_d1_2_3_65_niveles_es_limites_y_64_se_acepta():
    assert MAX_PROFUNDIDAD == 64
    assert leer_xml(_anidado(64)).tag == "domain"
    assert _motivo(_anidado(65)) == "limites"


def test_ca_d1_2_3_70_niveles_es_limites():
    assert _motivo(_anidado(70)) == "limites"


def test_ca_d1_2_3_50_000_elementos_se_acepta_y_50_001_es_limites():
    assert MAX_ELEMENTOS == 50_000
    assert leer_xml(_con_elementos(50_000)).tag == "domain"
    assert _motivo(_con_elementos(50_001)) == "limites"


def test_ca_d1_2_3_60_000_elementos_es_limites():
    assert _motivo(_con_elementos(60_000)) == "limites"


def test_ca_d1_2_3_anidamiento_extremo_no_agota_la_pila():
    # 100 000 niveles caben en menos de 4 MiB: debe cortar por límites, no por RecursionError.
    datos = b"<a>" * 100_000
    assert len(datos) < MAX_BYTES_XML
    assert _motivo(datos) == "limites"


def test_ca_d1_2_3_el_recuento_corta_antes_de_leer_todo_el_archivo(monkeypatch):
    """Con 4 MiB de elementos el análisis se detiene al pasar el límite (no recorre todo)."""
    alimentados: list[int] = []
    original = ET.XMLPullParser.feed

    def feed(self, data):
        alimentados.append(len(data))
        return original(self, data)

    monkeypatch.setattr(ET.XMLPullParser, "feed", feed)
    datos = b"<domain>" + b"<a/>" * 1_000_000 + b"</domain>"
    assert len(datos) < MAX_BYTES_XML
    assert _motivo(datos) == "limites"
    assert sum(alimentados) < len(datos)  # se cortó a mitad


# --- CA-D1.2.4 y codificaciones --------------------------------------------------------------


def _arbol_texto(raiz: ET.Element) -> str:
    return ET.tostring(raiz, encoding="unicode")


def test_ca_d1_2_4_utf16_con_bom_se_lee_igual_que_utf8():
    utf8 = leer_xml(bytes_xml("utf8_acentos.xml"))
    utf16 = leer_xml(bytes_xml("utf16_bom.xml"))
    assert _arbol_texto(utf8) == _arbol_texto(utf16)
    assert dominio_de("utf16_bom.xml") == dominio_de("utf8_acentos.xml")


@pytest.mark.parametrize("codec", ["utf-16-le", "utf-16-be"])
def test_ca_d1_2_4_utf16_le_y_be_con_bom(codec):
    texto = "<domain type='kvm'><name>ñ</name></domain>"
    bom = b"\xff\xfe" if codec.endswith("le") else b"\xfe\xff"
    raiz = leer_xml(bom + texto.encode(codec))
    assert raiz.findtext("name") == "ñ"


def test_utf8_con_bom_se_acepta():
    raiz = leer_xml(b"\xef\xbb\xbf" + "<domain><name>ñ</name></domain>".encode())
    assert raiz.findtext("name") == "ñ"


def test_utf16_sin_bom_es_codificacion():
    assert _motivo(bytes_xml("utf16_sin_bom.xml")) == "codificacion"


def test_latin1_con_acentos_es_codificacion():
    assert _motivo(bytes_xml("latin1.xml")) == "codificacion"


def test_utf32_con_bom_es_codificacion():
    assert _motivo(b"\xff\xfe\x00\x00" + "<domain/>".encode("utf-32-le")) == "codificacion"


def test_nul_dentro_del_texto_es_codificacion():
    assert _motivo(b"<domain>\x00</domain>") == "codificacion"


def test_la_declaracion_de_codificacion_se_ignora_porque_ya_se_decodifico():
    # Declara UTF-16 pero los bytes son UTF-8: se lee por lo real (no por lo declarado).
    datos = "<?xml version='1.0' encoding='UTF-16'?><domain><name>ñ</name></domain>".encode()
    assert leer_xml(datos).findtext("name") == "ñ"


# --- CA-D1.3.1 a CA-D1.3.3: DOCTYPE y ENTITY --------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        '<!DOCTYPE foo [<!ENTITY x "a">]><domain/>',
        "<!doctype domain><domain/>",
        "<!DocType domain><domain/>",
        "<!   DOCTYPE domain><domain/>",
        "<!\n\tDOCTYPE domain><domain/>",
        '<domain><!ENTITY x "a"></domain>',
        '<domain><!entity x "a"></domain>',
        '<domain><!  ENTITY x "a"></domain>',
        "<!-- comentario --><!DOCTYPE domain><domain/>",
        "<domain><!-- <!DOCTYPE x> --></domain>",
        "<domain><!-- <!ENTITY x 'a'> --></domain>",
        "<domain><![CDATA[ <!DOCTYPE x> ]]></domain>",
        "<domain><![CDATA[ <!ENTITY x 'a'> ]]></domain>",
        "<?xml version='1.0'?>\n<!DOCTYPE domain SYSTEM 'file:///etc/passwd'><domain/>",
    ],
    ids=lambda t: t[:28].replace("\n", " "),
)
def test_ca_d1_3_1_y_3_2_doctype_o_entity_en_cualquier_forma_es_doctype(texto):
    assert _motivo(texto.encode()) == "doctype"


@pytest.mark.parametrize("nombre", ["doctype.xml", "billion_laughs.xml", "entidad_externa.xml"])
def test_ca_d1_3_3_archivos_de_ataque_son_doctype(nombre):
    assert _motivo(bytes_xml(nombre)) == "doctype"


def test_ca_d1_3_3_el_analizador_ni_se_crea_si_hay_doctype(monkeypatch):
    """Con DOCTYPE/ENTITY nada se interpreta: no se llega a construir ningún analizador."""

    def prohibido(*a, **k):
        raise AssertionError("no debe analizarse un XML con DOCTYPE/ENTITY")

    monkeypatch.setattr(ET, "XMLPullParser", prohibido)
    monkeypatch.setattr(ET, "XMLParser", prohibido)
    monkeypatch.setattr(ET, "fromstring", prohibido)
    for nombre in ("doctype.xml", "billion_laughs.xml", "entidad_externa.xml"):
        assert _motivo(bytes_xml(nombre)) == "doctype"


def test_ca_d1_3_3_ninguna_entidad_se_expande_ni_se_resuelve_nada_externo(monkeypatch):
    """Con entidad externa no se abre ningún archivo ni se usa la red (dobles de open y socket)."""
    import builtins
    import socket

    abiertos: list[str] = []
    real_open = builtins.open

    def espia(archivo, *a, **k):
        abiertos.append(str(archivo))
        return real_open(archivo, *a, **k)

    def sin_red(*a, **k):
        raise AssertionError("el XML no puede abrir conexiones")

    monkeypatch.setattr(builtins, "open", espia)
    monkeypatch.setattr(socket, "socket", sin_red)
    monkeypatch.setattr(socket, "create_connection", sin_red)
    assert _motivo(bytes_xml("entidad_externa.xml")) == "doctype"
    assert not any("passwd" in a for a in abiertos)


def test_ca_d1_3_3_billion_laughs_con_mil_entidades_no_consume_memoria_ni_tiempo():
    entidades = '<!ENTITY l0 "lol">' + "".join(
        f'<!ENTITY l{i} "' + f"&l{i - 1};" * 10 + '">' for i in range(1, 12)
    )
    datos = f"<?xml version='1.0'?><!DOCTYPE d [{entidades}]><domain><name>&l11;</name></domain>"
    assert _motivo(datos.encode()) == "doctype"


def test_un_dumpxml_legitimo_no_trae_doctype_pero_si_el_prefijo_no_es_doctype():
    # «DOCTYPE» como texto normal (sin «<!») no es una declaración.
    raiz = leer_xml(b"<domain><description>DOCTYPE y ENTITY en texto</description></domain>")
    assert raiz.tag == "domain"


# --- CA-D1.3.4: mal formado -------------------------------------------------------------------


def test_ca_d1_3_4_mal_formado_da_formato_con_la_linea():
    with pytest.raises(ErrorXml) as e:
        leer_xml(bytes_xml("mal_formado.xml"))
    assert e.value.motivo == "formato"
    assert e.value.params["linea"].isdigit()
    assert int(e.value.params["linea"]) >= 1
    assert e.value.a_error().params["linea"] == e.value.params["linea"]


@pytest.mark.parametrize(
    "texto",
    [
        "<domain>",
        "<domain></otra>",
        "<domain><a></domain>",
        "<</domain>",
        "texto suelto",
        "<a/><b/>",
    ],
)
def test_ca_d1_3_4_otros_xml_rotos_son_formato(texto):
    assert _motivo(texto.encode()) == "formato"


def test_la_raiz_debe_ser_domain():
    assert _motivo(b"<machine/>") == "no_dominio"
    assert _motivo(b"<Domain/>") == "no_dominio"


# --- CA-D1.3.5: dumpxml reales ----------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre",
    ["linux_bios.xml", "windows11_uefi_tpm.xml", "varios_discos_nic.xml", "backing_store.xml"],
)
def test_ca_d1_3_5_los_dumpxml_de_ejemplo_se_interpretan(nombre):
    d = dominio_de(nombre)
    assert d.nombre
    assert d.discos
    assert d.tipo_dominio == "kvm"


def test_ca_d1_3_5_el_dominio_linux_trae_lo_esperado():
    d = dominio_de("linux_bios.xml")
    assert (d.arquitectura, d.memoria_mib, d.vcpus) == ("x86_64", 4096, 2)
    assert not d.uefi and not d.tpm
    assert len(d.tarjetas) == 1 and d.tarjetas[0].mac == "52:54:00:ab:cd:ef"


def test_ca_d1_3_5_el_dominio_windows_trae_uefi_tpm_y_nvram():
    d = dominio_de("windows11_uefi_tpm.xml")
    assert d.uefi and d.tpm and d.con_nvram
    assert (d.sockets, d.cores, d.threads) == (1, 4, 2)


def test_ca_d1_3_5_varios_discos_y_nic_se_conservan_todos():
    d = dominio_de("varios_discos_nic.xml")
    assert len(d.discos) == 4
    assert len(d.tarjetas) == 3
    assert [t.modelo for t in d.tarjetas] == ["virtio", "rtl8139", "vmxnet3"]


# --- CA-D1.3.6: nombres con marcado ----------------------------------------------------------


def test_ca_d1_3_6_un_nombre_con_marcado_html_se_muestra_saneado():
    d = dominio_desde_texto(
        "<domain type='kvm'><name>&lt;script&gt;alert(1)&lt;/script&gt;&amp;x</name>"
        "<os><type arch='x86_64'>hvm</type></os></domain>"
    )
    assert not set("<>&") & set(d.nombre)
    assert "script" in d.nombre  # se conserva el texto; solo se quita el marcado


def test_ca_d1_3_6_el_nombre_con_formato_invisible_o_control_se_sanea():
    d = dominio_desde_texto(
        "<domain type='kvm'><name>web‮​srv\u0085x</name>"
        "<os><type arch='x86_64'>hvm</type></os></domain>"
    )
    assert all(c.isprintable() for c in d.nombre)
    assert "‮" not in d.nombre and "​" not in d.nombre


def test_ca_d1_3_6_el_nombre_propuesto_cumple_la_limpieza_dns():
    assert nombre_dns_de("<b>web</b> & co") == nombre_dns_de("<b>web</b> & co")  # determinista
    for sucio in ("Web Server #1 (prod)", "a" * 200, "..--..", "ñandú", "x‮y", "-a-"):
        n = nombre_dns_de(sucio)
        assert n and len(n) <= 63
        assert all(c.isalnum() and c.isascii() or c in ".-" for c in n)
        assert not n.startswith(("-", ".")) and not n.endswith(("-", "."))


def test_texto_saneado_recorta_y_rechaza_no_cadenas():
    assert len(texto_saneado("a" * 1000)) == 256
    assert texto_saneado(None) == ""
    assert texto_saneado(b"x") == ""
    assert texto_saneado("a<b>&c\x00\x1b") == "abc"


# --- CA-D1.3.7: versión de Expat --------------------------------------------------------------


def test_ca_d1_3_7_expat_antiguo_solo_se_anota_en_el_registro(monkeypatch, caplog):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.6.4")
    with caplog.at_level(logging.WARNING, logger="proxlaunch.libvirt.lectura_xml"):
        assert leer_xml(DOMINIO_OK).tag == "domain"
    assert any("2.6.4" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("version", ["expat_2.7.2", "expat_2.8.0", "expat_3.0.0"])
def test_ca_d1_3_7_expat_nuevo_no_deja_rastro(monkeypatch, caplog, version):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", version)
    with caplog.at_level(logging.DEBUG, logger="proxlaunch.libvirt.lectura_xml"):
        leer_xml(DOMINIO_OK)
    assert not caplog.records


def test_ca_d1_3_7_una_version_de_expat_ilegible_no_bloquea(monkeypatch):
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "raro")
    assert leer_xml(DOMINIO_OK).tag == "domain"


def test_el_modulo_solo_usa_etree_de_la_biblioteca_estandar():
    codigo = Path(lectura_xml.__file__).read_text(encoding="utf-8")
    for prohibido in ("minidom", "xml.sax", "lxml", "defusedxml", "xml.dom"):
        assert prohibido not in codigo


# --- CA-D1.4.x: qué XML se acepta (interpretación del dominio) --------------------------------


def test_ca_d1_4_1_kvm_hvm_x86_se_interpreta_sin_error():
    d = dominio_desde_texto(xml_minimo())
    assert (d.tipo_dominio, d.tipo_os, d.arquitectura) == ("kvm", "hvm", "x86_64")


@pytest.mark.parametrize("tipo", ["xen", "lxc", "vmware", "hvf", "vbox"])
def test_ca_d1_4_2_los_dominios_no_kvm_se_leen_con_su_tipo_para_que_la_vista_previa_bloquee(tipo):
    assert dominio_desde_texto(xml_minimo(tipo=tipo)).tipo_dominio == tipo


def test_ca_d1_4_5_arch_ausente_queda_vacia_para_suponer_la_del_nodo():
    d = dominio_desde_texto(
        "<domain type='kvm'><name>m</name><os><type>hvm</type></os><devices/></domain>"
    )
    assert d.arquitectura == ""


@pytest.mark.parametrize(
    ("arch", "esperada"),
    [("x86_64", "x86_64"), ("aarch64", "aarch64"), ("ppc64le", "otro"), ("s390x", "otro"),
     ("riscv64", "otro"), ("armv7l", "otro"), ("i686", "x86_64")],
)  # fmt: skip
def test_ca_d1_4_4_y_4_6_arquitecturas_normalizadas(arch, esperada):
    assert dominio_desde_texto(xml_minimo(arch=arch)).arquitectura == esperada


def test_ca_d1_4_6_la_arquitectura_original_se_conserva_para_el_mensaje():
    d = dominio_desde_texto(xml_minimo(arch="ppc64le"))
    assert d.arquitectura_original == "ppc64le"


def test_interpretar_dominio_tolera_un_arbol_minimo_o_raro_sin_lanzar():
    for texto in ("<domain/>", "<domain><devices/></domain>", "<domain><os/><cpu/></domain>",
                  "<domain><memory unit='ZZ'>x</memory><vcpu>-3</vcpu></domain>"):  # fmt: skip
        assert interpretar_dominio(leer_xml(texto.encode())).tipo_dominio is not None


# --- Fuzz con bytes arbitrarios (arquitectura §7.1) -------------------------------------------


def _muta(rnd: random.Random, base: bytes) -> bytes:
    datos = bytearray(base)
    for _ in range(rnd.randint(1, 8)):
        if not datos:
            break
        pos = rnd.randrange(len(datos))
        accion = rnd.randrange(4)
        if accion == 0:
            datos[pos] = rnd.randrange(256)
        elif accion == 1:
            del datos[pos : pos + rnd.randint(1, 20)]
        elif accion == 2:
            datos[pos:pos] = bytes(rnd.randrange(256) for _ in range(rnd.randint(1, 10)))
        else:
            datos[pos:pos] = rnd.choice(
                [b"<", b">", b"&", b"<!", b"\xff\xfe", b"<!DOCTYPE", b"]]>"]
            )
    return bytes(datos)


def _comprobar_fuzz(datos: bytes) -> None:
    try:
        raiz = leer_xml(datos)
    except ErrorXml as e:
        assert e.motivo in {"tamano", "doctype", "formato", "codificacion", "limites", "no_dominio"}
        assert e.a_error().codigo == CodigoError.XML_NO_VALIDO
        return
    interpretar_dominio(raiz)  # tampoco debe lanzar


def test_fuzz_bytes_arbitrarios_solo_dan_arbol_o_error_xml():
    rnd = random.Random(20260901)
    for _ in range(2000):
        _comprobar_fuzz(bytes(rnd.randrange(256) for _ in range(rnd.randint(0, 200))))


def test_fuzz_xml_validos_mutados_solo_dan_arbol_o_error_xml():
    rnd = random.Random(20260902)
    bases = [
        bytes_xml(n) for n in ("linux_bios.xml", "windows11_uefi_tpm.xml", "varios_discos_nic.xml")
    ]
    for i in range(1500):
        _comprobar_fuzz(_muta(rnd, bases[i % len(bases)]))


def test_fuzz_prefijos_truncados_de_un_xml_real():
    base = bytes_xml("windows11_uefi_tpm.xml")
    for corte in range(0, len(base), 7):
        _comprobar_fuzz(base[:corte])


@pytest.mark.parametrize("bom", [b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf", b""])
def test_fuzz_con_cada_bom_y_cola_aleatoria(bom):
    rnd = random.Random(7)
    for _ in range(300):
        _comprobar_fuzz(bom + bytes(rnd.randrange(256) for _ in range(rnd.randint(0, 120))))
