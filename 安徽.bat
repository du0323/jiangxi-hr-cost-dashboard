@echo off
echo ====================================
echo   安徽战区人力成本分析看板
echo ====================================
echo.
cd /d "%~dp0"
set PORT=3001
set DATA_DIR=data-anhui
set ZONE_NAME=安徽战区
node server.js
pause
