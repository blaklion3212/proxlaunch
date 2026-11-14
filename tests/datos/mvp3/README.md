# Archivos de ejemplo del MVP 3

Entradas sintéticas (sin datos reales) para las pruebas de perfiles, lotes guardados e importación CSV.

- `perfiles-v1.json`, `lote-homogeneo-v1.json`, `lote-por-filas-v1.json`: un archivo de ejemplo de la
  versión 1 de cada formato (CA-X01.3). Cuando exista la versión 2 se añadirá aquí el ejemplo de la v1
  que debe migrar.
- `excel-windows1252.csv` (`;`, Windows-1252, decimal con coma), `utf8-bom-comas.csv` (`,`, UTF-8 con BOM),
  `utf16-le.csv` (UTF-16 LE con BOM), `sep-linea.csv` (primera línea `sep=;`), `formulas.csv` (celdas con
  disparadores de fórmula).
- `perfiles-truncado.json`, `lote-utf8-invalido.json`, `lote-version-futura.json`: archivos dañados o de
  una versión posterior.

Se regeneran con `generar_datos.py` (en esta carpeta); los bytes exactos importan (codificación y BOM).
