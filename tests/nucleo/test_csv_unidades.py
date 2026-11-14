"""Números, unidades y enumeraciones de las celdas (RF-C04; CA-C04.1..C04.10, CA-C05.6;
decisión D-T8/D-T9; tabla §13.11 de los requisitos).

Memoria y disco sin unidad = GiB; ``MB/GB/TB`` se tratan como binarias (con aviso); el resultado
debe ser entero (MiB para la memoria, GiB para el disco); las ambigüedades de miles (``1.000``,
``1.024,5``) son V-M08 y nunca se interpretan en silencio; nada de signo, exponente ni hex.
"""

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo as Aviso
from proxlaunch.nucleo.csv_importacion import unidades
from proxlaunch.nucleo.csv_importacion.unidades import ValorInvalido
from proxlaunch.nucleo.modelos.vm import Firmware, ModeloRed

GIB_ASUMIDO = Aviso.GIB_ASUMIDO
COMA = Aviso.DECIMAL_COMA
GB = Aviso.GB_COMO_GIB


def _invalido(funcion, *args) -> ValorInvalido:
    with pytest.raises(ValorInvalido) as exc:
        funcion(*args)
    return exc.value


# --- Memoria (CA-C04.1, CA-C04.2) -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "mib", "avisos"),
    [
        ("4", 4096, {GIB_ASUMIDO}),
        ("4 GiB", 4096, set()),
        ("4GiB", 4096, set()),
        ("4G", 4096, set()),
        ("4g", 4096, set()),
        ("4096 MiB", 4096, set()),
        ("4096MiB", 4096, set()),
        ("4096 M", 4096, set()),
        ("4096 mib", 4096, set()),
        ("1,5", 1536, {GIB_ASUMIDO, COMA}),
        ("1.5", 1536, {GIB_ASUMIDO}),
        ("1,5 GiB", 1536, {COMA}),
        ("1.5 GiB", 1536, set()),
        ("4 GB", 4096, {GB}),
        ("4 gb", 4096, {GB}),
        ("4096 MB", 4096, {GB}),
        ("1 TB", 1024 * 1024, {GB}),
        ("1 TiB", 1024 * 1024, set()),
        ("2T", 2 * 1024 * 1024, set()),
        ("0,125", 128, {GIB_ASUMIDO, COMA}),
        ("0.5G", 512, set()),
        ("512 MiB", 512, set()),
        ("4096", 4096 * 1024, {GIB_ASUMIDO}),
        ("16", 16 * 1024, {GIB_ASUMIDO}),
        ("  4  ", 4096, {GIB_ASUMIDO}),
        ('"4"', 4096, {GIB_ASUMIDO}),
        ("'4 GiB'", 4096, set()),
        ("“4”", 4096, {GIB_ASUMIDO}),
        ("0", 0, {GIB_ASUMIDO}),
        ("1.0000", 1024, {GIB_ASUMIDO}),
        ("1,25 GiB", 1280, {COMA}),
    ],
)
def test_memoria_valores_validos(texto, mib, avisos):
    resultado, a = unidades.memoria_mib(texto)
    assert resultado == mib
    assert a == frozenset(avisos)


def test_0_3_gib_no_es_un_numero_entero_de_mib_y_da_el_ejemplo_valido():
    """CA-C04.2: 0,3 GiB = 307,2 MiB."""
    e = _invalido(unidades.memoria_mib, "0,3")
    assert e.regla == "E-M11.mib_no_entero" and "MiB" in e.params["ejemplo"]


@pytest.mark.parametrize("texto", ["1.000", "1,000", "10.000", "2,500", "999.999"])
def test_memoria_con_patron_de_miles_ambiguo_es_v_m08(texto):
    """D-T8: ``1.000`` es tan ambiguo en memoria como en disco."""
    e = _invalido(unidades.memoria_mib, texto)
    assert e.regla == "V-M08" and e.params["motivo"] == "miles"
    assert e.params["mil"] == texto.replace(".", "").replace(",", "")


@pytest.mark.parametrize("texto", ["1.024,5", "1,024.5", "1.2.3", "1,2,3", "1.000.000"])
def test_con_ambos_separadores_o_varios_es_v_m08(texto):
    e = _invalido(unidades.memoria_mib, texto)
    assert e.regla == "V-M08"


def test_el_texto_del_error_de_miles_ofrece_las_dos_lecturas():
    e = _invalido(unidades.memoria_mib, "1.000")
    assert (e.params["mil"], e.params["uno"]) == ("1000", "1")


def test_parte_entera_cero_no_es_ambigua():
    """Decisión fijada: ``0,125`` es decimal, no V-M08."""
    assert unidades.memoria_mib("0,125")[0] == 128
    assert unidades.memoria_mib("0.250")[0] == 256


