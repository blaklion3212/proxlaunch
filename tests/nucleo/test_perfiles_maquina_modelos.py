"""Modelo del perfil, perfiles de fábrica y validación de nombres (RF-P01, RF-P02; CA-P01.*,
CA-P02.*; V-M01..V-M05; INV-M7; §8 y §13 casos 1 y 2 de los requisitos)."""

import dataclasses
import json
import unicodedata
from dataclasses import fields

import pytest

from proxlaunch.nucleo.archivos.esquema_config import config_perfil_a_dict, configuracion_a_dict
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.perfiles_maquina.aplicar import aplicar_perfil, config_desde_configuracion
from proxlaunch.nucleo.perfiles_maquina.fabrica import CLAVES_FABRICA, perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import perfil_a_dict, perfiles_a_bytes
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ID_PREDETERMINADO,
    PREFIJO_FABRICA,
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)
from proxlaunch.nucleo.perfiles_maquina.validacion import (
    id_valido,
    nombre_libre,
    validar_config_perfil,
    validar_descripcion,
    validar_nombre_perfil,
)
from proxlaunch.nucleo.validacion import Severidad, validar_vm
from proxlaunch.nucleo.valores_defecto import configuracion_por_defecto

from .apoyo_lote import inventario, nodo
from .apoyo_mvp3 import cfg_hw

PROHIBIDOS = ("vmid", "nombre_maquina", "nodo", "etiquetas")


def _claves(obj) -> set[str]:
    """Todas las claves de un JSON anidado."""
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _claves(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _claves(v)}
    return set()


def _perfil(nombre="X", config=None, id_="a" * 32, origen=OrigenPerfil.USUARIO):
    return PerfilMaquina(
        id_,
        nombre,
        "",
        origen,
        config or ConfigPerfil(discos=(DiscoPerfil(32),), redes=(RedPerfil(),)),
    )


# --- CA-P01.1 / CA-P06.8: sin vmid, nombre de MV, nodo ni etiquetas ---------------------------


def test_el_modelo_del_perfil_no_tiene_campos_vmid_nombre_nodo_ni_etiquetas():
    nombres = {f.name for f in fields(ConfigPerfil)}
    for clase in (DiscoPerfil, RedPerfil, BallooningPerfil):
        nombres |= {f.name for f in fields(clase)}
    assert not (nombres & {"vmid", "nombre", "nodo", "etiquetas"})


def test_ningun_campo_de_configuracionvm_prohibido_se_serializa_en_un_perfil():
    """CA-P01.1: se recorren todos los campos de ``ConfiguracionVM``; los del sitio/MV no salen."""
    cfg = cfg_hw(
        vmid=987654,
        nombre="MV-DEL-USUARIO",
        nodo="nodo-del-sitio",
        etiquetas=("proxlaunch", "lote-abcd1234"),
    )
    config = config_desde_configuracion(cfg, con_pistas=True)
    perfil = _perfil(config=config)
    serializaciones = [
        json.dumps(config_perfil_a_dict(config, con_pistas=True)),
        json.dumps(config_perfil_a_dict(config, con_pistas=False)),
        json.dumps(perfil_a_dict(perfil, con_pistas=True)),
        json.dumps(perfil_a_dict(perfil, con_pistas=True, con_id=True)),
        perfiles_a_bytes([perfil], con_pistas=True, app_version="1").decode(),
    ]
    for texto in serializaciones:
        for valor in ("987654", "MV-DEL-USUARIO", "nodo-del-sitio", "lote-abcd1234"):
            assert valor not in texto
        claves = _claves(json.loads(texto))
        for prohibida in ("vmid", "nodo", "etiquetas"):
            assert prohibida not in claves
    assert {f.name for f in fields(ConfiguracionVM)} >= {"vmid", "nombre", "nodo", "etiquetas"}


