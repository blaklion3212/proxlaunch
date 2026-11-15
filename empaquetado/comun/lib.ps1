# Funciones comunes de los scripts de empaquetado para Windows (equivalente de lib.sh).
# Se carga con `. lib.ps1`; no ejecuta nada. Compatible con Windows PowerShell 5.1 (el de la MV) y
# con PowerShell 7. El archivo es UTF-8 con BOM: PowerShell 5.1 lo necesita para leer los acentos.
#
# Define: Write-Msg, Invoke-Principal, Invoke-Paso, Invoke-Nativo, Start-ProcesoEspera,
# Initialize-Registro, Write-ResumenTiempos, Test-Entorno, Assert-HerramientaFijada, Get-PythonBuild,
# New-EntornoPython, Get-Iscc, Wait-Hasta, Get-HashArchivo.
#
# Cómo corta un fallo (equivalente de `paso` en lib.sh, QA-M5-01/02): $ErrorActionPreference = 'Stop'
# convierte los errores de cmdlets en excepciones dentro de cada bloque de Invoke-Paso, y los
# ejecutables NATIVOS solo se invocan con Invoke-Nativo (o Start-ProcesoEspera), que comprueban el
# código de salida y lanzan una excepción si no es válido; Invoke-Paso la reenvía con el nombre del paso
# e Invoke-Principal sale con 1. Un ejecutable nativo llamado a pelo con `&` NO corta el paso.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:NombreScript = 'empaquetado'
$script:Registro = $null
$script:Tiempos = New-Object System.Collections.Generic.List[string]
$script:Utf8SinBom = New-Object System.Text.UTF8Encoding($false)

try {
    [Console]::OutputEncoding = $script:Utf8SinBom
} catch {
    # Sin consola (p. ej. procesos sin ventana): no pasa nada, la salida sigue funcionando.
    $null = $_
}

# Write-Msg <texto> : escribe en pantalla y en el registro sustituyendo el perfil del usuario por ~ (RF-E35).
function Write-Msg {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Texto)
    $linea = "[$($script:NombreScript)] $Texto"
    if ($env:USERPROFILE) { $linea = $linea.Replace($env:USERPROFILE, '~') }
    Write-Host $linea
    if ($script:Registro) {
        [System.IO.File]::AppendAllText($script:Registro, $linea + "`r`n", $script:Utf8SinBom)
    }
}

# Initialize-Registro <nombre> : crea build\registros\<nombre>-<fecha>.txt (RF-E35).
function Initialize-Registro {
    param([Parameter(Mandatory = $true)][string]$Nombre)
    $carpeta = Join-Path $script:Raiz 'build\registros'
    New-Item -ItemType Directory -Force -Path $carpeta | Out-Null
    $script:Registro = Join-Path $carpeta ("{0}-{1}.txt" -f $Nombre, (Get-Date -Format 'yyyyMMdd-HHmmss'))
}

# Invoke-Principal <bloque> : ejecuta el cuerpo del script; ante un error lo informa y sale con 1.
function Invoke-Principal {
    param([Parameter(Mandatory = $true)][scriptblock]$Bloque)
    try {
        & $Bloque
    } catch {
        Write-Msg "ERROR: $($_.Exception.Message)"
        exit 1
    }
}

# Invoke-Paso <nombre> <bloque> : ejecuta, mide y falla con mensaje claro (RF-E37).
function Invoke-Paso {
    param(
        [Parameter(Mandatory = $true)][string]$Nombre,
        [Parameter(Mandatory = $true)][scriptblock]$Bloque
    )
    $t0 = Get-Date
    Write-Msg "=== $Nombre"
    try {
        & $Bloque | Out-Null
    } catch {
        throw "falló el paso: $Nombre ($($_.Exception.Message))"
    }
    $dt = [int]((Get-Date) - $t0).TotalSeconds
    $script:Tiempos.Add("${Nombre}: ${dt}s")
    Write-Msg "--- ${Nombre}: correcto (${dt}s)"
}

function Write-ResumenTiempos {
    Write-Msg 'Tiempos por paso:'
    foreach ($t in $script:Tiempos) { Write-Msg "  $t" }
}

