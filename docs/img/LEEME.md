# Capturas de la guía de usuario

Estas imágenes se generan con la aplicación real (ProxLaunch), servicios falsos y datos
inventados. No hay red, ni servidor Proxmox, ni rutas ni usuarios reales: todo lo que se ve
sale del escenario ficticio de `tests/interfaz/capturas_guia/escenario.py`.

## Cómo regenerarlas

```bash
.venv/bin/pytest -m capturas -p no:cacheprovider tests/interfaz/capturas_guia
```

- Las pruebas de este generador llevan la marca `capturas`, que la suite normal excluye.
- Escriben en esta carpeta (`docs/img/NN-nombre.png`) y sobrescriben lo que haya.
- Con la misma versión de la aplicación y de Qt, cada ejecución da exactamente los mismos
  archivos (misma suma de verificación).
- Para generar solo algunas: `... tests/interfaz/capturas_guia -k "test_13 or test_14"`.

## Cómo se hacen

- Tema claro (salvo la 24), fuente Open Sans a 13 px y traductor, como en `interfaz/app.py`.
- Pantalla virtual de 1920x1080 a 96 DPI (plataforma `offscreen` con un archivo de
  configuración), para que ninguna ventana se recorte por el límite de pantalla.
- La ventana principal mide 1240x820 salvo en las capturas que necesitan ver el formulario
  entero (más alta) o una tabla ancha (más ancha). Los diálogos salen con su tamaño natural;
  en unos pocos se agranda para ver todo el contenido sin barras.
- Son capturas del contenido de la ventana: no incluyen la barra de título ni el marco del
  sistema operativo.
- Fecha y hora fijas (10 de marzo de 2025, UTC), identificador de lote fijo (`a1b2c3d4`),
  usuario `ana@pve`, servidor `192.0.2.10`, nodos `pve`, `pve1`, `pve2` y `pve3`.
- No se capturan los diálogos de archivos del sistema (abrir y guardar).

## Lista

