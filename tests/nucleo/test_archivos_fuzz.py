"""Fuzz de lectura de archivos de terceros (CA-X02.11, RNF-M01; arquitectura §13 «Fuzz»).

10 000 entradas aleatorias o mutadas (semilla fija, sin dependencias nuevas) por cada lector
(``leer_perfiles``, ``leer_lote`` y ``leer_tabla`` + ``interpretar``) a partir de archivos
válidos: el resultado es siempre una salida normal o un ``ErrorProxLaunch``; nunca una excepción
sin controlar, nunca una lectura mayor que el límite y nunca una petición de red (la suite corre
con ``--disable-socket``).
"""

import copy
import json
import os
import random
import socket

import pytest

from proxlaunch.nucleo.archivos.lector import leer_archivo_limitado
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_tabla
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lotes_guardados.formato import leer_lote
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import leer_perfiles

from .apoyo_lote import inventario, nodo, storage
from .apoyo_mvp3 import DATOS_MVP3, perfil_base

ENTRADAS = 10_000
CODIGOS_PERMITIDOS = {
    CodigoError.ARCHIVO_NO_PERMITIDO,
    CodigoError.ARCHIVO_FORMATO_AJENO,
    CodigoError.ARCHIVO_VERSION_FUTURA,
    CodigoError.ARCHIVO_DANADO,
    CodigoError.ARCHIVO_DEMASIADAS_FILAS,
    CodigoError.CSV_CODIFICACION,
    CodigoError.CSV_VACIO,
    CodigoError.CSV_COLUMNAS,
}

# Trozos de texto "interesantes" para insertar en los archivos.
TROZOS = [
    b"NaN", b"Infinity", b"-Infinity", b"1e999", b"-1e999", b"0x10", b'""', b"\\u0000", b"\\ud800",
    b"\x00", b"\xff", b"\xfe\xff", b"\xef\xbb\xbf", b"{", b"}", b"[", b"]", b'"', b",", b":", b";", b"\t",  # noqa: E501
    b"\r", b"\n", b"\r\n", b"=1+1", b"@SUM(1)", b"-1", b"+1", b"9" * 40, b"9" * 5000, b"[" * 300,
    b'{"a":' * 12, b"null", b"true", b"false", b'"token"', b'"password"', b"\xe2\x80\xae", b"\xc3\xb1",  # noqa: E501
    b"\xed\xa0\x80", b'"nombre"', b'"cores"', b'"discos"', b'"config"', b'"filas"', b'"formato"',
    b"1.000", b"1,5", b"0,3", b"sep=;", b"ejemplo-01", b"A" * 300, b" " * 50, b"\\", b"/", b"..",
]  # fmt: skip


def _mutar(base: bytes, rng: random.Random, otros: list[bytes]) -> bytes:
    datos = bytearray(base)
    for _ in range(rng.randint(1, 5)):
        op = rng.randrange(10)
        n = len(datos)
        if op == 0 and n:  # voltear un byte
            datos[rng.randrange(n)] = rng.randrange(256)
        elif op == 1 and n:  # borrar un tramo
            i = rng.randrange(n)
            del datos[i : i + rng.randint(1, 40)]
        elif op == 2 and n:  # duplicar un tramo
            i = rng.randrange(n)
            j = i + rng.randint(1, 60)
            datos[i:i] = datos[i:j]
        elif op == 3:  # insertar un trozo interesante
            datos[rng.randint(0, n) : 0] = rng.choice(TROZOS)
        elif op == 4:  # insertar bytes aleatorios
            datos[rng.randint(0, n) : 0] = bytes(
                rng.randrange(256) for _ in range(rng.randint(1, 12))
            )
        elif op == 5 and n:  # truncar
            del datos[rng.randrange(n) :]
        elif op == 6 and n:  # cambiar un dígito
            digitos = [i for i, b in enumerate(datos) if 48 <= b <= 57]
            if digitos:
                datos[rng.choice(digitos)] = rng.randrange(48, 58)
        elif op == 7 and n:  # reemplazar un tramo por un trozo interesante
            i = rng.randrange(n)
            datos[i : i + rng.randint(1, 10)] = rng.choice(TROZOS)
        elif op == 8 and otros:  # injertar un tramo de otro archivo
            otro = rng.choice(otros)
            if otro:
                i = rng.randrange(len(otro))
                datos[rng.randint(0, n) : 0] = otro[i : i + rng.randint(1, 200)]
        elif op == 9 and n:  # intercambiar dos bytes
            i, j = rng.randrange(n), rng.randrange(n)
            datos[i], datos[j] = datos[j], datos[i]
    return bytes(datos)


