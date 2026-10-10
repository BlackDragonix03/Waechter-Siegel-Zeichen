@echo off
setlocal enableextensions
cd /d "%~dp0"
title Waechter-Siegelwerkstatt - Windows-Exe bauen

echo.
echo ==============================================================
echo   Waechter-Siegelwerkstatt: Windows-Exe bauen
echo ==============================================================
echo.

where node >nul 2>nul
if errorlevel 1 goto :no_node
where npm >nul 2>nul
if errorlevel 1 goto :no_node

echo Node.js gefunden:
node --version
echo.

echo [1/3] Programme laden. Das braucht Internet und dauert beim ersten Mal einige Minuten.
pushd desktop
call npm install --no-audit --no-fund
if errorlevel 1 goto :npm_failed

echo.
echo [2/3] Exe bauen.
rem Ohne Code-Signatur bauen. Ein Signaturzertifikat wird nicht gesucht.
set CSC_IDENTITY_AUTO_DISCOVERY=false
call npm run pack:win
if errorlevel 1 goto :build_failed
popd

echo.
echo [3/3] Exe in den Ordner release kopieren.
if not exist release mkdir release
copy /y "desktop\dist\Waechter-Siegelwerkstatt-*.exe" "release\" >nul
if errorlevel 1 goto :copy_failed

echo.
echo ==============================================================
echo   Fertig. Die Exe liegt im Ordner:
echo   %~dp0release
echo ==============================================================
echo.
echo Hinweis: Die Exe ist nicht signiert. Beim ersten Start zeigt Windows
echo eventuell eine Warnung. Dann auf "Weitere Informationen" und danach
echo auf "Trotzdem ausfuehren" klicken.
echo.
explorer "%~dp0release"
pause
exit /b 0

:no_node
echo FEHLER: Node.js wurde nicht gefunden.
echo Bitte Node.js 20 oder neuer installieren: https://nodejs.org
echo Danach dieses Fenster schliessen und die Datei erneut starten.
goto :fail

:npm_failed
popd
echo.
echo FEHLER: Die Programme konnten nicht geladen werden.
echo Bitte die Internetverbindung pruefen und erneut starten.
goto :fail

:build_failed
popd
echo.
echo FEHLER: Die Exe konnte nicht gebaut werden.
echo Wenn oben "Cannot create symbolic link" steht: Diese Datei per Rechtsklick
echo "Als Administrator ausfuehren" starten, oder in den Windows-Einstellungen
echo den Entwicklermodus einschalten.
goto :fail

:copy_failed
echo FEHLER: Die fertige Exe wurde nicht gefunden. Siehe Ordner desktop\dist.
goto :fail

:fail
echo.
echo Der Vorgang wurde abgebrochen.
pause
exit /b 1
