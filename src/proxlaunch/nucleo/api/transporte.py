"""Transporte HTTP: TLS con huella, timeouts y failover de hosts."""

from __future__ import annotations

import http.client
import logging
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol

import requests
import urllib3
from requests.adapters import HTTPAdapter

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket
from proxlaunch.nucleo.api.traductor_errores import (
    ESTADOS_NODO_CAIDO,
    es_huella_distinta,
    limpiar_detalle,
    nodo_de_ruta,
    traducir_http,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.constantes import MAX_NODOS_PARALELOS, MAX_PETICIONES_SIMULTANEAS

if TYPE_CHECKING:
    from proxlaunch.nucleo.api.autenticacion import Autenticador
    from proxlaunch.nucleo.modelos.conexion import PerfilConexion

TIMEOUT_CONEXION = 10  # segundos por host (RNF-03)
TIMEOUT_LECTURA = 30  # segundos por petición (RNF-03)
PREFIJO_API = "/api2/json"
_METODOS_SEGUROS = frozenset({"GET", "HEAD"})
# Conexiones simultáneas por host: sondeos del lote + una creación por nodo en paralelo.
POOL_MAXSIZE = MAX_PETICIONES_SIMULTANEAS + MAX_NODOS_PARALELOS

_log = logging.getLogger("proxlaunch.api.transporte")


class Transporte(Protocol):
    """Contrato mínimo que usan la autenticación y el cliente."""

    def peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        """Ejecuta la petición y devuelve el campo ``data`` de la respuesta."""
        ...

    @property
    def host_activo(self) -> str:
        """Host que respondió a la última petición correcta."""
        ...

    def usar_autenticador(self, auth: Autenticador | None) -> None:
        """Fija (o quita) el autenticador que firma cada petición."""
        ...


class AdaptadorHuella(HTTPAdapter):
    """Adaptador que fija la huella SHA-256 del certificado del servidor.

    Pasa ``assert_fingerprint`` y ``cert_reqs="CERT_NONE"`` a urllib3: la huella
    sustituye a la validación de la cadena y del nombre (certificados autofirmados).
    """

    def __init__(self, huella: str | None, **kwargs: Any) -> None:
        # Debe fijarse antes de ``super().__init__``: este llama a ``init_poolmanager``.
        self._huella = huella
        super().__init__(**kwargs)

    def _con_huella(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self._huella:
            kwargs["assert_fingerprint"] = self._huella
            kwargs["cert_reqs"] = "CERT_NONE"
        return kwargs

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        super().init_poolmanager(*args, **self._con_huella(kwargs))

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> Any:
        return super().proxy_manager_for(proxy, **self._con_huella(proxy_kwargs))


class AdaptadorBloqueado(HTTPAdapter):
    """Adaptador de último recurso: cualquier destino sin adaptador de huella se rechaza
    (falla en cerrado, Seg M1)."""

    def send(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        raise requests.exceptions.InvalidURL("destino sin adaptador de huella: bloqueado")


def _cadena(exc: BaseException) -> Iterator[BaseException]:
    """Recorre la excepción, sus ``args``, causas, contextos y ``reason`` (sin repetir)."""
    visto: set[int] = set()
    pendientes: list[Any] = [exc]
    while pendientes:
        actual = pendientes.pop()
        if id(actual) in visto:
            continue
        visto.add(id(actual))
        if isinstance(actual, BaseException):
            yield actual
            pendientes.extend(actual.args)
            pendientes.extend(x for x in (actual.__cause__, actual.__context__) if x)
            razon = getattr(actual, "reason", None)
            if razon is not None:
                pendientes.append(razon)


def _fallo_antes_de_enviar(exc: BaseException) -> bool:
    """``True`` si hay certeza de que la petición no salió: falló al establecer la conexión.

    Recorre la cadena de excepciones buscando ``NewConnectionError`` o un timeout de
    conexión de urllib3. Cualquier otro fallo (p. ej. ``ProtocolError`` "Connection
    aborted") se considera posterior al envío.
    """
    return any(
        isinstance(
            e,
            urllib3.exceptions.NewConnectionError
            | urllib3.exceptions.ConnectTimeoutError
            | requests.exceptions.ConnectTimeout,
        )
        for e in _cadena(exc)
    )


def _desconexion_reutilizada(exc: BaseException) -> bool:
    """``True`` si parece el cierre de una conexión reutilizada (keep-alive) al enviar.

    Solo ``ProtocolError`` de urllib3, ``RemoteDisconnected`` o ``ConnectionResetError``; no
    una conexión rechazada ni un timeout de lectura.
    """
    if _fallo_antes_de_enviar(exc):
        return False
    return any(
        isinstance(
            e,
            urllib3.exceptions.ProtocolError
            | http.client.RemoteDisconnected
            | ConnectionResetError,
        )
        for e in _cadena(exc)
    )


# Errores locales de requests que ocurren antes de tocar la red (la petición no salió).
_ERRORES_LOCALES = (
    requests.exceptions.InvalidURL,
    requests.exceptions.InvalidSchema,
    requests.exceptions.MissingSchema,
    requests.exceptions.InvalidHeader,
    requests.exceptions.URLRequired,
    requests.exceptions.InvalidProxyURL,
)


def _netloc(host: str, puerto: int) -> str:
    """``host:puerto`` con corchetes para IPv6."""
    h = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    return f"[{h}]:{puerto}" if ":" in h else f"{h}:{puerto}"


class TransporteHttp:
    """Transporte sobre ``requests.Session`` propia (D-17, sin proxmoxer).

    Args:
        hosts: hosts en orden de prioridad (failover).
        puerto: puerto de la API.
        huellas: huella SHA-256 confiada por host. Un host sin huella no se contacta
            (RNF-07: nada se envía antes de resolver la huella), salvo con ``ignorar_ssl``.
        ignorar_ssl: acepta cualquier certificado (RF-06); no usa huella.
        sesion: sesión de ``requests`` a usar (por defecto una nueva).
    """

    def __init__(
        self,
        hosts: Sequence[str],
        puerto: int = 8006,
        *,
        huellas: Mapping[str, str] | None = None,
        ignorar_ssl: bool = False,
        sesion: requests.Session | None = None,
        timeout_conexion: float = TIMEOUT_CONEXION,
        timeout_lectura: float = TIMEOUT_LECTURA,
    ) -> None:
        self._hosts = list(hosts)
        self._puerto = int(puerto)
        self._huellas = dict(huellas or {})
        self._ignorar_ssl = ignorar_ssl
        self._timeout = (timeout_conexion, timeout_lectura)
        self._auth: Autenticador | None = None
        self._activo = 0
        self._sesion = sesion if sesion is not None else requests.Session()
        # D-18: conexión directa; sin proxy del entorno ni credenciales de ~/.netrc.
        self._sesion.trust_env = False
        # Falla en cerrado: lo que no tenga adaptador propio no puede salir.
        self._sesion.mount("https://", AdaptadorBloqueado())
        self._sesion.mount("http://", AdaptadorBloqueado())
        if ignorar_ssl:
            # El usuario eligió explícitamente no verificar: se silencia el aviso repetitivo.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        for host in self._hosts:
            huella = None if ignorar_ssl else self._huellas.get(host)
            if ignorar_ssl or huella:
                self._sesion.mount(
                    f"https://{_netloc(host, self._puerto)}/",
                    AdaptadorHuella(huella, pool_maxsize=POOL_MAXSIZE),
                )

    # --- Contrato de Transporte ---------------------------------------------------

    @property
    def host_activo(self) -> str:
        return self._hosts[self._activo] if self._hosts else ""

    def usar_autenticador(self, auth: Autenticador | None) -> None:
        self._auth = auth

    def cerrar(self) -> None:
        """Cierra la sesión HTTP subyacente."""
        self._sesion.close()

    def peticion(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, Any] | None = None,
        datos: dict[str, Any] | None = None,
    ) -> Any:
        metodo = metodo.upper()
        motivos: list[tuple[str, str]] = []
        n = len(self._hosts)
        for desplazamiento in range(n):
            indice = (self._activo + desplazamiento) % n
            host = self._hosts[indice]
            if not self._ignorar_ssl and host not in self._huellas:
                motivos.append((host, "huella_no_confiada"))
                continue
            try:
                try:
                    resp = self._enviar(host, metodo, ruta, params, datos)
                except requests.exceptions.ConnectionError as e:
                    if (
                        metodo not in _METODOS_SEGUROS
                        or isinstance(
                            e, requests.exceptions.SSLError | requests.exceptions.ConnectTimeout
                        )
                        or not _desconexion_reutilizada(e)
                    ):
                        raise
                    # Lectura: pveproxy cierra las conexiones inactivas (~5 s) y la reutilizada
                    # puede fallar al reusarla. Un único reintento en el mismo host es inocuo;
                    # no se reintenta una conexión rechazada ni un timeout.
                    resp = self._enviar(host, metodo, ruta, params, datos)
            except requests.exceptions.SSLError as e:
                if es_huella_distinta(e):
                    # Posible suplantación: nunca se prueba otro host por este camino.
                    raise ErrorProxLaunch(
                        CodigoError.HUELLA_CAMBIADA,
                        {"host": host, "puerto": str(self._puerto)},
                        limpiar_detalle(f"{type(e).__name__}: {e}"),
                    ) from None
                if metodo not in _METODOS_SEGUROS:
                    raise self._envio_incierto(host, "ssl", e) from None
                motivos.append((host, "ssl"))
                continue
            except requests.exceptions.ReadTimeout:
                if metodo in _METODOS_SEGUROS:
                    motivos.append((host, "timeout"))
                    continue
                # La petición ya llegó al servidor: reintentarla en otro host podría
                # duplicar la operación. Se informa sin probar otro host.
                raise ErrorProxLaunch(
                    CodigoError.SERVIDOR_NO_RESPONDE,
                    {"host": host, "motivos": f"{host}=timeout"},
                    f"ReadTimeout en {metodo} {ruta}",
                ) from None
            except requests.exceptions.Timeout:
                motivos.append((host, "timeout"))
                continue
            except requests.exceptions.ConnectionError as e:
                if metodo not in _METODOS_SEGUROS and not _fallo_antes_de_enviar(e):
                    # No hay certeza de que la petición no saliera (p. ej. conexión
                    # abortada tras enviar): no se reenvía a otro host (riesgo de duplicar).
                    raise ErrorProxLaunch(
                        CodigoError.SERVIDOR_NO_RESPONDE,
                        {"host": host, "motivos": f"{host}=conexion_abortada"},
                        limpiar_detalle(f"{type(e).__name__}: {e}"),
                    ) from None
                motivos.append((host, "conexion"))
                continue
            except requests.exceptions.RequestException as e:
                if metodo not in _METODOS_SEGUROS and not isinstance(e, _ERRORES_LOCALES):
                    # Fallo tras iniciar el envío (p. ej. cuerpo cortado o mal decodificado): el
                    # POST/DELETE pudo llegar, así que el resultado es incierto.
                    raise self._envio_incierto(host, "error", e) from None
                raise ErrorProxLaunch(
                    CodigoError.DESCONOCIDO,
                    {"host": host},
                    limpiar_detalle(f"{type(e).__name__}: {e}"),
                ) from None

            if resp.status_code in ESTADOS_NODO_CAIDO:
                if metodo not in _METODOS_SEGUROS:
                    # El POST pudo llegar al nodo: no se reenvía a otro host.
                    raise self._envio_incierto(host, str(resp.status_code), None)
                motivos.append((host, str(resp.status_code)))
                continue
            self._activo = indice
            return self._procesar(resp, metodo, ruta)
        raise self._error_agotado(motivos, ruta)

    # --- Internos -------------------------------------------------------------------

    def _enviar(
        self,
        host: str,
        metodo: str,
        ruta: str,
        params: dict[str, Any] | None,
        datos: dict[str, Any] | None,
    ) -> requests.Response:
        url = f"https://{_netloc(host, self._puerto)}{PREFIJO_API}{ruta}"
        if not isinstance(self._sesion.get_adapter(url), AdaptadorHuella):
            raise ErrorProxLaunch(
                CodigoError.DESCONOCIDO,
                {"host": host},
                "el destino no tiene el adaptador de huella esperado",
            )
        cabeceras: dict[str, str] = {}
        cookies: dict[str, str] = {}
        if self._auth is not None:
            self._auth.aplicar(metodo, cabeceras, cookies)
        cuerpo = {k: str(v) for k, v in datos.items()} if datos is not None else None
        consulta = {k: str(v) for k, v in params.items()} if params else None
        try:
            # verify=False siempre: la verificación real la hace la huella fija del
            # adaptador. Con verify=True requests impondría CERT_REQUIRED y
            # sobrescribiría el cert_reqs del adaptador.
            return self._sesion.request(
                metodo,
                url,
                params=consulta,
                data=cuerpo,  # requests lo codifica como x-www-form-urlencoded
                headers=cabeceras,
                cookies=cookies or None,
                timeout=self._timeout,
                verify=False,
                allow_redirects=False,
            )
        finally:
            # Nada de cookies persistentes en la sesión.
            self._sesion.cookies.clear()

    def _procesar(self, resp: requests.Response, metodo: str, ruta: str) -> Any:
        # Solo método, ruta y estado: nunca cabeceras ni cuerpos (pueden llevar secretos).
        _log.debug("%s %s -> %s (host %s)", metodo, ruta, resp.status_code, self.host_activo)
        if 200 <= resp.status_code < 300:
            try:
                cuerpo = resp.json()
            except ValueError:
                raise ErrorProxLaunch(
                    CodigoError.DESCONOCIDO,
                    {"estado_http": str(resp.status_code)},
                    "la respuesta no es JSON",
                ) from None
            return cuerpo.get("data") if isinstance(cuerpo, dict) else cuerpo
        raise traducir_http(
            resp.status_code,
            resp.reason or "",
            resp.text,
            nodo=nodo_de_ruta(ruta),
            sesion_ticket=isinstance(self._auth, AutenticadorTicket),
        )

    @staticmethod
    def _envio_incierto(host: str, motivo: str, exc: BaseException | None) -> ErrorProxLaunch:
        """Error de una petición no GET que pudo haber llegado al servidor (sin failover).

        Usa ``SERVIDOR_NO_RESPONDE`` con ``incierto="1"``; la creación lo traduce a
        ``CONEXION_PERDIDA``.
        """
        detalle = f"{type(exc).__name__}: {exc}" if exc is not None else f"HTTP {motivo}"
        return ErrorProxLaunch(
            CodigoError.SERVIDOR_NO_RESPONDE,
            {"host": host, "motivos": f"{host}={motivo}", "incierto": "1"},
            limpiar_detalle(detalle),
        )

    def _error_agotado(self, motivos: list[tuple[str, str]], ruta: str) -> ErrorProxLaunch:
        """Error final cuando ningún host pudo atender la petición (CA-07.4)."""
        resumen = ";".join(f"{h}={m}" for h, m in motivos)
        params = {
            "host": self._hosts[0] if self._hosts else "",
            "hosts": ",".join(self._hosts),
            "motivos": resumen,
        }
        codigos = {m for _, m in motivos}
        if codigos == {"huella_no_confiada"}:
            return ErrorProxLaunch(CodigoError.HUELLA_NO_CONFIADA, params, resumen)
        if codigos and codigos <= {str(e) for e in ESTADOS_NODO_CAIDO}:
            nodo = nodo_de_ruta(ruta)
            if nodo:
                params["nodo"] = nodo
            return ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, params, resumen)
        return ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, params, resumen)


def crear_transporte_http(perfil: PerfilConexion, huellas: Mapping[str, str]) -> Transporte:
    """Fábrica por defecto: ``TransporteHttp`` para un perfil y sus huellas confiadas."""
    return TransporteHttp(
        perfil.hosts, perfil.puerto, huellas=huellas, ignorar_ssl=perfil.ignorar_ssl
    )
