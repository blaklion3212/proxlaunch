"""Catálogo de textos de la fase B (0.7.0): cada regla V-B y cada error B tiene su mensaje, todo es
traducible y las guías (permisos y ejemplo del agente) dicen lo que deben.

Derivadas de docs/requisitos/fase-b.md: CA-B0.6.1 (existen los textos de cada V-B y concepto del
glosario), CA-B8.1.2 (solo español, accesibles desde ``textos.py`` y traducibles), CA-B5.2.1
(guía de permisos por versión) y CA-B4.7.1 (el ejemplo copiado es el de la guía).
"""

from __future__ import annotations

import itertools
import re

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit

from proxlaunch.interfaz import textos, textos_b
from proxlaunch.interfaz.ayuda import (
    CAMPOS_AYUDA_FASE_B,
    ayuda,
    ejemplo_snippet_agente,
    instrucciones_snippet_agente,
)
from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken
from proxlaunch.interfaz.textos import texto_error, texto_estado_opcion, texto_generico
from proxlaunch.interfaz.textos_b import ayuda_b2, texto_aviso_b, texto_problema_completo
from proxlaunch.interfaz.vistas.seccion_cloudinit import SeccionCloudInit
from proxlaunch.nucleo.cloudinit.disponibilidad import OpcionB, disponibilidad_fase_b
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad
from proxlaunch.nucleo.validacion import Problema, Severidad

from .apoyo_fase_a import caps_de
from .apoyo_fase_b import info_plantilla

GENERICO_ESTADO = "No disponible."

# Un caso por rama de texto de cada regla V-B (con los parámetros que pone el núcleo).
TARJETA = {"tarjeta": "1"}
CASOS_V_B: list[tuple[str, dict[str, str]]] = [
    ("V-B01", {"requerida": "8.4", "version": "8.2"}),
    *[("V-B02", {"motivo": m}) for m in ("falta_archivo", "falta_url", "http", "volid", "otro")],
    ("V-B03", {"motivo": "extension"}),
    ("V-B03", {"motivo": "nombre"}),
    *[
        ("V-B04", {"motivo": m})
        for m in ("otro_formato", "extension_no_coincide", "nombre_incoherente", "vacio")
    ],
    *[("V-B05", {"motivo": m}) for m in ("solo_sha256_local", "no_se_usa", "formato")],
    *[("V-B05", {"motivo": m}) for m in ("suma_obligatoria",)],
    ("V-B05", {"motivo": "suma_debil", "algoritmo": "md5"}),
    ("V-B05", {"motivo": "suma_debil", "algoritmo": "sha1"}),
    ("V-B06", {"motivo": "no_valido"}),
    ("V-B06", {}),
    ("V-B07", {"storage": "datos", "nodo": "pve"}),
    ("V-B08", {}),
    ("V-B09", {}),
    ("V-B12", {"final_gib": "8", "imagen_gib": "10"}),
    ("V-B13", {}),
    ("V-B14", {}),
    ("V-B15", {"privilegio": "VM.Config.Disk", "ruta": "/vms"}),
    ("V-B16", {}),
    ("V-B20", {"plantilla": "base", "motivo": "sin_unidad"}),
    ("V-B20", {"plantilla": "base", "motivo": "no_comprobable"}),
    ("V-B20", {"plantilla": "base", "motivo": "sin_unidad", "elementos": "4"}),
    ("V-B21", {"motivo": "patron"}),
    ("V-B21", {}),
    *[
        ("V-B22", {"linea": "2", "motivo": m})
        for m in ("tipo_desconocido", "sin_cuerpo", "base64", "con_opciones", "otro")
    ],
    ("V-B23", {}),
    ("V-B24", {"motivo": "duplicadas", "cantidad": "2"}),
    ("V-B24", {"motivo": "demasiado_texto"}),
    ("V-B24", {"motivo": "demasiadas"}),
    *[("V-B25", {"motivo": m}) for m in ("no_coincide", "control", "larga", "corta", "windows")],
    *[
        ("V-B26", {**TARJETA, "motivo": m})
        for m in ("sin_prefijo", "prefijo", "octeto", "ceros", "reservada", "otro")
    ],
    ("V-B27", TARJETA),
    *[
        ("V-B28", {**TARJETA, "motivo": m})
        for m in ("fuera_de_red", "igual_a_ip", "red_o_difusion", "octeto", "otro")
    ],
    ("V-B29", TARJETA),
    *[
        ("V-B30", {**TARJETA, "motivo": m, "nombre": "web-03", "direccion": "10.0.0.255"})
        for m in ("desborde", "puerta", "red_o_difusion")
    ],
    ("V-B30", {**TARJETA, "motivo": "desborde", "nombre": "web-03", "afectadas": "3"}),
    ("V-B31", {"direccion": "10.0.0.5", "con": "web-01", "nombre": "web-02"}),
    ("V-B32", {"cantidad": "4"}),
    ("V-B32", {}),
    ("V-B33", {}),
    *[("V-B34", {**TARJETA, "motivo": m}) for m in ("rango", "repetida", "inexistente")],
    ("V-B35", {"plantilla": "win11"}),
    ("V-B36", {}),
    ("V-B38", {**TARJETA, "cantidad": "5"}),
    ("V-B39", {}),
    ("V-B39", {"motivo": "contrasena_en_plantilla"}),
    ("V-B39", {"motivo": "snippets"}),
    ("V-B39", {"motivo": "red"}),
    ("V-B40", {"motivo": "olvidada"}),
    ("V-B50", {"nodo": "pve2"}),
    ("V-B51", {"snippet": "local:snippets/a.yaml", "nodo": "pve2"}),
    ("V-B51", {"snippet": "x:snippets/a.yaml", "nodo": "pve2", "motivo": "sin_almacen"}),
    ("V-B52", {"snippet": "local:snippets/a.yaml"}),
    ("V-B52", {"motivo": "suma"}),
    ("V-B53", {}),
    ("V-B54", {"tipo": "vendor"}),
    ("V-B56", {"plantilla": "base"}),
    ("V-B60", {}),
    ("V-B61", {"minimo": "10", "maximo": "1800"}),
    ("V-B62", {"origen": "plantilla"}),
    ("V-B62", {"origen": "iso"}),
    ("V-B64", {}),
    ("V-B65", {"plazo_s": "30"}),
]


