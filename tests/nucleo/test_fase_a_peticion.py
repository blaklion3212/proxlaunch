"""Peticiones de creación con las opciones de la fase A: POST (disco vacío, ISO, importar), clon y
PUT posterior al clon.

Requisitos: RF-A1.2, RF-A1.3 (onboot/startup), RF-A2.1 (description), RF-A3.1 (tags), RF-A4.1/A4.5
(pool), RF-A5.1/A5.2 (mtu/rate), RF-A6.1 (protection), CL-A2, CL-A11, CL-A13, CL-A14.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from proxlaunch.nucleo.constructor_peticion import (
    construir_parametros,
    formato_limite,
    valor_red,
    valor_startup,
)
from proxlaunch.nucleo.modelos.origen import ModoClon
from proxlaunch.nucleo.modelos.vm import InterfazRed, ModeloRed
from proxlaunch.nucleo.opciones.etiquetas import etiquetas_finales
from proxlaunch.nucleo.origen.clon import (
    construir_ajustes_clon,
    construir_peticion_clon,
    detalle_de_config,
)

from .apoyo_fase_a import cfg_vm
from .apoyo_mvp4 import ClusterM4, cfg_base, cfg_clon, cfg_import, cfg_iso, inv_origen

INV = inv_origen()
ORIGENES = {
    "disco_vacio": lambda **k: cfg_base(**k),
    "iso": lambda **k: cfg_iso(**k),
    "importar": lambda **k: cfg_import(cfg=k),
}
NUEVAS = ("onboot", "startup", "description", "pool", "protection")


def _post(origen: str, **cambios):
    return construir_parametros(ORIGENES[origen](**cambios), INV, (9, 2))


# --- A1: «Arrancar con el servidor» y orden/espera --------------------------------------------


@pytest.mark.parametrize("origen", ORIGENES)
def test_ca_a1_2_1_casilla_marcada_envia_onboot_1(origen):
    """CA-A1.2.1: en disco vacío, ISO e importar el POST lleva ``onboot=1``."""
    assert _post(origen, arranque_auto=True)["onboot"] == "1"


@pytest.mark.parametrize("origen", ORIGENES)
def test_ca_a1_2_2_casilla_desmarcada_no_envia_onboot(origen):
    """CA-A1.2.2: sin la casilla no hay ``onboot`` (tampoco ``onboot=0``)."""
    assert "onboot" not in _post(origen)
    assert "onboot" not in _post(origen, arranque_auto=False)


@pytest.mark.parametrize(
    ("orden", "espera", "esperado"),
    [
        (2, 30, "order=2,up=30"),  # CA-A1.3.1
        (2, None, "order=2"),  # CA-A1.3.2
        (None, 30, "up=30"),  # CA-A1.3.2
        (0, 0, "order=0,up=0"),  # límite inferior: 0 es válido y no es «vacío»
    ],
)
def test_ca_a1_3_startup_compone_orden_y_espera(orden, espera, esperado):
    """CA-A1.3.1, CA-A1.3.2: ``startup=order=N,up=S`` con las partes fijadas."""
    cfg = cfg_vm(arranque_orden=orden, arranque_espera=espera)
    assert valor_startup(cfg) == esperado
    assert construir_parametros(cfg, INV, (9, 2))["startup"] == esperado


def test_ca_a1_3_4_sin_orden_ni_espera_no_se_envia_startup():
    """CA-A1.3.4: ambos campos vacíos no envían ``startup``."""
    assert valor_startup(cfg_vm()) is None
    assert "startup" not in construir_parametros(cfg_vm(), INV, (9, 2))


def test_ca_a1_3_5_startup_se_envia_aunque_arrancar_con_el_servidor_este_desmarcada():
    """CA-A1.3.5: ``startup`` y ``onboot`` son independientes."""
    p = construir_parametros(cfg_vm(arranque_orden=1, arranque_auto=False), INV, (9, 2))
    assert p["startup"] == "order=1" and "onboot" not in p


def test_ca_a1_1_1_la_creacion_nunca_lleva_start():
    """CA-A1.1.1: encender se hace con ``status/start``; ningún POST de creación lleva ``start``."""
    for origen in ORIGENES:
        assert "start" not in _post(origen, encender=True)
    cfg = cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, encender=True)
    assert "start" not in construir_peticion_clon(cfg, INV).parametros


# --- A2: description ------------------------------------------------------------------------------


@pytest.mark.parametrize("origen", ORIGENES)
def test_a2_description_se_envia_solo_si_esta_calculada(origen):
    """CA-A2.1.1/2: ``description`` sale de ``cfg.descripcion`` (calculada al planificar)."""
    assert "description" not in _post(origen)
    assert _post(origen, descripcion="hola")["description"] == "hola"


def test_ca_a2_5_5_description_se_envia_sin_deformar():
    """CA-A2.5.5: texto con ñ, tildes, emoji y ``:`` viaja tal cual (la codificación es del
    transporte).
    """
    texto = "Servidor: año ñandú 🚀\n\n- Fecha: 2026-11-21T10:30:15+00:00"
    assert _post("disco_vacio", descripcion=texto)["description"] == texto


# --- A3: tags -------------------------------------------------------------------------------------


def test_ca_a3_1_1_tags_fijas_primero_y_luego_las_del_usuario():
    """CA-A3.1.1: ``tags=proxlaunch;lote-x;web;prod``."""
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("web", "prod"))
    assert construir_parametros(cfg, INV, (9, 2))["tags"] == "proxlaunch;lote-x;web;prod"


def test_ca_a3_1_2_mv_individual_sin_lote():
    """CA-A3.1.2: sin lote, ``tags=proxlaunch;web;prod``."""
    cfg = cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("web", "prod"))
    assert construir_parametros(cfg, INV, (9, 2))["tags"] == "proxlaunch;web;prod"


def test_ca_a3_1_3_campo_vacio_tags_identico_a_0_5_1():
    """CA-A3.1.3: sin etiquetas del usuario, ``tags`` es solo la marca de propiedad."""
    cfg = cfg_vm(etiquetas=("proxlaunch", "lote-x"))
    assert construir_parametros(cfg, INV, (9, 2))["tags"] == "proxlaunch;lote-x"
    assert "tags" not in construir_parametros(cfg_vm(), INV, (9, 2))


def test_ca_a3_1_4_y_cl_a11_no_se_duplican_las_fijas_ni_las_repetidas():
    """CA-A3.1.4, CA-A3.2.4, CL-A11: ``proxlaunch`` o ``lote-x`` entre las del usuario no se
    duplica.
    """
    cfg = cfg_vm(
        etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("proxlaunch", "lote-x", "a", "a")
    )
    assert etiquetas_finales(cfg) == ("proxlaunch", "lote-x", "a")
    assert construir_parametros(cfg, INV, (9, 2))["tags"] == "proxlaunch;lote-x;a"


def test_ca_a3_3_2_sin_soporte_de_etiquetas_no_se_envia_tags():
    """CA-A3.3.2: con una versión que no admite etiquetas (< 7.3) no se envía ``tags`` (ni las
    fijas).
    """
    cfg = cfg_vm(etiquetas=("proxlaunch",), etiquetas_usuario=("web",))
    assert "tags" not in construir_parametros(cfg, INV, (7, 2))
    assert "tags" in construir_parametros(cfg, INV, (8, 0))  # P-1: 8.0 las admite


# --- A4: pool; A6: protection ---------------------------------------------------------------------


@pytest.mark.parametrize("origen", ORIGENES)
def test_ca_a4_1_3_pool_seleccionado_va_en_el_post(origen):
    """CA-A4.1.3: el POST de creación lleva ``pool=<id>``."""
    assert _post(origen, pool="produccion")["pool"] == "produccion"


@pytest.mark.parametrize("origen", ORIGENES)
def test_ca_a4_1_2_sin_pool_no_se_envia(origen):
    """CA-A4.1.2: valor por defecto («Ninguno») = sin ``pool``."""
    assert "pool" not in _post(origen)


@pytest.mark.parametrize("origen", ORIGENES)
def test_ca_a6_1_1_proteger_envia_protection_1(origen):
    """CA-A6.1.1: ``protection=1`` en la creación."""
    assert _post(origen, proteger=True)["protection"] == "1"
    assert "protection" not in _post(origen, proteger=False)  # CA-A6.1.2


def test_orden_de_las_claves_nuevas_tras_tags_arq_3_1():
    """Arq. §3.1: tras ``tags``, en este orden: onboot, startup, description, pool, protection."""
    cfg = cfg_vm(
        etiquetas=("proxlaunch",),
        arranque_auto=True,
        arranque_orden=1,
        descripcion="d",
        pool="p",
        proteger=True,
    )
    claves = list(construir_parametros(cfg, INV, (9, 2)))
    assert claves[claves.index("tags") :] == [
        "tags",
        "onboot",
        "startup",
        "description",
        "pool",
        "protection",
    ]


def test_cl_a2_cada_origen_usa_su_via_propia():
    """CL-A2: en un lote mixto el clon lleva ``description``/``pool`` en el POST de clone y
    ``protection``/``onboot``/``tags`` en el PUT posterior; el POST de disco vacío lo lleva todo."""
    kw: dict[str, Any] = dict(
        descripcion="d",
        pool="p",
        proteger=True,
        arranque_auto=True,
        etiquetas=("proxlaunch",),
        etiquetas_usuario=("web",),
    )
    clon = construir_peticion_clon(
        cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, **kw), INV
    ).parametros
    assert clon["description"] == "d" and clon["pool"] == "p"
    assert not {"protection", "onboot", "tags", "startup"} & set(clon)
    iso = _post("iso", **kw)
    assert {"description", "pool", "protection", "onboot", "tags"} <= set(iso)


# --- A5: MTU y límite -----------------------------------------------------------------------------


def test_ca_a5_1_1_mtu_heredar_no_envia_mtu():
    """CA-A5.1.1."""
    assert valor_red(InterfazRed("vmbr0")) == "virtio,bridge=vmbr0"


@pytest.mark.parametrize("mtu", [1, 576, 1500, 9000, 65520])
def test_ca_a5_1_2_y_a5_1_3_mtu_igual_y_valores_incluidos_los_limites(mtu):
    """CA-A5.1.2 (1 = igual al bridge), CA-A5.1.3 (576 y 65520 incluidos), CL-A14."""
    assert valor_red(InterfazRed("vmbr0", mtu=mtu)) == f"virtio,bridge=vmbr0,mtu={mtu}"
    assert (
        construir_parametros(cfg_vm(redes=[InterfazRed("vmbr0", mtu=mtu)]), INV, (9, 2))["net0"]
        == f"virtio,bridge=vmbr0,mtu={mtu}"
    )


@pytest.mark.parametrize(
    ("mb", "texto"),
    [(100, "100"), (100.0, "100"), (12.5, "12.5"), (0.5, "0.5"), (1, "1"), (1000, "1000")],
)
def test_ca_a5_1_5_rate_sin_ceros_sobrantes(mb, texto):
    """CA-A5.1.5 / P-17: ``rate=100`` (MB/s) y decimales admitidos (``12.5``)."""
    assert formato_limite(mb) == texto
    assert valor_red(InterfazRed("vmbr0", limite_mb=mb)).endswith(f",rate={texto}")


def test_ca_a5_1_5_limite_vacio_no_envia_rate():
    assert "rate" not in valor_red(InterfazRed("vmbr0", limite_mb=None))


def test_ca_a5_2_1_mtu_nunca_se_envia_con_un_modelo_distinto_de_virtio():
    """CA-A5.2.1 / CA-A5.2.2: con e1000 el MTU guardado no se envía."""
    r = InterfazRed("vmbr0", ModeloRed.E1000, mtu=9000)
    assert valor_red(r) == "e1000,bridge=vmbr0"


def test_ca_a5_2_3_rate_se_admite_con_cualquier_modelo():
    """CA-A5.2.3 / P-17."""
    r = InterfazRed("vmbr0", ModeloRed.E1000, limite_mb=50)
    assert valor_red(r) == "e1000,bridge=vmbr0,rate=50"


def test_a5_vlan_mtu_y_rate_en_orden_tag_mtu_rate():
    """Orden del valor de la tarjeta: bridge, tag, mtu, rate."""
    r = InterfazRed("vmbr0", ModeloRed.VIRTIO, 25, mtu=9000, limite_mb=12.5)
    assert valor_red(r) == "virtio,bridge=vmbr0,tag=25,mtu=9000,rate=12.5"


def test_ca_a5_1_9_cada_tarjeta_lleva_sus_propios_valores():
    """CA-A5.1.9: dos tarjetas con MTU y límite distintos."""
    cfg = cfg_vm(
        redes=[
            InterfazRed("vmbr0", mtu=9000, limite_mb=100),
            InterfazRed("vmbr0", ModeloRed.E1000, limite_mb=5),
            InterfazRed("vmbr0", mtu=1),
        ]
    )
    p = construir_parametros(cfg, INV, (9, 2))
    assert p["net0"] == "virtio,bridge=vmbr0,mtu=9000,rate=100"
    assert p["net1"] == "e1000,bridge=vmbr0,rate=5"
    assert p["net2"] == "virtio,bridge=vmbr0,mtu=1"


# --- Clon: POST de clone y PUT posterior ----------------------------------------------------------


def _detalle(**config):
    cl = ClusterM4(("pve1",))
    cl.agregar_plantilla(9000, "base", "pve1", **config)
    return detalle_de_config(cl.plantillas[9000]["config"])


def _clon(**kw):
    return cfg_clon("base", 9000, "pve1", efectivo=ModoClon.ENLAZADO, **kw)


def test_ca_a2_4_a4_5_1_el_post_de_clone_lleva_description_y_pool():
    """CA-A4.5.1, arq. §3.2: ``description`` y ``pool`` en el propio POST de clone."""
    p = construir_peticion_clon(
        _clon(descripcion="Plantilla\n\nnotas", pool="prod"), INV
    ).parametros
    assert p["description"] == "Plantilla\n\nnotas" and p["pool"] == "prod"
    assert {"newid", "name"} <= set(p)


def test_ca_a4_5_1_el_pool_del_clon_se_valida_como_identificador_seguro():
    """Defensa en profundidad: un pool con caracteres raros no llega al POST de clone."""
    from proxlaunch.nucleo.errores import ErrorProxLaunch

    with pytest.raises(ErrorProxLaunch):
        construir_peticion_clon(_clon(pool="a b;rm"), INV)


def test_ca_a1_2_3_a6_1_4_onboot_startup_y_protection_van_en_el_put_posterior():
    """CA-A1.2.3, CA-A1.3.1, CA-A6.1.4 (P-7): el POST de clone no admite estos parámetros."""
    cfg = _clon(arranque_auto=True, arranque_orden=2, arranque_espera=30, proteger=True)
    config = construir_ajustes_clon(cfg, _detalle(), cfg.etiquetas).config
    assert config == {"onboot": "1", "startup": "order=2,up=30", "protection": "1"}
    p = construir_peticion_clon(cfg, INV).parametros
    assert not {"onboot", "startup", "protection"} & set(p)


def test_cl_a13_plantilla_con_onboot_y_casilla_desmarcada_no_se_desactiva():
    """CL-A13 / P-21: la casilla desmarcada no envía ``onboot=0`` ni ``protection=0``."""
    cfg = _clon()
    config = construir_ajustes_clon(cfg, _detalle(onboot=1, protection=1), cfg.etiquetas).config
    assert not {"onboot", "startup", "protection"} & set(config)


def test_ca_a3_1_5_las_etiquetas_del_clon_van_en_el_put_unidas_a_las_de_la_plantilla():
    """CA-A3.1.5: ``tags`` = plantilla ∪ fijas ∪ usuario (el PUT sí comprueba la política)."""
    cfg = _clon(etiquetas=("proxlaunch", "lote-x"), etiquetas_usuario=("web",))
    config = construir_ajustes_clon(cfg, _detalle(tags="base"), etiquetas_finales(cfg)).config
    assert set(config["tags"].split(";")) == {"base", "proxlaunch", "lote-x", "web"}


def test_ca_a3_1_5_etiqueta_del_usuario_invalida_no_llega_al_put():
    """CA-A3.2.2 (defensa en profundidad): una etiqueta inválida se rechaza al construir el PUT."""
    from proxlaunch.nucleo.errores import ErrorProxLaunch

    cfg = _clon(etiquetas=("proxlaunch",), etiquetas_usuario=("Web;x",))
    with pytest.raises(ErrorProxLaunch):
        construir_ajustes_clon(cfg, _detalle(), etiquetas_finales(cfg))


def test_ca_a5_el_clon_ignora_mtu_y_limite_de_la_configuracion():
    """V-O29: un clon hereda sus redes; ningún parámetro de red sale en el POST ni en el PUT."""
    cfg = _clon(redes=[InterfazRed("vmbr0", mtu=9000, limite_mb=10)])
    assert not any(k.startswith("net") for k in construir_peticion_clon(cfg, INV).parametros)
    assert not any(
        k.startswith("net") for k in construir_ajustes_clon(cfg, _detalle(), cfg.etiquetas).config
    )


def test_pool_vacio_en_la_configuracion_no_se_envia():
    """``pool=""`` (sin pool explícito) no produce el parámetro."""
    cfg = dataclasses.replace(cfg_vm(), pool="")
    assert "pool" not in construir_parametros(cfg, INV, (9, 2))


def test_propiedad_la_peticion_refleja_exactamente_las_opciones_fijadas():
    """Propiedad (generada, semilla fija): para cualquier combinación de opciones el POST lleva
    cada clave nueva si y solo si la opción difiere del valor por defecto, con el formato del
    requisito (CA-A1.2.x, A1.3.x, A4.1.x, A5.1.x, A6.1.x)."""
    import random

    azar = random.Random(20261121)
    for _ in range(300):
        orden = azar.choice([None, 0, 1, 7])
        espera = azar.choice([None, 0, 30])
        mtu = azar.choice([None, 1, 576, 1500, 65520])
        modelo = azar.choice([ModeloRed.VIRTIO, ModeloRed.E1000])
        limite = azar.choice([None, 1, 12.5, 100])
        pool = azar.choice([None, "produccion"])
        usuario = tuple(azar.sample(["web", "prod", "db", "x1"], azar.randint(0, 3)))
        cfg = cfg_vm(
            arranque_auto=azar.random() < 0.5,
            arranque_orden=orden,
            arranque_espera=espera,
            proteger=azar.random() < 0.5,
            pool=pool,
            etiquetas=azar.choice([(), ("proxlaunch",), ("proxlaunch", "lote-ab")]),
            etiquetas_usuario=usuario,
            descripcion=azar.choice([None, "hola\n\nmundo"]),
            redes=[InterfazRed("vmbr0", modelo, azar.choice([None, 10]), mtu, limite)],
        )
        p = construir_parametros(cfg, INV, (9, 2))
        assert ("onboot" in p) is cfg.arranque_auto
        if cfg.arranque_auto:
            assert p["onboot"] == "1"
        assert ("protection" in p) is cfg.proteger
        assert p.get("pool") == pool
        assert p.get("description") == cfg.descripcion
        if orden is None and espera is None:
            assert "startup" not in p
        else:
            partes = []
            if orden is not None:
                partes.append(f"order={orden}")
            if espera is not None:
                partes.append(f"up={espera}")
            assert p["startup"] == ",".join(partes)
        esperadas = list(dict.fromkeys((*cfg.etiquetas, *usuario)))
        assert p.get("tags") == (";".join(esperadas) if esperadas else None)
        net = p["net0"]
        assert ("mtu=" in net) is (mtu is not None and modelo == ModeloRed.VIRTIO)
        assert ("rate=" in net) is (limite is not None)


# --- Defensas del constructor (la fase A no debe romper los errores de 0.5.1) ------------------


def test_defensa_sin_storage_para_el_efidisk_lanza_parametro_invalido():
    """Un OVMF sin ningún storage con ``images`` en el nodo no produce una petición a medias."""
    from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
    from proxlaunch.nucleo.modelos.vm import Firmware

    cfg = cfg_base(firmware=Firmware.OVMF, con_disco=False, nodo="pve9")
    with pytest.raises(ErrorProxLaunch) as exc:
        construir_parametros(cfg, INV, (9, 2))
    assert exc.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert exc.value.params["campo"] == "storage_efi"


def test_defensa_tpm_sin_storage_lanza_parametro_invalido():
    from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

    cfg = cfg_iso(tpm=True, con_disco=False, nodo="pve9")
    with pytest.raises(ErrorProxLaunch) as exc:
        construir_parametros(cfg, INV, (9, 2))
    assert exc.value.codigo == CodigoError.PARAMETRO_INVALIDO


def test_importar_disco_con_tpm_y_opciones_nuevas_conserva_el_orden_y_el_tpm():
    """El TPM de una importación sigue saliendo antes de las claves de la fase A."""
    from proxlaunch.nucleo.modelos.vm import Firmware

    p = _post("importar", tpm=True, firmware=Firmware.OVMF, arranque_auto=True, pool="p")
    claves = list(p)
    assert "tpmstate0" in p
    assert claves.index("tpmstate0") < claves.index("onboot") < claves.index("pool")
