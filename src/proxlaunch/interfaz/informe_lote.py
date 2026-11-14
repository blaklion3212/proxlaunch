"""Informe del lote en texto plano: una sola función para copiar y guardar (CA-L19.8).

``texto_informe`` convierte el ``InformeLote`` (datos con códigos) en texto en español con
columnas alineadas. No incluye host, IP ni usuario (CA-L19.3): del UPID se oculta el campo
del usuario. Aquí también viven el guardado en ``.txt`` UTF-8 y el informe parcial que se
escribe al cerrar la aplicación con un lote en curso (RF-L23).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import platformdirs
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFileDialog, QWidget

from proxlaunch.interfaz.modelos_tabla import detalle_entrada
from proxlaunch.interfaz.textos import (
    simbolo_estado_mv,
    texto_error,
    texto_estado_mv,
    texto_estado_rollback,
    texto_problema_lote,
)
from proxlaunch.nucleo.lote.constantes import ETIQUETA_APP, PREFIJO_ETIQUETA_LOTE
from proxlaunch.nucleo.lote.informe import upid_sin_usuario as _upid_sin_usuario
from proxlaunch.nucleo.lote.modelos import (
    EntradaLibro,
    EstadoMV,
    InformeLote,
    ResultadoRollback,
    Severidad,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.persistencia.rutas import NOMBRE_APP
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
        detalle = texto_error(r.error) if r.error is not None else ""
        filas.append((r.nombre, str(r.vmid), r.nodo, texto_estado_rollback(r.estado), detalle))
    cab = (
        QCoreApplication.translate("InformeLote", "Nombre"),
        QCoreApplication.translate("InformeLote", "VMID"),
        QCoreApplication.translate("InformeLote", "Nodo"),
        QCoreApplication.translate("InformeLote", "Resultado"),
        QCoreApplication.translate("InformeLote", "Detalle"),
    )
    lineas.extend(_tabla(cab, filas))
    return lineas


def _fila_maquina(e: EntradaLibro, duraciones: dict[int, float]) -> tuple[str, ...]:
    el = e.elemento
    resultado = f"{simbolo_estado_mv(e.estado)} {texto_estado_mv(e.estado)}"
    return (
        str(el.indice + 1),
        el.nombre,
        str(el.vmid),
        el.nodo,
        resultado,
        texto_duracion(duraciones.get(el.vmid)),
        upid_sin_usuario(e.upid),
    )


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
    lineas.extend(_tabla(cab, [_fila_maquina(e, informe.duraciones_s) for e in informe.entradas]))

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
                        ).format(d=enmascarar(e.error.detalle_tecnico))
                    )

    lineas += [
        "",
        QCoreApplication.translate("InformeLote", "Configuración de las máquinas"),
        "-" * 29,
    ]
    lineas.extend(_lineas_plantilla(informe.plantilla))

    if informe.problemas_plan:
        lineas += [
            "",
            QCoreApplication.translate("InformeLote", "Avisos del plan"),
            "---------------",
        ]
        for p in informe.problemas_plan:
            marca = "✕" if p.severidad == Severidad.ERROR else "⚠"
            lineas.append(f"{marca} {texto_problema_lote(p)}")

    if informe.rollback:
        lineas.extend(_lineas_deshacer(informe.rollback))

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


def carpeta_informes() -> Path:
    """Carpeta de datos del usuario donde se guardan los informes parciales (platformdirs)."""
    return Path(platformdirs.user_data_dir(NOMBRE_APP)) / "informes"


def nombre_archivo_sugerido(informe: InformeLote) -> str:
    prefijo = "simulacion" if informe.es_simulacion else "informe-lote"
    return f"{prefijo}-{informe.id_lote}.txt"


def escribir_informe(ruta: Path, texto: str) -> None:
    """Escribe el informe como texto UTF-8."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


def guardar_con_dialogo(
    parent: QWidget | None, informe: InformeLote, carpeta: Path | None = None
) -> Path | None:
    """Pregunta dónde guardar el informe y lo escribe; ``None`` si el usuario cancela."""
    carpeta = carpeta or carpeta_informes()
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


def guardar_informe_parcial(informe: InformeLote, carpeta: Path | None = None) -> Path | None:
    """Guarda el informe parcial al cerrar con un lote en curso y deja un aviso (CA-L23.3).

    Nunca falla: si no se puede escribir devuelve ``None`` y lo anota en el registro.
    """
    carpeta = carpeta or carpeta_informes()
    try:
        ruta = carpeta / f"parcial-{informe.id_lote}.txt"
        escribir_informe(ruta, texto_informe(informe))
        (carpeta / _ARCHIVO_AVISO).write_text(str(ruta), encoding="utf-8")
    except OSError:
        _log.warning("No se pudo guardar el informe parcial", exc_info=True)
        return None
    return ruta


def tomar_aviso_informe_parcial(carpeta: Path | None = None) -> Path | None:
    """Devuelve la ruta del último informe parcial (una sola vez) y borra la marca."""
    carpeta = carpeta or carpeta_informes()
    marca = carpeta / _ARCHIVO_AVISO
    try:
        if not marca.is_file():
            return None
        ruta = Path(marca.read_text(encoding="utf-8").strip())
        marca.unlink()
    except OSError:
        return None
    return ruta if ruta.is_file() else None
