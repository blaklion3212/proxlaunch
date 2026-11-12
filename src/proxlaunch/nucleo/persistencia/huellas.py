"""Repositorio de huellas SSL confiadas, por clave "host:puerto" (RF-05, P-12)."""

from __future__ import annotations

from pathlib import Path

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson

VERSION_ESQUEMA = 1


def clave_huella(host: str, puerto: int) -> str:
    """Normaliza "host:puerto": host en minúsculas e IPv6 entre corchetes."""
    h = host.strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if ":" in h:  # IPv6
        h = f"[{h}]"
    return f"{h}:{int(puerto)}"


class RepositorioHuellas:
    """Guarda `{"host:puerto": "AA:BB:..."}` dentro de un JSON versionado."""

    def __init__(self, ruta: Path) -> None:
        self._almacen = AlmacenJson(ruta)
        self.hubo_corrupcion = False
        self.copia_danada: Path | None = None

    def _cargar(self) -> dict[str, str]:
        r = self._almacen.leer()
        if r.hubo_corrupcion:
            self.hubo_corrupcion = True
            self.copia_danada = r.copia_danada
        crudo = r.datos.get("huellas", {})
        if not isinstance(crudo, dict):
            return {}
        return {str(k): v for k, v in crudo.items() if isinstance(v, str)}

    def _volcar(self, huellas: dict[str, str]) -> None:
        self._almacen.escribir({"version_esquema": VERSION_ESQUEMA, "huellas": huellas})

    def obtener(self, host: str, puerto: int) -> str | None:
        """Devuelve la huella confiada para ese host:puerto o `None`."""
        return self._cargar().get(clave_huella(host, puerto))

    def guardar(self, host: str, puerto: int, huella: str) -> None:
        """Guarda una huella nueva. Si ya hay otra distinta lanza HUELLA_CAMBIADA:
        para sustituirla hay que usar `reemplazar` (solo modo avanzado, con confirmación)."""
        clave = clave_huella(host, puerto)
        huellas = self._cargar()
        actual = huellas.get(clave)
        if actual is not None and actual != huella:
            raise ErrorProxLaunch(CodigoError.HUELLA_CAMBIADA, {"host": clave})
        huellas[clave] = huella
        self._volcar(huellas)

    def reemplazar(self, host: str, puerto: int, huella: str) -> None:
        """Sustituye (o crea) la huella de ese host:puerto sin comprobar la anterior."""
        huellas = self._cargar()
        huellas[clave_huella(host, puerto)] = huella
        self._volcar(huellas)

    def eliminar(self, host: str, puerto: int) -> bool:
        """Borra la huella; devuelve `True` si existía."""
        huellas = self._cargar()
        existia = huellas.pop(clave_huella(host, puerto), None) is not None
        if existia:
            self._volcar(huellas)
        return existia
