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
    # Fase B (CA-B6.3.8): cloud-init y espera de IP, solo útiles al clonar una plantilla. NO
    # incluye ``ci_contrasena``: una contraseña no se escribe en ningún archivo de la app.
    "ci_usuario",
    "ci_claves",
    "ci_ip",
    "ci_puerta",
    "ci_dns",
    "ci_dominio",
    "ci_actualizar",
    "ci_snippet_usuario",
    "ci_snippet_vendor",
    "ci_snippet_red",
    "ci_snippet_meta",
    "esperar_ip",
)
SEPARADORES_PLANTILLA = (";", ",")  # «;» Excel en español (por defecto), «,» Excel en inglés


def filas_plantilla() -> list[list[str | int]]:
    """Filas de ejemplo ``ejemplo-01``… (memoria y disco en GiB): vacía y una por origen.

    ``ejemplo-03`` instala un ISO, ``ejemplo-04`` importa un disco (``disco`` = ampliar a) y
    ``ejemplo-05`` clona una plantilla (``cpu``, ``memoria`` y ``disco`` = ajustes) y lleva un
    ejemplo de cloud-init (usuario y DHCP). Las fuentes son nombres ficticios que el usuario
    sustituye; nunca URL ni rutas.

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
    # Fase B: solo la fila que clona una plantilla lleva ejemplo (cloud-init no existe en los
    # demás orígenes, V-B39). Los snippets, las claves y la espera de IP quedan vacíos (= los del
    # formulario): dependen del servidor y de «Encender».
    vacias: list[str | int] = [""] * 12
    cloudinit: list[list[str | int]] = [list(vacias) for _ in filas]
    cloudinit[4] = ["ubuntu", "", "dhcp", "", "", "", "", "", "", "", "", ""]
    return [
        fila + extra + ops + ci
        for fila, extra, ops, ci in zip(filas, origenes, opciones, cloudinit, strict=True)
    ]


def escribir_plantilla(ruta: Path, *, separador: str = ";") -> None:
    """Escribe la plantilla (UTF-8 con BOM, CRLF, atómica y saneada por el escritor único)."""
    if separador not in SEPARADORES_PLANTILLA:
        raise ValueError("separador no admitido para la plantilla")
    escribir_csv(ruta, ENCABEZADO_PLANTILLA, filas_plantilla(), separador=separador)
