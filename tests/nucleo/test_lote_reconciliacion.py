"""Reconciliación de envíos inciertos sin UPID (RF-L15, CA-L15.2, CA-L15.5, E-L05, E-L06).

``existe_vm`` devuelve True / False / None; las esperas son del reloj simulado (0, +5, +15 s).
"""

import threading

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import COMPROBACIONES_EXISTENCIA_S
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.reconciliacion import (
    AVISO_CREADA_TRAS_COMPROBAR,
    etiquetas_de_config,
    reconciliar_incierta,
    tiene_etiqueta_del_lote,
)
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo_lote import plantilla

ID = "abcd1234"


class _Servicio:
    """``existe_vm`` con respuestas en secuencia; anota el instante de cada comprobación."""

    def __init__(self, reloj, *respuestas):
        self._reloj = reloj
        self._respuestas = list(respuestas)
        self.instantes = []

    def existe_vm(self, cfg):
        self.instantes.append(self._reloj.ahora())
        r = self._respuestas[min(len(self.instantes), len(self._respuestas)) - 1]
        if isinstance(r, BaseException):
            raise r
        return r


class _Cliente:
    def __init__(self, config=None, error=None):
        self._config = config
        self._error = error
        self.lecturas = 0

    def config_vm(self, nodo, vmid):
        self.lecturas += 1
        if self._error is not None:
            raise self._error
        return self._config


def _reconciliar(*respuestas, etiquetar=True, config=None, error=None, cancelado=None):
    reloj = RelojSimulado()
    servicio = _Servicio(reloj, *respuestas)
    cliente = _Cliente(config, error)
    cfg = plantilla(vmid=100, nombre="web-01", nodo="pve1")
    resultado = reconciliar_incierta(
        servicio,
        cfg,
        reloj,
        cancelado or threading.Event(),
        id_lote=ID,
        etiquetar=etiquetar,
        cliente=cliente,
    )
    return resultado, servicio, cliente


def test_las_comprobaciones_son_a_0_5_y_15_segundos():
    assert COMPROBACIONES_EXISTENCIA_S == (0.0, 5.0, 15.0)


def test_ca_l15_2_no_existe_en_las_tres_comprobaciones_es_no_creada_segura():
    (estado, aviso, error), servicio, _ = _reconciliar(False, False, False)
    assert (estado, aviso, error) == (EstadoMV.NO_CREADA_SEGURA, None, None)
    assert servicio.instantes == [0.0, 5.0, 15.0]


def test_ca_l15_2_existe_a_la_primera_es_ok_con_aviso_y_para():
    (estado, aviso, error), servicio, _ = _reconciliar(
        True, config={"name": "web-01", "tags": f"proxlaunch;lote-{ID}"}
    )
    assert (estado, aviso, error) == (EstadoMV.OK, AVISO_CREADA_TRAS_COMPROBAR, None)
    assert servicio.instantes == [0.0]


def test_ca_l15_2_existe_a_la_segunda_comprobacion():
    (estado, aviso, _), servicio, _ = _reconciliar(
        False, True, config={"tags": f"lote-{ID};proxlaunch"}
    )
    assert (estado, aviso) == (EstadoMV.OK, AVISO_CREADA_TRAS_COMPROBAR)
    assert servicio.instantes == [0.0, 5.0]


def test_ca_l15_2_existe_a_la_tercera_comprobacion():
    (estado, aviso, _), servicio, _ = _reconciliar(
        False, False, True, config={"tags": f"proxlaunch;lote-{ID}"}
    )
    assert estado == EstadoMV.OK
    assert servicio.instantes == [0.0, 5.0, 15.0]


