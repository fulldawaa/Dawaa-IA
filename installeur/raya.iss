; Installateur de Raya (Inno Setup 6). Construit par build.ps1.
#define NomApp "Raya Assistant"
#define VersionApp "0.4.0"

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
OutputBaseFilename=Raya-Setup
SetupIconFile=..\assets\raya.ico
UninstallDisplayIcon={app}\Raya.exe
UninstallDisplayName={#NomApp} - assistante vocale
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Demande de fermer Raya si elle est ouverte (même nom que dans raya/main.py), ou l'ancienne version Dawaa
AppMutex=Local\Raya_instance_unique,Local\Dawaa_instance_unique

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
fr.WelcomeLabel2=Ce programme va installer [name] sur votre ordinateur.%n%nRaya est une assistante que vous pouvez utiliser à la voix ou au clavier : écrire des lettres, faire des tableaux Excel, chercher sur internet…%n%nCliquez sur « Suivant » pour continuer.

[Tasks]
Name: "bureau"; Description: "Mettre un raccourci sur le bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\Raya\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Mise à jour d'une installation de Dawaa (nom avant la version 0.4.0) : on retire l'ancien programme et ses raccourcis
Type: files; Name: "{app}\Dawaa.exe"
Type: filesandordirs; Name: "{app}\_internal\dawaa"
Type: files; Name: "{app}\_internal\assets\dawaa.png"
Type: files; Name: "{autoprograms}\Dawaa.lnk"
Type: files; Name: "{autodesktop}\Dawaa.lnk"

[Icons]
Name: "{autoprograms}\{#NomApp}"; Filename: "{app}\Raya.exe"
Name: "{autodesktop}\{#NomApp}"; Filename: "{app}\Raya.exe"; Tasks: bureau

[Registry]
; Raya s'inscrit elle-même au démarrage de Windows (réglage) ; on retire l'inscription à la désinstallation
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Raya"; ValueType: none; Flags: uninsdeletevalue dontcreatekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Dawaa"; ValueType: none; Flags: deletevalue dontcreatekey

[Run]
Filename: "{app}\Raya.exe"; Description: "Lancer Raya maintenant"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Donnees: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Donnees := ExpandConstant('{userappdata}\Raya');
    if DirExists(Donnees) then
      if SuppressibleMsgBox('Voulez-vous aussi supprimer les modèles téléchargés (environ 3 Go), les réglages et l''historique des conversations ?'
                + #13#10#13#10 + 'Vos documents (dossier Documents > Raya) seront conservés dans tous les cas.',
                mbConfirmation, MB_YESNO, IDNO) = IDYES then
        DelTree(Donnees, True, True, True);
  end;
end;