@pytest.mark.parametrize(
    "texto",
    [
        "abc",
        "dos",
        "",
        "  ",
        "-1",
        "+1",
        "1e3",
        "1E3",
        "0x10",
        "NaN",
        "Infinity",
        "-Infinity",
        "inf",
        ".5",
        "5.",
        "1 000",
        "4 GiB extra",
        "GiB",
        "∞",
        "٣",
    ],
)
def test_memoria_no_numerica_signo_exponente_hex_nan_e_infinito_se_rechazan(texto):
    """CA-C04.5 / CA-C04.7."""
    e = _invalido(unidades.memoria_mib, texto)
    assert e.regla == "E-M11.no_numero" and "ejemplo" in e.params


@pytest.mark.parametrize("texto", ["4 KB", "4 KiB", "4 XB", "4 bytes", "4 GiBs", "4 Gb2"])
def test_memoria_con_unidad_desconocida(texto):
    e = _invalido(unidades.memoria_mib, texto)
    assert e.regla in {"E-M11.unidad", "E-M11.no_numero"}


def test_unidad_del_encabezado_para_un_numero_sin_unidad():
    """Un alias con unidad en el encabezado (``memoria_mib``) fija la unidad."""
    assert unidades.memoria_mib("4096", "mib") == (4096, frozenset())
    assert unidades.memoria_mib("4", "gib") == (4096, frozenset())


def test_la_unidad_escrita_en_la_celda_manda_sobre_la_del_encabezado():
    assert unidades.memoria_mib("4 GiB", "mib") == (4096, frozenset())
    assert unidades.memoria_mib("2048 MiB", "gib") == (2048, frozenset())


def test_una_unidad_de_encabezado_desconocida_se_ignora_y_vale_gib():
    assert unidades.memoria_mib("4", "kib") == (4096, frozenset({GIB_ASUMIDO}))
    assert unidades.memoria_mib("4", None) == (4096, frozenset({GIB_ASUMIDO}))


def test_memoria_mib_con_decimales_en_el_encabezado_mib_debe_ser_entera():
    assert _invalido(unidades.memoria_mib, "1,5", "mib").regla == "E-M11.mib_no_entero"


# --- Disco (CA-C04.3, CA-C03.8) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "gib", "avisos"),
    [
        ("40", 40, {GIB_ASUMIDO}),
        ("40 GiB", 40, set()),
        ("40G", 40, set()),
        ("40 GB", 40, {GB}),
        ("1 TiB", 1024, set()),
        ("1T", 1024, set()),
        ("1 TB", 1024, {GB}),
        ("1024 MiB", 1, set()),
        ("2048 M", 2, set()),
        ("40,0", 40, {GIB_ASUMIDO, COMA}),
        ("40.0", 40, {GIB_ASUMIDO}),
        ("0,5 TiB", 512, {COMA}),
        ("1", 1, {GIB_ASUMIDO}),
        ('"100"', 100, {GIB_ASUMIDO}),
    ],
)
def test_disco_valores_validos(texto, gib, avisos):
    resultado, a = unidades.disco_gib(texto)
    assert resultado == gib and a == frozenset(avisos)


@pytest.mark.parametrize(
    "texto",
    [
        "0",
        "0 GiB",
        "0,0",
        "ninguno",
        "Ninguna",
        "NINGUNO",
        "sin disco",
        "Sin Disco",
        "sin_disco",
        "  ninguno  ",
    ],
)
def test_disco_cero_o_ninguno_es_sin_disco(texto):
    assert unidades.disco_gib(texto) == (None, frozenset())


@pytest.mark.parametrize(
    "texto", ["0,5", "0.5", "512 MiB", "1500 MiB", "2,5", "1,5 GiB", "100 MiB"]
)
def test_disco_que_no_es_un_numero_entero_de_gib_es_error(texto):
    """CA-C04.3: «Los discos se miden en GiB enteros (mínimo 1)»."""
    assert _invalido(unidades.disco_gib, texto).regla == "E-M11.gib_no_entero"


@pytest.mark.parametrize("texto", ["1.000", "1,000", "1.024,5", "100.000"])
def test_disco_con_miles_ambiguo_es_v_m08(texto):
    assert _invalido(unidades.disco_gib, texto).regla == "V-M08"


@pytest.mark.parametrize(
    "texto", ["abc", "-5", "+5", "1e2", "0x40", "NaN", "", "ninguno extra", "sin"]
)
def test_disco_no_numerico(texto):
    assert _invalido(unidades.disco_gib, texto).regla == "E-M11.no_numero"


