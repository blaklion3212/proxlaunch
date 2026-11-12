"""Textos: cada código del núcleo produce un mensaje en español sin marcadores (RF-21, RF-23)."""

import re

import pytest

from proxlaunch.interfaz import textos
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.tarea import Desenlace, Etapa, ResultadoCreacion
from proxlaunch.nucleo.seleccion_nodo import MotivoNodo
from proxlaunch.nucleo.servicios.conexion import Aviso, CodigoAviso, EstadoHuella
from proxlaunch.nucleo.validacion import Problema, Severidad

MARCADOR = re.compile(r"\{[a-z_]+\}")

# Parámetros típicos que entrega el núcleo para cada código.
PARAMS_ERROR = {
    CodigoError.HUELLA_NO_CONFIADA: {"host": "pve1"},
    CodigoError.PERMISO_INSUFICIENTE: {"privilegio": "VM.Allocate", "ruta": "/vms"},
    CodigoError.VMID_OCUPADO: {"vmid": "100", "siguiente": "101"},
    CodigoError.SIN_ESPACIO: {"storage": "local-lvm"},
    CodigoError.ERROR_FORMATO: {"campo": "memory"},
    CodigoError.PARAMETRO_INVALIDO: {"campo": "cores", "mensaje": "fuera de rango"},
    CodigoError.VERSION_NO_SOPORTADA: {"minima": "8.0", "version": "7.4"},
    CodigoError.RECURSO_INEXISTENTE: {"recurso": "vmbr9"},
    CodigoError.NODO_NO_DISPONIBLE: {"nodo": "pve2"},
}


@pytest.mark.parametrize("codigo", list(CodigoError))
def test_cada_codigo_de_error_tiene_texto_sin_marcadores(codigo):
    texto = textos.texto_error(ErrorProxLaunch(codigo, PARAMS_ERROR.get(codigo)))
    assert texto.strip()
    assert not MARCADOR.search(texto)


@pytest.mark.parametrize("codigo", list(CodigoError))
def test_cada_codigo_de_error_sin_parametros_no_deja_llaves_vacias_ni_revienta(codigo):
    texto = textos.texto_error(ErrorProxLaunch(codigo))
    assert texto.strip()


def test_codigo_desconocido_usa_el_mensaje_generico():
    assert textos.texto_error(ErrorProxLaunch(CodigoError.DESCONOCIDO)) == textos.texto_generico()


def test_permiso_insuficiente_nombra_privilegio_y_ruta():
    e = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE, {"privilegio": "VM.Allocate", "ruta": "/vms"}
    )
    texto = textos.texto_error(e)
    assert "VM.Allocate" in texto
    assert "/vms" in texto


def test_vmid_ocupado_sugiere_el_siguiente():
    e = ErrorProxLaunch(CodigoError.VMID_OCUPADO, {"vmid": "100", "siguiente": "101"})
    assert "101" in textos.texto_error(e)


def test_sin_espacio_con_varios_storages_los_lista_todos():
    e = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"storage": "local-lvm,ceph,nfs"})
    texto = textos.texto_error(e)
    for nombre in ("local-lvm", "ceph", "nfs"):
        assert nombre in texto


def test_sin_espacio_por_nodo_indica_gib_requeridos():
    e = ErrorProxLaunch(CodigoError.SIN_ESPACIO, {"requerido_gib": "500"})
    assert "500" in textos.texto_error(e)


def test_servidor_no_responde_con_varias_ips_da_motivo_por_ip():
    e = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE,
        {"hosts": "10.0.0.1,10.0.0.2", "motivos": "10.0.0.1=timeout;10.0.0.2=refused"},
    )
    texto = textos.texto_error(e)
    assert "10.0.0.1" in texto and "10.0.0.2" in texto
    assert "tiempo" in texto
    assert "rechazada" in texto


def test_servidor_no_responde_con_destino_unico():
    e = ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE, {"host": "pve", "puerto": "8006"})
    assert "pve:8006" in textos.texto_error(e)


