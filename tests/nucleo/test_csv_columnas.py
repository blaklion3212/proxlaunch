"""Columnas, encabezados y alias del CSV (RF-C03; CA-C03.1..C03.5, CA-C03.9, CA-X04.2;
RNF-M04: alias del idioma activo).

Los encabezados no distinguen mayúsculas, acentos ni espacios (espacio y guion = guion bajo).
Las columnas con aspecto de credencial se descartan sin leer sus celdas; las desconocidas se
avisan UNA vez.
"""

import pytest

from proxlaunch.nucleo.archivos.esquema import CodigoAvisoArchivo
from proxlaunch.nucleo.csv_importacion.columnas import (
    COLUMNAS,
    normalizar_encabezado,
    resolver_columnas,
)
from proxlaunch.nucleo.csv_importacion.plantilla import ENCABEZADO_PLANTILLA
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

# Tabla de RF-C03: columna → alias aceptados.
ALIAS = {
    "nombre": ["name", "hostname"],
    "perfil": ["profile"],
    "vmid": ["id"],
    "nodo": ["node"],
    "cpu": ["cores", "nucleos"],
    "sockets": ["zocalos"],
    "memoria": ["ram", "memoria_gib", "memoria_mib"],
    "disco": ["disco1", "disco_gib", "tamano_disco"],
    "almacenamiento": ["storage", "almacenamiento1"],
    "red": ["bridge", "red1"],
    "vlan": ["vlan1"],
    "modelo_red": ["tarjeta_red"],
    "firmware": ["bios"],
    "tipo_cpu": ["cpu_tipo"],
    # MVP 4, RF-O28 (enmienda 14.7): columnas de origen.
    "origen": ["source"],
    "fuente": ["origen_archivo", "iso", "plantilla", "imagen"],
    "so": ["sistema"],
    "virtio": ["drivers"],
    "modo_clon": ["clon"],
    # Fase A (RF-A7.3)
    "encender": ["start"],
    "arranque_auto": ["onboot"],
    "notas": ["notes"],
    "etiquetas": ["tags"],
    "pool": [],
    "proteger": ["protection"],
    "mtu": [],
    "limite_red": ["rate"],
    # Fase B (RF-B6.3)
    "ci_usuario": ["ciuser", "ci_user"],
    "ci_claves": ["sshkeys", "ssh_keys", "claves_ssh"],
    "ci_contrasena": ["cipassword", "ci_password"],
    "ci_ip": ["ipconfig0"],
    "ci_puerta": ["puerta_enlace"],
    "ci_dns": ["nameserver"],
    "ci_dominio": ["searchdomain", "dominio_busqueda"],
    "ci_actualizar": ["ciupgrade"],
    "ci_snippet_usuario": ["cicustom_user", "snippet_user"],
    "ci_snippet_vendor": ["cicustom_vendor", "snippet_vendor"],
    "ci_snippet_red": ["cicustom_network", "snippet_network"],
    "ci_snippet_meta": ["cicustom_meta", "snippet_meta"],
    "esperar_ip": ["wait_ip", "wait_for_ip"],
    # fase C (RF-C6.3)
    "reescribir_red": ["rewrite_net", "red_clon"],
    "cortafuegos": ["firewall"],
    "grupo_seguridad": ["security_group", "firewall_group"],
    "politica_entrada": ["policy_in"],
    "politica_salida": ["policy_out"],
    # fase D (RF-D6.3)
    "mapeo_pci": ["pci_mapping"],
    "mapeo_usb": ["usb_mapping"],
    **{f"disco{n}": [] for n in range(2, 9)},
    **{f"almacenamiento{n}": [f"storage{n}"] for n in range(2, 9)},
}


def _error(encabezado) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        resolver_columnas(encabezado)
    assert exc.value.codigo == CodigoError.CSV_COLUMNAS
    return exc.value


def test_la_tabla_de_columnas_es_la_de_los_requisitos():
    canonicas = {c.canonica for c in COLUMNAS}
    assert canonicas == set(ALIAS)
    for c in COLUMNAS:
        assert set(c.alias) == set(ALIAS[c.canonica]), c.canonica
    assert [c.canonica for c in COLUMNAS if c.obligatoria] == ["nombre"]
    assert {c.canonica for c in COLUMNAS if c.avanzada} == {
        "sockets",
        "modelo_red",
        "tipo_cpu",
        "modo_clon",  # RF-O28: «No (avanzado)»
        "mtu",  # fase A (RF-A5.3)
        "limite_red",
        # fase B (RF-B6.3)
        "ci_dns",
        "ci_dominio",
        "ci_actualizar",
        "ci_snippet_usuario",
        "ci_snippet_vendor",
        "ci_snippet_red",
        "ci_snippet_meta",
        # fase C (RF-C6.3)
        "reescribir_red",
        "politica_entrada",
        "politica_salida",
        # fase D (RF-D6.3)
        "mapeo_pci",
        "mapeo_usb",
    }
    assert len(canonicas) == len(COLUMNAS)  # sin duplicados


