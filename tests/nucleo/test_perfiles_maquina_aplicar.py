"""Aplicar un perfil al formulario y compatibilidad (RF-P05, RF-P06, RF-P07; CA-P05.1,
CA-P05.3, CA-P05.7, CA-P06.1..P06.8, CA-P07.1..P07.4; INV-M1; RNF-M05; §13 caso 6).

``aplicar_perfil`` es puro: copia el hardware, conserva vmid/nombre/nodo/etiquetas y resuelve
las pistas de storage y bridge contra el inventario del nodo efectivo, sin inventar valores.
"""

import copy
import inspect
import time

from proxlaunch.nucleo.capacidades import Funcion, capacidades_para
from proxlaunch.nucleo.modelos.inventario import Bridge, Version
from proxlaunch.nucleo.modelos.vm import (
    Ballooning,
    Bus,
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
)
from proxlaunch.nucleo.perfiles_maquina.aplicar import (
    AvisoPista,
    aplicar_config,
    aplicar_perfil,
    config_desde_configuracion,
    hardware_igual,
    resumen_perfil,
)
from proxlaunch.nucleo.perfiles_maquina.compatibilidad import (
    evaluar_compatibilidad,
    funciones_requeridas,
)
from proxlaunch.nucleo.perfiles_maquina.fabrica import perfiles_fabrica
from proxlaunch.nucleo.perfiles_maquina.modelos import (
    BallooningPerfil,
    ConfigPerfil,
    DiscoPerfil,
    OrigenPerfil,
    PerfilMaquina,
    RedPerfil,
)
from proxlaunch.nucleo.validacion import Severidad, validar_vm

from .apoyo_lote import inventario, nodo, storage
from .apoyo_mvp3 import cfg_hw


def _perfil(config: ConfigPerfil) -> PerfilMaquina:
    return PerfilMaquina("a" * 32, "P", "", OrigenPerfil.USUARIO, config)


def _actual(nodo_="pve1", **kw) -> ConfiguracionVM:
    base = {"vmid": 321, "nombre": "mi-vm", "nodo": nodo_, "etiquetas": ("proxlaunch", "lote-x")}
    base.update(kw)
    return ConfiguracionVM(**base)


def _cluster():
    """Tres nodos con storages y bridges distintos (RF-P06, CA-P06.5)."""
    return inventario(
        (nodo("pve1"), nodo("pve2"), nodo("pve3")),
        storages={
            "pve1": (storage("local-lvm", "lvmthin", 150), storage("datos", "dir", 400)),
            "pve2": (storage("ssd-rapido", "zfspool", 100), storage("local-lvm", "lvmthin", 50)),
            "pve3": (storage("solo-iso", "dir", 100, contenido="iso"),),
        },
        bridges={
            "pve1": (Bridge("vmbr0", "bridge", False), Bridge("vmbr1", "bridge", False)),
            "pve2": (Bridge("br-otro", "bridge", False), Bridge("vmbr2", "OVSBridge", True)),
            "pve3": (Bridge("eno1", "eth", False),),
        },
    )


# --- CA-P05.1: qué se copia y qué se conserva ----------------------------------------------------


