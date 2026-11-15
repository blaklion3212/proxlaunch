"""MVP 4, F7: pruebas de las correcciones de la revisión QA y de seguridad (núcleo).

Derivadas de los requisitos y de las interfaces públicas (docs/requisitos/mvp4.md); un bloque por
hallazgo (QA-M4-xx / SEG-M4-xx). Todo con dobles: sin red, sin servidor real.
SEG-M4-02 (virtio-win exacto, V-O31) y QA-M4-05 (fuente_vigente) están en test_mvp4_catalogo.py.
"""

import dataclasses
import threading
from pathlib import Path

import pytest

from proxlaunch.nucleo.csv_importacion.errores_csv import escribir_filas_con_error
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.cupos import ClaseCarga, CuposEjecucion, clase_de, nodo_de_cupo
from proxlaunch.nucleo.lote.modelos import ElementoPlan
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.presupuesto import pedido_vm
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    ModoClon,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import Disco
from proxlaunch.nucleo.origen.clon import construir_ajustes_clon, detalle_de_config
from proxlaunch.nucleo.origen.nombres import parece_url_o_credenciales
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.servicios.catalogo import fuente_vigente
from proxlaunch.nucleo.servicios.creacion import Desenlace
from proxlaunch.nucleo.transferencias import servicio as modulo_servicio
from proxlaunch.nucleo.transferencias.archivo_local import (
    abrir_para_subir,
    comprobar_cabecera_abierto,
)
from proxlaunch.nucleo.transferencias.modelos import DestinoTransferencia, EstadoTransferencia
from proxlaunch.nucleo.transferencias.url import URL_CARACTERES, url_saneada, validar_url

from .apoyo_api import crear_sesion
from .apoyo_lote import GIB, NORMAL, TransporteCluster
from .apoyo_mvp3 import importar_csv, tabla_csv
from .apoyo_mvp4 import (
    VOLID_ISO,
    VOLID_VIRTIO,
    ClusterM4,
    cfg_clon,
    cfg_import,
    cfg_iso,
    detalle_plantilla,
    disco_plantilla,
    inv_origen,
    plantilla_pve,
)
from .test_mvp4_clon import _Mundo as MundoClon
from .test_mvp4_transferencias import DESTINO, _descargar, _Mundo

MIB = 1024**2


@pytest.fixture
def m(tmp_path):
    return _Mundo(tmp_path)


# --- QA-M4-01: dejar de esperar antes del POST download-url --------------------------------------


@pytest.mark.parametrize("punto", ["metadatos", "storages", "contenido"])
def test_qa_m4_01_dejar_de_esperar_tras_cada_get_previo_no_envia_el_post(m, punto):
    dejar = threading.Event()
    m.srv.fallos[punto] = dejar.set  # se activa cuando se atiende ese GET previo
    r = _descargar(m, dejar=dejar)
    assert r.estado == EstadoTransferencia.CANCELADA
    assert r.quedo_archivo is False
    assert m.srv.llamadas_a("POST", "/download-url$") == []
    assert m.registro.lista()[-1].estado == EstadoTransferencia.CANCELADA


def test_qa_m4_01_sin_cancelar_el_post_se_envia_una_sola_vez(m):
    r = _descargar(m)
    assert r.estado == EstadoTransferencia.TERMINADA
    assert len(m.srv.llamadas_a("POST", "/download-url$")) == 1


# --- QA-M4-02: cancelar con el cuerpo ya enviado -------------------------------------------------


def test_qa_m4_02_cancelar_esperando_al_servidor_es_sin_esperar_sin_afirmar_nada(m):
    consultas = {}

    def cancela():
        consultas["content_antes"] = len(m.srv.llamadas_a("GET", "/content$"))
        m.cancelado.set()

    m.srv.fallos["estado_tarea"] = cancela
    r = m.subir()
    assert r.estado == EstadoTransferencia.SIN_ESPERAR
    assert r.quedo_archivo is None  # ni «sí» ni «no»: la copia sigue en el servidor
    assert r.upid == m.srv.UPID and r.error is None
    # no se consultó el catálogo para afirmar nada tras cancelar
    assert len(m.srv.llamadas_a("GET", "/content$")) == consultas["content_antes"]
    assert m.registro.lista()[-1].estado == EstadoTransferencia.SIN_ESPERAR


