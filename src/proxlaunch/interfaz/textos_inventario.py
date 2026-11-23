"""Textos del diálogo «Lotes en el servidor» (fase C, C1). Español llano.

Los textos de V-C01..V-C09 siguen ``docs/requisitos/fase-c.md`` §12. Todo lo que viene del
servidor (nombres, etiquetas, bloqueos, nodos) se pone como parámetro y se muestra como texto
plano: nunca se interpreta como marcado.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.inventario.modelos import (
    EstadoIpInventario,
    EstadoNota,
    IpInventario,
    LoteServidor,
    MotivoNoDeshacible,
    MVInventario,
)
from proxlaunch.nucleo.lote.constantes import MAX_LOTE


class _Seguro(dict[str, str]):
    """Mapa que deja un texto neutro si falta un dato del marcador (nunca lanza)."""

    def __missing__(self, clave: str) -> str:
        return QCoreApplication.translate("TextosInventario", "un dato")


def _fmt(texto: str, **datos: str) -> str:
    try:
        return texto.format_map(_Seguro(datos))
    except (ValueError, IndexError, KeyError, AttributeError):
        return texto


# --- Cabecera del diálogo --------------------------------------------------------------------


def titulo_inventario() -> str:
    return QCoreApplication.translate("TextosInventario", "Lotes en el servidor")


def texto_intro_inventario() -> str:
    """Qué es una etiqueta y un lote (RF-C1.1)."""
    return QCoreApplication.translate(
        "TextosInventario",
        "ProxLaunch marca las máquinas que crea con dos etiquetas, «proxlaunch» y "
        "«lote-<código>». Así puede volver a encontrarlas aunque cierres la aplicación. "
        "Elige un lote para ver sus máquinas, exportarlas o deshacerlo.",
    )


def texto_limitacion_inventario() -> str:
    """Lo que el inventario no encuentra (RF-C1.9)."""
    return QCoreApplication.translate(
        "TextosInventario",
        "Las máquinas creadas con «Seguir sin etiquetas» o sin ninguna etiqueta no se pueden "
        "encontrar aquí; bórralas desde Proxmox o desde «Lote > Deshacer» si el lote sigue "
        "abierto en esta sesión.",
    )


def texto_buscar_lote() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Buscar por código de lote o nombre de máquina"
    )


def texto_leyendo_lotes() -> str:
    return QCoreApplication.translate("TextosInventario", "Leyendo los lotes del servidor…")


def texto_leyendo_detalle(codigo: str) -> str:
    return _fmt(
        QCoreApplication.translate("TextosInventario", "Leyendo las máquinas del lote {codigo}…"),
        codigo=codigo,
    )


def texto_lectura_cancelada() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Lectura cancelada. Pulsa «Comprobar» para volver a leer."
    )


def texto_sin_lotes_visibles() -> str:
    """V-C01: el servidor no devuelve ninguna máquina."""
    return QCoreApplication.translate(
        "TextosInventario",
        "No ves ninguna máquina en este servidor. Puede que no haya ninguna o que tu usuario no "
        "tenga el permiso “VM.Audit”. Pide al administrador que te lo dé.",
    )


def texto_sin_lotes_de_proxlaunch(total: int) -> str:
    """Hay máquinas, pero ninguna lleva etiqueta de lote."""
    return QCoreApplication.translate(
        "TextosInventario",
        "Ninguna de las %n máquinas que ves lleva una etiqueta de lote, así que no hay nada que "
        "mostrar aquí.",
        None,
        total,
    )


def texto_sin_resultados_busqueda() -> str:
    return QCoreApplication.translate("TextosInventario", "Ningún lote coincide con la búsqueda.")


def texto_lotes_leidos(n: int) -> str:
    return QCoreApplication.translate("TextosInventario", "%n lote(s) encontrado(s).", None, n)


def texto_elige_un_lote() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Elige un lote de la lista para ver sus máquinas."
    )


# --- Lista de lotes ---------------------------------------------------------------------------


def cabeceras_lotes() -> tuple[str, ...]:
    return (
        QCoreApplication.translate("TextosInventario", "Lote"),
        QCoreApplication.translate("TextosInventario", "Máquinas"),
        QCoreApplication.translate("TextosInventario", "Se pueden deshacer"),
        QCoreApplication.translate("TextosInventario", "Fecha"),
        QCoreApplication.translate("TextosInventario", "Aviso"),
    )


def texto_aviso_lote(lote: LoteServidor, abierto_en_sesion: bool) -> str:
    """Aviso de la fila de un lote: V-C02, sin etiqueta ``proxlaunch`` o abierto en la sesión."""
    avisos: list[str] = []
    if abierto_en_sesion:
        avisos.append(texto_abierto_en_sesion())
    if not lote.valido:
        avisos.append(texto_codigo_invalido(lote.codigo))
    elif not lote.de_proxlaunch:
        avisos.append(
            QCoreApplication.translate("TextosInventario", "No parece creado por ProxLaunch.")
        )
    return " ".join(avisos)


def texto_abierto_en_sesion() -> str:
    return QCoreApplication.translate("TextosInventario", "Abierto en esta sesión.")


def texto_codigo_invalido(codigo: str) -> str:
    """V-C02."""
    return _fmt(
        QCoreApplication.translate(
            "TextosInventario",
            "El código “{codigo}” no es de ProxLaunch (debería ser de 8 caracteres como "
            "“ab12cd34”). No se puede deshacer desde aquí.",
        ),
        codigo=codigo,
    )


def texto_fecha_lote(fecha_texto: str | None) -> str:
    if fecha_texto:
        return fecha_texto
    return QCoreApplication.translate("TextosInventario", "desconocida")


def texto_sin_leer() -> str:
    return QCoreApplication.translate("TextosInventario", "sin leer")


# --- Detalle de un lote -----------------------------------------------------------------------


def cabeceras_detalle() -> tuple[str, ...]:
    return (
        QCoreApplication.translate("TextosInventario", "Nombre"),
        "VMID",
        QCoreApplication.translate("TextosInventario", "Nodo"),
        QCoreApplication.translate("TextosInventario", "Estado"),
        QCoreApplication.translate("TextosInventario", "Bloqueo"),
        QCoreApplication.translate("TextosInventario", "Plantilla"),
        QCoreApplication.translate("TextosInventario", "Protegida"),
        QCoreApplication.translate("TextosInventario", "Nota de origen"),
        QCoreApplication.translate("TextosInventario", "IP"),
        QCoreApplication.translate("TextosInventario", "Se puede deshacer desde aquí"),
    )


def texto_sin_nombre() -> str:
    return QCoreApplication.translate("TextosInventario", "(sin nombre todavía)")


def texto_estado_maquina(estado: str | None) -> str:
    valor = (estado or "").lower()
    if valor == "running":
        return QCoreApplication.translate("TextosInventario", "encendida")
    if valor == "stopped":
        return QCoreApplication.translate("TextosInventario", "apagada")
    return QCoreApplication.translate("TextosInventario", "desconocido (Proxmox aún no lo informa)")


def texto_bloqueo(bloqueo: str | None) -> str:
    """Bloqueo en llano; un valor desconocido se muestra tal cual (texto plano)."""
    if not bloqueo:
        return ""
    conocidos = {
        "backup": QCoreApplication.translate("TextosInventario", "copia de seguridad en curso"),
        "clone": QCoreApplication.translate("TextosInventario", "clonación en curso"),
        "create": QCoreApplication.translate("TextosInventario", "creación en curso"),
        "migrate": QCoreApplication.translate("TextosInventario", "migración en curso"),
        "rollback": QCoreApplication.translate(
            "TextosInventario", "restauración de un snapshot en curso"
        ),
        "snapshot": QCoreApplication.translate("TextosInventario", "snapshot en curso"),
        "snapshot-delete": QCoreApplication.translate(
            "TextosInventario", "borrado de un snapshot en curso"
        ),
        "suspending": QCoreApplication.translate("TextosInventario", "suspensión en curso"),
        "suspended": QCoreApplication.translate("TextosInventario", "suspendida"),
    }
    return conocidos.get(bloqueo, bloqueo)


def texto_si_no(valor: bool | None) -> str:
    if valor is None:
        return QCoreApplication.translate("TextosInventario", "—")
    return (
        QCoreApplication.translate("TextosInventario", "sí")
        if valor
        else QCoreApplication.translate("TextosInventario", "no")
    )


def texto_nota_origen(mv: MVInventario) -> str:
    if mv.nota is None:
        return QCoreApplication.translate("TextosInventario", "sin leer")
    if mv.nota.estado == EstadoNota.COINCIDE:
        return QCoreApplication.translate("TextosInventario", "coincide")
    if mv.nota.estado == EstadoNota.OTRO_LOTE:
        return QCoreApplication.translate("TextosInventario", "de otro lote")
    return QCoreApplication.translate("TextosInventario", "falta")


def texto_motivo(motivo: MotivoNoDeshacible, params: Mapping[str, str], codigo: str) -> str:
    """Texto llano de un motivo de «No se puede deshacer desde aquí» (V-C02..V-C05, V-C08)."""
    if motivo == MotivoNoDeshacible.CODIGO_INVALIDO:
        return texto_codigo_invalido(codigo)
    if motivo == MotivoNoDeshacible.FALTA_ETIQUETA:  # V-C03
        return _fmt(
            QCoreApplication.translate(
                "TextosInventario",
                "Le falta la etiqueta “{falta}”. Sin las dos etiquetas no puedo asegurar que la "
                "creó ProxLaunch, así que no se puede deshacer desde aquí.",
            ),
            falta=params.get("falta", ""),
        )
    if motivo == MotivoNoDeshacible.SIN_NOTA:  # V-C04
        return QCoreApplication.translate(
            "TextosInventario",
            "No tiene la nota “Creada con ProxLaunch” de este lote (se creó con la nota "
            "desactivada o alguien la cambió). Por seguridad no se puede deshacer desde aquí.",
        )
    if motivo == MotivoNoDeshacible.NOTA_OTRO_LOTE:  # V-C04
        return _fmt(
            QCoreApplication.translate("TextosInventario", "Su nota dice que es del lote {otro}."),
            otro=params.get("otro", ""),
        )
    if motivo == MotivoNoDeshacible.PLANTILLA:  # V-C05
        return QCoreApplication.translate(
            "TextosInventario", "Es una plantilla; no se borra desde aquí."
        )
    if motivo == MotivoNoDeshacible.BLOQUEADA:
        return _fmt(
            QCoreApplication.translate(
                "TextosInventario", "Está ocupada ({bloqueo}); espera a que termine."
            ),
            bloqueo=texto_bloqueo(params.get("bloqueo")),
        )
    if motivo == MotivoNoDeshacible.ESTADO_DESCONOCIDO:
        return QCoreApplication.translate(
            "TextosInventario",
            "Proxmox aún no informa su estado; pulsa «Comprobar» en unos segundos.",
        )
    if motivo == MotivoNoDeshacible.CONFIG_ILEGIBLE:
        return QCoreApplication.translate("TextosInventario", "No se pudo leer su configuración.")
    if motivo == MotivoNoDeshacible.NODO_SIN_RESPUESTA:
        return _fmt(
            QCoreApplication.translate("TextosInventario", "El servidor de {nodo} no responde."),
            nodo=params.get("nodo", ""),
        )
    if motivo == MotivoNoDeshacible.YA_NO_EXISTE:
        return QCoreApplication.translate("TextosInventario", "Ya no existe.")
    if motivo == MotivoNoDeshacible.SIN_PERMISO_BORRAR:  # V-C08
        return _fmt(
            QCoreApplication.translate(
                "TextosInventario",
                "Tu usuario no puede borrar máquinas (falta “VM.Allocate” en /vms/{vmid}). Pide "
                "el permiso al administrador.",
            ),
            vmid=params.get("vmid", ""),
        )
    return QCoreApplication.translate(
        "TextosInventario", "Aún no se ha leído; espera un momento o pulsa «Comprobar»."
    )


def texto_motivos_mv(mv: MVInventario, codigo: str) -> str:
    """Todos los motivos de una máquina, o «Sí» si se puede deshacer."""
    if mv.deshacible:
        return QCoreApplication.translate("TextosInventario", "Sí")
    params = {**mv.params, "vmid": str(mv.recurso.vmid)}
    textos = [texto_motivo(m, params, codigo) for m in mv.motivos]
    prefijo = QCoreApplication.translate("TextosInventario", "No se puede deshacer desde aquí:")
    return f"{prefijo} {' '.join(textos)}"


def texto_ninguna_deshacible() -> str:
    """CA-C1.9.2."""
    return QCoreApplication.translate(
        "TextosInventario",
        "Ninguna máquina de este lote se puede deshacer desde aquí; mira el motivo de cada una.",
    )


def texto_ip(ip: IpInventario | None) -> str:
    if ip is None:
        return ""
    if ip.estado == EstadoIpInventario.OK:
        return ip.ip or ""
    nombres = {
        EstadoIpInventario.APAGADA: QCoreApplication.translate("TextosInventario", "apagada"),
        EstadoIpInventario.SIN_AGENTE: QCoreApplication.translate("TextosInventario", "sin agente"),
        EstadoIpInventario.SIN_RESPUESTA: QCoreApplication.translate(
            "TextosInventario", "sin respuesta"
        ),
        EstadoIpInventario.SIN_PERMISO: QCoreApplication.translate(
            "TextosInventario", "sin permiso"
        ),
        EstadoIpInventario.SIN_IP: QCoreApplication.translate("TextosInventario", "sin IP"),
    }
    return nombres.get(ip.estado, "")


# --- Botones y avisos -------------------------------------------------------------------------


def texto_boton(nombre: str) -> str:
    """Textos de los botones del diálogo (clave estable, texto traducible)."""
    textos = {
        "comprobar": QCoreApplication.translate("TextosInventario", "Comprobar"),
        "cancelar_lectura": QCoreApplication.translate("TextosInventario", "Cancelar la lectura"),
        "deshacer": QCoreApplication.translate("TextosInventario", "Deshacer…"),
        "exportar": QCoreApplication.translate("TextosInventario", "Exportar CSV…"),
        "obtener_ip": QCoreApplication.translate("TextosInventario", "Obtener IP"),
        "cerrar": QCoreApplication.translate("TextosInventario", "Cerrar"),
        "cancelar_deshacer": QCoreApplication.translate("TextosInventario", "Detener el borrado"),
        "borrar": QCoreApplication.translate("TextosInventario", "Borrar definitivamente"),
        "cancelar": QCoreApplication.translate("TextosInventario", "Cancelar"),
    }
    return textos.get(nombre, nombre)


def texto_casilla_ip_csv() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Incluir la IP (necesita el agente invitado)"
    )


def texto_casilla_todos_los_lotes() -> str:
    return QCoreApplication.translate("TextosInventario", "Exportar todos los lotes")


def texto_ip_sin_permiso(privilegio: str) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosInventario",
            "Para ver la IP tu usuario necesita el privilegio {privilegio} en las máquinas. "
            "Pídeselo a tu administrador.",
        ),
        privilegio=privilegio,
    )


def texto_ip_sin_version(version: str) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosInventario", "Ver la IP necesita Proxmox {version} o una versión posterior."
        ),
        version=version,
    )


def texto_ip_obtenida(n: int) -> str:
    return QCoreApplication.translate(
        "TextosInventario", "IP consultada en %n máquina(s).", None, n
    )


def texto_csv_guardado(archivo: str) -> str:
    return _fmt(
        QCoreApplication.translate("TextosInventario", "CSV guardado en «{archivo}»."),
        archivo=archivo,
    )


def texto_seleccion_vacia() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Marca al menos una máquina para deshacer."
    )


def texto_demasiadas_marcadas() -> str:
    """V-C09."""
    return QCoreApplication.translate(
        "TextosInventario",
        "Se pueden borrar como máximo %n máquinas a la vez. Desmarca algunas y repite el proceso.",
        None,
        MAX_LOTE,
    )


def texto_lote_abierto_en_sesion() -> str:
    """V-C07 con la indicación de RF-C1.10."""
    return QCoreApplication.translate(
        "TextosInventario",
        "Este lote sigue abierto en esta sesión. Usa Lote > Deshacer para no borrar dos veces.",
    )


def texto_lote_en_deshacer_inventario() -> str:
    """Lo ve «Lote > Deshacer» mientras el inventario borra ese mismo lote (RF-C1.10)."""
    return QCoreApplication.translate(
        "TextosInventario",
        "Este lote se está deshaciendo desde «Lotes en el servidor». Espera a que termine.",
    )


def texto_detalle_incompleto() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Faltan máquinas por leer. Pulsa «Comprobar» para leerlas de nuevo."
    )


def texto_comprobando_para_borrar() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Comprobando las máquinas antes de borrar…"
    )


def texto_borrando() -> str:
    return QCoreApplication.translate("TextosInventario", "Borrando las máquinas marcadas…")


def texto_cierre_con_borrado() -> str:
    return QCoreApplication.translate(
        "TextosInventario",
        "Se están borrando máquinas. Detén el borrado y espera a que termine antes de cerrar "
        "esta ventana.",
    )


# --- Confirmación escribiendo el código (V-C06) ------------------------------------------------


def titulo_confirmar_codigo() -> str:
    return QCoreApplication.translate("TextosInventario", "Confirmar el borrado")


def texto_aviso_borrado(n: int, codigo: str) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosInventario",
            "Se borrarán %n máquinas del lote {codigo} y sus discos. No se puede deshacer.",
            None,
            n,
        ),
        codigo=codigo,
    )


def texto_pedir_codigo(codigo: str) -> str:
    """V-C06."""
    return _fmt(
        QCoreApplication.translate(
            "TextosInventario",
            "Escribe el código del lote ({codigo}) para confirmar. Así evitas borrar por error.",
        ),
        codigo=codigo,
    )


# --- Resultado ---------------------------------------------------------------------------------


def titulo_resultado() -> str:
    return QCoreApplication.translate("TextosInventario", "Resultado del borrado")


def texto_resumen_resultado(
    eliminadas: int, omitidas: int, fallidas: int, ya_no_estaban: int = 0
) -> str:
    partes = [QCoreApplication.translate("TextosInventario", "%n eliminada(s)", None, eliminadas)]
    if ya_no_estaban:
        partes.append(
            QCoreApplication.translate(
                "TextosInventario",
                "%n ya no estaba(n) (no la borró ProxLaunch)",
                None,
                ya_no_estaban,
            )
        )
    if omitidas:
        partes.append(
            QCoreApplication.translate("TextosInventario", "%n sin tocar", None, omitidas)
        )
    if fallidas:
        partes.append(
            QCoreApplication.translate("TextosInventario", "%n con error", None, fallidas)
        )
    return ", ".join(partes) + "."


# --- Entrada de menú ---------------------------------------------------------------------------


def texto_sin_conexion_inventario() -> str:
    return QCoreApplication.translate(
        "TextosInventario", "Conéctate a un servidor para ver sus lotes."
    )


def texto_sin_version_inventario(version: str) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosInventario",
            "Ver los lotes del servidor necesita Proxmox {version} o una versión posterior.",
        ),
        version=version,
    )
