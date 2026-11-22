"""Secretos de la fase B (0.7.0): la contraseña de cloud-init no se persiste ni se registra.

Requisitos: RF-B0.8 (CA-B0.8.1 a CA-B0.8.3), CA-B3.6.3, CA-B6.5.3, CA-B6.5.4 y el contrato de
DT-B1 (``Secreto``: ``repr``, ``pickle``, ``deepcopy``, ``olvidar``, registro de secretos y el
único camino hacia el servidor). El centinela ``S3cr3t-Prueba!`` se busca (también codificado y en
su prefijo) en: el log a nivel DEBUG, ``a_dict()``, el JSON del lote guardado, el informe, la
simulación, los ``params`` y ``repr`` de los errores, los ``repr`` de los modelos y las
exportaciones de IP. El servidor simulado repite el cuerpo de los ``PUT`` en sus errores (modo eco).

Fuera de este archivo (interfaz): Resumen y vista previa del diálogo de CSV, en ``tests/interfaz``.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import logging
import pickle
from urllib.parse import quote, quote_plus, unquote_plus

import pytest
import responses

from proxlaunch.nucleo.agente.exportacion import guardar_ips_csv, lista_ips_texto
from proxlaunch.nucleo.agente.modelos import EstadoIp, ResultadoIp
from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo, es_clave_credencial
from proxlaunch.nucleo.cloudinit.modelos import ConfigCloudInit
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote
from proxlaunch.nucleo.errores import CodigoError
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.modelos import EstadoMV, MetadatosInforme
from proxlaunch.nucleo.lote.simulacion import simular
from proxlaunch.nucleo.lotes_guardados.formato import (
    leer_lote,
    lote_a_bytes,
    lote_a_dict,
    version_para,
)
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM
from proxlaunch.nucleo.registro import enmascarar, olvidar_secretos, registrar_secreto
from proxlaunch.nucleo.secreto import MASCARA, Secreto

from .apoyo_fase_b_p1 import CENTINELA, CLAVE, MundoB, ci, ci_completa, fallar_put
from .apoyo_lote import Http, error_http, volcar
from .apoyo_mvp3 import definicion_filas, importar_csv

# El centinela, sus formas codificadas (las que salen en un cuerpo de formulario) y un prefijo.
VARIANTES = (CENTINELA, quote(CENTINELA, safe=""), quote_plus(CENTINELA), "S3cr3t")


def _sin_centinela(texto: str) -> None:
    for v in VARIANTES:
        assert v not in texto, (
            f"el centinela ({v!r}) aparece en: …{texto[texto.find(v) - 40 :][:140]}…"
        )


@pytest.fixture(autouse=True)
def _registro_limpio():
    """Cada prueba parte de un registro de secretos vacío (y lo deja igual)."""
    olvidar_secretos(incluir_cloudinit=True)
    yield
    olvidar_secretos(incluir_cloudinit=True)


# --- Contrato de ``Secreto`` (DT-B1) --------------------------------------------------------------


def test_repr_str_y_format_dan_la_mascara_y_nunca_el_valor():
    s = Secreto(CENTINELA)
    assert repr(s) == f"Secreto({MASCARA})"
    assert str(s) == MASCARA and f"{s}" == MASCARA and f"{s:>20}" == MASCARA
    assert "%s" % s == MASCARA and "{}".format(s) == MASCARA  # noqa: UP031, UP032
    for texto in (repr(s), str(s), f"{s!r}", repr([s]), repr({"k": s}), str((s,))):
        _sin_centinela(texto)


def test_revelar_es_el_unico_acceso_al_valor_y_olvidar_lo_vacia():
    s = Secreto(CENTINELA)
    assert s.definido and bool(s) and s.revelar() == CENTINELA
    s.olvidar()
    assert not s.definido and not bool(s) and s.revelar() == ""
    s.olvidar()  # idempotente
    assert s.revelar() == ""


def test_un_secreto_vacio_o_no_texto_no_esta_definido_ni_se_registra():
    assert not Secreto("").definido
    assert not Secreto(None).definido  # type: ignore[arg-type]
    assert not Secreto(123).definido  # type: ignore[arg-type]
    assert enmascarar("texto 123 y None") == "texto 123 y None"


def test_copy_y_deepcopy_devuelven_la_misma_instancia():
    """Un único ``olvidar()`` vale para todas las copias del plan, el libro y la fila."""
    s = Secreto(CENTINELA)
    assert copy.copy(s) is s and copy.deepcopy(s) is s
    cfg = ConfiguracionVM(vmid=1, nombre="a", nodo="n", cloudinit=ConfigCloudInit(contrasena=s))
    for copia in (copy.deepcopy(cfg), copy.copy(cfg), dataclasses.replace(cfg)):
        assert copia.cloudinit.contrasena is s
    copy.deepcopy([cfg, {"x": cfg}])[1]["x"].cloudinit.contrasena.olvidar()
    assert not s.definido


@pytest.mark.parametrize("protocolo", range(pickle.HIGHEST_PROTOCOL + 1))
def test_pickle_falla_con_typeerror(protocolo):
    with pytest.raises(TypeError):
        pickle.dumps(Secreto(CENTINELA), protocol=protocolo)


def test_json_no_serializa_un_secreto():
    with pytest.raises(TypeError):
        json.dumps({"contrasena": Secreto(CENTINELA)})
    with pytest.raises(TypeError):
        json.dumps(dataclasses.asdict(ConfigCloudInit(contrasena=Secreto(CENTINELA))))


def test_la_igualdad_y_el_hash_son_por_identidad_nunca_por_contenido():
    a, b = Secreto(CENTINELA), Secreto(CENTINELA)
    assert a != b
    assert a == a  # noqa: PLR0124
    assert a != CENTINELA
    assert len({a, b}) == 2


def test_la_contrasena_de_cloudinit_no_cuenta_en_la_igualdad_ni_en_el_repr():
    uno = ConfigCloudInit(usuario="x", contrasena=Secreto(CENTINELA))
    otro = ConfigCloudInit(usuario="x", contrasena=Secreto("otra-distinta"))
    assert uno == otro
    _sin_centinela(repr(uno))
    assert "contrasena" not in repr(uno)


def test_un_secreto_registrado_se_enmascara_y_olvidarlo_lo_quita_sin_tocar_los_demas():
    """DT-B1: ``olvidar`` solo quita ese valor (y sus variantes), no el resto (p. ej. el token)."""
    registrar_secreto("token-de-sesion-9f8e7d")
    s = Secreto(CENTINELA)
    texto = (
        f"a {CENTINELA} b {quote(CENTINELA, safe='')} c {quote_plus(CENTINELA)} "
        "d token-de-sesion-9f8e7d"
    )
    assert enmascarar(texto).count(MASCARA) >= 4 or "***" in enmascarar(texto)
    _sin_centinela(enmascarar(texto))
    s.olvidar()
    despues = enmascarar(texto)
    assert CENTINELA in despues  # ya no es un secreto conocido
    assert "token-de-sesion-9f8e7d" not in despues  # el token sigue protegido


def test_dos_secretos_iguales_olvidar_uno_no_desprotege_al_otro():
    """El registro cuenta referencias (M2a): el valor sigue enmascarado mientras quede un
    ``Secreto`` vivo y solo se libera al olvidar el último."""
    a, b = Secreto(CENTINELA), Secreto(CENTINELA)
    a.olvidar()
    assert b.definido
    assert CENTINELA not in enmascarar(CENTINELA)
    b.olvidar()
    assert CENTINELA in enmascarar(CENTINELA)


def test_a_dict_omite_la_contrasena_y_deja_un_indicador_neutro():
    cfg = ConfiguracionVM(vmid=1, nombre="a", nodo="n", cloudinit=ci(contrasena=Secreto(CENTINELA)))
    datos = cfg.a_dict()
    texto = json.dumps(datos, ensure_ascii=False)
    _sin_centinela(texto)
    assert datos["cloudinit"].get("con_acceso_local") is True
    assert not any(es_clave_credencial(k) for k in _claves(datos))


def test_a_dict_de_un_secreto_olvidado_ya_no_marca_acceso_local():
    s = Secreto(CENTINELA)
    cfg = ConfiguracionVM(vmid=1, nombre="a", nodo="n", cloudinit=ci(contrasena=s))
    s.olvidar()
    assert "con_acceso_local" not in cfg.a_dict()["cloudinit"]


def test_desde_dict_nunca_recupera_una_contrasena():
    cfg = ConfiguracionVM(vmid=1, nombre="a", nodo="n", cloudinit=ci(contrasena=Secreto(CENTINELA)))
    leida = ConfiguracionVM.desde_dict(json.loads(json.dumps(cfg.a_dict())))
    assert leida.cloudinit is not None and leida.cloudinit.contrasena is None


def _claves(valor, acumulado=None):
    acumulado = [] if acumulado is None else acumulado
    if isinstance(valor, dict):
        for k, v in valor.items():
            acumulado.append(k)
            _claves(v, acumulado)
    elif isinstance(valor, list | tuple):
        for v in valor:
            _claves(v, acumulado)
    return acumulado


# --- El único camino hacia el servidor ------------------------------------------------------------


def test_el_put_de_contrasena_lleva_el_valor_real_y_solo_ese_parametro(rsps):
    """R-B5: ``configurar_contrasena`` es el único sitio que revela el valor."""
    m = MundoB(rsps=rsps)
    m.cl.agregar_vm(100, "pve1", "x")
    m.sesion.cliente.configurar_contrasena("pve1", 100, Secreto(CENTINELA))
    ((vmid, cuerpo),) = m.cl.puts_crudos
    assert vmid == 100 and cuerpo == f"cipassword={quote_plus(CENTINELA)}".encode()


def test_configurar_contrasena_con_un_secreto_olvidado_falla_sin_enviar_nada(rsps):
    m = MundoB(rsps=rsps)
    m.cl.agregar_vm(100, "pve1", "x")
    s = Secreto(CENTINELA)
    s.olvidar()
    with pytest.raises(ValueError, match="no está definida"):
        m.sesion.cliente.configurar_contrasena("pve1", 100, s)
    assert m.cl.puts_crudos == []


def test_contrato_un_secreto_en_un_diccionario_de_parametros_llega_enmascarado(rsps):
    """RD-B1: meter un ``Secreto`` en los ``datos`` NO envía la contraseña: el transporte hace
    ``str(valor)`` y el servidor recibe la máscara. Es un fallo seguro (y esta prueba lo vigila)."""
    m = MundoB(rsps=rsps)
    m.cl.agregar_vm(100, "pve1", "x")
    m.sesion.cliente.configurar_vm("pve1", 100, {"cipassword": Secreto(CENTINELA)})  # type: ignore[dict-item]
    ((_, cuerpo),) = m.cl.puts_crudos
    _sin_centinela(cuerpo.decode())
    assert quote_plus(MASCARA) in cuerpo.decode()


# --- CA-B0.8.1: el escenario completo con servidor «eco» ------------------------------------------


class _Capturador(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.registros: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.registros.append(record)


@pytest.fixture(scope="module")
def escenario(tmp_path_factory):
    """Dos lotes con la contraseña centinela: el primero sin fallos y el segundo contra un
    servidor que repite el cuerpo de los ``PUT`` de contraseña en su error (modo eco). Devuelve
    las salidas (texto) de cada superficie donde NO debe aparecer el centinela."""
    carpeta = tmp_path_factory.mktemp("secretos")
    capturador = _Capturador()
    logger = logging.getLogger("proxlaunch")
    nivel, logger.level = logger.level, logging.DEBUG
    logger.addHandler(capturador)
    olvidar_secretos(incluir_cloudinit=True)
    try:
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            m = MundoB(rsps=rsps)
            secreto = Secreto(CENTINELA)
            ok_plan = m.planificar(
                m.definicion(2, ci_completa(secreto, serie=True), encender=True, esperar_ip=True)
            )
            sim = simular(m.sesion, ok_plan.definicion, m.inv, reloj=m.reloj)
            libro_ok = m.ejecutar(ok_plan)
            m.cl.eco_put = {"cipassword"}  # el servidor repite el cuerpo en sus errores
            eco_plan = m.planificar(
                m.definicion(2, ci_completa(secreto, serie=True), encender=True, esperar_ip=True)
            )
            libro_eco = m.ejecutar(eco_plan)
            todos = (*libro_ok.instantanea(), *libro_eco.instantanea())
            for e in todos:  # resultados de IP de ejemplo para la exportación
                libro = libro_ok if e in libro_ok.instantanea() else libro_eco
                libro.registrar_ip(
                    e.elemento.vmid, ResultadoIp(EstadoIp.OBTENIDA, "10.0.0.50", ("10.0.1.9",))
                )
            todos = (*libro_ok.instantanea(), *libro_eco.instantanea())
            meta = MetadatosInforme("lab", "9.2.1", False, None, "2026-11-22T10:00:00+00:00")
            informes = [
                construir_informe(p, lb, meta, reloj=m.reloj)
                for p, lb in ((ok_plan, libro_ok), (eco_plan, libro_eco))
            ]
            exportacion = carpeta / "ips.csv"
            guardar_ips_csv(exportacion, todos)
            lote = LoteGuardado("lote de prueba", ok_plan.definicion, "9.2.1")
            formateador = logging.Formatter()
            salidas = {
                "log": "\n".join(formateador.format(r) for r in capturador.registros),
                "a_dict": json.dumps(
                    [e.elemento.cfg.a_dict() for e in todos]
                    + [ok_plan.definicion.plantilla.a_dict()],
                    ensure_ascii=False,
                ),
                "json_lote": lote_a_bytes(lote, app_version="0.7.0").decode("utf-8"),
                "lote_a_dict": json.dumps(lote_a_dict(lote), ensure_ascii=False),
                "informe": "\n".join(volcar(i) + repr(i) for i in informes),
                "simulacion": volcar(sim) + repr(sim),
                "params": "\n".join(
                    volcar(e.error) + repr(e.error) + str(e.error) + volcar(e.error.params)
                    for e in todos
                    if e.error is not None
                ),
                "repr_modelos": "\n".join(
                    [repr(ok_plan), repr(eco_plan), repr(todos), repr(libro_ok.plan)]
                    + [repr(e.elemento.cfg) + repr(e.elemento.cfg.cloudinit) for e in todos]
                ),
                "exportacion_csv": exportacion.read_text(encoding="utf-8-sig"),
                "exportacion_lista": lista_ips_texto(todos),
            }
            yield {
                "salidas": salidas,
                "m": m,
                "sim": sim,
                "libro_ok": libro_ok,
                "libro_eco": libro_eco,
                "informes": informes,
                "secreto": secreto,
                "exportacion": exportacion,
            }
    finally:
        logger.removeHandler(capturador)
        logger.level = nivel
        olvidar_secretos(incluir_cloudinit=True)


SUPERFICIES = [
    "log",
    "a_dict",
    "json_lote",
    "lote_a_dict",
    "informe",
    "simulacion",
    "params",
    "repr_modelos",
    "exportacion_csv",
    "exportacion_lista",
]


@pytest.mark.parametrize("superficie", SUPERFICIES)
def test_ca_b0_8_1_el_centinela_no_aparece_en_ninguna_salida(escenario, superficie):
    """CA-B0.8.1 / CA-B3.6.3: ni en el log (DEBUG), ``a_dict``, el JSON del lote guardado, el
    informe, la simulación, los ``params`` de los errores, los ``repr`` ni la exportación de IPs."""
    _sin_centinela(escenario["salidas"][superficie])


def test_ca_b0_8_1_la_prueba_ejercita_de_verdad_el_secreto(escenario):
    """El escenario no es vacío: la contraseña viajó en los PUT y el servidor la repitió."""
    m = escenario["m"]
    con_pw = [b for _, b in m.cl.puts_crudos if b.startswith(b"cipassword=")]
    assert len(con_pw) == 4  # una por MV, de los dos lotes
    assert all(CENTINELA in unquote_plus(b.decode()) for b in con_pw)
    ok = escenario["libro_ok"].instantanea()
    eco = escenario["libro_eco"].instantanea()
    assert {e.estado for e in ok} == {EstadoMV.CON_AVISOS} or {e.estado for e in ok} == {
        EstadoMV.OK
    }
    assert {e.estado for e in eco} == {EstadoMV.PARCIAL}
    for e in eco:  # el eco llegó al error del libro, ya enmascarado
        assert e.error is not None and "cipassword" in e.error.detalle_tecnico
        assert MASCARA in e.error.detalle_tecnico or "***" in e.error.detalle_tecnico


def test_ca_b0_8_1_la_simulacion_enmascara_el_cuerpo_del_put_de_contrasena(escenario):
    from proxlaunch.nucleo.lote.modelos import AccionPeticion

    detalle = escenario["sim"].peticiones_detalle
    for peticiones in detalle.values():
        acciones = [p.accion for p in peticiones]
        assert acciones.index(AccionPeticion.CLOUDINIT) < acciones.index(AccionPeticion.CONTRASENA)
        (pw,) = [p for p in peticiones if p.accion == AccionPeticion.CONTRASENA]
        assert pw.parametros == {"cipassword": MASCARA}
        (cloud,) = [p for p in peticiones if p.accion == AccionPeticion.CLOUDINIT]
        assert cloud.parametros["sshkeys"] == "[2]"  # nunca el cuerpo de las claves
        assert CLAVE not in volcar(cloud.parametros)


def test_ca_b0_8_1_la_simulacion_no_escribe_nada_en_el_servidor(escenario):
    """La simulación se hizo antes del primer lote: hasta entonces solo hubo lecturas."""
    m = escenario["m"]
    primera_escritura = next(i for i, c in enumerate(m.cl.llamadas) if c.metodo != "GET")
    assert m.cl.llamadas[primera_escritura].ruta.endswith("/clone")


def test_ca_b0_8_1_el_informe_no_lleva_ningun_dato_de_cloudinit(escenario):
    for informe in escenario["informes"]:
        for entrada in informe.entradas:
            assert entrada.elemento.cfg.cloudinit is None
            assert entrada.elemento.cfg.info_cloudinit is None
        texto = volcar(informe)
        for valor in ("deploy", CLAVE.split()[1], "lab.local", "10.0.0.50/24"):
            assert valor not in texto, valor


def test_ca_b0_8_1_el_libro_conserva_la_configuracion_en_memoria_para_reintentar(escenario):
    """CA-B7.2.5 vs «Reintentar ajustes» (§0): en memoria sí, pero nunca en su ``repr``."""
    for e in escenario["libro_eco"].instantanea():
        assert e.elemento.cfg.cloudinit is not None
        assert e.elemento.cfg.cloudinit.contrasena is escenario["secreto"]


def test_el_exportado_no_lleva_cloudinit_y_si_las_ips(escenario):
    texto = escenario["salidas"]["exportacion_csv"]
    assert "10.0.0.50" in texto and "web-01" in texto
    for valor in ("deploy", "ssh-ed25519", "lab.local", "agente.yaml"):
        assert valor not in texto
    assert escenario["salidas"]["exportacion_lista"].splitlines()[0] == "web-01\t10.0.0.50"


# --- CA-B0.8.2: el lote guardado ------------------------------------------------------------------


def _lote_con_contrasena(m: MundoB) -> LoteGuardado:
    return LoteGuardado("con contraseña", m.definicion(2, ci(contrasena=Secreto(CENTINELA))))


def test_ca_b0_8_2_el_lote_guardado_no_tiene_ningun_campo_de_credencial_y_avisa_al_reabrir():
    m = MundoB()
    lote = _lote_con_contrasena(m)
    datos = lote_a_bytes(lote, app_version="0.7.0")
    texto = datos.decode("utf-8")
    _sin_centinela(texto)
    documento = json.loads(texto)
    assert not [k for k in _claves(documento) if es_clave_credencial(k)]
    assert (
        '"con_acceso_local": true' in json.dumps(documento, indent=1) or "con_acceso_local" in texto
    )
    leido = leer_lote(datos)
    assert CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA in {a.codigo for a in leido.avisos}
    assert leido.lote.definicion.plantilla.cloudinit.contrasena is None


def test_ca_b0_8_2_sin_contrasena_no_hay_indicador_ni_aviso():
    m = MundoB()
    datos = lote_a_bytes(LoteGuardado("sin", m.definicion(2, ci())), app_version="0.7.0")
    assert b"con_acceso_local" not in datos
    assert CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA not in {
        a.codigo for a in leer_lote(datos).avisos
    }


def test_ca_b0_8_2_un_secreto_olvidado_antes_de_guardar_no_deja_el_indicador():
    m = MundoB()
    secreto = Secreto(CENTINELA)
    lote = LoteGuardado("x", m.definicion(2, ci(contrasena=secreto)))
    secreto.olvidar()
    assert b"con_acceso_local" not in lote_a_bytes(lote, app_version="0.7.0")


def test_ca_b0_8_2_la_contrasena_sola_ya_obliga_al_formato_nuevo_y_sin_ella_no():
    m = MundoB()
    con = LoteGuardado("c", m.definicion(2, ci(contrasena=Secreto(CENTINELA))))
    sin = LoteGuardado("s", m.definicion(2, None))
    assert version_para(con) == 4
    assert version_para(sin) < 4  # sin nada de B se escribe como en 0.6.0


# --- CA-B0.8.3: archivo manipulado ----------------------------------------------------------------


@pytest.mark.parametrize("clave", ["contrasena", "cipassword", "ci_password", "password"])
def test_ca_b0_8_3_una_clave_de_contrasena_en_el_archivo_se_ignora_con_aviso(clave):
    m = MundoB()
    documento = json.loads(
        lote_a_bytes(LoteGuardado("x", m.definicion(2, ci())), app_version="0.7.0")
    )
    documento["homogeneo"]["config"]["cloudinit"][clave] = CENTINELA
    documento["homogeneo"]["config"][clave] = CENTINELA
    leido = leer_lote(json.dumps(documento).encode())
    assert CodigoAvisoArchivo.CREDENCIAL_IGNORADA in {a.codigo for a in leido.avisos}
    cfg = leido.lote.definicion.plantilla
    assert cfg.cloudinit is not None and cfg.cloudinit.contrasena is None
    _sin_centinela(repr(leido) + json.dumps(cfg.a_dict()) + volcar(leido))


def test_ca_b0_8_3_la_clave_manipulada_no_llega_a_ninguna_peticion(rsps):
    """El lote leído se crea sin ningún ``PUT`` de contraseña: el valor no llega al servidor."""
    m = MundoB(rsps=rsps)
    documento = json.loads(
        lote_a_bytes(LoteGuardado("x", m.definicion(2, ci())), app_version="0.7.0")
    )
    documento["homogeneo"]["config"]["cloudinit"]["cipassword"] = CENTINELA
    leido = leer_lote(json.dumps(documento).encode())
    plan = m.planificar(dataclasses.replace(m.definicion(2, None), plantilla=_con_origen(m, leido)))
    libro = m.ejecutar(plan)
    assert {e.estado for e in libro.instantanea()} == {EstadoMV.OK}
    assert m.cl.puts_crudos
    assert not any(b"cipassword" in b or CENTINELA.encode() in b for _, b in m.cl.puts_crudos)


def _con_origen(m: MundoB, leido) -> ConfiguracionVM:
    """La plantilla de clon del lote leído (el archivo guarda el origen por nombre de plantilla)."""
    cfg = leido.lote.definicion.plantilla
    return dataclasses.replace(m.definicion(2, cfg.cloudinit).plantilla, cloudinit=cfg.cloudinit)


# --- CA-B6.5.3 / CA-B6.5.4: el CSV con contraseñas ------------------------------------------------


def _csv_con_errores():
    return importar_csv(
        [
            "nombre;origen;fuente;ci_contrasena;cores;memoria_mib",
            f"web-01;clonar;base;{CENTINELA};no-numero;2048",
            f"web-02;clonar;base;{CENTINELA};2;2048",
            f"web-03;clonar;base;{CENTINELA} con espacios y {'x' * 130};2;2048",
        ]
    )


def test_ca_b6_5_3_el_centinela_no_aparece_en_la_vista_previa_ni_en_los_errores_del_csv():
    """CA-B6.5.3: ``originales`` (vista previa), ``valor`` de cada problema, ``params`` y el
    ``repr`` de todo el resultado llevan la máscara; el aviso de contraseñas se da una vez."""
    r = _csv_con_errores()
    _sin_centinela(repr(r) + volcar(r))
    for f in r.filas:
        assert f.originales.get("ci_contrasena") in (None, MASCARA), f.numero
        for p in f.problemas:
            _sin_centinela(p.valor + volcar(p.params))
    assert any(f.estado.value == "con_error" for f in r.filas)  # hay errores en otras columnas
    assert [a.codigo for a in r.avisos].count(CodigoAvisoArchivo.CSV_CON_CONTRASENAS) == 1


def test_ca_b6_5_3_el_log_del_csv_no_lleva_el_centinela(caplog):
    caplog.set_level(logging.DEBUG)
    _csv_con_errores()
    _sin_centinela(caplog.text)


def test_ca_b6_5_4_el_lote_guardado_desde_un_csv_con_contrasena_no_la_contiene():
    """CA-B6.5.4: al guardar el lote del CSV no queda ninguna contraseña; al reabrirlo se avisa."""
    r = _csv_con_errores()
    filas = filas_lote(r, [3])  # la fila 3 (web-02) es la única sin errores
    assert filas and filas[0].opciones is not None
    assert filas[0].opciones.cloudinit is not None
    assert filas[0].opciones.cloudinit.contrasena is not None
    definicion = definicion_filas(list(filas))
    datos = lote_a_bytes(LoteGuardado("desde csv", definicion), app_version="0.7.0")
    _sin_centinela(datos.decode("utf-8"))
    assert not [k for k in _claves(json.loads(datos)) if es_clave_credencial(k)]
    leido = leer_lote(datos)
    assert CodigoAvisoArchivo.CONTRASENA_NO_GUARDADA in {a.codigo for a in leido.avisos}


# --- Errores y traducción -------------------------------------------------------------------------


def test_el_eco_de_un_error_del_servidor_sale_enmascarado_en_el_detalle_tecnico(rsps):
    m = MundoB(rsps=rsps)
    m.cl.eco_put = True
    s = Secreto(CENTINELA)
    m.cl.agregar_vm(100, "pve1", "x")
    with pytest.raises(Exception) as info:
        m.sesion.cliente.configurar_contrasena("pve1", 100, s)
    error = info.value
    assert error.codigo == CodigoError.DESCONOCIDO
    _sin_centinela(error.detalle_tecnico + repr(error) + volcar(error))
    assert "cipassword" in error.detalle_tecnico


def test_el_traductor_http_enmascara_un_secreto_registrado_en_cualquier_mensaje():
    Secreto(CENTINELA)
    e = error_http(
        500, f"Parameter verification failed. cipassword: {CENTINELA} ({quote(CENTINELA, safe='')})"
    )
    _sin_centinela(e.detalle_tecnico + repr(e) + volcar(e.params))


def test_un_error_de_contrasena_olvidada_no_lleva_valores_en_sus_params():
    from proxlaunch.nucleo.errores import ErrorProxLaunch

    m = MundoB()
    s = Secreto(CENTINELA)
    cfg = m.cfg(ci(contrasena=s))
    s.olvidar()
    r = m.crear(cfg)
    assert isinstance(r.error, ErrorProxLaunch)
    # Con V-B40 la validación lo frena antes de escribir: solo nombra el campo y la regla.
    assert set(r.error.params) <= {"nombre", "campo", "regla"}


def test_la_contrasena_olvidada_no_se_envia_ni_aunque_haya_otros_pasos_por_reintentar(rsps):
    """Tras ``olvidar`` el servidor no recibe ni el valor ni una cadena vacía como contraseña."""
    m = MundoB(rsps=rsps)
    s = Secreto(CENTINELA)
    cfg = m.cfg(ci(contrasena=s), etiquetas=())
    regla = fallar_put(m.cl, "ciuser", Http(500, "fallo de prueba"), veces=1)
    m.crear(cfg)
    m.cl.reglas.remove(regla)
    s.olvidar()
    m.reintentar(cfg, frozenset({"cloudinit", "contrasena"}))
    assert not [b for _, b in m.cl.puts_crudos if b"cipassword" in b]
