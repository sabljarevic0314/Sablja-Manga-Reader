; Sablja Manga Reader App - per-user installer (NSIS).
; (Install folder and registry keys keep the old "SabljaReader" id on purpose: existing installs and their
; data\ folder upgrade in place.)
; Build with:  installer\make_setup.ps1     (or: makensis installer\SabljaMangaReaderApp.nsi)
;
; Layout the app expects: exe + sources.json in the install folder, data\ created next to them.
; Installing under %LOCALAPPDATA%\Programs means no admin rights and a writable data folder.

Unicode true
!include "MUI2.nsh"

Name "Sablja Manga Reader App"
; make_setup.ps1 passes the version from config.py's APP_VERSION; this fallback is only
; for running makensis directly.
!ifndef APP_VERSION
  !define APP_VERSION "2.0.0"
!endif
VIProductVersion "${APP_VERSION}.0"
VIFileVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "Sablja Manga Reader App"
VIAddVersionKey "CompanyName" "Sablja Manga Reader App"
VIAddVersionKey "FileDescription" "Sablja Manga Reader App Installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}.0"
VIAddVersionKey "ProductVersion" "${APP_VERSION}.0"
VIAddVersionKey "LegalCopyright" "Sablja Manga Reader App"
OutFile "..\dist\SabljaMangaReaderApp-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\SabljaReader"
InstallDirRegKey HKCU "Software\SabljaReader" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\SabljaMangaReaderApp.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Start Sablja Manga Reader App"
!define MUI_FINISHPAGE_TEXT "Sablja Manga Reader App is installed.$\r$\n$\r$\nYour library, progress and downloaded chapters are kept in:$\r$\n$INSTDIR\data"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!define MUI_UNCONFIRMPAGE_TEXT_TOP "Sablja Manga Reader App will be removed. Your library, progress and downloaded chapters in $INSTDIR\data are kept."
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Sablja Manga Reader App" SecMain
  SetShellVarContext current
  ; A running copy would lock the exe. Ask it to close first (it saves db.json on the way out), then
  ; force what's left. /T takes the Flutter window (flet.exe, a child process) down with it.
  nsExec::Exec 'taskkill /IM SabljaMangaReaderApp.exe /T'
  Sleep 2000
  nsExec::Exec 'taskkill /IM SabljaMangaReaderApp.exe /T /F'
  ; pre-rename installs ran as SabljaReader.exe
  nsExec::Exec 'taskkill /IM SabljaReader.exe /T'
  nsExec::Exec 'taskkill /IM SabljaReader.exe /T /F'
  Sleep 500
  Delete "$INSTDIR\SabljaReader.exe"

  SetOutPath "$INSTDIR"
  ; Keep a copy of the library before any app files are replaced. The data folder itself is
  ; never deleted by the installer or the uninstaller - this is an extra safety net.
  IfFileExists "$INSTDIR\data\db.json" 0 no_db_backup
    CreateDirectory "$INSTDIR\data\backups"
    CopyFiles /SILENT "$INSTDIR\data\db.json" "$INSTDIR\data\backups\db-before-${APP_VERSION}.json"
  no_db_backup:
  File "..\dist\SabljaMangaReaderApp.exe"
  File "..\dist\sources.json"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\SabljaReader" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "DisplayName" "Sablja Manga Reader App"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "Publisher" "Sablja Manga Reader App"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "DisplayIcon" "$INSTDIR\SabljaMangaReaderApp.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "NoRepair" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "EstimatedSize" 92000

  ; the app used to be called "Sablja Reader": drop its old shortcuts on upgrade
  Delete "$DESKTOP\Sablja Reader.lnk"
  Delete "$SMPROGRAMS\Sablja Reader\Sablja Reader.lnk"
  Delete "$SMPROGRAMS\Sablja Reader\Uninstall Sablja Reader.lnk"
  RMDir "$SMPROGRAMS\Sablja Reader"

  CreateDirectory "$SMPROGRAMS\Sablja Manga Reader App"
  CreateShortCut "$SMPROGRAMS\Sablja Manga Reader App\Sablja Manga Reader App.lnk" "$INSTDIR\SabljaMangaReaderApp.exe"
  CreateShortCut "$SMPROGRAMS\Sablja Manga Reader App\Uninstall Sablja Manga Reader App.lnk" "$INSTDIR\uninstall.exe"
  CreateShortCut "$DESKTOP\Sablja Manga Reader App.lnk" "$INSTDIR\SabljaMangaReaderApp.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  nsExec::Exec 'taskkill /IM SabljaMangaReaderApp.exe /T'
  Sleep 2000
  nsExec::Exec 'taskkill /IM SabljaMangaReaderApp.exe /T /F'
  Sleep 500

  Delete "$INSTDIR\SabljaMangaReaderApp.exe"
  Delete "$INSTDIR\sources.json"
  Delete "$INSTDIR\uninstall.exe"
  Delete "$DESKTOP\Sablja Manga Reader App.lnk"
  Delete "$SMPROGRAMS\Sablja Manga Reader App\Sablja Manga Reader App.lnk"
  Delete "$SMPROGRAMS\Sablja Manga Reader App\Uninstall Sablja Manga Reader App.lnk"
  RMDir "$SMPROGRAMS\Sablja Manga Reader App"
  DeleteRegKey HKCU "Software\SabljaReader"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader"
  ; data\ (library, progress, cache, downloads) is deliberately left in place
  RMDir "$INSTDIR"
SectionEnd
