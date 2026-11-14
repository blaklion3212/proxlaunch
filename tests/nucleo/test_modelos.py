"""RF-18 (modelo de datos, origen), errores, inventario y tarea."""

import json

import pytest

from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos import (
    Ballooning,
    Bus,
    ConfiguracionVM,
    ControladorScsi,
    CredencialContrasena,
    CredencialToken,
    Desenlace,
    Disco,
    EstadoTarea,
    Etapa,
    Firmware,
    FormatoDisco,
    InterfazRed,
    OrigenSO,
    PerfilConexion,
    Ticket,
)

from .conftest import GIB, storage

# --- RF-18 modelo de la MV ----------------------------------------------------------


def test_ca18_1_el_modelo_contiene_los_campos_requeridos(hacer_cfg):
    """CA-18.1."""
    cfg = hacer_cfg()
    requeridos = {
        "vmid", "nombre", "nodo", "firmware", "sockets", "cores", "tipo_cpu", "memoria_mib",
        "ballooning", "discos", "redes", "origen",
    }  # fmt: skip
    assert requeridos <= set(cfg.a_dict())


def test_ca18_1_origen_admite_los_cuatro_valores_del_mvp4():
    """CA-18.1 ampliado por RF-O01: `OrigenSO` pasa de 1 a 4 valores."""
    assert [o.value for o in OrigenSO] == [
        "disco_vacio",
        "iso",
        "importar_disco",
        "clonar_plantilla",
    ]


def test_valores_por_defecto_del_modelo():
    cfg = ConfiguracionVM(vmid=100, nombre="a", nodo="pve1")
    assert cfg.firmware == Firmware.SEABIOS
    assert cfg.sockets == 1
    assert cfg.cores == 2
    assert cfg.tipo_cpu == "x86-64-v2-AES"
    assert cfg.memoria_mib == 2048
    assert cfg.origen == OrigenSO.DISCO_VACIO
    assert cfg.controlador_scsi == ControladorScsi.VIRTIO_SINGLE
    disco = Disco("s", 8)
    assert (disco.bus, disco.formato) == (Bus.SCSI, FormatoDisco.AUTO)
    assert (disco.discard, disco.ssd, disco.iothread) == (True, True, True)


@pytest.mark.parametrize("origen", ["ova", "", "DISCO_VACIO", None, 1])
def test_ca18_2_origen_distinto_lanza_error_de_validacion(origen):
    """CA-18.2."""
    with pytest.raises(ErrorProxLaunch) as e:
        ConfiguracionVM(vmid=100, nombre="a", nodo="pve1", origen=origen)
    assert e.value.codigo == CodigoError.PARAMETRO_INVALIDO
    assert e.value.params["campo"] == "origen"


def test_ca18_2_desde_dict_con_origen_invalido_lanza_error(hacer_cfg):
    """CA-18.2."""
    datos = hacer_cfg().a_dict()
    datos["origen"] = "ova"  # «iso» ya es un origen válido (RF-O01)
    with pytest.raises(ErrorProxLaunch):
        ConfiguracionVM.desde_dict(datos)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("firmware", "uefi"), ("controlador_scsi", "lsi")],
    ids=["firmware", "controlador"],
)
def test_desde_dict_rechaza_enumeraciones_invalidas(campo, valor, hacer_cfg):
    datos = hacer_cfg().a_dict()
    datos[campo] = valor
    with pytest.raises(ErrorProxLaunch):
        ConfiguracionVM.desde_dict(datos)


def test_ca18_3_origen_explicito_en_el_diccionario(hacer_cfg):
    """CA-18.3."""
    assert hacer_cfg().a_dict()["origen"] == "disco_vacio"


def test_ca18_3_ida_y_vuelta_identica(hacer_cfg):
    """CA-18.3."""
    cfg = hacer_cfg(
        firmware=Firmware.OVMF,
        storage_efi="nfs1",
        sockets=2,
        cores=4,
        memoria_mib=4096,
        ballooning=Ballooning(True, 1024),
        discos=[Disco("nfs1", 10, bus=Bus.VIRTIO, formato=FormatoDisco.QCOW2, ssd=False)],
        redes=[InterfazRed("vmbr1", vlan=120)],
        controlador_scsi=ControladorScsi.VIRTIO_PCI,
    )
    assert ConfiguracionVM.desde_dict(cfg.a_dict()) == cfg


