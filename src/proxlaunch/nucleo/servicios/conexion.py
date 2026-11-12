"""ServicioConexion: del perfil a una Sesion."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from proxlaunch.nucleo.api.autenticacion import (
    Autenticador,
    AutenticadorTicket,
    AutenticadorToken,
    DesafioTFA,
    TipoTFA,
    iniciar_sesion_ticket,
    responder_tfa,
)
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.huella import obtener_huella
from proxlaunch.nucleo.api.transporte import (
    TIMEOUT_CONEXION,
    Transporte,
)
from proxlaunch.nucleo.capacidades import VERSION_MINIMA, Capacidades, capacidades_para
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import (
    CredencialContrasena,
    CredencialToken,
    PerfilConexion,
    Ticket,
)
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.registro import registrar_secreto
from proxlaunch.nucleo.reloj import Reloj

_log = logging.getLogger("proxlaunch.servicios.conexion")

FabricaTransporte = Callable[[PerfilConexion, Mapping[str, str]], Transporte]
ObtenerHuella = Callable[[str, int, float], str]

# Privilegios mínimos del rol ProxLaunchCreador (f1 §5) que se comprueban tras conectar.
PRIVILEGIOS_REQUERIDOS = (
    "VM.Allocate",
    "VM.Audit",
    "VM.Config.Options",
    "VM.Config.HWType",
    "VM.Config.CPU",
    "VM.Config.Memory",
    "VM.Config.Network",
    "VM.Config.Disk",
    "Datastore.AllocateSpace",
    "SDN.Use",
    "Sys.Audit",
)


class EstadoHuella(StrEnum):
    """Situación de la huella SSL frente a la guardada (RF-05, RF-06)."""

    NUEVA = "nueva"
    CONFIRMADA = "confirmada"
    CAMBIADA = "cambiada"
    IGNORADA = "ignorada"  # el perfil ignora la verificación SSL: no hay huella


class CodigoAviso(StrEnum):
    """Avisos no bloqueantes de la sesión; la interfaz los traduce."""

    LLAVERO_NO_DISPONIBLE = "llavero_no_disponible"  # CA-08.4
    TOPOLOGIA_DEGRADADA = "topologia_degradada"  # A-6
    PERMISOS_INCOMPLETOS = "permisos_incompletos"  # RF-12


@dataclass(frozen=True)
class Aviso:
    """Aviso no bloqueante con parámetros."""

    codigo: CodigoAviso
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InformacionHuella:
    """Huella observada de un host frente a la guardada (para el diálogo de confianza)."""

    host: str
    puerto: int
    estado: EstadoHuella
    huella_observada: str | None
    huella_guardada: str | None


@dataclass
class Sesion:
    """Conexión establecida y verificada, lista para descubrir y crear."""

    perfil: PerfilConexion
    cliente: ClienteProxmox
    version: Version
    capacidades: Capacidades
    host_activo: str
    usuario_efectivo: str
    avisos: list[Aviso] = field(default_factory=list)


@dataclass
class _Pendiente:
    """Estado entre el paso 1 y el paso 2 del 2FA."""

    perfil: PerfilConexion
    transporte: Transporte
    version_forzada: tuple[int, int] | None
    # Solo si el perfil pide recordar la contraseña; se descarta al terminar.
    contrasena_a_recordar: str | None


class ServicioConexion:
    """Orquesta huella, autenticación, versión y llavero.

    Args:
        transporte_fabrica: crea el transporte de un perfil con sus huellas confiadas.
        huellas: repositorio de huellas confiadas.
        secretos: llavero.
        reloj: reloj inyectable (renovación del ticket).
        obtener_huella_fn: lectura de la huella remota (inyectable en pruebas).
    """

    def __init__(
        self,
        transporte_fabrica: FabricaTransporte,
        huellas: RepositorioHuellas,
        secretos: AlmacenSecretos,
        reloj: Reloj,
        obtener_huella_fn: ObtenerHuella = obtener_huella,
    ) -> None:
        self._fabrica = transporte_fabrica
        self._huellas = huellas
        self._secretos = secretos
        self._reloj = reloj
        self._obtener_huella = obtener_huella_fn
        self._pendientes: dict[str, _Pendiente] = {}
        self._cerrojo = threading.Lock()

    # --- Huella -----------------------------------------------------------------------

    def consultar_huellas(self, perfil: PerfilConexion) -> list[InformacionHuella]:
        """Lee la huella de cada host alcanzable SIN enviar credenciales (CA-05.1).

        Los hosts que no responden se omiten; si ninguno responde se lanza
        ``SERVIDOR_NO_RESPONDE``.
        """
        if perfil.ignorar_ssl:
            return [
                InformacionHuella(h, perfil.puerto, EstadoHuella.IGNORADA, None, None)
                for h in perfil.hosts
            ]
        resultado: list[InformacionHuella] = []
        motivos: list[str] = []
        for host in perfil.hosts:
            try:
                observada = self._obtener_huella(host, perfil.puerto, TIMEOUT_CONEXION)
            except ErrorProxLaunch as e:
                motivos.append(f"{host}={e.detalle_tecnico or e.codigo}")
                continue
            guardada = self._huellas.obtener(host, perfil.puerto)
            if guardada is None:
                estado = EstadoHuella.NUEVA
            elif guardada.upper() == observada.upper():
                estado = EstadoHuella.CONFIRMADA
            else:
                estado = EstadoHuella.CAMBIADA
            resultado.append(InformacionHuella(host, perfil.puerto, estado, observada, guardada))
        if not resultado:
            raise ErrorProxLaunch(
                CodigoError.SERVIDOR_NO_RESPONDE,
                {
                    "host": perfil.hosts[0] if perfil.hosts else "",
                    "hosts": ",".join(perfil.hosts),
                    "motivos": ";".join(motivos),
                },
                ";".join(motivos),
            )
        return resultado

    def preparar(self, perfil: PerfilConexion) -> EstadoHuella:
        """Estado global de la huella: el peor de los hosts (CAMBIADA > NUEVA > CONFIRMADA)."""
        estados = {i.estado for i in self.consultar_huellas(perfil)}
        for estado in (
            EstadoHuella.CAMBIADA,
            EstadoHuella.NUEVA,
            EstadoHuella.CONFIRMADA,
        ):
            if estado in estados:
                return estado
        return EstadoHuella.IGNORADA

    def confiar_huella(self, perfil: PerfilConexion, host: str, huella: str) -> None:
        """Guarda la huella de ``host:puerto`` tras la decisión del usuario (CA-05.2).

        Lanza ``HUELLA_CAMBIADA`` si ya hay otra distinta: ver ``reemplazar_huella``.
        """
        self._huellas.guardar(host, perfil.puerto, huella)

    def reemplazar_huella(self, perfil: PerfilConexion, host: str, huella: str) -> None:
        """Sustituye la huella guardada (solo modo avanzado, con confirmación; P-12)."""
        self._huellas.reemplazar(host, perfil.puerto, huella)

    # --- Conexión ---------------------------------------------------------------------

    def conectar(
        self,
        perfil: PerfilConexion,
        credencial: CredencialToken | CredencialContrasena,
        *,
        version_forzada: tuple[int, int] | None = None,
    ) -> Sesion | DesafioTFA:
        """Conecta con el perfil. Devuelve ``DesafioTFA`` si hace falta el segundo factor.

        Sin huella confiada para ningún host (y sin ``ignorar_ssl``) lanza
        ``HUELLA_NO_CONFIADA`` antes de abrir conexión ni enviar credenciales (RNF-07).
        """
        huellas: dict[str, str] = {}
        if not perfil.ignorar_ssl:
            for host in perfil.hosts:
                guardada = self._huellas.obtener(host, perfil.puerto)
                if guardada:
                    huellas[host] = guardada
            if not huellas:
                raise ErrorProxLaunch(
                    CodigoError.HUELLA_NO_CONFIADA,
                    {"host": perfil.hosts[0] if perfil.hosts else ""},
                )
        transporte = self._fabrica(perfil, huellas)

        if isinstance(credencial, CredencialToken):
            auth = AutenticadorToken(credencial)
            secreto = f"{credencial.token_id}={credencial.secreto}"
            return self._finalizar(
                perfil, transporte, auth, credencial.token_id, secreto, version_forzada
            )

        registrar_secreto(credencial.contrasena)
        resultado = iniciar_sesion_ticket(
            transporte,
            credencial.usuario,
            credencial.realm,
            credencial.contrasena,
            reloj=self._reloj,
        )
        recordar = credencial.contrasena if perfil.recordar_credenciales else None
        if isinstance(resultado, DesafioTFA):
            with self._cerrojo:
                self._pendientes[resultado.ticket_parcial] = _Pendiente(
                    perfil, transporte, version_forzada, recordar
                )
            return resultado
        return self._finalizar_ticket(perfil, transporte, resultado, recordar, version_forzada)

    def completar_tfa(self, desafio: DesafioTFA, codigo: str, tipo: TipoTFA) -> Sesion:
        """Paso 2 del 2FA. Con un código incorrecto se puede reintentar con el mismo desafío."""
        with self._cerrojo:
            pendiente = self._pendientes.get(desafio.ticket_parcial)
        if pendiente is None:
            raise ErrorProxLaunch(CodigoError.SESION_EXPIRADA, {}, "no hay un 2FA pendiente")
        try:
            ticket = responder_tfa(pendiente.transporte, desafio, codigo, tipo, reloj=self._reloj)
        except ErrorProxLaunch as e:
            if e.codigo != CodigoError.TFA_CODIGO_INCORRECTO:
                self._descartar(desafio)
            raise
        self._descartar(desafio)
        return self._finalizar_ticket(
            pendiente.perfil,
            pendiente.transporte,
            ticket,
            pendiente.contrasena_a_recordar,
            pendiente.version_forzada,
        )

    # --- Internos ---------------------------------------------------------------------

    def _descartar(self, desafio: DesafioTFA) -> None:
        with self._cerrojo:
            self._pendientes.pop(desafio.ticket_parcial, None)

    def _finalizar_ticket(
        self,
        perfil: PerfilConexion,
        transporte: Transporte,
        ticket: Ticket,
        secreto: str | None,
        version_forzada: tuple[int, int] | None,
    ) -> Sesion:
        auth = AutenticadorTicket(ticket, self._reloj)
        return self._finalizar(perfil, transporte, auth, ticket.usuario, secreto, version_forzada)

    def _finalizar(
        self,
        perfil: PerfilConexion,
        transporte: Transporte,
        auth: Autenticador,
        usuario_efectivo: str,
        secreto: str | None,
        version_forzada: tuple[int, int] | None,
    ) -> Sesion:
        """Comprueba la versión y, solo si todo fue bien, guarda el secreto (RF-08)."""
        cliente = ClienteProxmox(transporte, auth, self._reloj)
        version = cliente.version()
        if (version.mayor, version.menor) < VERSION_MINIMA:
            raise ErrorProxLaunch(
                CodigoError.VERSION_NO_SOPORTADA,
                {"version": version.texto, "minima": f"{VERSION_MINIMA[0]}.{VERSION_MINIMA[1]}"},
                f"versión {version.texto}",
            )
        sesion = Sesion(
            perfil=perfil,
            cliente=cliente,
            version=version,
            capacidades=capacidades_para(version, version_forzada),
            host_activo=transporte.host_activo,
            usuario_efectivo=usuario_efectivo,
        )
        if perfil.recordar_credenciales and secreto:
            try:
                self._secretos.guardar(perfil.id, secreto)
            except ErrorProxLaunch as e:
                if e.codigo != CodigoError.LLAVERO_NO_DISPONIBLE:
                    raise
                sesion.avisos.append(Aviso(CodigoAviso.LLAVERO_NO_DISPONIBLE))
        return sesion


def permisos_faltantes(sesion: Sesion) -> list[str] | None:
    """Privilegios del rol recomendado que el usuario no tiene en ninguna ruta (RF-12).

    Es una comprobación indulgente: un privilegio cuenta como presente si el usuario lo
    tiene en cualquier ruta. Devuelve ``None`` si la consulta falla (CA-12.3), y añade el
    aviso ``PERMISOS_INCOMPLETOS`` a la sesión si faltan.
    """
    try:
        permisos = sesion.cliente.permisos()
    except ErrorProxLaunch:
        return None
    presentes = {p for privs in permisos.values() for p, v in privs.items() if v}
    faltan = [p for p in PRIVILEGIOS_REQUERIDOS if p not in presentes]
    if faltan:
        sesion.avisos.append(
            Aviso(CodigoAviso.PERMISOS_INCOMPLETOS, {"privilegios": ",".join(faltan)})
        )
    return faltan
