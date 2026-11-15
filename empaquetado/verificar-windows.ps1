# Verifica el instalador de Windows ya construido (RF-E18, RF-E13, RF-E14, RF-E17, CA-E40.4).
# Se ejecuta DENTRO de la MV de pruebas de Windows (la prepara entornos\windows\preparar.ps1):
#
#   1. instala en silencio para el usuario actual (/VERYSILENT /CURRENTUSER) y comprueba accesos y registro;
#   2. --version (sin Python en el PATH);
#   3. prueba de humo en una tarea programada INTERACTIVA de «prueba», con una regla de cortafuegos de
#      salida que bloquea el .exe instalado mientras dura (CA-E17.1); lee PROXLAUNCH_HUMO_SALIDA;
#      comprueba que el backend del llavero es el de Windows (CA-E09.1) y que los datos no cambian (CA-E17.2);
#   4. desinstala en silencio sin borrar datos y comprueba residuos con los datos de prueba intactos (CA-E13.1);
#   5. reinstala (dos veces: una sola entrada, CA-E14.1) y desinstala con /BORRARDATOS=1: se borran SOLO las
#      carpetas de datos de ProxLaunch del usuario y nada más (CA-E13.2); el llavero no se toca (CA-E13.3);
#   6. instala «para todos los usuarios» (/ALLUSERS) y comprueba que el desinstalador IGNORA
#      /BORRARDATOS=1 (no borra datos y lo anota en el registro de Inno, QA-M5-06);
#   7. escribe el sello de verificación en build\verificacion\ (lo recoge verificar-todo.sh).
#
# Modo actualización (-SoloActualizacion, QA-M5-07): en lugar de los pasos anteriores instala
# -InstaladorAnterior (p. ej. 0.5.0) por usuario, siembra datos de prueba, instala encima el -Instalador
# (build de prueba 0.5.1) y comprueba: --version nueva, DisplayVersion nueva, una sola entrada de
# desinstalación, datos idénticos (SHA-256) y humo correcto; después desinstala. No escribe sello.
#
# Parámetro del desinstalador definido en proxlaunch.iss: /BORRARDATOS=1 (la pregunta interactiva
# «Borrar también mis datos» tiene «No» por defecto).
#
# Uso: empaquetado\verificar-windows.ps1 [-Instalador <ruta>] [-VersionEsperada X.Y.Z] [-PermitirFueraDeLaMV]
#                                        [-SoloActualizacion -InstaladorAnterior <ruta>]
#   -PermitirFueraDeLaMV  el script modifica el cortafuegos, instala y borra datos de prueba: por seguridad
#                         solo corre en la MV marcada por preparar.ps1, salvo que se indique esto.
[CmdletBinding()]
param(
    [string]$Instalador = '',
    [string]$VersionEsperada = '',
    [switch]$PermitirFueraDeLaMV,
    [switch]$SoloActualizacion,
    [string]$InstaladorAnterior = ''
)

. (Join-Path $PSScriptRoot 'comun\lib.ps1')
$script:NombreScript = 'verificar-windows'

$script:MarcadorMV = Join-Path $env:ProgramData 'ProxLaunch-MV\es-mv-de-prueba.txt'
$script:NombreRegla = 'ProxLaunch-prueba-humo-bloqueo'
$script:NombreTarea = 'ProxLaunch-prueba-humo'
$script:ServicioLlavero = 'ProxLaunch-prueba'

# --- Utilidades --------------------------------------------------------------------------------

function Get-AppIdClave {
    $iss = Get-Content -LiteralPath (Join-Path $script:Raiz 'empaquetado\windows\proxlaunch.iss') -Raw -Encoding UTF8
    $m = [regex]::Match($iss, 'AppId=\{\{([0-9A-Fa-f-]{36})\}')
    if (-not $m.Success) { throw 'no se encontró AppId en proxlaunch.iss' }
    return '{' + $m.Groups[1].Value + '}_is1'
}

# Entrada de «Aplicaciones instaladas» del programa (por usuario o para todos), o $null.
function Get-EntradaDesinstalacion {
    $clave = Get-AppIdClave
    foreach ($base in @('HKCU:', 'HKLM:')) {
        $ruta = "$base\Software\Microsoft\Windows\CurrentVersion\Uninstall\$clave"
        if (Test-Path -LiteralPath $ruta) { return (Get-ItemProperty -LiteralPath $ruta) }
    }
    return $null
}

function Get-ProcesosProxLaunch {
    return @(Get-Process -Name 'proxlaunch' -ErrorAction SilentlyContinue)
}

