"""Apoyo para las pruebas del núcleo del MVP 3 (perfiles, archivos, lotes guardados, CSV, filas).

Contiene constructores de datos (configuraciones, filas, archivos JSON y CSV) y los centinelas
de privacidad. No contiene aserciones de las pruebas. Las pruebas se derivan de
``docs/requisitos/mvp3.md`` y de las interfaces públicas del Anexo A de
``docs/arquitectura/mvp3.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import (
    OpcionesCsv,
    ResultadoImportacion,
    TablaCsv,
)
from proxlaunch.nucleo.lote.filas import definicion_por_filas
from proxlaunch.nucleo.lote.modelos import DefinicionLote, FilaLote
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO, PerfilMaquina

DATOS_MVP3 = Path(__file__).resolve().parent.parent / "datos" / "mvp3"

# --- Centinelas de privacidad (RNF-M03, INV-M2) -----------------------------------------------
# Valores únicos y reconocibles: ninguna salida de las funciones del MVP 3 puede contenerlos.
CENT_TOKEN = "CENTINELA-SECRETO-token-7f3a91"
CENT_PASSWORD = "CENTINELA-SECRETO-password-2b8c40"
CENT_TICKET = "CENTINELA-SECRETO-ticket-c19d5e"
CENT_CSRF = "CENTINELA-SECRETO-csrf-84e0aa"
CENT_HOST = "pve-centinela-host.invalid"
CENT_IP = "203.0.113.77"
CENT_USUARIO = "centinela-usuario@pve"
CENT_PERFIL_CONEXION = "CENTINELA-PERFIL-CONEXION"
CENTINELAS_SECRETOS = (CENT_TOKEN, CENT_PASSWORD, CENT_TICKET, CENT_CSRF)
CENTINELAS_SITIO = (CENT_HOST, CENT_IP, CENT_USUARIO, CENT_PERFIL_CONEXION)
TODOS_LOS_CENTINELAS = (*CENTINELAS_SECRETOS, *CENTINELAS_SITIO)


def sin_centinelas(texto: str | bytes, centinelas: Iterable[str] = TODOS_LOS_CENTINELAS) -> bool:
    """Verdadero si ninguno de los centinelas aparece en ``texto`` (bytes o cadena)."""
    crudo = texto if isinstance(texto, bytes) else texto.encode("utf-8", "surrogatepass")
    return not any(c.encode() in crudo for c in centinelas)


# --- Configuraciones y filas --------------------------------------------------------------------


def cfg_hw(**cambios: Any) -> ConfiguracionVM:
    """Configuración de hardware válida sobre ``inventario()`` de ``apoyo_lote`` (storage
    ``datos`` y bridge ``vmbr0``); vmid, nombre y nodo vacíos como en un lote leído."""
    base: dict[str, Any] = {
        "vmid": 0,
        "nombre": "",
        "nodo": "",
        "cores": 2,
        "memoria_mib": 2048,
        "discos": [Disco("datos", 32)],
        "redes": [InterfazRed("vmbr0")],
    }
    base.update(cambios)
    return ConfiguracionVM(**base)


def fila(
    nombre: str,
    *,
    vmid: int | None = None,
    nodo: str | None = None,
    origen: int | None = None,
    **cambios: Any,
) -> FilaLote:
    """``FilaLote`` con hardware válido; ``cambios`` sobrescribe campos de la configuración."""
    return FilaLote(nombre, cfg_hw(**cambios), vmid=vmid, nodo=nodo, origen=origen)


def definicion_filas(filas: Sequence[FilaLote], **kw: Any) -> DefinicionLote:
    """Definición por filas con una plantilla informativa cualquiera."""
    plantilla = kw.pop("plantilla_base", cfg_hw(nombre="plantilla-informativa"))
    return definicion_por_filas(filas, plantilla_base=plantilla, **kw)


def filas_heterogeneas() -> list[FilaLote]:
    """Cuatro MVs distintas (CPU, memoria, disco, bus, red y firmware) sin VMID ni nodo fijos."""
    return [
        fila("pg-01", cores=1, memoria_mib=1024, discos=[Disco("datos", 8)]),
        fila("pg-02", cores=4, memoria_mib=8192, discos=[Disco("datos", 64), Disco("datos", 16)]),
        fila("pg-03", cores=2, memoria_mib=4096, discos=[Disco("datos", 32)]),
        fila("pg-04", cores=8, memoria_mib=16384, discos=[Disco("datos", 128)]),
    ]


# --- JSON de perfiles y lotes (de terceros) --------------------------------------------------


def a_json(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def config_perfil_json(**cambios: Any) -> dict[str, Any]:
    """Configuración de perfil válida en JSON (formato §9.1 de los requisitos)."""
    base: dict[str, Any] = {
        "firmware": "seabios",
        "sockets": 1,
        "cores": 2,
        "tipo_cpu": "x86-64-v2-AES",
        "memoria_mib": 2048,
        "ballooning": None,
        "con_disco": True,
        "discos": [
            {
                "tamano_gib": 32,
                "bus": "scsi",
                "formato": "auto",
                "discard": True,
                "ssd": True,
                "iothread": True,
            }
        ],
        "controlador_scsi": "virtio-scsi-single",
        "redes": [{"modelo": "virtio", "vlan": None}],
        "origen": "disco_vacio",
    }
    base.update(cambios)
    return base


def perfil_json(nombre: str = "Perfil de prueba", **extra: Any) -> dict[str, Any]:
    cfg = extra.pop("config", config_perfil_json())
    return {"nombre": nombre, "descripcion": "", "config": cfg, **extra}


def archivo_perfiles(perfiles: Sequence[object] | None = None, /, **raiz: Any) -> bytes:
    """Archivo ``proxlaunch.perfiles`` v1 en bytes. ``raiz`` sobrescribe/añade claves raíz."""
    cuerpo: dict[str, Any] = {
        "formato": "proxlaunch.perfiles",
        "version_formato": VERSION_FORMATO,
        "app_version": "0.0.0-prueba",
        "perfiles": list(perfiles) if perfiles is not None else [perfil_json()],
    }
    cuerpo.update(raiz)
    return a_json(cuerpo)


def config_lote_json(**cambios: Any) -> dict[str, Any]:
    """Configuración de lote (con ``storage`` y ``bridge`` reales) en JSON."""
    base: dict[str, Any] = {
        "firmware": "seabios",
        "sockets": 1,
        "cores": 2,
        "tipo_cpu": "x86-64-v2-AES",
        "memoria_mib": 2048,
        "ballooning": None,
        "con_disco": True,
        "discos": [
            {
                "storage": "datos",
                "tamano_gib": 32,
                "bus": "scsi",
                "formato": "auto",
                "discard": True,
                "ssd": True,
                "iothread": True,
            }
        ],
        "storage_efi": None,
        "controlador_scsi": "virtio-scsi-single",
        "redes": [{"bridge": "vmbr0", "modelo": "virtio", "vlan": None}],
        "origen": "disco_vacio",
    }
    base.update(cambios)
    return base


def lote_homogeneo_json(**cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "config": config_lote_json(),
        "cantidad": 3,
        "patron": {"prefijo": "web", "separador": "-", "inicio": 1, "relleno": 2},
        "destino": {"modo": "automatico", "nodos": [], "algoritmo": "equilibrado"},
        "vmid_inicial": None,
        "etiquetar": True,
    }
    base.update(cambios)
    return base


def archivo_lote(contenido: dict[str, Any] | None = None, /, **raiz: Any) -> bytes:
    """Archivo ``proxlaunch.lote`` v1 homogéneo en bytes (``raiz`` sobrescribe claves raíz)."""
    cuerpo: dict[str, Any] = {
        "formato": "proxlaunch.lote",
        "version_formato": VERSION_FORMATO,
        "app_version": "0.0.0-prueba",
        "nombre": "Lote de prueba",
        "tipo": "homogeneo",
        "homogeneo": contenido if contenido is not None else lote_homogeneo_json(),
    }
    cuerpo.update(raiz)
    return a_json(cuerpo)


def archivo_lote_por_filas(filas: Sequence[object] | None = None, /, **raiz: Any) -> bytes:
    if filas is None:
        filas = [
            {"nombre": "a-01", "vmid": None, "nodo": None, "config": config_lote_json()},
            {"nombre": "a-02", "vmid": 150, "nodo": "pve2", "config": config_lote_json()},
        ]
    cuerpo: dict[str, Any] = {
        "formato": "proxlaunch.lote",
        "version_formato": VERSION_FORMATO,
        "app_version": "0.0.0-prueba",
        "nombre": "Por filas",
        "tipo": "por_filas",
        "por_filas": {
            "filas": list(filas),
            "destino": {"algoritmo": "equilibrado"},
            "vmid_inicial": None,
            "etiquetar": True,
        },
    }
    cuerpo.update(raiz)
    return a_json(cuerpo)


# --- CSV ----------------------------------------------------------------------------------------


def csv_bytes(
    lineas: Sequence[str],
    *,
    codificacion: str = "utf-8",
    fin: str = "\r\n",
    bom: bool = False,
) -> bytes:
    """CSV en bytes a partir de líneas de texto ya separadas."""
    datos = (fin.join(lineas) + fin).encode(codificacion)
    return (b"\xef\xbb\xbf" + datos) if bom else datos


def tabla_csv(lineas: Sequence[str], opciones: OpcionesCsv | None = None, **kw: Any) -> TablaCsv:
    datos = csv_bytes(lineas, **kw)
    return leer_tabla(datos, opciones) if opciones is not None else leer_tabla(datos)


def fabrica_por_id() -> dict[str, PerfilMaquina]:
    return {p.id: p for p in perfiles_fabrica()}


def perfil_base() -> PerfilMaquina:
    return fabrica_por_id()[ID_PREDETERMINADO]


def importar_csv(
    lineas: Sequence[str],
    *,
    inv: Inventario | None = None,
    perfiles: Sequence[PerfilMaquina] | None = None,
    base: PerfilMaquina | None = None,
    nodo_referencia: str | None = None,
    alias_extra: dict[str, str] | None = None,
    **kw: Any,
) -> ResultadoImportacion:
    """Atajo: ``leer_tabla`` + ``interpretar`` con perfiles de fábrica por defecto."""
    tabla = tabla_csv(lineas, **kw)
    disponibles = tuple(perfiles) if perfiles is not None else tuple(perfiles_fabrica())
    return interpretar(
        tabla,
        perfil_base=base or perfil_base(),
        perfiles=disponibles,
        inv=inv,
        nodo_referencia=nodo_referencia,
        alias_extra=alias_extra,
    )


def regla_de(resultado: ResultadoImportacion, fila_n: int) -> list[str]:
    """Reglas (códigos) de los problemas de una fila, por número de fila de Excel."""
    f = next(x for x in resultado.filas if x.numero == fila_n)
    return [p.regla for p in f.problemas]


def todos_los_bytes(carpeta: Path) -> Callable[[], list[tuple[Path, bytes]]]:
    """Función que lista (ruta, contenido) de todos los archivos bajo ``carpeta``."""

    def _leer() -> list[tuple[Path, bytes]]:
        return [(p, p.read_bytes()) for p in sorted(carpeta.rglob("*")) if p.is_file()]

    return _leer
