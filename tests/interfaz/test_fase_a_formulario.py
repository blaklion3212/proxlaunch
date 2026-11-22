"""Formulario de la fase A (0.6.0): controles deshabilitados (no ocultos) con explicación, pools,
MTU solo VirtIO, cambio de servidor, accesibilidad e ida y vuelta de la configuración.

Derivadas de docs/requisitos/fase-a.md: RF-A0.3, RF-A0.4, CA-A1.1.4, CA-A1.2.4, CA-A2.1.5,
CA-A2.3.3, CA-A4.2.1-5, CA-A5.1.7, CA-A5.1.8, CA-A5.2.1, CA-A5.2.2, CA-A6.1.3, CL-A15, RNF-A8.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QCheckBox, QLabel, QPlainTextEdit

from proxlaunch.interfaz.vistas.formulario_vm import FormularioVM
from proxlaunch.nucleo.capacidades import Funcion
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.modelos.vm import (
    MTU_IGUAL_BRIDGE,
    ConfiguracionVM,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.opciones.disponibilidad import disponibilidad_opciones
from proxlaunch.nucleo.opciones.modelos import EstadoOpcion, EstadoPools, OpcionA, PoolsServidor
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad

from .apoyo import inventario_individual
from .apoyo_fase_a import (
    cadena_de_foco,
    caps_de,
    estados_opciones,
    explicacion,
    orden_visual,
    permisos_fase_a,
    textos_de,
)
from .apoyo_mvp4 import caps_origen, inv_origen, plantilla_pve, volumen


@pytest.fixture
def formulario(qtbot):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inventario_individual())
    f.establecer_modo(True)  # avanzado: todos los controles nuevos a la vista
    return f


def aplicar(f: FormularioVM, *, quitar=(), anadir=("VM.PowerMgmt",), pools=None, **kw) -> None:
    permisos = permisos_fase_a(quitar=quitar, anadir=anadir)
    f.establecer_disponibilidad(estados_opciones(permisos, pools, **kw), pools)


def pools_ok(*ids: str) -> PoolsServidor:
    return PoolsServidor(EstadoPools.OK, tuple(ids))


# --- RF-A0.3 / CA-A1.1.4 / CA-A1.2.4 / CA-A2.1.5 / CA-A6.1.3: privilegio ausente ---


@pytest.mark.parametrize(
    ("ca", "privilegio", "control", "fila"),
    [
        ("CA-A1.1.4", "VM.PowerMgmt", "chk_encender", "fila_encender"),
        ("CA-A1.2.4", "VM.Config.Options", "chk_arranque_auto", "fila_arranque_auto"),
        ("CA-A2.1.5", "VM.Config.Options", "chk_notas_origen", "fila_notas_origen"),
        ("CA-A2.1.5", "VM.Config.Options", "txt_notas", "fila_notas_origen"),
        ("CA-A6.1.3", "VM.Config.Options", "chk_proteger", "fila_proteger"),
        ("RF-A0.3", "VM.Config.Options", "txt_etiquetas", "fila_etiquetas"),
        ("RF-A0.3", "VM.Config.Options", "txt_orden", "fila_orden"),
    ],
)
def test_sin_privilegio_el_control_se_deshabilita_no_se_oculta_y_nombra_privilegio_y_ruta(
    formulario, ca, privilegio, control, fila
):
    # CA-A0.3.1 y su concreción por opción: ``ca`` identifica el criterio de la opción.
    aplicar(formulario, quitar=(privilegio,))
    widget = getattr(formulario, control)
    assert widget.isVisible(), f"{ca}: el control debe seguir a la vista"
    assert not widget.isEnabled(), ca
    assert privilegio in explicacion(widget), ca
    assert "/vms" in explicacion(widget), ca
    # La explicación también es visible junto al campo.
    assert privilegio in textos_de(getattr(formulario, fila)), ca


def test_ca_a0_3_1_con_el_privilegio_el_control_queda_habilitado_y_sin_explicacion(formulario):
    aplicar(formulario)
    assert formulario.chk_encender.isEnabled()
    assert explicacion(formulario.chk_encender) == ""
    assert "VM.PowerMgmt" not in textos_de(formulario.fila_encender)


def test_ca_a0_3_2_con_permisos_desconocidos_los_controles_quedan_habilitados(formulario):
    # Permisos desconocidos: la función pura devuelve «SI» para todo lo que depende de privilegios.
    estados = disponibilidad_opciones(None, caps_de(), pools_ok("a"))
    formulario.establecer_disponibilidad(estados, pools_ok("a"))
    for nombre in ("chk_encender", "chk_arranque_auto", "chk_notas_origen", "chk_proteger"):
        assert getattr(formulario, nombre).isEnabled(), nombre
    assert formulario.txt_etiquetas.isEnabled()


def test_ca_a0_3_1_sin_encender_ni_otras_opciones_la_creacion_basica_sigue_disponible(formulario):
    # RF-A8.1: sin los privilegios opcionales solo se desactiva la opción afectada.
    aplicar(formulario, anadir=(), pools=PoolsServidor(EstadoPools.SIN_PERMISO))
    assert not formulario.chk_encender.isEnabled()
    assert not formulario.combo_pool.isEnabled()
    for nombre in ("vmid", "nombre", "chk_arranque_auto", "chk_proteger", "txt_etiquetas"):
        assert getattr(formulario, nombre).isEnabled(), nombre


# --- RF-A0.4: versión sin soporte ---


def estado_sin_version(opcion: OpcionA, version: str) -> EstadoOpcion:
    return EstadoOpcion(
        opcion,
        Disponibilidad.NO,
        CodigoError.OPCION_SIN_VERSION,
        {"opcion": opcion.value, "version": version},
    )


def test_ca_a0_4_1_version_menor_que_la_minima_deshabilita_con_la_version_en_el_texto(formulario):
    estados = estados_opciones()
    estados[OpcionA.ETIQUETAS] = estado_sin_version(OpcionA.ETIQUETAS, "9.9")
    formulario.establecer_disponibilidad(estados)
    assert formulario.txt_etiquetas.isVisible()
    assert not formulario.txt_etiquetas.isEnabled()
    assert "9.9" in explicacion(formulario.txt_etiquetas)
    assert "Proxmox" in explicacion(formulario.txt_etiquetas)


def test_ca_a0_4_2_version_forzada_menor_deshabilita_igual_que_la_real(formulario):
    # La tabla de capacidades fija 7.3 como mínimo de las etiquetas: se fuerza una anterior.
    estados = estados_opciones(version=(7, 0), forzada=True)
    assert estados[OpcionA.ETIQUETAS].codigo == CodigoError.OPCION_SIN_VERSION
    formulario.establecer_disponibilidad(estados)
    assert not formulario.txt_etiquetas.isEnabled()
    minima = "7.3"
    assert minima in explicacion(formulario.txt_etiquetas)
    assert Funcion.ETIQUETAS  # la función existe en la tabla de capacidades


def test_ca_a0_4_1_deshabilitada_por_version_vuelve_a_su_valor_por_defecto(formulario):
    formulario.txt_etiquetas.setText("web, prod")
    estados = estados_opciones()
    estados[OpcionA.ETIQUETAS] = estado_sin_version(OpcionA.ETIQUETAS, "9.9")
    formulario.establecer_disponibilidad(estados)
    assert formulario.configuracion().etiquetas_usuario == ()  # CA-A0.4.3: no se envía


# --- CA-A2.1.5 (clon) y CA-A2.3.3 ---


def test_ca_a2_1_5_en_clonar_las_notas_no_se_deshabilitan_por_falta_de_config_options(qtbot):
    inv = inv_origen()
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inv)
    f.selector_origen.establecer_capacidades(caps_origen(inv))
    f.selector_origen.establecer_catalogo(
        [volumen("local:iso/a.iso")], [plantilla_pve()], nodo="pve"
    )
    f.selector_origen.opciones[OrigenSO.CLONAR_PLANTILLA].setChecked(True)
    f.establecer_disponibilidad(estados_opciones(permisos_fase_a(quitar=("VM.Config.Options",))))
    assert f.chk_notas_origen.isEnabled()
    assert f.txt_notas.isEnabled()
    # El privilegio sigue haciendo falta para las demás opciones del mismo grupo.
    assert not f.chk_proteger.isEnabled()


def test_ca_a2_3_3_con_notas_de_origen_desmarcada_la_casilla_del_usuario_esta_deshabilitada(
    formulario,
):
    aplicar(formulario)
    formulario.chk_notas_origen.setChecked(True)
    assert formulario.chk_notas_usuario.isEnabled()
    formulario.chk_notas_origen.setChecked(False)
    assert formulario.chk_notas_usuario.isVisible()  # deshabilitada, no oculta
    assert not formulario.chk_notas_usuario.isEnabled()


def test_ca_a2_3_3_el_usuario_marcado_no_se_envia_si_se_desmarcan_las_notas_de_origen(formulario):
    aplicar(formulario)
    formulario.chk_notas_origen.setChecked(True)
    formulario.chk_notas_usuario.setChecked(True)
    formulario.chk_notas_origen.setChecked(False)
    cfg = formulario.configuracion()
    assert not (cfg.notas_origen and cfg.notas_usuario)


# --- CA-A4.2.x: pools ---


def textos_pool(f: FormularioVM) -> str:
    return textos_de(f.fila_pool) + "\n" + explicacion(f.combo_pool)


def items_pool(f: FormularioVM) -> list[str]:
    return [f.combo_pool.itemText(i) for i in range(f.combo_pool.count())]


def test_ca_a4_2_1_sin_pool_audit_la_lista_se_deshabilita_y_nombra_privilegio_y_ruta(formulario):
    aplicar(formulario, pools=PoolsServidor(EstadoPools.SIN_PERMISO))
    assert formulario.combo_pool.isVisible()
    assert not formulario.combo_pool.isEnabled()
    texto = textos_pool(formulario)
    assert "Pool.Audit" in texto
    assert "/pool" in texto


def test_ca_a4_2_2_con_pool_audit_y_sin_pools_solo_ofrece_ninguno_y_avisa_sin_deshabilitar(
    formulario,
):
    aplicar(formulario, pools=pools_ok())
    assert formulario.combo_pool.isEnabled()
    assert items_pool(formulario) == ["Ninguno"]
    assert "No hay pools" in textos_pool(formulario)
    assert "Pool.Audit" not in textos_pool(formulario)


def test_ca_a4_2_3_solo_se_ofrecen_los_pools_que_devuelve_la_api(formulario):
    aplicar(formulario, pools=pools_ok("a"))
    assert items_pool(formulario) == ["Ninguno", "a"]
    assert formulario.combo_pool.isEnabled()


def test_ca_a4_2_4_permiso_desconocido_y_sin_pools_da_un_aviso_neutro(formulario):
    aplicar(formulario, pools=PoolsServidor(EstadoPools.DESCONOCIDO))
    texto = textos_pool(formulario)
    assert "No sabemos si puedes ver" in texto
    assert "Pool.Audit" in texto  # nombra qué no se pudo comprobar
    assert formulario.combo_pool.isEnabled()  # aviso neutro: no se bloquea


def test_ca_a4_2_5_fallo_de_lectura_deshabilita_la_lista_sin_bloquear_el_resto(formulario):
    aplicar(formulario, pools=PoolsServidor(EstadoPools.ERROR))
    assert not formulario.combo_pool.isEnabled()
    assert "No se pudo leer la lista de pools" in textos_pool(formulario)
    assert formulario.nombre.isEnabled() and formulario.chk_encender.isEnabled()


def test_ca_a4_2_1_a_5_los_cuatro_avisos_de_pool_son_distintos(formulario):
    textos = []
    for estado in (
        PoolsServidor(EstadoPools.SIN_PERMISO),
        pools_ok(),
        PoolsServidor(EstadoPools.DESCONOCIDO),
        PoolsServidor(EstadoPools.ERROR),
    ):
        aplicar(formulario, pools=estado)
        textos.append(textos_pool(formulario).strip())
    assert all(textos)
    assert len(set(textos)) == 4


# --- CA-A5.1.x y CA-A5.2.x: MTU y límite ---


def test_ca_a5_1_7_en_modo_basico_mtu_y_limite_no_se_muestran_y_no_se_envian(qtbot):
    f = FormularioVM()
    qtbot.addWidget(f)
    f.show()
    f.establecer_inventario(inventario_individual())
    f.establecer_modo(False)
    fila = f.tabla_redes._filas[0]
    assert not fila.mtu.isVisible()
    assert not fila.limite.isVisible()
    red = f.configuracion().redes[0]
    assert red.mtu is None and red.limite_mb is None


def test_ca_a5_1_7_en_modo_avanzado_mtu_y_limite_si_se_muestran(formulario):
    fila = formulario.tabla_redes._filas[0]
    assert fila.mtu.isVisible() and fila.limite.isVisible()


def test_ca_a5_1_8_sin_vm_config_network_mtu_y_limite_se_deshabilitan_con_explicacion(formulario):
    aplicar(formulario, quitar=("VM.Config.Network",))
    fila = formulario.tabla_redes._filas[0]
    assert fila.mtu.isVisible() and fila.limite.isVisible()
    assert not fila.mtu.isEnabled()
    assert not fila.limite.isEnabled()
    for control in (fila.mtu, fila.limite):
        assert "VM.Config.Network" in explicacion(control)
        assert "/vms" in explicacion(control)
    assert "VM.Config.Network" in textos_de(formulario.tabla_redes)


def test_ca_a5_2_1_con_otro_modelo_el_mtu_se_deshabilita_y_explica_que_solo_es_virtio(formulario):
    aplicar(formulario)
    fila = formulario.tabla_redes._filas[0]
    assert fila.mtu.isEnabled()
    fila.modelo.setCurrentIndex(fila.modelo.findData(ModeloRed.E1000))
    assert not fila.mtu.isEnabled()
    assert "solo se aplica a tarjetas VirtIO" in explicacion(fila.mtu)
    assert fila.limite.isEnabled()  # CA-A5.2.3: el límite vale para todos los modelos
    assert formulario.configuracion().redes[0].mtu is None


def test_ca_a5_2_2_al_dejar_virtio_el_mtu_vuelve_a_heredar_p18(formulario):
    aplicar(formulario)
    fila = formulario.tabla_redes._filas[0]
    fila.mtu.setCurrentIndex(-1)
    fila.mtu.setEditText("1500")
    assert formulario.configuracion().redes[0].mtu == 1500
    fila.modelo.setCurrentIndex(fila.modelo.findData(ModeloRed.E1000))
    assert fila.mtu.currentIndex() == 0  # «Heredar del bridge»
    assert formulario.configuracion().redes[0].mtu is None
    # Al volver a VirtIO el valor no reaparece solo.
    fila.modelo.setCurrentIndex(fila.modelo.findData(ModeloRed.VIRTIO))
    assert formulario.configuracion().redes[0].mtu is None


def test_ca_a5_2_2_el_limite_se_conserva_al_cambiar_de_modelo(formulario):
    aplicar(formulario)
    fila = formulario.tabla_redes._filas[0]
    fila.limite.setText("12.5")
    fila.modelo.setCurrentIndex(fila.modelo.findData(ModeloRed.E1000))
    assert formulario.configuracion().redes[0].limite_mb == 12.5


# --- CL-A15: cambio de servidor ---


def test_cl_a15_al_perder_un_privilegio_el_valor_vuelve_al_por_defecto_con_aviso(formulario):
    aplicar(formulario)
    formulario.chk_encender.setChecked(True)
    formulario.chk_proteger.setChecked(True)
    cambios: list[bool] = []
    formulario.cambiado.connect(lambda: cambios.append(True))
    aplicar(formulario, quitar=("VM.PowerMgmt", "VM.Config.Options"))
    cfg = formulario.configuracion()
    assert not cfg.encender and not cfg.proteger
    assert "Se restableció" in textos_de(formulario.fila_encender)
    assert "Se restableció" in textos_de(formulario.fila_proteger)
    assert cambios, "el formulario debe pedir revalidar"


def test_cl_a15_mtu_y_limite_escritos_se_restablecen_si_el_nuevo_servidor_no_los_permite(
    formulario,
):
    aplicar(formulario)
    fila = formulario.tabla_redes._filas[0]
    fila.mtu.setCurrentIndex(-1)
    fila.mtu.setEditText("9000")
    fila.limite.setText("50")
    aplicar(formulario, quitar=("VM.Config.Network",))
    red = formulario.configuracion().redes[0]
    assert red.mtu is None and red.limite_mb is None
    assert "Se restableció" in textos_de(formulario.tabla_redes)


def test_cl_a15_un_pool_elegido_que_el_nuevo_servidor_no_tiene_se_restablece_con_aviso(formulario):
    aplicar(formulario, pools=pools_ok("produccion", "pruebas"))
    formulario.combo_pool.setCurrentIndex(formulario.combo_pool.findData("produccion"))
    assert formulario.configuracion().pool == "produccion"
    aplicar(formulario, pools=pools_ok("otro"))
    assert formulario.configuracion().pool is None
    assert "Se restableció" in textos_de(formulario.fila_pool)


def test_cl_a15_un_pool_elegido_se_restablece_si_el_nuevo_servidor_no_deja_ver_pools(formulario):
    aplicar(formulario, pools=pools_ok("produccion"))
    formulario.combo_pool.setCurrentIndex(formulario.combo_pool.findData("produccion"))
    aplicar(formulario, pools=PoolsServidor(EstadoPools.SIN_PERMISO))
    assert formulario.configuracion().pool is None
    assert "Se restableció" in textos_de(formulario.fila_pool)


def test_cl_a15_al_volver_el_privilegio_el_control_se_habilita_y_sin_aviso(formulario):
    aplicar(formulario, quitar=("VM.PowerMgmt",))
    assert not formulario.chk_encender.isEnabled()
    aplicar(formulario)
    assert formulario.chk_encender.isEnabled()
    assert "VM.PowerMgmt" not in textos_de(formulario.fila_encender)


# --- RNF-A8: accesibilidad ---


def controles_nuevos(f: FormularioVM):
    return [
        f.chk_encender,
        f.chk_arranque_auto,
        f.chk_notas_origen,
        f.chk_notas_usuario,
        f.txt_notas,
        f.txt_etiquetas,
        f.combo_pool,
        f.txt_orden,
        f.txt_espera,
        f.chk_proteger,
    ]


def etiquetas_asociadas(f: FormularioVM, control) -> list[QLabel]:
    return [lbl for lbl in f.findChildren(QLabel) if lbl.buddy() is control]


def test_rnf_a8_cada_control_nuevo_tiene_nombre_accesible_o_etiqueta_asociada(formulario):
    for c in controles_nuevos(formulario):
        tiene_nombre = bool(c.accessibleName().strip())
        tiene_etiqueta = bool(etiquetas_asociadas(formulario, c))
        texto_propio = isinstance(c, QCheckBox) and bool(c.text().strip())
        assert tiene_nombre or tiene_etiqueta or texto_propio, c.objectName() or type(c).__name__


def test_rnf_a8_los_nombres_accesibles_de_los_controles_nuevos_son_distintos(formulario):
    nombres = [c.accessibleName() for c in controles_nuevos(formulario) if c.accessibleName()]
    assert len(nombres) == len(set(nombres))
    assert any("Encender" in n for n in nombres)


def test_rnf_a8_mtu_y_limite_de_cada_tarjeta_tienen_nombre_accesible_con_su_numero(formulario):
    formulario.tabla_redes.agregar_red()
    filas = formulario.tabla_redes._filas
    assert len(filas) == 2
    nombres = []
    for n, fila in enumerate(filas):
        assert f"net{n}" in fila.mtu.accessibleName()
        assert f"net{n}" in fila.limite.accessibleName()
        nombres += [fila.mtu.accessibleName(), fila.limite.accessibleName()]
    assert len(set(nombres)) == 4


def test_rnf_a8_el_orden_de_tabulacion_sigue_el_orden_visual(formulario):
    visual = orden_visual(controles_nuevos(formulario), formulario)
    assert len(visual) == len(controles_nuevos(formulario))  # en avanzado se ven todos
    cadena = cadena_de_foco(formulario.chk_encender)
    posiciones = [cadena.index(c) for c in visual]
    assert posiciones == sorted(posiciones), "Tab no recorre los controles como se ven"


def test_rnf_a8_las_notas_dejan_pasar_el_tabulador_al_campo_siguiente(formulario):
    assert isinstance(formulario.txt_notas, QPlainTextEdit)
    assert formulario.txt_notas.tabChangesFocus()


def test_rnf_a8_con_un_control_deshabilitado_la_explicacion_es_visible_no_solo_en_tooltip(
    formulario,
):
    aplicar(formulario, quitar=("VM.PowerMgmt",))
    assert "VM.PowerMgmt" in textos_de(formulario.fila_encender)


# --- Ida y vuelta configuracion() <-> _aplicar_configuracion_interna ---


def cfg_con_todo() -> ConfiguracionVM:
    return ConfiguracionVM(
        vmid=150,
        nombre="srv-web-01",
        nodo="pve",
        encender=True,
        arranque_auto=True,
        arranque_orden=3,
        arranque_espera=30,
        notas_origen=True,
        notas_usuario=True,
        notas="primera línea\nsegunda línea\tcon tabulador",
        etiquetas_usuario=("web", "produccion"),
        pool="produccion",
        proteger=True,
        redes=[
            InterfazRed("vmbr0", ModeloRed.VIRTIO, 20, mtu=MTU_IGUAL_BRIDGE, limite_mb=12.5),
            InterfazRed("vmbr1", ModeloRed.E1000, None, mtu=None, limite_mb=100.0),
        ],
    )


CAMPOS_FASE_A = (
    "encender",
    "arranque_auto",
    "arranque_orden",
    "arranque_espera",
    "notas_origen",
    "notas_usuario",
    "notas",
    "etiquetas_usuario",
    "pool",
    "proteger",
)


def test_ida_y_vuelta_del_formulario_conserva_todas_las_opciones_nuevas(formulario):
    aplicar(formulario, pools=pools_ok("produccion", "pruebas"))
    entrada = cfg_con_todo()
    formulario._aplicar_configuracion_interna(entrada, None, None)
    salida = formulario.configuracion()
    for campo in CAMPOS_FASE_A:
        assert getattr(salida, campo) == getattr(entrada, campo), campo
    assert [(r.mtu, r.limite_mb) for r in salida.redes] == [(1, 12.5), (None, 100.0)]


@pytest.mark.parametrize("mtu", [None, MTU_IGUAL_BRIDGE, 576, 1500, 9000, 65520])
def test_ida_y_vuelta_del_formulario_conserva_cada_valor_de_mtu(formulario, mtu):
    aplicar(formulario)
    cfg = ConfiguracionVM(vmid=150, nombre="x", nodo="pve", redes=[InterfazRed("vmbr0", mtu=mtu)])
    formulario._aplicar_configuracion_interna(cfg, None, None)
    assert formulario.configuracion().redes[0].mtu == mtu


def test_ida_y_vuelta_con_valores_por_defecto_deja_los_de_0_5_1_salvo_notas_de_origen(formulario):
    aplicar(formulario)
    cfg = ConfiguracionVM(vmid=150, nombre="x", nodo="pve")
    formulario._aplicar_configuracion_interna(cfg, None, None)
    salida = formulario.configuracion()
    por_defecto = ConfiguracionVM(vmid=150, nombre="x", nodo="pve")
    for campo in CAMPOS_FASE_A:
        assert getattr(salida, campo) == getattr(por_defecto, campo), campo


def test_ida_y_vuelta_el_formulario_nuevo_trae_notas_de_origen_marcada_y_lo_demas_por_defecto(
    formulario,
):
    cfg = formulario.configuracion()
    assert cfg.notas_origen is True  # DT-A1: el valor por defecto del formulario
    assert not cfg.notas_usuario
    assert not cfg.encender and not cfg.arranque_auto and not cfg.proteger
    assert cfg.pool is None and cfg.etiquetas_usuario == () and cfg.notas == ""
    assert cfg.arranque_orden is None and cfg.arranque_espera is None


def test_ida_y_vuelta_una_opcion_bloqueada_no_se_reaplica_desde_un_archivo(formulario):
    # CA-A0.3.3: con el control deshabilitado, lo que fija un archivo no se aplica.
    aplicar(formulario, quitar=("VM.PowerMgmt",))
    formulario._aplicar_configuracion_interna(cfg_con_todo(), None, None)
    salida = formulario.configuracion()
    assert salida.encender is False
    assert not formulario.chk_encender.isEnabled()


def test_ida_y_vuelta_pool_de_un_archivo_que_el_servidor_no_tiene_no_se_pierde_en_silencio(
    formulario,
):
    aplicar(formulario, pools=pools_ok("otro"))
    formulario._aplicar_configuracion_interna(cfg_con_todo(), None, None)
    textos = [formulario.combo_pool.itemText(i) for i in range(formulario.combo_pool.count())]
    # O bien se conserva marcado como inexistente (la validación lo bloquea) o se restablece
    # con aviso: nunca se envía un pool inexistente sin decir nada.
    pool = formulario.configuracion().pool
    assert pool is None or any("produccion" in t for t in textos)
