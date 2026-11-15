# Construye el instalador de ProxLaunch para Windows (RF-E01, RF-E04, RF-E34).
# Pensado para la MV de pruebas de Windows 11 (RF-E40), con las herramientas que instala
# empaquetado\windows\preparar-build.ps1 (CPython 3.13 e Inno Setup 6 con suma fijada).
#
# Orden: versión -> calidad -> entorno desde lockfile -> revisión estática -> .qm -> iconos aprobados
#        -> avisos -> PyInstaller -> comprobaciones del congelado -> humo previo -> Inno Setup
#        -> presupuesto de tamaño -> paso de firma (desactivado salvo configuración explícita).
# Nada se escribe en dist\ si algún paso falla. Las sumas (SHA256SUMS) NO se escriben aquí: solo las
# escribe sumas.py tras la verificación instalada (verificar-windows.ps1, INV-E6).
#
# Uso: empaquetado\construir-windows.ps1 [-IconosProvisionales] [-SinCalidad]
#   -IconosProvisionales  ya no hace falta con los iconos aprobados; se conserva para usar iconos sin
#                         aprobar (solo verificación interna). El artefacto queda en dist\provisional\.
#   -SinCalidad           omite calidad.ps1 (atajo de desarrollo; también deja el artefacto como provisional).
#
# Firma (RF-E24): DESACTIVADA. Se activa solo si la variable PROXLAUNCH_FIRMA_CONFIG apunta a un
# archivo JSON FUERA del repositorio con: certificado (ruta al archivo del certificado),
# variable_contrasena (nombre de la variable de entorno que contiene la contraseña) y,
# opcionalmente, url_marca_de_tiempo. La clave y su contraseña nunca viven en el repositorio.
[CmdletBinding()]
param(
    [switch]$IconosProvisionales,
    [switch]$SinCalidad
)

. (Join-Path $PSScriptRoot 'comun\lib.ps1')
$script:NombreScript = 'construir-windows'

