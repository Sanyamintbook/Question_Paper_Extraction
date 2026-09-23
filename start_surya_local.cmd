@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -u "%~dp0code\surya_lan_server.py" --host 127.0.0.1 --port 8502 --no-token
pause
