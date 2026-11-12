Necesito que desarrolles la arquitectura completa, modelos de datos e implementación base de una aplicación de escritorio moderna para automatizar la creación y el aprovisionamiento en lote (batch) de Máquinas Virtuales (MVs) en Proxmox Virtual Environment (PVE) mediante su API REST.

---
### 1. REQUERIMIENTOS TÉCNICOS Y ARQUITECTURA
- **Tecnología sugerida:** Python 3.11+ con PySide6 (Qt) y la librería `proxmoxer` (o Rust + Tauri si consideras que ofrece mejor rendimiento/concurrencia).
- **Entorno de ejecución:** Escritorio multiplataforma (Linux / Windows / macOS).
- **Manejo de Red y API:** Asíncrono / Multi-threading (Workers) para evitar que las llamadas de red y el polling de tareas UPID congelen la interfaz de usuario (UI).

---
### 2. SISTEMA DE DISEÑO, ESTILOS Y PALETA DE COLORES (PROXMOX VE THEME)
La interfaz gráfica debe imitar fielmente la estética visual, paleta cromática, tipografía y estilo sobrio/industrial de la consola web oficial de Proxmox VE (ExtJS Theme):
- **Paleta de Colores Primaria:**
  - Naranja Corporativo Proxmox: `#E57000` / `#E85D04` (usado para acciones primarias, acentos de selección, logo y estados activos).
  - Encabezados / Barra superior: Gris oscuro pizarra (`#2C3E50` o `#212529`) con acentos en naranja corporativo.
  - Fondo general (Dark Mode oficial): `#1E1E1E` o `#2B2B2B`.
  - Fondo de paneles / contenedores: `#242424` / `#2D3238`.
  - Bordes y separadores de tabla: Gris neutro sutil (`#3E444A` o `#4A4A4A`).
  - Textos: Blanco hueso / Gris claro (`#E0E0E0` o `#CCCCCC`) para lectura de alto contraste, y gris atenuado (`#8A9BA8`) para etiquetas secundarias.
- **Tipografía y Controles:**
  - Tipografía tipo interfaz sans-serif limpia: *Open Sans*, *Ubuntu*, o tipografía fija/monospace (`JetBrains Mono`, `Consolas`) para campos técnicos como IDs, MACs, UPIDs y logs.
  - Tablas tipo Grid compactas con filas alternadas, cabeceras definidas y estados hover/focus que resalten en naranja o gris oscuro atenuado.
  - Botones estilizados tipo botón de acción Proxmox (bordes limpios, esquinas sutilmente redondeadas con `border-radius: 2px - 3px`, sin sombras exageradas ni gradientes estridentes).

---
### 3. MÓDULO DE AUTENTICACIÓN Y CONEXIÓN
El sistema debe soportar una barra o modal de conexión con dos métodos:
1. **API Token:** Formato `USER@REALM!TOKENID=UUID`. Conexión sin estado (stateless).
2. **Credenciales Clásicas (Ticket):** Campos para Host/IP, Puerto (default 8006), Realm (`pam` o `pve`), Usuario y Contraseña.
   - Debe implementar interceptor de sesión para renovar el ticket (`PVEAuthCookie` + `CSRFPreventionToken`) que expira cada 2 horas.
   - Soporte para desafío 2FA/TOTP en caso de que el servidor lo exija.
   - Opción explícita de "Ignorar verificación SSL" para entornos con certificados autofirmados.
   - Botón "Probar y Conectar" que llame a `/api2/json/version` para validar conectividad.

---
### 4. FASE DE DESCUBRIMIENTO DINÁMICO (POST-AUTH)
Al conectar exitosamente, la aplicación NO debe depender de inputs manuales ciegos. Debe consultar en segundo plano:
- Nodos disponibles (`/api2/json/nodes`).
- **Storage Pools / DataSources válidos:** Consultar `/api2/json/nodes/{node}/storage` y filtrar únicamente aquellos pools que tengan habilitado el flag de contenido `content: "images"` (ej. `local-lvm`, `local-zfs`, `ceph-pool`, `nfs`, etc.). Debe capturar nombre del pool, tipo de backend y espacio disponible (GB libres).
- Interfaces y bridges de red (`/api2/json/nodes/{node}/network`).
- Próximo VMID libre (`/api2/json/cluster/nextid`).

