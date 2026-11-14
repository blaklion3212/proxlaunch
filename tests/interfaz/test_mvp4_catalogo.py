"""Catálogo de ISOs, discos y plantillas; elegir y recordar el storage por servidor
(RF-O04 a RF-O07, RF-O19, RF-O24; V-O26)."""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import Qt

from proxlaunch.interfaz.controlador_origen import ControladorOrigen
from proxlaunch.interfaz.dialogos.catalogo import DialogoCatalogo, FuenteCatalogo
from proxlaunch.interfaz.dialogos.elegir_storage import DialogoElegirStorage, preseleccionado
from proxlaunch.interfaz.modelos_tabla_origen import FilaPlantilla, FilaVolumen
from proxlaunch.interfaz.trabajadores import Lanzador
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido, Plantilla
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.validacion import Severidad

from .apoyo import perfil, sesion_falsa, storage
from .apoyo_mvp4 import (
    ROL_10,
    VOLID_IMAGEN,
    VOLID_ISO,
    VOLID_VIRTIO,
    caps_origen,
    cfg_iso,
    inv_origen,
    permisos,
    plantilla_pve,
    storage_sin,
    volumen,
)

# --- Catálogo de volúmenes (RF-O07) ---------------------------------------------------------------


@pytest.fixture
def catalogo(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.ISO)
    qtbot.addWidget(d)
    d.show()
    return d


def _nombres(d: DialogoCatalogo) -> list[str]:
    m = d.modelo
    return [m.fila(i).volumen.nombre for i in range(m.rowCount())]


def test_ca_o07_1_el_catalogo_lista_los_isos_con_su_nombre_y_solo_los_del_contenido(catalogo):
    catalogo.establecer_volumenes(
        [volumen(VOLID_ISO), volumen(VOLID_IMAGEN, Contenido.IMPORT)], nodo="pve"
    )
    assert _nombres(catalogo) == ["alpine.iso"]
    assert catalogo.tabla.accessibleName()


def test_ca_o07_2_un_volumen_no_admitido_se_ve_pero_no_se_puede_elegir_y_dice_por_que(catalogo):
    malo = volumen("local:iso/virus.exe")
    assert not malo.admitido
    catalogo.establecer_volumenes([malo, volumen(VOLID_ISO)], nodo="pve")
    filas = {catalogo.modelo.fila(i).volumen.nombre: catalogo.modelo.fila(i) for i in range(2)}
    assert filas["virus.exe"].motivo and not filas["virus.exe"].elegible
    assert "Extensión" in filas["virus.exe"].motivo
    assert filas["alpine.iso"].elegible
    assert not catalogo.seleccionar_volid("local:iso/virus.exe")
    assert not catalogo.boton_elegir.isEnabled()


def test_ca_o07_2_nombre_con_caracteres_raros_no_es_elegible(catalogo):
    catalogo.establecer_volumenes([volumen("local:iso/a b;rm.iso")], nodo="pve")
    fila = catalogo.modelo.fila(0)
    assert not fila.elegible and "Nombre no admitido" in fila.motivo


def test_ca_o07_5_un_storage_sin_permiso_no_impide_ver_los_demas(catalogo):
    error = ErrorProxLaunch(
        CodigoError.CATALOGO_SIN_PERMISO, {"storage": "nfs1", "privilegio": "Datastore.Audit"}
    )
    catalogo.establecer_volumenes([volumen(VOLID_ISO)], nodo="pve", errores=[error])
    assert _nombres(catalogo) == ["alpine.iso"]
    assert catalogo.etiqueta_errores.isVisible()
    assert "nfs1" in catalogo.etiqueta_errores.text()


def test_ca_o07_8_catalogo_vacio_lleva_a_subir_y_descargar_si_se_puede(qtbot):
    caps = caps_origen()
    d = DialogoCatalogo(
        FuenteCatalogo.ISO,
        estado_subir=caps.estado(
            __import__("proxlaunch").nucleo.origen.capacidades_origen.Via.SUBIR_ISO
        ),
        estado_descargar=caps.estado(
            __import__("proxlaunch").nucleo.origen.capacidades_origen.Via.DESCARGAR_URL
        ),
    )
    qtbot.addWidget(d)
    d.show()
    d.establecer_volumenes([], nodo="pve")
    texto = d.etiqueta_estado.text()
    assert "No hay ningún ISO" in texto
    assert "subir" in texto and "descargue" in texto


