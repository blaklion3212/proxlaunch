"""MVP 4: CSV, perfiles de máquina, lotes guardados, descubrimiento, informe y errores E-O.

Requisitos: RF-O26 (CA-O26.1..O26.5), RF-O27 (CA-O27.2/O27.3/O27.6), RF-O28 (CA-O28.1..O28.8,
O28.12), RF-O31 (CA-O31.1..O31.3, D-25.2), RF-O04 (sin GET nuevos), CA-O02.6 (permisos que fallan),
RF-O25/RF-O30 (informe: archivos subidos, nada de URL ni rutas), RNF-O07 (códigos estables),
INV-O1 (cargar/aplicar/importar no transfiere nada).
"""

import dataclasses

import pytest

from proxlaunch.nucleo.api.traductor_errores import traducir_exitstatus, traducir_http
from proxlaunch.nucleo.csv_importacion import unidades
from proxlaunch.nucleo.csv_importacion.unidades import ValorInvalido
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.informe import construir_informe
from proxlaunch.nucleo.lote.modelos import DefinicionLote, FilaLote, MetadatosInforme, PatronNombres
from proxlaunch.nucleo.lotes_guardados.revalidacion import TipoDesajuste, desajustes
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleIso,
    ModoClon,
    RefVolumen,
    TipoSO,
)
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, Firmware, OrigenSO
from proxlaunch.nucleo.perfiles_maquina.aplicar import (
    aplicar_config,
    aplicar_perfil,
    config_desde_configuracion,
)
from proxlaunch.nucleo.perfiles_maquina.compatibilidad import funciones_requeridas
from proxlaunch.nucleo.perfiles_maquina.fabrica import CLAVES_FABRICA, perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PistaOrigen,
    RedPerfil,
)
from proxlaunch.nucleo.servicios.descubrimiento import descubrir
from proxlaunch.nucleo.transferencias.modelos import (
    EstadoTransferencia,
    RegistroTransferencia,
    TipoTransferencia,
)
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_api import TransporteFalso, crear_sesion, dato, rutas_inventario
from .apoyo_lote import crear_banco, definicion
from .apoyo_mvp3 import importar_csv, perfil_base, regla_de
from .apoyo_mvp4 import (
    ROL_MVP4,
    VOLID_IMAGEN,
    VOLID_ISO,
    ClusterM4,
    cfg_base,
    cfg_clon,
    cfg_import,
    cfg_iso,
    inv_origen,
    listado,
    plantilla_pve,
)

# --- CSV: valores de las columnas nuevas (RF-O28) -------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("vacio", OrigenSO.DISCO_VACIO), ("disco_vacio", OrigenSO.DISCO_VACIO),
        ("Vacío", OrigenSO.DISCO_VACIO), ("iso", OrigenSO.ISO), ("ISO", OrigenSO.ISO),
        ("importar", OrigenSO.IMPORTAR_DISCO), ("imagen", OrigenSO.IMPORTAR_DISCO),
        ("importar_disco", OrigenSO.IMPORTAR_DISCO), ("clonar", OrigenSO.CLONAR_PLANTILLA),
        ("Plantilla", OrigenSO.CLONAR_PLANTILLA), ("  CLONAR  ", OrigenSO.CLONAR_PLANTILLA),
    ],
)  # fmt: skip
def test_ca_o28_origen_sin_distinguir_mayusculas_ni_acentos(texto, esperado):
    assert unidades.origen(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("linux", TipoSO.LINUX), ("Windows 11", TipoSO.WINDOWS_11), ("windows_11", TipoSO.WINDOWS_11),  # noqa: E501
        ("windows server 2022/2025", TipoSO.WINDOWS_SERVER_2022_2025),
        ("Windows-Server_2022_2025", TipoSO.WINDOWS_SERVER_2022_2025),
        ("windows 10", TipoSO.WINDOWS_10), ("windows server 2016/2019", TipoSO.WINDOWS_SERVER_2016_2019),  # noqa: E501
        ("otro", TipoSO.OTRO),
    ],
)  # fmt: skip
def test_ca_o28_so_acepta_los_seis_valores_del_asistente(texto, esperado):
    assert unidades.tipo_so(texto) == esperado