def test_configuracion_a_dict_de_lote_tampoco_lleva_vmid_nombre_nodo_ni_etiquetas():
    cfg = cfg_hw(vmid=987654, nombre="MV-X", nodo="nodo-y", etiquetas=("t",))
    claves = _claves(configuracion_a_dict(cfg))
    assert not (claves & {"vmid", "nombre", "nodo", "etiquetas"})
    assert "987654" not in json.dumps(configuracion_a_dict(cfg))


def test_las_claves_de_la_configuracion_de_un_perfil_son_exactamente_la_lista_blanca():
    claves_cfg = set(
        config_perfil_a_dict(
            ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),)), con_pistas=True
        )
    )
    assert claves_cfg == {
        "firmware", "sockets", "cores", "tipo_cpu", "memoria_mib", "ballooning", "con_disco",
        "discos", "storage_efi_preferido", "controlador_scsi", "redes", "origen",
    }  # fmt: skip
    d = config_perfil_a_dict(
        ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),)), con_pistas=True
    )
    assert set(d["discos"][0]) == {  # type: ignore[index]
        "tamano_gib", "bus", "formato", "discard", "ssd", "iothread", "storage_preferido",
    }  # fmt: skip
    assert set(d["redes"][0]) == {"modelo", "vlan", "bridge_preferido"}  # type: ignore[index]


def test_sin_pistas_se_omiten_todas_las_claves_preferido():
    """CA-P08.2: con la casilla desmarcada el perfil no lleva pistas."""
    config = ConfigPerfil(
        discos=(DiscoPerfil(8, storage_preferido="almacen-rapido"),),
        storage_efi_preferido="efi",
        redes=(RedPerfil(bridge_preferido="vmbr7"),),
    )
    d = config_perfil_a_dict(config, con_pistas=False)
    assert not [k for k in _claves(d) if k.endswith("_preferido")]
    assert "almacen-rapido" not in json.dumps(d) and "vmbr7" not in json.dumps(d)
    con = json.dumps(config_perfil_a_dict(config, con_pistas=True))
    assert all(v in con for v in ("almacen-rapido", "efi", "vmbr7"))


def test_los_modelos_del_perfil_son_inmutables():
    perfil = _perfil()
    with pytest.raises(dataclasses.FrozenInstanceError):
        perfil.nombre = "otro"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        perfil.config.cores = 9  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        DiscoPerfil(8).tamano_gib = 9  # type: ignore[misc]


# --- CA-P01.4 / CA-P01.5 / §13.1: capa 1 ----------------------------------------------------------


def _errores(config: ConfigPerfil) -> set[str]:
    return {p.codigo for p in validar_config_perfil(config) if p.severidad == Severidad.ERROR}


def _config(**cambios) -> ConfigPerfil:
    base = {"discos": (DiscoPerfil(32),), "redes": (RedPerfil(),)}
    base.update(cambios)
    return ConfigPerfil(**base)


def test_un_perfil_valido_no_tiene_errores_de_capa_1():
    assert validar_config_perfil(_config()) == []


def test_sin_disco_se_admite_si_con_disco_es_falso():
    """CA-P01.5 / §13.1: 0 discos."""
    assert validar_config_perfil(_config(con_disco=False, discos=())) == []


def test_con_disco_marcado_pero_sin_discos_es_error():
    assert "V-07.sindisco" in _errores(_config(con_disco=True, discos=()))


def test_un_disco_y_treinta_y_uno_scsi_se_aceptan_y_treinta_y_dos_no():
    """§13.1: límite de V-07 (31 discos SCSI)."""
    assert _errores(_config(discos=(DiscoPerfil(8),))) == set()
    assert _errores(_config(discos=tuple(DiscoPerfil(8) for _ in range(31)))) == set()
    assert "V-07" in _errores(_config(discos=tuple(DiscoPerfil(8) for _ in range(32))))


def test_limites_de_redes_v_23():
    """§13.1: máximo de interfaces de red (net0..net31 = 32)."""
    assert _errores(_config(redes=tuple(RedPerfil() for _ in range(32)))) == set()
    assert "V-23" in _errores(_config(redes=tuple(RedPerfil() for _ in range(33))))