def test_ca18_3_ida_y_vuelta_a_traves_de_json(hacer_cfg):
    cfg = hacer_cfg()
    texto = json.dumps(cfg.a_dict())
    assert ConfiguracionVM.desde_dict(json.loads(texto)) == cfg


def test_ca18_3_ballooning_none_se_conserva(hacer_cfg):
    cfg = hacer_cfg(ballooning=None)
    assert ConfiguracionVM.desde_dict(cfg.a_dict()).ballooning is None


def test_a_dict_no_comparte_listas_con_el_modelo(hacer_cfg):
    cfg = hacer_cfg()
    datos = cfg.a_dict()
    datos["discos"].clear()
    assert len(cfg.discos) == 1


# --- Errores ------------------------------------------------------------------------


def test_error_conserva_codigo_params_y_detalle():
    err = ErrorProxLaunch(
        CodigoError.PERMISO_INSUFICIENTE,
        {"privilegio": "VM.Allocate", "ruta": "/vms/100"},
        "Permission check failed (/vms/100, VM.Allocate)",
    )
    assert err.codigo == CodigoError.PERMISO_INSUFICIENTE
    assert err.params == {"privilegio": "VM.Allocate", "ruta": "/vms/100"}
    assert "VM.Allocate" in err.detalle_tecnico
    assert isinstance(err, Exception)


def test_error_sin_params_tiene_diccionario_vacio_independiente():
    a, b = ErrorProxLaunch(CodigoError.DESCONOCIDO), ErrorProxLaunch(CodigoError.DESCONOCIDO)
    a.params["x"] = "1"
    assert b.params == {}
    assert a.detalle_tecnico == ""


def test_error_copia_los_params_recibidos():
    origen = {"k": "v"}
    err = ErrorProxLaunch(CodigoError.DESCONOCIDO, origen)
    origen["k"] = "otro"
    assert err.params == {"k": "v"}


def test_ca23_4_el_error_del_nucleo_no_trae_texto_para_el_usuario():
    """El mensaje de la excepción es solo el código estable, no una frase en español."""
    assert str(ErrorProxLaunch(CodigoError.VMID_OCUPADO)) == "vmid_ocupado"


def test_codigos_de_error_del_documento_de_arquitectura_existen_y_son_unicos():
    esperados = {
        "CREDENCIALES_INVALIDAS", "SESION_EXPIRADA", "HUELLA_CAMBIADA", "HUELLA_NO_CONFIADA",
        "TFA_NO_SOPORTADO", "TFA_CODIGO_INCORRECTO", "SERVIDOR_NO_RESPONDE",
        "NODO_NO_DISPONIBLE", "PERMISO_INSUFICIENTE", "VMID_OCUPADO", "SIN_ESPACIO",
        "TAREA_TIEMPO_AGOTADO", "ERROR_FORMATO", "PARAMETRO_INVALIDO", "VERSION_NO_SOPORTADA",
        "RECURSO_INEXISTENTE", "UPID_INVALIDO", "LLAVERO_NO_DISPONIBLE", "DESCONOCIDO",
    }  # fmt: skip
    assert esperados <= {c.name for c in CodigoError}
    valores = [c.value for c in CodigoError]
    assert len(valores) == len(set(valores))


# --- Inventario ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "thin"),
    [
        ("lvmthin", True), ("zfspool", True), ("rbd", True),
        ("lvm", False), ("dir", False), ("nfs", False), ("cifs", False),
    ],
)  # fmt: skip
def test_v14_backends_thin(tipo, thin):
    assert storage("s", tipo, "images", 10).es_thin is thin


