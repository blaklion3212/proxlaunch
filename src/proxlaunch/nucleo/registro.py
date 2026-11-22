"""Registro (log) rotativo con filtro que enmascara secretos (RNF-06, CA-08.5)."""

from __future__ import annotations

import contextlib
import faulthandler
import logging
import os
import re
import sys
import threading
import traceback
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import IO, Any
from urllib.parse import quote, quote_plus

from proxlaunch.nucleo.persistencia.rutas import crear_carpeta_privada

MASCARA = "***"
NOMBRE_LOGGER = "proxlaunch"
ARCHIVO_LOG = "proxlaunch.log"
ARCHIVO_FALLO_NATIVO = "fallo-nativo.txt"
# Mensajes idénticos seguidos de Qt que se registran antes de resumirlos.
MAX_MENSAJES_QT_REPETIDOS = 20
# Excepciones de Python idénticas (tipo + archivo + línea) que se registran antes de suprimirlas.
MAX_EXCEPCIONES_REPETIDAS = 20
# Claves distintas que se rastrean como máximo (acota la memoria ante avalanchas variadas).
_MAX_CLAVES_EXCEPCION = 500
# Bytes de fallo-nativo.txt que se conservan al rotarlo a .1.
MAX_BYTES_FALLO_PREVIO = 256 * 1024

# Nombres de campo cuyo valor siempre se enmascara (cabeceras, parámetros de formulario,
# claves de diccionarios o JSON). Cubre `clave=valor`, `clave: valor` y `'clave': 'valor'`.
_CAMPOS = (
    "tfa-challenge|tfa_challenge|password|contrasena|otp|tfa|ticket|"
    "CSRFPreventionToken|PVEAuthCookie|PVEAPIToken"
)
_RE_CAMPO = re.compile(
    rf"""(?ix)(?<![A-Za-z])({_CAMPOS})(["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s&;,}}"']+)"""
)
# Cabeceras que se enmascaran hasta el fin del valor (puede contener espacios).
_RE_CABECERA = re.compile(
    r"""(?i)(?<![A-Za-z])((?:set-)?cookie|authorization|proxy-authorization)(["']?\s*[:=]\s*)["']?[^\r\n"',}]+"""
)

# Códigos de segundo factor con prefijo (totp:123456, recovery:xxxx-..., y su forma
# codificada en URL totp%3A...). No toca `"recovery": [..]` del desafío (lleva comillas).
_RE_CODIGO_TFA = re.compile(r"(?i)\b(totp|recovery)(:|%3A)[^\s&;,\"'}]+")

# Token de API genérico (``usuario@realm!id=secreto``) en cualquier parte del texto: se oculta lo
# que va tras el «=» (SEG-A-07). Cuantificadores acotados: sin retroceso cuadrático.
_RE_TOKEN_GENERICO = re.compile(
    r"""([^@!=\s]{1,128}@[^@!=\s]{1,128}![A-Za-z0-9._-]{1,128}=)[^\s"'&;,}]+"""
)

_lock = threading.Lock()
_secretos: set[str] = set()


def registrar_secreto(valor: str) -> None:
    """Registra un valor concreto para que se enmascare en cualquier mensaje del log
    (incluidas sus variantes codificadas para URL). Los vacíos se ignoran."""
    if not valor:
        return
    with _lock:
        _secretos.update({valor, quote(valor, safe=""), quote_plus(valor)})


def olvidar_secretos() -> None:
    """Vacía la lista de secretos registrados (útil en pruebas)."""
    with _lock:
        _secretos.clear()


def enmascarar(texto: str) -> str:
    """Devuelve `texto` con todos los secretos conocidos sustituidos por `***`."""
    texto = _RE_CABECERA.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", texto)
    texto = _RE_CAMPO.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", texto)
    texto = _RE_CODIGO_TFA.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASCARA}", texto)
    if "@" in texto and "!" in texto and "=" in texto:  # evita la expresión en textos sin token
        texto = _RE_TOKEN_GENERICO.sub(lambda m: f"{m.group(1)}{MASCARA}", texto)
    with _lock:
        conocidos = sorted(_secretos, key=len, reverse=True)
    for s in conocidos:
        texto = texto.replace(s, MASCARA)
    return texto


