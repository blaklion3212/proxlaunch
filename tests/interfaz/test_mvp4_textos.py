"""Textos del MVP 4: todos los errores E-O y reglas V-O están traducidos y nunca muestran
identificadores crudos ni marcadores sin rellenar; la ayuda lista los 14 privilegios; el catálogo
.ts no tiene textos sin contexto (RNF-O08, RF-O24, RF-O32, CA-O32.x)."""

from __future__ import annotations

import ast
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from proxlaunch.interfaz import ayuda, textos
from proxlaunch.nucleo.errores import CodigoError, ErrorProxLaunch
from proxlaunch.nucleo.modelos.catalogo import Contenido
from proxlaunch.nucleo.modelos.origen import ModoClon, TipoSO
from proxlaunch.nucleo.modelos.vm import OrigenSO
from proxlaunch.nucleo.origen.capacidades_origen import Disponibilidad, Via
from proxlaunch.nucleo.origen.permisos import ROL_PROXLAUNCH
from proxlaunch.nucleo.transferencias.modelos import EstadoTransferencia, Progreso
from proxlaunch.nucleo.validacion import Problema, Severidad

RAIZ = Path(__file__).resolve().parents[2] / "src" / "proxlaunch"
CATALOGO = RAIZ / "recursos" / "traducciones" / "proxlaunch_es.ts"

CODIGOS_E_O = [
    CodigoError.IMPORTAR_VERSION_NO_SOPORTADA,  # E-O01
    CodigoError.IMPORTAR_SIN_STORAGE_IMPORT,  # E-O02
    CodigoError.DESCARGA_URL_SIN_PERMISO,  # E-O03
    CodigoError.STORAGE_RECORDADO_NO_DISPONIBLE,  # E-O04
    CodigoError.CATALOGO_SIN_PERMISO,  # E-O05
    CodigoError.TRANSFERENCIA_NO_VERIFICADA,  # E-O06
    CodigoError.TRANSFERENCIA_HUELLA_INCORRECTA,  # E-O07
    CodigoError.TRANSFERENCIA_CORTADA,  # E-O08
    CodigoError.ARCHIVO_CAMBIO,  # E-O09
    CodigoError.NOMBRE_YA_EXISTE,  # E-O10
    CodigoError.DESCARGA_URL_FALLIDA,  # E-O11
    CodigoError.IMPORTAR_SIN_PERMISO,  # E-O12
    CodigoError.IMPORTAR_DESTINO_SIN_PERMISO,  # E-O13
    CodigoError.RUTA_ABSOLUTA_NO_PERMITIDA,  # E-O14
    CodigoError.IMAGEN_NO_ADMITIDA,  # E-O15
    CodigoError.FUENTE_DESAPARECIO,  # E-O16
    CodigoError.SIN_PLANTILLAS,  # E-O17
    CodigoError.CLON_NO_POSIBLE,  # E-O18
    CodigoError.CLON_ID_OCUPADO,  # E-O19
    CodigoError.FUENTE_ES_URL,  # E-O21
    CodigoError.ESPACIO_INSUFICIENTE_TRANSFERENCIA,  # E-O22
    CodigoError.TRANSFERENCIA_EN_CURSO,  # E-O23
    CodigoError.AJUSTE_POST_CLON_FALLIDO,  # E-O24
]

PARAMS_TIPICOS = {
    "storage": "local",
    "nombre": "alpine.iso",
    "contenido": "iso",
    "privilegio": "Datastore.AllocateTemplate",
    "ruta": "/storage/local",
    "via": "subir_iso",
    "version": "8.0",
    "nodo": "pve",
    "tipo": "iso",
    "host": "x.org",
    "archivo": "a.iso",
    "motivo": "404",
    "bytes": "1048576",
    "total": "2097152",
    "necesario": "2147483648",
    "libre": "1048576",
    "volid": "local:iso/a.iso",
    "vmid": "150",
    "plantilla": "base",
}


def _sin_pendientes(texto: str) -> None:
    assert texto.strip()
    assert "{" not in texto and "}" not in texto, texto
    assert "None" not in texto, texto


