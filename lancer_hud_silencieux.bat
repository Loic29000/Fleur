@echo off
REM Lance le HUD sans fenêtre de console (menu dans la barre des tâches)
cd /d "%~dp0"
start "" pythonw -m fleur hud
