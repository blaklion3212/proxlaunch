"""Almacén de perfiles del usuario (RF-P03, RF-P04, RF-P09 importar, RF-P10, RF-P12;
CA-P03.4..P03.6,
CA-P04.*, CA-P09.3..P09.5, CA-P10.*, CA-P12.2/P12.3; INV-M7, INV-M8; §13 casos 2, 3 y 17).

``AlmacenPerfilesMaquina`` escribe a disco ANTES de cambiar la memoria, rechaza lo inválido con
``PERFIL_RECHAZADO`` (regla V-M01..V-M05), protege los perfiles de fábrica y no pisa un archivo
de versión futura ni uno que no pudo leer.
"""

import errno
import hashlib
import json
import os
import stat
from datetime import datetime
from pathlib import Path

import pytest

from proxlaunch.nucleo.archivos.constantes import MAX_PERFILES_USUARIO
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.almacen import (
    AccionImportar,
    AlmacenPerfilesMaquina,
    EntradaImportacion,
)
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import PerfilLeido
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    RedPerfil,
)

from .apoyo_mvp3 import config_perfil_json, sin_centinelas

AHORA = datetime(2026, 5, 14, 10, 30, 0)
posix = pytest.mark.skipif(os.name != "posix", reason="permisos POSIX")


def _contador_ids(inicio: int = 0):
    n = {"i": inicio}

    def _siguiente() -> str:
        n["i"] += 1
        return f"{n['i']:032x}"

    return _siguiente


def _almacen(ruta: Path, **kw) -> AlmacenPerfilesMaquina:
    kw.setdefault("generador_id", _contador_ids())
    return AlmacenPerfilesMaquina(ruta, fabrica=perfiles_fabrica(), ahora=lambda: AHORA, **kw)


def _config(cores=2, **kw) -> ConfigPerfil:
    return ConfigPerfil(cores=cores, discos=(DiscoPerfil(16),), redes=(RedPerfil(),), **kw)


def _escribir_almacen(ruta: Path, perfiles: list[dict], **raiz) -> bytes:
    cuerpo = {
        "formato": "proxlaunch.perfiles",
        "version_formato": 1,
        "app_version": "0.0.0",
        "perfiles": perfiles,
        **raiz,
    }
    datos = json.dumps(cuerpo, ensure_ascii=False).encode()
    ruta.write_bytes(datos)
    return datos


def _entrada(id_, nombre="Guardado", **cfg):
    return {"id": id_, "nombre": nombre, "descripcion": "", "config": config_perfil_json(**cfg)}


def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _rechazo(exc: pytest.ExceptionInfo) -> tuple[str, str]:
    assert exc.value.codigo == CodigoError.PERFIL_RECHAZADO
    return exc.value.params["regla"], exc.value.params["campo"]


# --- Carga (CA-P10.*, CA-P12.*; §13.3) ------------------------------------------------------------


def test_sin_archivo_arranca_vacio_y_no_crea_nada(tmp_path):
    """CA-P12.2."""
    ruta = tmp_path / "cfg" / "perfiles_maquina.json"
    a = _almacen(ruta)
    estado = a.cargar()
    assert a.usuario() == ()
    assert not estado.hubo_corrupcion and not estado.solo_lectura and not estado.error_lectura
    assert not ruta.exists() and not ruta.parent.exists()


def test_cargar_un_archivo_valido_conserva_ids_nombres_y_orden(tmp_path):
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada("b" * 32, "Segundo"), _entrada("a" * 32, "Primero")])
    a = _almacen(ruta)
    a.cargar()
    assert [(p.id, p.nombre, p.origen) for p in a.usuario()] == [
        ("b" * 32, "Segundo", OrigenPerfil.USUARIO),
        ("a" * 32, "Primero", OrigenPerfil.USUARIO),
    ]
    # MVP 4 (RF-O31, D-25): 9 perfiles de fábrica (6 de M3 + 3 nuevos).
    assert [p.id for p in a.todos()][:9] == [p.id for p in perfiles_fabrica()]
    assert a.todos()[9].nombre == "Segundo"


