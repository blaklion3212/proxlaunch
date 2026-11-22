"""Fase B (0.7.0): claves SSH públicas de cloud-init (RF-B1.4, RF-B1.5, DT-B4).

Cubre CA-B1.4.1 a CA-B1.4.6, CA-B1.5.1, CA-B1.5.2 y CA-B1.5.4 (parte del núcleo), CL-B3, CL-B4,
CL-B5 y las reglas V-B22, V-B23 y V-B24 (las de contenido; su emisión como ``Problema`` está en
``test_fase_b_validaciones.py``). El rechazo de la clave privada en CSV (CA-B1.5.3) está en
``test_fase_b_csv.py``.
"""

from __future__ import annotations

import base64
import random
import struct
from urllib.parse import parse_qs, quote, unquote, urlencode

import pytest

from proxlaunch.nucleo.cloudinit.claves import (
    MAX_BYTES_CLAVES,
    MAX_BYTES_PUB,
    MAX_CLAVES,
    TIPOS_CLAVE,
    MotivoClave,
    analizar_claves,
    codificar_sshkeys,
    contiene_clave_privada,
    leer_archivo_pub,
    resumen_clave,
)
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch

CENTINELA_PRIVADA = "S3cr3t-CuerpoPrivado-ZZZ"
SEMILLA = 20261122


def clave(tipo: str = "ssh-ed25519", comentario: str = "ana@pc", relleno: int = 8) -> str:
    """Clave pública sintética bien formada: ``tipo base64 comentario``."""
    cuerpo = struct.pack(">I", len(tipo)) + tipo.encode() + bytes(relleno)
    texto = f"{tipo} {base64.b64encode(cuerpo).decode()}"
    return f"{texto} {comentario}" if comentario else texto


def privada(tipo: str = "OPENSSH") -> str:
    return (
        f"-----BEGIN {tipo} PRIVATE KEY-----\n{CENTINELA_PRIVADA}\n-----END {tipo} PRIVATE KEY-----"
    )


def motivos(texto: str) -> list[tuple[int, MotivoClave]]:
    return [(p.linea, p.motivo) for p in analizar_claves(texto).problemas]


# --- CA-B1.4.1: codificación de ``sshkeys`` -------------------------------------------------------


def test_ca_b1_4_1_sshkeys_es_quote_de_las_claves_unidas_con_salto_de_linea():
    k1, k2 = clave(comentario="a@b"), clave("ssh-rsa", "c@d")
    assert codificar_sshkeys([k1, k2]) == quote(f"{k1}\n{k2}", safe="")


def test_ca_b1_4_1_el_valor_no_lleva_saltos_ni_espacios_ni_barras_sin_codificar():
    valor = codificar_sshkeys([clave(), clave("ssh-rsa")])
    assert all(c not in valor for c in "\n \t=+/")
    assert "%0A" in valor and "%20" in valor


def test_ca_b1_4_1_una_sola_clave_no_lleva_separador():
    k = clave()
    assert codificar_sshkeys([k]) == quote(k, safe="")
    assert "%0A" not in codificar_sshkeys([k])


def test_ca_b1_4_1_tras_la_codificacion_de_formulario_del_transporte_se_recupera_el_valor():
    """R-B1: el valor ya viaja URL-codificado y el transporte lo codifica otra vez (doble)."""
    claves = [clave(comentario="a@b"), clave("ssh-rsa", "c@d")]
    valor = codificar_sshkeys(claves)
    cuerpo = urlencode({"sshkeys": valor})
    recibido = parse_qs(cuerpo)["sshkeys"][0]
    assert recibido == valor  # el servidor ve el valor codificado una vez (lo que Proxmox espera)
    assert unquote(recibido).split("\n") == claves


# --- CL-B4: UTF-8 en el comentario ----------------------------------------------------------------


def test_cl_b4_comentario_con_acentos_y_emoji_se_acepta_y_la_codificacion_conserva_utf8():
    k = clave(comentario="ñandú 🙂")
    r = analizar_claves(k)
    assert r.problemas == () and r.claves == (k,)
    valor = codificar_sshkeys(r.claves)
    assert "%C3%B1" in valor and "%F0%9F%99%82" in valor
    assert unquote(valor) == k