@pytest.mark.parametrize("codigo", CODIGOS_E_O, ids=lambda c: c.name)
def test_cada_error_e_o_tiene_texto_propio_con_o_sin_parametros(codigo):
    generico = textos.texto_generico()
    for params in ({}, PARAMS_TIPICOS):
        texto = textos.texto_error(ErrorProxLaunch(codigo, dict(params)))
        _sin_pendientes(texto)
        assert texto != generico, f"{codigo.name} cae en el texto genérico"
        assert codigo.value not in texto, f"{codigo.name} muestra su identificador"


def test_e_o20_permiso_insuficiente_con_via_dice_que_hace_falta():
    texto = textos.texto_error(
        ErrorProxLaunch(
            CodigoError.PERMISO_INSUFICIENTE,
            {"privilegio": "VM.Clone", "ruta": "/vms/9000", "via": "clonar"},
        )
    )
    _sin_pendientes(texto)
    assert "VM.Clone" in texto


def test_e_o24_ajuste_post_clon_dice_que_la_maquina_si_se_creo():
    texto = textos.texto_error(
        ErrorProxLaunch(
            CodigoError.AJUSTE_POST_CLON_FALLIDO, {"nombre": "web-01", "ajuste": "resize"}
        )
    )
    _sin_pendientes(texto)
    assert "web-01" in texto and "se clonó" in texto and "reintentar" in texto
    assert "resize" not in texto


CODIGOS_V_O = [
    "V-O01", "V-O01.ajeno", "V-O02", "V-O03", "V-O02.ambiguo", "V-O03.ambiguo", "V-O02.drivers",
    "V-O04", "V-O04.ambiguo", "V-O05", "V-O05.seabios", "V-O05.rhel10", "V-O06", "V-O07", "V-O08",
    "V-O13", "V-O13.raiz", "V-O14", "V-O15", "V-O16", "V-O17", "V-O18", "V-O19", "V-O21", "V-O23",
    "V-O23.tamano", "V-O24", "V-O25", "V-O26", "V-O27", "V-O29", "V-O29.sindisco",
]  # fmt: skip


@pytest.mark.parametrize("codigo", CODIGOS_V_O)
def test_cada_regla_v_o_tiene_texto_sin_marcadores_ni_identificadores_crudos(codigo):
    for params in ({}, PARAMS_TIPICOS):
        texto = textos.texto_problema(Problema("origen", codigo, Severidad.ERROR, dict(params)))
        _sin_pendientes(texto)
        assert codigo not in texto


def test_texto_campo_traduce_los_campos_del_origen_y_devuelve_vacio_si_no_esta_mapeado():
    for campo, esperado in (
        ("origen", "Origen"),
        ("detalle_origen.plantilla", "Origen"),
        ("tipo_so", "Sistema operativo"),
        ("tpm", "TPM 2.0"),
        ("agente_qemu", "Agente de QEMU"),
    ):
        assert textos.texto_campo(campo) == esperado
    assert textos.texto_campo("campo_inventado") == ""
    assert textos.texto_campo("detalle_origen.algo_raro") == "Origen"  # por su raíz mapeada


def test_texto_origen_cubre_los_cuatro_orígenes_y_los_tipos_de_so():
    for o in OrigenSO:
        assert textos.texto_origen(o).strip() and textos.texto_origen_corto(o).strip()
    nombres = {textos.texto_tipo_so(t) for t in TipoSO}
    assert len(nombres) == len(list(TipoSO)) and all(nombres)
    assert (
        len({textos.texto_modo_clon(m, avanzado=a) for m in ModoClon for a in (True, False)}) >= 3
    )


def test_las_nueve_vias_tienen_texto_y_los_estados_no_dependen_solo_del_color():
    for v in Via:
        assert textos.texto_via(v).strip()
        assert textos.texto_accion_via(v).strip()
    for d in Disponibilidad:
        assert textos.texto_disponibilidad(d).strip()
    from proxlaunch.interfaz.modelos_tabla_origen import simbolo_disponibilidad

    assert len({simbolo_disponibilidad(d) for d in Disponibilidad}) == 3


