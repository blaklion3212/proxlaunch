---
name: reporte-de-avance
description: "Formato de reportes de subagentes y de avances al usuario: estados, tablero de fases y cierre de fase. Usar al delegar, al reportar progreso y antes de pedir aprobación."
---
# Reporte de avance

Todo en español.

## Estados
⏳ en curso | ✅ completada | ⚠️ bloqueada | ❌ fallida

## Reporte de subagente (5 secciones, en este orden)
1. **Resumen:** qué se hizo, 2-3 líneas.
2. **Progreso:** hecho / pendiente, con porcentaje aproximado.
3. **Archivos o artefactos:** rutas tocadas o generadas.
4. **Riesgos o hallazgos:** lo que el orquestador debe saber.
5. **Preguntas:** dudas para el usuario (vacío si no hay). El subagente no
   pregunta al usuario directamente.

## Tablero del orquestador (varias fases o trabajo en paralelo)
| Fase | Responsable | Estado | Avance |
|---|---|---|---|

## Cierre de fase (antes de pedir aprobación)
- Qué se logró
- Qué falta
- Decisiones tomadas
- Riesgos abiertos
- Qué se hará en la siguiente fase