@pytest.mark.parametrize("posicion", [0, 1, 2])
def test_ca_l15_2_no_se_pudo_saber_sigue_conexion_perdida_con_e_l06(posicion):
    respuestas = [False] * posicion + [None]
    (estado, aviso, error), servicio, _ = _reconciliar(*respuestas)
    assert estado == EstadoMV.CONEXION_PERDIDA
    assert error.codigo == CodigoError.LOTE_EXISTENCIA_INDETERMINADA
    assert error.params == {"nombre": "web-01", "vmid": "100"}
    assert len(servicio.instantes) == posicion + 1  # no sigue preguntando tras el None


def test_ca_l15_5_existe_sin_la_etiqueta_del_lote_no_confirma_la_propiedad():
    (estado, aviso, error), _, _ = _reconciliar(
        True, config={"name": "x", "tags": "otra;lote-9999"}
    )
    assert (estado, aviso, error) == (EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD, None, None)


def test_ca_l15_5_existe_sin_ninguna_etiqueta_tampoco_se_confirma():
    (estado, _, _), _, _ = _reconciliar(True, config={"name": "x"})
    assert estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD


def test_ca_l15_5_si_no_se_puede_leer_la_config_la_propiedad_no_esta_demostrada():
    (estado, _, _), _, _ = _reconciliar(True, error=RuntimeError("red"))
    assert estado == EstadoMV.EXISTE_SIN_CONFIRMAR_PROPIEDAD


def test_ca_l24_3_sin_etiquetas_activadas_existe_es_ok_sin_leer_la_config():
    (estado, aviso, _), _, cliente = _reconciliar(True, etiquetar=False)
    assert (estado, aviso) == (EstadoMV.OK, AVISO_CREADA_TRAS_COMPROBAR)
    assert cliente.lecturas == 0


def test_cancelar_durante_la_espera_deja_la_maquina_incierta_sin_declararla_no_creada():
    cancelado = threading.Event()
    cancelado.set()
    (estado, _, error), servicio, _ = _reconciliar(False, False, False, cancelado=cancelado)
    assert estado == EstadoMV.CONEXION_PERDIDA
    assert error.codigo == CodigoError.LOTE_ENVIO_INCIERTO
    assert servicio.instantes == []  # ni una comprobación: pregunta, no concluye


def test_la_reconciliacion_no_escribe_nada_solo_existe_vm_y_config():
    # El protocolo del servicio solo ofrece ``existe_vm``: no hay forma de enviar un POST.
    class _Solo:
        def existe_vm(self, cfg):
            return False

    reloj = RelojSimulado()
    resultado = reconciliar_incierta(
        _Solo(),
        plantilla(vmid=1, nombre="a", nodo="pve1"),
        reloj,
        threading.Event(),
        id_lote=ID,
        etiquetar=True,
        cliente=_Cliente(),
    )
    assert resultado[0] == EstadoMV.NO_CREADA_SEGURA


@pytest.mark.parametrize(
    ("tags", "esperado"),
    [
        ("proxlaunch;lote-abcd1234", True),
        ("lote-abcd1234", True),
        ("PROXLAUNCH;LOTE-ABCD1234", True),  # Proxmox guarda las etiquetas en minúsculas
        ("proxlaunch, lote-abcd1234", True),
        ("proxlaunch;lote-abcd12345", False),
        ("xlote-abcd1234", False),
        ("proxlaunch", False),
        ("", False),
        (None, False),
        (123, False),
    ],
)
def test_etiqueta_del_lote_en_la_config(tags, esperado):
    assert tiene_etiqueta_del_lote({"tags": tags}, ID) is esperado


def test_etiquetas_de_una_config_vacia_o_inexistente():
    assert etiquetas_de_config(None) == frozenset()
    assert etiquetas_de_config({}) == frozenset()
    assert not tiene_etiqueta_del_lote(None, ID)


def test_error_inesperado_de_existe_vm_se_propaga_como_dato_no_como_excepcion_silenciosa():
    """``existe_vm`` real traga sus errores y devuelve None; la reconciliación no los inventa."""
    (estado, _, error), _, _ = _reconciliar(None)
    assert estado == EstadoMV.CONEXION_PERDIDA
    assert isinstance(error, ErrorProxLaunch)
