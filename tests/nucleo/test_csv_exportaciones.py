"""Exportaciones CSV: plantilla y filas con error (RF-C10, RF-C11, RF-C12; CA-C10.1..C10.6,
CA-C11.4, CA-C11.8, CA-C12.1..C12.3; INV-M2; §13 caso 13 de los requisitos).

Ambas pasan por el escritor único: UTF-8 con BOM, ``\\r\\n``, celdas de texto saneadas, escritura
atómica; la de errores conserva las columnas originales (sin credenciales) y es reimportable.
"""

import csv
import io
import os
import stat

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo as Aviso
from proxlaunch.nucleo.csv_importacion.errores_csv import (
    COLUMNAS_EXTRA,
    escribir_filas_con_error,
    filas_con_error,
)
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.csv_importacion.plantilla import (
    ENCABEZADO_PLANTILLA,
    escribir_plantilla,
    filas_plantilla,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_mvp3 import (
    CENT_PASSWORD,
    CENT_TOKEN,
    csv_bytes,
    importar_csv,
    perfil_base,
    sin_centinelas,
)

BOM = b"\xef\xbb\xbf"


def _releer(datos: bytes, sep: str = ";") -> list[list[str]]:
    return list(csv.reader(io.StringIO(datos.decode("utf-8-sig"), newline=""), delimiter=sep))


def _traducir(p) -> str:
    return f"Fila {p.fila}, columna «{p.columna}»: {p.regla}"


# --- Plantilla (RF-C10) ---------------------------------------------------------------------------


@pytest.mark.parametrize("sep", [";", ","])
def test_la_plantilla_tiene_el_encabezado_canonico_y_cinco_filas_de_ejemplo(tmp_path, sep):
    """CA-C10.1 ampliado por CA-O28.9: una fila de ejemplo por origen (5 filas); fase A
    (CA-A7.3.10): 8 columnas nuevas al final (23 columnas); fase B (CA-B6.3.8): 12 más (35);
    fase C (CA-C6.3.7): 5 más (40)."""
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta, separador=sep)
    filas = _releer(ruta.read_bytes(), sep)
    assert filas[0] == [
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
        "encender",
        "arranque_auto",
        "notas",
        "etiquetas",
        "pool",
        "proteger",
        "mtu",
        "limite_red",
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
        "reescribir_red",
        "cortafuegos",
        "grupo_seguridad",
        "politica_entrada",
        "politica_salida",
    ]
    assert [f[0] for f in filas[1:]] == [f"ejemplo-0{n}" for n in range(1, 6)]
    assert all(len(f) == 40 for f in filas)
    assert tuple(filas[0]) == ENCABEZADO_PLANTILLA


def test_la_plantilla_usa_punto_y_coma_por_defecto_bom_y_crlf(tmp_path):
    """CA-C10.2."""
    ruta = tmp_path / "plantilla.csv"
    escribir_plantilla(ruta)
    datos = ruta.read_bytes()
    assert datos.startswith(BOM) and datos.count(BOM) == 1
    assert b'"nombre";"perfil";"cpu"' in datos
    assert (
        datos.count(b"\r\n") == 6  # encabezado + 5 filas de ejemplo (CA-O28.9)
        and datos.replace(b"\r\n", b"").count(b"\n") == 0
        and b"\r" not in datos.replace(b"\r\n", b"")
    )


@pytest.mark.parametrize("sep", ["|", "\t", "", ";;", "x"])
def test_la_plantilla_solo_admite_los_dos_separadores_de_excel(tmp_path, sep):
    with pytest.raises(ValueError):
        escribir_plantilla(tmp_path / "p.csv", separador=sep)
    assert not (tmp_path / "p.csv").exists()


def test_los_ejemplos_son_validos_y_no_empiezan_por_un_disparador():
    for fila in filas_plantilla():
        for celda in fila:
            assert not (isinstance(celda, str) and celda[:1] in {"=", "+", "-", "@", "\t", "\r"})
    assert [f[0] for f in filas_plantilla()] == [f"ejemplo-0{n}" for n in range(1, 6)]


def test_la_plantilla_escribe_enteros_sin_comilla_ni_apostrofe(tmp_path):
    ruta = tmp_path / "p.csv"
    escribir_plantilla(ruta)
    assert b"'" not in ruta.read_bytes()


def _validar_plantilla_con_base(tmp_path, sep, base):
    ruta = tmp_path / "p.csv"
    escribir_plantilla(ruta, separador=sep)
    tabla = leer_tabla(ruta.read_bytes())
    assert tabla.deteccion.separador == sep and tabla.codificacion.value == "utf-8-sig"
    return interpretar(
        tabla, perfil_base=base, perfiles=perfiles_fabrica(), inv=None, nodo_referencia=None
    )


