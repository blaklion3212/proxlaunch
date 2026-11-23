"""Textos de la fase C (0.8) en español llano: redes virtuales (VNets), firewall de la máquina con
un grupo de seguridad y red del clon.

Todos los textos pasan por ``QCoreApplication.translate`` con el literal a la vista (nunca un
alias): así ``lupdate`` los extrae al catálogo ``.ts``. Este módulo NO importa ``textos`` al
cargarse (``textos`` delega aquí sus códigos nuevos); lo que necesita de él lo importa
perezosamente. Nunca se escribe un secreto ni el valor de un parámetro sensible: solo nombres,
códigos, privilegios y números. Los nombres de red, grupo o plantilla vienen del servidor (no
confiables): se muestran como texto plano y el Resumen los escapa.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import ModoDhcp, Politica, usa_firewall
from proxlaunch.nucleo.lote.modelos import EntradaLibro
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, EstadoVia, Via
from proxlaunch.nucleo.red.modelos import (
    AccionTarjeta,
    CampoRed,
    ModoRedClon,
    RedClon,
    TarjetaClon,
    TarjetaFinal,
    usa_red_clon,
)
from proxlaunch.nucleo.servicios.creacion import (
    AVISO_AJUSTE_PENDIENTE,
    AVISO_FIREWALL_GRUPO_YA_ESTABA,
    AVISO_FIREWALL_HEREDADO,
    AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA,
    AVISO_RED_MAC_NUEVA,
    AVISO_RED_MTU_IGNORADA,
    AVISO_RED_TARJETA_ILEGIBLE,
)
from proxlaunch.nucleo.validacion import Problema, Severidad


class _Seguro(dict[str, str]):
    """Mapa que deja intacto un marcador ``{x}`` si falta el dato (nunca lanza)."""

    def __missing__(self, clave: str) -> str:
        # Un marcador sin valor nunca debe verse: se usa un texto neutro traducible.
        if clave in ("grupo", "red", "vnet", "plantilla"):
            return QCoreApplication.translate("TextosC", "ese elemento")
        if clave == "nodo":
            return QCoreApplication.translate("TextosC", "ese nodo")
        return QCoreApplication.translate("TextosC", "un dato")


def _fmt(texto: str, params: Mapping[str, str] | None = None, **extra: str) -> str:
    datos = _Seguro({**(params or {}), **extra})
    try:
        return texto.format_map(datos)
    except (ValueError, IndexError, KeyError, AttributeError):
        return texto


# =============================================================================================
# Nombres de opciones y motivos de disponibilidad
# =============================================================================================


def texto_nombre_opcion_c(opcion: str) -> str:
    """Nombre llano de una opción de la fase C (valor de ``OpcionC``); ``""`` si no es de C."""
    if opcion == "inventario":
        return QCoreApplication.translate("TextosC", "Ver y deshacer mis lotes en el servidor")
    if opcion == "vnets":
        return QCoreApplication.translate("TextosC", "Redes virtuales (SDN)")
    if opcion == "firewall":
        return QCoreApplication.translate("TextosC", "Firewall de la máquina")
    if opcion == "firewall_general":
        return QCoreApplication.translate("TextosC", "Saber si el firewall general está encendido")
    if opcion == "red_clon":
        return QCoreApplication.translate("TextosC", "Cambiar la red de las copias")
    if opcion == "ip_inventario":
        return QCoreApplication.translate("TextosC", "IP de las máquinas del servidor")
    return ""


def texto_motivo_opcion_c(motivo: str) -> str:
    """Por qué una opción de la fase C queda con reservas (sin código de error)."""
    if motivo == "permisos_desconocidos":
        return QCoreApplication.translate(
            "TextosC",
            "No se pudo comprobar tu permiso. Puedes intentarlo; si falta alguno, ProxLaunch te "
            "dirá cuál.",
        )
    return ""


# =============================================================================================
# Redes virtuales (C2) y red del clon (C4): textos de la tabla de redes
# =============================================================================================


def texto_intro_vnet() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Una red virtual (VNet) es una red que define el administrador de Proxmox y reparte por "
        "una zona; por ejemplo, la VNet «prod» de la zona «dc1». Conectas la máquina a ella como "
        "a un bridge.",
    )


def texto_grupo_bridges() -> str:
    return QCoreApplication.translate("TextosC", "Bridges del servidor")


def texto_grupo_vnets() -> str:
    return QCoreApplication.translate("TextosC", "Redes virtuales (SDN)")


def texto_vnet_con_alias(nombre: str, alias: str | None) -> str:
    """«prod — Red de producción»; sin alias, solo el nombre."""
    if alias:
        return QCoreApplication.translate("TextosC", "{nombre} — {alias}").format(
            nombre=nombre, alias=alias
        )
    return nombre


def texto_sdn_sin_leer(nodo: str) -> str:
    """CA-C2.1.3: la lectura de las redes virtuales (SDN) del nodo falló; solo hay bridges."""
    return QCoreApplication.translate(
        "TextosC",
        "No se pudieron leer las redes virtuales (SDN) del nodo {nodo}; solo se muestran los "
        "bridges.",
    ).format(nodo=nodo)


def texto_sin_vnets(version_con_sdn_incluido: bool) -> str:
    """V-C13 (RF-C2.4): sin redes virtuales visibles, según la versión de Proxmox."""
    if version_con_sdn_incluido:
        return QCoreApplication.translate(
            "TextosC",
            "No ves ninguna red virtual. Puede que no haya ninguna o que tu usuario no tenga "
            "permiso para usarlas. Pide al administrador el permiso «SDN.Use» en la zona "
            "(/sdn/zones/<zona>) o en la red virtual que quieras usar. Si la acaba de crear, "
            "pídele también que aplique la configuración de SDN.",
        )
    return QCoreApplication.translate(
        "TextosC",
        "Esta versión de Proxmox (8.0) solo tiene redes virtuales si el administrador instaló "
        "el paquete «libpve-network-perl» en cada nodo. Si no lo tienes, puedes seguir usando "
        "los bridges.",
    )


def texto_vlan_no_vlanaware() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Esta red virtual no admite VLAN (no es «vlanaware»). La VLAN ya viene definida en la "
        "propia red virtual.",
    )


def texto_redes_ocultas(n: int) -> str:
    """RF-C2.3: redes que no existen en todos los nodos elegidos."""
    if n == 1:
        return QCoreApplication.translate(
            "TextosC", "1 red no se muestra porque no existe en todos los nodos elegidos."
        )
    return QCoreApplication.translate(
        "TextosC", "{n} redes no se muestran porque no existen en todos los nodos elegidos."
    ).format(n=n)


def texto_nodos_sin_leer(nodos: Sequence[str]) -> str:
    """RF-C2.3 (CA-C2.3.4): nodos de los que no se pudo leer la red."""
    return QCoreApplication.translate(
        "TextosC",
        "No pude leer las redes de {nodos}; las redes mostradas se comprobaron solo en los "
        "demás nodos.",
    ).format(nodos=", ".join(nodos))


def texto_modo_red_plantilla() -> str:
    return QCoreApplication.translate("TextosC", "Como la plantilla")


def texto_modo_red_personalizar() -> str:
    return QCoreApplication.translate("TextosC", "Personalizar la red de las copias")


def texto_intro_red_clon() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Al clonar, cada copia hereda las tarjetas de red de la plantilla. Aquí puedes "
        "cambiarlas. La dirección MAC (la «matrícula» de la tarjeta) no se pierde.",
    )


def texto_plantilla_sin_tarjetas() -> str:
    return QCoreApplication.translate("TextosC", "La plantilla no tiene tarjetas de red.")


def texto_tarjeta_ilegible(indice: int) -> str:
    return QCoreApplication.translate(
        "TextosC",
        "No entendí la tarjeta net{n} de la plantilla; se deja como está y no se puede cambiar.",
    ).format(n=indice)


def texto_red_clon_sin_leer() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Todavía no se leyó la configuración de la plantilla; espera un momento para poder "
        "personalizar su red.",
    )


# =============================================================================================
# Firewall de la máquina (C3): textos de la sección
# =============================================================================================


def texto_intro_firewall() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "El firewall de Proxmox filtra el tráfico que entra y sale de la máquina virtual. Un "
        "grupo de seguridad es un conjunto de reglas ya preparado por el administrador (por "
        "ejemplo «web»: permite los puertos 80 y 443, o «ssh»: permite el 22). La política de "
        "entrada decide qué pasa con lo que ninguna regla permite: Bloquear (recomendado) o "
        "Permitir.",
    )


def texto_riesgo_firewall() -> str:
    """RF-C3.9: riesgo de dejar la máquina inaccesible por la red."""
    return QCoreApplication.translate(
        "TextosC",
        "Con la entrada en Bloquear, solo entra el tráfico que permita el grupo. Si el grupo no "
        "abre el puerto de acceso (SSH 22 en Linux, RDP 3389 en Windows) no podrás entrar a la "
        "máquina por la red; seguirás pudiendo usar la consola de Proxmox.",
    )


def texto_politica(politica: Politica) -> str:
    if politica == Politica.BLOQUEAR:
        return QCoreApplication.translate("TextosC", "Bloquear")
    return QCoreApplication.translate("TextosC", "Permitir")


def texto_explicacion_politica(entrada: bool) -> str:
    """Explicación llana con ejemplo de las dos políticas (RF-C3.3)."""
    if entrada:
        return QCoreApplication.translate(
            "TextosC",
            "Bloquear: nadie entra salvo lo que permita el grupo (por ejemplo, solo el puerto "
            "22). Permitir: entra todo lo que ninguna regla prohíba.",
        )
    return QCoreApplication.translate(
        "TextosC",
        "Permitir: la máquina puede conectarse a donde quiera (lo habitual). Bloquear: solo "
        "sale lo que permita el grupo.",
    )


def texto_sin_grupos() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "El servidor no tiene grupos de seguridad. Los crea el administrador en Centro de "
        "datos > Firewall > Grupos de seguridad.",
    )


def texto_grupos_ilegibles() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "No pude leer los grupos de seguridad del servidor, así que no puedo asegurar que el "
        "grupo exista. Reintenta o desactiva el firewall.",
    )


def texto_dhcp_automatico() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Con la entrada en Bloquear, la respuesta del servidor DHCP no llegaría y la máquina "
        "se quedaría sin IP.",
    )


def texto_ver_reglas_sin_permiso() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Para ver las reglas del grupo hace falta el permiso «Sys.Audit» en «/». Pídeselo a tu "
        "administrador.",
    )


def texto_reglas_grupo(grupo: str, lineas: Sequence[str]) -> str:
    if not lineas:
        return QCoreApplication.translate("TextosC", "El grupo «{grupo}» no tiene reglas.").format(
            grupo=grupo
        )
    return QCoreApplication.translate("TextosC", "Reglas del grupo «{grupo}»:\n{reglas}").format(
        grupo=grupo, reglas="\n".join(lineas)
    )


def texto_regla(tipo: str, accion: str, activa: bool, comentario: str) -> str:
    """Una regla de un grupo en una línea; los valores vienen del servidor (ya saneados)."""
    base = QCoreApplication.translate("TextosC", "• {tipo}: {accion}").format(
        tipo=tipo, accion=accion
    )
    if comentario:
        base += f" ({comentario})"
    if not activa:
        base += " " + QCoreApplication.translate("TextosC", "[desactivada]")
    return base


def texto_error_leer_reglas() -> str:
    return QCoreApplication.translate(
        "TextosC", "No pude leer las reglas de ese grupo. Puedes elegirlo igualmente."
    )


# =============================================================================================
# Validaciones V-C10..V-C52
# =============================================================================================


def _n_tarjeta(prm: Mapping[str, str]) -> str:
    """Número de tarjeta de un problema: «net1» (o «1» en V-C16) se muestra como «net1»."""
    valor = prm.get("tarjeta", "")
    if not valor:
        return QCoreApplication.translate("TextosC", "de red")
    return valor if valor.startswith("net") else f"net{valor}"


def texto_problema_c(p: Problema) -> str | None:
    """Mensaje de las reglas V-C10..V-C52; ``None`` si la regla no es de la fase C.

    V-C01..V-C09 (inventario) los traduce ``textos_inventario``. V-C12 es la V-16 de siempre.
    """
    cod, prm = p.codigo, p.params
    if cod == "V-C10":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "La red virtual «{vnet}» no admite VLAN en la tarjeta (no es «vlanaware»). Quita "
                "la VLAN o elige otra red; si no, la máquina se crearía pero no arrancaría.",
            ),
            prm,
        )
    if cod == "V-C11":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "La red virtual «{vnet}» no existe en el servidor {nodo}. Elige una red que "
                "exista en todos los servidores del lote.",
            ),
            prm,
        )
    if cod == "V-C14":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "La MTU {mtu} es mayor que la de la red ({mtu_red}); Proxmox podría negarse a "
                "arrancar la máquina. Usa «Igual al bridge» o un valor menor.",
            ),
            prm,
        )
    if cod == "V-C15":
        return QCoreApplication.translate(
            "TextosC", "La VLAN debe ser un número entre 1 y 4094 (por ejemplo, 20)."
        )
    if cod == "V-C16":
        numero = prm.get("tarjeta", "").removeprefix("net")
        if not numero:
            return QCoreApplication.translate(
                "TextosC",
                "Has configurado la IP de una tarjeta que vas a quitar. Quita su "
                "configuración o conserva la tarjeta.",
            )
        return QCoreApplication.translate(
            "TextosC",
            "Has configurado la IP de la tarjeta {n} pero la vas a quitar. Quita su "
            "configuración o conserva la tarjeta.",
        ).format(n=numero)
    if cod == "V-C17":
        return QCoreApplication.translate(
            "TextosC", "Una máquina admite como máximo 32 tarjetas de red."
        )
    if cod == "V-C18":
        return QCoreApplication.translate(
            "TextosC", "La máquina se quedará sin tarjetas de red y no tendrá conexión."
        )
    if cod == "V-C19":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "La plantilla usa la red «{red}» y tu usuario no tiene permiso para usarla; "
                "clonar o cambiar su tarjeta puede fallar con un error 403.",
            ),
            prm,
        )
    if cod == "V-C20":
        return QCoreApplication.translate(
            "TextosC", "No entendí la tarjeta {n} de la plantilla; la dejo como está."
        ).format(n=_n_tarjeta(prm))
    if cod == "V-C21":
        return QCoreApplication.translate(
            "TextosC",
            "No pude leer la configuración de la copia, así que no cambié su red para no "
            "perder su MAC. Usa «Reintentar ajustes».",
        )
    return _texto_problema_firewall(p)


def _texto_problema_firewall(p: Problema) -> str | None:
    cod, prm = p.codigo, p.params
    if cod == "V-C30":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "El grupo de seguridad «{grupo}» no existe en este servidor. Elige uno de la "
                "lista (los crea el administrador en Centro de datos > Firewall).",
            ),
            prm,
        )
    if cod == "V-C31":
        return QCoreApplication.translate(
            "TextosC",
            "El nombre del grupo debe empezar por una letra y tener entre 2 y 18 caracteres: "
            "letras, números, guion y guion bajo (por ejemplo, «web-01»).",
        )
    if cod == "V-C32":
        return texto_grupos_ilegibles()
    if cod == "V-C33":
        return QCoreApplication.translate(
            "TextosC",
            "El firewall general de Proxmox (Centro de datos > Firewall) está apagado: las "
            "reglas de esta máquina se guardan pero no se aplican. ProxLaunch no lo enciende "
            "(encenderlo bloquea el acceso a los servidores salvo los puertos permitidos); lo "
            "hace el administrador.",
        )
    if cod == "V-C34":
        return QCoreApplication.translate(
            "TextosC",
            "No pude comprobar si el firewall general está encendido (falta el permiso "
            "«Sys.Audit»). Las reglas se guardarán igualmente.",
        )
    if cod == "V-C35":
        return _texto_v_c35(prm)
    if cod == "V-C36":
        if p.severidad == Severidad.AVISO:
            return QCoreApplication.translate(
                "TextosC",
                "La máquina no aceptará conexiones por la red (firewall activo, entrada en "
                "Bloquear y ningún grupo). Podrás usar la consola de Proxmox.",
            )
        return QCoreApplication.translate(
            "TextosC",
            "Con el firewall activo, la entrada en Bloquear y ningún grupo, la máquina no "
            "aceptaría ninguna conexión por la red. Elige un grupo, cambia la entrada a Permitir "
            "o marca que lo entiendes.",
        )
    if cod == "V-C37":
        return QCoreApplication.translate(
            "TextosC",
            "La máquina pedirá su IP por DHCP pero el firewall bloqueará la respuesta y se "
            "quedará sin IP. Marca «Permitir que la máquina pida su IP por DHCP».",
        )
    if cod == "V-C38":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "El grupo «{grupo}» no permite ninguna conexión entrante; no podrás entrar por "
                "la red (por ejemplo, por SSH). Podrás usar la consola de Proxmox.",
            ),
            prm,
        )
    if cod == "V-C39":
        return QCoreApplication.translate(
            "TextosC", "La política debe ser «Bloquear» o «Permitir»."
        )
    if cod == "V-C40":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "Falta el permiso «{privilegio}» en {ruta} para activar el firewall. Pídeselo a "
                "tu administrador.",
            ),
            prm,
        )
    if cod == "V-C50":
        return _fmt(
            QCoreApplication.translate(
                "TextosC", "Esto no está disponible en la versión {version} de Proxmox."
            ),
            prm,
        )
    if cod == "V-C51":
        return QCoreApplication.translate(
            "TextosC", "«reescribir_red» solo vale en filas que clonan una plantilla."
        )
    if cod == "V-C52":
        return QCoreApplication.translate(
            "TextosC",
            "Has indicado un grupo o una política de firewall pero el firewall no está "
            "activado en esta fila. Pon «cortafuegos = sí» o quita esos valores.",
        )
    return None


def _texto_v_c35(prm: Mapping[str, str]) -> str:
    """La plantilla ya trae firewall, no se pudo comprobar o tiene una tarjeta ilegible."""
    motivo = prm.get("motivo", "heredado")
    if motivo == "no_comprobable":
        return QCoreApplication.translate(
            "TextosC", "No pude comprobar si la plantilla ya tiene firewall."
        )
    if motivo == "tarjeta_ilegible":
        return QCoreApplication.translate(
            "TextosC",
            "La tarjeta {n} de la plantilla no se entiende: quedará sin firewall (el resto de "
            "tarjetas sí lo tendrá).",
        ).format(n=_n_tarjeta(prm))
    return QCoreApplication.translate(
        "TextosC",
        "Esta plantilla ya traía firewall y reglas; las copias las heredan y se sumará el "
        "grupo que elijas.",
    )


# =============================================================================================
# Errores de la creación (I4b) y de SDN
# =============================================================================================


def _texto_403_sdn(p: Mapping[str, str]) -> str:
    """403 de ``SDN.Use`` con la zona y la red (RF-C4.5, CA-C2.5.3)."""
    lado = p.get("lado", "")
    tarjeta = p.get("tarjeta", "")
    if lado == "plantilla":
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "Proxmox no te deja clonar: la plantilla usa la red «{red}» y tu usuario no "
                "tiene el permiso SDN.Use sobre ella. Pide al administrador el permiso SDN.Use "
                "en /sdn/zones/{zona}/{red} o usa una plantilla conectada a una red que sí "
                "puedas usar.",
            ),
            p,
        )
    if lado == "antigua" and tarjeta:
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "Proxmox no te deja cambiar la tarjeta {tarjeta} porque la plantilla la conecta "
                "a la red «{red}» y tu usuario no tiene el permiso SDN.Use sobre ella. Pide al "
                "administrador el permiso SDN.Use en /sdn/zones/{zona}/{red} o usa una "
                "plantilla conectada a una red que sí puedas usar.",
            ),
            p,
        )
    if tarjeta:
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "Proxmox no te deja conectar la tarjeta {tarjeta} a la red «{red}»: a tu "
                "usuario le falta el permiso SDN.Use en /sdn/zones/{zona}/{red}. Pídeselo al "
                "administrador o elige otra red.",
            ),
            p,
        )
    return _fmt(
        QCoreApplication.translate(
            "TextosC",
            "Proxmox no te deja usar la red «{red}»: a tu usuario le falta el permiso SDN.Use "
            "en /sdn/zones/{zona}/{red}. Pídeselo al administrador o elige otra red.",
        ),
        p,
    )


def _que_ajuste_c(ajuste: str) -> str:
    if ajuste == "red":
        return QCoreApplication.translate("TextosC", "la red")
    if ajuste == "firewall_opciones":
        return QCoreApplication.translate("TextosC", "las opciones del firewall")
    return QCoreApplication.translate("TextosC", "la regla del grupo de seguridad")


def _texto_403_ajuste_c(p: Mapping[str, str]) -> str:
    """403 de un paso de C (red o firewall): la máquina existe y no se enciende."""
    que = _que_ajuste_c(p.get("ajuste", ""))
    if p.get("privilegio"):
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "Se creó, pero no se pudo aplicar {que}: a tu usuario le falta el permiso "
                "{privilegio} en «{ruta}». La máquina no se encendió. Pídeselo a tu "
                "administrador y reintenta los ajustes.",
            ),
            p,
            que=que,
        )
    return QCoreApplication.translate(
        "TextosC",
        "Se creó, pero no se pudo aplicar {que}: a tu usuario le falta un permiso "
        "(VM.Config.Network). La máquina no se encendió. Pídeselo a tu administrador y "
        "reintenta los ajustes.",
    ).format(que=que)


def texto_error_c(error: ErrorProxLaunch) -> str | None:
    """Mensaje de un error de la fase C; ``None`` si el código no es de C.

    Un 403 con ``zona`` (SDN) o con ``ajuste`` de C se explica aquí; los demás 403 siguen la
    traducción general.
    """
    p, c = error.params, error.codigo
    if c == CodigoError.PERMISO_INSUFICIENTE:
        if p.get("ajuste") in ("red", "firewall_opciones", "firewall_regla") and not p.get("zona"):
            return _texto_403_ajuste_c(p)
        if p.get("zona") and p.get("red"):
            return _texto_403_sdn(p)
        return None
    if c == CodigoError.RED_CONFIG_ILEGIBLE:
        return texto_problema_c(Problema("red_clon", "V-C21", Severidad.ERROR, dict(p)))
    if c == CodigoError.RED_PLANTILLA_CAMBIADA:
        return QCoreApplication.translate(
            "TextosC",
            "No se cambió la red de la copia: la tarjeta que querías añadir ya está ocupada por "
            "otra red (la plantilla cambió desde que preparaste el lote). No se tocó nada. "
            "Revisa la red y reintenta los ajustes.",
        )
    if c == CodigoError.RED_CONFIG_CAMBIADA:
        return QCoreApplication.translate(
            "TextosC",
            "No se cambió la red de la copia: su configuración cambió mientras la preparaba "
            "(alguien la editó a la vez). Reintenta los ajustes.",
        )
    if c == CodigoError.RED_SIN_DIRECCIONES:
        if p.get("zona"):
            return _fmt(
                QCoreApplication.translate(
                    "TextosC",
                    "La red virtual no tiene direcciones libres (zona «{zona}»). Pide al "
                    "administrador que amplíe el rango o elige otra red.",
                ),
                p,
            )
        return QCoreApplication.translate(
            "TextosC",
            "La red virtual no tiene direcciones libres. Pide al administrador que amplíe el "
            "rango o elige otra red.",
        )
    if c == CodigoError.FIREWALL_GRUPO_INEXISTENTE:
        return _fmt(
            QCoreApplication.translate(
                "TextosC",
                "El grupo de seguridad «{grupo}» ya no existe en el servidor, así que no se "
                "aplicó la regla. La máquina no se encendió. Elige otro grupo o pide al "
                "administrador que lo cree de nuevo.",
            ),
            p,
        )
    return None


def texto_ajuste_verbo_c(ajuste: str) -> str:
    """El ajuste de C como acción («aplicar la red»); ``""`` si no es de C."""
    if ajuste == "red":
        return QCoreApplication.translate("TextosC", "cambiar la red")
    if ajuste == "firewall_opciones":
        return QCoreApplication.translate("TextosC", "aplicar las opciones del firewall")
    if ajuste == "firewall_regla":
        return QCoreApplication.translate("TextosC", "poner la regla del grupo de seguridad")
    return ""


def texto_ajuste_sustantivo_c(ajuste: str) -> str:
    """El ajuste de C como cosa pendiente («la red de la copia»); ``""`` si no es de C."""
    if ajuste == "red":
        return QCoreApplication.translate("TextosC", "la red de la copia")
    if ajuste == "firewall_opciones":
        return QCoreApplication.translate("TextosC", "las opciones del firewall")
    if ajuste == "firewall_regla":
        return QCoreApplication.translate("TextosC", "la regla del grupo de seguridad")
    return ""


# =============================================================================================
# Avisos de máquina (códigos en ``EntradaLibro.avisos``) y de la simulación
# =============================================================================================


def texto_aviso_c(codigo: str) -> str:
    """Texto de un aviso de la fase C; cadena vacía si no es de C."""
    base, _, detalle = codigo.partition(":")
    if base == AVISO_AJUSTE_PENDIENTE and detalle in ("red", "firewall_opciones", "firewall_regla"):
        return QCoreApplication.translate(
            "TextosC", "Se creó, pero falta aplicar {ajuste}. Puedes reintentar los ajustes."
        ).format(ajuste=texto_ajuste_sustantivo_c(detalle))
    if base == AVISO_FIREWALL_GRUPO_YA_ESTABA:
        return QCoreApplication.translate(
            "TextosC", "El grupo «{grupo}» ya estaba en la plantilla: no se añadió otra regla."
        ).format(grupo=detalle)
    if base == AVISO_FIREWALL_HEREDADO:
        return QCoreApplication.translate(
            "TextosC",
            "La plantilla ya traía firewall y reglas; la máquina las heredó y se sumó el grupo "
            "elegido.",
        )
    if base == AVISO_FIREWALL_INCOMPLETO_NO_ENCENDIDA:
        return QCoreApplication.translate(
            "TextosC",
            "No se encendió: la tarjeta {tarjeta} de la plantilla no tiene firewall. Revísala en "
            "Proxmox y enciéndela a mano.",
        ).format(tarjeta=detalle)
    if base == AVISO_RED_MAC_NUEVA:
        return QCoreApplication.translate(
            "TextosC", "La tarjeta {tarjeta} recibirá una dirección MAC nueva (Proxmox la genera)."
        ).format(tarjeta=detalle)
    if base == AVISO_RED_MTU_IGNORADA:
        return QCoreApplication.translate(
            "TextosC",
            "La MTU de la tarjeta {tarjeta} se ignora: solo vale con tarjetas VirtIO.",
        ).format(tarjeta=detalle)
    if base == AVISO_RED_TARJETA_ILEGIBLE:
        return QCoreApplication.translate(
            "TextosC",
            "La tarjeta {tarjeta} de la plantilla no se entiende: quedará sin tocar (sin "
            "firewall si lo activaste).",
        ).format(tarjeta=detalle)
    return ""


# =============================================================================================
# Resumen (RF-C0.1)
# =============================================================================================


def texto_tarjeta_pedida(t_: TarjetaClon) -> str:
    """Lo que se hará con una tarjeta del clon: «net1: cambiar a prod, VLAN 20»."""
    nombre = f"net{t_.indice}"
    if t_.accion == AccionTarjeta.QUITAR:
        return QCoreApplication.translate("TextosC", "{n}: quitar").format(n=nombre)
    partes: list[str] = []
    todos = t_.accion == AccionTarjeta.ANADIR
    if todos or CampoRed.BRIDGE in t_.fijados:
        partes.append(t_.bridge or "—")
    if (todos and t_.modelo) or CampoRed.MODELO in t_.fijados:
        partes.append(
            QCoreApplication.translate("TextosC", "tarjeta {m}").format(m=t_.modelo or "—")
        )
    if (todos and t_.vlan is not None) or CampoRed.VLAN in t_.fijados:
        partes.append(
            QCoreApplication.translate("TextosC", "VLAN {v}").format(v=t_.vlan)
            if t_.vlan is not None
            else QCoreApplication.translate("TextosC", "sin VLAN")
        )
    if (todos and t_.mtu is not None) or CampoRed.MTU in t_.fijados:
        partes.append(
            QCoreApplication.translate("TextosC", "MTU {v}").format(
                v=t_.mtu if t_.mtu is not None else "—"
            )
        )
    if (todos and t_.limite_mb is not None) or CampoRed.LIMITE in t_.fijados:
        partes.append(
            QCoreApplication.translate("TextosC", "límite {v} MB/s").format(v=f"{t_.limite_mb:g}")
            if t_.limite_mb is not None
            else QCoreApplication.translate("TextosC", "sin límite")
        )
    if t_.mac_nueva:
        partes.append(QCoreApplication.translate("TextosC", "MAC nueva"))
    accion = (
        QCoreApplication.translate("TextosC", "añadir")
        if todos
        else (
            QCoreApplication.translate("TextosC", "cambiar")
            if partes
            else QCoreApplication.translate("TextosC", "conservar")
        )
    )
    detalle = ", ".join(partes)
    return f"{nombre}: {accion}" + (f" ({detalle})" if detalle else "")


def lineas_red_clon(red: RedClon | None) -> list[tuple[str, str]]:
    """Línea del Resumen con los cambios de red del clon; vacía si la red es «Como la plantilla»."""
    if red is None or not usa_red_clon(red) or red.modo != ModoRedClon.PERSONALIZAR:
        return []
    acciones = [
        texto_tarjeta_pedida(x) for x in red.tarjetas if x.accion != AccionTarjeta.CONSERVAR
    ]
    if not acciones:
        return [
            (
                QCoreApplication.translate("TextosC", "Red de la copia"),
                QCoreApplication.translate("TextosC", "personalizada, sin cambios"),
            )
        ]
    return [(QCoreApplication.translate("TextosC", "Red de la copia"), "; ".join(acciones))]


def texto_firewall_resumen(cfg: ConfiguracionVM, tarjetas_sin_firewall: Sequence[str] = ()) -> str:
    """«activado, grupo web, entrada Bloquear, salida Permitir, DHCP sí».

    Si alguna tarjeta de la plantilla no se entiende (``tarjetas_sin_firewall``) no se dice solo
    «activado»: se matiza qué tarjetas quedan sin firewall (§9 de la arquitectura).
    """
    fw = cfg.firewall
    if not usa_firewall(fw) or fw is None:
        return ""
    if tarjetas_sin_firewall:
        activo = QCoreApplication.translate("TextosC", "activado salvo en {tarjetas}").format(
            tarjetas=", ".join(tarjetas_sin_firewall)
        )
    else:
        activo = QCoreApplication.translate("TextosC", "activado")
    partes = [activo]
    partes.append(
        QCoreApplication.translate("TextosC", "grupo {g}").format(g=fw.grupo)
        if fw.grupo
        else QCoreApplication.translate("TextosC", "sin grupo")
    )
    partes.append(
        QCoreApplication.translate("TextosC", "entrada {p}").format(
            p=texto_politica(fw.politica_entrada)
        )
    )
    partes.append(
        QCoreApplication.translate("TextosC", "salida {p}").format(
            p=texto_politica(fw.politica_salida)
        )
    )
    if fw.dhcp == ModoDhcp.SI:
        partes.append(QCoreApplication.translate("TextosC", "DHCP sí"))
    elif fw.dhcp == ModoDhcp.NO:
        partes.append(QCoreApplication.translate("TextosC", "DHCP no"))
    else:
        partes.append(QCoreApplication.translate("TextosC", "DHCP automático"))
    return ", ".join(partes)


def _tarjetas_ilegibles(problemas: Sequence[Problema]) -> list[str]:
    vistas: dict[str, None] = {}
    for p in problemas:
        if p.codigo == "V-C35" and p.params.get("motivo") == "tarjeta_ilegible":
            vistas[p.params.get("tarjeta", "")] = None
    return [x for x in vistas if x]


def lineas_opciones_fase_c(
    cfg: ConfiguracionVM, problemas: Sequence[Problema] = ()
) -> list[tuple[str, str]]:
    """Líneas «etiqueta, valor» del Resumen para la fase C: solo lo que difiere del valor por
    defecto; sin opciones de C no hay ninguna línea (CA-C0.1.3)."""
    lineas = lineas_red_clon(cfg.red_clon)
    texto = texto_firewall_resumen(cfg, _tarjetas_ilegibles(problemas))
    if texto:
        lineas.append((QCoreApplication.translate("TextosC", "Firewall"), texto))
        if cfg.firewall is not None and cfg.firewall.acepto_aislada and cfg.firewall.grupo is None:
            lineas.append(
                (
                    QCoreApplication.translate("TextosC", "Aislamiento"),
                    QCoreApplication.translate(
                        "TextosC", "aceptado: la máquina no aceptará conexiones por la red"
                    ),
                )
            )
    return lineas


# =============================================================================================
# «Qué puedo hacer en este servidor» (RF-C5.2)
# =============================================================================================

VIAS_FASE_C: tuple[Via, ...] = (
    Via.LOTES_SERVIDOR,
    Via.VNETS_SDN,
    Via.FIREWALL,
    Via.FIREWALL_GENERAL,
    Via.RED_CLON,
)


def texto_via_c(via: str) -> str:
    """Nombre de una fila de la fase C en «Qué puedo hacer»; ``""`` si no es de C."""
    if via == Via.LOTES_SERVIDOR:
        return QCoreApplication.translate("TextosC", "Ver y deshacer mis lotes en el servidor")
    if via == Via.VNETS_SDN:
        return QCoreApplication.translate("TextosC", "Usar redes virtuales (SDN)")
    if via == Via.FIREWALL:
        return QCoreApplication.translate("TextosC", "Activar el firewall de las máquinas")
    if via == Via.FIREWALL_GENERAL:
        return QCoreApplication.translate("TextosC", "Saber si el firewall general está encendido")
    if via == Via.RED_CLON:
        return QCoreApplication.translate("TextosC", "Cambiar la red de las copias")
    return ""


def texto_accion_via_c(via: str) -> str:
    """La acción de la fila como frase para «… para {acción}»; ``""`` si no es de C."""
    if via == Via.LOTES_SERVIDOR:
        return QCoreApplication.translate("TextosC", "ver y deshacer tus lotes en el servidor")
    if via == Via.VNETS_SDN:
        return QCoreApplication.translate("TextosC", "usar redes virtuales")
    if via == Via.FIREWALL:
        return QCoreApplication.translate("TextosC", "activar el firewall de las máquinas")
    if via == Via.FIREWALL_GENERAL:
        return QCoreApplication.translate("TextosC", "saber si el firewall general está encendido")
    if via == Via.RED_CLON:
        return QCoreApplication.translate("TextosC", "cambiar la red de las copias")
    return ""


def texto_estado_fila_c(estado: EstadoVia) -> str:
    """Estado de una fila de la fase C: «Sí», «No» o «No se pudo comprobar» (CA-C5.2.1-3)."""
    if estado.disponibilidad == Disponibilidad.SI:
        return QCoreApplication.translate("TextosC", "Sí")
    if estado.disponibilidad == Disponibilidad.NO:
        return QCoreApplication.translate("TextosC", "No")
    if estado.codigo is not None:
        # Sin permiso conocido pero sin bloquear nada (firewall general): se dice «No».
        return QCoreApplication.translate("TextosC", "No")
    return QCoreApplication.translate("TextosC", "No se pudo comprobar")


def texto_explicacion_fila_c(via: str, estado: EstadoVia) -> str:
    """Por qué una fila de C no está disponible; ``""`` si lo está. Con SDN, el comando para el
    administrador con marcadores (nunca datos reales)."""
    if estado.disponibilidad == Disponibilidad.SI:
        return ""
    if estado.disponibilidad == Disponibilidad.CON_AVISO and estado.codigo is None:
        return QCoreApplication.translate(
            "TextosC",
            "No se pudieron comprobar tus permisos. Puedes intentarlo; si falta alguno, "
            "ProxLaunch te dirá cuál.",
        )
    if via == Via.VNETS_SDN and estado.codigo == CodigoError.PERMISO_INSUFICIENTE:
        return QCoreApplication.translate(
            "TextosC",
            "Falta el permiso SDN.Use fuera de la zona «localnetwork». Para que un usuario use "
            "la red virtual <red> de la zona <zona>, el administrador ejecuta: pveum acl modify "
            "/sdn/zones/<zona>/<red> --roles PVESDNUser --users <usuario>. Para toda la zona: "
            "/sdn/zones/<zona>. Para una sola VLAN: /sdn/zones/<zona>/<red>/<vlan>.",
        )
    if via == Via.FIREWALL_GENERAL:
        return QCoreApplication.translate(
            "TextosC",
            "Falta el permiso Sys.Audit en «/»: no se puede saber si el firewall general está "
            "encendido. Solo pierdes ese aviso; la creación no se bloquea.",
        )
    return ""


# =============================================================================================
# Informe (RF-C0.7, RF-C3.8, RF-C4.8)
# =============================================================================================


def texto_riesgo_firewall_parcial() -> str:
    """Riesgo en llano de una máquina ``PARCIAL`` con el firewall a medias (CA-C3.8.5)."""
    return QCoreApplication.translate(
        "TextosC",
        "Riesgo: la máquina quedó a medias. Si el firewall ya está activo en sus tarjetas pero "
        "faltan sus opciones o la regla del grupo, usa las políticas por defecto de Proxmox y "
        "puede quedar sin conexión entrante. No se encendió. Reintenta los ajustes o usa la "
        "consola de Proxmox.",
    )


def _nombre_ajuste_aplicado(ajuste: str) -> str:
    nombres = {
        "red": QCoreApplication.translate("TextosC", "red aplicada"),
        "firewall_opciones": QCoreApplication.translate(
            "TextosC", "opciones de firewall aplicadas"
        ),
        "firewall_regla": QCoreApplication.translate("TextosC", "regla de grupo aplicada"),
    }
    return nombres.get(ajuste, "")


def texto_ajustes_c_de_entrada(aplicados: Sequence[str], pendientes: Sequence[str]) -> str:
    """«red aplicada; opciones de firewall aplicadas; regla de grupo no aplicada» (CA-C0.7.2)."""
    partes: list[str] = []
    for a in ("red", "firewall_opciones", "firewall_regla"):
        if a in aplicados:
            partes.append(_nombre_ajuste_aplicado(a))
        elif a in pendientes:
            partes.append(
                {
                    "red": QCoreApplication.translate("TextosC", "red no aplicada"),
                    "firewall_opciones": QCoreApplication.translate(
                        "TextosC", "opciones de firewall no aplicadas"
                    ),
                    "firewall_regla": QCoreApplication.translate(
                        "TextosC", "regla de grupo no aplicada"
                    ),
                }[a]
            )
    return "; ".join(partes)


def texto_tarjeta_final(f: TarjetaFinal) -> str:
    """Una tarjeta del resultado: «net0: virtio, red prod, VLAN 20, MAC conservada, firewall»."""
    partes = [
        f.modelo or "—",
        QCoreApplication.translate("TextosC", "red {r}").format(r=f.red or "—"),
    ]
    if f.vlan is not None:
        partes.append(QCoreApplication.translate("TextosC", "VLAN {v}").format(v=f.vlan))
    partes.append(
        QCoreApplication.translate("TextosC", "MAC conservada")
        if f.mac_conservada
        else QCoreApplication.translate("TextosC", "MAC nueva")
    )
    if f.firewall:
        partes.append(QCoreApplication.translate("TextosC", "con firewall"))
    return f"net{f.indice}: " + ", ".join(partes)


def lineas_red_final(finales: Sequence[TarjetaFinal]) -> list[str]:
    """Tarjetas finales y acciones («quitada net1», «añadida net2») para el informe."""
    lineas: list[str] = []
    for f in finales:
        if f.accion == AccionTarjeta.QUITAR:
            lineas.append(
                QCoreApplication.translate("TextosC", "quitada net{n}").format(n=f.indice)
            )
            continue
        if f.accion == AccionTarjeta.ANADIR:
            lineas.append(
                QCoreApplication.translate("TextosC", "añadida net{n}").format(n=f.indice)
            )
        lineas.append(texto_tarjeta_final(f))
    return lineas


def lineas_fase_c_de_entrada(
    entrada: EntradaLibro, aplicados: Sequence[str], pendientes: Sequence[str], riesgo: bool
) -> list[str]:
    """Líneas del informe de una máquina que usa la fase C (vacío si no usa nada)."""
    lineas: list[str] = []
    cfg = entrada.elemento.cfg
    if not (usa_red_clon(cfg.red_clon) or usa_firewall(cfg.firewall)):
        return lineas
    resumen = texto_ajustes_c_de_entrada(aplicados, pendientes)
    if resumen:
        lineas.append(resumen[0].upper() + resumen[1:] + ".")
    lineas.extend(lineas_red_final(entrada.red_final))
    if riesgo:
        lineas.append(texto_riesgo_firewall_parcial())
    return lineas


def texto_tooltip_reintentar_ajustes_c() -> str:
    return QCoreApplication.translate(
        "TextosC",
        "Vuelve a aplicar lo que no se pudo cambiar tras clonar: etiquetas, procesadores, "
        "memoria, tamaño del disco, la configuración inicial, la red o el firewall. No crea "
        "máquinas nuevas.",
    )


# =============================================================================================
# Simulación (§9): peticiones nuevas
# =============================================================================================


def texto_aviso_simulacion(codigo: str) -> str:
    """Aviso previo de la simulación o del Resumen (mismos códigos que el informe)."""
    return texto_aviso_c(codigo)
