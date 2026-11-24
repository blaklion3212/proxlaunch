"""Regresión de los hallazgos del laboratorio (LAB-D-1, LAB-D-2, LAB-D-3 y LAB-C-1).

Cada prueba parte del escenario observado en el servidor real (Proxmox 9.2) y comprueba el
comportamiento esperado solo con la interfaz pública, sin servidor ni red. Los textos de la
interfaz se prueban aquí mismo porque no necesitan ventanas (solo ``QCoreApplication``).
"""

from __future__ import annotations

from typing import Any

import pytest

from proxlaunch.interfaz.textos import texto_problema
from proxlaunch.interfaz.textos_d import texto_error_d
from proxlaunch.nucleo.api.traductor_errores import traducir_exitstatus
from proxlaunch.nucleo.arquitectura.deteccion import detectar_nodo
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura, FuenteArquitectura
from proxlaunch.nucleo.arquitectura.validacion import avisos_arquitectura
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.hardware_cluster.errores import (
    MOTIVO_SIN_IOMMU,
    MOTIVO_SIN_Q35,
    traducir_error_hardware,
)
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.modelos import PoliticaEtiquetas
from proxlaunch.nucleo.servicios.descubrimiento import descubrir
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_api import TransporteFalso, crear_sesion, rutas_inventario
from .apoyo_fase_a import catalogo, cfg_vm, inv_con
from .apoyo_fase_b_p1 import V_90, V_91, V_92
from .apoyo_fase_d import caps_de, con_hardware, pci
from .apoyo_lote import error_http, estado_nodo_api

# --- LAB-D-3 y LAB-D-2: textos del arranque con hardware del clúster ------------------------------


def _traducir_arranque(exitstatus: str) -> tuple[ErrorProxLaunch, str]:
    """Lo que hace la app con un arranque fallido: exitstatus -> error clasificado -> texto."""
    cfg = con_hardware(cfg_vm(nodo="pve1"), pci("gpu0", pcie=True))
    final = traducir_error_hardware(traducir_exitstatus(exitstatus), cfg)
    return final, texto_error_d(final) or ""


def test_lab_d_3_q35_ausente_es_mapeo_no_disponible_con_motivo_necesita_q35():
    final, _ = _traducir_arranque("q35 machine model is not enabled")
    assert final.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert final.params["motivo"] == MOTIVO_SIN_Q35 == "necesita_q35"
    assert final.params["mapeo"] == "gpu0"


def test_lab_d_3_el_texto_de_necesita_q35_menciona_q35_y_el_mapeo():
    err = ErrorProxLaunch(
        CodigoError.MAPEO_NO_DISPONIBLE, {"mapeo": "gpu0", "nodo": "pve1", "motivo": "necesita_q35"}
    )
    texto = texto_error_d(err) or ""
    assert "q35" in texto.lower()
    assert "gpu0" in texto
    assert "{" not in texto


def test_lab_d_3_el_texto_de_un_motivo_distinto_no_habla_de_q35():
    err = ErrorProxLaunch(
        CodigoError.MAPEO_NO_DISPONIBLE, {"mapeo": "gpu0", "nodo": "pve1", "motivo": "sin_iommu"}
    )
    assert "q35" not in (texto_error_d(err) or "").lower()


_TEXTO_IOMMU = "cannot prepare PCI pass-through, IOMMU not present"


def test_lab_d_2_el_texto_de_proxmox_sin_iommu_se_traduce_a_mapeo_no_disponible():
    final, _ = _traducir_arranque(_TEXTO_IOMMU)
    assert final.codigo == CodigoError.MAPEO_NO_DISPONIBLE
    assert final.params["motivo"] == MOTIVO_SIN_IOMMU == "sin_iommu"
    assert final.detalle_tecnico  # se conserva el texto original