| Imagen | Qué muestra |
|---|---|
| `01-bienvenida.png` | Ventana sin conexión: mensaje de bienvenida y botón **Conectar...** |
| `02-menu-lote.png` | Menú **Lote** desplegado (abrir, guardar, importar CSV, plantilla CSV, informe) |
| `03-menu-ajustes.png` | Menú **Ajustes** con los submenús **Tema** y **Modo** desplegados |
| `04-conexion-token.png` | **Conectar con Proxmox** con API Token (token enmascarado) |
| `05-conexion-contrasena-root.png` | Conexión con usuario y contraseña de `root` y su aviso |
| `06-conexion-avanzado.png` | Conexión en modo avanzado: ignorar SSL, versión forzada, almacenamientos recordados |
| `07-conexion-validacion.png` | Errores de validación junto a los campos (servidor, token, nombre repetido) |
| `08-huella-primera-vez.png` | **Confiar en este servidor**: huella SHA-256 la primera vez |
| `09-huella-cambiada.png` | Aviso de certificado cambiado, con la huella guardada y la nueva |
| `10-2fa-codigo.png` | Código de verificación en dos pasos |
| `11-guia-token.png` | **¿Cómo creo un API Token?** (la guía es larga y se desplaza) |
| `12-acerca-de.png` | **Acerca de ProxLaunch** |
| `13-trabajo-individual-basico.png` | Ventana de trabajo con un servidor individual en modo básico |
| `14-trabajo-cluster-nodo.png` | Lo mismo en un clúster: aparece **Nodo destino** |
| `15-nodo-caido-reintentar.png` | Aviso de un nodo que no respondió y botón **Reintentar** |
| `16-formulario-errores.png` | Formulario con errores (nombre, número de máquina ocupado, memoria) y **Crear máquina** desactivado |
| `17-progreso-en-curso.png` | Progreso de una creación en marcha, con el UPID |
| `18-progreso-ok.png` | Máquina creada: resultado en verde y botones **Crear otra** y **Deshacer...** |
| `19-progreso-error-detalles.png` | Error de creación con los detalles técnicos desplegados |
| `20-progreso-tiempo-agotado.png` | Tiempo agotado: **Seguir esperando**, **Comprobar ahora** |
| `21-avanzado-formulario.png` | Formulario avanzado: UEFI, TPM, agente de QEMU, tipo de CPU, ballooning |
| `22-avanzado-discos.png` | Tabla de discos con todas las columnas |
| `23-avanzado-red.png` | Tabla de redes con VLAN |
| `24-tema-oscuro.png` | La ventana 13 en tema oscuro (única captura en oscuro) |
| `25-origen-selector-capacidades.png` | Origen del sistema: una opción desactivada con su motivo (falta un permiso) |
| `26-origen-iso-linux.png` | Instalar desde un ISO de Linux |
| `27-origen-iso-windows-drivers.png` | ISO de Windows 11: cambios del asistente y drivers virtio-win |
| `28-origen-importar.png` | Usar un disco existente (qcow2) y ampliarlo |
| `29-origen-clonar-basico.png` | Copiar una plantilla en modo básico |
| `30-origen-clonar-avanzado.png` | Copiar una plantilla en avanzado: tipo de copia y dónde guardarla |
| `31-catalogo-iso.png` | Elegir un archivo ISO del servidor |
| `32-catalogo-plantillas.png` | Elegir una plantilla (una sin permiso de clonado, no elegible) |
| `33-subida-iso-lista.png` | Subir un ISO desde el equipo, listo para enviar |
| `34-subida-ya-existe.png` | La subida avisa de que el archivo ya existe |
| `35-descarga-url.png` | Descargar un ISO en el servidor desde una dirección web |
| `36-elegir-storage.png` | **Elegir almacenamiento** entre varios candidatos |
| `37-capacidades-servidor.png` | **Qué puedo hacer en este servidor** (con permisos incompletos) |
| `38-archivos-subidos-sesion.png` | **Archivos subidos en esta sesión** |
| `39-selector-perfil.png` | Selector de perfil de máquina con un perfil de fábrica |
| `40-selector-perfil-modificado.png` | Perfil propio modificado, aviso del perfil y compatibilidad |
| `41-guardar-perfil.png` | **Guardar como perfil de máquina** |
| `42-administrar-perfiles.png` | **Administrar perfiles de máquina** |
| `43-exportar-perfiles.png` | **Exportar perfiles** |
| `44-importar-perfiles.png` | **Importar perfiles**: nuevo, nombre repetido y no válido |
| `45-lote-bloque-basico.png` | Bloque **Lote** en modo básico (cantidad, prefijo, vista previa) |
| `46-lote-bloque-avanzado-cluster.png` | Bloque **Lote** en avanzado y clúster (separador, VMID, nodos, reparto) |
| `47-lote-resumen.png` | **Vas a crear 5 máquinas**: tabla y totales |
| `48-lote-resumen-no-caben.png` | Resumen bloqueado: no caben, con **Reducir a 32** |
| `49-lote-simulacion.png` | Resultado de **Simular**, con las peticiones en detalles técnicos |
| `50-lote-progreso-en-curso.png` | Lote en marcha: 6 de 12 terminadas, un error, dos en curso |
| `51-lote-pausa.png` | El lote se detuvo por un problema general |
| `52-lote-progreso-terminado.png` | Lote terminado, con un error y una máquina sin confirmar |
| `53-lote-deshacer.png` | **Deshacer lo creado por el lote** |
| `54-lote-informe.png` | **Informe del lote** |
| `55-guardar-lote.png` | **Guardar lote** |
| `56-lote-no-encaja.png` | Un lote guardado que no encaja en este servidor (almacenamiento y nodo) |
| `57-csv-vista-previa-ok.png` | Importar desde CSV: vista previa sin errores graves |
| `58-csv-vista-previa-errores.png` | Importar desde CSV con errores, en modo avanzado |
| `59-lote-por-filas.png` | Lote por filas tras importar el CSV |
| `60-cambios-sin-guardar.png` | Pregunta **Cambios sin guardar** |
| `61-opciones-general.png` | Opciones de la máquina en modo básico (encender, arranque, notas, etiquetas, pool) y el resumen con las opciones avanzadas ocultas |
| `62-opciones-avanzadas.png` | Las mismas opciones en modo avanzado: orden y espera de arranque, protección, MTU y límite de red |
| `63-opciones-deshabilitadas.png` | Opciones desactivadas por falta de `VM.PowerMgmt` y `Pool.Audit`, con su explicación |
| `64-lote-resumen-opciones.png` | Resumen de un lote de 5 máquinas con las líneas de opciones |
| `65-simulacion-encender.png` | Simulación con opciones: `tags`, `onboot`, `startup`, `description`, `pool`, `protection` y el encendido final |
| `66-deshacer-confirmacion-forzada.png` | Confirmación expresa de Deshacer con máquinas encendidas y protegidas |
| `67-guia-privilegios-opcionales.png` | Final de la guía del token: privilegios opcionales y lo que no se pide |
| `68-seccion-cloudinit.png` | Origen **Copiar una plantilla** y, debajo, la sección **Configuración inicial (cloud-init)** rellena: usuario, 1 clave SSH, contraseña vacía, tarjeta de red 1 (net0) con IP fija y puerta de enlace, DNS y dominio |
| `69-cloudinit-ip-en-serie.png` | Resumen de un lote de 4 máquinas que clonan una plantilla con **IP en serie** (192.0.2.50 sumando 1 a cada una) y la tabla «IP que recibirá cada máquina» |
| `70-esperar-ip.png` | Paso **General** con **Encender al terminar** y **Esperar la IP de cada máquina** marcadas, su plazo (120 s) y el aviso de que las imágenes de Ubuntu y Debian no traen el agente invitado (V-B64) |
| `71-progreso-con-ip.png` | Lote terminado con la columna **IP** (una con IP, una «El agente no responde», una «Esperando la IP…») y los botones **Dejar de esperar la IP**, **Copiar lista de IPs** y **Exportar IPs…** |
| `72-asistente-plantilla-imagen.png` | Asistente **Crear plantilla desde imagen cloud**, parte superior: explicación, origen de la imagen (una ya importada en el servidor), dónde se crea y la máquina modelo |
| `73-asistente-plantilla-confirmar.png` | Parte inferior del asistente: opciones para imágenes cloud, valores de cloud-init de la plantilla (sin campo de contraseña), la casilla de conversión irreversible marcada y el aviso del agente invitado |
| `74-asistente-plantilla-fallo.png` | Asistente detenido tras fallar el paso 4 (permiso de cloud-init): los cinco pasos con su estado y las acciones **Reintentar este paso**, **Continuar sin cloud-init** y **Borrar la máquina a medio crear…** |
| `75-importar-csv-cloudinit.png` | **Importar desde CSV** con columnas de cloud-init: aviso de contraseñas en texto claro y, en el detalle de una fila, `ci_contrasena` enmascarada (`••••••`) |
| `76-menu-archivo-plantilla.png` | Menú **Archivo** con **Crear plantilla desde imagen cloud…** |
| `77-inventario-lotes.png` | **Lotes en el servidor** con tres lotes encontrados (sin leer aún), el cuadro de búsqueda, **Comprobar** y los botones **Obtener IP**, **Exportar CSV…**, **Deshacer…** y **Cerrar** |
| `78-inventario-detalle.png` | Detalle del lote `ab12cd34`: tres máquinas encendidas (`web-101` a `web-103`) con su IP tras **Obtener IP**, marcadas como deshacibles |
| `79-inventario-deshacer-codigo.png` | Lote `e5f60718` con **Deshacer…**: panel de confirmación con el aviso, el código del lote que hay que escribir y **Borrar definitivamente** desactivado |
| `80-redes-con-vnets.png` | Tabla **Red** en modo avanzado con el bridge `vmbr0`, la VNet `prod — Producción` con VLAN 30 y `lab — Pruebas` con la VLAN desactivada y su aviso (no es «vlanaware») |
| `81-seccion-firewall.png` | Grupo **Firewall de la máquina** con **Activar el firewall** marcada, el grupo `web — Servidores web`, entrada en **Bloquear** y salida en **Permitir** |
| `82-firewall-aviso-aislada.png` | Firewall activo con entrada en **Bloquear** y **Sin grupo**: aviso en rojo y la casilla **Entiendo que la máquina no aceptará conexiones por la red** sin marcar |
| `83-seccion-red-clon.png` | Grupo **Red de las copias** con **Personalizar la red de las copias**: `net1` en `prod — Producción` con VLAN 20 y MTU 1400, las tres tarjetas con **Quitar** y el botón **Añadir tarjeta** |
| `84-resumen-red-firewall.png` | Resumen de un lote de 3 clones con «Red de la copia: net1: cambiar (prod)» y la línea de Firewall activado (grupo `web`) |
| `85-menu-lotes-servidor.png` | Menú **Archivo** con **Lotes en el servidor…**, **Crear plantilla desde imagen cloud…** e **Importar desde libvirt…** |
| `86-libvirt-vista-previa.png` | Asistente **Importar desde libvirt**: XML de una máquina Linux con UEFI, 2 discos y 1 tarjeta leído; tabla de vista previa con filas **Migrado**, **Aproximado** y **No se migra**, y el detalle de avisos |
| `87-libvirt-como-obtener-xml.png` | El mismo asistente con **Cómo obtener el XML** desplegado: las cuatro órdenes (`virsh dumpxml`, `virsh domblklist`, `qemu-img info`, `qemu-img convert`), cada una con su botón **Copiar** |
| `88-libvirt-imagenes-por-disco.png` | Origen **Usar un disco existente** tras **Rellenar el formulario**: imagen del disco del sistema y, para los otros discos, **Elegir imagen…** o **Crear vacío** |
| `89-seccion-hardware-cluster.png` | Sección **Hardware del clúster**: una tarjeta PCI (`gpu-ejemplo`, PCIe y gráfica principal) y un USB (`llave-ejemplo`), con los avisos de q35 y de migración |
| `90-cpu-personalizada.png` | Desplegable **Tipo de CPU** abierto: tipos fijos y el grupo **Personalizados del clúster** (`custom-ejemplo`, `custom-laboratorio`) |
| `91-nodo-arm64-experimental.png` | Formulario con el nodo `pve-arm` elegido a mano: etiqueta **ARM64, experimental**, selector **Arquitectura de este servidor**, UEFI y CPU `host` adaptados y aviso de valores cambiados |
| `92-capacidades-fase-d.png` | **Qué puedo hacer en este servidor** con las filas nuevas: saber si un servidor es ARM, tarjetas PCI y USB del clúster y modelos de CPU personalizados |
| `93-resumen-fase-d.png` | **Resumen** de una máquina importada de libvirt: hardware del clúster, tipo de máquina q35, MAC conservada y discos importados |

