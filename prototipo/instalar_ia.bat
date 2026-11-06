@echo off
chcp 65001 >nul
title XARA - instalar IA
cd /d "%~dp0"
rem py es el lanzador de python.org; se prefiere porque "python" puede ser el atajo de la Microsoft Store.
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo.
  echo  No se encontro Python en este equipo. Sigue el paso 1 de la guia.
  echo.
  pause
  exit /b
)
%PY% xara.py instalar
pause
