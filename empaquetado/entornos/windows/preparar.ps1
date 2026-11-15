# Preparación de la MV de pruebas de Windows 11 (RF-E40, AR-9, sección 6.2). Se ejecuta UNA sola vez,
# como administrador, dentro de la MV, desde la unidad de apoyo (volumen «APOYO», solo lectura).
# Este archivo es UTF-8 con BOM: Windows PowerShell 5.1 lo necesita para leer los acentos.
#
# Qué hace:
#   1. instala OpenSSH Server (capacidad de Windows) y lo deja en inicio automático;
#   2. autoriza la clave pública de la MV para el usuario «prueba» (administrador): archivo
#      administrators_authorized_keys con las ACL correctas; desactiva el acceso SSH con contraseña;
#   3. pone PowerShell como intérprete por defecto de sshd;
#   4. configura el inicio de sesión automático de «prueba» con la contraseña que generó el anfitrión
#      (se lee de contrasena.txt, en esta misma unidad; nunca se escribe en pantalla ni en registros) y
#      evita el bloqueo de pantalla (el humo necesita escritorio interactivo);
#   5. deja un marcador que identifica esta máquina como MV de pruebas (verificar-windows.ps1 lo exige);
#   6. informa de TPM 2.0 y Secure Boot (Get-Tpm, Confirm-SecureBootUEFI; M-E10, CA-E40.3).
# Necesita Internet (red de usuario de QEMU) solo para descargar la capacidad OpenSSH Server.
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Aviso {
    param([string]$Texto)
    Write-Host "[preparar] $Texto"
}

