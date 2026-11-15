# Funciones comunes de los scripts de empaquetado para Windows (equivalente de lib.sh).
# Se carga con `. lib.ps1`; no ejecuta nada. Compatible con Windows PowerShell 5.1 (el de la MV) y
# con PowerShell 7. El archivo es UTF-8 con BOM: PowerShell 5.1 lo necesita para leer los acentos.
#
# Define: Write-Msg, Invoke-Principal, Invoke-Paso, Invoke-Nativo, Start-ProcesoEspera,
# Initialize-Registro, Write-ResumenTiempos, Test-Entorno, Get-PythonBuild, New-EntornoPython,
# Get-Iscc, Wait-Hasta, Get-HashArchivo.

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

# Get-PythonBuild : ruta del CPython 3.13 fijado (el de herramientas\python313 o el del PATH).
function Get-PythonBuild {
    $candidatos = @()
    if ($env:PROXLAUNCH_PYTHON) { $candidatos += $env:PROXLAUNCH_PYTHON }
    $candidatos += (Join-Path $HOME 'herramientas\python313\python.exe')
    $enRuta = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($enRuta) { $candidatos += $enRuta.Source }
    foreach ($c in $candidatos) {
        if (-not (Test-Path -LiteralPath $c)) { continue }
        $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$v".Trim() -eq '3.13') { return (Resolve-Path -LiteralPath $c).Path }
    }
    throw 'no se encontró CPython 3.13: ejecute empaquetado\windows\preparar-build.ps1'
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

# Get-Iscc : ruta del compilador de Inno Setup instalado por preparar-build.ps1.
function Get-Iscc {
    $candidatos = @(
        (Join-Path $HOME 'herramientas\innosetup6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    foreach ($c in $candidatos) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    throw 'no se encontró ISCC.exe: ejecute empaquetado\windows\preparar-build.ps1'
}