def test_lab_d_2_el_texto_llano_habla_de_iommu_y_del_administrador():
    _, texto = _traducir_arranque(_TEXTO_IOMMU)
    assert "IOMMU" in texto
    assert "administrador" in texto.lower()
    assert "{" not in texto


def test_lab_d_2_la_clasificacion_no_depende_de_mayusculas_ni_del_prefijo():
    final, _ = _traducir_arranque("TASK ERROR: start failed: iommu NOT present")
    assert final.params["motivo"] == "sin_iommu"


def test_lab_d_2_q35_e_iommu_no_se_confunden():
    iommu, _ = _traducir_arranque(_TEXTO_IOMMU)
    q35, _ = _traducir_arranque("q35 machine model is not enabled")
    assert iommu.params["motivo"] != q35.params["motivo"]


def test_lab_d_2_un_fallo_de_arranque_ajeno_no_se_reclasifica():
    crudo = traducir_exitstatus("fallo cualquiera sin relación con el hardware")
    cfg = con_hardware(cfg_vm(nodo="pve1"), pci("gpu0"))
    assert traducir_error_hardware(crudo, cfg).codigo != CodigoError.MAPEO_NO_DISPONIBLE


# --- LAB-D-1: arquitectura con host-arch ausente en 9.2 -------------------------------------------


def _fila(nodo: str, **extra: Any) -> dict[str, Any]:
    return {"node": nodo, "type": "node", "status": "online", **extra}


def _sin_permiso() -> ErrorProxLaunch:
    return error_http(403, "Permission check failed (/nodes/pve1, Sys.Audit)")


def _inventario(version, recursos: Any, estado: Any, nodo: str = "pve1"):
    """Descubre un nodo 9.x con ``/cluster/resources`` y ``/nodes/<n>/status`` dados."""
    t = TransporteFalso()
    rutas_inventario(t, "9.2", "nodes.json")
    if recursos is not None:
        t.en("GET", "/cluster/resources", recursos)
    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/status", estado)
    return descubrir(crear_sesion(t, version=version))


def test_lab_d_1_en_9_2_fila_sin_host_arch_y_estado_403_es_x86_sin_aviso_v_d04():
    inv = _inventario(V_92, [_fila("pve1"), _fila("pve2"), _fila("pve3")], _sin_permiso())
    info = inv.arquitecturas["pve1"]
    assert info.arquitectura == Arquitectura.X86_64
    assert info.fuente == FuenteArquitectura.RECURSOS_AUSENTE
    assert [
        a for a in avisos_arquitectura(inv, ["pve1"], caps_de(V_92)) if a.regla == "V-D04"
    ] == []


def test_lab_d_1_detectar_nodo_directo_con_403_y_fila_sin_arquitectura():
    class Cliente:
        def estado_nodo(self, nodo: str) -> dict[str, Any]:
            raise _sin_permiso()

    info = detectar_nodo(Cliente(), "pve1", recursos={"pve1": None})  # type: ignore[arg-type]
    assert (info.arquitectura, info.fuente) == (
        Arquitectura.X86_64,
        FuenteArquitectura.RECURSOS_AUSENTE,
    )
    assert info.motivo is None


def test_lab_d_1_con_host_arch_aarch64_gana_aarch64_aunque_el_estado_de_403():
    inv = _inventario(
        V_92, [_fila("pve1", **{"host-arch": "aarch64"}), _fila("pve2")], _sin_permiso()
    )
    assert inv.arquitecturas["pve1"].arquitectura == Arquitectura.AARCH64
    assert inv.arquitecturas["pve1"].fuente == FuenteArquitectura.RECURSOS
    assert inv.arquitecturas["pve2"].arquitectura == Arquitectura.X86_64


def test_lab_d_1_con_estado_legible_current_kernel_manda_cuando_falta_host_arch():
    estado = estado_nodo_api("aarch64")
    inv = _inventario(V_92, [_fila("pve1")], estado)
    info = inv.arquitecturas["pve1"]
    assert info.arquitectura == Arquitectura.AARCH64
    assert info.fuente == FuenteArquitectura.KERNEL