def test_los_estados_y_el_progreso_de_transferencia_estan_traducidos():
    for e in EstadoTransferencia:
        assert textos.texto_estado_transferencia(e).strip()
    p = Progreso(EstadoTransferencia.TRANSFIRIENDO, 1024**3, 2 * 1024**3, 1e6, 65.0, None)
    t = textos.texto_progreso_transferencia(p)
    assert "50 %" in t and "/s" in t and "quedan" in t
    for c in Contenido:
        assert textos.texto_contenido(c).strip() and "images" not in textos.texto_contenido(c)


@pytest.mark.parametrize("quedo", [True, False, None])
def test_texto_quedo_archivo_es_honesto_en_los_tres_casos(quedo):
    assert textos.texto_quedo_archivo(quedo).strip()


@pytest.mark.parametrize(
    "motivo", ["https", "credenciales", "host", "vacia", "esquema", "formato", "desconocido_xyz"]
)
def test_los_motivos_de_url_nunca_devuelven_el_identificador_crudo(motivo):
    texto = textos.texto_motivo_url(motivo)
    assert texto.strip() and "{" not in texto
    if motivo != "desconocido_xyz":
        assert texto != motivo


def test_las_urls_se_eliminan_de_los_textos_del_servidor():
    texto = textos.texto_sin_urls("fallo en https://u:clave-secreta@x.org/a.iso?token=T0K3N fin")
    assert "clave-secreta" not in texto and "T0K3N" not in texto and "https://" not in texto


# --- Ayuda: los 14 privilegios (RF-O24, RF-O32) -------------------------------------------------


def test_la_guia_lista_los_14_privilegios_del_rol_con_su_descripcion():
    assert len(ayuda.PRIVILEGIOS_ROL) == 14 == len(ROL_PROXLAUNCH)
    assert len(ayuda.privilegios_guia_token().splitlines()) == 14
    for p in ayuda.PRIVILEGIOS_ROL:
        assert ayuda.descripcion_privilegio(p).strip(), p


def test_ca_o24_3_los_cuatro_privilegios_nuevos_dicen_que_se_pierde_sin_ellos():
    notas = ayuda.notas_privilegios_nuevos()
    assert len(notas) == 4
    for p, nota in zip(ayuda.PRIVILEGIOS_NUEVOS, notas, strict=True):
        assert nota.startswith(p + ":") and "sin él" in nota


def test_ca_o32_2_el_texto_para_el_administrador_incluye_los_14_privilegios_y_no_secretos():
    texto = ayuda.texto_pedir_al_administrador()
    for p in ROL_PROXLAUNCH:
        assert p in texto
    assert "14" in texto
    assert "{" not in texto


def test_ca_o25_4_la_nota_de_archivos_subidos_dice_que_la_app_no_puede_borrarlos():
    assert "no puede borrar" in ayuda.nota_archivos_subidos()


def test_la_guia_del_token_muestra_los_14_privilegios(qtbot):
    from proxlaunch.interfaz.dialogos.guia_token import DialogoGuiaToken

    d = DialogoGuiaToken()
    qtbot.addWidget(d)
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTextEdit

    textos_dialogo = " ".join(
        [w.text() for w in d.findChildren(QLabel)]
        + [w.toPlainText() for w in d.findChildren(QPlainTextEdit)]
        + [w.toPlainText() for w in d.findChildren(QTextEdit)]
    )
    for p in ROL_PROXLAUNCH:
        assert p in textos_dialogo, p


# --- Catálogo de traducción (lupdate) -

ARCHIVOS_MVP4 = [
    "interfaz/controlador_origen.py",
    "interfaz/modelos_tabla_origen.py",
    "interfaz/vistas/selector_origen.py",
    "interfaz/dialogos/catalogo.py",
    "interfaz/dialogos/transferencia.py",
    "interfaz/dialogos/transferencias_sesion.py",
    "interfaz/dialogos/elegir_storage.py",
    "interfaz/dialogos/capacidades.py",
    "interfaz/vistas/resumen.py",
    "interfaz/vistas/progreso.py",
    "interfaz/vistas/formulario_vm.py",
    "interfaz/vistas/tabla_discos.py",
    "interfaz/vistas/resumen_lote.py",
    "interfaz/vistas/progreso_lote.py",
    "interfaz/ayuda.py",
    "interfaz/textos.py",
]


