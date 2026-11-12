# Bitácora del proyecto — ProxLaunch

## Propósito y uso

Registro cronológico de lo que se hizo en el proyecto y con qué resultado, para
que cualquiera pueda retomarlo. Las decisiones de fondo viven en
`decisiones.md` (D-01 a D-15); aquí solo se remite a ellas. La especificación
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

## Estado actual (2026-11-11)

- **Fase en curso:** arquitectura e interfaces del MVP 1 (orquestador). Requisitos
  aprobados en `docs/requisitos/mvp1.md`.
- **Bloqueo (⚠️):** el laboratorio Proxmox está **apagado**. Se perdió el permiso
  temporal (ACL) de `/dev/kvm`. El usuario se agregará al grupo `kvm` y
  reiniciará el equipo.
- **Próximo paso:** documentar la arquitectura del MVP 1 y, tras el reinicio,
  encender el laboratorio con `lab.sh iniciar` para verificar permisos y formatos.

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

---

## Pendientes y riesgos abiertos

| Tema | Detalle |
|---|---|
| Laboratorio apagado | Requiere grupo `kvm` y reinicio del equipo antes de seguir validando. |
| Eliminación del laboratorio | Obligatoria al final de las pruebas, sin dejar rastro (D-15). |
| D-13 pospuesta | Origen del SO (ISO, OVA, VMware): algunas importaciones exigen `root@pam` o SSH y dependen de la versión (MVP 4). |
| Política de sobreasignación | Bloquear o advertir en pools thin: se define en el MVP 2. |
| Firma de código en Windows | Pospuesta al MVP 5 (D-06). |
| Permisos de Proxmox | Lista mínima para el API Token por definir en los requisitos (D-09). |
| Sin Proxmox de pruebas en los sitios | Nunca crear ni borrar MVs contra producción (D-15). |
