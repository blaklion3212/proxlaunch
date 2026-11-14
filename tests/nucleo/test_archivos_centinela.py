"""Prueba del centinela en todo el MVP 3 (CA-X04.4, CA-X04.5, CA-P01.6, CA-C11.8; INV-M2; RNF-M03).

Con una sesión simulada (token, contraseña, ticket y CSRF únicos, y un host, IP, usuario y perfil
de conexión reconocibles), guardar, exportar, cargar e importar perfiles, lotes y CSV, y exportar
CSV, no deja ningún centinela en archivos, registro (log) ni mensajes. Además las claves y columnas
con aspecto de credencial que traiga un archivo de terceros se ignoran SIN leerlas y no vuelven a
salir por ninguna vía.
"""

import json
import logging

import pytest

from proxlaunch.nucleo.csv_importacion.errores_csv import escribir_filas_con_error
from proxlaunch.nucleo.csv_importacion.interpretacion import filas_lote, interpretar
from proxlaunch.nucleo.csv_importacion.lectura import leer_archivo_csv
from proxlaunch.nucleo.csv_importacion.plantilla import escribir_plantilla
from proxlaunch.nucleo.errores import ErrorProxLaunch
from proxlaunch.nucleo.lote.filas import definicion_por_filas
from proxlaunch.nucleo.lotes_guardados.formato import guardar_lote, leer_archivo_lote
from proxlaunch.nucleo.lotes_guardados.modelos import LoteGuardado
from proxlaunch.nucleo.perfiles_maquina.almacen import AlmacenPerfilesMaquina, EntradaImportacion
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.formato import (
    exportar_perfiles,
    leer_archivo_perfiles,
    leer_perfiles,
)
from proxlaunch.nucleo.perfiles_maquina.modelos import ConfigPerfil, DiscoPerfil, RedPerfil
from proxlaunch.nucleo.registro import configurar_registro, registrar_secreto

from .apoyo_lote import crear_banco, volcar
from .apoyo_mvp3 import (
    CENT_HOST,
    CENT_IP,
    CENT_PASSWORD,
    CENT_PERFIL_CONEXION,
    CENT_TICKET,
    CENT_TOKEN,
    CENT_USUARIO,
    CENTINELAS_SECRETOS,
    archivo_lote,
    archivo_perfiles,
    cfg_hw,
    config_lote_json,
    fila,
    lote_homogeneo_json,
    perfil_base,
    perfil_json,
    sin_centinelas,
)


@pytest.fixture
def entorno_con_sesion(tmp_path):
    """Registro real con filtro de secretos y una sesión simulada que conoce los centinelas."""
    carpeta_log = tmp_path / "log"
    logger = configurar_registro(carpeta_log, nivel=logging.DEBUG)
    for secreto in CENTINELAS_SECRETOS:
        registrar_secreto(secreto)
    banco = crear_banco(("pve1",))
    assert banco.sesion is not None  # hay una sesión viva mientras se hacen las operaciones
    yield tmp_path, carpeta_log
    for h in list(logger.handlers):
        h.flush()


def _todo_lo_escrito(carpeta) -> list[tuple[str, bytes]]:
    return [
        (str(p.relative_to(carpeta)), p.read_bytes())
        for p in sorted(carpeta.rglob("*"))
        if p.is_file()
    ]


def _contenido_con_credenciales() -> dict:
    """Archivo de terceros cuyas claves de credencial traen los centinelas en clave y valor."""
    perfil = perfil_json("Con claves")
    perfil["token"] = CENT_TOKEN
    perfil["config"]["password"] = CENT_PASSWORD
    perfil["config"]["discos"][0]["ticket"] = CENT_TICKET
    perfil[CENT_PASSWORD.replace("-", "_")] = "x"  # una clave que ES el centinela
    return perfil


