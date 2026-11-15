; Instalador de ProxLaunch para Windows (RF-E01, RF-E11, RF-E13, RF-E14, RF-E24; AR-10).
; Lo compila construir-windows.ps1 con ISCC y estas definiciones (no se compila a mano):
;   /DVersion=0.5.0  /DVersionWin=0.5.0.0  /DOrigen=<carpeta del congelado>
;   /DIconos=<carpeta con proxlaunch.ico>  /DRaiz=<raíz del repositorio>
; Este archivo es UTF-8 sin BOM (Inno Setup 6.3 o posterior lo lee bien; igual que LICENSE).
;
; Decisiones: ámbito «solo para mí» por defecto (sin administrador) con diálogo para elegir «todos
; los usuarios»; datos del usuario conservados al desinstalar salvo que se pida lo contrario (y solo
; en la instalación por usuario: con «todos los usuarios» nunca se borran datos);
; el llavero (Administrador de credenciales) NUNCA se toca; sin firma de código (RF-E24).

#ifndef Version
  #error Falta /DVersion=X.Y.Z
#endif
#ifndef VersionWin
  #error Falta /DVersionWin=X.Y.Z.0
#endif
#ifndef Origen
  #error Falta /DOrigen=<carpeta del congelado>
#endif
#ifndef Iconos
  #error Falta /DIconos=<carpeta de los iconos>
#endif
#ifndef Raiz
  #error Falta /DRaiz=<raíz del repositorio>
#endif

[Setup]
; Identificador FIJO entre versiones (RF-E14, INV-E3): cambiarlo rompería las actualizaciones.
AppId={{3D2EDDDE-BCD2-4541-A4A9-4892CB501210}
AppName=ProxLaunch
AppVersion={#Version}
AppVerName=ProxLaunch {#Version}
AppPublisher=ProxLaunch
; Detecta la aplicación abierta si esta crea el mutex con este nombre; además CloseApplications
; (Restart Manager) pide cerrarla si tiene archivos de la instalación en uso (CA-E13.5, CA-E14.3).
AppMutex=ProxLaunch.InstanciaUnica
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#VersionWin}
VersionInfoCompany=ProxLaunch
VersionInfoProductName=ProxLaunch
VersionInfoDescription=Instalador de ProxLaunch
DefaultDirName={autopf}\ProxLaunch
DisableProgramGroupPage=yes
DisableDirPage=no
DisableReadyPage=no
ShowLanguageDialog=no
LicenseFile={#Raiz}\LICENSE
; Ámbito: «solo para mí» por defecto (sin administrador); el diálogo permite «para todos» (UAC).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Windows 10 o posterior, 64 bits (CA-E01.4).
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile={#Iconos}\proxlaunch.ico
UninstallDisplayIcon={app}\proxlaunch.exe
UninstallDisplayName=ProxLaunch
Compression=lzma2/max
SolidCompression=yes
OutputBaseFilename=proxlaunch-{#Version}-windows-x64-setup
; Sin firma (RF-E24): no hay SignTool aquí; la firma opcional la hace construir-windows.ps1.

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
spanish.PreguntaBorrarDatos=¿Desea borrar también sus datos de ProxLaunch (perfiles, huellas de certificados, preferencias, lotes y registro de este usuario)?%n%nLas contraseñas guardadas en el Administrador de credenciales de Windows NO se borran.%n%nSi no está seguro, elija «No»: sus datos se conservarán.

[Tasks]
; Acceso directo del escritorio: opcional y desmarcado (RF-E11, CA-E11.3).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Al actualizar encima se limpia el contenido anterior del programa (nunca los datos del usuario).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ProxLaunch"; Filename: "{app}\proxlaunch.exe"; AppUserModelID: "ProxLaunch.ProxLaunch"
Name: "{autodesktop}\ProxLaunch"; Filename: "{app}\proxlaunch.exe"; AppUserModelID: "ProxLaunch.ProxLaunch"; Tasks: desktopicon

[Run]
Filename: "{app}\proxlaunch.exe"; Description: "{cm:LaunchProgram,ProxLaunch}"; Flags: nowait postinstall skipifsilent

[Code]
var
  BorrarDatos: Boolean;

{ Parámetro del desinstalador para el modo silencioso: unins000.exe /VERYSILENT /BORRARDATOS=1 }
function ParametroBorrarDatos(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/BORRARDATOS=1') = 0 then
      Result := True;
end;

{ Casilla «Borrar también mis datos»: por defecto NO (la respuesta predeterminada es «No»).
  Si la instalación es «para todos los usuarios» (modo administrador), el desinstalador NO pregunta ni
  borra datos: las carpetas de datos son de cada usuario y quien desinstala como administrador no
  puede borrar con seguridad las de los demás. Un /BORRARDATOS=1 en ese modo se IGNORA y queda anotado
  en el registro de Inno Setup (opción /LOG). En la instalación por usuario todo sigue igual. }
function InitializeUninstall(): Boolean;
begin
  Result := True;
  BorrarDatos := False;
  if IsAdminInstallMode then
  begin
    if ParametroBorrarDatos() then
      Log('Se ignora /BORRARDATOS=1: la instalacion es para todos los usuarios y no se borran datos de ningun usuario.');
  end
  else
  begin
    BorrarDatos := ParametroBorrarDatos();
    if (not BorrarDatos) and (not UninstallSilent()) then
      BorrarDatos := MsgBox(CustomMessage('PreguntaBorrarDatos'), mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2) = IDYES;
  end;
end;

{ Borra SOLO las carpetas de datos de ProxLaunch del usuario que desinstala. Son las de platformdirs
  en Windows (sin appauthor y sin roaming): %LOCALAPPDATA%\ProxLaunch\ProxLaunch (configuración,
  datos, lotes y registro cuelgan de ahí). Nunca se toca el llavero ni nada ajeno. Con instalación
  para todos los usuarios BorrarDatos es siempre falso (ver InitializeUninstall). }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Autor, Carpeta: String;
begin
  if (CurUninstallStep = usPostUninstall) and BorrarDatos and (not IsAdminInstallMode) then
  begin
    Autor := ExpandConstant('{localappdata}\ProxLaunch');
    Carpeta := Autor + '\ProxLaunch';
    if DirExists(Carpeta) then
      DelTree(Carpeta, True, True, True);
    { RemoveDir solo borra carpetas vacías: si alguien guardó algo más, se respeta. }
    RemoveDir(Autor);
  end;
end;
