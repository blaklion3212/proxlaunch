"""VentanaPrincipal ensamblada con dependencias falsas: conexión, descubrimiento, validación
en vivo, creación y sus desenlaces (RF-19 a RF-24, CA-19.x, CA-20.x)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMessageBox

from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.dialogos.acerca_de import DialogoAcercaDe
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.tema import ModoTema
from proxlaunch.interfaz.ventana_principal import VentanaPrincipal
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace
from proxlaunch.nucleo.persistencia.preferencias import Modo
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso

from .apoyo import UPID, CreacionFalsa, perfil, resultado, sesion_falsa


class Entorno:
    """Reúne lo que las pruebas necesitan manipular de la ventana."""

    def __init__(self, ventana, inv, deps):
        self.ventana = ventana
        self.inv = inv
        self.deps = deps
        self.llamadas: list[tuple] = []
        self.vmid_ocupados: dict[int, str] = {}
        self.fallo_descubrir: ErrorProxLaunch | None = None
        self.creacion = CreacionFalsa(resultado(Desenlace.OK))


@pytest.fixture
def entorno(qtbot, deps, inv_cluster, monkeypatch):
    env_holder = {}

    def descubrir(sesion):
        env = env_holder["env"]
        env.llamadas.append(("descubrir",))
        if env.fallo_descubrir is not None:
            raise env.fallo_descubrir
        return env.inv, None

    def recargar(sesion, nodo):
        env_holder["env"].llamadas.append(("recargar", nodo))
        inv = env_holder["env"].inv
        return nodo, list(inv.storages[nodo]), list(inv.bridges[nodo])

    def comprobar(sesion, vmid):
        env = env_holder["env"]
        env.llamadas.append(("vmid", vmid))
        return vmid, env.vmid_ocupados.get(vmid)

    def reintentar(sesion, nodos):
        env = env_holder["env"]
        env.llamadas.append(("reintentar", tuple(nodos)))
        return {n: (list(env.inv.storages[n]), list(env.inv.bridges[n])) for n in nodos}, {}

    monkeypatch.setattr(vp, "descubrir_y_comprobar_permisos", descubrir)
    monkeypatch.setattr(vp, "recargar_nodo", recargar)
    monkeypatch.setattr(vp, "comprobar_vmid", comprobar)
    monkeypatch.setattr(vp, "reintentar_nodos", reintentar)
    deps.fabrica_creacion = lambda sesion: env_holder["env"].creacion
    ventana = VentanaPrincipal(deps)
    qtbot.addWidget(ventana)
    ventana.show()
    env = Entorno(ventana, inv_cluster, deps)
    env_holder["env"] = env
    yield env
    ventana.close()


def conectar(qtbot, env, sesion=None, uso_recuperacion=False):
    """Simula que el diálogo de conexión terminó bien y espera el descubrimiento."""
    v = env.ventana
    s = sesion or sesion_falsa()
    dialogo = SimpleNamespace(
        sesion=s,
        perfil_conectado=s.perfil,
        version_forzada=None,
        uso_clave_recuperacion=uso_recuperacion,
    )
    v._al_conectar(dialogo)
    qtbot.waitUntil(lambda: v._formulario_listo and not v._descubriendo, timeout=4000)
    return s


def esperar_validacion(qtbot, v):
    """Deja correr el temporizador de validación (intervalo 0)."""
    qtbot.waitUntil(lambda: not v._timer_validar.isActive(), timeout=2000)


def poner_nombre(qtbot, v, nombre="srv-web-01"):
    v.formulario.nombre.setText(nombre)
    v.formulario.nombre.textEdited.emit(nombre)
    esperar_validacion(qtbot, v)


def crear_y_esperar(qtbot, v):
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)


# --- Inicio -----------------------------------------------------------------------------------


def test_arranca_en_bienvenida_sin_conexion(entorno):
    v = entorno.ventana
    assert v._paginas.currentIndex() == 0
    assert v.statusBar().currentMessage() == "Sin conexión"
    assert v.barra._perfil.text() == "Sin conexión"
    assert v.boton_conectar.isVisible()


def test_primera_ejecucion_en_modo_basico(entorno):
    assert not entorno.ventana.avanzado  # CA-24.1


def test_modo_guardado_avanzado_se_restaura(qtbot, deps, entorno, monkeypatch):
    from proxlaunch.nucleo.persistencia.preferencias import Preferencias

    deps.preferencias.guardar(Preferencias(modo=Modo.AVANZADO))
    v2 = VentanaPrincipal(deps)
    qtbot.addWidget(v2)
    assert v2.avanzado and v2._acciones_modo[Modo.AVANZADO].isChecked()  # CA-24.4


# --- Conexión y descubrimiento ----------------------------------------------------------------


def test_al_conectar_muestra_trabajo_barra_y_formulario(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    assert v._paginas.currentIndex() == 1
    assert v.barra._perfil.text() == "Laboratorio · ana@pve!lab"
    assert v.barra.texto_version == "Proxmox VE 9.2"
    assert "lab" in v.barra.texto_topologia
    assert v.statusBar().currentMessage() == "Conectado"
    assert v.formulario.configuracion().vmid == entorno.inv.proximo_vmid
    assert "3 nodo(s)" in v._estado_descubrimiento.text()
    assert v.boton_actualizar.isEnabled()


def test_conexion_por_segundo_host_lo_dice_en_la_barra_de_estado(qtbot, entorno):
    s = sesion_falsa(perfil(hosts=("10.0.0.5", "10.0.0.6")))
    s.host_activo = "10.0.0.6"
    conectar(qtbot, entorno, s)
    msg = entorno.ventana.statusBar().currentMessage()
    assert "10.0.0.6" in msg and "10.0.0.5" in msg


def test_clave_de_recuperacion_usada_agrega_aviso(qtbot, entorno):
    conectar(qtbot, entorno, uso_recuperacion=True)
    assert any("clave de recuperación" in t for t in _textos_avisos(entorno.ventana))


def test_dialogo_vacio_no_cambia_nada(qtbot, entorno):
    entorno.ventana._al_conectar(SimpleNamespace(sesion=None, perfil_conectado=None))
    assert entorno.ventana._paginas.currentIndex() == 0


def test_abrir_conexion_no_abre_dos_dialogos(qtbot, entorno):
    v = entorno.ventana
    v.abrir_conexion()
    primero = v._dialogo_conexion
    assert primero is not None and primero.isVisible()
    v.abrir_conexion()
    assert v._dialogo_conexion is primero
    primero.reject()
    qtbot.waitUntil(lambda: v._dialogo_conexion is None, timeout=2000)


def test_el_boton_conectar_abre_el_dialogo_de_conexion(qtbot, entorno):
    v = entorno.ventana
    v.boton_conectar.click()
    assert v._dialogo_conexion is not None
    v._dialogo_conexion.reject()


def test_conectar_de_verdad_por_el_dialogo(qtbot, entorno, servicio_falso):
    from proxlaunch.nucleo.servicios.conexion import EstadoHuella

    from .apoyo import info_huella

    v = entorno.ventana
    servicio_falso.infos = [info_huella(EstadoHuella.CONFIRMADA)]
    servicio_falso.resultado_conectar = sesion_falsa()
    v.abrir_conexion()
    d = v._dialogo_conexion
    d.hosts.setPlainText("10.0.0.5")
    d.token.setText("ana@pve!lab=11111111-2222-3333-4444-555555555555")
    d.btn_conectar.click()
    qtbot.waitUntil(lambda: v._formulario_listo and not v._descubriendo, timeout=4000)
    assert v._paginas.currentIndex() == 1
    assert v._dialogo_conexion is None


def test_cambio_de_perfil_reinicia_el_formulario_y_el_mismo_perfil_lo_conserva(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v, "conservar")
    conectar(qtbot, entorno)  # mismo perfil: se conserva (CA-03.3)
    assert v.formulario.nombre.text() == "conservar"
    conectar(qtbot, entorno, sesion_falsa(perfil("otro", "Otro", ("10.0.0.9",))))
    assert v.formulario.nombre.text() == ""


def test_cerrar_sesion_vuelve_a_la_bienvenida(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    v._cerrar_sesion()
    assert v._paginas.currentIndex() == 0
    assert v.barra._perfil.text() == "Sin conexión"
    assert v._sesion is None


def test_fallo_al_descubrir_se_muestra_y_no_rompe(qtbot, entorno):
    v = entorno.ventana
    entorno.fallo_descubrir = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.5", "puerto": "8006"}
    )
    v._al_conectar(
        SimpleNamespace(
            sesion=sesion_falsa(),
            perfil_conectado=sesion_falsa().perfil,
            version_forzada=None,
            uso_clave_recuperacion=False,
        )
    )
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    assert "No se pudo leer" in v._estado_descubrimiento.text()
    assert "10.0.0.5:8006" in v.statusBar().currentMessage()
    assert v.boton_actualizar.isEnabled()
    etiquetas = [v._zona_avisos.itemAt(i).widget().text() for i in range(v._zona_avisos.count())]
    assert any("10.0.0.5:8006" in t for t in etiquetas)


def test_sesion_expirada_reabre_la_conexion_con_el_motivo(qtbot, entorno):
    v = entorno.ventana
    entorno.fallo_descubrir = ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
    conectar_sin_esperar = SimpleNamespace(
        sesion=sesion_falsa(),
        perfil_conectado=sesion_falsa().perfil,
        version_forzada=None,
        uso_clave_recuperacion=False,
    )
    v._al_conectar(conectar_sin_esperar)
    qtbot.waitUntil(lambda: v._dialogo_conexion is not None, timeout=4000)
    assert "sesión expiró" in v._dialogo_conexion._motivo.text()
    v._dialogo_conexion.reject()


def test_boton_actualizar_vuelve_a_descubrir_y_no_se_duplica(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    antes = entorno.llamadas.count(("descubrir",))
    v.boton_actualizar.click()
    assert not v.boton_actualizar.isEnabled()
    v._descubrir()  # reentrada ignorada
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    assert entorno.llamadas.count(("descubrir",)) == antes + 1


def test_nodo_caido_en_el_descubrimiento_muestra_aviso_y_reintentar(qtbot, entorno):
    v = entorno.ventana
    entorno.inv.errores_por_nodo = {"pve2": ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE)}
    conectar(qtbot, entorno)
    assert not v._nodos_fallidos.isHidden() and "pve2" in v._nodos_fallidos.text()
    assert v.boton_reintentar.isVisible()


def test_reintentar_nodos_los_recupera(qtbot, entorno):
    v = entorno.ventana
    entorno.inv.errores_por_nodo = {"pve2": ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE)}
    conectar(qtbot, entorno)
    v.boton_reintentar.click()
    qtbot.waitUntil(lambda: v._nodos_fallidos.isHidden(), timeout=4000)
    assert ("reintentar", ("pve2",)) in entorno.llamadas
    assert not v.boton_reintentar.isVisible()
    assert entorno.inv.errores_por_nodo == {}
    assert all(n.en_linea for n in entorno.inv.topologia.nodos if n.nombre == "pve2")


def test_reintentar_sin_fallos_no_hace_nada(qtbot, entorno):
    conectar(qtbot, entorno)
    entorno.ventana._reintentar_nodos()
    assert not any(ll[0] == "reintentar" for ll in entorno.llamadas)


# --- Avisos de la sesión ----------------------------------------------------------------------


def _textos_avisos(v):
    return [v._zona_avisos.itemAt(i).widget().text() for i in range(v._zona_avisos.count())]


def test_avisos_de_la_sesion_se_muestran(qtbot, entorno):
    s = sesion_falsa(
        avisos=[
            Aviso(CodigoAviso.VERSION_NO_PROBADA, {"version": "9.9"}),
            Aviso(CodigoAviso.LLAVERO_NO_DISPONIBLE),
        ]
    )
    conectar(qtbot, entorno, s)
    textos = _textos_avisos(entorno.ventana)
    assert any("9.9" in t for t in textos)
    assert any("llavero" in t for t in textos)


def test_falta_vm_allocate_bloquea_la_creacion_con_motivo(qtbot, entorno):
    v = entorno.ventana
    s = sesion_falsa(
        avisos=[
            Aviso(
                CodigoAviso.PERMISOS_INCOMPLETOS,
                {"privilegios": "VM.Allocate", "rutas": "VM.Allocate@/vms"},
            )
        ]
    )
    conectar(qtbot, entorno, s)
    poner_nombre(qtbot, v)
    assert not v.resumen.boton_crear.isEnabled()
    assert "VM.Allocate" in v.resumen._motivo.text()


def test_permisos_no_criticos_avisan_pero_no_bloquean(qtbot, entorno):
    v = entorno.ventana
    s = sesion_falsa(
        avisos=[
            Aviso(
                CodigoAviso.PERMISOS_INCOMPLETOS,
                {"privilegios": "Sys.Audit", "rutas": "Sys.Audit@/"},
            )
        ]
    )
    conectar(qtbot, entorno, s)
    poner_nombre(qtbot, v)
    assert any("Sys.Audit en /" in t for t in _textos_avisos(v))
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)


def test_topologia_degradada_se_refleja_en_la_barra(qtbot, entorno):
    s = sesion_falsa(avisos=[Aviso(CodigoAviso.TOPOLOGIA_DEGRADADA, {"nodos": "3"})])
    conectar(qtbot, entorno, s)
    assert "desconocida" in entorno.ventana.barra.texto_topologia


# --- Validación en vivo y resumen sincronizado ---------------------------------------------------


def test_sin_nombre_el_boton_crear_esta_deshabilitado(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    esperar_validacion(qtbot, v)
    assert not v.resumen.boton_crear.isEnabled()
    assert "Nombre" in v.resumen.texto_pendientes


def test_nombre_valido_habilita_crear(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    assert v.resumen.boton_crear.isEnabled()
    assert v.resumen.texto_pendientes == ""


def test_resumen_se_sincroniza_con_el_formulario(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v, "mi-servidor")
    v.formulario.memoria.setText("8")
    v.formulario.memoria.textEdited.emit("8")
    v.formulario.tabla_discos.agregar_disco()
    v.formulario.tabla_redes.agregar_red()
    esperar_validacion(qtbot, v)
    html = v.resumen.texto_html
    assert "mi-servidor" in html and "8 GiB" in html
    assert "scsi1" in html and "net1" in html


def test_nombre_invalido_deshabilita_crear_y_marca_el_campo(qtbot, entorno):
    """CA-13.4."""
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v, "mal nombre")
    assert not v.resumen.boton_crear.isEnabled()
    assert v.formulario.fila_nombre.hay_error


def test_cambiar_a_avanzado_muestra_campos_y_guarda_la_preferencia(qtbot, entorno, deps):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v, "no-perder")
    v.establecer_modo(Modo.AVANZADO)
    assert v.avanzado and not v.formulario.fila_cpu.isHidden()
    assert v.formulario.nombre.text() == "no-perder"
    assert deps.preferencias.cargar().modo == Modo.AVANZADO  # CA-24.4
    v.establecer_modo(Modo.BASICO)
    assert deps.preferencias.cargar().modo == Modo.BASICO


def test_cambiar_el_tema_lo_persiste(qtbot, entorno, deps):
    v = entorno.ventana
    v.establecer_tema(ModoTema.CLARO)
    assert deps.preferencias.cargar().tema.value == "claro"
    assert v._acciones_tema[ModoTema.CLARO].isChecked()
    assert deps.gestor_tema.modo == ModoTema.CLARO


def test_fallo_al_guardar_preferencias_no_revienta(qtbot, entorno, monkeypatch):
    def falla(pref):
        raise OSError("disco lleno")

    monkeypatch.setattr(entorno.deps.preferencias, "guardar", falla)
    entorno.ventana.establecer_modo(Modo.AVANZADO)  # solo se registra en el log
    assert entorno.ventana.avanzado


def test_elegir_nodo_manual_recarga_sus_recursos(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    v.formulario._radio_manual.setChecked(True)
    qtbot.waitUntil(lambda: ("recargar", "pve1") in entorno.llamadas, timeout=3000)


def test_vmid_ocupado_se_detecta_en_segundo_plano_y_sugiere_el_siguiente(qtbot, entorno):
    v = entorno.ventana
    entorno.vmid_ocupados[100] = "105"
    conectar(qtbot, entorno)
    v.formulario.vmid.setText("100")
    v.formulario.vmid.textEdited.emit("100")
    v.formulario.vmid.editingFinished.emit()
    qtbot.waitUntil(lambda: v.formulario.fila_vmid.hay_error, timeout=3000)
    poner_nombre(qtbot, v)
    assert not v.resumen.boton_crear.isEnabled()
    assert "105" in v.formulario.fila_vmid._error.text()


def test_vmid_libre_no_marca_error(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    v.formulario.vmid.setText("300")
    v.formulario.vmid.editingFinished.emit()
    qtbot.waitUntil(lambda: ("vmid", 300) in entorno.llamadas, timeout=3000)
    esperar_validacion(qtbot, v)
    assert not v.formulario.fila_vmid.hay_error


# --- Creación y desenlaces ----------------------------------------------------------------------


def test_creacion_exitosa_muestra_etapas_upid_y_crear_otra(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert entorno.creacion.llamadas_crear == 1
    assert v.progreso.texto_upid == UPID
    assert "srv-web-01" in v.progreso.texto_mensaje and "101" in v.progreso.texto_mensaje
    assert v.progreso.boton_crear_otra.isVisible()
    assert not v.formulario.isEnabled()  # sigue bloqueado hasta «Crear otra» (CA-19.4)
    assert v.progreso.barra.format() != ""


def test_durante_la_creacion_el_formulario_esta_bloqueado_y_el_upid_visible(qtbot, entorno):
    import threading

    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    liberar = threading.Event()
    original = entorno.creacion.crear

    def lenta(cfg, inv, al_cambiar_etapa, cancelado, *, al_enviar=None):
        r = original(cfg, inv, al_cambiar_etapa, cancelado, al_enviar=al_enviar)
        liberar.wait(5)
        return r

    entorno.creacion.crear = lenta
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    qtbot.waitUntil(lambda: v.progreso.texto_upid == UPID, timeout=3000)
    assert v._creando and not v.formulario.isEnabled()
    assert "UPID" in v.progreso.detalles.texto
    assert not v.resumen.boton_crear.isEnabled()
    liberar.set()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)


def test_doble_clic_en_crear_envia_una_sola_peticion(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)
    v.resumen.boton_crear.click()
    v.resumen.boton_crear.click()
    v._crear()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert entorno.creacion.llamadas_crear == 1  # CA-19.6


def test_crear_otra_conserva_config_vacia_el_nombre_y_redescubre(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    v.formulario.memoria.setText("6")
    crear_y_esperar(qtbot, v)
    antes = entorno.llamadas.count(("descubrir",))
    v.progreso.boton_crear_otra.click()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    assert v.formulario.isEnabled()
    assert v.formulario.nombre.text() == ""
    assert v.formulario.memoria.text() == "6"
    assert entorno.llamadas.count(("descubrir",)) == antes + 1
    assert v.progreso.texto_upid == ""


def test_con_avisos_despliega_el_log_y_muestra_ambas_cosas(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.CON_AVISOS, log=["WARNINGS: 1"])
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert "Creada con avisos" in v.progreso.texto_mensaje
    assert "WARNINGS: 1" in v.progreso.detalles.texto
    assert v.progreso.detalles._texto.isVisible()


def test_error_de_creacion_desbloquea_y_muestra_el_mensaje_en_espanol(qtbot, entorno):
    v = entorno.ventana
    err = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm"}, "out of space")
    entorno.creacion.resultado = resultado(Desenlace.ERROR, err, upid=None)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert "local-lvm" in v.progreso.texto_mensaje
    assert v.formulario.isEnabled()
    assert v.progreso.boton_volver.isVisible()
    assert "out of space" in v.progreso.detalles.texto  # detalle técnico (CA-21.x)


def test_volver_al_formulario_tras_un_error(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(
        Desenlace.ERROR, ErrorProxLaunch(CodigoError.DESCONOCIDO), upid=None
    )
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    v.progreso.boton_volver.click()
    assert v.progreso.texto_upid == "" and not v.progreso.boton_volver.isVisible()
    assert v.formulario.isEnabled()
    qtbot.waitUntil(lambda: v.resumen.boton_crear.isEnabled(), timeout=2000)


def test_vmid_ocupado_en_la_creacion_marca_el_campo_con_el_siguiente(qtbot, entorno):
    # CA-13.3
    v = entorno.ventana
    err = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "101", "siguiente": "102"})
    entorno.creacion.resultado = resultado(Desenlace.ERROR, err, upid=None)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    esperar_validacion(qtbot, v)
    assert "102" in v.formulario.fila_vmid._error.text()
    assert v.formulario.nombre.text() == "srv-web-01"  # conserva todo lo escrito


def test_nodo_no_disponible_al_crear_vuelve_a_descubrir(qtbot, entorno):
    # CA-13.7
    v = entorno.ventana
    err = ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE, {"nodo": "pve1"})
    entorno.creacion.resultado = resultado(Desenlace.ERROR, err, upid=None)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    antes = entorno.llamadas.count(("descubrir",))
    crear_y_esperar(qtbot, v)
    qtbot.waitUntil(lambda: entorno.llamadas.count(("descubrir",)) == antes + 1, timeout=3000)


def test_sesion_expirada_al_crear_reabre_la_conexion(qtbot, entorno):
    v = entorno.ventana
    err = ErrorProxLaunch(CodigoError.SESION_EXPIRADA)
    entorno.creacion.resultado = resultado(Desenlace.ERROR, err, upid=None)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    qtbot.waitUntil(lambda: v._dialogo_conexion is not None, timeout=3000)
    v._dialogo_conexion.reject()


def test_excepcion_del_servicio_al_crear_es_conexion_perdida_conserva_upid_y_no_desbloquea(
    qtbot, entorno
):
    # F7 (punto 11): antes se trataba como ERROR y se desbloqueaba el formulario; ahora, como la
    # orden pudo haber salido, es CONEXION_PERDIDA, conserva el UPID y deja el formulario bloqueado.
    v = entorno.ventana
    entorno.creacion.resultado = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert not v.formulario.isEnabled()
    assert v._ultimo_resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert v._ultimo_resultado.upid == UPID


def test_tiempo_agotado_no_es_fallo_y_ofrece_seguir_o_comprobar(qtbot, entorno):
    # CA-20.6
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v.progreso.boton_seguir.isVisible() and v.progreso.boton_comprobar.isVisible()
    assert "sigue en marcha" in v.progreso.texto_mensaje
    assert not v.formulario.isEnabled()


def test_seguir_esperando_nunca_crea_dos_veces_y_termina_bien(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    entorno.creacion.respuestas_reanudar = [resultado(Desenlace.OK)]
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    v.progreso.boton_seguir.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert entorno.creacion.llamadas_crear == 1
    assert entorno.creacion.llamadas_reanudar == ["seguir"]
    assert v.progreso.boton_crear_otra.isVisible()
    assert "creada" in v.progreso.texto_mensaje


def test_comprobar_ahora_consulta_una_vez(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    entorno.creacion.respuestas_reanudar = [resultado(Desenlace.TIEMPO_AGOTADO)]
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert entorno.creacion.llamadas_reanudar == ["comprobar"]
    assert v.progreso.boton_seguir.isVisible()


def test_conexion_perdida_ofrece_comprobar_ahora_y_conserva_el_upid(qtbot, entorno):
    # CA-20.7
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.CONEXION_PERDIDA)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert v.progreso.boton_comprobar.isVisible() and not v.progreso.boton_seguir.isVisible()
    assert v.progreso.texto_upid == UPID
    assert "conexión" in v.progreso.texto_mensaje


def test_fallo_al_reanudar_se_trata_como_conexion_perdida(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.TIEMPO_AGOTADO)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)

    def falla(*a, **k):
        raise ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE)

    entorno.creacion.comprobar_ahora = falla
    v.progreso.boton_comprobar.click()
    qtbot.waitUntil(lambda: not v._creando, timeout=4000)
    assert v._ultimo_resultado.desenlace == Desenlace.CONEXION_PERDIDA
    assert v._ultimo_resultado.upid == UPID


def test_cancelado_es_neutral_y_desbloquea(qtbot, entorno):
    v = entorno.ventana
    entorno.creacion.resultado = resultado(Desenlace.CANCELADO, upid=None)
    conectar(qtbot, entorno)
    poner_nombre(qtbot, v)
    crear_y_esperar(qtbot, v)
    assert "No se creó nada" in v.progreso.texto_mensaje
    assert not v.progreso._mensaje.property("error")
    assert v.formulario.isEnabled()


def test_reanudar_sin_upid_no_hace_nada(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    v._reanudar(una_vez=True)
    assert not v._creando


def test_no_se_puede_abrir_conexion_ni_cerrar_sesion_creando(qtbot, entorno):
    v = entorno.ventana
    conectar(qtbot, entorno)
    v._creando = True
    v.abrir_conexion()
    v._cerrar_sesion()
    v._volver_al_formulario()
    v._crear_otra()
    assert v._dialogo_conexion is None and v._sesion is not None
    v._creando = False


# --- Cierre (CA-20.8) ---------------------------------------------------------------------


def test_cerrar_con_tarea_en_curso_pide_confirmacion_y_respeta_no(qtbot, entorno, monkeypatch):
    v = entorno.ventana
    preguntas = []

    def pregunta(padre, titulo, texto, *a, **k):
        preguntas.append(texto)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", pregunta)
    v._creando = True
    assert v.close() is False
    assert v.isVisible()
    assert "sigue ejecutándose" in preguntas[0]
    v._creando = False


def test_cerrar_con_tarea_en_curso_y_confirmar_cierra(qtbot, entorno, monkeypatch):
    v = entorno.ventana
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    v._creando = True
    assert v.close() is True
    v._creando = False


def test_cerrar_sin_tarea_no_pregunta(qtbot, entorno, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("no debe preguntar"))
    assert entorno.ventana.close() is True


# --- Menús -------------------------------------------------------------------------------------


def test_menu_ayuda_abre_guia_y_acerca_de_sin_bloquear(qtbot, entorno, monkeypatch):
    abiertos = []
    monkeypatch.setattr(DialogoGuiaToken, "exec", lambda self: abiertos.append("guia"))
    monkeypatch.setattr(DialogoAcercaDe, "exec", lambda self: abiertos.append("acerca"))
    menu_ayuda = next(
        a.menu()
        for a in entorno.ventana.menuBar().actions()
        if a.text().replace("&", "") == "Ayuda"
    )
    for accion in menu_ayuda.actions():
        accion.trigger()
    assert abiertos == ["guia", "acerca"]


def test_atajo_y_acciones_de_archivo(qtbot, entorno):
    barra = entorno.ventana.menuBar()
    archivo = barra.actions()[0].menu()
    nombres = [a.text() for a in archivo.actions() if a.text()]
    assert "Conectar..." in nombres and "Cerrar sesión" in nombres and "Salir" in nombres


def test_las_preferencias_se_guardan_en_la_ruta_de_prueba(qtbot, entorno, rutas):
    entorno.ventana.establecer_modo(Modo.AVANZADO)
    datos = json.loads(rutas.preferencias.read_text(encoding="utf-8"))
    assert datos["modo"] == "avanzado"