def test_flujo_completo_de_perfiles_lotes_y_csv_no_deja_centinelas_en_archivos_logs_ni_mensajes(
    entorno_con_sesion,
):
    tmp, carpeta_log = entorno_con_sesion
    mensajes: list[str] = []
    datos = tmp / "datos"
    datos.mkdir()

    # --- Perfiles: importar un archivo hostil, guardar en el almacén, exportar ---
    ajeno = datos / "ajeno.proxlaunch-perfiles.json"
    peligroso = perfil_json("Intento de token")
    peligroso["descripcion"] = f"usa PVEAPIToken={CENT_USUARIO}!t={CENT_TOKEN}"
    peligroso2 = perfil_json(f"{CENT_USUARIO}!x={CENT_TICKET}")
    ajeno.write_bytes(
        archivo_perfiles([_contenido_con_credenciales(), peligroso], csrf=CENT_PASSWORD)
    )
    archivo = leer_archivo_perfiles(ajeno)
    mensajes.append(volcar(archivo))
    assert (
        len(archivo.validos) == 1 and len(archivo.invalidos) == 1
    )  # el que trae un token se rechaza
    almacen = AlmacenPerfilesMaquina(
        tmp / "config" / "perfiles_maquina.json", fabrica=perfiles_fabrica()
    )
    almacen.cargar()
    almacen.importar([EntradaImportacion(v) for v in archivo.validos])
    almacen.crear(
        "Mío",
        "descripción normal",
        ConfigPerfil(
            discos=(DiscoPerfil(8, storage_preferido="local"),),
            redes=(RedPerfil(bridge_preferido="vmbr0"),),
        ),
    )
    for nombre, descripcion in (
        (peligroso["nombre"], peligroso["descripcion"]),
        (peligroso2["nombre"], ""),
    ):
        with pytest.raises(ErrorProxLaunch) as exc:
            almacen.crear(nombre, descripcion, ConfigPerfil(discos=(DiscoPerfil(8),)))
        mensajes.append(volcar(exc.value))
    (tmp / "salida").mkdir()
    exportar_perfiles(tmp / "salida" / "p.json", almacen.todos(), con_pistas=True, app_version="1")

    # --- Lotes: guardar uno bueno, abrir uno hostil ---
    guardar_lote(
        tmp / "salida" / "lote.proxlaunch-lote.json",
        LoteGuardado("Aula", definicion_por_filas([fila("a-01")], plantilla_base=cfg_hw())),
        app_version="1",
    )
    hostil = lote_homogeneo_json(
        config=config_lote_json(token=CENT_TOKEN, password=CENT_PASSWORD),
        host=CENT_HOST,
        usuario=CENT_USUARIO,
    )
    ruta_lote = datos / "hostil.json"
    ruta_lote.write_bytes(
        archivo_lote(hostil, perfil_conexion=CENT_PERFIL_CONEXION, ticket=CENT_TICKET)
    )
    abierto = leer_archivo_lote(ruta_lote)
    mensajes.append(volcar(abierto))
    guardar_lote(tmp / "salida" / "reguardado.proxlaunch-lote.json", abierto.lote, app_version="1")
    ruta_lote.write_bytes(archivo_lote(nombre=f"{CENT_USUARIO}!t={CENT_TOKEN}"))
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_lote(ruta_lote)
    mensajes.append(volcar(exc.value))

    # --- CSV: columnas de credenciales, plantilla y CSV de errores ---
    csv = datos / "lista.csv"
    csv.write_text(
        f"nombre;cpu;token;Password;api_key;ticket;CSRF\r\nok-01;2;{CENT_TOKEN};{CENT_PASSWORD};{CENT_TICKET};{CENT_TICKET};{CENT_PASSWORD}\r\n"  # noqa: E501
        f"mal nombre;0;{CENT_TOKEN};{CENT_PASSWORD};x;y;z\r\n",
        encoding="utf-8-sig",
    )
    tabla = leer_archivo_csv(csv)
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    mensajes.append(volcar(resultado))
    assert len(filas_lote(resultado, resultado.numeros_validos)) == 1
    escribir_filas_con_error(
        tmp / "salida" / "errores.csv", tabla, resultado, lambda p: f"{p.regla} {p.valor}"
    )
    escribir_plantilla(tmp / "salida" / "plantilla.csv")

    # --- Verificación global ---
    escritos = [
        (r, c) for r, c in _todo_lo_escrito(tmp) if not r.startswith(("datos/", "log/"))
    ]  # `datos/` = entradas hostiles
    assert {r for r, _ in escritos} >= {
        "config/perfiles_maquina.json",
        "salida/p.json",
        "salida/lote.proxlaunch-lote.json",
        "salida/reguardado.proxlaunch-lote.json",
        "salida/errores.csv",
        "salida/plantilla.csv",
    }
    for ruta, contenido in escritos:
        assert sin_centinelas(contenido), ruta
    for texto in mensajes:
        assert sin_centinelas(texto), texto[:200]
    for h in logging.getLogger("proxlaunch").handlers:
        h.flush()
    log = (
        (carpeta_log / "proxlaunch.log").read_bytes()
        if (carpeta_log / "proxlaunch.log").exists()
        else b""
    )
    assert log, "se esperaba actividad en el registro (nombre de archivo, tamaños y códigos)"
    assert sin_centinelas(log)
    assert b"ajeno.proxlaunch-perfiles.json" in log  # el nombre sí; nunca la ruta ni el contenido
    assert str(tmp).encode() not in log


