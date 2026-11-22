"""Corrección D de la revisión F6 (0.7.0): interfaz y textos de los códigos nuevos del núcleo.

Derivadas de docs/arquitectura/fase-b.md §17: B1 (contraseña corta = error), B2 (suma obligatoria
y débil, máquina anterior sin borrar), B3 (permisos de snippets en 8.x), B6 (olvidar la vista
previa del CSV), I3 (certificado), M3 (escapado), QA-M4, QA-M5, QA-M6, QA-B2 y QA-B6, y el
nuevo contrato de ``EsperaIp.cancelar`` (bloquea: nunca desde el hilo de la interfaz).
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QThreadPool

from proxlaunch.interfaz import trabajadores as trab
from proxlaunch.interfaz import ventana_principal as vp
from proxlaunch.interfaz.ayuda import privilegios_opcionales_guia, texto_pedir_al_administrador
from proxlaunch.interfaz.dialogos.importar_csv import DialogoImportarCsv
from proxlaunch.interfaz.textos import texto_error, texto_problema
from proxlaunch.interfaz.trabajadores import (
    Lanzador,
    cancelar_espera_en_fondo,
    deshacer_lotes,
    olvidar_secretos_de_filas,
    reintentar_ajustes_lote,
)
from proxlaunch.interfaz.vistas.seccion_cloudinit import SeccionCloudInit
from proxlaunch.nucleo.capacidades import Capacidades
from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.servicios.creacion import AVISO_ENCENDIDO_FALLIDO
from proxlaunch.nucleo.validacion import Problema, Severidad

from . import test_ventana_principal as _base
from .apoyo_fase_a import ClienteDeshacerFalso, lote_creado
from .apoyo_fase_b import CENTINELA, disponibilidad, info_plantilla

entorno = _base.entorno


@pytest.fixture(autouse=True)
def _siempre_limpio(limpieza):
    """Cierra sin bloquear ni preguntar."""


@pytest.fixture
def cliente():
    return ClienteDeshacerFalso()


# --- Textos de los códigos nuevos -------------------------------------------------------------


def prob(codigo: str, severidad: Severidad = Severidad.ERROR, **params: str) -> Problema:
    return Problema("campo", codigo, severidad, dict(params))


def test_v_b40_dice_que_la_contrasena_ya_no_esta_en_memoria():
    texto = texto_problema(prob("V-B40", motivo="olvidada"))
    assert "ya no está en memoria" in texto and "vuelve a escribirla" in texto


def test_v_b25_corta_pide_al_menos_8_caracteres():
    texto = texto_problema(prob("V-B25", motivo="corta"))
    assert "al menos 8 caracteres" in texto


def test_v_b05_suma_obligatoria_explica_por_que_y_donde_se_publica():
    texto = texto_problema(prob("V-B05", motivo="suma_obligatoria"))
    assert "http://" in texto and "certificados" in texto
    assert "SHA-256 o SHA-512" in texto and "SHA256SUMS" in texto


@pytest.mark.parametrize(("algoritmo", "nombre"), [("md5", "MD5"), ("sha1", "SHA-1")])
def test_v_b05_suma_debil_nombra_el_algoritmo(algoritmo, nombre):
    texto = texto_problema(prob("V-B05", Severidad.AVISO, motivo="suma_debil", algoritmo=algoritmo))
    assert nombre in texto and "SHA-256" in texto


def test_el_aviso_de_maquina_anterior_sin_borrar_nombra_la_maquina_y_pide_borrarla_a_mano():
    from proxlaunch.interfaz.textos import texto_aviso_origen

    texto = texto_aviso_origen("maquina_anterior_sin_borrar:105:ubuntu-base")
    assert "ubuntu-base" in texto and "105" in texto
    assert "a mano" in texto and "maquina_anterior" not in texto


def test_una_respuesta_demasiado_grande_tiene_texto_propio():
    texto = texto_error(
        ErrorProxLaunch(CodigoError.DESCONOCIDO, {"motivo": "respuesta_demasiado_grande"})
    )
    assert "demasiado grande" in texto


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        ("cloudinit.usuario", "el usuario"),
        ("cloudinit.tarjetas[1].ip", "la IP de la tarjeta de red 2"),
        ("cloudinit.tarjetas[0].puerta", "la puerta de enlace de la tarjeta de red 1"),
        ("cloudinit.dns", "los servidores DNS"),
    ],
)
def test_un_parametro_invalido_de_cloudinit_nombra_el_campo_de_forma_legible(campo, esperado):
    texto = texto_error(ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": campo}))
    assert esperado in texto and "cloudinit." not in texto and "[" not in texto


# --- B1: la contraseña corta es un error que bloquea ------------------------------------------


def test_b1_una_contrasena_corta_es_un_error_y_no_crea_el_secreto(qtbot):
    s = SeccionCloudInit()
    qtbot.addWidget(s)
    s.show()
    s.establecer_info(info_plantilla(), disponibilidad())
    for campo in (s.txt_contrasena, s.txt_repeticion):
        campo.setText("corta12")
        campo.textEdited.emit("corta12")
    problemas = [p for p in s.problemas() if p.codigo == "V-B25"]
    assert problemas and all(p.severidad == Severidad.ERROR for p in problemas)
    ci = s.configuracion()
    assert ci is None or ci.contrasena is None


# --- B3: permisos de snippets en 8.x ----------------------------------------------------------


def test_b3_en_8x_la_guia_nombra_el_almacen_de_snippets_y_alloc_space_va_primero():
    lineas = privilegios_opcionales_guia(Capacidades((8, 4), False), "local")
    espacio = next(i for i, ln in enumerate(lineas) if ln.startswith("Datastore.AllocateSpace"))
    asignar = next(i for i, ln in enumerate(lineas) if ln.startswith("Datastore.Allocate "))
    assert espacio < asignar
    assert "«/storage/local»" in lineas[espacio] and "«/storage/local»" in lineas[asignar]
    assert "snippets" in lineas[espacio]  # texto propio de AllocateSpace en 8.x
    assert "no está verificado" in lineas[asignar]


def test_b3_sin_almacen_conocido_la_ruta_tiene_un_texto_propio_sin_marcadores():
    lineas = privilegios_opcionales_guia(Capacidades((8, 4), False), None)
    texto = "\n".join(lineas)
    assert "<almacén" not in texto and "/storage/(el almacenamiento de snippets)" in texto


def test_b3_en_9x_no_se_proponen_los_privilegios_de_snippets_de_8x():
    lineas = privilegios_opcionales_guia(Capacidades((9, 2), False), "local")
    assert not [ln for ln in lineas if ln.startswith("Datastore.Allocate")]


def test_b3_el_texto_para_el_administrador_lleva_el_almacen():
    texto = texto_pedir_al_administrador(Capacidades((8, 4), False), "snips")
    assert "/storage/snips" in texto


def test_b3_el_formulario_elige_el_almacen_de_snippets_del_inventario(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    # El inventario de pruebas no tiene almacén de snippets: la guía usa la ruta genérica.
    assert v.formulario.almacen_snippets() in (None, *v.formulario.storages_snippets())


# --- Contrato de EsperaIp.cancelar: bloquea, nunca desde el hilo de la interfaz ---------------


class EsperaBloqueante:
    """``cancelar`` espera una señal, como la real hasta que acaba la petición en vuelo."""

    def __init__(self) -> None:
        self.liberar = threading.Event()
        self.hilos: list[int] = []
        self.terminadas = 0

    def ejecutar(self) -> dict:
        return {}

    def cancelar(self, vmids=None) -> None:
        self.hilos.append(threading.get_ident())
        self.liberar.wait(5)
        self.terminadas += 1


def test_cancelar_en_fondo_devuelve_enseguida_y_corre_en_otro_hilo():
    espera = EsperaBloqueante()
    inicio = time.monotonic()
    hilo = cancelar_espera_en_fondo(espera)  # type: ignore[arg-type]
    assert time.monotonic() - inicio < 1  # no se bloquea esperando la petición en vuelo
    assert hilo.is_alive()
    espera.liberar.set()
    hilo.join(3)
    assert espera.terminadas == 1 and espera.hilos == [hilo.ident]
    assert threading.get_ident() not in espera.hilos


def test_el_trabajador_de_la_espera_cancela_en_fondo(qtbot):
    espera = EsperaBloqueante()
    trabajador = trab._TrabajadorEspera(espera)  # type: ignore[arg-type]
    inicio = time.monotonic()
    trabajador.cancelar()  # lo llama la interfaz (cancelar_todos al cerrar)
    assert time.monotonic() - inicio < 1
    espera.liberar.set()
    assert trab.esperar_cancelaciones(3000)
    assert espera.terminadas == 1


def test_deshacer_lotes_cancela_las_esperas_en_su_propio_hilo_antes_de_borrar():
    eventos: list[str] = []

    class Espera:
        def cancelar(self, vmids=None) -> None:
            eventos.append(f"cancelar:{sorted(vmids)}:{threading.get_ident()}")

    resultado = deshacer_lotes(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        [],
        lambda r: None,
        ControlLote(),
        esperas_a_cancelar=[(Espera(), frozenset({101, 102}))],  # type: ignore[list-item]
    )
    assert resultado == []
    assert eventos == [f"cancelar:[101, 102]:{threading.get_ident()}"]  # síncrono, en este hilo


def test_qa_b6_al_cerrar_se_vacia_la_cola_de_la_espera_y_se_espera_con_tope(qtbot):
    lanzador = Lanzador()
    llamadas: list[object] = []
    lanzador._pool_espera = SimpleNamespace(  # type: ignore[assignment]
        clear=lambda: llamadas.append("clear"),
        waitForDone=lambda ms: llamadas.append(("espera", ms)) or True,
    )
    assert lanzador.esperar(3000) in (True, False)
    assert llamadas == ["clear", ("espera", 3000)]
    assert isinstance(QThreadPool.globalInstance(), QThreadPool)


# --- Ventana: Deshacer, dejar de esperar, QA-B2 -----------------------------------------------


class EsperaFalsa:
    def __init__(self) -> None:
        self.cancelaciones: list[tuple[int, object]] = []
        self.sin_mas = 0
        self.anadidas: list[tuple] = []

    def cancelar(self, vmids=None) -> None:
        self.cancelaciones.append((threading.get_ident(), vmids))

    def sin_mas_objetivos(self) -> None:
        self.sin_mas += 1

    def anadir(self, vmid, nodo, plazo_s, ip_configurada=None) -> None:
        self.anadidas.append((vmid, nodo, plazo_s, ip_configurada))


def test_dejar_de_esperar_la_ip_no_bloquea_la_interfaz(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    espera = EsperaFalsa()
    liberar = threading.Event()
    original = espera.cancelar

    def lenta(vmids=None):
        liberar.wait(5)
        original(vmids)

    espera.cancelar = lenta  # type: ignore[method-assign]
    v._lote.esperas.append(espera)
    inicio = time.monotonic()
    v._dejar_de_esperar_ip()
    assert time.monotonic() - inicio < 1
    liberar.set()
    qtbot.waitUntil(lambda: espera.cancelaciones != [], timeout=3000)
    assert espera.cancelaciones[0][0] != threading.get_ident()


def test_qa_b2_el_lote_terminado_y_el_fallo_del_motor_cierran_las_esperas(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    espera = EsperaFalsa()
    v._lote.esperas.append(espera)
    v._al_lote_terminado(v._lote, v._lote.libro)
    assert espera.sin_mas == 1
    v._fallo_lote(v._lote, ErrorProxLaunch(CodigoError.DESCONOCIDO))
    assert espera.sin_mas == 2  # idempotente en la espera real


# --- QA-M6: «Reintentar ajustes» entrega a una EsperaIp nueva ---------------------------------


def marcar_entrada(libro, vmid, estado, avisos=()):
    return libro.resolver(vmid, estado, t_fin=0.0, error=None, avisos=tuple(avisos))


def test_qa_m6_reintentar_ajustes_entrega_a_la_espera_las_maquinas_que_enciende(
    qtbot, entorno, cliente, monkeypatch
):
    v = lote_creado(qtbot, entorno, cliente)
    libro = v._lote.libro
    for e in libro.instantanea():
        e.elemento.cfg.encender = True
        e.elemento.cfg.esperar_ip = True
    marcar_entrada(libro, 102, EstadoMV.CON_AVISOS, (AVISO_ENCENDIDO_FALLIDO,))
    monkeypatch.setattr(trab, "reintentar_ajustes", lambda *a, **k: None)
    espera = EsperaFalsa()

    devuelto = reintentar_ajustes_lote(
        v._lote.sesion,
        v._deps.reloj,
        libro,
        (101, 102, 103),
        v._lote.inv,
        lambda e: None,
        ControlLote(),
        None,
        espera,  # type: ignore[arg-type]
    )

    assert devuelto is libro
    assert sorted(a[0] for a in espera.anadidas) == [101, 103]  # 102 no se encendió


def test_qa_m6_sin_esperar_ip_no_se_crea_ninguna_espera(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    lote = v._lote
    assert v._crear_espera(lote, lote.libro, solo_pendientes=False, solo_vmids={101}) is None
    for e in lote.libro.instantanea():
        e.elemento.cfg.encender = True
        e.elemento.cfg.esperar_ip = True
    espera = v._crear_espera(lote, lote.libro, solo_pendientes=False, solo_vmids={101})
    assert espera is not None and espera in lote.esperas


# --- QA-M4 y QA-M5: cuándo se olvida la contraseña --------------------------------------------


def poner_secreto_en_el_plan(lote) -> Secreto:
    secreto = Secreto(CENTINELA)
    for e in lote.plan.elementos:
        e.cfg.cloudinit = ConfigCloudInit(contrasena=secreto)
    return secreto


def test_qa_m5_volver_no_olvida_la_contrasena_mientras_el_lote_se_pueda_reintentar(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    secreto = poner_secreto_en_el_plan(v._lote)
    marcar_entrada(v._lote.libro, 101, EstadoMV.PARCIAL, ("ajuste_pendiente:contrasena",))
    v.progreso_lote.actualizar(v._lote.libro.instantanea())
    v._volver_de_lote()
    assert secreto.definido  # sigue reintentable: se conserva


def test_qa_m5_volver_con_el_lote_cerrado_de_verdad_si_la_olvida(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    secreto = poner_secreto_en_el_plan(v._lote)
    v.progreso_lote.actualizar(v._lote.libro.instantanea())
    v._volver_de_lote()  # todas las máquinas quedaron bien: nada que reintentar
    assert not secreto.definido


def test_qa_m5_lanzar_con_una_contrasena_olvidada_se_explica_como_vuelve_a_escribirla():
    texto = texto_problema(
        Problema("cloudinit.contrasena", "V-B40", Severidad.ERROR, {"motivo": "olvidada"})
    )
    assert "vuelve a escribirla" in texto


def fila_con_secreto(secreto: Secreto):
    cfg = SimpleNamespace(cloudinit=ConfigCloudInit(contrasena=secreto))
    return SimpleNamespace(cfg=cfg, opciones=None, numero=2)


def importado_con(secreto: Secreto):
    resultado = SimpleNamespace(filas=(fila_con_secreto(secreto),))
    return vp._OrigenLote("csv", "x.csv", None, resultado, 1)  # type: ignore[arg-type]


def test_qa_m4_al_descartar_un_lote_importado_se_olvidan_las_contrasenas_de_sus_filas(
    qtbot, entorno
):
    v = entorno.ventana
    secreto = Secreto(CENTINELA)
    v._origen_lote = importado_con(secreto)
    v._olvidar_filas_en_pantalla()
    assert not secreto.definido


def test_qa_m4_al_desconectar_se_olvidan_las_de_las_filas_importadas(qtbot, entorno, cliente):
    v = lote_creado(qtbot, entorno, cliente)
    secreto = Secreto(CENTINELA)
    v._origen_lote = importado_con(secreto)
    v._cerrar_sesion_confirmada()
    assert not secreto.definido


def test_qa_m4_no_se_olvida_la_contrasena_de_un_lote_que_aun_puede_reintentarse(
    qtbot, entorno, cliente
):
    v = lote_creado(qtbot, entorno, cliente)
    secreto = poner_secreto_en_el_plan(v._lote)
    marcar_entrada(v._lote.libro, 101, EstadoMV.PARCIAL, ("ajuste_pendiente:contrasena",))
    v._origen_lote = importado_con(secreto)  # las filas comparten la contraseña del lote
    v._olvidar_filas_en_pantalla()
    assert secreto.definido


def test_qa_m4_se_puede_conservar_la_contrasena_del_lote_nuevo():
    secreto, otra = Secreto(CENTINELA), Secreto("otra-contrasena-larga")
    filas = [fila_con_secreto(secreto), fila_con_secreto(otra)]
    assert olvidar_secretos_de_filas(filas, salvo=[otra]) == 1
    assert not secreto.definido and otra.definido


# --- B6: la vista previa del CSV olvida las contraseñas ---------------------------------------


def dialogo_csv(qtbot) -> DialogoImportarCsv:
    from proxlaunch.interfaz import textos
    from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
    from proxlaunch.nucleo.perfiles_maquina.modelos import ID_PREDETERMINADO

    from .apoyo import inventario_cluster

    d = DialogoImportarCsv(
        None,
        perfiles=perfiles_fabrica(textos.textos_perfiles_fabrica()),
        perfil_base_id=ID_PREDETERMINADO,
        inv=inventario_cluster(),
        nodo_referencia=None,
        lanzador=Lanzador(),
        alias_extra=textos.alias_columnas_csv(),
        encender_base=True,
    )
    qtbot.addWidget(d)
    d.show()
    return d


def csv_con_contrasena(tmp_path):
    from .apoyo_mvp3 import escribir_csv

    base = ["nombre", "nucleos", "memoria", "disco", "almacenamiento", "red"]
    fila = ["web-01", 2, "2 GiB", "20 GiB", "local-lvm", "vmbr0"]
    return escribir_csv(tmp_path / "f.csv", [base + ["ci_contrasena"], fila + [CENTINELA]])


def secretos_del_dialogo(d) -> list[Secreto]:
    return trab.secretos_de_filas(d.resultado.filas)


def test_b6_cancelar_el_dialogo_olvida_las_contrasenas_y_suelta_la_tabla(qtbot, tmp_path):
    d = dialogo_csv(qtbot)
    d.cargar_archivo(csv_con_contrasena(tmp_path))
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    secretos = secretos_del_dialogo(d)
    assert secretos and all(s.definido for s in secretos)
    d.reject()
    assert not any(s.definido for s in secretos)
    assert d.tabla_csv is None and d.resultado is None


def test_b6_reinterpretar_olvida_las_contrasenas_de_la_vista_previa_anterior(qtbot, tmp_path):
    d = dialogo_csv(qtbot)
    d.cargar_archivo(csv_con_contrasena(tmp_path))
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    anteriores = secretos_del_dialogo(d)
    d._lanzar_reinterpretacion()
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    nuevas = secretos_del_dialogo(d)
    assert not any(s.definido for s in anteriores)
    assert nuevas and all(s.definido for s in nuevas)
    d.reject()


def test_b6_aceptar_conserva_la_contrasena_de_la_fila_que_se_acepta(qtbot, tmp_path, monkeypatch):
    d = dialogo_csv(qtbot)
    d.cargar_archivo(csv_con_contrasena(tmp_path))
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    secretos = secretos_del_dialogo(d)
    elegidas = tuple(f.numero for f in d.resultado.filas)
    monkeypatch.setattr(d, "numeros_elegidos", lambda: elegidas)
    d.accept()
    assert all(s.definido for s in secretos)
    assert d.tabla_csv is not None  # la ventana la necesita para «Revisar filas…»
    olvidar_secretos_de_filas(d.resultado.filas)


def test_b6_un_resultado_ajeno_no_se_olvida_al_cancelar(qtbot, tmp_path):
    """«Revisar filas…» muestra el resultado del lote que ya está en pantalla: no es del diálogo."""
    d = dialogo_csv(qtbot)
    d.cargar_archivo(csv_con_contrasena(tmp_path))
    qtbot.waitUntil(lambda: d.resultado is not None and not d.ocupado, timeout=5000)
    tabla, resultado = d.tabla_csv, d.resultado
    d._resultado_propio = False  # como tras ``mostrar_resultado(..., propio=False)``
    d.reject()
    assert all(s.definido for s in trab.secretos_de_filas(resultado.filas))
    olvidar_secretos_de_filas(resultado.filas)
    assert tabla is not None


# --- I3: sin modo avanzado siempre se verifica el certificado ---------------------------------


@pytest.mark.parametrize(("avanzado", "verifica"), [(False, True), (True, False)])
def test_i3_sin_modo_avanzado_se_verifica_el_certificado_aunque_la_casilla_este_desmarcada(
    qtbot, avanzado, verifica
):
    from proxlaunch.interfaz.dialogos.plantilla_imagen import DialogoPlantillaImagen
    from proxlaunch.nucleo.reloj import RelojSimulado

    from .apoyo import sesion_falsa
    from .apoyo_mvp4 import ServicioTransferenciasFalso, inv_origen
    from .test_fase_b_plantilla_imagen import ClienteB2, FabricaCreacionFalsa

    d = DialogoPlantillaImagen(
        sesion=sesion_falsa(cliente=ClienteB2(), version=(8, 4)),
        reloj=RelojSimulado(),
        lanzador=Lanzador(),
        transferencias=ServicioTransferenciasFalso(),
        inv=inv_origen(version=(8, 4)),
        avanzado=avanzado,
        nodo="pve",
        fabrica_creacion=FabricaCreacionFalsa(),
    )
    qtbot.addWidget(d)
    d.casilla_certificados.setChecked(False)  # queda desmarcada, visible o no
    assert d.solicitud.verificar_certificados is verifica