def problema(codigo: str, params: dict[str, str], severidad=Severidad.ERROR) -> Problema:
    return Problema("campo", codigo, severidad, dict(params))


def id_caso(caso: tuple[str, dict[str, str]]) -> str:
    return caso[0] + ":" + ",".join(f"{k}={v}" for k, v in caso[1].items())


# --- CA-B0.6.1: un mensaje para cada regla V-B ---


@pytest.mark.parametrize("caso", CASOS_V_B, ids=id_caso)
def test_ca_b0_6_1_cada_regla_v_b_tiene_su_mensaje_y_no_cae_al_texto_generico(caso):
    codigo, params = caso
    texto = texto_problema_completo(problema(codigo, params))
    assert texto
    assert texto != texto_generico(), codigo
    assert codigo not in texto  # nunca el código crudo
    assert "{" not in texto and "}" not in texto  # sin marcadores sin resolver
    assert "?" not in re.sub(r"[¿][^?]*\?", "", texto)  # un «?» suelto delata un dato ausente


# V-B39 significa una cosa en el formulario y otra en B2: tiene su prueba aparte.
SIN_V_B39 = [c for c in CASOS_V_B if c[0] != "V-B39"]


@pytest.mark.parametrize("caso", SIN_V_B39, ids=id_caso)
def test_ca_b0_6_1_el_mensaje_de_la_regla_es_el_mismo_con_texto_problema_de_textos_py(caso):
    codigo, params = caso
    p = problema(codigo, params)
    assert textos.texto_problema(p) == texto_problema_completo(p)