def test_ca_o28_modo_clon_si_no_y_valores_invalidos_con_ejemplo():
    assert unidades.modo_clon("auto") == ModoClon.AUTOMATICO
    assert unidades.modo_clon("Enlazado") == ModoClon.ENLAZADO
    assert unidades.modo_clon("completo") == ModoClon.COMPLETO
    for si in ("si", "sí", "yes", "true", "1"):
        assert unidades.si_no(si) is True
    for no in ("no", "false", "0"):
        assert unidades.si_no(no) is False
    for funcion, malo in ((unidades.origen, "ova"), (unidades.tipo_so, "mac"), (unidades.si_no, "quizá"),  # noqa: E501
                          (unidades.modo_clon, "rapido")):  # fmt: skip
        with pytest.raises(ValorInvalido) as e:
            funcion(malo)
        assert "E-M11" in e.value.regla


# --- CSV: filas con origen (RF-O28) ---------------------------------------------------------------

ENC = "nombre;origen;fuente;so;virtio;modo_clon;cpu;memoria;disco"


def _csv(*filas, inv=None, **kw):
    return importar_csv([ENC, *filas], inv=inv, **kw)


def _fila(r, n):
    return next(f for f in r.filas if f.numero == n)


def test_ca_o28_1_sin_columna_origen_todas_las_filas_son_disco_vacio_como_en_mvp3():
    r = importar_csv(["nombre;cpu", "a-01;2", "a-02;4"])
    assert {f.cfg.origen for f in r.filas} == {OrigenSO.DISCO_VACIO}
    assert all(f.cfg.detalle_origen is None and f.cfg.tipo_so is None for f in r.filas)


def test_ca_o28_4_filas_de_iso_importacion_y_clon_forman_un_solo_lote_por_filas():
    r = _csv(
        "a-01;iso;alpine.iso;linux;;;;;", "a-02;importar;cirros.qcow2;;;;;;60",
        "a-03;clonar;base;;;enlazado;4;8;80", "a-04;vacio;;;;;;;",
    )  # fmt: skip
    f1, f2, f3, f4 = r.filas
    assert [f.cfg.origen for f in r.filas] == [
        OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO, OrigenSO.CLONAR_PLANTILLA, OrigenSO.DISCO_VACIO,
    ]  # fmt: skip
    assert all(
        f.problemas == () or not [p for p in f.problemas if p.severidad == Severidad.ERROR]
        for f in r.filas
    )
    assert f1.cfg.detalle_origen.iso.nombre == "alpine.iso" and f1.cfg.tipo_so == TipoSO.LINUX
    assert f2.cfg.detalle_origen.imagen.nombre == "cirros.qcow2"
    assert f2.cfg.detalle_origen.ampliar_a_gib == 60  # `disco` en importación = ampliar a (RF-O28)
    d3 = f3.cfg.detalle_origen
    assert d3.plantilla.nombre == "base" and d3.modo == ModoClon.ENLAZADO
    assert (d3.ajustes.cores, d3.ajustes.memoria_mib, d3.ajustes.disco_gib) == (4, 8192, 80)
    assert f4.cfg.detalle_origen is None


def test_ca_o28_2_origen_iso_sin_fuente_es_error_de_fila_y_columna():
    r = _csv("a-01;iso;;linux;;;;;")
    (e,) = [p for p in _fila(r, 2).problemas if p.severidad == Severidad.ERROR]
    assert (e.regla, e.columna) == ("V-O01", "fuente") and _fila(r, 2).estado.value == "con_error"


@pytest.mark.parametrize(
    ("celda", "regla"),
    [
        ("http://evil.example/a.iso", "E-O21"),  # CA-O28.6: nunca se descarga desde el CSV
        ("https://u:p@x.org/a.iso", "E-O21"),
        ("ftp://x/a.iso", "E-O21"),
        ("www.x.org/a.iso", "E-O21"),
        ("/var/lib/vz/template/iso/a.iso", "E-O14"),  # CA-O28.7
        ("C:\\isos\\a.iso", "E-O14"),
    ],
)
def test_ca_o28_6_o28_7_fuente_con_url_o_ruta_absoluta_es_error_y_no_se_interpreta(celda, regla):
    r = _csv(f"a-01;iso;{celda};linux;;;;;")
    f = _fila(r, 2)
    assert regla in [p.regla for p in f.problemas] and f.estado.value == "con_error"
    assert f.cfg is None  # la fila con error no produce ninguna configuración: nada se descarga


_URL_SECRETA = "https://u:clave-secreta@x.org/a.iso?token=T0K3N"


