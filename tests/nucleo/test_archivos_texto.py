"""Cadenas seguras, nombres y nombres de archivo (V-M01, V-M04, V-M05; CA-X02.5, CA-P08.5,
CA-X04.3, CA-X03.4; §13 casos 2 y 5 de los requisitos)."""

import unicodedata

import pytest

from proxlaunch.nucleo.archivos.constantes import LONG_NOMBRE_PERFIL, MAX_LONG_TEXTO
from proxlaunch.nucleo.archivos.texto import (
    clave_comparacion,
    contiene_token,
    nombre_archivo_seguro,
    texto_seguro,
    validar_nombre,
)

BIDI = [chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F, 0x061C)]


# --- texto_seguro (V-M04, CA-X02.5) -------------------------------------------------------------


def test_texto_seguro_acepta_texto_normal_y_acentos():
    assert texto_seguro("Servidor ñandú café", maximo=MAX_LONG_TEXTO) == "Servidor ñandú café"


def test_texto_seguro_normaliza_a_nfc():
    nfd = unicodedata.normalize("NFD", "café")
    assert nfd != "café"
    assert texto_seguro(nfd, maximo=MAX_LONG_TEXTO) == "café"


def test_texto_seguro_respeta_el_maximo_exacto():
    assert texto_seguro("a" * MAX_LONG_TEXTO, maximo=MAX_LONG_TEXTO) is not None
    assert texto_seguro("a" * (MAX_LONG_TEXTO + 1), maximo=MAX_LONG_TEXTO) is None


@pytest.mark.parametrize("control", ["\x00", "\x07", "\x1b", "\x7f", "\t", "\r", "\n", "\x85"])
def test_texto_seguro_rechaza_caracteres_de_control(control):
    assert texto_seguro(f"a{control}b", maximo=MAX_LONG_TEXTO) is None


@pytest.mark.parametrize("bidi", BIDI, ids=lambda c: f"U+{ord(c):04X}")
def test_texto_seguro_rechaza_cada_caracter_de_direccion_de_texto(bidi):
    assert texto_seguro(f"a{bidi}b", maximo=MAX_LONG_TEXTO) is None


def test_salto_de_linea_solo_se_admite_en_multilinea():
    assert texto_seguro("a\nb", maximo=50) is None
    assert texto_seguro("a\nb", maximo=50, multilinea=True) == "a\nb"
    assert texto_seguro("a\rb", maximo=50, multilinea=True) is None
    assert texto_seguro("a\tb", maximo=50, multilinea=True) is None


def test_texto_seguro_rechaza_sustitutos_sueltos_y_no_cadenas():
    assert texto_seguro("a\ud800b", maximo=50) is None
    assert texto_seguro(None, maximo=50) is None  # type: ignore[arg-type]
    assert texto_seguro(123, maximo=50) is None  # type: ignore[arg-type]


def test_un_texto_desmesurado_se_rechaza_sin_trabajo_excesivo():
    assert texto_seguro("a" * 5_000_000, maximo=MAX_LONG_TEXTO) is None


# --- contiene_token (V-M05, CA-X04.3) ---------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "ana@pve!lab=0123456789abcdef",
        "usa root@pam!mitoken=abc-123 para entrar",
        "PVEAPIToken=ana@pve!lab=secreto",
        "pveapitoken = x",
        "Authorization: PVEAPIToken=ana@pve!t=1",
    ],
)
def test_contiene_token_detecta_el_patron_de_un_api_token(texto):
    assert contiene_token(texto) is True


@pytest.mark.parametrize(
    "texto",
    ["", "servidor web", "ana@pve", "correo@dominio.com", "a=b", "usuario!id", "token de acceso"],
)
def test_contiene_token_no_da_falsos_positivos_en_texto_normal(texto):
    assert contiene_token(texto) is False


def test_contiene_token_con_no_cadena_es_falso():
    assert contiene_token(None) is False  # type: ignore[arg-type]


# --- validar_nombre (V-M01, V-M04, V-M05; §13 caso 2) -------------------------------------------


def test_nombre_de_60_caracteres_es_valido_y_de_61_no():
    assert validar_nombre("a" * 60) == ("a" * 60, None)
    normalizado, regla = validar_nombre("a" * 61)
    assert regla == "V-M01"
    assert len(normalizado) == 61


def test_el_limite_del_nombre_de_perfil_es_60():
    assert LONG_NOMBRE_PERFIL == 60


@pytest.mark.parametrize("vacio", ["", "   ", "\u00a0"])
def test_nombre_vacio_o_solo_espacios_es_v_m01(vacio):
    assert validar_nombre(vacio)[1] == "V-M01"


def test_el_nombre_se_recorta_y_se_normaliza_a_nfc():
    assert validar_nombre("  Café  ") == ("Café", None)
    assert validar_nombre(unicodedata.normalize("NFD", "Ñandú")) == ("Ñandú", None)