# Invoke-PasoFirma <ruta> : firma Authenticode opcional; sin configuración explícita se omite con un mensaje.
function Invoke-PasoFirma {
    param([Parameter(Mandatory = $true)][string]$Archivo)
    $configuracion = $env:PROXLAUNCH_FIRMA_CONFIG
    if (-not $configuracion) {
        Write-Msg 'Firma Authenticode OMITIDA: no hay configuración explícita (PROXLAUNCH_FIRMA_CONFIG). El instalador sale SIN FIRMAR (RF-E24).'
        return
    }
    $ruta = (Resolve-Path -LiteralPath $configuracion).Path
    $raizNorm = $script:Raiz.TrimEnd('\') + '\'
    if ($ruta.StartsWith($raizNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'la configuración de firma debe estar FUERA del repositorio'
    }
    $cfg = Get-Content -LiteralPath $ruta -Raw -Encoding UTF8 | ConvertFrom-Json
    $certificado = (Resolve-Path -LiteralPath $cfg.certificado).Path
    if ($certificado.StartsWith($raizNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'el certificado debe estar FUERA del repositorio'
    }
    $variable = [string]$cfg.variable_contrasena
    $valor = [Environment]::GetEnvironmentVariable($variable, 'Process')
    if (-not $valor) { throw "la variable '$variable' (contraseña del certificado) no está definida" }
    $segura = ConvertTo-SecureString -String $valor -AsPlainText -Force
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certificado, $segura)
    $parametros = @{ FilePath = $Archivo; Certificate = $cert; HashAlgorithm = 'SHA256' }
    if ($cfg.PSObject.Properties.Name -contains 'url_marca_de_tiempo' -and $cfg.url_marca_de_tiempo) {
        $parametros['TimestampServer'] = [string]$cfg.url_marca_de_tiempo
    }
    $resultado = Set-AuthenticodeSignature @parametros
    if ($resultado.Status -ne 'Valid') { throw "la firma no quedó válida: $($resultado.Status)" }
    Write-Msg "Firma Authenticode aplicada a $(Split-Path -Leaf $Archivo) (sin mostrar clave ni contraseña)."
}

Invoke-Principal {
    Set-Location $script:Raiz
    Initialize-Registro 'construir-windows'
    $provisional = [bool]($IconosProvisionales -or $SinCalidad)

    if ($env:PROXLAUNCH_LAB) {
        throw 'la variable de laboratorio está definida; estos scripts no corren pruebas de laboratorio (RF-E33)'
    }
    Test-Entorno

    # Epoch fijo para fechas (RF-E04b): el del entorno (lo pasa verificar-todo.sh) o el de LICENSE.
    if (-not $env:SOURCE_DATE_EPOCH) {
        $epoch = [DateTimeOffset]::new((Get-Item -LiteralPath 'LICENSE').LastWriteTimeUtc).ToUnixTimeSeconds()
        $env:SOURCE_DATE_EPOCH = "$epoch"
    }

    # 1. Versión (CA-E10.1/E10.3): falla antes de construir si no es SemVer o es incoherente.
    $pyBuild = Get-PythonBuild
    $script:Version = ((Invoke-Nativo -Ejecutable $pyBuild -Capturar -Argumentos @(
                '-I', 'empaquetado\comun\version.py', '--comprobar')) -join '').Trim()
    $script:VersionWin = ((Invoke-Nativo -Ejecutable $pyBuild -Capturar -Argumentos @(
                '-I', 'empaquetado\comun\version.py', '--windows')) -join '').Trim()
    if ($script:Version -notmatch '^\d+\.\d+\.\d+$') { throw "versión no válida: '$($script:Version)'" }
    $version = $script:Version
    $versionWin = $script:VersionWin
    Write-Msg "versión $version"

    if (-not $SinCalidad) {
        Invoke-Paso 'Calidad completa' {
            $global:LASTEXITCODE = 0
            & (Join-Path $script:Raiz 'empaquetado\calidad.ps1') -Registro $script:Registro
            if ($LASTEXITCODE -ne 0) { throw 'calidad.ps1 falló' }
        }
    } else {
        Write-Msg 'AVISO: se omite la calidad; el artefacto será provisional (no publicable)'
    }

    $venv = Join-Path $script:Raiz 'build\venv-construccion'
    $script:PyConstruccion = $null
    Invoke-Paso 'Entorno de construcción desde el lockfile' {
        $script:PyConstruccion = New-EntornoPython -Carpeta $venv -Lockfiles @(
            'empaquetado\requisitos\windows-construccion.txt', 'empaquetado\requisitos\windows-ejecucion.txt')
    }
    $py = $script:PyConstruccion
    Invoke-Paso 'Revisión estática (CA-E30/E33/E35/E21/E24)' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\revisar_estatico.py')
    }
    Invoke-Paso 'Traducciones (.qm)' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\compilar_qm.py')
    }

    # Iconos: se COPIAN los aprobados por el usuario (empaquetado\iconos) tras verificar su
    # SHA256SUMS; no se redibujan (otra versión de Qt cambiaría los píxeles).
    Invoke-Paso 'Iconos aprobados (copia verificada)' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\iconos.py', 'copiar', '--salida', 'build\iconos')
    }
    Invoke-Paso 'Iconos (comprobación)' {
        $a = @('-I', 'empaquetado\comun\iconos.py', 'verificar', '--salida', 'build\iconos')
        if ($provisional) { $a += '--provisional' }
        Invoke-Nativo -Ejecutable $py -Argumentos $a
    }
    Invoke-Paso 'Avisos de terceros' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\avisos.py',
            '--lock', 'empaquetado\requisitos\windows-ejecucion.txt', '--salida', 'build\THIRD-PARTY-NOTICES.txt')
    }

    Invoke-Paso 'Congelado con PyInstaller' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-m', 'PyInstaller', '--noconfirm', '--clean',
            '--distpath', 'build\pyi\dist', '--workpath', 'build\pyi\work', 'empaquetado\proxlaunch.spec')
    }
    $congelado = Join-Path $script:Raiz 'build\pyi\dist\proxlaunch'
    $exe = Join-Path $congelado 'proxlaunch.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'PyInstaller no produjo proxlaunch.exe' }

    # Salida del congelado (sin consola): el informe va al archivo de PROXLAUNCH_HUMO_SALIDA.
    $temporal = Join-Path $script:Raiz 'build\temporal'
    New-Item -ItemType Directory -Force -Path $temporal | Out-Null
    $salidaHumo = Join-Path $temporal 'salida-congelado.txt'

    Invoke-Paso 'Comprobaciones del congelado' {
        Remove-Item -LiteralPath $salidaHumo -Force -ErrorAction SilentlyContinue
        $codigo = Start-ProcesoEspera -Ruta $exe -Argumentos @('--version') `
            -Entorno @{ PROXLAUNCH_HUMO_SALIDA = $salidaHumo } -LimiteSegundos 60
        $texto = if (Test-Path -LiteralPath $salidaHumo) { (Get-Content -LiteralPath $salidaHumo -Raw).Trim() } else { '' }
        if ($codigo -ne 0 -or $texto -ne "ProxLaunch $version") {
            throw "--version devolvió código $codigo y '$texto'"
        }
        # CA-E19.2: sin pruebas, sin .ts ni módulos de Qt no usados.
        $sobrantes = @(Get-ChildItem -LiteralPath $congelado -Recurse -Force | Where-Object {
            $_.Name -like '*.ts' -or $_.FullName -like '*\tests\*' -or $_.Name -like 'Qt6Qml*' `
                -or $_.Name -like 'Qt6Quick*' -or $_.Name -like 'Qt6WebEngine*'
        })
        if ($sobrantes.Count -gt 0) { throw "el congelado contiene archivos que debían excluirse: $($sobrantes[0].FullName)" }
        # CA-E23.2: Qt como bibliotecas separadas.
        if (-not (Get-ChildItem -LiteralPath $congelado -Recurse -Filter 'Qt6Core.dll')) { throw 'falta Qt6Core.dll' }
        # RF-E08: el plugin de plataforma de Windows.
        if (-not (Get-ChildItem -LiteralPath $congelado -Recurse -Filter 'qwindows.dll')) { throw 'falta el plugin qwindows.dll' }
        # CA-E03.3: una sola versión de Python.
        $pythons = @(Get-ChildItem -LiteralPath $congelado -Recurse -File | Where-Object { $_.Name -match '^python3\d+\.dll$' })
        if ($pythons.Count -ne 1) { throw "no hay exactamente una DLL de Python ($($pythons.Count))" }
        # CA-E06.1: recursos obligatorios.
        $recursos = @('LICENSE', 'THIRD-PARTY-NOTICES.txt',
            'proxlaunch\recursos\traducciones\proxlaunch_es.qm',
            'proxlaunch\recursos\fuentes\OpenSans-Variable.ttf',
            'proxlaunch\recursos\fuentes\OpenSans-OFL.txt',
            'proxlaunch\recursos\fuentes\JetBrainsMono-Variable.ttf',
            'proxlaunch\interfaz\tema\plantilla.qss',
            'proxlaunch\recursos\marca\proxlaunch-icono-sin-texto.svg')
        foreach ($r in $recursos) {
            if (-not (Test-Path -LiteralPath (Join-Path $congelado "_internal\$r"))) { throw "falta $r en el congelado" }
        }
    }

    # Humo previo (RF-E34): del árbol de fuentes (CA-E17.3) y del congelado, con la plataforma
    # offscreen. El humo oficial es el del instalador ya instalado (verificar-windows.ps1).
    Invoke-Paso 'Humo previo (fuentes y congelado, offscreen)' {
        $lineas = Invoke-Nativo -Ejecutable $py -Capturar -Entorno @{
            QT_QPA_PLATFORM = 'offscreen'; PYTHONPATH = (Join-Path $script:Raiz 'src')
        } -Argumentos @('-m', 'proxlaunch', '--prueba-de-humo', '--permitir-sin-llavero')
        $json = @($lineas | Where-Object { $_ -like '{*' })
        if ($json.Count -ne 1) { throw 'el humo de las fuentes no produjo el informe esperado' }
        Write-Msg "humo del árbol de fuentes: $($json[0])"

        Remove-Item -LiteralPath $salidaHumo -Force -ErrorAction SilentlyContinue
        $codigo = Start-ProcesoEspera -Ruta $exe -Argumentos @('--prueba-de-humo', '--permitir-sin-llavero') `
            -Entorno @{ QT_QPA_PLATFORM = 'offscreen'; PROXLAUNCH_HUMO_SALIDA = $salidaHumo } -LimiteSegundos 60
        $informe = if (Test-Path -LiteralPath $salidaHumo) { (Get-Content -LiteralPath $salidaHumo -Raw).Trim() } else { '' }
        if ($codigo -ne 0 -or -not $informe.StartsWith('{')) { throw "el humo del congelado falló (código $codigo): $informe" }
        Write-Msg "humo del congelado: $informe"
    }

    # --- Instalador con Inno Setup ----------------------------------------------------------------
    $iconos = Join-Path $script:Raiz 'build\iconos'
    $salidaInno = Join-Path $script:Raiz 'build\inno'
    $nombreSetup = "proxlaunch-$version-windows-x64-setup.exe"
    $setup = Join-Path $salidaInno $nombreSetup
    Invoke-Paso 'Inno Setup (ISCC)' {
        $iscc = Get-Iscc
        $idiomas = Join-Path (Split-Path -Parent $iscc) 'Languages\Spanish.isl'
        if (-not (Test-Path -LiteralPath $idiomas)) { throw "falta Spanish.isl en la instalación de Inno Setup ($idiomas)" }
        New-Item -ItemType Directory -Force -Path $salidaInno | Out-Null
        Remove-Item -LiteralPath $setup -Force -ErrorAction SilentlyContinue
        Invoke-Nativo -Ejecutable $iscc -Argumentos @('/Qp', "/DVersion=$version", "/DVersionWin=$versionWin",
            "/DOrigen=$congelado", "/DIconos=$iconos", "/DRaiz=$($script:Raiz)", "/O$salidaInno",
            (Join-Path $script:Raiz 'empaquetado\windows\proxlaunch.iss'))
        if (-not (Test-Path -LiteralPath $setup)) { throw "ISCC no produjo $nombreSetup" }
        $info = (Get-Item -LiteralPath $setup).VersionInfo
        if (([string]$info.FileVersion).Trim() -ne $versionWin) { throw "la versión del instalador es '$($info.FileVersion)', se esperaba $versionWin" }
    }

    Invoke-Paso 'Presupuesto de tamaño (CA-E19.1)' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\presupuesto.py', 'windows', $setup, $congelado)
    }

    Invoke-Paso 'Firma de código (opcional, desactivada por defecto)' {
        Invoke-PasoFirma -Archivo $setup
    }

    # --- Publicación local en dist\ (solo si todo salió bien) -------------------------------------
    $destino = if ($provisional) { Join-Path $script:Raiz 'dist\provisional' } else { Join-Path $script:Raiz 'dist' }
    New-Item -ItemType Directory -Force -Path $destino | Out-Null
    Copy-Item -LiteralPath $setup -Destination (Join-Path $destino $nombreSetup) -Force
    if ($provisional) {
        Set-Content -LiteralPath (Join-Path $destino 'LEEME-NO-PUBLICABLE.txt') -Encoding UTF8 `
            -Value 'Artefacto provisional (iconos sin aprobar o calidad omitida): NO publicable.'
    }
    $mb = '{0:N1}' -f ((Get-Item -LiteralPath (Join-Path $destino $nombreSetup)).Length / 1MB)
    Write-Msg "artefacto: dist\$(if ($provisional) { 'provisional\' })$nombreSetup ($mb MB)"
    if ($provisional) { Write-Msg 'AVISO: artefacto PROVISIONAL; no entrará en SHA256SUMS' }
    Write-ResumenTiempos
    Write-Msg 'CONSTRUCCIÓN CORRECTA (falta la verificación instalada: verificar-windows.ps1)'
}