def test_ca_o07_8_catalogo_vacio_sin_vias_no_promete_lo_que_no_se_puede(qtbot):
    from proxlaunch.nucleo.origen.capacidades_origen import Via

    caps = caps_origen(inv_origen(privilegios=ROL_10))
    d = DialogoCatalogo(
        FuenteCatalogo.ISO,
        estado_subir=caps.estado(Via.SUBIR_ISO),
        estado_descargar=caps.estado(Via.DESCARGAR_URL),
    )
    qtbot.addWidget(d)
    d.show()
    d.establecer_volumenes([], nodo="pve")
    assert d.etiqueta_estado.text() == "No hay ningún ISO en el servidor."
    assert not d.boton_subir.isEnabled() and not d.boton_descargar.isEnabled()
    assert "Subir desde mi equipo" in d.motivo_subir.text()


def test_ca_o10_5_sin_allocate_template_subir_queda_deshabilitado_con_el_motivo(qtbot):
    from proxlaunch.nucleo.origen.capacidades_origen import Via

    caps = caps_origen(inv_origen(privilegios=ROL_10))
    d = DialogoCatalogo(FuenteCatalogo.ISO, estado_subir=caps.estado(Via.SUBIR_ISO))
    qtbot.addWidget(d)
    d.show()
    assert not d.boton_subir.isEnabled()
    assert "Datastore.AllocateTemplate" in d.boton_subir.toolTip()
    assert d.motivo_subir.isVisible()


def test_el_catalogo_muestra_cargando_hasta_recibir_datos(catalogo):
    catalogo.establecer_cargando(True)
    assert catalogo.etiqueta_estado.text() == "Cargando…"
    assert not catalogo.boton_actualizar.isEnabled()
    catalogo.establecer_volumenes([volumen(VOLID_ISO)], nodo="pve")
    assert catalogo.etiqueta_estado.text() == ""


def test_el_filtro_reduce_la_lista_y_dice_cuando_no_hay_coincidencias(catalogo, qtbot):
    catalogo.establecer_volumenes([volumen(VOLID_ISO), volumen(VOLID_VIRTIO)], nodo="pve")
    qtbot.keyClicks(catalogo.campo_filtro, "virtio")
    assert catalogo.tabla.model().rowCount() == 1
    catalogo.campo_filtro.setText("zzz")
    assert "Ningún elemento coincide" in catalogo.etiqueta_estado.text()


def test_elegir_con_doble_clic_o_boton_emite_la_fila_y_acepta(catalogo, qtbot):
    catalogo.establecer_volumenes([volumen(VOLID_ISO)], nodo="pve")
    assert catalogo.seleccionar_volid(VOLID_ISO)
    with qtbot.waitSignal(catalogo.elegido) as senal:
        catalogo.boton_elegir.click()
    fila = senal.args[0]
    assert isinstance(fila, FilaVolumen) and fila.volumen.volid == VOLID_ISO
    assert catalogo.seleccion is fila


def test_cancelar_no_elige_nada(catalogo):
    catalogo.establecer_volumenes([volumen(VOLID_ISO)], nodo="pve")
    catalogo.seleccionar_volid(VOLID_ISO)
    catalogo.boton_cancelar.click()
    assert catalogo.seleccion is None


def test_el_boton_actualizar_y_los_de_transferencia_emiten_sus_senales(catalogo, qtbot):
    with qtbot.waitSignal(catalogo.actualizar_solicitado):
        catalogo.boton_actualizar.click()
    with qtbot.waitSignal(catalogo.subir_solicitado):
        catalogo.boton_subir.click()
    with qtbot.waitSignal(catalogo.descargar_solicitado):
        catalogo.boton_descargar.click()


def test_el_estado_de_una_fila_se_ve_en_texto_y_no_solo_en_color(catalogo):
    catalogo.establecer_volumenes([volumen("local:iso/virus.exe")], nodo="pve")
    m = catalogo.modelo
    textos = " ".join(
        str(m.data(m.index(0, c), Qt.ItemDataRole.DisplayRole)) for c in range(m.columnCount())
    )
    assert "Extensión no admitida" in textos


# --- Plantillas (RF-O19) -------------------------------------------------------------------------


def test_ca_o19_2_una_plantilla_bloqueada_o_sin_vm_clone_se_ve_pero_no_se_elige(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA)
    qtbot.addWidget(d)
    d.show()
    bloqueada = Plantilla(9001, "ocupada", "pve", "clone", None, None)
    libre = plantilla_pve(9000, "base")
    d.establecer_plantillas([libre, bloqueada], permisos(["VM.Clone"]))
    filas = {d.modelo.fila(i).plantilla.vmid: d.modelo.fila(i) for i in range(2)}
    assert filas[9000].elegible
    assert not filas[9001].elegible and "Bloqueada" in filas[9001].motivo
    assert d.seleccionar_vmid(9000) and not d.seleccionar_vmid(9001)


