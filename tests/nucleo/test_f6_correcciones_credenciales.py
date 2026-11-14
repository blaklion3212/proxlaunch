"""Corrección S4 de la fase 6 del MVP 3 (INV-M2, V-M05): ningún texto libre guardado lleva un token.

Al SERIALIZAR (lotes, perfiles y exportaciones) se lanza E-M08 con ``motivo="credencial"`` y el
nombre técnico del campo, sin el valor. Al LEER se rechaza el campo con el motivo ``TOKEN``.
El almacén de perfiles no escribe ni cambia su memoria ante un rechazo.
"""

import dataclasses
import hashlib
import logging
from datetime import datetime

import pytest

from proxlaunch.nucleo.archivos.esquema import ErrorArchivo, MotivoCampo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import ModoDestino
from proxlaunch.nucleo.lotes_guardados.formato import leer_lote, lote_a_bytes, lote_a_dict
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.vm import Disco, InterfazRed
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import (
    exportar_perfiles,
    leer_perfiles,
    perfil_a_dict,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)

from .apoyo_lote import definicion
from .apoyo_mvp3 import (
    archivo_lote,
    archivo_lote_por_filas,
    archivo_perfiles,
    cfg_hw,
    config_lote_json,
    config_perfil_json,
    definicion_filas,
    fila,
    lote_homogeneo_json,
    perfil_json,
)

# Parece un token (usuario@realm!id=secreto); el secreto es único para buscarlo en las salidas.
SECRETO = "secretoXYZ123"
TOKEN = f"ana@pve!x={SECRETO}"
TOKEN_CORTO = "a@b!c=xyz1234"  # 13 caracteres
AHORA = datetime(2026, 5, 14, 10, 30, 0)


def _error(funcion, *args, **kw) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        funcion(*args, **kw)
    return exc.value


def _sin_valor(e: ErrorProxLaunch, caplog) -> None:
    assert SECRETO not in str(e) and SECRETO not in repr(e)
    assert SECRETO not in str(e.params) and SECRETO not in e.detalle_tecnico
    assert SECRETO not in caplog.text


def _esperado(campo: str) -> dict[str, str]:
    return {"motivo": "credencial", "campo": campo}


# --- Lotes: escritura ----------------------------------------------------------------------------


def _lote_homogeneo(campo: str) -> LoteGuardado:
    """Lote homogéneo válido con el token en el campo indicado."""
    plantilla = cfg_hw()
    prefijo, separador, nodos, nombre = "web", "-", (), "Lote"
    cantidad, version = 3, None
    if campo == "nombre":
        nombre = TOKEN
    elif campo == "version_proxmox":
        version = TOKEN
    elif campo == "prefijo":
        prefijo = TOKEN
    elif campo == "separador":
        separador = TOKEN
    elif campo == "nodos":
        nodos = ("pve1", TOKEN)
    elif campo == "nombre_maquina":
        prefijo, cantidad = "", 1
        plantilla = dataclasses.replace(plantilla, nombre=TOKEN)
    elif campo == "tipo_cpu":
        plantilla = dataclasses.replace(plantilla, tipo_cpu=TOKEN)
    elif campo == "storage_efi":
        plantilla = dataclasses.replace(plantilla, storage_efi=TOKEN)
    elif campo == "storage":
        plantilla = dataclasses.replace(plantilla, discos=[Disco(TOKEN, 32)])
    elif campo == "bridge":
        plantilla = dataclasses.replace(plantilla, redes=[InterfazRed(TOKEN)])
    else:  # pragma: no cover
        raise AssertionError(campo)
    modo = ModoDestino.NODOS_ELEGIDOS if nodos else ModoDestino.AUTOMATICO
    d = definicion(
        cantidad,
        prefijo=prefijo,
        separador=separador,
        plantilla_vm=plantilla,
        modo=modo,
        nodos=nodos,
    )
    return LoteGuardado(nombre, d, version_proxmox=version)


CAMPOS_LOTE = [
    "nombre",
    "version_proxmox",
    "prefijo",
    "separador",
    "nodos",
    "nombre_maquina",
    "tipo_cpu",
    "storage_efi",
    "storage",
    "bridge",
]


