@echo off
REM Clic derecho > "Ejecutar como administrador", en CADA equipo. Abre los puertos solo en redes privadas.
netsh advfirewall firewall delete rule name="XARA panel y tareas" >nul 2>nul
netsh advfirewall firewall delete rule name="XARA descubrimiento" >nul 2>nul
netsh advfirewall firewall delete rule name="XARA llama.cpp RPC" >nul 2>nul
netsh advfirewall firewall add rule name="XARA panel y tareas" dir=in action=allow protocol=TCP localport=8765 profile=private
netsh advfirewall firewall add rule name="XARA descubrimiento" dir=in action=allow protocol=UDP localport=8766 profile=private
netsh advfirewall firewall add rule name="XARA llama.cpp RPC" dir=in action=allow protocol=TCP localport=50052 profile=private
echo.
echo Listo. Comprueba en Configuracion ^> Red e Internet que tu red figura como "Privada".
pause
