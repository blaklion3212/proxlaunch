"""Traducción a español de los códigos del núcleo (RF-21, RF-23, CA-21.4).

El núcleo habla en códigos; aquí cada código se convierte en un mensaje en lenguaje llano
con ``QCoreApplication.translate``. Si un código no tiene texto se muestra el mensaje
genérico de CA-21.2 (los detalles técnicos los muestra la vista aparte).
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QCoreApplication

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
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso, EstadoHuella
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
    return QCoreApplication.translate("Textos", "un dato")


class _Seguro(dict[str, str]):
    """Diccionario que deja visible el marcador si falta un parámetro."""

    def __missing__(self, clave: str) -> str:
        # Un marcador sin valor nunca debe verse: se usa un valor neutro traducible.
        return _valor_neutro(clave)


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
    texto_lote = _texto_error_lote(error)
    if texto_lote is not None:
        return texto_lote
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
                "«{nombre}» está protegida o bloqueada. Quita la protección en Proxmox.",
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
    return None


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
    return _fmt(
        QCoreApplication.translate("Textos", "«{nodo}» no puede alojar esta configuración."), prm
    )


def texto_problema_lote(p: ProblemaLote) -> str:
    """Mensaje de una regla V-L (docs/requisitos/mvp2.md §4) o de una V-xx de M1 por elemento."""
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
        return _texto_v_l11(prm)
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
        return _texto_e_l01(prm)
    if regla == "V-24":
        return QCoreApplication.translate(
            "Textos", "Proxmox no admite esa etiqueta: usa solo letras, números y guiones."
        )
    if regla.startswith("V-") and not regla.startswith("V-L"):
        base = texto_problema(_a_problema_m1(p))
        if p.indice is not None and base != texto_generico():
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