def test_se_copia_el_hardware_y_se_conservan_vmid_nombre_nodo_y_etiquetas():
    config = ConfigPerfil(
        firmware=Firmware.OVMF, sockets=2, cores=6, tipo_cpu="host", memoria_mib=10240,
        ballooning=BallooningPerfil(True, 1024),
        discos=(DiscoPerfil(50, Bus.SATA, discard=False, ssd=False, iothread=False), DiscoPerfil(10)),  # noqa: E501
        redes=(RedPerfil(ModeloRed.E1000, 30), RedPerfil()),
    )  # fmt: skip
    inv = _cluster()
    r = aplicar_perfil(_perfil(config), _actual(), inv)
    cfg = r.cfg
    assert (cfg.vmid, cfg.nombre, cfg.nodo, cfg.etiquetas) == (
        321,
        "mi-vm",
        "pve1",
        ("proxlaunch", "lote-x"),
    )
    assert (cfg.firmware, cfg.sockets, cfg.cores, cfg.tipo_cpu, cfg.memoria_mib) == (
        Firmware.OVMF,
        2,
        6,
        "host",
        10240,
    )
    assert cfg.ballooning == Ballooning(True, 1024)
    assert [(d.tamano_gib, d.bus, d.discard, d.ssd, d.iothread) for d in cfg.discos] == [
        (50, Bus.SATA, False, False, False),
        (10, Bus.SCSI, True, True, True),
    ]
    assert [(x.modelo, x.vlan) for x in cfg.redes] == [
        (ModeloRed.E1000, 30),
        (ModeloRed.VIRTIO, None),
    ]
    assert (
        cfg.con_disco
        and cfg.controlador_scsi == config.controlador_scsi
        and cfg.origen == config.origen
    )


def test_aplicar_no_modifica_la_configuracion_actual_ni_comparte_listas_con_el_perfil():
    actual = _actual(discos=[Disco("x", 1)], redes=[InterfazRed("y")])
    copia = copy.deepcopy(actual)
    config = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    r = aplicar_perfil(_perfil(config), actual, _cluster())
    assert actual == copia
    r.cfg.discos[0].tamano_gib = 999  # mutar el resultado no afecta al perfil
    r.cfg.redes.append(InterfazRed("z"))
    assert config.discos[0].tamano_gib == 8 and len(config.redes) == 1
    r2 = aplicar_perfil(_perfil(config), actual, _cluster())
    assert r2.cfg.discos[0].tamano_gib == 8


def test_los_campos_avanzados_se_aplican_igualmente_en_modo_basico():
    """CA-P05.3: bus, formato, IO Thread, tipo de CPU, ballooning, discard y ssd se aplican."""
    config = ConfigPerfil(
        tipo_cpu="host", ballooning=BallooningPerfil(False, 256),
        discos=(DiscoPerfil(8, Bus.IDE, discard=False, ssd=False, iothread=False),),
    )  # fmt: skip
    cfg = aplicar_perfil(_perfil(config), _actual(), _cluster()).cfg
    assert cfg.tipo_cpu == "host" and cfg.ballooning == Ballooning(False, 256)
    d = cfg.discos[0]
    assert (d.bus, d.discard, d.ssd, d.iothread) == (Bus.IDE, False, False, False)


def test_aplicar_es_determinista():
    inv = _cluster()
    perfil = _perfil(
        ConfigPerfil(discos=(DiscoPerfil(8, storage_preferido="nada"),), redes=(RedPerfil(),))
    )
    assert aplicar_perfil(perfil, _actual(), inv) == aplicar_perfil(perfil, _actual(), inv)


def test_aplicar_perfil_no_recibe_cliente_ni_sesion_ni_hace_red():
    """INV-M1 / CA-P05.7: la firma solo admite perfil, configuración e inventario."""
    assert list(inspect.signature(aplicar_perfil).parameters) == ["perfil", "actual", "inv"]
    assert list(inspect.signature(aplicar_config).parameters) == ["config", "actual", "inv"]
    # La suite corre con ``--disable-socket``: cualquier intento de red haría fallar la prueba.
    aplicar_perfil(perfiles_fabrica()[0], _actual(), _cluster())


# --- CA-P06.*: pistas ---------------------------------------------------------------------------


def _con_pistas(**kw) -> ConfigPerfil:
    return ConfigPerfil(
        discos=(DiscoPerfil(8, storage_preferido=kw.get("storage")),),
        redes=(RedPerfil(bridge_preferido=kw.get("bridge")),),
        storage_efi_preferido=kw.get("efi"),
        firmware=kw.get("firmware", Firmware.SEABIOS),
    )


