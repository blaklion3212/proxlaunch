"""Conexión real al laboratorio: huella TOFU, token, usuario/contraseña y renovación.

Derivadas de RF-01 a RF-08 (docs/requisitos/mvp1.md). Solo 127.0.0.1:8006.
"""

from __future__ import annotations

import time

import pytest

from proxlaunch.nucleo.api.autenticacion import AutenticadorTicket
from proxlaunch.nucleo.api.transporte import crear_transporte_http
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.conexion import (
    CredencialContrasena,
    CredencialToken,
    MetodoAuth,
    Ticket,
)
from proxlaunch.nucleo.persistencia.huellas import RepositorioHuellas
from proxlaunch.nucleo.persistencia.secretos import AlmacenSecretos
from proxlaunch.nucleo.reloj import RelojSimulado
from proxlaunch.nucleo.servicios.conexion import (
    CodigoAviso,
    EstadoHuella,
    ServicioConexion,
)

from . import apoyo_lab as lab

pytestmark = pytest.mark.integracion

HUELLA_FALSA = ":".join(["AB"] * 32)


# --- Huella TOFU --------------------------------------------------------------------


def test_sonda_devuelve_huella_sha256_y_es_nueva(entorno):
    p = lab.perfil()
    info = entorno.servicio.consultar_huellas(p)
    assert len(info) == 1
    assert info[0].estado == EstadoHuella.NUEVA
    huella = info[0].huella_observada
    assert huella is not None
    partes = huella.split(":")
    assert len(partes) == 32
    assert all(len(x) == 2 and x == x.upper() for x in partes)


def test_la_huella_observada_coincide_con_la_del_certificado_del_servidor(entorno):
    # Verdad independiente: openssl en el propio servidor sobre su certificado.
    esperada = lab.ssh(
        "sudo openssl x509 -in /etc/pve/local/pve-ssl.pem -noout -fingerprint -sha256"
    ).strip()
    esperada = esperada.split("=", 1)[1].upper()
    observada = entorno.servicio.consultar_huellas(lab.perfil())[0].huella_observada
    assert observada == esperada


def test_sin_confiar_la_huella_no_se_conecta(entorno, plc):
    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialToken(plc.token_id, plc.token_secreto))
    assert e.value.codigo == CodigoError.HUELLA_NO_CONFIADA


def test_tras_confiar_la_huella_queda_confirmada(entorno):
    p = lab.perfil()
    observada = lab.confiar_en_laboratorio(entorno, p)
    info = entorno.servicio.consultar_huellas(p)[0]
    assert info.estado == EstadoHuella.CONFIRMADA
    assert info.huella_guardada == observada
    assert entorno.servicio.preparar(p) == EstadoHuella.CONFIRMADA


def test_huella_guardada_distinta_se_detecta_como_cambiada(entorno):
    p = lab.perfil()
    entorno.huellas.guardar(lab.HOST, p.puerto, HUELLA_FALSA)
    info = entorno.servicio.consultar_huellas(p)[0]
    assert info.estado == EstadoHuella.CAMBIADA
    assert entorno.servicio.preparar(p) == EstadoHuella.CAMBIADA


def test_conexion_con_huella_falsa_fijada_da_huella_cambiada_sin_enviar_credenciales(entorno, plc):
    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
    entorno.huellas.guardar(lab.HOST, p.puerto, HUELLA_FALSA)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialToken(plc.token_id, plc.token_secreto))
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA
    assert plc.token_secreto not in repr(e.value) + e.value.detalle_tecnico


def test_conexion_con_contrasena_y_huella_falsa_tambien_da_huella_cambiada(entorno, plc):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc")
    entorno.huellas.guardar(lab.HOST, p.puerto, HUELLA_FALSA)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialContrasena("plc", "pve", plc.contrasena))
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA


def test_guardar_otra_huella_sobre_la_confiada_exige_reemplazo_explicito(entorno):
    p = lab.perfil()
    lab.confiar_en_laboratorio(entorno, p)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.confiar_huella(p, lab.HOST, HUELLA_FALSA)
    assert e.value.codigo == CodigoError.HUELLA_CAMBIADA


