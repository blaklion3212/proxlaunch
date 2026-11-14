"""MVP 4: ServicioTransferencias (subir y descargar por URL) y el cliente de transferencias.

Requisitos: RF-O09 (CA-O09.1..O09.12), RF-O10 (CA-O10.1..O10.7), RF-O11 (CA-O11.1..O11.11),
RF-O12 (CA-O12.1..O12.9), RF-O25 (registro), V-O13..V-O16, V-O27 (E-O23), INV-O1, INV-O2, INV-O4,
INV-O6 (nada de URL, ruta ni hash en logs, errores o registro), E-O06..E-O11, E-O22, E-O23.
"""

import hashlib
import logging
import re
import threading
import time
from pathlib import Path

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.origen.constantes import (
    CHUNK_SUBIDA,
    PARO_SIN_PROGRESO_S,
    RESERVA_RAIZ_MIB,
    RESERVA_STORAGE_MIB,
)
from proxlaunch.nucleo.transferencias.modelos import (
    DestinoTransferencia,
    EstadoTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import RegistroSesion, ServicioTransferencias
from proxlaunch.nucleo.transferencias.url import validar_checksum, validar_url

from .apoyo_api import crear_sesion
from .apoyo_lote import GIB, RelojSeguro
from .apoyo_mvp3 import sin_centinelas
from .apoyo_mvp4 import ROL_MVP3, ServidorArchivos, inv_origen, permisos

MIB = 1024**2
DESTINO = DestinoTransferencia("pve1", "local", Contenido.ISO, "alpine.iso")
CENTINELAS_URL = ("SECRETO-TOKEN-URL", "clave-de-la-url", "usuario-url")


class _Mundo:
    def __init__(self, tmp_path: Path, *, version=None, tam=5000, **kw_srv):
        self.srv = ServidorArchivos(**kw_srv)
        self.reloj = RelojSeguro()
        self.sesion = crear_sesion(self.srv, reloj=self.reloj)
        self.registro = RegistroSesion()
        self.inv = inv_origen(version=version)
        self.archivo = tmp_path / "alpine.iso"
        self.datos = bytes(range(256)) * (tam // 256) + b"z" * (tam % 256)
        self.archivo.write_bytes(self.datos)
        self.eventos: list = []
        self.cancelado = threading.Event()

    def servicio(self, **kw) -> ServicioTransferencias:
        return ServicioTransferencias(
            self.sesion, self.reloj, self.registro, hora_local=lambda: "10:00", **kw
        )

    def subir(self, destino=DESTINO, *, acepta=False, inv=None, servicio=None):
        return (servicio or self.servicio()).subir(
            self.archivo,
            destino,
            inv or self.inv,
            al_progresar=self.eventos.append,
            cancelado=self.cancelado,
            acepta_aviso_raiz=acepta,
        )

    def posts_upload(self):
        return self.srv.llamadas_a("POST", "/upload$")


@pytest.fixture
def m(tmp_path):
    return _Mundo(tmp_path)


# --- Subida correcta (CA-O09.1, O09.3, O09.4, O09.6) ----------------------------------------------


def test_ca_o09_1_una_sola_peticion_upload_con_content_checksum_y_el_archivo_al_final(m):
    r = m.subir()
    assert r.estado == EstadoTransferencia.TERMINADA, r.error
    assert r.volid == "local:iso/alpine.iso" and r.upid == m.srv.UPID and r.error is None
    assert len(m.posts_upload()) == 1 and len(m.srv.subidas) == 1
    cuerpo = m.srv.subidas[0]
    sha = hashlib.sha256(m.datos).hexdigest()
    orden = [
        x.decode() for x in re.findall(rb'Content-Disposition: form-data; name="([^"]+)"', cuerpo)
    ]
    assert orden == ["content", "checksum", "checksum-algorithm", "filename"]
    assert f'name="checksum"\r\n\r\n{sha}\r\n'.encode() in cuerpo  # sha256 calculado ANTES
    assert b'name="checksum-algorithm"\r\n\r\nsha256\r\n' in cuerpo
    assert b'name="content"\r\n\r\niso\r\n' in cuerpo
    assert b"Content-Type: application/octet-stream\r\n\r\n" + m.datos in cuerpo
    assert b"tmpfilename" not in cuerpo


def test_la_subida_usa_content_length_exacto_y_el_multipart_de_la_misma_sesion(m):
    m.subir()
    cab = m.srv.cabeceras_subida[0]
    assert cab["Content-Length"] == len(m.srv.subidas[0])
    assert cab["Content-Type"].startswith("multipart/form-data; boundary=")


def test_ca_o09_3_ca_o09_4_sondea_la_tarea_y_verifica_el_volumen_en_el_catalogo(m):
    r = m.subir()
    estados = [e.estado for e in m.eventos]
    ordenados = [
        EstadoTransferencia.CALCULANDO_HUELLA,
        EstadoTransferencia.COMPROBANDO,
        EstadoTransferencia.TRANSFIRIENDO,
        EstadoTransferencia.ESPERANDO_SERVIDOR,
        EstadoTransferencia.VERIFICANDO,
    ]
    posiciones = [estados.index(e) for e in ordenados]
    assert posiciones == sorted(posiciones)
    assert len(m.srv.llamadas_a("GET", "/tasks/.+/status$")) >= 2  # running → stopped
    assert r.estado == EstadoTransferencia.TERMINADA


def test_el_progreso_de_la_transferencia_alcanza_el_total_y_nunca_lo_supera(m):
    m.subir()
    transf = [e for e in m.eventos if e.estado == EstadoTransferencia.TRANSFIRIENDO]
    assert transf and all(e.total_bytes == 5000 and 0 <= e.hechos_bytes <= 5000 for e in transf)
    assert (
        max(e.hechos_bytes for e in transf) == 5000
        or max(e.hechos_bytes for e in m.eventos) == 5000
    )


def test_un_observador_de_progreso_que_falla_no_interrumpe_la_subida(m):
    def malo(_):
        raise RuntimeError("boom")

    r = m.servicio().subir(
        m.archivo, DESTINO, m.inv, al_progresar=malo, cancelado=m.cancelado, acepta_aviso_raiz=False
    )
    assert r.estado == EstadoTransferencia.TERMINADA


def test_ca_o09_12_si_el_servidor_normaliza_el_nombre_se_acepta_el_volumen_real(m):
    m.srv.guardar_al_subir = False
    m.srv.contenido[("pve1", "local")]["ALPINE.ISO"] = (5000, "iso")
    # el nombre «alpine.iso» ya existe sin distinguir mayúsculas → se bloquea antes de subir
    r = m.subir()
    assert r.error.codigo == CodigoError.NOMBRE_YA_EXISTE


def test_verificar_acepta_el_nombre_normalizado_con_el_mismo_tamano(m):
    m.srv.contenido[("pve1", "local")]["ALPINE.ISO"] = (5000, "iso")
    r = m.servicio().verificar(DESTINO, 5000)
    assert r.estado == EstadoTransferencia.TERMINADA and r.volid == "local:iso/ALPINE.ISO"
    m.srv.contenido[("pve1", "local")]["ALPINE.ISO"] = (4999, "iso")
    assert (
        m.servicio().verificar(DESTINO, 5000).error.codigo
        == CodigoError.TRANSFERENCIA_NO_VERIFICADA
    )


def test_ca_o09_4_e_o06_si_el_tamano_o_el_volid_no_coinciden_no_se_usa_el_archivo(m):
    m.srv.tamano_guardado = 4999
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA and r.volid is None
    assert r.error.codigo == CodigoError.TRANSFERENCIA_NO_VERIFICADA
    assert (r.error.params["esperado"], r.error.params["real"]) == ("5000", "4999")
    carpeta = m.archivo.parent / "otro"
    carpeta.mkdir()
    m2 = _Mundo(carpeta)
    m2.srv.guardar_al_subir = False  # el servidor dice OK pero el archivo no aparece
    r2 = m2.subir()
    assert r2.error.codigo == CodigoError.TRANSFERENCIA_NO_VERIFICADA
    assert (
        r2.error.params["real"] == "ausente" and r2.error.params["volid"] == "local:iso/alpine.iso"
    )


def test_ca_o09_5_e_o07_huella_incorrecta_se_comprueba_que_no_quedo_el_archivo(m):
    m.srv.guardar_al_subir = False
    m.srv.estados_tarea = [{"status": "stopped", "exitstatus": "checksum verification failed"}]
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA
    assert r.error.params["algoritmo"] == "sha256" and r.quedo_archivo is False


def test_ca_o09_5_si_pese_a_la_huella_incorrecta_el_archivo_existe_se_avisa(m):
    m.srv.estados_tarea = [{"status": "stopped", "exitstatus": "wrong sha256 checksum"}]
    r = m.subir()
    assert r.error.codigo == CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA and r.quedo_archivo is True


def test_otra_falla_de_la_tarea_se_traduce_con_el_traductor_de_errores(m):
    m.srv.estados_tarea = [{"status": "stopped", "exitstatus": "unexpected status"}]
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA and r.error.codigo == CodigoError.DESCONOCIDO


def test_ca_o09_3_si_la_tarea_no_termina_a_tiempo_no_es_un_fallo(m):
    m.srv.estados_tarea = [{"status": "running"}]
    r = m.subir()
    assert r.estado == EstadoTransferencia.SIN_ESPERAR and r.error is None
    assert m.registro.lista()[-1].estado == EstadoTransferencia.SIN_ESPERAR


# --- RF-O10 / INV-O2: nunca sobrescribir ----------------------------------------------------------


def test_ca_o10_1_inv_o2_si_el_nombre_ya_existe_no_se_envia_ni_un_byte(m):
    m.srv.contenido[("pve1", "local")]["alpine.iso"] = (1, "iso")
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.NOMBRE_YA_EXISTE  # E-O10
    assert r.error.params == {"storage": "local", "nombre": "alpine.iso"}
    assert m.srv.subidas == [] and m.posts_upload() == []


def test_ca_o10_7_se_trata_como_existente_sin_distinguir_mayusculas(m):
    m.srv.contenido[("pve1", "local")]["ALPINE.ISO"] = (1, "iso")
    assert m.subir().error.codigo == CodigoError.NOMBRE_YA_EXISTE and m.srv.subidas == []


def test_ca_o10_2_el_nombre_se_vuelve_a_comprobar_justo_antes_del_primer_byte(m):
    """Otro usuario crea el archivo entre la primera comprobación y el envío."""
    llamadas = {"n": 0}

    def aparece_en_la_segunda():
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            m.srv.contenido[("pve1", "local")]["alpine.iso"] = (7, "iso")

    m.srv.fallos["contenido"] = aparece_en_la_segunda
    r = m.subir()
    assert llamadas["n"] >= 2
    assert r.error.codigo == CodigoError.NOMBRE_YA_EXISTE and m.posts_upload() == []


def test_ca_o10_1_un_403_al_listar_el_destino_no_permite_subir_a_ciegas(m):
    m.srv.fallos["contenido"] = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    r = m.subir()
    assert (
        r.error.codigo == CodigoError.CATALOGO_SIN_PERMISO and r.error.params["storage"] == "local"
    )
    assert m.posts_upload() == []


def test_no_existe_ninguna_opcion_para_sobrescribir_en_la_interfaz_publica():
    import inspect

    for metodo in (ServicioTransferencias.subir, ServicioTransferencias.descargar):
        nombres = " ".join(inspect.signature(metodo).parameters)
        assert (
            "sobrescrib" not in nombres and "overwrite" not in nombres and "forzar" not in nombres
        )


# --- Espacio (V-O13, E-O22) -----------------------------------------------------------------------


def test_ca_o10_3_el_limite_del_espacio_del_storage_es_avail_menos_100_mib(tmp_path):
    justo = _Mundo(tmp_path, libre=5000 + RESERVA_STORAGE_MIB * MIB)
    assert justo.subir().estado == EstadoTransferencia.TERMINADA
    corto_dir = tmp_path / "c"
    corto_dir.mkdir()
    corto = _Mundo(corto_dir, libre=5000 + RESERVA_STORAGE_MIB * MIB - 1)
    r = corto.subir()
    assert r.error.codigo == CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA  # E-O22
    assert r.error.params["storage"] == "local" and r.error.params["tamano"] == "5000"
    assert corto.posts_upload() == []


def test_ca_o10_4_poco_espacio_en_la_raiz_del_nodo_avisa_y_pide_la_casilla(m):
    m.srv.raiz_libre = 5000 + RESERVA_RAIZ_MIB * MIB - 1
    sin_casilla = m.subir(acepta=False)
    assert sin_casilla.error.codigo == CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA
    assert sin_casilla.error.params["ambito"] == "raiz" and m.posts_upload() == []
    con_casilla = m.subir(acepta=True)
    assert con_casilla.estado == EstadoTransferencia.TERMINADA


def test_ca_o10_4_si_el_endpoint_no_devuelve_el_dato_de_la_raiz_no_se_avisa(tmp_path):
    mundo = _Mundo(tmp_path, raiz_libre=None)
    assert mundo.subir(acepta=False).estado == EstadoTransferencia.TERMINADA
    caido = _Mundo(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path)
    caido.srv.fallos["estado_nodo"] = ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}, "403")
    assert caido.subir().estado == EstadoTransferencia.TERMINADA


