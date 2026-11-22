"""Correcciones de seguridad y QA de la fase A (0.6.0), segunda ronda (fase A §14 y §15).

Cubre SEG-A-02..08 (núcleo), QA-A-02, 03, 05, 09, 10, 11, 12 y las decisiones S-1. Los hallazgos
de Deshacer (SEG-A-01, QA-A-01, 06, 07, 08) tienen sus propias pruebas. Lo de interfaz está en
``tests/interfaz/test_fase_a_correcciones_2.py``.
"""

from __future__ import annotations

import dataclasses
import logging
import time

import pytest

from proxlaunch.nucleo.archivos.esquema import LectorEsquema
from proxlaunch.nucleo.archivos.esquema_opciones import (
    leer_pool,
    opciones_cfg_a_dict,
    opciones_lote_a_dict,
    opciones_parciales_a_dict,
)
from proxlaunch.nucleo.archivos.texto import contiene_token
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.csv_importacion import unidades
from proxlaunch.nucleo.csv_importacion.modelos import EstadoFila
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV, FilaLote
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.modelos.catalogo import PermisosEfectivos
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.modelos.vm import MAX_LIMITE_MB, InterfazRed, ModeloRed, pool_valido
from proxlaunch.nucleo.opciones.modelos import (
    EstadoPools,
    OpcionesLote,
    OpcionesParciales,
    PoliticaEtiquetas,
    PoolsServidor,
)
from proxlaunch.nucleo.opciones.notas import limpiar_texto_libre
from proxlaunch.nucleo.registro import MASCARA, enmascarar
from proxlaunch.nucleo.servicios.catalogo import leer_politica_etiquetas
from proxlaunch.nucleo.validacion import (
    CODIGOS_SIN_SERVIDOR,
    Severidad,
    validar_sin_servidor,
    validar_vm,
)

from .apoyo_api import TOKEN_ID, TOKEN_SECRETO, TransporteFalso
from .apoyo_fase_a import (
    banco_a,
    catalogo,
    cfg_vm,
    def_lote,
    inv_con,
    plan_de,
)
from .apoyo_lote import ControlAutomatico, envio_incierto, nodo_caido, plantilla
from .apoyo_mvp3 import definicion_filas, importar_csv

CAPS = capacidades_para(Version("9.2.1", 9, 2, 1), None)
TOKEN = "root@pam!ci=0a1b2c3d-1111-2222-3333-444455556666"


def _va(cfg, cat=None, **kw):
    inv = inv_con(cat if cat is not None else catalogo(), **kw)
    return [p for p in validar_vm(cfg, inv, CAPS) if p.codigo.startswith("V-A")]


# --- SEG-A-02 / QA-A-11: contiene_token normaliza ---


@pytest.mark.parametrize(
    "texto",
    [
        "root@pam!c‮i=0a1b2c3d-1111-2222-3333-444455556666",  # bidi en el id
        "root@pam!c​i=0a1b2c3d-1111-2222-3333-444455556666",  # ancho cero en el id
        "root@pam!c\x01i=0a1b2c3d-1111-2222-3333-444455556666",  # control en el id
        "root@pa‮m!ci=0a1b2c3d-1111-2222-3333-444455556666",  # bidi en el realm
        "roo​t@pam!ci=0a1b2c3d-1111-2222-3333-444455556666",  # ancho cero en el usuario
        "root@pa\x01m!ci=0a1b2c3d-1111-2222-3333-444455556666",  # control en el realm
        "root@pam!ci⁠=0a1b2c3d-1111-2222-3333-444455556666",  # unión de palabras
        "PVEAPIToken​=abc",  # la cabecera también
    ],
)
def test_seg_a_02_contiene_token_ve_a_traves_de_los_invisibles(texto):
    assert contiene_token(texto)


def test_seg_a_02_un_texto_normal_con_arroba_y_signos_no_es_un_token():
    assert not contiene_token("escribe a soporte@empresa.com para pedir x=1")
    assert not contiene_token("línea uno\nroot@pam!ci\n=algo")  # el salto sigue separando