## Detalles de contenido

- `13`, `14`, `16` y `21` salen con la ventana más alta que la habitual para enseñar el
  formulario entero; en la aplicación, con 820 px de alto, el formulario se desplaza.
- `29` (básico) no ofrece **Guardar la copia en**: esa fila solo aparece en avanzado con copia
  completa (`30`).
- `47`, `48` y `49` muestran solo el panel del resumen; en la ventana ocupa la columna derecha.
- `57` a `59` usan una copia de los CSV de `docs/ejemplos/` (`mvs-mixtas.csv` y
  `mvs-con-errores.csv`) incluida en el escenario. Si esos ejemplos cambian, hay que
  actualizar `CSV_MIXTAS` y `CSV_CON_ERRORES` en `escenario.py` y regenerar.
- `68` es la ventana completa (2500 px de alto, modo avanzado) para ver juntos el origen, **General**
  y la sección de cloud-init entera; el panel «Compatibilidad del perfil» no muestra ningún aviso.
- El escenario concede a la cuenta los privilegios del agente (`VM.GuestAgent.Audit` y `VM.Monitor`),
  por eso **Esperar la IP** sale disponible; `63` los quita a propósito (junto con `VM.PowerMgmt` y
  `Pool.Audit`) y enseña también esa opción desactivada con su explicación.