def test_inv_o6_el_csv_de_errores_no_escribe_la_url_de_la_celda_fuente(tmp_path):
    from proxlaunch.nucleo.csv_importacion.errores_csv import escribir_filas_con_error
    from proxlaunch.nucleo.csv_importacion.interpretacion import interpretar

    from .apoyo_mvp3 import tabla_csv

    tabla = tabla_csv([ENC, f"a-01;iso;{_URL_SECRETA};linux;;;;;"])
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    ruta = tmp_path / "errores.csv"
    escribir_filas_con_error(ruta, tabla, resultado, lambda p: p.regla)
    texto = ruta.read_text(encoding="utf-8-sig")
    assert "clave-secreta" not in texto and "T0K3N" not in texto


def test_inv_o6_el_problema_de_celda_no_repite_la_url_con_credenciales():
    r = _csv(f"a-01;iso;{_URL_SECRETA};linux;;;;;")
    for problema in _fila(r, 2).problemas:
        assert "clave-secreta" not in repr(problema) and "T0K3N" not in repr(problema)


@pytest.mark.parametrize(
    "celda", ["=cmd|calc", "+1+1", "-2", "@SUM(A1)", "a.iso,media=disk", "x y.iso"]
)
def test_ca_o28_8_fuente_con_disparador_o_caracteres_peligrosos_es_texto_y_no_pasa_la_lista_blanca(
    celda,
):
    r = _csv(f"a-01;iso;{celda};linux;;;;;")
    f = _fila(r, 2)
    assert f.estado.value == "con_error"
    assert f.cfg is None or f.cfg.detalle_origen.iso.volid is None  # nunca llega a un parámetro


def test_fuente_con_volid_completo_se_guarda_como_volid_y_nombre():
    r = _csv("a-01;iso;local:iso/a.iso;otro;;;;;", "a-02;importar;local:import/c.qcow2;;;;;;")
    assert _fila(r, 2).cfg.detalle_origen.iso == RefVolumen("a.iso", "local:iso/a.iso")
    assert _fila(r, 3).cfg.detalle_origen.imagen.volid == "local:import/c.qcow2"


def test_ca_o28_origen_invalido_es_e_m11_con_los_valores_validos():
    r = _csv("a-01;ova;x;;;;;;")
    (e,) = [p for p in _fila(r, 2).problemas if p.severidad == Severidad.ERROR]
    assert e.regla == "E-M11.valor_no_admitido" and e.columna == "origen"
    assert e.params["validos"] == "vacio, iso, importar, clonar"


def test_ca_o28_columnas_de_so_y_virtio_aplican_el_asistente_y_los_drivers():
    r = _csv("w-01;iso;win11.iso;windows 11;si;;;;", "w-02;iso;win10.iso;windows 10;no;;;;")
    c1, c2 = _fila(r, 2).cfg, _fila(r, 3).cfg
    assert (c1.firmware, c1.tpm, c1.agente_qemu, c1.tipo_so) == (
        Firmware.OVMF,
        True,
        True,
        TipoSO.WINDOWS_11,
    )
    assert c1.detalle_origen.sin_drivers is False
    assert (
        c2.detalle_origen.sin_drivers is True and c2.tpm is False and c2.firmware == Firmware.OVMF
    )


def test_ca_o28_5_precedencia_defecto_perfil_columnas_una_columna_presente_siempre_gana():
    por_id = {p.id: p for p in perfiles_fabrica()}
    r = importar_csv(
        [
            "nombre;perfil;origen;so",
            "p-01;fabrica.linux-red-hat;;",
            "p-02;fabrica.linux-red-hat;vacio;",
        ]
    )
    # sin columna `origen` la fila hereda el origen sugerido del perfil (ISO + linux) …
    assert _fila(r, 2).cfg.origen == OrigenSO.ISO and _fila(r, 2).cfg.tipo_so == TipoSO.LINUX
    # … y una columna presente (aunque sea «vacío») gana sobre el perfil.
    assert _fila(r, 3).cfg.origen == OrigenSO.DISCO_VACIO and _fila(r, 3).cfg.tipo_so is None
    assert por_id["fabrica.linux-red-hat"].config.origen == OrigenSO.ISO
    r2 = importar_csv(["nombre;perfil;so", "p-03;fabrica.linux-red-hat;windows 11"])
    assert _fila(r2, 2).cfg.tipo_so == TipoSO.WINDOWS_11


def test_ca_o28_5_cpu_memoria_y_disco_de_una_fila_clon_son_ajustes_no_pisan_los_de_la_plantilla():
    r = _csv("c-01;clonar;base;;;;;;", "c-02;clonar;base;;;;4;;")
    a1 = _fila(r, 2).cfg.detalle_origen.ajustes
    a2 = _fila(r, 3).cfg.detalle_origen.ajustes
    assert a1 == AjustesClon() and a2.cores == 4  # sin celda → «igual que la plantilla»


