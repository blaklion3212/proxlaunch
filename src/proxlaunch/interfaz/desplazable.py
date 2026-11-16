"""Diálogos y ventanas que nunca superan el área útil de la pantalla (alto y ancho).

El contenido se envuelve en un ``QScrollArea`` y los botones de acción quedan fuera, abajo,
siempre visibles. Si la pantalla es holgada la ventana se ve igual que sin la envoltura
(mismo tamaño, sin barras); si no cabe, su tamaño se limita al área útil y el contenido se
desplaza (la barra horizontal sale solo si tampoco cabe a lo ancho). El límite se recalcula
al mostrarse, al cambiar de pantalla y cuando cambia la visibilidad de partes del contenido.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

# Holgura de alto para el marco y la barra de título (px lógicos), si aún no se miden.
MARGEN_MARCO_PREDETERMINADO = 40
# Ídem para los bordes laterales.
MARGEN_MARCO_ANCHO = 16
# Holgura lateral de los márgenes del layout del diálogo al acotar el ancho mínimo del área.
MARGEN_LATERAL_DIALOGO = 12
# Alto mínimo del área desplazable, para que el diálogo pueda encogerse en pantallas pequeñas.
ALTO_MINIMO_AREA = 80


class _AreaDesplazable(QScrollArea):
    """Área sin marco cuyo tamaño sugerido es el del contenido, sin tope propio."""

    def sizeHint(self) -> QSize:
        widget = self.widget()
        if widget is None:
            return super().sizeHint()
        tam = widget.sizeHint()
        extra = 2 * self.frameWidth()
        ancho = tam.width() + extra
        barra = self.verticalScrollBar()
        if barra.isVisible():
            ancho += self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, barra)
        return QSize(ancho, tam.height() + extra)

    # Ancho máximo que puede exigir el área como mínimo (lo fija ``AjusteDesplazable``):
    # por encima, el contenido se desplaza con la barra horizontal en vez de ensanchar la ventana.
    tope_ancho: int | None = None

    def minimumSizeHint(self) -> QSize:
        widget = self.widget()
        ancho = super().minimumSizeHint().width()
        if widget is not None:
            ancho = widget.minimumSizeHint().width() + 2 * self.frameWidth()
        if self.tope_ancho is not None:
            ancho = min(ancho, self.tope_ancho)
        return QSize(ancho, ALTO_MINIMO_AREA)


class AreaInterna(QScrollArea):
    """Área interna (sin tope propio) cuyo ancho mínimo es el real de su contenido.

    El ``minimumSizeHint`` de un ``QScrollArea`` es pequeño y ajeno al contenido, y un
    ``QSplitter`` que las reparte no respeta los mínimos reales: el contenido quedaba recortado.
    Aquí el mínimo de ancho es el del widget + marcos + la barra vertical si se ve; el
    desplazamiento del conjunto lo da el área externa de la ventana.
    """

    # Último estado de la barra vertical que se usó para el mínimo de ancho. Valores de clase:
    # Qt puede entregar eventos al filtro antes de que termine ``__init__``.
    _barra_vista = False
    _contenedor_barra: QWidget | None = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # La barra vive en un contenedor que Qt muestra y oculta según haga falta.
        contenedor = self.verticalScrollBar().parentWidget()
        self._contenedor_barra = contenedor
        if contenedor is not None:
            contenedor.installEventFilter(self)

    def setWidget(self, widget: QWidget) -> None:
        super().setWidget(widget)
        if widget is not None:  # Qt ignora None en tiempo de ejecución; aquí no debe fallar
            widget.installEventFilter(self)

    def takeWidget(self) -> QWidget:
        widget = super().takeWidget()
        if widget is not None:
            widget.removeEventFilter(self)
        return widget

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        tipo = event.type()
        if watched is self.widget() and tipo == QEvent.Type.LayoutRequest:
            self.updateGeometry()  # el mínimo del contenido pudo cambiar
        elif watched is self._contenedor_barra and tipo in (QEvent.Type.Show, QEvent.Type.Hide):
            # La barra vertical aparece o desaparece sin que el contenido cambie (el área gana
            # o pierde alto): el mínimo de ancho incluye la barra, así que se avisa al padre.
            visible = tipo == QEvent.Type.Show
            if visible != self._barra_vista:
                self._barra_vista = visible
                self.updateGeometry()
        return super().eventFilter(watched, event)

    def minimumSizeHint(self) -> QSize:
        base = super().minimumSizeHint()
        widget = self.widget()
        if widget is None:
            return base
        ancho = widget.minimumSizeHint().width() + 2 * self.frameWidth()
        barra = self.verticalScrollBar()
        if barra.isVisible():
            ancho += self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, barra)
        return QSize(ancho, base.height())


class AjusteDesplazable(QObject):
    """Mantiene el tamaño de una ventana (diálogo o ventana principal) dentro del área útil.

    ``alto_disponible`` y ``ancho_disponible`` (px lógicos) sustituyen al área útil real de la
    pantalla; sirven para pruebas y pueden cambiarse en cualquier momento (seguido de
    ``reajustar``). ``contenido`` es el widget cuyo cambio de disposición (partes que se muestran
    u ocultan) obliga a recalcular; puede omitirse. ``tamano_deseado`` es el tamaño que la
    ventana pide al abrirse (p. ej. 1240x820); se recorta al área útil y se recupera si la
    pantalla vuelve a ser más grande.
    """

    def __init__(
        self,
        ventana: QWidget,
        contenido: QWidget | None,
        alto_disponible: int | None,
        ancho_disponible: int | None = None,
        tamano_deseado: QSize | None = None,
    ) -> None:
        super().__init__(ventana)
        self._dialogo = ventana
        self._contenido = contenido
        self._conectada = False
        self._pendiente = False
        # Mínimos que quiso la ventana (setMinimumSize) y los que se aplicaron tras acotarlos.
        self._minimo_deseado = QSize(ventana.minimumWidth(), ventana.minimumHeight())
        self._minimo_aplicado = QSize(self._minimo_deseado)
        self._tamano_deseado = tamano_deseado
        if tamano_deseado is None and ventana.testAttribute(Qt.WidgetAttribute.WA_Resized):
            self._tamano_deseado = ventana.size()  # tamaño fijado con resize() antes del ajuste
        self._limite_previo = QSize(0, 0)
        self._recortado = QSize(0, 0)  # 1 en cada eje donde el tamaño deseado excedía el límite
        self._hint_previo = 0  # alto sugerido en el último reajuste con la ventana visible
        self._acotado = False  # el último reajuste tuvo que recortar el alto sugerido
        self.alto_disponible = alto_disponible
        self.ancho_disponible = ancho_disponible
        ventana.installEventFilter(self)
        if contenido is not None:
            contenido.installEventFilter(self)
        # Con el tope puesto desde ya, Qt dimensiona y centra la ventana ya acotada.
        self.reajustar()

    def _area_util(self) -> tuple[int, int] | None:
        """``(ancho, alto)`` útil de la pantalla, o ``None`` si no se conoce."""
        pantalla = self._dialogo.screen() or QGuiApplication.primaryScreen()
        real = pantalla.availableGeometry() if pantalla is not None else None
        ancho = self.ancho_disponible if self.ancho_disponible is not None else None
        alto = self.alto_disponible
        if ancho is None and real is not None:
            ancho = real.width()
        if alto is None and real is not None:
            alto = real.height()
        if ancho is None or alto is None:
            return None
        return ancho, alto

    def _margen_marco(self) -> QSize:
        d = self._dialogo
        if d.isVisible():
            ancho = d.frameGeometry().width() - d.geometry().width()
            alto = d.frameGeometry().height() - d.geometry().height()
            if alto > 0:
                return QSize(max(ancho, 0), alto)
        return QSize(MARGEN_MARCO_ANCHO, MARGEN_MARCO_PREDETERMINADO)

    def limite_tamano(self) -> QSize | None:
        """Tamaño máximo de la ventana (sin marco), o ``None`` si no se conoce la pantalla."""
        util = self._area_util()
        if util is None:
            return None
        marco = self._margen_marco()
        return QSize(max(util[0] - marco.width(), 0), max(util[1] - marco.height(), 0))

    def limite_alto(self) -> int | None:
        """Alto máximo de la ventana (sin marco), o ``None`` si no se conoce la pantalla."""
        limite = self.limite_tamano()
        return None if limite is None else limite.height()

    def limite_ancho(self) -> int | None:
        """Ancho máximo de la ventana (sin marco), o ``None`` si no se conoce la pantalla."""
        limite = self.limite_tamano()
        return None if limite is None else limite.width()

    def reajustar(self) -> None:
        """Acota el tamaño al área útil; con la ventana visible, crece si el contenido crece.

        El alto inicial es el menor entre el sugerido del contenido y el límite (Qt, por su
        cuenta, recorta las ventanas a 2/3 de la pantalla); después, si el alto sugerido aumenta
        (se muestra una parte del contenido) la ventana crece hasta lo necesario, sin pasar del
        límite. No encoge por debajo de lo que ya tenía (salvo el límite). El ancho se acota al
        límite, pero también crece hasta lo que pide el contenido (sin pasar del límite): solo si
        ni así cabe, el área desplazable muestra su barra horizontal.
        """
        d = self._dialogo
        lim = self.limite_tamano()
        if lim is None:
            return
        # El mínimo se lee antes de tocar el máximo: Qt rebaja el mínimo si supera al nuevo máximo
        # y se confundiría con un setMinimumSize de la propia ventana (dependería del historial).
        actual = QSize(d.minimumWidth(), d.minimumHeight())
        self._acotar_area(lim.width())
        # Un setMinimumSize posterior de la propia ventana se respeta, pero acotado al límite.
        if actual != self._minimo_aplicado:
            self._minimo_deseado = actual
        minimo = QSize(
            min(self._minimo_deseado.width(), lim.width()),
            min(self._minimo_deseado.height(), lim.height()),
        )
        if minimo != actual:
            d.setMinimumSize(minimo)
        self._minimo_aplicado = minimo
        d.setMaximumSize(lim.width(), lim.height())
        # Recupera el tamaño pedido si estaba recortado por el límite y ahora cabe.
        deseado = self._tamano_deseado
        if deseado is not None:
            rec = QSize(int(deseado.width() > lim.width()), int(deseado.height() > lim.height()))
            nuevo_ancho = deseado.width() if self._recortado.width() and not rec.width() else None
            nuevo_alto = deseado.height() if self._recortado.height() and not rec.height() else None
            # Aún recortado pero con más sitio que antes: ocupa el nuevo límite.
            previo = self._limite_previo
            if rec.width() and previo.width() and d.width() >= previo.width() < lim.width():
                nuevo_ancho = lim.width()
            if rec.height() and previo.height() and d.height() >= previo.height() < lim.height():
                nuevo_alto = lim.height()
            self._recortado = rec
            if nuevo_ancho is not None or nuevo_alto is not None:
                d.resize(nuevo_ancho or d.width(), nuevo_alto or d.height())
        self._limite_previo = lim
        if not d.isVisible():
            self._hint_previo = 0
            self._acotado = False
            return  # al mostrarse, Qt dimensiona con estos topes
        ancho, alto = d.width(), d.height()
        hint = d.sizeHint().height()
        # Crece al mostrarse, si el contenido aumenta o si antes estaba recortado y ahora cabe más.
        crecio = self._hint_previo == 0 or hint > self._hint_previo or self._acotado
        self._hint_previo = hint
        self._acotado = hint > lim.height()
        if crecio:
            alto = max(alto, min(hint, lim.height()))
        alto = min(alto, lim.height())
        ancho = max(min(ancho, lim.width()), self._ancho_necesario(alto, hint, lim.width()))
        if (ancho, alto) != (d.width(), d.height()):
            d.resize(ancho, alto)

    def _area(self) -> _AreaDesplazable | None:
        """Área desplazable que envuelve el contenido, si la hay."""
        viewport = self._contenido.parentWidget() if self._contenido is not None else None
        area = viewport.parentWidget() if viewport is not None else None
        return area if isinstance(area, _AreaDesplazable) else None

    def _ancho_necesario(self, alto: int, hint_alto: int, limite: int) -> int:
        """Ancho con el que el contenido cabe sin barra horizontal, acotado al ``limite``.

        Qt recorta el ancho inicial a 2/3 de la pantalla y un ``setMinimumWidth`` explícito
        anula el mínimo del layout; con una fuente ancha el contenido pediría más y saldría una
        barra horizontal aun con espacio de sobra. Con ``tamano_deseado`` se parte del mínimo
        del contenido (el sugerido es el de la ventana ya fijada); si no, del sugerido sin la
        barra vertical, que solo se suma cuando el alto final no alcanza al sugerido.
        """
        d = self._dialogo
        area = self._area()
        barra = 0
        if area is not None:
            vertical = area.verticalScrollBar()
            barra = area.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, vertical)
        if self._tamano_deseado is not None:
            base = d.minimumSizeHint().width()
        else:
            visible = area is not None and area.verticalScrollBar().isVisible()
            base = d.sizeHint().width() - (barra if visible else 0)
        necesario = base + (barra if alto < hint_alto else 0)
        return min(necesario, limite)

    def _acotar_area(self, ancho_ventana: int) -> None:
        """Indica al área desplazable cuánto ancho puede exigir como mínimo."""
        area = self._area()
        if area is not None:
            tope = max(ancho_ventana - 2 * MARGEN_LATERAL_DIALOGO, 0)
            if area.tope_ancho != tope:
                area.tope_ancho = tope
                area.updateGeometry()

    def _reajustar_diferido(self) -> None:
        # Varios cambios de visibilidad seguidos se agrupan en un solo reajuste.
        if self._pendiente:
            return
        self._pendiente = True

        def _hacer() -> None:
            self._pendiente = False
            self.reajustar()

        QTimer.singleShot(0, self, _hacer)

    def _al_cambiar_pantalla(self, *_args: object) -> None:
        self.reajustar()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Durante la destrucción del diálogo Qt aún puede entregar eventos cuando el estado
        # Python de este objeto ya se liberó: se ignoran.
        if "_dialogo" not in self.__dict__:
            return False
        tipo = event.type()
        if watched is self._dialogo and tipo == QEvent.Type.Show:
            ventana = self._dialogo.windowHandle()
            if ventana is not None and not self._conectada:
                ventana.screenChanged.connect(self._al_cambiar_pantalla)
                self._conectada = True
            self.reajustar()
        elif watched is self._dialogo and tipo == QEvent.Type.Hide:
            self._hint_previo = 0
            self._acotado = False
        elif tipo == QEvent.Type.LayoutRequest and watched in (self._dialogo, self._contenido):
            if watched is self._contenido:
                # El QScrollArea no avisa al diálogo de que cambió el alto sugerido del contenido.
                viewport = self._contenido.parentWidget() if self._contenido else None
                area = viewport.parentWidget() if viewport is not None else None
                if area is not None:
                    area.updateGeometry()
            self._reajustar_diferido()
        return False


def crear_area_desplazable(contenido: QWidget) -> QScrollArea:
    """Área sin marco que envuelve ``contenido``; las barras salen solo cuando hacen falta."""
    area = _AreaDesplazable()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    area.setWidget(contenido)
    # Sin esto el fondo del área distinto al del contenedor se notaría con ciertos temas.
    area.viewport().setAutoFillBackground(False)
    contenido.setAutoFillBackground(False)
    return area


def limitar_a_pantalla(
    dialogo: QWidget,
    contenido: QWidget | None = None,
    *,
    alto_disponible: int | None = None,
    ancho_disponible: int | None = None,
    tamano_deseado: QSize | None = None,
) -> AjusteDesplazable:
    """Acota el tamaño de una ventana que ya tiene su propia zona desplazable.

    Llamar con el diálogo construido (o al menos con su ``setMinimumSize`` ya hecho).
    """
    return AjusteDesplazable(dialogo, contenido, alto_disponible, ancho_disponible, tamano_deseado)


def hacer_desplazable(
    dialogo: QDialog, *, alto_disponible: int | None = None, ancho_disponible: int | None = None
) -> tuple[QVBoxLayout, QVBoxLayout, AjusteDesplazable]:
    """Prepara ``dialogo`` (sin layout) con contenido desplazable y pie fijo.

    Devuelve ``(capa_contenido, capa_pie, ajuste)``: el contenido va en la primera
    (se desplaza), los botones de acción en la segunda (siempre visibles, abajo).
    """
    contenido = QWidget()
    capa_contenido = QVBoxLayout(contenido)
    capa_contenido.setContentsMargins(0, 0, 0, 0)
    area = crear_area_desplazable(contenido)

    externa = QVBoxLayout(dialogo)
    externa.addWidget(area, 1)
    capa_pie = QVBoxLayout()
    capa_pie.setContentsMargins(0, 0, 0, 0)
    externa.addLayout(capa_pie)

    ajuste = AjusteDesplazable(dialogo, contenido, alto_disponible, ancho_disponible)
    return capa_contenido, capa_pie, ajuste
