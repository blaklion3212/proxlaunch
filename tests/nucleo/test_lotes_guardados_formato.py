"""Lotes guardados: serializar y leer (RF-G01, RF-G02, RF-G06, RF-G07; CA-G01.*, CA-G02.3,
CA-G02.5, CA-G02.6, CA-G03.3, CA-G03.4, CA-G06.*; CA-X01.*, CA-X02.*, CA-X04.*; INV-M2, INV-M3,
INV-M5; RNF-M05; §13 casos 7, 8 y 9 de los requisitos).

El lote guardado es un archivo autocontenido: SOLO la lista blanca (nunca plan, VMIDs reservados,
libro, UPID, ``id_lote``, política thin, perfil de conexión, host ni usuario). Un lote se lee
sin los rangos de M1 (borrador aceptado, CA-G02.1): las reglas las muestra el formulario.
"""

import contextlib
import dataclasses
import hashlib
import json
import os
import stat
import time

import pytest

from proxlaunch.nucleo.archivos.constantes import MAX_BYTES_LOTE
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, ErrorArchivo, MotivoCampo
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote import constantes as constantes_lote
from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    DefinicionLote,
    Destino,
    FilaLote,
    ModoDestino,
    PatronNombres,
    PoliticaThin,
)
from proxlaunch.nucleo.lote.planificador import validar_definicion
from proxlaunch.nucleo.lotes_guardados.formato import (
    guardar_lote,
    leer_archivo_lote,
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.vm import Ballooning, Bus, Disco, Firmware, InterfazRed, ModeloRed
from proxlaunch.nucleo.validacion import validar_sin_servidor

from .apoyo_lote import definicion, inventario, plantilla, volcar
from .apoyo_mvp3 import (
    CENT_HOST,
    CENT_PASSWORD,
    CENT_TOKEN,
    CENT_USUARIO,
    archivo_lote,
    archivo_lote_por_filas,
    cfg_hw,
    config_lote_json,
    definicion_filas,
    fila,
    filas_heterogeneas,
    lote_homogeneo_json,
    sin_centinelas,
)

PROHIBIDAS = {
    "plan", "elementos", "libro", "upid", "id_lote", "vmids_saltados", "politica_thin",
    "vmids", "perfil", "host", "usuario", "token", "password", "ticket", "csrf", "huella", "puerto",
}  # fmt: skip


def _claves(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _claves(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _claves(v)}
    return set()


def _normalizada(d: DefinicionLote) -> DefinicionLote:
    """Lo que debe sobrevivir a un guardado: sin vmid/nombre/nodo/etiquetas de la plantilla
    ni política thin (CA-G01.1)."""

    def _cfg(c):
        return dataclasses.replace(c, vmid=0, nombre="", nodo="", etiquetas=())

    filas = tuple(dataclasses.replace(f, cfg=_cfg(f.cfg)) for f in d.filas)
    return dataclasses.replace(
        d, plantilla=_cfg(d.plantilla), filas=filas, politica_thin=PoliticaThin.CONFIRMAR_CON_TOPE
    )


def _ida_y_vuelta(d: DefinicionLote, nombre="Lote", **kw) -> LoteGuardado:
    return leer_lote(lote_a_bytes(LoteGuardado(nombre, d, **kw), app_version="0.3.0")).lote


def _error_lote(datos: bytes) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_lote(datos)
    return exc.value


def _campos(e: ErrorProxLaunch) -> list[tuple[str, MotivoCampo]]:
    assert isinstance(e, ErrorArchivo), e
    return [(x.ruta, x.motivo) for x in e.errores]


# --- CA-G01.1: ida y vuelta -----------------------------------------------------------------------


def test_ida_y_vuelta_de_un_lote_homogeneo_sencillo():
    d = definicion(5, prefijo="aula", relleno=3, inicio=7)
    assert _ida_y_vuelta(d).definicion == _normalizada(d)


def test_ida_y_vuelta_con_toda_la_configuracion_y_el_destino():
    cfg = plantilla(
        firmware=Firmware.OVMF, storage_efi="datos", sockets=2, cores=4, memoria_mib=8192,
        tipo_cpu="host", ballooning=Ballooning(True, 1024),
        discos=[Disco("datos", 50, Bus.SATA, discard=False, ssd=False, iothread=False), Disco("otro", 5)],  # noqa: E501
        redes=[InterfazRed("vmbr0", ModeloRed.E1000, 30), InterfazRed("vmbr1")],
    )  # fmt: skip
    for destino in (
        Destino(ModoDestino.UN_NODO, ("pve2",), Algoritmo.POR_TURNOS),
        Destino(ModoDestino.NODOS_ELEGIDOS, ("pve1", "pve3"), Algoritmo.EQUILIBRADO),
        Destino(ModoDestino.AUTOMATICO, (), Algoritmo.POR_TURNOS),
    ):
        d = DefinicionLote(
            cfg, 12, PatronNombres("srv", "_", 3, 4), destino, vmid_inicial=500, etiquetar=False
        )
        assert _ida_y_vuelta(d).definicion == _normalizada(d)


def test_ida_y_vuelta_sin_disco_ni_redes():
    d = definicion(2, plantilla_vm=plantilla(con_disco=False, discos=[], redes=[]))
    assert _ida_y_vuelta(d).definicion == _normalizada(d)


def test_la_politica_thin_no_se_guarda_y_al_leer_toma_el_valor_de_la_aplicacion():
    """CA-G01.1 / M2 CA-L08.7."""
    d = definicion(3, politica_thin=PoliticaThin.BLOQUEAR)
    datos = lote_a_bytes(LoteGuardado("L", d), app_version="1")
    assert b"thin" not in datos and b"politica" not in datos
    assert leer_lote(datos).lote.definicion.politica_thin == PoliticaThin.CONFIRMAR_CON_TOPE


def test_vmid_nombre_nodo_y_etiquetas_de_la_plantilla_no_se_guardan():
    d = definicion(
        3,
        plantilla_vm=plantilla(
            vmid=987654, nombre="NOMBRE-SECRETO", nodo="NODO-X", etiquetas=("etq-privada",)
        ),
    )
    datos = lote_a_bytes(LoteGuardado("L", d), app_version="1")
    for valor in (b"987654", b"NOMBRE-SECRETO", b"NODO-X", b"etq-privada"):
        assert valor not in datos
    leida = leer_lote(datos).lote.definicion.plantilla
    assert (leida.vmid, leida.nombre, leida.nodo, leida.etiquetas) == (0, "", "", ())


# --- CA-G01.2 / INV-M5: solo la lista blanca ------------------------------------------------------


def test_el_archivo_homogeneo_solo_contiene_claves_de_la_lista_blanca():
    crudo = json.loads(lote_a_bytes(LoteGuardado("L", definicion(3)), app_version="1"))
    assert set(crudo) == {
        "formato",
        "version_formato",
        "app_version",
        "nombre",
        "tipo",
        "homogeneo",
    }
    assert set(crudo["homogeneo"]) == {
        "config",
        "cantidad",
        "patron",
        "destino",
        "vmid_inicial",
        "etiquetar",
    }
    assert set(crudo["homogeneo"]["patron"]) == {"prefijo", "separador", "inicio", "relleno"}
    assert set(crudo["homogeneo"]["destino"]) == {"modo", "nodos", "algoritmo"}
    assert set(crudo["homogeneo"]["config"]) == {
        "firmware", "sockets", "cores", "tipo_cpu", "memoria_mib", "ballooning", "con_disco", "discos",  # noqa: E501
        "storage_efi", "controlador_scsi", "redes", "origen",
    }  # fmt: skip
    assert not (_claves(crudo) & PROHIBIDAS)


def test_el_archivo_por_filas_solo_contiene_claves_de_la_lista_blanca():
    d = definicion_filas([fila("a-01", vmid=150, nodo="pve2", origen=2), fila("a-02")])
    crudo = json.loads(lote_a_bytes(LoteGuardado("L", d), app_version="1"))
    assert crudo["tipo"] == "por_filas" and "homogeneo" not in crudo
    assert set(crudo["por_filas"]) == {"filas", "destino", "vmid_inicial", "etiquetar"}
    assert set(crudo["por_filas"]["destino"]) == {"algoritmo"}
    assert set(crudo["por_filas"]["filas"][0]) == {"nombre", "vmid", "nodo", "config", "origen"}
    assert set(crudo["por_filas"]["filas"][1]) == {"nombre", "vmid", "nodo", "config"}  # sin origen
    assert not (_claves(crudo) & PROHIBIDAS)
    assert "patron" not in _claves(crudo)


def test_la_plantilla_informativa_de_un_lote_por_filas_no_se_guarda():
    """La plantilla de un lote por filas «no la lee ningún cálculo»: tampoco el archivo."""
    d = definicion_filas(
        [fila("a-01")], plantilla_base=cfg_hw(cores=99, memoria_mib=777777, nombre="ABSURDA")
    )
    datos = lote_a_bytes(LoteGuardado("L", d), app_version="1")
    assert b"777777" not in datos and b"ABSURDA" not in datos and b'"cores": 99' not in datos


# --- CA-G01.3 / G01.4 / D-T12 ---------------------------------------------------------------------


def test_vmid_inicial_solo_se_guarda_si_el_usuario_lo_fijo_y_si_no_es_null():
    crudo = json.loads(lote_a_bytes(LoteGuardado("L", definicion(3)), app_version="1"))
    assert crudo["homogeneo"]["vmid_inicial"] is None
    crudo = json.loads(
        lote_a_bytes(LoteGuardado("L", definicion(3, vmid_inicial=400)), app_version="1")
    )
    assert crudo["homogeneo"]["vmid_inicial"] == 400
    assert _ida_y_vuelta(definicion(3, vmid_inicial=400)).definicion.vmid_inicial == 400
    assert _ida_y_vuelta(definicion(3)).definicion.vmid_inicial is None


@pytest.mark.parametrize("etiquetar", [True, False])
def test_etiquetar_se_guarda_y_se_restaura(etiquetar):
    assert _ida_y_vuelta(definicion(3, etiquetar=etiquetar)).definicion.etiquetar is etiquetar


def test_una_sola_maquina_con_prefijo_vacio_conserva_el_nombre_de_la_plantilla():
    """D-T12: si no, el nombre se perdería."""
    d = definicion(1, prefijo="", plantilla_vm=plantilla(nombre="mi-servidor"))
    crudo = json.loads(lote_a_bytes(LoteGuardado("L", d), app_version="1"))
    assert crudo["homogeneo"]["nombre_maquina"] == "mi-servidor"
    assert _ida_y_vuelta(d).definicion.plantilla.nombre == "mi-servidor"


def test_el_nombre_de_la_plantilla_no_se_guarda_si_hay_patron():
    for d in (definicion(1, prefijo="web"), definicion(3, prefijo="")):
        d = dataclasses.replace(d, plantilla=plantilla(nombre="no-guardar"))
        assert b"no-guardar" not in lote_a_bytes(LoteGuardado("L", d), app_version="1")


# --- Lote por filas (RF-G07, CA-G02.5) ------------------------------------------------------------


def test_ida_y_vuelta_de_un_lote_por_filas_heterogeneo_con_vmid_nodo_y_origen():
    filas = [
        fila("a-01", vmid=150, nodo="pve2", origen=2, cores=1, memoria_mib=512),
        fila("a-02", origen=3, cores=4, memoria_mib=8192, discos=[Disco("datos", 64), Disco("datos", 16)]),  # noqa: E501
        fila("a-03", nodo="pve3", firmware=Firmware.OVMF, tipo_cpu="host"),
    ]  # fmt: skip
    d = definicion_filas(filas, algoritmo=Algoritmo.POR_TURNOS, vmid_inicial=300, etiquetar=False)
    leido = _ida_y_vuelta(d).definicion
    assert leido.es_por_filas and leido.cantidad == 3
    assert leido.filas == _normalizada(d).filas  # configuración efectiva de CADA fila (CA-G02.5)
    assert (leido.destino.algoritmo, leido.vmid_inicial, leido.etiquetar) == (
        Algoritmo.POR_TURNOS,
        300,
        False,
    )
    assert leido.destino.modo == ModoDestino.AUTOMATICO and leido.patron == PatronNombres(
        prefijo=""
    )
    assert leido.plantilla == leido.filas[0].cfg  # informativa = copia de la primera fila


def test_la_plantilla_de_un_lote_por_filas_leido_es_una_copia_independiente():
    leido = _ida_y_vuelta(definicion_filas(filas_heterogeneas())).definicion
    assert leido.plantilla is not leido.filas[0].cfg
    leido.plantilla.cores = 77
    assert leido.filas[0].cfg.cores != 77


def test_no_se_guarda_el_csv_de_origen_ni_su_ruta():
    """CA-G07.1."""
    d = definicion_filas([fila("a-01", origen=2)])
    datos = lote_a_bytes(LoteGuardado("L", d), app_version="1")
    assert b".csv" not in datos and b"/" not in datos.replace(b"\\/", b"")


# --- version_proxmox y nombre del lote ------------------------------------------------------------


def test_version_proxmox_es_opcional_e_informativa():
    sin = lote_a_dict(LoteGuardado("L", definicion(2)))
    assert "version_proxmox" not in sin
    con = _ida_y_vuelta(definicion(2), version_proxmox="9.2.1")
    assert con.version_proxmox == "9.2.1"
    assert _ida_y_vuelta(definicion(2)).version_proxmox is None


def test_el_nombre_del_lote_se_recorta_y_normaliza():
    assert _ida_y_vuelta(definicion(2), nombre="  Aula 3  ").nombre == "Aula 3"
    assert leer_lote(archivo_lote(nombre="Aulá")).lote.nombre == "Aulá"


@pytest.mark.parametrize(
    ("nombre", "motivo"),
    [
        ("", MotivoCampo.LONGITUD),
        ("a" * 61, MotivoCampo.LONGITUD),
        ("ab‮cd", MotivoCampo.TEXTO_NO_VALIDO),
        ("a\x00b", MotivoCampo.TEXTO_NO_VALIDO),
        ("ana@pve!x=abcdef", MotivoCampo.TOKEN),
        (5, MotivoCampo.TIPO),
        (None, MotivoCampo.TIPO),
    ],
)
def test_nombre_de_lote_invalido_es_e_m04(nombre, motivo):
    assert ("nombre", motivo) in _campos(_error_lote(archivo_lote(nombre=nombre)))


def test_el_nombre_de_lote_no_exige_ser_unico():
    """CA-G02.2: V-M01 sin la unicidad (dos archivos pueden llamarse igual)."""
    assert (
        leer_lote(archivo_lote(nombre="Igual")).lote.nombre
        == leer_lote(archivo_lote(nombre="Igual")).lote.nombre
    )


# --- Errores de formato y esquema (E-M02, E-M03, E-M04, E-M06) ------------------------------------


def test_un_lote_valido_se_lee_con_su_configuracion():
    archivo = leer_lote(archivo_lote())
    d = archivo.lote.definicion
    assert archivo.version_original == 1 and archivo.avisos == ()
    assert (d.cantidad, d.patron, d.destino, d.vmid_inicial, d.etiquetar) == (
        3, PatronNombres("web", "-", 1, 2), Destino(), None, True,
    )  # fmt: skip
    assert d.plantilla.discos == [Disco("datos", 32)] and d.plantilla.redes == [
        InterfazRed("vmbr0")
    ]


def test_la_lista_completa_de_errores_con_la_ruta_de_cada_campo():
    """CA-G03.3: no se carga nada y se muestran TODOS los errores con su ruta."""
    contenido = lote_homogeneo_json(
        cantidad="10",
        config=config_lote_json(
            cores="x", discos=[{"storage": "datos", "tamano_gib": 8}, {"tamano_gib": 9}]
        ),
    )
    del contenido["patron"]
    e = _error_lote(archivo_lote(contenido))
    assert e.codigo == CodigoError.ARCHIVO_DANADO
    rutas = dict(_campos(e))
    assert rutas["homogeneo.cantidad"] == MotivoCampo.TIPO
    assert rutas["homogeneo.config.cores"] == MotivoCampo.TIPO
    assert rutas["homogeneo.config.discos[1].storage"] == MotivoCampo.REQUERIDO
    assert rutas["homogeneo.patron"] == MotivoCampo.REQUERIDO
    assert e.params["n"] == str(len(e.errores)) and e.params["campo"] == e.errores[0].ruta


@pytest.mark.parametrize(
    ("cantidad", "motivo"),
    [
        (-1, MotivoCampo.RANGO),
        (1.5, MotivoCampo.TIPO),
        ("10", MotivoCampo.TIPO),
        (True, MotivoCampo.TIPO),
        (None, MotivoCampo.TIPO),
        ([3], MotivoCampo.TIPO),
    ],
)
def test_cantidad_no_entera_o_negativa_es_e_m04_por_esquema(cantidad, motivo):
    """§13.7 / CA-G06.4."""
    assert ("homogeneo.cantidad", motivo) in _campos(
        _error_lote(archivo_lote(lote_homogeneo_json(cantidad=cantidad)))
    )


@pytest.mark.parametrize("cantidad", [0, 101, 5000])
def test_cantidad_fuera_de_1_a_100_se_lee_pero_v_l01_la_senala_sin_recortar(cantidad):
    """CA-G06.4: V-L01 como error del campo, sin recortar."""
    d = leer_lote(archivo_lote(lote_homogeneo_json(cantidad=cantidad))).lote.definicion
    assert d.cantidad == cantidad  # no se recorta
    problemas = validar_definicion(d, inventario(), (9, 2))
    assert [p.campo for p in problemas if p.regla == "V-L01"] == ["cantidad"]


@pytest.mark.parametrize("vmid_inicial", [99, 1_000_000_000])
def test_vmid_inicial_fuera_de_rango_se_lee_pero_v_l07_lo_senala(vmid_inicial):
    d = leer_lote(archivo_lote(lote_homogeneo_json(vmid_inicial=vmid_inicial))).lote.definicion
    assert d.vmid_inicial == vmid_inicial
    assert any(p.regla == "V-L07" for p in validar_definicion(d, inventario(), (9, 2)))


@pytest.mark.parametrize("vmid_inicial", [-5, "100", True, 1.5, [1]])
def test_vmid_inicial_de_tipo_erroneo_es_e_m04(vmid_inicial):
    campos = _campos(_error_lote(archivo_lote(lote_homogeneo_json(vmid_inicial=vmid_inicial))))
    assert any(r == "homogeneo.vmid_inicial" for r, _ in campos)


def test_nodos_elegidos_sin_ningun_nodo_se_lee_y_v_l13_lo_senala():
    """§13.7: modo ``nodos_elegidos`` con 0 nodos."""
    contenido = lote_homogeneo_json(
        destino={"modo": "nodos_elegidos", "nodos": [], "algoritmo": "equilibrado"}
    )
    d = leer_lote(archivo_lote(contenido)).lote.definicion
    assert d.destino == Destino(ModoDestino.NODOS_ELEGIDOS, (), Algoritmo.EQUILIBRADO)
    assert any(p.regla == "V-L13" for p in validar_definicion(d, inventario(), (9, 2)))


@pytest.mark.parametrize(
    ("destino", "ruta"),
    [
        ({"modo": "otro"}, "homogeneo.destino.modo"),
        ({"modo": 3}, "homogeneo.destino.modo"),
        ({"algoritmo": "azar"}, "homogeneo.destino.algoritmo"),
        ({"nodos": "pve1"}, "homogeneo.destino.nodos"),
        ({"nodos": [1]}, "homogeneo.destino.nodos[0]"),
        ({"nodos": ["a\x00b"]}, "homogeneo.destino.nodos[0]"),
    ],
)
def test_destino_mal_formado_es_e_m04(destino, ruta):
    base = {"modo": "automatico", "nodos": [], "algoritmo": "equilibrado", **destino}
    assert ruta in [
        r for r, _ in _campos(_error_lote(archivo_lote(lote_homogeneo_json(destino=base))))
    ]


@pytest.mark.parametrize(
    ("patron", "ruta"),
    [
        ({"prefijo": 5}, "homogeneo.patron.prefijo"),
        ({"prefijo": "w", "inicio": "1"}, "homogeneo.patron.inicio"),
        ({"prefijo": "w", "inicio": -1}, "homogeneo.patron.inicio"),
        ({"prefijo": "w", "relleno": 1.5}, "homogeneo.patron.relleno"),
        ({"prefijo": "w", "separador": 3}, "homogeneo.patron.separador"),
        ({"separador": "-"}, "homogeneo.patron.prefijo"),
    ],
)
def test_patron_mal_formado_es_e_m04(patron, ruta):
    assert ruta in [
        r for r, _ in _campos(_error_lote(archivo_lote(lote_homogeneo_json(patron=patron))))
    ]


@pytest.mark.parametrize(
    ("cambios", "ruta"),
    [
        ({"cores": True}, "homogeneo.config.cores"),
        ({"memoria_mib": "4096"}, "homogeneo.config.memoria_mib"),
        ({"firmware": "uefi"}, "homogeneo.config.firmware"),
        ({"origen": "usb"}, "homogeneo.config.origen"),  # «iso» ya es válido (MVP 4, RF-O27)
        ({"con_disco": "si"}, "homogeneo.config.con_disco"),
        ({"discos": [{"storage": 5, "tamano_gib": 8}]}, "homogeneo.config.discos[0].storage"),
        (
            {"discos": [{"storage": "d", "tamano_gib": 2.0}]},
            "homogeneo.config.discos[0].tamano_gib",
        ),
        ({"redes": [{"modelo": "virtio"}]}, "homogeneo.config.redes[0].bridge"),
        ({"redes": [{"bridge": "vmbr0", "vlan": "5"}]}, "homogeneo.config.redes[0].vlan"),
        ({"storage_efi": 3}, "homogeneo.config.storage_efi"),
    ],
)
def test_tipos_erroneos_en_la_configuracion_del_lote_dan_e_m04_con_la_ruta(cambios, ruta):
    config = config_lote_json(**cambios)
    assert ruta in [
        r for r, _ in _campos(_error_lote(archivo_lote(lote_homogeneo_json(config=config))))
    ]


def test_un_lote_borrador_con_valores_fuera_de_regla_se_carga_y_la_capa_1_los_muestra():
    """CA-G02.1: «borrador»; las reglas V-05, V-06, V-08 las comprueba el formulario tras cargar."""
    config = config_lote_json(
        cores=0, memoria_mib=4, discos=[{"storage": "datos", "tamano_gib": 0}]
    )
    d = leer_lote(archivo_lote(lote_homogeneo_json(config=config))).lote.definicion
    reglas = {p.codigo for p in validar_sin_servidor(d.plantilla)}
    assert {"V-05", "V-06", "V-08"} <= reglas


@pytest.mark.parametrize("tipo", [None, "otro", 5, "HOMOGENEO"])
def test_tipo_ausente_o_desconocido_es_e_m04(tipo):
    crudo = json.loads(archivo_lote())
    if tipo is None:
        del crudo["tipo"]
    else:
        crudo["tipo"] = tipo
    assert "tipo" in [r for r, _ in _campos(_error_lote(json.dumps(crudo).encode()))]


def test_el_bloque_del_tipo_declarado_es_obligatorio():
    crudo = json.loads(archivo_lote())
    del crudo["homogeneo"]
    assert ("homogeneo", MotivoCampo.REQUERIDO) in _campos(_error_lote(json.dumps(crudo).encode()))
    crudo = json.loads(archivo_lote_por_filas())
    del crudo["por_filas"]
    assert ("por_filas", MotivoCampo.REQUERIDO) in _campos(_error_lote(json.dumps(crudo).encode()))


def test_el_tipo_declarado_manda_sobre_el_bloque_que_no_corresponde():
    crudo = json.loads(archivo_lote())
    crudo["tipo"] = "por_filas"
    e = _error_lote(json.dumps(crudo).encode())
    assert ("por_filas", MotivoCampo.REQUERIDO) in _campos(e)


def test_por_filas_con_cero_filas_es_e_m04_y_con_mas_de_100_es_e_m06():
    assert any(r == "por_filas.filas" for r, _ in _campos(_error_lote(archivo_lote_por_filas([]))))
    fila_json = {"nombre": "x", "config": config_lote_json()}
    assert (
        len(
            leer_lote(
                archivo_lote_por_filas([dict(fila_json, nombre=f"n{i}") for i in range(100)])
            ).lote.definicion.filas
        )
        == 100
    )
    e = _error_lote(archivo_lote_por_filas([dict(fila_json, nombre=f"n{i}") for i in range(101)]))
    assert e.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    assert e.params == {"tipo": "filas", "filas": "101", "max": "100"}


def test_mas_de_max_lote_filas_se_rechaza_antes_de_interpretar_ninguna():
    """CA-G06.5: E-M06 «sin cargar ninguna» (ni siquiera se miran los elementos)."""
    e = _error_lote(archivo_lote_por_filas([1] * 101))
    assert e.codigo == CodigoError.ARCHIVO_DEMASIADAS_FILAS


def test_el_limite_de_filas_es_la_constante_max_lote_de_m2(monkeypatch):
    """CA-C15.2: cambiar ``MAX_LOTE`` cambia el límite del lote guardado."""
    from proxlaunch.nucleo.lotes_guardados import formato

    assert formato.MAX_LOTE is constantes_lote.MAX_LOTE == 100
    monkeypatch.setattr(formato, "MAX_LOTE", 3)
    fila_json = {"nombre": "x", "config": config_lote_json()}
    leer_lote(archivo_lote_por_filas([dict(fila_json, nombre=f"n{i}") for i in range(3)]))
    assert (
        _error_lote(
            archivo_lote_por_filas([dict(fila_json, nombre=f"n{i}") for i in range(4)])
        ).codigo
        == CodigoError.ARCHIVO_DEMASIADAS_FILAS
    )


@pytest.mark.parametrize(
    ("fila_json", "ruta"),
    [
        ({"config": config_lote_json()}, "por_filas.filas[0].nombre"),
        ({"nombre": "x"}, "por_filas.filas[0].config"),
        ({"nombre": "x", "config": config_lote_json(), "vmid": "150"}, "por_filas.filas[0].vmid"),
        ({"nombre": "x", "config": config_lote_json(), "vmid": True}, "por_filas.filas[0].vmid"),
        ({"nombre": "x", "config": config_lote_json(), "nodo": 5}, "por_filas.filas[0].nodo"),
        ({"nombre": "x", "config": config_lote_json(), "nodo": ""}, "por_filas.filas[0].nodo"),
        ({"nombre": 5, "config": config_lote_json()}, "por_filas.filas[0].nombre"),
        ({"nombre": "x", "config": config_lote_json(cores="2")}, "por_filas.filas[0].config.cores"),
    ],
)
def test_filas_mal_formadas_son_e_m04_con_la_ruta_de_la_fila(fila_json, ruta):
    assert ruta in [r for r, _ in _campos(_error_lote(archivo_lote_por_filas([fila_json])))]


def test_un_error_en_una_sola_fila_impide_cargar_cualquier_fila():
    """Carga atómica (RNF-M11): o todo válido o excepción."""
    buena = {"nombre": "bien", "config": config_lote_json()}
    mala = {"nombre": "mal", "config": config_lote_json(cores="x")}
    with pytest.raises(ErrorProxLaunch):
        leer_lote(archivo_lote_por_filas([buena, mala, buena]))


def test_un_archivo_de_perfiles_abierto_como_lote_da_e_m02_con_la_pista():
    """CA-G06.6."""
    datos = json.dumps(
        {"formato": "proxlaunch.perfiles", "version_formato": 1, "perfiles": []}
    ).encode()
    e = _error_lote(datos)
    assert e.codigo == CodigoError.ARCHIVO_FORMATO_AJENO
    assert e.params == {"esperado": "proxlaunch.lote", "encontrado": "proxlaunch.perfiles"}


def test_version_futura_es_e_m03_sin_lectura_parcial_y_con_version_invalida_e_m02():
    """CA-G06.2 / CA-X01.4: aunque el resto del archivo sea válido."""
    # Fase B (CA-B6.1.5): la 4 ya se lee; la futura es la 5.
    e = _error_lote(archivo_lote(version_formato=5))
    assert e.codigo == CodigoError.ARCHIVO_VERSION_FUTURA
    assert e.params == {"version_archivo": "5", "version_soportada": "4"}
    for malo in (0, -1, True, "1", 1.0, None):
        assert (
            _error_lote(archivo_lote(version_formato=malo)).codigo
            == CodigoError.ARCHIVO_FORMATO_AJENO
        )


@pytest.mark.parametrize(
    "datos",
    [b"", b"{", b'{"formato": "proxlaunch.lote", "version_formato": 1, "nombre": "x"', b"\xff\xfe\x00", b"[]", b"null", b"NaN",  # noqa: E501
     b'{"formato": "proxlaunch.lote", "formato": "proxlaunch.lote"}'],
)  # fmt: skip
def test_json_danado_truncado_o_con_utf8_invalido(datos):
    """CA-G06.1."""
    assert _error_lote(datos).codigo in {
        CodigoError.ARCHIVO_DANADO,
        CodigoError.ARCHIVO_FORMATO_AJENO,
    }


def test_un_bom_al_inicio_se_tolera():
    assert leer_lote(b"\xef\xbb\xbf" + archivo_lote()).lote.nombre == "Lote de prueba"


def test_500_niveles_de_anidamiento_dan_e_m04():
    datos = b'{"formato": "proxlaunch.lote", "x": ' + b"[" * 500 + b"]" * 500 + b"}"
    assert _error_lote(datos).codigo == CodigoError.ARCHIVO_DANADO


def test_nan_y_numeros_fuera_de_rango_en_el_lote_dan_e_m04():
    for literal in ("NaN", "Infinity", "1e999"):
        datos = archivo_lote().decode().replace('"cantidad": 3', f'"cantidad": {literal}').encode()
        assert _error_lote(datos).codigo == CodigoError.ARCHIVO_DANADO


def test_cadena_de_10_mb_en_el_lote_se_rechaza_por_tamano_en_el_lector_de_archivos(tmp_path):
    """§13.9 / CA-G06.7."""
    ruta = tmp_path / "enorme.proxlaunch-lote.json"
    ruta.write_bytes(
        b'{"formato": "proxlaunch.lote", "nombre": "' + b"x" * (10 * 1024 * 1024) + b'"}'
    )
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_lote(ruta)
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert exc.value.params["limite"] == str(MAX_BYTES_LOTE) == str(1024 * 1024)


def test_una_cadena_larga_dentro_del_limite_se_rechaza_por_el_esquema():
    contenido = lote_homogeneo_json(
        patron={"prefijo": "x" * 5000, "separador": "-", "inicio": 1, "relleno": 2}
    )
    assert any("prefijo" in r for r, _ in _campos(_error_lote(archivo_lote(contenido))))


# --- Avisos: desconocidos, credenciales, migrado (CA-G03.4, CA-X01.6, CA-X04.2) -------------------


def test_campos_desconocidos_y_claves_de_credencial_se_ignoran_con_avisos_y_no_se_leen():
    contenido = lote_homogeneo_json(extra_nuevo="VALOR-PRIVADO")
    contenido["config"]["token"] = CENT_TOKEN
    crudo = json.loads(archivo_lote(contenido))
    crudo["password"] = CENT_PASSWORD
    crudo["campo_futuro"] = {"x": 1}
    archivo = leer_lote(json.dumps(crudo).encode())
    por_codigo = {a.codigo: a.params for a in archivo.avisos}
    assert por_codigo[CodigoAvisoArchivo.CAMPOS_DESCONOCIDOS] == {"n": "2"}
    assert por_codigo[CodigoAvisoArchivo.CREDENCIAL_IGNORADA] == {"n": "2"}
    assert "VALOR-PRIVADO" not in volcar(archivo) and CENT_TOKEN not in volcar(archivo)
    reescrito = lote_a_bytes(archivo.lote, app_version="1")
    assert b"campo_futuro" not in reescrito and b"token" not in reescrito
    assert sin_centinelas(reescrito)


def test_un_lote_sin_avisos_no_trae_ninguno():
    assert leer_lote(archivo_lote()).avisos == ()


# --- INV-M3, atomicidad, permisos -----------------------------------------------------------------


@pytest.mark.parametrize(
    "contenido",
    [archivo_lote(), b"{ roto", b"\xff\xfe", archivo_lote(version_formato=4)],
    ids=["valido", "json_roto", "utf8_roto", "version_futura"],
)
def test_abrir_un_lote_no_lo_modifica_ni_aunque_este_danado(tmp_path, contenido):
    """INV-M3."""
    ruta = tmp_path / "mi.proxlaunch-lote.json"
    ruta.write_bytes(contenido)
    antes = (hashlib.sha256(contenido).hexdigest(), ruta.stat().st_mtime_ns, ruta.stat().st_ino)
    with contextlib.suppress(ErrorProxLaunch):
        leer_archivo_lote(ruta)
    assert (
        hashlib.sha256(ruta.read_bytes()).hexdigest(),
        ruta.stat().st_mtime_ns,
        ruta.stat().st_ino,
    ) == antes
    assert [p.name for p in tmp_path.iterdir()] == [ruta.name]


def test_guardar_y_abrir_un_archivo_con_ruta_con_espacios_y_acentos(tmp_path):
    carpeta = tmp_path / "Mis lotes ñandú"
    carpeta.mkdir()
    ruta = carpeta / "Aula 3 – mañana.proxlaunch-lote.json"
    d = definicion(4)
    guardar_lote(ruta, LoteGuardado("Aula 3", d), app_version="0.3.0")
    assert leer_archivo_lote(ruta).lote.definicion == _normalizada(d)
    if os.name == "posix":
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert not ruta.read_bytes().startswith(b"\xef\xbb\xbf")


def test_guardar_encima_reemplaza_y_un_fallo_deja_el_archivo_anterior_intacto(
    tmp_path, monkeypatch
):
    """CA-G02.6 / CA-G03.6."""
    ruta = tmp_path / "x.proxlaunch-lote.json"
    guardar_lote(ruta, LoteGuardado("Uno", definicion(2)), app_version="1")
    antes = ruta.read_bytes()

    def _replace(*a, **k):
        raise OSError(28, "disco lleno")

    monkeypatch.setattr(os, "replace", _replace)
    with pytest.raises(ErrorProxLaunch) as exc:
        guardar_lote(ruta, LoteGuardado("Dos", definicion(9)), app_version="1")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    monkeypatch.undo()
    assert ruta.read_bytes() == antes
    guardar_lote(ruta, LoteGuardado("Dos", definicion(9)), app_version="1")
    assert leer_archivo_lote(ruta).lote.nombre == "Dos"


def test_guardar_en_una_carpeta_inexistente_no_la_crea(tmp_path):
    with pytest.raises(ErrorProxLaunch) as exc:
        guardar_lote(
            tmp_path / "no-existe" / "x.json", LoteGuardado("L", definicion(1)), app_version="1"
        )
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    assert not (tmp_path / "no-existe").exists()


def test_guardar_el_mismo_lote_dos_veces_produce_bytes_identicos():
    """Diferencias legibles con control de versiones (CA-X03.6)."""
    lote = LoteGuardado("L", definicion_filas(filas_heterogeneas()))
    assert lote_a_bytes(lote, app_version="1") == lote_a_bytes(lote, app_version="1")


# --- Huella para «cambios sin guardar» (RF-G08) ---------------------------------------------------


def test_lote_a_dict_sirve_de_huella_igual_si_nada_cambia_y_distinta_si_cambia_algo_guardable():
    base = LoteGuardado("L", definicion(3))
    assert lote_a_dict(base) == lote_a_dict(LoteGuardado("L", definicion(3)))
    assert lote_a_dict(base) != lote_a_dict(LoteGuardado("L", definicion(4)))
    assert lote_a_dict(base) != lote_a_dict(LoteGuardado("Otro", definicion(3)))
    assert lote_a_dict(base) != lote_a_dict(
        LoteGuardado("L", definicion(3, plantilla_vm=plantilla(cores=3)))
    )
    assert lote_a_dict(base) != lote_a_dict(LoteGuardado("L", definicion(3, vmid_inicial=300)))
    assert lote_a_dict(base) == lote_a_dict(
        LoteGuardado("L", definicion(3, politica_thin=PoliticaThin.ADVERTIR))
    )


def test_lote_a_dict_no_incluye_la_envoltura():
    raiz = lote_a_dict(LoteGuardado("L", definicion(2)))
    assert not (set(raiz) & {"formato", "version_formato", "app_version"})


# --- Privacidad (INV-M2, CA-X04.5) ----------------------------------------------------------------


def test_el_archivo_no_contiene_host_usuario_ni_secretos_aunque_esten_en_otros_campos_del_programa():  # noqa: E501
    """La función recibe un ``LoteGuardado``: no tiene campos de sesión que filtrar."""
    assert {f.name for f in dataclasses.fields(LoteGuardado)} == {
        "nombre",
        "definicion",
        "version_proxmox",
    }
    d = definicion(
        3,
        plantilla_vm=plantilla(
            nombre=CENT_HOST, nodo=CENT_USUARIO, etiquetas=(CENT_TOKEN.lower(),)
        ),
    )
    datos = lote_a_bytes(LoteGuardado("Aula", d), app_version="1")
    assert sin_centinelas(datos) and sin_centinelas(datos.lower(), [CENT_TOKEN.lower()])


# --- Rendimiento (RNF-M05) ------------------------------------------------------------------------


def test_guardar_y_abrir_un_lote_de_100_filas_tarda_menos_de_500_ms_de_cpu(tmp_path):
    filas = [
        fila(f"maquina-{i:03d}", vmid=1000 + i, cores=1 + i % 4, memoria_mib=512 * (1 + i % 8))
        for i in range(100)
    ]
    lote = LoteGuardado("Cien", definicion_filas(filas))
    ruta = tmp_path / "cien.json"
    t0 = time.process_time()
    guardar_lote(ruta, lote, app_version="1")
    guardar_s = time.process_time() - t0
    t0 = time.process_time()
    leido = leer_archivo_lote(ruta)
    abrir_s = time.process_time() - t0
    assert len(leido.lote.definicion.filas) == 100
    assert guardar_s < 0.5 and abrir_s < 0.5, (guardar_s, abrir_s)
    assert ruta.stat().st_size < MAX_BYTES_LOTE  # un lote de 100 filas cabe en el límite de 1 MiB


def test_el_lote_por_filas_de_100_filas_con_8_discos_y_32_redes_cabe_en_1_mib():
    cfg_grande = cfg_hw(
        discos=[Disco("datos", 8) for _ in range(8)],
        redes=[InterfazRed("vmbr0") for _ in range(32)],
    )
    filas = [
        FilaLote(f"maquina-{i:03d}-" + "x" * 30, cfg_grande, vmid=1000 + i, nodo="pve1")
        for i in range(100)
    ]
    datos = lote_a_bytes(LoteGuardado("Grande", definicion_filas(filas)), app_version="1")
    assert len(datos) <= MAX_BYTES_LOTE
    assert len(leer_lote(datos).lote.definicion.filas) == 100


# --- Borradores: lo que se puede guardar se puede volver a abrir (CA-G02.1, CA-G03.1) ----------------------  # noqa: E501


@pytest.mark.parametrize(
    "borrador",
    [
        pytest.param(
            lambda: definicion(3, plantilla_vm=plantilla(tipo_cpu="")), id="tipo_cpu_vacio"
        ),
        pytest.param(
            lambda: definicion(3, plantilla_vm=plantilla(tipo_cpu="a" * 100)), id="tipo_cpu_de_100"
        ),
        pytest.param(lambda: definicion(3, prefijo="a" * 300), id="prefijo_de_300"),
        pytest.param(
            lambda: definicion(
                3, plantilla_vm=plantilla(discos=[Disco("datos", 1) for _ in range(58)])
            ),
            id="58_discos",
        ),
        pytest.param(
            lambda: definicion(
                3, plantilla_vm=plantilla(redes=[InterfazRed("vmbr0") for _ in range(33)])
            ),
            id="33_redes",
        ),
        pytest.param(lambda: definicion_filas([fila("a" * 300)]), id="nombre_de_fila_de_300"),
    ],
)
def test_un_borrador_con_errores_de_capa_1_guardado_se_puede_volver_a_abrir(borrador):
    """CA-G02.1: con errores de validación «se puede guardar igualmente (es un borrador)... se
    comprobará otra vez al abrirlo». Un lote que el escritor serializa sin error no puede quedar
    ilegible para el lector (E-M04): las reglas V-22, V-L02, V-07, V-23 y V-01 son del formulario."""  # noqa: E501
    d = borrador()
    leido = leer_lote(lote_a_bytes(LoteGuardado("Borrador", d), app_version="1")).lote.definicion
    assert leido.cantidad == d.cantidad