def test_qa_m4_02_cancelar_con_todo_el_cuerpo_ya_entregado_tambien_es_sin_esperar(m):
    # 5000 bytes caben en un solo trozo: el 1.º es la cabecera, el 2.º el archivo entero y el
    # 3.º el cierre. Se cancela justo tras entregar el archivo completo (hechos >= tamaño).
    llamadas = []

    def cancela_tras_el_archivo():
        llamadas.append(1)
        if len(llamadas) == 2:
            m.cancelado.set()

    m.srv.fallos["durante_subida"] = cancela_tras_el_archivo
    r = m.subir()
    assert r.estado == EstadoTransferencia.SIN_ESPERAR and r.quedo_archivo is None


def test_qa_m4_02_cancelar_a_mitad_del_envio_sigue_siendo_cancelada_y_mira_el_catalogo(m):
    m.srv.fallos["durante_subida"] = lambda: m.cancelado.set()
    r = m.subir()
    assert r.estado == EstadoTransferencia.CANCELADA and r.quedo_archivo is False


def test_qa_m4_02_archivo_cambio_con_upid_afirma_quedo_true_solo_si_esta_en_el_catalogo(m):
    def modifica(_):
        with open(m.archivo, "ab") as f:
            f.write(b"cambio")

    m.srv.al_subir = modifica
    r = m.subir()
    assert r.error.codigo == CodigoError.ARCHIVO_CAMBIO and r.upid == m.srv.UPID
    assert r.quedo_archivo is True  # el servidor ya lo tiene en el catálogo


def test_qa_m4_02_archivo_cambio_con_upid_y_sin_el_archivo_en_el_catalogo_es_none(m):
    def modifica(_):
        with open(m.archivo, "ab") as f:
            f.write(b"cambio")

    m.srv.guardar_al_subir = False  # todavía no aparece: un «no» sería prematuro
    m.srv.al_subir = modifica
    r = m.subir()
    assert r.error.codigo == CodigoError.ARCHIVO_CAMBIO and r.upid == m.srv.UPID
    assert r.quedo_archivo is None


# --- QA-M4-06 (núcleo): drivers solo si el SO los usa y no «sin drivers» -------------------------


def test_qa_m4_06_fuente_vigente_no_revalida_drivers_de_un_so_sin_drivers():
    cl = ClusterM4(("pve1",))
    cl.contenido[("pve1", "local")] = [VOLID_ISO]  # el virtio ya no está
    sesion = crear_sesion(TransporteCluster(cl))
    linux = cfg_iso(tipo_so=TipoSO.LINUX, drivers=VOLID_VIRTIO)
    assert fuente_vigente(sesion.cliente, linux) is None
    win = cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers=VOLID_VIRTIO)
    assert fuente_vigente(sesion.cliente, win).params["tipo"] == "drivers"


def test_qa_m4_06_la_resolucion_no_conserva_drivers_de_un_so_que_no_los_usa():
    inv = inv_origen()
    cfg = cfg_iso(tipo_so=TipoSO.LINUX, drivers="local:iso/virtio-win-0.1.1.iso")
    res, problemas = resolver_origen(cfg, inv, "pve1")
    assert res.detalle_origen.drivers is None
    assert not [p for p in problemas if p.campo.startswith("detalle_origen.drivers")]


# --- QA-M4-07: balloon y vcpus del clon ----------------------------------------------------------


def _plant(**kw):
    return dataclasses.replace(detalle_plantilla(), **kw)


def _ajustes(plantilla, **a):
    cfg = cfg_clon("base", 9000, "pve1", ajustes=AjustesClon(**a))
    return construir_ajustes_clon(cfg, plantilla, ()).config


