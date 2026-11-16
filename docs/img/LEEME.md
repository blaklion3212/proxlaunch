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

## Detalles de contenido

- `13`, `14`, `16` y `21` salen con la ventana más alta que la habitual para enseñar el
  formulario entero; en la aplicación, con 820 px de alto, el formulario se desplaza.
- `29` (básico) no ofrece **Guardar la copia en**: esa fila solo aparece en avanzado con copia
  completa (`30`).
- `47`, `48` y `49` muestran solo el panel del resumen; en la ventana ocupa la columna derecha.
- `57` a `59` usan una copia de los CSV de `docs/ejemplos/` (`mvs-mixtas.csv` y
  `mvs-con-errores.csv`) incluida en el escenario. Si esos ejemplos cambian, hay que
  actualizar `CSV_MIXTAS` y `CSV_CON_ERRORES` en `escenario.py` y regenerar.