@pytest.mark.parametrize(
    ("cambios", "regla"),
    [
        ({"cores": 0}, "V-05"),
        ({"cores": 129}, "V-05"),
        ({"sockets": 0}, "V-05"),
        ({"sockets": 5}, "V-05"),
        ({"memoria_mib": 15}, "V-06"),
        ({"memoria_mib": 0}, "V-06"),
        ({"memoria_mib": -4}, "V-06"),
        ({"tipo_cpu": "x86 64"}, "V-22"),
        ({"tipo_cpu": ""}, "V-22"),
        ({"tipo_cpu": "a,b"}, "V-22"),
        ({"ballooning": BallooningPerfil(True, 9999999)}, "V-06"),
        ({"ballooning": BallooningPerfil(True, 4)}, "V-06"),
        ({"discos": (DiscoPerfil(0),)}, "V-08"),
        ({"discos": (DiscoPerfil(65537),)}, "V-08"),
        ({"redes": (RedPerfil(vlan=0),)}, "V-15"),
        ({"redes": (RedPerfil(vlan=4095),)}, "V-15"),
    ],
)
def test_reglas_de_capa_1_del_perfil(cambios, regla):
    assert regla in _errores(_config(**cambios))


@pytest.mark.parametrize(
    "cambios",
    [
        {"cores": 1},
        {"cores": 128},
        {"sockets": 4},
        {"memoria_mib": 16},
        {"redes": (RedPerfil(vlan=1),)},
        {"redes": (RedPerfil(vlan=4094),)},
        {"discos": (DiscoPerfil(1),)},
        {"discos": (DiscoPerfil(65536),)},
    ],
)
def test_los_valores_en_el_limite_son_validos(cambios):
    assert _errores(_config(**cambios)) == set()


def test_las_reglas_incompatibles_de_disco_se_detectan_como_en_m1():
    """V-11/V-12/V-13 de M1 se reutilizan (CA-P07.1: sin reglas duplicadas)."""
    reglas = _errores(_config(discos=(DiscoPerfil(8, bus=Bus.VIRTIO, ssd=True),)))
    assert "V-12" in reglas


def test_una_pista_con_texto_no_valido_es_v_m04():
    config = _config(discos=(DiscoPerfil(8, storage_preferido="a\x00b"),))
    assert any(
        p.codigo == "V-M04" and p.campo == "discos[0].storage_preferido"
        for p in validar_config_perfil(config)
    )


# --- CA-P01.3: nombre del perfil (V-M01..V-M05) ---------------------------------------------------


def test_nombre_de_60_y_61_caracteres():
    nombre, problemas = validar_nombre_perfil("a" * 60, [])
    assert nombre == "a" * 60 and problemas == []
    _, problemas = validar_nombre_perfil("a" * 61, [])
    assert [p.codigo for p in problemas] == ["V-M01"]


def test_nombre_en_nfd_se_normaliza_a_nfc_y_con_acentos_es_valido():
    nombre, problemas = validar_nombre_perfil(unicodedata.normalize("NFD", "Café Ñandú"), [])
    assert (nombre, problemas) == ("Café Ñandú", [])


def test_nombre_con_u202e_es_v_m04():
    assert [p.codigo for p in validar_nombre_perfil("ab‮cd", [])[1]] == ["V-M04"]


def test_nombre_vacio_es_v_m01_y_con_token_es_v_m05():
    assert [p.codigo for p in validar_nombre_perfil("  ", [])[1]] == ["V-M01"]
    assert [p.codigo for p in validar_nombre_perfil("ana@pve!x=abc123", [])[1]] == ["V-M05"]


@pytest.mark.parametrize("otro", ["mi perfil", "MI PERFIL", "Mi Perfil", "  mi perfil  "])
def test_nombre_repetido_sin_distinguir_mayusculas_es_duplicado(otro):
    existente = _perfil("Mi Perfil")
    _, problemas = validar_nombre_perfil(otro, [existente])
    assert [p.codigo for p in problemas] == ["V-M01.duplicado"]


