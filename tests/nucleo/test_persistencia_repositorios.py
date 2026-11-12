"""Perfiles, huellas y preferencias (RF-05, RF-07, RF-22.3, RF-24, RNF-15, P-12)."""

import json

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos import MetodoAuth, PerfilConexion
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas, clave_huella
from proxlaunch.nucleo.persistencia.perfiles import RepositorioPerfiles
from proxlaunch.nucleo.persistencia.preferencias import (
    Modo,
    Preferencias,
    RepositorioPreferencias,
    Tema,
)
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos

HUELLA_A = ":".join(["AA", "BB", "CC", "DD"] * 8)
HUELLA_B = ":".join(["11", "22", "33", "44"] * 8)


def perfil(id_="p1", nombre="Laboratorio", hosts=("10.0.0.5", "10.0.0.6"), **kw):
    return PerfilConexion(id=id_, nombre=nombre, hosts=list(hosts), **kw)


class LlaveroEnMemoria:
    """Backend de keyring falso con la interfaz mínima."""

    def __init__(self):
        self.datos = {}

    def get_password(self, servicio, clave):
        return self.datos.get((servicio, clave))

    def set_password(self, servicio, clave, valor):
        self.datos[(servicio, clave)] = valor

    def delete_password(self, servicio, clave):
        import keyring.errors

        if (servicio, clave) not in self.datos:
            raise keyring.errors.PasswordDeleteError("no existe")
        del self.datos[(servicio, clave)]


# --- Perfiles -----------------------------------------------------------------------


@pytest.fixture
def perfiles(tmp_path):
    return RepositorioPerfiles(tmp_path / "perfiles.json")


def test_ca07_1_perfil_con_dos_ips_reaparece_en_el_mismo_orden(tmp_path):
    ruta = tmp_path / "perfiles.json"
    RepositorioPerfiles(ruta).guardar(perfil(hosts=("10.0.0.9", "10.0.0.1")))
    reiniciado = RepositorioPerfiles(ruta)  # nueva instancia = reinicio de la app
    [p] = reiniciado.listar()
    assert p.hosts == ["10.0.0.9", "10.0.0.1"]
    assert p == perfil(hosts=("10.0.0.9", "10.0.0.1"))


def test_ca07_1_y_rnf06_el_archivo_de_perfiles_no_contiene_secretos(tmp_path):
    ruta = tmp_path / "perfiles.json"
    repo = RepositorioPerfiles(ruta)
    llavero = AlmacenSecretos(backend=LlaveroEnMemoria())
    llavero.guardar("p1", "SECRETO-CENTINELA-123")
    repo.guardar(perfil(usuario="ana@pve!lab", recordar_credenciales=True))
    texto = ruta.read_text(encoding="utf-8")
    assert "CENTINELA" not in texto
    claves = set(json.loads(texto)["perfiles"][0])
    assert not claves & {"secreto", "password", "contrasena_guardada", "token_secreto", "ticket"}


def test_rf07_un_archivo_con_un_secreto_intruso_no_se_reescribe(tmp_path):
    """Defensa: si alguien añade un campo con secreto al JSON, no se propaga al guardar."""
    ruta = tmp_path / "perfiles.json"
    ruta.write_text(
        json.dumps(
            {"perfiles": [{"id": "p1", "nombre": "x", "hosts": ["h"], "secreto": "INTRUSO-999"}]}
        ),
        encoding="utf-8",
    )
    repo = RepositorioPerfiles(ruta)
    repo.guardar(repo.listar()[0])
    assert "INTRUSO-999" not in ruta.read_text(encoding="utf-8")


def test_perfiles_conservan_todos_los_campos(perfiles):
    original = perfil(
        puerto=9006,
        metodo=MetodoAuth.CONTRASENA,
        usuario="root",
        realm="pve",
        recordar_credenciales=True,
        ignorar_ssl=True,
    )
    perfiles.guardar(original)
    assert perfiles.obtener("p1") == original
    assert perfiles.obtener("p1").metodo is MetodoAuth.CONTRASENA


