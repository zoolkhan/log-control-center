@echo off
setlocal
echo --- LOG CONTROL CENTER INSTALLER ---

:: Try to find the best python command
set "PY_CMD="
for %%i in (python, py, python3) do (
    where %%i >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=%%i"
        goto :found
    )
)

:found
if "%PY_CMD%"=="" (
    echo ERROR: Python was not found. 
    echo Please install Python from python.org and ensure "Add Python to PATH" is checked.
    pause
    exit /b
)

echo Found Python using command: %PY_CMD%
%PY_CMD% --version

echo Creating Virtual Environment...
%PY_CMD% -m venv venv

echo Installing Dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo INSTALLATION COMPLETE!
echo You can now run the app using 'run.bat'
pause
