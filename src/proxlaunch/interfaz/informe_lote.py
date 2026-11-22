"""Informe del lote en texto plano: una sola función para copiar y guardar (CA-L19.8).

``texto_informe`` convierte el ``InformeLote`` (datos con códigos) en texto en español con
columnas alineadas. No incluye host, IP ni usuario (CA-L19.3): del UPID se oculta el campo
del usuario. Aquí también viven el guardado en ``.txt`` UTF-8 y el informe parcial que se
escribe al cerrar la aplicación con un lote en curso (RF-L23).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFileDialog, QWidget

from proxlaunch.interfaz.modelos_tabla import detalle_entrada
from proxlaunch.interfaz.textos import (
    simbolo_estado_mv,
    texto_ajustes_clon,
    texto_detalle_rollback,
    texto_estado_mv,
    texto_estado_rollback,
    texto_estado_transferencia,
    texto_fuente_origen,
    texto_modo_clon,
    texto_origen_corto,
    texto_problema_lote,
    texto_sin_urls,
    texto_tamano_bytes,
    texto_tipo_so,
    texto_tipo_transferencia,
)
from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv
from proxlaunch.nucleo.archivos.escritura import escribir_atomico
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.informe import upid_sin_usuario as _upid_sin_usuario
from proxlaunch.nucleo.lote.modelos import (
    EntradaLibro,
    EstadoMV,
    InformeLote,
    ResultadoRollback,
    Severidad,
)
from proxlaunch.nucleo.modelos.origen import DetalleClon
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.persistencia.rutas import crear_carpeta_privada
from proxlaunch.nucleo.registro import enmascarar

_log = logging.getLogger("proxlaunch.interfaz.informe")

_ARCHIVO_AVISO = "ultimo-informe-parcial.txt"


# --- Utilidades de formato ----------------------------------------------------------


def texto_rangos(numeros: Iterable[int]) -> str:
    """Agrupa números en rangos: ``[100, 101, 102, 104]`` -> «100–102, 104» (CA-L03.9)."""
    ordenados = sorted(set(numeros))
    partes: list[str] = []
    i = 0
    while i < len(ordenados):
        j = i
        while j + 1 < len(ordenados) and ordenados[j + 1] == ordenados[j] + 1:
            j += 1
        partes.append(str(ordenados[i]) if j == i else f"{ordenados[i]}–{ordenados[j]}")
        i = j + 1
    return ", ".join(partes)


def texto_duracion(segundos: float | None) -> str:
    """«12 s» o «1 min 5 s»; «—» si no terminó."""
    if segundos is None:
        return "—"
    total = max(0, round(segundos))
    if total < 60:
        return QCoreApplication.translate("InformeLote", "{s} s").format(s=total)
    return QCoreApplication.translate("InformeLote", "{m} min {s} s").format(
        m=total // 60, s=total % 60
    )


def upid_sin_usuario(upid: str | None) -> str:
    """UPID sin el campo del usuario; «—» si no hay (la lógica vive en el núcleo)."""
    return _upid_sin_usuario(upid) if upid else "—"


def _tabla(cabecera: tuple[str, ...], filas: list[tuple[str, ...]]) -> list[str]:
    """Columnas alineadas a la izquierda con dos espacios entre ellas."""
    anchos = [len(c) for c in cabecera]
    for f in filas:
        for i, celda in enumerate(f):
            anchos[i] = max(anchos[i], len(celda))
    lineas = ["  ".join(c.ljust(anchos[i]) for i, c in enumerate(cabecera)).rstrip()]
    lineas.append("  ".join("-" * a for a in anchos))
    for f in filas:
        lineas.append("  ".join(c.ljust(anchos[i]) for i, c in enumerate(f)).rstrip())
    return lineas


def _lineas_plantilla(cfg: ConfiguracionVM) -> list[str]:
    lineas = [
        QCoreApplication.translate("InformeLote", "Procesadores: {n} ({s} × {c})").format(
            n=cfg.sockets * cfg.cores, s=cfg.sockets, c=cfg.cores
        ),
        QCoreApplication.translate("InformeLote", "Memoria: {m:g} GiB").format(
            m=cfg.memoria_mib / 1024
        ),
        QCoreApplication.translate("InformeLote", "Arranque: {f}").format(
            f=str(cfg.firmware).upper()
        ),
    ]
    if cfg.con_disco and cfg.discos:
        discos = ", ".join(f"{d.tamano_gib} GiB en {d.storage}" for d in cfg.discos)
        lineas.append(QCoreApplication.translate("InformeLote", "Discos: {d}").format(d=discos))
    else:
        lineas.append(QCoreApplication.translate("InformeLote", "Discos: ninguno"))
    if cfg.redes:
        redes = ", ".join(
            r.bridge + (f" (VLAN {r.vlan})" if r.vlan is not None else "") for r in cfg.redes
        )
        lineas.append(QCoreApplication.translate("InformeLote", "Redes: {r}").format(r=redes))
    else:
        lineas.append(QCoreApplication.translate("InformeLote", "Redes: ninguna"))
    return lineas


def _suma(contadores: dict[str, int], *estados: EstadoMV) -> int:
    return sum(contadores.get(str(e), 0) for e in estados)


def _lineas_deshacer(resultados: tuple[ResultadoRollback, ...]) -> list[str]:
    lineas = ["", QCoreApplication.translate("InformeLote", "Deshacer"), "--------"]
    filas: list[tuple[str, ...]] = []
    for r in resultados:
        detalle = texto_detalle_rollback(r.acciones, r.error)
        filas.append((r.nombre, str(r.vmid), r.nodo, texto_estado_rollback(r.estado), detalle))
    cab = (
        QCoreApplication.translate("InformeLote", "Nombre"),
        QCoreApplication.translate("InformeLote", "VMID"),
        QCoreApplication.translate("InformeLote", "Nodo"),
        QCoreApplication.translate("InformeLote", "Resultado"),
        QCoreApplication.translate("InformeLote", "Detalle"),
    )
    lineas.extend(_tabla(cab, filas))
    lineas.append("")
    lineas.append(texto_archivos_no_se_eliminan())
    return lineas


def texto_archivos_no_se_eliminan() -> str:
    """Deshacer solo elimina máquinas; lo subido y las plantillas no se tocan (CA-O30.3)."""
    return QCoreApplication.translate(
        "InformeLote",
        "Los archivos que subiste (ISOs e imágenes de disco) y las plantillas no se eliminan "
        "al deshacer: Deshacer solo borra las máquinas creadas por el lote.",
    )


def _modo_clon_csv(cfg: ConfiguracionVM) -> str:
    det = cfg.detalle_origen
    if not isinstance(det, DetalleClon):
        return ""
    return str(det.modo_efectivo or det.modo)


def _ajustes_csv(cfg: ConfiguracionVM) -> str:
    """Ajustes del clon como «cores=2;memoria_mib=4096» (identificadores estables, sin traducir)."""
    det = cfg.detalle_origen
    if not isinstance(det, DetalleClon):
        return ""
    a = det.ajustes
    pares = (
        ("sockets", a.sockets),
        ("cores", a.cores),
        ("tipo_cpu", a.tipo_cpu),
        ("memoria_mib", a.memoria_mib),
        ("disco_gib", a.disco_gib),
    )
    return ";".join(f"{k}={v}" for k, v in pares if v is not None)


@dataclass(frozen=True)
class DatosMaquina:
    """Una máquina del informe. Es la ÚNICA fuente de las filas del informe de texto y del CSV
    (CA-C14.3): así los dos no pueden contradecirse. No lleva host, IP ni usuario."""

    numero: int
    nombre: str
    vmid: int
    nodo: str
    estado: EstadoMV
    codigo_error: str
    duracion_s: float | None
    upid: str | None
    # MVP 4 (CA-O30.5): de dónde sale el sistema operativo; sin URL ni rutas locales (INV-O6).
    origen: OrigenSO = OrigenSO.DISCO_VACIO
    fuente: str = ""
    modo: str = ""  # solo clones: identificador estable del modo efectivo
    ajustes: str = ""  # solo clones: «cores=2;memoria_mib=4096»

    @property
    def resultado(self) -> str:
        return f"{simbolo_estado_mv(self.estado)} {texto_estado_mv(self.estado)}"


def datos_maquinas(informe: InformeLote) -> list[DatosMaquina]:
    """Los datos de cada máquina del informe, en el orden del plan."""
    return [
        DatosMaquina(
            numero=e.elemento.indice + 1,
            nombre=e.elemento.nombre,
            vmid=e.elemento.vmid,
            nodo=e.elemento.nodo,
            estado=e.estado,
            codigo_error=str(e.error.codigo) if e.error is not None else "",
            duracion_s=informe.duraciones_s.get(e.elemento.vmid),
            upid=e.upid,
            origen=e.elemento.cfg.origen,
            fuente=texto_fuente_origen(e.elemento.cfg),
            modo=_modo_clon_csv(e.elemento.cfg),
            ajustes=_ajustes_csv(e.elemento.cfg),
        )
        for e in informe.entradas
    ]


def _fila_maquina(d: DatosMaquina) -> tuple[str, ...]:
    return (
        str(d.numero),
        d.nombre,
        str(d.vmid),
        d.nodo,
        d.resultado,
        texto_duracion(d.duracion_s),
        upid_sin_usuario(d.upid),
    )


def _lineas_por_maquina(informe: InformeLote) -> list[str]:
    """Configuración de cada máquina de un lote por filas (CA-C08.8)."""
    cab = (
        QCoreApplication.translate("InformeLote", "N.º"),
        QCoreApplication.translate("InformeLote", "Nombre"),
        QCoreApplication.translate("InformeLote", "Procesadores"),
        QCoreApplication.translate("InformeLote", "Memoria (GiB)"),
        QCoreApplication.translate("InformeLote", "Discos"),
        QCoreApplication.translate("InformeLote", "Redes"),
    )
    filas: list[tuple[str, ...]] = []
    ninguno = QCoreApplication.translate("InformeLote", "ninguno")
    for e in informe.entradas:
        cfg = e.elemento.cfg
        discos = (
            ", ".join(f"{d.tamano_gib} GiB en {d.storage}" for d in cfg.discos)
            if cfg.con_disco and cfg.discos
            else ninguno
        )
        redes = (
            ", ".join(
                r.bridge + (f" (VLAN {r.vlan})" if r.vlan is not None else "") for r in cfg.redes
            )
            if cfg.redes
            else ninguno
        )
        filas.append(
            (
                str(e.elemento.indice + 1),
                e.elemento.nombre,
                str(cfg.sockets * cfg.cores),
                f"{cfg.memoria_mib / 1024:g}",
                discos,
                redes,
            )
        )
    return _tabla(cab, filas)


# Encabezado del informe CSV: identificadores estables, no se traducen (RNF-M04).
ENCABEZADO_INFORME_CSV = (
    "numero",
    "nombre",
    "vmid",
    "nodo",
    "desenlace",
    "resultado",
    "codigo_error",
    "duracion_s",
    # MVP 4 (CA-O30.5): origen del sistema, fuente (nombre, nunca URL ni ruta), modo y ajustes.
    "origen",
    "fuente",
    "modo_clon",
    "ajustes",
)


def filas_informe_csv(informe: InformeLote) -> list[list[str | int]]:
    """Filas del informe CSV: nombre, VMID, nodo, desenlace, código de error, duración y origen.

    Nunca el UPID, ni host, IP, usuario, URL o ruta local (CA-C14, CA-O30.6).
    """
    filas: list[list[str | int]] = []
    for d in datos_maquinas(informe):
        duracion: str | int = "" if d.duracion_s is None else max(0, round(d.duracion_s))
        filas.append(
            [
                d.numero,
                d.nombre,
                d.vmid,
                d.nodo,
                str(d.estado),
                texto_estado_mv(d.estado),
                d.codigo_error,
                duracion,
                str(d.origen),
                d.fuente,
                d.modo,
                d.ajustes,
            ]
        )
    return filas


def guardar_informe_csv(ruta: Path, informe: InformeLote) -> None:
    """Escribe el informe como CSV por el escritor único y seguro (RF-C14, RF-C11).

    Lanza ``ErrorProxLaunch`` ``ARCHIVO_NO_GUARDABLE`` (E-M08) si no se puede escribir.
    """
    escribir_csv(ruta, ENCABEZADO_INFORME_CSV, filas_informe_csv(informe))


def _lineas_origen(entradas: tuple[EntradaLibro, ...]) -> list[str]:
    """Origen del sistema, fuente, modo y ajustes de cada máquina (CA-O30.5).

    Vacío si todas las máquinas son discos vacíos (los informes de antes no cambian).
    """
    if all(e.elemento.cfg.origen == OrigenSO.DISCO_VACIO for e in entradas):
        return []
    cab = (
        QCoreApplication.translate("InformeLote", "N.º"),
        QCoreApplication.translate("InformeLote", "Nombre"),
        QCoreApplication.translate("InformeLote", "Origen"),
        QCoreApplication.translate("InformeLote", "Fuente"),
        QCoreApplication.translate("InformeLote", "Sistema"),
        QCoreApplication.translate("InformeLote", "Modo"),
        QCoreApplication.translate("InformeLote", "Ajustes"),
    )
    filas: list[tuple[str, ...]] = []
    for e in entradas:
        cfg = e.elemento.cfg
        det = cfg.detalle_origen
        es_clon = isinstance(det, DetalleClon)
        filas.append(
            (
                str(e.elemento.indice + 1),
                e.elemento.nombre,
                texto_origen_corto(cfg.origen),
                texto_fuente_origen(cfg) or "—",
                texto_tipo_so(cfg.tipo_so) if cfg.tipo_so is not None and not es_clon else "—",
                texto_modo_clon(det.modo_efectivo or det.modo, avanzado=True)
                if isinstance(det, DetalleClon)
                else "—",
                texto_ajustes_clon(cfg) if es_clon else "—",
            )
        )
    return [
        "",
        QCoreApplication.translate("InformeLote", "Sistema operativo de las máquinas"),
        "-" * 34,
        *_tabla(cab, filas),
    ]


def _lineas_transferencias(informe: InformeLote) -> list[str]:
    """Archivos subidos o descargados en la sesión (RF-O25); sin URL, ruta local ni huella."""
    if not informe.transferencias:
        return []
    cab = (
        QCoreApplication.translate("InformeLote", "Tipo"),
        QCoreApplication.translate("InformeLote", "Archivo"),
        QCoreApplication.translate("InformeLote", "Almacenamiento"),
        QCoreApplication.translate("InformeLote", "Nodo"),
        QCoreApplication.translate("InformeLote", "Tamaño"),
        QCoreApplication.translate("InformeLote", "Hora"),
        QCoreApplication.translate("InformeLote", "Estado"),
        QCoreApplication.translate("InformeLote", "Identificador"),
    )
    filas: list[tuple[str, ...]] = [
        (
            texto_tipo_transferencia(t.tipo),
            t.nombre_archivo,
            t.storage,
            t.nodo,
            texto_tamano_bytes(t.tamano_bytes) if t.tamano_bytes is not None else "—",
            t.hora_local,
            texto_estado_transferencia(t.estado),
            t.volid or "—",
        )
        for t in informe.transferencias
    ]
    return [
        "",
        QCoreApplication.translate("InformeLote", "Archivos subidos o descargados en esta sesión"),
        "-" * 44,
        *_tabla(cab, filas),
        texto_archivos_no_se_eliminan(),
        QCoreApplication.translate(
            "InformeLote",
            "Si ya no los necesitas, pídele a un administrador que los borre desde Proxmox.",
        ),
    ]


def texto_permisos_no_verificados() -> str:
    """CA-L09.4: no se pudieron leer los permisos; el lote no se bloqueó por ello."""
    return QCoreApplication.translate(
        "InformeLote",
        "Permisos no verificados: no se pudieron leer los permisos del usuario, así que "
        "Proxmox pudo rechazar alguna máquina.",
    )


def texto_informe(informe: InformeLote) -> str:
    """Informe completo en texto plano (misma función para copiar y para guardar)."""
    m = informe.metadatos
    c = informe.contadores
    lineas: list[str] = []
    titulo = (
        QCoreApplication.translate("InformeLote", "ProxLaunch — Simulación del lote {id}")
        if informe.es_simulacion
        else QCoreApplication.translate("InformeLote", "ProxLaunch — Informe del lote {id}")
    ).format(id=informe.id_lote)
    lineas += [titulo, "=" * len(titulo)]
    if informe.es_simulacion:
        lineas.append(QCoreApplication.translate("InformeLote", "SIMULACIÓN — no se creó nada."))
    lineas.append(
        QCoreApplication.translate("InformeLote", "Fecha: {f}").format(f=m.fecha_hora_local)
    )
    lineas.append(
        QCoreApplication.translate("InformeLote", "Perfil: {p}").format(p=m.nombre_perfil)
    )
    lineas.append(
        QCoreApplication.translate("InformeLote", "Versión de Proxmox: {v}").format(
            v=m.version_proxmox
        )
    )
    if m.es_cluster:
        lineas.append(
            QCoreApplication.translate("InformeLote", "Servidor: clúster «{n}»").format(
                n=m.nombre_cluster or "—"
            )
        )
    else:
        lineas.append(QCoreApplication.translate("InformeLote", "Servidor: individual"))
    if not informe.permisos_verificados:
        lineas.append(texto_permisos_no_verificados())

    lineas += ["", QCoreApplication.translate("InformeLote", "Resumen"), "-------"]
    lineas.append(
        QCoreApplication.translate("InformeLote", "Pedidas: {n}").format(n=informe.pedidas)
    )
    lineas.append(
        QCoreApplication.translate("InformeLote", "Creadas: {n}").format(n=_suma(c, EstadoMV.OK))
    )
    lineas.append(
        QCoreApplication.translate("InformeLote", "Creadas con avisos: {n}").format(
            n=_suma(c, EstadoMV.CON_AVISOS)
        )
    )
    lineas.append(
        QCoreApplication.translate("InformeLote", "Con error: {n}").format(
            n=_suma(c, EstadoMV.ERROR, EstadoMV.PARCIAL)
        )
    )
    lineas.append(
        QCoreApplication.translate(
            "InformeLote", "Sin confirmar (no sabemos si se crearon): {n}"
        ).format(
            n=_suma(
                c,
                EstadoMV.TIEMPO_AGOTADO,
                EstadoMV.CONEXION_PERDIDA,
                EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD,
            )
        )
    )
    lineas.append(
        QCoreApplication.translate("InformeLote", "No enviadas: {n}").format(
            n=_suma(c, EstadoMV.NO_ENVIADA, EstadoMV.NO_CREADA_SEGURA)
        )
    )

    lineas += ["", QCoreApplication.translate("InformeLote", "Máquinas"), "--------"]
    cab = (
        QCoreApplication.translate("InformeLote", "N.º"),
        QCoreApplication.translate("InformeLote", "Nombre"),
        QCoreApplication.translate("InformeLote", "VMID"),
        QCoreApplication.translate("InformeLote", "Nodo"),
        QCoreApplication.translate("InformeLote", "Resultado"),
        QCoreApplication.translate("InformeLote", "Duración"),
        QCoreApplication.translate("InformeLote", "UPID"),
    )
    lineas.extend(_tabla(cab, [_fila_maquina(d) for d in datos_maquinas(informe)]))

    con_detalle = [e for e in informe.entradas if detalle_entrada(e)]
    if con_detalle:
        lineas += [
            "",
            QCoreApplication.translate("InformeLote", "Detalle de las máquinas con problemas"),
            "-" * 38,
        ]
        for e in con_detalle:
            el = e.elemento
            lineas.append(f"• {el.nombre} ({el.vmid}): {detalle_entrada(e)}")
            if e.error is not None:
                lineas.append(
                    QCoreApplication.translate("InformeLote", "    Código: {c}").format(
                        c=str(e.error.codigo)
                    )
                )
                if e.error.detalle_tecnico:
                    lineas.append(
                        QCoreApplication.translate(
                            "InformeLote", "    Detalles técnicos: {d}"
                        ).format(d=texto_sin_urls(enmascarar(e.error.detalle_tecnico)))
                    )

    lineas += [
        "",
        QCoreApplication.translate("InformeLote", "Configuración de las máquinas"),
        "-" * 29,
    ]
    if informe.por_filas:
        lineas.extend(_lineas_por_maquina(informe))
    else:
        lineas.extend(_lineas_plantilla(informe.plantilla))

    lineas.extend(_lineas_origen(informe.entradas))

    if informe.problemas_plan:
        lineas += [
            "",
            QCoreApplication.translate("InformeLote", "Avisos del plan"),
            "---------------",
        ]
        for p in informe.problemas_plan:
            marca = "✕" if p.severidad == Severidad.ERROR else "⚠"
            fila = str(p.indice + 1) if informe.por_filas and p.indice is not None else None
            lineas.append(f"{marca} {texto_problema_lote(p, fila=fila)}")

    if informe.rollback:
        lineas.extend(_lineas_deshacer(informe.rollback))

    lineas.extend(_lineas_transferencias(informe))

    if not informe.es_simulacion:
        vmids = [e.elemento.vmid for e in informe.entradas]
        lineas += [
            "",
            QCoreApplication.translate(
                "InformeLote",
                "Cómo encontrar estas máquinas en Proxmox: llevan las etiquetas «{e1}» y "
                "«{e2}{id}» (si el lote las activó) y sus números son {rangos}.",
            ).format(
                e1=ETIQUETA_APP,
                e2=PREFIJO_ETIQUETA_LOTE,
                id=informe.id_lote,
                rangos=texto_rangos(vmids),
            ),
        ]
    return "\n".join(lineas) + "\n"


# --- Guardado -----------------------------------------------------------------------


def nombre_archivo_sugerido(informe: InformeLote) -> str:
    prefijo = "simulacion" if informe.es_simulacion else "informe-lote"
    return f"{prefijo}-{informe.id_lote}.txt"


def _escribir_privado(ruta: Path, texto: str) -> None:
    """Escribe el texto UTF-8 de forma atómica y con permisos 0o600 (en Windows se heredan).

    Lanza ``ErrorProxLaunch`` (E-M08) si no se puede escribir; el destino anterior queda intacto.
    """
    escribir_atomico(ruta, texto.encode("utf-8"))


def escribir_informe(ruta: Path, texto: str) -> None:
    """Escribe el informe como texto UTF-8 con permisos 0o600."""
    carpeta = ruta.parent
    if not carpeta.exists():
        # Solo se crea (privada) la carpeta que falta; una carpeta ya existente que eligió el
        # usuario no se toca.
        crear_carpeta_privada(carpeta)
    _escribir_privado(ruta, texto)


def guardar_con_dialogo(parent: QWidget | None, informe: InformeLote, carpeta: Path) -> Path | None:
    """Pregunta dónde guardar el informe y lo escribe; ``None`` si el usuario cancela."""
    sugerido = str(carpeta / nombre_archivo_sugerido(informe))
    ruta, _filtro = QFileDialog.getSaveFileName(
        parent,
        QCoreApplication.translate("InformeLote", "Guardar informe"),
        sugerido,
        QCoreApplication.translate("InformeLote", "Texto (*.txt)"),
    )
    if not ruta:
        return None
    destino = Path(ruta)
    escribir_informe(destino, texto_informe(informe))
    return destino


def nombre_archivo_csv_sugerido(informe: InformeLote) -> str:
    prefijo = "simulacion" if informe.es_simulacion else "informe-lote"
    return f"{prefijo}-{informe.id_lote}.csv"


def guardar_informe_parcial(informe: InformeLote, carpeta: Path) -> Path | None:
    """Guarda el informe parcial al cerrar con un lote en curso y deja un aviso (CA-L23.3).

    Nunca falla: si no se puede escribir devuelve ``None`` y lo anota en el registro.
    """
    try:
        # Carpeta privada (0o700) y archivos 0o600: el informe puede revelar nombres y nodos.
        crear_carpeta_privada(carpeta)
        ruta = carpeta / f"parcial-{informe.id_lote}.txt"
        _escribir_privado(ruta, texto_informe(informe))
        _escribir_privado(carpeta / _ARCHIVO_AVISO, str(ruta))
    except (OSError, ErrorProxLaunch):
        _log.warning("No se pudo guardar el informe parcial", exc_info=True)
        return None
    return ruta


def tomar_aviso_informe_parcial(carpeta: Path) -> Path | None:
    """Devuelve la ruta del último informe parcial (una sola vez) y borra la marca."""
    marca = carpeta / _ARCHIVO_AVISO
    try:
        if not marca.is_file():
            return None
        ruta = Path(marca.read_text(encoding="utf-8").strip())
        marca.unlink()
    except OSError:
        return None
    return ruta if ruta.is_file() else None
