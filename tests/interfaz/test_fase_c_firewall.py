"""Firewall con grupo de seguridad (C3, fase C, 0.8.0) en la interfaz: sección del formulario,
Resumen, Resumen del lote, informe y detalle de la tabla (riesgo de un firewall a medias).

Derivadas de docs/requisitos/fase-c.md: RF-C3.1 (CA-C3.1.1, CA-C3.1.3, CA-C3.1.5), RF-C3.2
(CA-C3.2.3, CA-C3.2.5), RF-C3.4, RF-C3.8 (CA-C3.8.5), RF-C3.9 (P-C6), RF-C3.11 (CA-C3.11.1),
RF-C0.1 (CA-C0.1.1, CA-C0.1.3), RF-C0.3 (CA-C0.3.1, CA-C0.3.2), RF-C0.6 (CA-C0.6.2), CA-C12.1,
RNF-C6.2 y §9 de la arquitectura (aviso de tarjeta ilegible antes de crear).

Nunca hay red real ni diálogos modales.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz.modelos_tabla import detalle_entrada
from proxlaunch.interfaz.textos_c import (
    lineas_opciones_fase_c,
    texto_aviso_simulacion,
    texto_firewall_resumen,
    texto_grupos_ilegibles,
    texto_problema_c,
    texto_riesgo_firewall_parcial,
    texto_sin_grupos,
)
from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.resumen_lote import ResumenLote, texto_opciones_del_plan
from proxlaunch.interfaz.vistas.seccion_firewall import SeccionFirewall
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import (
    FirewallMV,
    GrupoSeguridad,
    LecturaGrupos,
    ModoDhcp,
    Politica,
    ReglaFirewall,
)
from proxlaunch.nucleo.lote.modelos import ElementoPlan, EntradaLibro, EstadoMV
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.opciones.disponibilidad_c import disponibilidad_fase_c
from proxlaunch.nucleo.opciones.modelos import OpcionC
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo import ClienteLoteFalso, inventario_cluster
from .apoyo_fase_b import textos_visibles
from .apoyo_lote import cfg_simple, informe_de, planificar
from .apoyo_mvp4 import cfg_base

WEB = GrupoSeguridad("web", "Servidores web")
DB = GrupoSeguridad("db")
CAPS_92 = Capacidades(version=(9, 2), forzada=False)


def fw(grupo: str | None = "web", **kw) -> FirewallMV:
    return FirewallMV(activo=True, grupo=grupo, **kw)


@pytest.fixture
def seccion(qtbot):
    s = SeccionFirewall()
    qtbot.addWidget(s)
    s.show()
    return s


@pytest.fixture
def activa(seccion):
    """Sección activada con dos grupos ya leídos."""
    seccion.chk_activar.setChecked(True)
    seccion.establecer_grupos(LecturaGrupos((WEB, DB)))
    return seccion


def elegir(s: SeccionFirewall, nombre: str | None) -> None:
    s.combo_grupo.setCurrentIndex(s.combo_grupo.findData(nombre))


def permisos(*quitar: str) -> PermisosEfectivos:
    privs = (*ROL_PROXLAUNCH, "VM.Config.Network", "Sys.Audit")
    return PermisosEfectivos(rutas={"/": {p: 1 for p in privs if p not in quitar}})


def estados(perm, caps=CAPS_92):
    return disponibilidad_fase_c(perm, caps)


# --- RF-C3.1: apagada por defecto -------------------------------------------------------------


def test_ca_c3_1_1_por_defecto_la_seccion_esta_apagada_y_no_pide_nada(qtbot, seccion):
    """CA-C3.1.1: ``firewall()`` es ``None`` (como 0.7.0), el cuerpo está plegado y no se pidió
    la lista de grupos."""
    pedidos = []
    seccion.pide_grupos.connect(lambda: pedidos.append(1))
    assert seccion.firewall() is None
    assert not seccion._cuerpo.isVisible()
    assert not seccion.chk_activar.isChecked()
    assert pedidos == []


def test_ca_c3_1_1_activar_muestra_el_cuerpo_y_pide_los_grupos_una_vez(qtbot, seccion):
    pedidos = []
    seccion.pide_grupos.connect(lambda: pedidos.append(1))
    seccion.chk_activar.setChecked(True)
    assert seccion._cuerpo.isVisible() and pedidos == [1]


def test_ca_c3_1_1_activar_y_desactivar_vuelve_a_none(activa):
    activa.chk_activar.setChecked(False)
    assert activa.firewall() is None


def test_ca_c3_1_1_los_valores_por_defecto_al_activar_son_los_de_proxmox_pedidos(activa):
    """Entrada Bloquear, salida Permitir, DHCP automático y sin casilla de aislamiento marcada."""
    f = activa.firewall()
    assert f == FirewallMV(
        activo=True,
        grupo=None,
        politica_entrada=Politica.BLOQUEAR,
        politica_salida=Politica.PERMITIR,
        dhcp=ModoDhcp.AUTO,
        acepto_aislada=False,
    )


# --- RF-C3.1 / RF-C3.2: grupos ----------------------------------------------------------------


def test_ca_c3_1_5_cada_entrada_muestra_el_nombre_y_su_comentario(activa):
    textos = [activa.combo_grupo.itemText(i) for i in range(activa.combo_grupo.count())]
    assert textos == ["Sin grupo", "web — Servidores web", "db"]


def test_ca_c3_2_1_elegir_un_grupo_de_la_lista_lo_pone_en_el_firewall(activa):
    elegir(activa, "web")
    assert activa.firewall().grupo == "web"


def test_ca_c3_2_1_volver_a_sin_grupo_quita_el_grupo(activa):
    elegir(activa, "web")
    elegir(activa, None)
    assert activa.firewall().grupo is None


@pytest.mark.parametrize("escrito", ["inventado", "web", "WEB", "web,db", "1web", ""])
def test_ca_c3_2_3_un_nombre_escrito_a_mano_nunca_cuenta_como_grupo(activa, escrito):
    """Conservador: solo vale lo elegido de la lista (evita reglas que no hacen nada)."""
    activa.combo_grupo.setEditText(escrito)
    assert activa.firewall().grupo is None


def test_ca_c3_2_3_con_la_lista_ilegible_el_control_queda_deshabilitado_con_el_motivo(activa):
    activa.establecer_grupos(
        LecturaGrupos(None, ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))
    )
    assert not activa.combo_grupo.isEnabled()
    assert texto_grupos_ilegibles() in textos_visibles(activa)
    assert activa.firewall().grupo is None


def test_ca_c3_2_3_con_la_lista_ilegible_el_resto_del_formulario_sigue_usable(activa):
    activa.establecer_grupos(LecturaGrupos(None, None))
    assert activa.combo_entrada.isEnabled() and activa.chk_activar.isEnabled()
    activa.combo_entrada.setCurrentIndex(activa.combo_entrada.findData(Politica.PERMITIR))
    assert activa.firewall().politica_entrada == Politica.PERMITIR


def test_ca_c3_2_3_una_lista_vacia_avisa_que_no_hay_grupos(activa):
    activa.establecer_grupos(LecturaGrupos(()))
    assert texto_sin_grupos() in textos_visibles(activa)
    assert [activa.combo_grupo.itemText(i) for i in range(activa.combo_grupo.count())] == [
        "Sin grupo"
    ]


def test_ca_c3_2_5_200_grupos_se_cargan_y_se_buscan_por_texto_sin_bloquear(activa):
    """CA-C3.2.5: búsqueda por «contiene» en el desplegable editable."""
    grupos = tuple(GrupoSeguridad(f"g{i:03d}", f"Grupo {i}") for i in range(200))
    t0 = time.perf_counter()
    activa.establecer_grupos(LecturaGrupos(grupos))
    assert time.perf_counter() - t0 < 2.0
    assert activa.combo_grupo.count() == 201
    completer = activa.combo_grupo.completer()
    completer.setCompletionPrefix("g15")
    assert completer.completionCount() == 10
    completer.setCompletionPrefix("GRUPO 77")  # sin distinguir mayúsculas y por el comentario
    assert completer.completionCount() == 1


def test_ca_c3_2_5_el_nombre_y_el_comentario_se_muestran_como_texto_plano(activa):
    """RNF-C6.2: el comentario del servidor nunca se interpreta como marcado."""
    activa.establecer_grupos(LecturaGrupos((GrupoSeguridad("web", "<b>negrita</b>"),)))
    assert "<b>" in activa.combo_grupo.itemText(1)  # tal cual, sin renderizar (QComboBox es texto)
    assert activa.firewall().grupo is None


def test_ca_c3_2_2_un_grupo_cargado_de_un_lote_que_ya_no_existe_se_muestra_y_no_se_cambia(seccion):
    """CA-C6.1.9 (interfaz): se ve «(no existe)» en vez de cambiarlo en silencio."""
    seccion.aplicar(fw("viejo"))
    seccion.establecer_grupos(LecturaGrupos((WEB, DB)))
    assert seccion.combo_grupo.currentText() == "viejo (no existe)"
    assert seccion.firewall().grupo == "viejo"  # lo valida V-C30 al «Comprobar»


def test_ca_c3_2_1_un_grupo_cargado_de_un_lote_que_existe_queda_elegido(seccion):
    seccion.aplicar(fw("db"))
    seccion.establecer_grupos(LecturaGrupos((WEB, DB)))
    assert seccion.firewall().grupo == "db"


# --- RF-C3.3 / RF-C3.4 / RF-C3.9 --------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [(Politica.PERMITIR, Politica.PERMITIR), (Politica.BLOQUEAR, Politica.BLOQUEAR)],
)
def test_ca_c3_3_1_las_politicas_elegidas_salen_en_el_firewall(activa, entrada, salida):
    activa.combo_entrada.setCurrentIndex(activa.combo_entrada.findData(entrada))
    activa.combo_salida.setCurrentIndex(activa.combo_salida.findData(salida))
    f = activa.firewall()
    assert (f.politica_entrada, f.politica_salida) == (entrada, salida)


def test_ca_c3_3_2_solo_hay_dos_politicas_bloquear_y_permitir_nunca_rechazar(activa):
    for combo in (activa.combo_entrada, activa.combo_salida):
        assert [combo.itemData(i) for i in range(combo.count())] == [
            Politica.BLOQUEAR,
            Politica.PERMITIR,
        ]
        assert "echaz" not in " ".join(combo.itemText(i) for i in range(combo.count()))


def test_ca_c3_4_1_con_dhcp_de_cloudinit_la_casilla_se_marca_sola_y_se_ve(activa):
    activa.establecer_hay_dhcp(True)
    assert activa.chk_dhcp.isChecked()
    assert activa._nota_dhcp.isVisible()
    assert activa.firewall().dhcp == ModoDhcp.AUTO


def test_ca_c3_4_3_sin_dhcp_de_cloudinit_la_casilla_esta_desmarcada(activa):
    activa.establecer_hay_dhcp(False)
    assert not activa.chk_dhcp.isChecked() and not activa._nota_dhcp.isVisible()
    assert activa.firewall().dhcp == ModoDhcp.AUTO


def test_ca_c3_4_2_el_usuario_puede_desmarcar_el_dhcp_y_eso_se_respeta(activa):
    activa.establecer_hay_dhcp(True)
    activa.chk_dhcp.click()
    assert not activa.chk_dhcp.isChecked()
    assert activa.firewall().dhcp == ModoDhcp.NO
    activa.establecer_hay_dhcp(False)  # cambiar cloud-init no revierte lo que el usuario decidió
    activa.establecer_hay_dhcp(True)
    assert activa.firewall().dhcp == ModoDhcp.NO


def test_ca_c3_4_1_el_usuario_puede_marcar_el_dhcp_sin_cloudinit(activa):
    activa.chk_dhcp.click()
    assert activa.firewall().dhcp == ModoDhcp.SI


def test_ca_c3_9_1_sin_grupo_y_con_entrada_bloquear_aparece_la_casilla_de_aislamiento(activa):
    assert activa.chk_aislada.isVisible() and not activa.chk_aislada.isChecked()
    assert activa.firewall().acepto_aislada is False


def test_ca_c3_9_1_marcar_la_casilla_se_refleja_en_el_firewall(activa):
    activa.chk_aislada.setChecked(True)
    assert activa.firewall().acepto_aislada is True


def test_ca_c3_9_4_con_la_entrada_permitir_no_hay_casilla_ni_se_arrastra_la_marca(activa):
    """P-C6: con Permitir no se exige; una marca previa no viaja si la casilla no se ve."""
    activa.chk_aislada.setChecked(True)
    activa.combo_entrada.setCurrentIndex(activa.combo_entrada.findData(Politica.PERMITIR))
    assert not activa.chk_aislada.isVisible()
    assert activa.firewall().acepto_aislada is False


def test_ca_c3_9_1_con_un_grupo_elegido_la_casilla_no_se_muestra_ni_se_arrastra(activa):
    activa.chk_aislada.setChecked(True)
    elegir(activa, "web")
    assert not activa.chk_aislada.isVisible()
    assert activa.firewall().acepto_aislada is False


def test_ca_c3_9_1_la_casilla_de_aislamiento_empieza_desmarcada_tras_aplicar_none(seccion):
    seccion.aplicar(fw(None, acepto_aislada=True))
    assert seccion.chk_aislada.isChecked()
    seccion.aplicar(None)
    assert not seccion.chk_aislada.isChecked() and seccion.firewall() is None


# --- RF-C0.3 / RF-C0.4: disponibilidad --------------------------------------------------------


def test_ca_c0_3_1_sin_vm_config_network_la_seccion_se_deshabilita_y_nombra_privilegio_y_ruta(
    seccion,
):
    """CA-C0.3.1 / CA-C3.1.3 / CA-C0.6.2: el motivo está visible sin pasar el ratón."""
    e = estados(permisos("VM.Config.Network"))
    seccion.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    assert not seccion.chk_activar.isEnabled()
    visible = textos_visibles(seccion)
    assert "VM.Config.Network" in visible and "/vms" in visible


def test_ca_c0_3_1_si_estaba_activada_vuelve_a_apagada_con_aviso(activa):
    e = estados(permisos("VM.Config.Network"))
    activa.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    assert activa.firewall() is None
    assert "restableci" in textos_visibles(activa).lower()


def test_ca_c0_3_2_con_permisos_desconocidos_la_seccion_queda_habilitada(seccion):
    e = estados(None)
    seccion.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    assert seccion.chk_activar.isEnabled()


def test_ca_c0_4_1_en_una_version_sin_grupos_la_seccion_se_deshabilita_con_la_version(seccion):
    e = estados(permisos(), Capacidades(version=(7, 4), forzada=True))
    seccion.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    assert not seccion.chk_activar.isEnabled()
    assert "8.0" in textos_visibles(seccion)


def test_ca_c0_3_1_con_el_privilegio_la_seccion_esta_habilitada_y_sin_motivo(seccion):
    e = estados(permisos())
    seccion.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    assert seccion.chk_activar.isEnabled()
    assert "VM.Config.Network" not in textos_visibles(seccion)


# --- RF-C3.11: ver reglas ---------------------------------------------------------------------


def test_ca_c3_11_1_con_sys_audit_ver_reglas_pide_las_del_grupo_elegido(activa):
    e = estados(permisos())
    activa.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    pedidas = []
    activa.pide_reglas.connect(pedidas.append)
    assert not activa.boton_reglas.isEnabled()  # sin grupo no hay qué ver
    elegir(activa, "web")
    assert activa.boton_reglas.isEnabled()
    activa.boton_reglas.click()
    assert pedidas == ["web"]


def test_ca_c3_11_1_las_reglas_recibidas_se_listan_como_texto_plano(activa):
    elegir(activa, "web")
    activa.establecer_reglas(
        "web",
        (ReglaFirewall("in", "ACCEPT", True, "SSH <script>"), ReglaFirewall("out", "DROP", False)),
        None,
    )
    visible = textos_visibles(activa)
    assert "ACCEPT" in visible and "DROP" in visible and "web" in visible
    assert activa.boton_reglas.isEnabled()


def test_ca_c3_11_1_sin_sys_audit_ver_reglas_esta_deshabilitado_con_el_motivo(activa):
    e = estados(permisos("Sys.Audit"))
    activa.establecer_disponibilidad(e[OpcionC.FIREWALL], e[OpcionC.FIREWALL_GENERAL])
    elegir(activa, "web")
    assert not activa.boton_reglas.isEnabled()
    assert activa.boton_reglas.toolTip()
    assert "Sys.Audit" in textos_visibles(activa) or "Sys.Audit" in activa.boton_reglas.toolTip()


def test_ca_c3_11_1_el_resultado_de_otro_grupo_se_descarta(activa):
    elegir(activa, "web")
    activa.establecer_reglas("db", (ReglaFirewall("in", "ACCEPT", True),), None)
    assert not activa._reglas.isVisible()


def test_ca_c3_11_1_un_error_al_leer_las_reglas_muestra_un_texto_y_reactiva_el_boton(activa):
    elegir(activa, "web")
    activa.boton_reglas.click()
    assert not activa.boton_reglas.isEnabled()
    activa.establecer_reglas("web", None, ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))
    assert activa._reglas.isVisible() and activa._reglas.text()
    assert activa.boton_reglas.isEnabled()


# --- Problemas junto a la sección -------------------------------------------------------------


def _problema(codigo, severidad=Severidad.ERROR, campo="firewall", **params):
    return Problema(campo, codigo, severidad, dict(params))


def test_ca_c12_1_los_errores_y_avisos_de_firewall_salen_junto_a_la_seccion(activa):
    activa.mostrar_problemas(
        [
            _problema("V-C36"),
            _problema("V-C33", Severidad.AVISO),
            _problema("V-C38", Severidad.AVISO, "firewall.grupo", grupo="web"),
            _problema("V-C20", Severidad.AVISO, "redes", tarjeta="1"),  # ajeno: no se muestra aquí
        ]
    )
    visible = textos_visibles(activa)
    assert "no aceptaría ninguna conexión" in visible
    assert "firewall general" in visible
    assert "«web»" in visible  # V-C38 nombra el grupo


def test_ca_c12_1_sin_problemas_no_queda_ningun_mensaje(activa):
    activa.mostrar_problemas([_problema("V-C36")])
    activa.mostrar_problemas([])
    assert "no aceptaría" not in textos_visibles(activa)


# --- CA-C12.1 / CA-C0.6.1: mensajes de V-C30..V-C40, V-C50, V-C52 -----------------------------

MENSAJES = [
    ("V-C30", Severidad.ERROR, {"grupo": "inventado"}, ["inventado", "no existe"]),
    ("V-C31", Severidad.ERROR, {}, ["letra", "18"]),
    ("V-C32", Severidad.ERROR, {}, ["grupos de seguridad"]),
    ("V-C33", Severidad.AVISO, {}, ["apagado", "no lo enciende"]),
    ("V-C34", Severidad.AVISO, {}, ["Sys.Audit"]),
    ("V-C35", Severidad.AVISO, {"plantilla": "base", "motivo": "heredado"}, ["plantilla"]),
    ("V-C35", Severidad.AVISO, {"plantilla": "base", "motivo": "no_comprobable"}, ["plantilla"]),
    (
        "V-C35",
        Severidad.AVISO,
        {"plantilla": "base", "motivo": "tarjeta_ilegible", "tarjeta": "net1"},
        ["net1"],
    ),
    ("V-C36", Severidad.ERROR, {}, ["no aceptaría", "grupo"]),
    ("V-C37", Severidad.AVISO, {}, ["DHCP"]),
    ("V-C38", Severidad.AVISO, {"grupo": "web"}, ["web", "consola"]),
    (
        "V-C40",
        Severidad.ERROR,
        {"privilegio": "VM.Config.Network", "ruta": "/vms"},
        ["VM.Config.Network", "/vms"],
    ),
    ("V-C50", Severidad.ERROR, {"version": "8.0"}, ["8.0"]),
    ("V-C52", Severidad.ERROR, {}, ["firewall"]),
]


@pytest.mark.parametrize(("codigo", "severidad", "params", "contiene"), MENSAJES)
def test_ca_c12_1_cada_regla_de_firewall_tiene_mensaje_con_causa_y_sin_marcadores_sin_rellenar(
    codigo, severidad, params, contiene
):
    texto = texto_problema_c(Problema("firewall", codigo, severidad, params))
    assert texto, codigo
    for esperado in contiene:
        assert esperado in texto, (codigo, esperado, texto)
    assert "{" not in texto and "}" not in texto


def test_ca_c12_1_los_mensajes_no_incluyen_valores_inesperados_del_servidor():
    """RNF-C6.2: solo se interpolan los params previstos; nada más."""
    p = Problema(
        "firewall.grupo",
        "V-C30",
        Severidad.ERROR,
        {"grupo": "web", "nota": "NOTA-PRIVADA", "comentario": "SECRETO"},
    )
    texto = texto_problema_c(p)
    assert "NOTA-PRIVADA" not in texto and "SECRETO" not in texto


def test_ca_c12_1_los_errores_de_firewall_de_un_paso_nombran_la_mv_y_el_grupo():
    from proxlaunch.interfaz.textos import texto_error

    e = ErrorProxLaunch(
        CodigoError.FIREWALL_GRUPO_INEXISTENTE,
        {"nombre": "web-01", "grupo": "web", "ajuste": "firewall_regla"},
    )
    texto = texto_error(e)
    assert "web" in texto


# --- RF-C0.1: Resumen -------------------------------------------------------------------------


@pytest.fixture
def resumen(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    return r


def pintar(resumen, cfg, problemas=()):
    resumen.actualizar(
        cfg, ["scsi0"], list(problemas), avanzado=True, motivo_nodo="", bloqueo=None, ocupado=False
    )
    return resumen.texto_html


def test_ca_c0_1_1_el_resumen_muestra_el_firewall_con_grupo_politicas_y_dhcp(resumen):
    html = pintar(resumen, cfg_base(firewall=fw("web", dhcp=ModoDhcp.SI)))
    assert "Firewall:</b> activado, grupo web, entrada Bloquear, salida Permitir, DHCP sí" in html


@pytest.mark.parametrize(
    ("dhcp", "texto"),
    [(ModoDhcp.AUTO, "DHCP automático"), (ModoDhcp.SI, "DHCP sí"), (ModoDhcp.NO, "DHCP no")],
)
def test_ca_c0_1_1_el_resumen_dice_el_modo_dhcp(resumen, dhcp, texto):
    assert texto in pintar(resumen, cfg_base(firewall=fw(dhcp=dhcp)))


def test_ca_c0_1_1_sin_grupo_el_resumen_lo_dice_y_recuerda_el_aislamiento_aceptado(resumen):
    html = pintar(resumen, cfg_base(firewall=fw(None, acepto_aislada=True)))
    assert "sin grupo" in html
    assert "Aislamiento:</b> aceptado" in html


def test_ca_c0_1_1_con_politicas_cambiadas_el_resumen_las_refleja(resumen):
    html = pintar(
        resumen,
        cfg_base(
            firewall=fw(politica_entrada=Politica.PERMITIR, politica_salida=Politica.BLOQUEAR)
        ),
    )
    assert "entrada Permitir, salida Bloquear" in html


@pytest.mark.parametrize("firewall", [None, FirewallMV(), FirewallMV(activo=False)])
def test_ca_c0_1_3_sin_firewall_el_resumen_no_gana_ninguna_linea(resumen, firewall):
    base = pintar(resumen, cfg_base())
    assert pintar(resumen, cfg_base(firewall=firewall)) == base
    assert "Firewall" not in base and "Aislamiento" not in base
    assert lineas_opciones_fase_c(cfg_base(firewall=firewall)) == []


def test_ca_c0_1_1_la_tarjeta_ilegible_matiza_el_activado_antes_de_crear(resumen):
    """§9: nunca se dice «activado» a secas si hay tarjetas que quedarán sin firewall."""
    p = _problema(
        "V-C35", Severidad.AVISO, plantilla="base", motivo="tarjeta_ilegible", tarjeta="net1"
    )
    html = pintar(resumen, cfg_base(firewall=fw()), [p])
    assert "activado salvo en net1" in html
    assert "activado," not in html


def test_ca_c0_1_1_los_avisos_de_firewall_salen_en_el_resumen(resumen):
    pintar(resumen, cfg_base(firewall=fw()), [_problema("V-C33", Severidad.AVISO)])
    assert "firewall general" in resumen.texto_pendientes or "firewall general" in "\n".join(
        lbl.text() for lbl in resumen.findChildren(QLabel)
    )


def test_ca_c0_1_1_un_error_de_firewall_bloquea_y_se_explica_en_el_resumen(resumen):
    pintar(resumen, cfg_base(firewall=fw(None)), [_problema("V-C36")])
    assert "no aceptaría ninguna conexión" in resumen.texto_pendientes


def test_ca_c0_1_1_el_texto_de_resumen_sin_firewall_apagado_es_vacio():
    assert texto_firewall_resumen(cfg_base()) == ""
    assert texto_firewall_resumen(cfg_base(firewall=FirewallMV())) == ""


# --- Resumen del lote -------------------------------------------------------------------------


class ClienteFirewallFalso(ClienteLoteFalso):
    """``ClienteLoteFalso`` que además lee los grupos y el firewall general (solo lectura)."""

    def grupos_firewall(self):
        return [WEB, DB]

    def opciones_firewall_cluster(self):
        return {"enable": 1}

    def reglas_grupo_firewall(self, grupo):
        return [ReglaFirewall("in", "ACCEPT", True)]


def _plan_con_firewall(firewalls):
    from proxlaunch.nucleo.lote.filas import definicion_por_filas
    from proxlaunch.nucleo.lote.modelos import FilaLote

    filas = [
        FilaLote(f"web-{i + 1:02d}", cfg_simple(nombre=f"web-{i + 1:02d}", firewall=f))
        for i, f in enumerate(firewalls)
    ]
    return planificar(
        inventario_cluster(),
        definicion_por_filas(filas, plantilla_base=cfg_simple()),
        cliente=ClienteFirewallFalso(),
    )


def test_ca_c0_1_1_el_resumen_del_lote_muestra_el_firewall_comun():
    plan = _plan_con_firewall([fw(), fw(), fw()])
    texto = texto_opciones_del_plan(plan)
    assert "Firewall: activado, grupo web, entrada Bloquear, salida Permitir" in texto


def test_ca_c0_5_2_el_resumen_del_lote_dice_que_varia_si_las_filas_difieren():
    plan = _plan_con_firewall([fw("web"), fw("db"), None])
    linea = next(x for x in texto_opciones_del_plan(plan).splitlines() if x.startswith("Firewall"))
    assert linea == "Firewall: varía según la fila"


def test_ca_c0_1_3_el_resumen_del_lote_sin_firewall_no_gana_lineas():
    plan = _plan_con_firewall([None, None])
    assert "Firewall" not in texto_opciones_del_plan(plan)
    plan2 = _plan_con_firewall([FirewallMV(), FirewallMV()])
    assert "Firewall" not in texto_opciones_del_plan(plan2)


def test_ca_c0_1_1_la_pantalla_del_lote_con_firewall_se_dibuja(qtbot):
    plan = _plan_con_firewall([fw(), fw()])
    r = ResumenLote()
    qtbot.addWidget(r)
    r.show()
    r.mostrar_plan(plan)
    assert "Firewall" in "\n".join(lbl.text() for lbl in r.findChildren(QLabel))


@pytest.mark.parametrize(
    ("codigo", "contiene"),
    [
        ("firewall_grupo_ya_estaba:web", "web"),
        ("firewall_heredado", "plantilla"),
        ("red_tarjeta_ilegible:net1", "net1"),
    ],
)
def test_ca_c3_6_1_los_avisos_previos_de_la_simulacion_tienen_texto(codigo, contiene):
    texto = texto_aviso_simulacion(codigo)
    assert texto and contiene in texto


# --- RF-C3.8 / CA-C3.8.5: informe y detalle ---------------------------------------------------


def _entrada_parcial(firewall, pendientes, *, error=None):
    cfg = cfg_simple(100, "web-01", firewall=firewall)
    return EntradaLibro(
        ElementoPlan(0, "web-01", 100, "pve1", cfg),
        EstadoMV.PARCIAL,
        post_intentado=True,
        upid="UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:ana@pve:",
        avisos=tuple(f"ajuste_pendiente:{p}" for p in pendientes),
        error=error,
    )


def _error_regla():
    return ErrorProxLaunch(
        CodigoError.AJUSTE_POST_CLON_FALLIDO,
        {"nombre": "web-01", "ajuste": "firewall_regla", "causa": "servidor_no_responde"},
    )


def test_ca_c3_8_5_el_detalle_de_una_mv_parcial_por_firewall_incluye_el_riesgo():
    e = _entrada_parcial(fw(), ["firewall_regla"], error=_error_regla())
    detalle = detalle_entrada(e)
    assert texto_riesgo_firewall_parcial() in detalle
    assert "sin conexión entrante" in detalle


@pytest.mark.parametrize("pendiente", ["red", "firewall_opciones", "firewall_regla"])
def test_ca_c3_8_5_el_riesgo_aparece_con_cada_paso_pendiente(pendiente):
    assert texto_riesgo_firewall_parcial() in detalle_entrada(
        _entrada_parcial(fw(), [pendiente], error=_error_regla())
    )


def test_ca_c3_8_5_una_mv_parcial_sin_firewall_no_lleva_el_texto_de_riesgo():
    e = _entrada_parcial(None, ["etiquetas"], error=_error_regla())
    assert texto_riesgo_firewall_parcial() not in detalle_entrada(e)
    e2 = _entrada_parcial(FirewallMV(), ["etiquetas"], error=_error_regla())
    assert texto_riesgo_firewall_parcial() not in detalle_entrada(e2)


def test_ca_c3_8_5_una_mv_parcial_con_firewall_pero_solo_pendiente_de_etiquetas_no_lleva_riesgo():
    e = _entrada_parcial(fw(), ["etiquetas"], error=_error_regla())
    assert texto_riesgo_firewall_parcial() not in detalle_entrada(e)


def test_ca_c0_7_2_el_informe_distingue_lo_aplicado_de_lo_pendiente_y_trae_el_riesgo():
    from proxlaunch.interfaz import informe_lote as il

    e = _entrada_parcial(fw(), ["firewall_regla"], error=_error_regla())
    texto = il.texto_informe(informe_de((e,)))
    assert "Red y firewall de las máquinas" in texto
    assert "web-01 (100)" in texto
    bloque = texto.split("Red y firewall de las máquinas", 1)[1]
    assert "opciones de firewall aplicadas" in bloque.lower()
    assert "regla de grupo no aplicada" in bloque.lower()
    assert texto_riesgo_firewall_parcial() in bloque


def test_ca_c0_1_3_el_informe_sin_fase_c_no_gana_la_seccion_de_red_y_firewall():
    from proxlaunch.interfaz import informe_lote as il

    cfg = cfg_simple(100, "web-01")
    e = EntradaLibro(
        ElementoPlan(0, "web-01", 100, "pve1", cfg),
        EstadoMV.OK,
        post_intentado=True,
        upid="UPID:pve1:0003A1B2:00F4C1D3:6535AB12:qmcreate:100:ana@pve:",
    )
    assert "Red y firewall" not in il.texto_informe(informe_de((e,)))
