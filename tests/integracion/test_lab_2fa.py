"""Segundo factor real (TOTP y claves de recuperación) contra el laboratorio.

Derivadas de RF-04 y A-7 (docs/requisitos/mvp1.md; f1 §3). El TOTP se calcula con
hmac/hashlib (RFC 6238). Los usuarios de prueba y sus entradas TFA se borran al terminar.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

from proxlaunch.nucleo.api.autenticacion import DesafioTFA, TipoTFA
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import CredencialContrasena, MetodoAuth

from . import apoyo_lab as lab

pytestmark = pytest.mark.integracion


@dataclass
class UsuarioTfa:
    nombre: str
    contrasena: str = field(repr=False)
    totp: str = field(repr=False)
    recuperacion: list[str] = field(repr=False)


def _crear_usuario_tfa(nombre: str, *, con_totp: bool, con_recuperacion: bool) -> UsuarioTfa:
    userid = f"{nombre}@pve"
    lab.borrar_usuario(userid)
    contrasena = lab.nuevo_secreto()
    lab.ssh(f"sudo pveum user add {userid} --password '{contrasena}'")
    secreto = lab.nuevo_secreto_totp()
    if con_totp:
        lab.configurar_totp(userid, secreto)
    claves = lab.configurar_recuperacion(userid) if con_recuperacion else []
    return UsuarioTfa(nombre, contrasena, secreto, claves)


@pytest.fixture
def usuario_totp() -> Iterator[UsuarioTfa]:
    u = _crear_usuario_tfa("tfatotp", con_totp=True, con_recuperacion=False)
    yield u
    lab.borrar_usuario("tfatotp@pve")


@pytest.fixture
def usuario_totp_y_recuperacion() -> Iterator[UsuarioTfa]:
    u = _crear_usuario_tfa("tfarec", con_totp=True, con_recuperacion=True)
    yield u
    lab.borrar_usuario("tfarec@pve")


@pytest.fixture
def usuario_solo_recuperacion() -> Iterator[UsuarioTfa]:
    u = _crear_usuario_tfa("tfasolorec", con_totp=False, con_recuperacion=True)
    yield u
    lab.borrar_usuario("tfasolorec@pve")


def _paso1(entorno, u: UsuarioTfa) -> DesafioTFA:
    p = lab.perfil(MetodoAuth.CONTRASENA, u.nombre)
    lab.confiar_en_laboratorio(entorno, p)
    r = entorno.servicio.conectar(p, CredencialContrasena(u.nombre, "pve", u.contrasena))
    assert isinstance(r, DesafioTFA), "se esperaba el desafío de segundo factor (NeedTFA)"
    return r


def test_paso1_con_totp_devuelve_desafio_totp(entorno, usuario_totp):
    d = _paso1(entorno, usuario_totp)
    assert d.totp is True
    assert d.recuperacion is False
    assert d.no_soportados == ()
    assert d.soportado
    assert d.usuario == "tfatotp@pve"
    assert d.ticket_parcial.split(":")[1].startswith("!tfa!")
    entorno.servicio.cancelar_tfa(d)


def test_paso2_con_totp_correcto_abre_sesion(entorno, usuario_totp):
    d = _paso1(entorno, usuario_totp)
    s = entorno.servicio.completar_tfa(d, lab.totp(usuario_totp.totp), TipoTFA.TOTP)
    try:
        assert s.usuario_efectivo == "tfatotp@pve"
        assert (s.version.mayor, s.version.menor) == (9, 2)
        assert s.cliente.proximo_vmid() >= 100  # el ticket completo funciona
    finally:
        entorno.servicio.cerrar_sesion(s)


def test_totp_con_espacios_se_normaliza(entorno, usuario_totp):
    d = _paso1(entorno, usuario_totp)
    codigo = lab.totp(usuario_totp.totp)
    s = entorno.servicio.completar_tfa(d, f"{codigo[:3]} {codigo[3:]}", TipoTFA.TOTP)
    assert s.usuario_efectivo == "tfatotp@pve"
    entorno.servicio.cerrar_sesion(s)


def test_totp_incorrecto_da_codigo_incorrecto_y_se_puede_reintentar(entorno, usuario_totp):
    d = _paso1(entorno, usuario_totp)
    correcto = lab.totp(usuario_totp.totp)
    incorrecto = f"{(int(correcto) + 1) % 1_000_000:06d}"
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(d, incorrecto, TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.TFA_CODIGO_INCORRECTO
    # Con el mismo desafío (ticket parcial) se puede reintentar con el código correcto.
    s = entorno.servicio.completar_tfa(d, correcto, TipoTFA.TOTP)
    assert s.usuario_efectivo == "tfatotp@pve"
    entorno.servicio.cerrar_sesion(s)


def test_desafio_cancelado_no_permite_completar(entorno, usuario_totp):
    d = _paso1(entorno, usuario_totp)
    entorno.servicio.cancelar_tfa(d)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(d, lab.totp(usuario_totp.totp), TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.SESION_EXPIRADA


def test_tipo_no_ofrecido_se_rechaza_sin_llamar_al_servidor(entorno, usuario_totp):
    d = _paso1(entorno, usuario_totp)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(d, "abcd-efgh-ijkl", TipoTFA.RECUPERACION)
    assert e.value.codigo == CodigoError.TFA_NO_SOPORTADO
    entorno.servicio.cancelar_tfa(d)


def test_totp_repetido_en_el_mismo_periodo_es_rechazado_por_proxmox(entorno, usuario_totp):
    # Comportamiento real de PVE: un código TOTP ya usado no se acepta de nuevo.
    codigo = lab.totp(usuario_totp.totp)
    d1 = _paso1(entorno, usuario_totp)
    s = entorno.servicio.completar_tfa(d1, codigo, TipoTFA.TOTP)
    entorno.servicio.cerrar_sesion(s)
    d2 = _paso1(entorno, usuario_totp)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(d2, codigo, TipoTFA.TOTP)
    assert e.value.codigo == CodigoError.TFA_CODIGO_INCORRECTO


def test_paso1_con_totp_y_recuperacion_ofrece_ambos(entorno, usuario_totp_y_recuperacion):
    d = _paso1(entorno, usuario_totp_y_recuperacion)
    assert d.totp is True
    assert d.recuperacion is True
    entorno.servicio.cancelar_tfa(d)


def test_clave_de_recuperacion_abre_sesion_y_se_consume(entorno, usuario_totp_y_recuperacion):
    u = usuario_totp_y_recuperacion
    assert len(u.recuperacion) >= 1
    clave = u.recuperacion[0]
    d = _paso1(entorno, u)
    s = entorno.servicio.completar_tfa(d, clave, TipoTFA.RECUPERACION)
    assert s.usuario_efectivo == "tfarec@pve"
    entorno.servicio.cerrar_sesion(s)
    # Una clave de recuperación vale una sola vez.
    d2 = _paso1(entorno, u)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(d2, clave, TipoTFA.RECUPERACION)
    assert e.value.codigo == CodigoError.TFA_CODIGO_INCORRECTO
    # Otra clave distinta sí sirve con el mismo desafío.
    s2 = entorno.servicio.completar_tfa(d2, u.recuperacion[1], TipoTFA.RECUPERACION)
    assert s2.usuario_efectivo == "tfarec@pve"
    entorno.servicio.cerrar_sesion(s2)


def test_clave_de_recuperacion_en_mayusculas_y_con_espacios_se_normaliza(
    entorno, usuario_solo_recuperacion
):
    u = usuario_solo_recuperacion
    d = _paso1(entorno, u)
    assert d.totp is False
    assert d.recuperacion is True
    s = entorno.servicio.completar_tfa(d, f"  {u.recuperacion[0].upper()} ", TipoTFA.RECUPERACION)
    assert s.usuario_efectivo == "tfasolorec@pve"
    entorno.servicio.cerrar_sesion(s)


def test_clave_de_recuperacion_incorrecta(entorno, usuario_solo_recuperacion):
    d = _paso1(entorno, usuario_solo_recuperacion)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.completar_tfa(d, "aaaa-bbbb-cccc", TipoTFA.RECUPERACION)
    assert e.value.codigo == CodigoError.TFA_CODIGO_INCORRECTO
    entorno.servicio.cancelar_tfa(d)


def test_contrasena_incorrecta_con_2fa_activo_no_ofrece_desafio(entorno, usuario_totp):
    p = lab.perfil(MetodoAuth.CONTRASENA, "tfatotp")
    lab.confiar_en_laboratorio(entorno, p)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialContrasena("tfatotp", "pve", "mala-contrasena"))
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS


def test_el_calculo_totp_propio_coincide_con_el_vector_rfc6238():
    # Vector del RFC 6238 (SHA-1, secreto "12345678901234567890", T=59 s -> 94287082; 6 dígitos).
    import base64

    secreto = base64.b32encode(b"12345678901234567890").decode()
    assert lab.totp(secreto, instante=59) == "287082"
    assert lab.totp(secreto, instante=1111111109) == "081804"
    assert lab.totp(secreto, instante=time.time()) == lab.totp(secreto)
