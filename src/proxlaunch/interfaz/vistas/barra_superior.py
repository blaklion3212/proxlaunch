"""Barra superior: logo, perfil, versión, topología e indicador SSL (RF-09, RF-10, RF-06)."""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from proxlaunch.nucleo.modelos.inventario import Topologia

_ALTO_LOGO = 36


def cargar_svg(nombre: str, tamano: QSize, razon: float = 1.0) -> QPixmap:
    """Dibuja un SVG de ``recursos/marca`` en un pixmap nítido (``razon`` = escala de pantalla)."""
    datos = resources.files("proxlaunch.recursos").joinpath("marca", nombre).read_bytes()
    renderer = QSvgRenderer(datos)
    destino = QSize(int(tamano.width() * razon), int(tamano.height() * razon))
    pixmap = QPixmap(destino)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    renderer.render(pintor)
    pintor.end()
    pixmap.setDevicePixelRatio(razon)
    return pixmap


def nombre_simbolo(tema: str) -> str:
    """El símbolo «oscuro» está pensado para fondos oscuros, y viceversa."""
    return "proxlaunch-simbolo-claro.svg" if tema == "claro" else "proxlaunch-simbolo-oscuro.svg"


def nombre_logotipo(tema: str) -> str:
    return "proxlaunch-logotipo-claro.svg" if tema == "claro" else "proxlaunch-logotipo-oscuro.svg"


class BarraSuperior(QFrame):
    """Muestra el estado de la conexión; su fondo es oscuro en ambos temas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BarraSuperior")
        self._logo = QLabel()
        self._marca = QLabel(QCoreApplication.translate("BarraSuperior", "ProxLaunch"))
        fuente = self._marca.font()
        fuente.setBold(True)
        fuente.setPointSize(fuente.pointSize() + 3)
        self._marca.setFont(fuente)
        self._perfil = QLabel()
        self._version = QLabel()
        self._topologia = QLabel()
        self._ssl = QLabel()
        # Los textos con datos del servidor (perfil, versión, nombre del clúster) son texto plano.
        for w in (self._perfil, self._version, self._topologia, self._ssl):
            w.setTextFormat(Qt.TextFormat.PlainText)
        self._ssl.setToolTip(
            QCoreApplication.translate(
                "BarraSuperior",
                "La identidad del servidor no se está comprobando. Úsalo solo en redes de prueba.",
            )
        )
        capa = QHBoxLayout(self)
        capa.setContentsMargins(12, 6, 12, 6)
        capa.setSpacing(14)
        capa.addWidget(self._logo)
        capa.addWidget(self._marca)
        capa.addSpacing(16)
        for w in (self._perfil, self._version, self._topologia):
            capa.addWidget(w)
        capa.addStretch(1)
        capa.addWidget(self._ssl)
        self.actualizar_logo("oscuro")
        self.limpiar()

    def actualizar_logo(self, tema: str) -> None:
        """La barra es oscura en ambos temas: se usa siempre el símbolo para fondos oscuros."""
        del tema
        razon = self.devicePixelRatioF()
        self._logo.setPixmap(
            cargar_svg(nombre_simbolo("oscuro"), QSize(_ALTO_LOGO, _ALTO_LOGO), razon)
        )

    def limpiar(self) -> None:
        """Estado sin conexión."""
        self._perfil.setText(QCoreApplication.translate("BarraSuperior", "Sin conexión"))
        for w in (self._version, self._topologia, self._ssl):
            w.clear()
            w.hide()

    def establecer_conexion(
        self,
        perfil: str,
        version: str,
        forzada: bool,
        ssl_sin_verificar: bool,
        usuario: str = "",
    ) -> None:
        """Muestra perfil, versión, «(forzada)» y el indicador SSL."""
        texto_perfil = perfil if not usuario else f"{perfil} · {usuario}"
        self._perfil.setText(texto_perfil)
        texto_version = QCoreApplication.translate("BarraSuperior", "Proxmox VE {version}").format(
            version=version
        )
        if forzada:
            texto_version += " " + QCoreApplication.translate("BarraSuperior", "(forzada)")
        self._version.setText(texto_version)
        self._version.show()
        if ssl_sin_verificar:
            self._ssl.setText(
                "⚠ " + QCoreApplication.translate("BarraSuperior", "Conexión sin verificar")
            )
            self._ssl.show()
        else:
            self._ssl.hide()

    def establecer_topologia(self, topologia: Topologia | None, degradada: bool = False) -> None:
        """«Clúster «x» — 3 nodos», «Servidor individual» o topología desconocida (A-6)."""
        if topologia is None:
            self._topologia.hide()
            return
        n = len(topologia.nodos)
        if degradada:
            texto = QCoreApplication.translate(
                "BarraSuperior", "Topología desconocida ({n} nodos)"
            ).format(n=n)
        elif topologia.es_cluster:
            texto = QCoreApplication.translate(
                "BarraSuperior", "Clúster «{nombre}» — {n} nodos"
            ).format(nombre=topologia.nombre_cluster or "", n=n)
        else:
            texto = QCoreApplication.translate("BarraSuperior", "Servidor individual")
        self._topologia.setText(texto)
        self._topologia.show()

    @property
    def texto_version(self) -> str:
        return self._version.text()

    @property
    def texto_topologia(self) -> str:
        return self._topologia.text()

    @property
    def texto_ssl(self) -> str:
        return self._ssl.text() if not self._ssl.isHidden() else ""