def test_disco_con_unidad_desconocida():
    assert _invalido(unidades.disco_gib, "40 KB").regla == "E-M11.unidad"


def test_unidad_del_encabezado_en_disco():
    assert unidades.disco_gib("2048", "mib") == (2, frozenset())
    assert unidades.disco_gib("40", "gib") == (40, frozenset())
    assert unidades.disco_gib("40 GiB", "mib") == (40, frozenset())


# --- Enteros (CA-C04.6) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        ("2", 2),
        ("2.0", 2),
        ("2,0", 2),
        ("  2  ", 2),
        ('"2"', 2),
        ("0", 0),
        ("129", 129),
        ("100", 100),
        ("999999999", 999999999),
        ("4095", 4095),
        ("007", 7),
    ],
)
def test_enteros_validos(texto, valor):
    assert unidades.entero(texto) == valor


@pytest.mark.parametrize("texto", ["2.5", "2,5", "0.1", "1.0001"])
def test_enteros_con_decimales_no_nulos(texto):
    assert _invalido(unidades.entero, texto).regla == "E-M11.no_entero"


@pytest.mark.parametrize(
    "texto", ["abc", "dos", "-1", "+1", "1e3", "0x10", "NaN", "Infinity", "2 GiB", "2x", "", "٣"]
)
def test_enteros_no_numericos(texto):
    assert _invalido(unidades.entero, texto).regla == "E-M11.no_numero"


@pytest.mark.parametrize("texto", ["1.000", "4.095", "1,000", "1.234.567", "2.000,5"])
def test_enteros_con_miles_ambiguo_son_v_m08(texto):
    """vlan ``4.095``, vmid ``1.000``..."""
    assert _invalido(unidades.entero, texto).regla == "V-M08"


# --- Enumeraciones (CA-C04.10) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("seabios", Firmware.SEABIOS), ("SeaBIOS", Firmware.SEABIOS), ("BIOS", Firmware.SEABIOS), ("bios", Firmware.SEABIOS),  # noqa: E501
     ("ovmf", Firmware.OVMF), ("OVMF", Firmware.OVMF), ("UEFI", Firmware.OVMF), ("uefi", Firmware.OVMF), ("  Uefi ", Firmware.OVMF), ('"ovmf"', Firmware.OVMF)],  # noqa: E501
)  # fmt: skip
def test_firmware_acepta_alias_sin_distinguir_mayusculas(texto, esperado):
    assert unidades.firmware(texto) is esperado


@pytest.mark.parametrize("texto", ["legacy", "efi", "", "seabios2", "uefi-secure"])
def test_firmware_invalido_lista_los_valores_validos(texto):
    e = _invalido(unidades.firmware, texto)
    assert e.regla == "E-M11.valor_no_admitido"
    assert (
        "ovmf" in e.params["validos"] and "seabios" in e.params["validos"] and e.params["ejemplo"]
    )


@pytest.mark.parametrize("texto", ["virtio", "VirtIO", "VIRTIO", "e1000", "E1000", " e1000 "])
def test_modelo_de_red_valido(texto):
    assert unidades.modelo_red(texto) in {ModeloRed.VIRTIO, ModeloRed.E1000}
    assert (
        unidades.modelo_red("E1000") is ModeloRed.E1000
        and unidades.modelo_red("VirtIO") is ModeloRed.VIRTIO
    )


@pytest.mark.parametrize("texto", ["rtl8139", "vmxnet3", "", "virtio-net"])
def test_modelo_de_red_invalido(texto):
    e = _invalido(unidades.modelo_red, texto)
    assert e.regla == "E-M11.valor_no_admitido" and "virtio" in e.params["validos"]


def test_los_enums_ignoran_acentos():
    assert unidades.firmware("ÜEFI".replace("Ü", "U")) is Firmware.OVMF  # sin diéresis
    assert unidades.modelo_red("VÍRTIO".replace("Í", "I")) is ModeloRed.VIRTIO


# --- Pureza ---------------------------------------------------------------------------------------


def test_las_conversiones_son_puras_y_deterministas():
    for _ in range(3):
        assert unidades.memoria_mib("1,5") == (1536, frozenset({GIB_ASUMIDO, COMA}))
        assert unidades.disco_gib("40") == (40, frozenset({GIB_ASUMIDO}))


def test_valor_invalido_es_value_error_con_regla_y_params():
    e = _invalido(unidades.entero, "x")
    assert isinstance(e, ValueError) and e.regla == "E-M11.no_numero" and isinstance(e.params, dict)


def test_numeros_enormes_no_hacen_nada_raro():
    assert unidades.entero("9" * 30) == int("9" * 30)
    assert unidades.memoria_mib("9" * 30)[0] == int("9" * 30) * 1024
