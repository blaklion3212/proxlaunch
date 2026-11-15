# Bitácora del proyecto — ProxLaunch

## Propósito y uso

Registro cronológico de lo que se hizo en el proyecto y con qué resultado, para
que cualquiera pueda retomarlo. Las decisiones de fondo viven en
`decisiones.md` (D-01 a D-23); aquí solo se remite a ellas. La especificación
original es `prompt.md`; si difieren, manda `decisiones.md`.

**Cómo agregar una entrada:** añádela al final de "Entradas", con este formato
y sin borrar las anteriores. Actualiza también "Estado actual" y
"Pendientes y riesgos abiertos".

```
### AAAA-MM-DD · Título
- **Responsable:** quién lo hizo
- **Qué se hizo:** ...
- **Resultado:** ✅ / ⚠️ / ❌ y un resumen
- **Archivos:** rutas
- **Siguientes pasos:** ...
```

Nunca registres contraseñas, tokens ni datos personales.

---

## Estado actual (2026-11-15)

- **MVP 1 a MVP 4 aprobados** por el usuario. MVP 4 (origen del SO: ISO con asistente para Windows,
  importar qcow2, clonar plantilla) aprobado el 2026-11-14 tras 7226 pruebas normales y 232 de
  laboratorio; D-24, D-25 y D-26 definitivas.
- **MVP 5 (instaladores y scripts de empaquetado, versión 0.5.0): en cierre.** Construcción y
  verificación completas y documentadas (entrada 18; D-27). Comprobaciones manuales hechas con
  el usuario; pendiente de su aprobación. **Es el último MVP del plan** (D-12).
- **Laboratorio:** apagado y conservado (PVE 9.2, solo 127.0.0.1); limpio de MVs y ajustes.
  Se destruirá sin rastro al terminar todas las pruebas (D-15). Las MVs de empaquetado
  (`~/aprovprox-empaquetado/`) se destruyen con `mv.sh destruir-todo` al cerrar el MVP.

---

## Entradas

### 2026-11-11 · 1. Análisis de brechas de `prompt.md`
- **Responsable:** orquestador
- **Qué se hizo:** revisión de la especificación original para detectar vacíos y errores.
  Hallazgos principales: no definía cómo se instala el SO; faltaba una capa de
  usabilidad para usuarios sin experiencia; no definía cómo se arma un lote; no
  listaba los permisos de Proxmox; contenía errores técnicos (`subvol`, progreso
  por UPID, `scsihw` por MV, `ssd` en virtio, etc.).
- **Resultado:** ✅ brechas identificadas y llevadas a decisiones. Ver D-13 (origen
  del SO), D-14 (usabilidad) y la sección "Correcciones técnicas" de `decisiones.md`.
- **Archivos:** `prompt.md` (sin modificar), `docs/decisiones.md`.
- **Siguientes pasos:** resolver las brechas con el usuario (entrada 2). Los
  permisos de Proxmox y la forma de armar lotes se concretan en los requisitos.

### 2026-11-11 · 2. Decisiones con el usuario
- **Responsable:** orquestador con el usuario
- **Qué se hizo:** se acordaron stack (D-05), plataformas (D-06), versiones de
  Proxmox (D-07), topología (D-08), plan de entregas (D-12), origen del SO
  pospuesto (D-13), idioma (D-04), tema (D-03), credenciales (D-09), 2FA (D-11),
  certificados SSL (D-10), varias IPs por perfil (D-09) y paleta (D-02).
- **Resultado:** ✅ decisiones aprobadas, salvo D-13 (pospuesta) y D-14
  (propuesta, pendiente de confirmar).
- **Archivos:** `docs/decisiones.md`.
- **Siguientes pasos:** confirmar D-14; decidir D-13 en el MVP 4.

### 2026-11-11 · 3. Laboratorio Proxmox
- **Responsable:** orquestador (verificación del equipo) y subagente `devops-ci` (instalación)
- **Qué se hizo:** se comprobó que el equipo (AMD Ryzen AI 9 HX 470, 24 hilos,
  26 GB de RAM, KVM anidado activo) puede alojar el laboratorio. `devops-ci`
  instaló Proxmox VE 9.2.26 sobre Debian 13 en QEMU, en `~/aprovprox-lab/`
  (fuera del repositorio), con el script `lab.sh`
  (crear / iniciar / detener / estado / ssh / destruir). Ver D-15.