def test_cl_b4_el_resumen_muestra_el_comentario_saneado_y_nunca_el_cuerpo():
    k = clave(comentario="ñandú\x07\x1b[31m 🙂")
    tipo, comentario = resumen_clave(k)
    assert tipo == "ssh-ed25519"
    assert "\x07" not in comentario and "\x1b" not in comentario
    assert "ñandú" in comentario and "🙂" in comentario
    cuerpo = k.split()[1]
    assert cuerpo not in tipo + comentario


def test_cl_b4_el_comentario_largo_se_recorta_en_el_resumen():
    _, comentario = resumen_clave(clave(comentario="z" * 500))
    assert len(comentario) <= 64


def test_ca_b1_4_resumen_de_clave_sin_comentario():
    assert resumen_clave(clave(comentario="")) == ("ssh-ed25519", "")


# --- CL-B3: normalización del texto pegado -------------------------------------------------------


def test_cl_b3_crlf_espacios_finales_y_lineas_de_comentario_se_normalizan():
    k1, k2 = clave(comentario="uno"), clave("ssh-rsa", "dos")
    texto = f"# mis claves\r\n\r\n  {k1}   \r\n\t\r\n# otra\r\n{k2}\r\n"
    r = analizar_claves(texto)
    assert r.problemas == ()
    assert r.claves == (k1, k2)


def test_cl_b3_cr_suelto_cuenta_como_salto_de_linea():
    k1, k2 = clave(comentario="uno"), clave("ssh-rsa", "dos")
    assert analizar_claves(f"{k1}\r{k2}").claves == (k1, k2)


def test_cl_b3_no_se_altera_el_contenido_de_la_clave_salvo_el_espaciado_interno():
    k = clave()
    cuerpo = k.split()[1]
    r = analizar_claves(f"  ssh-ed25519\t{cuerpo}    ana@pc  ")
    assert r.claves == (k,)


def test_cl_b3_texto_vacio_o_solo_comentarios_da_cero_claves_sin_problemas():
    for texto in ("", "\n\n", "# x\n#y\n", "   \r\n"):
        r = analizar_claves(texto)
        assert (r.claves, r.problemas, r.duplicadas) == ((), (), 0)


# --- CA-B1.4.2: duplicados exactos ---------------------------------------------------------------


def test_ca_b1_4_2_archivos_y_texto_pegado_se_unen_sin_duplicados():
    k1, k2, k3 = clave(comentario="a"), clave("ssh-rsa", "b"), clave("ecdsa-sha2-nistp256", "c")
    archivo1, archivo2, pegado = k1, f"{k2}\n{k1}", f"{k3}\n{k2}"
    r = analizar_claves("\n".join([archivo1, archivo2, pegado]))
    assert r.claves == (k1, k2, k3)  # nº de claves único = 3
    assert r.duplicadas == 2
    assert r.problemas == ()


def test_ca_b1_4_2_la_misma_clave_con_otro_comentario_no_es_duplicado_exacto():
    base = clave(comentario="a")
    otro = base.rsplit(" ", 1)[0] + " b"
    r = analizar_claves(f"{base}\n{otro}")
    assert len(r.claves) == 2 and r.duplicadas == 0


# --- CA-B1.4.3 / CA-B1.4.4 / V-B22: líneas inválidas ---------------------------------------------


@pytest.mark.parametrize(
    ("linea", "motivo"),
    [
        ("ssh-rsa", MotivoClave.SIN_CUERPO),
        ("hola", MotivoClave.TIPO_DESCONOCIDO),
        ("ssh-dss AAAAB3NzaC1kc3M=", MotivoClave.TIPO_DESCONOCIDO),
        ("ssh-ed25519 !!!no-es-base64!!!", MotivoClave.BASE64),
        ("ssh-ed25519 AAAA", MotivoClave.BASE64),  # decodifica a menos de 4 bytes
        ("ssh-ed25519 AAA", MotivoClave.BASE64),  # relleno incorrecto
    ],
)
def test_ca_b1_4_3_linea_no_valida_nombra_el_numero_de_linea_y_no_lleva_la_linea(linea, motivo):
    texto = f"{clave()}\n{linea}"
    r = analizar_claves(texto)
    assert [(p.linea, p.motivo) for p in r.problemas] == [(2, motivo)]
    assert r.claves == (clave(),)  # las demás líneas válidas se conservan
    assert linea not in repr(r.problemas)


