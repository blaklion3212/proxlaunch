"""Traducción a español de los códigos del núcleo (RF-21, RF-23, CA-21.4).

El núcleo habla en códigos; aquí cada código se convierte en un mensaje en lenguaje llano
con ``QCoreApplication.translate``. Si un código no tiene texto se muestra el mensaje
genérico de CA-21.2 (los detalles técnicos los muestra la vista aparte).
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Callable, Iterable, Mapping

from PySide6.QtCore import QCoreApplication, QLocale

from proxlaunch.nucleo.archivos.constantes import (
    LONG_DESCRIPCION,
    LONG_NOMBRE_PERFIL,
    MAX_PERFILES_USUARIO,
)
from proxlaunch.nucleo.archivos.esquema import (
    AvisoArchivo,
    CodigoAvisoArchivo,
    ErrorArchivo,
    ErrorCampo,
    MotivoCampo,
)
from proxlaunch.nucleo.cloudinit.claves import resumen_clave
from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    TIPOS_SNIPPET,
    ModoTarjeta,
)
from proxlaunch.nucleo.constructor_peticion import formato_limite
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, MapaColumnas, ProblemaCelda
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import (
    FACTOR_THIN_MAX,
    MAX_LOTE,
    NUMERO_NOMBRE_MAXIMO,
    RELLENO_MAXIMO,
    VMID_MAXIMO,
    VMID_MINIMO,
)
from proxlaunch.nucleo.lote.modelos import (
    EstadoMV,
    EstadoRollback,
    MotivoNoEnviada,
    MotivoPausa,
    MotivoReparto,
)
from proxlaunch.nucleo.lote.modelos import Problema as ProblemaLote
from proxlaunch.nucleo.lote.modelos import Severidad as SeveridadLote
from proxlaunch.nucleo.lote.rollback import InspeccionRollback
from proxlaunch.nucleo.lotes_guardados.revalidacion import Desajuste, TipoDesajuste
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import (
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    TipoSO,
)
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion
from proxlaunch.nucleo.origen.asistente import CambioAsistente, CampoAsistente
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, EstadoVia, Via
from proxlaunch.nucleo.origen.storages import DecisionStorage, TipoDecision
from proxlaunch.nucleo.perfiles_maquina.aplicar import AvisoPista, resumen_perfil
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso, EstadoHuella
from proxlaunch.nucleo.transferencias.modelos import (
    EstadoTransferencia,
    Progreso,
    RegistroTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.validacion import Problema, Severidad


def _valor_neutro(clave: str) -> str:
    """Texto neutro para un parámetro que falta (nunca se muestra «{clave}»)."""
    if clave in ("host", "destino"):
        return QCoreApplication.translate("Textos", "este servidor")
    if clave in ("vmid", "siguiente"):
        return QCoreApplication.translate("Textos", "esa máquina")
    if clave == "nodo":
        return QCoreApplication.translate("Textos", "ese nodo")
    if clave == "campo":
        return QCoreApplication.translate("Textos", "un campo")
    if clave == "version":
        return QCoreApplication.translate("Textos", "una versión desconocida")
    if clave == "minima":
        return "8.0"
    if clave == "nombre":
        return QCoreApplication.translate("Textos", "esa máquina")
    if clave in ("n", "max"):
        return QCoreApplication.translate("Textos", "varias")
    if clave in ("storage", "recurso"):
        return QCoreApplication.translate("Textos", "ese almacenamiento")
    if clave == "privilegio":
        return QCoreApplication.translate("Textos", "un permiso")
    if clave == "ruta":
        return QCoreApplication.translate("Textos", "esa ruta")
    if clave in ("archivo", "volid"):
        return QCoreApplication.translate("Textos", "el archivo")
    if clave in ("tamano", "libre", "actual_gib", "pedido_gib", "bytes", "total"):
        return "?"
    return QCoreApplication.translate("Textos", "un dato")


class _Seguro(dict[str, str]):
    """Diccionario que deja visible el marcador si falta un parámetro."""

    def __missing__(self, clave: str) -> str:
        # Un marcador sin valor nunca debe verse: se usa un valor neutro traducible.
        return _valor_neutro(clave)


def tooltip_plano(texto: str) -> str:
    """Texto de un tooltip con datos de terceros: se escapa para que Qt no lo lea como HTML.

    El prefijo ``<qt>`` fuerza texto enriquecido (con saltos ``<br>``) y ``html.escape``
    neutraliza cualquier etiqueta del archivo o del servidor.
    """
    return "<qt>" + html.escape(texto).replace("\n", "<br>") + "</qt>"


def _fmt(texto: str, params: Mapping[str, str] | None = None, **extra: str) -> str:
    datos = _Seguro({**(params or {}), **extra})
    try:
        return texto.format_map(datos)
    except (ValueError, IndexError, KeyError, AttributeError):
        return texto


# --- Errores ------------------------------------------------------------------------


def _destino(params: Mapping[str, str]) -> str:
    host = params.get("host", "")
    puerto = params.get("puerto", "")
    return f"{host}:{puerto}" if host and puerto else host


def texto_generico() -> str:
    """Mensaje para un error sin texto propio (CA-21.2)."""
    return QCoreApplication.translate("Textos", "Proxmox respondió con un error que no conocemos")


# Causas de un ajuste posterior al clon que tienen su propio texto (BUG-B-P1-2).
_CAUSAS_CON_TEXTO_PROPIO = frozenset(
    {str(CodigoError.CLAVE_SSH_RECHAZADA), str(CodigoError.SNIPPET_NO_ENCONTRADO)}
)


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
        if p.get("incierto") == "1":
            return QCoreApplication.translate(
                "Textos",
                "No sabemos si Proxmox recibió la orden de crear la máquina. Pulsa "
                "«Comprobar» antes de intentarlo de nuevo.",
            )
        return _texto_servidor_no_responde(p)
    if c == CodigoError.NODO_NO_DISPONIBLE:
        if p.get("nodo"):
            return _fmt(
                QCoreApplication.translate("Textos", "El nodo {nodo} no está disponible"), p
            )
        return QCoreApplication.translate("Textos", "El nodo no está disponible.")
    if c == CodigoError.PERMISO_INSUFICIENTE:
        if p.get("ajuste") in ("cloudinit", "contrasena"):
            # 403 de un paso de la fase B: la máquina existe y el lote no se pausa (RF-B5.3).
            from proxlaunch.interfaz.textos_b import texto_error_b

            texto_b = texto_error_b(error)
            if texto_b is not None:
                return texto_b
        if p.get("via"):
            return _texto_permiso_con_via(p)
        if p.get("privilegio") and p.get("inferido") == "1":
            # Proxmox no dijo qué falta; el privilegio se dedujo del contexto.
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Proxmox no permitió crear la máquina. Lo más probable es que a tu usuario "
                    "le falte {privilegio} en {ruta}. Pide a tu administrador que lo revise.",
                ),
                p,
            )
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
        if p.get("campo", "").startswith("cloudinit."):
            return _texto_parametro_cloudinit(p.get("campo", ""))
        texto_campo = _texto_parametro_origen(p.get("campo", ""))
        if texto_campo is not None:
            return texto_campo
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
    if c == CodigoError.DESCONOCIDO and p.get("motivo") == "respuesta_demasiado_grande":
        return QCoreApplication.translate(
            "Textos",
            "Proxmox devolvió una respuesta demasiado grande y se descartó por seguridad. "
            "Comprueba que la dirección apunta a un servidor Proxmox.",
        )
    texto_lote = _texto_error_lote(error)
    if texto_lote is not None:
        return texto_lote
    texto_archivo = _texto_error_archivo(error)
    if texto_archivo is not None:
        return texto_archivo
    texto_origen_so = _texto_error_origen(error)
    if texto_origen_so is not None:
        return texto_origen_so
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


def texto_campo(campo: str) -> str:
    """Etiqueta traducida del campo de un problema (``detalle_origen.plantilla`` → «Origen»).

    ``""`` si el campo no está mapeado: el llamador muestra solo el mensaje, nunca el
    identificador crudo.
    """
    base = campo.split("[")[0].split(".")[0]
    t = QCoreApplication.translate
    nombres = {
        "nombre": t("Textos", "Nombre"),
        "vmid": t("Textos", "Número de máquina"),
        "nodo": t("Textos", "Nodo"),
        "sockets": t("Textos", "Sockets"),
        "cores": t("Textos", "Núcleos"),
        "memoria_mib": t("Textos", "Memoria"),
        "ballooning": t("Textos", "Ballooning"),
        "controlador_scsi": t("Textos", "Controlador SCSI"),
        "storage_efi": t("Textos", "Almacenamiento de UEFI"),
        "discos": t("Textos", "Disco"),
        "redes": t("Textos", "Red"),
        "origen": t("Textos", "Origen"),
        "detalle_origen": t("Textos", "Origen"),
        "tipo_so": t("Textos", "Sistema operativo"),
        "tpm": t("Textos", "TPM 2.0"),
        "agente_qemu": t("Textos", "Agente de QEMU"),
        "firmware": t("Textos", "Arranque"),
        "tipo_cpu": t("Textos", "Tipo de CPU"),
        "cloudinit": t("Textos", "Configuración inicial"),
        "esperar_ip": t("Textos", "Esperar la IP"),
        "plazo_ip_s": t("Textos", "Plazo de espera de la IP"),
    }
    return nombres.get(base, "")


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
    if cod == "V-07.sindisco":
        return QCoreApplication.translate("Textos", "Agrega al menos un disco o marca «Sin disco».")
    if cod == "V-22":
        return QCoreApplication.translate("Textos", "El tipo de CPU no es válido.")
    if cod == "V-23":
        return QCoreApplication.translate(
            "Textos", "Una máquina admite como máximo 32 interfaces de red."
        )
    if cod == "V-21":
        return QCoreApplication.translate("Textos", "El código tiene 6 números.")
    texto_mvp3 = _texto_problema_mvp3(p)
    if texto_mvp3 is not None:
        return texto_mvp3
    texto_mvp4 = _texto_problema_origen(p)
    if texto_mvp4 is not None:
        return texto_mvp4
    texto_fase_a = _texto_problema_fase_a(p)
    if texto_fase_a is not None:
        return texto_fase_a
    texto_fase_b = _texto_problema_fase_b(p)
    if texto_fase_b is not None:
        return texto_fase_b
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
        base = QCoreApplication.translate("Textos", "Creada con avisos")
        detalles = " ".join(t for t in (texto_aviso_origen(a) for a in resultado.avisos) if t)
        return f"{base}. {detalles}" if detalles else base
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
        if resultado.error is not None and any(
            a.startswith("ajuste_pendiente:") for a in resultado.avisos
        ):
            # Clon creado al que le faltan ajustes: se pueden reintentar o deshacer (E-O24).
            return texto_error(resultado.error)
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
    if etapa == Etapa.AJUSTANDO:
        return QCoreApplication.translate("Textos", "Ajustando la máquina")
    if etapa == Etapa.ENCENDIENDO:
        return QCoreApplication.translate("Textos", "Encendiendo la máquina")
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


# --- Lotes (MVP 2): errores E-L, reglas V-L y estados ---------------------------------


def _plural_maquinas_sin_confirmar(n: int) -> str:
    """«Hay N máquinas sin confirmar» con la forma plural correcta."""
    if n == 1:
        return QCoreApplication.translate(
            "Textos", "Se perdió la conexión. Hay 1 máquina sin confirmar."
        )
    return QCoreApplication.translate(
        "Textos", "Se perdió la conexión. Hay %n máquinas sin confirmar.", None, n
    )


def _entero(valor: str | None) -> int | None:
    try:
        return int(valor) if valor is not None else None
    except ValueError:
        return None


def _causa_legible(causa: str) -> str:
    """La causa de una pausa llega como código de error o como texto ya redactado."""
    try:
        return texto_error(ErrorProxLaunch(CodigoError(causa)))
    except ValueError:
        return causa


def texto_vmid_ocupado_en_lote(vmid: str) -> str:
    """E-L03: en un lote el número lo tomó otra persona; esa máquina se reintenta después."""
    return QCoreApplication.translate(
        "Textos", "El número {vmid} lo usó otra persona mientras tanto. Esta máquina no se creó."
    ).format(vmid=vmid)


def _con_punto(texto: str) -> str:
    """Termina ``texto`` en punto sin duplicarlo."""
    texto = texto.rstrip()
    return texto if texto.endswith((".", "!", "?")) else texto + "."


def texto_motivo_no_enviada(motivo: MotivoNoEnviada | str | None) -> str:
    """Por qué una máquina no se envió (E-L10)."""
    if motivo == MotivoNoEnviada.CANCELADO:
        return QCoreApplication.translate("Textos", "cancelaste el lote")
    if motivo == MotivoNoEnviada.PAUSA:
        return QCoreApplication.translate("Textos", "el lote se detuvo")
    if motivo == MotivoNoEnviada.ERROR_GLOBAL:
        return QCoreApplication.translate("Textos", "hubo un error que afectaba a todo el lote")
    if motivo == MotivoNoEnviada.NODO_CAIDO:
        return QCoreApplication.translate("Textos", "el nodo no respondió")
    return QCoreApplication.translate("Textos", "no se llegó a enviar")


def _texto_error_lote(error: ErrorProxLaunch) -> str | None:
    """Mensajes E-L01 a E-L23; ``None`` si el código no es del lote."""
    p = error.params
    c = error.codigo
    if c == CodigoError.LOTE_SIN_NODO_APTO:
        return QCoreApplication.translate(
            "Textos",
            "Ningún servidor puede alojar esta máquina. Revisa que el almacenamiento y la red "
            "existan en los nodos elegidos.",
        )
    if c == CodigoError.LOTE_VMIDS_INSUFICIENTES:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No encontré {n} números de máquina libres a partir del {inicio}. Prueba con "
                "otro número inicial o con menos máquinas.",
            ),
            p,
            inicio=p.get("inicio", QCoreApplication.translate("Textos", "número inicial")),
        )
    if c == CodigoError.LOTE_SIN_ESPACIO:
        base = _fmt(
            QCoreApplication.translate(
                "Textos",
                "Las máquinas necesitan {pedido} GiB en «{storage}» y solo hay {libre} GiB libres.",
            ),
            p,
            pedido=p.get("pedido", "?"),
            libre=p.get("libre", "?"),
        )
        if p.get("max"):
            base += " " + _fmt(QCoreApplication.translate("Textos", "Caben {max}."), p)
        return base
    if c == CodigoError.LOTE_ENVIO_INCIERTO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No sabemos si «{nombre}» se creó. No se volverá a enviar: pulsa «Comprobar» "
                "para verlo.",
            ),
            p,
        )
    if c == CodigoError.LOTE_EXISTENCIA_INDETERMINADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No pudimos comprobar si «{nombre}» existe. Revisa la conexión y vuelve a "
                "comprobar antes de crearla otra vez.",
            ),
            p,
        )
    if c == CodigoError.LOTE_PAUSADO_REPETIDO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Fallaron {n} máquinas seguidas por la misma causa: {causa} ¿Continuar o detener?",
            ),
            p,
            causa=_con_punto(
                _causa_legible(p.get("causa", ""))
                or QCoreApplication.translate("Textos", "una causa desconocida")
            ),
        )
    if c == CodigoError.LOTE_PAUSADO_CONEXION:
        n = _entero(p.get("n"))
        if n is None:
            return QCoreApplication.translate(
                "Textos", "Se perdió la conexión. Hay máquinas sin confirmar."
            )
        return _plural_maquinas_sin_confirmar(n)
    if c == CodigoError.LOTE_NO_ENVIADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "«{nombre}» no se envió ({motivo}). No existe en Proxmox."
            ),
            p,
            motivo=texto_motivo_no_enviada(p.get("motivo")),
        )
    if c == CodigoError.LOTE_PLAN_CAMBIO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Los datos del servidor cambiaron: {diferencia}. Revisa el resumen y confirma "
                "otra vez.",
            ),
            p,
            diferencia=p.get("diferencia", QCoreApplication.translate("Textos", "hay cambios")),
        )
    if c == CodigoError.LOTE_EN_CURSO:
        return QCoreApplication.translate(
            "Textos", "Hay un lote en curso. Espera a que termine o cancélalo."
        )
    if c == CodigoError.LOTE_CANTIDAD_INVALIDA:
        return _fmt(
            QCoreApplication.translate("Textos", "Elige entre 1 y {max} máquinas."),
            p,
            max=str(MAX_LOTE),
        )
    if c == CodigoError.VERSION_FORZADA_MAYOR:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Has forzado una versión más nueva que la del servidor ({detectada}); solo "
                "puedes simular.",
            ),
            p,
            detectada=p.get("detectada", QCoreApplication.translate("Textos", "otra")),
        )
    if c == CodigoError.ETIQUETA_RECHAZADA:
        return QCoreApplication.translate(
            "Textos", "Proxmox no aceptó la etiqueta de la máquina. No se creó."
        )
    if c == CodigoError.ROLLBACK_FALLO:
        base = _fmt(QCoreApplication.translate("Textos", "No se pudo eliminar «{nombre}»."), p)
        if p.get("mensaje"):
            base = base[:-1] + f": {p['mensaje']}."
        return base + " " + QCoreApplication.translate("Textos", "Elimínala desde Proxmox.")
    if c == CodigoError.ROLLBACK_NO_PROPIA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No eliminamos «{nombre}» porque no podemos asegurar que la creó este lote.",
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_ENCENDIDA:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "«{nombre}» está encendida. Apágala en Proxmox y vuelve a intentarlo."
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_BLOQUEADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{nombre}» está bloqueada por una tarea de Proxmox. Espera a que termine.",
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_DISCOS_SUELTOS:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Pueden haber quedado discos sueltos de «{nombre}»; revísalos en Proxmox.",
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_INCIERTO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No sabemos si se eliminó «{nombre}». Comprueba antes de reintentar.",
            ),
            p,
        )
    if c == CodigoError.ESCRITURA_EN_SIMULACION:
        return QCoreApplication.translate(
            "Textos", "Error interno: se intentó escribir en modo simulación. No se creó nada."
        )
    return _texto_error_fase_a(error) or _texto_error_fase_b(error)


def texto_existe_sin_confirmar() -> str:
    """Una sola máquina existe en Proxmox, pero no se pudo confirmar que la creó ProxLaunch."""
    return QCoreApplication.translate(
        "Textos",
        "La máquina existe en Proxmox, pero no pudimos confirmar que la creó ProxLaunch: "
        "podría ser de otra persona con el mismo número. Verifícalo en Proxmox antes de hacer "
        "nada con ella. No se eliminará desde aquí.",
    )


def texto_estado_mv(estado: EstadoMV) -> str:
    """Nombre del estado de una máquina del lote (CA-L13.1)."""
    nombres = {
        EstadoMV.PENDIENTE: QCoreApplication.translate("Textos", "Pendiente"),
        EstadoMV.VALIDANDO: QCoreApplication.translate("Textos", "Validando datos"),
        EstadoMV.ENVIANDO: QCoreApplication.translate("Textos", "Enviando a Proxmox"),
        EstadoMV.CREANDO: QCoreApplication.translate("Textos", "Creando la máquina"),
        EstadoMV.COMPROBANDO: QCoreApplication.translate("Textos", "Comprobando el resultado"),
        EstadoMV.AJUSTANDO: QCoreApplication.translate("Textos", "Ajustando la máquina"),
        EstadoMV.OK: QCoreApplication.translate("Textos", "Lista"),
        EstadoMV.CON_AVISOS: QCoreApplication.translate("Textos", "Lista, con avisos"),
        EstadoMV.ERROR: QCoreApplication.translate("Textos", "Con error"),
        EstadoMV.PARCIAL: QCoreApplication.translate("Textos", "Quedó a medias"),
        EstadoMV.TIEMPO_AGOTADO: QCoreApplication.translate(
            "Textos", "Sin confirmar (sigue en Proxmox)"
        ),
        EstadoMV.CONEXION_PERDIDA: QCoreApplication.translate("Textos", "No sabemos si se creó"),
        EstadoMV.NO_ENVIADA: QCoreApplication.translate("Textos", "No enviada"),
        EstadoMV.NO_CREADA_SEGURA: QCoreApplication.translate("Textos", "No se creó"),
        EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD: QCoreApplication.translate(
            "Textos", "Existe, sin confirmar de quién es"
        ),
    }
    return nombres.get(estado, str(estado))


_SIMBOLOS_MV = {
    EstadoMV.PENDIENTE: "○",
    EstadoMV.VALIDANDO: "●",
    EstadoMV.ENVIANDO: "●",
    EstadoMV.CREANDO: "●",
    EstadoMV.COMPROBANDO: "●",
    EstadoMV.AJUSTANDO: "●",
    EstadoMV.OK: "✓",
    EstadoMV.CON_AVISOS: "⚠",
    EstadoMV.ERROR: "✕",
    EstadoMV.PARCIAL: "◐",
    EstadoMV.TIEMPO_AGOTADO: "?",
    EstadoMV.CONEXION_PERDIDA: "?",
    EstadoMV.NO_ENVIADA: "–",
    EstadoMV.NO_CREADA_SEGURA: "–",
    EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD: "?",
}


def simbolo_estado_mv(estado: EstadoMV) -> str:
    """Símbolo del estado: junto al texto, para que no dependa solo del color (RNF-L04)."""
    return _SIMBOLOS_MV.get(estado, "·")


def texto_estado_rollback(estado: EstadoRollback) -> str:
    """Nombre del estado de una máquina durante «Deshacer»."""
    nombres = {
        EstadoRollback.PENDIENTE: QCoreApplication.translate("Textos", "Pendiente"),
        EstadoRollback.COMPROBANDO: QCoreApplication.translate("Textos", "Comprobando"),
        EstadoRollback.ELIMINANDO: QCoreApplication.translate("Textos", "Eliminando"),
        EstadoRollback.ELIMINADA: QCoreApplication.translate("Textos", "Eliminada"),
        EstadoRollback.YA_NO_EXISTIA: QCoreApplication.translate("Textos", "Ya no existía"),
        EstadoRollback.FALLO: QCoreApplication.translate("Textos", "No se pudo eliminar"),
        EstadoRollback.OMITIDA: QCoreApplication.translate("Textos", "No se tocó"),
        EstadoRollback.INCIERTA: QCoreApplication.translate("Textos", "No sabemos si se eliminó"),
        EstadoRollback.NO_ENVIADA: QCoreApplication.translate("Textos", "No se procesó"),
    }
    return nombres.get(estado, str(estado))


_SIMBOLOS_ROLLBACK = {
    EstadoRollback.PENDIENTE: "○",
    EstadoRollback.COMPROBANDO: "●",
    EstadoRollback.ELIMINANDO: "●",
    EstadoRollback.ELIMINADA: "✓",
    EstadoRollback.YA_NO_EXISTIA: "✓",
    EstadoRollback.FALLO: "✕",
    EstadoRollback.OMITIDA: "–",
    EstadoRollback.INCIERTA: "?",
    EstadoRollback.NO_ENVIADA: "–",
}


def simbolo_estado_rollback(estado: EstadoRollback) -> str:
    return _SIMBOLOS_ROLLBACK.get(estado, "·")


def texto_motivo_reparto(motivo: str) -> str:
    """Por qué un nodo recibe sus máquinas (CA-L05.9)."""
    if motivo == MotivoReparto.UNICO_NODO:
        return QCoreApplication.translate("Textos", "es el único nodo disponible")
    if motivo == MotivoReparto.ELEGIDO_POR_USUARIO:
        return QCoreApplication.translate("Textos", "lo elegiste tú")
    if motivo == MotivoReparto.MAS_MEMORIA:
        return QCoreApplication.translate("Textos", "Equilibrado: más memoria libre")
    if motivo == MotivoReparto.MAS_ESPACIO:
        return QCoreApplication.translate("Textos", "Equilibrado: más espacio libre")
    if motivo == MotivoReparto.POR_TURNOS:
        return QCoreApplication.translate("Textos", "Por turnos")
    return ""


def texto_motivo_pausa(motivo: MotivoPausa) -> str:
    """Título corto de la pausa del lote."""
    if motivo == MotivoPausa.ERROR_GLOBAL:
        return QCoreApplication.translate("Textos", "El lote se detuvo por un problema general")
    if motivo == MotivoPausa.REPETIDO:
        return QCoreApplication.translate("Textos", "El lote se detuvo: el mismo error se repite")
    return QCoreApplication.translate("Textos", "El lote se detuvo: se perdió la conexión")


def texto_motivo_no_elegible(motivo: str | None) -> str:
    """Por qué una máquina no se puede deshacer (CA-L18.2), a partir del código del motivo."""
    if motivo in (None, ""):
        return QCoreApplication.translate("Textos", "No se puede deshacer.")
    if motivo in (EstadoMV.NO_ENVIADA, "no_enviada"):
        return QCoreApplication.translate("Textos", "No se envió: no existe en Proxmox.")
    if motivo in (EstadoMV.NO_CREADA_SEGURA, "no_creada_segura"):
        return QCoreApplication.translate("Textos", "No se creó: no hay nada que eliminar.")
    if motivo == "propiedad_no_demostrada":
        return QCoreApplication.translate(
            "Textos",
            "Se encontró tras una comprobación, sin etiqueta que la ate a este lote: no podemos "
            "asegurar que sea suya.",
        )
    if motivo in (EstadoMV.ERROR, "error"):
        return QCoreApplication.translate("Textos", "Falló y no se creó nada.")
    if motivo in (EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD, "existe_sin_confirmar_propiedad"):
        return QCoreApplication.translate(
            "Textos", "Existe, pero no podemos asegurar que la creó este lote."
        )
    if motivo in (
        EstadoMV.CONEXION_PERDIDA,
        EstadoMV.TIEMPO_AGOTADO,
        "conexion_perdida",
        "tiempo_agotado",
    ):
        return QCoreApplication.translate(
            "Textos", "No sabemos si se creó: comprueba primero qué pasó."
        )
    try:
        return texto_error(ErrorProxLaunch(CodigoError(motivo), {"nombre": ""})).replace(
            "«»", QCoreApplication.translate("Textos", "esta máquina")
        )
    except ValueError:
        return QCoreApplication.translate("Textos", "No se puede deshacer.")


def _gib_de(prm: Mapping[str, str], clave: str) -> str:
    """Valor en GiB de un parámetro: ``<clave>_gib`` o, si viene en MiB, ``<clave>_mib``."""
    if prm.get(f"{clave}_gib"):
        return prm[f"{clave}_gib"]
    if prm.get(f"{clave}_mib"):
        try:
            return f"{int(prm[f'{clave}_mib']) / 1024:g}"
        except ValueError:
            return "?"
    return prm.get(clave) or "?"


def _a_problema_m1(p: ProblemaLote) -> Problema:
    """Adapta una regla de M1 aplicada a un elemento del plan al formato de ``texto_problema``."""
    severidad = Severidad.ERROR if p.severidad == SeveridadLote.ERROR else Severidad.AVISO
    return Problema(p.campo or "", p.regla, severidad, dict(p.params))


def _causa_nombre(prm: Mapping[str, str]) -> str:
    """Causa por la que un nombre generado no es válido (V-L04)."""
    causa = prm.get("causa", "")
    if causa == "caracter":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "tiene el carácter «{caracter}», que no se admite"
            ),
            prm,
            caracter=prm.get("caracter", "?"),
        )
    if causa == "longitud":
        return QCoreApplication.translate(
            "Textos", "es demasiado largo (cada parte puede tener hasta 63 caracteres)"
        )
    return QCoreApplication.translate(
        "Textos", "no puede empezar ni terminar con guion o punto, ni tener partes vacías"
    )


def _texto_v_l04(p: ProblemaLote) -> str:
    prm = p.params
    causa = prm.get("causa", "")
    if causa == "inicio_fuera_de_rango" or (p.campo or "").endswith("inicio") and not causa:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El número inicial debe estar entre 0 y {maximo}."
            ),
            prm,
            maximo=str(NUMERO_NOMBRE_MAXIMO),
        )
    if causa == "numero_fuera_de_rango":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La numeración llegaría a {ultimo} y el máximo es {maximo}. Baja el número "
                "inicial o la cantidad.",
            ),
            prm,
            ultimo=prm.get("ultimo", "?"),
            maximo=str(NUMERO_NOMBRE_MAXIMO),
        )
    if causa == "relleno_fuera_de_rango" or (p.campo or "").endswith("relleno"):
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El relleno debe estar entre 0 y {maximo} dígitos."
            ),
            prm,
            maximo=str(RELLENO_MAXIMO),
        )
    return _fmt(
        QCoreApplication.translate("Textos", "El nombre «{nombre}» no es válido: {causa}."),
        prm,
        nombre=prm.get("ejemplo") or prm.get("nombre", "?"),
        causa=_causa_nombre(prm),
    )


def _texto_v_l09(prm: Mapping[str, str]) -> str:
    ambito = prm.get("ambito", "")
    lugar = _fmt(QCoreApplication.translate("Textos", "«{storage}»"), prm)
    if ambito == "*compartido*":
        lugar = _fmt(QCoreApplication.translate("Textos", "«{storage}» (compartido)"), prm)
    elif ambito:
        lugar = _fmt(
            QCoreApplication.translate("Textos", "«{storage}» del nodo {nodo}"),
            prm,
            nodo=ambito,
        )
    texto = _fmt(
        QCoreApplication.translate(
            "Textos",
            "Las {n} máquinas necesitan {pedido} GiB en {lugar} y solo hay {libre} GiB libres.",
        ),
        prm,
        pedido=_gib_de(prm, "pedido"),
        libre=_gib_de(prm, "libre"),
        lugar=lugar,
    )
    if prm.get("max"):
        texto += " " + _fmt(QCoreApplication.translate("Textos", "Caben {max}."), prm)
    return texto


def _texto_v_l11(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "sin_conexion":
        return _fmt(QCoreApplication.translate("Textos", "«{nodo}» está sin conexión."), prm)
    if motivo == "storage":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "«{nodo}» no tiene el almacenamiento «{storage}»."
            ),
            prm,
        )
    if motivo == "efidisk":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "«{nodo}» no tiene un almacenamiento para la configuración de UEFI."
            ),
            prm,
        )
    if motivo == "bridge":
        return _fmt(
            QCoreApplication.translate("Textos", "«{nodo}» no tiene la red «{bridge}»."), prm
        )
    if motivo == "fuente":
        return _texto_v_l11_fuente(prm)
    if motivo == "plantilla":
        return _texto_v_l11_plantilla(prm)
    return _fmt(
        QCoreApplication.translate("Textos", "«{nodo}» no puede alojar esta configuración."), prm
    )


def _con_fila(p: ProblemaLote, texto: str, fila: str | None) -> str:
    """Antepone «Fila N:» (lote por filas, ``fila`` = su número de origen) a un texto por fila."""
    if fila is None or p.indice is None:
        return texto
    return QCoreApplication.translate("Textos", "Fila {n}: {texto}").format(n=fila, texto=texto)


def texto_problema_lote(p: ProblemaLote, *, fila: str | None = None) -> str:
    """Mensaje de una regla V-L (docs/requisitos/mvp2.md §4) o de una V-xx de M1 por elemento.

    En un lote por filas, ``fila`` es el número con el que se nombra la fila del problema (su
    número en el archivo, o su posición): los problemas por fila dicen «Fila N» en vez de
    «Máquina N».
    """
    regla, prm = p.regla, p.params
    if regla == "V-L01":
        if prm.get("causa") == "maximo":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "El máximo por lote es {max} máquinas. Divide el trabajo en varios lotes.",
                ),
                prm,
                max=str(MAX_LOTE),
            )
        return _fmt(
            QCoreApplication.translate("Textos", "Elige entre 1 y {max} máquinas."),
            prm,
            max=str(MAX_LOTE),
        )
    if regla == "V-L02":
        if prm.get("causa") == "vacio":
            return QCoreApplication.translate("Textos", "Escribe un prefijo para los nombres.")
        return QCoreApplication.translate(
            "Textos", "El prefijo solo puede tener letras sin acentos, números y guiones."
        )
    if regla == "V-L03":
        return QCoreApplication.translate("Textos", "Elige un guion o ningún separador.")
    if regla == "V-L04":
        return _texto_v_l04(p)
    if regla == "V-L05":
        return QCoreApplication.translate("Textos", "Los nombres del lote no pueden repetirse.")
    if regla == "V-L06":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Ya existe una máquina llamada «{nombre}» (número {vmid})."
            ),
            prm,
        )
    if regla == "V-L07":
        if prm.get("ultimo"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "El lote llegaría hasta el número {ultimo} y el máximo es {maximo}. Baja el "
                    "número inicial o la cantidad.",
                ),
                prm,
                maximo=str(VMID_MAXIMO),
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El número inicial debe estar entre {minimo} y {maximo}."
            ),
            minimo=str(VMID_MINIMO),
            maximo=str(VMID_MAXIMO),
        )
    if regla == "V-L08":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "No hay {n} números de máquina libres a partir del {inicio}."
            ),
            prm,
        )
    if regla == "V-L09":
        return _texto_v_l09(prm)
    if regla == "V-L10":
        if p.severidad == SeveridadLote.ERROR:
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Estás pidiendo {pedido} GiB y en «{storage}» solo hay {libre} GiB libres: es "
                    "más de {factor} veces lo que hay. Reduce las máquinas o el tamaño de los "
                    "discos.",
                ),
                prm,
                pedido=_gib_de(prm, "pedido"),
                libre=_gib_de(prm, "libre"),
                factor=str(FACTOR_THIN_MAX),
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Estás pidiendo {pedido} GiB y solo hay {libre} GiB libres en «{storage}». "
                "Funciona mientras las máquinas no usen todo su disco; si se llena, todas las "
                "máquinas de ese almacenamiento pueden fallar.",
            ),
            prm,
            pedido=_gib_de(prm, "pedido"),
            libre=_gib_de(prm, "libre"),
        )
    if regla == "V-L11":
        return _con_fila(p, _texto_v_l11(prm), fila)
    if regla == "V-M07":
        return _con_fila(p, texto_problema(_a_problema_m1(p)), fila)
    if regla == "V-M10":
        return texto_problema(_a_problema_m1(p))
    if regla == "V-L12.cpu":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Cada máquina pide {vcpus} procesadores virtuales y «{nodo}» tiene {cpus_nodo}.",
            ),
            prm,
        )
    if regla == "V-L12.desconocida":
        nodos = [n for n in prm.get("nodos", "").split(",") if n]
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No se pudo leer la memoria libre de {nodos}; el reparto usa el espacio.",
            ),
            prm,
            nodos=", ".join(f"«{n}»" for n in nodos) or prm.get("nodo", "?"),
        )
    if regla == "V-L12":
        if "pedido_mib" not in prm and "pedido_gib" not in prm and "pedido" not in prm:
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "No se pudo leer la memoria libre de «{nodo}»; el reparto usa el espacio.",
                ),
                prm,
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "En «{nodo}» pides {pedido} GiB de memoria y hay {libre} GiB libres. Las "
                "máquinas se crean apagadas; el problema aparecerá al encenderlas.",
            ),
            prm,
            pedido=_gib_de(prm, "pedido"),
            libre=_gib_de(prm, "libre"),
        )
    if regla == "V-L13":
        return QCoreApplication.translate("Textos", "Elige al menos un nodo disponible.")
    if regla == "V-L14":
        return QCoreApplication.translate("Textos", "Se actualizaron los datos del servidor.")
    if regla == "V-L15":
        return texto_error(ErrorProxLaunch(CodigoError.VERSION_FORZADA_MAYOR, dict(prm)))
    if regla == "V-L16":
        return QCoreApplication.translate(
            "Textos", "Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate"
        )
    if regla == "V-L17":
        return texto_error(ErrorProxLaunch(CodigoError.LOTE_EN_CURSO))
    if regla == "E-L01":
        return _con_fila(p, _texto_e_l01(prm), fila)
    if regla == "V-24":
        return QCoreApplication.translate(
            "Textos", "Proxmox no admite esa etiqueta: usa solo letras, números y guiones."
        )
    if regla.startswith("V-") and not regla.startswith("V-L"):
        base = texto_problema(_a_problema_m1(p))
        if regla == "V-A03" and prm.get("elementos") and base != texto_generico():
            # V-A03 agrupado por etiqueta en un lote por filas: se indica cuántas filas afecta.
            base = QCoreApplication.translate("Textos", "{texto} (afecta a {n} filas)").format(
                texto=base, n=prm["elementos"]
            )
        if p.indice is not None and base != texto_generico():
            if fila is not None:
                return _con_fila(p, base, fila)
            return QCoreApplication.translate("Textos", "Máquina {n}: {texto}").format(
                n=p.indice + 1, texto=base
            )
        return base
    return texto_generico()


def _texto_e_l01(prm: Mapping[str, str]) -> str:
    """E-L01 como problema del plan: sin sitio para alguna máquina."""
    if prm.get("motivo") == "sin_espacio":
        return QCoreApplication.translate(
            "Textos",
            "Ningún nodo tiene sitio para todas las máquinas con el espacio libre actual.",
        )
    return texto_error(ErrorProxLaunch(CodigoError.LOTE_SIN_NODO_APTO))


# --- MVP 3: archivos, perfiles de máquina, lotes guardados e importación CSV --------------


def _lista_filas(filas: str) -> str:
    """«3,9,12» -> «3, 9 y 12» (para V-M10)."""
    partes = [f.strip() for f in filas.split(",") if f.strip()]
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + QCoreApplication.translate("Textos", " y ") + partes[-1]


def _tamano_legible(valor: str | None) -> str:
    """Bytes a «1 MiB» / «256 KiB»; si no es un número, el texto tal cual."""
    try:
        n = int(valor or "")
    except ValueError:
        return valor or "?"
    if n >= 1024 * 1024 and n % (1024 * 1024) == 0:
        return QCoreApplication.translate("Textos", "{n} MiB").format(n=n // (1024 * 1024))
    if n >= 1024:
        return QCoreApplication.translate("Textos", "{n} KiB").format(n=n // 1024)
    return QCoreApplication.translate("Textos", "{n} bytes").format(n=n)


def _texto_e_m10(p: Mapping[str, str]) -> str:
    motivo = p.get("motivo", "")
    if motivo == "falta_nombre":
        texto = QCoreApplication.translate("Textos", "Falta la columna «nombre».")
        if p.get("reconocidas"):
            texto += " " + _fmt(
                QCoreApplication.translate("Textos", "Columnas reconocidas: {reconocidas}."), p
            )
        return texto
    if motivo == "duplicada":
        return _fmt(
            QCoreApplication.translate("Textos", "La columna «{columna}» aparece dos veces."), p
        )
    return _fmt(
        QCoreApplication.translate(
            "Textos", "Hay datos en columnas que no tienen encabezado (columnas {posiciones})."
        ),
        p,
    )


def _motivo_acceso(motivo: str) -> str:
    if motivo == "no_existe":
        return QCoreApplication.translate("Textos", "El archivo no existe.")
    if motivo == "sin_permiso":
        return QCoreApplication.translate("Textos", "No tienes permiso para leer ese archivo.")
    return ""


def _texto_e_m06(p: Mapping[str, str]) -> str:
    tipo = p.get("tipo", "filas")
    maximo = p.get("max", "?")
    n = _entero(p.get(tipo))
    if tipo == "columnas":
        if n is None:
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "El archivo tiene demasiadas columnas; el máximo es {max}."
                ),
                p,
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El archivo tiene %n columnas; el máximo es {max}.", None, n
            ),
            p,
        )
    if tipo == "celda":
        texto = _fmt(
            QCoreApplication.translate(
                "Textos", "Una celda tiene demasiado texto; el máximo es {max} caracteres."
            ),
            p,
        )
        if p.get("fila"):
            texto += " " + _fmt(QCoreApplication.translate("Textos", "(fila {fila})"), p)
        return texto
    if n is None:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El archivo tiene demasiadas filas; el máximo por lote es {max}. Divide el "
                "archivo en partes.",
            ),
            p,
        )
    return _fmt(
        QCoreApplication.translate(
            "Textos",
            "El archivo tiene %n filas; el máximo por lote es {max}. Divide el archivo en partes.",
            None,
            n,
        ),
        p,
        max=maximo,
    )


def _campo_legible_credencial(campo: str) -> str:
    """Nombre en lenguaje llano del campo de texto libre; el técnico si no hay mapeo."""
    if campo == "tipo_cpu":
        return QCoreApplication.translate("Textos", "tipo de CPU")
    if campo == "storage_efi":
        return QCoreApplication.translate("Textos", "almacenamiento del disco EFI")
    if campo == "storage":
        return QCoreApplication.translate("Textos", "almacenamiento")
    if campo == "bridge":
        return QCoreApplication.translate("Textos", "puente de red")
    if campo == "nombre_fila":
        return QCoreApplication.translate("Textos", "nombre de la máquina")
    if campo == "nodo":
        return QCoreApplication.translate("Textos", "nodo")
    if campo == "prefijo":
        return QCoreApplication.translate("Textos", "prefijo")
    if campo == "separador":
        return QCoreApplication.translate("Textos", "separador")
    if campo == "nodos":
        return QCoreApplication.translate("Textos", "nodos")
    if campo == "nombre_maquina":
        return QCoreApplication.translate("Textos", "nombre de la máquina")
    if campo == "version_proxmox":
        return QCoreApplication.translate("Textos", "versión de Proxmox")
    if campo == "descripcion":
        return QCoreApplication.translate("Textos", "descripción")
    if campo == "storage_preferido":
        return QCoreApplication.translate("Textos", "almacenamiento preferido")
    if campo == "bridge_preferido":
        return QCoreApplication.translate("Textos", "puente de red preferido")
    if campo == "storage_efi_preferido":
        return QCoreApplication.translate("Textos", "almacenamiento EFI preferido")
    if campo == "nombre":
        return QCoreApplication.translate("Textos", "nombre")
    return campo


def _texto_e_m08(p: Mapping[str, str]) -> str:
    motivo = p.get("motivo", "")
    if motivo == "credencial":
        # Nunca se muestra el valor, solo el campo que lo contiene.
        campo = _campo_legible_credencial(p.get("campo", ""))
        return QCoreApplication.translate(
            "Textos",
            "No se guardó: el campo «{campo}» parece contener una credencial "
            "(usuario@realm!token). Bórrala y vuelve a guardar.",
        ).format(campo=campo)
    if motivo == "caracteres":
        # Nunca se muestra el valor ni la ruta del campo: solo qué debe corregirse.
        return QCoreApplication.translate(
            "Textos",
            "No se guardó: el nombre de un archivo, almacenamiento o plantilla tiene caracteres "
            "que no se pueden guardar. Usa solo letras sin acentos, números, punto, guion y "
            "guion bajo.",
        )
    if motivo == "sin_espacio":
        causa = QCoreApplication.translate("Textos", "no hay espacio en el disco")
    elif motivo == "sin_permiso":
        causa = QCoreApplication.translate("Textos", "no tienes permiso para escribir ahí")
    elif motivo == "bloqueado":
        causa = QCoreApplication.translate("Textos", "el archivo está abierto en otro programa")
    elif motivo == "ruta_larga":
        causa = QCoreApplication.translate("Textos", "la ruta es demasiado larga")
    else:
        causa = QCoreApplication.translate("Textos", "ocurrió un error al escribir")
    return QCoreApplication.translate(
        "Textos", "No se pudo guardar el archivo: {motivo}. No se cambió nada."
    ).format(motivo=causa)


def _texto_error_archivo(error: ErrorProxLaunch) -> str | None:
    """Mensajes E-M01 a E-M15; ``None`` si el código no es de archivos o perfiles."""
    p = error.params
    c = error.codigo
    if c == CodigoError.ARCHIVO_NO_PERMITIDO:
        motivo = p.get("motivo", "")
        if motivo == "no_regular":
            causa = QCoreApplication.translate("Textos", "no es un archivo normal")
            return QCoreApplication.translate(
                "Textos", "No se puede abrir este archivo: {motivo}."
            ).format(motivo=causa)
        if motivo == "vacio":
            return QCoreApplication.translate(
                "Textos", "No se puede abrir este archivo: está vacío."
            )
        if motivo == "demasiadas_entradas":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "No se puede abrir este archivo: tiene demasiados elementos (máximo {limite}).",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos", "No se puede abrir este archivo: es demasiado grande (límite {limite})."
        ).format(limite=_tamano_legible(p.get("limite")))
    if c == CodigoError.ARCHIVO_FORMATO_AJENO:
        texto = QCoreApplication.translate(
            "Textos", "Este archivo no es un archivo de ProxLaunch del tipo que buscas."
        )
        encontrado = p.get("encontrado", "")
        if encontrado == "proxlaunch.perfiles":
            texto += " " + QCoreApplication.translate(
                "Textos",
                "Parece un archivo de perfiles de máquina; usa «Importar perfiles» "
                "(menú Perfiles › Administrar perfiles… › Importar…).",
            )
        elif encontrado == "proxlaunch.lote":
            texto += " " + QCoreApplication.translate(
                "Textos", "Parece un archivo de lote guardado."
            )
        return texto
    if c == CodigoError.ARCHIVO_VERSION_FUTURA:
        return QCoreApplication.translate(
            "Textos",
            "Este archivo lo creó una versión más nueva de ProxLaunch. Actualiza la aplicación "
            "para abrirlo.",
        )
    if c == CodigoError.ARCHIVO_DANADO:
        campo = p.get("campo", "")
        if campo:
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "El archivo está dañado o tiene datos no válidos: {campo}."
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos", "El archivo está dañado o no tiene un formato válido."
        )
    if c == CodigoError.ARCHIVO_NO_ACCESIBLE:
        base = QCoreApplication.translate(
            "Textos",
            "No se pudo leer el archivo. Si está abierto en otro programa (como Excel), ciérralo "
            "o guarda una copia.",
        )
        extra = _motivo_acceso(p.get("motivo", ""))
        return f"{extra} {base}" if extra else base
    if c == CodigoError.ARCHIVO_DEMASIADAS_FILAS:
        return _texto_e_m06(p)
    if c == CodigoError.CSV_CODIFICACION:
        if p.get("motivo") == "comillas":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Hay unas comillas sin cerrar en la fila {fila}. Revisa el archivo o guárdalo "
                    "de nuevo como «CSV UTF-8» desde Excel.",
                ),
                p,
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No pude leer el archivo CSV (fila {fila}). Guárdalo como «CSV UTF-8» desde Excel.",
            ),
            p,
        )
    if c == CodigoError.ARCHIVO_NO_GUARDABLE:
        return _texto_e_m08(p)
    if c == CodigoError.CSV_VACIO:
        return QCoreApplication.translate("Textos", "El archivo no tiene máquinas.")
    if c == CodigoError.CSV_COLUMNAS:
        return _texto_e_m10(p)
    if c == CodigoError.CSV_VALOR_INVALIDO:
        detalle = _fmt(
            QCoreApplication.translate(
                "Textos", "el valor «{valor}» no es válido. Ejemplo: {ejemplo}."
            ),
            p,
            ejemplo=p.get("ejemplo", "—"),
        )
        return _fmt(
            QCoreApplication.translate("Textos", "Fila {fila}, columna «{columna}»: {detalle}"),
            p,
            detalle=detalle,
        )
    if c == CodigoError.PERFIL_INEXISTENTE:
        texto = _fmt(QCoreApplication.translate("Textos", "No existe el perfil «{nombre}»."), p)
        if p.get("disponibles"):
            texto += " " + _fmt(
                QCoreApplication.translate("Textos", "Perfiles disponibles: {disponibles}."), p
            )
        return texto
    if c == CodigoError.PERFIL_NO_MODIFICABLE:
        return QCoreApplication.translate(
            "Textos",
            "Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.",
        )
    if c == CodigoError.PERFILES_SOLO_LECTURA:
        return QCoreApplication.translate(
            "Textos",
            "Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden "
            "modificar.",
        )
    if c == CodigoError.LOTE_NO_ENCAJA:
        tipo = p.get("campo", "storage")
        valor = p.get("valor", "")
        disponibles = p.get("disponibles", "")
        desajuste = Desajuste(
            TipoDesajuste(tipo)
            if tipo in {t.value for t in TipoDesajuste}
            else TipoDesajuste.STORAGE,
            valor,
            (),
            (),
            tuple(d for d in disponibles.split(",") if d),
        )
        return QCoreApplication.translate(
            "Textos", "Este lote no encaja en este servidor: {detalle}"
        ).format(detalle=texto_desajuste(desajuste))
    if c == CodigoError.PERFIL_RECHAZADO:
        return texto_regla_perfil(p.get("regla", ""), p.get("campo", ""))
    return None


def texto_aviso_pista(aviso: AvisoPista) -> str:
    """Una pista de perfil que no sirvió en este nodo y qué se usó en su lugar (CA-P06)."""
    if aviso.recurso == "bridge":
        pedida = QCoreApplication.translate(
            "Textos", "El perfil pedía la red «{pedido}», que no existe en «{nodo}»."
        )
    elif aviso.recurso == "storage_efi":
        pedida = QCoreApplication.translate(
            "Textos",
            "El perfil pedía el almacenamiento de UEFI «{pedido}», que no existe en «{nodo}».",
        )
    elif aviso.recurso == "fuente":
        pedida = QCoreApplication.translate(
            "Textos",
            "El perfil recordaba «{pedido}» como origen del sistema, pero no está en «{nodo}».",
        )
    else:
        pedida = QCoreApplication.translate(
            "Textos", "El perfil pedía el almacenamiento «{pedido}», que no existe en «{nodo}»."
        )
    texto = pedida.format(pedido=aviso.pedido, nodo=aviso.nodo)
    if aviso.usado:
        texto += " " + QCoreApplication.translate("Textos", "Se usó «{usado}».").format(
            usado=aviso.usado
        )
    else:
        texto += " " + QCoreApplication.translate("Textos", "Elige uno antes de crear.")
    return texto


def _texto_problema_mvp3(p: Problema) -> str | None:
    """Reglas V-M y V-P07 de perfiles, archivos y filas; ``None`` si no es una de ellas."""
    cod = p.codigo
    prm = p.params
    if cod == "V-M01":
        return _fmt(
            QCoreApplication.translate("Textos", "Escribe un nombre de 1 a {maximo} caracteres."),
            prm,
            maximo=prm.get("maximo", str(LONG_NOMBRE_PERFIL)),
        )
    if cod == "V-M01.duplicado":
        return QCoreApplication.translate("Textos", "Ya existe un perfil con ese nombre.")
    if cod == "V-M03":
        return _fmt(
            QCoreApplication.translate("Textos", "Llegaste al máximo de {max} perfiles."),
            prm,
            max=prm.get("max", str(MAX_PERFILES_USUARIO)),
        )
    if cod == "V-M04":
        if p.campo == "descripcion":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "La descripción no es válida: máximo {maximo} caracteres y sin caracteres "
                    "de control.",
                ),
                prm,
                maximo=prm.get("maximo", str(LONG_DESCRIPCION)),
            )
        return QCoreApplication.translate("Textos", "El texto no es válido.")
    if cod == "V-M05":
        return QCoreApplication.translate(
            "Textos", "Parece un token de acceso. No lo escribas aquí."
        )
    if cod == "V-M07":
        return QCoreApplication.translate("Textos", "Falta el nombre.")
    if cod == "V-M10":
        filas = _lista_filas(prm.get("filas", ""))
        if "vmid" in prm:
            return _fmt(
                QCoreApplication.translate(
                    "Textos", "Las filas {filas} tienen el mismo número de máquina «{vmid}»."
                ),
                prm,
                filas=filas,
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Las filas {filas} tienen el mismo nombre «{nombre}»."
            ),
            prm,
            filas=filas,
        )
    if cod == "V-P07.version":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Este perfil requiere Proxmox {version} o superior."
            ),
            prm,
        )
    if cod == "V-P07.cpu_host":
        return QCoreApplication.translate(
            "Textos",
            "El tipo de CPU «host» impide mover la máquina entre nodos con procesadores distintos.",
        )
    return None


def textos_perfiles_fabrica() -> dict[str, tuple[str, str]]:
    """Nombre y descripción traducibles de los perfiles de fábrica (el núcleo no tiene textos)."""
    return {
        "fabrica.servidor-pequeno": (
            QCoreApplication.translate("PerfilesFabrica", "Servidor pequeño"),
            QCoreApplication.translate("PerfilesFabrica", "Para pruebas y servicios ligeros."),
        ),
        "fabrica.servidor-mediano": (
            QCoreApplication.translate("PerfilesFabrica", "Servidor mediano"),
            QCoreApplication.translate("PerfilesFabrica", "Para aplicaciones web."),
        ),
        "fabrica.base-de-datos": (
            QCoreApplication.translate("PerfilesFabrica", "Base de datos"),
            QCoreApplication.translate("PerfilesFabrica", "Para bases de datos."),
        ),
        "fabrica.servidor-grande": (
            QCoreApplication.translate("PerfilesFabrica", "Servidor grande"),
            QCoreApplication.translate("PerfilesFabrica", "Para cargas pesadas."),
        ),
        "fabrica.escritorio-compatible": (
            QCoreApplication.translate("PerfilesFabrica", "Escritorio (hardware compatible)"),
            QCoreApplication.translate(
                "PerfilesFabrica",
                "Para sistemas que aún no traen controladores virtio: disco SATA y tarjeta de "
                "red Intel E1000.",
            ),
        ),
        "fabrica.minimo": (
            QCoreApplication.translate("PerfilesFabrica", "Mínimo"),
            QCoreApplication.translate("PerfilesFabrica", "Disco y red básicos, para probar."),
        ),
        "fabrica.windows-11": (
            QCoreApplication.translate("PerfilesFabrica", "Windows 11 (escritorio)"),
            QCoreApplication.translate(
                "PerfilesFabrica",
                "Para instalar Windows 11: arranque UEFI, TPM y agente de QEMU. El ISO se elige "
                "después.",
            ),
        ),
        "fabrica.windows-server": (
            QCoreApplication.translate("PerfilesFabrica", "Windows Server"),
            QCoreApplication.translate(
                "PerfilesFabrica",
                "Para instalar Windows Server 2022 o 2025: arranque UEFI, TPM y agente de "
                "QEMU. El ISO se elige después.",
            ),
        ),
        "fabrica.linux-red-hat": (
            QCoreApplication.translate("PerfilesFabrica", "Linux (Red Hat y otros)"),
            QCoreApplication.translate(
                "PerfilesFabrica",
                "Para instalar Linux, en especial Red Hat, Rocky o Alma. El ISO se elige después.",
            ),
        ),
    }


def alias_columnas_csv() -> dict[str, str]:
    """Encabezados del idioma activo -> columna canónica, para ``resolver_columnas``.

    El parser acepta siempre los encabezados canónicos; además acepta estos (RNF-M04). En
    español coinciden con los canónicos, así que no añaden nada nuevo.
    """
    return {
        QCoreApplication.translate("ColumnasCsv", "nombre"): "nombre",
        QCoreApplication.translate("ColumnasCsv", "perfil"): "perfil",
        QCoreApplication.translate("ColumnasCsv", "vmid"): "vmid",
        QCoreApplication.translate("ColumnasCsv", "nodo"): "nodo",
        QCoreApplication.translate("ColumnasCsv", "cpu"): "cpu",
        QCoreApplication.translate("ColumnasCsv", "sockets"): "sockets",
        QCoreApplication.translate("ColumnasCsv", "memoria"): "memoria",
        QCoreApplication.translate("ColumnasCsv", "disco"): "disco",
        QCoreApplication.translate("ColumnasCsv", "almacenamiento"): "almacenamiento",
        QCoreApplication.translate("ColumnasCsv", "red"): "red",
        QCoreApplication.translate("ColumnasCsv", "vlan"): "vlan",
        QCoreApplication.translate("ColumnasCsv", "modelo_red"): "modelo_red",
        QCoreApplication.translate("ColumnasCsv", "firmware"): "firmware",
        QCoreApplication.translate("ColumnasCsv", "tipo_cpu"): "tipo_cpu",
        QCoreApplication.translate("ColumnasCsv", "origen"): "origen",
        QCoreApplication.translate("ColumnasCsv", "fuente"): "fuente",
        QCoreApplication.translate("ColumnasCsv", "so"): "so",
        QCoreApplication.translate("ColumnasCsv", "virtio"): "virtio",
        QCoreApplication.translate("ColumnasCsv", "modo_clon"): "modo_clon",
        QCoreApplication.translate("ColumnasCsv", "encender"): "encender",
        QCoreApplication.translate("ColumnasCsv", "arranque_auto"): "arranque_auto",
        QCoreApplication.translate("ColumnasCsv", "notas"): "notas",
        QCoreApplication.translate("ColumnasCsv", "etiquetas"): "etiquetas",
        QCoreApplication.translate("ColumnasCsv", "pool"): "pool",
        QCoreApplication.translate("ColumnasCsv", "proteger"): "proteger",
        QCoreApplication.translate("ColumnasCsv", "mtu"): "mtu",
        QCoreApplication.translate("ColumnasCsv", "limite_red"): "limite_red",
        # Fase B (RF-B6.3). ``ci_contrasena`` no admite alias traducidos (lista cerrada, DT-B13).
        QCoreApplication.translate("ColumnasCsv", "ci_usuario"): "ci_usuario",
        QCoreApplication.translate("ColumnasCsv", "ci_claves"): "ci_claves",
        QCoreApplication.translate("ColumnasCsv", "ci_ip"): "ci_ip",
        QCoreApplication.translate("ColumnasCsv", "ci_puerta"): "ci_puerta",
        QCoreApplication.translate("ColumnasCsv", "ci_dns"): "ci_dns",
        QCoreApplication.translate("ColumnasCsv", "ci_dominio"): "ci_dominio",
        QCoreApplication.translate("ColumnasCsv", "ci_actualizar"): "ci_actualizar",
        QCoreApplication.translate("ColumnasCsv", "ci_snippet_usuario"): "ci_snippet_usuario",
        QCoreApplication.translate("ColumnasCsv", "ci_snippet_vendor"): "ci_snippet_vendor",
        QCoreApplication.translate("ColumnasCsv", "ci_snippet_red"): "ci_snippet_red",
        QCoreApplication.translate("ColumnasCsv", "ci_snippet_meta"): "ci_snippet_meta",
        QCoreApplication.translate("ColumnasCsv", "esperar_ip"): "esperar_ip",
    }


# --- Textos de archivos, perfiles y filas de CSV (única fuente; antes en F4a) ---------------


def texto_motivo_campo(motivo: MotivoCampo) -> str:
    """Motivo de un campo inválido de un archivo, en lenguaje llano."""
    textos: dict[MotivoCampo, Callable[[], str]] = {
        MotivoCampo.REQUERIDO: lambda: QCoreApplication.translate("Textos", "falta"),
        MotivoCampo.TIPO: lambda: QCoreApplication.translate("Textos", "tipo de dato incorrecto"),
        MotivoCampo.RANGO: lambda: QCoreApplication.translate("Textos", "fuera de rango"),
        MotivoCampo.LONGITUD: lambda: QCoreApplication.translate("Textos", "longitud no válida"),
        MotivoCampo.ENUM: lambda: QCoreApplication.translate("Textos", "valor no admitido"),
        MotivoCampo.TEXTO_NO_VALIDO: lambda: QCoreApplication.translate(
            "Textos", "texto no válido"
        ),
        MotivoCampo.TOKEN: lambda: QCoreApplication.translate(
            "Textos", "parece un token de acceso"
        ),
        MotivoCampo.DEMASIADOS: lambda: QCoreApplication.translate("Textos", "hay demasiados"),
        MotivoCampo.DUPLICADO: lambda: QCoreApplication.translate("Textos", "está repetido"),
    }
    return textos[motivo]()


def texto_error_campo(error: ErrorCampo) -> str:
    """Una línea «ruta: motivo» para la lista de campos con problemas."""
    return f"{error.ruta or '·'}: {texto_motivo_campo(error.motivo)}"


def texto_aviso_archivo(aviso: AvisoArchivo) -> str:
    """Aviso no bloqueante al leer un archivo (nunca incluye valores del usuario)."""
    p = aviso.params
    c = aviso.codigo
    columna = p.get("columna", "")
    if c == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS:
        n = _entero_o(p.get("n"), 1)
        if n == 1:
            return QCoreApplication.translate(
                "Textos", "Se ignoró 1 campo que ProxLaunch no conoce."
            )
        return QCoreApplication.translate(
            "Textos", "Se ignoraron %n campos que ProxLaunch no conoce.", None, n
        )
    if c == CodigoAvisoArchivo.CREDENCIAL_IGNORADA:
        return QCoreApplication.translate(
            "Textos",
            "El archivo traía datos que parecen una credencial. No se usaron. "
            "Si eran reales, cámbialas.",
        )
    if c == CodigoAvisoArchivo.MIGRADO:
        return QCoreApplication.translate(
            "Textos",
            "El archivo era de la versión {desde} del formato y se convirtió a la {hasta}.",
        ).format(desde=p.get("desde", "?"), hasta=p.get("hasta", "?"))
    if c == CodigoAvisoArchivo.CSV_CON_CONTRASENAS:
        return QCoreApplication.translate(
            "Textos",
            "Este CSV contiene contraseñas en texto claro. Bórralo cuando termines; ProxLaunch "
            "no las guarda.",
        )
    if c == CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA:
        return QCoreApplication.translate(
            "Textos",
            "Este lote usaba una contraseña de cloud-init y no se guardó. Vuelve a escribirla "
            "antes de crear las máquinas.",
        )
    if c == CodigoAvisoArchivo.COLUMNA_NO_USADA:
        return QCoreApplication.translate(
            "Textos", "La columna «{columna}» no se usa y se ignoró."
        ).format(columna=columna)
    if c == CodigoAvisoArchivo.GIB_ASUMIDO:
        return QCoreApplication.translate(
            "Textos",
            "En la columna «{columna}» había números sin unidad: se entendieron como GiB.",
        ).format(columna=columna)
    if c == CodigoAvisoArchivo.DECIMAL_COMA:
        return QCoreApplication.translate(
            "Textos", "En la columna «{columna}» se usó la coma como separador decimal."
        ).format(columna=columna)
    return QCoreApplication.translate(
        "Textos", "En la columna «{columna}», «GB» se tomó como GiB (1 GB = 1024 MiB)."
    ).format(columna=columna)


def _entero_o(valor: str | None, defecto: int) -> int:
    try:
        return int(valor) if valor is not None else defecto
    except ValueError:
        return defecto


def texto_regla_perfil(regla: str, campo: str = "") -> str:
    """Mensaje de una regla de perfil o de nombre (V-M01..V-M05 y reglas de capa 1)."""
    if regla == "V-M01":
        return QCoreApplication.translate(
            "Textos", "Escribe un nombre de 1 a {maximo} caracteres."
        ).format(maximo=LONG_NOMBRE_PERFIL)
    if regla == "V-M01.duplicado":
        return QCoreApplication.translate(
            "Textos", "Ya existe un perfil con ese nombre. Elige otro."
        )
    if regla == "V-M02":
        return QCoreApplication.translate("Textos", "El identificador del perfil no es válido.")
    if regla == "V-M03":
        return QCoreApplication.translate(
            "Textos", "Llegaste al máximo de {maximo} perfiles. Elimina alguno para crear otro."
        ).format(maximo=MAX_PERFILES_USUARIO)
    if regla == "V-M04":
        return QCoreApplication.translate(
            "Textos", "El texto de «{campo}» no es válido. No uses caracteres especiales."
        ).format(campo=campo or "·")
    if regla == "V-M05":
        return QCoreApplication.translate(
            "Textos", "Parece un token de acceso. No lo escribas aquí."
        )
    return texto_problema(Problema(campo, regla, Severidad.ERROR, {}))


def texto_fallo(error: ErrorProxLaunch) -> str:
    """Mensaje de un error al operar con archivos o perfiles, listo para mostrar.

    Añade la lista de campos con problemas a un archivo dañado (E-M04, CA-G03.3) y traduce
    los rechazos internos del almacén de perfiles; el resto va a ``texto_error``.
    """
    if error.codigo == CodigoError.PERFIL_RECHAZADO:
        return texto_regla_perfil(error.params.get("regla", ""), error.params.get("campo", ""))
    base = texto_error(error)
    if isinstance(error, ErrorArchivo) and error.errores:
        maximo = 10
        lineas = [texto_error_campo(e) for e in error.errores[:maximo]]
        resto = len(error.errores) - maximo
        if resto > 0:
            lineas.append(QCoreApplication.translate("Textos", "y %n más", None, resto))
        return base + "\n\n" + "\n".join(lineas)
    return base


def texto_resumen_perfil(config: ConfigPerfil) -> str:
    """«2 núcleos · 4 GiB · 1 disco de 40 GiB» en lenguaje llano (CA-P09.1, CA-P11.2)."""
    r = resumen_perfil(config)
    if r.vcpus == 1:
        nucleos = QCoreApplication.translate("Textos", "1 núcleo")
    else:
        nucleos = QCoreApplication.translate("Textos", "%n núcleos", None, r.vcpus)
    mib = r.memoria_mib
    memoria = f"{mib // 1024} GiB" if mib % 1024 == 0 else f"{mib} MiB"
    if not r.discos_gib:
        disco = QCoreApplication.translate("Textos", "sin disco")
    elif len(r.discos_gib) == 1:
        disco = QCoreApplication.translate("Textos", "1 disco de {gib} GiB").format(
            gib=r.discos_gib[0]
        )
    else:
        disco = QCoreApplication.translate(
            "Textos", "%n discos", None, len(r.discos_gib)
        ) + QCoreApplication.translate("Textos", " ({gib} GiB en total)").format(
            gib=sum(r.discos_gib)
        )
    return f"{nucleos} · {memoria} · {disco}"


SIMBOLO_ESTADO: dict[EstadoFila, str] = {
    EstadoFila.CORRECTA: "✔",
    EstadoFila.CON_AVISO: "⚠",
    EstadoFila.CON_ERROR: "✖",
}


def texto_estado_fila(estado: EstadoFila) -> str:
    """Nombre del estado de una fila, sin símbolo."""
    if estado == EstadoFila.CORRECTA:
        return QCoreApplication.translate("Textos", "Correcta")
    if estado == EstadoFila.CON_AVISO:
        return QCoreApplication.translate("Textos", "Con aviso")
    return QCoreApplication.translate("Textos", "Con error")


def texto_estado_con_simbolo(estado: EstadoFila) -> str:
    """«✔ Correcta», «⚠ Con aviso» o «✖ Con error»."""
    return f"{SIMBOLO_ESTADO[estado]} {texto_estado_fila(estado)}"


def _texto_v_m08(p: ProblemaCelda) -> str:
    prm = p.params
    if prm.get("motivo") == "ambos":
        return QCoreApplication.translate(
            "Textos",
            "«{valor}» mezcla punto y coma. Escribe el número sin separador de miles, "
            "por ejemplo 1000.",
        ).format(valor=prm.get("valor", p.valor))
    return QCoreApplication.translate(
        "Textos", "¿Quisiste decir mil o uno? Escribe {mil} o {uno}."
    ).format(mil=prm.get("mil", "1000"), uno=prm.get("uno", "1"))


def _texto_valor_no_admitido(p: ProblemaCelda) -> str:
    prm = p.params
    motivo = prm.get("motivo")
    if motivo == "texto":
        return QCoreApplication.translate(
            "Textos",
            "El texto de «{columna}» no es válido. No uses caracteres especiales.",
        ).format(columna=p.columna or "·")
    if motivo == "token":
        return QCoreApplication.translate(
            "Textos",
            "El texto de «{columna}» parece un token de acceso y no se usa. Quítalo de la celda.",
        ).format(columna=p.columna or "·")
    if motivo == "longitud":
        return QCoreApplication.translate(
            "Textos", "El texto de «{columna}» es demasiado largo."
        ).format(columna=p.columna or "·")
    if motivo == "sin_disco_principal":
        return QCoreApplication.translate(
            "Textos", "Indicaste un almacenamiento, pero la fila no tiene disco."
        )
    if motivo == "sin_disco":
        return QCoreApplication.translate(
            "Textos", "Indicaste un almacenamiento, pero falta el tamaño de ese disco."
        )
    return QCoreApplication.translate(
        "Textos", "«{valor}» no es un valor válido. Valores válidos: {validos}."
    ).format(valor=p.valor, validos=prm.get("validos", prm.get("ejemplo", "")))


def _texto_pista(p: ProblemaCelda) -> str:
    prm = p.params
    return texto_aviso_pista(
        AvisoPista(
            p.regla.partition(".")[2],
            prm.get("pedido", ""),
            prm.get("usado") or None,
            prm.get("nodo", ""),
        )
    )


def texto_problema_celda(p: ProblemaCelda, columnas: MapaColumnas | None = None) -> str:
    """Mensaje del problema de una celda, sin número de fila ni columna (CA-C05.1/C05.9).

    ``columnas`` permite saber qué campo del formulario originó una regla V-xx cuando el texto
    depende de él (por ejemplo V-05 con sockets o con núcleos).
    """
    regla = p.regla
    prm = p.params
    if regla == "V-M06":
        if prm.get("motivo") == "ambiguo":
            return QCoreApplication.translate(
                "Textos",
                "Hay más de un perfil llamado «{nombre}». Escribe el nombre exacto.",
            ).format(nombre=prm.get("nombre", p.valor))
        return QCoreApplication.translate(
            "Textos",
            "No existe el perfil «{nombre}». Perfiles disponibles: {disponibles}.",
        ).format(nombre=prm.get("nombre", p.valor), disponibles=prm.get("disponibles", ""))
    if regla == "V-M07":
        return QCoreApplication.translate("Textos", "Falta el nombre.")
    if regla == "V-M08":
        return _texto_v_m08(p)
    if regla == "V-M09":
        return QCoreApplication.translate(
            "Textos", "Pides {gib} GiB de memoria. ¿Querías MiB?"
        ).format(gib=prm.get("gib", "?"))
    if regla == "V-M10":
        if "vmid" in prm:
            return QCoreApplication.translate(
                "Textos", "Las filas {filas} tienen el mismo número de máquina «{valor}»."
            ).format(filas=prm.get("filas", ""), valor=prm.get("vmid", p.valor))
        return QCoreApplication.translate(
            "Textos", "Las filas {filas} tienen el mismo nombre «{valor}»."
        ).format(filas=prm.get("filas", ""), valor=prm.get("nombre", p.valor))
    if regla == "V-M11":
        return QCoreApplication.translate("Textos", "Parece una fila de ejemplo de la plantilla.")
    if regla == "E-M11.no_numero":
        return QCoreApplication.translate(
            "Textos", "«{valor}» no es un número. Escribe, por ejemplo, {ejemplo}."
        ).format(valor=p.valor, ejemplo=prm.get("ejemplo", "2"))
    if regla == "E-M11.no_entero":
        return QCoreApplication.translate(
            "Textos", "«{valor}» no es un número entero. Escribe, por ejemplo, {ejemplo}."
        ).format(valor=p.valor, ejemplo=prm.get("ejemplo", "2"))
    if regla == "E-M11.mib_no_entero":
        return QCoreApplication.translate(
            "Textos",
            "«{valor}» no da una cantidad entera de MiB. Escribe, por ejemplo, {ejemplo}.",
        ).format(valor=p.valor, ejemplo=prm.get("ejemplo", "1024 MiB"))
    if regla == "E-M11.gib_no_entero":
        return QCoreApplication.translate(
            "Textos",
            "«{valor}» no da una cantidad entera de GiB. Escribe, por ejemplo, {ejemplo}.",
        ).format(valor=p.valor, ejemplo=prm.get("ejemplo", "40"))
    if regla == "E-M11.unidad":
        return QCoreApplication.translate(
            "Textos", "«{unidad}» no es una unidad válida. Usa {validas}."
        ).format(unidad=prm.get("unidad", p.valor), validas=prm.get("validas", "MiB, GiB, TiB"))
    if regla == "E-M11.valor_no_admitido":
        return _texto_valor_no_admitido(p)
    if regla in ("pista.storage", "pista.storage_efi", "pista.bridge", "pista.fuente"):
        return _texto_pista(p)
    if regla == "E-O14":
        return texto_error(ErrorProxLaunch(CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA))
    if regla == "E-O21":
        return texto_error(ErrorProxLaunch(CodigoError.FUENTE_ES_URL))
    if regla == "V-L11":
        return QCoreApplication.translate(
            "Textos", "Ningún nodo del servidor puede alojar esta máquina."
        )
    if regla == "V-04":
        if prm.get("motivo") == "no_existe":
            return QCoreApplication.translate("Textos", "El nodo no existe en este servidor.")
        if prm.get("motivo") == "sin_conexion":
            return QCoreApplication.translate("Textos", "El nodo está sin conexión.")
    campo = ""
    if columnas is not None and p.columna is not None:
        if p.columna == columnas.encabezados.get("sockets"):
            campo = "sockets"
        elif p.columna == columnas.encabezados.get("cpu"):
            campo = "cores"
    return texto_problema(Problema(campo, regla, p.severidad, dict(p.params)))


def texto_linea_problema(p: ProblemaCelda, columnas: MapaColumnas | None = None) -> str:
    """«Fila 7, columna «memoria»: «abc» no es un número. Escribe, por ejemplo, 4.» (CA-C05.1)."""
    detalle = _con_punto(texto_problema_celda(p, columnas))
    if p.columna:
        return QCoreApplication.translate(
            "Textos", "Fila {fila}, columna «{columna}»: {detalle}"
        ).format(fila=p.fila, columna=p.columna, detalle=detalle)
    return QCoreApplication.translate("Textos", "Fila {fila}: {detalle}").format(
        fila=p.fila, detalle=detalle
    )


def traductor_para_archivo(columnas: MapaColumnas) -> Callable[[ProblemaCelda], str]:
    """``traducir`` de ``escribir_filas_con_error``: «columna»: detalle (RF-C12)."""

    def traducir(p: ProblemaCelda) -> str:
        detalle = _con_punto(texto_problema_celda(p, columnas))
        return f"«{p.columna}»: {detalle}" if p.columna else detalle

    return traducir


def texto_desajuste(d: Desajuste) -> str:
    """Descripción llana de un valor de un lote cargado que el servidor no tiene (E-M15)."""
    if d.tipo == TipoDesajuste.STORAGE:
        return QCoreApplication.translate(
            "Textos", "El almacenamiento «{valor}» no existe en este servidor o no admite discos."
        ).format(valor=d.valor)
    if d.tipo == TipoDesajuste.STORAGE_EFI:
        return QCoreApplication.translate(
            "Textos",
            "El almacenamiento «{valor}» para la configuración UEFI no existe en este "
            "servidor o no admite discos.",
        ).format(valor=d.valor)
    if d.tipo == TipoDesajuste.BRIDGE:
        return QCoreApplication.translate(
            "Textos", "La red «{valor}» no existe en este servidor."
        ).format(valor=d.valor)
    if d.tipo == TipoDesajuste.ISO:
        return QCoreApplication.translate(
            "Textos", "El ISO «{valor}» no está en este servidor."
        ).format(valor=d.valor)
    if d.tipo == TipoDesajuste.DRIVERS:
        return QCoreApplication.translate(
            "Textos", "El CD de drivers «{valor}» no está en este servidor."
        ).format(valor=d.valor)
    if d.tipo == TipoDesajuste.IMAGEN:
        return QCoreApplication.translate(
            "Textos", "La imagen de disco «{valor}» no está en este servidor."
        ).format(valor=d.valor)
    if d.tipo == TipoDesajuste.PLANTILLA:
        return QCoreApplication.translate(
            "Textos", "La plantilla «{valor}» no existe en este servidor."
        ).format(valor=d.valor)
    return QCoreApplication.translate(
        "Textos", "El nodo «{valor}» no existe o está sin conexión."
    ).format(valor=d.valor)


# --- MVP 4: origen del sistema operativo ----------------------------------------------------
#
# Todo lo que sigue traduce códigos del núcleo (vías, estados, errores E-O, reglas V-O, avisos)
# a lenguaje llano. Nunca se muestran URL completas, rutas locales ni huellas (INV-O6).


# Cualquier cosa con forma de URL (también codificada); espejo de la defensa final de
# ``nucleo.transferencias.url.ocultar_url``, que necesita la URL exacta y aquí no se conoce.
_RE_URL = re.compile(r"(?i)https?(?::|%3A)(?://|%2F%2F)[^\s'\"<>)]*")


def texto_sin_urls(texto: str) -> str:
    """Sustituye toda dirección web de ``texto`` por «(dirección web)» (INV-O6).

    Defensa en profundidad para textos de terceros (mensajes del servidor, detalles técnicos):
    el núcleo ya oculta la URL de las descargas con ``ocultar_url``; aquí nunca se muestra una
    dirección completa, sin importar de dónde venga el texto.
    """
    return _RE_URL.sub(QCoreApplication.translate("Textos", "(dirección web)"), texto)


def _unir_y(partes: list[str]) -> str:
    """«a», «a y b», «a, b y c»."""
    partes = [x for x in partes if x]
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + QCoreApplication.translate("Textos", " y ") + partes[-1]


def texto_tamano_bytes(valor: int | str | None) -> str:
    """Bytes a «350 MiB» / «1,2 GiB»; «?» si no es un número."""
    try:
        n = int(valor) if valor is not None and valor != "" else None
    except (TypeError, ValueError):
        n = None
    if n is None or n < 0:
        return "?"
    unidades = (
        QCoreApplication.translate("Textos", "bytes"),
        "KiB",
        "MiB",
        "GiB",
        "TiB",
    )
    cantidad = float(n)
    i = 0
    while cantidad >= 1024 and i < len(unidades) - 1:
        cantidad /= 1024
        i += 1
    if i == 0:
        return f"{n} {unidades[0]}"
    texto = QLocale().toString(cantidad, "f", 0 if cantidad >= 100 else 1)
    separador = QLocale().decimalPoint()
    if texto.endswith(separador + "0"):
        texto = texto[: -len(separador) - 1]
    return f"{texto} {unidades[i]}"


def _duracion_corta(segundos: float) -> str:
    total = max(0, round(segundos))
    if total < 60:
        return QCoreApplication.translate("Textos", "{s} s").format(s=total)
    if total < 3600:
        return QCoreApplication.translate("Textos", "{m} min {s} s").format(
            m=total // 60, s=total % 60
        )
    return QCoreApplication.translate("Textos", "{h} h {m} min").format(
        h=total // 3600, m=(total % 3600) // 60
    )


def texto_contenido(contenido: Contenido | str) -> str:
    """Qué guarda un almacenamiento, en plural y llano: «imágenes ISO»."""
    valor = str(contenido)
    if valor == Contenido.ISO:
        return QCoreApplication.translate("Textos", "imágenes ISO")
    if valor == Contenido.IMPORT:
        return QCoreApplication.translate("Textos", "imágenes de disco para importar")
    if valor == Contenido.IMAGENES:
        return QCoreApplication.translate("Textos", "discos de máquinas")
    return QCoreApplication.translate("Textos", "ese tipo de archivos")


def texto_origen(origen: OrigenSO) -> str:
    """Nombre largo del origen del sistema operativo (selector del formulario)."""
    if origen == OrigenSO.ISO:
        return QCoreApplication.translate("Textos", "Instalar desde un ISO")
    if origen == OrigenSO.IMPORTAR_DISCO:
        return QCoreApplication.translate("Textos", "Importar un disco existente")
    if origen == OrigenSO.CLONAR_PLANTILLA:
        return QCoreApplication.translate("Textos", "Clonar una plantilla de Proxmox")
    return QCoreApplication.translate("Textos", "Disco vacío (sin sistema)")


def texto_origen_corto(origen: OrigenSO) -> str:
    """Nombre corto del origen para tablas e informes."""
    if origen == OrigenSO.ISO:
        return QCoreApplication.translate("Textos", "ISO")
    if origen == OrigenSO.IMPORTAR_DISCO:
        return QCoreApplication.translate("Textos", "Disco importado")
    if origen == OrigenSO.CLONAR_PLANTILLA:
        return QCoreApplication.translate("Textos", "Clon")
    return QCoreApplication.translate("Textos", "Disco vacío")


def texto_tipo_so(tipo: TipoSO) -> str:
    """Nombre del sistema operativo del asistente."""
    if tipo == TipoSO.LINUX:
        return QCoreApplication.translate("Textos", "Linux")
    if tipo == TipoSO.WINDOWS_11:
        return QCoreApplication.translate("Textos", "Windows 11")
    if tipo == TipoSO.WINDOWS_SERVER_2022_2025:
        return QCoreApplication.translate("Textos", "Windows Server 2022 / 2025")
    if tipo == TipoSO.WINDOWS_10:
        return QCoreApplication.translate("Textos", "Windows 10")
    if tipo == TipoSO.WINDOWS_SERVER_2016_2019:
        return QCoreApplication.translate("Textos", "Windows Server 2016 / 2019")
    return QCoreApplication.translate("Textos", "Otro sistema")


def texto_modo_clon(modo: ModoClon, *, avanzado: bool = False) -> str:
    """Nombre del modo de clonado: en básico «Rápido y ligero» / «Copia independiente»."""
    if avanzado:
        if modo == ModoClon.ENLAZADO:
            return QCoreApplication.translate("Textos", "Enlazado")
        if modo == ModoClon.COMPLETO:
            return QCoreApplication.translate("Textos", "Completo")
        return QCoreApplication.translate("Textos", "Automático")
    if modo == ModoClon.COMPLETO:
        return QCoreApplication.translate("Textos", "Copia independiente")
    if modo == ModoClon.ENLAZADO:
        return QCoreApplication.translate("Textos", "Rápido y ligero")
    return QCoreApplication.translate("Textos", "Rápido y ligero (recomendado)")


_ACCIONES_VIA: dict[str, Callable[[], str]] = {
    "iso": lambda: QCoreApplication.translate("Textos", "usar un ISO del servidor"),
    "subir_iso": lambda: QCoreApplication.translate("Textos", "subir un ISO"),
    "descargar_url": lambda: QCoreApplication.translate(
        "Textos", "descargar un ISO desde una dirección web"
    ),
    "importar": lambda: QCoreApplication.translate("Textos", "importar un disco"),
    "subir_imagen": lambda: QCoreApplication.translate("Textos", "subir una imagen de disco"),
    "descargar_imagen": lambda: QCoreApplication.translate(
        "Textos", "descargar una imagen de disco desde una dirección web"
    ),
    "clonar": lambda: QCoreApplication.translate("Textos", "clonar la plantilla"),
    "orden_arranque": lambda: QCoreApplication.translate("Textos", "fijar el orden de arranque"),
    "ampliar_disco": lambda: QCoreApplication.translate("Textos", "ampliar el disco"),
    "config": lambda: QCoreApplication.translate("Textos", "ajustar la máquina"),
    "resize": lambda: QCoreApplication.translate("Textos", "ampliar el disco"),
}


def texto_accion_via(via: Via | str) -> str:
    """La acción de una vía como frase para «… para {acción}»: «subir un ISO»."""
    fabrica = _ACCIONES_VIA.get(str(via))
    if fabrica is not None:
        return fabrica()
    return QCoreApplication.translate("Textos", "hacer esta acción")


def texto_via(via: Via) -> str:
    """Nombre de una vía de origen como opción de menú o fila de la tabla de capacidades."""
    nombres: dict[str, Callable[[], str]] = {
        "iso": lambda: QCoreApplication.translate("Textos", "Usar un ISO del servidor"),
        "subir_iso": lambda: QCoreApplication.translate("Textos", "Subir un ISO desde tu equipo"),
        "descargar_url": lambda: QCoreApplication.translate(
            "Textos", "Descargar un ISO desde una dirección web"
        ),
        "importar": lambda: QCoreApplication.translate("Textos", "Importar un disco del servidor"),
        "subir_imagen": lambda: QCoreApplication.translate(
            "Textos", "Subir una imagen de disco desde tu equipo"
        ),
        "descargar_imagen": lambda: QCoreApplication.translate(
            "Textos", "Descargar una imagen de disco desde una dirección web"
        ),
        "clonar": lambda: QCoreApplication.translate("Textos", "Clonar una plantilla"),
        "orden_arranque": lambda: QCoreApplication.translate(
            "Textos", "Fijar el orden de arranque"
        ),
        "ampliar_disco": lambda: QCoreApplication.translate("Textos", "Ampliar el disco"),
    }
    fabrica = nombres.get(str(via))
    return fabrica() if fabrica is not None else str(via)


def texto_disponibilidad(disponibilidad: Disponibilidad) -> str:
    """Si una vía se puede usar: «Disponible», «No disponible» o «Disponible, sin confirmar»."""
    if disponibilidad == Disponibilidad.SI:
        return QCoreApplication.translate("Textos", "Disponible")
    if disponibilidad == Disponibilidad.CON_AVISO:
        return QCoreApplication.translate("Textos", "Disponible, sin poder confirmar tus permisos")
    return QCoreApplication.translate("Textos", "No disponible")


def texto_estado_via(estado: EstadoVia) -> str:
    """Por qué una vía está (o no) disponible, en lenguaje llano.

    Con ``Disponibilidad.NO`` explica la causa y qué hacer; con ``CON_AVISO`` dice que no se
    pudieron comprobar los permisos; con ``SI`` solo confirma que se puede usar.
    """
    if estado.disponibilidad == Disponibilidad.SI:
        return QCoreApplication.translate("Textos", "Disponible.")
    if estado.disponibilidad == Disponibilidad.CON_AVISO:
        return QCoreApplication.translate(
            "Textos",
            "No pudimos comprobar tus permisos. Puedes intentarlo; si falta alguno, "
            "ProxLaunch te dirá cuál.",
        )
    if estado.codigo is not None:
        return texto_error(ErrorProxLaunch(estado.codigo, dict(estado.params)))
    if estado.params.get("motivo") == "sin_storage_iso":
        return QCoreApplication.translate(
            "Textos",
            "Ningún almacenamiento de este servidor guarda imágenes ISO. Pide a tu administrador "
            "que active el contenido «ISO» en uno.",
        )
    return QCoreApplication.translate("Textos", "No disponible.")


def texto_tipo_decision(tipo: TipoDecision) -> str:
    """Resumen corto de qué se hizo con el almacenamiento de un tipo de archivo."""
    if tipo == TipoDecision.UNICO:
        return QCoreApplication.translate("Textos", "Es el único almacenamiento que sirve")
    if tipo == TipoDecision.RECORDADO:
        return QCoreApplication.translate("Textos", "El que usaste la vez anterior")
    if tipo == TipoDecision.PREGUNTAR:
        return QCoreApplication.translate("Textos", "Hay que elegir uno")
    if tipo == TipoDecision.RECORDADO_NO_DISPONIBLE:
        return QCoreApplication.translate("Textos", "El que usabas ya no está disponible")
    return QCoreApplication.translate("Textos", "Ningún almacenamiento sirve")


def texto_decision_storage(decision: DecisionStorage, contenido: Contenido | str) -> str:
    """Mensaje completo de la decisión del almacenamiento (E-O04 si el recordado ya no sirve)."""
    if decision.tipo == TipoDecision.RECORDADO_NO_DISPONIBLE:
        return texto_error(
            ErrorProxLaunch(
                CodigoError.STORAGE_RECORDADO_NO_DISPONIBLE,
                {"storage": decision.recordado or "", "contenido": str(contenido)},
            )
        )
    if decision.tipo == TipoDecision.SIN_CANDIDATOS:
        return QCoreApplication.translate(
            "Textos",
            "Ningún almacenamiento activo de este servidor guarda {contenido}. Pide a tu "
            "administrador que lo active en uno.",
        ).format(contenido=texto_contenido(contenido))
    if decision.tipo == TipoDecision.PREGUNTAR:
        return QCoreApplication.translate(
            "Textos", "Elige el almacenamiento donde guardar {contenido}."
        ).format(contenido=texto_contenido(contenido))
    return texto_tipo_decision(decision.tipo)


# --- Transferencias -----------------------------------------------------------------------


def texto_tipo_transferencia(tipo: TipoTransferencia) -> str:
    if tipo == TipoTransferencia.SUBIDA:
        return QCoreApplication.translate("Textos", "Subida desde tu equipo")
    return QCoreApplication.translate("Textos", "Descarga en el servidor")


def texto_estado_transferencia(estado: EstadoTransferencia) -> str:
    """Nombre corto del estado de una transferencia."""
    nombres = {
        EstadoTransferencia.CALCULANDO_HUELLA: QCoreApplication.translate(
            "Textos", "Calculando la huella del archivo"
        ),
        EstadoTransferencia.COMPROBANDO: QCoreApplication.translate(
            "Textos", "Comprobando el destino"
        ),
        EstadoTransferencia.TRANSFIRIENDO: QCoreApplication.translate("Textos", "Enviando"),
        EstadoTransferencia.ESPERANDO_SERVIDOR: QCoreApplication.translate(
            "Textos", "Esperando al servidor"
        ),
        EstadoTransferencia.VERIFICANDO: QCoreApplication.translate("Textos", "Verificando"),
        EstadoTransferencia.TERMINADA: QCoreApplication.translate("Textos", "Terminada"),
        EstadoTransferencia.CANCELADA: QCoreApplication.translate("Textos", "Cancelada"),
        EstadoTransferencia.FALLIDA: QCoreApplication.translate("Textos", "Falló"),
        EstadoTransferencia.SIN_ESPERAR: QCoreApplication.translate("Textos", "Dejaste de esperar"),
    }
    return nombres.get(estado, str(estado))


def texto_progreso_transferencia(progreso: Progreso) -> str:
    """Línea de progreso: «Enviando: 120 MiB de 1,2 GiB (10 %) · 45 MiB/s · quedan 2 min 5 s».

    Sin porcentaje inventado: solo se muestra el que sale de bytes reales o el que informa el
    servidor.
    """
    estado = progreso.estado
    base = texto_estado_transferencia(estado)
    if estado in (
        EstadoTransferencia.CALCULANDO_HUELLA,
        EstadoTransferencia.TRANSFIRIENDO,
        EstadoTransferencia.ESPERANDO_SERVIDOR,
    ):
        partes: list[str] = []
        total = progreso.total_bytes
        if total and progreso.hechos_bytes > 0:
            pct = min(100, int(progreso.hechos_bytes * 100 / total))
            partes.append(
                QCoreApplication.translate("Textos", "{hechos} de {total} ({pct} %)").format(
                    hechos=texto_tamano_bytes(progreso.hechos_bytes),
                    total=texto_tamano_bytes(total),
                    pct=pct,
                )
            )
        elif progreso.porcentaje_servidor is not None:
            partes.append(
                QCoreApplication.translate("Textos", "{pct} %").format(
                    pct=int(progreso.porcentaje_servidor)
                )
            )
        elif total:
            partes.append(
                QCoreApplication.translate("Textos", "{total} en total").format(
                    total=texto_tamano_bytes(total)
                )
            )
        if estado == EstadoTransferencia.TRANSFIRIENDO and progreso.velocidad_bps:
            partes.append(
                QCoreApplication.translate("Textos", "{v}/s").format(
                    v=texto_tamano_bytes(int(progreso.velocidad_bps))
                )
            )
            if progreso.restante_s is not None:
                partes.append(
                    QCoreApplication.translate("Textos", "quedan {t}").format(
                        t=_duracion_corta(progreso.restante_s)
                    )
                )
        if partes:
            return f"{base}: " + " · ".join(partes)
    return base


def texto_quedo_archivo(quedo: bool | None) -> str:
    """Qué pasó con el archivo del servidor tras cancelar o fallar (la app no puede borrarlo)."""
    if quedo is True:
        return QCoreApplication.translate(
            "Textos",
            "Quedó un archivo incompleto en el servidor. ProxLaunch no puede borrarlo: pídele a "
            "tu administrador que lo elimine.",
        )
    if quedo is False:
        return QCoreApplication.translate("Textos", "No quedó ningún archivo en el servidor.")
    return QCoreApplication.translate(
        "Textos",
        "No sabemos si quedó un archivo incompleto en el servidor. Revisa el almacenamiento en "
        "Proxmox.",
    )


def texto_registro_transferencia(r: RegistroTransferencia) -> str:
    """Una línea del registro de la sesión; sin URL, sin ruta local y sin huella (INV-O6)."""
    partes = [
        texto_tipo_transferencia(r.tipo),
        r.nombre_archivo,
        QCoreApplication.translate("Textos", "en «{storage}» ({nodo})").format(
            storage=r.storage, nodo=r.nodo
        ),
    ]
    if r.tamano_bytes is not None:
        partes.append(texto_tamano_bytes(r.tamano_bytes))
    partes.append(r.hora_local)
    partes.append(texto_estado_transferencia(r.estado))
    return " · ".join(p for p in partes if p)


def texto_aviso_archivo_local(codigo: str) -> str:
    """Aviso (no bloqueante) al elegir un archivo de tu equipo para subir."""
    if codigo == "no_iso9660":
        return QCoreApplication.translate(
            "Textos",
            "Este archivo no parece un ISO de instalación normal. Puedes subirlo, pero revisa "
            "que sea el correcto.",
        )
    if codigo == "raw_sin_verificar":
        return QCoreApplication.translate(
            "Textos",
            "ProxLaunch no puede comprobar el contenido de un disco raw. Asegúrate de que es "
            "el archivo que quieres importar.",
        )
    return ""


def texto_motivo_url(motivo: str) -> str:
    """Por qué una dirección web no sirve (V-O11), sin repetir la dirección."""
    textos = {
        "vacia": QCoreApplication.translate(
            "Textos", "Escribe una dirección web completa que empiece por https://."
        ),
        "larga": QCoreApplication.translate("Textos", "La dirección web es demasiado larga."),
        "caracteres": QCoreApplication.translate(
            "Textos", "La dirección web tiene espacios o caracteres no admitidos."
        ),
        "esquema": QCoreApplication.translate(
            "Textos", "Escribe una dirección web completa que empiece por https://."
        ),
        "solo_https": QCoreApplication.translate(
            "Textos",
            "Solo se admiten direcciones seguras (https://). Una dirección http:// no está "
            "protegida y solo se permite en el modo avanzado, con confirmación.",
        ),
        "sin_host": QCoreApplication.translate(
            "Textos", "A la dirección web le falta el nombre del servidor."
        ),
        "credenciales": QCoreApplication.translate(
            "Textos",
            "La dirección web no debe llevar usuario ni contraseña. Quítalos de la dirección.",
        ),
        "puerto": QCoreApplication.translate(
            "Textos", "El puerto de la dirección web no es válido."
        ),
    }
    return textos.get(
        motivo, QCoreApplication.translate("Textos", "La dirección web no es válida.")
    )


def texto_motivo_checksum(motivo: str) -> str:
    """Por qué una huella (checksum) no sirve (V-O12)."""
    if motivo == "vacio":
        return QCoreApplication.translate("Textos", "Escribe la huella del archivo.")
    return QCoreApplication.translate(
        "Textos",
        "La huella no tiene un formato válido: son solo números y letras de la A a la F "
        "(por ejemplo, 64 caracteres para SHA-256).",
    )


def texto_motivo_nombre_archivo(motivo: str, contenido: Contenido | str = Contenido.ISO) -> str:
    """Por qué un nombre de archivo no sirve para subirlo o descargarlo (V-O09)."""
    if motivo == "ruta_absoluta":
        return texto_error(ErrorProxLaunch(CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA))
    if motivo == "extension":
        if str(contenido) == Contenido.IMPORT:
            return QCoreApplication.translate(
                "Textos", "El nombre debe terminar en qcow2, raw o vmdk."
            )
        return QCoreApplication.translate("Textos", "El nombre debe terminar en iso o img.")
    if motivo == "reservado":
        return QCoreApplication.translate(
            "Textos", "Ese nombre está reservado por Windows. Elige otro."
        )
    if motivo == "forma":
        return QCoreApplication.translate(
            "Textos", "El nombre debe tener entre 1 y 100 caracteres."
        )
    return QCoreApplication.translate(
        "Textos",
        "Usa solo letras sin acentos, números, punto, guion y guion bajo, y no empieces por "
        "un punto.",
    )


# --- Asistente de sistema operativo -----------------------------------------------------


def _valor_asistente(campo: CampoAsistente, valor: str) -> str:
    """Valor de un cambio del asistente en lenguaje llano."""
    if campo in (CampoAsistente.TPM, CampoAsistente.AGENTE):
        if valor == "si":
            return QCoreApplication.translate("Textos", "sí")
        if valor == "no":
            return QCoreApplication.translate("Textos", "no")
    if campo == CampoAsistente.FIRMWARE:
        if valor == "seabios":
            return QCoreApplication.translate("Textos", "SeaBIOS (clásico)")
        if valor == "ovmf":
            return QCoreApplication.translate("Textos", "UEFI (OVMF)")
    if campo == CampoAsistente.BUS_DISCO:
        return valor.upper()
    if campo == CampoAsistente.MODELO_RED:
        return ", ".join("VirtIO" if v == "virtio" else v for v in valor.split(",") if v)
    return valor


def texto_cambio_asistente(cambio: CambioAsistente) -> str:
    """Una línea «Arranque: SeaBIOS (clásico) → UEFI (OVMF)» de lo que cambió el asistente."""
    campo = cambio.campo
    if campo == CampoAsistente.FIRMWARE:
        titulo = QCoreApplication.translate("Textos", "Arranque")
    elif campo == CampoAsistente.TPM:
        titulo = QCoreApplication.translate("Textos", "TPM 2.0")
    elif campo == CampoAsistente.CONTROLADOR:
        titulo = QCoreApplication.translate("Textos", "Controlador de discos")
    elif campo == CampoAsistente.MODELO_RED:
        titulo = QCoreApplication.translate("Textos", "Tarjeta de red")
    elif campo == CampoAsistente.BUS_DISCO:
        titulo = QCoreApplication.translate("Textos", "Conexión del primer disco")
    else:
        titulo = QCoreApplication.translate("Textos", "Agente de QEMU")
    return QCoreApplication.translate("Textos", "{campo}: {antes} → {despues}").format(
        campo=titulo,
        antes=_valor_asistente(campo, cambio.antes),
        despues=_valor_asistente(campo, cambio.despues),
    )


# --- Ajustes tras clonar, avisos de la máquina y fuente del origen --------------------------


def _ajuste_verbo(ajuste: str) -> str:
    """El ajuste como acción: «ampliar el disco»."""
    if ajuste == "etiquetas":
        return QCoreApplication.translate("Textos", "poner las etiquetas")
    if ajuste == "cpu_memoria":
        return QCoreApplication.translate("Textos", "cambiar los procesadores o la memoria")
    if ajuste == "disco":
        return QCoreApplication.translate("Textos", "ampliar el disco")
    if ajuste == "arranque":
        return QCoreApplication.translate("Textos", "configurar el arranque con el servidor")
    if ajuste == "proteccion":
        return QCoreApplication.translate("Textos", "activar la protección contra borrado")
    if ajuste == "cloudinit":
        return QCoreApplication.translate("Textos", "aplicar la configuración inicial (cloud-init)")
    if ajuste == "contrasena":
        return QCoreApplication.translate("Textos", "poner la contraseña de cloud-init")
    return QCoreApplication.translate("Textos", "aplicar los ajustes")


def _ajuste_sustantivo(ajuste: str) -> str:
    """El ajuste como cosa pendiente: «el tamaño del disco»."""
    if ajuste == "etiquetas":
        return QCoreApplication.translate("Textos", "las etiquetas")
    if ajuste == "cpu_memoria":
        return QCoreApplication.translate("Textos", "los procesadores o la memoria")
    if ajuste == "disco":
        return QCoreApplication.translate("Textos", "el tamaño del disco")
    if ajuste == "arranque":
        return QCoreApplication.translate("Textos", "el arranque con el servidor")
    if ajuste == "proteccion":
        return QCoreApplication.translate("Textos", "la protección contra borrado")
    if ajuste == "cloudinit":
        return QCoreApplication.translate("Textos", "la configuración inicial (cloud-init)")
    if ajuste == "contrasena":
        return QCoreApplication.translate("Textos", "la contraseña de cloud-init")
    return QCoreApplication.translate("Textos", "los ajustes")


def texto_aviso_origen(codigo: str) -> str:
    """Texto de un código de aviso de una máquina del libro del MVP 4 (vacío si no se conoce).

    Códigos: ``ajuste_pendiente:<ajuste>``, ``ajuste_omitido:disco``, ``ajustes_reintentados``
    y ``discos_sueltos_posibles``.
    """
    base, _, detalle = codigo.partition(":")
    texto_fase_a = _texto_aviso_fase_a(codigo)
    if texto_fase_a:
        return texto_fase_a
    texto_fase_b = _texto_aviso_fase_b(codigo)
    if texto_fase_b:
        return texto_fase_b
    if base == "ajuste_pendiente":
        return QCoreApplication.translate(
            "Textos", "Se creó, pero falta aplicar {ajuste}. Puedes reintentar los ajustes."
        ).format(ajuste=_ajuste_sustantivo(detalle))
    if base == "ajuste_omitido":
        return QCoreApplication.translate(
            "Textos",
            "No se amplió el disco: no pudimos comprobar que tengas el permiso VM.Config.Disk. "
            "Amplíalo en Proxmox si lo necesitas.",
        )
    if codigo == "ajustes_reintentados":
        return QCoreApplication.translate(
            "Textos", "Se aplicaron los ajustes que faltaban al reintentar."
        )
    if codigo == "discos_sueltos_posibles":
        return QCoreApplication.translate(
            "Textos",
            "La importación falló después de enviarse; pueden haber quedado discos sueltos en el "
            "almacenamiento. Revísalos en Proxmox.",
        )
    return ""


def texto_fuente_origen(cfg: ConfiguracionVM) -> str:
    """De dónde sale el sistema de una máquina: nombre del ISO, la imagen o la plantilla.

    Nunca una dirección web ni una ruta local. Vacío si el origen es un disco vacío.
    """
    det = cfg.detalle_origen
    if isinstance(det, DetalleIso):
        return det.iso.volid or det.iso.nombre
    if isinstance(det, DetalleImportacion):
        return det.imagen.volid or det.imagen.nombre
    if isinstance(det, DetalleClon):
        return det.plantilla.nombre or (
            "" if det.plantilla.vmid is None else str(det.plantilla.vmid)
        )
    return ""


def texto_ajustes_clon(cfg: ConfiguracionVM) -> str:
    """Ajustes pedidos sobre la plantilla, en una línea; «igual que la plantilla» si no hay."""
    det = cfg.detalle_origen
    if not isinstance(det, DetalleClon):
        return ""
    a = det.ajustes
    partes: list[str] = []
    if a.sockets is not None and a.cores is not None:
        partes.append(
            QCoreApplication.translate("Textos", "{n} procesadores").format(n=a.sockets * a.cores)
        )
    elif a.cores is not None:
        partes.append(QCoreApplication.translate("Textos", "{n} núcleos").format(n=a.cores))
    elif a.sockets is not None:
        partes.append(QCoreApplication.translate("Textos", "{n} sockets").format(n=a.sockets))
    if a.tipo_cpu is not None:
        partes.append(QCoreApplication.translate("Textos", "CPU {t}").format(t=a.tipo_cpu))
    if a.memoria_mib is not None:
        partes.append(
            QCoreApplication.translate("Textos", "{m} de memoria").format(
                m=texto_tamano_bytes(a.memoria_mib * 1024 * 1024)
            )
        )
    if a.disco_gib is not None:
        partes.append(
            QCoreApplication.translate("Textos", "disco de {g} GiB").format(g=a.disco_gib)
        )
    if not partes:
        return QCoreApplication.translate("Textos", "igual que la plantilla")
    return ", ".join(partes)


def texto_resumen_origen(cfg: ConfiguracionVM) -> str:
    """«ISO: local:iso/alpine.iso (Linux)» o «Clon: web-base (Rápido y ligero)»; vacío si no hay."""
    if cfg.origen == OrigenSO.DISCO_VACIO:
        return ""
    texto = texto_origen_corto(cfg.origen)
    fuente = texto_fuente_origen(cfg)
    if fuente:
        texto += f": {fuente}"
    detalles: list[str] = []
    if cfg.origen != OrigenSO.CLONAR_PLANTILLA and cfg.tipo_so is not None:
        detalles.append(texto_tipo_so(cfg.tipo_so))
    det = cfg.detalle_origen
    if isinstance(det, DetalleClon):
        detalles.append(texto_modo_clon(det.modo_efectivo or det.modo, avanzado=True))
        detalles.append(texto_ajustes_clon(cfg))
    elif isinstance(det, DetalleImportacion) and det.ampliar_a_gib is not None:
        detalles.append(
            QCoreApplication.translate("Textos", "ampliado a {g} GiB").format(g=det.ampliar_a_gib)
        )
    detalles = [d for d in detalles if d]
    if detalles:
        texto += " (" + ", ".join(detalles) + ")"
    return texto


# --- Errores E-O ----------------------------------------------------------------------------


def _texto_permiso_con_via(p: Mapping[str, str]) -> str:
    """E-O20: permiso que falta para una acción concreta (extiende CA-L18.9)."""
    accion = texto_accion_via(p.get("via", ""))
    if not p.get("privilegio"):
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Tu usuario no tiene permiso para {accion}. Pide a tu administrador este permiso "
                "o usa un token con permisos suficientes.",
            ),
            accion=accion,
        )
    if p.get("desconocido") == "1":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No pudimos comprobar tus permisos. Para {accion} hace falta {privilegio} en "
                "«{ruta}»; sin poder confirmarlo, esta opción no se usa.",
            ),
            p,
            accion=accion,
        )
    if p.get("inferido") == "1":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Proxmox no permitió {accion}. Lo más probable es que a tu usuario le falte "
                "{privilegio} en «{ruta}». Pídeselo a tu administrador.",
            ),
            p,
            accion=accion,
        )
    return _fmt(
        QCoreApplication.translate(
            "Textos",
            "Falta el permiso {privilegio} en «{ruta}» para {accion}. Pídeselo a tu administrador.",
        ),
        p,
        accion=accion,
    )


def _nombre_campo_cloudinit(campo: str) -> str:
    """Nombre legible de un campo ``cloudinit.*`` (defensa en profundidad del núcleo)."""
    resto = campo.removeprefix("cloudinit.")
    coincidencia = re.fullmatch(r"tarjetas\[(\d+)\]\.(ip|puerta)", resto)
    if coincidencia is not None:
        n = int(coincidencia.group(1)) + 1
        if coincidencia.group(2) == "ip":
            return QCoreApplication.translate("Textos", "la IP de la tarjeta de red {n}").format(
                n=n
            )
        return QCoreApplication.translate(
            "Textos", "la puerta de enlace de la tarjeta de red {n}"
        ).format(n=n)
    if resto.startswith("snippets."):
        return QCoreApplication.translate("Textos", "el script de configuración «{tipo}»").format(
            tipo=texto_tipo_snippet(resto.partition(".")[2])
        )
    nombres: dict[str, Callable[[], str]] = {
        "usuario": lambda: QCoreApplication.translate("Textos", "el usuario"),
        "claves": lambda: QCoreApplication.translate("Textos", "las claves SSH"),
        "dns": lambda: QCoreApplication.translate("Textos", "los servidores DNS"),
        "dominio": lambda: QCoreApplication.translate("Textos", "el dominio de búsqueda"),
        "actualizar": lambda: QCoreApplication.translate(
            "Textos", "la opción de actualizar paquetes"
        ),
        "contrasena": lambda: QCoreApplication.translate("Textos", "la contraseña"),
    }
    fabrica = nombres.get(resto)
    return (
        fabrica()
        if fabrica is not None
        else QCoreApplication.translate("Textos", "un valor de la configuración inicial")
    )


def _texto_parametro_cloudinit(campo: str) -> str:
    return QCoreApplication.translate(
        "Textos",
        "No se envió a Proxmox: {que} de la configuración inicial (cloud-init) no es válido. "
        "Corrígelo en esa sección y vuelve a intentarlo.",
    ).format(que=_nombre_campo_cloudinit(campo))


def _texto_parametro_origen(campo: str) -> str | None:
    """Rechazos de Proxmox que el traductor clasifica por campo (``filename``, ``content``…)."""
    if campo == "filename":
        return QCoreApplication.translate(
            "Textos",
            "Proxmox no aceptó el nombre del archivo. Usa solo letras sin acentos, números, "
            "punto, guion y guion bajo, con la extensión correcta (iso, qcow2, raw o vmdk). Una "
            "imagen de disco debe terminar en .qcow2, .raw, .vmdk u .ova; si es un .img, "
            "renómbralo a .qcow2.",
        )
    if campo == "content":
        return QCoreApplication.translate(
            "Textos",
            "Ese almacenamiento no admite este tipo de archivo. Elige otro almacenamiento o "
            "pide a tu administrador que lo active.",
        )
    if campo == "media":
        return QCoreApplication.translate(
            "Textos",
            "Proxmox no aceptó el ISO como unidad de CD. Comprueba que el archivo sea un ISO y "
            "vuelve a intentarlo.",
        )
    if campo == "size":
        return QCoreApplication.translate(
            "Textos",
            "Los discos solo pueden crecer: elige un tamaño igual o mayor que el actual.",
        )
    return None


def _texto_tipo_fuente(tipo: str) -> str:
    if tipo == "plantilla":
        return QCoreApplication.translate("Textos", "La plantilla")
    if tipo == "imagen":
        return QCoreApplication.translate("Textos", "La imagen de disco")
    if tipo == "drivers":
        return QCoreApplication.translate("Textos", "El CD de drivers")
    if tipo == "iso":
        return QCoreApplication.translate("Textos", "El ISO")
    return QCoreApplication.translate("Textos", "El archivo")


def _texto_motivo_clon(motivo: str, nombre: str) -> str:
    if motivo == "no_compartido":
        return QCoreApplication.translate(
            "Textos",
            "la plantilla está en un almacenamiento que solo existe en su nodo y la máquina "
            "nueva iría a otro",
        )
    if motivo == "sin_images":
        return QCoreApplication.translate(
            "Textos", "el almacenamiento elegido no admite discos de máquinas"
        )
    if motivo == "parametro_enlazado":
        return QCoreApplication.translate(
            "Textos",
            "un clon rápido y ligero no permite elegir almacenamiento ni formato; usa «Copia "
            "independiente»",
        )
    if motivo == "enlazado_no_soportado":
        return QCoreApplication.translate(
            "Textos",
            "el almacenamiento de la plantilla no admite clones rápidos y ligeros; usa «Copia "
            "independiente»",
        )
    if motivo == "bloqueada":
        return QCoreApplication.translate(
            "Textos", "la plantilla está ocupada con otra operación; espera a que termine"
        )
    if motivo == "no_plantilla":
        return QCoreApplication.translate("Textos", "«{nombre}» ya no es una plantilla").format(
            nombre=nombre or QCoreApplication.translate("Textos", "esa máquina")
        )
    if motivo == "tpm_en_marcha":
        return QCoreApplication.translate(
            "Textos", "la plantilla tiene TPM y está encendida; apágala antes de clonar"
        )
    return QCoreApplication.translate("Textos", "Proxmox no lo permite con esta plantilla")


def _texto_motivo_imagen(motivo: str) -> str:
    if motivo == "backing":
        return QCoreApplication.translate(
            "Textos",
            "Este disco depende de otro archivo (un disco base). Conviértelo a un qcow2 "
            "independiente antes de subirlo.",
        )
    if motivo == "cifrado":
        return QCoreApplication.translate(
            "Textos",
            "Este disco está cifrado y Proxmox no puede importarlo. Quítale el cifrado antes de "
            "subirlo.",
        )
    if motivo == "multiarchivo":
        return QCoreApplication.translate(
            "Textos",
            "Este disco está formado por varios archivos. Conviértelo a un solo archivo antes "
            "de subirlo.",
        )
    if motivo == "ova":
        return QCoreApplication.translate(
            "Textos",
            "Un archivo OVA no se puede importar tal cual. Extrae el disco que lleva dentro y "
            "súbelo.",
        )
    if motivo == "version":
        return QCoreApplication.translate(
            "Textos",
            "Esta versión del formato de disco no es compatible. Conviértelo a un qcow2 estándar.",
        )
    if motivo == "truncado":
        return QCoreApplication.translate(
            "Textos",
            "El archivo parece incompleto o dañado. Vuelve a copiarlo o a descargarlo.",
        )
    return QCoreApplication.translate(
        "Textos",
        "Este disco depende de otro archivo, está cifrado o no es un solo archivo. Conviértelo "
        "a un qcow2 independiente antes de subirlo.",
    )


def _texto_error_origen(error: ErrorProxLaunch) -> str | None:
    """Mensajes E-O01 a E-O24; ``None`` si el código no es del origen del sistema operativo."""
    p = error.params
    c = error.codigo
    if c == CodigoError.IMPORTAR_VERSION_NO_SOPORTADA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Tu Proxmox {version} no permite importar discos sin ser administrador del "
                "servidor. Puedes instalar desde un ISO o clonar una plantilla. Desde la "
                "versión 8.4 sí se puede importar.",
            ),
            p,
        )
    if c == CodigoError.IMPORTAR_SIN_STORAGE_IMPORT:
        texto = QCoreApplication.translate(
            "Textos",
            "Para importar discos, pide a tu administrador que active el contenido «Import» en "
            "un almacenamiento de tipo directorio, NFS o CIFS.",
        )
        candidatos = [c for c in p.get("candidatos", "").split(",") if c]
        if candidatos:
            texto += " " + QCoreApplication.translate(
                "Textos", "Podría activarse en: {lista}."
            ).format(lista=", ".join(f"«{c}»" for c in candidatos))
        return texto
    if c == CodigoError.DESCARGA_URL_SIN_PERMISO:
        if p.get("privilegio") == "Sys.AccessNetwork":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Falta el permiso Sys.AccessNetwork en el nodo «{nodo}» para descargar "
                    "desde una dirección web. Pídeselo a tu administrador o descarga el archivo "
                    "en tu equipo y súbelo.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos",
            "Descargar desde una dirección web exige permisos de administrador en esta versión "
            "de Proxmox. Descarga el archivo en tu equipo y súbelo.",
        )
    if c == CodigoError.STORAGE_RECORDADO_NO_DISPONIBLE:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El almacenamiento «{storage}» que usabas en este servidor ya no está "
                "disponible o ya no admite {contenido}. Elige otro.",
            ),
            p,
            contenido=texto_contenido(p.get("contenido", "")),
        )
    if c == CodigoError.CATALOGO_SIN_PERMISO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No puedes ver los archivos de «{storage}»: falta el permiso Datastore.Audit o "
                "Datastore.AllocateSpace.",
            ),
            p,
        )
    if c == CodigoError.TRANSFERENCIA_NO_VERIFICADA:
        return QCoreApplication.translate(
            "Textos",
            "El servidor dice que terminó, pero el archivo no coincide con el que enviaste. No "
            "lo uses.",
        )
    if c == CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA:
        return QCoreApplication.translate(
            "Textos", "El archivo llegó dañado: la huella no coincide. No quedó guardado."
        )
    if c == CodigoError.TRANSFERENCIA_CORTADA:
        texto = QCoreApplication.translate(
            "Textos", "Se cortó la conexión mientras se subía el archivo."
        )
        if p.get("bytes") and p.get("total") and p.get("total") != "0":
            texto += " " + QCoreApplication.translate(
                "Textos", "Se habían enviado {hechos} de {total}."
            ).format(hechos=texto_tamano_bytes(p["bytes"]), total=texto_tamano_bytes(p["total"]))
        return texto
    if c == CodigoError.ARCHIVO_CAMBIO:
        return QCoreApplication.translate(
            "Textos", "El archivo cambió mientras se subía. Vuelve a intentarlo."
        )
    if c == CodigoError.NOMBRE_YA_EXISTE:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Ya existe un archivo llamado «{nombre}» en «{storage}». ProxLaunch no lo "
                "sobrescribe: usa el que ya está o elige otro nombre.",
            ),
            p,
        )
    if c == CodigoError.DESCARGA_URL_FALLIDA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El servidor no pudo descargar {archivo} desde {host}: {motivo}. Prueba a "
                "descargarlo en tu equipo y subirlo.",
            ),
            p,
            motivo=texto_sin_urls(p.get("motivo", ""))
            or QCoreApplication.translate("Textos", "sin más detalles"),
        )
    if c == CodigoError.IMPORTAR_SIN_PERMISO:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Falta el permiso {privilegio} en «{ruta}» para {accion}."
            ),
            p,
            accion=texto_accion_via(p.get("via") or "importar"),
        )
    if c == CodigoError.IMPORTAR_DESTINO_SIN_PERMISO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Para guardar el disco importado necesitas el permiso Datastore.AllocateSpace "
                "en «{storage}».",
            ),
            p,
        )
    if c == CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA:
        return QCoreApplication.translate(
            "Textos",
            "Importar desde una ruta del servidor exige ser administrador (root). Sube el "
            "archivo desde tu equipo.",
        )
    if c == CodigoError.IMAGEN_NO_ADMITIDA:
        return _texto_motivo_imagen(p.get("motivo", ""))
    if c == CodigoError.FUENTE_DESAPARECIO:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "{tipo} «{nombre}» ya no está en el servidor. Elige otra."
            ),
            p,
            tipo=_texto_tipo_fuente(p.get("tipo", "")),
        )
    if c == CodigoError.SIN_PLANTILLAS:
        return QCoreApplication.translate(
            "Textos",
            "No veo ninguna plantilla con tu cuenta. Pide el permiso VM.Audit o crea la "
            "plantilla en Proxmox (clic derecho en la máquina → Convertir en plantilla).",
        )
    if c == CodigoError.CLON_NO_POSIBLE:
        return QCoreApplication.translate("Textos", "No se puede clonar así: {motivo}.").format(
            motivo=_texto_motivo_clon(p.get("motivo", ""), p.get("nombre", ""))
        )
    if c == CodigoError.CLON_ID_OCUPADO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El número de máquina {vmid} se ocupó justo antes de clonar. Vuelve a intentarlo.",
            ),
            p,
        )
    if c == CodigoError.FUENTE_ES_URL:
        return QCoreApplication.translate(
            "Textos",
            "Aquí va el nombre de un archivo del servidor, no una dirección web. Para descargar "
            "usa «Descargar en el servidor».",
        )
    if c == CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA:
        if p.get("ambito") == "raiz":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "El nodo «{nodo}» tiene poco espacio temporal ({libre} libres) para recibir "
                    "un archivo de {tamano}. La subida podría fallar.",
                ),
                p,
                tamano=texto_tamano_bytes(p.get("tamano")),
                libre=texto_tamano_bytes(p.get("libre")),
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El archivo pesa {tamano} y «{storage}» solo tiene {libre} libres."
            ),
            p,
            tamano=texto_tamano_bytes(p.get("tamano")),
            libre=texto_tamano_bytes(p.get("libre")),
        )
    if c == CodigoError.TRANSFERENCIA_EN_CURSO:
        return QCoreApplication.translate(
            "Textos", "Hay una transferencia en curso. Espera a que termine o cancélala."
        )
    if c == CodigoError.AJUSTE_POST_CLON_FALLIDO:
        if p.get("causa") in _CAUSAS_CON_TEXTO_PROPIO:
            # BUG-B-P1-2: el servidor rechazó algo concreto (claves SSH, script): se dice eso.
            return texto_error(
                ErrorProxLaunch(
                    CodigoError(p["causa"]),
                    {k: v for k, v in p.items() if k == "snippet"},
                )
            )
        ajustes = [a for a in p.get("ajuste", "").split(",") if a]
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La máquina «{nombre}» se clonó, pero no se pudo {ajuste}. Puedes reintentar los "
                "ajustes o deshacer.",
            ),
            p,
            ajuste=_unir_y([_ajuste_verbo(a) for a in ajustes]) or _ajuste_verbo(""),
        )
    if c == CodigoError.TRANSFERENCIA_CANCELADA:
        quedo = {"si": True, "no": False}.get(p.get("quedo_archivo", ""))
        return (
            QCoreApplication.translate("Textos", "Transferencia cancelada.")
            + " "
            + texto_quedo_archivo(quedo)
        )
    return None


# --- Reglas V-O -----------------------------------------------------------------------------


def _nombre_fuente_campo(campo: str, regla: str) -> str:
    """«el ISO», «el CD de drivers» o «la imagen de disco» según el campo de la regla."""
    if campo.endswith("drivers"):
        return QCoreApplication.translate("Textos", "el CD de drivers")
    if regla.startswith("V-O03") or campo.endswith("imagen"):
        return QCoreApplication.translate("Textos", "la imagen de disco")
    return QCoreApplication.translate("Textos", "el ISO")


def _texto_v_o_fuente(p: Problema) -> str:
    """V-O02 (ISO, drivers) y V-O03 (imagen): la fuente no sirve o no está."""
    prm = p.params
    motivo = prm.get("motivo", "")
    objeto = _nombre_fuente_campo(p.campo, p.codigo)
    es_imagen = p.codigo.startswith("V-O03")
    if motivo == "ruta_absoluta":
        return texto_error(ErrorProxLaunch(CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA))
    if motivo in ("forma", "caracteres", "extension", "reservado"):
        contenido = Contenido.IMPORT if es_imagen else Contenido.ISO
        return QCoreApplication.translate("Textos", "No se puede usar {objeto}. {causa}").format(
            objeto=objeto, causa=texto_motivo_nombre_archivo(motivo, contenido)
        )
    if motivo == "no_disponible":
        if prm.get("nombre"):
            texto = _fmt(
                QCoreApplication.translate("Textos", "No encuentro «{nombre}» en «{nodo}»."), prm
            )
        else:
            texto = _fmt(
                QCoreApplication.translate("Textos", "No encuentro {objeto} en «{nodo}»."),
                prm,
                objeto=objeto,
            )
        alternativas = [a for a in prm.get("alternativas", "").split(",") if a]
        if alternativas:
            texto += " " + QCoreApplication.translate("Textos", "Disponibles: {lista}.").format(
                lista=", ".join(f"«{a.strip()}»" for a in alternativas)
            )
        return texto
    if motivo == "nombre_no_admitido":
        return QCoreApplication.translate(
            "Textos",
            "Este archivo tiene un nombre que ProxLaunch no admite. Cámbiale el nombre en "
            "Proxmox o elige otro.",
        )
    if motivo == "sin_resolver":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No encuentro «{nombre}» entre los archivos del servidor. Elígelo de la lista.",
            ),
            prm,
        )
    if motivo == "storage_inactivo":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El almacenamiento «{storage}» no está activo en «{nodo}»."
            ),
            prm,
        )
    if motivo == "version":
        return texto_error(
            ErrorProxLaunch(
                CodigoError.IMPORTAR_VERSION_NO_SOPORTADA, {"version": prm.get("version", "")}
            )
        )
    return QCoreApplication.translate("Textos", "Elige {objeto} de la lista.").format(objeto=objeto)


def _texto_v_o01(p: Problema) -> str:
    motivo = p.params.get("motivo", "")
    if motivo == "falta_fuente":
        if p.campo.endswith("imagen"):
            return QCoreApplication.translate("Textos", "Elige una imagen de disco.")
        if p.campo.endswith("plantilla"):
            return QCoreApplication.translate("Textos", "Elige una plantilla.")
        return QCoreApplication.translate("Textos", "Elige un ISO.")
    if motivo == "falta_so":
        return QCoreApplication.translate("Textos", "Elige qué sistema operativo vas a instalar.")
    if motivo == "incoherente":
        return QCoreApplication.translate(
            "Textos", "Los datos del sistema operativo no corresponden al origen elegido."
        )
    return QCoreApplication.translate("Textos", "Falta elegir de dónde sale el sistema operativo.")


def _campo_legible_origen(campo: str) -> str:
    if campo == "tipo_so":
        return QCoreApplication.translate("Textos", "el sistema operativo")
    if campo == "tpm":
        return QCoreApplication.translate("Textos", "el TPM")
    if campo == "agente_qemu":
        return QCoreApplication.translate("Textos", "el agente de QEMU")
    return QCoreApplication.translate("Textos", "el archivo de origen")


def _texto_v_o07(prm: Mapping[str, str], campo: str = "") -> str:
    """Aviso de mínimos de Windows: cada problema dice solo el mínimo que no se cumple."""
    try:
        so = texto_tipo_so(TipoSO(prm.get("tipo_so", "")))
    except ValueError:
        so = QCoreApplication.translate("Textos", "Este sistema")
    if campo == "cores":
        return QCoreApplication.translate("Textos", "{so} pide al menos {cores} núcleos.").format(
            so=so, cores=prm.get("minimo_cores", "?")
        )
    if campo == "memoria_mib":
        memoria = (
            f"{int(prm['minimo_memoria_mib']) / 1024:g}"
            if prm.get("minimo_memoria_mib", "").isdigit()
            else "?"
        )
        return QCoreApplication.translate(
            "Textos", "{so} pide al menos {memoria} GiB de memoria."
        ).format(so=so, memoria=memoria)
    if campo.startswith("discos"):
        return QCoreApplication.translate(
            "Textos", "{so} pide al menos {disco} GiB de disco."
        ).format(so=so, disco=prm.get("minimo_disco_gib", "?"))
    return QCoreApplication.translate(
        "Textos",
        "{so} pide al menos {cores} núcleos, {memoria} GiB de memoria y {disco} GiB de disco.",
    ).format(
        so=so,
        cores=prm.get("minimo_cores", "?"),
        memoria=f"{int(prm['minimo_memoria_mib']) / 1024:g}"
        if prm.get("minimo_memoria_mib", "").isdigit()
        else "?",
        disco=prm.get("minimo_disco_gib", "?"),
    )


def _texto_v_o18(prm: Mapping[str, str]) -> str:
    if prm.get("efecto") == "orden_arranque":
        base = QCoreApplication.translate(
            "Textos",
            "Sin el permiso VM.Config.Disk no se puede fijar el orden de arranque. La máquina se "
            "creará igual; si no arranca desde el ISO, cambia el orden en Proxmox.",
        )
    else:
        base = QCoreApplication.translate(
            "Textos",
            "Sin el permiso VM.Config.Disk no se puede ampliar el disco. La máquina se creará "
            "con el tamaño original.",
        )
    if prm.get("desconocido") == "1":
        base = QCoreApplication.translate("Textos", "No pudimos comprobar tus permisos. ") + base
    return base


def _texto_problema_origen(p: Problema) -> str | None:
    """Reglas V-O01 a V-O31 (docs/requisitos/mvp4.md §7); ``None`` si no es una de ellas."""
    cod = p.codigo
    prm = p.params
    if cod == "V-O01":
        return _texto_v_o01(p)
    if cod == "V-O01.ajeno":
        return QCoreApplication.translate(
            "Textos", "Este origen no usa {dato}: se ignorará."
        ).format(dato=_campo_legible_origen(p.campo))
    if cod in ("V-O02", "V-O03"):
        return _texto_v_o_fuente(p)
    if cod in ("V-O02.ambiguo", "V-O03.ambiguo"):
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Hay más de un archivo llamado «{nombre}» ({volids}). Elige cuál usar.",
            ),
            prm,
        )
    if cod == "V-O02.drivers":
        return QCoreApplication.translate(
            "Textos",
            "Windows necesita los drivers VirtIO y no encuentro ningún ISO «virtio-win» en el "
            "servidor. Sube uno, o elige «Crear sin los drivers» y cárgalos después.",
        )
    if cod == "V-O04":
        return _texto_v_o04(prm)
    if cod == "V-O04.ambiguo":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Hay varias plantillas llamadas «{nombre}» ({plantillas}). Elige una."
            ),
            prm,
        )
    if cod == "V-O05":
        if prm.get("motivo") == "tpm":
            return QCoreApplication.translate("Textos", "Windows 11 exige un TPM 2.0.")
        return QCoreApplication.translate("Textos", "Windows 11 exige arranque UEFI (OVMF).")
    if cod == "V-O05.seabios":
        return QCoreApplication.translate(
            "Textos",
            "Windows funciona con el arranque clásico (SeaBIOS), pero se recomienda UEFI (OVMF).",
        )
    if cod == "V-O05.rhel10":
        if prm.get("coincide_iso") == "0":
            return QCoreApplication.translate(
                "Textos",
                "Si vas a instalar RHEL 10 (o Rocky, Alma, CentOS Stream 10), necesita un "
                "procesador x86-64-v3. Elige ese tipo de CPU o «host».",
            )
        return QCoreApplication.translate(
            "Textos",
            "Este ISO parece de la familia RHEL 10 (Red Hat, Rocky, Alma), que necesita un "
            "procesador x86-64-v3. Con el tipo de CPU actual puede no arrancar: elige "
            "x86-64-v3 o «host».",
        )
    if cod == "V-O06":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Con un ISO solo caben {maximo} discos IDE; usa SCSI o SATA."
            ),
            prm,
            maximo=prm.get("maximo", "2"),
        )
    if cod == "V-O07":
        return _texto_v_o07(prm, p.campo)
    if cod == "V-O08":
        if prm.get("storage"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "No hay un almacenamiento válido para el TPM: «{storage}» en «{nodo}» no "
                    "admite discos de máquinas. Elige otro.",
                ),
                prm,
            )
        return QCoreApplication.translate(
            "Textos", "No hay un almacenamiento válido para el TPM. Elige uno que admita discos."
        )
    if cod in ("V-O13", "V-O13.raiz"):
        return texto_error(
            ErrorProxLaunch(
                CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA,
                {**prm, **({"ambito": "raiz"} if cod == "V-O13.raiz" else {})},
            )
        )
    if cod == "V-O14":
        return texto_error(ErrorProxLaunch(CodigoError.NOMBRE_YA_EXISTE, dict(prm)))
    if cod == "V-O15":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Falta el permiso {privilegio} en «{ruta}» para subir o descargar archivos.",
            ),
            prm,
        )
    if cod == "V-O16":
        return texto_error(ErrorProxLaunch(CodigoError.DESCARGA_URL_SIN_PERMISO, dict(prm)))
    if cod == "V-O17":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "Falta el permiso {privilegio} en «{ruta}» para clonar la plantilla."
            ),
            prm,
        )
    if cod == "V-O18":
        return _texto_v_o18(prm)
    if cod == "V-O19":
        return texto_error(ErrorProxLaunch(CodigoError.IMPORTAR_DESTINO_SIN_PERMISO, dict(prm)))
    if cod == "V-O21":
        if prm.get("motivo") == "storage_destino":
            return QCoreApplication.translate(
                "Textos",
                "Un clon rápido y ligero se guarda en el almacenamiento de la plantilla y no "
                "permite elegir otro. Elige «Copia independiente».",
            )
        return QCoreApplication.translate(
            "Textos",
            "Este almacenamiento no permite clonar de forma rápida y ligera. Elige «Copia "
            "independiente».",
        )
    if cod == "V-O23":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El tamaño del disco debe ser un número entero de GiB entre {minimo} y {maximo}.",
            ),
            prm,
        )
    if cod == "V-O23.tamano":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El disco ya mide {actual_gib} GiB y pediste {pedido_gib} GiB. Los discos solo "
                "pueden crecer.",
            ),
            prm,
        )
    if cod == "V-O24":
        campo = p.campo.rpartition(".")[2]
        texto = texto_problema(Problema(campo, prm.get("regla", ""), p.severidad, {}))
        if texto == texto_generico():
            return QCoreApplication.translate(
                "Textos", "Un valor que pides cambiar en la plantilla no es válido."
            )
        return texto
    if cod == "V-O25":
        return _texto_v_l11(prm)
    if cod == "V-O26":
        return texto_error(ErrorProxLaunch(CodigoError.STORAGE_RECORDADO_NO_DISPONIBLE, dict(prm)))
    if cod == "V-O27":
        return texto_error(ErrorProxLaunch(CodigoError.TRANSFERENCIA_EN_CURSO))
    if cod == "V-O29":
        return QCoreApplication.translate(
            "Textos", "Para importar un disco necesitas un disco donde guardarlo."
        )
    if cod == "V-O29.sindisco":
        return QCoreApplication.translate(
            "Textos",
            "Sin disco no podrás instalar el sistema desde el ISO. Agrega un disco si quieres "
            "instalarlo.",
        )
    if cod == "V-O31":
        # Aviso (no bloquea): el CD de drivers no es el virtio-win que ProxLaunch conoce.
        volid = prm.get("volid", "")
        storage = volid.partition(":")[0] if ":" in volid else ""
        if storage:
            return QCoreApplication.translate(
                "Textos",
                "Se usará el CD de drivers «{volid}» (almacenamiento «{storage}»), que no es la "
                "versión que conoce ProxLaunch. Comprueba que es de confianza antes de crear la "
                "máquina.",
            ).format(volid=volid, storage=storage)
        return QCoreApplication.translate(
            "Textos",
            "Se usará el CD de drivers «{volid}», que no es la versión que conoce ProxLaunch. "
            "Comprueba que es de confianza antes de crear la máquina.",
        ).format(volid=volid)
    return None


def _texto_v_o04(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "no_en_nodo":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La plantilla «{nombre}» no está en el nodo «{nodo}» ni en un almacenamiento "
                "compartido con él.",
            ),
            prm,
        )
    if motivo == "bloqueada":
        return QCoreApplication.translate(
            "Textos", "La plantilla está ocupada con otra operación. Espera a que termine."
        )
    if motivo == "sin_detalle":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "No se pudo leer la configuración de la plantilla «{nombre}»."
            ),
            prm,
        )
    if motivo == "sin_resolver":
        return QCoreApplication.translate("Textos", "Elige una plantilla de la lista.")
    texto = _fmt(QCoreApplication.translate("Textos", "No encuentro la plantilla «{nombre}»."), prm)
    alternativas = [a for a in prm.get("alternativas", "").split(",") if a]
    if alternativas:
        texto += " " + QCoreApplication.translate("Textos", "Disponibles: {lista}.").format(
            lista=", ".join(f"«{a.strip()}»" for a in alternativas)
        )
    return texto


def _texto_v_l11_fuente(prm: Mapping[str, str]) -> str:
    """V-L11 por origen: «pve2» no tiene el ISO / la imagen / el CD de drivers."""
    tipo = prm.get("tipo", "")
    objeto = _texto_tipo_fuente(tipo).lower()
    return _fmt(
        QCoreApplication.translate("Textos", "«{nodo}» no tiene {objeto} «{fuente}»."),
        prm,
        objeto=objeto,
    )


def _texto_v_l11_plantilla(prm: Mapping[str, str]) -> str:
    """V-L11 por origen: «pve2» no tiene la plantilla ni su almacenamiento."""
    if prm.get("storage"):
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{nodo}» no tiene la plantilla «{plantilla}» ni el almacenamiento «{storage}».",
            ),
            prm,
        )
    return _fmt(
        QCoreApplication.translate("Textos", "«{nodo}» no tiene la plantilla «{plantilla}»."),
        prm,
    )


# --- Fase A: Deshacer, CSV y guía (I5b) -------------------------------------------------------


def texto_nombre_opcion_fase_a(opcion: str) -> str:
    """Nombre llano de una opción de la fase A (valor de ``OpcionA``) para los avisos."""
    nombres: dict[str, Callable[[], str]] = {
        "encender": lambda: QCoreApplication.translate("Textos", "Encender al terminar"),
        "arranque_auto": lambda: QCoreApplication.translate("Textos", "Arrancar con el servidor"),
        "arranque_orden": lambda: QCoreApplication.translate(
            "Textos", "Orden y espera de arranque"
        ),
        "notas": lambda: QCoreApplication.translate("Textos", "Notas"),
        "etiquetas": lambda: QCoreApplication.translate("Textos", "Etiquetas"),
        "pool": lambda: QCoreApplication.translate("Textos", "Pool"),
        "mtu": lambda: QCoreApplication.translate("Textos", "MTU de la red"),
        "limite_red": lambda: QCoreApplication.translate("Textos", "Límite de velocidad de red"),
        "proteger": lambda: QCoreApplication.translate("Textos", "Proteger contra borrado"),
        # Fase B (0.7)
        "cloudinit": lambda: QCoreApplication.translate(
            "Textos", "Configuración inicial (cloud-init)"
        ),
        "contrasena": lambda: QCoreApplication.translate("Textos", "Contraseña"),
        "dns_dominio": lambda: QCoreApplication.translate("Textos", "DNS y dominio"),
        "snippets": lambda: QCoreApplication.translate("Textos", "Scripts de configuración"),
        "esperar_ip": lambda: QCoreApplication.translate("Textos", "Esperar la IP"),
        "activar_agente": lambda: QCoreApplication.translate(
            "Textos", "Activar el agente invitado"
        ),
    }
    fabrica = nombres.get(opcion)
    return fabrica() if fabrica is not None else opcion


def _texto_error_fase_a(error: ErrorProxLaunch) -> str | None:
    """Textos de los errores nuevos de la fase A (opciones, pools y Deshacer forzado)."""
    p = error.params
    c = error.codigo
    if c == CodigoError.OPCION_SIN_PRIVILEGIO:
        return _texto_sin_privilegio(p)
    if c == CodigoError.OPCION_SIN_VERSION:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "«{opcion}» necesita Proxmox {version} o una versión posterior."
            ),
            p,
            opcion=texto_nombre_opcion_fase_a(p.get("opcion", "")),
        )
    if c == CodigoError.POOLS_SIN_PERMISO:
        return QCoreApplication.translate(
            "Textos",
            "No puedes ver la lista de pools: falta el privilegio Pool.Audit en «/pool». "
            "Eso no significa que no existan pools; pídeselo a tu administrador.",
        )
    if c == CodigoError.POOLS_DESCONOCIDO:
        return QCoreApplication.translate(
            "Textos",
            "No sabemos si puedes ver la lista de pools (privilegio Pool.Audit en «/pool»). "
            "Si el pool no existe o no tienes acceso, Proxmox lo rechazará al crear.",
        )
    if c == CodigoError.POOLS_ERROR:
        return QCoreApplication.translate(
            "Textos", "No se pudo leer la lista de pools del servidor. Inténtalo de nuevo."
        )
    if c == CodigoError.POOL_INEXISTENTE:
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El pool «{pool}» no existe en Proxmox. No se creó la máquina."
            ),
            p,
        )
    if c == CodigoError.DESCRIPCION_LARGA:
        return QCoreApplication.translate(
            "Textos",
            "Las notas superan los 8192 caracteres que admite Proxmox. Acórtalas y vuelve a "
            "intentarlo.",
        )
    if c == CodigoError.ROLLBACK_PROTEGIDA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{nombre}» está protegida contra borrado. Deshacer puede quitarle la "
                "protección si lo confirmas expresamente.",
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_SIN_POWERMGMT:
        texto = _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{nombre}» está encendida y no se pudo apagar: falta el privilegio "
                "VM.PowerMgmt. Apágala en Proxmox y vuelve a intentarlo.",
            ),
            p,
        )
        if p.get("tambien") == str(CodigoError.ROLLBACK_SIN_OPCIONES):
            texto += " " + QCoreApplication.translate(
                "Textos",
                "También está protegida y falta VM.Config.Options para quitarle la protección.",
            )
        return texto
    if c == CodigoError.ROLLBACK_SIN_OPCIONES:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{nombre}» está protegida y no se pudo desproteger: falta el privilegio "
                "VM.Config.Options. Quita la protección en Proxmox y vuelve a intentarlo.",
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_APAGADO_FALLIDO:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No se pudo apagar «{nombre}», así que no se eliminó. Apágala desde Proxmox "
                "y vuelve a intentarlo.",
            ),
            p,
        )
    if c == CodigoError.ROLLBACK_DESPROTECCION_FALLIDA:
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No se pudo quitar la protección de «{nombre}», así que no se eliminó. "
                "Quítala desde Proxmox y vuelve a intentarlo.",
            ),
            p,
        )
    return None


def texto_acciones_rollback(acciones: tuple[str, ...]) -> str:
    """Acciones hechas sobre una máquina al deshacer: «Apagada a la fuerza, desprotegida…»."""
    nombres = {
        "apagada": lambda: QCoreApplication.translate("Textos", "apagada a la fuerza"),
        "desprotegida": lambda: QCoreApplication.translate("Textos", "desprotegida"),
        "borrada": lambda: QCoreApplication.translate("Textos", "eliminada"),
    }
    partes = [nombres[a]() if a in nombres else a for a in acciones]
    if not partes:
        return ""
    texto = ", ".join(partes)
    return texto[:1].upper() + texto[1:]


def titulo_confirmacion_forzada() -> str:
    """Título del diálogo de confirmación expresa de Deshacer (RF-A6.4)."""
    return QCoreApplication.translate("Textos", "Confirmar Deshacer con apagado o desprotección")


def _lista_maquinas(vmids: Iterable[int], nombres: Mapping[int, str]) -> str:
    """Una línea «  • nombre (VMID n)» por máquina."""
    plantilla = QCoreApplication.translate("Textos", "  • {nombre} (VMID {vmid})")
    return "\n".join(plantilla.format(nombre=nombres.get(v, "?"), vmid=v) for v in vmids)


def texto_confirmacion_forzada(inspeccion: InspeccionRollback) -> str:
    """Confirmación expresa: lista cada máquina que se apagará o desprotegerá (RF-A6.4).

    Indica aparte las que se omitirán por falta de privilegio y las que no se pudieron leer.
    """
    n = inspeccion.nombres
    bloques: list[str] = []
    if inspeccion.encendidas:
        bloques.append(
            QCoreApplication.translate(
                "Textos",
                "Se apagarán a la fuerza estas máquinas encendidas. Se perderán los datos que "
                "no estén guardados:",
            )
            + "\n"
            + _lista_maquinas(inspeccion.encendidas, n)
        )
    if inspeccion.protegidas:
        bloques.append(
            QCoreApplication.translate(
                "Textos", "Se quitará la protección contra borrado a estas máquinas:"
            )
            + "\n"
            + _lista_maquinas(inspeccion.protegidas, n)
        )
        bloques.append(
            QCoreApplication.translate(
                "Textos",
                "Si no se puede quitar la protección de una máquina, no se eliminará y, si "
                "estaba encendida, quedará apagada.",
            )
        )
    if inspeccion.encendidas_sin_privilegio:
        bloques.append(
            QCoreApplication.translate(
                "Textos",
                "Se omitirán porque están encendidas y tu usuario no tiene el privilegio "
                "VM.PowerMgmt para apagarlas:",
            )
            + "\n"
            + _lista_maquinas(inspeccion.encendidas_sin_privilegio, n)
        )
    if inspeccion.protegidas_sin_privilegio:
        bloques.append(
            QCoreApplication.translate(
                "Textos",
                "Se omitirán porque están protegidas y tu usuario no tiene el privilegio "
                "VM.Config.Options para quitarles la protección:",
            )
            + "\n"
            + _lista_maquinas(inspeccion.protegidas_sin_privilegio, n)
        )
    if inspeccion.ilegibles:
        bloques.append(
            QCoreApplication.translate(
                "Textos",
                "No se pudo comprobar el estado de estas máquinas. Si están encendidas o "
                "protegidas se omitirán; si no, se eliminarán:",
            )
            + "\n"
            + _lista_maquinas(inspeccion.ilegibles, n)
        )
    bloques.append(
        QCoreApplication.translate(
            "Textos",
            "Después se eliminarán junto con las demás máquinas que elegiste. Solo se tocan "
            "máquinas creadas por este lote; esto no se puede deshacer.",
        )
        if inspeccion.hay_forzables
        else QCoreApplication.translate(
            "Textos",
            "El resto de las máquinas que elegiste se eliminará como siempre. Solo se tocan "
            "máquinas creadas por este lote; esto no se puede deshacer.",
        )
    )
    return "\n\n".join(bloques)


def texto_casilla_confirmar_forzado() -> str:
    return QCoreApplication.translate(
        "Textos", "Entiendo que se apagarán o desprotegerán máquinas y que puedo perder datos"
    )


def texto_boton_deshacer_forzado() -> str:
    return QCoreApplication.translate("Textos", "Apagar, desproteger y eliminar")


def texto_boton_deshacer_sin_forzar() -> str:
    return QCoreApplication.translate("Textos", "Eliminar sin apagar ni desproteger")


def texto_explicacion_sin_forzar() -> str:
    return QCoreApplication.translate(
        "Textos",
        "Si eliges «Eliminar sin apagar ni desproteger», esas máquinas se omiten y se quedan "
        "en Proxmox; el resto se elimina como siempre.",
    )


def texto_boton_cancelar_deshacer() -> str:
    return QCoreApplication.translate("Textos", "Cancelar")


def texto_inspeccion_fallida() -> str:
    """No se pudo comprobar el estado de las máquinas antes de deshacer."""
    return QCoreApplication.translate(
        "Textos",
        "No se pudo comprobar el estado de las máquinas antes de deshacer. No se eliminó "
        "nada; inténtalo de nuevo.",
    )


def texto_comprobando_antes_de_deshacer() -> str:
    return QCoreApplication.translate("Textos", "Comprobando las máquinas antes de deshacer…")


def texto_detalle_rollback(acciones: tuple[str, ...], error: ErrorProxLaunch | None) -> str:
    """Detalle de una máquina al deshacer: lo hecho (si no es solo borrar) y el motivo si falló.

    CA-A6.4.3: el informe lista por máquina las acciones realizadas y las omitidas con motivo.
    """
    partes: list[str] = []
    if acciones and acciones != ("borrada",):
        partes.append(
            QCoreApplication.translate("Textos", "Hecho: {acciones}.").format(
                acciones=texto_acciones_rollback(acciones).lower()
            )
        )
    if error is not None:
        partes.append(texto_error(error))
    return " ".join(partes)


# --- Fase A: formulario y resúmenes (I5a) ---


def _texto_aviso_fase_a(codigo: str) -> str:
    """Avisos de máquina de la fase A (encendido y ajustes de arranque o protección)."""
    if codigo == "encendido_fallido":
        return QCoreApplication.translate(
            "Textos",
            "Se creó, pero no se pudo encender. Enciéndela desde Proxmox si la necesitas.",
        )
    if codigo == "encendido_omitido":
        return QCoreApplication.translate(
            "Textos",
            "No se encendió: quedaron ajustes por aplicar o su creación se confirmó después "
            "(al comprobarla). Revisa la máquina y, si hace falta, enciéndela desde Proxmox.",
        )
    if codigo == "notas_plantilla_ilegible":
        return QCoreApplication.translate(
            "Textos",
            "No se añadieron las notas de origen: no se pudo leer la descripción de la "
            "plantilla y así no se pisan sus notas.",
        )
    if codigo == "ajuste_pendiente:arranque":
        return QCoreApplication.translate(
            "Textos",
            "Se creó, pero falta aplicar el arranque con el servidor. Puedes reintentar los "
            "ajustes.",
        )
    if codigo == "ajuste_pendiente:proteccion":
        return QCoreApplication.translate(
            "Textos",
            "Se creó, pero falta aplicar la protección contra borrado. Puedes reintentar los "
            "ajustes.",
        )
    return ""


def _texto_v_a03(prm: Mapping[str, str]) -> str:
    """Mensaje de V-A03 (etiqueta rechazada por la política del centro de datos)."""
    motivo = prm.get("motivo", "")
    if motivo == "registrada":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La etiqueta «{etiqueta}» está registrada en el centro de datos y tu "
                "usuario no puede aplicarla (hace falta Sys.Modify en «/»). Pídele a tu "
                "administrador que la aplique o que la quite del registro.",
            ),
            prm,
        )
    if motivo == "ninguna_permitida":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El centro de datos no deja a tu usuario poner etiquetas (política «none») "
                "y esta máquina llevaría «{etiqueta}». Pídele a tu administrador que la "
                "autorice.",
            ),
            prm,
        )
    return _fmt(
        QCoreApplication.translate(
            "Textos",
            "Tu administrador no ha autorizado la etiqueta «{etiqueta}». Pídele que la "
            "añada a las etiquetas permitidas del centro de datos.",
        ),
        prm,
    )


def _texto_problema_fase_a(p: Problema) -> str | None:
    """Mensaje de las reglas V-A01..V-A16 (opciones de la fase A); ``None`` si no es una."""
    cod = p.codigo
    prm = p.params
    if cod == "V-A01":
        campo = (
            QCoreApplication.translate("Textos", "La espera de arranque")
            if p.campo == "arranque_espera"
            else QCoreApplication.translate("Textos", "El orden de arranque")
        )
        return _fmt(
            QCoreApplication.translate("Textos", "{campo} debe ser un número entero de 0 o más."),
            prm,
            campo=campo,
        )
    if cod == "V-A02":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La etiqueta «{etiqueta}» no es válida: usa minúsculas, números, «_», «-», «+» "
                "y «.», sin espacios, y empieza por una letra, un número o «_» (máximo 128 "
                "caracteres).",
            ),
            prm,
        )
    if cod == "V-A03":
        base = _texto_v_a03(prm)
        if prm.get("incierto"):
            # QA-A-10: sin saber si el usuario tiene Sys.Modify, la política es solo un aviso.
            base += " " + QCoreApplication.translate(
                "Textos",
                "No se pudieron leer tus permisos, así que quizá Proxmox sí la acepte.",
            )
        return base
    if cod == "V-A04":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El MTU de la tarjeta {tarjeta} debe ser «Igual al bridge» o un número entre "
                "576 y 65520.",
            ),
            prm,
        )
    if cod == "V-A05":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El MTU de la tarjeta {tarjeta} solo se aplica a tarjetas VirtIO. Elige "
                "VirtIO o deja el MTU en «Heredar del bridge».",
            ),
            prm,
        )
    if cod == "V-A06":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El límite de velocidad de la tarjeta {tarjeta} debe ser un número mayor que "
                "0 y no superior a 1 000 000 000 (en MB/s).",
            ),
            prm,
        )
    if cod == "V-A07":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Las notas ocupan {total} caracteres y Proxmox admite {limite}: sobran "
                "{sobran}. Acórtalas.",
            ),
            prm,
        )
    if cod == "V-A08":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Las notas ocupan {total} de los {limite} caracteres que admite Proxmox: "
                "queda poco espacio.",
            ),
            prm,
        )
    if cod == "V-A09":
        return QCoreApplication.translate(
            "Textos",
            "No se pudo leer la política de etiquetas del centro de datos, así que no se pudo "
            "comprobar si tus etiquetas están permitidas. Si Proxmox las rechaza, la máquina "
            "no se creará.",
        )
    if cod == "V-A10":
        return _fmt(
            QCoreApplication.translate("Textos", "El pool «{pool}» no existe en este servidor."),
            prm,
        )
    if cod == "V-A11":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No se pudo comprobar que el pool «{pool}» exista (no se puede leer la lista "
                "de pools). Proxmox lo verificará al crear.",
            ),
            prm,
        )
    if cod == "V-A12":
        sin_version = prm.get("motivo") == str(CodigoError.OPCION_SIN_VERSION)
        error = ErrorProxLaunch(
            CodigoError.OPCION_SIN_VERSION if sin_version else CodigoError.OPCION_SIN_PRIVILEGIO,
            dict(prm),
        )
        return texto_error(error)
    if cod == "V-A13":
        return QCoreApplication.translate(
            "Textos",
            "No se pudo leer la descripción de la plantilla: no se añadirán las notas para no "
            "pisar las suyas.",
        )
    if cod == "V-A14":
        return QCoreApplication.translate(
            "Textos",
            "Las notas tienen caracteres de control (no imprimibles): se eliminarán al crear.",
        )
    if cod == "V-A16":
        return QCoreApplication.translate(
            "Textos",
            "El nombre del pool no es válido: usa letras, números, «_» y «-», y «/» para "
            "separar pools anidados (hasta 3 niveles).",
        )
    if cod == "V-A15":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Para crear la máquina en el pool «{pool}» falta el privilegio VM.Allocate en "
                "«{ruta}» o en «{ruta_pool}».",
            ),
            prm,
        )
    return None


def texto_estado_opcion(estado: EstadoOpcion) -> str:
    """Por qué una opción de la fase A está deshabilitada o con reservas (vacío si está libre).

    Nombra el privilegio y la ruta (o la versión de Proxmox) que faltan.
    """
    if estado.disponibilidad == Disponibilidad.SI:
        return ""
    if estado.codigo is not None:
        return texto_error(ErrorProxLaunch(estado.codigo, dict(estado.params)))
    motivo = estado.params.get("motivo")
    texto_b = _texto_motivo_opcion_b(motivo or "")
    if texto_b:
        return texto_b
    if motivo == "sin_pools":
        return QCoreApplication.translate("Textos", "No hay pools en este servidor.")
    if motivo == "no_leido":
        return QCoreApplication.translate(
            "Textos", "Todavía no se leyó la lista de pools del servidor."
        )
    return QCoreApplication.translate("Textos", "No disponible.")


def texto_opcion_restablecida(opcion: str, motivo: str) -> str:
    """Aviso de que una opción volvió a su valor por defecto (CL-A15): «motivo» explica por qué."""
    texto = QCoreApplication.translate(
        "Textos", "Se restableció «{opcion}» a su valor por defecto."
    ).format(opcion=texto_nombre_opcion_fase_a(opcion))
    return f"{texto} {motivo}".strip()


def texto_mtu_solo_virtio() -> str:
    return QCoreApplication.translate(
        "Textos", "El MTU solo se aplica a tarjetas VirtIO: con otra tarjeta queda en «Heredar»."
    )


def texto_si_no(valor: bool) -> str:
    return (
        QCoreApplication.translate("Textos", "sí")
        if valor
        else QCoreApplication.translate("Textos", "no")
    )


def texto_mtu(mtu: int | None) -> str:
    """MTU de una tarjeta como lo ve el usuario («Heredar del bridge», «Igual al bridge», 1500)."""
    if mtu is None:
        return QCoreApplication.translate("Textos", "Heredar del bridge")
    if mtu == 1:
        return QCoreApplication.translate("Textos", "Igual al bridge")
    return str(mtu)


def texto_limite_mb(limite: float) -> str:
    """Límite de velocidad en MB/s sin ceros sobrantes (100 → «100 MB/s», 12.5 → «12.5 MB/s»)."""
    return QCoreApplication.translate("Textos", "{valor} MB/s").format(
        valor=formato_limite(limite) if math.isfinite(limite) else f"{limite:g}"
    )


def _recorte(texto: str, maximo: int = 60) -> str:
    una_linea = " ".join(texto.split())
    return una_linea if len(una_linea) <= maximo else una_linea[: maximo - 1] + "…"


def lineas_opciones_fase_a(cfg: ConfiguracionVM, *, avanzado: bool) -> list[tuple[str, str]]:
    """Líneas «etiqueta, valor» de las opciones de la fase A para el Resumen (RF-A0.1).

    Solo salen las que difieren del valor por defecto de 0.5.1, salvo «Notas de origen», que
    sale siempre. Las avanzadas (orden, espera, protección) solo si ``avanzado``: en modo
    básico las lista ``opciones_avanzadas_fase_a`` como ocultas.
    """
    lineas: list[tuple[str, str]] = []
    origen = texto_si_no(cfg.notas_origen)
    if cfg.notas_origen and cfg.notas_usuario:
        origen = QCoreApplication.translate("Textos", "sí, con tu usuario")
    lineas.append((QCoreApplication.translate("Textos", "Notas de origen"), origen))
    if cfg.notas.strip():
        lineas.append((QCoreApplication.translate("Textos", "Notas"), _recorte(cfg.notas)))
    if cfg.encender:
        lineas.append(
            (QCoreApplication.translate("Textos", "Encender al terminar"), texto_si_no(True))
        )
    if cfg.arranque_auto:
        lineas.append(
            (QCoreApplication.translate("Textos", "Arrancar con el servidor"), texto_si_no(True))
        )
    if cfg.etiquetas_usuario:
        lineas.append(
            (QCoreApplication.translate("Textos", "Etiquetas"), ", ".join(cfg.etiquetas_usuario))
        )
    if cfg.pool is not None:
        lineas.append((QCoreApplication.translate("Textos", "Pool"), cfg.pool))
    if avanzado:
        lineas.extend(_lineas_avanzadas_fase_a(cfg))
    return lineas


def _lineas_avanzadas_fase_a(cfg: ConfiguracionVM) -> list[tuple[str, str]]:
    lineas: list[tuple[str, str]] = []
    if cfg.arranque_orden is not None:
        lineas.append(
            (QCoreApplication.translate("Textos", "Orden de arranque"), str(cfg.arranque_orden))
        )
    if cfg.arranque_espera is not None:
        lineas.append(
            (
                QCoreApplication.translate("Textos", "Espera de arranque"),
                QCoreApplication.translate("Textos", "{n} s").format(n=cfg.arranque_espera),
            )
        )
    if cfg.proteger:
        lineas.append(
            (QCoreApplication.translate("Textos", "Proteger contra borrado"), texto_si_no(True))
        )
    return lineas


def opciones_avanzadas_fase_a(cfg: ConfiguracionVM, *, con_red: bool = True) -> list[str]:
    """Opciones avanzadas de la fase A que se aplicarán aunque el modo básico las oculte.

    ``con_red=False`` omite MTU y límite (un clon hereda la red de la plantilla).
    """
    lineas = [f"{nombre}: {valor}" for nombre, valor in _lineas_avanzadas_fase_a(cfg)]
    for i, r in enumerate(cfg.redes if con_red else ()):
        if r.mtu is not None:
            lineas.append(
                QCoreApplication.translate("Textos", "Red {n}: MTU {valor}").format(
                    n=i + 1, valor=texto_mtu(r.mtu)
                )
            )
        if r.limite_mb is not None:
            lineas.append(
                QCoreApplication.translate("Textos", "Red {n}: límite {valor}").format(
                    n=i + 1, valor=texto_limite_mb(r.limite_mb)
                )
            )
    return lineas


def texto_detalle_red_fase_a(mtu: int | None, limite_mb: float | None, *, virtio: bool) -> str:
    """Sufijo de la línea de una tarjeta en el Resumen: «, MTU 1500, límite 100 MB/s»."""
    partes: list[str] = []
    if mtu is not None:
        parte = QCoreApplication.translate("Textos", "MTU {valor}").format(valor=texto_mtu(mtu))
        if not virtio:
            parte += QCoreApplication.translate("Textos", " (se ignora: no es VirtIO)")
        partes.append(parte)
    if limite_mb is not None:
        partes.append(
            QCoreApplication.translate("Textos", "límite {valor}").format(
                valor=texto_limite_mb(limite_mb)
            )
        )
    return "".join(f", {x}" for x in partes)


# --- Fase B (0.7): cloud-init, snippets y espera de IP -----------------------------------------
#
# Todos los textos usan ``QCoreApplication.translate`` directo (sin alias) para que ``lupdate``
# los extraiga. Ningún texto incluye contraseñas, cuerpos de claves ni líneas completas: solo
# números de línea y motivos (CA-B14.1). Los textos de B2 (plantilla desde imagen) y de B3
# (estados de la IP) viven en ``textos_b`` y se enlazan desde ``_texto_error_fase_b``.


def _numero_tarjeta(prm: Mapping[str, str]) -> str:
    """Número de tarjeta como lo ve el usuario (1 = net0) a partir del índice ``netN``."""
    try:
        return str(int(prm.get("tarjeta", "")) + 1)
    except ValueError:
        return "?"


def texto_tipo_snippet(tipo: str) -> str:
    """Nombre llano de cada tipo de script de cloud-init (RF-B4.1)."""
    if tipo == "user":
        return QCoreApplication.translate("Textos", "Datos de usuario")
    if tipo == "vendor":
        return QCoreApplication.translate("Textos", "Datos del proveedor")
    if tipo == "network":
        return QCoreApplication.translate("Textos", "Red")
    if tipo == "meta":
        return QCoreApplication.translate("Textos", "Metadatos")
    return tipo


def _texto_sin_privilegio(p: Mapping[str, str]) -> str:
    """Opción deshabilitada o con reservas por falta de privilegio (RF-B0.3, RF-B5.3)."""
    opcion = texto_nombre_opcion_fase_a(p.get("opcion", ""))
    motivo = p.get("motivo", "")
    if motivo == "version_incierta":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{opcion}»: tu usuario no tiene el privilegio {privilegio} en «{ruta}», pero "
                "sí VM.Config.Network. En tu versión de Proxmox puede que lo rechace; si falla, "
                "pídele el privilegio a tu administrador.",
            ),
            p,
            opcion=opcion,
        )
    if motivo == "no_verificado":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{opcion}»: tu usuario no tiene el privilegio {privilegio} en «{ruta}». En tu "
                "versión de Proxmox puede hacer falta (no está verificado): si Proxmox rechaza "
                "el script, pídeselo a tu administrador.",
            ),
            p,
            opcion=opcion,
        )
    if p.get("alternativo"):
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "«{opcion}» no está disponible: tu usuario no tiene el privilegio {privilegio} "
                "(ni {alternativo}, que en tu versión también vale) en «{ruta}». Pídeselo a tu "
                "administrador.",
            ),
            p,
            opcion=opcion,
        )
    return _fmt(
        QCoreApplication.translate(
            "Textos",
            "«{opcion}» no está disponible: tu usuario no tiene el privilegio {privilegio} "
            "en «{ruta}». Pídeselo a tu administrador.",
        ),
        p,
        opcion=opcion,
    )


def _texto_motivo_opcion_b(motivo: str) -> str:
    """Por qué una opción de la fase B está deshabilitada o con reservas (sin código de error)."""
    if motivo == "unidad_desconocida":
        return QCoreApplication.translate(
            "Textos",
            "No se pudo leer la configuración de la plantilla, así que no se sabe si tiene "
            "unidad cloud-init. Puedes rellenar la sección, pero si la plantilla no la tiene "
            "Proxmox no entregará estos datos.",
        )
    if motivo == "windows":
        return QCoreApplication.translate(
            "Textos",
            "Con Windows, Proxmox guardaría la contraseña sin cifrar; no se permite.",
        )
    if motivo == "sin_storage_snippets":
        return QCoreApplication.translate(
            "Textos",
            "Pide al administrador que active el contenido «Fragmentos» (snippets) en un "
            "almacenamiento de archivos.",
        )
    if motivo == "agente_ya_activo":
        return QCoreApplication.translate(
            "Textos", "La plantilla ya tiene el agente invitado activado."
        )
    return ""


def _texto_error_fase_b(error: ErrorProxLaunch) -> str | None:
    """Errores de cloud-init y snippets de la fase B. ``None`` si el código no es uno de ellos.

    Los de B2 y B3 (plantilla desde imagen, agente, suma) los traduce ``textos_b``.
    """
    p = error.params
    c = error.codigo
    if c == CodigoError.CLOUDINIT_SIN_UNIDAD:
        if p.get("plantilla"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "La plantilla «{plantilla}» no tiene unidad cloud-init, así que Proxmox no "
                    "podría entregar estos datos a la máquina. Usa una plantilla creada con "
                    "«Crear plantilla desde imagen cloud» o añade una unidad «CloudInit Drive» "
                    "a la plantilla en Proxmox.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos",
            "Esta plantilla no tiene unidad cloud-init, así que Proxmox no podría entregar "
            "estos datos a la máquina. Usa una plantilla creada con «Crear plantilla desde "
            "imagen cloud» o añade una unidad «CloudInit Drive» a la plantilla en Proxmox.",
        )
    if c == CodigoError.CLAVE_SSH_RECHAZADA:
        return QCoreApplication.translate(
            "Textos",
            "Proxmox rechazó una de las claves SSH. Revisa que sean claves públicas completas.",
        )
    if c == CodigoError.SNIPPET_NO_ENCONTRADO:
        if p.get("snippet"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Proxmox no encuentra el script «{snippet}». Revisa que exista en el "
                    "almacenamiento del nodo.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "Textos",
            "Proxmox no encuentra uno de los scripts de configuración. Revisa que exista en el "
            "almacenamiento del nodo.",
        )
    if c == CodigoError.CONTRASENA_OLVIDADA:
        return QCoreApplication.translate(
            "Textos",
            "La contraseña de cloud-init ya no está en memoria (por seguridad no se guarda). "
            "Vuelve a escribirla y reintenta los ajustes.",
        )
    if c == CodigoError.ARCHIVO_CLAVES_NO_VALIDO:
        motivo = p.get("motivo", "")
        if motivo == "tamano":
            return QCoreApplication.translate(
                "Textos",
                "Ese archivo es demasiado grande para ser una clave pública (máximo 64 KiB).",
            )
        if motivo == "binario":
            return QCoreApplication.translate(
                "Textos",
                "Ese archivo no es de texto. Elige el archivo de la clave pública (el que "
                "termina en .pub).",
            )
        return QCoreApplication.translate(
            "Textos", "No se pudo leer ese archivo. Revisa que exista y que puedas abrirlo."
        )
    # Importación diferida: ``textos_b`` (B2 y B3) no depende de este módulo.
    from proxlaunch.interfaz.textos_b import texto_error_b

    return texto_error_b(error)


def _texto_aviso_fase_b(codigo: str) -> str:
    """Avisos de máquina de cloud-init (``ajuste_pendiente:cloudinit`` y ``…:contrasena``)."""
    if codigo == "ajuste_pendiente:cloudinit":
        return QCoreApplication.translate(
            "Textos",
            "Se creó, pero falta aplicar la configuración inicial (cloud-init). Puedes "
            "reintentar los ajustes.",
        )
    if codigo == "ajuste_pendiente:contrasena":
        return QCoreApplication.translate(
            "Textos",
            "Se creó y la configuración inicial se aplicó, pero falta poner la contraseña. "
            "Puedes reintentar los ajustes (si ya no está en memoria, tendrás que escribirla de "
            "nuevo).",
        )
    # Importación diferida: ``textos_b`` (B2 y B3) no depende de este módulo.
    from proxlaunch.interfaz.textos_b import texto_aviso_b

    return texto_aviso_b(codigo)


def _motivo_clave(motivo: str) -> str:
    if motivo == "tipo_desconocido":
        return QCoreApplication.translate(
            "Textos", "no empieza por un tipo de clave conocido (ssh-ed25519, ssh-rsa…)"
        )
    if motivo == "sin_cuerpo":
        return QCoreApplication.translate("Textos", "falta el cuerpo de la clave")
    if motivo == "base64":
        return QCoreApplication.translate("Textos", "el cuerpo de la clave no es válido")
    if motivo == "con_opciones":
        return QCoreApplication.translate(
            "Textos", "no puede llevar opciones por delante (command=…, from=…)"
        )
    return QCoreApplication.translate("Textos", "no es una clave pública válida")


def _motivo_ip_cloudinit(motivo: str) -> str:
    if motivo == "sin_prefijo":
        return QCoreApplication.translate(
            "Textos", "falta la máscara (por ejemplo 192.168.1.50/24)"
        )
    if motivo == "prefijo":
        return QCoreApplication.translate("Textos", "la máscara debe estar entre /8 y /30")
    if motivo == "octeto":
        return QCoreApplication.translate(
            "Textos", "cada número de la dirección debe estar entre 0 y 255"
        )
    if motivo == "ceros":
        return QCoreApplication.translate(
            "Textos", "no uses ceros a la izquierda (010.0.0.1 es ambiguo)"
        )
    if motivo == "reservada":
        return QCoreApplication.translate(
            "Textos", "es una dirección reservada (0.0.0.0, loopback, multicast o link-local)"
        )
    if motivo == "fuera_de_red":
        return QCoreApplication.translate("Textos", "no está en la misma red que la IP")
    if motivo == "igual_a_ip":
        return QCoreApplication.translate("Textos", "es la misma que la IP de la máquina")
    if motivo == "red_o_difusion":
        return QCoreApplication.translate("Textos", "es la dirección de red o de difusión")
    return QCoreApplication.translate("Textos", "no es una dirección IPv4")


def _texto_v_b25(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "no_coincide":
        return QCoreApplication.translate("Textos", "Las dos contraseñas no coinciden.")
    if motivo == "control":
        return QCoreApplication.translate(
            "Textos", "La contraseña no puede tener saltos de línea ni caracteres de control."
        )
    if motivo == "larga":
        return QCoreApplication.translate(
            "Textos", "La contraseña no puede superar los 128 caracteres."
        )
    if motivo == "corta":
        return QCoreApplication.translate(
            "Textos",
            "La contraseña debe tener al menos 8 caracteres. Con menos, Proxmox la acepta pero "
            "es fácil de adivinar, así que no se admite.",
        )
    return _texto_motivo_opcion_b("windows")


def _texto_v_b30(prm: Mapping[str, str]) -> str:
    motivo = prm.get("motivo", "")
    if motivo == "desborde":
        causa = QCoreApplication.translate("Textos", "se sale de la red")
    elif motivo == "puerta":
        causa = QCoreApplication.translate("Textos", "es la puerta de enlace")
    else:
        causa = QCoreApplication.translate("Textos", "es la dirección de red o de difusión")
    base = _fmt(
        QCoreApplication.translate(
            "Textos",
            "La serie de IP de la tarjeta {n} no cabe: «{nombre}» recibiría {direccion}, que "
            "{causa}.",
        ),
        prm,
        n=_numero_tarjeta(prm),
        causa=causa,
    )
    if _entero(prm.get("afectadas")) not in (None, 1):
        base += " " + _fmt(
            QCoreApplication.translate("Textos", "Afecta a {afectadas} máquinas."), prm
        )
    return base


def _texto_v_b20(prm: Mapping[str, str]) -> str:
    """V-B20: la plantilla no tiene unidad cloud-init (o no se pudo comprobar)."""
    if prm.get("motivo") == "no_comprobable":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "No se pudo leer la configuración de la plantilla «{plantilla}», así que no se "
                "sabe si tiene unidad cloud-init. Si no la tiene, Proxmox no entregará estos "
                "datos.",
            ),
            prm,
        )
    texto = texto_error(ErrorProxLaunch(CodigoError.CLOUDINIT_SIN_UNIDAD, dict(prm)))
    elementos = _entero(prm.get("elementos"))
    if elementos is not None and elementos > 1:
        texto += " " + QCoreApplication.translate(
            "Textos", "Afecta a {n} máquinas del lote."
        ).format(n=elementos)
    return texto


def _texto_v_b34(prm: Mapping[str, str]) -> str:
    n = _numero_tarjeta(prm)
    motivo = prm.get("motivo", "")
    if motivo == "rango":
        return QCoreApplication.translate(
            "Textos", "La tarjeta de red {n} no existe: una máquina tiene hasta 32."
        ).format(n=n)
    if motivo == "repetida":
        return QCoreApplication.translate("Textos", "La tarjeta de red {n} está repetida.").format(
            n=n
        )
    return QCoreApplication.translate(
        "Textos", "La plantilla no tiene la tarjeta de red {n}."
    ).format(n=n)


def _texto_v_b_snippets(p: Problema) -> str | None:
    cod, prm = p.codigo, p.params
    if cod == "V-B50":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El nodo «{nodo}» no tiene ningún almacenamiento con el contenido «Fragmentos» "
                "(snippets). Pide al administrador que lo active.",
            ),
            prm,
        )
    if cod == "V-B51":
        if prm.get("motivo") == "sin_almacen":
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "El almacenamiento del script «{snippet}» no existe en el nodo «{nodo}».",
                ),
                prm,
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El script «{snippet}» no existe en el nodo «{nodo}»."
            ),
            prm,
        )
    if cod == "V-B52":
        if prm.get("motivo") == "suma":
            return QCoreApplication.translate(
                "Textos", "Los scripts elegidos suman más de 3 MiB, el máximo que admite Proxmox."
            )
        return _fmt(
            QCoreApplication.translate(
                "Textos", "El script «{snippet}» pesa más de 1 MiB, el máximo que admite Proxmox."
            ),
            prm,
        )
    if cod == "V-B53":
        return QCoreApplication.translate(
            "Textos",
            "Con «Datos de usuario» elegido, el usuario, las claves y la contraseña de arriba "
            "se ignoran: ese script sustituye a los datos que genera Proxmox.",
        )
    if cod == "V-B54":
        return QCoreApplication.translate(
            "Textos",
            "El identificador del script «{tipo}» no es válido: usa almacén:snippets/archivo, "
            "sin espacios, comas ni «..».",
        ).format(tipo=texto_tipo_snippet(prm.get("tipo", "")))
    if cod == "V-B56":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La plantilla «{plantilla}» ya tiene scripts que ProxLaunch no sabe interpretar: "
                "solo se puede dejar «Como la plantilla».",
            ),
            prm,
        )
    return None


def _texto_v_b_espera(p: Problema) -> str | None:
    cod, prm = p.codigo, p.params
    if cod == "V-B60":
        return QCoreApplication.translate(
            "Textos",
            "La IP solo se puede conocer con la máquina encendida: marca «Encender al terminar».",
        )
    if cod == "V-B61":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "El plazo debe ser un número entero de segundos entre {minimo} y {maximo}.",
            ),
            prm,
        )
    if cod == "V-B62":
        if prm.get("origen") == "plantilla":
            return QCoreApplication.translate(
                "Textos",
                "La plantilla no tiene activado el agente invitado, así que no se podrá saber "
                "la IP. Marca «Activar el agente invitado» en la configuración inicial y "
                "asegúrate de que el programa esté instalado dentro de la máquina.",
            )
        return QCoreApplication.translate(
            "Textos",
            "La máquina no tiene activado el agente invitado (casilla «Agente de QEMU»), así "
            "que no se podrá saber la IP.",
        )
    if cod == "V-B63":
        return _texto_estado_de_problema(prm)
    if cod == "V-B64":
        return QCoreApplication.translate(
            "Textos",
            "Las imágenes de Ubuntu y Debian no traen el agente invitado instalado: sin él no "
            "se podrá saber la IP. Las de Rocky y Alma sí lo traen.",
        )
    if cod == "V-B65":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "Con las actualizaciones activadas, el primer arranque puede tardar más que el "
                "plazo de {plazo_s} s. Sube el plazo o desactiva «Actualizar paquetes».",
            ),
            prm,
        )
    return None


def _texto_estado_de_problema(prm: Mapping[str, str]) -> str:
    """V-B37, V-B55 y V-B63: el problema trae los parámetros de un estado de opción."""
    sin_version = prm.get("motivo") == str(CodigoError.OPCION_SIN_VERSION)
    return texto_error(
        ErrorProxLaunch(
            CodigoError.OPCION_SIN_VERSION if sin_version else CodigoError.OPCION_SIN_PRIVILEGIO,
            dict(prm),
        )
    )


def _texto_problema_fase_b(p: Problema) -> str | None:
    """Mensaje de las reglas V-B20..V-B65 (cloud-init, snippets y espera de IP).

    ``None`` si la regla no es de la fase B (las de B2, V-B01..V-B16, las traduce ``textos_b``).
    """
    cod, prm = p.codigo, p.params
    if cod == "V-B20":
        return _texto_v_b20(prm)
    if cod == "V-B21":
        if prm.get("motivo") == "patron":
            return QCoreApplication.translate(
                "Textos",
                "El usuario no sigue el patrón habitual (minúsculas, números, «_» y «-», hasta "
                "32 caracteres). Proxmox lo acepta, pero cloud-init podría rechazarlo.",
            )
        return QCoreApplication.translate(
            "Textos", "El usuario no puede tener espacios, «:» ni caracteres de control."
        )
    if cod == "V-B22":
        return QCoreApplication.translate(
            "Textos", "La línea {linea} de las claves SSH no es una clave pública válida: {motivo}."
        ).format(linea=prm.get("linea", "?"), motivo=_motivo_clave(prm.get("motivo", "")))
    if cod == "V-B23":
        return QCoreApplication.translate(
            "Textos",
            "Eso parece una clave privada. Nunca la pegues aquí: usa solo la clave pública (el "
            "archivo que termina en .pub).",
        )
    if cod == "V-B24":
        motivo = prm.get("motivo", "")
        if motivo == "duplicadas":
            return _fmt(
                QCoreApplication.translate("Textos", "Se descartaron {cantidad} claves repetidas."),
                prm,
            )
        if motivo == "demasiado_texto":
            return QCoreApplication.translate(
                "Textos", "Las claves SSH ocupan demasiado (máximo 8 KiB en total)."
            )
        return QCoreApplication.translate("Textos", "Hay demasiadas claves SSH (máximo 20).")
    if cod == "V-B25":
        return _texto_v_b25(prm)
    if cod == "V-B26":
        return QCoreApplication.translate(
            "Textos", "La IP de la tarjeta de red {n} no es válida: {motivo}."
        ).format(n=_numero_tarjeta(prm), motivo=_motivo_ip_cloudinit(prm.get("motivo", "")))
    if cod == "V-B27":
        return QCoreApplication.translate(
            "Textos",
            "La IP de la tarjeta de red {n} es la dirección de red o de difusión de su red: "
            "elige otra.",
        ).format(n=_numero_tarjeta(prm))
    if cod == "V-B28":
        return QCoreApplication.translate(
            "Textos", "La puerta de enlace de la tarjeta de red {n} no es válida: {motivo}."
        ).format(n=_numero_tarjeta(prm), motivo=_motivo_ip_cloudinit(prm.get("motivo", "")))
    if cod == "V-B29":
        return QCoreApplication.translate(
            "Textos", "La puerta de enlace de la tarjeta de red {n} solo vale con IP fija."
        ).format(n=_numero_tarjeta(prm))
    if cod == "V-B30":
        return _texto_v_b30(prm)
    if cod == "V-B31":
        return _fmt(
            QCoreApplication.translate(
                "Textos", "La IP {direccion} se repite: la usan «{con}» y «{nombre}»."
            ),
            prm,
        )
    if cod == "V-B32":
        if prm.get("cantidad"):
            return _fmt(
                QCoreApplication.translate(
                    "Textos",
                    "Has puesto {cantidad} servidores DNS; lo habitual es usar hasta tres.",
                ),
                prm,
            )
        return QCoreApplication.translate(
            "Textos",
            "Los DNS no son válidos: escribe direcciones IP (por ejemplo 1.1.1.1 o 8.8.8.8) "
            "separadas por espacio o coma.",
        )
    if cod == "V-B33":
        return QCoreApplication.translate(
            "Textos",
            "El dominio de búsqueda no es válido: usa un nombre como lab.local, sin espacios.",
        )
    if cod == "V-B34":
        return _texto_v_b34(prm)
    if cod == "V-B35":
        return _fmt(
            QCoreApplication.translate(
                "Textos",
                "La plantilla «{plantilla}» es de Windows: cloud-init no está probado con "
                "Windows y puede no funcionar.",
            ),
            prm,
        )
    if cod == "V-B36":
        return QCoreApplication.translate(
            "Textos", "«Actualizar paquetes» debe ser «Como la plantilla», «Sí» o «No»."
        )
    if cod in ("V-B37", "V-B55"):
        return _texto_estado_de_problema(prm)
    if cod == "V-B38":
        return QCoreApplication.translate(
            "Textos",
            "Las {cantidad} máquinas del lote tendrían la misma IP en la tarjeta de red {n}. "
            "Marca «Sumar 1 a cada máquina» o usa DHCP.",
        ).format(cantidad=prm.get("cantidad", "?"), n=_numero_tarjeta(prm))
    if cod == "V-B39":
        return QCoreApplication.translate(
            "Textos",
            "La configuración inicial (cloud-init) solo se puede usar al clonar una plantilla.",
        )
    if cod == "V-B40":
        return QCoreApplication.translate(
            "Textos", "La contraseña ya no está en memoria; vuelve a escribirla."
        )
    texto = _texto_v_b_snippets(p) or _texto_v_b_espera(p)
    if texto is not None:
        return texto
    from proxlaunch.interfaz.textos_b import texto_problema_b2

    return texto_problema_b2(p)


# --- Resumen de la fase B -----------------------------------------------------------------------


def texto_claves_ssh(claves: tuple[str, ...]) -> str:
    """«2 claves: ssh-ed25519 (ana@portatil), ssh-rsa»; nunca el cuerpo de una clave (RF-B0.1)."""
    partes: list[str] = []
    for clave in claves:
        tipo, comentario = resumen_clave(clave)
        partes.append(f"{tipo} ({comentario})" if comentario else tipo)
    n = len(claves)
    cuenta = (
        QCoreApplication.translate("Textos", "1 clave")
        if n == 1
        else QCoreApplication.translate("Textos", "{n} claves").format(n=n)
    )
    return f"{cuenta}: {', '.join(partes)}"


def texto_tarjeta_cloudinit(
    modo: ModoTarjeta, ip: str | None, puerta: str | None, serie: bool
) -> str:
    """Modo de red de una tarjeta: «DHCP» o «IP fija 10.0.0.50/24, puerta 10.0.0.1»."""
    if modo == ModoTarjeta.DHCP:
        return QCoreApplication.translate("Textos", "DHCP")
    texto = QCoreApplication.translate("Textos", "IP fija {ip}").format(ip=ip or "—")
    if puerta:
        texto += QCoreApplication.translate("Textos", ", puerta {puerta}").format(puerta=puerta)
    if serie:
        texto += QCoreApplication.translate("Textos", " (sumando 1 a cada máquina)")
    return texto


def texto_snippet_elegido(valor: str) -> str:
    """Un script elegido: el identificador, o «ninguno» si se quita el de la plantilla."""
    if valor == NINGUNO:
        return QCoreApplication.translate("Textos", "ninguno")
    return valor


def _lineas_avanzadas_fase_b(cfg: ConfiguracionVM) -> list[tuple[str, str]]:
    ci = cfg.cloudinit
    if ci is None:
        return []
    lineas: list[tuple[str, str]] = []
    if ci.dns:
        lineas.append((QCoreApplication.translate("Textos", "DNS"), ", ".join(ci.dns)))
    if ci.dominio:
        lineas.append((QCoreApplication.translate("Textos", "Dominio de búsqueda"), ci.dominio))
    if ci.actualizar is not None:
        lineas.append(
            (
                QCoreApplication.translate("Textos", "Actualizar paquetes al arrancar"),
                texto_si_no(ci.actualizar),
            )
        )
    for tipo in TIPOS_SNIPPET:
        valor: str | None = getattr(ci.snippets, tipo)
        if valor is not None:
            lineas.append(
                (
                    QCoreApplication.translate("Textos", "Script: {tipo}").format(
                        tipo=texto_tipo_snippet(tipo)
                    ),
                    texto_snippet_elegido(valor),
                )
            )
    return lineas


def lineas_opciones_fase_b(cfg: ConfiguracionVM, *, avanzado: bool) -> list[tuple[str, str]]:
    """Líneas «etiqueta, valor» de cloud-init y la espera de IP para el Resumen (RF-B0.1).

    Solo salen los valores que difieren del predeterminado: sin opciones de la fase B no hay
    ninguna línea. La contraseña es «definida (oculta)» y las claves, número, tipo y comentario.
    Las avanzadas (DNS, dominio, actualizar, scripts) solo si ``avanzado``; en modo básico las
    lista ``opciones_avanzadas_fase_b`` como ocultas.
    """
    lineas: list[tuple[str, str]] = []
    ci = cfg.cloudinit
    if ci is not None and not ci.vacia:
        if ci.usuario:
            lineas.append((QCoreApplication.translate("Textos", "Usuario inicial"), ci.usuario))
        if ci.claves:
            lineas.append(
                (QCoreApplication.translate("Textos", "Claves SSH"), texto_claves_ssh(ci.claves))
            )
        if ci.contrasena is not None and ci.contrasena.definido:
            lineas.append(
                (
                    QCoreApplication.translate("Textos", "Contraseña inicial"),
                    QCoreApplication.translate("Textos", "definida (oculta)"),
                )
            )
        for t in ci.tarjetas:
            if t.modo != ModoTarjeta.SIN_CONFIGURAR:
                lineas.append(
                    (
                        QCoreApplication.translate("Textos", "Red net{i}").format(i=t.indice),
                        texto_tarjeta_cloudinit(t.modo, t.ip, t.puerta, t.serie),
                    )
                )
        if ci.activar_agente:
            lineas.append(
                (
                    QCoreApplication.translate("Textos", "Activar el agente invitado"),
                    texto_si_no(True),
                )
            )
        if avanzado:
            lineas.extend(_lineas_avanzadas_fase_b(cfg))
    if cfg.esperar_ip:
        lineas.append(
            (
                QCoreApplication.translate("Textos", "Esperar la IP"),
                QCoreApplication.translate("Textos", "sí (plazo {n} s)").format(n=cfg.plazo_ip_s),
            )
        )
    return lineas


def opciones_avanzadas_fase_b(cfg: ConfiguracionVM) -> list[str]:
    """Opciones avanzadas de cloud-init que se aplicarán aunque el modo básico las oculte."""
    if cfg.cloudinit is None or cfg.cloudinit.vacia:
        return []
    return [f"{nombre}: {valor}" for nombre, valor in _lineas_avanzadas_fase_b(cfg)]
