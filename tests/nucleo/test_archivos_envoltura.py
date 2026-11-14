"""Envoltura, versionado y migraciones (RF-X01: CA-X01.1..X01.8; CA-G06.2/G06.3/G06.6).

``abrir_envoltura(dato, formato)`` verifica la raíz; ``crear_envoltura`` y ``a_bytes_json``
producen JSON estable (UTF-8 sin BOM, ``ensure_ascii=False``, sangría y claves ordenadas, CA-X03.6).
"""

import json

import pytest

from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO
from proxlaunch.nucleo.archivos.envoltura import (
    FORMATO_LOTE,
    FORMATO_PERFILES,
    MIGRACIONES,
    a_bytes_json,
    abrir_envoltura,
    crear_envoltura,
)
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

from .apoyo_lote import volcar


def _raiz(**cambios):
    base = {"formato": FORMATO_PERFILES, "version_formato": 1, "app_version": "9.9", "perfiles": []}
    base.update(cambios)
    return base


def _error(dato, formato=FORMATO_PERFILES, **kw) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        abrir_envoltura(dato, formato, **kw)
    return exc.value


def test_la_version_actual_del_formato_es_1():
    assert VERSION_FORMATO == 1


def test_una_envoltura_valida_devuelve_el_contenido_sin_las_claves_de_la_envoltura():
    e = abrir_envoltura(_raiz(extra=5), FORMATO_PERFILES)
    assert e.formato == FORMATO_PERFILES
    assert e.version_original == 1
    assert e.contenido == {"perfiles": [], "extra": 5}
    assert e.avisos == ()


# --- CA-X01.1 / CA-X01.5: formato ajeno y versión inválida (E-M02) --------------------------------


@pytest.mark.parametrize("dato", [[], "texto", 5, None, True, [{"formato": FORMATO_PERFILES}]])
def test_una_raiz_que_no_es_objeto_da_e_m02(dato):
    e = _error(dato)
    assert e.codigo == CodigoError.ARCHIVO_FORMATO_AJENO
    assert e.params == {"esperado": FORMATO_PERFILES}


@pytest.mark.parametrize(
    "formato", [None, "", "otra.cosa", "PROXLAUNCH.PERFILES", " proxlaunch.perfiles", 5, True, []]
)
def test_formato_ausente_o_distinto_da_e_m02_sin_revelar_texto_ajeno(formato):
    e = _error(_raiz(formato=formato))
    assert e.codigo == CodigoError.ARCHIVO_FORMATO_AJENO
    assert "encontrado" not in e.params  # solo se revela otro formato CONOCIDO de ProxLaunch


def test_formato_ausente_da_e_m02():
    dato = _raiz()
    del dato["formato"]
    assert _error(dato).codigo == CodigoError.ARCHIVO_FORMATO_AJENO


def test_un_lote_abierto_como_perfiles_da_e_m02_con_la_pista_encontrado():
    """CA-G06.6 / CA-X01.1: «Parece un archivo de lote», solo con formatos conocidos."""
    e = _error(_raiz(formato=FORMATO_LOTE), FORMATO_PERFILES)
    assert e.codigo == CodigoError.ARCHIVO_FORMATO_AJENO
    assert e.params == {"esperado": FORMATO_PERFILES, "encontrado": FORMATO_LOTE}
    e = _error(_raiz(), FORMATO_LOTE)
    assert e.params == {"esperado": FORMATO_LOTE, "encontrado": FORMATO_PERFILES}


@pytest.mark.parametrize("version", [0, -1, -100, True, False, 1.0, 1.5, "1", None, [1], {"v": 1}])
def test_version_ausente_no_entera_booleana_negativa_o_cero_da_e_m02(version):
    e = _error(_raiz(version_formato=version))
    assert e.codigo == CodigoError.ARCHIVO_FORMATO_AJENO


def test_version_ausente_da_e_m02():
    dato = _raiz()
    del dato["version_formato"]
    assert _error(dato).codigo == CodigoError.ARCHIVO_FORMATO_AJENO


# --- CA-X01.4: versión futura (E-M03) -------------------------------------------------------------


@pytest.mark.parametrize("version", [2, 3, 99, 10**9])
def test_version_mayor_da_e_m03_sin_lectura_parcial(version):
    e = _error(_raiz(version_formato=version))
    assert e.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert e.params == {"version_archivo": str(version), "version_soportada": "1"}


# --- CA-X01.3: migraciones -----------------------------------------------------------------------


def test_sin_migraciones_registradas_la_cadena_esta_vacia_y_v1_se_lee():
    """CA-X01.3: «la prueba comprueba que existe la cadena vacía y que el v1 se lee»."""
    assert MIGRACIONES == {FORMATO_PERFILES: {}, FORMATO_LOTE: {}}
    assert abrir_envoltura(_raiz(), FORMATO_PERFILES).avisos == ()