def test_ca_o28_12_el_limite_de_filas_del_lote_no_cambia():
    from proxlaunch.nucleo.lote.constantes import MAX_LOTE

    assert MAX_LOTE == 100


def test_ca_o28_3_con_catalogo_leido_una_fuente_inexistente_da_error_con_alternativas():
    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO, "local:iso/b.iso"),)
    )
    r = _csv("a-01;iso;falta.iso;linux;;;;;", inv=inv, nodo_referencia="pve1")
    f = _fila(r, 2)
    (e,) = [p for p in f.problemas if p.regla == "V-O02"]
    assert e.severidad == Severidad.ERROR and e.params["motivo"] == "no_disponible"
    assert e.params["alternativas"] == "alpine.iso, b.iso" and e.columna == "fuente"


def test_ca_o28_3_fuente_ambigua_en_dos_storages_pide_el_volid_completo():
    inv = inv_origen(listados=(
        listado("pve1", "local", Contenido.ISO, "local:iso/igual.iso"),
        listado("pve1", "nfs1", Contenido.ISO, "nfs1:iso/igual.iso"),
    ))  # fmt: skip
    r = _csv("a-01;iso;igual.iso;linux;;;;;", inv=inv, nodo_referencia="pve1")
    assert "V-O02.ambiguo" in regla_de(r, 2)
    r2 = _csv("a-01;iso;nfs1:iso/igual.iso;linux;;;;;", inv=inv, nodo_referencia="pve1")
    assert "V-O02.ambiguo" not in regla_de(r2, 2)


def test_la_exportacion_del_csv_neutraliza_disparadores_en_origen_y_fuente(tmp_path):
    from proxlaunch.nucleo.archivos.csv_seguro import escribir_csv

    ruta = tmp_path / "e.csv"
    escribir_csv(ruta, ("nombre", "fuente"), [["a-01", '=HYPERLINK("http://x")'], ["a-02", "@x"]])
    texto = ruta.read_text(encoding="utf-8-sig")
    for linea in texto.splitlines()[1:]:
        assert not linea.split(";")[1].strip('"').startswith(("=", "@", "+", "-"))


# --- Perfiles de fábrica (RF-O31, D-25.2) ---------------------------------------------------------


def test_d_25_hay_nueve_perfiles_de_fabrica_los_seis_de_m3_primero_y_son_inmutables():
    ps = perfiles_fabrica()
    assert len(ps) == 9 and CLAVES_FABRICA[-3:] == ("windows-11", "windows-server", "linux-red-hat")
    assert [p.id for p in ps[:6]] == [
        f"fabrica.{c}" for c in ("servidor-pequeno", "servidor-mediano", "base-de-datos",
                                 "servidor-grande", "escritorio-compatible", "minimo")
    ]  # fmt: skip
    assert all(p.origen == OrigenPerfil.FABRICA for p in ps)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ps[6].nombre = "otro"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ps[6].config.cores = 99  # type: ignore[misc]


def test_ca_o31_1_windows_11_4_nucleos_8_gib_64_gib_ovmf_tpm_origen_iso_sin_fuente():
    c = {p.id: p for p in perfiles_fabrica()}["fabrica.windows-11"].config
    assert (c.cores, c.sockets, c.memoria_mib, c.discos[0].tamano_gib) == (4, 1, 8192, 64)
    assert (c.firmware, c.tpm, c.agente_qemu, c.tipo_so) == (
        Firmware.OVMF,
        True,
        True,
        TipoSO.WINDOWS_11,
    )
    assert c.origen == OrigenSO.ISO and c.pista_origen is None  # sin ISO ni fuente


def test_ca_o31_windows_server_y_linux_red_hat_describen_solo_hardware():
    por_id = {p.id: p.config for p in perfiles_fabrica()}
    ws = por_id["fabrica.windows-server"]
    assert (ws.tipo_so, ws.tpm, ws.firmware, ws.origen) == (
        TipoSO.WINDOWS_SERVER_2022_2025, True, Firmware.OVMF, OrigenSO.ISO,
    )  # fmt: skip
    rh = por_id["fabrica.linux-red-hat"]
    assert (rh.tipo_so, rh.tpm, rh.firmware, rh.origen) == (
        TipoSO.LINUX,
        False,
        Firmware.SEABIOS,
        OrigenSO.ISO,
    )
    for c in por_id.values():
        assert c.pista_origen is None and c.discos[0].storage_preferido is None