def test_qa_m4_07_el_detalle_de_la_plantilla_lee_balloon_y_vcpus():
    det = detalle_de_config({"memory": 4096, "balloon": "2048", "vcpus": 2, "cores": 4})
    assert (det.balloon, det.vcpus) == (2048, 2)
    vacio = detalle_de_config({"memory": 4096})
    assert (vacio.balloon, vacio.vcpus) == (None, None)


def test_qa_m4_07_memoria_menor_que_el_balloon_baja_tambien_el_balloon():
    config = _ajustes(_plant(memoria_mib=4096, balloon=2048), memoria_mib=1024)
    assert config == {"memory": "1024", "balloon": "1024"}


@pytest.mark.parametrize(
    "balloon,memoria",
    [(2048, 2048), (2048, 3072), (0, 1024), (None, 1024)],
    ids=["igual", "mayor", "balloon-desactivado", "sin-balloon"],
)
def test_qa_m4_07_sin_conflicto_no_se_envia_balloon(balloon, memoria):
    config = _ajustes(_plant(memoria_mib=4096, balloon=balloon), memoria_mib=memoria)
    assert config == {"memory": str(memoria)}


def test_qa_m4_07_menos_nucleos_que_los_vcpus_baja_tambien_los_vcpus():
    config = _ajustes(_plant(cores=4, sockets=1, vcpus=4), cores=2)
    assert config == {"cores": "2", "vcpus": "2"}


def test_qa_m4_07_vcpus_con_sockets_nuevos_usa_sockets_por_cores():
    config = _ajustes(_plant(cores=2, sockets=2, vcpus=4), sockets=1)
    assert config == {"sockets": "1", "vcpus": "2"}


@pytest.mark.parametrize("vcpus", [None, 2, 1])
def test_qa_m4_07_si_los_nucleos_nuevos_alcanzan_los_vcpus_no_se_envian(vcpus):
    config = _ajustes(_plant(cores=2, sockets=1, vcpus=vcpus), cores=4)
    assert config == {"cores": "4"}


@pytest.mark.parametrize(
    "config,ajustes,esperado",
    [
        ({"cores": 4, "vcpus": 4, "memory": 512}, {"cores": 2}, {"cores": "2", "vcpus": "2"}),
        ({"sockets": 2, "vcpus": 2, "memory": 512}, {"sockets": 1}, {"sockets": "1", "vcpus": "1"}),
    ],
    ids=["sockets-ausente", "cores-ausente"],
)
def test_defecto_f7_01_vcpus_con_sockets_o_cores_ausentes_en_la_config_de_la_plantilla(
    config, ajustes, esperado
):
    plantilla = detalle_de_config(config)
    assert _ajustes(plantilla, **ajustes) == esperado


def test_qa_m4_07_clon_completo_ajusta_memoria_y_balloon_y_queda_ok_sin_parcial():
    mundo = MundoClon(memory=4096, balloon=2048, cores=4, sockets=1, vcpus=4)

    def valida(ll):
        # El servidor real rechaza balloon > memory y vcpus > sockets*cores.
        vm = mundo.cl.vms[100]["config"]
        nuevo = {**vm, **(ll.datos or {})}
        if int(nuevo.get("balloon", 0)) > int(nuevo["memory"]):
            raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "balloon > memory")
        if int(nuevo.get("vcpus", 0)) > int(nuevo["sockets"]) * int(nuevo["cores"]):
            raise ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "vcpus > cores")
        return NORMAL

    mundo.cl.regla("PUT", r"/config$", valida)
    cfg = mundo.cfg(ajustes=AjustesClon(memoria_mib=1024, cores=2))
    r = mundo.crear(cfg)
    assert r.desenlace == Desenlace.OK, (r.desenlace, r.error)
    (put,) = mundo.put("config")
    assert put[3]["memory"] == "1024" and put[3]["balloon"] == "1024"
    assert put[3]["cores"] == "2" and put[3]["vcpus"] == "2"
    assert mundo.cl.vms[100]["config"]["balloon"] == "1024"


