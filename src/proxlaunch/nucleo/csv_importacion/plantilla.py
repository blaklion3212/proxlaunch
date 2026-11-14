"""Plantilla CSV descargable (RF-C10).

Encabezados canónicos (estables entre idiomas) y dos filas de ejemplo válidas que no empiezan
por ``= + - @``. La columna ``perfil`` usa el id del perfil de fábrica, que no depende del
idioma, para que la plantilla pase su propia validación con cualquier perfil base.
"""

from pathlib import Path

from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv

ENCABEZADO_PLANTILLA: tuple[str, ...] = (
    "nombre",
    "perfil",
    "cpu",
    "memoria",
    "disco",
    "almacenamiento",
    "red",
    "vlan",
    "nodo",
    "vmid",
)
SEPARADORES_PLANTILLA = (";", ",")  # «;» Excel en español (por defecto), «,» Excel en inglés


def filas_plantilla() -> list[list[str | int]]:
    """Filas de ejemplo ``ejemplo-01`` y ``ejemplo-02`` (memoria y disco en GiB)."""
    return [
        ["ejemplo-01", "fabrica.servidor-mediano", "", "8", 100, "local-lvm", "vmbr0", "", "", ""],
        ["ejemplo-02", "", 2, "4 GiB", 40, "", "vmbr1", 20, "pve2", 250],
    ]


def escribir_plantilla(ruta: Path, *, separador: str = ";") -> None:
    """Escribe la plantilla (UTF-8 con BOM, CRLF, atómica y saneada por el escritor único)."""
    if separador not in SEPARADORES_PLANTILLA:
        raise ValueError("separador no admitido para la plantilla")
    escribir_csv(ruta, ENCABEZADO_PLANTILLA, filas_plantilla(), separador=separador)