- **Resultado:** ⚠️ instalado y probado, pero **apagado**. Pasaron las pruebas de
  versión, ticket de autenticación, storages (`local`, `lab-lvmthin`), bridges
  (`vmbr0` y `vmbr1` VLAN-aware) y crear/borrar una MV por la API. Se perdió el
  permiso temporal (ACL) de `/dev/kvm`; el usuario se agregará al grupo `kvm` y
  reiniciará el equipo.
- **Hallazgo:** parámetros como `net0` deben ir bien codificados o la API responde
  "format error" (corrección 9 de `decisiones.md`).
- **Archivos:** `~/aprovprox-lab/` (fuera del repo), `~/aprovprox-lab/lab.sh`.
- **Siguientes pasos:** tras el reinicio, encender y revalidar. Al terminar **todas**
  las pruebas, eliminarlo sin rastro: `lab.sh destruir` y quitar al usuario del
  grupo `kvm` (D-15).

### 2026-11-11 · 4. Identidad visual
- **Responsable:** orquestador con el usuario
- **Qué se hizo:** nombre **ProxLaunch** (D-01). El usuario entregó tres imágenes PNG y un
  SVG vectorizado automáticamente, de baja calidad (sin degradados, bordes
  irregulares, sin transparencia). Se redibujó como SVG limpio con 6 variantes y
  un generador. Tras un ajuste de contraste (flama naranja y "P" en azul medio en
  el icono) el usuario lo aprobó.
- **Resultado:** ✅ logo aprobado. No cambiarlo sin consultar al usuario (D-01).
- **Archivos:** `recursos/marca/` (logotipo, símbolo, icono e icono sin texto) y
  `recursos/marca/generador/generar_logo.py` (requiere Montserrat, licencia OFL).
- **Siguientes pasos:** aplicar la paleta (D-02) y los temas (D-03) en la interfaz.

### 2026-11-11 · 5. Repositorio git y registro de decisiones
- **Responsable:** orquestador
- **Qué se hizo:** se inicializó el repositorio git (rama `main`, con `.gitignore`)
  y se creó el registro de decisiones.
- **Resultado:** ✅ repositorio creado y primer commit `ab133c0`. Autor configurado solo para este repositorio: `ozz-minia` con un correo de marcador (`ozz-minia@localhost`); cambiarlo si el repositorio se sube a una plataforma remota.
- **Archivos:** `.gitignore`, `docs/decisiones.md`.
- **Siguientes pasos:** mantener `decisiones.md` como fuente de verdad.

### 2026-11-11 · 6. Requisitos del MVP 1
- **Responsable:** subagente `analista-requisitos`
- **Qué se hizo:** redacción de requisitos y criterios de aceptación del MVP 1:
  conexión (token y usuario/contraseña con 2FA), descubrimiento de nodos,
  storages y redes, y crear una MV con disco vacío (D-12).
- **Resultado:** ✅ 27 RF, 16 RNF, 21 reglas de validación, valores por defecto,
  permisos mínimos (por verificar en laboratorio) y casos de error. El orquestador
  lo revisó y corrigió una contradicción (CA-22.6). El usuario aprobó las 15
  preguntas abiertas con la recomendación (D-16) y D-14 pasó a Aprobada.
- **Archivos:** `docs/requisitos/mvp1.md`, `docs/decisiones.md`.
- **Siguientes pasos:** arquitectura e interfaces del MVP 1 (orquestador).

### 2026-11-11 · 7. Arquitectura del MVP 1
- **Responsable:** orquestador
- **Qué se hizo:** diseño de módulos, modelos de datos (`dataclasses`), interfaces entre
  capas, manejo de errores por códigos, hilos de trabajo y plan de implementación por fases.
  Se dejó abierta la decisión ADR-01 (usar `proxmoxer` o `requests` directo para el
  transporte), que resolverá el `investigador`.
- **Resultado:** ✅ aprobada por el usuario.
- **Archivos:** `docs/arquitectura/mvp1.md`.
- **Siguientes pasos:** con la aprobación, F0 (entorno, `devops-ci`) y F1 (ADR-01,
  `investigador`) en paralelo.

### 2026-11-11 · 8. F0 entorno, F2 núcleo y F5a pruebas
- **Responsable:** `devops-ci` (F0), 3 × `implementador` (F2a/b/c), `probador` (F5a), orquestador
- **Qué se hizo:** entorno `.venv` (Python 3.14, PySide6-Essentials 6.12) y esqueleto; núcleo
  puro (modelos, 21 validaciones, capacidades, constructor de parámetros); persistencia,
  llavero y registro con filtro de secretos; paleta, QSS, gestor de tema y fuentes OFL.
  El probador escribió 602 pruebas derivadas de los requisitos.