def test_ca_o31_1_aplicar_un_perfil_nuevo_deja_origen_iso_sin_fuente_y_bloquea():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    perfil = {p.id: p for p in perfiles_fabrica()}["fabrica.windows-11"]
    base = ConfiguracionVM(vmid=100, nombre="w11", nodo="pve1")
    res = aplicar_perfil(perfil, base, inv)
    cfg = res.cfg
    assert cfg.origen == OrigenSO.ISO and cfg.tipo_so == TipoSO.WINDOWS_11 and cfg.tpm is True
    assert isinstance(cfg.detalle_origen, DetalleIso) and not cfg.detalle_origen.iso.nombre
    from proxlaunch.nucleo.capacidades import capacidades_para
    from proxlaunch.nucleo.modelos.inventario import Version

    problemas = validar_vm(cfg, inv, capacidades_para(Version("9.2", 9, 2, 0), None))
    assert "V-O01" in [p.codigo for p in problemas if p.severidad == Severidad.ERROR]  # CA-O26.2


# --- Perfiles con origen sugerido (RF-O26) --------------------------------------------------------


def _hw(**kw):
    return ConfigPerfil(discos=(DiscoPerfil(32),), redes=(RedPerfil(),), **kw)


def test_ca_o26_1_un_perfil_iso_con_pista_elige_el_iso_si_existe_en_el_catalogo():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),))
    cfg = _hw(
        origen=OrigenSO.ISO, tipo_so=TipoSO.LINUX, pista_origen=PistaOrigen("alpine.iso", "local")
    )
    res = aplicar_config(cfg, ConfiguracionVM(vmid=100, nombre="a", nodo="pve1"), inv)
    assert res.cfg.detalle_origen.iso == RefVolumen("alpine.iso", VOLID_ISO) and res.avisos == ()


def test_ca_o26_2_si_la_fuente_no_existe_se_avisa_y_no_se_cambia_a_vacia_en_silencio():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, "local:iso/otra.iso"),))
    cfg = _hw(origen=OrigenSO.ISO, tipo_so=TipoSO.LINUX, pista_origen=PistaOrigen("alpine.iso"))
    res = aplicar_config(cfg, ConfiguracionVM(vmid=100, nombre="a", nodo="pve1"), inv)
    assert res.cfg.origen == OrigenSO.ISO  # sigue elegido el origen
    assert [(a.recurso, a.pedido, a.usado) for a in res.avisos] == [("fuente", "alpine.iso", None)]
    assert res.cfg.detalle_origen.iso.volid is None


def test_ca_o26_1_la_pista_de_importacion_y_de_clon_se_resuelven_por_nombre():
    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.IMPORT, VOLID_IMAGEN),),
        plantillas=(plantilla_pve(9000, "base", "pve1"),),
    )
    imp = _hw(
        origen=OrigenSO.IMPORTAR_DISCO, pista_origen=PistaOrigen("cirros.qcow2", ampliar_a_gib=40)
    )
    r = aplicar_config(imp, ConfiguracionVM(vmid=100, nombre="a", nodo="pve1"), inv)
    assert (
        r.cfg.detalle_origen.imagen.volid == VOLID_IMAGEN
        and r.cfg.detalle_origen.ampliar_a_gib == 40
    )
    clon = _hw(
        origen=OrigenSO.CLONAR_PLANTILLA,
        pista_origen=PistaOrigen("base", modo_clon=ModoClon.COMPLETO),
    )
    r = aplicar_config(clon, ConfiguracionVM(vmid=100, nombre="a", nodo="pve1"), inv)
    d = r.cfg.detalle_origen
    assert (d.plantilla.nombre, d.plantilla.vmid, d.modo) == ("base", 9000, ModoClon.COMPLETO)


def test_ca_o26_5_un_perfil_de_clon_no_pisa_nucleos_memoria_ni_disco_de_la_plantilla():
    cfg = _hw(
        origen=OrigenSO.CLONAR_PLANTILLA,
        cores=16,
        memoria_mib=65536,
        pista_origen=PistaOrigen("base"),
    )
    actual = ConfiguracionVM(vmid=100, nombre="a", nodo="pve1", cores=3, memoria_mib=3072)
    res = aplicar_config(cfg, actual, inv_origen(plantillas=(plantilla_pve(),)))
    assert (res.cfg.cores, res.cfg.memoria_mib) == (3, 3072)
    assert res.cfg.tipo_so is None and res.cfg.tpm is False