@pytest.mark.parametrize(
    "contenido",
    [
        b"",
        b"   ",
        b"{no es json",
        b"[]",
        b"[1, 2]",
        b'"texto"',
        b"42",
        b"\xff\xfe\x00basura",
        b"null",
    ],
)
def test_archivo_corrupto_se_conserva_como_danado_y_se_parte_de_vacio(tmp_path, contenido):
    """CA-P10.3 / §13.3: JSON inválido, UTF-8 inválido o raíz que no es un objeto."""
    ruta = tmp_path / "perfiles_maquina.json"
    ruta.write_bytes(contenido)
    a = _almacen(ruta)
    estado = a.cargar()
    assert estado.hubo_corrupcion and not estado.error_lectura
    assert a.usuario() == ()
    assert estado.copia_danada is not None
    assert estado.copia_danada.name == "perfiles_maquina.json.danado-20260514-103000"
    assert estado.copia_danada.read_bytes() == contenido  # el contenido original no se pierde
    assert not ruta.exists()


def test_una_segunda_copia_danada_del_mismo_instante_no_pisa_la_primera(tmp_path):
    ruta = tmp_path / "perfiles_maquina.json"
    ruta.write_bytes(b"uno")
    c1 = _almacen(ruta).cargar().copia_danada
    ruta.write_bytes(b"dos")
    c2 = _almacen(ruta).cargar().copia_danada
    assert c1 != c2 and c1.read_bytes() == b"uno" and c2.read_bytes() == b"dos"


def test_raiz_objeto_vacio_no_pierde_datos_ni_rompe(tmp_path):
    """§13.3: raíz ``{}`` sin ``perfiles``."""
    ruta = tmp_path / "perfiles_maquina.json"
    ruta.write_bytes(b"{}")
    a = _almacen(ruta)
    estado = a.cargar()
    assert a.usuario() == () and not estado.solo_lectura
    conservado = ruta.read_bytes() if ruta.exists() else estado.copia_danada.read_bytes()  # type: ignore[union-attr]  # noqa: E501
    assert conservado == b"{}"


def test_formato_ajeno_en_el_almacen_propio_no_se_pierde(tmp_path):
    ruta = tmp_path / "perfiles_maquina.json"
    datos = json.dumps({"formato": "otra.cosa", "version_formato": 1, "perfiles": []}).encode()
    ruta.write_bytes(datos)
    a = _almacen(ruta)
    estado = a.cargar()
    assert a.usuario() == ()
    conservado = ruta.read_bytes() if ruta.exists() else estado.copia_danada.read_bytes()  # type: ignore[union-attr]  # noqa: E501
    assert conservado == datos


def test_un_perfil_malo_entre_buenos_se_descarta_solo_el_malo_y_el_archivo_no_se_toca(tmp_path):
    """CA-P10.4 / §13.3."""
    ruta = tmp_path / "p.json"
    datos = _escribir_almacen(
        ruta,
        [
            _entrada("a" * 32, "Bueno 1"),
            _entrada("b" * 32, "Malo", cores=0),
            _entrada("c" * 32, "Bueno 2"),
        ],
    )
    a = _almacen(ruta)
    estado = a.cargar()
    assert [p.nombre for p in a.usuario()] == ["Bueno 1", "Bueno 2"]
    assert len(estado.descartados) >= 1
    assert estado.descartados[0].ruta.startswith("perfiles[1]")
    assert not estado.hubo_corrupcion
    assert ruta.read_bytes() == datos  # no se reescribe ni se renombra


@pytest.mark.parametrize(
    ("malo", "nota"),
    [
        ({"id": "FABRICA.X", "nombre": "A", "config": config_perfil_json()}, "id con mayúsculas"),
        ({"id": "fabrica.minimo", "nombre": "A", "config": config_perfil_json()}, "id reservado"),
        ({"id": 5, "nombre": "A", "config": config_perfil_json()}, "id no cadena"),
        ({"nombre": "A", "config": config_perfil_json()}, "sin id"),
        ({"id": "d" * 32, "nombre": "", "config": config_perfil_json()}, "sin nombre"),
        (
            {"id": "d" * 32, "nombre": "A", "config": config_perfil_json(origen="ova")},
            "origen",
        ),  # «iso» ya es válido (RF-O26)
        ("no es un objeto", "no objeto"),
        (None, "null"),
    ],
)
def test_perfiles_individuales_invalidos_se_descartan(tmp_path, malo, nota):
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada("a" * 32, "Bueno"), malo])
    a = _almacen(ruta)
    estado = a.cargar()
    assert [p.nombre for p in a.usuario()] == ["Bueno"], nota
    assert estado.descartados, nota


