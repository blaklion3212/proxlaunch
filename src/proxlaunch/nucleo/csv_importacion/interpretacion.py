"""Interpretación y validación fila a fila del CSV (RF-C04..C07, RF-C13).

``interpretar`` es una función pura sobre ``(tabla, perfil base, perfiles, inventario o None)``:
mismo archivo y entorno, mismos resultados (CA-C05.8). Precedencia (CA-C13.5), de menor a
mayor: valores por defecto de M1 -> perfil base o perfil de la fila -> columnas del CSV.

Capa 1 (sin servidor) siempre; capa 2 de vista previa solo con inventario. Los problemas de
celda son ``ProblemaCelda`` (código y parámetros, nunca texto de interfaz). Las columnas de
credenciales y las desconocidas no se leen jamás. Un problema de la tabla completa lanza
``ErrorProxLaunch`` (E-M10).

Fase B (DT-B13): la columna ``ci_contrasena`` es la única credencial admitida. Su celda se valida
con ``validar_contrasena`` ANTES de crear el ``Secreto``; en ``originales`` y en ``valor`` de los
problemas se sustituye por ``MASCARA``, y nunca entra en los ``params`` de un problema.
"""

import copy
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from proxlaunch.nucleo.archivos.constantes import (
    MAX_LONG_CLAVES,
    MAX_LONG_NOTAS,
    MAX_LONG_TEXTO,
    MAX_PROBLEMAS_FILA,
    MEMORIA_AVISO_GIB,
)
from proxlaunch.nucleo.archivos.csv_seguro import DISPARADORES
from proxlaunch.nucleo.archivos.esquema import AvisoArchivo, CodigoAvisoArchivo
from proxlaunch.nucleo.archivos.texto import (
    MOTIVO_LONGITUD,
    analizar_texto,
    clave_comparacion,
    contiene_token,
    texto_seguro,
)
from proxlaunch.nucleo.arquitectura.modelos import Arquitectura, arquitectura_efectiva
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.cloudinit.claves import MotivoClave, analizar_claves, contiene_clave_privada
from proxlaunch.nucleo.cloudinit.modelos import (
    NINGUNO,
    CloudInitParcial,
    ModoTarjeta,
    SnippetsCloudInit,
    TarjetaCloudInit,
    combinar,
)
from proxlaunch.nucleo.cloudinit.red import normalizar_dns
from proxlaunch.nucleo.cloudinit.validacion import validar_contrasena
from proxlaunch.nucleo.csv_importacion import unidades
from proxlaunch.nucleo.csv_importacion.columnas import (
    COLUMNA_CONTRASENA,
    MAX_DISCOS_CSV,
    normalizar_encabezado,
    resolver_columnas,
)
from proxlaunch.nucleo.csv_importacion.modelos import (
    EstadoFila,
    FilaCsv,
    FilaInterpretada,
    MapaColumnas,
    ProblemaCelda,
    ResultadoImportacion,
    TablaCsv,
)
from proxlaunch.nucleo.csv_importacion.saneado import sin_control, texto_visible
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.firewall.modelos import RE_GRUPO, FirewallParcial, Politica
from proxlaunch.nucleo.hardware_cluster.modelos import (
    MAX_PCI,
    MAX_USB,
    RE_ID_MAPEO,
    AsignacionPCI,
    AsignacionUSB,
    HardwareCluster,
)
from proxlaunch.nucleo.lote.modelos import Destino, FilaLote
from proxlaunch.nucleo.lote.reparto import nodos_elegibles
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.cpu import es_cpu_solo_x86
from proxlaunch.nucleo.modelos.inventario import Inventario
from proxlaunch.nucleo.modelos.origen import (
    AjustesClon,
    DetalleClon,
    DetalleImportacion,
    DetalleIso,
    RefPlantilla,
    RefVolumen,
)
from proxlaunch.nucleo.modelos.vm import (
    ConfiguracionVM,
    Disco,
    Firmware,
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.opciones.etiquetas import normalizar_etiquetas
from proxlaunch.nucleo.opciones.modelos import OpcionesParciales
from proxlaunch.nucleo.opciones.notas import limpiar_texto_libre
from proxlaunch.nucleo.origen.asistente import aplicar_asistente
from proxlaunch.nucleo.origen.nombres import (
    es_ruta_absoluta,
    parece_url,
    parece_url_o_credenciales,
    validar_nombre_archivo,
    validar_volid,
)
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.perfiles_maquina.aplicar import AvisoPista, aplicar_config
from proxlaunch.nucleo.perfiles_maquina.modelos import PerfilMaquina
from proxlaunch.nucleo.red.modelos import AccionTarjeta, CampoRed, ModoRedClon, RedClon, TarjetaClon
from proxlaunch.nucleo.secreto import MASCARA, Secreto
from proxlaunch.nucleo.transferencias.url import url_saneada
from proxlaunch.nucleo.validacion import (
    VMID_MIN,
    Problema,
    Severidad,
    validar_sin_servidor,
    validar_vm,
)
from proxlaunch.nucleo.valores_defecto import (
    bridge_por_defecto,
    disco_por_defecto,
    storage_por_defecto,
)

PREFIJO_EJEMPLO = "ejemplo-"  # V-M11
MAX_DISPONIBLES = 5  # perfiles que se listan en V-M06
MAX_NODOS_MOTIVOS = 5  # nodos que se detallan en V-L11

# Reglas de capa 2 que la vista previa evalúa con el servidor (nodo fijo).
_CAPA2 = frozenset({"V-04", "V-09", "V-16", "V-16.sinredes", "V-17"})

_REGLA_NO_ADMITIDO = "E-M11.valor_no_admitido"

# Fase B: columnas de snippets (columna -> tipo de ``SnippetsCloudInit``) y columnas de texto cuyo
# valor no se conserva si trae un token (INV-M2).
_COLUMNAS_SNIPPET = (
    ("ci_snippet_usuario", "user"),
    ("ci_snippet_vendor", "vendor"),
    ("ci_snippet_red", "network"),
    ("ci_snippet_meta", "meta"),
)
_SNIPPET_A_COLUMNA = {tipo: columna for columna, tipo in _COLUMNAS_SNIPPET}
TEXTOS_SIN_TOKEN = frozenset(
    {
        "pool",
        "ci_usuario",
        "ci_dominio",
        "ci_ip",
        "ci_puerta",
        "ci_dns",
        "grupo_seguridad",
        "mapeo_pci",
        "mapeo_usb",
        *(columna for columna, _tipo in _COLUMNAS_SNIPPET),
    }
)
_SEPARADORES_DNS = re.compile(r"[\s,;]+")
_SEPARADOR_MAPEOS = ";"  # fase D: separador de los ids de ``mapeo_pci`` y ``mapeo_usb``


@dataclass
class _Borrador:
    """Fila en construcción (los problemas se completan con V-M10 antes de congelarla)."""

    fila: FilaCsv
    nombre: str = ""
    perfil: str | None = None
    vmid: int | None = None
    nodo: str | None = None
    cfg: ConfiguracionVM | None = None
    problemas: list[tuple[int, ProblemaCelda]] = field(default_factory=list)
    originales: dict[str, str] = field(default_factory=dict)
    sin_cfg: bool = False  # un error de la fila impide construir la configuración
    opciones: OpcionesParciales | None = None  # fase A: celdas fijadas (None = hereda todo)


# --- Utilidades ---------------------------------------------------------------------------


def _nombre_columna_disco(k: int) -> str:
    return "disco" if k == 0 else f"disco{k + 1}"


def _nombre_columna_almacenamiento(k: int) -> str:
    return "almacenamiento" if k == 0 else f"almacenamiento{k + 1}"


def _columna_de_campo(campo: str) -> str | None:
    """Columna canónica del CSV que origina un campo de ``ConfiguracionVM`` (o ``None``)."""
    fijos = {
        "nombre": "nombre",
        "vmid": "vmid",
        "nodo": "nodo",
        "sockets": "sockets",
        "cores": "cpu",
        "memoria_mib": "memoria",
        "ballooning.minimo_mib": "memoria",
        "tipo_cpu": "tipo_cpu",
        "firmware": "firmware",
        "discos": "disco",
        "storage_efi": "almacenamiento",
        # Fase A: campos de ``ConfiguracionVM`` y de ``OpcionA`` (V-A12) que tienen columna.
        "notas": "notas",
        "etiquetas": "etiquetas",
        "pool": "pool",
        "encender": "encender",
        "arranque_auto": "arranque_auto",
        "proteger": "proteger",
        "mtu": "mtu",
        "limite_red": "limite_red",
        "esperar_ip": "esperar_ip",
    }
    if campo in fijos:
        return fijos[campo]
    if campo.startswith("cloudinit."):
        return _columna_de_cloudinit(campo[len("cloudinit.") :])
    if campo.startswith("etiquetas_usuario["):
        return "etiquetas"
    # Fase C: campos del firewall y de la red del clon (V-C) que tienen columna.
    if campo.startswith("firewall"):
        return {
            "grupo": "grupo_seguridad",
            "politica_entrada": "politica_entrada",
            "politica_salida": "politica_salida",
        }.get(campo.partition(".")[2], "cortafuegos")
    if campo.startswith("red_clon"):
        return "reescribir_red"
    # Fase D: mapeos PCI/USB (V-D5x de ``hardware_cluster.validacion``).
    if campo.startswith("hardware_cluster.pci"):
        return "mapeo_pci"
    if campo.startswith("hardware_cluster.usb"):
        return "mapeo_usb"
    # MVP 4: campos del origen del SO.
    if campo == "detalle_origen":
        return "origen"
    if campo in ("tipo_so", "firmware_so"):
        return "so"
    if campo.startswith(
        ("detalle_origen.iso", "detalle_origen.imagen", "detalle_origen.plantilla")
    ):
        return "fuente"
    if campo.startswith("detalle_origen.drivers"):
        return "virtio"
    if campo == "detalle_origen.modo":
        return "modo_clon"
    if campo in ("detalle_origen.ajustes.cores",):
        return "cpu"
    if campo == "detalle_origen.ajustes.sockets":
        return "sockets"
    if campo == "detalle_origen.ajustes.memoria_mib":
        return "memoria"
    if campo == "detalle_origen.ajustes.tipo_cpu":
        return "tipo_cpu"
    if campo in ("detalle_origen.ajustes.disco_gib", "detalle_origen.ampliar_a_gib"):
        return "disco"
    if campo.startswith("discos["):
        indice, _, resto = campo[len("discos[") :].partition("]")
        if indice.isdigit() and int(indice) < MAX_DISCOS_CSV:
            k = int(indice)
            if resto == ".storage":
                return _nombre_columna_almacenamiento(k)
            return _nombre_columna_disco(k)
    if campo.startswith("redes[0]."):
        return {
            "vlan": "vlan",
            "bridge": "red",
            "modelo": "modelo_red",
            "mtu": "mtu",
            "limite_mb": "limite_red",
        }.get(campo[9:])
    return None


def _columna_de_cloudinit(resto: str) -> str | None:
    """Columna del CSV de un campo ``cloudinit.<resto>`` de las reglas V-B (o ``None``)."""
    simples = {
        "usuario": "ci_usuario",
        "claves": "ci_claves",
        "contrasena": COLUMNA_CONTRASENA,
        "dns": "ci_dns",
        "dominio": "ci_dominio",
        "actualizar": "ci_actualizar",
    }
    if resto in simples:
        return simples[resto]
    if resto.startswith("tarjetas["):  # el CSV solo llega a la tarjeta 1 (net0)
        return "ci_puerta" if resto.endswith(".puerta") else "ci_ip"
    if resto.startswith("snippets."):
        return _SNIPPET_A_COLUMNA.get(resto.partition(".")[2])
    return None


def _orden(mapa: MapaColumnas, canonica: str | None) -> int:
    """Posición de la columna en el archivo (para ordenar); los de fila van primero."""
    return -1 if canonica is None else mapa.posiciones.get(canonica, -1)


class _Contexto:
    """Datos compartidos por todas las filas de una importación."""

    def __init__(
        self,
        mapa: MapaColumnas,
        perfil_base: PerfilMaquina,
        perfiles: Sequence[PerfilMaquina],
        inv: Inventario | None,
        nodo_referencia: str | None,
        encender_base: bool | None = None,
        hardware_base: HardwareCluster | None = None,
    ) -> None:
        self.mapa = mapa
        self.encender_base = encender_base
        self.hardware_base = hardware_base
        self.base = perfil_base
        self.inv = inv
        self.nodo_referencia = nodo_referencia
        self.avisos_unidad: dict[CodigoAvisoArchivo, set[str]] = {}
        todos: dict[str, PerfilMaquina] = {}
        for p in perfiles:
            todos.setdefault(p.id, p)
        self.perfiles = tuple(todos.values())
        self.por_id = {p.id.casefold(): p for p in self.perfiles}
        self.por_nombre: dict[str, list[PerfilMaquina]] = {}
        for p in self.perfiles:
            self.por_nombre.setdefault(clave_comparacion(p.nombre, sin_acentos=True), []).append(p)
        self.caps = capacidades_para(inv.version, None) if inv is not None else None
        self.memoria_maxima_mib = (
            max(
                (n.mem_libre_mib for n in inv.topologia.nodos if n.mem_libre_mib is not None),
                default=None,
            )
            if inv is not None
            else None
        )

    def es_arm(self, nodo: str) -> bool:
        """¿El nodo es ARM64 según el inventario? (sin inventario o sin detectar: no)."""
        return (
            self.inv is not None
            and bool(nodo)
            and arquitectura_efectiva(self.inv, nodo) == Arquitectura.AARCH64
        )

    def nodo_efectivo(self, nodo: str | None) -> str:
        """Nodo en el que se resuelven las pistas: el de la fila, el de referencia o el primero."""
        if nodo:
            return nodo
        if self.nodo_referencia:
            return self.nodo_referencia
        if self.inv is not None:
            for n in self.inv.topologia.nodos:
                if n.en_linea:
                    return n.nombre
        return ""

    def unidad_encabezado(self, canonica: str) -> str | None:
        """Unidad que fija el nombre de la columna (``memoria_mib`` -> ``mib``), si la hay."""
        titulo = self.mapa.encabezados.get(canonica)
        if titulo is None:
            return None
        final = normalizar_encabezado(titulo).rpartition("_")[2]
        return final if final in ("mib", "gib") else None

    def registrar_avisos(self, canonica: str, codigos: Collection[CodigoAvisoArchivo]) -> None:
        for c in codigos:
            self.avisos_unidad.setdefault(c, set()).add(canonica)

    def buscar_perfil(self, texto: str) -> tuple[PerfilMaquina | None, str]:
        """Perfil por nombre visible o id (sin mayúsculas ni acentos). ``(None, motivo)`` si no."""
        por_id = self.por_id.get(texto.casefold())
        if por_id is not None:
            return por_id, ""
        candidatos = self.por_nombre.get(clave_comparacion(texto, sin_acentos=True), [])
        if len(candidatos) == 1:
            return candidatos[0], ""
        return None, "ambiguo" if candidatos else "no_existe"

    def avisos_de_archivo(self) -> list[AvisoArchivo]:
        """Un aviso por columna y código (D-T9), en orden de columna y de código."""
        avisos: list[AvisoArchivo] = []
        for codigo in (
            CodigoAvisoArchivo.GIB_ASUMIDO,
            CodigoAvisoArchivo.GB_COMO_GIB,
            CodigoAvisoArchivo.DECIMAL_COMA,
        ):
            for canonica in sorted(
                self.avisos_unidad.get(codigo, ()), key=lambda c: self.mapa.posiciones[c]
            ):
                avisos.append(AvisoArchivo(codigo, {"columna": self.mapa.encabezados[canonica]}))
        return avisos


@dataclass(frozen=True)
class _CeldasRed:
    """Columnas de la tarjeta 1 ya leídas (``None`` = celda vacía o inválida)."""

    bridge: str | None
    vlan: int | None
    modelo: ModeloRed | None
    mtu_fijado: bool  # «heredar» también es una elección explícita (``mtu`` = ``None``)
    mtu: int | None
    limite: float | None


# --- Una fila -------------------------------------------------------------------------------


class _Fila:
    """Interpreta una fila. Agrupa el estado para no repartir parámetros entre funciones."""

    def __init__(self, ctx: _Contexto, fila: FilaCsv) -> None:
        self.ctx = ctx
        self.b = _Borrador(fila)
        self._ajustes: AjustesClon | None = None  # clon: ajustes leídos de las columnas
        self._ampliar: int | None = None  # importación: columna ``disco`` = ampliar a
        self._red_clon: RedClon | None = None  # fase C: ``reescribir_red`` de la fila
        self._arm = False  # fase D: ¿el nodo efectivo de la fila es ARM64? (RF-D2.7)

    # -- lectura de celdas (solo columnas conocidas y no credenciales) --

    def celda(self, canonica: str) -> str:
        pos = self.ctx.mapa.posiciones.get(canonica)
        if pos is None or pos >= len(self.b.fila.celdas):
            return ""
        texto = self.b.fila.celdas[pos].strip()
        # CA-C11.5: una «'» inicial seguida de un disparador viene de una exportación anterior.
        if len(texto) > 1 and texto[0] == "'" and texto[1] in DISPARADORES:
            texto = texto[1:]
        return texto

    def problema(
        self,
        canonica: str | None,
        regla: str,
        severidad: Severidad,
        params: Mapping[str, str] | None = None,
        valor: str = "",
    ) -> None:
        mapa = self.ctx.mapa
        columna = mapa.encabezados.get(canonica) if canonica else None
        if canonica is not None and not valor:
            valor = self.celda(canonica)
        if canonica == "fuente" and parece_url_o_credenciales(valor):
            valor = url_saneada(valor)  # INV-O6: la URL con credenciales no se conserva
        if canonica == COLUMNA_CONTRASENA:
            valor = MASCARA  # DT-B13: la contraseña nunca se muestra, ni en un error
        elif canonica == "ci_claves":
            valor = ""  # puede traer una clave privada pegada por error: no se conserva
        elif canonica in TEXTOS_SIN_TOKEN and contiene_token(valor):
            valor = ""  # un token en el pool o en cloud-init tampoco se conserva
        if canonica == "notas" and (regla == _REGLA_NO_ADMITIDO or contiene_token(valor)):
            # RNF-A2: un token en las notas no se conserva en el resultado; y una celda de
            # notas con error tampoco muestra su valor (pudo traer un token disfrazado).
            valor = ""
        self.b.problemas.append(
            (
                _orden(mapa, canonica),
                ProblemaCelda(
                    fila=self.b.fila.numero,
                    columna=columna,
                    regla=regla,
                    severidad=severidad,
                    params=dict(params or {}),
                    valor=texto_visible(valor),
                ),
            )
        )

    def error_valor(self, canonica: str, e: unidades.ValorInvalido) -> None:
        self.b.sin_cfg = True
        self.problema(canonica, e.regla, Severidad.ERROR, e.params)

    def texto(self, canonica: str) -> str | None:
        """Texto libre de la celda validado (V-M04). ``None`` si está vacía o no es válido."""
        crudo = self.celda(canonica)
        if not crudo:
            return None
        seguro = texto_seguro(crudo, maximo=MAX_LONG_TEXTO)
        if seguro is None:
            self.b.sin_cfg = True
            self.problema(canonica, _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": "texto"})
        return seguro

    def booleano(self, canonica: str) -> bool | None:
        """Casilla de la celda (``si``/``no``...). ``None`` si está vacía (hereda) o es inválida."""
        crudo = self.celda(canonica)
        if not crudo:
            return None
        try:
            return unidades.si_no(crudo)
        except unidades.ValorInvalido as e:
            self.error_valor(canonica, e)
            return None

    def entero(self, canonica: str) -> int | None:
        crudo = self.celda(canonica)
        if not crudo:
            return None
        try:
            return unidades.entero(crudo)
        except unidades.ValorInvalido as e:
            self.error_valor(canonica, e)
            return None

    # -- construcción --

    def interpretar(self) -> _Borrador:
        ctx, b = self.ctx, self.b
        b.nombre = sin_control(self.celda("nombre"))
        nombre_crudo = self.celda("nombre")
        if not nombre_crudo:
            self.problema("nombre", "V-M07", Severidad.ERROR)
        elif b.nombre.casefold().startswith(PREFIJO_EJEMPLO):
            self.problema("nombre", "V-M11", Severidad.AVISO)

        perfil = self._perfil()
        b.nodo = self.texto("nodo")
        b.vmid = self.entero("vmid")
        nodo_ef = ctx.nodo_efectivo(b.nodo)
        self._arm = ctx.es_arm(nodo_ef)
        actual = ConfiguracionVM(
            vmid=b.vmid if b.vmid is not None else VMID_MIN, nombre=nombre_crudo, nodo=nodo_ef
        )
        resultado = aplicar_config(perfil.config, actual, ctx.inv)
        cfg = resultado.cfg
        cfg.nombre = nombre_crudo
        cfg.etiquetas = ()

        self._origen(cfg)
        cfg = self._asistente(cfg)
        clon = cfg.origen == OrigenSO.CLONAR_PLANTILLA
        if clon:
            self._ajustes_clon(cfg)
        else:
            cpu = self.entero("cpu")
            if cpu is not None:
                cfg.cores = cpu
            sockets = self.entero("sockets")
            if sockets is not None:
                cfg.sockets = sockets
            self._memoria(cfg)
        self._firmware_y_cpu(cfg, aplicar_tipo_cpu=not clon)
        reescribir = self.booleano("reescribir_red")
        if not clon:
            self._discos(cfg, nodo_ef)
            self._red(cfg, nodo_ef)
        self._reescribir_red(reescribir, clon)
        self._hardware(cfg)
        self._detalle_origen(cfg)
        b.opciones = self._opciones(cfg, perfil)
        self._pistas(resultado.avisos, perfil)

        # Capa 1 (V-01 solo con nombre; V-02 con el VMID explícito o uno válido de relleno).
        cfg.vmid = b.vmid if b.vmid is not None else VMID_MIN
        for p in validar_sin_servidor(cfg, incluir_nombre=bool(nombre_crudo), incluir_vmid=True):
            self._de_validacion(p)
        self._memoria_desmesurada(cfg)
        # Capa 2 (solo con inventario y si la configuración se pudo construir).
        if ctx.inv is not None and not b.sin_cfg:
            self._capa2(cfg)
        cfg.cloudinit = None  # la fuente de cloud-init de la fila es ``b.opciones.cloudinit``

        cfg.vmid = b.vmid if b.vmid is not None else 0
        cfg.nodo = b.nodo or ""
        b.cfg = None if b.sin_cfg else cfg
        for canonica, pos in ctx.mapa.posiciones.items():
            if pos < len(b.fila.celdas):
                bruta = b.fila.celdas[pos]
                original = sin_control(bruta).strip()
                if canonica == COLUMNA_CONTRASENA:
                    if bruta.strip():
                        b.originales[canonica] = MASCARA  # DT-B13: nunca el texto
                    continue
                if canonica == "ci_claves" and contiene_clave_privada(bruta):
                    continue  # una clave privada pegada por error no se conserva
                if original:
                    if canonica == "fuente" and parece_url_o_credenciales(original):
                        original = url_saneada(original)  # INV-O6
                    if canonica in ("notas", *TEXTOS_SIN_TOKEN) and contiene_token(bruta):
                        continue  # RNF-A2: un token en las notas, el pool o cloud-init
                    b.originales[canonica] = original
        return b

    def _perfil(self) -> PerfilMaquina:
        """Perfil de la fila (V-M06 si no existe: se diagnostica con el base, sin usarlo)."""
        ctx, b = self.ctx, self.b
        texto = self.celda("perfil")
        if not texto:
            return ctx.base
        encontrado, motivo = ctx.buscar_perfil(texto)
        if encontrado is None:
            b.sin_cfg = True
            b.perfil = texto_visible(texto)
            disponibles = ", ".join(texto_visible(p.nombre) for p in ctx.perfiles[:MAX_DISPONIBLES])
            self.problema(
                "perfil",
                "V-M06",
                Severidad.ERROR,
                {"nombre": texto_visible(texto), "disponibles": disponibles, "motivo": motivo},
            )
            return ctx.base
        b.perfil = encontrado.nombre
        return encontrado

    def _memoria(self, cfg: ConfiguracionVM) -> None:
        crudo = self.celda("memoria")
        if not crudo:
            return
        try:
            mib, avisos = unidades.memoria_mib(crudo, self.ctx.unidad_encabezado("memoria"))
        except unidades.ValorInvalido as e:
            self.error_valor("memoria", e)
            return
        cfg.memoria_mib = mib
        self.ctx.registrar_avisos("memoria", avisos)

    def _firmware_y_cpu(self, cfg: ConfiguracionVM, *, aplicar_tipo_cpu: bool = True) -> None:
        arm = self._arm
        crudo = self.celda("firmware")
        if crudo:
            try:
                cfg.firmware = unidades.firmware(crudo)
            except unidades.ValorInvalido as e:
                self.error_valor("firmware", e)
            else:
                if arm and cfg.firmware == Firmware.SEABIOS:
                    self._incompatible_arm("firmware", "firmware", "ovmf")
        tipo = self.texto("tipo_cpu")
        if tipo is not None and arm and es_cpu_solo_x86(tipo):
            # Aplica también al clonar: el tipo de CPU va en los ajustes de la copia.
            self._incompatible_arm("tipo_cpu", "cpu", "host")
        if tipo is not None and aplicar_tipo_cpu:
            cfg.tipo_cpu = tipo

    def _modelo_red_arm(self, modelo: ModeloRed | None) -> None:
        """V-D09 si la celda ``modelo_red`` pide ``e1000`` en un nodo ARM64 (solo ``virtio``)."""
        if self._arm and modelo == ModeloRed.E1000:
            self._incompatible_arm("modelo_red", "red", "virtio")

    def _incompatible_arm(
        self, canonica: str, motivo: str, alternativa: str, opcion: str | None = None
    ) -> None:
        """V-D09: una celda EXPLÍCITA de la fila no existe en el nodo ARM64 (RF-D2.7, CA-D6.3.9).

        ``opcion`` es lo que se muestra como «opción» (por defecto, el texto de la celda). Lo
        heredado del formulario o del perfil no pasa por aquí: se adapta (V-D08)."""
        self.problema(
            canonica,
            "V-D09",
            Severidad.ERROR,
            {
                "opcion": opcion if opcion is not None else texto_visible(self.celda(canonica)),
                "motivo": motivo,
                "alternativa": alternativa,
            },
        )

    # -- hardware del clúster de la fase D (RF-D6.3) --

    def _ids_mapeo(self, canonica: str, maximo: int, tipo: str) -> tuple[str, ...] | None:
        """Ids de una celda ``mapeo_pci``/``mapeo_usb`` separados por «;».

        ``None`` = celda vacía (hereda del formulario) o con un error ya anotado: V-D70 por un id
        no válido y V-D59 por pasar del máximo de dispositivos. Ambos marcan la fila (``sin_cfg``)
        sin impedir que se lean las demás celdas."""
        crudo = self.celda(canonica)
        ids = tuple(t.strip() for t in crudo.split(_SEPARADOR_MAPEOS) if t.strip())
        if not ids:
            return None
        if any(RE_ID_MAPEO.fullmatch(i) is None for i in ids):
            self.b.sin_cfg = True
            self.problema(canonica, "V-D70", Severidad.ERROR, {"motivo": "id_invalido"})
            return None
        if len(ids) > maximo:
            self.b.sin_cfg = True
            self.problema(
                canonica,
                "V-D59",
                Severidad.ERROR,
                {"tipo": tipo, "maximo": str(maximo), "cantidad": str(len(ids))},
            )
            return None
        return ids

    def _hardware(self, cfg: ConfiguracionVM) -> None:
        """Mapeos PCI/USB de la fila: manda la celda con ids y, vacía, hereda los del formulario.

        Cada id lleva las opciones (``pcie``, ``x_vga``…) que el formulario ya le dio (``base``);
        un id nuevo, las de por defecto. ``cfg.hardware_cluster`` queda con el valor efectivo
        (``None`` si no hay ninguno): las filas no tienen otro sitio donde heredarlo."""
        base = self.ctx.hardware_base or HardwareCluster()
        ids_pci = self._ids_mapeo("mapeo_pci", MAX_PCI, "pci")
        ids_usb = self._ids_mapeo("mapeo_usb", MAX_USB, "usb")
        pci = base.pci
        usb = base.usb
        if ids_pci is not None:
            previas = {a.mapeo: a for a in reversed(base.pci)}
            pci = tuple(previas.get(i) or AsignacionPCI(mapeo=i) for i in ids_pci)
            if self._arm and any(a.pcie for a in pci):
                self._incompatible_arm("mapeo_pci", "pcie", "", opcion="pcie")
        if ids_usb is not None:
            previas_usb = {a.mapeo: a for a in reversed(base.usb)}
            usb = tuple(previas_usb.get(i) or AsignacionUSB(mapeo=i) for i in ids_usb)
        hw = HardwareCluster(pci=pci, usb=usb)
        cfg.hardware_cluster = None if hw.vacio else hw

    # -- origen del SO (MVP 4, RF-O28) --

    def _origen(self, cfg: ConfiguracionVM) -> None:
        """Columna ``origen``: gana sobre el origen sugerido del perfil (CA-O28.5)."""
        crudo = self.celda("origen")
        if not crudo:
            return
        try:
            nuevo = unidades.origen(crudo)
        except unidades.ValorInvalido as e:
            self.error_valor("origen", e)
            return
        if nuevo != cfg.origen:
            cfg.origen = nuevo
            cfg.detalle_origen = None  # el detalle del perfil era de otro origen
            if nuevo in (OrigenSO.DISCO_VACIO, OrigenSO.CLONAR_PLANTILLA):
                cfg.tipo_so, cfg.tpm, cfg.agente_qemu = None, False, False

    def _asistente(self, cfg: ConfiguracionVM) -> ConfiguracionVM:
        """Columna ``so``: fija el tipo y aplica el asistente (antes de las columnas de hardware,
        que por eso siguen ganando)."""
        crudo = self.celda("so")
        if not crudo:
            return cfg
        try:
            tipo = unidades.tipo_so(crudo)
        except unidades.ValorInvalido as e:
            self.error_valor("so", e)
            return cfg
        if cfg.origen in (OrigenSO.ISO, OrigenSO.IMPORTAR_DISCO):
            return aplicar_asistente(cfg, tipo).cfg
        cfg.tipo_so = tipo  # origen ajeno: V-O01.ajeno lo avisará
        return cfg

    def _ajustes_clon(self, cfg: ConfiguracionVM) -> None:
        """En un clon ``cpu``, ``memoria``, ``disco`` y ``tipo_cpu`` son ajustes (CA-O22.1)."""
        sockets, cores = self.entero("sockets"), self.entero("cpu")
        memoria: int | None = None
        disco: int | None = None
        crudo = self.celda("memoria")
        if crudo:
            try:
                memoria, avisos = unidades.memoria_mib(crudo, self.ctx.unidad_encabezado("memoria"))
                self.ctx.registrar_avisos("memoria", avisos)
            except unidades.ValorInvalido as e:
                self.error_valor("memoria", e)
        crudo = self.celda("disco")
        if crudo:
            try:
                disco, avisos = unidades.disco_gib(crudo, self.ctx.unidad_encabezado("disco"))
                self.ctx.registrar_avisos("disco", avisos)
            except unidades.ValorInvalido as e:
                self.error_valor("disco", e)
        previo = (
            cfg.detalle_origen if isinstance(cfg.detalle_origen, DetalleClon) else DetalleClon()
        )
        base = previo.ajustes
        self._ajustes = AjustesClon(
            sockets if sockets is not None else base.sockets,
            cores if cores is not None else base.cores,
            self.texto("tipo_cpu") or base.tipo_cpu,
            memoria if memoria is not None else base.memoria_mib,
            disco if disco is not None else base.disco_gib,
        )

    def _ref_fuente(self, crudo: str, contenido: Contenido) -> RefVolumen | None:
        """``fuente`` de ISO o imagen: volid (con ``:``) o nombre; URL y rutas se rechazan."""
        regla = "V-O02" if contenido == Contenido.ISO else "V-O03"
        motivo: str | None
        if parece_url(crudo):
            self.b.sin_cfg = True
            self.problema("fuente", "E-O21", Severidad.ERROR)
            return None
        if es_ruta_absoluta(crudo):
            self.b.sin_cfg = True
            self.problema("fuente", "E-O14", Severidad.ERROR)
            return None
        if ":" in crudo:
            motivo = validar_volid(crudo, contenido)
            ref = RefVolumen(nombre=crudo.partition("/")[2], volid=crudo)
        else:
            motivo = validar_nombre_archivo(crudo, contenido)
            ref = RefVolumen(nombre=crudo)
        if motivo is not None:
            self.b.sin_cfg = True
            self.problema("fuente", regla, Severidad.ERROR, {"motivo": motivo})
            return None
        return ref

    def _detalle_origen(self, cfg: ConfiguracionVM) -> None:
        """Construye ``detalle_origen`` con ``fuente``, ``virtio``, ``modo_clon`` y los ajustes."""
        crudo = self.celda("fuente")
        virtio = self.celda("virtio")
        modo_txt = self.celda("modo_clon")
        con_virtio: bool | None = None
        if virtio:
            try:
                con_virtio = unidades.si_no(virtio)
            except unidades.ValorInvalido as e:
                self.error_valor("virtio", e)
        modo = None
        if modo_txt:
            try:
                modo = unidades.modo_clon(modo_txt)
            except unidades.ValorInvalido as e:
                self.error_valor("modo_clon", e)
        origen = cfg.origen
        if origen == OrigenSO.DISCO_VACIO:
            if crudo:
                self.problema("fuente", "V-O01.ajeno", Severidad.AVISO)
            return
        previo = cfg.detalle_origen
        if origen == OrigenSO.ISO:
            det = previo if isinstance(previo, DetalleIso) else DetalleIso()
            ref = self._ref_fuente(crudo, Contenido.ISO) if crudo else det.iso
            sin = det.sin_drivers if con_virtio is None else not con_virtio
            cfg.detalle_origen = DetalleIso(
                iso=ref or RefVolumen(), drivers=det.drivers, sin_drivers=sin
            )
        elif origen == OrigenSO.IMPORTAR_DISCO:
            det_i = previo if isinstance(previo, DetalleImportacion) else DetalleImportacion()
            ref = self._ref_fuente(crudo, Contenido.IMPORT) if crudo else det_i.imagen
            cfg.detalle_origen = DetalleImportacion(
                imagen=ref or RefVolumen(), ampliar_a_gib=self._ampliar
            )
        else:
            det_c = previo if isinstance(previo, DetalleClon) else DetalleClon()
            plantilla = det_c.plantilla
            if crudo:
                texto = self.texto("fuente")
                plantilla = RefPlantilla(nombre=texto) if texto else RefPlantilla()
            cfg.detalle_origen = DetalleClon(
                plantilla=plantilla,
                modo=modo or det_c.modo,
                ajustes=self._ajustes or det_c.ajustes,
                storage_destino=det_c.storage_destino,
            )

    def _discos(self, cfg: ConfiguracionVM, nodo_ef: str) -> None:
        ctx = self.ctx
        tamanos: dict[int, int | None] = {}  # None = «sin disco»
        almacenes: dict[int, str] = {}
        for k in range(MAX_DISCOS_CSV):
            col = _nombre_columna_disco(k)
            crudo = self.celda(col)
            if crudo:
                try:
                    gib, avisos = unidades.disco_gib(crudo, self.ctx.unidad_encabezado(col))
                except unidades.ValorInvalido as e:
                    self.error_valor(col, e)
                else:
                    tamanos[k] = gib
                    ctx.registrar_avisos(col, avisos)
            col_alm = _nombre_columna_almacenamiento(k)
            almacen = self.texto(col_alm)
            if almacen is not None:
                almacenes[k] = almacen
        if cfg.origen == OrigenSO.IMPORTAR_DISCO and tamanos.get(0) is not None:
            # La imagen manda el tamaño; la columna ``disco`` significa «ampliar a» (CA-O28).
            self._ampliar = tamanos.pop(0)
        if not tamanos and not almacenes:
            return

        if k0_sin_disco := (0 in tamanos and tamanos[0] is None):
            # Con «sin disco» en el principal no puede haber otros discos ni storages.
            for k in sorted((set(tamanos) | set(almacenes)) - {0}):
                if tamanos.get(k) is not None or k in almacenes:
                    col = (
                        _nombre_columna_disco(k)
                        if tamanos.get(k) is not None
                        else (_nombre_columna_almacenamiento(k))
                    )
                    self.b.sin_cfg = True
                    self.problema(
                        col, _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": "sin_disco_principal"}
                    )
            if 0 in almacenes:
                self.b.sin_cfg = True
                self.problema(
                    _nombre_columna_almacenamiento(0),
                    _REGLA_NO_ADMITIDO,
                    Severidad.ERROR,
                    {"motivo": "sin_disco_principal"},
                )
            cfg.con_disco = False
            cfg.discos = []
            return
        del k0_sin_disco

        discos: list[Disco] = list(cfg.discos) if cfg.con_disco else []
        quitar: set[int] = set()
        for k in sorted(set(tamanos) | set(almacenes)):
            pedido = tamanos.get(k)
            if k in tamanos and pedido is None:
                quitar.add(k)  # «0»/«ninguno» en un disco adicional: no existe
                continue
            if k < len(discos):
                if pedido is not None:
                    discos[k].tamano_gib = pedido
                if k in almacenes:
                    discos[k].storage = almacenes[k]
                continue
            if k > 0 and pedido is None:
                # Un storage para un disco que no existe y sin tamaño: no hay qué crear.
                self.b.sin_cfg = True
                self.problema(
                    _nombre_columna_almacenamiento(k),
                    _REGLA_NO_ADMITIDO,
                    Severidad.ERROR,
                    {"motivo": "sin_disco"},
                )
                continue
            storage = almacenes.get(k)
            if storage is None:
                storage = discos[0].storage if discos else self._storage_por_defecto(nodo_ef)
            nuevo = disco_por_defecto(storage)
            if pedido is not None:
                nuevo.tamano_gib = pedido
            discos.append(nuevo)
        cfg.discos = [d for i, d in enumerate(discos) if i not in quitar]
        cfg.con_disco = bool(cfg.discos)

    def _storage_por_defecto(self, nodo_ef: str) -> str:
        inv = self.ctx.inv
        if inv is None:
            return ""
        return storage_por_defecto(inv.storages.get(nodo_ef, ())) or ""

    def _celdas_red(self) -> _CeldasRed:
        """Lee y valida las columnas de la tarjeta 1 (``red``, ``vlan``, ``modelo_red``, ``mtu``,
        ``limite_red``). Los errores de celda quedan anotados en la fila."""
        bridge = self.texto("red")
        vlan = self.entero("vlan")
        crudo_modelo = self.celda("modelo_red")
        modelo: ModeloRed | None = None
        if crudo_modelo:
            try:
                modelo = unidades.modelo_red(crudo_modelo)
            except unidades.ValorInvalido as e:
                self.error_valor("modelo_red", e)
        mtu_fijado = False
        mtu: int | None = None
        crudo_mtu = self.celda("mtu")
        if crudo_mtu:
            try:
                mtu = unidades.mtu(crudo_mtu)
                mtu_fijado = True  # «heredar» también es una elección explícita (None)
            except unidades.ValorInvalido as e:
                self.error_valor("mtu", e)
        limite: float | None = None
        crudo_limite = self.celda("limite_red")
        if crudo_limite:
            try:
                limite = unidades.limite_mb(crudo_limite)
            except unidades.ValorInvalido as e:
                self.error_valor("limite_red", e)
        return _CeldasRed(bridge, vlan, modelo, mtu_fijado, mtu, limite)

    def _red(self, cfg: ConfiguracionVM, nodo_ef: str) -> None:
        c = self._celdas_red()
        self._modelo_red_arm(c.modelo)
        bridge, vlan, modelo, mtu_fijado, mtu, limite = (
            c.bridge,
            c.vlan,
            c.modelo,
            c.mtu_fijado,
            c.mtu,
            c.limite,
        )
        if bridge is None and vlan is None and modelo is None and not mtu_fijado and limite is None:
            return
        if not cfg.redes:
            inv = self.ctx.inv
            por_defecto = (bridge_por_defecto(inv.bridges.get(nodo_ef, ())) or "") if inv else ""
            cfg.redes = [InterfazRed(bridge=bridge if bridge is not None else por_defecto)]
            red = cfg.redes[0]
        else:
            red = cfg.redes[0]
            if bridge is not None:
                red.bridge = bridge
        if modelo is not None:
            red.modelo = modelo
        if vlan is not None:
            red.vlan = vlan
        # Fase A: MTU y límite van a la tarjeta 1 (hardware, como ``modelo_red``; P-19).
        if mtu_fijado:
            red.mtu = mtu
        if limite is not None:
            red.limite_mb = limite

    # -- red del clon y firewall de la fase C (RF-C6.3) --

    def _reescribir_red(self, reescribir: bool | None, clon: bool) -> None:
        """Columna ``reescribir_red``: ``sí`` en un clon aplica las columnas de red a ``net0`` del
        clon conservando la MAC (P-C7); ``no`` fija «como la plantilla»; vacía hereda el
        formulario. ``sí`` con un origen distinto de clonar es el error V-C51 de la celda."""
        if reescribir is None:
            return
        if not reescribir:
            self._red_clon = RedClon()
            return
        if not clon:
            self.b.sin_cfg = True
            self.problema("reescribir_red", "V-C51", Severidad.ERROR)
            return
        c = self._celdas_red()
        self._modelo_red_arm(c.modelo)
        fijados = {
            campo
            for campo, fijado in (
                (CampoRed.BRIDGE, c.bridge is not None),
                (CampoRed.MODELO, c.modelo is not None),
                (CampoRed.VLAN, c.vlan is not None),
                (CampoRed.MTU, c.mtu_fijado),
                (CampoRed.LIMITE, c.limite is not None),
            )
            if fijado
        }
        tarjeta = TarjetaClon(
            indice=0,
            accion=AccionTarjeta.CAMBIAR,
            bridge=c.bridge,
            modelo=None if c.modelo is None else c.modelo.value,
            vlan=c.vlan,
            mtu=c.mtu,
            limite_mb=c.limite,
            fijados=frozenset(fijados),
        )
        self._red_clon = RedClon(ModoRedClon.PERSONALIZAR, (tarjeta,))

    def _politica(self, canonica: str) -> Politica | None:
        crudo = self.celda(canonica)
        if not crudo:
            return None
        try:
            return unidades.politica(crudo)
        except unidades.ValorInvalido as e:
            self.error_valor(canonica, e)
            return None

    def _grupo_seguridad(self) -> str | None:
        """Nombre del grupo de seguridad (V-C31); su existencia la comprueba «Comprobar»."""
        grupo = self.texto("grupo_seguridad")
        if grupo is not None and RE_GRUPO.fullmatch(grupo) is None:
            self.b.sin_cfg = True
            self.problema("grupo_seguridad", "V-C31", Severidad.ERROR)
            return None
        return grupo

    def _firewall(self) -> FirewallParcial | None:
        """Celdas de firewall de la fila (``None`` = hereda todo del formulario). La coherencia
        con el firewall del formulario (V-C52: grupo sin firewall activo) la evalúa el
        planificador con el valor combinado."""
        parcial = FirewallParcial(
            activo=self.booleano("cortafuegos"),
            grupo=self._grupo_seguridad(),
            politica_entrada=self._politica("politica_entrada"),
            politica_salida=self._politica("politica_salida"),
        )
        return None if parcial == FirewallParcial() else parcial

    # -- opciones de la fase A (RF-A7.3) --

    def _notas(self) -> str | None:
        """Texto libre de ``notas``: saltos normalizados y sin control (aviso V-A14); hasta
        ``MAX_LONG_NOTAS``. Un token o caracteres no admitidos es un error de la celda."""
        crudo = self.celda("notas")
        if not crudo:
            return None
        limpio, cambios = limpiar_texto_libre(crudo)
        seguro, motivo = analizar_texto(
            limpio, maximo=MAX_LONG_NOTAS, multilinea=True, tabulador=True
        )
        if motivo is not None or contiene_token(seguro):
            self.b.sin_cfg = True
            detalle = "longitud" if motivo == MOTIVO_LONGITUD else "texto"
            if motivo is None:
                detalle = "token"  # parece un API Token: no se guardaría en ningún lote (INV-M2)
            self.problema("notas", _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": detalle})
            return None
        if cambios:
            self.problema("notas", "V-A14", Severidad.AVISO)
        return seguro

    def _etiquetas(self) -> tuple[str, ...] | None:
        """``etiquetas`` separadas por ``,`` o ``;``. Su validez la comprueba V-A02."""
        crudo = self.celda("etiquetas")
        return (normalizar_etiquetas(crudo) or None) if crudo else None

    def _pool(self) -> str | None:
        """``pool``: vacío = hereda (``None``); ``ninguno`` = sin pool aunque el lote lo fije."""
        crudo = self.celda("pool")
        if not crudo:
            return None
        if unidades.es_ninguno(crudo):
            return ""
        pool = self.texto("pool")
        if pool is not None and contiene_token(pool):
            # SEG-A-04: un token pegado en el pool no se conserva ni se guarda (INV-M2).
            self.b.sin_cfg = True
            self.problema("pool", _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": "token"})
            return None
        return pool

    # -- cloud-init y espera de IP (fase B, RF-B6.3) --

    def _texto_sin_token(self, canonica: str) -> str | None:
        """Texto libre de cloud-init (``ci_usuario``, ``ci_dominio``) sin token (INV-M2)."""
        texto = self.texto(canonica)
        if texto is not None and contiene_token(texto):
            self.b.sin_cfg = True
            self.problema(canonica, _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": "token"})
            return None
        return texto

    def _celda_sin_token(self, canonica: str) -> str:
        """Celda de cloud-init (IP, DNS, snippets) sin token: con uno la celda se descarta y la
        fila queda con error, como en ``ci_usuario`` (INV-M2). Devuelve ``""`` si se descartó."""
        crudo = self.celda(canonica)
        if crudo and contiene_token(crudo):
            self.b.sin_cfg = True
            self.problema(canonica, _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": "token"})
            return ""
        return crudo

    def _claves(self) -> tuple[str, ...] | None:
        """``ci_claves``: claves públicas separadas por salto de línea o ``;`` (hasta 8192).

        Los problemas se describen por línea y motivo, nunca con el contenido de la celda."""
        crudo = self.celda("ci_claves")
        if not crudo:
            return None
        if len(crudo) > MAX_LONG_CLAVES:  # defensa: el lector ya impone el límite de la celda
            self.b.sin_cfg = True
            self.problema("ci_claves", _REGLA_NO_ADMITIDO, Severidad.ERROR, {"motivo": "longitud"})
            return None
        resultado = analizar_claves(crudo.replace(";", "\n"))
        for p in resultado.problemas:
            self.b.sin_cfg = True
            if p.motivo == MotivoClave.CLAVE_PRIVADA:
                self.problema("ci_claves", "V-B23", Severidad.ERROR)
            elif p.motivo in (MotivoClave.DEMASIADAS, MotivoClave.DEMASIADO_TEXTO):
                self.problema("ci_claves", "V-B24", Severidad.ERROR, {"motivo": p.motivo.value})
            else:
                self.problema(
                    "ci_claves",
                    "V-B22",
                    Severidad.ERROR,
                    {"linea": str(p.linea), "motivo": p.motivo.value},
                )
        if resultado.problemas:
            return None
        return resultado.claves or None  # solo comentarios o líneas vacías = celda vacía

    def _contrasena(self) -> Secreto | None:
        """``ci_contrasena``: se valida el texto en claro y solo entonces nace el ``Secreto``.

        Se lee sin recortar (un espacio puede ser parte de la contraseña) y los problemas (V-B25)
        solo llevan el motivo."""
        pos = self.ctx.mapa.posiciones.get(COLUMNA_CONTRASENA)
        if pos is None or pos >= len(self.b.fila.celdas):
            return None
        valor = self.b.fila.celdas[pos]
        if not valor.strip():
            return None
        problemas = validar_contrasena(valor, valor, None)
        for p in problemas:
            self.problema(COLUMNA_CONTRASENA, p.codigo, p.severidad, p.params)
        if any(p.severidad == Severidad.ERROR for p in problemas):
            self.b.sin_cfg = True
            return None
        return Secreto(valor)

    def _tarjeta0(self) -> TarjetaCloudInit | None:
        """``ci_ip`` + ``ci_puerta`` -> tarjeta 1 (``net0``). ``heredar`` = sin configurar."""
        crudo = self._celda_sin_token("ci_ip")
        puerta = self._texto_sin_token("ci_puerta")
        if not crudo and puerta is None:
            return None
        modo, ip = (ModoTarjeta.SIN_CONFIGURAR, None) if not crudo else unidades.modo_ip(crudo)
        return TarjetaCloudInit(indice=0, modo=modo, ip=ip, serie=False, puerta=puerta)

    def _dns(self) -> tuple[str, ...] | None:
        """``ci_dns``: direcciones separadas por espacio, coma o ``;``. Su validez la
        comprueba V-B32."""
        if not self._celda_sin_token("ci_dns"):
            return None
        crudo = self.texto("ci_dns")
        if not crudo:
            return None
        tokens = tuple(t for t in _SEPARADORES_DNS.split(crudo) if t)
        if not tokens:
            return None
        normalizadas, motivo = normalizar_dns(" ".join(tokens))
        return tokens if motivo is not None else normalizadas

    def _snippets(self) -> SnippetsCloudInit | None:
        """Un volid, ``ninguno`` o vacío (= como la plantilla) por tipo. V-B54 revisa el formato."""
        valores: dict[str, str | None] = {}
        for columna, tipo in _COLUMNAS_SNIPPET:
            crudo = self._celda_sin_token(columna)
            if not crudo:
                valores[tipo] = None
            elif unidades.es_ninguno(crudo):
                valores[tipo] = NINGUNO
            else:
                valores[tipo] = self.texto(columna)
        snippets = SnippetsCloudInit(**valores)
        return None if snippets.como_la_plantilla else snippets

    def _cloudinit(self) -> CloudInitParcial | None:
        """Celdas de cloud-init de la fila (``None`` = hereda todo del formulario)."""
        parcial = CloudInitParcial(
            usuario=self._texto_sin_token("ci_usuario"),
            claves=self._claves(),
            contrasena=self._contrasena(),
            tarjeta0=self._tarjeta0(),
            dns=self._dns(),
            dominio=self._texto_sin_token("ci_dominio"),
            actualizar=self.booleano("ci_actualizar"),
            snippets=self._snippets(),
        )
        return None if parcial.vacia else parcial

    def _opciones(self, cfg: ConfiguracionVM, perfil: PerfilMaquina) -> OpcionesParciales | None:
        """Lee las columnas de la fase A. Las celdas vacías heredan las del formulario (``None``).

        Un perfil elegido en la columna ``perfil`` que marca «Arrancar con el servidor» lo fija en
        la fila (``aplicar_opciones_lote`` ignoraría el de ``cfg``); el perfil base ya lo aplicó
        el formulario y no se repite aquí.

        Los valores fijados también se copian a ``cfg`` para que las reglas V-A de capa 1 los
        vean; el planificador los reescribe con ``aplicar_opciones_lote``."""
        arranque_auto = self.booleano("arranque_auto")
        if arranque_auto is None and self.celda("perfil") and perfil.config.arranque_auto:
            arranque_auto = True
        op = OpcionesParciales(
            encender=self.booleano("encender"),
            arranque_auto=arranque_auto,
            notas=self._notas(),
            etiquetas_usuario=self._etiquetas(),
            pool=self._pool(),
            proteger=self.booleano("proteger"),
            cloudinit=self._cloudinit(),
            esperar_ip=self.booleano("esperar_ip"),
            firewall=self._firewall(),
            red_clon=self._red_clon,
        )
        if op.encender is not None:
            cfg.encender = op.encender
        if op.arranque_auto is not None:
            cfg.arranque_auto = op.arranque_auto
        if op.notas is not None:
            cfg.notas = op.notas
        if op.etiquetas_usuario is not None:
            cfg.etiquetas_usuario = op.etiquetas_usuario
        if op.pool is not None:
            cfg.pool = op.pool or None
        if op.proteger is not None:
            cfg.proteger = op.proteger
        # Fase B: cloud-init se copia a ``cfg`` solo para que las reglas V-B de capa 1 lo vean;
        # ``interpretar`` lo retira después (la fuente es ``opciones.cloudinit``). V-B60 se evalúa
        # aquí: ``cfg.encender`` no conoce el «Encender» del formulario.
        if op.cloudinit is not None:
            cfg.cloudinit = combinar(None, op.cloudinit)
        if op.esperar_ip:
            encender = op.encender if op.encender is not None else self.ctx.encender_base
            if encender is False:
                self.problema("esperar_ip", "V-B60", Severidad.ERROR)
        return op if op != OpcionesParciales() else None

    def _pistas(self, avisos: Sequence[AvisoPista], perfil: PerfilMaquina) -> None:
        """Avisos de pistas no resueltas (una vez por fila), salvo los que el CSV ya reemplazó."""
        config = perfil.config
        pista_disco = config.discos[0].storage_preferido if config.discos else None
        pista_red = config.redes[0].bridge_preferido if config.redes else None
        for a in avisos:
            if a.recurso == "storage" and a.pedido == pista_disco and self.celda("almacenamiento"):
                continue
            if a.recurso == "bridge" and a.pedido == pista_red and self.celda("red"):
                continue
            canonica = {"storage": "almacenamiento", "bridge": "red"}.get(a.recurso)
            if canonica not in self.ctx.mapa.posiciones:
                canonica = None
            self.problema(
                canonica,
                f"pista.{a.recurso}",
                Severidad.AVISO,
                {"pedido": a.pedido, "usado": a.usado or "", "nodo": a.nodo},
                valor=a.pedido,
            )

    def _de_validacion(self, p: Problema) -> None:
        canonica = _columna_de_campo(p.campo)
        if canonica not in self.ctx.mapa.posiciones:
            canonica = None
        self.problema(canonica, p.codigo, p.severidad, p.params)

    def _memoria_desmesurada(self, cfg: ConfiguracionVM) -> None:
        """V-M09: aviso si la memoria supera 1024 GiB o el mayor nodo conocido (CA-C04.9)."""
        mib = cfg.memoria_mib
        maximo = self.ctx.memoria_maxima_mib
        if mib > MEMORIA_AVISO_GIB * 1024 or (maximo is not None and mib > maximo):
            gib = mib / 1024
            texto = str(int(gib)) if gib == int(gib) else f"{gib:.1f}"
            params = {"gib": texto}
            if maximo is not None:
                params["maximo_nodo_mib"] = str(maximo)
            canonica = "memoria" if "memoria" in self.ctx.mapa.posiciones else None
            self.problema(canonica, "V-M09", Severidad.AVISO, params)

    def _capa2(self, cfg: ConfiguracionVM) -> None:
        ctx, b = self.ctx, self.b
        inv = ctx.inv
        assert inv is not None and ctx.caps is not None
        if cfg.origen != OrigenSO.DISCO_VACIO and inv.catalogo is not None:
            # CA-O28.3: fuente inexistente o ambigua, con alternativas (catálogo ya leído).
            _, de_origen = resolver_origen(cfg, inv, b.nodo or ctx.nodo_efectivo(None))
            for p in de_origen:
                self._de_validacion(p)
        if b.nodo:
            cfg.nodo = b.nodo
            for p in validar_vm(cfg, inv, ctx.caps):
                if p.codigo not in _CAPA2 or (p.codigo == "V-16" and p.campo.endswith(".modelo")):
                    continue
                params = dict(p.params)
                if p.codigo == "V-04":
                    nodo = next((n for n in inv.topologia.nodos if n.nombre == b.nodo), None)
                    params["motivo"] = "no_existe" if nodo is None else "sin_conexion"
                canonica = _columna_de_campo(p.campo)
                if canonica not in ctx.mapa.posiciones:
                    canonica = None
                self.problema(canonica, p.codigo, p.severidad, params)
            return
        elegibles, motivos = nodos_elegibles(cfg, inv, Destino())
        if elegibles:
            return
        detalle: list[str] = []
        for nombre, lista in list(motivos.items())[:MAX_NODOS_MOTIVOS]:
            m = lista[0].params
            recurso = m.get("storage") or m.get("bridge") or ""
            detalle.append(":".join(x for x in (nombre, m.get("motivo", ""), recurso) if x))
        self.problema(
            None,
            "V-L11",
            Severidad.ERROR,
            {"motivos": "|".join(detalle), "n": str(len(motivos))},
        )


# --- Tabla completa -------------------------------------------------------------------------


def _verificar_columnas_sin_encabezado(tabla: TablaCsv, reconocidas: Sequence[str]) -> None:
    """E-M10 ``vacia``: hay datos en columnas que no tienen encabezado (CA-C03.4)."""
    n = len(tabla.encabezado)
    extra = sorted({i for f in tabla.filas for i in range(n, len(f.celdas)) if f.celdas[i].strip()})
    if extra:
        raise ErrorProxLaunch(
            CodigoError.CSV_COLUMNAS,
            {
                "motivo": "vacia",
                "columna": "",
                "posiciones": ", ".join(str(i + 1) for i in extra),
                "reconocidas": ", ".join(reconocidas),
            },
        )


def _marcar_duplicados(borradores: Sequence[_Borrador], mapa: MapaColumnas) -> None:
    """V-M10: nombres (sin distinguir mayúsculas) o VMIDs repetidos; marca todas las filas."""
    por_nombre: dict[str, list[_Borrador]] = {}
    por_vmid: dict[int, list[_Borrador]] = {}
    for b in borradores:
        if b.nombre:
            por_nombre.setdefault(clave_comparacion(b.nombre), []).append(b)
        if b.vmid is not None:
            por_vmid.setdefault(b.vmid, []).append(b)
    grupos: list[tuple[str, str, list[_Borrador], str]] = []
    grupos += [("nombre", "nombre", g, g[0].nombre) for g in por_nombre.values() if len(g) > 1]
    grupos += [("vmid", "vmid", g, str(v)) for v, g in por_vmid.items() if len(g) > 1]
    for canonica, clave, grupo, valor in grupos:
        filas = ", ".join(str(g.fila.numero) for g in grupo)
        for b in grupo:
            b.problemas.append(
                (
                    _orden(mapa, canonica),
                    ProblemaCelda(
                        fila=b.fila.numero,
                        columna=mapa.encabezados.get(canonica),
                        regla="V-M10",
                        severidad=Severidad.ERROR,
                        params={"filas": filas, clave: texto_visible(valor)},
                        valor=texto_visible(valor),
                    ),
                )
            )


def _congelar(b: _Borrador) -> FilaInterpretada:
    """Ordena por columna y limita a ``MAX_PROBLEMAS_FILA`` sin ocultar nunca un error."""
    ordenados = sorted(range(len(b.problemas)), key=lambda i: (b.problemas[i][0], i))
    if len(ordenados) > MAX_PROBLEMAS_FILA:
        errores = [i for i in ordenados if b.problemas[i][1].severidad == Severidad.ERROR]
        resto = [i for i in ordenados if b.problemas[i][1].severidad != Severidad.ERROR]
        elegidos = set((errores + resto)[:MAX_PROBLEMAS_FILA])
        visibles = [i for i in ordenados if i in elegidos]
    else:
        visibles = ordenados
    return FilaInterpretada(
        numero=b.fila.numero,
        nombre=b.nombre,
        perfil=b.perfil,
        vmid=b.vmid,
        nodo=b.nodo,
        cfg=b.cfg,
        problemas=tuple(b.problemas[i][1] for i in visibles),
        problemas_omitidos=len(ordenados) - len(visibles),
        originales=b.originales,
        opciones=b.opciones,
    )


def interpretar(
    tabla: TablaCsv,
    *,
    perfil_base: PerfilMaquina,
    perfiles: Sequence[PerfilMaquina],
    inv: Inventario | None,
    nodo_referencia: str | None,
    alias_extra: Mapping[str, str] | None = None,
    encender_base: bool | None = None,
    hardware_base: HardwareCluster | None = None,
) -> ResultadoImportacion:
    """Interpreta y valida todas las filas (capa 1 y, con ``inv``, la capa 2 de vista previa).

    ``perfiles`` son los perfiles elegibles en la columna ``perfil`` (fábrica y usuario).
    ``nodo_referencia`` es el nodo en el que se resuelven las pistas de las filas sin nodo.
    ``encender_base`` es el «Encender al terminar» del formulario (``None`` = se desconoce): sirve
    para V-B60 (``esperar_ip`` en una fila sin encendido efectivo). Si se desconoce, esa regla la
    evalúa el planificador con la configuración completa.
    ``hardware_base`` son los mapeos PCI/USB del formulario (fase D): una celda ``mapeo_pci`` o
    ``mapeo_usb`` vacía los hereda y los ids de una celda con valor toman de ahí sus opciones.
    Lanza ``ErrorProxLaunch`` ``CSV_COLUMNAS`` (E-M10) si el encabezado no sirve.
    """
    mapa, avisos_columnas = resolver_columnas(tabla.encabezado, alias_extra=alias_extra)
    _verificar_columnas_sin_encabezado(tabla, list(mapa.posiciones))
    ctx = _Contexto(mapa, perfil_base, perfiles, inv, nodo_referencia, encender_base, hardware_base)
    borradores = [_Fila(ctx, f).interpretar() for f in tabla.filas]
    _marcar_duplicados(borradores, mapa)
    avisos_secretos: tuple[AvisoArchivo, ...] = ()
    if any(COLUMNA_CONTRASENA in b.originales for b in borradores):
        # RF-B6.5 (4): el CSV trae contraseñas en texto claro; se avisa una vez, sin valores.
        avisos_secretos = (AvisoArchivo(CodigoAvisoArchivo.CSV_CON_CONTRASENAS),)
    return ResultadoImportacion(
        codificacion=tabla.codificacion,
        deteccion=tabla.deteccion,
        columnas=mapa,
        filas=tuple(_congelar(b) for b in borradores),
        avisos=avisos_columnas + avisos_secretos + tuple(ctx.avisos_de_archivo()),
        perfil_base_id=perfil_base.id,
        con_inventario=inv is not None,
    )


def filas_lote(resultado: ResultadoImportacion, numeros: Collection[int]) -> tuple[FilaLote, ...]:
    """Convierte las filas elegidas (por número de fila) en ``FilaLote``, en orden de archivo.

    Lanza ``ValueError`` si algún número no existe o corresponde a una fila con error.
    """
    pedidas = set(numeros)
    existentes = {f.numero for f in resultado.filas}
    if desconocidas := pedidas - existentes:
        raise ValueError(f"filas inexistentes: {sorted(desconocidas)}")
    salida: list[FilaLote] = []
    for f in resultado.filas:
        if f.numero not in pedidas:
            continue
        if f.estado == EstadoFila.CON_ERROR or f.cfg is None:
            raise ValueError(f"la fila {f.numero} tiene errores")
        cfg = copy.deepcopy(f.cfg)
        cfg.nombre, cfg.vmid, cfg.nodo, cfg.etiquetas = f.nombre, f.vmid or 0, f.nodo or "", ()
        salida.append(FilaLote(f.nombre, cfg, f.vmid, f.nodo, f.numero, f.opciones, f.perfil))
    return tuple(salida)