def test_v_b39_se_explica_distinto_en_el_formulario_y_en_la_plantilla_de_b2():
    p = problema("V-B39", {})
    assert "solo se puede usar al clonar" in textos.texto_problema(p)
    assert "primera tarjeta de red" in texto_problema_completo(p)
    sin_clave = problema("V-B39", {"motivo": "contrasena_en_plantilla"})
    assert "nunca lleva contraseña" in texto_problema_completo(sin_clave)


def test_ca_b0_6_1_v_b11_traduce_la_regla_de_validar_vm_que_reporta():
    p = Problema("sockets", "V-B11", Severidad.ERROR, {"regla": "V-05"})
    texto = texto_problema_completo(p)
    assert texto == textos.texto_problema(Problema("sockets", "V-05", Severidad.ERROR, {}))
    assert "V-05" not in texto and "V-B11" not in texto


def test_ca_b0_6_1_los_avisos_a_nivel_de_maquina_de_la_fase_b_tienen_texto():
    codigos = (
        "ip_no_obtenida",
        "ip_parcial",
        "ip_no_coincide",
        "ajuste_pendiente:cloudinit",
        "ajuste_pendiente:contrasena",
        "sin_ampliar",
        "imagen_sin_agente",
        "consola_serie",
        "se_asume_qcow2",
        "solo_clon_completo",
        "maquina_borrada",
        "imagen_quedo_en_import",
        "borrado_sin_esperar",
        "ajuste_omitido:disco",
        "omitido:cloudinit",
        "omitido:ampliar",
        "maquina_anterior_sin_borrar:105:ubuntu-base",
    )
    for codigo in codigos:
        texto = textos.texto_aviso_origen(codigo)
        assert texto, codigo
        assert codigo not in texto
        assert texto == texto_aviso_b(codigo) or codigo.startswith("ajuste_pendiente")


# --- CA-B0.6.1: un mensaje para cada error B ---


CODIGOS_ERROR_B = [
    (CodigoError.CLOUDINIT_SIN_UNIDAD, {"plantilla": "base"}),
    (CodigoError.CLAVE_SSH_RECHAZADA, {}),
    (CodigoError.SNIPPET_NO_ENCONTRADO, {"snippet": "local:snippets/a.yaml"}),
    (CodigoError.SNIPPET_NO_ENCONTRADO, {}),
    (CodigoError.CONTRASENA_OLVIDADA, {}),
    (CodigoError.DESCONOCIDO, {"motivo": "respuesta_demasiado_grande"}),
    *[
        (CodigoError.PARAMETRO_INVALIDO, {"campo": c})
        for c in (
            "cloudinit.usuario",
            "cloudinit.claves",
            "cloudinit.dns",
            "cloudinit.dominio",
            "cloudinit.actualizar",
            "cloudinit.tarjetas[1].ip",
            "cloudinit.tarjetas[0].puerta",
            "cloudinit.snippets.vendor",
            "cloudinit.otro",
        )
    ],
    *[
        (CodigoError.ARCHIVO_CLAVES_NO_VALIDO, {"motivo": m})
        for m in ("tamano", "binario", "ilegible")
    ],
    (CodigoError.AGENTE_NO_CONFIGURADO, {}),
    (CodigoError.AGENTE_NO_RESPONDE, {}),
    (CodigoError.MV_NO_EN_MARCHA, {}),
    (CodigoError.PLANTILLA_EN_MARCHA, {}),
    (CodigoError.PLANTILLA_CON_SNAPSHOTS, {}),
    (CodigoError.PLANTILLA_NO_APAGADA, {}),
    (CodigoError.PLANTILLA_NO_APAGADA, {"bloqueo": "backup"}),
    (CodigoError.IMAGEN_FORMATO_INCORRECTO, {}),
    (CodigoError.SUMA_NO_COINCIDE, {}),
    (CodigoError.SUMA_NO_COINCIDE, {"esperada": "abc123abc123", "obtenida": "def456def456"}),
    (CodigoError.PLANTILLA_IMAGEN_SIN_IMPORT, {}),
    (
        CodigoError.OPCION_SIN_PRIVILEGIO,
        {"opcion": "cloudinit", "privilegio": "VM.Config.Cloudinit", "ruta": "/vms"},
    ),
    (CodigoError.OPCION_SIN_VERSION, {"opcion": "asistente", "version": "8.4"}),
    (
        CodigoError.PERMISO_INSUFICIENTE,
        {"ajuste": "cloudinit", "privilegio": "VM.Config.Cloudinit", "ruta": "/vms/101"},
    ),
    (CodigoError.PERMISO_INSUFICIENTE, {"ajuste": "cloudinit"}),
    (CodigoError.PERMISO_INSUFICIENTE, {"ajuste": "contrasena"}),
]


