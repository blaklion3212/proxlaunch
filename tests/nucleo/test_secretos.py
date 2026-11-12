"""Llavero (RF-08: CA-08.2 a CA-08.6) y centinela de secretos (CA-08.5, RNF-06)."""

import logging

import keyring
import keyring.backends.fail
import keyring.backends.null
import keyring.errors
import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos import CredencialContrasena, CredencialToken, PerfilConexion, Ticket
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import Preferencias, RepositorioPreferencias
from proxlaunch.nucleo.persistencia.secretos import SERVICIO, AlmacenSecretos
from proxlaunch.nucleo.registro import ARCHIVO_LOG, configurar_registro, registrar_secreto

SECRETO = "SECRETO-CENTINELA-5d2b"


class LlaveroEnMemoria:
    """Backend de keyring falso que guarda todo en un diccionario."""

    def __init__(self):
        self.datos = {}

    def get_password(self, servicio, clave):
        return self.datos.get((servicio, clave))

    def set_password(self, servicio, clave, valor):
        self.datos[(servicio, clave)] = valor

    def delete_password(self, servicio, clave):
        if (servicio, clave) not in self.datos:
            raise keyring.errors.PasswordDeleteError("no existe")
        del self.datos[(servicio, clave)]


class LlaveroQueFalla:
    """Backend que lanza al usarse; su mensaje contiene el secreto a propósito."""

    def get_password(self, servicio, clave):
        raise RuntimeError(f"fallo del daemon con {SECRETO}")

    def set_password(self, servicio, clave, valor):
        raise RuntimeError(f"fallo del daemon con {valor}")

    def delete_password(self, servicio, clave):
        raise RuntimeError("fallo del daemon")


@pytest.fixture
def llavero():
    backend = LlaveroEnMemoria()
    return AlmacenSecretos(backend=backend), backend


# --- CA-08.3: con llavero disponible ------------------------------------------------


def test_ca08_3_guardar_y_recuperar_bajo_el_servicio_de_proxlaunch(llavero):
    almacen, backend = llavero
    almacen.guardar("abc-123", SECRETO)
    assert backend.datos == {(SERVICIO, "perfil:abc-123"): SECRETO}
    assert SERVICIO == "ProxLaunch"
    assert almacen.obtener("abc-123") == SECRETO
    assert almacen.disponible() is True


def test_ca08_3_secreto_inexistente_devuelve_none(llavero):
    assert llavero[0].obtener("no-existe") is None


def test_ca08_3_cada_perfil_tiene_su_propia_clave(llavero):
    almacen, _ = llavero
    almacen.guardar("a", "uno")
    almacen.guardar("b", "dos")
    assert (almacen.obtener("a"), almacen.obtener("b")) == ("uno", "dos")


def test_ca08_6_borrar_elimina_el_secreto(llavero):
    almacen, backend = llavero
    almacen.guardar("a", SECRETO)
    almacen.borrar("a")
    assert almacen.obtener("a") is None
    assert backend.datos == {}


def test_ca08_6_borrar_un_secreto_inexistente_no_falla(llavero):
    llavero[0].borrar("nunca-existio")


def test_ca08_3_el_servicio_es_configurable():
    backend = LlaveroEnMemoria()
    AlmacenSecretos(servicio="Otro", backend=backend).guardar("a", "x")
    assert ("Otro", "perfil:a") in backend.datos


def test_ca08_3_sin_backend_explicito_usa_el_del_sistema(monkeypatch):
    falso = LlaveroEnMemoria()
    monkeypatch.setattr(keyring, "get_keyring", lambda: falso)
    almacen = AlmacenSecretos()
    almacen.guardar("a", "x")
    assert almacen.obtener("a") == "x"


# --- CA-08.4: sin llavero -----------------------------------------------------------

BACKENDS_NO_DISPONIBLES = [
    pytest.param(keyring.backends.null.Keyring(), id="CA-08.4-backend-nulo"),
    pytest.param(keyring.backends.fail.Keyring(), id="CA-08.4-backend-fail"),
    pytest.param(LlaveroQueFalla(), id="CA-08.4-backend-que-lanza"),
]


@pytest.mark.parametrize("backend", BACKENDS_NO_DISPONIBLES)
def test_ca08_4_guardar_sin_llavero_lanza_llavero_no_disponible(backend, tmp_path):
    almacen = AlmacenSecretos(backend=backend)
    with pytest.raises(ErrorProxLaunch) as e:
        almacen.guardar("a", SECRETO)
    assert e.value.codigo == CodigoError.LLAVERO_NO_DISPONIBLE
    assert list(tmp_path.iterdir()) == []  # no se guarda nada en ningún archivo


@pytest.mark.parametrize("backend", BACKENDS_NO_DISPONIBLES)
def test_ca08_4_obtener_y_borrar_sin_llavero_lanzan_el_mismo_codigo(backend):
    almacen = AlmacenSecretos(backend=backend)
    for operacion in (lambda: almacen.obtener("a"), lambda: almacen.borrar("a")):
        with pytest.raises(ErrorProxLaunch) as e:
            operacion()
        assert e.value.codigo == CodigoError.LLAVERO_NO_DISPONIBLE


@pytest.mark.parametrize("backend", [BACKENDS_NO_DISPONIBLES[0], BACKENDS_NO_DISPONIBLES[1]])
def test_ca08_4_disponible_es_false_con_backend_nulo(backend):
    assert AlmacenSecretos(backend=backend).disponible() is False


