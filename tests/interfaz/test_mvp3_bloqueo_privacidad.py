"""Bloqueo de la edición con un lote en ejecución (CA-P05.6, CA-L10.9, CA-G02.4) y privacidad
(RNF-M03): ningún secreto, host ni usuario en los archivos escritos, los mensajes ni el registro.

El «centinela» es un valor único colocado donde un descuido podría filtrarlo (el cliente de la
sesión, el llavero, el usuario efectivo, columnas de credenciales de un CSV). Después de recorrer
los flujos de archivos se busca ese valor en todo lo que la aplicación emitió.
"""

from __future__ import annotations

import csv
import io
import logging
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from proxlaunch.interfaz import archivos_ui
from proxlaunch.interfaz.dialogos.guardar_lote import DialogoGuardarLote
from proxlaunch.interfaz.dialogos.guardar_perfil import DialogoGuardarPerfil
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.interfaz.dialogos.perfiles_maquina import DialogoPerfilesMaquina, _DialogoExportar

from . import test_ventana_principal as _base
from .apoyo import ClienteLoteFalso, CreacionPorVmid, perfil, sesion_falsa
from .apoyo_mvp3 import (
    ENCABEZADO_CSV,
    conectar3,
    csv_valido,
    definicion_homogenea,
    escribir,
    escribir_csv,
    escribir_lote_guardado,
    pulsar_boton,
    textos_de_avisos,
    todos_los_textos,
)
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .apoyo_ventana_lote import crear_lote, esperar_fin
from .test_ventana_principal import conectar, esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

SECRETO = "SENTINELA-token-3f9a1c77"
CLAVE_CSV = "SENTINELA-csv-clave-8b21"
HOST = "host-sentinela.lab.invalid"
USUARIO = "sentinela-usuario@pve!tok"


class ClienteConSecreto(ClienteLoteFalso):
    """Cliente falso cuyo ``repr`` lleva el secreto: si algo lo serializara, se vería."""

    token = SECRETO

    def __repr__(self) -> str:
        return f"ClienteConSecreto(token={self.token})"

    __str__ = __repr__


def ver_resumen_filas(qtbot, v) -> None:
    qtbot.waitUntil(lambda: v.panel_filas.boton_resumen.isEnabled(), timeout=3000)
    v.panel_filas.boton_resumen.click()
    qtbot.waitUntil(lambda: v.resumen_lote.plan is not None and not v._planificando, timeout=5000)


# --- Bloqueo con un lote en ejecución ----------------------------------------------------------


@pytest.fixture
def lote_por_filas_en_ejecucion(qtbot, entorno3, limpieza, modales, archivos, tmp_path):
    """Lote importado de un CSV con la primera máquina «en vuelo» (puerta cerrada)."""
    cliente = conectar3(qtbot, entorno3)
    puerta = threading.Event()
    entorno3.creacion = CreacionPorVmid(puertas={101: puerta})
    from .test_mvp3_filas_csv import importar

    importar(qtbot, entorno3, modales, archivos, csv_valido(tmp_path / "c.csv", 3))
    v = entorno3.ventana
    ver_resumen_filas(qtbot, v)
    crear_lote(qtbot, v)
    qtbot.waitUntil(lambda: v._lote_en_curso, timeout=4000)
    return v, cliente, puerta


def test_ca_l10_9_con_el_lote_en_ejecucion_todo_lo_editable_queda_bloqueado(
    lote_por_filas_en_ejecucion,
):
    v, _, _ = lote_por_filas_en_ejecucion
    p = v.panel_filas
    for boton in (p.boton_resumen, p.boton_quitar, p.boton_salir, p.boton_revisar):
        assert not boton.isEnabled(), boton.text()
    assert not v.bloque_lote.isEnabled() and not v.formulario.isEnabled()
    assert not v.selector_perfil.combo.isEnabled()
    assert not v.panel_no_encaja.isEnabled()
    for accion in (
        v._accion_abrir_lote,
        v._accion_importar_csv,
        v._accion_guardar_perfil,
        v._accion_administrar_perfiles,
    ):
        assert not accion.isEnabled(), accion.text()