def id_error(caso) -> str:
    return f"{caso[0].value}:{','.join(caso[1])}"


@pytest.mark.parametrize("caso", CODIGOS_ERROR_B, ids=id_error)
def test_ca_b0_6_1_cada_error_de_la_fase_b_tiene_mensaje_propio(caso):
    codigo, params = caso
    texto = texto_error(ErrorProxLaunch(codigo, dict(params)))
    assert texto
    assert texto != texto_generico(), codigo
    assert codigo.value not in texto  # nunca el código crudo (p. ej. «agente_no_responde»)
    assert "{" not in texto and "}" not in texto


def test_ca_b0_6_1_todo_codigo_de_error_nuevo_de_la_fase_b_esta_en_la_prueba():
    nuevos = {
        CodigoError.CLOUDINIT_SIN_UNIDAD,
        CodigoError.CLAVE_SSH_RECHAZADA,
        CodigoError.SNIPPET_NO_ENCONTRADO,
        CodigoError.CONTRASENA_OLVIDADA,
        CodigoError.ARCHIVO_CLAVES_NO_VALIDO,
        CodigoError.AGENTE_NO_CONFIGURADO,
        CodigoError.AGENTE_NO_RESPONDE,
        CodigoError.MV_NO_EN_MARCHA,
        CodigoError.PLANTILLA_EN_MARCHA,
        CodigoError.PLANTILLA_CON_SNAPSHOTS,
        CodigoError.PLANTILLA_NO_APAGADA,
        CodigoError.IMAGEN_FORMATO_INCORRECTO,
        CodigoError.SUMA_NO_COINCIDE,
        CodigoError.PLANTILLA_IMAGEN_SIN_IMPORT,
    }
    cubiertos = {c for c, _ in CODIGOS_ERROR_B}
    assert nuevos <= cubiertos


def test_un_403_de_un_paso_b_dice_que_la_maquina_se_creo_y_falta_un_permiso():
    e = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE,
        {"ajuste": "cloudinit", "privilegio": "VM.Config.Cloudinit", "ruta": "/vms/101"},
    )
    texto = texto_error(e)
    assert "Se creó" in texto and "VM.Config.Cloudinit" in texto and "/vms/101" in texto
    # Sin la marca de paso B, el 403 sigue siendo el de siempre.
    normal = texto_error(ErrorProxLaunch(CodigoError.PERMISO_INSUFICIENTE, {}))
    assert "Se creó" not in normal


def test_ca_b0_6_1_cada_estado_de_opcion_no_disponible_de_la_fase_b_tiene_motivo_propio():
    """Ningún estado deshabilitado o con reservas cae a «No disponible.»."""
    estados = []
    versiones = [(8, 0), (8, 4), (9, 0), (9, 1), (9, 2)]
    privilegios = [
        None,
        [],
        ["VM.Config.Cloudinit"],
        ["VM.Config.Network"],
        ["VM.Config.Cloudinit", "VM.GuestAgent.Audit", "Datastore.AllocateSpace"],
        ["VM.Monitor", "Datastore.Allocate", "VM.Config.Network"],
    ]
    infos = [
        None,
        info_plantilla(),
        info_plantilla(unidad=False),
        info_plantilla(unidad=None),
        info_plantilla(es_windows=True),
        info_plantilla(agente=True),
    ]
    for version, privs, info, snippets in itertools.product(
        versiones, privilegios, infos, (True, False)
    ):
        permisos = (
            None if privs is None else PermisosEfectivos(rutas={"/": dict.fromkeys(privs, 1)})
        )
        estados.extend(disponibilidad_fase_b(permisos, caps_de(version), info, snippets).values())
    assert {e.opcion for e in estados} == set(OpcionB)
    no_libres = [e for e in estados if e.disponibilidad != Disponibilidad.SI]
    assert no_libres
    for e in no_libres:
        texto = texto_estado_opcion(e)
        assert texto and texto != GENERICO_ESTADO, (e.opcion, e.codigo, e.params)
        assert "{" not in texto and "}" not in texto


