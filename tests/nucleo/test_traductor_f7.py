"""Traductor (ronda F7): «already exists» de VM y de contenedor es VMID_OCUPADO."""

import pytest

from proxlaunch.nucleo.api.traductor_errores import traducir_http
from proxlaunch.nucleo.errores import CodigoError


@pytest.mark.parametrize("tipo", ["VM", "CT"])
def test_already_exists_en_la_frase_de_estado_es_vmid_ocupado(tipo):
    error = traducir_http(500, f"{tipo} 100 already exists on node 'pve1'", '{"data":null}')
    assert error.codigo == CodigoError.VMID_OCUPADO
    assert error.params["vmid"] == "100"
    assert error.params["nodo"] == "pve1"


@pytest.mark.parametrize("tipo", ["VM", "CT"])
def test_already_exists_en_el_cuerpo_400_es_vmid_ocupado(tipo):
    cuerpo = f'{{"errors":{{"vmid":"{tipo} 100 already exists"}}}}'
    error = traducir_http(400, "Parameter verification failed.", cuerpo)
    assert error.codigo == CodigoError.VMID_OCUPADO
    assert error.params == {"vmid": "100"}