# Listado estable (ruta relativa, tamaño y SHA-256) de las carpetas dadas, para comparar antes y después.
function Get-Listado {
    param([string[]]$Carpetas)
    $lineas = New-Object System.Collections.Generic.List[string]
    foreach ($c in $Carpetas) {
        if (-not (Test-Path -LiteralPath $c)) { $lineas.Add("AUSENTE|$c"); continue }
        Get-ChildItem -LiteralPath $c -Recurse -Force -File | ForEach-Object {
            $lineas.Add(('{0}|{1}|{2}' -f $_.FullName, $_.Length, (Get-HashArchivo -Ruta $_.FullName)))
        }
    }
    return (($lineas | Sort-Object) -join "`n")
}

function Install-ProxLaunch {
    param([string]$Setup, [string]$Registro, [switch]$TodosLosUsuarios)
    $ambito = if ($TodosLosUsuarios) { '/ALLUSERS' } else { '/CURRENTUSER' }
    $parametros = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', $ambito, "/LOG=`"$Registro`"")
    $codigo = Start-ProcesoEspera -Ruta $Setup -Argumentos $parametros -LimiteSegundos 300
    if ($codigo -ne 0) { throw "el instalador terminó con el código $codigo" }
    if (-not (Wait-Hasta -Segundos 30 -Condicion { $null -ne (Get-EntradaDesinstalacion) })) {
        throw 'tras instalar no aparece la entrada de «Aplicaciones instaladas»'
    }
}

function Uninstall-ProxLaunch {
    param([string]$Registro, [switch]$BorrarDatos)
    $entrada = Get-EntradaDesinstalacion
    if (-not $entrada) { throw 'no hay nada que desinstalar' }
    $carpeta = ([string]$entrada.InstallLocation).TrimEnd('\')
    $desinstalador = Join-Path $carpeta 'unins000.exe'
    if (-not (Test-Path -LiteralPath $desinstalador)) { throw "falta el desinstalador ($desinstalador)" }
    $parametros = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$Registro`"")
    if ($BorrarDatos) { $parametros += '/BORRARDATOS=1' }
    $codigo = Start-ProcesoEspera -Ruta $desinstalador -Argumentos $parametros -LimiteSegundos 300
    if ($codigo -ne 0) { throw "el desinstalador terminó con el código $codigo" }
    # El desinstalador de Inno puede devolver el control antes de terminar su segunda fase.
    $fin = Wait-Hasta -Segundos 90 -Condicion {
        ($null -eq (Get-EntradaDesinstalacion)) -and (-not (Test-Path -LiteralPath $carpeta)) `
            -and (@(Get-ProcesosProxLaunch).Count -eq 0)
    }
    if (-not $fin) { throw 'el desinstalador no terminó de limpiar en 90 s' }
}

# Residuos de la instalación (no de los datos del usuario).
function Test-SinResiduos {
    param([string]$CarpetaInstalacion)
    $problemas = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $CarpetaInstalacion) { $problemas.Add("queda la carpeta $CarpetaInstalacion") }
    $menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ProxLaunch.lnk'
    if (Test-Path -LiteralPath $menu) { $problemas.Add('queda el acceso directo del menú Inicio') }
    $escritorio = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ProxLaunch.lnk'
    if (Test-Path -LiteralPath $escritorio) { $problemas.Add('queda el acceso directo del escritorio') }
    if (Get-EntradaDesinstalacion) { $problemas.Add('queda la entrada de «Aplicaciones instaladas»') }
    if (@(Get-ProcesosProxLaunch).Count -gt 0) { $problemas.Add('queda un proceso proxlaunch') }
    if ($problemas.Count -gt 0) { throw ('residuos tras desinstalar: ' + ($problemas -join '; ')) }
}

# Sesión interactiva del usuario actual (explorer.exe): la necesita la tarea programada del humo.
function Test-SesionInteractiva {
    $yo = $env:USERNAME
    foreach ($p in @(Get-CimInstance -ClassName Win32_Process -Filter "Name='explorer.exe'")) {
        $dueno = Invoke-CimMethod -InputObject $p -MethodName GetOwner
        if ($dueno.User -eq $yo) { return $true }
    }
    return $false
}