---
### 5. MATRIZ DE CONFIGURACIÓN Y CREACIÓN DE MVs
La UI debe permitir armar una lista/cola de una o múltiples MVs a aprovisionar con:
- **Datos Generales:** VMID (autogenerado con opción de override), Nombre de la MV, Nodo destino.
- **Firmware / BIOS:** SeaBIOS u OVMF (UEFI). Si es UEFI, agregar automáticamente el disco EFI (`efidisk0`) solicitando o asignando por defecto el Storage Pool de destino compatible.
- **Cómputo:**
  - Sockets (default 1) y Cores (selector numérico).
  - CPU Type (default `host` con fallback a `x86-64-v2-AES`).
  - Memoria RAM (en MB o GB) con soporte para Memory Ballooning.
- **Almacenamiento (Discos y Storage / Datasource):**
  - Checkbox para MV con/sin disco.
  - Tabla dinámica para agregar 1 o más discos virtuales con los siguientes campos obligatorios por cada disco:
    * **Storage Pool / DataSource:** Menú desplegable poblado dinámicamente con los almacenamientos del nodo que soportan `images`, mostrando nombre y espacio libre en GB (ej. `local-zfs (140 GB libres)`).
    * **Bus / Controlador:** Selector entre `scsi` (con controlador `virtio-scsi-single` por defecto), `virtio`, `sata` o `ide`.
    * **Tamaño del Disco:** Campo numérico en Gigabytes (GB).
    * **Formato de Disco (si aplica):** `raw`, `qcow2` o `subvol` según el backend de almacenamiento.
    * **Opciones Avanzadas:** Checkbox de `Discard` (activación de TRIM/SSD emulation) e `IO Thread`.
- **Interfaces de Red:**
  - Interfaz VirtIO predeterminada conectada al bridge principal (`vmbr0`).
  - Capacidad de añadir interfaces adicionales, especificando bridge y VLAN Tag opcional.

---
### 6. MOTOR DE EJECUCIÓN Y TOLERANCIA A FALLOS
- **Validación Pre-Vuelo:** Verificar que la suma de GB de todos los discos virtuales configurados para un DataSource no sobrepase el almacenamiento disponible en el nodo antes de lanzar la creación.
- **Ejecución de tareas:** Enviar peticiones `POST` a `/api2/json/nodes/{node}/qemu` estructurando el parámetro de disco en la sintaxis requerida por Proxmox (ej. `scsi0: local-zfs:32,discard=on,ssd=1`).
- **Seguimiento:** Capturar el identificador de tarea (`UPID`) devuelto por Proxmox y hacer polling a `/api2/json/nodes/{node}/tasks/{upid}/status` mostrando una barra de progreso real con el naranja característico de Proxmox.
- **Manejo de errores:** Si una MV falla (por ejemplo, espacio insuficiente o timeout al crear volumen), el lote debe reportar el error con claridad sin detener abruptamente el resto de las máquinas, y ofrecer la opción de limpieza/rollback.

---
### ENTREGABLES ESPERADOS:
1. Diagrama o desglose de la arquitectura de clases / módulos del proyecto.
2. Hoja de estilos completa (QSS si es PySide6/Qt, o Tailwind/CSS si es Tauri) con la paleta de colores y componentes nativos de Proxmox.
3. Definición de modelos de datos (dataclasses o Pydantic) para la configuración de la MV, discos (incluyendo Storage Pool) y sesión.
4. Código funcional del cliente de conexión a la API con manejo de tokens, tickets y descubrimiento de Storage Pools compatibles con imágenes.
5. Código base de la interfaz gráfica y el worker thread asíncrono encargado del aprovisionamiento en lote.
6. Crear una vitacora donde se documenta cada paso realizado y el resultado de tal forma de que si en algun moento se quiera retomar el proyecto para futuros cambios o mejora.