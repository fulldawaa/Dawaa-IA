; Installateur de Dawaa (Inno Setup 6). Construit par build.ps1.
#define NomApp "Dawaa"
#define VersionApp "0.1.0"

[Setup]
AppId={{7C1E8F5A-4B2D-4E8A-9D3F-2A6B1C0D9E47}
AppName={#NomApp}
AppVersion={#VersionApp}
AppVerName={#NomApp} {#VersionApp}
AppPublisher={#NomApp}
; Installation pour l'utilisateur courant : aucun mot de passe administrateur demandé
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#NomApp}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=..\dist
OutputBaseFilename=Dawaa-Setup
SetupIconFile=..\assets\dawaa.ico
UninstallDisplayIcon={app}\Dawaa.exe
UninstallDisplayName={#NomApp} - assistant vocal
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Demande de fermer Dawaa s'il est ouvert (même nom que dans dawaa/main.py)
AppMutex=Local\Dawaa_instance_unique

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
fr.WelcomeLabel2=Ce programme va installer [name] sur votre ordinateur.%n%nDawaa est un assistant que vous pouvez utiliser à la voix ou au clavier : écrire des lettres, faire des tableaux Excel, chercher sur internet…%n%nCliquez sur « Suivant » pour continuer.

[Tasks]
Name: "bureau"; Description: "Mettre un raccourci sur le bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\Dawaa\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#NomApp}"; Filename: "{app}\Dawaa.exe"
Name: "{autodesktop}\{#NomApp}"; Filename: "{app}\Dawaa.exe"; Tasks: bureau

[Run]
Filename: "{app}\Dawaa.exe"; Description: "Lancer Dawaa maintenant"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Donnees: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Donnees := ExpandConstant('{userappdata}\Dawaa');
    if DirExists(Donnees) then
      if SuppressibleMsgBox('Voulez-vous aussi supprimer les modèles téléchargés (environ 3 Go), les réglages et l''historique des conversations ?'
                + #13#10#13#10 + 'Vos documents (dossier Documents > Dawaa) seront conservés dans tous les cas.',
                mbConfirmation, MB_YESNO, IDNO) = IDYES then
        DelTree(Donnees, True, True, True);
  end;
end;
