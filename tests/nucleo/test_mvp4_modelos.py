"""MVP 4: modelos del origen, serialización y versionado de archivos.

Requisitos: RF-O01 (CA-O01.5), RF-O03 (CA-O03.2/O03.3), RF-O26 (CA-O26.6/O26.8),
RF-O27 (CA-O27.1/O27.5), INV-O6 (nada de URL, rutas ni checksums en archivos).
"""

import dataclasses
import json

import pytest

from proxlaunch.nucleo.archivos.esquema_config import requiere_version_2
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, FilaLote, PatronNombres
from proxlaunch.nucleo.lotes_guardados.formato import leer_lote, lote_a_bytes, version_para
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    ModoClon,
    RefPlantilla,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.perfiles_maquina.formato import leer_perfiles, perfiles_a_bytes
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    PistaOrigen,
    RedPerfil,
)

from .apoyo_mvp3 import archivo_lote, archivo_perfiles, sin_centinelas
from .apoyo_mvp4 import cfg_base, cfg_clon, cfg_import, cfg_iso


def _lote(cfg: ConfiguracionVM) -> LoteGuardado:
    d = DefinicionLote(cfg, 2, PatronNombres("web", "-", 1, 2))
    return LoteGuardado("Lote M4", d)


# --- CA-O01.5: ida y vuelta por origen ------------------------------------------------------


@pytest.mark.parametrize(
    "cfg",
    [
        pytest.param(cfg_base(), id="vacio"),
        pytest.param(cfg_iso(), id="iso-linux"),
        pytest.param(
            cfg_iso(
                "local:iso/win11.iso",
                TipoSO.WINDOWS_11,
                drivers="local:iso/virtio-win-0.1.271.iso",
                tpm=True,
                agente_qemu=True,
            ),
            id="iso-windows-con-drivers",
        ),
        pytest.param(cfg_iso(sin_drivers=True), id="iso-sin-drivers"),
        pytest.param(cfg_import(ampliar_a_gib=40, tamano_virtual_bytes=2 * 1024**3), id="import"),
        pytest.param(
            cfg_clon(
                "base",
                9000,
                "pve1",
                modo=ModoClon.COMPLETO,
                efectivo=ModoClon.COMPLETO,
                ajustes=AjustesClon(2, 4, "x86-64-v3", 4096, 64),
                storage_destino="local-lvm",
            ),
            id="clon",
        ),
    ],
)
def test_ca_o01_5_a_dict_desde_dict_hacen_ida_y_vuelta(cfg):
    assert ConfiguracionVM.desde_dict(cfg.a_dict()) == cfg


def test_ca_o01_5_el_a_dict_es_compatible_con_json_y_no_cambia_para_el_mvp3():
    assert json.dumps(cfg_iso().a_dict())  # serializable
    d = cfg_base().a_dict()
    # Una MV sin datos de SO no añade claves nuevas (a_dict idéntico al de M3).
    for clave in ("tipo_so", "tpm", "agente_qemu", "detalle_origen"):
        assert clave not in d


@pytest.mark.parametrize("valor", ["ova", "", "DISCO_VACIO", None, 1, "vmware"])
def test_ca_o01_5_origen_desconocido_da_parametro_invalido_con_el_campo(valor):
    with pytest.raises(ErrorProxLaunch) as e:
        ConfiguracionVM(vmid=100, nombre="a", nodo="pve1", origen=valor)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert e.value.params["campo"] == "origen"


def test_ca_o01_1_el_origen_por_defecto_es_disco_vacio_sin_detalle():
    cfg = ConfiguracionVM(vmid=100, nombre="a", nodo="pve1")
    assert cfg.origen == OrigenSO.DISCO_VACIO
    assert (cfg.detalle_origen, cfg.tipo_so, cfg.tpm, cfg.agente_qemu) == (None, None, False, False)


def test_los_detalles_del_origen_son_inmutables():
    for det in (DetalleIso(), DetalleImportacion(), DetalleClon(), RefVolumen(), RefPlantilla()):
        campo = dataclasses.fields(det)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(det, campo, None)


