"""Reglas de validación V-O01..V-O30 del origen del SO (docs/requisitos/mvp4.md §7). Puras.

- Capa 1 (``validar_origen_sin_servidor``): no necesita servidor; la usan perfiles, lotes, CSV y
  ``validar_vm``. Sus códigos están en ``CODIGOS_ORIGEN_SIN_SERVIDOR``.
- Capa 2 (``validar_origen``): contra el inventario y el catálogo ya leídos, sobre la
  configuración **resuelta** (``resolver_origen``). No hace E/S.

Los ``Problema`` son los de ``nucleo.validacion`` (código y parámetros, nunca texto de interfaz).
Este módulo importa ``validacion``; ``validacion.validar_vm`` lo importa de forma diferida.
"""

from __future__ import annotations

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.modelos.catalogo import CatalogoServidor, Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.vm import Bus, ConfiguracionVM, Firmware, OrigenSO
from proxlaunch.nucleo.origen.asistente import TABLA_SO, avisos_so
from proxlaunch.nucleo.origen.clon import disco_principal, modo_efectivo
from proxlaunch.nucleo.origen.nombres import partes_volid, validar_volid
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.validacion import (
    CODIGOS_ORIGEN_SIN_SERVIDOR,
    CORES_MAX,
    CORES_MIN,
    DISCO_MAX_GIB,
    DISCO_MIN_GIB,
    MEMORIA_MIN_MIB,
    SOCKETS_MAX,
    SOCKETS_MIN,
    Problema,
    Severidad,
    storage_efi_efectivo,
    tipo_cpu_valido,
)

__all__ = [
    "CODIGOS_ORIGEN_SIN_SERVIDOR",
    "validar_origen",
    "validar_origen_sin_servidor",
]

_GIB = 1024**3
MAX_IDE_CON_ISO = 2  # ide1 e ide3 (ide0 e ide2 son de los CD, V-O06)


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def _aviso(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.AVISO, dict(params))


# --- Capa 1 --------------------------------------------------------------------------------


def _coherencia(cfg: ConfiguracionVM, p: list[Problema]) -> None:
    """V-O01: el detalle es el del origen, está completo y no hay datos de SO ajenos."""
    origen, det = cfg.origen, cfg.detalle_origen
    esperado = {
        OrigenSO.ISO: DetalleIso,
        OrigenSO.IMPORTAR_DISCO: DetalleImportacion,
        OrigenSO.CLONAR_PLANTILLA: DetalleClon,
    }.get(origen)
    if esperado is None:
        if det is not None:
            p.append(_error("detalle_origen", "V-O01", motivo="incoherente"))
    elif det is None:
        p.append(_error("detalle_origen", "V-O01", motivo="falta"))
    elif not isinstance(det, esperado):
        p.append(_error("detalle_origen", "V-O01", motivo="incoherente"))
    elif isinstance(det, DetalleIso):
        if not (det.iso.volid or det.iso.nombre):
            p.append(_error("detalle_origen.iso", "V-O01", motivo="falta_fuente"))
        if cfg.tipo_so is None:
            p.append(_error("tipo_so", "V-O01", motivo="falta_so"))
    elif isinstance(det, DetalleImportacion):
        if not (det.imagen.volid or det.imagen.nombre):
            p.append(_error("detalle_origen.imagen", "V-O01", motivo="falta_fuente"))
    elif isinstance(det, DetalleClon) and not (det.plantilla.nombre or det.plantilla.vmid):
        p.append(_error("detalle_origen.plantilla", "V-O01", motivo="falta_fuente"))
    if origen in (OrigenSO.DISCO_VACIO, OrigenSO.CLONAR_PLANTILLA):
        for campo, activo in (
            ("tipo_so", cfg.tipo_so is not None),
            ("tpm", cfg.tpm),
            ("agente_qemu", cfg.agente_qemu),
        ):
            if activo:
                p.append(_aviso(campo, "V-O01.ajeno", origen=str(origen)))