def test_ca_b1_4_3_varias_lineas_invalidas_se_numeran_una_a_una_contando_vacias_y_comentarios():
    texto = f"{clave()}\n\n# comentario\nhola\nssh-rsa\n"
    assert motivos(texto) == [
        (4, MotivoClave.TIPO_DESCONOCIDO),
        (5, MotivoClave.SIN_CUERPO),
    ]


def test_ca_b1_4_3_una_linea_con_caracter_de_control_es_invalida():
    r = analizar_claves(f"{clave()}\n" + clave().replace("ana", "a\x07na"))
    assert [p.linea for p in r.problemas] == [2]
    assert r.claves == (clave(),)


@pytest.mark.parametrize(
    "prefijo",
    [
        'command="echo hola" ',
        'from="10.0.0.0/8" ',
        "no-pty,no-agent-forwarding ",
        'environment="A=b c" ',
    ],
)
def test_ca_b1_4_4_una_linea_con_opciones_por_delante_es_con_opciones(prefijo):
    r = analizar_claves(f"{clave()}\n{prefijo}{clave('ssh-rsa')}")
    assert [(p.linea, p.motivo) for p in r.problemas] == [(2, MotivoClave.CON_OPCIONES)]


@pytest.mark.parametrize("tipo", sorted(TIPOS_CLAVE))
def test_rf_b1_4_se_admiten_todos_los_tipos_de_la_lista(tipo):
    r = analizar_claves(clave(tipo))
    assert r.problemas == () and len(r.claves) == 1


def test_rf_b1_4_la_lista_de_tipos_es_la_de_los_requisitos():
    esperados = {
        "ssh-ed25519",
        "ssh-rsa",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "sk-ssh-ed25519@openssh.com",
        "sk-ecdsa-sha2-nistp256@openssh.com",
    }
    assert esperados == TIPOS_CLAVE


def test_rf_b1_4_el_tipo_distingue_mayusculas():
    assert motivos(clave().replace("ssh-ed25519", "SSH-ED25519", 1)) == [
        (1, MotivoClave.TIPO_DESCONOCIDO)
    ]


# --- CA-B1.4.5: archivos .pub --------------------------------------------------------------------


def _error_de(ruta) -> ErrorProxLaunch:
    with pytest.raises(ErrorProxLaunch) as exc:
        leer_archivo_pub(ruta)
    return exc.value


def test_ca_b1_4_5_un_pub_normal_se_lee_como_texto(tmp_path):
    ruta = tmp_path / "id.pub"
    ruta.write_text(clave() + "\n", encoding="utf-8")
    assert leer_archivo_pub(ruta) == clave() + "\n"


def test_ca_b1_4_5_el_limite_es_65536_bytes_inclusive(tmp_path):
    assert MAX_BYTES_PUB == 65536
    justo = tmp_path / "justo.pub"
    justo.write_bytes(b"#" * MAX_BYTES_PUB)
    assert len(leer_archivo_pub(justo)) == MAX_BYTES_PUB
    pasado = tmp_path / "pasado.pub"
    pasado.write_bytes(b"#" * (MAX_BYTES_PUB + 1))
    err = _error_de(pasado)
    assert err.codigo == CodigoError.ARCHIVO_CLAVES_NO_VALIDO
    assert err.params == {"motivo": "tamano"}


@pytest.mark.parametrize("datos", [b"ssh-rsa AAA\x00B", b"\x00", b"\xff\xfe\xfa\xfb"])
def test_ca_b1_4_5_un_archivo_binario_o_no_utf8_se_rechaza(tmp_path, datos):
    ruta = tmp_path / "x.pub"
    ruta.write_bytes(datos)
    err = _error_de(ruta)
    assert err.codigo == CodigoError.ARCHIVO_CLAVES_NO_VALIDO
    assert err.params == {"motivo": "binario"}


def test_ca_b1_4_5_un_archivo_inexistente_o_una_carpeta_es_ilegible(tmp_path):
    for ruta in (tmp_path / "no-existe.pub", tmp_path):
        err = _error_de(ruta)
        assert err.codigo == CodigoError.ARCHIVO_CLAVES_NO_VALIDO
        assert err.params == {"motivo": "ilegible"}