def test_ca_o19_2_sin_el_permiso_vm_clone_la_plantilla_no_es_elegible(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA)
    qtbot.addWidget(d)
    d.establecer_plantillas([plantilla_pve()], permisos(ROL_10))
    fila = d.modelo.fila(0)
    assert not fila.elegible and "VM.Clone" in fila.motivo


def test_ca_o19_2_con_permisos_desconocidos_la_plantilla_se_ofrece(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA)
    qtbot.addWidget(d)
    d.establecer_plantillas([plantilla_pve()], None)
    assert d.modelo.fila(0).elegible


def test_e_o17_sin_plantillas_dice_que_hacer(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA)
    qtbot.addWidget(d)
    d.show()
    d.establecer_plantillas([], None)
    assert d.etiqueta_estado.text() == "No hay ninguna plantilla en el servidor." or (
        "plantilla" in d.etiqueta_estado.text()
    )
    assert not d.boton_subir.isVisible() and not d.boton_descargar.isVisible()


def test_plantillas_aun_sin_leer_muestran_cargando(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA)
    qtbot.addWidget(d)
    d.show()
    d.establecer_plantillas(None)
    assert d.etiqueta_estado.text() == "Cargando…"


def test_elegir_una_plantilla_emite_filaplantilla(qtbot):
    d = DialogoCatalogo(FuenteCatalogo.PLANTILLA)
    qtbot.addWidget(d)
    d.show()
    d.establecer_plantillas([plantilla_pve()], None)
    d.seleccionar_vmid(9000)
    with qtbot.waitSignal(d.elegido) as senal:
        d.boton_elegir.click()
    assert isinstance(senal.args[0], FilaPlantilla)


# --- Diálogo «¿Cuál usar siempre?» (RF-O05, RF-O06) -----------------------------------------------


def _storages():
    return [storage("local", "dir", "images", 50), storage("datos", "dir", "images", 400)]


def test_ca_o05_2_el_dialogo_preselecciona_el_de_mas_espacio_y_recuerda_por_defecto(qtbot):
    d = DialogoElegirStorage(Contenido.IMAGENES, _storages())
    qtbot.addWidget(d)
    assert d.storage_seleccionado == "datos"
    assert d.casilla_recordar.isChecked()
    assert "¿Cuál usar siempre" in d.findChildren(__import__("PySide6").QtWidgets.QLabel)[0].text()
    assert not d.boton_dejar.isVisibleTo(d)
    d.boton_aceptar.click()
    assert d.eleccion.storage == "datos" and d.eleccion.recordar


def test_ca_o05_2_se_puede_elegir_sin_recordar(qtbot):
    d = DialogoElegirStorage(Contenido.IMAGENES, _storages())
    qtbot.addWidget(d)
    d.tabla.selectRow(0)
    d.casilla_recordar.setChecked(False)
    d.boton_aceptar.click()
    assert d.eleccion.storage == "datos" or d.eleccion.storage == "local"
    assert d.eleccion.recordar is False


def test_preseleccionado_desempata_por_id():
    a = storage("b", "dir", "images", 10)
    b = storage("a", "dir", "images", 10)
    assert preseleccionado([a, b]) == "a"
    assert preseleccionado([]) is None


def test_ca_o06_2_recordado_no_disponible_ofrece_elegir_otro_y_dejar_de_recordar(qtbot):
    d = DialogoElegirStorage(Contenido.ISO, _storages(), no_disponible="viejo")
    qtbot.addWidget(d)
    d.show()
    assert d.boton_dejar.isVisible()
    assert d.boton_aceptar.text() == "Elegir otro"
    d.boton_dejar.click()
    assert d.eleccion.dejar_de_recordar and d.eleccion.storage is None


def test_cancelar_el_dialogo_de_storage_no_deja_eleccion(qtbot):
    d = DialogoElegirStorage(Contenido.IMAGENES, _storages())
    qtbot.addWidget(d)
    d.boton_cancelar.click()
    assert d.eleccion is None


# --- ControladorOrigen.storage_para: recordar y olvidar ---------------------------------------


@pytest.fixture
def controlador(qtbot, rutas):
    from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles

    repo = RepositorioPerfiles(rutas.perfiles)
    repo.guardar(perfil())
    c = ControladorOrigen(Lanzador(), repo, RelojSimulado())
    c.repo = repo
    c.dialogos = []

    def _ejecutar(dialogo):
        c.dialogos.append(dialogo)
        return c.respuesta(dialogo)

    c._ejecutar = _ejecutar  # sin modales: la prueba decide qué responde el diálogo
    c.respuesta = lambda d: (d.boton_aceptar.click(), True)[1]
    return c


