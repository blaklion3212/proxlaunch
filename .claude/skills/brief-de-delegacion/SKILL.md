---
name: brief-de-delegacion
description: "Plantilla del brief obligatorio al delegar en un subagente. Usar siempre antes de invocar a un subagente."
---
# Brief de delegación

Los subagentes no ven la conversación. Todo encargo incluye:

1. **Objetivo:** qué debe lograr, en una o dos frases.
2. **Contexto mínimo:** rutas de archivos, interfaces, decisiones previas y
   requisitos que aplican (cita `docs/requisitos/...` si existe).
3. **Alcance:** qué puede tocar y qué NO.
4. **Restricciones:** convenciones, dependencias, compatibilidad.
5. **Formato de salida:** el reporte de 5 secciones de `reporte-de-avance`.
6. **Criterio de aceptación:** cómo sabremos que está terminado.

## Plantilla
```
Objetivo:
Contexto:
Alcance (sí / no):
Restricciones:
Entregable y formato:
Criterio de aceptación:
```

Un brief que no cabe en una pantalla suele indicar que la tarea debe dividirse.
