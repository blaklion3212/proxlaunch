"""Resolución del origen por elemento del plan y elegibilidad de nodos (RF-O07, O14, O17, O19, O23).

Todo es puro: trabaja con el inventario y el catálogo ya leídos (``Inventario.catalogo``).
``resolver_origen`` convierte nombres en volids, detecta los drivers virtio-win, elige la
plantilla del nodo y fija el modo efectivo del clon; los fallos salen como ``Problema`` (nunca
excepciones) y **no** sustituyen nada en silencio (D-23.2).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from proxlaunch.nucleo.cloudinit.snippets import volid_snippet_valido
from proxlaunch.nucleo.firewall.modelos import RE_GRUPO, FirewallMV, FirewallParcial
from proxlaunch.nucleo.lote.modelos import FilaLote
from proxlaunch.nucleo.lote.modelos import Problema as ProblemaLote
from proxlaunch.nucleo.lote.modelos import Severidad as SeveridadLote
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor, Contenido, Plantilla, Volumen
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage
from proxlaunch.nucleo.modelos.origen import (
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefPlantilla,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.opciones.modelos import OpcionesLote
from proxlaunch.nucleo.origen.asistente import TABLA_SO
from proxlaunch.nucleo.origen.clon import modo_efectivo
from proxlaunch.nucleo.origen.constantes import ESPERA_BASE_S, ESPERA_POR_GIB_S
from proxlaunch.nucleo.origen.nombres import (
    es_virtio_win,
    nombre_virtio_win_fijado,
    partes_volid,
    validar_volid,
)
from proxlaunch.nucleo.red.modelos import RedClon
from proxlaunch.nucleo.red.redes_nodo import redes_de_nodo
from proxlaunch.nucleo.red.tarjetas import bridges_finales
from proxlaunch.nucleo.validacion import Problema, Severidad

MAX_ALTERNATIVAS = 5  # alternativas que se listan en un «no encontrado» (CA-O28.3)
_GIB = 1024**3
_RE_UPID_NODO = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")


@dataclass(frozen=True)
class NecesidadesCatalogo:
    """Qué hay que leer del servidor para planificar estas filas (solo GET)."""

    contenidos: frozenset[Contenido] = frozenset()  # listados de ``iso`` y/o ``import``
    plantillas: frozenset[str] = frozenset()  # nombres de plantilla a resolver
    formatos: bool = False  # ``GET …/storage?format=1`` (destino de importación y clon)
    # Fase B (B4): ids de storage de los snippets elegidos; se listan solo esos (DT-B11).
    snippets: frozenset[str] = frozenset()
    # Fase C (C3): alguna fila usa el firewall; grupos elegidos y plantillas de las filas de clon.
    firewall: bool = False
    grupos_firewall: frozenset[str] = frozenset()
    firewall_plantillas: frozenset[str] = frozenset()  # nombres de plantilla de filas con C3

    @property
    def vacias(self) -> bool:
        return (
            not self.contenidos
            and not self.plantillas
            and not self.formatos
            and not self.snippets
            and not self.firewall
        )


def _firewall_de_fila(fila: FilaLote, opciones: OpcionesLote | None) -> tuple[bool, str | None]:
    """``(usa C3, grupo)`` de una fila: el firewall del lote (``opciones`` o el de su propia
    configuración) con las celdas de la fila encima (``None`` = hereda). Mismo criterio que el
    plan, para leer solo lo que hará falta."""
    base: FirewallMV | None = opciones.firewall if opciones is not None else fila.cfg.firewall
    parcial: FirewallParcial | None = fila.opciones.firewall if fila.opciones is not None else None
    activo = base.activo if base is not None else False
    grupo = base.grupo if base is not None else None
    if parcial is not None:
        activo = activo if parcial.activo is None else parcial.activo
        grupo = grupo if parcial.grupo is None else parcial.grupo
    return activo, grupo


def _storage_de_snippet(volid: str | None) -> str | None:
    """Id del storage de un volid ``almacén:snippets/archivo`` válido; ``None`` si no lo es."""
    if volid is None or not volid_snippet_valido(volid):
        return None
    return volid.partition(":")[0]


def _storages_de_snippets(fila: FilaLote, opciones: OpcionesLote | None) -> Iterable[str]:
    """Storages de los snippets que puede llevar la fila: los de su formulario, los de las
    opciones del lote y los de su propia fila (``CloudInitParcial.snippets``)."""
    volids: list[str | None] = []
    if fila.cfg.cloudinit is not None:
        volids.extend(fila.cfg.cloudinit.snippets.elegidos().values())
    if opciones is not None and opciones.cloudinit is not None:
        volids.extend(opciones.cloudinit.snippets.elegidos().values())
    parcial = fila.opciones.cloudinit if fila.opciones is not None else None
    if parcial is not None and parcial.snippets is not None:
        volids.extend(parcial.snippets.elegidos().values())
    return (a for a in (_storage_de_snippet(v) for v in volids) if a is not None)


def necesidades_catalogo(
    filas: Sequence[FilaLote], opciones: OpcionesLote | None = None
) -> NecesidadesCatalogo:
    """Catálogo que necesitan las filas. Sin ningún origen distinto de ``disco_vacio`` es vacío:
    el planificador no hace entonces ninguna lectura nueva (CA-O03.1).

    Fase B: en una fila de clon, los snippets elegidos (en su formulario, en ``opciones`` del lote
    o en su fila) añaden el storage de cada uno para listarlo (B4.2). Sin cloud-init no cambia.
    """
    contenidos: set[Contenido] = set()
    plantillas: set[str] = set()
    snippets: set[str] = set()
    grupos: set[str] = set()
    plantillas_fw: set[str] = set()
    formatos = False
    usa_fw = False
    for fila in filas:
        det = fila.cfg.detalle_origen
        fw_activo, fw_grupo = _firewall_de_fila(fila, opciones)
        if fw_activo:
            usa_fw = True
            if fw_grupo is not None and RE_GRUPO.fullmatch(fw_grupo):
                grupos.add(fw_grupo)
        if fila.cfg.origen == OrigenSO.ISO and isinstance(det, DetalleIso):
            contenidos.add(Contenido.ISO)
        elif fila.cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion):
            contenidos.add(Contenido.IMPORT)
            formatos = True
        elif fila.cfg.origen == OrigenSO.CLONAR_PLANTILLA and isinstance(det, DetalleClon):
            if det.plantilla.nombre:
                plantillas.add(det.plantilla.nombre)
                if fw_activo:
                    plantillas_fw.add(det.plantilla.nombre)
            formatos = True
            snippets.update(_storages_de_snippets(fila, opciones))
    return NecesidadesCatalogo(
        frozenset(contenidos),
        frozenset(plantillas),
        formatos,
        frozenset(snippets),
        usa_fw,
        frozenset(grupos),
        frozenset(plantillas_fw),
    )


# --- Utilidades de catálogo ---------------------------------------------------------------


def _storages_nodo(inv: Inventario, nodo: str) -> tuple[Storage, ...]:
    return inv.storages_todos.get(nodo) or inv.storages.get(nodo, ())


def _storage_activo(inv: Inventario, nodo: str, storage: str) -> bool:
    """Sin datos de storages del nodo se acepta (la capa 2 no afirma lo que no sabe)."""
    if nodo not in inv.storages_todos:
        return True
    return any(s.id == storage and s.activo for s in inv.storages_todos[nodo])


def _hay_listado(cat: CatalogoServidor | None, nodo: str, contenido: Contenido) -> bool:
    return cat is not None and any(
        lst.nodo == nodo and lst.contenido == contenido for lst in cat.listados
    )


def _catalogo_leido(cat: CatalogoServidor | None, contenido: Contenido) -> bool:
    return cat is not None and any(lst.contenido == contenido for lst in cat.listados)


def _disponibles(
    inv: Inventario, cat: CatalogoServidor, nodo: str, contenido: Contenido
) -> list[Volumen]:
    """Volúmenes del nodo y contenido, admitidos y en un storage activo."""
    return [
        v
        for v in cat.volumenes(nodo, contenido)
        if v.admitido and _storage_activo(inv, nodo, v.storage)
    ]


def _clave_natural(nombre: str) -> list[tuple[int, int, str]]:
    """Orden natural (``virtio-win-0.1.271`` > ``virtio-win-0.1.9``)."""
    return [
        (1, int(t), "") if t.isdigit() else (0, 0, t) for t in re.split(r"(\d+)", nombre.casefold())
    ]


def _problema(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def _alternativas(nombres: Sequence[str]) -> str:
    return ", ".join(sorted(set(nombres))[:MAX_ALTERNATIVAS])


# --- Resolución de un archivo (ISO, drivers, imagen) -----------------------------------------


def _resolver_ref(
    inv: Inventario,
    nodo: str,
    ref: RefVolumen,
    contenido: Contenido,
    codigo: str,
    campo: str,
) -> tuple[RefVolumen, Problema | None]:
    """Completa ``volid``/``nombre`` de ``ref`` en ``nodo``; un fallo deja ``ref`` como estaba."""
    cat = inv.catalogo
    if ref.volid:
        motivo = validar_volid(ref.volid, contenido)
        if motivo is not None:
            return ref, _problema(campo, codigo, motivo=motivo)
        if cat is None or not _hay_listado(cat, nodo, contenido):
            return ref, None
        volumen = cat.buscar_volid(ref.volid, nodo)
        if volumen is None or not _storage_activo(inv, nodo, volumen.storage):
            return ref, _problema(campo, codigo, motivo="no_disponible", nodo=nodo)
        if not volumen.admitido:
            return ref, _problema(campo, codigo, motivo="nombre_no_admitido")
        return RefVolumen(nombre=ref.nombre or volumen.nombre, volid=volumen.volid), None
    if not ref.nombre or cat is None or not _hay_listado(cat, nodo, contenido):
        # sin fuente: lo da V-O01; catálogo sin listar en el nodo: no se afirma nada
        return ref, None
    todos = [v for v in cat.buscar_nombre(ref.nombre, nodo, contenido)]
    coincidentes = [v for v in todos if v.admitido and _storage_activo(inv, nodo, v.storage)]
    if len(coincidentes) == 1:
        return RefVolumen(nombre=ref.nombre, volid=coincidentes[0].volid), None
    if len(coincidentes) > 1:
        volids = ", ".join(sorted(v.volid for v in coincidentes))
        return ref, _problema(campo, f"{codigo}.ambiguo", nombre=ref.nombre, volids=volids)
    if todos and not any(v.admitido for v in todos):
        return ref, _problema(campo, codigo, motivo="nombre_no_admitido")
    alternativas = _alternativas([v.nombre for v in _disponibles(inv, cat, nodo, contenido)])
    return ref, _problema(
        campo,
        codigo,
        motivo="no_disponible",
        nodo=nodo,
        nombre=ref.nombre,
        alternativas=alternativas,
    )


def _detectar_drivers_elegido(inv: Inventario, nodo: str) -> tuple[RefVolumen | None, bool]:
    """``(drivers, es_el_fijado)``: el virtio-win a usar entre los ``iso`` activos del nodo.

    Se prefiere SIEMPRE el nombre exacto fijado por la app (``virtio-win-<versión>.iso``, el
    que ella descarga), aunque haya versiones mayores (SEG-M4-02). Si no está, se elige el
    más reciente y ``es_el_fijado`` es ``False``: quien llama debe avisar (V-O31).
    """
    if inv.catalogo is None:
        return None, False
    candidatos = [
        v for v in _disponibles(inv, inv.catalogo, nodo, Contenido.ISO) if es_virtio_win(v.nombre)
    ]
    if not candidatos:
        return None, False
    fijado = nombre_virtio_win_fijado().casefold()
    exactos = [v for v in candidatos if fijado and v.nombre.casefold() == fijado]
    if exactos:
        elegido = min(exactos, key=lambda v: v.volid)
        return RefVolumen(nombre=elegido.nombre, volid=elegido.volid), True
    mejor = max(candidatos, key=lambda v: (_clave_natural(v.nombre), v.volid))
    return RefVolumen(nombre=mejor.nombre, volid=mejor.volid), False


def _detectar_drivers(inv: Inventario, nodo: str) -> RefVolumen | None:
    """virtio-win preferido presente en un storage ``iso`` activo del nodo (CA-O14.1)."""
    return _detectar_drivers_elegido(inv, nodo)[0]


def _resolver_iso(
    cfg: ConfiguracionVM, inv: Inventario, nodo: str, det: DetalleIso, problemas: list[Problema]
) -> DetalleIso:
    iso, p = _resolver_ref(inv, nodo, det.iso, Contenido.ISO, "V-O02", "detalle_origen.iso")
    if p is not None:
        problemas.append(p)
    drivers = det.drivers
    usa_drivers = cfg.tipo_so is not None and TABLA_SO[cfg.tipo_so].drivers
    if not usa_drivers:
        # QA-M4-06: si el SO no usa drivers la resolución no los conserva (ni se revalidan).
        drivers = None
    quiere = usa_drivers and not det.sin_drivers
    if quiere and inv.catalogo is not None:
        if drivers is not None and (drivers.volid or drivers.nombre):
            drivers, p = _resolver_ref(
                inv, nodo, drivers, Contenido.ISO, "V-O02", "detalle_origen.drivers"
            )
            if p is not None:
                problemas.append(p)
        else:
            drivers, es_fijado = _detectar_drivers_elegido(inv, nodo)
            if drivers is not None and not es_fijado:
                # V-O31 (aviso): no es el virtio-win fijado por la app; no se elige en silencio.
                problemas.append(
                    Problema(
                        "detalle_origen",
                        "V-O31",
                        Severidad.AVISO,
                        {"volid": drivers.volid or ""},
                    )
                )
            if drivers is None and _hay_listado(inv.catalogo, nodo, Contenido.ISO):
                problemas.append(
                    _problema("detalle_origen.drivers", "V-O02.drivers", motivo="sin_drivers")
                )
    return DetalleIso(iso=iso, drivers=drivers, sin_drivers=det.sin_drivers)


def _resolver_imagen(
    inv: Inventario, nodo: str, det: DetalleImportacion, problemas: list[Problema]
) -> DetalleImportacion:
    imagen, p = _resolver_ref(
        inv, nodo, det.imagen, Contenido.IMPORT, "V-O03", "detalle_origen.imagen"
    )
    if p is not None:
        problemas.append(p)
    return DetalleImportacion(
        imagen=imagen,
        ampliar_a_gib=det.ampliar_a_gib,
        tamano_virtual_bytes=det.tamano_virtual_bytes,
    )


# --- Resolución de la plantilla --------------------------------------------------------------


def _es_compartida(p: Plantilla, inv: Inventario) -> bool:
    """Todos los discos de la plantilla están en storages compartidos de su nodo."""
    if p.detalle is None or not p.detalle.discos:
        return False
    compartidos = {s.id for s in _storages_nodo(inv, p.nodo) if s.compartido and s.activo}
    return all(d.storage in compartidos for d in p.detalle.discos)


def _alcanzable(p: Plantilla, nodo: str, inv: Inventario) -> bool:
    """Se puede clonar a ``nodo``: sus discos están en storages compartidos activos allí."""
    if p.detalle is None or not p.detalle.discos:
        return False
    activos = {s.id for s in _storages_nodo(inv, nodo) if s.compartido and s.activo}
    return all(d.storage in activos for d in p.detalle.discos)


def _elegir_plantilla(
    inv: Inventario, nodo: str, ref: RefPlantilla, cat: CatalogoServidor, problemas: list[Problema]
) -> Plantilla | None:
    campo = "detalle_origen.plantilla"
    candidatas = cat.plantillas_por_nombre(ref.nombre) if ref.nombre else ()
    if not candidatas and ref.vmid is not None:
        candidatas = tuple(p for p in (cat.plantillas or ()) if p.vmid == ref.vmid)
    if not candidatas:
        alternativas = _alternativas([p.nombre for p in cat.plantillas or ()])
        problemas.append(
            _problema(
                campo, "V-O04", motivo="no_existe", nombre=ref.nombre, alternativas=alternativas
            )
        )
        return None

    def desempatar(grupo: list[Plantilla]) -> Plantilla | None:
        por_vmid = [p for p in grupo if p.vmid == ref.vmid]
        if len(por_vmid) == 1:
            return por_vmid[0]
        vmids = ", ".join(f"{p.nodo}:{p.vmid}" for p in grupo)
        problemas.append(_problema(campo, "V-O04.ambiguo", nombre=ref.nombre, plantillas=vmids))
        return None

    # Mismo nombre en varios nodos con storage compartido: se pide elegir (CA-O23.5).
    compartidas = [p for p in candidatas if _es_compartida(p, inv)]
    if len(compartidas) > 1 and len({p.nodo for p in compartidas}) > 1:
        return desempatar(list(compartidas))
    locales = [p for p in candidatas if p.nodo == nodo]
    if len(locales) == 1:
        return locales[0]
    if len(locales) > 1:
        return desempatar(locales)
    remotas = [p for p in candidatas if _alcanzable(p, nodo, inv)]
    if len(remotas) == 1:
        return remotas[0]
    if len(remotas) > 1:
        return desempatar(remotas)
    problemas.append(_problema(campo, "V-O04", motivo="no_en_nodo", nombre=ref.nombre, nodo=nodo))
    return None


def _resolver_clon(
    cfg: ConfiguracionVM, inv: Inventario, nodo: str, det: DetalleClon, problemas: list[Problema]
) -> ConfiguracionVM:
    cat = inv.catalogo
    if cat is None or cat.plantillas is None:
        return cfg  # plantillas sin leer: nada que resolver todavía
    plantilla = _elegir_plantilla(inv, nodo, det.plantilla, cat, problemas)
    if plantilla is None:
        return cfg
    campo = "detalle_origen.plantilla"
    if plantilla.bloqueo:
        problemas.append(_problema(campo, "V-O04", motivo="bloqueada", bloqueo=plantilla.bloqueo))
        return cfg
    detalle = plantilla.detalle
    if detalle is None:
        problemas.append(_problema(campo, "V-O04", motivo="sin_detalle", nombre=plantilla.nombre))
        return cfg
    modo, problema = modo_efectivo(det, detalle, inv, plantilla.nodo)
    if problema is not None:
        problemas.append(problema)
    nueva = copy.deepcopy(cfg)
    nueva.detalle_origen = DetalleClon(
        plantilla=RefPlantilla(plantilla.nombre, plantilla.vmid, plantilla.nodo),
        modo=det.modo,
        ajustes=det.ajustes,
        storage_destino=det.storage_destino,
        modo_efectivo=modo,
    )
    a = det.ajustes
    # Valores efectivos para presupuesto, memoria (V-L12), informe y libro (§3.1).
    nueva.sockets = a.sockets if a.sockets is not None else (detalle.sockets or nueva.sockets)
    nueva.cores = a.cores if a.cores is not None else (detalle.cores or nueva.cores)
    nueva.tipo_cpu = a.tipo_cpu if a.tipo_cpu is not None else (detalle.tipo_cpu or nueva.tipo_cpu)
    nueva.memoria_mib = (
        a.memoria_mib if a.memoria_mib is not None else (detalle.memoria_mib or nueva.memoria_mib)
    )
    return nueva


def resolver_origen(
    cfg: ConfiguracionVM, inv: Inventario, nodo: str
) -> tuple[ConfiguracionVM, list[Problema]]:
    """Copia de ``cfg`` con el origen resuelto en ``nodo`` y los problemas de la resolución.

    - ISO e imagen: ``volid`` por nombre en el nodo (único; varios → ``V-O0x.ambiguo``).
    - Drivers virtio-win de Windows: el indicado o el más reciente presente en un storage ``iso``
      activo (ninguno y sin ``sin_drivers`` → ``V-O02.drivers``).
    - Clon: la plantilla de ese nodo (o alcanzable por storage compartido), el modo efectivo y los
      valores efectivos de CPU y memoria (ajuste o plantilla).
    Sin catálogo leído no se afirma nada: la referencia queda como estaba (la capa 2 la exige).
    """
    det = cfg.detalle_origen
    problemas: list[Problema] = []
    if cfg.origen == OrigenSO.ISO and isinstance(det, DetalleIso):
        nueva = copy.deepcopy(cfg)
        nueva.detalle_origen = _resolver_iso(cfg, inv, nodo, det, problemas)
        return nueva, problemas
    if cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion):
        nueva = copy.deepcopy(cfg)
        nueva.detalle_origen = _resolver_imagen(inv, nodo, det, problemas)
        return nueva, problemas
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA and isinstance(det, DetalleClon):
        return _resolver_clon(cfg, inv, nodo, det, problemas), problemas
    return cfg, problemas


# --- Elegibilidad de nodo (V-O25) -----------------------------------------------------------


def _motivo(nodo: str, motivo: str, **params: str) -> ProblemaLote:
    return ProblemaLote(
        "V-L11", SeveridadLote.ERROR, "destino", {"nodo": nodo, "motivo": motivo, **params}
    )


def _falta_archivo(inv: Inventario, nodo: str, ref: RefVolumen, contenido: Contenido) -> str | None:
    """Nombre de la fuente que falta en el nodo, o ``None`` si está (o no se puede saber)."""
    cat = inv.catalogo
    if cat is None or not _catalogo_leido(cat, contenido):
        return None
    if ref.volid:
        v = cat.buscar_volid(ref.volid, nodo)
        presente = v is not None and _storage_activo(inv, nodo, v.storage)
        partes = partes_volid(ref.volid)
        nombre = ref.nombre or (partes[2] if partes else "")
    elif ref.nombre:
        presente = any(
            v.admitido and _storage_activo(inv, nodo, v.storage)
            for v in cat.buscar_nombre(ref.nombre, nodo, contenido)
        )
        nombre = ref.nombre
    else:
        return None
    return None if presente else nombre


def _motivos_clon(
    inv: Inventario, nodo: str, det: DetalleClon, red: RedClon | None = None
) -> list[ProblemaLote]:
    cat = inv.catalogo
    if cat is None or cat.plantillas is None or not det.plantilla.nombre:
        return []
    candidatas = cat.plantillas_por_nombre(det.plantilla.nombre)
    if not candidatas:
        return []  # «no existe» lo da la resolución, no es cuestión de nodo
    elegible = [p for p in candidatas if p.nodo == nodo or _alcanzable(p, nodo, inv)]
    if not elegible:
        activos = {s.id for s in _storages_nodo(inv, nodo) if s.activo}
        usados = sorted({d.storage for p in candidatas if p.detalle for d in p.detalle.discos})
        # Si todos los storages de la plantilla existen y están activos en el nodo (mismo nombre,
        # pero no compartido), el motivo cita igualmente el storage de la plantilla.
        faltan = [s for s in usados if s not in activos] or usados
        return [
            _motivo(
                nodo,
                "plantilla",
                plantilla=det.plantilla.nombre,
                storage=faltan[0] if faltan else "",
            )
        ]
    # Una VNet de SDN es, para Proxmox, un nombre de bridge (DT-C4).
    bridges = redes_de_nodo(inv, nodo)
    # Los bridges FINALES del clon (los de la plantilla tras CAMBIAR/AÑADIR/QUITAR) deben existir
    # en el nodo (CA-O22.9; sin red personalizada son los de la plantilla).
    finales: list[tuple[str, ...]] = []
    for p in elegible:
        if p.detalle is None:
            return []
        exigidos = bridges_finales(p.detalle.bridges, p.detalle.tarjetas, red)
        if not [b for b in exigidos if b not in bridges]:
            return []
        finales.append(exigidos)
    primero = next(b for b in finales[0] if b not in bridges)
    return [_motivo(nodo, "bridge", bridge=primero, plantilla=det.plantilla.nombre)]


def motivos_nodo_origen(cfg: ConfiguracionVM, inv: Inventario, nodo: str) -> list[ProblemaLote]:
    """Motivos ``V-L11`` (``fuente`` o ``plantilla``) por los que ``nodo`` no sirve para el origen.

    Vacío = elegible por origen (V-O25). Sin catálogo leído no se descarta ningún nodo. Un ISO,
    una imagen o un CD de drivers deben estar en un storage activo de ese nodo (compartido o
    local); una plantilla, en ese nodo o alcanzable por storage compartido, con sus bridges.
    """
    det = cfg.detalle_origen
    if cfg.origen == OrigenSO.ISO and isinstance(det, DetalleIso):
        falta = _falta_archivo(inv, nodo, det.iso, Contenido.ISO)
        if falta is not None:
            return [_motivo(nodo, "fuente", fuente=falta, tipo="iso")]
        quiere = cfg.tipo_so is not None and TABLA_SO[cfg.tipo_so].drivers and not det.sin_drivers
        if quiere:
            if det.drivers is not None and (det.drivers.volid or det.drivers.nombre):
                falta = _falta_archivo(inv, nodo, det.drivers, Contenido.ISO)
                if falta is not None:
                    return [_motivo(nodo, "fuente", fuente=falta, tipo="drivers")]
            elif inv.catalogo is not None and _hay_listado(inv.catalogo, nodo, Contenido.ISO):
                # Detección: el nodo sin virtio-win solo se excluye si otro nodo sí lo tiene.
                otros = {n.nombre for n in inv.topologia.nodos} - {nodo}
                if _detectar_drivers(inv, nodo) is None and any(
                    _detectar_drivers(inv, o) is not None for o in otros
                ):
                    return [_motivo(nodo, "fuente", fuente="virtio-win", tipo="drivers")]
        return []
    if cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion):
        falta = _falta_archivo(inv, nodo, det.imagen, Contenido.IMPORT)
        return [] if falta is None else [_motivo(nodo, "fuente", fuente=falta, tipo="imagen")]
    if cfg.origen == OrigenSO.CLONAR_PLANTILLA and isinstance(det, DetalleClon):
        return _motivos_clon(inv, nodo, det, cfg.red_clon)
    return []


# --- Firma, espera y UPID ------------------------------------------------------------------


def firma_origen(cfg: ConfiguracionVM) -> tuple[object, ...]:
    """Lo que del origen decide la elegibilidad y el espacio (para la caché del reparto)."""
    det = cfg.detalle_origen
    base: tuple[object, ...] = (str(cfg.origen), cfg.tpm)
    if isinstance(det, DetalleIso):
        drivers = None if det.drivers is None else (det.drivers.volid, det.drivers.nombre)
        return (
            *base,
            det.iso.volid,
            det.iso.nombre,
            drivers,
            det.sin_drivers,
            None if cfg.tipo_so is None else str(cfg.tipo_so),
        )
    if isinstance(det, DetalleImportacion):
        return (
            *base,
            det.imagen.volid,
            det.imagen.nombre,
            det.ampliar_a_gib,
            det.tamano_virtual_bytes,
        )
    if isinstance(det, DetalleClon):
        a = det.ajustes
        return (
            *base,
            det.plantilla.nombre,
            det.plantilla.vmid,
            str(det.modo),
            det.storage_destino,
            (a.sockets, a.cores, a.tipo_cpu, a.memoria_mib, a.disco_gib),
        )
    return base


def _gib(bytes_: int) -> int:
    return -(-bytes_ // _GIB)


def espera_maxima_s(cfg: ConfiguracionVM, inv: Inventario, base_s: float) -> float:
    """Espera máxima de la tarea de creación (CA-O17.4, enmienda 14.4).

    Importación: ``max(ESPERA_BASE_S, ESPERA_POR_GIB_S × GiB)`` con el tamaño virtual o, si se
    desconoce, el del archivo. Clon completo: lo mismo con la suma de los discos de la plantilla.
    El resto (y el clon enlazado) usa ``base_s``. Nunca es menor que ``base_s``.
    """
    det = cfg.detalle_origen
    gib = 0
    if cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion):
        tamano = det.tamano_virtual_bytes
        if tamano is None and inv.catalogo is not None and det.imagen.volid:
            volumen = inv.catalogo.buscar_volid(det.imagen.volid, cfg.nodo)
            tamano = None if volumen is None else volumen.tamano_bytes
        gib = _gib(tamano) if tamano else 0
    elif (
        cfg.origen == OrigenSO.CLONAR_PLANTILLA
        and isinstance(det, DetalleClon)
        and det.modo_efectivo == ModoClon.COMPLETO
        and inv.catalogo is not None
    ):
        for p in inv.catalogo.plantillas or ():
            if p.vmid == det.plantilla.vmid and p.nodo == det.plantilla.nodo and p.detalle:
                gib = _gib(sum(d.tamano_bytes or 0 for d in p.detalle.discos))
                break
    else:
        return base_s
    return max(base_s, ESPERA_BASE_S, ESPERA_POR_GIB_S * gib)


def nodo_de_upid(upid: str) -> str | None:
    """Nodo que figura en un UPID (``UPID:<nodo>:<pid>:…``); ``None`` si no tiene esa forma."""
    if not isinstance(upid, str) or not upid.startswith("UPID:"):
        return None
    partes = upid.split(":")
    if len(partes) < 8:
        return None
    nodo = partes[1]
    return nodo if _RE_UPID_NODO.fullmatch(nodo) else None
