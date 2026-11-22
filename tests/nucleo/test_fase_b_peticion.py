"""Fase B (0.7.0): construcción del ``PUT config`` de cloud-init (RF-B1.17, RF-B4.5, DT-B4).

Cubre CA-B1.3.1, CA-B1.3.2, CA-B1.4.1, CA-B1.6.1 y CA-B1.6.2 (parte del núcleo), CA-B1.7.1,
CA-B1.7.2, CA-B1.8.1, CA-B1.8.6, CA-B1.10.1, CA-B1.10.2, CA-B1.12.1 (parámetros simulados),
CA-B1.13.1, CA-B1.15.1, CA-B1.15.2, CA-B1.17.2, CA-B4.1.2, CA-B4.1.3, CA-B4.5.1 a CA-B4.5.4,
CL-B2 y CL-B12. La secuencia de llamadas contra el servidor (CA-B1.17.1, .3, .4, .5, .6 y .7) y la
contraseña por el transporte (CL-B9, CL-B10) están en ``test_fase_b_creacion.py`` y
``test_fase_b_secretos.py``.

La petición se compara siempre contra el texto que fija el requisito, no contra lo que devuelve
la implementación en otro caso.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    CicustomHeredado,
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.cloudinit.peticion import (
    ORDEN_CLAVES,
    PARAMETROS_CONTRASENA_SIMULADOS,
    construir_put_cloudinit,
    parametros_simulados,
    valor_cicustom,
)
from proxlaunch.nucleo.secreto import MASCARA, Secreto

CENTINELA = "S3cr3t-Prueba!"
CLAVE_1 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA= ana@pc"
CLAVE_2 = "ssh-rsa AAAAB3NzaC1yc2EAAAAAAAAAAA== bea@pc"
FIJA, DHCP, SIN = ModoTarjeta.FIJA, ModoTarjeta.DHCP, ModoTarjeta.SIN_CONFIGURAR

INFO = InfoCloudInitPlantilla(unidad=True, agente=False, tarjetas=(0, 1))


def snippets(**kw) -> SnippetsCloudInit:
    return SnippetsCloudInit(**kw)


def heredado(**tipos: str) -> CicustomHeredado:
    return CicustomHeredado(tipos=tipos, interpretable=True)


def info(**kw) -> InfoCloudInitPlantilla:
    return InfoCloudInitPlantilla(unidad=True, agente=False, tarjetas=(0, 1), **kw)


def put(ci: ConfigCloudInit, plantilla: InfoCloudInitPlantilla = INFO) -> dict[str, str]:
    return construir_put_cloudinit(ci, plantilla)


# --- Sin nada fijado no se envía nada ------------------------------------------------------------


def test_una_configuracion_vacia_no_genera_ninguna_peticion():
    assert put(ConfigCloudInit()) == {}


def test_solo_la_contrasena_no_entra_en_el_put_de_cloudinit():
    """La contraseña va en su ``PUT`` propio (CA-B1.6.1): este diccionario queda vacío."""
    assert put(ConfigCloudInit(contrasena=Secreto(CENTINELA))) == {}


def test_ca_b1_17_2_el_put_nunca_lleva_cipassword_ni_el_valor_de_la_contrasena():
    ci = ConfigCloudInit(
        usuario="deploy", claves=(CLAVE_1,), contrasena=Secreto(CENTINELA), dominio="lab.local"
    )
    cuerpo = put(ci)
    assert "cipassword" not in cuerpo
    assert CENTINELA not in "".join(f"{k}={v}" for k, v in cuerpo.items())


def test_ca_b1_6_2_sin_contrasena_tampoco_hay_cipassword():
    assert "cipassword" not in put(ConfigCloudInit(usuario="deploy"))
    assert "cipassword" not in put(ConfigCloudInit(contrasena=None, usuario="deploy"))


# --- CA-B1.3.1 / CA-B1.3.2: usuario --------------------------------------------------------------


def test_ca_b1_3_1_el_usuario_se_envia_como_ciuser():
    assert put(ConfigCloudInit(usuario="deploy")) == {"ciuser": "deploy"}


def test_ca_b1_3_2_usuario_vacio_no_se_envia():
    assert "ciuser" not in put(ConfigCloudInit(usuario="", dominio="x.local"))


# --- CA-B1.4.1: claves ---------------------------------------------------------------------------


def test_ca_b1_4_1_sshkeys_es_el_quote_de_las_claves_unidas_por_salto_de_linea():
    cuerpo = put(ConfigCloudInit(claves=(CLAVE_1, CLAVE_2)))
    assert cuerpo == {"sshkeys": quote(f"{CLAVE_1}\n{CLAVE_2}", safe="")}


def test_ca_b1_4_1_sin_claves_no_hay_sshkeys():
    assert "sshkeys" not in put(ConfigCloudInit(usuario="u"))


# --- CA-B1.7.1 / CA-B1.7.2 / CL-B2: tarjetas -----------------------------------------------------


def test_ca_b1_7_1_tarjeta_0_dhcp_y_tarjeta_1_fija_con_puerta():
    ci = ConfigCloudInit(
        tarjetas=(
            TarjetaCloudInit(0, DHCP),
            TarjetaCloudInit(1, FIJA, "192.168.10.5/24", puerta="192.168.10.1"),
        )
    )
    assert put(ci) == {
        "ipconfig0": "ip=dhcp",
        "ipconfig1": "ip=192.168.10.5/24,gw=192.168.10.1",
    }


def test_ca_b1_7_2_una_tarjeta_sin_configurar_no_emite_ipconfig():
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, SIN), TarjetaCloudInit(1, DHCP)))
    assert put(ci) == {"ipconfig1": "ip=dhcp"}


def test_cl_b2_con_varias_tarjetas_y_solo_la_primera_configurada_solo_sale_ipconfig0():
    ci = ConfigCloudInit(
        tarjetas=(
            TarjetaCloudInit(0, FIJA, "10.0.0.5/24"),
            TarjetaCloudInit(1, SIN),
            TarjetaCloudInit(2, SIN),
        )
    )
    assert put(ci) == {"ipconfig0": "ip=10.0.0.5/24"}


def test_ca_b1_8_3_con_dhcp_la_puerta_no_viaja():
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, DHCP, puerta="10.0.0.1"),))
    assert put(ci) == {"ipconfig0": "ip=dhcp"}


def test_ca_b1_7_1_el_indice_de_la_tarjeta_es_el_de_netn_y_se_ordena_numericamente():
    ci = ConfigCloudInit(
        tarjetas=(TarjetaCloudInit(10, DHCP), TarjetaCloudInit(2, DHCP), TarjetaCloudInit(31, DHCP))
    )
    assert list(put(ci)) == ["ipconfig2", "ipconfig10", "ipconfig31"]  # 2 antes que 10


# --- CA-B1.8.1 / CA-B1.8.6: DNS y dominio --------------------------------------------------------


def test_ca_b1_8_1_los_dns_se_envian_separados_por_espacio():
    assert put(ConfigCloudInit(dns=("8.8.8.8", "1.1.1.1"))) == {"nameserver": "8.8.8.8 1.1.1.1"}


def test_ca_b1_8_1_el_dominio_se_envia_como_searchdomain():
    assert put(ConfigCloudInit(dominio="lab.local")) == {"searchdomain": "lab.local"}


def test_ca_b1_8_6_dns_y_dominio_vacios_no_se_envian():
    cuerpo = put(ConfigCloudInit(usuario="u", dns=(), dominio=""))
    assert "nameserver" not in cuerpo and "searchdomain" not in cuerpo


# --- CA-B1.10.1 / CA-B1.10.2: ciupgrade ----------------------------------------------------------


def test_ca_b1_10_1_como_la_plantilla_no_envia_ciupgrade():
    assert "ciupgrade" not in put(ConfigCloudInit(usuario="u", actualizar=None))


@pytest.mark.parametrize(("valor", "esperado"), [(True, "1"), (False, "0")])
def test_ca_b1_10_2_si_y_no_envian_ciupgrade_1_y_0(valor, esperado):
    assert put(ConfigCloudInit(actualizar=valor)) == {"ciupgrade": esperado}


# --- CA-B1.13.1: lo heredado de la plantilla no se toca ------------------------------------------


def test_ca_b1_13_1_tarjeta_sin_configurar_con_ipconfig_heredado_no_envia_ipconfig_ni_delete():
    plantilla = info(heredados={"ipconfig0": "ip=dhcp", "ciuser": "ubuntu"})
    ci = ConfigCloudInit(usuario="deploy", tarjetas=(TarjetaCloudInit(0, SIN),))
    cuerpo = put(ci, plantilla)
    assert cuerpo == {"ciuser": "deploy"}
    assert "ipconfig0" not in cuerpo and "delete" not in cuerpo


def test_ca_b1_13_1_lo_heredado_no_se_reenvia_si_no_se_toco():
    plantilla = info(heredados={"ciuser": "ubuntu", "nameserver": "9.9.9.9", "ciupgrade": "0"})
    assert put(ConfigCloudInit(dominio="lab.local"), plantilla) == {"searchdomain": "lab.local"}


def test_ca_b1_13_1_nunca_se_envia_delete_salvo_para_cicustom():
    plantilla = info(
        heredados={"ipconfig0": "ip=dhcp"}, cicustom=heredado(user="local:snippets/a.yaml")
    )
    ci = ConfigCloudInit(
        usuario="u",
        claves=(CLAVE_1,),
        tarjetas=(TarjetaCloudInit(0, SIN),),
        dns=("1.1.1.1",),
        dominio="x.y",
        actualizar=True,
    )
    assert "delete" not in put(ci, plantilla)


# --- CA-B1.15.1 / CA-B1.15.2: agente -------------------------------------------------------------


def test_ca_b1_15_1_plantilla_sin_agente_y_casilla_marcada_envia_agent_1():
    assert put(ConfigCloudInit(activar_agente=True), info()) == {"agent": "1"}


def test_ca_b1_15_1_si_no_se_sabe_si_hay_agente_tambien_se_envia():
    desconocida = InfoCloudInitPlantilla(unidad=True, agente=None)
    assert put(ConfigCloudInit(activar_agente=True), desconocida) == {"agent": "1"}


def test_ca_b1_15_2_casilla_desmarcada_no_envia_agent():
    assert "agent" not in put(ConfigCloudInit(usuario="u", activar_agente=False), info())


def test_ca_b1_15_1_si_la_plantilla_ya_tiene_el_agente_no_se_reenvia():
    con_agente = InfoCloudInitPlantilla(unidad=True, agente=True)
    assert put(ConfigCloudInit(activar_agente=True), con_agente) == {}


# --- CA-B4.1.2 / CA-B4.1.3: cicustom sin heredado ------------------------------------------------


def test_ca_b4_1_2_user_y_vendor_se_envian_en_el_orden_fijo_de_proxmox():
    ci = ConfigCloudInit(
        snippets=snippets(vendor="local:snippets/v.yaml", user="local:snippets/u.yaml")
    )
    assert put(ci) == {"cicustom": "user=local:snippets/u.yaml,vendor=local:snippets/v.yaml"}


def test_ca_b4_1_2_los_cuatro_tipos_salen_en_el_orden_user_vendor_network_meta():
    ci = ConfigCloudInit(
        snippets=snippets(
            meta="a:snippets/m", network="a:snippets/n", vendor="a:snippets/v", user="a:snippets/u"
        )
    )
    assert put(ci)["cicustom"] == (
        "user=a:snippets/u,vendor=a:snippets/v,network=a:snippets/n,meta=a:snippets/m"
    )


def test_ca_b4_1_3_los_cuatro_como_la_plantilla_no_envian_cicustom_ni_delete():
    cuerpo = put(ConfigCloudInit(usuario="u", snippets=snippets()))
    assert "cicustom" not in cuerpo and "delete" not in cuerpo


def test_ca_b4_5_ninguno_sin_cicustom_heredado_no_envia_nada():
    """No hay nada que quitar: ni ``cicustom`` vacío ni ``delete``."""
    cuerpo = put(ConfigCloudInit(snippets=snippets(user=NINGUNO)))
    assert cuerpo == {}


# --- CA-B4.5.1 a CA-B4.5.4 / CL-B12: combinación con lo heredado ---------------------------------


def test_ca_b4_5_1_se_parte_de_lo_heredado_y_se_suma_el_tipo_elegido():
    plantilla = info(cicustom=heredado(user="local:snippets/a.yaml"))
    ci = ConfigCloudInit(snippets=snippets(vendor="local:snippets/v.yaml"))
    assert put(ci, plantilla) == {
        "cicustom": "user=local:snippets/a.yaml,vendor=local:snippets/v.yaml"
    }


def test_ca_b4_5_2_ninguno_que_deja_vacio_lo_heredado_envia_delete_y_no_cicustom():
    plantilla = info(cicustom=heredado(user="local:snippets/a.yaml"))
    cuerpo = put(ConfigCloudInit(snippets=snippets(user=NINGUNO)), plantilla)
    assert cuerpo == {"delete": "cicustom"}
    assert "cicustom" not in cuerpo


def test_ca_b4_5_3_como_la_plantilla_en_los_cuatro_no_envia_cicustom_ni_delete():
    plantilla = info(cicustom=heredado(user="local:snippets/a.yaml"))
    cuerpo = put(ConfigCloudInit(usuario="u", snippets=snippets()), plantilla)
    assert cuerpo == {"ciuser": "u"}


def test_ca_b4_5_4_un_cicustom_heredado_no_interpretable_solo_admite_como_la_plantilla():
    plantilla = info(cicustom=CicustomHeredado(tipos={}, interpretable=False))
    ci = ConfigCloudInit(usuario="u", snippets=snippets(vendor="local:snippets/v.yaml"))
    cuerpo = put(ci, plantilla)
    assert cuerpo == {"ciuser": "u"}  # no se pisa lo que no se sabe leer
    ci2 = ConfigCloudInit(snippets=snippets(user=NINGUNO))
    assert put(ci2, plantilla) == {}


def test_cl_b12_dos_tipos_heredados_y_se_cambia_uno_conserva_el_otro():
    plantilla = info(
        cicustom=heredado(user="local:snippets/a.yaml", vendor="local:snippets/v.yaml")
    )
    ci = ConfigCloudInit(snippets=snippets(vendor="local:snippets/v2.yaml"))
    assert put(ci, plantilla) == {
        "cicustom": "user=local:snippets/a.yaml,vendor=local:snippets/v2.yaml"
    }


def test_cl_b12_quitar_solo_uno_de_dos_conserva_el_otro_sin_delete():
    plantilla = info(
        cicustom=heredado(user="local:snippets/a.yaml", vendor="local:snippets/v.yaml")
    )
    cuerpo = put(ConfigCloudInit(snippets=snippets(user=NINGUNO)), plantilla)
    assert cuerpo == {"cicustom": "vendor=local:snippets/v.yaml"}


def test_ca_b4_5_el_orden_del_resultado_es_el_de_proxmox_aunque_el_heredado_venga_desordenado():
    valor, borrar = valor_cicustom(
        snippets(meta="a:snippets/m"),
        heredado(vendor="a:snippets/v", user="a:snippets/u"),
    )
    assert (valor, borrar) == ("user=a:snippets/u,vendor=a:snippets/v,meta=a:snippets/m", False)


@pytest.mark.parametrize(
    ("elegidos", "previo", "esperado"),
    [
        (snippets(), None, (None, False)),
        (snippets(), heredado(user="a:snippets/a"), (None, False)),
        (snippets(user=NINGUNO), None, (None, False)),
        (snippets(user=NINGUNO), CicustomHeredado({}, True), (None, False)),
        (snippets(user=NINGUNO), heredado(user="a:snippets/a"), (None, True)),
        (
            snippets(user=NINGUNO, vendor=NINGUNO),
            heredado(user="a:s/1", vendor="a:s/2"),
            (None, True),
        ),
        (
            snippets(user="a:snippets/n"),
            heredado(user="a:snippets/a"),
            ("user=a:snippets/n", False),
        ),
        (snippets(meta="a:snippets/m"), CicustomHeredado({}, False), (None, False)),
    ],
)
def test_ca_b4_5_valor_cicustom_cubre_la_tabla_de_combinaciones(elegidos, previo, esperado):
    assert valor_cicustom(elegidos, previo) == esperado


# --- Orden y forma del cuerpo --------------------------------------------------------------------


def test_el_orden_de_las_claves_es_el_de_orden_claves():
    ci = ConfigCloudInit(
        usuario="deploy",
        claves=(CLAVE_1,),
        tarjetas=(TarjetaCloudInit(1, DHCP), TarjetaCloudInit(0, FIJA, "10.0.0.5/24")),
        dns=("1.1.1.1",),
        dominio="lab.local",
        actualizar=True,
        snippets=snippets(user=NINGUNO, vendor="a:snippets/v"),
        activar_agente=True,
    )
    plantilla = info(cicustom=heredado(user="a:snippets/u"))
    cuerpo = put(ci, plantilla)
    claves = list(cuerpo)
    assert claves == sorted(claves, key=ORDEN_CLAVES.index)
    assert claves == [
        "ciuser",
        "sshkeys",
        "ipconfig0",
        "ipconfig1",
        "nameserver",
        "searchdomain",
        "ciupgrade",
        "cicustom",
        "agent",
    ]


def test_orden_claves_contiene_todas_las_que_puede_enviar_y_ninguna_de_contrasena():
    assert {"ciuser", "sshkeys", "nameserver", "searchdomain", "ciupgrade", "cicustom"} <= set(
        ORDEN_CLAVES
    )
    assert {"delete", "agent"} <= set(ORDEN_CLAVES)
    assert {f"ipconfig{i}" for i in range(32)} <= set(ORDEN_CLAVES)
    assert "cipassword" not in ORDEN_CLAVES
    assert len(set(ORDEN_CLAVES)) == len(ORDEN_CLAVES)


def test_delete_y_cicustom_nunca_van_juntos():
    plantilla = info(cicustom=heredado(user="a:snippets/a"))
    for elegidos in (snippets(user=NINGUNO), snippets(vendor="a:snippets/v"), snippets()):
        cuerpo = put(ConfigCloudInit(snippets=elegidos), plantilla)
        assert not ("delete" in cuerpo and "cicustom" in cuerpo)


def test_todos_los_valores_del_put_son_texto():
    ci = ConfigCloudInit(
        usuario="u", actualizar=False, tarjetas=(TarjetaCloudInit(0, DHCP),), activar_agente=True
    )
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in put(ci).items())


def test_la_funcion_es_pura_no_modifica_la_configuracion_ni_la_info():
    ci = ConfigCloudInit(usuario="u", claves=(CLAVE_1,), dns=("1.1.1.1",))
    plantilla = info(heredados={"ciuser": "x"})
    antes = (repr(ci), repr(plantilla))
    assert put(ci, plantilla) == put(ci, plantilla)
    assert (repr(ci), repr(plantilla)) == antes


# --- CA-B1.12.1 / RF-B0.1: parametros simulados --------------------------------------------------


def test_ca_b1_12_1_la_simulacion_lista_ipconfig_nameserver_y_el_numero_de_claves():
    ci = ConfigCloudInit(
        claves=(CLAVE_1, CLAVE_2),
        tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.51/24", puerta="10.0.0.1"),),
        dns=("8.8.8.8",),
    )
    simulados = parametros_simulados(put(ci), ci)
    assert simulados["ipconfig0"] == "ip=10.0.0.51/24,gw=10.0.0.1"
    assert simulados["nameserver"] == "8.8.8.8"
    assert simulados["sshkeys"] == "[2]"


def test_ca_b1_12_1_la_simulacion_nunca_lleva_el_cuerpo_de_las_claves():
    ci = ConfigCloudInit(claves=(CLAVE_1,))
    simulados = parametros_simulados(put(ci), ci)
    cuerpo_clave = CLAVE_1.split()[1]
    assert cuerpo_clave not in "".join(simulados.values())
    assert quote(cuerpo_clave, safe="") not in "".join(simulados.values())


def test_ca_b1_12_1_sin_claves_la_simulacion_no_inventa_sshkeys_y_no_toca_el_put():
    ci = ConfigCloudInit(usuario="u")
    cuerpo = put(ci)
    assert "sshkeys" not in parametros_simulados(cuerpo, ci)
    assert cuerpo == {"ciuser": "u"}  # el original no se modifica


def test_ca_b1_12_1_la_simulacion_no_modifica_el_put_original_que_si_lleva_las_claves():
    ci = ConfigCloudInit(claves=(CLAVE_1,))
    cuerpo = put(ci)
    parametros_simulados(cuerpo, ci)
    assert cuerpo["sshkeys"] == quote(CLAVE_1, safe="")


def test_ca_b0_8_1_la_simulacion_nunca_contiene_la_contrasena():
    ci = ConfigCloudInit(usuario="u", claves=(CLAVE_1,), contrasena=Secreto(CENTINELA))
    simulados = parametros_simulados(put(ci), ci)
    assert CENTINELA not in repr(simulados)
    assert "cipassword" not in simulados  # su parámetro propio lo pinta la simulación enmascarado


def test_ca_b0_8_1_los_parametros_simulados_de_la_contrasena_son_la_mascara():
    assert dict(PARAMETROS_CONTRASENA_SIMULADOS) == {"cipassword": MASCARA}
    assert CENTINELA not in repr(PARAMETROS_CONTRASENA_SIMULADOS)
    with pytest.raises(TypeError):
        PARAMETROS_CONTRASENA_SIMULADOS["cipassword"] = "otra"  # type: ignore[index]


def test_ca_b0_8_1_el_repr_de_la_configuracion_no_deja_ver_la_contrasena():
    ci = ConfigCloudInit(usuario="u", contrasena=Secreto(CENTINELA))
    assert CENTINELA not in repr(ci)
    assert CENTINELA not in str(ci)
