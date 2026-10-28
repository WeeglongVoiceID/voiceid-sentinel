@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
echo ===== VoiceID Sentinel v1.6 LOCAL OFFLINE REGRESSION =====
echo No API key, live Meta credit, or production connectivity is needed.
for %%F in (test_v1_6.py test_v1_5.py test_workbench_v1_4.py test_navigation_v1_4_1.py test_typography_v1_4_2.py engine_v1_2\test_v1_2.py legacy_v1_3\test_dashboard_v1_3.py) do (
 echo.
 echo ===== Running %%F =====
 py "%%F"
 if errorlevel 1 goto failed
)
echo.
echo PASS: 270 fixed offline tests across seven regression suites.
pause
exit /b 0
:failed
echo.
echo FAILURE: Stop and inspect the output above.
pause
exit /b 1
