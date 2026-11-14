"""Lectura y escritura de lotes guardados (RF-G01..G07, formato §9.2).

Dos tipos: ``homogeneo`` (plantilla + cantidad + patrón + destino) y ``por_filas`` (D-22).
Se escribe SOLO la lista blanca. Nunca plan, VMIDs reservados, libro, UPID, ``id_lote``,
política thin, perfil de conexión, host ni usuario (INV-M2, INV-M5): las funciones reciben un
``LoteGuardado``, no un ``Plan``.
"""

from __future__ import annotations

import copy
import logging
from enum import StrEnum
from pathlib import Path

from proxlaunch.nucleo.archivos.constantes import MAX_BYTES_LOTE
from proxlaunch.nucleo.archivos.envoltura import (
    FORMATO_LOTE,
    a_bytes_json,
    abrir_envoltura,
    crear_envoltura,
)
from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.archivos.esquema import LectorEsquema, MotivoCampo, combinar_avisos
from proxlaunch.nucleo.archivos.esquema_config import configuracion_a_dict, leer_configuracion
from proxlaunch.nucleo.archivos.json_estricto import cargar_json_estricto
from proxlaunch.nucleo.archivos.lector import leer_archivo_limitado
from proxlaunch.nucleo.archivos.texto import texto_seguro
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    DefinicionLote,
    Destino,
    FilaLote,
    ModoDestino,
    PatronNombres,
)
from proxlaunch.nucleo.lotes_guardados.modelos import ArchivoLote, LoteGuardado

_log = logging.getLogger("proxlaunch.lotes_guardados.formato")

_TOPE = 10**9  # cordura; los rangos reales los validan V-L01..V-L07 al planificar
MAX_NODOS_ARCHIVO = 256
MAX_LONG_VERSION = 32


class TipoLote(StrEnum):
    HOMOGENEO = "homogeneo"
    POR_FILAS = "por_filas"


def _es_nombre_de_plantilla(d: DefinicionLote) -> bool:
    """N=1 con prefijo vacío en homogéneo: el nombre es el de la plantilla (D-T12)."""
    return not d.es_por_filas and d.cantidad == 1 and d.patron.prefijo == ""


def _fila_a_dict(f: FilaLote) -> dict[str, object]:
    datos: dict[str, object] = {
        "nombre": f.nombre,
        "vmid": f.vmid,
        "nodo": f.nodo,
        "config": configuracion_a_dict(f.cfg),
    }
    if f.origen is not None:
        datos["origen"] = f.origen
    return datos


def lote_a_dict(lote: LoteGuardado) -> dict[str, object]:
    """Contenido del lote SIN la envoltura (sirve también de «huella» para RF-G08)."""
    d = lote.definicion
    datos: dict[str, object] = {"nombre": lote.nombre}
    if lote.version_proxmox is not None:
        datos["version_proxmox"] = lote.version_proxmox
    if d.es_por_filas:
        datos["tipo"] = str(TipoLote.POR_FILAS)
        datos["por_filas"] = {
            "filas": [_fila_a_dict(f) for f in d.filas],
            "destino": {"algoritmo": str(d.destino.algoritmo)},
            "vmid_inicial": d.vmid_inicial,
            "etiquetar": d.etiquetar,
        }
        return datos
    homogeneo: dict[str, object] = {
        "config": configuracion_a_dict(d.plantilla),
        "cantidad": d.cantidad,
        "patron": {
            "prefijo": d.patron.prefijo,
            "separador": d.patron.separador,
            "inicio": d.patron.inicio,
            "relleno": d.patron.relleno,
        },
        "destino": {
            "modo": str(d.destino.modo),
            "nodos": list(d.destino.nodos),
            "algoritmo": str(d.destino.algoritmo),
        },
        "vmid_inicial": d.vmid_inicial,
        "etiquetar": d.etiquetar,
    }
    if _es_nombre_de_plantilla(d):
        homogeneo["nombre_maquina"] = d.plantilla.nombre
    datos["tipo"] = str(TipoLote.HOMOGENEO)
    datos["homogeneo"] = homogeneo
    return datos


def lote_a_bytes(lote: LoteGuardado, *, app_version: str) -> bytes:
    return a_bytes_json(crear_envoltura(FORMATO_LOTE, lote_a_dict(lote), app_version=app_version))


# --- Lectura -----------------------------------------------------------------------------


def _ruta(base: str, clave: str) -> str:
    return f"{base}.{clave}" if base else clave


