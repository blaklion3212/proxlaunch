"""Límites y formatos de los archivos del MVP 3 (docs/requisitos/mvp3.md §6).

Cada valor es la única fuente para núcleo e interfaz. ``MAX_LOTE`` no se redefine aquí:
se importa de ``proxlaunch.nucleo.lote.constantes`` (CA-C15.2).
"""

VERSION_FORMATO = 6  # versión MÁXIMA que se lee de los formatos JSON propios (fase D, RF-D6.1)
VERSION_FORMATO_FASE_C = 5  # la que se escribe si el archivo usa algo de la fase C y nada de la D
VERSION_FORMATO_FASE_B = 4  # la que se escribe si el archivo usa algo de la fase B y nada de la C
VERSION_FORMATO_FASE_A = 3  # la que se escribe si el archivo usa algo de la fase A y nada de la B
VERSION_FORMATO_MVP4 = 2  # la que se escribe si el archivo usa algo del MVP 4 y nada de la fase A
VERSION_FORMATO_BASE = 1  # la que se escribe cuando el archivo no usa nada del MVP 4 (DT-O15)
LONG_NOMBRE_PERFIL = 60
LONG_DESCRIPCION = 200
MAX_LONG_TEXTO = 256
MAX_LONG_CELDA = 256
MAX_LONG_NOTAS = 8192  # notas de la MV (límite de ``description`` de Proxmox, DT-A11)
MAX_LONG_CLAVES = 8192  # celda ``ci_claves`` del CSV (claves públicas de cloud-init, DT-B13)
MAX_PERFILES_USUARIO = 100
MAX_PERFILES_ARCHIVO = 100
MAX_BYTES_PERFILES = 256 * 1024  # 256 KiB
MAX_BYTES_LOTE = 1024 * 1024  # 1 MiB
MAX_BYTES_CSV = 1024 * 1024  # 1 MiB
MAX_COLUMNAS_CSV = 70  # DT-A11 y P-C4: las columnas de las fases A y C suben el tope
# Celda ``mapeo_pci``/``mapeo_usb`` (fase D): hasta 16 ids de 64 caracteres separados por «;».
MAX_LONG_CELDA_MAPEOS = 16 * 65
PROFUNDIDAD_JSON_MAX = 8
LINEAS_DETECCION = 20  # líneas que se inspeccionan para detectar el separador
MAX_PROBLEMAS_FILA = 5
MEMORIA_AVISO_GIB = 1024