def test_valores_por_defecto_de_los_detalles():
    assert DetalleClon().modo == ModoClon.AUTOMATICO
    assert DetalleClon().modo_efectivo is None
    assert DetalleClon().ajustes == AjustesClon(None, None, None, None, None)
    assert DetalleIso().drivers is None and DetalleIso().sin_drivers is False
    assert DetalleImportacion().ampliar_a_gib is None


# --- CA-O26.8 / CA-O27.5: version_formato 2 solo con origen no vacío ----------------------------


def test_requiere_version_2_solo_con_algo_del_mvp4():
    assert requiere_version_2(cfg_base()) is False
    assert requiere_version_2(cfg_iso()) is True
    assert requiere_version_2(cfg_import()) is True
    assert requiere_version_2(cfg_clon()) is True
    # Datos de SO sueltos (aunque el origen sea disco vacío) también cuentan.
    assert requiere_version_2(cfg_base(tipo_so=TipoSO.LINUX)) is True
    assert requiere_version_2(cfg_base(tpm=True)) is True
    assert requiere_version_2(cfg_base(agente_qemu=True)) is True


def test_el_lote_sin_origen_se_escribe_como_v1_y_con_origen_como_v2():
    vacio = lote_a_bytes(_lote(cfg_base()), app_version="0.4")
    iso = lote_a_bytes(_lote(cfg_iso()), app_version="0.4")
    assert json.loads(vacio)["version_formato"] == 1
    assert json.loads(iso)["version_formato"] == 2
    assert version_para(_lote(cfg_base())) == 1 and version_para(_lote(cfg_iso())) == 2


def test_un_lote_por_filas_es_v2_si_alguna_fila_usa_origen():
    filas = (FilaLote("a-01", cfg_base()), FilaLote("a-02", cfg_clon("base", 9000, "pve1")))
    d = DefinicionLote(cfg_base(), 0, PatronNombres("x"), filas=filas)
    assert version_para(LoteGuardado("mixto", d)) == 2
    d1 = DefinicionLote(cfg_base(), 0, PatronNombres("x"), filas=filas[:1])
    assert version_para(LoteGuardado("solo vacío", d1)) == 1


def test_ca_o27_5_la_migracion_v1_a_v2_es_la_identidad_con_origen_vacio():
    """Un lote v1 se lee sin avisos y con origen `disco_vacio`; el v2 de un lote vacío es igual."""
    leido = leer_lote(archivo_lote())  # archivo de apoyo v1 (MVP 3)
    assert leido.version_original == 1 and leido.avisos == ()
    assert leido.lote.definicion.plantilla.origen == OrigenSO.DISCO_VACIO
    assert leido.lote.definicion.plantilla.detalle_origen is None
    crudo = json.loads(archivo_lote())
    crudo["version_formato"] = 2
    v2 = leer_lote(json.dumps(crudo).encode())
    assert v2.lote == leido.lote and v2.avisos == ()


def test_ida_y_vuelta_de_un_lote_con_cada_origen_sin_perder_la_fuente():
    for cfg in (cfg_iso(sin_drivers=True), cfg_import(ampliar_a_gib=40), cfg_clon("base", 9000)):
        leido = leer_lote(lote_a_bytes(_lote(cfg), app_version="0.4"))
        p = leido.lote.definicion.plantilla
        assert p.origen == cfg.origen and p.tipo_so == cfg.tipo_so
        assert type(p.detalle_origen) is type(cfg.detalle_origen)


def test_ca_o27_1_el_lote_con_origen_no_guarda_url_ruta_checksum_ni_datos_efimeros():
    """INV-O6: lista blanca de claves; `tamano_virtual_bytes` y `modo_efectivo` no se escriben."""
    cfg = cfg_import(ampliar_a_gib=40, tamano_virtual_bytes=2 * 1024**3)
    texto = lote_a_bytes(_lote(cfg), app_version="0.4").decode()
    for prohibido in ("tamano_virtual_bytes", "http", "checksum", "/home", "C:\\"):
        assert prohibido not in texto
    clon = cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO)
    texto = lote_a_bytes(_lote(clon), app_version="0.4").decode()
    assert "modo_efectivo" not in texto and "pve1" not in texto.replace("pve1x", "")
    assert sin_centinelas(texto)


