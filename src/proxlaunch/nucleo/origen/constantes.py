"""Constantes del origen del SO (docs/requisitos/mvp4.md §10, arquitectura Anexo A).

Cada valor es la única fuente para núcleo e interfaz.
"""

CHUNK_SUBIDA = 1 * 1024**2  # lectura de archivo para hash y subida
BLOQUE_ENVIO = 64 * 1024  # tamaño de cada bloque enviado al socket
PARO_SIN_PROGRESO_S = 120.0  # sin avance durante este tiempo se da por cortada
MAX_LONG_URL = 2048
MAX_LONG_NOMBRE_VOLUMEN = 100  # nombre de archivo en el storage
RESERVA_STORAGE_MIB = 100  # margen libre exigido en el storage destino
RESERVA_RAIZ_MIB = 512  # margen libre exigido en la raíz del nodo (aviso)
ESPERA_BASE_S = 600.0  # M1 P-05
ESPERA_POR_GIB_S = 30.0
MAX_CATALOGO = 500  # volúmenes máximos mostrados por storage
URL_VIRTIO_WIN = ""  # se fija en LAB-M4-07 (DT-O10)
SHA256_VIRTIO_WIN = ""  # se fija en LAB-M4-07 (DT-O10)

ORDEN_ARRANQUE: tuple[str, ...] = ("disco", "cd", "red")  # DT-O1
RANURA_ISO = "ide2"
RANURA_DRIVERS = "ide0"
RANURAS_IDE_CON_ISO: tuple[str, ...] = ("ide1", "ide3")  # alternativas si ide2/ide0 están ocupadas
TAM_TPM_MIB = 4
VERSION_TPM = "v2.0"
PREFIJO_VIRTIO_WIN = "virtio-win"