@pytest.mark.parametrize(
    ("libre_bytes", "esperado"),
    [
        pytest.param(150 * GIB, 150.0, id="CA-11.4-150-GiB-exactos"),
        pytest.param(GIB, 1.0, id="CA-11.4-1-GiB"),
        pytest.param(int(1.99 * GIB), 1.9, id="CA-11.4-redondeo-hacia-abajo"),
        pytest.param(int(150.19 * GIB), 150.1, id="CA-11.4-150.19-a-150.1"),
        pytest.param(GIB // 20, 0.0, id="CA-11.4-menos-de-una-decima"),
        pytest.param(0, 0.0, id="CA-11.4-cero"),
    ],
)
def test_ca11_4_libre_gib_redondea_hacia_abajo_a_un_decimal(libre_bytes, esperado):
    s = storage("s", "dir", "images", 1)
    s = type(s)(s.id, s.tipo, s.contenido, s.compartido, s.activo, 10 * GIB, libre_bytes)
    assert s.libre_gib == esperado


def test_ca11_4_la_conversion_es_coherente_con_v14(hacer_cfg, inv, caps, con_codigo):
    """Un disco igual al libre redondeado hacia abajo (150.0 GiB) cabe; uno mayor, no."""
    from proxlaunch.nucleo.validacion import validar_vm

    libre = int(inv.storages["pve1"][3].libre_gib)  # dirimg: 100 GiB
    assert (
        con_codigo(validar_vm(hacer_cfg(discos=[Disco("dirimg", libre)]), inv, caps), "V-14") == []
    )
    assert con_codigo(validar_vm(hacer_cfg(discos=[Disco("dirimg", libre + 1)]), inv, caps), "V-14")


# --- Tarea --------------------------------------------------------------------------


def test_ca20_2_etapas_en_orden():
    # MVP 4: se intercala «ajustando» (PUT config/resize tras clonar, RF-O22) antes de «listo».
    assert [e.value for e in Etapa] == [
        "validando",
        "enviando",
        "creando",
        "comprobando",
        "ajustando",
        "listo",
    ]


def test_desenlaces_previstos_por_rf20():
    assert {d.name for d in Desenlace} >= {
        "OK", "CON_AVISOS", "ERROR", "TIEMPO_AGOTADO", "CONEXION_PERDIDA", "PARCIAL",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("estado", "terminada"),
    [("stopped", True), ("running", False), ("", False)],
    ids=["CA-20.1-stopped", "CA-20.1-running", "CA-20.1-vacio"],
)
def test_ca20_1_estado_de_tarea_terminada(estado, terminada):
    assert EstadoTarea(estado).terminada is terminada


# --- Modelos de conexión: secretos fuera del repr (RNF-06) --------------------------


def test_rnf06_repr_de_credenciales_y_ticket_no_muestra_secretos():
    objetos = [
        CredencialToken("ana@pve!lab", "SECRETO-CENTINELA"),
        CredencialContrasena("root", "pam", "CLAVE-CENTINELA"),
        Ticket("TICKET-CENTINELA", "CSRF-CENTINELA", "root@pam", 0.0),
    ]
    for obj in objetos:
        for texto in (repr(obj), str(obj), f"{obj}", repr([obj]), repr({"x": obj})):
            assert "CENTINELA" not in texto


def test_rnf06_el_repr_mantiene_los_datos_no_secretos():
    assert "ana@pve!lab" in repr(CredencialToken("ana@pve!lab", "x"))
    assert "root" in repr(CredencialContrasena("root", "pam", "x"))


def test_rf07_el_perfil_no_tiene_campos_de_secretos():
    from dataclasses import fields

    nombres = {f.name for f in fields(PerfilConexion)}
    assert not nombres & {"secreto", "contrasena", "password", "token", "ticket", "csrf"}


def test_ca08_1_ca06_defaults_del_perfil():
    p = PerfilConexion(id="1", nombre="n", hosts=["h"])
    assert p.recordar_credenciales is False  # CA-08.1
    assert p.ignorar_ssl is False  # sección 5
    assert (p.puerto, p.realm) == (8006, "pam")
    assert p.metodo == "token"  # sección 5: método por defecto