def test_el_nombre_de_un_perfil_de_fabrica_tambien_cuenta_para_la_unicidad():
    fabrica = perfiles_fabrica({"servidor-pequeno": ("Servidor pequeño", "")})
    _, problemas = validar_nombre_perfil("SERVIDOR PEQUEÑO", fabrica)
    assert [p.codigo for p in problemas] == ["V-M01.duplicado"]


def test_excluir_id_permite_conservar_el_propio_nombre():
    p = _perfil("Mi Perfil")
    assert validar_nombre_perfil("mi perfil", [p], excluir_id=p.id)[1] == []


def test_nombres_en_nfd_y_nfc_se_consideran_el_mismo_nombre():
    existente = _perfil("Café")
    _, problemas = validar_nombre_perfil(unicodedata.normalize("NFD", "CAFÉ"), [existente])
    assert [p.codigo for p in problemas] == ["V-M01.duplicado"]


def test_nombre_libre_propone_nombre_2_nombre_3():
    """CA-P03.4."""
    assert nombre_libre("Web", []) == "Web"
    assert nombre_libre("Web", [_perfil("web")]) == "Web (2)"
    assert nombre_libre("Web", [_perfil("Web"), _perfil("web (2)")]) == "Web (3)"


def test_nombre_libre_respeta_el_maximo_de_60_con_el_sufijo():
    base = "x" * 60
    propuesto = nombre_libre(base, [_perfil(base)])
    assert len(propuesto) <= 60 and propuesto.endswith(" (2)")
    assert validar_nombre_perfil(propuesto, [_perfil(base)])[1] == []


def test_descripcion_de_200_y_201_caracteres_saltos_y_token():
    assert validar_descripcion("a" * 200)[1] == []
    assert [p.codigo for p in validar_descripcion("a" * 201)[1]] == ["V-M04"]
    assert validar_descripcion("línea 1\nlínea 2")[1] == []
    assert [p.codigo for p in validar_descripcion("a\x00b")[1]] == ["V-M04"]
    assert [p.codigo for p in validar_descripcion("usa PVEAPIToken=ana@pve!t=1")[1]] == ["V-M05"]
    assert validar_descripcion("")[1] == []


# --- V-M02: identificadores -----------------------------------------------------------------------


@pytest.mark.parametrize("id_", ["a" * 32, "0123456789abcdef0123456789abcdef", "abc-123", "x"])
def test_ids_validos_de_usuario(id_):
    assert id_valido(id_) is True


@pytest.mark.parametrize(
    "id_", ["", "ABC", "a b", "a.b", "fabrica.minimo", "fabrica.", "x" * 65, "ñ", None, 5, "a/b"]
)
def test_ids_invalidos_de_usuario(id_):
    assert id_valido(id_) is False


def test_los_ids_de_fabrica_solo_se_aceptan_si_se_permite():
    """CA-P02.7."""
    assert id_valido("fabrica.minimo") is False
    assert id_valido("fabrica.minimo", permitir_fabrica=True) is True
    assert id_valido("fabrica.MINIMO", permitir_fabrica=True) is False


# --- Fábrica (RF-P02, §8) -------------------------------------------------------------------------

TABLA_FABRICA = {
    # clave: (sockets, cores, memoria_mib, disco_gib, firmware, bus, modelo_red, iothread)
    "servidor-pequeno": (1, 2, 2048, 32, Firmware.SEABIOS, Bus.SCSI, ModeloRed.VIRTIO, True),
    "servidor-mediano": (1, 4, 4096, 64, Firmware.SEABIOS, Bus.SCSI, ModeloRed.VIRTIO, True),
    "base-de-datos": (1, 4, 8192, 100, Firmware.SEABIOS, Bus.SCSI, ModeloRed.VIRTIO, True),
    "servidor-grande": (1, 8, 16384, 128, Firmware.SEABIOS, Bus.SCSI, ModeloRed.VIRTIO, True),
    "escritorio-compatible": (1, 4, 4096, 80, Firmware.OVMF, Bus.SATA, ModeloRed.E1000, False),
    "minimo": (1, 1, 512, 8, Firmware.SEABIOS, Bus.SCSI, ModeloRed.VIRTIO, True),
}