@pytest.mark.parametrize("campo", CAMPOS_LOTE)
def test_s4_lote_homogeneo_con_token_en_el_campo_no_se_serializa(campo, caplog):
    caplog.set_level(logging.DEBUG)
    lote = _lote_homogeneo(campo)
    for funcion in (lote_a_dict, lambda lg: lote_a_bytes(lg, app_version="0.3.0")):
        e = _error(funcion, lote)
        assert e.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
        assert e.params == _esperado(campo)
        _sin_valor(e, caplog)


@pytest.mark.parametrize(
    ("campo", "filas"),
    [
        ("nombre_fila", [fila(TOKEN), fila("ok-02")]),
        ("nodo", [fila("ok-01"), fila("ok-02", nodo=None)]),
    ],
)
def test_s4_lote_por_filas_con_token_en_nombre_o_nodo_no_se_serializa(campo, filas, caplog):
    caplog.set_level(logging.DEBUG)
    if campo == "nodo":
        filas = [fila("ok-01", nodo=TOKEN), fila("ok-02")]
    lote = LoteGuardado("Por filas", definicion_filas(filas))
    e = _error(lote_a_bytes, lote, app_version="0.3.0")
    assert e.codigo == CodigoError.ARCHIVO_NO_GUARDABLE and e.params == _esperado(campo)
    _sin_valor(e, caplog)


def test_s4_un_lote_sin_tokens_se_serializa_y_se_lee():
    lote = _lote_homogeneo("nombre")
    lote = dataclasses.replace(lote, nombre="Lote normal, con ñ y espacios")
    assert leer_lote(lote_a_bytes(lote, app_version="0.3.0")).lote.nombre == lote.nombre


def test_s4_texto_parecido_a_un_correo_no_se_confunde_con_token():
    lote = dataclasses.replace(_lote_homogeneo("nombre"), nombre="soporte@ejemplo.org")
    assert lote_a_bytes(lote, app_version="0.3.0")


# --- Lotes: lectura ------------------------------------------------------------------------------


def _lectura_homogenea(campo: str) -> tuple[bytes, str]:
    """Archivo de lote con el token en el campo y la ruta que debe señalar el error."""
    cont = lote_homogeneo_json()
    raiz: dict = {}
    ruta = campo
    if campo == "nombre":
        raiz["nombre"] = TOKEN
    elif campo == "version_proxmox":
        raiz["version_proxmox"] = TOKEN
    elif campo in ("prefijo", "separador"):
        # El separador admite 16 caracteres como máximo: se usa un token corto para ese campo.
        cont["patron"][campo] = TOKEN_CORTO if campo == "separador" else TOKEN
        ruta = f"homogeneo.patron.{campo}"
    elif campo == "nodos":
        cont["destino"] = {"modo": "nodos_elegidos", "nodos": [TOKEN], "algoritmo": "equilibrado"}
        ruta = "homogeneo.destino.nodos[0]"
    elif campo == "nombre_maquina":
        cont["nombre_maquina"] = TOKEN
        ruta = "homogeneo.nombre_maquina"
    elif campo == "tipo_cpu":
        cont["config"]["tipo_cpu"] = TOKEN
        ruta = "homogeneo.config.tipo_cpu"
    elif campo == "storage_efi":
        cont["config"]["storage_efi"] = TOKEN
        ruta = "homogeneo.config.storage_efi"
    elif campo == "storage":
        cont["config"]["discos"][0]["storage"] = TOKEN
        ruta = "homogeneo.config.discos[0].storage"
    elif campo == "bridge":
        cont["config"]["redes"][0]["bridge"] = TOKEN
        ruta = "homogeneo.config.redes[0].bridge"
    return archivo_lote(cont, **raiz), ruta


@pytest.mark.parametrize("campo", CAMPOS_LOTE)
def test_s4_la_lectura_de_un_lote_rechaza_el_token_en_el_campo(campo, caplog):
    caplog.set_level(logging.DEBUG)
    datos, ruta = _lectura_homogenea(campo)
    e = _error(leer_lote, datos)
    assert isinstance(e, ErrorArchivo)
    assert (ruta, MotivoCampo.TOKEN) in [(x.ruta, x.motivo) for x in e.errores]
    _sin_valor(e, caplog)
    assert SECRETO not in repr(e.errores) and "xyz1234" not in repr(e.errores)


