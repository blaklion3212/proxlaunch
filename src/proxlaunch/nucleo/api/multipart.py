"""Cuerpo ``multipart/form-data`` en streaming con ``Content-Length`` exacto (MVP 4, §7.2).

Proxmox rechaza la subida sin ``Content-Length`` («upload without content length header not
supported»). ``requests`` pone ``Transfer-Encoding: chunked`` con un iterable sin longitud, pero
con un objeto que define ``__len__`` calcula ``Content-Length`` y envía iterando. Este cuerpo
no carga el archivo en memoria: lee del flujo en bloques de ``tam_lectura`` y entrega bloques
de ``tam_envio`` al socket, comprobando la cancelación entre bloques (D-A2, D-A3).
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import BinaryIO

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.origen.constantes import BLOQUE_ENVIO, CHUNK_SUBIDA

_CRLF = b"\r\n"
# Caracteres que romperían la cabecera de una parte (inyección de cabeceras).
_PROHIBIDOS_CABECERA = ('"', "\r", "\n", "\x00")


class SubidaCancelada(Exception):
    """La lanza el iterador del cuerpo al ver ``cancelado`` (no deriva de ``OSError``: así
    ``urllib3`` no la envuelve y llega intacta al transporte)."""


@dataclass(frozen=True)
class ParteArchivo:
    """Parte de archivo del cuerpo: nombre en el servidor, tamaño exacto y flujo abierto."""

    nombre_archivo: str
    tamano: int
    flujo: BinaryIO
    tipo: str = "application/octet-stream"


def _sin_prohibidos(texto: str, que: str) -> str:
    if any(c in texto for c in _PROHIBIDOS_CABECERA):
        raise ValueError(f"{que} con caracteres no permitidos en una cabecera multipart")
    return texto


class CuerpoMultipart:
    """Cuerpo multipart: campos de texto primero y, al final, la parte ``filename``.

    Args:
        campos: campos de texto, enviados en el orden de inserción del mapeo. pveproxy exige
            el orden fijo ``content``, ``checksum-algorithm``, ``checksum`` (y luego el
            archivo): quien llama es responsable de construirlo en ese orden.
        parte: archivo a enviar. Se envían exactamente ``parte.tamano`` bytes; si el flujo
            acaba antes se lanza ``ARCHIVO_CAMBIO`` (el archivo se truncó) en vez de dejar
            al servidor esperando bytes que no llegarán.
        frontera: ``boundary`` (por defecto aleatorio).
        tam_lectura: tamaño de cada lectura del flujo.
        tam_envio: tamaño de cada trozo entregado al socket (granularidad de la cancelación).
        al_progresar: ``(bytes_del_archivo_enviados, total)`` tras cada trozo.
        cancelado: evento; si se activa, el iterador lanza ``SubidaCancelada``.
        al_leer: recibe cada bloque leído del archivo (para recalcular el sha256 al vuelo).
    """

    def __init__(
        self,
        campos: Mapping[str, str],
        parte: ParteArchivo,
        *,
        frontera: str | None = None,
        tam_lectura: int = CHUNK_SUBIDA,
        tam_envio: int = BLOQUE_ENVIO,
        al_progresar: Callable[[int, int], None] | None = None,
        cancelado: threading.Event | None = None,
        al_leer: Callable[[bytes], None] | None = None,
    ) -> None:
        if parte.tamano < 0:
            raise ValueError("tamano negativo")
        if tam_lectura <= 0 or tam_envio <= 0:
            raise ValueError("los tamaños de bloque deben ser positivos")
        self._frontera = frontera or secrets.token_hex(24)
        self._parte = parte
        self._tam_lectura = tam_lectura
        self._tam_envio = tam_envio
        self._al_progresar = al_progresar
        self._cancelado = cancelado
        self._al_leer = al_leer
        self._enviados = 0
        marca = b"--" + self._frontera.encode("ascii")
        cabecera = bytearray()
        for nombre, valor in campos.items():
            _sin_prohibidos(nombre, "nombre de campo")
            if "\r" in valor or "\n" in valor or "\x00" in valor:
                raise ValueError("valor de campo con saltos de línea")
            cabecera += marca + _CRLF
            cabecera += f'Content-Disposition: form-data; name="{nombre}"'.encode() + _CRLF + _CRLF
            cabecera += valor.encode("utf-8") + _CRLF
        nombre_archivo = _sin_prohibidos(parte.nombre_archivo, "nombre de archivo")
        tipo = _sin_prohibidos(parte.tipo, "tipo de contenido")
        cabecera += marca + _CRLF
        cabecera += (
            f'Content-Disposition: form-data; name="filename"; filename="{nombre_archivo}"'
        ).encode() + _CRLF
        cabecera += f"Content-Type: {tipo}".encode() + _CRLF + _CRLF
        self._cabecera = bytes(cabecera)
        self._cierre = _CRLF + marca + b"--" + _CRLF

    # --- Contrato de cuerpo para requests/http.client -----------------------------------

    def __len__(self) -> int:
        """Longitud exacta del cuerpo (``Content-Length``)."""
        return len(self._cabecera) + self._parte.tamano + len(self._cierre)

    @property
    def tipo_contenido(self) -> str:
        """Valor de la cabecera ``Content-Type`` de la petición."""
        return f"multipart/form-data; boundary={self._frontera}"

    @property
    def cancelado(self) -> threading.Event | None:
        """Evento de cancelación (lo consulta también el transporte mientras espera al socket)."""
        return self._cancelado

    @property
    def enviados(self) -> int:
        """Bytes del archivo entregados al socket hasta ahora (sin contar cabeceras)."""
        return self._enviados

    def _comprobar_cancelacion(self) -> None:
        if self._cancelado is not None and self._cancelado.is_set():
            raise SubidaCancelada

    def __iter__(self) -> Iterator[bytes]:
        self._enviados = 0
        self._comprobar_cancelacion()
        yield self._cabecera
        restante = self._parte.tamano
        while restante > 0:
            try:
                bloque = self._parte.flujo.read(min(self._tam_lectura, restante))
            except OSError:
                # Fallo de lectura del disco (no de red): se registra como archivo no accesible,
                # solo con el nombre (nunca la ruta ni el texto del sistema operativo).
                raise ErrorProxLaunch(
                    CodigoError.ARCHIVO_NO_ACCESIBLE,
                    {"archivo": self._parte.nombre_archivo, "motivo": "otro"},
                ) from None
            if not bloque:
                # El archivo se acortó tras anunciar su tamaño: abortar, no colgar al servidor.
                raise ErrorProxLaunch(CodigoError.ARCHIVO_CAMBIO, {}, "el archivo se acortó")
            restante -= len(bloque)
            if self._al_leer is not None:
                self._al_leer(bloque)
            vista = memoryview(bloque)
            for inicio in range(0, len(bloque), self._tam_envio):
                self._comprobar_cancelacion()
                trozo = bytes(vista[inicio : inicio + self._tam_envio])
                yield trozo
                self._enviados += len(trozo)
                if self._al_progresar is not None:
                    self._al_progresar(self._enviados, self._parte.tamano)
        self._comprobar_cancelacion()
        yield self._cierre
