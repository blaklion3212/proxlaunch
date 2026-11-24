"""MVP 4: capacidades de origen por versión y permisos, y storages por contenido.

Requisitos: RF-O02 (CA-O02.1..O02.9), RF-O04 (CA-O04.1..O04.5), RF-O05 (CA-O05.1..O05.7, O05.9),
RF-O06 (CA-O06.1..O06.5), RF-O24 (CA-O24.1/O24.4), INV-O10, INV-O11, RNF-O13 (puro) y la matriz de
la sección 3 de los requisitos (RNF-O09), fila a fila.
"""

import json
import os
import time

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, Funcion, capacidades_para
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.catalogo import Contenido, PermisosEfectivos
from proxlaunch.nucleo.modelos.conexion import PerfilConexion
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.capacidades_origen import (
    Disponibilidad,
    Via,
    calcular_capacidades,
    vias_de_origen,
)
from proxlaunch.nucleo.origen.storages import (
    TipoDecision,
    candidatos,
    candidatos_servidor,
    con_recordado,
    decidir_storage,
    elegir_nodo_transferencia,
    podria_admitir,
    recordado_de,
)
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.valores_defecto import storage_disco_por_defecto

from .apoyo_lote import nodo, storage
from .apoyo_mvp4 import ROL_MVP3, ROL_MVP4, inv_origen, permisos, plantilla_pve

VERSIONES = [(8, 4), (9, 0), (9, 1), (9, 2)]  # la mínima de 0.9.0 es 8.4


def _caps(v: tuple[int, int], forzada: bool = False) -> Capacidades:
    if forzada:
        return Capacidades(version=v, forzada=True)
    return capacidades_para(Version(f"{v[0]}.{v[1]}", v[0], v[1], 0), None)


def _calc(v, inv=None, nodo_=None, **kw):
    return calcular_capacidades(_caps(v), inv or inv_origen(**kw), nodo_)


def _estado(caps, via):
    return caps.estado(via).disponibilidad


# --- La matriz de la sección 3, fila a fila (RNF-O09) ---------------------------------------------


@pytest.mark.parametrize("version", VERSIONES, ids=lambda v: f"{v[0]}.{v[1]}")
def test_matriz_catalogo_de_iso_subir_y_clonar_estan_en_todas_las_versiones(version):
    cap = _calc(version, plantillas=(plantilla_pve(),))
    for via in (Via.ISO, Via.SUBIR_ISO, Via.CLONAR, Via.ORDEN_ARRANQUE, Via.AMPLIAR_DISCO):
        assert _estado(cap, via) == Disponibilidad.SI, via


@pytest.mark.parametrize("version", VERSIONES, ids=lambda v: f"{v[0]}.{v[1]}")
def test_matriz_importar_esta_en_todas_las_versiones_soportadas(version):
    """Con la mínima 8.4 (DT-D3) importar y subir o descargar imágenes no dependen de la versión."""
    cap = _calc(version)
    for via in (Via.IMPORTAR, Via.SUBIR_IMAGEN, Via.DESCARGAR_IMAGEN):
        assert cap.disponible(via), (via, version)
        assert cap.estado(via).codigo != CodigoError.IMPORTAR_VERSION_NO_SOPORTADA  # E-O01 obsoleto


@pytest.mark.parametrize("version", VERSIONES, ids=lambda v: f"{v[0]}.{v[1]}")
def test_matriz_descargar_url_con_sys_access_network_en_todas_las_versiones(version):
    """Con el rol de 14 (sin Sys.Modify) descargar por URL es posible desde 8.4."""
    cap = _calc(version)
    assert _estado(cap, Via.DESCARGAR_URL) == Disponibilidad.SI
    assert _estado(cap, Via.SUBIR_ISO) == Disponibilidad.SI  # CA-O02.4


def test_ca_o02_4_el_administrador_con_sys_modify_puede_descargar():
    admin = permisos(ROL_MVP4 + ("Sys.Modify",), quitar=("Sys.AccessNetwork",))
    assert _calc((8, 4), permisos_efectivos=admin).disponible(Via.DESCARGAR_URL)


