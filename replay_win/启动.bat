@echo off
chcp 65001 >nul
title Replay - 行业轮动回放
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve.ps1"
pause
