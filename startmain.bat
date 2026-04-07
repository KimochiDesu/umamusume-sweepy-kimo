@echo off
cd /d C:\Repositories\umamusume-sweepy
set UAT_AUTORESTART=1
call conda activate umamusume
python main.py
pause
