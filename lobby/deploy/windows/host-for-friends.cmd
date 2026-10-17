@echo off
rem Host a T5DR lobby for your friends on this PC (the launcher's "Host for friends" does the same).
rem   Double-click it, or from a console:   host-for-friends.cmd [--map-ports] [--port 7781] [--guests-only]
rem   --map-ports asks your router to forward the ports (UPnP / NAT-PMP); nothing is sent to it otherwise.
rem Stop with Ctrl+C. Data, logs and backups: %LOCALAPPDATA%\T5DR Online\lobby-host
setlocal
set "LOBBY=%~dp0..\.."
if exist "%LOBBY%\..\python\python.exe" goto :bundled
where py >nul 2>nul
if not errorlevel 1 goto :launcher
python "%LOBBY%\run.py" host %*
goto :done
:bundled
rem the release zip's own Python
"%LOBBY%\..\python\python.exe" "%LOBBY%\run.py" host %*
goto :done
:launcher
py -3 "%LOBBY%\run.py" host %*
:done
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" exit /b 0
echo.
echo The lobby server stopped with an error (code %RC%). See above, or the log:
echo   %LOCALAPPDATA%\T5DR Online\lobby-host\logs\t5lobby.log
pause
exit /b %RC%
