"""Esquema estricto y lista blanca (RF-X02 CA-X02.4/X02.5, RF-X04 CA-X04.1/X04.2, CA-X01.6;
§13 casos 7 y 9 de los requisitos).

Tipos REALES (un booleano no es entero, un decimal no es entero, una cadena no es número),
rangos, longitudes, enumeraciones exactas y claves: las de credencial se descartan sin leer el
valor y las desconocidas se descartan y se cuentan (nunca sus valores).
"""

from enum import StrEnum

import pytest

from proxlaunch.nucleo.archivos.esquema import (
    AvisoArchivo,
    CodigoAvisoArchivo,
    ErrorArchivo,
    LectorEsquema,
    MotivoCampo,
    combinar_avisos,
    es_clave_credencial,
)
from proxlaunch.nucleo.errores import CodigoError

from .apoyo_lote import volcar


class Color(StrEnum):
    ROJO = "rojo"
    VERDE = "verde"


# --- es_clave_credencial (CA-X04.2) -------------------------------------------------------------


@pytest.mark.parametrize(
    "clave",
    [
        "token", "Token", "api_token", "API-TOKEN", "password", "Password", "PASSWORD1", "pass_password",  # noqa: E501
        "contrasena", "contraseña", "Contraseña", "secreto", "Secreto", "secret", "client_secret",
        "ticket", "Ticket_PVE", "csrf", "CSRFPreventionToken", "apikey", "api_key", "API Key",
        "api-key", "credencial", "Credenciales", "mi token", "x.token.y",
    ],
)  # fmt: skip
def test_claves_que_parecen_credencial(clave):
    assert es_clave_credencial(clave) is True


@pytest.mark.parametrize(
    "clave",
    [
        "nombre",
        "cpu",
        "memoria",
        "disco",
        "almacenamiento",
        "vmid",
        "nodo",
        "red",
        "firmware",
        "",
        "x",
    ],
)
def test_claves_normales_no_son_credencial(clave):
    assert es_clave_credencial(clave) is False


def test_es_clave_credencial_con_no_cadena_es_falso():
    assert es_clave_credencial(None) is False  # type: ignore[arg-type]
    assert es_clave_credencial(5) is False  # type: ignore[arg-type]


# --- objeto: lista blanca, credenciales y desconocidas ------------------------------------------


