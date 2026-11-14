"""Planificación del lote: reserva de VMIDs (E/S) y construcción del plan (función pura).

``Planificador.planificar`` es el ÚNICO camino de planificación: lo usan la creación real y
la simulación (CA-L11.3). ``construir_plan`` no hace E/S y es determinista (RNF-L09).
"""

import copy
import secrets
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace

from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote import presupuesto
from proxlaunch.nucleo.lote.constantes import (
    ETIQUETA_APP,
    MAX_CONSULTAS_SIMULTANEAS,
    MAX_LOTE,
    MAX_SALTO_VMID,
    PREFIJO_ETIQUETA_LOTE,
    VMID_MAXIMO,
    VMID_MINIMO,
)
from proxlaunch.nucleo.lote.filas import filas_efectivas, validar_filas
from proxlaunch.nucleo.lote.filas import usa_nombre_de_plantilla as _usa_nombre_de_plantilla
from proxlaunch.nucleo.lote.modelos import (
    ClavePresupuesto,
    DefinicionLote,
    ElementoPlan,
    ModoDestino,
    Plan,
    Problema,
    Severidad,
    UsoStorage,
)
from proxlaunch.nucleo.lote.nombres import validar_patron
from proxlaunch.nucleo.lote.reparto import repartir_filas
from proxlaunch.nucleo.modelos.inventario import Inventario, VMRemota
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.resolucion import necesidades_catalogo, resolver_origen
from proxlaunch.nucleo.reloj import Reloj
from proxlaunch.nucleo.servicios.catalogo import ServicioCatalogo, con_catalogo
from proxlaunch.nucleo.servicios.conexion import Sesion, permisos_faltantes_detalle
from proxlaunch.nucleo.validacion import Problema as ProblemaM1
from proxlaunch.nucleo.validacion import Severidad as SeveridadM1
from proxlaunch.nucleo.validacion import validar_vm

# Reglas de M1 que el espacio acumulado del lote (V-L09/V-L10) ya cubre y supera.
_REGLAS_M1_SUBSUMIDAS = frozenset({"V-14", "V-14.thin"})
# Reglas que solo bloquean la creación real; la simulación sigue disponible (CA-L09.3, CA-L11.7).
REGLAS_SOLO_CREACION = frozenset({"V-L15", "V-L16"})


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _id_aleatorio() -> str:
    """Id de lote: 8 hexadecimales en minúsculas (CA-L20.3)."""
    return secrets.token_hex(4)


def usa_nombre_de_plantilla(definicion: DefinicionLote) -> bool:
    """N=1 con prefijo vacío: el nombre es el de la plantilla, igual que en M1 (CA-L04.1).

    Ese nombre se valida con V-01 de M1, no con V-L02/V-L04. Siempre falso en un lote por
    filas: cada fila trae su nombre.
    """
    return _usa_nombre_de_plantilla(definicion)


# --- Validación de la definición (pura, sin E/S) -----------------------------------