def test_ca_o02_5_sys_access_network_en_el_nodo_o_sys_modify_en_raiz():
    solo_nodo = PermisosEfectivos(
        {
            "/": {p: 1 for p in ROL_MVP4 if p != "Sys.AccessNetwork"},
            "/nodes/pve1": {"Sys.AccessNetwork": 1},
        }
    )
    inv = inv_origen(permisos_efectivos=solo_nodo)
    assert calcular_capacidades(_caps((9, 2)), inv, "pve1").disponible(Via.DESCARGAR_URL)
    en_pve2 = calcular_capacidades(_caps((9, 2)), inv, "pve2")
    assert not en_pve2.disponible(Via.DESCARGAR_URL)
    assert en_pve2.estado(Via.DESCARGAR_URL).codigo == CodigoError.DESCARGA_URL_SIN_PERMISO
    admin = permisos(ROL_MVP4 + ("Sys.Modify",), quitar=("Sys.AccessNetwork",))
    assert _calc((9, 2), permisos_efectivos=admin).disponible(Via.DESCARGAR_URL)


VIAS_FASE_D = (Via.ARQUITECTURA, Via.MAPEOS, Via.CPU_PERSONALIZADA)


def test_ca_o02_1_mock_9_2_con_rol_ampliado_e_iso_import_todo_disponible():
    cap = _calc((9, 2), plantillas=(plantilla_pve(),))
    # El rol de 14 no incluye ``Mapping.Use``: las vías de mapeos y CPU de la fase D no son «sí».
    previas = [v for v in Via if v not in VIAS_FASE_D]
    assert all(cap.estado(v).disponibilidad == Disponibilidad.SI for v in previas), {
        v: cap.estado(v) for v in previas
    }
    assert cap.version == (9, 2) and cap.forzada is False
    assert cap.estado(Via.ARQUITECTURA).disponibilidad == Disponibilidad.SI  # host-arch (9.2)


def test_ca_o02_2_importar_disponible_en_8_4_y_las_otras_vias_no_cambian_respecto_de_9_2():
    base = _calc((9, 2))
    cap = _calc((8, 4))
    assert cap.disponible(Via.IMPORTAR)
    for via in (Via.ISO, Via.SUBIR_ISO, Via.CLONAR, Via.ORDEN_ARRANQUE):
        assert _estado(cap, via) == _estado(base, via)


def test_ca_o02_3_8_4_sin_storage_import_da_e_o02_con_el_candidato():
    sin_import = (
        storage("local", "dir", 100, contenido="images,iso"),
        storage("local-lvm", "lvmthin", 100, contenido="images"),
    )
    inv = inv_origen(extra_storages={})
    inv.storages_todos = {"pve1": sin_import, "pve2": sin_import}
    cap = calcular_capacidades(_caps((9, 2)), inv, "pve1")
    e = cap.estado(Via.IMPORTAR)
    assert (
        e.disponibilidad == Disponibilidad.NO
        and e.codigo == CodigoError.IMPORTAR_SIN_STORAGE_IMPORT
    )
    assert "local" in e.params["candidatos"].split(",")  # un dir que sí lo admitiría
    assert "local-lvm" not in e.params["candidatos"].split(",")  # lvmthin no admite «import»
    assert cap.estado(Via.SUBIR_IMAGEN).codigo == CodigoError.IMPORTAR_SIN_STORAGE_IMPORT


def test_sin_storage_iso_no_hay_catalogo_ni_subida_ni_descarga_de_iso():
    sin_iso = (storage("local-lvm", "lvmthin", 100, contenido="images"),)
    inv = inv_origen()
    inv.storages_todos = {"pve1": sin_iso, "pve2": sin_iso}
    cap = calcular_capacidades(_caps((9, 2)), inv, None)
    for via in (Via.ISO, Via.SUBIR_ISO, Via.DESCARGAR_URL):
        e = cap.estado(via)
        assert e.disponibilidad == Disponibilidad.NO and e.params["motivo"] == "sin_storage_iso"


# --- Permisos (RF-O24, CA-O02.6, INV-O10) ---------------------------------------------------------