def test_ca07_7_editar_actualiza_en_su_posicion(perfiles):
    perfiles.guardar(perfil("a", "A"))
    perfiles.guardar(perfil("b", "B"))
    perfiles.guardar(perfil("a", "A editado", hosts=("1.1.1.1",)))
    assert [(p.id, p.nombre) for p in perfiles.listar()] == [("a", "A editado"), ("b", "B")]
    assert perfiles.obtener("a").hosts == ["1.1.1.1"]


def test_ca07_7_duplicar_crea_id_nuevo_con_el_nombre_dado(perfiles):
    perfiles.guardar(perfil("a", "A", usuario="ana@pve!lab"))
    copia = perfiles.duplicar("a", "A (copia)")
    assert copia.id != "a"
    assert copia.nombre == "A (copia)"
    assert copia.hosts == ["10.0.0.5", "10.0.0.6"]
    assert copia.usuario == "ana@pve!lab"
    assert len(perfiles.listar()) == 2


def test_ca07_7_duplicar_no_comparte_la_lista_de_hosts(perfiles):
    perfiles.guardar(perfil("a"))
    copia = perfiles.duplicar("a", "copia")
    copia.hosts.append("9.9.9.9")
    assert perfiles.obtener("a").hosts == ["10.0.0.5", "10.0.0.6"]


def test_ca07_7_duplicar_inexistente_lanza_recurso_inexistente(perfiles):
    with pytest.raises(ErrorProxLaunch) as e:
        perfiles.duplicar("no-existe", "x")
    assert e.value.codigo == CodigoError.RECURSO_INEXISTENTE


def test_ca07_7_eliminar_devuelve_el_perfil_o_none(perfiles):
    perfiles.guardar(perfil("a"))
    assert perfiles.eliminar("a").id == "a"
    assert perfiles.eliminar("a") is None
    assert perfiles.listar() == []


def test_ca07_7_eliminar_borra_secreto_y_huellas_propias(tmp_path):
    repo = RepositorioPerfiles(tmp_path / "perfiles.json")
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    llavero = AlmacenSecretos(backend=LlaveroEnMemoria())
    repo.guardar(perfil("a", hosts=("10.0.0.5", "10.0.0.6")))
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    huellas.guardar("10.0.0.6", 8006, HUELLA_B)
    llavero.guardar("a", "SECRETO-CENTINELA")

    repo.eliminar_con_dependencias("a", llavero, huellas)

    assert repo.obtener("a") is None
    assert llavero.obtener("a") is None
    assert huellas.obtener("10.0.0.5", 8006) is None
    assert huellas.obtener("10.0.0.6", 8006) is None


def test_ca07_7_no_se_borra_la_huella_que_otro_perfil_sigue_usando(tmp_path):
    repo = RepositorioPerfiles(tmp_path / "perfiles.json")
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    repo.guardar(perfil("a", hosts=("10.0.0.5", "10.0.0.6")))
    repo.guardar(perfil("b", hosts=("10.0.0.6",)))
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    huellas.guardar("10.0.0.6", 8006, HUELLA_B)

    repo.eliminar_con_dependencias("a", None, huellas)

    assert huellas.obtener("10.0.0.5", 8006) is None
    assert huellas.obtener("10.0.0.6", 8006) == HUELLA_B


def test_ca07_7_eliminar_sin_llavero_disponible_igual_elimina_el_perfil(tmp_path):
    import keyring.backends.null

    repo = RepositorioPerfiles(tmp_path / "perfiles.json")
    repo.guardar(perfil("a"))
    sin_llavero = AlmacenSecretos(backend=keyring.backends.null.Keyring())
    assert repo.eliminar_con_dependencias("a", sin_llavero, None).id == "a"
    assert repo.listar() == []


def test_ca07_7_eliminar_con_dependencias_de_un_inexistente(perfiles):
    assert perfiles.eliminar_con_dependencias("nada") is None


