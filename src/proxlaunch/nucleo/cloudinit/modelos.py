"""Modelos de cloud-init (DT-B2): configuración inmutable, snippets, tarjetas y lo que trae la
plantilla. Sin E/S.

``ConfigCloudInit`` cuelga de ``ConfiguracionVM.cloudinit`` (``None`` = sin cloud-init = 0.6.0).
La contraseña vive siempre en un ``Secreto`` y nunca entra en ``repr`` ni en las comparaciones.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Final

from proxlaunch.nucleo.secreto import Secreto

NINGUNO: Final[str] = "ninguno"
TIPOS_SNIPPET: Final[tuple[str, ...]] = ("user", "vendor", "network", "meta")
# ``netN`` / ``ipconfigN``: N va de 0 a 31.
MAX_TARJETAS: Final = 32


class ModoTarjeta(StrEnum):
    SIN_CONFIGURAR = "sin_configurar"
    DHCP = "dhcp"
    FIJA = "fija"


@dataclass(frozen=True)
class TarjetaCloudInit:
    """Red de una tarjeta ``netN`` (RF-B1.7): modo, IP y puerta de enlace."""

    indice: int  # N de netN / ipconfigN (0..31)
    modo: ModoTarjeta = ModoTarjeta.SIN_CONFIGURAR
    ip: str | None = None  # CIDR IPv4, solo FIJA (en serie: la inicial)
    serie: bool = False  # «Sumar 1 a cada máquina»
    puerta: str | None = None  # gw, solo FIJA
    # CALCULADO por ``expandir_serie``: CIDR inicial de la serie de la que sale ``ip``. Permite
    # evaluar V-B30 después de expandir. No se serializa ni cuenta en la igualdad.
    serie_inicial: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class SnippetsCloudInit:
    """Un snippet por tipo. ``None`` = como la plantilla; ``NINGUNO``; o volid «st:snippets/x»."""

    user: str | None = None
    vendor: str | None = None
    network: str | None = None
    meta: str | None = None

    @property
    def como_la_plantilla(self) -> bool:
        return all(getattr(self, t) is None for t in TIPOS_SNIPPET)

    def elegidos(self) -> dict[str, str]:
        """Tipo -> volid de los que apuntan a un snippet (sin ``NINGUNO`` ni ``None``)."""
        resultado: dict[str, str] = {}
        for tipo in TIPOS_SNIPPET:
            valor: str | None = getattr(self, tipo)
            if valor is not None and valor != NINGUNO:
                resultado[tipo] = valor
        return resultado


@dataclass(frozen=True)
class ConfigCloudInit:
    """Lo que el usuario fija en la sección «Configuración inicial (cloud-init)»."""

    usuario: str = ""
    claves: tuple[str, ...] = ()  # claves públicas ya normalizadas
    contrasena: Secreto | None = field(default=None, repr=False, compare=False)
    tarjetas: tuple[TarjetaCloudInit, ...] = ()  # ordenadas por indice, sin repetidos
    dns: tuple[str, ...] = ()
    dominio: str = ""
    actualizar: bool | None = None  # ``ciupgrade``; None = como la plantilla
    snippets: SnippetsCloudInit = field(default_factory=SnippetsCloudInit)
    activar_agente: bool = False  # RF-B1.15 (agent=1 en el PUT de cloud-init)

    @property
    def vacia(self) -> bool:
        """No hay nada que enviar (la contraseña cuenta)."""
        return (
            not self.usuario
            and not self.claves
            and not (self.contrasena is not None and self.contrasena.definido)
            and all(t.modo == ModoTarjeta.SIN_CONFIGURAR for t in self.tarjetas)
            and not self.dns
            and not self.dominio
            and self.actualizar is None
            and self.snippets.como_la_plantilla
            and not self.activar_agente
        )

    @property
    def sin_nada_que_aplicar(self) -> bool:
        """``vacia`` y sin contraseña pedida: una ``Secreto`` ya olvidado cuenta como pedido, para
        que el envío lo marque pendiente (``CONTRASENA_OLVIDADA``) en vez de ignorarlo."""
        return self.vacia and self.contrasena is None

    def tarjeta(self, indice: int) -> TarjetaCloudInit | None:
        for t in self.tarjetas:
            if t.indice == indice:
                return t
        return None


@dataclass(frozen=True)
class CicustomHeredado:
    """``cicustom`` que ya trae la plantilla. ``interpretable`` False = formato desconocido
    (``tipos`` queda vacío y solo se admite «como la plantilla»)."""

    tipos: Mapping[str, str]  # tipo -> volid
    interpretable: bool


@dataclass(frozen=True)
class InfoCloudInitPlantilla:
    """Lo que la ``config`` de la plantilla dice de cloud-init (DT-B2, DT-B5)."""

    unidad: bool | None  # None = no se pudo leer (V-B20 aviso)
    clave_unidad: str | None = None  # p. ej. "ide2"
    ostype: str | None = None
    es_windows: bool = False
    agente: bool | None = None  # agent habilitado (1 / enabled=1)
    tarjetas: tuple[int, ...] = ()  # N de cada netN presente
    mac_net0: str | None = None
    # ciuser, ipconfigN, nameserver, searchdomain y ciupgrade (nunca cipassword).
    heredados: Mapping[str, str] = field(default_factory=dict)
    cicustom: CicustomHeredado | None = None


INFO_DESCONOCIDA: Final[InfoCloudInitPlantilla] = InfoCloudInitPlantilla(unidad=None)


@dataclass(frozen=True)
class CloudInitParcial:
    """Celdas de una fila de CSV; ``None`` = hereda del formulario."""

    usuario: str | None = None
    claves: tuple[str, ...] | None = None
    contrasena: Secreto | None = field(default=None, repr=False, compare=False)
    tarjeta0: TarjetaCloudInit | None = None  # ci_ip + ci_puerta (indice 0, serie=False)
    dns: tuple[str, ...] | None = None
    dominio: str | None = None
    actualizar: bool | None = None  # vacío = hereda (no hay «como la plantilla» por fila)
    snippets: SnippetsCloudInit | None = None  # cada tipo None = hereda

    @property
    def vacia(self) -> bool:
        return (
            self.usuario is None
            and self.claves is None
            and self.contrasena is None
            and self.tarjeta0 is None
            and self.dns is None
            and self.dominio is None
            and self.actualizar is None
            and (self.snippets is None or self.snippets.como_la_plantilla)
        )


def _combinar_snippets(
    base: SnippetsCloudInit, fila: SnippetsCloudInit | None
) -> SnippetsCloudInit:
    if fila is None:
        return base
    return SnippetsCloudInit(
        **{
            t: (getattr(fila, t) if getattr(fila, t) is not None else getattr(base, t))
            for t in TIPOS_SNIPPET
        }
    )


def combinar(base: ConfigCloudInit | None, fila: CloudInitParcial | None) -> ConfigCloudInit | None:
    """Combina el formulario (``base``) con las celdas de una fila (RF-B0.5, CA-B6.3.2).

    La celda no vacía de la fila prevalece; la vacía (``None``) hereda del formulario. Con una
    fila sin nada devuelve ``base`` tal cual; sin formulario y con celdas, parte de una
    configuración vacía.
    """
    if fila is None or fila.vacia:
        return base
    actual = base if base is not None else ConfigCloudInit()
    tarjetas = actual.tarjetas
    if fila.tarjeta0 is not None:
        resto = tuple(t for t in tarjetas if t.indice != fila.tarjeta0.indice)
        tarjetas = tuple(sorted((*resto, fila.tarjeta0), key=lambda t: t.indice))
    return replace(
        actual,
        usuario=actual.usuario if fila.usuario is None else fila.usuario,
        claves=actual.claves if fila.claves is None else fila.claves,
        contrasena=actual.contrasena if fila.contrasena is None else fila.contrasena,
        tarjetas=tarjetas,
        dns=actual.dns if fila.dns is None else fila.dns,
        dominio=actual.dominio if fila.dominio is None else fila.dominio,
        actualizar=actual.actualizar if fila.actualizar is None else fila.actualizar,
        snippets=_combinar_snippets(actual.snippets, fila.snippets),
    )