# Invoke-Nativo : ejecuta un programa externo, copia su salida al registro y falla si el código no es válido.
# -Entorno define variables solo durante la llamada. Con -Capturar devuelve las líneas (stdout y stderr).
function Invoke-Nativo {
    param(
        [Parameter(Mandatory = $true)][string]$Ejecutable,
        [string[]]$Argumentos = @(),
        [hashtable]$Entorno = @{},
        [switch]$Capturar,
        [int[]]$CodigosValidos = @(0)
    )
    # Un ejecutable que no existe no debe pasar por un código de salida «0» heredado.
    if (-not (Get-Command -Name $Ejecutable -ErrorAction SilentlyContinue)) {
        throw "no se encontró el ejecutable $Ejecutable"
    }
    $anteriores = @{}
    foreach ($k in $Entorno.Keys) {
        $anteriores[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$Entorno[$k], 'Process')
    }
    $previa = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # PowerShell 5.1 trata stderr de programas externos como error
    $global:LASTEXITCODE = 0
    $lineas = New-Object System.Collections.Generic.List[string]
    try {
        & $Ejecutable @Argumentos 2>&1 | ForEach-Object {
            $t = "$_"
            $lineas.Add($t)
            if (-not $Capturar) { Write-Msg $t }
        }
        $codigo = $global:LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previa
        foreach ($k in $anteriores.Keys) {
            [Environment]::SetEnvironmentVariable($k, $anteriores[$k], 'Process')
        }
    }
    if ($CodigosValidos -notcontains $codigo) {
        throw "$(Split-Path -Leaf $Ejecutable) terminó con el código $codigo"
    }
    if ($Capturar) { return , $lineas.ToArray() }
}

# Start-ProcesoEspera : lanza un programa (también de interfaz gráfica), espera con límite y devuelve su código.
function Start-ProcesoEspera {
    param(
        [Parameter(Mandatory = $true)][string]$Ruta,
        [string[]]$Argumentos = @(),
        [hashtable]$Entorno = @{},
        [int]$LimiteSegundos = 120
    )
    $anteriores = @{}
    foreach ($k in $Entorno.Keys) {
        $anteriores[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$Entorno[$k], 'Process')
    }
    try {
        $parametros = @{ FilePath = $Ruta; PassThru = $true; WindowStyle = 'Hidden' }
        if ($Argumentos.Count -gt 0) { $parametros['ArgumentList'] = $Argumentos }
        $proceso = Start-Process @parametros
        $null = $proceso.Handle   # fija el manejador para poder leer ExitCode después
    } finally {
        foreach ($k in $anteriores.Keys) {
            [Environment]::SetEnvironmentVariable($k, $anteriores[$k], 'Process')
        }
    }
    if (-not $proceso.WaitForExit($LimiteSegundos * 1000)) {
        try { $proceso.Kill() } catch { $null = $_ }
        throw "$(Split-Path -Leaf $Ruta) no terminó en ${LimiteSegundos}s"
    }
    return [int]$proceso.ExitCode
}

# Wait-Hasta <condición> : espera a que el bloque devuelva verdadero (sondeo cada segundo).
function Wait-Hasta {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Condicion,
        [int]$Segundos = 60
    )
    $limite = (Get-Date).AddSeconds($Segundos)
    while ((Get-Date) -lt $limite) {
        if (& $Condicion) { return $true }
        Start-Sleep -Seconds 1
    }
    return [bool](& $Condicion)
}

function Get-HashArchivo {
    param([Parameter(Mandatory = $true)][string]$Ruta)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Ruta).Hash.ToLowerInvariant()
}

# Test-Entorno : Windows de 64 bits y PowerShell 5.1 o posterior.
function Test-Entorno {
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'este script solo se ejecuta en Windows' }
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'solo se admite Windows de 64 bits' }
    if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'se necesita PowerShell 5.1 o posterior' }
}

