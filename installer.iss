; Installer di ScreenAgent (Inno Setup 6).
; Lo compila build.bat se Inno Setup e' presente, oppure a mano:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; Produce Output\ScreenAgent-Setup.exe

; (per una build di prova isolata: ISCC /DNome=ScreenAgentProva installer.iss
;  -> altro nome, altra voce di disinstallazione, altri collegamenti)
#ifndef Nome
  #define Nome "ScreenAgent"
#endif
#define Versione "1.2"

[Setup]
AppName={#Nome}
AppVersion={#Versione}
AppPublisher=ScreenAgent
; icona dell'installer e voce in "App installate" di Windows
SetupIconFile=icona.ico
UninstallDisplayIcon={app}\ScreenAgent.exe
UninstallDisplayName={#Nome}
VersionInfoVersion={#Versione}.0.0
VersionInfoDescription=Installazione di {#Nome}
; installazione PER UTENTE: niente richiesta di amministratore, cartella
; scrivibile (l'app salva li' sequenze, macro e immagini)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#Nome}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename={#Nome}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti:"

[Files]
; tutta la cartella prodotta da PyInstaller
Source: "dist\ScreenAgent\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; il README accanto all'app
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; cartelle dati, create vuote e scrivibili dall'utente (l'app le ricrea
; comunque da sola se mancano): immagini, sequenze, macro
Name: "{app}\templates"
Name: "{app}\sequenze"
Name: "{app}\macro"

[Icons]
Name: "{group}\{#Nome}"; Filename: "{app}\ScreenAgent.exe"
Name: "{group}\Disinstalla {#Nome}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\ScreenAgent.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ScreenAgent.exe"; Description: "Avvia {#Nome} adesso"; Flags: nowait postinstall skipifsilent
