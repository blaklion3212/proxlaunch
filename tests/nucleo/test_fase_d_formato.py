"""D6.1, D6.4 y D3.7 (0.9.0): formato v6 de lotes guardados, compatibilidad y mapeos en lotes.

CA-D6.1.1–10, CA-D6.4.1–2, CA-D3.7.2, CA-D0.2.3, CL-D21. ``VERSION_FORMATO`` pasa a 6 (la máxima
que se lee), pero un lote solo se escribe como v6 si usa algo de D (mapeos PCI/USB, MAC
conservada o más de una imagen de importación): con la CPU ``custom-*`` o valores ARM sigue
escribiéndose con la versión mínima de siempre, de modo que 0.8.0 lo abre.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import random
from pathlib import Path
from typing import Any

import pytest

from proxlaunch.nucleo.archivos import envoltura
from proxlaunch.nucleo.archivos.constantes import VERSION_FORMATO, VERSION_FORMATO_FASE_C
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, ErrorArchivo, MotivoCampo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.modelos import HardwareCluster
from proxlaunch.nucleo.lote.modelos import FilaLote
from proxlaunch.nucleo.lotes_guardados.formato import (
    leer_archivo_lote,
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.origen import DetalleImportacion, ImagenDisco, RefVolumen
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Disco, InterfazRed, ModeloRed

from .apoyo_fase_d import cfg_arm, hw, pci, usb
from .apoyo_lote import definicion, plantilla
from .apoyo_mvp4 import cfg_import

DATOS = Path(__file__).resolve().parent.parent / "datos"
MAC = "52:54:00:ab:cd:ef"
SEMILLA = 20261123
TOKEN = "root@pam!lab=0a1b2c3d-1111-2222-3333-444455556666"
ANTIGUOS = [
    ("fase_a_p2/lote-homogeneo-051-v1.json", 1),
    ("fase_a_p2/lote-homogeneo-051-v2.json", 2),
    ("fase_a_p2/lote-por-filas-051-v2.json", 2),
    ("fase_b/p2_lote-homogeneo-060-v3.json", 3),
    ("fase_b/p2_lote-por-filas-060-v3.json", 3),
    ("fase_c/p4_lote-homogeneo-070-v1.json", 1),
    ("fase_c/p4_lote-homogeneo-070-v3.json", 3),
    ("fase_c/p4_lote-homogeneo-070-v4.json", 4),
    ("fase_c/p4_lote-por-filas-070-v4.json", 4),
]


def lote_d(cantidad: int = 2, **cfg: Any) -> LoteGuardado:
    return LoteGuardado("Lote D", definicion(cantidad, plantilla_vm=plantilla(**cfg)))


def bytes_de(lote: LoteGuardado) -> bytes:
    return lote_a_bytes(lote, app_version="0.9.0")


def cuerpo_de(lote: LoteGuardado) -> dict[str, Any]:
    return json.loads(bytes_de(lote))


def version_escrita(lote: LoteGuardado) -> int:
    return cuerpo_de(lote)["version_formato"]


def mutar(datos: bytes, fn) -> bytes:
    cuerpo = json.loads(datos)
    fn(cuerpo)
    return json.dumps(cuerpo).encode()


def cfg_json(cuerpo: dict[str, Any]) -> dict[str, Any]:
    return cuerpo["homogeneo"]["config"]


def rutas_error(datos: bytes) -> list[tuple[str, MotivoCampo]]:
    with pytest.raises(ErrorArchivo) as exc:
        leer_lote(datos)
    return [(e.ruta, e.motivo) for e in exc.value.errores]


def importar_con_imagenes(*, otras: tuple[ImagenDisco, ...], mac: str | None = None):
    cfg = cfg_import(cfg={"discos": [Disco("datos", 32), Disco("datos", 16)]})
    cfg = dataclasses.replace(
        cfg,
        detalle_origen=dataclasses.replace(cfg.detalle_origen, otras=otras),
        redes=[InterfazRed("vmbr0", mac_conservada=mac)],
    )
    return cfg


def con_cfg(lote: LoteGuardado, cfg: ConfiguracionVM) -> LoteGuardado:
    return LoteGuardado(lote.nombre, dataclasses.replace(lote.definicion, plantilla=cfg))


IMAGEN_2 = ImagenDisco(1, RefVolumen("debian.qcow2", "local:import/debian.qcow2"))


# --- Constantes y migración -----------------------------------------------------------------------


def test_la_version_maxima_que_se_lee_es_6_y_la_de_la_fase_c_sigue_siendo_5():
    assert VERSION_FORMATO == 6 and VERSION_FORMATO_FASE_C == 5


def test_la_migracion_de_5_a_6_es_identidad_y_no_lleva_aviso():
    assert 5 in envoltura.PASOS_SIN_AVISO and 6 not in envoltura.PASOS_SIN_AVISO


# --- CA-D6.1.1, CA-D6.1.2, CA-D6.4.1: archivos de 0.5.1 a 0.8.0 -----------------------------------


@pytest.mark.parametrize(("ruta", "version"), ANTIGUOS, ids=lambda x: str(x).split("/")[-1])
def test_ca_d6_1_1_los_lotes_de_0_5_1_a_0_8_0_se_leen_sin_aviso_y_con_los_campos_de_d_por_defecto(
    ruta, version
):
    archivo = leer_archivo_lote(DATOS / ruta)
    assert archivo.version_original == version
    assert archivo.avisos == ()  # sin MIGRADO ni ruido
    d = archivo.lote.definicion
    cfgs = [f.cfg for f in d.filas] if d.es_por_filas else [d.plantilla]
    for cfg in cfgs:
        assert cfg.hardware_cluster is None
        assert all(r.mac_conservada is None for r in cfg.redes)
        if isinstance(cfg.detalle_origen, DetalleImportacion):
            assert cfg.detalle_origen.otras == ()


@pytest.mark.parametrize(("ruta", "version"), ANTIGUOS, ids=lambda x: str(x).split("/")[-1])
def test_ca_d6_4_1_la_ida_y_vuelta_de_un_lote_antiguo_es_identica_y_no_sube_de_version(
    ruta, version
):
    original = json.loads((DATOS / ruta).read_text(encoding="utf-8"))
    archivo = leer_archivo_lote(DATOS / ruta)
    regrabado = json.loads(lote_a_bytes(archivo.lote, app_version=original["app_version"]))
    assert regrabado == original
    assert regrabado["version_formato"] == version  # 0.8.0 vuelve a abrirlo


@pytest.mark.parametrize(("ruta", "_v"), ANTIGUOS, ids=lambda x: str(x).split("/")[-1])
def test_ca_d6_4_1_el_regrabado_de_un_lote_antiguo_es_byte_a_byte_el_mismo_texto(ruta, _v):
    crudo = (DATOS / ruta).read_bytes()
    original = json.loads(crudo)
    regrabado = lote_a_bytes(
        leer_archivo_lote(DATOS / ruta).lote, app_version=original["app_version"]
    )
    assert json.loads(regrabado) == original


# --- CA-D6.1.3, CA-D6.1.10: lo que NO sube de versión ---------------------------------------------


@pytest.mark.parametrize(
    "cfg",
    [
        {"tipo_cpu": "custom-gamer"},
        {"tipo_cpu": "host"},
        {"firmware": "ovmf", "tipo_cpu": "host"},
        {"discos": [Disco("datos", 8)], "redes": [InterfazRed("vmbr0")]},
    ],
    ids=["custom_cpu", "cpu_arm", "valores_arm", "plano"],
)
def test_ca_d6_1_3_un_lote_sin_nada_de_d_se_escribe_con_la_version_minima(cfg):
    lote = lote_d(**cfg)
    assert version_para(lote) <= 5 and version_escrita(lote) <= 5
    assert "hardware_cluster" not in cfg_json(cuerpo_de(lote))


def test_ca_d6_1_3_la_cpu_custom_se_guarda_tal_cual_y_se_relee():
    lote = lote_d(tipo_cpu="custom-gamer")
    assert cfg_json(cuerpo_de(lote))["tipo_cpu"] == "custom-gamer"
    assert leer_lote(bytes_de(lote)).lote.definicion.plantilla.tipo_cpu == "custom-gamer"


def test_ca_d6_1_10_un_solo_disco_importado_con_mac_nueva_se_escribe_como_0_8_0():
    cfg = cfg_import(cfg={"discos": [Disco("datos", 32)]})
    lote = con_cfg(lote_d(), cfg)
    assert version_escrita(lote) <= 2  # el origen «importar» es de MVP 4 (v2): no sube a 6
    cuerpo = cfg_json(cuerpo_de(lote))
    assert "imagenes" not in cuerpo["detalle_origen"]
    assert "mac_conservada" not in json.dumps(cuerpo["redes"])


def test_ca_d6_1_10_una_entrada_pendiente_se_escribe_y_sube_la_version():
    # Decisión de la revisión F6 (QA-4): la pendiente se escribe para que al reabrir siga
    # pendiente (V-D27) y no se convierta en un disco vacío.
    cfg = importar_con_imagenes(otras=(ImagenDisco(1, None, False),))
    assert version_escrita(con_cfg(lote_d(), cfg)) == 6


# --- CA-D6.1.4: lo que sube a v6 ------------------------------------------------------------------


def test_ca_d6_1_4_mapeos_pci_o_usb_escriben_v6():
    for dispositivos in ((pci("gpu-a2"),), (usb("llave-hasp"),), (pci("a"), usb("b"))):
        lote = lote_d(hardware_cluster=hw(*dispositivos))
        assert version_escrita(lote) == 6
    assert version_escrita(lote_d(hardware_cluster=HardwareCluster())) <= 5  # vacío = sin D


def test_ca_d6_1_4_la_mac_conservada_escribe_v6():
    cfg = importar_con_imagenes(otras=(), mac=MAC)
    assert version_escrita(con_cfg(lote_d(), cfg)) == 6


def test_ca_d6_1_4_dos_o_mas_imagenes_de_importacion_escriben_v6_y_se_releen_igual():
    cfg = importar_con_imagenes(otras=(IMAGEN_2,))
    lote = con_cfg(lote_d(), cfg)
    assert version_escrita(lote) == 6
    leido = leer_lote(bytes_de(lote)).lote.definicion.plantilla
    assert leido.detalle_origen.otras[0].imagen.volid == "local:import/debian.qcow2"
    assert leido.detalle_origen.otras[0].indice == 1


def test_ca_d6_1_4_un_lote_por_filas_con_hardware_en_una_sola_fila_escribe_v6():
    from .apoyo_mvp3 import definicion_filas

    filas = [
        FilaLote("a-01", cfg_arm()),
        FilaLote("a-02", dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("g")))),
    ]
    lote = LoteGuardado("Por filas", definicion_filas(filas))
    assert version_escrita(lote) == 6
    assert leer_lote(bytes_de(lote)).lote.definicion.filas[1].cfg.hardware_cluster == hw(pci("g"))


def test_ca_d6_1_4_la_version_6_no_cambia_nada_mas_del_archivo():
    sin = cuerpo_de(lote_d())
    con = cuerpo_de(lote_d(hardware_cluster=hw(pci("g"))))
    assert con["version_formato"] == 6
    quitar = lambda c: {k: v for k, v in c.items() if k != "version_formato"}  # noqa: E731
    con_sin_hw = copy.deepcopy(quitar(con))
    del con_sin_hw["homogeneo"]["config"]["hardware_cluster"]
    assert con_sin_hw == quitar(sin)


# --- CA-D6.1.5: versión futura --------------------------------------------------------------------


def test_ca_d6_1_5_un_archivo_v7_se_rechaza_como_version_futura_y_no_cambia():
    datos = mutar(
        bytes_de(lote_d(hardware_cluster=hw(pci("g")))), lambda c: c.update(version_formato=7)
    )
    copia = bytes(datos)
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_lote(datos)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert exc.value.params["version_archivo"] == "7"
    assert exc.value.params["version_soportada"] == "6"
    assert datos == copia


def test_ca_d6_4_2_un_archivo_v6_con_el_lector_de_0_8_0_se_rechaza_como_version_futura():
    """Doble del lector anterior: ``abrir_envoltura`` con la versión máxima de 0.8.0 (5)."""
    datos = json.loads(bytes_de(lote_d(hardware_cluster=hw(pci("g")))))
    assert datos["version_formato"] == 6
    with pytest.raises(ErrorProxLaunch) as exc:
        envoltura.abrir_envoltura(datos, "proxlaunch.lote", version_soportada=5)
    assert exc.value.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert exc.value.params == {"version_archivo": "6", "version_soportada": "5"}
    # Y un lote sin nada de D (v ≤ 5) sí lo abre el lector anterior.
    plano = json.loads(bytes_de(lote_d(tipo_cpu="custom-gamer")))
    envoltura.abrir_envoltura(plano, "proxlaunch.lote", version_soportada=5)


# --- CA-D6.1.6: tipos y rangos --------------------------------------------------------------------


def _con_hw(**cambios: Any) -> bytes:
    datos = bytes_de(lote_d(hardware_cluster=hw(pci("gpu-a2", pcie=True), usb("u", usb3=True))))
    return mutar(datos, lambda c: cfg_json(c)["hardware_cluster"].update(cambios))


def _pci0(**cambios: Any):
    def f(c):
        cfg_json(c)["hardware_cluster"]["pci"][0].update(cambios)

    return mutar(bytes_de(lote_d(hardware_cluster=hw(pci("gpu-a2", pcie=True)))), f)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("mapeo", 5), ("mapeo", ""), ("mapeo", "a b"), ("mapeo", "x" * 65), ("mapeo", None),
     ("mapeo", ["gpu"]), ("pcie", "sí"), ("pcie", 1), ("x_vga", "no"), ("rombar", None),
     ("driver_keep", "keep")],
)  # fmt: skip
def test_ca_d6_1_6_un_campo_pci_con_tipo_o_valor_erroneo_se_marca_invalido_con_su_ruta(
    campo, valor
):
    errores = rutas_error(_pci0(**{campo: valor}))
    assert any(r == f"homogeneo.config.hardware_cluster.pci[0].{campo}" for r, _ in errores), (
        errores
    )


@pytest.mark.parametrize(
    ("campo", "valor"), [("mapeo", 5), ("mapeo", "a;b"), ("usb3", "zz"), ("usb3", 1)]
)
def test_ca_d6_1_6_un_campo_usb_con_tipo_o_valor_erroneo_se_marca_invalido_con_su_ruta(
    campo, valor
):
    def f(c):
        cfg_json(c)["hardware_cluster"]["usb"][0].update({campo: valor})

    datos = mutar(bytes_de(lote_d(hardware_cluster=hw(usb("u")))), f)
    errores = rutas_error(datos)
    assert any(r == f"homogeneo.config.hardware_cluster.usb[0].{campo}" for r, _ in errores), (
        errores
    )


def test_ca_d6_1_6_mas_de_16_pci_o_mas_de_5_usb_se_rechazan_con_la_ruta_de_la_lista():
    exceso_pci = [{"mapeo": f"g{i}"} for i in range(17)]
    errores = rutas_error(_con_hw(pci=exceso_pci))
    assert any(r.endswith("hardware_cluster.pci") for r, _ in errores), errores
    exceso_usb = [{"mapeo": f"u{i}"} for i in range(6)]
    errores = rutas_error(_con_hw(usb=exceso_usb))
    assert any(r.endswith("hardware_cluster.usb") for r, _ in errores), errores
    datos = _con_hw(
        pci=[{"mapeo": f"g{i}"} for i in range(16)], usb=[{"mapeo": f"u{i}"} for i in range(5)]
    )
    leer_lote(datos)  # el límite exacto sí se acepta


@pytest.mark.parametrize("malo", ["zz", "52:54:00:AB:CD:EF:00", "53:54:00:ab:cd:ef", 5, ""])
def test_ca_d6_1_6_una_mac_conservada_invalida_se_marca_con_su_ruta(malo):
    cfg = importar_con_imagenes(otras=(), mac=MAC)
    datos = bytes_de(con_cfg(lote_d(), cfg))
    datos = mutar(datos, lambda c: cfg_json(c)["redes"][0].update(mac_conservada=malo))
    errores = rutas_error(datos)
    assert any("redes[0].mac_conservada" in r for r, _ in errores), errores


@pytest.mark.parametrize(
    "mutacion",
    [
        {"hardware_cluster": 5},
        {"hardware_cluster": []},
        {"hardware_cluster": {"pci": "gpu"}},
        {"hardware_cluster": {"pci": [5]}},
        {"hardware_cluster": {"usb": {"mapeo": "u"}}},
    ],
)
def test_ca_d6_1_6_la_forma_general_del_hardware_se_valida(mutacion):
    datos = mutar(
        bytes_de(lote_d(hardware_cluster=hw(pci("g")))), lambda c: cfg_json(c).update(mutacion)
    )
    assert rutas_error(datos)


def test_ca_d6_1_6_un_archivo_invalido_no_ejecuta_ni_resuelve_nada_solo_se_marca():
    """Un valor con aspecto de orden o ruta se rechaza como dato; nunca se usa."""
    with pytest.raises(ErrorArchivo):
        leer_lote(_pci0(mapeo="$(rm -rf /)"))
    with pytest.raises(ErrorArchivo):
        leer_lote(_pci0(mapeo="../../etc/passwd"))


# --- CA-D6.1.7: campos desconocidos ---------------------------------------------------------------


def test_ca_d6_1_7_un_campo_desconocido_en_hardware_se_ignora_con_aviso():
    datos = mutar(
        bytes_de(lote_d(hardware_cluster=hw(pci("g")))),
        lambda c: cfg_json(c)["hardware_cluster"]["pci"][0].update(
            host="0000:01:00.0", romfile="x"
        ),
    )
    archivo = leer_lote(datos)
    assert any(a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS for a in archivo.avisos)
    assert archivo.lote.definicion.plantilla.hardware_cluster == hw(pci("g"))  # no se coló nada
    assert "host" not in json.dumps(lote_a_dict(archivo.lote))


def test_ca_d6_1_7_un_campo_desconocido_en_hardware_y_en_la_raiz_tambien_avisa():
    def f(c: dict[str, Any]) -> None:
        cfg_json(c)["hardware_cluster"].update(extra=1)
        c.update(otro=2)

    datos = mutar(bytes_de(lote_d(hardware_cluster=hw(pci("g")))), f)
    archivo = leer_lote(datos)
    assert any(a.codigo == CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS for a in archivo.avisos)


# --- CA-D6.1.8: ida y vuelta ----------------------------------------------------------------------


def _todo_de_d() -> ConfiguracionVM:
    cfg = importar_con_imagenes(otras=(IMAGEN_2,), mac=MAC)
    return dataclasses.replace(
        cfg,
        tipo_cpu="custom-gamer",
        hardware_cluster=hw(
            pci("gpu-a2", pcie=True, x_vga=True, rombar=False, driver_keep=True),
            pci("gpu-b1"),
            usb("llave-hasp", usb3=True),
        ),
    )


def test_ca_d6_1_8_la_ida_y_vuelta_con_todas_las_opciones_de_d_es_identica():
    lote = con_cfg(lote_d(), _todo_de_d())
    leido = leer_lote(bytes_de(lote)).lote.definicion.plantilla
    esperado = lote.definicion.plantilla
    assert leido.hardware_cluster == esperado.hardware_cluster
    assert leido.tipo_cpu == esperado.tipo_cpu
    assert leido.redes[0].mac_conservada == MAC
    assert leido.detalle_origen.otras == esperado.detalle_origen.otras
    assert lote_a_bytes(leer_lote(bytes_de(lote)).lote, app_version="0.9.0") == bytes_de(lote)


def test_ca_d6_1_8_el_hardware_se_escribe_solo_con_las_claves_distintas_del_defecto():
    cuerpo = cfg_json(cuerpo_de(con_cfg(lote_d(), _todo_de_d())))["hardware_cluster"]
    assert cuerpo["pci"][0] == {
        "mapeo": "gpu-a2", "pcie": True, "x_vga": True, "rombar": False, "driver_keep": True,
    }  # fmt: skip
    assert cuerpo["pci"][1] == {"mapeo": "gpu-b1"} and cuerpo["usb"] == [
        {"mapeo": "llave-hasp", "usb3": True}
    ]


def test_ca_d6_1_8_propiedad_ida_y_vuelta_con_generacion_aleatoria():
    azar = random.Random(SEMILLA)
    for _ in range(60):
        dispositivos = [
            pci(f"g{i}", pcie=azar.random() < 0.5, x_vga=False, rombar=azar.random() < 0.5,
                driver_keep=azar.random() < 0.3)
            for i in range(azar.randint(0, 16))
        ] + [usb(f"u{i}", usb3=azar.random() < 0.5) for i in range(azar.randint(0, 5))]  # fmt: skip
        lote = lote_d(
            hardware_cluster=hw(*dispositivos), tipo_cpu=azar.choice(["host", "custom-a"])
        )
        datos = bytes_de(lote)
        releido = leer_lote(datos).lote
        assert lote_a_bytes(releido, app_version="0.9.0") == datos
        assert releido.definicion.plantilla.hardware_cluster == (
            hw(*dispositivos) if dispositivos else None
        ) or (not dispositivos)


def test_el_lote_migrado_y_el_original_planifican_igual():
    """CA-D6.1.2 / CA-D0.2.3: la planificación de un lote de 0.8.0 no trae nada de D."""
    from proxlaunch.nucleo.lote.planificador import construir_plan

    from .apoyo_lote import inventario

    lote = leer_archivo_lote(DATOS / "fase_c/p4_lote-homogeneo-070-v3.json").lote
    plan = construir_plan(
        lote.definicion, inventario(), [100, 101], [], id_lote="abcd1234", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    assert not [p for p in plan.problemas if p.regla.startswith("V-D")]
    assert all(e.cfg.hardware_cluster is None for e in plan.elementos)


# --- CA-D6.1.9: secretos --------------------------------------------------------------------------


def test_ca_d6_1_9_un_id_de_mapeo_con_aspecto_de_token_no_se_guarda():
    with pytest.raises(ErrorProxLaunch) as e:
        bytes_de(lote_d(hardware_cluster=hw(pci(TOKEN))))
    assert e.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE


def test_ca_d6_1_9_una_mac_con_aspecto_de_token_no_se_guarda():
    cfg = importar_con_imagenes(otras=(), mac=TOKEN)
    with pytest.raises(ErrorProxLaunch):
        bytes_de(con_cfg(lote_d(), cfg))


def test_ca_d6_1_9_un_lote_con_hardware_no_incluye_xml_ni_rutas_ni_credenciales():
    texto = bytes_de(con_cfg(lote_d(), _todo_de_d())).decode()
    for prohibido in ("passwd", "<domain", ".xml", "/home/", "C:\\", "graphics", "password"):
        assert prohibido not in texto


def test_ca_d6_1_9_el_tamano_virtual_de_la_imagen_nunca_se_serializa():
    cfg = importar_con_imagenes(
        otras=(dataclasses.replace(IMAGEN_2, tamano_virtual_bytes=10 * 1024**3),)
    )
    texto = bytes_de(con_cfg(lote_d(), cfg)).decode()
    assert "tamano_virtual" not in texto and str(10 * 1024**3) not in texto


# --- CA-D3.7.2 y CL-D21: mapeos en lotes guardados ------------------------------------------------


def test_ca_d3_7_2_un_lote_con_mapeos_reabierto_planifica_igual_con_el_mismo_servidor():
    from .apoyo_fase_a import def_lote, plan_de
    from .apoyo_fase_d import X86, banco_d, permisos_mapeo
    from .apoyo_lote import mapeo_api

    banco = banco_d({"pve1": X86}, nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("gpu-a2", ("pve1", "/x"), migrable=True)]
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("gpu-a2")))
    original = plan_de(banco, def_lote(2, plantilla_vm=cfg))
    reabierto = leer_lote(
        bytes_de(LoteGuardado("x", def_lote(2, plantilla_vm=cfg)))
    ).lote.definicion
    de_nuevo = plan_de(banco, reabierto)
    assert [e.cfg.hardware_cluster for e in de_nuevo.elementos] == [
        e.cfg.hardware_cluster for e in original.elementos
    ]
    assert sorted(p.regla for p in de_nuevo.problemas) == sorted(
        p.regla for p in original.problemas
    )
    assert not de_nuevo.bloqueado


def test_ca_d3_7_2_con_el_mapeo_borrado_da_v_d51_y_no_se_crea_nada():
    from .apoyo_fase_a import def_lote, plan_de
    from .apoyo_fase_d import X86, banco_d, permisos_mapeo
    from .apoyo_lote import mapeo_api

    banco = banco_d({"pve1": X86}, nodos=("pve1",), permisos_efectivos=permisos_mapeo("/mapping"))
    banco.cluster.mapeos_api["pci"] = [mapeo_api("otro", ("pve1", "/x"))]
    cfg = dataclasses.replace(cfg_arm(), hardware_cluster=hw(pci("gpu-a2")))
    reabierto = leer_lote(
        bytes_de(LoteGuardado("x", def_lote(2, plantilla_vm=cfg)))
    ).lote.definicion
    plan = plan_de(banco, reabierto)
    assert plan.bloqueado and "V-D51" in {p.regla for p in plan.problemas}
    assert banco.cluster.total("POST") == 0


def test_cl_d21_un_lote_v5_con_importar_de_un_disco_se_abre_igual_y_se_vuelve_a_escribir_igual():
    cfg = cfg_import(cfg={"discos": [Disco("datos", 32)]})
    lote = con_cfg(lote_d(), cfg)
    datos = bytes_de(lote)
    assert lote_a_bytes(leer_lote(datos).lote, app_version="0.9.0") == datos
    assert ModeloRed.VIRTIO.value in datos.decode()