def test_ca_o10_6_las_comprobaciones_previas_solo_usan_lecturas(m):
    comp = m.servicio().comprobar(DESTINO, 5000, m.inv)
    assert set(m.srv.metodos) == {"GET"}
    assert comp.volid_existente is None and comp.permiso is True and comp.problemas == ()
    assert comp.libre_storage_bytes == 500 * GIB and comp.libre_raiz_bytes == 50 * GIB


def test_comprobar_devuelve_el_volid_existente_y_el_problema_v_o14(m):
    m.srv.contenido[("pve1", "local")]["alpine.iso"] = (1, "iso")
    comp = m.servicio().comprobar(DESTINO, 5000, m.inv)
    assert comp.volid_existente == "local:iso/alpine.iso"
    assert [p.codigo for p in comp.problemas] == ["V-O14"]


def test_comprobar_con_tamano_desconocido_no_da_problemas_de_espacio(m):
    m.srv.libre = 1
    assert m.servicio().comprobar(DESTINO, None, m.inv).problemas == ()


# --- Permisos (V-O15, V-O16) ----------------------------------------------------------------------


def test_ca_o10_5_v_o15_sin_allocate_template_no_se_sube_nada(m):
    inv = inv_origen(privilegios=ROL_MVP3)
    r = m.subir(inv=inv)
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["privilegio"] == "Datastore.AllocateTemplate"
    assert r.error.params["ruta"] == "/storage/local" and r.error.params["via"] == "subir_iso"
    assert m.posts_upload() == []