try {
    $esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $esAdmin) {
        throw 'Abra PowerShell con «Ejecutar como administrador» y vuelva a lanzar la orden.'
    }
    if ($env:USERNAME -ne 'prueba') {
        throw "Este script debe ejecutarse con la cuenta «prueba» (ahora es «$($env:USERNAME)»)."
    }

    $clavePublica = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'clave.pub') -Raw -Encoding ASCII).Trim()
    if ($clavePublica -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+') { throw 'clave.pub no es una clave pública ed25519.' }
    $contrasena = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'contrasena.txt') -Raw -Encoding ASCII).Trim()
    if ($contrasena.Length -lt 12) { throw 'contrasena.txt no es válida.' }

    # 0. Comprueba que la contraseña de la cuenta es la que dio el anfitrión (si no, el inicio automático fallaría).
    Add-Type -AssemblyName System.DirectoryServices.AccountManagement
    $contexto = New-Object System.DirectoryServices.AccountManagement.PrincipalContext(
        [System.DirectoryServices.AccountManagement.ContextType]::Machine)
    if (-not $contexto.ValidateCredentials('prueba', $contrasena)) {
        throw ('La contraseña de la cuenta «prueba» no es la que indicó el anfitrión. ' +
            'Cámbiela con:  net user prueba *   (escriba la contraseña que le dio el anfitrión) y repita esta orden.')
    }
    Write-Aviso 'La contraseña de «prueba» es la correcta.'

    # 1. OpenSSH Server.
    $capacidad = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' | Select-Object -First 1
    if (-not $capacidad) { throw 'Windows no ofrece la capacidad OpenSSH Server.' }
    if ($capacidad.State -ne 'Installed') {
        Write-Aviso 'Instalando OpenSSH Server (puede tardar unos minutos; necesita Internet)...'
        Add-WindowsCapability -Online -Name $capacidad.Name | Out-Null
    }
    Set-Service -Name sshd -StartupType Automatic
    if ((Get-Service -Name sshd).Status -ne 'Running') { Start-Service -Name sshd }
    Write-Aviso 'OpenSSH Server instalado, automático y en marcha.'

    # La regla de entrada la crea la capacidad; si faltara, se crea (el reenvío del anfitrión llega por el puerto 22).
    if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True `
            -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    }
    # La regla de la capacidad solo vale en redes privadas y Windows marca la red de QEMU como pública
    # (visto en la primera instalación): la red de esta MV de pruebas pasa a privada.
    Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } |
        Set-NetConnectionProfile -NetworkCategory Private

    # 3. PowerShell como intérprete por defecto de sshd.
    New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null
    New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name 'DefaultShell' -PropertyType String -Force `
        -Value (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') | Out-Null

    # 2. Clave pública para administradores (el usuario «prueba» es administrador).
    $carpetaSsh = Join-Path $env:ProgramData 'ssh'
    New-Item -ItemType Directory -Force -Path $carpetaSsh | Out-Null
    $claves = Join-Path $carpetaSsh 'administrators_authorized_keys'
    [System.IO.File]::WriteAllText($claves, $clavePublica + "`n", [System.Text.Encoding]::ASCII)
    # ACL: solo SYSTEM y Administradores (por SID, independiente del idioma). sshd rechaza permisos más abiertos.
    & icacls.exe $claves /inheritance:r /grant '*S-1-5-18:(F)' /grant '*S-1-5-32-544:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron fijar los permisos de administrators_authorized_keys.' }

    # Solo acceso por clave (sin contraseña) y reinicio de sshd.
    $configuracion = Join-Path $carpetaSsh 'sshd_config'
    $lineas = @()
    if (Test-Path -LiteralPath $configuracion) { $lineas = @(Get-Content -LiteralPath $configuracion -Encoding ASCII) }
    $lineas = @($lineas | Where-Object { $_ -notmatch '^\s*#?\s*PasswordAuthentication\b' })
    # La directiva debe ir antes del primer bloque «Match»; si no hay ninguno, al final.
    $nuevas = New-Object System.Collections.Generic.List[string]
    $puesta = $false
    foreach ($l in $lineas) {
        if (-not $puesta -and $l -match '^\s*Match\b') { $nuevas.Add('PasswordAuthentication no'); $puesta = $true }
        $nuevas.Add($l)
    }
    if (-not $puesta) { $nuevas.Add('PasswordAuthentication no') }
    $lineas = $nuevas.ToArray()
    [System.IO.File]::WriteAllLines($configuracion, [string[]]$lineas, [System.Text.Encoding]::ASCII)
    Restart-Service -Name sshd
    Write-Aviso 'Clave pública autorizada; acceso SSH solo con clave.'

    # 4. Inicio de sesión automático de «prueba» y sin bloqueo de pantalla.
    $winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    Set-ItemProperty -Path $winlogon -Name 'AutoAdminLogon' -Value '1' -Type String
    Set-ItemProperty -Path $winlogon -Name 'DefaultUserName' -Value 'prueba' -Type String
    Set-ItemProperty -Path $winlogon -Name 'DefaultDomainName' -Value $env:COMPUTERNAME -Type String
    Set-ItemProperty -Path $winlogon -Name 'DefaultPassword' -Value $contrasena -Type String
    & powercfg.exe /change monitor-timeout-ac 0 | Out-Null
    & powercfg.exe /change standby-timeout-ac 0 | Out-Null
    New-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization' -Force | Out-Null
    New-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization' -Name 'NoLockScreen' `
        -PropertyType DWord -Value 1 -Force | Out-Null
    Write-Aviso 'Inicio de sesión automático de «prueba» configurado (sin bloqueo de pantalla).'

    # 5. Marcador de MV de pruebas.
    $carpetaMarca = Join-Path $env:ProgramData 'ProxLaunch-MV'
    New-Item -ItemType Directory -Force -Path $carpetaMarca | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $carpetaMarca 'es-mv-de-prueba.txt'),
        "MV de pruebas de ProxLaunch preparada el $(Get-Date -Format 's')`r`n", [System.Text.Encoding]::UTF8)

    # 6. TPM 2.0 y Secure Boot.
    Write-Aviso '--- Comprobación del hardware virtual ---'
    try {
        $tpm = Get-Tpm
        $especificacion = ''
        try {
            $especificacion = [string](Get-CimInstance -Namespace 'root\cimv2\Security\MicrosoftTpm' -ClassName Win32_Tpm).SpecVersion
        } catch { $especificacion = '(no disponible)' }
        Write-Aviso ("TPM presente: {0}; listo: {1}; especificación: {2}" -f $tpm.TpmPresent, $tpm.TpmReady, $especificacion)
        if (-not $tpm.TpmPresent -or $especificacion -notmatch '^2\.0') { Write-Aviso 'AVISO: no se detecta un TPM 2.0.' }
    } catch {
        Write-Aviso "AVISO: no se pudo consultar el TPM ($($_.Exception.Message))"
    }
    try {
        $seguro = Confirm-SecureBootUEFI
        Write-Aviso ("Secure Boot activado: {0}" -f $seguro)
        if (-not $seguro) { Write-Aviso 'AVISO: Secure Boot no está activo.' }
    } catch {
        Write-Aviso "AVISO: Secure Boot no se pudo comprobar ($($_.Exception.Message))"
    }

    Write-Host ''
    Write-Aviso 'LISTO. Ya puede cerrar esta ventana de PowerShell.'
    Write-Aviso 'En el anfitrión ejecute:  empaquetado/entornos/mv.sh arrancar windows11'
    exit 0
} catch {
    Write-Host "[preparar] ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