@pytest.mark.parametrize(
    "volid",
    [
        "local:iso/x.iso,media=disk",
        "local:iso/x.iso,ide0=a",
        "local:iso/../x.iso",
        "/var/lib/vz/x.iso",
        "http://evil/x.iso",
        "local:iso/x y.iso",
    ],
)
def test_inv_o7_no_se_escribe_un_volid_fuera_de_la_lista_blanca(volid):
    cfg = cfg_iso(volid)
    with pytest.raises(ErrorProxLaunch) as e:
        lote_a_bytes(_lote(cfg), app_version="0.4")
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


# --- Perfiles de máquina (RF-O26) --------------------------------------------------------------


def _hw(**kw) -> ConfigPerfil:
    return ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),), **kw)


def _perfil(config: ConfigPerfil, nombre: str = "Con origen") -> PerfilMaquina:
    return PerfilMaquina("d" * 32, nombre, "", OrigenPerfil.USUARIO, config)


def test_ca_o26_8_perfil_sin_origen_es_v1_y_con_origen_o_so_es_v2():
    vacio = perfiles_a_bytes([_perfil(_hw())], con_pistas=False, app_version="0.4")
    assert json.loads(vacio)["version_formato"] == 1
    con_so = _hw(origen=OrigenSO.ISO, tipo_so=TipoSO.LINUX)
    v2 = perfiles_a_bytes([_perfil(con_so)], con_pistas=False, app_version="0.4")
    assert json.loads(v2)["version_formato"] == 2


def test_ca_o26_8_ida_y_vuelta_del_perfil_con_origen_sugerido_y_pista():
    pista = PistaOrigen(nombre_fuente="alpine.iso", storage_preferido="local")
    cfg = _hw(origen=OrigenSO.ISO, tipo_so=TipoSO.LINUX, pista_origen=pista)
    datos = perfiles_a_bytes([_perfil(cfg)], con_pistas=True, app_version="0.4")
    (leido,) = leer_perfiles(datos).validos
    assert leido.config.origen == OrigenSO.ISO and leido.config.tipo_so == TipoSO.LINUX
    assert leido.config.pista_origen == pista


def test_ca_o26_7_sin_pistas_el_perfil_exportado_no_lleva_el_nombre_de_la_fuente():
    pista = PistaOrigen(nombre_fuente="alpine.iso", storage_preferido="local")
    cfg = _hw(origen=OrigenSO.ISO, tipo_so=TipoSO.LINUX, pista_origen=pista)
    datos = perfiles_a_bytes([_perfil(cfg)], con_pistas=False, app_version="0.4")
    assert b"alpine" not in datos


def test_ca_o26_6_el_perfil_nunca_contiene_url_ruta_checksum_ni_conexion():
    pista = PistaOrigen(nombre_fuente="base", modo_clon=ModoClon.COMPLETO)
    cfg = _hw(origen=OrigenSO.CLONAR_PLANTILLA, pista_origen=pista)
    datos = perfiles_a_bytes([_perfil(cfg)], con_pistas=True, app_version="0.4").decode()
    for prohibido in ("http", "checksum", "10.0.0.1", "ana@pve", "/home"):
        assert prohibido not in datos


def test_ca_o26_7_un_perfil_importado_con_origen_iso_se_acepta_y_no_descarga_nada():
    """Ya no se rechaza por V-20 (enmienda 14.5): es solo un origen sugerido."""
    crudo = json.loads(archivo_perfiles())
    crudo["version_formato"] = 2
    crudo["perfiles"][0]["config"]["origen"] = "iso"
    crudo["perfiles"][0]["config"]["tipo_so"] = "linux"
    archivo = leer_perfiles(json.dumps(crudo).encode())
    assert not archivo.invalidos
    assert archivo.validos[0].config.origen == OrigenSO.ISO


def test_ca_o03_2_un_perfil_v1_del_mvp3_carga_sin_cambios_y_sin_avisos():
    archivo = leer_perfiles(archivo_perfiles())
    assert archivo.avisos == () and not archivo.invalidos
    assert archivo.validos[0].config.origen == OrigenSO.DISCO_VACIO
    assert archivo.validos[0].config.pista_origen is None