def _tipo_so(cfg: ConfiguracionVM, p: list[Problema]) -> None:
    """V-O05 (Windows 11 exige UEFI y TPM; otro Windows con SeaBIOS es aviso) y V-O07/RHEL."""
    if cfg.tipo_so is None:
        return
    perfil = TABLA_SO[cfg.tipo_so]
    if perfil.tpm_obligatorio:
        if cfg.firmware != Firmware.OVMF:
            p.append(_error("firmware", "V-O05", motivo="uefi", tipo_so=str(cfg.tipo_so)))
        if not cfg.tpm:
            p.append(_error("tpm", "V-O05", motivo="tpm", tipo_so=str(cfg.tipo_so)))
    elif perfil.es_windows and cfg.firmware != Firmware.OVMF:
        p.append(_aviso("firmware", "V-O05.seabios", tipo_so=str(cfg.tipo_so)))
    p.extend(avisos_so(cfg))


def _rango_disco(valor: int | None, campo: str, p: list[Problema]) -> None:
    if valor is None:
        return
    if not _es_entero(valor) or not DISCO_MIN_GIB <= valor <= DISCO_MAX_GIB:
        p.append(_error(campo, "V-O23", minimo=str(DISCO_MIN_GIB), maximo=str(DISCO_MAX_GIB)))


def _ajustes(a: AjustesClon, p: list[Problema]) -> None:
    """V-O23 (rango del disco) y V-O24 (CPU y memoria con las reglas V-05, V-06 y V-22)."""
    base = "detalle_origen.ajustes"
    if a.sockets is not None and (
        not _es_entero(a.sockets) or not SOCKETS_MIN <= a.sockets <= SOCKETS_MAX
    ):
        p.append(_error(f"{base}.sockets", "V-O24", regla="V-05"))
    if a.cores is not None and (not _es_entero(a.cores) or not CORES_MIN <= a.cores <= CORES_MAX):
        p.append(_error(f"{base}.cores", "V-O24", regla="V-05"))
    if a.memoria_mib is not None and (
        not _es_entero(a.memoria_mib) or a.memoria_mib < MEMORIA_MIN_MIB
    ):
        p.append(_error(f"{base}.memoria_mib", "V-O24", regla="V-06"))
    if a.tipo_cpu is not None and not tipo_cpu_valido(a.tipo_cpu):
        p.append(_error(f"{base}.tipo_cpu", "V-O24", regla="V-22"))
    _rango_disco(a.disco_gib, f"{base}.disco_gib", p)


def validar_origen_sin_servidor(cfg: ConfiguracionVM) -> list[Problema]:
    """V-O01, V-O05, V-O06, V-O07, V-O23, V-O24 y V-O29 (capa 1, sin servidor).

    Con ``disco_vacio`` y datos de SO ajenos solo da el aviso ``V-O01.ajeno``; una MV de
    M1–M3 (sin esos campos) no produce ningún problema.
    """
    p: list[Problema] = []
    _coherencia(cfg, p)
    det = cfg.detalle_origen
    origen = cfg.origen
    if origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO):
        _tipo_so(cfg, p)
    if origen == OrigenSO.ISO and isinstance(det, DetalleIso):
        if cfg.con_disco:
            ide = sum(1 for d in cfg.discos if d.bus == Bus.IDE)
            if ide > MAX_IDE_CON_ISO:
                p.append(_error("discos", "V-O06", maximo=str(MAX_IDE_CON_ISO), n=str(ide)))
        else:
            p.append(_aviso("con_disco", "V-O29.sindisco"))
    elif origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion):
        if not cfg.con_disco or not cfg.discos:
            p.append(_error("con_disco", "V-O29", motivo="importar_exige_disco"))
        _rango_disco(det.ampliar_a_gib, "detalle_origen.ampliar_a_gib", p)
    elif origen == OrigenSO.CLONAR_PLANTILLA and isinstance(det, DetalleClon):
        _ajustes(det.ajustes, p)
    return p


# --- Capa 2 --------------------------------------------------------------------------------


def _hay_listado(cat: CatalogoServidor | None, nodo: str, contenido: Contenido) -> bool:
    return cat is not None and any(
        lst.nodo == nodo and lst.contenido == contenido for lst in cat.listados
    )


def _storage_activo(inv: Inventario, nodo: str, storage: str) -> bool | None:
    """``None`` = no se conocen los storages de ese nodo (no se puede afirmar nada)."""
    if nodo not in inv.storages_todos:
        return None
    return any(s.id == storage and s.activo for s in inv.storages_todos[nodo])