- `72` a `74`: la barra de desplazamiento del asistente queda a la derecha, sin tapar los campos. Su
  marcador solo cubre una parte porque el contenido total es más alto que la ventana (se ve la parte
  alta en `72` y `74`, la baja en `73`). La barra de avance solo aparece mientras hay trabajo en
  marcha, por eso no sale en `74`.
- `75` usa una copia del CSV `mvs-cloudinit.csv` con una columna `ci_contrasena` añadida (contraseña
  inventada, siempre enmascarada en pantalla); el ejemplo de `docs/ejemplos/` no la trae.
- La clave SSH que aparece (`ssh-ed25519 AAAAC3Nz… ana@portatil`) es falsa: tiene formato válido pero no
  hay clave privada detrás (`CLAVE_SSH_FALSA` en `escenario.py`).
- `74` muestra «Reintentar» y «Omitir» (paso fallido); «Comprobar ahora» solo aparece cuando un paso queda
  dudoso (no se sabe cómo terminó), por eso no coincide con un fallo claro.
- `86` a `88` y `93` salen del XML ficticio `XML_LIBVIRT_EJEMPLO` de `escenario.py` (máquina `app-linux-ejemplo`,
  MAC `52:54:00:12:34:56`); `93` marca **Conservar la MAC de origen** y `88` usa un XML con un tercer disco.
- `87` es el asistente con el XML ya leído y el panel desplegado (1090 px de alto para ver el detalle entero).
- `89` a `92` usan el clúster ficticio `demo` con `pve1`, `pve2` y `pve-arm` (arm64), los mapeos `gpu-ejemplo` y
  `llave-ejemplo` y las CPU `custom-ejemplo` y `custom-laboratorio` (`inventario_guia_fase_d` e `info_hardware_guia`).
- `90` compone la ventana con el desplegable abierto (el desplegable es una ventana propia); `91` es la ventana
  completa (2550 px de alto) con el nodo elegido a mano.
