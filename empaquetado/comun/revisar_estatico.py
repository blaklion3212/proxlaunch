"""Revisión estática de los scripts de empaquetado y del flujo de CI de GitHub Actions.

Aplica: CA-E30.1 (la única CI activa es ``.github/workflows/empaquetado.yml``; cualquier otro
archivo o proveedor de CI se rechaza), CA-E30.2/E31.2 (flujo válido, solo invoca ``empaquetado/``,
disparadores solo por etiquetas ``v*`` y a mano, y matriz), CA-E21.3 (sin etiquetas móviles),
CA-E33.1 (el nombre de la variable de laboratorio y la opción que habilita sockets reales solo
aparecen en guardas que las prohíben),
CA-E35.1 (sin trazas del shell, sin volcado del entorno, sin secretos literales, permisos de solo
lectura), CA-E23.4 (sin publicación) y CA-E24.2 (sin certificados, claves ni contraseñas).
También revisa los scripts de PowerShell (.ps1): sin trazas ni transcripciones, sin volcado de
variables de entorno, sin descargas dentro de los scripts, sin contraseñas literales, con BOM UTF-8
si tienen acentos (Windows PowerShell 5.1 lo exige) y, si hay PowerShell disponible, con sintaxis
válida; y las condiciones del instalador (proxlaunch.iss, CA-E01.4) y de herramientas.json.

Uso::

    python empaquetado/comun/revisar_estatico.py [--raiz DIR]

Sale con 1 y lista cada incumplimiento si hay alguno. Solo usa la biblioteca estándar; si PyYAML
está disponible valida el flujo con él (si no, hace una comprobación estructural reducida).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ESTE_ARCHIVO = Path(__file__).resolve()
CARPETAS_IGNORADAS = {".git", ".venv", "venv", "build", "dist", "__pycache__", "node_modules"}

# Único archivo de CI permitido (CA-E30.1): el flujo de GitHub Actions de empaquetado.
FLUJO_CI = ".github/workflows/empaquetado.yml"
# Archivos de CI que nunca deben estar activos, salvo FLUJO_CI (CA-E30.1).
CI_ACTIVA = (
    re.compile(r"(^|/)\.github/workflows/"),
    re.compile(r"(^|/)\.gitlab-ci\.ya?ml$"),
    re.compile(r"(^|/)azure-pipelines\.ya?ml$"),
    re.compile(r"(^|/)Jenkinsfile$"),
    re.compile(r"(^|/)\.circleci/"),
    re.compile(r"(^|/)bitbucket-pipelines\.ya?ml$"),
    re.compile(r"(^|/)\.travis\.ya?ml$"),
    re.compile(r"(^|/)appveyor\.ya?ml$"),
    re.compile(r"(^|/)\.drone\.ya?ml$"),
    re.compile(r"(^|/)\.buildkite/"),
)
EXTENSIONES_SECRETOS = {".pfx", ".p12", ".pem", ".key", ".crt", ".cer", ".snk", ".jks", ".keystore"}
EXTENSIONES_SCRIPT = {".sh", ".ps1"}
EXTENSIONES_TEXTO = EXTENSIONES_SCRIPT | {".py", ".spec", ".iss", ".toml", ".json", ".in", ".md"}

NOMBRE_LAB = "PROXLAUNCH" + "_LAB"
OPCION_SOCKET = "force-enable" + "-socket"
ASIGNA_LAB = re.compile(
    rf"(export|declare\s+-x|setx?|env|-e)\s+{NOMBRE_LAB}\b|{NOMBRE_LAB}=|{NOMBRE_LAB}\s*:\s+\S"
    rf"|\$env:{NOMBRE_LAB}\s*=(?!=)|Set-Item[^\n]*{NOMBRE_LAB}|[\"']{NOMBRE_LAB}[\"']\s*[:=]"
)
LINEA_DE_MENSAJE = re.compile(
    r"\b(grep|echo|printf|Select-String|Write-\w+|die|msg|prohib|must not)\b|-match"
)

TRAZAS = (
    (re.compile(r"\bset\s+-[a-zA-Z]*x"), "traza del shell (set -x)"),
    (re.compile(r"\bset\s+-o\s+xtrace"), "traza del shell (xtrace)"),
    (re.compile(r"\b(ba)?sh\s+-[a-zA-Z]*x\b"), "traza del shell (sh -x)"),
    (re.compile(r"Set-PSDebug\s+-Trace", re.I), "traza de PowerShell"),
    (re.compile(r"\bprintenv\b"), "volcado del entorno (printenv)"),
    (re.compile(r"^\s*env\s*(\||$|>)"), "volcado del entorno (env)"),
    (re.compile(r"\bexport\s+-p\b|\bdeclare\s+-px?\b"), "volcado del entorno (export -p)"),
    (re.compile(r"^\s*set\s*(\||$)"), "volcado del entorno (set)"),
    (re.compile(r"(Get-ChildItem|gci|dir|ls|Get-Item)\s+(-Path\s+)?env:", re.I), "volcado Env:"),
    (re.compile(r"GetEnvironmentVariables\(\)"), "volcado del entorno (.NET)"),
    (re.compile(r"toJSON\((env|secrets|github)\b"), "volcado de contexto en el flujo"),
    (re.compile(r"\bStart-Transcript\b", re.I), "transcripción de PowerShell (registra todo)"),
    (re.compile(r"\bTrace-Command\b", re.I), "traza de PowerShell (Trace-Command)"),
    (re.compile(r"\b(Get-Variable|gv)\s*(\||$|>)", re.I), "volcado de variables de PowerShell"),
    (re.compile(r"Environment\]::GetEnvironmentVariables\(", re.I), "volcado del entorno (.NET)"),
    (
        re.compile(
            r"\b(Invoke-WebRequest|iwr|Invoke-RestMethod|irm|Start-BitsTransfer)\b"
            r"|DownloadString|DownloadFile|\bInvoke-Expression\b|\biex\b",
            re.I,
        ),
        "descarga o ejecución dinámica en un script (las descargas las hace el anfitrión)",
    ),
)
SECRETOS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "clave privada"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "token de GitHub"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "clave de AWS"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "token de Slack"),
    (
        re.compile(
            r"(?i)(password|passwd|contrase[ñn]a|secret|token|api[_-]?key)\s*[:=]\s*[\"'][^\"'$\s{][^\"']{3,}[\"']"
        ),
        "secreto literal",
    ),
    (re.compile(r"(?i)signtool[^\n]*\s/p\s+\S+"), "contraseña de firma en la línea de órdenes"),
    (
        re.compile(r"(?i)ConvertTo-SecureString\s+(-String\s+)?[\"'][^\"'$]{3,}[\"']"),
        "contraseña literal",
    ),
    (re.compile(r"[\"'][^\"'\n]*\.(pfx|p12)[\"']"), "ruta de certificado"),
)
PUBLICACION = re.compile(
    r"\b(gh\s+release|twine\s+upload|docker\s+push|npm\s+publish|git\s+push|upload-release-asset"
    r"|action-gh-release|pypa/gh-action-pypi-publish)\b"
)


class Revision:
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self.problemas: list[str] = []

    def error(self, criterio: str, ruta: Path | str, linea: int | None, texto: str) -> None:
        ref = str(ruta) if linea is None else f"{ruta}:{linea}"
        self.problemas.append(f"{criterio}: {ref}: {texto}")


def archivos_del_repo(raiz: Path) -> list[Path]:
    """Archivos versionados o sin versionar y no ignorados; sin git, recorre el árbol."""
    try:
        res = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "-z", "-co", "--exclude-standard"],
            capture_output=True,
            check=True,
        )
        rutas = [raiz / p for p in res.stdout.decode().split("\0") if p]
        return [r for r in rutas if r.exists()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [
            p
            for p in raiz.rglob("*")
            if p.is_file() and not (set(p.relative_to(raiz).parts) & CARPETAS_IGNORADAS)
        ]


def lineas_de(ruta: Path) -> list[tuple[int, str]]:
    try:
        texto = ruta.read_text("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    return list(enumerate(texto.splitlines(), start=1))


def es_comentario(linea: str) -> bool:
    return linea.lstrip().startswith("#")


def revisar_ci_activa(rev: Revision, archivos: list[Path]) -> None:
    for ruta in archivos:
        rel = ruta.relative_to(rev.raiz).as_posix()
        if rel != FLUJO_CI and any(p.search(rel) for p in CI_ACTIVA):
            rev.error("CA-E30.1", rel, None, "archivo de CI activo en el repositorio")


def revisar_certificados(rev: Revision, archivos: list[Path]) -> None:
    for ruta in archivos:
        rel = ruta.relative_to(rev.raiz)
        if ruta.suffix.lower() in EXTENSIONES_SECRETOS:
            rev.error("CA-E24.2", rel.as_posix(), None, "certificado o clave en el repositorio")


def revisar_texto(rev: Revision, archivos: list[Path]) -> None:
    emp = rev.raiz / "empaquetado"
    for ruta in archivos:
        if ruta.name == ESTE_ARCHIVO.name or emp not in ruta.parents:
            continue
        if ruta.suffix not in EXTENSIONES_TEXTO or "requisitos" in ruta.relative_to(emp).parts:
            continue
        rel = ruta.relative_to(rev.raiz).as_posix()
        es_script = ruta.suffix in EXTENSIONES_SCRIPT
        for n, linea in lineas_de(ruta):
            comentario = es_comentario(linea)
            if not comentario:
                for patron, que in SECRETOS:
                    if patron.search(linea):
                        crit = "CA-E24.2" if "certificado" in que or "firma" in que else "CA-E35.1"
                        rev.error(crit, rel, n, f"{que}")
                if es_script:
                    for patron, que in TRAZAS:
                        if patron.search(linea):
                            rev.error("CA-E35.1", rel, n, que)
                    if PUBLICACION.search(linea):
                        rev.error("CA-E23.4", rel, n, "publicación en un sitio externo")
            # CA-E33.1: el nombre de la variable y la opción de sockets solo en guardas.
            if ruta.suffix in EXTENSIONES_SCRIPT | {".py", ".spec"} and not comentario:
                if NOMBRE_LAB in linea and ASIGNA_LAB.search(linea):
                    rev.error(
                        "CA-E33.1", rel, n, "define la variable de las pruebas de laboratorio"
                    )
                if OPCION_SOCKET in linea and not LINEA_DE_MENSAJE.search(linea):
                    rev.error("CA-E33.1", rel, n, "habilita sockets reales en las pruebas")


def revisar_guardas(rev: Revision) -> None:
    """Las guardas deben existir: calidad (y su equivalente de Windows) prohíben la variable."""
    emp = rev.raiz / "empaquetado"
    for nombre in ("calidad.sh", "calidad.ps1"):
        ruta = emp / nombre
        if not ruta.is_file():
            if nombre == "calidad.sh":
                rev.error("CA-E33.1", f"empaquetado/{nombre}", None, "falta el script de calidad")
            continue
        texto = ruta.read_text("utf-8")
        if "not integracion" not in texto:
            rev.error("CA-E33.1", f"empaquetado/{nombre}", None, 'falta -m "not integracion"')
        if nombre.endswith(".sh"):
            lib = (
                (emp / "comun" / "lib.sh").read_text("utf-8")
                if (emp / "comun" / "lib.sh").is_file()
                else ""
            )
            guarda = f'-n "${{{NOMBRE_LAB}:-}}"'
            if "guardia_laboratorio" not in texto or guarda not in lib:
                rev.error(
                    "CA-E33.1", f"empaquetado/{nombre}", None, "falta la guarda de laboratorio"
                )
        elif NOMBRE_LAB not in texto:
            rev.error("CA-E33.1", f"empaquetado/{nombre}", None, "falta la guarda de laboratorio")


def revisar_paso(rev: Revision) -> None:
    """QA-M5-01/02: ``paso`` de lib.sh debe correr la orden con ``set -e`` activo (subshell).

    Con ``if ! "$@"`` Bash ignora ``set -e`` dentro de las funciones y un fallo intermedio pasa
    inadvertido. El comportamiento se prueba con ``comun/autotest-lib.sh``.
    """
    ruta = rev.raiz / "empaquetado" / "comun" / "lib.sh"
    if not ruta.is_file():
        return
    rel = ruta.relative_to(rev.raiz).as_posix()
    sin_comentarios = "\n".join(ln for _, ln in lineas_de(ruta) if not es_comentario(ln))
    if re.search(r'\bif\s+!\s+"\$@"', sin_comentarios):
        rev.error("QA-M5-01", rel, None, 'paso no debe ejecutar la orden dentro de `if ! "$@"`')
    if not re.search(r'\(\s*set -e;\s*"\$@"\s*\)', sin_comentarios):
        rev.error("QA-M5-01", rel, None, 'paso debe ejecutar `( set -e; "$@" )` (set -e activo)')


def revisar_codificacion_ps1(rev: Revision, archivos: list[Path]) -> None:
    """Windows PowerShell 5.1 lee como ANSI un .ps1 sin BOM: con acentos exige BOM UTF-8."""
    emp = rev.raiz / "empaquetado"
    for ruta in archivos:
        if ruta.suffix != ".ps1" or emp not in ruta.parents:
            continue
        datos = ruta.read_bytes()
        rel = ruta.relative_to(rev.raiz).as_posix()
        try:
            texto = datos.decode("utf-8-sig")
        except UnicodeDecodeError:
            rev.error("CA-E35.1", rel, None, "el .ps1 no es UTF-8")
            continue
        if not texto.isascii() and not datos.startswith(b"\xef\xbb\xbf"):
            rev.error(
                "CA-E35.1", rel, None, "tiene acentos y le falta el BOM UTF-8 (PowerShell 5.1)"
            )


def revisar_sintaxis_powershell(rev: Revision, archivos: list[Path]) -> None:
    """Valida la sintaxis de los .ps1 con el analizador de PowerShell si hay uno disponible."""
    emp = rev.raiz / "empaquetado"
    scripts = [r for r in archivos if r.suffix == ".ps1" and emp in r.parents]
    interprete = next((e for e in ("pwsh", "powershell") if shutil.which(e)), None)
    if not scripts or interprete is None:
        if scripts:
            print(
                "AVISO: no hay PowerShell (pwsh/powershell): no se valida la sintaxis de los .ps1"
            )
        return
    lista = ",".join("'" + str(s).replace("'", "''") + "'" for s in scripts)
    orden = (
        "$fallo = 0; foreach ($f in @(" + lista + ")) { $e = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$e); "
        "foreach ($x in $e) { Write-Output ('{0}:{1}: {2}' -f $f, $x.Extent.StartLineNumber, "
        "$x.Message); "
        "$fallo = 1 } }; exit $fallo"
    )
    res = subprocess.run(
        [interprete, "-NoProfile", "-NonInteractive", "-Command", orden],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        for linea in res.stdout.splitlines():
            if linea.strip():
                rev.error("SINTAXIS-PS1", Path(linea.split(":", 1)[0]).name, None, linea)
        if not res.stdout.strip():
            rev.error(
                "SINTAXIS-PS1",
                "empaquetado",
                None,
                res.stderr.strip()[:300] or "falló el analizador",
            )


def revisar_instalador(rev: Revision) -> None:
    """CA-E01.4, RF-E01, RF-E11, RF-E13, RF-E24: condiciones del script de Inno Setup."""
    ruta = rev.raiz / "empaquetado" / "windows" / "proxlaunch.iss"
    if not ruta.is_file():
        return  # el instalador de Windows es opcional en árboles sin esa parte
    rel = ruta.relative_to(rev.raiz).as_posix()
    texto = ruta.read_text("utf-8-sig")
    sin_comentarios = "\n".join(ln for ln in texto.splitlines() if not ln.lstrip().startswith(";"))
    exigidos = {
        r"^AppId=\{\{[0-9A-Fa-f-]{36}\}\s*$": "AppId fijo (GUID)",
        r"^MinVersion=10\.0\s*$": "MinVersion=10.0 (Windows 10 o posterior)",
        r"^ArchitecturesAllowed=x64compatible\s*$": "ArchitecturesAllowed=x64compatible",
        r"^PrivilegesRequired=lowest\s*$": "PrivilegesRequired=lowest (sin administrador)",
        r"^PrivilegesRequiredOverridesAllowed=dialog\s*$": "OverridesAllowed=dialog",
        r"^AppMutex=\S+": "AppMutex",
        r"^AppPublisher=ProxLaunch\s*$": "editor «ProxLaunch»",
        r"Languages\\Spanish\.isl": "asistente en español (Spanish.isl)",
        r"^Name: \"desktopicon\".*Flags: unchecked": "acceso directo del escritorio desmarcado",
        r"^OutputBaseFilename=proxlaunch-\{#Version\}-windows-x64-setup\s*$": "nombre",
        r"LicenseFile=\{#Raiz\}\\LICENSE\s*$": "licencia = LICENSE",
        r"BORRARDATOS": "parámetro del desinstalador para borrar datos",
    }
    for patron, que in exigidos.items():
        if not re.search(patron, sin_comentarios, re.M):
            rev.error("CA-E01.4", rel, None, f"falta o cambió: {que}")
    for prohibido in (
        r"\bSignTool\b",
        r"\bSignedUninstaller\b",
        r"\bDeleteKey\b",
        r"\bCredWrite\b",
    ):
        if re.search(prohibido, sin_comentarios, re.I):
            rev.error("CA-E24.2", rel, None, f"no debe aparecer {prohibido}")
    if "HKCU" in sin_comentarios or "[Registry]" in sin_comentarios:
        rev.error(
            "CA-E13.1",
            rel,
            None,
            "el instalador no debe tocar el registro fuera de lo que gestiona Inno",
        )


def revisar_herramientas(rev: Revision) -> None:
    """RF-E21: las herramientas de Windows tienen URL HTTPS, versión y SHA-256 completos."""
    ruta = rev.raiz / "empaquetado" / "entornos" / "windows" / "herramientas.json"
    if not ruta.is_file():
        return
    rel = ruta.relative_to(rev.raiz).as_posix()
    try:
        datos = json.loads(ruta.read_text("utf-8"))["herramientas"]
    except (ValueError, KeyError) as exc:
        rev.error("CA-E21.3", rel, None, f"JSON no válido: {exc}")
        return
    for nombre, h in datos.items():
        if not str(h.get("url", "")).startswith("https://"):
            rev.error("CA-E21.3", rel, None, f"{nombre}: la URL debe ser HTTPS")
        if not re.fullmatch(r"[0-9a-f]{64}", str(h.get("sha256", ""))):
            rev.error("CA-E21.3", rel, None, f"{nombre}: falta un SHA-256 válido")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(h.get("version", ""))):
            rev.error("CA-E21.3", rel, None, f"{nombre}: versión exacta requerida")
        if not h.get("origen_de_la_suma"):
            rev.error("CA-E21.3", rel, None, f"{nombre}: falta anotar el origen de la suma")


def _cargar_yaml(texto: str, rev: Revision, rel: str):  # noqa: ANN202
    try:
        import yaml
    except ImportError:
        print("AVISO: PyYAML no está instalado; se hace solo la comprobación estructural reducida")
        return None
    try:
        return yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        rev.error("CA-E30.2", rel, None, f"YAML no válido: {exc}")
        return {}


def revisar_flujo(rev: Revision) -> None:
    ruta = rev.raiz / FLUJO_CI
    rel = ruta.relative_to(rev.raiz).as_posix()
    if not ruta.is_file():
        rev.error("CA-E30.2", rel, None, "falta el flujo de CI")
        return
    texto = ruta.read_text("utf-8")
    sin_comentarios = [(n, ln) for n, ln in lineas_de(ruta) if not es_comentario(ln)]
    if "\t" in texto:
        rev.error("CA-E30.2", rel, None, "contiene tabuladores (no es YAML válido)")
    for n, linea in sin_comentarios:
        if re.search(r"(@main|@master|:latest\b|-latest\b|@v\d)", linea):
            rev.error("CA-E21.3", rel, n, "etiqueta móvil (main/master/latest/vN)")
        m = re.search(r"\buses:\s*(\S+)", linea)
        if (
            m
            and not m.group(1).startswith("./")
            and not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", m.group(1).strip("'\""))
        ):
            rev.error("CA-E21.3", rel, n, f"acción sin fijar por SHA de commit: {m.group(1)}")
        m = re.search(r"\b(image|container):\s*(\S+)", linea)
        if m and "@sha256:" not in m.group(2):
            rev.error("CA-E21.3", rel, n, f"imagen sin digest: {m.group(2)}")
        if re.search(r"\$\{\{\s*secrets\.", linea):
            rev.error("CA-E35.1", rel, n, "el flujo no debe usar secretos")
        if "pull_request_target" in linea:
            rev.error("CA-E35.1", rel, n, "pull_request_target no está permitido")
        if re.search(r"permissions:.*write|:\s*write\b", linea):
            rev.error("CA-E35.1", rel, n, "permiso de escritura en el token")

    datos = _cargar_yaml(texto, rev, rel)
    if datos is None:  # sin PyYAML: comprobación reducida por texto
        for clave in ("name:", "permissions:", "jobs:", "workflow_dispatch", "tags:"):
            if clave not in texto:
                rev.error("CA-E30.2", rel, None, f"falta '{clave}'")
        for clave in ("pull_request", "branches:"):
            if clave in "\n".join(ln for _, ln in sin_comentarios):
                rev.error("CA-E30.2", rel, None, f"no debe haber disparador '{clave}'")
        if not re.search(r"os:\s*\[.*ubuntu.*windows|ubuntu-\d+\.\d+[\s\S]*windows", texto):
            rev.error("CA-E31.2", rel, None, "la matriz no cubre Ubuntu y Windows")
        # Solo las órdenes `run:` de una línea (el resto de claves del YAML no son órdenes).
        pasos = [
            re.sub(r"^\s*(-\s*)?run:\s*", "", ln)
            for _, ln in sin_comentarios
            if re.match(r"\s*(-\s*)?run:\s*\S", ln)
        ]
    else:
        if not isinstance(datos, dict) or "jobs" not in datos:
            rev.error("CA-E30.2", rel, None, "no define jobs")
            return
        disparadores = datos.get("on", datos.get(True, {}))
        if not isinstance(disparadores, dict):
            rev.error("CA-E30.2", rel, None, "'on' debe ser un mapa de disparadores")
            disparadores = {}
        # Decisión del usuario: solo etiquetas v* y a mano (repo privado, cupo de minutos).
        push = disparadores.get("push") or {}
        if not any(str(t).startswith("v") for t in (push.get("tags") or [])):
            rev.error("CA-E30.2", rel, None, "falta el disparador por etiquetas v*")
        if push.get("branches") or push.get("branches-ignore"):
            rev.error("CA-E30.2", rel, None, "push no debe dispararse por ramas")
        if "workflow_dispatch" not in disparadores:
            rev.error("CA-E30.2", rel, None, "falta el disparador workflow_dispatch")
        extra = sorted(set(disparadores) - {"push", "workflow_dispatch"})
        if extra:
            rev.error("CA-E30.2", rel, None, f"disparadores no permitidos: {', '.join(extra)}")
        if datos.get("permissions") != {"contents": "read"}:
            rev.error("CA-E35.1", rel, None, "permissions debe ser exactamente {contents: read}")
        sistemas: list[str] = []
        pasos = []
        for job in datos["jobs"].values():
            estrategia = (job.get("strategy") or {}).get("matrix") or {}
            sistemas += [str(x) for x in estrategia.get("os", [])] + [str(job.get("runs-on", ""))]
            for paso in job.get("steps", []):
                if "run" in paso:
                    pasos += [x for x in str(paso["run"]).splitlines() if x.strip()]
        if not (any("ubuntu" in s for s in sistemas) and any("windows" in s for s in sistemas)):
            rev.error("CA-E31.2", rel, None, "la matriz debe cubrir Ubuntu y Windows")
    # Además de los scripts, se admite `python -I empaquetado/...` (herramientas fijadas).
    permitido = re.compile(r"^(bash |pwsh |powershell |sh |python3? -I )?(\./)?empaquetado/\S+")
    for orden in pasos:
        if not permitido.match(orden.strip().lstrip("-").strip()):
            rev.error(
                "CA-E30.2", rel, None, f"el flujo solo invoca empaquetado/: '{orden.strip()}'"
            )


def revisar(raiz: Path) -> list[str]:
    rev = Revision(raiz)
    archivos = archivos_del_repo(raiz)
    revisar_ci_activa(rev, archivos)
    revisar_certificados(rev, archivos)
    revisar_texto(rev, archivos)
    revisar_guardas(rev)
    revisar_paso(rev)
    revisar_flujo(rev)
    revisar_codificacion_ps1(rev, archivos)
    revisar_sintaxis_powershell(rev, archivos)
    revisar_instalador(rev)
    revisar_herramientas(rev)
    return rev.problemas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raiz", type=Path, default=RAIZ)
    args = ap.parse_args(argv)
    problemas = revisar(args.raiz.resolve())
    for p in problemas:
        print(p, file=sys.stderr)
    if problemas:
        print(f"revisión estática: {len(problemas)} incumplimiento(s)", file=sys.stderr)
        return 1
    print("revisión estática correcta (CA-E30, E21.3, E33.1, E35.1, E23.4, E24.2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
