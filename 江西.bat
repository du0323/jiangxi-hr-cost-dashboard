@echo off
chcp 65001 >nul
echo ====================================
echo   江西战区人力成本分析看板
echo ====================================
echo.
cd /d "%~dp0"
set "PORT=3003"
set "DATA_DIR=data"
set "ZONE_NAME=江西战区"
node server.js
pause