- **Resultado:** ✅ 602 pruebas en verde, 99 % de cobertura del núcleo. Se corrigieron 3
  defectos (validaciones que aceptaban un salto de línea final).
- **Archivos:** `pyproject.toml`, `src/proxlaunch/`, `tests/`, anexo A de la arquitectura,
  aclaraciones A-1 a A-4 de los requisitos.
- **Siguientes pasos:** F3 (API y servicios).

### 2026-11-11 · 9. F1 investigación y D-17
- **Responsable:** `investigador`; decisión del usuario
- **Qué se hizo:** análisis del código de proxmoxer y de la API de Proxmox (2FA,
  renovación, permisos, parámetros de creación, PySide6/Qt).
- **Resultado:** ✅ se reemplaza `proxmoxer` por `requests` directo (D-17, aprobada por el
  usuario). Se corrigieron la tabla de permisos y la regla V-13 (discard en ide permitido).
- **Archivos:** `docs/investigacion/f1-api-proxmox.md`, `docs/decisiones.md` (D-17),
  aclaraciones A-5 a A-9 de los requisitos.
- **Siguientes pasos:** F3 con las especificaciones de la investigación.

### 2026-11-11 · 10. F3 API y servicios, F4 interfaz, F5b pruebas
- **Responsable:** 2 × `implementador` (F3, F4), `probador` (F5b), orquestador
- **Qué se hizo:** transporte con huella SHA-256 y failover entre IPs; autenticación
  por token y por usuario/contraseña con 2FA en dos pasos y renovación del ticket;
  descubrimiento de nodos, storages y bridges; servicio de creación con seguimiento de
  la tarea. Interfaz completa (formulario, tablas de discos y redes, resumen, progreso,
  diálogos de conexión, huella, 2FA y guía de token).
- **Resultado:** ✅ 1087 pruebas en verde, núcleo al 99 %. El probador detectó 3 defectos,
  corregidos: un POST abortado podía hacer failover y duplicar la creación; errores de
  sesión se mostraban como "nodo caído"; la cancelación no cortaba la espera tolerante.
  Decisión técnica: un 403 en un solo nodo se registra como error de ese nodo y no
  detiene el descubrimiento.
- **Archivos:** `src/proxlaunch/nucleo/api/`, `src/proxlaunch/nucleo/servicios/`,
  `src/proxlaunch/interfaz/`, `tests/nucleo/`; commits e66a6e9, 59cfb9a, d946095.
- **Siguientes pasos:** F5c (pruebas de interfaz, cobertura global ≥ 75 %), F6 laboratorio.

### 2026-11-11 · 11. F5c pruebas de interfaz y F7 revisión
- **Responsable:** `probador` (F5c y regresión F7), `revisor-qa` y `auditor-seguridad` (F7),
  2 × `implementador`, orquestador
- **Qué se hizo:** 587 pruebas de interfaz (pytest-qt). Se corrigieron 2 defectos que
  encontraron (versión forzada no conservada, RF-26; aviso de recurso perdido, CA-11.7) y los
  mensajes con marcadores sin sustituir. Revisión de calidad: 2 altas, 5 medias, 9 bajas;
  auditoría: 0 críticas/altas, 4 medias, 8 bajas. Todas corregidas en una ronda.
- **Resultado:** ✅ 1761 pruebas, cobertura global 98 %. Lo más importante: la app ya no
  puede inducir a crear dos veces la misma MV (envío incierto, «Comprobar» verifica si
  existe; tras el UPID, los errores dan "conexión perdida" y no "error"). El transporte
  falla en cerrado si no hay verificación de huella. Decisión del usuario: D-18 (sin proxy).
- **Archivos:** `src/proxlaunch/`, `tests/**/*_f7.py`, `pyproject.toml`, `docs/decisiones.md`;
  commits a1c37c0, aea1a20, 7b27097, 42a09a4.
- **Por verificar en laboratorio:** texto real de "CT <n> already exists" y cuándo pveproxy
  responde 596 en un POST.
- **Siguientes pasos:** F8 documentación; F6 laboratorio tras el reinicio.