def _volumen(
    cfg: ConfiguracionVM,
    inv: Inventario,
    ref: RefVolumen,
    contenido: Contenido,
    campo: str,
    codigo: str,
    p: list[Problema],
) -> None:
    """V-O02 (ISO, drivers) y V-O03 (imagen): lista blanca, existencia y storage activo."""
    if not ref.volid:
        if ref.nombre:
            p.append(_error(campo, codigo, motivo="sin_resolver", nombre=ref.nombre))
        return
    motivo = validar_volid(ref.volid, contenido)
    if motivo is not None:
        p.append(_error(campo, codigo, motivo=motivo))
        return
    cat = inv.catalogo
    if _hay_listado(cat, cfg.nodo, contenido):
        assert cat is not None
        volumen = cat.buscar_volid(ref.volid, cfg.nodo)
        if volumen is None:
            p.append(_error(campo, codigo, motivo="no_disponible", nodo=cfg.nodo, volid=ref.volid))
            return
        if not volumen.admitido:
            p.append(_error(campo, codigo, motivo="nombre_no_admitido"))
            return
    partes = partes_volid(ref.volid)
    if partes is not None and _storage_activo(inv, cfg.nodo, partes[0]) is False:
        p.append(_error(campo, codigo, motivo="storage_inactivo", storage=partes[0], nodo=cfg.nodo))


def _validar_iso(cfg: ConfiguracionVM, inv: Inventario, det: DetalleIso, p: list[Problema]) -> None:
    _volumen(cfg, inv, det.iso, Contenido.ISO, "detalle_origen.iso", "V-O02", p)
    if cfg.tipo_so is not None and TABLA_SO[cfg.tipo_so].drivers and not det.sin_drivers:
        if det.drivers is None or not det.drivers.volid:
            p.append(_error("detalle_origen.drivers", "V-O02.drivers", motivo="sin_drivers"))
        else:
            _volumen(cfg, inv, det.drivers, Contenido.ISO, "detalle_origen.drivers", "V-O02", p)


def _validar_tpm(cfg: ConfiguracionVM, inv: Inventario, p: list[Problema]) -> None:
    """V-O08: el TPM necesita un storage con ``images`` activo (el del ``efidisk0``)."""
    if not cfg.tpm or cfg.firmware == Firmware.OVMF:
        return  # con OVMF ya lo comprueba V-17 (sin reglas duplicadas, CA-O13.12)
    id_efi = storage_efi_efectivo(cfg, inv)
    st = next((s for s in inv.storages.get(cfg.nodo, ()) if s.id == id_efi), None)
    if st is None or not st.activo or "images" not in st.contenido:
        p.append(_error("storage_efi", "V-O08", storage=id_efi or "", nodo=cfg.nodo))