def test_puerto_cerrado_da_servidor_no_responde(entorno):
    # 127.0.0.1:1 no escucha: el destino sigue siendo el host local permitido.
    p = lab.perfil()
    p.puerto = 1
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.consultar_huellas(p)
    assert e.value.codigo == CodigoError.SERVIDOR_NO_RESPONDE


# --- Token --------------------------------------------------------------------------


def test_conexion_por_token_reporta_version_92_y_usuario_del_token(entorno, plc):
    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialToken(plc.token_id, plc.token_secreto))
    try:
        assert (s.version.mayor, s.version.menor) == (9, 2)
        assert s.usuario_efectivo == plc.token_id
        assert s.host_activo == lab.HOST
        assert s.avisos == []  # 9.2 es la última versión conocida; el rol está completo
    finally:
        entorno.servicio.cerrar_sesion(s)


def test_token_del_laboratorio_aprovprox_conecta():
    # El token de aprovprox@pve (ya existente, solo lectura de su secreto) funciona.
    import tempfile
    from pathlib import Path

    completo = lab.secreto("token.txt")
    token_id, secreto = completo.rsplit("=", 1)
    with tempfile.TemporaryDirectory() as d:
        entorno = lab.crear_entorno(Path(d))
        p = lab.perfil(MetodoAuth.TOKEN, token_id)
        lab.confiar_en_laboratorio(entorno, p)
        s = entorno.servicio.conectar(p, CredencialToken(token_id, secreto))
        assert s.usuario_efectivo == token_id
        entorno.servicio.cerrar_sesion(s)


def test_token_con_secreto_incorrecto_da_credenciales_invalidas(entorno, plc):
    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
    lab.confiar_en_laboratorio(entorno, p)
    malo = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialToken(plc.token_id, malo))
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS
    assert malo not in e.value.detalle_tecnico


def test_token_inexistente_da_credenciales_invalidas(entorno):
    p = lab.perfil(MetodoAuth.TOKEN, "nadie@pve!x")
    lab.confiar_en_laboratorio(entorno, p)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(
            p, CredencialToken("nadie@pve!x", "00000000-0000-0000-0000-000000000000")
        )
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS


def test_recordar_credenciales_guarda_el_token_en_el_llavero_falso(entorno, plc):
    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id, recordar=True)
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialToken(plc.token_id, plc.token_secreto))
    entorno.servicio.cerrar_sesion(s)
    assert entorno.llavero.datos[("ProxLaunch", f"perfil:{p.id}")] == (
        f"{plc.token_id}={plc.token_secreto}"
    )


# --- Usuario y contraseña (ticket) --------------------------------------------------


def test_conexion_por_contrasena_obtiene_ticket(entorno, plc):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc")
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialContrasena("plc", "pve", plc.contrasena))
    try:
        assert s.usuario_efectivo == "plc@pve"
        assert (s.version.mayor, s.version.menor) == (9, 2)
        assert isinstance(s.cliente._auth, AutenticadorTicket)
        assert s.cliente.nodos()[0].nombre == lab.NODO
    finally:
        entorno.servicio.cerrar_sesion(s)


def test_usuario_con_realm_incluido_no_duplica_el_realm(entorno, plc):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc@pve")
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialContrasena("plc@pve", "pve", plc.contrasena))
    assert s.usuario_efectivo == "plc@pve"
    entorno.servicio.cerrar_sesion(s)


def test_contrasena_incorrecta_da_credenciales_invalidas(entorno, plc):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc")
    lab.confiar_en_laboratorio(entorno, p)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialContrasena("plc", "pve", "incorrecta-1234"))
    assert e.value.codigo == CodigoError.CREDENCIALES_INVALIDAS
    assert "incorrecta-1234" not in e.value.detalle_tecnico


def test_root_pam_conecta_con_la_contrasena_del_laboratorio(entorno):
    p = lab.perfil(MetodoAuth.CONTRASENA, "root", realm="pam")
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(
        p, CredencialContrasena("root", "pam", lab.secreto("root_pam.pass"))
    )
    assert s.usuario_efectivo == "root@pam"
    entorno.servicio.cerrar_sesion(s)