def test_con_permisos_desconocidos_la_subida_se_intenta_y_el_servidor_decide(m):
    r = m.subir(inv=inv_origen(permisos_efectivos=None))
    assert r.estado == EstadoTransferencia.TERMINADA


def test_la_via_del_permiso_distingue_iso_de_imagen(m, tmp_path):
    inv = inv_origen(privilegios=ROL_MVP3)
    destino = DestinoTransferencia("pve1", "local", Contenido.IMPORT, "cirros.qcow2")
    r = m.subir(destino, inv=inv)
    assert r.error.params["via"] == "subir_imagen"


# --- Cancelación, cortes y ticket (RF-O12, RNF-O03, RNF-O12) --------------------------------------


def test_ca_o12_3_cancelar_antes_de_empezar_no_envia_nada_y_no_deja_archivo(m):
    m.cancelado.set()
    r = m.subir()
    assert r.estado == EstadoTransferencia.CANCELADA and r.quedo_archivo is False
    assert r.error.codigo == CodigoError.TRANSFERENCIA_CANCELADA
    assert m.posts_upload() == []


def test_ca_o12_3_cancelar_durante_el_calculo_de_la_huella_no_envia_nada(tmp_path):
    mundo = _Mundo(tmp_path, tam=3 * CHUNK_SUBIDA)

    def cancela(p):
        if p.estado == EstadoTransferencia.CALCULANDO_HUELLA and p.hechos_bytes > 0:
            mundo.cancelado.set()

    r = mundo.servicio().subir(
        mundo.archivo, DESTINO, mundo.inv, al_progresar=cancela, cancelado=mundo.cancelado,
        acepta_aviso_raiz=False,
    )  # fmt: skip
    assert r.estado == EstadoTransferencia.CANCELADA and mundo.posts_upload() == []
    assert mundo.srv.llamadas_a("GET", "/content$") == []  # ni siquiera comprobó el destino


