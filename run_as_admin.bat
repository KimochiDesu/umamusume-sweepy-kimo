@echo off
cd /d "%~dp0"
powershell -Command "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'Set-Location ''%~dp0''; python main.py' -Verb RunAs"
