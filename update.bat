@echo off
setlocal
cd /d "%~dp0"
git pull --autostash -X ours --no-edit

winget install -e --id Google.PlatformTools --accept-package-agreements --accept-source-agreements


adb kill-server
adb start-server

pip install -r requirements.txt

set UAT_AUTORESTART=1

where python3 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python3 bake_templates.py
    python3 main.py
    if %ERRORLEVEL% EQU 0 goto :end
)

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    python bake_templates.py
    python main.py
) else (
    python bake_templates.py
    python main.py
)

:end