def test_qa_m4_07_la_puerta_del_servidor_si_rechaza_sin_la_correccion():
    """La regla de validación de la prueba anterior detecta el PUT sin corrección."""
    mundo = MundoClon(memory=4096, balloon=2048)
    mundo.cl.regla(
        "PUT",
        r"/config$",
        lambda ll: (
            (_ for _ in ()).throw(ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "x"))
            if int((ll.datos or {}).get("memory", 4096)) < 2048
            and "balloon" not in (ll.datos or {})
            else NORMAL
        ),
    )
    r = mundo.crear(mundo.cfg(ajustes=AjustesClon(memoria_mib=1024)))
    assert r.desenlace == Desenlace.OK  # con la corrección envía balloon y el servidor acepta


# --- QA-M4-08: tope de enlazados en el nodo de la plantilla --------------------------------------


def _elem(vmid, nodo, cfg):
    return ElementoPlan(
        vmid - 100, f"vm-{vmid}", vmid, nodo, dataclasses.replace(cfg, nodo=nodo, vmid=vmid)
    )


def _enlazado(nodo_plantilla="pve1"):
    return cfg_clon("base", 9000, nodo_plantilla, efectivo=ModoClon.ENLAZADO)


def test_qa_m4_08_nodo_de_cupo_del_enlazado_es_el_de_la_plantilla():
    e = _elem(100, "pve2", _enlazado("pve1"))
    assert clase_de(e.cfg) == ClaseCarga.LIGERA
    assert nodo_de_cupo(e) == "pve1"


def test_qa_m4_08_sin_nodo_de_plantilla_se_usa_el_destino():
    e = _elem(100, "pve2", _enlazado(None))
    assert nodo_de_cupo(e) == "pve2"


@pytest.mark.parametrize(
    "cfg",
    [
        cfg_clon("base", 9000, "pve1", efectivo=ModoClon.COMPLETO),
        cfg_iso(),
    ],
    ids=["clon-completo", "iso"],
)
def test_qa_m4_08_lo_que_no_es_enlazado_cuenta_en_el_destino(cfg):
    assert nodo_de_cupo(_elem(100, "pve2", cfg)) == "pve2"


def test_qa_m4_08_enlazados_a_destinos_distintos_comparten_el_tope_de_la_plantilla():
    cupos = CuposEjecucion(inv_origen(), por_nodo=3)
    control = ControlLote()
    elems = [_elem(100 + i, f"pve{1 + i % 2}", _enlazado("pve1")) for i in range(4)]
    assert all(cupos.adquirir(e, control) for e in elems[:3])
    resultado: list[bool] = []
    hilo = threading.Thread(target=lambda: resultado.append(cupos.adquirir(elems[3], control)))
    hilo.start()
    hilo.join(0.3)
    assert hilo.is_alive() and not resultado  # el cuarto espera aunque su destino tenga hueco
    cupos.liberar(elems[0])
    hilo.join(3)
    assert resultado == [True]
    for e in elems[1:]:
        cupos.liberar(e)


def test_qa_m4_08_dos_pesados_por_storage_destino_siguen_igual():
    inv = inv_origen(nodos=("pve1", "pve2", "pve3"))
    cupos = CuposEjecucion(inv, por_nodo=3, pesadas_por_storage=2)
    control = ControlLote()
    cfg = cfg_import(cfg={"discos": [Disco("nfs1", 8)]})  # importación hacia un storage compartido
    elems = [_elem(100 + i, f"pve{1 + i}", cfg) for i in range(3)]
    assert all(clase_de(e.cfg) == ClaseCarga.PESADA for e in elems)
    assert [nodo_de_cupo(e) for e in elems] == ["pve1", "pve2", "pve3"]  # el destino
    assert cupos.adquirir(elems[0], control) and cupos.adquirir(elems[1], control)
    resultado: list[bool] = []
    hilo = threading.Thread(target=lambda: resultado.append(cupos.adquirir(elems[2], control)))
    hilo.start()
    hilo.join(0.3)
    assert hilo.is_alive() and not resultado  # el 3.º hacia el mismo storage espera
    cupos.liberar(elems[0])
    hilo.join(3)
    assert resultado == [True]
    cupos.liberar(elems[1])
    cupos.liberar(elems[2])


