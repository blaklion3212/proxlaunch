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
        <location filename="../../interfaz/ayuda.py" line="31"/>
        <source>Es el número que identifica a la máquina en todo el servidor y no se puede repetir. ProxLaunch propone el siguiente libre; solo cámbialo si necesitas uno concreto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="36"/>
        <source>Un nodo es cada servidor físico de tu clúster. En Automático ProxLaunch elige el que tiene más memoria y espacio libres; en Manual eliges tú dónde se crea la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="41"/>
        <source>Es el programa con el que arranca la máquina. SeaBIOS es el clásico y sirve para casi todo; UEFI (OVMF) es el moderno y lo piden algunos sistemas, como Windows 11.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="46"/>
        <source>Define qué procesador ve la máquina. El valor predeterminado funciona en servidores distintos; «host» rinde más pero impide mover la máquina entre nodos con procesadores diferentes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="52"/>
        <source>Un socket es un procesador físico virtual. Casi siempre basta con 1; sube los núcleos en lugar de los sockets.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="57"/>
        <source>Cantidad de núcleos de cálculo por cada socket. El total de procesadores virtuales es sockets por núcleos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="62"/>
        <source>Memoria RAM que tendrá la máquina, en GiB (1 GiB son 1024 MiB). Puedes usar decimales, por ejemplo 0,5 para medio GiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="67"/>
        <source>Permite que el servidor recupere memoria que la máquina no está usando. Si lo activas indicas la memoria mínima que se le deja; «Predeterminado» deja que Proxmox decida.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="72"/>
        <source>Es el tipo de conexión del disco virtual. SCSI es la opción recomendada; VirtIO es muy rápido pero necesita controladores en algunos sistemas; SATA e IDE son los más compatibles y los más lentos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="78"/>
        <source>Es el controlador que gestiona los discos SCSI de la máquina. El predeterminado (virtio-scsi-single) es el mejor y es el único que permite IO Thread.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="83"/>
        <source>Cómo se guarda el disco. Raw ocupa todo el espacio y es el más rápido; qcow2 crece según se usa y permite instantáneas. Algunos almacenamientos solo admiten raw.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="88"/>
        <source>Es el lugar del servidor donde se guardará el disco. Se muestra el espacio libre de cada uno; ProxLaunch propone el que más tiene.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="93"/>
        <source>Tamaño del disco en GiB, siempre un número entero de 1 en adelante. El disco se crea vacío: el sistema operativo se instala después.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="98"/>
        <source>Avisa al almacenamiento de qué espacio ya no se usa para que pueda recuperarlo. Conviene dejarlo activado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="103"/>
        <source>Hace que el sistema vea el disco como una unidad de estado sólido (SSD), lo que mejora cómo lo trata. No está disponible en el bus VirtIO.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="108"/>
        <source>Dedica un hilo de trabajo propio a atender el disco, lo que mejora el rendimiento con mucha actividad. Necesita el bus VirtIO o SCSI con el controlador virtio-scsi-single.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="113"/>
        <source>Crea la máquina sin ningún disco. Es útil si vas a añadirlo o importarlo más tarde.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="117"/>
        <source>Un bridge es el «conmutador virtual» del servidor que conecta la máquina a tu red. Lo habitual es vmbr0.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="122"/>
        <source>Tipo de tarjeta de red que ve la máquina. VirtIO es la más rápida; E1000 es más compatible con sistemas antiguos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="127"/>
        <source>Número de red virtual (VLAN) para separar el tráfico, entre 1 y 4094. Déjalo vacío si tu red no usa VLAN.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="132"/>
        <source>La huella es la «firma» del certificado del servidor. Comprueba que coincide con la que te dé tu administrador: así sabes que te conectas al servidor correcto y no a uno falso.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="138"/>
        <source>Acepta cualquier certificado sin comprobarlo. Es inseguro: úsalo solo en redes de prueba que controles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="143"/>
        <source>Es el segundo paso de seguridad de tu cuenta. Escribe el código de 6 números que muestra tu aplicación de autenticación, o usa una clave de recuperación si no puedes acceder a ella.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="149"/>
        <source>Guarda el token o la contraseña en el llavero de tu sistema (nunca en un archivo). Déjalo desmarcado en equipos compartidos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="154"/>
        <source>Hace que ProxLaunch se comporte como si el servidor tuviera otra versión de Proxmox. Solo para casos especiales; normalmente se detecta sola.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="160"/>
        <source>Cuántas máquinas iguales quieres crear de una vez, de 1 a {max}. Todas comparten la misma configuración del formulario y solo cambian el nombre y el número.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="165"/>
        <source>Es el principio del nombre de todas las máquinas. Con «srv-web» se crean srv-web-01, srv-web-02, etc. Usa letras sin acentos, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="170"/>
        <source>Lo que va entre el prefijo y el número. Puede ser un guion («srv-01») o nada («srv01»).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="174"/>
        <source>Es el número con el que empieza la numeración de los nombres. Con 5, las máquinas se llaman srv-05, srv-06, srv-07...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="179"/>
        <source>Cuántos dígitos tiene como mínimo el número del nombre, completando con ceros: con 2 es «01» y con 3 es «001». Si hacen falta más dígitos, se usan en todos los nombres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="184"/>
        <source>Es el primer número de máquina (VMID) del lote; las demás usan los siguientes. Si alguno ya está ocupado se salta y se te avisa. Déjalo vacío para que ProxLaunch proponga uno.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="190"/>
        <source>Dónde se crean las máquinas. En Automático ProxLaunch las reparte entre los nodos del clúster que pueden alojarlas; en «Un nodo» van todas al que elijas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="195"/>
        <source>Marca los nodos entre los que se repartirán las máquinas. Solo se pueden elegir los que están en línea.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="200"/>
        <source>Equilibrado manda cada máquina al nodo que tenga más memoria libre en ese momento (contando las que ya le tocaron), para que ninguno se llene antes que los demás.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="205"/>
        <source>Por turnos reparte las máquinas una a cada nodo, en orden alfabético, y vuelve a empezar. Es predecible, pero no tiene en cuenta cuánta memoria le queda a cada nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="210"/>
        <source>Algunos almacenamientos prometen el espacio de los discos pero no lo reservan hasta que se usa. Puedes crear más discos de los que caben, y funciona mientras no se llenen; si se llenan, todas las máquinas de ese almacenamiento pueden fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="216"/>
        <source>Simular hace todas las comprobaciones y muestra qué se enviaría a Proxmox, pero no crea nada ni cambia nada en el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="221"/>
        <source>Elimina de Proxmox las máquinas que creó este lote, con sus discos. Solo toca las que ProxLaunch puede demostrar que creó él, y nunca se hace sin que lo confirmes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="226"/>
        <source>Marca cada máquina con las etiquetas «proxlaunch» y «lote-» más un código, visibles en Proxmox. Sirven para reconocer lo que creó este lote y poder deshacerlo con seguridad. Si tu servidor no admite etiquetas nuevas, desactívalo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="232"/>
        <source>Un perfil de máquina guarda el hardware de una máquina virtual (procesadores, memoria, discos y red). Al elegirlo se rellena el formulario; el nombre, el número y el nodo siguen siendo tuyos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="238"/>
        <source>Los perfiles de fábrica vienen con ProxLaunch y no se pueden cambiar ni borrar. Si quieres una variante, duplícalo y haz tu propia versión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="243"/>
        <source>Un perfil puede recordar el almacenamiento y la red que usaba. Si en este servidor no existen, ProxLaunch usa los predeterminados y te avisa; nunca inventa nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="248"/>
        <source>Guarda el hardware actual del formulario como perfil de máquina para reutilizarlo. No guarda el nombre, el número ni el nodo de la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="253"/>
        <source>Exportar crea un archivo con tus perfiles para compartirlos. Por defecto no incluye los nombres de almacenamiento y de red de tu servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="258"/>
        <source>Importar añade perfiles de un archivo. Antes de guardar nada verás una lista para elegir cuáles, y si un nombre ya existe puedes conservar ambos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="263"/>
        <source>Indica si el perfil funciona con la versión de Proxmox y con el servidor al que estás conectado. Los avisos no impiden crear la máquina; los errores sí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="268"/>
        <source>Un lote guardado es un archivo con la definición de un lote (hardware, cantidad, nombres y reparto) para repetirlo. No guarda datos de conexión ni contraseñas; al abrirlo se vuelve a comprobar todo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="274"/>
        <source>Importar desde CSV crea un lote con una máquina por cada fila de una hoja de cálculo. Antes de crear nada verás una vista previa y un resumen que debes confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="279"/>
        <source>Descarga un archivo CSV de ejemplo con todas las columnas y dos filas de muestra. Ábrelo en tu hoja de cálculo, cambia los datos y guárdalo como CSV.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="284"/>
        <source>Es el carácter que separa las columnas: punto y coma, coma o tabulador. ProxLaunch lo detecta solo; cámbialo si la vista previa se ve mal.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="289"/>
        <source>Es la forma en que el archivo guarda los acentos. ProxLaunch la detecta sola; si ves letras raras, prueba otra o guarda el archivo como «CSV UTF-8» desde Excel.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="294"/>
        <source>Memoria y disco sin unidad se leen en GiB. También puedes escribir MiB, GiB o TiB (por ejemplo «4 GiB»). Evita los separadores de miles: «1.000» es ambiguo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="299"/>
        <source>Muestra cada fila del archivo con su estado y sus problemas. Puedes excluir filas antes de continuar; nada se crea hasta que confirmes el resumen del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="304"/>
        <source>En un lote por filas cada máquina tiene su propia configuración, como venía en el archivo. Para cambiar algo, corrige el archivo e impórtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="309"/>
        <source>Si se corta la conexión justo al enviar una máquina, no se sabe si Proxmox llegó a crearla. ProxLaunch nunca la vuelve a enviar sola, porque podría duplicarla: usa «Comprobar» para ver si existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="384"/>
        <source>Rinde más pero impide mover la máquina entre nodos con procesadores distintos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="393"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="399"/>
        <source>Entra en la página web de tu Proxmox y ve a Datacenter → Permisos → Roles → Crear. Llama al rol «{rol}» y marca los privilegios de la lista de abajo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="404"/>
        <source>Ve a Datacenter → Permisos → Usuarios y crea un usuario para ProxLaunch (por ejemplo «proxlaunch@pve»), o elige uno que ya tengas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="409"/>
        <source>Ve a Datacenter → Permisos → Tokens de API → Añadir. Elige el usuario, escribe un nombre para el token (por ejemplo «lab») y pulsa Añadir. Copia el secreto que se muestra: solo aparece una vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="415"/>
        <source>Ve a Datacenter → Permisos → Añadir → Permiso de usuario (o de token). Ruta «/», elige el usuario o el token, rol «{rol}» y deja marcado «Propagar».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="420"/>
        <source>En ProxLaunch pega el token completo con el formato usuario@realm!nombre=secreto, por ejemplo proxlaunch@pve!lab=11111111-2222-3333-4444-555555555555.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="431"/>
        <source>Usa siempre un token con los permisos mínimos en lugar de root@pam: si el token se filtra, el daño es mucho menor y puedes revocarlo sin cambiar contraseñas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="436"/>
        <source>Al crear el token puedes desmarcar «Separación de privilegios» solo si ya asignaste los permisos al usuario; si la dejas marcada, el token necesita sus propios permisos (paso 4 con el token).</source>
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
        <location filename="../../interfaz/vistas/bloque_lote.py" line="74"/>
        <source>Lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="105"/>
        <source>Cantidad</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="109"/>
        <source>Cantidad de máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="120"/>
        <source>por ejemplo srv-web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="123"/>
        <source>Prefijo de los nombres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="127"/>
        <source>Prefijo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="133"/>
        <source>Vista previa de los nombres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="136"/>
        <source>Guion (-)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="137"/>
        <source>Ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="140"/>
        <source>Separador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="148"/>
        <source>Número inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="156"/>
        <source>Relleno (dígitos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="162"/>
        <source>automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="165"/>
        <source>Número de máquina inicial (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="187"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="188"/>
        <source>Un nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="190"/>
        <source>Nodos elegidos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="199"/>
        <source>Nodo de destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="208"/>
        <source>Equilibrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="211"/>
        <source>Por turnos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="214"/>
        <source>Algoritmo de reparto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="230"/>
        <source>Dónde crearlas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="235"/>
        <source>Reparto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="250"/>
        <source>Etiquetar las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="359"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="397"/>
        <source>{nodo} (no existe)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="638"/>
        <source>Se llamarán: {nombres}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Campos</name>
    <message>
        <location filename="../../interfaz/vistas/campos.py" line="98"/>
        <source>Ayuda</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ColumnasCsv</name>
    <message>
        <location filename="../../interfaz/textos.py" line="1678"/>
        <source>nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1679"/>
        <source>perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1680"/>
        <source>vmid</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1681"/>
        <source>nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1682"/>
        <source>cpu</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1683"/>
        <source>sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1684"/>
        <source>memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1685"/>
        <source>disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1686"/>
        <source>almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1687"/>
        <source>red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1688"/>
        <source>vlan</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1689"/>
        <source>modelo_red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1690"/>
        <source>firmware</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1691"/>
        <source>tipo_cpu</source>
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
    <name>DialogoConexion</name>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="85"/>
        <source>Conectar con Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="122"/>
        <source>Duplicar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="123"/>
        <source>Eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="125"/>
        <source>Perfil guardado:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="133"/>
        <source>Nombre del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="137"/>
        <source>Un servidor por línea. Si el primero no responde se prueba el siguiente.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="139"/>
        <source>Servidores (IP o nombre)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="142"/>
        <source>Puerto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="147"/>
        <source>API Token (recomendado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="148"/>
        <source>Usuario y contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="160"/>
        <source>Método</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="166"/>
        <source>Token</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="167"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="174"/>
        <source>Realm</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="176"/>
        <source>Usuario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="179"/>
        <source>Contraseña</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="190"/>
        <source>Recordar credenciales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="193"/>
        <source>Ignorar verificación SSL</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="197"/>
        <source>Detectada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="202"/>
        <source>Forzar compatibilidad con la versión...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="233"/>
        <source>Guardar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="234"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="235"/>
        <source>Probar y conectar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="280"/>
        <location filename="../../interfaz/dialogos/conexion.py" line="584"/>
        <source>(Perfil nuevo)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="363"/>
        <source>Las credenciales guardadas se borrarán del llavero al guardar o conectar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="368"/>
        <source>(guardado en el llavero)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="379"/>
        <source>{nombre} (copia)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="389"/>
        <source>Eliminar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="391"/>
        <source>Se eliminará el perfil «{nombre}», sus credenciales guardadas en el llavero y las huellas de certificado que solo usaba él. ¿Continuar?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="411"/>
        <source>Ya existe otro perfil con este nombre. Puedes guardarlo igualmente, pero costará distinguirlos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="493"/>
        <source>Escribe tu usuario.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="520"/>
        <source>Estás usando root@pam. Es más seguro usar un API Token con permisos mínimos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="542"/>
        <source>La identidad del servidor no se comprobará: la conexión quedará sin verificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="561"/>
        <source>Perfil guardado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="566"/>
        <source>Perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="633"/>
        <source>Escribe tu contraseña.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="639"/>
        <source>Conexión sin verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="641"/>
        <source>No se comprobará la identidad del servidor. Tu contraseña viajaría sin esa protección y alguien en la red podría interceptarla. ¿Conectar igualmente?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="661"/>
        <source>Comprobando el certificado del servidor...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="699"/>
        <source>Conectando...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/conexion.py" line="724"/>
        <source>Esperando el segundo factor...</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoDeshacer</name>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="33"/>
        <source>Deshacer lo creado por el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="39"/>
        <source>Todo lo que creó el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="42"/>
        <source>Solo las incompletas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="49"/>
        <source>Máquinas que se pueden eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="74"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="85"/>
        <source>¿Qué quieres deshacer?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="123"/>
        <source>Se eliminará esta máquina y sus discos de Proxmox. Esta acción no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/deshacer.py" line="130"/>
        <source>Eliminar 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/deshacer.py" line="134"/>
        <source>Se eliminarán estas %n máquinas y sus discos de Proxmox. Esta acción no se puede deshacer.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/deshacer.py" line="143"/>
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
        <source>Se guardará el hardware actual del formulario: procesador, memoria, discos y redes. No se guarda el nombre de la máquina, su número ni el nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="297"/>
        <source>Resumen del perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="302"/>
        <source>Recordar los nombres de almacenamiento y red (solo sirven en servidores que los tengan)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="310"/>
        <source>Recordar los nombres de almacenamiento y red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="315"/>
        <source>Si lo marcas, el perfil recuerda en qué almacenamiento y red estaba cada disco. Al usarlo en otro servidor, si esos nombres no existen se elegirán otros y se te avisará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guardar_perfil.py" line="343"/>
        <source>Corrige esto en el formulario antes de guardar el perfil:</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoGuiaToken</name>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="39"/>
        <source>Privilegios del rol «{rol}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/guia_token.py" line="55"/>
        <source>Cerrar</source>
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
        <location filename="../../interfaz/dialogos/importar_csv.py" line="148"/>
        <source>Importar desde CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="187"/>
        <source>Cada fila del archivo es una máquina. Aquí solo se revisa: no se crea nada hasta que confirmes el resumen del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="196"/>
        <source>Todavía no elegiste un archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="197"/>
        <source>Archivo CSV</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="199"/>
        <source>Elegir otro archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="200"/>
        <source>Descargar plantilla…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="202"/>
        <source>Guarda un CSV de ejemplo con las columnas que entiende ProxLaunch.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="212"/>
        <source>Perfil base</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="216"/>
        <source>Perfil base:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="223"/>
        <source>El perfil base aporta todo lo que el archivo no diga (procesador, discos, red…). Las columnas del archivo siempre mandan sobre el perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="230"/>
        <source>Codificación del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="231"/>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="251"/>
        <source>Detectar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="240"/>
        <source>Codificación:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="244"/>
        <source>Es la forma en que el archivo guarda las letras con acento. Si ves símbolos raros, prueba otra; lo más habitual es «UTF-8» o «Windows-1252».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="250"/>
        <source>Separador de columnas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="253"/>
        <source>; (punto y coma)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="254"/>
        <source>, (coma)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="255"/>
        <source>Tabulador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="256"/>
        <source>| (barra vertical)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="260"/>
        <source>Separador:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="264"/>
        <source>Es el carácter que separa las columnas. Excel en español usa «;» y en inglés «,». ProxLaunch lo detecta solo; cámbialo únicamente si las columnas salen mal.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="297"/>
        <source>Sin conexión: aún no se comprobó contra el servidor. Conéctate a un servidor para poder continuar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="306"/>
        <source>Resumen de la vista previa</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="307"/>
        <source>Mostrar solo problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="308"/>
        <source>Copiar errores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="309"/>
        <source>Copia al portapapeles la lista de errores.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="320"/>
        <source>Filas del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="327"/>
        <source>Detalle de la fila seleccionada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="329"/>
        <source>Selecciona una fila para ver sus problemas y los valores originales.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="337"/>
        <source>Descargar filas con error…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="339"/>
        <source>Guarda un CSV con solo las filas con error, listo para corregir y reimportar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="341"/>
        <source>Corregir el archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="342"/>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="786"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="343"/>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="611"/>
        <source>Continuar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="468"/>
        <source>Leyendo el archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="562"/>
        <source>No se pudo saber qué separador usa el archivo. Elige uno en la lista «Separador».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="582"/>
        <source>tabulador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="595"/>
        <source>Codificación {codificacion} · separador {separador} · </source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="599"/>
        <source>1 fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="599"/>
        <source>%n filas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="600"/>
        <source>{c} correctas, {a} con aviso, {e} con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="613"/>
        <source>No hay filas correctas para importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="615"/>
        <source>Importar solo la fila correcta</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="617"/>
        <source>Importar solo las %n filas correctas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="630"/>
        <source>Conéctate a un servidor para poder continuar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="633"/>
        <source>No queda ninguna fila para importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="665"/>
        <source>Se guardó la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="681"/>
        <source>{base}-errores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="695"/>
        <source>Se guardó el archivo con las filas con error.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="705"/>
        <source>Se copiaron %n errores.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="722"/>
        <source>Fila {n} · {nombre} · {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="730"/>
        <source>Sin problemas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="733"/>
        <source>{columna}: Valor del archivo: «{valor}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="750"/>
        <source>tiene un error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="752"/>
        <source>la excluiste tú</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="755"/>
        <source>Fila {n} · {nombre} ({motivo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="771"/>
        <source>Se importarán {n} de {total} filas del archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="774"/>
        <source>No se importarán estas filas:</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_csv.py" line="777"/>
        <source>y %n más (míralas en «Mostrar detalles»)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="780"/>
        <source>Importar solo una parte del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_csv.py" line="785"/>
        <source>Importar esas filas</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DialogoImportarPerfiles</name>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="124"/>
        <source>Importar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="125"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="126"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="127"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="153"/>
        <source>✖ No válido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="155"/>
        <source>Omitido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="157"/>
        <source>✔ Nuevo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="159"/>
        <source>⚠ Reemplaza al existente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="160"/>
        <source>⚠ Nombre repetido: se conservan ambos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="175"/>
        <source>Importar «{nombre}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="216"/>
        <source>Importar perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="227"/>
        <source>El archivo tiene 1 perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="229"/>
        <source>El archivo tiene %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="231"/>
        <source>Se pueden importar {n}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="233"/>
        <source>Resumen del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="237"/>
        <source>Todavía no se guardó nada. Elige qué perfiles quieres importar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="248"/>
        <source>Perfiles del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="254"/>
        <source>Este nombre ya existe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="255"/>
        <source>Qué hacer con un nombre repetido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="256"/>
        <source>Conservar ambos (el importado se renombra)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="257"/>
        <source>Reemplazar el perfil que ya tengo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="258"/>
        <source>Omitir este perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="276"/>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="428"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="312"/>
        <source>(perfil {n} sin nombre válido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="357"/>
        <source>Importar 1 perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="357"/>
        <source>Importar %n perfiles</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="376"/>
        <source>Ya existe «{nombre}» y es un perfil de fábrica: no se puede reemplazar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="379"/>
        <source>Ya tienes un perfil llamado «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="417"/>
        <source>Se reemplazará %n perfil tuyo por el del archivo:</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="421"/>
        <source>Esta acción no se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="425"/>
        <source>Reemplazar perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/importar_perfiles.py" line="427"/>
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
        <location filename="../../interfaz/dialogos/informe.py" line="77"/>
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
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="66"/>
        <source>De fábrica</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="67"/>
        <source>Propio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="102"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="103"/>
        <source>Tipo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="104"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="117"/>
        <source>{nombre}, {tipo}: {resumen}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="212"/>
        <source>Administrar perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="231"/>
        <source>Un perfil de máquina es un punto de partida con el hardware ya elegido (procesador, memoria, discos y red). No es una plantilla de Proxmox ni un perfil de conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="242"/>
        <source>Perfiles de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="247"/>
        <source>Descripción del perfil seleccionado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="250"/>
        <source>Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="261"/>
        <source>Usar en el formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="262"/>
        <source>Guardar el formulario como perfil…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="263"/>
        <source>Duplicar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="264"/>
        <source>Renombrar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="265"/>
        <source>Eliminar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="278"/>
        <source>Importar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="279"/>
        <source>Exportar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="280"/>
        <source>Cerrar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="335"/>
        <source>Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="342"/>
        <source>No se pudo leer tu archivo de perfiles (revisa sus permisos). Solo se muestran los de fábrica y no se guardará nada nuevo hasta que se pueda leer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="350"/>
        <source>Tu archivo de perfiles estaba dañado. Se guardó una copia («{copia}») y se empezó con la lista vacía.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="357"/>
        <source>Se descartó 1 campo no válido del archivo de perfiles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="360"/>
        <source>Se descartaron %n campos no válidos del archivo de perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="387"/>
        <source>Este perfil no tiene descripción.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="417"/>
        <source>Duplicar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="418"/>
        <source>Duplicar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="420"/>
        <source>Copia de {nombre}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="432"/>
        <source>Se creó «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="444"/>
        <source>Renombrar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="445"/>
        <source>Guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="460"/>
        <source>Se cambió el nombre a «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="473"/>
        <source>Eliminar perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="475"/>
        <source>¿Eliminar el perfil «{nombre}»? Los lotes que ya guardaste no cambian.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="477"/>
        <source>Eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="478"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="487"/>
        <source>Se eliminó «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="501"/>
        <source>perfiles-proxlaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="509"/>
        <source>Exportando…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="524"/>
        <source>Se exportó 1 perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="526"/>
        <source>Se exportaron %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="549"/>
        <source>Leyendo el archivo…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="582"/>
        <source>Se importó 1 perfil.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="584"/>
        <source>Se importaron %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
</context>
<context>
    <name>FormularioVM</name>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="124"/>
        <source>General</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="128"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="476"/>
        <source>Número de máquina (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="130"/>
        <source>por ejemplo srv-web-01</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="131"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="133"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="134"/>
        <source>Manual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="151"/>
        <source>Nodo destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="164"/>
        <source>Firmware</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="166"/>
        <source>SeaBIOS (clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="167"/>
        <source>UEFI (OVMF)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="168"/>
        <source>Tipo de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="171"/>
        <source>Almacenamiento de UEFI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="182"/>
        <source>Cómputo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="187"/>
        <source>Sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="190"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="477"/>
        <source>Núcleos por socket</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="195"/>
        <source>Tipo de CPU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="200"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="478"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="202"/>
        <source>Predeterminado de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="203"/>
        <source>Activado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="204"/>
        <source>Desactivado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="205"/>
        <source>Ballooning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="209"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="480"/>
        <source>Memoria mínima (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="239"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="240"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="246"/>
        <source>Controlador SCSI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="258"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="388"/>
        <source>El almacenamiento de UEFI «{recurso}» no existe en el nodo «{nodo}». Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="483"/>
        <source>Tamaño del disco {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="487"/>
        <source>VLAN de {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="560"/>
        <source>Nodo elegido: {nodo} ({motivo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="373"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="598"/>
        <source>El almacenamiento «{recurso}» no existe en el nodo «{nodo}». Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="380"/>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="605"/>
        <source>La red «{recurso}» no existe en el nodo «{nodo}». Elige otra.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="632"/>
        <source>Automático (el del primer disco)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="663"/>
        <source>Este servidor no tiene almacenamiento para discos de máquinas virtuales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="752"/>
        <source>{n} procesadores virtuales en total</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>InformeLote</name>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="71"/>
        <source>{s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="72"/>
        <source>{m} min {s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="97"/>
        <source>Procesadores: {n} ({s} × {c})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="100"/>
        <source>Memoria: {m:g} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="103"/>
        <source>Arranque: {f}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="109"/>
        <source>Discos: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="111"/>
        <source>Discos: ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="116"/>
        <source>Redes: {r}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="118"/>
        <source>Redes: ninguna</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="127"/>
        <source>Deshacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="133"/>
        <location filename="../../interfaz/informe_lote.py" line="195"/>
        <location filename="../../interfaz/informe_lote.py" line="356"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="134"/>
        <location filename="../../interfaz/informe_lote.py" line="357"/>
        <source>VMID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="135"/>
        <location filename="../../interfaz/informe_lote.py" line="358"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="136"/>
        <location filename="../../interfaz/informe_lote.py" line="359"/>
        <source>Resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="137"/>
        <source>Detalle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="196"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="197"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="198"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="199"/>
        <source>Redes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="202"/>
        <source>ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="276"/>
        <source>Permisos no verificados: no se pudieron leer los permisos del usuario, así que Proxmox pudo rechazar alguna máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="289"/>
        <source>ProxLaunch — Simulación del lote {id}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="291"/>
        <source>ProxLaunch — Informe del lote {id}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="295"/>
        <source>SIMULACIÓN — no se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="297"/>
        <source>Fecha: {f}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="300"/>
        <source>Perfil: {p}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="303"/>
        <source>Versión de Proxmox: {v}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="309"/>
        <source>Servidor: clúster «{n}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="314"/>
        <source>Servidor: individual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="318"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="320"/>
        <source>Pedidas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="323"/>
        <source>Creadas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="326"/>
        <source>Creadas con avisos: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="331"/>
        <source>Con error: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="336"/>
        <source>Sin confirmar (no sabemos si se crearon): {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="348"/>
        <source>No enviadas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="353"/>
        <source>Máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="194"/>
        <location filename="../../interfaz/informe_lote.py" line="355"/>
        <source>N.º</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="360"/>
        <source>Duración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="361"/>
        <source>UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="369"/>
        <source>Detalle de las máquinas con problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="377"/>
        <source>    Código: {c}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="383"/>
        <source>    Detalles técnicos: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="390"/>
        <source>Configuración de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="401"/>
        <source>Avisos del plan</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="416"/>
        <source>Cómo encontrar estas máquinas en Proxmox: llevan las etiquetas «{e1}» y «{e2}{id}» (si el lote las activó) y sus números son {rangos}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="467"/>
        <source>Guardar informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="469"/>
        <source>Texto (*.txt)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModelosTabla</name>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="182"/>
        <location filename="../../interfaz/modelos_tabla.py" line="279"/>
        <source>Fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="184"/>
        <source>N.º</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="185"/>
        <location filename="../../interfaz/modelos_tabla.py" line="280"/>
        <location filename="../../interfaz/modelos_tabla.py" line="414"/>
        <location filename="../../interfaz/modelos_tabla.py" line="530"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="187"/>
        <location filename="../../interfaz/modelos_tabla.py" line="282"/>
        <location filename="../../interfaz/modelos_tabla.py" line="416"/>
        <location filename="../../interfaz/modelos_tabla.py" line="532"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="188"/>
        <location filename="../../interfaz/modelos_tabla.py" line="286"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="189"/>
        <location filename="../../interfaz/modelos_tabla.py" line="285"/>
        <source>Discos (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="195"/>
        <location filename="../../interfaz/modelos_tabla.py" line="283"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="196"/>
        <location filename="../../interfaz/modelos_tabla.py" line="284"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="247"/>
        <source>Fila {n}: {nombre}, número {vmid}, nodo {nodo}, {v} procesadores virtuales, {m} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="259"/>
        <source>Máquina {n}: {nombre}, número {vmid}, nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="287"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="313"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="332"/>
        <source>Fila {n}: {nombre}, {v} procesadores virtuales, {m} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="347"/>
        <source>Se creó aunque Proxmox tardó en responder.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="367"/>
        <source>Se creó, pero hay avisos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="378"/>
        <source>Se comprobó y no existe en Proxmox. Puedes reintentarla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="382"/>
        <source>Existe en Proxmox, pero no podemos asegurar que la creó este lote. No se eliminará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="387"/>
        <source>Quedó a medias; elimínala con «Deshacer…» o desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="413"/>
        <location filename="../../interfaz/modelos_tabla.py" line="529"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="417"/>
        <location filename="../../interfaz/modelos_tabla.py" line="533"/>
        <source>Detalle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="475"/>
        <source>{nombre}, número {vmid}, nodo {nodo}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="580"/>
        <source>{nombre}, número {vmid}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModelosTablaCsv</name>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="73"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/modelos_tabla_csv.py" line="212"/>
        <source>y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="242"/>
        <source>Incluir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="243"/>
        <source>Fila</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="244"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="245"/>
        <source>Perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="247"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="248"/>
        <source>Núcleos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="249"/>
        <source>Memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="250"/>
        <source>Disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="251"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="252"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="253"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="309"/>
        <source>auto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="312"/>
        <source>automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="367"/>
        <source>Una fila con error no se puede importar. Corrígela en el archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="372"/>
        <source>Incluir la fila {n}: no se puede, tiene un error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="380"/>
        <source>Incluir la fila {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="385"/>
        <source>sí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="387"/>
        <source>no</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="402"/>
        <source>Fila {n}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla_csv.py" line="408"/>
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
        <location filename="../../interfaz/vistas/lote_filas.py" line="27"/>
        <source>1 máquina desde el archivo «{origen}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/lote_filas.py" line="30"/>
        <source>%n máquinas desde el archivo «{origen}»</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="34"/>
        <source>1 máquina del lote «{origen}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/lote_filas.py" line="37"/>
        <source>%n máquinas del lote «{origen}»</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="65"/>
        <source>Título del lote por filas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="68"/>
        <source>Cada máquina trae su propia configuración. Para cambiar algo, corrige el archivo e impórtalo de nuevo, o quita las filas que no quieras.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="78"/>
        <source>Problemas de las filas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="83"/>
        <source>Máquinas del lote por filas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="90"/>
        <source>Ver resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="94"/>
        <source>Ver el resumen del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="97"/>
        <source>Revisar filas…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="100"/>
        <source>Revisar las filas del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="103"/>
        <source>Guardar lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="106"/>
        <source>Guardar el lote en un archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="109"/>
        <source>Quitar las filas seleccionadas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="112"/>
        <source>Quitar las filas seleccionadas del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/lote_filas.py" line="115"/>
        <location filename="../../interfaz/vistas/lote_filas.py" line="118"/>
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
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="136"/>
        <source>Nodo que reemplaza a «{valor}»:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="150"/>
        <source>Usar otro…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="151"/>
        <source>Usar otro en lugar de «{valor}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="155"/>
        <source>Disponibles en este servidor: {lista}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="160"/>
        <source>Este servidor no tiene ninguna alternativa.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="165"/>
        <source>Pasar a Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/lote_no_encaja.py" line="167"/>
        <source>Pasar a Automático en lugar del nodo «{valor}»</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PanelProgreso</name>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="37"/>
        <source>Progreso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="55"/>
        <source>Identificador de la tarea (UPID):</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="62"/>
        <source>Copiar UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="66"/>
        <source>Crear otra</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="70"/>
        <source>Seguir esperando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="73"/>
        <location filename="../../interfaz/vistas/progreso.py" line="186"/>
        <source>Comprobar ahora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="76"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="78"/>
        <source>Deshacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="81"/>
        <source>Crear sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="115"/>
        <source>Sin tareas en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso.py" line="184"/>
        <source>Comprobar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>PerfilesFabrica</name>
    <message>
        <location filename="../../interfaz/textos.py" line="1641"/>
        <source>Servidor pequeño</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1642"/>
        <source>Para pruebas y servicios ligeros.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1645"/>
        <source>Servidor mediano</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1646"/>
        <source>Para aplicaciones web.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1649"/>
        <source>Base de datos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1650"/>
        <source>Para bases de datos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1653"/>
        <source>Servidor grande</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1654"/>
        <source>Para cargas pesadas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1657"/>
        <source>Escritorio (hardware compatible)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1658"/>
        <source>Para sistemas que aún no traen controladores virtio: disco SATA y tarjeta de red Intel E1000.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1665"/>
        <source>Mínimo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1666"/>
        <source>Disco y red básicos, para probar.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ProgresoLote</name>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="70"/>
        <source>{t} de {n} terminadas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="76"/>
        <source>{c} con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="80"/>
        <source>{c} sin confirmar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="84"/>
        <source>{c} sin enviar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="87"/>
        <source>{c} en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="95"/>
        <source>Estado: {estado} ({codigo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="99"/>
        <source>Nodo: {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="105"/>
        <source>Motivo: {m}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="109"/>
        <source>Avisos: {a}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="113"/>
        <source>Código: {c}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="119"/>
        <source>Mensaje original: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="124"/>
        <source>Registro de la tarea:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="159"/>
        <source>Avance del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="164"/>
        <source>Mostrar solo problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="170"/>
        <source>Estado de cada máquina del lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="178"/>
        <source>Identificador de la tarea (UPID):</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="185"/>
        <source>UPID de la máquina seleccionada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="187"/>
        <source>Copiar UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="197"/>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="380"/>
        <source>Deshaciendo el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="202"/>
        <source>Estado de cada máquina eliminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="210"/>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="348"/>
        <source>Cancelar lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="213"/>
        <source>Decidir qué hacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="218"/>
        <source>Comprobar ahora</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="222"/>
        <source>Deshacer…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="224"/>
        <source>Reintentar pendientes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="226"/>
        <source>Informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="228"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="375"/>
        <source>Lote terminado (1 máquina)</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/progreso_lote.py" line="376"/>
        <source>Lote terminado (%n máquinas)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="382"/>
        <source>Comprobando las máquinas dudosas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="384"/>
        <source>Creando 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/progreso_lote.py" line="385"/>
        <source>Creando %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="341"/>
        <source>Dejar de esperar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="345"/>
        <source>Detener lo que falta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/progreso_lote.py" line="353"/>
        <source>Comprobar la dudosa</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/progreso_lote.py" line="357"/>
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
        <location filename="../../interfaz/vistas/resumen_lote.py" line="47"/>
        <source>Vas a crear una máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="48"/>
        <source>Vas a crear %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="54"/>
        <source>Crear de verdad esta máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="55"/>
        <source>Crear de verdad estas %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="59"/>
        <source>Crear 1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="60"/>
        <source>Crear %n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="65"/>
        <source>Reducir a 1</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="66"/>
        <source>Reducir a %n</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="70"/>
        <source>Quitar las filas que no caben</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="75"/>
        <source>Se van a crear {n} de las {total} filas del archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="82"/>
        <source>1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="83"/>
        <source>%n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="135"/>
        <source>Título del resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="148"/>
        <source>Máquinas que se van a crear</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="160"/>
        <source>Entiendo el riesgo de sobreasignar espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="163"/>
        <source>Confirmo que entiendo el riesgo de sobreasignar espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="173"/>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="177"/>
        <source>Nodo de destino para el reintento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="183"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="185"/>
        <source>Copiar resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="186"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="189"/>
        <source>Informe de la simulación…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="195"/>
        <source>Quitar del lote las filas que no caben en el servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="207"/>
        <source>Filas con el número de máquina ocupado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="212"/>
        <source>Simular</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="214"/>
        <source>Hace todas las comprobaciones y muestra lo que se enviaría, sin crear nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="316"/>
        <source>Los mismos nodos de antes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="335"/>
        <source>Preparando el resumen…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="343"/>
        <source>No se pudo preparar el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="346"/>
        <source>No se pudo consultar el servidor. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="399"/>
        <source>Puede haber otras máquinas con esos nombres que tú no puedes ver.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="425"/>
        <source>SIMULACIÓN — no se creó nada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="427"/>
        <source>Simulado con compatibilidad de Proxmox {forzada} (el servidor es {detectada})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="447"/>
        <source>Totales: {n}, {v} procesadores virtuales, {m:g} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="454"/>
        <source>«{s}» (compartido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="458"/>
        <source>«{s}» en {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="463"/>
        <source>Espacio en {donde}: {pedido} GiB de {libre} GiB libres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="478"/>
        <source>Reparto:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="484"/>
        <source>Se saltaron los números {rangos} (ya los usa otra máquina).</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="507"/>
        <source>… y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="531"/>
        <source>No caben las filas: {filas}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="547"/>
        <source>Fila {n}: el número {vmid} ya lo usa otra máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="552"/>
        <source>Asignar automáticamente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="555"/>
        <source>Asignar un número de máquina automático a la fila {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="567"/>
        <source>Asignar automáticamente a las %n filas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="616"/>
        <source>Corrige los errores marcados para poder crear las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="620"/>
        <source>Marca la casilla para confirmar que entiendes el riesgo de sobreasignar.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ResumenVM</name>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="31"/>
        <location filename="../../interfaz/vistas/resumen.py" line="186"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="32"/>
        <location filename="../../interfaz/vistas/resumen.py" line="187"/>
        <source>Número de máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="33"/>
        <location filename="../../interfaz/vistas/resumen.py" line="188"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="34"/>
        <source>Sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="35"/>
        <source>Núcleos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="36"/>
        <location filename="../../interfaz/vistas/resumen.py" line="191"/>
        <source>Memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="37"/>
        <source>Ballooning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="38"/>
        <source>Controlador SCSI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="39"/>
        <source>Almacenamiento de UEFI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="40"/>
        <source>Disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="41"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="42"/>
        <source>Origen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="52"/>
        <source>Tipo de CPU: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="59"/>
        <source>Ballooning activado, memoria mínima {valor} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="64"/>
        <source>Ballooning desactivado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="67"/>
        <source>Controlador SCSI: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="73"/>
        <source>UEFI se guarda en: {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="83"/>
        <source>conexión {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="89"/>
        <source>formato {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="94"/>
        <source>sin discard</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="96"/>
        <source>sin SSD</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="98"/>
        <source>sin IO Thread</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="101"/>
        <source>Disco {n}: {cambios}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="108"/>
        <source>Red {n}: tarjeta {valor}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="121"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="130"/>
        <location filename="../../interfaz/vistas/resumen.py" line="157"/>
        <source>Crear máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="155"/>
        <source>Ver resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="189"/>
        <source>Arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="190"/>
        <source>Procesadores</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="192"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="193"/>
        <source>Redes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="194"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="195"/>
        <source>Sin red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="206"/>
        <source>SeaBIOS (clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="208"/>
        <source>{n} procesadores virtuales en total</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="212"/>
        <source>{valor} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="220"/>
        <source>{etiqueta}: {tam} GiB en {storage}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="238"/>
        <source>Opciones avanzadas que se aplicarán (ocultas en modo básico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="249"/>
        <source>Para crear la máquina hay que corregir:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="263"/>
        <source>Corrige los datos marcados para poder crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="283"/>
        <source>Esta máquina pide más núcleos de los que tiene el servidor ({n} en el nodo).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen.py" line="290"/>
        <source>Esta máquina pide más memoria de la que tiene libre el servidor ({valor} GiB libres en el nodo).</source>
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
        <location filename="../../interfaz/vistas/selector_perfil.py" line="196"/>
        <source>Personalizado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="201"/>
        <source>{perfil} (modificado)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/selector_perfil.py" line="222"/>
        <source>Guardar cambios en el perfil «{nombre}»</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>TablaDiscos</name>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="48"/>
        <source>{id} ({tipo}, {libre:g} GiB libres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="52"/>
        <source>Inactivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="58"/>
        <source>{id} (no existe)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="86"/>
        <source>Quitar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="131"/>
        <source>Disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="134"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="137"/>
        <source>Tamaño (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="138"/>
        <source>Conexión (bus)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="139"/>
        <source>Formato</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="140"/>
        <source>Discard</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="141"/>
        <source>SSD</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="142"/>
        <source>IO Thread</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="154"/>
        <source>Agregar disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="321"/>
        <source>Elige un almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="426"/>
        <source>Automático (qcow2)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="436"/>
        <source>(automático, raw)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>TablaRedes</name>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="42"/>
        <source>{id} (no existe)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="63"/>
        <source>Sin VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="64"/>
        <source>Quitar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="92"/>
        <source>Interfaz</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="93"/>
        <source>Red (bridge)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="94"/>
        <source>Tarjeta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="95"/>
        <source>VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="105"/>
        <source>Agregar interfaz</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="155"/>
        <source>El nodo no tiene redes (bridges) disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="250"/>
        <source>Elige una red</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Textos</name>
    <message>
        <location filename="../../interfaz/textos.py" line="57"/>
        <source>este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="59"/>
        <location filename="../../interfaz/textos.py" line="69"/>
        <source>esa máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="61"/>
        <source>ese nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="63"/>
        <location filename="../../interfaz/textos.py" line="224"/>
        <source>un campo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="65"/>
        <source>una versión desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="71"/>
        <source>varias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="73"/>
        <source>ese almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="74"/>
        <source>un dato</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="104"/>
        <source>Proxmox respondió con un error que no conocemos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="112"/>
        <source>Las credenciales no son válidas. Revisa el usuario, el token o la contraseña.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="117"/>
        <source>Tu sesión expiró. Vuelve a iniciar sesión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="119"/>
        <source>El certificado del servidor cambió. Podría ser un cambio legítimo (renovación) o un intento de suplantación. Verifica con tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="126"/>
        <source>Primero hay que confiar en el certificado del servidor ({host}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="132"/>
        <source>Este usuario exige un método de segundo factor que ProxLaunch no admite. Usa un API Token.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="138"/>
        <source>El código no es correcto o ya venció. Espera al siguiente código e inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="145"/>
        <source>No sabemos si Proxmox recibió la orden de crear la máquina. Pulsa «Comprobar» antes de intentarlo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="154"/>
        <source>El nodo {nodo} no está disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="156"/>
        <location filename="../../interfaz/textos.py" line="345"/>
        <source>El nodo no está disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="161"/>
        <source>Proxmox no permitió crear la máquina. Lo más probable es que a tu usuario le falte {privilegio} en {ruta}. Pide a tu administrador que lo revise.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="170"/>
        <source>Tu usuario no tiene permiso para realizar esta acción. Falta {privilegio} en {ruta}. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="178"/>
        <source>Tu usuario no tiene permiso para realizar esta acción. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="186"/>
        <source>El número {vmid} ya lo usa otra máquina. Prueba con {siguiente}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="192"/>
        <source>El número {vmid} ya lo usa otra máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="198"/>
        <source>No hay espacio suficiente en «{storage}» para crear el disco. Libera espacio o elige otro almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="207"/>
        <source>Ningún nodo tiene {requerido_gib} GiB libres en un almacenamiento para discos. Reduce el tamaño de los discos o libera espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="214"/>
        <source>No hay espacio suficiente para crear el disco. Libera espacio o elige otro almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="220"/>
        <location filename="../../interfaz/textos.py" line="542"/>
        <source>La tarea sigue en marcha en Proxmox, no sabemos si terminó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="226"/>
        <source>Proxmox no entendió el valor de {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="232"/>
        <source>Proxmox rechazó el valor de {campo}: {mensaje}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="238"/>
        <source>El formulario tiene datos que hay que corregir antes de crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="242"/>
        <source>Proxmox rechazó el valor de {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="245"/>
        <source>ProxLaunch requiere Proxmox VE {minima} o superior (el servidor tiene {version})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="255"/>
        <source>Proxmox dijo que la tarea terminó, pero la máquina {vmid} no aparece en el nodo {nodo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="265"/>
        <source>«{recurso}» ya no existe en el nodo. Actualiza y elige de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="271"/>
        <source>Ese elemento ya no existe. Actualiza y elige de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="275"/>
        <source>Proxmox no devolvió el identificador de la tarea</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="279"/>
        <location filename="../../interfaz/textos.py" line="481"/>
        <source>No hay un llavero disponible en este equipo; las credenciales no se guardarán</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="298"/>
        <source>No se pudo contactar con ninguno de los servidores del perfil:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="309"/>
        <source>No se pudo contactar con el servidor ({destino})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="314"/>
        <source>El servidor no responde</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="319"/>
        <source>no respondió a tiempo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="321"/>
        <source>conexión rechazada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="322"/>
        <source>no respondió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="333"/>
        <source>El nombre solo puede tener letras sin acentos, números y guiones, y no puede empezar ni terminar con guion.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="339"/>
        <source>El número de máquina debe estar entre 100 y 999999999.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="348"/>
        <source>Elige entre 1 y 4 sockets.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="349"/>
        <source>Elige entre 1 y 128 núcleos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="352"/>
        <source>La memoria mínima no puede superar a la memoria total.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="355"/>
        <source>La memoria debe ser de al menos 16 MiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="359"/>
        <source>Ese tipo de conexión admite como máximo {maximo} discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="364"/>
        <source>Elige un tipo de conexión de disco válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="366"/>
        <source>El tamaño debe ser un número entero de GiB, mínimo 1.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="370"/>
        <source>Este almacenamiento solo admite formato raw.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="372"/>
        <source>El controlador de discos no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="374"/>
        <source>IO Thread necesita el bus VirtIO o SCSI con controlador virtio-scsi-single.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="378"/>
        <source>La emulación SSD no está disponible en el bus VirtIO.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="382"/>
        <source>Este tipo de conexión no admite liberar el espacio sin usar (discard).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="387"/>
        <source>El disco pide {pedido_gib} GiB y «{storage}» solo tiene {libre_gib} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="395"/>
        <source>Los discos piden {pedido_gib} GiB y «{storage}» tiene {libre_gib} GiB libres. Este almacenamiento solo ocupa el espacio a medida que se usa, así que puedes continuar, pero conviene vigilar el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="404"/>
        <source>La VLAN debe estar entre 1 y 4094.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="406"/>
        <source>El nodo no tiene redes (bridges) disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="410"/>
        <source>La red «{bridge}» no existe en el nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="415"/>
        <source>El modelo de tarjeta de red no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="418"/>
        <source>UEFI necesita un almacenamiento para guardar su configuración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="421"/>
        <source>Ese almacenamiento no está disponible en el nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="425"/>
        <source>El token debe tener el formato usuario@realm!nombre=secreto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="429"/>
        <source>Escribe solo el nombre o la IP del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="431"/>
        <source>El origen del sistema no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="433"/>
        <source>Agrega al menos un disco o marca «Sin disco».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="435"/>
        <source>El tipo de CPU no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="437"/>
        <source>Una máquina admite como máximo 32 interfaces de red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="441"/>
        <source>El código tiene 6 números.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="468"/>
        <source>{privilegio} en {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="487"/>
        <source>Topología desconocida ({nodos} nodos): a tu usuario le falta el permiso Sys.Audit en «/» para ver el clúster. Puedes seguir trabajando.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="496"/>
        <location filename="../../interfaz/textos.py" line="1253"/>
        <source>Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="502"/>
        <source>A tu usuario le faltan permisos recomendados ({privilegios}). Algunas acciones podrían fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="511"/>
        <source>Este servidor tiene Proxmox VE {version}, más nuevo que la última versión que ProxLaunch ha probado. Puedes continuar, pero algo podría no funcionar como se espera.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="530"/>
        <source>Máquina {nombre} ({vmid}) creada en {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="536"/>
        <source>Creada con avisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="546"/>
        <source>Se perdió la conexión mientras se creaba la máquina; la tarea puede haber terminado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="551"/>
        <source>La máquina quedó parcialmente creada; elimínala desde Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="556"/>
        <source>Cancelado. La tarea pudo seguir en Proxmox; revisa si la máquina existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="560"/>
        <source>Cancelado. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="567"/>
        <location filename="../../interfaz/textos.py" line="835"/>
        <source>Validando datos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="569"/>
        <location filename="../../interfaz/textos.py" line="836"/>
        <source>Enviando a Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="571"/>
        <location filename="../../interfaz/textos.py" line="837"/>
        <source>Creando la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="573"/>
        <location filename="../../interfaz/textos.py" line="838"/>
        <source>Comprobando el resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="575"/>
        <source>Listo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="582"/>
        <source>es el único con espacio suficiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="584"/>
        <source>más memoria y espacio libres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="586"/>
        <source>misma memoria libre; se eligió el que tiene más espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="595"/>
        <source>Servidor nuevo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="597"/>
        <source>Certificado conocido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="599"/>
        <source>El certificado cambió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="600"/>
        <source>Sin verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="609"/>
        <source>Se perdió la conexión. Hay 1 máquina sin confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="612"/>
        <source>Se perdió la conexión. Hay %n máquinas sin confirmar.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="634"/>
        <source>El número {vmid} lo usó otra persona mientras tanto. Esta máquina no se creó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="648"/>
        <source>cancelaste el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="650"/>
        <source>el lote se detuvo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="652"/>
        <source>hubo un error que afectaba a todo el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="654"/>
        <source>el nodo no respondió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="655"/>
        <source>no se llegó a enviar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="663"/>
        <source>Ningún servidor puede alojar esta máquina. Revisa que el almacenamiento y la red existan en los nodos elegidos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="670"/>
        <source>No encontré {n} números de máquina libres a partir del {inicio}. Prueba con otro número inicial o con menos máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="676"/>
        <source>número inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="680"/>
        <source>Las máquinas necesitan {pedido} GiB en «{storage}» y solo hay {libre} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="689"/>
        <location filename="../../interfaz/textos.py" line="1071"/>
        <source>Caben {max}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="693"/>
        <source>No sabemos si «{nombre}» se creó. No se volverá a enviar: pulsa «Comprobar» para verlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="702"/>
        <source>No pudimos comprobar si «{nombre}» existe. Revisa la conexión y vuelve a comprobar antes de crearla otra vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="711"/>
        <source>Fallaron {n} máquinas seguidas por la misma causa: {causa} ¿Continuar o detener?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="718"/>
        <source>una causa desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="724"/>
        <source>Se perdió la conexión. Hay máquinas sin confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="730"/>
        <source>«{nombre}» no se envió ({motivo}). No existe en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="738"/>
        <source>Los datos del servidor cambiaron: {diferencia}. Revisa el resumen y confirma otra vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="744"/>
        <source>hay cambios</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="747"/>
        <source>Hay un lote en curso. Espera a que termine o cancélalo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="752"/>
        <location filename="../../interfaz/textos.py" line="1128"/>
        <source>Elige entre 1 y {max} máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="758"/>
        <source>Has forzado una versión más nueva que la del servidor ({detectada}); solo puedes simular.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="764"/>
        <source>otra</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="767"/>
        <source>Proxmox no aceptó la etiqueta de la máquina. No se creó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="771"/>
        <source>No se pudo eliminar «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="774"/>
        <source>Elimínala desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="777"/>
        <source>No eliminamos «{nombre}» porque no podemos asegurar que la creó este lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="785"/>
        <source>«{nombre}» está encendida. Apágala en Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="792"/>
        <source>«{nombre}» está protegida o bloqueada. Quita la protección en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="800"/>
        <source>Pueden haber quedado discos sueltos de «{nombre}»; revísalos en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="808"/>
        <source>No sabemos si se eliminó «{nombre}». Comprueba antes de reintentar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="815"/>
        <source>Error interno: se intentó escribir en modo simulación. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="823"/>
        <source>La máquina existe en Proxmox, pero no pudimos confirmar que la creó ProxLaunch: podría ser de otra persona con el mismo número. Verifícalo en Proxmox antes de hacer nada con ella. No se eliminará desde aquí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="834"/>
        <location filename="../../interfaz/textos.py" line="882"/>
        <source>Pendiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="839"/>
        <source>Lista</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="840"/>
        <source>Lista, con avisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="841"/>
        <location filename="../../interfaz/textos.py" line="1856"/>
        <source>Con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="842"/>
        <source>Quedó a medias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="843"/>
        <source>Sin confirmar (sigue en Proxmox)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="846"/>
        <source>No sabemos si se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="847"/>
        <source>No enviada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="848"/>
        <source>No se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="849"/>
        <source>Existe, sin confirmar de quién es</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="883"/>
        <source>Comprobando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="884"/>
        <source>Eliminando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="885"/>
        <source>Eliminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="886"/>
        <source>Ya no existía</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="887"/>
        <source>No se pudo eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="888"/>
        <source>No se tocó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="889"/>
        <source>No sabemos si se eliminó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="890"/>
        <source>No se procesó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="915"/>
        <source>es el único nodo disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="917"/>
        <source>lo elegiste tú</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="919"/>
        <source>Equilibrado: más memoria libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="921"/>
        <source>Equilibrado: más espacio libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="923"/>
        <source>Por turnos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="930"/>
        <source>El lote se detuvo por un problema general</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="932"/>
        <source>El lote se detuvo: el mismo error se repite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="933"/>
        <source>El lote se detuvo: se perdió la conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="939"/>
        <location filename="../../interfaz/textos.py" line="970"/>
        <source>No se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="941"/>
        <source>No se envió: no existe en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="943"/>
        <source>No se creó: no hay nada que eliminar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="945"/>
        <source>Se encontró tras una comprobación, sin etiqueta que la ate a este lote: no podemos asegurar que sea suya.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="951"/>
        <source>Falló y no se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="953"/>
        <source>Existe, pero no podemos asegurar que la creó este lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="962"/>
        <source>No sabemos si se creó: comprueba primero qué pasó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="967"/>
        <source>esta máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="996"/>
        <source>tiene el carácter «{caracter}», que no se admite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1003"/>
        <source>es demasiado largo (cada parte puede tener hasta 63 caracteres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1006"/>
        <source>no puede empezar ni terminar con guion o punto, ni tener partes vacías</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1016"/>
        <source>El número inicial debe estar entre 0 y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1024"/>
        <source>La numeración llegaría a {ultimo} y el máximo es {maximo}. Baja el número inicial o la cantidad.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1035"/>
        <source>El relleno debe estar entre 0 y {maximo} dígitos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1042"/>
        <source>El nombre «{nombre}» no es válido: {causa}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1051"/>
        <source>«{storage}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1053"/>
        <source>«{storage}» (compartido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1056"/>
        <source>«{storage}» del nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1061"/>
        <source>Las {n} máquinas necesitan {pedido} GiB en {lugar} y solo hay {libre} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1078"/>
        <source>«{nodo}» está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1081"/>
        <source>«{nodo}» no tiene el almacenamiento «{storage}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1088"/>
        <source>«{nodo}» no tiene un almacenamiento para la configuración de UEFI.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1095"/>
        <source>«{nodo}» no tiene la red «{bridge}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1098"/>
        <source>«{nodo}» no puede alojar esta configuración.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1106"/>
        <source>Fila {n}: {texto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1120"/>
        <source>El máximo por lote es {max} máquinas. Divide el trabajo en varios lotes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1134"/>
        <source>Escribe un prefijo para los nombres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1135"/>
        <source>El prefijo solo puede tener letras sin acentos, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1139"/>
        <source>Elige un guion o ningún separador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1143"/>
        <source>Los nombres del lote no pueden repetirse.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1146"/>
        <source>Ya existe una máquina llamada «{nombre}» (número {vmid}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1154"/>
        <source>El lote llegaría hasta el número {ultimo} y el máximo es {maximo}. Baja el número inicial o la cantidad.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1163"/>
        <source>El número inicial debe estar entre {minimo} y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1171"/>
        <source>No hay {n} números de máquina libres a partir del {inicio}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1181"/>
        <source>Estás pidiendo {pedido} GiB y en «{storage}» solo hay {libre} GiB libres: es más de {factor} veces lo que hay. Reduce las máquinas o el tamaño de los discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1193"/>
        <source>Estás pidiendo {pedido} GiB y solo hay {libre} GiB libres en «{storage}». Funciona mientras las máquinas no usen todo su disco; si se llena, todas las máquinas de ese almacenamiento pueden fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1211"/>
        <source>Cada máquina pide {vcpus} procesadores virtuales y «{nodo}» tiene {cpus_nodo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1220"/>
        <source>No se pudo leer la memoria libre de {nodos}; el reparto usa el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1230"/>
        <source>No se pudo leer la memoria libre de «{nodo}»; el reparto usa el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1237"/>
        <source>En «{nodo}» pides {pedido} GiB de memoria y hay {libre} GiB libres. Las máquinas se crean apagadas; el problema aparecerá al encenderlas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1247"/>
        <source>Elige al menos un nodo disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1249"/>
        <source>Se actualizaron los datos del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1261"/>
        <source>Proxmox no admite esa etiqueta: usa solo letras, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1269"/>
        <source>Máquina {n}: {texto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1279"/>
        <source>Ningún nodo tiene sitio para todas las máquinas con el espacio libre actual.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1294"/>
        <source> y </source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1304"/>
        <source>{n} MiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1306"/>
        <source>{n} KiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1307"/>
        <source>{n} bytes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1313"/>
        <source>Falta la columna «nombre».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1316"/>
        <source>Columnas reconocidas: {reconocidas}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1321"/>
        <source>La columna «{columna}» aparece dos veces.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1324"/>
        <source>Hay datos en columnas que no tienen encabezado (columnas {posiciones}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1333"/>
        <source>El archivo no existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1335"/>
        <source>No tienes permiso para leer ese archivo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1346"/>
        <source>El archivo tiene demasiadas columnas; el máximo es {max}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1352"/>
        <source>El archivo tiene %n columnas; el máximo es {max}.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1359"/>
        <source>Una celda tiene demasiado texto; el máximo es {max} caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1365"/>
        <source>(fila {fila})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1369"/>
        <source>El archivo tiene demasiadas filas; el máximo por lote es {max}. Divide el archivo en partes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1377"/>
        <source>El archivo tiene %n filas; el máximo por lote es {max}. Divide el archivo en partes.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1391"/>
        <source>no hay espacio en el disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1393"/>
        <source>no tienes permiso para escribir ahí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1395"/>
        <source>el archivo está abierto en otro programa</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1397"/>
        <source>la ruta es demasiado larga</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1399"/>
        <source>ocurrió un error al escribir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1400"/>
        <source>No se pudo guardar el archivo: {motivo}. No se cambió nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1412"/>
        <source>no es un archivo normal</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1413"/>
        <source>No se puede abrir este archivo: {motivo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1418"/>
        <source>No se puede abrir este archivo: tiene demasiados elementos (máximo {limite}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1424"/>
        <source>No se puede abrir este archivo: es demasiado grande (límite {limite}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1428"/>
        <source>Este archivo no es un archivo de ProxLaunch del tipo que buscas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1433"/>
        <source>Parece un archivo de perfiles de máquina; usa «Importar perfiles».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1437"/>
        <source>Parece un archivo de lote guardado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1442"/>
        <source>Este archivo lo creó una versión más nueva de ProxLaunch. Actualiza la aplicación para abrirlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1451"/>
        <source>El archivo está dañado o tiene datos no válidos: {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1456"/>
        <source>El archivo está dañado o no tiene un formato válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1460"/>
        <source>No se pudo leer el archivo. Si está abierto en otro programa (como Excel), ciérralo o guarda una copia.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1472"/>
        <source>Hay unas comillas sin cerrar en la fila {fila}. Revisa el archivo o guárdalo de nuevo como «CSV UTF-8» desde Excel.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1480"/>
        <source>No pude leer el archivo CSV (fila {fila}). Guárdalo como «CSV UTF-8» desde Excel.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1489"/>
        <source>El archivo no tiene máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1494"/>
        <source>el valor «{valor}» no es válido. Ejemplo: {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1501"/>
        <location filename="../../interfaz/textos.py" line="1994"/>
        <source>Fila {fila}, columna «{columna}»: {detalle}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1506"/>
        <source>No existe el perfil «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1509"/>
        <source>Perfiles disponibles: {disponibles}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1513"/>
        <source>Los perfiles de fábrica no se pueden cambiar. Duplícalo para hacer tu propia versión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1518"/>
        <source>Tus perfiles se crearon con una versión más nueva de ProxLaunch; no se pueden modificar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1536"/>
        <source>Este lote no encaja en este servidor: {detalle}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1547"/>
        <source>El perfil pedía la red «{pedido}», que no existe en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1551"/>
        <source>El perfil pedía el almacenamiento de UEFI «{pedido}», que no existe en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1556"/>
        <source>El perfil pedía el almacenamiento «{pedido}», que no existe en «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1561"/>
        <source>Se usó «{usado}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1565"/>
        <source>Elige uno antes de crear.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1575"/>
        <location filename="../../interfaz/textos.py" line="1776"/>
        <source>Escribe un nombre de 1 a {maximo} caracteres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1580"/>
        <source>Ya existe un perfil con ese nombre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1583"/>
        <source>Llegaste al máximo de {max} perfiles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1590"/>
        <source>La descripción no es válida: máximo {maximo} caracteres y sin caracteres de control.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1598"/>
        <source>El texto no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1600"/>
        <location filename="../../interfaz/textos.py" line="1794"/>
        <source>Parece un token de acceso. No lo escribas aquí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1604"/>
        <location filename="../../interfaz/textos.py" line="1929"/>
        <source>Falta el nombre.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1609"/>
        <source>Las filas {filas} tienen el mismo número de máquina «{vmid}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1616"/>
        <source>Las filas {filas} tienen el mismo nombre «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1624"/>
        <source>Este perfil requiere Proxmox {version} o superior.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1630"/>
        <source>El tipo de CPU «host» impide mover la máquina entre nodos con procesadores distintos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1701"/>
        <source>falta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1702"/>
        <source>tipo de dato incorrecto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1703"/>
        <source>fuera de rango</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1704"/>
        <source>longitud no válida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1705"/>
        <source>valor no admitido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1706"/>
        <source>texto no válido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1709"/>
        <source>parece un token de acceso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1712"/>
        <source>hay demasiados</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1713"/>
        <source>está repetido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1731"/>
        <source>Se ignoró 1 campo que ProxLaunch no conoce.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1734"/>
        <source>Se ignoraron %n campos que ProxLaunch no conoce.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1738"/>
        <source>El archivo traía datos que parecen una credencial. No se usaron. Si eran reales, cámbialas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1744"/>
        <source>El archivo era de la versión {desde} del formato y se convirtió a la {hasta}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1749"/>
        <source>La columna «{columna}» no se usa y se ignoró.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1753"/>
        <source>En la columna «{columna}» había números sin unidad: se entendieron como GiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1758"/>
        <source>En la columna «{columna}» se usó la coma como separador decimal.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1761"/>
        <source>En la columna «{columna}», «GB» se tomó como GiB (1 GB = 1024 MiB).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1780"/>
        <source>Ya existe un perfil con ese nombre. Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1784"/>
        <source>El identificador del perfil no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1786"/>
        <source>Llegaste al máximo de {maximo} perfiles. Elimina alguno para crear otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1790"/>
        <source>El texto de «{campo}» no es válido. No uses caracteres especiales.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1814"/>
        <source>y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1823"/>
        <source>1 núcleo</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1825"/>
        <source>%n núcleos</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1829"/>
        <source>sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1831"/>
        <source>1 disco de {gib} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="1835"/>
        <source>%n discos</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1837"/>
        <source> ({gib} GiB en total)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1853"/>
        <source>Correcta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1855"/>
        <source>Con aviso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1867"/>
        <source>«{valor}» mezcla punto y coma. Escribe el número sin separador de miles, por ejemplo 1000.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1872"/>
        <source>¿Quisiste decir mil o uno? Escribe {mil} o {uno}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1881"/>
        <source>El texto de «{columna}» no es válido. No uses caracteres especiales.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1886"/>
        <source>Indicaste un almacenamiento, pero la fila no tiene disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1890"/>
        <source>Indicaste un almacenamiento, pero falta el tamaño de ese disco.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1893"/>
        <source>«{valor}» no es un valor válido. Valores válidos: {validos}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1920"/>
        <source>Hay más de un perfil llamado «{nombre}». Escribe el nombre exacto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1924"/>
        <source>No existe el perfil «{nombre}». Perfiles disponibles: {disponibles}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1933"/>
        <source>Pides {gib} GiB de memoria. ¿Querías MiB?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1938"/>
        <source>Las filas {filas} tienen el mismo número de máquina «{valor}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1941"/>
        <source>Las filas {filas} tienen el mismo nombre «{valor}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1945"/>
        <source>Parece una fila de ejemplo de la plantilla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1947"/>
        <source>«{valor}» no es un número. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1951"/>
        <source>«{valor}» no es un número entero. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1955"/>
        <source>«{valor}» no da una cantidad entera de MiB. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1960"/>
        <source>«{valor}» no da una cantidad entera de GiB. Escribe, por ejemplo, {ejemplo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1965"/>
        <source>«{unidad}» no es una unidad válida. Usa {validas}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1973"/>
        <source>Ningún nodo del servidor puede alojar esta máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1978"/>
        <source>El nodo no existe en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1980"/>
        <source>El nodo está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1997"/>
        <source>Fila {fila}: {detalle}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2015"/>
        <source>El almacenamiento «{valor}» no existe en este servidor o no admite discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2019"/>
        <source>El almacenamiento «{valor}» para la configuración UEFI no existe en este servidor o no admite discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2025"/>
        <source>La red «{valor}» no existe en este servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="2028"/>
        <source>El nodo «{valor}» no existe o está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>VentanaPrincipal</name>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="284"/>
        <source>ahora hay errores que impiden crear el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="295"/>
        <source>el número {a} ya no está libre (ahora se usa el {b})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="301"/>
        <source>«{n}» pasa de {a} a {b}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="309"/>
        <source>y %n cambios más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="319"/>
        <source>ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="423"/>
        <location filename="../../interfaz/ventana_principal.py" line="792"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="444"/>
        <source>Conecta con tu servidor Proxmox para empezar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="449"/>
        <location filename="../../interfaz/ventana_principal.py" line="532"/>
        <source>Conectar...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="465"/>
        <source>Actualizar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="469"/>
        <source>Reintentar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="485"/>
        <source>Avisos del archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="531"/>
        <source>&amp;Archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="535"/>
        <source>Cerrar sesión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="537"/>
        <source>Salir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="540"/>
        <source>Ver el último lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="547"/>
        <source>&amp;Lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="548"/>
        <source>Abrir lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="551"/>
        <source>Guardar lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="554"/>
        <source>Guardar lote como…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="557"/>
        <source>Importar desde CSV…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="559"/>
        <source>Descargar plantilla CSV…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="561"/>
        <source>Guardar el informe del lote como CSV…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="570"/>
        <source>&amp;Perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="571"/>
        <source>Guardar como perfil de máquina…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="573"/>
        <source>Administrar perfiles…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="578"/>
        <source>&amp;Ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="579"/>
        <source>Tema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="583"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="584"/>
        <source>Oscuro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="585"/>
        <source>Claro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="593"/>
        <source>Modo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="597"/>
        <source>Básico</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="598"/>
        <source>Avanzado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="607"/>
        <source>A&amp;yuda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="608"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="610"/>
        <source>Acerca de ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="716"/>
        <source>Esa clave de recuperación ya no se puede volver a usar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="722"/>
        <source>Conectado a {b} ({a} no respondió)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="726"/>
        <source>Conectado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="827"/>
        <source>No se pudo leer el archivo de huellas (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="831"/>
        <source>Se dañó el archivo de huellas; se recuperaron {n} servidores. Los demás tendrás que confirmarlos de nuevo comparando la huella con tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="838"/>
        <source>No se pudo leer el archivo de perfiles (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="842"/>
        <source>El archivo de perfiles estaba dañado: se guardó una copia y se empezó uno nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="847"/>
        <source>No se pudo leer el archivo de preferencias (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="867"/>
        <source>Buscando nodos, almacenamientos y redes...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="879"/>
        <source>No se pudo leer el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="888"/>
        <source>{n} nodo(s) encontrados.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="896"/>
        <source>Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="914"/>
        <source>No se pudo leer el nodo {nodos}: aparece como «Sin conexión».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1183"/>
        <source>El servidor no permite poner etiquetas a las máquinas. Puedes crearla sin etiquetas; después, «Deshacer» solo podrá eliminarla si el nombre coincide.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1227"/>
        <source>Etiquetas desactivadas. Pulsa «Crear» para crear la máquina sin ellas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1242"/>
        <source>Todavía no sabemos si se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1244"/>
        <source>No hemos podido confirmar si la máquina se creó. Si vuelves al formulario y la creas otra vez, podrías duplicarla. ¿Volver de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1278"/>
        <source>Comprobando si la máquina existe...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1294"/>
        <source>Comprobando la tarea...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1296"/>
        <source>Esperando a que termine la tarea...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1337"/>
        <source>La máquina sí se creó. Verifica en Proxmox que quedó como esperabas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1345"/>
        <source>No se creó; puedes intentarlo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1354"/>
        <source>No se pudo comprobar si la máquina existe. Revisa la conexión e inténtalo de nuevo antes de volver a crearla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1401"/>
        <source>El último lote se cerró sin terminar. Informe: {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1647"/>
        <source>Confirmar el envío</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="1648"/>
        <source>Se enviarán %n máquinas a Proxmox. ¿Continuar?</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1654"/>
        <source>Crear las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1655"/>
        <location filename="../../interfaz/ventana_principal.py" line="1809"/>
        <location filename="../../interfaz/ventana_principal.py" line="2526"/>
        <location filename="../../interfaz/ventana_principal.py" line="2613"/>
        <location filename="../../interfaz/ventana_principal.py" line="2686"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1801"/>
        <source>Seguir sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1802"/>
        <source>Se detendrá este lote y se armará uno nuevo con las máquinas que faltan, sin etiquetas. Después, «Deshacer» solo podrá eliminar las máquinas que ProxLaunch confirme que creó él mismo. Antes de crear nada verás el resumen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1808"/>
        <source>Preparar el lote sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1819"/>
        <source>Esperando a que terminen las tareas en curso para continuar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1838"/>
        <location filename="../../interfaz/ventana_principal.py" line="1844"/>
        <source>Cancelar el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1839"/>
        <source>Las máquinas que ya se enviaron seguirán creándose en Proxmox y se esperará su resultado. Las demás no se enviarán.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1845"/>
        <source>Seguir creando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1889"/>
        <source>El lote terminó de forma inesperada: {m}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1908"/>
        <source>Reconecta para continuar con las máquinas que faltan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1910"/>
        <source>Reconecta para continuar con el lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2203"/>
        <source>Eliminando las máquinas elegidas…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2354"/>
        <source>Hay máquinas sin confirmar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2355"/>
        <source>No sabemos si algunas máquinas se crearon. Si vuelves y repites el lote, podrías duplicarlas. ¿Volver de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2360"/>
        <source>Volver de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2361"/>
        <source>Quedarme aquí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2426"/>
        <source>No se pudo leer el archivo de perfiles de máquina (permisos): solo verás los perfiles de fábrica.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2433"/>
        <source>El archivo de perfiles de máquina estaba dañado: se guardó una copia y se empezó uno nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="2442"/>
        <source>Se omitieron %n perfiles dañados del archivo de perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2523"/>
        <source>Cambiar de perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2524"/>
        <source>Se reemplazarán los ajustes de hardware que cambiaste.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2525"/>
        <source>Reemplazar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2544"/>
        <source>Perfil «{nombre}» aplicado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2593"/>
        <source>Perfil «{nombre}» guardado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2608"/>
        <source>Guardar cambios en el perfil</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2609"/>
        <source>Se reemplazará el hardware guardado en el perfil «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2612"/>
        <source>Guardar cambios</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2627"/>
        <source>Perfil «{nombre}» actualizado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2681"/>
        <source>Cambios sin guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2682"/>
        <source>¿Guardar el lote antes de continuar?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2683"/>
        <source>Si no lo guardas, se perderán los cambios del lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2684"/>
        <source>Guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2685"/>
        <source>No guardar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2748"/>
        <source>No se puede guardar el lote: {campos} no es un número. Corrígelo e inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2794"/>
        <source>Lote guardado en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2810"/>
        <source>Leyendo el lote…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2850"/>
        <source>Lote «{nombre}» cargado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2863"/>
        <source>El lote se guardó con Proxmox {guardada}; este servidor tiene {actual}. Algunas opciones podrían no estar disponibles.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2960"/>
        <source>Corrige los errores marcados para poder ver el resumen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3100"/>
        <source>No se pudieron importar las filas elegidas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="3121"/>
        <source>Se importaron %n máquinas desde «{archivo}»</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3132"/>
        <source>Plantilla guardada en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3150"/>
        <source>Informe guardado en «{archivo}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3204"/>
        <source>Hay un «Deshacer» en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3205"/>
        <source>Se están eliminando máquinas. Si cierras, ProxLaunch dejará de esperar: las eliminaciones ya enviadas seguirán en Proxmox y el resto no se hará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3183"/>
        <source>Hay un lote en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3184"/>
        <source>Hay un lote en curso ({x} de {n} terminadas). Si cierras, las tareas ya enviadas seguirán en Proxmox, pero ProxLaunch no enviará el resto ni podrá deshacer lo creado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3190"/>
        <location filename="../../interfaz/ventana_principal.py" line="3210"/>
        <source>Cerrar de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3191"/>
        <location filename="../../interfaz/ventana_principal.py" line="3211"/>
        <source>Seguir en ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3224"/>
        <source>Hay una máquina en creación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3226"/>
        <source>Se está creando una máquina. Si cierras ProxLaunch, la tarea sigue ejecutándose en el servidor Proxmox, pero ya no verás su resultado. ¿Cerrar de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="3240"/>
        <source>Cerrando...</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>_DialogoExportar</name>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="130"/>
        <source>Exportar perfiles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="136"/>
        <source>Se exportará el perfil «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="138"/>
        <source>Se exportarán %n perfiles.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="140"/>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="143"/>
        <source>Incluir los nombres de almacenamiento y red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="150"/>
        <source>Normalmente conviene dejarlo sin marcar: esos nombres son de tu servidor y casi nunca existen en el de otra persona.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="159"/>
        <source>El archivo nunca incluye contraseñas, tokens, direcciones ni nombres de usuario.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="166"/>
        <source>Elegir dónde guardar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/dialogos/perfiles_maquina.py" line="167"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
</context>
</TS>
