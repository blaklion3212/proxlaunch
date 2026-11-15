"""Textos del lote: mensajes E-L y V-L, plurales (%n), ayudas y traducción (RNF-L03, CA-L22.4).

Con un catálogo de prueba «[T]» se comprueba que todo texto visible del lote pasa por el
sistema de traducción, y con un traductor espía que los plurales usan las formas de Qt.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QWidget,
)

from proxlaunch.interfaz import textos
from proxlaunch.interfaz.ayuda import CAMPOS_AYUDA_LOTE, ayuda
from proxlaunch.interfaz.dialogos.deshacer import DialogoDeshacer
from proxlaunch.interfaz.dialogos.informe import DialogoInforme
from proxlaunch.interfaz.dialogos.pausa_lote import DialogoPausaLote
from proxlaunch.interfaz.vistas.bloque_lote import BloqueLote
from proxlaunch.interfaz.vistas.progreso_lote import FaseLote, ProgresoLote, texto_barra
from proxlaunch.interfaz.vistas.resumen_lote import (
    ResumenLote,
    texto_boton_crear,
    texto_boton_reducir,
    texto_total_maquinas,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import (
    CandidatoRollback,
    EstadoMV,
    MotivoNoEnviada,
    MotivoPausa,
    Problema,
    Severidad,
)

from .apoyo_lote import entrada, entradas_de, informe_de
from .test_lote_resumen import plan_de

EM = EstadoMV

PARAMS = {
    "nombre": "web-01",
    "vmid": "101",
    "n": "3",
    "causa": "sin_espacio",
    "storage": "local",
    "pedido": "160",
    "libre": "150",
    "max": "4",
    "inicio": "100",
    "diferencia": "el número 102 ya no está libre",
    "detectada": "9.2",
    "mensaje": "tarea fallida",
    "motivo": "cancelado",
}

# Código -> fragmentos literales que debe contener su mensaje (sección 7 de los requisitos).
ESPERADOS_EL = {
    CodigoError.LOTE_SIN_NODO_APTO: ["Ningún servidor puede alojar esta máquina"],  # E-L01
    CodigoError.LOTE_VMIDS_INSUFICIENTES: [  # E-L02
        "No encontré 3 números de máquina libres a partir del 100"
    ],
    CodigoError.LOTE_SIN_ESPACIO: [  # E-L04
        "necesitan 160 GiB en «local» y solo hay 150 GiB libres",
        "Caben 4",
    ],
    CodigoError.LOTE_ENVIO_INCIERTO: [  # E-L05
        "No sabemos si «web-01» se creó. No se volverá a enviar: pulsa «Comprobar» para verlo."
    ],
    CodigoError.LOTE_EXISTENCIA_INDETERMINADA: [  # E-L06
        "No pudimos comprobar si «web-01» existe. Revisa la conexión y vuelve a comprobar "
        "antes de crearla otra vez."
    ],
    CodigoError.LOTE_PAUSADO_REPETIDO: [  # E-L07
        "Fallaron 3 máquinas seguidas por la misma causa:",
        "¿Continuar o detener?",
    ],
    CodigoError.LOTE_PAUSADO_CONEXION: [
        "Se perdió la conexión. Hay 3 máquinas sin confirmar."
    ],  # E-L09
    CodigoError.LOTE_NO_ENVIADA: [  # E-L10
        "«web-01» no se envió (cancelaste el lote). No existe en Proxmox."
    ],
    CodigoError.LOTE_PLAN_CAMBIO: [  # E-L11
        "Los datos del servidor cambiaron: el número 102 ya no está libre. Revisa el resumen "
        "y confirma otra vez."
    ],
    CodigoError.LOTE_EN_CURSO: ["Hay un lote en curso. Espera a que termine o cancélalo."],  # E-L12
    CodigoError.LOTE_CANTIDAD_INVALIDA: ["Elige entre 1 y 100 máquinas."],  # E-L13
    CodigoError.VERSION_FORZADA_MAYOR: [  # E-L14
        "Has forzado una versión más nueva que la del servidor (9.2); solo puedes simular."
    ],
    CodigoError.ETIQUETA_RECHAZADA: [  # E-L15
        "Proxmox no aceptó la etiqueta de la máquina. No se creó."
    ],
    CodigoError.ROLLBACK_FALLO: [  # E-L17
        "No se pudo eliminar «web-01»",
        "tarea fallida",
        "Elimínala desde Proxmox.",
    ],
    CodigoError.ROLLBACK_NO_PROPIA: [  # E-L18
        "No eliminamos «web-01» porque no podemos asegurar que la creó este lote."
    ],
    CodigoError.ROLLBACK_ENCENDIDA: [  # E-L19
        "«web-01» está encendida. Apágala en Proxmox y vuelve a intentarlo."
    ],
    CodigoError.ROLLBACK_BLOQUEADA: [  # E-L20
        "«web-01» está protegida o bloqueada. Quita la protección en Proxmox."
    ],
    CodigoError.ROLLBACK_DISCOS_SUELTOS: [  # E-L21
        "Pueden haber quedado discos sueltos de «web-01»; revísalos en Proxmox."
    ],
    CodigoError.ROLLBACK_INCIERTO: [  # E-L22
        "No sabemos si se eliminó «web-01». Comprueba antes de reintentar."
    ],
    CodigoError.ESCRITURA_EN_SIMULACION: [  # E-L23
        "Error interno: se intentó escribir en modo simulación. No se creó nada."
    ],
}


@pytest.mark.parametrize("codigo", list(ESPERADOS_EL), ids=lambda c: c.value)
def test_cada_error_del_lote_tiene_el_mensaje_llano_del_requisito(codigo):
    texto = textos.texto_error(ErrorProxLaunch(codigo, dict(PARAMS)))
    for fragmento in ESPERADOS_EL[codigo]:
        assert fragmento in texto, (codigo, texto)


@pytest.mark.parametrize("codigo", list(ESPERADOS_EL), ids=lambda c: c.value)
def test_los_mensajes_del_lote_no_dejan_marcadores_ni_puntos_dobles(codigo):
    texto = textos.texto_error(ErrorProxLaunch(codigo, dict(PARAMS)))
    assert "{" not in texto and "}" not in texto and "%n" not in texto
    assert ".." not in texto, texto  # la causa ya termina en punto: no se duplica


@pytest.mark.parametrize("codigo", list(ESPERADOS_EL), ids=lambda c: c.value)
def test_los_mensajes_del_lote_sin_parametros_no_revientan(codigo):
    assert textos.texto_error(ErrorProxLaunch(codigo)).strip()


def test_e_l09_en_singular_y_plural():
    uno = textos.texto_error(ErrorProxLaunch(CodigoError.LOTE_PAUSADO_CONEXION, {"n": "1"}))
    assert uno == "Se perdió la conexión. Hay 1 máquina sin confirmar."


def test_e_l07_la_causa_puede_ser_un_codigo_de_error_traducido_o_un_texto():
    por_codigo = textos.texto_error(
        ErrorProxLaunch(CodigoError.LOTE_PAUSADO_REPETIDO, {"n": "3", "causa": "sin_espacio"})
    )
    assert "No hay espacio suficiente" in por_codigo
    por_texto = textos.texto_error(
        ErrorProxLaunch(CodigoError.LOTE_PAUSADO_REPETIDO, {"n": "3", "causa": "algo raro"})
    )
    assert "algo raro" in por_texto


def test_e_l03_en_un_lote_se_explica_que_la_maquina_no_se_creo_y_se_reintenta_despues():
    """E-L03: «El número {vmid} lo usó otra persona mientras tanto. Esta máquina no se creó.»"""
    e = entrada(0, EM.ERROR, error=ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "101"}))
    from proxlaunch.interfaz.modelos_tabla import detalle_entrada

    texto = detalle_entrada(e)
    assert "lo usó otra persona mientras tanto" in texto
    assert "no se creó" in texto.lower()


def test_e_l16_un_403_por_maquina_nombra_el_privilegio_y_la_ruta():
    e = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE,
        {"privilegio": "VM.Allocate", "ruta": "/vms/104", "vmid": "104"},
    )
    texto = textos.texto_error(e)
    assert "VM.Allocate" in texto and "/vms/104" in texto


@pytest.mark.parametrize(
    "motivo, frase",
    [
        (MotivoNoEnviada.CANCELADO, "cancelaste el lote"),
        (MotivoNoEnviada.PAUSA, "el lote se detuvo"),
        (MotivoNoEnviada.ERROR_GLOBAL, "afectaba a todo el lote"),
        (MotivoNoEnviada.NODO_CAIDO, "el nodo no respondió"),
        (None, "no se llegó a enviar"),
    ],
)
def test_e_l10_cada_motivo_de_no_envio_se_explica(motivo, frase):
    assert frase in textos.texto_motivo_no_enviada(motivo)


@pytest.mark.parametrize("motivo", list(MotivoPausa))
def test_el_titulo_de_cada_pausa_existe(motivo):
    assert textos.texto_motivo_pausa(motivo).startswith("El lote se detuvo")


# --- Reglas V-L ---------------------------------------------------------------------------


REGLAS_V = [
    ("V-L01", "cantidad", {}, "Elige entre 1 y 100 máquinas."),
    ("V-L02", "patron.prefijo", {}, "El prefijo solo puede tener letras sin acentos"),
    ("V-L02", "patron.prefijo", {"causa": "vacio"}, "Escribe un prefijo"),
    ("V-L03", "patron.separador", {}, "Elige un guion o ningún separador."),
    ("V-L05", None, {}, "no pueden repetirse"),
    (
        "V-L06",
        "nombre",
        {"nombre": "web-01", "vmid": "105"},
        "Ya existe una máquina llamada «web-01»",
    ),
    ("V-L07", "vmid_inicial", {}, "entre 100 y 999999999"),
    ("V-L07", "vmid_inicial", {"ultimo": "1000000004"}, "llegaría hasta el número 1000000004"),
    (
        "V-L08",
        None,
        {"n": "5", "inicio": "100"},
        "No hay 5 números de máquina libres a partir del 100",
    ),
    (
        "V-L09",
        "storage",
        {"n": "5", "storage": "local", "pedido_gib": "160", "libre_gib": "150"},
        "Las 5 máquinas necesitan 160 GiB en «local» y solo hay 150 GiB libres.",
    ),
    (
        "V-L11",
        "destino",
        {"motivo": "storage", "nodo": "pve3", "storage": "local-lvm"},
        "«pve3» no tiene el almacenamiento «local-lvm».",
    ),
    (
        "V-L11",
        "destino",
        {"motivo": "bridge", "nodo": "pve3", "bridge": "vmbr9"},
        "no tiene la red «vmbr9»",
    ),
    ("V-L11", "destino", {"motivo": "sin_conexion", "nodo": "pve2"}, "«pve2» está sin conexión."),
    (
        "V-L12",
        "memoria_mib",
        {"nodo": "pve2"},
        "No se pudo leer la memoria libre de «pve2»; el reparto usa el espacio.",
    ),
    ("V-L13", "destino", {}, "Elige al menos un nodo disponible."),
    ("V-L14", None, {}, "Se actualizaron los datos del servidor."),
    ("V-L16", None, {}, "falta el permiso VM.Allocate"),
    ("V-L17", None, {}, "Hay un lote en curso."),
    ("E-L01", None, {}, "Ningún servidor puede alojar esta máquina"),
]


@pytest.mark.parametrize("regla, campo, params, esperado", REGLAS_V)
def test_cada_regla_vl_tiene_su_mensaje(regla, campo, params, esperado):
    texto = textos.texto_problema_lote(Problema(regla, Severidad.ERROR, campo, params))
    assert esperado in texto
    assert "{" not in texto and "%n" not in texto


def test_v_l04_nombra_el_primer_nombre_invalido_y_la_causa():
    p = Problema(
        "V-L04",
        Severidad.ERROR,
        "patron.prefijo",
        {"nombre": "web_01", "causa": "caracter", "caracter": "_"},
    )
    texto = textos.texto_problema_lote(p)
    assert texto == "El nombre «web_01» no es válido: tiene el carácter «_», que no se admite."


def test_v_l10_distingue_aviso_y_error_de_sobreasignacion():
    prm = {"pedido_gib": "300", "libre_gib": "150", "storage": "local-lvm"}
    aviso = textos.texto_problema_lote(Problema("V-L10", Severidad.AVISO_CONFIRMABLE, None, prm))
    assert "Estás pidiendo 300 GiB y solo hay 150 GiB libres" in aviso
    assert "pueden fallar" in aviso
    error = textos.texto_problema_lote(Problema("V-L10", Severidad.ERROR, None, prm))
    assert "más de 3 veces" in error


# --- Ayuda (CA-L22.4) ---------------------------------------------------------------------


@pytest.mark.parametrize("clave", CAMPOS_AYUDA_LOTE)
def test_ca_l22_4_cada_concepto_del_lote_tiene_ayuda_de_una_a_tres_frases(clave):
    texto = ayuda(clave)
    assert texto.strip(), clave
    frases = [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]
    assert 1 <= len(frases) <= 3, (clave, texto)
    assert "{" not in texto


def test_ca_l22_4_la_lista_cubre_los_conceptos_pedidos():
    pedidos = {
        "lote_cantidad", "lote_prefijo", "lote_inicio", "lote_relleno", "lote_vmid_inicial",
        "lote_destino", "lote_equilibrado", "lote_por_turnos", "lote_sobreasignacion",
        "lote_simulacion", "lote_deshacer", "lote_etiqueta", "lote_envio_incierto",
    }  # fmt: skip
    assert pedidos <= set(CAMPOS_AYUDA_LOTE)


def test_ca_l08_5_la_ayuda_de_sobreasignacion_explica_el_concepto():
    texto = ayuda("lote_sobreasignacion").lower()
    # «espacio prometido que no se reserva hasta usarlo» (CA-L08.5), sin la jerga «thin».
    assert "reserva" in texto and "hasta que se usa" in texto
    assert "thin" not in texto


# --- Plurales con las formas de Qt (RNF-L03) -------------------------------------------------


class _TraductorEspia(QTranslator):
    """Registra cada (texto fuente, n) que se traduce; devuelve el texto sin cambios."""

    def __init__(self):
        super().__init__()
        self.visto: list[tuple[str, int]] = []

    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        self.visto.append((source_text, n))
        return ""  # sin traducción: Qt usa el texto fuente y sustituye %n


@pytest.fixture
def espia(qapp):
    t = _TraductorEspia()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


def test_los_plurales_pasan_n_a_qt_y_el_texto_fuente_lleva_percent_n(espia, qtbot):
    texto_total_maquinas(12)
    texto_boton_crear(12, simulado=False)
    texto_boton_crear(12, simulado=True)
    texto_boton_reducir(7)
    textos.texto_error(ErrorProxLaunch(CodigoError.LOTE_PAUSADO_CONEXION, {"n": "4"}))
    p = ProgresoLote()
    qtbot.addWidget(p)
    p.establecer_fase(FaseLote.TERMINADO, dudosas=5)
    d = DialogoDeshacer([CandidatoRollback(entrada(i, EM.OK), True, None, False) for i in range(6)])
    qtbot.addWidget(d)
    vistos = set(espia.visto)
    for fuente, n in (
        ("Vas a crear %n máquinas", 12),
        ("Crear %n máquinas", 12),
        ("Crear de verdad estas %n máquinas", 12),
        ("Reducir a %n", 7),
        ("Se perdió la conexión. Hay %n máquinas sin confirmar.", 4),
        ("Comprobar las %n dudosas", 5),
        ("Eliminar %n máquinas", 6),
    ):
        assert (fuente, n) in vistos, (fuente, n)


def test_el_resumen_de_un_lote_usa_la_forma_correcta_segun_la_cantidad(qapp):
    assert texto_total_maquinas(1) == "Vas a crear una máquina"
    assert texto_total_maquinas(2) == "Vas a crear 2 máquinas"
    assert texto_boton_reducir(1) == "Reducir a 1"


# --- Todo texto visible pasa por tr (CA-23.3 aplicado al lote) ------------------------------------


class _TraductorPrefijo(QTranslator):
    def translate(self, context, source_text, disambiguation=None, n=-1):  # noqa: ANN001
        return "[T]" + source_text


@pytest.fixture
def traductor(qapp):
    t = _TraductorPrefijo()
    QCoreApplication.installTranslator(t)
    yield t
    QCoreApplication.removeTranslator(t)


_TRADUCIDO = re.compile(r"^[^\wÁ-ú\[]*\[T\]")
_TIENE_LETRAS = re.compile(r"[A-Za-zÁ-ú]{2,}")
# Sin traducir por naturaleza: nombres técnicos de Proxmox y datos del usuario o del servidor.
_NO_TRADUCIBLES = {"VMID", "?"}


def _sin_traducir(raiz: QWidget, nodos=("pve1", "pve2", "pve3")) -> list[str]:
    """Textos fijos visibles de ``raiz`` que no llevan el prefijo del catálogo de prueba."""
    malos: list[str] = []

    def revisar(texto: str, donde: str) -> None:
        t = texto.strip()
        if not t or not _TIENE_LETRAS.search(t) or t in _NO_TRADUCIBLES:
            return
        if any(t.startswith(n) for n in nodos):  # nombres de nodo: datos del servidor
            return
        if not _TRADUCIDO.search(t):
            malos.append(f"{donde}: {t[:50]!r}")

    for w in raiz.findChildren(QWidget):
        nombre = type(w).__name__
        if isinstance(w, (QPushButton, QCheckBox, QRadioButton)):
            revisar(w.text(), nombre)
            revisar(w.toolTip(), nombre + ".tooltip")
        elif isinstance(w, QLabel):
            revisar(w.text(), nombre)
        elif isinstance(w, QGroupBox):
            revisar(w.title(), nombre)
        elif isinstance(w, QComboBox):
            for i in range(w.count()):
                revisar(w.itemText(i), nombre + ".item")
        if w.accessibleName():
            revisar(w.accessibleName(), nombre + ".accesible")
    return malos


def test_ca_rnf_l03_bloque_lote_todo_el_texto_pasa_por_tr(qtbot, traductor, inv_cluster):
    b = BloqueLote()
    qtbot.addWidget(b)
    b.establecer_inventario(inv_cluster)
    b.cantidad.setText("3")
    b.prefijo.setText("web")
    b.establecer_modo(True)
    b.aplicar_problemas(b.problemas(plan_de(inv_cluster, 1).definicion.plantilla))
    b.show()
    assert b.title().startswith("[T]")
    assert "[T]" in b.texto_vista_previa
    assert _sin_traducir(b) == []


def test_ca_rnf_l03_resumen_lote_todo_el_texto_pasa_por_tr(qtbot, traductor, inv_cluster):
    r = ResumenLote()
    qtbot.addWidget(r)
    r.mostrar_plan(plan_de(inv_cluster, 3, gib=60))  # thin: casilla, avisos, motivo
    r.show()
    assert _sin_traducir(r) == []
    r.mostrar_plan(plan_de(inv_cluster, 3, gib=20, storage="local"))  # error y «Reducir a»
    assert _sin_traducir(r) == []
    assert r.boton_reducir.text().startswith("[T]")


def test_ca_rnf_l03_progreso_lote_todo_el_texto_pasa_por_tr(qtbot, traductor, inv_cluster):
    p = ProgresoLote()
    qtbot.addWidget(p)
    p.iniciar(plan_de(inv_cluster, 3))
    p.actualizar(entradas_de([EM.OK, EM.ERROR, EM.NO_ENVIADA]))
    p.establecer_fase(FaseLote.TERMINADO, dudosas=2, elegibles=1, reintentables=1)
    p.show()
    assert _sin_traducir(p) == []
    assert p.texto_resumen_barra.startswith("[T]")
    for estado in EM:
        assert "[T]" in textos.texto_estado_mv(estado)


def test_ca_rnf_l03_dialogos_del_lote_todo_el_texto_pasa_por_tr(qtbot, traductor, tmp_path):
    pausa = DialogoPausaLote(
        MotivoPausa.ERROR_GLOBAL, ErrorProxLaunch(CodigoError.ETIQUETA_RECHAZADA)
    )
    qtbot.addWidget(pausa)
    pausa.show()
    deshacer = DialogoDeshacer(
        [
            CandidatoRollback(entrada(0, EM.OK), True, None, False),
            CandidatoRollback(entrada(1, EM.ERROR), False, "error", False),
        ]
    )
    qtbot.addWidget(deshacer)
    deshacer.show()
    informe = DialogoInforme(informe_de(entradas_de([EM.OK, EM.ERROR])), tmp_path)
    qtbot.addWidget(informe)
    informe.show()
    for d in (pausa, deshacer, informe):
        assert _sin_traducir(d) == [], type(d).__name__
    assert pausa.windowTitle().startswith("[T]") and deshacer.windowTitle().startswith("[T]")
    assert informe.windowTitle().startswith("[T]")


def test_ca_l19_6_la_plantilla_del_informe_pasa_por_la_traduccion(traductor):
    from proxlaunch.interfaz.informe_lote import texto_informe

    t = texto_informe(
        informe_de(
            entradas_de([EM.OK, EM.ERROR, EM.NO_ENVIADA], upid="UPID:pve1:1:2:3:q:101:u@pam:")
        )
    )
    for encabezado in (
        "Resumen",
        "Pedidas:",
        "Creadas:",
        "Máquinas",
        "Configuración de las máquinas",
    ):
        assert f"[T]{encabezado}" in t, encabezado
    assert t.startswith("[T]ProxLaunch")
    assert "[T]Cómo encontrar estas máquinas" in t


@pytest.mark.parametrize("codigo", list(ESPERADOS_EL), ids=lambda c: c.value)
def test_ca_rnf_l03_cada_error_del_lote_sale_del_sistema_de_traduccion(traductor, codigo):
    assert "[T]" in textos.texto_error(ErrorProxLaunch(codigo, dict(PARAMS)))


@pytest.mark.parametrize("regla, campo, params, _", REGLAS_V)
def test_ca_rnf_l03_cada_regla_vl_sale_del_sistema_de_traduccion(
    traductor, regla, campo, params, _
):
    assert "[T]" in textos.texto_problema_lote(Problema(regla, Severidad.ERROR, campo, params))


def test_ca_rnf_l03_la_barra_global_se_traduce(traductor):
    assert texto_barra(entradas_de([EM.OK, EM.ERROR])).count("[T]") >= 2


def test_texto_de_estado_de_deshacer_se_traduce(traductor):
    from proxlaunch.nucleo.lote.modelos import EstadoRollback

    for e in EstadoRollback:
        assert "[T]" in textos.texto_estado_rollback(e)
