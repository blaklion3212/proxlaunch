"""Validación de B2: reglas V-B01..V-B16 (RF-B2.*, §4 de la arquitectura de la fase B).

``validar_solicitud`` solo LEE: inspecciona la cabecera de un archivo local y mira el inventario
y el catálogo ya leídos; no hace ninguna petición. Los ``params`` de los problemas no llevan
rutas locales, URLs ni sumas completas (solo nombres de archivo y motivos). El nombre de archivo
que sale de aquí es el que va al almacenamiento ``import``.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

from proxlaunch.nucleo.arquitectura.modelos import arquitectura_efectiva
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.modelos import (
    InfoCloudInitPlantilla,
    ModoTarjeta,
)
from proxlaunch.nucleo.cloudinit.validacion import validar_cloudinit
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleClon, RefPlantilla
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.nombres import validar_nombre_archivo, validar_volid
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.origen.storages import candidatos
from proxlaunch.nucleo.plantilla_imagen.modelos import (
    EXTENSIONES_IMAGEN,
    OrigenImagen,
    SolicitudPlantillaImagen,
)
from proxlaunch.nucleo.plantilla_imagen.peticion import (
    cfg_de_creacion,
    nombre_archivo_import,
    tamano_final_gib,
    tamano_virtual_gib,
    volid_de_imagen,
)
from proxlaunch.nucleo.transferencias.archivo_local import TipoArchivoLocal, inspeccionar
from proxlaunch.nucleo.transferencias.url import AlgoritmoChecksum, UrlDescarga
from proxlaunch.nucleo.validacion import Problema, Severidad, nombre_dns_valido, validar_vm

_RE_UBUNTU_DEBIAN = re.compile(r"ubuntu|debian|cloudimg", re.IGNORECASE)
_RE_HEX = re.compile(r"^[0-9a-fA-F]+$")
_LONGITUD_POR_ALGORITMO = {
    AlgoritmoChecksum.MD5: 32,
    AlgoritmoChecksum.SHA1: 40,
    AlgoritmoChecksum.SHA224: 56,
    AlgoritmoChecksum.SHA256: 64,
    AlgoritmoChecksum.SHA384: 96,
    AlgoritmoChecksum.SHA512: 128,
}
# Reglas de ``validar_vm`` que en B2 se reportan como V-B09 / V-B11 (RF-B2.6).
_REGLAS_NOMBRE = frozenset({"V-01"})
_REGLAS_RANGOS = frozenset({"V-05", "V-06", "V-08", "V-22", "V-O23"})
# Reglas de ``validar_vm`` que no aplican a B2 (la imagen aún no existe en el catálogo leído, o
# dependen de datos de lote).
_REGLAS_IGNORADAS = frozenset({"V-O03", "V-O18", "V-O19"})
PRIVILEGIO_HWTYPE = "VM.Config.HWType"
PRIVILEGIO_OPCIONES = "VM.Config.Options"
PRIVILEGIO_DISCO = "VM.Config.Disk"


@dataclass(frozen=True)
class InspeccionImagen:
    """Lo que la interfaz necesita saber de un archivo local antes de pedir nada (RF-B2.3/6)."""

    nombre_final: str | None  # nombre en el almacenamiento ``import`` (``.img`` renombrado)
    motivo_rechazo: str | None  # ``extension``, ``otro_formato``, ``backing``, ``cifrado``…
    es_qcow2: bool | None
    tamano_bytes: int
    tamano_virtual_bytes: int | None  # de la cabecera qcow2/vmdk; el crudo mide lo que el archivo
    avisos: tuple[str, ...] = ()


def inspeccionar_imagen(ruta: Path) -> InspeccionImagen:
    """Lee solo la cabecera del archivo (CA-B2.3.1, CA-B2.6.4). Nunca lo modifica.

    ``.img`` con firma qcow2 → ``.qcow2``; ``.img`` crudo → ``.raw``; otro contenido (vmdk, ova…)
    o una extensión que no corresponde al contenido se rechazan (no se renombra a ciegas).

    Raises:
        ErrorProxLaunch: ``ARCHIVO_NO_ACCESIBLE`` o ``ARCHIVO_NO_PERMITIDO`` (vacío, no regular).
    """
    ruta = Path(ruta)
    ins = inspeccionar(ruta, Contenido.IMPORT)
    es_qcow2 = ins.tipo == TipoArchivoLocal.QCOW2
    sufijo = ruta.suffix.lower()
    motivo = ins.motivo_rechazo
    if motivo is None:
        coincide = {
            ".qcow2": TipoArchivoLocal.QCOW2,
            ".raw": TipoArchivoLocal.RAW,
            ".vmdk": TipoArchivoLocal.VMDK,
        }.get(sufijo)
        if sufijo == ".img":
            if ins.tipo not in (TipoArchivoLocal.QCOW2, TipoArchivoLocal.RAW):
                motivo = "otro_formato"
        elif coincide is None:
            motivo = "extension"
        elif ins.tipo != coincide:
            motivo = "extension_no_coincide"
    nombre: str | None = None
    if motivo is None:
        nombre, motivo = nombre_archivo_import(ruta.name, es_qcow2)
    return InspeccionImagen(
        nombre_final=nombre,
        motivo_rechazo=motivo,
        es_qcow2=es_qcow2,
        tamano_bytes=ins.tamano_bytes,
        tamano_virtual_bytes=ins.tamano_virtual_bytes,
        avisos=ins.avisos,
    )


def nombre_para_url(url: UrlDescarga) -> tuple[str | None, str | None, tuple[str, ...]]:
    """``(nombre final, motivo de rechazo, avisos)`` del archivo que descargará el servidor.

    Una URL ``.img`` se pide como ``.qcow2`` (R-B2) y se avisa «se asume formato qcow2»; la URL
    original no cambia (CA-B2.3.3).
    """
    nombre, motivo = nombre_archivo_import(url.archivo, None)
    avisos = ("se_asume_qcow2",) if url.archivo.lower().endswith(".img") else ()
    return nombre, motivo, avisos


def _error(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.ERROR, dict(params))


def _aviso(campo: str, codigo: str, **params: str) -> Problema:
    return Problema(campo, codigo, Severidad.AVISO, dict(params))


def _validar_origen(sol: SolicitudPlantillaImagen, p: list[Problema]) -> None:
    """V-B02 a V-B05 y V-B16 (lo que depende solo de la imagen)."""
    nombre_origen = ""
    if sol.origen == OrigenImagen.ARCHIVO_LOCAL:
        if sol.ruta_local is None:
            p.append(_error("origen", "V-B02", motivo="falta_archivo"))
        else:
            nombre_origen = sol.ruta_local.name
            _validar_archivo_local(sol, sol.ruta_local, p)
    elif sol.origen == OrigenImagen.URL:
        if sol.url is None:
            p.append(_error("origen", "V-B02", motivo="falta_url"))
        else:
            nombre_origen = sol.url.archivo
            if sol.url.es_http:
                p.append(_aviso("origen", "V-B02", motivo="http"))
            if not sol.url.archivo.lower().endswith(EXTENSIONES_IMAGEN):
                p.append(_error("origen", "V-B03", motivo="extension", archivo=sol.url.archivo))
    else:
        volid = sol.volid_existente or ""
        motivo = validar_volid(volid, Contenido.IMPORT) if volid else "falta"
        if motivo is not None:
            p.append(_error("origen", "V-B02", motivo="volid", detalle=motivo))
        else:
            nombre_origen = volid.partition("/")[2]
    # El nombre final que va al servidor debe ser admisible (V-B03/V-O09).
    motivo_nombre = validar_nombre_archivo(sol.nombre_archivo, Contenido.IMPORT)
    if motivo_nombre is not None:
        p.append(
            _error("nombre_archivo", "V-B03", motivo=motivo_nombre, archivo=sol.nombre_archivo)
        )
    _validar_suma(sol, p)
    if sol.fijas.agente and _RE_UBUNTU_DEBIAN.search(nombre_origen or sol.nombre_archivo):
        p.append(_aviso("fijas.agente", "V-B16", archivo=nombre_origen or sol.nombre_archivo))


def _validar_archivo_local(sol: SolicitudPlantillaImagen, ruta: Path, p: list[Problema]) -> None:
    try:
        ins = inspeccionar_imagen(ruta)
    except ErrorProxLaunch as e:
        motivo = e.params.get("motivo", str(e.codigo))
        p.append(_error("origen", "V-B02", motivo="ilegible", detalle=motivo))
        return
    if ins.motivo_rechazo is not None:
        codigo = "V-B03" if ins.motivo_rechazo == "extension" else "V-B04"
        p.append(_error("origen", codigo, motivo=ins.motivo_rechazo, archivo=ruta.name))
    elif ins.nombre_final is not None and ins.nombre_final != sol.nombre_archivo:
        # El nombre pedido no es el que corresponde al contenido: no se sube con otro nombre.
        p.append(_error("nombre_archivo", "V-B04", motivo="nombre_incoherente", archivo=ruta.name))


def _validar_suma(sol: SolicitudPlantillaImagen, p: list[Problema]) -> None:
    """V-B05: hexadecimal, longitud acorde y, para un archivo local, solo SHA-256.

    Con URL ``http://`` o sin verificar certificados nada autentica la descarga: la suma
    (SHA-256/SHA-512) es obligatoria (motivo ``suma_obligatoria``); con MD5 o SHA-1 solo se avisa
    (motivo ``suma_debil``).
    """
    suma = sol.suma
    sin_garantia = (
        sol.origen == OrigenImagen.URL
        and sol.url is not None
        and (sol.url.es_http or not sol.verificar_certificados)
    )
    if suma is None:
        if sin_garantia:
            p.append(_error("suma", "V-B05", motivo="suma_obligatoria"))
        return
    if sin_garantia and suma.algoritmo in (AlgoritmoChecksum.MD5, AlgoritmoChecksum.SHA1):
        p.append(_aviso("suma", "V-B05", motivo="suma_debil", algoritmo=str(suma.algoritmo)))
    esperada = _LONGITUD_POR_ALGORITMO.get(suma.algoritmo)
    if esperada is None or len(suma.valor) != esperada or _RE_HEX.fullmatch(suma.valor) is None:
        p.append(_error("suma", "V-B05", motivo="formato", algoritmo=str(suma.algoritmo)))
    elif sol.origen == OrigenImagen.ARCHIVO_LOCAL and suma.algoritmo != AlgoritmoChecksum.SHA256:
        p.append(_error("suma", "V-B05", motivo="solo_sha256_local", algoritmo=str(suma.algoritmo)))
    elif sol.origen == OrigenImagen.YA_IMPORTADA:
        p.append(_aviso("suma", "V-B05", motivo="no_se_usa"))


def _validar_almacenamientos(
    sol: SolicitudPlantillaImagen, inv: Inventario, p: list[Problema]
) -> None:
    """V-B06, V-B07, V-B08 y V-B13."""
    imports = candidatos(inv, Contenido.IMPORT, sol.nodo)
    if not imports:
        p.append(_error("storage_import", "V-B06", motivo="sin_import", nodo=sol.nodo))
    elif sol.storage_import not in {s.id for s in imports}:
        p.append(_error("storage_import", "V-B06", motivo="no_valido", storage=sol.storage_import))
    destinos = candidatos(inv, Contenido.IMAGENES, sol.nodo)
    destino = next((s for s in destinos if s.id == sol.storage_destino), None)
    if destino is None:
        p.append(_error("storage_destino", "V-B07", storage=sol.storage_destino, nodo=sol.nodo))
    elif destino.tipo == "lvm":
        p.append(_aviso("storage_destino", "V-B08", storage=destino.id, tipo=destino.tipo))
    # V-B13: nombre ya presente en el listado (si el catálogo lo trae). La elección es del
    # usuario; sin ella, la transferencia se negará a escribir (NOMBRE_YA_EXISTE).
    if sol.origen != OrigenImagen.YA_IMPORTADA and sol.accion_existente is None:
        existente = _volid_en_catalogo(inv, sol)
        if existente is not None:
            p.append(_aviso("accion_existente", "V-B13", volid=existente))


def _volid_en_catalogo(inv: Inventario, sol: SolicitudPlantillaImagen) -> str | None:
    if inv.catalogo is None:
        return None
    buscado = sol.nombre_archivo.casefold()
    for listado in inv.catalogo.listados:
        if (
            listado.nodo == sol.nodo
            and listado.storage == sol.storage_import
            and listado.contenido == Contenido.IMPORT
        ):
            for v in listado.volumenes:
                if v.nombre.casefold() == buscado:
                    return v.volid
    return None


def _validar_maquina(
    sol: SolicitudPlantillaImagen, inv: Inventario, caps: Capacidades, p: list[Problema]
) -> None:
    """V-B09, V-B11 y V-B12: las reglas de ``validar_vm`` sobre la configuración de B2."""
    if not nombre_dns_valido(sol.cfg.nombre):
        p.append(_error("nombre", "V-B09"))
    cfg = cfg_de_creacion(
        sol, volid_de_imagen(sol), arquitectura=arquitectura_efectiva(inv, sol.nodo)
    )
    for q in validar_vm(cfg, inv, caps):
        regla = q.codigo.split(".", 1)[0]
        if regla in _REGLAS_NOMBRE or regla in _REGLAS_IGNORADAS:
            continue  # el nombre ya se evaluó como V-B09
        if regla in _REGLAS_RANGOS:
            p.append(Problema(q.campo, "V-B11", q.severidad, {**q.params, "regla": q.codigo}))
        else:
            p.append(q)
    virtual = tamano_virtual_gib(sol.tamano_virtual_bytes)
    if virtual is not None and tamano_final_gib(sol) <= virtual:
        # CA-B2.6.3: solo se puede crecer; no se emite ``resize``.
        p.append(
            _aviso(
                "detalle_origen.ampliar_a_gib",
                "V-B12",
                final_gib=str(tamano_final_gib(sol)),
                imagen_gib=str(virtual),
            )
        )


def _validar_permisos(sol: SolicitudPlantillaImagen, inv: Inventario, p: list[Problema]) -> None:
    """V-B15: una opción fija marcada sin su privilegio (permisos desconocidos = no bloquea)."""
    permisos = inv.catalogo.permisos if inv.catalogo is not None else None
    ruta = f"/vms/{sol.cfg.vmid}"
    necesarios: list[tuple[str, str, bool]] = [
        ("fijas.consola_serie", PRIVILEGIO_HWTYPE, sol.fijas.consola_serie),
        ("fijas.agente", PRIVILEGIO_OPCIONES, sol.fijas.agente),
        ("fijas.unidad_cloudinit", PRIVILEGIO_DISCO, sol.fijas.unidad_cloudinit),
    ]
    for campo, privilegio, marcada in necesarios:
        if marcada and estado_privilegio(permisos, privilegio, ruta) is False:
            p.append(_error(campo, "V-B15", privilegio=privilegio, ruta=ruta))


def _info_de_la_plantilla(sol: SolicitudPlantillaImagen) -> InfoCloudInitPlantilla:
    """Lo que tendrá la plantilla creada, para validar los valores de cloud-init con las reglas
    de B1 (RF-B2.8): unidad según la casilla, Linux y una tarjeta por cada ``netN``."""
    return InfoCloudInitPlantilla(
        unidad=sol.fijas.unidad_cloudinit,
        clave_unidad="ide2" if sol.fijas.unidad_cloudinit else None,
        ostype="l26",
        es_windows=False,
        agente=sol.fijas.agente,
        tarjetas=tuple(range(len(sol.cfg.redes))),
    )


def _validar_cloudinit_b2(
    sol: SolicitudPlantillaImagen, inv: Inventario, caps: Capacidades, p: list[Problema]
) -> None:
    """V-B21..V-B37 sobre los valores por defecto de la plantilla (RF-B2.8).

    Se reutilizan las reglas de B1 evaluándolas como si la plantilla ya existiera y se clonara;
    además B2 no admite contraseña (PB-1), snippets, serie ni más tarjeta que la primera.
    """
    ci = sol.cloudinit
    if ci is None or ci.vacia:
        return
    if ci.contrasena is not None:
        p.append(_error("cloudinit.contrasena", "V-B39", motivo="contrasena_en_plantilla"))
    if not ci.snippets.como_la_plantilla:
        p.append(_error("cloudinit.snippets", "V-B39", motivo="snippets"))
    if any(t.indice != 0 or t.serie for t in ci.tarjetas) or any(
        t.modo == ModoTarjeta.FIJA for t in ci.tarjetas
    ):
        p.append(_error("cloudinit.tarjetas", "V-B39", motivo="solo_tarjeta_0_sin_ip_fija"))
    sin_secreto = dataclasses.replace(ci, contrasena=None)
    cfg = dataclasses.replace(
        sol.cfg,
        nodo=sol.nodo,
        origen=OrigenSO.CLONAR_PLANTILLA,
        detalle_origen=DetalleClon(plantilla=RefPlantilla(nombre=sol.cfg.nombre)),
        cloudinit=sin_secreto,
        info_cloudinit=_info_de_la_plantilla(sol),
        esperar_ip=False,
        encender=False,
    )
    codigos_ya = {(q.codigo, q.campo) for q in p}
    for q in validar_cloudinit(cfg, inv, caps):
        if q.codigo in ("V-B50", "V-B39") or (q.codigo, q.campo) in codigos_ya:
            continue  # snippets y origen: B2 los trata arriba
        p.append(q)


def validar_solicitud(
    sol: SolicitudPlantillaImagen, inv: Inventario, caps: Capacidades
) -> list[Problema]:
    """Reglas V-B01..V-B16 y los valores de cloud-init de la plantilla (RF-B2.8).

    Un ``ERROR`` impide empezar: no se escribe nada (RF-B2.9). V-B10 (VMID libre) la comprueba
    ``ServicioCreacion`` al crear. Lee la cabecera de un archivo local; no hace peticiones.
    """
    p: list[Problema] = []
    _validar_origen(sol, p)
    _validar_almacenamientos(sol, inv, p)
    _validar_maquina(sol, inv, caps, p)
    if not sol.confirmada:
        p.append(_error("confirmada", "V-B14"))
    _validar_permisos(sol, inv, p)
    _validar_cloudinit_b2(sol, inv, caps, p)
    return p


def hay_errores(problemas: list[Problema]) -> bool:
    """``True`` si algún problema es un error (bloquea «Crear»)."""
    return any(q.severidad == Severidad.ERROR for q in problemas)