@pytest.mark.parametrize("invisible", ["‮", "​", "\x01"])
def test_seg_a_02_csv_notas_con_token_disfrazado_es_error_sin_valor_ni_original(invisible):
    token = f"root@pam!c{invisible}i=0a1b2c3d-1111-2222-3333-444455556666"
    r = importar_csv(["nombre;notas", f"a;{token}"])
    (f,) = r.filas
    assert f.cfg is None and f.problemas
    problema = next(p for p in f.problemas if p.columna == "notas")
    assert problema.valor == ""  # RNF-A2: la celda con error no muestra su valor
    assert "notas" not in f.originales
    assert "0a1b2c3d" not in repr(f)


def test_seg_a_02_csv_pool_con_token_es_error_y_no_se_conserva():
    r = importar_csv(["nombre;pool", f"a;{TOKEN}"])
    (f,) = r.filas
    assert f.cfg is None
    assert any(p.columna == "pool" and p.valor == "" for p in f.problemas)
    assert "pool" not in f.originales


# --- SEG-A-03: rendimiento de la búsqueda de token ---


@pytest.mark.parametrize(
    "texto",
    [
        "=@!" * 2731,
        "a@" * 4096,
        "a@b!" * 2048 + "=",
        "x" * 8000 + "@" + "y" * 100 + "!=",
        ("a" * 120 + "@" + "b" * 120 + "!") * 30 + "=",
    ],
)
def test_seg_a_03_contiene_token_en_8192_caracteres_sin_token_es_rapido(texto):
    texto = texto[:8192]
    inicio = time.perf_counter()
    assert not contiene_token(texto)
    assert time.perf_counter() - inicio < 0.05


def test_seg_a_03_un_token_con_partes_de_128_caracteres_se_detecta_y_mas_largas_no_se_exige():
    assert contiene_token(f"{'u' * 128}@{'r' * 128}!{'i' * 128}=s")
    assert contiene_token(f"nota {TOKEN} fin")


# --- SEG-A-04: formato del pool (V-A16) ---


@pytest.mark.parametrize(
    ("pool", "valido"),
    [
        ("produccion", True),
        ("Prod_01-a", True),
        ("a/b", True),
        ("a/b/c", True),
        ("a/b/c/d", False),
        ("a//b", False),
        ("/a", False),
        ("a/", False),
        ("a b", False),
        ("a\n", False),
        ("pool;rm", False),
        ("a%2Fb", False),
        ("../x", False),
        ("", False),
    ],
)
def test_seg_a_04_formato_de_pool(pool, valido):
    assert pool_valido(pool) is valido


def test_seg_a_04_va16_esta_en_capa_1_y_se_marca_sin_servidor():
    assert "V-A16" in CODIGOS_SIN_SERVIDOR
    cfg = cfg_vm(pool="malo pool")
    cods = [p.codigo for p in validar_sin_servidor(cfg, incluir_nombre=False, incluir_vmid=False)]
    assert "V-A16" in cods


def test_seg_a_04_va16_con_catalogo_es_error_y_no_se_consulta_el_servidor():
    cat = catalogo(pools=PoolsServidor(EstadoPools.OK, ("produccion",)))
    p16 = [p for p in _va(cfg_vm(pool="a b"), cat) if p.codigo == "V-A16"]
    assert len(p16) == 1 and p16[0].severidad == Severidad.ERROR and p16[0].campo == "pool"
    assert not {"V-A10", "V-A11", "V-A15"} & {p.codigo for p in _va(cfg_vm(pool="a b"), cat)}


def test_seg_a_04_pool_anidado_valido_pasa_por_va16_y_se_comprueba_en_el_servidor():
    cat = catalogo(pools=PoolsServidor(EstadoPools.OK, ("a/b",)))
    assert _va(cfg_vm(pool="a/b"), cat) == []
    assert [p.codigo for p in _va(cfg_vm(pool="a/c"), cat)] == ["V-A10"]


