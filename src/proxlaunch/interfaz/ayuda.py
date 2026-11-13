"""Textos de ayuda en lenguaje llano para los campos técnicos (RF-25).

Cada texto tiene de 1 a 3 frases y evita la jerga sin explicar. ``ayuda(campo)`` devuelve
el texto traducido; ``CAMPOS_AYUDA`` es la lista fija de campos que deben tenerlo (CA-25.1).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication

# Privilegios del rol ProxLaunchCreador (docs/investigacion/f1-api-proxmox.md §5).
PRIVILEGIOS_ROL = (
    "VM.Allocate",
    "VM.Audit",
    "VM.Config.Options",
    "VM.Config.HWType",
    "VM.Config.CPU",
    "VM.Config.Memory",
    "VM.Config.Network",
    "Datastore.AllocateSpace",
    "SDN.Use",
    "Sys.Audit",
)
NOMBRE_ROL = "ProxLaunchCreador"

_TEXTOS: dict[str, Callable[[], str]] = {
    "vmid": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el número que identifica a la máquina en todo el servidor y no se puede repetir. "
        "ProxLaunch propone el siguiente libre; solo cámbialo si necesitas uno concreto.",
    ),
    "nodo": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un nodo es cada servidor físico de tu clúster. En Automático ProxLaunch elige el que "
        "tiene más memoria y espacio libres; en Manual eliges tú dónde se crea la máquina.",
    ),
    "firmware": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el programa con el que arranca la máquina. SeaBIOS es el clásico y sirve para casi "
        "todo; UEFI (OVMF) es el moderno y lo piden algunos sistemas, como Windows 11.",
    ),
    "tipo_cpu": lambda: QCoreApplication.translate(
        "Ayuda",
        "Define qué procesador ve la máquina. El valor predeterminado funciona en servidores "
        "distintos; «host» rinde más pero impide mover la máquina entre nodos con "
        "procesadores diferentes.",
    ),
    "sockets": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un socket es un procesador físico virtual. Casi siempre basta con 1; sube los núcleos "
        "en lugar de los sockets.",
    ),
    "cores": lambda: QCoreApplication.translate(
        "Ayuda",
        "Cantidad de núcleos de cálculo por cada socket. El total de procesadores virtuales es "
        "sockets por núcleos.",
    ),
    "memoria": lambda: QCoreApplication.translate(
        "Ayuda",
        "Memoria RAM que tendrá la máquina, en GiB (1 GiB son 1024 MiB). Puedes usar decimales, "
        "por ejemplo 0,5 para medio GiB.",
    ),
    "ballooning": lambda: QCoreApplication.translate(
        "Ayuda",
        "Permite que el servidor recupere memoria que la máquina no está usando. Si lo activas "
        "indicas la memoria mínima que se le deja; «Predeterminado» deja que Proxmox decida.",
    ),
    "bus": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el tipo de conexión del disco virtual. SCSI es la opción recomendada; VirtIO es muy "
        "rápido pero necesita controladores en algunos sistemas; SATA e IDE son los más "
        "compatibles y los más lentos.",
    ),
    "controlador": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el controlador que gestiona los discos SCSI de la máquina. El predeterminado "
        "(virtio-scsi-single) es el mejor y es el único que permite IO Thread.",
    ),
    "formato": lambda: QCoreApplication.translate(
        "Ayuda",
        "Cómo se guarda el disco. Raw ocupa todo el espacio y es el más rápido; qcow2 crece "
        "según se usa y permite instantáneas. Algunos almacenamientos solo admiten raw.",
    ),
    "almacenamiento": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el lugar del servidor donde se guardará el disco. Se muestra el espacio libre de "
        "cada uno; ProxLaunch propone el que más tiene.",
    ),
    "tamano": lambda: QCoreApplication.translate(
        "Ayuda",
        "Tamaño del disco en GiB, siempre un número entero de 1 en adelante. El disco se crea "
        "vacío: el sistema operativo se instala después.",
    ),
    "discard": lambda: QCoreApplication.translate(
        "Ayuda",
        "Avisa al almacenamiento de qué espacio ya no se usa para que pueda recuperarlo. "
        "Conviene dejarlo activado.",
    ),
    "ssd": lambda: QCoreApplication.translate(
        "Ayuda",
        "Hace que el sistema vea el disco como una unidad de estado sólido (SSD), lo que "
        "mejora cómo lo trata. No está disponible en el bus VirtIO.",
    ),
    "iothread": lambda: QCoreApplication.translate(
        "Ayuda",
        "Dedica un hilo de trabajo propio a atender el disco, lo que mejora el rendimiento con "
        "mucha actividad. Necesita el bus VirtIO o SCSI con el controlador virtio-scsi-single.",
    ),
    "sin_disco": lambda: QCoreApplication.translate(
        "Ayuda",
        "Crea la máquina sin ningún disco. Es útil si vas a añadirlo o importarlo más tarde.",
    ),
    "bridge": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un bridge es el «conmutador virtual» del servidor que conecta la máquina a tu red. "
        "Lo habitual es vmbr0.",
    ),
    "modelo_red": lambda: QCoreApplication.translate(
        "Ayuda",
        "Tipo de tarjeta de red que ve la máquina. VirtIO es la más rápida; E1000 es más "
        "compatible con sistemas antiguos.",
    ),
    "vlan": lambda: QCoreApplication.translate(
        "Ayuda",
        "Número de red virtual (VLAN) para separar el tráfico, entre 1 y 4094. Déjalo vacío si "
        "tu red no usa VLAN.",
    ),
    "huella_ssl": lambda: QCoreApplication.translate(
        "Ayuda",
        "La huella es la «firma» del certificado del servidor. Comprueba que coincide con la "
        "que te dé tu administrador: así sabes que te conectas al servidor correcto y no a "
        "uno falso.",
    ),
    "ignorar_ssl": lambda: QCoreApplication.translate(
        "Ayuda",
        "Acepta cualquier certificado sin comprobarlo. Es inseguro: úsalo solo en redes de "
        "prueba que controles.",
    ),
    "tfa": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el segundo paso de seguridad de tu cuenta. Escribe el código de 6 números que "
        "muestra tu aplicación de autenticación, o usa una clave de recuperación si no puedes "
        "acceder a ella.",
    ),
    "recordar": lambda: QCoreApplication.translate(
        "Ayuda",
        "Guarda el token o la contraseña en el llavero de tu sistema (nunca en un archivo). "
        "Déjalo desmarcado en equipos compartidos.",
    ),
    "version_forzada": lambda: QCoreApplication.translate(
        "Ayuda",
        "Hace que ProxLaunch se comporte como si el servidor tuviera otra versión de Proxmox. "
        "Solo para casos especiales; normalmente se detecta sola.",
    ),
}

# Campos técnicos que deben tener ayuda (CA-25.1, CA-25.2).
CAMPOS_AYUDA: tuple[str, ...] = (
    "vmid",
    "nodo",
    "firmware",
    "tipo_cpu",
    "sockets",
    "cores",
    "ballooning",
    "bus",
    "formato",
    "discard",
    "ssd",
    "iothread",
    "bridge",
    "vlan",
    "huella_ssl",
    "tfa",
)


def ayuda(campo: str) -> str:
    """Texto de ayuda traducido de un campo; cadena vacía si no existe."""
    fabrica = _TEXTOS.get(campo)
    return fabrica() if fabrica is not None else ""


def ayuda_cpu_host() -> str:
    """Aviso que aparece al elegir el tipo de CPU ``host`` (CA-15.7)."""
    return QCoreApplication.translate(
        "Ayuda", "Rinde más pero impide mover la máquina entre nodos con procesadores distintos"
    )


# --- Guía «¿Cómo creo un API Token?» (CA-25.3) --------------------------------------


def titulo_guia_token() -> str:
    return QCoreApplication.translate("Ayuda", "¿Cómo creo un API Token?")


def pasos_guia_token() -> list[str]:
    """Pasos de la guía, en lenguaje llano."""
    return [
        QCoreApplication.translate(
            "Ayuda",
            "Entra en la página web de tu Proxmox y ve a Datacenter → Permisos → Roles → "
            "Crear. Llama al rol «{rol}» y marca los privilegios de la lista de abajo.",
        ).format(rol=NOMBRE_ROL),
        QCoreApplication.translate(
            "Ayuda",
            "Ve a Datacenter → Permisos → Usuarios y crea un usuario para ProxLaunch (por "
            "ejemplo «proxlaunch@pve»), o elige uno que ya tengas.",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "Ve a Datacenter → Permisos → Tokens de API → Añadir. Elige el usuario, escribe un "
            "nombre para el token (por ejemplo «lab») y pulsa Añadir. Copia el secreto que se "
            "muestra: solo aparece una vez.",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "Ve a Datacenter → Permisos → Añadir → Permiso de usuario (o de token). Ruta «/», "
            "elige el usuario o el token, rol «{rol}» y deja marcado «Propagar».",
        ).format(rol=NOMBRE_ROL),
        QCoreApplication.translate(
            "Ayuda",
            "En ProxLaunch pega el token completo con el formato usuario@realm!nombre=secreto, "
            "por ejemplo proxlaunch@pve!lab=11111111-2222-3333-4444-555555555555.",
        ),
    ]


def notas_guia_token() -> list[str]:
    """Recomendaciones de la guía (permisos mínimos y separación de privilegios)."""
    return [
        QCoreApplication.translate(
            "Ayuda",
            "Usa siempre un token con los permisos mínimos en lugar de root@pam: si el token se "
            "filtra, el daño es mucho menor y puedes revocarlo sin cambiar contraseñas.",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "Al crear el token puedes desmarcar «Separación de privilegios» solo si ya "
            "asignaste los permisos al usuario; si la dejas marcada, el token necesita sus "
            "propios permisos (paso 4 con el token).",
        ),
    ]


def privilegios_guia_token() -> str:
    """Privilegios del rol, uno por línea (se muestra en fuente monoespaciada)."""
    return "\n".join(PRIVILEGIOS_ROL)
