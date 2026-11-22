"""Exportar e importar perfiles (RF-P08, RF-P09, RF-X01, RF-X02, RF-X04; CA-P08.*, CA-P09.*,
CA-X01.6, CA-X04.2/X04.3; INV-M3; §9.1 y §13 casos 3, 4 y 9 de los requisitos).

Un archivo de terceros se lee con esquema estricto: un perfil inválido NO invalida el archivo
(va a ``invalidos`` con la ruta de cada campo); las claves de credencial se ignoran sin leer sus
valores; ``id`` y ``origen`` del archivo no se leen jamás.
"""

import contextlib
import hashlib
import json
import logging
import os
import stat
import unicodedata

import pytest

from proxlaunch.nucleo.archivos.constantes import MAX_BYTES_PERFILES
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, ErrorArchivo, MotivoCampo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina, EntradaImportacion
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import (
    exportar_perfiles,
    leer_archivo_perfiles,
    leer_perfiles,
    perfiles_a_bytes,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)

from .apoyo_lote import volcar
from .apoyo_mvp3 import (
    CENT_PASSWORD,
    CENT_TOKEN,
    archivo_perfiles,
    config_perfil_json,
    perfil_json,
    sin_centinelas,
)


def _perfil(nombre="Mi perfil", desc="d", config=None) -> PerfilMaquina:
    cfg = config or ConfigPerfil(
        cores=3, memoria_mib=3072,
        discos=(DiscoPerfil(40, storage_preferido="ssd-1"),),
        redes=(RedPerfil(vlan=12, bridge_preferido="vmbr5"),),
        storage_efi_preferido="efi-1",
    )  # fmt: skip
    return PerfilMaquina("a" * 32, nombre, desc, OrigenPerfil.USUARIO, cfg)


def _regla_de(invalido, ruta_fin: str) -> list:
    return [e for e in invalido.errores if e.ruta.endswith(ruta_fin)]


# --- Exportar (CA-P08.*) --------------------------------------------------------------------------


def test_el_archivo_exportado_tiene_la_envoltura_y_la_lista_blanca_sin_id_ni_origen():
    datos = perfiles_a_bytes([_perfil()], con_pistas=True, app_version="0.3.0")
    assert not datos.startswith(b"\xef\xbb\xbf")
    crudo = json.loads(datos)
    assert crudo["formato"] == "proxlaunch.perfiles"
    assert crudo["version_formato"] == 1 and crudo["app_version"] == "0.3.0"
    (p,) = crudo["perfiles"]
    assert set(p) == {"nombre", "descripcion", "config"}
    assert "origen" not in p and "id" not in p
    assert (
        crudo["perfiles"][0]["config"]["origen"] == "disco_vacio"
    )  # el origen del SO, no del perfil
    assert sin_centinelas(datos)


def test_un_perfil_de_fabrica_exportado_se_describe_como_un_perfil_normal():
    """CA-P08.3."""
    datos = perfiles_a_bytes(list(perfiles_fabrica()), con_pistas=False, app_version="1")
    texto = datos.decode()
    assert "fabrica" not in texto
    importado = leer_perfiles(datos)
    assert len(importado.validos) == 9 and not importado.invalidos  # RF-O31: 6 + 3 de fábrica


def test_ida_y_vuelta_exportar_importar_con_pistas():
    """CA-P08.7."""
    original = [
        _perfil("Uno", "d1"),
        _perfil("Dos", "línea1\nlínea2", ConfigPerfil(discos=(), con_disco=False, redes=())),
    ]
    leido = leer_perfiles(perfiles_a_bytes(original, con_pistas=True, app_version="1"))
    assert [(p.nombre, p.descripcion, p.config) for p in leido.validos] == [
        (p.nombre, p.descripcion, p.config) for p in original
    ]
    assert [p.indice for p in leido.validos] == [0, 1]
    assert leido.avisos == () and leido.invalidos == ()


def test_sin_pistas_el_perfil_importado_no_trae_nombres_de_storage_ni_bridge():
    """CA-P08.2."""
    texto = perfiles_a_bytes([_perfil()], con_pistas=False, app_version="1").decode()
    for pista in ("ssd-1", "vmbr5", "efi-1"):
        assert pista not in texto
    (leido,) = leer_perfiles(texto.encode()).validos
    assert leido.config.discos[0].storage_preferido is None
    assert leido.config.redes[0].bridge_preferido is None
    assert leido.config.storage_efi_preferido is None