def test_ca_o26_9_inv_o1_aplicar_un_perfil_con_origen_no_hace_ninguna_peticion():
    """aplicar_config es pura: recibe el inventario ya leído y no tiene acceso a la red."""
    import inspect

    firma = inspect.signature(aplicar_config)
    assert "sesion" not in firma.parameters and "cliente" not in firma.parameters


def test_ca_o26_4_guardar_como_perfil_con_y_sin_pistas():
    cfg = cfg_iso(volid=VOLID_ISO)
    con = config_desde_configuracion(cfg, con_pistas=True)
    sin = config_desde_configuracion(cfg, con_pistas=False)
    assert con.origen == OrigenSO.ISO and con.tipo_so == TipoSO.LINUX
    assert (
        con.pista_origen.nombre_fuente == "alpine.iso"
        and con.pista_origen.storage_preferido == "local"
    )
    # Sin la casilla de pistas el perfil se guarda con origen `disco_vacio` explícito (CA-O26.4).
    assert sin.origen == OrigenSO.DISCO_VACIO and sin.pista_origen is None


def test_la_compatibilidad_del_perfil_no_pide_ninguna_funcion_por_origen_con_la_minima_8_4():
    """DT-D3: importar disco ya no depende de la versión; ningún origen exige funciones."""
    for origen in OrigenSO:
        assert funciones_requeridas(_hw(origen=origen)) == frozenset()


# --- Lotes guardados (RF-O27) ---------------------------------------------------------------------


def _lote(cfg):
    return DefinicionLote(cfg, 2, PatronNombres("web"))


def test_ca_o27_2_ca_o27_6_la_revalidacion_marca_las_fuentes_que_el_servidor_no_tiene():
    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.ISO, "local:iso/otra.iso"),
                  listado("pve1", "local", Contenido.IMPORT)),
        plantillas=(plantilla_pve(9000, "otra", "pve1"),),
    )  # fmt: skip
    iso = _lote(
        cfg_iso(tipo_so=TipoSO.WINDOWS_10, drivers=VOLID_ISO.replace("alpine", "virtio-win"))
    )
    tipos = {d.tipo for d in desajustes(iso, inv)}
    assert {TipoDesajuste.ISO, TipoDesajuste.DRIVERS} <= tipos
    imagen = desajustes(_lote(cfg_import()), inv)
    assert [(d.tipo, d.valor) for d in imagen if d.tipo == TipoDesajuste.IMAGEN] == [
        (TipoDesajuste.IMAGEN, VOLID_IMAGEN)
    ]
    plantilla = desajustes(_lote(cfg_clon("base")), inv)
    (d,) = [x for x in plantilla if x.tipo == TipoDesajuste.PLANTILLA]
    assert (
        d.valor == "base"
        and d.disponibles == ("otra",)
        and d.campos == ("detalle_origen.plantilla",)
    )


def test_ca_o27_2_sin_leer_el_catalogo_no_se_afirma_ningun_desajuste_de_fuente():
    inv = inv_origen()
    tipos = {d.tipo for d in desajustes(_lote(cfg_iso()), inv)}
    assert tipos <= {TipoDesajuste.STORAGE, TipoDesajuste.BRIDGE, TipoDesajuste.NODO,
                     TipoDesajuste.STORAGE_EFI}  # fmt: skip
    inv.catalogo = None
    assert not {d.tipo for d in desajustes(_lote(cfg_clon("base")), inv)} & {
        TipoDesajuste.PLANTILLA
    }


def test_ca_o27_2_una_fuente_valida_en_el_servidor_no_da_desajuste():
    inv = inv_origen(
        listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),),
        plantillas=(plantilla_pve(9000, "base", "pve1"),),
    )
    for cfg in (cfg_iso(), cfg_clon("base")):
        assert not [d for d in desajustes(_lote(cfg), inv) if d.tipo in (
            TipoDesajuste.ISO, TipoDesajuste.PLANTILLA)]  # fmt: skip


def test_ca_o27_7_un_lote_por_filas_indica_la_fila_afectada_por_cada_fuente():
    inv = inv_origen(listados=(listado("pve1", "local", Contenido.ISO, VOLID_ISO),),
                     plantillas=(plantilla_pve(9000, "base", "pve1"),))  # fmt: skip
    filas = (
        FilaLote("a-01", cfg_iso()), FilaLote("a-02", cfg_iso("local:iso/falta.iso")),
        FilaLote("a-03", cfg_clon("nueva")),
    )  # fmt: skip
    d = DefinicionLote(cfg_base(), 0, PatronNombres("x"), filas=filas)
    por_tipo = {x.tipo: x for x in desajustes(d, inv)}
    assert por_tipo[TipoDesajuste.ISO].indices == (1,)
    assert por_tipo[TipoDesajuste.ISO].campos == ("filas[1].detalle_origen.iso",)
    assert por_tipo[TipoDesajuste.PLANTILLA].indices == (2,)