def test_las_claves_de_fabrica_son_las_seis_de_la_seccion_8_en_orden():
    assert tuple(TABLA_FABRICA) == CLAVES_FABRICA


def test_el_perfil_predeterminado_es_servidor_pequeno():
    assert ID_PREDETERMINADO == "fabrica.servidor-pequeno"
    assert PREFIJO_FABRICA == "fabrica."


@pytest.mark.parametrize("clave", list(TABLA_FABRICA))
def test_hardware_de_cada_perfil_de_fabrica_segun_la_seccion_8(clave):
    sockets, cores, mem, disco, fw, bus, red, iothread = TABLA_FABRICA[clave]
    perfil = {p.id: p for p in perfiles_fabrica()}[PREFIJO_FABRICA + clave]
    c = perfil.config
    assert perfil.origen == OrigenPerfil.FABRICA
    assert (c.sockets, c.cores, c.memoria_mib, c.firmware) == (sockets, cores, mem, fw)
    assert c.con_disco and len(c.discos) == 1 and len(c.redes) == 1
    assert (c.discos[0].tamano_gib, c.discos[0].bus, c.discos[0].iothread) == (disco, bus, iothread)
    assert c.redes[0].modelo == red
    assert c.tipo_cpu == "x86-64-v2-AES"
    assert c.controlador_scsi.value == "virtio-scsi-single"
    assert c.origen == OrigenSO.DISCO_VACIO  # solo hardware, disco vacío (CA-P02.6)
    assert c.ballooning is None


@pytest.mark.parametrize("clave", list(TABLA_FABRICA))
def test_los_perfiles_de_fabrica_no_llevan_pistas_ni_datos_del_sitio(clave):
    perfil = {p.id: p for p in perfiles_fabrica()}[PREFIJO_FABRICA + clave]
    assert perfil.config.discos[0].storage_preferido is None
    assert perfil.config.redes[0].bridge_preferido is None
    assert perfil.config.storage_efi_preferido is None


def test_ids_unicos_con_prefijo_reservado_y_validos_como_de_fabrica():
    perfiles = perfiles_fabrica()
    ids = [p.id for p in perfiles]
    assert len(set(ids)) == len(ids) == 6
    for p in perfiles:
        assert p.id.startswith("fabrica.")
        assert id_valido(p.id, permitir_fabrica=True)
        assert not id_valido(p.id)


def test_sin_textos_el_nombre_es_la_clave_y_con_textos_se_usan_los_de_la_interfaz():
    sin = {p.id: p for p in perfiles_fabrica()}
    assert sin["fabrica.minimo"].nombre == "minimo" and sin["fabrica.minimo"].descripcion == ""
    con = {
        p.id: p
        for p in perfiles_fabrica(
            {"fabrica.minimo": ("Mínimo", "d"), "servidor-grande": ("Grande", "g")}
        )
    }
    assert (con["fabrica.minimo"].nombre, con["fabrica.minimo"].descripcion) == ("Mínimo", "d")
    assert con["fabrica.servidor-grande"].nombre == "Grande"
    assert con["fabrica.servidor-mediano"].nombre == "servidor-mediano"


def test_los_perfiles_de_fabrica_son_inmutables_y_se_reconstruyen_iguales():
    """INV-M7."""
    a, b = perfiles_fabrica(), perfiles_fabrica()
    assert a == b
    with pytest.raises(dataclasses.FrozenInstanceError):
        a[0].nombre = "otro"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        a[0].config.cores = 99  # type: ignore[misc]


@pytest.mark.parametrize("clave", list(TABLA_FABRICA))
def test_cada_perfil_de_fabrica_pasa_la_capa_1(clave):
    perfil = {p.id: p for p in perfiles_fabrica()}[PREFIJO_FABRICA + clave]
    assert [p for p in validar_config_perfil(perfil.config) if p.severidad == Severidad.ERROR] == []