# --- QA-M4-11: adquirir no suelta el turno si devuelve False -------------------------------------


def test_qa_m4_11_tras_un_false_el_elemento_conserva_su_turno_original():
    cupos = CuposEjecucion(inv_origen(), por_nodo=1)
    control = ControlLote()
    a, b, c = (_elem(100 + i, "pve1", cfg_iso()) for i in range(3))
    assert cupos.adquirir(a, control)
    cupos.encolar(b)
    cupos.encolar(c)
    cancelado = ControlLote()
    cancelado.cancelar()
    assert cupos.adquirir(b, cancelado) is False  # b abandona la espera (p. ej. pausa)
    cupos.liberar(a)
    resultado_c: list[bool] = []
    hc = threading.Thread(target=lambda: resultado_c.append(cupos.adquirir(c, control)))
    hc.start()
    hc.join(0.3)
    assert hc.is_alive() and not resultado_c  # c no adelanta a b: b conserva el turno 1
    assert cupos.adquirir(b, control) is True
    cupos.liberar(b)
    hc.join(3)
    assert resultado_c == [True]
    cupos.liberar(c)


def test_qa_m4_11_descartar_si_libera_el_turno_para_los_demas():
    cupos = CuposEjecucion(inv_origen(), por_nodo=1)
    control = ControlLote()
    a, b, c = (_elem(100 + i, "pve1", cfg_iso()) for i in range(3))
    assert cupos.adquirir(a, control)
    cupos.encolar(b)
    cupos.encolar(c)
    cupos.descartar(b)
    cupos.liberar(a)
    assert cupos.adquirir(c, control) is True


# --- QA-M4-12: el presupuesto usa el disco principal del resize ----------------------------------


def test_qa_m4_12_el_presupuesto_amplia_el_scsi0_y_no_el_primero_de_la_lista():
    discos = [disco_plantilla("ide0", "local-lvm", 30), disco_plantilla("scsi0", "local-lvm", 8)]
    inv = inv_origen(plantillas=(plantilla_pve(detalle=detalle_plantilla(discos)),))
    cfg, _ = resolver_origen(
        cfg_clon("base", modo=ModoClon.COMPLETO, ajustes=AjustesClon(disco_gib=50)), inv, "pve1"
    )
    pedido = {(k.ambito, k.storage): v for k, v in pedido_vm(cfg, inv).items()}
    # scsi0 (principal) crece de 8 a 50 GiB; ide0 queda en 30.
    assert pedido == {("pve1", "local-lvm"): 80 * GIB}


@pytest.mark.parametrize(
    "claves,principal",
    [
        (("sata0", "virtio0"), "virtio0"),
        (("ide0", "sata0"), "sata0"),
        (("ide0", "virtio0", "scsi0"), "scsi0"),
    ],
)
def test_qa_m4_12_prioridad_scsi0_virtio0_sata0_ide0(claves, principal):
    discos = [disco_plantilla(c, "local-lvm", 10) for c in claves]
    inv = inv_origen(plantillas=(plantilla_pve(detalle=detalle_plantilla(discos)),))
    cfg, _ = resolver_origen(
        cfg_clon("base", modo=ModoClon.COMPLETO, ajustes=AjustesClon(disco_gib=40)), inv, "pve1"
    )
    pedido = sum(pedido_vm(cfg, inv).values())
    assert pedido == (40 + 10 * (len(claves) - 1)) * GIB, principal


# --- QA-M4-10 / SEG-M4-06: OSError del disco -----------------------------------------------------


class _FlujoQueFalla:
    """Envuelve el flujo real y lanza ``OSError`` (con la ruta en el texto) cuando está armado."""

    def __init__(self, real, ruta, armado):
        self._real, self._ruta, self.armado = real, ruta, armado

    def read(self, *a):
        if self.armado():
            raise OSError(5, f"fallo de E/S en {self._ruta}")
        return self._real.read(*a)

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def _con_flujo_roto(monkeypatch, ruta: Path, armado):
    original = modulo_servicio.abrir_para_subir

    def abrir(r):
        archivo = original(r)
        archivo._flujo = _FlujoQueFalla(archivo._flujo, str(ruta), armado)
        return archivo

    monkeypatch.setattr(modulo_servicio, "abrir_para_subir", abrir)


