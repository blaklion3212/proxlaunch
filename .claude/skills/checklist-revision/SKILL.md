---
name: checklist-revision
description: "Criterios de revisión de código: lógica, manejo de errores, concurrencia, rendimiento y mantenibilidad. Usar al revisar código o diseño."
---
# Checklist de revisión

## Lógica
- Condiciones límite, off-by-one, nulos y vacíos.
- Casos no cubiertos por los requisitos.

## Errores
- Excepciones tragadas, mensajes sin contexto, recursos no liberados.
- Reintentos y timeouts razonables.

## Concurrencia
- Estado compartido sin protección, race conditions, deadlocks.
- Operaciones no idempotentes que se pueden repetir.

## Rendimiento
- Consultas o bucles repetidos innecesarios, cargas completas en memoria.

## Mantenibilidad
- Interfaces claras, duplicación, funciones demasiado largas, nombres engañosos.

## Cómo reportar
Cada hallazgo: severidad (crítico/alto/medio/bajo), archivo y línea,
escenario de fallo y corrección sugerida.