def test_rnf15_perfiles_corruptos_no_impiden_arrancar(tmp_path):
    ruta = tmp_path / "perfiles.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    repo = RepositorioPerfiles(ruta)
    assert repo.listar() == []
    assert repo.hubo_corrupcion is True
    assert repo.copia_danada is not None
    assert repo.copia_danada.read_text(encoding="utf-8") == "{ esto no es json"
    repo.guardar(perfil("nuevo"))  # se crea uno nuevo
    assert [p.id for p in RepositorioPerfiles(ruta).listar()] == ["nuevo"]


def test_rnf15_una_entrada_invalida_no_arrastra_a_las_demas(tmp_path):
    ruta = tmp_path / "perfiles.json"
    ruta.write_text(
        json.dumps(
            {
                "perfiles": [
                    {"id": "bueno", "nombre": "B", "hosts": ["h"]},
                    {"id": "malo", "nombre": "M", "hosts": ["h"], "metodo": "telepatia"},
                    {"nombre": "sin id"},
                    "basura",
                ]
            }
        ),
        encoding="utf-8",
    )
    assert [p.id for p in RepositorioPerfiles(ruta).listar()] == ["bueno"]


def test_perfiles_sin_archivo_lista_vacia_y_sin_corrupcion(perfiles):
    assert perfiles.listar() == []
    assert perfiles.hubo_corrupcion is False


# --- Huellas ------------------------------------------------------------------------


@pytest.fixture
def huellas(tmp_path):
    return RepositorioHuellas(tmp_path / "huellas.json")


@pytest.mark.parametrize(
    ("host", "puerto", "esperado"),
    [
        ("PVE.Lab", 8006, "pve.lab:8006"),
        ("  10.0.0.5 ", 8006, "10.0.0.5:8006"),
        ("::1", 8006, "[::1]:8006"),
        ("[::1]", 8006, "[::1]:8006"),
    ],
    ids=["S-7-minusculas", "S-7-espacios", "S-7-ipv6", "S-7-ipv6-con-corchetes"],
)
def test_s7_clave_de_huella(host, puerto, esperado):
    assert clave_huella(host, puerto) == esperado


def test_ca05_2_guardar_y_recuperar_por_host_y_puerto(huellas):
    assert huellas.obtener("10.0.0.5", 8006) is None
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    assert huellas.obtener("10.0.0.5", 8006) == HUELLA_A


def test_s7_misma_ip_con_otro_puerto_es_otra_huella(huellas):
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    assert huellas.obtener("10.0.0.5", 8007) is None


def test_s7_el_host_no_distingue_mayusculas(huellas):
    huellas.guardar("PVE.Lab", 8006, HUELLA_A)
    assert huellas.obtener("pve.lab", 8006) == HUELLA_A


def test_ca05_2_las_huellas_persisten_tras_reiniciar(tmp_path):
    ruta = tmp_path / "huellas.json"
    RepositorioHuellas(ruta).guardar("10.0.0.5", 8006, HUELLA_A)
    assert RepositorioHuellas(ruta).obtener("10.0.0.5", 8006) == HUELLA_A


def test_guardar_la_misma_huella_dos_veces_es_inocuo(huellas):
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    assert huellas.obtener("10.0.0.5", 8006) == HUELLA_A


def test_ca05_4_guardar_una_huella_distinta_lanza_huella_cambiada(huellas):
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    with pytest.raises(ErrorProxLaunch) as e:
        huellas.guardar("10.0.0.5", 8006, HUELLA_B)
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA
    assert huellas.obtener("10.0.0.5", 8006) == HUELLA_A  # no se pisa en silencio


def test_p12_reemplazar_es_la_via_explicita_para_cambiarla(huellas):
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    huellas.reemplazar("10.0.0.5", 8006, HUELLA_B)
    assert huellas.obtener("10.0.0.5", 8006) == HUELLA_B