def test_ca_o12_2_cancelar_durante_el_envio_en_menos_de_2_s_y_verifica_el_catalogo(m):
    def cancela_y_deja_parcial():
        m.cancelado.set()
        m.srv.contenido[("pve1", "local")]["alpine.iso"] = (100, "iso")  # archivo parcial

    m.srv.fallos["durante_subida"] = cancela_y_deja_parcial
    t0 = time.monotonic()
    r = m.subir()
    assert time.monotonic() - t0 < 2.0
    assert r.estado == EstadoTransferencia.CANCELADA
    assert r.quedo_archivo is True  # «se canceló, pero el archivo parcial quedó guardado»
    assert r.error.params["quedo_archivo"] == "si"
    assert (
        len(m.posts_upload()) == 1
        and m.registro.lista()[-1].estado == EstadoTransferencia.CANCELADA
    )


def test_ca_o12_2_cancelar_durante_el_envio_sin_archivo_parcial(m):
    m.srv.fallos["durante_subida"] = lambda: m.cancelado.set()
    r = m.subir()
    assert r.estado == EstadoTransferencia.CANCELADA and r.quedo_archivo is False
    assert r.error.params["quedo_archivo"] == "no"


def test_ca_o09_7_e_o08_un_corte_durante_el_envio_no_se_reintenta_y_se_verifica_el_catalogo(m):
    corte = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE, {"host": "x", "incierto": "1"}, "connection reset"
    )
    m.srv.fallos["durante_subida"] = corte
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.TRANSFERENCIA_CORTADA  # E-O08
    assert r.error.params["total"] == "5000" and "bytes" in r.error.params
    assert len(m.posts_upload()) == 1  # sin reintento automático
    assert r.quedo_archivo is False  # se mira el catálogo, no se asume


def test_ca_o09_7_ticket_caducado_a_mitad_de_la_subida_no_se_reintenta(m):
    m.srv.fallos["durante_subida"] = ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "401")
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.SESION_EXPIRADA and len(m.posts_upload()) == 1


def test_ca_o12_6_la_subida_se_pide_con_el_tope_de_120_s_sin_progreso(m):
    m.subir()
    assert m.srv.timeouts_subida == [PARO_SIN_PROGRESO_S] and PARO_SIN_PROGRESO_S == 120.0


def test_ca_o12_6_si_la_tarea_no_responde_mas_de_120_s_es_transferencia_cortada(m):
    caida = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "x"}, "timeout")
    m.srv.estados_tarea = [caida]
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.TRANSFERENCIA_CORTADA
    assert (
        m.reloj.ahora() >= 120.0
    )  # esperó el plazo (reloj simulado) y no más allá de lo necesario


def test_una_caida_breve_de_la_red_durante_el_sondeo_no_falla(m):
    caida = ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"}, "596")
    m.srv.estados_tarea = [caida, caida, {"status": "stopped", "exitstatus": "OK"}]
    assert m.subir().estado == EstadoTransferencia.TERMINADA


# --- E-O09: el archivo cambia (CA-O09.8) ----------------------------------------------------------


def test_ca_o09_8_e_o09_el_archivo_cambia_tras_el_envio_no_se_da_por_buena(m):
    def modifica(_):
        with open(m.archivo, "ab") as f:
            f.write(b"cambio")

    m.srv.al_subir = modifica
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.ARCHIVO_CAMBIO  # E-O09
    assert r.quedo_archivo is True  # el servidor lo aceptó: se avisa para que el admin lo limpie
    assert m.registro.lista()[-1].estado == EstadoTransferencia.FALLIDA


def test_ca_o09_8_el_archivo_se_trunca_a_mitad_del_envio(tmp_path):
    import os

    mundo = _Mundo(tmp_path, tam=3 * CHUNK_SUBIDA)

    def trunca():
        os.truncate(mundo.archivo, 10)

    mundo.srv.fallos["durante_subida"] = trunca
    r = mundo.subir()
    assert r.estado == EstadoTransferencia.FALLIDA and r.error.codigo == CodigoError.ARCHIVO_CAMBIO


def test_el_archivo_sin_acceso_es_un_fallo_limpio_sin_la_ruta_en_el_error(m):
    m.archivo.unlink()
    r = m.subir()
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert str(m.archivo.parent) not in repr(r.error.params) + r.error.detalle_tecnico
    assert m.posts_upload() == [] and m.registro.lista()[-1].tamano_bytes is None


# --- V-O27 / E-O23: una transferencia a la vez ----------------------------------------------------


def test_v_o27_e_o23_solo_una_transferencia_a_la_vez(m):
    dentro, seguir = threading.Event(), threading.Event()

    def detiene(_crudo):
        dentro.set()
        assert seguir.wait(5)

    m.srv.al_subir = detiene
    svc = m.servicio()
    resultado = []
    hilo = threading.Thread(target=lambda: resultado.append(m.subir(servicio=svc)))
    hilo.start()
    assert dentro.wait(5)
    assert svc.ocupado is True
    with pytest.raises(ErrorProxLaunch) as e:
        m.subir(servicio=svc)
    assert e.value.codigo == CodigoError.TRANSFERENCIA_EN_CURSO  # E-O23
    with pytest.raises(ErrorProxLaunch) as e2:  # tampoco una descarga mientras se sube
        svc.descargar(_url(), DESTINO, m.inv, checksum=None, verificar_certificados=True,
                      al_progresar=lambda p: None, dejar_de_esperar=threading.Event())  # fmt: skip
    assert e2.value.codigo == CodigoError.TRANSFERENCIA_EN_CURSO
    seguir.set()
    hilo.join(5)
    assert resultado[0].estado == EstadoTransferencia.TERMINADA and svc.ocupado is False
    assert m.subir(servicio=svc).error.codigo == CodigoError.NOMBRE_YA_EXISTE  # y se libera