def test_ca_o02_6_permisos_desconocidos_las_vias_se_ofrecen_con_aviso_salvo_las_opcionales():
    cap = _calc((9, 2), permisos_efectivos=None, plantillas=(plantilla_pve(),))
    for via in (Via.SUBIR_ISO, Via.DESCARGAR_URL, Via.IMPORTAR, Via.CLONAR):
        e = cap.estado(via)
        assert e.disponibilidad == Disponibilidad.CON_AVISO, via
        assert e.params["motivo"] == "permisos_desconocidos"
        assert cap.disponible(via)  # se ofrecen
    for via in (Via.ORDEN_ARRANQUE, Via.AMPLIAR_DISCO):  # INV-O10: se omiten
        e = cap.estado(via)
        assert e.disponibilidad == Disponibilidad.NO and e.params["desconocido"] == "1"


def test_ca_o24_4_el_rol_del_mvp3_solo_deshabilita_las_vias_nuevas():
    cap = _calc((9, 2), privilegios=ROL_MVP3, plantillas=(plantilla_pve(),))
    assert _estado(cap, Via.ISO) == Disponibilidad.SI
    for via, privilegio in (
        (Via.SUBIR_ISO, "Datastore.AllocateTemplate"),
        (Via.CLONAR, "VM.Clone"),
        (Via.ORDEN_ARRANQUE, "VM.Config.Disk"),
        (Via.AMPLIAR_DISCO, "VM.Config.Disk"),
    ):
        e = cap.estado(via)
        assert e.disponibilidad == Disponibilidad.NO, via
        assert e.codigo == CodigoError.PERMISO_INSUFICIENTE and e.params["privilegio"] == privilegio
    assert cap.estado(Via.DESCARGAR_URL).codigo == CodigoError.DESCARGA_URL_SIN_PERMISO
    assert cap.estado(Via.DESCARGAR_URL).params["privilegio"] == "Sys.AccessNetwork"


@pytest.mark.parametrize(
    ("quitar", "via", "codigo"),
    [
        ("Datastore.AllocateTemplate", Via.SUBIR_ISO, CodigoError.PERMISO_INSUFICIENTE),
        ("Datastore.AllocateTemplate", Via.SUBIR_IMAGEN, CodigoError.IMPORTAR_SIN_PERMISO),
        ("Sys.AccessNetwork", Via.DESCARGAR_URL, CodigoError.DESCARGA_URL_SIN_PERMISO),
        ("VM.Clone", Via.CLONAR, CodigoError.PERMISO_INSUFICIENTE),
        ("VM.Config.Disk", Via.ORDEN_ARRANQUE, CodigoError.PERMISO_INSUFICIENTE),
        ("VM.Config.Disk", Via.AMPLIAR_DISCO, CodigoError.PERMISO_INSUFICIENTE),
    ],
)
def test_ca_o24_1_sin_cada_privilegio_nuevo_se_deshabilita_su_via_con_motivo(quitar, via, codigo):
    cap = _calc(
        (9, 2), permisos_efectivos=permisos(quitar=(quitar,)), plantillas=(plantilla_pve(),)
    )
    e = cap.estado(via)
    assert e.disponibilidad == Disponibilidad.NO and e.codigo == codigo
    # y las vías que no dependen de ese privilegio siguen igual
    assert _estado(cap, Via.ISO) == Disponibilidad.SI


def test_importar_sin_lectura_en_el_storage_import_da_e_o12():
    solo_otros = PermisosEfectivos({"/": {"VM.Allocate": 1, "VM.Audit": 1}})
    cap = _calc((9, 2), permisos_efectivos=solo_otros)
    e = cap.estado(Via.IMPORTAR)
    assert e.codigo == CodigoError.IMPORTAR_SIN_PERMISO and e.disponibilidad == Disponibilidad.NO


def test_clonar_sin_plantillas_visibles_da_e_o17_y_sin_leerlas_no_se_afirma():
    assert _calc((9, 2), plantillas=()).estado(Via.CLONAR).codigo == CodigoError.SIN_PLANTILLAS
    assert _estado(_calc((9, 2), plantillas=None), Via.CLONAR) == Disponibilidad.SI