def test_reemplazar_tambien_crea_si_no_existia(huellas):
    huellas.reemplazar("10.0.0.5", 8006, HUELLA_A)
    assert huellas.obtener("10.0.0.5", 8006) == HUELLA_A


def test_eliminar_huella_informa_si_existia(huellas):
    huellas.guardar("10.0.0.5", 8006, HUELLA_A)
    assert huellas.eliminar("10.0.0.5", 8006) is True
    assert huellas.eliminar("10.0.0.5", 8006) is False
    assert huellas.obtener("10.0.0.5", 8006) is None


def test_ca05_3_cancelar_no_guarda_nada(tmp_path):
    """Sin llamar a `guardar` el archivo ni siquiera se crea."""
    repo = RepositorioHuellas(tmp_path / "huellas.json")
    assert repo.obtener("10.0.0.5", 8006) is None
    assert not (tmp_path / "huellas.json").exists()


def test_rnf15_huellas_corruptas_no_impiden_arrancar(tmp_path):
    ruta = tmp_path / "huellas.json"
    ruta.write_text("[]", encoding="utf-8")
    repo = RepositorioHuellas(ruta)
    assert repo.obtener("10.0.0.5", 8006) is None
    assert repo.hubo_corrupcion is True
    repo.guardar("10.0.0.5", 8006, HUELLA_A)
    assert repo.obtener("10.0.0.5", 8006) == HUELLA_A


# --- Preferencias -------------------------------------------------------------------


@pytest.fixture
def prefs(tmp_path):
    return RepositorioPreferencias(tmp_path / "preferencias.json")


def test_ca22_3_y_ca24_1_valores_iniciales(prefs):
    p = prefs.cargar()
    assert p.tema == Tema.AUTOMATICO
    assert p.modo == Modo.BASICO
    assert p.version_forzada is None


@pytest.mark.parametrize("tema", list(Tema), ids=lambda t: f"CA-22.3-{t.value}")
def test_ca22_3_el_tema_elegido_se_conserva_tras_reiniciar(tema, tmp_path):
    ruta = tmp_path / "preferencias.json"
    RepositorioPreferencias(ruta).guardar(Preferencias(tema=tema))
    assert RepositorioPreferencias(ruta).cargar().tema == tema


@pytest.mark.parametrize("modo", list(Modo), ids=lambda m: f"CA-24.4-{m.value}")
def test_ca24_4_el_modo_se_guarda_y_se_restaura(modo, tmp_path):
    ruta = tmp_path / "preferencias.json"
    RepositorioPreferencias(ruta).guardar(Preferencias(modo=modo))
    assert RepositorioPreferencias(ruta).cargar().modo == modo


def test_ca26_2_la_version_forzada_se_conserva(tmp_path):
    ruta = tmp_path / "preferencias.json"
    RepositorioPreferencias(ruta).guardar(Preferencias(version_forzada=(8, 2)))
    assert RepositorioPreferencias(ruta).cargar().version_forzada == (8, 2)


@pytest.mark.parametrize("valor", ["abc", "8", "8.2.1", "8.x", 8.2, "", None, [8, 2]])
def test_version_forzada_invalida_se_ignora(valor, tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"version_forzada": valor}), encoding="utf-8")
    assert RepositorioPreferencias(ruta).cargar().version_forzada is None


def test_valores_invalidos_caen_al_valor_por_defecto(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"tema": "morado", "modo": "experto"}), encoding="utf-8")
    p = RepositorioPreferencias(ruta).cargar()
    assert (p.tema, p.modo) == (Tema.AUTOMATICO, Modo.BASICO)


def test_rnf15_preferencias_corruptas_usan_los_valores_por_defecto(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text("\x00\x01 no json", encoding="utf-8")
    repo = RepositorioPreferencias(ruta)
    assert repo.cargar() == Preferencias()
    assert repo.hubo_corrupcion is True
    assert repo.copia_danada.exists()