_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Igual, pero conserva el salto de línea (las trazas son multilínea de forma legítima).
_RE_CONTROL_SALVO_NL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]")


def _escapar_control(texto: str) -> str:
    """Sustituye los caracteres de control (``Cc``, incluidos ``\\r`` y ``\\n``) por ``\\xNN``."""
    return _RE_CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}", texto)


def _escapar_control_salvo_nl(texto: str) -> str:
    """Como ``_escapar_control`` pero respeta ``\\n``; escapa ``\\r`` y el resto de controles."""
    return _RE_CONTROL_SALVO_NL.sub(lambda m: f"\\x{ord(m.group()):02x}", texto)


class FiltroSecretos(logging.Filter):
    """Enmascara secretos en el mensaje ya formateado, sus argumentos, el texto de las
    excepciones y la traza de pila. Nunca descarta registros."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            mensaje = record.getMessage()
        except Exception:
            mensaje = str(record.msg)
        # Los nombres de archivo u otros datos externos no pueden inyectar líneas falsas (S5).
        record.msg = _escapar_control(enmascarar(mensaje))
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            # Un mensaje de servidor con \r o controles no puede fabricar líneas falsas.
            record.exc_text = _escapar_control_salvo_nl(enmascarar(record.exc_text))
        if record.stack_info:
            record.stack_info = _escapar_control_salvo_nl(enmascarar(record.stack_info))
        return True


class _RotativoPrivado(RotatingFileHandler):
    """Archivo rotativo que en POSIX queda con permisos 0o600 (también tras rotar)."""

    def _open(self):  # noqa: ANN202
        flujo = super()._open()
        if os.name == "posix":
            with contextlib.suppress(OSError):
                os.chmod(self.baseFilename, 0o600)
        return flujo


def configurar_registro(
    directorio: Path | str,
    nivel: int | str = logging.INFO,
    max_bytes: int = 1_000_000,
    copias: int = 5,
) -> logging.Logger:
    """Configura el logger "proxlaunch" con archivo rotativo (1 MB x 5 por defecto) y
    filtro de secretos. Es idempotente: reemplaza el manejador previo si lo hubiera."""
    carpeta = Path(directorio)
    crear_carpeta_privada(carpeta)
    logger = logging.getLogger(NOMBRE_LOGGER)
    for h in list(logger.handlers):
        if getattr(h, "_proxlaunch", False):
            logger.removeHandler(h)
            h.close()
    manejador = _RotativoPrivado(
        carpeta / ARCHIVO_LOG, maxBytes=max_bytes, backupCount=copias, encoding="utf-8"
    )
    manejador._proxlaunch = True  # type: ignore[attr-defined]
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    # El filtro va en el manejador: afecta a los registros de todos los submódulos.
    manejador.addFilter(FiltroSecretos())
    logger.addHandler(manejador)
    logger.setLevel(nivel)
    logger.propagate = False  # evita que un manejador raíz escriba sin filtrar
    return logger


def cerrar_registro() -> None:
    """Quita y cierra los manejadores que añadió ``configurar_registro``.

    Libera el archivo de log (en Windows impide borrar su carpeta mientras siga abierto).
    """
    logger = logging.getLogger(NOMBRE_LOGGER)
    for h in list(logger.handlers):
        if getattr(h, "_proxlaunch", False):
            logger.removeHandler(h)
            with contextlib.suppress(Exception):
                h.close()


# --- Captura de fallos inesperados -------------------------------------------------------

_log_fallos = logging.getLogger(f"{NOMBRE_LOGGER}.fallos")

# Indicios de una caída real en el volcado de faulthandler. Un volcado "Windows fatal exception:
# code 0x..." a secas es una excepción nativa (p. ej. de C++) que Qt o el sistema manejaron.
_RE_INDICIOS_CAIDA = re.compile(
    r"(?i)access violation|stack overflow|Fatal Python error|Segmentation fault|Aborted|"
    r"illegal instruction|bus error|floating.point exception|privileged instruction|"
    r"in.page error|int(?:eger)? divide by zero"
)
_VEREDICTO_CAIDA = "caida"
_VEREDICTO_MANEJADAS = "manejadas"


class _EstadoCaptura:
    """Hooks previos y archivo de faulthandler mientras la captura está instalada."""

    def __init__(self, directorio: Path) -> None:
        self.directorio = directorio
        self.excepthook: Callable[..., Any] = sys.__excepthook__
        self.hilo_hook: Callable[..., Any] | None = None
        self.unraisable: Callable[..., Any] | None = None
        self.faulthandler_activo = False
        self.archivo_fallo: IO[str] | None = None
        self.restaurar_qt: Callable[[], None] | None = None
        self.receptor_qt: _ReceptorQt | None = None
        self.hook_sys: Callable[..., Any] | None = None
        self.hook_hilo: Callable[..., Any] | None = None
        self.hook_unraisable: Callable[..., Any] | None = None
        self._bloqueo = threading.Lock()
        # clave -> (descripción, veces vista)
        self._repetidas: dict[tuple[str, str, int], list[Any]] = {}

    def contar(
        self, tipo: type[BaseException], traza: TracebackType | None
    ) -> tuple[bool, str | None]:
        """Cuenta una excepción por (tipo, archivo, línea del último frame).

        Devuelve ``(registrar, resumen)``: ``registrar`` es False tras superar el máximo y
        ``resumen`` es un texto periódico (a las 100, 1000, 10000... repeticiones).
        """
        archivo, linea = "", 0
        while traza is not None:
            archivo, linea = traza.tb_frame.f_code.co_filename, traza.tb_lineno
            traza = traza.tb_next
        clave = (f"{tipo.__module__}.{tipo.__qualname__}", archivo, linea)
        with self._bloqueo:
            entrada = self._repetidas.get(clave)
            if entrada is None:
                if len(self._repetidas) >= _MAX_CLAVES_EXCEPCION:
                    return True, None
                entrada = self._repetidas[clave] = [0, 0]
            entrada[0] += 1
            veces = entrada[0]
            if veces <= MAX_EXCEPCIONES_REPETIDAS:
                return True, None
            resumen = None
            if _es_potencia_de_diez(veces):
                entrada[1] = veces
                resumen = _texto_resumen(clave, veces)
            return False, resumen

    def resumenes_pendientes(self) -> list[str]:
        """Resúmenes de las excepciones suprimidas cuyo último resumen quedó desactualizado."""
        with self._bloqueo:
            pendientes = [
                _texto_resumen(clave, entrada[0])
                for clave, entrada in self._repetidas.items()
                if entrada[0] > MAX_EXCEPCIONES_REPETIDAS and entrada[1] != entrada[0]
            ]
            self._repetidas.clear()
        return pendientes


def _es_potencia_de_diez(n: int) -> bool:
    while n >= 10 and n % 10 == 0:
        n //= 10
    return n == 1


def _texto_resumen(clave: tuple[str, str, int], veces: int) -> str:
    return (
        f"Excepción {clave[0]} ({Path(clave[1]).name}:{clave[2]}) repetida "
        f"{veces - MAX_EXCEPCIONES_REPETIDAS} veces más (suprimidas)"
    )


_estado: _EstadoCaptura | None = None
_lock_captura = threading.Lock()


def _banderas_seguras() -> int:
    """``O_NOFOLLOW`` (POSIX) y ``O_BINARY`` (Windows) cuando existen."""
    return getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _abrir_privado(ruta: Path, banderas: int) -> int:
    """Abre ``ruta`` sin seguir enlaces (POSIX) y la deja 0o600 sobre el descriptor."""
    descriptor = os.open(ruta, banderas | _banderas_seguras(), 0o600)
    if sys.platform != "win32":  # mypy entiende sys.platform (os.fchmod no existe en Windows)
        with contextlib.suppress(OSError):
            os.fchmod(descriptor, 0o600)
    return descriptor


def _rotar_fallo_previo(carpeta: Path) -> str | None:
    """Copia a ``.1`` los primeros ``MAX_BYTES_FALLO_PREVIO`` bytes de un ``fallo-nativo.txt``
    previo y devuelve el veredicto (``caida``/``manejadas``), o ``None`` si estaba vacío."""
    ruta = carpeta / ARCHIVO_FALLO_NATIVO
    try:
        descriptor = os.open(ruta, os.O_RDONLY | _banderas_seguras())
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as flujo:
        datos = flujo.read(MAX_BYTES_FALLO_PREVIO)
    if not datos:
        return None
    destino = _abrir_privado(
        carpeta / f"{ARCHIVO_FALLO_NATIVO}.1", os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    )
    with os.fdopen(destino, "wb") as flujo:
        flujo.write(datos)
    texto = datos.decode("utf-8", "replace")
    solo_manejadas = "Windows fatal exception" in texto and not _RE_INDICIOS_CAIDA.search(texto)
    return _VEREDICTO_MANEJADAS if solo_manejadas else _VEREDICTO_CAIDA


def _abrir_archivo_fallo(carpeta: Path) -> tuple[IO[str], str | None]:
    """Abre ``fallo-nativo.txt`` privado (0o600, sin seguir enlaces en POSIX).

    Si traía contenido de un cierre anterior conserva su inicio en ``.1`` (para no perder el
    último fallo) y devuelve en el segundo valor el veredicto sobre ese contenido.
    """
    ruta = carpeta / ARCHIVO_FALLO_NATIVO
    veredicto: str | None = None
    with contextlib.suppress(OSError):
        veredicto = _rotar_fallo_previo(carpeta)
    # Se abre truncando: nunca crece más allá de un solo cierre.
    descriptor = _abrir_privado(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    return os.fdopen(descriptor, "w", encoding="utf-8"), veredicto


def _escribir_stderr(texto: str) -> None:
    """Escribe en stderr el texto ya enmascarado (stderr es None en Windows sin consola)."""
    flujo = sys.stderr
    if flujo is None:
        return
    with contextlib.suppress(Exception):
        flujo.write(enmascarar(texto))
        flujo.flush()


def _trazas(
    tipo: type[BaseException], valor: BaseException | None, traza: TracebackType | None
) -> str:
    return "".join(traceback.format_exception(tipo, valor, traza))


def _crear_hooks(estado: _EstadoCaptura) -> None:
    def registrar(
        tipo: type[BaseException],
        valor: BaseException,
        traza: TracebackType | None,
        nivel: int,
        mensaje: str,
        *args: Any,
    ) -> bool:
        """Registra la excepción salvo que sea una repetición suprimida; True si se registró."""
        registrar_ahora, resumen = estado.contar(tipo, traza)
        with contextlib.suppress(Exception):
            if registrar_ahora:
                _log_fallos.log(nivel, mensaje, *args, exc_info=(tipo, valor, traza))
            if resumen is not None:
                _log_fallos.warning("%s", resumen)
        return registrar_ahora

    def hook_sys(
        tipo: type[BaseException], valor: BaseException, traza: TracebackType | None
    ) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            estado.excepthook(tipo, valor, traza)
            return
        if not registrar(tipo, valor, traza, logging.CRITICAL, "Error no controlado"):
            return
        if estado.excepthook is sys.__excepthook__:
            # El hook por defecto imprimiría sin enmascarar (en Linux, al journal).
            _escribir_stderr(_trazas(tipo, valor, traza))
        elif sys.stderr is not None:
            with contextlib.suppress(Exception):
                estado.excepthook(tipo, valor, traza)

    def hook_hilo(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        nombre = args.thread.name if args.thread is not None else "desconocido"
        if args.exc_value is not None and not registrar(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            logging.CRITICAL,
            "Error no controlado en el hilo %s",
            nombre,
        ):
            return
        if estado.hilo_hook is None or estado.hilo_hook is threading.__excepthook__:
            if args.exc_value is not None:
                _escribir_stderr(
                    f"Exception in thread {nombre}:\n"
                    + _trazas(args.exc_type, args.exc_value, args.exc_traceback)
                )
        elif sys.stderr is not None:
            with contextlib.suppress(Exception):
                estado.hilo_hook(args)

    def hook_unraisable(args: Any) -> None:
        objeto = ""
        with contextlib.suppress(Exception):
            objeto = repr(args.object)[:200]
        mensaje = f"{args.err_msg or 'Excepción no propagable'} (objeto: {objeto})"
        if args.exc_value is not None:
            if not registrar(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                logging.WARNING,
                "Excepción no propagable: %s",
                mensaje,
            ):
                return
            texto = _trazas(args.exc_type, args.exc_value, args.exc_traceback)
        else:
            with contextlib.suppress(Exception):
                _log_fallos.warning("Excepción no propagable: %s", mensaje)
            texto = ""
        if estado.unraisable is None or estado.unraisable is sys.__unraisablehook__:
            _escribir_stderr(f"{mensaje}\n{texto}")
        elif sys.stderr is not None:
            with contextlib.suppress(Exception):
                estado.unraisable(args)

    estado.hook_sys = hook_sys
    estado.hook_hilo = hook_hilo
    estado.hook_unraisable = hook_unraisable


# Receptor de mensajes de Qt: (nivel de logging, categoría o None, texto).
ReceptorMensajesQt = Callable[[int, str | None, str], None]
# Instala un manejador de Qt que alimente al receptor y devuelve la función que lo desinstala.
InstaladorQt = Callable[[ReceptorMensajesQt], Callable[[], None]]


class _ReceptorQt:
    """Registra los mensajes de Qt y resume los idénticos seguidos."""

    def __init__(self) -> None:
        self._log = logging.getLogger(f"{NOMBRE_LOGGER}.qt")
        self._bloqueo = threading.Lock()
        self._clave: str | None = None
        self._cuenta = 0
        self._nivel = logging.WARNING

    def _cerrar_racha(self) -> tuple[int, str] | None:
        """Devuelve el resumen de la racha y la reinicia. Debe llamarse con el bloqueo tomado."""
        extra = self._cuenta - MAX_MENSAJES_QT_REPETIDOS
        resumen = (
            (self._nivel, f"(mensaje de Qt repetido {extra} veces más)") if extra > 0 else None
        )
        self._clave, self._cuenta = None, 0
        return resumen

    def _emitir(self, resumenes: list[tuple[int, str]]) -> None:
        for nivel, texto in resumenes:
            with contextlib.suppress(Exception):
                self._log.log(nivel, "%s", texto)

    def vaciar(self) -> None:
        """Escribe el resumen de la racha pendiente (al desinstalar)."""
        with self._bloqueo:
            resumen = self._cerrar_racha()
        self._emitir([resumen] if resumen else [])

    def __call__(self, nivel: int, categoria: str | None, mensaje: str) -> None:
        texto = f"[{categoria}] {mensaje}" if categoria and categoria != "default" else mensaje
        pendientes: list[tuple[int, str]] = []
        suprimir = False
        # Se calcula con el bloqueo tomado y se escribe fuera: el log puede tardar o reentrar.
        with self._bloqueo:
            if nivel >= logging.CRITICAL:
                # Un mensaje fatal siempre se registra y corta la racha.
                resumen = self._cerrar_racha()
                if resumen:
                    pendientes.append(resumen)
            else:
                clave = f"{nivel}:{texto}"
                if clave == self._clave:
                    self._cuenta += 1
                else:
                    resumen = self._cerrar_racha()
                    if resumen:
                        pendientes.append(resumen)
                    self._clave, self._cuenta, self._nivel = clave, 1, nivel
                suprimir = self._cuenta > MAX_MENSAJES_QT_REPETIDOS
        self._emitir(pendientes)
        if not suprimir:
            with contextlib.suppress(Exception):
                self._log.log(nivel, "%s", texto)
        if nivel >= logging.CRITICAL:
            # Qt abortará al volver: se vacía el registro para no perder la causa.
            for h in logging.getLogger(NOMBRE_LOGGER).handlers:
                with contextlib.suppress(Exception):
                    h.flush()


def instalar_captura_de_fallos(
    directorio: Path | str, instalar_qt: InstaladorQt | None = None
) -> None:
    """Instala la captura de cierres inesperados (idempotente).

    - ``sys.excepthook``, ``threading.excepthook`` y ``sys.unraisablehook`` registran la traza
      (el filtro de secretos del registro la enmascara). Si el hook previo era el de Python
      escriben en stderr la traza enmascarada; si era uno personalizado, lo encadenan.
      Las excepciones idénticas (tipo, archivo y línea) se suprimen tras
      ``MAX_EXCEPCIONES_REPETIDAS`` con un resumen periódico y otro al desinstalar.
    - ``faulthandler`` vuelca la pila de un fallo nativo en ``fallo-nativo.txt`` (privado). Si
      ya había contenido de una ejecución anterior se conserva su inicio en ``.1`` y se avisa en
      el registro (con un aviso suave si solo son excepciones nativas manejadas).
    - Si se pasa ``instalar_qt`` (lo aporta la interfaz: el núcleo no importa PySide6), los
      mensajes de Qt pasan al registro y los idénticos seguidos se resumen.

    Los fallos al preparar faulthandler o Qt se registran como aviso y no se propagan. Una
    segunda llamada con la misma carpeta no hace nada; con otra, reinstala.
    """
    global _estado
    carpeta = Path(directorio)
    veredicto: str | None = None
    with _lock_captura:
        if _estado is not None:
            if _estado.directorio == carpeta:
                return
            _desinstalar_sin_bloqueo()
        crear_carpeta_privada(carpeta)
        estado = _EstadoCaptura(carpeta)
        _crear_hooks(estado)
        estado.excepthook = sys.excepthook
        estado.hilo_hook = threading.excepthook
        estado.unraisable = sys.unraisablehook
        sys.excepthook = estado.hook_sys  # type: ignore[assignment]
        threading.excepthook = estado.hook_hilo  # type: ignore[assignment]
        sys.unraisablehook = estado.hook_unraisable  # type: ignore[assignment]
        # El estado se asigna antes de lo que puede fallar: así siempre se puede desinstalar.
        _estado = estado
        try:
            estado.archivo_fallo, veredicto = _abrir_archivo_fallo(carpeta)
            estado.faulthandler_activo = faulthandler.is_enabled()
            faulthandler.enable(file=estado.archivo_fallo, all_threads=True)
        except Exception as exc:  # noqa: BLE001 - la captura nunca debe impedir arrancar
            _log_fallos.warning("No se pudo preparar %s: %s", ARCHIVO_FALLO_NATIVO, exc)
        if instalar_qt is not None:
            receptor = _ReceptorQt()
            try:
                estado.restaurar_qt = instalar_qt(receptor)
                estado.receptor_qt = receptor
            except Exception as exc:  # noqa: BLE001
                _log_fallos.warning("No se pudo instalar la captura de mensajes de Qt: %s", exc)
    if veredicto == _VEREDICTO_CAIDA:
        _log_fallos.warning(
            "La ejecución anterior terminó con un fallo nativo; ver %s.1", ARCHIVO_FALLO_NATIVO
        )
    elif veredicto == _VEREDICTO_MANEJADAS:
        _log_fallos.info(
            "Se registraron excepciones nativas manejadas en la ejecución anterior "
            "(no indican una caída); ver %s.1",
            ARCHIVO_FALLO_NATIVO,
        )


def _desinstalar_sin_bloqueo(limpio: bool = False) -> None:
    global _estado
    estado = _estado
    if estado is None:
        return
    if sys.excepthook is estado.hook_sys:
        sys.excepthook = estado.excepthook
    if threading.excepthook is estado.hook_hilo and estado.hilo_hook is not None:
        threading.excepthook = estado.hilo_hook
    if sys.unraisablehook is estado.hook_unraisable and estado.unraisable is not None:
        sys.unraisablehook = estado.unraisable
    if estado.restaurar_qt is not None:
        with contextlib.suppress(Exception):
            estado.restaurar_qt()
    if estado.receptor_qt is not None:
        with contextlib.suppress(Exception):
            estado.receptor_qt.vaciar()
    for resumen in estado.resumenes_pendientes():
        with contextlib.suppress(Exception):
            _log_fallos.warning("%s", resumen)
    if estado.archivo_fallo is not None:
        faulthandler.disable()
        if estado.faulthandler_activo and sys.stderr is not None:
            with contextlib.suppress(Exception):
                faulthandler.enable()
        with contextlib.suppress(Exception):
            estado.archivo_fallo.close()
        if limpio:
            # Cierre normal: no hay volcados que conservar (evita falsas alarmas al arrancar).
            with contextlib.suppress(OSError):
                (estado.directorio / ARCHIVO_FALLO_NATIVO).unlink()
    _estado = None


def desinstalar_captura_de_fallos(limpio: bool = False) -> None:
    """Restaura los hooks previos, vacía los resúmenes pendientes y cierra ``fallo-nativo.txt``.

    Con ``limpio=True`` (cierre normal de la app) además elimina ``fallo-nativo.txt``.
    """
    with _lock_captura:
        _desinstalar_sin_bloqueo(limpio)