@pytest.mark.parametrize("sep", [";", ","])
def test_la_plantilla_pasa_su_propia_validacion_de_capa_1_con_cualquier_perfil_base(tmp_path, sep):
    """CA-C10.4 (y V-M11 como aviso, CA-C10.3) con los perfiles base de origen «vacío»."""
    bases = [b for b in perfiles_fabrica() if b.config.origen.value == "disco_vacio"]
    assert len(bases) >= 6  # los 6 perfiles de M3 no cambian (CA-O31.2)
    for base in bases:
        r = _validar_plantilla_con_base(tmp_path, sep, base)
        assert [f.estado for f in r.filas] == [EstadoFila.CON_AVISO] * 5, base.id
        for f in r.filas:
            assert [p.regla for p in f.problemas if p.severidad == Severidad.ERROR] == []
            assert [p.regla for p in f.problemas] == ["V-M11"]
        assert r.numeros_validos == (2, 3, 4, 5, 6)


@pytest.mark.parametrize("sep", [";"])
def test_la_plantilla_pasa_su_validacion_tambien_con_perfiles_base_de_origen_iso(tmp_path, sep):
    bases = [b for b in perfiles_fabrica() if b.config.origen.value != "disco_vacio"]
    assert bases  # RF-O31: windows-11, windows-server y linux-red-hat
    for base in bases:
        r = _validar_plantilla_con_base(tmp_path, sep, base)
        assert r.numeros_validos == (2, 3, 4, 5, 6), base.id


def test_la_plantilla_es_atomica_con_permisos_0600_y_reemplaza_la_anterior(tmp_path, monkeypatch):
    ruta = tmp_path / "plantilla.csv"
    ruta.write_bytes(b"ORIGINAL")

    def _replace(*a, **k):
        raise OSError(28, "disco lleno")

    monkeypatch.setattr(os, "replace", _replace)
    with pytest.raises(ErrorProxLaunch) as exc:
        escribir_plantilla(ruta)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    monkeypatch.undo()
    assert ruta.read_bytes() == b"ORIGINAL"
    escribir_plantilla(ruta)
    assert ruta.read_bytes().startswith(BOM)
    if os.name == "posix":
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["plantilla.csv"]


def test_los_encabezados_de_la_plantilla_son_estables_entre_idiomas(tmp_path):
    """CA-C10.6: la plantilla no recibe ningún texto traducido."""
    import inspect

    assert list(inspect.signature(escribir_plantilla).parameters) == ["ruta", "separador"]


# --- Filas con error (RF-C12) ---------------------------------------------------------------------


def _resultado_con_errores(extra_cabecera="", extra_celdas=""):
    lineas = [
        f"nombre;cpu;memoria;comentario;token{extra_cabecera}",
        f"ok-01;2;4;libre;{CENT_TOKEN}{extra_celdas}",
        f"mal nombre;0;abc;nota 1;{CENT_PASSWORD}{extra_celdas}",
        f"=cmd;2;4;@SUM(1);secreto{extra_celdas}",
        f"ok-04;3;1.000;ñandú;x{extra_celdas}",
    ]
    tabla = leer_tabla(csv_bytes(lineas))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    return tabla, resultado


def test_el_csv_de_errores_lleva_solo_las_filas_con_error_y_las_tres_columnas_nuevas():
    """CA-C12.1."""
    tabla, resultado = _resultado_con_errores()
    encabezado, filas = filas_con_error(tabla, resultado, _traducir)
    assert encabezado == [
        "nombre",
        "cpu",
        "memoria",
        "comentario",
        "fila_original",
        "columna",
        "problema",
    ]
    assert [f[4] for f in filas] == [3, 4, 5]  # fila_original, numeración de Excel
    assert filas[0][:4] == ["mal nombre", "0", "abc", "nota 1"]
    assert "cpu" in filas[0][5] and "memoria" in filas[0][5]  # columnas con error
    assert "Fila 3" in filas[0][6]  # texto traducido por la interfaz


def test_las_columnas_de_credenciales_no_se_exportan_ni_sus_valores():
    """CA-C12.1 / INV-M2."""
    tabla, resultado = _resultado_con_errores()
    encabezado, filas = filas_con_error(tabla, resultado, _traducir)
    assert "token" not in encabezado
    assert CENT_TOKEN not in str(filas) and CENT_PASSWORD not in str(filas)


def test_solo_se_exportan_errores_no_avisos():
    lineas = ["nombre", "ejemplo-01", "ok-02", "mal nombre"]
    tabla = leer_tabla(csv_bytes(lineas))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    _, filas = filas_con_error(tabla, resultado, _traducir)
    assert [f[1] for f in filas] == [4]


def test_sin_filas_con_error_el_csv_de_errores_solo_trae_encabezado():
    tabla = leer_tabla(csv_bytes(["nombre", "ok-01"]))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    encabezado, filas = filas_con_error(tabla, resultado, _traducir)
    assert encabezado == ["nombre", *COLUMNAS_EXTRA] and filas == []


def test_el_csv_de_errores_sanea_valores_originales_y_mensajes(tmp_path):
    """CA-C12.2: RF-C11 también para el texto traducido."""
    tabla, resultado = _resultado_con_errores()
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(
        ruta, tabla, resultado, lambda p: '=HYPERLINK("http://x")' + "\t", separador=";"
    )
    datos = ruta.read_bytes()
    assert datos.startswith(BOM) and b"\r\n" in datos
    filas = _releer(datos)
    celdas = [c for f in filas for c in f]
    assert "'=cmd" in celdas  # el nombre `=cmd` del usuario quedó neutralizado
    assert "'@SUM(1)" in celdas
    assert all(not c.startswith(("=", "@", "+", "-", "\t")) for c in celdas if c)
    assert all(
        f[-1].startswith("'=HYPERLINK") for f in filas[1:]
    )  # el mensaje también se neutraliza