def validar_definicion(
    definicion: DefinicionLote, inv: Inventario, version_validacion: tuple[int, int]
) -> list[Problema]:
    """V-L01, V-L02..V-L04, V-L07, V-L13 y V-L15: lo que se decide sin consultar al servidor."""
    p: list[Problema] = []
    n = definicion.cantidad
    por_filas = definicion.es_por_filas
    if por_filas:
        # V-L01, V-M07, V-M10, V-02 y V-L13; el patrón se ignora (D-22).
        p.extend(validar_filas(definicion))
        n = len(definicion.filas)
        automaticas = sum(1 for f in definicion.filas if f.vmid is None)
    else:
        if not _es_entero(n) or not 1 <= n <= MAX_LOTE:
            p.append(Problema("V-L01", Severidad.ERROR, "cantidad", {"max": str(MAX_LOTE)}))
        if not usa_nombre_de_plantilla(definicion):
            p.extend(validar_patron(definicion.patron, n if _es_entero(n) else 0))
        automaticas = n if _es_entero(n) else 0

    inicio = definicion.vmid_inicial
    if inicio is not None and (not _es_entero(inicio) or not VMID_MINIMO <= inicio <= VMID_MAXIMO):
        p.append(
            Problema(
                "V-L07",
                Severidad.ERROR,
                "vmid_inicial",
                {"minimo": str(VMID_MINIMO), "maximo": str(VMID_MAXIMO)},
            )
        )
    elif _es_entero(n) and automaticas >= 1:
        primero = inicio if inicio is not None else inv.proximo_vmid
        if _es_entero(primero) and primero + automaticas - 1 > VMID_MAXIMO:
            p.append(
                Problema(
                    "V-L07",
                    Severidad.ERROR,
                    "vmid_inicial",
                    {"ultimo": str(primero + automaticas - 1), "maximo": str(VMID_MAXIMO)},
                )
            )

    destino = definicion.destino
    en_linea = {nd.nombre for nd in inv.topologia.nodos if nd.en_linea}
    if por_filas:
        pass  # V-L13 (destino siempre Automático) ya lo evaluó validar_filas
    elif destino.modo == ModoDestino.UN_NODO:
        if len(destino.nodos) != 1 or destino.nodos[0] not in en_linea:
            p.append(Problema("V-L13", Severidad.ERROR, "destino", {"modo": "un_nodo"}))
    elif destino.modo == ModoDestino.NODOS_ELEGIDOS and not any(
        nombre in en_linea for nombre in destino.nodos
    ):
        p.append(Problema("V-L13", Severidad.ERROR, "destino", {"modo": "nodos_elegidos"}))

    detectada = (inv.version.mayor, inv.version.menor)
    if version_validacion > detectada:
        p.append(
            Problema(
                "V-L15",
                Severidad.ERROR,
                "version",
                {
                    "forzada": f"{version_validacion[0]}.{version_validacion[1]}",
                    "detectada": f"{detectada[0]}.{detectada[1]}",
                    "codigo": CodigoError.VERSION_FORZADA_MAYOR.value,
                },
            )
        )
    return p


# --- Construcción del plan (pura) ---------------------------------------------------


def _etiquetas(base: Sequence[str], etiquetar: bool, id_lote: str) -> tuple[str, ...]:
    """Etiquetas de una MV: las propias de su configuración más las del lote si se etiqueta."""
    propias_cfg = tuple(base)
    if not etiquetar:
        return propias_cfg
    del_lote = (ETIQUETA_APP, f"{PREFIJO_ETIQUETA_LOTE}{id_lote}")
    return propias_cfg + tuple(e for e in del_lote if e not in propias_cfg)


def _agrupar_m1(problemas: Sequence[Problema]) -> list[Problema]:
    """Une los problemas de M1 iguales de varios elementos (primer índice + ``elementos``)."""
    cuenta: Counter[tuple[str, str | None, tuple[tuple[str, str], ...]]] = Counter()
    primeros: dict[tuple[str, str | None, tuple[tuple[str, str], ...]], Problema] = {}
    for pr in problemas:
        k = (pr.regla, pr.campo, tuple(sorted(pr.params.items())))
        cuenta[k] += 1
        primeros.setdefault(k, pr)
    resultado: list[Problema] = []
    for k, pr in primeros.items():
        if cuenta[k] > 1:
            pr = replace(pr, params={**pr.params, "elementos": str(cuenta[k])})
        resultado.append(pr)
    return resultado


def _problemas_memoria_y_cpu(elementos: Sequence[ElementoPlan], inv: Inventario) -> list[Problema]:
    """V-L12: aviso por nodo si lo pedido de memoria supera la libre; aviso de CPUs (CA-L09.2)."""
    p: list[Problema] = []
    por_nodo: dict[str, list[ElementoPlan]] = {}
    for e in elementos:
        por_nodo.setdefault(e.nodo, []).append(e)
    nodos = {n.nombre: n for n in inv.topologia.nodos}
    for nombre in sorted(por_nodo):
        nodo = nodos.get(nombre)
        if nodo is None:
            continue
        pedido = sum(e.cfg.memoria_mib for e in por_nodo[nombre])
        if nodo.mem_libre_mib is not None and pedido > nodo.mem_libre_mib:
            p.append(
                Problema(
                    "V-L12",
                    Severidad.AVISO,
                    "memoria_mib",
                    {
                        "nodo": nombre,
                        "pedido_mib": str(pedido),
                        "libre_mib": str(nodo.mem_libre_mib),
                    },
                )
            )
        vcpu = max(e.cfg.sockets * e.cfg.cores for e in por_nodo[nombre])
        if nodo.cpus is not None and vcpu > nodo.cpus:
            p.append(
                Problema(
                    "V-L12.cpu",
                    Severidad.AVISO,
                    "cores",
                    {"nodo": nombre, "vcpus": str(vcpu), "cpus_nodo": str(nodo.cpus)},
                )
            )
    return p


