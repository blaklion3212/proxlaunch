"""Diálogo de conexión: perfiles, token o contraseña, huella SSL y 2FA (RF-01 a RF-08).

El diálogo conduce todo el flujo en segundo plano y se mantiene abierto hasta conectar,
para mostrar los errores junto a los campos (el botón se rehabilita tras un fallo).
Orden del flujo, sin enviar credenciales antes de resolver la huella (RNF-07):
huellas -> confianza -> conexión -> segundo factor (si lo pide el servidor).
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping, Sequence

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from proxlaunch.interfaz.ayuda import ayuda
from proxlaunch.interfaz.dialogos.dos_factores import DialogoDosFactores
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.huella import DialogoHuella
from proxlaunch.interfaz.textos import texto_aviso, texto_error, texto_problema
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.interfaz.vistas.campos import (
    EnlaceLabel,
    FilaCampo,
    boton_ayuda,
    etiqueta,
    mensaje,
    poner_mensaje,
)
from proxlaunch.nucleo.api.autenticacion import DesafioTFA, TipoTFA
from proxlaunch.nucleo.capacidades import VERSIONES_CONOCIDAS
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.conexion import (
    CredencialContrasena,
    CredencialToken,
    MetodoAuth,
    PerfilConexion,
)
from proxlaunch.nucleo.origen.storages import recordado_de
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.servicios.conexion import (
    Aviso,
    CodigoAviso,
    EstadoHuella,
    InformacionHuella,
    ServicioConexion,
    Sesion,
)
from proxlaunch.nucleo.validacion import normalizar_host, validar_perfil, validar_token
from proxlaunch.nucleo.valores_defecto import PUERTO, REALM


class DialogoConexion(QDialog):
    """Conecta con un perfil. Al aceptar, ``sesion`` contiene la sesión establecida."""

    def __init__(
        self,
        servicio: ServicioConexion,
        perfiles: RepositorioPerfiles,
        huellas: RepositorioHuellas,
        secretos: AlmacenSecretos,
        lanzador: Lanzador,
        *,
        candidatos_storage: Mapping[Contenido, Sequence[str]] | None = None,
        avanzado: bool,
        version_forzada: tuple[int, int] | None = None,
        perfil_id: str | None = None,
        motivo: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Conectar con Proxmox"))
        self.setModal(True)
        self.setMinimumWidth(600)
        self._servicio = servicio
        self._perfiles = perfiles
        self._huellas = huellas
        self._secretos = secretos
        self._lanzador = lanzador
        self._avanzado = avanzado
        # Storages del servidor conectado (para elegir cuál recordar) y los recordados del perfil.
        self._candidatos = {c: tuple(v) for c, v in (candidatos_storage or {}).items()}
        self._recordados: dict[Contenido, str | None] = dict.fromkeys(Contenido)
        self._perfil_actual: PerfilConexion | None = None
        self._secreto_guardado: str | None = None
        self._ignorar_guardado = False  # valor del perfil aunque la casilla esté oculta
        self._generacion = 0  # invalida los resultados de un intento abandonado
        self._ocupado = False
        self._dialogo_tfa: DialogoDosFactores | None = None
        self._desafio_tfa: DesafioTFA | None = None
        self._cargando = False  # evita reacciones a cambios hechos por código
        self.sesion: Sesion | None = None
        self.perfil_conectado: PerfilConexion | None = None
        self.version_forzada: tuple[int, int] | None = version_forzada
        self.uso_clave_recuperacion = False
        self._perfil_a_conectar: PerfilConexion | None = None
        self._efectivo: PerfilConexion | None = None
        self._construir(motivo)
        self._recargar_perfiles(perfil_id)
        self._actualizar_visibilidad()

    # --- Construcción -----------------------------------------------------------------

    def _construir(self, motivo: str | None) -> None:
        capa = QVBoxLayout(self)
        self._motivo = mensaje(aviso=True)
        poner_mensaje(self._motivo, motivo, aviso=True)
        capa.addWidget(self._motivo)

        # Perfiles guardados.
        self.combo_perfiles = QComboBox()
        self.btn_duplicar = QPushButton(self.tr("Duplicar"))
        self.btn_eliminar = QPushButton(self.tr("Eliminar"))
        fila_perfiles = QHBoxLayout()
        fila_perfiles.addWidget(QLabel(self.tr("Perfil guardado:")))
        fila_perfiles.addWidget(self.combo_perfiles, 1)
        fila_perfiles.addWidget(self.btn_duplicar)
        fila_perfiles.addWidget(self.btn_eliminar)
        capa.addLayout(fila_perfiles)

        # Datos del perfil.
        self.nombre = QLineEdit()
        self.fila_nombre = FilaCampo(self.tr("Nombre del perfil"), self.nombre)
        self.hosts = QPlainTextEdit()
        self.hosts.setFixedHeight(64)
        self.hosts.setPlaceholderText(
            self.tr("Un servidor por línea. Si el primero no responde se prueba el siguiente.")
        )
        self.fila_hosts = FilaCampo(self.tr("Servidores (IP o nombre)"), self.hosts)
        self.puerto = QLineEdit(str(PUERTO))
        self.puerto.setMaximumWidth(90)
        self.fila_puerto = FilaCampo(self.tr("Puerto"), self.puerto)
        for f in (self.fila_nombre, self.fila_hosts, self.fila_puerto):
            capa.addWidget(f)

        # Método de conexión.
        self.radio_token = QRadioButton(self.tr("API Token (recomendado)"))
        self.radio_clave = QRadioButton(self.tr("Usuario y contraseña"))
        self.radio_token.setChecked(True)
        grupo = QButtonGroup(self)
        grupo.addButton(self.radio_token)
        grupo.addButton(self.radio_clave)
        fila_metodo = QHBoxLayout()
        fila_metodo.addWidget(self.radio_token)
        fila_metodo.addWidget(self.radio_clave)
        fila_metodo.addStretch(1)
        contenedor_metodo = QWidget()
        contenedor_metodo.setLayout(fila_metodo)
        fila_metodo.setContentsMargins(0, 0, 0, 0)
        self.fila_metodo = FilaCampo(self.tr("Método"), contenedor_metodo)
        capa.addWidget(self.fila_metodo)

        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("usuario@realm!nombre=secreto")
        self.fila_token = FilaCampo(self.tr("Token"), self.token)
        self.enlace_guia = EnlaceLabel(self.tr("¿Cómo creo un API Token?"))
        self.realm = QComboBox()
        self.realm.setEditable(True)
        self.realm.addItems(["pam", "pve"])
        self.realm.setCurrentText(REALM)
        self.realm.setMinimumWidth(110)
        self.realm.setMaximumWidth(160)
        self.fila_realm = FilaCampo(self.tr("Realm"), self.realm)
        self.usuario = QLineEdit()
        self.fila_usuario = FilaCampo(self.tr("Usuario"), self.usuario)
        self.contrasena = QLineEdit()
        self.contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        self.fila_contrasena = FilaCampo(self.tr("Contraseña"), self.contrasena)
        for w in (
            self.fila_token,
            self.enlace_guia,
            self.fila_usuario,
            self.fila_realm,
            self.fila_contrasena,
        ):
            capa.addWidget(w)

        # Opciones.
        self.chk_recordar = QCheckBox(self.tr("Recordar credenciales"))
        self.chk_recordar.setChecked(False)  # CA-08.1
        self.chk_recordar.setToolTip(ayuda("recordar"))
        self.chk_ignorar = QCheckBox(self.tr("Ignorar verificación SSL"))
        self.chk_ignorar.setToolTip(ayuda("ignorar_ssl"))
        self._ayuda_ssl = boton_ayuda("huella_ssl")
        self.combo_version = QComboBox()
        self.combo_version.addItem(self.tr("Detectada"), None)
        for mayor, menor in VERSIONES_CONOCIDAS:
            self.combo_version.addItem(f"{mayor}.{menor}", (mayor, menor))
        self.combo_version.setToolTip(ayuda("version_forzada"))
        self.fila_version = FilaCampo(
            self.tr("Forzar compatibilidad con la versión..."),
            self.combo_version,
            "version_forzada",
        )
        fila_ssl = QHBoxLayout()
        fila_ssl.addWidget(self.chk_ignorar)
        fila_ssl.addWidget(self._ayuda_ssl)
        fila_ssl.addStretch(1)
        self._contenedor_ssl = QWidget()
        self._contenedor_ssl.setLayout(fila_ssl)
        fila_ssl.setContentsMargins(0, 0, 0, 0)
        self._nota_recordar = mensaje(aviso=True)
        capa.addWidget(self.chk_recordar)
        capa.addWidget(self._nota_recordar)
        capa.addWidget(self._contenedor_ssl)
        capa.addWidget(self.fila_version)
        self._construir_storages(capa)
        if self.version_forzada is not None:
            self._seleccionar_version(self.version_forzada)

        # Avisos y estado.
        self._aviso_root = mensaje(aviso=True)
        self._estado = mensaje(error=True)
        self._info = QLabel()
        self._info.setProperty("secundario", True)
        self._info.setWordWrap(True)
        self._info.hide()
        capa.addWidget(self._aviso_root)
        capa.addWidget(self._info)
        capa.addWidget(self._estado)

        # Botones.
        self.btn_guardar = QPushButton(self.tr("Guardar perfil"))
        self.btn_cancelar = QPushButton(self.tr("Cancelar"))
        self.btn_conectar = QPushButton(self.tr("Probar y conectar"))
        self.btn_conectar.setDefault(True)
        self.btn_conectar.setProperty("primario", True)
        fila_botones = QHBoxLayout()
        fila_botones.addWidget(self.btn_guardar)
        fila_botones.addStretch(1)
        fila_botones.addWidget(self.btn_cancelar)
        fila_botones.addWidget(self.btn_conectar)
        capa.addLayout(fila_botones)

        # Conexiones.
        self.combo_perfiles.currentIndexChanged.connect(self._al_elegir_perfil)
        self.btn_duplicar.clicked.connect(self._duplicar)
        self.btn_eliminar.clicked.connect(self._eliminar)
        self.btn_guardar.clicked.connect(self._guardar_clic)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_conectar.clicked.connect(self._conectar)
        self.radio_token.toggled.connect(lambda _v: self._al_cambiar_metodo())
        self.enlace_guia.clicked.connect(self._abrir_guia)
        self.nombre.textChanged.connect(lambda _t: self._revisar_nombre_duplicado())
        self.token.textEdited.connect(lambda _t: self._validar_token_en_vivo())
        for campo_texto in (self.usuario, self.puerto):
            campo_texto.textChanged.connect(lambda _t: self._revisar_root())
        self.token.textChanged.connect(lambda _t: self._revisar_root())
        self.realm.currentTextChanged.connect(lambda _t: self._revisar_root())
        self.chk_ignorar.toggled.connect(lambda _v: self._actualizar_info_ssl())
        self.chk_recordar.toggled.connect(self._al_cambiar_recordar)

    def _construir_storages(self, capa: QVBoxLayout) -> None:
        """Almacenamientos recordados de este servidor (RF-O05): se ven y se pueden olvidar."""
        caja = QGroupBox(self.tr("Almacenamientos recordados de este servidor"))
        interior = QVBoxLayout(caja)
        interior.addWidget(
            etiqueta(
                self.tr(
                    "ProxLaunch los detecta solo. Aquí aparecen los que elegiste que recuerde; "
                    "solo se guarda el nombre del almacenamiento."
                ),
                secundario=True,
            )
        )
        self._filas_storage: dict[Contenido, tuple[QLabel, QComboBox, QPushButton]] = {}
        for contenido, titulo in (
            (Contenido.IMAGENES, self.tr("Discos de las máquinas")),
            (Contenido.ISO, self.tr("Archivos ISO")),
            (Contenido.IMPORT, self.tr("Discos para importar")),
        ):
            valor = QLabel()
            combo = QComboBox()
            combo.setAccessibleName(titulo)
            combo.currentIndexChanged.connect(
                lambda _i, c=contenido, w=combo: self._al_elegir_storage(c, w)
            )
            olvidar = QPushButton(self.tr("Dejar de recordar"))
            olvidar.setAccessibleName(self.tr("Dejar de recordar: {nombre}").format(nombre=titulo))
            olvidar.clicked.connect(lambda _c=False, c=contenido: self._olvidar_storage(c))
            fila = QHBoxLayout()
            fila.addWidget(QLabel(titulo))
            fila.addWidget(valor, 1)
            fila.addWidget(combo, 1)
            fila.addWidget(olvidar)
            interior.addLayout(fila)
            self._filas_storage[contenido] = (valor, combo, olvidar)
        capa.addWidget(caja)
        self._pintar_storages()

    def _pintar_storages(self) -> None:
        """Texto en básico y lista desplegable en avanzado; el recordado que ya no está se marca."""
        for contenido, (valor, combo, olvidar) in self._filas_storage.items():
            recordado = self._recordados[contenido]
            candidatos = self._candidatos.get(contenido, ())
            automatico = self.tr("Detectar automáticamente")
            ausente = bool(recordado) and bool(candidatos) and recordado not in candidatos
            nombre = recordado or ""
            if ausente:
                nombre = self.tr("{nombre} (no disponible)").format(nombre=nombre)
            valor.setText(nombre if recordado else automatico)
            valor.setVisible(not self._avanzado)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(automatico, None)
            for c in candidatos:
                combo.addItem(c, c)
            if recordado and recordado not in candidatos:
                combo.addItem(nombre, recordado)
            combo.setCurrentIndex(max(combo.findData(recordado), 0))
            combo.blockSignals(False)
            combo.setVisible(self._avanzado)
            olvidar.setEnabled(recordado is not None and not self._ocupado)

    def _al_elegir_storage(self, contenido: Contenido, combo: QComboBox) -> None:
        if self._cargando:
            return
        self._recordados[contenido] = combo.currentData()
        self._pintar_storages()

    def _olvidar_storage(self, contenido: Contenido) -> None:
        """«Dejar de recordar»: vuelve a detectarlo solo; se guarda con el perfil."""
        self._recordados[contenido] = None
        self._pintar_storages()

    def _seleccionar_version(self, version: tuple[int, int]) -> None:
        """Selecciona por igualdad: PySide compara las tuplas de ``findData`` por identidad."""
        for i in range(self.combo_version.count()):
            dato = self.combo_version.itemData(i)
            if dato is not None and tuple(dato) == tuple(version):
                self.combo_version.setCurrentIndex(i)
                return

    def _version_elegida(self) -> tuple[int, int] | None:
        dato = self.combo_version.currentData()
        return None if dato is None else (int(dato[0]), int(dato[1]))

    # --- Perfiles ---------------------------------------------------------------------

    def _recargar_perfiles(self, seleccionar: str | None = None) -> None:
        self.combo_perfiles.blockSignals(True)
        self.combo_perfiles.clear()
        self.combo_perfiles.addItem(self.tr("(Perfil nuevo)"), None)
        for p in self._perfiles.listar():
            self.combo_perfiles.addItem(p.nombre, p.id)
        idx = self.combo_perfiles.findData(seleccionar) if seleccionar else -1
        if idx < 0 and seleccionar is None and self.combo_perfiles.count() > 1:
            idx = 1  # el primero guardado
        self.combo_perfiles.setCurrentIndex(max(idx, 0))
        self.combo_perfiles.blockSignals(False)
        self._cargar_perfil(self._perfiles.obtener(str(self.combo_perfiles.currentData())))

    def _al_elegir_perfil(self, _i: int) -> None:
        pid = self.combo_perfiles.currentData()
        self._cargar_perfil(self._perfiles.obtener(str(pid)) if pid else None)

    def _cargar_perfil(self, perfil: PerfilConexion | None) -> None:
        self._cargando = True
        try:
            poner_mensaje(self._nota_recordar, None)
            self._cargar_perfil_interno(perfil)
        finally:
            self._cargando = False

    def _cargar_perfil_interno(self, perfil: PerfilConexion | None) -> None:
        self._perfil_actual = perfil
        self._secreto_guardado = None
        self._recordados = {
            c: (None if perfil is None else recordado_de(perfil, c)) for c in Contenido
        }
        self._pintar_storages()
        poner_mensaje(self._estado, None)
        for fila in (
            self.fila_nombre,
            self.fila_hosts,
            self.fila_puerto,
            self.fila_token,
            self.fila_usuario,
        ):
            fila.mostrar_error(None)
        self.contrasena.clear()
        self.token.clear()
        if perfil is None:
            self.nombre.clear()
            self.hosts.clear()
            self.puerto.setText(str(PUERTO))
            self.usuario.clear()
            self.realm.setCurrentText(REALM)
            self.radio_token.setChecked(True)
            self.chk_recordar.setChecked(False)
            self.chk_ignorar.setChecked(False)
            self._ignorar_guardado = False
        else:
            self.nombre.setText(perfil.nombre)
            self.hosts.setPlainText("\n".join(perfil.hosts))
            self.puerto.setText(str(perfil.puerto))
            self.realm.setCurrentText(perfil.realm)
            self.radio_token.setChecked(perfil.metodo == MetodoAuth.TOKEN)
            self.radio_clave.setChecked(perfil.metodo == MetodoAuth.CONTRASENA)
            self.usuario.setText(perfil.usuario if perfil.metodo == MetodoAuth.CONTRASENA else "")
            self.chk_recordar.setChecked(perfil.recordar_credenciales)
            self._ignorar_guardado = perfil.ignorar_ssl
            self.chk_ignorar.setChecked(perfil.ignorar_ssl)
            if perfil.recordar_credenciales:
                try:
                    self._secreto_guardado = self._secretos.obtener(perfil.id)
                except ErrorProxLaunch:
                    self._secreto_guardado = None
        self._actualizar_marcador_secreto()
        self._al_cambiar_metodo()
        self._revisar_nombre_duplicado()
        self._actualizar_info_ssl()
        self.btn_duplicar.setEnabled(perfil is not None)
        self.btn_eliminar.setEnabled(perfil is not None)

    def _al_cambiar_recordar(self, marcada: bool) -> None:
        """Seg B3: al desmarcar deja de usarse el secreto guardado y se avisa en línea
        (sin ventana modal) de que se borrará al guardar o conectar (CA-08.6)."""
        if self._cargando:
            return
        if marcada:
            poner_mensaje(self._nota_recordar, None)
            return
        if self._secreto_guardado is None:
            return
        self._secreto_guardado = None
        self._actualizar_marcador_secreto()
        poner_mensaje(
            self._nota_recordar,
            self.tr("Las credenciales guardadas se borrarán del llavero al guardar o conectar."),
            aviso=True,
        )

    def _actualizar_marcador_secreto(self) -> None:
        guardado = self.tr("(guardado en el llavero)")
        self.token.setPlaceholderText(
            guardado if self._secreto_guardado else "usuario@realm!nombre=secreto"
        )
        self.contrasena.setPlaceholderText(guardado if self._secreto_guardado else "")

    def _duplicar(self) -> None:
        actual = self._perfil_actual
        if actual is None:
            return
        copia = self._perfiles.duplicar(
            actual.id, self.tr("{nombre} (copia)").format(nombre=actual.nombre)
        )
        self._recargar_perfiles(copia.id)

    def _eliminar(self) -> None:
        actual = self._perfil_actual
        if actual is None:
            return
        respuesta = QMessageBox.question(
            self,
            self.tr("Eliminar perfil"),
            self.tr(
                "Se eliminará el perfil «{nombre}», sus credenciales guardadas en el llavero y "
                "las huellas de certificado que solo usaba él. ¿Continuar?"
            ).format(nombre=actual.nombre),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self._perfiles.eliminar_con_dependencias(actual.id, self._secretos, self._huellas)
        self._recargar_perfiles(None)

    def _revisar_nombre_duplicado(self) -> None:
        """A-4: dos perfiles pueden llamarse igual, pero se avisa sin bloquear."""
        nombre = self.nombre.text().strip()
        actual_id = self._perfil_actual.id if self._perfil_actual else None
        repetido = bool(nombre) and any(
            p.nombre == nombre and p.id != actual_id for p in self._perfiles.listar()
        )
        self.fila_nombre.mostrar_aviso(
            self.tr(
                "Ya existe otro perfil con este nombre. Puedes guardarlo igualmente, pero "
                "costará distinguirlos."
            )
            if repetido
            else None
        )

    # --- Lectura y validación ---------------------------------------------------------

    def _es_token(self) -> bool:
        return self.radio_token.isChecked()

    def _texto_token(self) -> str:
        return self.token.text().strip() or (self._secreto_guardado or "")

    def _leer_hosts(self) -> tuple[list[str], int | None]:
        hosts: list[str] = []
        puerto_en_host: int | None = None
        for linea in self.hosts.toPlainText().splitlines():
            if not linea.strip():
                continue
            host, puerto = normalizar_host(linea)
            hosts.append(host)
            if puerto_en_host is None and puerto is not None:
                puerto_en_host = puerto
        return hosts, puerto_en_host

    def _leer_perfil(self, *, credenciales: bool = True) -> PerfilConexion | None:
        """Construye el perfil de los campos; ``None`` si hay errores (ya mostrados)."""
        hosts, puerto_host = self._leer_hosts()
        texto_puerto = self.puerto.text().strip()
        try:
            puerto = int(texto_puerto) if texto_puerto else (puerto_host or PUERTO)
        except ValueError:
            puerto = 0
        if puerto_host is not None and texto_puerto in ("", str(PUERTO)):
            puerto = puerto_host
        perfil = PerfilConexion(
            id=self._perfil_actual.id if self._perfil_actual else str(uuid.uuid4()),
            nombre=self.nombre.text().strip(),
            hosts=hosts,
            puerto=puerto,
            metodo=MetodoAuth.TOKEN if self._es_token() else MetodoAuth.CONTRASENA,
            usuario="",
            realm=self.realm.currentText().strip() or REALM,
            recordar_credenciales=self.chk_recordar.isChecked(),
            ignorar_ssl=self.chk_ignorar.isChecked() if self._avanzado else self._ignorar_guardado,
            storage_mv=self._recordados[Contenido.IMAGENES],
            storage_iso=self._recordados[Contenido.ISO],
            storage_import=self._recordados[Contenido.IMPORT],
        )
        ok = True
        problemas = validar_perfil(perfil)
        errores_hosts = [p for p in problemas if p.campo.startswith("hosts")]
        errores_puerto = [p for p in problemas if p.campo == "puerto"]
        self.fila_hosts.marcar_tocado()
        self.fila_puerto.marcar_tocado()
        self.fila_hosts.mostrar_error(texto_problema(errores_hosts[0]) if errores_hosts else None)
        self.fila_puerto.mostrar_error(
            texto_problema(errores_puerto[0]) if errores_puerto else None
        )
        ok = ok and not problemas
        if not credenciales:
            # Guardar el perfil no exige credenciales (p. ej. tras dejar de recordarlas).
            token = self.token.text().strip()
            if self._es_token():
                perfil.usuario = (
                    token.split("=", 1)[0]
                    if not validar_token(token)
                    else (self._perfil_actual.usuario if self._perfil_actual else "")
                )
            else:
                perfil.usuario = self.usuario.text().strip()
            return perfil if ok else None
        if self._es_token():
            token = self._texto_token()
            self.fila_token.marcar_tocado()
            p_token = validar_token(token)
            self.fila_token.mostrar_error(texto_problema(p_token[0]) if p_token else None)
            ok = ok and not p_token
            if not p_token:
                perfil.usuario = token.split("=", 1)[0]
        else:
            self.fila_usuario.marcar_tocado()
            vacio = not self.usuario.text().strip()
            self.fila_usuario.mostrar_error(self.tr("Escribe tu usuario.") if vacio else None)
            ok = ok and not vacio
            perfil.usuario = self.usuario.text().strip()
        return perfil if ok else None

    def _credencial(self, perfil: PerfilConexion) -> CredencialToken | CredencialContrasena:
        if perfil.metodo == MetodoAuth.TOKEN:
            token_id, _, secreto = self._texto_token().partition("=")
            return CredencialToken(token_id=token_id, secreto=secreto)
        clave = self.contrasena.text() or (self._secreto_guardado or "")
        return CredencialContrasena(usuario=perfil.usuario, realm=perfil.realm, contrasena=clave)

    def _validar_token_en_vivo(self) -> None:
        self.fila_token.marcar_tocado()
        problemas = validar_token(self._texto_token())
        self.fila_token.mostrar_error(texto_problema(problemas[0]) if problemas else None)

    def _revisar_root(self) -> None:
        """CA-25.4: aviso no bloqueante si se conecta como root@pam."""
        if self._es_token():
            identidad = self.token.text().strip().split("!", 1)[0]
        else:
            usuario = self.usuario.text().strip()
            realm = self.realm.currentText().strip()
            identidad = usuario if "@" in usuario else f"{usuario}@{realm}"
        poner_mensaje(
            self._aviso_root,
            self.tr("Estás usando root@pam. Es más seguro usar un API Token con permisos mínimos.")
            if identidad == "root@pam"
            else None,
            aviso=True,
        )

    def _al_cambiar_metodo(self) -> None:
        self._actualizar_visibilidad()
        self._revisar_root()

    def _actualizar_visibilidad(self) -> None:
        token = self._es_token()
        self.fila_token.setVisible(token)
        for w in (self.fila_usuario, self.fila_realm, self.fila_contrasena):
            w.setVisible(not token)
        self._contenedor_ssl.setVisible(self._avanzado)  # CA-06.1
        self.fila_version.setVisible(self._avanzado)  # CA-26.3

    def _actualizar_info_ssl(self) -> None:
        if self._avanzado and self.chk_ignorar.isChecked():
            self._info.setText(
                self.tr(
                    "La identidad del servidor no se comprobará: la conexión quedará sin verificar."
                )
            )
            self._info.show()
        else:
            self._info.hide()

    def _abrir_guia(self) -> None:
        DialogoGuiaToken(self).exec()

    # --- Guardar ----------------------------------------------------------------------

    def _guardar_clic(self) -> None:
        # Sin nada escrito en el token no se exige (p. ej. tras dejar de recordarlo).
        escrito = bool(self.token.text().strip())
        perfil = self._leer_perfil(credenciales=escrito if self._es_token() else True)
        if perfil is None:
            return
        self._guardar_perfil(perfil)
        self._info.setText(self.tr("Perfil guardado."))
        self._info.show()

    def _guardar_perfil(self, perfil: PerfilConexion) -> None:
        if not perfil.nombre:
            perfil.nombre = perfil.hosts[0] if perfil.hosts else self.tr("Perfil")
            self.nombre.setText(perfil.nombre)
        self._perfiles.guardar(perfil)
        if not perfil.recordar_credenciales:
            # CA-08.6: al desmarcar la casilla se borra el secreto guardado.
            try:
                self._secretos.borrar(perfil.id)
            except ErrorProxLaunch as e:
                if e.codigo != CodigoError.LLAVERO_NO_DISPONIBLE:
                    raise
            self._secreto_guardado = None
            self._actualizar_marcador_secreto()
        self._perfil_actual = perfil
        self._recargar_combo_conservando(perfil.id)

    def _recargar_combo_conservando(self, perfil_id: str) -> None:
        self.combo_perfiles.blockSignals(True)
        self.combo_perfiles.clear()
        self.combo_perfiles.addItem(self.tr("(Perfil nuevo)"), None)
        for p in self._perfiles.listar():
            self.combo_perfiles.addItem(p.nombre, p.id)
        self.combo_perfiles.setCurrentIndex(max(self.combo_perfiles.findData(perfil_id), 0))
        self.combo_perfiles.blockSignals(False)
        self.btn_duplicar.setEnabled(True)
        self.btn_eliminar.setEnabled(True)

    # --- Flujo de conexión ------------------------------------------------------------

    def _ocupar(self, ocupado: bool, texto: str = "") -> None:
        self._ocupado = ocupado
        for w in (
            self.combo_perfiles,
            self.btn_duplicar,
            self.btn_eliminar,
            self.btn_guardar,
            self.btn_conectar,
            self.nombre,
            self.hosts,
            self.puerto,
            self.radio_token,
            self.radio_clave,
            self.token,
            self.usuario,
            self.realm,
            self.contrasena,
            self.chk_recordar,
            self.chk_ignorar,
            self.combo_version,
            *(combo for _v, combo, _o in self._filas_storage.values()),
        ):
            w.setEnabled(not ocupado)
        if ocupado:
            self._info.setText(texto)
            self._info.show()
        else:
            self._info.hide()
            self.btn_duplicar.setEnabled(self._perfil_actual is not None)
            self.btn_eliminar.setEnabled(self._perfil_actual is not None)

    def _conectar(self) -> None:
        if self._ocupado:
            return
        poner_mensaje(self._estado, None)
        perfil = self._leer_perfil()
        if perfil is None:
            return
        if not self._es_token() and not (self.contrasena.text() or self._secreto_guardado):
            self.fila_contrasena.marcar_tocado()
            self.fila_contrasena.mostrar_error(self.tr("Escribe tu contraseña."))
            return
        self.fila_contrasena.mostrar_error(None)
        if self._avanzado and perfil.ignorar_ssl and perfil.metodo == MetodoAuth.CONTRASENA:
            respuesta = QMessageBox.warning(
                self,
                self.tr("Conexión sin verificar"),
                self.tr(
                    "No se comprobará la identidad del servidor. Tu contraseña viajaría sin "
                    "esa protección y alguien en la red podría interceptarla. ¿Conectar "
                    "igualmente?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return
        self._generacion += 1
        gen = self._generacion
        # CA-06.3: fuera del modo avanzado se verifica siempre por huella.
        efectivo = dataclasses.replace(
            perfil, ignorar_ssl=perfil.ignorar_ssl if self._avanzado else False
        )
        self._perfil_a_conectar = perfil
        self._efectivo = efectivo
        if self._avanzado:
            self.version_forzada = self._version_elegida()
        # En modo básico se conserva la preferencia previa (solo se oculta el selector).
        self._ocupar(True, self.tr("Comprobando el certificado del servidor..."))
        self._lanzador.lanzar(
            self._servicio.consultar_huellas,
            efectivo,
            al_terminar=lambda infos: self._tras_huellas(gen, infos),
            al_fallar=lambda e: self._error_conexion(gen, e),
        )

    def _tras_huellas(self, gen: int, infos: list[InformacionHuella]) -> None:
        if gen != self._generacion:
            return
        efectivo = self._efectivo
        if efectivo is None:
            return
        pendientes = [i for i in infos if i.estado in (EstadoHuella.CAMBIADA, EstadoHuella.NUEVA)]
        for info in pendientes:
            dialogo = DialogoHuella(
                info, self._avanzado, self, archivo_danado=self._huellas.hubo_corrupcion
            )
            aceptado = dialogo.exec() == QDialog.DialogCode.Accepted
            dialogo.deleteLater()
            if not aceptado:
                # CA-05.3 y CA-05.4: no se conecta y no se guarda nada.
                self._abandonar(
                    texto_error(ErrorProxLaunch(CodigoError.HUELLA_CAMBIADA))
                    if info.estado == EstadoHuella.CAMBIADA
                    else None
                )
                return
            huella = info.huella_observada or ""
            try:
                if info.estado == EstadoHuella.CAMBIADA and dialogo.reemplazar:
                    self._servicio.reemplazar_huella(efectivo, info.host, huella)
                else:
                    self._servicio.confiar_huella(efectivo, info.host, huella)
            except ErrorProxLaunch as e:
                self._abandonar(texto_error(e))
                return
        self._ocupar(True, self.tr("Conectando..."))
        credencial = self._credencial(efectivo)
        self._lanzador.lanzar(
            self._servicio.conectar,
            efectivo,
            credencial,
            version_forzada=self.version_forzada if self._avanzado else None,
            al_terminar=lambda r: self._tras_conectar(gen, r),
            al_fallar=lambda e: self._error_conexion(gen, e),
        )

    def _abandonar(self, texto: str | None) -> None:
        """Termina el intento sin conectar (el usuario canceló o la huella lo bloqueó)."""
        self._ocupar(False)
        poner_mensaje(self._estado, texto)

    def _tras_conectar(self, gen: int, resultado: Sesion | DesafioTFA) -> None:
        if gen != self._generacion:
            return
        if isinstance(resultado, DesafioTFA):
            self._pedir_tfa(gen, resultado)
        else:
            self._exito(resultado)

    def _pedir_tfa(self, gen: int, desafio: DesafioTFA) -> None:
        self._ocupar(True, self.tr("Esperando el segundo factor..."))
        dialogo = DialogoDosFactores(desafio, self)
        self._dialogo_tfa = dialogo
        self._desafio_tfa = desafio
        dialogo.enviado.connect(lambda codigo, tipo: self._enviar_tfa(gen, desafio, codigo, tipo))
        dialogo.rejected.connect(lambda: self._tfa_cancelado(gen))
        dialogo.open()

    def _enviar_tfa(self, gen: int, desafio: DesafioTFA, codigo: str, tipo: TipoTFA) -> None:
        self._lanzador.lanzar(
            self._servicio.completar_tfa,
            desafio,
            codigo,
            tipo,
            al_terminar=lambda s: self._tfa_ok(gen, s, tipo),
            al_fallar=lambda e: self._tfa_fallo(gen, e),
        )

    def _tfa_ok(self, gen: int, sesion: Sesion, tipo: TipoTFA) -> None:
        if gen != self._generacion:
            return
        self.uso_clave_recuperacion = tipo == TipoTFA.RECUPERACION
        self._desafio_tfa = None
        self._cerrar_tfa()
        self._exito(sesion)

    def _tfa_fallo(self, gen: int, error: ErrorProxLaunch) -> None:
        if gen != self._generacion:
            return
        if error.codigo == CodigoError.TFA_CODIGO_INCORRECTO and self._dialogo_tfa is not None:
            # CA-04.3: se puede reintentar sin reescribir usuario y contraseña.
            self._dialogo_tfa.mostrar_error(texto_error(error))
            return
        self._cerrar_tfa()
        self._error_conexion(gen, error)

    def _tfa_cancelado(self, gen: int) -> None:
        if gen != self._generacion or self._dialogo_tfa is None:
            return
        dialogo, self._dialogo_tfa = self._dialogo_tfa, None
        dialogo.deleteLater()
        self._descartar_tfa_pendiente()
        self._generacion += 1
        self._ocupar(False)

    def _descartar_tfa_pendiente(self) -> None:
        """Pide al servicio que olvide el desafío 2FA pendiente (Seg B2)."""
        desafio, self._desafio_tfa = self._desafio_tfa, None
        if desafio is not None:
            self._servicio.cancelar_tfa(desafio)

    def _cerrar_tfa(self) -> None:
        dialogo, self._dialogo_tfa = self._dialogo_tfa, None
        if dialogo is not None:
            dialogo.blockSignals(True)
            dialogo.close()
            dialogo.deleteLater()

    def _error_conexion(self, gen: int, error: ErrorProxLaunch) -> None:
        if gen != self._generacion:
            return
        if error.codigo == CodigoError.SERVIDOR_NO_RESPONDE:
            error.params.setdefault("puerto", self.puerto.text().strip())
        self._ocupar(False)
        poner_mensaje(self._estado, texto_error(error))
        if error.codigo == CodigoError.CREDENCIALES_INVALIDAS and not self._es_token():
            self.contrasena.clear()  # CA-02.2
        self.btn_conectar.setFocus()

    def _exito(self, sesion: Sesion) -> None:
        perfil = self._perfil_a_conectar
        if perfil is None:
            return
        self._guardar_perfil(perfil)
        self.sesion = sesion
        self.perfil_conectado = perfil
        self.contrasena.clear()
        self.token.clear()
        self._ocupar(False)
        self.accept()

    def reject(self) -> None:
        # Los resultados que lleguen después de cerrar se descartan.
        self._generacion += 1
        if self._dialogo_tfa is not None:
            self._descartar_tfa_pendiente()
        self._cerrar_tfa()
        super().reject()

    # --- Utilidades para la ventana ---------------------------------------------------

    def textos_avisos(self) -> list[str]:
        """Avisos de la sesión (llavero, etc.) ya traducidos."""
        if self.sesion is None:
            return []
        return [texto_aviso(a) for a in self.sesion.avisos if isinstance(a, Aviso)]

    @staticmethod
    def hay_aviso_llavero(sesion: Sesion) -> bool:
        return any(a.codigo == CodigoAviso.LLAVERO_NO_DISPONIBLE for a in sesion.avisos)
