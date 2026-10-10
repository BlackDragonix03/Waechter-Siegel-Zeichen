@echo off
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"
title Waechter-Siegelwerkstatt - Android-APK bauen

echo.
echo ==============================================================
echo   Waechter-Siegelwerkstatt: Android-APK bauen
echo ==============================================================
echo.

rem --- Voraussetzungen pruefen ---------------------------------------------
where node >nul 2>nul
if errorlevel 1 goto :no_node
where npm >nul 2>nul
if errorlevel 1 goto :no_node
echo Node.js gefunden:
node --version

where java >nul 2>nul
if errorlevel 1 goto :no_java
set "JV="
for /f "tokens=3" %%v in ('java -version 2^>^&1 ^| findstr /i /c:" version "') do if not defined JV set "JV=%%~v"
for /f "delims=." %%a in ("!JV!") do set "JMAJ=%%a"
echo Java gefunden: !JV!
if not "!JMAJ!"=="17" goto :wrong_java

set "SDK=%ANDROID_HOME%"
if "!SDK!"=="" set "SDK=%ANDROID_SDK_ROOT%"
if "!SDK!"=="" goto :no_sdk
if not exist "!SDK!\platforms" goto :no_sdk
echo Android-SDK gefunden: !SDK!
echo.

rem --- Bauen ---------------------------------------------------------------
echo [1/4] Web-App sammeln.
call node scripts\build-web.js
if errorlevel 1 goto :failed_generic

echo.
echo [2/4] Android-Projekt vorbereiten. Das braucht Internet und dauert einige Minuten.
if exist android-app rmdir /s /q android-app
mkdir android-app
copy /y android\package.json android-app\ >nul
copy /y android\capacitor.config.json android-app\ >nul
pushd android-app
call npm install --no-audit --no-fund
if errorlevel 1 goto :npm_failed
call npx cap telemetry off >nul 2>nul
call npx cap add android
if errorlevel 1 goto :npm_failed
call npx cap sync android
if errorlevel 1 goto :npm_failed
popd

rem Pfad zum SDK fuer Gradle eintragen (Backslashes verdoppeln)
set "SDK_ESC=!SDK:\=\\!"
> "android-app\android\local.properties" echo sdk.dir=!SDK_ESC!

echo.
echo [3/4] APK bauen. Beim ersten Mal laedt Gradle viele Dateien, das kann 10 Minuten dauern.
pushd android-app\android
call gradlew.bat assembleDebug --no-daemon
if errorlevel 1 goto :gradle_failed
popd

echo.
echo [4/4] APK in den Ordner release kopieren.
if not exist release mkdir release
copy /y "android-app\android\app\build\outputs\apk\debug\app-debug.apk" "release\Waechter-Siegelwerkstatt-debug.apk" >nul
if errorlevel 1 goto :copy_failed

echo.
echo ==============================================================
echo   Fertig. Die APK liegt im Ordner:
echo   %~dp0release
echo ==============================================================
echo.
echo Installation auf dem Handy: Datei auf das Handy kopieren, antippen und
echo die Installation aus unbekannten Quellen erlauben. Die APK ist mit einem
echo Debug-Schluessel signiert. Fuer den Play Store braucht es einen eigenen.
echo.
explorer "%~dp0release"
pause
exit /b 0

:no_node
echo FEHLER: Node.js wurde nicht gefunden.
echo Bitte Node.js 20 oder neuer installieren: https://nodejs.org
goto :fail

:no_java
echo FEHLER: Java wurde nicht gefunden.
echo Bitte JDK 17 installieren, zum Beispiel Temurin 17: https://adoptium.net
echo Danach ein neues Fenster oeffnen und die Datei erneut starten.
goto :fail

:wrong_java
echo FEHLER: Es wird Java !JV! verwendet, benoetigt wird JDK 17.
echo Bitte JDK 17 installieren und JAVA_HOME darauf zeigen lassen.
goto :fail

:no_sdk
echo FEHLER: Das Android-SDK wurde nicht gefunden.
echo 1. Android Studio installieren: https://developer.android.com/studio
echo 2. Android Studio einmal starten und das SDK installieren lassen.
echo 3. Die Umgebungsvariable ANDROID_HOME auf den SDK-Ordner setzen, meist
echo    %%LOCALAPPDATA%%\Android\Sdk
echo 4. Ein neues Fenster oeffnen und diese Datei erneut starten.
goto :fail

:npm_failed
popd
echo.
echo FEHLER: Das Android-Projekt konnte nicht vorbereitet werden.
echo Bitte die Internetverbindung pruefen und erneut starten.
goto :fail

:gradle_failed
popd
echo.
echo FEHLER: Die APK konnte nicht gebaut werden. Meldungen siehe oben.
echo Haeufige Ursachen:
echo - Lizenzen nicht akzeptiert: im Android-SDK-Ordner unter
echo   cmdline-tools\latest\bin den Befehl  sdkmanager --licenses  ausfuehren
echo   und alles mit y bestaetigen. Die Command-line Tools gibt es in Android
echo   Studio unter SDK Manager, Reiter SDK Tools.
echo - Fehlende SDK-Teile: im SDK Manager die Plattform Android 14 ^(API 34^)
echo   und die Build-Tools installieren.
goto :fail

:copy_failed
echo FEHLER: Die fertige APK wurde nicht gefunden.
goto :fail

:failed_generic
echo FEHLER: Die Web-App konnte nicht gesammelt werden.
goto :fail

:fail
echo.
echo Der Vorgang wurde abgebrochen.
pause
exit /b 1
