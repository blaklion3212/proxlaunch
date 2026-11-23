"""Asistente de importación desde CSV: archivo, vista previa por filas y confirmación (RF-C).

El diálogo solo LEE: no cambia el formulario ni envía nada al servidor (CA-C06.9). Lectura,
interpretación y escritura de CSV corren en un hilo del ``Lanzador``; un contador de generación
descarta los resultados tardíos de un archivo, perfil o separador abandonados (§10 de la
arquitectura). Al aceptar, quien lo abre construye el lote con
``filas_lote(resultado, numeros_elegidos)`` (P-M02 B: solo las filas correctas, con las
excluidas a la vista).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

from PySide6.QtCore import QItemSelection, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from proxlaunch.interfaz.archivos_ui import (
    TipoArchivo,
    boton_ayuda_texto,
    descargar_plantilla,
    elegir_para_abrir,
    elegir_para_guardar,
    nombre_sugerido,
)
from proxlaunch.interfaz.desplazable import hacer_desplazable
from proxlaunch.interfaz.modelos_tabla import TablaCopiable
from proxlaunch.interfaz.modelos_tabla_csv import (
    FiltroProblemasCsv,
    ModeloVistaPreviaCsv,
    valor_original_visible,
)
from proxlaunch.interfaz.textos import (
    texto_aviso_archivo,
    texto_estado_con_simbolo,
    texto_fallo,
    traductor_para_archivo,
)
from proxlaunch.interfaz.trabajadores import Lanzador, Trabajador, olvidar_secretos_de_filas
from proxlaunch.interfaz.vistas.campos import etiqueta, mensaje, poner_mensaje
from proxlaunch.nucleo.csv_importacion.errores_csv import escribir_filas_con_error
from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
from proxlaunch.nucleo.csv_importacion.modelos import (
    Codificacion,
    EstadoFila,
    OpcionesCsv,
    ResultadoImportacion,
    TablaCsv,
)
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO, PerfilMaquina

_log = logging.getLogger("proxlaunch.interfaz.importar_csv")

# Separadores que ofrece el selector (el núcleo acepta estos; ``None`` = detectar).
SEPARADORES: tuple[str, ...] = (";", ",", "\t", "|")
MAX_EXCLUIDAS_EN_TEXTO = 10


# --- Trabajos que corren en el hilo (envoltorios finos del núcleo) --------------------------


def leer_e_interpretar(
    ruta: Path,
    opciones: OpcionesCsv,
    perfil_base: PerfilMaquina,
    perfiles: Sequence[PerfilMaquina],
    inv: Inventario | None,
    nodo_referencia: str | None,
    alias_extra: Mapping[str, str] | None,
    encender_base: bool | None = None,
) -> tuple[TablaCsv, ResultadoImportacion]:
    """Lee el archivo y lo interpreta. Pura salvo la lectura (solo ``O_RDONLY``).

    ``encender_base`` es el «Encender al terminar» del formulario (``None`` = se desconoce): una
    fila con ``esperar_ip`` y sin encendido efectivo da V-B60 (arquitectura §12).
    """
    tabla = leer_archivo_csv(ruta, opciones, alias_extra=alias_extra)
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base,
        perfiles=perfiles,
        inv=inv,
        nodo_referencia=nodo_referencia,
        alias_extra=alias_extra,
        encender_base=encender_base,
    )
    return tabla, resultado


def reinterpretar(
    tabla: TablaCsv,
    perfil_base: PerfilMaquina,
    perfiles: Sequence[PerfilMaquina],
    inv: Inventario | None,
    nodo_referencia: str | None,
    alias_extra: Mapping[str, str] | None,
    encender_base: bool | None = None,
) -> ResultadoImportacion:
    """Vuelve a interpretar una tabla ya leída (cambio de perfil base)."""
    return interpretar(
        tabla,
        perfil_base=perfil_base,
        perfiles=perfiles,
        inv=inv,
        nodo_referencia=nodo_referencia,
        alias_extra=alias_extra,
        encender_base=encender_base,
    )


class DialogoImportarCsv(QDialog):
    """Asistente de importación CSV.

    Constructor: ``DialogoImportarCsv(parent, *, perfiles, perfil_base_id, inv,
    nodo_referencia, lanzador, avanzado=False, alias_extra=None, tema="oscuro",
    encender_base=None)``. ``encender_base`` es el «Encender al terminar» del formulario (para
    V-B60 por fila). ``inv`` es ``None`` sin conexión: entonces solo se valida la capa 1 y no se
    puede continuar (CA-C06.10). ``avanzado`` muestra siempre codificación y separador; en
    básico el separador solo aparece si la detección es ambigua.

    Uso: ``dialogo.ejecutar()`` pide el archivo con el diálogo del sistema (o usa ``ruta``), lo
    procesa en un hilo, muestra la vista previa y devuelve ``(resultado, numeros_elegidos)`` o
    ``None`` si el usuario cancela o elige «Corregir el archivo». Para «Revisar filas…» sin
    releer el archivo, ``mostrar_resultado(tabla, resultado, nombre_archivo)`` antes de
    ``ejecutar()``.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        perfiles: Sequence[PerfilMaquina],
        perfil_base_id: str,
        inv: Inventario | None,
        nodo_referencia: str | None,
        lanzador: Lanzador,
        avanzado: bool = False,
        alias_extra: Mapping[str, str] | None = None,
        tema: str = "oscuro",
        al_resultado_tardio: Callable[[str, bool], None] | None = None,
        encender_base: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Importar desde CSV"))
        self.setModal(True)
        self.resize(980, 640)
        self._perfiles = tuple(perfiles)
        self._inv = inv
        self._nodo_referencia = nodo_referencia
        self._lanzador = lanzador
        self._avanzado = avanzado
        self._alias_extra = alias_extra
        self._encender_base = encender_base
        self._ruta: Path | None = None
        self._nombre_archivo = ""
        self._tabla: TablaCsv | None = None
        self._resultado: ResultadoImportacion | None = None
        # B6: ``True`` si las contraseñas del resultado mostrado son de esta vista previa y se
        # olvidan al reinterpretar o al cerrar sin aceptar; un resultado ajeno (el del lote
        # que ya está en pantalla) no se toca.
        self._resultado_propio = True
        self._opciones = OpcionesCsv()
        self._generacion = 0
        self._ocupado = False
        self._trabajo: Trabajador | None = None
        self._cargando_combos = False
        # Resultado de una escritura que termina con el diálogo ya cerrado: (texto, es_error)
        # se entrega a quien abrió el diálogo y no se toca ningún widget.
        self._al_resultado_tardio = al_resultado_tardio
        self._cerrado = False
        self._perfil_base = self._buscar_perfil(perfil_base_id)
        self._construir(tema)
        self._actualizar_estado()

    # --- Construcción --------------------------------------------------------------------

    def _buscar_perfil(self, id_perfil: str) -> PerfilMaquina:
        for p in self._perfiles:
            if p.id == id_perfil:
                return p
        for p in self._perfiles:
            if p.id == ID_PREDETERMINADO:
                return p
        return self._perfiles[0]

    def _construir(self, tema: str) -> None:
        capa, capa_pie, _ = hacer_desplazable(self)

        capa.addWidget(
            etiqueta(
                self.tr(
                    "Cada fila del archivo es una máquina. Aquí solo se revisa: no se crea nada "
                    "hasta que confirmes el resumen del lote."
                ),
                secundario=True,
            )
        )
        # MVP 4: columnas del sistema operativo (RF-O28).
        capa.addWidget(
            etiqueta(
                self.tr(
                    "Para elegir de dónde sale el sistema operativo usa las columnas «origen» "
                    "(iso, importar o clonar) y «fuente» (el nombre del ISO, de la imagen o de "
                    "la plantilla en el servidor). «fuente» no admite direcciones web ni rutas."
                ),
                secundario=True,
            )
        )
        # Archivo.
        fila_archivo = QHBoxLayout()
        self.etiqueta_archivo = QLabel(self.tr("Todavía no elegiste un archivo."))
        self.etiqueta_archivo.setAccessibleName(self.tr("Archivo CSV"))
        self.etiqueta_archivo.setTextFormat(Qt.TextFormat.PlainText)
        self.boton_elegir = QPushButton(self.tr("Elegir otro archivo…"))
        self.boton_plantilla = QPushButton(self.tr("Descargar plantilla…"))
        self.boton_plantilla.setToolTip(
            self.tr("Guarda un CSV de ejemplo con las columnas que entiende ProxLaunch.")
        )
        fila_archivo.addWidget(self.etiqueta_archivo, 1)
        fila_archivo.addWidget(self.boton_elegir)
        fila_archivo.addWidget(self.boton_plantilla)
        # Fase C (RF-C6.3): firewall y red del clon, en una ayuda «?» para no alargar el diálogo.
        fila_archivo.addWidget(
            boton_ayuda_texto(
                self.tr(
                    "Para poner firewall usa «cortafuegos» (sí o no) y «grupo_seguridad» (el "
                    "nombre de un grupo que ya exista en Proxmox). Para cambiar la red de una "
                    "copia al clonar, pon «reescribir_red» en sí: se aplican «red», «vlan», "
                    "«modelo_red», «mtu» y «limite_red» a la tarjeta net0 de la copia. «red» "
                    "puede ser un bridge o una red virtual (VNet). Una celda vacía usa el valor "
                    "del formulario."
                )
            )
        )
        capa.addLayout(fila_archivo)

        # Perfil base, codificación y separador.
        fila_opciones = QHBoxLayout()
        self.combo_perfil = QComboBox()
        self.combo_perfil.setAccessibleName(self.tr("Perfil base"))
        for p in self._perfiles:
            self.combo_perfil.addItem(p.nombre, p.id)
        self.combo_perfil.setCurrentIndex(max(self.combo_perfil.findData(self._perfil_base.id), 0))
        etiqueta_perfil = QLabel(self.tr("Perfil base:"))
        etiqueta_perfil.setBuddy(self.combo_perfil)
        fila_opciones.addWidget(etiqueta_perfil)
        fila_opciones.addWidget(self.combo_perfil)
        fila_opciones.addWidget(
            boton_ayuda_texto(
                self.tr(
                    "El perfil base aporta todo lo que el archivo no diga (procesador, discos, "
                    "red…). Las columnas del archivo siempre mandan sobre el perfil."
                )
            )
        )

        self.combo_codificacion = QComboBox()
        self.combo_codificacion.setAccessibleName(self.tr("Codificación del archivo"))
        self.combo_codificacion.addItem(self.tr("Detectar"), None)
        for cod, nombre in (
            (Codificacion.UTF8_BOM, "UTF-8 (BOM)"),
            (Codificacion.UTF8, "UTF-8"),
            (Codificacion.UTF16, "UTF-16"),
            (Codificacion.WINDOWS_1252, "Windows-1252"),
            (Codificacion.ISO_8859_1, "ISO-8859-1"),
        ):
            self.combo_codificacion.addItem(nombre, cod)
        self.etiqueta_codificacion = QLabel(self.tr("Codificación:"))
        self.etiqueta_codificacion.setBuddy(self.combo_codificacion)
        self.ayuda_codificacion = boton_ayuda_texto(
            self.tr(
                "Es la forma en que el archivo guarda las letras con acento. Si ves símbolos "
                "raros, prueba otra; lo más habitual es «UTF-8» o «Windows-1252»."
            )
        )

        self.combo_separador = QComboBox()
        self.combo_separador.setAccessibleName(self.tr("Separador de columnas"))
        self.combo_separador.addItem(self.tr("Detectar"), None)
        nombres_sep = {
            ";": self.tr("; (punto y coma)"),
            ",": self.tr(", (coma)"),
            "\t": self.tr("Tabulador"),
            "|": self.tr("| (barra vertical)"),
        }
        for sep in SEPARADORES:
            self.combo_separador.addItem(nombres_sep[sep], sep)
        self.etiqueta_separador = QLabel(self.tr("Separador:"))
        self.etiqueta_separador.setBuddy(self.combo_separador)
        self.ayuda_separador = boton_ayuda_texto(
            self.tr(
                "Es el carácter que separa las columnas. Excel en español usa «;» y en inglés «,». "
                "ProxLaunch lo detecta solo; cámbialo únicamente si las columnas salen mal."
            )
        )
        for w in (
            self.etiqueta_codificacion,
            self.combo_codificacion,
            self.ayuda_codificacion,
            self.etiqueta_separador,
            self.combo_separador,
            self.ayuda_separador,
        ):
            fila_opciones.addWidget(w)
        fila_opciones.addStretch(1)
        capa.addLayout(fila_opciones)

        # Avisos y errores globales.
        self.aviso_sin_conexion = mensaje(aviso=True)
        self.error_lectura = mensaje(error=True)
        self.aviso_separador = mensaje(aviso=True)
        self.avisos_archivo = mensaje(aviso=True)
        self.estado_operacion = etiqueta("", secundario=True)
        for w in (
            self.aviso_sin_conexion,
            self.error_lectura,
            self.aviso_separador,
            self.avisos_archivo,
        ):
            capa.addWidget(w)
        if self._inv is None:
            poner_mensaje(
                self.aviso_sin_conexion,
                self.tr(
                    "Sin conexión: aún no se comprobó contra el servidor. Conéctate a un "
                    "servidor para poder continuar."
                ),
                aviso=True,
            )

        # Resumen y filtros.
        fila_resumen = QHBoxLayout()
        self.etiqueta_resumen = QLabel()
        self.etiqueta_resumen.setAccessibleName(self.tr("Resumen de la vista previa"))
        self.casilla_problemas = QCheckBox(self.tr("Mostrar solo problemas"))
        self.boton_copiar = QPushButton(self.tr("Copiar errores"))
        self.boton_copiar.setToolTip(self.tr("Copia al portapapeles la lista de errores."))
        fila_resumen.addWidget(self.etiqueta_resumen, 1)
        fila_resumen.addWidget(self.casilla_problemas)
        fila_resumen.addWidget(self.boton_copiar)
        capa.addLayout(fila_resumen)

        # Tabla (modelo, no un widget por fila) y detalle.
        self.modelo = ModeloVistaPreviaCsv(self)
        self.modelo.establecer_tema(tema)
        self.filtro = FiltroProblemasCsv(self)
        self.filtro.setSourceModel(self.modelo)
        self.tabla = TablaCopiable(self.tr("Filas del archivo"))
        self.tabla.setModel(self.filtro)
        self.tabla.setSelectionMode(TablaCopiable.SelectionMode.SingleSelection)
        capa.addWidget(self.tabla, 3)

        self.detalle = QPlainTextEdit()
        self.detalle.setReadOnly(True)
        self.detalle.setAccessibleName(self.tr("Detalle de la fila seleccionada"))
        self.detalle.setPlaceholderText(
            self.tr("Selecciona una fila para ver sus problemas y los valores originales.")
        )
        self.detalle.setMaximumHeight(130)
        capa.addWidget(self.detalle, 1)
        capa_pie.addWidget(self.estado_operacion)  # siempre visible, junto a los botones

        # Botones.
        pie = QHBoxLayout()
        self.boton_errores = QPushButton(self.tr("Descargar filas con error…"))
        self.boton_errores.setToolTip(
            self.tr("Guarda un CSV con solo las filas con error, listo para corregir y reimportar.")
        )
        self.boton_corregir = QPushButton(self.tr("Corregir el archivo"))
        self.boton_cancelar = QPushButton(self.tr("Cancelar"))
        self.boton_continuar = QPushButton(self.tr("Continuar"))
        pie.addWidget(self.boton_errores)
        pie.addStretch(1)
        pie.addWidget(self.boton_cancelar)
        pie.addWidget(self.boton_corregir)
        pie.addWidget(self.boton_continuar)
        capa_pie.addLayout(pie)
        for b in (self.boton_corregir, self.boton_cancelar, self.boton_continuar):
            b.setAutoDefault(False)

        # Conexiones.
        self.boton_elegir.clicked.connect(self._elegir_otro)
        self.boton_plantilla.clicked.connect(self._descargar_plantilla)
        self.boton_errores.clicked.connect(self._descargar_errores)
        self.boton_copiar.clicked.connect(self._copiar_errores)
        self.boton_corregir.clicked.connect(self.reject)
        self.boton_cancelar.clicked.connect(self.reject)
        self.boton_continuar.clicked.connect(self._continuar)
        self.casilla_problemas.toggled.connect(self.filtro.establecer_solo_problemas)
        self.combo_perfil.currentIndexChanged.connect(self._al_cambiar_perfil)
        self.combo_codificacion.currentIndexChanged.connect(self._al_cambiar_opciones)
        self.combo_separador.currentIndexChanged.connect(self._al_cambiar_opciones)
        self.modelo.seleccion_cambiada.connect(self._actualizar_estado)
        self.tabla.selectionModel().selectionChanged.connect(self._al_seleccionar)

    # --- API pública ----------------------------------------------------------------------

    @property
    def tabla_csv(self) -> TablaCsv | None:
        """La ``TablaCsv`` leída (para volver a abrir la vista previa o exportar errores)."""
        return self._tabla

    @property
    def resultado(self) -> ResultadoImportacion | None:
        return self._resultado

    @property
    def nombre_archivo(self) -> str:
        """Solo el nombre del archivo, nunca la ruta."""
        return self._nombre_archivo

    @property
    def perfil_base(self) -> PerfilMaquina:
        return self._perfil_base

    @property
    def ocupado(self) -> bool:
        """``True`` mientras un hilo lee o interpreta."""
        return self._ocupado

    def numeros_elegidos(self) -> tuple[int, ...]:
        """Números de fila marcados (los que no tienen error y el usuario no desmarcó)."""
        return self.modelo.numeros_elegidos()

    @property
    def hay_errores(self) -> bool:
        return self.modelo.conteos()[2] > 0

    @property
    def puede_continuar(self) -> bool:
        """Hay resultado, hay conexión, no hay trabajo en curso y queda al menos una fila."""
        return (
            self._resultado is not None
            and self._inv is not None
            and not self._ocupado
            and bool(self.numeros_elegidos())
        )

    def cargar_archivo(self, ruta: Path) -> None:
        """Lee y valida ``ruta`` en un hilo; la vista previa se rellena al terminar."""
        self._ruta = ruta
        self._nombre_archivo = ruta.name
        self._opciones = OpcionesCsv()
        self._cargando_combos = True
        self.combo_codificacion.setCurrentIndex(0)
        self.combo_separador.setCurrentIndex(0)
        self._cargando_combos = False
        self._lanzar_lectura()

    def mostrar_resultado(
        self,
        tabla: TablaCsv,
        resultado: ResultadoImportacion,
        nombre_archivo: str,
        *,
        propio: bool = False,
    ) -> None:
        """Muestra un resultado ya calculado (reabrir la vista previa, «Revisar filas…»).

        ``propio``: el resultado se calculó solo para esta vista previa (sus contraseñas se
        olvidan al reinterpretar o al cancelar). Con ``False`` es el del lote que ya está en
        pantalla y el diálogo no toca sus contraseñas.
        """
        self._generacion += 1
        self._ruta = None
        self._nombre_archivo = nombre_archivo
        self._tabla = tabla
        self._perfil_base = self._buscar_perfil(resultado.perfil_base_id)
        self._cargando_combos = True
        self.combo_perfil.setCurrentIndex(max(self.combo_perfil.findData(self._perfil_base.id), 0))
        self._cargando_combos = False
        self._aplicar_resultado(resultado, propio=propio)

    def ejecutar(
        self, ruta: Path | None = None
    ) -> tuple[ResultadoImportacion, tuple[int, ...]] | None:
        """Muestra el asistente. ``(resultado, números elegidos)`` si se continúa, si no ``None``.

        Si no hay resultado previo y no se pasa ``ruta``, primero pregunta el archivo con el
        diálogo del sistema; si el usuario cancela, devuelve ``None`` sin abrir el asistente.
        """
        if self._resultado is None:
            if ruta is None:
                ruta = elegir_para_abrir(self.parentWidget(), TipoArchivo.CSV)
                if ruta is None:
                    return None
            self.cargar_archivo(ruta)
        if self.exec() != QDialog.DialogCode.Accepted or self._resultado is None:
            return None
        return self._resultado, self.numeros_elegidos()

    # --- Lectura en hilo --------------------------------------------------------------------

    def _si_vigente(
        self, generacion: int, accion: Callable[[], None], *, descartable: object = None
    ) -> None:
        """Ejecuta ``accion`` solo si no hubo un trabajo más reciente ni se cerró el diálogo.

        Si el resultado llega tarde (``descartable``) se descarta y se olvidan sus contraseñas
        (B6): nadie más lo va a usar.
        """
        if generacion == self._generacion:
            accion()
            return
        resultado = descartable[1] if isinstance(descartable, tuple) else descartable
        if isinstance(resultado, ResultadoImportacion):
            olvidar_secretos_de_filas(resultado.filas)

    def _olvidar_vista_previa(self, *, salvo: Collection[int] = ()) -> None:
        """Olvida las contraseñas del resultado propio de la vista previa (B6), menos las de las
        filas de número ``salvo`` (las que se aceptan)."""
        resultado = self._resultado
        if resultado is None or not self._resultado_propio:
            return
        olvidar_secretos_de_filas([f for f in resultado.filas if f.numero not in salvo])

    def _poner_ocupado(self, ocupado: bool) -> None:
        self._ocupado = ocupado
        self.combo_perfil.setEnabled(not ocupado)
        self.combo_codificacion.setEnabled(not ocupado)
        self.combo_separador.setEnabled(not ocupado)
        self.boton_elegir.setEnabled(not ocupado)
        if ocupado:
            self.estado_operacion.setText(self.tr("Leyendo el archivo…"))
        else:
            self.estado_operacion.setText("")
        self._actualizar_estado()

    def _lanzar_lectura(self) -> None:
        if self._ruta is None:
            return
        self._generacion += 1
        generacion = self._generacion
        self._poner_ocupado(True)
        poner_mensaje(self.error_lectura, None)
        self._trabajo = self._lanzador.lanzar(
            leer_e_interpretar,
            self._ruta,
            self._opciones,
            self._perfil_base,
            self._perfiles,
            self._inv,
            self._nodo_referencia,
            self._alias_extra,
            self._encender_base,
            al_terminar=lambda r: self._si_vigente(
                generacion, lambda: self._al_leer(r), descartable=r
            ),
            al_fallar=lambda e: self._si_vigente(generacion, lambda: self._al_fallar(e)),
        )

    def _lanzar_reinterpretacion(self) -> None:
        if self._tabla is None:
            return
        self._generacion += 1
        generacion = self._generacion
        self._poner_ocupado(True)
        self._trabajo = self._lanzador.lanzar(
            reinterpretar,
            self._tabla,
            self._perfil_base,
            self._perfiles,
            self._inv,
            self._nodo_referencia,
            self._alias_extra,
            self._encender_base,
            al_terminar=lambda r: self._si_vigente(
                generacion, lambda: self._al_reinterpretar(r), descartable=r
            ),
            al_fallar=lambda e: self._si_vigente(generacion, lambda: self._al_fallar(e)),
        )

    def _al_leer(self, par: tuple[TablaCsv, ResultadoImportacion]) -> None:
        self._tabla, resultado = par
        self._trabajo = None
        self._aplicar_resultado(resultado)

    def _al_reinterpretar(self, resultado: ResultadoImportacion) -> None:
        self._trabajo = None
        self._aplicar_resultado(resultado)

    def _al_fallar(self, error: ErrorProxLaunch) -> None:
        """Error de todo el archivo (E-M01, E-M05..E-M10): no hay vista previa que mostrar."""
        self._trabajo = None
        self._olvidar_vista_previa()
        self._tabla = None
        self._resultado = None
        self.modelo.establecer_resultado(None)
        self._poner_ocupado(False)
        poner_mensaje(self.error_lectura, texto_fallo(error))
        poner_mensaje(self.avisos_archivo, None)
        poner_mensaje(self.aviso_separador, None)
        self.detalle.clear()
        self._actualizar_estado()

    # --- Mostrar el resultado -----------------------------------------------------------------

    def _aplicar_resultado(self, resultado: ResultadoImportacion, *, propio: bool = True) -> None:
        if self._resultado is not resultado:
            self._olvidar_vista_previa()  # B6: la interpretación anterior ya no se usa
        self._resultado = resultado
        self._resultado_propio = propio
        self.modelo.establecer_resultado(resultado)
        poner_mensaje(self.error_lectura, None)
        lineas = [texto_aviso_archivo(a) for a in resultado.avisos]
        poner_mensaje(self.avisos_archivo, "\n".join(lineas) if lineas else None, aviso=True)
        self._mostrar_opciones_de_lectura(resultado)
        self.detalle.clear()
        self._poner_ocupado(False)
        if self.filtro.rowCount():
            self.tabla.selectRow(0)

    def _mostrar_opciones_de_lectura(self, resultado: ResultadoImportacion) -> None:
        """Muestra los selectores de codificación y separador si hace falta (CA-C06.6)."""
        det = resultado.deteccion
        ambiguo = det.ambiguo and self._opciones.separador is None
        self.etiqueta_codificacion.setVisible(self._avanzado)
        self.combo_codificacion.setVisible(self._avanzado)
        self.ayuda_codificacion.setVisible(self._avanzado)
        visible_sep = self._avanzado or ambiguo
        self.etiqueta_separador.setVisible(visible_sep)
        self.combo_separador.setVisible(visible_sep)
        self.ayuda_separador.setVisible(visible_sep)
        if ambiguo:
            poner_mensaje(
                self.aviso_separador,
                self.tr(
                    "No se pudo saber qué separador usa el archivo. Elige uno en la lista "
                    "«Separador»."
                ),
                aviso=True,
            )
        else:
            poner_mensaje(self.aviso_separador, None)

    def _texto_codificacion(self, cod: Codificacion) -> str:
        nombres = {
            Codificacion.UTF8_BOM: "UTF-8 (BOM)",
            Codificacion.UTF8: "UTF-8",
            Codificacion.UTF16: "UTF-16",
            Codificacion.WINDOWS_1252: "Windows-1252",
            Codificacion.ISO_8859_1: "ISO-8859-1",
        }
        return nombres[cod]

    def _texto_separador(self, sep: str) -> str:
        if sep == "\t":
            return self.tr("tabulador")
        return f"«{sep}»"

    def _actualizar_estado(self) -> None:
        """Rótulos, contadores y botones según el resultado y el modo de errores."""
        resultado = self._resultado
        if self._nombre_archivo:
            self.etiqueta_archivo.setText(self._nombre_archivo)
        if resultado is None:
            self.etiqueta_resumen.setText("")
        else:
            correctas, avisos, errores = self.modelo.conteos()
            total = len(resultado.filas)
            cabecera = self.tr("Codificación {codificacion} · separador {separador} · ").format(
                codificacion=self._texto_codificacion(resultado.codificacion),
                separador=self._texto_separador(resultado.deteccion.separador),
            )
            filas = self.tr("1 fila") if total == 1 else self.tr("%n filas", None, total)
            detalle = self.tr("{c} correctas, {a} con aviso, {e} con error").format(
                c=correctas, a=avisos, e=errores
            )
            self.etiqueta_resumen.setText(f"{cabecera}{filas}: {detalle}")
        con_errores = self.hay_errores
        elegidas = len(self.numeros_elegidos())
        self.boton_corregir.setVisible(con_errores)
        self.boton_cancelar.setVisible(not con_errores)
        self.boton_errores.setEnabled(con_errores and not self._ocupado)
        self.boton_copiar.setEnabled(con_errores)
        if not con_errores:
            texto_continuar = self.tr("Continuar")
        elif elegidas == 0:
            texto_continuar = self.tr("No hay filas correctas para importar")
        elif elegidas == 1:
            texto_continuar = self.tr("Importar solo la fila correcta")
        else:
            texto_continuar = self.tr("Importar solo las %n filas correctas", None, elegidas)
        self.boton_continuar.setText(texto_continuar)
        self.boton_continuar.setEnabled(self.puede_continuar)
        principal = self.boton_corregir if con_errores else self.boton_continuar
        otro = self.boton_continuar if con_errores else self.boton_corregir
        principal.setProperty("primario", True)
        otro.setProperty("primario", False)
        for b in (principal, otro):
            b.style().unpolish(b)
            b.style().polish(b)
        principal.setDefault(principal.isEnabled())
        if self._resultado is not None and self._inv is None:
            self.boton_continuar.setToolTip(
                self.tr("Conéctate a un servidor para poder continuar.")
            )
        elif self._resultado is not None and not elegidas:
            self.boton_continuar.setToolTip(self.tr("No queda ninguna fila para importar."))
        else:
            self.boton_continuar.setToolTip("")

    # --- Interacción -----------------------------------------------------------------------

    def _al_cambiar_perfil(self, _indice: int) -> None:
        if self._cargando_combos:
            return
        id_perfil = self.combo_perfil.currentData()
        self._perfil_base = self._buscar_perfil(str(id_perfil))
        self._lanzar_reinterpretacion()

    def _al_cambiar_opciones(self, _indice: int) -> None:
        if self._cargando_combos or self._ruta is None:
            return
        self._opciones = OpcionesCsv(
            codificacion=self.combo_codificacion.currentData(),
            separador=self.combo_separador.currentData(),
        )
        self._lanzar_lectura()

    def _elegir_otro(self) -> None:
        ruta = elegir_para_abrir(self, TipoArchivo.CSV)
        if ruta is not None:
            self.cargar_archivo(ruta)

    def _descargar_plantilla(self) -> None:
        descargar_plantilla(
            self,
            self._lanzador,
            al_terminar=lambda _r: self._informar_operacion(self.tr("Se guardó la plantilla.")),
            al_fallar=self._mostrar_error_operacion,
        )

    def _mostrar_error_operacion(self, error: ErrorProxLaunch) -> None:
        self._informar_operacion(texto_fallo(error), es_error=True)

    def _informar_operacion(self, texto: str, *, es_error: bool = False) -> None:
        """Resultado de una escritura: en el diálogo, o en la ventana principal si ya se cerró."""
        if self._cerrado:
            if self._al_resultado_tardio is not None:
                self._al_resultado_tardio(texto, es_error)
            return
        self.estado_operacion.setText(texto)

    def _descargar_errores(self) -> None:
        resultado, tabla = self._resultado, self._tabla
        if resultado is None or tabla is None or not self.hay_errores:
            return
        base = Path(self._nombre_archivo or "importacion").stem
        ruta = elegir_para_guardar(
            self,
            TipoArchivo.CSV,
            nombre_sugerido(TipoArchivo.CSV, self.tr("{base}-errores").format(base=base)),
        )
        if ruta is None:
            return
        sep = resultado.deteccion.separador
        separador = sep if sep in (";", ",") else ";"
        self._lanzador.lanzar(
            escribir_filas_con_error,
            ruta,
            tabla,
            resultado,
            traductor_para_archivo(resultado.columnas),
            separador=separador,
            al_terminar=lambda _r: self._informar_operacion(
                self.tr("Se guardó el archivo con las filas con error.")
            ),
            al_fallar=self._mostrar_error_operacion,
        )

    def _copiar_errores(self) -> None:
        lineas = self.modelo.lineas_de_error()
        if not lineas:
            return
        QApplication.clipboard().setText("\n".join(lineas))
        self.estado_operacion.setText(self.tr("Se copiaron %n errores.", None, len(lineas)))

    def _al_seleccionar(self, _nuevo: QItemSelection, _viejo: QItemSelection) -> None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            self.detalle.clear()
            return
        origen = self.filtro.mapToSource(filas[0])
        self.detalle.setPlainText(self._texto_detalle(origen.row()))

    def _texto_detalle(self, fila: int) -> str:
        """Problemas de la fila y valores originales del archivo (CA-C06.3, CA-C06.4)."""
        f = self.modelo.fila_en(fila)
        resultado = self._resultado
        if f is None or resultado is None:
            return ""
        partes = [
            self.tr("Fila {n} · {nombre} · {estado}").format(
                n=f.numero, nombre=f.nombre or "—", estado=texto_estado_con_simbolo(f.estado)
            )
        ]
        problemas = self.modelo.lineas_de_problema(fila)
        if problemas:
            partes.extend(problemas)
        else:
            partes.append(self.tr("Sin problemas."))
        encabezados = resultado.columnas.encabezados
        originales = [
            self.tr("{columna}: Valor del archivo: «{valor}»").format(
                columna=encabezados.get(canonica, canonica),
                valor=valor_original_visible(canonica, valor),
            )
            for canonica, valor in f.originales.items()
        ]
        if originales:
            partes.append("")
            partes.extend(originales)
        return "\n".join(partes)

    # --- Continuar -----------------------------------------------------------------------

    def textos_excluidas(self) -> list[str]:
        """Una línea por fila que no entra: «Fila 3 · web-02 (tiene un error)»."""
        lineas = []
        for f in self.modelo.numeros_excluidos():
            motivo = (
                self.tr("tiene un error")
                if f.estado == EstadoFila.CON_ERROR
                else self.tr("la excluiste tú")
            )
            lineas.append(
                self.tr("Fila {n} · {nombre} ({motivo})").format(
                    n=f.numero, nombre=f.nombre or "—", motivo=motivo
                )
            )
        return lineas

    def confirmar_exclusiones(self) -> bool:
        """Pide confirmar que se importa solo una parte, listando las excluidas (CA-C07.2).

        El foco inicial va a «Cancelar». Es un método aparte para poder sustituirlo en pruebas.
        """
        excluidas = self.textos_excluidas()
        elegidas = len(self.numeros_elegidos())
        total = len(self._resultado.filas) if self._resultado is not None else elegidas
        visibles = excluidas[:MAX_EXCLUIDAS_EN_TEXTO]
        resto = len(excluidas) - len(visibles)
        texto = self.tr("Se importarán {n} de {total} filas del archivo.").format(
            n=elegidas, total=total
        )
        texto += "\n\n" + self.tr("No se importarán estas filas:") + "\n"
        texto += "\n".join(f"• {t}" for t in visibles)
        if resto > 0:
            texto += "\n" + self.tr("y %n más (míralas en «Mostrar detalles»)", None, resto)
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Icon.Warning)
        caja.setWindowTitle(self.tr("Importar solo una parte del archivo"))
        caja.setText(texto)
        caja.setTextFormat(Qt.TextFormat.PlainText)
        if resto > 0:
            caja.setDetailedText("\n".join(excluidas))
        aceptar = caja.addButton(self.tr("Importar esas filas"), QMessageBox.ButtonRole.AcceptRole)
        cancelar = caja.addButton(self.tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
        caja.setDefaultButton(cancelar)
        caja.setEscapeButton(cancelar)
        cancelar.setFocus()
        caja.exec()
        return caja.clickedButton() is aceptar

    def _continuar(self) -> None:
        if not self.puede_continuar:
            return
        if self.modelo.numeros_excluidos() and not self.confirmar_exclusiones():
            return
        self.accept()

    # --- Cierre -----------------------------------------------------------------------------

    def showEvent(self, evento: QShowEvent) -> None:
        self._cerrado = False
        super().showEvent(evento)

    def done(self, resultado: int) -> None:
        """Al cerrar se invalidan los trabajos pendientes (patrón de generación)."""
        self._generacion += 1
        self._cerrado = True
        if self._trabajo is not None:
            self._trabajo.cancelar()
            self._trabajo = None
        if resultado == QDialog.DialogCode.Accepted and self._resultado is not None:
            # Se aceptan las filas elegidas: sus contraseñas pasan al lote; las demás se olvidan.
            self._olvidar_vista_previa(salvo=set(self.numeros_elegidos()))
        else:
            # B6: sin aceptar, ninguna contraseña de la vista previa sobrevive y se suelta la
            # tabla cruda (sus celdas llevan las contraseñas en claro).
            self._olvidar_vista_previa()
            self._resultado = None
            self._tabla = None
        super().done(resultado)