def _leer_destino(
    lector: LectorEsquema, valor: object, ruta: str, *, completo: bool
) -> Destino | None:
    claves = frozenset({"modo", "nodos", "algoritmo"} if completo else {"algoritmo"})
    obj = lector.objeto(valor, ruta, claves)
    if obj is None:
        return None
    n0 = len(lector.errores)
    algoritmo = lector.enumerado(
        obj, "algoritmo", ruta, Algoritmo, requerido=False, defecto=Algoritmo.EQUILIBRADO
    )
    modo = ModoDestino.AUTOMATICO
    nodos: tuple[str, ...] = ()
    if completo:
        leido = lector.enumerado(
            obj, "modo", ruta, ModoDestino, requerido=False, defecto=ModoDestino.AUTOMATICO
        )
        modo = leido or modo
        crudos = lector.lista(obj, "nodos", ruta, maximo=MAX_NODOS_ARCHIVO, requerido=False)
        lista: list[str] = []
        for i, nodo in enumerate(crudos or []):
            campo = f"{_ruta(ruta, 'nodos')}[{i}]"
            if not isinstance(nodo, str):
                lector.error(campo, MotivoCampo.TIPO)
                continue
            seguro = texto_seguro(nodo, maximo=253)
            if seguro:
                lista.append(seguro)
            else:
                lector.error(campo, MotivoCampo.TEXTO_NO_VALIDO)
        nodos = tuple(lista)
    if len(lector.errores) > n0 or algoritmo is None:
        return None
    return Destino(modo, nodos, algoritmo)


def _leer_comunes(
    lector: LectorEsquema, obj: dict[str, object], ruta: str
) -> tuple[int | None, bool | None]:
    vmid_inicial = lector.entero(
        obj, "vmid_inicial", ruta, minimo=0, maximo=_TOPE, nulo=True, requerido=False
    )
    etiquetar = lector.booleano(obj, "etiquetar", ruta, requerido=False, defecto=True)
    return vmid_inicial, etiquetar


def _leer_homogeneo(lector: LectorEsquema, valor: object, ruta: str) -> DefinicionLote | None:
    obj = lector.objeto(
        valor,
        ruta,
        frozenset(
            {
                "config",
                "cantidad",
                "patron",
                "destino",
                "vmid_inicial",
                "etiquetar",
                "nombre_maquina",
            }
        ),
    )
    if obj is None:
        return None
    n0 = len(lector.errores)
    cfg = leer_configuracion(lector, obj.get("config"), _ruta(ruta, "config"))
    if "config" not in obj:
        lector.error(_ruta(ruta, "config"), MotivoCampo.REQUERIDO)
    cantidad = lector.entero(obj, "cantidad", ruta, minimo=0, maximo=_TOPE)
    patron = _leer_patron(lector, obj.get("patron"), _ruta(ruta, "patron"), "patron" in obj)
    destino = (
        _leer_destino(lector, obj.get("destino"), _ruta(ruta, "destino"), completo=True)
        if "destino" in obj
        else Destino()
    )
    vmid_inicial, etiquetar = _leer_comunes(lector, obj, ruta)
    nombre_maquina = lector.texto(obj, "nombre_maquina", ruta, requerido=False, defecto="")
    if (
        len(lector.errores) > n0
        or cfg is None
        or cantidad is None
        or patron is None
        or destino is None
        or etiquetar is None
        or nombre_maquina is None
    ):
        return None
    if nombre_maquina and cantidad == 1 and patron.prefijo == "":
        cfg.nombre = nombre_maquina  # D-T12: se restaura el nombre de la MV única
    return DefinicionLote(
        plantilla=cfg,
        cantidad=cantidad,
        patron=patron,
        destino=destino,
        vmid_inicial=vmid_inicial,
        etiquetar=etiquetar,
    )


def _leer_patron(
    lector: LectorEsquema, valor: object, ruta: str, presente: bool
) -> PatronNombres | None:
    if not presente:
        lector.error(ruta, MotivoCampo.REQUERIDO)
        return None
    obj = lector.objeto(valor, ruta, frozenset({"prefijo", "separador", "inicio", "relleno"}))
    if obj is None:
        return None
    n0 = len(lector.errores)
    prefijo = lector.texto(obj, "prefijo", ruta, minimo=0, maximo=1024)
    separador = lector.texto(
        obj, "separador", ruta, minimo=0, maximo=16, requerido=False, defecto="-"
    )
    inicio = lector.entero(obj, "inicio", ruta, minimo=0, maximo=_TOPE, requerido=False, defecto=1)
    relleno = lector.entero(
        obj, "relleno", ruta, minimo=0, maximo=_TOPE, requerido=False, defecto=2
    )
    if (
        len(lector.errores) > n0
        or prefijo is None
        or separador is None
        or inicio is None
        or relleno is None
    ):
        return None
    return PatronNombres(prefijo, separador, inicio, relleno)


def _leer_fila(lector: LectorEsquema, valor: object, ruta: str) -> FilaLote | None:
    obj = lector.objeto(valor, ruta, frozenset({"nombre", "vmid", "nodo", "config", "origen"}))
    if obj is None:
        return None
    n0 = len(lector.errores)
    nombre = lector.texto(obj, "nombre", ruta, minimo=0, maximo=1024)
    vmid = lector.entero(obj, "vmid", ruta, minimo=0, maximo=_TOPE, nulo=True, requerido=False)
    nodo = lector.texto(obj, "nodo", ruta, minimo=1, maximo=253, nulo=True, requerido=False)
    origen = lector.entero(obj, "origen", ruta, minimo=0, maximo=_TOPE, nulo=True, requerido=False)
    cfg = leer_configuracion(lector, obj.get("config"), _ruta(ruta, "config"))
    if "config" not in obj:
        lector.error(_ruta(ruta, "config"), MotivoCampo.REQUERIDO)
    if len(lector.errores) > n0 or nombre is None or cfg is None:
        return None
    return FilaLote(nombre=nombre, cfg=cfg, vmid=vmid, nodo=nodo, origen=origen)