### 2026-11-13 · 12. F6 laboratorio (Proxmox VE 9.2 real)
- **Responsable:** `probador`, `implementador`, orquestador
- **Qué se hizo:** tras el reinicio (usuario en el grupo `kvm`) se encendió el laboratorio.
  86 pruebas de integración contra PVE 9.2.26 con el núcleo real (huella, token, ticket, 2FA
  TOTP y recuperación, renovación, descubrimiento, creación SeaBIOS/OVMF, VMID ocupado por
  VM y por CT, SIN_ESPACIO con un LVM temporal, matriz de permisos). 50 respuestas reales
  saneadas en `tests/datos/respuestas/9.2-lab/` y 79 pruebas de contrato sin red.
- **Resultado:** ✅ sin defectos graves. Rol mínimo real: 10 privilegios (sin
  `VM.Config.Disk` ni `Datastore.Audit`). Se confirmó en vivo que un 596 puede llegar con la
  MV ya creada (la política de "envío incierto" de F7 era necesaria). Corregidos: detalle
  técnico duplicado en 403 reales, estado 597 tratado como incierto, 403 de `VM.Allocate`
  sin detalle (se infiere el privilegio). Guía y README sin marcas de "pendiente" salvo
  realms LDAP/AD. El laboratorio quedó limpio de artefactos de prueba.
- **No reproducible en el laboratorio:** clúster multinodo, nodo caído, PVE 8.x, WARNINGS,
  webauthn/yubico (siguen con respuestas sintéticas).
- **Archivos:** `tests/integracion/`, `tests/datos/respuestas/9.2-lab/`,
  `src/proxlaunch/nucleo/{api/traductor_errores.py, servicios/conexion.py, servicios/creacion.py}`,
  `src/proxlaunch/interfaz/{ayuda.py, textos.py}`, `docs/`.
- **Siguientes pasos:** cierre del MVP 1.

### 2026-11-13 · 13. Cierre del MVP 1
- **Responsable:** orquestador; aprobación del usuario
- **Qué se hizo:** checklist `definicion-de-terminado`. Trazabilidad: los 147 criterios de
  aceptación quedaron citados en pruebas (5 nuevas). Se corrigió CA-23.2 (16 textos que
  lupdate no detectaba por un alias de `translate`) y se añadió la convención.
- **Resultado:** ✅ MVP 1 aprobado. 1884 pruebas normales + 86 de integración contra PVE 9.2,
  cobertura 98 %, sin hallazgos críticos/altos abiertos, sin secretos en el repositorio.
- **Archivos:** commit 03d736c.
- **Siguientes pasos:** MVP 2.

### 2026-11-13 · 14. MVP 2: creación por lotes (F1 a F6)
- **Responsable:** `analista-requisitos`, orquestador (arquitectura), 3 × `implementador` (F3)
  y varios en las correcciones, `probador` (F4, F5), `depurador`, `revisor-qa`,
  `auditor-seguridad`, `documentador`; decisiones del usuario D-20 y D-21.
- **Qué se hizo:** requisitos (24 RF-L, 11 RNF-L) y 12 decisiones de lotes (D-20); arquitectura
  (planificación pura, reserva de VMIDs, reparto Equilibrado/Por turnos, presupuesto de
  espacio con tope thin 3×, motor con colas por nodo, reconciliación del envío incierto,
  pausas, rollback, simulación de solo lectura, informe saneado). Una sola MV también pasa por
  el motor. Pruebas: unitarias con inyección de fallos en todos los puntos (INV-L1), contadores
  de métodos, centinela de secretos e interfaz; LAB-L01..L13 en PVE 9.2.
- **Resultado:** ✅ 3480 pruebas normales + 142 de integración en verde; INV-L1 (como máximo un
  POST por VMID) sin excepción en ninguna ruta. El laboratorio encontró 3 defectos (etiqueta
  rechazada en la tarea, config en `lock: create`, 596 tras entrega), corregidos. Revisión:
  3 altas, 5 medias, 8 bajas; auditoría: 0 críticas/altas, 2 medias, 4 bajas; todas
  corregidas. D-21 (usuario): deshacer sin borrar discos sueltos. Regresión detectada en la
  documentación y corregida: una sola MV con etiquetas restringidas ofrece «Crear sin
  etiquetas».
- **Hallazgos del laboratorio:** ver `docs/investigacion/f1-api-proxmox.md` §8 (DELETE solo
  exige `VM.Allocate`, efidisk de 4 MiB, normalización de etiquetas, MV recién creada sin
  nombre ~4 s en `/cluster/resources`).
