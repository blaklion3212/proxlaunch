"""Traducción a español de los códigos del núcleo (RF-21, RF-23, CA-21.4).

El núcleo habla en códigos; aquí cada código se convierte en un mensaje en lenguaje llano
con ``QCoreApplication.translate``. Si un código no tiene texto se muestra el mensaje
genérico de CA-21.2 (los detalles técnicos los muestra la vista aparte).
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso, EstadoHuella
from proxlaunch.nucleo.validacion import Problema


class _Seguro(dict[str, str]):
    """Diccionario que deja visible el marcador si falta un parámetro."""

    def __missing__(self, clave: str) -> str:
        return "{" + clave + "}"


def _fmt(texto: str, params: Mapping[str, str] | None = None, **extra: str) -> str:
    datos = _Seguro({**(params or {}), **extra})
    return texto.format_map(datos)


# --- Errores ------------------------------------------------------------------------


def _destino(params: Mapping[str, str]) -> str:
    host = params.get("host", "")
    puerto = params.get("puerto", "")
    return f"{host}:{puerto}" if host and puerto else host


def texto_generico() -> str:
    """Mensaje para un error sin texto propio (CA-21.2)."""
    return QCoreApplication.translate("Textos", "Proxmox respondió con un error que no conocemos")


def texto_error(error: ErrorProxLaunch) -> str:
    """Mensaje en español de un ``ErrorProxLaunch`` según su código y parámetros."""
    p = error.params
    c = error.codigo
    if c == CodigoError.CREDENCIALES_INVALIDAS:
        return QCoreApplication.translate(
            "Textos",
            "Las credenciales no son válidas. Revisa el usuario, el token o la contraseña.",
        )
    if c == CodigoError.SESION_EXPIRADA:
        return QCoreApplication.translate("Textos", "Tu sesión expiró. Vuelve a iniciar sesión.")
    if c == CodigoError.HUELLA_CAMBIADA:
        return QCoreApplication.translate(
            "Textos",
            "El certificado del servidor cambió. Podría ser un cambio legítimo (renovación) "
            "o un intento de suplantación. Verifica con tu administrador.",
        )
    if c == CodigoError.HUELLA_NO_CONFIADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Primero hay que confiar en el certificado del servidor ({host})."
            ),
            p,
        )
    if c == CodigoError.TFA_NO_SOPORTADO:
        return QCoreApplication.translate(
            "Textos",
            "Este usuario exige un método de segundo factor que ProxLaunch no admite. "
            "Usa un API Token.",
        )
    if c == CodigoError.TFA_CODIGO_INCORRECTO:
        return QCoreApplication.translate(
            "Textos",
            "El código no es correcto o ya venció. Espera al siguiente código e inténtalo "
            "de nuevo.",
        )
    if c == CodigoError.SERVIDOR_NO_RESPONDE:
        return _texto_servidor_no_responde(p)
    if c == CodigoError.NODO_NO_DISPONIBLE:
        if p.get("nodo"):
            return _fmt(
                QCoreApplication.translate("Textos", "El nodo {nodo} no está disponible"), p
            )
        return QCoreApplication.translate("Textos", "El nodo no está disponible.")
    if c == CodigoError.PERMISO_INSUFICIENTE:
        if p.get("privilegio"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Tu usuario no tiene permiso para realizar esta acción. Falta {privilegio} "
                    "en {ruta}. Pide a tu administrador este permiso o usa un token con "
                    "permisos suficientes.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos",
            "Tu usuario no tiene permiso para realizar esta acción. Pide a tu administrador "
            "este permiso o usa un token con permisos suficientes.",
        )
    if c == CodigoError.VMID_OCUPADO:
        if p.get("siguiente"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "El número {vmid} ya lo usa otra máquina. Prueba con {siguiente}"
                ),
                p,
            )
        return _fmt(
            QCoreApplication.translate("Textos", "El número {vmid} ya lo usa otra máquina."), p
        )
    if c == CodigoError.SIN_ESPACIO:
        if p.get("storage"):
            ids = [x for x in p["storage"].split(",") if x]
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "No hay espacio suficiente en «{storage}» para crear el disco. Libera "
                    "espacio o elige otro almacenamiento.",
                ),
                storage="», «".join(ids),
            )
        if p.get("requerido_gib"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Ningún nodo tiene {requerido_gib} GiB libres en un almacenamiento para "
                    "discos. Reduce el tamaño de los discos o libera espacio.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos",
            "No hay espacio suficiente para crear el disco. Libera espacio o elige otro "
            "almacenamiento.",
        )
    if c == CodigoError.TAREA_TIEMPO_AGOTADO:
        return QCoreApplication.translate(
            "Textos", "La tarea sigue en marcha en Proxmox, no sabemos si terminó"
        )
    if c == CodigoError.ERROR_FORMATO:
        campo = p.get("campo") or QCoreApplication.translate("Textos", "un campo")
        return _fmt(
            QCoreApplication.translate("Textos", "Proxmox no entendió el valor de {campo}."),
            campo=campo,
        )
    if c == CodigoError.PARAMETRO_INVALIDO:
        if p.get("mensaje"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "Proxmox rechazó el valor de {campo}: {mensaje}"
                ),
                p,
            )
        if p.get("regla"):
            return QCoreApplication.translate(
                "Textos",
                "El formulario tiene datos que hay que corregir antes de crear la máquina.",
            )
        return _fmt(QCoreApplication.translate("Textos", "Proxmox rechazó el valor de {campo}."), p)
    if c == CodigoError.VERSION_NO_SOPORTADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "ProxLaunch requiere Proxmox VE {minima} o superior (el servidor tiene {version})",
            ),
            p,
        )
    if c == CodigoError.RECURSO_INEXISTENTE:
        recurso = p.get("recurso", "")
        if recurso.startswith("vm "):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Proxmox dijo que la tarea terminó, pero la máquina {vmid} no aparece en "
                    "el nodo {nodo}.",
                ),
                p,
                vmid=recurso[3:],
            )
        if recurso:
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "«{recurso}» ya no existe en el nodo. Actualiza y elige de nuevo.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos", "Ese elemento ya no existe. Actualiza y elige de nuevo."
        )
    if c == CodigoError.UPID_INVALIDO:
        return QCoreApplication.translate(
            "Textos", "Proxmox no devolvió el identificador de la tarea"
        )
    if c == CodigoError.LLAVERO_NO_DISPONIBLE:
        return QCoreApplication.translate(
            "Textos",
            "No hay un llavero disponible en este equipo; las credenciales no se guardarán",
        )
    return texto_generico()


def _texto_servidor_no_responde(p: Mapping[str, str]) -> str:
    """CA-01.5, CA-07.4 y CA-07.6: destino y motivo por IP si hay varias."""
    motivos = [m for m in p.get("motivos", "").split(";") if m]
    hosts = [h for h in p.get("hosts", "").split(",") if h]
    if len(hosts) > 1 or len(motivos) > 1:
        lineas = [
            QCoreApplication.translate(
                "Textos", "No se pudo contactar con ninguno de los servidores del perfil:"
            )
        ]
        for m in motivos:
            host, _, motivo = m.partition("=")
            lineas.append(f"  • {host}: {_motivo_red(motivo)}")
        return "\n".join(lineas)
    destino = _destino(p)
    if destino:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "No se pudo contactar con el servidor ({destino})"
            ),
            destino=destino,
        )
    return QCoreApplication.translate("Textos", "El servidor no responde")


def _motivo_red(motivo: str) -> str:
    if "timeout" in motivo.lower():
        return QCoreApplication.translate("Textos", "no respondió a tiempo")
    if "rechaz" in motivo.lower() or "refused" in motivo.lower():
        return QCoreApplication.translate("Textos", "conexión rechazada")
    return QCoreApplication.translate("Textos", "no respondió")


# --- Problemas de validación --------------------------------------------------------


def texto_problema(p: Problema) -> str:
    """Mensaje de una regla V-xx (sección 4 de los requisitos)."""
    cod = p.codigo
    prm = p.params
    if cod == "V-01":
        return QCoreApplication.translate(
            "Textos",
            "El nombre solo puede tener letras sin acentos, números y guiones, y no puede "
            "empezar ni terminar con guion.",
        )
    if cod == "V-02":
        return QCoreApplication.translate(
            "Textos", "El número de máquina debe estar entre 100 y 999999999."
        )
    if cod == "V-03":
        return texto_error(ErrorProxLaunch(CodigoError.VMID_OCUPADO, dict(prm)))
    if cod == "V-04":
        return QCoreApplication.translate("Textos", "El nodo no está disponible.")
    if cod == "V-05":
        if p.campo == "sockets":
            return QCoreApplication.translate("Textos", "Elige entre 1 y 4 sockets.")
        return QCoreApplication.translate("Textos", "Elige entre 1 y 128 núcleos.")
    if cod == "V-06":
        if p.campo.startswith("ballooning"):
            return QCoreApplication.translate(
                "Textos", "La memoria mínima no puede superar a la memoria total."
            )
        return QCoreApplication.translate("Textos", "La memoria debe ser de al menos 16 MiB.")
    if cod == "V-07":
        if prm.get("maximo"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "Ese tipo de conexión admite como máximo {maximo} discos."
                ),
                prm,
            )
        return QCoreApplication.translate("Textos", "Elige un tipo de conexión de disco válido.")
    if cod == "V-08":
        return QCoreApplication.translate(
            "Textos", "El tamaño debe ser un número entero de GiB, mínimo 1."
        )
    if cod == "V-09":
        return QCoreApplication.translate("Textos", "Este almacenamiento solo admite formato raw.")
    if cod == "V-10":
        return QCoreApplication.translate("Textos", "El controlador de discos no es válido.")
    if cod == "V-11":
        return QCoreApplication.translate(
            "Textos", "IO Thread necesita el bus VirtIO o SCSI con controlador virtio-scsi-single."
        )
    if cod == "V-12":
        return QCoreApplication.translate(
            "Textos", "La emulación SSD no está disponible en el bus VirtIO."
        )
    if cod == "V-13":
        return QCoreApplication.translate(
            "Textos", "Este tipo de conexión no admite liberar el espacio sin usar (discard)."
        )
    if cod == "V-14":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El disco pide {pedido_gib} GiB y «{storage}» solo tiene {libre_gib} GiB libres.",
            ),
            prm,
        )
    if cod == "V-14.thin":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Los discos piden {pedido_gib} GiB y «{storage}» tiene {libre_gib} GiB libres. "
                "Este almacenamiento solo ocupa el espacio a medida que se usa, así que puedes "
                "continuar, pero conviene vigilar el espacio.",
            ),
            prm,
        )
    if cod == "V-15":
        return QCoreApplication.translate("Textos", "La VLAN debe estar entre 1 y 4094.")
    if cod == "V-16.sinredes":
        return QCoreApplication.translate("Textos", "El nodo no tiene redes (bridges) disponibles")
    if cod == "V-16":
        if prm.get("bridge") is not None:
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "La red «{bridge}» no existe en el nodo «{nodo}»."
                ),
                prm,
            )
        return QCoreApplication.translate("Textos", "El modelo de tarjeta de red no es válido.")
    if cod == "V-17":
        if p.campo == "storage_efi":
            return QCoreApplication.translate(
                "Textos", "UEFI necesita un almacenamiento para guardar su configuración"
            )
        return QCoreApplication.translate(
            "Textos", "Ese almacenamiento no está disponible en el nodo."
        )
    if cod == "V-18":
        return QCoreApplication.translate(
            "Textos", "El token debe tener el formato usuario@realm!nombre=secreto."
        )
    if cod == "V-19":
        return QCoreApplication.translate("Textos", "Escribe solo el nombre o la IP del servidor.")
    if cod == "V-20":
        return QCoreApplication.translate("Textos", "El origen del sistema no es válido.")
    if cod == "V-21":
        return QCoreApplication.translate("Textos", "El código tiene 6 números.")
    return texto_generico()


# --- Avisos de la sesión ------------------------------------------------------------


def privilegio_faltante_critico(aviso: Aviso) -> bool:
    """``True`` si el aviso de permisos indica que falta ``VM.Allocate`` (CA-12.1)."""
    if aviso.codigo != CodigoAviso.PERMISOS_INCOMPLETOS:
        return False
    return "VM.Allocate" in aviso.params.get("privilegios", "").split(",")


def _lista_privilegios(p: Mapping[str, str]) -> str:
    """«VM.Allocate en /vms, Sys.Audit en /» a partir de ``rutas`` («Priv@/ruta,...»)."""
    rutas = [r for r in p.get("rutas", "").split(",") if r]
    if not rutas:
        return p.get("privilegios", "").replace(",", ", ")
    partes = []
    for r in rutas:
        priv, _, ruta = r.partition("@")
        if ruta:
            partes.append(
                QCoreApplication.translate("Textos", "{privilegio} en {ruta}").format(
                    privilegio=priv, ruta=ruta
                )
            )
        else:
            partes.append(priv)
    return ", ".join(partes)


def texto_aviso(aviso: Aviso) -> str:
    """Mensaje de un aviso no bloqueante."""
    p = aviso.params
    if aviso.codigo == CodigoAviso.LLAVERO_NO_DISPONIBLE:
        return QCoreApplication.translate(
            "Textos",
            "No hay un llavero disponible en este equipo; las credenciales no se guardarán",
        )
    if aviso.codigo == CodigoAviso.TOPOLOGIA_DEGRADADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Topología desconocida ({nodos} nodos): a tu usuario le falta el permiso "
                "Sys.Audit en «/» para ver el clúster. Puedes seguir trabajando.",
            ),
            p,
        )
    if aviso.codigo == CodigoAviso.PERMISOS_INCOMPLETOS:
        if privilegio_faltante_critico(aviso):
            return QCoreApplication.translate(
                "Textos",
                "Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate",
            )
        faltan = _lista_privilegios(p)
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "A tu usuario le faltan permisos recomendados ({privilegios}). Algunas "
                "acciones podrían fallar.",
            ),
            privilegios=faltan,
        )
    if aviso.codigo == CodigoAviso.VERSION_NO_PROBADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Este servidor tiene Proxmox VE {version}, más nuevo que la última versión "
                "que ProxLaunch ha probado. Puedes continuar, pero algo podría no funcionar "
                "como se espera.",
            ),
            p,
        )
    return texto_generico()


# --- Desenlaces, etapas y otros -----------------------------------------------------


def texto_desenlace(resultado: ResultadoCreacion, nombre: str = "") -> str:
    """Mensaje principal del desenlace de una creación."""
    d = resultado.desenlace
    if d == Desenlace.OK:
        return _fmt(
            QCoreApplication.translate("Textos", "Máquina {nombre} ({vmid}) creada en {nodo}"),
            nombre=nombre,
            vmid=str(resultado.vmid),
            nodo=resultado.nodo,
        )
    if d == Desenlace.CON_AVISOS:
        return QCoreApplication.translate("Textos", "Creada con avisos")
    if d == Desenlace.ERROR:
        if resultado.error is not None:
            return texto_error(resultado.error)
        return texto_generico()
    if d == Desenlace.TIEMPO_AGOTADO:
        return QCoreApplication.translate(
            "Textos", "La tarea sigue en marcha en Proxmox, no sabemos si terminó"
        )
    if d == Desenlace.CONEXION_PERDIDA:
        return QCoreApplication.translate(
            "Textos",
            "Se perdió la conexión mientras se creaba la máquina; la tarea puede haber terminado",
        )
    if d == Desenlace.PARCIAL:
        return QCoreApplication.translate(
            "Textos", "La máquina quedó parcialmente creada; elimínala desde Proxmox"
        )
    if d == Desenlace.CANCELADO:
        if resultado.upid:
            return QCoreApplication.translate(
                "Textos",
                "Cancelado. La tarea pudo seguir en Proxmox; revisa si la máquina existe.",
            )
        return QCoreApplication.translate("Textos", "Cancelado. No se creó nada.")
    return texto_generico()


def texto_etapa(etapa: Etapa) -> str:
    """Nombre de una etapa de la barra de progreso (CA-20.2)."""
    if etapa == Etapa.VALIDANDO:
        return QCoreApplication.translate("Textos", "Validando datos")
    if etapa == Etapa.ENVIANDO:
        return QCoreApplication.translate("Textos", "Enviando a Proxmox")
    if etapa == Etapa.CREANDO:
        return QCoreApplication.translate("Textos", "Creando la máquina")
    if etapa == Etapa.COMPROBANDO:
        return QCoreApplication.translate("Textos", "Comprobando el resultado")
    if etapa == Etapa.LISTO:
        return QCoreApplication.translate("Textos", "Listo")
    return str(etapa)


def texto_motivo_nodo(motivo: MotivoNodo) -> str:
    """Por qué el modo Automático eligió un nodo (CA-13.5)."""
    if motivo == MotivoNodo.UNICO_CANDIDATO:
        return QCoreApplication.translate("Textos", "es el único con espacio suficiente")
    if motivo == MotivoNodo.MAS_MEMORIA_LIBRE:
        return QCoreApplication.translate("Textos", "más memoria y espacio libres")
    if motivo == MotivoNodo.DESEMPATE_ESPACIO_LIBRE:
        return QCoreApplication.translate(
            "Textos", "misma memoria libre; se eligió el que tiene más espacio"
        )
    return ""


def texto_estado_huella(estado: EstadoHuella) -> str:
    """Estado de la huella SSL para mostrarlo al usuario."""
    if estado == EstadoHuella.NUEVA:
        return QCoreApplication.translate("Textos", "Servidor nuevo")
    if estado == EstadoHuella.CONFIRMADA:
        return QCoreApplication.translate("Textos", "Certificado conocido")
    if estado == EstadoHuella.CAMBIADA:
        return QCoreApplication.translate("Textos", "El certificado cambió")
    return QCoreApplication.translate("Textos", "Sin verificar")