def test_clonar_con_vm_clone_solo_en_una_plantilla_basta():
    p = PermisosEfectivos(
        {"/": {x: 1 for x in ROL_MVP4 if x != "VM.Clone"}, "/vms/9001": {"VM.Clone": 0}}
    )
    cap = _calc(
        (9, 2),
        permisos_efectivos=p,
        plantillas=(plantilla_pve(9000, "a"), plantilla_pve(9001, "b")),
    )
    assert cap.disponible(Via.CLONAR)


def test_ca_o02_7_version_forzada_recalcula_y_se_etiqueta():
    inv = inv_origen()
    cap = calcular_capacidades(_caps((8, 4), forzada=True), inv, None)
    assert cap.forzada is True and cap.version == (8, 4)
    assert cap.disponible(Via.IMPORTAR) and cap.disponible(Via.DESCARGAR_URL)
    real = calcular_capacidades(_caps((9, 2)), inv, None)
    assert real.forzada is False and real.disponible(Via.IMPORTAR)
    assert real.version == (9, 2)


def test_ca_o02_9_cada_via_no_disponible_trae_codigo_o_motivo_estable_y_ayuda():
    for version in VERSIONES:
        for priv in (ROL_MVP4, ROL_MVP3, ()):
            cap = _calc(version, privilegios=priv, plantillas=())
            for via in Via:
                e = cap.estado(via)
                assert e.id_ayuda, (via, version)
                if e.disponibilidad == Disponibilidad.NO:
                    assert e.codigo is not None or e.params.get("motivo"), (via, version, priv)


def test_ca_o02_8_rnf_o13_calculo_puro_rapido_y_sin_modificar_el_inventario():
    nodos = ("pve1", "pve2", "pve3")
    inv = inv_origen(
        nodos=nodos, plantillas=tuple(plantilla_pve(9000 + i, f"p{i}") for i in range(200))
    )
    antes = repr(inv)
    t0 = time.perf_counter()
    for n in (None, "pve1", "pve2", "pve3"):
        calcular_capacidades(_caps((9, 2)), inv, n)
    assert time.perf_counter() - t0 < 2.0
    assert repr(inv) == antes


def test_vias_de_origen_son_las_imprescindibles_de_cada_origen():
    assert vias_de_origen(OrigenSO.DISCO_VACIO) == ()
    assert vias_de_origen(OrigenSO.ISO) == (Via.ISO,)
    assert vias_de_origen(OrigenSO.IMPORTAR_DISCO) == (Via.IMPORTAR,)
    assert vias_de_origen(OrigenSO.CLONAR_PLANTILLA) == (Via.CLONAR,)


def test_funcion_de_version_una_sola_tabla_sin_comparaciones_en_la_logica_de_origen():
    """CA-09.6: la versión se consulta solo por `Funcion.*` (aquí, los umbrales de 9.1)."""
    tabla = {
        Funcion.CLAVES_MS_2023: (9, 1),
        Funcion.MAPEO_DRIVER_KEEP: (9, 1),
    }
    for funcion, minimo in tabla.items():
        assert _caps((9, 2)).requisito(funcion) == minimo
        for v in VERSIONES:
            assert _caps(v).tiene(funcion) is (v >= minimo)


# --- RF-O04: detección de storages por contenido --------------------------------------------------


def _inv_storages(*storages_, nodo_="pve1"):
    inv = inv_origen(nodos=(nodo_,))
    inv.storages_todos = {nodo_: tuple(storages_)}
    inv.storages = {nodo_: tuple(s for s in storages_ if "images" in s.contenido)}
    return inv


def test_ca_o04_1_content_iso_backup_es_candidato_de_iso_y_no_de_mvs():
    inv = _inv_storages(storage("local", "dir", 10, contenido="iso,backup"))
    assert [s.id for s in candidatos(inv, Contenido.ISO, "pve1")] == ["local"]
    assert candidatos(inv, Contenido.IMAGENES, "pve1") == ()
    assert candidatos(inv, Contenido.IMPORT, "pve1") == ()


