# Calidad de ProxLaunch en Windows (RF-E32, RF-E33): equivalente de calidad.sh.
# Lockfile con hashes, ruff, mypy, pytest y cobertura. Orden fijo; cada paso falla el script si falla.
# Nunca ejecuta pruebas de laboratorio (D-15): usa -m "not integracion" y exige que la variable
# de laboratorio no esté definida.
#
# Uso: empaquetado\calidad.ps1 [-Registro <archivo>]
#   -Registro  añade la salida a un registro ya iniciado (lo usa construir-windows.ps1).
[CmdletBinding()]
param([string]$Registro = '')

. (Join-Path $PSScriptRoot 'comun\lib.ps1')
$script:NombreScript = 'calidad'

Invoke-Principal {
    Set-Location $script:Raiz
    if ($Registro) { $script:Registro = $Registro } else { Initialize-Registro 'calidad' }

    # Guarda de RF-E33: la variable que habilita las pruebas de laboratorio debe estar sin definir.
    if ($env:PROXLAUNCH_LAB) {
        throw 'la variable de laboratorio está definida; estos scripts no corren pruebas de laboratorio (RF-E33)'
    }
    Test-Entorno

    $venv = Join-Path $script:Raiz 'build\venv-calidad'
    $script:PyCalidad = $null
    Invoke-Paso 'Entorno desde el lockfile (--require-hashes)' {
        $script:PyCalidad = New-EntornoPython -Carpeta $venv -Lockfiles @('empaquetado\requisitos\windows-calidad.txt')
    }
    $py = $script:PyCalidad
    Invoke-Paso 'Lockfiles coherentes' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\comprobar_lock.py')
    }
    Invoke-Paso 'Revisión estática de los scripts' {
        Invoke-Nativo -Ejecutable $py -Argumentos @('-I', 'empaquetado\comun\revisar_estatico.py')
    }
    if (Select-String -Path 'pyproject.toml' -SimpleMatch -Quiet -Pattern '--force-enable-socket') {
        throw 'pyproject.toml no debe habilitar sockets reales (RF-E33)'
    }

    $ruff = Join-Path $venv 'Scripts\ruff.exe'
    $mypy = Join-Path $venv 'Scripts\mypy.exe'
    Invoke-Paso 'ruff check' {
        Invoke-Nativo -Ejecutable $ruff -Argumentos @('check', 'src', 'tests', 'empaquetado')
    }
    Invoke-Paso 'ruff format --check' {
        Invoke-Nativo -Ejecutable $ruff -Argumentos @('format', '--check', 'src', 'tests', 'empaquetado')
    }
    Invoke-Paso 'mypy src' {
        Invoke-Nativo -Ejecutable $mypy -Argumentos @('src')
    }

    $entorno = @{
        QT_QPA_PLATFORM = 'offscreen'
        COVERAGE_FILE   = (Join-Path $script:Raiz 'build\.coverage')
    }
    Invoke-Paso 'pytest (sin pruebas de laboratorio)' {
        Invoke-Nativo -Ejecutable $py -Entorno $entorno -Argumentos @(
            '-m', 'pytest', '-q', '-m', 'not integracion', '--cov=proxlaunch', '--cov-report=',
            '-p', 'no:cacheprovider')
    }
    Invoke-Paso 'Cobertura del núcleo >= 85 %' {
        Invoke-Nativo -Ejecutable $py -Entorno $entorno -Argumentos @(
            '-m', 'coverage', 'report', '--include=*/proxlaunch/nucleo/*', '--fail-under=85')
    }
    Invoke-Paso 'Cobertura global >= 75 %' {
        Invoke-Nativo -Ejecutable $py -Entorno $entorno -Argumentos @(
            '-m', 'coverage', 'report', '--fail-under=75')
    }

    Write-ResumenTiempos
    Write-Msg 'CALIDAD CORRECTA'
}
