"""Resumen de una máquina y del lote con las opciones de la fase B (0.7.0).

Derivadas de docs/requisitos/fase-b.md: RF-B0.1 (CA-B0.1.1, CA-B0.1.3), RF-B0.8 (la contraseña
nunca se muestra), CA-B1.9.8 (tabla «nombre → IP» del lote) y el plural «1 clave» / «N claves».
El centinela de contraseña es ``S3cr3t-Prueba!``.
"""

from __future__ import annotations

import pytest

from proxlaunch.interfaz.textos import (
    lineas_opciones_fase_b,
    opciones_avanzadas_fase_b,
    texto_claves_ssh,
)
from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.resumen_lote import (
    ResumenLote,
    texto_ips_del_plan,
    texto_opciones_del_plan,
)
from proxlaunch.nucleo.cloudinit.modelos import (
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.secreto import Secreto

from .apoyo_fase_b import CENTINELA, CLAVE_ED25519, CLAVE_RSA
from .apoyo_lote import cfg_simple, definicion, planificar
from .apoyo_mvp4 import cfg_base

FIJA = ModoTarjeta.FIJA


def ci_completa(**cambios) -> ConfigCloudInit:
    base = {
        "usuario": "deploy",
        "claves": (CLAVE_ED25519, CLAVE_RSA),
        "contrasena": Secreto(CENTINELA),
        "tarjetas": (
            TarjetaCloudInit(0, ModoTarjeta.DHCP),
            TarjetaCloudInit(1, FIJA, ip="192.168.10.5/24", puerta="192.168.10.1"),
        ),
        "dns": ("1.1.1.1", "8.8.8.8"),
        "dominio": "lab.local",
        "actualizar": False,
        "snippets": SnippetsCloudInit(vendor="local:snippets/agente.yaml", user="ninguno"),
    }
    base.update(cambios)
    return ConfigCloudInit(**base)


def cfg_b(**cambios) -> ConfiguracionVM:
    base = {"cloudinit": ci_completa(), "encender": True, "esperar_ip": True, "plazo_ip_s": 90}
    base.update(cambios)
    return cfg_base(**base)


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


def pintar(resumen: ResumenVM, cfg: ConfiguracionVM, *, avanzado: bool = True) -> str:
    resumen.actualizar(
        cfg, ["scsi0"], [], avanzado=avanzado, motivo_nodo="", bloqueo=None, ocupado=False
    )
    return resumen.texto_html


def texto_de_widgets(raiz) -> str:
    from PySide6.QtWidgets import QLabel

    return "\n".join(lbl.text() for lbl in raiz.findChildren(QLabel))


# --- CA-B0.1.1: cada opción aparece con su valor legible ---


def test_ca_b0_1_1_el_resumen_muestra_usuario_claves_red_dns_dominio_actualizar_y_scripts(resumen):
    html = pintar(resumen, cfg_b())
    for esperado in (
        "Usuario inicial:</b> deploy",
        "Claves SSH:</b> 2 claves: ssh-ed25519 (ana@portatil), ssh-rsa (bea@oficina)",
        "Red net0:</b> DHCP",
        "Red net1:</b> IP fija 192.168.10.5/24, puerta 192.168.10.1",
        "DNS:</b> 1.1.1.1, 8.8.8.8",
        "Dominio de búsqueda:</b> lab.local",
        "Actualizar paquetes al arrancar:</b> no",
        "local:snippets/agente.yaml",
        "ninguno",
        "Esperar la IP:</b> sí (plazo 90 s)",
    ):
        assert esperado in html, esperado


def test_ca_b0_1_1_la_contrasena_sale_como_definida_oculta_y_nunca_con_su_valor(resumen):
    html = pintar(resumen, cfg_b())
    assert "Contraseña inicial:</b> definida (oculta)" in html
    assert CENTINELA not in html
    assert CENTINELA not in resumen.texto_html
    assert CENTINELA not in texto_de_widgets(resumen)


def test_ca_b0_1_1_las_claves_salen_con_tipo_y_comentario_y_nunca_el_cuerpo(resumen):
    html = pintar(resumen, cfg_b())
    for cuerpo in ("AAAAC3NzaC1lZDI1NTE5", "AAAAB3NzaC1yc2E", "mqqnkVzrm0SzG0"):
        assert cuerpo not in html
        assert cuerpo not in texto_de_widgets(resumen)


def test_ca_b0_1_1_el_comentario_de_una_clave_se_escapa_en_el_resumen(resumen):
    clave = CLAVE_ED25519.rsplit(" ", 1)[0] + " <b>x</b>&co"
    html = pintar(resumen, cfg_b(cloudinit=ci_completa(claves=(clave,))))
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_ca_b0_1_1_en_modo_basico_dns_dominio_y_scripts_van_como_avanzadas_que_se_aplicaran(
    resumen,
):
    html = pintar(resumen, cfg_b(), avanzado=False)
    assert "Opciones avanzadas que se aplicarán" in html
    for esperado in ("DNS: 1.1.1.1, 8.8.8.8", "Dominio de búsqueda: lab.local"):
        assert esperado in html, esperado
    # Lo básico sigue en el cuerpo.
    assert "Usuario inicial:</b> deploy" in html
    assert "Esperar la IP:</b> sí (plazo 90 s)" in html
    assert CENTINELA not in html


def test_ca_b0_1_1_cada_tarjeta_sin_configurar_no_genera_linea(resumen):
    ci = ci_completa(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.SIN_CONFIGURAR),))
    html = pintar(resumen, cfg_b(cloudinit=ci))
    assert "Red net0" not in html