@pytest.mark.parametrize("campo", ["nombre", "nodo"])
def test_s4_la_lectura_de_un_lote_por_filas_rechaza_el_token(campo):
    f = {"nombre": "a-01", "vmid": None, "nodo": None, "config": config_lote_json()}
    f[campo] = TOKEN
    e = _error(leer_lote, archivo_lote_por_filas([f]))
    assert [x.motivo for x in e.errores] == [MotivoCampo.TOKEN]


# --- Perfiles: escritura -------------------------------------------------------------------------


def _perfil(campo: str) -> PerfilMaquina:
    nombre, descripcion = "Perfil", ""
    cfg = ConfigPerfil(discos=(DiscoPerfil(16),), redes=(RedPerfil(),))
    if campo == "nombre":
        nombre = TOKEN
    elif campo == "descripcion":
        descripcion = f"usa {TOKEN} para entrar"
    elif campo == "tipo_cpu":
        cfg = dataclasses.replace(cfg, tipo_cpu=TOKEN)
    elif campo == "storage_efi_preferido":
        cfg = dataclasses.replace(cfg, storage_efi_preferido=TOKEN)
    elif campo == "storage_preferido":
        cfg = dataclasses.replace(cfg, discos=(DiscoPerfil(16, storage_preferido=TOKEN),))
    elif campo == "bridge_preferido":
        cfg = dataclasses.replace(cfg, redes=(RedPerfil(bridge_preferido=TOKEN),))
    return PerfilMaquina("a" * 32, nombre, descripcion, OrigenPerfil.USUARIO, cfg)


CAMPOS_PERFIL = [
    "nombre",
    "descripcion",
    "tipo_cpu",
    "storage_efi_preferido",
    "storage_preferido",
    "bridge_preferido",
]
PISTAS = {"storage_efi_preferido", "storage_preferido", "bridge_preferido"}


@pytest.mark.parametrize("campo", CAMPOS_PERFIL)
def test_s4_perfil_con_token_en_el_campo_no_se_serializa(campo, caplog):
    caplog.set_level(logging.DEBUG)
    perfil = _perfil(campo)
    e = _error(perfil_a_dict, perfil, con_pistas=True)
    assert e.codigo == CodigoError.ARCHIVO_NO_GUARDABLE and e.params == _esperado(campo)
    _sin_valor(e, caplog)
    e = _error(perfiles_a_bytes, [perfil], con_pistas=True, app_version="0.3.0")
    assert e.params == _esperado(campo)


@pytest.mark.parametrize("campo", sorted(PISTAS))
def test_s4_con_pistas_desactivadas_las_pistas_con_token_no_fallan_ni_se_escriben(campo):
    perfil = _perfil(campo)
    datos = perfiles_a_bytes([perfil], con_pistas=False, app_version="0.3.0")
    assert SECRETO.encode() not in datos and b"_preferido" not in datos


@pytest.mark.parametrize("campo", sorted(set(CAMPOS_PERFIL) - PISTAS))
def test_s4_con_pistas_desactivadas_nombre_descripcion_y_cpu_siguen_validandose(campo):
    e = _error(perfiles_a_bytes, [_perfil(campo)], con_pistas=False, app_version="0.3.0")
    assert e.params == _esperado(campo)


@pytest.mark.parametrize("campo", CAMPOS_PERFIL)
def test_s4_exportar_perfiles_con_token_no_crea_archivo(tmp_path, campo):
    ruta = tmp_path / "salida.json"
    e = _error(exportar_perfiles, ruta, [_perfil(campo)], con_pistas=True, app_version="0.3.0")
    assert e.params == _esperado(campo)
    assert list(tmp_path.iterdir()) == []


# --- Perfiles: lectura ---------------------------------------------------------------------------