def test_una_pista_de_storage_que_existe_y_sirve_se_usa_sin_aviso():
    """CA-P06.1."""
    r = aplicar_perfil(_perfil(_con_pistas(storage="datos")), _actual("pve1"), _cluster())
    assert r.cfg.discos[0].storage == "datos"
    assert r.avisos == ()


def test_una_pista_que_no_existe_usa_el_storage_de_mayor_espacio_libre_con_aviso():
    """CA-P06.2."""
    r = aplicar_perfil(_perfil(_con_pistas(storage="ssd-rapido")), _actual("pve1"), _cluster())
    assert r.cfg.discos[0].storage == "datos"  # 400 GiB libres > 150
    assert r.avisos == (AvisoPista("storage", "ssd-rapido", "datos", "pve1"),)


def test_la_misma_pista_se_resuelve_distinto_segun_el_nodo_efectivo():
    """§13.6: pista inexistente en un nodo y existente en otro (clúster, Automático)."""
    perfil = _perfil(_con_pistas(storage="ssd-rapido"))
    inv = _cluster()
    en_pve1 = aplicar_perfil(perfil, _actual("pve1"), inv)
    en_pve2 = aplicar_perfil(perfil, _actual("pve2"), inv)
    assert en_pve1.cfg.discos[0].storage == "datos" and len(en_pve1.avisos) == 1
    assert en_pve2.cfg.discos[0].storage == "ssd-rapido" and en_pve2.avisos == ()


def test_pista_que_existe_pero_esta_inactiva_o_sin_images_no_sirve():
    inv = inventario(
        (nodo("pve1"),),
        storages={
            "pve1": (
                storage("inactivo", "dir", 900, activo=False),
                storage("sin-images", "dir", 800, contenido="iso,backup"),
                storage("bueno", "dir", 10),
            )
        },
    )
    for pista in ("inactivo", "sin-images"):
        r = aplicar_perfil(_perfil(_con_pistas(storage=pista)), _actual("pve1"), inv)
        assert r.cfg.discos[0].storage == "bueno"
        assert r.avisos == (AvisoPista("storage", pista, "bueno", "pve1"),)


def test_una_pista_con_caracteres_prohibidos_no_se_usa():
    inv = inventario(
        (nodo("pve1"),), storages={"pve1": (storage("a,b", "dir", 1), storage("ok", "dir", 900))}
    )
    r = aplicar_perfil(_perfil(_con_pistas(storage="a,b")), _actual("pve1"), inv)
    assert r.cfg.discos[0].storage == "ok"
    assert r.avisos == (AvisoPista("storage", "a,b", "ok", "pve1"),)


def test_sin_pistas_se_usan_los_valores_por_defecto_sin_aviso():
    """CA-P06.4."""
    r = aplicar_perfil(_perfil(_con_pistas()), _actual("pve1"), _cluster())
    assert r.cfg.discos[0].storage == "datos"
    assert r.cfg.redes[0].bridge == "vmbr0"
    assert r.avisos == ()


def test_pista_de_bridge_que_existe_se_usa_y_la_que_no_cae_en_vmbr0_con_aviso():
    """CA-P06.3."""
    inv = _cluster()
    ok = aplicar_perfil(_perfil(_con_pistas(bridge="vmbr1")), _actual("pve1"), inv)
    assert ok.cfg.redes[0].bridge == "vmbr1" and ok.avisos == ()
    mal = aplicar_perfil(_perfil(_con_pistas(bridge="vmbr9")), _actual("pve1"), inv)
    assert mal.cfg.redes[0].bridge == "vmbr0"
    assert mal.avisos == (AvisoPista("bridge", "vmbr9", "vmbr0", "pve1"),)


def test_sin_vmbr0_el_bridge_por_defecto_es_el_primero_del_nodo():
    mal = aplicar_perfil(_perfil(_con_pistas(bridge="vmbr9")), _actual("pve2"), _cluster())
    assert mal.cfg.redes[0].bridge == "br-otro"


