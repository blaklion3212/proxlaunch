"""ServicioTransferencias: subir un archivo local o hacer que el servidor descargue una URL.

Fuera del lote (INV-O1): solo lo invoca la interfaz tras una confirmación explícita. Una sola
transferencia a la vez (V-O27). Nunca sobrescribe (INV-O2): el nombre se comprueba antes y de
nuevo justo antes del primer byte; solo se sobrescribe con ``permitir_reemplazo`` (fase B, tras
la elección explícita «Reemplazarla» del asistente de plantillas). Nada de lo que
se registra o se escribe en el log contiene la URL, la ruta local ni el hash (INV-O6).
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path

from proxlaunch.nucleo.api.cliente import ClienteProxmox, MetadatosUrl
from proxlaunch.nucleo.api.multipart import ParteArchivo
from proxlaunch.nucleo.api.traductor_errores import (
    CODIGOS_DE_RED,
    limpiar_detalle,
    traducir_exitstatus,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Volumen
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.tarea import EstadoTarea
from proxlaunch.nucleo.origen.constantes import (
    ESPERA_BASE_S,
    ESPERA_POR_GIB_S,
    PARO_SIN_PROGRESO_S,
    RESERVA_RAIZ_MIB,
    RESERVA_STORAGE_MIB,
)
from proxlaunch.nucleo.origen.nombres import validar_nombre_archivo
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.transferencias.archivo_local import (
    abrir_para_subir,
    calcular_sha256,
    comprobar_cabecera_abierto,
)
from proxlaunch.nucleo.transferencias.modelos import (
    ComprobacionPrevia,
    DestinoTransferencia,
    EstadoTransferencia,
    Progreso,
    RegistroTransferencia,
    ResultadoTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.transferencias.progreso import MedidorProgreso, progreso_de_log
from proxlaunch.nucleo.transferencias.url import (
    AlgoritmoChecksum,
    ChecksumTransferencia,
    UrlDescarga,
    host_y_archivo,
    ocultar_url,
)
from proxlaunch.nucleo.validacion import Problema, Severidad

_log = logging.getLogger("proxlaunch.transferencias.servicio")

# Mismo ritmo de sondeo que la creación (CA-20.1); se repite aquí para no depender de ese módulo.
INTERVALO_SONDEO_S = 1.5
_MIB = 1024**2
_GIB = 1024**3

PRIVILEGIO_SUBIDA = "Datastore.AllocateTemplate"
PRIVILEGIO_RED = "Sys.AccessNetwork"
PRIVILEGIO_ADMIN = "Sys.Modify"
_VERSION_RED = (8, 2)

# Vías (``origen.capacidades_origen.Via``) para el texto «… para {acción}» de E-O20.
_VIA_SUBIR = {"iso": "subir_iso", "import": "subir_imagen"}
_VIA_DESCARGAR = {"iso": "descargar_url", "import": "descargar_imagen"}

_RE_NO_SEGURO = re.compile(r"[^A-Za-z0-9._-]")
_RE_HUELLA_FALLIDA = re.compile(r"checksum|hash|digest", re.IGNORECASE)

_ESTADOS_FINALES = frozenset(
    {
        EstadoTransferencia.TERMINADA,
        EstadoTransferencia.CANCELADA,
        EstadoTransferencia.FALLIDA,
        EstadoTransferencia.SIN_ESPERAR,
    }
)


class RegistroSesion:
    """Transferencias de la sesión (RF-O25), en memoria y seguro entre hilos. No se persiste."""

    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self._registros: list[RegistroTransferencia] = []

    def agregar(self, registro: RegistroTransferencia) -> None:
        with self._cerrojo:
            self._registros.append(registro)

    def lista(self) -> tuple[RegistroTransferencia, ...]:
        with self._cerrojo:
            return tuple(self._registros)

    def vaciar(self) -> None:
        with self._cerrojo:
            self._registros.clear()


def _y_logico(*valores: bool | None) -> bool | None:
    """Y de tres valores: un ``False`` manda; si no, un desconocido (``None``) manda."""
    if any(v is False for v in valores):
        return False
    if any(v is None for v in valores):
        return None
    return True


def _o_logico(*valores: bool | None) -> bool | None:
    """O de tres valores: un ``True`` manda; si no, un desconocido (``None``) manda."""
    if any(v is True for v in valores):
        return True
    if any(v is None for v in valores):
        return None
    return False


def _normalizado(nombre: str) -> str:
    return _RE_NO_SEGURO.sub("_", nombre)


_CARACTERES_SEGUROS = re.compile(r"^[A-Za-z0-9._-]+$")


def _validar_destino(destino: DestinoTransferencia) -> None:
    """SEG-M4-04: el destino se valida también en el núcleo (no solo en la interfaz).

    Nombre de archivo según ``validar_nombre_archivo(nombre, contenido)`` y storage / nodo
    con ``[A-Za-z0-9._-]+``; si no, ``PARAMETRO_INVALIDO`` (sin red).
    """
    campo = ""
    if _CARACTERES_SEGUROS.match(destino.storage) is None:
        campo = "storage"
    elif _CARACTERES_SEGUROS.match(destino.nodo) is None:
        campo = "nodo"
    elif validar_nombre_archivo(destino.nombre_archivo, destino.contenido) is not None:
        campo = "nombre_archivo"
    if campo:
        raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": campo})


def _sin_bytes_por_enviar(
    seg: _Seguimiento, tipo: TipoTransferencia, tamano: int | None, upid: str | None
) -> bool:
    """``True`` si ya no quedan bytes por enviar desde la app: la copia sigue en el servidor.

    Es el caso de una subida con la tarea iniciada o en ``ESPERANDO_SERVIDOR`` /
    ``VERIFICANDO`` (o con todo el cuerpo ya entregado al socket). Una descarga nunca envía
    bytes: solo se considera así si el ``POST download-url`` ya se envió (``upid``).
    """
    if upid is not None:
        return True
    if tipo == TipoTransferencia.DESCARGA:
        return False
    if seg.estado in (EstadoTransferencia.ESPERANDO_SERVIDOR, EstadoTransferencia.VERIFICANDO):
        return True
    return (
        seg.estado == EstadoTransferencia.TRANSFIRIENDO
        and tamano is not None
        and seg.hechos >= tamano
    )


class _Seguimiento:
    """Estado mutable de UNA transferencia: avance, medidor y emisión de progreso."""

    def __init__(self, reloj: Reloj, al_progresar: Callable[[Progreso], None]) -> None:
        self._al_progresar = al_progresar
        self.medidor = MedidorProgreso(reloj)
        self.hechos = 0
        self.total: int | None = None
        self.estado = EstadoTransferencia.COMPROBANDO

    def emitir(
        self,
        estado: EstadoTransferencia,
        hechos: int,
        total: int | None,
        *,
        porcentaje: float | None = None,
        forzar: bool = False,
    ) -> None:
        """Notifica el avance (≤ 10 por segundo salvo ``forzar``); un fallo del observador no
        interrumpe la transferencia."""
        self.hechos, self.total, self.estado = hechos, total, estado
        velocidad, restante = self.medidor.registrar(hechos, total)
        if not (forzar or self.medidor.debe_emitir()):
            return
        try:
            self._al_progresar(Progreso(estado, hechos, total, velocidad, restante, porcentaje))
        except Exception:
            _log.exception("El observador de progreso falló; la transferencia sigue")


class ServicioTransferencias:
    """Subidas y descargas por URL de archivos ``iso`` / ``import`` (RF-O09..O12, O16)."""

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        registro: RegistroSesion,
        *,
        intervalo_s: float = INTERVALO_SONDEO_S,
        paro_sin_progreso_s: float = PARO_SIN_PROGRESO_S,
        hora_local: Callable[[], str],
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._registro = registro
        self._intervalo = intervalo_s
        # Cuánto se tolera perder la red mientras se sondea la tarea del servidor. La subida
        # en sí corta por el timeout de escritura del transporte (PARO_SIN_PROGRESO_S).
        self._paro = paro_sin_progreso_s
        self._hora_local = hora_local
        self._cerrojo = threading.Lock()
        self._ocupado = False

    @property
    def _cliente(self) -> ClienteProxmox:
        return self._sesion.cliente

    @property
    def ocupado(self) -> bool:
        """``True`` mientras haya una subida o descarga en curso (V-O27)."""
        return self._ocupado

    def _tomar(self) -> None:
        with self._cerrojo:
            if self._ocupado:
                raise ErrorProxLaunch(CodigoError.TRANSFERENCIA_EN_CURSO)
            self._ocupado = True

    def _soltar(self) -> None:
        with self._cerrojo:
            self._ocupado = False

    # --- Comprobaciones (solo GET) --------------------------------------------------------

    def _listar_destino(self, destino: DestinoTransferencia) -> list[Volumen]:
        """Archivos del storage destino. Un 403 es ``CATALOGO_SIN_PERMISO``: sin poder mirar si
        el nombre existe no se sube (fallar en cerrado, INV-O2)."""
        try:
            return self._cliente.contenido_storage(destino.nodo, destino.storage, destino.contenido)
        except ErrorProxLaunch as e:
            if e.codigo == CodigoError.PERMISO_INSUFICIENTE:
                raise ErrorProxLaunch(
                    CodigoError.CATALOGO_SIN_PERMISO,
                    {"storage": destino.storage},
                    e.detalle_tecnico,
                ) from None
            raise

    @staticmethod
    def _volid_de(destino: DestinoTransferencia) -> str:
        return f"{destino.storage}:{destino.contenido.value}/{destino.nombre_archivo}"

    def _volid_existente(self, destino: DestinoTransferencia) -> str | None:
        """Volid ya presente con ese nombre SIN distinguir mayúsculas (C5); ``None`` si libre."""
        buscado = destino.nombre_archivo.casefold()
        for v in self._listar_destino(destino):
            if v.nombre.casefold() == buscado:
                return v.volid
        return None

    def _libre_storage(self, destino: DestinoTransferencia, inv: Inventario) -> int | None:
        try:
            for s in self._cliente.storages(destino.nodo):
                if s.id == destino.storage:
                    return s.libre_bytes
        except ErrorProxLaunch as e:
            if e.codigo not in CODIGOS_DE_RED:
                raise
        for s in inv.storages_todos.get(destino.nodo, ()):
            if s.id == destino.storage:
                return s.libre_bytes
        return None

    def _libre_raiz(self, nodo: str) -> int | None:
        """``rootfs.avail`` del nodo (``/var/tmp`` recibe el archivo); sin dato, ``None``."""
        try:
            estado = self._cliente.estado_nodo(nodo)
        except ErrorProxLaunch:
            return None
        raiz = estado.get("rootfs")
        avail = raiz.get("avail") if isinstance(raiz, dict) else None
        try:
            return int(avail) if avail is not None else None
        except (TypeError, ValueError):
            return None

    def comprobar(
        self,
        destino: DestinoTransferencia,
        tamano_bytes: int | None,
        inv: Inventario,
        *,
        para_subida: bool = True,
        permitir_reemplazo: bool = False,
    ) -> ComprobacionPrevia:
        """Comprobaciones previas con solo lecturas (RF-O10, CA-O10.6).

        Nombre existente (V-O14; con ``permitir_reemplazo`` ya no bloquea, pero el volid
        existente se sigue devolviendo para que la interfaz lo muestre), espacio en el storage
        (V-O13), espacio en la raíz del nodo (aviso; solo ``para_subida``: la descarga escribe
        directo en el storage) y permisos (V-O15; V-O16 si es una descarga). Los permisos salen
        de ``inv.catalogo``.
        """
        problemas: list[Problema] = []
        volid_existente = self._volid_existente(destino)
        if volid_existente is not None and not permitir_reemplazo:
            problemas.append(
                Problema(
                    "destino",
                    "V-O14",
                    Severidad.ERROR,
                    {"storage": destino.storage, "nombre": destino.nombre_archivo},
                )
            )
        libre = self._libre_storage(destino, inv)
        if (
            tamano_bytes is not None
            and libre is not None
            and tamano_bytes > libre - RESERVA_STORAGE_MIB * _MIB
        ):
            problemas.append(
                Problema(
                    "destino",
                    "V-O13",
                    Severidad.ERROR,
                    {
                        "storage": destino.storage,
                        "tamano": str(tamano_bytes),
                        "libre": str(max(0, libre)),
                    },
                )
            )
        libre_raiz: int | None = None
        if para_subida:
            libre_raiz = self._libre_raiz(destino.nodo)
            if (
                tamano_bytes is not None
                and libre_raiz is not None
                and libre_raiz < tamano_bytes + RESERVA_RAIZ_MIB * _MIB
            ):
                problemas.append(
                    Problema(
                        "destino",
                        "V-O13.raiz",
                        Severidad.AVISO,
                        {
                            "nodo": destino.nodo,
                            "tamano": str(tamano_bytes),
                            "libre": str(max(0, libre_raiz)),
                        },
                    )
                )
        permiso = self._permisos(destino, inv, para_subida, problemas)
        return ComprobacionPrevia(
            volid_existente=volid_existente,
            libre_storage_bytes=libre,
            libre_raiz_bytes=libre_raiz,
            permiso=permiso,
            problemas=tuple(problemas),
        )

    def _permisos(
        self,
        destino: DestinoTransferencia,
        inv: Inventario,
        para_subida: bool,
        problemas: list[Problema],
    ) -> bool | None:
        """V-O15 (y V-O16 en descargas); añade el ``Problema`` que corresponda."""
        efectivos = inv.catalogo.permisos if inv.catalogo is not None else None
        ruta_storage = f"/storage/{destino.storage}"
        v15 = estado_privilegio(efectivos, PRIVILEGIO_SUBIDA, ruta_storage)
        if v15 is False:
            problemas.append(
                Problema(
                    "permiso",
                    "V-O15",
                    Severidad.ERROR,
                    {"privilegio": PRIVILEGIO_SUBIDA, "ruta": ruta_storage},
                )
            )
        if para_subida:
            return v15
        ruta_nodo = f"/nodes/{destino.nodo}"
        admin = estado_privilegio(efectivos, PRIVILEGIO_ADMIN, "/")
        if (inv.version.mayor, inv.version.menor) >= _VERSION_RED:
            v16 = _o_logico(
                estado_privilegio(efectivos, PRIVILEGIO_RED, ruta_nodo),
                admin,
            )
            privilegio, ruta = PRIVILEGIO_RED, ruta_nodo
        else:
            v16 = admin  # en 8.0 y 8.1 la única vía es Sys.Modify en «/» (nunca se pide)
            privilegio, ruta = PRIVILEGIO_ADMIN, "/"
        if v16 is False:
            problemas.append(
                Problema(
                    "permiso",
                    "V-O16",
                    Severidad.ERROR,
                    {
                        "privilegio": privilegio,
                        "ruta": ruta,
                        "version": inv.version.texto,
                        "nodo": destino.nodo,
                    },
                )
            )
        return _y_logico(v15, v16)

    def _error_de_problemas(
        self, comp: ComprobacionPrevia, destino: DestinoTransferencia, via: str
    ) -> ErrorProxLaunch | None:
        """Primer problema bloqueante como error de núcleo (permiso, nombre, espacio)."""
        por_codigo = {p.codigo: p for p in comp.problemas if p.severidad == Severidad.ERROR}
        if "V-O15" in por_codigo:
            params = dict(por_codigo["V-O15"].params)
            params["via"] = via
            return ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, params)
        if "V-O16" in por_codigo:
            p = por_codigo["V-O16"].params
            return ErrorProxLaunch(
                CodigoError.DESCARGA_URL_SIN_PERMISO,
                {"version": p["version"], "nodo": p["nodo"], "privilegio": p["privilegio"]},
            )
        if "V-O14" in por_codigo:
            return ErrorProxLaunch(
                CodigoError.NOMBRE_YA_EXISTE,
                {"storage": destino.storage, "nombre": destino.nombre_archivo},
            )
        if "V-O13" in por_codigo:
            return ErrorProxLaunch(
                CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA, dict(por_codigo["V-O13"].params)
            )
        return None

    # --- Subir ----------------------------------------------------------------------------

    def subir(
        self,
        ruta: Path,
        destino: DestinoTransferencia,
        inv: Inventario,
        *,
        al_progresar: Callable[[Progreso], None],
        cancelado: threading.Event,
        acepta_aviso_raiz: bool,
        suma_esperada: ChecksumTransferencia | None = None,
        permitir_reemplazo: bool = False,
    ) -> ResultadoTransferencia:
        """Sube ``ruta`` a ``destino`` (hash → comprobar → enviar → tarea → verificar).

        Devuelve siempre un ``ResultadoTransferencia`` (también si falla o se cancela). Lanza
        ``TRANSFERENCIA_EN_CURSO`` si ya hay otra transferencia. ``acepta_aviso_raiz`` es la
        casilla «Entiendo que la subida puede fallar» (CA-O10.4).

        Fase B (RF-B2.4, RF-B2.5): ``suma_esperada`` (solo SHA-256, la huella que ya se
        calcula) se compara antes de cualquier escritura; si no coincide no se envía nada
        (``SUMA_NO_COINCIDE``). ``permitir_reemplazo`` deja de bloquear un nombre ya
        existente: solo lo activa la interfaz tras la elección explícita «Reemplazarla».
        """
        _validar_destino(destino)
        self._tomar()
        inicio = self._reloj.ahora()
        seg = _Seguimiento(self._reloj, al_progresar)
        upid: str | None = None
        tamano: int | None = None
        try:
            with abrir_para_subir(ruta) as archivo:
                tamano = archivo.huella.tamano
                # SEG-M4-10: la cabecera se vuelve a evaluar sobre el descriptor que se enviará.
                comprobar_cabecera_abierto(archivo, destino.contenido)
                seg.emitir(EstadoTransferencia.CALCULANDO_HUELLA, 0, tamano, forzar=True)
                huella = calcular_sha256(
                    archivo,
                    al_progresar=lambda h, t: seg.emitir(
                        EstadoTransferencia.CALCULANDO_HUELLA, h, t
                    ),
                    cancelado=cancelado,
                )
                self._comprobar_suma(suma_esperada, huella)
                seg.emitir(EstadoTransferencia.COMPROBANDO, 0, tamano, forzar=True)
                self._antes_de_enviar(
                    destino, tamano, inv, cancelado, acepta_aviso_raiz, permitir_reemplazo
                )
                seg.emitir(EstadoTransferencia.TRANSFIRIENDO, 0, tamano, forzar=True)
                vivo = hashlib.sha256()
                upid = self._cliente.subir_archivo(
                    destino.nodo,
                    destino.storage,
                    destino.contenido,
                    ParteArchivo(destino.nombre_archivo, tamano, archivo.flujo),
                    huella,
                    al_progresar=lambda h, t: seg.emitir(EstadoTransferencia.TRANSFIRIENDO, h, t),
                    cancelado=cancelado,
                    al_leer=vivo.update,
                )
                if vivo.hexdigest() != huella or not archivo.sigue_igual():
                    # CA-O09.8: no se da por buena aunque el servidor la acepte.
                    raise ErrorProxLaunch(CodigoError.ARCHIVO_CAMBIO)
            seg.emitir(EstadoTransferencia.ESPERANDO_SERVIDOR, tamano, tamano, forzar=True)
            return self._tras_envio(destino, tamano, upid, inicio, cancelado, seg)
        except ErrorProxLaunch as e:
            return self._fallo(e, destino, TipoTransferencia.SUBIDA, tamano, inicio, upid, seg)
        finally:
            self._soltar()

    def _antes_de_enviar(
        self,
        destino: DestinoTransferencia,
        tamano: int,
        inv: Inventario,
        cancelado: threading.Event,
        acepta_aviso_raiz: bool,
        permitir_reemplazo: bool = False,
    ) -> None:
        """Comprobaciones, aviso de la raíz y nombre libre justo antes del primer byte."""
        self._cancelar_si(cancelado)
        comp = self.comprobar(
            destino, tamano, inv, para_subida=True, permitir_reemplazo=permitir_reemplazo
        )
        error = self._error_de_problemas(comp, destino, _VIA_SUBIR.get(destino.contenido.value, ""))
        if error is not None:
            raise error
        raiz = next((p for p in comp.problemas if p.codigo == "V-O13.raiz"), None)
        if raiz is not None and not acepta_aviso_raiz:
            raise ErrorProxLaunch(
                CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA,
                {**raiz.params, "ambito": "raiz"},
            )
        self._cancelar_si(cancelado)
        # CA-O10.2: el nombre puede haber aparecido tras la comprobación anterior.
        if not permitir_reemplazo and self._volid_existente(destino) is not None:
            raise ErrorProxLaunch(
                CodigoError.NOMBRE_YA_EXISTE,
                {"storage": destino.storage, "nombre": destino.nombre_archivo},
            )
        self._cancelar_si(cancelado)

    @staticmethod
    def _comprobar_suma(suma: ChecksumTransferencia | None, huella: str) -> None:
        """RF-B2.4: la suma dada se compara con la huella local ANTES de escribir nada.

        Solo SHA-256 (es la huella que ya se calculó). Ambas sumas se muestran recortadas.
        """
        if suma is None:
            return
        if suma.algoritmo != AlgoritmoChecksum.SHA256:
            raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "suma"})
        if suma.valor.casefold() != huella.casefold():
            raise ErrorProxLaunch(
                CodigoError.SUMA_NO_COINCIDE,
                {"esperada": suma.valor[:12].lower(), "obtenida": huella[:12].lower()},
            )

    @staticmethod
    def _cancelar_si(cancelado: threading.Event) -> None:
        if cancelado.is_set():
            raise ErrorProxLaunch(CodigoError.TRANSFERENCIA_CANCELADA, {"quedo_archivo": "no"})

    def _tras_envio(
        self,
        destino: DestinoTransferencia,
        tamano: int,
        upid: str,
        inicio: float,
        cancelado: threading.Event,
        seg: _Seguimiento,
    ) -> ResultadoTransferencia:
        """Sondea la tarea ``imgcopy`` y verifica el volumen (CA-O09.3/O09.4/O09.5)."""
        limite = ESPERA_BASE_S + ESPERA_POR_GIB_S * (tamano / _GIB)
        como, estado = self._sondear(destino.nodo, upid, cancelado, limite)
        if como == "detenido":
            # QA-M4-02: el cuerpo ya se envió y la copia sigue en el servidor; no se afirma
            # nada del archivo (quedo_archivo = None) ni se consulta el catálogo.
            sin_esperar = self._resultado(
                EstadoTransferencia.SIN_ESPERAR, None, None, None, inicio, upid
            )
            return self._cerrar(destino, TipoTransferencia.SUBIDA, tamano, sin_esperar)
        if como == "agotado":
            # La tarea sigue en el servidor: no es un fallo, solo se deja de esperar.
            sin_esperar = self._resultado(
                EstadoTransferencia.SIN_ESPERAR, None, None, None, inicio, upid
            )
            return self._cerrar(destino, TipoTransferencia.SUBIDA, tamano, sin_esperar)
        if estado is None or estado.exitstatus != "OK":
            texto = (estado.exitstatus if estado is not None else None) or ""
            if _RE_HUELLA_FALLIDA.search(texto):
                raise ErrorProxLaunch(
                    CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA,
                    {"algoritmo": "sha256"},
                    limpiar_detalle(texto),
                )
            raise traducir_exitstatus(texto)
        seg.emitir(EstadoTransferencia.VERIFICANDO, tamano, tamano, forzar=True)
        verificado = self.verificar(destino, tamano)
        final = dataclasses.replace(
            verificado, upid=upid, duracion_s=max(0.0, self._reloj.ahora() - inicio)
        )
        return self._cerrar(destino, TipoTransferencia.SUBIDA, tamano, final)

    # --- Descargar ------------------------------------------------------------------------

    def consultar_url(
        self, nodo: str, url: UrlDescarga, *, verificar_certificados: bool = True
    ) -> MetadatosUrl:
        """Nombre, tamaño y tipo que ve el SERVIDOR (CA-O11.1). La app no abre la URL."""
        return self._cliente.metadatos_url(nodo, url, verificar_certificados=verificar_certificados)

    def descargar(
        self,
        url: UrlDescarga,
        destino: DestinoTransferencia,
        inv: Inventario,
        *,
        checksum: ChecksumTransferencia | None,
        verificar_certificados: bool,
        al_progresar: Callable[[Progreso], None],
        dejar_de_esperar: threading.Event,
        permitir_reemplazo: bool = False,
    ) -> ResultadoTransferencia:
        """Hace que el nodo descargue ``url`` en ``destino`` y sigue la tarea ``download``.

        Un solo ``POST download-url`` (CA-O11.2). ``dejar_de_esperar`` deja de sondear
        (``SIN_ESPERAR``): la descarga sigue en el servidor y no se puede detener desde la app.
        ``permitir_reemplazo`` (fase B) deja de bloquear un nombre ya existente.
        """
        _validar_destino(destino)
        self._tomar()
        inicio = self._reloj.ahora()
        seg = _Seguimiento(self._reloj, al_progresar)
        upid: str | None = None
        tamano: int | None = None
        try:
            seg.emitir(EstadoTransferencia.COMPROBANDO, 0, None, forzar=True)
            self._cancelar_si(dejar_de_esperar)
            tamano = self._tamano_del_servidor(destino.nodo, url, verificar_certificados)
            self._cancelar_si(dejar_de_esperar)
            comp = self.comprobar(
                destino, tamano, inv, para_subida=False, permitir_reemplazo=permitir_reemplazo
            )
            via = _VIA_DESCARGAR.get(destino.contenido.value, "")
            error = self._error_de_problemas(comp, destino, via)
            if error is not None:
                raise error
            self._cancelar_si(dejar_de_esperar)
            # CA-O10.2: nombre libre justo antes de pedir la descarga.
            if not permitir_reemplazo and self._volid_existente(destino) is not None:
                raise ErrorProxLaunch(
                    CodigoError.NOMBRE_YA_EXISTE,
                    {"storage": destino.storage, "nombre": destino.nombre_archivo},
                )
            # QA-M4-01: si el usuario ya dejó de esperar, no se envía el POST (nada quedó).
            self._cancelar_si(dejar_de_esperar)
            tarea = self._cliente.descargar_url(
                destino.nodo,
                destino.storage,
                url=url,
                contenido=destino.contenido,
                nombre=destino.nombre_archivo,
                checksum=checksum,
                verificar_certificados=verificar_certificados,
            )
            upid = tarea
            seg.emitir(EstadoTransferencia.ESPERANDO_SERVIDOR, 0, tamano, forzar=True)
            como, estado = self._sondear(
                destino.nodo,
                tarea,
                dejar_de_esperar,
                None,
                en_ciclo=lambda: self._progreso_descarga(destino.nodo, tarea, url, tamano, seg),
            )
            if como == "detenido":
                sin_esperar = self._resultado(
                    EstadoTransferencia.SIN_ESPERAR, None, None, None, inicio, tarea
                )
                return self._cerrar(destino, TipoTransferencia.DESCARGA, tamano, sin_esperar)
            if estado is None or estado.exitstatus != "OK":
                raise self._error_descarga(url, (estado.exitstatus if estado else None) or "")
            seg.emitir(EstadoTransferencia.VERIFICANDO, tamano or 0, tamano, forzar=True)
            verificado = self.verificar(destino, tamano)
            final = dataclasses.replace(
                verificado, upid=tarea, duracion_s=max(0.0, self._reloj.ahora() - inicio)
            )
            return self._cerrar(destino, TipoTransferencia.DESCARGA, tamano, final)
        except ErrorProxLaunch as e:
            self._sin_url(e, url)
            return self._fallo(e, destino, TipoTransferencia.DESCARGA, tamano, inicio, upid, seg)
        finally:
            self._soltar()

    def _tamano_del_servidor(
        self, nodo: str, url: UrlDescarga, verificar_certificados: bool
    ) -> int | None:
        """Tamaño según ``query-url-metadata`` (CA-O11.2); si no se obtiene, ``None``."""
        try:
            return self._cliente.metadatos_url(
                nodo, url, verificar_certificados=verificar_certificados
            ).tamano
        except ErrorProxLaunch as e:
            self._sin_url(e, url)
            _log.info("Metadatos de la URL no disponibles (%s)", e.codigo)
            return None

    @staticmethod
    def _sin_url(error: ErrorProxLaunch, url: UrlDescarga) -> None:
        error.detalle_tecnico = ocultar_url(error.detalle_tecnico, url)
        error.params = {k: ocultar_url(v, url) for k, v in error.params.items()}

    def _progreso_descarga(
        self, nodo: str, upid: str, url: UrlDescarga, total: int | None, seg: _Seguimiento
    ) -> None:
        """Lee el log de la tarea ``download`` y emite el progreso que traiga (CA-O11.5)."""
        try:
            lineas = [ocultar_url(x, url) for x in self._cliente.log_tarea(nodo, upid)]
        except ErrorProxLaunch:
            return
        hechos, total_log, porcentaje = progreso_de_log(lineas)
        seg.emitir(
            EstadoTransferencia.ESPERANDO_SERVIDOR,
            hechos if hechos is not None else seg.hechos,
            total_log if total_log is not None else total,
            porcentaje=porcentaje,
        )

    def _error_descarga(self, url: UrlDescarga, exitstatus: str) -> ErrorProxLaunch:
        """Fallo de la tarea ``download``: huella incorrecta (E-O07) o E-O11 con host y archivo."""
        seguro = ocultar_url(exitstatus, url)
        if _RE_HUELLA_FALLIDA.search(seguro):
            return ErrorProxLaunch(
                CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA,
                {"algoritmo": ""},
                limpiar_detalle(seguro),
            )
        host, archivo = host_y_archivo(url)
        return ErrorProxLaunch(
            CodigoError.DESCARGA_URL_FALLIDA,
            {"host": host, "archivo": archivo, "motivo": limpiar_detalle(seguro)[:200]},
            limpiar_detalle(seguro),
        )

    # --- Verificar ------------------------------------------------------------------------

    def verificar(
        self, destino: DestinoTransferencia, tamano_esperado: int | None
    ) -> ResultadoTransferencia:
        """Comprueba en el catálogo que el volumen está y (si se conoce) que pesa lo esperado.

        Si el servidor «normalizó» el nombre se acepta el volumen real cuando su tamaño
        coincide (CA-O09.12). Si no, ``TRANSFERENCIA_NO_VERIFICADA`` (E-O06): no se usa.
        """
        inicio = self._reloj.ahora()
        esperado_volid = self._volid_de(destino)
        try:
            volumenes = self._listar_destino(destino)
        except ErrorProxLaunch as e:
            return self._resultado(EstadoTransferencia.FALLIDA, None, e, None, inicio, None)
        propio = next((v for v in volumenes if v.volid == esperado_volid), None)
        if propio is None and tamano_esperado is not None:
            # Nombre normalizado por el servidor: un único candidato del mismo tamaño.
            opciones = {destino.nombre_archivo.casefold(), _normalizado(destino.nombre_archivo)}
            candidatos = [
                v
                for v in volumenes
                if v.tamano_bytes == tamano_esperado
                and (v.nombre.casefold() in opciones or v.nombre in opciones)
            ]
            propio = candidatos[0] if len(candidatos) == 1 else None
        if propio is not None and (
            tamano_esperado is None
            or propio.tamano_bytes is None
            or propio.tamano_bytes == tamano_esperado
        ):
            return self._resultado(
                EstadoTransferencia.TERMINADA, propio.volid, None, None, inicio, None
            )
        error = ErrorProxLaunch(
            CodigoError.TRANSFERENCIA_NO_VERIFICADA,
            {
                "volid": esperado_volid if propio is None else propio.volid,
                "esperado": "" if tamano_esperado is None else str(tamano_esperado),
                "real": "ausente" if propio is None else str(propio.tamano_bytes),
            },
        )
        return self._resultado(
            EstadoTransferencia.FALLIDA, None, error, propio is not None, inicio, None
        )

    # --- Internos -------------------------------------------------------------------------

    def _sondear(
        self,
        nodo: str,
        upid: str,
        detener: threading.Event,
        limite_s: float | None,
        *,
        en_ciclo: Callable[[], None] | None = None,
    ) -> tuple[str, EstadoTarea | None]:
        """Sondea la tarea. Devuelve ``("terminada", estado)``, ``("detenido", None)`` si se
        activó ``detener`` o ``("agotado", None)`` si pasó ``limite_s``.

        Tolera caídas de red hasta ``paro_sin_progreso_s`` seguidos; pasado ese tiempo lanza
        ``TRANSFERENCIA_CORTADA`` (el estado real se mira en el catálogo).
        """
        inicio = self._reloj.ahora()
        primer_fallo: float | None = None
        while True:
            if detener.is_set():
                return "detenido", None
            try:
                estado = self._cliente.estado_tarea(nodo, upid)
                primer_fallo = None
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    raise
                ahora = self._reloj.ahora()
                if primer_fallo is None:
                    primer_fallo = ahora
                elif ahora - primer_fallo > self._paro:
                    raise ErrorProxLaunch(
                        CodigoError.TRANSFERENCIA_CORTADA, {}, e.detalle_tecnico
                    ) from None
                self._reloj.dormir(self._intervalo)
                continue
            if estado.terminada:
                return "terminada", estado
            if en_ciclo is not None:
                en_ciclo()
            if limite_s is not None and self._reloj.ahora() - inicio > limite_s:
                return "agotado", None
            self._reloj.dormir(self._intervalo)

    def _quedo_archivo(self, destino: DestinoTransferencia) -> bool | None:
        """¿Hay un archivo con ese nombre en el catálogo? ``None`` si no se puede mirar."""
        try:
            return self._volid_existente(destino) is not None
        except ErrorProxLaunch:
            return None

    def _resultado(
        self,
        estado: EstadoTransferencia,
        volid: str | None,
        error: ErrorProxLaunch | None,
        quedo: bool | None,
        inicio: float,
        upid: str | None,
    ) -> ResultadoTransferencia:
        return ResultadoTransferencia(
            estado=estado,
            volid=volid,
            error=error,
            quedo_archivo=quedo,
            duracion_s=max(0.0, self._reloj.ahora() - inicio),
            upid=upid,
        )

    def _cerrar(
        self,
        destino: DestinoTransferencia,
        tipo: TipoTransferencia,
        tamano: int | None,
        resultado: ResultadoTransferencia,
    ) -> ResultadoTransferencia:
        """Resultado final: lo anota en el registro de la sesión y en el log (sin secretos)."""
        self._registrar(destino, tipo, tamano, resultado)
        return resultado

    def _fallo(
        self,
        error: ErrorProxLaunch,
        destino: DestinoTransferencia,
        tipo: TipoTransferencia,
        tamano: int | None,
        inicio: float,
        upid: str | None,
        seg: _Seguimiento,
    ) -> ResultadoTransferencia:
        """Convierte un error en resultado (cancelada o fallida); mira el catálogo si hace falta."""
        if error.codigo == CodigoError.TRANSFERENCIA_CANCELADA and _sin_bytes_por_enviar(
            seg, tipo, tamano, upid
        ):
            # QA-M4-02: la copia sigue en el servidor; no se consulta el catálogo para decir «no».
            sin_esperar = self._resultado(
                EstadoTransferencia.SIN_ESPERAR, None, None, None, inicio, upid
            )
            return self._cerrar(destino, tipo, tamano, sin_esperar)
        if error.codigo == CodigoError.TRANSFERENCIA_CANCELADA:
            quedo = (
                False if error.params.get("quedo_archivo") == "no" else self._quedo_archivo(destino)
            )
            error.params["quedo_archivo"] = {True: "si", False: "no", None: "desconocido"}[quedo]
            cancelada = self._resultado(
                EstadoTransferencia.CANCELADA, None, error, quedo, inicio, upid
            )
            return self._cerrar(destino, tipo, tamano, cancelada)
        if (
            error.codigo == CodigoError.SERVIDOR_NO_RESPONDE
            and tipo == TipoTransferencia.SUBIDA
            and seg.estado == EstadoTransferencia.TRANSFIRIENDO
        ):
            # Corte durante el envío: sin reintento; E-O08 con lo enviado (CA-O09.7).
            error = ErrorProxLaunch(
                CodigoError.TRANSFERENCIA_CORTADA,
                {"bytes": str(seg.hechos), "total": str(tamano or 0)},
                error.detalle_tecnico,
            )
        if error.codigo == CodigoError.PERMISO_INSUFICIENTE and "via" not in error.params:
            vias = _VIA_SUBIR if tipo == TipoTransferencia.SUBIDA else _VIA_DESCARGAR
            error.params["via"] = vias.get(destino.contenido.value, "")
        if error.codigo == CodigoError.ARCHIVO_CAMBIO and upid is not None:
            # El cuerpo ya se envió y la tarea del servidor puede seguir: solo se afirma el
            # «sí» (ya está en el catálogo); un «no» sería prematuro (QA-M4-02).
            quedo = True if self._quedo_archivo(destino) is True else None
        elif error.codigo in _ERRORES_CON_COMPROBACION:
            quedo = self._quedo_archivo(destino)
        else:
            quedo = None
        fallida = self._resultado(EstadoTransferencia.FALLIDA, None, error, quedo, inicio, upid)
        return self._cerrar(destino, tipo, tamano, fallida)

    def _registrar(
        self,
        destino: DestinoTransferencia,
        tipo: TipoTransferencia,
        tamano: int | None,
        resultado: ResultadoTransferencia,
    ) -> None:
        self._registro.agregar(
            RegistroTransferencia(
                tipo=tipo,
                nombre_archivo=destino.nombre_archivo,
                storage=destino.storage,
                nodo=destino.nodo,
                tamano_bytes=tamano,
                hora_local=self._hora_local(),
                estado=resultado.estado,
                volid=resultado.volid,
            )
        )
        # CA-O12.7: nunca la ruta local, la URL, el hash ni cabeceras.
        _log.info(
            "Transferencia tipo=%s archivo=%s tamano=%s storage=%s nodo=%s duracion=%.1fs "
            "estado=%s codigo=%s",
            tipo.value,
            destino.nombre_archivo,
            tamano,
            destino.storage,
            destino.nodo,
            resultado.duracion_s,
            resultado.estado.value,
            resultado.error.codigo.value if resultado.error else "-",
        )


# Tras estos errores se mira el catálogo para saber si quedó un archivo (CA-O09.5, CA-O09.7).
_ERRORES_CON_COMPROBACION = frozenset(
    {
        CodigoError.TRANSFERENCIA_CORTADA,
        CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA,
        CodigoError.ARCHIVO_CAMBIO,
    }
)
