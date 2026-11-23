@echo off
REM Lance le HUD sans fenetre de console (menu dans la barre des taches)
cd /d "%~dp0"
set PYW=pythonw
if exist ".venv\Scripts\pythonw.exe" set PYW=.venv\Scripts\pythonw.exe
start "" %PYW% -m fleur hud
