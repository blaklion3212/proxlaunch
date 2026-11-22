"""Correcciones de la revisión F6 de la fase B (0.7.0): seguridad (M1-M3, B1-B5, I1, I2, I4) y QA
(QA-M1, QA-M2, QA-M5, QA-B1, QA-B3, QA-B4, QA-B5). Una prueba mínima por punto; las pruebas de
los puntos que ya tenían suites propias (B1, B3, QA-B5) están en ellas.

Decisiones: ``docs/arquitectura/fase-b.md`` §17.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from urllib.parse import quote

import pytest
import responses

from proxlaunch.nucleo import registro
from proxlaunch.nucleo.agente.clasificacion import es_error_de_red
from proxlaunch.nucleo.agente.espera import EsperaIp
from proxlaunch.nucleo.agente.modelos import EstadoIp
from proxlaunch.nucleo.agente.seleccion import interpretar_interfaces
from proxlaunch.nucleo.api import cliente as modulo_cliente
from proxlaunch.nucleo.api.autenticacion import AutenticadorToken
from proxlaunch.nucleo.api.cliente import ClienteProxmox
from proxlaunch.nucleo.api.traductor_errores import traducir_http
from proxlaunch.nucleo.api.transporte import TransporteHttp, limitar_respuesta
from proxlaunch.nucleo.cloudinit.claves import leer_archivo_pub
from proxlaunch.nucleo.cloudinit.modelos import (
    INFO_DESCONOCIDA,
    ConfigCloudInit,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.cloudinit.peticion import construir_put_cloudinit
from proxlaunch.nucleo.cloudinit.validacion import validar_cloudinit
from proxlaunch.nucleo.csv_importacion.errores_csv import filas_con_error
from proxlaunch.nucleo.csv_importacion.modelos import FilaCsv
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.lote.modelos import EstadoMV
from proxlaunch.nucleo.lote.motor import ControlLote
from proxlaunch.nucleo.lote.politica_pausa import PoliticaPausa, es_error_global
from proxlaunch.nucleo.modelos.conexion import CredencialToken
from proxlaunch.nucleo.plantilla_imagen import PasoB2, validar_solicitud
from proxlaunch.nucleo.reloj import RelojReal, RelojSimulado
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.transferencias.url import AlgoritmoChecksum, ChecksumTransferencia
from proxlaunch.nucleo.validacion import Severidad

from .apoyo_api import HUELLA_A, TOKEN_ID, TOKEN_SECRETO
from .apoyo_fase_a import banco_a, def_lote, plan_de
from .apoyo_fase_b_agente import (
    caps,
    crear_imagen,
    crear_mundo_b2,
    ejecutar_espera,
    err_no_en_ejecucion,
    mundo_con_mvs,
)
from .apoyo_lote import (
    ControlAutomatico,
    envio_incierto,
    nodo_caido,
    plantilla,
)
from .apoyo_mvp4 import inv_origen
from .test_fase_b_csv import CUERPO_PRIVADO, PRIVADA, clonando, importar, tabla_csv
from .test_fase_b_plantilla_imagen import sol_local, sol_url
from .test_fase_b_validaciones import CAPS_92, INV_TODO, ci_, clon

CLAVE_VALIDA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBkeyP3x ana@pc"


# --- M1: la clave privada de ci_claves no pasa al CSV de errores --------------------------------


def test_m1_el_csv_de_errores_vacia_ci_claves_si_trae_una_clave_privada():
    lineas = clonando("ci_claves", f'a;"{PRIVADA.replace(chr(10), chr(13) + chr(10))}"')
    r = importar(lineas)
    _, filas = filas_con_error(tabla_csv(lineas), r, lambda p: p.regla)
    assert filas, "la fila con la clave privada debe ser una fila con error"
    assert CUERPO_PRIVADO not in repr(filas)


def test_m1_tambien_vacia_ci_claves_si_trae_un_token():
    token = "root@pam!tok=0123456789abcdef-0123456789abcdef"
    lineas = clonando("ci_claves", f"a;{token}")
    r = importar(lineas)
    _, filas = filas_con_error(tabla_csv(lineas), r, lambda p: p.regla)
    assert filas and "0123456789abcdef-0123456789abcdef" not in repr(filas)


# --- M2: registro de secretos -------------------------------------------------------------------


def test_m2a_el_registro_cuenta_referencias():
    valor = "Valor-Compartido-1"
    registro.registrar_secreto(valor)
    registro.registrar_secreto(valor)
    registro.olvidar_secreto(valor)
    assert valor not in registro.enmascarar(valor)  # queda una referencia
    registro.olvidar_secreto(valor)
    assert valor in registro.enmascarar(valor)  # ya sin referencias


def test_m2b_cipassword_entra_en_la_red_por_nombre_de_campo():
    assert "Desconocida-9" not in registro.enmascarar("cipassword=Desconocida-9&x=1")
    assert "Desconocida-9" not in registro.enmascarar('{"cipassword": "Desconocida-9"}')


def test_m2c_se_registran_las_variantes_json_quote_con_barra_y_minusculas():
    valor = 'a"b\\c/d é-1234'
    registro.registrar_secreto(valor)
    variantes = [
        json.dumps(valor)[1:-1],  # JSON escapada
        quote(valor, safe="/"),  # barra sin codificar
        quote(valor, safe="").lower(),  # percent-encoding en minúsculas
    ]
    for v in variantes:
        assert v not in registro.enmascarar(f"eco: {v} fin"), v


def test_qa_m3a_cerrar_sesion_no_borra_los_secretos_de_cloudinit():
    s = Secreto("Contrasena-Plan-1")
    registro.registrar_secreto("token-de-sesion-9f8e7d")
    registro.olvidar_secretos()  # lo que hace cerrar_sesion
    assert "Contrasena-Plan-1" not in registro.enmascarar("eco Contrasena-Plan-1")
    assert "token-de-sesion-9f8e7d" in registro.enmascarar("token-de-sesion-9f8e7d")
    s.olvidar()
    assert "Contrasena-Plan-1" in registro.enmascarar("eco Contrasena-Plan-1")


# --- M3: nombres de interfaz del agente ---------------------------------------------------------


def test_m3_el_nombre_de_interfaz_solo_conserva_la_lista_blanca():
    sucio = "ens‮18<b>x</b>​⁦:0@a-b_c.d é"
    (i,) = interpretar_interfaces(
        {"result": [{"name": sucio, "hardware-address": "aa:bb:cc:dd:ee:ff", "ip-addresses": []}]}
    )
    assert i.nombre == "ens18bxb:0@a-b_c.d"
    assert interpretar_interfaces([{"name": "‮​", "ip-addresses": []}]) == ()


# --- B1: contraseña corta -----------------------------------------------------------------------


def test_b1_el_registro_no_registra_contrasenas_de_menos_de_8_caracteres():
    corta = "abc1234"
    s = Secreto(corta)
    assert corta in registro.enmascarar(f"valor {corta}")
    s.olvidar()  # no debe fallar aunque no se registrara
    larga = Secreto("abcd1234")
    assert "abcd1234" not in registro.enmascarar("abcd1234")
    larga.olvidar()


# --- B2: suma obligatoria sin garantía de transporte --------------------------------------------


def _problemas_suma(sol):
    return [
        (p.severidad, p.params.get("motivo"))
        for p in validar_solicitud(sol, inv_origen(nodos=("pve1",)), caps())
        if p.codigo == "V-B05"
    ]


def test_b2_con_http_la_suma_es_obligatoria():
    sol = sol_url("http://ejemplo.org/imagen.qcow2", "imagen.qcow2")
    assert (Severidad.ERROR, "suma_obligatoria") in _problemas_suma(sol)
    con_suma = dataclasses.replace(
        sol, suma=ChecksumTransferencia(AlgoritmoChecksum.SHA256, "ab" * 32)
    )
    assert _problemas_suma(con_suma) == []


def test_b2_sin_verificar_certificados_la_suma_es_obligatoria_y_md5_o_sha1_avisan():
    sol = dataclasses.replace(sol_url(), verificar_certificados=False)
    assert (Severidad.ERROR, "suma_obligatoria") in _problemas_suma(sol)
    for alg, n in ((AlgoritmoChecksum.MD5, 16), (AlgoritmoChecksum.SHA1, 20)):
        debil = dataclasses.replace(sol, suma=ChecksumTransferencia(alg, "ab" * n))
        assert _problemas_suma(debil) == [(Severidad.AVISO, "suma_debil")]
    # Con certificados verificados y https la suma sigue siendo opcional.
    assert _problemas_suma(sol_url()) == []


# --- B4: tope de la respuesta del agente --------------------------------------------------------


def _transporte():
    t = TransporteHttp(["10.0.0.1"], 8006, huellas={"10.0.0.1": HUELLA_A})
    t.usar_autenticador(AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)))
    return t


@responses.activate
def test_b4_limitar_respuesta_rechaza_el_cuerpo_demasiado_grande_y_sin_tope_todo_sigue_igual():
    url = "https://10.0.0.1:8006/api2/json/nodes/pve1/qemu/100/agent/network-get-interfaces"
    cuerpo = {"data": {"result": ["x" * 5000]}}
    responses.get(url, json=cuerpo)
    t = _transporte()
    with limitar_respuesta(1000), pytest.raises(ErrorProxLaunch) as exc:
        t.peticion("GET", "/nodes/pve1/qemu/100/agent/network-get-interfaces")
    assert exc.value.params.get("motivo") == "respuesta_demasiado_grande"
    with limitar_respuesta(100_000):
        assert (
            t.peticion("GET", "/nodes/pve1/qemu/100/agent/network-get-interfaces") == cuerpo["data"]
        )
    # Fuera del bloque no hay tope.
    assert t.peticion("GET", "/nodes/pve1/qemu/100/agent/network-get-interfaces") == cuerpo["data"]


@responses.activate
def test_b4_interfaces_agente_aplica_el_tope_de_4_mib(monkeypatch):
    assert modulo_cliente.MAX_RESPUESTA_AGENTE == 4 * 1024 * 1024
    monkeypatch.setattr(modulo_cliente, "MAX_RESPUESTA_AGENTE", 2000)
    url = "https://10.0.0.1:8006/api2/json/nodes/pve1/qemu/100/agent/network-get-interfaces"
    responses.get(url, json={"data": {"result": ["x" * 5000]}})
    cliente = ClienteProxmox(
        _transporte(), AutenticadorToken(CredencialToken(TOKEN_ID, TOKEN_SECRETO)), RelojSimulado()
    )
    with pytest.raises(ErrorProxLaunch):
        cliente.interfaces_agente("pve1", 100)


# --- B5: repr de FilaCsv ------------------------------------------------------------------------


def test_b5_el_repr_de_filacsv_no_muestra_las_celdas():
    fila = FilaCsv(2, ("a", "Secreto-Celda-9", PRIVADA))
    assert "Secreto-Celda-9" not in repr(fila) and CUERPO_PRIVADO not in repr(fila)
    assert "2" in repr(fila)


# --- I1: leer_archivo_pub -----------------------------------------------------------------------


def test_i1_leer_archivo_pub_lee_un_archivo_regular(tmp_path):
    ruta = tmp_path / "id.pub"
    ruta.write_text(CLAVE_VALIDA + "\n", encoding="utf-8")
    assert leer_archivo_pub(ruta).startswith("ssh-ed25519")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="solo POSIX")
def test_i1_una_fifo_sin_escritor_no_cuelga_y_se_rechaza_como_ilegible(tmp_path):
    ruta = tmp_path / "tuberia.pub"
    os.mkfifo(ruta)
    resultado: list[object] = []

    def leer() -> None:
        try:
            leer_archivo_pub(ruta)
        except ErrorProxLaunch as e:
            resultado.append(e)

    hilo = threading.Thread(target=leer, daemon=True)
    hilo.start()
    hilo.join(5)
    assert not hilo.is_alive(), "leer_archivo_pub se quedó bloqueada en la FIFO"
    assert resultado and resultado[0].params.get("motivo") == "ilegible"  # type: ignore[attr-defined]


# --- I2: construir_put_cloudinit revalida -------------------------------------------------------


@pytest.mark.parametrize(
    "ci",
    [
        ConfigCloudInit(tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "999.1.1.1/24"),)),
        ConfigCloudInit(
            tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.5/24", puerta="10.9.9.9"),)
        ),
        ConfigCloudInit(dns=("no-es-ip",)),
        ConfigCloudInit(dominio="mal_dominio..x"),
        ConfigCloudInit(usuario="con espacio"),
        ConfigCloudInit(claves=("ssh-ed25519 !!!no-base64!!! x",)),
        ConfigCloudInit(snippets=SnippetsCloudInit(user="no-es-volid")),
    ],
    ids=["ip", "puerta", "dns", "dominio", "usuario", "claves", "snippet"],
)
def test_i2_un_valor_invalido_lanza_parametro_invalido_con_solo_el_campo(ci):
    with pytest.raises(ErrorProxLaunch) as exc:
        construir_put_cloudinit(ci, INFO_DESCONOCIDA)
    assert exc.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert set(exc.value.params) == {"campo"}


def test_i2_un_valor_valido_se_construye_igual_que_antes():
    ci = ConfigCloudInit(
        usuario="ubuntu",
        claves=(CLAVE_VALIDA,),
        tarjetas=(TarjetaCloudInit(0, ModoTarjeta.FIJA, "10.0.0.5/24", puerta="10.0.0.1"),),
        dns=("1.1.1.1",),
        dominio="lab.local",
    )
    put = construir_put_cloudinit(ci, INFO_DESCONOCIDA)
    assert put["ciuser"] == "ubuntu" and put["ipconfig0"] == "ip=10.0.0.5/24,gw=10.0.0.1"


# --- I4: params["recurso"] limpio ---------------------------------------------------------------


def test_i4_el_recurso_del_error_pasa_por_limpiar_detalle():
    secreto = "Secreto-Recurso-12345"
    registro.registrar_secreto(secreto)
    e = traducir_http(
        500, "", f"Configuration file 'nodes/pve1/qemu-server/{secreto}.conf' does not exist"
    )
    e2 = traducir_http(500, f"VM '{secreto}' does not exist", "")
    for err in (e, e2):
        assert secreto not in repr(err.params)


# --- QA-M1: cancelar espera a la petición en vuelo ----------------------------------------------


def test_qa_m1_tras_cancelar_no_sale_ninguna_peticion_de_esa_mv():
    log: list[tuple[str, int, bool]] = []
    cancelar_volvio = threading.Event()
    en_estado = threading.Event()
    seguir = threading.Event()

    class Cliente:
        def config_vm(self, nodo, vmid):
            log.append(("config_vm", vmid, cancelar_volvio.is_set()))
            return {"agent": "1", "net0": "virtio=BC:24:11:AA:BB:01,bridge=vmbr0"}

        def interfaces_agente(self, nodo, vmid):
            log.append(("interfaces_agente", vmid, cancelar_volvio.is_set()))
            return {"result": []}

    class Sesion:
        cliente = Cliente()

    def al_estado(vmid, estado):
        en_estado.set()
        seguir.wait(2)

    resultados = []
    e = EsperaIp(
        Sesion(),  # type: ignore[arg-type]
        RelojReal(),
        lambda v, r: resultados.append((v, r.estado)),
        al_estado=al_estado,
    )
    e.anadir(105, "pve1", 60)
    hilo = threading.Thread(target=e.ejecutar)
    hilo.start()
    assert en_estado.wait(2)
    e.cancelar([105])
    cancelar_volvio.set()
    seguir.set()
    e.sin_mas_objetivos()
    hilo.join(3)
    assert [x for x in log if x[2]] == []  # ninguna petición tras volver cancelar()
    assert resultados == [(105, EstadoIp.CANCELADA)]


def test_qa_m1_cancelar_espera_a_que_termine_la_peticion_en_vuelo():
    dentro = threading.Event()
    liberar = threading.Event()
    orden: list[str] = []

    class Cliente:
        def config_vm(self, nodo, vmid):
            dentro.set()
            liberar.wait(5)
            orden.append("peticion_terminada")
            return {"agent": "1", "net0": "virtio=BC:24:11:AA:BB:01,bridge=vmbr0"}

        def interfaces_agente(self, nodo, vmid):
            return {"result": []}

    class Sesion:
        cliente = Cliente()

    e = EsperaIp(Sesion(), RelojReal(), lambda v, r: None)  # type: ignore[arg-type]
    e.anadir(105, "pve1", 60)
    hilo = threading.Thread(target=e.ejecutar)
    hilo.start()
    assert dentro.wait(2)
    cancelador = threading.Thread(
        target=lambda: (e.cancelar([105]), orden.append("cancelar_volvio"))
    )
    cancelador.start()
    cancelador.join(0.3)
    assert cancelador.is_alive(), "cancelar() volvió con una petición todavía en vuelo"
    liberar.set()
    cancelador.join(3)
    e.sin_mas_objetivos()
    hilo.join(3)
    assert orden == ["peticion_terminada", "cancelar_volvio"]


# --- QA-M2: los 403 de pasos B no cuentan para «repetido» ---------------------------------------


def test_qa_m2_los_errores_de_ajuste_de_cloudinit_o_contrasena_no_cuentan_para_la_racha():
    p = PoliticaPausa()
    for ajuste in ("cloudinit", "contrasena"):
        for _ in range(6):
            e = ErrorProxLaunch(
                CodigoError.PERMISO_INSUFICIENTE,
                {"privilegio": "VM.Config.Network", "ajuste": ajuste, "via": "config"},
            )
            assert p.registrar(e) is None
    # Sin privilegio indicado tampoco es un error global.
    sin = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "", "ajuste": "cloudinit"}
    )
    assert not es_error_global(sin)
    # Un error sin «ajuste» sigue contando.
    otro = ErrorProxLaunch(CodigoError.DESCONOCIDO, {})
    assert [p.registrar(otro) for _ in range(3)][-1] is not None


# --- QA-M5: contraseña olvidada = error de validación -------------------------------------------


def test_qa_m5_una_contrasena_olvidada_da_v_b40_como_error():
    s = Secreto("Contrasena-Olvidada-1")
    cfg = clon(ci_(usuario="u", contrasena=s))
    s.olvidar()
    problemas = [p for p in validar_cloudinit(cfg, INV_TODO, CAPS_92) if p.codigo == "V-B40"]
    assert [(p.severidad, p.campo, p.params) for p in problemas] == [
        (Severidad.ERROR, "cloudinit.contrasena", {"motivo": "olvidada"})
    ]
    # También cuando la contraseña era lo único de cloud-init.
    s2 = Secreto("Contrasena-Olvidada-2")
    solo = clon(ci_(contrasena=s2))
    s2.olvidar()
    assert any(p.codigo == "V-B40" for p in validar_cloudinit(solo, INV_TODO, CAPS_92))


# --- QA-B1: plazo vencido con el último error de red --------------------------------------------


def test_qa_b1_si_el_plazo_vence_con_un_error_de_red_el_resultado_es_error_de_red():
    m = mundo_con_mvs(100)
    caido = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "10.0.0.1"})
    assert es_error_de_red(caido) and not es_error_de_red(err_no_en_ejecucion())
    m.cluster.guion[100] = [err_no_en_ejecucion(), caido]
    espera = m.espera()
    espera.anadir(100, "pve1", 30)
    r = ejecutar_espera(m, espera)[100]
    assert r.estado == EstadoIp.ERROR
    assert r.error is not None and r.error.codigo == CodigoError.SERVIDOR_NO_RESPONDE


def test_qa_b1_un_agente_mudo_sigue_siendo_agente_no_responde():
    m = mundo_con_mvs(100)
    m.cluster.guion[100] = [err_no_en_ejecucion()]
    espera = m.espera()
    espera.anadir(100, "pve1", 30)
    assert ejecutar_espera(m, espera)[100].estado == EstadoIp.AGENTE_NO_RESPONDE


# --- QA-B3: dudosa resuelta con esperar_ip → IP omitida -----------------------------------------


def test_qa_b3_una_dudosa_resuelta_registra_la_ip_como_omitida():
    banco = banco_a()
    banco.cluster.regla("POST", r"/qemu$", lambda llamada: (_ for _ in ()).throw(envio_incierto()))
    bloqueo = banco.cluster.regla("GET", r"qemu/10[01]/config$", nodo_caido("pve1", 596))
    plan = plan_de(
        banco, def_lote(1, plantilla_vm=plantilla(encender=True, esperar_ip=True), vmid_inicial=100)
    )
    assert not plan.bloqueado, plan.problemas
    libro = banco.ejecutar(plan, ControlAutomatico("suspender"))
    assert libro.entrada(100).estado == EstadoMV.CONEXION_PERDIDA
    banco.cluster.reglas.remove(bloqueo)
    banco.cluster.reglas.clear()
    banco.cluster.agregar_vm(100, "pve1", "web-01", tags=f"proxlaunch;lote-{libro.id_lote}")
    banco.motor().comprobar_dudosas(libro, banco.observador, ControlLote(), frozenset({100}))
    e = libro.entrada(100)
    assert e.estado in (EstadoMV.OK, EstadoMV.CON_AVISOS)
    assert e.ip is not None and e.ip.estado == EstadoIp.OMITIDA


# --- QA-B4: máquina anterior sin borrar al cambiar de VMID --------------------------------------


def test_qa_b4_al_cambiar_de_vmid_tras_un_fallo_se_avisa_de_la_maquina_anterior(tmp_path):
    imagen = crear_imagen(tmp_path / "ubuntu-24.04.qcow2", 2 * 1024**3)
    m = crear_mundo_b2()
    m.cluster.exitstatus[9100] = "TASK ERROR: import failed"
    m.cluster.parciales = {9100}  # la MV queda a medias
    sol = sol_local(imagen)
    primero = m.ejecutar(sol)
    assert primero.pasos[PasoB2.CREAR].value == "fallido" and primero.vmid_reservado_aqui
    nombre = primero.nombre_reservado
    del m.cluster.exitstatus[9100]
    otro = dataclasses.replace(sol, cfg=dataclasses.replace(sol.cfg, vmid=sol.cfg.vmid + 1))
    segundo = m.ejecutar(otro)
    assert f"maquina_anterior_sin_borrar:{sol.cfg.vmid}:{nombre}" in segundo.avisos