def _comprueba_no_accesible(m, r):
    assert r.estado == EstadoTransferencia.FALLIDA
    e = r.error
    assert e.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert e.params == {"archivo": "alpine.iso", "motivo": "otro"}
    assert e.__cause__ is None  # from None: sin el OSError (y su ruta) encadenado
    volcado = repr(e.params) + e.detalle_tecnico + repr(r) + repr(m.registro.lista())
    assert str(m.archivo.parent) not in volcado
    assert m.registro.lista()[-1].estado == EstadoTransferencia.FALLIDA


def test_qa_m4_10_oserror_al_calcular_la_huella_es_archivo_no_accesible(m, monkeypatch):
    _con_flujo_roto(monkeypatch, m.archivo, lambda: True)
    r = m.subir()
    _comprueba_no_accesible(m, r)
    assert m.posts_upload() == []


def test_qa_m4_10_oserror_durante_el_envio_es_archivo_no_accesible_no_corte_de_red(m, monkeypatch):
    estado = {"envio": False}
    _con_flujo_roto(monkeypatch, m.archivo, lambda: estado["envio"])

    def al_progresar(p):
        m.eventos.append(p)
        if p.estado == EstadoTransferencia.TRANSFIRIENDO:
            estado["envio"] = True

    r = m.servicio().subir(
        m.archivo, DESTINO, m.inv, al_progresar=al_progresar, cancelado=m.cancelado,
        acepta_aviso_raiz=False,
    )  # fmt: skip
    _comprueba_no_accesible(m, r)
    assert r.error.codigo != CodigoError.TRANSFERENCIA_CORTADA


# --- SEG-M4-03: caracteres de control y host con «%» en la URL -----------------------------------


@pytest.mark.parametrize(
    "codificado",
    ["%E2%80%AE", "%0A", "%00", "%1B", "%C2%85"],
    ids=["rlo-cf", "salto-linea", "nul", "escape", "nel-c1"],
)
def test_seg_m4_03_controles_y_formato_codificados_en_el_archivo_pasan_a_guion_bajo(codificado):
    url, motivo = validar_url(f"https://dl.example.org/iso/a{codificado}b.iso", permitir_http=False)
    assert motivo is None
    assert url.archivo == "a_b.iso"
    assert all(ord(c) >= 32 and ord(c) != 0x202E for c in url.archivo)
    assert "%" not in repr(url)


def test_seg_m4_03_el_host_con_porcentaje_se_rechaza():
    url, motivo = validar_url("https://dl%2Eexample.org/a.iso", permitir_http=False)
    assert url is None and motivo == URL_CARACTERES


def test_seg_m4_03_url_saneada_nunca_lleva_controles_y_con_host_raro_es_url():
    assert url_saneada("https://ho%73t.example.org/a.iso") == "(url)"
    limpio = url_saneada("https://dl.example.org/x%E2%80%AEy.iso?token=SECRETO")
    assert "SECRETO" not in limpio and "‮" not in limpio and "x_y.iso" in limpio
    assert url_saneada("https://dl.example.org/a%0Ab.iso") == "dl.example.org/a_b.iso"


# --- SEG-M4-04: el núcleo valida el destino de subir/descargar -----------------------------------