- **Archivos:** `src/proxlaunch/nucleo/lote/`, `src/proxlaunch/interfaz/`, `tests/`,
  `docs/requisitos/mvp2.md`, `docs/arquitectura/mvp2.md`, `docs/guia-usuario.md`, `README.md`;
  commits f9e5bbc a b1dec89.
- **Cierre:** ✅ aprobado por el usuario (2026-11-13).
- **Siguientes pasos:** MVP 3.

### 2026-11-13 · 15. Requisitos del MVP 3
- **Responsable:** `analista-requisitos`; revisión del orquestador
- **Qué se hizo:** `docs/requisitos/mvp3.md`: 12 RF de perfiles de máquina, 5 de archivos
  seguros, 8 de lotes guardados y 15 de CSV; 12 RNF-M, 15 reglas V-M, 16 errores E-M,
  8 invariantes, 4 pruebas de laboratorio, 6 perfiles de fábrica y 12 preguntas P-M.
- **Resultado:** ⏳ el usuario pidió (estando ausente) avanzar solo y esperar únicamente
  ante decisiones suyas. P-M01 (cómo encaja un CSV con MVs distintas en el lote homogéneo
  de D-20) cambia una decisión aprobada: se le consulta. Las demás P-M (02 a 12) se adoptan
  de forma provisional con la recomendación del analista, para revisión del usuario.
- **Archivos:** `docs/requisitos/mvp3.md`.
- **Decisión:** el usuario eligió P-M01 A, lote por filas (D-22, 2026-11-14).
- **Siguientes pasos:** arquitectura del MVP 3.

### 2026-11-14 · 16. MVP 3: arquitectura, implementación, pruebas y revisión (F2 a F7)
- **Responsable:** orquestador; `implementador` (núcleo A/B/C, interfaz F4a/F4b y correcciones),
  `probador` (núcleo, interfaz, laboratorio), `revisor-qa`, `auditor-seguridad`, `documentador`
- **Qué se hizo:** arquitectura (`docs/arquitectura/mvp3.md`); núcleo de archivos seguros,
  perfiles de máquina, lotes guardados, importación CSV y lote por filas por un único camino
  (`filas_efectivas`; motor, libro, rollback y simulación sin cambios); interfaz (selector de
  perfil, menús «Lote» y «Perfiles», 6 diálogos, panel de lote por filas, cambios sin guardar).
- **Resultado:** ✅ 5823 pruebas normales y 154 de laboratorio en verde; ruff, mypy y catálogo
  de traducción limpios. Las pruebas encontraron 11 defectos (corregidos). QA: 2 altos, 2 medios,
  6 bajos; seguridad: 0 críticos, 1 alto (JSON con coste cuadrático), 1 medio (fórmulas tras
  separador interno), 7 bajos; todos corregidos y con pruebas. Decisiones técnicas en D-23.
- **Archivos:** `src/proxlaunch/nucleo/{archivos,perfiles_maquina,lotes_guardados,csv_importacion}/`,
  `nucleo/lote/filas.py`, `src/proxlaunch/interfaz/` (diálogos y vistas nuevos), `tests/`.
  Commits 849c35a, 30fdf45, 92a903d, 9625522, 8a29e08.
- **Siguientes pasos:** aprobación del usuario; después MVP 4 (requiere decidir D-13).
  Documentación cerrada en e90b183.

### 2026-11-14 · 17. MVP 4: arquitectura, implementación, pruebas y revisión (F2 a F7)
- **Responsable:** orquestador; `implementador` (núcleo, interfaz y correcciones), `probador` (núcleo,
  interfaz y laboratorio), `revisor-qa`, `auditor-seguridad`, `documentador`
- **Qué se hizo:** arquitectura (`docs/arquitectura/mvp4.md`) y el origen del sistema operativo por un
  único camino en el núcleo: disco vacío, ISO (con asistente de SO y, para Windows, segundo CD
  virtio-win, q35, OVMF y TPM), importar qcow2 (Proxmox ≥ 8.4, storage con contenido «import») y
  clonar plantillas (enlazado si se puede, si no completo; hasta 3 clones enlazados simultáneos por
  nodo). Subida de archivos desde el equipo y descarga por URL en el servidor, con SHA-256. Storages
  detectados por contenido y recordados por servidor. Rol de 14 privilegios y 9 perfiles de fábrica
  (nuevos: `windows-11`, `windows-server`, `linux-red-hat`). Interfaz: selector de origen y
  diálogos de catálogo, transferencia, archivos subidos en la sesión, elegir almacenamiento y
  capacidades. Perfiles, lotes guardados y CSV con origen. OVA y migración desde VMware quedan fuera
  (D-24).