def test_las_pistas_importadas_se_conservan_como_pistas():
    """CA-P09.8."""
    (leido,) = leer_perfiles(
        perfiles_a_bytes([_perfil()], con_pistas=True, app_version="1")
    ).validos
    assert leido.config.discos[0].storage_preferido == "ssd-1"
    assert leido.config.redes[0].bridge_preferido == "vmbr5"
    assert leido.config.storage_efi_preferido == "efi-1"


def test_exportar_escribe_atomico_en_la_ruta_elegida_y_con_0600(tmp_path):
    ruta = tmp_path / "Mis perfiles ñandú.proxlaunch-perfiles.json"
    exportar_perfiles(ruta, [_perfil()], con_pistas=False, app_version="1")
    assert len(leer_perfiles(ruta.read_bytes()).validos) == 1
    if os.name == "posix":
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [ruta.name]


def test_exportar_sobre_un_archivo_existente_lo_reemplaza_y_si_falla_lo_deja_intacto(
    tmp_path, monkeypatch
):
    """CA-P08.6."""
    ruta = tmp_path / "x.json"
    ruta.write_bytes(b"ORIGINAL")

    def _replace(*a, **k):
        raise OSError(28, "disco lleno")

    monkeypatch.setattr(os, "replace", _replace)
    with pytest.raises(ErrorProxLaunch) as exc:
        exportar_perfiles(ruta, [_perfil()], con_pistas=False, app_version="1")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    monkeypatch.undo()
    assert ruta.read_bytes() == b"ORIGINAL"
    exportar_perfiles(ruta, [_perfil()], con_pistas=False, app_version="1")
    assert ruta.read_bytes() != b"ORIGINAL"


# --- Importar: id, origen y límites (§13.4) -------------------------------------------------------


def test_id_y_origen_del_archivo_no_se_leen_y_el_almacen_asigna_los_suyos(tmp_path):
    """CA-P09.4 / CA-P02.7: ``id = fabrica.servidor-pequeno`` y ``origen = fabrica``."""
    datos = archivo_perfiles(
        [perfil_json("Intruso", id="fabrica.servidor-pequeno", origen="fabrica")]
    )
    archivo = leer_perfiles(datos)
    (leido,) = archivo.validos
    assert not hasattr(leido, "id") and not hasattr(leido, "origen")
    assert archivo.avisos == ()  # id y origen se aceptan en el archivo (aunque no se lean)
    almacen = AlmacenPerfilesMaquina(tmp_path / "p.json", fabrica=perfiles_fabrica())
    almacen.cargar()
    (creado,) = almacen.importar([EntradaImportacion(leido)])
    assert creado.id != "fabrica.servidor-pequeno" and not creado.id.startswith("fabrica.")
    assert creado.origen == OrigenPerfil.USUARIO
    assert almacen.obtener("fabrica.servidor-pequeno").nombre == "servidor-pequeno"  # intacta


def test_exactamente_100_perfiles_se_aceptan_y_101_se_rechazan_antes_de_interpretarlos():
    """CA-P09.6 / §13.4."""
    assert (
        len(leer_perfiles(archivo_perfiles([perfil_json(f"P{i}") for i in range(100)])).validos)
        == 100
    )
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_perfiles(archivo_perfiles([1] * 101))  # ni siquiera son objetos: no se interpretan
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert exc.value.params == {"motivo": "demasiadas_entradas", "limite": "100", "tamano": "101"}


def test_un_archivo_de_300_kib_se_rechaza_sin_interpretarlo(tmp_path):
    """CA-P09.6: E-M01 por tamaño (256 KiB)."""
    ruta = tmp_path / "grande.json"
    ruta.write_bytes(archivo_perfiles([perfil_json("x" * 40)]) + b" " * (300 * 1024))
    assert MAX_BYTES_PERFILES == 256 * 1024
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_perfiles(ruta)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert exc.value.params["motivo"] == "demasiado_grande"
    assert exc.value.params["limite"] == str(256 * 1024)


def test_un_archivo_de_exactamente_256_kib_valido_se_lee(tmp_path):
    base = archivo_perfiles([perfil_json("Uno")])
    ruta = tmp_path / "justo.json"
    ruta.write_bytes(base + b" " * (MAX_BYTES_PERFILES - len(base)))
    assert len(leer_archivo_perfiles(ruta).validos) == 1


# --- Credenciales y campos desconocidos (CA-P09.7, CA-X04.2, CA-X01.6) ----------------------------


