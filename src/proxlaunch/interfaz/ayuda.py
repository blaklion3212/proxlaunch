"""Textos de ayuda en lenguaje llano para los campos técnicos (RF-25).

Cada texto tiene de 1 a 3 frases y evita la jerga sin explicar. ``ayuda(campo)`` devuelve
el texto traducido; ``CAMPOS_AYUDA`` es la lista fija de campos que deben tenerlo (CA-25.1).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.lote.constantes import MAX_LOTE

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
    # --- Lotes (MVP 2, RF-L22) ---
    "lote_cantidad": lambda: QCoreApplication.translate(
        "Ayuda",
        "Cuántas máquinas iguales quieres crear de una vez, de 1 a {max}. Todas comparten la "
        "misma configuración del formulario y solo cambian el nombre y el número.",
    ).format(max=MAX_LOTE),
    "lote_prefijo": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el principio del nombre de todas las máquinas. Con «srv-web» se crean srv-web-01, "
        "srv-web-02, etc. Usa letras sin acentos, números y guiones.",
    ),
    "lote_separador": lambda: QCoreApplication.translate(
        "Ayuda",
        "Lo que va entre el prefijo y el número. Puede ser un guion («srv-01») o nada («srv01»).",
    ),
    "lote_inicio": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el número con el que empieza la numeración de los nombres. Con 5, las máquinas se "
        "llaman srv-05, srv-06, srv-07...",
    ),
    "lote_relleno": lambda: QCoreApplication.translate(
        "Ayuda",
        "Cuántos dígitos tiene como mínimo el número del nombre, completando con ceros: con 2 "
        "es «01» y con 3 es «001». Si hacen falta más dígitos, se usan en todos los nombres.",
    ),
    "lote_vmid_inicial": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el primer número de máquina (VMID) del lote; las demás usan los siguientes. Si "
        "alguno ya está ocupado se salta y se te avisa. Déjalo vacío para que ProxLaunch "
        "proponga uno.",
    ),
    "lote_destino": lambda: QCoreApplication.translate(
        "Ayuda",
        "Dónde se crean las máquinas. En Automático ProxLaunch las reparte entre los nodos "
        "del clúster que pueden alojarlas; en «Un nodo» van todas al que elijas.",
    ),
    "lote_nodos": lambda: QCoreApplication.translate(
        "Ayuda",
        "Marca los nodos entre los que se repartirán las máquinas. Solo se pueden elegir los "
        "que están en línea.",
    ),
    "lote_equilibrado": lambda: QCoreApplication.translate(
        "Ayuda",
        "Equilibrado manda cada máquina al nodo que tenga más memoria libre en ese momento "
        "(contando las que ya le tocaron), para que ninguno se llene antes que los demás.",
    ),
    "lote_por_turnos": lambda: QCoreApplication.translate(
        "Ayuda",
        "Por turnos reparte las máquinas una a cada nodo, en orden alfabético, y vuelve a "
        "empezar. Es predecible, pero no tiene en cuenta cuánta memoria le queda a cada nodo.",
    ),
    "lote_sobreasignacion": lambda: QCoreApplication.translate(
        "Ayuda",
        "Algunos almacenamientos prometen el espacio de los discos pero no lo reservan hasta "
        "que se usa. Puedes crear más discos de los que caben, y funciona mientras no se "
        "llenen; si se llenan, todas las máquinas de ese almacenamiento pueden fallar.",
    ),
    "lote_simulacion": lambda: QCoreApplication.translate(
        "Ayuda",
        "Simular hace todas las comprobaciones y muestra qué se enviaría a Proxmox, pero no "
        "crea nada ni cambia nada en el servidor.",
    ),
    "lote_deshacer": lambda: QCoreApplication.translate(
        "Ayuda",
        "Elimina de Proxmox las máquinas que creó este lote, con sus discos. Solo toca las "
        "que ProxLaunch puede demostrar que creó él, y nunca se hace sin que lo confirmes.",
    ),
    "lote_etiqueta": lambda: QCoreApplication.translate(
        "Ayuda",
        "Marca cada máquina con las etiquetas «proxlaunch» y «lote-» más un código, visibles "
        "en Proxmox. Sirven para reconocer lo que creó este lote y poder deshacerlo con "
        "seguridad. Si tu servidor no admite etiquetas nuevas, desactívalo.",
    ),
    "perfil": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un perfil de máquina guarda el hardware de una máquina virtual (procesadores, memoria, "
        "discos y red). Al elegirlo se rellena el formulario; el nombre, el número y el nodo "
        "siguen siendo tuyos.",
    ),
    "perfil_fabrica": lambda: QCoreApplication.translate(
        "Ayuda",
        "Los perfiles de fábrica vienen con ProxLaunch y no se pueden cambiar ni borrar. Si "
        "quieres una variante, duplícalo y haz tu propia versión.",
    ),
    "perfil_pistas": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un perfil puede recordar el almacenamiento y la red que usaba. Si en este servidor no "
        "existen, ProxLaunch usa los predeterminados y te avisa; nunca inventa nada.",
    ),
    "perfil_guardar": lambda: QCoreApplication.translate(
        "Ayuda",
        "Guarda el hardware actual del formulario como perfil de máquina para reutilizarlo. No "
        "guarda el nombre, el número ni el nodo de la máquina.",
    ),
    "perfil_exportar": lambda: QCoreApplication.translate(
        "Ayuda",
        "Exportar crea un archivo con tus perfiles para compartirlos. Por defecto no incluye los "
        "nombres de almacenamiento y de red de tu servidor.",
    ),
    "perfil_importar": lambda: QCoreApplication.translate(
        "Ayuda",
        "Importar añade perfiles de un archivo. Antes de guardar nada verás una lista para "
        "elegir cuáles, y si un nombre ya existe puedes conservar ambos.",
    ),
    "perfil_compatibilidad": lambda: QCoreApplication.translate(
        "Ayuda",
        "Indica si el perfil funciona con la versión de Proxmox y con el servidor al que estás "
        "conectado. Los avisos no impiden crear la máquina; los errores sí.",
    ),
    "lote_guardado": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un lote guardado es un archivo con la definición de un lote (hardware, cantidad, "
        "nombres y reparto) para repetirlo. No guarda datos de conexión ni contraseñas; al "
        "abrirlo se vuelve a comprobar todo.",
    ),
    "csv": lambda: QCoreApplication.translate(
        "Ayuda",
        "Importar desde CSV crea un lote con una máquina por cada fila de una hoja de cálculo. "
        "Antes de crear nada verás una vista previa y un resumen que debes confirmar.",
    ),
    "csv_plantilla": lambda: QCoreApplication.translate(
        "Ayuda",
        "Descarga un archivo CSV de ejemplo con todas las columnas y dos filas de muestra. "
        "Ábrelo en tu hoja de cálculo, cambia los datos y guárdalo como CSV.",
    ),
    "csv_separador": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es el carácter que separa las columnas: punto y coma, coma o tabulador. ProxLaunch lo "
        "detecta solo; cámbialo si la vista previa se ve mal.",
    ),
    "csv_codificacion": lambda: QCoreApplication.translate(
        "Ayuda",
        "Es la forma en que el archivo guarda los acentos. ProxLaunch la detecta sola; si ves "
        "letras raras, prueba otra o guarda el archivo como «CSV UTF-8» desde Excel.",
    ),
    "csv_unidades": lambda: QCoreApplication.translate(
        "Ayuda",
        "Memoria y disco sin unidad se leen en GiB. También puedes escribir MiB, GiB o TiB "
        "(por ejemplo «4 GiB»). Evita los separadores de miles: «1.000» es ambiguo.",
    ),
    "csv_vista_previa": lambda: QCoreApplication.translate(
        "Ayuda",
        "Muestra cada fila del archivo con su estado y sus problemas. Puedes excluir filas "
        "antes de continuar; nada se crea hasta que confirmes el resumen del lote.",
    ),
    "lote_por_filas": lambda: QCoreApplication.translate(
        "Ayuda",
        "En un lote por filas cada máquina tiene su propia configuración, como venía en el "
        "archivo. Para cambiar algo, corrige el archivo e impórtalo de nuevo.",
    ),
    "lote_envio_incierto": lambda: QCoreApplication.translate(
        "Ayuda",
        "Si se corta la conexión justo al enviar una máquina, no se sabe si Proxmox llegó a "
        "crearla. ProxLaunch nunca la vuelve a enviar sola, porque podría duplicarla: usa "
        "«Comprobar» para ver si existe.",
    ),
}

# Ayudas del lote que deben tener texto (CA-L22.4).
CAMPOS_AYUDA_LOTE: tuple[str, ...] = (
    "lote_cantidad",
    "lote_prefijo",
    "lote_separador",
    "lote_inicio",
    "lote_relleno",
    "lote_vmid_inicial",
    "lote_destino",
    "lote_nodos",
    "lote_equilibrado",
    "lote_por_turnos",
    "lote_sobreasignacion",
    "lote_simulacion",
    "lote_deshacer",
    "lote_etiqueta",
    "lote_envio_incierto",
)

# Ayudas del MVP 3 que deben tener texto (CA-P11.3).
CAMPOS_AYUDA_MVP3: tuple[str, ...] = (
    "perfil",
    "perfil_fabrica",
    "perfil_pistas",
    "perfil_guardar",
    "perfil_exportar",
    "perfil_importar",
    "perfil_compatibilidad",
    "lote_guardado",
    "csv",
    "csv_plantilla",
    "csv_separador",
    "csv_codificacion",
    "csv_unidades",
    "csv_vista_previa",
    "lote_por_filas",
)

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