def test_los_archivos_que_escribe_la_aplicacion_no_contienen_host_ip_usuario_ni_perfil_de_conexion(
    tmp_path,
):
    """CA-X04.5: se busca el host y el usuario de la sesión simulada en todos los archivos escritos."""  # noqa: E501
    banco = crear_banco(("pve1",))
    banco.sesion  # noqa: B018 - la sesión existe mientras se guarda
    almacen = AlmacenPerfilesMaquina(tmp_path / "p.json", fabrica=perfiles_fabrica())
    almacen.cargar()
    almacen.crear(
        "Normal", "Para pruebas", ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    )
    exportar_perfiles(tmp_path / "e.json", almacen.todos(), con_pistas=False, app_version="1")
    guardar_lote(
        tmp_path / "l.json",
        LoteGuardado(
            "Lote", definicion_por_filas([fila("a-01"), fila("a-02")], plantilla_base=cfg_hw())
        ),
        app_version="1",
    )
    escribir_plantilla(tmp_path / "plantilla.csv")
    for ruta, contenido in _todo_lo_escrito(tmp_path):
        assert sin_centinelas(
            contenido,
            [CENT_HOST, CENT_IP, CENT_USUARIO, CENT_PERFIL_CONEXION, *CENTINELAS_SECRETOS],
        ), ruta
        assert (
            b"/home" not in contenido and str(tmp_path).encode() not in contenido
        )  # sin rutas absolutas


def test_un_perfil_con_un_token_en_el_texto_libre_no_se_guarda_ni_se_registra(tmp_path, caplog):
    """CA-X04.3 / V-M05."""
    almacen = AlmacenPerfilesMaquina(tmp_path / "p.json", fabrica=perfiles_fabrica())
    almacen.cargar()
    with caplog.at_level(logging.DEBUG), pytest.raises(ErrorProxLaunch):
        almacen.crear(
            "Mi perfil",
            f"PVEAPIToken={CENT_USUARIO}!t={CENT_TOKEN}",
            ConfigPerfil(discos=(DiscoPerfil(8),)),
        )
    assert not (tmp_path / "p.json").exists()
    assert sin_centinelas("\n".join(r.getMessage() for r in caplog.records))


def test_las_columnas_de_credenciales_no_aparecen_en_ninguna_estructura_del_resultado(tmp_path):
    csv = tmp_path / "x.csv"
    csv.write_text(
        f"nombre;token;contrasena\r\na-01;{CENT_TOKEN};{CENT_PASSWORD}\r\n", encoding="utf-8"
    )
    tabla = leer_archivo_csv(csv)
    resultado = interpretar(
        tabla,
        perfil_base=perfil_base(),
        perfiles=perfiles_fabrica(),
        inv=None,
        nodo_referencia=None,
    )
    assert resultado.columnas.credenciales == (1, 2)
    assert sin_centinelas(
        volcar(resultado.filas) + volcar(resultado.columnas) + volcar(resultado.avisos)
    )
    assert (
        json.dumps(resultado.columnas.encabezados)
        and "token" not in resultado.columnas.encabezados.values()
    )


def test_un_perfil_invalido_por_llevar_un_token_en_el_nombre_no_devuelve_ese_nombre_para_mostrarlo():  # noqa: E501
    """CA-X04.3 / INV-M2 / CA-P09.2: la lista de revisión identifica al perfil inválido por su
    nombre, pero un nombre que ES un token (V-M05) no debe volver a salir en ningún mensaje."""
    nombre_token = f"{CENT_USUARIO}!x={CENT_TICKET}"
    archivo = leer_perfiles(archivo_perfiles([perfil_json(nombre_token)]))
    assert len(archivo.invalidos) == 1 and archivo.validos == ()
    assert sin_centinelas(volcar(archivo)), volcar(archivo.invalidos)
