@echo off
cd /d C:\Repositories\umamusume-sweepy
set UAT_AUTORESTART=1
call conda activate umamusume

rem Kill anything already holding port 8071 before starting
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8071 " ^| findstr LISTENING') do (
    echo Killing stale process %%p on port 8071
    taskkill /F /PID %%p >nul 2>&1
)

python main.py
