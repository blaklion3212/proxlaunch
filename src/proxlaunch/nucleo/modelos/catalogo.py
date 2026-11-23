"""Catálogo del servidor: volúmenes, plantillas y permisos (MVP 4, arquitectura §3.2).

Son datos leídos del servidor (texto no confiable ya parseado). Los modelos son
inmutables; los métodos de consulta son puros y no hacen E/S.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.cloudinit.modelos import InfoCloudInitPlantilla
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import InfoFirewall
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoliticaEtiquetas, PoolsServidor
from proxlaunch.nucleo.red.modelos import TarjetaPlantilla


class Contenido(StrEnum):
    """Tipo de contenido de un storage que usa el origen del SO."""

    IMAGENES = "images"
    ISO = "iso"
    IMPORT = "import"


@dataclass(frozen=True)
class Volumen:
    """Archivo de un storage (ISO o imagen a importar)."""

    volid: str
    storage: str
    contenido: Contenido
    nombre: str  # parte tras "iso/" o "import/"
    tamano_bytes: int | None
    creado: int | None  # ctime (epoch) si viene
    admitido: bool  # pasa la lista blanca (V-O02/V-O03)


@dataclass(frozen=True)
class ListadoStorage:
    """Resultado de listar UN storage en UN nodo."""

    nodo: str
    storage: str
    contenido: Contenido
    volumenes: tuple[Volumen, ...] = ()
    error: ErrorProxLaunch | None = None  # E-O05 por storage


@dataclass(frozen=True)
class Snippet:
    """Archivo de un almacenamiento con contenido «snippets» (fase B, B4)."""

    volid: str
    nombre: str  # parte tras «snippets/»
    tamano: int | None
    admitido: bool  # el volid tiene el formato admitido (V-B54)


@dataclass(frozen=True)
class ListadoSnippets:
    """Resultado de listar los snippets de UN storage en UN nodo."""

    nodo: str
    storage: str
    compartido: bool
    snippets: tuple[Snippet, ...] = ()
    error: ErrorProxLaunch | None = None  # el listado falló: se pasa a entrada manual


@dataclass(frozen=True)
class DiscoPlantilla:
    """Disco de una plantilla (sin CD-ROM; incluye efidisk0/tpmstate0)."""

    clave: str
    storage: str
    tamano_bytes: int | None
    formato: str | None


@dataclass(frozen=True)
class DetallePlantilla:
    """De ``GET …/qemu/{vmid}/config`` (texto no confiable, ya parseado)."""

    es_plantilla: bool
    bloqueo: str | None
    discos: tuple[DiscoPlantilla, ...]
    bridges: tuple[str, ...]
    sockets: int | None
    cores: int | None
    tipo_cpu: str | None
    memoria_mib: int | None
    etiquetas: frozenset[str]
    # Con valor por defecto: tope de memoria del globo (``balloon``, 0 = desactivado) y CPUs
    # conectadas (``vcpus``) de la plantilla; limitan los ajustes de memoria y CPU (QA-M4-07).
    balloon: int | None = None
    vcpus: int | None = None
    # Fase A: ``description`` de la plantilla (None = no tiene) y si se pudo leer; ilegible =
    # el GET falló por permiso (no se pisan sus notas, P-10).
    descripcion: str | None = None
    descripcion_legible: bool = True
    # Fase B: lo que la config dice de cloud-init (None = aún no interpretada).
    cloudinit: InfoCloudInitPlantilla | None = None
    # Fase C: ``net0..net31`` de la misma config, interpretadas (DT-C5); () = no leídas.
    tarjetas: tuple[TarjetaPlantilla, ...] = ()


@dataclass(frozen=True)
class Plantilla:
    """De ``GET /cluster/resources?type=vm`` con ``template = 1``."""

    vmid: int
    nombre: str
    nodo: str
    bloqueo: str | None
    disco_total_bytes: int | None
    detalle: DetallePlantilla | None = None


@dataclass(frozen=True)
class PermisosEfectivos:
    """``GET /access/permissions``: ``{ruta: {privilegio: propagate}}`` del token."""

    rutas: Mapping[str, Mapping[str, int]]

    def tiene(self, privilegio: str, ruta: str) -> bool:
        """Indica si se tiene el privilegio en la ruta (propia o heredada).

        ``propagate=1`` = concedido y heredado por las subrutas; ``0`` = solo en esa ruta
        exacta. En ``/storage`` también cuenta un ``/storage/<id>`` concreto (misma
        semántica que el cálculo de permisos del MVP 1).
        """
        for p, privs in self.rutas.items():
            if privilegio not in privs:
                continue
            if p == ruta:
                return True
            if bool(privs[privilegio]) and (p == "/" or ruta.startswith(p.rstrip("/") + "/")):
                return True
            if ruta == "/storage" and p.startswith("/storage/"):
                return True
        return False


@dataclass(frozen=True)
class CatalogoServidor:
    """Lo leído del servidor para el origen del SO (bajo demanda, solo GET)."""

    permisos: PermisosEfectivos | None = None  # None = desconocidos (CA-O02.6)
    listados: tuple[ListadoStorage, ...] = ()
    plantillas: tuple[Plantilla, ...] | None = None  # None = aún no leídas
    formatos: Mapping[str, frozenset[str]] = field(default_factory=dict)  # storage → formatos API
    leido_en: float = 0.0  # reloj inyectado (vigencia V-L14)
    # Fase A: pools del servidor y política de etiquetas del centro de datos (None = no legible).
    pools: PoolsServidor = field(default_factory=lambda: PoolsServidor(EstadoPools.NO_LEIDO))
    politica_etiquetas: PoliticaEtiquetas | None = None
    # True si se intentó leer ``/cluster/options`` y falló (403/5xx/cuerpo inesperado): con la
    # política en ``None`` distingue «no se pudo comprobar» (aviso V-A09) de «aún no leída».
    politica_etiquetas_fallida: bool = False
    # Fase B: snippets por (nodo, storage); un storage compartido se lista una vez (DT-B11).
    snippets: tuple[ListadoSnippets, ...] = ()
    # Fase C: lecturas del firewall de «Comprobar» (None = sin lecturas, DT-C11).
    firewall: InfoFirewall | None = None

    def snippets_en(self, nodo: str, storage: str) -> ListadoSnippets | None:
        """Listado de snippets del storage en ese nodo. Un storage compartido leído en otro nodo
        vale para todos; ``None`` si no se leyó."""
        for lst in self.snippets:
            if lst.storage == storage and (lst.nodo == nodo or lst.compartido):
                return lst
        return None

    def volumenes(self, nodo: str, contenido: Contenido) -> tuple[Volumen, ...]:
        """Volúmenes listados del nodo con ese contenido (todos los storages leídos)."""
        return tuple(
            v
            for lst in self.listados
            if lst.nodo == nodo and lst.contenido == contenido
            for v in lst.volumenes
        )

    def buscar_volid(self, volid: str, nodo: str) -> Volumen | None:
        """Volumen con ese volid entre los listados del nodo; ``None`` si no está."""
        for lst in self.listados:
            if lst.nodo != nodo:
                continue
            for v in lst.volumenes:
                if v.volid == volid:
                    return v
        return None

    def buscar_nombre(self, nombre: str, nodo: str, contenido: Contenido) -> tuple[Volumen, ...]:
        """Volúmenes del nodo y contenido cuyo nombre de archivo coincide exactamente."""
        return tuple(v for v in self.volumenes(nodo, contenido) if v.nombre == nombre)

    def plantillas_por_nombre(self, nombre: str) -> tuple[Plantilla, ...]:
        """Plantillas leídas con ese nombre (vacío si aún no se leyeron)."""
        return tuple(p for p in (self.plantillas or ()) if p.nombre == nombre)
