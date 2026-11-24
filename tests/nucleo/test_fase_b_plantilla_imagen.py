"""B2: crear una plantilla desde una imagen cloud (RF-B2.1..B2.11, RF-B5.4, RF-B7.1).

Requisitos: CA-B2.1.1..2, CA-B2.2.1..4, CA-B2.3.1..5, CA-B2.4.1..4, CA-B2.5.1..3, CA-B2.6.1..4,
CA-B2.7.1..5, CA-B2.8.1..3, CA-B2.9.1..4 y 6, CA-B2.10.1..6, CA-B2.11.1, CA-B5.4.1, CA-B7.1.1..2,
CL-B19, CL-B21, CL-B22. Los CA ``[MANUAL]`` (CA-B2.9.5) y los de la interfaz quedan fuera.

Se prueba por la interfaz pública del paquete ``plantilla_imagen`` con el servicio REAL de
transferencias y de creación sobre un doble del servidor (``ClusterAgente``); las imágenes son
archivos diminutos con la cabecera qcow2 mínima generados en ``tmp_path``. Sin red ni ``sleep``.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from pathlib import Path
from typing import Any

import pytest

from proxlaunch.nucleo.api.traductor_errores import traducir_http
from proxlaunch.nucleo.cloudinit.deteccion import info_cloudinit
from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit, ModoTarjeta, TarjetaCloudInit
from proxlaunch.nucleo.cloudinit.peticion import codificar_sshkeys
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido, ListadoStorage
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.origen.storages import candidatos
from proxlaunch.nucleo.plantilla_imagen import (
    AccionExistente,
    ControlB2,
    EstadoPaso,
    FijasPlantilla,
    OrigenImagen,
    PasoB2,
    disponibilidad_plantilla_imagen,
    hay_errores,
    inspeccionar_imagen,
    nombre_archivo_import,
    nombre_para_url,
    nombre_sugerido,
    parametros_extra,
    validar_solicitud,
)
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.transferencias.url import (
    AlgoritmoChecksum,
    ChecksumTransferencia,
    validar_url,
)
from proxlaunch.nucleo.validacion import Severidad, nombre_dns_valido

from .apoyo_fase_b_agente import (
    GIB,
    caps,
    cfg_plantilla,
    con_cfg,
    crear_imagen,
    crear_imagen_cruda,
    crear_mundo_b2,
    error_http,
    solicitud,
)
from .apoyo_lote import RelojSeguro, envio_incierto, storage
from .apoyo_mvp4 import ROL_MVP4, inv_origen, permisos, volumen

NOMBRE_IMG = "ubuntu-24.04.qcow2"
URL_UBUNTU = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
CLAVE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBkeyP3x ana@pc"
CENTINELA_CONTRASENA = "S3cr3t-Prueba!"


def codigos(problemas) -> list[str]:
    return [p.codigo for p in problemas]


def errores(problemas) -> list[str]:
    return [p.codigo for p in problemas if p.severidad == Severidad.ERROR]


def avisos(problemas) -> list[str]:
    return [p.codigo for p in problemas if p.severidad == Severidad.AVISO]


@pytest.fixture
def imagen(tmp_path) -> Path:
    return crear_imagen(tmp_path / NOMBRE_IMG, 2 * GIB)


def sol_local(imagen: Path, **cambios: Any):
    """Solicitud con archivo local (tamaño virtual 2 GiB leído de la cabecera) y disco final 10."""
    cambios.setdefault("tamano_virtual_bytes", 2 * GIB)
    return solicitud(imagen, **cambios)


def sol_url(url_texto: str = URL_UBUNTU, nombre: str = "noble-server-cloudimg-amd64.qcow2", **kw):
    url, motivo = validar_url(url_texto, permitir_http=True)
    assert url is not None, motivo
    return solicitud(origen=OrigenImagen.URL, url=url, nombre_archivo=nombre, **kw)


def sol_ya_importada(volid: str = "local:import/ubuntu-24.04.qcow2", **kw):
    return solicitud(
        origen=OrigenImagen.YA_IMPORTADA,
        volid_existente=volid,
        nombre_archivo=volid.partition("/")[2],
        **kw,
    )


def escrituras(m) -> list[tuple[str, str]]:
    return m.escrituras()


def total_post_qemu(m) -> int:
    return sum(1 for mt, r in escrituras(m) if mt == "POST" and r == "/nodes/pve1/qemu")


def puts(m, que: str) -> list[dict[str, str]]:
    return [d for _n, _v, q, d in m.cluster.puts if q == que]


# --- CA-B2.1: disponibilidad y versión -----------------------------------------------------------


@pytest.mark.parametrize("version", [(8, 4, 0), (9, 0, 1), (9, 2, 1)])
def test_ca_b2_1_1_con_8_4_o_superior_y_permisos_el_asistente_esta_habilitado(version):
    inv = inv_origen(nodos=("pve1",), version=Version("x", *version))
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(version), inv, "pve1")
    assert d[ControlB2.ASISTENTE].habilitado
    assert "V-B01" not in codigos(validar_solicitud(_sol_basica(), inv, caps(version)))


def _sol_basica():
    return solicitud(
        origen=OrigenImagen.YA_IMPORTADA,
        volid_existente="local:import/ubuntu-24.04.qcow2",
        nombre_archivo="ubuntu-24.04.qcow2",
    )


@pytest.mark.parametrize("version", [(8, 4, 0), (9, 2, 1)])
def test_ca_b2_1_1_con_la_minima_8_4_el_asistente_esta_habilitado_y_no_existe_v_b01(version):
    """DT-D3: la versión ya no deshabilita el asistente; V-B01 quedó sin productor."""
    inv = inv_origen(nodos=("pve1",), version=Version("x", *version))
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(version), inv, "pve1")
    assert d[ControlB2.ASISTENTE].habilitado
    assert "V-B01" not in errores(validar_solicitud(_sol_basica(), inv, caps(version)))


def _inv_sin_import():
    inv = inv_origen(nodos=("pve1",))
    inv.storages_todos = {
        n: tuple(dataclasses.replace(s, contenido=s.contenido - {"import"}) for s in sts)
        for n, sts in inv.storages_todos.items()
    }
    return inv


def test_ca_b2_1_2_sin_almacenamiento_con_import_el_asistente_no_avanza_y_se_explica():
    inv = _inv_sin_import()
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert not d[ControlB2.ASISTENTE].habilitado
    assert d[ControlB2.ASISTENTE].codigo == CodigoError.PLANTILLA_IMAGEN_SIN_IMPORT
    problemas = validar_solicitud(_sol_basica(), inv, caps())
    assert "V-B06" in errores(problemas) and hay_errores(problemas)


# --- CA-B2.2: origen de la imagen ----------------------------------------------------------------


def test_ca_b2_2_1_un_archivo_local_se_sube_con_su_nombre_y_content_import(imagen):
    m = crear_mundo_b2()
    est = m.ejecutar(sol_local(imagen))
    assert (
        est.pasos[PasoB2.IMAGEN] == EstadoPaso.HECHO
        and est.volid_imagen == f"local:import/{NOMBRE_IMG}"
    )
    (subida,) = m.cluster.subidas
    assert subida["nombre"] == NOMBRE_IMG and subida["content"] == "import"
    assert (subida["nodo"], subida["storage"]) == ("pve1", "local")
    assert subida["campos"]["checksum-algorithm"] == "sha256"
    assert m.cluster.descargas == []


def test_ca_b2_2_2_una_url_se_descarga_con_download_url_y_content_import():
    m = crear_mundo_b2()
    est = m.ejecutar(sol_url())
    assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.HECHO
    (d,) = m.cluster.descargas
    assert d["content"] == "import" and d["url"] == URL_UBUNTU
    assert d["filename"] == "noble-server-cloudimg-amd64.qcow2"
    assert m.cluster.subidas == []


def test_ca_b2_2_2_http_produce_aviso_y_las_urls_invalidas_se_rechazan_como_en_transferencias():
    http, motivo = validar_url("http://ejemplo.org/imagen.qcow2", permitir_http=True)
    assert http is not None and motivo is None
    sol = sol_url("http://ejemplo.org/imagen.qcow2", "imagen.qcow2")
    problemas = validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps())
    assert any(p.codigo == "V-B02" and p.severidad == Severidad.AVISO for p in problemas)
    for mala in (
        "ftp://x.org/a.qcow2",
        "https://",
        "javascript:alert(1)",
        "https://x.org/" + "a" * 3000,
    ):
        assert validar_url(mala, permitir_http=True)[0] is None


@pytest.mark.parametrize("extension", [".iso", ".ova", ".zip", ".tar.gz", ""])
def test_ca_b2_2_3_una_extension_no_admitida_se_rechaza_en_url_y_nombre(extension):
    assert nombre_archivo_import(f"imagen{extension}", None) == (None, "extension")
    sol = sol_url(
        f"https://x.example.org/imagen{extension or '.bin'}", f"imagen{extension or '.bin'}"
    )
    problemas = validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps())
    assert "V-B03" in errores(problemas)


def test_ca_b2_2_3_un_archivo_local_con_extension_no_admitida_se_rechaza(tmp_path):
    iso = tmp_path / "debian.iso"
    iso.write_bytes(b"\x00" * 40000)
    ins = inspeccionar_imagen(iso)
    assert ins.nombre_final is None and ins.motivo_rechazo is not None
    sol = solicitud(iso, nombre_archivo="debian.iso", tamano_virtual_bytes=None)
    problemas = validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps())
    assert hay_errores(problemas) and set(errores(problemas)) & {"V-B03", "V-B04"}


def test_ca_b2_2_3_un_ova_se_rechaza(tmp_path):
    ova = tmp_path / "maquina.ova"
    cabecera = bytearray(1024)
    cabecera[257:262] = b"ustar"
    ova.write_bytes(bytes(cabecera))
    ins = inspeccionar_imagen(ova)
    assert ins.nombre_final is None and ins.motivo_rechazo


def test_ca_b2_2_4_sin_allocate_template_no_se_sube_ni_descarga_pero_si_se_usa_una_importada():
    inv = inv_origen(
        nodos=("pve1",),
        permisos_efectivos=permisos(ROL_MVP4, quitar=("Datastore.AllocateTemplate",)),
    )
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert not d[ControlB2.ORIGEN_ARCHIVO].habilitado and not d[ControlB2.ORIGEN_URL].habilitado
    assert d[ControlB2.ORIGEN_ARCHIVO].codigo is not None
    assert d[ControlB2.ORIGEN_YA_IMPORTADA].habilitado  # CA-B5.4.1


@pytest.mark.parametrize(
    "quitar",
    [("Sys.AccessNetwork",), ("Sys.AccessNetwork", "Sys.Modify")],
)
def test_ca_b2_2_4_sin_sys_access_network_solo_se_deshabilita_la_url(quitar):
    inv = inv_origen(nodos=("pve1",), permisos_efectivos=permisos(ROL_MVP4, quitar=quitar))
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert d[ControlB2.ORIGEN_ARCHIVO].habilitado
    assert not d[ControlB2.ORIGEN_URL].habilitado


def test_ca_b2_2_4_sys_modify_mas_sys_audit_sustituyen_a_sys_access_network():
    privilegios = tuple(p for p in ROL_MVP4 if p != "Sys.AccessNetwork") + ("Sys.Modify",)
    inv = inv_origen(nodos=("pve1",), privilegios=privilegios)
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert d[ControlB2.ORIGEN_URL].habilitado


def test_permisos_desconocidos_no_deshabilitan_nada():
    inv = inv_origen(nodos=("pve1",), permisos_efectivos=None)
    d = disponibilidad_plantilla_imagen(None, caps(), inv, "pve1")
    assert all(e.habilitado for c, e in d.items() if c != ControlB2.VALORES_CLOUDINIT)


# --- CA-B2.3: renombrado .img -> .qcow2 ----------------------------------------------------------


def test_ca_b2_3_1_un_img_local_con_firma_qcow2_se_sube_como_qcow2_sin_modificar_el_contenido(
    tmp_path,
):
    img = crear_imagen(tmp_path / "noble-server-cloudimg-amd64.img", 2 * GIB)
    original = img.read_bytes()
    ins = inspeccionar_imagen(img)
    assert ins.es_qcow2 is True and ins.nombre_final == "noble-server-cloudimg-amd64.qcow2"
    m = crear_mundo_b2()
    sol = solicitud(
        img, nombre_archivo=ins.nombre_final, tamano_virtual_bytes=ins.tamano_virtual_bytes
    )
    assert not hay_errores(validar_solicitud(sol, m.inv, caps()))
    m.ejecutar(sol)
    (subida,) = m.cluster.subidas
    assert subida["nombre"] == "noble-server-cloudimg-amd64.qcow2"
    assert subida["archivo"] == original  # byte a byte
    assert (
        img.read_bytes() == original and img.exists()
    )  # el archivo local ni se renombra ni cambia


def test_ca_b2_3_2_un_img_crudo_nunca_se_sube_como_qcow2(tmp_path):
    img = crear_imagen_cruda(tmp_path / "disco.img")
    ins = inspeccionar_imagen(img)
    assert ins.es_qcow2 is False
    assert ins.nombre_final is not None and ins.nombre_final.endswith(".raw")
    # Pedir el nombre .qcow2 para un contenido crudo es un error (V-B04): no se sube nada.
    sol = solicitud(img, nombre_archivo="disco.qcow2", tamano_virtual_bytes=None)
    problemas = validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps())
    assert "V-B04" in errores(problemas)
    ok = solicitud(img, nombre_archivo=ins.nombre_final, tamano_virtual_bytes=None)
    assert "V-B04" not in codigos(validar_solicitud(ok, inv_origen(nodos=("pve1",)), caps()))


def test_ca_b2_3_2_un_qcow2_con_extension_raw_o_viceversa_se_rechaza_sin_renombrar_a_ciegas(
    tmp_path,
):
    mentiroso = crear_imagen(tmp_path / "disco.raw", 2 * GIB)  # contenido qcow2, nombre .raw
    ins = inspeccionar_imagen(mentiroso)
    assert ins.nombre_final is None and ins.motivo_rechazo == "extension_no_coincide"


def test_ca_b2_3_3_una_url_img_pide_filename_qcow2_y_conserva_la_url_original():
    url, _ = validar_url(URL_UBUNTU, permitir_http=False)
    nombre, motivo, aviso = nombre_para_url(url)
    assert (nombre, motivo) == ("noble-server-cloudimg-amd64.qcow2", None)
    assert aviso == ("se_asume_qcow2",)
    m = crear_mundo_b2()
    sol = solicitud(origen=OrigenImagen.URL, url=url, nombre_archivo=nombre)
    m.ejecutar(sol)
    (d,) = m.cluster.descargas
    assert d["filename"] == "noble-server-cloudimg-amd64.qcow2"
    assert d["url"] == URL_UBUNTU  # la URL original, sin tocar


def test_una_url_qcow2_no_avisa_de_que_se_asume_el_formato():
    url, _ = validar_url("https://x.example.org/a/b.qcow2", permitir_http=False)
    assert nombre_para_url(url) == ("b.qcow2", None, ())


@pytest.mark.parametrize(
    "bruto",
    [
        "mi imagen.img",
        "../../etc/passwd.img",
        "a/b/c.img",
        "a\\b\\c.img",
        "ñandú café.img",
        "x;rm.img",
    ],
)
def test_ca_b2_3_4_los_nombres_no_seguros_se_saneann_a_un_unico_componente_seguro(bruto):
    nombre, motivo = nombre_archivo_import(bruto, True)
    assert motivo is None and nombre is not None and nombre.endswith(".qcow2")
    assert "/" not in nombre and "\\" not in nombre and ".." not in nombre and " " not in nombre
    assert all(c.isascii() and (c.isalnum() or c in "._-") for c in nombre)


@pytest.mark.parametrize(
    "nombre", ["con espacio.qcow2", "../x.qcow2", "a/b.qcow2", "x;y.qcow2", ""]
)
def test_ca_b2_3_4_un_nombre_final_no_seguro_en_la_solicitud_es_error_v_b03(nombre):
    sol = solicitud(
        origen=OrigenImagen.YA_IMPORTADA,
        volid_existente="local:import/ubuntu-24.04.qcow2",
        nombre_archivo=nombre,
    )
    assert "V-B03" in errores(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))


def test_ca_b2_3_5_los_errores_de_extension_o_formato_del_servidor_se_traducen_en_espanol():
    from proxlaunch.interfaz.textos import texto_error

    nombre = traducir_http(400, "invalid filename or wrong extension", "")
    formato = traducir_http(500, "image format 'raw' does not match extension .qcow2", "")
    assert formato.codigo == CodigoError.IMAGEN_FORMATO_INCORRECTO
    assert "formato" in texto_error(formato) and "qcow2" in texto_error(formato)
    assert "extensión" in texto_error(nombre)


# --- CA-B2.4: suma de verificación ---------------------------------------------------------------


def sha256_de(ruta: Path) -> str:
    import hashlib

    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_ca_b2_4_1_una_suma_correcta_de_un_archivo_local_permite_subir(imagen):
    m = crear_mundo_b2()
    suma = ChecksumTransferencia(AlgoritmoChecksum.SHA256, sha256_de(imagen).upper())
    est = m.ejecutar(sol_local(imagen, suma=suma))
    assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.HECHO and len(m.cluster.subidas) == 1


def test_ca_b2_4_1_una_suma_distinta_no_emite_ninguna_escritura_y_muestra_ambas_recortadas(imagen):
    m = crear_mundo_b2()
    mala = "0" * 64
    est = m.ejecutar(sol_local(imagen, suma=ChecksumTransferencia(AlgoritmoChecksum.SHA256, mala)))
    assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.FALLIDO
    assert est.error is not None and est.error.codigo == CodigoError.SUMA_NO_COINCIDE
    assert est.error.params == {"esperada": "0" * 12, "obtenida": sha256_de(imagen)[:12]}
    assert escrituras(m) == [] and m.cluster.subidas == []  # ni siquiera un POST
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.PENDIENTE


def test_ca_b2_4_2_una_url_con_suma_la_pasa_al_servidor_con_su_algoritmo():
    m = crear_mundo_b2()
    valor = "ab" * 32
    m.ejecutar(sol_url(suma=ChecksumTransferencia(AlgoritmoChecksum.SHA256, valor)))
    (d,) = m.cluster.descargas
    assert d["checksum"] == valor and d["checksum-algorithm"] == "sha256"


def test_ca_b2_4_2_si_el_servidor_rechaza_la_suma_el_paso_falla_con_el_error_de_suma():
    from proxlaunch.interfaz.textos import texto_error

    m = crear_mundo_b2()
    m.cluster.salida_tarea["download"] = "wrong sha256 checksum"
    est = m.ejecutar(sol_url(suma=ChecksumTransferencia(AlgoritmoChecksum.SHA256, "ab" * 32)))
    assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.FALLIDO
    assert est.error is not None and est.error.codigo == CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.PENDIENTE and total_post_qemu(m) == 0
    assert texto_error(est.error)  # hay mensaje en español


@pytest.mark.parametrize(
    ("algoritmo", "valor"),
    [
        (AlgoritmoChecksum.SHA256, "xyz" * 21 + "z"),  # no hexadecimal
        (AlgoritmoChecksum.SHA256, "ab" * 31),  # corta
        (AlgoritmoChecksum.SHA256, "ab" * 33),  # larga
        (AlgoritmoChecksum.MD5, "ab" * 32),  # longitud de otro algoritmo
        (AlgoritmoChecksum.SHA512, "ab" * 32),
    ],
)
def test_ca_b2_4_3_una_suma_mal_formada_se_rechaza_antes_de_enviar(algoritmo, valor):
    sol = sol_url(suma=ChecksumTransferencia(algoritmo, valor))
    assert "V-B05" in errores(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))


def test_ca_b2_4_3_para_un_archivo_local_solo_se_admite_sha256(imagen):
    sol = sol_local(imagen, suma=ChecksumTransferencia(AlgoritmoChecksum.MD5, "ab" * 16))
    assert "V-B05" in errores(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))


def test_ca_b2_4_4_sin_suma_no_hay_aviso_ni_parametros_de_suma():
    sol = sol_url()
    assert "V-B05" not in codigos(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))
    m = crear_mundo_b2()
    m.ejecutar(sol)
    (d,) = m.cluster.descargas
    assert "checksum" not in d and "checksum-algorithm" not in d


# --- CA-B2.5: nodo y almacenamientos -------------------------------------------------------------


def test_ca_b2_5_1_las_listas_ofrecen_solo_almacenamientos_activos_con_el_contenido_pedido():
    inv = inv_origen(
        nodos=("pve1",),
        extra_storages={
            "pve1": (
                storage("solo-imagenes", "dir", contenido="images"),
                storage("apagado", "dir", contenido="images,import", activo=False),
                storage("copias", "dir", contenido="backup"),
            )
        },
    )
    imports = {s.id for s in candidatos(inv, Contenido.IMPORT, "pve1")}
    imagenes = {s.id for s in candidatos(inv, Contenido.IMAGENES, "pve1")}
    assert imports == {"local"}
    assert {"local", "local-lvm", "nfs1", "solo-imagenes"} <= imagenes
    assert "apagado" not in imports | imagenes and "copias" not in imports | imagenes
    base = solicitud(
        origen=OrigenImagen.YA_IMPORTADA,
        volid_existente="local:import/a.qcow2",
        nombre_archivo="a.qcow2",
    )
    assert "V-B06" in errores(
        validar_solicitud(dataclasses.replace(base, storage_import="solo-imagenes"), inv, caps())
    )
    assert "V-B07" in errores(
        validar_solicitud(dataclasses.replace(base, storage_destino="copias"), inv, caps())
    )
    assert "V-B07" in errores(
        validar_solicitud(dataclasses.replace(base, storage_destino="apagado"), inv, caps())
    )


def test_ca_b2_5_2_un_destino_lvm_grueso_avisa_pero_permite_continuar():
    inv = inv_origen(
        nodos=("pve1",), extra_storages={"pve1": (storage("lvm1", "lvm", contenido="images"),)}
    )
    sol = dataclasses.replace(sol_ya_importada(), storage_destino="lvm1")
    problemas = validar_solicitud(sol, inv, caps())
    assert "V-B08" in avisos(problemas) and not hay_errores(problemas)


def test_ca_b2_5_2_un_destino_thin_o_directorio_no_avisa_de_clones_completos():
    problemas = validar_solicitud(sol_ya_importada(), inv_origen(nodos=("pve1",)), caps())
    assert "V-B08" not in codigos(problemas)


def inv_con_import_existente(nombre: str = NOMBRE_IMG):
    listado = ListadoStorage(
        "pve1", "local", Contenido.IMPORT, (volumen(f"local:import/{nombre}", Contenido.IMPORT),)
    )
    return inv_origen(nodos=("pve1",), listados=(listado,))


def test_ca_b2_5_3_cl_b21_con_el_nombre_ya_presente_se_exige_elegir_usar_o_reemplazar(imagen):
    inv = inv_con_import_existente()
    sin_eleccion = validar_solicitud(sol_local(imagen), inv, caps())
    assert "V-B13" in avisos(sin_eleccion)
    for eleccion in (AccionExistente.USAR, AccionExistente.REEMPLAZAR):
        con = validar_solicitud(sol_local(imagen, accion_existente=eleccion), inv, caps())
        assert "V-B13" not in codigos(con)


def test_ca_b2_5_3_sin_eleccion_ninguna_subida_ni_descarga_se_hace(imagen):
    for sol in (sol_local(imagen), sol_url(nombre=NOMBRE_IMG)):
        m = crear_mundo_b2()
        m.cluster.archivos[("pve1", "local")][NOMBRE_IMG] = 1234
        est = m.ejecutar(sol)
        assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.FALLIDO
        assert est.error is not None and est.error.codigo == CodigoError.NOMBRE_YA_EXISTE
        assert escrituras(m) == []


def test_ca_b2_5_3_usar_la_que_ya_esta_no_sube_nada_y_sigue_con_ella(imagen):
    m = crear_mundo_b2()
    m.cluster.archivos[("pve1", "local")][NOMBRE_IMG] = 1234
    est = m.ejecutar(sol_local(imagen, accion_existente=AccionExistente.USAR))
    assert est.completo and est.es_plantilla
    assert m.cluster.subidas == [] and m.cluster.descargas == []
    assert est.volid_imagen == f"local:import/{NOMBRE_IMG}"


def test_ca_b2_5_3_reemplazarla_si_sube_y_deja_la_imagen_nueva(imagen):
    m = crear_mundo_b2()
    m.cluster.archivos[("pve1", "local")][NOMBRE_IMG] = 1234
    est = m.ejecutar(sol_local(imagen, accion_existente=AccionExistente.REEMPLAZAR))
    assert est.completo and len(m.cluster.subidas) == 1
    assert m.cluster.archivos[("pve1", "local")][NOMBRE_IMG] == imagen.stat().st_size


def test_una_imagen_ya_importada_no_escribe_en_el_almacenamiento_import():
    m = crear_mundo_b2()
    m.cluster.archivos[("pve1", "local")]["ubuntu-24.04.qcow2"] = 5 * GIB // 10
    est = m.ejecutar(sol_ya_importada())
    assert est.completo and m.cluster.subidas == [] and m.cluster.descargas == []


# --- CA-B2.6: datos de la máquina ----------------------------------------------------------------


def cuerpo_creacion(m) -> dict[str, Any]:
    return m.cluster.cuerpos_post[9100]


def test_ca_b2_6_1_y_b2_7_1_el_post_de_creacion_lleva_el_import_y_las_opciones_fijas(imagen):
    m = crear_mundo_b2()
    m.ejecutar(sol_local(imagen))
    c = cuerpo_creacion(m)
    assert c["scsi0"].startswith(f"local-lvm:0,import-from=local:import/{NOMBRE_IMG}")
    assert c["boot"] == "order=scsi0" and c["ostype"] == "l26"
    assert c["scsihw"] == "virtio-scsi-single"
    assert c["ide2"] == "local-lvm:cloudinit"
    assert c["serial0"] == "socket" and c["vga"] == "serial0" and c["agent"] == "1"
    assert "template" not in c  # se convierte al final, no al crear
    assert c["name"] == "plantilla-ubuntu-2404" and c["vmid"] == "9100"


@pytest.mark.parametrize(
    ("fijas", "ausentes"),
    [
        (FijasPlantilla(unidad_cloudinit=False), {"ide2"}),
        (FijasPlantilla(consola_serie=False), {"serial0", "vga"}),
        (FijasPlantilla(agente=False), {"agent"}),
        (FijasPlantilla(False, False, False), {"ide2", "serial0", "vga", "agent"}),
    ],
)
def test_ca_b2_7_2_cada_casilla_desmarcada_quita_su_parametro(imagen, fijas, ausentes):
    m = crear_mundo_b2()
    m.ejecutar(sol_local(imagen, fijas=fijas))
    c = cuerpo_creacion(m)
    assert not ausentes & set(c)
    assert {"ide2", "serial0", "vga", "agent"} - ausentes <= set(c)
    assert c["boot"] == "order=scsi0" and c["ostype"] == "l26"  # lo básico siempre va


def test_ca_b2_7_5_serial0_es_siempre_socket_y_nunca_un_dispositivo_real():
    extra = parametros_extra(FijasPlantilla(), "local-lvm")
    assert extra["serial0"] == "socket" and extra["vga"] == "serial0"
    assert extra == {
        "ide2": "local-lvm:cloudinit",
        "serial0": "socket",
        "vga": "serial0",
        "boot": "order=scsi0",
    }
    assert "agent" not in extra  # lo envía la creación desde cfg.agente_qemu


@pytest.mark.parametrize(
    "nombre",
    ["ubuntu-24.04.qcow2", "debian-12-genericcloud.qcow2", "noble-cloudimg.qcow2", "UBUNTU.qcow2"],
)
def test_ca_b2_7_3_los_nombres_de_ubuntu_debian_o_cloudimg_avisan_de_que_falta_el_agente(nombre):
    sol = sol_ya_importada(f"local:import/{nombre}")
    assert "V-B16" in avisos(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))


def test_ca_b2_7_3_con_otro_nombre_o_sin_la_casilla_del_agente_no_avisa():
    inv = inv_origen(nodos=("pve1",))
    assert "V-B16" not in codigos(
        validar_solicitud(sol_ya_importada("local:import/almalinux-9.qcow2"), inv, caps())
    )
    sin_agente = sol_ya_importada(fijas=FijasPlantilla(agente=False))
    assert "V-B16" not in codigos(validar_solicitud(sin_agente, inv, caps()))


def test_ca_b2_7_4_sin_vm_config_hwtype_la_consola_serie_se_deshabilita_con_motivo():
    inv = inv_origen(
        nodos=("pve1",), permisos_efectivos=permisos(ROL_MVP4, quitar=("VM.Config.HWType",))
    )
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert not d[ControlB2.CONSOLA_SERIE].habilitado
    assert d[ControlB2.CONSOLA_SERIE].params["privilegio"] == "VM.Config.HWType"
    assert d[ControlB2.AGENTE].habilitado and d[ControlB2.UNIDAD_CLOUDINIT].habilitado
    # Si aun así se deja marcada es un error; desmarcada, no.
    assert "V-B15" in errores(validar_solicitud(sol_ya_importada(), inv, caps()))
    sin_serie = sol_ya_importada(fijas=FijasPlantilla(consola_serie=False))
    assert "V-B15" not in codigos(validar_solicitud(sin_serie, inv, caps()))


@pytest.mark.parametrize(
    ("quitar", "control"),
    [
        ("VM.Config.Options", ControlB2.AGENTE),
        ("VM.Config.Disk", ControlB2.UNIDAD_CLOUDINIT),
    ],
)
def test_rf_b5_4_cada_opcion_fija_se_deshabilita_sin_su_privilegio(quitar, control):
    inv = inv_origen(nodos=("pve1",), permisos_efectivos=permisos(ROL_MVP4, quitar=(quitar,)))
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert not d[control].habilitado and d[control].params["privilegio"] == quitar
    assert "V-B15" in errores(validar_solicitud(sol_ya_importada(), inv, caps()))


def test_ca_b2_6_2_el_nombre_sugerido_se_deriva_del_archivo_y_es_un_nombre_dns_valido():
    assert nombre_sugerido("ubuntu-24.04.qcow2") == "plantilla-ubuntu-24-04"
    assert (
        nombre_sugerido("noble-server-cloudimg-amd64.img")
        == "plantilla-noble-server-cloudimg-amd64"
    )
    for bruto in (
        "Debian_12 Genérica.QCOW2",
        "a" * 200 + ".qcow2",
        "....qcow2",
        "ñ.raw",
        "x/y/z.img",
    ):
        sugerido = nombre_sugerido(bruto)
        assert nombre_dns_valido(sugerido), sugerido
        assert len(sugerido) <= 63 and sugerido.startswith("plantilla-")
        sol = sol_ya_importada()
        sol = con_cfg(sol, nombre=sugerido)
        assert "V-B09" not in codigos(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))


@pytest.mark.parametrize(
    "nombre", ["con_guion_bajo", "-empieza", "termina-", "", "a" * 64, "con espacio"]
)
def test_v_b09_un_nombre_de_maquina_invalido_es_error(nombre):
    sol = con_cfg(sol_ya_importada(), nombre=nombre)
    assert "V-B09" in errores(validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps()))


def resizes(m) -> list[dict[str, str]]:
    return puts(m, "resize")


@pytest.mark.parametrize(("final_gib", "esperado"), [(10, "10G"), (3, "3G"), (200, "200G")])
def test_ca_b2_6_3_si_el_tamano_final_supera_el_de_la_imagen_hay_resize_absoluto(
    imagen, final_gib, esperado
):
    m = crear_mundo_b2()
    sol = con_cfg(
        sol_local(imagen),
        discos=[dataclasses.replace(cfg_plantilla().discos[0], tamano_gib=final_gib)],
    )
    est = m.ejecutar(sol)
    assert est.completo and est.pasos[PasoB2.AMPLIAR] == EstadoPaso.HECHO
    assert resizes(m) == [{"disk": "scsi0", "size": esperado}]
    assert "sin_ampliar" not in est.avisos


@pytest.mark.parametrize("final_gib", [2, 1])
def test_ca_b2_6_3_y_cl_b22_si_el_tamano_final_no_supera_el_de_la_imagen_no_hay_resize_y_se_informa(
    imagen, final_gib
):
    """Imagen de 2 GiB (cabecera): final igual (CL-B22) o menor → sin ``resize`` y con aviso."""
    m = crear_mundo_b2()
    sol = con_cfg(
        sol_local(imagen),
        discos=[dataclasses.replace(cfg_plantilla().discos[0], tamano_gib=final_gib)],
    )
    problemas = validar_solicitud(sol, m.inv, caps())
    assert "V-B12" in avisos(problemas)
    est = m.ejecutar(sol)
    assert est.completo and resizes(m) == []
    assert est.pasos[PasoB2.AMPLIAR] == EstadoPaso.OMITIDO and "sin_ampliar" in est.avisos


def test_ca_b2_6_3_con_url_el_tamano_real_se_lee_de_la_config_tras_crear_y_solo_crece():
    """URL: el tamaño virtual no se conoce; la imagen deja un disco de 3 GiB y se pide 10."""
    m = crear_mundo_b2()
    m.cluster.tamano_importado_gib = 3
    est = m.ejecutar(sol_url())
    assert est.completo and resizes(m) == [{"disk": "scsi0", "size": "10G"}]


def test_ca_b2_6_3_con_url_y_tamano_igual_al_importado_no_hay_resize_y_se_informa():
    m = crear_mundo_b2()
    m.cluster.tamano_importado_gib = 10  # la imagen ya mide los 10 GiB pedidos
    est = m.ejecutar(sol_url())
    assert est.completo and resizes(m) == []
    assert "sin_ampliar" in est.avisos


def test_ca_b2_6_4_el_tamano_virtual_de_un_qcow2_local_se_lee_de_la_cabecera(tmp_path):
    for virtual in (1 * GIB, 2 * GIB + 1, 20 * GIB):
        ins = inspeccionar_imagen(crear_imagen(tmp_path / f"d{virtual}.qcow2", virtual))
        assert ins.tamano_virtual_bytes == virtual
        assert ins.tamano_bytes < 10_000  # solo se leyó la cabecera de un archivo diminuto
    url, _ = validar_url(URL_UBUNTU, permitir_http=False)
    assert solicitud(origen=OrigenImagen.URL, url=url).tamano_virtual_bytes is None


@pytest.mark.parametrize(
    "mal",
    [
        {"backing": 1},  # con archivo base
    ],
)
def test_una_imagen_qcow2_con_backing_se_rechaza(tmp_path, mal):
    from .apoyo_fase_b_agente import cabecera_qcow2

    ruta = tmp_path / "b.qcow2"
    ruta.write_bytes(cabecera_qcow2(GIB, backing=mal["backing"]))
    ins = inspeccionar_imagen(ruta)
    assert ins.nombre_final is None and ins.motivo_rechazo == "backing"


def test_un_archivo_local_inexistente_o_vacio_no_cuelga_la_inspeccion(tmp_path):
    with pytest.raises(ErrorProxLaunch):
        inspeccionar_imagen(tmp_path / "no-existe.qcow2")
    vacio = tmp_path / "vacio.qcow2"
    vacio.write_bytes(b"")
    ins = inspeccionar_imagen(vacio)
    assert ins.nombre_final is None and ins.motivo_rechazo == "vacio"


# --- CA-B2.8: valores de cloud-init de la plantilla ----------------------------------------------


def inv_con_cloudinit():
    return inv_origen(nodos=("pve1",), privilegios=(*ROL_MVP4, "VM.Config.Cloudinit"))


def cloudinit_basico(**cambios: Any) -> ConfigCloudInit:
    base: dict[str, Any] = {
        "usuario": "ubuntu",
        "claves": (CLAVE,),
        "tarjetas": (TarjetaCloudInit(0, ModoTarjeta.DHCP),),
    }
    base.update(cambios)
    return ConfigCloudInit(**base)


def test_ca_b2_8_1_con_usuario_y_clave_hay_un_put_config_previo_a_template(imagen):
    m = crear_mundo_b2(inv=inv_con_cloudinit())
    est = m.ejecutar(sol_local(imagen, cloudinit=cloudinit_basico()))
    assert est.completo and est.pasos[PasoB2.CLOUDINIT] == EstadoPaso.HECHO
    (put,) = puts(m, "config")
    assert put["ciuser"] == "ubuntu" and put["ipconfig0"] == "ip=dhcp"
    assert put["sshkeys"] == codificar_sshkeys((CLAVE,)) and CLAVE not in put["sshkeys"]
    assert "cipassword" not in put
    ordenado = escrituras(m)
    assert ordenado.index(("PUT", "/nodes/pve1/qemu/9100/config")) < ordenado.index(
        ("POST", "/nodes/pve1/qemu/9100/template")
    )


def test_ca_b2_8_1_con_la_seccion_vacia_no_se_envia_ningun_ci_ni_hay_put_config(imagen):
    for vacia in (None, ConfigCloudInit()):
        m = crear_mundo_b2(inv=inv_con_cloudinit())
        est = m.ejecutar(sol_local(imagen, cloudinit=vacia))
        assert est.completo and est.pasos[PasoB2.CLOUDINIT] == EstadoPaso.OMITIDO
        assert puts(m, "config") == []
        assert not [k for k in cuerpo_creacion(m) if k.startswith(("ci", "ipconfig", "sshkeys"))]


def test_ca_b2_8_2_el_asistente_no_ofrece_ninguna_contraseña():
    campos = {f.name for f in dataclasses.fields(solicitud())}
    assert not [c for c in campos if "contras" in c or "pass" in c]


def test_ca_b2_8_2_una_contraseña_en_la_plantilla_es_error_y_si_llegase_no_se_envia(imagen, caplog):
    inv = inv_con_cloudinit()
    ci = cloudinit_basico(contrasena=Secreto(CENTINELA_CONTRASENA))
    sol = sol_local(imagen, cloudinit=ci)
    problemas = validar_solicitud(sol, inv, caps())
    assert "V-B39" in errores(problemas)
    assert CENTINELA_CONTRASENA not in repr(problemas)
    # Defensa en profundidad: aunque se saltase la validación, el PUT no lleva cipassword.
    m = crear_mundo_b2(inv=inv)
    with caplog.at_level(logging.DEBUG):
        m.ejecutar(sol)
    vuelco = repr([(c.metodo, c.ruta, c.datos, c.params) for c in m.cluster.llamadas])
    assert CENTINELA_CONTRASENA not in vuelco and CENTINELA_CONTRASENA not in caplog.text
    assert "cipassword" not in vuelco


@pytest.mark.parametrize(
    "ci",
    [
        cloudinit_basico(
            tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, ip="10.0.0.5/24", puerta="10.0.0.1"),)
        ),
        cloudinit_basico(tarjetas=(TarjetaCloudInit(1, ModoTarjeta.DHCP),)),
    ],
)
def test_ca_b2_8_1_la_plantilla_solo_admite_dhcp_en_la_tarjeta_1(ci):
    sol = sol_ya_importada(cloudinit=ci)
    assert "V-B39" in errores(validar_solicitud(sol, inv_con_cloudinit(), caps()))


def test_ca_b2_8_3_sin_el_privilegio_de_cloudinit_la_seccion_se_deshabilita_y_el_resto_funciona():
    inv = inv_origen(nodos=("pve1",))  # ROL_MVP4: sin VM.Config.Cloudinit
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps(), inv, "pve1")
    assert not d[ControlB2.VALORES_CLOUDINIT].habilitado
    assert d[ControlB2.VALORES_CLOUDINIT].codigo is not None
    assert all(
        d[c].habilitado
        for c in (ControlB2.ASISTENTE, ControlB2.ORIGEN_ARCHIVO, ControlB2.CONVERTIR)
    )


def test_ca_b2_8_3_con_8_x_basta_vm_config_network():
    inv = inv_origen(nodos=("pve1",), version=Version("8.4.1", 8, 4, 1))
    d = disponibilidad_plantilla_imagen(inv.catalogo.permisos, caps((8, 4, 1)), inv, "pve1")
    assert d[ControlB2.VALORES_CLOUDINIT].habilitado  # ROL_MVP4 trae VM.Config.Network


# --- CA-B2.9: confirmación y conversión ----------------------------------------------------------


def test_ca_b2_9_1_con_la_casilla_desmarcada_hay_un_error_que_impide_crear(imagen):
    sol = sol_local(imagen, confirmada=False)
    problemas = validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps())
    assert "V-B14" in errores(problemas) and hay_errores(problemas)


def test_ca_b2_9_2_la_ultima_escritura_es_post_template_tras_crear_resize_y_cloudinit(imagen):
    m = crear_mundo_b2(inv=inv_con_cloudinit())
    est = m.ejecutar(sol_local(imagen, cloudinit=cloudinit_basico()))
    assert est.completo and est.es_plantilla
    assert [(a, b) for a, b in escrituras(m)] == [
        ("POST", "/nodes/pve1/storage/local/upload"),
        ("POST", "/nodes/pve1/qemu"),
        ("PUT", "/nodes/pve1/qemu/9100/resize"),
        ("PUT", "/nodes/pve1/qemu/9100/config"),
        ("POST", "/nodes/pve1/qemu/9100/template"),
    ]
    assert m.cluster.convertidas == [9100] and m.cluster.deletes == {}


def test_ca_b2_9_3_una_mv_encendida_no_se_convierte_y_se_avisa_sin_post_template(imagen):
    m = crear_mundo_b2()
    m.cluster.regla(
        "GET", r"/qemu/9100/status/current$", lambda _ll: {"status": "running", "vmid": 9100}
    )
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.FALLIDO
    assert est.error is not None and est.error.codigo == CodigoError.PLANTILLA_NO_APAGADA
    assert ("POST", "/nodes/pve1/qemu/9100/template") not in escrituras(m)
    assert not est.es_plantilla and m.cluster.convertidas == []


def test_ca_b2_9_3_una_mv_bloqueada_tampoco_se_convierte(imagen):
    m = crear_mundo_b2()
    m.cluster.regla(
        "GET", r"/qemu/9100/status/current$", lambda _ll: {"status": "stopped", "lock": "backup"}
    )
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.FALLIDO and m.cluster.convertidas == []


@pytest.mark.parametrize(
    ("motivo", "codigo"),
    [
        ("you can't convert a VM to template if VM is running", CodigoError.PLANTILLA_EN_MARCHA),
        (
            "unable to convert to template because VM contains snapshots",
            CodigoError.PLANTILLA_CON_SNAPSHOTS,
        ),
    ],
)
def test_ca_b2_9_4_los_errores_de_post_template_se_traducen_con_su_causa(imagen, motivo, codigo):
    from proxlaunch.interfaz.textos import texto_error

    m = crear_mundo_b2()
    m.cluster.regla("POST", r"/template$", error_http(500, motivo))
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.FALLIDO
    assert est.error is not None and est.error.codigo == codigo
    assert "plantilla" in texto_error(est.error)
    assert est.pasos[PasoB2.AMPLIAR] == EstadoPaso.HECHO  # nada de lo anterior se deshace
    assert m.cluster.deletes == {}


def test_ca_b2_9_4_si_la_tarea_de_conversion_falla_el_paso_5_queda_fallido(imagen):
    m = crear_mundo_b2()
    m.cluster.salida_tarea["qmtemplate"] = "unexpected status"
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.FALLIDO and not est.es_plantilla


def test_ca_b2_9_6_no_se_hace_nada_especial_con_la_unidad_cloudinit_tras_convertir(imagen):
    m = crear_mundo_b2()
    m.ejecutar(sol_local(imagen))
    assert escrituras(m)[-1] == ("POST", "/nodes/pve1/qemu/9100/template")
    assert [e for e in escrituras(m) if "cloudinit" in e[1]] == []


# --- CA-B2.10: progreso, fallos a mitad, reintentos y borrado ------------------------------------


def estados(est) -> dict[int, str]:
    return {int(p): e.value for p, e in est.pasos.items()}


def test_ca_b2_10_1_paso_1_fallido_deja_lo_demas_pendiente_y_no_ofrece_borrar(imagen):
    m = crear_mundo_b2()
    m.cluster.salida_tarea["imgcopy"] = "unexpected status"
    est = m.ejecutar(sol_local(imagen))
    assert estados(est) == {
        1: "fallido",
        2: "pendiente",
        3: "pendiente",
        4: "pendiente",
        5: "pendiente",
    }
    assert est.error is not None
    assert not m.servicio.puede_borrar(sol_local(imagen), est, inv=m.inv)
    assert m.cluster.vms == {} and m.cluster.deletes == {}  # la app no borra archivos ni MVs


def test_ca_b2_10_1_un_fallo_de_subida_con_el_archivo_en_import_informa_su_nombre(imagen):
    m = crear_mundo_b2()
    m.cluster.salida_tarea["imgcopy"] = "wrong sha256 checksum"
    m.cluster.guardar_aun_fallando = True  # el servidor dejó el archivo en import
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.FALLIDO
    assert "imagen_quedo_en_import" in est.avisos  # el archivo quedó y la app no lo borra
    assert NOMBRE_IMG in m.cluster.archivos[("pve1", "local")] and m.cluster.deletes == {}


def test_ca_b2_10_1_paso_2_fallido_antes_de_enviar_no_reserva_ni_ofrece_borrar(imagen):
    m = crear_mundo_b2()
    m.cluster.regla("POST", r"/nodes/pve1/qemu$", error_http(500, "boom"))
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert (
        est.pasos[PasoB2.IMAGEN] == EstadoPaso.HECHO
        and est.pasos[PasoB2.CREAR] == EstadoPaso.FALLIDO
    )
    assert est.vmid_reservado_aqui is False
    assert not m.servicio.puede_borrar(sol, est, inv=m.inv)


def test_ca_b2_10_1_paso_2_con_tarea_fallida_y_mv_a_medias_queda_fallido_y_no_se_convierte(imagen):
    m = crear_mundo_b2()
    m.cluster.exitstatus[9100] = "TASK ERROR: import failed"
    m.cluster.parciales = {9100}
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.FALLIDO
    m.cluster.exitstatus.clear()  # el reintento «saldría bien»
    final = m.ejecutar(sol)
    assert not final.es_plantilla and m.cluster.convertidas == []


def test_ejecutar_se_niega_a_escribir_si_la_solicitud_no_esta_confirmada(imagen):
    """Defensa en profundidad (V-B14): sin la casilla no se toca el servidor ni el estado."""
    m = crear_mundo_b2()
    sol = dataclasses.replace(sol_local(imagen), confirmada=False)
    with pytest.raises(ValueError):
        m.ejecutar(sol)
    assert m.cluster.deletes == {} and m.cluster.convertidas == [] and resizes(m) == []


def test_ca_b2_10_1_paso_2_con_tarea_fallida_y_mv_a_medias_si_se_ofrece_borrar(imagen):
    """Sea cual sea el paso en que se marque, la MV a medias es nuestra (hay UPID): se borra."""
    m = crear_mundo_b2()
    m.cluster.exitstatus[9100] = "TASK ERROR: import failed"
    m.cluster.parciales = {9100}
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert not est.completo and est.error is not None
    assert est.vmid_reservado_aqui is True and est.vmid_reservado == 9100
    cond = m.servicio.condiciones_borrado(sol, est, inv=m.inv)
    assert cond.ok and cond.error is None and cond.sin_certeza is False
    assert m.cluster.deletes == {}  # ofrecer no es borrar


def test_ca_b2_10_1_paso_2_con_tarea_fallida_sin_mv_no_ofrece_borrar(imagen):
    m = crear_mundo_b2()
    m.cluster.exitstatus[9100] = "TASK ERROR: import failed"  # y la MV no queda
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.FALLIDO
    assert est.vmid_reservado_aqui is True  # hubo UPID…
    assert (
        m.servicio.condiciones_borrado(sol, est, inv=m.inv).ok is False
    )  # …pero no hay qué borrar


def test_ca_b2_10_1_paso_3_fallido_deja_la_mv_completa_sin_ampliar(imagen):
    m = crear_mundo_b2()
    m.cluster.regla("PUT", r"/resize$", error_http(500, "resize failed"))
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert estados(est) == {1: "hecho", 2: "hecho", 3: "fallido", 4: "pendiente", 5: "pendiente"}
    assert m.servicio.puede_borrar(sol, est, inv=m.inv)  # la MV es nuestra y no es plantilla
    assert est.vmid_reservado_aqui is True


def test_ca_b2_10_1_paso_4_fallido_ofrece_reintentar_continuar_sin_ellos_o_borrar(imagen):
    m = crear_mundo_b2(inv=inv_con_cloudinit())
    m.cluster.regla("PUT", r"/config$", error_http(500, "config failed"), veces=1)
    sol = sol_local(imagen, cloudinit=cloudinit_basico())
    est = m.ejecutar(sol)
    assert estados(est) == {1: "hecho", 2: "hecho", 3: "hecho", 4: "fallido", 5: "pendiente"}
    assert m.servicio.puede_borrar(sol, est, inv=m.inv)
    omitida = m.servicio.omitir(est, PasoB2.CLOUDINIT)  # «continuar sin ellos»
    assert (
        omitida.pasos[PasoB2.CLOUDINIT] == EstadoPaso.OMITIDO
        and "omitido:cloudinit" in omitida.avisos
    )
    final = m.ejecutar(sol)
    assert (
        final.completo and final.es_plantilla and puts(m, "config") == []
    )  # nunca llegó a aplicarse


def test_ca_b2_10_1_paso_5_fallido_se_puede_reintentar_dejar_como_mv_normal_o_borrar(imagen):
    m = crear_mundo_b2()
    m.cluster.regla("POST", r"/template$", error_http(500, "boom"), veces=1)
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert estados(est) == {1: "hecho", 2: "hecho", 3: "hecho", 4: "omitido", 5: "fallido"}
    assert m.servicio.puede_borrar(sol, est, inv=m.inv)
    reintento = m.ejecutar(sol)  # «Reintentar la conversión»
    assert reintento.es_plantilla and reintento.completo
    # Y la alternativa: dejarla como MV normal.
    m2 = crear_mundo_b2()
    m2.cluster.regla("POST", r"/template$", error_http(500, "boom"))
    est2 = m2.ejecutar(sol)
    m2.servicio.omitir(est2, PasoB2.CONVERTIR)
    assert est2.completo and not est2.es_plantilla and m2.cluster.convertidas == []


@pytest.mark.parametrize("paso", [PasoB2.IMAGEN, PasoB2.CREAR])
def test_los_pasos_1_y_2_no_se_pueden_omitir(imagen, paso):
    m = crear_mundo_b2()
    with pytest.raises(ValueError):
        m.servicio.omitir(m.estado, paso)
    assert m.estado.pasos[paso] == EstadoPaso.PENDIENTE and escrituras(m) == []


def test_ca_b2_10_4_reintentar_tras_un_fallo_en_el_paso_3_no_repite_los_pasos_1_y_2(imagen):
    m = crear_mundo_b2()
    m.cluster.regla("PUT", r"/resize$", error_http(500, "resize failed"), veces=1)
    sol = sol_local(imagen)
    primero = m.ejecutar(sol)
    assert primero.pasos[PasoB2.AMPLIAR] == EstadoPaso.FALLIDO
    segundo = m.ejecutar(sol)
    assert segundo.completo and segundo.es_plantilla
    assert len(m.cluster.subidas) == 1 and total_post_qemu(m) == 1  # ni se sube ni se crea otra vez
    assert (
        len(m.cluster.llamadas_a("PUT", r"/resize$")) == 2
    )  # el resize (idempotente) se reintenta


def test_un_estado_ya_completo_no_repite_ningun_paso(imagen):
    m = crear_mundo_b2()
    sol = sol_local(imagen)
    m.ejecutar(sol)
    antes = len(m.cluster.llamadas)
    m.ejecutar(sol)
    assert len(m.cluster.llamadas) == antes  # ni siquiera lecturas: todo estaba resuelto


def test_ca_b2_10_5_cl_b19_una_conexion_perdida_al_crear_deja_el_paso_incierto_y_no_se_repite(
    imagen,
):
    m = crear_mundo_b2()
    m.cluster.regla("POST", r"/nodes/pve1/qemu$", envio_incierto(), veces=1)
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.INCIERTO
    assert est.pasos[PasoB2.AMPLIAR] == EstadoPaso.PENDIENTE
    # «Comprobar ahora» solo lee: la MV no existe → se sabe que no se creó → es seguro repetir.
    antes = list(escrituras(m))
    comprobado = m.servicio.comprobar_ahora(sol, est, inv=m.inv)
    assert escrituras(m) == antes
    assert comprobado.pasos[PasoB2.CREAR] == EstadoPaso.PENDIENTE


def test_ca_b2_10_5_incierto_con_una_mv_del_mismo_nombre_sin_upid_no_se_da_por_propia(imagen):
    """Decisión del orquestador: sin UPID de creación NUNCA se ofrece el borrado."""
    m = crear_mundo_b2()
    sol = sol_local(imagen)
    m.cluster.regla("POST", r"/nodes/pve1/qemu$", envio_incierto(), veces=1)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.INCIERTO and est.vmid_reservado_aqui is False
    # La MV con ese nombre aparece (¿la creó el POST perdido o es de otra persona? No se sabe).
    m.cluster.agregar_vm(9100, "pve1", "plantilla-ubuntu-2404", status="stopped")
    antes = list(escrituras(m))
    comprobado = m.servicio.comprobar_ahora(sol, est, inv=m.inv)
    assert escrituras(m) == antes
    assert comprobado.pasos[PasoB2.CREAR] == EstadoPaso.INCIERTO  # sigue dudoso
    assert comprobado.vmid_reservado_aqui is False
    assert (
        comprobado.error is not None and comprobado.error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    )
    cond = m.servicio.condiciones_borrado(sol, comprobado, inv=m.inv)
    assert cond.ok is False and cond.sin_certeza is True
    assert cond.error is not None and cond.error.codigo == CodigoError.ROLLBACK_NO_PROPIA
    assert cond.error.params["motivo"] == "sin_upid"
    with pytest.raises(ValueError):
        m.servicio.borrar_a_medio_crear(
            sol, comprobado, threading.Event(), confirmado=False, inv=m.inv
        )
    m.servicio.borrar_a_medio_crear(sol, comprobado, threading.Event(), confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {} and 9100 in m.cluster.vms  # nunca se borra una MV ajena


def test_ca_b2_10_5_un_incierto_nunca_se_repite_a_ciegas_al_reanudar(imagen):
    m = crear_mundo_b2()
    m.cluster.regla("POST", r"/nodes/pve1/qemu$", envio_incierto(), veces=1)
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    m.cluster.agregar_vm(
        9100, "pve1", "plantilla-ubuntu-2404", status="stopped"
    )  # existe, sin UPID
    segundo = m.ejecutar(sol)
    assert segundo.pasos[PasoB2.CREAR] == EstadoPaso.INCIERTO
    assert total_post_qemu(m) == 1  # no hubo un segundo POST de creación
    assert segundo is est


def test_ca_b2_10_5_conexion_perdida_al_convertir_se_reconcilia_leyendo_la_config(imagen):
    m = crear_mundo_b2()

    def convierte_y_pierde_la_respuesta(_ll):
        m.cluster._convertir("pve1", 9100)  # el servidor SÍ actuó
        raise envio_incierto()

    m.cluster.regla("POST", r"/template$", convierte_y_pierde_la_respuesta, veces=1)
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.INCIERTO
    antes = list(escrituras(m))
    comprobado = m.servicio.comprobar_ahora(sol, est, inv=m.inv)
    assert escrituras(m) == antes  # solo lecturas
    assert comprobado.pasos[PasoB2.CONVERTIR] == EstadoPaso.HECHO and comprobado.es_plantilla


def test_ca_b2_10_5_si_la_conversion_no_llego_a_actuar_se_puede_repetir(imagen):
    m = crear_mundo_b2()
    m.cluster.regla("POST", r"/template$", envio_incierto(), veces=1)
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.INCIERTO
    m.servicio.comprobar_ahora(sol, est, inv=m.inv)
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.PENDIENTE
    assert m.ejecutar(sol).es_plantilla


def test_ca_b2_10_5_una_subida_cortada_deja_el_paso_1_incierto(imagen):
    from .apoyo_fase_b_agente import TransporteAgente

    m = crear_mundo_b2()
    assert isinstance(m.sesion.cliente._transporte, TransporteAgente)
    m.sesion.cliente._transporte.fallo_subida = envio_incierto()
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.IMAGEN] == EstadoPaso.INCIERTO
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.PENDIENTE and total_post_qemu(m) == 0


def test_ca_b2_10_6_dejar_de_esperar_a_mitad_de_la_creacion_no_borra_nada(imagen):
    m = crear_mundo_b2()
    m.cluster.en_curso[("qmcreate", 9100)] = 50  # la tarea de creación sigue «running»
    m.cluster.regla("GET", r"qmcreate.+/status$", lambda _ll: m.cancelado.set(), veces=1)
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.INCIERTO  # la tarea sigue en el servidor
    assert m.cluster.deletes == {} and m.cluster.convertidas == []
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.PENDIENTE


def test_ca_b2_10_6_dejar_de_esperar_durante_la_conversion_deja_el_paso_5_incierto(imagen):
    m = crear_mundo_b2()
    m.cluster.en_curso[("qmtemplate", 9100)] = 50  # la tarea de conversión sigue «running»

    def convierte_y_el_usuario_deja_de_esperar(_ll):
        upid = m.cluster._convertir("pve1", 9100)
        m.cancelado.set()
        return upid

    m.cluster.regla("POST", r"/template$", convierte_y_el_usuario_deja_de_esperar, veces=1)
    est = m.ejecutar(sol_local(imagen))
    assert est.pasos[PasoB2.CONVERTIR] == EstadoPaso.INCIERTO  # la tarea sigue en el servidor
    assert est.upid is not None and m.cluster.deletes == {}
    m.cancelado.clear()
    m.cluster.en_curso.clear()
    comprobado = m.servicio.comprobar_ahora(sol_local(imagen), est, inv=m.inv)
    assert comprobado.pasos[PasoB2.CONVERTIR] == EstadoPaso.HECHO and comprobado.es_plantilla


def test_un_evento_cancelado_antes_de_empezar_no_hace_nada(imagen):
    m = crear_mundo_b2()
    m.cancelado.set()
    est = m.ejecutar(sol_local(imagen))
    assert escrituras(m) == [] and est.pasos[PasoB2.IMAGEN] == EstadoPaso.PENDIENTE


# --- Borrar a medio crear (RF-B2.10) -------------------------------------------------------------


def mundo_con_mv_a_medias(imagen, **config: Any):
    """Paso 3 fallido: la MV 9100 existe, la reservó el asistente y no es plantilla."""
    m = crear_mundo_b2()
    m.cluster.regla("PUT", r"/resize$", error_http(500, "resize failed"))
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.pasos[PasoB2.AMPLIAR] == EstadoPaso.FALLIDO and est.vmid_reservado_aqui
    m.cluster.vms[9100]["config"].update(config)
    return m, sol, est


def test_ca_b2_10_3_confirmado_se_emite_delete_sin_purge_y_se_espera_su_tarea(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    assert m.servicio.puede_borrar(sol, est, inv=m.inv)
    final = m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {9100: 1} and 9100 not in m.cluster.vms
    params = m.cluster.params_delete[9100] or {}
    assert "purge" not in params and set(params) <= {"destroy-unreferenced-disks"}
    assert str(params.get("destroy-unreferenced-disks", "0")) == "0"
    assert [c.ruta for c in m.cluster.llamadas_a("DELETE")] == ["/nodes/pve1/qemu/9100"]
    ultimo_delete = max(i for i, c in enumerate(m.cluster.llamadas) if c.metodo == "DELETE")
    assert any(
        "/tasks/" in c.ruta for c in m.cluster.llamadas[ultimo_delete + 1 :]
    )  # espera la tarea
    assert final.error is None and "maquina_borrada" in final.avisos
    assert final.vmid_reservado_aqui is False and final.vmid_reservado is None
    assert [
        final.pasos[p] for p in (PasoB2.CREAR, PasoB2.AMPLIAR, PasoB2.CLOUDINIT, PasoB2.CONVERTIR)
    ] == [EstadoPaso.PENDIENTE] * 4
    assert (
        final.pasos[PasoB2.IMAGEN] == EstadoPaso.HECHO
    )  # la imagen no se borra ni se vuelve a subir


def test_tras_borrar_se_puede_volver_a_crear_sin_repetir_la_imagen(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    m.cluster.reglas.clear()
    m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    final = m.ejecutar(sol)
    assert final.completo and final.es_plantilla and len(m.cluster.subidas) == 1


def test_borrar_exige_confirmado_true_y_si_no_lanza_value_error_sin_tocar_nada(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    antes = len(m.cluster.llamadas)
    for valor in (False, 0, None):
        with pytest.raises(ValueError):
            m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=valor, inv=m.inv)  # type: ignore[arg-type]
    assert len(m.cluster.llamadas) == antes and m.cluster.deletes == {}


@pytest.mark.parametrize(
    ("cambio", "codigo", "motivo"),
    [
        ({"name": "otra-maquina"}, CodigoError.ROLLBACK_NO_PROPIA, "nombre"),
        ({"template": 1}, CodigoError.ROLLBACK_NO_PROPIA, "plantilla"),
        ({"lock": "backup"}, CodigoError.ROLLBACK_BLOQUEADA, "lock"),
        ({"protection": 1}, CodigoError.ROLLBACK_PROTEGIDA, "protection"),
    ],
)
def test_ca_b2_10_2_si_la_mv_no_cumple_las_condiciones_no_se_ofrece_ni_se_emite_delete(
    imagen, cambio, codigo, motivo
):
    m, sol, est = mundo_con_mv_a_medias(imagen, **cambio)
    cond = m.servicio.condiciones_borrado(sol, est, inv=m.inv)
    assert cond.ok is False and cond.error is not None and cond.error.codigo == codigo
    assert cond.error.params["motivo"] == motivo
    assert m.servicio.puede_borrar(sol, est, inv=m.inv) is False
    resultado = m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {} and 9100 in m.cluster.vms
    assert resultado.error is not None and resultado.error.codigo == codigo


def test_ca_b2_10_2_una_mv_encendida_no_se_ofrece_para_borrar(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    m.cluster.vms[9100]["status"] = "running"
    cond = m.servicio.condiciones_borrado(sol, est, inv=m.inv)
    assert cond.ok is False and cond.error is not None
    assert cond.error.codigo == CodigoError.ROLLBACK_ENCENDIDA
    m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {}


def test_ca_b2_10_2_si_el_vmid_no_lo_reservo_el_asistente_no_se_ofrece(imagen):
    m = crear_mundo_b2()
    m.cluster.agregar_vm(9100, "pve1", "plantilla-ubuntu-2404", status="stopped")  # ya existía
    sol = sol_local(imagen)
    est = m.ejecutar(sol)  # la creación falla: V-03 «VM ya existe»
    assert est.pasos[PasoB2.CREAR] == EstadoPaso.FALLIDO and est.vmid_reservado_aqui is False
    cond = m.servicio.condiciones_borrado(sol, est, inv=m.inv)
    assert cond.ok is False and cond.error is not None
    assert (
        cond.error.codigo == CodigoError.ROLLBACK_NO_PROPIA
        and cond.error.params["motivo"] == "sin_upid"
    )
    m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {}


def test_ca_b2_10_2_sin_vm_allocate_la_accion_no_se_ofrece(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    sin = inv_origen(
        nodos=("pve1",), permisos_efectivos=permisos(ROL_MVP4, quitar=("VM.Allocate",))
    )
    cond = m.servicio.condiciones_borrado(sol, est, inv=sin)
    assert cond.ok is False and cond.error is not None
    assert cond.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=sin)
    assert m.cluster.deletes == {}
    d = disponibilidad_plantilla_imagen(sin.catalogo.permisos, caps(), sin, "pve1")
    assert not d[ControlB2.BORRAR].habilitado and not d[ControlB2.CONVERTIR].habilitado


def test_ca_b2_10_2_si_no_se_pueden_leer_los_datos_no_hay_certeza_y_no_se_ofrece(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    m.cluster.regla("GET", r"/qemu/9100/config$", error_http(596, ""))
    cond = m.servicio.condiciones_borrado(sol, est, inv=m.inv)
    assert cond.ok is False and cond.sin_certeza is True
    m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {}


def test_ca_b2_10_2_una_plantilla_ya_convertida_nunca_se_borra_desde_la_app(imagen):
    m = crear_mundo_b2()
    sol = sol_local(imagen)
    est = m.ejecutar(sol)
    assert est.es_plantilla
    assert m.servicio.puede_borrar(sol, est, inv=m.inv) is False
    m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert m.cluster.deletes == {} and 9100 in m.cluster.vms


def test_si_el_delete_falla_se_informa_y_el_estado_no_se_reinicia(imagen):
    m, sol, est = mundo_con_mv_a_medias(imagen)
    m.cluster.regla("DELETE", r"/qemu/9100$", error_http(500, "no se pudo"))
    final = m.servicio.borrar_a_medio_crear(sol, est, m.cancelado, confirmado=True, inv=m.inv)
    assert final.error is not None and final.vmid_reservado_aqui is True
    assert final.pasos[PasoB2.CREAR] == EstadoPaso.HECHO


# --- CA-B2.11 y CA-B7.1 --------------------------------------------------------------------------


def test_ca_b2_11_1_la_plantilla_nueva_aparece_en_las_plantillas_y_se_detecta_su_unidad_cloudinit(
    imagen,
):
    m = crear_mundo_b2()
    est = m.ejecutar(sol_local(imagen))
    assert est.es_plantilla and est.completo
    nuevas = [p for p in m.sesion.cliente.plantillas_visibles() if p.vmid == 9100]
    assert [(p.nombre, p.nodo) for p in nuevas] == [("plantilla-ubuntu-2404", "pve1")]
    config = m.sesion.cliente.config_vm("pve1", 9100)
    info = info_cloudinit(config)
    assert info.unidad is True and info.clave_unidad == "ide2"
    assert info.agente is True and info.ostype == "l26"
    assert str(config["template"]) == "1"


def test_ca_b2_11_1_sin_la_unidad_cloudinit_la_plantilla_la_detecta_como_ausente(imagen):
    m = crear_mundo_b2()
    m.ejecutar(sol_local(imagen, fijas=FijasPlantilla(unidad_cloudinit=False)))
    info = info_cloudinit(m.sesion.cliente.config_vm("pve1", 9100))
    assert info.unidad is False


def test_ca_b7_1_1_b2_no_usa_el_libro_ni_deja_ninguna_entrada(imagen):
    """B2 no es un lote: ni el servicio recibe un libro ni queda nada para Deshacer."""
    import inspect

    from proxlaunch.nucleo.plantilla_imagen import ServicioPlantillaImagen

    parametros = set(inspect.signature(ServicioPlantillaImagen.__init__).parameters)
    assert not parametros & {"libro", "plan", "control"}
    m = crear_mundo_b2()
    est = m.ejecutar(sol_local(imagen))
    assert est.es_plantilla and m.cluster.deletes == {}
    assert not any("lote-" in str(c.datos) for c in m.cluster.llamadas)  # sin etiquetas de lote


@pytest.mark.parametrize(
    "fallo",
    [
        ("PUT", r"/resize$"),
        ("PUT", r"/qemu/9100/config$"),
        ("POST", r"/template$"),
        ("POST", r"/nodes/pve1/qemu$"),
    ],
)
def test_ca_b7_1_2_ningun_fallo_de_b2_emite_delete_sin_la_confirmacion(imagen, fallo):
    m = crear_mundo_b2(inv=inv_con_cloudinit())
    m.cluster.regla(fallo[0], fallo[1], error_http(500, "boom"))
    est = m.ejecutar(sol_local(imagen, cloudinit=cloudinit_basico()))
    assert not est.completo
    assert m.cluster.deletes == {} and m.cluster.llamadas_a("DELETE") == []
    m.ejecutar(sol_local(imagen, cloudinit=cloudinit_basico()))  # y reintentar tampoco borra
    assert m.cluster.llamadas_a("DELETE") == []


def test_los_observadores_de_estado_y_progreso_reciben_copias_y_su_fallo_no_detiene_el_asistente(
    imagen,
):
    m = crear_mundo_b2()
    avisados: list[Any] = []

    def roto(estado) -> None:
        avisados.append(estado)
        raise RuntimeError("observador roto")

    est = m.servicio.ejecutar(
        sol_local(imagen), m.inv, m.estado, roto, m.progreso.append, m.cancelado
    )
    assert est.completo and avisados and all(a is not est for a in avisados)
    assert avisados[-1].pasos == est.pasos
    assert m.progreso  # hubo progreso de la subida


def test_el_reloj_es_simulado_y_no_se_duerme_de_verdad(imagen):
    m = crear_mundo_b2()
    assert isinstance(m.reloj, RelojSeguro)
    m.cluster.en_curso[("qmcreate", 9100)] = 3
    est = m.ejecutar(sol_local(imagen))
    assert est.completo and m.reloj.ahora() > 0  # el tiempo avanzó solo en el reloj simulado


def test_la_contraseña_nunca_forma_parte_de_ninguna_peticion_ni_registro_de_b2(imagen, caplog):
    m = crear_mundo_b2(inv=inv_con_cloudinit())
    with caplog.at_level(logging.DEBUG):
        m.ejecutar(sol_local(imagen, cloudinit=cloudinit_basico()))
    volcado = repr([(c.metodo, c.ruta, c.params, c.datos) for c in m.cluster.llamadas])
    assert "cipassword" not in volcado and CENTINELA_CONTRASENA not in caplog.text