def test_el_encabezado_de_la_plantilla_usa_nombres_canonicos():
    assert set(ENCABEZADO_PLANTILLA) <= {c.canonica for c in COLUMNAS}
    # MVP 4 (RF-O28, CA-O28.9) y fase A (CA-A7.3.10): la plantilla añade columnas al final.
    assert ENCABEZADO_PLANTILLA == (
        "nombre", "perfil", "cpu", "memoria", "disco", "almacenamiento", "red", "vlan", "nodo", "vmid",  # noqa: E501
        "origen", "fuente", "so", "virtio", "modo_clon",
        "encender", "arranque_auto", "notas", "etiquetas", "pool", "proteger", "mtu", "limite_red",  # noqa: E501
        # Fase B (CA-B6.3.8): cloud-init y espera de IP; sin ``ci_contrasena``.
        "ci_usuario", "ci_claves", "ci_ip", "ci_puerta", "ci_dns", "ci_dominio", "ci_actualizar",  # noqa: E501
        "ci_snippet_usuario", "ci_snippet_vendor", "ci_snippet_red", "ci_snippet_meta", "esperar_ip",  # noqa: E501
        # Fase C (CA-C6.3.7): red del clon y firewall.
        "reescribir_red", "cortafuegos", "grupo_seguridad", "politica_entrada", "politica_salida",  # noqa: E501
        # Fase D (CA-D6.3.7): mapeos PCI/USB del clúster.
        "mapeo_pci", "mapeo_usb",
    )  # fmt: skip
    assert "ci_contrasena" not in ENCABEZADO_PLANTILLA


@pytest.mark.parametrize(
    ("alias", "canonica"), [(a, c) for c, alias in ALIAS.items() for a in [c, *alias]]
)
def test_cada_nombre_y_alias_resuelve_a_su_columna_canonica(alias, canonica):
    mapa, avisos = resolver_columnas([alias] if canonica == "nombre" else ["nombre", alias])
    assert canonica in mapa.posiciones
    assert avisos == ()


@pytest.mark.parametrize(
    ("escrito", "canonica"),
    [
        ("Memoria", "memoria"), ("MEMORIA", "memoria"), ("  memoria  ", "memoria"), ("Núcleos", "cpu"),  # noqa: E501
        ("NÚCLEOS", "cpu"), ("nucleos", "cpu"), ("Zócalos", "sockets"), ("Tamaño disco", "disco"),
        ("tamaño-disco", "disco"), ("Tamaño_Disco", "disco"), ("Memoria GiB", "memoria"),
        ("memoria-mib", "memoria"), ("Tipo CPU", "tipo_cpu"), ("modelo red", "modelo_red"),
        ("Modelo-Red", "modelo_red"), ("Disco 2", "disco2"), ("disco-3", "disco3"), ("DISCO_8", "disco8"),  # noqa: E501
        ("Almacenamiento 2", "almacenamiento2"), ("Storage 4", "almacenamiento4"), ("RED 1", "red"),
        ("Almacenamiento1", "almacenamiento"), ("VLAN 1", "vlan"), ("Perfil", "perfil"), ("ID", "vmid"),  # noqa: E501
        ("﻿nombre", "nombre"), ("Nodo", "nodo"), ("BIOS", "firmware"),
    ],
)  # fmt: skip
def test_los_encabezados_no_distinguen_mayusculas_acentos_espacios_ni_guiones(escrito, canonica):
    """CA-C03 (regla general) y CA-C03.5."""
    mapa, _ = resolver_columnas([escrito] if canonica == "nombre" else ["nombre", escrito])
    assert canonica in mapa.posiciones


def test_las_posiciones_y_los_textos_de_encabezado_para_mensajes():
    mapa, avisos = resolver_columnas(["Nombre", "Núcleos", "Memoria (GiB)x", "RAM"][:2] + ["RAM"])
    assert mapa.posiciones == {"nombre": 0, "cpu": 1, "memoria": 2}
    assert mapa.encabezados == {"nombre": "Nombre", "cpu": "Núcleos", "memoria": "RAM"}
    assert mapa.ignoradas == () and mapa.credenciales == () and avisos == ()


def test_normalizar_encabezado():
    assert normalizar_encabezado("  Tamaño  Disco ") == "tamano_disco"
    assert normalizar_encabezado("A-B C") == "a_b_c"
    assert normalizar_encabezado("﻿Nombre") == "nombre"
    assert normalizar_encabezado("") == ""


# --- Errores E-M10 --------------------------------------------------------------------------------


def test_sin_nombre_es_e_m10_y_lista_las_columnas_reconocidas():
    """CA-C03.1."""
    e = _error(["cpu", "memoria", "xyz"])
    assert e.params["motivo"] == "falta_nombre" and e.params["columna"] == "nombre"
    assert e.params["reconocidas"] == "cpu, memoria"


def test_dos_columnas_que_resuelven_a_la_misma_es_e_m10_con_las_posiciones():
    """CA-C03.2: ``cpu`` y ``cores`` (posiciones en base 1, como en Excel)."""
    e = _error(["nombre", "cpu", "memoria", "cores"])
    assert e.params["motivo"] == "duplicada" and e.params["columna"] == "cpu"
    assert e.params["posiciones"] == "2, 4"