def test_servidor_no_responde_sin_datos():
    assert textos.texto_error(ErrorProxLaunch(CodigoError.SERVIDOR_NO_RESPONDE))


def test_motivo_de_red_desconocido_tiene_texto():
    e = ErrorProxLaunch(
        CodigoError.SERVIDOR_NO_RESPONDE,
        {"hosts": "a,b", "motivos": "a=algo raro;b=otro"},
    )
    assert "no respondió" in textos.texto_error(e)


def test_recurso_inexistente_de_vm_nombra_vmid_y_nodo():
    e = ErrorProxLaunch(CodigoError.RECURSO_INEXISTENTE, {"recurso": "vm 123", "nodo": "pve1"})
    texto = textos.texto_error(e)
    assert "123" in texto and "pve1" in texto


def test_parametro_invalido_por_regla_pide_corregir_formulario():
    e = ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"regla": "V-01"})
    assert "formulario" in textos.texto_error(e)


def test_parametro_invalido_solo_con_campo():
    e = ErrorProxLaunch(CodigoError.PARAMETRO_INVALIDO, {"campo": "cores"})
    assert "cores" in textos.texto_error(e)


def test_nodo_no_disponible_sin_nombre():
    assert textos.texto_error(ErrorProxLaunch(CodigoError.NODO_NO_DISPONIBLE))


@pytest.mark.parametrize("codigo", list(CodigoAviso))
def test_cada_codigo_de_aviso_tiene_texto_sin_marcadores(codigo):
    params = {
        CodigoAviso.TOPOLOGIA_DEGRADADA: {"nodos": "3"},
        CodigoAviso.PERMISOS_INCOMPLETOS: {"privilegios": "Sys.Audit"},
        CodigoAviso.VERSION_NO_PROBADA: {"version": "9.9"},
    }.get(codigo, {})
    texto = textos.texto_aviso(Aviso(codigo, params))
    assert texto.strip()
    assert not MARCADOR.search(texto)


def test_permisos_incompletos_con_rutas_dice_privilegio_en_ruta():
    aviso = Aviso(
        CodigoAviso.PERMISOS_INCOMPLETOS,
        {"privilegios": "Sys.Audit", "rutas": "Sys.Audit@/"},
    )
    assert "Sys.Audit en /" in textos.texto_aviso(aviso)


def test_permisos_incompletos_con_varias_rutas():
    aviso = Aviso(
        CodigoAviso.PERMISOS_INCOMPLETOS,
        {
            "privilegios": "SDN.Use,Sys.Audit",
            "rutas": "SDN.Use@/sdn/zones/localnetwork,Sys.Audit@/",
        },
    )
    texto = textos.texto_aviso(aviso)
    assert "SDN.Use en /sdn/zones/localnetwork" in texto
    assert "Sys.Audit en /" in texto


def test_permisos_incompletos_sin_rutas_lista_privilegios():
    aviso = Aviso(CodigoAviso.PERMISOS_INCOMPLETOS, {"privilegios": "SDN.Use,Sys.Audit"})
    assert "SDN.Use, Sys.Audit" in textos.texto_aviso(aviso)


def test_permisos_incompletos_ruta_sin_arroba_muestra_solo_privilegio():
    aviso = Aviso(CodigoAviso.PERMISOS_INCOMPLETOS, {"privilegios": "X", "rutas": "Sys.Audit"})
    assert "Sys.Audit" in textos.texto_aviso(aviso)


def test_falta_vm_allocate_es_critico_y_lo_dice():
    aviso = Aviso(CodigoAviso.PERMISOS_INCOMPLETOS, {"privilegios": "VM.Allocate,Sys.Audit"})
    assert textos.privilegio_faltante_critico(aviso)
    assert "no podrás crear" in textos.texto_aviso(aviso)


def test_otros_avisos_no_son_criticos():
    assert not textos.privilegio_faltante_critico(
        Aviso(CodigoAviso.PERMISOS_INCOMPLETOS, {"privilegios": "Sys.Audit"})
    )
    assert not textos.privilegio_faltante_critico(
        Aviso(CodigoAviso.VERSION_NO_PROBADA, {"privilegios": "VM.Allocate"})
    )


