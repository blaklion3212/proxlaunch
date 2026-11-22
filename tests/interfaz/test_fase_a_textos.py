"""Textos de la fase A: códigos nuevos, etapa de encendido, avisos, reglas V-A y guía de permisos.

Derivadas de docs/requisitos/fase-a.md: RF-A8.2, RF-A8.4 (presencia de textos), CA-A8.1.x en lo
que toca a la guía, y los CA que exigen que el texto nombre privilegio, ruta o versión.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import QLabel

from proxlaunch.interfaz import ayuda, textos
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Etapa
from proxlaunch.nucleo.origen.permisos import PRIVILEGIOS_OPCIONALES, ROL_PROXLAUNCH
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo import inventario_individual
from .apoyo_fase_a import estados_opciones, textos_de
from .test_mvp3_textos_accesibilidad import sin_traducir

MARCADOR = re.compile(r"\{[a-z_]+\}")

CODIGOS_NUEVOS = (
    CodigoError.OPCION_SIN_PRIVILEGIO,
    CodigoError.OPCION_SIN_VERSION,
    CodigoError.POOLS_SIN_PERMISO,
    CodigoError.POOLS_DESCONOCIDO,
    CodigoError.POOLS_ERROR,
    CodigoError.POOL_INEXISTENTE,
    CodigoError.DESCRIPCION_LARGA,
    CodigoError.ROLLBACK_PROTEGIDA,
    CodigoError.ROLLBACK_SIN_POWERMGMT,
    CodigoError.ROLLBACK_SIN_OPCIONES,
    CodigoError.ROLLBACK_APAGADO_FALLIDO,
    CodigoError.ROLLBACK_DESPROTECCION_FALLIDA,
)

PARAMS = {
    "opcion": "encender",
    "privilegio": "VM.PowerMgmt",
    "ruta": "/vms",
    "version": "9.9",
    "pool": "produccion",
    "nombre": "web-01",
    "vmid": "101",
}


def texto_de(codigo: CodigoError, **extra: str) -> str:
    return textos.texto_error(ErrorProxLaunch(codigo, {**PARAMS, **extra}))


# --- RF-A8.4: cada código nuevo tiene texto en español distinto de su código ---


@pytest.mark.parametrize("codigo", CODIGOS_NUEVOS)
def test_rf_a8_4_cada_codigo_nuevo_tiene_texto_en_espanol_distinto_de_su_codigo(codigo):
    texto = texto_de(codigo)
    assert texto.strip()
    assert texto != codigo.value and texto != str(codigo)
    assert codigo.value not in texto  # sin identificadores crudos
    assert not MARCADOR.search(texto)
    assert textos.texto_generico() != texto  # no cae en el mensaje genérico


@pytest.mark.parametrize("codigo", CODIGOS_NUEVOS)
def test_rf_a8_4_cada_codigo_nuevo_sin_parametros_no_revienta_ni_queda_vacio(codigo):
    texto = textos.texto_error(ErrorProxLaunch(codigo))
    assert texto.strip()


def test_rf_a8_4_los_textos_de_los_codigos_nuevos_son_todos_distintos():
    todos = [texto_de(c) for c in CODIGOS_NUEVOS]
    assert len(set(todos)) == len(todos)


def test_rf_a0_3_el_error_de_privilegio_de_una_opcion_nombra_privilegio_y_ruta():
    texto = texto_de(CodigoError.OPCION_SIN_PRIVILEGIO)
    assert "VM.PowerMgmt" in texto and "/vms" in texto
    assert "Encender al terminar" in texto  # el nombre llano de la opción, no «encender»


def test_rf_a0_4_el_error_de_version_nombra_la_version():
    texto = texto_de(CodigoError.OPCION_SIN_VERSION, version="8.4")
    assert "8.4" in texto and "Proxmox" in texto


def test_ca_a4_2_1_el_texto_de_pools_sin_permiso_nombra_pool_audit_y_pool():
    texto = texto_de(CodigoError.POOLS_SIN_PERMISO)
    assert "Pool.Audit" in texto and "/pool" in texto
    assert texto != texto_de(CodigoError.POOLS_DESCONOCIDO) != texto_de(CodigoError.POOLS_ERROR)


def test_ca_a6_3_3_el_rollback_sin_powermgmt_y_sin_opciones_nombran_su_privilegio():
    assert "VM.PowerMgmt" in texto_de(CodigoError.ROLLBACK_SIN_POWERMGMT)
    assert "VM.Config.Options" in texto_de(CodigoError.ROLLBACK_SIN_OPCIONES)


def test_ca_a1_5_3_el_motivo_de_encendida_sin_permiso_es_distinto_del_generico_de_encendida():
    nuevo = texto_de(CodigoError.ROLLBACK_SIN_POWERMGMT)
    generico = texto_de(CodigoError.ROLLBACK_ENCENDIDA)
    assert nuevo != generico and "VM.PowerMgmt" in nuevo


def test_ca_a1_5_3_si_faltan_ambos_privilegios_el_texto_menciona_los_dos():
    texto = texto_de(
        CodigoError.ROLLBACK_SIN_POWERMGMT, tambien=str(CodigoError.ROLLBACK_SIN_OPCIONES)
    )
    assert "VM.PowerMgmt" in texto and "VM.Config.Options" in texto


def test_rnf_a5_los_errores_de_rollback_dicen_que_hacer():
    assert "Apágala" in texto_de(CodigoError.ROLLBACK_APAGADO_FALLIDO)
    assert "Quítala" in texto_de(CodigoError.ROLLBACK_DESPROTECCION_FALLIDA)


def test_ca_a2_5_el_error_de_descripcion_larga_dice_el_limite():
    assert "8192" in texto_de(CodigoError.DESCRIPCION_LARGA)


# --- Etapa.ENCENDIENDO ---


def test_rf_a8_4_la_etapa_encendiendo_tiene_texto_propio():
    texto = textos.texto_etapa(Etapa.ENCENDIENDO)
    assert "Encend" in texto
    assert texto != str(Etapa.ENCENDIENDO) and texto != Etapa.ENCENDIENDO.value


@pytest.mark.parametrize("etapa", list(Etapa))
def test_rf_a8_4_ninguna_etapa_se_muestra_con_su_identificador_crudo(etapa):
    texto = textos.texto_etapa(etapa)
    assert texto.strip() and texto != etapa.value and texto != str(etapa)


def test_dt_a5_las_etapas_de_encendido_y_ajuste_se_distinguen():
    assert textos.texto_etapa(Etapa.ENCENDIENDO) != textos.texto_etapa(Etapa.AJUSTANDO)


# --- Avisos de máquina ---


@pytest.mark.parametrize(
    "aviso",
    [
        "encendido_fallido",
        "encendido_omitido",
        "notas_plantilla_ilegible",
        "ajuste_pendiente:arranque",
        "ajuste_pendiente:proteccion",
    ],
)
def test_rf_a8_4_cada_aviso_de_maquina_nuevo_tiene_texto(aviso):
    texto = textos.texto_aviso_origen(aviso)
    assert texto.strip() and aviso not in texto


def test_ca_a1_1_5_el_aviso_de_encendido_fallido_dice_que_se_creo_y_esta_apagada():
    texto = textos.texto_aviso_origen("encendido_fallido")
    assert "Se creó" in texto and "no se pudo encender" in texto


# --- Reglas de validación V-A ---


PARAMS_VA = {
    "V-A01": {},
    "V-A02": {"etiqueta": "Mala Etiqueta"},
    "V-A03": {"etiqueta": "web", "motivo": "no_permitida"},
    "V-A04": {"tarjeta": "net0"},
    "V-A05": {"tarjeta": "net0"},
    "V-A06": {"tarjeta": "net0"},
    "V-A07": {"total": "9000", "limite": "8192", "sobran": "808"},
    "V-A08": {"total": "7600", "limite": "8192"},
    "V-A09": {},
    "V-A10": {"pool": "produccion"},
    "V-A11": {"pool": "produccion", "estado": "sin_permiso"},
    "V-A12": {"opcion": "encender", "privilegio": "VM.PowerMgmt", "ruta": "/vms"},
    "V-A13": {},
    "V-A14": {},
    "V-A15": {"pool": "produccion", "ruta": "/vms", "ruta_pool": "/pool/produccion"},
    "V-A16": {"pool": "a b"},
}


@pytest.mark.parametrize("codigo", sorted(PARAMS_VA))
def test_rf_a8_4_cada_regla_v_a_tiene_mensaje_sin_marcadores_ni_codigo_crudo(codigo):
    p = Problema("campo", codigo, Severidad.ERROR, dict(PARAMS_VA[codigo]))
    texto = textos.texto_problema(p)
    assert texto.strip()
    assert codigo not in texto
    assert not MARCADOR.search(texto)


@pytest.mark.parametrize("motivo", ["registrada", "no_permitida", "ninguna_permitida"])
def test_ca_a3_cada_motivo_de_etiqueta_rechazada_tiene_su_mensaje_y_nombra_la_etiqueta(motivo):
    p = Problema("etiquetas", "V-A03", Severidad.ERROR, {"etiqueta": "web", "motivo": motivo})
    assert "web" in textos.texto_problema(p)


def test_ca_a3_los_tres_motivos_de_etiqueta_rechazada_dan_mensajes_distintos():
    mensajes = {
        textos.texto_problema(
            Problema("etiquetas", "V-A03", Severidad.ERROR, {"etiqueta": "web", "motivo": m})
        )
        for m in ("registrada", "no_permitida", "ninguna_permitida")
    }
    assert len(mensajes) == 3


def test_ca_a2_5_v_a07_dice_cuantos_caracteres_sobran():
    p = Problema("notas", "V-A07", Severidad.ERROR, PARAMS_VA["V-A07"])
    texto = textos.texto_problema(p)
    assert "9000" in texto and "8192" in texto and "808" in texto


def test_ca_a0_3_3_v_a12_por_privilegio_y_por_version_son_mensajes_distintos():
    por_priv = Problema("encender", "V-A12", Severidad.ERROR, PARAMS_VA["V-A12"])
    por_version = Problema(
        "etiquetas",
        "V-A12",
        Severidad.ERROR,
        {"opcion": "etiquetas", "version": "9.9", "motivo": str(CodigoError.OPCION_SIN_VERSION)},
    )
    assert textos.texto_problema(por_priv) != textos.texto_problema(por_version)
    assert "9.9" in textos.texto_problema(por_version)


# --- RF-A8.2: guía de permisos con «Privilegios opcionales» ---


def test_rf_a8_2_los_privilegios_opcionales_estan_fuera_del_rol_de_14():
    assert len(ROL_PROXLAUNCH) == 14
    nombres = {p for p, _ in PRIVILEGIOS_OPCIONALES}
    assert nombres == {"VM.PowerMgmt", "Pool.Audit"}
    assert not nombres & set(ROL_PROXLAUNCH)  # CA-A8.1.1: el rol de 0.5.1 no cambia


def test_rf_a8_2_la_guia_tiene_la_seccion_privilegios_opcionales_con_cada_privilegio_y_ruta():
    assert ayuda.titulo_privilegios_opcionales() == "Privilegios opcionales"
    lineas = ayuda.privilegios_opcionales_guia()
    assert len(lineas) == len(PRIVILEGIOS_OPCIONALES)
    for (privilegio, ruta), linea in zip(PRIVILEGIOS_OPCIONALES, lineas, strict=True):
        assert privilegio in linea and ruta in linea
        assert ayuda.efecto_privilegio_opcional(privilegio) in linea


def test_rf_a8_2_la_guia_dice_que_sys_modify_no_se_pide_y_como_autorizar_etiquetas():
    notas = " ".join(ayuda.notas_opcionales_guia())
    assert "Sys.Modify" in notas
    assert "user-allow-list" in notas and "registered-tags" in notas


def test_rf_a8_2_el_dialogo_de_la_guia_muestra_la_seccion_y_los_privilegios(qtbot):
    d = DialogoGuiaToken()
    qtbot.addWidget(d)
    d.show()
    todo = "\n".join(lbl.text() for lbl in d.findChildren(QLabel))
    assert "Privilegios opcionales" in todo
    assert "VM.PowerMgmt" in todo and "Pool.Audit" in todo
    assert "Sys.Modify" in todo


def test_rf_a8_2_el_texto_para_el_administrador_menciona_los_privilegios_opcionales():
    texto = ayuda.texto_pedir_al_administrador()
    assert "VM.PowerMgmt" in texto and "Pool.Audit" in texto


def test_rf_a8_2_los_privilegios_del_rol_siguen_siendo_los_14_en_la_guia():
    assert len(ayuda.PRIVILEGIOS_ROL) == 14
    assert "VM.PowerMgmt" not in ayuda.privilegios_guia_token()


# --- RF-A8.4: los controles nuevos pasan por la traducción ---


class _TraductorPrefijo(QTranslator):
    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        return "[T]" + source_text


@pytest.fixture
def traductor(qapp):
    t = _TraductorPrefijo()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


def test_rf_a8_4_los_textos_de_los_controles_nuevos_del_formulario_son_traducibles(
    qtbot, traductor
):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inventario_individual())
    f.establecer_modo(True)
    controles = (
        f.fila_encender,
        f.fila_arranque_auto,
        f.fila_notas_origen,
        f.fila_notas_usuario,
        f.fila_notas,
        f.fila_etiquetas,
        f.fila_pool,
        f.fila_orden,
        f.fila_espera,
        f.fila_proteger,
        f.tabla_redes,
    )
    malos: list[str] = []
    for c in controles:
        malos += sin_traducir(c, ignorar=("net", "VirtIO", "Intel E1000", "vmbr"))
    assert malos == []


def test_rf_a8_4_las_explicaciones_de_deshabilitado_son_traducibles(qtbot, traductor):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inventario_individual())
    f.establecer_modo(True)
    from .apoyo_fase_a import permisos_fase_a

    f.establecer_disponibilidad(
        estados_opciones(permisos_fase_a(quitar=("VM.PowerMgmt",), anadir=("VM.PowerMgmt",)))
    )
    assert textos_de(f.fila_encender).count("[T]") >= 1
