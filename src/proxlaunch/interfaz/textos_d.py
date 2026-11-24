"""Textos de la fase D (0.9) en español llano: versión mínima 8.4, servidores ARM64 (experimental),
traer una máquina de libvirt y hardware del clúster (mapeos PCI/USB y CPU personalizadas).

Todos los textos pasan por ``QCoreApplication.translate`` con el literal a la vista (nunca un
alias): así ``lupdate`` los extrae al catálogo ``.ts``. Este módulo NO importa ``textos`` al
cargarse (``textos`` delega aquí sus códigos nuevos). Nunca se escribe un secreto: solo nombres,
códigos, privilegios y números. Los nombres de mapeo, CPU, nodo o archivo vienen del servidor o
del XML (no confiables): se muestran como texto plano y el Resumen los escapa.

Los marcadores de los parámetros siguen los nombres de ``docs/requisitos/fase-d.md`` (§11); si
falta uno, se muestra un texto neutro en su lugar y nunca se lanza una excepción.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
from proxlaunch.nucleo.arquitectura.perfil import CambioArquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import (
    RE_ID_MAPEO,
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
    TipoMapeo,
)
from proxlaunch.nucleo.lote.modelos import EntradaLibro
from proxlaunch.nucleo.modelos.cpu import es_cpu_personalizada
from proxlaunch.nucleo.modelos.origen import DetalleImportacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, EstadoVia, Via
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso
from proxlaunch.nucleo.validacion import Problema, Severidad

if TYPE_CHECKING:
    from proxlaunch.nucleo.libvirt.correspondencias import EstadoFila

# Usuario de ejemplo cuando no se conoce el real o no es seguro ponerlo en una orden.
_RE_USUARIO_SEGURO = re.compile(r"[A-Za-z0-9._@+-]{1,128}")


class _Seguro(dict[str, str]):
    """Mapa que deja un texto neutro si falta el dato de un marcador (nunca lanza)."""

    def __missing__(self, clave: str) -> str:
        if clave in ("nodo", "nodos", "nodos_x86", "nodos_arm"):
            return QCoreApplication.translate("TextosD", "ese servidor")
        if clave in ("mapeo", "cpu", "plantilla", "disco", "archivo"):
            return QCoreApplication.translate("TextosD", "ese elemento")
        return QCoreApplication.translate("TextosD", "un dato")


def _fmt(texto: str, params: Mapping[str, str] | None = None, **extra: str) -> str:
    datos = _Seguro({**(params or {}), **extra})
    try:
        return texto.format_map(datos)
    except (ValueError, IndexError, KeyError, AttributeError):
        return texto


# =============================================================================================
# Arquitectura y etiqueta «experimental» (RF-D2.12)
# =============================================================================================


def texto_arquitectura(arq: Arquitectura) -> str:
    """El tipo de procesador del servidor en llano."""
    if arq == Arquitectura.AARCH64:
        return QCoreApplication.translate("TextosD", "ARM64")
    if arq == Arquitectura.X86_64:
        return QCoreApplication.translate("TextosD", "x86 (Intel o AMD)")
    return QCoreApplication.translate("TextosD", "no detectada")


def etiqueta_experimental_arm() -> str:
    """Marca que acompaña a todo lo ARM64 (RF-D2.12)."""
    return QCoreApplication.translate("TextosD", "experimental, sin probar en un servidor arm64")


def texto_linea_experimental_arm() -> str:
    """Línea del Resumen y del informe cuando algún servidor es ARM64."""
    return QCoreApplication.translate(
        "TextosD", "ARM64: experimental, sin probar en un servidor arm64"
    )


def texto_nodo_arm(nodo: str) -> str:
    """«pve-arm (ARM64, experimental)»: cómo se muestra un nodo aarch64 (CA-D2.12.1)."""
    return QCoreApplication.translate("TextosD", "{nodo} (ARM64, experimental)").format(nodo=nodo)


def texto_nodo_con_arquitectura(nodo: str, arq: Arquitectura) -> str:
    """El nombre del nodo; con la marca «ARM64, experimental» si es aarch64. Un nodo x86 o de
    arquitectura desconocida sale tal cual (CA-D2.12.2)."""
    return texto_nodo_arm(nodo) if arq == Arquitectura.AARCH64 else nodo


def texto_arquitectura_detectada(arq: Arquitectura, fuente: str, forzada: bool) -> str:
    """Debajo del selector de arquitectura: qué sabe ProxLaunch de este servidor."""
    if forzada:
        return QCoreApplication.translate("TextosD", "Elegida por ti: {arquitectura}.").format(
            arquitectura=texto_arquitectura(arq)
        )
    if arq == Arquitectura.DESCONOCIDA:
        return QCoreApplication.translate(
            "TextosD",
            "No pude saber el tipo de procesador del servidor; lo trato como x86. Si es ARM64, "
            "elígelo aquí.",
        )
    por = {
        "recursos": QCoreApplication.translate("TextosD", "lo dice el clúster"),
        "recursos_ausente": QCoreApplication.translate("TextosD", "lo indica el clúster"),
        "kernel": QCoreApplication.translate("TextosD", "por el sistema del servidor"),
        "kversion": QCoreApplication.translate("TextosD", "por la versión del sistema"),
        "lista_cpu": QCoreApplication.translate("TextosD", "por sus modelos de CPU"),
    }.get(fuente, "")
    if por:
        return QCoreApplication.translate("TextosD", "Detectada: {arquitectura} ({por}).").format(
            arquitectura=texto_arquitectura(arq), por=por
        )
    return QCoreApplication.translate("TextosD", "Detectada: {arquitectura}.").format(
        arquitectura=texto_arquitectura(arq)
    )


def texto_cambio_arquitectura(c: CambioArquitectura) -> str:
    """Un valor x86 cambiado al pasar a ARM64: «tipo de arranque: SeaBIOS → UEFI (OVMF)»."""
    campo = c.campo
    if campo == "firmware":
        nombre = QCoreApplication.translate("TextosD", "tipo de arranque")
    elif campo == "tipo_cpu":
        nombre = QCoreApplication.translate("TextosD", "tipo de CPU")
    elif campo.endswith(".bus"):
        nombre = QCoreApplication.translate("TextosD", "conexión del disco {n}").format(
            n=_numero_de_indice(campo)
        )
    elif campo.endswith(".modelo"):
        nombre = QCoreApplication.translate("TextosD", "tarjeta de red {n}").format(
            n=_numero_de_indice(campo, base=0)
        )
    else:
        nombre = campo
    return QCoreApplication.translate("TextosD", "{campo}: {antes} → {despues}").format(
        campo=nombre, antes=c.antes, despues=c.despues
    )


def _numero_de_indice(campo: str, *, base: int = 1) -> str:
    """El número de ``discos[2].bus`` → «3» (se muestra desde 1; las tarjetas, desde 0)."""
    m = re.search(r"\[(\d+)\]", campo)
    return str(int(m.group(1)) + base) if m else "?"


def texto_cambios_arquitectura(cambios: Sequence[CambioArquitectura]) -> str:
    """V-D08 con la lista de lo que se cambió; vacío si no se cambió nada."""
    if not cambios:
        return ""
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "Cambié estos valores porque el servidor es ARM64: {lista}. Revisa que te sirvan.",
        ),
        lista="; ".join(texto_cambio_arquitectura(c) for c in cambios),
    )


# =============================================================================================
# Estados de la vista previa de libvirt (RF-D1.6)
# =============================================================================================


def texto_estado_fila(e: EstadoFila) -> str:
    """Estado de una fila de la vista previa: «Migrado», «Aproximado», «No se migra», «Bloquea».

    Nunca solo color: la interfaz añade además un símbolo (RNF-D9)."""
    valor = str(getattr(e, "value", e))
    if valor == "migrado":
        return QCoreApplication.translate("TextosD", "Migrado")
    if valor == "aproximado":
        return QCoreApplication.translate("TextosD", "Aproximado")
    if valor == "no_se_migra":
        return QCoreApplication.translate("TextosD", "No se migra")
    if valor == "bloquea":
        return QCoreApplication.translate("TextosD", "Bloquea")
    return valor


# =============================================================================================
# Problemas V-D01 a V-D70
# =============================================================================================


def texto_problema_d(p: Problema) -> str | None:
    """Mensaje de las reglas V-D01..V-D70; ``None`` si el código no es de la fase D."""
    if p.codigo in _SUBTIPOS:
        return _SUBTIPOS[p.codigo](p.params)
    cod = p.codigo.split(".")[0]
    if not cod.startswith("V-D"):
        return None
    return (
        _texto_v_d_version_y_arquitectura(cod, p.params)
        or _texto_v_d_libvirt(cod, p.params)
        or _texto_v_d_hardware(cod, p.params)
        or _texto_v_d_cpu_y_csv(cod, p.params)
    )


def texto_v_d07(prm: Mapping[str, str]) -> str:
    """V-D07: la plantilla es de otra arquitectura que el servidor de destino.

    Acepta ``arq_origen``/``arq_destino`` y, por compatibilidad, los nombres antiguos
    ``arquitectura_plantilla``/``arquitectura_nodo``; si falta alguno, un texto neutro.
    """
    origen = prm.get("arq_origen") or prm.get("arquitectura_plantilla") or ""
    destino = prm.get("arq_destino") or prm.get("arquitectura_nodo") or ""
    neutro = QCoreApplication.translate("TextosD", "otro tipo")
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "La plantilla «{plantilla}» es de un servidor {arq_origen} y no se puede clonar "
            "en {nodo} ({arq_destino}). Elige un servidor del mismo tipo.",
        ),
        prm,
        arq_origen=_arq_llana(origen) or neutro,
        arq_destino=_arq_llana(destino) or neutro,
    )


def _arq_llana(valor: str) -> str:
    """«aarch64» → «ARM64», «x86_64» → «x86»; otro valor tal cual; vacío si no hay."""
    if not valor:
        return ""
    try:
        return texto_arquitectura(Arquitectura(valor))
    except ValueError:
        return valor


def _texto_v_d_version_y_arquitectura(cod: str, prm: Mapping[str, str]) -> str | None:
    if cod == "V-D01":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Este servidor usa Proxmox {version}. ProxLaunch necesita la versión 8.4 o "
                "posterior. Actualiza el servidor (las versiones 8.0 a 8.3 ya no se admiten) y "
                "vuelve a conectar.",
            ),
            prm,
        )
    if cod == "V-D02":
        return QCoreApplication.translate(
            "TextosD",
            "La rama 8 de Proxmox ya no recibe actualizaciones de seguridad desde agosto de "
            "2026. ProxLaunch sigue funcionando con la 8.4, pero conviene actualizar a la "
            "versión 9.",
        )
    if cod == "V-D03":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La versión forzada {version} ya no se admite; uso «Detectar» en su lugar.",
            ),
            prm,
        )
    if cod == "V-D04":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No pude saber si el servidor {nodo} es x86 o ARM (falta el permiso "
                "«Sys.Audit»). Lo trato como x86. Si es ARM64, indícalo en Opciones avanzadas.",
            ),
            prm,
        )
    if cod == "V-D05":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El servidor {nodo} es ARM64. Esto es experimental: ProxLaunch aún no se ha "
                "probado en un servidor ARM64 y la máquina podría no arrancar. Si pasa, mira "
                "la consola en Proxmox.",
            ),
            prm,
        )
    if cod == "V-D06":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Un lote no puede mezclar servidores x86 y ARM64 ({nodos_x86} es x86; "
                "{nodos_arm} es ARM64). Crea un lote para cada tipo.",
            ),
            prm,
        )
    if cod == "V-D07":
        return texto_v_d07(prm)
    if cod == "V-D08":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Cambié estos valores porque el servidor es ARM64: {lista}. Revisa que te sirvan.",
            ),
            prm,
            lista=_lista_v_d08(prm),
        )
    if cod == "V-D09":
        prm = _motivo_v_d09(prm)
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "«{opcion}» no existe en servidores ARM64 ({motivo}). Elige {alternativa}.",
            ),
            prm,
        )
    return None


def _texto_v_d_libvirt(cod: str, prm: Mapping[str, str]) -> str | None:
    """V-D20 a V-D41: el XML de libvirt y lo que se traslada de él."""
    return _texto_v_d_xml(cod, prm) or _texto_v_d_discos(cod, prm) or _texto_v_d_resto_xml(cod, prm)


def _tamano_v_d20(valor: str) -> str:
    """Los bytes del archivo con unidad legible («5,2 MiB»); sin dato, un texto neutro."""
    from proxlaunch.interfaz.textos import texto_tamano_bytes  # evita el import circular

    texto = texto_tamano_bytes(valor)
    return texto if texto != "?" else QCoreApplication.translate("TextosD", "tamaño desconocido")


def _texto_v_d_xml(cod: str, prm: Mapping[str, str]) -> str | None:
    if cod == "V-D20":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El archivo es demasiado grande para ser la descripción de una máquina "
                "({tamano}). El límite es de 4 MiB. ¿Es el archivo correcto?",
            ),
            prm,
            tamano=_tamano_v_d20(prm.get("tamano", "")),
        )
    if cod == "V-D21":
        return QCoreApplication.translate(
            "TextosD",
            "El archivo contiene instrucciones que ProxLaunch no acepta por seguridad (DOCTYPE "
            "o ENTITY). Un XML normal de libvirt no las trae; vuelve a generarlo con «virsh "
            "dumpxml».",
        )
    if cod == "V-D22":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No pude leer el archivo como la descripción de una máquina de libvirt "
                "({motivo}). Genera uno nuevo con «virsh dumpxml --inactive nombre > "
                "maquina.xml».",
            ),
            prm,
        )
    if cod == "V-D23":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Esta máquina no es de tipo KVM ({tipo}); ProxLaunch solo sabe traer máquinas KVM.",
            ),
            prm,
        )
    if cod == "V-D23b":
        return QCoreApplication.translate(
            "TextosD",
            "Esta máquina usaba emulación completa (sin KVM). En Proxmox se creará con KVM y "
            "puede comportarse distinto.",
        )
    if cod == "V-D24":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La máquina es {arq_xml} pero el servidor {nodo} es {arq_nodo}. Elige un "
                "servidor del mismo tipo.",
            ),
            prm,
        )
    return None


def _texto_v_d_discos(cod: str, prm: Mapping[str, str]) -> str | None:
    if cod == "V-D25":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El disco «{disco}» depende de otro archivo (backing file) y Proxmox no lo "
                "admite. Aplánalo antes con: qemu-img convert -O qcow2 origen.qcow2 "
                "plano.qcow2 (sin la opción -B).",
            ),
            prm,
        )
    if cod == "V-D25a":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "libvirt indica que el disco «{disco}» puede depender de otra imagen. "
                "Asegúrate de usar una imagen aplanada.",
            ),
            prm,
        )
    if cod == "V-D25c":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No puedo comprobar si «{archivo}» depende de otra imagen. Si Proxmox la "
                "rechaza, aplánala con: qemu-img convert -O qcow2 origen.qcow2 plano.qcow2.",
            ),
            prm,
        )
    if cod == "V-D26":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "«{archivo}» tiene {n} fotos (snapshots) internas. Solo se copia el estado "
                "actual; las fotos se pierden.",
            ),
            prm,
        )
    if cod == "V-D27":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Elige la imagen del disco «{disco}» (o márcalo «Crear vacío» o «No migrar»). "
                "El disco del sistema no se puede omitir.",
            ),
            prm,
        )
    if cod == "V-D27b":
        return _fmt(
            QCoreApplication.translate(
                "TextosD", "Los discos necesitan {necesario} y en «{storage}» quedan {libre}."
            ),
            prm,
        )
    if cod == "V-D28":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Hay {n} discos {bus} y ese tipo admite como máximo {maximo}. Cambia el tipo de "
                "algunos discos.",
            ),
            prm,
        )
    if cod == "V-D29":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El disco «{disco}» es de tipo {tipo}; ProxLaunch solo sabe traer discos que "
                "sean archivos. Copia su contenido a un archivo y elige ese.",
            ),
            prm,
        )
    return None


def _texto_v_d_resto_xml(cod: str, prm: Mapping[str, str]) -> str | None:
    if cod == "V-D30":
        return QCoreApplication.translate(
            "TextosD",
            "La memoria de arranque (NVRAM) no se traslada. Si la máquina no arranca, entra al "
            "menú UEFI (Esc al arrancar) y añade la entrada de arranque, por ejemplo "
            "\\EFI\\ubuntu\\shimx64.efi.",
        )
    if cod == "V-D31":
        return QCoreApplication.translate(
            "TextosD",
            "El TPM se crea nuevo (v2.0); su contenido no se traslada (BitLocker y claves "
            "guardadas se pierden).",
        )
    if cod == "V-D32":
        return QCoreApplication.translate(
            "TextosD",
            "Apaga la máquina original antes de encender la nueva: dos máquinas con la misma "
            "MAC en la misma red se estorban.",
        )
    if cod == "V-D33":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No puedes conservar la MAC si creas {n} copias (se repetiría). Crea una sola "
                "o usa una MAC nueva.",
            ),
            prm,
        )
    if cod == "V-D33b":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La MAC conservada «{mac}» ya la usa la máquina {vmid} del clúster. Si la "
                "máquina original sigue encendida habrá un conflicto de red.",
            ),
            prm,
        )
    if cod == "V-D34":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La MAC «{mac}» no es válida (usa el formato 52:54:00:ab:cd:ef y que el primer "
                "byte sea par).",
            ),
            prm,
        )
    if cod == "V-D35":
        return _texto_v_d35(prm)
    if cod == "V-D36" and prm.get("bus") and not prm.get("modelo"):
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El tipo de disco «{bus}» no existe en la app; uso «{nuevo}». En Windows "
                "necesitas los drivers VirtIO.",
            ),
            prm,
        )
    if cod == "V-D36":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "«{modelo}» no existe en la app; uso «{nuevo}». En Windows necesitas los "
                "drivers VirtIO.",
            ),
            prm,
        )
    if cod == "V-D37":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La CPU «{origen}» no tiene equivalente exacto en Proxmox; uso «{cpu}». Las "
                "opciones avanzadas de CPU no se trasladan.",
            ),
            prm,
        )
    if cod == "V-D38":
        if not prm.get("pista", "").strip():
            # Sin metadatos libosinfo no hay nada que citar: se evitan las comillas vacías.
            return QCoreApplication.translate(
                "TextosD",
                "No estoy seguro del sistema operativo: el archivo no lo indica. Elige el tipo "
                "correcto en la lista.",
            )
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No estoy seguro del sistema operativo («{pista}»). Elige el tipo correcto en "
                "la lista.",
            ),
            prm,
        )
    if cod == "V-D39":
        return QCoreApplication.translate(
            "TextosD",
            "Este archivo contiene contraseñas (VNC/SPICE). No las he leído; no compartas el "
            "archivo y, si lo subiste a algún sitio, cámbialas.",
        )
    if cod == "V-D40":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La memoria ({memoria}) está fuera de lo que admite ProxLaunch (mínimo 16 MiB, "
                "máximo {maximo}).",
            ),
            prm,
        )
    if cod == "V-D41":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Estos elementos no se trasladan: {lista}. Si necesitas una tarjeta PCI o USB, "
                "usa «Hardware del clúster».",
            ),
            prm,
        )
    return None


def _texto_v_d35(prm: Mapping[str, str]) -> str:
    """V-D35: la tarjeta de red no tiene equivalente directo; ``tarjeta`` va desde 0."""
    motivo = prm.get("motivo", "")
    try:
        tarjeta = str(int(prm.get("tarjeta", "")) + 1)
    except ValueError:
        tarjeta = QCoreApplication.translate("TextosD", "de red")
    if motivo == "nat" or prm.get("origen") == "default" or prm.get("tipo") == "nat_libvirt":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La tarjeta {n} era la red NAT de libvirt, que Proxmox no tiene. Elige un "
                "bridge o una red virtual del servidor.",
            ),
            prm,
            n=tarjeta,
        )
    if motivo == "direct" or prm.get("tipo") == "direct":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La tarjeta {n} usaba una conexión directa a la tarjeta física (macvtap), que "
                "Proxmox no tiene. Elige un bridge del servidor.",
            ),
            prm,
            n=tarjeta,
        )
    if motivo == "openvswitch":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La tarjeta {n} usaba Open vSwitch. Elige un bridge de Open vSwitch del "
                "servidor para que funcione igual.",
            ),
            prm,
            n=tarjeta,
        )
    if not prm.get("origen") or not prm.get("tipo"):
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La tarjeta {n} usaba una red que Proxmox no tiene. Elige un bridge o una red "
                "virtual del servidor.",
            ),
            prm,
            n=tarjeta,
        )
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "La tarjeta {n} usaba la red «{origen}» ({tipo}), que Proxmox no tiene. Elige un "
            "bridge o una red virtual del servidor.",
        ),
        prm,
        n=tarjeta,
    )


def _texto_v_d_hardware(cod: str, prm: Mapping[str, str]) -> str | None:
    """V-D50 a V-D60 y V-D63/V-D64: mapeos PCI y USB."""
    if cod == "V-D50":
        if prm.get("motivo") in ("no_leidos", "no_leido", "error"):
            return _fmt(
                QCoreApplication.translate("TextosD", "No pude leer los mapeos de {tipo}."),
                prm,
                tipo=_tipo(prm),
            )
        return QCoreApplication.translate(
            "TextosD",
            "No hay mapeos que puedas usar (o no pude leerlos). Pide al administrador que cree "
            "un mapeo y te dé el permiso «Mapping.Use» sobre él.",
        )
    if cod == "V-D51":
        return _fmt(
            QCoreApplication.translate(
                "TextosD", "El mapeo «{mapeo}» ya no existe en este servidor. Elige otro."
            ),
            prm,
        )
    if cod == "V-D52":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El mapeo «{mapeo}» no tiene dispositivo en {nodos}. Quita esos servidores del "
                "lote o elige otro mapeo.",
            ),
            prm,
        )
    if cod == "V-D53":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Proxmox dice que el mapeo «{mapeo}» no es válido en {nodo}: {mensaje}. Avisa "
                "al administrador.",
            ),
            prm,
        )
    if cod == "V-D54":
        return QCoreApplication.translate(
            "TextosD",
            "La tarjeta PCIe necesita el tipo de máquina «q35»; lo pongo yo.",
        )
    if cod == "V-D55":
        return QCoreApplication.translate(
            "TextosD",
            "Para usar la tarjeta como gráfica principal, marca también «Es una tarjeta PCIe».",
        )
    if cod == "V-D55b":
        return QCoreApplication.translate(
            "TextosD",
            "Con una gráfica principal propia, la consola de Proxmox no mostrará pantalla "
            "(pongo «sin pantalla virtual»).",
        )
    if cod == "V-D56":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "Solo podrán arrancar {k} de las {n} máquinas de {nodo} a la vez con el mapeo "
                "«{mapeo}»: cada dispositivo lo usa una sola máquina encendida.",
            ),
            prm,
        )
    if cod == "V-D57":
        return QCoreApplication.translate(
            "TextosD",
            "Con hardware asignado la máquina no se podrá migrar encendida a otro servidor.",
        )
    if cod == "V-D58":
        return QCoreApplication.translate(
            "TextosD",
            "La plantilla usa dispositivos asignados directamente; solo el administrador puede "
            "clonarla. Crea una plantilla con mapeos.",
        )
    if cod == "V-D58b":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La plantilla usa mapeos ({lista}); necesitas «Mapping.Use» en ellos y no "
                "podrán arrancar dos copias a la vez con el mismo dispositivo.",
            ),
            prm,
        )
    if cod == "V-D59":
        return _texto_v_d59(prm)
    if cod == "V-D60":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "«Mantener el controlador del servidor» necesita Proxmox 9.1 o posterior "
                "(esta versión es {version}).",
            ),
            prm,
        )
    return None


def _tipo(prm: Mapping[str, str]) -> str:
    """«PCI» o «USB» según el parámetro ``tipo`` de un problema de mapeos."""
    return "USB" if prm.get("tipo", "").lower() == "usb" else "PCI"


def _texto_v_d_cpu_y_csv(cod: str, prm: Mapping[str, str]) -> str | None:
    if cod == "V-D61":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "La CPU personalizada «{cpu}» no existe en {nodos}. Elige otra o pide al "
                "administrador que la cree.",
            ),
            prm,
        )
    if cod == "V-D62":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No pude leer las CPUs personalizadas del servidor; no puedo asegurar que "
                "«{cpu}» exista.",
            ),
            prm,
        )
    if cod == "V-D63":
        return _fmt(
            QCoreApplication.translate("TextosD", "Falta el permiso «{privilegio}» en {ruta}."), prm
        )
    if cod == "V-D64":
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "El mapeo «{mapeo}» está dos veces en la misma máquina; quita una.",
            ),
            prm,
        )
    if cod == "V-D70":
        return _fmt(
            QCoreApplication.translate("TextosD", "Fila {fila}, columna «{columna}»: {motivo}."),
            prm,
            motivo=texto_motivo_v_d70(prm.get("motivo", "")),
        )
    return None


def texto_motivo_v_d70(motivo: str) -> str:
    """Por qué falló una celda de las columnas de mapeos del CSV (V-D70), en llano.

    Un código conocido se traduce; un texto ya redactado (con espacios) se deja tal cual y
    cualquier otro código se resume en «valor no válido»."""
    conocidos = {
        "id_invalido": QCoreApplication.translate(
            "TextosD",
            "el identificador del mapeo no es válido (usa letras, números, «.», «_» y «-», hasta "
            "64 caracteres)",
        ),
        "demasiados_pci": QCoreApplication.translate(
            "TextosD", "una máquina admite como máximo 16 tarjetas PCI"
        ),
        "demasiados_usb": QCoreApplication.translate(
            "TextosD", "una máquina admite como máximo 5 dispositivos USB"
        ),
        "repetido": QCoreApplication.translate("TextosD", "el mismo mapeo aparece dos veces"),
        "pcie_en_arm": QCoreApplication.translate(
            "TextosD", "las tarjetas PCIe no existen en servidores ARM64"
        ),
    }
    if motivo in conocidos:
        return conocidos[motivo]
    if " " in motivo:
        return motivo
    return QCoreApplication.translate("TextosD", "valor no válido")


# =============================================================================================
# Errores y avisos de conexión
# =============================================================================================


def texto_aviso_conexion_d(aviso: Aviso) -> str | None:
    """Aviso de la sesión de la fase D (rama 8 sin soporte); ``None`` si no es de D."""
    if aviso.codigo == CodigoAviso.RAMA_8_SIN_SOPORTE:
        return texto_problema_d(Problema("", "V-D02", Severidad.AVISO, dict(aviso.params)))
    return None


def texto_version_forzada_descartada(version: str) -> str:
    """V-D03: la versión forzada guardada ya no se admite (una vez al abrir la app)."""
    return _fmt(
        QCoreApplication.translate(
            "TextosD", "La versión forzada {version} ya no se admite; uso «Detectar» en su lugar."
        ),
        version=version,
    )


def texto_error_d(err: ErrorProxLaunch) -> str | None:
    """Mensaje de un error de la fase D; ``None`` si el código no es de D.

    Un 403 con ``mapeo`` (hardware del clúster) se explica aquí; los demás 403 siguen la
    traducción general (``textos``).
    """
    c, p = err.codigo, err.params
    if c == CodigoError.XML_NO_VALIDO:
        return _texto_xml_no_valido(p)
    if c == CodigoError.MAPEO_NO_DISPONIBLE:
        return _texto_mapeo_no_disponible(p)
    if c == CodigoError.CPU_PERSONALIZADA_RECHAZADA:
        return _texto_cpu_rechazada(p)
    if c == CodigoError.PERMISO_INSUFICIENTE and (p.get("mapeo") or p.get("ajuste") == "hardware"):
        return _texto_403_mapeo(p)
    if c == CodigoError.VERSION_NO_SOPORTADA:
        return texto_problema_d(Problema("", "V-D01", Severidad.ERROR, dict(p)))
    return None


def _texto_xml_no_valido(p: Mapping[str, str]) -> str:
    """V-D20 a V-D23 según ``motivo``."""
    motivo = p.get("motivo", "")
    if motivo == "tamano":
        return _texto_v_d_xml("V-D20", p) or ""
    if motivo == "doctype":
        return _texto_v_d_xml("V-D21", p) or ""
    if motivo == "no_kvm":
        return _texto_v_d_xml("V-D23", p) or ""
    explicacion = {
        "formato": QCoreApplication.translate("TextosD", "el XML está mal formado"),
        "codificacion": QCoreApplication.translate(
            "TextosD", "no reconozco la codificación del texto"
        ),
        "limites": QCoreApplication.translate(
            "TextosD", "el XML es demasiado grande o está demasiado anidado"
        ),
        "no_dominio": QCoreApplication.translate("TextosD", "no es la descripción de una máquina"),
    }.get(motivo, QCoreApplication.translate("TextosD", "el contenido no es válido"))
    if motivo == "formato" and p.get("linea"):
        explicacion = _fmt(
            QCoreApplication.translate(
                "TextosD", "el XML está mal formado, cerca de la línea {linea}"
            ),
            p,
        )
    return _texto_v_d_xml("V-D22", {**p, "motivo": explicacion}) or ""


def _texto_mapeo_no_disponible(p: Mapping[str, str]) -> str:
    """Un arranque que falló por el hardware del clúster (RF-D3.8): texto llano y, detrás, el
    mensaje original saneado de Proxmox si lo hay."""
    motivo = p.get("motivo", "")
    if motivo in ("no_encontrado", "sin_dispositivo"):
        base = QCoreApplication.translate(
            "TextosD", "El mapeo «{mapeo}» no tiene dispositivo en este servidor ({nodo})."
        )
    elif motivo in ("invalido", "hardware_cambiado"):
        base = QCoreApplication.translate(
            "TextosD",
            "El hardware del servidor cambió y el mapeo «{mapeo}» ya no es válido. Avisa al "
            "administrador.",
        )
    elif motivo == "necesita_q35":
        if p.get("mapeo"):
            base = QCoreApplication.translate(
                "TextosD",
                "La tarjeta PCIe del mapeo «{mapeo}» necesita que la máquina sea de tipo «q35».",
            )
        else:  # sin nombre de mapeo no se deja un «» vacío
            base = QCoreApplication.translate(
                "TextosD", "La tarjeta PCIe necesita que la máquina sea de tipo «q35»."
            )
    elif motivo == "sin_iommu":
        base = QCoreApplication.translate(
            "TextosD",
            "El servidor no tiene IOMMU activado: no puede pasar tarjetas PCI a las máquinas. "
            "El administrador debe activarlo en la BIOS y en el arranque de Proxmox.",
        )
    elif motivo == "usb_en_uso":
        base = QCoreApplication.translate(
            "TextosD",
            "El dispositivo USB del mapeo «{mapeo}» ya lo usa otra máquina encendida.",
        )
    else:
        base = QCoreApplication.translate("TextosD", "No se pudo usar el mapeo «{mapeo}».")
    texto = _fmt(base, p)
    original = p.get("original") or p.get("mensaje") or ""
    if original:
        texto += " " + QCoreApplication.translate("TextosD", "Proxmox dijo: {mensaje}").format(
            mensaje=original
        )
    return texto


def _texto_cpu_rechazada(p: Mapping[str, str]) -> str:
    """403 o 400 de ``cpu=custom-*`` (RF-D3.6, RF-D3.8): según la versión, el privilegio y la
    ruta nombrados son distintos."""
    ruta = p.get("ruta", "")
    if ruta.startswith("/mapping/cpu"):
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No tienes permiso para usar la CPU personalizada «{cpu}» (falta "
                "«Mapping.Use» en {ruta}). Pide al administrador que te lo dé.",
            ),
            p,
            ruta=ruta,
        )
    if ruta or p.get("privilegio"):
        return _fmt(
            QCoreApplication.translate(
                "TextosD",
                "No tienes permiso para usar la CPU personalizada «{cpu}» (falta "
                "«{privilegio}» en {ruta}). Pide al administrador que te lo dé.",
            ),
            p,
            privilegio=p.get("privilegio", "Sys.Audit"),
            ruta=ruta or "/nodes",
        )
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "Proxmox no aceptó la CPU personalizada «{cpu}». Comprueba que existe en el "
            "servidor y que tienes permiso para usarla.",
        ),
        p,
    )


def _texto_403_mapeo(p: Mapping[str, str]) -> str:
    """403 al crear o ajustar con ``hostpciN`` o ``usbN`` (RF-D3.8): nombra mapeo, privilegio y
    ruta, y qué hacer."""
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "No tienes permiso para usar el mapeo «{mapeo}» (falta «{privilegio}» en {ruta}). "
            "Pide al administrador que te lo dé.",
        ),
        p,
        privilegio=p.get("privilegio", "Mapping.Use"),
        ruta=p.get("ruta", "/mapping"),
    )


# =============================================================================================
# Ajuste «hardware» del clon y avisos de la máquina
# =============================================================================================


def texto_ajuste_verbo_d(ajuste: str) -> str:
    """El ajuste de D como acción; ``""`` si no es de D."""
    if ajuste == "hardware":
        return QCoreApplication.translate("TextosD", "asignar el hardware del clúster")
    return ""


def texto_ajuste_sustantivo_d(ajuste: str) -> str:
    """El ajuste de D como cosa pendiente; ``""`` si no es de D."""
    if ajuste == "hardware":
        return QCoreApplication.translate("TextosD", "el hardware del clúster")
    return ""


# =============================================================================================
# Nombres de opciones y motivos de disponibilidad (RF-D0.3)
# =============================================================================================


def texto_nombre_opcion_d(opcion: str) -> str:
    """Nombre llano de una opción de la fase D (valor de ``OpcionD``); ``""`` si no es de D."""
    if opcion == "mapeos":
        return QCoreApplication.translate("TextosD", "Hardware del clúster")
    if opcion == "cpu_personalizada":
        return QCoreApplication.translate("TextosD", "CPU personalizada")
    if opcion == "conservar_mac":
        return QCoreApplication.translate("TextosD", "Conservar la MAC de origen")
    return ""


# =============================================================================================
# Hardware del clúster: textos de la sección (RF-D3.1 a RF-D3.4)
# =============================================================================================


def texto_intro_hardware_cluster() -> str:
    return QCoreApplication.translate(
        "TextosD",
        "Un mapeo es un nombre que el administrador le pone a una tarjeta PCI (por ejemplo, una "
        "gráfica) o a un dispositivo USB (por ejemplo, una llave de licencias) del servidor, "
        "para que puedas dárselo a una máquina sin ser administrador.",
    )


def texto_hardware_sin_leer() -> str:
    return QCoreApplication.translate(
        "TextosD", "Abre esta sección para leer los mapeos del clúster."
    )


def texto_leyendo_mapeos() -> str:
    return QCoreApplication.translate("TextosD", "Leyendo los mapeos del clúster…")


def texto_sin_mapeos_de(tipo: TipoMapeo) -> str:
    """No hay mapeos de este tipo (o no se ve ninguno con tus permisos)."""
    if tipo == TipoMapeo.USB:
        return QCoreApplication.translate(
            "TextosD", "No hay dispositivos USB mapeados que puedas usar."
        )
    return QCoreApplication.translate("TextosD", "No hay tarjetas PCI mapeadas que puedas usar.")


def texto_mapeo_sin_permiso(tipo: TipoMapeo, id_mapeo: str) -> str:
    """CA-D0.3.1: el mapeo sale deshabilitado con el permiso que falta y su ruta."""
    ruta = f"/mapping/{tipo.value}/{id_mapeo}"
    return QCoreApplication.translate("TextosD", "Falta el permiso Mapping.Use en {ruta}").format(
        ruta=ruta
    )


def texto_mapeo_con_detalle(
    id_mapeo: str, descripcion: str, nodos: Sequence[str], *, migrable: bool
) -> str:
    """«gpu-a2 — Tarjeta de la sala 2 (en pve1, pve2)» para la lista de mapeos."""
    partes = [id_mapeo]
    if descripcion:
        partes.append(f"— {descripcion}")
    if nodos:
        partes.append(
            QCoreApplication.translate("TextosD", "(en {nodos})").format(nodos=", ".join(nodos))
        )
    if migrable:
        partes.append(QCoreApplication.translate("TextosD", "[admite migración en vivo]"))
    return " ".join(partes)


def texto_mapeo_no_listado(id_mapeo: str) -> str:
    """Un mapeo cargado de un lote guardado que el servidor ya no lista (V-D51 lo explica)."""
    return QCoreApplication.translate("TextosD", "{mapeo} (no existe)").format(mapeo=id_mapeo)


def texto_pcie_no_en_arm() -> str:
    """Por qué «Es una tarjeta PCIe» y «Es la gráfica principal» no valen en ARM64."""
    return QCoreApplication.translate(
        "TextosD",
        "No disponible en servidores ARM64: allí no existe el tipo de máquina «q35».",
    )


def texto_driver_keep_sin_version() -> str:
    return QCoreApplication.translate("TextosD", "Necesita Proxmox 9.1 o posterior.")


def texto_maximo_dispositivos(tipo: TipoMapeo, maximo: int) -> str:
    if tipo == TipoMapeo.USB:
        return QCoreApplication.translate(
            "TextosD", "Ya tienes {n} dispositivos USB, el máximo de una máquina."
        ).format(n=maximo)
    return QCoreApplication.translate(
        "TextosD", "Ya tienes {n} tarjetas PCI, el máximo de una máquina."
    ).format(n=maximo)


# =============================================================================================
# CPU personalizada (RF-D3.6)
# =============================================================================================


def texto_grupo_cpu_personalizada() -> str:
    return QCoreApplication.translate("TextosD", "Personalizados del clúster")


def texto_cpu_personalizada_item(nombre: str) -> str:
    """El modelo en el desplegable: «custom-gamer»."""
    return nombre


def texto_cpus_ocultas(n: int) -> str:
    """CA-D3.6.2: modelos que no existen en todos los servidores del lote."""
    if n == 1:
        return QCoreApplication.translate(
            "TextosD", "1 modelo no se muestra por no existir en todos los servidores."
        )
    return QCoreApplication.translate(
        "TextosD", "{n} modelos no se muestran por no existir en todos los servidores."
    ).format(n=n)


def texto_cpus_no_leidas() -> str:
    """V-D62 sin nombre de modelo: la lista no se pudo leer."""
    return QCoreApplication.translate(
        "TextosD",
        "No pude leer las CPUs personalizadas del servidor; solo se ofrecen los tipos fijos.",
    )


def texto_cpus_sin_personalizadas() -> str:
    return QCoreApplication.translate(
        "TextosD", "El clúster no tiene CPUs personalizadas que puedas usar."
    )


def texto_cpu_arm_sin_listar() -> str:
    return QCoreApplication.translate(
        "TextosD",
        "En servidores ARM64 de esta versión de Proxmox no se pueden listar las CPUs "
        "personalizadas.",
    )


# =============================================================================================
# Resumen, resumen del lote e informe (RF-D0.1)
# =============================================================================================


def texto_asignacion_pci(a: AsignacionPCI) -> str:
    """«tarjeta PCI “gpu-a2” (pcie, pantalla principal)»."""
    extras: list[str] = []
    if a.pcie:
        extras.append(QCoreApplication.translate("TextosD", "pcie"))
    if a.x_vga:
        extras.append(QCoreApplication.translate("TextosD", "pantalla principal"))
    if not a.rombar:
        extras.append(QCoreApplication.translate("TextosD", "sin ROM"))
    if a.driver_keep:
        extras.append(QCoreApplication.translate("TextosD", "conserva el controlador"))
    base = QCoreApplication.translate("TextosD", "tarjeta PCI «{mapeo}»").format(mapeo=a.mapeo)
    return f"{base} ({', '.join(extras)})" if extras else base


def texto_asignacion_usb(a: AsignacionUSB) -> str:
    """«USB “llave-hasp” (USB 3)»."""
    base = QCoreApplication.translate("TextosD", "USB «{mapeo}»").format(mapeo=a.mapeo)
    if a.usb3:
        usb3 = QCoreApplication.translate("TextosD", "USB 3")
        return f"{base} ({usb3})"
    return base


def texto_hardware_cluster(hw: HardwareCluster | None) -> str:
    """El hardware del clúster en una línea; vacío si no hay ninguno."""
    if hw is None or hw.vacio:
        return ""
    return ", ".join(
        [*(texto_asignacion_pci(a) for a in hw.pci), *(texto_asignacion_usb(a) for a in hw.usb)]
    )


def texto_cpu_personalizada_resumen(tipo_cpu: str) -> str:
    """«personalizada “custom-x”»; vacío si el tipo de CPU no es personalizado."""
    if not es_cpu_personalizada(tipo_cpu):
        return ""
    return QCoreApplication.translate("TextosD", "personalizada «{cpu}»").format(cpu=tipo_cpu)


def texto_mac_conservada_resumen(cfg: ConfiguracionVM) -> str:
    """«net0 (52:54:00:ab:cd:ef)»; vacío si ninguna tarjeta conserva la MAC."""
    return ", ".join(
        f"net{i} ({r.mac_conservada})" for i, r in enumerate(cfg.redes) if r.mac_conservada
    )


def texto_discos_importados_resumen(cfg: ConfiguracionVM) -> str:
    """Los discos de más de uno traídos de libvirt: «disco 2: copia de «x.qcow2»; disco 3: vacío».
    Vacío si no hay discos adicionales con imagen o marca."""
    det = cfg.detalle_origen
    if not isinstance(det, DetalleImportacion) or not det.otras:
        return ""
    partes: list[str] = []
    for o in det.otras:
        if o.imagen is not None:
            nombre = o.imagen.nombre or o.imagen.volid
            partes.append(
                QCoreApplication.translate("TextosD", "disco {n}: copia de «{imagen}»").format(
                    n=o.indice + 1, imagen=nombre
                )
            )
        elif o.crear_vacio:
            partes.append(
                QCoreApplication.translate("TextosD", "disco {n}: vacío").format(n=o.indice + 1)
            )
        else:
            partes.append(
                QCoreApplication.translate("TextosD", "disco {n}: sin imagen elegida").format(
                    n=o.indice + 1
                )
            )
    return "; ".join(partes)


def lineas_opciones_fase_d(
    cfg: ConfiguracionVM,
    arquitectura: Arquitectura | None = None,
    cambios: Sequence[CambioArquitectura] = (),
) -> list[tuple[str, str]]:
    """Líneas «etiqueta, valor» del Resumen para la fase D: solo lo que difiere del valor por
    defecto; sin opciones de D en un nodo x86 no hay ninguna línea (CA-D0.1.2)."""
    lineas: list[tuple[str, str]] = []
    if arquitectura == Arquitectura.AARCH64:
        lineas.append(
            (QCoreApplication.translate("TextosD", "Servidor"), texto_linea_experimental_arm())
        )
        if cambios:
            lineas.append(
                (
                    QCoreApplication.translate("TextosD", "Valores adaptados a ARM64"),
                    "; ".join(texto_cambio_arquitectura(c) for c in cambios),
                )
            )
    hardware = texto_hardware_cluster(cfg.hardware_cluster)
    if hardware:
        lineas.append((QCoreApplication.translate("TextosD", "Hardware del clúster"), hardware))
        if cfg.hardware_cluster is not None and any(a.pcie for a in cfg.hardware_cluster.pci):
            lineas.append((QCoreApplication.translate("TextosD", "Tipo de máquina"), "q35"))
    cpu = texto_cpu_personalizada_resumen(cfg.tipo_cpu)
    if cpu:
        lineas.append((QCoreApplication.translate("TextosD", "CPU"), cpu))
    mac = texto_mac_conservada_resumen(cfg)
    if mac:
        lineas.append((QCoreApplication.translate("TextosD", "MAC conservada"), mac))
    discos = texto_discos_importados_resumen(cfg)
    if discos:
        lineas.append((QCoreApplication.translate("TextosD", "Discos importados"), discos))
    return lineas


def lineas_fase_d_de_entrada(entrada: EntradaLibro, *, arm: bool) -> list[str]:
    """Líneas del informe de una máquina que usa la fase D (vacío si no usa nada)."""
    lineas = [
        f"{etiqueta}: {valor}"
        for etiqueta, valor in lineas_opciones_fase_d(
            entrada.elemento.cfg, Arquitectura.AARCH64 if arm else None
        )
    ]
    return lineas


# =============================================================================================
# «Qué puedo hacer en este servidor» (RF-D5.2)
# =============================================================================================

VIAS_FASE_D: tuple[Via, ...] = (Via.ARQUITECTURA, Via.MAPEOS, Via.CPU_PERSONALIZADA)


def texto_via_d(via: str) -> str:
    """Nombre de una fila de la fase D en «Qué puedo hacer»; ``""`` si no es de D."""
    if via == Via.ARQUITECTURA:
        return QCoreApplication.translate("TextosD", "Saber si un servidor es ARM")
    if via == Via.MAPEOS:
        return QCoreApplication.translate("TextosD", "Usar tarjetas PCI y USB del clúster")
    if via == Via.CPU_PERSONALIZADA:
        return QCoreApplication.translate("TextosD", "Usar modelos de CPU personalizados")
    return ""


def texto_accion_via_d(via: str) -> str:
    """La acción de la fila como frase para «… para {acción}»; ``""`` si no es de D."""
    if via == Via.ARQUITECTURA:
        return QCoreApplication.translate("TextosD", "saber si un servidor es ARM")
    if via == Via.MAPEOS:
        return QCoreApplication.translate("TextosD", "usar tarjetas PCI y USB del clúster")
    if via == Via.CPU_PERSONALIZADA:
        return QCoreApplication.translate("TextosD", "usar modelos de CPU personalizados")
    return ""


def texto_estado_fila_d(estado: EstadoVia) -> str:
    """Estado de una fila de D: «Sí», «No» o «No lo sé» (CA-D5.2.1)."""
    if estado.disponibilidad == Disponibilidad.SI:
        return QCoreApplication.translate("TextosD", "Sí")
    if estado.disponibilidad == Disponibilidad.NO:
        return QCoreApplication.translate("TextosD", "No")
    return QCoreApplication.translate("TextosD", "No lo sé")


def _usuario_seguro(usuario: str) -> str:
    """El usuario tal cual si es seguro dentro de una orden; si no, un marcador."""
    if _RE_USUARIO_SEGURO.fullmatch(usuario):
        return usuario
    return "usuario@pve"


def texto_admin_mapeo(tipo: TipoMapeo, id_mapeo: str, usuario: str) -> str:
    """Qué pedir al administrador para usar un mapeo (RF-D5.2): la orden con ejemplo.

    ``id_mapeo`` y ``usuario`` van dentro de una orden: solo se ponen si son seguros."""
    id_ok = id_mapeo if RE_ID_MAPEO.fullmatch(id_mapeo) else "<mapeo>"
    usuario_ok = _usuario_seguro(usuario)
    ruta = f"/mapping/{tipo.value}/{id_ok}"
    return QCoreApplication.translate(
        "TextosD",
        "Para que {usuario} pueda usar el mapeo «{mapeo}», el administrador ejecuta en un "
        "servidor de Proxmox: pveum acl modify {ruta} --roles PVEMappingUser --users {usuario}. "
        "Para todos los mapeos de este tipo: /mapping/{tipo}; para todos los del clúster: "
        "/mapping.",
    ).format(usuario=usuario_ok, mapeo=id_ok, ruta=ruta, tipo=tipo.value)


def texto_admin_cpu(nombre: str, usuario: str, *, por_mapeo: bool) -> str:
    """Qué pedir al administrador para usar una CPU personalizada (RF-D5.2).

    ``por_mapeo`` es Proxmox 9.2 (permiso sobre ``/mapping/cpu``); antes basta ``Sys.Audit``."""
    usuario_ok = _usuario_seguro(usuario)
    simple = nombre.removeprefix("custom-")
    if not RE_ID_MAPEO.fullmatch(simple):
        simple = "<modelo>"
    if por_mapeo:
        return QCoreApplication.translate(
            "TextosD",
            "Para que {usuario} pueda usar la CPU personalizada «{cpu}», el administrador "
            "ejecuta en un servidor de Proxmox: pveum acl modify /mapping/cpu/{simple} --roles "
            "PVEMappingUser --users {usuario}.",
        ).format(usuario=usuario_ok, cpu=nombre, simple=simple)
    return QCoreApplication.translate(
        "TextosD",
        "Para que {usuario} pueda usar CPUs personalizadas, necesita el permiso «Sys.Audit» "
        "en /nodes (por ejemplo, el rol PVEAuditor en /).",
    ).format(usuario=usuario_ok)


def texto_explicacion_fila_d(via: str, estado: EstadoVia) -> str:
    """Por qué una fila de D no está disponible y qué pedir; ``""`` si lo está."""
    if estado.disponibilidad == Disponibilidad.SI:
        return ""
    if estado.disponibilidad == Disponibilidad.CON_AVISO:
        return QCoreApplication.translate(
            "TextosD",
            "No se pudieron comprobar tus permisos. Puedes intentarlo; si falta alguno, "
            "ProxLaunch te dirá cuál.",
        )
    if via == Via.ARQUITECTURA:
        return QCoreApplication.translate(
            "TextosD",
            "Falta el permiso Sys.Audit en «/nodes»: no puedo saber si un servidor es ARM64 y "
            "lo trato como x86. Si es ARM64, indícalo en Opciones avanzadas.",
        )
    if via == Via.MAPEOS:
        return QCoreApplication.translate(
            "TextosD",
            "Falta el permiso Mapping.Use en los mapeos. Para un mapeo PCI el administrador "
            "ejecuta: pveum acl modify /mapping/pci/<mapeo> --roles PVEMappingUser --users "
            "<usuario>; para uno USB, /mapping/usb/<mapeo>; para todos los del clúster, "
            "/mapping.",
        )
    if via == Via.CPU_PERSONALIZADA:
        if estado.params.get("ruta", "").startswith("/mapping/cpu"):
            return QCoreApplication.translate(
                "TextosD",
                "Falta el permiso Mapping.Use en «/mapping/cpu». Para usar la CPU personalizada "
                "<modelo>, el administrador ejecuta: pveum acl modify /mapping/cpu/<modelo> "
                "--roles PVEMappingUser --users <usuario>.",
            )
        return QCoreApplication.translate(
            "TextosD",
            "Falta el permiso {privilegio} en «{ruta}». Para listar y usar las CPUs "
            "personalizadas el usuario necesita «Sys.Audit» en /nodes (por ejemplo, el rol "
            "PVEAuditor en /) y «VM.Config.CPU» en /vms.",
        ).format(
            privilegio=estado.params.get("privilegio", "Sys.Audit"),
            ruta=estado.params.get("ruta", "/nodes"),
        )
    return ""


def _texto_v_d59(prm: Mapping[str, str]) -> str:
    """Demasiados dispositivos: con ``tipo`` y ``maximo`` dice cuál se pasó (CSV y formulario)."""
    tipo = prm.get("tipo", "").lower()
    if tipo in ("pci", "usb") and prm.get("maximo"):
        if tipo == "usb":
            base = QCoreApplication.translate(
                "TextosD", "Una máquina admite como máximo {maximo} dispositivos USB"
            )
        else:
            base = QCoreApplication.translate(
                "TextosD", "Una máquina admite como máximo {maximo} tarjetas PCI"
            )
        if prm.get("cantidad"):
            base += QCoreApplication.translate("TextosD", " (hay {cantidad}).")
        else:
            base += "."
        return _fmt(base, prm)
    return QCoreApplication.translate(
        "TextosD", "Una máquina admite como máximo 16 tarjetas PCI y 5 dispositivos USB."
    )


def _motivo_v_d09(prm: Mapping[str, str]) -> dict[str, str]:
    """Si ``motivo`` es un código (firmware, cpu, red, pcie), lo cambia por su explicación."""
    explicaciones = {
        "firmware": QCoreApplication.translate("TextosD", "allí solo se arranca con UEFI"),
        "cpu": QCoreApplication.translate("TextosD", "ese procesador es solo de servidores x86"),
        "red": QCoreApplication.translate("TextosD", "esa tarjeta de red no existe en ARM64"),
        "pcie": QCoreApplication.translate("TextosD", "no existe el tipo de máquina «q35»"),
    }
    alternativas = {
        "sin_pcie": QCoreApplication.translate("TextosD", "quitar la opción PCIe del dispositivo"),
    }
    datos = dict(prm)
    motivo = datos.get("motivo", "")
    if motivo in explicaciones:
        datos["motivo"] = explicaciones[motivo]
    alternativa = datos.get("alternativa", "")
    if alternativa in alternativas:
        datos["alternativa"] = alternativas[alternativa]
    return datos


def _texto_v_d24_supuesta(prm: Mapping[str, str]) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "El archivo no dice si la máquina es x86 o ARM; supongo que es x86. Si no lo es, "
            "elige un servidor ARM64 y revisa el resultado.",
        ),
        prm,
    )


def _texto_v_d24_i686(prm: Mapping[str, str]) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "La máquina es de 32 bits (i686). Se crea como x86 de 64 bits, que también ejecuta "
            "sistemas de 32 bits; revisa que arranque.",
        ),
        prm,
    )


def _texto_v_d41_desconocidos(prm: Mapping[str, str]) -> str:
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "El archivo trae elementos que ProxLaunch no conoce y no se trasladan: {lista}. "
            "Revisa que la máquina no los necesite.",
        ),
        prm,
    )


# =============================================================================================
# Asistente «Importar desde libvirt» (RF-D1.1, RF-D1.6, RF-D1.14) y avisos de imágenes
# =============================================================================================

_RE_CONCEPTO = re.compile(r"^(disco_origen|disco|cdrom|red)\[(\d+)\](?:\.([a-z_0-9]+))?$")


def _lista_v_d08(prm: Mapping[str, str]) -> str:
    """Lo que V-D08 cambió, en llano. Con ``cambios`` («campo:antes>despues;…», del plan) dice
    también el valor anterior y el nuevo; con solo ``lista`` (campos separados por coma) nombra los
    campos. Un dato mal formado se muestra tal cual, sin lanzar."""
    cambios: list[CambioArquitectura] = []
    for trozo in prm.get("cambios", "").split(";"):
        campo, _, resto = trozo.partition(":")
        antes, sep, despues = resto.partition(">")
        if campo and sep:
            cambios.append(CambioArquitectura(campo.strip(), antes.strip(), despues.strip()))
    if cambios:
        return "; ".join(texto_cambio_arquitectura(c) for c in cambios)
    lista = [c.strip() for c in prm.get("lista", "").split(",") if c.strip()]
    nombres = {
        "firmware": QCoreApplication.translate("TextosD", "tipo de arranque"),
        "bus": QCoreApplication.translate("TextosD", "conexión del disco"),
        "modelo_red": QCoreApplication.translate("TextosD", "tarjeta de red"),
        "modelo": QCoreApplication.translate("TextosD", "tarjeta de red"),
        "tipo_cpu": QCoreApplication.translate("TextosD", "tipo de CPU"),
    }
    return ", ".join(nombres.get(c, c) for c in lista)


def texto_causa_ajuste_hardware(causa: str) -> str:
    """Por qué falló el ajuste «hardware» tras clonar (I5); vacío si la causa no se conoce."""
    if causa == "sin_indices_libres":
        return QCoreApplication.translate(
            "TextosD",
            "La plantilla ya usa todas las ranuras PCI o USB que admite una máquina; quita "
            "alguna del hardware del clúster o elige otra plantilla.",
        )
    if causa == "mapeo_invalido":
        return QCoreApplication.translate(
            "TextosD",
            "Uno de los mapeos elegidos ya no es válido; revisa el hardware del clúster y "
            "reintenta.",
        )
    return ""


def texto_concepto_fila(campo: str) -> str:
    """Nombre en llano de la clave de una fila de la vista previa de libvirt (columna
    «Concepto»); una clave desconocida se muestra tal cual."""
    t = QCoreApplication.translate
    fijos = {
        "nombre": t("TextosD", "Nombre"),
        "tipo_dominio": t("TextosD", "Tipo de virtualización"),
        "tipo_os": t("TextosD", "Tipo de máquina"),
        "arquitectura": t("TextosD", "Arquitectura"),
        "arquitectura.i686": t("TextosD", "Arquitectura (32 bits)"),
        "memoria": t("TextosD", "Memoria"),
        "memoria.actual": t("TextosD", "Memoria en uso (globo)"),
        "cpu": t("TextosD", "Tipo de CPU"),
        "cpu.topologia": t("TextosD", "Sockets y núcleos"),
        "cpu.hilos": t("TextosD", "Hilos por núcleo"),
        "cpu.actual": t("TextosD", "CPU encendidas"),
        "cpu.banderas": t("TextosD", "Opciones avanzadas de CPU"),
        "tipo_so": t("TextosD", "Sistema operativo"),
        "firmware": t("TextosD", "Arranque"),
        "firmware.claves": t("TextosD", "Claves de arranque seguro"),
        "nvram": t("TextosD", "Memoria de arranque (NVRAM)"),
        "tpm": t("TextosD", "TPM"),
        "agente": t("TextosD", "Agente de la máquina"),
        "controlador": t("TextosD", "Controlador de discos"),
        "dispositivos": t("TextosD", "Dispositivos sin equivalente"),
        "pantalla": t("TextosD", "Pantalla remota"),
        "otros": t("TextosD", "Otros ajustes"),
        "desconocidos": t("TextosD", "Elementos desconocidos"),
        "contrasenas": t("TextosD", "Contraseñas"),
    }
    if campo in fijos:
        return fijos[campo]
    if campo.startswith("discos."):
        return t("TextosD", "Discos {bus}").format(bus=campo.split(".", 1)[1])
    m = _RE_CONCEPTO.match(campo)
    if m is None:
        return campo
    clase, n, sufijo = m.group(1), int(m.group(2)), m.group(3) or ""
    if clase == "cdrom":
        return t("TextosD", "Lector o disquetera {n}").format(n=n + 1)
    if clase == "disco_origen":
        return t("TextosD", "Disco original {n}").format(n=n + 1)
    if clase == "disco":
        base = t("TextosD", "Disco {n}").format(n=n + 1)
        detalle = {
            "bus": t("TextosD", "conexión"),
            "backing": t("TextosD", "depende de otra imagen"),
            "imagen": t("TextosD", "imagen"),
            "opciones": t("TextosD", "opciones"),
        }
    else:
        base = t("TextosD", "Tarjeta de red {n}").format(n=n)
        detalle = {
            "modelo": t("TextosD", "modelo"),
            "vlan": t("TextosD", "VLAN"),
            "mtu": t("TextosD", "MTU"),
            "limite": t("TextosD", "límite de velocidad"),
            "mac": t("TextosD", "MAC"),
            "virtualport": t("TextosD", "Open vSwitch"),
            "extra": t("TextosD", "otras opciones"),
        }
    return f"{base}: {detalle.get(sufijo, sufijo)}" if sufijo else base


def texto_estado_fila_simbolo(e: EstadoFila) -> str:
    """El estado con un símbolo delante: nunca solo color (RNF-D9)."""
    valor = str(getattr(e, "value", e))
    simbolo = {"migrado": "✔", "aproximado": "⚠", "no_se_migra": "–", "bloquea": "✖"}.get(valor, "")
    return f"{simbolo} {texto_estado_fila(e)}".strip()


def texto_comandos_obtener_xml() -> tuple[tuple[str, str], ...]:
    """Las órdenes de RF-D1.14 con su explicación: ``(orden, para qué sirve)``. Son copiables."""
    t = QCoreApplication.translate
    return (
        (
            "virsh dumpxml --inactive nombre-de-la-maquina > maquina.xml",
            t(
                "TextosD",
                "Guarda la descripción de la máquina en un archivo. No uses --security-info: "
                "añadiría las contraseñas.",
            ),
        ),
        (
            "virsh domblklist nombre-de-la-maquina",
            t("TextosD", "Lista los discos de la máquina y los archivos que usan."),
        ),
        (
            "qemu-img info --backing-chain disco.qcow2",
            t(
                "TextosD",
                "Comprueba si un disco depende de otra imagen (backing file). Si sale más de un "
                "archivo, hay que aplanarlo.",
            ),
        ),
        (
            "qemu-img convert -O qcow2 entrada.qcow2 salida.qcow2",
            t("TextosD", "Aplana el disco en un solo archivo, listo para subirlo a Proxmox."),
        ),
    )


def texto_aviso_snapshots() -> str:
    """V-D26 al elegir un archivo local con fotos internas (la cabecera no dice cuántas)."""
    return QCoreApplication.translate(
        "TextosD",
        "Este disco tiene fotos (snapshots) internas. Solo se copia el estado actual; las "
        "fotos se pierden.",
    )


def texto_motivo_backing() -> str:
    """V-D25 al rechazar un archivo local que depende de otro (backing file)."""
    return QCoreApplication.translate(
        "TextosD",
        "Este disco depende de otro archivo (backing file) y Proxmox no lo admite. Aplánalo "
        "antes con: qemu-img convert -O qcow2 origen.qcow2 plano.qcow2 (sin la opción -B).",
    )


def _texto_v_d53_sin_comprobar(prm: Mapping[str, str]) -> str:
    """V-D53.sin_comprobar: no se pudo comprobar el mapeo en ese servidor (P-D11)."""
    return _fmt(
        QCoreApplication.translate(
            "TextosD",
            "No pude comprobar si el mapeo «{mapeo}» es válido en {nodo}. Lo intentaré igualmente "
            "al crear la máquina.",
        ),
        prm,
    )


_SUBTIPOS = {
    "V-D53.sin_comprobar": _texto_v_d53_sin_comprobar,
    "V-D24.supuesta": _texto_v_d24_supuesta,
    "V-D24.i686": _texto_v_d24_i686,
    "V-D41.desconocidos": _texto_v_d41_desconocidos,
}