def test_una_pista_de_bridge_que_no_es_bridge_no_sirve():
    r = aplicar_perfil(
        _perfil(_con_pistas(bridge="eno1")),
        _actual("pve1"),
        inventario(
            (nodo("pve1"),),
            bridges={"pve1": (Bridge("eno1", "eth", False), Bridge("vmbr0", "bridge", False))},
        ),
    )
    assert r.cfg.redes[0].bridge == "vmbr0" and len(r.avisos) == 1


def test_sin_bridges_ni_storage_aptos_no_se_inventa_nada_y_v_16_v_17_lo_senalan():
    """CA-P06.7 / CA-P06.3: queda vacío; las reglas de M1 explican el problema."""
    inv = _cluster()
    r = aplicar_perfil(_perfil(_con_pistas(storage="datos", bridge="vmbr0")), _actual("pve3"), inv)
    assert r.cfg.discos[0].storage == "" and r.cfg.redes[0].bridge == ""
    assert {a.recurso for a in r.avisos} == {"storage", "bridge"}
    assert all(a.usado is None for a in r.avisos)
    codigos = {p.codigo for p in validar_vm(r.cfg, inv, capacidades_para(inv.version, None))}
    assert {"V-17", "V-16.sinredes"} <= codigos


def test_nodo_desconocido_no_rompe_y_deja_vacio():
    r = aplicar_perfil(_perfil(_con_pistas(storage="x")), _actual("nodo-inexistente"), _cluster())
    assert r.cfg.discos[0].storage == "" and r.cfg.redes[0].bridge == ""


def test_un_aviso_por_pista_distinta_no_uno_por_disco():
    config = ConfigPerfil(
        discos=(DiscoPerfil(8, storage_preferido="falta"), DiscoPerfil(8, storage_preferido="falta"), DiscoPerfil(8, storage_preferido="otra")),  # noqa: E501
        redes=(RedPerfil(bridge_preferido="b9"), RedPerfil(bridge_preferido="b9")),
    )  # fmt: skip
    r = aplicar_perfil(_perfil(config), _actual("pve1"), _cluster())
    assert sorted((a.recurso, a.pedido) for a in r.avisos) == [
        ("bridge", "b9"), ("storage", "falta"), ("storage", "otra"),
    ]  # fmt: skip


def test_con_disco_falso_no_hay_discos_ni_avisos_de_storage():
    config = ConfigPerfil(
        con_disco=False, discos=(DiscoPerfil(8, storage_preferido="falta"),), redes=(RedPerfil(),)
    )
    r = aplicar_perfil(_perfil(config), _actual("pve1"), _cluster())
    assert r.cfg.discos == [] and r.cfg.con_disco is False
    assert not [a for a in r.avisos if a.recurso == "storage"]


def test_pista_de_efi_solo_cuenta_con_ovmf_y_si_no_sirve_se_deja_none_con_aviso():
    inv = _cluster()
    seabios = aplicar_perfil(_perfil(_con_pistas(efi="ssd-rapido")), _actual("pve1"), inv)
    assert seabios.cfg.storage_efi is None and seabios.avisos == ()
    mal = aplicar_perfil(
        _perfil(_con_pistas(efi="ssd-rapido", firmware=Firmware.OVMF)), _actual("pve1"), inv
    )
    assert mal.cfg.storage_efi is None  # None = el del primer disco
    assert mal.avisos == (AvisoPista("storage_efi", "ssd-rapido", "datos", "pve1"),)
    bien = aplicar_perfil(
        _perfil(_con_pistas(efi="ssd-rapido", firmware=Firmware.OVMF)), _actual("pve2"), inv
    )
    assert bien.cfg.storage_efi == "ssd-rapido" and bien.avisos == ()