# --- Datos de prueba -----------------------------------------------------------------------------
# Carpetas reales de la aplicación en Windows (platformdirs: appauthor = appname, sin roaming):
#   %LOCALAPPDATA%\ProxLaunch\ProxLaunch (configuración, datos, lotes y registro).
# Además se crean carpetas ajenas («señuelos») que NUNCA deben borrarse.
function Get-RutasDePrueba {
    $local = $env:LOCALAPPDATA
    return [pscustomobject]@{
        Externo  = (Join-Path $local 'ProxLaunch')
        Interno  = (Join-Path $local 'ProxLaunch\ProxLaunch')
        Marcador = (Join-Path $local 'ProxLaunch\.datos-de-prueba')
        Roaming  = (Join-Path $env:APPDATA 'ProxLaunch')
        Senuelo1 = (Join-Path $local 'PruebaProxLaunchSenuelo')
        Senuelo2 = (Join-Path $local 'PruebaOtraApp')
    }
}

function New-DatosDePrueba {
    $r = Get-RutasDePrueba
    # Protección: no se toca nada que no sea de una ejecución anterior de este mismo script.
    if ((Test-Path -LiteralPath $r.Externo) -and -not (Test-Path -LiteralPath $r.Marcador)) {
        throw "ya existe $($r.Externo) y no es de prueba: se niega a seguir para no tocar datos reales"
    }
    foreach ($ajena in @($r.Roaming, $r.Senuelo1, $r.Senuelo2)) {
        if ((Test-Path -LiteralPath $ajena) -and -not (Test-Path -LiteralPath (Join-Path $ajena '.datos-de-prueba'))) {
            throw "ya existe $ajena y no es de prueba: se niega a seguir"
        }
    }
    function Escribir-Prueba {
        param([string]$Ruta)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Ruta) | Out-Null
        [System.IO.File]::WriteAllText($Ruta, ('datos de prueba ' + [guid]::NewGuid().ToString()), $script:Utf8SinBom)
    }
    Escribir-Prueba $r.Marcador
    foreach ($archivo in @('perfiles.json', 'huellas.json', 'preferencias.json', 'lotes\lote-1.json', 'Logs\proxlaunch.log')) {
        Escribir-Prueba (Join-Path $r.Interno $archivo)
    }
    Escribir-Prueba (Join-Path $r.Externo 'ajeno.txt')
    Escribir-Prueba (Join-Path $r.Roaming '.datos-de-prueba')
    Escribir-Prueba (Join-Path $r.Roaming 'dato-roaming.txt')
    Escribir-Prueba (Join-Path $r.Senuelo1 '.datos-de-prueba')
    Escribir-Prueba (Join-Path $r.Senuelo1 'dato.txt')
    Escribir-Prueba (Join-Path $r.Senuelo2 '.datos-de-prueba')
    Escribir-Prueba (Join-Path $r.Senuelo2 'dato.txt')
}

