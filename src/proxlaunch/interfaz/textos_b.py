"""Textos de la fase B (0.7) en español llano: asistente «Crear plantilla desde imagen cloud» (B2)
y espera de la IP de cada máquina (B3).

Todos los textos pasan por ``QCoreApplication.translate`` con el literal a la vista (nunca un
alias): así ``lupdate`` los extrae al catálogo ``.ts`` y la interfaz queda lista para traducir
(CA-B8.1.2). Este módulo NO importa ``textos`` al cargarse (``textos`` puede delegar aquí sus
códigos nuevos): ``texto_problema_completo`` y ``texto_estado_control_b2`` lo hacen perezosamente.

Nunca se escribe una contraseña, una clave ni el valor de un parámetro secreto: los mensajes solo
nombran códigos, privilegios, nombres de archivo y números.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.agente.modelos import EstadoIp, ResultadoIp
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import ESTADOS_EN_CURSO, EntradaLibro, EstadoMV
from proxlaunch.nucleo.plantilla_imagen.disponibilidad import ControlB2, EstadoControlB2
from proxlaunch.nucleo.plantilla_imagen.modelos import EstadoPaso, PasoB2
from proxlaunch.nucleo.validacion import Problema, Severidad

if TYPE_CHECKING:
    from proxlaunch.nucleo.lote.informe import ResumenIps


class _Seguro(dict[str, str]):
    """Mapa que deja intacto un marcador ``{x}`` si falta el dato (nunca lanza)."""

    def __missing__(self, clave: str) -> str:
        return "{" + clave + "}"


def _fmt(texto: str, params: Mapping[str, str] | None = None, **extra: str) -> str:
    datos = _Seguro({**(params or {}), **extra})
    try:
        return texto.format_map(datos)
    except (ValueError, IndexError, KeyError, AttributeError):
        return texto


# =============================================================================================
# B3. Esperar la IP de cada máquina
# =============================================================================================

_SIMBOLOS_IP: dict[EstadoIp, str] = {
    EstadoIp.PENDIENTE: "○",
    EstadoIp.ESPERANDO: "●",
    EstadoIp.OBTENIDA: "✓",
    EstadoIp.OBTENIDA_PARCIAL: "⚠",
    EstadoIp.SIN_AGENTE: "–",
    EstadoIp.AGENTE_NO_RESPONDE: "⚠",
    EstadoIp.SIN_IP: "⚠",
    EstadoIp.SIN_PERMISO: "✕",
    EstadoIp.OMITIDA: "–",
    EstadoIp.CANCELADA: "–",
    EstadoIp.ERROR: "✕",
}


def simbolo_estado_ip(estado: EstadoIp) -> str:
    """Símbolo del estado de IP: junto al texto, para no depender solo del color."""
    return _SIMBOLOS_IP.get(estado, "·")


def texto_estado_ip(estado: EstadoIp) -> str:
    """Nombre corto del estado de IP de una máquina (columna «IP» y filtros)."""
    if estado == EstadoIp.PENDIENTE:
        return QCoreApplication.translate("TextosB", "Pendiente")
    if estado == EstadoIp.ESPERANDO:
        return QCoreApplication.translate("TextosB", "Esperando la IP…")
    if estado == EstadoIp.OBTENIDA:
        return QCoreApplication.translate("TextosB", "IP obtenida")
    if estado == EstadoIp.OBTENIDA_PARCIAL:
        return QCoreApplication.translate("TextosB", "IP a revisar")
    if estado == EstadoIp.SIN_AGENTE:
        return QCoreApplication.translate("TextosB", "Sin agente")
    if estado == EstadoIp.AGENTE_NO_RESPONDE:
        return QCoreApplication.translate("TextosB", "El agente no responde")
    if estado == EstadoIp.SIN_IP:
        return QCoreApplication.translate("TextosB", "Sin IP")
    if estado == EstadoIp.SIN_PERMISO:
        return QCoreApplication.translate("TextosB", "Sin permiso")
    if estado == EstadoIp.OMITIDA:
        return QCoreApplication.translate("TextosB", "No aplica")
    if estado == EstadoIp.CANCELADA:
        return QCoreApplication.translate("TextosB", "Se dejó de esperar")
    return QCoreApplication.translate("TextosB", "Error")


def texto_celda_ip(entrada: EntradaLibro, *, espera_activa: bool) -> str:
    """Contenido de la celda «IP» de una máquina del progreso (vacía si no pidió esperar la IP).

    Con IP muestra la dirección (con «(a revisar)» si no es la de la primera tarjeta); sin ella,
    el estado en palabras. ``espera_activa`` indica que la espera de IP sigue en marcha.
    """
    ip = entrada.ip
    if ip is None:
        if not entrada.elemento.cfg.esperar_ip:
            return ""
        if espera_activa and entrada.estado in (EstadoMV.OK, EstadoMV.CON_AVISOS):
            return f"{simbolo_estado_ip(EstadoIp.ESPERANDO)} " + texto_estado_ip(EstadoIp.ESPERANDO)
        if entrada.estado in ESTADOS_EN_CURSO:
            return f"{simbolo_estado_ip(EstadoIp.PENDIENTE)} " + texto_estado_ip(EstadoIp.PENDIENTE)
        return "—"
    if ip.estado == EstadoIp.OBTENIDA and ip.principal:
        return f"{simbolo_estado_ip(ip.estado)} {ip.principal}"
    if ip.estado == EstadoIp.OBTENIDA_PARCIAL and ip.principal:
        sufijo = QCoreApplication.translate("TextosB", "(a revisar)")
        return f"{simbolo_estado_ip(ip.estado)} {ip.principal} {sufijo}"
    return f"{simbolo_estado_ip(ip.estado)} {texto_estado_ip(ip.estado)}"


def token_color_ip(entrada: EntradaLibro) -> str:
    """Token de color de la celda «IP» (nunca solo color: el texto y el símbolo van aparte)."""
    ip = entrada.ip
    if ip is None:
        return "texto_secundario"
    if ip.estado == EstadoIp.OBTENIDA:
        return "exito"
    if ip.estado in (
        EstadoIp.OBTENIDA_PARCIAL,
        EstadoIp.AGENTE_NO_RESPONDE,
        EstadoIp.SIN_IP,
    ):
        return "aviso"
    if ip.estado in (EstadoIp.SIN_PERMISO, EstadoIp.ERROR):
        return "error"
    return "texto_secundario"


def _texto_sin_permiso_ip(error: ErrorProxLaunch | None) -> str:
    privilegio = error.params.get("privilegio", "") if error is not None else ""
    if privilegio:
        return QCoreApplication.translate(
            "TextosB",
            "Tu usuario no puede preguntar a la máquina por su IP: falta el permiso {privilegio}. "
            "Pídeselo a tu administrador.",
        ).format(privilegio=privilegio)
    return QCoreApplication.translate(
        "TextosB",
        "Tu usuario no puede preguntar a la máquina por su IP. Hace falta el permiso "
        "VM.Monitor (Proxmox 8) o VM.GuestAgent.Audit (Proxmox 9) sobre la máquina. Pídeselo a "
        "tu administrador.",
    )


def texto_detalle_ip(resultado: ResultadoIp | None, *, ip_fija: str | None = None) -> str:
    """Explicación en lenguaje llano del resultado de IP de una máquina (detalles e informe).

    ``ip_fija`` es la IP que se pidió fijar (CIDR) para explicar un «no coincide».
    """
    if resultado is None:
        return ""
    e = resultado.estado
    if e == EstadoIp.OBTENIDA:
        partes = [
            QCoreApplication.translate("TextosB", "IP obtenida: {ip}.").format(
                ip=resultado.principal or "—"
            )
        ]
        if resultado.no_coincide:
            partes.append(
                QCoreApplication.translate(
                    "TextosB",
                    "No coincide con la IP fija que se configuró{cual}. Revisa la red de la "
                    "máquina.",
                ).format(cual=f" ({ip_fija})" if ip_fija else "")
            )
        return " ".join(partes)
    if e == EstadoIp.OBTENIDA_PARCIAL:
        base = QCoreApplication.translate(
            "TextosB",
            "Solo se encontró {ip}, que no es una dirección IPv4 de la primera tarjeta de red de "
            "la máquina (puede ser de otra tarjeta o ser IPv6). Compruébala antes de usarla.",
        ).format(ip=resultado.principal or "—")
        if resultado.no_coincide:
            base += " " + QCoreApplication.translate(
                "TextosB", "Tampoco coincide con la IP fija que se configuró."
            )
        return base
    if e == EstadoIp.SIN_AGENTE:
        return QCoreApplication.translate(
            "TextosB",
            "La máquina no tiene activado el agente invitado en Proxmox, así que no se puede "
            "saber su IP. Actívalo en sus opciones (Opciones → Agente QEMU) y vuelve a "
            "encenderla.",
        )
    if e == EstadoIp.AGENTE_NO_RESPONDE:
        return QCoreApplication.translate(
            "TextosB",
            "El agente invitado no respondió en el plazo. Suele pasar con las imágenes de Ubuntu "
            "y Debian, que no traen el agente: instálalo dentro de la máquina (paquete "
            "qemu-guest-agent) o usa un script de cloud-init que lo instale.",
        )
    if e == EstadoIp.SIN_IP:
        base = QCoreApplication.translate(
            "TextosB",
            "El agente respondió, pero no encontró ninguna IP útil (se ignoran las direcciones "
            "locales y las de Docker o de puentes). Puede que la máquina aún no tenga red.",
        )
        if resultado.descartadas:
            base += " " + QCoreApplication.translate(
                "TextosB", "Interfaces ignoradas: {n}."
            ).format(n=", ".join(resultado.descartadas))
        return base
    if e == EstadoIp.SIN_PERMISO:
        return _texto_sin_permiso_ip(resultado.error)
    if e == EstadoIp.OMITIDA:
        return QCoreApplication.translate(
            "TextosB",
            "No se esperó su IP: la máquina no se encendió o no llegó a crearse.",
        )
    if e == EstadoIp.CANCELADA:
        return QCoreApplication.translate(
            "TextosB",
            "Se dejó de esperar su IP (o la máquina se eliminó). La máquina no se tocó.",
        )
    if e == EstadoIp.ERROR:
        return QCoreApplication.translate(
            "TextosB",
            "No se pudo consultar la IP por un error inesperado. Puedes verla en Proxmox, en "
            "el resumen de la máquina.",
        )
    return texto_estado_ip(e)


def texto_resumen_ips(resumen: ResumenIps, esperando: int = 0) -> str:
    """«3 con IP · 1 sin IP · 0 no aplicable» (RF-B3.6). Las máquinas que aún esperan su IP se
    cuentan aparte («1 esperando») y no como «sin IP» mientras dure la espera."""
    sin = max(0, resumen.sin_ip - esperando)
    texto = QCoreApplication.translate(
        "TextosB", "{con} con IP · {sin} sin IP · {na} no aplicable"
    ).format(con=resumen.con_ip, sin=sin, na=resumen.no_aplicable)
    if esperando > 0:
        texto += " · " + QCoreApplication.translate("TextosB", "{n} esperando").format(n=esperando)
    return texto


def texto_esperando_ips(n: int) -> str:
    """Aviso mientras sigue la espera de IP tras terminar la creación."""
    if n == 1:
        return QCoreApplication.translate(
            "TextosB",
            "La creación terminó. Se está esperando la IP de 1 máquina; no hace falta esperar "
            "para usar el resto.",
        )
    return QCoreApplication.translate(
        "TextosB",
        "La creación terminó. Se está esperando la IP de %n máquinas; no hace falta esperar "
        "para usar el resto.",
        None,
        n,
    )


def texto_espera_ip_en_uno(plazo_s: int) -> str:
    """Línea del resultado de una sola máquina mientras se espera su IP."""
    return QCoreApplication.translate(
        "TextosB", "Esperando su IP (hasta {plazo} s)… Puedes seguir usando ProxLaunch."
    ).format(plazo=plazo_s)


def texto_ip_en_uno(resultado: ResultadoIp, *, ip_fija: str | None = None) -> str:
    """Línea del resultado de una sola máquina con el desenlace de su espera de IP."""
    if resultado.estado in (EstadoIp.OBTENIDA, EstadoIp.OBTENIDA_PARCIAL):
        return texto_detalle_ip(resultado, ip_fija=ip_fija)
    return QCoreApplication.translate("TextosB", "IP: {motivo}").format(
        motivo=texto_detalle_ip(resultado, ip_fija=ip_fija)
    )


def texto_confirmar_cerrar_con_espera_ip() -> str:
    """Aviso al cerrar la aplicación con la espera de IP en marcha (CA-B3.5.5)."""
    return QCoreApplication.translate(
        "TextosB",
        "ProxLaunch sigue esperando la IP de algunas máquinas. Si cierras, dejará de esperar. "
        "Las máquinas no se tocan y no pasa nada en el servidor.",
    )


def texto_nota_deshacer_espera_ip() -> str:
    """Nota del diálogo «Deshacer» cuando hay máquinas esperando su IP."""
    return QCoreApplication.translate(
        "TextosB",
        "Algunas máquinas todavía esperan su IP. Si las eliminas, se dejará de esperar antes "
        "de borrarlas.",
    )


def texto_tooltip_reintentar_ajustes() -> str:
    """Ayuda de «Reintentar ajustes» (incluye cloud-init y contraseña de la fase B)."""
    return QCoreApplication.translate(
        "TextosB",
        "Vuelve a aplicar lo que no se pudo cambiar tras clonar: etiquetas, procesadores, "
        "memoria, tamaño del disco o la configuración inicial (cloud-init y contraseña). No "
        "crea máquinas nuevas.",
    )


# =============================================================================================
# Avisos de máquina (códigos en ``EntradaLibro.avisos`` y ``EstadoPlantillaImagen.avisos``)
# =============================================================================================


def texto_aviso_b(codigo: str) -> str:
    """Texto de un código de aviso de la fase B; cadena vacía si no es de la fase B.

    Cubre B3 (``ip_*``) y B2 (``sin_ampliar``,
    ``ajuste_omitido:disco``, ``imagen_quedo_en_import``, ``maquina_borrada``,
    ``borrado_sin_esperar``, ``omitido:<paso>``, ``se_asume_qcow2``, ``consola_serie``,
    ``imagen_sin_agente``, ``solo_clon_completo``).
    """
    if codigo == "ip_no_obtenida":
        return QCoreApplication.translate(
            "TextosB",
            "La máquina se creó, pero no se pudo conocer su IP. Mira la columna «IP» para ver "
            "el motivo.",
        )
    if codigo == "ip_parcial":
        return QCoreApplication.translate(
            "TextosB",
            "La IP encontrada no es la de la primera tarjeta de red (o es IPv6). Compruébala "
            "antes de usarla.",
        )
    if codigo == "ip_no_coincide":
        return QCoreApplication.translate(
            "TextosB", "La IP que tiene la máquina no coincide con la IP fija que se pidió."
        )
    return _texto_aviso_b2(codigo)


def _texto_aviso_b2(codigo: str) -> str:
    """Avisos del asistente de plantillas (B2)."""
    if codigo == "sin_ampliar":
        return QCoreApplication.translate(
            "TextosB",
            "No se amplió el disco: el tamaño pedido no supera el de la imagen (el disco solo "
            "puede crecer).",
        )
    if codigo == "ajuste_omitido:disco":
        return QCoreApplication.translate(
            "TextosB",
            "No se amplió el disco: no pudimos comprobar que tengas el permiso VM.Config.Disk. "
            "Amplíalo en Proxmox si lo necesitas.",
        )
    if codigo == "imagen_quedo_en_import":
        return QCoreApplication.translate(
            "TextosB",
            "La imagen se quedó en el almacenamiento de importación. ProxLaunch no la borra: "
            "pide a un administrador que la elimine desde Proxmox si ya no la necesitas.",
        )
    if codigo == "maquina_borrada":
        return QCoreApplication.translate(
            "TextosB",
            "Se borró la máquina a medio crear. Puedes reintentar la creación (con otro VMID "
            "si quieres).",
        )
    if codigo == "borrado_sin_esperar":
        return QCoreApplication.translate(
            "TextosB",
            "Se pidió borrar la máquina a medio crear, pero se dejó de esperar: la tarea sigue "
            "en Proxmox. Comprueba allí si se borró.",
        )
    if codigo.startswith("maquina_anterior_sin_borrar:"):
        # ``maquina_anterior_sin_borrar:<vmid>:<nombre>``; el nombre no lleva «:».
        _, vmid, nombre = (codigo.split(":", 2) + ["", ""])[:3]
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "La máquina del intento anterior ({nombre}, VMID {vmid}) sigue en Proxmox. "
                "ProxLaunch no la borra: si no la quieres, bórrala a mano desde Proxmox.",
            ),
            nombre=nombre or "—",
            vmid=vmid or "—",
        )
    if codigo.startswith("omitido:"):
        paso = codigo.partition(":")[2]
        if paso == "ampliar":
            return QCoreApplication.translate(
                "TextosB", "Se continuó sin ampliar el disco: tiene el tamaño de la imagen."
            )
        if paso == "cloudinit":
            return QCoreApplication.translate(
                "TextosB",
                "Se continuó sin guardar los valores de cloud-init: las copias no los heredarán.",
            )
        if paso == "convertir":
            return QCoreApplication.translate(
                "TextosB",
                "No se convirtió en plantilla: la máquina quedó como máquina normal y puedes "
                "encenderla o convertirla en Proxmox.",
            )
        return ""
    if codigo == "se_asume_qcow2":
        return QCoreApplication.translate(
            "TextosB",
            "La dirección termina en «.img». Se pedirá al servidor con la extensión «.qcow2» "
            "porque las imágenes cloud de este tipo son qcow2.",
        )
    if codigo == "consola_serie":
        return QCoreApplication.translate(
            "TextosB",
            "Con la consola serie, la consola gráfica clásica de Proxmox (noVNC) se queda en "
            "negro. Para entrar a la máquina usa la consola «xterm.js» (la de texto).",
        )
    if codigo == "imagen_sin_agente":
        return QCoreApplication.translate(
            "TextosB",
            "Las imágenes oficiales de Ubuntu y Debian no traen el agente invitado "
            "(qemu-guest-agent). Sin él ProxLaunch no podrá decirte la IP de las copias y el "
            "apagado desde Proxmox puede tardar. Puedes instalarlo con un script de cloud-init.",
        )
    if codigo == "solo_clon_completo":
        return QCoreApplication.translate(
            "TextosB",
            "El almacenamiento de destino es de tipo LVM grueso: las copias de esta plantilla "
            "solo podrán ser clones completos (no enlazados).",
        )
    return ""


# =============================================================================================
# Errores de la fase B
# =============================================================================================


def texto_error_b(error: ErrorProxLaunch) -> str | None:
    """Mensaje en español de un error de B2 o B3; ``None`` si el código no es de B2 ni de B3.

    ``textos.texto_error`` delega aquí al final de su cadena (DT-B15). Los errores de B1
    (cloud-init, claves, snippets y contraseña) los traduce ``textos``. Un 403 de un paso B
    (cloud-init o contraseña) lleva ``params["ajuste"]`` y se explica aquí como «se creó, pero
    faltan permisos»: ``textos.texto_error`` lo consulta ANTES que la cadena genérica.
    """
    p = error.params
    c = error.codigo
    if c == CodigoError.PERMISO_INSUFICIENTE and p.get("ajuste") in ("cloudinit", "contrasena"):
        return _texto_403_ajuste_b(p)
    return _texto_error_agente_y_plantilla(error)


def _texto_403_ajuste_b(p: Mapping[str, str]) -> str:
    """403 de un paso B: la máquina existe, falta un permiso y el lote no se pausa."""
    if p.get("ajuste") == "contrasena":
        que = QCoreApplication.translate("TextosB", "la contraseña")
    else:
        que = QCoreApplication.translate("TextosB", "la configuración inicial (cloud-init)")
    if p.get("privilegio"):
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "Se creó, pero no se pudo guardar {que}: a tu usuario le falta el permiso "
                "{privilegio} en «{ruta}». La máquina no se encendió. Pídeselo a tu "
                "administrador y reintenta los ajustes.",
            ),
            p,
            que=que,
        )
    return QCoreApplication.translate(
        "TextosB",
        "Se creó, pero no se pudo guardar {que}: a tu usuario le falta un permiso (en Proxmox 8 "
        "VM.Config.Cloudinit o VM.Config.Network; en Proxmox 9, VM.Config.Cloudinit). La "
        "máquina no se encendió. Pídeselo a tu administrador y reintenta los ajustes.",
    ).format(que=que)


def _texto_error_agente_y_plantilla(error: ErrorProxLaunch) -> str | None:
    p = error.params
    c = error.codigo
    if c == CodigoError.AGENTE_NO_CONFIGURADO:
        return QCoreApplication.translate(
            "TextosB",
            "La máquina no tiene activado el agente invitado en Proxmox, así que no se puede "
            "saber su IP.",
        )
    if c == CodigoError.AGENTE_NO_RESPONDE:
        return QCoreApplication.translate(
            "TextosB",
            "El agente invitado no respondió. Instala el paquete qemu-guest-agent dentro de la "
            "máquina o usa un script de cloud-init que lo instale.",
        )
    if c == CodigoError.MV_NO_EN_MARCHA:
        return QCoreApplication.translate(
            "TextosB", "La máquina no está encendida, así que no puede contestar."
        )
    if c == CodigoError.PLANTILLA_EN_MARCHA:
        return QCoreApplication.translate(
            "TextosB",
            "No se puede convertir en plantilla una máquina encendida. Apágala y reintenta.",
        )
    if c == CodigoError.PLANTILLA_CON_SNAPSHOTS:
        return QCoreApplication.translate(
            "TextosB",
            "No se puede convertir en plantilla una máquina con instantáneas (snapshots). "
            "Bórralas en Proxmox y reintenta.",
        )
    if c == CodigoError.PLANTILLA_NO_APAGADA:
        if p.get("bloqueo"):
            return _fmt(
                QCoreApplication.translate(
                    "TextosB",
                    "La máquina está bloqueada por otra tarea de Proxmox ({bloqueo}). Espera a "
                    "que termine y reintenta. No se convirtió en plantilla.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "TextosB",
            "La máquina no está apagada, así que no se convirtió en plantilla. Apágala en "
            "Proxmox y reintenta.",
        )
    if c == CodigoError.IMAGEN_FORMATO_INCORRECTO:
        return QCoreApplication.translate(
            "TextosB",
            "Proxmox no aceptó el archivo porque su formato no coincide con la extensión. Si "
            "es una imagen «.img», ProxLaunch la pide como «.qcow2»; prueba a elegir una imagen "
            "con extensión .qcow2 o .raw, o descárgala a mano e impórtala desde Proxmox.",
        )
    if c == CodigoError.SUMA_NO_COINCIDE:
        if p.get("esperada") and p.get("obtenida"):
            return _fmt(
                QCoreApplication.translate(
                    "TextosB",
                    "La suma no coincide: la descarga no es la esperada. Esperada «{esperada}…», "
                    "obtenida «{obtenida}…». No se usó el archivo.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "TextosB", "La suma no coincide: la descarga no es la esperada. No se usó el archivo."
        )
    if c == CodigoError.PLANTILLA_IMAGEN_SIN_IMPORT:
        return QCoreApplication.translate(
            "TextosB",
            "Ningún almacenamiento de este nodo admite el contenido «Importar». Pide al "
            "administrador que lo active (Centro de datos → Almacenamiento) en uno de tipo "
            "directorio, NFS o CIFS.",
        )
    return None


# =============================================================================================
# B2. Asistente «Crear plantilla desde imagen cloud»
# =============================================================================================


def titulo_asistente_b2() -> str:
    return QCoreApplication.translate("TextosB", "Crear plantilla desde imagen cloud")


def texto_intro_b2() -> str:
    """Qué es una imagen cloud, qué es una plantilla y qué hará el asistente (RF-B2.1)."""
    return QCoreApplication.translate(
        "TextosB",
        "Una imagen cloud es un disco ya instalado y mínimo (Ubuntu, Debian, Rocky…) que se "
        "publica para servidores. No trae instalador: se importa tal cual y cloud-init la "
        "personaliza en el primer arranque.\n\n"
        "Una plantilla es una máquina «modelo» de la que se sacan copias (clones). No se "
        "enciende ni se edita; cada copia nace con su propio disco. Convertir una máquina en "
        "plantilla no se puede deshacer.\n\n"
        "El asistente hará esto, en orden: 1) pone la imagen en el servidor (la sube desde tu "
        "equipo o el servidor la descarga); 2) crea una máquina nueva con esa imagen como disco; "
        "3) amplía el disco al tamaño que pidas; 4) guarda los valores de cloud-init (opcional); "
        "5) convierte la máquina en plantilla.",
    )


def ayuda_b2(clave: str) -> str:
    """Ayuda ampliada («?») de cada sección del asistente (RF-B8.1)."""
    if clave == "intro":
        return QCoreApplication.translate(
            "TextosB",
            "Con este asistente conviertes una imagen cloud (un archivo .qcow2, .img, .raw o "
            ".vmdk) en una plantilla lista para clonar en «Clonar una plantilla». Si no sabes "
            "qué elegir, deja las opciones como están: están pensadas para Ubuntu, Debian, "
            "Rocky o AlmaLinux.",
        )
    if clave == "imagen":
        return QCoreApplication.translate(
            "TextosB",
            "La imagen es el disco de partida. Puedes subirla desde tu equipo, pedir al servidor "
            "que la descargue de una dirección web o usar una que ya esté en el servidor. Las "
            "imágenes «.img» de Ubuntu son en realidad qcow2: ProxLaunch las sube como «.qcow2» "
            "sin tocar su contenido.",
        )
    if clave == "suma":
        return QCoreApplication.translate(
            "TextosB",
            "La suma de verificación (huella) comprueba que el archivo no está dañado ni "
            "manipulado. Cópiala de la web oficial de la distribución. Si no coincide, no se "
            "sube ni se usa nada. Para archivos de tu equipo solo se admite SHA-256.",
        )
    if clave == "opciones_cloud":
        return QCoreApplication.translate(
            "TextosB",
            "Son los ajustes que las imágenes cloud esperan. La unidad cloud-init es el pequeño "
            "disco donde Proxmox deja usuario, claves y red. La consola serie permite entrar "
            "con la consola «xterm.js». El agente invitado deja que Proxmox sepa la IP de la "
            "máquina, pero hay que instalarlo dentro (las imágenes de Ubuntu y Debian no lo "
            "traen).",
        )
    if clave == "cloudinit":
        return QCoreApplication.translate(
            "TextosB",
            "Aquí puedes dejar guardados valores de cloud-init que heredarán todas las copias: "
            "usuario, claves SSH públicas, red por DHCP, DNS y dominio. Las copias pueden "
            "cambiarlos después. Por seguridad no existe campo de contraseña: una contraseña en "
            "la plantilla se copiaría a todas las máquinas.",
        )
    if clave == "irreversible":
        return QCoreApplication.translate(
            "TextosB",
            "Una plantilla no se enciende ni se vuelve a convertir en máquina normal: solo sirve "
            "para crear copias. ProxLaunch no puede borrarla; si te equivocas, bórrala desde "
            "Proxmox (no se puede mientras tenga copias enlazadas).",
        )
    return ""


def texto_ejemplos_urls_b2() -> str:
    """Ejemplos de direcciones oficiales (solo texto: nunca se descargan solas)."""
    return QCoreApplication.translate(
        "TextosB",
        "Ejemplos (revisa en la web de cada distribución cuál es la dirección vigente):\n"
        "• Ubuntu 24.04: https://cloud-images.ubuntu.com/noble/current/"
        "noble-server-cloudimg-amd64.img\n"
        "• Debian 12: https://cloud.debian.org/images/cloud/bookworm/latest/"
        "debian-12-genericcloud-amd64.qcow2\n"
        "• AlmaLinux 9: https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/"
        "AlmaLinux-9-GenericCloud-latest.x86_64.qcow2",
    )


def texto_irreversible_b2() -> str:
    """Texto exacto de la casilla de irreversibilidad (RF-B2.9)."""
    return QCoreApplication.translate(
        "TextosB",
        "Entiendo que la plantilla no se puede encender ni volver a convertir en máquina "
        "normal; solo sirve para crear copias",
    )


def texto_confirmacion_b2(
    *, nombre: str, vmid: int, nodo: str, gib: int, storage: str, imagen: str, lvm: bool
) -> str:
    """Resumen que se confirma antes de escribir nada (RF-B2.9)."""
    base = QCoreApplication.translate(
        "TextosB",
        "Se va a crear la plantilla «{nombre}» (número {vmid}) en el nodo «{nodo}», con un "
        "disco de {gib} GiB en «{storage}», a partir de «{imagen}».\n\n"
        "Cuando termine, la máquina se convertirá en plantilla. Esto NO se puede deshacer: la "
        "plantilla no se podrá encender ni volver a ser una máquina normal; solo servirá para "
        "crear copias.",
    ).format(nombre=nombre, vmid=vmid, nodo=nodo, gib=gib, storage=storage, imagen=imagen)
    if lvm:
        base += "\n\n" + _texto_aviso_b2("solo_clon_completo")
    return base


def texto_nombre_paso_b2(paso: PasoB2) -> str:
    if paso == PasoB2.IMAGEN:
        return QCoreApplication.translate("TextosB", "1. Poner la imagen en el servidor")
    if paso == PasoB2.CREAR:
        return QCoreApplication.translate("TextosB", "2. Crear la máquina e importar el disco")
    if paso == PasoB2.AMPLIAR:
        return QCoreApplication.translate("TextosB", "3. Ampliar el disco")
    if paso == PasoB2.CLOUDINIT:
        return QCoreApplication.translate("TextosB", "4. Guardar los valores de cloud-init")
    return QCoreApplication.translate("TextosB", "5. Convertir en plantilla")


_SIMBOLOS_PASO: dict[EstadoPaso, str] = {
    EstadoPaso.PENDIENTE: "○",
    EstadoPaso.EN_CURSO: "●",
    EstadoPaso.HECHO: "✓",
    EstadoPaso.FALLIDO: "✕",
    EstadoPaso.OMITIDO: "–",
    EstadoPaso.INCIERTO: "?",
}


def simbolo_estado_paso_b2(estado: EstadoPaso) -> str:
    return _SIMBOLOS_PASO.get(estado, "·")


def texto_estado_paso_b2(estado: EstadoPaso) -> str:
    if estado == EstadoPaso.PENDIENTE:
        return QCoreApplication.translate("TextosB", "Pendiente")
    if estado == EstadoPaso.EN_CURSO:
        return QCoreApplication.translate("TextosB", "En curso")
    if estado == EstadoPaso.HECHO:
        return QCoreApplication.translate("TextosB", "Hecho")
    if estado == EstadoPaso.FALLIDO:
        return QCoreApplication.translate("TextosB", "Falló")
    if estado == EstadoPaso.OMITIDO:
        return QCoreApplication.translate("TextosB", "Omitido")
    return QCoreApplication.translate("TextosB", "No sabemos cómo acabó")


def texto_que_queda_tras_fallo(paso: PasoB2, nombre_archivo: str) -> str:
    """Qué ha quedado en el servidor tras fallar un paso (tabla de RF-B2.10)."""
    if paso == PasoB2.IMAGEN:
        return QCoreApplication.translate(
            "TextosB",
            "Puede haber quedado un archivo parcial («{archivo}») o nada en el almacenamiento "
            "de importación. ProxLaunch no borra archivos del almacenamiento.",
        ).format(archivo=nombre_archivo)
    if paso == PasoB2.CREAR:
        return QCoreApplication.translate(
            "TextosB",
            "Puede haber quedado una máquina a medio crear con el número reservado. Puedes "
            "comprobarlo, borrarla si es seguro, o reintentar con otro número.",
        )
    if paso == PasoB2.AMPLIAR:
        return QCoreApplication.translate(
            "TextosB", "La máquina está completa, pero el disco no se amplió."
        )
    if paso == PasoB2.CLOUDINIT:
        return QCoreApplication.translate(
            "TextosB", "La máquina está completa, pero sin los valores de cloud-init."
        )
    return QCoreApplication.translate(
        "TextosB", "La máquina está completa, pero todavía no es una plantilla."
    )


def texto_accion_reintentar(paso: PasoB2) -> str:
    if paso == PasoB2.CONVERTIR:
        return QCoreApplication.translate("TextosB", "Reintentar la conversión")
    if paso == PasoB2.IMAGEN:
        return QCoreApplication.translate("TextosB", "Reintentar la imagen")
    return QCoreApplication.translate("TextosB", "Reintentar este paso")


def texto_accion_omitir(paso: PasoB2) -> str:
    """Botón «continuar sin…» de los pasos 3 a 5 (RF-B2.10)."""
    if paso == PasoB2.AMPLIAR:
        return QCoreApplication.translate("TextosB", "Continuar sin ampliar")
    if paso == PasoB2.CLOUDINIT:
        return QCoreApplication.translate("TextosB", "Continuar sin cloud-init")
    return QCoreApplication.translate("TextosB", "Dejarla como máquina normal")


def texto_borrado_no_ofrecido(motivo: str, *, sin_certeza: bool) -> str:
    """Por qué no se ofrece «Borrar la máquina a medio crear» (RF-B2.10).

    ``motivo`` es el código del error de ``condiciones_borrado`` (o vacío) y ``sin_certeza`` que
    alguna lectura falló o no hay UPID de creación.
    """
    if sin_certeza:
        return QCoreApplication.translate(
            "TextosB",
            "No puedo confirmar que la máquina sea tuya (no consta que este asistente la "
            "creara, o no se pudo leer su estado), así que no la borro. Si la máquina es de "
            "este asistente, bórrala desde Proxmox (menú «Más» → «Eliminar»).",
        )
    if motivo == CodigoError.ROLLBACK_ENCENDIDA:
        return QCoreApplication.translate(
            "TextosB", "No se ofrece borrarla: está encendida. Apágala en Proxmox primero."
        )
    if motivo == CodigoError.ROLLBACK_BLOQUEADA:
        return QCoreApplication.translate(
            "TextosB", "No se ofrece borrarla: está bloqueada por otra tarea de Proxmox."
        )
    if motivo == CodigoError.ROLLBACK_PROTEGIDA:
        return QCoreApplication.translate(
            "TextosB", "No se ofrece borrarla: tiene la protección contra borrado activada."
        )
    if motivo == CodigoError.PERMISO_INSUFICIENTE:
        return QCoreApplication.translate(
            "TextosB",
            "No se ofrece borrarla: tu usuario no tiene el permiso VM.Allocate sobre la máquina.",
        )
    return QCoreApplication.translate(
        "TextosB",
        "No se ofrece borrarla: no cumple todas las condiciones de seguridad (nombre, "
        "plantilla, bloqueos).",
    )


def texto_confirmar_borrado(nombre: str, vmid: int) -> str:
    """Confirmación expresa de «Borrar la máquina a medio crear»."""
    return QCoreApplication.translate(
        "TextosB",
        "Se va a eliminar de Proxmox la máquina «{nombre}» (número {vmid}), que este asistente "
        "dejó a medio crear. Esta acción no se puede deshacer. La imagen del almacenamiento de "
        "importación no se borra.",
    ).format(nombre=nombre, vmid=vmid)


def texto_resultado_b2(*, nombre: str, vmid: int, storage: str) -> str:
    """Resultado de una plantilla creada con éxito (RF-B2.11)."""
    return QCoreApplication.translate(
        "TextosB",
        "La plantilla «{nombre}» (número {vmid}) está lista en «{storage}». Ya puedes usarla en "
        "«Clonar una plantilla» (actualiza la lista de plantillas si no aparece).",
    ).format(nombre=nombre, vmid=vmid, storage=storage)


def texto_resultado_b2_sin_plantilla(*, nombre: str, vmid: int) -> str:
    """Resultado cuando la máquina quedó completa pero no se convirtió en plantilla."""
    return QCoreApplication.translate(
        "TextosB",
        "La máquina «{nombre}» (número {vmid}) quedó como máquina normal, no como plantilla. "
        "Puedes convertirla en plantilla desde Proxmox cuando quieras.",
    ).format(nombre=nombre, vmid=vmid)


def texto_cerrar_en_curso_b2() -> str:
    """Confirmación al cerrar el asistente mientras trabaja (RF-B2.10, CA-B2.10.6)."""
    return QCoreApplication.translate(
        "TextosB",
        "El asistente está trabajando. Si lo cierras, ProxLaunch dejará de esperar, pero lo que "
        "ya se envió al servidor seguirá su curso y no se borrará nada. Después podrás ver en "
        "Proxmox cómo quedó.",
    )


def texto_estado_control_b2(estado: EstadoControlB2) -> str:
    """Por qué un control del asistente está deshabilitado, con el privilegio o versión."""
    p = estado.params
    codigo = estado.codigo
    nombre = _nombre_control_b2(estado.control)
    if codigo == CodigoError.OPCION_SIN_VERSION:
        base = _fmt(
            QCoreApplication.translate(
                "TextosB", "«{opcion}» necesita Proxmox {version} o una versión posterior."
            ),
            p,
            opcion=nombre,
        )
        if estado.control == ControlB2.ASISTENTE:
            # CA-B0.4.1: la razón de fondo de la versión mínima (BUG-B-P1-5).
            base += " " + QCoreApplication.translate(
                "TextosB",
                "Antes de la 8.4 Proxmox no permite subir imágenes de disco al contenido "
                "«Importar» del almacenamiento.",
            )
        return base
    if codigo == CodigoError.OPCION_SIN_PRIVILEGIO:
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "«{opcion}» no está disponible: tu usuario no tiene el privilegio {privilegio} "
                "en «{ruta}». Pídeselo a tu administrador.",
            ),
            p,
            opcion=nombre,
        )
    if codigo is None:
        return ""
    texto = texto_error_b(ErrorProxLaunch(codigo, dict(p)))
    if texto is not None:
        return texto
    from proxlaunch.interfaz.textos import texto_error

    return texto_error(ErrorProxLaunch(codigo, dict(p)))


def _nombre_control_b2(control: ControlB2) -> str:
    if control == ControlB2.ASISTENTE:
        return QCoreApplication.translate("TextosB", "Crear plantilla desde imagen cloud")
    if control == ControlB2.ORIGEN_ARCHIVO:
        return QCoreApplication.translate("TextosB", "Subir un archivo de tu equipo")
    if control == ControlB2.ORIGEN_URL:
        return QCoreApplication.translate("TextosB", "Descargar desde una dirección web")
    if control == ControlB2.ORIGEN_YA_IMPORTADA:
        return QCoreApplication.translate("TextosB", "Usar una imagen que ya está en el servidor")
    if control == ControlB2.CONSOLA_SERIE:
        return QCoreApplication.translate("TextosB", "Consola serie")
    if control == ControlB2.UNIDAD_CLOUDINIT:
        return QCoreApplication.translate("TextosB", "Unidad cloud-init")
    if control == ControlB2.AGENTE:
        return QCoreApplication.translate("TextosB", "Agente invitado")
    if control == ControlB2.VALORES_CLOUDINIT:
        return QCoreApplication.translate("TextosB", "Valores de cloud-init para las copias")
    if control == ControlB2.CONVERTIR:
        return QCoreApplication.translate("TextosB", "Convertir en plantilla")
    return QCoreApplication.translate("TextosB", "Borrar la máquina a medio crear")


# --- Problemas V-B01..V-B16 (validación de la solicitud) ----------------------------------


def texto_problema_b2(p: Problema) -> str | None:
    """Mensaje de un problema V-B01..V-B16 y V-B39 del asistente; ``None`` si no es de B2."""
    prm = p.params
    cod = p.codigo
    if cod == "V-B01":
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "Este asistente necesita Proxmox {requerida} o una versión posterior; este "
                "servidor es el {version}.",
            ),
            prm,
        )
    if cod == "V-B02":
        return _texto_origen_b2(prm)
    if cod == "V-B03":
        return _texto_nombre_b2(prm)
    if cod == "V-B04":
        return _texto_formato_b2(prm)
    if cod == "V-B05":
        return _texto_suma_b2(prm)
    if cod == "V-B06":
        if prm.get("motivo") == "no_valido":
            return QCoreApplication.translate(
                "TextosB",
                "El almacenamiento elegido para la imagen no admite el contenido «Importar» "
                "en este nodo.",
            )
        return texto_error_b(ErrorProxLaunch(CodigoError.PLANTILLA_IMAGEN_SIN_IMPORT)) or ""
    if cod == "V-B07":
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "El almacenamiento «{storage}» no guarda discos de máquinas en el nodo "
                "«{nodo}». Elige otro.",
            ),
            prm,
        )
    if cod == "V-B08":
        return _texto_aviso_b2("solo_clon_completo")
    if cod == "V-B09":
        return QCoreApplication.translate(
            "TextosB",
            "El nombre de la plantilla no es válido: usa letras sin acentos, números y guiones "
            "(sin espacios ni guiones al principio o al final), hasta 63 caracteres.",
        )
    if cod == "V-B12":
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "El tamaño pedido ({final_gib} GiB) no supera el de la imagen ({imagen_gib} "
                "GiB): el disco no se ampliará (solo puede crecer).",
            ),
            prm,
        )
    if cod == "V-B13":
        return QCoreApplication.translate(
            "TextosB",
            "Ya hay un archivo con ese nombre en el servidor. Elige si usar el que ya está o "
            "reemplazarlo.",
        )
    if cod == "V-B14":
        return QCoreApplication.translate(
            "TextosB", "Marca la casilla de que entiendes que la plantilla no se puede deshacer."
        )
    if cod == "V-B15":
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "Una de las opciones marcadas necesita el permiso {privilegio} en «{ruta}», que "
                "tu usuario no tiene. Desmarca esa opción o pídeselo a tu administrador.",
            ),
            prm,
        )
    if cod == "V-B16":
        return _texto_aviso_b2("imagen_sin_agente")
    if cod == "V-B39":
        return _texto_v_b39(prm)
    return None


def _texto_origen_b2(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "falta_archivo":
        return QCoreApplication.translate("TextosB", "Elige el archivo de imagen de tu equipo.")
    if motivo == "falta_url":
        return QCoreApplication.translate(
            "TextosB", "Escribe la dirección web de la imagen y pulsa «Comprobar»."
        )
    if motivo == "http":
        return QCoreApplication.translate(
            "TextosB",
            "La dirección usa http://: no se puede garantizar que el archivo no fue alterado "
            "por el camino. Conviene indicar la suma de verificación.",
        )
    if motivo == "volid":
        return QCoreApplication.translate(
            "TextosB", "Elige una imagen de la lista de imágenes del servidor."
        )
    return QCoreApplication.translate(
        "TextosB",
        "No se pudo leer el archivo de imagen. Comprueba que existe y que puedes abrirlo.",
    )


def _texto_nombre_b2(prm: Mapping[str, str]) -> str:
    if prm.get("motivo") == "extension":
        return QCoreApplication.translate(
            "TextosB",
            "El archivo debe terminar en .qcow2, .img, .raw o .vmdk. Otros formatos (ISO, OVA, "
            "ZIP…) no se pueden importar como disco.",
        )
    return QCoreApplication.translate(
        "TextosB",
        "El nombre del archivo no es admisible: usa solo letras sin acentos, números, punto, "
        "guion y guion bajo.",
    )


def _texto_formato_b2(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "otro_formato":
        return QCoreApplication.translate(
            "TextosB",
            "El archivo «.img» no es una imagen qcow2 ni un disco en bruto: no se renombra a "
            "ciegas. Conviértelo antes a qcow2.",
        )
    if motivo == "extension_no_coincide":
        return QCoreApplication.translate(
            "TextosB",
            "El contenido del archivo no corresponde a su extensión. Renómbralo o conviértelo "
            "al formato correcto.",
        )
    if motivo == "nombre_incoherente":
        return QCoreApplication.translate(
            "TextosB",
            "El nombre con el que se subiría no corresponde al contenido del archivo. Vuelve "
            "a elegir el archivo.",
        )
    if motivo == "vacio":
        return QCoreApplication.translate("TextosB", "El archivo está vacío.")
    from proxlaunch.interfaz.textos import texto_error

    return texto_error(ErrorProxLaunch(CodigoError.IMAGEN_NO_ADMITIDA, {"motivo": motivo}))


def _nombre_algoritmo_suma(algoritmo: str) -> str:
    """«MD5» o «SHA-1» a partir del valor del algoritmo («md5», «sha1»)."""
    if algoritmo.lower() in ("sha1", "sha-1"):
        return "SHA-1"
    if algoritmo.lower() == "md5":
        return "MD5"
    return algoritmo.upper() or QCoreApplication.translate("TextosB", "elegida")


def _texto_suma_b2(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "suma_obligatoria":
        return QCoreApplication.translate(
            "TextosB",
            "Con una dirección http:// o sin verificar los certificados nada garantiza que el "
            "archivo no fue alterado por el camino, así que hace falta la suma de verificación "
            "SHA-256 o SHA-512. Suele publicarla la distribución junto a la imagen, por ejemplo "
            "en el archivo SHA256SUMS de Ubuntu.",
        )
    if motivo == "suma_debil":
        return _fmt(
            QCoreApplication.translate(
                "TextosB",
                "La suma {algoritmo} es débil: no protege bien contra un archivo manipulado. "
                "Mejor usa SHA-256 o SHA-512.",
            ),
            algoritmo=_nombre_algoritmo_suma(prm.get("algoritmo", "")),
        )
    if motivo == "solo_sha256_local":
        return QCoreApplication.translate(
            "TextosB",
            "Para un archivo de tu equipo solo se admite la suma SHA-256 (64 caracteres).",
        )
    if motivo == "no_se_usa":
        return QCoreApplication.translate(
            "TextosB", "La suma no se usa con una imagen que ya está en el servidor."
        )
    return QCoreApplication.translate(
        "TextosB",
        "La suma de verificación no tiene un formato válido: solo números y letras de la A a la "
        "F, con la longitud de su algoritmo (64 caracteres para SHA-256).",
    )


def _texto_v_b39(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "contrasena_en_plantilla":
        return QCoreApplication.translate(
            "TextosB",
            "Una plantilla nunca lleva contraseña: se copiaría a todas las máquinas.",
        )
    if motivo == "snippets":
        return QCoreApplication.translate(
            "TextosB", "Los scripts (snippets) se eligen al clonar, no en la plantilla."
        )
    return QCoreApplication.translate(
        "TextosB",
        "En la plantilla solo se puede configurar la primera tarjeta de red y por DHCP. La IP "
        "fija se elige al clonar.",
    )


def texto_clave_privada_rechazada() -> str:
    """Rechazo de una clave privada pegada o leída de un archivo (RF-B1.5)."""
    return QCoreApplication.translate(
        "TextosB",
        "Eso parece una clave privada. Nunca la pegues aquí: usa solo la clave pública (el "
        "archivo que termina en .pub).",
    )


def texto_problema_clave(linea: int, motivo: str) -> str:
    """Por qué una línea de claves SSH no sirve (V-B22 a V-B24); nunca repite su contenido."""
    donde = (
        QCoreApplication.translate("TextosB", "Línea {n}").format(n=linea)
        if linea > 0
        else QCoreApplication.translate("TextosB", "El texto")
    )
    if motivo == "tipo_desconocido":
        que = QCoreApplication.translate(
            "TextosB",
            "no empieza por un tipo de clave conocido (por ejemplo ssh-ed25519 o ssh-rsa)",
        )
    elif motivo == "sin_cuerpo":
        que = QCoreApplication.translate("TextosB", "le falta el cuerpo de la clave")
    elif motivo == "base64":
        que = QCoreApplication.translate("TextosB", "el cuerpo de la clave no es válido")
    elif motivo == "con_opciones":
        que = QCoreApplication.translate(
            "TextosB", "lleva opciones por delante (command=…, from=…), que no se admiten"
        )
    elif motivo == "demasiadas":
        que = QCoreApplication.translate("TextosB", "supera el máximo de 20 claves")
    elif motivo == "demasiado_texto":
        que = QCoreApplication.translate("TextosB", "es demasiado largo (máximo 8 KiB en total)")
    else:
        que = QCoreApplication.translate("TextosB", "no es una clave pública")
    return f"{donde}: {que}."


def texto_problema_completo(p: Problema) -> str:
    """Texto de un problema: los de B2 primero y, si no, los de siempre y los de B1."""
    texto = texto_problema_b2(p)
    if texto is not None:
        return texto
    if p.codigo == "V-B11":
        regla = Problema(p.campo, p.params.get("regla", ""), p.severidad, dict(p.params))
        from proxlaunch.interfaz.textos import texto_problema

        return texto_problema(regla)
    from proxlaunch.interfaz.textos import texto_problema

    return texto_problema(p)


def es_error(p: Problema) -> bool:
    """El problema bloquea (es un error, no un aviso)."""
    return p.severidad == Severidad.ERROR