def test_seg_a_04_pool_vacio_es_sin_pool_y_no_da_va16():
    assert "V-A16" not in [p.codigo for p in _va(cfg_vm(pool=""))]


def test_seg_a_04_lector_rechaza_un_pool_con_formato_invalido_y_acepta_el_anidado():
    lector = LectorEsquema()
    assert leer_pool(lector, {"pool": "a/b/c"}, "config", nulo=True) == "a/b/c"
    assert not lector.errores
    for malo in ("a b", "a/b/c/d", "x;y", "a\\b"):
        lector = LectorEsquema()
        assert leer_pool(lector, {"pool": malo}, "config", nulo=True) is None
        assert [e.ruta for e in lector.errores] == ["config.pool"]
    lector = LectorEsquema()
    assert leer_pool(lector, {"pool": ""}, "fila", nulo=False) == ""  # «sin pool»
    assert not lector.errores


def test_seg_a_04_el_escritor_rechaza_un_pool_que_el_lector_no_aceptaria():
    for escribir in (
        lambda p: opciones_cfg_a_dict(cfg_vm(pool=p)),
        lambda p: opciones_lote_a_dict(OpcionesLote(pool=p)),
        lambda p: opciones_parciales_a_dict(OpcionesParciales(pool=p)),
    ):
        with pytest.raises(ErrorProxLaunch) as exc:
            escribir("a b")
        assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
        assert escribir("a/b")["pool"] == "a/b"


def test_seg_a_04_csv_pool_invalido_da_va16_y_el_anidado_se_acepta():
    r = importar_csv(["nombre;pool", "a;prod/web/x", "b;prod web", "c;a/b/c/d"])
    f_ok, f_mal1, f_mal2 = r.filas
    assert f_ok.cfg is not None and f_ok.cfg.pool == "prod/web/x"
    for f in (f_mal1, f_mal2):
        assert f.estado == EstadoFila.CON_ERROR
        assert any(p.regla == "V-A16" and p.columna == "pool" for p in f.problemas)


def test_seg_a_04_el_clon_acepta_pool_anidado_y_rechaza_el_inseguro():
    from proxlaunch.nucleo.origen.clon import _id_seguro

    assert _id_seguro("a/b/c", anidado=True)
    assert not _id_seguro("a/b/c")  # nodo y storage no admiten «/»
    assert not _id_seguro("a/../b", anidado=True)
    assert not _id_seguro("a?x=1", anidado=True)


# --- SEG-A-06 / QA-A-03: tope compartido del límite y escritor simétrico ---


def test_seg_a_06_v_a06_rechaza_por_encima_del_tope():
    def _p(limite):
        cfg = cfg_vm(redes=[InterfazRed("vmbr0", limite_mb=limite)])
        return [p.codigo for p in _va(cfg)]

    assert _p(float(MAX_LIMITE_MB)) == []
    assert _p(MAX_LIMITE_MB + 1.0) == ["V-A06"]
    assert _p(float("inf")) == ["V-A06"]
    assert _p(0.0) == ["V-A06"]


def test_seg_a_06_csv_limite_enorme_se_rechaza_por_va06_sin_desbordar():
    assert unidades.limite_mb("50") == 50.0
    assert unidades.limite_mb("1" + "0" * 400) > MAX_LIMITE_MB
    r = importar_csv(["nombre;limite_red", "a;50", "b;" + "9" * 200])
    f_ok, f_mal = r.filas
    assert f_ok.estado == EstadoFila.CORRECTA
    assert f_mal.estado == EstadoFila.CON_ERROR and any(p.regla == "V-A06" for p in f_mal.problemas)