def test_ca_b0_1_1_una_ip_en_serie_lo_dice(resumen):
    ci = ci_completa(tarjetas=(TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True),))
    html = pintar(resumen, cfg_b(cloudinit=ci))
    assert "10.0.0.5/24" in html and "sumando 1 a cada máquina" in html


def test_ca_b0_1_1_el_agente_activado_por_cloudinit_sale_en_el_resumen(resumen):
    html = pintar(resumen, cfg_b(cloudinit=ci_completa(activar_agente=True)))
    assert "Activar el agente invitado:</b> sí" in html


def test_ca_b0_1_1_esperar_ip_sin_cloudinit_solo_añade_la_linea_de_la_espera(resumen):
    html = pintar(resumen, cfg_base(encender=True, esperar_ip=True, plazo_ip_s=45))
    assert "Esperar la IP:</b> sí (plazo 45 s)" in html
    for ausente in ("Usuario inicial", "Claves SSH", "Contraseña", "Red net", "DNS"):
        assert ausente not in html, ausente


# --- CA-B0.1.3: sin opciones de la fase B el Resumen no gana líneas ---


LINEAS_B = (
    "Usuario inicial",
    "Claves SSH",
    "Contraseña inicial",
    "Red net",
    "DNS",
    "Dominio de búsqueda",
    "Actualizar paquetes",
    "Script:",
    "Activar el agente",
    "Esperar la IP",
)


def test_ca_b0_1_3_sin_ninguna_opcion_de_la_fase_b_el_resumen_no_gana_ninguna_linea(resumen):
    html = pintar(resumen, cfg_base())
    for ausente in LINEAS_B:
        assert ausente not in html, ausente


def test_ca_b0_1_3_el_resumen_es_identico_con_cloudinit_none_y_con_cloudinit_vacia(resumen):
    sin = pintar(resumen, cfg_base())
    con_vacia = pintar(resumen, cfg_base(cloudinit=ConfigCloudInit()))
    assert sin == con_vacia


def test_ca_b0_1_3_con_esperar_ip_en_falso_el_plazo_no_se_muestra(resumen):
    html = pintar(resumen, cfg_base(esperar_ip=False, plazo_ip_s=300))
    assert "Esperar la IP" not in html