def test_el_cerrojo_se_libera_aunque_la_subida_falle(m):
    svc = m.servicio()
    m.srv.fallos["durante_subida"] = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom")
    m.subir(servicio=svc)
    assert svc.ocupado is False


# --- RF-O25 y RNF-O06: registro y privacidad ------------------------------------------------------


def test_rf_o25_el_registro_de_la_sesion_guarda_nombre_storage_tamano_hora_y_volid(m):
    m.subir()
    (r,) = m.registro.lista()
    assert (r.tipo, r.nombre_archivo, r.storage, r.nodo, r.tamano_bytes) == (
        TipoTransferencia.SUBIDA, "alpine.iso", "local", "pve1", 5000,
    )  # fmt: skip
    assert (r.hora_local, r.estado, r.volid) == (
        "10:00",
        EstadoTransferencia.TERMINADA,
        "local:iso/alpine.iso",
    )
    m.registro.vaciar()
    assert m.registro.lista() == ()


def test_registro_de_sesion_es_seguro_entre_hilos():
    reg = RegistroSesion()
    from proxlaunch.nucleo.transferencias.modelos import RegistroTransferencia

    def agrega():
        for i in range(200):
            reg.agregar(
                RegistroTransferencia(
                    TipoTransferencia.SUBIDA,
                    f"a{i}.iso",
                    "s",
                    "n",
                    1,
                    "t",
                    EstadoTransferencia.TERMINADA,
                    None,
                )
            )

    hilos = [threading.Thread(target=agrega) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert len(reg.lista()) == 1600


def test_ca_o12_7_el_log_tiene_nombre_tamano_storage_nodo_duracion_y_estado_sin_ruta_ni_hash(
    m, caplog
):
    caplog.set_level(logging.DEBUG)
    m.subir()
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "alpine.iso" in texto and "storage=local" in texto and "nodo=pve1" in texto
    assert "tamano=5000" in texto and "estado=terminada" in texto
    assert str(m.archivo.parent) not in texto
    assert hashlib.sha256(m.datos).hexdigest() not in texto
    assert sin_centinelas(texto)


def test_inv_o6_la_ruta_local_no_aparece_en_ningun_resultado_ni_registro(m):
    r = m.subir()
    volcado = repr(r) + repr(m.registro.lista()) + repr(m.eventos)
    assert str(m.archivo.parent) not in volcado


# --- Descarga por URL (RF-O11) --------------------------------------------------------------------

URL = "https://dl.example.org/iso/alpine.iso"


def _url(texto=URL):
    return validar_url(texto, permitir_http=False)[0]


def _descargar(
    m, url=None, *, checksum=None, verificar=True, inv=None, dejar=None, destino=DESTINO
):
    return m.servicio().descargar(
        url or _url(),
        destino,
        inv or m.inv,
        checksum=checksum,
        verificar_certificados=verificar,
        al_progresar=m.eventos.append,
        dejar_de_esperar=dejar or threading.Event(),
    )


def test_ca_o11_1_consultar_url_pide_los_metadatos_al_servidor_y_no_abre_la_url(m):
    meta = m.servicio().consultar_url("pve1", _url())
    assert (meta.nombre, meta.tamano, meta.tipo_mime) == ("x.iso", 1000, "x/y")
    (ll,) = m.srv.llamadas_a("GET", "/query-url-metadata$")
    assert ll.params == {"url": URL, "verify-certificates": 1}
    assert set(m.srv.metodos) == {"GET"}


def test_ca_o11_1_metadatos_con_el_certificado_sin_verificar_solo_si_se_pide(m):
    m.servicio().consultar_url("pve1", _url(), verificar_certificados=False)
    assert m.srv.llamadas[-1].params["verify-certificates"] == 0


def test_ca_o11_2_un_solo_download_url_con_url_content_filename_y_verify_certificates(m):
    m.srv.metadatos = {"filename": "alpine.iso", "size": 2000, "mimetype": "x"}
    r = _descargar(m)
    assert r.estado == EstadoTransferencia.TERMINADA and r.volid == "local:iso/alpine.iso"
    (ll,) = m.srv.llamadas_a("POST", "/download-url$")
    assert ll.datos == {
        "url": URL, "content": "iso", "filename": "alpine.iso", "verify-certificates": 1,
    }  # fmt: skip
    assert "compression" not in ll.datos and "checksum" not in ll.datos


def test_ca_o11_2_con_checksum_se_envia_la_huella_y_su_algoritmo(m):
    cs, _ = validar_checksum("AB" * 32)
    _descargar(m, checksum=cs)
    (ll,) = m.srv.llamadas_a("POST", "/download-url$")
    assert ll.datos["checksum"] == "ab" * 32 and ll.datos["checksum-algorithm"] == "sha256"


def test_ca_o11_4_verificar_certificados_desmarcado_solo_si_se_pide(m):
    _descargar(m, verificar=False)
    assert m.srv.llamadas_a("POST", "/download-url$")[0].datos["verify-certificates"] == 0


def test_ca_o11_5_el_progreso_sale_del_log_de_la_tarea_si_trae_porcentaje(m):
    m.srv.log = ["Length: 2000", " 50M ... 40% 1M 1s"]
    m.srv.estados_tarea = [
        {"status": "running"},
        {"status": "running"},
        {"status": "stopped", "exitstatus": "OK"},
    ]
    m.srv.metadatos["size"] = 2000
    _descargar(m)
    con_pct = [e for e in m.eventos if e.porcentaje_servidor is not None]
    assert con_pct and con_pct[-1].porcentaje_servidor == 40.0 and con_pct[-1].total_bytes == 2000


def test_ca_o11_5_sin_porcentaje_el_estado_es_indeterminado_y_no_falla(m):
    m.srv.log = ["starting download"]
    r = _descargar(m)
    assert r.estado == EstadoTransferencia.TERMINADA
    assert all(e.porcentaje_servidor is None for e in m.eventos)


def test_ca_o11_6_verifica_el_volumen_en_el_catalogo_tras_la_tarea(m):
    m.srv.guardar_al_subir = False
    r = _descargar(m)
    assert r.error.codigo == CodigoError.TRANSFERENCIA_NO_VERIFICADA  # E-O06
    m.srv.guardar_al_subir = True
    m.srv.tamano_guardado = 1
    m.srv.contenido[("pve1", "local")].clear()
    assert _descargar(m).error.codigo == CodigoError.TRANSFERENCIA_NO_VERIFICADA


def test_ca_o11_7_e_o11_la_descarga_fallida_muestra_host_y_archivo_nunca_la_url(m):
    m.srv.estados_tarea = [
        {
            "status": "stopped",
            "exitstatus": f"download failed: 404 Not Found {URL.replace('https://', 'https://usuario-url:clave-de-la-url@')}?token=SECRETO-TOKEN-URL",
        }
    ]
    url = _url(URL + "?token=SECRETO-TOKEN-URL")
    r = _descargar(m, url)
    e = r.error
    assert r.estado == EstadoTransferencia.FALLIDA and e.codigo == CodigoError.DESCARGA_URL_FALLIDA
    assert (e.params["host"], e.params["archivo"]) == ("dl.example.org", "alpine.iso")
    volcado = repr(e.params) + e.detalle_tecnico + repr(r) + repr(m.registro.lista())
    for secreto in CENTINELAS_URL + ("https://", "http://"):
        assert secreto not in volcado, secreto


def test_ca_o11_7_checksum_incorrecto_en_la_descarga_es_e_o07(m):
    m.srv.estados_tarea = [{"status": "stopped", "exitstatus": "checksum mismatch: expected abc"}]
    cs, _ = validar_checksum("ab" * 32)
    r = _descargar(m, checksum=cs)
    assert r.error.codigo == CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA


def test_inv_o6_la_url_con_credenciales_en_la_consulta_nunca_llega_a_logs_ni_registro(m, caplog):
    caplog.set_level(logging.DEBUG)
    url = _url("https://dl.example.org/a.iso?token=SECRETO-TOKEN-URL")
    m.srv.fallos["metadatos"] = ErrorProxLaunch(
        CodigoError.DESCONOCIDO,
        {"url": "https://dl.example.org/a.iso?token=SECRETO-TOKEN-URL"},
        "GET https://dl.example.org/a.iso?token=SECRETO-TOKEN-URL fallo",
    )
    m.srv.estados_tarea = [
        {
            "status": "stopped",
            "exitstatus": "error: https://dl.example.org/a.iso?token=SECRETO-TOKEN-URL",
        }
    ]
    r = _descargar(m, url)
    todo = " ".join(rg.getMessage() for rg in caplog.records) + repr(r) + repr(m.registro.lista())
    assert "SECRETO-TOKEN-URL" not in todo


def test_ca_o11_8_dejar_de_esperar_no_cancela_la_descarga_ni_hace_nada_en_el_servidor(m):
    dejar = threading.Event()
    dejar.set()
    r = _descargar(m, dejar=dejar)
    assert r.estado == EstadoTransferencia.SIN_ESPERAR and r.error is None
    assert len(m.srv.llamadas_a("POST", "/download-url$")) == 1
    assert set(m.srv.metodos) <= {"GET", "POST"}  # nada de DELETE ni de «detener tarea»
    assert m.registro.lista()[-1].estado == EstadoTransferencia.SIN_ESPERAR


def test_ca_o10_1_inv_o2_la_descarga_tampoco_sobrescribe(m):
    m.srv.contenido[("pve1", "local")]["alpine.iso"] = (1, "iso")
    r = _descargar(m)
    assert (
        r.error.codigo == CodigoError.NOMBRE_YA_EXISTE
        and m.srv.llamadas_a("POST", "/download-url$") == []
    )


def test_ca_o10_3_la_descarga_comprueba_el_espacio_con_el_tamano_que_ve_el_servidor(tmp_path):
    mundo = _Mundo(tmp_path, libre=10 * MIB)
    mundo.srv.metadatos["size"] = 20 * MIB
    r = _descargar(mundo)
    assert r.error.codigo == CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA
    assert mundo.srv.llamadas_a("POST", "/download-url$") == []


def test_la_descarga_sin_tamano_conocido_no_se_bloquea_por_espacio(tmp_path):
    mundo = _Mundo(tmp_path, libre=1)
    mundo.srv.metadatos.pop("size")
    mundo.srv.fallos["metadatos"] = ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "sin metadatos")
    r = _descargar(mundo)
    assert r.error is None or r.error.codigo != CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA


def test_la_descarga_no_mira_la_raiz_del_nodo(m):
    _descargar(m)
    assert m.srv.llamadas_a("GET", r"^/nodes/pve1/status$") == []


@pytest.mark.parametrize("version", ["8.2.1", "9.2.0"])
def test_v_o16_desde_8_2_hace_falta_sys_access_network_o_sys_modify(tmp_path, version):
    mayor, menor = (int(x) for x in version.split(".")[:2])
    v = Version(version, mayor, menor, 0)
    m = _Mundo(tmp_path, version=v)
    sin = inv_origen(version=v, permisos_efectivos=permisos(quitar=("Sys.AccessNetwork",)))
    r = _descargar(m, inv=sin)
    assert r.error.codigo == CodigoError.DESCARGA_URL_SIN_PERMISO  # E-O03
    assert r.error.params["privilegio"] == "Sys.AccessNetwork" and r.error.params["nodo"] == "pve1"
    assert m.srv.llamadas_a("POST", "/download-url$") == []
    admin = inv_origen(
        version=v,
        permisos_efectivos=permisos(ROL_MVP3 + ("Datastore.AllocateTemplate", "Sys.Modify")),
    )
    assert _descargar(m, inv=admin).estado == EstadoTransferencia.TERMINADA


@pytest.mark.parametrize("version", ["8.0.4", "8.1.2"])
def test_v_o16_en_8_0_y_8_1_solo_vale_sys_modify_y_nunca_se_pide(tmp_path, version):
    mayor, menor = (int(x) for x in version.split(".")[:2])
    v = Version(version, mayor, menor, 0)
    m = _Mundo(tmp_path, version=v)
    r = _descargar(m, inv=inv_origen(version=v))  # rol de 14 sin Sys.Modify
    assert r.error.codigo == CodigoError.DESCARGA_URL_SIN_PERMISO
    assert r.error.params["privilegio"] == "Sys.Modify"