def test_seg_a_06_el_escritor_valida_etiquetas_mtu_y_limite_como_el_lector(tmp_path):
    from proxlaunch.nucleo.archivos.esquema_config import configuracion_a_dict as config_a_dict

    for cambios in (
        {"etiquetas_usuario": ("Mayusculas Mal",)},
        {"etiquetas_usuario": ("x" * 129,)},
        {"etiquetas_usuario": tuple(f"e{i}" for i in range(257))},
    ):
        with pytest.raises(ErrorProxLaunch) as exc:
            opciones_cfg_a_dict(cfg_vm(**cambios))
        assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    with pytest.raises(ErrorProxLaunch):
        opciones_lote_a_dict(OpcionesLote(etiquetas_usuario=("a b",)))
    with pytest.raises(ErrorProxLaunch):
        opciones_parciales_a_dict(OpcionesParciales(etiquetas_usuario=("a b",)))
    assert opciones_cfg_a_dict(cfg_vm(etiquetas_usuario=("web", "prod-1")))["etiquetas_usuario"]

    for red in (
        InterfazRed("vmbr0", ModeloRed.VIRTIO, mtu=100),
        InterfazRed("vmbr0", ModeloRed.VIRTIO, mtu=70000),
        InterfazRed("vmbr0", limite_mb=0.0),
        InterfazRed("vmbr0", limite_mb=MAX_LIMITE_MB + 1.0),
        InterfazRed("vmbr0", limite_mb=float("nan")),
    ):
        with pytest.raises(ErrorProxLaunch) as exc:
            config_a_dict(cfg_vm(redes=[red]))
        assert exc.value.codigo == CodigoError.ARCHIVO_NO_GUARDABLE
    buena = InterfazRed("vmbr0", ModeloRed.VIRTIO, mtu=1, limite_mb=100.0)
    assert config_a_dict(cfg_vm(redes=[buena]))["redes"][0]["limite_mb"] == 100.0


# --- SEG-A-07: el registro enmascara el token genérico ---


def test_seg_a_07_enmascarar_oculta_el_secreto_de_un_token_generico():
    salida = enmascarar(f"fallo con {TOKEN} y más texto")
    assert "0a1b2c3d" not in salida
    assert f"root@pam!ci={MASCARA}" in salida
    assert salida.endswith("y más texto")


def test_seg_a_07_el_filtro_del_log_enmascara_el_token_en_el_mensaje(caplog):
    from proxlaunch.nucleo.registro import FiltroSecretos

    registro = logging.LogRecord("x", logging.INFO, __file__, 1, "token %s", (TOKEN,), None)
    FiltroSecretos().filter(registro)
    assert "0a1b2c3d" not in registro.getMessage()


def test_seg_a_07_un_texto_sin_token_queda_igual_y_es_rapido():
    assert enmascarar("hola a@b.com x=1") == "hola a@b.com x=1"
    largo = "=@!" * 5000
    inicio = time.perf_counter()
    assert enmascarar(largo) == largo
    assert time.perf_counter() - inicio < 0.25


# --- QA-A-02: encendido omitido al comprobar o reconciliar ---


def _mundo_creacion():
    from .test_fase_a_creacion import Mundo

    return Mundo()


def test_qa_a_02_comprobar_ahora_avisa_encendido_omitido_si_se_pedia_encender():
    from .apoyo_lote import upid_de

    m = _mundo_creacion()
    for encender, esperado in ((True, True), (False, False)):
        cfg = m.cfg_clon(encender=encender)
        m.cl.vms[100] = {
            "nodo": "pve1",
            "config": {"name": cfg.nombre, "digest": "d", "tags": ";".join(cfg.etiquetas)},
            "status": "stopped",
        }
        r = m.servicio().comprobar_ahora(cfg, upid_de("pve1", 100, "qmclone"), inv=m.inv)
        assert ("encendido_omitido" in r.avisos) is esperado, (r.desenlace, r.avisos)
        assert m.inicios() == []


