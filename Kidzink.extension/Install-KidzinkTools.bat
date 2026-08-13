@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: Install-KidzinkTools.bat
:: Kidzink Koda -- pyRevit Extension Installer
::
:: REPO PLACEMENT: repo root, beside Kidzink.extension\
::
::   Revit.Tools-Kidzink\
::     Kidzink.extension\        <- pyRevit extension
::     Install-KidzinkTools.bat  <- this file
::
:: After a GitHub ZIP download the folder will be named
:: something like "Revit.Tools-Kidzink-main\" -- that is fine.
:: %~dp0 always resolves to wherever the BAT actually lives.
:: ============================================================

:: ROOT = folder containing this BAT (trailing backslash stripped)
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "EXTENSION=%ROOT%\Kidzink.extension"

echo.
echo  ================================================
echo   Kidzink Koda -- pyRevit Tools Installer
echo  ================================================
echo.
echo  Detected paths
echo  --------------
echo  This installer : %~f0
echo  Root folder    : %ROOT%
echo  Extension      : %EXTENSION%
echo.

:: ----------------------------------------------------------
:: 1. Verify the extension folder exists beside this BAT
:: ----------------------------------------------------------
if not exist "%EXTENSION%\" (
    echo  ERROR: Kidzink.extension was not found next to this BAT file.
    echo.
    echo  Make sure you extract the ZIP fully before running --
    echo  do not run the BAT from inside the ZIP.
    echo.
    echo  Expected folder:
    echo    %EXTENSION%
    echo.
    echo  Your current folder contains:
    dir /b "%ROOT%"
    echo.
    pause
    exit /b 1
)

:: ----------------------------------------------------------
:: 2. Warn if running from a temp / Downloads location
:: ----------------------------------------------------------
echo %ROOT% | findstr /I "Temp\|Downloads\|AppData\\Local\\Temp" >nul 2>&1
if not errorlevel 1 (
    echo  WARNING: You appear to be running from a temporary location:
    echo    %ROOT%
    echo.
    echo  If you continue, pyRevit will point to this folder.
    echo  If this folder is deleted or moved later, the extension
    echo  will stop loading.
    echo.
    echo  Recommended: move the extracted folder to a stable location
    echo  such as OneDrive or a network share BEFORE continuing.
    echo.
    choice /C YN /M "Continue anyway from this location"
    if errorlevel 2 (
        echo.
        echo  Setup cancelled. Move the folder and re-run the installer.
        echo.
        pause
        exit /b 0
    )
) else (
    echo  Location looks stable. Continuing...
    echo.
)

:: ----------------------------------------------------------
:: 3. Check pyRevit CLI is available
:: ----------------------------------------------------------
where pyrevit >nul 2>&1
if errorlevel 1 (
    echo  ERROR: The pyRevit CLI ^(pyrevit.exe^) was not found.
    echo.
    echo  Install pyRevit first:
    echo    https://github.com/eirannejad/pyRevit/releases
    echo.
    echo  After installing, restart this installer.
    echo.
    pause
    exit /b 1
)

:: ----------------------------------------------------------
:: 4. Check if path is already registered (avoid duplicates)
:: ----------------------------------------------------------
pyrevit extensions paths >nul 2>&1
pyrevit extensions paths | findstr /I "%ROOT%" >nul 2>&1
if not errorlevel 1 (
    echo  This path is already registered with pyRevit:
    echo    %ROOT%
    echo.
    echo  Nothing to do. If the tab is missing in Revit, run:
    echo    pyrevit reload
    echo.
    pause
    exit /b 0
)

:: ----------------------------------------------------------
:: 5. Register the extension search path
::    The argument is the PARENT of Kidzink.extension\
::    pyRevit discovers the extension by the .extension suffix
:: ----------------------------------------------------------
echo  Registering extension path...
echo    pyrevit extensions paths add "%ROOT%"
echo.

pyrevit extensions paths add "%ROOT%"

if errorlevel 1 (
    echo.
    echo  ERROR: pyRevit returned an error.
    echo  Try running this BAT as Administrator, or check the
    echo  output above for details.
    echo.
    pause
    exit /b 1
)

:: ----------------------------------------------------------
:: 6. Success
:: ----------------------------------------------------------
echo.
echo  ================================================
echo   Installation complete!
echo  ================================================
echo.
echo  Kidzink.extension is now registered at:
echo    %ROOT%
echo.
echo  Next steps:
echo    1. Open Revit (or restart if already open).
echo    2. The KidzinkTools tab will appear automatically.
echo    3. If it does not appear, use the pyRevit ribbon
echo       to reload, or run:  pyrevit reload
echo.
pause
exit /b 0
