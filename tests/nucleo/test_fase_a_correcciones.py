"""Correcciones tras las pruebas de la fase A: tamaño al guardar, V-A10 parcial y límite."""

from __future__ import annotations

import pytest

from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.constructor_peticion import formato_limite
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import DefinicionLote, Destino, FilaLote, PatronNombres
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.opciones.modelos import EstadoPools, PoolsServidor
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_fase_a import ROL_BASE, catalogo, cfg_vm, inv_con, permisos

CAPS = capacidades_para(Version("9.2.1", 9, 2, 1), None)
POOLS = PoolsServidor(EstadoPools.OK, ("produccion",))


def test_guardar_lote_de_mas_de_1_mib_se_rechaza_con_el_error_de_tamano(tmp_path):
    """Se rechaza al guardar con el mismo error que al leer y no se escribe nada."""
    filas = tuple(
        FilaLote(f"vm-{i:03d}", cfg_vm(notas="x" * 7500), None, None, i + 2, None)
        for i in range(100)
    )
    filas = filas + tuple(
        FilaLote(f"w-{i:03d}", cfg_vm(notas="x" * 7500), None, None, i + 102, None)
        for i in range(60)
    )
    definicion = DefinicionLote(cfg_vm(), len(filas), PatronNombres(""), Destino(), filas=filas)
    ruta = tmp_path / "enorme.json"
    with pytest.raises(ErrorProxLaunch) as exc:
        guardar_lote(ruta, LoteGuardado("enorme", definicion), app_version="0.6.0")
    assert exc.value.codigo == CodigoError.ARCHIVO_NO_PERMITIDO
    assert exc.value.params["motivo"] == "demasiado_grande"
    assert not ruta.exists()


def _va(cfg, cat):
    return [p for p in validar_vm(cfg, inv_con(cat), CAPS) if p.codigo.startswith("V-A")]


def test_va10_con_pool_audit_parcial_solo_avisa_con_va11():
    """Decisión §13: sin Pool.Audit en «/pool» la lista puede estar incompleta: V-A11, no V-A10."""
    cat = catalogo(perm=permisos(ROL_BASE, extra={"/pool/otro": {"Pool.Audit": 1}}), pools=POOLS)
    codigos = {p.codigo: p.severidad for p in _va(cfg_vm(pool="borrado"), cat)}
    assert "V-A10" not in codigos
    assert codigos["V-A11"] == Severidad.AVISO


@pytest.mark.parametrize(
    ("mb", "esperado"),
    [
        (100.0, "100"),
        (12.5, "12.5"),
        (0.00001, "0.00001"),
        (1e-07, "0.0000001"),
        (1e16, "1" + "0" * 16),
    ],
)
def test_formato_limite_usa_notacion_decimal_fija_sin_exponentes(mb, esperado):
    assert formato_limite(mb) == esperado