def test_sin_inventario_las_pistas_quedan_como_valor_y_sin_avisos():
    """Arquitectura §6.6: CSV sin conexión."""
    config = _con_pistas(storage="lo-que-sea", bridge="vmbrX", efi="e", firmware=Firmware.OVMF)
    r = aplicar_config(config, _actual("pve1"), None)
    assert r.cfg.discos[0].storage == "lo-que-sea" and r.cfg.redes[0].bridge == "vmbrX"
    assert r.cfg.storage_efi == "e" and r.avisos == ()


# --- config_desde_configuracion / hardware_igual / resumen ----------------------------------------


def test_config_desde_configuracion_con_y_sin_pistas():
    cfg = cfg_hw(storage_efi="efi1", firmware=Firmware.OVMF, vmid=5, nombre="x", nodo="y")
    con = config_desde_configuracion(cfg, con_pistas=True)
    assert con.discos[0].storage_preferido == "datos"
    assert con.redes[0].bridge_preferido == "vmbr0"
    assert con.storage_efi_preferido == "efi1"
    sin = config_desde_configuracion(cfg, con_pistas=False)
    assert sin.discos[0].storage_preferido is None and sin.redes[0].bridge_preferido is None
    assert sin.storage_efi_preferido is None
    assert (sin.cores, sin.memoria_mib) == (cfg.cores, cfg.memoria_mib)


def test_una_pista_vacia_no_se_guarda():
    cfg = cfg_hw(discos=[Disco("", 8)], redes=[InterfazRed("")])
    c = config_desde_configuracion(cfg, con_pistas=True)
    assert c.discos[0].storage_preferido is None and c.redes[0].bridge_preferido is None


def test_ida_y_vuelta_formulario_perfil_formulario_en_el_mismo_servidor():
    inv = _cluster()
    cfg = cfg_hw(
        nodo="pve1", cores=3, memoria_mib=3000,
        discos=[Disco("datos", 20, Bus.SATA, discard=False), Disco("local-lvm", 5)],
        redes=[InterfazRed("vmbr1", ModeloRed.E1000, 7)],
    )  # fmt: skip
    perfil = _perfil(config_desde_configuracion(cfg, con_pistas=True))
    de_vuelta = aplicar_perfil(perfil, _actual("pve1"), inv)
    assert de_vuelta.avisos == () and hardware_igual(de_vuelta.cfg, cfg)


def test_hardware_igual_ignora_vmid_nombre_nodo_y_etiquetas_pero_ve_el_hardware():
    base = cfg_hw()
    assert hardware_igual(base, cfg_hw(vmid=1, nombre="otro", nodo="n", etiquetas=("t",)))
    for cambio in (
        {"cores": 3}, {"sockets": 2}, {"memoria_mib": 4096}, {"firmware": Firmware.OVMF},
        {"tipo_cpu": "host"}, {"ballooning": Ballooning(True, 512)}, {"con_disco": False},
        {"discos": [Disco("datos", 33)]}, {"discos": [Disco("otro", 32)]},
        {"discos": [Disco("datos", 32, discard=False)]}, {"redes": [InterfazRed("vmbr1")]},
        {"redes": [InterfazRed("vmbr0", vlan=3)]}, {"storage_efi": "e"},
    ):  # fmt: skip
        assert not hardware_igual(base, cfg_hw(**cambio)), cambio


def test_resumen_del_perfil_para_el_selector():
    r = resumen_perfil(
        ConfigPerfil(
            sockets=2,
            cores=3,
            memoria_mib=4096,
            discos=(DiscoPerfil(40), DiscoPerfil(10)),
            redes=(RedPerfil(),),
        )
    )
    assert (r.vcpus, r.memoria_mib, r.discos_gib, r.redes) == (6, 4096, (40, 10), 1)
    sin = resumen_perfil(ConfigPerfil(con_disco=False, discos=(DiscoPerfil(40),)))
    assert sin.discos_gib == () and sin.redes == 0


