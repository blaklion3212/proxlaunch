"""Importación de CSV desde la interfaz con las columnas de la fase A: alias traducidos
(``alias_extra``) y notas largas (RF-A1.4, RF-A2.5, P-13, P-22; DT-A11).

Derivadas de docs/requisitos/fase-a.md: CA-A1.4.2-4, P-13 (la celda ``notas`` admite 8192),
P-22 (alias en inglés) y la regla de que el resto de celdas sigue limitado a 256 caracteres.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.dialogos.importar_csv import leer_e_interpretar
from proxlaunch.nucleo.archivos.constantes import MAX_LONG_CELDA, MAX_LONG_NOTAS
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila, OpcionesCsv
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

from .apoyo import inventario_cluster
from .apoyo_mvp3 import escribir_csv

CANONICAS_NUEVAS = (
    "encender",
    "arranque_auto",
    "notas",
    "etiquetas",
    "pool",
    "proteger",
    "mtu",
    "limite_red",
)

BASE = ["nombre", "nucleos", "memoria", "disco", "almacenamiento", "red"]
FILA = ["web-01", 2, "2 GiB", "20 GiB", "local-lvm", "vmbr0"]


def interpretar(ruta: Path, alias: dict[str, str] | None):
    perfiles = perfiles_fabrica(textos.textos_perfiles_fabrica())
    base = next(p for p in perfiles if p.id == ID_PREDETERMINADO)
    return leer_e_interpretar(
        ruta, OpcionesCsv(), base, perfiles, inventario_cluster(), None, alias
    )


def csv_con(tmp_path: Path, columnas: list[str], valores: list) -> Path:
    return escribir_csv(tmp_path / "f.csv", [BASE + columnas, FILA + valores])


class _TraductorColumnas(QTranslator):
    """Traduce los encabezados del contexto ``ColumnasCsv`` (simula otro idioma)."""

    def __init__(self, tabla: dict[str, str]) -> None:
        super().__init__()
        self._tabla = tabla

    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        if context == "ColumnasCsv":
            return self._tabla.get(source_text, source_text)
        return ""


@pytest.fixture
def idioma_ingles(qapp):
    t = _TraductorColumnas(
        {
            "encender": "poweron",
            "arranque_auto": "autostart",
            "notas": "remarks",
            "etiquetas": "labels",
            "pool": "resourcepool",
            "proteger": "lock_delete",
            "mtu": "mtusize",
            "limite_red": "netlimit",
        }
    )
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


# --- Los alias del idioma activo cubren las 8 columnas canónicas nuevas ---


@pytest.mark.parametrize("canonica", CANONICAS_NUEVAS)
def test_rf_a1_4_alias_columnas_csv_incluye_cada_columna_nueva(canonica):
    alias = textos.alias_columnas_csv()
    assert canonica in alias.values()
    assert alias[next(k for k, v in alias.items() if v == canonica)] == canonica


def test_rnf_m04_en_otro_idioma_los_alias_apuntan_a_las_canonicas_nuevas(idioma_ingles):
    alias = textos.alias_columnas_csv()
    for traducido, canonica in (
        ("poweron", "encender"),
        ("autostart", "arranque_auto"),
        ("remarks", "notas"),
        ("labels", "etiquetas"),
        ("resourcepool", "pool"),
        ("lock_delete", "proteger"),
        ("mtusize", "mtu"),
        ("netlimit", "limite_red"),
    ):
        assert alias[traducido] == canonica


# --- Notas largas con el encabezado traducido (alias_extra) ---


def test_p13_notas_de_mas_de_256_caracteres_con_encabezado_canonico(tmp_path):
    texto = "n" * 1000
    _, res = interpretar(csv_con(tmp_path, ["notas"], [texto]), textos.alias_columnas_csv())
    fila = res.filas[0]
    assert fila.estado != EstadoFila.CON_ERROR
    assert fila.opciones is not None and fila.opciones.notas == texto


def test_p13_notas_largas_con_el_encabezado_traducido_se_leen_con_el_limite_ampliado(
    tmp_path, idioma_ingles
):
    texto = "n" * 1000
    ruta = csv_con(tmp_path, ["remarks"], [texto])
    _, res = interpretar(ruta, textos.alias_columnas_csv())
    fila = res.filas[0]
    assert fila.estado != EstadoFila.CON_ERROR
    assert fila.opciones is not None and fila.opciones.notas == texto


def test_p13_sin_alias_extra_el_encabezado_traducido_no_amplia_el_limite(tmp_path, idioma_ingles):
    # Documenta por qué la ventana debe pasar ``alias_extra``: sin él «remarks» no es «notas».
    ruta = csv_con(tmp_path, ["remarks"], ["n" * 1000])
    with pytest.raises(ErrorProxLaunch) as exc:
        interpretar(ruta, None)
    assert str(MAX_LONG_CELDA) in str(exc.value.params.values())


def test_p13_notas_en_el_limite_exacto_de_8192_se_aceptan(tmp_path):
    _, res = interpretar(
        csv_con(tmp_path, ["notas"], ["x" * MAX_LONG_NOTAS]), textos.alias_columnas_csv()
    )
    assert res.filas[0].estado != EstadoFila.CON_ERROR


def test_p13_notas_de_8193_caracteres_se_rechazan_nombrando_el_limite(tmp_path):
    with pytest.raises(ErrorProxLaunch) as exc:
        interpretar(
            csv_con(tmp_path, ["notas"], ["x" * (MAX_LONG_NOTAS + 1)]),
            textos.alias_columnas_csv(),
        )
    assert str(MAX_LONG_NOTAS) in str(exc.value.params.values())


def test_dt_a11_otra_columna_de_mas_de_256_caracteres_sigue_rechazada(tmp_path):
    with pytest.raises(ErrorProxLaunch) as exc:
        interpretar(
            csv_con(tmp_path, ["etiquetas"], ["a" * (MAX_LONG_CELDA + 1)]),
            textos.alias_columnas_csv(),
        )
    assert str(MAX_LONG_CELDA) in str(exc.value.params.values())


def test_dt_a11_una_celda_de_256_en_otra_columna_se_acepta(tmp_path):
    _, res = interpretar(
        csv_con(tmp_path, ["etiquetas"], ["a" * MAX_LONG_CELDA]), textos.alias_columnas_csv()
    )
    assert res.filas  # se leyó; las etiquetas inválidas se marcan en la fila, no en la lectura


# --- Alias en inglés (P-22) y columnas con encabezado traducido ---


@pytest.mark.parametrize(
    ("encabezado", "valor", "campo", "esperado"),
    [
        ("start", "sí", "encender", True),
        ("onboot", "sí", "arranque_auto", True),
        ("notes", "hola", "notas", "hola"),
        ("tags", "web;prod", "etiquetas_usuario", ("web", "prod")),
        ("protection", "sí", "proteger", True),
    ],
)
def test_p22_los_alias_en_ingles_llegan_a_las_opciones_de_la_fila(
    tmp_path, encabezado, valor, campo, esperado
):
    _, res = interpretar(csv_con(tmp_path, [encabezado], [valor]), textos.alias_columnas_csv())
    fila = res.filas[0]
    assert fila.estado != EstadoFila.CON_ERROR, fila.problemas
    assert fila.opciones is not None
    assert getattr(fila.opciones, campo) == esperado


def test_ca_a1_4_4_un_csv_sin_las_columnas_nuevas_no_fija_ninguna_opcion(tmp_path):
    ruta = escribir_csv(tmp_path / "f.csv", [BASE, FILA])
    _, res = interpretar(ruta, textos.alias_columnas_csv())
    fila = res.filas[0]
    assert fila.opciones is None or all(
        getattr(fila.opciones, c) is None
        for c in ("encender", "arranque_auto", "notas", "etiquetas_usuario", "pool", "proteger")
    )


def test_ca_a1_4_2_columna_encender_con_valor_no_booleano_es_error_de_fila_con_columna(tmp_path):
    _, res = interpretar(csv_con(tmp_path, ["encender"], ["quizá"]), textos.alias_columnas_csv())
    fila = res.filas[0]
    assert fila.estado == EstadoFila.CON_ERROR
    assert any(p.columna == "encender" for p in fila.problemas)


def test_ca_a5_2_4_mtu_con_tarjeta_no_virtio_es_error_de_fila(tmp_path):
    ruta = escribir_csv(
        tmp_path / "f.csv", [[*BASE, "modelo_red", "mtu"], [*FILA, "e1000", "9000"]]
    )
    _, res = interpretar(ruta, textos.alias_columnas_csv())
    assert res.filas[0].estado == EstadoFila.CON_ERROR
