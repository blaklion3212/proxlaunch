"""Ayudas para manejar la ventana principal en las pruebas de lotes (sin aserciones)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .apoyo import ClienteLoteFalso, CreacionPorVmid, sesion_falsa
from .test_ventana_principal import conectar, esperar_validacion


class Confirmaciones:
    """Sustituye ``confirmar``: registra lo que se preguntó y responde lo programado."""

    def __init__(self, respuesta: bool = True) -> None:
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, str, str, str]] = []

    def __call__(self, parent, titulo, texto, aceptar, cancelar) -> bool:
        self.llamadas.append((titulo, texto, aceptar, cancelar))
        return self.respuesta


def escribir(campo, texto: str) -> None:
    campo.setText(texto)
    campo.textEdited.emit(texto)


def preparar_lote(
    qtbot,
    entorno,
    *,
    cantidad: int = 3,
    prefijo: str = "web",
    cliente: ClienteLoteFalso | None = None,
    creacion: CreacionPorVmid | None = None,
    nodo: str | None = "pve1",
    avanzado: bool = False,
    **sesion_kw,
) -> ClienteLoteFalso:
    """Conecta con un cliente falso y deja escrito el lote en el bloque «Lote»."""
    cliente = cliente or ClienteLoteFalso()
    entorno.cliente = cliente
    entorno.creacion = creacion or CreacionPorVmid()
    conectar(qtbot, entorno, sesion_falsa(cliente=cliente, **sesion_kw))
    v = entorno.ventana
    if avanzado:
        from proxlaunch.nucleo.persistencia.preferencias import Modo

        v.establecer_modo(Modo.AVANZADO)
    b = v.bloque_lote
    escribir(b.cantidad, str(cantidad))
    escribir(b.prefijo, prefijo)
    if nodo is not None:
        b._radio_un_nodo.setChecked(True)
        b.combo_nodo.setCurrentIndex(b.combo_nodo.findData(nodo))
    esperar_validacion(qtbot, v)
    return cliente


def ver_resumen(qtbot, v) -> None:
    """Pulsa el botón principal («Ver resumen») y espera a que el plan esté dibujado."""
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: v.resumen_lote.plan is not None and not v._planificando, timeout=4000)


def crear_lote(qtbot, v, *, aceptar_thin: bool = True) -> None:
    """Confirma el resumen (el lote arranca de inmediato salvo que haya que replanificar).

    La plantilla predeterminada pide 32 GiB por máquina: con 5 o más se sobreasigna el
    almacenamiento thin y hay que marcar la casilla de riesgo (CA-L08.2).
    """
    r = v.resumen_lote
    if aceptar_thin and r.casilla_thin.isVisible():
        r.casilla_thin.setChecked(True)
    r.boton_crear.click()


def esperar_fin(qtbot, v, timeout: int = 8000) -> None:
    qtbot.waitUntil(
        lambda: (
            v._lote is not None
            and v._lote.terminado
            and not v._lote.deshaciendo
            and not v._lote.inspeccionando  # Deshacer: la inspección previa es asíncrona
        ),
        timeout=timeout,
    )


def esperar_pausa(qtbot, v) -> None:
    """Espera a que el temporizador del lote muestre el diálogo de pausa."""
    qtbot.waitUntil(lambda: v._lote is not None and v._lote.dialogo_pausa is not None, timeout=5000)


def estados(v) -> list[str]:
    snap = v._lote.libro.instantanea() if v._lote.libro else v._lote.puente.instantanea()
    return [e.estado.value for e in snap]


def hijos(v, tipo) -> list[QWidget]:
    return v.findChildren(tipo)