def test_ca_o04_2_nombres_enganosos_se_clasifican_por_contenido_no_por_nombre():
    inv = _inv_storages(
        storage("iso", "lvmthin", 10, contenido="images"),
        storage("discos", "dir", 10, contenido="iso"),
        storage("import", "dir", 10, contenido="backup"),
    )
    assert [s.id for s in candidatos(inv, Contenido.ISO, "pve1")] == ["discos"]
    assert [s.id for s in candidatos(inv, Contenido.IMAGENES, "pve1")] == ["iso"]
    assert candidatos(inv, Contenido.IMPORT, "pve1") == ()


def test_ca_o04_3_inactivo_o_ausente_en_el_nodo_no_es_candidato_en_ese_nodo():
    inv = inv_origen()
    inv.storages_todos["pve1"] = (storage("viejo", "dir", 10, activo=False, contenido="iso"),)
    inv.storages_todos["pve2"] = (storage("nuevo", "dir", 10, contenido="iso"),)
    assert candidatos(inv, Contenido.ISO, "pve1") == ()
    assert [s.id for s in candidatos(inv, Contenido.ISO, "pve2")] == ["nuevo"]
    assert candidatos(inv, Contenido.ISO, "pve9") == ()  # nodo desconocido, sin excepción
    assert candidatos_servidor(inv, Contenido.ISO) == ("nuevo",)


def test_ca_o04_5_content_ausente_no_es_candidato_y_no_hay_excepcion():
    inv = _inv_storages(storage("sin_contenido", "dir", 10, contenido="x"))
    inv.storages_todos["pve1"] = (
        type(inv.storages_todos["pve1"][0])("viejo", "dir", frozenset(), False, True, 1, 1),
    )
    for c in Contenido:
        assert candidatos(inv, c, "pve1") == ()


def test_candidatos_estan_ordenados_por_id_y_sin_storages_todos_solo_se_conocen_las_images():
    inv = _inv_storages(
        storage("zeta", "dir", 1, contenido="iso"), storage("alfa", "dir", 1, contenido="iso")
    )
    assert [s.id for s in candidatos(inv, Contenido.ISO, "pve1")] == ["alfa", "zeta"]
    inv.storages_todos = {}  # inventario de MVP 3
    assert candidatos(inv, Contenido.ISO, "pve1") == ()
    assert candidatos(inv, Contenido.IMAGENES, "pve1") == ()  # inv.storages no tiene images aquí


def test_ca_o04_4_storage_compartido_y_local_se_distinguen_por_nodo():
    inv = inv_origen()
    assert candidatos_servidor(inv, Contenido.ISO) == ("local", "nfs1")
    assert next(s for s in candidatos(inv, Contenido.ISO, "pve1") if s.id == "nfs1").compartido
    assert not next(s for s in candidatos(inv, Contenido.ISO, "pve1") if s.id == "local").compartido


def test_podria_admitir_segun_la_tabla_de_tipos_sin_esxi():
    for tipo in ("dir", "nfs", "cifs", "btrfs", "cephfs"):
        assert podria_admitir(tipo, Contenido.IMPORT) and podria_admitir(tipo, Contenido.ISO)
    for tipo in ("lvmthin", "zfspool", "rbd", "esxi"):
        assert not podria_admitir(tipo, Contenido.IMPORT), tipo  # CA-O16.7
    assert podria_admitir("lvmthin", Contenido.IMAGENES)


# --- RF-O05 / RF-O06: elegir y recordar el storage ------------------------------------------------


def test_ca_o05_1_un_solo_candidato_se_usa_sin_preguntar_y_no_se_guarda():
    inv = _inv_storages(storage("local", "dir", 1, contenido="iso"))
    d = decidir_storage(inv, Contenido.ISO, "pve1", None)
    assert (d.tipo, d.storage, d.recordado) == (TipoDecision.UNICO, "local", None)


def test_ca_o05_2_varios_candidatos_sin_recordado_hay_que_preguntar():
    inv = inv_origen()
    d = decidir_storage(inv, Contenido.ISO, "pve1", None)
    assert d.tipo == TipoDecision.PREGUNTAR and d.storage is None
    assert d.candidatos == ("local", "nfs1")


