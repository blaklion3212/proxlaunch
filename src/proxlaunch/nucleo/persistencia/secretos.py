"""AlmacenSecretos sobre keyring, con detección de llavero no disponible (CA-08.4)."""

from __future__ import annotations

from typing import Any

import keyring
import keyring.backends.fail
import keyring.backends.null

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

SERVICIO = "ProxLaunch"


class AlmacenSecretos:
    """Guarda secretos en el llavero del sistema bajo la clave `perfil:<id>`.

    `backend` es cualquier objeto con `get_password`, `set_password` y
    `delete_password` (interfaz de keyring); si es `None` se usa el del sistema.
    Si el backend es nulo/fallido o lanza una excepción, se lanza
    `ErrorProxLaunch(LLAVERO_NO_DISPONIBLE)` y NO se guarda en ningún otro sitio.
    """

    def __init__(self, servicio: str = SERVICIO, backend: Any | None = None) -> None:
        self.servicio = servicio
        self._backend = backend

    @staticmethod
    def _clave(perfil_id: str) -> str:
        return f"perfil:{perfil_id}"

    def _obtener_backend(self) -> Any:
        backend = self._backend
        if backend is None:
            try:
                backend = keyring.get_keyring()
            except Exception as e:
                raise self._no_disponible(e) from None
        if isinstance(backend, keyring.backends.fail.Keyring | keyring.backends.null.Keyring):
            raise self._no_disponible(None)
        return backend

    @staticmethod
    def _no_disponible(causa: Exception | None) -> ErrorProxLaunch:
        # Solo el tipo de la excepción: el texto podría contener datos sensibles.
        detalle = type(causa).__name__ if causa is not None else "backend nulo o fallido"
        return ErrorProxLaunch(CodigoError.LLAVERO_NO_DISPONIBLE, {}, detalle)

    def disponible(self) -> bool:
        """`True` si hay un backend de llavero utilizable (no comprueba permisos)."""
        try:
            self._obtener_backend()
        except ErrorProxLaunch:
            return False
        return True

    def guardar(self, perfil_id: str, secreto: str) -> None:
        backend = self._obtener_backend()
        try:
            backend.set_password(self.servicio, self._clave(perfil_id), secreto)
        except Exception as e:
            raise self._no_disponible(e) from None

    def obtener(self, perfil_id: str) -> str | None:
        backend = self._obtener_backend()
        try:
            valor = backend.get_password(self.servicio, self._clave(perfil_id))
        except Exception as e:
            raise self._no_disponible(e) from None
        return valor if isinstance(valor, str) else None

    def borrar(self, perfil_id: str) -> None:
        """Borra el secreto; si no existía no hace nada."""
        backend = self._obtener_backend()
        try:
            backend.delete_password(self.servicio, self._clave(perfil_id))
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as e:
            raise self._no_disponible(e) from None
