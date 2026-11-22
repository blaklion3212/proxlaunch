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
    "origen",
    "fuente",
    "so",
    "virtio",
    "modo_clon",
    # Fase A (CA-A7.3.10): opciones de la MV; una celda vacía hereda las del formulario.
    "encender",
    "arranque_auto",
    "notas",
    "etiquetas",
    "pool",
    "proteger",
    "mtu",
    "limite_red",
)
SEPARADORES_PLANTILLA = (";", ",")  # «;» Excel en español (por defecto), «,» Excel en inglés


def filas_plantilla() -> list[list[str | int]]:
    """Filas de ejemplo ``ejemplo-01``… (memoria y disco en GiB): vacía y una por origen.

    ``ejemplo-03`` instala un ISO, ``ejemplo-04`` importa un disco (``disco`` = ampliar a) y
    ``ejemplo-05`` clona una plantilla (``cpu``, ``memoria`` y ``disco`` = ajustes). Las fuentes
    son nombres ficticios que el usuario sustituye; nunca URL ni rutas.

    Las columnas de la fase A van vacías (= las del formulario) salvo dos filas de muestra. El
    ejemplo de MTU es ``heredar`` y no un número: un perfil base con tarjeta no VirtIO lo
    rechazaría (V-A05) y la plantilla debe pasar su propia validación con cualquier perfil.
    """
    filas: list[list[str | int]] = [
        ["ejemplo-01", "fabrica.servidor-mediano", "", "8", 100, "local-lvm", "vmbr0", "", "", ""],
        ["ejemplo-02", "", 2, "4 GiB", 40, "", "vmbr1", 20, "pve2", 250],
        ["ejemplo-03", "", 2, "4", 32, "", "", "", "", ""],
        ["ejemplo-04", "", 2, "4", 40, "", "", "", "", ""],
        ["ejemplo-05", "", 4, "8", 80, "", "", "", "", ""],
    ]
    origenes: list[list[str | int]] = [
        # «vacio» explícito: sin él la fila heredaría el origen del perfil base (p. ej. ISO sin
        # fuente) y la plantilla no pasaría su propia validación.
        ["vacio", "", "", "", ""],
        ["vacio", "", "", "", ""],
        ["iso", "ejemplo-instalador.iso", "linux", "", ""],
        ["importar", "ejemplo-disco.qcow2", "", "", ""],
        ["clonar", "ejemplo-plantilla", "", "", "auto"],
    ]
    opciones: list[list[str | int]] = [
        ["", "si", "Servidor de ejemplo", "web,prod", "", "", "", ""],
        ["no", "", "", "", "ninguno", "no", "heredar", 50],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
    ]
    return [fila + extra + ops for fila, extra, ops in zip(filas, origenes, opciones, strict=True)]


def escribir_plantilla(ruta: Path, *, separador: str = ";") -> None:
    """Escribe la plantilla (UTF-8 con BOM, CRLF, atómica y saneada por el escritor único)."""
    if separador not in SEPARADORES_PLANTILLA:
        raise ValueError("separador no admitido para la plantilla")
    escribir_csv(ruta, ENCABEZADO_PLANTILLA, filas_plantilla(), separador=separador)
