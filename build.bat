@echo off
setlocal

echo ================================================
echo  Shopify Fulfillment Tool -- PyInstaller Build
echo ================================================
echo.

REM Clean previous build artifacts
if exist build\ (
    echo Cleaning build\...
    rmdir /s /q build
)
if exist dist\ (
    echo Cleaning dist\...
    rmdir /s /q dist
)

echo.
echo Running PyInstaller...
echo.

pyinstaller shopify_fulfillment.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED ^(exit code %ERRORLEVEL%^)
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================================
echo  Build complete: dist\ShopifyFulfillmentTool\
echo ================================================
pause
