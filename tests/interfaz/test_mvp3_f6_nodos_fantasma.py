"""Nodos elegidos que el servidor no tiene (CA-G04.1, CA-G04.3) y texto con forma de credencial.

Un nodo inexistente en «Nodos elegidos» de un lote cargado BLOQUEA «Ver resumen»/crear aunque
queden nodos válidos. En avanzado se desmarca el check «x (no existe)»; en básico los checks son de
solo lectura y «Pasar a Automático» del panel desbloquea. Ningún diálogo modal real.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QCheckBox

from proxlaunch.interfaz.textos import texto_error
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import ModoDestino
from proxlaunch.nucleo.lotes_guardados.revalidacion import TipoDesajuste
from proxlaunch.nucleo.persistencia.preferencias import Modo

from . import test_ventana_principal as _base
from .apoyo_mvp3 import archivos as archivos  # noqa: F401  (fixture)
from .apoyo_mvp3 import (
    cierre_sin_preguntar_al_terminar,
    conectar3,
    definicion_homogenea,
    escribir,
    escribir_lote_guardado,
    todos_los_textos,
)
from .apoyo_mvp3 import entorno3 as entorno3  # noqa: F401  (fixture)
from .apoyo_mvp3 import modales as modales  # noqa: F401  (fixture)
from .test_mvp3_cambios_sin_guardar import Pregunta
from .test_mvp3_cambios_sin_guardar import pregunta_real as pregunta_real  # noqa: F401  (fixture)
from .test_mvp3_f6_destino_y_reintento import NOTA_ELEGIDOS, lote_con_nodos
from .test_mvp3_lotes import abrir_lote
from .test_ventana_principal import esperar_validacion

entorno = _base.entorno  # fixture base de la ventana

TEXTO_BLOQUEO = "Este servidor no tiene uno de los nodos del lote"


@pytest.fixture
def conectado(qtbot, entorno3):
    cliente = conectar3(qtbot, entorno3)
    return entorno3.ventana, cliente


def desajustes_nodo(v) -> list[str]:
    return [d.valor for d in v.panel_no_encaja.desajustes() if d.tipo == TipoDesajuste.NODO]


def bloqueado(v) -> bool:
    return not v.resumen.boton_crear.isEnabled()


def check_de(v, nodo: str) -> QCheckBox:
    return next(c for c in list(v.bloque_lote._checks_nodos.values()) if c.text().startswith(nodo))


def cargar(qtbot, v, archivos, tmp_path: Path, nodos: tuple[str, ...]) -> None:
    abrir_lote(qtbot, v, archivos, lote_con_nodos(tmp_path / "l.proxlaunch-lote.json", nodos))


# --- (1) Bloqueo ---------------------------------------------------------------------------------


def test_ca_g04_3_un_nodo_fantasma_entre_validos_bloquea_el_resumen_y_lo_explica(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    cargar(qtbot, v, archivos, tmp_path, ("pve1", "pveX"))
    assert desajustes_nodo(v) == ["pveX"]
    assert bloqueado(v) and v.resumen_lote.plan is None
    assert TEXTO_BLOQUEO in todos_los_textos(v.resumen, solo_visibles=False)
    assert v.bloque_lote.destino().modo == ModoDestino.NODOS_ELEGIDOS  # nada cambió solo


# --- (2) y (3) Avanzado: desmarcar ---------------------------------------------------------------


def test_ca_g04_3_en_avanzado_desmarcar_el_fantasma_levanta_el_bloqueo(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    cargar(qtbot, v, archivos, tmp_path, ("pve1", "pveX"))
    v.establecer_modo(Modo.AVANZADO)
    fantasma = check_de(v, "pveX")
    assert fantasma.text() == "pveX (no existe)" and fantasma.isChecked() and fantasma.isEnabled()
    fantasma.click()
    esperar_validacion(qtbot, v)
    assert desajustes_nodo(v) == [] and not bloqueado(v)
    assert v.bloque_lote.destino().nodos == ("pve1",)
    assert TEXTO_BLOQUEO not in todos_los_textos(v.resumen)


def test_ca_g04_3_tras_desmarcar_un_refresco_del_mismo_servidor_no_lo_hace_reaparecer(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    cargar(qtbot, v, archivos, tmp_path, ("pve1", "pveX"))
    v.establecer_modo(Modo.AVANZADO)
    check_de(v, "pveX").click()
    esperar_validacion(qtbot, v)
    v.boton_actualizar.click()
    qtbot.waitUntil(lambda: not v._descubriendo, timeout=4000)
    esperar_validacion(qtbot, v)
    assert desajustes_nodo(v) == [] and not bloqueado(v)
    assert v.bloque_lote.destino().nodos == ("pve1",)
    assert not [
        c
        for c in list(v.bloque_lote._checks_nodos.values())
        if "pveX" in c.text() and c.isChecked()
    ]


# --- (4) Básico ----------------------------------------------------------------------------------


def test_ca_g04_3_en_basico_los_checks_son_de_solo_lectura_y_pasar_a_automatico_desbloquea(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    cargar(qtbot, v, archivos, tmp_path, ("pve1", "pveX"))
    checks = list(v.bloque_lote._checks_nodos.values())
    assert checks and all(not c.isEnabled() for c in checks)
    assert NOTA_ELEGIDOS in todos_los_textos(v.bloque_lote)
    fantasma = check_de(v, "pveX")
    fantasma.click()
    assert fantasma.isChecked() and bloqueado(v)  # no se puede quitar desde aquí
    (auto,) = v.panel_no_encaja.botones_automatico
    auto.click()
    esperar_validacion(qtbot, v)
    assert v.bloque_lote.modo_destino == ModoDestino.AUTOMATICO
    assert desajustes_nodo(v) == [] and not bloqueado(v)


# --- (5) Todos ausentes --------------------------------------------------------------------------


def test_ca_g04_3_con_todos_los_nodos_ausentes_bloquea_y_automatico_desbloquea(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    cargar(qtbot, v, archivos, tmp_path, ("pveX", "pveY"))
    assert sorted(desajustes_nodo(v)) == ["pveX", "pveY"] and bloqueado(v)
    for auto in list(v.panel_no_encaja.botones_automatico)[:1]:
        auto.click()
    esperar_validacion(qtbot, v)
    assert v.bloque_lote.modo_destino == ModoDestino.AUTOMATICO
    assert desajustes_nodo(v) == [] and not bloqueado(v)


def test_ca_g04_3_con_todos_ausentes_quitarlos_quita_el_desajuste_y_exige_un_nodo_valido(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    cargar(qtbot, v, archivos, tmp_path, ("pveX", "pveY"))
    v.establecer_modo(Modo.AVANZADO)
    for nodo in ("pveX", "pveY"):
        check_de(v, nodo).click()
    esperar_validacion(qtbot, v)
    assert desajustes_nodo(v) == []
    # Ya no es un desajuste, pero sin ningún nodo marcado V-L13 sigue impidiendo continuar.
    assert bloqueado(v) and TEXTO_BLOQUEO not in todos_los_textos(v.resumen, solo_visibles=False)
    assert "Elige al menos un nodo disponible." in todos_los_textos(v, solo_visibles=False)
    check_de(v, "pve1").click()  # con un nodo válido marcado se puede continuar
    esperar_validacion(qtbot, v)
    assert not bloqueado(v) and v.bloque_lote.destino().nodos == ("pve1",)


# --- (6) Un nodo ausente: sin regresión; (7) lote armado a mano ----------------------------------


def test_ca_g04_4_un_nodo_ausente_en_un_nodo_sigue_bloqueando_y_automatico_lo_resuelve(
    qtbot, conectado, archivos, tmp_path
):
    v, _ = conectado
    ruta = escribir_lote_guardado(
        tmp_path / "un.proxlaunch-lote.json", definicion_homogenea(nodo="pveX")
    )
    abrir_lote(qtbot, v, archivos, ruta)
    assert desajustes_nodo(v) == ["pveX"] and bloqueado(v)
    assert v.bloque_lote.modo_destino == ModoDestino.UN_NODO
    v.panel_no_encaja.botones_automatico[0].click()
    esperar_validacion(qtbot, v)
    assert v.bloque_lote.modo_destino == ModoDestino.AUTOMATICO and not bloqueado(v)


def test_un_lote_armado_a_mano_con_nodos_elegidos_validos_no_se_bloquea(qtbot, conectado):
    v, _ = conectado
    v.establecer_modo(Modo.AVANZADO)
    b = v.bloque_lote
    escribir(b.cantidad, "3")
    escribir(b.prefijo, "web")
    b._radio_elegidos.setChecked(True)
    esperar_validacion(qtbot, v)
    assert b.destino().modo == ModoDestino.NODOS_ELEGIDOS and b.destino().nodos
    assert desajustes_nodo(v) == [] and not bloqueado(v)


# --- (8) Texto con forma de credencial -----------------------------------------------------------

SECRETO = "ana@pve!lab=0123456789abcdef-SECRETO"


def test_cerrar_con_un_prefijo_con_forma_de_credencial_pregunta_y_cierra_sin_excepcion(
    request,
    qtbot,
    entorno3,
    modales,
    pregunta_real,  # noqa: F811
):
    conectar3(qtbot, entorno3)
    v = entorno3.ventana
    cierre_sin_preguntar_al_terminar(request, v)
    escribir(v.bloque_lote.cantidad, "2")
    escribir(v.bloque_lote.prefijo, SECRETO)
    esperar_validacion(qtbot, v)
    pregunta = Pregunta(modales, "Cancelar")
    assert v.close() is False and pregunta.veces == 1  # pregunta, sin excepción
    pregunta = Pregunta(modales, "No guardar")
    assert v.close() is True and pregunta.veces == 1


@pytest.mark.parametrize(
    ("tecnico", "legible"),
    [
        ("nombre_maquina", "nombre de la máquina"),
        ("version_proxmox", "versión de Proxmox"),
        ("descripcion", "descripción"),
        ("storage_preferido", "almacenamiento preferido"),
        ("bridge_preferido", "puente de red preferido"),
        ("storage_efi_preferido", "almacenamiento EFI preferido"),
    ],
)
def test_s_c_los_campos_nuevos_del_mapeo_se_muestran_legibles_sin_nombre_tecnico_ni_valor(
    tecnico, legible
):
    error = ErrorProxLaunch(
        CodigoError.ARCHIVO_NO_GUARDABLE,
        {"motivo": "credencial", "campo": tecnico, "valor": SECRETO},
    )
    texto = texto_error(error)
    assert f"«{legible}»" in texto
    assert tecnico not in texto and "SECRETO" not in texto and SECRETO not in texto
