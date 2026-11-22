"""IP en serie para lotes (RF-B1.9, DT-B3): expansión por índice y reglas de lote V-B30, V-B31 y
V-B38. Puro.

``expandir_serie`` deja la IP final y ``serie=False``; el CIDR inicial queda en
``TarjetaCloudInit.serie_inicial`` (calculado) para que ``problemas_serie_lote`` pueda decir si
la serie desborda aunque ya esté expandida.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from ipaddress import IPv4Interface

from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit, ModoTarjeta, TarjetaCloudInit
from proxlaunch.nucleo.cloudinit.red import (
    ip_desplazada,
    ip_desplazada_sin_limite,
    motivo_cidr,
)
from proxlaunch.nucleo.lote.modelos import ElementoPlan, Problema, Severidad


def expandir_serie(ci: ConfigCloudInit, indice: int) -> ConfigCloudInit:
    """IP inicial + ``indice`` en cada tarjeta con ``serie``; devuelve ``serie=False``.

    Idempotente: una configuración ya expandida (sin ``serie``) no cambia. Si la suma sale de la
    red se deja la dirección resultante (la regla V-B30 la señalará); si ``ip`` no se puede
    analizar se conserva tal cual (V-B26 la señalará).
    """
    if not any(t.serie for t in ci.tarjetas):
        return ci
    tarjetas: list[TarjetaCloudInit] = []
    for t in ci.tarjetas:
        if t.serie and t.modo == ModoTarjeta.FIJA and t.ip:
            final = ip_desplazada_sin_limite(t.ip, indice)
            tarjetas.append(replace(t, ip=final or t.ip, serie=False, serie_inicial=t.ip))
        else:
            tarjetas.append(replace(t, serie=False))
    return replace(ci, tarjetas=tuple(tarjetas))


def _direccion(cidr: str) -> str:
    return cidr.partition("/")[0]


def _fijas(e: ElementoPlan) -> list[TarjetaCloudInit]:
    ci = e.cfg.cloudinit
    if ci is None:
        return []
    return [t for t in ci.tarjetas if t.modo == ModoTarjeta.FIJA and t.ip]


@dataclass
class _Serie:
    """Elementos afectados de una serie (tarjeta, CIDR inicial)."""

    primero: ElementoPlan
    direccion: str
    motivo: str
    afectadas: int = 1


def _misma_red(t: TarjetaCloudInit) -> bool:
    """¿La IP expandida sigue en la red de la inicial? (si no, la serie ha desbordado)."""
    assert t.serie_inicial is not None and t.ip is not None
    try:
        return IPv4Interface(t.ip).ip in IPv4Interface(t.serie_inicial).network
    except ValueError:
        return False


def _motivo_serie(t: TarjetaCloudInit, k: int) -> str | None:
    """Por qué la IP de la MV ``k`` de la serie no vale; ``None`` si vale."""
    assert t.serie_inicial is not None and t.ip is not None
    if ip_desplazada(t.serie_inicial, k) is None:
        # Fuera de los hosts útiles: desborda la red o cae en su dirección de red/difusión.
        return "red_o_difusion" if _misma_red(t) else "desborde"
    if t.puerta and _direccion(t.ip) == t.puerta:
        return "puerta"
    return None


def problemas_serie_lote(elementos: Sequence[ElementoPlan]) -> list[Problema]:
    """Reglas de lote sobre las IP de todos los elementos (ya expandidos).

    - **V-B30**: la serie sale de la red, pasa por la dirección de red o de difusión, o por la
      puerta de enlace. Un problema por serie, en la primera MV afectada.
    - **V-B38**: N > 1 con la misma IP fija en todas las MVs y sin serie.
    - **V-B31**: cualquier otra IP repetida entre MVs, filas o tarjetas del lote.
    """
    problemas: list[Problema] = []

    # V-B30: se agrupa por (tarjeta, CIDR inicial); la inicial inválida es asunto de V-B26/V-B27.
    series: dict[tuple[int, str], _Serie] = {}
    for e in elementos:
        for t in _fijas(e):
            if t.serie_inicial is None or motivo_cidr(t.serie_inicial) is not None:
                continue
            motivo = _motivo_serie(t, e.indice)
            if motivo is None:
                continue
            clave = (t.indice, t.serie_inicial)
            if clave in series:
                series[clave].afectadas += 1
            else:
                assert t.ip is not None
                series[clave] = _Serie(e, _direccion(t.ip), motivo)
    for (tarjeta, _inicial), s in series.items():
        problemas.append(
            Problema(
                "V-B30",
                Severidad.ERROR,
                f"cloudinit.tarjetas[{tarjeta}].ip",
                {
                    "tarjeta": str(tarjeta),
                    "motivo": s.motivo,
                    "direccion": s.direccion,
                    "nombre": s.primero.nombre,
                    "afectadas": str(s.afectadas),
                },
                s.primero.indice,
            )
        )

    # V-B38: la misma IP fija, sin serie, en todas las MVs de un lote de más de una.
    cubiertas: set[str] = set()
    if len(elementos) > 1:
        comunes: dict[int, set[str]] | None = None
        for e in elementos:
            propias = {
                t.indice: _direccion(t.ip or "") for t in _fijas(e) if t.serie_inicial is None
            }
            if comunes is None:
                comunes = {i: {d} for i, d in propias.items()}
            else:
                for i in list(comunes):
                    if i in propias:
                        comunes[i].add(propias[i])
                    else:
                        del comunes[i]
        for i, direcciones in sorted((comunes or {}).items()):
            if len(direcciones) == 1:
                cubiertas.update(direcciones)
                problemas.append(
                    Problema(
                        "V-B38",
                        Severidad.ERROR,
                        f"cloudinit.tarjetas[{i}].ip",
                        {"tarjeta": str(i), "cantidad": str(len(elementos))},
                    )
                )

    # V-B31: el resto de repeticiones.
    vistas: dict[str, ElementoPlan] = {}
    avisadas: set[str] = set()
    for e in elementos:
        for t in _fijas(e):
            assert t.ip is not None
            if motivo_cidr(t.ip) is not None:
                continue  # IP ilegible: la señala V-B26/V-B27, aquí sería ruido
            direccion = _direccion(t.ip)
            previo = vistas.get(direccion)
            if previo is None:
                vistas[direccion] = e
            elif direccion not in cubiertas and direccion not in avisadas:
                avisadas.add(direccion)
                problemas.append(
                    Problema(
                        "V-B31",
                        Severidad.ERROR,
                        f"cloudinit.tarjetas[{t.indice}].ip",
                        {
                            "direccion": direccion,
                            "tarjeta": str(t.indice),
                            "nombre": e.nombre,
                            "con": previo.nombre,
                        },
                        e.indice,
                    )
                )
    return problemas
