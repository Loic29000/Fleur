@echo off
REM Construit dist\Fleur.exe (necessite : pip install -r requirements-dev.txt)
cd /d "%~dp0"
set PYI=pyinstaller
if exist ".venv\Scripts\pyinstaller.exe" set PYI=.venv\Scripts\pyinstaller.exe
%PYI% --noconfirm --onefile --console --name Fleur fleur\__main__.py
echo.
echo Executable : dist\Fleur.exe
