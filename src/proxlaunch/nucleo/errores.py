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