def test_lab_d_1_con_estado_legible_x86_la_fuente_es_el_kernel():
    inv = _inventario(V_92, [_fila("pve1")], estado_nodo_api("x86_64"))
    assert inv.arquitecturas["pve1"].arquitectura == Arquitectura.X86_64
    assert inv.arquitecturas["pve1"].fuente == FuenteArquitectura.KERNEL


def test_lab_d_1_en_9_2_sin_fila_del_nodo_y_403_sigue_desconocida_con_v_d04():
    inv = _inventario(V_92, [_fila("pve2"), _fila("pve3")], _sin_permiso())
    info = inv.arquitecturas["pve1"]
    assert info.arquitectura == Arquitectura.DESCONOCIDA
    assert info.motivo == "sin_permiso"
    (v_d04,) = [a for a in avisos_arquitectura(inv, ["pve1"], caps_de(V_92)) if a.regla == "V-D04"]
    assert v_d04.params["motivo"] == "sin_permiso"


@pytest.mark.parametrize("version", [V_90, V_91], ids=["9.0", "9.1"])
def test_lab_d_1_en_9_0_y_9_1_sigue_desconocida_con_v_d04_si_no_se_lee_el_estado(version):
    # Sin la función HOST_ARCH_EN_RESOURCES no se lee /cluster/resources: nada de RECURSOS_AUSENTE.
    inv = _inventario(version, [_fila("pve1")], _sin_permiso())
    info = inv.arquitecturas["pve1"]
    assert info.arquitectura == Arquitectura.DESCONOCIDA
    assert info.fuente == FuenteArquitectura.NINGUNA
    avisos = [a for a in avisos_arquitectura(inv, ["pve1"], caps_de(version)) if a.regla == "V-D04"]
    assert [a.params["motivo"] for a in avisos] == ["sin_permiso"]


def test_lab_d_1_sin_recursos_en_absoluto_el_403_sigue_dando_desconocida():
    class Cliente:
        def estado_nodo(self, nodo: str) -> dict[str, Any]:
            raise _sin_permiso()

    info = detectar_nodo(Cliente(), "pve1", recursos=None)  # type: ignore[arg-type]
    assert info.arquitectura == Arquitectura.DESCONOCIDA
    assert info.motivo == "sin_permiso"


def test_lab_d_1_un_host_arch_ilegible_no_se_toma_por_ausente():
    """Un valor presente pero raro (no vacío) no es «clave ausente»: no se asume x86 a ciegas."""

    class Cliente:
        def estado_nodo(self, nodo: str) -> dict[str, Any]:
            raise _sin_permiso()

    info = detectar_nodo(Cliente(), "pve1", recursos={"pve1": "riscv64"})  # type: ignore[arg-type]
    assert info.arquitectura == Arquitectura.DESCONOCIDA
    assert info.fuente == FuenteArquitectura.NINGUNA


# --- LAB-C-1: V-A03 sin Sys.Audit ----------------------------------------------------------------

_SOLO_ALLOWED_TAGS = PoliticaEtiquetas(
    "none", acceso_ausente=True
)  # /cluster/options parcial: sin user-tag-access


def _cat(privilegios: dict[str, int] | None):
    perm = None if privilegios is None else PermisosEfectivos(rutas={"/": privilegios})
    return catalogo(politica=_SOLO_ALLOWED_TAGS, perm=perm)


def _va03(cfg, cat):
    inv = inv_con(cat)
    return [p for p in validar_vm(cfg, inv, caps_de(V_92)) if p.codigo == "V-A03"]