def test_el_csv_de_errores_es_reimportable_y_las_tres_columnas_se_ignoran_como_desconocidas(
    tmp_path,
):
    """CA-C12.3: el ciclo corregir-y-reimportar funciona."""
    tabla, resultado = _resultado_con_errores()
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, resultado, _traducir, separador=";")
    tabla2 = leer_tabla(ruta.read_bytes())
    assert tabla2.encabezado[-3:] == ("fila_original", "columna", "problema")
    r2 = interpretar(
        tabla2,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    no_usadas = [a.params["columna"] for a in r2.avisos if a.codigo == Aviso.COLUMNA_NO_USADA]
    assert {"fila_original", "columna", "problema"} <= set(no_usadas)
    assert len(r2.filas) == 3
    # Los mismos errores de antes (los datos no cambiaron): el ciclo no inventa ni pierde problemas.
    assert [f.estado for f in r2.filas] == [EstadoFila.CON_ERROR] * 3
    # La apóstrofe antepuesta al exportar se quita al reimportar (CA-C11.5): vuelve el `=cmd` original.  # noqa: E501
    assert r2.filas[1].nombre == "=cmd"


def test_reexportar_un_csv_de_errores_no_duplica_las_columnas_extra(tmp_path):
    tabla, resultado = _resultado_con_errores()
    ruta = tmp_path / "e1.csv"
    escribir_filas_con_error(ruta, tabla, resultado, _traducir)
    tabla2 = leer_tabla(ruta.read_bytes())
    resultado2 = interpretar(
        tabla2,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    encabezado, _ = filas_con_error(tabla2, resultado2, _traducir)
    assert (
        encabezado.count("fila_original") == 1
        and encabezado.count("columna") == 1
        and encabezado.count("problema") == 1
    )
    assert encabezado[-3:] == ["fila_original", "columna", "problema"]


def test_varios_errores_de_una_fila_se_unen_en_una_celda_sin_repetir_columnas():
    tabla = leer_tabla(csv_bytes(["nombre;cpu;memoria", "mal nombre;0;abc"]))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    _, (fila,) = filas_con_error(tabla, resultado, _traducir)
    columnas = fila[-2].split(" | ")
    assert len(columnas) == len(set(columnas)) and {"nombre", "cpu", "memoria"} <= set(columnas)
    assert fila[-1].count(" | ") >= 2


def test_el_csv_de_errores_con_coma_como_separador_y_celdas_con_el_separador(tmp_path):
    tabla = leer_tabla(csv_bytes(["nombre,cpu", '"mal, nombre",0']))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    ruta = tmp_path / "e.csv"
    escribir_filas_con_error(ruta, tabla, resultado, _traducir, separador=",")
    filas = _releer(ruta.read_bytes(), ",")
    assert filas[1][0] == "mal, nombre" and filas[1][1] == "0"


def test_celdas_mas_cortas_que_el_encabezado_se_rellenan_en_el_csv_de_errores():
    tabla = leer_tabla(csv_bytes(["nombre;cpu;memoria", "mal nombre"]))
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    _, (fila,) = filas_con_error(tabla, resultado, _traducir)
    assert fila[:3] == ["mal nombre", "", ""]


def test_el_csv_de_errores_es_atomico(tmp_path, monkeypatch):
    tabla, resultado = _resultado_con_errores()
    ruta = tmp_path / "errores.csv"
    ruta.write_bytes(b"ORIGINAL")

    def _replace(*a, **k):
        raise OSError(28, "disco lleno")

    monkeypatch.setattr(os, "replace", _replace)
    with pytest.raises(ErrorProxLaunch):
        escribir_filas_con_error(ruta, tabla, resultado, _traducir)
    monkeypatch.undo()
    assert ruta.read_bytes() == b"ORIGINAL"


# --- Privacidad (CA-C11.8, INV-M2) ----------------------------------------------------------------


def test_ninguna_exportacion_csv_contiene_centinelas(tmp_path):
    tabla, resultado = _resultado_con_errores()
    escribir_filas_con_error(tmp_path / "e.csv", tabla, resultado, _traducir)
    escribir_plantilla(tmp_path / "p.csv")
    archivos = sorted(tmp_path.iterdir())
    assert len(archivos) == 2
    for archivo in archivos:
        assert sin_centinelas(archivo.read_bytes())
        assert sin_centinelas(archivo.read_bytes(), [CENT_TOKEN, CENT_PASSWORD, "secreto"])


def test_importar_csv_helper_devuelve_los_mismos_resultados_que_interpretar_directo():
    lineas = ["nombre;cpu", "ok-01;2", "mal nombre;0"]
    a = importar_csv(lineas)
    b = interpretar(
        leer_tabla(csv_bytes(lineas)),
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    assert a == b
