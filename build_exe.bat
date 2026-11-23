@echo off
REM Construit dist\Fleur.exe (nécessite : pip install -r requirements-dev.txt)
pyinstaller --noconfirm --onefile --console --name Fleur fleur\__main__.py
echo.
echo Executable : dist\Fleur.exe