- **Resultado:** ✅ 7226 pruebas normales y 232 de laboratorio en verde; ruff, mypy y catálogo de
  traducción limpios. Laboratorio PVE 9.2: DEFECTO-LAB-01, DEFECTO-LAB-02, HALLAZGO-LAB-03 y
  DEFECTO-F7-01 (corregido en `c850689`), y en las pruebas del núcleo F6-01..03; todos corregidos.
  Revisión QA: 12 hallazgos (QA-M4-01..12), corregidos salvo QA-M4-09 (cancelar una subida no es
  inmediato; queda documentado). Seguridad: SEG-M4-01..12 corregidos y SEG-M4-13 (residuos
  `/var/tmp/pveupload-*`) informativo, documentado en la guía. Decisiones técnicas en D-26. Hechos
  medidos en el laboratorio y desviaciones: `docs/arquitectura/mvp4.md`, Anexo B. Guía de usuario
  ampliada (origen del SO y permisos acotados).
- **Archivos:** `src/proxlaunch/nucleo/{origen,transferencias}/`, `nucleo/lote/{cupos,ajustes}.py`,
  `nucleo/api/multipart.py`, `src/proxlaunch/interfaz/` (selector, controlador y diálogos del
  origen), `tests/`, `docs/guia-usuario.md`, `docs/arquitectura/mvp4.md`. Commits f8f7e3b (F4
  núcleo), 55c67c7 y 95a934b (F5 interfaz), a15ef3f, 8d8b3f9 y 4957753 (F6 pruebas y laboratorio),
  c850689 y 9b8dccc (F7).
- **Siguientes pasos:** MVP 4 aprobado por el usuario (2026-11-14); siguiente, MVP 5 (instaladores y CI).

### 2026-11-15 · 18. MVP 5: instaladores, scripts de empaquetado y verificación (F2 a F7)
- **Responsable:** orquestador; `analista-requisitos`, `implementador` (versión, argumentos y prueba de
  humo), `devops-ci` (scripts, MVs, instaladores), `probador`, `revisor-qa`, `auditor-seguridad`,
  `documentador`
- **Qué se hizo:**
  - App (único cambio de `src/` además de las correcciones de I-1 a I-4): versión única `0.5.0`,
    `--version`, `--prueba-de-humo` y `--permitir-sin-llavero`.
  - Instalador de Ubuntu: `.deb` (22.04 y 24.04, `amd64`) construido en una MV Ubuntu 22.04 por la
    glibc; dependencias del sistema declaradas y `gnome-keyring` sugerido; `.desktop` e iconos
    `hicolor`. Instalador de Windows: Inno Setup (`-setup.exe`, 64 bits, Windows 10 o posterior),
    «solo para mí» por defecto o «para todos los usuarios», asistente en español, sin firma.
  - Scripts en `empaquetado/`: calidad, construcción, verificación del artefacto instalado,
    orquestador `verificar-todo.sh`, MVs QEMU (`mv.sh`), lockfiles con hashes, sumas con sello
    (INV-E6), avisos de terceros, presupuesto de tamaño y plantilla de CI inactiva.
  - Decisiones del usuario en D-27: CI solo como plantilla; `.deb` para Ubuntu; sin firma; datos
    conservados al desinstalar con opción de borrarlos; icono regenerado y aprobado; editor
    «ProxLaunch» sin correo; MV de Windows en este equipo con ISO de consumo descargada por el
    usuario; exclusión mutua con el laboratorio; «para todos» sin borrado; actualización probada con
    una build que no se publica; se conserva `build/registros/crear-windows11.txt`.
- **Verificaciones (resultados):**
  - Suite local: 7517 pruebas correctas.
  - `verificar-todo.sh linux`: correcto (`.deb` instalado en Ubuntu 22.04 y 24.04, humo,
    `remove`/`purge` sin residuos).
  - `verificar-todo.sh windows`: correcto en Windows 11 con TPM 2.0 y Secure Boot: instalación por
    usuario, humo con el llavero real (`WinVaultKeyring`), desinstalación sin residuos, reinstalación
    con una sola entrada, `/BORRARDATOS=1` solo en ese usuario con el llavero intacto, y modo «para
    todos» que ignora `/BORRARDATOS=1`.
  - `actualizacion-linux` y `actualizacion-windows`: correctos (0.5.0 → 0.5.1 de prueba; datos
    intactos byte a byte).
  - `dist/SHA256SUMS` con los dos artefactos: el `.deb` (`a758b0c4…`) y el `-setup.exe`
    (`f8737c07…`).