def _perfil_leido_json(campo: str) -> dict:
    cfg = config_perfil_json()
    p = perfil_json("Perfil", config=cfg)
    if campo in ("nombre", "descripcion"):
        p[campo] = TOKEN
    elif campo == "tipo_cpu":
        cfg["tipo_cpu"] = TOKEN
    elif campo == "storage_efi_preferido":
        cfg[campo] = TOKEN
    elif campo == "storage_preferido":
        cfg["discos"][0][campo] = TOKEN
    elif campo == "bridge_preferido":
        cfg["redes"][0][campo] = TOKEN
    return p


@pytest.mark.parametrize("campo", CAMPOS_PERFIL)
def test_s4_la_lectura_de_perfiles_rechaza_el_token_en_el_campo(campo):
    archivo = leer_perfiles(archivo_perfiles([_perfil_leido_json(campo)]))
    assert not archivo.validos and len(archivo.invalidos) == 1
    errores = archivo.invalidos[0].errores
    assert [e.motivo for e in errores] == [MotivoCampo.TOKEN]
    assert errores[0].ruta.split(".")[-1].split("[")[0] == campo
    assert SECRETO not in repr(archivo)


# --- Almacén de perfiles -------------------------------------------------------------------------


def _almacen(ruta) -> AlmacenPerfilesMaquina:
    n = {"i": 0}

    def _id() -> str:
        n["i"] += 1
        return f"{n['i']:032x}"

    return AlmacenPerfilesMaquina(
        ruta, fabrica=perfiles_fabrica(), generador_id=_id, ahora=lambda: AHORA
    )


def _hash(ruta) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _cfg(**kw) -> ConfigPerfil:
    return ConfigPerfil(discos=(DiscoPerfil(16),), redes=(RedPerfil(),), **kw)


@pytest.mark.parametrize("campo", ["nombre", "descripcion"])
def test_s4_crear_con_token_en_texto_libre_no_toca_el_archivo_ni_la_memoria(tmp_path, campo):
    ruta = tmp_path / "perfiles_maquina.json"
    almacen = _almacen(ruta)
    almacen.cargar()
    almacen.crear("Base", "", _cfg())
    antes, lista = _hash(ruta), almacen.usuario()
    nombre, desc = ("Otro", TOKEN) if campo == "descripcion" else (TOKEN, "")
    with pytest.raises(ErrorProxLaunch):
        almacen.crear(nombre, desc, _cfg())
    assert _hash(ruta) == antes and almacen.usuario() == lista


@pytest.mark.parametrize("campo", ["tipo_cpu", "storage_efi_preferido"])
def test_s4_crear_y_actualizar_con_token_en_la_config_no_tocan_archivo_ni_memoria(tmp_path, campo):
    ruta = tmp_path / "perfiles_maquina.json"
    almacen = _almacen(ruta)
    almacen.cargar()
    base = almacen.crear("Base", "", _cfg())
    antes, lista = _hash(ruta), almacen.usuario()
    malo = _cfg(**{campo: TOKEN})
    for operacion in (
        lambda: almacen.crear("Nuevo", "", malo),
        lambda: almacen.actualizar(base.id, malo),
    ):
        with pytest.raises(ErrorProxLaunch):
            operacion()
        assert _hash(ruta) == antes and almacen.usuario() == lista
    assert SECRETO.encode() not in ruta.read_bytes()


def test_s4_actualizar_con_token_en_una_pista_de_disco_o_red_no_toca_nada(tmp_path):
    ruta = tmp_path / "perfiles_maquina.json"
    almacen = _almacen(ruta)
    almacen.cargar()
    base = almacen.crear("Base", "", _cfg())
    antes, lista = _hash(ruta), almacen.usuario()
    for malo in (
        ConfigPerfil(discos=(DiscoPerfil(16, storage_preferido=TOKEN),), redes=(RedPerfil(),)),
        ConfigPerfil(discos=(DiscoPerfil(16),), redes=(RedPerfil(bridge_preferido=TOKEN),)),
    ):
        with pytest.raises(ErrorProxLaunch):
            almacen.actualizar(base.id, malo)
        assert _hash(ruta) == antes and almacen.usuario() == lista