def test_nombre_con_acentos_de_60_caracteres_en_nfd_cuenta_tras_normalizar():
    nfd = unicodedata.normalize("NFD", "é" * 60)
    assert len(nfd) == 120
    assert validar_nombre(nfd) == ("é" * 60, None)


@pytest.mark.parametrize("bidi", BIDI, ids=lambda c: f"U+{ord(c):04X}")
def test_nombre_con_direccion_de_texto_es_v_m04(bidi):
    assert validar_nombre(f"Perfil{bidi}")[1] == "V-M04"


@pytest.mark.parametrize("control", ["\x00", "\n", "\t", "\x1b"])
def test_nombre_con_caracteres_de_control_es_v_m04(control):
    assert validar_nombre(f"a{control}b")[1] == "V-M04"


def test_nombre_desmesurado_es_v_m04():
    assert validar_nombre("a" * (MAX_LONG_TEXTO + 1))[1] == "V-M04"


def test_nombre_que_parece_un_token_es_v_m05():
    assert validar_nombre("ana@pve!lab=abcdef")[1] == "V-M05"
    assert validar_nombre("PVEAPIToken=x")[1] == "V-M05"


def test_nombre_no_cadena_es_v_m01():
    assert validar_nombre(None)[1] == "V-M01"  # type: ignore[arg-type]


# --- clave_comparacion --------------------------------------------------------------------------


def test_clave_comparacion_ignora_mayusculas_y_forma_unicode():
    assert clave_comparacion("SERVIDOR") == clave_comparacion("servidor")
    assert clave_comparacion(unicodedata.normalize("NFD", "Café")) == clave_comparacion("CAFÉ")


def test_clave_comparacion_distingue_acentos_salvo_que_se_pida():
    assert clave_comparacion("café") != clave_comparacion("cafe")
    assert clave_comparacion("Café", sin_acentos=True) == clave_comparacion(
        "CAFE", sin_acentos=True
    )


def test_clave_comparacion_recorta_espacios():
    assert clave_comparacion("  web ") == "web"


def test_clave_comparacion_usa_casefold_para_la_eszett():
    assert clave_comparacion("STRASSE") == clave_comparacion("straße")


# --- nombre_archivo_seguro (CA-P08.5, §13 caso 5) -----------------------------------------------

EXT = ".proxlaunch-perfiles.json"


@pytest.mark.parametrize(
    "base", ["CON", "con", "PRN", "AUX", "NUL", "COM1", "com9", "LPT1", "lpt9", "CON.txt", "nul.x"]
)
def test_los_nombres_reservados_de_windows_no_salen_tal_cual(base):
    nombre = nombre_archivo_seguro(base, EXT)
    assert nombre.split(".", 1)[0].upper() not in {"CON", "PRN", "AUX", "NUL"}
    assert nombre.split(".", 1)[0].upper() not in {f"COM{i}" for i in range(1, 10)}
    assert nombre.split(".", 1)[0].upper() not in {f"LPT{i}" for i in range(1, 10)}
    assert nombre.endswith(EXT)


@pytest.mark.parametrize("base", ["a/b", "a\\b", "../../etc/passwd", "C:\\x", "a:b", "x|y", 'a"b'])
def test_sin_separadores_de_ruta_ni_caracteres_prohibidos(base):
    nombre = nombre_archivo_seguro(base, EXT)
    assert not any(c in nombre for c in '/\\:|"<>?*')
    assert nombre.endswith(EXT)


@pytest.mark.parametrize("base", ["..", ".", "...", " . ", "", "   "])
def test_nunca_sale_un_nombre_vacio_ni_punto_ni_dobles_puntos(base):
    nombre = nombre_archivo_seguro(base, EXT)
    assert nombre not in {"", ".", ".."}
    assert not nombre.startswith(("..", "./"))
    assert nombre.endswith(EXT)
    assert nombre != EXT  # siempre hay un cuerpo antes de la extensión


def test_el_nombre_sugerido_no_supera_80_caracteres_con_extension():
    nombre = nombre_archivo_seguro("x" * 200, EXT)
    assert len(nombre) <= 80
    assert nombre.endswith(EXT)
    assert nombre.startswith("x")


def test_el_nombre_sugerido_conserva_acentos_y_espacios_legitimos():
    assert nombre_archivo_seguro("Servidor ñandú", ".csv") == "Servidor ñandú.csv"


def test_el_nombre_sugerido_reemplaza_control_y_direccion_de_texto():
    nombre = nombre_archivo_seguro("a\x00b\u202ec\nd", ".csv")
    assert "\x00" not in nombre and "\u202e" not in nombre and "\n" not in nombre


def test_el_nombre_sugerido_no_termina_en_punto_ni_espacio_antes_de_la_extension():
    nombre = nombre_archivo_seguro("informe. ", ".csv")
    assert not nombre.removesuffix(".csv").endswith((" ", "."))
