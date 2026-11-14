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

from dataclasses import replace

from proxlaunch.nucleo.lote.modelos import (
    Algoritmo,
    ClavePresupuesto,
    DefinicionLote,
    Destino,
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


def repartir(
    definicion: DefinicionLote, inv: Inventario, cantidad: int
) -> tuple[list[str], dict[str, tuple[int, MotivoReparto]], list[Problema]]:
    """Asigna un nodo a cada una de ``cantidad`` MVs.

    Devuelve ``(nodo_por_indice, {nodo: (cuántas, motivo)}, problemas)``. Un índice sin
    nodo posible lleva ``""`` y hay un problema ERROR (E-L01). La memoria desconocida
    (``None``) cuenta como -1 y se avisa (V-L12.desconocida, CA-L05.6).
    """
    plantilla, destino = definicion.plantilla, definicion.destino
    problemas: list[Problema] = []
    nodos_inv = {n.nombre: n for n in inv.topologia.nodos}

    if destino.modo == ModoDestino.UN_NODO:
        nombre = destino.nodos[0] if len(destino.nodos) == 1 else ""
        nodo = nodos_inv.get(nombre)
        if nodo is None or not nodo.en_linea:
            motivo = "no_existe" if nodo is None else "sin_conexion"
            problemas.append(
                Problema("E-L01", Severidad.ERROR, "destino", {"nodo": nombre, "motivo": motivo})
            )
            return [""] * cantidad, {}, problemas
        reparto = {nombre: (cantidad, MotivoReparto.ELEGIDO_POR_USUARIO)} if cantidad else {}
        return [nombre] * cantidad, reparto, problemas

    elegibles, motivos = nodos_elegibles(plantilla, inv, destino)
    hay_elegibles = bool(elegibles)
    for nombre in sorted(motivos):
        for m in motivos[nombre]:
            # Aviso mientras quede algún nodo; si no queda ninguno, error (con E-L01).
            sev = Severidad.AVISO if hay_elegibles else Severidad.ERROR
            problemas.append(replace(m, severidad=sev))
    if not hay_elegibles:
        problemas.append(
            Problema(
                "E-L01",
                Severidad.ERROR,
                "destino",
                {"nodos": ",".join(sorted(motivos)), "motivo": "sin_nodo_elegible"},
            )
        )
        return [""] * cantidad, {}, problemas

    # Presupuesto vivo por clave y petición de una MV en cada nodo elegible.
    pedido = {n: pedido_vm(replace(plantilla, nodo=n), inv) for n in elegibles}
    claves = {k for p in pedido.values() for k in p}
    libre_inicial = libres_iniciales(inv, claves)
    restante: dict[ClavePresupuesto, int] = dict(libre_inicial)

    def tiene_sitio(n: str) -> bool:
        return all(restante.get(k, 0) >= v for k, v in pedido[n].items() if k in libre_inicial)

    def tiene_sitio_duro(n: str) -> bool:
        """Solo cuentan los storages no thin: un thin se puede sobreasignar (RF-L08)."""
        return all(
            restante.get(k, 0) >= v
            for k, v in pedido[n].items()
            if k in libre_inicial and not (libre_de_clave(inv, k) or (0, False))[1]
        )

    def espacio_inicial(n: str) -> int:
        return max((libre_inicial[k] for k in pedido[n] if k in libre_inicial), default=0)

    def descontar(n: str) -> None:
        for k, v in pedido[n].items():
            if k in restante:
                restante[k] -= v

    asignado_mem: dict[str, int] = {n: 0 for n in elegibles}
    memoria = {n: nodos_inv[n].mem_libre_mib for n in elegibles}
    desconocida = any(m is None for m in memoria.values())
    por_turnos = destino.algoritmo == Algoritmo.POR_TURNOS

    if desconocida and not por_turnos:
        problemas.append(
            Problema(
                "V-L12.desconocida",
                Severidad.AVISO,
                None,
                {"nodos": ",".join(n for n in elegibles if memoria[n] is None)},
            )
        )

    nodos: list[str] = []
    sin_sitio = 0
    primero_sin_sitio: int | None = None
    for i in range(cantidad):
        elegido = ""
        if por_turnos:
            k = len(elegibles)
            for desplazamiento in range(k):
                candidato = elegibles[(i + desplazamiento) % k]
                if tiene_sitio(candidato):
                    elegido = candidato
                    break
            else:
                # Sin sitio holgado: si solo falta en storages thin, el turno sigue (como en
                # Equilibrado) y evaluar_espacio pide la confirmación con tope (V-L10).
                for desplazamiento in range(k):
                    candidato = elegibles[(i + desplazamiento) % k]
                    if tiene_sitio_duro(candidato):
                        elegido = candidato
                        break
        else:
            con_sitio = [n for n in elegibles if tiene_sitio(n)]

            def clave(n: str) -> tuple[int, int, str]:
                libre = memoria[n]
                mem = -1 if libre is None else libre - asignado_mem[n]
                return (-mem, -espacio_inicial(n), n)

            # Sin sitio en ninguno: el mejor nodo igualmente; el exceso lo informa V-L09/V-L10.
            elegido = min(con_sitio or elegibles, key=clave)
        if elegido:
            descontar(elegido)
            asignado_mem[elegido] += plantilla.memoria_mib
        else:
            sin_sitio += 1
            if primero_sin_sitio is None:
                primero_sin_sitio = i
        nodos.append(elegido)

    if primero_sin_sitio is not None:
        problemas.append(
            Problema(
                "E-L01",
                Severidad.ERROR,
                "destino",
                {"motivo": "sin_espacio", "elementos": str(sin_sitio)},
                indice=primero_sin_sitio,
            )
        )

    conteo: dict[str, int] = {}
    for n in nodos:
        if n:
            conteo[n] = conteo.get(n, 0) + 1
    motivo = _motivo_reparto(destino, len(elegibles), desconocida)
    reparto = {n: (conteo[n], motivo) for n in sorted(conteo)}
    return nodos, reparto, problemas