def test_claves_token_y_password_se_ignoran_sin_leerlas_y_se_avisa():
    p = perfil_json("Con claves")
    p["token"] = CENT_TOKEN
    p["config"]["password"] = CENT_PASSWORD
    p["config"]["discos"][0]["api_key"] = "CENTINELA-SECRETO-apikey"
    datos = archivo_perfiles([p], ticket="CENTINELA-SECRETO-ticket-raiz", csrf="x")
    archivo = leer_perfiles(datos)
    assert len(archivo.validos) == 1 and not archivo.invalidos
    (aviso,) = [a for a in archivo.avisos if a.codigo == CodigoAvisoArchivo.CREDENCIAL_IGNORADA]
    assert aviso.params == {"n": "5"}  # token, password, api_key, ticket y csrf
    assert "CENTINELA-SECRETO" not in volcar(archivo)
    assert CENT_TOKEN not in volcar(archivo)


def test_lo_ignorado_no_se_reescribe_al_exportar():
    p = perfil_json("Con claves")
    p["token"] = CENT_TOKEN
    p["campo_raro"] = {"x": 1}
    (leido,) = leer_perfiles(archivo_perfiles([p])).validos
    reexportado = perfiles_a_bytes(
        [
            PerfilMaquina(
                "b" * 32, leido.nombre, leido.descripcion, OrigenPerfil.USUARIO, leido.config
            )
        ],
        con_pistas=True,
        app_version="1",
    )
    assert b"token" not in reexportado and b"campo_raro" not in reexportado
    assert sin_centinelas(reexportado)


def test_campos_desconocidos_se_cuentan_en_un_aviso_sin_mostrar_sus_valores():
    p = perfil_json("Nuevo")
    p["extra_uno"] = "VALOR-PRIVADO-1"
    p["config"]["extra_dos"] = ["VALOR-PRIVADO-2"]
    archivo = leer_perfiles(archivo_perfiles([p], otra_clave_raiz=7))
    (aviso,) = [a for a in archivo.avisos if a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS]
    assert aviso.params == {"n": "3"}
    assert "VALOR-PRIVADO" not in volcar(archivo)
    assert len(archivo.validos) == 1


# --- Perfiles inválidos no invalidan el archivo (CA-P09.2) ----------------------------------------


def test_un_perfil_invalido_se_marca_con_la_ruta_del_campo_y_los_demas_se_importan():
    malo = perfil_json("Malo", config=config_perfil_json(discos=[
        {"tamano_gib": 10}, {"tamano_gib": "mucho"},
    ]))  # fmt: skip
    archivo = leer_perfiles(
        archivo_perfiles([perfil_json("Bueno 1"), malo, perfil_json("Bueno 2")])
    )
    assert [p.nombre for p in archivo.validos] == ["Bueno 1", "Bueno 2"]
    assert [p.indice for p in archivo.validos] == [0, 2]
    (inv,) = archivo.invalidos
    assert inv.indice == 1 and inv.nombre == "Malo"
    (e,) = inv.errores
    assert (e.ruta, e.motivo) == ("perfiles[1].config.discos[1].tamano_gib", MotivoCampo.TIPO)