def _avisos_nombres_existentes(
    elementos: Sequence[ElementoPlan], visibles: Sequence[VMRemota]
) -> list[Problema]:
    """V-L06: un nombre del plan coincide con una MV visible (no bloquea, CA-L02.7)."""
    por_nombre: dict[str, VMRemota] = {}
    for vm in sorted(visibles, key=lambda v: v.vmid):
        por_nombre.setdefault(vm.nombre.lower(), vm)  # los nombres DNS no distinguen mayúsculas
    p: list[Problema] = []
    for e in elementos:
        existente = por_nombre.get(e.nombre.lower())
        if existente is not None:
            p.append(
                Problema(
                    "V-L06",
                    Severidad.AVISO,
                    "nombre",
                    {
                        "nombre": e.nombre,
                        "vmid": str(existente.vmid),
                        "nodo": existente.nodo,
                        "calificado": "1",  # puede haber otras que el usuario no ve (LAB-L11)
                    },
                    indice=e.indice,
                )
            )
    return p


def _problema_de_m1(pm: ProblemaM1, indice: int) -> Problema:
    """Convierte un problema de validación de formulario (M1 / V-O) en uno del lote."""
    sev = Severidad.ERROR if pm.severidad == SeveridadM1.ERROR else Severidad.AVISO
    return Problema(pm.codigo, sev, pm.campo, dict(pm.params), indice)