def test_la_descarga_exige_allocate_template_en_el_storage(m):
    inv = inv_origen(permisos_efectivos=permisos(quitar=("Datastore.AllocateTemplate",)))
    r = _descargar(m, inv=inv)
    assert r.error.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert r.error.params["via"] == "descargar_url"


def test_no_hay_ninguna_escritura_distinta_de_upload_y_download_url(m):
    m.subir()
    _descargar(m, dejar=_set())
    escrituras = [c for c in m.srv.llamadas if c.metodo != "GET"]
    assert {c.ruta.rsplit("/", 1)[-1] for c in escrituras} <= {"upload", "download-url"}


def _set():
    ev = threading.Event()
    ev.set()
    return ev


# --- Transporte HTTP real (con `responses`) y cliente ---------------------------------------------


def _transporte_http(auth=None):
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
    from proxlaunch.nucleo.api.transporte import TransporteHttp
    from proxlaunch.nucleo.modelos.conexion import CredencialToken

    from .apoyo_api import HUELLA_A, TOKEN_ID, TOKEN_SECRETO

    t = TransporteHttp(["10.0.0.1"], 8006, huellas={"10.0.0.1": HUELLA_A})
    t.usar_autenticador(auth or AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)))
    return t


def _cuerpo_http(datos=b"HOLA", cancelado=None):
    import io

    from proxlaunch.nucleo.api.multipart import CuerpoMultipart, ParteArchivo

    return CuerpoMultipart(
        {"content": "iso"},
        ParteArchivo("a.iso", len(datos), io.BytesIO(datos)),
        cancelado=cancelado,
    )


RUTA_UPLOAD = "/nodes/pve1/storage/local/upload"


def test_ca_o09_10_la_subida_real_envia_content_length_exacto_multipart_y_autenticacion(rsps):
    import json

    from .apoyo_api import url

    visto = {}

    def cb(request):
        visto["cab"] = dict(request.headers)
        visto["cuerpo"] = b"".join(request.body)
        return 200, {}, json.dumps({"data": ServidorArchivos.UPID})

    rsps.add_callback("POST", url("10.0.0.1", RUTA_UPLOAD), callback=cb)
    cuerpo = _cuerpo_http(b"DATOS-DEL-ISO")
    assert (
        _transporte_http().subir(RUTA_UPLOAD, cuerpo, timeout_lectura=120) == ServidorArchivos.UPID
    )
    cab = visto["cab"]
    assert int(cab["Content-Length"]) == len(visto["cuerpo"]) == len(cuerpo)
    assert cab["Content-Type"].startswith("multipart/form-data; boundary=")
    assert cab["Authorization"].startswith("PVEAPIToken=")
    assert "Transfer-Encoding" not in cab  # Proxmox rechaza la subida sin Content-Length
    assert b"DATOS-DEL-ISO" in visto["cuerpo"]


def test_ca_o09_9_con_ticket_la_subida_lleva_cookie_y_csrf_prevention_token(rsps):
    import json

    from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket, Ticket

    from .apoyo_api import url

    visto = {}

    def cb(request):
        visto["cab"] = dict(request.headers)
        b"".join(request.body)
        return 200, {}, json.dumps({"data": ServidorArchivos.UPID})

    rsps.add_callback("POST", url("10.0.0.1", RUTA_UPLOAD), callback=cb)
    auth = AutenticadorTicket(Ticket("TICKET-X", "CSRF-X", "ana@pve", 0.0), RelojSeguro())
    _transporte_http(auth).subir(RUTA_UPLOAD, _cuerpo_http(), timeout_lectura=120)
    assert visto["cab"]["CSRFPreventionToken"] == "CSRF-X"
    assert "PVEAuthCookie=TICKET-X" in visto["cab"]["Cookie"]


def test_ca_o09_7_un_corte_de_conexion_en_la_subida_real_no_se_reintenta(rsps):
    import requests

    from .apoyo_api import url

    rsps.add(
        "POST", url("10.0.0.1", RUTA_UPLOAD), body=requests.exceptions.ConnectionError("reset")
    )
    with pytest.raises(ErrorProxLaunch) as e:
        _transporte_http().subir(RUTA_UPLOAD, _cuerpo_http(), timeout_lectura=120)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE and e.value.params["incierto"] == "1"
    assert len(rsps.calls) == 1


