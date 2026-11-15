"""MVP 4, F7: pruebas de las correcciones de la revisión QA y de seguridad (interfaz).

Derivadas de los requisitos (docs/requisitos/mvp4.md) y de las interfaces públicas de los widgets.
Un bloque por hallazgo (QA-M4-xx / SEG-M4-xx). Sin red ni modales reales: ``confirmar`` y el
servicio de transferencias están sustituidos; nada llama a ``exec``.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz import ayuda as ay
from proxlaunch.interfaz import textos
from proxlaunch.interfaz.dialogos import transferencia as dt
from proxlaunch.interfaz.dialogos.catalogo import FuenteCatalogo
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.dialogos.transferencia import DialogoDescarga, DialogoSubida
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.interfaz.vistas.resumen import ResumenVM
from proxlaunch.interfaz.vistas.selector_origen import SelectorOrigen
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import DetalleClon, DetalleIso, ModoClon, TipoSO
from proxlaunch.nucleo.modelos.vm import Firmware, OrigenSO
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.transferencias.modelos import EstadoTransferencia as Est
from proxlaunch.nucleo.transferencias.url import validar_checksum, validar_url
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_mvp4 import (
    VOLID_ISO,
    VOLID_VIRTIO,
    ControladorFalso,
    ServicioTransferenciasFalso,
    caps_origen,
    cfg_base,
    cfg_clon,
    cfg_iso,
    inv_origen,
    permisos,
    plantilla_pve,
    progreso,
    resultado_transferencia,
    volumen,
)

# --- Selector: QA-M4-03 (destino del clon completo) y QA-M4-06 (drivers) -------------------------


@pytest.fixture
def selector(qtbot):
    s = SelectorOrigen()
    qtbot.addWidget(s)
    s.show()
    s.establecer_capacidades(caps_origen())
    return s


def _clon_completo(destino: str | None):
    cfg = cfg_clon(modo=ModoClon.COMPLETO)
    det = dataclasses.replace(cfg.detalle_origen, storage_destino=destino)
    return dataclasses.replace(cfg, detalle_origen=det)


@pytest.mark.parametrize("avanzado", [False, True], ids=["basico", "avanzado"])
def test_qa_m4_03_un_lote_guardado_conserva_el_storage_destino_aunque_el_combo_este_vacio(
    selector, avanzado
):
    selector.establecer_modo(avanzado)
    selector.aplicar(_clon_completo("datos"))  # el combo aún no tiene la lista del servidor
    cfg = selector.completar(cfg_base())
    assert isinstance(cfg.detalle_origen, DetalleClon)
    assert cfg.detalle_origen.modo == ModoClon.COMPLETO
    assert cfg.detalle_origen.storage_destino == "datos"


def test_qa_m4_03_se_reaplica_al_rellenar_el_combo_sin_emitir_cambios(selector, qtbot):
    selector.establecer_modo(True)
    selector.aplicar(_clon_completo("datos"))
    with qtbot.assertNotEmitted(selector.seleccion_cambiada):  # RF-G08: ningún cambio falso
        selector.establecer_storages_destino(["otro", "datos"])
    assert selector.combo_storage_destino.currentData() == "datos"
    assert selector.completar(cfg_base()).detalle_origen.storage_destino == "datos"


def test_qa_m4_03_cambiar_el_combo_al_aplicar_no_añade_cambios_falsos(selector):
    selector.establecer_modo(True)
    selector.establecer_storages_destino(["datos"])
    emisiones = []
    selector.seleccion_cambiada.connect(lambda: emisiones.append(1))
    selector.aplicar(_clon_completo(None))
    emisiones.clear()  # la primera carga puede emitir por el cambio de origen; la segunda no
    selector.aplicar(_clon_completo("datos"))  # el combo pasa de «plantilla» a «datos»
    assert emisiones == []  # cambiar el combo al cargar no cuenta como cambio del usuario (RF-G08)
    assert selector.combo_storage_destino.currentData() == "datos"


def test_qa_m4_03_si_el_servidor_no_tiene_ese_storage_no_se_sustituye_en_silencio(selector):
    selector.establecer_modo(True)
    selector.aplicar(_clon_completo("fantasma"))
    selector.establecer_storages_destino(["datos"])
    assert selector.combo_storage_destino.currentIndex() == 0  # «El de la plantilla»
    # el valor pedido sigue siendo el del lote: no se cambia a otro storage sin avisar
    assert selector.completar(cfg_base()).detalle_origen.storage_destino == "fantasma"


def test_qa_m4_03_el_destino_solo_se_envia_con_copia_completa(selector):
    selector.aplicar(_clon_completo("datos"))
    selector.combo_modo.setCurrentIndex(selector.combo_modo.findData(ModoClon.ENLAZADO.value))
    assert selector.completar(cfg_base()).detalle_origen.storage_destino is None


def test_qa_m4_03_aplicar_otro_lote_sin_destino_o_con_otro_origen_lo_olvida(selector):
    selector.establecer_modo(True)
    selector.aplicar(_clon_completo("datos"))
    selector.aplicar(_clon_completo(None))
    assert selector.completar(cfg_base()).detalle_origen.storage_destino is None
    selector.aplicar(_clon_completo("datos"))
    selector.aplicar(cfg_iso())
    selector.aplicar(_clon_completo(None))
    assert selector.completar(cfg_base()).detalle_origen.storage_destino is None


def test_qa_m4_03_lo_que_elige_el_usuario_despues_manda(selector, qtbot):
    selector.establecer_modo(True)
    selector.establecer_storages_destino(["datos", "otro"])
    selector.aplicar(_clon_completo("datos"))
    with qtbot.waitSignal(selector.seleccion_cambiada):
        selector.combo_storage_destino.setCurrentIndex(
            selector.combo_storage_destino.findData("otro")
        )
    assert selector.completar(cfg_base()).detalle_origen.storage_destino == "otro"


def test_qa_m4_03_el_formulario_hace_ida_y_vuelta_del_destino(qtbot):
    inv = inv_origen()
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo([], [plantilla_pve()], nodo="pve")
    f.establecer_modo(True)
    f.aplicar_hardware(_clon_completo("local"))
    det = f.configuracion().detalle_origen
    assert det.modo == ModoClon.COMPLETO and det.storage_destino == "local"


def _a_windows(selector):
    selector.opciones[OrigenSO.ISO].setChecked(True)
    selector.combo_so.setCurrentIndex(selector.combo_so.findData(TipoSO.WINDOWS_10.value))


def _a_so(selector, tipo):
    selector.combo_so.setCurrentIndex(selector.combo_so.findData(tipo.value))


def test_qa_m4_06_al_pasar_a_un_so_sin_drivers_se_olvidan_y_se_desmarca_sin_drivers(selector):
    _a_windows(selector)
    selector.establecer_seleccion(FuenteCatalogo.DRIVERS, volumen(VOLID_VIRTIO))
    selector.casilla_sin_drivers.setChecked(True)  # marcar la casilla descarta los elegidos
    selector.establecer_seleccion(FuenteCatalogo.DRIVERS, volumen(VOLID_VIRTIO))
    _a_so(selector, TipoSO.LINUX)
    assert not selector.casilla_sin_drivers.isChecked()
    assert not selector.aviso_sin_drivers.isVisible()
    det = selector.completar(cfg_base()).detalle_origen
    assert isinstance(det, DetalleIso)
    assert det.drivers is None and det.sin_drivers is False


def test_qa_m4_06_sin_drivers_marcado_no_se_arrastra_a_un_so_no_windows(selector):
    _a_windows(selector)
    selector.casilla_sin_drivers.setChecked(True)
    assert selector.completar(cfg_base()).detalle_origen.sin_drivers is True
    _a_so(selector, TipoSO.OTRO)
    det = selector.completar(cfg_base()).detalle_origen
    assert det.sin_drivers is False and det.drivers is None


def test_qa_m4_06_al_volver_a_windows_hay_que_decidir_de_nuevo(selector):
    _a_windows(selector)
    selector.casilla_sin_drivers.setChecked(True)
    _a_so(selector, TipoSO.LINUX)
    _a_so(selector, TipoSO.WINDOWS_11)
    assert not selector.casilla_sin_drivers.isChecked()
    assert selector.completar(cfg_base()).detalle_origen.sin_drivers is False


# --- Formulario: QA-M4-04 (base del asistente) ---------------------------------------------------


@pytest.fixture
def formulario(qtbot):
    inv = inv_origen()
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo([volumen(VOLID_ISO)], [plantilla_pve()], nodo="pve")
    return f


def _elegir(f, tipo):
    combo = f.selector_origen.combo_so
    combo.setCurrentIndex(combo.findData(tipo.value))


def _huella_hw(f):
    c = f.configuracion()
    return (
        c.firmware,
        c.tpm,
        c.agente_qemu,
        c.controlador_scsi,
        tuple(d.bus for d in c.discos),
        tuple(r.modelo for r in c.redes),
    )


@pytest.mark.parametrize("destino", [TipoSO.OTRO, TipoSO.LINUX], ids=["otro", "linux"])
def test_qa_m4_04_de_windows_11_a_otro_so_se_vuelve_a_la_base_sin_uefi_tpm_ni_agente(
    formulario, destino
):
    formulario.selector_origen.opciones[OrigenSO.ISO].setChecked(True)
    base_antes = _huella_hw(formulario)
    _elegir(formulario, TipoSO.WINDOWS_11)
    w11 = _huella_hw(formulario)
    assert w11 != base_antes and w11[0] == Firmware.OVMF and w11[1] is True
    _elegir(formulario, destino)
    cfg = formulario.configuracion()
    assert cfg.firmware != Firmware.OVMF
    assert cfg.tpm is False and cfg.agente_qemu is False
    if destino == TipoSO.LINUX:
        assert cfg.tipo_so == TipoSO.LINUX


def test_qa_m4_04_cada_so_se_aplica_sobre_la_misma_base_aunque_se_cambie_varias_veces(formulario):
    formulario.selector_origen.opciones[OrigenSO.ISO].setChecked(True)
    _elegir(formulario, TipoSO.LINUX)
    linux = _huella_hw(formulario)
    _elegir(formulario, TipoSO.WINDOWS_11)
    _elegir(formulario, TipoSO.WINDOWS_10)
    _elegir(formulario, TipoSO.WINDOWS_11)
    _elegir(formulario, TipoSO.LINUX)
    assert _huella_hw(formulario) == linux  # el orden de elecciones no deja rastro
    _elegir(formulario, TipoSO.WINDOWS_10)
    assert formulario.configuracion().tpm is False  # sin TPM heredado de Windows 11


def test_qa_m4_04_cargar_un_perfil_o_lote_descarta_la_base_anterior(formulario):
    formulario.selector_origen.opciones[OrigenSO.ISO].setChecked(True)
    _elegir(formulario, TipoSO.WINDOWS_11)
    cargado = cfg_iso(tipo_so=TipoSO.LINUX)  # SeaBIOS, sin TPM, sin agente
    formulario.aplicar_hardware(cargado)
    _elegir(formulario, TipoSO.OTRO)
    cfg = formulario.configuracion()
    assert cfg.firmware == Firmware.SEABIOS and cfg.tpm is False  # no vuelve al W11 viejo


def test_qa_m4_04_al_dejar_iso_y_volver_la_base_es_lo_que_muestra_el_formulario(formulario):
    formulario.selector_origen.opciones[OrigenSO.ISO].setChecked(True)
    _elegir(formulario, TipoSO.WINDOWS_11)
    formulario.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    formulario.selector_origen.opciones[OrigenSO.ISO].setChecked(True)
    _elegir(formulario, TipoSO.OTRO)
    # La base nueva es lo que había en los widgets (UEFI de la elección anterior): se conserva.
    assert formulario.configuracion().firmware == Firmware.OVMF


# --- Diálogos de transferencia: QA-M4-02 ---------------------------------------------------------


@pytest.fixture
def iso_local(tmp_path):
    ruta = tmp_path / "alpine mini.iso"
    ruta.write_bytes(bytes(bytearray(0x8000) + b"\x01CD001\x01" + bytes(2048)))
    return ruta


@pytest.fixture
def servicio():
    s = ServicioTransferenciasFalso()
    yield s
    s.puerta.set()


@pytest.fixture
def ctrl(servicio):
    c = ControladorFalso(inv_origen(), servicio)
    yield c
    c.lanzador.esperar(3000)


def _subida(qtbot, ctrl, ruta) -> DialogoSubida:
    d = DialogoSubida(ctrl, Contenido.ISO, "pve", ruta=ruta)
    qtbot.addWidget(d)
    d.show()
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)
    return d


@pytest.mark.parametrize("estado", [Est.ESPERANDO_SERVIDOR, Est.VERIFICANDO])
def test_qa_m4_02_con_el_cuerpo_enviado_cancelar_subida_pasa_a_dejar_de_esperar(
    qtbot, ctrl, servicio, iso_local, estado
):
    servicio.progresos = [progreso(1024, 1024, estado)]
    servicio.bloquear = True
    d = _subida(qtbot, ctrl, iso_local)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: d.boton_cancelar.text() == "Dejar de esperar", timeout=3000)
    d.boton_cancelar.click()
    assert d.boton_cancelar.text() == "Dejando de esperar…"
    assert not d.boton_cancelar.isEnabled()
    qtbot.waitUntil(lambda: d.resultado is not None, timeout=4000)


def test_qa_m4_02_mientras_se_envia_el_boton_sigue_siendo_cancelar_subida(
    qtbot, ctrl, servicio, iso_local
):
    servicio.progresos = [progreso(512, 1024, Est.TRANSFIRIENDO)]
    servicio.bloquear = True
    d = _subida(qtbot, ctrl, iso_local)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: d.transferencia_en_curso, timeout=3000)
    assert d.boton_cancelar.text() == "Cancelar subida"
    servicio.puerta.set()
    qtbot.waitUntil(lambda: d.resultado is not None, timeout=4000)


def test_qa_m4_02_el_mensaje_final_de_la_subida_sin_esperar_dice_que_el_servidor_sigue(
    qtbot, ctrl, servicio, iso_local
):
    servicio.resultado = resultado_transferencia(
        Est.SIN_ESPERAR, volid=None, quedo=None, upid="UPID:pve:1:2:3:imgcopy::a@pve:"
    )
    d = _subida(qtbot, ctrl, iso_local)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: d.resultado is not None, timeout=4000)
    texto = d.etiqueta_final.text()
    assert "el servidor sigue copiándolo" in texto
    assert "No quedó ningún archivo" not in texto  # no se afirma nada falso
    assert not d.boton_reintentar.isVisible()


def test_qa_m4_02_el_mensaje_sin_esperar_de_una_descarga_sigue_siendo_el_de_la_descarga(
    qtbot, ctrl, servicio
):
    servicio.resultado = resultado_transferencia(Est.SIN_ESPERAR, volid=None, quedo=None)
    d = DialogoDescarga(ctrl, Contenido.ISO, "pve")
    qtbot.addWidget(d)
    d.show()
    _comprobar(qtbot, d)
    d.boton_accion.click()
    qtbot.waitUntil(lambda: d.resultado is not None, timeout=4000)
    assert "La descarga sigue en el servidor" in d.etiqueta_final.text()


def test_qa_m4_02_texto_quedo_archivo_desconocido_empieza_por_no_sabemos():
    assert textos.texto_quedo_archivo(None).startswith("No sabemos")
    assert "Quedó un archivo" in textos.texto_quedo_archivo(True)
    assert "No quedó ningún archivo" in textos.texto_quedo_archivo(False)


# --- Descarga: SEG-M4-07, SEG-M4-08, SEG-M4-09, SEG-M4-11 ----------------------------------------


def _descarga(qtbot, ctrl) -> DialogoDescarga:
    d = DialogoDescarga(ctrl, Contenido.ISO, "pve")
    qtbot.addWidget(d)
    d.show()
    return d


def _comprobar(qtbot, d, url="https://mirror.example.org/alpine.iso", huella=""):
    d.campo_url.setText(url)
    d.campo_checksum.setText(huella)
    d.comprobar_url()
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.5/a.iso",
        "https://192.168.1.20/a.iso",
        "https://172.16.0.9/a.iso",
        "https://127.0.0.1/a.iso",
        "https://169.254.169.254/a.iso",
        "https://[::1]/a.iso",
    ],
)
def test_seg_m4_07_una_ip_literal_privada_loopback_o_link_local_avisa_pero_no_bloquea(
    qtbot, ctrl, url
):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, url)  # llega a «listo»: no bloquea
    assert d.avisos_descarga.isVisible()
    assert "red interna" in d.avisos_descarga.text()


@pytest.mark.parametrize(
    "url",
    ["https://8.8.8.8/a.iso", "https://mirror.example.org/a.iso", "https://localhost/a.iso"],
)
def test_seg_m4_07_una_ip_publica_o_un_nombre_no_avisan(qtbot, ctrl, url):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, url)
    assert not d.avisos_descarga.isVisible()


@pytest.mark.parametrize("puerto,avisa", [(8080, True), (8443, True), (443, False), (80, False)])
def test_seg_m4_07_un_puerto_distinto_de_80_y_443_avisa(qtbot, ctrl, puerto, avisa):
    d = _descarga(qtbot, ctrl)
    ctrl.modo_avanzado = True  # el puerto 80 solo es posible con http en avanzado
    _comprobar_aceptando(qtbot, d, f"https://mirror.example.org:{puerto}/a.iso")
    assert d.avisos_descarga.isVisible() is avisa
    if avisa:
        assert str(puerto) in d.avisos_descarga.text()


def _comprobar_aceptando(qtbot, d, url):
    d.campo_url.setText(url)
    d.comprobar_url()
    qtbot.waitUntil(lambda: d.listo_para_confirmar, timeout=4000)


def test_seg_m4_07_se_pueden_acumular_aviso_de_ip_y_de_puerto(qtbot, ctrl):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, "https://10.0.0.5:8443/a.iso")
    texto = d.avisos_descarga.text()
    assert "red interna" in texto and "8443" in texto


def test_seg_m4_07_un_aviso_viejo_se_borra_al_comprobar_otra_direccion(qtbot, ctrl):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, "https://10.0.0.5/a.iso")
    assert d.avisos_descarga.isVisible()
    _comprobar(qtbot, d, "https://mirror.example.org/a.iso")
    assert not d.avisos_descarga.isVisible()


def test_seg_m4_08_la_nota_del_registro_de_tareas_del_servidor_esta_visible(qtbot, ctrl):
    d = _descarga(qtbot, ctrl)
    assert d.nota_registro.isVisible()
    assert d.nota_registro.text() == "La dirección quedará en el registro de tareas del servidor."


def test_seg_m4_09_aceptar_el_riesgo_una_vez_no_lo_repite_si_nada_cambia(
    qtbot, ctrl, servicio, monkeypatch
):
    ctrl.modo_avanzado = True
    preguntas = []
    monkeypatch.setattr(dt, "confirmar", lambda *a, **k: preguntas.append(a[2]) or True)
    d = _descarga(qtbot, ctrl)
    d.casilla_certificados.setChecked(False)
    _comprobar(qtbot, d)
    _comprobar(qtbot, d)  # nueva comprobación igual: la respuesta se recuerda
    d.boton_accion.click()
    qtbot.waitUntil(lambda: any(ll[0] == "descargar" for ll in servicio.llamadas), timeout=3000)
    assert len(preguntas) == 1


def test_seg_m4_09_cambiar_la_casilla_o_el_esquema_vuelve_a_preguntar(qtbot, ctrl, monkeypatch):
    ctrl.modo_avanzado = True
    preguntas = []
    monkeypatch.setattr(dt, "confirmar", lambda *a, **k: preguntas.append(a[2]) or True)
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, "http://mirror.example.org/a.iso")  # http: riesgo 1
    assert len(preguntas) == 1
    d.casilla_certificados.setChecked(False)  # http + sin verificar: otra clave
    _comprobar(qtbot, d, "http://mirror.example.org/a.iso")
    assert len(preguntas) == 2
    _comprobar(qtbot, d, "https://mirror.example.org/a.iso")  # https sin verificar: otra clave
    assert len(preguntas) == 3
    assert "http://" in preguntas[0] and "certificado" in preguntas[2]


def test_seg_m4_09_rechazar_el_riesgo_no_se_recuerda(qtbot, ctrl, monkeypatch):
    ctrl.modo_avanzado = True
    respuestas = iter([False, True])
    preguntas = []
    monkeypatch.setattr(dt, "confirmar", lambda *a, **k: preguntas.append(a[2]) or next(respuestas))
    d = _descarga(qtbot, ctrl)
    d.casilla_certificados.setChecked(False)
    d.campo_url.setText("https://mirror.example.org/alpine.iso")
    d.comprobar_url()
    assert not d.listo_para_confirmar
    _comprobar(qtbot, d)  # segunda vez: vuelve a preguntar y ahora acepta
    assert len(preguntas) == 2


@pytest.mark.parametrize(
    "huella,algoritmo",
    [("a" * 32, "MD5"), ("a" * 40, "SHA1")],
)
def test_seg_m4_11_una_huella_md5_o_sha1_avisa_sin_bloquear(qtbot, ctrl, huella, algoritmo):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, huella=huella)
    assert d.avisos_descarga.isVisible()
    assert algoritmo in d.avisos_descarga.text() and "SHA-256" in d.avisos_descarga.text()


@pytest.mark.parametrize("huella", ["a" * 64, "a" * 128, ""])
def test_seg_m4_11_sha256_sha512_o_sin_huella_no_avisan(qtbot, ctrl, huella):
    d = _descarga(qtbot, ctrl)
    _comprobar(qtbot, d, huella=huella)
    assert not d.avisos_descarga.isVisible()


def test_seg_m4_07_y_11_funciones_de_aviso_puras():
    url, _ = validar_url("https://10.1.2.3:9000/a.iso", permitir_http=False)
    assert len(dt._avisos_url(url)) == 2
    cs, _ = validar_checksum("b" * 32)
    assert dt._aviso_checksum(cs) is not None
    assert dt._aviso_checksum(None) is None


# --- Guía del token y texto para el administrador: SEG-M4-01 -------------------------------------


def test_seg_m4_01_el_rol_de_maquinas_no_lleva_vm_clone_y_conserva_el_resto_de_vm():
    assert "VM.Clone" in ROL_PROXLAUNCH and "VM.Clone" not in ay.PRIVILEGIOS_ROL_MAQUINAS
    esperados = tuple(p for p in ROL_PROXLAUNCH if p.startswith("VM.") and p != "VM.Clone")
    assert esperados == ay.PRIVILEGIOS_ROL_MAQUINAS and esperados
    assert all(p.startswith("VM.") for p in ay.PRIVILEGIOS_ROL_MAQUINAS)
    assert ay.NOMBRE_ROL_MAQUINAS == "ProxLaunchMaquinas"


def test_seg_m4_01_los_permisos_acotados_cubren_cada_ruta_recomendada():
    texto = "\n".join(ay.permisos_acotados())
    for esperado in (
        "/pool/plantillas-proxlaunch",
        ay.NOMBRE_ROL,
        ay.NOMBRE_ROL_MAQUINAS,
        "«/vms»",
        "/storage/<almacenamiento>",
        "/nodes/<nodo>",
        "Sys.AccessNetwork",
        "/sdn/zones/localnetwork",
        "SDN.Use",
        "Sys.Audit",
        "Datastore.AllocateTemplate",
        "Datastore.AllocateSpace",
    ):
        assert esperado in texto, esperado
    assert "SIN «Propagar»" in texto  # la ruta «/» no se propaga
    assert "SIN VM.Clone" in texto
    for p in ay.PRIVILEGIOS_ROL_MAQUINAS:
        assert p in texto


def test_seg_m4_01_la_alternativa_simple_explica_el_riesgo():
    t = ay.alternativa_simple_permisos()
    assert "«/»" in t and "Propagar" in t and ay.NOMBRE_ROL in t
    assert "todo el servidor" in t and "clonar cualquier máquina" in t
    assert "laboratorio" in t


def test_seg_m4_01_los_pasos_de_la_guia_ya_no_mandan_a_la_raiz_como_unica_via():
    pasos = "\n".join(ay.pasos_guia_token())
    assert "deja marcado «Propagar»" not in pasos
    assert "alcance acotado" in pasos


def test_seg_m4_01_texto_para_el_administrador_incluye_alcance_acotado_y_alternativa():
    t = ay.texto_pedir_al_administrador()
    for linea in ay.permisos_acotados():
        assert linea in t
    assert ay.alternativa_simple_permisos() in t
    assert "alcance acotado" in t


def test_seg_m4_01_el_dialogo_de_la_guia_muestra_el_alcance_acotado_y_el_aviso(qtbot):
    d = DialogoGuiaToken()
    qtbot.addWidget(d)
    d.show()
    textos_ui = "\n".join(w.text() for w in d.findChildren(QLabel))
    assert "alcance acotado" in textos_ui
    assert "/pool/plantillas-proxlaunch" in textos_ui and "/sdn/zones/localnetwork" in textos_ui
    assert d.aviso_alternativa.isVisible()
    assert d.aviso_alternativa.text() == ay.alternativa_simple_permisos()


# --- SEG-M4-02 en la interfaz: V-O31 -------------------------------------------------------------


def test_seg_m4_02_texto_de_v_o31_lleva_el_volid_y_el_storage():
    p = Problema("detalle_origen", "V-O31", Severidad.AVISO, {"volid": "nfs1:iso/virtio-win-9.iso"})
    t = textos.texto_problema(p)
    assert "nfs1:iso/virtio-win-9.iso" in t and "«nfs1»" in t and "de confianza" in t


def test_seg_m4_02_v_o31_sin_storage_sigue_mostrando_el_volid():
    p = Problema("detalle_origen", "V-O31", Severidad.AVISO, {"volid": "virtio-win.iso"})
    assert "virtio-win.iso" in textos.texto_problema(
        p
    ) and "almacenamiento" not in textos.texto_problema(p)


def test_seg_m4_02_el_resumen_lo_muestra_como_aviso_no_bloqueante(qtbot):
    r = ResumenVM()
    qtbot.addWidget(r)
    r.show()
    p = Problema(
        "detalle_origen", "V-O31", Severidad.AVISO, {"volid": "local:iso/virtio-win-0.1.9.iso"}
    )
    r.actualizar(
        cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers="local:iso/virtio-win-0.1.9.iso"),
        ["scsi0"],
        [p],
        avanzado=False,
        motivo_nodo="",
        bloqueo=None,
        ocupado=False,
        cambios_asistente=(),
        permisos=permisos(),
    )
    assert "local:iso/virtio-win-0.1.9.iso" in r._avisos.text()
    assert r._avisos.isVisible()
