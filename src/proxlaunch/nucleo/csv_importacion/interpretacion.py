"""Interpretación y validación fila a fila del CSV (RF-C04..C07, RF-C13).

``interpretar`` es una función pura sobre ``(tabla, perfil base, perfiles, inventario o None)``:
mismo archivo y entorno, mismos resultados (CA-C05.8). Precedencia (CA-C13.5), de menor a
mayor: valores por defecto de M1 -> perfil base o perfil de la fila -> columnas del CSV.

Capa 1 (sin servidor) siempre; capa 2 de vista previa solo con inventario. Los problemas de
celda son ``ProblemaCelda`` (código y parámetros, nunca texto de interfaz). Las columnas de
credenciales y las desconocidas no se leen jamás. Un problema de la tabla completa lanza
``ErrorProxLaunch`` (E-M10).
"""

import copy
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from proxlaunch.nucleo.archivos.constantes import (
    MAX_LONG_TEXTO,
    MAX_PROBLEMAS_FILA,
    MEMORIA_AVISO_GIB,
)
from proxlaunch.nucleo.archivos.csv_seguro import DISPARADORES
from proxlaunch.nucleo.archivos.esquema import AvisoArchivo, CodigoAvisoArchivo
from proxlaunch.nucleo.archivos.texto import clave_comparacion, texto_seguro
from proxlaunch.nucleo.capacidades import capacidades_para
from proxlaunch.nucleo.csv_importacion import unidades
from proxlaunch.nucleo.csv_importacion.columnas import (
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
from proxlaunch.nucleo.lote.modelos import Destino, FilaLote
from proxlaunch.nucleo.lote.reparto import nodos_elegibles
from proxlaunch.nucleo.modelos.catalogo import Contenido
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
    InterfazRed,
    ModeloRed,
    OrigenSO,
)
from proxlaunch.nucleo.origen.asistente import aplicar_asistente
from proxlaunch.nucleo.origen.nombres import (
    es_ruta_absoluta,
    parece_url,
    validar_nombre_archivo,
    validar_volid,
)
from proxlaunch.nucleo.origen.resolucion import resolver_origen
from proxlaunch.nucleo.perfiles_maquina.aplicar import AvisoPista, aplicar_config
from proxlaunch.nucleo.perfiles_maquina.modelos import PerfilMaquina
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
    }
    if campo in fijos:
        return fijos[campo]
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
        return {"vlan": "vlan", "bridge": "red", "modelo": "modelo_red"}.get(campo[9:])
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
    ) -> None:
        self.mapa = mapa
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


# --- Una fila -------------------------------------------------------------------------------


class _Fila:
    """Interpreta una fila. Agrupa el estado para no repartir parámetros entre funciones."""

    def __init__(self, ctx: _Contexto, fila: FilaCsv) -> None:
        self.ctx = ctx
        self.b = _Borrador(fila)
        self._ajustes: AjustesClon | None = None  # clon: ajustes leídos de las columnas
        self._ampliar: int | None = None  # importación: columna ``disco`` = ampliar a

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
        if not clon:
            self._discos(cfg, nodo_ef)
            self._red(cfg, nodo_ef)
        self._detalle_origen(cfg)
        self._pistas(resultado.avisos, perfil)

        # Capa 1 (V-01 solo con nombre; V-02 con el VMID explícito o uno válido de relleno).
        cfg.vmid = b.vmid if b.vmid is not None else VMID_MIN
        for p in validar_sin_servidor(cfg, incluir_nombre=bool(nombre_crudo), incluir_vmid=True):
            self._de_validacion(p)
        self._memoria_desmesurada(cfg)
        # Capa 2 (solo con inventario y si la configuración se pudo construir).
        if ctx.inv is not None and not b.sin_cfg:
            self._capa2(cfg)

        cfg.vmid = b.vmid if b.vmid is not None else 0
        cfg.nodo = b.nodo or ""
        b.cfg = None if b.sin_cfg else cfg
        for canonica, pos in ctx.mapa.posiciones.items():
            if pos < len(b.fila.celdas):
                original = sin_control(b.fila.celdas[pos]).strip()
                if original:
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
        crudo = self.celda("firmware")
        if crudo:
            try:
                cfg.firmware = unidades.firmware(crudo)
            except unidades.ValorInvalido as e:
                self.error_valor("firmware", e)
        tipo = self.texto("tipo_cpu")
        if tipo is not None and aplicar_tipo_cpu:
            cfg.tipo_cpu = tipo

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

    def _red(self, cfg: ConfiguracionVM, nodo_ef: str) -> None:
        bridge = self.texto("red")
        vlan = self.entero("vlan")
        crudo_modelo = self.celda("modelo_red")
        modelo: ModeloRed | None = None
        if crudo_modelo:
            try:
                modelo = unidades.modelo_red(crudo_modelo)
            except unidades.ValorInvalido as e:
                self.error_valor("modelo_red", e)
        if bridge is None and vlan is None and modelo is None:
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
    )


def interpretar(
    tabla: TablaCsv,
    *,
    perfil_base: PerfilMaquina,
    perfiles: Sequence[PerfilMaquina],
    inv: Inventario | None,
    nodo_referencia: str | None,
    alias_extra: Mapping[str, str] | None = None,
) -> ResultadoImportacion:
    """Interpreta y valida todas las filas (capa 1 y, con ``inv``, la capa 2 de vista previa).

    ``perfiles`` son los perfiles elegibles en la columna ``perfil`` (fábrica y usuario).
    ``nodo_referencia`` es el nodo en el que se resuelven las pistas de las filas sin nodo.
    Lanza ``ErrorProxLaunch`` ``CSV_COLUMNAS`` (E-M10) si el encabezado no sirve.
    """
    mapa, avisos_columnas = resolver_columnas(tabla.encabezado, alias_extra=alias_extra)
    _verificar_columnas_sin_encabezado(tabla, list(mapa.posiciones))
    ctx = _Contexto(mapa, perfil_base, perfiles, inv, nodo_referencia)
    borradores = [_Fila(ctx, f).interpretar() for f in tabla.filas]
    _marcar_duplicados(borradores, mapa)
    return ResultadoImportacion(
        codificacion=tabla.codificacion,
        deteccion=tabla.deteccion,
        columnas=mapa,
        filas=tuple(_congelar(b) for b in borradores),
        avisos=avisos_columnas + tuple(ctx.avisos_de_archivo()),
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
        salida.append(FilaLote(f.nombre, cfg, f.vmid, f.nodo, f.numero))
    return tuple(salida)