@pytest.mark.parametrize(
    ("config", "ruta_fin", "motivo"),
    [
        ({"cores": "2"}, "cores", MotivoCampo.TIPO),
        ({"cores": True}, "cores", MotivoCampo.TIPO),
        ({"cores": 2.0}, "cores", MotivoCampo.TIPO),
        ({"cores": None}, "cores", MotivoCampo.TIPO),
        ({"cores": 0}, "cores", MotivoCampo.RANGO),
        ({"cores": 129}, "cores", MotivoCampo.RANGO),
        ({"sockets": 5}, "sockets", MotivoCampo.RANGO),
        ({"memoria_mib": "4096"}, "memoria_mib", MotivoCampo.TIPO),
        ({"memoria_mib": 15}, "memoria_mib", MotivoCampo.RANGO),
        ({"memoria_mib": 4096.0}, "memoria_mib", MotivoCampo.TIPO),
        ({"firmware": "UEFI"}, "firmware", MotivoCampo.ENUM),
        ({"firmware": 1}, "firmware", MotivoCampo.TIPO),
        ({"controlador_scsi": "lsi"}, "controlador_scsi", MotivoCampo.ENUM),
        ({"tipo_cpu": 5}, "tipo_cpu", MotivoCampo.TIPO),
        ({"tipo_cpu": ""}, "tipo_cpu", MotivoCampo.LONGITUD),
        ({"con_disco": "si"}, "con_disco", MotivoCampo.TIPO),
        ({"con_disco": 1}, "con_disco", MotivoCampo.TIPO),
        ({"discos": "no"}, "discos", MotivoCampo.TIPO),
        ({"discos": [5]}, "discos[0]", MotivoCampo.TIPO),
        ({"discos": [{"tamano_gib": 0}]}, "discos[0].tamano_gib", MotivoCampo.RANGO),
        ({"discos": [{"tamano_gib": 8, "bus": "SCSI"}]}, "discos[0].bus", MotivoCampo.ENUM),
        ({"discos": [{"tamano_gib": 8, "discard": "true"}]}, "discos[0].discard", MotivoCampo.TIPO),
        (
            {"discos": [{"tamano_gib": 8, "storage_preferido": 3}]},
            "discos[0].storage_preferido",
            MotivoCampo.TIPO,
        ),
        (
            {"discos": [{"tamano_gib": 8, "storage_preferido": "a\x00b"}]},
            "discos[0].storage_preferido",
            MotivoCampo.TEXTO_NO_VALIDO,
        ),
        ({"discos": [{"tamano_gib": 8}] * 58}, "discos", MotivoCampo.DEMASIADOS),
        ({"redes": [{"vlan": 0}]}, "redes[0].vlan", MotivoCampo.RANGO),
        ({"redes": [{"vlan": 4095}]}, "redes[0].vlan", MotivoCampo.RANGO),
        ({"redes": [{"vlan": "10"}]}, "redes[0].vlan", MotivoCampo.TIPO),
        ({"redes": [{"modelo": "rtl8139"}]}, "redes[0].modelo", MotivoCampo.ENUM),
        ({"redes": [{}] * 33}, "redes", MotivoCampo.DEMASIADOS),
        ({"ballooning": {"activo": True}}, "ballooning.minimo_mib", MotivoCampo.REQUERIDO),
        ({"ballooning": {"activo": 1, "minimo_mib": 512}}, "ballooning.activo", MotivoCampo.TIPO),
        ({"ballooning": "si"}, "ballooning", MotivoCampo.TIPO),
        ({"storage_efi_preferido": 5}, "storage_efi_preferido", MotivoCampo.TIPO),
        ({"origen": "ova"}, "origen", MotivoCampo.ENUM),  # «iso» ya es válido (RF-O26)
        ({"origen": 5}, "origen", MotivoCampo.TIPO),
    ],
)
def test_cada_tipo_erroneo_de_la_configuracion_se_informa_con_su_ruta(config, ruta_fin, motivo):
    """CA-X02.4 / CA-P01.2."""
    archivo = leer_perfiles(
        archivo_perfiles([perfil_json("X", config=config_perfil_json(**config))])
    )
    assert archivo.validos == ()
    (inv,) = archivo.invalidos
    encontrados = _regla_de(inv, ruta_fin)
    assert encontrados, [(e.ruta, e.motivo) for e in inv.errores]
    assert any(e.motivo == motivo for e in encontrados), [(e.ruta, e.motivo) for e in encontrados]


def test_los_rangos_de_capa_1_de_m1_se_comprueban_al_leer():
    """CA-P01.4: una configuración que no pasa la capa 1 es un perfil inválido."""
    cfg = config_perfil_json(discos=[{"tamano_gib": 8, "bus": "virtio", "ssd": True}])
    (inv,) = leer_perfiles(archivo_perfiles([perfil_json("X", config=cfg)])).invalidos
    assert any(e.params.get("regla") == "V-12" for e in inv.errores)


def test_31_discos_scsi_se_leen_y_32_son_invalidos_y_lo_mismo_con_32_y_33_redes():
    """§13.1."""
    disco = {"tamano_gib": 1}
    ok = leer_perfiles(
        archivo_perfiles(
            [perfil_json("A", config=config_perfil_json(discos=[disco] * 31, redes=[{}] * 32))]
        )
    )
    assert len(ok.validos) == 1
    mal_d = leer_perfiles(
        archivo_perfiles([perfil_json("A", config=config_perfil_json(discos=[disco] * 32))])
    )
    assert any(e.params.get("regla") == "V-07" for e in mal_d.invalidos[0].errores)
    mal_r = leer_perfiles(
        archivo_perfiles([perfil_json("A", config=config_perfil_json(redes=[{}] * 33))])
    )
    assert any(
        e.ruta == "perfiles[0].config.redes" and e.motivo == MotivoCampo.DEMASIADOS
        for e in mal_r.invalidos[0].errores
    )  # el esquema corta antes de la regla V-23: el límite de interfaces es el mismo (32)


