"""Errores del núcleo: códigos estables y excepción con parámetros.

El núcleo no contiene textos para el usuario: la interfaz traduce cada
``CodigoError`` (con sus ``params``) a un mensaje en español.
"""

from enum import StrEnum


class CodigoError(StrEnum):
    """Códigos de error que la interfaz traduce a mensajes."""

    CREDENCIALES_INVALIDAS = "credenciales_invalidas"
    SESION_EXPIRADA = "sesion_expirada"
    HUELLA_CAMBIADA = "huella_cambiada"
    HUELLA_NO_CONFIADA = "huella_no_confiada"
    TFA_NO_SOPORTADO = "tfa_no_soportado"
    TFA_CODIGO_INCORRECTO = "tfa_codigo_incorrecto"
    SERVIDOR_NO_RESPONDE = "servidor_no_responde"
    NODO_NO_DISPONIBLE = "nodo_no_disponible"
    PERMISO_INSUFICIENTE = "permiso_insuficiente"
    VMID_OCUPADO = "vmid_ocupado"
    SIN_ESPACIO = "sin_espacio"
    TAREA_TIEMPO_AGOTADO = "tarea_tiempo_agotado"
    ERROR_FORMATO = "error_formato"
    PARAMETRO_INVALIDO = "parametro_invalido"
    VERSION_NO_SOPORTADA = "version_no_soportada"
    RECURSO_INEXISTENTE = "recurso_inexistente"
    UPID_INVALIDO = "upid_invalido"
    LLAVERO_NO_DISPONIBLE = "llavero_no_disponible"
    DESCONOCIDO = "desconocido"


class ErrorProxLaunch(Exception):
    """Error del núcleo con código, parámetros y detalle técnico.

    Atributos:
        codigo: código estable del error.
        params: parámetros para el mensaje, p. ej. ``{"privilegio": "VM.Allocate"}``.
        detalle_tecnico: texto original de Proxmox, ya sin secretos.
    """

    def __init__(
        self,
        codigo: CodigoError,
        params: dict[str, str] | None = None,
        detalle_tecnico: str = "",
    ) -> None:
        super().__init__(str(codigo))
        self.codigo = codigo
        self.params: dict[str, str] = dict(params) if params else {}
        self.detalle_tecnico = detalle_tecnico

    def __repr__(self) -> str:
        return (
            f"ErrorProxLaunch(codigo={self.codigo!s}, params={self.params!r}, "
            f"detalle_tecnico={self.detalle_tecnico!r})"
        )