def _leer_por_filas(lector: LectorEsquema, valor: object, ruta: str) -> DefinicionLote | None:
    obj = lector.objeto(valor, ruta, frozenset({"filas", "destino", "vmid_inicial", "etiquetar"}))
    if obj is None:
        return None
    crudas = obj.get("filas")
    if isinstance(crudas, list) and len(crudas) > MAX_LOTE:  # antes de interpretar ninguna
        raise ErrorProxLaunch(
            CodigoError.ARCHIVO_DEMASIADAS_FILAS,
            {"tipo": "filas", "filas": str(len(crudas)), "max": str(MAX_LOTE)},
        )
    n0 = len(lector.errores)
    items = lector.lista(obj, "filas", ruta, maximo=MAX_LOTE, minimo=1)
    filas: list[FilaLote] = []
    for i, item in enumerate(items or []):
        fila = _leer_fila(lector, item, f"{_ruta(ruta, 'filas')}[{i}]")
        if fila is not None:
            filas.append(fila)
    destino = (
        _leer_destino(lector, obj.get("destino"), _ruta(ruta, "destino"), completo=False)
        if "destino" in obj
        else Destino()
    )
    vmid_inicial, etiquetar = _leer_comunes(lector, obj, ruta)
    if len(lector.errores) > n0 or not filas or destino is None or etiquetar is None:
        return None
    return DefinicionLote(
        plantilla=copy.deepcopy(filas[0].cfg),  # informativa: ningún cálculo la lee
        cantidad=len(filas),
        patron=PatronNombres(prefijo=""),
        destino=destino,
        vmid_inicial=vmid_inicial,
        etiquetar=etiquetar,
        filas=tuple(filas),
    )


def leer_lote(datos: bytes) -> ArchivoLote:
    """Interpreta un lote de terceros (puro). Carga atómica: o todo válido o excepción.

    E-M02/E-M03 (formato, versión), E-M04 (``ErrorArchivo`` con todos los campos),
    E-M06 (más de ``MAX_LOTE`` filas). Los problemas de reglas (V-05...) NO se comprueban aquí:
    los muestra el formulario tras cargar.
    """
    envoltura = abrir_envoltura(cargar_json_estricto(datos), FORMATO_LOTE)
    lector = LectorEsquema()
    raiz = lector.objeto(
        envoltura.contenido,
        "",
        frozenset({"nombre", "tipo", "version_proxmox", "homogeneo", "por_filas"}),
    )
    definicion: DefinicionLote | None = None
    nombre: str | None = None
    version_proxmox: str | None = None
    if raiz is not None:
        nombre = lector.nombre(raiz, "nombre", "")
        tipo = lector.enumerado(raiz, "tipo", "", TipoLote)
        version_proxmox = lector.texto(
            raiz,
            "version_proxmox",
            "",
            minimo=1,
            maximo=MAX_LONG_VERSION,
            nulo=True,
            requerido=False,
        )
        if tipo == TipoLote.HOMOGENEO:
            if "homogeneo" not in raiz:
                lector.error("homogeneo", MotivoCampo.REQUERIDO)
            else:
                definicion = _leer_homogeneo(lector, raiz["homogeneo"], "homogeneo")
        elif tipo == TipoLote.POR_FILAS:
            if "por_filas" not in raiz:
                lector.error("por_filas", MotivoCampo.REQUERIDO)
            else:
                definicion = _leer_por_filas(lector, raiz["por_filas"], "por_filas")
    lector.fallar_si_errores()
    if definicion is None or nombre is None:  # pragma: no cover - lo cubre fallar_si_errores
        raise ErrorProxLaunch(CodigoError.ARCHIVO_DANADO, {"campo": "", "detalle": "esquema"})
    return ArchivoLote(
        lote=LoteGuardado(nombre, definicion, version_proxmox),
        version_original=envoltura.version_original,
        avisos=combinar_avisos([*envoltura.avisos, *lector.avisos()]),
    )


def leer_archivo_lote(ruta: Path) -> ArchivoLote:
    """Lee un lote del usuario (E/S, solo lectura, ≤ 1 MiB). El archivo nunca se modifica."""
    try:
        archivo = leer_lote(leer_archivo_limitado(ruta, MAX_BYTES_LOTE))
    except ErrorProxLaunch as exc:
        _log.info("Lote rechazado archivo=%s codigo=%s", Path(ruta).name, exc.codigo)
        raise
    _log.info("Lote leído archivo=%s avisos=%d", Path(ruta).name, len(archivo.avisos))
    return archivo


def guardar_lote(ruta: Path, lote: LoteGuardado, *, app_version: str) -> None:
    """Escribe el lote de forma atómica en la ruta elegida por el usuario (E/S)."""
    escribir_atomico(ruta, lote_a_bytes(lote, app_version=app_version))
