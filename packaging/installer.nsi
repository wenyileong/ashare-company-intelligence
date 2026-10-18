; NSIS installer for A-share Company Intelligence (v2.0)
;
; Build after PyInstaller has produced dist\AShareScraper\ :
;   makensis /DVERSION=2.0.4 packaging\installer.nsi
; (build_windows.bat does this when NSIS is installed; on Linux, apt install nsis.)
;
; The installer is per-user (no administrator rights are needed). It installs
; both programs, the desktop interface and the command line, with the
; documentation, adds Start-menu shortcuts and an uninstaller, and can add the
; program folder to the user's PATH so that ashare-cli runs from any prompt.
; The data folder (Documents\AShareScraper) is never touched by installing,
; upgrading or uninstalling.

; 64-bit installer: the programs are 64-bit, so 32-bit Windows is not supported anyway
Target amd64-unicode
SetCompressor /SOLID lzma
SetCompressorDictSize 64
RequestExecutionLevel user

!ifndef VERSION
  !define VERSION "2.0.4"
!endif
!ifndef DIST
  !define DIST "..\dist\AShareScraper"
!endif
!ifndef OUTFILE
  !define OUTFILE "..\AShareScraper-${VERSION}-setup.exe"
!endif
!define APP "A-share Company Intelligence"
!define KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AShareScraper"

Name "${APP} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\AShareScraper"
InstallDirRegKey HKCU "Software\AShareScraper" "InstallDir"
Icon "ashare.ico"
UninstallIcon "ashare.ico"
BrandingText "${APP} ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${APP} installer"
VIAddVersionKey "LegalCopyright" "Research software; see docs\compliance.md"

!include "MUI2.nsh"
!include "WinMessages.nsh"
!define MUI_ICON "ashare.ico"
!define MUI_UNICON "ashare.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\AShareScraper.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Start ${APP}"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\docs\user_guide.html"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Open the user guide"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Program (desktop and command line)" SecMain
  SectionIn RO
  ; an upgrade replaces the program files; the data folder is elsewhere
  RMDir /r "$INSTDIR\_internal"
  SetOutPath "$INSTDIR"
  File /r "${DIST}\*.*"
  WriteRegStr HKCU "Software\AShareScraper" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\AShareScraper" "Version" "${VERSION}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${KEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${KEY}" "Publisher" "${APP}"
  WriteRegStr HKCU "${KEY}" "DisplayIcon" "$INSTDIR\AShareScraper.exe"
  WriteRegStr HKCU "${KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${KEY}" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortcut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\AShareScraper.exe"
  CreateShortcut "$SMPROGRAMS\${APP}\Command line.lnk" "$SYSDIR\cmd.exe" \
    '/k "cd /d "$INSTDIR" && ashare-cli --help"' "$INSTDIR\ashare-cli.exe"
  CreateShortcut "$SMPROGRAMS\${APP}\User guide.lnk" "$INSTDIR\docs\user_guide.html"
  CreateShortcut "$SMPROGRAMS\${APP}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section /o "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\AShareScraper.exe"
SectionEnd

Section /o "Add ashare-cli to PATH (this user)" SecPath
  ReadRegDWORD $1 HKCU "Software\AShareScraper" "AddedToPath"
  StrCmp $1 "1" path_done
  ReadRegStr $0 HKCU "Environment" "Path"
  ; NSIS strings hold 1,024 characters: never rewrite a longer PATH (it would be cut short)
  StrLen $2 $0
  IntCmp $2 900 0 0 path_too_long
  StrCmp $0 "" 0 path_append
    WriteRegExpandStr HKCU "Environment" "Path" "$INSTDIR"
    Goto path_written
  path_append:
    WriteRegExpandStr HKCU "Environment" "Path" "$0;$INSTDIR"
  path_written:
    WriteRegDWORD HKCU "Software\AShareScraper" "AddedToPath" 1
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
    Goto path_done
  path_too_long:
    MessageBox MB_OK|MB_ICONINFORMATION "Your PATH is long, so it was left unchanged. Add $INSTDIR to it under \
      Environment Variables to run ashare-cli from any prompt."
  path_done:
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "AShareScraper.exe, ashare-cli.exe and the documentation."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "A shortcut on the desktop."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPath} "Lets you type ashare-cli in any command prompt. \
    The uninstaller does not edit PATH; remove the entry under Environment Variables if you wish."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  Delete "$DESKTOP\${APP}.lnk"
  RMDir /r "$SMPROGRAMS\${APP}"
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\docs"
  Delete "$INSTDIR\AShareScraper.exe"
  Delete "$INSTDIR\ashare-cli.exe"
  Delete "$INSTDIR\READ_ME_FIRST.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${KEY}"
  DeleteRegKey HKCU "Software\AShareScraper"
  ; Your data folder (Documents\AShareScraper by default) is kept.
SectionEnd
