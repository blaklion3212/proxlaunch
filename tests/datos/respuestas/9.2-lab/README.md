# Respuestas REALES de PVE 9.2 (laboratorio), saneadas

Capturadas con `tests/integracion/capturar_respuestas.py` contra el laboratorio local
(Proxmox VE 9.2.26, nodo `pve-lab`, servidor individual). Mismos nombres que en `../9.2/`
cuando aplica; los archivos adicionales (`error_*`, `permisos_sin_*`, ...) son casos reales
nuevos. `_http.json` guarda el estado HTTP y la frase de estado de cada respuesta (Proxmox
pone ahí el mensaje corto del error).

Saneado: tickets (la firma queda como `FIRMA_SANEADA`), CSRF, huellas, UPIDs (numerados
`0000000N`), digests y cualquier secreto de la ejecución se reemplazan por marcadores. Los
tokens, contraseñas, códigos TOTP y claves de recuperación se registran en memoria y se
verifica al final que ninguno quedó en disco. Los pid/pstart/starttime de las tareas son
valores fijos por coherencia con el UPID saneado.

Pruebas que las usan: `tests/nucleo/test_respuestas_reales_lab.py` (sin red).
No hay captura de `WARNINGS`, de clúster de varios nodos ni de desafíos webauthn/yubico.
