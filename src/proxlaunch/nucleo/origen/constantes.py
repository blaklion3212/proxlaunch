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
# URL versionada (la «stable» cambia de contenido con cada versión). ISO 0.1.302, 877 373 440 B,
# medida en el laboratorio (DT-O10). El nombre empieza por «virtio-win» y acaba en «.iso», como
# exige la detección del catálogo (PREFIJO_VIRTIO_WIN).
URL_VIRTIO_WIN = (
    "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/"
    "archive-virtio/virtio-win-0.1.302-1/virtio-win-0.1.302.iso"
)
SHA256_VIRTIO_WIN = "303f7ae40dad495d6ae474fdc571df58958a4dbc5c37a522d80f9a203867949d"

ORDEN_ARRANQUE: tuple[str, ...] = ("disco", "cd", "red")  # DT-O1
RANURA_ISO = "ide2"
RANURA_DRIVERS = "ide0"
RANURAS_IDE_CON_ISO: tuple[str, ...] = ("ide1", "ide3")  # alternativas si ide2/ide0 están ocupadas
TAM_TPM_MIB = 4
VERSION_TPM = "v2.0"
PREFIJO_VIRTIO_WIN = "virtio-win"