- **Incidencias resueltas** (detalle en `docs/arquitectura/mvp5.md`, Anexo B.2):
  - reintento de `os.replace` ante bloqueos de Windows (I-1);
  - límite `MAX_PATH` (≥ 260) en la escritura atómica (I-2);
  - informes parciales en `Rutas.informes` tras una fuga de pruebas a la carpeta real, ya limpiada (I-3);
  - aislamiento de carpetas en `tests/conftest.py` (I-4);
  - vigilante del humo a 15 s con respaldo `faulthandler`, arbitraje y cierre del registro (I-5);
  - `.Count` en `StrictMode` de PowerShell 5.1 (I-6);
  - QA-M5-01 (crítico): `paso` ignoraba `set -e` y llegó a sellar un `.deb` viejo; corregido con
    autotest (I-7);
  - un `lib.ps1` con error de sintaxis salía con 0; ahora `$ErrorActionPreference` va antes de cargarla
    y el analizador de PowerShell de la MV valida los `.ps1` (I-8);
  - subprocesos de prueba con `PYTHONPATH` (I-9);
  - red de la MV de Windows pública → privada en `preparar.ps1` (I-10);
  - desinstalador con Sí/No en lugar de casilla, `AppMutex` sin efecto, ISO de consumo en lugar de la
    de evaluación, `Categories=Network;` y sumas tras verificar (B-3 a B-7).
- **Pendientes que quedan abiertos:**
  - RF-E21b, auditoría de CVE («Debería»): no implementada.
  - Exclusión inversa (que `lab.sh` rechace arrancar con MVs de empaquetado): no implementada.
  - Semilla cloud-init por disco vvfat: sin probar en una MV nueva (las MVs ya existían).
  - Firma de código: preparada y desactivada.
  - `directorio_lotes` ya es obligatorio en las dependencias de la ventana: cerrado.
- **Comprobaciones manuales** (2026-11-15, con el usuario, en la MV Windows 11):
  - SmartScreen: aparece el aviso y se continúa con «Más información → Ejecutar de todas formas» ✅.
  - Asistente de instalación: íntegramente en español ✅.
  - Icono aprobado en la barra de tareas, la ventana y el menú Inicio ✅.
  - Escalado 125 % y 150 % ✅. Al 175 % (forzado por registro sobre una pantalla de 1024 × 768) todo se veía
    nítido, pero el diálogo «Conectar con Proxmox» no cabía y sus botones quedaban fuera: **corregido** (I-11,
    I-12) y comprobado de nuevo por el usuario ✅ (barra de desplazamiento y botones siempre visibles).
  - Limitación conocida: en esa combinación forzada el asistente de Inno Setup (tamaño fijo) tampoco cabe; se
    avanza con Enter. Documentado en la guía de usuario.
  - M-E6 (escritorio Ubuntu con Wayland): no realizada (opcional).
- **Correcciones posteriores a la documentación inicial:**
  - Ventanas y diálogos acotados al área útil de la pantalla (`interfaz/desplazable.py`), con contenido
    desplazable y botones fijos; con pantalla holgada crecen hasta lo que pide su contenido (sin barras con
    fuentes anchas como las de Windows). Commits `adfdc6a`, `36a846c`, `445eb38`.
  - Carrera en la prueba de guardar lote (leía la barra de estado antes de la señal en cola): corregida en la prueba.
  - MV Windows de pruebas: sshd terminaba de forma inesperada y Windows Update instalaba en segundo plano;
    sshd se reinicia solo y las actualizaciones automáticas quedan desactivadas en esa MV (commit `3178cd2`).
  - Verificación de Windows: falla si el humo deja carpetas en `%TEMP%` (QA-M5-03, confirmado en la MV con
    restos anteriores a la corrección).
- **Verificación final** con el código definitivo: `linux` ✅, `windows` ✅ (calidad 7638 en Windows, 7691 en
  Ubuntu, 7693 local), `actualizacion-linux` ✅. Sumas: `.deb` `daa8b3dc…`, `-setup.exe` `5c39a384…`.