def test_realm_inexistente_da_credenciales_invalidas(entorno):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc", realm="noexiste")
    lab.confiar_en_laboratorio(entorno, p)
    with pytest.raises(ErrorProxLaunch) as e:
        entorno.servicio.conectar(p, CredencialContrasena("plc", "noexiste", "x"))
    assert e.value.codigo in (CodigoError.CREDENCIALES_INVALIDAS, CodigoError.PARAMETRO_INVALIDO)


def test_con_recordar_la_contrasena_se_guarda_solo_si_hay_sesion(entorno, plc):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc", recordar=True)
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialContrasena("plc", "pve", plc.contrasena))
    entorno.servicio.cerrar_sesion(s)
    assert entorno.llavero.datos[("ProxLaunch", f"perfil:{p.id}")] == plc.contrasena


# --- Renovación del ticket ----------------------------------------------------------


def _servicio_con_reloj(tmp_path, reloj):
    llavero = lab.LlaveroFalso()
    huellas = RepositorioHuellas(tmp_path / "huellas.json")
    servicio = ServicioConexion(
        crear_transporte_http, huellas, AlmacenSecretos(backend=llavero), reloj
    )
    return servicio


def test_el_ticket_se_renueva_con_el_servidor_real_cuando_quedan_15_minutos(tmp_path, plc):
    reloj = RelojSimulado(1000.0)
    servicio = _servicio_con_reloj(tmp_path, reloj)
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc")
    info = servicio.consultar_huellas(p)[0]
    servicio.confiar_huella(p, info.host, info.huella_observada)
    s = servicio.conectar(p, CredencialContrasena("plc", "pve", plc.contrasena))
    auth = s.cliente._auth
    antes = auth.ticket
    assert not auth.necesita_renovar()
    # El ticket lleva la hora en segundos: si se renueva en el mismo segundo sale idéntico.
    time.sleep(1.2)

    reloj.avanzar(2 * 3600 - 14 * 60)  # quedan 14 min: toca renovar
    assert auth.necesita_renovar()
    assert s.cliente.nodos()[0].nombre == lab.NODO  # esta llamada renueva antes de ejecutarse

    despues = auth.ticket
    # Se compara sin que pytest imprima los valores (son material de sesión).
    assert (despues.ticket == antes.ticket) is False
    assert (despues.csrf == antes.csrf) is False
    assert despues.emitido_en == reloj.ahora()
    assert despues.usuario == "plc@pve"
    assert not auth.necesita_renovar()
    # El ticket nuevo funciona (también para un POST con CSRF: GET autenticado basta aquí).
    assert s.cliente.proximo_vmid() >= 100
    servicio.cerrar_sesion(s)


def test_ticket_invalido_da_sesion_expirada(entorno, plc):
    p = lab.perfil(MetodoAuth.CONTRASENA, "plc")
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialContrasena("plc", "pve", plc.contrasena))
    s.cliente._auth._ticket = Ticket(
        ticket="PVE:plc@pve:00000000::AAAA", csrf="0:xx", usuario="plc@pve", emitido_en=0.0
    )
    # emitido_en=0 con reloj real sería "viejo": se fuerza a que no intente renovar primero.
    s.cliente._auth._ticket.emitido_en = s.cliente._reloj.ahora()
    with pytest.raises(ErrorProxLaunch) as e:
        s.cliente.nodos()
    assert e.value.codigo == CodigoError.SESION_EXPIRADA
    entorno.servicio.cerrar_sesion(s)


def test_el_aviso_de_version_no_probada_no_aparece_en_92(entorno, plc):
    p = lab.perfil(MetodoAuth.TOKEN, plc.token_id)
    lab.confiar_en_laboratorio(entorno, p)
    s = entorno.servicio.conectar(p, CredencialToken(plc.token_id, plc.token_secreto))
    assert all(a.codigo != CodigoAviso.VERSION_NO_PROBADA for a in s.avisos)
    entorno.servicio.cerrar_sesion(s)
