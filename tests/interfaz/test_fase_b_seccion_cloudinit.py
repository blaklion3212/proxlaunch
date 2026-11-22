"""Sección «Configuración inicial (cloud-init)» (fase B, 0.7.0): tarjetas, heredados, motivo de lo
deshabilitado, contraseña y propiedad del ``Secreto``.

Derivadas de docs/requisitos/fase-b.md y de los contratos de docs/arquitectura/fase-b.md §14:
CA-B0.6.2, CA-B1.2.2, CA-B1.2.4, CA-B1.2.5, CA-B1.7.3, CA-B1.7.6, CA-B8.1.1, CL-B20, RF-B0.8 y
RF-B1.4. El centinela de contraseña es ``S3cr3t-Prueba!``.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QToolButton

from proxlaunch.interfaz.vistas.seccion_cloudinit import SeccionCloudInit
from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB
from proxlaunch.nucleo.cloudinit.modelos import ModoTarjeta
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

from .apoyo_fase_b import (
    CENTINELA,
    CLAVE_ED25519,
    CLAVE_RSA,
    disponibilidad,
    heredado,
    info_plantilla,
    textos_visibles,
)


@pytest.fixture
def seccion(qtbot):
    s = SeccionCloudInit()
    qtbot.addWidget(s)
    s.show()
    s.establecer_modo(True)  # avanzado: DNS, dominio, actualizar y scripts a la vista
    s.establecer_info(info_plantilla(), disponibilidad())
    return s


def escribir(campo, texto: str) -> None:
    """Como el teclado: cambia el texto y emite ``textEdited``."""
    campo.setText(texto)
    campo.textEdited.emit(texto)


def poner_contrasena(s: SeccionCloudInit, valor: str, repeticion: str | None = None) -> None:
    escribir(s.txt_contrasena, valor)
    escribir(s.txt_repeticion, valor if repeticion is None else repeticion)


def permisos_sin(*quitar: str) -> PermisosEfectivos:
    """Rol de ProxLaunch más los privilegios de la fase B, sin los que se quitan."""
    todos = (
        *ROL_PROXLAUNCH,
        "VM.Config.Cloudinit",
        "VM.GuestAgent.Audit",
        "Datastore.AllocateSpace",
    )
    return PermisosEfectivos(rutas={"/": {p: 1 for p in todos if p not in quitar}})


# --- CA-B1.7.6: una tarjeta por netN de la plantilla ---


def test_ca_b1_7_6_una_plantilla_con_una_sola_tarjeta_muestra_solo_el_bloque_de_la_tarjeta_1(
    seccion,
):
    assert list(seccion.tarjetas) == [0]
    assert seccion.tarjetas[0].isVisibleTo(seccion)
    nombre = seccion.tarjetas[0].combo_modo.accessibleName()
    assert "Tarjeta de red 1" in nombre and "net0" in nombre


def test_ca_b1_7_6_con_tres_tarjetas_salen_tres_bloques_en_orden_de_netn(qtbot, seccion):
    seccion.establecer_info(info_plantilla(tarjetas=(2, 0, 1)), disponibilidad())
    assert list(seccion.tarjetas) == [0, 1, 2]
    # Un widget añadido a un layout visible se muestra en la siguiente vuelta del bucle de eventos.
    qtbot.waitUntil(lambda: all(b.isVisibleTo(seccion) for b in seccion.tarjetas.values()))
    ys = [b.mapTo(seccion, b.rect().topLeft()).y() for b in seccion.tarjetas.values()]
    assert ys == sorted(ys)


def test_ca_b1_7_6_una_plantilla_sin_tarjetas_conocidas_ofrece_la_tarjeta_1(seccion):
    seccion.establecer_info(info_plantilla(tarjetas=()), disponibilidad())
    assert list(seccion.tarjetas) == [0]


# --- CA-B1.7.3: IP y puerta solo con IP fija ---


@pytest.mark.parametrize(
    ("modo", "habilitados"),
    [
        (ModoTarjeta.SIN_CONFIGURAR, False),
        (ModoTarjeta.DHCP, False),
        (ModoTarjeta.FIJA, True),
    ],
)
def test_ca_b1_7_3_ip_y_puerta_solo_se_habilitan_con_ip_fija(seccion, modo, habilitados):
    bloque = seccion.tarjetas[0]
    bloque.combo_modo.setCurrentIndex(bloque.combo_modo.findData(modo))
    assert bloque.txt_ip.isEnabled() is habilitados
    assert bloque.txt_puerta.isEnabled() is habilitados
    assert bloque.combo_modo.isEnabled()


def test_ca_b1_7_3_pasar_de_ip_fija_a_dhcp_deshabilita_los_campos_sin_perder_lo_escrito(seccion):
    bloque = seccion.tarjetas[0]
    bloque.combo_modo.setCurrentIndex(bloque.combo_modo.findData(ModoTarjeta.FIJA))
    escribir(bloque.txt_ip, "192.168.1.50/24")
    bloque.combo_modo.setCurrentIndex(bloque.combo_modo.findData(ModoTarjeta.DHCP))
    assert not bloque.txt_ip.isEnabled()
    ci = seccion.configuracion()
    assert ci is not None
    assert ci.tarjeta(0).modo == ModoTarjeta.DHCP
    assert ci.tarjeta(0).ip is None  # en DHCP la IP escrita no se envía


def test_ca_b1_7_3_el_valor_de_ip_fija_llega_a_la_configuracion(seccion):
    bloque = seccion.tarjetas[0]
    bloque.combo_modo.setCurrentIndex(bloque.combo_modo.findData(ModoTarjeta.FIJA))
    escribir(bloque.txt_ip, "192.168.1.50/24")
    escribir(bloque.txt_puerta, "192.168.1.1")
    t = seccion.configuracion().tarjeta(0)
    assert (t.modo, t.ip, t.puerta) == (ModoTarjeta.FIJA, "192.168.1.50/24", "192.168.1.1")


def test_la_serie_solo_se_ofrece_en_un_lote_con_ip_fija(seccion):
    bloque = seccion.tarjetas[0]
    bloque.combo_modo.setCurrentIndex(bloque.combo_modo.findData(ModoTarjeta.FIJA))
    assert not bloque.fila_serie.isVisibleTo(seccion)
    seccion.establecer_lote(True)
    assert bloque.fila_serie.isVisibleTo(seccion)
    assert bloque.chk_serie.isChecked()  # en un lote la serie viene marcada (RF-B1.9)
    escribir(bloque.txt_ip, "10.0.0.5/24")
    assert seccion.configuracion().tarjeta(0).serie is True
    seccion.establecer_lote(False)
    assert not bloque.fila_serie.isVisibleTo(seccion)
    assert seccion.configuracion().tarjeta(0).serie is False


# --- CA-B1.2.4: cambiar de plantilla relee los datos y restablece lo incompatible ---


def test_ca_b1_2_4_una_tarjeta_que_la_plantilla_nueva_no_tiene_se_restablece_con_aviso(seccion):
    seccion.establecer_info(info_plantilla(tarjetas=(0, 1, 2)), disponibilidad())
    bloque = seccion.tarjetas[2]
    bloque.combo_modo.setCurrentIndex(bloque.combo_modo.findData(ModoTarjeta.FIJA))
    escribir(bloque.txt_ip, "10.0.0.9/24")
    avisos = []
    seccion.cambiado.connect(lambda: avisos.append(1))

    seccion.establecer_info(info_plantilla(tarjetas=(0,)), disponibilidad())

    assert list(seccion.tarjetas) == [0]
    assert "tarjeta de red 3" in textos_visibles(seccion)
    assert "restableci" in textos_visibles(seccion)
    ci = seccion.configuracion()
    assert ci is None or ci.tarjeta(2) is None
    assert avisos, "el formulario debe revalidar tras un restablecimiento"


def test_ca_b1_2_4_una_tarjeta_sin_valor_que_desaparece_no_genera_aviso(seccion):
    seccion.establecer_info(info_plantilla(tarjetas=(0, 1)), disponibilidad())
    seccion.establecer_info(info_plantilla(tarjetas=(0,)), disponibilidad())
    assert list(seccion.tarjetas) == [0]
    assert "restableci" not in textos_visibles(seccion)


def test_ca_b1_2_4_la_tarjeta_que_sigue_existiendo_conserva_lo_escrito(seccion):
    seccion.establecer_info(info_plantilla(tarjetas=(0, 1)), disponibilidad())
    b0 = seccion.tarjetas[0]
    b0.combo_modo.setCurrentIndex(b0.combo_modo.findData(ModoTarjeta.DHCP))
    seccion.establecer_info(info_plantilla(tarjetas=(0,)), disponibilidad())
    assert seccion.tarjetas[0].modo == ModoTarjeta.DHCP


def test_ca_b1_2_4_el_valor_de_una_opcion_que_deja_de_estar_disponible_se_restablece_con_aviso(
    seccion,
):
    escribir(seccion.txt_usuario, "deploy")
    assert seccion.configuracion().usuario == "deploy"
    # La plantilla nueva no trae unidad cloud-init: todo se deshabilita y se restablece.
    seccion.establecer_info(
        info_plantilla(unidad=False), disponibilidad(info_plantilla(unidad=False))
    )
    assert seccion.txt_usuario.text() == ""
    assert not seccion.txt_usuario.isEnabled()
    assert "restableci" in textos_visibles(seccion)
    assert seccion.configuracion() is None


def test_ca_b1_2_4_la_misma_informacion_dos_veces_no_repite_avisos_ni_emite_senales(seccion):
    emitidas = []
    seccion.cambiado.connect(lambda: emitidas.append(1))
    seccion.establecer_info(info_plantilla(), disponibilidad())
    seccion.establecer_info(info_plantilla(), disponibilidad())
    assert emitidas == []


# --- CA-B1.2.5: heredados como ayuda, campos vacíos ---


def test_ca_b1_2_5_los_valores_heredados_son_ayuda_y_los_campos_siguen_vacios(seccion):
    info = heredado(ciuser="ubuntu", **{"ipconfig0": "ip=dhcp"})
    seccion.establecer_info(info, disponibilidad(info))
    assert seccion.txt_usuario.text() == ""
    assert "Heredado de la plantilla: ubuntu" in seccion.txt_usuario.placeholderText()
    bloque = seccion.tarjetas[0]
    assert bloque.lbl_heredado.isVisibleTo(seccion)
    assert bloque.lbl_heredado.text() == "Heredado de la plantilla: ip=dhcp"
    assert bloque.modo == ModoTarjeta.SIN_CONFIGURAR  # no se reenvía si no se toca
    assert seccion.configuracion() is None  # nada que enviar: la plantilla ya lo trae


def test_ca_b1_2_5_dns_dominio_y_actualizar_heredados_tambien_se_muestran_como_ayuda(seccion):
    info = heredado(nameserver="1.1.1.1", searchdomain="lab.local", ciupgrade="1")
    seccion.establecer_info(info, disponibilidad(info))
    assert "1.1.1.1" in seccion.txt_dns.placeholderText()
    assert "lab.local" in seccion.txt_dominio.placeholderText()
    assert seccion.lbl_heredado_actualizar.isVisibleTo(seccion)
    assert seccion.txt_dns.text() == "" and seccion.txt_dominio.text() == ""
    assert seccion.configuracion() is None


def test_ca_b1_2_5_sin_valores_heredados_no_hay_etiquetas_de_heredado(seccion):
    assert not seccion.tarjetas[0].lbl_heredado.isVisibleTo(seccion)
    assert not seccion.lbl_heredado_actualizar.isVisibleTo(seccion)
    assert "Heredado" not in seccion.txt_usuario.placeholderText()


def test_ca_b1_2_5_el_script_heredado_se_muestra_junto_a_su_tipo(seccion):
    info = heredado()
    from .apoyo_fase_b import con_cicustom

    info = con_cicustom(vendor="local:snippets/agente.yaml")
    seccion.establecer_info(info, disponibilidad(info))
    sel = seccion.selectores_snippet["vendor"]
    assert "local:snippets/agente.yaml" in sel.lbl_heredado.text()
    assert sel.valor() is None  # «Como la plantilla»: no se reenvía


# --- CA-B1.2.2 / CA-B0.6.2: deshabilitado con el motivo visible ---


def test_ca_b1_2_2_sin_unidad_los_campos_se_deshabilitan_y_el_motivo_se_ve_sin_pasar_el_raton(
    seccion,
):
    info = info_plantilla(unidad=False)
    seccion.establecer_info(info, disponibilidad(info))
    for campo in (seccion.txt_usuario, seccion.txt_claves, seccion.btn_archivo_pub):
        assert not campo.isEnabled()
    assert not seccion.tarjetas[0].combo_modo.isEnabled()
    visible = textos_visibles(seccion)
    assert "unidad" in visible.lower()
    assert seccion.txt_usuario.accessibleDescription()  # y también para lectores de pantalla


def test_ca_b0_6_2_sin_privilegio_de_cloudinit_el_motivo_nombra_el_privilegio(seccion):
    permisos = permisos_sin("VM.Config.Cloudinit")
    seccion.establecer_info(
        info_plantilla(), disponibilidad(info_plantilla(), version=(9, 2), permisos=permisos)
    )
    assert not seccion.txt_usuario.isEnabled()
    assert "VM.Config.Cloudinit" in textos_visibles(seccion)
    assert "VM.Config.Cloudinit" in seccion.txt_usuario.accessibleDescription()


def test_ca_b0_6_2_sin_almacenamiento_de_scripts_el_selector_se_deshabilita_con_motivo(seccion):
    seccion.establecer_info(info_plantilla(), disponibilidad(snippets=False))
    for sel in seccion.selectores_snippet.values():
        assert not sel.combo.isEnabled()
    assert seccion.txt_usuario.isEnabled()  # cloud-init básico sigue disponible
    visible = textos_visibles(seccion).lower()
    assert "fragmentos" in visible or "snippets" in visible or "scripts" in visible


def test_ca_b0_6_2_una_plantilla_de_windows_deshabilita_la_contrasena_y_lo_explica(seccion):
    info = info_plantilla(es_windows=True, ostype="win11")
    seccion.establecer_info(info, disponibilidad(info))
    assert not seccion.txt_contrasena.isEnabled()
    assert "windows" in textos_visibles(seccion).lower()
    assert seccion.txt_usuario.isEnabled()


def test_ca_b0_6_2_al_volver_a_estar_disponible_los_controles_se_rehabilitan(seccion):
    info = info_plantilla(unidad=False)
    seccion.establecer_info(info, disponibilidad(info))
    seccion.establecer_info(info_plantilla(), disponibilidad())
    assert seccion.txt_usuario.isEnabled() and seccion.txt_claves.isEnabled()
    assert seccion.tarjetas[0].combo_modo.isEnabled()


# --- CA-B8.1.1: texto introductorio visible y «?» ---


def test_ca_b8_1_1_la_seccion_tiene_texto_introductorio_visible_y_un_boton_de_ayuda(seccion):
    assert "Cloud-init configura la máquina" in textos_visibles(seccion)
    ayudas = [b for b in seccion.findChildren(QToolButton) if b.text() == "?"]
    assert ayudas
    assert all(b.toolTip() for b in ayudas)
    assert all(b.accessibleName() for b in ayudas)


def test_ca_b8_1_1_los_scripts_tienen_explicacion_visible_y_su_propio_boton_de_ayuda(seccion):
    caja = seccion.caja_snippets
    assert caja.isVisibleTo(seccion)
    etiquetas = textos_visibles(caja)
    assert "Un script (snippet) es un archivo de texto" in etiquetas
    assert [b for b in caja.findChildren(QToolButton) if b.text() == "?" and b.toolTip()]


def test_en_modo_basico_dns_dominio_actualizar_y_scripts_se_ocultan_sin_perder_valores(seccion):
    escribir(seccion.txt_dns, "1.1.1.1")
    seccion.establecer_modo(False)
    assert not seccion.txt_dns.isVisibleTo(seccion)
    assert not seccion.caja_snippets.isVisibleTo(seccion)
    assert seccion.configuracion().dns == ("1.1.1.1",)


# --- Contraseña: campo vacío = None; nunca Secreto("") ---


def test_un_campo_de_contrasena_vacio_da_contrasena_none(seccion):
    escribir(seccion.txt_usuario, "deploy")
    ci = seccion.configuracion()
    assert ci is not None
    assert ci.contrasena is None


def test_solo_la_contrasena_vacia_y_nada_mas_no_envia_cloudinit(seccion):
    assert seccion.configuracion() is None


def test_una_contrasena_no_vacia_crea_un_secreto_con_el_valor_escrito(seccion):
    poner_contrasena(seccion, CENTINELA)
    ci = seccion.configuracion()
    assert ci is not None and ci.contrasena is not None
    assert ci.contrasena.definido
    assert ci.contrasena.revelar() == CENTINELA


def test_la_contrasena_nunca_aparece_en_repr_str_ni_en_el_dataclass(seccion):
    poner_contrasena(seccion, CENTINELA)
    ci = seccion.configuracion()
    assert ci is not None and ci.contrasena is not None
    for texto in (repr(ci), str(ci), repr(ci.contrasena), str(ci.contrasena), f"{ci.contrasena}"):
        assert CENTINELA not in texto
    assert CENTINELA not in repr(seccion.configuracion())


def test_una_contrasena_distinta_de_su_repeticion_no_crea_secreto_y_da_v_b25(seccion):
    poner_contrasena(seccion, CENTINELA, "otra-distinta-123")
    ci = seccion.configuracion()
    assert ci is None or ci.contrasena is None
    problemas = seccion.problemas()
    assert any(p.codigo == "V-B25" for p in problemas)
    assert all(CENTINELA not in str(p.params) for p in problemas)


def test_la_misma_contrasena_devuelve_el_mismo_secreto_mientras_no_cambie(seccion):
    poner_contrasena(seccion, CENTINELA)
    primero = seccion.configuracion().contrasena
    assert seccion.configuracion().contrasena is primero


def test_editar_la_contrasena_olvida_el_secreto_anterior(seccion):
    poner_contrasena(seccion, CENTINELA)
    anterior = seccion.configuracion().contrasena
    escribir(seccion.txt_contrasena, "OtraClave-123456")
    assert not anterior.definido
    assert CENTINELA not in repr(seccion.configuracion())


def test_el_aviso_de_contrasena_no_muestra_el_valor_escrito(seccion):
    poner_contrasena(seccion, CENTINELA, "otra-distinta-123")
    seccion.mostrar_problemas(seccion.problemas())
    assert CENTINELA not in textos_visibles(seccion)
    assert "otra-distinta-123" not in textos_visibles(seccion)


def test_los_campos_de_contrasena_estan_enmascarados_por_defecto(seccion):
    from PySide6.QtWidgets import QLineEdit

    assert seccion.txt_contrasena.echoMode() == QLineEdit.EchoMode.Password
    assert seccion.txt_repeticion.echoMode() == QLineEdit.EchoMode.Password
    seccion.chk_mostrar.setChecked(True)
    assert seccion.txt_contrasena.echoMode() == QLineEdit.EchoMode.Normal


# --- ceder_secreto() y limpiar_secretos(): propiedad del Secreto (§14) ---


def test_ceder_secreto_suelta_el_secreto_sin_olvidarlo_y_vacia_los_campos(seccion):
    poner_contrasena(seccion, CENTINELA)
    secreto = seccion.configuracion().contrasena

    seccion.ceder_secreto()

    assert secreto.definido, "ceder no es olvidar: el lote lo seguirá usando"
    assert secreto.revelar() == CENTINELA
    assert seccion.txt_contrasena.text() == "" and seccion.txt_repeticion.text() == ""
    ci = seccion.configuracion()
    assert ci is None or ci.contrasena is None


def test_ceder_secreto_sin_contrasena_no_falla(seccion):
    seccion.ceder_secreto()
    assert seccion.txt_contrasena.text() == ""


def test_limpiar_secretos_olvida_el_secreto_que_la_seccion_aun_posee_y_vacia_los_campos(seccion):
    poner_contrasena(seccion, CENTINELA)
    secreto = seccion.configuracion().contrasena

    seccion.limpiar_secretos()

    assert not secreto.definido
    assert seccion.txt_contrasena.text() == "" and seccion.txt_repeticion.text() == ""


def test_limpiar_secretos_no_olvida_un_secreto_ya_cedido_solo_el_propio(seccion):
    poner_contrasena(seccion, CENTINELA)
    cedido = seccion.configuracion().contrasena
    seccion.ceder_secreto()
    poner_contrasena(seccion, "SegundaClave-9876")
    propio = seccion.configuracion().contrasena
    assert propio is not cedido

    seccion.limpiar_secretos()

    assert cedido.definido and cedido.revelar() == CENTINELA
    assert not propio.definido


def test_editar_tras_ceder_no_olvida_el_secreto_cedido(seccion):
    poner_contrasena(seccion, CENTINELA)
    cedido = seccion.configuracion().contrasena
    seccion.ceder_secreto()
    escribir(seccion.txt_contrasena, "Nueva-123456")  # editar crea uno nuevo, no toca el cedido
    assert cedido.definido


def test_limpiar_secretos_dos_veces_es_inocuo(seccion):
    poner_contrasena(seccion, CENTINELA)
    seccion.limpiar_secretos()
    seccion.limpiar_secretos()
    assert seccion.txt_contrasena.text() == ""


def test_limpiar_secretos_deja_de_marcar_error_en_la_fila_de_contrasena(seccion):
    poner_contrasena(seccion, CENTINELA, "otra-distinta-123")
    seccion.limpiar_secretos()
    assert not seccion.problemas() or all(p.codigo != "V-B25" for p in seccion.problemas())


# --- Claves SSH: la clave privada se rechaza y se borra; el resumen no enseña el cuerpo ---


def test_una_clave_privada_se_rechaza_y_se_borra_del_campo_al_instante(seccion):
    seccion.txt_claves.setPlainText(CLAVE_ED25519)
    seccion.txt_claves.setPlainText(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----"
    )
    assert seccion.txt_claves.toPlainText() == ""
    assert seccion.lbl_error_claves.isVisibleTo(seccion)
    assert "clave privada" in seccion.lbl_error_claves.text()
    ci = seccion.configuracion()
    assert ci is None or ci.claves == ()


def test_el_resumen_de_claves_dice_tipo_y_comentario_y_nunca_el_cuerpo(seccion):
    seccion.txt_claves.setPlainText(f"{CLAVE_ED25519}\n{CLAVE_RSA}")
    texto = seccion.lbl_resumen_claves.text()
    assert "2 claves" in texto and "ssh-ed25519" in texto and "ana@portatil" in texto
    assert "AAAAC3NzaC1lZDI1NTE5" not in texto and "AAAAB3NzaC1yc2E" not in texto


def test_plural_una_clave_dice_1_clave_y_dos_dicen_n_claves(seccion):
    seccion.txt_claves.setPlainText(CLAVE_ED25519)
    assert seccion.lbl_resumen_claves.text().startswith("1 clave:")
    assert not seccion.lbl_resumen_claves.text().startswith("1 claves")
    seccion.txt_claves.setPlainText(f"{CLAVE_ED25519}\n{CLAVE_RSA}")
    assert seccion.lbl_resumen_claves.text().startswith("2 claves:")


# --- CL-B20: cambio de servidor tras rellenar el formulario ---


def test_cl_b20_al_cambiar_de_servidor_se_reevaluan_privilegios_y_se_restablece_con_aviso(seccion):
    escribir(seccion.txt_usuario, "deploy")
    poner_contrasena(seccion, CENTINELA)
    secreto = seccion.configuracion().contrasena
    sin_permiso = permisos_sin("VM.Config.Cloudinit")

    seccion.establecer_info(
        info_plantilla(), disponibilidad(info_plantilla(), version=(9, 2), permisos=sin_permiso)
    )

    assert seccion.txt_usuario.text() == ""
    assert seccion.txt_contrasena.text() == "" and seccion.txt_repeticion.text() == ""
    assert "restableci" in textos_visibles(seccion)
    assert "VM.Config.Cloudinit" in textos_visibles(seccion)
    assert not secreto.definido, "la contraseña restablecida no debe quedar viva en memoria"


def test_cl_b20_al_cambiar_de_version_a_una_sin_la_funcion_la_opcion_se_deshabilita(seccion):
    escribir(seccion.txt_dns, "1.1.1.1")
    seccion.establecer_info(
        info_plantilla(),
        disponibilidad(
            info_plantilla(), permisos=permisos_sin("VM.Config.Cloudinit", "VM.Config.Network")
        ),
    )
    assert not seccion.txt_dns.isEnabled()
    assert seccion.txt_dns.text() == ""


def test_cl_b20_el_estado_de_cada_opcion_llega_a_su_grupo(seccion):
    estados = disponibilidad()
    assert set(estados) >= {OpcionB.CLOUDINIT, OpcionB.CONTRASENA, OpcionB.SNIPPETS}
    seccion.establecer_info(info_plantilla(), estados)
    assert seccion.txt_contrasena.isEnabled()