- **Archivos:** `empaquetado/` (completo; ver `empaquetado/LEEME.md`), `src/proxlaunch/interfaz/{app,humo}.py`,
  `src/proxlaunch/nucleo/archivos/reemplazo.py`, `tests/conftest.py`, `docs/requisitos/mvp5.md`,
  `docs/arquitectura/mvp5.md`, `docs/empaquetado.md`, `docs/guia-usuario.md`, `docs/decisiones.md`
  (D-27), `README.md`. Últimos commits del MVP: `5a5a2c8`, `527a5dc`, `683703a`, `431064d`, `9c9bbfb`.
- **Siguientes pasos:** aprobación del usuario y limpieza total
  (`mv.sh destruir-todo`, laboratorio incluido según D-15).

---

## Pendientes y riesgos abiertos

| Tema | Detalle |
|---|---|
| Eliminación del laboratorio | Obligatoria al final de las pruebas, sin dejar rastro (D-15). |
| D-13 resuelta | Resuelta por D-24 (MVP 4): ISO, importar qcow2 y clonar plantilla. OVA y migración desde VMware quedan fuera del alcance. |
| QA-M4-09 | Cancelar una subida no es inmediato: tarda hasta 10 s al conectar y hasta 120 s mientras se espera la respuesta tras enviar el cuerpo; cerrar la app puede tardar unos 6 s. No corregido; ver el comentario en `nucleo/api/transporte.py`. |
| Residuos `pveupload` (SEG-M4-13) | Algunos rechazos de subida dejan `/var/tmp/pveupload-*` en el nodo y el rol no puede borrarlos (no tiene `Datastore.Allocate`). Subidas fallidas repetidas pueden llenar la raíz; la app avisa si queda poco espacio. El administrador debe limpiar de vez en cuando. |
| ISO de Windows real | No probado: el laboratorio solo usa Alpine/Linux. El hardware de Windows (OVMF, TPM, virtio-win) se comprobó sin instalar Windows. |
| Importación en PVE 8.x | La importación de discos (8.4 o superior) se probó solo con dobles; el laboratorio es PVE 9.2. |
| Plantillas ajenas visibles | Con la guía de permisos acotada, `VM.Audit` no queda limitado al pool: las demás plantillas se ven en la lista, pero la app no las clona (V-O17). |
| Python en Ubuntu 22.04 | Resuelto en el MVP 5: el `.deb` incluye su propio intérprete. Para desarrollo desde el código fuente sigue haciendo falta Python ≥ 3.11. |
| Realms LDAP/AD | No probados. |
| Firma de código en Windows | MVP 5: sin firma (D-27). El paso de firma está preparado y desactivado (`PROXLAUNCH_FIRMA_CONFIG`); el usuario ve SmartScreen. |
| Asistente de instalación con escala alta | En pantallas muy pequeñas con escala alta (1024 × 768 al 175 %) el asistente de Inno Setup no cabe; se avanza con Enter. ProxLaunch sí se adapta. |
| Escritorio Ubuntu con Wayland (M-E6) | Comprobación manual opcional no realizada. |
| Auditoría de CVE (RF-E21b) | «Debería»; no implementada. |
| Exclusión inversa del laboratorio | Solo las MVs de empaquetado rechazan arrancar con el laboratorio activo; el laboratorio no comprueba lo contrario. |
| Semilla cloud-init vvfat | Sin probar en una MV nueva de Ubuntu (las existentes ya estaban creadas). |
| Limpieza de las MVs de empaquetado | `empaquetado/entornos/mv.sh destruir-todo` al cerrar el MVP (RF-E41). |
| Respuestas sintéticas | Clúster multinodo, nodo caído y PVE 8.x solo con respuestas sintéticas (el laboratorio es un nodo 9.2). |
| Clúster multinodo de lotes | Reparto, nodo caído y concurrencia entre nodos probados solo con dobles (laboratorio de un nodo). |
| Aviso de nombre duplicado | Una MV creada hace ~4 s puede no aparecer con nombre en `/cluster/resources` (limitación de Proxmox). |
| Sin Proxmox de pruebas en los sitios | Nunca crear ni borrar MVs contra producción (D-15). |
| Windows real (MVP 3) | «Archivo bloqueado» (WinError 5 al reemplazar) y rutas largas del temporal probados solo con simulación. |
| Bloqueo por nodo elegido inexistente | Solo en la interfaz; el núcleo acepta el lote si queda algún nodo válido. |
| Tooltips de MVP 1/2 | Muestran texto del propio usuario sin escapar (riesgo bajo). |
| Intermitencia del laboratorio | Justo tras arrancar, el nodo puede verse «sin conexión» unos instantes (3 fallos en 2 ejecuciones; luego 12/12). |