def test_un_596_en_la_subida_real_es_envio_incierto_sin_failover(rsps):
    from .apoyo_api import url

    rsps.add("POST", url("10.0.0.1", RUTA_UPLOAD), status=596)
    with pytest.raises(ErrorProxLaunch) as e:
        _transporte_http().subir(RUTA_UPLOAD, _cuerpo_http(), timeout_lectura=120)
    assert e.value.params["incierto"] == "1" and len(rsps.calls) == 1


def test_la_cancelacion_en_la_subida_real_es_transferencia_cancelada(rsps):
    from .apoyo_api import url

    ev = threading.Event()
    ev.set()

    def cb(request):
        b"".join(request.body)
        return 200, {}, "{}"

    rsps.add_callback("POST", url("10.0.0.1", RUTA_UPLOAD), callback=cb)
    with pytest.raises(ErrorProxLaunch) as e:
        _transporte_http().subir(RUTA_UPLOAD, _cuerpo_http(cancelado=ev), timeout_lectura=120)
    assert e.value.codigo == CodigoError.TRANSFERENCIA_CANCELADA


def test_la_subida_real_exige_huella_confiada_y_no_abre_otra_conexion():
    from proxlaunch.nucleo.api.transporte import TransporteHttp

    t = TransporteHttp(["10.0.0.1"], 8006, huellas={})
    with pytest.raises(ErrorProxLaunch) as e:
        t.subir(RUTA_UPLOAD, _cuerpo_http(), timeout_lectura=120)
    assert e.value.codigo == CodigoError.HUELLA_NO_CONFIADA


def test_el_transporte_de_solo_lectura_rechaza_las_subidas_en_simulacion():
    from proxlaunch.nucleo.api.solo_lectura import TransporteSoloLectura

    ro = TransporteSoloLectura(_transporte_http())
    with pytest.raises(ErrorProxLaunch) as e:
        ro.subir(RUTA_UPLOAD, _cuerpo_http(), timeout_lectura=120)
    assert e.value.codigo == CodigoError.ESCRITURA_EN_SIMULACION


def test_el_cliente_exige_un_transporte_con_subida_y_un_contenido_de_archivo():
    import io

    from proxlaunch.nucleo.api.multipart import ParteArchivo

    from .apoyo_api import TransporteFalso

    sesion = crear_sesion(TransporteFalso())
    parte = ParteArchivo("a.iso", 1, io.BytesIO(b"x"))
    with pytest.raises(TypeError):
        sesion.cliente.subir_archivo("pve1", "local", Contenido.ISO, parte, "ab" * 32)
    sesion2 = crear_sesion(ServidorArchivos())
    with pytest.raises(ValueError):
        sesion2.cliente.subir_archivo("pve1", "local", Contenido.IMAGENES, parte, "ab" * 32)
    with pytest.raises(ValueError):
        sesion2.cliente.descargar_url(
            "pve1", "local", url=_url(), contenido=Contenido.IMAGENES, nombre="a.iso", checksum=None
        )


def test_el_cliente_sin_upid_en_la_respuesta_de_la_subida_da_upid_invalido():
    import io

    from proxlaunch.nucleo.api.multipart import ParteArchivo

    srv = ServidorArchivos()
    srv.UPID = "no es un upid"
    sesion = crear_sesion(srv)
    with pytest.raises(ErrorProxLaunch) as e:
        sesion.cliente.subir_archivo(
            "pve1", "local", Contenido.ISO, ParteArchivo("a.iso", 1, io.BytesIO(b"x")), "ab" * 32
        )
    assert e.value.codigo == CodigoError.UPID_INVALIDO


def test_contenido_storage_marca_admitido_y_conserva_los_no_admitidos_deshabilitados():
    srv = ServidorArchivos()

    def listado(llamada):
        return [
            {"volid": "local:iso/alpine.iso", "size": 10, "ctime": 5},
            {"volid": "local:iso/con espacio.iso", "size": 1},
            {"volid": "local:iso/x.iso,media=disk", "size": 1},
            {"volid": "local:iso/virus.exe", "size": 1},
            {"volid": 5},
            "basura",
            {"volid": "sin_barra"},
            {"volid": "local:iso/sin_tamano.iso"},
        ]

    srv.peticion = lambda metodo, ruta, **kw: listado(None)  # type: ignore[method-assign]
    sesion = crear_sesion(srv)
    vols = sesion.cliente.contenido_storage("pve1", "local", Contenido.ISO)
    por_volid = {v.volid: v for v in vols}
    assert por_volid["local:iso/alpine.iso"].admitido is True
    assert (
        por_volid["local:iso/alpine.iso"].tamano_bytes == 10
        and por_volid["local:iso/alpine.iso"].nombre == "alpine.iso"
    )
    for malo in ("local:iso/con espacio.iso", "local:iso/x.iso,media=disk", "local:iso/virus.exe"):
        assert por_volid[malo].admitido is False  # INV-O7: nunca llegará a un parámetro
    assert por_volid["local:iso/sin_tamano.iso"].tamano_bytes is None
    assert len(vols) == 5


def test_el_cliente_pide_el_contenido_con_el_parametro_content():
    srv = ServidorArchivos()
    crear_sesion(srv).cliente.contenido_storage("pve1", "local", Contenido.IMPORT)
    (ll,) = srv.llamadas_a("GET", "/content$")
    assert ll.params == {"content": "import"} and ll.ruta == "/nodes/pve1/storage/local/content"
