<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="es" sourcelanguage="es">
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
        <source>Si se corta la conexión justo al enviar una máquina, no se sabe si Proxmox llegó a crearla. ProxLaunch nunca la vuelve a enviar sola, porque podría duplicarla: usa «Comprobar» para ver si existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="288"/>
        <source>Rinde más pero impide mover la máquina entre nodos con procesadores distintos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="297"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="303"/>
        <source>Entra en la página web de tu Proxmox y ve a Datacenter → Permisos → Roles → Crear. Llama al rol «{rol}» y marca los privilegios de la lista de abajo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="308"/>
        <source>Ve a Datacenter → Permisos → Usuarios y crea un usuario para ProxLaunch (por ejemplo «proxlaunch@pve»), o elige uno que ya tengas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="313"/>
        <source>Ve a Datacenter → Permisos → Tokens de API → Añadir. Elige el usuario, escribe un nombre para el token (por ejemplo «lab») y pulsa Añadir. Copia el secreto que se muestra: solo aparece una vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="319"/>
        <source>Ve a Datacenter → Permisos → Añadir → Permiso de usuario (o de token). Ruta «/», elige el usuario o el token, rol «{rol}» y deja marcado «Propagar».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="324"/>
        <source>En ProxLaunch pega el token completo con el formato usuario@realm!nombre=secreto, por ejemplo proxlaunch@pve!lab=11111111-2222-3333-4444-555555555555.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="335"/>
        <source>Usa siempre un token con los permisos mínimos en lugar de root@pam: si el token se filtra, el daño es mucho menor y puedes revocarlo sin cambiar contraseñas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ayuda.py" line="340"/>
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
        <location filename="../../interfaz/vistas/bloque_lote.py" line="73"/>
        <source>Lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="99"/>
        <source>Cantidad</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="103"/>
        <source>Cantidad de máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="114"/>
        <source>por ejemplo srv-web</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="117"/>
        <source>Prefijo de los nombres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="121"/>
        <source>Prefijo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="127"/>
        <source>Vista previa de los nombres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="130"/>
        <source>Guion (-)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="131"/>
        <source>Ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="134"/>
        <source>Separador</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="142"/>
        <source>Número inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="150"/>
        <source>Relleno (dígitos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="156"/>
        <source>automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="159"/>
        <source>Número de máquina inicial (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="181"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="182"/>
        <source>Un nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="184"/>
        <source>Nodos elegidos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="193"/>
        <source>Nodo de destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="202"/>
        <source>Equilibrado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="205"/>
        <source>Por turnos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="208"/>
        <source>Algoritmo de reparto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="224"/>
        <source>Dónde crearlas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="229"/>
        <source>Reparto</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="244"/>
        <source>Etiquetar las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="327"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/bloque_lote.py" line="458"/>
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
    <name>FormularioVM</name>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="122"/>
        <source>General</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="126"/>
        <source>Número de máquina (VMID)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="128"/>
        <source>por ejemplo srv-web-01</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="129"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="131"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="132"/>
        <source>Manual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="149"/>
        <source>Nodo destino</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="162"/>
        <source>Firmware</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="164"/>
        <source>SeaBIOS (clásico)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="165"/>
        <source>UEFI (OVMF)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="166"/>
        <source>Tipo de arranque</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="169"/>
        <source>Almacenamiento de UEFI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="180"/>
        <source>Cómputo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="185"/>
        <source>Sockets</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="188"/>
        <source>Núcleos por socket</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="193"/>
        <source>Tipo de CPU</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="198"/>
        <source>Memoria (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="200"/>
        <source>Predeterminado de Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="201"/>
        <source>Activado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="202"/>
        <source>Desactivado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="203"/>
        <source>Ballooning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="207"/>
        <source>Memoria mínima (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="237"/>
        <source>Discos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="238"/>
        <source>Sin disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="244"/>
        <source>Controlador SCSI</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="256"/>
        <source>Red</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="452"/>
        <source>Nodo elegido: {nodo} ({motivo})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="490"/>
        <source>El almacenamiento «{recurso}» no existe en el nodo «{nodo}». Elige otro.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="497"/>
        <source>La red «{recurso}» no existe en el nodo «{nodo}». Elige otra.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="524"/>
        <source>Automático (el del primer disco)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="540"/>
        <source>Este servidor no tiene almacenamiento para discos de máquinas virtuales</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/formulario_vm.py" line="629"/>
        <source>{n} procesadores virtuales en total</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>InformeLote</name>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="70"/>
        <source>{s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="71"/>
        <source>{m} min {s} s</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="96"/>
        <source>Procesadores: {n} ({s} × {c})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="99"/>
        <source>Memoria: {m:g} GiB</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="102"/>
        <source>Arranque: {f}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="108"/>
        <source>Discos: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="110"/>
        <source>Discos: ninguno</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="115"/>
        <source>Redes: {r}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="117"/>
        <source>Redes: ninguna</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="126"/>
        <source>Deshacer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="132"/>
        <location filename="../../interfaz/informe_lote.py" line="238"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="133"/>
        <location filename="../../interfaz/informe_lote.py" line="239"/>
        <source>VMID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="134"/>
        <location filename="../../interfaz/informe_lote.py" line="240"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="135"/>
        <location filename="../../interfaz/informe_lote.py" line="241"/>
        <source>Resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="136"/>
        <source>Detalle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="158"/>
        <source>Permisos no verificados: no se pudieron leer los permisos del usuario, así que Proxmox pudo rechazar alguna máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="171"/>
        <source>ProxLaunch — Simulación del lote {id}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="173"/>
        <source>ProxLaunch — Informe del lote {id}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="177"/>
        <source>SIMULACIÓN — no se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="179"/>
        <source>Fecha: {f}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="182"/>
        <source>Perfil: {p}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="185"/>
        <source>Versión de Proxmox: {v}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="191"/>
        <source>Servidor: clúster «{n}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="196"/>
        <source>Servidor: individual</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="200"/>
        <source>Resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="202"/>
        <source>Pedidas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="205"/>
        <source>Creadas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="208"/>
        <source>Creadas con avisos: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="213"/>
        <source>Con error: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="218"/>
        <source>Sin confirmar (no sabemos si se crearon): {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="230"/>
        <source>No enviadas: {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="235"/>
        <source>Máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="237"/>
        <source>N.º</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="242"/>
        <source>Duración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="243"/>
        <source>UPID</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="251"/>
        <source>Detalle de las máquinas con problemas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="259"/>
        <source>    Código: {c}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="265"/>
        <source>    Detalles técnicos: {d}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="272"/>
        <source>Configuración de las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="280"/>
        <source>Avisos del plan</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="294"/>
        <source>Cómo encontrar estas máquinas en Proxmox: llevan las etiquetas «{e1}» y «{e2}{id}» (si el lote las activó) y sus números son {rangos}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="345"/>
        <source>Guardar informe</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/informe_lote.py" line="347"/>
        <source>Texto (*.txt)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ModelosTabla</name>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="162"/>
        <source>N.º</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="163"/>
        <location filename="../../interfaz/modelos_tabla.py" line="274"/>
        <location filename="../../interfaz/modelos_tabla.py" line="390"/>
        <source>Nombre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="165"/>
        <location filename="../../interfaz/modelos_tabla.py" line="276"/>
        <location filename="../../interfaz/modelos_tabla.py" line="392"/>
        <source>Nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="166"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="167"/>
        <source>Discos (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="195"/>
        <source>Máquina {n}: {nombre}, número {vmid}, nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="207"/>
        <source>Se creó aunque Proxmox tardó en responder.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="227"/>
        <source>Se creó, pero hay avisos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="238"/>
        <source>Se comprobó y no existe en Proxmox. Puedes reintentarla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="242"/>
        <source>Existe en Proxmox, pero no podemos asegurar que la creó este lote. No se eliminará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="247"/>
        <source>Quedó a medias; elimínala con «Deshacer…» o desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="273"/>
        <location filename="../../interfaz/modelos_tabla.py" line="389"/>
        <source>Estado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="277"/>
        <location filename="../../interfaz/modelos_tabla.py" line="393"/>
        <source>Detalle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="335"/>
        <source>{nombre}, número {vmid}, nodo {nodo}: {estado}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/modelos_tabla.py" line="440"/>
        <source>{nombre}, número {vmid}: {estado}</source>
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
        <location filename="../../interfaz/vistas/resumen_lote.py" line="71"/>
        <source>1 máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="72"/>
        <source>%n máquinas</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="120"/>
        <source>Título del resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="133"/>
        <source>Máquinas que se van a crear</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="145"/>
        <source>Entiendo el riesgo de sobreasignar espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="148"/>
        <source>Confirmo que entiendo el riesgo de sobreasignar espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="158"/>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="162"/>
        <source>Nodo de destino para el reintento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="168"/>
        <source>Volver al formulario</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="170"/>
        <source>Copiar resumen</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="171"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="174"/>
        <source>Informe de la simulación…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="178"/>
        <source>Simular</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="180"/>
        <source>Hace todas las comprobaciones y muestra lo que se enviaría, sin crear nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="273"/>
        <source>Los mismos nodos de antes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="292"/>
        <source>Preparando el resumen…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="300"/>
        <source>No se pudo preparar el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="303"/>
        <source>No se pudo consultar el servidor. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="353"/>
        <source>Puede haber otras máquinas con esos nombres que tú no puedes ver.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="375"/>
        <source>SIMULACIÓN — no se creó nada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="377"/>
        <source>Simulado con compatibilidad de Proxmox {forzada} (el servidor es {detectada})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="397"/>
        <source>Totales: {n}, {v} procesadores virtuales, {m:g} GiB de memoria</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="404"/>
        <source>«{s}» (compartido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="408"/>
        <source>«{s}» en {n}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="413"/>
        <source>Espacio en {donde}: {pedido} GiB de {libre} GiB libres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="428"/>
        <source>Reparto:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="434"/>
        <source>Se saltaron los números {rangos} (ya los usa otra máquina).</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/vistas/resumen_lote.py" line="450"/>
        <source>… y %n más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="487"/>
        <source>Corrige los errores marcados para poder crear las máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/resumen_lote.py" line="491"/>
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
        <location filename="../../interfaz/vistas/tabla_discos.py" line="81"/>
        <source>Quitar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="123"/>
        <source>Disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="126"/>
        <source>Almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="129"/>
        <source>Tamaño (GiB)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="130"/>
        <source>Conexión (bus)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="131"/>
        <source>Formato</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="132"/>
        <source>Discard</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="133"/>
        <source>SSD</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="134"/>
        <source>IO Thread</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="146"/>
        <source>Agregar disco</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="283"/>
        <source>Elige un almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="381"/>
        <source>Automático (qcow2)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_discos.py" line="391"/>
        <source>(automático, raw)</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>TablaRedes</name>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="55"/>
        <source>Sin VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="56"/>
        <source>Quitar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="84"/>
        <source>Interfaz</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="85"/>
        <source>Red (bridge)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="86"/>
        <source>Tarjeta</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="87"/>
        <source>VLAN</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="97"/>
        <source>Agregar interfaz</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="140"/>
        <source>El nodo no tiene redes (bridges) disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/vistas/tabla_redes.py" line="210"/>
        <source>Elige una red</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>Textos</name>
    <message>
        <location filename="../../interfaz/textos.py" line="41"/>
        <source>este servidor</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="43"/>
        <location filename="../../interfaz/textos.py" line="53"/>
        <source>esa máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="45"/>
        <source>ese nodo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="47"/>
        <location filename="../../interfaz/textos.py" line="208"/>
        <source>un campo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="49"/>
        <source>una versión desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="55"/>
        <source>varias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="57"/>
        <source>ese almacenamiento</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="58"/>
        <source>un dato</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="88"/>
        <source>Proxmox respondió con un error que no conocemos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="96"/>
        <source>Las credenciales no son válidas. Revisa el usuario, el token o la contraseña.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="101"/>
        <source>Tu sesión expiró. Vuelve a iniciar sesión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="103"/>
        <source>El certificado del servidor cambió. Podría ser un cambio legítimo (renovación) o un intento de suplantación. Verifica con tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="110"/>
        <source>Primero hay que confiar en el certificado del servidor ({host}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="116"/>
        <source>Este usuario exige un método de segundo factor que ProxLaunch no admite. Usa un API Token.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="122"/>
        <source>El código no es correcto o ya venció. Espera al siguiente código e inténtalo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="129"/>
        <source>No sabemos si Proxmox recibió la orden de crear la máquina. Pulsa «Comprobar» antes de intentarlo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="138"/>
        <source>El nodo {nodo} no está disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="140"/>
        <location filename="../../interfaz/textos.py" line="326"/>
        <source>El nodo no está disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="145"/>
        <source>Proxmox no permitió crear la máquina. Lo más probable es que a tu usuario le falte {privilegio} en {ruta}. Pide a tu administrador que lo revise.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="154"/>
        <source>Tu usuario no tiene permiso para realizar esta acción. Falta {privilegio} en {ruta}. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="162"/>
        <source>Tu usuario no tiene permiso para realizar esta acción. Pide a tu administrador este permiso o usa un token con permisos suficientes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="170"/>
        <source>El número {vmid} ya lo usa otra máquina. Prueba con {siguiente}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="176"/>
        <source>El número {vmid} ya lo usa otra máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="182"/>
        <source>No hay espacio suficiente en «{storage}» para crear el disco. Libera espacio o elige otro almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="191"/>
        <source>Ningún nodo tiene {requerido_gib} GiB libres en un almacenamiento para discos. Reduce el tamaño de los discos o libera espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="198"/>
        <source>No hay espacio suficiente para crear el disco. Libera espacio o elige otro almacenamiento.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="204"/>
        <location filename="../../interfaz/textos.py" line="520"/>
        <source>La tarea sigue en marcha en Proxmox, no sabemos si terminó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="210"/>
        <source>Proxmox no entendió el valor de {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="216"/>
        <source>Proxmox rechazó el valor de {campo}: {mensaje}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="222"/>
        <source>El formulario tiene datos que hay que corregir antes de crear la máquina.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="226"/>
        <source>Proxmox rechazó el valor de {campo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="229"/>
        <source>ProxLaunch requiere Proxmox VE {minima} o superior (el servidor tiene {version})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="239"/>
        <source>Proxmox dijo que la tarea terminó, pero la máquina {vmid} no aparece en el nodo {nodo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="249"/>
        <source>«{recurso}» ya no existe en el nodo. Actualiza y elige de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="255"/>
        <source>Ese elemento ya no existe. Actualiza y elige de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="259"/>
        <source>Proxmox no devolvió el identificador de la tarea</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="263"/>
        <location filename="../../interfaz/textos.py" line="459"/>
        <source>No hay un llavero disponible en este equipo; las credenciales no se guardarán</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="279"/>
        <source>No se pudo contactar con ninguno de los servidores del perfil:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="290"/>
        <source>No se pudo contactar con el servidor ({destino})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="295"/>
        <source>El servidor no responde</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="300"/>
        <source>no respondió a tiempo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="302"/>
        <source>conexión rechazada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="303"/>
        <source>no respondió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="314"/>
        <source>El nombre solo puede tener letras sin acentos, números y guiones, y no puede empezar ni terminar con guion.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="320"/>
        <source>El número de máquina debe estar entre 100 y 999999999.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="329"/>
        <source>Elige entre 1 y 4 sockets.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="330"/>
        <source>Elige entre 1 y 128 núcleos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="333"/>
        <source>La memoria mínima no puede superar a la memoria total.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="336"/>
        <source>La memoria debe ser de al menos 16 MiB.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="340"/>
        <source>Ese tipo de conexión admite como máximo {maximo} discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="345"/>
        <source>Elige un tipo de conexión de disco válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="347"/>
        <source>El tamaño debe ser un número entero de GiB, mínimo 1.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="351"/>
        <source>Este almacenamiento solo admite formato raw.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="353"/>
        <source>El controlador de discos no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="355"/>
        <source>IO Thread necesita el bus VirtIO o SCSI con controlador virtio-scsi-single.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="359"/>
        <source>La emulación SSD no está disponible en el bus VirtIO.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="363"/>
        <source>Este tipo de conexión no admite liberar el espacio sin usar (discard).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="368"/>
        <source>El disco pide {pedido_gib} GiB y «{storage}» solo tiene {libre_gib} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="376"/>
        <source>Los discos piden {pedido_gib} GiB y «{storage}» tiene {libre_gib} GiB libres. Este almacenamiento solo ocupa el espacio a medida que se usa, así que puedes continuar, pero conviene vigilar el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="385"/>
        <source>La VLAN debe estar entre 1 y 4094.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="387"/>
        <source>El nodo no tiene redes (bridges) disponibles</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="391"/>
        <source>La red «{bridge}» no existe en el nodo «{nodo}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="396"/>
        <source>El modelo de tarjeta de red no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="399"/>
        <source>UEFI necesita un almacenamiento para guardar su configuración</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="402"/>
        <source>Ese almacenamiento no está disponible en el nodo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="406"/>
        <source>El token debe tener el formato usuario@realm!nombre=secreto.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="410"/>
        <source>Escribe solo el nombre o la IP del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="412"/>
        <source>El origen del sistema no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="414"/>
        <source>Agrega al menos un disco o marca «Sin disco».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="416"/>
        <source>El tipo de CPU no es válido.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="418"/>
        <source>Una máquina admite como máximo 32 interfaces de red.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="422"/>
        <source>El código tiene 6 números.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="446"/>
        <source>{privilegio} en {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="465"/>
        <source>Topología desconocida ({nodos} nodos): a tu usuario le falta el permiso Sys.Audit en «/» para ver el clúster. Puedes seguir trabajando.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="474"/>
        <location filename="../../interfaz/textos.py" line="1215"/>
        <source>Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="480"/>
        <source>A tu usuario le faltan permisos recomendados ({privilegios}). Algunas acciones podrían fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="489"/>
        <source>Este servidor tiene Proxmox VE {version}, más nuevo que la última versión que ProxLaunch ha probado. Puedes continuar, pero algo podría no funcionar como se espera.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="508"/>
        <source>Máquina {nombre} ({vmid}) creada en {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="514"/>
        <source>Creada con avisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="524"/>
        <source>Se perdió la conexión mientras se creaba la máquina; la tarea puede haber terminado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="529"/>
        <source>La máquina quedó parcialmente creada; elimínala desde Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="534"/>
        <source>Cancelado. La tarea pudo seguir en Proxmox; revisa si la máquina existe.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="538"/>
        <source>Cancelado. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="545"/>
        <location filename="../../interfaz/textos.py" line="813"/>
        <source>Validando datos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="547"/>
        <location filename="../../interfaz/textos.py" line="814"/>
        <source>Enviando a Proxmox</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="549"/>
        <location filename="../../interfaz/textos.py" line="815"/>
        <source>Creando la máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="551"/>
        <location filename="../../interfaz/textos.py" line="816"/>
        <source>Comprobando el resultado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="553"/>
        <source>Listo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="560"/>
        <source>es el único con espacio suficiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="562"/>
        <source>más memoria y espacio libres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="564"/>
        <source>misma memoria libre; se eligió el que tiene más espacio</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="573"/>
        <source>Servidor nuevo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="575"/>
        <source>Certificado conocido</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="577"/>
        <source>El certificado cambió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="578"/>
        <source>Sin verificar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="587"/>
        <source>Se perdió la conexión. Hay 1 máquina sin confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/textos.py" line="590"/>
        <source>Se perdió la conexión. Hay %n máquinas sin confirmar.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="612"/>
        <source>El número {vmid} lo usó otra persona mientras tanto. Esta máquina no se creó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="626"/>
        <source>cancelaste el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="628"/>
        <source>el lote se detuvo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="630"/>
        <source>hubo un error que afectaba a todo el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="632"/>
        <source>el nodo no respondió</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="633"/>
        <source>no se llegó a enviar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="641"/>
        <source>Ningún servidor puede alojar esta máquina. Revisa que el almacenamiento y la red existan en los nodos elegidos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="648"/>
        <source>No encontré {n} números de máquina libres a partir del {inicio}. Prueba con otro número inicial o con menos máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="654"/>
        <source>número inicial</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="658"/>
        <source>Las máquinas necesitan {pedido} GiB en «{storage}» y solo hay {libre} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="667"/>
        <location filename="../../interfaz/textos.py" line="1049"/>
        <source>Caben {max}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="671"/>
        <source>No sabemos si «{nombre}» se creó. No se volverá a enviar: pulsa «Comprobar» para verlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="680"/>
        <source>No pudimos comprobar si «{nombre}» existe. Revisa la conexión y vuelve a comprobar antes de crearla otra vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="689"/>
        <source>Fallaron {n} máquinas seguidas por la misma causa: {causa} ¿Continuar o detener?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="696"/>
        <source>una causa desconocida</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="702"/>
        <source>Se perdió la conexión. Hay máquinas sin confirmar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="708"/>
        <source>«{nombre}» no se envió ({motivo}). No existe en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="716"/>
        <source>Los datos del servidor cambiaron: {diferencia}. Revisa el resumen y confirma otra vez.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="722"/>
        <source>hay cambios</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="725"/>
        <source>Hay un lote en curso. Espera a que termine o cancélalo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="730"/>
        <location filename="../../interfaz/textos.py" line="1094"/>
        <source>Elige entre 1 y {max} máquinas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="736"/>
        <source>Has forzado una versión más nueva que la del servidor ({detectada}); solo puedes simular.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="742"/>
        <source>otra</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="745"/>
        <source>Proxmox no aceptó la etiqueta de la máquina. No se creó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="749"/>
        <source>No se pudo eliminar «{nombre}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="752"/>
        <source>Elimínala desde Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="755"/>
        <source>No eliminamos «{nombre}» porque no podemos asegurar que la creó este lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="763"/>
        <source>«{nombre}» está encendida. Apágala en Proxmox y vuelve a intentarlo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="770"/>
        <source>«{nombre}» está protegida o bloqueada. Quita la protección en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="778"/>
        <source>Pueden haber quedado discos sueltos de «{nombre}»; revísalos en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="786"/>
        <source>No sabemos si se eliminó «{nombre}». Comprueba antes de reintentar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="793"/>
        <source>Error interno: se intentó escribir en modo simulación. No se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="801"/>
        <source>La máquina existe en Proxmox, pero no pudimos confirmar que la creó ProxLaunch: podría ser de otra persona con el mismo número. Verifícalo en Proxmox antes de hacer nada con ella. No se eliminará desde aquí.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="812"/>
        <location filename="../../interfaz/textos.py" line="860"/>
        <source>Pendiente</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="817"/>
        <source>Lista</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="818"/>
        <source>Lista, con avisos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="819"/>
        <source>Con error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="820"/>
        <source>Quedó a medias</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="821"/>
        <source>Sin confirmar (sigue en Proxmox)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="824"/>
        <source>No sabemos si se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="825"/>
        <source>No enviada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="826"/>
        <source>No se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="827"/>
        <source>Existe, sin confirmar de quién es</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="861"/>
        <source>Comprobando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="862"/>
        <source>Eliminando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="863"/>
        <source>Eliminada</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="864"/>
        <source>Ya no existía</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="865"/>
        <source>No se pudo eliminar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="866"/>
        <source>No se tocó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="867"/>
        <source>No sabemos si se eliminó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="868"/>
        <source>No se procesó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="893"/>
        <source>es el único nodo disponible</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="895"/>
        <source>lo elegiste tú</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="897"/>
        <source>Equilibrado: más memoria libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="899"/>
        <source>Equilibrado: más espacio libre</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="901"/>
        <source>Por turnos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="908"/>
        <source>El lote se detuvo por un problema general</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="910"/>
        <source>El lote se detuvo: el mismo error se repite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="911"/>
        <source>El lote se detuvo: se perdió la conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="917"/>
        <location filename="../../interfaz/textos.py" line="948"/>
        <source>No se puede deshacer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="919"/>
        <source>No se envió: no existe en Proxmox.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="921"/>
        <source>No se creó: no hay nada que eliminar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="923"/>
        <source>Se encontró tras una comprobación, sin etiqueta que la ate a este lote: no podemos asegurar que sea suya.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="929"/>
        <source>Falló y no se creó nada.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="931"/>
        <source>Existe, pero no podemos asegurar que la creó este lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="940"/>
        <source>No sabemos si se creó: comprueba primero qué pasó.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="945"/>
        <source>esta máquina</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="974"/>
        <source>tiene el carácter «{caracter}», que no se admite</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="981"/>
        <source>es demasiado largo (cada parte puede tener hasta 63 caracteres)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="984"/>
        <source>no puede empezar ni terminar con guion o punto, ni tener partes vacías</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="994"/>
        <source>El número inicial debe estar entre 0 y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1002"/>
        <source>La numeración llegaría a {ultimo} y el máximo es {maximo}. Baja el número inicial o la cantidad.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1013"/>
        <source>El relleno debe estar entre 0 y {maximo} dígitos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1020"/>
        <source>El nombre «{nombre}» no es válido: {causa}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1029"/>
        <source>«{storage}»</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1031"/>
        <source>«{storage}» (compartido)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1034"/>
        <source>«{storage}» del nodo {nodo}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1039"/>
        <source>Las {n} máquinas necesitan {pedido} GiB en {lugar} y solo hay {libre} GiB libres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1056"/>
        <source>«{nodo}» está sin conexión.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1059"/>
        <source>«{nodo}» no tiene el almacenamiento «{storage}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1066"/>
        <source>«{nodo}» no tiene un almacenamiento para la configuración de UEFI.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1073"/>
        <source>«{nodo}» no tiene la red «{bridge}».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1076"/>
        <source>«{nodo}» no puede alojar esta configuración.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1086"/>
        <source>El máximo por lote es {max} máquinas. Divide el trabajo en varios lotes.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1100"/>
        <source>Escribe un prefijo para los nombres.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1101"/>
        <source>El prefijo solo puede tener letras sin acentos, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1105"/>
        <source>Elige un guion o ningún separador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1109"/>
        <source>Los nombres del lote no pueden repetirse.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1112"/>
        <source>Ya existe una máquina llamada «{nombre}» (número {vmid}).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1120"/>
        <source>El lote llegaría hasta el número {ultimo} y el máximo es {maximo}. Baja el número inicial o la cantidad.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1129"/>
        <source>El número inicial debe estar entre {minimo} y {maximo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1137"/>
        <source>No hay {n} números de máquina libres a partir del {inicio}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1147"/>
        <source>Estás pidiendo {pedido} GiB y en «{storage}» solo hay {libre} GiB libres: es más de {factor} veces lo que hay. Reduce las máquinas o el tamaño de los discos.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1159"/>
        <source>Estás pidiendo {pedido} GiB y solo hay {libre} GiB libres en «{storage}». Funciona mientras las máquinas no usen todo su disco; si se llena, todas las máquinas de ese almacenamiento pueden fallar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1173"/>
        <source>Cada máquina pide {vcpus} procesadores virtuales y «{nodo}» tiene {cpus_nodo}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1182"/>
        <source>No se pudo leer la memoria libre de {nodos}; el reparto usa el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1192"/>
        <source>No se pudo leer la memoria libre de «{nodo}»; el reparto usa el espacio.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1199"/>
        <source>En «{nodo}» pides {pedido} GiB de memoria y hay {libre} GiB libres. Las máquinas se crean apagadas; el problema aparecerá al encenderlas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1209"/>
        <source>Elige al menos un nodo disponible.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1211"/>
        <source>Se actualizaron los datos del servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1223"/>
        <source>Proxmox no admite esa etiqueta: usa solo letras, números y guiones.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1229"/>
        <source>Máquina {n}: {texto}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/textos.py" line="1239"/>
        <source>Ningún nodo tiene sitio para todas las máquinas con el espacio libre actual.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>VentanaPrincipal</name>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="207"/>
        <source>ahora hay errores que impiden crear el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="218"/>
        <source>el número {a} ya no está libre (ahora se usa el {b})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="224"/>
        <source>«{n}» pasa de {a} a {b}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="232"/>
        <source>y %n cambios más</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="242"/>
        <source>ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="321"/>
        <location filename="../../interfaz/ventana_principal.py" line="635"/>
        <source>Sin conexión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="342"/>
        <source>Conecta con tu servidor Proxmox para empezar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="347"/>
        <location filename="../../interfaz/ventana_principal.py" line="421"/>
        <source>Conectar...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="363"/>
        <source>Actualizar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="367"/>
        <source>Reintentar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="420"/>
        <source>&amp;Archivo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="424"/>
        <source>Cerrar sesión</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="426"/>
        <source>Salir</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="429"/>
        <source>Ver el último lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="436"/>
        <source>&amp;Ajustes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="437"/>
        <source>Tema</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="441"/>
        <source>Automático</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="442"/>
        <source>Oscuro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="443"/>
        <source>Claro</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="451"/>
        <source>Modo</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="455"/>
        <source>Básico</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="456"/>
        <source>Avanzado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="465"/>
        <source>A&amp;yuda</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="466"/>
        <source>¿Cómo creo un API Token?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="468"/>
        <source>Acerca de ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="563"/>
        <source>Esa clave de recuperación ya no se puede volver a usar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="569"/>
        <source>Conectado a {b} ({a} no respondió)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="573"/>
        <source>Conectado</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="669"/>
        <source>No se pudo leer el archivo de huellas (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="673"/>
        <source>Se dañó el archivo de huellas; se recuperaron {n} servidores. Los demás tendrás que confirmarlos de nuevo comparando la huella con tu administrador.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="680"/>
        <source>No se pudo leer el archivo de perfiles (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="684"/>
        <source>El archivo de perfiles estaba dañado: se guardó una copia y se empezó uno nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="689"/>
        <source>No se pudo leer el archivo de preferencias (permisos)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="708"/>
        <source>Buscando nodos, almacenamientos y redes...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="720"/>
        <source>No se pudo leer el servidor.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="729"/>
        <source>{n} nodo(s) encontrados.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="737"/>
        <source>Con este usuario no podrás crear máquinas: falta el permiso VM.Allocate</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="753"/>
        <source>No se pudo leer el nodo {nodos}: aparece como «Sin conexión».</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1013"/>
        <source>El servidor no permite poner etiquetas a las máquinas. Puedes crearla sin etiquetas; después, «Deshacer» solo podrá eliminarla si el nombre coincide.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1058"/>
        <source>Etiquetas desactivadas. Pulsa «Crear» para crear la máquina sin ellas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1073"/>
        <source>Todavía no sabemos si se creó</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1075"/>
        <source>No hemos podido confirmar si la máquina se creó. Si vuelves al formulario y la creas otra vez, podrías duplicarla. ¿Volver de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1109"/>
        <source>Comprobando si la máquina existe...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1125"/>
        <source>Comprobando la tarea...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1127"/>
        <source>Esperando a que termine la tarea...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1168"/>
        <source>La máquina sí se creó. Verifica en Proxmox que quedó como esperabas.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1176"/>
        <source>No se creó; puedes intentarlo de nuevo.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1185"/>
        <source>No se pudo comprobar si la máquina existe. Revisa la conexión e inténtalo de nuevo antes de volver a crearla.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1232"/>
        <source>El último lote se cerró sin terminar. Informe: {ruta}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1478"/>
        <source>Confirmar el envío</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../../interfaz/ventana_principal.py" line="1479"/>
        <source>Se enviarán %n máquinas a Proxmox. ¿Continuar?</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1485"/>
        <source>Crear las máquinas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1486"/>
        <location filename="../../interfaz/ventana_principal.py" line="1641"/>
        <source>Cancelar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1633"/>
        <source>Seguir sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1634"/>
        <source>Se detendrá este lote y se armará uno nuevo con las máquinas que faltan, sin etiquetas. Después, «Deshacer» solo podrá eliminar las máquinas que ProxLaunch confirme que creó él mismo. Antes de crear nada verás el resumen.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1640"/>
        <source>Preparar el lote sin etiquetas</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1651"/>
        <source>Esperando a que terminen las tareas en curso para continuar…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1670"/>
        <location filename="../../interfaz/ventana_principal.py" line="1676"/>
        <source>Cancelar el lote</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1671"/>
        <source>Las máquinas que ya se enviaron seguirán creándose en Proxmox y se esperará su resultado. Las demás no se enviarán.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1677"/>
        <source>Seguir creando</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1721"/>
        <source>El lote terminó de forma inesperada: {m}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1740"/>
        <source>Reconecta para continuar con las máquinas que faltan.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="1742"/>
        <source>Reconecta para continuar con el lote.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2035"/>
        <source>Eliminando las máquinas elegidas…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2186"/>
        <source>Hay máquinas sin confirmar</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2187"/>
        <source>No sabemos si algunas máquinas se crearon. Si vuelves y repites el lote, podrías duplicarlas. ¿Volver de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2192"/>
        <source>Volver de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2193"/>
        <source>Quedarme aquí</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2270"/>
        <source>Hay un «Deshacer» en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2271"/>
        <source>Se están eliminando máquinas. Si cierras, ProxLaunch dejará de esperar: las eliminaciones ya enviadas seguirán en Proxmox y el resto no se hará.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2249"/>
        <source>Hay un lote en curso</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2250"/>
        <source>Hay un lote en curso ({x} de {n} terminadas). Si cierras, las tareas ya enviadas seguirán en Proxmox, pero ProxLaunch no enviará el resto ni podrá deshacer lo creado.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2256"/>
        <location filename="../../interfaz/ventana_principal.py" line="2276"/>
        <source>Cerrar de todos modos</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2257"/>
        <location filename="../../interfaz/ventana_principal.py" line="2277"/>
        <source>Seguir en ProxLaunch</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2290"/>
        <source>Hay una máquina en creación</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2292"/>
        <source>Se está creando una máquina. Si cierras ProxLaunch, la tarea sigue ejecutándose en el servidor Proxmox, pero ya no verás su resultado. ¿Cerrar de todos modos?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../../interfaz/ventana_principal.py" line="2306"/>
        <source>Cerrando...</source>
        <translation type="unfinished"></translation>
    </message>
</context>
</TS>