def test_ca_b0_1_3_las_funciones_de_texto_no_devuelven_lineas_sin_opciones():
    cfg = cfg_base()
    assert lineas_opciones_fase_b(cfg, avanzado=True) == []
    assert lineas_opciones_fase_b(cfg, avanzado=False) == []
    assert opciones_avanzadas_fase_b(cfg) == []


def test_ca_b0_1_3_el_resumen_del_lote_sin_opciones_de_la_fase_b_no_gana_lineas(qtbot):
    from .apoyo import inventario_cluster

    plan = planificar(inventario_cluster(), definicion(3, plantilla=cfg_simple(notas_origen=True)))
    texto = texto_opciones_del_plan(plan)
    for ausente in LINEAS_B:
        assert ausente not in texto, ausente
    assert texto_ips_del_plan(plan) == ""


# --- Plural «1 clave» / «N claves» ---


@pytest.mark.parametrize(
    ("claves", "empieza"),
    [
        ((CLAVE_ED25519,), "1 clave: ssh-ed25519 (ana@portatil)"),
        ((CLAVE_ED25519, CLAVE_RSA), "2 claves: ssh-ed25519 (ana@portatil), ssh-rsa (bea@oficina)"),
        ((CLAVE_ED25519,) * 5, "5 claves: "),
    ],
)
def test_el_plural_de_las_claves_es_1_clave_y_n_claves(claves, empieza):
    assert texto_claves_ssh(claves).startswith(empieza)
    if len(claves) == 1:
        assert "1 claves" not in texto_claves_ssh(claves)


def test_una_clave_sin_comentario_se_lista_solo_con_su_tipo():
    sin_comentario = CLAVE_ED25519.rsplit(" ", 1)[0]
    assert texto_claves_ssh((sin_comentario,)) == "1 clave: ssh-ed25519"


# --- Repr y volcados: la contraseña no aparece ---


def test_la_contrasena_no_aparece_en_el_repr_de_la_configuracion_ni_en_el_de_cloudinit():
    cfg = cfg_b()
    for texto in (repr(cfg), str(cfg), repr(cfg.cloudinit), str(cfg.cloudinit)):
        assert CENTINELA not in texto


def test_la_contrasena_no_cuenta_para_comparar_dos_configuraciones():
    assert ci_completa(contrasena=Secreto("a")) == ci_completa(contrasena=Secreto("b"))


def test_las_lineas_del_resumen_nunca_contienen_el_centinela():
    for avanzado in (True, False):
        texto = "\n".join(
            f"{k}: {v}" for k, v in lineas_opciones_fase_b(cfg_b(), avanzado=avanzado)
        )
        assert CENTINELA not in texto
    assert CENTINELA not in "\n".join(opciones_avanzadas_fase_b(cfg_b()))


# --- Resumen del lote ---


def plan_b(inv, ci: ConfigCloudInit | None, cantidad: int = 3, **cambios):
    cfg = cfg_simple(cloudinit=ci, **cambios)
    return planificar(inv, definicion(cantidad, plantilla=cfg))


def test_ca_b0_1_1_el_resumen_del_lote_lista_cloudinit_y_la_espera_sin_la_contrasena(inv_cluster):
    plan = plan_b(inv_cluster, ci_completa(), encender=True, esperar_ip=True, plazo_ip_s=90)
    texto = texto_opciones_del_plan(plan)
    for esperado in (
        "Usuario inicial: deploy",
        "Claves SSH: 2 claves",
        "Contraseña inicial (definida, oculta)",
        "DNS: 1.1.1.1, 8.8.8.8",
        "Esperar la IP: sí (plazo 90 s)",
    ):
        assert esperado in texto, esperado
    assert CENTINELA not in texto
    assert CENTINELA not in texto_ips_del_plan(plan)


def test_ca_b0_1_1_la_pantalla_del_lote_nunca_muestra_la_contrasena(qtbot, inv_cluster):
    plan = plan_b(
        inv_cluster,
        ci_completa(tarjetas=(TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True),)),
        encender=True,
        esperar_ip=True,
    )
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    r.mostrar_plan(plan)
    assert CENTINELA not in texto_de_widgets(r)
    assert "Contraseña inicial" in texto_de_widgets(r)


