"""Obtención de la huella SHA-256 del certificado sin enviar credenciales."""

from __future__ import annotations

import hashlib
import socket
import ssl

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch


def formatear_huella(der: bytes) -> str:
    """Calcula la huella SHA-256 de un certificado DER en formato ``AA:BB:...``."""
    resumen = hashlib.sha256(der).hexdigest().upper()
    return ":".join(resumen[i : i + 2] for i in range(0, len(resumen), 2))


def obtener_huella(host: str, puerto: int, timeout: float) -> str:
    """Abre una conexión TLS, lee el certificado del servidor y la cierra.

    No envía ningún dato HTTP (CA-05.1): solo el saludo TLS. No valida la cadena,
    porque el objetivo es precisamente mostrar la huella para que el usuario decida.

    Raises:
        ErrorProxLaunch: ``SERVIDOR_NO_RESPONDE`` si no se puede conectar.
    """
    destino = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((destino, puerto), timeout=timeout) as sock,
            contexto.wrap_socket(sock, server_hostname=destino) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError) as e:
        raise ErrorProxLaunch(
            CodigoError.SERVIDOR_NO_RESPONDE,
            {"host": host, "puerto": str(puerto)},
            f"{type(e).__name__}: {e}",
        ) from None
    if not der:
        raise ErrorProxLaunch(
            CodigoError.SERVIDOR_NO_RESPONDE,
            {"host": host, "puerto": str(puerto)},
            "el servidor no presentó certificado",
        )
    return formatear_huella(der)