def _inventario_version(texto: str, mayor: int, menor: int):
    inv = inventario((nodo("pve1", 64),), es_cluster=False)
    inv.version = Version(texto, mayor, menor, 0)
    return inv


@pytest.mark.parametrize(
    ("texto", "mayor", "menor"), [("8.0.4", 8, 0), ("8.3.2", 8, 3), ("9.2.1", 9, 2)]
)
@pytest.mark.parametrize("clave", list(TABLA_FABRICA))
def test_cada_perfil_de_fabrica_pasa_validar_vm_en_8_0_8_x_y_9_x(clave, texto, mayor, menor):
    """CA-P02.3: contra el inventario de cada versión, con un storage y un bridge normales."""
    inv = _inventario_version(texto, mayor, menor)
    perfil = {p.id: p for p in perfiles_fabrica()}[PREFIJO_FABRICA + clave]
    actual = ConfiguracionVM(vmid=120, nombre="prueba", nodo="pve1")
    resultado = aplicar_perfil(perfil, actual, inv)
    assert resultado.avisos == ()
    caps = capacidades_para(inv.version, None)
    errores = [p for p in validar_vm(resultado.cfg, inv, caps) if p.severidad == Severidad.ERROR]
    assert errores == []


def test_el_perfil_predeterminado_equivale_a_configuracion_por_defecto_de_m1():
    """CA-P02.4 / RF-P12: 2 núcleos, 2 GiB, un disco de 32 GiB, virtio-scsi-single, una red virtio."""  # noqa: E501
    inv = inventario((nodo("pve1", 64),), es_cluster=False)
    por_defecto = configuracion_por_defecto(120, "web", "pve1", "datos", "vmbr0")
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    aplicada = aplicar_perfil(perfil, ConfiguracionVM(vmid=120, nombre="web", nodo="pve1"), inv).cfg
    assert aplicada == por_defecto  # igualdad completa de la configuración


def test_la_config_del_predeterminado_es_la_de_m1_sin_pistas():
    por_defecto = configuracion_por_defecto(120, "web", "pve1", "datos", "vmbr0")
    perfil = {p.id: p for p in perfiles_fabrica()}[ID_PREDETERMINADO]
    assert config_desde_configuracion(por_defecto, con_pistas=False) == perfil.config


def test_ningun_id_ni_clave_de_fabrica_nombra_un_sistema_operativo():
    """CA-P02.6: describen solo hardware."""
    texto = " ".join(p.id for p in perfiles_fabrica()).lower()
    for so in ("windows", "ubuntu", "debian", "linux", "centos", "tpm", "freebsd"):
        assert so not in texto


def test_el_perfil_de_escritorio_usa_uefi_sata_y_e1000_sin_iothread():
    c = {p.id: p for p in perfiles_fabrica()}["fabrica.escritorio-compatible"].config
    assert c.firmware == Firmware.OVMF
    assert c.discos[0].bus == Bus.SATA and c.discos[0].iothread is False
    assert c.redes[0].modelo == ModeloRed.E1000


def test_ballooning_y_redes_en_un_perfil_se_copian_a_la_configuracion_con_tipos_propios():
    config = ConfigPerfil(
        ballooning=BallooningPerfil(True, 512),
        discos=(DiscoPerfil(8),),
        redes=(RedPerfil(ModeloRed.E1000, 20, None),),
    )
    inv = inventario((nodo("pve1", 64),), es_cluster=False)
    cfg = aplicar_perfil(
        _perfil(config=config), ConfiguracionVM(vmid=120, nombre="n", nodo="pve1"), inv
    ).cfg
    assert cfg.ballooning == Ballooning(True, 512)
    assert cfg.redes == [InterfazRed("vmbr0", ModeloRed.E1000, 20)]
    assert cfg.discos == [Disco("datos", 8)]