def construir_plan(
    definicion: DefinicionLote,
    inv: Inventario,
    vmids: Sequence[int],
    saltados: Sequence[int],
    *,
    id_lote: str,
    ahora: float,
    version_validacion: tuple[int, int],
    vms_visibles: Sequence[VMRemota] | None,
    problemas_extra: Sequence[Problema] = (),
) -> Plan:
    """Construye y valida el plan completo sin hacer E/S (pura y determinista).

    Aplica V-L01..V-L16 y ``validar_vm`` de M1 a cada elemento en su nodo. ``vmids`` debe
    traer uno por MV (``Planificador.reservar_vmids``); ``vms_visibles=None`` omite el
    aviso V-L06; ``problemas_extra`` añade los que dependen de E/S (V-L16). Con errores
    de definición, de destino o de capacidad el plan sale bloqueado y sin elementos.
    """

    def plan(
        elementos: Sequence[ElementoPlan],
        problemas: Sequence[Problema],
        reparto: dict[str, tuple[int, str]] | None = None,
        uso: dict[ClavePresupuesto, UsoStorage] | None = None,
        capacidad: int | None = None,
        excedentes: Sequence[int] = (),
    ) -> Plan:
        return Plan(
            id_lote=id_lote,
            definicion=definicion,
            elementos=tuple(elementos),
            vmids_saltados=tuple(saltados),
            reparto=dict(reparto or {}),
            uso=dict(uso or {}),
            problemas=tuple([*problemas, *problemas_extra]),
            capacidad_maxima=capacidad,
            generado_en=ahora,
            version_validacion=version_validacion,
            filas_excedentes=tuple(excedentes),
        )

    problemas = validar_definicion(definicion, inv, version_validacion)
    # V-L15 solo bloquea la creación real: no impide planificar para simular.
    if any(p.severidad == Severidad.ERROR and p.regla != "V-L15" for p in problemas):
        return plan([], problemas)

    filas = filas_efectivas(definicion)  # camino único: homogéneo y por filas (D-22)
    por_filas = definicion.es_por_filas
    n = len(filas)
    if len(vmids) != n:
        raise ValueError(f"se esperaban {n} VMIDs y llegaron {len(vmids)}")
    if len(set(vmids)) != len(vmids):  # defensa de INV-L1: nunca dos MVs con el mismo VMID
        raise ValueError("los VMIDs del plan deben ser únicos")
    nodos, reparto, p_reparto = repartir_filas(filas, definicion.destino, inv, por_filas=por_filas)
    problemas.extend(p_reparto)

    # Sin sitio para alguna MV o sin nodos (E-L01): plan bloqueado y sin elementos. Si fue por
    # espacio se calcula cuántas caben (CA-L07.7); por filas, qué filas no caben (CA-C08.6).
    if any(not nodo for nodo in nodos):
        por_espacio = any(
            p.regla == "E-L01" and p.params.get("motivo") == "sin_espacio" for p in p_reparto
        )
        sin_sitio = tuple(
            p.indice
            for p in p_reparto
            if por_filas
            and p.regla == "E-L01"
            and p.params.get("motivo") == "sin_espacio"
            and p.indice is not None
        )
        return plan(
            [],
            problemas,
            dict(reparto),
            presupuesto.uso_de_filas(filas, nodos, inv),
            presupuesto.capacidad_maxima(definicion, inv)
            if por_espacio and not por_filas
            else None,
            sin_sitio,
        )

    elementos: list[ElementoPlan] = []
    de_origen: list[Problema] = []
    hay_origen = False
    for i, fila in enumerate(filas):
        cfg = copy.deepcopy(fila.cfg)
        cfg.vmid, cfg.nombre, cfg.nodo = vmids[i], fila.nombre, nodos[i]
        cfg.etiquetas = _etiquetas(fila.cfg.etiquetas, definicion.etiquetar, id_lote)
        if cfg.origen != OrigenSO.DISCO_VACIO:
            # MVP 4 (§4.4): fuente, drivers, plantilla y modo del clon, resueltos en el nodo.
            hay_origen = True
            cfg, resueltos = resolver_origen(cfg, inv, nodos[i])
            de_origen.extend(_problema_de_m1(pm, i) for pm in resueltos)
        elementos.append(ElementoPlan(i, fila.nombre, vmids[i], nodos[i], cfg))

    nombres = [fila.nombre for fila in filas]
    if len(set(nombres)) != len(nombres):  # V-L05: imposible por construcción
        problemas.append(Problema("V-L05", Severidad.ERROR, "patron"))

    uso = presupuesto.uso_por_clave(elementos, inv)
    p_espacio = presupuesto.evaluar_espacio(uso, definicion.politica_thin)
    capacidad: int | None = None
    excedentes: tuple[int, ...] = ()
    if any(p.severidad == Severidad.ERROR for p in p_espacio):
        if por_filas:  # «Reducir a N» no aplica: se indica qué filas no caben
            excedentes = presupuesto.filas_que_exceden(elementos, inv, definicion.politica_thin)
        else:
            capacidad = presupuesto.capacidad_maxima(definicion, inv)
            p_espacio = [
                replace(p, params={**p.params, "n": str(n), "max": str(capacidad)})
                for p in p_espacio
            ]
    problemas.extend(p_espacio)

    if vms_visibles is not None:
        problemas.extend(_avisos_nombres_existentes(elementos, vms_visibles))
    problemas.extend(_problemas_memoria_y_cpu(elementos, inv))

    # M1 (V-01..V-24) en el nodo de CADA elemento, contra la tabla de capacidades efectiva.
    detectada = (inv.version.mayor, inv.version.menor)
    caps = Capacidades(version=version_validacion, forzada=version_validacion != detectada)
    de_m1: list[Problema] = []
    for e in elementos:
        for pm in validar_vm(e.cfg, inv, caps):
            if pm.codigo in _REGLAS_M1_SUBSUMIDAS:
                continue
            de_m1.append(_problema_de_m1(pm, e.indice))
    # Por filas cada problema conserva su fila (``indice``): no se agrupan.
    problemas.extend(de_m1 if por_filas else _agrupar_m1(de_m1))
    # Los problemas de resolución del origen llevan siempre su fila (V-O02, V-O03, V-O04...).
    problemas.extend(de_origen)

    resultado = plan(elementos, problemas, dict(reparto), uso, capacidad, excedentes)
    # El catálogo viaja con el plan solo si hubo orígenes: sin ellos el plan es el de M3.
    return replace(resultado, catalogo=inv.catalogo) if hay_origen else resultado


# --- Planificador (con E/S) ----------------------------------------------------------


