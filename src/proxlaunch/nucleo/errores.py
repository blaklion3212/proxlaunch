"""Errores del núcleo: códigos estables y excepción con parámetros.

El núcleo no contiene textos para el usuario: la interfaz traduce cada
``CodigoError`` (con sus ``params``) a un mensaje en español.
"""

from enum import StrEnum


class CodigoError(StrEnum):
    """Códigos de error que la interfaz traduce a mensajes."""

    CREDENCIALES_INVALIDAS = "credenciales_invalidas"
    SESION_EXPIRADA = "sesion_expirada"
    HUELLA_CAMBIADA = "huella_cambiada"
    HUELLA_NO_CONFIADA = "huella_no_confiada"
    TFA_NO_SOPORTADO = "tfa_no_soportado"
    TFA_CODIGO_INCORRECTO = "tfa_codigo_incorrecto"
    SERVIDOR_NO_RESPONDE = "servidor_no_responde"
    NODO_NO_DISPONIBLE = "nodo_no_disponible"
    PERMISO_INSUFICIENTE = "permiso_insuficiente"
    VMID_OCUPADO = "vmid_ocupado"
    SIN_ESPACIO = "sin_espacio"
    TAREA_TIEMPO_AGOTADO = "tarea_tiempo_agotado"
    ERROR_FORMATO = "error_formato"
    PARAMETRO_INVALIDO = "parametro_invalido"
    VERSION_NO_SOPORTADA = "version_no_soportada"
    RECURSO_INEXISTENTE = "recurso_inexistente"
    UPID_INVALIDO = "upid_invalido"
    LLAVERO_NO_DISPONIBLE = "llavero_no_disponible"
    DESCONOCIDO = "desconocido"
    # --- Lotes (MVP 2, docs/requisitos/mvp2.md §7) ---
    LOTE_SIN_NODO_APTO = "lote_sin_nodo_apto"  # E-L01
    LOTE_VMIDS_INSUFICIENTES = "lote_vmids_insuficientes"  # E-L02
    LOTE_SIN_ESPACIO = "lote_sin_espacio"  # E-L04
    LOTE_ENVIO_INCIERTO = "lote_envio_incierto"  # E-L05
    LOTE_EXISTENCIA_INDETERMINADA = "lote_existencia_indeterminada"  # E-L06
    LOTE_PAUSADO_REPETIDO = "lote_pausado_repetido"  # E-L07
    LOTE_PAUSADO_CONEXION = "lote_pausado_conexion"  # E-L09
    LOTE_NO_ENVIADA = "lote_no_enviada"  # E-L10
    LOTE_PLAN_CAMBIO = "lote_plan_cambio"  # E-L11
    LOTE_EN_CURSO = "lote_en_curso"  # E-L12
    LOTE_CANTIDAD_INVALIDA = "lote_cantidad_invalida"  # E-L13
    VERSION_FORZADA_MAYOR = "version_forzada_mayor"  # E-L14
    ETIQUETA_RECHAZADA = "etiqueta_rechazada"  # E-L15
    ROLLBACK_FALLO = "rollback_fallo"  # E-L17
    ROLLBACK_NO_PROPIA = "rollback_no_propia"  # E-L18
    ROLLBACK_ENCENDIDA = "rollback_encendida"  # E-L19
    ROLLBACK_BLOQUEADA = "rollback_bloqueada"  # E-L20
    ROLLBACK_DISCOS_SUELTOS = "rollback_discos_sueltos"  # E-L21
    ROLLBACK_INCIERTO = "rollback_incierto"  # E-L22
    ESCRITURA_EN_SIMULACION = "escritura_en_simulacion"  # E-L23
    # --- Perfiles, lotes guardados y CSV (MVP 3, docs/requisitos/mvp3.md §7) ---
    ARCHIVO_NO_PERMITIDO = "archivo_no_permitido"  # E-M01
    ARCHIVO_FORMATO_AJENO = "archivo_formato_ajeno"  # E-M02
    ARCHIVO_VERSION_FUTURA = "archivo_version_futura"  # E-M03
    ARCHIVO_DANADO = "archivo_danado"  # E-M04 (sin «ñ» en el identificador)
    ARCHIVO_NO_ACCESIBLE = "archivo_no_accesible"  # E-M05
    ARCHIVO_DEMASIADAS_FILAS = "archivo_demasiadas_filas"  # E-M06
    CSV_CODIFICACION = "csv_codificacion"  # E-M07
    ARCHIVO_NO_GUARDABLE = "archivo_no_guardable"  # E-M08
    CSV_VACIO = "csv_vacio"  # E-M09
    CSV_COLUMNAS = "csv_columnas"  # E-M10
    CSV_VALOR_INVALIDO = "csv_valor_invalido"  # E-M11
    PERFIL_INEXISTENTE = "perfil_inexistente"  # E-M12
    PERFIL_NO_MODIFICABLE = "perfil_no_modificable"  # E-M13
    PERFILES_SOLO_LECTURA = "perfiles_solo_lectura"  # E-M14
    LOTE_NO_ENCAJA = "lote_no_encaja"  # E-M15
    PERFIL_RECHAZADO = "perfil_rechazado"  # interno: regla V-M01/V-M03/V-M05 (sin E-M propio)
    # --- Origen del sistema operativo (MVP 4, docs/arquitectura/mvp4.md §8) ---
    IMPORTAR_VERSION_NO_SOPORTADA = "importar_version_no_soportada"  # E-O01
    IMPORTAR_SIN_STORAGE_IMPORT = "importar_sin_storage_import"  # E-O02
    DESCARGA_URL_SIN_PERMISO = "descarga_url_sin_permiso"  # E-O03
    STORAGE_RECORDADO_NO_DISPONIBLE = "storage_recordado_no_disponible"  # E-O04
    CATALOGO_SIN_PERMISO = "catalogo_sin_permiso"  # E-O05
    TRANSFERENCIA_NO_VERIFICADA = "transferencia_no_verificada"  # E-O06
    TRANSFERENCIA_HUELLA_INCORRECTA = "transferencia_huella_incorrecta"  # E-O07
    TRANSFERENCIA_CORTADA = "transferencia_cortada"  # E-O08
    ARCHIVO_CAMBIO = "archivo_cambio"  # E-O09
    NOMBRE_YA_EXISTE = "nombre_ya_existe"  # E-O10
    DESCARGA_URL_FALLIDA = "descarga_url_fallida"  # E-O11
    IMPORTAR_SIN_PERMISO = "importar_sin_permiso"  # E-O12
    IMPORTAR_DESTINO_SIN_PERMISO = "importar_destino_sin_permiso"  # E-O13
    RUTA_ABSOLUTA_NO_PERMITIDA = "ruta_absoluta_no_permitida"  # E-O14
    IMAGEN_NO_ADMITIDA = "imagen_no_admitida"  # E-O15
    FUENTE_DESAPARECIO = "fuente_desaparecio"  # E-O16
    SIN_PLANTILLAS = "sin_plantillas"  # E-O17
    CLON_NO_POSIBLE = "clon_no_posible"  # E-O18
    CLON_ID_OCUPADO = "clon_id_ocupado"  # E-O19
    # E-O20 reutiliza PERMISO_INSUFICIENTE con params["via"]
    FUENTE_ES_URL = "fuente_es_url"  # E-O21
    ESPACIO_INSUFICIENTE_TRANSFERENCIA = "espacio_insuficiente_transferencia"  # E-O22
    TRANSFERENCIA_EN_CURSO = "transferencia_en_curso"  # E-O23
    AJUSTE_POST_CLON_FALLIDO = "ajuste_post_clon_fallido"  # E-O24
    TRANSFERENCIA_CANCELADA = "transferencia_cancelada"  # interno: sin E-O propio
    # --- Fase A (0.6): opciones de creación y Deshacer ampliado ---
    OPCION_SIN_PRIVILEGIO = "opcion_sin_privilegio"  # params: privilegio, ruta, opcion
    OPCION_SIN_VERSION = "opcion_sin_version"  # params: version, opcion
    POOLS_SIN_PERMISO = "pools_sin_permiso"  # no hay Pool.Audit: la lista llega vacía
    POOLS_DESCONOCIDO = "pools_desconocido"  # no se sabe si se tiene Pool.Audit
    POOLS_ERROR = "pools_error"  # falló la lectura de GET /pools
    POOL_INEXISTENTE = "pool_inexistente"
    DESCRIPCION_LARGA = "descripcion_larga"  # el 400 de Proxmox por > 8192 caracteres
    ROLLBACK_PROTEGIDA = "rollback_protegida"  # protection=1 (salvable con confirmación)
    ROLLBACK_SIN_POWERMGMT = "rollback_sin_powermgmt"
    ROLLBACK_SIN_OPCIONES = "rollback_sin_opciones"  # falta VM.Config.Options para desproteger
    ROLLBACK_APAGADO_FALLIDO = "rollback_apagado_fallido"
    ROLLBACK_DESPROTECCION_FALLIDA = "rollback_desproteccion_fallida"
    # --- Fase B (0.7): cloud-init, snippets, espera de IP y plantilla desde imagen ---
    CLOUDINIT_SIN_UNIDAD = "cloudinit_sin_unidad"  # la plantilla no tiene unidad cloud-init
    CLAVE_SSH_RECHAZADA = "clave_ssh_rechazada"  # 500 «SSH public key validation error»
    SNIPPET_NO_ENCONTRADO = "snippet_no_encontrado"  # params: snippet (opcional)
    CONTRASENA_OLVIDADA = "contrasena_olvidada"  # el Secreto ya no está en memoria
    ARCHIVO_CLAVES_NO_VALIDO = (
        "archivo_claves_no_valido"  # params: motivo (tamano|binario|ilegible)
    )
    AGENTE_NO_CONFIGURADO = "agente_no_configurado"  # «No QEMU guest agent configured»
    AGENTE_NO_RESPONDE = "agente_no_responde"  # el agente no contesta en el plazo
    MV_NO_EN_MARCHA = "mv_no_en_marcha"  # «VM … is not running»
    PLANTILLA_EN_MARCHA = "plantilla_en_marcha"
    PLANTILLA_CON_SNAPSHOTS = "plantilla_con_snapshots"
    PLANTILLA_NO_APAGADA = "plantilla_no_apagada"  # comprobación previa propia (sin POST)
    IMAGEN_FORMATO_INCORRECTO = "imagen_formato_incorrecto"
    SUMA_NO_COINCIDE = "suma_no_coincide"  # params: esperada, obtenida (12 caracteres)
    PLANTILLA_IMAGEN_SIN_IMPORT = "plantilla_imagen_sin_import"
    # --- Fase C (0.8): lotes del servidor, VNets de SDN, firewall y red del clon ---
    RED_CONFIG_ILEGIBLE = "red_config_ilegible"  # V-C21 (GET config del clon falló)
    RED_PLANTILLA_CAMBIADA = "red_plantilla_cambiada"  # índice de AÑADIR ocupado al ejecutar
    RED_CONFIG_CAMBIADA = "red_config_cambiada"  # digest distinto dos veces
    RED_SIN_DIRECCIONES = "red_sin_direcciones"  # IPAM: «can't find any free ip in zone…»
    FIREWALL_GRUPO_INEXISTENTE = "firewall_grupo_inexistente"  # el grupo desapareció


class ErrorProxLaunch(Exception):
    """Error del núcleo con código, parámetros y detalle técnico.

    Atributos:
        codigo: código estable del error.
        params: parámetros para el mensaje, p. ej. ``{"privilegio": "VM.Allocate"}``.
        detalle_tecnico: texto original de Proxmox, ya sin secretos.
    """

    def __init__(
        self,
        codigo: CodigoError,
        params: dict[str, str] | None = None,
        detalle_tecnico: str = "",
    ) -> None:
        super().__init__(str(codigo))
        self.codigo = codigo
        self.params: dict[str, str] = dict(params) if params else {}
        self.detalle_tecnico = detalle_tecnico

    def __repr__(self) -> str:
        return (
            f"ErrorProxLaunch(codigo={self.codigo!s}, params={self.params!r}, "
            f"detalle_tecnico={self.detalle_tecnico!r})"
        )