def test_ca_g02_4_guardar_lote_sigue_disponible_y_no_afecta_la_ejecucion(
    qtbot, lote_por_filas_en_ejecucion, modales, archivos, tmp_path
):
    v, _, puerta = lote_por_filas_en_ejecucion
    assert v._accion_guardar_lote.isEnabled() and v._accion_guardar_lote_como.isEnabled()
    destino = tmp_path / "durante.proxlaunch-lote.json"
    archivos.guardar.append(destino)
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("durante"), d.boton_aceptar.click())
    )
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    assert v._lote_en_curso  # sigue ejecutándose
    puerta.set()
    esperar_fin(qtbot, v)
    assert set(_estados(v)) == {"ok"}


def _estados(v) -> list[str]:
    return [e.estado.value for e in v._lote.libro.instantanea()]


def test_con_el_lote_en_ejecucion_las_acciones_de_edicion_no_hacen_nada(
    lote_por_filas_en_ejecucion,
):
    v, _, _ = lote_por_filas_en_ejecucion
    antes = v._definicion_actual()
    v._quitar_filas((0,))
    v._salir_de_por_filas()
    v._asignar_automaticamente((0,))
    v._revisar_filas()
    v._sustituir_desajuste(None, None)
    assert v._definicion_actual() == antes and v.bloque_lote.es_por_filas


def test_el_lote_en_ejecucion_no_dispara_escrituras_por_las_acciones_bloqueadas(
    lote_por_filas_en_ejecucion,
):
    v, cliente, _ = lote_por_filas_en_ejecucion
    n = len(v._definicion_actual().filas)
    v._importar_csv()
    v._abrir_lote()
    assert len(v._definicion_actual().filas) == n
    assert not cliente.eliminados  # nada se deshizo ni se borró al pulsar acciones bloqueadas


# --- Centinela: ningún secreto en archivos, mensajes ni registro -------------------------------


@pytest.fixture
def entorno_centinela(qtbot, entorno3, llavero, modales, archivos, tmp_path, caplog):
    """Sesión con host, usuario y cliente que contienen centinelas; todo en ``tmp_path``."""
    caplog.set_level(logging.DEBUG)
    llavero.set_password("proxlaunch", "p1", SECRETO)
    cliente = ClienteConSecreto()
    entorno3.cliente = cliente
    sesion = sesion_falsa(perfil("p1", "Laboratorio", hosts=(HOST,)), cliente=cliente)
    sesion = replace(sesion, usuario_efectivo=USUARIO)
    conectar(qtbot, entorno3, sesion)
    esperar_validacion(qtbot, entorno3.ventana)
    (tmp_path / "entradas").mkdir()
    (tmp_path / "salidas").mkdir()
    return entorno3, cliente


def _csv_con_credenciales(tmp_path: Path) -> Path:
    encabezado = [*ENCABEZADO_CSV, "token", "contraseña", "password"]
    base = ["2 GiB", "20 GiB", "local-lvm", "vmbr0", "", ""]
    return escribir_csv(
        tmp_path / "entradas" / "con-claves.csv",
        [
            encabezado,
            ["a", 2, *base, CLAVE_CSV, CLAVE_CSV, CLAVE_CSV],
            ["b", 4, *base, CLAVE_CSV, CLAVE_CSV, CLAVE_CSV],
            ["c-mala", "abc", *base, CLAVE_CSV, CLAVE_CSV, CLAVE_CSV],
        ],
    )