# --- CA-B0.6.1: glosario ---


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_FASE_B)
def test_ca_b0_6_1_cada_ayuda_de_la_fase_b_existe(clave):
    texto = ayuda(clave)
    assert texto and len(texto) > 20
    assert "{" not in texto


@pytest.mark.parametrize(
    "clave", ["intro", "imagen", "suma", "opciones_cloud", "cloudinit", "irreversible"]
)
def test_ca_b0_6_1_cada_seccion_del_asistente_tiene_ayuda_ampliada(clave):
    assert ayuda_b2(clave)


def test_ca_b0_6_1_el_glosario_explica_cada_concepto_con_sus_palabras_clave():
    esperado = {
        "cloudinit": ("primer arranque",),
        "imagen_cloud": ("Ubuntu",),
        "plantilla_irreversible": ("no se puede",),
        "agente": ("qemu-guest-agent", "Ubuntu", "Debian"),
        "snippets": ("archivo",),
        "ci_claves": (".pub",),
        "ci_puerta": ("router",),
        "consola_serie": ("xterm.js",),
        "ci_actualizar": ("actualiza",),
        "ci_unidad": ("disco",),
    }
    for clave, palabras in esperado.items():
        texto = ayuda(clave)
        for palabra in palabras:
            assert palabra.lower() in texto.lower(), (clave, palabra)


# --- CA-B8.1.2: todo es español y traducible desde textos.py ---


class _TraductorMarca(QTranslator):
    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        return "[T]" + source_text


@pytest.fixture
def traductor(qapp):
    t = _TraductorMarca()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


@pytest.mark.parametrize("caso", CASOS_V_B, ids=id_caso)
def test_ca_b8_1_2_el_mensaje_de_cada_regla_v_b_pasa_por_la_traduccion(traductor, caso):
    codigo, params = caso
    assert "[T]" in texto_problema_completo(problema(codigo, params))


@pytest.mark.parametrize("caso", CODIGOS_ERROR_B, ids=id_error)
def test_ca_b8_1_2_el_mensaje_de_cada_error_b_pasa_por_la_traduccion(traductor, caso):
    codigo, params = caso
    assert "[T]" in texto_error(ErrorProxLaunch(codigo, dict(params)))


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_FASE_B)
def test_ca_b8_1_2_las_ayudas_de_la_fase_b_pasan_por_la_traduccion(traductor, clave):
    assert "[T]" in ayuda(clave)


def test_ca_b8_1_2_el_ejemplo_del_agente_es_yaml_y_no_se_traduce_pero_sus_instrucciones_si(
    traductor,
):
    assert "[T]" not in ejemplo_snippet_agente()
    assert "[T]" in instrucciones_snippet_agente()


def test_ca_b8_1_2_la_seccion_de_cloudinit_no_deja_ningun_texto_fijo_sin_traducir(qtbot, traductor):
    from .test_mvp3_textos_accesibilidad import sin_traducir

    s = SeccionCloudInit()
    qtbot.addWidget(s)
    s.show()
    s.establecer_modo(True)
    s.establecer_info(info_plantilla(tarjetas=(0, 1)), {})
    s.establecer_esperar_ip(True)
    s.btn_ejemplo.setChecked(True)
    malos = sin_traducir(s, ignorar=("ssh-",))
    # El ejemplo YAML del agente no es un texto de la interfaz: no se traduce (es un archivo).
    malos = [m for m in malos if "#cloud-config" not in m and "package_update" not in m]
    assert malos == [], malos


