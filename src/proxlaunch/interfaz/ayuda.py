"""Textos de ayuda en lenguaje llano para los campos técnicos (RF-25).

Cada texto tiene de 1 a 3 frases y evita la jerga sin explicar. ``ayuda(campo)`` devuelve
el texto traducido; ``CAMPOS_AYUDA`` es la lista fija de campos que deben tenerlo (CA-25.1).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication

from proxlaunch.nucleo.lote.constantes import MAX_LOTE
from proxlaunch.nucleo.origen.permisos import PRIVILEGIOS_OPCIONALES, ROL_PROXLAUNCH

# Privilegios del rol ProxLaunchCreador: los 10 de siempre y los 4 del MVP 4 (RF-O24). La lista
# vive en el núcleo (única fuente); aquí solo se muestra.
PRIVILEGIOS_ROL: tuple[str, ...] = ROL_PROXLAUNCH
NOMBRE_ROL = "ProxLaunchCreador"
# Segundo rol del alcance acotado para la ruta «/vms»: los privilegios de máquina SIN VM.Clone,
# de modo que clonar solo valga para las plantillas del pool (SEG-M4-01).
NOMBRE_ROL_MAQUINAS = "ProxLaunchMaquinas"
PRIVILEGIOS_ROL_MAQUINAS: tuple[str, ...] = tuple(
    p for p in ROL_PROXLAUNCH if p.startswith("VM.") and p != "VM.Clone"
)

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
    "origen": lambda: QCoreApplication.translate(
        "Ayuda",
        "Aquí eliges de dónde sale el sistema operativo de la máquina: un disco vacío, un ISO de "
        "instalación, un disco ya hecho que se importa o la copia de una plantilla de Proxmox. "
        "Si no sabes cuál, usa un ISO para instalar desde cero o una plantilla para empezar con "
        "algo ya instalado.",
    ),
    "iso": lambda: QCoreApplication.translate(
        "Ayuda",
        "Un ISO es la imagen del disco de instalación de un sistema operativo, como el CD con "
        "el que se instalaría. La máquina arranca desde él y tú terminas la instalación desde "
        "la consola de Proxmox.",
    ),
    "subir": lambda: QCoreApplication.translate(
        "Ayuda",
        "Sube un archivo de tu equipo al servidor de Proxmox para poder usarlo. ProxLaunch no "
        "puede borrar lo que subes: si ya no lo necesitas, pídele a un administrador que lo "
        "elimine desde Proxmox.",
    ),
    "descargar_url": lambda: QCoreApplication.translate(
        "Ayuda",
        "El propio servidor de Proxmox descarga el archivo desde la dirección web que indiques, "
        "sin pasar por tu equipo. Usa solo direcciones https de confianza y, si puedes, escribe "
        "también la huella del archivo para comprobarlo.",
    ),
    "checksum": lambda: QCoreApplication.translate(
        "Ayuda",
        "La huella (checksum) es un código que identifica un archivo. Si la escribes, Proxmox "
        "comprueba al terminar que lo descargado coincide y, si no, descarta el archivo.",
    ),
    "asistente_so": lambda: QCoreApplication.translate(
        "Ayuda",
        "El asistente ajusta la máquina al sistema que vas a instalar: tipo de arranque, TPM, "
        "controlador de discos y tarjeta de red. Te muestra cada cambio y no toca los núcleos, "
        "la memoria ni el tamaño del disco.",
    ),
    "drivers_virtio": lambda: QCoreApplication.translate(
        "Ayuda",
        "Windows no trae los controladores de los discos y la red virtuales de Proxmox. Por eso "
        "se añade un segundo CD, llamado virtio-win, para cargarlos durante la instalación.",
    ),
    "importar": lambda: QCoreApplication.translate(
        "Ayuda",
        "Importar crea la máquina a partir de un disco que ya tiene un sistema instalado, en "
        "lugar de empezar vacía. Necesita una imagen en el servidor, guardada en un "
        "almacenamiento con el contenido «Import» activado.",
    ),
    "formatos_disco": lambda: QCoreApplication.translate(
        "Ayuda",
        "qcow2, raw y vmdk son formas de guardar un disco virtual y ProxLaunch acepta las tres. "
        "Tiene que ser un solo archivo: un disco que depende de otro o está cifrado no se puede "
        "importar.",
    ),
    "copia_por_mv": lambda: QCoreApplication.translate(
        "Ayuda",
        "Cada máquina del lote recibe su propia copia del disco, así que ocupa espacio propio. "
        "Con muchas máquinas el espacio necesario se multiplica.",
    ),
    "plantilla": lambda: QCoreApplication.translate(
        "Ayuda",
        "Una plantilla de Proxmox es una máquina ya instalada que se marcó como modelo. Al "
        "clonarla obtienes máquinas nuevas con su mismo sistema, sin instalar nada.",
    ),
    "enlazado_completo": lambda: QCoreApplication.translate(
        "Ayuda",
        "«Rápido y ligero» (enlazado) comparte los datos con la plantilla: se crea en segundos "
        "y casi no ocupa espacio, pero depende de ella. «Copia independiente» (completo) "
        "duplica todo el disco: tarda más y ocupa más, pero la máquina no depende de nada.",
    ),
    "storage_recordado": lambda: QCoreApplication.translate(
        "Ayuda",
        "ProxLaunch recuerda, para cada servidor, el almacenamiento que usaste para ISOs, "
        "imágenes y discos. La próxima vez lo propone solo; si deja de estar disponible te lo "
        "diremos y podrás elegir otro.",
    ),
    "permisos_rol_ampliado": lambda: QCoreApplication.translate(
        "Ayuda",
        "Para usar ISOs, importar discos y clonar plantillas, el rol de ProxLaunch necesita "
        "cuatro permisos más que antes. Si faltan, crear máquinas vacías sigue funcionando y "
        "solo se desactivan esas opciones, indicando qué permiso falta.",
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

# Ayudas del origen del sistema operativo que deben tener texto (CA-O32.1).
CAMPOS_AYUDA_ORIGEN: tuple[str, ...] = (
    "origen",
    "iso",
    "subir",
    "descargar_url",
    "checksum",
    "asistente_so",
    "drivers_virtio",
    "importar",
    "formatos_disco",
    "copia_por_mv",
    "plantilla",
    "enlazado_completo",
    "storage_recordado",
    "permisos_rol_ampliado",
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
            "Ve a Datacenter → Permisos → Añadir → Permiso de usuario (o de token) y da al "
            "usuario o al token los permisos. Lo más seguro es el alcance acotado de abajo; la "
            "alternativa simple es una sola asignación en la ruta «/».",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "En ProxLaunch pega el token completo con el formato usuario@realm!nombre=secreto, "
            "por ejemplo proxlaunch@pve!lab=11111111-2222-3333-4444-555555555555.",
        ),
    ]


def permisos_acotados() -> list[str]:
    """Asignaciones del alcance acotado (recomendado), una por línea y en lenguaje llano.

    Coherentes con las rutas donde la aplicación comprueba cada privilegio: ``/vms`` (crear),
    ``/vms/<id>`` de la plantilla (clonar), ``/storage/<almacenamiento>``, ``/nodes/<nodo>``,
    ``/sdn/zones/localnetwork`` y ``/`` (solo ver el estado, sin propagar).
    """
    return [
        QCoreApplication.translate(
            "Ayuda",
            "Pool de plantillas: en Datacenter → Permisos → Pools crea un pool (por ejemplo "
            "«plantillas-proxlaunch») y añade solo las plantillas que ProxLaunch podrá clonar. "
            "Luego añade el permiso en la ruta «/pool/plantillas-proxlaunch» con el rol «{rol}» "
            "y «Propagar». Así VM.Clone vale solo para esas plantillas: las demás pueden verse "
            "en la lista, pero ProxLaunch no las clonará.",
        ).format(rol=NOMBRE_ROL),
        QCoreApplication.translate(
            "Ayuda",
            "Crear máquinas: crea un segundo rol, «{rol}», con los privilegios de máquina del "
            "rol anterior SIN VM.Clone ({privilegios}) y asígnalo en la ruta «/vms» con "
            "«Propagar».",
        ).format(rol=NOMBRE_ROL_MAQUINAS, privilegios=", ".join(PRIVILEGIOS_ROL_MAQUINAS)),
        QCoreApplication.translate(
            "Ayuda",
            "Almacenamientos: en la ruta «/storage/<almacenamiento>» con el rol «{rol}», solo "
            "en los que usarás para ISOs, imágenes de disco importadas y discos de las máquinas "
            "(Datastore.AllocateTemplate y Datastore.AllocateSpace).",
        ).format(rol=NOMBRE_ROL),
        QCoreApplication.translate(
            "Ayuda",
            "Nodos: en la ruta «/nodes/<nodo>» con el rol «{rol}», solo en los nodos que "
            "descargarán archivos desde una dirección web (Sys.AccessNetwork).",
        ).format(rol=NOMBRE_ROL),
        QCoreApplication.translate(
            "Ayuda",
            "Red y estado: en la ruta «/sdn/zones/localnetwork» (SDN.Use) y en la ruta «/» "
            "con el rol «{rol}» pero SIN «Propagar» (Sys.Audit, solo para ver el estado de los "
            "nodos).",
        ).format(rol=NOMBRE_ROL),
    ]


def alternativa_simple_permisos() -> str:
    """Alternativa simple: el rol completo en «/» con «Propagar», con su riesgo explicado."""
    return QCoreApplication.translate(
        "Ayuda",
        "Alternativa simple: asigna el rol «{rol}» una sola vez en la ruta «/» con «Propagar». "
        "Es más cómodo, pero el permiso alcanza a todo el servidor: quien consiga el token podría "
        "clonar cualquier máquina y leer sus discos, subir archivos a cualquier almacenamiento y "
        "hacer que los nodos descarguen direcciones web. Úsalo solo en un laboratorio o si "
        "confías plenamente en quien guarde el token.",
    ).format(rol=NOMBRE_ROL)


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
        QCoreApplication.translate(
            "Ayuda",
            "Los últimos cuatro privilegios de la lista sirven para instalar desde un ISO, "
            "importar discos y clonar plantillas. Si los omites, crear máquinas vacías sigue "
            "funcionando y ProxLaunch solo desactiva esas opciones.",
        ),
        nota_archivos_subidos(),
    ]


def privilegios_guia_token() -> str:
    """Privilegios del rol, uno por línea (se muestra en fuente monoespaciada)."""
    return "\n".join(PRIVILEGIOS_ROL)


def descripcion_privilegio(privilegio: str) -> str:
    """Para qué sirve cada privilegio del rol, en lenguaje llano ("" si no se conoce)."""
    textos: dict[str, Callable[[], str]] = {
        "VM.Allocate": lambda: QCoreApplication.translate("Ayuda", "crear máquinas"),
        "VM.Audit": lambda: QCoreApplication.translate("Ayuda", "ver las máquinas del servidor"),
        "VM.Config.Options": lambda: QCoreApplication.translate(
            "Ayuda", "ajustar nombre, etiquetas y opciones generales"
        ),
        "VM.Config.HWType": lambda: QCoreApplication.translate(
            "Ayuda", "elegir el tipo de equipo y de arranque"
        ),
        "VM.Config.CPU": lambda: QCoreApplication.translate("Ayuda", "configurar procesadores"),
        "VM.Config.Memory": lambda: QCoreApplication.translate("Ayuda", "configurar la memoria"),
        "VM.Config.Network": lambda: QCoreApplication.translate(
            "Ayuda", "configurar las tarjetas de red"
        ),
        "Datastore.AllocateSpace": lambda: QCoreApplication.translate(
            "Ayuda", "crear discos en los almacenamientos"
        ),
        "SDN.Use": lambda: QCoreApplication.translate("Ayuda", "usar las redes del servidor"),
        "Sys.Audit": lambda: QCoreApplication.translate("Ayuda", "ver el estado de los nodos"),
        "VM.Config.Disk": lambda: QCoreApplication.translate(
            "Ayuda", "fijar el orden de arranque con ISO y ampliar discos"
        ),
        "VM.Clone": lambda: QCoreApplication.translate("Ayuda", "clonar plantillas"),
        "Datastore.AllocateTemplate": lambda: QCoreApplication.translate(
            "Ayuda", "subir y descargar ISOs e imágenes de disco"
        ),
        "Sys.AccessNetwork": lambda: QCoreApplication.translate(
            "Ayuda", "que el servidor descargue archivos desde una dirección web"
        ),
        "VM.PowerMgmt": lambda: QCoreApplication.translate(
            "Ayuda", "encender máquinas al terminar y apagarlas a la fuerza al deshacer"
        ),
        "Pool.Audit": lambda: QCoreApplication.translate("Ayuda", "ver la lista de pools"),
    }
    fabrica = textos.get(privilegio)
    return fabrica() if fabrica is not None else ""


# Privilegios añadidos en el MVP 4 y lo que se pierde sin cada uno (RF-O24, CA-O24.3).
PRIVILEGIOS_NUEVOS: tuple[str, ...] = (
    "VM.Config.Disk",
    "VM.Clone",
    "Datastore.AllocateTemplate",
    "Sys.AccessNetwork",
)


def funcion_perdida_sin_privilegio(privilegio: str) -> str:
    """Qué deja de poder hacerse sin uno de los cuatro privilegios nuevos ("" si no aplica)."""
    if privilegio == "VM.Config.Disk":
        return QCoreApplication.translate(
            "Ayuda",
            "sin él no se fija el orden de arranque con un ISO ni se amplían discos",
        )
    if privilegio == "VM.Clone":
        return QCoreApplication.translate("Ayuda", "sin él no se pueden clonar plantillas")
    if privilegio == "Datastore.AllocateTemplate":
        return QCoreApplication.translate(
            "Ayuda", "sin él no se pueden subir ni descargar ISOs o imágenes de disco"
        )
    if privilegio == "Sys.AccessNetwork":
        return QCoreApplication.translate(
            "Ayuda", "sin él el servidor no puede descargar archivos desde una dirección web"
        )
    return ""


def notas_privilegios_nuevos() -> list[str]:
    """Una línea por privilegio nuevo del rol: «VM.Clone: sin él no se pueden clonar…»."""
    return [f"{p}: {funcion_perdida_sin_privilegio(p)}" for p in PRIVILEGIOS_NUEVOS]


# --- Fase A: privilegios opcionales (RF-A8.1, RF-A8.2) ------------------------------------------


def titulo_privilegios_opcionales() -> str:
    """Título de la sección de la guía sobre los privilegios que no forman parte del rol."""
    return QCoreApplication.translate("Ayuda", "Privilegios opcionales")


def intro_privilegios_opcionales() -> str:
    return QCoreApplication.translate(
        "Ayuda",
        "No forman parte del rol «{rol}» y no hacen falta para crear máquinas: sin ellos "
        "ProxLaunch solo desactiva la opción afectada y te explica por qué.",
    ).format(rol=NOMBRE_ROL)


def efecto_privilegio_opcional(privilegio: str) -> str:
    """Qué habilita un privilegio opcional ("" si no se conoce)."""
    if privilegio == "VM.PowerMgmt":
        return QCoreApplication.translate(
            "Ayuda",
            "permite «Encender al terminar» y apagar a la fuerza las máquinas encendidas del "
            "lote al usar Deshacer. Debe concederse en «/vms» (no solo en una máquina concreta) "
            "para que «Encender al terminar» se habilite. Sin él, esas máquinas encendidas no "
            "se tocan.",
        )
    if privilegio == "Pool.Audit":
        return QCoreApplication.translate(
            "Ayuda",
            "permite ver la lista de pools para elegir uno. Sin él no se puede elegir pool, "
            "aunque existan.",
        )
    return ""


def privilegios_opcionales_guia() -> list[str]:
    """Una línea por privilegio opcional: «VM.PowerMgmt en «/vms»: permite…»."""
    return [
        QCoreApplication.translate("Ayuda", "{privilegio} en «{ruta}»: {efecto}").format(
            privilegio=privilegio, ruta=ruta, efecto=efecto_privilegio_opcional(privilegio)
        )
        for privilegio, ruta in PRIVILEGIOS_OPCIONALES
    ]


def nota_sys_modify() -> str:
    """Sys.Modify no se pide (solo lo tiene Administrator)."""
    return QCoreApplication.translate(
        "Ayuda",
        "ProxLaunch no pide el privilegio Sys.Modify, que solo tiene el rol Administrator. No "
        "hace falta darlo.",
    )


def nota_etiquetas_administrador() -> str:
    """Cómo el administrador autoriza las etiquetas de usuario."""
    return QCoreApplication.translate(
        "Ayuda",
        "Las etiquetas propias dependen de la política del servidor: si Proxmox solo admite "
        "etiquetas autorizadas, el administrador debe añadirlas en Datacenter → Opciones → "
        "Etiquetas (lista de etiquetas permitidas a usuarios, «user-allow-list», o etiquetas "
        "registradas, «registered-tags»).",
    )


def notas_opcionales_guia() -> list[str]:
    """Notas de la sección «Privilegios opcionales»: Sys.Modify y etiquetas autorizadas."""
    return [nota_sys_modify(), nota_etiquetas_administrador()]


def nota_archivos_subidos() -> str:
    """La app no puede borrar lo que sube (RF-O25, CA-O25.4)."""
    return QCoreApplication.translate(
        "Ayuda",
        "ProxLaunch no puede borrar los ISOs ni las imágenes que subas o descargues, ni siquiera "
        "con un usuario administrador. Si ya no los necesitas, bórralos desde Proxmox (en el "
        "almacenamiento, sección «ISO Images» o «Import»).",
    )


def texto_pedir_al_administrador() -> str:
    """Texto listo para copiar y enviar al administrador de Proxmox (CA-O32.2)."""
    lineas = [
        QCoreApplication.translate(
            "Ayuda",
            "Hola. Para que ProxLaunch pueda instalar máquinas desde un ISO, importar discos y "
            "clonar plantillas necesito lo siguiente en Proxmox:",
        ),
        "",
        QCoreApplication.translate(
            "Ayuda",
            "1. Un rol llamado «{rol}» (Datacenter → Permisos → Roles → Crear) con estos {n} "
            "privilegios:",
        ).format(rol=NOMBRE_ROL, n=len(PRIVILEGIOS_ROL)),
    ]
    for privilegio in PRIVILEGIOS_ROL:
        lineas.append(f"   - {privilegio}: {descripcion_privilegio(privilegio)}")
    lineas += [
        "",
        QCoreApplication.translate(
            "Ayuda",
            "2. Asignar los permisos a mi usuario o a mi token solo donde hacen falta "
            "(Datacenter → Permisos → Añadir). Opción recomendada, de alcance acotado:",
        ),
        *[f"   - {linea}" for linea in permisos_acotados()],
        "   - " + alternativa_simple_permisos(),
        QCoreApplication.translate(
            "Ayuda",
            "3. Para importar discos: activar el contenido «Import» en un almacenamiento de tipo "
            "directorio, NFS o CIFS (Datacenter → Almacenamiento → Editar → Contenido). Hace "
            "falta Proxmox 8.4 o superior.",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "4. Para clonar: convertir en plantilla una máquina ya instalada (clic derecho en la "
            "máquina → Convertir en plantilla).",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "5. Los ISOs e imágenes que suba no los puede borrar ProxLaunch: habrá que eliminarlos "
            "desde Proxmox cuando ya no hagan falta.",
        ),
        QCoreApplication.translate(
            "Ayuda",
            "6. Opcional: para encender las máquinas al terminar y apagarlas a la fuerza al "
            "deshacer, el privilegio VM.PowerMgmt en «/vms»; para elegir un pool, Pool.Audit en "
            "«/pool». No forman parte del rol.",
        ),
        *[f"   - {linea}" for linea in privilegios_opcionales_guia()],
        "   - " + nota_etiquetas_administrador(),
    ]
    return "\n".join(lineas)