def _validar_importacion(
    cfg: ConfiguracionVM,
    inv: Inventario,
    caps: Capacidades,
    det: DetalleImportacion,
    p: list[Problema],
) -> None:
    _volumen(cfg, inv, det.imagen, Contenido.IMPORT, "detalle_origen.imagen", "V-O03", p)
    if det.ampliar_a_gib is not None and det.tamano_virtual_bytes is not None:
        actual = -(-det.tamano_virtual_bytes // _GIB)
        if det.ampliar_a_gib < actual:
            p.append(
                _error(
                    "detalle_origen.ampliar_a_gib",
                    "V-O23.tamano",
                    actual_gib=str(actual),
                    pedido_gib=str(det.ampliar_a_gib),
                )
            )
    if cfg.discos:
        destino = cfg.discos[0].storage
        cat = inv.catalogo
        if (
            cat is not None
            and estado_privilegio(cat.permisos, "Datastore.AllocateSpace", f"/storage/{destino}")
            is False
        ):
            p.append(
                _error(
                    "discos[0].storage",
                    "V-O19",
                    motivo="destino_sin_permiso",
                    storage=destino,
                    privilegio="Datastore.AllocateSpace",
                )
            )


def _validar_clon(
    cfg: ConfiguracionVM, inv: Inventario, det: DetalleClon, p: list[Problema]
) -> None:
    cat = inv.catalogo
    ref = det.plantilla
    campo = "detalle_origen.plantilla"
    if ref.vmid is None or not ref.nodo:
        p.append(_error(campo, "V-O04", motivo="sin_resolver", nombre=ref.nombre))
        return
    plantilla = None
    if cat is not None and cat.plantillas is not None:
        plantilla = next(
            (x for x in cat.plantillas if x.vmid == ref.vmid and x.nodo == ref.nodo), None
        )
        if plantilla is None:
            p.append(_error(campo, "V-O04", motivo="no_existe", nombre=ref.nombre))
            return
        if plantilla.bloqueo:
            p.append(_error(campo, "V-O04", motivo="bloqueada", bloqueo=plantilla.bloqueo))
    if cat is not None and estado_privilegio(cat.permisos, "VM.Clone", f"/vms/{ref.vmid}") is False:
        p.append(_error(campo, "V-O17", privilegio="VM.Clone", ruta=f"/vms/{ref.vmid}"))
    detalle = None if plantilla is None else plantilla.detalle
    if detalle is not None:
        _, problema = modo_efectivo(det, detalle, inv, ref.nodo)
        if problema is not None:
            p.append(problema)
    elif det.modo == ModoClon.ENLAZADO and det.storage_destino:
        p.append(_error("detalle_origen.modo", "V-O21", motivo="storage_destino"))
    if det.storage_destino and det.modo_efectivo != ModoClon.ENLAZADO:
        st = next((s for s in inv.storages.get(cfg.nodo, ()) if s.id == det.storage_destino), None)
        if st is None or not st.activo or "images" not in st.contenido:
            p.append(
                _error(
                    "detalle_origen.storage_destino",
                    "V-17",
                    storage=det.storage_destino,
                    nodo=cfg.nodo,
                )
            )
    pedido = det.ajustes.disco_gib
    if pedido is not None and detalle is not None:
        principal = disco_principal(detalle)
        if principal is not None and principal.tamano_bytes is not None:
            actual = -(-principal.tamano_bytes // _GIB)
            if pedido < actual:
                p.append(
                    _error(
                        "detalle_origen.ajustes.disco_gib",
                        "V-O23.tamano",
                        actual_gib=str(actual),
                        pedido_gib=str(pedido),
                    )
                )


def _validar_permiso_disco(cfg: ConfiguracionVM, inv: Inventario, p: list[Problema]) -> None:
    """V-O18: sin certeza de ``VM.Config.Disk`` se omite ``boot`` o la ampliación (INV-O10)."""
    det = cfg.detalle_origen
    amplia = (isinstance(det, DetalleImportacion) and det.ampliar_a_gib is not None) or (
        isinstance(det, DetalleClon) and det.ajustes.disco_gib is not None
    )
    if cfg.origen == OrigenSO.ISO:
        efecto = "orden_arranque"
    elif amplia:
        efecto = "ampliar"
    else:
        return
    permisos = None if inv.catalogo is None else inv.catalogo.permisos
    estado = estado_privilegio(permisos, "VM.Config.Disk", f"/vms/{cfg.vmid}")
    if estado is not True:
        p.append(
            _aviso(
                "origen",
                "V-O18",
                efecto=efecto,
                privilegio="VM.Config.Disk",
                desconocido="1" if estado is None else "0",
            )
        )


def validar_origen(cfg: ConfiguracionVM, inv: Inventario, caps: Capacidades) -> list[Problema]:
    """Capa 2 del origen (V-O02..V-O04, V-O08, V-O17..V-O19, V-O21, V-O23): contra el servidor.

    Espera la configuración ya resuelta (``resolver_origen``) y no repite la capa 1: ``validar_vm``
    llama a ambas. Si el catálogo del nodo no se ha leído no se afirma que un volumen falte;
    sí se exige que la referencia esté resuelta (volid o plantilla) y sea admisible.
    """
    p: list[Problema] = []
    det = cfg.detalle_origen
    if cfg.origen == OrigenSO.ISO and isinstance(det, DetalleIso):
        _validar_iso(cfg, inv, det, p)
        _validar_tpm(cfg, inv, p)
    elif cfg.origen == OrigenSO.IMPORTAR_DISCO and isinstance(det, DetalleImportacion):
        _validar_importacion(cfg, inv, caps, det, p)
        _validar_tpm(cfg, inv, p)
    elif cfg.origen == OrigenSO.CLONAR_PLANTILLA and isinstance(det, DetalleClon):
        _validar_clon(cfg, inv, det, p)
    else:
        return p  # incoherencias: las da la capa 1 (V-O01)
    _validar_permiso_disco(cfg, inv, p)
    return p
