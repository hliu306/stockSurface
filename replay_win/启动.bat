@echo off
setlocal
 title Replay - Local Server
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve.ps1"
if errorlevel 1 pause
endlocal