class _DiccionarioEspia(dict):
    """Registra qué claves se leen (``__getitem__``/``get``/``items``/``values``)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.leidas: list[str] = []

    def __getitem__(self, clave):
        self.leidas.append(clave)
        return super().__getitem__(clave)

    def get(self, clave, defecto=None):
        self.leidas.append(clave)
        return super().get(clave, defecto)

    def items(self):
        self.leidas.append("*items*")
        return super().items()

    def values(self):
        self.leidas.append("*values*")
        return super().values()


def test_objeto_devuelve_solo_las_claves_de_la_lista_blanca():
    lector = LectorEsquema()
    limpio = lector.objeto({"a": 1, "b": 2, "z": 3}, "", frozenset({"a", "b"}))
    assert limpio == {"a": 1, "b": 2}
    assert not lector.errores


def test_las_claves_de_credencial_se_descartan_sin_leer_su_valor_y_se_cuentan():
    lector = LectorEsquema()
    entrada = _DiccionarioEspia(
        {"a": 1, "token": "CENTINELA-SECRETO-1", "Password": "CENTINELA-SECRETO-2", "ticket": 5}
    )
    limpio = lector.objeto(entrada, "", frozenset({"a"}))
    assert limpio == {"a": 1}
    assert set(entrada.leidas) == {"a"}  # el valor de las credenciales no se tocó
    assert lector.avisos() == (AvisoArchivo(CodigoAvisoArchivo.CREDENCIAL_IGNORADA, {"n": "3"}),)


def test_una_clave_de_credencial_gana_aunque_este_en_la_lista_blanca():
    lector = LectorEsquema()
    limpio = lector.objeto({"password": "x", "a": 1}, "", frozenset({"a", "password"}))
    assert limpio == {"a": 1}


def test_las_claves_desconocidas_se_descartan_y_se_cuentan_sin_sus_valores():
    lector = LectorEsquema()
    lector.objeto({"a": 1, "zeta": "VALOR-SECRETO", "otra": 2}, "", frozenset({"a"}))
    (aviso,) = lector.avisos()
    assert aviso.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS
    assert aviso.params == {"n": "2"}
    assert "VALOR-SECRETO" not in volcar(aviso)


def test_sin_desconocidas_ni_credenciales_no_hay_avisos():
    lector = LectorEsquema()
    lector.objeto({"a": 1}, "", frozenset({"a"}))
    assert lector.avisos() == ()


@pytest.mark.parametrize("no_objeto", [[], "texto", 5, None, True, 1.5])
def test_objeto_rechaza_lo_que_no_es_un_objeto(no_objeto):
    lector = LectorEsquema()
    assert lector.objeto(no_objeto, "config", frozenset({"a"})) is None
    assert [(e.ruta, e.motivo) for e in lector.errores] == [("config", MotivoCampo.TIPO)]


def test_combinar_avisos_suma_los_contadores_del_mismo_codigo():
    lector1, lector2 = LectorEsquema(), LectorEsquema()
    lector1.objeto({"x": 1, "y": 2, "token": 1}, "", frozenset())
    lector2.objeto({"z": 1, "password": 1, "secret": 1}, "", frozenset())
    avisos = combinar_avisos([*lector1.avisos(), *lector2.avisos()])
    por_codigo = {a.codigo: a.params["n"] for a in avisos}
    assert por_codigo == {
        CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS: "3",
        CodigoAvisoArchivo.CREDENCIAL_IGNORADA: "3",
    }


# --- entero: tipo real, rango, nulo, requerido, defecto -----------------------------------------


@pytest.mark.parametrize("valor", [True, False, 2.0, 2.5, "2", "10", [2], {"a": 1}, None])
def test_entero_exige_un_entero_real(valor):
    """CA-X02.4: ni booleanos, ni decimales (aunque sean ``2.0``), ni cadenas, ni ``null``."""
    lector = LectorEsquema()
    assert lector.entero({"n": valor}, "n", "x") is None
    (error,) = lector.errores
    assert (error.ruta, error.motivo) == ("x.n", MotivoCampo.TIPO)


def test_entero_acepta_enteros_y_comprueba_el_rango():
    lector = LectorEsquema()
    assert lector.entero({"n": 5}, "n", "", minimo=1, maximo=10) == 5
    assert lector.entero({"n": 1}, "n", "", minimo=1, maximo=10) == 1
    assert lector.entero({"n": 10}, "n", "", minimo=1, maximo=10) == 10
    assert not lector.errores
    assert lector.entero({"n": 0}, "n", "", minimo=1, maximo=10) is None
    assert lector.entero({"n": 11}, "n", "", minimo=1, maximo=10) is None
    assert [e.motivo for e in lector.errores] == [MotivoCampo.RANGO, MotivoCampo.RANGO]


def test_entero_nulo_solo_si_se_permite():
    lector = LectorEsquema()
    assert lector.entero({"n": None}, "n", "", nulo=True) is None
    assert not lector.errores


def test_entero_requerido_ausente_es_error_y_con_defecto_no():
    lector = LectorEsquema()
    assert lector.entero({}, "n", "disco") is None
    assert lector.errores[0].ruta == "disco.n"
    assert lector.errores[0].motivo == MotivoCampo.REQUERIDO
    lector2 = LectorEsquema()
    assert lector2.entero({}, "n", "", defecto=7) == 7
    assert lector2.entero({}, "n", "", requerido=False) is None
    assert not lector2.errores


# --- booleano / texto / enumerado / lista -------------------------------------------------------


@pytest.mark.parametrize("valor", [1, 0, "true", "si", None, 1.0])
def test_booleano_exige_un_booleano_real(valor):
    lector = LectorEsquema()
    assert lector.booleano({"b": valor}, "b", "") is None
    assert lector.errores[0].motivo == MotivoCampo.TIPO


def test_booleano_acepta_true_y_false_y_usa_el_defecto():
    lector = LectorEsquema()
    assert lector.booleano({"b": True}, "b", "") is True
    assert lector.booleano({"b": False}, "b", "") is False
    assert lector.booleano({}, "b", "", requerido=False, defecto=True) is True
    assert not lector.errores


@pytest.mark.parametrize("valor", [5, 1.5, True, None, ["a"], {"a": "b"}])
def test_texto_exige_una_cadena(valor):
    lector = LectorEsquema()
    assert lector.texto({"t": valor}, "t", "") is None
    assert lector.errores[0].motivo == MotivoCampo.TIPO


def test_texto_comprueba_longitud_caracteres_y_normaliza():
    lector = LectorEsquema()
    assert lector.texto({"t": "a" * 256}, "t", "") == "a" * 256
    assert lector.texto({"t": "a" * 257}, "t", "") is None
    assert lector.texto({"t": "x\x00y"}, "t", "") is None
    assert lector.texto({"t": "x‮y"}, "t", "") is None
    assert [e.motivo for e in lector.errores] == [
        MotivoCampo.LONGITUD,
        MotivoCampo.TEXTO_NO_VALIDO,
        MotivoCampo.TEXTO_NO_VALIDO,
    ]
    assert LectorEsquema().texto({"t": "café"}, "t", "") == "café"


def test_texto_respeta_minimo_maximo_y_multilinea():
    lector = LectorEsquema()
    assert lector.texto({"t": ""}, "t", "", minimo=1) is None
    assert lector.errores[0].motivo == MotivoCampo.LONGITUD
    assert lector.texto({"t": "a\nb"}, "t", "") is None
    assert lector.texto({"t": "a\nb"}, "t", "", multilinea=True) == "a\nb"
    assert lector.texto({"t": "abcd"}, "t", "", maximo=3) is None


def test_texto_sin_token_rechaza_un_api_token():
    lector = LectorEsquema()
    assert lector.texto({"t": "ana@pve!x=abc"}, "t", "", sin_token=True) is None
    assert lector.errores[0].motivo == MotivoCampo.TOKEN
    assert LectorEsquema().texto({"t": "ana@pve!x=abc"}, "t", "") == "ana@pve!x=abc"


def test_nombre_aplica_v_m01_v_m04_y_v_m05_con_su_motivo():
    lector = LectorEsquema()
    assert lector.nombre({"n": "  Hola  "}, "n", "") == "Hola"
    assert lector.nombre({"n": "a" * 61}, "n", "") is None
    assert lector.nombre({"n": "a\x00"}, "n", "") is None
    assert lector.nombre({"n": "ana@pve!x=abc"}, "n", "") is None
    assert [e.motivo for e in lector.errores] == [
        MotivoCampo.LONGITUD,
        MotivoCampo.TEXTO_NO_VALIDO,
        MotivoCampo.TOKEN,
    ]
    assert [e.params["regla"] for e in lector.errores] == ["V-M01", "V-M04", "V-M05"]


def test_enumerado_exige_el_valor_exacto():
    lector = LectorEsquema()
    assert lector.enumerado({"c": "rojo"}, "c", "", Color) is Color.ROJO
    assert not lector.errores
    for valor in ("ROJO", "Rojo", " rojo", "azul", 1, None):
        assert lector.enumerado({"c": valor}, "c", "", Color) is None
    assert len(lector.errores) == 6
    assert lector.errores[0].motivo == MotivoCampo.ENUM
    assert "rojo" in lector.errores[0].params["validos"]


def test_enumerado_usa_el_defecto_si_falta():
    lector = LectorEsquema()
    assert lector.enumerado({}, "c", "", Color, requerido=False, defecto=Color.VERDE) is Color.VERDE
    assert not lector.errores


def test_lista_comprueba_tipo_y_maximo():
    lector = LectorEsquema()
    assert lector.lista({"l": [1, 2]}, "l", "", maximo=2) == [1, 2]
    assert lector.lista({"l": [1, 2, 3]}, "l", "", maximo=2) is None
    assert lector.lista({"l": "no"}, "l", "", maximo=2) is None
    assert lector.lista({}, "l", "", maximo=2) is None
    assert [e.motivo for e in lector.errores] == [
        MotivoCampo.DEMASIADOS,
        MotivoCampo.TIPO,
        MotivoCampo.REQUERIDO,
    ]
    assert lector.errores[0].params["n"] == "3"


# --- Acumulación de errores y E-M04 -------------------------------------------------------------


def test_fallar_si_errores_no_hace_nada_sin_errores():
    LectorEsquema().fallar_si_errores()


def test_fallar_si_errores_lanza_e_m04_con_la_lista_completa_y_la_primera_ruta():
    lector = LectorEsquema()
    lector.entero({"n": "x"}, "n", "discos[1]")
    lector.booleano({"b": 3}, "b", "config")
    with pytest.raises(ErrorArchivo) as exc:
        lector.fallar_si_errores()
    e = exc.value
    assert e.codigo == CodigoError.ARCHIVO_DANADO
    assert e.params["campo"] == "discos[1].n"
    assert e.params["n"] == "2"
    assert [x.ruta for x in e.errores] == ["discos[1].n", "config.b"]


def test_el_numero_de_errores_acumulados_esta_acotado():
    lector = LectorEsquema()
    for i in range(5000):
        lector.error(f"c{i}", MotivoCampo.TIPO)
    assert len(lector.errores) <= 1000


def test_los_errores_de_esquema_no_incluyen_el_valor_enviado():
    lector = LectorEsquema()
    lector.entero({"n": "CENTINELA-SECRETO-valor"}, "n", "")
    lector.texto({"t": 12345}, "t", "")
    assert "CENTINELA-SECRETO" not in volcar(lector.errores)
