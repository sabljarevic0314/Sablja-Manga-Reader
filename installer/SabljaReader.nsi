; Sablja Reader - per-user installer (NSIS).
; Build with:  installer\make_setup.ps1     (or: makensis installer\SabljaReader.nsi)
;
; Layout the app expects: exe + sources.json in the install folder, data\ created next to them.
; Installing under %LOCALAPPDATA%\Programs means no admin rights and a writable data folder.

Unicode true
!include "MUI2.nsh"

Name "Sablja Reader"
OutFile "..\dist\SabljaReader-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\SabljaReader"
InstallDirRegKey HKCU "Software\SabljaReader" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\SabljaReader.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Start Sablja Reader"
!define MUI_FINISHPAGE_TEXT "Sablja Reader is installed.$\r$\n$\r$\nYour library, progress and downloaded chapters are kept in:$\r$\n$INSTDIR\data"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!define MUI_UNCONFIRMPAGE_TEXT_TOP "Sablja Reader will be removed. Your library, progress and downloaded chapters in $INSTDIR\data are kept."
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Sablja Reader" SecMain
  SetShellVarContext current
  ; a running copy would lock the exe
  nsExec::Exec 'taskkill /IM SabljaReader.exe /F'
  Sleep 500

  SetOutPath "$INSTDIR"
  File "..\dist\SabljaReader.exe"
  File "..\dist\sources.json"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\SabljaReader" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "DisplayName" "Sablja Reader"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "DisplayVersion" "1.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "Publisher" "Sablja Reader"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "DisplayIcon" "$INSTDIR\SabljaReader.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "NoRepair" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader" "EstimatedSize" 24000

  CreateDirectory "$SMPROGRAMS\Sablja Reader"
  CreateShortCut "$SMPROGRAMS\Sablja Reader\Sablja Reader.lnk" "$INSTDIR\SabljaReader.exe"
  CreateShortCut "$SMPROGRAMS\Sablja Reader\Uninstall Sablja Reader.lnk" "$INSTDIR\uninstall.exe"
  CreateShortCut "$DESKTOP\Sablja Reader.lnk" "$INSTDIR\SabljaReader.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  nsExec::Exec 'taskkill /IM SabljaReader.exe /F'
  Sleep 500

  Delete "$INSTDIR\SabljaReader.exe"
  Delete "$INSTDIR\sources.json"
  Delete "$INSTDIR\uninstall.exe"
  Delete "$DESKTOP\Sablja Reader.lnk"
  Delete "$SMPROGRAMS\Sablja Reader\Sablja Reader.lnk"
  Delete "$SMPROGRAMS\Sablja Reader\Uninstall Sablja Reader.lnk"
  RMDir "$SMPROGRAMS\Sablja Reader"
  DeleteRegKey HKCU "Software\SabljaReader"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SabljaReader"
  ; data\ (library, progress, cache, downloads) is deliberately left in place
  RMDir "$INSTDIR"
SectionEnd
