"""Autenticación por token y ticket, renovación y doble factor.

Referencia: ``docs/investigacion/f1-api-proxmox.md`` §3 (2FA) y §4 (renovación).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import unquote

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken, Ticket
from proxlaunch.nucleo.registro import registrar_secreto
from proxlaunch.nucleo.reloj import Reloj, RelojReal

if TYPE_CHECKING:
    from proxlaunch.nucleo.api.transporte import Transporte

RUTA_TICKET = "/access/ticket"
COOKIE_TICKET = "PVEAuthCookie"
CABECERA_CSRF = "CSRFPreventionToken"
VIDA_TICKET_S = 2 * 60 * 60  # el ticket vive 2 h
MARGEN_RENOVACION_S = 15 * 60  # se renueva cuando quedan <= 15 min (CA-03.1)
_PREFIJO_TFA = "!tfa!"
_TIPOS_NO_SOPORTADOS = ("webauthn", "u2f", "yubico")


class TipoTFA(StrEnum):
    """Tipos de segundo factor que ProxLaunch admite; el valor es el prefijo de la API."""

    TOTP = "totp"
    RECUPERACION = "recovery"


@dataclass(frozen=True)
class DesafioTFA:
    """Desafío de segundo factor extraído del ticket parcial (A-7).

    ``ticket_parcial`` se excluye del ``repr`` por ser material de sesión.
    """

    usuario: str
    ticket_parcial: str = field(repr=False)
    totp: bool
    recuperacion: bool
    no_soportados: tuple[str, ...] = ()

    @property
    def soportado(self) -> bool:
        """``True`` si ofrece TOTP o claves de recuperación (CA-04.5, CA-04.6)."""
        return self.totp or self.recuperacion


class Autenticador(Protocol):
    """Firma las peticiones y, si procede, renueva la credencial."""

    def aplicar(self, metodo: str, cabeceras: dict[str, str], cookies: dict[str, str]) -> None:
        """Añade a ``cabeceras``/``cookies`` lo necesario para autenticar la petición."""
        ...

    def necesita_renovar(self) -> bool:
        """Indica si hay que renovar antes de la siguiente petición."""
        ...

    def renovar(self, transporte: Transporte) -> None:
        """Renueva la credencial usando el transporte."""
        ...


class AutenticadorToken:
    """Cabecera ``Authorization: PVEAPIToken=...``. Nunca renueva (CA-03.4)."""

    def __init__(self, credencial: CredencialToken) -> None:
        self._credencial = credencial
        registrar_secreto(credencial.secreto)

    def aplicar(self, metodo: str, cabeceras: dict[str, str], cookies: dict[str, str]) -> None:
        c = self._credencial
        cabeceras["Authorization"] = f"PVEAPIToken={c.token_id}={c.secreto}"

    def necesita_renovar(self) -> bool:
        return False

    def renovar(self, transporte: Transporte) -> None:
        return None

    def olvidar(self) -> None:
        """Suelta el secreto del token (al cerrar la sesión)."""
        self._credencial = CredencialToken(self._credencial.token_id, "")


def _es_ticket_parcial(ticket: str) -> bool:
    partes = ticket.split(":")
    return len(partes) > 1 and partes[1].startswith(_PREFIJO_TFA)


def _ticket_desde_respuesta(data: Any, reloj: Reloj, usuario_por_defecto: str) -> Ticket:
    """Construye un ``Ticket`` completo a partir de la respuesta de ``/access/ticket``."""
    if not isinstance(data, dict) or not data.get("ticket") or not data.get(CABECERA_CSRF):
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "respuesta de ticket incompleta")
    ticket = str(data["ticket"])
    csrf = str(data[CABECERA_CSRF])
    registrar_secreto(ticket)
    registrar_secreto(csrf)
    if _es_ticket_parcial(ticket):
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "se recibió un ticket parcial")
    usuario = str(data.get("username") or usuario_por_defecto)
    return Ticket(ticket=ticket, csrf=csrf, usuario=usuario, emitido_en=reloj.ahora())


class AutenticadorTicket:
    """Cookie ``PVEAuthCookie`` y ``CSRFPreventionToken`` en métodos que no son GET.

    Renueva con el ticket vigente como contraseña cuando quedan <= 15 min. No guarda
    la contraseña (S-5, P-13).
    """

    def __init__(
        self,
        ticket: Ticket,
        reloj: Reloj,
        *,
        vida_s: float = VIDA_TICKET_S,
        margen_s: float = MARGEN_RENOVACION_S,
    ) -> None:
        self._ticket = ticket
        self._reloj = reloj
        self._vida_s = vida_s
        self._margen_s = margen_s
        self._lock = threading.Lock()
        registrar_secreto(ticket.ticket)
        registrar_secreto(ticket.csrf)

    @property
    def ticket(self) -> Ticket:
        """Ticket vigente (solo en memoria)."""
        return self._ticket

    def aplicar(self, metodo: str, cabeceras: dict[str, str], cookies: dict[str, str]) -> None:
        t = self._ticket
        cookies[COOKIE_TICKET] = t.ticket
        if metodo.upper() != "GET":
            cabeceras[CABECERA_CSRF] = t.csrf

    def olvidar(self) -> None:
        """Suelta ticket y CSRF (al cerrar la sesión)."""
        with self._lock:
            self._ticket = Ticket(ticket="", csrf="", usuario=self._ticket.usuario, emitido_en=0.0)

    def necesita_renovar(self) -> bool:
        edad = self._reloj.ahora() - self._ticket.emitido_en
        return edad >= self._vida_s - self._margen_s

    def renovar(self, transporte: Transporte) -> None:
        """Pide un ticket nuevo usando el vigente como contraseña (f1 §4).

        Raises:
            ErrorProxLaunch: ``SESION_EXPIRADA`` si el servidor rechaza el ticket.
        """
        with self._lock:
            if not self.necesita_renovar():
                return  # otro hilo ya lo renovó
            actual = self._ticket
            try:
                data = transporte.peticion(
                    "POST",
                    RUTA_TICKET,
                    datos={"username": actual.usuario, "password": actual.ticket},
                )
            except ErrorProxLaunch as e:
                if e.codigo in (CodigoError.CREDENCIALES_INVALIDAS, CodigoError.SESION_EXPIRADA):
                    raise ErrorProxLaunch(
                        CodigoError.SESION_EXPIRADA, e.params, e.detalle_tecnico
                    ) from None
                raise
            # Se actualizan ticket y CSRF a la vez (la respuesta trae un CSRF nuevo).
            self._ticket = _ticket_desde_respuesta(data, self._reloj, actual.usuario)


def normalizar_usuario(usuario: str, realm: str) -> str:
    """Devuelve ``usuario@realm`` sin duplicar el realm (CA-02.4)."""
    u = usuario.strip()
    r = realm.strip()
    if not r or u.endswith(f"@{r}"):
        return u
    return f"{u}@{r}"


def _parsear_desafio(ticket_parcial: str) -> dict[str, Any]:
    """Extrae el desafío JSON del ticket parcial ``PVE:!tfa!<desafío>:<HEX8>::<firma>``."""
    partes = ticket_parcial.split(":")
    if len(partes) < 2 or not partes[1].startswith(_PREFIJO_TFA):
        raise ValueError("el ticket no es parcial")
    obj = json.loads(unquote(partes[1][len(_PREFIJO_TFA) :]))
    if not isinstance(obj, dict):
        raise ValueError("el desafío no es un objeto")
    return obj


def iniciar_sesion_ticket(
    transporte: Transporte,
    usuario: str,
    realm: str,
    contrasena: str,
    *,
    reloj: Reloj | None = None,
) -> Ticket | DesafioTFA:
    """Paso 1 del inicio de sesión: usuario y contraseña.

    Devuelve un ``Ticket`` completo, o un ``DesafioTFA`` si el usuario tiene 2FA.

    Args:
        reloj: fuente de tiempo para ``emitido_en`` (por defecto el real).

    Raises:
        ErrorProxLaunch: ``CREDENCIALES_INVALIDAS`` (401) o ``TFA_NO_SOPORTADO`` si el
            desafío no ofrece TOTP ni claves de recuperación.
    """
    reloj = reloj or RelojReal()
    nombre = normalizar_usuario(usuario, realm)
    registrar_secreto(contrasena)
    data = transporte.peticion(
        "POST", RUTA_TICKET, datos={"username": nombre, "password": contrasena}
    )
    if not isinstance(data, dict):
        raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "respuesta de ticket inválida")

    ticket = str(data.get("ticket") or "")
    if data.get("NeedTFA") or _es_ticket_parcial(ticket):
        registrar_secreto(ticket)
        try:
            desafio = _parsear_desafio(ticket)
        except ValueError:
            raise ErrorProxLaunch(
                CodigoError.TFA_NO_SOPORTADO, {}, "no se pudo leer el desafío del ticket parcial"
            ) from None
        resultado = DesafioTFA(
            usuario=str(data.get("username") or nombre),
            ticket_parcial=ticket,
            totp=bool(desafio.get("totp")),
            recuperacion=bool(desafio.get("recovery")),
            no_soportados=tuple(t for t in _TIPOS_NO_SOPORTADOS if desafio.get(t)),
        )
        if not resultado.soportado:
            raise ErrorProxLaunch(
                CodigoError.TFA_NO_SOPORTADO,
                {"tipos": ",".join(resultado.no_soportados)},
                f"el desafío no ofrece totp ni recovery: {sorted(desafio)}",
            )
        return resultado
    return _ticket_desde_respuesta(data, reloj, nombre)


def responder_tfa(
    transporte: Transporte,
    desafio: DesafioTFA,
    codigo: str,
    tipo: TipoTFA,
    *,
    reloj: Reloj | None = None,
) -> Ticket:
    """Paso 2: envía el código TOTP o la clave de recuperación.

    El código se normaliza (sin espacios; la clave de recuperación en minúsculas).

    Raises:
        ErrorProxLaunch: ``TFA_CODIGO_INCORRECTO`` ante un 401, ``TFA_NO_SOPORTADO`` si
            el desafío no ofrece ese tipo.
    """
    reloj = reloj or RelojReal()
    if (tipo == TipoTFA.TOTP and not desafio.totp) or (
        tipo == TipoTFA.RECUPERACION and not desafio.recuperacion
    ):
        raise ErrorProxLaunch(CodigoError.TFA_NO_SOPORTADO, {"tipo": str(tipo)}, "tipo no ofrecido")
    limpio = "".join(codigo.split())
    if tipo == TipoTFA.RECUPERACION:
        limpio = limpio.lower()
    registrar_secreto(limpio)
    registrar_secreto(codigo)
    try:
        data = transporte.peticion(
            "POST",
            RUTA_TICKET,
            datos={
                "username": desafio.usuario,
                "tfa-challenge": desafio.ticket_parcial,
                "password": f"{tipo.value}:{limpio}",
            },
        )
    except ErrorProxLaunch as e:
        # En este paso un 401 significa código incorrecto, no contraseña errónea.
        if e.codigo == CodigoError.CREDENCIALES_INVALIDAS:
            raise ErrorProxLaunch(
                CodigoError.TFA_CODIGO_INCORRECTO, e.params, e.detalle_tecnico
            ) from None
        raise
    return _ticket_desde_respuesta(data, reloj, desafio.usuario)
