; SPDX-License-Identifier: AGPL-3.0-or-later
; Copyright (C) 2026 OpenFollow Project
; AutoFollow Windows installer. Built by makensis from the PyInstaller output in
; dist\AutoFollow; VERSION and SRC are passed on the command line.

Unicode true
!include "MUI2.nsh"

Name "AutoFollow"
OutFile "AutoFollow-${VERSION}-Setup.exe"
InstallDir "$PROGRAMFILES64\AutoFollow"
InstallDirRegKey HKLM "Software\AutoFollow" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoFollow"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LICENSE}"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\AutoFollow.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "AutoFollow"
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\AutoFollow.lnk" "$INSTDIR\AutoFollow.exe"
  CreateShortcut "$DESKTOP\AutoFollow.lnk" "$INSTDIR\AutoFollow.exe"
  WriteRegStr HKLM "Software\AutoFollow" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "AutoFollow"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "AutoFollow"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\AutoFollow.exe"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
SectionEnd

; Settings in %APPDATA%\AutoFollow are kept, so a reinstall keeps the show setup.
Section "Uninstall"
  Delete "$SMPROGRAMS\AutoFollow.lnk"
  Delete "$DESKTOP\AutoFollow.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "Software\AutoFollow"
SectionEnd