def test_ca_b8_1_2_el_progreso_con_columna_ip_no_deja_ningun_texto_fijo_sin_traducir(
    qtbot, traductor
):
    from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote

    from .apoyo_fase_b import con_ip, entrada_ip
    from .test_lote_progreso import plan_vacio
    from .test_mvp3_textos_accesibilidad import sin_traducir

    p = ProgresoLote()
    qtbot.addWidget(p)
    p.show()
    p.iniciar(plan_vacio(2))
    p.actualizar((entrada_ip(0, ip=con_ip("10.0.0.5")), entrada_ip(1)))
    p.establecer_fase(FaseLote.TERMINADO)
    p.establecer_espera_ip(1)
    malos = sin_traducir(p, ignorar=("web-",))
    assert malos == [], malos


def test_ca_b8_1_2_los_textos_de_la_fase_b_estan_accesibles_desde_textos_py():
    for nombre in (
        "texto_problema",
        "texto_error",
        "texto_estado_opcion",
        "texto_claves_ssh",
        "texto_tarjeta_cloudinit",
        "lineas_opciones_fase_b",
        "opciones_avanzadas_fase_b",
    ):
        assert callable(getattr(textos, nombre)), nombre
    # Y el módulo de B2/B3 lo consulta ``textos`` para errores y problemas (DT-B15).
    assert textos_b.texto_error_b(ErrorProxLaunch(CodigoError.AGENTE_NO_RESPONDE, {}))


# --- CA-B4.7.1: el ejemplo copiado es el de la guía ---


def test_ca_b4_7_1_el_texto_copiado_es_el_mismo_que_el_del_cuadro_y_el_de_la_guia(qtbot):
    s = SeccionCloudInit()
    qtbot.addWidget(s)
    s.show()
    s.establecer_modo(True)
    s.btn_ejemplo.setChecked(True)
    assert s.caja_ejemplo.isVisibleTo(s)
    QApplication.clipboard().setText("antes")
    s.btn_copiar_ejemplo.click()
    copiado = QApplication.clipboard().text()
    assert copiado == s.txt_ejemplo.toPlainText() == ejemplo_snippet_agente()
    assert copiado == SeccionCloudInit.texto_ejemplo()


def test_ca_b4_7_1_el_ejemplo_es_un_snippet_vendor_que_instala_y_activa_el_agente():
    texto = ejemplo_snippet_agente()
    assert texto.startswith("#cloud-config\n")
    assert "qemu-guest-agent" in texto
    assert "systemctl enable --now qemu-guest-agent" in texto


def test_ca_b4_7_1_las_instrucciones_dicen_que_las_aplica_el_administrador_y_donde():
    texto = instrucciones_snippet_agente()
    assert "administrador" in texto
    assert "/var/lib/vz/snippets" in texto
    assert "no puede subir" in texto


def test_ca_b4_7_1_el_cuadro_del_ejemplo_es_de_solo_lectura_y_no_envia_nada(qtbot):
    s = SeccionCloudInit()
    qtbot.addWidget(s)
    assert s.txt_ejemplo.isReadOnly()
    emitidas = []
    s.cambiado.connect(lambda: emitidas.append(1))
    s.btn_copiar_ejemplo.click()
    assert emitidas == []  # copiar no cambia la configuración
    assert s.configuracion() is None


# --- CA-B5.2.1: guía de permisos por versión ---


def texto_de_guia(qtbot, version: tuple[int, int]) -> str:
    d = DialogoGuiaToken(caps=caps_de(version))
    qtbot.addWidget(d)
    d.show()
    etiquetas = "\n".join(lbl.text() for lbl in d.findChildren(QLabel))
    cajas = "\n".join(c.toPlainText() for c in d.findChildren(QPlainTextEdit))
    return etiquetas + "\n" + cajas


def test_ca_b5_2_1_con_proxmox_8_4_la_guia_lista_cloudinit_y_monitor_y_no_guestagent(qtbot):
    texto = texto_de_guia(qtbot, (8, 4))
    assert "VM.Config.Cloudinit" in texto
    assert "VM.Monitor" in texto
    assert "VM.GuestAgent" not in texto