def _fuentes_del_catalogo() -> set[str]:
    raiz = ET.parse(CATALOGO).getroot()
    return {
        m.findtext("source") or "" for c in raiz.findall("context") for m in c.findall("message")
    }


def _literales_tr(ruta: Path) -> list[tuple[int, str]]:
    salida: list[tuple[int, str]] = []
    for n in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        if n.func.attr == "tr" and n.args and isinstance(n.args[0], ast.Constant):
            salida.append((n.lineno, str(n.args[0].value)))
        elif (
            n.func.attr == "translate" and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)
        ):
            salida.append((n.lineno, str(n.args[1].value)))
    return salida


@pytest.mark.parametrize("relativa", ARCHIVOS_MVP4)
def test_rnf_o_el_catalogo_contiene_cada_texto_traducible_del_mvp4(relativa):
    fuentes = _fuentes_del_catalogo()
    faltan = [
        f"{relativa}:{linea} {texto[:50]!r}"
        for linea, texto in _literales_tr(RAIZ / relativa)
        if texto not in fuentes
    ]
    assert faltan == []


def test_el_catalogo_versionado_no_tiene_mensajes_sin_contexto():
    """``grep -c "<name></name>"`` = 0: ningún texto quedó fuera de una clase con contexto."""
    assert CATALOGO.read_text(encoding="utf-8").count("<name></name>") == 0


def test_lupdate_sobre_el_codigo_actual_no_genera_mensajes_sin_contexto(tmp_path):
    """Regenera el catálogo en un directorio temporal (sin tocar el del repo)."""
    import PySide6

    lupdate = Path(next(iter(PySide6.__path__))) / "lupdate"
    if not lupdate.exists():
        pytest.skip("pyside6-lupdate no está disponible")
    salida = tmp_path / "n.ts"
    fuentes = sorted(str(p) for p in (RAIZ / "interfaz").rglob("*.py"))
    r = subprocess.run(  # noqa: S603
        [str(lupdate), "-extensions", "py", *fuentes, "-no-obsolete", "-ts", str(salida)],
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )
    assert salida.exists(), r.stderr
    nuevo = salida.read_text(encoding="utf-8")
    assert nuevo.count("<name></name>") == 0
    # Todo texto extraído ahora ya está en el catálogo versionado (no hay textos nuevos sin subir).
    extraidas = {
        m.findtext("source") or ""
        for c in ET.fromstring(nuevo).findall("context")
        for m in c.findall("message")
    }
    faltan = sorted(extraidas - _fuentes_del_catalogo())
    assert faltan == [], faltan[:5]


def test_ningun_texto_del_mvp4_usa_alias_que_lupdate_no_detecte():
    """Convención: ``self.tr`` o ``QCoreApplication.translate`` con literales directos."""
    patron = re.compile(r"\b(_tr|tr_)\s*\(")
    for relativa in ARCHIVOS_MVP4:
        texto = (RAIZ / relativa).read_text(encoding="utf-8")
        assert not patron.search(texto), relativa


def test_hallazgo_lab_03_ningun_texto_de_la_interfaz_promete_que_proxmox_impide_borrar():
    """En lvmthin PVE 9.2 sí deja borrar una plantilla con clones enlazados: no se promete lo
    contrario. La interfaz avisa de que se comparte el disco base."""
    from pathlib import Path

    import proxlaunch

    raiz = Path(proxlaunch.__file__).parent
    archivos = [*raiz.joinpath("interfaz").rglob("*.py"), *raiz.rglob("*.ts")]
    assert archivos
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8").lower()
        assert "no te dejará borrar" not in texto, archivo
        assert "no te dejara borrar" not in texto, archivo