def _lote_con_dudosa(encender: bool):
    banco = banco_a()
    banco.cluster.regla("POST", r"/qemu$", lambda llamada: (_ for _ in ()).throw(envio_incierto()))
    bloqueo = banco.cluster.regla("GET", r"qemu/10[01]/config$", nodo_caido("pve1", 596))
    plan = plan_de(banco, def_lote(1, plantilla_vm=plantilla(encender=encender), vmid_inicial=100))
    assert not plan.bloqueado, plan.problemas
    libro = banco.ejecutar(plan, ControlAutomatico("suspender"))
    assert libro.entrada(100).estado == EstadoMV.CONEXION_PERDIDA
    banco.cluster.reglas.remove(bloqueo)
    return banco, libro


@pytest.mark.parametrize(("encender", "esperado"), [(True, True), (False, False)])
def test_qa_a_02_la_reconciliacion_de_una_dudosa_avisa_encendido_omitido(encender, esperado):
    banco, libro = _lote_con_dudosa(encender)
    banco.cluster.reglas.clear()
    banco.cluster.agregar_vm(100, "pve1", "web-01", tags=f"proxlaunch;lote-{libro.id_lote}")
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({100}))
    e = libro.entrada(100)
    assert e.estado == EstadoMV.OK
    assert ("encendido_omitido" in e.avisos) is esperado
    assert "creada_tras_comprobar" in e.avisos


# --- QA-A-05: cuerpo inesperado de /cluster/options ---


@pytest.mark.parametrize("cuerpo", [[], "texto", 7, None])
def test_qa_a_05_un_cuerpo_que_no_es_diccionario_es_lectura_fallida(cuerpo):
    from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
    from proxlaunch.nucleo.api.cliente import ClienteProxmox
    from proxlaunch.nucleo.modelos.conexion import CredencialToken
    from proxlaunch.nucleo.reloj import RelojSimulado

    cliente = ClienteProxmox(
        TransporteFalso(),
        AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)),
        RelojSimulado(),
    )
    cliente._llamar = lambda *a, **k: cuerpo  # type: ignore[method-assign]
    assert leer_politica_etiquetas(cliente) == (None, True)
    cliente._llamar = lambda *a, **k: {}  # type: ignore[method-assign]
    politica, fallida = leer_politica_etiquetas(cliente)
    assert politica == PoliticaEtiquetas() and fallida is False


# --- QA-A-09: «Perfil:» de cada fila ---


def test_qa_a_09_el_perfil_de_la_fila_manda_sobre_el_del_contexto():
    from proxlaunch.nucleo.opciones.modelos import ContextoNotas

    from .apoyo_fase_a import FECHA_FIJA

    banco = banco_a()
    filas = [
        FilaLote("a", cfg_vm(notas_origen=True), perfil="Servidor web"),
        FilaLote("b", cfg_vm(notas_origen=True)),
        FilaLote("c", cfg_vm(notas_origen=True), perfil="Base de datos"),
    ]
    ctx = ContextoNotas("0.6.0", FECHA_FIJA, None, "Del formulario", None)
    plan = plan_de(banco, definicion_filas(filas), contexto_notas=ctx)
    assert not plan.bloqueado, plan.problemas
    perfiles = [
        next(ln for ln in (e.cfg.descripcion or "").splitlines() if ln.startswith("- Perfil"))
        for e in plan.elementos
    ]
    assert perfiles == [
        "- Perfil: Servidor web",
        "- Perfil: Del formulario",
        "- Perfil: Base de datos",
    ]


def test_qa_a_09_el_perfil_de_la_fila_no_se_serializa(tmp_path):
    from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote
    from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado

    ruta = tmp_path / "l.json"
    d = definicion_filas([FilaLote("a", cfg_vm(), perfil="Servidor web")])
    guardar_lote(ruta, LoteGuardado("l", d), app_version="0.6.0")
    assert "Servidor web" not in ruta.read_text(encoding="utf-8")


def test_qa_a_09_el_csv_lleva_el_perfil_de_cada_fila_a_filas_lote():
    from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote

    r = importar_csv(["nombre;perfil", "a;minimo", "b;"])
    filas = filas_lote(r, r.numeros_validos)
    assert [f.perfil for f in filas] == [r.filas[0].perfil, None]
    assert filas[0].perfil