def test_ca_b0_1_1_una_espera_solo_en_algunas_maquinas_se_dice_con_cuantas(inv_cluster):
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.lote.modelos import FilaLote

    filas = []
    for i in range(3):
        cfg = cfg_simple(encender=True, esperar_ip=i == 0, plazo_ip_s=60)
        filas.append(FilaLote(f"web-{i + 1:02d}", cfg, None, "pve1", None))
    plan = planificar(inv_cluster, definicion_por_filas(filas, plantilla_base=cfg_simple()))
    assert "Esperar la IP: sí en 1 de 3 máquinas (plazo 60 s)" in texto_opciones_del_plan(plan)


# --- CA-B1.9.8: tabla «nombre → IP» y aviso de IP en uso ---


def test_ca_b1_9_8_el_resumen_del_lote_muestra_la_tabla_nombre_a_ip_calculada(inv_cluster):
    ci = ConfigCloudInit(
        tarjetas=(TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True, puerta="10.0.0.1"),)
    )
    plan = plan_b(inv_cluster, ci)
    texto = texto_ips_del_plan(plan)
    filas = texto.splitlines()
    assert "web-01  →  net0: 10.0.0.5/24" in filas
    assert "web-02  →  net0: 10.0.0.6/24" in filas
    assert "web-03  →  net0: 10.0.0.7/24" in filas
    assert "no puede comprobar si una IP ya está en uso" in filas[-1]


def test_ca_b1_9_8_la_tabla_incluye_todas_las_tarjetas_con_ip_fija_de_cada_maquina(inv_cluster):
    ci = ConfigCloudInit(
        tarjetas=(
            TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True),
            TarjetaCloudInit(1, FIJA, ip="172.16.0.10/24", serie=True),
        )
    )
    texto = texto_ips_del_plan(plan_b(inv_cluster, ci, cantidad=2))
    assert "web-01  →  net0: 10.0.0.5/24, net1: 172.16.0.10/24" in texto
    assert "web-02  →  net0: 10.0.0.6/24, net1: 172.16.0.11/24" in texto


def test_ca_b1_9_8_sin_ip_fija_no_hay_tabla_ni_aviso(inv_cluster):
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.DHCP),))
    assert texto_ips_del_plan(plan_b(inv_cluster, ci)) == ""
    assert texto_ips_del_plan(plan_b(inv_cluster, None)) == ""


def test_ca_b1_9_8_un_lote_de_una_maquina_muestra_la_ip_inicial_sin_sumar(inv_cluster):
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True),))
    texto = texto_ips_del_plan(plan_b(inv_cluster, ci, cantidad=1))
    assert "web-01  →  net0: 10.0.0.5/24" in texto
    assert "10.0.0.6" not in texto


def test_ca_b1_9_8_la_tabla_se_recorta_en_lotes_grandes_y_dice_cuantas_faltan(inv_cluster):
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True),))
    plan = plan_b(inv_cluster, ci, cantidad=50)
    texto = texto_ips_del_plan(plan, maximo=10)
    assert "… y 40 máquinas más" in texto
    assert texto.count("→") == 10
    assert "no puede comprobar si una IP ya está en uso" in texto  # el aviso nunca se recorta


def test_ca_b1_9_8_la_pantalla_del_lote_muestra_la_tabla_y_el_aviso(qtbot, inv_cluster):
    ci = ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, FIJA, ip="10.0.0.5/24", serie=True),))
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    r.mostrar_plan(plan_b(inv_cluster, ci))
    assert r._ips.isVisibleTo(r)
    assert "web-02  →  net0: 10.0.0.6/24" in r._ips.text()
    assert "no puede comprobar si una IP ya está en uso" in r._ips.text()


def test_ca_b1_9_8_sin_ip_fija_la_pantalla_del_lote_oculta_la_tabla(qtbot, inv_cluster):
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    r.mostrar_plan(plan_b(inv_cluster, None))
    assert not r._ips.isVisibleTo(r)