def test_lab_c_1_sin_sys_audit_ni_sys_modify_avisa_por_cada_etiqueta_usuario():
    cfg = cfg_vm(etiquetas_usuario=("web", "db"))
    problemas = _va03(cfg, _cat({"VM.Allocate": 1}))
    usuario = [p for p in problemas if p.campo.startswith("etiquetas_usuario")]
    assert {p.params["etiqueta"] for p in usuario} == {"web", "db"}
    assert all(p.severidad == Severidad.AVISO for p in problemas)
    assert all(p.params["motivo"] == "sin_sys_audit" for p in problemas)
    assert all("incierto" not in p.params for p in problemas)


def test_lab_c_1_los_campos_de_cada_aviso_apuntan_a_su_etiqueta():
    cfg = cfg_vm(etiquetas_usuario=("web", "db"))
    problemas = _va03(cfg, _cat({"VM.Allocate": 1}))
    campos = {p.params["etiqueta"]: p.campo for p in problemas if "etiquetas_usuario" in p.campo}
    assert campos == {"web": "etiquetas_usuario[0]", "db": "etiquetas_usuario[1]"}


def test_lab_c_1_sin_sys_audit_tambien_avisa_de_las_etiquetas_fijas():
    cfg = cfg_vm(etiquetas_usuario=())
    problemas = _va03(cfg, _cat({"VM.Allocate": 1}))
    # las etiquetas finales incluyen las que añade la propia app (p. ej. la del lote)
    from proxlaunch.nucleo.opciones.etiquetas import etiquetas_finales

    assert {p.params["etiqueta"] for p in problemas} == set(etiquetas_finales(cfg))


def test_lab_c_1_el_texto_dice_que_el_lote_quiza_no_aparezca_en_lotes_en_el_servidor():
    cfg = cfg_vm(etiquetas_usuario=("web",))
    (p, *_) = _va03(cfg, _cat({"VM.Allocate": 1}))
    texto = texto_problema(p)
    assert "Lotes en el servidor" in texto
    assert "Sys.Audit" in texto
    assert "web" in texto
    assert "{" not in texto


def test_lab_c_1_con_sys_modify_verdadero_no_se_emite_el_aviso_sin_sys_audit():
    cfg = cfg_vm(etiquetas_usuario=("web",))
    problemas = _va03(cfg, _cat({"VM.Allocate": 1, "Sys.Modify": 1}))
    assert all(p.params.get("motivo") != "sin_sys_audit" for p in problemas)


def test_lab_c_1_con_sys_audit_presente_se_comporta_como_en_0_8_0():
    cfg = cfg_vm(etiquetas_usuario=("web",))
    problemas = _va03(cfg, _cat({"VM.Allocate": 1, "Sys.Audit": 1}))
    assert [(p.severidad, p.params["motivo"]) for p in problemas] == [
        (Severidad.ERROR, "ninguna_permitida")
    ]


def test_lab_c_1_con_permisos_desconocidos_sigue_siendo_aviso_incierto_de_0_8_0():
    cfg = cfg_vm(etiquetas_usuario=("web",))
    problemas = _va03(cfg, _cat(None))
    assert [(p.severidad, p.params["motivo"], p.params.get("incierto")) for p in problemas] == [
        (Severidad.AVISO, "ninguna_permitida", "1")
    ]


def test_lab_c_1_sin_etiquetas_que_avisar_no_hay_v_a03_sin_sys_audit():
    cfg = cfg_vm(etiquetas_usuario=())
    problemas = _va03(cfg, _cat({"VM.Allocate": 1}))
    assert all(p.params["etiqueta"] for p in problemas)  # solo las fijas, nunca vacías


# --- Regresión de la revisión (M1, M2, B1, B2, B3) -----------------------------------------------


def test_m1_fila_sin_status_o_fuera_de_linea_no_se_toma_por_x86():
    inv = _inventario(
        V_92,
        [
            {"node": "pve1", "type": "node"},
            _fila("pve2", status="offline"),
            _fila("pve3"),
        ],
        _sin_permiso(),
    )
    for nodo in ("pve1", "pve2"):
        assert inv.arquitecturas[nodo].arquitectura == Arquitectura.DESCONOCIDA
        assert inv.arquitecturas[nodo].fuente == FuenteArquitectura.NINGUNA
    assert inv.arquitecturas["pve3"].fuente == FuenteArquitectura.RECURSOS_AUSENTE


