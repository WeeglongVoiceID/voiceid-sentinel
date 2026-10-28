@echo off
setlocal
cd /d "%~dp0"
echo ==================================================
echo WEEGLONG AI - VOICEID SENTINEL v1.6
 echo Local synthetic investigation ^& assurance showcase
 echo No Meta API call unless you explicitly enable it.
echo ==================================================
echo.
py workbench_v1_6.py
if errorlevel 1 (
 echo.
 echo Could not start. Check Python installation and stop any previous VoiceID Sentinel localhost server using Ctrl+C.
 pause
)
endlocal
