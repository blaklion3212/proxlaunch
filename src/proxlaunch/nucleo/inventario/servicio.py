"""Servicio del inventario de lotes (DT-C12, DT-C13; flujo 3.6). Bloqueante: va en trabajadores.

Lee ``/cluster/resources`` una vez, el detalle de un lote con concurrencia acotada y delega el
borrado en ``ServicioRollback`` con la regla de propiedad del inventario (sin tocar D-21).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Collection
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from proxlaunch.nucleo.agente.clasificacion import Clase, clasificar_error
from proxlaunch.nucleo.agente.seleccion import elegir_ip, interpretar_interfaces
from proxlaunch.nucleo.cloudinit.deteccion import info_cloudinit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.inventario.agrupacion import agrupar_lotes
from proxlaunch.nucleo.inventario.modelos import (
    MAX_LECTURAS_INVENTARIO,
    DetalleLote,
    EstadoIpInventario,
    EstadoNota,
    IpInventario,
    ListaLotes,
    LoteServidor,
    MotivoNoDeshacible,
    MVInventario,
)
from proxlaunch.nucleo.inventario.propiedad import (
    ESTADOS_CONOCIDOS,
    candidatos_inventario,
    es_propia_inventario,
    evaluar_mv,
    mv_sin_detalle,
    problema_seleccion,
)
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.rollback import (
    InspeccionRollback,
    ResultadoRollback,
    ServicioRollback,
)
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import RecursoVM
from proxlaunch.nucleo.origen.permisos import estado_privilegio, privilegios_agente
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.conexion import Sesion

_log = logging.getLogger("proxlaunch.inventario")


class ServicioInventario:
    """Lista lotes del servidor, detalla uno, exporta datos y lo deshace con doble control."""

    def __init__(
        self, sesion: Sesion, reloj: Reloj, *, max_lecturas: int = MAX_LECTURAS_INVENTARIO
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._max_lecturas = max(1, max_lecturas)
        self._rollback = ServicioRollback(
            sesion, reloj, regla_propiedad=es_propia_inventario, estados_conocidos=ESTADOS_CONOCIDOS
        )

    # --- Lectura ----------------------------------------------------------------------

    def listar(self) -> ListaLotes:
        """Una sola petición (``/cluster/resources``). Lanza ``ErrorProxLaunch``."""
        return agrupar_lotes(self._sesion.cliente.recursos_vm())

    def detallar(
        self, lote: LoteServidor, cancelado: threading.Event, permisos: PermisosEfectivos | None
    ) -> DetalleLote:
        """Un ``GET config`` por MV del lote, como máximo ``max_lecturas`` a la vez.

        Un fallo en una MV solo afecta a esa fila. Con ``cancelado`` las MVs no leídas quedan
        «sin detalle» y el resultado, ``completo=False``.
        """

        def leer(recurso: RecursoVM) -> MVInventario:
            if cancelado.is_set():
                return mv_sin_detalle(recurso)
            if recurso.nodo is None:
                return evaluar_mv(
                    recurso, lote, None, ErrorProxLaunch(CodigoError.DESCONOCIDO), permisos
                )
            try:
                config = self._sesion.cliente.config_vm_legible(recurso.nodo, recurso.vmid)
            except ErrorProxLaunch as e:
                return evaluar_mv(recurso, lote, None, e, permisos)
            except Exception:
                _log.warning("Inventario: no se pudo leer la config de vmid=%s", recurso.vmid)
                return evaluar_mv(
                    recurso, lote, None, ErrorProxLaunch(CodigoError.DESCONOCIDO), permisos
                )
            return evaluar_mv(recurso, lote, config, None, permisos)

        with ThreadPoolExecutor(max_workers=self._max_lecturas) as pool:
            maquinas = tuple(pool.map(leer, lote.recursos))
        fechas: list[datetime] = [
            mv.nota.fecha
            for mv in maquinas
            if mv.nota is not None and mv.nota.estado == EstadoNota.COINCIDE and mv.nota.fecha
        ]
        completo = not any(MotivoNoDeshacible.SIN_DETALLE in mv.motivos for mv in maquinas)
        return DetalleLote(lote, maquinas, min(fechas) if fechas else None, completo)

    # --- Deshacer ---------------------------------------------------------------------

    def inspeccionar(
        self, detalle: DetalleLote, marcadas: Collection[int], permisos: PermisosEfectivos | None
    ) -> InspeccionRollback:
        """Solo lectura: encendidas, protegidas e ilegibles entre las marcadas deshacibles."""
        candidatos = candidatos_inventario(detalle, marcadas)
        return self._rollback.inspeccionar(
            candidatos, id_lote=detalle.lote.codigo, etiquetado=True, permisos=permisos
        )

    def deshacer(
        self,
        detalle: DetalleLote,
        marcadas: Collection[int],
        observador: Callable[[ResultadoRollback], None],
        control: ControlLote,
        *,
        forzar_apagado: frozenset[int],
        forzar_desproteccion: frozenset[int],
        permisos: PermisosEfectivos | None,
    ) -> list[ResultadoRollback]:
        """Borra las marcadas deshacibles con ``ServicioRollback`` (mismo ``DELETE``, sin purge).

        Antes de cada ``DELETE`` se relee la config y se vuelve a exigir la regla de propiedad
        del inventario. Más de ``MAX_LOTE`` marcadas lanza ``ValueError`` (V-C09).

        Raises:
            ValueError: si hay más MVs marcadas que ``MAX_LOTE``.
        """
        if problema_seleccion(len(set(marcadas))) == "V-C09":
            raise ValueError("demasiadas máquinas marcadas (V-C09)")
        candidatos = candidatos_inventario(detalle, marcadas)
        return self._rollback.deshacer(
            candidatos,
            observador,
            control,
            id_lote=detalle.lote.codigo,
            etiquetado=True,
            forzar_apagado=forzar_apagado,
            forzar_desproteccion=forzar_desproteccion,
            permisos=permisos,
        )

    # --- IP del agente ----------------------------------------------------------------

    def obtener_ips(
        self,
        detalle: DetalleLote,
        vmids: Collection[int],
        cancelado: threading.Event,
        permisos: PermisosEfectivos | None,
    ) -> dict[int, IpInventario]:
        """Una sonda del agente por MV (sin espera), ≤ ``max_lecturas`` a la vez (CA-C1.7.4).

        Solo se consulta a las ``running`` con ``agent`` activo y privilegio de agente no
        negado; las demás se resuelven sin petición. Las MVs no procesadas por cancelación no
        aparecen en el resultado. Solo lectura.
        """
        pedidas = frozenset(vmids)
        recursos = [mv.recurso for mv in detalle.maquinas if mv.recurso.vmid in pedidas]

        def sondear(recurso: RecursoVM) -> tuple[int, IpInventario | None]:
            if cancelado.is_set():
                return recurso.vmid, None
            return recurso.vmid, self._ip_de(recurso, permisos)

        with ThreadPoolExecutor(max_workers=self._max_lecturas) as pool:
            pares = list(pool.map(sondear, recursos))
        return {vmid: ip for vmid, ip in pares if ip is not None}

    def _ip_de(self, recurso: RecursoVM, permisos: PermisosEfectivos | None) -> IpInventario:
        if (recurso.estado or "").lower() != "running" or recurso.nodo is None:
            return IpInventario(EstadoIpInventario.APAGADA)
        cliente = self._sesion.cliente
        ruta = f"/vms/{recurso.vmid}"
        privilegios = privilegios_agente(self._sesion.capacidades)
        if permisos is not None and all(
            estado_privilegio(permisos, p, ruta) is False for p in privilegios
        ):
            return IpInventario(EstadoIpInventario.SIN_PERMISO)
        try:
            config = cliente.config_vm(recurso.nodo, recurso.vmid)
            if config is None:
                return IpInventario(EstadoIpInventario.SIN_RESPUESTA)
            info = info_cloudinit(config)
            if not info.agente:
                return IpInventario(EstadoIpInventario.SIN_AGENTE)
            respuesta = cliente.interfaces_agente(recurso.nodo, recurso.vmid)
        except ErrorProxLaunch as e:
            clase = clasificar_error(e)
            if clase == Clase.FATAL:
                raise
            if clase == Clase.SIN_AGENTE:
                return IpInventario(EstadoIpInventario.SIN_AGENTE)
            if clase == Clase.SIN_PERMISO:
                return IpInventario(EstadoIpInventario.SIN_PERMISO)
            return IpInventario(EstadoIpInventario.SIN_RESPUESTA)
        eleccion = elegir_ip(interpretar_interfaces(respuesta), info.mac_net0, final=True)
        if eleccion is None:
            return IpInventario(EstadoIpInventario.SIN_IP)
        return IpInventario(EstadoIpInventario.OK, eleccion.principal)