def test_ids_repetidos_en_el_archivo_descartan_el_segundo(tmp_path):
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada("a" * 32, "Uno"), _entrada("a" * 32, "Dos")])
    a = _almacen(ruta)
    estado = a.cargar()
    assert [p.nombre for p in a.usuario()] == ["Uno"] and estado.descartados


def test_mas_de_100_perfiles_en_el_archivo_cargan_100_y_descartan_el_resto(tmp_path):
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada(f"{i:032x}", f"P{i}") for i in range(1, 106)])
    a = _almacen(ruta)
    estado = a.cargar()
    assert len(a.usuario()) == MAX_PERFILES_USUARIO == 100
    assert len(estado.descartados) == 5


def test_sin_permiso_de_lectura_arranca_con_fabrica_avisa_y_no_pierde_el_archivo(tmp_path):
    """CA-P12.3 / §13.3."""
    ruta = tmp_path / "perfiles_maquina.json"
    datos = _escribir_almacen(ruta, [_entrada("a" * 32, "Mio")])
    ruta.chmod(0)
    try:
        if os.access(ruta, os.R_OK):
            pytest.skip("el proceso ignora los permisos (¿superusuario?)")
        a = _almacen(ruta)
        estado = a.cargar()
        assert estado.error_lectura and estado.hubo_corrupcion
        assert a.usuario() == () and a.todos() == a.fabrica
        with pytest.raises(ErrorProxLaunch) as exc:  # no se pisa un archivo que no se pudo leer
            a.crear("Nuevo", "", _config())
        assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    finally:
        ruta.chmod(0o600)
    assert ruta.read_bytes() == datos
    assert [p.name for p in tmp_path.iterdir()] == ["perfiles_maquina.json"]


# --- Versión futura: solo lectura (CA-P10.2, INV-M8) ----------------------------------------------


def _almacen_futuro(tmp_path):
    ruta = tmp_path / "perfiles_maquina.json"
    futuro = _entrada("a" * 32, "De la versión nueva")
    futuro["campo_de_v2"] = {"algo": "nuevo"}
    datos = _escribir_almacen(
        ruta, [futuro, _entrada("b" * 32, "Ilegible", cores=0)], version_formato=5
    )  # fase B: la 4 ya se lee (CA-B6.1.5); la «futura» es la 5
    a = _almacen(ruta)
    return ruta, datos, a, a.cargar()


def test_version_futura_muestra_los_perfiles_que_se_entienden_y_queda_en_solo_lectura(tmp_path):
    ruta, datos, a, estado = _almacen_futuro(tmp_path)
    assert estado.solo_lectura and not estado.hubo_corrupcion
    assert [p.nombre for p in a.usuario()] == ["De la versión nueva"]
    assert estado.descartados  # el que no pasa el esquema v1 se descarta
    assert ruta.read_bytes() == datos


@pytest.mark.parametrize(
    "operacion",
    [
        lambda a, p: a.crear("Otro", "", _config()),
        lambda a, p: a.actualizar(p.id, _config(cores=4)),
        lambda a, p: a.renombrar(p.id, "Nuevo nombre"),
        lambda a, p: a.duplicar(p.id, "Copia"),
        lambda a, p: a.eliminar(p.id),
        lambda a, p: a.importar([EntradaImportacion(PerfilLeido(0, "Importado", "", _config()))]),
    ],
    ids=["crear", "actualizar", "renombrar", "duplicar", "eliminar", "importar"],
)
def test_toda_escritura_en_solo_lectura_da_e_m14_y_no_toca_el_archivo(tmp_path, operacion):
    """INV-M8: un almacén de versión posterior no se sobrescribe."""
    ruta, datos, a, _ = _almacen_futuro(tmp_path)
    antes = a.usuario()
    with pytest.raises(ErrorProxLaunch) as exc:
        operacion(a, a.usuario()[0])
    assert exc.value.codigo == CodigoError.PERFILES_SOLO_LECTURA
    assert ruta.read_bytes() == datos
    assert a.usuario() == antes
    assert [p.name for p in tmp_path.iterdir()] == ["perfiles_maquina.json"]


