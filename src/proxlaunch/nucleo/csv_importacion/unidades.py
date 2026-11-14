"""Números, unidades y enumeraciones de las celdas del CSV (RF-C04, §6.6.1).

Aritmética exacta con ``Fraction``. Los errores de celda son ``ValorInvalido`` (con la regla
y los parámetros para el mensaje); el intérprete los convierte en ``ProblemaCelda``.
Se rechazan signo, exponente, hexadecimal, ``NaN`` e ``Infinity``. Un valor con ambos
separadores, con varios separadores o con un único separador seguido de exactamente tres
dígitos es ambiguo (V-M08) y nunca se interpreta en silencio.
"""

import re
import unicodedata
from fractions import Fraction
from typing import TypeVar

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo
from proxlaunch.nucleo.modelos.vm import Firmware, ModeloRed

_T = TypeVar("_T")

_RECORTE = " \t \"'“”‘’"
_NUMERO = re.compile(r"([0-9][0-9.,]*)[ \t ]*([A-Za-z]*)", re.ASCII)
_ENTERO_MILES = re.compile(r"[0-9]+[.,][0-9]{3}")

# Factor hacia MiB y marca de «unidad decimal tratada como binaria» (CT-6).
_UNIDADES: dict[str, tuple[int, bool]] = {
    "m": (1, False),
    "mib": (1, False),
    "mb": (1, True),
    "g": (1024, False),
    "gib": (1024, False),
    "gb": (1024, True),
    "t": (1024 * 1024, False),
    "tib": (1024 * 1024, False),
    "tb": (1024 * 1024, True),
}
_SIN_DISCO = frozenset({"ninguno", "ninguna", "sin disco", "sin_disco"})
_FIRMWARE = {
    "seabios": Firmware.SEABIOS,
    "bios": Firmware.SEABIOS,
    "ovmf": Firmware.OVMF,
    "uefi": Firmware.OVMF,
}
_MODELOS_RED = {"virtio": ModeloRed.VIRTIO, "e1000": ModeloRed.E1000}


class ValorInvalido(ValueError):
    """Celda que no se puede interpretar. ``regla`` p. ej. ``E-M11.no_numero`` o ``V-M08``."""

    def __init__(self, regla: str, params: dict[str, str] | None = None) -> None:
        super().__init__(regla)
        self.regla = regla
        self.params: dict[str, str] = dict(params) if params else {}


def _uno_de_miles(numero: str) -> str:
    """Lectura «decimal» de un número de miles ambiguo: ``1.000`` -> ``1``."""
    return numero.replace(",", ".").rstrip("0").rstrip(".") or "0"


def _recortar(texto: str) -> str:
    return texto.strip(_RECORTE)


