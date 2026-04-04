@echo off
echo ========================================
echo Shopify Tool - Development Mode
echo ========================================
echo.

REM Set development environment variable
set FULFILLMENT_SERVER_PATH=D:\Dev\fulfillment-server-mock

echo Environment: DEVELOPMENT
echo Server Path: %FULFILLMENT_SERVER_PATH%
echo.

REM Check if dev structure exists
if not exist "%FULFILLMENT_SERVER_PATH%\Clients" (
    echo Dev environment not found. Running setup with pre-populated session...
    python scripts/setup_dev_env.py --with-session --with-analysis "%FULFILLMENT_SERVER_PATH%"
    echo.
)

echo ========================================
echo Starting Shopify Tool...
echo ========================================
echo.
python gui_main.py

pause