@pytest.mark.parametrize(
    "cambios,campo",
    [
        ({"nombre_archivo": "../x.iso"}, "nombre_archivo"),
        ({"nombre_archivo": "a b.iso"}, "nombre_archivo"),
        ({"nombre_archivo": "malo.exe"}, "nombre_archivo"),
        ({"nombre_archivo": ""}, "nombre_archivo"),
        ({"storage": "lo cal"}, "storage"),
        ({"storage": "local/../x"}, "storage"),
        ({"storage": "a;b"}, "storage"),
        ({"nodo": "pve1/../x"}, "nodo"),
        ({"nodo": "pve 1"}, "nodo"),
        ({"nodo": ""}, "nodo"),
    ],
)
def test_seg_m4_04_destino_invalido_es_parametro_invalido_sin_tocar_la_red(m, cambios, campo):
    # Hallazgo de la prueba: el servicio LANZA la excepción (no devuelve un resultado FALLIDA)
    # y lo hace antes de tomar el cerrojo de «una transferencia a la vez» y de abrir nada.
    destino = dataclasses.replace(DESTINO, **cambios)
    with pytest.raises(ErrorProxLaunch) as ex_subir:
        m.subir(destino)
    with pytest.raises(ErrorProxLaunch) as ex_descargar:
        _descargar(m, destino=destino)
    for ex in (ex_subir, ex_descargar):
        assert ex.value.codigo == CodigoError.PARAMETRO_INVALIDO
        assert ex.value.params["campo"] == campo
    assert m.srv.llamadas == []  # ni una sola llamada al servidor
    assert m.registro.lista() == ()  # y no se registró nada
    assert m.subir().estado == EstadoTransferencia.TERMINADA  # el cerrojo no quedó tomado


@pytest.mark.parametrize("contenido", [Contenido.ISO, Contenido.IMPORT])
def test_seg_m4_04_un_destino_correcto_sigue_funcionando(m, contenido):
    ok = DestinoTransferencia("pve1", "local", Contenido.ISO, "alpine-3.19_x86.iso")
    assert m.subir(ok).estado == EstadoTransferencia.TERMINADA
    assert contenido  # parametrizado solo para documentar los dos contenidos admitidos


# --- SEG-M4-05: celdas «fuente» con «@» o «//» ---------------------------------------------------


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("usuario:clave@x.org/a.iso", True),
        ("//x.org/a.iso", True),
        ("  //x.org/a.iso", True),
        ("a@b", True),
        ("https://x.org/a.iso", True),
        ("www.x.org/a.iso", True),
        ("alpine.iso", False),
        ("local:iso/alpine.iso", False),
        ("", False),
    ],
)
def test_seg_m4_05_parece_url_o_credenciales(texto, esperado):
    assert parece_url_o_credenciales(texto) is esperado


def test_seg_m4_05_parece_url_o_credenciales_con_no_texto_es_false():
    assert parece_url_o_credenciales(None) is False  # type: ignore[arg-type]
    assert parece_url_o_credenciales(123) is False  # type: ignore[arg-type]


ENC = "nombre;origen;fuente;so;virtio;modo_clon;cpu;memoria;disco"
SECRETOS = ("clave-secreta", "T0K3N", "usuario-url")


@pytest.mark.parametrize(
    "celda,visible",
    [
        ("usuario-url:clave-secreta@x.org/a.iso?token=T0K3N", "(url)"),
        ("//usuario-url:clave-secreta@x.org/a.iso", "x.org/a.iso"),
    ],
)
def test_seg_m4_05_la_celda_fuente_sin_esquema_no_se_conserva_en_ninguna_parte(
    tmp_path, celda, visible
):
    from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica

    from .apoyo_mvp3 import perfil_base

    tabla = tabla_csv([ENC, f"a-01;iso;{celda};linux;;;;;"])
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    fila = next(f for f in resultado.filas if f.numero == 2)
    assert fila.originales["fuente"] == visible
    volcado = repr(fila.originales) + repr(fila.problemas)
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, resultado, lambda p: p.regla)
    texto_csv = ruta.read_text(encoding="utf-8-sig")
    assert f'"{visible}"' in texto_csv  # la celda de errores lleva la forma saneada
    for secreto in SECRETOS:
        assert secreto not in volcado + texto_csv, secreto


def test_seg_m4_05_un_nombre_de_archivo_normal_no_se_altera_en_originales():
    r = importar_csv([ENC, "a-01;iso;alpine.iso;linux;;;;;"])
    fila = next(f for f in r.filas if f.numero == 2)
    assert fila.originales.get("fuente") == "alpine.iso"


