# Respuestas simuladas de la API de Proxmox VE

**ATENCIÓN: estas respuestas son SINTÉTICAS.** Se construyeron a mano a partir de la
investigación `docs/investigacion/f1-api-proxmox.md` (formatos de ticket parcial `PVE:!tfa!`,
`NeedTFA`, renovación, errores de VMID, `Permission check failed (...)`) y de la
documentación de la API. **No se han capturado en el laboratorio.** Hasta que se capturen y
anonimicen respuestas reales, RNF-05 y RNF-09 solo se cumplen de forma provisional.

Subcarpetas por versión de Proxmox: `9.2/` y `8.0/` (mismos nombres de archivo).
Cada archivo es el cuerpo completo de la respuesta (`{"data": ...}`).

| Archivo | Endpoint o situación |
|---|---|
| `version.json` | `GET /version` |
| `nextid.json` | `GET /cluster/nextid` |
| `cluster_status*.json` | `GET /cluster/status` (clúster de 3 nodos, individual, un nodo con `online: 0`) |
| `nodes*.json` | `GET /nodes` (3 nodos, individual, un nodo `offline`, sin `Sys.Audit`) |
| `storage.json` | `GET /nodes/{n}/storage` (con `active: 0`, `enabled: 0` y un tamaño fraccionario) |
| `network.json` | `GET /nodes/{n}/network` (eth, bridge, OVSBridge, bond, vlan, OVSPort) |
| `permisos_*.json` | `GET /access/permissions` |
| `ticket_completo.json`, `ticket_renovado.json` | `POST /access/ticket` correcto y renovación |
| `ticket_tfa_*.json` | `POST /access/ticket` con 2FA: ticket parcial con el desafío escapado |
| `crear_vm_upid.json` | `POST /nodes/{n}/qemu` (UPID) |
| `tarea_status_*.json`, `tarea_log.json` | estado y log de la tarea |
| `qemu_config.json` | `GET /nodes/{n}/qemu/{vmid}/config` |
| `error_*.json` | cuerpos de error (VMID ocupado, permisos, configuración inexistente) |

Nota: en Proxmox real el mensaje corto del error viaja también en la frase de estado HTTP
(`HTTP/1.1 500 VM 100 already exists ...`). Las pruebas lo reproducen con
`RespuestaConMotivo` en `tests/nucleo/apoyo_api.py`.

Pendiente de laboratorio: sustituir estos archivos por capturas reales anonimizadas y
confirmar los textos exactos de error en 8.x y 9.2 (requisitos, sección 10, puntos 3, 4 y 6).