VALORES = [
    None, True, False, 0, 1, -1, 2, 10**30, 1.5, 2.0, "", "x", "a" * 300, "\x00", "\u202e", "ana@pve!t=abc", [], [1],  # noqa: E501
    {}, {"a": 1}, ["x"] * 120, [{}] * 120, {"token": "CENTINELA-SECRETO", "password": 1}, "seabios", "ovmf", "iso",  # noqa: E501
    "automatico", "por_filas", "homogeneo", 100, 101, 999_999_999, 1_000_000_000, 4096, 65537,
]  # fmt: skip


def _valor(rng: random.Random):
    return copy.deepcopy(rng.choice(VALORES))


def _mutar_estructura(valor, rng: random.Random, profundidad: int = 0):
    """Cambia, borra o añade un nodo cualquiera de un documento JSON (sigue siendo JSON válido)."""
    if isinstance(valor, dict) and valor and rng.random() < 0.8:
        clave = rng.choice(list(valor))
        op = rng.randrange(5)
        if op == 0:
            del valor[clave]
        elif op == 1:
            valor[clave] = _valor(rng)
        elif op == 2:
            valor[
                rng.choice(["token", "extra", "vmid", "nombre", "x" * 70, "Password", "api_key"])
            ] = _valor(rng)
        else:
            valor[clave] = _mutar_estructura(valor[clave], rng, profundidad + 1)
        return valor
    if isinstance(valor, list) and valor and rng.random() < 0.8:
        i = rng.randrange(len(valor))
        op = rng.randrange(4)
        if op == 0:
            del valor[i]
        elif op == 1:
            valor[i] = _valor(rng)
        elif op == 2:
            valor.extend([valor[i]] * rng.randint(1, 120))
        else:
            valor[i] = _mutar_estructura(valor[i], rng, profundidad + 1)
        return valor
    return _valor(rng)


def _mutar_json(base: bytes, rng: random.Random) -> bytes:
    try:
        documento = json.loads(base.decode("utf-8-sig"))
    except ValueError:
        return _mutar(base, rng, [base])
    for _ in range(rng.randint(1, 4)):
        documento = _mutar_estructura(documento, rng)
    return json.dumps(documento, ensure_ascii=rng.random() < 0.5).encode()


def _entradas(semilla: int, muestras: list[bytes], *, json_estructural: bool = False):
    rng = random.Random(semilla)
    for i in range(ENTRADAS):
        if i % 20 == 0:  # una de cada 20 es ruido puro
            yield bytes(rng.randrange(256) for _ in range(rng.randint(0, 300)))
        elif (
            json_estructural and i % 10 < 6
        ):  # 6 de cada 10: JSON válido con la estructura alterada
            yield _mutar_json(rng.choice(muestras), rng)
        else:
            yield _mutar(rng.choice(muestras), rng, muestras)


def _ejecutar(funcion, entrada: bytes) -> None:
    try:
        funcion(entrada)
    except ErrorProxLaunch as exc:
        assert exc.codigo in CODIGOS_PERMITIDOS, (exc.codigo, entrada[:200])
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in exc.params.items()), (
            exc.params
        )
    except BaseException as exc:  # noqa: BLE001 - lo que se quiere detectar
        pytest.fail(
            f"excepción sin controlar {type(exc).__name__}: {exc!r} con la entrada {entrada[:300]!r}"  # noqa: E501
        )


def _muestras(*nombres: str) -> list[bytes]:
    return [(DATOS_MVP3 / n).read_bytes() for n in nombres]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_la_suite_no_puede_abrir_sockets():
    """Sin red: si un lector intentara conectar, ``pytest-socket`` fallaría la prueba."""
    with pytest.raises(Exception) as exc:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    assert "socket" in type(exc.value).__name__.lower() or "socket" in str(exc.value).lower()


def test_fuzz_de_leer_perfiles():
    muestras = _muestras("perfiles-v1.json", "lote-homogeneo-v1.json", "perfiles-truncado.json")
    for entrada in _entradas(1, muestras, json_estructural=True):
        _ejecutar(leer_perfiles, entrada)


def test_fuzz_de_leer_lote():
    muestras = _muestras(
        "lote-homogeneo-v1.json",
        "lote-por-filas-v1.json",
        "perfiles-v1.json",
        "lote-version-futura.json",
    )
    for entrada in _entradas(2, muestras, json_estructural=True):
        _ejecutar(leer_lote, entrada)