def test_version_no_probada_incluye_la_version():
    texto = textos.texto_aviso(Aviso(CodigoAviso.VERSION_NO_PROBADA, {"version": "9.7"}))
    assert "9.7" in texto


def test_aviso_de_topologia_menciona_sys_audit():
    texto = textos.texto_aviso(Aviso(CodigoAviso.TOPOLOGIA_DEGRADADA, {"nodos": "2"}))
    assert "Sys.Audit" in texto


REGLAS = [f"V-{n:02d}" for n in range(1, 22)] + ["V-14.thin", "V-16.sinredes"]


@pytest.mark.parametrize("regla", REGLAS)
def test_cada_regla_v_tiene_texto(regla):
    p = Problema(
        "campo",
        regla,
        Severidad.ERROR,
        {
            "vmid": "100",
            "pedido_gib": "50",
            "libre_gib": "10",
            "storage": "local",
            "maximo": "6",
            "bridge": "vmbr9",
            "nodo": "pve1",
        },
    )
    texto = textos.texto_problema(p)
    assert texto.strip()
    assert not MARCADOR.search(texto)


def test_regla_desconocida_usa_generico():
    p = Problema("x", "V-99", Severidad.ERROR)
    assert textos.texto_problema(p) == textos.texto_generico()


def test_v05_distingue_sockets_de_nucleos():
    s = textos.texto_problema(Problema("sockets", "V-05", Severidad.ERROR))
    n = textos.texto_problema(Problema("cores", "V-05", Severidad.ERROR))
    assert "sockets" in s and "núcleos" in n


def test_v06_distingue_ballooning():
    a = textos.texto_problema(Problema("ballooning_min", "V-06", Severidad.ERROR))
    b = textos.texto_problema(Problema("memoria", "V-06", Severidad.ERROR))
    assert a != b


def test_v07_sin_maximo_y_v16_sin_bridge_y_v17_efi():
    assert textos.texto_problema(Problema("d", "V-07", Severidad.ERROR))
    assert textos.texto_problema(Problema("r", "V-16", Severidad.ERROR))
    assert "UEFI" in textos.texto_problema(Problema("storage_efi", "V-17", Severidad.ERROR))


def _res(desenlace, error=None, upid=None):
    return ResultadoCreacion(desenlace, 123, "pve1", upid, error)


@pytest.mark.parametrize("desenlace", list(Desenlace))
def test_cada_desenlace_tiene_texto(desenlace):
    assert textos.texto_desenlace(_res(desenlace), "mi-vm").strip()


def test_desenlace_ok_nombra_maquina_vmid_y_nodo():
    texto = textos.texto_desenlace(_res(Desenlace.OK), "mi-vm")
    assert "mi-vm" in texto and "123" in texto and "pve1" in texto


def test_desenlace_error_usa_el_error_o_el_generico():
    err = ErrorProxLaunch(CodigoError.CREDENCIALES_INVALIDAS)
    assert textos.texto_desenlace(_res(Desenlace.ERROR, err)) == textos.texto_error(err)
    assert textos.texto_desenlace(_res(Desenlace.ERROR)) == textos.texto_generico()


def test_cancelado_distingue_si_hubo_upid():
    sin = textos.texto_desenlace(_res(Desenlace.CANCELADO))
    con = textos.texto_desenlace(_res(Desenlace.CANCELADO, upid="UPID:x"))
    assert "No se creó nada" in sin
    assert "pudo seguir" in con


@pytest.mark.parametrize("etapa", list(Etapa))
def test_cada_etapa_tiene_texto_distinto_de_su_codigo(etapa):
    assert textos.texto_etapa(etapa) != str(etapa)


@pytest.mark.parametrize("motivo", list(MotivoNodo))
def test_cada_motivo_de_nodo_tiene_texto(motivo):
    assert textos.texto_motivo_nodo(motivo)


@pytest.mark.parametrize("estado", list(EstadoHuella))
def test_cada_estado_de_huella_tiene_texto(estado):
    assert textos.texto_estado_huella(estado)