def test_ca_b1_4_5_el_error_nunca_incluye_la_ruta_ni_el_contenido(tmp_path):
    ruta = tmp_path / "secreto-en-el-nombre.pub"
    ruta.write_bytes(b"\x00" + CENTINELA_PRIVADA.encode())
    err = _error_de(ruta)
    texto = f"{err} {err!r} {err.params}"
    assert "secreto-en-el-nombre" not in texto and CENTINELA_PRIVADA not in texto


def test_ca_b1_4_5_el_bom_utf8_se_descarta(tmp_path):
    ruta = tmp_path / "bom.pub"
    ruta.write_bytes(b"\xef\xbb\xbf" + clave().encode())
    assert analizar_claves(leer_archivo_pub(ruta)).claves == (clave(),)


# --- CA-B1.4.6 / V-B24: límites ------------------------------------------------------------------


def test_ca_b1_4_6_veinte_claves_valen_y_veintiuna_no():
    assert MAX_CLAVES == 20
    veinte = "\n".join(clave(comentario=f"c{i}") for i in range(20))
    assert analizar_claves(veinte).problemas == ()
    veintiuna = veinte + "\n" + clave(comentario="c20")
    r = analizar_claves(veintiuna)
    assert [(p.linea, p.motivo) for p in r.problemas] == [(0, MotivoClave.DEMASIADAS)]


def test_ca_b1_4_6_el_limite_de_texto_es_8192_bytes_de_claves_unidas():
    assert MAX_BYTES_CLAVES == 8192
    base = clave(comentario="")
    justo = base + " " + "x" * (MAX_BYTES_CLAVES - len(base) - 1)
    assert len(justo.encode()) == MAX_BYTES_CLAVES
    assert analizar_claves(justo).problemas == ()
    pasado = justo + "x"
    assert motivos(pasado) == [(0, MotivoClave.DEMASIADO_TEXTO)]