def _tabla_e_interpretacion(entrada: bytes) -> None:
    tabla = leer_tabla(entrada)
    inv = _INVENTARIO
    perfiles = _PERFILES
    for con_inventario in (None, inv):  # solo capa 1 y capa 1 + vista previa contra el servidor
        interpretar(
            tabla,
            perfil_base=perfil_base(),
            perfiles=perfiles,
            inv=con_inventario,
            nodo_referencia="pve1",
        )


_INVENTARIO = inventario(
    (nodo("pve1"), nodo("pve2"), nodo("pve3", en_linea=False)),
    storages={n: (storage("datos"),) for n in ("pve1", "pve2", "pve3")},
)
_PERFILES = tuple(perfiles_fabrica())


def test_fuzz_de_leer_tabla_mas_interpretar():
    muestras = _muestras(
        "excel-windows1252.csv",
        "utf8-bom-comas.csv",
        "utf16-le.csv",
        "sep-linea.csv",
        "formulas.csv",
    )
    muestras.append(
        b"nombre;perfil;cpu;memoria;disco;almacenamiento;red;vlan;nodo;vmid\r\nweb-01;servidor-mediano;2;4 GiB;40;datos;vmbr0;20;pve1;150\r\n"  # noqa: E501
    )
    for entrada in _entradas(3, muestras):
        _ejecutar(_tabla_e_interpretacion, entrada)


def test_fuzz_el_tiempo_de_cada_entrada_es_acotado():
    """Ninguna entrada (de hasta 1 MiB) deja colgado el análisis ni dispara una complejidad cuadrática."""  # noqa: E501
    import time

    rng = random.Random(4)
    casos = [
        b'{"formato": "proxlaunch.lote", "x": ' + b"[" * 100_000 + b"]" * 100_000 + b"}",
        b'{"a": "' + b"\\u0000" * 200_000 + b'"}',
        b'{"formato": "proxlaunch.perfiles", "perfiles": ['
        + b",".join([b'{"nombre": "x"}'] * 50_000)
        + b"]}",
        b"nombre\r\n" + b'"' * 500_000,
        b"nombre;" * 200_000,
        b"\r\n".join([b"a;" * 30] * 20_000),
        bytes(rng.randrange(256) for _ in range(900_000)),
    ]
    inicio = time.process_time()
    for caso in casos:
        for funcion in (leer_perfiles, leer_lote, _tabla_e_interpretacion):
            _ejecutar(funcion, caso[: 1024 * 1024])
    assert time.process_time() - inicio < 20.0


def test_fuzz_del_lector_ninguna_lectura_supera_el_limite_mas_uno(tmp_path, monkeypatch):
    """Archivos de tamaño aleatorio alrededor del límite, con ``st_size`` mentiroso incluido."""
    rng = random.Random(5)
    limite = 4096
    pedidos: list[int] = []  # bytes leídos en cada llamada
    real_read, real_fstat = os.read, os.fstat

    def _leer(fd, n):
        trozo = real_read(fd, n)
        pedidos.append(len(trozo))  # bytes realmente obtenidos del archivo
        assert n <= limite + 1  # y nunca se pide un bloque mayor que límite + 1
        return trozo

    monkeypatch.setattr(os, "read", _leer)
    ruta = tmp_path / "f.bin"
    for i in range(1500):
        tamano = rng.choice(
            [0, 1, limite - 1, limite, limite + 1, limite * 2, rng.randint(0, limite * 12)]
        )
        ruta.write_bytes(bytes(tamano))
        if i % 3 == 0:  # st_size miente (archivo que crece o sistema de archivos raro)

            class _Falso:
                st_mode = real_fstat(os.open(ruta, os.O_RDONLY)).st_mode
                st_size = rng.randint(0, limite)

            monkeypatch.setattr(os, "fstat", lambda fd, _f=_Falso: _f)
        else:
            monkeypatch.setattr(os, "fstat", real_fstat)
        pedidos.clear()
        try:
            datos = leer_archivo_limitado(ruta, limite)
            assert len(datos) == tamano <= limite
        except ErrorProxLaunch as exc:
            assert exc.codigo == CodigoError.ARCHIVO_NO_PERMITIDO and tamano > limite
        assert sum(pedidos) <= limite + 1, (tamano, pedidos)
