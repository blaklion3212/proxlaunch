"""Lotes guardados en la interfaz (MVP 3): guardar, abrir, revalidar contra el servidor y el panel
«Este lote no encaja en este servidor» (RF-G01..G07, CA-G02.x, CA-G03.x, CA-G04.x, CA-G06.x).

Cada prueba parte de los criterios de aceptación de docs/requisitos/mvp3.md, no del código.
Ningún diálogo modal real; los archivos viven en ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox

from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.nucleo.lote.modelos import ModoDestino
from proxlaunch.nucleo.lotes_guardados.revalidacion import TipoDesajuste

from . import test_ventana_principal as _base
from .apoyo import perfil, sesion_falsa
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    conectar3,
    definicion_filas,
    definicion_homogenea,
    escribir,
    escribir_lote_guardado,
    hubo_escritura,
    inventario_cluster_otros_nodos,
    pulsar_boton,
    textos_de_avisos,
    todos_los_textos,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_ventana_principal import conectar, esperar_validacion

entorno = _base.entorno  # fixture base de la ventana


def sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


@pytest.fixture
def conectado(qtbot, entorno3):
    """Ventana conectada con un cliente falso; devuelve (ventana, cliente)."""
    cliente = conectar3(qtbot, entorno3)
    return entorno3.ventana, cliente


def abrir_lote(qtbot, v, archivos, ruta: Path) -> None:
    """«Lote > Abrir lote…» con la ruta elegida y espera a que el lote quede cargado."""
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == ruta or v._errores_sesion != [], timeout=4000)
    esperar_validacion(qtbot, v)


def guardar_lote_por_menu(qtbot, v, modales, archivos, destino: Path | None, **dialogo) -> None:
    """«Lote > Guardar lote…»: el diálogo del nombre y luego la ruta del sistema."""

    def _aceptar(d: DialogoGuardarLote) -> None:
        # El formulario recién abierto no trae nombre: el usuario lo escribe en el diálogo.
        d.campo_nombre.setText(dialogo.get("nombre") or d.campo_nombre.text() or "lote de prueba")
        if dialogo.get("sobrescribir"):
            d.radio_sobrescribir.click()
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _aceptar)
    archivos.guardar.append(destino)
    v._accion_guardar_lote.trigger()


def combos_con_texto(raiz, fragmento: str) -> list[str]:
    return [c.currentText() for c in raiz.findChildren(QComboBox) if fragmento in c.currentText()]


# --- Menús y habilitación ----------------------------------------------------------------------


def test_el_menu_lote_ofrece_las_acciones_del_mvp3(qtbot, entorno3):
    v = entorno3.ventana
    menu = next(a.menu() for a in v.menuBar().actions() if a.text().replace("&", "") == "Lote")
    textos = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert textos == [
        "Abrir lote…",
        "Guardar lote…",
        "Guardar lote como…",
        "Importar desde CSV…",
        "Descargar plantilla CSV…",
        "Guardar el informe del lote como CSV…",
    ]


def test_el_menu_perfiles_ofrece_guardar_y_administrar(qtbot, entorno3):
    v = entorno3.ventana
    menu = next(a.menu() for a in v.menuBar().actions() if a.text().replace("&", "") == "Perfiles")
    assert [a.text() for a in menu.actions()] == [
        "Guardar como perfil de máquina…",
        "Administrar perfiles…",
    ]


def test_sin_conexion_no_se_puede_abrir_ni_guardar_un_lote_pero_si_bajar_la_plantilla(entorno3):
    v = entorno3.ventana
    assert not v._accion_abrir_lote.isEnabled()
    assert not v._accion_guardar_lote.isEnabled()
    assert not v._accion_guardar_lote_como.isEnabled()
    assert v._accion_plantilla_csv.isEnabled()  # P-M08: funciona sin conexión


def test_con_conexion_se_habilitan_las_acciones_de_archivo(qtbot, conectado):
    v, _ = conectado
    for accion in (v._accion_abrir_lote, v._accion_guardar_lote, v._accion_guardar_lote_como):
        assert accion.isEnabled()
    assert not v._accion_informe_csv.isEnabled()  # aún no hay un lote que informar


# --- Guardar un lote (RF-G02) ------------------------------------------------------------------


def test_ca_g02_2_guardar_propone_el_prefijo_como_nombre_y_escribe_el_archivo(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, cliente = conectado
    escribir(v.bloque_lote.cantidad, "3")
    escribir(v.bloque_lote.prefijo, "web")
    esperar_validacion(qtbot, v)
    visto: dict[str, str] = {}
    destino = tmp_path / "web.proxlaunch-lote.json"

    def _ver(d: DialogoGuardarLote) -> None:
        visto["nombre"] = d.campo_nombre.text()
        visto["boton"] = d.boton_aceptar.text()
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _ver)
    archivos.guardar.append(destino)
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    # El archivo se escribe en un hilo y el aviso llega después por una señal en cola: se espera
    # al mensaje antes de leer la barra de estado (evita la carrera con la máquina cargada).
    qtbot.waitUntil(
        lambda: v.statusBar().currentMessage() == "Lote guardado en «web.proxlaunch-lote.json»",
        timeout=3000,
    )
    assert visto == {"nombre": "web", "boton": "Elegir dónde guardar…"}
    assert archivos.pedidos_guardar[0][1] == "web.proxlaunch-lote.json"
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["formato"] == "proxlaunch.lote" and datos["homogeneo"]["cantidad"] == 3
    assert v.statusBar().currentMessage() == "Lote guardado en «web.proxlaunch-lote.json»"
    assert not hubo_escritura(cliente)


def test_ca_g02_3_el_archivo_no_lleva_plan_ni_servidor_ni_usuario(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    destino = tmp_path / "l.proxlaunch-lote.json"
    guardar_lote_por_menu(qtbot, v, modales, archivos, destino)
    qtbot.waitUntil(destino.exists, timeout=3000)
    texto = destino.read_text(encoding="utf-8")
    for prohibido in ("10.0.0.5", "ana@pve", "Laboratorio", "plan", "upid", "id_lote", "libro"):
        assert f'"{prohibido}"' not in texto and prohibido not in texto.replace("version_", ""), (
            prohibido
        )


def test_ca_g02_2_un_nombre_vacio_no_deja_aceptar(qtbot, conectado, modales, archivos):
    v, _ = conectado
    vistos: dict[str, object] = {}

    def _ver(d: DialogoGuardarLote) -> None:
        d.campo_nombre.setText("   ")
        vistos["habilitado"] = d.boton_aceptar.isEnabled()
        d.reject()

    modales.responder(DialogoGuardarLote, _ver)
    v._accion_guardar_lote.trigger()
    assert vistos["habilitado"] is False


def test_ca_g02_1_un_lote_con_errores_de_validacion_se_puede_guardar_como_borrador(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    escribir(v.formulario.cores, "0")  # fuera de rango: error de capa 1, pero numérico
    esperar_validacion(qtbot, v)
    assert v._hay_problemas
    destino = tmp_path / "borrador.proxlaunch-lote.json"
    vistos: dict[str, str] = {}

    def _ver(d: DialogoGuardarLote) -> None:
        vistos["aviso"] = d.aviso_problemas.text()
        d.campo_nombre.setText("borrador")
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _ver)
    archivos.guardar.append(destino)
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    assert vistos["aviso"] == "El lote tiene problemas; se comprobará otra vez al abrirlo."


def test_ca_g02_1_un_campo_no_numerico_bloquea_el_guardado_y_dice_cual(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    escribir(v.formulario.cores, "abc")
    v._accion_guardar_lote.trigger()
    assert modales.de_clase(DialogoGuardarLote) == []
    assert archivos.pedidos_guardar == []
    assert "no es un número" in textos_de_avisos(v)
    assert "No se puede guardar el lote" in v.statusBar().currentMessage()


def test_guardar_con_la_ruta_del_sistema_cancelada_no_escribe_nada(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    guardar_lote_por_menu(qtbot, v, modales, archivos, None)
    qtbot.wait(100)
    assert list(tmp_path.glob("*.json")) == []
    assert not v.statusBar().currentMessage().startswith("Lote guardado")


def test_ca_g02_6_un_fallo_de_escritura_se_dice_en_llano_y_no_cambia_la_huella(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    huella = v._huella_guardada
    bloqueo = tmp_path / "es-un-archivo"
    bloqueo.write_text("x")
    imposible = bloqueo / "no-cabe.proxlaunch-lote.json"  # la «carpeta» es un archivo
    guardar_lote_por_menu(qtbot, v, modales, archivos, imposible)
    qtbot.waitUntil(lambda: "No se pudo guardar" in textos_de_avisos(v), timeout=3000)
    assert v._huella_guardada == huella
    assert v._ruta_lote is None


def test_ca_g03_6_tras_abrir_un_lote_se_ofrece_sobrescribir_y_pide_confirmar_con_foco_en_cancelar(
    qtbot, conectado, modales, archivos, tmp_path
):
    from PySide6.QtWidgets import QMessageBox

    v, _ = conectado
    origen = escribir_lote_guardado(tmp_path / "o.proxlaunch-lote.json", definicion_homogenea())
    abrir_lote(qtbot, v, archivos, origen)
    antes = sha(origen)
    escribir(v.bloque_lote.cantidad, "4")  # lote modificado
    esperar_validacion(qtbot, v)
    visto: dict[str, object] = {}

    def _caja(caja: QMessageBox) -> None:
        visto["defecto"] = caja.defaultButton().text()
        visto["texto"] = caja.text()
        pulsar_boton(caja, "Cancelar")

    modales.responder(QMessageBox, _caja)

    def _dialogo(d: DialogoGuardarLote) -> None:
        visto["radio"] = d.radio_sobrescribir.isVisibleTo(d)
        d.radio_sobrescribir.click()
        visto["boton"] = d.boton_aceptar.text()
        d.boton_aceptar.click()

    modales.responder(DialogoGuardarLote, _dialogo)
    v._accion_guardar_lote.trigger()
    qtbot.wait(100)
    assert visto["radio"] is True and visto["boton"] == "Sobrescribir"
    assert visto["defecto"] == "Cancelar" and "o.proxlaunch-lote.json" in str(visto["texto"])
    assert sha(origen) == antes  # Cancelar: el archivo no se tocó
    assert archivos.pedidos_guardar == []  # y no se pidió otra ruta


def test_ca_g03_6_sobrescribir_confirmado_reemplaza_el_archivo_de_origen(
    qtbot, conectado, modales, archivos, tmp_path
):
    from PySide6.QtWidgets import QMessageBox

    v, _ = conectado
    origen = escribir_lote_guardado(tmp_path / "o.proxlaunch-lote.json", definicion_homogenea())
    abrir_lote(qtbot, v, archivos, origen)
    antes = sha(origen)
    escribir(v.bloque_lote.cantidad, "4")
    esperar_validacion(qtbot, v)
    modales.pulsar(QMessageBox, "Sobrescribir")
    guardar_lote_por_menu(qtbot, v, modales, archivos, None, sobrescribir=True)
    qtbot.waitUntil(lambda: sha(origen) != antes, timeout=3000)
    assert json.loads(origen.read_text(encoding="utf-8"))["homogeneo"]["cantidad"] == 4
    assert archivos.pedidos_guardar == []  # no hubo diálogo del sistema: se escribe en el origen


def test_ca_g03_6_guardar_como_nuevo_no_toca_el_origen(
    qtbot, conectado, modales, archivos, tmp_path
):
    v, _ = conectado
    origen = escribir_lote_guardado(tmp_path / "o.proxlaunch-lote.json", definicion_homogenea())
    abrir_lote(qtbot, v, archivos, origen)
    antes = sha(origen)
    nuevo = tmp_path / "copia.proxlaunch-lote.json"
    guardar_lote_por_menu(qtbot, v, modales, archivos, nuevo)  # radio por defecto: archivo nuevo
    qtbot.waitUntil(nuevo.exists, timeout=3000)
    assert sha(origen) == antes


def test_guardar_como_nunca_ofrece_sobrescribir(qtbot, conectado, modales, archivos, tmp_path):
    v, _ = conectado
    origen = escribir_lote_guardado(tmp_path / "o.proxlaunch-lote.json", definicion_homogenea())
    abrir_lote(qtbot, v, archivos, origen)
    visto: dict[str, bool] = {}

    def _ver(d: DialogoGuardarLote) -> None:
        visto["radio"] = d.radio_sobrescribir.isVisibleTo(d)
        d.reject()

    modales.responder(DialogoGuardarLote, _ver)
    v._accion_guardar_lote_como.trigger()
    assert visto["radio"] is False


# --- Abrir un lote (RF-G03, RF-G06) ------------------------------------------------------------


def test_ca_g03_2_abrir_un_lote_no_crea_nada_y_deja_el_resumen_sin_generar(
    qtbot, conectado, archivos, tmp_path
):
    v, cliente = conectado
    ruta = escribir_lote_guardado(tmp_path / "a.proxlaunch-lote.json", definicion_homogenea(3))
    abrir_lote(qtbot, v, archivos, ruta)
    assert v.statusBar().currentMessage() == "Lote «lote de prueba» cargado"
    assert v.bloque_lote.cantidad_valor() == 3 and v.bloque_lote.patron().prefijo == "web"
    assert v.resumen_lote.plan is None and not v.resumen_lote.puede_crear
    assert v._lote is None and not v._creando and not v._planificando
    assert not hubo_escritura(cliente)
    assert not any(ll[0] in ("vmid_libre", "proximo_vmid") for ll in cliente.llamadas)  # no reserva


def test_ca_g03_1_abrir_reemplaza_plantilla_y_bloque_de_lote(qtbot, conectado, archivos, tmp_path):
    v, _ = conectado
    d = definicion_homogenea(5, "db", nodo="pve3")
    d.plantilla.cores = 4
    ruta = escribir_lote_guardado(tmp_path / "a.proxlaunch-lote.json", d)
    abrir_lote(qtbot, v, archivos, ruta)
    assert v.formulario.cores.text() == "4"
    assert v.bloque_lote.cantidad_valor() == 5
    assert v.bloque_lote.destino().nodos == ("pve3",)


def test_abrir_cancelado_en_el_selector_de_archivos_no_cambia_nada(qtbot, conectado, archivos):
    v, _ = conectado
    antes = v.formulario.configuracion()
    archivos.abrir.append(None)
    v._accion_abrir_lote.trigger()
    qtbot.wait(100)
    assert v.formulario.configuracion() == antes and v._ruta_lote is None


def test_ca_g06_1_un_archivo_danado_no_cambia_el_formulario_ni_se_modifica(
    qtbot, conectado, archivos, tmp_path
):
    v, cliente = conectado
    malo = tmp_path / "malo.proxlaunch-lote.json"
    malo.write_text('{"formato": "proxlaunch.lote", "version_formato": 1, "tipo": ', "utf-8")
    antes_cfg, antes_sha = v.formulario.configuracion(), sha(malo)
    abrir_lote(qtbot, v, archivos, malo)
    qtbot.waitUntil(lambda: "dañado" in textos_de_avisos(v), timeout=3000)
    assert v.formulario.configuracion() == antes_cfg and v._ruta_lote is None
    assert sha(malo) == antes_sha
    assert not hubo_escritura(cliente)


def test_ca_g06_6_un_archivo_de_perfiles_abierto_como_lote_dice_que_parece_de_perfiles(
    qtbot, conectado, archivos, tmp_path
):
    from proxlaunch.nucleo.perfiles_maquina.formato import exportar_perfiles

    v, _ = conectado
    ruta = tmp_path / "perfiles.json"
    exportar_perfiles(ruta, v._almacen_perfiles.todos()[:1], con_pistas=False, app_version="0.1.0")
    abrir_lote(qtbot, v, archivos, ruta)
    qtbot.waitUntil(lambda: "Parece un archivo de perfiles" in textos_de_avisos(v), timeout=3000)


def test_ca_g06_6_la_pista_indica_que_hay_que_usar_importar_perfiles(
    qtbot, conectado, archivos, tmp_path
):
    """CA-G06.6 pide la pista «Parece un archivo de perfiles; usa «Importar perfiles»»."""
    from proxlaunch.nucleo.perfiles_maquina.formato import exportar_perfiles

    v, _ = conectado
    ruta = tmp_path / "perfiles.json"
    exportar_perfiles(ruta, v._almacen_perfiles.todos()[:1], con_pistas=False, app_version="0.1.0")
    abrir_lote(qtbot, v, archivos, ruta)
    qtbot.waitUntil(lambda: "Parece un archivo de perfiles" in textos_de_avisos(v), timeout=3000)
    assert "Importar perfiles" in textos_de_avisos(v)


def test_ca_g03_4_un_archivo_con_campos_desconocidos_se_carga_y_avisa_en_un_panel_cerrable(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    ruta = escribir_lote_guardado(tmp_path / "a.proxlaunch-lote.json", definicion_homogenea(3))
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["campo_inventado"] = "valor"
    datos["homogeneo"]["token"] = "no-debe-usarse"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    abrir_lote(qtbot, v, archivos, ruta)
    assert v._ruta_lote == ruta  # se cargó
    assert v.panel_avisos_archivo.isVisibleTo(v) and v.panel_avisos_archivo.texto
    assert "no-debe-usarse" not in textos_de_avisos(v)
    v.panel_avisos_archivo.boton_cerrar.click()
    assert not v.panel_avisos_archivo.isVisibleTo(v)


def test_ca_g04_6_un_lote_de_una_version_mayor_de_proxmox_solo_avisa(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    ruta = escribir_lote_guardado(
        tmp_path / "a.proxlaunch-lote.json", definicion_homogenea(), version_proxmox="10.3"
    )
    abrir_lote(qtbot, v, archivos, ruta)
    texto = v.panel_avisos_archivo.texto
    assert "Proxmox 10.3" in texto and "9.2" in texto
    assert v._ruta_lote == ruta  # se cargó igual: es solo informativo


def test_ca_g06_5_un_lote_de_version_posterior_no_se_carga(qtbot, conectado, archivos, tmp_path):
    v, _ = conectado
    ruta = escribir_lote_guardado(tmp_path / "a.proxlaunch-lote.json", definicion_homogenea())
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["version_formato"] = 99
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    abrir_lote(qtbot, v, archivos, ruta)
    qtbot.waitUntil(lambda: "versión más nueva" in textos_de_avisos(v), timeout=3000)
    assert v._ruta_lote is None


def test_ca_g07_2_un_lote_por_filas_guardado_entra_directo_a_la_tabla_de_filas(
    qtbot, conectado, archivos, tmp_path
):
    v, cliente = conectado
    d = definicion_filas(
        [
            {"nombre": "web-01", "origen": 2},
            {"nombre": "web-02", "origen": 3, "vmid": 250},
            {"nombre": "db-01", "origen": 4, "nodo": "pve3"},
        ]
    )
    ruta = escribir_lote_guardado(tmp_path / "f.proxlaunch-lote.json", d, nombre="tres filas")
    abrir_lote(qtbot, v, archivos, ruta)
    assert v.bloque_lote.es_por_filas
    assert v.panel_filas.isVisibleTo(v) and not v.formulario.isVisibleTo(v)
    assert v.panel_filas.titulo == "3 máquinas del lote «tres filas»"
    assert v.panel_filas.modelo.rowCount() == 3
    assert v.resumen_lote.plan is None and not hubo_escritura(cliente)


# --- Panel «Este lote no encaja en este servidor» (RF-G04, E-M15) ------------------------------


@pytest.fixture
def lote_que_no_encaja(tmp_path):
    return escribir_lote_guardado(
        tmp_path / "x.proxlaunch-lote.json",
        definicion_homogenea(3, "web", storage="no-hay", bridge="vmbr9", nodo="pve2"),
    )


def test_ca_g04_3_el_valor_inexistente_se_muestra_con_no_existe_y_nunca_se_sustituye(
    qtbot, conectado, archivos, lote_que_no_encaja
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_que_no_encaja)
    assert combos_con_texto(v.formulario, "no-hay (no existe)")
    assert combos_con_texto(v.formulario, "vmbr9 (no existe)")
    assert v.formulario.configuracion().discos[0].storage == "no-hay"  # sin sustitución silenciosa


def test_ca_g04_3_el_panel_lista_cada_desajuste_con_usar_otro(
    qtbot, conectado, archivos, lote_que_no_encaja
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_que_no_encaja)
    p = v.panel_no_encaja
    assert p.isVisibleTo(v) and p.cantidad == 3
    tipos = {d.tipo for d in p.desajustes()}
    assert tipos == {TipoDesajuste.STORAGE, TipoDesajuste.BRIDGE, TipoDesajuste.NODO}
    assert len(p.botones_usar_otro) == 3 and all(b.isEnabled() for b in p.botones_usar_otro)
    assert [b.text() for b in p.botones_usar_otro] == ["Usar otro…"] * 3
    assert p.accessibleName() == "Este lote no encaja en este servidor"


def test_ca_g04_3_mientras_no_se_resuelva_no_se_puede_generar_el_resumen(
    qtbot, conectado, archivos, lote_que_no_encaja
):
    v, cliente = conectado
    abrir_lote(qtbot, v, archivos, lote_que_no_encaja)
    assert not v.resumen.boton_crear.isEnabled()
    assert v.resumen_lote.plan is None
    assert not hubo_escritura(cliente)


def test_ca_g04_3_usar_otro_aplica_el_valor_elegido_solo_tras_la_accion_del_usuario(
    qtbot, conectado, archivos, lote_que_no_encaja, monkeypatch
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_que_no_encaja)
    p = v.panel_no_encaja
    desajuste = next(d for d in p.desajustes() if d.tipo == TipoDesajuste.STORAGE)
    preguntas: list[object] = []

    def _elegir(d):
        preguntas.append(d)
        return d.disponibles[0]  # una alternativa que el servidor sí tiene

    monkeypatch.setattr(p, "elegir_alternativa", _elegir)
    assert v.formulario.configuracion().discos[0].storage == "no-hay"  # antes de pulsar
    p.botones_usar_otro[0].click()
    esperar_validacion(qtbot, v)
    assert len(preguntas) == 1
    assert v.formulario.configuracion().discos[0].storage == "local-lvm"
    assert TipoDesajuste.STORAGE not in {d.tipo for d in p.desajustes()}
    assert desajuste.valor == "no-hay"


def test_ca_g04_3_cancelar_la_eleccion_no_cambia_nada(
    qtbot, conectado, archivos, lote_que_no_encaja, monkeypatch
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_que_no_encaja)
    p = v.panel_no_encaja
    monkeypatch.setattr(p, "elegir_alternativa", lambda d: None)
    p.botones_usar_otro[0].click()
    assert v.formulario.configuracion().discos[0].storage == "no-hay"
    assert p.cantidad == 3


def test_ca_g04_4_pasar_a_automatico_cambia_el_destino_solo_al_pulsar(
    qtbot, conectado, archivos, lote_que_no_encaja
):
    v, _ = conectado
    abrir_lote(qtbot, v, archivos, lote_que_no_encaja)
    p = v.panel_no_encaja
    assert len(p.botones_automatico) == 1 and p.botones_automatico[0].text() == (
        "Pasar a Automático"
    )
    assert v.bloque_lote.modo_destino == ModoDestino.UN_NODO  # nada cambió solo
    p.botones_automatico[0].click()
    esperar_validacion(qtbot, v)
    assert v.bloque_lote.modo_destino == ModoDestino.AUTOMATICO
    assert TipoDesajuste.NODO not in {d.tipo for d in p.desajustes()}


def test_ca_g04_4_un_nodo_fuera_de_linea_tambien_es_desajuste(qtbot, conectado, archivos, tmp_path):
    v, _ = conectado
    ruta = escribir_lote_guardado(
        tmp_path / "n.proxlaunch-lote.json", definicion_homogenea(nodo="pve2")
    )
    abrir_lote(qtbot, v, archivos, ruta)
    nodo = [d for d in v.panel_no_encaja.desajustes() if d.tipo == TipoDesajuste.NODO]
    assert [d.valor for d in nodo] == ["pve2"]
    assert "pve2" in v.panel_no_encaja.texto_desajuste(nodo[0])


def test_ca_g05_2_un_lote_que_si_encaja_no_muestra_el_panel(qtbot, conectado, archivos, tmp_path):
    v, _ = conectado
    ruta = escribir_lote_guardado(
        tmp_path / "ok.proxlaunch-lote.json", definicion_homogenea(nodo=None)
    )
    abrir_lote(qtbot, v, archivos, ruta)
    assert not v.panel_no_encaja.isVisibleTo(v) and v.panel_no_encaja.cantidad == 0


def test_lote_por_filas_agrupa_por_valor_y_dice_que_filas_afecta(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    d = definicion_filas(
        [
            {"nombre": "a", "origen": 2},
            {"nombre": "b", "origen": 3, "storage": "no-hay"},
            {"nombre": "c", "origen": 4},
            {"nombre": "d", "origen": 5, "storage": "no-hay"},
        ]
    )
    ruta = escribir_lote_guardado(tmp_path / "f.proxlaunch-lote.json", d)
    abrir_lote(qtbot, v, archivos, ruta)
    p = v.panel_no_encaja
    assert p.cantidad == 1
    assert "Afecta a 2 máquinas" in p.texto_afectadas(p.desajustes()[0])


def test_el_panel_nombra_las_filas_con_el_mismo_numero_que_la_tabla(
    qtbot, conectado, archivos, tmp_path
):
    """La tabla dice «Fila 3» y «Fila 5» (número de origen, como en Excel); el panel de
    desajustes debe usar esos mismos números y no la posición 2 y 4 dentro del lote."""
    v, _ = conectado
    d = definicion_filas(
        [
            {"nombre": "a", "origen": 2},
            {"nombre": "b", "origen": 3, "storage": "no-hay"},
            {"nombre": "c", "origen": 4},
            {"nombre": "d", "origen": 5, "storage": "no-hay"},
        ]
    )
    ruta = escribir_lote_guardado(tmp_path / "f.proxlaunch-lote.json", d)
    abrir_lote(qtbot, v, archivos, ruta)
    p = v.panel_no_encaja
    columna_fila = [
        str(v.panel_filas.modelo.data(v.panel_filas.modelo.index(r, 0))) for r in range(4)
    ]
    assert columna_fila == ["2", "3", "4", "5"]
    texto = p.texto_afectadas(p.desajustes()[0])
    assert "3" in texto and "5" in texto and "n.º 2, 4" not in texto


def test_lote_por_filas_usar_otro_corrige_todas_las_filas_afectadas(
    qtbot, conectado, archivos, tmp_path, monkeypatch
):
    v, _ = conectado
    d = definicion_filas(
        [
            {"nombre": "a", "origen": 2, "storage": "no-hay"},
            {"nombre": "b", "origen": 3},
            {"nombre": "c", "origen": 4, "storage": "no-hay"},
        ]
    )
    ruta = escribir_lote_guardado(tmp_path / "f.proxlaunch-lote.json", d)
    abrir_lote(qtbot, v, archivos, ruta)
    p = v.panel_no_encaja
    monkeypatch.setattr(p, "elegir_alternativa", lambda d: "local")
    p.botones_usar_otro[0].click()
    esperar_validacion(qtbot, v)
    storages = [f.cfg.discos[0].storage for f in v._definicion_actual().filas]
    assert storages == ["local", "local-lvm", "local"]
    assert p.cantidad == 0 and not p.isVisibleTo(v)


# --- Cambio de servidor con un lote cargado (CA-G04.8, CA-G05.4) -------------------------------


def _cambiar_a_otro_cluster(qtbot, entorno3, v, cliente, archivos, tmp_path) -> None:
    ruta = escribir_lote_guardado(
        tmp_path / "ok.proxlaunch-lote.json", definicion_homogenea(2, "web", nodo="pve1")
    )
    abrir_lote(qtbot, v, archivos, ruta)
    assert not v.panel_no_encaja.isVisibleTo(v)
    # Se cambia a otro perfil de conexión cuyo clúster tiene otros nodos (n1, n2, n3).
    entorno3.inv = inventario_cluster_otros_nodos()
    conectar(qtbot, entorno3, sesion_falsa(perfil(id_="p2", nombre="Otro"), cliente=cliente))
    esperar_validacion(qtbot, v)


def test_ca_g05_4_cambiar_de_servidor_invalida_el_resumen_del_lote_cargado(
    qtbot, entorno3, conectado, archivos, tmp_path
):
    v, cliente = conectado
    _cambiar_a_otro_cluster(qtbot, entorno3, v, cliente, archivos, tmp_path)
    assert v.resumen_lote.plan is None and not v.resumen_lote.puede_crear
    assert not hubo_escritura(cliente)


def test_ca_g04_4_g05_3_el_nodo_que_no_existe_en_el_servidor_nuevo_es_un_error_no_una_sustitucion(
    qtbot, entorno3, conectado, archivos, tmp_path
):
    """El lote pedía «pve1»; el servidor nuevo no lo tiene. Debe salir como desajuste (con la
    opción «Pasar a Automático») y el destino del formulario no debe cambiar solo a otro nodo."""
    v, cliente = conectado
    _cambiar_a_otro_cluster(qtbot, entorno3, v, cliente, archivos, tmp_path)
    nodos_desajuste = [
        d.valor for d in v.panel_no_encaja.desajustes() if d.tipo == TipoDesajuste.NODO
    ]
    assert nodos_desajuste == ["pve1"]
    assert "pve1" in todos_los_textos(v.panel_no_encaja)
    assert v.bloque_lote.destino().nodos != ("n1",)  # no se reinterpreta en silencio
