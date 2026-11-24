"""D2.1–D2.4 y D0.4 (0.9.0): versión mínima 8.4, aviso de la rama 8, versión forzada y funciones.

CA-D2.1.1–4, CA-D2.2.1–3, CA-D2.3.1–3, CA-D2.4.1, CA-D2.4.3–4, CA-D0.4.1–2. Las pruebas de textos
y de pantalla de V-D01 a V-D03 están en ``tests/interfaz/test_fase_d_conexion.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

import proxlaunch
from proxlaunch.nucleo import capacidades as cap
from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.capacidades import (
    VERSION_MINIMA,
    VERSIONES_CONOCIDAS,
    Capacidades,
    Funcion,
    capacidades_para,
    es_rama_8,
    interpretar_version,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.modelos.inventario import Version
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.preferencias import Preferencias, RepositorioPreferencias
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.servicios.conexion import CodigoAviso, ServicioConexion

from .apoyo_api import HUELLA_A, TOKEN_ID, TOKEN_SECRETO, TransporteFalso, perfil_basico

A = "10.0.0.1"
TOKEN = CredencialToken(TOKEN_ID, TOKEN_SECRETO)
RAIZ_SRC = Path(proxlaunch.__file__).parent


class _Llavero:
    def __init__(self) -> None:
        self.almacen: dict[tuple[str, str], str] = {}

    def set_password(self, servicio: str, clave: str, valor: str) -> None:
        self.almacen[(servicio, clave)] = valor

    def get_password(self, servicio: str, clave: str) -> str | None:
        return self.almacen.get((servicio, clave))

    def delete_password(self, servicio: str, clave: str) -> None:
        self.almacen.pop((servicio, clave), None)


@pytest.fixture
def servicio(tmp_path, reloj):
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    huellas.guardar(A, 8006, HUELLA_A)
    return ServicioConexion(
        crear_transporte_http, huellas, AlmacenSecretos(backend=_Llavero()), reloj
    )


def _conectar(servicio: ServicioConexion, texto: str, **kw: Any):
    t = TransporteFalso().en("GET", "/version", {"version": texto})
    servicio._fabrica = lambda perfil, huellas: t
    sesion = servicio.conectar(perfil_basico(), TOKEN, **kw)
    return sesion, t


def _avisos(sesion: Any, codigo: CodigoAviso) -> list[Any]:
    return [a for a in sesion.avisos if a.codigo == codigo]


# --- CA-D2.1: versión mínima 8.4 --------------------------------------------------------------


def test_la_version_minima_es_8_4_y_la_ultima_conocida_9_2():
    assert VERSION_MINIMA == (8, 4)
    assert cap.ULTIMA_VERSION_CONOCIDA == (9, 2)


@pytest.mark.parametrize("texto", ["8.0", "8.0.4", "8.1", "8.2.4", "8.3", "8.3.9", "7.4-17"])
def test_ca_d2_1_1_8_0_a_8_3_se_rechazan_sin_hacer_ninguna_otra_peticion(servicio, texto):
    t = TransporteFalso().en("GET", "/version", {"version": texto})
    servicio._fabrica = lambda perfil, huellas: t
    with pytest.raises(ErrorProxLaunch) as e:
        servicio.conectar(perfil_basico(), TOKEN)
    assert e.value.codigo == CodigoError.VERSION_NO_SOPORTADA
    assert e.value.params == {"version": texto, "minima": "8.4"}
    assert [c.ruta for c in t.llamadas] == ["/version"]  # ni permisos, ni nodos, ni nada más


@pytest.mark.parametrize("texto", ["8.4.0", "8.4.14", "9.0", "9.1", "9.2", "9.2.1"])
def test_ca_d2_1_2_8_4_y_posteriores_conectan(servicio, texto):
    sesion, _ = _conectar(servicio, texto)
    assert sesion.capacidades.es_soportada()
    assert all(a.codigo != CodigoAviso.VERSION_NO_PROBADA for a in sesion.avisos)


@pytest.mark.parametrize("texto", ["8.4-beta", "", "texto raro", "v?", "ocho"])
def test_ca_d2_1_3_un_formato_inesperado_usa_la_minima_8_4_sin_excepcion(servicio, texto):
    sesion, _ = _conectar(servicio, texto)
    assert sesion.capacidades.version == (8, 4)
    assert sesion.capacidades.es_soportada()


def test_ca_d2_1_3_interpretar_version_devuelve_la_minima_con_advertencia():
    version, advertencia = interpretar_version("???")
    assert (version.mayor, version.menor) == (8, 4) and advertencia is True


@pytest.mark.parametrize("texto", ["9.3", "9.3.1", "10.0"])
def test_ca_d2_1_4_una_version_futura_conecta_con_el_aviso_version_no_probada(servicio, texto):
    sesion, _ = _conectar(servicio, texto)
    (aviso,) = _avisos(sesion, CodigoAviso.VERSION_NO_PROBADA)
    assert aviso.params["version"] == texto


def test_ca_d2_1_la_validacion_usa_la_nueva_minima():
    """``Capacidades.es_soportada`` y la validación sin servidor comparan con 8.4."""
    assert not Capacidades((8, 3), False).es_soportada()
    assert Capacidades((8, 4), False).es_soportada()


# --- CA-D2.2: aviso de fin de soporte de la rama 8 ---------------------------------------


@pytest.mark.parametrize("texto", ["8.4", "8.4.1", "8.4.14"])
def test_ca_d2_2_1_una_8_x_detectada_lleva_un_unico_aviso(servicio, texto):
    sesion, _ = _conectar(servicio, texto)
    (aviso,) = _avisos(sesion, CodigoAviso.RAMA_8_SIN_SOPORTE)
    assert aviso.params == {"version": texto}


def test_ca_d2_2_1_el_aviso_no_se_repite_al_descubrir_ni_al_simular(servicio):
    """No se vuelve a añadir en operaciones posteriores (descubrir, planificar, simular)."""
    from proxlaunch.nucleo.lote.simulacion import simular

    from .apoyo_fase_a import catalogo, cfg_vm, def_lote, inv_con
    from .apoyo_lote import Cluster, crear_banco

    sesion, _ = _conectar(servicio, "8.4.1")
    antes = list(sesion.avisos)
    banco = crear_banco(("pve1",), cluster=Cluster(("pve1",)))
    banco.inv = inv_con(catalogo(), version=Version("8.4.1", 8, 4, 1))
    banco.sesion.avisos = sesion.avisos  # misma lista de avisos de la conexión
    banco.sesion.version = Version("8.4.1", 8, 4, 1)
    banco.sesion.capacidades = capacidades_para(banco.sesion.version, None)
    res = simular(banco.sesion, def_lote(2, plantilla_vm=cfg_vm()), banco.inv, reloj=banco.reloj)
    assert not res.plan.bloqueado
    assert sesion.avisos == antes and len(_avisos(sesion, CodigoAviso.RAMA_8_SIN_SOPORTE)) == 1


@pytest.mark.parametrize("texto", ["9.0", "9.1", "9.2", "9.2.1", "10.0"])
def test_ca_d2_2_2_la_rama_9_y_posteriores_no_llevan_el_aviso(servicio, texto):
    sesion, _ = _conectar(servicio, texto)
    assert _avisos(sesion, CodigoAviso.RAMA_8_SIN_SOPORTE) == []


def test_ca_d2_2_3_la_version_forzada_no_quita_el_aviso_porque_manda_la_detectada(servicio):
    """CL-D1: servidor 8.4 con versión forzada 9.2: funciones de 9.2, aviso por la detectada."""
    sesion, _ = _conectar(servicio, "8.4.1", version_forzada=(9, 2))
    assert sesion.capacidades.forzada is True and sesion.capacidades.version == (9, 2)
    assert sesion.capacidades.tiene(Funcion.HOST_ARCH_EN_RESOURCES)
    assert len(_avisos(sesion, CodigoAviso.RAMA_8_SIN_SOPORTE)) == 1


def test_ca_d2_2_3_un_servidor_9_2_forzado_a_8_4_no_lleva_el_aviso(servicio):
    sesion, _ = _conectar(servicio, "9.2.1", version_forzada=(8, 4))
    assert _avisos(sesion, CodigoAviso.RAMA_8_SIN_SOPORTE) == []


@pytest.mark.parametrize(
    ("version", "esperado"), [((8, 4), True), ((8, 99), True), ((9, 0), False), ((10, 0), False)]
)
def test_es_rama_8(version, esperado):
    assert es_rama_8(version) is esperado


# --- CA-D2.3: selector de versión forzada y preferencias ------------------------------------------


def test_ca_d2_3_1_las_versiones_conocidas_son_exactamente_8_4_9_0_9_1_y_9_2():
    assert VERSIONES_CONOCIDAS == ((8, 4), (9, 0), (9, 1), (9, 2))
    assert all(v >= (8, 4) for v in VERSIONES_CONOCIDAS)


@pytest.mark.parametrize("texto", ["8.0", "8.1", "8.2", "8.3"])
def test_ca_d2_3_2_una_version_forzada_anterior_a_8_4_se_descarta_con_aviso(tmp_path, texto):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"version_esquema": 1, "version_forzada": texto}), encoding="utf-8")
    repo = RepositorioPreferencias(ruta)
    pref = repo.cargar()
    assert pref.version_forzada is None  # vuelve a «Detectar»
    assert repo.version_forzada_descartada == texto
    assert repo.hubo_corrupcion is False  # la carga no se rompe


@pytest.mark.parametrize("texto", ["8.4", "9.0", "9.1", "9.2"])
def test_ca_d2_3_2_una_version_forzada_valida_se_conserva_sin_aviso(tmp_path, texto):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"version_esquema": 1, "version_forzada": texto}), encoding="utf-8")
    repo = RepositorioPreferencias(ruta)
    mayor, menor = (int(x) for x in texto.split("."))
    assert repo.cargar().version_forzada == (mayor, menor)
    assert repo.version_forzada_descartada is None


@pytest.mark.parametrize("valor", [None, "", "abc", "8", "8.4.1", 84, ["8.2"]])
def test_ca_d2_3_2_una_version_forzada_ilegible_se_ignora_sin_romper_la_carga(tmp_path, valor):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"version_esquema": 1, "version_forzada": valor}), encoding="utf-8")
    repo = RepositorioPreferencias(ruta)
    assert repo.cargar().version_forzada is None
    assert repo.version_forzada_descartada is None


def test_ca_d2_3_2_guardar_tras_descartar_ya_no_escribe_la_version_antigua(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"version_esquema": 1, "version_forzada": "8.2"}), encoding="utf-8")
    repo = RepositorioPreferencias(ruta)
    repo.guardar(repo.cargar())
    assert json.loads(ruta.read_text(encoding="utf-8"))["version_forzada"] is None
    assert Preferencias().version_forzada is None


def test_ca_d2_3_3_una_version_forzada_8_4_sobre_un_servidor_9_2_manda_en_las_funciones():
    caps = capacidades_para(Version("9.2.1", 9, 2, 1), (8, 4))
    assert caps.forzada and caps.version == (8, 4)
    for f in (
        Funcion.MAPEO_DRIVER_KEEP,
        Funcion.CPU_PERSONALIZADA_POR_MAPPING,
        Funcion.CAPACIDADES_POR_ARCH,
        Funcion.HOST_ARCH_EN_RESOURCES,
        Funcion.NODO_ARM64,
    ):
        assert not caps.tiene(f), f


# --- CA-D2.4: lo que desaparece al subir la mínima ---------------------------------------

_RETIRADAS = (
    "DESCARGAR_URL",
    "IMPORTAR_DISCO",
    "SUBIR_IMAGEN_DISCO",
    "TPM_CLON_COMPLETO",
    "ASISTENTE_PLANTILLA_IMAGEN",
    "SDN_INCLUIDO",
)


@pytest.mark.parametrize("nombre", _RETIRADAS)
def test_ca_d2_4_1_la_funcion_retirada_ya_no_existe_en_funcion_ni_en_tabla(nombre):
    assert nombre not in Funcion.__members__
    assert nombre.lower() not in {f.value for f in Funcion}
    assert nombre.lower() not in {str(f) for f in cap.TABLA}


def test_ca_d2_4_1_ningun_modulo_de_src_hace_referencia_a_las_funciones_retiradas():
    """Recorre todo ``src/``: ni ``Funcion.X`` ni ``caps.tiene(Funcion.X)`` de las seis."""
    patron = re.compile(r"\bFuncion\.(" + "|".join(_RETIRADAS) + r")\b")
    hallazgos = [
        f"{ruta.relative_to(RAIZ_SRC)}:{n}"
        for ruta in RAIZ_SRC.rglob("*.py")
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        if patron.search(linea)
    ]
    assert hallazgos == []


def test_ca_d2_4_1_las_demas_funciones_se_conservan():
    for f in (
        "CLAVES_MS_2023",
        "CLOUDINIT_PRIVILEGIO_PROPIO",
        "PRIVILEGIOS_GUEST_AGENT",
        "CLOUDINIT_PRIVILEGIO_INCIERTO",
        "CICUSTOM_CON_ALLOCATESPACE",
    ):
        assert f in Funcion.__members__


def test_ca_d2_4_4_con_8_4_el_asistente_de_imagen_cloud_esta_disponible_sin_mensaje_de_version():
    caps = capacidades_para(Version("8.4.1", 8, 4, 1), None)
    assert cap.asistente_plantilla_disponible(caps) is True
    assert cap.asistente_plantilla_disponible(None) is False


def test_ca_d2_4_4_con_8_4_importar_descargar_y_subir_estan_habilitados_sin_motivo_de_version():
    from proxlaunch.nucleo.origen.capacidades_origen import (
        Disponibilidad,
        Via,
        calcular_capacidades,
    )

    from .apoyo_fase_d import V_84, caps_de, inv_arq

    inv = inv_arq(nodos=("pve1",), version=V_84)
    co = calcular_capacidades(caps_de(V_84), inv, "pve1")
    for via in (Via.IMPORTAR, Via.SUBIR_IMAGEN, Via.DESCARGAR_IMAGEN, Via.DESCARGAR_URL):
        estado = co.estado(via)
        assert estado.disponibilidad != Disponibilidad.NO, via
        assert "version" not in estado.params, via
        assert estado.codigo != CodigoError.IMPORTAR_VERSION_NO_SOPORTADA


# --- CA-D0.4: funciones por versión ------------------------------------------------------

_DESDE = {
    Funcion.MAPEO_DRIVER_KEEP: (9, 1),
    Funcion.CPU_PERSONALIZADA_POR_MAPPING: (9, 2),
    Funcion.CAPACIDADES_POR_ARCH: (9, 2),
    Funcion.HOST_ARCH_EN_RESOURCES: (9, 2),
    Funcion.NODO_ARM64: (9, 2),
}


@pytest.mark.parametrize("funcion", sorted(_DESDE))
@pytest.mark.parametrize("version", [(8, 4), (9, 0), (9, 1), (9, 2)])
def test_ca_d0_4_1_cada_funcion_de_d_esta_disponible_solo_desde_su_version(funcion, version):
    caps = Capacidades(version, True)
    assert caps.tiene(funcion) is (version >= _DESDE[funcion])
    assert caps.requisito(funcion) == _DESDE[funcion]


def test_ca_d0_4_1_la_tabla_incluye_justo_las_cinco_funciones_de_d():
    nuevas = {f for f in Funcion if f.value in {
        "mapeo_driver_keep", "cpu_personalizada_por_mapping", "capacidades_por_arch",
        "host_arch_en_resources", "nodo_arm64",
    }}  # fmt: skip
    assert nuevas == set(_DESDE)
    assert set(Funcion) == set(cap.TABLA)


def test_ca_d0_4_1_las_funciones_que_existen_desde_8_4_no_tienen_bandera_de_d():
    """Mapeos PCI/USB y migración con mapeos existen desde 8.x: sin ``Funcion`` propia."""
    nombres = {f.value for f in Funcion}
    assert not any(("mapeo_pci" in n or "mapeo_usb" in n or n == "mapeos") for n in nombres)


def test_ca_d0_4_1_las_versiones_solo_se_comparan_en_capacidades():
    """El resto de ``src/`` no compara ``version >= (9, x)`` a mano (CA-09.6)."""
    patron = re.compile(r"\bversion(?:_validacion)?\s*(?:>=|<|>|<=)\s*\(\s*(?:8|9)\s*,")
    # ``notas.py`` conserva desde 0.6 una guarda ``version >= (8, 3)`` (issue 5486 de Proxmox):
    # con la mínima 8.4 es siempre verdadera pero no es una función de la tabla.
    permitidos = {"capacidades.py", "notas.py"}
    hallazgos = [
        f"{ruta.relative_to(RAIZ_SRC)}:{n}"
        for ruta in RAIZ_SRC.rglob("*.py")
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        if ruta.name not in permitidos and patron.search(linea)
    ]
    assert hallazgos == [], hallazgos


def test_ca_d0_4_2_driver_keep_con_9_0_da_v_d60_y_con_9_1_y_9_2_se_acepta():
    from proxlaunch.nucleo.arquitectura.modelos import Arquitectura
    from proxlaunch.nucleo.hardware_cluster.validacion import validar_hardware_local

    from .apoyo_fase_a import cfg_vm
    from .apoyo_fase_d import con_hardware, pci

    cfg = con_hardware(cfg_vm(), pci("gpu-a2", driver_keep=True))
    for version, bloquea in (((9, 0), True), ((9, 1), False), ((9, 2), False), ((8, 4), True)):
        codigos = [
            p.codigo
            for p in validar_hardware_local(cfg, Capacidades(version, True), Arquitectura.X86_64)
        ]
        assert ("V-D60" in codigos) is bloquea, version
