@echo off
setlocal enableextensions
cd /d "%~dp0netguard"
title NetGuard - Windows-Exe bauen

echo.
echo ==============================================================
echo   NetGuard: Windows-Exe bauen
echo ==============================================================
echo.

set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (where python >nul 2>nul && set PY=python)
if "%PY%"=="" goto :no_python

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python
echo Python gefunden:
%PY% --version
echo.

echo [1/4] Virtuelle Umgebung anlegen (Ordner netguard\.venv).
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 goto :venv_failed
)
set VPY=.venv\Scripts\python.exe

echo.
echo [2/4] Programme laden (PySide6, PyInstaller). Braucht Internet, beim ersten Mal einige Minuten.
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :pip_failed

echo.
echo [3/4] Tests und Symbol.
"%VPY%" -m unittest discover -s tests
if errorlevel 1 goto :tests_failed
"%VPY%" scripts\make_icon.py build\netguard.ico
set ICON=
if exist "build\netguard.ico" set ICON=--icon build\netguard.ico

echo.
set EXCL=--exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts --exclude-module PySide6.QtPdf
echo [4/4] Exe bauen (eine Datei, ohne Konsolenfenster) und NetGuard-MCP.exe (Konsole, fuer KI per Stdio).
"%VPY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name NetGuard %ICON% %EXCL% netguard.py
if errorlevel 1 goto :build_failed
"%VPY%" -m PyInstaller --noconfirm --onefile --console --name NetGuard-MCP %ICON% %EXCL% netguard.py
if errorlevel 1 goto :build_failed

if not exist "..\release" mkdir "..\release"
copy /y "dist\NetGuard.exe" "..\release\NetGuard.exe" >nul
if errorlevel 1 goto :copy_failed
copy /y "dist\NetGuard-MCP.exe" "..\release\NetGuard-MCP.exe" >nul

echo.
echo ==============================================================
echo   Fertig. Die Exe liegt hier:
echo   %~dp0release\NetGuard.exe
echo ==============================================================
echo.
echo Hinweise:
echo  - Die Exe ist nicht signiert. Windows SmartScreen zeigt beim ersten Start
echo    eventuell eine Warnung: "Weitere Informationen", dann "Trotzdem ausfuehren".
echo  - Beim ersten Start fragt die Windows-Firewall eventuell nach Netzwerkzugriff:
echo    fuer private Netzwerke zulassen, sonst fehlen UPnP- und Namensantworten.
echo  - Scans und Einstellungen landen im Ordner "NetGuard-Daten" neben der Exe.
echo  - NetGuard-MCP.exe --mcp ist der MCP-Server fuer Claude Desktop (beide Exe im selben Ordner lassen).
echo.
explorer "%~dp0release"
pause
exit /b 0

:no_python
echo FEHLER: Python wurde nicht gefunden.
echo Bitte Python 3.10 oder neuer installieren: https://www.python.org/downloads/windows/
echo Beim Installieren "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
goto :fail

:old_python
echo FEHLER: Python ist zu alt. Es wird Python 3.10 oder neuer gebraucht.
goto :fail

:venv_failed
echo FEHLER: Die virtuelle Umgebung konnte nicht angelegt werden.
goto :fail

:pip_failed
echo.
echo FEHLER: Die Programme konnten nicht geladen werden.
echo Bitte die Internetverbindung pruefen und erneut starten.
goto :fail

:tests_failed
echo.
echo FEHLER: Die Tests sind fehlgeschlagen. Siehe Ausgabe oben.
goto :fail

:build_failed
echo.
echo FEHLER: Die Exe konnte nicht gebaut werden. Siehe Ausgabe oben.
echo Wenn ein Virenscanner meckert: Ordner netguard\build und netguard\dist freigeben.
goto :fail

:copy_failed
echo FEHLER: Die fertige Exe wurde nicht gefunden. Siehe Ordner netguard\dist.
goto :fail

:fail
echo.
echo Der Vorgang wurde abgebrochen.
pause
exit /b 1
