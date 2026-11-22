"""Asistente «Crear plantilla desde imagen cloud» (B2) y su acceso desde la ventana (0.7.0).

Derivadas de docs/requisitos/fase-b.md: RF-B0.4 (disponible desde Proxmox 8.4), RF-B2.9
(casilla de irreversibilidad desmarcada, «Cancelar» predeterminado, confirmación expresa),
RF-B2.10 (nunca se ofrece borrar sin certeza), CA-B0.6.2 y CA-B8.1.1 (textos visibles y «?»).
El doble es el cliente de Proxmox (límite del sistema): nunca hay red real ni diálogos modales.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QToolButton

from proxlaunch.interfaz.dialogos import plantilla_imagen as modulo
from proxlaunch.interfaz.dialogos.plantilla_imagen import DialogoPlantillaImagen
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.tarea import Desenlace, EstadoTarea, ResultadoCreacion
from proxlaunch.nucleo.plantilla_imagen.modelos import EstadoPaso, PasoB2
from proxlaunch.nucleo.reloj import RelojSimulado

from .apoyo import sesion_falsa
from .apoyo_mvp4 import ServicioTransferenciasFalso, inv_origen, volumen

VOLID_IMAGEN = "local:import/ubuntu-24.04.qcow2"
NOMBRE_MV = "plantilla-ubuntu"
VMID = 9100
UPID = "UPID:pve:0003A1B2:00F4C1D3:6535AB12:qmcreate:9100:root@pam:"


class ClienteB2:
    """Cliente de Proxmox mínimo para el asistente: anota cada escritura."""

    def __init__(self) -> None:
        self.escrituras: list[tuple] = []
        self.config: dict | None = {"name": NOMBRE_MV, "template": 0}
        self.estado: dict = {"status": "stopped"}
        self.fallo_config: ErrorProxLaunch | None = None

    def contenido_storage(self, nodo, storage, contenido):
        if contenido == Contenido.IMPORT and storage == "local":
            return [volumen(VOLID_IMAGEN, Contenido.IMPORT)]
        return []

    def config_vm(self, nodo, vmid):
        if self.fallo_config is not None:
            raise self.fallo_config
        return dict(self.config) if self.config is not None else None

    def estado_actual_vm(self, nodo, vmid):
        return dict(self.estado)

    def configurar_vm(self, nodo, vmid, parametros):
        self.escrituras.append(("config", vmid, dict(parametros)))

    def convertir_en_plantilla(self, nodo, vmid):
        self.escrituras.append(("template", vmid))
        self.config = {**(self.config or {}), "template": 1}
        return None

    def eliminar_vm(self, nodo, vmid):
        self.escrituras.append(("delete", vmid))
        return UPID.replace("qmcreate", "qmdestroy")

    def estado_tarea(self, nodo, upid):
        return EstadoTarea("stopped", "OK")


class FabricaCreacionFalsa:
    """``fabrica_creacion`` del asistente: ``crear`` devuelve el desenlace programado."""

    def __init__(self, desenlace=Desenlace.OK, *, enviar: bool = True, error=None) -> None:
        self.desenlace = desenlace
        self.enviar = enviar
        self.error = error
        self.llamadas = 0

    def __call__(self, sesion, reloj):
        return self

    def crear(self, cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None, **_kw):
        self.llamadas += 1
        if self.enviar and al_enviar is not None:
            al_enviar(UPID)
        return ResultadoCreacion(
            self.desenlace, cfg.vmid, cfg.nodo, UPID if self.enviar else None, self.error
        )


class Confirmador:
    def __init__(self, respuesta: bool) -> None:
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, str, str, str]] = []

    def __call__(self, parent, titulo, texto, aceptar, cancelar) -> bool:
        self.llamadas.append((titulo, texto, aceptar, cancelar))
        return self.respuesta


@pytest.fixture
def cliente():
    return ClienteB2()


def hacer_dialogo(qtbot, cliente, fabrica=None, *, version=(8, 4)):
    inv = inv_origen(version=version)
    sesion = sesion_falsa(cliente=cliente, version=version)
    d = DialogoPlantillaImagen(
        sesion=sesion,
        reloj=RelojSimulado(),
        lanzador=Lanzador(),
        transferencias=ServicioTransferenciasFalso(),
        inv=inv,
        avanzado=True,
        nodo="pve",
        fabrica_creacion=fabrica or FabricaCreacionFalsa(),
    )
    qtbot.addWidget(d)
    d.show()
    return d


def preparar_formulario(qtbot, d: DialogoPlantillaImagen) -> None:
    """Elige la imagen que ya está en el servidor y rellena lo mínimo (sin pulsar «Crear»)."""
    d.radio_importada.setChecked(True)
    d.boton_actualizar_importadas.click()
    qtbot.waitUntil(lambda: d.combo_importadas.count() > 0, timeout=3000)
    d.campo_nombre.setText(NOMBRE_MV)
    d.spin_vmid.setValue(VMID)


def listo_para_crear(qtbot, d: DialogoPlantillaImagen) -> None:
    preparar_formulario(qtbot, d)
    d.casilla_irreversible.setChecked(True)
    qtbot.waitUntil(lambda: d.boton_crear.isEnabled(), timeout=3000)


def crear_y_esperar(qtbot, d, *, fase: str = "detenido") -> None:
    d.boton_crear.click()
    qtbot.waitUntil(lambda: d.fase == fase, timeout=5000)


# --- CA-B8.1.1 / texto introductorio visible y «?» ---


def test_ca_b8_1_1_el_asistente_tiene_texto_introductorio_visible_y_botones_de_ayuda(
    qtbot, cliente
):
    d = hacer_dialogo(qtbot, cliente)
    assert d.etiqueta_intro.isVisibleTo(d)
    assert "imagen cloud" in d.etiqueta_intro.text().lower()
    ayudas = [b for b in d.findChildren(QToolButton) if b.text() == "?"]
    assert len(ayudas) >= 5  # intro, imagen, suma, opciones, cloud-init, irreversible
    assert all(b.toolTip() for b in ayudas)


def test_el_asistente_tiene_titulo_y_nombre_accesible_en_la_casilla_de_irreversibilidad(
    qtbot, cliente
):
    d = hacer_dialogo(qtbot, cliente)
    assert d.windowTitle() == "Crear plantilla desde imagen cloud"
    assert d.casilla_irreversible.accessibleName() == d.casilla_irreversible.text()


# --- RF-B2.9: irreversibilidad y confirmación expresa ---


def test_ca_b2_9_1_la_casilla_de_irreversibilidad_viene_desmarcada_y_crear_esta_deshabilitado(
    qtbot, cliente
):
    d = hacer_dialogo(qtbot, cliente)
    preparar_formulario(qtbot, d)
    assert not d.casilla_irreversible.isChecked()
    qtbot.wait(100)  # deja correr la validación diferida
    assert not d.boton_crear.isEnabled()
    d.boton_crear.click()
    assert cliente.escrituras == []
    assert d.fase == "editando"


def test_ca_b2_9_1_marcar_la_casilla_habilita_crear_y_desmarcarla_lo_deshabilita(qtbot, cliente):
    d = hacer_dialogo(qtbot, cliente)
    listo_para_crear(qtbot, d)
    d.casilla_irreversible.setChecked(False)
    qtbot.waitUntil(lambda: not d.boton_crear.isEnabled(), timeout=3000)


def test_cancelar_es_el_boton_predeterminado_y_la_casilla_dice_que_no_se_puede_deshacer(
    qtbot, cliente
):
    d = hacer_dialogo(qtbot, cliente)
    assert d.boton_cancelar.isDefault()
    assert not d.boton_crear.isDefault()
    assert "no se puede encender ni volver a convertir en máquina normal" in (
        d.casilla_irreversible.text()
    )


def test_convertir_en_plantilla_pide_confirmacion_expresa_con_el_nombre_y_la_irreversibilidad(
    qtbot, cliente, monkeypatch
):
    confirmar = Confirmador(False)
    monkeypatch.setattr(modulo, "confirmar", confirmar)
    fabrica = FabricaCreacionFalsa()
    d = hacer_dialogo(qtbot, cliente, fabrica)
    listo_para_crear(qtbot, d)

    d.boton_crear.click()

    assert len(confirmar.llamadas) == 1
    titulo, texto, aceptar, cancelar = confirmar.llamadas[0]
    assert titulo == "Crear la plantilla"
    assert NOMBRE_MV in texto and str(VMID) in texto
    assert "no se puede" in texto.lower() or "no podrás" in texto.lower()
    assert (aceptar, cancelar) == ("Crear la plantilla", "Cancelar")


def test_si_se_rechaza_la_confirmacion_no_se_envia_nada_ni_se_crea_la_maquina(
    qtbot, cliente, monkeypatch
):
    monkeypatch.setattr(modulo, "confirmar", Confirmador(False))
    fabrica = FabricaCreacionFalsa()
    d = hacer_dialogo(qtbot, cliente, fabrica)
    listo_para_crear(qtbot, d)
    d.boton_crear.click()
    assert d.fase == "editando"
    assert fabrica.llamadas == 0 and cliente.escrituras == []
    assert d.boton_crear.isEnabled()  # se puede volver a intentar


def test_aceptada_la_confirmacion_el_flujo_completo_termina_con_la_conversion_en_plantilla(
    qtbot, cliente, monkeypatch
):
    monkeypatch.setattr(modulo, "confirmar", Confirmador(True))
    d = hacer_dialogo(qtbot, cliente)
    listo_para_crear(qtbot, d)
    crear_y_esperar(qtbot, d, fase="terminado")
    assert cliente.escrituras[-1] == ("template", VMID)  # lo último que se escribe
    assert d.estado.es_plantilla
    assert d.etiqueta_final.isVisibleTo(d)


# --- RF-B2.10: «Borrar la máquina a medio crear» solo con certeza ---


def fallar_en_crear(qtbot, monkeypatch, cliente, fabrica):
    monkeypatch.setattr(modulo, "confirmar", Confirmador(True))
    d = hacer_dialogo(qtbot, cliente, fabrica)
    listo_para_crear(qtbot, d)
    crear_y_esperar(qtbot, d)
    return d


def test_ca_b2_10_2_sin_certeza_de_que_la_maquina_es_suya_no_se_ofrece_borrar_y_se_explica(
    qtbot, cliente, monkeypatch
):
    # El servidor no responde al leer la configuración: no hay certeza.
    cliente.fallo_config = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {})
    fabrica = FabricaCreacionFalsa(Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.DESCONOCIDO))
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    qtbot.waitUntil(lambda: d.etiqueta_borrado.isVisibleTo(d), timeout=3000)
    assert not d.boton_borrar.isVisibleTo(d)
    assert "No puedo confirmar que la máquina sea tuya" in d.etiqueta_borrado.text()
    assert "Proxmox" in d.etiqueta_borrado.text()  # explica dónde borrarla
    assert ("delete", VMID) not in cliente.escrituras


def test_ca_b2_10_2_si_el_nombre_no_coincide_no_se_ofrece_borrar(qtbot, cliente, monkeypatch):
    cliente.config = {"name": "otra-maquina", "template": 0}
    fabrica = FabricaCreacionFalsa(Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.DESCONOCIDO))
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    qtbot.waitUntil(lambda: d.etiqueta_borrado.isVisibleTo(d), timeout=3000)
    assert not d.boton_borrar.isVisibleTo(d)
    assert ("delete", VMID) not in cliente.escrituras


@pytest.mark.parametrize(
    ("config", "estado", "texto"),
    [
        ({"name": NOMBRE_MV, "template": 1}, {"status": "stopped"}, "no cumple"),
        ({"name": NOMBRE_MV, "protection": 1}, {"status": "stopped"}, "protección"),
        ({"name": NOMBRE_MV, "lock": "clone"}, {"status": "stopped"}, "bloqueada"),
        ({"name": NOMBRE_MV}, {"status": "running"}, "encendida"),
    ],
)
def test_ca_b2_10_2_plantilla_protegida_bloqueada_o_encendida_no_se_ofrece_borrar(
    qtbot, cliente, monkeypatch, config, estado, texto
):
    cliente.config, cliente.estado = config, estado
    fabrica = FabricaCreacionFalsa(Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.DESCONOCIDO))
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    qtbot.waitUntil(lambda: d.etiqueta_borrado.isVisibleTo(d), timeout=3000)
    assert not d.boton_borrar.isVisibleTo(d)
    assert texto in d.etiqueta_borrado.text()
    assert ("delete", VMID) not in cliente.escrituras


def test_si_la_creacion_nunca_se_envio_no_hay_nada_que_borrar_ni_se_ofrece(
    qtbot, cliente, monkeypatch
):
    fabrica = FabricaCreacionFalsa(
        Desenlace.ERROR, enviar=False, error=ErrorProxLaunch(CodigoError.DESCONOCIDO)
    )
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    qtbot.wait(200)
    assert not d.boton_borrar.isVisibleTo(d)
    assert d.estado.pasos[PasoB2.CREAR] == EstadoPaso.FALLIDO
    assert d.boton_reintentar.isVisibleTo(d)
    assert ("delete", VMID) not in cliente.escrituras


def test_ca_b2_10_3_con_todas_las_condiciones_se_ofrece_pero_nunca_borra_sin_confirmar(
    qtbot, cliente, monkeypatch
):
    fabrica = FabricaCreacionFalsa(Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.DESCONOCIDO))
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    qtbot.waitUntil(lambda: d.boton_borrar.isVisibleTo(d), timeout=3000)
    assert cliente.escrituras == []  # ofrecerlo no escribe nada

    rechazo = Confirmador(False)
    monkeypatch.setattr(modulo, "confirmar", rechazo)
    d.boton_borrar.click()
    assert len(rechazo.llamadas) == 1
    titulo, texto, _aceptar, cancelar = rechazo.llamadas[0]
    assert NOMBRE_MV in texto and str(VMID) in texto  # el diálogo dice el nombre y el número
    assert cancelar == "Cancelar"
    assert ("delete", VMID) not in cliente.escrituras  # «Cancelar» no borra nada

    monkeypatch.setattr(modulo, "confirmar", Confirmador(True))
    d.boton_borrar.click()
    qtbot.waitUntil(lambda: ("delete", VMID) in cliente.escrituras, timeout=5000)
    assert cliente.escrituras.count(("delete", VMID)) == 1


def test_cerrar_el_asistente_tras_un_fallo_no_borra_nada(qtbot, cliente, monkeypatch):
    fabrica = FabricaCreacionFalsa(Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.DESCONOCIDO))
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    assert not d.en_curso
    d.reject()
    assert ("delete", VMID) not in cliente.escrituras


# --- La barra de avance solo se ve mientras hay un trabajo en marcha ---


def test_la_barra_de_avance_no_se_ve_antes_de_empezar(qtbot, cliente):
    d = hacer_dialogo(qtbot, cliente)
    assert not d.barra.isVisibleTo(d)


def test_la_barra_de_avance_se_oculta_al_detenerse_por_un_fallo(qtbot, cliente, monkeypatch):
    fabrica = FabricaCreacionFalsa(Desenlace.ERROR, error=ErrorProxLaunch(CodigoError.DESCONOCIDO))
    d = fallar_en_crear(qtbot, monkeypatch, cliente, fabrica)
    assert d.panel_progreso.isVisibleTo(d)
    assert not d.barra.isVisibleTo(d)


def test_la_barra_de_avance_se_oculta_al_terminar_bien(qtbot, cliente, monkeypatch):
    monkeypatch.setattr(modulo, "confirmar", Confirmador(True))
    d = hacer_dialogo(qtbot, cliente)
    listo_para_crear(qtbot, d)
    crear_y_esperar(qtbot, d, fase="terminado")
    assert not d.barra.isVisibleTo(d)


def test_la_barra_de_avance_se_ve_mientras_hay_trabajo(qtbot, cliente, monkeypatch):
    import threading

    liberar = threading.Event()

    class FabricaLenta(FabricaCreacionFalsa):
        def crear(self, *a, **k):
            liberar.wait(5)
            return super().crear(*a, **k)

    monkeypatch.setattr(modulo, "confirmar", Confirmador(True))
    d = hacer_dialogo(qtbot, cliente, FabricaLenta())
    listo_para_crear(qtbot, d)
    d.boton_crear.click()
    qtbot.waitUntil(lambda: d.fase == "en_curso", timeout=3000)
    assert d.barra.isVisibleTo(d)
    liberar.set()
    qtbot.waitUntil(lambda: d.fase == "terminado", timeout=5000)
    assert not d.barra.isVisibleTo(d)
