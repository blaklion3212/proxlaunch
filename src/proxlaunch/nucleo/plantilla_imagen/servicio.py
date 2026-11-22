"""ServicioPlantillaImagen: crear una plantilla desde una imagen cloud en cinco pasos (B2, DT-B10).

Pasos reanudables: 1 imagen en el almacenamiento ``import``; 2 crear la MV e importar el disco;
3 ampliar el disco; 4 valores de cloud-init (sin contraseña); 5 convertir en plantilla. Los pasos 2
y 3 los hace ``ServicioCreacion.crear`` (hereda sus esperas largas, la tolerancia de red y el
``resize`` absoluto que solo crece); la imagen la mueve ``ServicioTransferencias``.

Reglas de seguridad:

- No usa el libro ni Deshacer (RF-B7.1) y NO borra nada por sí solo: tras un fallo deja el estado
  como está. La única operación destructiva es ``borrar_a_medio_crear``, que exige que la
  interfaz haya confirmado y que ``condiciones_borrado`` (solo lecturas) pase TODAS las
  condiciones de RF-B2.10.
- Un paso ``INCIERTO`` (conexión perdida, o el usuario dejó de esperar con la tarea en vuelo)
  nunca se repite a ciegas: ``ejecutar`` primero lo comprueba con lecturas (``comprobar_ahora``).
- Nunca se envía una contraseña (PB-1); el ``PUT`` de cloud-init va sin ``cipassword``.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from typing import Any

from proxlaunch.nucleo.api.traductor_errores import CODIGOS_DE_RED, traducir_exitstatus
from proxlaunch.nucleo.cloudinit.deteccion import info_cloudinit
from proxlaunch.nucleo.cloudinit.peticion import construir_put_cloudinit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido, ListadoStorage
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import DetalleImportacion
from proxlaunch.nucleo.modelos.tarea import Desenlace, EstadoTarea, Etapa, ResultadoCreacion
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.origen.clon import detalle_de_config
from proxlaunch.nucleo.origen.permisos import estado_privilegio
from proxlaunch.nucleo.plantilla_imagen.modelos import (
    AVISO_AJUSTE_DISCO_OMITIDO,
    AVISO_SIN_AMPLIAR,
    PASOS_RESUELTOS,
    AccionExistente,
    CondicionesBorrado,
    EstadoPaso,
    EstadoPlantillaImagen,
    OrigenImagen,
    PasoB2,
    SolicitudPlantillaImagen,
)
from proxlaunch.nucleo.plantilla_imagen.peticion import (
    cfg_de_creacion,
    parametros_extra,
    volid_de_imagen,
)
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion
from proxlaunch.nucleo.servicios.creacion import (
    AJUSTE_DISCO,
    ServicioCreacion,
    ampliacion_importacion,
    clave_primer_disco,
)
from proxlaunch.nucleo.transferencias.modelos import (
    DestinoTransferencia,
    EstadoTransferencia,
    Progreso,
    ResultadoTransferencia,
)
from proxlaunch.nucleo.transferencias.servicio import ServicioTransferencias

_log = logging.getLogger("proxlaunch.plantilla_imagen.servicio")

INTERVALO_TAREA_S = 1.5  # mismo ritmo de sondeo que la creación (CA-20.1)
MAX_ESPERA_TAREA_S = 300.0  # convertir o borrar: tareas cortas
TOLERANCIA_RED_S = 60.0  # CA-20.7
PRIVILEGIO_ASIGNAR = "VM.Allocate"

FabricaCreacion = Callable[[Sesion, Reloj], ServicioCreacion]
AlCambiar = Callable[[EstadoPlantillaImagen], None]
AlProgresar = Callable[[Progreso], None]

_AVISO_AJUSTE_PENDIENTE_DISCO = f"ajuste_pendiente:{AJUSTE_DISCO}"
_GIB = 1024**3
_PREFIJO_AJUSTE_PENDIENTE = "ajuste_pendiente"
_AVISO_IMAGEN_EN_IMPORT = "imagen_quedo_en_import"
_AVISO_BORRADA = "maquina_borrada"
_AVISO_BORRADO_SIN_ESPERAR = "borrado_sin_esperar"
# QA-B4: al cambiar de VMID tras un fallo quedó una máquina propia sin borrar. Aviso con la forma
# ``maquina_anterior_sin_borrar:<vmid>:<nombre>`` (los avisos son cadenas; el nombre no lleva «:»).
AVISO_MAQUINA_ANTERIOR_SIN_BORRAR = "maquina_anterior_sin_borrar"


@dataclasses.dataclass
class _Ejecucion:
    """Contexto de UNA llamada (el servicio puede usarse desde varios hilos)."""

    sol: SolicitudPlantillaImagen
    inv: Inventario | None
    estado: EstadoPlantillaImagen
    cancelado: threading.Event
    al_cambiar: AlCambiar | None = None
    al_progresar: AlProgresar | None = None
    paso: PasoB2 = PasoB2.IMAGEN  # paso en curso (para atribuir un fallo inesperado)
    # El disco importado ya medía lo pedido y ``crear`` no enviará ``resize`` (BUG-B-P3-3).
    disco_ya_del_tamano: bool = False


def _como_entero(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _es_plantilla(config: dict[str, Any]) -> bool:
    return _como_entero(config.get("template")) == 1


def _error_inesperado(exc: BaseException) -> ErrorProxLaunch:
    """Envuelve una excepción inesperada sin filtrar su texto (solo el tipo)."""
    return ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, type(exc).__name__)


def _inexistente(nodo: str, vmid: int) -> ErrorProxLaunch:
    return ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"recurso": f"vm {vmid}", "nodo": nodo})


class ServicioPlantillaImagen:
    """Los cinco pasos de B2 con estado reanudable. No usa el libro ni Deshacer."""

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        transferencias: ServicioTransferencias,
        *,
        fabrica_creacion: FabricaCreacion | None = None,
        intervalo_s: float = INTERVALO_TAREA_S,
        max_espera_tarea_s: float = MAX_ESPERA_TAREA_S,
        tolerancia_red_s: float = TOLERANCIA_RED_S,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._transferencias = transferencias
        self._fabrica: FabricaCreacion = fabrica_creacion or ServicioCreacion
        self._intervalo = intervalo_s
        self._max_espera = max_espera_tarea_s
        self._tolerancia_red = tolerancia_red_s

    # --- API pública ------------------------------------------------------------------------

    def ejecutar(
        self,
        sol: SolicitudPlantillaImagen,
        inv: Inventario,
        estado: EstadoPlantillaImagen,
        al_cambiar: AlCambiar,
        al_progresar: AlProgresar,
        cancelado: threading.Event,
    ) -> EstadoPlantillaImagen:
        """Empieza en el primer paso no ``HECHO``/``OMITIDO`` y nunca repite uno ya hecho.

        Bloqueante (la interfaz lo llama en un hilo). Se detiene en cuanto un paso queda
        ``FALLIDO`` o ``INCIERTO`` o se activa ``cancelado`` («Dejar de esperar»: no se cancela
        ninguna tarea del servidor). Antes de llamar a ``ejecutar``, la interfaz ha de haber
        validado la solicitud (``validar_solicitud``) y obtenido la casilla de irreversibilidad.
        ``al_cambiar`` recibe una COPIA del estado tras cada cambio. Devuelve el mismo
        ``estado``, ya actualizado. Lanza ``ValueError`` si la solicitud no está ``confirmada``.
        """
        if not sol.confirmada:
            # Defensa en profundidad: la interfaz ya exige la casilla (V-B14). Es un fallo de
            # programación del llamador, como en ``omitir``: no escribe nada ni toca el estado.
            raise ValueError("la solicitud no está confirmada: no se escribe nada en el servidor")
        ctx = _Ejecucion(sol, inv, estado, cancelado, al_cambiar, al_progresar)
        estado.error = None
        try:
            self._recorrer(ctx)
        except ErrorProxLaunch as e:  # defensa: los pasos ya atrapan los suyos
            self._fallar(ctx, ctx.paso, e)
        except Exception as exc:
            _log.exception("Fallo inesperado en el asistente de plantillas (paso %s)", ctx.paso)
            self._fallar(ctx, ctx.paso, _error_inesperado(exc))
        return estado

    def omitir(self, estado: EstadoPlantillaImagen, paso: PasoB2) -> EstadoPlantillaImagen:
        """«Continuar sin ampliar / sin cloud-init / dejarla como MV normal» (RF-B2.10).

        Solo para los pasos 3, 4 y 5. No escribe nada en el servidor.
        """
        if paso not in (PasoB2.AMPLIAR, PasoB2.CLOUDINIT, PasoB2.CONVERTIR):
            raise ValueError(f"el paso {paso.name} no se puede omitir")
        estado.pasos[paso] = EstadoPaso.OMITIDO
        estado.error = None
        estado.avisos.append(f"omitido:{paso.name.lower()}")
        return estado

    def comprobar_ahora(
        self,
        sol: SolicitudPlantillaImagen,
        estado: EstadoPlantillaImagen,
        *,
        inv: Inventario | None = None,
    ) -> EstadoPlantillaImagen:
        """«Comprobar ahora» de los pasos ``INCIERTO``: solo lecturas (CA-B2.10.5).

        Reconcilia cada paso dudoso con lo que hay en el servidor: lo da por hecho, por fallido o
        lo devuelve a ``PENDIENTE`` si se sabe que no ocurrió; si no se puede saber, sigue
        ``INCIERTO``. Nunca escribe.
        """
        ctx = _Ejecucion(sol, inv, estado, threading.Event())
        for paso in PasoB2:
            if estado.pasos[paso] != EstadoPaso.INCIERTO:
                continue
            ctx.paso = paso
            try:
                self._comprobar_paso(ctx, paso)
            except ErrorProxLaunch as e:
                estado.error = e  # no se pudo leer: el paso sigue dudoso
            except Exception as exc:
                _log.exception("Fallo inesperado al comprobar el paso %s", paso)
                estado.error = _error_inesperado(exc)
        return estado

    def condiciones_borrado(
        self,
        sol: SolicitudPlantillaImagen,
        estado: EstadoPlantillaImagen,
        *,
        inv: Inventario | None = None,
    ) -> CondicionesBorrado:
        """¿Se puede ofrecer «Borrar la máquina a medio crear»? Solo lecturas (RF-B2.10).

        Deben cumplirse TODAS: el VMID lo reservó el asistente en esta sesión; ``GET config``
        muestra el ``name`` pedido; no es plantilla (``template`` ≠ 1), no tiene ``lock`` ni
        ``protection`` y no está ``running``; y, si se conocen los permisos (``inv``), hay
        ``VM.Allocate``. Ante un fallo de lectura devuelve ``sin_certeza`` y no se ofrece.
        """
        vmid = estado.vmid_reservado
        nodo = estado.nodo_reservado or sol.nodo
        nombre = estado.nombre_reservado or sol.cfg.nombre
        params = {"nombre": nombre, "vmid": str(vmid), "nodo": nodo}
        if (
            not estado.vmid_reservado_aqui
            or vmid is None
            or vmid != sol.cfg.vmid
            or estado.pasos[PasoB2.CONVERTIR] == EstadoPaso.HECHO
        ):
            # Sin UPID de creación no hay certeza de que sea nuestra: nunca se borra (RF-B2.10).
            sin_certeza = estado.pasos[PasoB2.CONVERTIR] != EstadoPaso.HECHO
            motivo = "sin_upid" if sin_certeza else "no_reservado"
            return CondicionesBorrado(
                False,
                ErrorProxLaunch(CodigoError.ROLLBACK_NO_PROPIA, {**params, "motivo": motivo}),
                sin_certeza=sin_certeza,
            )
        permisos = inv.catalogo.permisos if inv is not None and inv.catalogo is not None else None
        if estado_privilegio(permisos, PRIVILEGIO_ASIGNAR, f"/vms/{vmid}") is False:
            return CondicionesBorrado(
                False,
                ErrorProxLaunch(
                    CodigoError.PERMISO_INSUFICIENTE,
                    {"privilegio": PRIVILEGIO_ASIGNAR, "ruta": f"/vms/{vmid}"},
                ),
            )
        try:
            config = self._sesion.cliente.config_vm(nodo, vmid)
            actual = self._sesion.cliente.estado_actual_vm(nodo, vmid) if config is not None else {}
        except ErrorProxLaunch:
            return CondicionesBorrado(False, sin_certeza=True)
        return self._juzgar_borrado(config, actual, nombre, params)

    def puede_borrar(
        self,
        sol: SolicitudPlantillaImagen,
        estado: EstadoPlantillaImagen,
        *,
        inv: Inventario | None = None,
    ) -> bool:
        """``True`` solo si ``condiciones_borrado`` pasa todas las condiciones (solo lecturas)."""
        return self.condiciones_borrado(sol, estado, inv=inv).ok

    def borrar_a_medio_crear(
        self,
        sol: SolicitudPlantillaImagen,
        estado: EstadoPlantillaImagen,
        cancelado: threading.Event,
        *,
        confirmado: bool,
        inv: Inventario | None = None,
    ) -> EstadoPlantillaImagen:
        """Borra la máquina a medio crear (RF-B2.10). Nunca es automático.

        ``confirmado`` debe ser ``True`` solo tras el diálogo con el nombre y el VMID; si no,
        lanza ``ValueError`` sin tocar nada. Vuelve a comprobar TODAS las condiciones justo antes
        (``condiciones_borrado``): si alguna falla no se emite ningún ``DELETE`` y el motivo queda
        en ``estado.error``. Usa ``eliminar_vm`` (``destroy-unreferenced-disks=0``, sin
        ``purge``): no borra volúmenes sueltos ni la imagen del almacenamiento ``import``. Si se
        borra, los pasos 2 a 5 vuelven a ``PENDIENTE`` para poder reintentar.
        """
        if not confirmado:
            raise ValueError("borrar_a_medio_crear exige la confirmación del usuario")
        condiciones = self.condiciones_borrado(sol, estado, inv=inv)
        if not condiciones.ok:
            estado.error = condiciones.error or ErrorProxLaunch(
                CodigoError.ROLLBACK_INCIERTO, {"vmid": str(estado.vmid_reservado)}
            )
            return estado
        nodo = estado.nodo_reservado or sol.nodo
        vmid = estado.vmid_reservado
        assert vmid is not None  # lo garantiza ``condiciones_borrado``
        ctx = _Ejecucion(sol, inv, estado, cancelado)
        try:
            upid = self._sesion.cliente.eliminar_vm(nodo, vmid)
            tarea = self._esperar_tarea(ctx, nodo, upid)
            if tarea is None:
                estado.upid = upid
                estado.avisos.append(_AVISO_BORRADO_SIN_ESPERAR)
                return estado
            if tarea.exitstatus != "OK":
                estado.error = traducir_exitstatus(tarea.exitstatus)
                return estado
        except ErrorProxLaunch as e:
            estado.error = e
            return estado
        for paso in (PasoB2.CREAR, PasoB2.AMPLIAR, PasoB2.CLOUDINIT, PasoB2.CONVERTIR):
            estado.pasos[paso] = EstadoPaso.PENDIENTE
        estado.vmid_reservado_aqui = False
        estado.vmid_reservado = None
        estado.nombre_reservado = None
        estado.nodo_reservado = None
        estado.upid = None
        estado.error = None
        estado.avisos.append(_AVISO_BORRADA)
        return estado

    # --- Recorrido --------------------------------------------------------------------------

    def _recorrer(self, ctx: _Ejecucion) -> None:
        pasos: dict[PasoB2, Callable[[_Ejecucion], bool]] = {
            PasoB2.IMAGEN: self._paso_imagen,
            PasoB2.CREAR: self._paso_crear,
            PasoB2.AMPLIAR: self._paso_ampliar,
            PasoB2.CLOUDINIT: self._paso_cloudinit,
            PasoB2.CONVERTIR: self._paso_convertir,
        }
        for paso in PasoB2:
            estado = ctx.estado
            if estado.pasos[paso] in PASOS_RESUELTOS:
                continue
            if ctx.cancelado.is_set():
                return
            ctx.paso = paso
            if estado.pasos[paso] == EstadoPaso.INCIERTO:
                # Nunca se repite a ciegas (un POST repetido podría duplicar la operación).
                try:
                    self._comprobar_paso(ctx, paso)
                except ErrorProxLaunch as e:
                    estado.error = e  # no se pudo leer: el paso sigue dudoso y no se repite
                    self._notificar(ctx)
                    return
                self._notificar(ctx)
                if estado.pasos[paso] in PASOS_RESUELTOS:
                    continue
                if estado.pasos[paso] != EstadoPaso.PENDIENTE:
                    return
            if not pasos[paso](ctx):
                return

    # --- Paso 1: imagen ---------------------------------------------------------------------

    def _paso_imagen(self, ctx: _Ejecucion) -> bool:
        sol, estado = ctx.sol, ctx.estado
        volid = volid_de_imagen(sol)
        if sol.origen == OrigenImagen.YA_IMPORTADA or sol.accion_existente == AccionExistente.USAR:
            estado.volid_imagen = volid  # nada se escribe
            self._poner(ctx, PasoB2.IMAGEN, EstadoPaso.HECHO)
            return True
        destino = DestinoTransferencia(
            sol.nodo, sol.storage_import, Contenido.IMPORT, sol.nombre_archivo
        )
        reemplazar = sol.accion_existente == AccionExistente.REEMPLAZAR
        al_progresar: AlProgresar = ctx.al_progresar or (lambda _p: None)
        self._poner(ctx, PasoB2.IMAGEN, EstadoPaso.EN_CURSO)
        assert ctx.inv is not None
        try:
            if sol.origen == OrigenImagen.ARCHIVO_LOCAL:
                if sol.ruta_local is None:
                    raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "ruta_local"})
                resultado = self._transferencias.subir(
                    sol.ruta_local,
                    destino,
                    ctx.inv,
                    al_progresar=al_progresar,
                    cancelado=ctx.cancelado,
                    acepta_aviso_raiz=sol.acepta_aviso_raiz,
                    suma_esperada=sol.suma,
                    permitir_reemplazo=reemplazar,
                )
            else:
                if sol.url is None:
                    raise ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "url"})
                resultado = self._transferencias.descargar(
                    sol.url,
                    destino,
                    ctx.inv,
                    checksum=sol.suma,
                    verificar_certificados=sol.verificar_certificados,
                    al_progresar=al_progresar,
                    dejar_de_esperar=ctx.cancelado,
                    permitir_reemplazo=reemplazar,
                )
        except ErrorProxLaunch as e:  # destino inválido, otra transferencia en curso…
            self._fallar(ctx, PasoB2.IMAGEN, e)
            return False
        return self._aplicar_transferencia(ctx, resultado)

    def _aplicar_transferencia(self, ctx: _Ejecucion, res: ResultadoTransferencia) -> bool:
        estado = ctx.estado
        if res.estado == EstadoTransferencia.TERMINADA:
            estado.volid_imagen = res.volid or volid_de_imagen(ctx.sol)
            estado.upid = None
            self._poner(ctx, PasoB2.IMAGEN, EstadoPaso.HECHO)
            return True
        if res.estado == EstadoTransferencia.SIN_ESPERAR:
            # La copia sigue en el servidor y no se puede detener desde aquí.
            estado.upid = res.upid
            self._poner(ctx, PasoB2.IMAGEN, EstadoPaso.INCIERTO)
            return False
        if res.quedo_archivo is True and _AVISO_IMAGEN_EN_IMPORT not in estado.avisos:
            estado.avisos.append(_AVISO_IMAGEN_EN_IMPORT)  # la app no lo borra (RF-B2.10)
        error = res.error or ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, str(res.estado))
        if error.codigo == CodigoError.TRANSFERENCIA_CORTADA or error.codigo in CODIGOS_DE_RED:
            # Conexión perdida a mitad del paso (CA-B2.10.5): no se sabe cómo quedó.
            self._poner(ctx, PasoB2.IMAGEN, EstadoPaso.INCIERTO, error)
            return False
        self._fallar(ctx, PasoB2.IMAGEN, error)
        return False

    # --- Pasos 2 y 3: crear, importar y ampliar -----------------------------------------------

    def _paso_crear(self, ctx: _Ejecucion) -> bool:
        sol, estado = ctx.sol, ctx.estado
        if estado.vmid_reservado not in (None, sol.cfg.vmid):
            # Otro VMID tras un fallo: lo reservado antes ya no cuenta para el nuevo intento.
            if estado.vmid_reservado_aqui and estado.vmid_reservado is not None:
                # Era una máquina propia (con UPID): no se borra sola y el usuario debe saberlo.
                estado.avisos.append(
                    f"{AVISO_MAQUINA_ANTERIOR_SIN_BORRAR}:{estado.vmid_reservado}:"
                    f"{estado.nombre_reservado or ''}"
                )
            estado.vmid_reservado_aqui = False
            estado.vmid_reservado = None
            estado.nombre_reservado = None
            estado.nodo_reservado = None
            estado.upid = None
        cfg = cfg_de_creacion(sol, estado.volid_imagen or volid_de_imagen(sol))
        inv = self._inventario_con_imagen(ctx, cfg)
        servicio = self._fabrica(self._sesion, self._reloj)
        self._poner(ctx, PasoB2.CREAR, EstadoPaso.EN_CURSO)

        def al_cambiar_etapa(etapa: Etapa) -> None:
            if etapa == Etapa.AJUSTANDO:  # la creación terminó; sigue la ampliación (paso 3)
                ctx.disco_ya_del_tamano = self._disco_ya_del_tamano(cfg)
                estado.pasos[PasoB2.CREAR] = EstadoPaso.HECHO
                estado.pasos[PasoB2.AMPLIAR] = EstadoPaso.EN_CURSO
                self._notificar(ctx)

        def al_enviar(upid: str) -> None:
            estado.upid = upid
            estado.vmid_reservado_aqui = True
            estado.vmid_reservado = cfg.vmid
            estado.nombre_reservado = cfg.nombre
            estado.nodo_reservado = cfg.nodo
            self._notificar(ctx)

        resultado = servicio.crear(
            cfg,
            inv,
            al_cambiar_etapa,
            ctx.cancelado,
            al_enviar=al_enviar,
            parametros_extra=parametros_extra(sol.fijas, sol.storage_destino),
        )
        return self._aplicar_creacion(ctx, cfg, resultado)

    def _aplicar_creacion(
        self, ctx: _Ejecucion, cfg: ConfiguracionVM, res: ResultadoCreacion
    ) -> bool:
        """Traduce el desenlace de ``crear`` (o de ``comprobar_ahora``) a los pasos 2 y 3."""
        estado = ctx.estado
        for aviso in res.avisos:
            if aviso not in estado.avisos:
                estado.avisos.append(aviso)
        if res.upid is not None:
            estado.upid = res.upid
        d = res.desenlace
        if d in (Desenlace.OK, Desenlace.CON_AVISOS):
            estado.upid = None
            estado.pasos[PasoB2.CREAR] = EstadoPaso.HECHO
            detalle = cfg.detalle_origen
            ampliar = isinstance(detalle, DetalleImportacion) and detalle.ampliar_a_gib is not None
            if not ampliar or AVISO_AJUSTE_DISCO_OMITIDO in res.avisos or ctx.disco_ya_del_tamano:
                estado.pasos[PasoB2.AMPLIAR] = EstadoPaso.OMITIDO
                # CA-B2.6.3: solo se puede crecer. Sin ``ampliar`` el tamaño ya se conocía; con
                # URL el disco importado ya medía lo pedido y ``crear`` no envió ``resize``
                # (BUG-B-P3-3). En ambos casos se informa.
                if AVISO_SIN_AMPLIAR not in estado.avisos:
                    estado.avisos.append(AVISO_SIN_AMPLIAR)
            else:
                estado.pasos[PasoB2.AMPLIAR] = EstadoPaso.HECHO
            self._notificar(ctx)
            return True
        if d == Desenlace.PARCIAL:
            if not any(a.startswith(_PREFIJO_AJUSTE_PENDIENTE) for a in res.avisos):
                # La tarea de creación/importación falló y dejó la MV a medias: sin avisos
                # ``ajuste_pendiente:*`` el paso 2 no terminó y no se puede seguir (BUG-B-P3-4).
                self._fallar(ctx, PasoB2.CREAR, res.error)
                return False
            estado.pasos[PasoB2.CREAR] = EstadoPaso.HECHO
            self._fallar(ctx, PasoB2.AMPLIAR, res.error)
            return False
        if d in (Desenlace.CONEXION_PERDIDA, Desenlace.TIEMPO_AGOTADO):
            self._poner(ctx, PasoB2.CREAR, EstadoPaso.INCIERTO, res.error)
            return False
        if d == Desenlace.CANCELADO:
            # Dejó de esperar: con tarea en vuelo no se sabe cómo acabó; sin ella no se envió nada.
            nuevo = EstadoPaso.INCIERTO if res.upid is not None else EstadoPaso.PENDIENTE
            self._poner(ctx, PasoB2.CREAR, nuevo)
            return False
        self._fallar(ctx, PasoB2.CREAR, res.error)  # ERROR
        return False

    def _disco_ya_del_tamano(self, cfg: ConfiguracionVM) -> bool:
        """``True`` si el disco importado ya mide lo pedido y no hará falta ``resize``.

        Una lectura de la configuración de la MV (con URL el tamaño de la imagen no se conoce
        hasta importarla). Si la lectura falla devuelve ``False``: ``crear`` decide por su cuenta.
        """
        detalle = cfg.detalle_origen
        clave = clave_primer_disco(cfg)
        if not isinstance(detalle, DetalleImportacion) or detalle.ampliar_a_gib is None:
            return False
        if detalle.tamano_virtual_bytes is not None or clave is None:
            return False  # el tamaño ya se conocía al planificar: lo cubre ``necesita_ampliar``
        try:
            config = self._sesion.cliente.config_vm(cfg.nodo, cfg.vmid)
        except ErrorProxLaunch:
            return False
        if config is None:
            return False
        tam = next(
            (d.tamano_bytes for d in detalle_de_config(config).discos if d.clave == clave), None
        )
        if tam is None:
            return False
        return ampliacion_importacion(cfg, None, -(-tam // _GIB)) is None

    def _paso_ampliar(self, ctx: _Ejecucion) -> bool:
        """Reintento del paso 3 (``resize`` absoluto, idempotente): ``reintentar_ajustes``."""
        sol, estado = ctx.sol, ctx.estado
        cfg = cfg_de_creacion(sol, estado.volid_imagen or volid_de_imagen(sol))
        detalle = cfg.detalle_origen
        if not isinstance(detalle, DetalleImportacion) or detalle.ampliar_a_gib is None:
            estado.pasos[PasoB2.AMPLIAR] = EstadoPaso.OMITIDO
            if AVISO_SIN_AMPLIAR not in estado.avisos:
                estado.avisos.append(AVISO_SIN_AMPLIAR)
            self._notificar(ctx)
            return True
        self._poner(ctx, PasoB2.AMPLIAR, EstadoPaso.EN_CURSO)
        servicio = self._fabrica(self._sesion, self._reloj)
        assert ctx.inv is not None
        res = servicio.reintentar_ajustes(cfg, self._inventario_con_imagen(ctx, cfg), ctx.cancelado)
        if res.desenlace in (Desenlace.OK, Desenlace.CON_AVISOS):
            omitido = AVISO_AJUSTE_DISCO_OMITIDO in res.avisos
            for aviso in res.avisos:
                if aviso not in estado.avisos:
                    estado.avisos.append(aviso)
            nuevo = EstadoPaso.OMITIDO if omitido else EstadoPaso.HECHO
            self._poner(ctx, PasoB2.AMPLIAR, nuevo)
            return True
        if res.desenlace == Desenlace.CANCELADO:
            self._poner(ctx, PasoB2.AMPLIAR, EstadoPaso.PENDIENTE)
            return False
        self._fallar(
            ctx, PasoB2.AMPLIAR, res.error
        )  # el resize es idempotente: se puede reintentar
        return False

    def _inventario_con_imagen(self, ctx: _Ejecucion, cfg: ConfiguracionVM) -> Inventario:
        """Inventario cuyo catálogo YA conoce la imagen recién subida o descargada.

        ``crear`` valida contra el catálogo leído al planificar, que no la trae (V-O03). Se relee
        el listado del almacenamiento ``import`` (una lectura) y se sustituye en una copia; si
        la lectura falla se quita el listado (sin él la validación no afirma que falte; ``crear``
        la vuelve a comprobar contra el servidor, INV-O8). El inventario original no cambia.
        """
        inv = ctx.inv
        assert inv is not None
        catalogo = inv.catalogo
        if catalogo is None:
            return inv
        sol = ctx.sol
        restantes = tuple(
            lst
            for lst in catalogo.listados
            if not (
                lst.nodo == cfg.nodo
                and lst.contenido == Contenido.IMPORT
                and lst.storage == sol.storage_import
            )
        )
        try:
            volumenes = self._sesion.cliente.contenido_storage(
                cfg.nodo, sol.storage_import, Contenido.IMPORT
            )
            nuevo = ListadoStorage(cfg.nodo, sol.storage_import, Contenido.IMPORT, tuple(volumenes))
            restantes = (*restantes, nuevo)
        except ErrorProxLaunch:
            _log.info("No se pudo releer el contenido import; se valida sin listado")
        return dataclasses.replace(inv, catalogo=dataclasses.replace(catalogo, listados=restantes))

    # --- Paso 4: cloud-init -----------------------------------------------------------------

    def _paso_cloudinit(self, ctx: _Ejecucion) -> bool:
        sol, estado = ctx.sol, ctx.estado
        ci = sol.cloudinit
        if ci is None or ci.vacia:
            self._poner(ctx, PasoB2.CLOUDINIT, EstadoPaso.OMITIDO)
            return True
        nodo = estado.nodo_reservado or sol.nodo
        vmid = estado.vmid_reservado if estado.vmid_reservado is not None else sol.cfg.vmid
        self._poner(ctx, PasoB2.CLOUDINIT, EstadoPaso.EN_CURSO)
        cliente = self._sesion.cliente
        try:
            config = cliente.config_vm(nodo, vmid)
            if config is None:
                raise _inexistente(nodo, vmid)
            info = info_cloudinit(config)
            if info.unidad is False:
                raise ErrorProxLaunch(
                    CodigoError.CLOUDINIT_SIN_UNIDAD, {"plantilla": sol.cfg.nombre}
                )
            # Nunca contraseña en una plantilla (PB-1): se envía una copia sin ella.
            peticion = construir_put_cloudinit(dataclasses.replace(ci, contrasena=None), info)
            if not peticion:
                self._poner(ctx, PasoB2.CLOUDINIT, EstadoPaso.OMITIDO)
                return True
            cliente.configurar_vm(nodo, vmid, peticion)
        except ErrorProxLaunch as e:
            self._fallar(ctx, PasoB2.CLOUDINIT, e)
            return False
        self._poner(ctx, PasoB2.CLOUDINIT, EstadoPaso.HECHO)
        return True

    # --- Paso 5: convertir en plantilla -----------------------------------------------------

    def _paso_convertir(self, ctx: _Ejecucion) -> bool:
        sol, estado = ctx.sol, ctx.estado
        nodo = estado.nodo_reservado or sol.nodo
        vmid = estado.vmid_reservado if estado.vmid_reservado is not None else sol.cfg.vmid
        cliente = self._sesion.cliente
        self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.EN_CURSO)
        try:
            config = cliente.config_vm(nodo, vmid)
            if config is None:
                raise _inexistente(nodo, vmid)
            if _es_plantilla(config):  # ya convertida (p. ej. tras una conexión perdida)
                self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.HECHO)
                return True
            actual = cliente.estado_actual_vm(nodo, vmid)
            situacion = str(actual.get("status", ""))
            bloqueo = str(actual.get("lock") or config.get("lock") or "")
            if situacion != "stopped" or bloqueo:
                # CA-B2.9.3: no se convierte una máquina en marcha o bloqueada; ningún POST.
                raise ErrorProxLaunch(
                    CodigoError.PLANTILLA_NO_APAGADA, {"estado": situacion, "bloqueo": bloqueo}
                )
        except ErrorProxLaunch as e:
            self._fallar(ctx, PasoB2.CONVERTIR, e)
            return False
        if ctx.cancelado.is_set():
            self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.PENDIENTE)
            return False
        try:
            upid = cliente.convertir_en_plantilla(nodo, vmid)
        except ErrorProxLaunch as e:
            incierto = e.codigo in CODIGOS_DE_RED or e.params.get("incierto") == "1"
            if incierto:
                self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.INCIERTO, e)
            else:
                self._fallar(ctx, PasoB2.CONVERTIR, e)
            return False
        return self._tras_conversion(ctx, nodo, vmid, upid)

    def _tras_conversion(self, ctx: _Ejecucion, nodo: str, vmid: int, upid: str | None) -> bool:
        """Espera la tarea ``qmtemplate`` (si hay) y comprueba que ``template`` quedó en 1."""
        estado = ctx.estado
        estado.upid = upid
        try:
            if upid is not None:
                tarea = self._esperar_tarea(ctx, nodo, upid)
                if tarea is None:  # dejó de esperar: la tarea sigue en el servidor
                    self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.INCIERTO)
                    return False
                if tarea.exitstatus != "OK":
                    self._fallar(ctx, PasoB2.CONVERTIR, traducir_exitstatus(tarea.exitstatus))
                    return False
            config = self._sesion.cliente.config_vm(nodo, vmid)
        except ErrorProxLaunch as e:
            self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.INCIERTO, e)  # no se sabe cómo acabó
            return False
        if config is not None and _es_plantilla(config):
            estado.upid = None
            self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.HECHO)
            return True
        self._fallar(
            ctx,
            PasoB2.CONVERTIR,
            ErrorProxLaunch(CodigoError.DESCONOCIDO, {"motivo": "sin_template"}),
        )
        return False

    # --- Comprobación de pasos dudosos (solo lecturas) --------------------------------------

    def _comprobar_paso(self, ctx: _Ejecucion, paso: PasoB2) -> None:
        if paso == PasoB2.IMAGEN:
            self._comprobar_imagen(ctx)
        elif paso == PasoB2.CREAR:
            self._comprobar_creacion(ctx)
        elif paso == PasoB2.CONVERTIR:
            self._comprobar_conversion(ctx)
        # Los pasos 3 y 4 son idempotentes y nunca quedan ``INCIERTO``.

    def _comprobar_imagen(self, ctx: _Ejecucion) -> None:
        sol, estado = ctx.sol, ctx.estado
        cliente = self._sesion.cliente
        if estado.upid is not None:
            tarea = cliente.estado_tarea(sol.nodo, estado.upid)
            if not tarea.terminada:
                return  # la copia sigue en el servidor: se queda dudoso
            if tarea.exitstatus != "OK":
                self._fallar(ctx, PasoB2.IMAGEN, traducir_exitstatus(tarea.exitstatus))
                return
        if sol.origen == OrigenImagen.URL and estado.upid is None:
            return  # sin tarea no hay forma de saber si la descarga acabó: sigue dudoso
        esperado = volid_de_imagen(sol)
        volumenes = cliente.contenido_storage(sol.nodo, sol.storage_import, Contenido.IMPORT)
        propio = next((v for v in volumenes if v.volid == esperado), None)
        if propio is None:
            return  # aún no está: sigue dudoso
        if sol.ruta_local is not None and sol.origen == OrigenImagen.ARCHIVO_LOCAL:
            try:
                local = sol.ruta_local.stat().st_size
            except OSError:
                local = None
            if local is not None and propio.tamano_bytes not in (None, local):
                return  # tamaño distinto: una copia a medias no se da por buena
        estado.volid_imagen = propio.volid
        estado.upid = None
        estado.error = None
        self._poner(ctx, PasoB2.IMAGEN, EstadoPaso.HECHO)

    def _comprobar_creacion(self, ctx: _Ejecucion) -> None:
        sol, estado = ctx.sol, ctx.estado
        cfg = cfg_de_creacion(sol, estado.volid_imagen or volid_de_imagen(sol))
        servicio = self._fabrica(self._sesion, self._reloj)
        if estado.upid is not None:
            res = servicio.comprobar_ahora(cfg, estado.upid, inv=ctx.inv)
            if res.desenlace in (Desenlace.TIEMPO_AGOTADO, Desenlace.CONEXION_PERDIDA):
                estado.error = res.error  # sigue dudoso
                return
            self._aplicar_creacion(ctx, cfg, res)
            return
        existe = servicio.existe_vm(cfg)
        if existe is False:
            estado.error = None
            self._poner(ctx, PasoB2.CREAR, EstadoPaso.PENDIENTE)  # nada se creó: es seguro repetir
            return
        if existe is None:
            return
        # Sin UPID no se puede probar que la máquina sea del asistente (otra persona pudo crear una
        # con ese nombre): no se infiere la propiedad. El paso sigue dudoso y no se ofrece borrar;
        # con otro VMID libre se puede reintentar.
        estado.error = ErrorProxLaunch(
            CodigoError.ROLLBACK_NO_PROPIA,
            {"nombre": cfg.nombre, "vmid": str(cfg.vmid), "nodo": cfg.nodo, "motivo": "sin_upid"},
        )

    def _comprobar_conversion(self, ctx: _Ejecucion) -> None:
        sol, estado = ctx.sol, ctx.estado
        nodo = estado.nodo_reservado or sol.nodo
        vmid = estado.vmid_reservado if estado.vmid_reservado is not None else sol.cfg.vmid
        cliente = self._sesion.cliente
        if estado.upid is not None:
            tarea = cliente.estado_tarea(nodo, estado.upid)
            if not tarea.terminada:
                return  # la conversión sigue en marcha
            if tarea.exitstatus != "OK":
                self._fallar(ctx, PasoB2.CONVERTIR, traducir_exitstatus(tarea.exitstatus))
                return
        config = cliente.config_vm(nodo, vmid)
        if config is not None and _es_plantilla(config):
            estado.upid = None
            estado.error = None
            self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.HECHO)
        elif config is not None and estado.upid is None:
            estado.error = None
            self._poner(ctx, PasoB2.CONVERTIR, EstadoPaso.PENDIENTE)  # el POST no llegó a actuar

    # --- Borrado ----------------------------------------------------------------------------

    @staticmethod
    def _juzgar_borrado(
        config: dict[str, Any] | None,
        actual: dict[str, Any],
        nombre: str,
        params: dict[str, str],
    ) -> CondicionesBorrado:
        def no(codigo: CodigoError, motivo: str) -> CondicionesBorrado:
            return CondicionesBorrado(False, ErrorProxLaunch(codigo, {**params, "motivo": motivo}))

        if config is None:
            return no(CodigoError.ROLLBACK_NO_PROPIA, "no_existe")
        if config.get("name") != nombre:
            return no(CodigoError.ROLLBACK_NO_PROPIA, "nombre")
        if _es_plantilla(config):
            return no(CodigoError.ROLLBACK_NO_PROPIA, "plantilla")
        if config.get("lock") or actual.get("lock"):
            return no(CodigoError.ROLLBACK_BLOQUEADA, "lock")
        if _como_entero(config.get("protection")) == 1:
            return no(CodigoError.ROLLBACK_PROTEGIDA, "protection")
        if str(actual.get("status", "")) == "running":
            return no(CodigoError.ROLLBACK_ENCENDIDA, "running")
        return CondicionesBorrado(True)

    # --- Utilidades -------------------------------------------------------------------------

    def _esperar_tarea(self, ctx: _Ejecucion, nodo: str, upid: str) -> EstadoTarea | None:
        """Sondea una tarea corta hasta que termine. ``None`` si el usuario dejó de esperar.

        Tolera caídas de red hasta ``tolerancia_red_s`` y agota en ``max_espera_tarea_s``
        (``TAREA_TIEMPO_AGOTADO``). No cancela nada en el servidor.
        """
        inicio = self._reloj.ahora()
        primer_fallo: float | None = None
        while True:
            if ctx.cancelado.is_set():
                return None
            try:
                tarea = self._sesion.cliente.estado_tarea(nodo, upid)
                primer_fallo = None
            except ErrorProxLaunch as e:
                if e.codigo not in CODIGOS_DE_RED:
                    raise
                ahora = self._reloj.ahora()
                if primer_fallo is None:
                    primer_fallo = ahora
                elif ahora - primer_fallo > self._tolerancia_red:
                    raise
                self._reloj.dormir(self._intervalo)
                continue
            if tarea.terminada:
                return tarea
            if self._reloj.ahora() - inicio > self._max_espera:
                raise ErrorProxLaunch(CodigoError.TAREA_TIEMPO_AGOTADO, {"upid": upid})
            self._reloj.dormir(self._intervalo)

    def _poner(
        self,
        ctx: _Ejecucion,
        paso: PasoB2,
        valor: EstadoPaso,
        error: ErrorProxLaunch | None = None,
    ) -> None:
        ctx.estado.pasos[paso] = valor
        if error is not None:
            ctx.estado.error = error
        self._notificar(ctx)

    def _fallar(self, ctx: _Ejecucion, paso: PasoB2, error: ErrorProxLaunch | None) -> None:
        """Deja el paso ``FALLIDO`` con su error. No deshace nada (RF-B2.10)."""
        ctx.estado.pasos[paso] = EstadoPaso.FALLIDO
        ctx.estado.error = error or ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, str(paso))
        self._notificar(ctx)

    @staticmethod
    def _notificar(ctx: _Ejecucion) -> None:
        """Entrega una copia del estado a la interfaz; un fallo suyo no detiene el asistente."""
        if ctx.al_cambiar is None:
            return
        try:
            ctx.al_cambiar(ctx.estado.copia())
        except Exception:
            _log.exception("El observador del asistente de plantillas falló")