def test_ca_o05_3_recordado_vigente_se_usa_sin_preguntar():
    d = decidir_storage(inv_origen(), Contenido.ISO, "pve1", "nfs1")
    assert (d.tipo, d.storage) == (TipoDecision.RECORDADO, "nfs1")


def test_sin_ningun_candidato():
    inv = _inv_storages(storage("local-lvm", "lvmthin", 1, contenido="images"))
    assert decidir_storage(inv, Contenido.ISO, "pve1", None).tipo == TipoDecision.SIN_CANDIDATOS


@pytest.mark.parametrize(
    "cambio",
    ["inexistente", "inactivo", "sin_contenido", "otro_nodo"],
)
def test_ca_o06_1_inv_o11_recordado_que_ya_no_sirve_avisa_y_no_se_sustituye(cambio):
    inv = inv_origen()
    if cambio == "inactivo":
        inv.storages_todos["pve1"] = tuple(
            storage(s.id, s.tipo, 10, activo=s.id != "nfs1", contenido=",".join(s.contenido),
                    compartido=s.compartido)
            for s in inv.storages_todos["pve1"]
        )  # fmt: skip
    elif cambio == "sin_contenido":
        inv.storages_todos["pve1"] = tuple(
            storage(
                s.id, s.tipo, 10, contenido="images" if s.id == "nfs1" else ",".join(s.contenido)
            )
            for s in inv.storages_todos["pve1"]
        )
    elif cambio == "otro_nodo":
        inv.storages_todos["pve1"] = tuple(s for s in inv.storages_todos["pve1"] if s.id != "nfs1")
    recordado = "nfs1" if cambio != "inexistente" else "ya_no_existe"
    d = decidir_storage(inv, Contenido.ISO, "pve1", recordado)
    assert d.tipo == TipoDecision.RECORDADO_NO_DISPONIBLE
    assert d.storage is None  # nada elegido en su lugar (INV-O11)
    assert d.recordado == recordado
    assert "local" in d.candidatos  # se ofrecen las alternativas actuales (CA-O06.2)


def test_ca_o06_5_si_el_recordado_vuelve_a_existir_se_usa_sin_preguntar():
    inv = inv_origen()
    quitado = inv_origen()
    quitado.storages_todos["pve1"] = tuple(
        s for s in quitado.storages_todos["pve1"] if s.id != "nfs1"
    )
    assert decidir_storage(quitado, Contenido.ISO, "pve1", "nfs1").tipo == (
        TipoDecision.RECORDADO_NO_DISPONIBLE
    )
    assert decidir_storage(inv, Contenido.ISO, "pve1", "nfs1").tipo == TipoDecision.RECORDADO


def test_recordado_vacio_se_trata_como_ninguno():
    d = decidir_storage(inv_origen(), Contenido.ISO, "pve1", "")
    assert d.tipo == TipoDecision.PREGUNTAR


def test_ca_o05_7_recordado_de_y_con_recordado_son_por_contenido_y_no_mutan():
    a = PerfilConexion(id="a", nombre="A", hosts=["10.0.0.1"])
    b = PerfilConexion(id="b", nombre="B", hosts=["10.0.0.2"])
    assert (a.storage_mv, a.storage_iso, a.storage_import) == (None, None, None)  # CA-O03.3
    a2 = con_recordado(a, Contenido.ISO, "nfs1")
    a3 = con_recordado(a2, Contenido.IMPORT, "local")
    a4 = con_recordado(a3, Contenido.IMAGENES, "local-lvm")
    assert (recordado_de(a4, Contenido.ISO), recordado_de(a4, Contenido.IMPORT)) == (
        "nfs1",
        "local",
    )
    assert recordado_de(a4, Contenido.IMAGENES) == "local-lvm"
    assert a.storage_iso is None and recordado_de(b, Contenido.ISO) is None  # no se arrastra
    assert con_recordado(a4, Contenido.ISO, None).storage_iso is None  # «dejar de recordar»


