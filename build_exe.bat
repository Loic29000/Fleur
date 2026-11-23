@echo off
REM Construit Fleur (necessite : pip install -r requirements-dev.txt)
REM   dist\Fleur\Fleur.exe : HUD + tableau de bord + analyse, sans console, avec icone
cd /d "%~dp0"
set PYI=pyinstaller
if exist ".venv\Scripts\pyinstaller.exe" set PYI=.venv\Scripts\pyinstaller.exe
REM Qt WebEngine est volumineux : un dossier demarre bien plus vite qu'un exe unique
%PYI% --noconfirm --onedir --windowed --name Fleur --icon fleur\assets\fleur.ico ^
  --add-data "fleur\web\static;fleur\web\static" --add-data "fleur\assets;fleur\assets" ^
  fleur\__main__.py || exit /b 1
REM Anciennes versions (deux programmes separes) : on les retire pour eviter la confusion
if exist "dist\Fleur.exe" del /q "dist\Fleur.exe"
if exist "dist\FleurAnalyse" rmdir /s /q "dist\FleurAnalyse"
echo.
echo Programme : dist\Fleur\Fleur.exe
