---
name: estrategia-de-pruebas
description: "Estrategia de pruebas: principios, detección del framework y comandos del proyecto, y cobertura. Usar al escribir o ejecutar pruebas."
---
# Estrategia de pruebas (genérica, válida para cualquier proyecto)

## Procedimiento
1. **Reglas explícitas del proyecto.** Si existe `.claude/proyecto/pruebas.md` y
   NO contiene la línea `ESTADO: SIN COMPLETAR`, léelo y síguelo; prevalece.
2. **Detecta el framework de pruebas.** Señales comunes: pytest/unittest,
   jest/vitest/mocha, JUnit/TestNG, xUnit/NUnit/MSTest, `go test`, `cargo test`,
   PHPUnit, RSpec.
3. **Detecta comandos.** Revisa scripts de `package.json`, `Makefile`, `tox`,
   `pyproject.toml`, `pom.xml`/`build.gradle` y los workflows de CI
   (`.github/workflows`, `.gitlab-ci.yml`, etc.). Usa los comandos que el CI ya ejecuta.
4. **Detecta convenciones de pruebas:** carpeta, nombres de archivo y estilo de las
   pruebas existentes. Imítalas.
5. **Si no hay framework de pruebas,** repórtalo y propón la opción habitual del
   stack; no instales nada sin aprobación del usuario.
6. **Reporta lo detectado** (framework, comandos, cobertura actual si existe) en
   "Riesgos o hallazgos".

## Principios universales
- Las pruebas se derivan de los requisitos y de las interfaces públicas, no del
  código ya escrito.
- Cubre camino feliz, casos límite, errores y entradas inválidas.
- Una prueba, una razón para fallar; sin dependencias entre pruebas.
- Mocks solo en los límites del sistema (red, disco, reloj, servicios externos).
- Nunca debilites ni borres una prueba para hacerla pasar; reporta el fallo.
- Cobertura: respeta el umbral configurado en el proyecto; si no hay, no inventes
  uno y repórtalo.