def test_m1_recursos_nodos_solo_deja_none_en_filas_en_linea():
    t = TransporteFalso()
    t.en(
        "GET",
        "/cluster/resources",
        [{"node": "a", "status": "online"}, {"node": "b", "status": "offline"}, {"node": "c"}],
    )
    assert crear_sesion(t, version=V_92).cliente.recursos_nodos() == {"a": None}


def test_m1_un_nodo_anterior_a_9_2_no_se_toma_por_x86():
    estado = estado_nodo_api(None, pveversion="pve-manager/9.1.4/abcd")
    info = _inventario(V_92, [_fila("pve1")], estado).arquitecturas["pve1"]
    assert info.arquitectura == Arquitectura.DESCONOCIDA


def test_m1_un_nodo_9_2_sin_kernel_sigue_siendo_x86_por_ausencia():
    estado = estado_nodo_api(None, pveversion="pve-manager/9.2.1/abcd")
    info = _inventario(V_92, [_fila("pve1")], estado).arquitecturas["pve1"]
    assert info.fuente == FuenteArquitectura.RECURSOS_AUSENTE


def test_m2_con_user_tag_access_presente_se_evalua_la_politica_real_sin_sys_audit():
    politica = PoliticaEtiquetas.desde_opciones({"user-tag-access": {"user-allow": "none"}})
    assert politica.acceso_ausente is False
    cat = catalogo(politica=politica, perm=PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}}))
    problemas = _va03(cfg_vm(etiquetas_usuario=("web",)), cat)
    assert [(p.severidad, p.params["motivo"]) for p in problemas] == [
        (Severidad.ERROR, "ninguna_permitida")
    ]


def test_m2_sin_user_tag_access_la_politica_queda_marcada_como_parcial():
    assert PoliticaEtiquetas.desde_opciones({"allowed-tags": ["a"]}).acceso_ausente is True


def test_b1_quitar_la_arquitectura_forzada_usa_los_recursos_del_inventario():
    from proxlaunch.interfaz.trabajadores import detectar_arquitectura

    t = TransporteFalso()
    rutas_inventario(t, "9.2", "nodes.json")
    t.en("GET", "/cluster/resources", [_fila("pve1"), _fila("pve2"), _fila("pve3")])
    for n in ("pve1", "pve2", "pve3"):
        t.en("GET", f"/nodes/{n}/status", _sin_permiso())
    sesion = crear_sesion(t, version=V_92)
    inv = descubrir(sesion)
    assert inv.recursos_arquitectura is not None
    _, info = detectar_arquitectura(sesion, "pve1", None, inv.recursos_arquitectura)
    assert info == inv.arquitecturas["pve1"]
    _, sin = detectar_arquitectura(sesion, "pve1", None, None)
    assert sin.arquitectura == Arquitectura.DESCONOCIDA


def test_b2_la_fuente_recursos_ausente_tiene_texto_llano():
    from proxlaunch.interfaz.textos_d import texto_arquitectura_detectada

    texto = texto_arquitectura_detectada(Arquitectura.X86_64, "recursos_ausente", False)
    assert texto.startswith("Detectada: x86") and "clúster" in texto
    assert "{" not in texto


def test_b3_necesita_q35_sin_mapeo_no_deja_comillas_vacias():
    err = ErrorProxLaunch(
        CodigoError.MAPEO_NO_DISPONIBLE, {"nodo": "pve1", "motivo": "necesita_q35"}
    )
    texto = texto_error_d(err) or ""
    assert "q35" in texto and "«»" not in texto and "{" not in texto
    assert "mapeo" not in texto