# --- QA-A-10 y S-1: política de etiquetas ---


def _cat_politica(politica, **kw):
    return catalogo(politica=politica, **kw)


def test_qa_a_10_sin_sys_modify_conocido_el_rechazo_por_politica_es_aviso():
    pol = PoliticaEtiquetas("none")
    cfg = cfg_vm(etiquetas_usuario=("web",))
    desconocido = [p for p in _va(cfg, _cat_politica(pol, perm=None)) if p.codigo == "V-A03"]
    assert [(p.severidad, p.params["motivo"]) for p in desconocido] == [
        (Severidad.AVISO, "ninguna_permitida")
    ]
    sin_permiso = catalogo(
        politica=pol,
        perm=PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}}),
    )
    conocido = [p for p in _va(cfg, sin_permiso) if p.codigo == "V-A03"]
    assert [p.severidad for p in conocido] == [Severidad.ERROR]


def test_qa_a_10_list_y_existing_tambien_degradan_a_aviso_con_permisos_desconocidos():
    for permiso, kw in (("list", {"lista_usuario": ("otra",)}), ("existing", {})):
        pol = PoliticaEtiquetas(permiso, **kw)
        va03 = [
            p
            for p in _va(cfg_vm(etiquetas_usuario=("web",)), _cat_politica(pol, perm=None))
            if p.codigo == "V-A03"
        ]
        assert [p.severidad for p in va03] == [Severidad.AVISO], permiso


def test_s_1_la_comparacion_es_exacta_aunque_el_estilo_no_distinga_mayusculas():
    pol = PoliticaEtiquetas("list", ("Web",), distingue_mayusculas=False)
    cat = catalogo(politica=pol, perm=PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}}))
    va03 = [p for p in _va(cfg_vm(etiquetas_usuario=("web",)), cat) if p.codigo == "V-A03"]
    assert [p.params["etiqueta"] for p in va03] == ["web"]


def test_s_1_un_clon_solo_evalua_las_etiquetas_anadidas_a_las_de_la_plantilla():
    from proxlaunch.nucleo.origen.resolucion import resolver_origen

    from .apoyo_mvp4 import cfg_clon, detalle_plantilla, inv_origen, plantilla_pve

    pol = PoliticaEtiquetas("list", ("nueva",))
    inv = inv_origen(
        plantillas=(
            plantilla_pve(9000, "base", "pve1", detalle=detalle_plantilla(etiquetas={"heredada"})),
        )
    )
    inv.catalogo = dataclasses.replace(
        inv.catalogo,
        politica_etiquetas=pol,
        permisos=PermisosEfectivos(rutas={"/": {"VM.Allocate": 1}}),
    )
    cfg, problemas = resolver_origen(
        cfg_clon("base", etiquetas=("heredada",), etiquetas_usuario=("nueva", "otra")), inv, "pve1"
    )
    assert problemas == []
    va03 = [p for p in validar_vm(cfg, inv, CAPS) if p.codigo == "V-A03"]
    assert [p.params["etiqueta"] for p in va03] == ["otra"]


# --- QA-A-12: las notas pierden los caracteres bidi ---


def test_qa_a_12_limpiar_texto_libre_quita_bidi_y_avisa():
    limpio, cambios = limpiar_texto_libre("uno‮two⁦ tres‏")
    assert limpio == "unotwo tres" and cambios is True
    assert limpiar_texto_libre("a\nb\tc") == ("a\nb\tc", False)


def test_qa_a_12_validar_avisa_va14_con_bidi_en_las_notas():
    assert "V-A14" in [p.codigo for p in _va(cfg_vm(notas="hola‮"))]


def test_qa_a_12_la_descripcion_enviada_no_lleva_bidi():
    from proxlaunch.nucleo.opciones.notas import componer_descripcion

    from .apoyo_fase_a import ctx_notas

    texto = componer_descripcion(cfg_vm(notas="abc‮def"), ctx_notas(), None, None)
    assert texto == "abcdef"
