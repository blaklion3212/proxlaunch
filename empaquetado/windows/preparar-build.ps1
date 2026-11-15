# Instala en la MV de Windows las herramientas de construcción (equivalente de linux/preparar-build.sh):
# CPython 3.13 e Inno Setup 6. Los instaladores los descarga el anfitrión (con SHA-256 fijado en
# empaquetado\entornos\windows\herramientas.json) y los copia por scp a ~\herramientas. Aquí se
# VUELVE a comprobar la suma y la firma Authenticode antes de ejecutar nada. Todo se instala para el
# usuario actual (sin administrador) y no se modifica el PATH.
#
# Uso: empaquetado\windows\preparar-build.ps1 [-Carpeta <carpeta con los instaladores>]
[CmdletBinding()]
param([string]$Carpeta = (Join-Path $HOME 'herramientas'))

. (Join-Path $PSScriptRoot '..\comun\lib.ps1')
$script:NombreScript = 'preparar-build'

Invoke-Principal {
    Set-Location $script:Raiz
    Initialize-Registro 'preparar-build'
    Test-Entorno

    $inventario = Get-Content -LiteralPath (Join-Path $script:Raiz 'empaquetado\entornos\windows\herramientas.json') `
        -Raw -Encoding UTF8 | ConvertFrom-Json
    $herramientas = $inventario.herramientas

    # Comprobación de suma y de firma de cada instalador.
    function Test-Instalador {
        param($Herramienta)
        $ruta = Join-Path $Carpeta $Herramienta.archivo
        if (-not (Test-Path -LiteralPath $ruta)) { throw "falta $($Herramienta.archivo) en $Carpeta" }
        $real = Get-HashArchivo -Ruta $ruta
        if ($real -ne $Herramienta.sha256) {
            throw "la suma SHA-256 de $($Herramienta.archivo) no coincide con la fijada (real $real)"
        }
        $firma = Get-AuthenticodeSignature -LiteralPath $ruta
        $sujeto = if ($firma.SignerCertificate) { $firma.SignerCertificate.Subject } else { '' }
        if ($firma.Status -ne 'Valid' -or $sujeto -notlike "*$($Herramienta.editor_authenticode)*") {
            throw "la firma de $($Herramienta.archivo) no es válida o no es de '$($Herramienta.editor_authenticode)' (estado $($firma.Status))"
        }
        Write-Msg "$($Herramienta.nombre): SHA-256 y firma Authenticode correctos"
        return $ruta
    }

    $destinoPython = Join-Path $HOME 'herramientas\python313'
    Invoke-Paso 'Python 3.13 (instalador oficial, solo para este usuario)' {
        $instalador = Test-Instalador -Herramienta $herramientas.python
        $pythonExe = Join-Path $destinoPython 'python.exe'
        $ya = $false
        if (Test-Path -LiteralPath $pythonExe) {
            $v = (& $pythonExe -c 'import sys; print(sys.version.split()[0])').Trim()
            $ya = ($v -eq $herramientas.python.version)
        }
        if ($ya) {
            Write-Msg "Python $($herramientas.python.version) ya instalado"
        } else {
            $registroInstalador = Join-Path $script:Raiz 'build\registros\instalador-python.txt'
            $parametros = @('/quiet', 'InstallAllUsers=0', "TargetDir=`"$destinoPython`"", 'PrependPath=0',
                'Include_launcher=0', 'Include_test=0', 'Include_doc=0', 'Include_tcltk=0', 'Include_pip=1',
                'Shortcuts=0', 'AssociateFiles=0', 'CompileAll=0', '/log', "`"$registroInstalador`"")
            $codigo = Start-ProcesoEspera -Ruta $instalador -Argumentos $parametros -LimiteSegundos 900
            if ($codigo -ne 0) { throw "el instalador de Python terminó con el código $codigo" }
        }
        $v = (& $pythonExe -c 'import sys; print(sys.version.split()[0])').Trim()
        if ($v -ne $herramientas.python.version) { throw "Python instalado es $v, se esperaba $($herramientas.python.version)" }
        Write-Msg "Python $v listo en ~\herramientas\python313"
    }

    $destinoInno = Join-Path $HOME 'herramientas\innosetup6'
    Invoke-Paso 'Inno Setup 6 (instalador oficial, solo para este usuario)' {
        $instalador = Test-Instalador -Herramienta $herramientas.innosetup
        $iscc = Join-Path $destinoInno 'ISCC.exe'
        if (-not (Test-Path -LiteralPath $iscc)) {
            $registroInstalador = Join-Path $script:Raiz 'build\registros\instalador-innosetup.txt'
            $parametros = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER', '/NOICONS',
                "/DIR=`"$destinoInno`"", "/LOG=`"$registroInstalador`"")
            $codigo = Start-ProcesoEspera -Ruta $instalador -Argumentos $parametros -LimiteSegundos 600
            if ($codigo -ne 0) { throw "el instalador de Inno Setup terminó con el código $codigo" }
        }
        if (-not (Test-Path -LiteralPath $iscc)) { throw 'no se encontró ISCC.exe tras instalar Inno Setup' }
        if (-not (Test-Path -LiteralPath (Join-Path $destinoInno 'Languages\Spanish.isl'))) {
            throw 'Inno Setup no trae Languages\Spanish.isl'
        }
        Write-Msg "Inno Setup $($herramientas.innosetup.version) listo en ~\herramientas\innosetup6"
    }

    Write-ResumenTiempos
    Write-Msg 'HERRAMIENTAS DE CONSTRUCCIÓN LISTAS'
}