def _recorrer_flujos(qtbot, env, modales, archivos, tmp_path, monkeypatch) -> list[str]:
    """Ejecuta todos los flujos de archivos del MVP 3 y devuelve los textos que se mostraron."""
    from PySide6.QtWidgets import QMessageBox

    v = env.ventana
    salidas = tmp_path / "salidas"
    env.creacion = CreacionPorVmid()
    visto: list[str] = []

    # 1. Importar un CSV con columnas de credenciales y una fila mala (se importan las buenas).
    archivos.abrir.append(_csv_con_credenciales(tmp_path))
    errores = salidas / "errores.csv"

    def _asistente(d: DialogoImportarCsv) -> None:
        qtbot.waitUntil(lambda: not d.ocupado and d.resultado is not None, timeout=5000)
        d.tabla.selectRow(2)
        visto.append(todos_los_textos(d))
        visto.append(d.detalle.toPlainText())
        archivos.guardar.append(errores)
        d.boton_errores.click()
        qtbot.waitUntil(errores.exists, timeout=3000)
        qtbot.waitUntil(lambda: "Se guardó" in d.estado_operacion.text(), timeout=3000)
        d.boton_copiar.click()
        visto.append(QApplication.clipboard().text())
        d.boton_continuar.click()

    modales.responder(DialogoImportarCsv, _asistente)
    modales.pulsar(QMessageBox, "Importar esas filas")
    v._accion_importar_csv.trigger()
    qtbot.waitUntil(lambda: v.bloque_lote.es_por_filas, timeout=5000)
    esperar_validacion(qtbot, v)
    visto.append(textos_de_avisos(v))

    # 2. Resumen, creación (con el servicio falso) e informe CSV.
    ver_resumen_filas(qtbot, v)
    visto.append(todos_los_textos(v.resumen_lote))
    crear_lote(qtbot, v)
    esperar_fin(qtbot, v)
    archivos.guardar.append(salidas / "informe.csv")
    v._accion_informe_csv.trigger()
    qtbot.waitUntil((salidas / "informe.csv").exists, timeout=3000)

    # 3. Guardar el lote por filas.
    archivos.guardar.append(salidas / "filas.proxlaunch-lote.json")
    modales.responder(
        DialogoGuardarLote, lambda d: (d.campo_nombre.setText("filas"), d.boton_aceptar.click())
    )
    v._accion_guardar_lote.trigger()
    qtbot.waitUntil((salidas / "filas.proxlaunch-lote.json").exists, timeout=3000)

    # 4. Plantilla CSV.
    monkeypatch.setattr(archivos_ui, "pedir_separador_plantilla", lambda parent: ";")
    archivos.guardar.append(salidas / "plantilla.csv")
    v._accion_plantilla_csv.trigger()
    qtbot.waitUntil((salidas / "plantilla.csv").exists, timeout=3000)

    # 5. Perfil de máquina: guardar y exportar.
    modales.responder(
        DialogoGuardarPerfil,
        lambda d: (d.campo_nombre.setText("Perfil de prueba"), pulsar_boton(d, "Guardar perfil")),
    )
    v.panel_filas.boton_salir.click()
    esperar_validacion(qtbot, v)
    escribir(v.formulario.cores, "3")
    esperar_validacion(qtbot, v)
    v._accion_guardar_perfil.trigger()
    gestor = DialogoPerfilesMaquina(v._almacen_perfiles, v._lanzador, app_version="0.1.0")
    qtbot.addWidget(gestor)
    gestor.seleccionar(v.selector_perfil.perfil_actual_id or "fabrica.minimo")
    archivos.guardar.append(salidas / "perfiles.proxlaunch-perfiles.json")
    modales.responder(_DialogoExportar, lambda d: d.boton_exportar.click())
    gestor.boton_exportar.click()
    qtbot.waitUntil((salidas / "perfiles.proxlaunch-perfiles.json").exists, timeout=3000)
    qtbot.waitUntil(lambda: "exportó" in gestor.estado.text(), timeout=3000)
    visto.append(todos_los_textos(gestor))

    # 6. Un lote homogéneo guardado y vuelto a abrir.
    homogeneo = escribir_lote_guardado(
        salidas / "homogeneo.proxlaunch-lote.json", definicion_homogenea()
    )
    archivos.abrir.append(homogeneo)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == homogeneo, timeout=4000)
    visto.append(textos_de_avisos(v))
    return visto


def _todo_lo_emitido(env, visto: list[str], caplog) -> str:
    v = env.ventana
    partes = [*visto, todos_los_textos(v, solo_visibles=False), v.statusBar().currentMessage()]
    partes.append(caplog.text)
    return "\n".join(partes)


def test_rnf_m03_ningun_archivo_escrito_contiene_secretos_ni_host_ni_usuario(
    qtbot, entorno_centinela, modales, archivos, tmp_path, caplog, monkeypatch
):
    env, _ = entorno_centinela
    _recorrer_flujos(qtbot, env, modales, archivos, tmp_path, monkeypatch)
    escritos = [f for f in tmp_path.rglob("*") if f.is_file() and "entradas" not in f.parts]
    assert any(f.name == "informe.csv" for f in escritos)  # se recorrió el flujo
    assert {f.name for f in (tmp_path / "salidas").iterdir()} >= {
        "errores.csv", "informe.csv", "filas.proxlaunch-lote.json", "plantilla.csv",
        "perfiles.proxlaunch-perfiles.json",
    }  # fmt: skip
    for f in escritos:
        contenido = f.read_bytes().decode("utf-8", errors="replace")
        for centinela in (SECRETO, CLAVE_CSV, HOST, USUARIO):
            assert centinela not in contenido, f"{centinela!r} en {f.relative_to(tmp_path)}"