# --- Crear y persistencia (CA-P03.*, CA-P04.7, CA-P10.1/P10.5/P10.6) ------------------------------


def test_crear_devuelve_el_perfil_con_id_generado_y_origen_usuario(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    p = a.crear("  Mi perfil  ", "desc", _config())
    assert p.id == f"{1:032x}" and p.nombre == "Mi perfil" and p.descripcion == "desc"
    assert p.origen == OrigenPerfil.USUARIO
    assert a.obtener(p.id) == p and a.usuario() == (p,)


def test_cada_operacion_queda_en_disco_antes_de_devolver_el_control(tmp_path):
    """CA-P04.7: se relee el almacén con otra instancia tras cada operación."""
    ruta = tmp_path / "carpeta" / "p.json"
    a = _almacen(ruta)
    a.cargar()

    def _en_disco() -> list[tuple[str, str, int]]:
        otra = _almacen(ruta)
        otra.cargar()
        return [(p.id, p.nombre, p.config.cores) for p in otra.usuario()]

    p1 = a.crear("Uno", "", _config(2))
    assert _en_disco() == [(p1.id, "Uno", 2)]
    p2 = a.crear("Dos", "", _config(3))
    a.actualizar(p1.id, _config(4))
    assert _en_disco() == [(p1.id, "Uno", 4), (p2.id, "Dos", 3)]
    a.renombrar(p2.id, "Dos bis")
    assert _en_disco() == [(p1.id, "Uno", 4), (p2.id, "Dos bis", 3)]
    copia = a.duplicar(p1.id, "Copia de Uno")
    assert _en_disco()[-1] == (copia.id, "Copia de Uno", 4)
    a.eliminar(p1.id)
    assert [x[1] for x in _en_disco()] == ["Dos bis", "Copia de Uno"]


def test_ida_y_vuelta_de_n_perfiles_conserva_datos_y_orden_de_creacion(tmp_path):
    """CA-P10.6."""
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    creados = [
        a.crear(f"Perfil {i:02d}", f"d{i}", ConfigPerfil(cores=1 + i % 8, memoria_mib=512 + i, discos=(DiscoPerfil(8 + i, storage_preferido=f"s{i}"),), redes=(RedPerfil(vlan=i + 1, bridge_preferido="vmbr0"),)))  # noqa: E501
        for i in range(25)
    ]  # fmt: skip
    b = _almacen(ruta)
    b.cargar()
    assert b.usuario() == tuple(creados)


@posix
def test_el_archivo_nace_0600_y_su_carpeta_0700(tmp_path):
    """CA-P10.5."""
    ruta = tmp_path / "config-nueva" / "perfiles_maquina.json"
    a = _almacen(ruta)
    a.cargar()
    a.crear("X", "", _config())
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert stat.S_IMODE(ruta.parent.stat().st_mode) == 0o700


def test_el_archivo_usa_la_envoltura_v1_con_ids_y_solo_campos_de_la_lista_blanca(tmp_path):
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    a.crear("X", "descripción", _config())
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    assert crudo["formato"] == "proxlaunch.perfiles" and crudo["version_formato"] == 1
    assert set(crudo) == {"formato", "version_formato", "app_version", "perfiles"}
    (perfil,) = crudo["perfiles"]
    assert set(perfil) == {"id", "nombre", "descripcion", "config"}
    assert not ruta.read_bytes().startswith(b"\xef\xbb\xbf")


def test_el_almacen_guarda_las_pistas_del_usuario(tmp_path):
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    config = ConfigPerfil(
        discos=(DiscoPerfil(8, storage_preferido="rapido"),),
        redes=(RedPerfil(bridge_preferido="vmbr3"),),
        storage_efi_preferido="efi",
    )
    p = a.crear("Con pistas", "", config)
    b = _almacen(ruta)
    b.cargar()
    assert b.obtener(p.id).config == config


@pytest.mark.parametrize(
    ("nombre", "descripcion", "config", "regla", "campo"),
    [
        ("", "", _config(), "V-M01", "nombre"),
        ("a" * 61, "", _config(), "V-M01", "nombre"),
        ("ab‮cd", "", _config(), "V-M04", "nombre"),
        ("ana@pve!x=abc", "", _config(), "V-M05", "nombre"),
        ("Bien", "PVEAPIToken=x", _config(), "V-M05", "descripcion"),
        ("Bien", "a" * 201, _config(), "V-M04", "descripcion"),
        ("Bien", "", _config(cores=0), "V-05", "cores"),
    ],
)
def test_lo_invalido_se_rechaza_sin_escribir_nada(
    tmp_path, nombre, descripcion, config, regla, campo
):
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    with pytest.raises(ErrorProxLaunch) as exc:
        a.crear(nombre, descripcion, config)
    assert _rechazo(exc) == (regla, campo)
    assert a.usuario() == () and not ruta.exists()


@pytest.mark.parametrize("existente", ["mi perfil", "MI PERFIL", "Mi Perfil"])
def test_nombre_repetido_de_usuario_sin_distinguir_mayusculas_se_rechaza(tmp_path, existente):
    """CA-P03.4."""
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    a.crear(existente, "", _config())
    with pytest.raises(ErrorProxLaunch) as exc:
        a.crear("Mi Perfil", "", _config())
    assert _rechazo(exc) == ("V-M01.duplicado", "nombre")
    assert len(a.usuario()) == 1


def test_nombre_igual_al_de_fabrica_se_rechaza_sin_distinguir_mayusculas(tmp_path):
    a = AlmacenPerfilesMaquina(
        tmp_path / "p.json",
        fabrica=perfiles_fabrica({"servidor-pequeno": ("Servidor pequeño", "")}),
        generador_id=_contador_ids(),
    )
    a.cargar()
    with pytest.raises(ErrorProxLaunch) as exc:
        a.crear("SERVIDOR PEQUEÑO", "", _config())
    assert _rechazo(exc) == ("V-M01.duplicado", "nombre")


def test_el_limite_de_100_perfiles_se_rechaza_con_v_m03(tmp_path):
    """CA-P03.5."""
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada(f"{i:032x}", f"P{i}") for i in range(1, 101)])
    a = _almacen(ruta)
    a.cargar()
    antes = _huella(ruta)
    with pytest.raises(ErrorProxLaunch) as exc:
        a.crear("El 101", "", _config())
    assert _rechazo(exc)[0] == "V-M03"
    with pytest.raises(ErrorProxLaunch) as exc2:
        a.duplicar("0" * 31 + "1", "Copia")
    assert _rechazo(exc2)[0] == "V-M03"
    assert _huella(ruta) == antes and len(a.usuario()) == 100