def _sesion_con(c: ControladorOrigen, inv, **perfil_kw):
    s = sesion_falsa(perfil(**perfil_kw))
    c.establecer_sesion(s, inv)
    return s


def _esperar_guardado(qtbot, c, campo, valor):
    qtbot.waitUntil(
        lambda: getattr(c.repo.obtener("p1"), campo) == valor and not c.lanzador.hay_activos,
        timeout=3000,
    )


def test_ca_o05_1_un_solo_candidato_se_usa_sin_preguntar_ni_guardar(
    controlador, qtbot, widget_padre
):
    _sesion_con(controlador, inv_origen())
    assert controlador.storage_para(Contenido.ISO, "pve", widget_padre) == "local"
    assert controlador.dialogos == []
    assert controlador.recordado(Contenido.ISO) is None
    assert controlador.repo.obtener("p1").storage_iso is None


def test_ca_o05_2_varios_candidatos_preguntan_y_recuerdan_en_el_perfil(
    controlador, qtbot, widget_padre
):
    _sesion_con(controlador, inv_origen(extra_images=True))
    elegido = controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre)
    assert elegido == "datos"
    assert len(controlador.dialogos) == 1
    assert controlador.recordado(Contenido.IMAGENES) == "datos"
    _esperar_guardado(qtbot, controlador, "storage_mv", "datos")


def test_ca_o05_3_con_un_recordado_vigente_no_vuelve_a_preguntar(controlador, widget_padre):
    _sesion_con(controlador, inv_origen(extra_images=True), storage_mv="local")
    assert controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre) == "local"
    assert controlador.dialogos == []


def test_ca_o05_2_elegir_sin_recordar_no_guarda_nada(controlador, widget_padre, qtbot):
    def sin_recordar(d):
        d.casilla_recordar.setChecked(False)
        d.boton_aceptar.click()
        return True

    controlador.respuesta = sin_recordar
    _sesion_con(controlador, inv_origen(extra_images=True))
    assert controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre) == "datos"
    assert controlador.recordado(Contenido.IMAGENES) is None
    assert controlador.repo.obtener("p1").storage_mv is None


def test_ca_o05_2_cancelar_el_dialogo_devuelve_none_y_no_recuerda(controlador, widget_padre):
    controlador.respuesta = lambda d: (d.boton_cancelar.click(), False)[1]
    _sesion_con(controlador, inv_origen(extra_images=True))
    assert controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre) is None
    assert controlador.recordado(Contenido.IMAGENES) is None


def test_ca_o06_1_recordado_que_ya_no_existe_avisa_y_no_lo_sustituye_en_silencio(
    controlador, widget_padre
):
    visto = {}

    def cancelar(d):
        visto["texto"] = d.findChildren(__import__("PySide6").QtWidgets.QLabel)[0].text()
        visto["dejar"] = d.boton_dejar.isVisibleTo(d)
        d.boton_cancelar.click()
        return False

    controlador.respuesta = cancelar
    _sesion_con(controlador, inv_origen(extra_images=True), storage_mv="fantasma")
    assert controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre) is None
    assert "fantasma" in visto["texto"]
    assert visto["dejar"] is True
    assert controlador.recordado(Contenido.IMAGENES) == "fantasma"  # no se tocó


def test_ca_o06_2_dejar_de_recordar_borra_el_recordado_y_vuelve_a_decidir(
    controlador, widget_padre, qtbot
):
    respuestas = []

    def responder(d):
        respuestas.append(d.boton_dejar.isVisibleTo(d))
        if d.boton_dejar.isVisibleTo(d):
            d.boton_dejar.click()
        else:
            d.boton_aceptar.click()
        return True

    controlador.respuesta = responder
    controlador.repo.guardar(dataclasses.replace(perfil(), storage_mv="fantasma"))
    _sesion_con(controlador, inv_origen(extra_images=True), storage_mv="fantasma")
    elegido = controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre)
    assert respuestas == [True, False]  # primero el aviso; luego el diálogo normal
    assert elegido == "datos"
    assert controlador.recordado(Contenido.IMAGENES) == "datos"