def test_perfil_sin_disco_con_con_disco_falso_es_valido():
    """§13.1 / CA-P01.5."""
    cfg = config_perfil_json(con_disco=False, discos=[])
    assert len(leer_perfiles(archivo_perfiles([perfil_json("Sin disco", config=cfg)])).validos) == 1


def test_valores_omitidos_toman_el_valor_por_defecto_del_perfil():
    cfg = {
        "sockets": 1,
        "cores": 2,
        "memoria_mib": 2048,
        "con_disco": False,
        "discos": [],
        "redes": [],
    }
    (p,) = leer_perfiles(archivo_perfiles([{"nombre": "Mínimo", "config": cfg}])).validos
    assert p.config.firmware.value == "seabios" and p.config.tipo_cpu == "x86-64-v2-AES"
    assert p.config.controlador_scsi.value == "virtio-scsi-single" and p.descripcion == ""


@pytest.mark.parametrize(
    ("campo", "valor", "motivo"),
    [
        ("nombre", "", MotivoCampo.LONGITUD),
        ("nombre", "a" * 61, MotivoCampo.LONGITUD),
        ("nombre", "ab‮cd", MotivoCampo.TEXTO_NO_VALIDO),
        ("nombre", "a\x00b", MotivoCampo.TEXTO_NO_VALIDO),
        ("nombre", "ana@pve!x=secretoabc", MotivoCampo.TOKEN),
        ("nombre", 5, MotivoCampo.TIPO),
        ("nombre", None, MotivoCampo.TIPO),
        ("descripcion", "PVEAPIToken=ana@pve!t=abc", MotivoCampo.TOKEN),
        ("descripcion", "usa ana@pve!t=abc123 para entrar", MotivoCampo.TOKEN),
        ("descripcion", "a" * 201, MotivoCampo.LONGITUD),
        ("descripcion", "a\x00b", MotivoCampo.TEXTO_NO_VALIDO),
        ("descripcion", "a‮b", MotivoCampo.TEXTO_NO_VALIDO),
        ("descripcion", 7, MotivoCampo.TIPO),
    ],
)
def test_nombre_y_descripcion_invalidos_hacen_invalido_al_perfil(campo, valor, motivo):
    """CA-P01.3 / CA-X04.3 / V-M04 / V-M05."""
    p = perfil_json("Bien")
    p[campo] = valor
    archivo = leer_perfiles(archivo_perfiles([p]))
    assert archivo.validos == ()
    (inv,) = archivo.invalidos
    assert any(e.ruta == f"perfiles[0].{campo}" and e.motivo == motivo for e in inv.errores)


def test_descripcion_con_salto_de_linea_y_de_200_caracteres_es_valida():
    p = perfil_json("Bien")
    p["descripcion"] = "línea\n" + "a" * 194
    (leido,) = leer_perfiles(archivo_perfiles([p])).validos
    assert "\n" in leido.descripcion and len(leido.descripcion) == 200


def test_nombre_nfd_se_normaliza_y_se_recorta():
    p = perfil_json(unicodedata.normalize("NFD", "  Ñandú  "))
    (leido,) = leer_perfiles(archivo_perfiles([p])).validos
    assert leido.nombre == "Ñandú"


def test_el_nombre_de_un_perfil_invalido_solo_se_muestra_si_es_seguro():
    seguro = perfil_json("Nombre visible", config=config_perfil_json(cores=0))
    peligroso = perfil_json("Peli‮groso", config=config_perfil_json(cores=0))
    archivo = leer_perfiles(archivo_perfiles([seguro, peligroso]))
    assert [i.nombre for i in archivo.invalidos] == ["Nombre visible", None]


def test_un_elemento_que_no_es_objeto_es_un_perfil_invalido_no_un_error_de_archivo():
    archivo = leer_perfiles(archivo_perfiles([perfil_json("Bien"), "texto", 5, None, [1]]))
    assert len(archivo.validos) == 1 and [i.indice for i in archivo.invalidos] == [1, 2, 3, 4]


def test_el_perfil_sin_config_es_invalido():
    archivo = leer_perfiles(archivo_perfiles([{"nombre": "Sin config"}]))
    (inv,) = archivo.invalidos
    assert any(
        e.ruta == "perfiles[0].config" and e.motivo == MotivoCampo.REQUERIDO for e in inv.errores
    )