def test_el_mismo_alias_dos_veces_tambien_es_duplicada():
    e = _error(["nombre", "ram", "RAM"])
    assert e.params["motivo"] == "duplicada" and e.params["posiciones"] == "2, 3"


def test_nombre_duplicado():
    assert _error(["nombre", "name"]).params["motivo"] == "duplicada"


def test_un_encabezado_vacio_entre_columnas_es_e_m10_con_la_posicion():
    """CA-C03.4."""
    e = _error(["nombre", "", "cpu"])
    assert e.params["motivo"] == "vacia" and e.params["posiciones"] == "2"
    assert _error(["nombre", "cpu", "  ", "", "memoria"]).params["posiciones"] == "3, 4"


# --- Desconocidas y credenciales (CA-C03.3, CA-X04.2) ---------------------------------------------


def test_una_columna_desconocida_se_ignora_con_un_aviso_una_sola_vez():
    mapa, avisos = resolver_columnas(["nombre", "xyz", "cpu", "otra"])
    assert mapa.ignoradas == (1, 3)
    assert [(a.codigo, a.params) for a in avisos] == [
        (CodigoAvisoArchivo.COLUMNA_NO_USADA, {"columna": "xyz"}),
        (CodigoAvisoArchivo.COLUMNA_NO_USADA, {"columna": "otra"}),
    ]
    assert "xyz" not in mapa.posiciones


def test_el_nombre_de_una_columna_desconocida_se_sanea_y_se_recorta_en_el_aviso():
    largo = "columna-" + "x" * 100
    _, avisos = resolver_columnas(["nombre", largo, "mala\x07‮col"])
    assert len(avisos[0].params["columna"]) <= 40
    assert avisos[1].params["columna"] == "malacol"


@pytest.mark.parametrize(
    "titulo",
    [
        "token",
        "Token",
        "API_TOKEN",
        "password",
        "Contraseña",
        "contrasena",
        "secreto",
        "client_secret",
        "ticket",
        "CSRF",
        "csrf-token",
        "apikey",
        "API key",
        "api_key",
        "credencial",
        "Credenciales",
    ],
)
def test_una_columna_de_credencial_se_descarta_y_el_aviso_es_el_de_credenciales(titulo):
    mapa, avisos = resolver_columnas(["nombre", titulo, "cpu"])
    assert mapa.credenciales == (1,)
    assert 1 not in mapa.posiciones.values()
    assert [(a.codigo, a.params) for a in avisos] == [
        (CodigoAvisoArchivo.CREDENCIAL_IGNORADA, {"n": "1"})
    ]
    assert mapa.ignoradas == ()  # no se avisa además como «no usada»


def test_varias_credenciales_dan_un_solo_aviso_con_el_total():
    _, avisos = resolver_columnas(["nombre", "token", "password", "xyz", "ticket"])
    credenciales = [a for a in avisos if a.codigo == CodigoAvisoArchivo.CREDENCIAL_IGNORADA]
    assert len(credenciales) == 1 and credenciales[0].params == {"n": "3"}
    assert len([a for a in avisos if a.codigo == CodigoAvisoArchivo.COLUMNA_NO_USADA]) == 1


def test_una_credencial_no_cuenta_como_duplicada_ni_como_vacia():
    resolver_columnas(["nombre", "token", "password", "token"])


# --- Alias del idioma activo ----------------------------------------------------------------------


def test_alias_extra_del_idioma_activo_se_aceptan():
    """RNF-M04: la interfaz pasa los encabezados traducidos."""
    mapa, avisos = resolver_columnas(
        ["Name_en", "Cores_es", "RAM Memory"],
        alias_extra={"name_en": "nombre", "cores_es": "cpu", "ram memory": "memoria"},
    )
    assert mapa.posiciones == {"nombre": 0, "cpu": 1, "memoria": 2} and avisos == ()


def test_alias_extra_no_puede_crear_columnas_inexistentes_ni_pisar_a_las_canonicas():
    mapa, avisos = resolver_columnas(
        ["nombre", "cpu", "zzz"], alias_extra={"zzz": "columna_inventada", "cpu": "memoria"}
    )
    assert mapa.posiciones == {"nombre": 0, "cpu": 1}
    assert [a.codigo for a in avisos] == [CodigoAvisoArchivo.COLUMNA_NO_USADA]


def test_alias_extra_con_clave_vacia_se_ignora():
    mapa, _ = resolver_columnas(["nombre"], alias_extra={"": "cpu", "  ": "cpu"})
    assert mapa.posiciones == {"nombre": 0}


def test_el_encabezado_con_bom_y_espacios_resuelve():
    """CA-C03.5."""
    mapa, _ = resolver_columnas(["﻿  nombre  ", "  CPU "])
    assert mapa.posiciones == {"nombre": 0, "cpu": 1}


def test_resolver_columnas_es_puro():
    h = ["nombre", "xyz", "token", "Memoria"]
    assert resolver_columnas(h) == resolver_columnas(list(h))
