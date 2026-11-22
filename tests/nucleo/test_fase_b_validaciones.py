"""Fase B (0.7.0): reglas V-B de cloud-init, snippets y espera de IP (CA-B14.1).

Cada regla V-B20 a V-B39, V-B50 a V-B56 y V-B60 a V-B65 se provoca con una configuración mínima y
se comprueba su severidad, su campo (o la MV del plan) y que ningún ``params`` lleva valores
secretos: toda configuración de la tabla que admite contraseña lleva el centinela y una clave
privada pegada lleva otro, y ninguno puede aparecer en los problemas.

Las reglas de B2 (V-B01 a V-B16) son de ``test_fase_b_plantilla_imagen.py``. Las tres reglas de
lote de IP (V-B30, V-B31 y V-B38) se ejercitan a fondo en ``test_fase_b_red.py``; aquí solo hay un
caso de cada una para cerrar la tabla. Se usa ``validar_vm`` (el mismo camino de una MV suelta,
un lote y una fila de CSV) y, para V-B51 y V-B52, ``construir_plan``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from proxlaunch.nucleo.capacidades import Capacidades, capacidades_para
from proxlaunch.nucleo.cloudinit.codigos import (
    CODIGOS_CLOUDINIT_SIN_SERVIDOR,
    CODIGOS_ESPERA_IP_SIN_SERVIDOR,
)
from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    CicustomHeredado,
    ConfigCloudInit,
    InfoCloudInitPlantilla,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
)
from proxlaunch.nucleo.cloudinit.serie import expandir_serie, problemas_serie_lote
from proxlaunch.nucleo.cloudinit.validacion import validar_contrasena
from proxlaunch.nucleo.lote.modelos import ElementoPlan
from proxlaunch.nucleo.lote.planificador import construir_plan
from proxlaunch.nucleo.modelos.catalogo import ListadoSnippets, Snippet
from proxlaunch.nucleo.modelos.inventario import Inventario, Storage, Version
from proxlaunch.nucleo.modelos.vm import ConfiguracionVM, OrigenSO
from proxlaunch.nucleo.secreto import Secreto
from proxlaunch.nucleo.validacion import Severidad, validar_sin_servidor, validar_vm

from .apoyo_fase_a import ROL_COMPLETO, catalogo, inv_con, permisos
from .apoyo_lote import definicion
from .apoyo_mvp4 import cfg_base, cfg_clon, inv_origen, plantilla_pve

CENTINELA = "S3cr3t-Prueba!"
CUERPO_PRIVADO = "CuerpoPrivado-ZZZ-9f8e7d"
CLAVE_OK = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAAAAAAAA= ana@pc"
ERROR, AVISO = Severidad.ERROR, Severidad.AVISO
FIJA, DHCP = ModoTarjeta.FIJA, ModoTarjeta.DHCP

CAPS_92 = capacidades_para(Version("9.2.1", 9, 2, 1), None)
CAPS_90 = capacidades_para(Version("9.0.0", 9, 0, 0), None)
CAPS_81 = capacidades_para(Version("8.1.4", 8, 1, 4), None)

# Privilegios de B (más el rol base): con todos, ninguna regla de permisos se dispara.
TODOS = (
    *ROL_COMPLETO,
    "VM.Config.Cloudinit",
    "VM.GuestAgent.Audit",
    "VM.Monitor",
    "Datastore.Audit",
    "Datastore.Allocate",
)
BASE_B = tuple(
    p for p in TODOS if p not in ("VM.Config.Cloudinit", "VM.GuestAgent.Audit", "VM.Monitor")
)

INFO_OK = InfoCloudInitPlantilla(unidad=True, agente=False, tarjetas=(0, 1))
SNIPPET_OK = "local:snippets/agente.yaml"
STORAGE_SNIPPETS = Storage(
    "local", "dir", frozenset({"snippets", "iso"}), False, True, 10**12, 10**12
)


def inv_con_permisos(*privilegios: str, storages: dict | None = None) -> Inventario:
    """Inventario con catálogo cuyos permisos efectivos son exactamente los dados (en ``/``)."""
    inv = inv_con(catalogo(perm=permisos(tuple(privilegios))))
    if storages is not None:
        inv = dataclasses.replace(inv, storages_todos=storages)
    return inv


INV_TODO = inv_con_permisos(*TODOS, storages={"pve1": (STORAGE_SNIPPETS,)})


def clon(
    ci: ConfigCloudInit | None = None,
    info: InfoCloudInitPlantilla | None = INFO_OK,
    *,
    plantilla: str = "base",
    **cambios,
) -> ConfiguracionVM:
    """Clon de una plantilla con cloud-init y la info que la plantilla dio al leer su config."""
    return cfg_clon(plantilla, 9000, "pve1", cloudinit=ci, info_cloudinit=info, **cambios)


def ci_(**kw) -> ConfigCloudInit:
    return ConfigCloudInit(**kw)


@dataclass
class Caso:
    """Una regla provocada: lo que se espera de su problema y cómo se obtiene."""

    regla: str
    severidad: Severidad
    campo: str | None
    obtener: Callable[[], list]
    params: dict[str, str] = field(default_factory=dict)  # subconjunto esperado de params
    indice: int | None = None  # MV del plan (solo reglas de lote)


def vb(cfg, inv=INV_TODO, caps: Capacidades = CAPS_92) -> list:
    return [p for p in validar_vm(cfg, inv, caps) if p.codigo.startswith("V-B")]


def con_secreto(cfg: ConfiguracionVM) -> ConfiguracionVM:
    """La misma configuración con el centinela como contraseña (si lleva cloud-init)."""
    if cfg.cloudinit is None:
        return cfg
    secreto = Secreto(CENTINELA)
    return dataclasses.replace(
        cfg, cloudinit=dataclasses.replace(cfg.cloudinit, contrasena=secreto)
    )


def validar(cfg, inv=INV_TODO, caps: Capacidades = CAPS_92):
    return lambda: vb(con_secreto(cfg), inv, caps)


def elementos(config: ConfigCloudInit, n: int) -> list[ElementoPlan]:
    out = []
    for i in range(n):
        nombre = f"web-{i + 1:02d}"
        cfg = ConfiguracionVM(100 + i, nombre, "pve1", cloudinit=expandir_serie(config, i))
        out.append(ElementoPlan(i, nombre, 100 + i, "pve1", cfg))
    return out


def plan_con_snippets(volid: str, tamanos: dict[str, int | None], **otros) -> list:
    """Problemas de ``construir_plan`` para un clon de 1 MV con los snippets pedidos."""
    sn = Storage("local", "dir", frozenset({"snippets"}), False, True, 10**12, 10**12)
    inv = inv_origen(
        nodos=("pve1",),
        plantillas=(plantilla_pve(9000, "base", "pve1"),),
        extra_storages={"pve1": (sn,)},
    )
    listado = ListadoSnippets(
        "pve1",
        "local",
        False,
        tuple(Snippet(v, v.partition("/")[2], t, True) for v, t in tamanos.items()),
    )
    inv.catalogo = dataclasses.replace(inv.catalogo, snippets=(listado,))
    cfg = cfg_clon("base", 9000, "pve1", cloudinit=ci_(snippets=SnippetsCloudInit(**otros)))
    d = definicion(1, plantilla_vm=cfg)
    plan = construir_plan(
        d,
        inv,
        [100],
        [],
        id_lote="abcd1234",
        ahora=0.0,
        version_validacion=(9, 2),
        vms_visibles=None,
    )
    return list(plan.problemas)


MIB = 1024 * 1024
V_USER = "local:snippets/u.yaml"
V_VENDOR = "local:snippets/v.yaml"
PRIVADA = (
    f"-----BEGIN OPENSSH PRIVATE KEY-----\n{CUERPO_PRIVADO}\n-----END OPENSSH PRIVATE KEY-----"
)


def _claves_invalidas(*lineas: str) -> ConfigCloudInit:
    return ci_(claves=(CLAVE_OK, *lineas))


CASOS: dict[str, Caso] = {
    # --- V-B20: unidad cloud-init de la plantilla ---
    "V-B20 sin unidad": Caso(
        "V-B20",
        ERROR,
        "cloudinit",
        validar(clon(ci_(usuario="u"), InfoCloudInitPlantilla(unidad=False), plantilla="base")),
        {"plantilla": "base"},
    ),
    "V-B20 no comprobable": Caso(
        "V-B20",
        AVISO,
        "cloudinit",
        validar(clon(ci_(usuario="u"), InfoCloudInitPlantilla(unidad=None))),
        {"motivo": "no_comprobable"},
    ),
    # --- V-B21: usuario ---
    "V-B21 espacio": Caso(
        "V-B21",
        ERROR,
        "cloudinit.usuario",
        validar(clon(ci_(usuario="mal usuario"))),
        {"motivo": "caracteres"},
    ),  # fmt: skip
    "V-B21 dos puntos": Caso(
        "V-B21",
        ERROR,
        "cloudinit.usuario",
        validar(clon(ci_(usuario="a:b"))),
        {"motivo": "caracteres"},
    ),  # fmt: skip
    "V-B21 salto de linea": Caso(
        "V-B21",
        ERROR,
        "cloudinit.usuario",
        validar(clon(ci_(usuario="a\nb"))),
        {"motivo": "caracteres"},
    ),  # fmt: skip
    "V-B21 control": Caso(
        "V-B21",
        ERROR,
        "cloudinit.usuario",
        validar(clon(ci_(usuario="a\x07"))),
        {"motivo": "caracteres"},
    ),  # fmt: skip
    "V-B21 patron tipico": Caso(
        "V-B21",
        AVISO,
        "cloudinit.usuario",
        validar(clon(ci_(usuario="Root"))),
        {"motivo": "patron"},
    ),  # fmt: skip
    # --- V-B22 / V-B23 / V-B24: claves ---
    "V-B22 sin cuerpo": Caso(
        "V-B22",
        ERROR,
        "cloudinit.claves",
        validar(clon(_claves_invalidas("ssh-rsa"))),
        {"linea": "2", "motivo": "sin_cuerpo"},
    ),  # fmt: skip
    "V-B22 tipo desconocido": Caso(
        "V-B22",
        ERROR,
        "cloudinit.claves",
        validar(clon(_claves_invalidas("hola"))),
        {"linea": "2", "motivo": "tipo_desconocido"},
    ),  # fmt: skip
    "V-B22 no base64": Caso(
        "V-B22",
        ERROR,
        "cloudinit.claves",
        validar(clon(_claves_invalidas("ssh-rsa !!!!"))),
        {"linea": "2", "motivo": "base64"},
    ),  # fmt: skip
    "V-B22 con opciones": Caso(
        "V-B22",
        ERROR,
        "cloudinit.claves",
        validar(clon(_claves_invalidas(f'command="x" {CLAVE_OK}'))),
        {"linea": "2", "motivo": "con_opciones"},
    ),  # fmt: skip
    "V-B23 clave privada": Caso(
        "V-B23", ERROR, "cloudinit.claves", validar(clon(ci_(claves=(PRIVADA,)))), {}
    ),
    "V-B23 mezcla con publica": Caso(
        "V-B23", ERROR, "cloudinit.claves", validar(clon(ci_(claves=(CLAVE_OK, PRIVADA)))), {}
    ),
    "V-B24 demasiadas": Caso(
        "V-B24",
        ERROR,
        "cloudinit.claves",
        validar(clon(ci_(claves=tuple(CLAVE_OK.replace("ana@pc", f"c{i}") for i in range(21))))),
        {"motivo": "demasiadas"},
    ),  # fmt: skip
    "V-B24 demasiado texto": Caso(
        "V-B24",
        ERROR,
        "cloudinit.claves",
        validar(clon(ci_(claves=(CLAVE_OK + " " + "x" * 8200,)))),
        {"motivo": "demasiado_texto"},
    ),  # fmt: skip
    "V-B24 duplicadas": Caso(
        "V-B24",
        AVISO,
        "cloudinit.claves",
        validar(clon(ci_(claves=(CLAVE_OK, CLAVE_OK)))),
        {"motivo": "duplicadas", "cantidad": "1"},
    ),  # fmt: skip
    # --- V-B26..V-B29: IP, puerta ---
    "V-B26 sin prefijo": Caso(
        "V-B26",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5"),)))),
        {"tarjeta": "0", "motivo": "sin_prefijo"},
    ),  # fmt: skip
    "V-B26 prefijo fuera de rango": Caso(
        "V-B26",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5/31"),)))),
        {"motivo": "prefijo"},
    ),  # fmt: skip
    "V-B26 octeto": Caso(
        "V-B26",
        ERROR,
        "cloudinit.tarjetas[1].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(1, FIJA, "10.0.0.256/24"),)))),
        {"tarjeta": "1", "motivo": "octeto"},
    ),  # fmt: skip
    "V-B26 ceros": Caso(
        "V-B26",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "010.0.0.1/24"),)))),
        {"motivo": "ceros"},
    ),  # fmt: skip
    "V-B26 reservada": Caso(
        "V-B26",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "127.0.0.1/8"),)))),
        {"motivo": "reservada"},
    ),  # fmt: skip
    "V-B27 direccion de red": Caso(
        "V-B27",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.0/24"),)))),
        {"motivo": "red_o_difusion"},
    ),  # fmt: skip
    "V-B27 difusion": Caso(
        "V-B27",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.255/24"),)))),
        {"motivo": "red_o_difusion"},
    ),  # fmt: skip
    "V-B28 puerta fuera de red": Caso(
        "V-B28",
        ERROR,
        "cloudinit.tarjetas[0].puerta",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5/24", puerta="10.0.1.1"),)))),
        {"motivo": "fuera_de_red"},
    ),  # fmt: skip
    "V-B28 puerta igual a la ip": Caso(
        "V-B28",
        ERROR,
        "cloudinit.tarjetas[0].puerta",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5/24", puerta="10.0.0.5"),)))),
        {"motivo": "igual_a_ip"},
    ),  # fmt: skip
    "V-B28 puerta es difusion": Caso(
        "V-B28",
        ERROR,
        "cloudinit.tarjetas[0].puerta",
        validar(
            clon(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5/24", puerta="10.0.0.255"),)))
        ),
        {"motivo": "red_o_difusion"},
    ),  # fmt: skip
    "V-B29 puerta con dhcp": Caso(
        "V-B29",
        ERROR,
        "cloudinit.tarjetas[0].puerta",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, DHCP, puerta="10.0.0.1"),)))),
        {"tarjeta": "0"},
    ),  # fmt: skip
    "V-B29 puerta sin configurar": Caso(
        "V-B29",
        ERROR,
        "cloudinit.tarjetas[0].puerta",
        validar(
            clon(
                ci_(
                    usuario="u",  # sin otro dato la config cuenta como vacía: ver BUG-B-P2-3
                    tarjetas=(TarjetaCloudInit(0, ModoTarjeta.SIN_CONFIGURAR, puerta="10.0.0.1"),),
                )
            )
        ),
        {"tarjeta": "0"},
    ),  # fmt: skip
    # --- V-B30 / V-B31 / V-B38: lote de IP (un caso de cada una; detalle en test_fase_b_red) ---
    "V-B30 serie desborda": Caso(
        "V-B30",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        lambda: problemas_serie_lote(
            elementos(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.250/24", serie=True),)), 10)
        ),
        {"nombre": "web-06", "direccion": "10.0.0.255"},
        indice=5,
    ),  # fmt: skip
    "V-B31 ip repetida": Caso(
        "V-B31",
        ERROR,
        "cloudinit.tarjetas[1].ip",
        lambda: problemas_serie_lote(
            elementos(
                ci_(
                    tarjetas=(
                        TarjetaCloudInit(0, FIJA, "10.0.0.5/24"),
                        TarjetaCloudInit(1, FIJA, "10.0.0.5/24"),
                    )
                ),
                1,
            )
        ),
        {"direccion": "10.0.0.5"},
        indice=0,
    ),  # fmt: skip
    "V-B38 misma ip sin serie": Caso(
        "V-B38",
        ERROR,
        "cloudinit.tarjetas[0].ip",
        lambda: problemas_serie_lote(
            elementos(ci_(tarjetas=(TarjetaCloudInit(0, FIJA, "10.0.0.5/24"),)), 3)
        ),
        {"tarjeta": "0", "cantidad": "3"},
    ),  # fmt: skip
    # --- V-B32 / V-B33 / V-B36 ---
    "V-B32 dns invalido": Caso(
        "V-B32", ERROR, "cloudinit.dns", validar(clon(ci_(dns=("8.8.8",)))), {}
    ),
    "V-B32 dns con punto y coma": Caso(
        "V-B32", ERROR, "cloudinit.dns", validar(clon(ci_(dns=("8.8.8.8;1.1.1.1",)))), {}
    ),
    "V-B32 mas de tres": Caso(
        "V-B32",
        AVISO,
        "cloudinit.dns",
        validar(clon(ci_(dns=("1.1.1.1", "8.8.8.8", "9.9.9.9", "8.8.4.4")))),
        {"cantidad": "4"},
    ),  # fmt: skip
    "V-B33 dominio invalido": Caso(
        "V-B33", ERROR, "cloudinit.dominio", validar(clon(ci_(dominio="_a..b"))), {}
    ),
    "V-B36 ciupgrade no booleano": Caso(
        "V-B36",
        ERROR,
        "cloudinit.actualizar",
        validar(clon(ci_(actualizar="si"))),
        {},  # type: ignore[arg-type]
    ),
    # --- V-B34 / V-B35 / V-B39 ---
    "V-B34 tarjeta inexistente": Caso(
        "V-B34",
        ERROR,
        "cloudinit.tarjetas[3]",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(3, DHCP),)))),
        {"tarjeta": "3", "motivo": "inexistente"},
    ),  # fmt: skip
    "V-B34 indice fuera de rango": Caso(
        "V-B34",
        ERROR,
        "cloudinit.tarjetas[32]",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(32, DHCP),)))),
        {"motivo": "rango"},
    ),  # fmt: skip
    "V-B34 tarjeta repetida": Caso(
        "V-B34",
        ERROR,
        "cloudinit.tarjetas[0]",
        validar(clon(ci_(tarjetas=(TarjetaCloudInit(0, DHCP), TarjetaCloudInit(0, DHCP))))),
        {"motivo": "repetida"},
    ),  # fmt: skip
    "V-B35 windows": Caso(
        "V-B35",
        AVISO,
        "cloudinit",
        validar(
            clon(
                ci_(usuario="u"),
                InfoCloudInitPlantilla(unidad=True, ostype="win10", es_windows=True),
            )
        ),
        {},
    ),  # fmt: skip
    "V-B39 origen distinto de clonar": Caso(
        "V-B39",
        ERROR,
        "cloudinit",
        validar(cfg_base(cloudinit=ci_(usuario="u"), origen=OrigenSO.DISCO_VACIO)),
        {},
    ),  # fmt: skip
    # --- V-B25: contraseña (con la plantilla, el centinela ya va en la config) ---
    "V-B25 windows": Caso(
        "V-B25",
        ERROR,
        "cloudinit.contrasena",
        validar(
            clon(
                ci_(usuario="u"),
                InfoCloudInitPlantilla(unidad=True, ostype="win11", es_windows=True),
            )
        ),
        {"motivo": "windows"},
    ),  # fmt: skip
    "V-B25 no coincide": Caso(
        "V-B25",
        ERROR,
        "cloudinit.contrasena",
        lambda: validar_contrasena(CENTINELA, CENTINELA + "x", INFO_OK),
        {"motivo": "no_coincide"},
    ),  # fmt: skip
    "V-B25 control": Caso(
        "V-B25",
        ERROR,
        "cloudinit.contrasena",
        lambda: validar_contrasena(CENTINELA + "\n", CENTINELA + "\n", INFO_OK),
        {"motivo": "control"},
    ),  # fmt: skip
    "V-B25 demasiado larga": Caso(
        "V-B25",
        ERROR,
        "cloudinit.contrasena",
        lambda: validar_contrasena(CENTINELA + "a" * 128, CENTINELA + "a" * 128, INFO_OK),
        {"motivo": "larga"},
    ),  # fmt: skip
    "V-B25 corta": Caso(
        "V-B25",
        ERROR,
        "cloudinit.contrasena",
        lambda: validar_contrasena("S3c!", "S3c!", INFO_OK),
        {"motivo": "corta"},
    ),  # fmt: skip
    # --- V-B37: privilegio de cloud-init de la versión ---
    "V-B37 9.2 sin Cloudinit": Caso(
        "V-B37",
        ERROR,
        "cloudinit",
        validar(clon(ci_(usuario="u")), inv_con_permisos(*BASE_B, storages={"pve1": ()}), CAPS_92),
        {"privilegio": "VM.Config.Cloudinit", "ruta": "/vms"},
    ),  # fmt: skip
    "V-B37 9.0 solo Network aviso": Caso(
        "V-B37",
        AVISO,
        "cloudinit",
        validar(clon(ci_(usuario="u")), inv_con_permisos(*BASE_B), CAPS_90),
        {"motivo": "version_incierta"},
    ),  # fmt: skip
    "V-B37 8.x sin ninguno": Caso(
        "V-B37",
        ERROR,
        "cloudinit",
        validar(
            clon(ci_(usuario="u")),
            inv_con_permisos(*(p for p in BASE_B if p != "VM.Config.Network")),
            CAPS_81,
        ),
        {"privilegio": "VM.Config.Cloudinit"},
    ),  # fmt: skip
    "V-B37 dns sin Cloudinit ni Network": Caso(
        "V-B37",
        ERROR,
        "cloudinit.dns",
        validar(
            clon(ci_(dns=("1.1.1.1",))),
            inv_con_permisos(*(p for p in BASE_B if p != "VM.Config.Network")),
            CAPS_92,
        ),
        {},
    ),  # fmt: skip
    # --- V-B50: almacenamiento con contenido snippets en el nodo ---
    "V-B50 nodo sin snippets": Caso(
        "V-B50",
        ERROR,
        "cloudinit.snippets",
        validar(
            clon(ci_(snippets=SnippetsCloudInit(vendor=SNIPPET_OK))),
            inv_con_permisos(
                *TODOS,
                storages={
                    "pve1": (Storage("local", "dir", frozenset({"iso"}), False, True, 1, 1),)
                },
            ),
        ),
        {"nodo": "pve1"},
    ),  # fmt: skip
    # --- V-B51 / V-B52 (planificador, contra los listados del catálogo) ---
    "V-B51 el snippet no existe": Caso(
        "V-B51",
        ERROR,
        "cloudinit.snippets.vendor",
        lambda: plan_con_snippets(SNIPPET_OK, {"local:snippets/otro.yaml": 10}, vendor=SNIPPET_OK),
        {"nodo": "pve1", "tipo": "vendor", "motivo": "no_existe"},
        indice=0,
    ),  # fmt: skip
    "V-B52 individual": Caso(
        "V-B52",
        ERROR,
        "cloudinit.snippets.vendor",
        lambda: plan_con_snippets(SNIPPET_OK, {SNIPPET_OK: 2 * MIB}, vendor=SNIPPET_OK),
        {"motivo": "individual", "tipo": "vendor"},
        indice=0,
    ),  # fmt: skip
    "V-B52 suma": Caso(
        "V-B52",
        ERROR,
        "cloudinit.snippets",
        lambda: plan_con_snippets(
            V_USER,
            {
                V_USER: MIB,
                V_VENDOR: MIB,
                "local:snippets/n.yaml": MIB,
                "local:snippets/m.yaml": MIB,
            },
            user=V_USER,
            vendor=V_VENDOR,
            network="local:snippets/n.yaml",
            meta="local:snippets/m.yaml",
        ),
        {"motivo": "suma"},
        indice=0,
    ),  # fmt: skip
    # --- V-B53 / V-B54 / V-B55 / V-B56 ---
    "V-B53 user junto a usuario": Caso(
        "V-B53",
        AVISO,
        "cloudinit.snippets.user",
        validar(clon(ci_(usuario="deploy", snippets=SnippetsCloudInit(user=V_USER)))),
        {},
    ),  # fmt: skip
    "V-B53 user junto a claves": Caso(
        "V-B53",
        AVISO,
        "cloudinit.snippets.user",
        validar(clon(ci_(claves=(CLAVE_OK,), snippets=SnippetsCloudInit(user=V_USER)))),
        {},
    ),  # fmt: skip
    "V-B54 sin snippets en la ruta": Caso(
        "V-B54",
        ERROR,
        "cloudinit.snippets.user",
        validar(clon(ci_(snippets=SnippetsCloudInit(user="local:iso/a.iso")))),
        {"tipo": "user"},
    ),  # fmt: skip
    "V-B54 sin almacenamiento": Caso(
        "V-B54",
        ERROR,
        "cloudinit.snippets.vendor",
        validar(clon(ci_(snippets=SnippetsCloudInit(vendor="snippets/a.yaml")))),
        {"tipo": "vendor"},
    ),  # fmt: skip
    "V-B54 con ..": Caso(
        "V-B54",
        ERROR,
        "cloudinit.snippets.network",
        validar(clon(ci_(snippets=SnippetsCloudInit(network="local:snippets/../x")))),
        {"tipo": "network"},
    ),  # fmt: skip
    "V-B54 con coma": Caso(
        "V-B54",
        ERROR,
        "cloudinit.snippets.meta",
        validar(clon(ci_(snippets=SnippetsCloudInit(meta="local:snippets/a,b")))),
        {"tipo": "meta"},
    ),  # fmt: skip
    "V-B54 con espacio": Caso(
        "V-B54",
        ERROR,
        "cloudinit.snippets.user",
        validar(clon(ci_(snippets=SnippetsCloudInit(user="local:snippets/a b")))),
        {"tipo": "user"},
    ),  # fmt: skip
    "V-B55 9.2 sin AllocateSpace": Caso(
        "V-B55",
        ERROR,
        "cloudinit.snippets",
        validar(
            clon(ci_(snippets=SnippetsCloudInit(vendor=SNIPPET_OK))),
            inv_con_permisos(
                *(p for p in TODOS if p not in ("Datastore.AllocateSpace", "Datastore.Audit")),
                storages={"pve1": (STORAGE_SNIPPETS,)},
            ),
            CAPS_92,
        ),
        {"ruta": "/storage"},
    ),  # fmt: skip
    "V-B55 8.x sin Allocate aviso": Caso(
        "V-B55",
        AVISO,
        "cloudinit.snippets",
        validar(
            clon(ci_(snippets=SnippetsCloudInit(vendor=SNIPPET_OK))),
            inv_con_permisos(
                *(p for p in TODOS if p != "Datastore.Allocate"),
                storages={"pve1": (STORAGE_SNIPPETS,)},
            ),
            CAPS_81,
        ),
        {"motivo": "no_verificado"},
    ),  # fmt: skip
    "V-B56 cicustom no interpretable": Caso(
        "V-B56",
        AVISO,
        "cloudinit.snippets",
        validar(
            clon(
                ci_(snippets=SnippetsCloudInit(vendor=SNIPPET_OK)),
                dataclasses.replace(INFO_OK, cicustom=CicustomHeredado({}, interpretable=False)),
            )
        ),
        {"plantilla": "base"},
    ),  # fmt: skip
    # --- B3: V-B60 .. V-B65 ---
    "V-B60 esperar ip sin encender": Caso(
        "V-B60", ERROR, "esperar_ip", validar(clon(esperar_ip=True, encender=False)), {}
    ),
    "V-B61 plazo bajo": Caso(
        "V-B61",
        ERROR,
        "plazo_ip_s",
        validar(clon(esperar_ip=True, encender=True, plazo_ip_s=9)),
        {"minimo": "10", "maximo": "1800"},
    ),  # fmt: skip
    "V-B61 plazo alto": Caso(
        "V-B61",
        ERROR,
        "plazo_ip_s",
        validar(clon(esperar_ip=True, encender=True, plazo_ip_s=1801)),
        {"minimo": "10", "maximo": "1800"},
    ),  # fmt: skip
    "V-B62 plantilla sin agente": Caso(
        "V-B62",
        AVISO,
        "esperar_ip",
        validar(clon(esperar_ip=True, encender=True, plazo_ip_s=120)),
        {"origen": "plantilla"},
    ),  # fmt: skip
    "V-B63 9.2 sin GuestAgent.Audit": Caso(
        "V-B63",
        ERROR,
        "esperar_ip",
        validar(
            clon(esperar_ip=True, encender=True),
            inv_con_permisos(*(p for p in TODOS if p != "VM.GuestAgent.Audit")),
            CAPS_92,
        ),
        {"privilegio": "VM.GuestAgent.Audit"},
    ),  # fmt: skip
    "V-B63 8.x sin VM.Monitor": Caso(
        "V-B63",
        ERROR,
        "esperar_ip",
        validar(
            clon(esperar_ip=True, encender=True),
            inv_con_permisos(*(p for p in TODOS if p != "VM.Monitor")),
            CAPS_81,
        ),
        {"privilegio": "VM.Monitor"},
    ),  # fmt: skip
    "V-B64 nombre ubuntu": Caso(
        "V-B64",
        AVISO,
        "esperar_ip",
        validar(clon(esperar_ip=True, encender=True, plantilla="ubuntu-2204-base")),
        {},
    ),  # fmt: skip
    "V-B64 nombre debian": Caso(
        "V-B64",
        AVISO,
        "esperar_ip",
        validar(clon(esperar_ip=True, encender=True, plantilla="Debian12")),
        {},
    ),  # fmt: skip
    "V-B65 ciupgrade si con plazo corto": Caso(
        "V-B65",
        AVISO,
        "plazo_ip_s",
        validar(clon(ci_(actualizar=True), esperar_ip=True, encender=True, plazo_ip_s=60)),
        {"plazo_s": "60"},
    ),  # fmt: skip
    "V-B65 ciupgrade sin definir": Caso(
        "V-B65",
        AVISO,
        "plazo_ip_s",
        validar(clon(ci_(usuario="u"), esperar_ip=True, encender=True, plazo_ip_s=30)),
        {"plazo_s": "30"},
    ),  # fmt: skip
    "V-B65 ciupgrade heredado 1": Caso(
        "V-B65",
        AVISO,
        "plazo_ip_s",
        validar(
            clon(
                ci_(usuario="u"),
                dataclasses.replace(INFO_OK, heredados={"ciupgrade": "1"}),
                esperar_ip=True,
                encender=True,
                plazo_ip_s=45,
            )
        ),
        {"plazo_s": "45"},
    ),  # fmt: skip
}


def _codigo(p) -> str:
    return getattr(p, "codigo", None) or p.regla


def _textos(valor) -> str:
    """Todo lo que contienen los problemas, repr incluido (campo, código, params y más)."""
    return repr(valor)


@pytest.mark.parametrize("nombre", list(CASOS), ids=list(CASOS))
def test_ca_b14_1_cada_regla_se_provoca_con_su_severidad_campo_y_params(nombre):
    caso = CASOS[nombre]
    problemas = [p for p in caso.obtener() if _codigo(p) == caso.regla]
    assert problemas, f"{caso.regla} no se disparó"
    coincidentes = [
        p
        for p in problemas
        if p.severidad == caso.severidad
        and p.campo == caso.campo
        and all(p.params.get(k) == v for k, v in caso.params.items())
    ]
    assert coincidentes, (
        f"{caso.regla}: esperado {caso.severidad} {caso.campo} {caso.params}; hay {problemas}"
    )
    if caso.indice is not None:
        assert any(getattr(p, "indice", None) == caso.indice for p in coincidentes)


@pytest.mark.parametrize("nombre", list(CASOS), ids=list(CASOS))
def test_ca_b14_1_ningun_problema_lleva_secretos_ni_valores_de_claves(nombre):
    """Ni la contraseña, ni el cuerpo de una clave privada, ni el de una clave pública."""
    problemas = CASOS[nombre].obtener()
    texto = _textos(problemas)
    assert CENTINELA not in texto
    assert CUERPO_PRIVADO not in texto
    assert "AAAAC3NzaC1lZDI1NTE5" not in texto  # cuerpo de la clave pública de la tabla
    assert "PRIVATE KEY" not in texto
    for p in problemas:
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in p.params.items())


def test_ca_b14_1_la_tabla_cubre_cada_regla_de_este_archivo_al_menos_una_vez():
    esperadas = {
        *(f"V-B{n}" for n in (20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36)),
        *(f"V-B{n}" for n in (37, 38, 39, 50, 51, 52, 53, 54, 55, 56, 60, 61, 62, 63, 64, 65)),
    }
    assert {c.regla for c in CASOS.values()} == esperadas


# --- Lo que NO debe dispararse -------------------------------------------------------------------


def test_sin_cloudinit_ni_espera_de_ip_ninguna_regla_b_se_dispara_comportamiento_de_0_6_0():
    assert vb(cfg_base()) == []
    assert vb(clon(None)) == []
    assert vb(clon(ConfigCloudInit())) == []  # vacía = nada que enviar
    assert vb(cfg_base(), inv_con(None)) == []


def test_una_configuracion_completa_y_valida_no_da_ningun_problema():
    ci = ci_(
        usuario="deploy",
        claves=(CLAVE_OK,),
        tarjetas=(
            TarjetaCloudInit(0, FIJA, "10.0.0.50/24", puerta="10.0.0.1"),
            TarjetaCloudInit(1, DHCP),
        ),
        dns=("1.1.1.1", "8.8.8.8"),
        dominio="lab.local",
        actualizar=False,
        snippets=SnippetsCloudInit(vendor=SNIPPET_OK),
        activar_agente=True,
    )
    cfg = clon(ci, esperar_ip=True, encender=True, plazo_ip_s=120)
    assert vb(cfg) == []


@pytest.mark.parametrize("usuario", ["deploy", "_svc", "a", "ubuntu", "a-b_c9", "u" * 32])
def test_ca_b1_3_3_usuarios_con_el_patron_tipico_no_dan_problema(usuario):
    assert vb(clon(ci_(usuario=usuario))) == []


@pytest.mark.parametrize("usuario", ["1abc", "Root", "u" * 33, "ñandú", "a.b"])
def test_ca_b1_3_3_un_usuario_fuera_del_patron_tipico_es_solo_aviso(usuario):
    (p,) = vb(clon(ci_(usuario=usuario)))
    assert (p.codigo, p.severidad, p.params["motivo"]) == ("V-B21", AVISO, "patron")


def test_ca_b1_4_1_las_claves_validas_no_dan_problema():
    assert vb(clon(ci_(claves=(CLAVE_OK, CLAVE_OK.replace("ana", "bea"))))) == []


def test_v_b22_nombra_la_linea_sin_mostrarla_y_una_clave_valida_no_se_marca():
    cfg = clon(ci_(claves=(CLAVE_OK, "ssh-rsa", CLAVE_OK.replace("ana", "x"), "hola")))
    ps = [p for p in vb(cfg) if p.codigo == "V-B22"]
    assert [(p.params["linea"], p.params["motivo"]) for p in ps] == [
        ("2", "sin_cuerpo"),
        ("4", "tipo_desconocido"),
    ]
    assert "hola" not in repr(ps)


def test_v_b23_rechaza_todo_y_no_emite_ademas_otros_problemas_de_clave():
    ps = [
        p for p in vb(clon(ci_(claves=(CLAVE_OK, PRIVADA, "hola")))) if p.codigo.startswith("V-B2")
    ]
    assert [p.codigo for p in ps] == ["V-B23"]
    assert CUERPO_PRIVADO not in repr(ps)


@pytest.mark.parametrize(
    "modo",
    [ModoTarjeta.SIN_CONFIGURAR, DHCP],
    ids=lambda m: str(m),
)
def test_ca_b1_8_3_una_puerta_sin_ip_fija_es_v_b29_aunque_sea_lo_unico_que_trae_la_config(modo):
    cfg = clon(ci_(tarjetas=(TarjetaCloudInit(0, modo, puerta="10.0.0.1"),)))
    assert [p.campo for p in vb(cfg) if p.codigo == "V-B29"] == ["cloudinit.tarjetas[0].puerta"]


# --- V-B25 en detalle ----------------------------------------------------------------------------


def test_v_b25_dos_campos_vacios_son_sin_contrasena_y_no_hay_nada_que_validar():
    assert validar_contrasena("", "", INFO_OK) == []
    assert validar_contrasena("", "", None) == []


def test_v_b25_una_contrasena_valida_no_da_problema():
    for valor in ("S3cr3t-Prueba!", "contraseña-ñandú-🙂", "a%b&c+d=e", "x" * 128, "12345678"):
        assert validar_contrasena(valor, valor, INFO_OK) == [], valor


def test_v_b25_los_limites_de_longitud_son_8_y_128_y_ambos_son_error():
    # B1: menos de 8 caracteres dejó de ser un aviso.
    (corta,) = validar_contrasena("1234567", "1234567", INFO_OK)
    assert (corta.severidad, corta.params["motivo"]) == (ERROR, "corta")
    assert validar_contrasena("12345678", "12345678", INFO_OK) == []
    assert validar_contrasena("x" * 128, "x" * 128, INFO_OK) == []
    (p,) = validar_contrasena("x" * 129, "x" * 129, INFO_OK)
    assert (p.severidad, p.params["motivo"]) == (ERROR, "larga")


def test_v_b25_solo_la_repeticion_vacia_es_no_coincide_y_nunca_eco_del_valor():
    ps = validar_contrasena(CENTINELA, "", INFO_OK)
    assert [(p.severidad, p.params["motivo"]) for p in ps] == [(ERROR, "no_coincide")]
    assert CENTINELA not in repr(ps)


def test_v_b25_con_windows_es_error_aunque_la_contrasena_sea_perfecta():
    windows = InfoCloudInitPlantilla(unidad=True, ostype="win10", es_windows=True)
    ps = validar_contrasena(CENTINELA, CENTINELA, windows)
    assert [(p.severidad, p.params["motivo"]) for p in ps] == [(ERROR, "windows")]
    assert CENTINELA not in repr(ps)


def test_v_b25_sin_info_de_plantilla_no_se_asume_windows():
    assert validar_contrasena(CENTINELA, CENTINELA, None) == []


def test_v_b25_varios_motivos_se_acumulan_sin_repetir_el_valor():
    ps = validar_contrasena("a\nb", "otra", INFO_OK)
    assert {p.params["motivo"] for p in ps} >= {"no_coincide", "control", "corta"}
    assert "a\nb" not in repr(ps) and "otra" not in repr(ps)


# --- V-B20 por plantilla (CA-B1.11.1) y reglas sin servidor --------------------------------------


def test_ca_b1_11_1_dos_plantillas_solo_la_que_no_tiene_unidad_da_v_b20_y_se_nombra():
    con = clon(ci_(usuario="u"), INFO_OK, plantilla="con-unidad")
    sin = clon(ci_(usuario="u"), InfoCloudInitPlantilla(unidad=False), plantilla="sin-unidad")
    assert [p for p in vb(con) if p.codigo == "V-B20"] == []
    (p,) = [p for p in vb(sin) if p.codigo == "V-B20"]
    assert (p.severidad, p.params["plantilla"]) == (ERROR, "sin-unidad")


def test_ca_b1_11_2_una_fila_sin_cloudinit_no_se_valida_contra_la_unidad():
    sin_unidad = InfoCloudInitPlantilla(unidad=False)
    assert vb(clon(None, sin_unidad)) == []
    assert vb(clon(ConfigCloudInit(), sin_unidad)) == []


def test_cl_b11_una_lectura_incompleta_avisa_y_no_bloquea():
    ps = vb(clon(ci_(usuario="u"), None))  # info_cloudinit None = no se pudo leer
    (p,) = [p for p in ps if p.codigo == "V-B20"]
    assert (p.severidad, p.params["motivo"]) == (AVISO, "no_comprobable")


def test_v_b34_no_se_evalua_si_no_se_pudo_leer_la_plantilla():
    cfg = clon(ci_(tarjetas=(TarjetaCloudInit(5, DHCP),)), InfoCloudInitPlantilla(unidad=None))
    assert [p for p in vb(cfg) if p.codigo == "V-B34"] == []


def test_v_b34_una_tarjeta_sin_configurar_no_se_exige_que_exista():
    cfg = clon(ci_(tarjetas=(TarjetaCloudInit(7, ModoTarjeta.SIN_CONFIGURAR),)))
    assert [p for p in vb(cfg) if p.codigo == "V-B34"] == []


def test_v_b37_en_8x_basta_network_en_92_no_y_en_90_es_aviso():
    solo_red = inv_con_permisos(*BASE_B)
    ci = ci_(usuario="u")
    assert [p for p in vb(clon(ci), solo_red, CAPS_81) if p.codigo == "V-B37"] == []
    (p90,) = [p for p in vb(clon(ci), solo_red, CAPS_90) if p.codigo == "V-B37"]
    (p92,) = [p for p in vb(clon(ci), solo_red, CAPS_92) if p.codigo == "V-B37"]
    assert (p90.severidad, p92.severidad) == (AVISO, ERROR)


def test_v_b37_dns_y_dominio_solo_piden_network_incluso_en_92():
    solo_red = inv_con_permisos(*BASE_B)
    assert [
        p for p in vb(clon(ci_(dns=("1.1.1.1",), dominio="x.y")), solo_red) if p.codigo == "V-B37"
    ] == []


def test_v_b37_permisos_desconocidos_no_bloquean():
    inv = inv_con(catalogo(perm=None))
    assert [p for p in vb(clon(ci_(usuario="u")), inv) if p.codigo == "V-B37"] == []
    assert [p for p in vb(clon(esperar_ip=True, encender=True), inv) if p.codigo == "V-B63"] == []


def test_v_b63_sin_cloudinit_sigue_evaluandose_si_se_pide_esperar_la_ip():
    cfg = clon(None, INFO_OK, esperar_ip=True, encender=True)
    inv = inv_con_permisos(*(p for p in TODOS if p != "VM.GuestAgent.Audit"))
    assert [p.codigo for p in vb(cfg, inv, CAPS_92) if p.codigo == "V-B63"] == ["V-B63"]


# --- B3 en detalle -------------------------------------------------------------------------------


def _b3(info=INFO_OK, **cambios):
    base = {"esperar_ip": True, "encender": True, "plazo_ip_s": 120}
    base.update(cambios)
    return clon(ci_(usuario="u", actualizar=False), info, **base)


@pytest.mark.parametrize("plazo", [10, 11, 120, 1799, 1800])
def test_v_b61_los_plazos_validos_incluidos_los_limites(plazo):
    assert [p for p in vb(_b3(plazo_ip_s=plazo)) if p.codigo == "V-B61"] == []


@pytest.mark.parametrize("plazo", [0, 9, 1801, -5, "120", 1.5, True, None])
def test_v_b61_los_plazos_invalidos_no_son_enteros_en_rango(plazo):
    ps = [p for p in vb(_b3(plazo_ip_s=plazo)) if p.codigo == "V-B61"]
    assert len(ps) == 1 and ps[0].severidad == ERROR and ps[0].campo == "plazo_ip_s"


def test_v_b60_con_encender_no_da_error_y_sin_esperar_ip_nunca_se_evalua():
    assert [p for p in vb(_b3(encender=True)) if p.codigo == "V-B60"] == []
    assert vb(clon(None, INFO_OK, esperar_ip=False, encender=False, plazo_ip_s=1)) == []


def test_v_b62_no_avisa_si_la_plantilla_ya_tiene_agente_ni_si_se_va_a_activar():
    con_agente = dataclasses.replace(INFO_OK, agente=True)
    assert [p for p in vb(_b3(con_agente)) if p.codigo == "V-B62"] == []
    activa = clon(
        ci_(usuario="u", actualizar=False, activar_agente=True), esperar_ip=True, encender=True
    )
    assert [p for p in vb(activa) if p.codigo == "V-B62"] == []


def test_v_b64_no_avisa_con_otro_nombre_de_plantilla():
    assert [p for p in vb(_b3(plantilla="rocky-9")) if p.codigo == "V-B64"] == []


@pytest.mark.parametrize(
    ("plazo", "actualizar", "heredado", "avisa"),
    [
        (60, True, None, True),
        (10, True, None, True),
        (61, True, None, False),  # solo con plazo <= 60
        (60, False, None, False),
        (60, None, None, True),  # ciupgrade sin definir: Proxmox lo trata como «sí» (§10)
        (60, None, "1", True),
        (60, None, "true", True),
        (60, None, "0", False),
        (60, None, "false", False),
        (120, None, None, False),
        (60, None, "", False),
    ],
)
def test_ca_b1_10_3_v_b65_avisa_con_ciupgrade_activo_heredado_o_sin_definir(
    plazo, actualizar, heredado, avisa
):
    info = dataclasses.replace(
        INFO_OK, heredados={} if heredado is None else {"ciupgrade": heredado}
    )
    cfg = clon(
        ci_(usuario="u", actualizar=actualizar),
        info,
        esperar_ip=True,
        encender=True,
        plazo_ip_s=plazo,
    )
    ps = [p for p in vb(cfg) if p.codigo == "V-B65"]
    assert bool(ps) is avisa
    assert all(p.severidad == AVISO for p in ps)


def test_v_b65_sin_esperar_ip_nunca_avisa():
    cfg = clon(ci_(actualizar=True), esperar_ip=False, plazo_ip_s=10)
    assert [p for p in vb(cfg) if p.codigo == "V-B65"] == []


# --- V-B53 / V-B54 / V-B50 en detalle ------------------------------------------------------------


def test_ca_b4_4_3_vendor_con_claves_no_avisa_del_reemplazo():
    cfg = clon(ci_(claves=(CLAVE_OK,), usuario="u", snippets=SnippetsCloudInit(vendor=SNIPPET_OK)))
    assert [p for p in vb(cfg) if p.codigo == "V-B53"] == []


def test_v_b53_user_ninguno_no_es_elegir_un_snippet_de_usuario():
    cfg = clon(ci_(usuario="u", snippets=SnippetsCloudInit(user=NINGUNO)))
    assert [p for p in vb(cfg) if p.codigo == "V-B53"] == []


def test_ca_b4_3_1_v_b54_un_volid_correcto_es_valido_y_ninguno_no_se_valida_como_volid():
    ok = ci_(snippets=SnippetsCloudInit(user="local:snippets/a.yaml", meta=NINGUNO))
    assert [p for p in vb(clon(ok)) if p.codigo == "V-B54"] == []


@pytest.mark.parametrize(
    "volid",
    [
        "local:iso/a.iso",
        "snippets/a.yaml",
        "local:snippets/../x",
        "local:snippets/a,b",
        "local:snippets/a b",
        "local:snippets/",
        "local:snippets/a=b",
        ":snippets/a.yaml",
        "local:snippets/sub/a.yaml",
        "local:snippets/a\n.yaml",
    ],
)
def test_ca_b4_3_1_v_b54_volids_no_validos(volid):
    ps = [p for p in vb(clon(ci_(snippets=SnippetsCloudInit(user=volid)))) if p.codigo == "V-B54"]
    assert len(ps) == 1 and ps[0].severidad == ERROR


def test_v_b50_se_evalua_solo_si_se_conocen_los_almacenamientos_del_nodo():
    ci = ci_(snippets=SnippetsCloudInit(vendor=SNIPPET_OK))
    sin_datos = inv_con_permisos(*TODOS, storages={})
    assert [p for p in vb(clon(ci), sin_datos) if p.codigo == "V-B50"] == []


def test_v_b50_un_almacenamiento_inactivo_con_snippets_no_cuenta():
    inactivo = Storage("local", "dir", frozenset({"snippets"}), False, False, 1, 1)
    inv = inv_con_permisos(*TODOS, storages={"pve1": (inactivo,)})
    ci = ci_(snippets=SnippetsCloudInit(vendor=SNIPPET_OK))
    assert [p.severidad for p in vb(clon(ci), inv) if p.codigo == "V-B50"] == [ERROR]


# --- V-B51 / V-B52 en detalle (CA-B4.4.1) --------------------------------------------------------


def _codigos(problemas, regla):
    return [p for p in problemas if p.regla == regla]


def test_ca_b4_4_1_tres_snippets_de_1_mib_son_3_mib_exactos_y_se_aceptan():
    tam = {V_USER: MIB, V_VENDOR: MIB, "local:snippets/n.yaml": MIB}
    ps = plan_con_snippets(
        V_USER, tam, user=V_USER, vendor=V_VENDOR, network="local:snippets/n.yaml"
    )
    assert _codigos(ps, "V-B52") == [] and _codigos(ps, "V-B51") == []


def test_ca_b4_4_1_tres_snippets_de_1_2_mib_fallan_por_tamano_individual():
    grande = int(1.2 * MIB)
    tam = {V_USER: grande, V_VENDOR: grande, "local:snippets/n.yaml": grande}
    ps = plan_con_snippets(
        V_USER, tam, user=V_USER, vendor=V_VENDOR, network="local:snippets/n.yaml"
    )
    individuales = [p for p in _codigos(ps, "V-B52") if p.params["motivo"] == "individual"]
    assert {p.params["tipo"] for p in individuales} == {"user", "vendor", "network"}


def test_ca_b4_4_1_un_snippet_de_exactamente_1_mib_se_acepta_y_uno_de_un_byte_mas_no():
    assert _codigos(plan_con_snippets(V_USER, {V_USER: MIB}, user=V_USER), "V-B52") == []
    ps = plan_con_snippets(V_USER, {V_USER: MIB + 1}, user=V_USER)
    assert [p.params["motivo"] for p in _codigos(ps, "V-B52")] == ["individual"]


def test_ca_b4_4_1_la_suma_de_mas_de_3_mib_falla_aunque_cada_uno_pase():
    tam = {V_USER: MIB, V_VENDOR: MIB, "local:snippets/n.yaml": MIB, "local:snippets/m.yaml": 1}
    ps = plan_con_snippets(
        V_USER,
        tam,
        user=V_USER,
        vendor=V_VENDOR,
        network="local:snippets/n.yaml",
        meta="local:snippets/m.yaml",
    )
    assert [p.params["motivo"] for p in _codigos(ps, "V-B52")] == ["suma"]


def test_v_b51_si_el_snippet_existe_en_el_nodo_no_hay_problema():
    assert _codigos(plan_con_snippets(V_USER, {V_USER: 10}, user=V_USER), "V-B51") == []


def test_v_b51_sin_listado_no_se_juzga_la_existencia():
    """Entrada manual (RF-B4.3): el listado no está disponible y el formulario solo avisa."""
    sn = Storage("local", "dir", frozenset({"snippets"}), False, True, 10**12, 10**12)
    inv = inv_origen(
        nodos=("pve1",),
        plantillas=(plantilla_pve(9000, "base", "pve1"),),
        extra_storages={"pve1": (sn,)},
    )
    cfg = cfg_clon("base", 9000, "pve1", cloudinit=ci_(snippets=SnippetsCloudInit(user=V_USER)))
    plan = construir_plan(
        definicion(1, plantilla_vm=cfg), inv, [100], [], id_lote="a", ahora=0.0,
        version_validacion=(9, 2), vms_visibles=None,
    )  # fmt: skip
    assert _codigos(plan.problemas, "V-B51") == []


# --- Reglas con y sin servidor -------------------------------------------------------------------


def test_los_codigos_sin_servidor_son_los_de_la_arquitectura():
    assert set(CODIGOS_CLOUDINIT_SIN_SERVIDOR) == {
        f"V-B{n}" for n in (21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 36, 38, 39, 54)
    }
    assert set(CODIGOS_ESPERA_IP_SIN_SERVIDOR) == {"V-B60", "V-B61", "V-B64", "V-B65"}


def test_la_capa_1_solo_emite_reglas_de_contenido_y_nunca_las_que_piden_servidor():
    cfg = clon(
        ci_(
            usuario="mal usuario",
            tarjetas=(TarjetaCloudInit(5, FIJA, "10.0.0.5"),),
            snippets=SnippetsCloudInit(vendor=SNIPPET_OK),
        ),
        InfoCloudInitPlantilla(unidad=False, es_windows=True, ostype="win10"),
        esperar_ip=True,
        encender=False,
        plazo_ip_s=5,
    )
    emitidos = {p.codigo for p in validar_sin_servidor(cfg) if p.codigo.startswith("V-B")}
    permitidos = set(CODIGOS_CLOUDINIT_SIN_SERVIDOR) | set(CODIGOS_ESPERA_IP_SIN_SERVIDOR)
    assert emitidos and emitidos <= permitidos
    assert {"V-B21", "V-B26", "V-B60", "V-B61"} <= emitidos
    # V-B20, V-B34, V-B35, V-B37, V-B50, V-B55, V-B56, V-B62 y V-B63 miran el servidor.
    assert not emitidos & {
        "V-B20",
        "V-B34",
        "V-B35",
        "V-B37",
        "V-B50",
        "V-B55",
        "V-B56",
        "V-B62",
        "V-B63",
    }


def test_la_capa_1_con_una_configuracion_valida_no_da_reglas_b():
    cfg = clon(ci_(usuario="deploy", dns=("1.1.1.1",)))
    assert [p for p in validar_sin_servidor(cfg) if p.codigo.startswith("V-B")] == []


# --- Los mensajes nombran la causa: campo siempre presente ---------------------------------------


def test_rnf_b8_todas_las_reglas_de_la_tabla_llevan_campo_y_codigo():
    for nombre, caso in CASOS.items():
        for p in caso.obtener():
            assert getattr(p, "campo", None), (nombre, p)
            assert _codigo(p).startswith("V-"), (nombre, p)
