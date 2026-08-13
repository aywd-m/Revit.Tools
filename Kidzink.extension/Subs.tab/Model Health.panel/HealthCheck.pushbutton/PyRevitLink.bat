if not exist "%EXTENSION%\" (
    echo ERROR: CompanyTools.extension was not found.
    echo.
    echo Keep this BAT file in the repository root,
    echo beside the CompanyTools.extension folder.
    echo Expected:
    echo   %EXTENSION%
    echo.
    pause
    exit /b 1
)

echo.
echo IMPORTANT - Recommended shared deployment
echo -----------------------------------------
echo Before continuing, it is recommended to move this entire folder,
echo including this BAT file and CompanyTools.extension, to a stable
echo shared server location accessible to all intended users.
echo.
echo Example:
echo   \\CompanyServer\BIM-Tools\pyRevit\Revit.Tools\
echo.
echo Run this installer from that shared location so each user points
echo to the same centrally managed extension copy.
echo.
echo Do NOT run the installer from Downloads or a temporary extracted
echo ZIP folder. If this folder is moved, renamed, or deleted after
echo setup, pyRevit will no longer find the extension.
echo.
choice /C YN /M "Is this folder in its final shared location"
if errorlevel 2 (
    echo.
    echo Setup cancelled.
    echo Move the entire Revit.Tools folder to the approved shared
    echo server location, then run Install-CompanyTools.bat again.
    echo.
    pause
    exit /b 0
)

where pyrevit >nul 2>&1
if errorlevel 1 (
    echo pyRevit was not found on this computer.
    echo.
    echo Install pyRevit first, then restart this installer.
    echo.
    pause
    exit /b 1
)

pyrevit extensions paths add "%ROOT%"