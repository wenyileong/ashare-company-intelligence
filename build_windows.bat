@echo off
REM ------------------------------------------------------------------
REM  Build the Windows application (AShareScraper.exe + ashare-cli.exe)
REM  Requirements: Python 3.10-3.13 (64-bit) from python.org, with
REM  "Add python.exe to PATH" or the "py" launcher installed.
REM  Output: dist\AShareScraper\, AShareScraper-<version>-setup.exe (if NSIS is
REM  installed) and AShareScraper-<version>-portable.zip
REM  Signing: set ASHARE_SIGN_CERT (see packaging\sign.bat); unsigned otherwise.
REM ------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/windows/
  echo and tick "Add python.exe to PATH", then run this script again.
  pause & exit /b 1
)

%PY% -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)"
if errorlevel 1 (
  echo Python 3.10 to 3.13 is required. Found:
  %PY% --version
  pause & exit /b 1
)

echo [1/5] Creating build environment...
%PY% -m venv .build-venv || (pause & exit /b 1)
call .build-venv\Scripts\activate.bat

echo [2/5] Installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-dev.txt || (pause & exit /b 1)

echo [3/5] Running tests...
python -m pytest -q || (echo Tests failed; not building. & pause & exit /b 1)

echo [4/5] Building executables...
pyinstaller --noconfirm --clean packaging\ashare.spec --distpath dist --workpath build || (pause & exit /b 1)

dist\AShareScraper\ashare-cli.exe version || (echo The built CLI did not start. & pause & exit /b 1)
for /f %%v in ('dist\AShareScraper\ashare-cli.exe version') do set "VER=%%v"
copy /y packaging\READ_ME_FIRST.txt dist\AShareScraper\ >nul
python packaging\build_docs.py dist\AShareScraper\docs || (pause & exit /b 1)
call packaging\sign.bat dist\AShareScraper\AShareScraper.exe || (pause & exit /b 1)
call packaging\sign.bat dist\AShareScraper\ashare-cli.exe || (pause & exit /b 1)

echo [5/5] Packaging...
set "NSIS="
where makensis >nul 2>nul && set "NSIS=makensis"
if not defined NSIS if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set "NSIS=%ProgramFiles(x86)%\NSIS\makensis.exe"
if defined NSIS (
  "%NSIS%" /V2 /DVERSION=%VER% packaging\installer.nsi || (pause & exit /b 1)
  call packaging\sign.bat AShareScraper-%VER%-setup.exe || (pause & exit /b 1)
) else (
  echo NSIS not found: skipping the installer ^(install it from https://nsis.sourceforge.io^).
)
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\AShareScraper' -DestinationPath 'AShareScraper-%VER%-portable.zip'"

echo.
echo Done.
echo   Desktop app : dist\AShareScraper\AShareScraper.exe
echo   Command line: dist\AShareScraper\ashare-cli.exe
echo   Installer   : AShareScraper-%VER%-setup.exe
echo   Portable zip: AShareScraper-%VER%-portable.zip
pause