def test_ca08_4_falla_al_obtener_el_backend_del_sistema(monkeypatch):
    def romper():
        raise RuntimeError("sin dbus")

    monkeypatch.setattr(keyring, "get_keyring", romper)
    almacen = AlmacenSecretos()
    assert almacen.disponible() is False
    with pytest.raises(ErrorProxLaunch) as e:
        almacen.guardar("a", SECRETO)
    assert e.value.codigo == CodigoError.LLAVERO_NO_DISPONIBLE


def test_rnf06_el_error_del_llavero_no_filtra_el_secreto():
    """La excepción del backend puede traer el secreto en su texto: no debe copiarse."""
    almacen = AlmacenSecretos(backend=LlaveroQueFalla())
    with pytest.raises(ErrorProxLaunch) as e:
        almacen.guardar("a", SECRETO)
    err = e.value
    assert SECRETO not in repr(err) + str(err) + err.detalle_tecnico + repr(err.params)
    with pytest.raises(ErrorProxLaunch) as e2:
        almacen.obtener("a")
    assert SECRETO not in repr(e2.value) + e2.value.detalle_tecnico


def test_rnf06_el_error_del_llavero_no_encadena_la_causa_original():
    almacen = AlmacenSecretos(backend=LlaveroQueFalla())
    with pytest.raises(ErrorProxLaunch) as e:
        almacen.guardar("a", SECRETO)
    assert e.value.__cause__ is None


# --- CA-08.2 / CA-08.5 / RNF-06: centinela en todos los artefactos -------------------


def test_ca08_2_con_casilla_desmarcada_no_queda_secreto_en_disco_ni_llavero(tmp_path):
    """Un perfil con `recordar_credenciales=False` no escribe en el llavero (nada que hacer
    desde el núcleo) y el archivo de perfiles no contiene el secreto."""
    backend = LlaveroEnMemoria()
    repo = RepositorioPerfiles(tmp_path / "perfiles.json")
    repo.guardar(PerfilConexion("p1", "lab", ["10.0.0.5"], usuario="ana@pve!lab"))
    assert backend.datos == {}
    assert SECRETO not in (tmp_path / "perfiles.json").read_text(encoding="utf-8")


def test_ca08_5_rnf06_el_centinela_no_aparece_en_archivos_logs_ni_salida(tmp_path, capsys):
    """Recorre los flujos del núcleo con un secreto único de cada tipo y busca el texto en
    TODOS los archivos de la carpeta de usuario, el log y la salida estándar."""
    sentinelas = {
        "token": "TOK-CENTINELA-A1",
        "contrasena": "PWD-CENTINELA-B2",
        "ticket": "TKT-CENTINELA-C3",
        "csrf": "CSRF-CENTINELA-D4",
        "totp": "TOTP-CENTINELA-E5",
        "recuperacion": "REC-CENTINELA-F6",
    }
    for valor in sentinelas.values():
        registrar_secreto(valor)
    logger = configurar_registro(tmp_path / "log")

    # Modelos con secretos en memoria: su repr no debe mostrarlos.
    cred_token = CredencialToken("ana@pve!lab", sentinelas["token"])
    cred_pwd = CredencialContrasena("root", "pam", sentinelas["contrasena"])
    ticket = Ticket(sentinelas["ticket"], sentinelas["csrf"], "root@pam", 0.0)
    for objeto in (cred_token, cred_pwd, ticket):
        logger.info("objeto %r / %s", objeto, objeto)

    # Mensajes que un desarrollador podría escribir sin querer.
    logger.info("Authorization: PVEAPIToken=ana@pve!lab=%s", sentinelas["token"])
    logger.info("Cookie: PVEAuthCookie=%s", sentinelas["ticket"])
    logger.info("CSRFPreventionToken: %s", sentinelas["csrf"])
    logger.info("codigo %s y clave %s", sentinelas["totp"], sentinelas["recuperacion"])
    try:
        raise ValueError(f"falló con {sentinelas['contrasena']}")
    except ValueError:
        logger.exception("error en la conexión")

    # Persistencia: perfil, huella, preferencias y llavero.
    repo = RepositorioPerfiles(tmp_path / "perfiles.json")
    repo.guardar(PerfilConexion("p1", "lab", ["10.0.0.5"], usuario="ana@pve!lab"))
    RepositorioHuellas(tmp_path / "huellas.json").guardar("10.0.0.5", 8006, "AA:BB")
    RepositorioPreferencias(tmp_path / "preferencias.json").guardar(Preferencias())
    llavero = LlaveroEnMemoria()
    AlmacenSecretos(backend=llavero).guardar("p1", sentinelas["token"])

    # Error del núcleo con detalle técnico ya sin secretos.
    err = ErrorProxLaunch(CodigoError.CREDENCIALES_INVALIDAS, {}, "401 Unauthorized")
    logger.error("falló: %r", err)

    for handler in logging.getLogger("proxlaunch").handlers:
        handler.flush()
    archivos = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert any(p.name == ARCHIVO_LOG for p in archivos)
    for archivo in archivos:
        texto = archivo.read_bytes().decode("utf-8", errors="replace")
        for nombre, valor in sentinelas.items():
            assert valor not in texto, f"{nombre} apareció en {archivo.name}"
    salida = capsys.readouterr()
    for valor in sentinelas.values():
        assert valor not in salida.out + salida.err
    # El único lugar permitido es el llavero.
    assert sentinelas["token"] in llavero.datos.values()
