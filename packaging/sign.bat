@echo off
REM ------------------------------------------------------------------
REM  Code-signing hook (v2.0). Called by build_windows.bat for each
REM  executable and for the installer. Signs only when a certificate is
REM  configured; otherwise it does nothing and the build continues unsigned.
REM
REM    set ASHARE_SIGN_CERT=C:\path\to\certificate.pfx
REM    set ASHARE_SIGN_PASSWORD=...            (if the .pfx has a password)
REM    set ASHARE_SIGN_TIMESTAMP=http://timestamp.digicert.com   (optional)
REM
REM  For a certificate held in a hardware token or a cloud signing service,
REM  set ASHARE_SIGN_COMMAND instead; %%1 is replaced by the file to sign, e.g.
REM    set ASHARE_SIGN_COMMAND=signtool sign /n "My Org" /fd sha256 /tr http://timestamp.digicert.com /td sha256
REM  Requires signtool.exe (Windows SDK) on PATH.
REM ------------------------------------------------------------------
setlocal
if "%~1"=="" (echo usage: sign.bat FILE & exit /b 2)
if defined ASHARE_SIGN_COMMAND (
  %ASHARE_SIGN_COMMAND% "%~1" || exit /b 1
  echo Signed %~nx1
  exit /b 0
)
if not defined ASHARE_SIGN_CERT (
  echo Not signed: %~nx1 ^(set ASHARE_SIGN_CERT to sign^)
  exit /b 0
)
if not defined ASHARE_SIGN_TIMESTAMP set "ASHARE_SIGN_TIMESTAMP=http://timestamp.digicert.com"
set "PW="
if defined ASHARE_SIGN_PASSWORD set "PW=/p %ASHARE_SIGN_PASSWORD%"
signtool sign /f "%ASHARE_SIGN_CERT%" %PW% /fd sha256 /tr %ASHARE_SIGN_TIMESTAMP% /td sha256 /d "A-share Company Intelligence" "%~1" || exit /b 1
signtool verify /pa "%~1" >nul || (echo Signature check failed for %~nx1 & exit /b 1)
echo Signed %~nx1
