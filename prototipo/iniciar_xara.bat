@echo off
chcp 65001 >nul
title XARA
cd /d "%~dp0"
rem py es el lanzador de python.org; se prefiere porque "python" puede ser el atajo de la Microsoft Store.
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo.
  echo  No se encontro Python en este equipo.
  echo  Instalalo desde https://www.python.org/downloads/ y marca la casilla
  echo  "Add python.exe to PATH" durante la instalacion. Luego vuelve a abrir este archivo.
  echo.
  pause
  exit /b
)
echo Preparando XARA (solo tarda la primera vez)...
%PY% -m pip install --user --quiet --disable-pip-version-check psutil
echo.
echo  XARA esta funcionando. NO cierres esta ventana mientras uses XARA.
echo  Si este equipo es el coordinador, abre en el navegador: http://localhost:8765
echo.
:inicio
%PY% xara.py
if %errorlevel%==3 goto inicio
pause