def test_rnf_m03_ningun_mensaje_ni_registro_contiene_secretos(
    qtbot, entorno_centinela, modales, archivos, tmp_path, caplog, monkeypatch
):
    env, _ = entorno_centinela
    visto = _recorrer_flujos(qtbot, env, modales, archivos, tmp_path, monkeypatch)
    todo = _todo_lo_emitido(env, visto, caplog)
    for centinela in (SECRETO, CLAVE_CSV):
        assert centinela not in todo, centinela
    for caja in modales.textos_vistos:
        assert SECRETO not in caja and CLAVE_CSV not in caja


def test_rnf_m03_el_csv_de_errores_no_lleva_las_columnas_de_credenciales_y_es_reimportable(
    qtbot, entorno_centinela, modales, archivos, tmp_path, monkeypatch
):
    env, _ = entorno_centinela
    _recorrer_flujos(qtbot, env, modales, archivos, tmp_path, monkeypatch)
    texto = (tmp_path / "salidas" / "errores.csv").read_text(encoding="utf-8-sig")
    # El núcleo escribe todo entre comillas (QUOTE_ALL): se lee con el módulo csv, no a mano.
    filas_csv = list(csv.reader(io.StringIO(texto), delimiter=";"))
    encabezado = ";".join(filas_csv[0]).lower()
    for prohibida in ("token", "contraseña", "password", "clave"):
        assert prohibida not in encabezado
    assert len(filas_csv) == 2 and filas_csv[1][0] == "c-mala"  # solo la fila con error
    assert texto.splitlines()[1].startswith('"c-mala";')  # formato real: todo entrecomillado
    visto: dict[str, object] = {}

    def _ver(d: DialogoImportarCsv) -> None:
        qtbot.waitUntil(lambda: not d.ocupado and d.resultado is not None, timeout=5000)
        visto["filas"] = len(d.resultado.filas)
        visto["errores"] = d.hay_errores
        d.reject()

    archivos.abrir.append(tmp_path / "salidas" / "errores.csv")
    modales.responder(DialogoImportarCsv, _ver)
    env.ventana.panel_filas.boton_salir.click()  # el lote ya está en curso/terminado: se vuelve
    env.ventana._accion_importar_csv.trigger()
    assert visto == {"filas": 1, "errores": True}  # sigue siendo la fila mala: reimportable


def test_rnf_m03_el_lote_guardado_de_un_lote_cargado_con_credenciales_no_las_conserva(
    qtbot, entorno_centinela, modales, archivos, tmp_path
):
    import json

    env, _ = entorno_centinela
    v = env.ventana
    ruta = escribir_lote_guardado(
        tmp_path / "entradas" / "c.proxlaunch-lote.json", definicion_homogenea()
    )
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["homogeneo"]["token"] = CLAVE_CSV
    datos["password"] = CLAVE_CSV
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    archivos.abrir.append(ruta)
    v._accion_abrir_lote.trigger()
    qtbot.waitUntil(lambda: v._ruta_lote == ruta, timeout=3000)
    assert CLAVE_CSV not in textos_de_avisos(v)
    assert "credencial" in v.panel_avisos_archivo.texto  # E-M16: se avisa sin repetir el valor
    destino = tmp_path / "salidas" / "reescrito.proxlaunch-lote.json"
    archivos.guardar.append(destino)
    modales.responder(
        DialogoGuardarLote,
        lambda d: (d.campo_nombre.setText("reescrito"), d.boton_aceptar.click()),
    )
    v._accion_guardar_lote_como.trigger()
    qtbot.waitUntil(destino.exists, timeout=3000)
    assert CLAVE_CSV not in destino.read_text(encoding="utf-8")


def test_los_widgets_de_la_ventana_no_exponen_el_secreto_ni_en_tooltips(qtbot, entorno_centinela):
    env, _ = entorno_centinela
    v = env.ventana
    textos: list[str] = []
    for w in [v, *v.findChildren(QWidget)]:
        textos += [w.toolTip(), w.accessibleName(), w.accessibleDescription()]
    assert SECRETO not in "\n".join(textos)