def test_ca_o05_8_ca_o05_9_el_storage_recordado_viaja_en_el_perfil_sin_secretos(tmp_path):
    repo = RepositorioPerfiles(tmp_path / "perfiles.json")
    p = PerfilConexion(
        id="a", nombre="A", hosts=["10.0.0.1"], storage_mv="local-lvm", storage_iso="nfs1"
    )
    repo.guardar(p)
    relectura = RepositorioPerfiles(tmp_path / "perfiles.json").obtener("a")
    assert (relectura.storage_mv, relectura.storage_iso, relectura.storage_import) == (
        "local-lvm",
        "nfs1",
        None,
    )
    texto = (tmp_path / "perfiles.json").read_text()
    assert "nfs1" in texto and "secret" not in texto.lower()
    if os.name == "posix":  # los bits de modo POSIX no existen en Windows
        assert (tmp_path / "perfiles.json").stat().st_mode & 0o777 == 0o600
    repo.eliminar("a")
    assert "nfs1" not in (tmp_path / "perfiles.json").read_text()  # CA-O05.9


def test_ca_o03_3_un_perfiles_json_del_mvp3_carga_con_los_campos_en_none(tmp_path):
    ruta = tmp_path / "perfiles.json"
    ruta.write_text(
        json.dumps({"perfiles": [{"id": "a", "nombre": "A", "hosts": ["10.0.0.1"]}]}), "utf-8"
    )
    p = RepositorioPerfiles(ruta).obtener("a")
    assert p is not None and (p.storage_mv, p.storage_iso, p.storage_import) == (None, None, None)


def test_un_storage_recordado_con_tipo_invalido_se_ignora_sin_descartar_el_perfil(tmp_path):
    ruta = tmp_path / "perfiles.json"
    ruta.write_text(
        json.dumps(
            {
                "perfiles": [
                    {
                        "id": "a", "nombre": "A", "hosts": ["10.0.0.1"],
                        "storage_mv": 5, "storage_iso": ["x"], "storage_import": "  ",
                    }
                ]
            }
        ),
        "utf-8",
    )  # fmt: skip
    p = RepositorioPerfiles(ruta).obtener("a")
    assert p is not None and (p.storage_mv, p.storage_iso, p.storage_import) == (None, None, None)


def test_ca_o05_5_precedencia_del_storage_de_un_disco_recordado_sobre_mayor_espacio():
    sts = (
        storage("grande", "dir", 900, contenido="images"),
        storage("chico", "dir", 10, contenido="images"),
    )
    assert storage_disco_por_defecto(sts, None) == "grande"  # MVP 1: mayor espacio
    assert storage_disco_por_defecto(sts, "chico") == "chico"  # recordado vigente gana
    assert storage_disco_por_defecto(sts, "fantasma") == "grande"  # no se usa un inexistente


def test_ca_o05_5_el_recordado_inactivo_o_sin_images_no_se_propone_como_disco():
    sts = (
        storage("grande", "dir", 900, contenido="images"),
        storage("inactivo", "dir", 10, activo=False, contenido="images"),
        storage("solo_iso", "dir", 10, contenido="iso"),
    )
    assert storage_disco_por_defecto(sts, "inactivo") == "grande"
    assert storage_disco_por_defecto(sts, "solo_iso") == "grande"


def test_dt_o4_nodo_de_la_transferencia_es_el_conectado_si_el_storage_esta_activo():
    inv = inv_origen(nodos=("pve1", "pve2", "pve3"))
    assert elegir_nodo_transferencia(inv, "local", "pve2") == "pve2"
    assert elegir_nodo_transferencia(inv, "local", None) == "pve1"  # primero en línea por nombre
    inv.storages = {"pve1": (), "pve2": inv.storages["pve2"], "pve3": ()}
    inv.storages_todos["pve1"] = tuple(s for s in inv.storages_todos["pve1"] if s.id != "local")
    assert elegir_nodo_transferencia(inv, "local", "pve1") in {"pve2", "pve3"}
    assert elegir_nodo_transferencia(inv, "no_existe", "pve1") is None


def test_dt_o4_un_nodo_fuera_de_linea_nunca_se_elige():
    inv = inv_origen(nodos=("pve1", "pve2"))
    nodos = inv.topologia.nodos
    inv.topologia = type(inv.topologia)(True, "lab", (nodo("pve1", en_linea=False), nodos[1]))
    assert elegir_nodo_transferencia(inv, "local", "pve1") == "pve2"