# --- Descubrimiento (RF-O04, CA-O02.6) ------------------------------------------------------------


def _transporte_inventario():
    t = TransporteFalso()
    rutas_inventario(t)
    return t


def test_ca_o04_el_descubrimiento_rellena_storages_todos_sin_peticiones_nuevas():
    t = _transporte_inventario()
    inv = descubrir(crear_sesion(t))
    todos = {s.id for s in inv.storages_todos["pve1"]}
    imagenes = {s.id for s in inv.storages["pve1"]}
    assert imagenes < todos  # el storage solo de ISO/backups ahora es visible para el MVP 4
    assert all("images" in s.contenido for s in inv.storages["pve1"])
    rutas = [c.ruta for c in t.llamadas if c.metodo == "GET"]
    assert rutas.count("/nodes/pve1/storage") == 1  # una sola lectura por nodo (cero GET nuevos)
    assert set(t.metodos) == {"GET"}


def test_ca_o02_6_el_descubrimiento_lee_los_permisos_una_vez_y_los_deja_en_el_catalogo():
    t = _transporte_inventario()
    inv = descubrir(crear_sesion(t))
    assert len(t.llamadas_a("GET", "/access/permissions")) == 1
    assert inv.catalogo.permisos is not None and inv.catalogo.permisos.tiene("VM.Allocate", "/")
    assert (
        inv.catalogo.listados == () and inv.catalogo.plantillas is None
    )  # nada se lee al conectar


def test_ca_o02_6_si_la_lectura_de_permisos_falla_quedan_desconocidos_y_la_conexion_sigue():
    t = _transporte_inventario()
    t.en("GET", "/access/permissions", ErrorProxLaunch(CodigoError.DESCONOCIDO, {}, "boom"))
    inv = descubrir(crear_sesion(t))
    assert inv.catalogo is not None and inv.catalogo.permisos is None
    assert len(inv.storages["pve1"]) > 0


# --- Informe (RF-O25, RF-O30) ---------------------------------------------------------------------


def _metadatos():
    return MetadatosInforme("lab", "9.2", False, None, "2026-11-14T10:00:00")


def test_ca_o25_2_el_informe_lista_los_archivos_subidos_en_la_sesion_sin_ruta_ni_url():
    banco, cl = _banco_clon()
    plan = banco.planificar(_lote_clon(2))
    libro = banco.ejecutar(plan)
    registros = (
        RegistroTransferencia(TipoTransferencia.SUBIDA, "alpine.iso", "local", "pve1", 1234, "10:00",  # noqa: E501
                              EstadoTransferencia.TERMINADA, VOLID_ISO),
        RegistroTransferencia(TipoTransferencia.DESCARGA, "virtio-win.iso", "local", "pve1", None, "10:05",  # noqa: E501
                              EstadoTransferencia.FALLIDA, None),
    )  # fmt: skip
    inf = construir_informe(plan, libro, _metadatos(), reloj=banco.reloj, transferencias=registros)
    assert [t.nombre_archivo for t in inf.transferencias] == ["alpine.iso", "virtio-win.iso"]
    assert inf.transferencias[0].volid == VOLID_ISO
    volcado = repr(inf)
    for prohibido in ("http://", "https://", "/home/", "token="):
        assert prohibido not in volcado


def test_ca_o30_5_ca_o30_6_el_informe_de_un_lote_de_clones_no_contiene_url_ni_rutas_locales():
    banco, cl = _banco_clon()
    plan = banco.planificar(_lote_clon(2))
    libro = banco.ejecutar(plan)
    inf = construir_informe(plan, libro, _metadatos(), reloj=banco.reloj)
    assert inf.transferencias == () and len(inf.entradas) == 2
    assert inf.plantilla is not None


def _banco_clon():
    cl = ClusterM4(("pve1",))
    cl.agregar_plantilla(9000, "base", "pve1")
    inv = inv_origen(nodos=("pve1",))
    banco = crear_banco(("pve1",), inv=inv, cluster=cl)
    return banco, cl


def _lote_clon(n):
    plant = cfg_clon("base", vmid=0, nombre="plantilla", nodo="", discos=[], redes=[])
    return definicion(n, plantilla_vm=plant)


# --- Errores E-O del traductor (RNF-O07: códigos estables) ----------------------------------------