function Remove-DatosDePrueba {
    $r = Get-RutasDePrueba
    foreach ($par in @(@($r.Externo, $r.Marcador), @($r.Roaming, (Join-Path $r.Roaming '.datos-de-prueba')),
            @($r.Senuelo1, (Join-Path $r.Senuelo1 '.datos-de-prueba')), @($r.Senuelo2, (Join-Path $r.Senuelo2 '.datos-de-prueba')))) {
        if ((Test-Path -LiteralPath $par[0]) -and (Test-Path -LiteralPath $par[1])) {
            Remove-Item -LiteralPath $par[0] -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-CarpetasDeDatos {
    $r = Get-RutasDePrueba
    return @($r.Externo, $r.Roaming, $r.Senuelo1, $r.Senuelo2)
}

# --- Humo con escritorio -------------------------------------------------------------------------
function Invoke-HumoInteractivo {
    param([string]$Exe, [string]$Temporal)
    $salida = Join-Path $Temporal 'humo-salida.txt'
    $codigoArchivo = Join-Path $Temporal 'humo-codigo.txt'
    Remove-Item -LiteralPath $salida, $codigoArchivo -Force -ErrorAction SilentlyContinue
    $q = { param($t) $t.Replace("'", "''") }
    $runner = Join-Path $Temporal 'humo-tarea.ps1'
    $contenido = @"
`$ErrorActionPreference = 'Stop'
`$env:PROXLAUNCH_HUMO_SALIDA = '$(& $q $salida)'
try {
    `$p = Start-Process -FilePath '$(& $q $Exe)' -ArgumentList '--prueba-de-humo' -PassThru
    `$null = `$p.Handle
    if (`$p.WaitForExit(45000)) { `$c = `$p.ExitCode } else { `$p.Kill(); `$c = 124 }
} catch { `$c = 125 }
Set-Content -LiteralPath '$(& $q $codigoArchivo)' -Value `$c
"@
    [System.IO.File]::WriteAllText($runner, $contenido, (New-Object System.Text.UTF8Encoding($true)))

    $usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $accion = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`""
    $principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
    $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
    Register-ScheduledTask -TaskName $script:NombreTarea -Action $accion -Principal $principal `
        -Settings $ajustes -Force | Out-Null
    try {
        Start-ScheduledTask -TaskName $script:NombreTarea
        if (-not (Wait-Hasta -Segundos 90 -Condicion { Test-Path -LiteralPath $codigoArchivo })) {
            throw 'la tarea de humo no terminó en 90 s'
        }
    } finally {
        Unregister-ScheduledTask -TaskName $script:NombreTarea -Confirm:$false -ErrorAction SilentlyContinue
    }
    $codigo = [int]((Get-Content -LiteralPath $codigoArchivo -Raw).Trim())
    $informe = if (Test-Path -LiteralPath $salida) { (Get-Content -LiteralPath $salida -Raw -Encoding UTF8).Trim() } else { '' }
    return [pscustomobject]@{ Codigo = $codigo; Informe = $informe }
}

# Texto de «--version» del ejecutable instalado (la salida del congelado va a PROXLAUNCH_HUMO_SALIDA).
function Get-TextoVersion {
    param([string]$Exe, [string]$Temporal)
    $salida = Join-Path $Temporal 'version.txt'
    Remove-Item -LiteralPath $salida -Force -ErrorAction SilentlyContinue
    $codigo = Start-ProcesoEspera -Ruta $Exe -Argumentos @('--version') -LimiteSegundos 60 `
        -Entorno @{ PROXLAUNCH_HUMO_SALIDA = $salida }
    $texto = if (Test-Path -LiteralPath $salida) { (Get-Content -LiteralPath $salida -Raw).Trim() } else { '' }
    if ($codigo -ne 0) { throw "--version terminó con el código $codigo ('$texto')" }
    return $texto
}

# Humo con escritorio, sin red (cortafuegos de salida) y con el llavero real; el informe debe ser
# completo, con la versión esperada, y las carpetas de datos no deben cambiar (CA-E17.1/E17.2/E09.1).
function Test-HumoInstalado {
    param([string]$Exe, [string]$Temporal, [string]$Version)
    if (-not (Test-SesionInteractiva)) {
        throw "no hay sesión interactiva de «$($env:USERNAME)»: reinicie la MV (inicio de sesión automático) o inicie sesión en su ventana"
    }
    Get-NetFirewallRule -DisplayName $script:NombreRegla -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $script:NombreRegla -Direction Outbound -Action Block `
        -Program $Exe -Profile Any | Out-Null
    try {
        if (-not (Get-NetFirewallRule -DisplayName $script:NombreRegla -ErrorAction SilentlyContinue)) {
            throw 'no se pudo crear la regla de cortafuegos de salida'
        }
        $antes = Get-Listado -Carpetas (Get-CarpetasDeDatos)
        $humo = Invoke-HumoInteractivo -Exe $Exe -Temporal $Temporal
    } finally {
        Get-NetFirewallRule -DisplayName $script:NombreRegla -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    Write-Msg "humo: código $($humo.Codigo); informe: $($humo.Informe)"
    if ($humo.Codigo -ne 0) { throw "la prueba de humo salió con el código $($humo.Codigo)" }
    $informe = $humo.Informe | ConvertFrom-Json
    if (@($informe.problemas).Count -ne 0) { throw "el informe de humo trae problemas: $(@($informe.problemas) -join '; ')" }
    if (@($informe.recursos_faltantes).Count -ne 0) { throw 'faltan recursos en el congelado instalado' }
    if (-not ($informe.traductor -and $informe.icono_ok -and $informe.ventana_mostrada)) { throw 'el informe de humo no está completo' }
    if ([string]$informe.version -ne $Version) { throw "el humo informa la versión '$($informe.version)'" }
    if ([string]$informe.backend_llavero -match 'fail|null|Null|Fail') {
        throw "el backend del llavero es '$($informe.backend_llavero)', no el de Windows (CA-E09.1)"
    }
    Write-Msg "backend del llavero: $($informe.backend_llavero)"
    $despues = Get-Listado -Carpetas (Get-CarpetasDeDatos)
    if ($antes -ne $despues) { throw 'el humo modificó las carpetas de datos (CA-E17.2)' }
}

# Verificación de la actualización (QA-M5-07): versión anterior -> nueva con datos del usuario.
function Invoke-VerificacionActualizacion {
    param(
        [string]$SetupNuevo, [string]$VersionNueva, [string]$SetupAnterior,
        [string]$Temporal, [string]$Registros
    )
    $m = [regex]::Match((Split-Path -Leaf $SetupAnterior), '^proxlaunch-(\d+\.\d+\.\d+)-windows-x64-setup\.exe$')
    if (-not $m.Success) { throw "nombre del instalador anterior inesperado: $(Split-Path -Leaf $SetupAnterior)" }
    $versionAnterior = $m.Groups[1].Value
    if ([version]$versionAnterior -ge [version]$VersionNueva) {
        throw "el instalador anterior ($versionAnterior) debe ser menor que el nuevo ($VersionNueva)"
    }
    $carpetaInstalacion = Join-Path $env:LOCALAPPDATA 'Programs\ProxLaunch'
    $exe = Join-Path $carpetaInstalacion 'proxlaunch.exe'
    Write-Msg "MODO ACTUALIZACIÓN: $versionAnterior -> $VersionNueva (build de prueba; no se publica ni se sella)"

    Invoke-Paso 'Estado inicial limpio (sin instalación previa; datos de prueba nuevos)' {
        if (Get-EntradaDesinstalacion) {
            Write-Msg 'AVISO: había una instalación previa; se desinstala antes de empezar'
            Uninstall-ProxLaunch -Registro (Join-Path $Registros 'inno-actualizacion-desinstalar-previo.txt')
        }
        Remove-DatosDePrueba
        New-DatosDePrueba
    }
    Invoke-Paso "Instalación de la versión anterior $versionAnterior (por usuario)" {
        Install-ProxLaunch -Setup $SetupAnterior -Registro (Join-Path $Registros 'inno-actualizacion-instalar-anterior.txt')
        $entrada = Get-EntradaDesinstalacion
        if ([string]$entrada.DisplayVersion -ne $versionAnterior) {
            throw "DisplayVersion es '$($entrada.DisplayVersion)' y se esperaba $versionAnterior"
        }
        $texto = Get-TextoVersion -Exe $exe -Temporal $Temporal
        if ($texto -ne "ProxLaunch $versionAnterior") { throw "--version devolvió '$texto'" }
        Write-Msg "versión anterior instalada: $texto"
    }
    # Los datos de usuario sembrados con la versión anterior se anotan (ruta, tamaño y SHA-256).
    $datosAntes = Get-Listado -Carpetas (Get-CarpetasDeDatos)

    Invoke-Paso "Actualización encima a $VersionNueva (una sola entrada, versión nueva, datos intactos)" {
        Install-ProxLaunch -Setup $SetupNuevo -Registro (Join-Path $Registros 'inno-actualizacion-instalar-nueva.txt')
        $clave = Get-AppIdClave
        $entradas = @(Get-ChildItem -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' |
                Where-Object { $_.PSChildName -eq $clave })
        if (@($entradas).Count -ne 1) { throw "hay $(@($entradas).Count) entradas de desinstalación en HKCU" }
        if (Test-Path -LiteralPath "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$clave") {
            throw 'hay además una entrada de desinstalación en HKLM'
        }
        $entrada = Get-EntradaDesinstalacion
        if ([string]$entrada.DisplayVersion -ne $VersionNueva) {
            throw "DisplayVersion es '$($entrada.DisplayVersion)' y se esperaba $VersionNueva"
        }
        Write-Msg "DisplayVersion: $($entrada.DisplayVersion)"
        if (-not (Test-Path -LiteralPath (Join-Path $carpetaInstalacion 'unins000.exe'))) { throw 'falta unins000.exe' }
        $texto = Get-TextoVersion -Exe $exe -Temporal $Temporal
        if ($texto -ne "ProxLaunch $VersionNueva") { throw "--version devolvió '$texto' y se esperaba la versión nueva" }
        Write-Msg "--version: $texto"
        $datosDespues = Get-Listado -Carpetas (Get-CarpetasDeDatos)
        if ($datosAntes -ne $datosDespues) { throw 'la actualización cambió los datos del usuario' }
        Write-Msg 'datos de usuario idénticos (misma suma) tras actualizar'
    }
    Invoke-Paso 'Humo tras actualizar (escritorio, sin red, llavero)' {
        Test-HumoInstalado -Exe $exe -Temporal $Temporal -Version $VersionNueva
    }
    Invoke-Paso 'Desinstalación sin borrar datos y comprobación de residuos' {
        Uninstall-ProxLaunch -Registro (Join-Path $Registros 'inno-actualizacion-desinstalar.txt')
        Test-SinResiduos -CarpetaInstalacion $carpetaInstalacion
        $datosFinal = Get-Listado -Carpetas (Get-CarpetasDeDatos)
        if ($datosAntes -ne $datosFinal) { throw 'la desinstalación cambió los datos del usuario' }
    }
}

# --- Cuerpo ----------------------------------------------------------------------------------------

Invoke-Principal {
    Set-Location $script:Raiz
    Initialize-Registro 'verificar-windows'
    if ($env:PROXLAUNCH_LAB) {
        throw 'la variable de laboratorio está definida; estos scripts no corren pruebas de laboratorio (RF-E33)'
    }
    Test-Entorno

    $esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $esAdmin) { throw 'se necesita una sesión de administrador (cortafuegos y tarea programada)' }
    if (-not $PermitirFueraDeLaMV -and -not (Test-Path -LiteralPath $script:MarcadorMV)) {
        throw 'esta no es la MV de pruebas (falta el marcador de preparar.ps1); use -PermitirFueraDeLaMV bajo su responsabilidad'
    }

    # Instalador a verificar.
    $provisional = $false
    if (-not $Instalador) {
        $buscar = @('dist', 'dist\provisional')
        foreach ($c in $buscar) {
            $carpeta = Join-Path $script:Raiz $c
            if (-not (Test-Path -LiteralPath $carpeta)) { continue }
            $hallado = @(Get-ChildItem -LiteralPath $carpeta -Filter 'proxlaunch-*-windows-x64-setup.exe' -File |
                    Sort-Object LastWriteTime -Descending)
            if (@($hallado).Count -gt 0) { $Instalador = $hallado[0].FullName; $provisional = ($c -ne 'dist'); break }
        }
    }
    if (-not $Instalador -or -not (Test-Path -LiteralPath $Instalador)) { throw 'no se encontró el instalador (dist\proxlaunch-*-windows-x64-setup.exe)' }
    $setup = (Resolve-Path -LiteralPath $Instalador).Path
    $nombreSetup = Split-Path -Leaf $setup
    if ($setup -like '*\provisional\*') { $provisional = $true }
    $m = [regex]::Match($nombreSetup, '^proxlaunch-(\d+\.\d+\.\d+)-windows-x64-setup\.exe$')
    if (-not $m.Success) { throw "nombre de instalador inesperado: $nombreSetup" }
    $version = $m.Groups[1].Value
    if ($VersionEsperada -and $VersionEsperada -ne $version) { throw "el instalador es de la versión $version, se esperaba $VersionEsperada" }
    $sumaSetup = Get-HashArchivo -Ruta $setup
    Write-Msg "instalador $nombreSetup (versión $version, SHA-256 $sumaSetup)"

    $temporal = Join-Path ([IO.Path]::GetTempPath()) ('plv-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $temporal | Out-Null
    $registros = Join-Path $script:Raiz 'build\registros'
    $carpetaInstalacion = Join-Path $env:LOCALAPPDATA 'Programs\ProxLaunch'
    $exe = Join-Path $carpetaInstalacion 'proxlaunch.exe'
    $script:LlaveroCreado = $false

    try {
        if ($SoloActualizacion) {
            if (-not $InstaladorAnterior -or -not (Test-Path -LiteralPath $InstaladorAnterior)) {
                throw '-SoloActualizacion necesita -InstaladorAnterior <ruta del instalador de la versión anterior>'
            }
            $anterior = (Resolve-Path -LiteralPath $InstaladorAnterior).Path
            Invoke-VerificacionActualizacion -SetupNuevo $setup -VersionNueva $version -SetupAnterior $anterior `
                -Temporal $temporal -Registros $registros
            Write-ResumenTiempos
            Write-Msg "ACTUALIZACIÓN WINDOWS CORRECTA ($(Split-Path -Leaf $anterior) -> $nombreSetup)"
            return
        }

        Invoke-Paso 'Estado inicial limpio' {
            if (Get-EntradaDesinstalacion) {
                Write-Msg 'AVISO: había una instalación previa; se desinstala antes de empezar'
                Uninstall-ProxLaunch -Registro (Join-Path $registros 'inno-desinstalar-previo.txt')
            }
            Remove-DatosDePrueba
            New-DatosDePrueba
            # Entrada de prueba del llavero (CA-E13.3): nunca el servicio real; mejor esfuerzo.
            $valor = [guid]::NewGuid().ToString('N')
            Invoke-Nativo -Ejecutable 'cmdkey.exe' -Capturar -CodigosValidos @(0, 1) -Argumentos @(
                "/generic:$($script:ServicioLlavero)", '/user:prueba', "/pass:$valor") | Out-Null
            $lista = Invoke-Nativo -Ejecutable 'cmdkey.exe' -Capturar -CodigosValidos @(0, 1) -Argumentos @(
                "/list:$($script:ServicioLlavero)")
            $script:LlaveroCreado = (@($lista) -join ' ') -match [regex]::Escape($script:ServicioLlavero)
            if (-not $script:LlaveroCreado) { Write-Msg 'AVISO: no se pudo crear la credencial de prueba; se omite CA-E13.3' }
        }
        $datosAntes = Get-Listado -Carpetas (Get-CarpetasDeDatos)

        Invoke-Paso 'Instalación silenciosa por usuario (/VERYSILENT /CURRENTUSER)' {
            Install-ProxLaunch -Setup $setup -Registro (Join-Path $registros 'inno-instalar-1.txt')
            if (-not (Test-Path -LiteralPath $exe)) { throw "no se instaló $exe" }
            if (-not (Test-Path -LiteralPath (Join-Path $carpetaInstalacion 'unins000.exe'))) { throw 'falta unins000.exe' }
            $entrada = Get-EntradaDesinstalacion
            if ($entrada.PSPath -notlike 'Microsoft.PowerShell.Core\Registry::HKEY_CURRENT_USER*') {
                throw 'la instalación no quedó en el ámbito del usuario (HKCU)'
            }
            if ($entrada.DisplayName -ne 'ProxLaunch' -or $entrada.Publisher -ne 'ProxLaunch' -or $entrada.DisplayVersion -ne $version) {
                throw "datos de «Aplicaciones instaladas» inesperados: '$($entrada.DisplayName)' / '$($entrada.Publisher)' / '$($entrada.DisplayVersion)'"
            }
            if (-not (Test-Path -LiteralPath (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ProxLaunch.lnk'))) {
                throw 'falta el acceso directo del menú Inicio'
            }
            if (Test-Path -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ProxLaunch.lnk')) {
                throw 'se creó el acceso directo del escritorio sin pedirlo (CA-E11.3)'
            }
        }

        Invoke-Paso '--version sin Python en el PATH (CA-E03.2)' {
            if (Get-Command -Name 'python.exe', 'py.exe' -ErrorAction SilentlyContinue) {
                Write-Msg 'AVISO: hay Python en el PATH de esta sesión; --version no depende de él'
            }
            $salidaVersion = Join-Path $temporal 'version.txt'
            $codigo = Start-ProcesoEspera -Ruta $exe -Argumentos @('--version') -LimiteSegundos 60 `
                -Entorno @{ PROXLAUNCH_HUMO_SALIDA = $salidaVersion }
            $texto = if (Test-Path -LiteralPath $salidaVersion) { (Get-Content -LiteralPath $salidaVersion -Raw).Trim() } else { '' }
            if ($codigo -ne 0 -or $texto -ne "ProxLaunch $version") { throw "--version devolvió código $codigo y '$texto'" }
            Write-Msg "--version: $texto"
        }

        Invoke-Paso 'Humo con escritorio, sin red (cortafuegos de salida) y con el llavero real de Windows' {
            Test-HumoInstalado -Exe $exe -Temporal $temporal -Version $version
        }

        Invoke-Paso 'Desinstalación sin borrar datos y comprobación de residuos (CA-E13.1)' {
            Uninstall-ProxLaunch -Registro (Join-Path $registros 'inno-desinstalar-1.txt')
            Test-SinResiduos -CarpetaInstalacion $carpetaInstalacion
            $datosDespues = Get-Listado -Carpetas (Get-CarpetasDeDatos)
            if ($datosAntes -ne $datosDespues) { throw 'la desinstalación cambió los datos del usuario' }
        }

        Invoke-Paso 'Reinstalar encima: una sola entrada (RF-E14, CL-E9)' {
            Install-ProxLaunch -Setup $setup -Registro (Join-Path $registros 'inno-instalar-2.txt')
            Install-ProxLaunch -Setup $setup -Registro (Join-Path $registros 'inno-instalar-3.txt')
            $clave = Get-AppIdClave
            $entradas = @(Get-ChildItem -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' |
                    Where-Object { $_.PSChildName -eq $clave })
            if (@($entradas).Count -ne 1) { throw "hay $(@($entradas).Count) entradas de desinstalación" }
            if (-not (Test-Path -LiteralPath $exe)) { throw 'falta proxlaunch.exe tras reinstalar' }
        }

        Invoke-Paso 'Desinstalación con «Borrar también mis datos» (/BORRARDATOS=1, CA-E13.2)' {
            Uninstall-ProxLaunch -Registro (Join-Path $registros 'inno-desinstalar-2.txt') -BorrarDatos
            Test-SinResiduos -CarpetaInstalacion $carpetaInstalacion
            $r = Get-RutasDePrueba
            if (Test-Path -LiteralPath $r.Interno) { throw 'no se borraron las carpetas de datos de ProxLaunch' }
            # Todo lo ajeno debe seguir intacto.
            foreach ($intacto in @((Join-Path $r.Externo 'ajeno.txt'), (Join-Path $r.Roaming 'dato-roaming.txt'),
                    (Join-Path $r.Senuelo1 'dato.txt'), (Join-Path $r.Senuelo2 'dato.txt'))) {
                if (-not (Test-Path -LiteralPath $intacto)) { throw "se borró algo ajeno: $intacto" }
            }
        }

        Invoke-Paso 'El llavero no se toca (CA-E13.3)' {
            if ($script:LlaveroCreado) {
                $lista = Invoke-Nativo -Ejecutable 'cmdkey.exe' -Capturar -CodigosValidos @(0, 1) -Argumentos @(
                    "/list:$($script:ServicioLlavero)")
                if (-not ((@($lista) -join ' ') -match [regex]::Escape($script:ServicioLlavero))) {
                    throw 'la credencial de prueba desapareció tras desinstalar'
                }
                Write-Msg 'la credencial de prueba sigue en el Administrador de credenciales'
            } else {
                Write-Msg 'omitido: no se pudo crear la credencial de prueba'
            }
        }

        Invoke-Paso 'Instalación para todos los usuarios: el desinstalador ignora /BORRARDATOS=1 (QA-M5-06)' {
            Remove-DatosDePrueba
            New-DatosDePrueba
            $antesTodos = Get-Listado -Carpetas (Get-CarpetasDeDatos)
            Install-ProxLaunch -Setup $setup -Registro (Join-Path $registros 'inno-todos-instalar.txt') -TodosLosUsuarios
            $entrada = Get-EntradaDesinstalacion
            if (-not $entrada -or $entrada.PSPath -notlike 'Microsoft.PowerShell.Core\Registry::HKEY_LOCAL_MACHINE*') {
                throw 'la instalación para todos los usuarios no quedó en HKLM'
            }
            $registroDesinstalar = Join-Path $registros 'inno-todos-desinstalar.txt'
            Uninstall-ProxLaunch -Registro $registroDesinstalar -BorrarDatos
            Test-SinResiduos -CarpetaInstalacion (Join-Path $env:ProgramFiles 'ProxLaunch')
            $despuesTodos = Get-Listado -Carpetas (Get-CarpetasDeDatos)
            if ($antesTodos -ne $despuesTodos) { throw 'con «todos los usuarios» el desinstalador borró datos (debía ignorar /BORRARDATOS=1)' }
            $registroInno = Get-Content -LiteralPath $registroDesinstalar -Raw
            if ($registroInno -notmatch 'Se ignora /BORRARDATOS=1') {
                throw 'el registro de Inno no anota que se ignoró /BORRARDATOS=1'
            }
            Write-Msg 'instalación para todos los usuarios: /BORRARDATOS=1 ignorado, datos intactos y anotado en el registro de Inno'
        }

        # Sello de verificación (lo recoge verificar-todo.sh; INV-E6). Un artefacto provisional no se sella.
        if ($provisional) {
            Write-Msg 'AVISO: instalador provisional; no se escribe sello de verificación'
        } else {
            $carpetaSello = Join-Path $script:Raiz 'build\verificacion'
            New-Item -ItemType Directory -Force -Path $carpetaSello | Out-Null
            $sello = Join-Path $carpetaSello "$nombreSetup.ok"
            $contenido = "{0}  {1}`r`nversion={2}`r`nfecha={3}`r`n" -f $sumaSetup, $nombreSetup, $version, (Get-Date -Format 's')
            [System.IO.File]::WriteAllText($sello, $contenido, $script:Utf8SinBom)
            Write-Msg "sello de verificación: build\verificacion\$nombreSetup.ok"
        }
    } finally {
        Get-NetFirewallRule -DisplayName $script:NombreRegla -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Unregister-ScheduledTask -TaskName $script:NombreTarea -Confirm:$false -ErrorAction SilentlyContinue
        if ($script:LlaveroCreado) {
            Invoke-Nativo -Ejecutable 'cmdkey.exe' -Capturar -CodigosValidos @(0, 1) -Argumentos @(
                "/delete:$($script:ServicioLlavero)") | Out-Null
        }
        Remove-DatosDePrueba
        Remove-Item -LiteralPath $temporal -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-ResumenTiempos
    Write-Msg "VERIFICACIÓN WINDOWS CORRECTA ($nombreSetup)"
}