def test_una_cadena_de_migraciones_lleva_v1_a_v3_y_avisa():
    pasos = []

    def v1_a_v2(c):
        pasos.append(1)
        return {**c, "nuevo_v2": True}

    def v2_a_v3(c):
        pasos.append(2)
        return {**c, "nuevo_v3": True}

    e = abrir_envoltura(
        _raiz(version_formato=1),
        FORMATO_PERFILES,
        version_soportada=3,
        migraciones={1: v1_a_v2, 2: v2_a_v3},
    )
    assert pasos == [1, 2]  # en orden, una por versión
    assert e.contenido["nuevo_v2"] is True and e.contenido["nuevo_v3"] is True
    assert e.version_original == 1
    (aviso,) = e.avisos
    assert aviso.codigo == CodigoAvisoArchivo.MIGRADO
    assert aviso.params == {"desde": "1", "hasta": "3"}


def test_migrar_desde_una_version_intermedia_solo_aplica_los_pasos_que_faltan():
    pasos = []
    e = abrir_envoltura(
        _raiz(version_formato=2),
        FORMATO_PERFILES,
        version_soportada=3,
        migraciones={1: lambda c: pasos.append(1) or c, 2: lambda c: pasos.append(2) or c},
    )
    assert pasos == [2]
    assert e.avisos[0].params == {"desde": "2", "hasta": "3"}


def test_las_migraciones_no_reciben_las_claves_de_la_envoltura_ni_mutan_la_entrada():
    vistas = []
    dato = _raiz(version_formato=1)
    copia = json.loads(json.dumps(dato))
    abrir_envoltura(
        dato,
        FORMATO_PERFILES,
        version_soportada=2,
        migraciones={1: lambda c: vistas.append(set(c)) or dict(c)},
    )
    assert vistas == [{"perfiles"}]
    assert dato == copia


def test_una_cadena_de_migraciones_rota_da_e_m04_y_no_una_excepcion_cruda():
    e = _error(_raiz(version_formato=1), version_soportada=3, migraciones={2: lambda c: c})
    assert e.codigo == CodigoError.ARCHIVO_DANADO


def test_una_migracion_no_aplica_a_una_version_igual_a_la_soportada():
    llamadas = []
    e = abrir_envoltura(
        _raiz(), FORMATO_PERFILES, migraciones={1: lambda c: llamadas.append(1) or c}
    )
    assert llamadas == [] and e.avisos == ()


# --- crear_envoltura / a_bytes_json (CA-X01.8, CA-X03.6) -----------------------------------------


def test_crear_envoltura_pone_formato_version_y_app_version():
    raiz = crear_envoltura(FORMATO_LOTE, {"nombre": "x"}, app_version="0.3.0")
    assert raiz == {
        "formato": FORMATO_LOTE,
        "version_formato": 1,
        "app_version": "0.3.0",
        "nombre": "x",
    }


@pytest.mark.parametrize("clave", ["formato", "version_formato", "app_version"])
def test_crear_envoltura_rechaza_contenido_que_pise_la_envoltura(clave):
    with pytest.raises(ValueError):
        crear_envoltura(FORMATO_LOTE, {clave: "x"}, app_version="1")


def test_a_bytes_json_es_utf8_sin_bom_con_sangria_claves_ordenadas_y_sin_escapar_acentos():
    datos = a_bytes_json({"b": "ñandú", "a": {"z": 1, "y": 2}})
    assert not datos.startswith(b"\xef\xbb\xbf")
    texto = datos.decode("utf-8")
    assert "ñandú" in texto and "\\u" not in texto
    assert texto.index('"a"') < texto.index('"b"')
    assert texto.index('"y"') < texto.index('"z"')
    assert "\n  " in texto  # sangría
    assert json.loads(texto) == {"b": "ñandú", "a": {"z": 1, "y": 2}}


def test_a_bytes_json_es_determinista():
    obj = {"b": [1, 2, {"d": 1, "c": 2}], "a": "x"}
    assert a_bytes_json(obj) == a_bytes_json(dict(reversed(list(obj.items()))))


def test_a_bytes_json_rechaza_nan_e_infinito():
    with pytest.raises(ValueError):
        a_bytes_json({"x": float("nan")})
    with pytest.raises(ValueError):
        a_bytes_json({"x": float("inf")})


def test_el_error_de_envoltura_no_incluye_el_contenido_del_archivo():
    e = _error(_raiz(formato="CENTINELA-SECRETO-formato"))
    assert "CENTINELA-SECRETO" not in volcar(e)