class Planificador:
    """Reserva VMIDs y arma el plan consultando al servidor solo con lecturas (GET)."""

    def __init__(
        self,
        sesion: Sesion,
        reloj: Reloj,
        *,
        generador_id: Callable[[], str] | None = None,
    ) -> None:
        self._sesion = sesion
        self._reloj = reloj
        self._generador_id = generador_id or _id_aleatorio

    def reservar_vmids(
        self, inicio: int, cantidad: int, *, excluir: frozenset[int] = frozenset()
    ) -> tuple[list[int], list[int]]:
        """Confirma ``cantidad`` VMIDs libres desde ``inicio`` con ``GET /cluster/nextid?vmid=``.

        Devuelve ``(vmids, saltados)`` en orden: los saltados son los ocupados que quedaron
        por debajo del último VMID asignado. Consulta en tandas de hasta
        ``MAX_CONSULTAS_SIMULTANEAS`` y nunca más candidatos de los que aún faltan, así que
        hace como máximo ``cantidad + saltos`` consultas (CA-L03.7). La ventana es de
        ``MAX_SALTO_VMID`` números. Los VMIDs de ``excluir`` (los fijos de un lote por
        filas) no se consultan ni cuentan como saltados.

        Raises:
            ErrorProxLaunch: ``LOTE_VMIDS_INSUFICIENTES`` (E-L02) si la ventana no alcanza;
                cualquier error de red de la consulta aborta sin plan parcial; un VMID
                nunca se da por libre sin confirmarlo.
        """
        if cantidad < 1:
            return [], []
        ultimo = min(inicio + MAX_SALTO_VMID, VMID_MAXIMO + 1)
        candidatos = (v for v in range(inicio, ultimo) if v not in excluir)
        libres: list[int] = []
        saltados: list[int] = []
        pendientes: dict[Future[bool], int] = {}
        cliente = self._sesion.cliente
        with ThreadPoolExecutor(max_workers=MAX_CONSULTAS_SIMULTANEAS) as pool:
            try:
                while True:
                    # Ventana deslizante: solo se consulta un candidato si, aun siendo libres
                    # todos los que están en vuelo, todavía faltarían VMIDs (así el total de
                    # consultas es exactamente cantidad + saltos).
                    while (
                        len(libres) + len(pendientes) < cantidad
                        and len(pendientes) < MAX_CONSULTAS_SIMULTANEAS
                    ):
                        candidato = next(candidatos, None)
                        if candidato is None:
                            break
                        pendientes[pool.submit(cliente.vmid_libre, candidato)] = candidato
                    if not pendientes:
                        break
                    hechos, _ = wait(pendientes, return_when=FIRST_COMPLETED)
                    for futuro in hechos:
                        candidato = pendientes.pop(futuro)
                        # Un error de red aborta aquí: nunca se da un VMID por libre sin confirmar.
                        (libres if futuro.result() else saltados).append(candidato)
            except BaseException:
                for futuro in pendientes:
                    futuro.cancel()
                raise
        if len(libres) < cantidad:
            raise ErrorProxLaunch(
                CodigoError.LOTE_VMIDS_INSUFICIENTES,
                {"n": str(cantidad), "inicio": str(inicio)},
            )
        return sorted(libres), sorted(saltados)

    def comprobar_vmids(self, vmids: Sequence[int]) -> dict[int, bool]:
        """Comprueba con ``GET /cluster/nextid?vmid=`` cada VMID dado (solo lecturas).

        Devuelve ``{vmid: libre}`` (``True`` = libre en todo el clúster). Las consultas van
        en paralelo (``MAX_CONSULTAS_SIMULTANEAS``); un error de red aborta sin resultado
        parcial. No reasigna nada: decidir qué hacer con un VMID ocupado es del usuario.
        """
        unicos = sorted(set(vmids))
        if not unicos:
            return {}
        cliente = self._sesion.cliente
        with ThreadPoolExecutor(max_workers=MAX_CONSULTAS_SIMULTANEAS) as pool:
            futuros = {v: pool.submit(cliente.vmid_libre, v) for v in unicos}
            try:
                return {v: futuros[v].result() for v in unicos}
            except BaseException:
                for futuro in futuros.values():
                    futuro.cancel()
                raise

    def _vmids_por_filas(
        self, definicion: DefinicionLote, inv: Inventario
    ) -> tuple[list[int], list[int], list[Problema]]:
        """VMIDs de un lote por filas: los fijos se comprueban aparte y no se reasignan
        (V-03 por fila si están ocupados); los demás se reservan excluyendo los fijos."""
        filas = definicion.filas
        fijos = [f.vmid for f in filas if f.vmid is not None]
        libres = self.comprobar_vmids(fijos)
        problemas = [
            Problema("V-03", Severidad.ERROR, "vmid", {"vmid": str(f.vmid)}, indice=i)
            for i, f in enumerate(filas)
            if f.vmid is not None and not libres[f.vmid]
        ]
        inicio = (
            definicion.vmid_inicial if definicion.vmid_inicial is not None else inv.proximo_vmid
        )
        automaticos, saltados = self.reservar_vmids(
            inicio, len(filas) - len(fijos), excluir=frozenset(fijos)
        )
        siguiente = iter(automaticos)
        vmids = [f.vmid if f.vmid is not None else next(siguiente) for f in filas]
        return vmids, saltados, problemas

    def _con_catalogo_fresco(self, definicion: DefinicionLote, inv: Inventario) -> Inventario:
        """Lee el catálogo del servidor (solo GET) si hay filas con origen distinto de disco
        vacío; si no, devuelve ``inv`` intacto sin ninguna lectura nueva (CA-O03.1, INV-O8)."""
        necesidades = necesidades_catalogo(filas_efectivas(definicion))
        if necesidades.vacias:
            return inv
        catalogo = ServicioCatalogo(self._sesion, self._reloj).leer_para(
            inv, necesidades, self._nodos_del_catalogo(definicion, inv)
        )
        previo = inv.catalogo
        if catalogo.permisos is None and previo is not None and previo.permisos is not None:
            catalogo = replace(catalogo, permisos=previo.permisos)  # se reutiliza la respuesta
        return con_catalogo(inv, catalogo)

    @staticmethod
    def _nodos_del_catalogo(definicion: DefinicionLote, inv: Inventario) -> list[str]:
        """Nodos en línea donde puede caer una MV: los candidatos del destino y los fijos."""
        en_linea = {n.nombre for n in inv.topologia.nodos if n.en_linea}
        if definicion.es_por_filas or definicion.destino.modo == ModoDestino.AUTOMATICO:
            candidatos = set(en_linea)
        else:
            candidatos = en_linea & set(definicion.destino.nodos)
        candidatos |= {f.nodo for f in definicion.filas if f.nodo and f.nodo in en_linea}
        return sorted(candidatos)

    def planificar(
        self,
        definicion: DefinicionLote,
        inv: Inventario,
        *,
        version_forzada: tuple[int, int] | None = None,
    ) -> Plan:
        """Valida el lote, reserva VMIDs y devuelve el plan (V-L01..V-L16, RF-L01..RF-L09).

        Errores de la definición salen como plan bloqueado SIN consultar al servidor. Un
        fallo de red al reservar VMIDs lanza ``ErrorProxLaunch`` (sin plan parcial).
        """
        version_validacion = (
            version_forzada if version_forzada is not None else self._sesion.capacidades.version
        )
        id_lote = self._generador_id()
        ahora = self._reloj.ahora()
        bloqueo = validar_definicion(definicion, inv, version_validacion)
        if any(p.severidad == Severidad.ERROR and p.regla != "V-L15" for p in bloqueo):
            return construir_plan(
                definicion,
                inv,
                [],
                [],
                id_lote=id_lote,
                ahora=ahora,
                version_validacion=version_validacion,
                vms_visibles=None,
            )

        extra: list[Problema] = []
        if definicion.es_por_filas:
            vmids, saltados, ocupados = self._vmids_por_filas(definicion, inv)
            extra.extend(ocupados)
        else:
            inicio = (
                definicion.vmid_inicial if definicion.vmid_inicial is not None else inv.proximo_vmid
            )
            vmids, saltados = self.reservar_vmids(inicio, definicion.cantidad)

        try:
            visibles: list[VMRemota] | None = self._sesion.cliente.vms_visibles()
        except ErrorProxLaunch:
            visibles = None  # sin el aviso V-L06; no bloquea

        faltan = permisos_faltantes_detalle(self._sesion)  # None si no se pudo verificar
        for privilegio, ruta in faltan or []:
            if privilegio == "VM.Allocate":
                extra.append(
                    Problema(
                        "V-L16",
                        Severidad.ERROR,
                        None,
                        {"privilegio": privilegio, "ruta": ruta},
                    )
                )

        inv_trabajo = self._con_catalogo_fresco(definicion, inv)
        plan = construir_plan(
            definicion,
            inv_trabajo,
            vmids,
            saltados,
            id_lote=id_lote,
            ahora=self._reloj.ahora(),
            version_validacion=version_validacion,
            vms_visibles=visibles,
            problemas_extra=extra,
        )
        # Si no se pudieron leer los permisos no se bloquea, pero el plan queda marcado.
        return replace(plan, permisos_verificados=faltan is not None)