# --- Errores de todo el archivo -------------------------------------------------------------------


@pytest.mark.parametrize("perfiles", ["x", {}, 5, None, True])
def test_perfiles_que_no_es_una_lista_es_e_m04(perfiles):
    with pytest.raises(ErrorArchivo) as exc:
        leer_perfiles(archivo_perfiles(**{"perfiles": perfiles}))
    assert exc.value.codigo == CodigoError.ARCHIVO_DANADO
    assert exc.value.params["campo"] == "perfiles"


def test_perfiles_ausente_es_e_m04():
    crudo = json.loads(archivo_perfiles())
    del crudo["perfiles"]
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_perfiles(json.dumps(crudo).encode())
    assert exc.value.codigo == CodigoError.ARCHIVO_DANADO


def test_una_lista_vacia_de_perfiles_es_valida():
    archivo = leer_perfiles(archivo_perfiles([]))
    assert archivo.validos == () and archivo.invalidos == ()


def test_un_lote_abierto_como_perfiles_da_e_m02_con_la_pista():
    """CA-G06.6 (al revés): el archivo de lote no se interpreta como perfiles."""
    datos = json.dumps({"formato": "proxlaunch.lote", "version_formato": 1}).encode()
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_perfiles(datos)
    assert exc.value.codigo == CodigoError.ARCHIVO_FORMATO_AJENO
    assert exc.value.params["encontrado"] == "proxlaunch.lote"


def test_version_futura_es_e_m03_y_version_invalida_e_m02():
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_perfiles(archivo_perfiles(version_formato=5))  # fase B: la 4 ya se lee (CA-B6.1.5)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    for malo in (0, -1, True, "1", 1.0):
        with pytest.raises(ErrorProxLaunch) as exc:
            leer_perfiles(archivo_perfiles(version_formato=malo))
        assert exc.value.codigo == CodigoError.ARCHIVO_FORMATO_AJENO


@pytest.mark.parametrize(
    "datos",
    [b"", b"{", b"[]", b"\xff\xfe", b'{"formato": "proxlaunch.perfiles", "formato": "x"}', b"NaN"],
)
def test_json_danado_es_e_m04_o_e_m02(datos):
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_perfiles(datos)
    assert exc.value.codigo in {CodigoError.ARCHIVO_DANADO, CodigoError.ARCHIVO_FORMATO_AJENO}


def test_un_bom_al_inicio_se_tolera():
    assert len(leer_perfiles(b"\xef\xbb\xbf" + archivo_perfiles()).validos) == 1


# --- INV-M3 y registro ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "contenido",
    [
        archivo_perfiles(),
        b"{ esto no es json",
        b"\xff\xfe\x00",
        b"[]",
        archivo_perfiles(version_formato=9),
    ],
    ids=["valido", "json_roto", "utf8_roto", "raiz_lista", "version_futura"],
)
def test_importar_un_archivo_no_lo_modifica_ni_aunque_este_danado(tmp_path, contenido):
    """INV-M3 / CA-X02.7: hash, fecha y carpeta intactos; nada de ``.danado``."""
    ruta = tmp_path / "terceros.json"
    ruta.write_bytes(contenido)
    antes = (hashlib.sha256(contenido).hexdigest(), ruta.stat().st_mtime_ns, ruta.stat().st_ino)
    with contextlib.suppress(ErrorProxLaunch):
        leer_archivo_perfiles(ruta)
    despues = (
        hashlib.sha256(ruta.read_bytes()).hexdigest(),
        ruta.stat().st_mtime_ns,
        ruta.stat().st_ino,
    )
    assert despues == antes
    assert [p.name for p in tmp_path.iterdir()] == ["terceros.json"]


def test_el_registro_de_la_importacion_lleva_nombre_y_cifras_pero_no_el_contenido(tmp_path, caplog):
    """CA-X02.10."""
    carpeta = tmp_path / "carpeta-del-usuario"
    carpeta.mkdir()
    ruta = carpeta / "perfiles-ajenos.json"
    ruta.write_bytes(
        archivo_perfiles(
            [
                perfil_json("Nombre-que-no-debe-loguearse"),
                perfil_json("Malo", config=config_perfil_json(cores=0)),
            ]
        )
    )
    with caplog.at_level(logging.DEBUG):
        leer_archivo_perfiles(ruta)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "perfiles-ajenos.json" in texto and "validos=1" in texto and "invalidos=1" in texto
    assert "Nombre-que-no-debe-loguearse" not in texto and "carpeta-del-usuario" not in texto
