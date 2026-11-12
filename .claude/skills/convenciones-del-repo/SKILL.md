---
name: convenciones-del-repo
description: "Convenciones del proyecto: estructura, estilo, nombres y patrones, detectadas del propio repositorio. Usar al escribir, modificar o refactorizar código."
---
# Convenciones del repositorio (genérico, válido para cualquier proyecto)

Este skill no asume ningún lenguaje ni framework: lo detectas en cada proyecto.

## Procedimiento
1. **Reglas explícitas del proyecto.** Si existe `.claude/proyecto/convenciones.md`
   y NO contiene la línea `ESTADO: SIN COMPLETAR`, léelo y síguelo; prevalece
   sobre cualquier detección.
2. **Detecta el stack.** Busca manifiestos: `package.json`, `pyproject.toml`,
   `requirements.txt`, `pom.xml`, `build.gradle*`, `*.csproj`/`*.sln`, `go.mod`,
   `Cargo.toml`, `composer.json`, `Gemfile`, `Makefile`.
3. **Detecta estilo.** Busca configuración de linter y formateador
   (`.editorconfig`, `.eslintrc*`, `.prettierrc*`, `ruff.toml`, secciones
   `[tool.*]` en `pyproject.toml`, `checkstyle`, etc.), `README` y `CONTRIBUTING`.
4. **Aprende por muestreo.** Lee 3-5 archivos representativos para ver nombres,
   estructura de carpetas, manejo de errores y patrones. Imita el código
   existente; si hay conflicto con una guía escrita, gana el código vigente.
5. **Reporta lo detectado** en "Riesgos o hallazgos": stack, convenciones
   asumidas y comandos de lint/build encontrados, para que el usuario los confirme.

## Principios universales
- Cambios mínimos y dentro del alcance del brief.
- No agregues dependencias nuevas sin que el brief lo pida.
- No mezcles refactor con cambios funcionales.
- Los comentarios nuevos van en español.
