"""Constantes del lote (docs/requisitos/mvp2.md §5, decisión D-20).

Cada valor es la única fuente para núcleo e interfaz (CA-L01.4).
"""

MAX_LOTE = 100  # P-L07
MAX_SALTO_VMID = 1000  # ventana de búsqueda de VMIDs libres
VMID_MINIMO = 100
VMID_MAXIMO = 999_999_999
NUMERO_NOMBRE_MAXIMO = 999_999
RELLENO_MAXIMO = 8
FACTOR_THIN_MAX = 3  # P-L01: aviso hasta 3 × libre; por encima, error
UMBRAL_CONFIRMACION_DOBLE = 10  # CA-L10.4
UMBRAL_PAUSA_ERRORES = 3  # P-L09
MAX_NODOS_PARALELOS = 4  # P-L05
MAX_PETICIONES_SIMULTANEAS = 8
MAX_CONSULTAS_SIMULTANEAS = 8  # reserva de VMIDs
COMPROBACIONES_EXISTENCIA_S = (0.0, 5.0, 15.0)  # CA-L15.2 (esperas acumuladas)
PLAN_MAX_EDAD_S = 300.0  # V-L14
TAM_EFIDISK_MIB = 4  # LAB-L04 lo confirma
ACTUALIZACIONES_POR_S = 10  # interfaz (CA-L13.5)
LINEAS_LOG_TAREA = 50  # por MV con avisos o error (RNF-L05)
ETIQUETA_APP = "proxlaunch"
PREFIJO_ETIQUETA_LOTE = "lote-"
