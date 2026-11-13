; Установщик необязателен. build_win.ps1 запускает ISCC, только если он есть в PATH.
; Ярлык попадает в меню «Пуск», удаление снимает каталог программы и ярлыки.

#ifndef Version
  #define Version "0.0.0"
#endif

#define MyAppName "Окно капремонта мельницы"
#define MyAppExe "millrepair.exe"

[Setup]
AppId={{A7B1C2E4-5F60-4D11-9A2B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#Version}
AppPublisher=Mill Repair Window
DefaultDirName={autopf}\MillRepair
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\output
OutputBaseFilename=MillRepair-{#Version}-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}
WizardStyle=modern

[Files]
Source: "..\..\dist\millrepair\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Запустить программу"; Flags: nowait postinstall skipifsilent
