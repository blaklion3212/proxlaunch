"""Límites y formatos de los archivos del MVP 3 (docs/requisitos/mvp3.md §6).

Cada valor es la única fuente para núcleo e interfaz. ``MAX_LOTE`` no se redefine aquí:
se importa de ``proxlaunch.nucleo.lote.constantes`` (CA-C15.2).
"""

VERSION_FORMATO = 1  # versión actual de los formatos JSON propios
LONG_NOMBRE_PERFIL = 60
LONG_DESCRIPCION = 200
MAX_LONG_TEXTO = 256
MAX_LONG_CELDA = 256
MAX_PERFILES_USUARIO = 100
MAX_PERFILES_ARCHIVO = 100
MAX_BYTES_PERFILES = 256 * 1024  # 256 KiB
MAX_BYTES_LOTE = 1024 * 1024  # 1 MiB
MAX_BYTES_CSV = 1024 * 1024  # 1 MiB
MAX_COLUMNAS_CSV = 40
PROFUNDIDAD_JSON_MAX = 8
LINEAS_DETECCION = 20  # líneas que se inspeccionan para detectar el separador
MAX_PROBLEMAS_FILA = 5
MEMORIA_AVISO_GIB = 1024