def test_ca_o06_5_si_el_recordado_vuelve_a_existir_se_usa_sin_preguntar(controlador, widget_padre):
    inv = inv_origen(extra_images=True)
    inv.storages_todos["pve"] = tuple(s for s in inv.storages_todos["pve"] if s.id != "datos")
    _sesion_con(controlador, inv, storage_mv="datos")
    assert controlador.hay_recordado_no_disponible("pve")
    inv2 = inv_origen(extra_images=True)
    controlador.adoptar(inv2)
    assert not controlador.hay_recordado_no_disponible("pve")
    assert controlador.storage_para(Contenido.IMAGENES, "pve", widget_padre) == "datos"
    assert controlador.dialogos == []


def test_ca_o05_7_cambiar_de_perfil_usa_los_recordados_de_ese_perfil(controlador, widget_padre):
    inv = inv_origen(extra_images=True)
    _sesion_con(controlador, inv, storage_mv="local")
    assert controlador.recordado(Contenido.IMAGENES) == "local"
    controlador.establecer_sesion(sesion_falsa(perfil("p2", "Otro")), inv)
    assert controlador.recordado(Contenido.IMAGENES) is None


def test_asegurar_storage_mv_pregunta_una_vez_y_emite_la_eleccion(controlador, widget_padre, qtbot):
    inv = inv_origen(extra_images=True)
    _sesion_con(controlador, inv)
    controlador.enlazar(
        __import__("proxlaunch").interfaz.vistas.selector_origen.SelectorOrigen(), lambda: "pve"
    )
    with qtbot.waitSignal(controlador.storage_mv_elegido) as senal:
        controlador.asegurar_storage_mv(widget_padre)
    assert senal.args == ["datos"]
    # Con el storage ya recordado no vuelve a preguntar.
    controlador.dialogos.clear()
    controlador.asegurar_storage_mv(widget_padre)
    assert controlador.dialogos == []


def test_asegurar_storage_mv_no_pregunta_con_un_solo_candidato(controlador, widget_padre):
    _sesion_con(controlador, inv_origen())
    controlador.asegurar_storage_mv(widget_padre)
    assert controlador.dialogos == []


def test_revisar_recordados_ofrece_elegir_otro_para_cada_no_disponible(controlador, widget_padre):
    inv = inv_origen(extra_images=True)
    _sesion_con(controlador, inv, storage_mv="fantasma")
    controlador.enlazar(
        __import__("proxlaunch").interfaz.vistas.selector_origen.SelectorOrigen(), lambda: "pve"
    )
    controlador.revisar_recordados(widget_padre)
    assert len(controlador.dialogos) >= 1


# --- V-O26: el resumen se bloquea si el recordado ya no existe -


def test_v_o26_con_iso_o_importar_el_recordado_inexistente_es_error_y_con_vacia_solo_aviso(
    controlador,
):
    _sesion_con(controlador, inv_origen(extra_images=True), storage_mv="fantasma")
    _, problemas = controlador.resolver(cfg_iso())
    v26 = [p for p in problemas if p.codigo == "V-O26"]
    assert v26 and v26[0].severidad == Severidad.ERROR
    from .apoyo_mvp4 import cfg_base

    _, problemas_vacia = controlador.resolver(cfg_base())
    v26 = [p for p in problemas_vacia if p.codigo == "V-O26"]
    assert v26 and v26[0].severidad == Severidad.AVISO


def test_v_o26_sin_recordado_no_hay_regla(controlador):
    _sesion_con(controlador, inv_origen(extra_images=True))
    _, problemas = controlador.resolver(cfg_iso())
    assert not [p for p in problemas if p.codigo == "V-O26"]


def test_v_o27_con_una_transferencia_activa_se_bloquea_crear(controlador, monkeypatch):
    _sesion_con(controlador, inv_origen())
    monkeypatch.setattr(
        ControladorOrigen, "transferencia_activa", property(lambda self: True), raising=True
    )
    _, problemas = controlador.resolver(cfg_iso())
    assert any(p.codigo == "V-O27" and p.severidad == Severidad.ERROR for p in problemas)


def test_el_origen_de_una_configuracion_vacia_no_necesita_catalogo(controlador):
    _sesion_con(controlador, inv_origen())
    from .apoyo_mvp4 import cfg_base

    cfg, problemas = controlador.resolver(cfg_base())
    assert cfg.origen == OrigenSO.DISCO_VACIO
    assert problemas == []


def test_helpers_de_storage_sin_usar_para_cubrir_clasificacion_por_contenido():
    """CA-O04.2: el contenido manda, no el nombre del storage."""
    from proxlaunch.nucleo.origen.storages import candidatos

    inv = inv_origen()
    inv.storages_todos["pve"] += (storage_sin("iso", "images"), storage_sin("discos", "iso"))
    ids_iso = [s.id for s in candidatos(inv, Contenido.ISO, "pve")]
    assert "discos" in ids_iso and "iso" not in ids_iso