def test_los_codigos_de_error_del_mvp4_son_estables_y_coinciden_con_la_tabla_de_errores():
    esperado = {
        "IMPORTAR_VERSION_NO_SOPORTADA": "importar_version_no_soportada",
        "IMPORTAR_SIN_STORAGE_IMPORT": "importar_sin_storage_import",
        "DESCARGA_URL_SIN_PERMISO": "descarga_url_sin_permiso",
        "STORAGE_RECORDADO_NO_DISPONIBLE": "storage_recordado_no_disponible",
        "CATALOGO_SIN_PERMISO": "catalogo_sin_permiso",
        "TRANSFERENCIA_NO_VERIFICADA": "transferencia_no_verificada",
        "TRANSFERENCIA_HUELLA_INCORRECTA": "transferencia_huella_incorrecta",
        "TRANSFERENCIA_CORTADA": "transferencia_cortada",
        "ARCHIVO_CAMBIO": "archivo_cambio",
        "NOMBRE_YA_EXISTE": "nombre_ya_existe",
        "DESCARGA_URL_FALLIDA": "descarga_url_fallida",
        "IMPORTAR_SIN_PERMISO": "importar_sin_permiso",
        "IMPORTAR_DESTINO_SIN_PERMISO": "importar_destino_sin_permiso",
        "RUTA_ABSOLUTA_NO_PERMITIDA": "ruta_absoluta_no_permitida",
        "IMAGEN_NO_ADMITIDA": "imagen_no_admitida",
        "FUENTE_DESAPARECIO": "fuente_desaparecio",
        "SIN_PLANTILLAS": "sin_plantillas",
        "CLON_NO_POSIBLE": "clon_no_posible",
        "CLON_ID_OCUPADO": "clon_id_ocupado",
        "FUENTE_ES_URL": "fuente_es_url",
        "ESPACIO_INSUFICIENTE_TRANSFERENCIA": "espacio_insuficiente_transferencia",
        "TRANSFERENCIA_EN_CURSO": "transferencia_en_curso",
        "AJUSTE_POST_CLON_FALLIDO": "ajuste_post_clon_fallido",
    }
    for nombre, valor in esperado.items():
        assert CodigoError[nombre].value == valor, nombre


@pytest.mark.parametrize(
    ("texto", "codigo"),
    [
        ("Only root can pass arbitrary filesystem paths.", CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA),
        ("backing file not allowed for untrusted image 'x.qcow2'!", CodigoError.IMAGEN_NO_ADMITIDA),
        ("can't clone to non-shared storage 'local-lvm'", CodigoError.CLON_NO_POSIBLE),
        ("storage 'x' does not support vm images", CodigoError.CLON_NO_POSIBLE),
        ("Linked clone feature is not supported for 'vm-1-disk-0'", CodigoError.CLON_NO_POSIBLE),
        ("unable to create VM 105: config file already exists", CodigoError.CLON_ID_OCUPADO),
    ],
)
def test_ca_o21_9_ca_o15_3_los_errores_del_servidor_del_mvp4_se_traducen_a_su_codigo(texto, codigo):
    assert traducir_http(500, texto, "").codigo == codigo
    assert traducir_exitstatus(texto).codigo == codigo


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        ("invalid filename or wrong extension", "filename"),
        ("storage 'local' does not support 'import' content", "content"),
        ("explicit 'media=cdrom' is required for ISO files", "media"),
        ("Shrinking disk size is not supported", "size"),
    ],
)
def test_los_rechazos_de_parametros_del_mvp4_dan_parametro_invalido_con_el_campo(texto, campo):
    e = traducir_http(400, texto, "")
    assert e.codigo == CodigoError.PARAMETRO_INVALIDO and e.params["campo"] == campo


def test_un_403_de_permiso_de_las_acciones_nuevas_nombra_privilegio_y_ruta_e_o20():
    e = traducir_http(
        403, "Permission check failed (/storage/local, Datastore.AllocateTemplate)", "", nodo="pve1"
    )
    assert e.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert (
        e.params["privilegio"] == "Datastore.AllocateTemplate"
        and e.params["ruta"] == "/storage/local"
    )


def test_el_rol_ampliado_de_14_privilegios_coincide_con_los_privilegios_que_usan_las_vias():
    from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH

    assert set(ROL_MVP4) == set(ROL_PROXLAUNCH) and len(ROL_PROXLAUNCH) == 14
    assert dato("9.2", "permisos_completos.json")  # el mock del laboratorio sigue disponible