def test_ca_b1_4_6_el_limite_cuenta_bytes_utf8_no_caracteres():
    base = clave(comentario="")
    # 2 bytes por «ñ»: la mitad de caracteres ya rebasa los 8192 bytes.
    comentario = "ñ" * ((MAX_BYTES_CLAVES - len(base)) // 2 + 1)
    assert len(base + " " + comentario) < MAX_BYTES_CLAVES
    assert motivos(base + " " + comentario) == [(0, MotivoClave.DEMASIADO_TEXTO)]


def test_ca_b1_4_6_el_texto_de_mas_de_64_kib_se_rechaza_sin_analizar_linea_a_linea():
    r = analizar_claves("# " + "x" * MAX_BYTES_PUB)
    assert r.claves == ()
    assert [(p.linea, p.motivo) for p in r.problemas] == [(0, MotivoClave.DEMASIADO_TEXTO)]


# --- RF-B1.5 / CA-B1.5.1 / CA-B1.5.4 / CL-B5: clave privada --------------------------------------


@pytest.mark.parametrize(
    "marca",
    [
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN ENCRYPTED PRIVATE KEY-----",
        "-----begin openssh private key-----",
        "PuTTY-User-Key-File-2: ssh-rsa",
        "PuTTY-User-Key-File-3: ssh-ed25519",
    ],
)
def test_ca_b1_5_1_las_marcas_de_clave_privada_se_detectan(marca):
    assert contiene_clave_privada(marca)
    assert contiene_clave_privada(f"{clave()}\n{marca}\ncuerpo")


@pytest.mark.parametrize(
    "texto",
    ["-----BEGIN PUBLIC KEY-----", "-----BEGIN CERTIFICATE-----", clave(), "", "private key"],
)
def test_ca_b1_5_1_lo_que_no_es_clave_privada_no_se_marca(texto):
    assert not contiene_clave_privada(texto)


def test_ca_b1_5_1_una_clave_privada_se_rechaza_con_un_solo_problema_de_todo_el_texto():
    r = analizar_claves(privada())
    assert r.claves == ()
    assert [(p.linea, p.motivo) for p in r.problemas] == [(0, MotivoClave.CLAVE_PRIVADA)]


def test_ca_b1_5_1_el_resultado_nunca_conserva_el_cuerpo_de_la_clave_privada():
    r = analizar_claves(privada())
    assert CENTINELA_PRIVADA not in repr(r)
    assert CENTINELA_PRIVADA not in "".join(r.claves)


def test_ca_b1_5_4_una_mezcla_de_publica_y_privada_rechaza_todo():
    r = analizar_claves(f"{clave()}\n{privada('RSA')}\n{clave('ssh-rsa')}")
    assert r.claves == ()
    assert r.duplicadas == 0
    assert [p.motivo for p in r.problemas] == [MotivoClave.CLAVE_PRIVADA]


def test_cl_b5_una_clave_privada_dentro_de_un_pub_de_varias_claves_rechaza_todo():
    contenido_pub = "\n".join(
        [clave(comentario="a"), clave("ssh-rsa", "b"), privada(), clave(comentario="c")]
    )
    r = analizar_claves(contenido_pub)
    assert r.claves == ()
    assert [p.motivo for p in r.problemas] == [MotivoClave.CLAVE_PRIVADA]


def test_ca_b1_5_2_un_archivo_pub_que_es_una_clave_privada_se_rechaza_igual(tmp_path):
    ruta = tmp_path / "id_rsa.pub"
    ruta.write_text(privada("RSA"), encoding="utf-8")
    texto = leer_archivo_pub(ruta)  # el archivo se lee (es texto), pero el análisis lo rechaza
    r = analizar_claves(texto)
    assert r.claves == ()
    assert r.problemas[0].motivo == MotivoClave.CLAVE_PRIVADA


def test_ca_b1_5_1_la_clave_privada_no_se_cuela_por_los_demas_motivos():
    """Aunque el texto además sea enorme, el motivo es la clave privada, no «demasiado texto»."""
    r = analizar_claves(privada() + "\n" + "x" * (MAX_BYTES_PUB + 10))
    assert [p.motivo for p in r.problemas] == [MotivoClave.CLAVE_PRIVADA]


# --- Entradas inválidas y propiedades ------------------------------------------------------------


@pytest.mark.parametrize("valor", [None, 5, b"ssh-rsa AAA", ["ssh-rsa"]])
def test_analizar_claves_con_un_tipo_que_no_es_texto_no_lanza(valor):
    r = analizar_claves(valor)  # type: ignore[arg-type]
    assert r.claves == () and r.problemas


def test_propiedad_lo_que_acepta_analizar_claves_se_reanaliza_igual_y_nunca_trae_privadas():
    rng = random.Random(SEMILLA)
    tipos = sorted(TIPOS_CLAVE)
    piezas = [
        "",
        "# comentario",
        "hola mundo",
        "ssh-rsa",
        "ssh-ed25519 ####",
        "\t",
        "   ",
        "texto-suelto",
    ]
    for _ in range(200):
        lineas = []
        for _ in range(rng.randint(0, 12)):
            if rng.random() < 0.6:
                tipo = rng.choice(tipos)
                lineas.append(
                    clave(tipo, rng.choice(["", "a@b", "ñandú 🙂", "x y z"]), rng.randint(0, 20))
                )
            else:
                lineas.append(rng.choice(piezas))
        texto = rng.choice(["\n", "\r\n"]).join(lineas)
        r = analizar_claves(texto)
        assert not any("PRIVATE KEY" in c for c in r.claves)
        assert len(set(r.claves)) == len(r.claves)  # sin duplicados
        if not r.problemas:
            de_nuevo = analizar_claves("\n".join(r.claves))
            assert de_nuevo.claves == r.claves and de_nuevo.problemas == ()


def test_propiedad_basura_aleatoria_nunca_lanza_y_nunca_devuelve_el_texto_en_los_problemas():
    rng = random.Random(SEMILLA + 1)
    alfabeto = "abc ssh-rsa AAAA+/=\n\r\t#\"'\\\x00\x07ñ🙂-----BEGIN PRIVATE KEY"
    for _ in range(300):
        texto = "".join(rng.choice(alfabeto) for _ in range(rng.randint(0, 200)))
        r = analizar_claves(texto)
        for p in r.problemas:
            assert isinstance(p.linea, int) and p.linea >= 0
            assert isinstance(p.motivo, MotivoClave)
        if contiene_clave_privada(texto):
            assert r.claves == ()


def test_ca_b1_4_5_un_pub_con_saltos_de_windows_se_lee_con_saltos_normalizados(tmp_path):
    ruta = tmp_path / "id_win.pub"
    ruta.write_bytes((clave() + "\r\n").encode("utf-8"))
    assert leer_archivo_pub(ruta) == clave() + "\n"
