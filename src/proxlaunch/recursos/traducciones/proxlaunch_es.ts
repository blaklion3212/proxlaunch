<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="es" sourcelanguage="es">
<context>
    <name>ArchivosUi</name>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="60"/>
        <source>Perfiles de ProxLaunch (*.json)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="62"/>
        <source>Lotes de ProxLaunch (*.json)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="63"/>
        <source>CSV (*.csv *.txt)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="92"/>
        <source>Abrir archivo de perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="93"/>
        <source>Abrir lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="94"/>
        <source>Elegir archivo CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="118"/>
        <source>Exportar perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="119"/>
        <source>Guardar lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="120"/>
        <source>Guardar archivo CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="143"/>
        <source>; (Excel en español)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="144"/>
        <source>, (Excel en inglés)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="148"/>
        <source>Descargar plantilla CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="149"/>
        <source>Separador de columnas:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="179"/>
        <source>plantilla-proxlaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/archivos_ui.py" line="210"/>
        <source>Ayuda</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Ayuda</name>
    <message>
        <location filename="../../interfaz/ayuda.py" line="33"/>
        <source>Es el número que identifica a la máquina en todo el servidor y no se puede repetir. ProxLaunch propone el siguiente libre; solo cámbialo si necesitas uno concreto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="38"/>
        <source>Un nodo es cada servidor físico de tu clúster. En Automático ProxLaunch elige el que tiene más memoria y espacio libres; en Manual eliges tú dónde se crea la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="43"/>
        <source>Es el programa con el que arranca la máquina. SeaBIOS es el clásico y sirve para casi todo; UEFI (OVMF) es el moderno y lo piden algunos sistemas, como Windows 11.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="48"/>
        <source>Define qué procesador ve la máquina. El valor predeterminado funciona en servidores distintos; «host» rinde más pero impide mover la máquina entre nodos con procesadores diferentes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="54"/>
        <source>Un socket es un procesador físico virtual. Casi siempre basta con 1; sube los núcleos en lugar de los sockets.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="59"/>
        <source>Cantidad de núcleos de cálculo por cada socket. El total de procesadores virtuales es sockets por núcleos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="64"/>
        <source>Memoria RAM que tendrá la máquina, en GiB (1 GiB son 1024 MiB). Puedes usar decimales, por ejemplo 0,5 para medio GiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="69"/>
        <source>Permite que el servidor recupere memoria que la máquina no está usando. Si lo activas indicas la memoria mínima que se le deja; «Predeterminado» deja que Proxmox decida.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="74"/>
        <source>Es el tipo de conexión del disco virtual. SCSI es la opción recomendada; VirtIO es muy rápido pero necesita controladores en algunos sistemas; SATA e IDE son los más compatibles y los más lentos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="80"/>
        <source>Es el controlador que gestiona los discos SCSI de la máquina. El predeterminado (virtio-scsi-single) es el mejor y es el único que permite IO Thread.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="85"/>
        <source>Cómo se guarda el disco. Raw ocupa todo el espacio y es el más rápido; qcow2 crece según se usa y permite instantáneas. Algunos almacenamientos solo admiten raw.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="90"/>
        <source>Es el lugar del servidor donde se guardará el disco. Se muestra el espacio libre de cada uno; ProxLaunch propone el que más tiene.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="95"/>
        <source>Tamaño del disco en GiB, siempre un número entero de 1 en adelante. El disco se crea vacío: el sistema operativo se instala después.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="100"/>
        <source>Avisa al almacenamiento de qué espacio ya no se usa para que pueda recuperarlo. Conviene dejarlo activado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="105"/>
        <source>Hace que el sistema vea el disco como una unidad de estado sólido (SSD), lo que mejora cómo lo trata. No está disponible en el bus VirtIO.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="110"/>
        <source>Dedica un hilo de trabajo propio a atender el disco, lo que mejora el rendimiento con mucha actividad. Necesita el bus VirtIO o SCSI con el controlador virtio-scsi-single.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="115"/>
        <source>Crea la máquina sin ningún disco. Es útil si vas a añadirlo o importarlo más tarde.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="119"/>
        <source>Un bridge es el «conmutador virtual» del servidor que conecta la máquina a tu red. Lo habitual es vmbr0.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="124"/>
        <source>Tipo de tarjeta de red que ve la máquina. VirtIO es la más rápida; E1000 es más compatible con sistemas antiguos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="129"/>
        <source>Número de red virtual (VLAN) para separar el tráfico, entre 1 y 4094. Déjalo vacío si tu red no usa VLAN.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="134"/>
        <source>La huella es la «firma» del certificado del servidor. Comprueba que coincide con la que te dé tu administrador: así sabes que te conectas al servidor correcto y no a uno falso.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="140"/>
        <source>Acepta cualquier certificado sin comprobarlo. Es inseguro: úsalo solo en redes de prueba que controles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="145"/>
        <source>Es el segundo paso de seguridad de tu cuenta. Escribe el código de 6 números que muestra tu aplicación de autenticación, o usa una clave de recuperación si no puedes acceder a ella.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="151"/>
        <source>Guarda el token o la contraseña en el llavero de tu sistema (nunca en un archivo). Déjalo desmarcado en equipos compartidos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="156"/>
        <source>Hace que ProxLaunch se comporte como si el servidor tuviera otra versión de Proxmox. Solo para casos especiales; normalmente se detecta sola.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="162"/>
        <source>Cuántas máquinas iguales quieres crear de una vez, de 1 a {max}. Todas comparten la misma configuración del formulario y solo cambian el nombre y el número.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="167"/>
        <source>Es el principio del nombre de todas las máquinas. Con «srv-web» se crean srv-web-01, srv-web-02, etc. Usa letras sin acentos, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="172"/>
        <source>Lo que va entre el prefijo y el número. Puede ser un guion («srv-01») o nada («srv01»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="176"/>
        <source>Es el número con el que empieza la numeración de los nombres. Con 5, las máquinas se llaman srv-05, srv-06, srv-07...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="181"/>
        <source>Cuántos dígitos tiene como mínimo el número del nombre, completando con ceros: con 2 es «01» y con 3 es «001». Si hacen falta más dígitos, se usan en todos los nombres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="186"/>
        <source>Es el primer número de máquina (VMID) del lote; las demás usan los siguientes. Si alguno ya está ocupado se salta y se te avisa. Déjalo vacío para que ProxLaunch proponga uno.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="192"/>
        <source>Dónde se crean las máquinas. En Automático ProxLaunch las reparte entre los nodos del clúster que pueden alojarlas; en «Un nodo» van todas al que elijas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="197"/>
        <source>Marca los nodos entre los que se repartirán las máquinas. Solo se pueden elegir los que están en línea.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="202"/>
        <source>Equilibrado manda cada máquina al nodo que tenga más memoria libre en ese momento (contando las que ya le tocaron), para que ninguno se llene antes que los demás.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="207"/>
        <source>Por turnos reparte las máquinas una a cada nodo, en orden alfabético, y vuelve a empezar. Es predecible, pero no tiene en cuenta cuánta memoria le queda a cada nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="212"/>
        <source>Algunos almacenamientos prometen el espacio de los discos pero no lo reservan hasta que se usa. Puedes crear más discos de los que caben, y funciona mientras no se llenen; si se llenan, todas las máquinas de ese almacenamiento pueden fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="218"/>
        <source>Simular hace todas las comprobaciones y muestra qué se enviaría a Proxmox, pero no crea nada ni cambia nada en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="223"/>
        <source>Elimina de Proxmox las máquinas que creó este lote, con sus discos. Solo toca las que ProxLaunch puede demostrar que creó él, y nunca se hace sin que lo confirmes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="228"/>
        <source>Marca cada máquina con las etiquetas «proxlaunch» y «lote-» más un código, visibles en Proxmox. Sirven para reconocer lo que creó este lote y poder deshacerlo con seguridad. Si tu servidor no admite etiquetas nuevas, desactívalo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="234"/>
        <source>Un perfil de máquina guarda el hardware de una máquina virtual (procesadores, memoria, discos y red). Al elegirlo se rellena el formulario; el nombre, el número y el nodo siguen siendo tuyos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="240"/>
        <source>Los perfiles de fábrica vienen con ProxLaunch y no se pueden cambiar ni borrar. Si quieres una variante, duplícalo y haz tu propia versión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="245"/>
        <source>Un perfil puede recordar el almacenamiento y la red que usaba. Si en este servidor no existen, ProxLaunch usa los predeterminados y te avisa; nunca inventa nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="250"/>
        <source>Guarda el hardware actual del formulario como perfil de máquina para reutilizarlo. No guarda el nombre, el número ni el nodo de la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="255"/>
        <source>Exportar crea un archivo con tus perfiles para compartirlos. Por defecto no incluye los nombres de almacenamiento y de red de tu servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="260"/>
        <source>Importar añade perfiles de un archivo. Antes de guardar nada verás una lista para elegir cuáles, y si un nombre ya existe puedes conservar ambos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="265"/>
        <source>Indica si el perfil funciona con la versión de Proxmox y con el servidor al que estás conectado. Los avisos no impiden crear la máquina; los errores sí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="270"/>
        <source>Un lote guardado es un archivo con la definición de un lote (hardware, cantidad, nombres y reparto) para repetirlo. No guarda datos de conexión ni contraseñas; al abrirlo se vuelve a comprobar todo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="276"/>
        <source>Importar desde CSV crea un lote con una máquina por cada fila de una hoja de cálculo. Antes de crear nada verás una vista previa y un resumen que debes confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="281"/>
        <source>Descarga un archivo CSV de ejemplo con todas las columnas y dos filas de muestra. Ábrelo en tu hoja de cálculo, cambia los datos y guárdalo como CSV.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="286"/>
        <source>Es el carácter que separa las columnas: punto y coma, coma o tabulador. ProxLaunch lo detecta solo; cámbialo si la vista previa se ve mal.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="291"/>
        <source>Es la forma en que el archivo guarda los acentos. ProxLaunch la detecta sola; si ves letras raras, prueba otra o guarda el archivo como «CSV UTF-8» desde Excel.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="296"/>
        <source>Memoria y disco sin unidad se leen en GiB. También puedes escribir MiB, GiB o TiB (por ejemplo «4 GiB»). Evita los separadores de miles: «1.000» es ambiguo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="301"/>
        <source>Muestra cada fila del archivo con su estado y sus problemas. Puedes excluir filas antes de continuar; nada se crea hasta que confirmes el resumen del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="306"/>
        <source>En un lote por filas cada máquina tiene su propia configuración, como venía en el archivo. Para cambiar algo, corrige el archivo e impórtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="311"/>
        <source>Aquí eliges de dónde sale el sistema operativo de la máquina: un disco vacío, un ISO de instalación, un disco ya hecho que se importa o la copia de una plantilla de Proxmox. Si no sabes cuál, usa un ISO para instalar desde cero o una plantilla para empezar con algo ya instalado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="318"/>
        <source>Un ISO es la imagen del disco de instalación de un sistema operativo, como el CD con el que se instalaría. La máquina arranca desde él y tú terminas la instalación desde la consola de Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="324"/>
        <source>Sube un archivo de tu equipo al servidor de Proxmox para poder usarlo. ProxLaunch no puede borrar lo que subes: si ya no lo necesitas, pídele a un administrador que lo elimine desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="330"/>
        <source>El propio servidor de Proxmox descarga el archivo desde la dirección web que indiques, sin pasar por tu equipo. Usa solo direcciones https de confianza y, si puedes, escribe también la huella del archivo para comprobarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="336"/>
        <source>La huella (checksum) es un código que identifica un archivo. Si la escribes, Proxmox comprueba al terminar que lo descargado coincide y, si no, descarta el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="341"/>
        <source>El asistente ajusta la máquina al sistema que vas a instalar: tipo de arranque, TPM, controlador de discos y tarjeta de red. Te muestra cada cambio y no toca los núcleos, la memoria ni el tamaño del disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="347"/>
        <source>Windows no trae los controladores de los discos y la red virtuales de Proxmox. Por eso se añade un segundo CD, llamado virtio-win, para cargarlos durante la instalación.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="352"/>
        <source>Importar crea la máquina a partir de un disco que ya tiene un sistema instalado, en lugar de empezar vacía. Necesita una imagen en el servidor, guardada en un almacenamiento con el contenido «Import» activado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="358"/>
        <source>qcow2, raw y vmdk son formas de guardar un disco virtual y ProxLaunch acepta las tres. Tiene que ser un solo archivo: un disco que depende de otro o está cifrado no se puede importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="364"/>
        <source>Cada máquina del lote recibe su propia copia del disco, así que ocupa espacio propio. Con muchas máquinas el espacio necesario se multiplica.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="369"/>
        <source>Una plantilla de Proxmox es una máquina ya instalada que se marcó como modelo. Al clonarla obtienes máquinas nuevas con su mismo sistema, sin instalar nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="374"/>
        <source>«Rápido y ligero» (enlazado) comparte los datos con la plantilla: se crea en segundos y casi no ocupa espacio, pero depende de ella. «Copia independiente» (completo) duplica todo el disco: tarda más y ocupa más, pero la máquina no depende de nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="380"/>
        <source>ProxLaunch recuerda, para cada servidor, el almacenamiento que usaste para ISOs, imágenes y discos. La próxima vez lo propone solo; si deja de estar disponible te lo diremos y podrás elegir otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="386"/>
        <source>Para usar ISOs, importar discos y clonar plantillas, el rol de ProxLaunch necesita cuatro permisos más que antes. Si faltan, crear máquinas vacías sigue funcionando y solo se desactivan esas opciones, indicando qué permiso falta.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="392"/>
        <source>Si se corta la conexión justo al enviar una máquina, no se sabe si Proxmox llegó a crearla. ProxLaunch nunca la vuelve a enviar sola, porque podría duplicarla: usa «Comprobar» para ver si existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="399"/>
        <source>Cloud-init es un programa que viene dentro de las imágenes de servidores en la nube. En el primer arranque lee unos datos que Proxmox le entrega (usuario, claves, red) y configura la máquina sola, sin que tengas que entrar a instalarla. Ejemplo: usuario «deploy», tu clave SSH y la IP 192.168.1.50/24.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="406"/>
        <source>La unidad cloud-init es un pequeño disco virtual donde Proxmox deja los datos de cloud-init. Sin ella, la máquina no recibe usuario ni red. Se añade a la plantilla desde Proxmox (Hardware, Añadir, «CloudInit Drive»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="412"/>
        <source>Nombre del usuario que se crea en la máquina, por ejemplo «deploy». Si lo dejas vacío se usa el usuario por defecto de la imagen (en Ubuntu es «ubuntu»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="417"/>
        <source>Una clave SSH pública (el archivo que termina en .pub) te deja entrar a la máquina sin contraseña. Pega una clave por línea o añade los archivos .pub. La clave privada nunca se comparte: ProxLaunch la rechaza si la pegas. Ejemplo de línea: ssh-ed25519 AAAAC3Nza… ana@portatil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="424"/>
        <source>Opcional. Sirve para entrar por la consola de Proxmox si falla la red o las claves. Es menos segura que una clave SSH: se envía a Proxmox y queda en su configuración. No se guarda en lotes, perfiles ni archivos. Con una plantilla de Windows no se permite.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="431"/>
        <source>DHCP: la red asigna la dirección sola. IP fija: tú eliges la dirección (con su máscara, por ejemplo 192.168.1.50/24) y la puerta de enlace. «Sin configurar» deja lo que ya tenga la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="437"/>
        <source>Dirección IPv4 con su máscara, por ejemplo 192.168.1.50/24 (el /24 equivale a la máscara 255.255.255.0). ProxLaunch no puede comprobar si la IP ya está en uso en tu red: eso lo tienes que saber tú.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="443"/>
        <source>La puerta de enlace es la dirección del router por el que la máquina sale a otras redes e internet, por ejemplo 192.168.1.1. Debe estar en la misma red que la IP.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="448"/>
        <source>En un lote, la primera máquina recibe la IP que escribas, la segunda la siguiente (192.168.1.51), y así. Sin marcar, todas tendrían la misma IP y ProxLaunch no te dejaría crear el lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="454"/>
        <source>Servidores DNS que usará la máquina para traducir nombres, separados por espacio o coma, por ejemplo 1.1.1.1, 8.8.8.8. Vacío = los del servidor Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="459"/>
        <source>El dominio de búsqueda se añade a los nombres cortos: con «lab.local», escribir «srv01» equivale a «srv01.lab.local». Vacío = el del servidor Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="464"/>
        <source>Si está activado, en el primer arranque la máquina actualiza el sistema; puede tardar varios minutos. «Como la plantilla» no cambia nada (si la plantilla no lo define, Proxmox lo trata como «sí»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="470"/>
        <source>Un snippet es un archivo de texto (normalmente YAML) guardado en el servidor que cloud-init usa como guion de configuración. ProxLaunch no los crea ni los sube: los deja un administrador en un almacenamiento con el contenido «Fragmentos» (snippets). Con uno puedes, por ejemplo, instalar el agente invitado. Recomendación: usa «Datos del proveedor»; «Datos de usuario» sustituye al usuario, las claves y la contraseña de arriba.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="479"/>
        <source>Escribe el identificador con la forma almacén:snippets/archivo, por ejemplo local:snippets/agente.yaml. Sin la lista del servidor, ProxLaunch no puede comprobar que el archivo exista.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="485"/>
        <source>El agente invitado (qemu-guest-agent) es un programa que corre dentro de la máquina y le cuenta a Proxmox cosas como su IP. Las imágenes de Ubuntu y Debian no lo traen; Rocky y Alma sí. Sin él no podemos saber la IP.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="491"/>
        <source>Activa la opción del agente invitado en la configuración de la máquina. El programa también tiene que estar instalado dentro del sistema (las imágenes de Ubuntu y Debian no lo traen; puedes instalarlo con un script de configuración).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="497"/>
        <source>Tras encender cada máquina, ProxLaunch pregunta cada pocos segundos a Proxmox por su IP hasta que la tenga o se acabe el plazo. Necesita el agente invitado instalado dentro de la máquina. Si no hay IP, la máquina se crea igual y solo se avisa.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="503"/>
        <source>Una imagen cloud es un disco ya instalado y mínimo (Ubuntu, Debian, Rocky…) que se publica para servidores. No trae instalador: se importa tal cual y cloud-init lo personaliza al arrancar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="509"/>
        <source>Una plantilla es una máquina «modelo» de la que se sacan copias (clones). No se enciende ni se edita; cada copia nace con su propio disco. Convertir una máquina en plantilla no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="515"/>
        <source>Con la consola serie, la consola gráfica de Proxmox se queda en negro: usa la consola «xterm.js» (texto), que es la que muestran las imágenes cloud.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="631"/>
        <source>Rinde más pero impide mover la máquina entre nodos con procesadores distintos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="640"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="646"/>
        <source>Entra en la página web de tu Proxmox y ve a Datacenter → Permisos → Roles → Crear. Llama al rol «{rol}» y marca los privilegios de la lista de abajo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="651"/>
        <source>Ve a Datacenter → Permisos → Usuarios y crea un usuario para ProxLaunch (por ejemplo «proxlaunch@pve»), o elige uno que ya tengas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="656"/>
        <source>Ve a Datacenter → Permisos → Tokens de API → Añadir. Elige el usuario, escribe un nombre para el token (por ejemplo «lab») y pulsa Añadir. Copia el secreto que se muestra: solo aparece una vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="662"/>
        <source>Ve a Datacenter → Permisos → Añadir → Permiso de usuario (o de token) y da al usuario o al token los permisos. Lo más seguro es el alcance acotado de abajo; la alternativa simple es una sola asignación en la ruta «/».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="684"/>
        <source>Pool de plantillas: en Datacenter → Permisos → Pools crea un pool (por ejemplo «plantillas-proxlaunch») y añade solo las plantillas que ProxLaunch podrá clonar. Luego añade el permiso en la ruta «/pool/plantillas-proxlaunch» con el rol «{rol}» y «Propagar». Así VM.Clone vale solo para esas plantillas: las demás pueden verse en la lista, pero ProxLaunch no las clonará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="692"/>
        <source>Crear máquinas: crea un segundo rol, «{rol}», con los privilegios de máquina del rol anterior SIN VM.Clone ({privilegios}) y asígnalo en la ruta «/vms» con «Propagar».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="698"/>
        <source>Almacenamientos: en la ruta «/storage/&lt;almacenamiento&gt;» con el rol «{rol}», solo en los que usarás para ISOs, imágenes de disco importadas y discos de las máquinas (Datastore.AllocateTemplate y Datastore.AllocateSpace).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="704"/>
        <source>Nodos: en la ruta «/nodes/&lt;nodo&gt;» con el rol «{rol}», solo en los nodos que descargarán archivos desde una dirección web (Sys.AccessNetwork).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="709"/>
        <source>Red y estado: en la ruta «/sdn/zones/localnetwork» (SDN.Use) y en la ruta «/» con el rol «{rol}» pero SIN «Propagar» (Sys.Audit, solo para ver el estado de los nodos).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="790"/>
        <source>encender máquinas al terminar y apagarlas a la fuerza al deshacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="793"/>
        <source>ver la lista de pools</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="838"/>
        <source>Privilegios opcionales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="842"/>
        <source>No forman parte del rol «{rol}» y no hacen falta para crear máquinas: sin ellos ProxLaunch solo desactiva la opción afectada y te explica por qué.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="860"/>
        <source>permite ver la lista de pools para elegir uno. Sin él no se puede elegir pool, aunque existan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="866"/>
        <source>permite poner usuario, claves SSH, contraseña, red y scripts a las máquinas clonadas con cloud-init. Sin él esa sección se desactiva (en Proxmox 8.x también vale VM.Config.Network, que ya forma parte del rol).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="873"/>
        <location filename="../../interfaz/ayuda.py" line="879"/>
        <source>permite consultar al agente invitado para «Esperar la IP» de cada máquina. Sin él esa casilla se desactiva.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="885"/>
        <source>en Proxmox 8.x hace falta para usar scripts de configuración (snippets). Ya forma parte del rol; compruébalo también sobre el almacenamiento de snippets, que es donde se guardan. Es la opción recomendada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="892"/>
        <source>en tu versión puede hacer falta (es un permiso de administrador del almacenamiento) para elegir scripts de configuración (snippets); no está verificado. Sin él los scripts pueden ser rechazados por Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="904"/>
        <source>/storage/(el almacenamiento de snippets)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="919"/>
        <source>{privilegio} en «{ruta}»: {efecto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="942"/>
        <source>Para añadir al rol que ya tienes los privilegios de cloud-init y de la espera de IP, sin recrearlo, ejecuta en un nodo de Proxmox: {comando}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="966"/>
        <source>ProxLaunch no puede subir este archivo. Pide a tu administrador que lo guarde, por ejemplo como agente.yaml, en la carpeta de snippets de un almacenamiento con el contenido «Fragmentos» (en el almacenamiento «local» suele ser /var/lib/vz/snippets) de cada nodo. Después elígelo en «Datos del proveedor» (vendor).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="977"/>
        <source>ProxLaunch no pide el privilegio Sys.Modify, que solo tiene el rol Administrator. No hace falta darlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="986"/>
        <source>Las etiquetas propias dependen de la política del servidor: si Proxmox solo admite etiquetas autorizadas, el administrador debe añadirlas en Datacenter → Opciones → Etiquetas (lista de etiquetas permitidas a usuarios, «user-allow-list», o etiquetas registradas, «registered-tags»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1035"/>
        <source>2. Asignar los permisos a mi usuario o a mi token solo donde hacen falta (Datacenter → Permisos → Añadir). Opción recomendada, de alcance acotado:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1058"/>
        <source>6. Opcional: para encender las máquinas al terminar y apagarlas a la fuerza al deshacer, el privilegio VM.PowerMgmt en «/vms»; para elegir un pool, Pool.Audit en «/pool». No forman parte del rol.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="668"/>
        <source>En ProxLaunch pega el token completo con el formato usuario@realm!nombre=secreto, por ejemplo proxlaunch@pve!lab=11111111-2222-3333-4444-555555555555.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="720"/>
        <source>Alternativa simple: asigna el rol «{rol}» una sola vez en la ruta «/» con «Propagar». Es más cómodo, pero el permiso alcanza a todo el servidor: quien consiga el token podría clonar cualquier máquina y leer sus discos, subir archivos a cualquier almacenamiento y hacer que los nodos descarguen direcciones web. Úsalo solo en un laboratorio o si confías plenamente en quien guarde el token.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="733"/>
        <source>Usa siempre un token con los permisos mínimos en lugar de root@pam: si el token se filtra, el daño es mucho menor y puedes revocarlo sin cambiar contraseñas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="738"/>
        <source>Al crear el token puedes desmarcar «Separación de privilegios» solo si ya asignaste los permisos al usuario; si la dejas marcada, el token necesita sus propios permisos (paso 4 con el token).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="744"/>
        <source>Los últimos cuatro privilegios de la lista sirven para instalar desde un ISO, importar discos y clonar plantillas. Si los omites, crear máquinas vacías sigue funcionando y ProxLaunch solo desactiva esas opciones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="762"/>
        <source>crear máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="763"/>
        <source>ver las máquinas del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="764"/>
        <source>ajustar nombre, etiquetas y opciones generales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="767"/>
        <source>elegir el tipo de equipo y de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="770"/>
        <source>configurar procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="771"/>
        <source>configurar la memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="772"/>
        <source>configurar las tarjetas de red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="775"/>
        <source>crear discos en los almacenamientos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="778"/>
        <source>usar las redes del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="779"/>
        <source>ver el estado de los nodos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="780"/>
        <source>fijar el orden de arranque con ISO y ampliar discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="783"/>
        <source>clonar plantillas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="784"/>
        <source>subir y descargar ISOs e imágenes de disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="787"/>
        <source>que el servidor descargue archivos desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="811"/>
        <source>sin él no se fija el orden de arranque con un ISO ni se amplían discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="816"/>
        <source>sin él no se pueden clonar plantillas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="818"/>
        <source>sin él no se pueden subir ni descargar ISOs o imágenes de disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="822"/>
        <source>sin él el servidor no puede descargar archivos desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="852"/>
        <source>permite «Encender al terminar» y apagar a la fuerza las máquinas encendidas del lote al usar Deshacer. Debe concederse en «/vms» (no solo en una máquina concreta) para que «Encender al terminar» se habilite. Sin él, esas máquinas encendidas no se tocan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1002"/>
        <source>ProxLaunch no puede borrar los ISOs ni las imágenes que subas o descargues, ni siquiera con un usuario administrador. Si ya no los necesitas, bórralos desde Proxmox (en el almacenamiento, sección «ISO Images» o «Import»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1019"/>
        <source>Hola. Para que ProxLaunch pueda instalar máquinas desde un ISO, importar discos y clonar plantillas necesito lo siguiente en Proxmox:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1025"/>
        <source>1. Un rol llamado «{rol}» (Datacenter → Permisos → Roles → Crear) con estos {n} privilegios:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1042"/>
        <source>3. Para importar discos: activar el contenido «Import» en un almacenamiento de tipo directorio, NFS o CIFS (Datacenter → Almacenamiento → Editar → Contenido). Hace falta Proxmox 8.4 o superior.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1048"/>
        <source>4. Para clonar: convertir en plantilla una máquina ya instalada (clic derecho en la máquina → Convertir en plantilla).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="1053"/>
        <source>5. Los ISOs e imágenes que suba no los puede borrar ProxLaunch: habrá que eliminarlos desde Proxmox cuando ya no hagan falta.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>BarraSuperior</name>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="47"/>
        <source>ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="60"/>
        <source>La identidad del servidor no se está comprobando. Úsalo solo en redes de prueba.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="88"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="104"/>
        <source>Proxmox VE {version}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="108"/>
        <source>(forzada)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="113"/>
        <source>Conexión sin verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="126"/>
        <source>Topología desconocida ({n} nodos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="130"/>
        <source>Clúster «{nombre}» — {n} nodos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/barra_superior.py" line="134"/>
        <source>Servidor individual</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>BloqueLote</name>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="78"/>
        <source>Lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="110"/>
        <source>Cantidad</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="114"/>
        <source>Cantidad de máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="125"/>
        <source>por ejemplo srv-web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="128"/>
        <source>Prefijo de los nombres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="132"/>
        <source>Prefijo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="138"/>
        <source>Vista previa de los nombres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="141"/>
        <source>Guion (-)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="142"/>
        <source>Ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="145"/>
        <source>Separador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="153"/>
        <source>Número inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="161"/>
        <source>Relleno (dígitos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="167"/>
        <source>automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="170"/>
        <source>Número de máquina inicial (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="192"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="193"/>
        <source>Un nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="195"/>
        <source>Nodos elegidos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="204"/>
        <source>Nodo de destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="213"/>
        <source>Equilibrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="216"/>
        <source>Por turnos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="219"/>
        <source>Algoritmo de reparto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="234"/>
        <source>Este lote usa nodos elegidos; cámbialo en modo avanzado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="245"/>
        <source>Dónde crearlas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="250"/>
        <source>Reparto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="265"/>
        <source>Etiquetar las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="388"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="428"/>
        <source>{nodo} (no existe)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="713"/>
        <source>Se llamarán: {nombres}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Campos</name>
    <message>
        <location filename="../../interfaz/vistas/campos.py" line="99"/>
        <source>Ayuda</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ColumnasCsv</name>
    <message>
        <location filename="../../interfaz/textos.py" line="1906"/>
        <source>nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1907"/>
        <source>perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1908"/>
        <source>vmid</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1909"/>
        <source>nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1910"/>
        <source>cpu</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1911"/>
        <source>sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1912"/>
        <source>memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1913"/>
        <source>disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1914"/>
        <source>almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1915"/>
        <source>red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1916"/>
        <source>vlan</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1917"/>
        <source>modelo_red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1918"/>
        <source>firmware</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1919"/>
        <source>tipo_cpu</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1920"/>
        <source>origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1921"/>
        <source>fuente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1922"/>
        <source>so</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1923"/>
        <source>virtio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1924"/>
        <source>modo_clon</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1925"/>
        <source>encender</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1926"/>
        <source>arranque_auto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1927"/>
        <source>notas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1928"/>
        <source>etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1929"/>
        <source>pool</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1930"/>
        <source>proteger</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1931"/>
        <source>mtu</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1932"/>
        <source>limite_red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1934"/>
        <source>ci_usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1935"/>
        <source>ci_claves</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1936"/>
        <source>ci_ip</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1937"/>
        <source>ci_puerta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1938"/>
        <source>ci_dns</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1939"/>
        <source>ci_dominio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1940"/>
        <source>ci_actualizar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1941"/>
        <source>ci_snippet_usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1942"/>
        <source>ci_snippet_vendor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1943"/>
        <source>ci_snippet_red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1944"/>
        <source>ci_snippet_meta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1945"/>
        <source>esperar_ip</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ControladorOrigen</name>
    <message>
        <location filename="../../interfaz/controlador_origen.py" line="860"/>
        <source>Hay una transferencia, un lote o una simulación en curso. Espera a que termine o cancélala.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Detalles</name>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="20"/>
        <source>Resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="21"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="28"/>
        <source>Código</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="29"/>
        <source>Mensaje original</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="36"/>
        <source>Registro de la tarea</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="66"/>
        <source>Ocultar detalles técnicos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/detalles_tecnicos.py" line="68"/>
        <source>Ver detalles técnicos</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoAcercaDe</name>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="45"/>
        <source>Acerca de ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="50"/>
        <source>ProxLaunch {version}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="52"/>
        <source>Compatible con Proxmox VE</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="56"/>
        <source>Asistente para crear máquinas virtuales. Proxmox es una marca de Proxmox Server Solutions GmbH; ProxLaunch es un proyecto independiente.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="65"/>
        <source>Las máquinas que crea ProxLaunch llevan la etiqueta «proxlaunch» (y otra «lote-…» si se crean en un lote). Así se reconocen en Proxmox y se pueden deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="78"/>
        <source>Licencia de la fuente {nombre} (SIL Open Font License)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/acerca_de.py" line="84"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoCapacidades</name>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="104"/>
        <source>Qué puedo hacer en este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="110"/>
        <source>Versión de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="115"/>
        <source>Qué quieres hacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="115"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="115"/>
        <source>Por qué</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="117"/>
        <source>Funciones disponibles en este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="129"/>
        <source>Qué pedirle a tu administrador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="135"/>
        <source>Texto para el administrador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="138"/>
        <source>Copiar texto para el administrador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="141"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="166"/>
        <source>Todavía no se conocen las capacidades: conéctate a un servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="185"/>
        <source>En este servidor no puedo hacer lo siguiente:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="192"/>
        <source>No hace falta pedir nada: todas las funciones están disponibles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="203"/>
        <source>Proxmox VE {version}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="205"/>
        <source>(versión forzada)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/capacidades.py" line="207"/>
        <source>nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoCatalogo</name>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="118"/>
        <location filename="../../interfaz/dialogos/catalogo.py" line="119"/>
        <source>Filtrar por nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="147"/>
        <source>Estado del catálogo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="155"/>
        <source>Subir desde mi equipo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="158"/>
        <source>Descargar en el servidor…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="161"/>
        <source>Actualizar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="164"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="167"/>
        <source>Elegir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="294"/>
        <source>Elegir un archivo ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="295"/>
        <source>Elegir el ISO de drivers virtio-win</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="296"/>
        <source>Elegir un disco existente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="297"/>
        <source>Elegir una plantilla de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="303"/>
        <source>Estos son los archivos ISO que hay en el servidor. Si el tuyo no está, súbelo desde tu equipo o haz que el servidor lo descargue.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="307"/>
        <source>Windows necesita los drivers virtio-win para ver el disco y la red. Elige el ISO que empieza por «virtio-win».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="311"/>
        <source>Estos son los discos (qcow2, vmdk, raw) que hay en el servidor para importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="314"/>
        <source>Estas son las plantillas de Proxmox que tu cuenta puede ver. La nueva máquina será una copia de la que elijas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="321"/>
        <location filename="../../interfaz/dialogos/catalogo.py" line="322"/>
        <source>Archivos ISO del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="323"/>
        <source>Discos del servidor para importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="324"/>
        <source>Plantillas del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="331"/>
        <source>No hay ningún disco en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="333"/>
        <source>No hay ningún ISO en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="340"/>
        <source>Puedes subir uno desde tu equipo o hacer que el servidor lo descargue.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="343"/>
        <source>Puedes subir uno desde tu equipo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="345"/>
        <source>Puedes hacer que el servidor lo descargue.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="393"/>
        <source>Cargando…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/catalogo.py" line="397"/>
        <source>Ningún elemento coincide con el filtro.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoConexion</name>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="92"/>
        <source>Conectar con Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="133"/>
        <source>Duplicar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="134"/>
        <source>Eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="136"/>
        <source>Perfil guardado:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="144"/>
        <source>Nombre del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="148"/>
        <source>Un servidor por línea. Si el primero no responde se prueba el siguiente.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="150"/>
        <source>Servidores (IP o nombre)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="153"/>
        <source>Puerto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="158"/>
        <source>API Token (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="159"/>
        <source>Usuario y contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="171"/>
        <source>Método</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="177"/>
        <source>Token</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="178"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="185"/>
        <source>Realm</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="187"/>
        <source>Usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="190"/>
        <source>Contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="201"/>
        <source>Recordar credenciales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="204"/>
        <source>Ignorar verificación SSL</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="208"/>
        <source>Detectada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="213"/>
        <source>Forzar compatibilidad con la versión...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="246"/>
        <source>Guardar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="247"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="248"/>
        <source>Probar y conectar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="278"/>
        <source>Almacenamientos recordados de este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="283"/>
        <source>ProxLaunch los detecta solo. Aquí aparecen los que elegiste que recuerde; solo se guarda el nombre del almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="291"/>
        <source>Discos de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="292"/>
        <source>Archivos ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="293"/>
        <source>Discos para importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="301"/>
        <source>Dejar de recordar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="302"/>
        <source>Dejar de recordar: {nombre}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="319"/>
        <source>Detectar automáticamente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="323"/>
        <source>{nombre} (no disponible)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="366"/>
        <location filename="../../interfaz/dialogos/conexion.py" line="677"/>
        <source>(Perfil nuevo)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="453"/>
        <source>Las credenciales guardadas se borrarán del llavero al guardar o conectar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="458"/>
        <source>(guardado en el llavero)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="469"/>
        <source>{nombre} (copia)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="479"/>
        <source>Eliminar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="481"/>
        <source>Se eliminará el perfil «{nombre}», sus credenciales guardadas en el llavero y las huellas de certificado que solo usaba él. ¿Continuar?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="501"/>
        <source>Ya existe otro perfil con este nombre. Puedes guardarlo igualmente, pero costará distinguirlos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="586"/>
        <source>Escribe tu usuario.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="613"/>
        <source>Estás usando root@pam. Es más seguro usar un API Token con permisos mínimos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="635"/>
        <source>La identidad del servidor no se comprobará: la conexión quedará sin verificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="654"/>
        <source>Perfil guardado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="659"/>
        <source>Perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="727"/>
        <source>Escribe tu contraseña.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="733"/>
        <source>Conexión sin verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="735"/>
        <source>No se comprobará la identidad del servidor. Tu contraseña viajaría sin esa protección y alguien en la red podría interceptarla. ¿Conectar igualmente?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="755"/>
        <source>Comprobando el certificado del servidor...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="793"/>
        <source>Conectando...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="818"/>
        <source>Esperando el segundo factor...</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoDescarga</name>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1101"/>
        <source>Descargar un ISO en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1103"/>
        <source>Descargar un disco en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1105"/>
        <source>Descargar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1109"/>
        <source>https://…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1110"/>
        <source>Dirección web del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1113"/>
        <source>Comprobar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1121"/>
        <source>Opcional: huella (sha256, sha512…)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1122"/>
        <source>Huella para verificar el archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1127"/>
        <source>Nombre del archivo en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1133"/>
        <source>Comprobar el certificado del servidor web (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1137"/>
        <source>Comprobar el certificado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1149"/>
        <source>Avisos de la descarga</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1155"/>
        <source>Lo que ve el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1160"/>
        <source>La descarga la hace el servidor: una vez empezada, no se puede cancelar desde ProxLaunch. Solo puedes dejar de esperar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1168"/>
        <source>La dirección quedará en el registro de tareas del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1174"/>
        <source>Dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1175"/>
        <source>Huella</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1176"/>
        <source>Nombre en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1237"/>
        <source>Preguntando al servidor por «{host}/{archivo}»…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1284"/>
        <source>El servidor ve: «{host}/{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1287"/>
        <source>Nombre: {nombre}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1287"/>
        <source>no indicado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1289"/>
        <source>Tamaño: {tamano}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1291"/>
        <source>Tipo: {tipo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1327"/>
        <source>El servidor descargará «{nombre}» ({tamano}) en el almacenamiento «{storage}» del nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1350"/>
        <source>Dejando de esperar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1353"/>
        <source>Dejar de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1366"/>
        <source>La dirección usa http://: no se puede garantizar que el archivo no fue alterado por el camino. Conviene indicar la huella.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1373"/>
        <source>No se comprobará el certificado del servidor web: podrías descargar un archivo de un sitio falso.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1389"/>
        <source>Consulta con riesgo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1391"/>
        <source>Consultar de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1397"/>
        <source>Descarga con riesgo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1399"/>
        <source>Descargar de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1392"/>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1400"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoDeshacer</name>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="40"/>
        <source>Deshacer lo creado por el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="46"/>
        <source>Todo lo que creó el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="49"/>
        <source>Solo las incompletas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="56"/>
        <source>Máquinas que se pueden eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="82"/>
        <source>Los archivos que subiste (ISOs e imágenes de disco) y las plantillas no se eliminan. Si ya no los necesitas, un administrador puede borrarlos desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="96"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="107"/>
        <source>¿Qué quieres deshacer?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="147"/>
        <source>Se eliminará esta máquina y sus discos de Proxmox. Esta acción no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="154"/>
        <source>Eliminar 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/deshacer.py" line="158"/>
        <source>Se eliminarán estas %n máquinas y sus discos de Proxmox. Esta acción no se puede deshacer.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/deshacer.py" line="167"/>
        <source>Eliminar %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
</context>
<context>
    <name>DialogoDosFactores</name>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="29"/>
        <source>Código de verificación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="41"/>
        <source>Verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="44"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="75"/>
        <source>Escribe una de tus claves de recuperación. Cada clave solo sirve una vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="78"/>
        <source>clave de recuperación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="79"/>
        <source>Usar el código de la aplicación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="83"/>
        <source>Escribe el código de 6 números que muestra tu aplicación de autenticación.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="88"/>
        <source>Usar una clave de recuperación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/dos_factores.py" line="99"/>
        <source>Escribe la clave de recuperación.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoElegirStorage</name>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="82"/>
        <source>Elegir almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="89"/>
        <source>Explicación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="94"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="95"/>
        <source>Tipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="96"/>
        <source>Espacio libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="97"/>
        <source>Compartido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="98"/>
        <source>Nota</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="101"/>
        <source>Almacenamientos disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="109"/>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="111"/>
        <source>Recordar mi elección</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="113"/>
        <source>Se guarda solo el nombre del almacenamiento, en el perfil de este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="123"/>
        <source>Dejar de recordar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="127"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="131"/>
        <source>Elegir otro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="131"/>
        <source>Usar este</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="157"/>
        <source>Hay varios almacenamientos para {contenido}. ¿Cuál usar siempre en este servidor?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="164"/>
        <source>Más espacio libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="169"/>
        <source>Sí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/elegir_storage.py" line="169"/>
        <source>No</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoGuardarLote</name>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="59"/>
        <source>Guardar lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="68"/>
        <source>Se guarda la configuración del lote para volver a usarla. No se guardan las máquinas creadas ni ningún dato de conexión (servidor, usuario o credenciales).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="79"/>
        <source>El lote tiene problemas; se comprobará otra vez al abrirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="85"/>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="87"/>
        <source>Nombre del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="86"/>
        <source>Por ejemplo: Servidores web de pruebas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="94"/>
        <source>Guardar como un archivo nuevo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="96"/>
        <source>Sobrescribir el archivo «{nombre}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="111"/>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="176"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="157"/>
        <source>nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="162"/>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="175"/>
        <source>Sobrescribir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="164"/>
        <source>Elegir dónde guardar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="171"/>
        <source>Sobrescribir archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_lote.py" line="173"/>
        <source>¿Sobrescribir el archivo «{nombre}»? Su contenido anterior se perderá.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoGuardarPerfil</name>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="51"/>
        <source>Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="89"/>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="95"/>
        <source>Nombre del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="92"/>
        <source>Por ejemplo: Servidor web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="109"/>
        <source>Descripción del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="112"/>
        <source>Opcional: para qué sirve este perfil (hasta {n} caracteres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="118"/>
        <source>Descripción (opcional)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="134"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="184"/>
        <source>descripción</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="268"/>
        <source>Guardar como perfil de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="271"/>
        <source>Guardar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="273"/>
        <source>Mi perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="287"/>
        <source>Se guardará el hardware actual del formulario: procesador, memoria, discos y redes (con su MTU y límite de velocidad), y si arranca con el servidor. No se guarda el nombre de la máquina, su número ni el nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="298"/>
        <source>Resumen del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="303"/>
        <source>También se recordará el origen del sistema operativo: el nombre del ISO, de la imagen o de la plantilla. Nunca se guardan direcciones web ni rutas de tu equipo. Al usar el perfil en otro servidor se buscará ese nombre y, si no está, tendrás que elegir otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="316"/>
        <source>Recordar los nombres de almacenamiento y red (solo sirven en servidores que los tengan)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="324"/>
        <source>Recordar los nombres de almacenamiento y red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="329"/>
        <source>Si lo marcas, el perfil recuerda en qué almacenamiento y red estaba cada disco. Al usarlo en otro servidor, si esos nombres no existen se elegirán otros y se te avisará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="357"/>
        <source>Corrige esto en el formulario antes de guardar el perfil:</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoGuiaToken</name>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="61"/>
        <source>Privilegios del rol «{rol}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="72"/>
        <source>Qué se pierde sin los cuatro privilegios nuevos:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="80"/>
        <source>Dónde asignar los permisos (recomendado: alcance acotado):</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="121"/>
        <source>Copiar texto para mi administrador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="124"/>
        <source>Copia un mensaje con los permisos, la activación de «Import» y la creación de plantillas que hay que pedir.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="118"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="148"/>
        <source>Texto copiado.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoHuella</name>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="67"/>
        <source>El certificado del servidor cambió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="72"/>
        <source>Servidor: {destino}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="73"/>
        <source>Huella guardada:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="75"/>
        <source>Huella nueva:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="77"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="83"/>
        <location filename="../../interfaz/dialogos/huella.py" line="127"/>
        <source>Reemplazar la huella guardada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="88"/>
        <source>Confiar en este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="92"/>
        <source>No tenemos registro de este servidor porque el archivo de huellas se dañó. Compara la huella con la de tu administrador antes de confiar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="97"/>
        <source>Es la primera vez que te conectas a este servidor. Comprueba que la huella de abajo coincide con la que te dio tu administrador. No se ha enviado ninguna credencial.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="105"/>
        <source>Servidor: {host}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="106"/>
        <source>Puerto: {puerto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="108"/>
        <source>Huella SHA-256:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="113"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="116"/>
        <source>Confiar y continuar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/huella.py" line="129"/>
        <source>Vas a confiar en el certificado nuevo de {destino}. Hazlo solo si tu administrador confirmó el cambio. ¿Reemplazar la huella guardada?</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoImportarCsv</name>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="161"/>
        <source>Importar desde CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="209"/>
        <source>Cada fila del archivo es una máquina. Aquí solo se revisa: no se crea nada hasta que confirmes el resumen del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="219"/>
        <source>Para elegir de dónde sale el sistema operativo usa las columnas «origen» (iso, importar o clonar) y «fuente» (el nombre del ISO, de la imagen o de la plantilla en el servidor). «fuente» no admite direcciones web ni rutas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="229"/>
        <source>Todavía no elegiste un archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="230"/>
        <source>Archivo CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="232"/>
        <source>Elegir otro archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="233"/>
        <source>Descargar plantilla…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="235"/>
        <source>Guarda un CSV de ejemplo con las columnas que entiende ProxLaunch.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="245"/>
        <source>Perfil base</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="249"/>
        <source>Perfil base:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="256"/>
        <source>El perfil base aporta todo lo que el archivo no diga (procesador, discos, red…). Las columnas del archivo siempre mandan sobre el perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="263"/>
        <source>Codificación del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="264"/>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="284"/>
        <source>Detectar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="273"/>
        <source>Codificación:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="277"/>
        <source>Es la forma en que el archivo guarda las letras con acento. Si ves símbolos raros, prueba otra; lo más habitual es «UTF-8» o «Windows-1252».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="283"/>
        <source>Separador de columnas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="286"/>
        <source>; (punto y coma)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="287"/>
        <source>, (coma)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="288"/>
        <source>Tabulador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="289"/>
        <source>| (barra vertical)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="293"/>
        <source>Separador:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="297"/>
        <source>Es el carácter que separa las columnas. Excel en español usa «;» y en inglés «,». ProxLaunch lo detecta solo; cámbialo únicamente si las columnas salen mal.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="330"/>
        <source>Sin conexión: aún no se comprobó contra el servidor. Conéctate a un servidor para poder continuar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="339"/>
        <source>Resumen de la vista previa</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="340"/>
        <source>Mostrar solo problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="341"/>
        <source>Copiar errores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="342"/>
        <source>Copia al portapapeles la lista de errores.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="353"/>
        <source>Filas del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="360"/>
        <source>Detalle de la fila seleccionada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="362"/>
        <source>Selecciona una fila para ver sus problemas y los valores originales.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="370"/>
        <source>Descargar filas con error…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="372"/>
        <source>Guarda un CSV con solo las filas con error, listo para corregir y reimportar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="374"/>
        <source>Corregir el archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="375"/>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="864"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="376"/>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="682"/>
        <source>Continuar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="529"/>
        <source>Leyendo el archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="633"/>
        <source>No se pudo saber qué separador usa el archivo. Elige uno en la lista «Separador».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="653"/>
        <source>tabulador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="666"/>
        <source>Codificación {codificacion} · separador {separador} · </source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="670"/>
        <source>1 fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="670"/>
        <source>%n filas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="671"/>
        <source>{c} correctas, {a} con aviso, {e} con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="684"/>
        <source>No hay filas correctas para importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="686"/>
        <source>Importar solo la fila correcta</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="688"/>
        <source>Importar solo las %n filas correctas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="701"/>
        <source>Conéctate a un servidor para poder continuar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="704"/>
        <source>No queda ninguna fila para importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="735"/>
        <source>Se guardó la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="758"/>
        <source>{base}-errores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="772"/>
        <source>Se guardó el archivo con las filas con error.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="782"/>
        <source>Se copiaron %n errores.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="799"/>
        <source>Fila {n} · {nombre} · {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="807"/>
        <source>Sin problemas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="810"/>
        <source>{columna}: Valor del archivo: «{valor}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="828"/>
        <source>tiene un error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="830"/>
        <source>la excluiste tú</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="833"/>
        <source>Fila {n} · {nombre} ({motivo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="849"/>
        <source>Se importarán {n} de {total} filas del archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="852"/>
        <source>No se importarán estas filas:</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="855"/>
        <source>y %n más (míralas en «Mostrar detalles»)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="858"/>
        <source>Importar solo una parte del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="863"/>
        <source>Importar esas filas</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoImportarPerfiles</name>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="126"/>
        <source>Importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="127"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="128"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="129"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="155"/>
        <source>✖ No válido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="157"/>
        <source>Omitido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="159"/>
        <source>✔ Nuevo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="161"/>
        <source>⚠ Reemplaza al existente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="162"/>
        <source>⚠ Nombre repetido: se conservan ambos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="177"/>
        <source>Importar «{nombre}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="218"/>
        <source>Importar perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="229"/>
        <source>El archivo tiene 1 perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="231"/>
        <source>El archivo tiene %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="233"/>
        <source>Se pueden importar {n}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="235"/>
        <source>Resumen del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="239"/>
        <source>Todavía no se guardó nada. Elige qué perfiles quieres importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="250"/>
        <source>Perfiles del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="256"/>
        <source>Este nombre ya existe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="257"/>
        <source>Qué hacer con un nombre repetido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="258"/>
        <source>Conservar ambos (el importado se renombra)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="259"/>
        <source>Reemplazar el perfil que ya tengo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="260"/>
        <source>Omitir este perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="278"/>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="430"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="314"/>
        <source>(perfil {n} sin nombre válido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="359"/>
        <source>Importar 1 perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="359"/>
        <source>Importar %n perfiles</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="378"/>
        <source>Ya existe «{nombre}» y es un perfil de fábrica: no se puede reemplazar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="381"/>
        <source>Ya tienes un perfil llamado «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="419"/>
        <source>Se reemplazará %n perfil tuyo por el del archivo:</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="423"/>
        <source>Esta acción no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="427"/>
        <source>Reemplazar perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="429"/>
        <source>Reemplazar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoInforme</name>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="34"/>
        <source>Simulación del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="36"/>
        <source>Informe del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="45"/>
        <source>Texto del informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="50"/>
        <source>Copiar informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="53"/>
        <source>Guardar informe…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="55"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="71"/>
        <source>Informe copiado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/informe.py" line="81"/>
        <source>Guardado en {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoPausaLote</name>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="59"/>
        <source>Motivo de la pausa</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="72"/>
        <source>Comprobar y continuar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="76"/>
        <source>Continuar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="82"/>
        <source>Reconectar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="87"/>
        <source>Seguir sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="90"/>
        <source>Reintentar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="104"/>
        <source>Detener el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="105"/>
        <source>Cancelar lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="130"/>
        <source>desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="140"/>
        <source>«Comprobar y continuar» mira qué pasó con las máquinas sin confirmar y después envía solo las que faltaban. Nunca vuelve a enviar una máquina que ya salió.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="147"/>
        <source>Hubo un problema que afecta a todo el lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="150"/>
        <source>No se enviará ninguna máquina más hasta que decidas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/pausa_lote.py" line="154"/>
        <source>Puedes seguir sin etiquetas. En ese caso, «Deshacer» solo podrá eliminar las máquinas que ProxLaunch confirme que creó él mismo.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoPerfilesMaquina</name>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="68"/>
        <source>De fábrica</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="69"/>
        <source>Propio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="104"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="105"/>
        <source>Tipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="106"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="119"/>
        <source>{nombre}, {tipo}: {resumen}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="215"/>
        <source>Administrar perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="238"/>
        <source>Un perfil de máquina es un punto de partida con el hardware ya elegido (procesador, memoria, discos y red). No es una plantilla de Proxmox ni un perfil de conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="249"/>
        <source>Perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="254"/>
        <source>Descripción del perfil seleccionado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="257"/>
        <source>Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="271"/>
        <source>Usar en el formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="272"/>
        <source>Guardar el formulario como perfil…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="273"/>
        <source>Duplicar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="274"/>
        <source>Renombrar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="275"/>
        <source>Eliminar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="288"/>
        <source>Importar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="289"/>
        <source>Exportar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="290"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="345"/>
        <source>Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="352"/>
        <source>No se pudo leer tu archivo de perfiles (revisa sus permisos). Solo se muestran los de fábrica y no se guardará nada nuevo hasta que se pueda leer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="360"/>
        <source>Tu archivo de perfiles estaba dañado. Se guardó una copia («{copia}») y se empezó con la lista vacía.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="367"/>
        <source>Se descartó 1 campo no válido del archivo de perfiles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="370"/>
        <source>Se descartaron %n campos no válidos del archivo de perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="397"/>
        <source>Este perfil no tiene descripción.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="427"/>
        <source>Duplicar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="428"/>
        <source>Duplicar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="430"/>
        <source>Copia de {nombre}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="442"/>
        <source>Se creó «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="454"/>
        <source>Renombrar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="455"/>
        <source>Guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="470"/>
        <source>Se cambió el nombre a «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="483"/>
        <source>Eliminar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="485"/>
        <source>¿Eliminar el perfil «{nombre}»? Los lotes que ya guardaste no cambian.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="487"/>
        <source>Eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="488"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="497"/>
        <source>Se eliminó «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="511"/>
        <source>perfiles-proxlaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="519"/>
        <source>Exportando…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="533"/>
        <source>Se exportó 1 perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="535"/>
        <source>Se exportaron %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="571"/>
        <source>Leyendo el archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="604"/>
        <source>Se importó 1 perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="606"/>
        <source>Se importaron %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
</context>
<context>
    <name>DialogoPlantillaImagen</name>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="195"/>
        <source>Ayuda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="351"/>
        <source>Qué hace este asistente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="352"/>
        <source>Qué vas a hacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="360"/>
        <source>1. La imagen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="361"/>
        <source>Un archivo de mi equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="362"/>
        <source>Una dirección web (la descarga el servidor)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="363"/>
        <source>Una imagen que ya está en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="376"/>
        <source>Ningún archivo elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="377"/>
        <source>Archivo de imagen elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="378"/>
        <source>Elegir archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="393"/>
        <source>https://…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="394"/>
        <source>Dirección web de la imagen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="397"/>
        <source>Comprobar el certificado del servidor web (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="416"/>
        <source>Imágenes que ya están en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="418"/>
        <source>Actualizar lista</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="427"/>
        <source>Opcional: suma de verificación (SHA-256…)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="428"/>
        <source>Suma de verificación de la imagen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="442"/>
        <source>2. Dónde se crea</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="444"/>
        <source>Nodo donde se crea la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="448"/>
        <source>Almacenamiento donde queda la imagen importada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="452"/>
        <source>Almacenamiento del disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="457"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="458"/>
        <source>Imagen importada en</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="459"/>
        <source>Disco de la máquina en</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="464"/>
        <source>3. La máquina modelo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="466"/>
        <source>Nombre de la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="471"/>
        <source>Número de la máquina (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="476"/>
        <source>Sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="480"/>
        <source>Núcleos por socket</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="486"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="491"/>
        <source> GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="487"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="527"/>
        <source>Memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="492"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="528"/>
        <source>Tamaño final del disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="496"/>
        <source>SeaBIOS (el clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="497"/>
        <source>UEFI (OVMF)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="498"/>
        <source>Firmware de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="501"/>
        <source>Red (bridge)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="506"/>
        <source>Modelo de la tarjeta de red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="510"/>
        <source>Sin VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="511"/>
        <source>VLAN de la red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="515"/>
        <source>socket(s) ×</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="517"/>
        <source>núcleo(s)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="524"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="525"/>
        <source>Número (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="526"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="529"/>
        <source>Firmware</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="530"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="538"/>
        <source>4. Opciones para imágenes cloud</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="541"/>
        <source>Unidad cloud-init (donde Proxmox deja los datos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="542"/>
        <source>Consola serie (la que esperan las imágenes cloud)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="544"/>
        <source>Agente invitado (para conocer la IP de las copias)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="554"/>
        <source>5. Valores de cloud-init (opcional)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="555"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="559"/>
        <source>Valores de cloud-init para las copias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="561"/>
        <source>Qué es esto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="564"/>
        <source>Por ejemplo: ubuntu (vacío = el de la imagen)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="566"/>
        <source>Usuario por defecto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="570"/>
        <source>Una clave pública por línea (ssh-ed25519 AAAA… tu@equipo)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="572"/>
        <source>Claves SSH públicas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="575"/>
        <source>Añadir archivo .pub…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="582"/>
        <source>Pedir IP por DHCP en la primera tarjeta (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="587"/>
        <source>Por ejemplo: 1.1.1.1 8.8.8.8</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="588"/>
        <source>Servidores DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="591"/>
        <source>Por ejemplo: lab.local</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="592"/>
        <source>Dominio de búsqueda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="595"/>
        <source>Como la plantilla (sin cambios)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="596"/>
        <source>Sí, actualizar en el primer arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="597"/>
        <source>No actualizar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="598"/>
        <source>Actualizar paquetes al arrancar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="602"/>
        <source>Aquí no hay campo de contraseña a propósito: se copiaría a todas las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="607"/>
        <source>Usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="608"/>
        <source>Claves SSH</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="612"/>
        <source>DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="613"/>
        <source>Dominio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="614"/>
        <source>Actualizar paquetes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="623"/>
        <source>6. Confirmar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="633"/>
        <source>Usar la que ya está (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="634"/>
        <source>Reemplazarla por la nueva</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="640"/>
        <source>Entiendo que la subida puede fallar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="659"/>
        <source>Progreso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="667"/>
        <source>Avance del paso actual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="681"/>
        <source>Comprobar ahora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="683"/>
        <source>Borrar la máquina a medio crear…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="717"/>
        <source>Crear plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="722"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1473"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1876"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1947"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="766"/>
        <source>Leyendo el archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="791"/>
        <source>Dejando de esperar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="936"/>
        <source>Elegir la imagen de disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="938"/>
        <source>Imágenes de disco (*.qcow2 *.img *.raw *.vmdk)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="959"/>
        <source>La imagen mide {tam} (tamaño del disco virtual).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="971"/>
        <source>Se subirá como «{nombre}» (el contenido del archivo no cambia).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1139"/>
        <source>Elegir claves públicas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1141"/>
        <source>Claves públicas (*.pub);;Todos los archivos (*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1318"/>
        <source>…y {n} más.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1372"/>
        <source>Comprobando el servidor (solo lecturas, no se escribe nada)…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1421"/>
        <source>Ya hay un archivo con ese nombre en el servidor («{volid}»). Elige si usar el que ya está o reemplazarlo, y vuelve a pulsar «Crear plantilla».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1460"/>
        <source>La dirección usa http://: no se puede garantizar que el archivo no fue alterado por el camino.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1465"/>
        <source>No se comprobará el certificado del servidor web: podrías descargar un archivo de un sitio falso.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1470"/>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1472"/>
        <source>Crear la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1529"/>
        <source>Trabajando…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1573"/>
        <source>Tiempo transcurrido: {t}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1664"/>
        <source>Para tener en cuenta:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1695"/>
        <source>No sabemos cómo terminó el paso «{paso}» (se perdió la conexión o se dejó de esperar). Pulsa «Comprobar ahora» para consultarlo en el servidor: solo lee, no cambia nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1705"/>
        <source>Se detuvo antes de terminar el paso «{paso}». Lo que ya se envió al servidor sigue su curso y no se borró nada. Puedes continuar desde aquí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1717"/>
        <source>Continuar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1824"/>
        <source>Comprobando en el servidor…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1873"/>
        <source>Borrar la máquina a medio crear</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1875"/>
        <source>Borrar la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1881"/>
        <source>Borrando la máquina…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1941"/>
        <source>Dejar de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1944"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1975"/>
        <source>El asistente está trabajando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1977"/>
        <source>Dejar de esperar y cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/plantilla_imagen.py" line="1978"/>
        <source>Seguir aquí</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoSubida</name>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="864"/>
        <source>Subir un ISO desde mi equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="866"/>
        <source>Subir un disco desde mi equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="868"/>
        <source>Subir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="872"/>
        <source>Ningún archivo elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="873"/>
        <source>Archivo elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="874"/>
        <source>Elegir archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="884"/>
        <source>Datos del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="888"/>
        <source>Nombre del archivo en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="898"/>
        <source>Archivo del equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="899"/>
        <source>Nombre en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="925"/>
        <source>Leyendo el archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="951"/>
        <source>Imágenes ISO (*.iso *.img);;Todos los archivos (*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="953"/>
        <source>Discos (*.qcow2 *.vmdk *.raw *.img);;Todos los archivos (*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="954"/>
        <source>Elegir archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="961"/>
        <source>{nombre} · {tamano}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1013"/>
        <source>Se subirá «{nombre}» ({tamano}) al almacenamiento «{storage}» del nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1037"/>
        <source>Dejando de esperar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1038"/>
        <source>Cancelando…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1042"/>
        <source>Dejar de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="1043"/>
        <source>Cancelar subida</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoTransferencia</name>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="183"/>
        <source>La dirección apunta a un equipo de la red interna del servidor. Descárgala solo si sabes de qué equipo se trata.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="195"/>
        <source>La dirección usa el puerto {puerto}, que no es el habitual (80 o 443).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="210"/>
        <source>La huella usa un algoritmo antiguo ({algoritmo}): ya no protege de un archivo manipulado a propósito. Si puedes, usa una huella SHA-256 o SHA-512.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="220"/>
        <source>Esta subida no se puede deshacer desde ProxLaunch (requeriría un permiso de administrador). Si te equivocas, pídele al administrador que borre el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="225"/>
        <source>Esta descarga no se puede deshacer desde ProxLaunch (requeriría un permiso de administrador). Si te equivocas, pídele al administrador que borre el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="275"/>
        <source>Resultado de las comprobaciones</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="280"/>
        <source>Usar el existente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="285"/>
        <source>Cambiar el nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="298"/>
        <location filename="../../interfaz/dialogos/transferencia.py" line="303"/>
        <source>Entiendo que la subida puede fallar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="314"/>
        <source>Resumen de lo que se va a hacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="322"/>
        <source>Aviso: no se puede deshacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="332"/>
        <source>Estado de la transferencia</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="338"/>
        <source>Progreso de la transferencia</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="343"/>
        <source>Velocidad y tiempo restante</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="354"/>
        <source>Resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="365"/>
        <source>Reintentar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="371"/>
        <location filename="../../interfaz/dialogos/transferencia.py" line="765"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="458"/>
        <source>Todavía no se conoce el servidor. Conéctate primero.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="467"/>
        <source>No hay un almacenamiento donde guardar el archivo. Pídele al administrador que active este tipo de contenido en un almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="496"/>
        <source>Comprobando el destino…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="680"/>
        <source>Duración: {tiempo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="687"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="699"/>
        <source>Listo. El archivo «{volid}» está en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="705"/>
        <source>Dejaste de esperar. El archivo ya se envió y el servidor sigue copiándolo: no se puede cancelar desde ProxLaunch y puede aparecer en el catálogo cuando termine. Revísalo allí más tarde.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="712"/>
        <source>La descarga sigue en el servidor y no se puede cancelar desde ProxLaunch. Cuando termine, abre el catálogo para ver el resultado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="722"/>
        <source>La transferencia falló.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="741"/>
        <source>Se canceló. No se guardó ningún archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="745"/>
        <source>Se canceló, pero el archivo parcial quedó guardado: pídele al administrador que lo borre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="750"/>
        <source>Se canceló. No se pudo comprobar si quedó algún archivo a medias: míralo en el catálogo del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="791"/>
        <location filename="../../interfaz/dialogos/transferencia.py" line="817"/>
        <source>Tiempo transcurrido: {tiempo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencia.py" line="837"/>
        <source>El archivo está vacío.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoTransferenciasSesion</name>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="55"/>
        <source>Archivos subidos o descargados en esta sesión de ProxLaunch:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="93"/>
        <source>Archivos subidos en esta sesión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="99"/>
        <source>Estos archivos quedan en el servidor hasta que un administrador los borre: ProxLaunch no puede borrarlos. La lista solo existe mientras la aplicación está abierta y no se guarda sola.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="110"/>
        <source>Hora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="111"/>
        <source>Tipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="112"/>
        <source>Archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="113"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="114"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="115"/>
        <source>Tamaño</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="116"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="119"/>
        <source>Archivos transferidos en esta sesión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="50"/>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="126"/>
        <source>En esta sesión no se ha subido ni descargado ningún archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="131"/>
        <source>Copiar lista</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="134"/>
        <source>Guardar como .txt…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="137"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="208"/>
        <source>Guardar la lista de archivos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="210"/>
        <source>Texto (*.txt)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/transferencias_sesion.py" line="222"/>
        <source>No se pudo guardar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FormularioVM</name>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="220"/>
        <source>General</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="224"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1199"/>
        <source>Número de máquina (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="226"/>
        <source>por ejemplo srv-web-01</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="227"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="229"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="230"/>
        <source>Manual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="247"/>
        <source>Nodo destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="271"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="274"/>
        <source>Encender al terminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="272"/>
        <source>Enciende la máquina cuando termina de crearse y de ajustarse.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="277"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="282"/>
        <source>Esperar la IP de cada máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="279"/>
        <source>Tras encender cada máquina, ProxLaunch pregunta a Proxmox por su IP hasta que la tenga o se acabe el plazo. Necesita el agente invitado dentro de la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="286"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="295"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1219"/>
        <source>Plazo (segundos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="288"/>
        <source>Segundos que se espera la IP de cada máquina, entre 10 y 1800.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="298"/>
        <source>Esperar la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="300"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="304"/>
        <source>Arrancar con el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="301"/>
        <source>La máquina se enciende sola cuando arranca el servidor Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="307"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="314"/>
        <source>Añadir notas de origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="309"/>
        <source>Escribe en las notas de la máquina que la creó ProxLaunch: versión, fecha, lote y perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="316"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="318"/>
        <source>Incluir mi usuario en las notas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="317"/>
        <source>Escribe tu usuario de Proxmox en las notas de origen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="321"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="324"/>
        <source>Cualquiera con acceso a la máquina en Proxmox podrá ver tu usuario.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="335"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="341"/>
        <source>Notas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="337"/>
        <source>Texto libre para la descripción de la máquina (opcional)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="343"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="351"/>
        <source>Etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="344"/>
        <source>por ejemplo web, produccion</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="347"/>
        <source>Separadas por comas. Se suman a las etiquetas que ProxLaunch pone siempre. Solo minúsculas, números, «_», «-», «+» y «.».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="353"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="356"/>
        <source>Pool</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="354"/>
        <source>Pool de recursos donde se crea la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="360"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="364"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1213"/>
        <source>Orden de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="362"/>
        <source>Número de orden con que arranca respecto a otras máquinas. Vacío = sin orden.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="367"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="371"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1214"/>
        <source>Espera (s)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="369"/>
        <source>Segundos que se espera tras arrancar esta máquina. Vacío = sin espera.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="373"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="376"/>
        <source>Proteger contra borrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="374"/>
        <source>Proxmox no dejará eliminar la máquina hasta que quites la protección.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="485"/>
        <source>Firmware</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="487"/>
        <source>SeaBIOS (clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="488"/>
        <source>UEFI (OVMF)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="489"/>
        <source>Tipo de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="492"/>
        <source>Almacenamiento de UEFI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="500"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="501"/>
        <source>TPM 2.0</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="503"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="504"/>
        <source>Agente de QEMU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="517"/>
        <source>Cómputo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="522"/>
        <source>Sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="525"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1200"/>
        <source>Núcleos por socket</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="530"/>
        <source>Tipo de CPU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="535"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1201"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="537"/>
        <source>Predeterminado de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="538"/>
        <source>Activado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="539"/>
        <source>Desactivado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="540"/>
        <source>Ballooning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="544"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1203"/>
        <source>Memoria mínima (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="574"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="575"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="581"/>
        <source>Controlador SCSI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="594"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="778"/>
        <source>El almacenamiento de UEFI «{recurso}» no existe en el nodo «{nodo}». Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1071"/>
        <source>Ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1148"/>
        <source>El servidor no tiene el pool «{pool}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1206"/>
        <source>Tamaño del disco {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1210"/>
        <source>VLAN de {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1220"/>
        <source>MTU de {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1222"/>
        <source>Límite de {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1297"/>
        <source>Nodo elegido: {nodo} ({motivo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="763"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1337"/>
        <source>El almacenamiento «{recurso}» no existe en el nodo «{nodo}». Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="195"/>
        <source>Origen del sistema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="199"/>
        <source>El hardware, los discos y la red se copian de la plantilla. Arriba eliges solo lo que quieres cambiar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="206"/>
        <source>El primer disco de la máquina será la copia del disco que elegiste.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="770"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1344"/>
        <source>La red «{recurso}» no existe en el nodo «{nodo}». Elige otra.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1371"/>
        <source>Automático (el del primer disco)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1404"/>
        <source>Este servidor no tiene almacenamiento para discos de máquinas virtuales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="1560"/>
        <source>{n} procesadores virtuales en total</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>InformeLote</name>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="89"/>
        <source>{s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="90"/>
        <source>{m} min {s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="115"/>
        <source>Procesadores: {n} ({s} × {c})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="118"/>
        <source>Memoria: {m:g} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="121"/>
        <source>Arranque: {f}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="127"/>
        <source>Discos: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="129"/>
        <source>Discos: ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="134"/>
        <source>Redes: {r}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="136"/>
        <source>Redes: ninguna</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="145"/>
        <source>Deshacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="151"/>
        <location filename="../../interfaz/informe_lote.py" line="266"/>
        <location filename="../../interfaz/informe_lote.py" line="298"/>
        <location filename="../../interfaz/informe_lote.py" line="395"/>
        <location filename="../../interfaz/informe_lote.py" line="550"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="152"/>
        <location filename="../../interfaz/informe_lote.py" line="551"/>
        <source>VMID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="153"/>
        <location filename="../../interfaz/informe_lote.py" line="436"/>
        <location filename="../../interfaz/informe_lote.py" line="552"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="154"/>
        <location filename="../../interfaz/informe_lote.py" line="553"/>
        <source>Resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="155"/>
        <source>Detalle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="165"/>
        <source>Los archivos que subiste (ISOs e imágenes de disco) y las plantillas no se eliminan al deshacer: Deshacer solo borra las máquinas creadas por el lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="260"/>
        <source>Direcciones IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="267"/>
        <source>Estado de la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="268"/>
        <source>IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="269"/>
        <source>Otras direcciones</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="299"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="300"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="301"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="302"/>
        <source>Redes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="305"/>
        <source>ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="396"/>
        <source>Origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="397"/>
        <source>Fuente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="398"/>
        <source>Sistema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="399"/>
        <source>Modo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="400"/>
        <source>Ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="422"/>
        <source>Sistema operativo de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="433"/>
        <source>Tipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="434"/>
        <source>Archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="435"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="437"/>
        <source>Tamaño</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="438"/>
        <source>Hora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="439"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="440"/>
        <source>Identificador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="457"/>
        <source>Archivos subidos o descargados en esta sesión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="461"/>
        <source>Si ya no los necesitas, pídele a un administrador que los borre desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="470"/>
        <source>Permisos no verificados: no se pudieron leer los permisos del usuario, así que Proxmox pudo rechazar alguna máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="483"/>
        <source>ProxLaunch — Simulación del lote {id}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="485"/>
        <source>ProxLaunch — Informe del lote {id}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="489"/>
        <source>SIMULACIÓN — no se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="491"/>
        <source>Fecha: {f}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="494"/>
        <source>Perfil: {p}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="497"/>
        <source>Versión de Proxmox: {v}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="503"/>
        <source>Servidor: clúster «{n}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="508"/>
        <source>Servidor: individual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="512"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="514"/>
        <source>Pedidas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="517"/>
        <source>Creadas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="520"/>
        <source>Creadas con avisos: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="525"/>
        <source>Con error: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="530"/>
        <source>Sin confirmar (no sabemos si se crearon): {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="542"/>
        <source>No enviadas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="547"/>
        <source>Máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="265"/>
        <location filename="../../interfaz/informe_lote.py" line="297"/>
        <location filename="../../interfaz/informe_lote.py" line="394"/>
        <location filename="../../interfaz/informe_lote.py" line="549"/>
        <source>N.º</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="554"/>
        <source>Duración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="555"/>
        <source>UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="564"/>
        <source>Detalle de las máquinas con problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="572"/>
        <source>    Código: {c}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="578"/>
        <source>    Detalles técnicos: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="585"/>
        <source>Configuración de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="598"/>
        <source>Avisos del plan</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="615"/>
        <source>Cómo encontrar estas máquinas en Proxmox: llevan las etiquetas «{e1}» y «{e2}{id}» (si el lote las activó) y sus números son {rangos}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="660"/>
        <source>Guardar informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="662"/>
        <source>Texto (*.txt)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModeloCatalogoVolumenes</name>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="111"/>
        <source>Extensión no admitida (solo {extensiones})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="115"/>
        <source>Una ruta del servidor no se puede usar: elige un archivo de la lista</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="119"/>
        <source>Nombre no admitido: solo letras, números, punto, guion y guion bajo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="209"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="210"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="211"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="212"/>
        <source>Tamaño</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="213"/>
        <source>Fecha</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="214"/>
        <source>Nota</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="253"/>
        <source>Drivers virtio-win para Windows</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModeloPlantillas</name>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="131"/>
        <source>Bloqueada ({bloqueo}): espera a que termine lo que Proxmox está haciendo con ella</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="136"/>
        <source>Falta el permiso VM.Clone</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="312"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="313"/>
        <source>VMID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="314"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="315"/>
        <source>Tamaño de los discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="316"/>
        <source>Nota</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModelosTabla</name>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="237"/>
        <location filename="../../interfaz/modelos_tabla.py" line="347"/>
        <source>Fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="239"/>
        <source>N.º</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="240"/>
        <location filename="../../interfaz/modelos_tabla.py" line="348"/>
        <location filename="../../interfaz/modelos_tabla.py" line="528"/>
        <location filename="../../interfaz/modelos_tabla.py" line="673"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="242"/>
        <location filename="../../interfaz/modelos_tabla.py" line="350"/>
        <location filename="../../interfaz/modelos_tabla.py" line="530"/>
        <location filename="../../interfaz/modelos_tabla.py" line="675"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="243"/>
        <location filename="../../interfaz/modelos_tabla.py" line="354"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="244"/>
        <location filename="../../interfaz/modelos_tabla.py" line="353"/>
        <source>Discos (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="249"/>
        <location filename="../../interfaz/modelos_tabla.py" line="351"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="250"/>
        <location filename="../../interfaz/modelos_tabla.py" line="352"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="253"/>
        <location filename="../../interfaz/modelos_tabla.py" line="358"/>
        <source>Sistema operativo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="311"/>
        <source>Fila {n}: {nombre}, número {vmid}, nodo {nodo}, {v} procesadores virtuales, {m} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="324"/>
        <source>Máquina {n}: {nombre}, número {vmid}, nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="355"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="385"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="413"/>
        <source>Fila {n}: {nombre}. {origen}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="416"/>
        <source>Fila {n}: {nombre}, {v} procesadores virtuales, {m} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="432"/>
        <source>Se creó aunque Proxmox tardó en responder.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="455"/>
        <source>Se creó, pero hay avisos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="466"/>
        <source>Se comprobó y no existe en Proxmox. Puedes reintentarla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="470"/>
        <source>Existe en Proxmox, pero no podemos asegurar que la creó este lote. No se eliminará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="479"/>
        <source>Quedó a medias; elimínala con «Deshacer…» o desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="527"/>
        <location filename="../../interfaz/modelos_tabla.py" line="672"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="533"/>
        <source>IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="534"/>
        <location filename="../../interfaz/modelos_tabla.py" line="676"/>
        <source>Detalle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="614"/>
        <source>{nombre}, número {vmid}, nodo {nodo}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="620"/>
        <source>IP: {ip}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="723"/>
        <source>{nombre}, número {vmid}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModelosTablaCsv</name>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="82"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/modelos_tabla_csv.py" line="221"/>
        <source>y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="251"/>
        <source>Incluir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="252"/>
        <source>Fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="253"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="254"/>
        <source>Perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="256"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="257"/>
        <source>Núcleos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="258"/>
        <source>Memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="259"/>
        <source>Disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="260"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="261"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="262"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="318"/>
        <source>auto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="321"/>
        <source>automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="377"/>
        <source>Una fila con error no se puede importar. Corrígela en el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="382"/>
        <source>Incluir la fila {n}: no se puede, tiene un error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="390"/>
        <source>Incluir la fila {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="395"/>
        <source>sí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="397"/>
        <source>no</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="412"/>
        <source>Fila {n}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="418"/>
        <source>Fila {n}, {columna}: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PanelAvisos</name>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="41"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="43"/>
        <source>Cerrar los avisos</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PanelLoteFilas</name>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="28"/>
        <source>1 máquina desde el archivo «{origen}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/lote_filas.py" line="31"/>
        <source>%n máquinas desde el archivo «{origen}»</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="35"/>
        <source>1 máquina del lote «{origen}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/lote_filas.py" line="38"/>
        <source>%n máquinas del lote «{origen}»</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="66"/>
        <source>Título del lote por filas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="69"/>
        <source>Cada máquina trae su propia configuración. Para cambiar algo, corrige el archivo e impórtalo de nuevo, o quita las filas que no quieras.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="78"/>
        <source>En las máquinas clonadas, los procesadores, la memoria y los discos salen de la plantilla: aquí solo ves lo que pediste cambiar y «—» significa «igual que la plantilla».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="90"/>
        <source>Problemas de las filas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="95"/>
        <source>Máquinas del lote por filas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="102"/>
        <source>Ver resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="106"/>
        <source>Ver el resumen del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="109"/>
        <source>Revisar filas…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="112"/>
        <source>Revisar las filas del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="115"/>
        <source>Guardar lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="118"/>
        <source>Guardar el lote en un archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="121"/>
        <source>Quitar las filas seleccionadas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="124"/>
        <source>Quitar las filas seleccionadas del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="127"/>
        <location filename="../../interfaz/vistas/lote_filas.py" line="130"/>
        <source>Salir del lote por filas</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PanelLoteNoEncaja</name>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="46"/>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="52"/>
        <source>Este lote no encaja en este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="59"/>
        <source>Algunos valores guardados en el lote no existen aquí. Elige otros para poder continuar: ProxLaunch no cambia nada por su cuenta.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="123"/>
        <source>Afecta a 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="123"/>
        <source>Afecta a %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="125"/>
        <source>(n.º {lista}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="129"/>
        <source>Usar otro valor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="131"/>
        <source>Almacenamiento que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="135"/>
        <source>Red que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="137"/>
        <source>ISO que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="139"/>
        <source>CD de drivers que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="141"/>
        <source>Imagen de disco que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="145"/>
        <source>Plantilla que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="146"/>
        <source>Nodo que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="160"/>
        <source>Usar otro…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="161"/>
        <source>Usar otro en lugar de «{valor}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="165"/>
        <source>Disponibles en este servidor: {lista}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="170"/>
        <source>Este servidor no tiene ninguna alternativa.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="175"/>
        <source>Pasar a Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="177"/>
        <source>Pasar a Automático en lugar del nodo «{valor}»</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PanelProgreso</name>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="48"/>
        <source>Progreso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="67"/>
        <source>Identificador de la tarea (UPID):</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="74"/>
        <source>Copiar UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="78"/>
        <source>Crear otra</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="82"/>
        <source>Seguir esperando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="85"/>
        <location filename="../../interfaz/vistas/progreso.py" line="233"/>
        <source>Comprobar ahora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="88"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="90"/>
        <source>Deshacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="93"/>
        <source>Crear sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="97"/>
        <source>Reintentar ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="100"/>
        <source>Vuelve a aplicar las etiquetas, los procesadores, la memoria o el tamaño del disco que no se pudieron cambiar tras clonar. No crea máquinas nuevas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="108"/>
        <source>Dejar de esperar la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="111"/>
        <source>Deja de preguntar a la máquina por su IP. La máquina no se toca.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="152"/>
        <source>Sin tareas en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="231"/>
        <source>Comprobar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PerfilesFabrica</name>
    <message>
        <location filename="../../interfaz/textos.py" line="1846"/>
        <source>Servidor pequeño</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1847"/>
        <source>Para pruebas y servicios ligeros.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1850"/>
        <source>Servidor mediano</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1851"/>
        <source>Para aplicaciones web.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1854"/>
        <source>Base de datos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1855"/>
        <source>Para bases de datos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1858"/>
        <source>Servidor grande</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1859"/>
        <source>Para cargas pesadas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1862"/>
        <source>Escritorio (hardware compatible)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1863"/>
        <source>Para sistemas que aún no traen controladores virtio: disco SATA y tarjeta de red Intel E1000.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1870"/>
        <source>Mínimo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1871"/>
        <source>Disco y red básicos, para probar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1874"/>
        <source>Windows 11 (escritorio)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1875"/>
        <source>Para instalar Windows 11: arranque UEFI, TPM y agente de QEMU. El ISO se elige después.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1882"/>
        <source>Windows Server</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1883"/>
        <source>Para instalar Windows Server 2022 o 2025: arranque UEFI, TPM y agente de QEMU. El ISO se elige después.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1890"/>
        <source>Linux (Red Hat y otros)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1891"/>
        <source>Para instalar Linux, en especial Red Hat, Rocky o Alma. El ISO se elige después.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ProgresoLote</name>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="79"/>
        <source>{t} de {n} terminadas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="85"/>
        <source>{c} con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="89"/>
        <source>{c} sin confirmar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="93"/>
        <source>{c} sin enviar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="96"/>
        <source>{c} en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="104"/>
        <source>Estado: {estado} ({codigo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="108"/>
        <source>Nodo: {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="113"/>
        <source>Sistema operativo: {o}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="119"/>
        <source>IP: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="123"/>
        <source>Otras direcciones: {o}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="129"/>
        <source>Motivo: {m}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="133"/>
        <source>Avisos: {a}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="137"/>
        <source>Código: {c}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="143"/>
        <source>Mensaje original: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="148"/>
        <source>Registro de la tarea:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="188"/>
        <source>Avance del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="193"/>
        <source>Mostrar solo problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="199"/>
        <source>Estado de cada máquina del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="207"/>
        <source>Identificador de la tarea (UPID):</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="214"/>
        <source>UPID de la máquina seleccionada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="216"/>
        <source>Copiar UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="226"/>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="468"/>
        <source>Deshaciendo el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="231"/>
        <source>Estado de cada máquina eliminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="242"/>
        <source>Resumen de las IP de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="246"/>
        <source>Dejar de esperar la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="249"/>
        <source>Deja de preguntar a las máquinas por su IP. Las máquinas ya creadas no se tocan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="255"/>
        <source>Copiar lista de IPs</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="258"/>
        <source>Copia «nombre», un tabulador y la IP, una máquina por línea.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="263"/>
        <source>Exportar IPs…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="266"/>
        <source>Guarda en un archivo CSV el nombre, el número, el nodo y la IP.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="284"/>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="435"/>
        <source>Cancelar lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="287"/>
        <source>Decidir qué hacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="292"/>
        <source>Comprobar ahora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="296"/>
        <source>Deshacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="298"/>
        <source>Reintentar pendientes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="301"/>
        <source>Reintentar ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="304"/>
        <source>Informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="306"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="463"/>
        <source>Lote terminado (1 máquina)</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/progreso_lote.py" line="464"/>
        <source>Lote terminado (%n máquinas)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="470"/>
        <source>Comprobando las máquinas dudosas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="472"/>
        <source>Creando 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/progreso_lote.py" line="473"/>
        <source>Creando %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="428"/>
        <source>Dejar de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="432"/>
        <source>Detener lo que falta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="440"/>
        <source>Comprobar la dudosa</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/progreso_lote.py" line="444"/>
        <source>Comprobar las %n dudosas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
</context>
<context>
    <name>ResumenLote</name>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="62"/>
        <source>Vas a crear una máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="63"/>
        <source>Vas a crear %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="69"/>
        <source>Crear de verdad esta máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="70"/>
        <source>Crear de verdad estas %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="74"/>
        <source>Crear 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="75"/>
        <source>Crear %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="80"/>
        <source>Reducir a 1</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="81"/>
        <source>Reducir a %n</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="85"/>
        <source>Quitar las filas que no caben</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="90"/>
        <source>Se van a crear {n} de las {total} filas del archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="97"/>
        <source>1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="98"/>
        <source>%n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="138"/>
        <source>{nombre}: varía según la fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="155"/>
        <source>{texto} ({n} caracteres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="166"/>
        <source>{nombre}: sí en {n} de {total} máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="285"/>
        <source>Usuario inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="291"/>
        <source>Claves SSH</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="301"/>
        <source>Contraseña inicial (definida, oculta)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="312"/>
        <source>Red net{i}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="318"/>
        <source>DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="324"/>
        <source>Dominio de búsqueda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="330"/>
        <source>Actualizar paquetes al arrancar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="340"/>
        <source>Script: {tipo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="353"/>
        <source>Activar el agente invitado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="362"/>
        <source>plazo {n} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="364"/>
        <source>plazos distintos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="366"/>
        <source>Esperar la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="369"/>
        <source>{nombre}: sí ({plazo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="375"/>
        <source>{nombre}: sí en {n} de {total} máquinas ({plazo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="398"/>
        <source>… y {n} máquinas más</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="402"/>
        <source>IP que recibirá cada máquina (calculadas antes de crear):</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="405"/>
        <source>ProxLaunch no puede comprobar si una IP ya está en uso en tu red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="448"/>
        <source>Origen de las máquinas: {partes}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="453"/>
        <source>Origen: {origen}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="468"/>
        <source>La plantilla «{nombre}» está en {nodos}: se clona la de cada nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="475"/>
        <source>Las máquinas comparten el disco base con la plantilla (copia {modo}): no borres la plantilla mientras existan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="486"/>
        <source>Cada máquina recibirá una copia completa del disco ({t} GiB). Total: {total} GiB en «{storage}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="528"/>
        <source>Título del resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="541"/>
        <source>Máquinas que se van a crear</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="558"/>
        <source>Entiendo el riesgo de sobreasignar espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="561"/>
        <source>Confirmo que entiendo el riesgo de sobreasignar espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="571"/>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="575"/>
        <source>Nodo de destino para el reintento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="581"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="583"/>
        <source>Copiar resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="584"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="587"/>
        <source>Informe de la simulación…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="593"/>
        <source>Quitar del lote las filas que no caben en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="605"/>
        <source>Filas con el número de máquina ocupado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="610"/>
        <source>Simular</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="612"/>
        <source>Hace todas las comprobaciones y muestra lo que se enviaría, sin crear nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="727"/>
        <source>Los mismos nodos de antes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="746"/>
        <source>Preparando el resumen…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="754"/>
        <source>No se pudo preparar el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="757"/>
        <source>No se pudo consultar el servidor. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="810"/>
        <source>Puede haber otras máquinas con esos nombres que tú no puedes ver.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="836"/>
        <source>SIMULACIÓN — no se creó nada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="838"/>
        <source>Simulado con compatibilidad de Proxmox {forzada} (el servidor es {detectada})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="867"/>
        <source>Totales: {n}, {v} procesadores virtuales, {m:g} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="874"/>
        <source>«{s}» (compartido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="878"/>
        <source>«{s}» en {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="883"/>
        <source>Espacio en {donde}: {pedido} GiB de {libre} GiB libres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="898"/>
        <source>Reparto:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="904"/>
        <source>Se saltaron los números {rangos} (ya los usa otra máquina).</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="927"/>
        <source>… y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="958"/>
        <source>No caben las filas: {filas}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="976"/>
        <source>Fila {n}: el número {vmid} ya lo usa otra máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="981"/>
        <source>Asignar automáticamente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="984"/>
        <source>Asignar un número de máquina automático a la fila {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="996"/>
        <source>Asignar automáticamente a las %n filas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="1045"/>
        <source>Corrige los errores marcados para poder crear las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="1049"/>
        <source>Marca la casilla para confirmar que entiendes el riesgo de sobreasignar.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ResumenVM</name>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="196"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="197"/>
        <source>Número de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="198"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="201"/>
        <source>Memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="325"/>
        <source>Origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="57"/>
        <source>Tipo de CPU: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="64"/>
        <source>Ballooning activado, memoria mínima {valor} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="69"/>
        <source>Ballooning desactivado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="72"/>
        <source>Controlador SCSI: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="78"/>
        <source>UEFI se guarda en: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="88"/>
        <source>conexión {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="94"/>
        <source>formato {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="99"/>
        <source>sin discard</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="101"/>
        <source>sin SSD</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="103"/>
        <source>sin IO Thread</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="106"/>
        <source>Disco {n}: {cambios}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="113"/>
        <source>Red {n}: tarjeta {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="129"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="138"/>
        <location filename="../../interfaz/vistas/resumen.py" line="165"/>
        <source>Crear máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="163"/>
        <source>Ver resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="199"/>
        <source>Arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="200"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="202"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="203"/>
        <source>Redes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="204"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="205"/>
        <source>Sin red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="219"/>
        <source>SeaBIOS (clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="222"/>
        <source>{n} procesadores virtuales en total</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="226"/>
        <source>{valor} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="230"/>
        <source>los de la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="238"/>
        <source>{etiqueta}: {tam} GiB en {storage}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="271"/>
        <source>Opciones avanzadas que se aplicarán (ocultas en modo básico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="282"/>
        <source>Para crear la máquina hay que corregir:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="302"/>
        <source>Corrige los datos marcados para poder crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="330"/>
        <source>Montará el ISO «{iso}» como CD y encenderá la máquina al terminar para que empiece la instalación del sistema.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="336"/>
        <source>Montará el ISO «{iso}» como CD. ProxLaunch no enciende la máquina: arráncala tú en Proxmox para instalar el sistema.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="344"/>
        <source>disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="345"/>
        <source>CD</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="346"/>
        <source>red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="351"/>
        <source>Orden de arranque: {orden}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="359"/>
        <source>CD de drivers (virtio-win): {nombre}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="366"/>
        <source>Al instalar Windows, carga los controladores desde ese CD: vioscsi (disco), NetKVM (red) y Balloon.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="376"/>
        <source>El primer disco será una copia del disco «{imagen}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="385"/>
        <source>Forma de copiar: {modo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="394"/>
        <source>Ajustes: {ajustes}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="402"/>
        <source>La máquina comparte el disco base con la plantilla: no borres la plantilla mientras exista.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="410"/>
        <source>Para {so} el asistente aplicó:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="425"/>
        <source>Sin los drivers, Windows no verá el disco VirtIO ni la red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="440"/>
        <source>Esta máquina pide más núcleos de los que tiene el servidor ({n} en el nodo).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="447"/>
        <source>Esta máquina pide más memoria de la que tiene libre el servidor ({valor} GiB libres en el nodo).</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>SeccionCloudInit</name>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="115"/>
        <source>Sin configurar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="117"/>
        <source>DHCP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="119"/>
        <source>IP fija</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="121"/>
        <source>Tarjeta de red {n} (net{i})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="127"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="208"/>
        <source>por ejemplo 192.168.1.50/24</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="130"/>
        <source>IP de la tarjeta {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="135"/>
        <source>Sumar 1 a cada máquina del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="140"/>
        <source>por ejemplo 192.168.1.1</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="143"/>
        <source>Puerta de enlace de la tarjeta {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="151"/>
        <source>IP con máscara</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="157"/>
        <source>Puerta de enlace</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="204"/>
        <source>IP de la primera máquina, por ejemplo 192.168.1.50/24</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="222"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="396"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="927"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="937"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="945"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="953"/>
        <source>Heredado de la plantilla: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="286"/>
        <source>almacén:snippets/archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="289"/>
        <source>Identificador del script ({tipo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="326"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="625"/>
        <source>Como la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="328"/>
        <source>Ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="333"/>
        <source> (demasiado grande: máximo 1 MiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="344"/>
        <source>Escribir a mano…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="412"/>
        <source>Configuración inicial (cloud-init)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="448"/>
        <source>Cloud-init configura la máquina sola en su primer arranque con los datos que pongas aquí (usuario, claves, red). Todo es opcional: lo que dejes vacío se queda como lo tiene la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="470"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="476"/>
        <source>Usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="473"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="931"/>
        <source>por ejemplo deploy</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="483"/>
        <source>Claves SSH públicas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="486"/>
        <source>Una clave pública por línea, por ejemplo: ssh-ed25519 AAAAC3Nza… ana@portatil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="494"/>
        <source>Añadir archivo .pub…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="497"/>
        <source>Lee la clave pública de uno o varios archivos .pub (suelen estar en la carpeta .ssh de tu usuario).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="518"/>
        <source>Claves SSH</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="524"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="527"/>
        <source>Contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="531"/>
        <source>Repite la contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="535"/>
        <source>Repetir la contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="537"/>
        <source>Mostrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="539"/>
        <source>Muestra las contraseñas mientras las escribes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="544"/>
        <source>Las claves SSH son más seguras. La contraseña sirve para entrar por la consola de Proxmox si falla la red; quien tenga acceso a la consola o a la configuración podría obtenerla. Úsala solo para pruebas o como último recurso.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="563"/>
        <source>Contraseña (opcional)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="575"/>
        <source>Activar el agente invitado en la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="580"/>
        <source>Activar el agente invitado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="604"/>
        <source>DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="606"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="941"/>
        <source>por ejemplo 1.1.1.1, 8.8.8.8</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="609"/>
        <source>Servidores DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="613"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="619"/>
        <source>Dominio de búsqueda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="616"/>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="949"/>
        <source>por ejemplo lab.local</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="628"/>
        <source>Sí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="630"/>
        <source>No</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="633"/>
        <source>Actualizar paquetes en el primer arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="646"/>
        <source>Actualizar paquetes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="656"/>
        <source>Scripts de configuración (avanzado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="662"/>
        <source>Un script (snippet) es un archivo de texto guardado en el servidor que cloud-init usa para configurar la máquina, por ejemplo para instalar el agente invitado. ProxLaunch no los crea ni los sube: los deja tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="687"/>
        <source>Ver ejemplo para instalar el agente invitado…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="700"/>
        <source>Ejemplo de script para el agente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="704"/>
        <source>Copiar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="708"/>
        <source>Ejemplo de script «Datos del proveedor» (vendor) que instala y activa el agente invitado:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="897"/>
        <source>Se restableció la tarjeta de red {n}: la plantilla elegida no la tiene.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="1084"/>
        <source>Añadir claves públicas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="1086"/>
        <source>Claves públicas (*.pub);;Todos los archivos (*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="1229"/>
        <source>No se pudo leer la lista de scripts del servidor. Elige «Escribir a mano…» y escribe el identificador (almacén:snippets/archivo); no se podrá comprobar que exista.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/seccion_cloudinit.py" line="1236"/>
        <source>Leyendo la lista de scripts del servidor…</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>SelectorOrigen</name>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="108"/>
        <source>Vacía, sin sistema operativo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="111"/>
        <source>Instalar desde un archivo ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="112"/>
        <source>Usar un disco existente (qcow2, vmdk, raw)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="115"/>
        <source>Copiar una plantilla de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="188"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="192"/>
        <source>¿Cómo quieres crear la máquina?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="212"/>
        <source>¿Por qué no puedo usar alguna opción?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="243"/>
        <source>La máquina se crea con un disco vacío y sin sistema operativo. Instálalo después desde la consola de Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="273"/>
        <source>Elegir ISO…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="273"/>
        <source>Archivo ISO elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="284"/>
        <source>Elegir disco…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="284"/>
        <source>Disco elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="293"/>
        <source>Ampliar el disco a</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="297"/>
        <source>Tamaño del disco importado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="298"/>
        <source>Ampliar el disco importado a (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="310"/>
        <source>Elegir plantilla…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="310"/>
        <source>Plantilla elegida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="320"/>
        <source>Rápido y ligero (recomendado): la copia comparte el disco con la plantilla y se crea en segundos. Si el almacenamiento no lo permite, Proxmox hace una copia independiente.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="331"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="333"/>
        <source>Tipo de copia</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="347"/>
        <source>Guardar la copia en</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="349"/>
        <source>Almacenamiento de la copia</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="350"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="612"/>
        <source>El de la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="356"/>
        <source>Ajustes de la copia (opcional)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="358"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="368"/>
        <source>Procesadores (sockets)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="359"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="369"/>
        <source>Núcleos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="360"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="371"/>
        <source>Memoria (MiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="361"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="372"/>
        <source>Disco principal (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="363"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="387"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="573"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="581"/>
        <source>Igual que la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="364"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="370"/>
        <source>Tipo de CPU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="393"/>
        <source>Sistema operativo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="396"/>
        <source>Sistema operativo que vas a instalar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="397"/>
        <source>Elige el sistema operativo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="404"/>
        <source>Disco compatible (SATA): no hace falta cargar un controlador al instalar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="406"/>
        <source>Disco compatible (SATA)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="424"/>
        <source>Drivers de Windows (virtio-win)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="427"/>
        <source>Drivers virtio-win elegidos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="430"/>
        <source>Elegir otro ISO de drivers…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="435"/>
        <source>Descargarlo en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="440"/>
        <source>Ya lo tengo en mi equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="450"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="451"/>
        <source>Crear sin los drivers</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="455"/>
        <source>Sin los drivers, Windows no verá el disco VirtIO ni la red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="575"/>
        <location filename="../../interfaz/vistas/selector_origen.py" line="579"/>
        <source>Igual que la plantilla ({valor})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="593"/>
        <source>Se hará una copia rápida y ligera. Las máquinas comparten el disco base con la plantilla: no borres la plantilla mientras existan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="602"/>
        <source>Se hará una copia independiente: tarda más y ocupa el espacio completo del disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="807"/>
        <source>Conéctate a un servidor para ver si esta opción está disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="822"/>
        <source>Cambiar la forma de crear la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="823"/>
        <source>Si cambias, se pierde lo que elegiste: {que_se_pierde}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="826"/>
        <source>Cambiar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="827"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="880"/>
        <source>Ningún archivo ISO elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="881"/>
        <source>Ningún disco elegido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="888"/>
        <source>Ninguna plantilla elegida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="943"/>
        <source>La máquina se creará sin el CD de drivers.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="945"/>
        <source>Se usará el CD de drivers «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="952"/>
        <source>Se usará el CD de drivers «{nombre}», que ya está en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="956"/>
        <source>No hay ningún ISO de virtio-win en el servidor. Elige cómo conseguirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="980"/>
        <source>Para {so} el asistente va a cambiar:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_origen.py" line="988"/>
        <source>Para {so} no hace falta cambiar nada más.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>SelectorPerfil</name>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="72"/>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="80"/>
        <source>Perfil de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="90"/>
        <source>Resumen del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="94"/>
        <source>Descripción del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="98"/>
        <source>Guardar como perfil…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="102"/>
        <source>Guardar como perfil de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="109"/>
        <source>Administrar perfiles…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="112"/>
        <source>Administrar perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="119"/>
        <source>Avisos del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="123"/>
        <source>Compatibilidad del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="132"/>
        <source>Errores de compatibilidad del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="138"/>
        <source>Avisos de compatibilidad del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="172"/>
        <source>{nombre} — De fábrica</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="180"/>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="198"/>
        <source>Personalizado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="203"/>
        <source>{perfil} (modificado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="224"/>
        <source>Guardar cambios en el perfil «{nombre}»</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>TablaDiscos</name>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="50"/>
        <source>{id} ({tipo}, {libre:g} GiB libres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="54"/>
        <source>Inactivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="60"/>
        <source>{id} (no existe)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="88"/>
        <source>Quitar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="135"/>
        <source>Disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="138"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="141"/>
        <source>Tamaño (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="142"/>
        <source>Conexión (bus)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="143"/>
        <source>Formato</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="144"/>
        <source>Discard</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="145"/>
        <source>SSD</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="146"/>
        <source>IO Thread</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="158"/>
        <source>Agregar disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="205"/>
        <source>Este disco es una copia de la imagen que elegiste: tiene el tamaño de la imagen. Para hacerlo más grande usa «Ampliar el disco» en el origen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="378"/>
        <source>Elige un almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="489"/>
        <source>Automático (qcow2)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="499"/>
        <source>(automático, raw)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>TablaRedes</name>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="74"/>
        <source>{id} (no existe)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="95"/>
        <source>Sin VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="100"/>
        <source>Heredar del bridge</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="101"/>
        <source>Igual al bridge</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="108"/>
        <source>Sin límite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="109"/>
        <source>Quitar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="144"/>
        <source>Interfaz</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="145"/>
        <source>Red (bridge)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="146"/>
        <source>Tarjeta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="147"/>
        <source>VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="148"/>
        <source>MTU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="149"/>
        <source>Límite (MB/s)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="161"/>
        <source>Agregar interfaz</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="222"/>
        <source>El nodo no tiene redes (bridges) disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="444"/>
        <source>Elige una red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="512"/>
        <source>MTU de net{n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="515"/>
        <source>Límite de velocidad de net{n} (MB/s)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Textos</name>
    <message>
        <location filename="../../interfaz/textos.py" line="87"/>
        <source>este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="89"/>
        <location filename="../../interfaz/textos.py" line="99"/>
        <location filename="../../interfaz/textos.py" line="3142"/>
        <source>esa máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="91"/>
        <source>ese nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="93"/>
        <location filename="../../interfaz/textos.py" line="286"/>
        <source>un campo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="95"/>
        <source>una versión desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="101"/>
        <source>varias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="103"/>
        <source>ese almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="105"/>
        <source>un permiso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="107"/>
        <source>esa ruta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="109"/>
        <source>el archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="112"/>
        <source>un dato</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="151"/>
        <source>Proxmox respondió con un error que no conocemos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="165"/>
        <source>Las credenciales no son válidas. Revisa el usuario, el token o la contraseña.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="170"/>
        <source>Tu sesión expiró. Vuelve a iniciar sesión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="172"/>
        <source>El certificado del servidor cambió. Podría ser un cambio legítimo (renovación) o un intento de suplantación. Verifica con tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="179"/>
        <source>Primero hay que confiar en el certificado del servidor ({host}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="185"/>
        <source>Este usuario exige un método de segundo factor que ProxLaunch no admite. Usa un API Token.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="191"/>
        <source>El código no es correcto o ya venció. Espera al siguiente código e inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="198"/>
        <source>No sabemos si Proxmox recibió la orden de crear la máquina. Pulsa «Comprobar» antes de intentarlo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="207"/>
        <source>El nodo {nodo} no está disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="209"/>
        <location filename="../../interfaz/textos.py" line="455"/>
        <source>El nodo no está disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="223"/>
        <source>Proxmox no permitió crear la máquina. Lo más probable es que a tu usuario le falte {privilegio} en {ruta}. Pide a tu administrador que lo revise.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="232"/>
        <source>Tu usuario no tiene permiso para realizar esta acción. Falta {privilegio} en {ruta}. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="240"/>
        <source>Tu usuario no tiene permiso para realizar esta acción. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="248"/>
        <source>El número {vmid} ya lo usa otra máquina. Prueba con {siguiente}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="254"/>
        <source>El número {vmid} ya lo usa otra máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="260"/>
        <source>No hay espacio suficiente en «{storage}» para crear el disco. Libera espacio o elige otro almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="269"/>
        <source>Ningún nodo tiene {requerido_gib} GiB libres en un almacenamiento para discos. Reduce el tamaño de los discos o libera espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="276"/>
        <source>No hay espacio suficiente para crear el disco. Libera espacio o elige otro almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="282"/>
        <location filename="../../interfaz/textos.py" line="663"/>
        <source>La tarea sigue en marcha en Proxmox, no sabemos si terminó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="288"/>
        <source>Proxmox no entendió el valor de {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="299"/>
        <source>Proxmox rechazó el valor de {campo}: {mensaje}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="305"/>
        <source>El formulario tiene datos que hay que corregir antes de crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="309"/>
        <source>Proxmox rechazó el valor de {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="312"/>
        <source>ProxLaunch requiere Proxmox VE {minima} o superior (el servidor tiene {version})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="322"/>
        <source>Proxmox dijo que la tarea terminó, pero la máquina {vmid} no aparece en el nodo {nodo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="332"/>
        <source>«{recurso}» ya no existe en el nodo. Actualiza y elige de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="338"/>
        <source>Ese elemento ya no existe. Actualiza y elige de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="342"/>
        <source>Proxmox no devolvió el identificador de la tarea</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="346"/>
        <location filename="../../interfaz/textos.py" line="600"/>
        <source>No hay un llavero disponible en este equipo; las credenciales no se guardarán</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="351"/>
        <source>Proxmox devolvió una respuesta demasiado grande y se descartó por seguridad. Comprueba que la dirección apunta a un servidor Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="374"/>
        <source>No se pudo contactar con ninguno de los servidores del perfil:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="385"/>
        <source>No se pudo contactar con el servidor ({destino})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="390"/>
        <source>El servidor no responde</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="395"/>
        <source>no respondió a tiempo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="397"/>
        <source>conexión rechazada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="398"/>
        <source>no respondió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="443"/>
        <source>El nombre solo puede tener letras sin acentos, números y guiones, y no puede empezar ni terminar con guion.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="449"/>
        <source>El número de máquina debe estar entre 100 y 999999999.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="458"/>
        <source>Elige entre 1 y 4 sockets.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="459"/>
        <source>Elige entre 1 y 128 núcleos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="462"/>
        <source>La memoria mínima no puede superar a la memoria total.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="465"/>
        <source>La memoria debe ser de al menos 16 MiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="469"/>
        <source>Ese tipo de conexión admite como máximo {maximo} discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="474"/>
        <source>Elige un tipo de conexión de disco válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="476"/>
        <source>El tamaño debe ser un número entero de GiB, mínimo 1.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="480"/>
        <source>Este almacenamiento solo admite formato raw.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="482"/>
        <source>El controlador de discos no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="484"/>
        <source>IO Thread necesita el bus VirtIO o SCSI con controlador virtio-scsi-single.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="488"/>
        <source>La emulación SSD no está disponible en el bus VirtIO.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="492"/>
        <source>Este tipo de conexión no admite liberar el espacio sin usar (discard).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="497"/>
        <source>El disco pide {pedido_gib} GiB y «{storage}» solo tiene {libre_gib} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="505"/>
        <source>Los discos piden {pedido_gib} GiB y «{storage}» tiene {libre_gib} GiB libres. Este almacenamiento solo ocupa el espacio a medida que se usa, así que puedes continuar, pero conviene vigilar el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="514"/>
        <source>La VLAN debe estar entre 1 y 4094.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="516"/>
        <source>El nodo no tiene redes (bridges) disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="520"/>
        <source>La red «{bridge}» no existe en el nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="525"/>
        <source>El modelo de tarjeta de red no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="528"/>
        <source>UEFI necesita un almacenamiento para guardar su configuración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="531"/>
        <source>Ese almacenamiento no está disponible en el nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="535"/>
        <source>El token debe tener el formato usuario@realm!nombre=secreto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="539"/>
        <source>Escribe solo el nombre o la IP del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="541"/>
        <source>El origen del sistema no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="543"/>
        <source>Agrega al menos un disco o marca «Sin disco».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="545"/>
        <source>El tipo de CPU no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="547"/>
        <source>Una máquina admite como máximo 32 interfaces de red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="551"/>
        <source>El código tiene 6 números.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="587"/>
        <source>{privilegio} en {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="606"/>
        <source>Topología desconocida ({nodos} nodos): a tu usuario le falta el permiso Sys.Audit en «/» para ver el clúster. Puedes seguir trabajando.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="615"/>
        <location filename="../../interfaz/textos.py" line="1389"/>
        <source>Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="621"/>
        <source>A tu usuario le faltan permisos recomendados ({privilegios}). Algunas acciones podrían fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="630"/>
        <source>Este servidor tiene Proxmox VE {version}, más nuevo que la última versión que ProxLaunch ha probado. Puedes continuar, pero algo podría no funcionar como se espera.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="649"/>
        <source>Máquina {nombre} ({vmid}) creada en {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="655"/>
        <source>Creada con avisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="667"/>
        <source>Se perdió la conexión mientras se creaba la máquina; la tarea puede haber terminado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="677"/>
        <source>La máquina quedó parcialmente creada; elimínala desde Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="682"/>
        <source>Cancelado. La tarea pudo seguir en Proxmox; revisa si la máquina existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="686"/>
        <source>Cancelado. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="693"/>
        <location filename="../../interfaz/textos.py" line="965"/>
        <source>Validando datos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="695"/>
        <location filename="../../interfaz/textos.py" line="966"/>
        <source>Enviando a Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="697"/>
        <location filename="../../interfaz/textos.py" line="967"/>
        <source>Creando la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="699"/>
        <location filename="../../interfaz/textos.py" line="968"/>
        <source>Comprobando el resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="701"/>
        <location filename="../../interfaz/textos.py" line="969"/>
        <source>Ajustando la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="705"/>
        <source>Listo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="712"/>
        <source>es el único con espacio suficiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="714"/>
        <source>más memoria y espacio libres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="716"/>
        <source>misma memoria libre; se eligió el que tiene más espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="725"/>
        <source>Servidor nuevo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="727"/>
        <source>Certificado conocido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="729"/>
        <source>El certificado cambió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="730"/>
        <source>Sin verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="739"/>
        <source>Se perdió la conexión. Hay 1 máquina sin confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="742"/>
        <source>Se perdió la conexión. Hay %n máquinas sin confirmar.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="764"/>
        <source>El número {vmid} lo usó otra persona mientras tanto. Esta máquina no se creó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="778"/>
        <source>cancelaste el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="780"/>
        <source>el lote se detuvo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="782"/>
        <source>hubo un error que afectaba a todo el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="784"/>
        <source>el nodo no respondió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="785"/>
        <source>no se llegó a enviar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="793"/>
        <source>Ningún servidor puede alojar esta máquina. Revisa que el almacenamiento y la red existan en los nodos elegidos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="800"/>
        <source>No encontré {n} números de máquina libres a partir del {inicio}. Prueba con otro número inicial o con menos máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="806"/>
        <source>número inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="810"/>
        <source>Las máquinas necesitan {pedido} GiB en «{storage}» y solo hay {libre} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="819"/>
        <location filename="../../interfaz/textos.py" line="1203"/>
        <source>Caben {max}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="823"/>
        <source>No sabemos si «{nombre}» se creó. No se volverá a enviar: pulsa «Comprobar» para verlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="832"/>
        <source>No pudimos comprobar si «{nombre}» existe. Revisa la conexión y vuelve a comprobar antes de crearla otra vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="841"/>
        <source>Fallaron {n} máquinas seguidas por la misma causa: {causa} ¿Continuar o detener?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="848"/>
        <source>una causa desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="854"/>
        <source>Se perdió la conexión. Hay máquinas sin confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="860"/>
        <source>«{nombre}» no se envió ({motivo}). No existe en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="868"/>
        <source>Los datos del servidor cambiaron: {diferencia}. Revisa el resumen y confirma otra vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="874"/>
        <source>hay cambios</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="877"/>
        <source>Hay un lote en curso. Espera a que termine o cancélalo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="882"/>
        <location filename="../../interfaz/textos.py" line="1264"/>
        <source>Elige entre 1 y {max} máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="888"/>
        <source>Has forzado una versión más nueva que la del servidor ({detectada}); solo puedes simular.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="894"/>
        <source>otra</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="897"/>
        <source>Proxmox no aceptó la etiqueta de la máquina. No se creó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="901"/>
        <source>No se pudo eliminar «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="904"/>
        <source>Elimínala desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="907"/>
        <source>No eliminamos «{nombre}» porque no podemos asegurar que la creó este lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="915"/>
        <source>«{nombre}» está encendida. Apágala en Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="922"/>
        <source>«{nombre}» está bloqueada por una tarea de Proxmox. Espera a que termine.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="930"/>
        <source>Pueden haber quedado discos sueltos de «{nombre}»; revísalos en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="938"/>
        <source>No sabemos si se eliminó «{nombre}». Comprueba antes de reintentar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="945"/>
        <source>Error interno: se intentó escribir en modo simulación. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="953"/>
        <source>La máquina existe en Proxmox, pero no pudimos confirmar que la creó ProxLaunch: podría ser de otra persona con el mismo número. Verifícalo en Proxmox antes de hacer nada con ella. No se eliminará desde aquí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="964"/>
        <location filename="../../interfaz/textos.py" line="1014"/>
        <source>Pendiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="970"/>
        <source>Lista</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="971"/>
        <source>Lista, con avisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="972"/>
        <location filename="../../interfaz/textos.py" line="2122"/>
        <source>Con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="973"/>
        <source>Quedó a medias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="974"/>
        <source>Sin confirmar (sigue en Proxmox)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="977"/>
        <source>No sabemos si se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="978"/>
        <source>No enviada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="979"/>
        <source>No se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="980"/>
        <source>Existe, sin confirmar de quién es</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1015"/>
        <source>Comprobando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1016"/>
        <source>Eliminando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1017"/>
        <source>Eliminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1018"/>
        <source>Ya no existía</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1019"/>
        <source>No se pudo eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1020"/>
        <source>No se tocó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1021"/>
        <source>No sabemos si se eliminó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1022"/>
        <source>No se procesó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1047"/>
        <source>es el único nodo disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1049"/>
        <source>lo elegiste tú</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1051"/>
        <source>Equilibrado: más memoria libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1053"/>
        <source>Equilibrado: más espacio libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1055"/>
        <source>Por turnos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1062"/>
        <source>El lote se detuvo por un problema general</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1064"/>
        <source>El lote se detuvo: el mismo error se repite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1065"/>
        <source>El lote se detuvo: se perdió la conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1071"/>
        <location filename="../../interfaz/textos.py" line="1102"/>
        <source>No se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1073"/>
        <source>No se envió: no existe en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1075"/>
        <source>No se creó: no hay nada que eliminar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1077"/>
        <source>Se encontró tras una comprobación, sin etiqueta que la ate a este lote: no podemos asegurar que sea suya.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1083"/>
        <source>Falló y no se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1085"/>
        <source>Existe, pero no podemos asegurar que la creó este lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1094"/>
        <source>No sabemos si se creó: comprueba primero qué pasó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1099"/>
        <source>esta máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1128"/>
        <source>tiene el carácter «{caracter}», que no se admite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1135"/>
        <source>es demasiado largo (cada parte puede tener hasta 63 caracteres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1138"/>
        <source>no puede empezar ni terminar con guion o punto, ni tener partes vacías</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1148"/>
        <source>El número inicial debe estar entre 0 y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1156"/>
        <source>La numeración llegaría a {ultimo} y el máximo es {maximo}. Baja el número inicial o la cantidad.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1167"/>
        <source>El relleno debe estar entre 0 y {maximo} dígitos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1174"/>
        <source>El nombre «{nombre}» no es válido: {causa}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1183"/>
        <source>«{storage}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1185"/>
        <source>«{storage}» (compartido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1188"/>
        <source>«{storage}» del nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1193"/>
        <source>Las {n} máquinas necesitan {pedido} GiB en {lugar} y solo hay {libre} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1210"/>
        <source>«{nodo}» está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1213"/>
        <source>«{nodo}» no tiene el almacenamiento «{storage}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1220"/>
        <source>«{nodo}» no tiene un almacenamiento para la configuración de UEFI.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1227"/>
        <source>«{nodo}» no tiene la red «{bridge}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1234"/>
        <source>«{nodo}» no puede alojar esta configuración.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1242"/>
        <source>Fila {n}: {texto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1256"/>
        <source>El máximo por lote es {max} máquinas. Divide el trabajo en varios lotes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1270"/>
        <source>Escribe un prefijo para los nombres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1271"/>
        <source>El prefijo solo puede tener letras sin acentos, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1275"/>
        <source>Elige un guion o ningún separador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1279"/>
        <source>Los nombres del lote no pueden repetirse.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1282"/>
        <source>Ya existe una máquina llamada «{nombre}» (número {vmid}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1290"/>
        <source>El lote llegaría hasta el número {ultimo} y el máximo es {maximo}. Baja el número inicial o la cantidad.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1299"/>
        <source>El número inicial debe estar entre {minimo} y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1307"/>
        <source>No hay {n} números de máquina libres a partir del {inicio}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1317"/>
        <source>Estás pidiendo {pedido} GiB y en «{storage}» solo hay {libre} GiB libres: es más de {factor} veces lo que hay. Reduce las máquinas o el tamaño de los discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1329"/>
        <source>Estás pidiendo {pedido} GiB y solo hay {libre} GiB libres en «{storage}». Funciona mientras las máquinas no usen todo su disco; si se llena, todas las máquinas de ese almacenamiento pueden fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1347"/>
        <source>Cada máquina pide {vcpus} procesadores virtuales y «{nodo}» tiene {cpus_nodo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1356"/>
        <source>No se pudo leer la memoria libre de {nodos}; el reparto usa el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1366"/>
        <source>No se pudo leer la memoria libre de «{nodo}»; el reparto usa el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1373"/>
        <source>En «{nodo}» pides {pedido} GiB de memoria y hay {libre} GiB libres. Las máquinas se crean apagadas; el problema aparecerá al encenderlas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1383"/>
        <source>Elige al menos un nodo disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1385"/>
        <source>Se actualizaron los datos del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1397"/>
        <source>Proxmox no admite esa etiqueta: usa solo letras, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1404"/>
        <source>{texto} (afecta a {n} filas)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1410"/>
        <source>Máquina {n}: {texto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1420"/>
        <source>Ningún nodo tiene sitio para todas las máquinas con el espacio libre actual.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1435"/>
        <location filename="../../interfaz/textos.py" line="2354"/>
        <source> y </source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1445"/>
        <source>{n} MiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1447"/>
        <source>{n} KiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1448"/>
        <source>{n} bytes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1454"/>
        <source>Falta la columna «nombre».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1457"/>
        <source>Columnas reconocidas: {reconocidas}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1462"/>
        <source>La columna «{columna}» aparece dos veces.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1465"/>
        <source>Hay datos en columnas que no tienen encabezado (columnas {posiciones}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1474"/>
        <source>El archivo no existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1476"/>
        <source>No tienes permiso para leer ese archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1487"/>
        <source>El archivo tiene demasiadas columnas; el máximo es {max}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1493"/>
        <source>El archivo tiene %n columnas; el máximo es {max}.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1500"/>
        <source>Una celda tiene demasiado texto; el máximo es {max} caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1506"/>
        <source>(fila {fila})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1510"/>
        <source>El archivo tiene demasiadas filas; el máximo por lote es {max}. Divide el archivo en partes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1518"/>
        <source>El archivo tiene %n filas; el máximo por lote es {max}. Divide el archivo en partes.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1532"/>
        <source>tipo de CPU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1534"/>
        <source>almacenamiento del disco EFI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1536"/>
        <source>almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1538"/>
        <source>puente de red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1540"/>
        <location filename="../../interfaz/textos.py" line="1550"/>
        <source>nombre de la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1542"/>
        <source>nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1544"/>
        <source>prefijo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1546"/>
        <source>separador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1548"/>
        <source>nodos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1552"/>
        <source>versión de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1554"/>
        <source>descripción</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1556"/>
        <source>almacenamiento preferido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1558"/>
        <source>puente de red preferido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1560"/>
        <source>almacenamiento EFI preferido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1562"/>
        <source>nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1571"/>
        <source>No se guardó: el campo «{campo}» parece contener una credencial (usuario@realm!token). Bórrala y vuelve a guardar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1578"/>
        <source>No se guardó: el nombre de un archivo, almacenamiento o plantilla tiene caracteres que no se pueden guardar. Usa solo letras sin acentos, números, punto, guion y guion bajo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1585"/>
        <source>no hay espacio en el disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1587"/>
        <source>no tienes permiso para escribir ahí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1589"/>
        <source>el archivo está abierto en otro programa</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1591"/>
        <source>la ruta es demasiado larga</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1593"/>
        <source>ocurrió un error al escribir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1594"/>
        <source>No se pudo guardar el archivo: {motivo}. No se cambió nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1606"/>
        <source>no es un archivo normal</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1607"/>
        <source>No se puede abrir este archivo: {motivo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1611"/>
        <source>No se puede abrir este archivo: está vacío.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1616"/>
        <source>No se puede abrir este archivo: tiene demasiados elementos (máximo {limite}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1622"/>
        <source>No se puede abrir este archivo: es demasiado grande (límite {limite}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1626"/>
        <source>Este archivo no es un archivo de ProxLaunch del tipo que buscas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1631"/>
        <source>Parece un archivo de perfiles de máquina; usa «Importar perfiles» (menú Perfiles › Administrar perfiles… › Importar…).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1637"/>
        <source>Parece un archivo de lote guardado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1642"/>
        <source>Este archivo lo creó una versión más nueva de ProxLaunch. Actualiza la aplicación para abrirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1651"/>
        <source>El archivo está dañado o tiene datos no válidos: {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1656"/>
        <source>El archivo está dañado o no tiene un formato válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1660"/>
        <source>No se pudo leer el archivo. Si está abierto en otro programa (como Excel), ciérralo o guarda una copia.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1672"/>
        <source>Hay unas comillas sin cerrar en la fila {fila}. Revisa el archivo o guárdalo de nuevo como «CSV UTF-8» desde Excel.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1680"/>
        <source>No pude leer el archivo CSV (fila {fila}). Guárdalo como «CSV UTF-8» desde Excel.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1689"/>
        <source>El archivo no tiene máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1694"/>
        <source>el valor «{valor}» no es válido. Ejemplo: {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1701"/>
        <location filename="../../interfaz/textos.py" line="2273"/>
        <source>Fila {fila}, columna «{columna}»: {detalle}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1706"/>
        <source>No existe el perfil «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1709"/>
        <source>Perfiles disponibles: {disponibles}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1713"/>
        <source>Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1718"/>
        <source>Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1736"/>
        <source>Este lote no encaja en este servidor: {detalle}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1747"/>
        <source>El perfil pedía la red «{pedido}», que no existe en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1751"/>
        <source>El perfil pedía el almacenamiento de UEFI «{pedido}», que no existe en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1756"/>
        <source>El perfil recordaba «{pedido}» como origen del sistema, pero no está en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1761"/>
        <source>El perfil pedía el almacenamiento «{pedido}», que no existe en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1766"/>
        <source>Se usó «{usado}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1770"/>
        <source>Elige uno antes de crear.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1780"/>
        <location filename="../../interfaz/textos.py" line="2042"/>
        <source>Escribe un nombre de 1 a {maximo} caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1785"/>
        <source>Ya existe un perfil con ese nombre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1788"/>
        <source>Llegaste al máximo de {max} perfiles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1795"/>
        <source>La descripción no es válida: máximo {maximo} caracteres y sin caracteres de control.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1803"/>
        <source>El texto no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1805"/>
        <location filename="../../interfaz/textos.py" line="2060"/>
        <source>Parece un token de acceso. No lo escribas aquí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1809"/>
        <location filename="../../interfaz/textos.py" line="2204"/>
        <source>Falta el nombre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1814"/>
        <source>Las filas {filas} tienen el mismo número de máquina «{vmid}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1821"/>
        <source>Las filas {filas} tienen el mismo nombre «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1829"/>
        <source>Este perfil requiere Proxmox {version} o superior.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1835"/>
        <source>El tipo de CPU «host» impide mover la máquina entre nodos con procesadores distintos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1955"/>
        <source>falta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1956"/>
        <source>tipo de dato incorrecto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1957"/>
        <source>fuera de rango</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1958"/>
        <source>longitud no válida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1959"/>
        <source>valor no admitido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1960"/>
        <source>texto no válido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1963"/>
        <source>parece un token de acceso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1966"/>
        <source>hay demasiados</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1967"/>
        <source>está repetido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1985"/>
        <source>Se ignoró 1 campo que ProxLaunch no conoce.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1988"/>
        <source>Se ignoraron %n campos que ProxLaunch no conoce.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1992"/>
        <source>El archivo traía datos que parecen una credencial. No se usaron. Si eran reales, cámbialas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1998"/>
        <source>El archivo era de la versión {desde} del formato y se convirtió a la {hasta}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2003"/>
        <source>Este CSV contiene contraseñas en texto claro. Bórralo cuando termines; ProxLaunch no las guarda.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2009"/>
        <source>Este lote usaba una contraseña de cloud-init y no se guardó. Vuelve a escribirla antes de crear las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2015"/>
        <source>La columna «{columna}» no se usa y se ignoró.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2019"/>
        <source>En la columna «{columna}» había números sin unidad: se entendieron como GiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2024"/>
        <source>En la columna «{columna}» se usó la coma como separador decimal.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2027"/>
        <source>En la columna «{columna}», «GB» se tomó como GiB (1 GB = 1024 MiB).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2046"/>
        <source>Ya existe un perfil con ese nombre. Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2050"/>
        <source>El identificador del perfil no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2052"/>
        <source>Llegaste al máximo de {maximo} perfiles. Elimina alguno para crear otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2056"/>
        <source>El texto de «{campo}» no es válido. No uses caracteres especiales.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="2080"/>
        <source>y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2089"/>
        <source>1 núcleo</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="2091"/>
        <source>%n núcleos</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2095"/>
        <source>sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2097"/>
        <source>1 disco de {gib} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="2101"/>
        <source>%n discos</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2103"/>
        <source> ({gib} GiB en total)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2119"/>
        <source>Correcta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2121"/>
        <source>Con aviso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2133"/>
        <source>«{valor}» mezcla punto y coma. Escribe el número sin separador de miles, por ejemplo 1000.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2138"/>
        <source>¿Quisiste decir mil o uno? Escribe {mil} o {uno}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2147"/>
        <source>El texto de «{columna}» no es válido. No uses caracteres especiales.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2152"/>
        <source>El texto de «{columna}» parece un token de acceso y no se usa. Quítalo de la celda.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2157"/>
        <source>El texto de «{columna}» es demasiado largo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2161"/>
        <source>Indicaste un almacenamiento, pero la fila no tiene disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2165"/>
        <source>Indicaste un almacenamiento, pero falta el tamaño de ese disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2168"/>
        <source>«{valor}» no es un valor válido. Valores válidos: {validos}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2195"/>
        <source>Hay más de un perfil llamado «{nombre}». Escribe el nombre exacto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2199"/>
        <source>No existe el perfil «{nombre}». Perfiles disponibles: {disponibles}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2208"/>
        <source>Pides {gib} GiB de memoria. ¿Querías MiB?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2213"/>
        <source>Las filas {filas} tienen el mismo número de máquina «{valor}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2216"/>
        <source>Las filas {filas} tienen el mismo nombre «{valor}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2220"/>
        <source>Parece una fila de ejemplo de la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2222"/>
        <source>«{valor}» no es un número. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2226"/>
        <source>«{valor}» no es un número entero. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2230"/>
        <source>«{valor}» no da una cantidad entera de MiB. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2235"/>
        <source>«{valor}» no da una cantidad entera de GiB. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2240"/>
        <source>«{unidad}» no es una unidad válida. Usa {validas}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2252"/>
        <source>Ningún nodo del servidor puede alojar esta máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2257"/>
        <source>El nodo no existe en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2259"/>
        <source>El nodo está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2276"/>
        <source>Fila {fila}: {detalle}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2294"/>
        <source>El almacenamiento «{valor}» no existe en este servidor o no admite discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2298"/>
        <source>El almacenamiento «{valor}» para la configuración UEFI no existe en este servidor o no admite discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2304"/>
        <source>La red «{valor}» no existe en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2308"/>
        <source>El ISO «{valor}» no está en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2312"/>
        <source>El CD de drivers «{valor}» no está en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2316"/>
        <source>La imagen de disco «{valor}» no está en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2320"/>
        <source>La plantilla «{valor}» no existe en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2323"/>
        <source>El nodo «{valor}» no existe o está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2346"/>
        <source>(dirección web)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2366"/>
        <source>bytes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2389"/>
        <source>{s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2391"/>
        <source>{m} min {s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2394"/>
        <source>{h} h {m} min</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2403"/>
        <source>imágenes ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2405"/>
        <source>imágenes de disco para importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2407"/>
        <source>discos de máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2408"/>
        <source>ese tipo de archivos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2414"/>
        <source>Instalar desde un ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2416"/>
        <source>Importar un disco existente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2418"/>
        <source>Clonar una plantilla de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2419"/>
        <source>Disco vacío (sin sistema)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2425"/>
        <source>ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2427"/>
        <source>Disco importado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2429"/>
        <source>Clon</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2430"/>
        <source>Disco vacío</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2436"/>
        <source>Linux</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2438"/>
        <source>Windows 11</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2440"/>
        <source>Windows Server 2022 / 2025</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2442"/>
        <source>Windows 10</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2444"/>
        <source>Windows Server 2016 / 2019</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2445"/>
        <source>Otro sistema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2452"/>
        <source>Enlazado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2454"/>
        <source>Completo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2455"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2457"/>
        <source>Copia independiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2459"/>
        <source>Rápido y ligero</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2460"/>
        <source>Rápido y ligero (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2464"/>
        <source>usar un ISO del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2465"/>
        <source>subir un ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2466"/>
        <source>descargar un ISO desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2469"/>
        <source>importar un disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2470"/>
        <source>subir una imagen de disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2471"/>
        <source>descargar una imagen de disco desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2474"/>
        <source>clonar la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2475"/>
        <source>fijar el orden de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2476"/>
        <location filename="../../interfaz/textos.py" line="2478"/>
        <location filename="../../interfaz/textos.py" line="2842"/>
        <source>ampliar el disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2477"/>
        <source>ajustar la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2487"/>
        <source>hacer esta acción</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2493"/>
        <source>Usar un ISO del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2494"/>
        <source>Subir un ISO desde tu equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2495"/>
        <source>Descargar un ISO desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2498"/>
        <source>Importar un disco del servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2499"/>
        <source>Subir una imagen de disco desde tu equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2502"/>
        <source>Descargar una imagen de disco desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2505"/>
        <source>Clonar una plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2506"/>
        <source>Fijar el orden de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2509"/>
        <source>Ampliar el disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2518"/>
        <source>Disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2520"/>
        <source>Disponible, sin poder confirmar tus permisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2521"/>
        <source>No disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2531"/>
        <source>Disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2533"/>
        <source>No pudimos comprobar tus permisos. Puedes intentarlo; si falta alguno, ProxLaunch te dirá cuál.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2541"/>
        <source>Ningún almacenamiento de este servidor guarda imágenes ISO. Pide a tu administrador que active el contenido «ISO» en uno.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2546"/>
        <location filename="../../interfaz/textos.py" line="4316"/>
        <source>No disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2552"/>
        <source>Es el único almacenamiento que sirve</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2554"/>
        <source>El que usaste la vez anterior</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2556"/>
        <source>Hay que elegir uno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2558"/>
        <source>El que usabas ya no está disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2559"/>
        <source>Ningún almacenamiento sirve</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2572"/>
        <source>Ningún almacenamiento activo de este servidor guarda {contenido}. Pide a tu administrador que lo active en uno.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2578"/>
        <source>Elige el almacenamiento donde guardar {contenido}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2844"/>
        <source>configurar el arranque con el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2846"/>
        <source>activar la protección contra borrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2848"/>
        <source>aplicar la configuración inicial (cloud-init)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2850"/>
        <source>poner la contraseña de cloud-init</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2863"/>
        <source>el arranque con el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2865"/>
        <source>la protección contra borrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2867"/>
        <source>la configuración inicial (cloud-init)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2869"/>
        <source>la contraseña de cloud-init</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2938"/>
        <source>{n} núcleos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2940"/>
        <source>{n} sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3035"/>
        <source>la IP de la tarjeta de red {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3038"/>
        <source>la puerta de enlace de la tarjeta de red {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3042"/>
        <source>el script de configuración «{tipo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3046"/>
        <source>el usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3047"/>
        <source>las claves SSH</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3048"/>
        <source>los servidores DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3049"/>
        <source>el dominio de búsqueda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3050"/>
        <source>la opción de actualizar paquetes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3053"/>
        <source>la contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3059"/>
        <source>un valor de la configuración inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3064"/>
        <source>No se envió a Proxmox: {que} de la configuración inicial (cloud-init) no es válido. Corrígelo en esa sección y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3074"/>
        <source>Proxmox no aceptó el nombre del archivo. Usa solo letras sin acentos, números, punto, guion y guion bajo, con la extensión correcta (iso, qcow2, raw o vmdk). Una imagen de disco debe terminar en .qcow2, .raw, .vmdk u .ova; si es un .img, renómbralo a .qcow2.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3808"/>
        <location filename="../../interfaz/textos.py" line="4378"/>
        <source>Encender al terminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3809"/>
        <location filename="../../interfaz/textos.py" line="4382"/>
        <source>Arrancar con el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3810"/>
        <source>Orden y espera de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3813"/>
        <location filename="../../interfaz/textos.py" line="4375"/>
        <source>Notas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3814"/>
        <location filename="../../interfaz/textos.py" line="4386"/>
        <source>Etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3815"/>
        <location filename="../../interfaz/textos.py" line="4389"/>
        <source>Pool</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3816"/>
        <source>MTU de la red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3817"/>
        <source>Límite de velocidad de red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3818"/>
        <location filename="../../interfaz/textos.py" line="4410"/>
        <source>Proteger contra borrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3820"/>
        <source>Configuración inicial (cloud-init)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3823"/>
        <source>Contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3824"/>
        <source>DNS y dominio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3825"/>
        <source>Scripts de configuración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3826"/>
        <location filename="../../interfaz/textos.py" line="5140"/>
        <source>Esperar la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3827"/>
        <location filename="../../interfaz/textos.py" line="5131"/>
        <source>Activar el agente invitado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4473"/>
        <source>Datos de usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4475"/>
        <source>Datos del proveedor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4477"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4479"/>
        <source>Metadatos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4489"/>
        <source>«{opcion}»: tu usuario no tiene el privilegio {privilegio} en «{ruta}», pero sí VM.Config.Network. En tu versión de Proxmox puede que lo rechace; si falla, pídele el privilegio a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4500"/>
        <source>«{opcion}»: tu usuario no tiene el privilegio {privilegio} en «{ruta}». En tu versión de Proxmox puede hacer falta (no está verificado): si Proxmox rechaza el script, pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4511"/>
        <source>«{opcion}» no está disponible: tu usuario no tiene el privilegio {privilegio} (ni {alternativo}, que en tu versión también vale) en «{ruta}». Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4521"/>
        <source>«{opcion}» no está disponible: tu usuario no tiene el privilegio {privilegio} en «{ruta}». Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4534"/>
        <source>No se pudo leer la configuración de la plantilla, así que no se sabe si tiene unidad cloud-init. Puedes rellenar la sección, pero si la plantilla no la tiene Proxmox no entregará estos datos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4541"/>
        <source>Con Windows, Proxmox guardaría la contraseña sin cifrar; no se permite.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4546"/>
        <source>Pide al administrador que active el contenido «Fragmentos» (snippets) en un almacenamiento de archivos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4552"/>
        <source>La plantilla ya tiene el agente invitado activado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4568"/>
        <source>La plantilla «{plantilla}» no tiene unidad cloud-init, así que Proxmox no podría entregar estos datos a la máquina. Usa una plantilla creada con «Crear plantilla desde imagen cloud» o añade una unidad «CloudInit Drive» a la plantilla en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4577"/>
        <source>Esta plantilla no tiene unidad cloud-init, así que Proxmox no podría entregar estos datos a la máquina. Usa una plantilla creada con «Crear plantilla desde imagen cloud» o añade una unidad «CloudInit Drive» a la plantilla en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4584"/>
        <source>Proxmox rechazó una de las claves SSH. Revisa que sean claves públicas completas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4591"/>
        <source>Proxmox no encuentra el script «{snippet}». Revisa que exista en el almacenamiento del nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4598"/>
        <source>Proxmox no encuentra uno de los scripts de configuración. Revisa que exista en el almacenamiento del nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4604"/>
        <source>La contraseña de cloud-init ya no está en memoria (por seguridad no se guarda). Vuelve a escribirla y reintenta los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4612"/>
        <source>Ese archivo es demasiado grande para ser una clave pública (máximo 64 KiB).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4617"/>
        <source>Ese archivo no es de texto. Elige el archivo de la clave pública (el que termina en .pub).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4622"/>
        <source>No se pudo leer ese archivo. Revisa que exista y que puedas abrirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4634"/>
        <source>Se creó, pero falta aplicar la configuración inicial (cloud-init). Puedes reintentar los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4640"/>
        <source>Se creó y la configuración inicial se aplicó, pero falta poner la contraseña. Puedes reintentar los ajustes (si ya no está en memoria, tendrás que escribirla de nuevo).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4654"/>
        <source>no empieza por un tipo de clave conocido (ssh-ed25519, ssh-rsa…)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4658"/>
        <source>falta el cuerpo de la clave</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4660"/>
        <source>el cuerpo de la clave no es válido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4662"/>
        <source>no puede llevar opciones por delante (command=…, from=…)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4665"/>
        <source>no es una clave pública válida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4670"/>
        <source>falta la máscara (por ejemplo 192.168.1.50/24)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4674"/>
        <source>la máscara debe estar entre /8 y /30</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4676"/>
        <source>cada número de la dirección debe estar entre 0 y 255</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4680"/>
        <source>no uses ceros a la izquierda (010.0.0.1 es ambiguo)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4684"/>
        <source>es una dirección reservada (0.0.0.0, loopback, multicast o link-local)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4688"/>
        <source>no está en la misma red que la IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4690"/>
        <source>es la misma que la IP de la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4692"/>
        <location filename="../../interfaz/textos.py" line="4724"/>
        <source>es la dirección de red o de difusión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4693"/>
        <source>no es una dirección IPv4</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4699"/>
        <source>Las dos contraseñas no coinciden.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4701"/>
        <source>La contraseña no puede tener saltos de línea ni caracteres de control.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4705"/>
        <source>La contraseña no puede superar los 128 caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4709"/>
        <source>La contraseña debe tener al menos 8 caracteres. Con menos, Proxmox la acepta pero es fácil de adivinar, así que no se admite.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4720"/>
        <source>se sale de la red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4722"/>
        <source>es la puerta de enlace</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4726"/>
        <source>La serie de IP de la tarjeta {n} no cabe: «{nombre}» recibiría {direccion}, que {causa}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4737"/>
        <source>Afecta a {afectadas} máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4746"/>
        <source>No se pudo leer la configuración de la plantilla «{plantilla}», así que no se sabe si tiene unidad cloud-init. Si no la tiene, Proxmox no entregará estos datos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4757"/>
        <source>Afecta a {n} máquinas del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4767"/>
        <source>La tarjeta de red {n} no existe: una máquina tiene hasta 32.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4771"/>
        <source>La tarjeta de red {n} está repetida.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4774"/>
        <source>La plantilla no tiene la tarjeta de red {n}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4783"/>
        <source>El nodo «{nodo}» no tiene ningún almacenamiento con el contenido «Fragmentos» (snippets). Pide al administrador que lo active.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4793"/>
        <source>El almacenamiento del script «{snippet}» no existe en el nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4800"/>
        <source>El script «{snippet}» no existe en el nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4807"/>
        <source>Los scripts elegidos suman más de 3 MiB, el máximo que admite Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4811"/>
        <source>El script «{snippet}» pesa más de 1 MiB, el máximo que admite Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4817"/>
        <source>Con «Datos de usuario» elegido, el usuario, las claves y la contraseña de arriba se ignoran: ese script sustituye a los datos que genera Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4823"/>
        <source>El identificador del script «{tipo}» no es válido: usa almacén:snippets/archivo, sin espacios, comas ni «..».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4830"/>
        <source>La plantilla «{plantilla}» ya tiene scripts que ProxLaunch no sabe interpretar: solo se puede dejar «Como la plantilla».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4843"/>
        <source>La IP solo se puede conocer con la máquina encendida: marca «Encender al terminar».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4849"/>
        <source>El plazo debe ser un número entero de segundos entre {minimo} y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4857"/>
        <source>La plantilla no tiene activado el agente invitado, así que no se podrá saber la IP. Marca «Activar el agente invitado» en la configuración inicial y asegúrate de que el programa esté instalado dentro de la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4863"/>
        <source>La máquina no tiene activado el agente invitado (casilla «Agente de QEMU»), así que no se podrá saber la IP.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4871"/>
        <source>Las imágenes de Ubuntu y Debian no traen el agente invitado instalado: sin él no se podrá saber la IP. Las de Rocky y Alma sí lo traen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4878"/>
        <source>Con las actualizaciones activadas, el primer arranque puede tardar más que el plazo de {plazo_s} s. Sube el plazo o desactiva «Actualizar paquetes».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4909"/>
        <source>El usuario no sigue el patrón habitual (minúsculas, números, «_» y «-», hasta 32 caracteres). Proxmox lo acepta, pero cloud-init podría rechazarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4914"/>
        <source>El usuario no puede tener espacios, «:» ni caracteres de control.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4918"/>
        <source>La línea {linea} de las claves SSH no es una clave pública válida: {motivo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4922"/>
        <source>Eso parece una clave privada. Nunca la pegues aquí: usa solo la clave pública (el archivo que termina en .pub).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4931"/>
        <source>Se descartaron {cantidad} claves repetidas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4935"/>
        <source>Las claves SSH ocupan demasiado (máximo 8 KiB en total).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4938"/>
        <source>Hay demasiadas claves SSH (máximo 20).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4942"/>
        <source>La IP de la tarjeta de red {n} no es válida: {motivo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4946"/>
        <source>La IP de la tarjeta de red {n} es la dirección de red o de difusión de su red: elige otra.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4952"/>
        <source>La puerta de enlace de la tarjeta de red {n} no es válida: {motivo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4956"/>
        <source>La puerta de enlace de la tarjeta de red {n} solo vale con IP fija.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4963"/>
        <source>La IP {direccion} se repite: la usan «{con}» y «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4971"/>
        <source>Has puesto {cantidad} servidores DNS; lo habitual es usar hasta tres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4977"/>
        <source>Los DNS no son válidos: escribe direcciones IP (por ejemplo 1.1.1.1 o 8.8.8.8) separadas por espacio o coma.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4983"/>
        <source>El dominio de búsqueda no es válido: usa un nombre como lab.local, sin espacios.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4991"/>
        <source>La plantilla «{plantilla}» es de Windows: cloud-init no está probado con Windows y puede no funcionar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4999"/>
        <source>«Actualizar paquetes» debe ser «Como la plantilla», «Sí» o «No».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5005"/>
        <source>Las {cantidad} máquinas del lote tendrían la misma IP en la tarjeta de red {n}. Marca «Sumar 1 a cada máquina» o usa DHCP.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5011"/>
        <source>La configuración inicial (cloud-init) solo se puede usar al clonar una plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5016"/>
        <source>La contraseña ya no está en memoria; vuelve a escribirla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5038"/>
        <source>1 clave</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5040"/>
        <source>{n} claves</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5050"/>
        <source>DHCP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5051"/>
        <source>IP fija {ip}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5053"/>
        <source>, puerta {puerta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5055"/>
        <source> (sumando 1 a cada máquina)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5062"/>
        <source>ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5072"/>
        <source>DNS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5074"/>
        <source>Dominio de búsqueda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5078"/>
        <source>Actualizar paquetes al arrancar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5087"/>
        <source>Script: {tipo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5108"/>
        <source>Usuario inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5111"/>
        <source>Claves SSH</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5116"/>
        <source>Contraseña inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5117"/>
        <source>definida (oculta)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5124"/>
        <source>Red net{i}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="5141"/>
        <source>sí (plazo {n} s)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3843"/>
        <source>«{opcion}» necesita Proxmox {version} o una versión posterior.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3850"/>
        <source>No puedes ver la lista de pools: falta el privilegio Pool.Audit en «/pool». Eso no significa que no existan pools; pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3856"/>
        <source>No sabemos si puedes ver la lista de pools (privilegio Pool.Audit en «/pool»). Si el pool no existe o no tienes acceso, Proxmox lo rechazará al crear.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3862"/>
        <source>No se pudo leer la lista de pools del servidor. Inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3867"/>
        <source>El pool «{pool}» no existe en Proxmox. No se creó la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3873"/>
        <source>Las notas superan los 8192 caracteres que admite Proxmox. Acórtalas y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3880"/>
        <source>«{nombre}» está protegida contra borrado. Deshacer puede quitarle la protección si lo confirmas expresamente.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3889"/>
        <source>«{nombre}» está encendida y no se pudo apagar: falta el privilegio VM.PowerMgmt. Apágala en Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3897"/>
        <source>También está protegida y falta VM.Config.Options para quitarle la protección.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3904"/>
        <source>«{nombre}» está protegida y no se pudo desproteger: falta el privilegio VM.Config.Options. Quita la protección en Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3913"/>
        <source>No se pudo apagar «{nombre}», así que no se eliminó. Apágala desde Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3922"/>
        <source>No se pudo quitar la protección de «{nombre}», así que no se eliminó. Quítala desde Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3935"/>
        <source>apagada a la fuerza</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3936"/>
        <source>desprotegida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3937"/>
        <source>eliminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3948"/>
        <source>Confirmar Deshacer con apagado o desprotección</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3953"/>
        <source>  • {nombre} (VMID {vmid})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3966"/>
        <source>Se apagarán a la fuerza estas máquinas encendidas. Se perderán los datos que no estén guardados:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3976"/>
        <source>Se quitará la protección contra borrado a estas máquinas:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3983"/>
        <source>Si no se puede quitar la protección de una máquina, no se eliminará y, si estaba encendida, quedará apagada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3991"/>
        <source>Se omitirán porque están encendidas y tu usuario no tiene el privilegio VM.PowerMgmt para apagarlas:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4001"/>
        <source>Se omitirán porque están protegidas y tu usuario no tiene el privilegio VM.Config.Options para quitarles la protección:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4011"/>
        <source>No se pudo comprobar el estado de estas máquinas. Si están encendidas o protegidas se omitirán; si no, se eliminarán:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4020"/>
        <source>Después se eliminarán junto con las demás máquinas que elegiste. Solo se tocan máquinas creadas por este lote; esto no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4026"/>
        <source>El resto de las máquinas que elegiste se eliminará como siempre. Solo se tocan máquinas creadas por este lote; esto no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4036"/>
        <source>Entiendo que se apagarán o desprotegerán máquinas y que puedo perder datos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4042"/>
        <source>Apagar, desproteger y eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4046"/>
        <source>Eliminar sin apagar ni desproteger</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4050"/>
        <source>Si eliges «Eliminar sin apagar ni desproteger», esas máquinas se omiten y se quedan en Proxmox; el resto se elimina como siempre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4058"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4063"/>
        <source>No se pudo comprobar el estado de las máquinas antes de deshacer. No se eliminó nada; inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4071"/>
        <source>Comprobando las máquinas antes de deshacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4082"/>
        <source>Hecho: {acciones}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4097"/>
        <source>Se creó, pero no se pudo encender. Enciéndela desde Proxmox si la necesitas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4102"/>
        <source>No se encendió: quedaron ajustes por aplicar o su creación se confirmó después (al comprobarla). Revisa la máquina y, si hace falta, enciéndela desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4372"/>
        <source>sí, con tu usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4373"/>
        <source>Notas de origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4399"/>
        <source>Orden de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4404"/>
        <source>Espera de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4405"/>
        <source>{n} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4424"/>
        <source>Red {n}: MTU {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4430"/>
        <source>Red {n}: límite {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4441"/>
        <source>MTU {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4443"/>
        <source> (se ignora: no es VirtIO)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4447"/>
        <source>límite {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4108"/>
        <source>No se añadieron las notas de origen: no se pudo leer la descripción de la plantilla y así no se pisan sus notas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4114"/>
        <source>Se creó, pero falta aplicar el arranque con el servidor. Puedes reintentar los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4120"/>
        <source>Se creó, pero falta aplicar la protección contra borrado. Puedes reintentar los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4133"/>
        <source>La etiqueta «{etiqueta}» está registrada en el centro de datos y tu usuario no puede aplicarla (hace falta Sys.Modify en «/»). Pídele a tu administrador que la aplique o que la quite del registro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4143"/>
        <source>El centro de datos no deja a tu usuario poner etiquetas (política «none») y esta máquina llevaría «{etiqueta}». Pídele a tu administrador que la autorice.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4152"/>
        <source>Tu administrador no ha autorizado la etiqueta «{etiqueta}». Pídele que la añada a las etiquetas permitidas del centro de datos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4167"/>
        <source>La espera de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4169"/>
        <source>El orden de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4172"/>
        <source>{campo} debe ser un número entero de 0 o más.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4178"/>
        <source>La etiqueta «{etiqueta}» no es válida: usa minúsculas, números, «_», «-», «+» y «.», sin espacios, y empieza por una letra, un número o «_» (máximo 128 caracteres).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4190"/>
        <source>No se pudieron leer tus permisos, así que quizá Proxmox sí la acepte.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4197"/>
        <source>El MTU de la tarjeta {tarjeta} debe ser «Igual al bridge» o un número entre 576 y 65520.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4206"/>
        <source>El MTU de la tarjeta {tarjeta} solo se aplica a tarjetas VirtIO. Elige VirtIO o deja el MTU en «Heredar del bridge».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4215"/>
        <source>El límite de velocidad de la tarjeta {tarjeta} debe ser un número mayor que 0 y no superior a 1 000 000 000 (en MB/s).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4224"/>
        <source>Las notas ocupan {total} caracteres y Proxmox admite {limite}: sobran {sobran}. Acórtalas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4233"/>
        <source>Las notas ocupan {total} de los {limite} caracteres que admite Proxmox: queda poco espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4241"/>
        <source>No se pudo leer la política de etiquetas del centro de datos, así que no se pudo comprobar si tus etiquetas están permitidas. Si Proxmox las rechaza, la máquina no se creará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4249"/>
        <source>El pool «{pool}» no existe en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4254"/>
        <source>No se pudo comprobar que el pool «{pool}» exista (no se puede leer la lista de pools). Proxmox lo verificará al crear.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4269"/>
        <source>No se pudo leer la descripción de la plantilla: no se añadirán las notas para no pisar las suyas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4275"/>
        <source>Las notas tienen caracteres de control (no imprimibles): se eliminarán al crear.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4280"/>
        <source>El nombre del pool no es válido: usa letras, números, «_» y «-», y «/» para separar pools anidados (hasta 3 niveles).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4287"/>
        <source>Para crear la máquina en el pool «{pool}» falta el privilegio VM.Allocate en «{ruta}» o en «{ruta_pool}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4311"/>
        <source>No hay pools en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4313"/>
        <source>Todavía no se leyó la lista de pools del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4321"/>
        <source>Se restableció «{opcion}» a su valor por defecto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4328"/>
        <source>El MTU solo se aplica a tarjetas VirtIO: con otra tarjeta queda en «Heredar».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4344"/>
        <source>Heredar del bridge</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4346"/>
        <source>Igual al bridge</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="4352"/>
        <source>{valor} MB/s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2589"/>
        <source>Subida desde tu equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="703"/>
        <source>Encendiendo la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2590"/>
        <source>Descarga en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2596"/>
        <source>Calculando la huella del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2599"/>
        <source>Comprobando el destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2602"/>
        <source>Enviando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2603"/>
        <source>Esperando al servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2606"/>
        <source>Verificando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2607"/>
        <source>Terminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2608"/>
        <source>Cancelada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2609"/>
        <source>Falló</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2610"/>
        <source>Dejaste de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2633"/>
        <source>{hechos} de {total} ({pct} %)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2641"/>
        <source>{pct} %</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2647"/>
        <source>{total} en total</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2653"/>
        <source>{v}/s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2659"/>
        <source>quedan {t}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2671"/>
        <source>Quedó un archivo incompleto en el servidor. ProxLaunch no puede borrarlo: pídele a tu administrador que lo elimine.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2677"/>
        <source>No quedó ningún archivo en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2678"/>
        <source>No sabemos si quedó un archivo incompleto en el servidor. Revisa el almacenamiento en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2690"/>
        <source>en «{storage}» ({nodo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2704"/>
        <source>Este archivo no parece un ISO de instalación normal. Puedes subirlo, pero revisa que sea el correcto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2710"/>
        <source>ProxLaunch no puede comprobar el contenido de un disco raw. Asegúrate de que es el archivo que quieres importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2721"/>
        <location filename="../../interfaz/textos.py" line="2728"/>
        <source>Escribe una dirección web completa que empiece por https://.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2724"/>
        <source>La dirección web es demasiado larga.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2725"/>
        <source>La dirección web tiene espacios o caracteres no admitidos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2731"/>
        <source>Solo se admiten direcciones seguras (https://). Una dirección http:// no está protegida y solo se permite en el modo avanzado, con confirmación.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2736"/>
        <source>A la dirección web le falta el nombre del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2739"/>
        <source>La dirección web no debe llevar usuario ni contraseña. Quítalos de la dirección.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2743"/>
        <source>El puerto de la dirección web no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2748"/>
        <source>La dirección web no es válida.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2755"/>
        <source>Escribe la huella del archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2756"/>
        <source>La huella no tiene un formato válido: son solo números y letras de la A a la F (por ejemplo, 64 caracteres para SHA-256).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2769"/>
        <source>El nombre debe terminar en qcow2, raw o vmdk.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2772"/>
        <source>El nombre debe terminar en iso o img.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2774"/>
        <source>Ese nombre está reservado por Windows. Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2778"/>
        <source>El nombre debe tener entre 1 y 100 caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2781"/>
        <source>Usa solo letras sin acentos, números, punto, guion y guion bajo, y no empieces por un punto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2795"/>
        <location filename="../../interfaz/textos.py" line="4335"/>
        <source>sí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2797"/>
        <location filename="../../interfaz/textos.py" line="4337"/>
        <source>no</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2800"/>
        <source>SeaBIOS (clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2802"/>
        <source>UEFI (OVMF)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2814"/>
        <source>Arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2816"/>
        <source>TPM 2.0</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2818"/>
        <source>Controlador de discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2820"/>
        <source>Tarjeta de red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2822"/>
        <source>Conexión del primer disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2824"/>
        <source>Agente de QEMU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2825"/>
        <source>{campo}: {antes} → {despues}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2838"/>
        <source>poner las etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2840"/>
        <source>cambiar los procesadores o la memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2851"/>
        <source>aplicar los ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2857"/>
        <source>las etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2859"/>
        <source>los procesadores o la memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2861"/>
        <source>el tamaño del disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2870"/>
        <source>los ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2887"/>
        <source>Se creó, pero falta aplicar {ajuste}. Puedes reintentar los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2891"/>
        <source>No se amplió el disco: no pudimos comprobar que tengas el permiso VM.Config.Disk. Amplíalo en Proxmox si lo necesitas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2897"/>
        <source>Se aplicaron los ajustes que faltaban al reintentar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2901"/>
        <source>La importación falló después de enviarse; pueden haber quedado discos sueltos en el almacenamiento. Revísalos en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2935"/>
        <source>{n} procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2942"/>
        <source>CPU {t}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2945"/>
        <source>{m} de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2951"/>
        <source>disco de {g} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2954"/>
        <source>igual que la plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2975"/>
        <source>ampliado a {g} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2991"/>
        <source>Tu usuario no tiene permiso para {accion}. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3000"/>
        <source>No pudimos comprobar tus permisos. Para {accion} hace falta {privilegio} en «{ruta}»; sin poder confirmarlo, esta opción no se usa.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3010"/>
        <source>Proxmox no permitió {accion}. Lo más probable es que a tu usuario le falte {privilegio} en «{ruta}». Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3019"/>
        <source>Falta el permiso {privilegio} en «{ruta}» para {accion}. Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3082"/>
        <source>Ese almacenamiento no admite este tipo de archivo. Elige otro almacenamiento o pide a tu administrador que lo active.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3088"/>
        <source>Proxmox no aceptó el ISO como unidad de CD. Comprueba que el archivo sea un ISO y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3094"/>
        <source>Los discos solo pueden crecer: elige un tamaño igual o mayor que el actual.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3103"/>
        <source>La plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3105"/>
        <source>La imagen de disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3107"/>
        <source>El CD de drivers</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3109"/>
        <source>El ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3110"/>
        <source>El archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3115"/>
        <source>la plantilla está en un almacenamiento que solo existe en su nodo y la máquina nueva iría a otro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3121"/>
        <source>el almacenamiento elegido no admite discos de máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3125"/>
        <source>un clon rápido y ligero no permite elegir almacenamiento ni formato; usa «Copia independiente»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3131"/>
        <source>el almacenamiento de la plantilla no admite clones rápidos y ligeros; usa «Copia independiente»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3137"/>
        <source>la plantilla está ocupada con otra operación; espera a que termine</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3141"/>
        <source>«{nombre}» ya no es una plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3145"/>
        <source>la plantilla tiene TPM y está encendida; apágala antes de clonar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3148"/>
        <source>Proxmox no lo permite con esta plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3153"/>
        <source>Este disco depende de otro archivo (un disco base). Conviértelo a un qcow2 independiente antes de subirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3159"/>
        <source>Este disco está cifrado y Proxmox no puede importarlo. Quítale el cifrado antes de subirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3165"/>
        <source>Este disco está formado por varios archivos. Conviértelo a un solo archivo antes de subirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3171"/>
        <source>Un archivo OVA no se puede importar tal cual. Extrae el disco que lleva dentro y súbelo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3177"/>
        <source>Esta versión del formato de disco no es compatible. Conviértelo a un qcow2 estándar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3182"/>
        <source>El archivo parece incompleto o dañado. Vuelve a copiarlo o a descargarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3186"/>
        <source>Este disco depende de otro archivo, está cifrado o no es un solo archivo. Conviértelo a un qcow2 independiente antes de subirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3199"/>
        <source>Tu Proxmox {version} no permite importar discos sin ser administrador del servidor. Puedes instalar desde un ISO o clonar una plantilla. Desde la versión 8.4 sí se puede importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3208"/>
        <source>Para importar discos, pide a tu administrador que active el contenido «Import» en un almacenamiento de tipo directorio, NFS o CIFS.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3215"/>
        <source>Podría activarse en: {lista}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3222"/>
        <source>Falta el permiso Sys.AccessNetwork en el nodo «{nodo}» para descargar desde una dirección web. Pídeselo a tu administrador o descarga el archivo en tu equipo y súbelo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3230"/>
        <source>Descargar desde una dirección web exige permisos de administrador en esta versión de Proxmox. Descarga el archivo en tu equipo y súbelo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3237"/>
        <source>El almacenamiento «{storage}» que usabas en este servidor ya no está disponible o ya no admite {contenido}. Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3247"/>
        <source>No puedes ver los archivos de «{storage}»: falta el permiso Datastore.Audit o Datastore.AllocateSpace.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3255"/>
        <source>El servidor dice que terminó, pero el archivo no coincide con el que enviaste. No lo uses.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3261"/>
        <source>El archivo llegó dañado: la huella no coincide. No quedó guardado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3265"/>
        <source>Se cortó la conexión mientras se subía el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3269"/>
        <source>Se habían enviado {hechos} de {total}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3274"/>
        <source>El archivo cambió mientras se subía. Vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3279"/>
        <source>Ya existe un archivo llamado «{nombre}» en «{storage}». ProxLaunch no lo sobrescribe: usa el que ya está o elige otro nombre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3288"/>
        <source>El servidor no pudo descargar {archivo} desde {host}: {motivo}. Prueba a descargarlo en tu equipo y subirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3295"/>
        <source>sin más detalles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3299"/>
        <source>Falta el permiso {privilegio} en «{ruta}» para {accion}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3307"/>
        <source>Para guardar el disco importado necesitas el permiso Datastore.AllocateSpace en «{storage}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3315"/>
        <source>Importar desde una ruta del servidor exige ser administrador (root). Sube el archivo desde tu equipo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3324"/>
        <source>{tipo} «{nombre}» ya no está en el servidor. Elige otra.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3331"/>
        <source>No veo ninguna plantilla con tu cuenta. Pide el permiso VM.Audit o crea la plantilla en Proxmox (clic derecho en la máquina → Convertir en plantilla).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3337"/>
        <source>No se puede clonar así: {motivo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3342"/>
        <source>El número de máquina {vmid} se ocupó justo antes de clonar. Vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3349"/>
        <source>Aquí va el nombre de un archivo del servidor, no una dirección web. Para descargar usa «Descargar en el servidor».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3357"/>
        <source>El nodo «{nodo}» tiene poco espacio temporal ({libre} libres) para recibir un archivo de {tamano}. La subida podría fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3367"/>
        <source>El archivo pesa {tamano} y «{storage}» solo tiene {libre} libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3375"/>
        <source>Hay una transferencia en curso. Espera a que termine o cancélala.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3389"/>
        <source>La máquina «{nombre}» se clonó, pero no se pudo {ajuste}. Puedes reintentar los ajustes o deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3400"/>
        <source>Transferencia cancelada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3413"/>
        <source>el CD de drivers</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3415"/>
        <source>la imagen de disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3416"/>
        <source>el ISO</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3429"/>
        <source>No se puede usar {objeto}. {causa}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3435"/>
        <source>No encuentro «{nombre}» en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3439"/>
        <source>No encuentro {objeto} en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3445"/>
        <location filename="../../interfaz/textos.py" line="3769"/>
        <source>Disponibles: {lista}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3450"/>
        <source>Este archivo tiene un nombre que ProxLaunch no admite. Cámbiale el nombre en Proxmox o elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3457"/>
        <source>No encuentro «{nombre}» entre los archivos del servidor. Elígelo de la lista.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3465"/>
        <source>El almacenamiento «{storage}» no está activo en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3476"/>
        <source>Elige {objeto} de la lista.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3483"/>
        <source>Elige una imagen de disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3485"/>
        <source>Elige una plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3486"/>
        <source>Elige un ISO.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3488"/>
        <source>Elige qué sistema operativo vas a instalar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3490"/>
        <source>Los datos del sistema operativo no corresponden al origen elegido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3493"/>
        <source>Falta elegir de dónde sale el sistema operativo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3498"/>
        <source>el sistema operativo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3500"/>
        <source>el TPM</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3502"/>
        <source>el agente de QEMU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3503"/>
        <source>el archivo de origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3511"/>
        <source>Este sistema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3513"/>
        <source>{so} pide al menos {cores} núcleos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3522"/>
        <source>{so} pide al menos {memoria} GiB de memoria.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3526"/>
        <source>{so} pide al menos {disco} GiB de disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3529"/>
        <source>{so} pide al menos {cores} núcleos, {memoria} GiB de memoria y {disco} GiB de disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3544"/>
        <source>Sin el permiso VM.Config.Disk no se puede fijar el orden de arranque. La máquina se creará igual; si no arranca desde el ISO, cambia el orden en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3550"/>
        <source>Sin el permiso VM.Config.Disk no se puede ampliar el disco. La máquina se creará con el tamaño original.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3556"/>
        <source>No pudimos comprobar tus permisos. </source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3567"/>
        <source>Este origen no usa {dato}: se ignorará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3574"/>
        <source>Hay más de un archivo llamado «{nombre}» ({volids}). Elige cuál usar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3581"/>
        <source>Windows necesita los drivers VirtIO y no encuentro ningún ISO «virtio-win» en el servidor. Sube uno, o elige «Crear sin los drivers» y cárgalos después.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3590"/>
        <source>Hay varias plantillas llamadas «{nombre}» ({plantillas}). Elige una.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3597"/>
        <source>Windows 11 exige un TPM 2.0.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3598"/>
        <source>Windows 11 exige arranque UEFI (OVMF).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3600"/>
        <source>Windows funciona con el arranque clásico (SeaBIOS), pero se recomienda UEFI (OVMF).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3606"/>
        <source>Si vas a instalar RHEL 10 (o Rocky, Alma, CentOS Stream 10), necesita un procesador x86-64-v3. Elige ese tipo de CPU o «host».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3611"/>
        <source>Este ISO parece de la familia RHEL 10 (Red Hat, Rocky, Alma), que necesita un procesador x86-64-v3. Con el tipo de CPU actual puede no arrancar: elige x86-64-v3 o «host».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3619"/>
        <source>Con un ISO solo caben {maximo} discos IDE; usa SCSI o SATA.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3630"/>
        <source>No hay un almacenamiento válido para el TPM: «{storage}» en «{nodo}» no admite discos de máquinas. Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3637"/>
        <source>No hay un almacenamiento válido para el TPM. Elige uno que admita discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3651"/>
        <source>Falta el permiso {privilegio} en «{ruta}» para subir o descargar archivos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3661"/>
        <source>Falta el permiso {privilegio} en «{ruta}» para clonar la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3672"/>
        <source>Un clon rápido y ligero se guarda en el almacenamiento de la plantilla y no permite elegir otro. Elige «Copia independiente».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3677"/>
        <source>Este almacenamiento no permite clonar de forma rápida y ligera. Elige «Copia independiente».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3684"/>
        <source>El tamaño del disco debe ser un número entero de GiB entre {minimo} y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3692"/>
        <source>El disco ya mide {actual_gib} GiB y pediste {pedido_gib} GiB. Los discos solo pueden crecer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3703"/>
        <source>Un valor que pides cambiar en la plantilla no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3714"/>
        <source>Para importar un disco necesitas un disco donde guardarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3718"/>
        <source>Sin disco no podrás instalar el sistema desde el ISO. Agrega un disco si quieres instalarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3728"/>
        <source>Se usará el CD de drivers «{volid}» (almacenamiento «{storage}»), que no es la versión que conoce ProxLaunch. Comprueba que es de confianza antes de crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3734"/>
        <source>Se usará el CD de drivers «{volid}», que no es la versión que conoce ProxLaunch. Comprueba que es de confianza antes de crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3746"/>
        <source>La plantilla «{nombre}» no está en el nodo «{nodo}» ni en un almacenamiento compartido con él.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3754"/>
        <source>La plantilla está ocupada con otra operación. Espera a que termine.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3759"/>
        <source>No se pudo leer la configuración de la plantilla «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3765"/>
        <source>Elige una plantilla de la lista.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3766"/>
        <source>No encuentro la plantilla «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3780"/>
        <source>«{nodo}» no tiene {objeto} «{fuente}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3790"/>
        <source>«{nodo}» no tiene la plantilla «{plantilla}» ni el almacenamiento «{storage}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="3797"/>
        <source>«{nodo}» no tiene la plantilla «{plantilla}».</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>TextosB</name>
    <message>
        <location filename="../../interfaz/textos_b.py" line="73"/>
        <location filename="../../interfaz/textos_b.py" line="693"/>
        <source>Pendiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="75"/>
        <source>Esperando la IP…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="77"/>
        <source>IP obtenida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="79"/>
        <source>IP a revisar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="81"/>
        <source>Sin agente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="83"/>
        <source>El agente no responde</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="85"/>
        <source>Sin IP</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="87"/>
        <source>Sin permiso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="89"/>
        <source>No aplica</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="91"/>
        <source>Se dejó de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="92"/>
        <source>Error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="113"/>
        <source>(a revisar)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="139"/>
        <source>Tu usuario no puede preguntar a la máquina por su IP: falta el permiso {privilegio}. Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="144"/>
        <source>Tu usuario no puede preguntar a la máquina por su IP. Hace falta el permiso VM.Monitor (Proxmox 8) o VM.GuestAgent.Audit (Proxmox 9) sobre la máquina. Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="162"/>
        <source>IP obtenida: {ip}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="168"/>
        <source>No coincide con la IP fija que se configuró{cual}. Revisa la red de la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="176"/>
        <source>Solo se encontró {ip}, que no es una dirección IPv4 de la primera tarjeta de red de la máquina (puede ser de otra tarjeta o ser IPv6). Compruébala antes de usarla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="182"/>
        <source>Tampoco coincide con la IP fija que se configuró.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="187"/>
        <source>La máquina no tiene activado el agente invitado en Proxmox, así que no se puede saber su IP. Actívalo en sus opciones (Opciones → Agente QEMU) y vuelve a encenderla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="194"/>
        <source>El agente invitado no respondió en el plazo. Suele pasar con las imágenes de Ubuntu y Debian, que no traen el agente: instálalo dentro de la máquina (paquete qemu-guest-agent) o usa un script de cloud-init que lo instale.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="201"/>
        <source>El agente respondió, pero no encontró ninguna IP útil (se ignoran las direcciones locales y las de Docker o de puentes). Puede que la máquina aún no tenga red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="207"/>
        <source>Interfaces ignoradas: {n}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="214"/>
        <source>No se esperó su IP: la máquina no se encendió o no llegó a crearse.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="219"/>
        <source>Se dejó de esperar su IP (o la máquina se eliminó). La máquina no se tocó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="224"/>
        <source>No se pudo consultar la IP por un error inesperado. Puedes verla en Proxmox, en el resumen de la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="236"/>
        <source>{con} con IP · {sin} sin IP · {na} no aplicable</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="240"/>
        <source>{n} esperando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="247"/>
        <source>La creación terminó. Se está esperando la IP de 1 máquina; no hace falta esperar para usar el resto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos_b.py" line="252"/>
        <source>La creación terminó. Se está esperando la IP de %n máquinas; no hace falta esperar para usar el resto.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="263"/>
        <source>Esperando su IP (hasta {plazo} s)… Puedes seguir usando ProxLaunch.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="272"/>
        <source>IP: {motivo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="279"/>
        <source>ProxLaunch sigue esperando la IP de algunas máquinas. Si cierras, dejará de esperar. Las máquinas no se tocan y no pasa nada en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="288"/>
        <source>Algunas máquinas todavía esperan su IP. Si las eliminas, se dejará de esperar antes de borrarlas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="297"/>
        <source>Vuelve a aplicar lo que no se pudo cambiar tras clonar: etiquetas, procesadores, memoria, tamaño del disco o la configuración inicial (cloud-init y contraseña). No crea máquinas nuevas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="319"/>
        <source>La máquina se creó, pero no se pudo conocer su IP. Mira la columna «IP» para ver el motivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="325"/>
        <source>La IP encontrada no es la de la primera tarjeta de red (o es IPv6). Compruébala antes de usarla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="331"/>
        <source>La IP que tiene la máquina no coincide con la IP fija que se pidió.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="340"/>
        <source>No se amplió el disco: el tamaño pedido no supera el de la imagen (el disco solo puede crecer).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="346"/>
        <source>No se amplió el disco: no pudimos comprobar que tengas el permiso VM.Config.Disk. Amplíalo en Proxmox si lo necesitas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="352"/>
        <source>La imagen se quedó en el almacenamiento de importación. ProxLaunch no la borra: pide a un administrador que la elimine desde Proxmox si ya no la necesitas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="358"/>
        <source>Se borró la máquina a medio crear. Puedes reintentar la creación (con otro VMID si quieres).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="364"/>
        <source>Se pidió borrar la máquina a medio crear, pero se dejó de esperar: la tarea sigue en Proxmox. Comprueba allí si se borró.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="373"/>
        <source>La máquina del intento anterior ({nombre}, VMID {vmid}) sigue en Proxmox. ProxLaunch no la borra: si no la quieres, bórrala a mano desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="384"/>
        <source>Se continuó sin ampliar el disco: tiene el tamaño de la imagen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="388"/>
        <source>Se continuó sin guardar los valores de cloud-init: las copias no los heredarán.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="393"/>
        <source>No se convirtió en plantilla: la máquina quedó como máquina normal y puedes encenderla o convertirla en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="400"/>
        <source>La dirección termina en «.img». Se pedirá al servidor con la extensión «.qcow2» porque las imágenes cloud de este tipo son qcow2.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="406"/>
        <source>Con la consola serie, la consola gráfica clásica de Proxmox (noVNC) se queda en negro. Para entrar a la máquina usa la consola «xterm.js» (la de texto).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="412"/>
        <source>Las imágenes oficiales de Ubuntu y Debian no traen el agente invitado (qemu-guest-agent). Sin él ProxLaunch no podrá decirte la IP de las copias y el apagado desde Proxmox puede tardar. Puedes instalarlo con un script de cloud-init.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="419"/>
        <source>El almacenamiento de destino es de tipo LVM grueso: las copias de esta plantilla solo podrán ser clones completos (no enlazados).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="450"/>
        <source>la contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="452"/>
        <source>la configuración inicial (cloud-init)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="455"/>
        <source>Se creó, pero no se pudo guardar {que}: a tu usuario le falta el permiso {privilegio} en «{ruta}». La máquina no se encendió. Pídeselo a tu administrador y reintenta los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="464"/>
        <source>Se creó, pero no se pudo guardar {que}: a tu usuario le falta un permiso (en Proxmox 8 VM.Config.Cloudinit o VM.Config.Network; en Proxmox 9, VM.Config.Cloudinit). La máquina no se encendió. Pídeselo a tu administrador y reintenta los ajustes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="476"/>
        <source>La máquina no tiene activado el agente invitado en Proxmox, así que no se puede saber su IP.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="482"/>
        <source>El agente invitado no respondió. Instala el paquete qemu-guest-agent dentro de la máquina o usa un script de cloud-init que lo instale.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="488"/>
        <source>La máquina no está encendida, así que no puede contestar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="492"/>
        <source>No se puede convertir en plantilla una máquina encendida. Apágala y reintenta.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="497"/>
        <source>No se puede convertir en plantilla una máquina con instantáneas (snapshots). Bórralas en Proxmox y reintenta.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="505"/>
        <source>La máquina está bloqueada por otra tarea de Proxmox ({bloqueo}). Espera a que termine y reintenta. No se convirtió en plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="512"/>
        <source>La máquina no está apagada, así que no se convirtió en plantilla. Apágala en Proxmox y reintenta.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="518"/>
        <source>Proxmox no aceptó el archivo porque su formato no coincide con la extensión. Si es una imagen «.img», ProxLaunch la pide como «.qcow2»; prueba a elegir una imagen con extensión .qcow2 o .raw, o descárgala a mano e impórtala desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="527"/>
        <source>La suma no coincide: la descarga no es la esperada. Esperada «{esperada}…», obtenida «{obtenida}…». No se usó el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="534"/>
        <source>La suma no coincide: la descarga no es la esperada. No se usó el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="538"/>
        <source>Ningún almacenamiento de este nodo admite el contenido «Importar». Pide al administrador que lo active (Centro de datos → Almacenamiento) en uno de tipo directorio, NFS o CIFS.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="553"/>
        <location filename="../../interfaz/textos_b.py" line="867"/>
        <source>Crear plantilla desde imagen cloud</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="558"/>
        <source>Una imagen cloud es un disco ya instalado y mínimo (Ubuntu, Debian, Rocky…) que se publica para servidores. No trae instalador: se importa tal cual y cloud-init la personaliza en el primer arranque.

Una plantilla es una máquina «modelo» de la que se sacan copias (clones). No se enciende ni se edita; cada copia nace con su propio disco. Convertir una máquina en plantilla no se puede deshacer.

El asistente hará esto, en orden: 1) pone la imagen en el servidor (la sube desde tu equipo o el servidor la descarga); 2) crea una máquina nueva con esa imagen como disco; 3) amplía el disco al tamaño que pidas; 4) guarda los valores de cloud-init (opcional); 5) convierte la máquina en plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="576"/>
        <source>Con este asistente conviertes una imagen cloud (un archivo .qcow2, .img, .raw o .vmdk) en una plantilla lista para clonar en «Clonar una plantilla». Si no sabes qué elegir, deja las opciones como están: están pensadas para Ubuntu, Debian, Rocky o AlmaLinux.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="584"/>
        <source>La imagen es el disco de partida. Puedes subirla desde tu equipo, pedir al servidor que la descargue de una dirección web o usar una que ya esté en el servidor. Las imágenes «.img» de Ubuntu son en realidad qcow2: ProxLaunch las sube como «.qcow2» sin tocar su contenido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="592"/>
        <source>La suma de verificación (huella) comprueba que el archivo no está dañado ni manipulado. Cópiala de la web oficial de la distribución. Si no coincide, no se sube ni se usa nada. Para archivos de tu equipo solo se admite SHA-256.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="599"/>
        <source>Son los ajustes que las imágenes cloud esperan. La unidad cloud-init es el pequeño disco donde Proxmox deja usuario, claves y red. La consola serie permite entrar con la consola «xterm.js». El agente invitado deja que Proxmox sepa la IP de la máquina, pero hay que instalarlo dentro (las imágenes de Ubuntu y Debian no lo traen).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="608"/>
        <source>Aquí puedes dejar guardados valores de cloud-init que heredarán todas las copias: usuario, claves SSH públicas, red por DHCP, DNS y dominio. Las copias pueden cambiarlos después. Por seguridad no existe campo de contraseña: una contraseña en la plantilla se copiaría a todas las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="616"/>
        <source>Una plantilla no se enciende ni se vuelve a convertir en máquina normal: solo sirve para crear copias. ProxLaunch no puede borrarla; si te equivocas, bórrala desde Proxmox (no se puede mientras tenga copias enlazadas).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="627"/>
        <source>Ejemplos (revisa en la web de cada distribución cuál es la dirección vigente):
• Ubuntu 24.04: https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
• Debian 12: https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2
• AlmaLinux 9: https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="641"/>
        <source>Entiendo que la plantilla no se puede encender ni volver a convertir en máquina normal; solo sirve para crear copias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="652"/>
        <source>Se va a crear la plantilla «{nombre}» (número {vmid}) en el nodo «{nodo}», con un disco de {gib} GiB en «{storage}», a partir de «{imagen}».

Cuando termine, la máquina se convertirá en plantilla. Esto NO se puede deshacer: la plantilla no se podrá encender ni volver a ser una máquina normal; solo servirá para crear copias.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="667"/>
        <source>1. Poner la imagen en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="669"/>
        <source>2. Crear la máquina e importar el disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="671"/>
        <source>3. Ampliar el disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="673"/>
        <source>4. Guardar los valores de cloud-init</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="674"/>
        <source>5. Convertir en plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="695"/>
        <source>En curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="697"/>
        <source>Hecho</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="699"/>
        <source>Falló</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="701"/>
        <source>Omitido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="702"/>
        <source>No sabemos cómo acabó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="708"/>
        <source>Puede haber quedado un archivo parcial («{archivo}») o nada en el almacenamiento de importación. ProxLaunch no borra archivos del almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="714"/>
        <source>Puede haber quedado una máquina a medio crear con el número reservado. Puedes comprobarlo, borrarla si es seguro, o reintentar con otro número.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="720"/>
        <source>La máquina está completa, pero el disco no se amplió.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="724"/>
        <source>La máquina está completa, pero sin los valores de cloud-init.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="727"/>
        <source>La máquina está completa, pero todavía no es una plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="734"/>
        <source>Reintentar la conversión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="736"/>
        <source>Reintentar la imagen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="737"/>
        <source>Reintentar este paso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="743"/>
        <source>Continuar sin ampliar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="745"/>
        <source>Continuar sin cloud-init</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="746"/>
        <source>Dejarla como máquina normal</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="756"/>
        <source>No puedo confirmar que la máquina sea tuya (no consta que este asistente la creara, o no se pudo leer su estado), así que no la borro. Si la máquina es de este asistente, bórrala desde Proxmox (menú «Más» → «Eliminar»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="763"/>
        <source>No se ofrece borrarla: está encendida. Apágala en Proxmox primero.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="767"/>
        <source>No se ofrece borrarla: está bloqueada por otra tarea de Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="771"/>
        <source>No se ofrece borrarla: tiene la protección contra borrado activada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="775"/>
        <source>No se ofrece borrarla: tu usuario no tiene el permiso VM.Allocate sobre la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="779"/>
        <source>No se ofrece borrarla: no cumple todas las condiciones de seguridad (nombre, plantilla, bloqueos).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="788"/>
        <source>Se va a eliminar de Proxmox la máquina «{nombre}» (número {vmid}), que este asistente dejó a medio crear. Esta acción no se puede deshacer. La imagen del almacenamiento de importación no se borra.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="798"/>
        <source>La plantilla «{nombre}» (número {vmid}) está lista en «{storage}». Ya puedes usarla en «Clonar una plantilla» (actualiza la lista de plantillas si no aparece).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="807"/>
        <source>La máquina «{nombre}» (número {vmid}) quedó como máquina normal, no como plantilla. Puedes convertirla en plantilla desde Proxmox cuando quieras.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="816"/>
        <source>El asistente está trabajando. Si lo cierras, ProxLaunch dejará de esperar, pero lo que ya se envió al servidor seguirá su curso y no se borrará nada. Después podrás ver en Proxmox cómo quedó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="831"/>
        <source>«{opcion}» necesita Proxmox {version} o una versión posterior.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="839"/>
        <source>Antes de la 8.4 Proxmox no permite subir imágenes de disco al contenido «Importar» del almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="847"/>
        <source>«{opcion}» no está disponible: tu usuario no tiene el privilegio {privilegio} en «{ruta}». Pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="869"/>
        <source>Subir un archivo de tu equipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="871"/>
        <source>Descargar desde una dirección web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="873"/>
        <source>Usar una imagen que ya está en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="875"/>
        <source>Consola serie</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="877"/>
        <source>Unidad cloud-init</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="879"/>
        <source>Agente invitado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="881"/>
        <source>Valores de cloud-init para las copias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="883"/>
        <source>Convertir en plantilla</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="884"/>
        <source>Borrar la máquina a medio crear</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="896"/>
        <source>Este asistente necesita Proxmox {requerida} o una versión posterior; este servidor es el {version}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="913"/>
        <source>El almacenamiento elegido para la imagen no admite el contenido «Importar» en este nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="921"/>
        <source>El almacenamiento «{storage}» no guarda discos de máquinas en el nodo «{nodo}». Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="931"/>
        <source>El nombre de la plantilla no es válido: usa letras sin acentos, números y guiones (sin espacios ni guiones al principio o al final), hasta 63 caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="938"/>
        <source>El tamaño pedido ({final_gib} GiB) no supera el de la imagen ({imagen_gib} GiB): el disco no se ampliará (solo puede crecer).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="946"/>
        <source>Ya hay un archivo con ese nombre en el servidor. Elige si usar el que ya está o reemplazarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="952"/>
        <source>Marca la casilla de que entiendes que la plantilla no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="957"/>
        <source>Una de las opciones marcadas necesita el permiso {privilegio} en «{ruta}», que tu usuario no tiene. Desmarca esa opción o pídeselo a tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="974"/>
        <source>Elige el archivo de imagen de tu equipo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="976"/>
        <source>Escribe la dirección web de la imagen y pulsa «Comprobar».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="980"/>
        <source>La dirección usa http://: no se puede garantizar que el archivo no fue alterado por el camino. Conviene indicar la suma de verificación.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="986"/>
        <source>Elige una imagen de la lista de imágenes del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="989"/>
        <source>No se pudo leer el archivo de imagen. Comprueba que existe y que puedes abrirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="997"/>
        <source>El archivo debe terminar en .qcow2, .img, .raw o .vmdk. Otros formatos (ISO, OVA, ZIP…) no se pueden importar como disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1002"/>
        <source>El nombre del archivo no es admisible: usa solo letras sin acentos, números, punto, guion y guion bajo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1012"/>
        <source>El archivo «.img» no es una imagen qcow2 ni un disco en bruto: no se renombra a ciegas. Conviértelo antes a qcow2.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1018"/>
        <source>El contenido del archivo no corresponde a su extensión. Renómbralo o conviértelo al formato correcto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1024"/>
        <source>El nombre con el que se subiría no corresponde al contenido del archivo. Vuelve a elegir el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1030"/>
        <source>El archivo está vacío.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1042"/>
        <source>elegida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1048"/>
        <source>Con una dirección http:// o sin verificar los certificados nada garantiza que el archivo no fue alterado por el camino, así que hace falta la suma de verificación SHA-256 o SHA-512. Suele publicarla la distribución junto a la imagen, por ejemplo en el archivo SHA256SUMS de Ubuntu.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1057"/>
        <source>La suma {algoritmo} es débil: no protege bien contra un archivo manipulado. Mejor usa SHA-256 o SHA-512.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1065"/>
        <source>Para un archivo de tu equipo solo se admite la suma SHA-256 (64 caracteres).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1070"/>
        <source>La suma no se usa con una imagen que ya está en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1073"/>
        <source>La suma de verificación no tiene un formato válido: solo números y letras de la A a la F, con la longitud de su algoritmo (64 caracteres para SHA-256).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1083"/>
        <source>Una plantilla nunca lleva contraseña: se copiaría a todas las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1088"/>
        <source>Los scripts (snippets) se eligen al clonar, no en la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1091"/>
        <source>En la plantilla solo se puede configurar la primera tarjeta de red y por DHCP. La IP fija se elige al clonar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1100"/>
        <source>Eso parece una clave privada. Nunca la pegues aquí: usa solo la clave pública (el archivo que termina en .pub).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1110"/>
        <source>Línea {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1112"/>
        <source>El texto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1115"/>
        <source>no empieza por un tipo de clave conocido (por ejemplo ssh-ed25519 o ssh-rsa)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1120"/>
        <source>le falta el cuerpo de la clave</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1122"/>
        <source>el cuerpo de la clave no es válido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1124"/>
        <source>lleva opciones por delante (command=…, from=…), que no se admiten</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1128"/>
        <source>supera el máximo de 20 claves</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1130"/>
        <source>es demasiado largo (máximo 8 KiB en total)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos_b.py" line="1132"/>
        <source>no es una clave pública</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>VentanaPrincipal</name>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="342"/>
        <source>ahora hay errores que impiden crear el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="353"/>
        <source>el número {a} ya no está libre (ahora se usa el {b})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="359"/>
        <source>«{n}» pasa de {a} a {b}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="367"/>
        <source>y %n cambios más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="385"/>
        <source>ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="506"/>
        <location filename="../../interfaz/ventana_principal.py" line="953"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="533"/>
        <source>Conecta con tu servidor Proxmox para empezar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="538"/>
        <location filename="../../interfaz/ventana_principal.py" line="621"/>
        <source>Conectar...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="554"/>
        <source>Actualizar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="558"/>
        <source>Reintentar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="574"/>
        <source>Avisos del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="620"/>
        <source>&amp;Archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="624"/>
        <source>Cerrar sesión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="626"/>
        <source>Salir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="629"/>
        <source>Ver el último lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="632"/>
        <source>Archivos subidos en esta sesión…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="635"/>
        <source>Crear plantilla desde imagen cloud…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="651"/>
        <source>&amp;Lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="652"/>
        <source>Abrir lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="655"/>
        <source>Guardar lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="658"/>
        <source>Guardar lote como…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="661"/>
        <source>Importar desde CSV…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="663"/>
        <source>Descargar plantilla CSV…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="665"/>
        <source>Guardar el informe del lote como CSV…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="674"/>
        <source>&amp;Perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="675"/>
        <source>Guardar como perfil de máquina…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="677"/>
        <source>Administrar perfiles…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="682"/>
        <source>&amp;Ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="683"/>
        <source>Almacenamientos recordados…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="686"/>
        <source>Tema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="690"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="691"/>
        <source>Oscuro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="692"/>
        <source>Claro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="700"/>
        <source>Modo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="704"/>
        <source>Básico</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="705"/>
        <source>Avanzado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="714"/>
        <source>A&amp;yuda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="715"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="725"/>
        <source>Acerca de ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="731"/>
        <source>Qué puedo hacer en este servidor…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="859"/>
        <source>Esa clave de recuperación ya no se puede volver a usar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="865"/>
        <source>Conectado a {b} ({a} no respondió)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="869"/>
        <source>Conectado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="989"/>
        <source>No se pudo leer el archivo de huellas (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="993"/>
        <source>Se dañó el archivo de huellas; se recuperaron {n} servidores. Los demás tendrás que confirmarlos de nuevo comparando la huella con tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1000"/>
        <source>No se pudo leer el archivo de perfiles (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1004"/>
        <source>El archivo de perfiles estaba dañado: se guardó una copia y se empezó uno nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1009"/>
        <source>No se pudo leer el archivo de preferencias (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1029"/>
        <source>Buscando nodos, almacenamientos y redes...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1041"/>
        <source>No se pudo leer el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1058"/>
        <source>{n} nodo(s) encontrados.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1066"/>
        <source>Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1106"/>
        <source>No se pudo leer el nodo {nodos}: aparece como «Sin conexión».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1258"/>
        <source>Este servidor no tiene uno de los nodos del lote. Quítalo de la lista o pasa a Automático para continuar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1514"/>
        <source>El servidor no permite poner etiquetas a las máquinas. Puedes crearla sin etiquetas; después, «Deshacer» solo podrá eliminarla si el nombre coincide.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1558"/>
        <source>Etiquetas desactivadas. Pulsa «Crear» para crear la máquina sin ellas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1573"/>
        <source>Todavía no sabemos si se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1575"/>
        <source>No hemos podido confirmar si la máquina se creó. Si vuelves al formulario y la creas otra vez, podrías duplicarla. ¿Volver de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1620"/>
        <source>Comprobando si la máquina existe...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1636"/>
        <source>Comprobando la tarea...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1638"/>
        <source>Esperando a que termine la tarea...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1679"/>
        <source>La máquina sí se creó. Verifica en Proxmox que quedó como esperabas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1688"/>
        <source>No se creó; puedes intentarlo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1697"/>
        <source>No se pudo comprobar si la máquina existe. Revisa la conexión e inténtalo de nuevo antes de volver a crearla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1744"/>
        <source>El último lote se cerró sin terminar. Informe: {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1997"/>
        <source>Confirmar el envío</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="1998"/>
        <source>Se enviarán %n máquinas a Proxmox. ¿Continuar?</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2004"/>
        <source>Crear las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2005"/>
        <location filename="../../interfaz/ventana_principal.py" line="2211"/>
        <location filename="../../interfaz/ventana_principal.py" line="3407"/>
        <location filename="../../interfaz/ventana_principal.py" line="3504"/>
        <location filename="../../interfaz/ventana_principal.py" line="3578"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2203"/>
        <source>Seguir sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2204"/>
        <source>Se detendrá este lote y se armará uno nuevo con las máquinas que faltan, sin etiquetas. Después, «Deshacer» solo podrá eliminar las máquinas que ProxLaunch confirme que creó él mismo. Antes de crear nada verás el resumen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2210"/>
        <source>Preparar el lote sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2221"/>
        <source>Esperando a que terminen las tareas en curso para continuar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2240"/>
        <location filename="../../interfaz/ventana_principal.py" line="2246"/>
        <source>Cancelar el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2241"/>
        <source>Las máquinas que ya se enviaron seguirán creándose en Proxmox y se esperará su resultado. Las demás no se enviarán.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2247"/>
        <source>Seguir creando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2292"/>
        <source>El lote terminó de forma inesperada: {m}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2313"/>
        <source>Reconecta para continuar con las máquinas que faltan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2315"/>
        <source>Reconecta para continuar con el lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2471"/>
        <source>Reintentando los ajustes pendientes...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2677"/>
        <source>Deshacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2770"/>
        <source>Eliminando las máquinas elegidas…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2922"/>
        <source>Hay máquinas sin confirmar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2923"/>
        <source>No sabemos si algunas máquinas se crearon. Si vuelves y repites el lote, podrías duplicarlas. ¿Volver de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2928"/>
        <source>Volver de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2929"/>
        <source>Quedarme aquí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3003"/>
        <source>No se pudo leer el archivo de perfiles de máquina (permisos): solo verás los perfiles de fábrica.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3010"/>
        <source>El archivo de perfiles de máquina estaba dañado: se guardó una copia y se empezó uno nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="3019"/>
        <source>Se omitieron %n perfiles dañados del archivo de perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3092"/>
        <source>Necesita Proxmox 8.4 o una versión posterior.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3104"/>
        <source>Hay una transferencia, un lote o una simulación en curso. Espera a que termine o cancélala.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3129"/>
        <source>Plantilla creada. Ya puedes clonarla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3201"/>
        <source>La espera de la IP terminó de forma inesperada: {m}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3266"/>
        <source>IPs guardadas en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3404"/>
        <source>Cambiar de perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3405"/>
        <source>Se reemplazarán los ajustes de hardware que cambiaste.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3406"/>
        <source>Reemplazar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3432"/>
        <source>Perfil «{nombre}» aplicado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3484"/>
        <source>Perfil «{nombre}» guardado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3499"/>
        <source>Guardar cambios en el perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3500"/>
        <source>Se reemplazará el hardware guardado en el perfil «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3503"/>
        <source>Guardar cambios</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3518"/>
        <source>Perfil «{nombre}» actualizado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3573"/>
        <source>Cambios sin guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3574"/>
        <source>¿Guardar el lote antes de continuar?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3575"/>
        <source>Si no lo guardas, se perderán los cambios del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3576"/>
        <source>Guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3577"/>
        <source>No guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3644"/>
        <source>No se puede guardar el lote: {campos} no es un número. Corrígelo e inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3707"/>
        <source>Lote guardado en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3723"/>
        <source>Leyendo el lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3767"/>
        <source>Lote «{nombre}» cargado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3780"/>
        <source>El lote se guardó con Proxmox {guardada}; este servidor tiene {actual}. Algunas opciones podrían no estar disponibles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3885"/>
        <source>Corrige los errores marcados para poder ver el resumen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4043"/>
        <source>No se pudieron importar las filas elegidas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="4066"/>
        <source>Se importaron %n máquinas desde «{archivo}»</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4077"/>
        <source>Plantilla guardada en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4095"/>
        <source>Informe guardado en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4115"/>
        <source>Hay una transferencia en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4116"/>
        <source>Se está subiendo o descargando un archivo. Si cierras, se cancelará: puede quedar un archivo incompleto en el servidor y ProxLaunch no puede borrarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4121"/>
        <source>Cancelar la transferencia y cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4179"/>
        <source>Hay un «Deshacer» en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4180"/>
        <source>Se están eliminando máquinas. Si cierras, ProxLaunch dejará de esperar: las eliminaciones ya enviadas seguirán en Proxmox y el resto no se hará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4158"/>
        <source>Hay un lote en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4159"/>
        <source>Hay un lote en curso ({x} de {n} terminadas). Si cierras, las tareas ya enviadas seguirán en Proxmox, pero ProxLaunch no enviará el resto ni podrá deshacer lo creado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4165"/>
        <location filename="../../interfaz/ventana_principal.py" line="4185"/>
        <location filename="../../interfaz/ventana_principal.py" line="4210"/>
        <location filename="../../interfaz/ventana_principal.py" line="4225"/>
        <source>Cerrar de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4122"/>
        <location filename="../../interfaz/ventana_principal.py" line="4166"/>
        <location filename="../../interfaz/ventana_principal.py" line="4186"/>
        <location filename="../../interfaz/ventana_principal.py" line="4211"/>
        <location filename="../../interfaz/ventana_principal.py" line="4226"/>
        <source>Seguir en ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4206"/>
        <source>Se está esperando la IP de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4219"/>
        <source>Hay una plantilla en creación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4220"/>
        <source>El asistente de plantillas está trabajando. Si cierras, ProxLaunch dejará de esperar: lo que ya se envió seguirá en Proxmox y no se borrará nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4234"/>
        <source>Hay una máquina en creación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4236"/>
        <source>Se está creando una máquina. Si cierras ProxLaunch, la tarea sigue ejecutándose en el servidor Proxmox, pero ya no verás su resultado. ¿Cerrar de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="4250"/>
        <source>Cerrando...</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>VistaCapacidades</name>
    <message>
        <location filename="../../interfaz/modelos_tabla_origen.py" line="436"/>
        <source>En Proxmox se activa en Datacenter → Almacenamiento → (el almacenamiento) → Editar → Contenido → {contenido}.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>_DialogoExportar</name>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="132"/>
        <source>Exportar perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="138"/>
        <source>Se exportará el perfil «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="140"/>
        <source>Se exportarán %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="142"/>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="145"/>
        <source>Incluir los nombres de almacenamiento y red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="152"/>
        <source>Normalmente conviene dejarlo sin marcar: esos nombres son de tu servidor y casi nunca existen en el de otra persona.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="161"/>
        <source>El archivo nunca incluye contraseñas, tokens, direcciones ni nombres de usuario.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="168"/>
        <source>Elegir dónde guardar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="169"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
</TS>
