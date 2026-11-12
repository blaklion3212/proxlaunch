"""Repositorio de huellas SSL confiadas, por clave "host:puerto" (RF-05, P-12)."""

from __future__ import annotations

import re
from pathlib import Path

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.persistencia.almacen_json import AlmacenJson

VERSION_ESQUEMA = 1

# Entrada "host:puerto": "AA:BB:...(32 pares)" legible dentro de un archivo dañado.
_RE_ENTRADA = re.compile(
    r'"(?P<clave>[^"\s]+:\d{1,5})"\s*:\s*"(?P<huella>(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2})"'
)


def clave_huella(host: str, puerto: int) -> str:
    """Normaliza "host:puerto": host en minúsculas e IPv6 entre corchetes."""
    h = host.strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if ":" in h:  # IPv6
        h = f"[{h}]"
    return f"{h}:{int(puerto)}"


def _recuperar_de_copia(copia: Path) -> dict[str, str]:
    """Rescata las entradas ``host:puerto -> huella`` que aún se pueden leer de un archivo
    dañado (búsqueda textual: el JSON ya no es válido)."""
    try:
        texto = copia.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    return {m.group("clave"): m.group("huella").upper() for m in _RE_ENTRADA.finditer(texto)}


class RepositorioHuellas:
    """Guarda `{"host:puerto": "AA:BB:..."}` dentro de un JSON versionado.

    Atributos públicos de estado (la interfaz los usa para avisar, RNF-15):
        hubo_corrupcion: el archivo estaba dañado (o no se pudo leer) y se empezó vacío.
        copia_danada: ruta de la copia del archivo dañado (``None`` si no hubo copia).
        error_lectura: el archivo no se pudo leer o renombrar (permisos, carpeta...).
        huellas_recuperadas: huellas rescatadas de la copia dañada (``host:puerto``).
    """

    def __init__(self, ruta: Path) -> None:
        self._almacen = AlmacenJson(ruta)
        self.hubo_corrupcion = False
        self.copia_danada: Path | None = None
        self.error_lectura = False
        self.huellas_recuperadas: tuple[str, ...] = ()

    def _cargar(self) -> dict[str, str]:
        r = self._almacen.leer()
        if r.hubo_corrupcion:
            self.hubo_corrupcion = True
            self.copia_danada = r.copia_danada
            self.error_lectura = self.error_lectura or r.error_lectura
        crudo = r.datos.get("huellas", {})
        huellas = (
            {str(k): v for k, v in crudo.items() if isinstance(v, str)}
            if isinstance(crudo, dict)
            else {}
        )
        if r.hubo_corrupcion and r.copia_danada is not None:
            rescatadas = _recuperar_de_copia(r.copia_danada)
            if rescatadas:
                huellas.update(rescatadas)
                self.huellas_recuperadas = tuple(sorted(rescatadas))
                self._volcar(huellas)  # se restauran para que no se pierdan en la siguiente lectura
        return huellas

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