def test_un_id_generado_invalido_o_repetido_se_rechaza_con_v_m02(tmp_path):
    for malo in ("fabrica.minimo", "ABC", "", "con espacio"):
        a = _almacen(tmp_path / f"{abs(hash(malo))}.json", generador_id=lambda m=malo: m)
        a.cargar()
        with pytest.raises(ErrorProxLaunch) as exc:
            a.crear("X", "", _config())
        assert _rechazo(exc)[0] == "V-M02"
    a = _almacen(tmp_path / "rep.json", generador_id=lambda: "a" * 32)
    a.cargar()
    a.crear("Uno", "", _config())
    with pytest.raises(ErrorProxLaunch) as exc:
        a.crear("Dos", "", _config())
    assert _rechazo(exc)[0] == "V-M02"


# --- Fallo de escritura: la memoria no cambia (CA-P03.6, INV-M8) ----------------------------------


def _fallar_replace(monkeypatch, codigo=errno.ENOSPC):
    def _replace(*a, **k):
        raise OSError(codigo, "fallo inyectado")

    monkeypatch.setattr(os, "replace", _replace)


@pytest.mark.parametrize(
    "operacion",
    [
        lambda a, ids: a.crear("Nuevo", "", _config()),
        lambda a, ids: a.actualizar(ids[0], _config(cores=7)),
        lambda a, ids: a.renombrar(ids[0], "Renombrado"),
        lambda a, ids: a.duplicar(ids[0], "Copia"),
        lambda a, ids: a.eliminar(ids[0]),
        lambda a, ids: a.importar([EntradaImportacion(PerfilLeido(0, "Imp", "", _config()))]),
    ],
    ids=["crear", "actualizar", "renombrar", "duplicar", "eliminar", "importar"],
)
def test_si_falla_la_escritura_e_m08_la_memoria_y_el_archivo_no_cambian(
    tmp_path, monkeypatch, operacion
):
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada("a" * 32, "Existente")])
    a = _almacen(ruta)
    a.cargar()
    antes_mem, antes_disco = a.usuario(), _huella(ruta)
    _fallar_replace(monkeypatch)
    with pytest.raises(ErrorProxLaunch) as exc:
        operacion(a, [p.id for p in a.usuario()])
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert exc.value.params["motivo"] == "sin_espacio"
    monkeypatch.undo()
    assert a.usuario() == antes_mem
    assert _huella(ruta) == antes_disco
    assert [p.name for p in tmp_path.iterdir()] == ["p.json"]  # sin temporales