# Assert-HerramientaFijada <python|innosetup> <ruta> : exige que <ruta> sea el ejecutable que
# preparar-build.ps1 instaló a partir del instalador cuyo SHA-256 fija herramientas.json (SEG-M5-04).
# preparar-build.ps1 escribe ~\herramientas\verificadas.json con el SHA-256 del instalador fijado y el
# del ejecutable instalado; aquí se vuelve a calcular el del ejecutable y se compara.
function Assert-HerramientaFijada {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('python', 'innosetup')][string]$Nombre,
        [Parameter(Mandatory = $true)][string]$Ruta
    )
    $registro = Join-Path $HOME 'herramientas\verificadas.json'
    if (-not (Test-Path -LiteralPath $registro)) {
        throw "falta $registro: ejecute empaquetado\windows\preparar-build.ps1"
    }
    $datos = Get-Content -LiteralPath $registro -Raw -Encoding UTF8 | ConvertFrom-Json
    $inventario = Get-Content -LiteralPath (Join-Path $script:Raiz 'empaquetado\entornos\windows\herramientas.json') `
        -Raw -Encoding UTF8 | ConvertFrom-Json
    $fijada = $inventario.herramientas.$Nombre
    if (-not $datos.PSObject.Properties[$Nombre]) { throw "el registro de herramientas no incluye '$Nombre'" }
    $anotada = $datos.$Nombre
    if ([string]$anotada.instalador_sha256 -ne [string]$fijada.sha256) {
        throw "'$Nombre' se instaló con otro instalador que el fijado en herramientas.json: vuelva a ejecutar preparar-build.ps1"
    }
    if (-not (Test-Path -LiteralPath $Ruta)) { throw "no existe $Ruta: ejecute empaquetado\windows\preparar-build.ps1" }
    $real = Get-HashArchivo -Ruta $Ruta
    if ($real -ne [string]$anotada.ejecutable_sha256) {
        throw "el SHA-256 de $(Split-Path -Leaf $Ruta) no es el verificado por preparar-build.ps1 (¿cambió la herramienta?)"
    }
}

# Get-PythonBuild : ruta del CPython 3.13 fijado. SOLO el de ~\herramientas\python313 instalado y
# verificado por preparar-build.ps1; no se acepta el del PATH ni una variable de entorno (SEG-M5-04).
function Get-PythonBuild {
    $ruta = Join-Path $HOME 'herramientas\python313\python.exe'
    if (-not (Test-Path -LiteralPath $ruta)) {
        throw 'no se encontró CPython 3.13: ejecute empaquetado\windows\preparar-build.ps1'
    }
    Assert-HerramientaFijada -Nombre 'python' -Ruta $ruta
    $v = & $ruta -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -ne 0 -or "$v".Trim() -ne '3.13') { throw "$ruta no es CPython 3.13" }
    return (Resolve-Path -LiteralPath $ruta).Path
}

# New-EntornoPython <carpeta> <lockfile...> : venv con el CPython fijado e instalación con hashes obligatorios.
function New-EntornoPython {
    param(
        [Parameter(Mandatory = $true)][string]$Carpeta,
        [Parameter(Mandatory = $true)][string[]]$Lockfiles
    )
    $py = Get-PythonBuild
    Invoke-Nativo -Ejecutable $py -Argumentos @('-m', 'venv', '--clear', $Carpeta)
    $venvPy = Join-Path $Carpeta 'Scripts\python.exe'
    $argsPip = @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--quiet',
        '--require-hashes', '--no-deps', '--only-binary=:all:')
    foreach ($l in $Lockfiles) { $argsPip += @('-r', $l) }
    Invoke-Nativo -Ejecutable $venvPy -Argumentos $argsPip
    return $venvPy
}

# Get-Iscc : ruta del compilador de Inno Setup. SOLO el de ~\herramientas\innosetup6 instalado y
# verificado por preparar-build.ps1 (no se buscan otras instalaciones; SEG-M5-04).
function Get-Iscc {
    $ruta = Join-Path $HOME 'herramientas\innosetup6\ISCC.exe'
    if (-not (Test-Path -LiteralPath $ruta)) {
        throw 'no se encontró ISCC.exe: ejecute empaquetado\windows\preparar-build.ps1'
    }
    Assert-HerramientaFijada -Nombre 'innosetup' -Ruta $ruta
    return $ruta
}
