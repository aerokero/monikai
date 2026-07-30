@echo off
setlocal
cd /d "%~dp0"

echo Starting Monik.AI desktop client...
echo Backend: configured in .env.local
echo.

call npm run dev:client
if errorlevel 1 (
    echo.
    echo Monik.AI client could not be started.
    pause
)

endlocal