def test_ca_b5_2_1_con_proxmox_9_2_la_guia_lista_guestagent_audit(qtbot):
    texto = texto_de_guia(qtbot, (9, 2))
    assert "VM.Config.Cloudinit" in texto
    assert "VM.GuestAgent.Audit" in texto


def test_ca_b5_2_1_con_proxmox_9_2_la_guia_no_menciona_vm_monitor(qtbot):
    assert "VM.Monitor" not in texto_de_guia(qtbot, (9, 2))


def test_ca_b5_2_1_la_linea_del_privilegio_del_agente_de_9_2_es_una_sola_y_no_la_de_8_x(qtbot):
    texto = texto_de_guia(qtbot, (9, 2))
    lineas = [ln for ln in texto.splitlines() if ln.startswith("• VM.")]
    assert sum("VM.GuestAgent.Audit" in ln for ln in lineas) == 1
    assert not [ln for ln in lineas if ln.startswith("• VM.Monitor")]


def test_ca_b5_2_1_con_8_4_la_guia_pide_el_privilegio_de_scripts_y_con_9_2_no_hace_falta(qtbot):
    assert "Datastore.Allocate" in texto_de_guia(qtbot, (8, 4))
    nueve = texto_de_guia(qtbot, (9, 2))
    assert "• Datastore.Allocate en" not in nueve


def test_la_guia_no_cambia_el_rol_base_de_catorce_privilegios_con_la_version(qtbot):
    a, b = texto_de_guia(qtbot, (8, 4)), texto_de_guia(qtbot, (9, 2))
    base = "VM.Allocate\nVM.Audit\nVM.Config.Options"
    assert base in a and base in b


def test_ca_b8_1_2_el_asistente_de_plantillas_no_deja_ningun_texto_fijo_sin_traducir(
    qtbot, traductor
):
    from .test_fase_b_plantilla_imagen import ClienteB2, hacer_dialogo
    from .test_mvp3_textos_accesibilidad import sin_traducir

    d = hacer_dialogo(qtbot, ClienteB2())
    # Las listas de nodos, almacenamientos y bridges son datos del servidor, no textos fijos.
    malos = [m for m in sin_traducir(d, ignorar=("https://",)) if "QComboBox.item" not in m]
    assert malos == [], malos


def test_ca_b8_1_2_el_formulario_al_clonar_no_deja_ningun_texto_fijo_sin_traducir(qtbot, traductor):
    from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
    from proxlaunch.nucleo.modelos.vm import OrigenSO

    from .apoyo_fase_b import disponibilidad
    from .apoyo_mvp4 import caps_origen, inv_origen
    from .test_mvp3_textos_accesibilidad import sin_traducir

    inv = inv_origen()
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.establecer_modo(True)
    f.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    f.establecer_info_cloudinit(info_plantilla(), disponibilidad())
    f.chk_encender.setChecked(True)
    f.chk_esperar_ip.setChecked(True)
    malos = sin_traducir(f.fila_esperar_ip) + sin_traducir(f.seccion_cloudinit, ignorar=("ssh-",))
    malos = [m for m in malos if "#cloud-config" not in m and "package_update" not in m]
    assert malos == [], malos


def test_ca_b8_1_2_el_dialogo_de_deshacer_con_la_nota_de_ip_traduce_todo(qtbot, traductor):
    from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer

    from .test_mvp3_textos_accesibilidad import sin_traducir

    d = DialogoDeshacer([], hay_espera_ip=True)
    qtbot.addWidget(d)
    d.show()
    assert sin_traducir(d) == []
    assert "[T]" in d._nota_espera_ip.text()


def test_ca_b2_3_5_el_rechazo_de_nombre_o_extension_dice_las_extensiones_y_el_renombrado_de_img():
    from proxlaunch.interfaz.textos import texto_error

    texto = texto_error(ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "filename"}))
    for extension in (".qcow2", ".raw", ".vmdk", ".ova"):
        assert extension in texto
    assert ".img" in texto