def test_aplicar_un_perfil_tarda_menos_de_100_ms():
    """CA-RNF-M05 (con holgura: promedio sobre 200 aplicaciones)."""
    inv = _cluster()
    perfil = _perfil(_con_pistas(storage="falta", bridge="b9"))
    actual = _actual("pve1")
    inicio = time.process_time()
    for _ in range(200):
        aplicar_perfil(perfil, actual, inv)
    assert (time.process_time() - inicio) / 200 < 0.1


# --- Compatibilidad (RF-P07) ----------------------------------------------------------------------


def _preparar(config, version=(9, 2), nodo_="pve1"):
    inv = _cluster()
    inv.version = Version(f"{version[0]}.{version[1]}.0", version[0], version[1], 0)
    cfg = aplicar_perfil(_perfil(config), _actual(nodo_), inv).cfg
    return cfg, inv, capacidades_para(inv.version, None)


def test_sin_funciones_requeridas_es_exactamente_validar_vm():
    """CA-P07.1 / CA-P07.2: en el MVP 3 ningún campo exige versión superior a 8.0."""
    config = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    assert funciones_requeridas(config) == frozenset()
    cfg, inv, caps = _preparar(config, (8, 0))
    assert evaluar_compatibilidad(cfg, config, inv, caps) == validar_vm(cfg, inv, caps)


def test_el_mecanismo_senala_una_funcion_de_prueba_inyectada_con_la_version_requerida():
    config = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    cfg, inv, caps = _preparar(config, (8, 0))
    problemas = evaluar_compatibilidad(
        cfg, config, inv, caps, requeridas=lambda c: frozenset({Funcion.IMPORTAR_DISCO})
    )
    (p,) = [x for x in problemas if x.codigo == "V-P07.version"]
    assert p.severidad == Severidad.ERROR
    assert p.params == {"funcion": "importar_disco", "version": "8.2"}


def test_con_la_version_suficiente_la_funcion_inyectada_no_da_problema():
    config = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    cfg, inv, caps = _preparar(config, (9, 2))
    problemas = evaluar_compatibilidad(
        cfg, config, inv, caps, requeridas=lambda c: frozenset({Funcion.IMPORTAR_DISCO})
    )
    assert not [x for x in problemas if x.codigo == "V-P07.version"]


def test_con_version_forzada_menor_la_compatibilidad_usa_las_capacidades_forzadas():
    """CA-P07.5."""
    config = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    cfg, inv, _ = _preparar(config, (9, 2))
    forzada = capacidades_para(inv.version, (8, 0))
    problemas = evaluar_compatibilidad(
        cfg, config, inv, forzada, requeridas=lambda c: frozenset({Funcion.IMPORTAR_DISCO})
    )
    assert any(x.codigo == "V-P07.version" for x in problemas)


def test_tipo_cpu_host_da_el_aviso_de_migracion_y_no_bloquea():
    """CA-P07.4."""
    config = ConfigPerfil(tipo_cpu="host", discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    cfg, inv, caps = _preparar(config)
    (aviso,) = [
        p for p in evaluar_compatibilidad(cfg, config, inv, caps) if p.codigo == "V-P07.cpu_host"
    ]
    assert aviso.severidad == Severidad.AVISO
    normal = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    cfg2, inv2, caps2 = _preparar(normal)
    assert not [
        p for p in evaluar_compatibilidad(cfg2, normal, inv2, caps2) if p.codigo == "V-P07.cpu_host"
    ]


def test_el_panel_incluye_los_errores_de_capa_2_del_servidor():
    """CA-P07.6: los errores de capa 2 se tratan como los de cualquier formulario."""
    config = ConfigPerfil(discos=(DiscoPerfil(8),), redes=(RedPerfil(),))
    cfg, inv, caps = _preparar(config, nodo_="pve3")  # sin storage ni bridge aptos
    codigos = {p.codigo for p in evaluar_compatibilidad(cfg, config, inv, caps)}
    assert {"V-17", "V-16.sinredes"} <= codigos
