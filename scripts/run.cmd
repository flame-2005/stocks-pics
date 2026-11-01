@echo off
rem Runs one pipeline mode inside the project venv and appends everything to a log.
rem Usage: scripts\run.cmd prep | morning | confirm | scorecard
setlocal
set "ROOT=%~dp0.."
set "LOGDIR=%LOCALAPPDATA%\intraday-picks\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
cd /d "%ROOT%"
echo [%date% %time%] start %* >> "%LOGDIR%\task.log"
"%ROOT%\.venv\Scripts\python.exe" -m intraday_picks %* >> "%LOGDIR%\task.log" 2>&1
echo [%date% %time%] exit %ERRORLEVEL% >> "%LOGDIR%\task.log"
endlocal
