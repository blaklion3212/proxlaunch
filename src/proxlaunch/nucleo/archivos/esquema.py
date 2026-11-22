"""Esquema estricto de archivos (docs/arquitectura/mvp3.md §3.3 y §5.3).

Tipos compartidos (``ErrorCampo``, ``ErrorArchivo``, ``AvisoArchivo``...) y ``LectorEsquema``:
validación por tipo REAL (un booleano no es entero, un decimal no es entero, una cadena no es
número), rango y longitud, con lista blanca de claves. Las claves que parecen credenciales se
descartan SIN leer su valor y las desconocidas se descartan y se cuentan.
"""

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from proxlaunch.nucleo.archivos.constantes import LONG_NOMBRE_PERFIL, MAX_LONG_TEXTO
from proxlaunch.nucleo.archivos.texto import (
    MOTIVO_LONGITUD,
    analizar_texto,
    contiene_token,
    validar_nombre,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch


class MotivoCampo(StrEnum):
    """Por qué un campo del archivo no pasa el esquema."""

    REQUERIDO = "requerido"
    TIPO = "tipo"
    RANGO = "rango"
    LONGITUD = "longitud"
    ENUM = "enum"
    TEXTO_NO_VALIDO = "texto_no_valido"
    TOKEN = "token"
    DEMASIADOS = "demasiados"
    DUPLICADO = "duplicado"


@dataclass(frozen=True)
class ErrorCampo:
    """Un campo inválido: ruta (``"discos[1].tamano_gib"``), motivo y parámetros."""

    ruta: str
    motivo: MotivoCampo
    params: dict[str, str] = field(default_factory=dict)


class ErrorArchivo(ErrorProxLaunch):
    """E-M04 con la lista completa de errores de campo (CA-G03.3).

    ``params["campo"]`` es la ruta del primer error y ``params["n"]`` el total.
    """

    def __init__(
        self,
        errores: tuple[ErrorCampo, ...],
        params: dict[str, str] | None = None,
        detalle_tecnico: str = "",
    ) -> None:
        base = {"campo": errores[0].ruta if errores else "", "n": str(len(errores))}
        base.update(params or {})
        super().__init__(CodigoError.ARCHIVO_DANADO, base, detalle_tecnico)
        self.errores = errores


class CodigoAvisoArchivo(StrEnum):
    """Avisos no bloqueantes al leer un archivo (nunca incluyen valores del usuario)."""

    CAMPOS_DESCONOCIDOS = "campos_desconocidos"  # CA-X01.6: params n
    CREDENCIAL_IGNORADA = "credencial_ignorada"  # E-M16 / CA-X04.2: params n
    MIGRADO = "migrado"  # CA-X01.3: params desde, hasta
    COLUMNA_NO_USADA = "columna_no_usada"  # CA-C03.3: params columna (saneada y recortada)
    GIB_ASUMIDO = "gib_asumido"  # CA-C05.6, una vez por columna y archivo
    DECIMAL_COMA = "decimal_coma"
    GB_COMO_GIB = "gb_como_gib"
    # Fase B (RF-B0.8, RF-B6.5): sin parámetros; nunca llevan valores del usuario.
    CONTRASENA_NO_GUARDADA = "contrasena_no_guardada"  # el lote tenía contraseña y no se guardó
    CSV_CON_CONTRASENAS = "csv_con_contrasenas"  # el CSV trae la columna de contraseñas


@dataclass(frozen=True)
class AvisoArchivo:
    codigo: CodigoAvisoArchivo
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Envoltura:
    """Raíz de un archivo propio ya verificada: formato, versión original y contenido."""

    formato: str
    version_original: int
    contenido: dict[str, object]
    avisos: tuple[AvisoArchivo, ...] = ()


# --- Lectura estricta ------------------------------------------------------------------

E = TypeVar("E", bound=StrEnum)

# Fragmentos (ya normalizados: minúsculas, sin acentos ni separadores) que delatan una credencial.
_FRAGMENTOS_CREDENCIAL = (
    "token",
    "password",
    "contrasena",
    "secreto",
    "secret",
    "ticket",
    "csrf",
    "apikey",
    "credencial",
)
MAX_ERRORES_CAMPO = 1000  # tope de errores que acumula un lector (el archivo ya está acotado)


def es_clave_credencial(nombre: str) -> bool:
    """Indica si una clave o encabezado parece una credencial (CA-X04.2).

    Se normaliza (minúsculas, sin acentos, sin separadores): ``API_Key`` → ``apikey``.
    """
    if not isinstance(nombre, str):
        return False
    descompuesto = unicodedata.normalize("NFD", nombre.casefold())
    normal = "".join(c for c in descompuesto if c.isalnum())  # los acentos (Mn) no son alnum
    return any(f in normal for f in _FRAGMENTOS_CREDENCIAL)


def _ruta_de(ruta: str, clave: str) -> str:
    return f"{ruta}.{clave}" if ruta else clave


def combinar_avisos(avisos: Iterable[AvisoArchivo]) -> tuple[AvisoArchivo, ...]:
    """Suma los avisos con contador ``n`` del mismo código (desconocidos, credenciales).

    El resto de avisos se conserva tal cual, en orden de aparición.
    """
    conteos: dict[CodigoAvisoArchivo, int] = {}
    otros: list[AvisoArchivo] = []
    orden: list[CodigoAvisoArchivo] = []
    for a in avisos:
        if a.codigo in (
            CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS,
            CodigoAvisoArchivo.CREDENCIAL_IGNORADA,
        ):
            if a.codigo not in conteos:
                orden.append(a.codigo)
            conteos[a.codigo] = conteos.get(a.codigo, 0) + int(a.params.get("n", "0"))
        else:
            otros.append(a)
    sumados = [AvisoArchivo(c, {"n": str(conteos[c])}) for c in orden if conteos[c] > 0]
    return (*sumados, *otros)


class LectorEsquema:
    """Acumula los errores de un archivo mientras se lee campo a campo.

    ``ruta`` es siempre la ruta del OBJETO que contiene la clave (``""`` en la raíz); la ruta
    del campo se forma como ``f"{ruta}.{clave}"``. Los métodos devuelven ``None`` ante un
    error (anotado en ``errores``) o un ``nulo`` permitido: quien construye el modelo
    comprueba ``errores`` al final con ``fallar_si_errores``.
    """

    def __init__(self) -> None:
        self.errores: list[ErrorCampo] = []
        self._desconocidas = 0
        self._credenciales = 0
        self._contrasena_no_guardada = False

    # --- Avisos y errores ---

    def avisos(self) -> tuple[AvisoArchivo, ...]:
        """Avisos acumulados: campos desconocidos, credenciales ignoradas (solo contadores) y, en
        la fase B, el indicador de contraseña no guardada."""
        res: list[AvisoArchivo] = []
        if self._desconocidas:
            res.append(
                AvisoArchivo(CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS, {"n": str(self._desconocidas)})
            )
        if self._credenciales:
            res.append(
                AvisoArchivo(CodigoAvisoArchivo.CREDENCIAL_IGNORADA, {"n": str(self._credenciales)})
            )
        if self._contrasena_no_guardada:
            res.append(AvisoArchivo(CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA))
        return tuple(res)

    def marcar_contrasena_no_guardada(self) -> None:
        """Anota que el archivo indica «tenía contraseña» (``con_acceso_local``, RF-B0.8)."""
        self._contrasena_no_guardada = True

    def error(self, ruta: str, motivo: MotivoCampo, **params: str) -> None:
        """Anota un error de campo (hasta ``MAX_ERRORES_CAMPO``)."""
        if len(self.errores) < MAX_ERRORES_CAMPO:
            self.errores.append(ErrorCampo(ruta, motivo, dict(params)))

    def fallar_si_errores(self) -> None:
        """Lanza ``ErrorArchivo`` (E-M04) con la lista completa si hubo algún error."""
        if self.errores:
            raise ErrorArchivo(tuple(self.errores))

    # --- Estructuras ---

    def objeto(self, valor: object, ruta: str, claves: frozenset[str]) -> dict[str, object] | None:
        """Verifica que ``valor`` sea un objeto y devuelve solo las claves de la lista blanca.

        Las claves con aspecto de credencial se descartan sin leer su valor y se cuentan;
        las desconocidas también se descartan y se cuentan (CA-X01.6).
        """
        if not isinstance(valor, dict):
            self.error(ruta, MotivoCampo.TIPO)
            return None
        limpio: dict[str, object] = {}
        for clave in valor:
            if es_clave_credencial(clave):
                self._credenciales += 1
            elif clave in claves:
                limpio[clave] = valor[clave]
            else:
                self._desconocidas += 1
        return limpio

    def _ausente(
        self, obj: Mapping[str, object], clave: str, ruta: str, requerido: bool, hay_defecto: bool
    ) -> bool:
        """True si la clave falta (y ya se anotó el error si era obligatoria)."""
        if clave in obj:
            return False
        if requerido and not hay_defecto:
            self.error(_ruta_de(ruta, clave), MotivoCampo.REQUERIDO)
        return True

    def entero(
        self,
        obj: Mapping[str, object],
        clave: str,
        ruta: str,
        *,
        minimo: int | None = None,
        maximo: int | None = None,
        nulo: bool = False,
        requerido: bool = True,
        defecto: int | None = None,
    ) -> int | None:
        """Entero REAL (ni booleano ni decimal, aunque sea ``2.0``) dentro del rango."""
        if self._ausente(obj, clave, ruta, requerido, defecto is not None):
            return defecto
        valor = obj[clave]
        campo = _ruta_de(ruta, clave)
        if valor is None and nulo:
            return None
        if isinstance(valor, bool) or not isinstance(valor, int):
            self.error(campo, MotivoCampo.TIPO)
            return None
        if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
            self.error(
                campo,
                MotivoCampo.RANGO,
                minimo="" if minimo is None else str(minimo),
                maximo="" if maximo is None else str(maximo),
            )
            return None
        return valor

    def booleano(
        self,
        obj: Mapping[str, object],
        clave: str,
        ruta: str,
        *,
        requerido: bool = True,
        defecto: bool | None = None,
    ) -> bool | None:
        if self._ausente(obj, clave, ruta, requerido, defecto is not None):
            return defecto
        valor = obj[clave]
        if not isinstance(valor, bool):
            self.error(_ruta_de(ruta, clave), MotivoCampo.TIPO)
            return None
        return valor

    def texto(
        self,
        obj: Mapping[str, object],
        clave: str,
        ruta: str,
        *,
        minimo: int = 0,
        maximo: int = MAX_LONG_TEXTO,
        multilinea: bool = False,
        tabulador: bool = False,
        nulo: bool = False,
        requerido: bool = True,
        sin_token: bool = False,
        defecto: str | None = None,
    ) -> str | None:
        """Cadena segura (NFC, sin control ni dirección de texto) de ``minimo`` a ``maximo``.

        ``sin_token`` rechaza texto que parezca un API Token (V-M05). Devuelve el texto
        normalizado a NFC (no lo recorta).
        """
        if self._ausente(obj, clave, ruta, requerido, defecto is not None):
            return defecto
        valor = obj[clave]
        campo = _ruta_de(ruta, clave)
        if valor is None and nulo:
            return None
        if not isinstance(valor, str):
            self.error(campo, MotivoCampo.TIPO)
            return None
        texto, motivo = analizar_texto(
            valor, maximo=maximo, multilinea=multilinea, tabulador=tabulador
        )
        if motivo == MOTIVO_LONGITUD:
            self.error(campo, MotivoCampo.LONGITUD, maximo=str(maximo))
            return None
        if motivo is not None:
            self.error(campo, MotivoCampo.TEXTO_NO_VALIDO)
            return None
        if len(texto) < minimo:
            self.error(campo, MotivoCampo.LONGITUD, minimo=str(minimo))
            return None
        if sin_token and contiene_token(texto):
            self.error(campo, MotivoCampo.TOKEN)
            return None
        return texto

    def nombre(
        self,
        obj: Mapping[str, object],
        clave: str,
        ruta: str,
        *,
        maximo: int = LONG_NOMBRE_PERFIL,
        requerido: bool = True,
    ) -> str | None:
        """Nombre de perfil o de lote (V-M01 sin unicidad, V-M04, V-M05), recortado y en NFC."""
        if self._ausente(obj, clave, ruta, requerido, False):
            return None
        valor = obj[clave]
        campo = _ruta_de(ruta, clave)
        if not isinstance(valor, str):
            self.error(campo, MotivoCampo.TIPO)
            return None
        normalizado, regla = validar_nombre(valor, maximo=maximo)
        if regla is None:
            return normalizado
        motivo = {
            "V-M01": MotivoCampo.LONGITUD,
            "V-M04": MotivoCampo.TEXTO_NO_VALIDO,
            "V-M05": MotivoCampo.TOKEN,
        }[regla]
        self.error(campo, motivo, regla=regla, maximo=str(maximo))
        return None

    def enumerado(
        self,
        obj: Mapping[str, object],
        clave: str,
        ruta: str,
        tipo: type[E],
        *,
        requerido: bool = True,
        defecto: E | None = None,
    ) -> E | None:
        """Valor exacto de una enumeración (sin mayúsculas ni conversiones)."""
        if self._ausente(obj, clave, ruta, requerido, defecto is not None):
            return defecto
        valor = obj[clave]
        campo = _ruta_de(ruta, clave)
        if not isinstance(valor, str):
            self.error(campo, MotivoCampo.TIPO)
            return None
        try:
            return tipo(valor)
        except ValueError:
            self.error(campo, MotivoCampo.ENUM, validos=", ".join(str(m.value) for m in tipo))
            return None

    def lista(
        self,
        obj: Mapping[str, object],
        clave: str,
        ruta: str,
        *,
        maximo: int,
        requerido: bool = True,
        minimo: int = 0,
    ) -> list[object] | None:
        """Lista de a lo sumo ``maximo`` elementos (y al menos ``minimo``)."""
        if self._ausente(obj, clave, ruta, requerido, False):
            return None
        valor = obj[clave]
        campo = _ruta_de(ruta, clave)
        if not isinstance(valor, list):
            self.error(campo, MotivoCampo.TIPO)
            return None
        if len(valor) > maximo:
            self.error(campo, MotivoCampo.DEMASIADOS, maximo=str(maximo), n=str(len(valor)))
            return None
        if len(valor) < minimo:
            self.error(campo, MotivoCampo.LONGITUD, minimo=str(minimo))
            return None
        return valor
