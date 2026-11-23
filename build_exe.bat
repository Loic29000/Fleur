@echo off
REM Construit les executables (necessite : pip install -r requirements-dev.txt)
REM   dist\Fleur.exe                       : HUD (icone dans la barre des taches)
REM   dist\FleurAnalyse\FleurAnalyse.exe   : application d'analyse (fenetre Windows)
cd /d "%~dp0"
set PYI=pyinstaller
if exist ".venv\Scripts\pyinstaller.exe" set PYI=.venv\Scripts\pyinstaller.exe
%PYI% --noconfirm --onefile --console --name Fleur --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineCore --add-data "fleur\web\static;fleur\web\static" fleur\__main__.py || exit /b 1
REM Qt WebEngine est volumineux : un dossier demarre bien plus vite qu'un exe unique
%PYI% --noconfirm --onedir --windowed --name FleurAnalyse --add-data "fleur\web\static;fleur\web\static" fleur\analyse_main.py || exit /b 1
echo.
echo Executables : dist\Fleur.exe et dist\FleurAnalyse\FleurAnalyse.exe