# --- SEG-M4-10: la cabecera se reinspecciona sobre el descriptor abierto -------------------------


def _ustar() -> bytes:
    return bytes(257) + b"ustar" + bytes(600)


def test_seg_m4_10_un_disco_que_pasa_a_ser_tar_tras_la_inspeccion_no_se_sube(tmp_path):
    ruta = tmp_path / "disco.img"
    ruta.write_bytes(b"\x00" * 4096)
    with abrir_para_subir(ruta) as archivo:
        ruta.write_bytes(_ustar())  # mismo inodo: cambia el contenido bajo el descriptor
        with pytest.raises(ErrorProxLaunch) as ex:
            comprobar_cabecera_abierto(archivo, Contenido.IMPORT)
        assert ex.value.codigo == CodigoError.IMAGEN_NO_ADMITIDA
        assert ex.value.params["motivo"] == "ova" and ex.value.params["archivo"] == "disco.img"
        assert archivo.flujo.tell() == 0


def test_seg_m4_10_un_raw_normal_se_admite_y_deja_el_flujo_en_cero(tmp_path):
    ruta = tmp_path / "disco.img"
    ruta.write_bytes(b"\x00" * 4096)
    with abrir_para_subir(ruta) as archivo:
        comprobar_cabecera_abierto(archivo, Contenido.IMPORT)
        assert archivo.flujo.tell() == 0


def test_seg_m4_10_un_ova_por_nombre_no_se_admite_como_imagen(tmp_path):
    ruta = tmp_path / "maquina.ova"
    ruta.write_bytes(b"\x00" * 4096)
    with abrir_para_subir(ruta) as archivo, pytest.raises(ErrorProxLaunch) as ex:
        comprobar_cabecera_abierto(archivo, Contenido.IMPORT)
    assert ex.value.codigo == CodigoError.IMAGEN_NO_ADMITIDA


def test_seg_m4_10_un_iso_cualquiera_se_admite(tmp_path):
    ruta = tmp_path / "x.iso"
    ruta.write_bytes(b"\x00" * 4096)
    with abrir_para_subir(ruta) as archivo:
        comprobar_cabecera_abierto(archivo, Contenido.ISO)  # no lanza: solo aviso de no ISO9660


def test_seg_m4_10_el_servicio_rechaza_antes_de_enviar_si_la_cabecera_ya_no_vale(tmp_path):
    mundo = _Mundo(tmp_path)
    destino = DestinoTransferencia("pve1", "local", Contenido.IMPORT, "disco.qcow2")
    mundo.archivo.write_bytes(_ustar())
    r = mundo.subir(destino)
    assert r.estado == EstadoTransferencia.FALLIDA
    assert r.error.codigo == CodigoError.IMAGEN_NO_ADMITIDA
    assert mundo.posts_upload() == []


# --- SEG-M4-12: sin __cause__ con la ruta en archivo_local ---------------------------------------


def test_seg_m4_12_abrir_un_archivo_inexistente_no_encadena_el_oserror(tmp_path):
    ruta = tmp_path / "carpeta-secreta" / "no-existe.iso"
    with pytest.raises(ErrorProxLaunch) as ex:
        abrir_para_subir(ruta)
    assert ex.value.codigo == CodigoError.ARCHIVO_NO_ACCESIBLE
    assert ex.value.__cause__ is None and ex.value.__suppress_context__ is True
    assert "carpeta-secreta" not in repr(ex.value.params) + ex.value.detalle_tecnico


def test_seg_m4_12_inspeccionar_un_archivo_ilegible_no_encadena_el_oserror(tmp_path):
    from proxlaunch.nucleo.transferencias.archivo_local import inspeccionar

    ruta = tmp_path / "carpeta-secreta" / "x.iso"
    with pytest.raises(ErrorProxLaunch) as ex:
        inspeccionar(ruta, Contenido.ISO)
    assert ex.value.__cause__ is None
