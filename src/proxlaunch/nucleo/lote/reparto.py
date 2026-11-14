"""Elegibilidad de nodos y reparto de las MVs del lote (RF-L05, RF-L06). Funciones puras.

Reglas de ``repartir`` (todas deterministas):

- ``UN_NODO``: todas las MVs al nodo indicado (si está en línea); sus carencias de storage o
  bridge las señala la validación de M1 por elemento (V-16/V-17, CA-L06.3).
- ``AUTOMATICO`` y ``NODOS_ELEGIDOS``: solo nodos elegibles (``nodos_elegibles``).
  * Equilibrado (CA-L05.2): entre los elegibles con espacio para la MV tras descontar lo
    ya asignado, el de mayor memoria libre restante; desempate por el mayor espacio libre
    INICIAL del storage más amplio de la plantilla (como ``elegir_nodo`` de M1) y por el
    nombre ascendente. Si ninguno tiene espacio, la MV va al mejor nodo igualmente y
    ``evaluar_espacio`` informa el exceso (V-L09/V-L10, CA-L07.1).
  * Por turnos (CA-L05.5): MV ``i`` al nodo ``i mod k`` en orden alfabético; el que no
    puede alojarla se salta; si ninguno puede, error E-L01. Un storage thin sin sitio no
    cuenta como «no puede» (RF-L08): el turno se respeta y el exceso lo informa V-L10.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace

from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    ClavePresupuesto,
    DefinicionLote,
    Destino,
    FilaLote,
    ModoDestino,
    MotivoReparto,
    Problema,
    Severidad,
)
from proxlaunch.nucleo.lote.presupuesto import libre_de_clave, libres_iniciales, pedido_vm
from proxlaunch.nucleo.modelos.inventario import Inventario, Nodo
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware
from proxlaunch.nucleo.validacion import TIPOS_BRIDGE, storage_efi_efectivo


def _nodos_candidatos(inv: Inventario, destino: Destino) -> list[str]:
    """Nombres a evaluar, sin repetidos y en orden alfabético."""
    if destino.modo == ModoDestino.AUTOMATICO:
        return sorted({n.nombre for n in inv.topologia.nodos})
    return sorted(set(destino.nodos))


def _motivos_nodo(plantilla: ConfiguracionVM, inv: Inventario, nombre: str) -> list[Problema]:
    """Motivos (V-L11) por los que el nodo no puede alojar la plantilla; vacío = elegible."""
    nodo: Nodo | None = next((n for n in inv.topologia.nodos if n.nombre == nombre), None)
    if nodo is None:
        return [
            Problema("V-L11", Severidad.ERROR, "destino", {"nodo": nombre, "motivo": "no_existe"})
        ]
    if not nodo.en_linea:
        return [
            Problema(
                "V-L11", Severidad.ERROR, "destino", {"nodo": nombre, "motivo": "sin_conexion"}
            )
        ]

    motivos: list[Problema] = []

    def falta(motivo: str, **params: str) -> None:
        motivos.append(
            Problema(
                "V-L11", Severidad.ERROR, "destino", {"nodo": nombre, "motivo": motivo, **params}
            )
        )

    cfg = replace(plantilla, nodo=nombre)
    storages = {s.id: s for s in inv.storages.get(nombre, ())}
    discos = cfg.discos if cfg.con_disco else []

    def apto(id_storage: str | None) -> bool:
        st = storages.get(id_storage) if id_storage is not None else None
        return st is not None and st.activo and "images" in st.contenido

    vistos: set[str] = set()
    for d in discos:
        if d.storage not in vistos and not apto(d.storage):
            vistos.add(d.storage)
            falta("storage", storage=str(d.storage))
    if cfg.firmware == Firmware.OVMF:
        id_efi = storage_efi_efectivo(cfg, inv, discos)
        if id_efi not in vistos and not apto(id_efi):
            falta("efidisk", storage=id_efi or "")
    bridges = {b.nombre for b in inv.bridges.get(nombre, ()) if b.tipo in TIPOS_BRIDGE}
    for r in cfg.redes:
        if r.bridge not in bridges:
            falta("bridge", bridge=str(r.bridge))
            bridges.add(r.bridge)  # un solo motivo por bridge
    return motivos


def nodos_elegibles(
    plantilla: ConfiguracionVM, inv: Inventario, destino: Destino
) -> tuple[list[str], dict[str, list[Problema]]]:
    """Nodos que pueden alojar la plantilla (RF-L06) y, para los demás, sus motivos.

    Un nodo es elegible si está en línea y tiene, activos y con ``images``, los storages de
    todos los discos (y del efidisk con OVMF) y los bridges de todas las redes. Se evalúan
    todos los nodos del servidor (Automático) o solo los de ``destino.nodos``. Los motivos
    son problemas ``V-L11`` con ``params`` ``nodo`` y ``motivo`` (``no_existe``,
    ``sin_conexion``, ``storage``, ``efidisk``, ``bridge``) más ``storage`` o ``bridge``.
    """
    elegibles: list[str] = []
    motivos: dict[str, list[Problema]] = {}
    for nombre in _nodos_candidatos(inv, destino):
        m = _motivos_nodo(plantilla, inv, nombre)
        if m:
            motivos[nombre] = m
        else:
            elegibles.append(nombre)
    return elegibles, motivos


def _motivo_reparto(destino: Destino, n_elegibles: int, memoria_desconocida: bool) -> MotivoReparto:
    if destino.modo == ModoDestino.UN_NODO:
        return MotivoReparto.ELEGIDO_POR_USUARIO
    if n_elegibles == 1:
        return MotivoReparto.UNICO_NODO
    if destino.algoritmo == Algoritmo.POR_TURNOS:
        return MotivoReparto.POR_TURNOS
    return MotivoReparto.MAS_ESPACIO if memoria_desconocida else MotivoReparto.MAS_MEMORIA


_Firma = tuple[object, ...]


def _firma(cfg: ConfiguracionVM) -> _Firma:
    """Lo que de una configuración decide la elegibilidad y el pedido de espacio de un nodo."""
    return (
        cfg.con_disco,
        tuple((d.storage, d.tamano_gib) for d in cfg.discos),
        cfg.firmware,
        cfg.storage_efi,
        tuple(r.bridge for r in cfg.redes),
    )


def repartir(
    definicion: DefinicionLote, inv: Inventario, cantidad: int
) -> tuple[list[str], dict[str, tuple[int, MotivoReparto]], list[Problema]]:
    """Asigna un nodo a cada una de ``cantidad`` MVs de la plantilla (lote homogéneo).

    Devuelve ``(nodo_por_indice, {nodo: (cuántas, motivo)}, problemas)``. Un índice sin
    nodo posible lleva ``""`` y hay un problema ERROR (E-L01). La memoria desconocida
    (``None``) cuenta como -1 y se avisa (V-L12.desconocida, CA-L05.6). Delega en
    ``repartir_filas`` con ``cantidad`` filas iguales.
    """
    filas = [FilaLote("", definicion.plantilla)] * max(cantidad, 0)
    return repartir_filas(filas, definicion.destino, inv)


def repartir_filas(
    filas: Sequence[FilaLote],
    destino: Destino,
    inv: Inventario,
    *,
    por_filas: bool = False,
) -> tuple[list[str], dict[str, tuple[int, MotivoReparto]], list[Problema]]:
    """Asigna un nodo a cada fila (docs/arquitectura/mvp3.md §4.4). Función pura.

    Devuelve ``(nodo_por_fila, {nodo: (cuántas, motivo)}, problemas)``; una fila sin nodo
    posible lleva ``""`` y hay un problema ERROR.

    1. Filas con ``nodo`` fijo (en orden): el nodo debe existir, estar en línea y ser elegible
       PARA ESA FILA; si no, V-L11 ERROR con su ``indice``. Si sí, se descuentan su pedido y
       su memoria del presupuesto vivo. Nunca se reasignan.
    2. Filas automáticas (en orden): candidatos = nodos elegibles para esa fila (se evalúa una
       vez por firma de recursos: en un lote homogéneo hay una sola, con el mismo coste y el
       mismo resultado que antes). Equilibrado y Por turnos con las reglas de ``repartir``,
       descontando el pedido y la memoria de la fila.

    Con ``por_filas`` el destino se trata como Automático y los problemas llevan ``indice``
    (E-L01 y V-L11 por fila). Sin él, el comportamiento es el del lote homogéneo: ``UN_NODO``
    lleva todo a su nodo y E-L01 es único (sin ``indice``, salvo el de «sin espacio»).
    """
    n = len(filas)
    problemas: list[Problema] = []
    nodos_inv = {nd.nombre: nd for nd in inv.topologia.nodos}

    if not por_filas and destino.modo == ModoDestino.UN_NODO:
        nombre = destino.nodos[0] if len(destino.nodos) == 1 else ""
        nodo = nodos_inv.get(nombre)
        if nodo is None or not nodo.en_linea:
            motivo = "no_existe" if nodo is None else "sin_conexion"
            problemas.append(
                Problema("E-L01", Severidad.ERROR, "destino", {"nodo": nombre, "motivo": motivo})
            )
            return [""] * n, {}, problemas
        reparto = {nombre: (n, MotivoReparto.ELEGIDO_POR_USUARIO)} if n else {}
        return [nombre] * n, reparto, problemas
    if n == 0:
        return [], {}, []

    destino_ef = Destino(ModoDestino.AUTOMATICO, (), destino.algoritmo) if por_filas else destino
    por_turnos = destino_ef.algoritmo == Algoritmo.POR_TURNOS
    nodos: list[str] = [""] * n
    fijas = [i for i, f in enumerate(filas) if f.nodo]
    automaticas = [i for i, f in enumerate(filas) if not f.nodo]

    # Elegibilidad y pedido, calculados una vez por firma (y nodo).
    cache_eleg: dict[_Firma, tuple[list[str], dict[str, list[Problema]]]] = {}
    cache_fijo: dict[tuple[_Firma, str], list[Problema]] = {}
    cache_pedido: dict[tuple[_Firma, str], dict[ClavePresupuesto, int]] = {}

    def elegibles_de(fila: FilaLote) -> tuple[list[str], dict[str, list[Problema]]]:
        f = _firma(fila.cfg)
        if f not in cache_eleg:
            cache_eleg[f] = nodos_elegibles(fila.cfg, inv, destino_ef)
        return cache_eleg[f]

    def pedido_de(fila: FilaLote, nodo: str) -> dict[ClavePresupuesto, int]:
        k = (_firma(fila.cfg), nodo)
        if k not in cache_pedido:
            cache_pedido[k] = pedido_vm(replace(fila.cfg, nodo=nodo), inv)
        return cache_pedido[k]

    # --- Filas con nodo fijo: validez ---
    fijas_validas: list[int] = []
    for i in fijas:
        fila = filas[i]
        nodo_fijo = str(fila.nodo)
        k = (_firma(fila.cfg), nodo_fijo)
        if k not in cache_fijo:
            cache_fijo[k] = _motivos_nodo(fila.cfg, inv, nodo_fijo)
        if cache_fijo[k]:
            problemas.extend(replace(m, indice=i) for m in cache_fijo[k])
        else:
            fijas_validas.append(i)
            nodos[i] = nodo_fijo

    # --- Filas automáticas: nodos elegibles y avisos de los no elegibles ---
    elegibles_unidos: set[str] = set()
    vistos: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    firmas_sin_nodo: set[_Firma] = set()
    primero_por_firma: dict[_Firma, int] = {}
    for i in automaticas:
        f = _firma(filas[i].cfg)
        if f in primero_por_firma:
            continue
        primero_por_firma[f] = i
        elegibles, motivos = elegibles_de(filas[i])
        elegibles_unidos.update(elegibles)
        hay_elegibles = bool(elegibles)
        if not hay_elegibles:
            firmas_sin_nodo.add(f)
        for nombre in sorted(motivos):
            for m in motivos[nombre]:
                # Aviso mientras quede algún nodo; si no queda ninguno, error (con E-L01).
                sev = Severidad.AVISO if hay_elegibles else Severidad.ERROR
                nuevo = replace(
                    m, severidad=sev, indice=primero_por_firma[f] if por_filas else None
                )
                clave_vista = (nuevo.regla, sev.value, tuple(sorted(nuevo.params.items())))
                if clave_vista in vistos:  # dos firmas pueden compartir el mismo motivo
                    continue
                vistos.add(clave_vista)
                problemas.append(nuevo)
        if not hay_elegibles and not por_filas:
            problemas.append(
                Problema(
                    "E-L01",
                    Severidad.ERROR,
                    "destino",
                    {"nodos": ",".join(sorted(motivos)), "motivo": "sin_nodo_elegible"},
                )
            )
            return [""] * n, {}, problemas
    if por_filas:
        for i in automaticas:
            if _firma(filas[i].cfg) in firmas_sin_nodo:
                _, motivos = elegibles_de(filas[i])
                problemas.append(
                    Problema(
                        "E-L01",
                        Severidad.ERROR,
                        "destino",
                        {"nodos": ",".join(sorted(motivos)), "motivo": "sin_nodo_elegible"},
                        indice=i,
                    )
                )

    # --- Presupuesto vivo por clave ---
    claves: set[ClavePresupuesto] = set()
    for i in automaticas:
        for nombre in elegibles_de(filas[i])[0]:
            claves.update(pedido_de(filas[i], nombre))
    for i in fijas_validas:
        claves.update(pedido_de(filas[i], nodos[i]))
    libre_inicial = libres_iniciales(inv, claves)
    restante: dict[ClavePresupuesto, int] = dict(libre_inicial)

    def tiene_sitio(ped: dict[ClavePresupuesto, int]) -> bool:
        return all(restante.get(k, 0) >= v for k, v in ped.items() if k in libre_inicial)

    def tiene_sitio_duro(ped: dict[ClavePresupuesto, int]) -> bool:
        """Solo cuentan los storages no thin: un thin se puede sobreasignar (RF-L08)."""
        return all(
            restante.get(k, 0) >= v
            for k, v in ped.items()
            if k in libre_inicial and not (libre_de_clave(inv, k) or (0, False))[1]
        )

    def espacio_inicial(ped: dict[ClavePresupuesto, int]) -> int:
        return max((libre_inicial[k] for k in ped if k in libre_inicial), default=0)

    def descontar(ped: dict[ClavePresupuesto, int]) -> None:
        for k, v in ped.items():
            if k in restante:
                restante[k] -= v

    asignado_mem: defaultdict[str, int] = defaultdict(int)
    for i in fijas_validas:  # 1.ª pasada: lo fijo se descuenta antes de repartir
        descontar(pedido_de(filas[i], nodos[i]))
        asignado_mem[nodos[i]] += filas[i].cfg.memoria_mib

    memoria = {nombre: nodos_inv[nombre].mem_libre_mib for nombre in elegibles_unidos}
    desconocida = any(m is None for m in memoria.values())
    if desconocida and not por_turnos:
        problemas.append(
            Problema(
                "V-L12.desconocida",
                Severidad.AVISO,
                None,
                {"nodos": ",".join(nm for nm in sorted(memoria) if memoria[nm] is None)},
            )
        )

    # --- 2.ª pasada: filas automáticas ---
    sin_sitio: list[int] = []
    turno = 0
    for i in automaticas:
        fila = filas[i]
        elegibles, _ = elegibles_de(fila)
        if not elegibles:
            continue  # ya tiene su E-L01
        elegido = ""
        if por_turnos:
            k_nodos = len(elegibles)
            for desplazamiento in range(k_nodos):
                candidato = elegibles[(turno + desplazamiento) % k_nodos]
                if tiene_sitio(pedido_de(fila, candidato)):
                    elegido = candidato
                    break
            else:
                # Sin sitio holgado: si solo falta en storages thin, el turno sigue (como en
                # Equilibrado) y evaluar_espacio pide la confirmación con tope (V-L10).
                for desplazamiento in range(k_nodos):
                    candidato = elegibles[(turno + desplazamiento) % k_nodos]
                    if tiene_sitio_duro(pedido_de(fila, candidato)):
                        elegido = candidato
                        break
        else:
            con_sitio = [nm for nm in elegibles if tiene_sitio(pedido_de(fila, nm))]

            def clave(nm: str, fila: FilaLote = fila) -> tuple[int, int, str]:
                libre = memoria[nm]
                mem = -1 if libre is None else libre - asignado_mem[nm]
                return (-mem, -espacio_inicial(pedido_de(fila, nm)), nm)

            # Sin sitio en ninguno: el mejor nodo igualmente; el exceso lo informa V-L09/V-L10.
            elegido = min(con_sitio or elegibles, key=clave)
        turno += 1
        if elegido:
            descontar(pedido_de(fila, elegido))
            asignado_mem[elegido] += fila.cfg.memoria_mib
            nodos[i] = elegido
        else:
            sin_sitio.append(i)

    if sin_sitio:
        if por_filas:
            problemas.extend(
                Problema(
                    "E-L01",
                    Severidad.ERROR,
                    "destino",
                    {"motivo": "sin_espacio", "elementos": "1"},
                    indice=i,
                )
                for i in sin_sitio
            )
        else:
            problemas.append(
                Problema(
                    "E-L01",
                    Severidad.ERROR,
                    "destino",
                    {"motivo": "sin_espacio", "elementos": str(len(sin_sitio))},
                    indice=sin_sitio[0],
                )
            )

    conteo: dict[str, int] = {}
    fijas_por_nodo: dict[str, int] = {}
    for i, nm in enumerate(nodos):
        if nm:
            conteo[nm] = conteo.get(nm, 0) + 1
            if filas[i].nodo:
                fijas_por_nodo[nm] = fijas_por_nodo.get(nm, 0) + 1
    motivo = _motivo_reparto(destino_ef, len(elegibles_unidos), desconocida)
    reparto = {
        nm: (
            conteo[nm],
            MotivoReparto.ELEGIDO_POR_USUARIO
            if fijas_por_nodo.get(nm, 0) == conteo[nm]
            else motivo,
        )
        for nm in sorted(conteo)
    }
    return nodos, reparto, problemas