def _clave(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar enumeraciones."""
    sin = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return " ".join(sin.casefold().split())


def _separar(texto: str, ejemplo: str) -> tuple[Fraction, str, bool]:
    """Parte «número [unidad]»: ``(valor exacto, unidad en minúsculas, usó coma decimal)``."""
    t = _recortar(texto)
    m = _NUMERO.fullmatch(t)
    if m is None:
        raise ValorInvalido("E-M11.no_numero", {"ejemplo": ejemplo})
    numero, unidad = m.group(1), m.group(2).lower()
    if "." in numero and "," in numero:
        raise ValorInvalido("V-M08", {"motivo": "ambos", "valor": numero})
    separadores = numero.count(".") + numero.count(",")
    if (
        separadores == 1
        and _ENTERO_MILES.fullmatch(numero)
        and int(numero.replace(",", ".").split(".")[0]) != 0  # «0,125» es decimal, no ambiguo
    ):
        # «1.000» / «1,000»: ¿mil o uno? (V-M08)
        raise ValorInvalido(
            "V-M08",
            {
                "motivo": "miles",
                "valor": numero,
                "mil": numero.replace(".", "").replace(",", ""),
                "uno": _uno_de_miles(numero),
            },
        )
    if separadores > 1:
        raise ValorInvalido("V-M08", {"motivo": "miles", "valor": numero})
    if numero.endswith((".", ",")):
        raise ValorInvalido("E-M11.no_numero", {"ejemplo": ejemplo})
    coma = "," in numero
    return Fraction(numero.replace(",", ".")), unidad, coma


def entero(texto: str) -> int:
    """Entero de ``cpu``, ``sockets``, ``vmid``, ``vlan`` (``2`` y ``2.0`` valen; ``2.5`` no)."""
    valor, unidad, _ = _separar(texto, "2")
    if unidad:
        raise ValorInvalido("E-M11.no_numero", {"ejemplo": "2"})
    if valor.denominator != 1:
        raise ValorInvalido("E-M11.no_entero", {"ejemplo": "2"})
    return int(valor)


def _avisos(unidad: str, coma: bool, decimal_binario: bool) -> frozenset[CodigoAvisoArchivo]:
    avisos: set[CodigoAvisoArchivo] = set()
    if not unidad:
        avisos.add(CodigoAvisoArchivo.GIB_ASUMIDO)
    if decimal_binario:
        avisos.add(CodigoAvisoArchivo.GB_COMO_GIB)
    if coma:
        avisos.add(CodigoAvisoArchivo.DECIMAL_COMA)
    return frozenset(avisos)


def memoria_mib(
    texto: str, unidad_encabezado: str | None = None
) -> tuple[int, frozenset[CodigoAvisoArchivo]]:
    """Memoria en MiB. Sin unidad = GiB (P-M06). El resultado debe ser entero (CA-C04.2).

    ``unidad_encabezado`` (p. ej. ``"mib"`` por una columna ``memoria_mib``) sustituye al GiB
    por defecto de un número sin unidad; una unidad escrita en la celda manda sobre ella.
    """
    valor, unidad, coma = _separar(texto, "4 GiB")
    if unidad and unidad not in _UNIDADES:
        raise ValorInvalido(
            "E-M11.unidad", {"unidad": unidad, "validas": "MiB, GiB, TiB, M, G, T, MB, GB, TB"}
        )
    if not unidad and unidad_encabezado in _UNIDADES:
        factor, decimal_binario = _UNIDADES[unidad_encabezado]
        unidad = unidad_encabezado  # la unidad no se «asume»: la fija el encabezado
    else:
        factor, decimal_binario = _UNIDADES.get(unidad, (1024, False))
    mib = valor * factor
    if mib.denominator != 1:
        redondeado = max(round(mib), 1)
        raise ValorInvalido("E-M11.mib_no_entero", {"ejemplo": f"{redondeado} MiB"})
    return int(mib), _avisos(unidad, coma, decimal_binario)


def disco_gib(
    texto: str, unidad_encabezado: str | None = None
) -> tuple[int | None, frozenset[CodigoAvisoArchivo]]:
    """Disco en GiB enteros (≥ 1). ``None`` = sin disco (``0``, ``ninguno``, ``sin disco``).

    ``unidad_encabezado`` actúa como en ``memoria_mib``.
    """
    if _clave(_recortar(texto)) in _SIN_DISCO:
        return None, frozenset()
    valor, unidad, coma = _separar(texto, "40")
    if unidad and unidad not in _UNIDADES:
        raise ValorInvalido(
            "E-M11.unidad", {"unidad": unidad, "validas": "MiB, GiB, TiB, M, G, T, MB, GB, TB"}
        )
    if valor == 0:
        return None, frozenset()
    if not unidad and unidad_encabezado in _UNIDADES:
        factor, decimal_binario = _UNIDADES[unidad_encabezado]
        unidad = unidad_encabezado
    else:
        factor, decimal_binario = _UNIDADES.get(unidad, (1024, False))
    gib = valor * factor / 1024
    if gib.denominator != 1:
        raise ValorInvalido("E-M11.gib_no_entero", {"ejemplo": "40"})
    return int(gib), _avisos(unidad, coma, decimal_binario)


def _enumeracion(texto: str, tabla: dict[str, _T], validos: str, ejemplo: str) -> _T:
    clave = _clave(_recortar(texto))
    if clave in tabla:
        return tabla[clave]
    raise ValorInvalido("E-M11.valor_no_admitido", {"validos": validos, "ejemplo": ejemplo})


def firmware(texto: str) -> Firmware:
    """``seabios``/``bios`` o ``ovmf``/``uefi``, sin distinguir mayúsculas ni acentos."""
    return _enumeracion(texto, _FIRMWARE, "seabios, bios, ovmf, uefi", "ovmf")


def modelo_red(texto: str) -> ModeloRed:
    """``virtio`` o ``e1000``, sin distinguir mayúsculas."""
    return _enumeracion(texto, _MODELOS_RED, "virtio, e1000", "virtio")