# --- Actualizar, renombrar, duplicar, eliminar ----------------------------------------------------


def test_actualizar_conserva_id_nombre_y_descripcion(tmp_path):
    """CA-P04.1."""
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    p = a.crear("Base", "desc", _config(2))
    n = a.actualizar(p.id, _config(8))
    assert (n.id, n.nombre, n.descripcion, n.config.cores) == (p.id, "Base", "desc", 8)
    assert a.usuario() == (n,)


def test_actualizar_con_una_configuracion_invalida_se_rechaza(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    p = a.crear("Base", "", _config())
    with pytest.raises(ErrorProxLaunch) as exc:
        a.actualizar(p.id, _config(cores=0))
    assert _rechazo(exc)[0] == "V-05"
    assert a.obtener(p.id) == p


def test_renombrar_cambia_nombre_y_descripcion_sin_tocar_config_ni_id(tmp_path):
    """CA-P04.2."""
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    p = a.crear("Base", "d1", _config(5))
    n = a.renombrar(p.id, "Nuevo")
    assert (n.id, n.nombre, n.descripcion, n.config) == (p.id, "Nuevo", "d1", p.config)
    n2 = a.renombrar(p.id, "Nuevo", "d2")
    assert n2.descripcion == "d2"


def test_renombrar_solo_cambiando_mayusculas_se_permite_pero_a_un_nombre_ajeno_no(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    p = a.crear("Base", "", _config())
    a.crear("Otro", "", _config())
    assert a.renombrar(p.id, "BASE").nombre == "BASE"
    with pytest.raises(ErrorProxLaunch) as exc:
        a.renombrar(p.id, "otro")
    assert _rechazo(exc)[0] == "V-M01.duplicado"


def test_duplicar_crea_un_perfil_nuevo_con_id_nuevo_tambien_de_fabrica(tmp_path):
    """CA-P04.3."""
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    c = a.duplicar("fabrica.servidor-mediano", "Copia de Servidor mediano")
    assert c.id != "fabrica.servidor-mediano" and c.origen == OrigenPerfil.USUARIO
    assert c.config == a.obtener("fabrica.servidor-mediano").config
    u = a.crear("Mío", "", _config(3))
    d = a.duplicar(u.id, "Copia de Mío")
    assert d.id != u.id and d.config == u.config


def test_la_copia_de_un_perfil_de_fabrica_no_cambia_si_la_fabrica_cambia_en_otra_version(tmp_path):
    """CA-P02.5."""
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    copia = a.duplicar("fabrica.minimo", "Mi mínimo")
    nueva_fabrica = tuple(
        p
        if p.id != "fabrica.minimo"
        else type(p)(p.id, p.nombre, p.descripcion, p.origen, _config(cores=64))
        for p in perfiles_fabrica()
    )
    b = AlmacenPerfilesMaquina(ruta, fabrica=nueva_fabrica, generador_id=_contador_ids())
    b.cargar()
    assert b.obtener(copia.id).config == copia.config
    assert b.obtener(copia.id).config.cores == 1


def test_eliminar_quita_solo_ese_perfil_y_persiste(tmp_path):
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    uno, dos, tres = (a.crear(n, "", _config()) for n in ("Uno", "Dos", "Tres"))
    a.eliminar(dos.id)
    assert a.usuario() == (uno, tres)
    b = _almacen(ruta)
    b.cargar()
    assert b.usuario() == (uno, tres)
    with pytest.raises(ErrorProxLaunch) as exc:
        b.obtener(dos.id)
    assert exc.value.codigo == CodigoError.PERFIL_INEXISTENTE


@pytest.mark.parametrize(
    "operacion",
    [
        lambda a, i: a.actualizar(i, _config(cores=9)),
        lambda a, i: a.renombrar(i, "Otro nombre"),
        lambda a, i: a.eliminar(i),
    ],
    ids=["actualizar", "renombrar", "eliminar"],
)
@pytest.mark.parametrize("id_fabrica", [p.id for p in perfiles_fabrica()])
def test_los_perfiles_de_fabrica_no_se_editan_renombran_ni_eliminan(
    tmp_path, operacion, id_fabrica
):
    """INV-M7 / E-M13."""
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    antes = a.obtener(id_fabrica)
    with pytest.raises(ErrorProxLaunch) as exc:
        operacion(a, id_fabrica)
    assert exc.value.codigo == CodigoError.PERFIL_NO_MODIFICABLE
    assert a.obtener(id_fabrica) == antes
    assert not ruta.exists()


@pytest.mark.parametrize(
    "operacion",
    [
        lambda a: a.actualizar("z" * 32, _config()),
        lambda a: a.renombrar("z" * 32, "X"),
        lambda a: a.eliminar("z" * 32),
        lambda a: a.duplicar("z" * 32, "X"),
        lambda a: a.obtener("z" * 32),
    ],
    ids=["actualizar", "renombrar", "eliminar", "duplicar", "obtener"],
)
def test_un_perfil_inexistente_es_e_m12_con_los_disponibles(tmp_path, operacion):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    with pytest.raises(ErrorProxLaunch) as exc:
        operacion(a)
    assert exc.value.codigo == CodigoError.PERFIL_INEXISTENTE
    assert 1 <= len(exc.value.params["disponibles"].split(", ")) <= 5


def test_buscar_por_nombre_ignora_mayusculas_y_acentos_y_acepta_el_id(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    p = a.crear("Café Ñandú", "", _config())
    assert a.buscar_por_nombre("cafe nandu") == [p]
    assert a.buscar_por_nombre("CAFÉ ÑANDÚ") == [p]
    assert a.buscar_por_nombre(p.id) == [p]
    assert a.buscar_por_nombre("minimo")[0].id == "fabrica.minimo"
    assert a.buscar_por_nombre("no existe") == []


# --- Importar (CA-P09.3..P09.5) -------------------------------------------------------------------


def _leido(nombre="Importado", cores=2) -> PerfilLeido:
    return PerfilLeido(0, nombre, "", _config(cores))


def test_importar_asigna_id_nuevo_y_origen_usuario_y_persiste(tmp_path):
    """CA-P09.4."""
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    (p,) = a.importar([EntradaImportacion(_leido())])
    assert p.id == f"{1:032x}" and p.origen == OrigenPerfil.USUARIO
    b = _almacen(ruta)
    b.cargar()
    assert b.usuario() == (p,)


def test_conservar_ambos_renombra_el_importado_con_sufijo(tmp_path):
    """CA-P09.3: «conservar ambos» (el importado queda como «<nombre> (2)»)."""
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    a.crear("Web", "", _config())
    (n1,) = a.importar([EntradaImportacion(_leido("web"))])
    (n2,) = a.importar([EntradaImportacion(_leido("WEB"))])
    assert (n1.nombre, n2.nombre) == ("web (2)", "WEB (3)")
    # Conflicto con un perfil de fábrica: también se conserva con sufijo.
    (n3,) = a.importar([EntradaImportacion(_leido("minimo"))])
    assert n3.nombre == "minimo (2)"


def test_varios_importados_con_el_mismo_nombre_en_el_mismo_lote_no_chocan(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    creados = a.importar([EntradaImportacion(_leido("Igual")), EntradaImportacion(_leido("Igual"))])
    assert [p.nombre for p in creados] == ["Igual", "Igual (2)"]


def test_reemplazar_sustituye_a_un_perfil_del_usuario_en_su_posicion_con_id_nuevo(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    uno = a.crear("Uno", "", _config(1))
    dos = a.crear("Dos", "", _config(2))
    tres = a.crear("Tres", "", _config(3))
    (nuevo,) = a.importar(
        [EntradaImportacion(_leido("Dos", cores=9), AccionImportar.REEMPLAZAR, reemplaza_id=dos.id)]
    )
    assert [p.nombre for p in a.usuario()] == ["Uno", "Dos", "Tres"]
    assert a.usuario()[1] == nuevo and nuevo.id != dos.id and nuevo.config.cores == 9
    assert a.usuario()[0] == uno and a.usuario()[2] == tres


def test_reemplazar_sin_id_lo_deduce_por_nombre_y_sin_coincidencia_es_e_m12(tmp_path):
    a = _almacen(tmp_path / "p.json")
    a.cargar()
    a.crear("Dos", "", _config(2))
    a.importar([EntradaImportacion(_leido("dos", 7), AccionImportar.REEMPLAZAR)])
    assert [p.config.cores for p in a.usuario()] == [7]
    with pytest.raises(ErrorProxLaunch) as exc:
        a.importar([EntradaImportacion(_leido("Inexistente"), AccionImportar.REEMPLAZAR)])
    assert exc.value.codigo == CodigoError.PERFIL_INEXISTENTE


def test_reemplazar_un_perfil_de_fabrica_nunca_se_permite_y_no_importa_ninguno(tmp_path):
    """CA-P09.3 / INV-M7 / todo o nada."""
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    for entrada in (
        EntradaImportacion(
            _leido("Servidor mediano"),
            AccionImportar.REEMPLAZAR,
            reemplaza_id="fabrica.servidor-mediano",
        ),
        EntradaImportacion(_leido("minimo"), AccionImportar.REEMPLAZAR),  # deducido por nombre
    ):
        with pytest.raises(ErrorProxLaunch) as exc:
            a.importar([EntradaImportacion(_leido("Bueno")), entrada])
        assert exc.value.codigo == CodigoError.PERFIL_NO_MODIFICABLE
        assert a.usuario() == () and not ruta.exists()  # «Bueno» tampoco se importó


def test_importar_que_supera_el_limite_no_importa_ninguno(tmp_path):
    """CA-P09.5: todo o nada para el límite."""
    ruta = tmp_path / "p.json"
    _escribir_almacen(ruta, [_entrada(f"{i:032x}", f"P{i}") for i in range(1, 99)])  # 98
    a = _almacen(ruta, generador_id=_contador_ids(5000))
    a.cargar()
    antes = _huella(ruta)
    with pytest.raises(ErrorProxLaunch) as exc:
        a.importar([EntradaImportacion(_leido(f"Nuevo {i}")) for i in range(3)])
    assert _rechazo(exc)[0] == "V-M03"
    assert len(a.usuario()) == 98 and _huella(ruta) == antes
    assert len(a.importar([EntradaImportacion(_leido(f"Cabe {i}")) for i in range(2)])) == 2
    assert len(a.usuario()) == 100


def test_importar_con_un_nombre_invalido_a_mitad_no_importa_ninguno(tmp_path):
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    with pytest.raises(ErrorProxLaunch):
        a.importar(
            [EntradaImportacion(_leido("Bueno")), EntradaImportacion(_leido("ana@pve!x=abc"))]
        )
    assert a.usuario() == () and not ruta.exists()


# --- Dos instancias (CA-P04.8, §13.17) ------------------------------------------------------------


def test_dos_instancias_la_ultima_escritura_gana_pero_el_archivo_nunca_queda_ilegible(tmp_path):
    ruta = tmp_path / "p.json"
    a, b = _almacen(ruta), _almacen(ruta)
    a.cargar()
    b.cargar()
    pa = a.crear("Desde A", "", _config())
    pb = b.crear("Desde B", "", _config())  # B no conoce lo de A
    c = _almacen(ruta)
    estado = c.cargar()
    assert not estado.hubo_corrupcion and not estado.descartados
    assert [p.nombre for p in c.usuario()] == ["Desde B"]  # última escritura gana (documentado)
    assert pa.nombre == "Desde A" and pb.nombre == "Desde B"
    json.loads(ruta.read_text(encoding="utf-8"))


# --- Privacidad (CA-P01.6, RNF-M03) ---------------------------------------------------------------


def test_el_archivo_del_almacen_no_contiene_centinelas_de_secretos(tmp_path):
    ruta = tmp_path / "p.json"
    a = _almacen(ruta)
    a.cargar()
    a.crear("Normal", "descripción normal", _config())
    assert sin_centinelas(ruta.read_bytes())
