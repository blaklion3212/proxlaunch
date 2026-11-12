"""Modelos de conexión: perfil persistible y credenciales/ticket (solo en memoria)."""

from dataclasses import dataclass
from enum import StrEnum

_MASCARA = "***"


class MetodoAuth(StrEnum):
    """Método de autenticación contra Proxmox."""

    TOKEN = "token"
    CONTRASENA = "contrasena"


@dataclass
class PerfilConexion:
    """Perfil persistible. NUNCA contiene secretos (RF-07)."""

    id: str  # uuid
    nombre: str
    hosts: list[str]  # el orden es la prioridad de failover
    puerto: int = 8006
    metodo: MetodoAuth = MetodoAuth.TOKEN
    usuario: str = ""  # con token: "ana@pve!lab" (sin secreto)
    realm: str = "pam"
    recordar_credenciales: bool = False
    ignorar_ssl: bool = False  # solo efectivo en modo avanzado (CA-06.3)


@dataclass(repr=False)
class CredencialToken:
    """Token de API. El repr enmascara el secreto."""

    token_id: str
    secreto: str

    def __repr__(self) -> str:
        return f"CredencialToken(token_id={self.token_id!r}, secreto={_MASCARA!r})"


@dataclass(repr=False)
class CredencialContrasena:
    """Usuario y contraseña. El repr enmascara la contraseña."""

    usuario: str
    realm: str
    contrasena: str

    def __repr__(self) -> str:
        return (
            f"CredencialContrasena(usuario={self.usuario!r}, realm={self.realm!r}, "
            f"contrasena={_MASCARA!r})"
        )


@dataclass(repr=False)
class Ticket:
    """Ticket de sesión (solo en memoria). El repr enmascara ticket y CSRF."""

    ticket: str
    csrf: str
    usuario: str
    emitido_en: float

    def __repr__(self) -> str:
        return (
            f"Ticket(ticket={_MASCARA!r}, csrf={_MASCARA!r}, usuario={self.usuario!r}, "
            f"emitido_en={self.emitido_en!r})"
        )
